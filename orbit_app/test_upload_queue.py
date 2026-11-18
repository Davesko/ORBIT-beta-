import unittest,tempfile,json,sys,time
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from youtube import queue_upload,validate_short
class UploadQueueTests(unittest.TestCase):
 def test_rejects_landscape_long_and_stale_render(self):
  with tempfile.TemporaryDirectory() as folder:
   file=Path(folder)/'clip.mp4';file.write_bytes(b'fixture')
   for width,height,duration,size in [(1920,1080,40,7),(1080,1920,181,7),(1080,1920,40,99)]:
    file.with_suffix('.json').write_text(json.dumps(dict(width=width,height=height,duration=duration,bytes=size)))
    with self.assertRaises(ValueError):validate_short(file)
 def test_public_payload_and_duplicate_protection(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder)/'orbit')
   file=s.safe_path('universe','renders/verified.mp4');file.parent.mkdir(exist_ok=True);file.write_bytes(b'verified test fixture')
   file.with_suffix('.json').write_text(json.dumps(dict(width=1080,height=1920,duration=40,bytes=file.stat().st_size)))
   s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('artifact','universe','verified.mp4',str(file),'video',time.time(),'source-job'));s.db.commit()
   with patch('youtube.read_state',return_value={'connected':True}):
    first=queue_upload(s,'universe','artifact','Real title',privacy='public',run_id='run')
    again=queue_upload(s,'universe','artifact','Real title',privacy='public',run_id='run')
   self.assertEqual(first['job'],again['job']);self.assertTrue(again['existing'])
   payload=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(first['job'],)).fetchone()[0]);self.assertEqual(payload['privacy'],'public');self.assertEqual(payload['run'],'run')
   s.db.close()
