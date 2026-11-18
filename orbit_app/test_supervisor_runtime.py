import json,tempfile,time,unittest,threading
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from commander import enqueue,run,schema,apply,approve
from supervisor_runtime import load,explicit_short_plan,continue_turn
from execution_queue import DeferredExecution,defer
from inference_gate import lease

class SupervisorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def job(self,prompt='Vizsgáld meg a projektet és módosítsd a leírását.'):
  jid=enqueue(self.s,'universe',prompt,'auto',global_mode=True);return dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
 def response(self,**data):
  result=dict(reply='Terv',reads=[],actions=[]);result.update(data);return dict(message=dict(content=json.dumps(result)))
 def shorts(self):
  pid=self.s.create_project('YouTube Shorts')
  for name,role in [('KING','Producer'),('Atlas','Forrásszerkesztő'),('Echo','Átiratgazda'),('Scout','Klipszerkesztő'),('Pixel','Videószerkesztő'),('Lex','Felirat- és hangszerkesztő'),('Reach','Cím- és csomagszerkesztő'),('Vega','Végellenőr')]:
   self.s.save_agent(dict(project=pid,name=name,role=role,room='bridge',prompt='Use current verified inputs only.',tools=[]))
  return pid
 def test_acceptance_never_waits_for_model_inventory(self):
  with patch('model_hub.models',side_effect=AssertionError('No inventory on request acceptance')):
   job=self.job()
  self.assertEqual(job['status'],'queued')
 def test_named_project_id_question_is_repaired_not_marked_done(self):
  pid=self.s.create_project('GTA6 farm')
  job=self.job('Optimalizáld a GTA6 farm projekt leírását.')
  replies=[self.response(reply='Kérlek add meg a pontos projekt-azonosítót (ID).'),self.response(actions=[dict(type='project_save',project='GTA 6 farm',name='GTA6 farm',description='GTA 6 only.')])]
  with patch('studio.local_api',side_effect=replies) as api:
   with self.assertRaises(DeferredExecution):run(self.s,job)
   run(self.s,job)
  turn=self.s.rows('SELECT * FROM command_turns')[0]
  self.assertEqual(json.loads(turn['actions'])[0]['project'],pid)
  self.assertIn(pid,api.call_args.args[2]['messages'][-1]['content'])
 def test_read_aliases_are_canonical_and_unknown_target_is_not_discarded(self):
  from commander import tidy_read
  pid=self.s.create_project('GTA6 farm')
  self.assertEqual(tidy_read(self.s,dict(type='email',project='GTA 6 farm')),dict(app='emails',project=pid))
  self.assertEqual(tidy_read(self.s,dict(app='automations',project='missing'))['project'],'missing')
 def test_optimize_then_generate_does_not_skip_configuration(self):
  self.shorts()
  self.assertIsNone(explicit_short_plan(self.s,'universe','Optimalizáld a projektet, majd készíts shorts videót. Fő téma: GTA6',True))
 def test_explicit_video_uses_controller_without_a_model_or_read_loop(self):
  pid=self.shorts();prompt='generálj egy youtube shorts anyagot az agentekkel. Fő téma: Victoria Secret fashion show 2026 best moments. A vicdeó hossza 50-100 mp.'
  job=self.job(prompt)
  with patch('studio.local_api',side_effect=AssertionError('No planning call needed')):run(self.s,job)
  turn=self.s.rows('SELECT * FROM command_turns')[0];actions=json.loads(turn['actions']);self.assertEqual(actions[-1]['query'],'Victoria Secret fashion show 2026 best moments');self.assertEqual(actions[-1]['project'],pid)
  current=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(turn['job'],)).fetchone());self.assertEqual(current['kind'],'control_apply')
  with patch('execution_queue.submit_short',return_value=dict(run='real-dispatch',jobs={})) as submit:
   apply(self.s,current);apply(self.s,current)
  self.assertEqual(submit.call_count,1)
 def test_read_evidence_survives_slices_and_reopened_database(self):
  job=self.job();agent=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  replies=[self.response(reads=[dict(project='universe')]),self.response(reads=[dict(agent=agent)]),self.response(actions=[dict(type='project_save',project='universe',name='Műhely',description='Factual updated description.')])]
  with patch('studio.local_api',side_effect=replies) as api,patch('model_hub.brief',return_value={}):
   with self.assertRaises(DeferredExecution):run(self.s,job)
   self.assertEqual(api.call_count,1)
   other=Studio(self.s.root)
   try:
    with self.assertRaises(DeferredExecution):run(other,job)
    self.assertEqual(len(load(other,json.loads(job['payload'])['turn'])['cache']),2)
    run(other,job)
   finally:other.db.close()
  self.assertEqual(api.call_count,3);last='\n'.join(m.get('content','') for m in api.call_args.args[2]['messages']);self.assertIn('project_context',last);self.assertIn(agent,last)
 def test_repeated_read_does_not_refetch_or_throw_budget_timeout(self):
  job=self.job()
  with patch('studio.local_api',return_value=self.response(reads=[dict(project='universe')])),patch('model_hub.brief',return_value={}),patch('commander.context',wraps=__import__('commander').context) as read:
   for _ in range(8):
    try:run(self.s,job);break
    except DeferredExecution:pass
  turn=self.s.rows('SELECT * FROM command_turns')[0];self.assertEqual(turn['status'],'attention');self.assertEqual(read.call_count,1);self.assertNotIn('időtúllépés',turn['response'])
 def test_timeout_retains_checkpoint_and_waits_without_failing_request(self):
  job=self.job()
  with patch('studio.local_api',side_effect=ValueError('A helyi AI nem válaszolt az időkereten belül.')),patch('model_hub.brief',return_value={}):self.s.run_next(('command',))
  row=self.s.db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone();self.assertEqual(row['status'],'queued');self.assertEqual(row['error'],'');self.assertGreater(json.loads(row['payload'])['retry_at'],time.time());self.assertTrue(load(self.s,json.loads(job['payload'])['turn'])['messages'])
 def test_model_busy_is_waiting_and_cannot_overwrite_new_progress(self):
  job=self.job();self.s.db.execute("UPDATE jobs SET payload=json_set(payload,'$.selected_model','verified-model') WHERE id=?",(job['id'],));self.s.db.commit()
  defer(self.s,job,DeferredExecution('A modell foglalt.',3));p=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]);self.assertEqual(p['selected_model'],'verified-model');self.assertEqual(self.s.rows('SELECT status FROM command_turns')[0]['status'],'queued')
 def test_continuation_reuses_original_job_not_a_duplicate_request(self):
  job=self.job();turn=json.loads(job['payload'])['turn'];self.s.db.execute("UPDATE jobs SET status='failed' WHERE id=?",(job['id'],));self.s.db.execute("UPDATE command_turns SET status='attention' WHERE id=?",(turn,));self.s.db.commit()
  self.assertEqual(continue_turn(self.s,turn),job['id']);self.assertEqual(self.s.db.execute('SELECT count(*) FROM command_turns').fetchone()[0],1)
 def test_fast_controller_never_treats_examples_or_negation_as_execution(self):
  self.shorts()
  for prompt in ('Ne generálj youtube shorts videót. Fő téma: Speed','Ez egy prompt példa: generálj youtube shorts videót. Fő téma: Speed','Hogyan kell youtube shorts videót generálni? Fő téma: Speed'):
   self.assertIsNone(explicit_short_plan(self.s,'universe',prompt,True))
 def test_quick_controls_are_available_while_a_render_job_runs(self):
  pid=self.shorts();aid=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];heavy=self.s.enqueue(aid,'A long render','graph');self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(heavy,));self.s.db.commit()
  job=self.job('Generálj youtube shorts videót. Fő téma: Public fashion highlights. A videó hossza 50-100 mp.')
  with patch('studio.local_api',side_effect=AssertionError('No GPU needed')):self.s.run_next(('command','control_apply'))
  turn=self.s.rows('SELECT * FROM command_turns')[0]
  with patch('execution_queue.submit_short',return_value=dict(job='queued-short',queued=True)):
   # In production the queued job exists; exercise dispatch without fake linked IDs.
   with patch('execution_queue.submit_short',return_value=dict(queued=True)):self.s.run_next(('command','control_apply'))
  self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(heavy,)).fetchone()[0],'running');self.assertEqual(self.s.db.execute('SELECT status FROM command_turns WHERE id=?',(turn['id'],)).fetchone()[0],'done')
 def test_approval_queue_creation_is_atomic_on_failure(self):
  job=self.job();turn=json.loads(job['payload'])['turn'];self.s.db.execute("UPDATE command_turns SET status='review',actions='[]' WHERE id=?",(turn,));self.s.db.commit()
  with patch('commander.queue',side_effect=RuntimeError('Simulated disk error')):
   with self.assertRaises(RuntimeError):approve(self.s,'universe',turn,True)
  self.assertEqual(self.s.db.execute('SELECT status FROM command_turns WHERE id=?',(turn,)).fetchone()[0],'review')

class GateTests(unittest.TestCase):
 def test_reentrant_same_thread_but_other_thread_yields_immediately(self):
  with tempfile.TemporaryDirectory() as folder:
   seen=[]
   with lease(folder):
    with lease(folder):pass
    def other():
     try:
      with lease(folder):seen.append('incorrect acquisition')
     except DeferredExecution:seen.append('waiting')
    t=threading.Thread(target=other);t.start();t.join(2);self.assertFalse(t.is_alive());self.assertEqual(seen,['waiting'])
   with lease(folder):pass

class BusyMediaTests(unittest.TestCase):
 setUp=SupervisorTests.setUp
 job=SupervisorTests.job
 shorts=SupervisorTests.shorts
 def test_busy_image_waits_before_any_action_journal_or_effect(self):
  from action_journal import schema as journal_schema
  journal_schema(self.s);job=self.job('Készíts egy képet.');turn=json.loads(job['payload'])['turn']
  actions=[dict(type='generate_image',project='universe',prompt='A simple green cube',width=512,height=512)]
  self.s.db.execute("UPDATE command_turns SET status='review',actions=? WHERE id=?",(json.dumps(actions),turn));self.s.db.commit();jid=approve(self.s,'universe',turn,True);execution=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  with patch('inference_gate.lease',side_effect=DeferredExecution('A modell foglalt.',3)),patch('commander._generate_image',side_effect=AssertionError('No generation while busy')):
   with self.assertRaises(DeferredExecution):apply(self.s,execution)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM command_action_journal').fetchone()[0],0);self.assertEqual(self.s.db.execute('SELECT status FROM command_turns WHERE id=?',(turn,)).fetchone()[0],'queued_apply')
 def test_busy_editorial_model_is_not_misreported_as_bad_source(self):
  from autonomous import start,run_step
  from short_style import DEFAULT
  pid=self.shorts();result=start(self.s,pid,'An actual video topic',requirements=dict(visual_analysis=False,max_shot_seconds=12,min_seconds=50,max_seconds=100,target_seconds=75))
  base=self.s.root/'projects'/pid;base.mkdir(parents=True,exist_ok=True);transcript=dict(text='Actual complete source sentences.',segments=[dict(start=i*10,end=(i+1)*10,text='This is an actual complete source sentence.') for i in range(8)])
  (base/'transcript.json').write_text(json.dumps(transcript));(base/'source.srt').write_text('')
  row=self.s.db.execute('SELECT data FROM short_runs WHERE id=?',(result['run'],)).fetchone();data=json.loads(row[0]);source=dict(source_video='sources/actual.mp4',duration=80,metadata=dict(title='Actual video',url='https://example.test/source'));data.update(source=source,sources=[source],transcript='transcript.json',subtitle='source.srt',tracks=[dict(source=source,transcript_file='transcript.json',subtitle='source.srt')]);self.s.db.execute('UPDATE short_runs SET data=? WHERE id=?',(json.dumps(data),result['run']));self.s.db.commit();job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(result['jobs']['selection'],)).fetchone())
  for step in ('producer','source','transcript'):self.s.db.execute("UPDATE jobs SET status='done',result='{}' WHERE id=?",(result['jobs'][step],))
  self.s.db.commit()
  with patch('semantic_boundaries.enrich'),patch('language_bridge.translate_many',side_effect=lambda values,root:values),patch('autonomous.ask_json',side_effect=DeferredExecution('A modell másik feladaton dolgozik.',3)) as ask,patch('source_quality.annotate',side_effect=lambda s,j,t,d:d.setdefault('source_quality',{})):
   with self.assertRaises(DeferredExecution):run_step(self.s,job)
  self.assertEqual(ask.call_count,1)

class CancellationTests(unittest.TestCase):
 setUp=SupervisorTests.setUp
 job=SupervisorTests.job
 def test_cancelled_planning_cannot_be_resurrected_by_a_defer(self):
  job=self.job();self.s.cancel(job['id']);defer(self.s,job,DeferredExecution('wait',3));self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'cancelled')
 def test_stopping_original_request_also_cancels_its_queued_control_job(self):
  from bridge import dispatch
  job=self.job();turn=json.loads(job['payload'])['turn'];self.s.db.execute("UPDATE command_turns SET status='review',actions='[]' WHERE id=?",(turn,));self.s.db.commit();child=approve(self.s,'universe',turn,True)
  dispatch(dict(action='job_cancel',project='universe',id=job['id']),self.s);self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(child,)).fetchone()[0],'cancelled')
 def test_cancelled_request_cannot_consume_approval(self):
  job=self.job();turn=json.loads(job['payload'])['turn'];self.s.db.execute("UPDATE command_turns SET status='review',actions='[]' WHERE id=?",(turn,));self.s.db.commit();self.s.cancel(job['id'])
  with self.assertRaises(ValueError):approve(self.s,'universe',turn,True)

class IntentLabels(unittest.TestCase):
 def test_negated_media_instructions_are_a_conversation(self):
  from model_router import task_type
  self.assertEqual(task_type('Sorold fel a projektjeimet. Ne indíts videót és ne hozz létre új feladatot.'),'chat')
  self.assertEqual(task_type('Indíts egy YouTube Shorts videót a meglévő csapattal.'),'video')

class ClipFarmControlTests(unittest.TestCase):
 def test_natural_clip_farm_request_starts_existing_team_without_model_or_approval(self):
  from clip_farm import configure,PROJECT
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close);schema(s);configure(s)
   prompt='generálj a clip farm automatizálásával egy videót ami A victoria secret show 2026 ról szól'
   plan=explicit_short_plan(s,'universe',prompt,True)
   self.assertEqual(plan[-1]['project'],PROJECT);self.assertEqual(plan[-1]['query'],'victoria secret show 2026');self.assertEqual(plan[-1]['source_mode'],'topic')
   turn_job=enqueue(s,'universe',prompt,'auto',global_mode=True)
   with patch('studio.local_api',side_effect=AssertionError('No model planning needed')):
    self.assertTrue(s.run_next(('command',)));self.assertTrue(s.run_next(('control_apply',)))
   self.assertEqual(s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND kind='graph'",(PROJECT,)).fetchone()[0],8)
   status=s.db.execute('SELECT status FROM command_turns WHERE prompt=?',(prompt,)).fetchone()[0]
   self.assertEqual(status,'done')
