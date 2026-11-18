import json,time,unittest
from unittest.mock import patch
import missions as m
import enterprise

class EnterpriseTests(unittest.TestCase):
 def setUp(self):
  from test_supervisor_runtime import SupervisorTests
  self.f=SupervisorTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s;self.pid=self.f.shorts();m.schema(self.s)
 def start(self,**kw):
  return enterprise.configure(self.s,self.pid,dict(enabled=True,**kw))['id']
 def test_switch_starts_one_persistent_local_mission_and_can_pause(self):
  mid=self.start();self.assertEqual(self.start(),mid)
  spec=json.loads(m.definition(self.s,self.pid,mid)['spec']);self.assertTrue(spec['continuous']);self.assertTrue(spec['local_only'])
  self.assertEqual(spec['nodes'][3]['query_from'],'plan');m.tick(self.s)
  self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),1)
  enterprise.configure(self.s,self.pid,dict(enabled=False));m.tick(self.s)
  self.assertEqual(m.definition(self.s,self.pid,mid)['status'],'paused')
 def test_continuous_success_ignores_single_cycle_limit_but_respects_daily_goal(self):
  mid=m.save(self.s,self.pid,dict(name='Continuous',goal='Measure real performance.',spec=dict(nodes=[dict(id='a',kind='evaluate')],continuous=True,daily_cycles=2,max_cycles=1)))
  m.start(self.s,self.pid,mid)
  for _ in range(3):
   self.s.db.execute('UPDATE orbit_missions SET next_run=0');self.s.db.commit();m.tick(self.s)
   while self.s.run_next(('mission_dispatch',)):pass
   m.tick(self.s)
  self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),2);self.assertEqual(m.definition(self.s,self.pid,mid)['status'],'active')
 def test_failed_cycle_schedules_new_plan_with_real_error_and_no_upload_replay(self):
  mid=self.start();m.tick(self.s);r=self.s.rows('SELECT * FROM orbit_mission_runs')[0]
  m._end(self.s,r,'attention','The selected source lacks an actual payoff.')
  saved=m.definition(self.s,self.pid,mid);self.assertEqual(saved['status'],'active');self.assertGreater(saved['next_run'],time.time()+60)
  self.assertIn('payoff',enterprise.planning_context(self.s,saved,self.pid)['previous_cycles'][0]['error'])
  self.assertFalse(self.s.rows("SELECT id FROM jobs WHERE kind='youtube_upload'"))
 def test_plan_is_grounded_structured_file_and_unknown_revenue(self):
  plan=dict(topic='a specific creator recent highlights',audience='English speakers',hypothesis='Test context before the reaction.',revenue_path='Unverified future ad revenue',experiment='Use one coherent event.',success_metric='Compare measured viewing percentage.',steps=['Research sources','Validate story','Measure results'],other_business_ideas=[dict(name='Local editing service',validation='Interview potential clients first')])
  saved=enterprise.save_plan(self.s,self.pid,'run-one',plan)
  from pathlib import Path
  self.assertTrue(Path(saved['path']).is_file());self.assertEqual(saved['profit_status'],'unverified');self.assertEqual(saved['other_business_ideas'][0]['status'],'proposal')
  with self.assertRaises(ValueError):enterprise.save_plan(self.s,self.pid,'run-two',dict(plan,topic='https://youtube.com/watch?v=invented'))
 def test_only_local_follows_a_deferred_production_origin(self):
  from autonomous import plan_schema
  from ai_runtime import local_job
  mid=self.start();m.tick(self.s);rid=self.s.rows('SELECT id FROM orbit_mission_runs')[0]['id'];plan_schema(self.s)
  self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('prod',self.pid,'Actual source',json.dumps(dict(origin='mission:'+rid+':produce')),time.time()))
  aid=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(self.pid,))[0]['id'];jid=self.s.enqueue(aid,'Edit source','graph',payload=dict(run='prod',auto_step='selection'));self.s.db.commit()
  with patch('connections.ROOT',self.s.root):self.assertTrue(local_job(jid))
 def test_local_mission_never_falls_back_to_cloud(self):
  import ai_runtime
  from contextlib import nullcontext
  with patch('ai_runtime.local_job',return_value=True),patch('connections.settings',return_value=dict(mode='hybrid',share_context=True,preferred='groq',providers={})),patch('inference_gate.lease',return_value=nullcontext()),patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',return_value=dict(message=dict(content='{"ok":true}'))),patch('connections.read',return_value={}),patch('connections.atomic'),patch('ai_runtime.record'),patch('ai_runtime.cloud_chat',side_effect=AssertionError('Local-only mission')):
   result=ai_runtime.request('api/chat',dict(model='groq/manual-model',messages=[dict(role='user',content='Return actual evidence')],format='json'),timeout=90)
  self.assertIn('ok',result['message']['content'])
 def test_native_admits_enterprise_controls(self):
  from pathlib import Path
  import re
  base=Path(__file__).parent;swift=(base/'OrbitApp.swift').read_text();allowed=set(re.findall(r'"([a-z_]+)"',swift.split('private let actions: Set<String> = [',1)[1].split(']',1)[0]));calls=set(re.findall(r"call\('([a-z_]+)'",(base/'web/enterprise_ui.js').read_text()))
  self.assertFalse(calls-allowed)
 def test_missing_optional_research_is_disclosed_and_does_not_block_planning(self):
  mid=self.start();m.tick(self.s)
  rid=self.s.rows('SELECT id FROM orbit_mission_runs')[0]['id']
  self.s.db.execute("UPDATE orbit_mission_steps SET state='attention',error='Research quota unavailable' WHERE node='research'")
  self.s.db.execute("UPDATE orbit_mission_steps SET state='done' WHERE node='measure'");self.s.db.commit();m.tick(self.s)
  row=self.s.db.execute("SELECT state,result FROM orbit_mission_steps WHERE run=? AND node='research'",(rid,)).fetchone()
  self.assertEqual(row['state'],'done');self.assertFalse(json.loads(row['result'])['available'])
  m.tick(self.s);self.assertEqual(self.s.db.execute("SELECT state FROM orbit_mission_steps WHERE node='plan'").fetchone()[0],'dispatching')
