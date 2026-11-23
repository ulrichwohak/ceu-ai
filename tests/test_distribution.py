"""Regression tests for credential-only startup and a single distributable script."""
import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_app as fixtures
from test_files import ceu


class DistributionTests(unittest.TestCase):
    setUp = fixtures.AppTests.setUp
    file = fixtures.AppTests.file
    client = fixtures.AppTests.client

    def script(self):
        path = self.root / 'ceu-api.py'
        shutil.copyfile(Path(ceu.__file__), path)
        return path

    def fresh_module(self, path):
        name = 'ceu_student_' + str(id(path))
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        return module

    def test_default_access_covers_project_and_hidden_source_folders(self):
        (self.root / 'harness.md').unlink()
        names = ['README', 'src/app.py', 'data/raw/notes.txt', 'grading/rubric.md',
                 'exams/revision.md', 'private/draft.txt', '.github/workflows/build.yml',
                 '.vscode/settings.json', 'AGENTS.md', 'tables/schema.toml']
        for name in names:
            self.file(name, 'Sample text')
        workspace = ceu.Workspace(self.root, ceu.load_settings(self.root))
        self.assertEqual(workspace.course_context()['guide']['status'], 'not_provided')
        self.assertEqual(set(workspace.read(set(names))), set(names))
        self.assertTrue(set(names).issubset(workspace.tree()['tree']))
        self.assertEqual(workspace.path('any/new/place.txt', writing=True), self.root / 'any/new/place.txt')

    def test_full_scope_still_excludes_credentials_environments_and_traversal(self):
        workspace = ceu.Workspace(self.root, ceu.Settings())
        for name in ['.env', '.env.local', '.ceu/config.json', '.git/config',
                     '.venv/site.py', 'nested/credentials.json', '../outside.txt', 'ssh/private-key.pem']:
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                workspace.path(name)

    def test_unhandled_binary_files_fail_without_guessing_their_contents(self):
        for name, content in [('image.png', b'\x89PNG\0'), ('document.txt', b'%PDF-1.4\n')]:
            path = self.file(name, '')
            path.write_bytes(content)
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                ceu.Workspace(self.root, ceu.Settings()).read({name})

    def test_configured_script_carries_preferences_without_credentials_or_sidecars(self):
        script = self.script()
        client = self.client(names=['class-model'])
        answers = iter(['1', 'Explain uncertainty and cite supplied sources.'])
        with patch.object(ceu, '__file__', str(script)), contextlib.redirect_stdout(io.StringIO()):
            settings = ceu.configure_preferences(self.root, client, lambda _: next(answers))
        self.assertEqual(client.calls, 0)
        self.assertFalse((self.root / 'ceu-ai.json').exists())
        source = script.read_text()
        self.assertNotIn(client.config.client_id, source)
        self.assertNotIn(client.config.secret, source)
        self.assertTrue(list((self.root / '.ceu/backups').rglob('ceu-api.py')))
        with tempfile.TemporaryDirectory() as folder:
            student = Path(folder).resolve()
            copied = student / script.name
            shutil.copyfile(script, copied)
            module = self.fresh_module(copied)
            loaded = module.load_settings(student)
            self.assertEqual(loaded.model, settings.model)
            self.assertEqual(loaded.instructions, settings.instructions)
            self.assertEqual(loaded.context_paths, ['.'])
            self.assertEqual(loaded.output_paths, ['.'])
            self.assertEqual(list(student.iterdir()), [copied])
            session = Mock(prompt=Mock(side_effect=['student-id', '/quit']))
            with patch.object(module.Path, 'cwd', return_value=student), \
                 patch.object(module.sys, 'argv', ['ceu-api.py']), \
                 patch.object(module.sys.stdin, 'isatty', return_value=True), \
                 patch('prompt_toolkit.PromptSession', return_value=session), \
                 patch.object(module, 'read_secret', return_value='student-secret'), \
                 patch.object(module.CEUClient, 'models', return_value=['class-model']), \
                 patch.object(module.CEUClient, 'complete', side_effect=AssertionError('No setup call')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 0)
            self.assertEqual([c.args[0] for c in session.prompt.call_args_list], ['Client ID: ', 'You> '])
            self.assertEqual(copied.read_bytes(), script.read_bytes())
            self.assertFalse((student / 'harness.md').exists())

    def test_optional_existing_restrictions_are_preserved_and_model_is_updated(self):
        script = self.script()
        self.file('ceu-ai.json', json.dumps(ceu.asdict(self.settings)))
        answers = iter(['1', ''])
        with patch.object(ceu, '__file__', str(script)), contextlib.redirect_stdout(io.StringIO()):
            ceu.configure_preferences(self.root, self.client(names=['new-model']), lambda _: next(answers))
        module = self.fresh_module(script)
        settings = module.load_settings(self.root)
        self.assertEqual(settings.model, 'new-model')
        self.assertEqual(settings.context_paths, ['materials'])
        self.assertEqual(settings.output_paths, ['work'])

    def test_instructor_secret_instructions_are_rejected_before_source_changes(self):
        script = self.script()
        original = script.read_bytes()
        answers = iter(['1', 'test-client-secret'])
        with patch.object(ceu, '__file__', str(script)), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ceu.UserError):
            ceu.configure_preferences(self.root, self.client(), lambda _: next(answers))
        self.assertEqual(script.read_bytes(), original)

    def test_concurrent_source_edit_is_preserved(self):
        script = self.script()
        original = script.read_text()
        def ask(question):
            if question == 'Model number: ':
                return '1'
            script.write_text(original + '\n# Instructor edit\n', newline='\n')
            return ''
        with patch.object(ceu, '__file__', str(script)), contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ceu.UserError, 'changed during'):
            ceu.configure_preferences(self.root, self.client(), ask)
        self.assertTrue(script.read_text().endswith('# Instructor edit\n'))

    def test_inline_instructions_and_optional_guide_are_sent_in_chat(self):
        client = self.client([{'message': 'Hello', 'files': []}])
        settings = ceu.Settings(model='example-model', instructions='Use short explanations.')
        workspace = ceu.Workspace(self.root, settings)
        ceu.generate_with_project(client, workspace, 'Hello', set(), [], emit=lambda _: None)
        sent = json.loads(self.requests[-1].data)['messages'][0]['content']
        self.assertIn('Use short explanations.', sent)
        self.assertIn('Help discuss supplied readings.', sent)

    def test_preferences_can_be_reconfigured_and_cleared_without_accumulating_blocks(self):
        script = self.script()
        answers = iter(['1', 'Initial instructions'])
        with patch.object(ceu, '__file__', str(script)), contextlib.redirect_stdout(io.StringIO()):
            ceu.configure_preferences(self.root, self.client(), lambda _: next(answers))
        module = self.fresh_module(script)
        answers = iter(['1', '-'])
        with contextlib.redirect_stdout(io.StringIO()):
            module.configure_preferences(self.root, self.client(), lambda _: next(answers))
        updated = self.fresh_module(script)
        self.assertEqual(updated.load_settings(self.root).instructions, '')
        assignments = [n for n in ast.parse(script.read_text()).body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'SHARED_PREFERENCES' for t in n.targets)]
        self.assertEqual(len(assignments), 1)

    def test_missing_default_model_is_an_error_not_an_unannounced_substitution(self):
        client = self.client(names=['other-model'])
        with self.assertRaisesRegex(ceu.UserError, 'no substitute'):
            client.check_model(ceu.Settings().model)
        self.assertEqual(client.calls, 0)
