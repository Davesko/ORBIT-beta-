import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import missions as m

class MissionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);m.schema(self.s)
  self.a=self.s.rows("SELECT id FROM agents WHERE project='universe' ORDER BY rowid")[0]['id']
 def goal(self,nodes=None,**opts):
  return dict(name='ORBIT tesztcél',goal='Analyze actual project results. Do not publish, transfer funds or trade.',spec=dict(nodes=nodes or [dict(id='review',kind='evaluate')],**opts))
 def launch(self,nodes=None,**opts):
  mid=m.save(self.s,'universe',self.goal(nodes,**opts));m.start(self.s,'universe',mid);m.tick(self.s);return mid
 def dispatch_all(self):
  while self.s.run_next(('mission_dispatch',)):pass
 def steps(self):return self.s.rows('SELECT * FROM orbit_mission_steps ORDER BY rowid')
 def test_cycles_rejected_before_queue_effects(self):
  with self.assertRaisesRegex(ValueError,'Körkörös'):m.save(self.s,'universe',self.goal([dict(id='a',kind='evaluate',after=['b']),dict(id='b',kind='evaluate',after=['a'])]))
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
 def test_live_financial_effects_not_a_capability(self):
  for kind in ('trade','copy_trade','transfer','run_command'):
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.save(self.s,'universe',self.goal([dict(id='a',kind=kind)]))
 def test_nonfinite_and_unbounded_settings_rejected(self):
  for opts in (dict(max_cycles=0),dict(max_attempts=99),dict(interval_minutes=float('inf')),dict(daily_cycles=True)):
   with self.subTest(opts=opts),self.assertRaises(ValueError):m.save(self.s,'universe',self.goal(**opts))
 def test_draft_is_not_started_by_saving(self):
  m.save(self.s,'universe',self.goal());m.tick(self.s)
  self.assertFalse(self.steps());self.assertFalse(self.s.rows('SELECT id FROM jobs'))
  self.assertEqual(m.listing(self.s)['missions'][0]['steps'][0]['state'],'planned')
 def test_local_mission_waits_while_the_model_ssd_hangs(self):
  # 2026-11-01: with the model SSD hung, cycle 205 ended in "attention" instead of waiting.
  nodes=[dict(id='a',kind='agent',agent=self.a,prompt='Inspect actual project state.')]
  mid=m.save(self.s,'universe',self.goal(nodes,local_only=True,run_minutes=5));m.start(self.s,'universe',mid)
  with patch('missions.ssd_waiting',return_value=True):m.tick(self.s);m.tick(self.s)
  step=self.steps()[0];run=self.s.rows('SELECT status,deadline FROM orbit_mission_runs')[0]
  self.assertEqual(step['state'],'pending');self.assertEqual(json.loads(step['result'])['waiting_reason'],m.SSD_WAIT)
  self.assertFalse(self.s.rows("SELECT id FROM jobs WHERE kind='mission_dispatch'"),'nothing is sent to a model that cannot answer')
  self.assertEqual(run['status'],'running');self.assertGreater(run['deadline'],time.time()+25*60,'the cycle keeps its time budget')
  self.s.db.execute('UPDATE orbit_mission_steps SET retry_at=0');self.s.db.commit()
  with patch('missions.ssd_waiting',return_value=False):m.tick(self.s)
  self.assertEqual(self.steps()[0]['state'],'dispatching','it continues once the disk answers')
  self.assertFalse(m.ssd_waiting(self.s),'no model storage configured: nothing to wait for')
 def test_dispatch_is_not_a_completed_child(self):
  self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Inspect actual files and return the evidence.')]);self.dispatch_all()
  self.assertEqual(self.steps()[0]['state'],'waiting')
  self.assertEqual(self.s.rows("SELECT status FROM jobs WHERE kind='mission_agent'")[0]['status'],'queued')
 def test_dependency_outputs_and_cross_project_routing(self):
  other=self.s.create_project('Másik projekt');aid=self.s.rows('SELECT id FROM agents WHERE project=?',(other,))[0]['id']
  self.launch([dict(id='a',kind='evaluate'),dict(id='b',kind='agent',project=other,agent=aid,after=['a'],prompt='Summarize the evidence; missing revenue is unknown.')])
  self.dispatch_all();m.tick(self.s);self.dispatch_all()
  job=self.s.rows("SELECT * FROM jobs WHERE kind='mission_agent'")[0]
  self.assertEqual(job['project'],other);self.assertIn('profit_status',job['prompt']);self.assertIn('unknown',job['prompt'])
  payload=json.loads(job['payload']);self.assertNotIn('write_file',payload['allowed_tools']);self.assertEqual(payload['agent_snapshot']['id'],aid)
 def test_repeated_and_interrupted_dispatch_has_one_child(self):
  self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Inspect actual project state.')]);d=self.s.claim(('mission_dispatch',));m.dispatch(self.s,d)
  self.s.db.execute("UPDATE orbit_mission_steps SET state='dispatching' WHERE node='a'");self.s.db.commit()
  m.dispatch(self.s,d);m.recover_interrupted(self.s)
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='mission_agent'").fetchone()[0],1)
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(d['id'],)).fetchone()[0],'queued')
 def test_agent_snapshot_does_not_change_midflight(self):
  self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Read project files and return a grounded answer.')]);self.dispatch_all()
  a=self.s.agent(self.a);old=a['prompt'];self.s.save_agent(dict(a,prompt='A newer different role.'))
  job=self.s.claim(('mission_agent',));captured=[]
  def model(*args,**kwargs):captured.append(args[2]);return dict(message=dict(content='Grounded answer'))
  with patch('studio.local_api',side_effect=model):self.s.run_agent(job)
  system=captured[0]['messages'][0]['content'];self.assertIn(old,system);self.assertNotIn('A newer different role.',system)
  tools=[t['function']['name'] for t in captured[0].get('tools',[])];self.assertNotIn('write_file',tools)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM orbit_agent_revisions').fetchone()[0],1)
 def test_json_contract_invalid_result_never_completes(self):
  self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Return a JSON report.',output='json')],max_attempts=1);self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='done',result='broken json' WHERE kind='mission_agent'");self.s.db.commit();m.tick(self.s)
  self.assertEqual(self.steps()[0]['state'],'attention')
 def test_read_only_transient_retry_preserves_done_parent(self):
  self.launch([dict(id='a',kind='evaluate'),dict(id='b',kind='agent',agent=self.a,after=['a'],prompt='Analyze predecessor evidence.')]);self.dispatch_all();m.tick(self.s);self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='failed',error='modell időkeret' WHERE kind='mission_agent'");self.s.db.commit();m.tick(self.s)
  steps=self.steps();self.assertEqual(steps[0]['state'],'done');self.assertEqual(steps[1]['state'],'pending');self.assertGreater(steps[1]['retry_at'],time.time())
  self.s.db.execute('UPDATE orbit_mission_steps SET retry_at=0');self.s.db.commit();m.tick(self.s);self.dispatch_all()
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='mission_agent'").fetchone()[0],2)
 def test_retried_step_learns_why_its_answer_was_rejected(self):
  # Cycle 163: the retry of a rejected build got the reason ("Érvénytelen csere-blokk.") and fixed it.
  self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Return a JSON report.',output='json')],max_attempts=2);self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='done',result='broken json' WHERE kind='mission_agent'");self.s.db.commit();m.tick(self.s)
  step=self.steps()[0];self.assertEqual(step['state'],'pending');self.assertTrue(step['error'])
  self.s.db.execute('UPDATE orbit_mission_steps SET retry_at=0');self.s.db.commit();m.tick(self.s);self.dispatch_all()
  prompts=[r['prompt'] for r in self.s.rows("SELECT prompt FROM jobs WHERE kind='mission_agent' ORDER BY created,rowid")]
  self.assertEqual(len(prompts),2);self.assertNotIn('Previous read-only attempt',prompts[0])
  self.assertIn('failed its contract. Return a corrected complete result. Diagnostic (data): '+step['error'][:40],prompts[1])
 def test_a_timeout_is_not_reported_to_the_model_as_its_mistake(self):
  self.launch([dict(id='a',kind='evaluate'),dict(id='b',kind='agent',agent=self.a,after=['a'],prompt='Analyze predecessor evidence.')]);self.dispatch_all();m.tick(self.s);self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='failed',error='modell időkeret' WHERE kind='mission_agent'");self.s.db.commit();m.tick(self.s)
  self.s.db.execute('UPDATE orbit_mission_steps SET retry_at=0');self.s.db.commit();m.tick(self.s);self.dispatch_all()
  self.assertNotIn('Previous read-only attempt',self.s.rows("SELECT prompt FROM jobs WHERE kind='mission_agent' ORDER BY created DESC,rowid DESC")[0]['prompt'])
 def test_an_answer_cut_at_the_limit_is_retried_with_more_room(self):
  # TermékA's 11 000-character sales page was cut mid-file twice at the same 4500-token limit.
  job=dict(payload=json.dumps(dict(rounds=[dict(stop='stop'),dict(stop='length')])))
  self.assertTrue(m.was_cut(job));self.assertFalse(m.was_cut(dict(payload='{}')))
  self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Return a JSON report.',output='json')],max_attempts=2);self.dispatch_all()
  self.s.db.execute("UPDATE orbit_mission_steps SET state='pending',error=?,retry_at=0,receipt='{}',dispatch=NULL",(m.CUT_NOTE+'Hiányzik az elkészült munka leírása.',))
  self.s.db.execute("UPDATE jobs SET status='done' WHERE kind='mission_agent'");self.s.db.commit()
  m.tick(self.s);self.dispatch_all()
  job=self.s.rows("SELECT prompt,payload FROM jobs WHERE kind='mission_agent' ORDER BY created DESC,rowid DESC")[0]
  self.assertEqual(json.loads(job['payload'])['reply_budget'],m.RETRY_REPLY);self.assertIn('cut off at the length limit inside a file',job['prompt'])
 def test_retry_circuit_stops_at_limit(self):
  mid=self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Analyze actual project evidence.')],max_attempts=1);self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='failed',error='connection timeout' WHERE kind='mission_agent'");self.s.db.commit();m.tick(self.s)
  self.assertEqual(self.steps()[0]['state'],'attention');self.assertEqual(m.listing(self.s)['missions'][0]['status'],'attention')
  with self.assertRaises(ValueError):m.start(self.s,'universe',mid)
 def test_pause_and_resume_do_not_duplicate_jobs(self):
  mid=self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Inspect actual project files.')]);m.pause(self.s,'universe',mid)
  self.dispatch_all();self.assertEqual(self.steps()[0]['state'],'dispatching')
  m.start(self.s,'universe',mid);m.recover_interrupted(self.s);m.tick(self.s)
  # Paused dispatch must become pending again rather than being lost as "done".
  self.assertIn(self.steps()[0]['state'],('pending','dispatching'))
 def test_wait_is_persisted_and_not_a_busy_loop(self):
  self.launch([dict(id='a',kind='evaluate'),dict(id='pause',kind='wait',after=['a'],seconds=3600),dict(id='b',kind='evaluate',after=['pause'])]);self.dispatch_all();m.tick(self.s)
  self.assertEqual(self.steps()[1]['state'],'pending');self.assertEqual(len(self.s.rows('SELECT id FROM jobs')),1)
  self.s.db.execute('UPDATE orbit_mission_steps SET updated=? WHERE node=\'a\'',(time.time()-3601,));self.s.db.commit();m.tick(self.s);m.tick(self.s);self.dispatch_all();m.tick(self.s)
  self.assertTrue(all(x['state']=='done' for x in self.steps()))
 def test_money_stays_unknown_without_accounting_evidence(self):
  result=m.evaluate(self.s,'universe')
  for key in ('net_profit','available_cash','verified_revenue','verified_cost'):self.assertIsNone(result[key])
 def test_capital_review_connects_projects_without_executing_trades(self):
  trade=self.s.create_project('BILLIONS','Virtuális kutatás','trading')
  self.launch([dict(id='a',kind='evaluate'),dict(id='b',kind='capital_review',project=trade,source_project='universe',after=['a'])]);self.dispatch_all();m.tick(self.s);self.dispatch_all();m.tick(self.s)
  result=json.loads(self.steps()[1]['result']);self.assertFalse(result['trade_executed']);self.assertFalse(result['transfer_executed']);self.assertIsNone(result['verified_available_cash'])
 def test_cycle_limit_and_duplicate_ticks(self):
  self.launch();m.tick(self.s);self.dispatch_all();m.tick(self.s);m.tick(self.s)
  self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),1);self.assertEqual(m.listing(self.s)['missions'][0]['status'],'completed')
 def test_cancel_stops_tracked_children(self):
  mid=self.launch([dict(id='a',kind='agent',agent=self.a,prompt='Inspect actual project state.')]);self.dispatch_all();m.pause(self.s,'universe',mid,True)
  self.assertEqual(self.s.rows("SELECT status FROM jobs WHERE kind='mission_agent'")[0]['status'],'cancelled')
 def test_save_origin_is_idempotent(self):
  a=m.save(self.s,'universe',self.goal(),origin='test:1');b=m.save(self.s,'universe',self.goal(),origin='test:1');self.assertEqual(a,b)
 def test_control_runs_actual_action_once(self):
  mid=self.launch([dict(id='configure',kind='control',actions=[dict(type='agent_save',agent=dict(self.s.agent(self.a),prompt='Use evidence and report unknown information.'))])])
  self.dispatch_all();self.s.run_next(('control_apply',));m.tick(self.s)
  self.assertIn('Use evidence',self.s.agent(self.a)['prompt']);self.assertEqual(self.steps()[0]['state'],'done');self.assertEqual(self.s.db.execute('SELECT count(*) FROM orbit_agent_revisions').fetchone()[0],1)
 def test_control_cannot_escape_project_or_run_shell(self):
  other=self.s.create_project('Másik')
  for action in (dict(type='run_command',cwd='/tmp',command='echo wrong'),dict(type='project_save',project=other,name='Wrong')):
   with self.subTest(action=action),self.assertRaises(ValueError):m.save(self.s,'universe',self.goal([dict(id='a',kind='control',actions=[action])]))
 def test_application_context_contains_real_mission_state(self):
  self.launch();from assistant_context import snapshot,read_app
  snap=snapshot(self.s);self.assertEqual(snap['assistant'],'ORBIT');self.assertEqual(len(snap['missions']['missions']),1)
  self.assertEqual(read_app(self.s,'universe','missions')['missions'][0]['steps'][0]['state'],'dispatching')
 def test_scheduler_failure_isolated_and_recorded(self):
  from scheduler_services import tick
  with patch.object(self.s,'schedule',side_effect=ValueError('test failure')),patch('growth.tick'),patch('assistant_context.publish'):
   health=tick(self.s)
  self.assertFalse(health['schedules']['ok']);self.assertTrue(health['missions']['ok']);self.assertTrue((self.s.root/'worker.heartbeat').exists())
 def shorts_team(self):
  for name in ('Echo','Scout','Lex','Reach','Vega'):
   self.s.save_agent(dict(project='universe',name=name,role=name,room='bridge',tools=['project_files','read_file','transcribe_media','analyze_video','render_short']))
  a=self.s.rows("SELECT id FROM agents WHERE project='universe' AND name='Pixel'")[0]['id']
  self.s.save_agent(dict(self.s.agent(a),tools=['analyze_video','render_short']))
 def test_verified_trend_source_required_for_dynamic_video(self):
  self.shorts_team()
  good=self.goal([dict(id='fresh',kind='trends'),dict(id='video',kind='shorts',after=['fresh'],query_from='fresh')]);m.save(self.s,'universe',good)
  for invalid in ('missing','video'):
   good['spec']['nodes'][1]['query_from']=invalid
   with self.assertRaises(ValueError):m.save(self.s,'universe',good)
 def test_mission_cannot_change_publication_policy(self):
  self.shorts_team()
  for node in (dict(id='a',kind='shorts',query='A topic',requirements=dict(publish_to_youtube=True)),dict(id='a',kind='control',actions=[dict(type='short_style_save',settings=dict(review_before_upload=False))])):
   with self.assertRaisesRegex(ValueError,'publikál'):m.save(self.s,'universe',self.goal([node]))
 def test_short_admission_receipt_is_not_verified_video(self):
  self.shorts_team();self.launch([dict(id='video',kind='shorts',query='A grounded subject')])
  jid=self.s.enqueue(self.a,'A queued video request','short_request')
  with patch('execution_queue.submit_short',return_value=dict(job=jid,queued=True)):self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(jid,));self.s.db.commit();m.tick(self.s)
  self.assertEqual(self.steps()[0]['state'],'attention');self.assertIn('ellenőrzött videó',self.steps()[0]['error'])
 def test_queue_receipt_expands_to_actual_run_members(self):
  self.shorts_team()
  from autonomous import start
  receipt=start(self.s,'universe','A real test subject',origin='test-origin')
  ids=m.job_ids(self.s,dict(project='universe',receipt=json.dumps(dict(origin='test-origin'))))
  self.assertEqual(set(ids),set(receipt['jobs'].values()))
 def test_two_scheduler_instances_admit_one_dispatch(self):
  mid=self.launch();other=Studio(self.s.root)
  try:m.tick(other);m.tick(self.s)
  finally:other.db.close()
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='mission_dispatch'").fetchone()[0],1)
 def test_assistant_saves_draft_without_model_in_start(self):
  from commander import prepare
  action=dict(type='mission_save',project='universe',mission=self.goal(),start=True)
  with self.assertRaisesRegex(ValueError,'nem indítható'):prepare(self.s,'universe',[action],True,user_request='Készíts egy tervet, ne indítsd el.')
  self.assertTrue(prepare(self.s,'universe',[action],True,user_request='Indítsd el ezt az ORBIT célt.')[0]['start'])
 def test_negative_bridge_receipt_is_not_claimed_success(self):
  from commander import schema,enqueue,approve,apply
  schema(self.s);jid=enqueue(self.s,'universe','Állítsd be a projekt nevét.');turn=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['turn']
  self.s.db.execute("UPDATE command_turns SET actions=?,status='review' WHERE id=?",(json.dumps([dict(type='project_save',project='universe',name='New')]),turn));self.s.db.commit()
  approved=approve(self.s,'universe',turn);job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(approved,)).fetchone())
  with patch('bridge.dispatch',return_value=dict(ok=False,message='Actual application failure')),self.assertRaisesRegex(ValueError,'Actual application failure'):apply(self.s,job)
  self.assertEqual(self.s.db.execute('SELECT status FROM command_turns WHERE id=?',(turn,)).fetchone()[0],'failed')
 def test_explicit_resume_preserves_completed_predecessor(self):
  mid=self.launch([dict(id='a',kind='evaluate'),dict(id='b',kind='agent',agent=self.a,after=['a'],prompt='Inspect the evidence.')],max_attempts=1);self.dispatch_all();m.tick(self.s);self.dispatch_all()
  self.s.db.execute("UPDATE jobs SET status='failed',error='model timeout' WHERE kind='mission_agent'");self.s.db.commit();m.tick(self.s)
  rid=self.steps()[0]['run'];m.resume(self.s,'universe',mid);m.tick(self.s);self.dispatch_all()
  self.assertEqual(self.steps()[0]['state'],'done');self.assertEqual(self.steps()[1]['state'],'waiting');self.assertTrue(all(x['run']==rid for x in self.steps()))
  self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),1)
 def test_large_handoffs_are_valid_json_without_truncated_objects(self):
  values={'source'+str(i):dict(content='a'*6000) for i in range(24)}
  raw=m.handoff_data(values,'run');parsed=json.loads(raw)
  self.assertEqual(len(parsed['omitted_steps']),24);self.assertLess(len(raw),6000)
 def test_publication_wait_requires_exact_public_processed_receipt(self):
  self.shorts_team();from autonomous import start
  production=start(self.s,'universe','A source topic',origin='publication-test')
  jid=self.s.enqueue(self.a,'Upload receipt test','youtube_upload',payload=dict(run=production['run']))
  step=dict(project='universe',receipt=json.dumps(dict(origin='publication-test')))
  base=self.s.root/'integrations/youtube/universe';base.mkdir(parents=True)
  file=base/('receipt-'+jid+'.json')
  self.assertIsNone(m.published_results(self.s,'universe',[step]))
  file.write_text(json.dumps(dict(id='abcdefghijk',privacy='private',processing='processed')));self.assertIsNone(m.published_results(self.s,'universe',[step]))
  file.write_text(json.dumps(dict(id='abcdefghijk',privacy='public',processing='uploaded')));self.assertIsNone(m.published_results(self.s,'universe',[step]))
  file.write_text(json.dumps(dict(id='abcdefghijk',privacy='public',processing='processed')))
  self.assertEqual(m.published_results(self.s,'universe',[step])['youtube_ids'],['abcdefghijk'])
 def test_rejected_youtube_processing_never_counts_as_ready(self):
  jid=self.s.enqueue(self.a,'Upload receipt test','youtube_upload');step=dict(project='universe',receipt=json.dumps(dict(job=jid)))
  base=self.s.root/'integrations/youtube/universe';base.mkdir(parents=True);(base/('receipt-'+jid+'.json')).write_text(json.dumps(dict(id='abcdefghijk',privacy='public',processing='rejected')))
  with self.assertRaisesRegex(ValueError,'feldolgozási hibát'):m.published_results(self.s,'universe',[step])
 def test_repeated_pause_preserves_original_pause_time(self):
  mid=self.launch();m.pause(self.s,'universe',mid)
  self.s.db.execute('UPDATE orbit_missions SET updated=1000 WHERE id=?',(mid,));self.s.db.commit()
  m.pause(self.s,'universe',mid)
  self.assertEqual(self.s.db.execute('SELECT updated FROM orbit_missions WHERE id=?',(mid,)).fetchone()[0],1000)
 def test_large_event_details_remain_valid_json(self):
  m.log(self.s,'test',None,None,'test',dict(content='árvíztűrő '*3000));self.s.db.commit()
  data=json.loads(self.s.db.execute('SELECT detail FROM orbit_mission_events').fetchone()[0])
  self.assertTrue(data['truncated']);self.assertIn('preview',data)
 def test_agent_receives_backend_read_files_without_model_tool_calls(self):
  base=self.s.root/'projects/universe';base.mkdir(parents=True,exist_ok=True);(base/'real-input.txt').write_text('Actual project input')
  self.launch([dict(id='inspect',kind='agent',agent=self.a,prompt='Analyze the real project inventory.')]);self.dispatch_all()
  job=self.s.rows("SELECT * FROM jobs WHERE kind='mission_agent'")[0];payload=json.loads(job['payload'])
  self.assertIn('real-input.txt',payload['input_evidence'][0]['result']);self.assertIn('real-input.txt',job['prompt'])
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM job_log WHERE kind='input_tool_done'").fetchone()[0],1)
  self.s.db.execute("UPDATE jobs SET status='done',result='The supplied real inventory contains real-input.txt.' WHERE id=?",(job['id'],));self.s.db.commit();m.tick(self.s)
  result=json.loads(self.steps()[0]['result']);self.assertEqual(result['content_source'],'model_analysis');self.assertEqual(result['input_evidence'][0]['tool'],'project_files')

if __name__=='__main__':unittest.main()
