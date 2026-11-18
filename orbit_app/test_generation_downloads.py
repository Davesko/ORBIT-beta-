import errno
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generation_downloads as media
from studio import Studio


class MediaDownloadTests(unittest.TestCase):
    def test_unwritable_model_folder_reports_permissions_before_queueing(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Studio(Path(directory))
            self.addCleanup(s.db.close)
            # The real disk must not decide this test: with under 9 GB free it reported "no space" instead (10 Nov).
            room = patch('generation_downloads.shutil.disk_usage', return_value=type('U', (), dict(free=10**13))())
            with room, patch('model_hub.config', return_value={}), patch('generation_downloads.tempfile.TemporaryFile',
                   side_effect=PermissionError(errno.EPERM, 'Operation not permitted')):
                with self.assertRaisesRegex(ValueError, 'Fájlok és mappák'):
                    media.enqueue(s, 'wan21', foreground=True)
            self.assertFalse(s.claim(('model_pull',)))

    def test_verified_download_and_registration(self):
        raw = b'example model weights'
        pack = ('Example', 'Képgenerálás', 'publisher/repo', 'rev',
                (('model.safetensors', 'checkpoints/model.safetensors', len(raw), hashlib.sha256(raw).hexdigest()),))
        with tempfile.TemporaryDirectory() as directory:
            s = Studio(Path(directory))
            self.addCleanup(s.db.close)
            target = s.root/'models'/'comfy-models'
            with patch.dict(media.PACKS, {'sample': pack}), patch('model_hub.config', return_value={}), \
                 patch('connections.under_test', return_value=False), \
                 patch('urllib.request.OpenerDirector.open', side_effect=[io.BytesIO(b'bad'),io.BytesIO(raw)]):
                job = media.enqueue(s,'sample')
                with self.assertRaisesRegex(ValueError,'ellenőrzőösszege'):
                    media.download(s,dict(id=job['job']),'sample')
                self.assertFalse((target/'.orbit-sample').exists())
                self.assertFalse((target/'checkpoints/model.part').exists())
                self.assertIn('letöltve',media.download(s,dict(id=job['job']),'sample'))
                self.assertEqual((target/'checkpoints/model.safetensors').read_bytes(),raw)
                self.assertTrue(next(x for x in media.catalog(s) if x['id']=='sample')['ready'])
                (target/'checkpoints/model.safetensors').unlink()
                self.assertFalse(next(x for x in media.catalog(s) if x['id']=='sample')['ready'])
                s.cancel(job['job'])
                retry=media.enqueue(s,'sample',foreground=True)
                self.assertFalse(s.claim(('model_pull',)))
                self.assertEqual(s.db.execute('SELECT status FROM jobs WHERE id=?',(retry['job'],)).fetchone()[0],'running')
