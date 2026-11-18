import tempfile,time,json,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from short_recovery import recover,SourceEvidenceError
from autonomous import save_settings,daily_progress,schedule,plan_schema
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name)/'orbit');self.addCleanup(self.s.db.close);plan_schema(self.s)
  self.a=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','real topic',json.dumps(dict(automatic=True)),time.time()));self.s.db.commit()
 def job(self,kind='graph',step='selection'):
  jid=self.s.enqueue(self.a,'test',kind,payload=dict(run='run',auto_step=step));return self.s.claim((kind,))
 def test_retry_waits_and_is_bounded(self):
  j=self.job(step='render');self.assertTrue(recover(self.s,j,'temporary'))
  self.assertIsNone(self.s.claim(('graph',)))
  for i in range(2):
   self.s.db.execute("UPDATE jobs SET payload=json_set(payload,'$.retry_at',0) WHERE id=?",(j['id'],));self.s.db.commit();j=self.s.claim(('graph',));answer=recover(self.s,j,'temporary')
  self.assertFalse(answer)
 def test_upload_is_never_blindly_retried(self):
  j=self.job(kind='youtube_upload');self.assertFalse(recover(self.s,j,'unknown upload outcome'))
 def test_director_conflict_replans_once_without_redownloading_or_faking_approval(self):
  data=dict(tracks=[dict(transcript_file='real.json')],sources=[dict(source_video='real.mp4')],director=dict(event_id=0,catalog_key='actual-evidence'),selection_checkpoint=dict(choice='old'))
  self.s.db.execute('UPDATE short_runs SET data=?',(json.dumps(data),));self.s.db.commit()
  j=self.job();p=json.loads(j['payload']);p['recovery_attempt']=2;j['payload']=json.dumps(p)
  self.assertTrue(recover(self.s,j,'A kiválasztásból kimaradt a történet tényleges csúcspontja.'))
  saved=json.loads(self.s.db.execute('SELECT data FROM short_runs').fetchone()[0])
  self.assertEqual(saved['tracks'],data['tracks']);self.assertEqual(saved['sources'],data['sources']);self.assertNotIn('director',saved);self.assertNotIn('montage',saved)
  self.assertFalse(recover(self.s,j,'A kiválasztásból kimaradt a történet tényleges csúcspontja.'))
 def test_selection_refreshes_sources_once_after_retries(self):
  j=self.job();p=json.loads(j['payload']);p['recovery_attempt']=2;j['payload']=json.dumps(p)
  self.assertTrue(recover(self.s,j,SourceEvidenceError('not enough context')))
  d=json.loads(self.s.db.execute('SELECT data FROM short_runs').fetchone()[0]);self.assertEqual(d['source_refreshes'],1)
  self.assertFalse(recover(self.s,j,SourceEvidenceError('still insufficient')))
 def test_goal_counts_success_not_failed_attempts(self):
  self.assertEqual(daily_progress(self.s,'universe'),dict(completed=0,attempts=1))
  self.s.db.execute('UPDATE short_runs SET data=?',(json.dumps(dict(automatic=True,complete=True,style=dict(publish_to_youtube=False))),));self.s.db.commit()
  self.assertEqual(daily_progress(self.s,'universe')['completed'],1)
  self.s.db.execute('UPDATE short_runs SET data=?',(json.dumps(dict(automatic=True,complete=True,style=dict(publish_to_youtube=True,review_before_upload=False))),));self.s.db.commit()
  self.assertEqual(daily_progress(self.s,'universe')['completed'],0)
 def test_daily_goal_starts_after_failed_attempt_and_honors_budget(self):
  with patch('autonomous.role_agents',return_value={}):save_settings(self.s,'universe','topic',True,daily_limit=1,daily_goal=1)
  with patch('autonomous.start') as start:schedule(self.s);start.assert_called_once()

 def test_editorial_rejection_keeps_verified_sources_and_does_not_restart_pipeline(self):
  data=dict(sources=[{'source_video':'real.mp4'}],tracks=[{'transcript_file':'real.json'}],visual_analysis=[{'frames':[]}],selection_checkpoint={'mode':'candidates'})
  self.s.db.execute('UPDATE short_runs SET data=?',(json.dumps(data),));self.s.db.commit()
  j=self.job();p=json.loads(j['payload']);p['recovery_attempt']=2;j['payload']=json.dumps(p)
  for reason in ('Selected scenes overlap','Invalid JSON','Szerkesztői javítás szükséges','Nincs elérhető helyi beszélgetőmodell'):
   self.assertFalse(recover(self.s,j,reason))
   self.assertEqual(json.loads(self.s.db.execute('SELECT data FROM short_runs').fetchone()[0]),data)
