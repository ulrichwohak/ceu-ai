"""Offline tests for first-run setup, API contracts and course-independent context."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from test_files import ceu


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.file('harness.md', '# Seminar\nHelp discuss supplied readings.\n')
        self.settings = ceu.Settings('Seminar', 'example-model', ['materials'], [], ['work'])
        self.requests = []

    def file(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline="\n")
        return path

    def client(self, replies=(), *, names=None):
        responses = iter(replies)
        def open_request(request, timeout):
            self.requests.append(request)
            if request.full_url.endswith('/models'):
                response = {'data': [{'modelName': n} for n in (names or ['example-model'])]}
            else:
                item = next(responses)
                if isinstance(item, Exception):
                    raise item
                response = {'data': {'content': item if isinstance(item, str) else json.dumps(item),
                                     'usage': {'promptTokens': 100, 'completionTokens': 50}}}
            handle = io.BytesIO(json.dumps(response).encode())
            return handle
        return ceu.CEUClient(ceu.Config('test-client-id', 'test-client-secret'), Mock(open=open_request))

    def workspace(self):
        return ceu.Workspace(self.root, self.settings)

    def generate(self, client, prompt='Create notes.', shared=None, workspace=None):
        return ceu.generate_with_project(client, workspace or self.workspace(), prompt,
                                         set() if shared is None else shared, [], emit=lambda _: None)

    def test_settings_round_trip_and_unknown_fields_fail(self):
        self.file('ceu-ai.json', json.dumps(ceu.asdict(self.settings)))
        self.assertEqual(ceu.load_settings(self.root), self.settings)
        self.file('ceu-ai.json', json.dumps(ceu.asdict(self.settings) | {'secret': 'bad'}))
        with self.assertRaises(ceu.UserError):
            ceu.load_settings(self.root)

    def test_settings_reject_unsafe_scopes_and_invalid_versions(self):
        for name in ('../outside', '.env', 'private', '/tmp', 'foo/../bar', 'foo//bar'):
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                ceu.Settings('Example', 'model', [name]).validate(self.root)
        for version in (True, 2, '1'):
            with self.subTest(version=version), self.assertRaises(ceu.UserError):
                ceu.Settings('Example', 'model', version=version).validate(self.root)

    def test_dataset_must_be_in_approved_context(self):
        self.settings.data_paths = ['outside.csv']
        with self.assertRaises(ceu.UserError):
            self.workspace()

    def test_scopes_hide_unapproved_files_and_block_writes(self):
        self.file('materials/reading.md', 'A reading')
        self.file('unapproved/notes.txt', 'PRIVATE_SENTINEL')
        self.file('materials/.env', 'SECRET_SENTINEL')
        workspace = self.workspace()
        names = workspace.tree()['tree']
        self.assertIn('materials/reading.md', names)
        self.assertNotIn('unapproved/', names)
        self.assertNotIn('materials/.env', names)
        with self.assertRaises(ceu.UserError):
            workspace.read({'unapproved/notes.txt'})
        with self.assertRaises(ceu.UserError):
            workspace.path('materials/reading.md', writing=True)

    def test_read_then_write_uses_real_contents_and_backs_up(self):
        self.file('work/notes.md', 'Original')
        client = self.client([{'message': 'Read', 'files': [], 'read_files': ['work/notes.md']},
                              {'message': 'Revised', 'files': [{'path': 'work/notes.md', 'content': 'Revised'}]}])
        reply, context = self.generate(client, 'Revise work/notes.md')
        self.workspace().apply(reply, context, lambda _: 'yes', emit=lambda _: None)
        self.assertEqual((self.root / 'work/notes.md').read_text(), 'Revised')
        self.assertEqual(next((self.root / '.ceu/backups').rglob('notes.md')).read_text(), 'Original')
        self.assertEqual(client.usage(), (2, 200, 100, 0))

    def test_unread_existing_file_cannot_be_replaced_or_deleted(self):
        self.file('work/notes.md', 'Original')
        self.settings.allow_delete = True
        for reply in ({'message': 'Write', 'files': [{'path': 'work/notes.md', 'content': 'Changed'}]},
                      {'message': 'Delete', 'files': [], 'delete_files': ['work/notes.md']}):
            with self.subTest(reply=reply), self.assertRaises(ceu.UserError):
                self.generate(self.client([reply]))
        self.assertEqual((self.root / 'work/notes.md').read_text(), 'Original')

    def test_crlf_file_snapshot_can_be_revised(self):
        path = self.file('work/notes.md', '')
        path.write_bytes(b'First\r\nSecond\r\n')
        context = self.workspace().read({'work/notes.md'})
        self.assertIn('\r\n', context['work/notes.md'])
        reply = {'message': 'Update', 'files': [{'path': 'work/notes.md', 'content': 'Updated\n'}]}
        self.workspace().apply(reply, context, lambda _: 'y', emit=lambda _: None)
        self.assertEqual(path.read_text(), 'Updated\n')

    def test_disabled_deletion_is_enforced_in_code(self):
        self.file('work/notes.md', 'Original')
        reply = {'message': 'Delete', 'files': [], 'delete_files': ['work/notes.md']}
        with self.assertRaises(ceu.UserError):
            self.workspace().apply(reply, {'work/notes.md': 'Original'}, lambda _: 'y')

    def test_automatic_mode_keeps_backup_without_prompt(self):
        self.settings.write_mode = 'automatic'
        self.file('work/notes.md', 'Original')
        reply = {'message': 'Update', 'files': [{'path': 'work/notes.md', 'content': 'New'}]}
        ask = Mock(side_effect=AssertionError('Unexpected confirmation'))
        self.workspace().apply(reply, {'work/notes.md': 'Original'}, ask, emit=lambda _: None)
        self.assertTrue(list((self.root / '.ceu/backups').rglob('notes.md')))

    def test_metadata_and_program_cannot_be_changed_even_with_root_output(self):
        self.settings.output_paths = ['.']
        for name in ('harness.md', 'ceu-ai.json', 'ceu-ai.py', 'pyproject.toml', 'uv.lock'):
            with self.subTest(name=name), self.assertRaises(ceu.UserError):
                self.workspace().path(name, writing=True)

    def test_csv_catalogue_omits_values_and_requested_preview_is_bounded(self):
        self.file('materials/data.csv', 'label,value\n' + '\n'.join(f'example{i},{i}' for i in range(8)))
        self.settings.data_paths = ['materials/data.csv']
        workspace = self.workspace()
        catalogue = workspace.course_context()['datasets'][0]
        self.assertEqual(catalogue['row_count'], 8)
        self.assertNotIn('example0', json.dumps(catalogue))
        preview = json.loads(workspace.read({'materials/data.csv'})['materials/data.csv'])
        self.assertEqual(len(preview['preview']), 5)

    def test_model_requested_private_or_unapproved_reads_never_send_content(self):
        self.file('unapproved/source.txt', 'NEVER_UPLOAD')
        self.file('materials/credentials.txt', 'NEVER_UPLOAD')
        client = self.client([{'message': 'Read', 'files': [], 'read_files': ['unapproved/source.txt', 'materials/credentials.txt']},
                              {'message': 'Cannot inspect these files.', 'files': []}])
        self.generate(client)
        self.assertNotIn('NEVER_UPLOAD', b''.join(r.data or b'' for r in self.requests).decode())

    def test_saved_credentials_in_context_or_prompt_never_reach_api(self):
        for source in ('prompt', 'file', 'guide'):
            with self.subTest(source=source):
                self.file('harness.md', '# Guide')
                client = self.client()
                shared = set()
                prompt = 'Explain'
                if source == 'prompt':
                    prompt = 'test-client-secret'
                elif source == 'file':
                    self.file('materials/ordinary.md', 'test-client-secret')
                    shared.add('materials/ordinary.md')
                else:
                    self.file('harness.md', 'test-client-secret')
                with self.assertRaises(ceu.UserError):
                    self.generate(client, prompt, shared)
                self.assertEqual(client.calls, 0)

    def test_secret_in_model_reply_cannot_be_displayed_or_saved(self):
        with self.assertRaisesRegex(ceu.UserError, 'credentials'):
            self.generate(self.client([{'message': 'test-client-secret', 'files': []}]))

    def test_one_json_correction_is_counted_and_second_failure_stops(self):
        good = {'message': 'Done', 'files': [{'path': 'work/draft.md', 'content': 'Draft'}]}
        client = self.client(['broken json', good])
        reply, _ = self.generate(client)
        self.assertEqual(reply, good)
        self.assertEqual(client.calls, 2)
        client = self.client(['broken json', 'still broken'])
        with self.assertRaises(ceu.UserError):
            self.generate(client)
        self.assertEqual(client.calls, 2)
        self.assertFalse((self.root / 'work/draft.md').exists())

    def test_source_correction_cannot_expand_destinations(self):
        bad = {'message': 'Bad syntax', 'files': [{'path': 'work/a.py', 'content': 'x = ('}]}
        other = {'message': 'Elsewhere', 'files': [{'path': 'work/b.py', 'content': 'x = 1'}]}
        with self.assertRaisesRegex(ceu.UserError, 'destinations'):
            self.generate(self.client([bad, other]))

    def test_reads_are_bounded_by_four_model_calls(self):
        read = {'message': 'Read', 'files': [], 'read_files': ['materials/missing.txt']}
        client = self.client([read] * 4)
        with self.assertRaisesRegex(ceu.UserError, 'limit'):
            self.generate(client)
        self.assertEqual(client.calls, 4)

    def test_unsupported_tool_or_mixed_action_is_not_retried(self):
        for reply in ({'message': 'Run', 'files': [], 'shell': 'echo example'},
                      {'message': 'Mix', 'files': [{'path': 'work/a.md', 'content': 'a'}], 'read_files': ['materials/a.md']}):
            client = self.client([reply])
            with self.assertRaises(ceu.UserError):
                self.generate(client)
            self.assertEqual(client.calls, 1)

    def test_api_contract_and_model_unavailable_does_not_fallback(self):
        client = self.client([{'message': 'Hello', 'files': []}])
        client.check_model('example-model')
        self.generate(client)
        request = self.requests[-1]
        body = json.loads(request.data)
        self.assertEqual(set(body), {'model', 'messages'})
        self.assertEqual(body['model'], 'example-model')
        self.assertEqual(request.full_url, ceu.API_URL + '/api/v1/llm/chat')
        self.assertEqual(request.get_header('X-client-id'), 'test-client-id')
        self.assertNotIn('test-client-secret', request.data.decode())
        with self.assertRaisesRegex(ceu.UserError, 'substitute'):
            client.check_model('unavailable')
        self.assertEqual(client.calls, 1)

    def test_api_errors_do_not_retry_or_expose_headers(self):
        for error in (HTTPError(ceu.API_URL, 401, 'test-client-secret', {}, None), URLError('test-client-secret')):
            client = self.client([error])
            with self.assertRaises(ceu.UserError) as raised:
                self.generate(client)
            self.assertNotIn('test-client-secret', str(raised.exception))
            self.assertEqual(client.usage(), (1, 0, 0, 1))

    def test_missing_usage_and_truncation_are_reported_honestly(self):
        client = self.client()
        client.request = Mock(return_value={'data': {'content': 'partial', 'finishReason': 'length'}})
        with self.assertRaisesRegex(ceu.UserError, 'cut short'):
            self.generate(client)
        output = []
        client.report_usage(emit=output.append)
        self.assertIn('unavailable for 1', output[0])

    def test_redirects_are_refused(self):
        self.assertIsNone(ceu.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def setup_answers(self, *, approve=''):
        # Title, audience/purpose, rules, context, datasets, outputs, excludes,
        # model, write mode, deletion, final guide review.
        return iter(['History seminar', 'Help students compare arguments.', 'Explain uncertainty.',
                     'materials', '', '', '', '1', '', '', approve])

    def test_first_run_builds_subject_neutral_shared_setup(self):
        self.file('materials/overview.md', 'Reading summaries and discussions.')
        client = self.client([{'guide': '# History seminar\nCompare supplied arguments.\n'}])
        inputs = self.setup_answers()
        with contextlib.redirect_stdout(io.StringIO()):
            settings = ceu.configure_course(self.root, client, lambda _: next(inputs))
        self.assertEqual(settings.title, 'History seminar')
        self.assertEqual(ceu.load_settings(self.root), settings)
        self.assertEqual(client.calls, 1)
        self.assertIn('History', (self.root / 'harness.md').read_text())
        self.assertFalse((self.root / '.ceu/setup.json').exists())
        self.assertNotIn('test-client-secret', (self.root / 'ceu-ai.json').read_text())
        self.assertNotIn('Coding 2', ceu.SETUP_PROMPT + ceu.INSTRUCTIONS)

    def test_paused_setup_resumes_edited_draft_without_another_generation(self):
        self.file('materials/overview.md', 'Overview')
        client = self.client([{'guide': '# Draft\nOriginal'}])
        inputs = self.setup_answers(approve='n')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ceu.UserError):
            ceu.configure_course(self.root, client, lambda _: next(inputs))
        self.file('.ceu/harness-draft.md', '# Edited guide\nMy own instructions.')
        inputs = iter(['', ''])
        with contextlib.redirect_stdout(io.StringIO()):
            ceu.configure_course(self.root, client, lambda _: next(inputs))
        self.assertEqual(client.calls, 1)
        self.assertIn('My own instructions', (self.root / 'harness.md').read_text())

    def test_interrupted_setup_with_no_draft_can_resume(self):
        saved = {'settings': ceu.asdict(self.settings), 'answers': {'purpose': 'A seminar'}}
        self.file('.ceu/setup.json', json.dumps(saved))
        client = self.client([{'guide': '# Resumed\nUse evidence.'}])
        inputs = iter(['', ''])
        with contextlib.redirect_stdout(io.StringIO()):
            ceu.configure_course(self.root, client, lambda _: next(inputs))
        self.assertEqual(client.calls, 1)

    def test_setup_preserves_editor_changes_made_while_awaiting_model(self):
        self.file('materials/overview.md', 'Overview')
        client = self.client([{'guide': '# Draft'}])
        complete = client.complete
        def concurrent(*args):
            answer = complete(*args)
            self.file('harness.md', 'New manual edit')
            return answer
        client.complete = concurrent
        inputs = self.setup_answers()
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ceu.UserError, 'changed during'):
            ceu.configure_course(self.root, client, lambda _: next(inputs))
        self.assertEqual((self.root / 'harness.md').read_text(), 'New manual edit')

    def test_guide_generation_cannot_write_arbitrary_files(self):
        client = self.client([{'guide': '# Guide', 'files': [{'path': 'bad', 'content': 'bad'}]}] * 2)
        with self.assertRaises(ceu.UserError):
            ceu.draft_guide(client, self.workspace(), {})
        self.assertFalse((self.root / 'bad').exists())

    def test_guide_draft_size_and_control_characters_are_rejected(self):
        for value in ('', 'x' * ceu.MAX_HARNESS_BYTES, '\x1b[2Jhidden'):
            with self.subTest(value=value[:10]), self.assertRaises(ceu.UserError):
                ceu.validate_guide(value)

    def test_credential_setup_and_import_never_embed_credentials_in_course_files(self):
        source = self.file('download [1].json', json.dumps({'client_id': 'test-client-id', 'secret': 'test-client-secret'}))
        client = self.client()
        with contextlib.redirect_stdout(io.StringIO()):
            actual = ceu.credentials_for(self.root, Mock(side_effect=AssertionError()), Mock(side_effect=AssertionError()),
                                         import_path=source, client_factory=lambda _: client)
        self.assertIs(actual, client)
        self.assertEqual(ceu.load_config(self.root / '.ceu/config.json'), client.config)
        ignore = (self.root / '.gitignore').read_text()
        self.assertIn('/download\\ \\[1\\].json', ignore)
        self.assertNotIn('test-client-secret', ignore)

    def test_failed_credential_check_does_not_replace_existing_credentials(self):
        original = ceu.Config('old-id', 'old-secret')
        ceu.save_config(original, self.root / '.ceu/config.json')
        client = self.client()
        client.models = Mock(side_effect=ceu.UserError('Rejected'))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ceu.UserError):
            ceu.credentials_for(self.root, lambda _: 'new-id', lambda _: 'new-secret', force=True,
                                 client_factory=lambda _: client)
        self.assertEqual(ceu.load_config(self.root / '.ceu/config.json'), original)

    def test_gitignore_setup_is_idempotent_and_overrides_old_negations(self):
        self.file('.gitignore', 'custom/\n.ceu/\n!.ceu/\n')
        ceu.ensure_gitignore(self.root)
        first = (self.root / '.gitignore').read_text()
        ceu.ensure_gitignore(self.root)
        self.assertEqual((self.root / '.gitignore').read_text(), first)
        self.assertGreater(first.rfind('.ceu/'), first.index('!.ceu/'))
        self.assertTrue(first.startswith('custom/'))

    def test_existing_student_setup_skips_instructor_wizard(self):
        self.file('ceu-ai.json', json.dumps(ceu.asdict(self.settings)))
        client = self.client()
        session = Mock(prompt=Mock(return_value='/quit'))
        with patch.object(ceu, '__file__', str(self.root / 'ceu-ai.py')), \
             patch.object(ceu.Path, 'cwd', return_value=self.root), \
             patch.object(ceu.sys, 'argv', ['ceu-ai.py']), \
             patch.object(ceu.sys.stdin, 'isatty', return_value=True), \
             patch('prompt_toolkit.PromptSession', return_value=session), \
             patch.object(ceu, 'credentials_for', return_value=client), \
             patch.object(ceu, 'configure_course') as wizard, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ceu.main(), 0)
            wizard.assert_not_called()
        self.assertEqual(client.calls, 0)

    def test_context_and_tree_previews_make_no_chat_calls(self):
        commands = iter(['/context', '/tree', '/quit'])
        client = self.client()
        with contextlib.redirect_stdout(io.StringIO()):
            ceu.run_chat(client, self.workspace(), lambda _: next(commands))
        self.assertEqual(client.calls, 0)

    def test_exclusions_survive_new_and_shared_files_are_cleared(self):
        self.file('materials/a.md', 'A')
        commands = iter(['/add materials/a.md', '/drop materials', '/new', '/quit'])
        workspace = self.workspace()
        with contextlib.redirect_stdout(io.StringIO()):
            ceu.run_chat(self.client(), workspace, lambda _: next(commands))
        with self.assertRaises(ceu.UserError):
            workspace.read({'materials/a.md'})

    def test_new_generated_files_become_followup_context(self):
        client = self.client([{'message': 'Ready', 'files': [{'path': 'work/notes.md', 'content': 'My draft'}]},
                              {'message': 'Explained', 'files': []}])
        commands = iter(['Create notes.', 'Explain the notes.', '/quit'])
        with contextlib.redirect_stdout(io.StringIO()):
            ceu.run_chat(client, self.workspace(), lambda _: next(commands))
        second = json.loads(self.requests[-1].data)['messages'][0]['content']
        self.assertIn('My draft', second)

    def test_help_and_version_work_without_credentials_or_terminal(self):
        for option in ('--help', '--version'):
            result = subprocess.run([sys.executable, str(Path(ceu.__file__)), option], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_python_notebook_is_not_misrepresented_as_validated_python(self):
        nb = {'cells': [], 'metadata': {'kernelspec': {'name': 'ir', 'display_name': 'R', 'language': 'R'}},
              'nbformat': 4, 'nbformat_minor': 5}
        with self.assertRaisesRegex(ceu.InvalidSourceError, 'Python notebooks'):
            ceu.validate_source('work/example.ipynb', json.dumps(nb))

    def test_student_without_course_files_does_not_request_credentials(self):
        session = Mock(prompt=Mock(return_value='2'))
        output = io.StringIO()
        with patch.object(ceu, '__file__', str(self.root / 'ceu-ai.py')), \
             patch.object(ceu.Path, 'cwd', return_value=self.root), \
             patch.object(ceu.sys, 'argv', ['ceu-ai.py']), \
             patch.object(ceu.sys.stdin, 'isatty', return_value=True), \
             patch('prompt_toolkit.PromptSession', return_value=session), \
             patch.object(ceu, 'credentials_for') as credentials, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(output):
            self.assertEqual(ceu.main(), 1)
            credentials.assert_not_called()
        self.assertIn('Get harness.md and ceu-ai.json', output.getvalue())

    def test_declined_changes_are_not_claimed_as_saved_in_chat_history(self):
        self.file('work/notes.md', 'Original')
        client = self.client([{'message': 'Saved successfully', 'files': [{'path': 'work/notes.md', 'content': 'Replacement'}]},
                              {'message': 'Explained', 'files': []}])
        commands = iter(['/add work/notes.md', 'Revise the notes', 'n', 'What happened?', '/quit'])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ceu.run_chat(client, self.workspace(), lambda _: next(commands))
        self.assertEqual((self.root / 'work/notes.md').read_text(), 'Original')
        self.assertNotIn('Saved successfully', output.getvalue())
        sent = json.loads(self.requests[-1].data)['messages'][0]['content']
        self.assertNotIn('Saved successfully', sent)
        self.assertIn('No files changed.', sent)

    def test_secret_input_refuses_visible_terminal_fallback(self):
        import warnings
        def visible_fallback(_):
            warnings.warn('Cannot hide input', ceu.getpass.GetPassWarning)
            raise AssertionError('Must stop before visible input')
        with patch.object(ceu.getpass, 'getpass', side_effect=visible_fallback), \
             self.assertRaisesRegex(ceu.UserError, 'cannot hide'):
            ceu.read_secret('Secret: ')

    def test_combined_context_limit_blocks_network_request(self):
        client = self.client()
        with self.assertRaisesRegex(ceu.UserError, 'too large'):
            client.complete('example-model', ceu.INSTRUCTIONS, {'request': 'x' * ceu.MAX_CONTEXT})
        self.assertEqual(self.requests, [])

    def test_published_setup_prompt_is_the_prompt_used_in_app(self):
        document = (Path(ceu.__file__).parent / 'SETUP_PROMPT.md').read_text(encoding='utf-8')
        self.assertEqual(document.split('```text\n', 1)[1].rsplit('```', 1)[0], ceu.SETUP_PROMPT)

    def test_documented_protocol_examples_parse_and_validate(self):
        for line in ceu.INSTRUCTIONS.splitlines():
            if line.startswith('{'):
                reply = ceu.parse_reply(line)
                for item in reply['files']:
                    ceu.validate_source(item['path'], item['content'])


if __name__ == '__main__':
    unittest.main()
