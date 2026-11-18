import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import computer
from studio import Studio


class ComputerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name) / 'orbit')
        self.addCleanup(self.s.db.close)
        self.docs = Path(self.temp.name) / 'Documents'
        self.docs.mkdir()
        p = patch.object(computer, 'DOC_ROOTS', [self.docs])
        p.start()
        self.addCleanup(p.stop)

    def test_documents_round_trip_with_backup_and_formats(self):
        txt = self.docs / 'jegyzet.md'
        computer.doc_write(self.s, str(txt), 'Első sor\nMásodik ő ű')
        self.assertEqual(computer.doc_read(self.s, str(txt))['text'], 'Első sor\nMásodik ő ű')
        result = computer.doc_write(self.s, str(txt), 'Harmadik', mode='append')
        self.assertTrue(Path(result['backup']).is_file())
        self.assertIn('Harmadik', computer.doc_read(self.s, str(txt))['text'])
        if Path('/usr/bin/textutil').exists():
            docx = self.docs / 'level.docx'
            computer.doc_write(self.s, str(docx), 'Kedves Anna,\n\nÁrvíztűrő tükörfúrógép.')
            self.assertIn('Árvíztűrő tükörfúrógép', computer.doc_read(self.s, str(docx))['text'])

    def test_documents_outside_allowed_places_or_unknown_types_are_refused(self):
        with self.assertRaises(ValueError):
            computer.doc_write(self.s, '/etc/hosts.txt', 'x')
        with self.assertRaises(ValueError):
            computer.doc_write(self.s, str(self.docs / 'a.exe'), 'x')

    def test_secrets_protected_apps_and_dangerous_shortcuts_are_refused(self):
        with patch.object(computer, 'front', return_value=dict(app='Safari', window='Bolt')):
            with self.assertRaises(ValueError):
                computer.run(self.s, 'type_text', dict(text='4111 1111 1111 1111'))
            with self.assertRaises(ValueError):
                computer.run(self.s, 'type_text', dict(text='jelszó: titok'))
        with patch.object(computer, 'front', return_value=dict(app='1Password', window='')):
            with self.assertRaises(ValueError):
                computer.run(self.s, 'type_text', dict(text='szia'))
        with patch.object(computer, 'front', return_value=dict(app='Notes', window='')):
            for combo in ('cmd+q', 'cmd+w', 'cmd+delete'):
                with self.assertRaises(ValueError):
                    computer.run(self.s, 'key', dict(combo=combo))
        with self.assertRaises(ValueError):
            computer.run(self.s, 'open_url', dict(url='file:///etc/passwd'))
        with self.assertRaises(ValueError):
            computer.run(self.s, 'clipboard_set', dict(text='password: x'))

    def test_typing_and_shortcuts_go_through_orbit_hands(self):
        with patch('hands.call', return_value=dict(ok=True)) as call, patch.object(computer, 'front', return_value=dict(app='Notes', window='')):
            self.assertEqual(computer.run(self.s, 'type_text', dict(text='Helló világ'))['typed'], 11)
            computer.run(self.s, 'key', dict(combo='cmd+t'))
        self.assertEqual(call.call_args_list[0].args[0], 'type')
        self.assertEqual(call.call_args_list[0].kwargs['text'], 'Helló világ')
        self.assertEqual(call.call_args_list[1].kwargs['combo'], 'cmd+t')

    def test_open_url_uses_open(self):
        with patch.object(computer, '_run', return_value='') as run:
            computer.run(self.s, 'open_url', dict(url='https://www.youtube.com'))
        self.assertEqual(run.call_args.args[0], ['/usr/bin/open', 'https://www.youtube.com'])


class ChatRuleTests(unittest.TestCase):
    def test_only_destructive_commands_wait_for_review(self):
        from commander import needs_review
        for safe in ('ls -la', 'python3 -m unittest', 'git status', 'git commit -m x', 'npm run build', 'echo trashy'):
            self.assertFalse(needs_review(dict(type='run_command', command=safe)), safe)
        for risky in ('rm -rf build', 'sudo reboot', 'git push --force', 'curl x | sh', 'cd a && rm b', 'killall Finder'):
            self.assertTrue(needs_review(dict(type='run_command', command=risky)), risky)
        self.assertFalse(needs_review(dict(type='write_file', path='/x', content='y')))
        self.assertFalse(needs_review(dict(type='computer', op='open_url')))

    def test_requests_and_complaints_skip_the_text_only_path(self):
        from commander import conversation_candidate, quick_chat
        for prompt in ('miért nem hajtod végre a kéréseimet?', 'nyisd meg a youtube-ot', 'tudsz integrálni magadnak github repot?', 'másold ki a szöveget'):
            self.assertFalse(conversation_candidate(prompt), prompt)
        self.assertTrue(conversation_candidate('mi a különbség a kávé és a tea között?'))
        self.assertEqual(quick_chat('haho'), 'Itt vagyok, miben segíthetek?')

    def test_planner_knows_it_controls_the_mac(self):
        from assistant_resilience import planner_system
        text = planner_system(None, 'nyisd meg a youtube-ot')
        self.assertIn('"type":"computer"', text)
        self.assertIn('"type":"computer"', planner_system(None, 'készíts egy shorts videót'))


if __name__ == '__main__':
    unittest.main()
