import unittest,tempfile,time,json
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from autonomous import run_step
from short_style import DEFAULT
class ScoutRepairTests(unittest.TestCase):
 def test_editor_receives_short_proposal_before_length_rejection(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder)/'orbit')
   transcript=dict(segments=[dict(start=0,end=6,text='This is the setup.'),dict(start=6,end=12,text='This is the actual payoff!')])
   path=s.safe_path('universe','real-transcript.json');path.write_text(json.dumps(transcript))
   source=dict(source_video='real-source.mp4',duration=12)
   data=dict(style=dict(DEFAULT,visual_analysis=False),source=source,transcript='real-transcript.json',subtitle='real.srt',tracks=[dict(source=source,transcript_file='real-transcript.json',subtitle='real.srt')])
   s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','same topic',json.dumps(data),time.time()));s.db.commit()
   a=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];jid=s.enqueue(a,'edit','graph',payload=dict(run='run',auto_step='selection'));job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
   choice=dict(hook=0,sequence=[1],context='setup',payoff='payoff',caption_theme='clean')
   review=dict(approved=True,hook_candidates=[dict(id=0,reason='Real setup')],plan=choice,beats=[dict(id=1,beat='payoff',sound='none')])
   with patch('semantic_boundaries.enrich'),patch('story_director.direct',side_effect=lambda s,j,d,c,a:d.setdefault('director',{})),patch('source_quality.annotate',side_effect=lambda s,j,t,d:d.setdefault('source_quality',{})),patch('autonomous.ask_json',side_effect=[choice,review]) as model:run_step(s,job)
   self.assertEqual(model.call_count,2)
   saved=json.loads(s.db.execute('SELECT data FROM short_runs').fetchone()[0]);self.assertEqual(saved['montage']['duration'],12);self.assertEqual(saved['style']['min_seconds'],12);self.assertTrue(saved['montage']['editorial_review']['approved']);s.db.close()
