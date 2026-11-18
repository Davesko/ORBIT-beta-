import json,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import automations as auto
from bridge import dispatch

class AutomationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Studio(Path(self.tmp.name));self.pid='universe';self.a=self.s.rows('SELECT id FROM agents WHERE project=?',(self.pid,))[0]['id'];auto.schema(self.s)
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def spec(self,**kw):return dict(dict(name='Kutatás',kind='agent',config=dict(agent=self.a,prompt='Research the provided topic; save a factual report.'),enabled=False,interval=30,runtime_minutes=15,daily_goal=2),**kw)
 def test_daily_time_is_fixed_to_budapest_including_dst(self):
  import datetime
  from zoneinfo import ZoneInfo
  z=ZoneInfo('Europe/Budapest')
  spec=self.spec(kind='assistant',config=dict(prompt='Review mail.',scope='global',daily_time='08:00'))
  for day in ['2026-11-04','2027-03-27','2027-10-30']:
   now=datetime.datetime.fromisoformat(day+'T09:00').replace(tzinfo=z)
   due=datetime.datetime.fromtimestamp(auto.next_due(now.timestamp(),spec),z)
   self.assertEqual(due.hour,8);self.assertEqual(due.date(),now.date()+datetime.timedelta(days=1))
 def test_global_mail_task_launches_real_local_handler_not_planner(self):
  spec=self.spec(kind='assistant',config=dict(prompt='Review mail.',scope='global',handler='email_review',daily_time='08:00'))
  aid=auto.save(self.s,'universe',spec)
  with patch('commander.enqueue',side_effect=AssertionError('No planner for typed mailbox review')):r=auto.launch(self.s,'universe',aid)
  job=self.s.db.execute('SELECT kind,payload FROM jobs WHERE id=?',(r['jobs'][0],)).fetchone()
  self.assertEqual(job['kind'],'assist');self.assertEqual(json.loads(job['payload'])['task'],'scheduled_email_review')
  self.assertEqual(auto.task_directory(self.s)['automations'][0]['scope'],'global')
 def test_global_task_directory_keeps_project_ownership(self):
  one=auto.save(self.s,self.pid,self.spec());other=self.s.create_project('Másik projekt')
  two=auto.save(self.s,other,self.spec(kind='assistant',config=dict(prompt='Compare the owned projects and write a report.')))
  result=dispatch(dict(action='automation_tasks',project=self.pid),self.s)
  tasks={a['id']:a for a in result['automations']}
  self.assertEqual(tasks[one]['project'],self.pid);self.assertEqual(tasks[two]['project'],other)
  self.assertEqual(tasks[two]['project_name'],'Másik projekt')
 def test_toggle_changes_only_one_schedule_and_preserves_definition_and_work(self):
  one=auto.save(self.s,self.pid,self.spec());two=auto.save(self.s,self.pid,self.spec(name='Másik'))
  run=auto.launch(self.s,self.pid,one)
  original=auto.get(self.s,self.pid,one)
  dispatch(dict(action='automation_toggle',project=self.pid,id=one,enabled=True),self.s)
  self.assertTrue(auto.get(self.s,self.pid,one)['enabled']);self.assertFalse(auto.get(self.s,self.pid,two)['enabled'])
  auto.toggle(self.s,self.pid,one,False)
  self.assertEqual(auto.get(self.s,self.pid,one)['config'],original['config'])
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(run['jobs'][0],)).fetchone()[0],'queued')
  with self.assertRaises(ValueError):auto.toggle(self.s,self.pid,one,'false')
 def test_global_view_does_not_allow_wrong_project_mutations(self):
  aid=auto.save(self.s,self.pid,self.spec());other=self.s.create_project('Másik')
  with self.assertRaises(ValueError):dispatch(dict(action='automation_toggle',project=other,id=aid,enabled=True),self.s)
  with self.assertRaises(ValueError):dispatch(dict(action='automation_run',project=other,id=aid),self.s)
  self.assertFalse(auto.get(self.s,self.pid,aid)['enabled'])
 def test_assistant_reads_tasks_and_can_prepare_project_owned_toggle(self):
  from assistant_context import read_app
  from commander import prepare
  aid=auto.save(self.s,self.pid,self.spec())
  self.assertEqual(read_app(self.s,self.pid,'tasks')['automations'][0]['id'],aid)
  plan=prepare(self.s,self.pid,[dict(type='app_action',project=self.pid,operation='automation_toggle',args=dict(id=aid,enabled=True))],True,user_request='Kapcsold be ezt a feladatot.')
  self.assertEqual(plan[0]['operation'],'automation_toggle')
 def test_independent_schedules_and_project_isolation(self):
  one=auto.save(self.s,self.pid,self.spec());two=auto.save(self.s,self.pid,self.spec(name='Másik'))
  self.assertNotEqual(one,two);other=self.s.create_project('Másik projekt')
  with self.assertRaises(ValueError):auto.get(self.s,other,one)
  self.assertEqual(len(auto.listing(self.s,self.pid)['automations']),2)
 def test_duplicate_start_and_completed_runs(self):
  aid=auto.save(self.s,self.pid,self.spec());run=auto.launch(self.s,self.pid,aid)
  with self.assertRaises(ValueError):auto.launch(self.s,self.pid,aid)
  self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(run['jobs'][0],));self.s.db.commit();auto.reconcile(self.s)
  self.assertEqual(auto.listing(self.s,self.pid)['automations'][0]['runs'][0]['status'],'done')
 def test_runtime_never_stops_working_jobs(self):
  aid=auto.save(self.s,self.pid,self.spec());run=auto.launch(self.s,self.pid,aid);unrelated=self.s.enqueue(self.a,'Unrelated');jid=run['jobs'][0]
  now=time.time()
  self.s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?",(now-7300,jid))
  self.s.db.execute('UPDATE automation_runs SET created=?,deadline=?',(now-7300,now-100))
  self.s.db.execute("INSERT INTO job_log(job,kind,label,details,created) VALUES(?,?,?,?,?)",(jid,'stage','Jelenet 6/6','',now-60));self.s.db.commit()
  auto.reconcile(self.s)
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'running')
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(unrelated,)).fetchone()[0],'queued')
 def test_stuck_or_failed_step_resumes_same_run(self):
  aid=auto.save(self.s,self.pid,self.spec());run=auto.launch(self.s,self.pid,aid);jid=run['jobs'][0]
  self.s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?",(time.time()-auto.STALL-60,jid));self.s.db.commit()
  auto.reconcile(self.s)
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'failed')
  auto.reconcile(self.s)
  row=self.s.db.execute('SELECT status,payload FROM jobs WHERE id=?',(jid,)).fetchone()
  self.assertEqual(row[0],'queued');self.assertEqual(json.loads(row[1])['resumed'],1)
  self.assertEqual(self.s.db.execute('SELECT status FROM automation_runs').fetchone()[0],'running')
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM automation_runs').fetchone()[0],1)
  for _ in range(auto.MAX_RESUMES):
   self.s.db.execute("UPDATE jobs SET status='failed',error='boom' WHERE id=?",(jid,));self.s.db.commit();auto.reconcile(self.s)
  self.assertEqual(self.s.db.execute('SELECT status FROM automation_runs').fetchone()[0],'failed')
 def test_a_step_the_owner_stopped_is_never_resumed(self):
  aid=auto.save(self.s,self.pid,self.spec());run=auto.launch(self.s,self.pid,aid);jid=run['jobs'][0]
  self.s.cancel(jid);auto.reconcile(self.s);auto.reconcile(self.s)
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'cancelled')
  self.assertEqual(self.s.db.execute('SELECT status FROM automation_runs').fetchone()[0],'cancelled')
 def test_pause_does_not_cancel_active_run(self):
  aid=auto.save(self.s,self.pid,self.spec(enabled=True));run=auto.launch(self.s,self.pid,aid);auto.stop(self.s,self.pid,aid)
  self.assertFalse(auto.get(self.s,self.pid,aid)['enabled']);self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(run['jobs'][0],)).fetchone()[0],'queued')
 def test_tick_does_not_duplicate_active_runs(self):
  auto.save(self.s,self.pid,self.spec(enabled=True));auto.tick(self.s);auto.tick(self.s)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM automation_runs').fetchone()[0],1)
 def test_legacy_timer_migrates_once(self):
  self.s.db.execute('UPDATE agents SET interval=30,next_run=? WHERE id=?',(time.time()+500,self.a));self.s.db.commit();auto.migrate(self.s);auto.migrate(self.s)
  self.assertEqual(len(auto.listing(self.s,self.pid)['automations']),1);self.assertEqual(self.s.agent(self.a)['interval'],0)
 def test_recipe_chain_and_foreign_agent_rejected(self):
  ids=[a['id'] for a in self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 2',(self.pid,))];rid=self.s.save_recipe(self.pid,'Lánc',ids,'A real task')
  aid=auto.save(self.s,self.pid,self.spec(kind='recipe',config=dict(recipe=rid,prompt='Run this factual task')));run=auto.launch(self.s,self.pid,aid)
  self.assertEqual(len(run['jobs']),2)
  other=self.s.create_project('Másik');foreign=self.s.rows('SELECT id FROM agents WHERE project=?',(other,))[0]['id']
  with self.assertRaises(ValueError):auto.save(self.s,self.pid,self.spec(config=dict(agent=foreign,prompt='No')))
 def test_graph_steps_are_observable(self):
  ids=[a['id'] for a in self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 2',(self.pid,))];self.s.save_connection(self.pid,dict(source=ids[0],target=ids[1],name='Data',task='Use previous factual data',instructions='Pass actual findings',mode='result'))
  aid=auto.save(self.s,self.pid,self.spec(kind='graph'));auto.launch(self.s,self.pid,aid)
  self.assertEqual(len(auto.listing(self.s,self.pid)['automations'][0]['runs'][0]['steps']),2)
 def test_invalid_window_and_runtime(self):
  with self.assertRaises(ValueError):auto.save(self.s,self.pid,self.spec(runtime_minutes=0))
  with self.assertRaises(ValueError):auto.save(self.s,self.pid,self.spec(plan=dict(from_time='22:00',to_time='08:00')))
 def test_bridge_admission(self):
  r=dispatch(dict(action='automation_save',project=self.pid,automation=self.spec()),self.s);self.assertTrue(r['ok']);self.assertEqual(len(dispatch(dict(action='automation_list',project=self.pid),self.s)['automations']),1)
 def test_global_supervisor_keeps_every_project_and_can_target_another_project(self):
  from commander import planning_overview,prepare,schema
  from assistant_resilience import compact_context,planner_system
  from commander import SYSTEM
  schema(self.s);other=self.s.create_project('MiLLIONS Research');overview=planning_overview(self.s,self.pid,'List projects')
  ids={p['id'] for p in compact_context(dict(overview=overview))['overview']['projects']};self.assertIn(other,ids)
  agent=self.s.rows('SELECT id FROM agents WHERE project=?',(other,))[0]['id']
  action=prepare(self.s,self.pid,[dict(type='agent_run',project=other,agent=agent,prompt='Explain the available research tools without executing a trade.')],global_mode=True)[0]
  self.assertEqual(action['project'],other);self.assertEqual(action['agent'],agent);self.assertIn('workflow_automation_save',planner_system(SYSTEM))
 def test_daily_goal_prevents_another_scheduled_run(self):
  aid=auto.save(self.s,self.pid,self.spec(enabled=True,daily_goal=1));r=auto.launch(self.s,self.pid,aid)
  self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(r['jobs'][0],));self.s.db.commit();auto.tick(self.s)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM automation_runs').fetchone()[0],1)
