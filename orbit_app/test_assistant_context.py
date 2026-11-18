import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from commander import schema,enqueue,run,prepare
from assistant_context import snapshot,metric_question,read_app,publish
from execution_queue import DeferredExecution

class LiveAssistantTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def measurement(self,pid='universe',views=788,age=0):
  p=self.s.root/'integrations/youtube'/pid;p.mkdir(parents=True,exist_ok=True)
  (p/'status.json').write_text(json.dumps(dict(connected=True,channel='Real channel',channel_id='channel-1')))
  (p/'feedback.json').write_text(json.dumps(dict(collected_at=time.time()-age,channel=dict(id='channel-1',title='Real channel',views=views),videos=[dict(id='abcdefghijk',views=views-1)],analytics_status='available')))
 def job(self,prompt):
  jid=enqueue(self.s,'universe',prompt,'auto',global_mode=True);return dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
 def test_plain_question_is_a_measured_read_not_a_generation(self):
  self.measurement();j=self.job('Mennyien nézték meg a videóimat?')
  with patch('studio.local_api',side_effect=AssertionError('Counts never need an LLM')):answer=run(self.s,j)
  self.assertIn('788',answer);self.assertIn('Budapest',answer);self.assertIn('nem az egyedi',answer)
  row=self.s.db.execute('SELECT status,actions FROM command_turns WHERE job=?',(j['id'],)).fetchone();self.assertEqual(row['status'],'done');self.assertEqual(json.loads(row['actions']),[])
  self.assertFalse(self.s.db.execute("SELECT 1 FROM jobs WHERE kind IN ('graph','youtube_upload')").fetchone())
 def test_stale_metrics_refresh_then_answer_without_replaying_effects(self):
  self.measurement(age=1000);j=self.job('Mennyi megtekintés van a videóimon?')
  with self.assertRaises(DeferredExecution):run(self.s,j)
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='growth_metrics'").fetchone()[0],1)
  self.measurement(views=999);self.s.db.execute("UPDATE jobs SET status='done' WHERE kind='growth_metrics'");self.s.db.commit()
  self.assertIn('999',run(self.s,j));self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='growth_metrics'").fetchone()[0],1)
 def test_dynamic_app_state_changes_between_slices_and_hides_credentials(self):
  self.measurement();one=snapshot(self.s);self.s.create_project('New app','Real new project','general','new-app');two=snapshot(self.s)
  self.assertNotIn('new-app',[p['id'] for p in one['projects']]);self.assertIn('new-app',[p['id'] for p in two['projects']])
  folder=self.s.root/'connections';folder.mkdir();(folder/'private.json').write_text('{"secret":"NEVER_IN_CONTEXT"}')
  self.assertNotIn('NEVER_IN_CONTEXT',json.dumps(snapshot(self.s)));publish(self.s);self.assertTrue((self.s.root/'assistant-live-context.json').exists())
 def test_model_receives_fresh_snapshot_on_resumed_planning(self):
  from supervisor_runtime import load
  j=self.job('Nézd meg a projekteket, és válaszolj röviden.')
  first=dict(message=dict(content=json.dumps(dict(reply='Reading',reads=[dict(app='metrics',project='universe')],actions=[]))))
  with patch('studio.local_api',return_value=first):
   with self.assertRaises(DeferredExecution):run(self.s,j)
  self.s.create_project('Latest app','New','general','latest')
  second=dict(message=dict(content=json.dumps(dict(reply='Ellenőriztem.',reads=[],actions=[]))))
  with patch('studio.local_api',return_value=second) as model:run(self.s,j)
  messages=model.call_args.args[2]['messages'];fresh=[m for m in messages if m.get('content','').startswith('CURRENT APP STATE')]
  self.assertEqual(len(fresh),1);self.assertIn('latest',fresh[0]['content']);self.assertIn('publication_approve',fresh[0]['content'])
 def test_app_reads_are_project_scoped(self):
  self.measurement();self.s.create_project('Other','Other','general','other')
  self.assertNotIn('channel',read_app(self.s,'other','metrics')['measurements'])
  self.assertEqual(read_app(self.s,'universe','metrics')['measurements']['channel']['views'],788)
 def test_specific_periods_platforms_and_implementation_requests_are_not_total_views(self):
  self.assertTrue(metric_question('Mennyien nézték meg a videóimat?'))
  for text in ['Mennyien nézték meg a videóimat ma?','Mennyi az Instagram videóim nézettsége?','Fejleszd le, hogy megmondja mennyien nézték meg a videóimat.','Hányan nézték meg a legutóbbi videót?']:
   self.assertFalse(metric_question(text))
 def test_read_question_cannot_approve_a_public_upload(self):
  with self.assertRaises(ValueError):prepare(self.s,'universe',[dict(type='app_action',operation='publication_approve',args=dict(id='artifact'))],user_request='Mennyi a nézettség?')

class CounterConsistencyTests(unittest.TestCase):
 def test_delayed_channel_counter_cannot_hide_known_video_views(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));schema(s);p=s.root/'integrations/youtube/universe';p.mkdir(parents=True)
   (p/'status.json').write_text(json.dumps(dict(connected=True,channel='Real channel')))
   (p/'feedback.json').write_text(json.dumps(dict(collected_at=time.time(),channel=dict(id='channel',title='Real channel',views=0),videos=[dict(views=787),dict(views=1)])))
   jid=enqueue(s,'universe','Mennyien nézték meg a videóimat?','auto',global_mode=True);j=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
   answer=run(s,j);self.assertIn('788',answer);self.assertNotIn('**0 megtekintés**',answer);self.assertIn('videónkénti',answer);s.db.close()
