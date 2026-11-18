import json,tempfile,time,unittest
from pathlib import Path
from studio import Studio
import missions,venture
class VentureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
 def start(self):return venture.configure(self.s,dict(enabled=True))['id']
 def value(self):return dict(name='Local tool',problem='Specific problem',buyer='Specific buyer',offer='Useful tool',revenue_model='Unverified subscription',costs='Unknown costs',hypothesis='Customers will pay',validation='Measure actual conversion',progress='Built initial prototype',next_action='Test assumptions',decision='continue',evidence=['Demand not yet verified'],files=[dict(name='prototype.py',content='def value():\n return 42\n')])
 def test_global_mission_reuses_state_without_shorts(self):
  mid=self.start();self.assertEqual(mid,self.start());m=venture.status(self.s);self.assertTrue(m['spec']['exploration']);self.assertTrue(m['spec']['local_only']);self.assertEqual([n['kind'] for n in m['spec']['nodes']],['agent','venture','agent'])
 def test_header_is_independent_of_history_and_model_services(self):
  from unittest.mock import patch
  self.assertIsNone(venture.status_head(self.s))
  mid=self.start()
  with patch('venture.history',side_effect=AssertionError('history')),       patch('missions.ssd_waiting',side_effect=AssertionError('network')):
   header=venture.status_head(self.s)
   self.assertEqual((header['id'],header['status']),(mid,'active'))
   self.assertEqual(header['steps'],[])
 def test_stop_resume_keeps_completed_steps_and_direction(self):
  mid=self.start();missions.tick(self.s);rid=self.s.rows('SELECT id FROM orbit_mission_runs')[0]['id']
  self.s.db.execute("UPDATE orbit_mission_steps SET state='done',result=? WHERE node='research'",(json.dumps(dict(content='Actual research')),));self.s.db.commit()
  report=venture.configure(self.s,dict(enabled=False));self.assertIn('summary',report)
  venture.configure(self.s,dict(enabled=True,direction='Explore B2B tools'))
  self.assertEqual(self.s.db.execute("SELECT state FROM orbit_mission_steps WHERE node='research'").fetchone()[0],'done')
  self.assertIn('B2B',missions.definition(self.s,venture.PID,mid)['goal']);self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),1)
 def test_versioned_files_idempotent_and_no_fake_revenue(self):
  self.start();r=venture.save_result(self.s,venture.PID,'cycle-one',self.value());venture.save_result(self.s,venture.PID,'cycle-one',self.value())
  self.assertEqual(len(self.s.rows('SELECT id FROM artifacts')),1);self.assertTrue(Path(r['files'][0]).is_file());self.assertEqual(r['revenue_status'],'unverified')
 def test_paths_and_invalid_code_rejected_before_writes(self):
  self.start()
  for name,content in [('../secret.py','print(1)'),('x.sh','echo bad')]:
   v=self.value();v['files']=[dict(name=name,content=content)]
   with self.assertRaises((ValueError,SyntaxError)):venture.save_result(self.s,venture.PID,'bad',v)
  self.assertFalse((self.s.root/'projects'/venture.PID/'workspace/ventures/bad').exists())
 def test_broken_draft_code_is_kept_and_flagged_not_the_cycle_lost(self):
  self.start();v=self.value();v['files']=[dict(name='bad.py',content='def ('),dict(name='bad.json',content='{"a":')]
  r=venture.save_result(self.s,venture.PID,'broken',v)
  self.assertEqual(len(r['files']),2);self.assertEqual([b.split(':')[0] for b in r['broken_files']],['bad.py','bad.json'])
 def test_too_many_files_keep_the_first_four_instead_of_losing_the_cycle(self):
  self.start();v=self.value();v['files']=[dict(name='f'+str(i)+'.md',content='draft '+str(i)) for i in range(6)]
  r=venture.save_result(self.s,venture.PID,'many',v)
  self.assertEqual([Path(f).name for f in r['files']],['f0.md','f1.md','f2.md','f3.md'])
 def test_exploration_continues_after_daily_count(self):
  mid=self.start();m=missions.definition(self.s,venture.PID,mid)
  for i in range(25):self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',(str(i),mid,i+1,m['spec'],'done',time.time(),time.time()))
  self.s.db.commit();missions.tick(self.s);self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),26)
 def test_scope_routes_use_existing_native_actions(self):
  from pathlib import Path
  js=(Path(__file__).parent/'web/venture_ui.js').read_text();self.assertIn("call('enterprise_save'",js);self.assertIn('businessLabPanel',(Path(__file__).parent/'web/index.html').read_text())
 def test_actual_queue_cycle_saves_artifacts_then_review(self):
  from unittest.mock import patch
  mid=self.start()
  def answer(job):
   p=json.loads(job['payload']);self.assertTrue(p.get('local_only'))
   return json.dumps(self.value()) if p['mission_node']=='build' else 'Evidence is incomplete; test willingness to pay.'
  with patch.object(self.s,'run_agent',side_effect=answer):
   for _ in range(14):
    missions.tick(self.s)
    while self.s.run_next(('mission_dispatch','mission_agent')):pass
  m=venture.status(self.s);self.assertEqual(m['run']['status'],'done')
  self.assertTrue(self.s.rows('SELECT path FROM artifacts'));self.assertIn('Local tool',m['summary'])
  self.assertEqual(m['ideas'][0]['name'],'Local tool');self.assertTrue(m['ideas'][0]['saved'])
  self.assertEqual(m['cycles'][0]['idea']['name'],'Local tool');self.assertIn('Evidence is incomplete',m['cycles'][0]['review'])
 def test_table_shaped_fields_and_gaps_do_not_discard_a_cycle(self):
  self.start();v=self.value();v['costs']=dict(known='hosting 10 EUR',unknowns=['CAC']);v.pop('validation');v['decision']='maybe'
  r=venture.save_result(self.s,venture.PID,'gaps',v)
  self.assertEqual(r['costs'],'known: hosting 10 EUR; unknowns: CAC');self.assertEqual(r['missing_fields'],['validation']);self.assertEqual(r['decision'],'continue')
  v=self.value();v.pop('offer')
  with self.assertRaises(ValueError):venture.save_result(self.s,venture.PID,'nooffer',v)
 def test_printed_tool_call_is_executed_not_returned(self):
  from studio import text_tool_calls
  calls=text_tool_calls('```json\n{"name":"read_file","arguments":{"name":"README.md"}}\n```',['read_file'])
  self.assertEqual(calls[0]['function'],dict(name='read_file',arguments=dict(name='README.md')))
  self.assertEqual(text_tool_calls('{"name":"rm","arguments":{}}',['read_file']),[])
  self.assertEqual(text_tool_calls('{"name":"Idea","offer":"x"}',['read_file']),[])
  self.assertTrue(venture.printed_call('```json\n{\n "name": "web_search",\n "arguments": {"query": "x"}\n}\n```'))
 def test_one_idea_keeps_its_id_across_languages(self):
  self.start()
  a=venture.save_result(self.s,venture.PID,'c1',dict(self.value(),name='AI-Enabled Personalized Nutrition Advice'))
  b=venture.save_result(self.s,venture.PID,'c2',dict(self.value(),name='AI Táplálkozási Terv MVP'))
  c=venture.save_result(self.s,venture.PID,'c3',dict(self.value(),name='Kisvállalkozói marketing asszisztens',idea_id='new'))
  self.assertEqual(a['idea_id'],b['idea_id']);self.assertNotEqual(a['idea_id'],c['idea_id'])
  d=venture.save_result(self.s,venture.PID,'c4',dict(self.value(),name='Teljesen új név',idea_id=c['idea_id']))
  self.assertEqual(d['idea_id'],c['idea_id'])
  known=venture.known_ideas(self.s,venture.PID);self.assertEqual(len(known),2)
  venture.configure(self.s,dict(focus='explore'));self.assertIn('known_ideas',venture.context(self.s,dict(id='x',goal='g'),venture.PID))
 def test_busy_model_lease_waits_instead_of_failing(self):
  import threading
  from inference_gate import lease
  from execution_queue import DeferredExecution
  root=self.s.root;release=threading.Event();held=threading.Event()
  def holder():
   with lease(root):held.set();release.wait(2)
  t=threading.Thread(target=holder);t.start();held.wait(2)
  with self.assertRaises(DeferredExecution):
   with lease(root):pass
  threading.Timer(.3,release.set).start()
  with lease(root,wait=5):pass
  t.join()
 def test_path_named_and_repeated_files_keep_the_latest_draft(self):
  self.start();v=self.value();v['files']=[dict(name='workspace/ventures/abc/README.md',content='old draft'),dict(name='README.md',content='new draft'),'notes.md']
  r=venture.save_result(self.s,venture.PID,'paths',v)
  self.assertEqual([Path(f).name for f in r['files']],['README.md']);self.assertEqual(Path(r['files'][0]).read_text(),'new draft')
  v['files']=[];self.assertEqual(venture.save_result(self.s,venture.PID,'nofiles',v)['files'],[])
 def test_broken_json_plan_is_repaired_in_json_mode(self):
  from unittest.mock import patch
  good=json.dumps(self.value());calls=[]
  def fake(service,route,data,timeout=8):calls.append(data);return {'message':{'content':good}}
  with patch('studio.local_api',side_effect=fake):
   fixed=self.s.repair_json(dict(id='j'),dict(model='auto'),'{"name":"x" "offer":"y"}')
  self.assertEqual(json.loads(fixed)['name'],'Local tool');self.assertEqual(calls[0]['format'],'json')
  self.assertEqual(self.s.repair_json(dict(id='j'),dict(model='auto'),good),good)
if __name__=='__main__':unittest.main()
