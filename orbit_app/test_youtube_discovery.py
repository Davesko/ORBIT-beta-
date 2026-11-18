import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from youtube_discovery import compare,discover,record
from studio import Studio

class DiscoveryTests(unittest.TestCase):
 def candidate(self):return dict(id='new-video',channel_id='channel',age_hours=24,duration=30,views=6000,observed_at=time.time())
 def peers(self):return [dict(id=str(i),channel_id='channel',age_hours=24,duration=30,views=1000) for i in range(12)]
 def test_no_custom_ratio_without_recorded_permission(self):
  self.assertEqual(compare(self.candidate(),self.peers())['status'],'approval_required')
  self.assertIsNone(compare(self.candidate(),self.peers())['ratio'])
 def test_age_format_small_sample_and_zero_baseline_are_not_faked(self):
  v=self.candidate();peers=self.peers()
  self.assertEqual(compare(v,peers,True)['ratio'],6)
  self.assertIsNone(compare(v,peers[:3],True)['ratio'])
  self.assertIsNone(compare(v,[dict(p,age_hours=500) for p in peers],True)['ratio'])
  self.assertIsNone(compare(v,[dict(p,duration=300) for p in peers],True)['ratio'])
  self.assertIsNone(compare(v,[dict(p,views=1) for p in peers],True)['ratio'])
 def test_discovery_is_fresh_bounded_and_raw_counts_are_retained(self):
  from datetime import datetime,timezone
  service=MagicMock();now=time.time();stamp=datetime.fromtimestamp(now-3600,timezone.utc).isoformat()
  service.search.return_value.list.return_value.execute.return_value={'items':[{'id':{'videoId':'abcdefghijk'}}]}
  service.videos.return_value.list.return_value.execute.return_value={'items':[dict(id='abcdefghijk',snippet=dict(title='Togi clip',channelId='channel',publishedAt=stamp),contentDetails=dict(duration='PT30S'),statistics=dict(viewCount='1234'))]}
  service.channels.return_value.list.return_value.execute.return_value={'items':[dict(id='channel',statistics=dict(subscriberCount='10000'))]}
  out=discover(service,dict(queries=['Togi']*5+['Kai','Speed','Fourth']),now)
  self.assertEqual(service.search.return_value.list.call_count,3);self.assertEqual(out['videos'][0]['views'],1234)
  self.assertEqual(out['videos'][0]['format'],'short_form_candidate_not_confirmed_shorts')
 def test_history_is_project_scoped_and_expires(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));self.addCleanup(s.db.close);v=self.candidate()
   result=record(s,'universe',dict(videos=[v]));self.assertFalse(result['advanced_metrics_enabled'])
   s.db.execute('UPDATE youtube_research_observations SET observed=?',(time.time()-31*86400,));s.db.commit()
   record(s,'universe',dict(videos=[]));self.assertEqual(s.db.execute('SELECT count(*) FROM youtube_research_observations').fetchone()[0],0)
 def test_fresh_youtube_handoff_needs_no_fabricated_article_but_expires(self):
  from growth import choose_topic
  from source_policy import persist,resolve
  from test_source_policy import video
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));self.addCleanup(s.db.close)
   v=video();p=s.safe_path('universe','insights/trends.json');p.parent.mkdir()
   p.write_text(json.dumps(dict(collected_at=time.time(),items=[dict(id='research',topic='Minecraft',research_kind='youtube',published_at=time.time(),sample=dict(videos=[v]))])))
   chosen=choose_topic(s,'universe');self.assertEqual(chosen['source_bundle']['mode'],'explicit');self.assertEqual(chosen['source_bundle']['news'],[])
   hid=persist(s,'universe',chosen['source_bundle']);resolve(s,'universe',hid)
   with patch('source_policy.time.time',return_value=time.time()+4*86400):
    with self.assertRaises(ValueError):resolve(s,'universe',hid)

class NaturalVideoIntakeTests(unittest.TestCase):
 def setUp(self):
  from test_supervisor_runtime import SupervisorTests
  self.fixture=SupervisorTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.s=self.fixture.s;self.pid=self.fixture.shorts()
 def test_togi_natural_request_needs_no_model_roundtrip(self):
  from supervisor_runtime import explicit_short_plan
  plan=explicit_short_plan(self.s,'universe','generálj egy videót Togi youtuber best moments témában. kb 50-70 mp legyen.',True)
  self.assertEqual(plan[-1]['query'],'Togi best moments');self.assertEqual(plan[0]['settings']['min_seconds'],50)
  from commander import run,apply
  job=self.fixture.job('generálj egy videót Togi youtuber best moments témában. kb 50-70 mp legyen.')
  with patch('studio.local_api',side_effect=AssertionError('No model planning for this brief')):run(self.s,job)
  turn=self.s.rows('SELECT * FROM command_turns')[0]
  execution=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(turn['job'],)).fetchone())
  with patch('execution_queue.submit_short',return_value=dict(queued=True)) as submit:
   apply(self.s,execution);apply(self.s,execution)
  self.assertEqual(submit.call_count,1)
  self.assertEqual(self.s.rows('SELECT status FROM command_turns')[0]['status'],'done')
 def test_subject_clarification_keeps_prior_duration(self):
  from commander import enqueue
  from supervisor_runtime import explicit_short_plan
  enqueue(self.s,'universe','generálj egy videót Togi youtuber best moments témában. kb 50-70 mp legyen.',global_mode=True)
  self.s.db.execute("UPDATE command_turns SET status='attention'");self.s.db.commit()
  plan=explicit_short_plan(self.s,'universe','Togi youtuber, BEST moments',True)
  self.assertEqual(plan[-1]['query'],'Togi best moments');self.assertEqual(plan[0]['settings']['max_seconds'],70)
 def test_link_brief_with_hungarian_team_imperative_starts_without_model(self):
  from commander import run
  for wording in ('ebből a videóból készítsen a youtube shorts csapat egy viral képes videót.', 'erről a videóról vágj össze egy pörgős shorts videót:'):
   job=self.fixture.job('https://www.youtube.com/watch?v=CIY9PO0IODU\n\n'+wording)
   with patch('studio.local_api',side_effect=AssertionError('Explicit video URL needs no model')):run(self.s,job)
   turn=self.s.db.execute('SELECT actions,status FROM command_turns WHERE id=?',(json.loads(job['payload'])['turn'],)).fetchone()
   self.assertEqual(json.loads(turn['actions'])[-1]['query'],'https://www.youtube.com/watch?v=CIY9PO0IODU')
   self.assertEqual(turn['status'],'queued_apply')
 def test_unrelated_fragment_and_negated_or_explanatory_prompt_do_not_start(self):
  from supervisor_runtime import explicit_short_plan
  for prompt in ('Togi youtuber, BEST moments','Ne generálj egy videót Togi youtuberről.','Miért nem működik a videó Togi youtuberről?','Fejlessz egy appot ami videót generál Togi youtuberről.'):
   self.assertIsNone(explicit_short_plan(self.s,'universe',prompt,True))
 def test_placeholder_is_not_accepted_as_completed_conversation(self):
  from commander import run
  from execution_queue import DeferredExecution
  job=self.fixture.job('Szia, miben tudsz segíteni?')
  response=dict(message=dict(content=json.dumps(dict(reply='Hungarian reply',reads=[],actions=[]))))
  with patch('studio.local_api',return_value=response),patch('model_hub.brief',return_value={}):
   with self.assertRaises(DeferredExecution):run(self.s,job)
  self.assertNotEqual(self.s.rows('SELECT status FROM command_turns')[0]['status'],'done')
 def test_named_resume_targets_saved_stage_instead_of_starting_a_new_video(self):
  from autonomous import plan_schema
  from conversation_intake import resume_plan
  plan_schema(self.s);run='saved-run';self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',(run,self.pid,'Togi funny moments','{}',time.time()))
  aid=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(self.pid,))[0]['id']
  jid=self.s.enqueue(aid,'select','graph',payload=dict(run=run,auto_step='selection'))
  self.s.db.execute("UPDATE jobs SET status='failed' WHERE id=?",(jid,));self.s.db.commit()
  actions=resume_plan(self.s,'universe','Most folytasd a TOGI ról az anyag készítését.',True)
  self.assertEqual(actions[0]['operation'],'production_resume');self.assertEqual(actions[0]['args']['id'],jid)
  self.assertIsNone(resume_plan(self.s,'universe','Ne folytasd a TOGI ról az anyagot.',True))
