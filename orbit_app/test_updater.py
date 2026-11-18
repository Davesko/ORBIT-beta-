import io, json, tempfile, unittest, urllib.error, zipfile
from pathlib import Path
from unittest.mock import patch

import updater
from studio import Studio


def zipball(build, top='ORBIT-beta--main/'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(top + 'install.sh', '#!/bin/bash\necho "✓ Kész."\n')
        z.writestr(top + 'orbit_app/BUILD', build + '\n')
        z.writestr(top + 'orbit_app/web/x.js', 'x')
    return buf.getvalue()


class Updater(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        (self.s.root / 'install.json').write_text(json.dumps(dict(source='o/r', branch='main', build='20261101000000-aaaa111', version='v1.2 beta')))

    def test_new_build_is_reported_without_git_or_login(self):
        with patch.object(updater, 'http_get', return_value=b'20261118190000-bbbb222\n'):
            out = updater.check(self.s)
        self.assertTrue(out['available'])
        self.assertEqual(out['latest'], '20261118190000-bbbb222')
        with patch.object(updater, 'http_get', return_value=b'20261101000000-aaaa111'):
            self.assertFalse(updater.check(self.s)['available'])

    def test_private_repository_asks_for_the_key_once(self):
        err = urllib.error.HTTPError('u', 404, 'nf', {}, None)
        with patch.object(updater, 'http_get', side_effect=err):
            out = updater.check(self.s)
        self.assertFalse(out['available'])
        self.assertTrue(out['needs_key'])
        self.assertIn('frissítési kulcs', out['error'])
        updater.save_token(self.s, 'github_pat_' + 'a' * 30)
        self.assertEqual(updater.headers(self.s)['Authorization'], 'Bearer github_pat_' + 'a' * 30)
        with self.assertRaises(ValueError):
            updater.save_token(self.s, 'rövid kulcs szóközzel')

    def test_apply_unpacks_the_download_and_starts_the_installer_there(self):
        calls = {}
        def fake_get(url, head, timeout=60):
            return b'20261118190000-bbbb222' if 'contents' in url else zipball('20261118190000-bbbb222')
        with patch.object(updater, 'http_get', side_effect=fake_get), patch.object(updater.subprocess, 'Popen', side_effect=lambda *a, **k: calls.setdefault('cmd', a[0])):
            out = updater.apply(self.s)
        self.assertTrue(out['started'])
        folder = self.s.root / 'updates' / '20261118190000-bbbb222'
        self.assertTrue((folder / 'install.sh').is_file())
        self.assertEqual((folder / 'orbit_app/BUILD').read_text().strip(), '20261118190000-bbbb222')
        self.assertIn('install.sh --update', calls['cmd'][2])
        self.assertEqual(calls['cmd'][3], str(folder))

    def test_a_download_that_is_not_an_installer_is_refused(self):
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, 'w') as z:
            z.writestr('x/readme.txt', 'nope')
        def fake_get(url, head, timeout=60):
            return b'20261118190000-bbbb222' if 'contents' in url else bad.getvalue()
        with patch.object(updater, 'http_get', side_effect=fake_get):
            with self.assertRaises(ValueError):
                updater.apply(self.s)

    def test_install_without_source_explains_the_one_time_reinstall(self):
        (self.s.root / 'install.json').write_text('{}')
        out = updater.check(self.s)
        self.assertIn('install.sh', out['error'])


if __name__ == '__main__':
    unittest.main()
