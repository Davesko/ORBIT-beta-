import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from clip_farm import configure,PROJECT
from autonomous import start
from short_recovery import resume
class ResumeTests(unittest.TestCase):
 def test_resume_reuses_completed_inputs_and_does_not_duplicate_work(self):
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close);configure(s);run=start(s,PROJECT,'A real topic')
   source=s.safe_path(PROJECT,'sources/saved.mp4');source.parent.mkdir(parents=True);source.write_bytes(b'fixture source')
   transcript=s.safe_path(PROJECT,'sources/saved.json');transcript.write_text('{"segments":[]}')
   data=json.loads(s.db.execute('SELECT data FROM short_runs WHERE id=?',(run['run'],)).fetchone()[0]);data['tracks']=[dict(source=dict(source_video='sources/saved.mp4'),transcript_file='sources/saved.json')]
   s.db.execute('UPDATE short_runs SET data=? WHERE id=?',(json.dumps(data),run['run']))
   for stage,jid in run['jobs'].items():s.db.execute('UPDATE jobs SET status=? WHERE id=?',('done' if stage in ('producer','source','transcript') else 'failed' if stage=='selection' else 'blocked',jid))
   s.db.commit();result=resume(s,PROJECT,run['jobs']['selection']);self.assertEqual(len(result['jobs']),5)
   self.assertTrue(resume(s,PROJECT,run['jobs']['selection'])['existing'])
   self.assertEqual(s.db.execute('SELECT status FROM jobs WHERE id=?',(run['jobs']['source'],)).fetchone()[0],'done')
   self.assertEqual(s.db.execute('SELECT count(*) FROM jobs WHERE project=?',(PROJECT,)).fetchone()[0],8)
   with self.assertRaises(ValueError):resume(s,PROJECT,run['jobs']['render'])
   with self.assertRaises(ValueError):resume(s,'universe',run['jobs']['selection'])
