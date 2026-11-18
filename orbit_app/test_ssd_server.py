"""14 Nov: Ollama listed no models after a restart because macOS sidecars appeared after it started."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import ssd_server

SIDE = b'\x00\x05\x16\x07' + b'\x00' * 60


class SsdServer(unittest.TestCase):
    def test_manifests_are_found_and_sidecars_do_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            models = Path(d)
            (models / 'manifests-v2/ollama.com/library/gemma4').mkdir(parents=True)
            (models / 'manifests-v2/ollama.com/library/gemma4/._26b').write_bytes(SIDE)
            self.assertFalse(ssd_server.manifests_on_disk(models))
            (models / 'manifests-v2/ollama.com/library/gemma4/26b').write_text('{}')
            self.assertTrue(ssd_server.manifests_on_disk(models))

    def test_an_empty_list_with_models_on_disk_repairs_and_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            models = root / 'ollama'
            (models / 'manifests-v2/ollama.com/library/gemma4').mkdir(parents=True)
            (models / 'manifests-v2/ollama.com/library/gemma4/26b').write_text('{}')
            (models / 'manifests-v2/ollama.com/library/gemma4/._26b').write_bytes(SIDE)
            (root / 'model-storage.json').write_text('{"mount": "%s", "ollama": "%s"}' % (root, models))
            children = []
            def serve(m):
                child = MagicMock();child.poll.return_value = None;children.append(child);return child
            clock = iter(range(0, 10000, 30))
            sleeps = []
            def sleep(seconds):
                sleeps.append(seconds)
                if len(children) >= 2:raise SystemExit
            with patch.object(ssd_server, 'root', root), patch('ssd_server.os.path.ismount', return_value=True), \
                    patch('ssd_server.serve', side_effect=serve), patch('ssd_server.listed', return_value=0), \
                    patch('ssd_server.time.time', side_effect=lambda: next(clock)), patch('ssd_server.time.sleep', side_effect=sleep):
                with self.assertRaises(SystemExit):
                    ssd_server.main()
            self.assertEqual(len(children), 2)                     # restarted once
            children[0].terminate.assert_called_once()
            self.assertFalse((models / 'manifests-v2/ollama.com/library/gemma4/._26b').exists())   # moved to backups
            self.assertTrue(any((root / 'backups').rglob('._26b')))


if __name__ == '__main__':
    unittest.main()
