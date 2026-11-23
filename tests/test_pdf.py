"""Exercise local PDF extraction with real documents and an offline chat client."""

import contextlib
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import test_app as fixtures
from test_files import ceu


class PdfTests(unittest.TestCase):
    setUp = fixtures.AppTests.setUp
    file = fixtures.AppTests.file
    client = fixtures.AppTests.client
    workspace = fixtures.AppTests.workspace
    generate = fixtures.AppTests.generate

    def pdf(self, name, pages, password=None):
        with PdfWriter() as writer:
            for text in pages:
                page = writer.add_blank_page(612, 792)
                stream = DecodedStreamObject()
                if text is None:
                    # A grayscale image with no accompanying text layer.
                    stream.set_data(b"q 100 0 0 100 20 100 cm BI /W 1 /H 1 /BPC 8 /CS /G ID \x80 EI Q")
                else:
                    font = DictionaryObject({
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                    })
                    page[NameObject("/Resources")] = DictionaryObject({
                        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
                    })
                    content = text.encode("cp1252").hex().encode("ascii")
                    stream.set_data(b"BT /F1 12 Tf 50 700 Td <" + content + b"> Tj ET")
                page[NameObject("/Contents")] = writer._add_object(stream)
            if password:
                writer.encrypt(password, algorithm="RC4-128")
            path = self.file(name, "")
            writer.write(path)
        return path

    def test_pdf_text_reaches_chat_with_page_numbers_but_no_binary_data(self):
        name = "materials/Reader notes.PDF"
        self.pdf(name, ["Café prices rose by twelve percent.", None, "The survey had 27 responses."])
        client = self.client([
            {"message": "Inspect", "files": [], "read_files": [name]},
            {"message": "Done", "files": [{"path": "work/notes.md", "content": "The survey had 27 responses."}]},
        ])
        reply, files = self.generate(client)
        first, second = [json.loads(req.data)["messages"][0]["content"] for req in self.requests]
        self.assertNotIn("Café prices", first)
        self.assertIn("page 1 of 3", files[name])
        self.assertIn("Café prices rose by twelve percent.", second)
        self.assertIn("page 2 of 3", second)
        self.assertIn("No extractable text on this page", second)
        self.assertIn("The survey had 27 responses.", second)
        self.assertNotIn("%PDF", second)
        self.assertEqual(self.workspace().apply(reply, files, lambda _: "", emit=lambda _: None), ["work/notes.md"])

    def test_scanned_encrypted_and_malformed_pdfs_have_actionable_errors(self):
        self.pdf("materials/scan.pdf", [None])
        self.pdf("materials/locked.pdf", ["Protected"], "password")
        aes_fixture = Path(__file__).with_name("fixtures") / "locked-aes.pdf"
        self.file("materials/locked-aes.pdf", "").write_bytes(aes_fixture.read_bytes())
        self.file("materials/broken.pdf", "%PDF-1.4\n")
        self.file("materials/fake.pdf", "Plain text with a misleading extension")
        for name, advice in [
            ("scan.pdf", "OCR"),
            ("locked.pdf", "unlocked copy"),
            ("locked-aes.pdf", "unlocked copy"),
            ("broken.pdf", "export a fresh PDF"),
            ("fake.pdf", "does not have a PDF header"),
        ]:
            with self.subTest(name=name), self.assertRaisesRegex(ceu.UserError, advice):
                self.workspace().read({f"materials/{name}"})

    def test_pdf_page_size_and_text_limits(self):
        name = "materials/reader.pdf"
        self.pdf(name, ["Evidence"] * (ceu.MAX_PDF_PAGES + 1))
        with self.assertRaisesRegex(ceu.UserError, "smaller section"):
            self.workspace().read({name})
        self.pdf(name, ["Long reading. " * 300] * 30)
        with self.assertRaisesRegex(ceu.UserError, "too much text"):
            self.workspace().read({name})
        with patch.object(ceu, "MAX_PDF_BYTES", 64), patch.object(ceu.subprocess, "run") as worker:
            with self.assertRaisesRegex(ceu.UserError, "20 MB"):
                self.workspace().read({name})
            worker.assert_not_called()

    def test_chat_reports_failed_pdf_read_and_keeps_running(self):
        name = "materials/scan.pdf"
        self.pdf(name, [None])
        client = self.client([{"message": "Chat is working.", "files": []}])
        answers = iter([f"/add {name}", "Say hello.", "/quit"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ceu.run_chat(client, self.workspace(), lambda _: next(answers))
        self.assertIn("run OCR", output.getvalue())
        self.assertIn("Chat is working.", output.getvalue())
        self.assertEqual(client.calls, 1)

    def test_add_accepts_a_quoted_pdf_path_and_shares_text_on_next_prompt(self):
        name = "materials/Week 2 notes.pdf"
        self.pdf(name, ["The agreed deadline is 10 June."])
        client = self.client([{"message": "The deadline is 10 June.", "files": []}])
        answers = iter([f'/add "{name}"', "When is the deadline?", "/quit"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ceu.run_chat(client, self.workspace(), lambda _: next(answers))
        self.assertIn(f"Added {name}", output.getvalue())
        self.assertEqual(client.calls, 1)
        self.assertIn("The agreed deadline is 10 June.", self.requests[0].data.decode("utf-8"))

    def test_pdf_timeout_is_a_read_error(self):
        name = "materials/reader.pdf"
        self.pdf(name, ["Evidence"])
        with patch.object(ceu.subprocess, "run", side_effect=subprocess.TimeoutExpired("pdf worker", 1)):
            with self.assertRaisesRegex(ceu.UserError, "took too long"):
                self.workspace().read({name})

    def test_pdf_text_respects_scope_and_credentials_and_pdf_is_read_only(self):
        name = "materials/reader.pdf"
        original = self.pdf(name, ["test-client-secret"]).read_bytes()
        requests = [
            {"message": "Inspect", "files": [], "read_files": [name, "other/reader.pdf"]},
            {"message": "Unavailable", "files": []},
        ]
        self.pdf("other/reader.pdf", ["PRIVATE_PDF_CONTENT"])
        self.generate(self.client(requests))
        sent = b"".join(request.data for request in self.requests)
        self.assertNotIn(b"test-client-secret", sent)
        self.assertNotIn(b"PRIVATE_PDF_CONTENT", sent)
        with self.assertRaisesRegex(ceu.UserError, "read-only"):
            ceu.apply_files(self.root, [{"path": name, "content": "Attempted overwrite"}])
        with self.assertRaisesRegex(ceu.UserError, "read-only"):
            ceu.apply_files(self.root, [], delete_files=[name])
        self.assertEqual((self.root / name).read_bytes(), original)
