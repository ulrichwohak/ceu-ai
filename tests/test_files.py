"""Offline regression tests for the CEU terminal client; no real credentials used."""

from __future__ import annotations

import contextlib
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest.mock import Mock
from unittest.mock import patch
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ceu-ai.py"
if not MODULE.exists():
    MODULE = Path(__file__).with_name("ceu-ai.py")
spec = importlib.util.spec_from_file_location("ceu", MODULE)
ceu = importlib.util.module_from_spec(spec)
sys.modules["ceu"] = ceu
spec.loader.exec_module(ceu)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = []

    def apply(self, files, answer=True, expected=None):
        return ceu.apply_files(self.root, files, lambda _: answer, self.output.append, expected)

    def test_creates_multiple_files_without_executing_them(self):
        result = self.apply([
            {"path": "src/hello.py", "content": "raise RuntimeError('not executed')\n"},
            {"path": "README.md", "content": "Generated example.\n"},
        ])
        self.assertEqual(result, ["src/hello.py", "README.md"])
        self.assertIn("RuntimeError", (self.root / "src/hello.py").read_text())

    def test_declining_overwrite_cancels_whole_batch(self):
        (self.root / "analysis.py").write_text("x = 1\n", newline="\n")
        result = self.apply([
            {"path": "new.py", "content": "x = 3\n"},
            {"path": "analysis.py", "content": "x = 2\n"},
        ], answer=False)
        self.assertEqual(result, [])
        self.assertFalse((self.root / "new.py").exists())
        self.assertEqual((self.root / "analysis.py").read_text(), "x = 1\n")

    def test_approved_replacement_keeps_backup(self):
        (self.root / "analysis.py").write_text("x = 1\n", newline="\n")
        self.apply([{"path": "analysis.py", "content": "x = 2\n"}])
        backups = list((self.root / ".ceu/backups").rglob("analysis.py"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "x = 1\n")
        self.assertEqual((self.root / "analysis.py").read_text(), "x = 2\n")
        self.assertTrue(any("-x = 1" in line for line in self.output))

    def test_automatic_batch_reports_created_updated_deleted_and_keeps_originals(self):
        (self.root / "update.py").write_text("x = 1\n", newline="\n")
        (self.root / "remove.py").write_text("old work\n", newline="\n")
        changed = ceu.apply_files(self.root, [
            {"path": "new.py", "content": "raise RuntimeError('not executed')\n"},
            {"path": "update.py", "content": "x = 2\n"},
        ], emit=self.output.append, delete_files=["remove.py"])
        self.assertEqual(changed, ["new.py", "update.py", "remove.py"])
        self.assertEqual((self.root / "update.py").read_text(), "x = 2\n")
        self.assertFalse((self.root / "remove.py").exists())
        self.assertEqual(self.output[:3], ["Created new.py", "Updated update.py", "Deleted remove.py"])
        self.assertFalse(any(line.startswith("---") for line in self.output))
        backups = list((self.root / ".ceu/backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "update.py").read_text(), "x = 1\n")
        self.assertEqual((backups[0] / "remove.py").read_text(), "old work\n")
        self.assertIn(str(backups[0].relative_to(self.root)), self.output[-1])

    def test_deletion_rejects_directories_missing_files_and_protected_paths_before_writes(self):
        (self.root / "folder").mkdir()
        for name in ("folder", "missing.py", "../outside.py", ".git/config", "harness.md",
                     "ceu-ai.py", "data/raw/source.csv", "ceu-api-credentials.txt"):
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                ceu.apply_files(self.root, [{"path": "new.py", "content": "x = 1"}],
                                emit=self.output.append, delete_files=[name])
            self.assertFalse((self.root / "new.py").exists())
            self.assertFalse((self.root / ".ceu").exists())
        self.assertTrue((self.root / "folder").is_dir())

    def test_deletion_rejects_symlinks_and_existing_datasets(self):
        (self.root / "data.csv").write_text("price\n80\n", newline="\n")
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "notes.txt"
            target.write_text("Keep this", newline="\n")
            (self.root / "link.txt").symlink_to(target)
            for name in ("link.txt", "data.csv"):
                with self.subTest(name=name), self.assertRaises(ceu.UserError):
                    ceu.apply_files(self.root, [], delete_files=[name])
            self.assertEqual(target.read_text(), "Keep this")
        self.assertEqual((self.root / "data.csv").read_text(), "price\n80\n")

    def test_write_delete_conflict_is_rejected_before_any_change(self):
        path = self.root / "analysis.py"
        path.write_text("x = 1", newline="\n")
        with self.assertRaisesRegex(ceu.UserError, "same file twice"):
            ceu.apply_files(self.root, [{"path": "analysis.py", "content": "x = 2"}],
                            delete_files=["analysis.py"])
        self.assertEqual(path.read_text(), "x = 1")
        self.assertFalse((self.root / ".ceu").exists())

    def test_deletion_preserves_newer_editor_changes(self):
        path = self.root / "analysis.py"
        path.write_text("newer work", newline="\n")
        with self.assertRaisesRegex(ceu.UserError, "changed in your editor"):
            ceu.apply_files(self.root, [], expected={"analysis.py": "old work"}, delete_files=["analysis.py"])
        self.assertEqual(path.read_text(), "newer work")
        self.assertFalse((self.root / ".ceu").exists())

    def test_editor_change_while_waiting_is_preserved(self):
        (self.root / "analysis.py").write_text("x = 99\n", newline="\n")
        with self.assertRaises(ceu.UserError):
            self.apply([{"path": "analysis.py", "content": "x = 2\n"}],
                       expected={"analysis.py": "x = 1\n"})
        self.assertEqual((self.root / "analysis.py").read_text(), "x = 99\n")

    def test_editor_change_during_confirmation_is_preserved(self):
        path = self.root / "analysis.py"
        path.write_text("x = 1\n", newline="\n")
        def confirm(_):
            path.write_text("x = 99\n", newline="\n")
            return True
        with self.assertRaises(ceu.UserError):
            ceu.apply_files(self.root, [{"path": "analysis.py", "content": "x = 2\n"}], confirm, self.output.append)
        self.assertEqual(path.read_text(), "x = 99\n")

    def test_unsafe_paths_are_rejected_before_any_write(self):
        for name in ("../escape.py", "/tmp/escape.py", "C:\\escape.py", ".env", ".ceu/config.json",
                     "nested/.secrets.md", "data/raw/data.csv", "credentials.json", "key.pem", "ceu-ai.py",
                     "NUL.py", "hello\x1b.py"):
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                self.apply([{"path": "good.py", "content": "x = 1"}, {"path": name, "content": "x = 2"}])
            self.assertFalse((self.root / "good.py").exists())

    def test_duplicate_and_conflicting_paths_are_rejected(self):
        for names in (("a.py", "a.py"), ("a.py", "A.py"), ("a", "a/b.py")):
            with self.subTest(names=names), self.assertRaises(ceu.UserError):
                self.apply([{"path": name, "content": "x = 1"} for name in names])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ceu.UserError):
                self.apply([{"path": "link/out.py", "content": "x = 1"}])
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_invalid_python_does_not_write_any_files(self):
        with self.assertRaises(ceu.UserError):
            self.apply([{"path": "good.py", "content": "x = 1"}, {"path": "bad.py", "content": "def !"}])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_read_context_only_reads_explicitly_shared_files(self):
        (self.root / "chosen.py").write_text("x = 1", newline="\n")
        (self.root / "unshared.py").write_text("x = 2", newline="\n")
        (self.root / ".env").write_text("DUMMY_SECRET=not-real", newline="\n")
        self.assertEqual(ceu.read_context(self.root, {"chosen.py"}), {"chosen.py": "x = 1"})
        with self.assertRaises(ceu.UserError):
            ceu.read_context(self.root, {".env"})

    def test_csv_context_is_a_read_only_summary_with_five_preview_rows(self):
        path = self.root / "data/raw/hotels.csv"
        path.parent.mkdir(parents=True)
        source = "city,price,distance_miles\n" + "Vienna,80,2.5\n" * 5 + "NOT_IN_PREVIEW,90,3.5\n"
        path.write_text(source, newline="\n")
        (self.root / "unshared.csv").write_text("private\nNEVER_SEND_THIS\n", newline="\n")
        context = ceu.read_context(self.root, {"data/raw/hotels.csv"})
        summary = json.loads(context["data/raw/hotels.csv"])
        self.assertEqual(summary["kind"], "read_only_csv_summary")
        self.assertEqual(summary["row_count"], 6)
        self.assertEqual([c["name"] for c in summary["columns"]], ["city", "price", "distance_miles"])
        self.assertEqual(summary["columns"][1]["dtype"], "int64")
        self.assertEqual(summary["columns"][2]["dtype"], "float64")
        self.assertEqual(len(summary["preview"]), 5)
        self.assertNotIn("NOT_IN_PREVIEW", context["data/raw/hotels.csv"])
        self.assertNotIn("NEVER_SEND_THIS", str(context))
        self.assertEqual(path.read_text(), source)

    def test_csv_types_use_all_rows_and_preview_handles_missing_values(self):
        path = self.root / "sample.csv"
        path.write_text("price,label\n80,a\n,b\n90,c\n100,d\n110,e\n120.5,f\n", newline="\n")
        summary = json.loads(ceu.read_context(self.root, {"sample.csv"})["sample.csv"])
        self.assertEqual(summary["columns"][0]["dtype"], "float64")
        self.assertIsNone(summary["preview"][1]["price"])
        self.assertEqual(summary["row_count"], 6)

    def test_csv_summary_supports_files_larger_than_text_context_limit(self):
        path = self.root / "sample.csv"
        path.write_text("price,description\n" + "100,Hotel room\n" * 20_000, newline="\n")
        self.assertGreater(path.stat().st_size, ceu.MAX_CONTEXT)
        context = ceu.read_context(self.root, {"sample.csv"})
        self.assertEqual(json.loads(context["sample.csv"])["row_count"], 20_000)
        self.assertLess(len(context["sample.csv"].encode()), ceu.MAX_CONTEXT)

    def test_csv_preview_truncates_long_text_and_keeps_headers(self):
        (self.root / "sample.csv").write_text("long_column_name\n" + "x" * 500 + "\n", newline="\n")
        summary = json.loads(ceu.read_context(self.root, {"sample.csv"})["sample.csv"])
        self.assertEqual(summary["columns"][0]["name"], "long_column_name")
        self.assertEqual(summary["preview"][0]["long_column_name"], "x" * ceu.CSV_PREVIEW_CHARS + "... [truncated]")

    def test_header_only_csv_is_valid(self):
        (self.root / "empty.csv").write_text("price,distance_miles\n", newline="\n")
        summary = json.loads(ceu.read_context(self.root, {"empty.csv"})["empty.csv"])
        self.assertEqual(summary["row_count"], 0)
        self.assertEqual(summary["preview"], [])

    def test_invalid_and_oversized_csv_fail_with_friendly_errors(self):
        path = self.root / "bad.csv"
        for content in (b"", b"a,b\n1,2\n3,4,5\n", b"a\n\xff\n"):
            with self.subTest(content=content):
                path.write_bytes(content)
                with self.assertRaisesRegex(ceu.UserError, "Cannot read"):
                    ceu.read_context(self.root, {"bad.csv"})
        path.write_text("value\n1\n", newline="\n")
        with patch.object(ceu, "MAX_CSV_BYTES", 1), self.assertRaisesRegex(ceu.UserError, "CSV limit"):
            ceu.read_context(self.root, {"bad.csv"})

    def test_csv_summary_obeys_total_context_limit(self):
        (self.root / "small.csv").write_text("value\n1\n", newline="\n")
        with patch.object(ceu, "MAX_CONTEXT", 100), self.assertRaisesRegex(ceu.UserError, "shared files are too large"):
            ceu.read_context(self.root, {"small.csv"})

    def test_csv_read_access_does_not_weaken_path_or_raw_write_protection(self):
        for name in ("../outside.csv", ".ceu/config.csv", "data/raw/notes.txt", "venv/data.csv", "secret.key"):
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                ceu.read_context(self.root, {name})
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "linked.csv").symlink_to(Path(outside) / "data.csv")
            with self.assertRaises(ceu.UserError):
                ceu.read_context(self.root, {"linked.csv"})
        for name in ("data/raw/hotels.csv", "Data/Raw/hotels.csv"):
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                self.apply([{"path": "good.py", "content": "x = 1"}, {"path": name, "content": "a\n1\n"}])
        self.assertFalse((self.root / "good.py").exists())

    def test_existing_csv_outside_raw_cannot_be_overwritten(self):
        (self.root / "sample.csv").write_text("price\n80\n", newline="\n")
        expected = ceu.read_context(self.root, {"sample.csv"})
        with self.assertRaisesRegex(ceu.UserError, "read-only"):
            self.apply([{"path": "new.py", "content": "x = 1"},
                        {"path": "sample.csv", "content": "price\n999\n"}], expected=expected)
        self.assertEqual((self.root / "sample.csv").read_text(), "price\n80\n")
        self.assertFalse((self.root / "new.py").exists())

    def test_notebook_cell_ids_are_repaired_and_saved_without_warnings(self):
        import nbformat

        for minor in (4, 5):
            with self.subTest(minor=minor):
                notebook = {"nbformat": 4, "nbformat_minor": minor, "metadata": {}, "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": "A heading", "id": "keep-me"},
                    {"cell_type": "code", "metadata": {}, "source": "x = 1", "execution_count": None, "outputs": []},
                    {"cell_type": "raw", "metadata": {}, "source": "Some notes", "id": "keep-me"},
                ]}
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    self.apply([{"path": f"notebook-{minor}.ipynb", "content": json.dumps(notebook)}])
                    saved = nbformat.read(self.root / f"notebook-{minor}.ipynb", as_version=4)
                    nbformat.validate(saved)
                self.assertEqual(caught, [])
                self.assertEqual(saved.nbformat_minor, 5)
                ids = [cell.id for cell in saved.cells]
                self.assertEqual(ids[0], "keep-me")
                self.assertEqual(len(set(ids)), 3)
                self.assertEqual([cell.source for cell in saved.cells], ["A heading", "x = 1", "Some notes"])
                self.assertIsNone(saved.cells[1].execution_count)
                self.assertEqual(saved.cells[1].outputs, [])

    def test_notebook_repair_does_not_accept_bad_code_or_stored_results(self):
        for changes in ({"source": "def !"}, {"execution_count": 1},
                        {"outputs": [{"output_type": "stream", "name": "stdout", "text": "fake result"}]}):
            cell = {"cell_type": "code", "metadata": {}, "source": "x = 1", "execution_count": None, "outputs": []}
            cell.update(changes)
            notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [cell]}
            with self.subTest(changes=changes), self.assertRaises(ceu.UserError):
                self.apply([{"path": "good.py", "content": "x = 1"},
                            {"path": "bad.ipynb", "content": json.dumps(notebook)}])
        self.assertFalse((self.root / "good.py").exists())
        self.assertFalse((self.root / "bad.ipynb").exists())

    def test_notebook_accepts_strings_and_lists_of_lines_without_changing_content(self):
        import nbformat

        sources = ["# Description\n\nA café example.\n", "x = 1\nprint(x)\n", "Unformatted\nnotes"]
        for as_list in (False, True):
            cells = []
            for kind, source in zip(("markdown", "code", "raw"), sources):
                cell = {"cell_type": kind, "metadata": {},
                        "source": source.splitlines(keepends=True) if as_list else source}
                if kind == "code":
                    cell.update(execution_count=None, outputs=[])
                cells.append(cell)
            notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": cells}
            name = f"source-{as_list}.ipynb"
            with self.subTest(as_list=as_list), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.apply([{"path": name, "content": json.dumps(notebook)}])
                saved = nbformat.read(self.root / name, as_version=4)
                nbformat.validate(saved)
            self.assertEqual(caught, [])
            self.assertEqual([cell.source for cell in saved.cells], sources)
            self.assertEqual(len({cell.id for cell in saved.cells}), 3)

    def test_invalid_source_lists_are_rejected_with_field_not_full_content(self):
        for source in (["SECRET_SENTINEL\n", 42], [None], [["nested"]]):
            notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
                {"cell_type": "code", "id": "cell-1", "metadata": {}, "source": source,
                 "execution_count": None, "outputs": []}]}
            with self.subTest(source=source), self.assertRaises(ceu.InvalidSourceError) as caught:
                self.apply([{"path": "good.py", "content": "x = 1"},
                            {"path": "bad.ipynb", "content": json.dumps(notebook)}])
            self.assertIn("cells.0.source", str(caught.exception))
            self.assertNotIn("SECRET_SENTINEL", str(caught.exception))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_notebook_syntax_error_identifies_cell_and_line_without_printing_code(self):
        notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
            {"cell_type": "markdown", "id": "intro", "metadata": {}, "source": "Intro"},
            {"cell_type": "code", "id": "code", "metadata": {},
             "source": ["x = 1\n", "SECRET_SENTINEL =\n"], "execution_count": None, "outputs": []}]}
        with self.assertRaises(ceu.InvalidSourceError) as caught:
            ceu.validate_source("analysis.ipynb", json.dumps(notebook))
        message = str(caught.exception)
        self.assertIn("analysis.ipynb", message)
        self.assertIn("cell 2, line 2", message)
        self.assertIn("invalid Python syntax", message)
        self.assertNotIn("SECRET_SENTINEL", message)

    def test_notebook_json_and_version_errors_are_specific(self):
        for source, reason in (("{\ninvalid}", "JSON at line 2"),
                               ("[]", "JSON must be an object"),
                               ('{"nbformat": 4.5}', "nbformat must be the integer 4"),
                               ('{"nbformat": 4, "nbformat_minor": "5"}', "nbformat_minor")):
            with self.subTest(source=source), self.assertRaisesRegex(ceu.InvalidSourceError, reason):
                ceu.validate_source("analysis.ipynb", source)

    def test_structured_notebook_cells_are_packaged_without_changing_code(self):
        import nbformat

        source = "x = 1\nprint('first\\nsecond')\npath = r'C:\\new'\n"
        original = {"cells": [{"cell_type": "markdown", "source": "# Example"},
                              {"cell_type": "code", "source": source}]}
        reply = ceu.parse_reply(json.dumps({"message": "Ready", "files": [
            {"path": "analysis.ipynb", "content": original}]}))
        self.apply(reply["files"])
        saved = nbformat.read(self.root / "analysis.ipynb", as_version=4)
        nbformat.validate(saved)
        self.assertEqual(saved.cells[1].source, source)
        self.assertEqual(saved.metadata.kernelspec.name, "python3")
        self.assertEqual(saved.metadata.kernelspec.display_name, "Python 3 (ipykernel)")
        self.assertIsNone(saved.cells[1].execution_count)
        self.assertEqual(saved.cells[1].outputs, [])
        self.assertTrue(all(cell.id for cell in saved.cells))
        self.assertNotIn("nbformat", original)

    def test_structured_notebooks_still_reject_bad_code_and_stored_results(self):
        for changes in ({"source": "def !"}, {"execution_count": 1},
                        {"outputs": [{"output_type": "stream", "name": "stdout", "text": "invented"}]}):
            cell = {"cell_type": "code", "source": "x = 1"} | changes
            reply = ceu.parse_reply(json.dumps({"message": "Ready", "files": [
                {"path": "good.py", "content": "x = 1"},
                {"path": "bad.ipynb", "content": {"cells": [cell]}}]}))
            with self.subTest(changes=changes), self.assertRaises(ceu.InvalidSourceError):
                self.apply(reply["files"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_structured_content_is_only_allowed_for_notebooks_and_is_size_limited(self):
        for path, content in (("analysis.py", {"cells": []}), ("analysis.ipynb", []),
                              ("analysis.ipynb", None)):
            with self.subTest(path=path, content=content), self.assertRaises(ceu.UserError):
                ceu.parse_reply(json.dumps({"message": "Ready", "files": [{"path": path, "content": content}]}))
        with patch.object(ceu, "MAX_BYTES", 10), self.assertRaisesRegex(ceu.UserError, "too large"):
            ceu.parse_reply(json.dumps({"message": "Ready", "files": [
                {"path": "analysis.ipynb", "content": {"cells": []}}]}))

    def test_required_field_error_identifies_missing_field(self):
        content = ceu.notebook_content({"cells": [{"cell_type": "code"}]})
        with self.assertRaisesRegex(ceu.InvalidSourceError, "missing required fields: source"):
            ceu.validate_source("analysis.ipynb", content)

    def test_uppercase_extensions_do_not_bypass_source_validation(self):
        for name, content in (("bad.PY", "def !"), ("bad.IPYNB", "not JSON")):
            with self.subTest(name=name), self.assertRaises(ceu.InvalidSourceError):
                ceu.validate_source(name, content)

    def test_setup_round_trip_and_private_permissions(self):
        path = self.root / ".ceu/config.json"
        config = ceu.Config("dummy-id", "dummy-secret")
        ceu.save_config(config, path)
        self.assertEqual(ceu.load_config(path), config)
        self.assertEqual(set(json.loads(path.read_text())), {"client_id", "secret"})
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_symlink_config_is_rejected(self):
        (self.root / ".ceu").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ceu.UserError):
            ceu.save_config(ceu.Config("dummy", "dummy"), self.root / ".ceu/config.json")
