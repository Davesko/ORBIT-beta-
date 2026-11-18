import json,time,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import test_autonomous as fixture
import automations
from execution_queue import submit_short,run_short
from workflow_health import production_task,failure_health

class WorkflowReliabilityTests(unittest.TestCase):
 setUp=fixture.AutoTests.setUp
 def test_producer_video_task_creates_actual_chain_without_model(self):
  producer=self.roles['producer'];self.s.db.execute('UPDATE agents SET name=? WHERE id=?',('Director',producer));self.s.db.commit()
  self.assertTrue(production_task(self.s,'universe',producer,'KAICENAT best moments video.'))
  aid=automations.save(self.s,'universe',dict(name='Production',kind='agent',config=dict(agent=producer,prompt='KAICENAT best moments video.')))
  with patch('studio.local_api',side_effect=AssertionError('No dialogue needed')):result=automations.launch(self.s,'universe',aid)
  self.assertEqual(len(result['jobs']),8)
  view=automations.listing(self.s,'universe')['automations'][0]
  self.assertEqual(view['execution_kind'],'shorts');self.assertEqual(len(view['workflow']),8)
  steps=view['runs'][0]['steps'];self.assertEqual(len(steps),8);self.assertEqual(steps[1]['parents'],[steps[0]['id']])
  self.assertTrue(all(json.loads(j['payload']).get('auto_step') for j in self.s.rows('SELECT payload FROM jobs')))
 def test_conversation_and_wrong_agent_do_not_start_videos(self):
  for prompt in ('Ne indíts videót','Hogyan készül egy video?','Check video status','Mennyi shorts készült?','Elemezd a video promptot'):
   self.assertFalse(production_task(self.s,'universe',self.roles['producer'],prompt))
  self.assertFalse(production_task(self.s,'universe',self.roles['source'],'Create a video'))
 def test_immediate_start_receipt_survives_completion_and_reopen(self):
  one=submit_short(self.s,'universe','A real video topic',origin='command:1')
  self.assertEqual(submit_short(self.s,'universe','A real video topic',origin='command:1')['run'],one['run'])
  self.s.db.execute("UPDATE jobs SET status='done'");self.s.db.commit()
  from studio import Studio
  other=Studio(self.s.root)
  try:self.assertEqual(submit_short(other,'universe','A real video topic',origin='command:1')['run'],one['run'])
  finally:other.db.close()
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM short_runs').fetchone()[0],1)
 def test_queue_resume_does_not_duplicate_started_production(self):
  first=submit_short(self.s,'universe','First real topic',origin='first')
  queued=submit_short(self.s,'universe','Second real topic',origin='second')
  self.s.db.execute("UPDATE jobs SET status='done' WHERE kind='graph'");self.s.db.commit()
  job=self.s.rows('SELECT * FROM jobs WHERE id=?',(queued['job'],))[0]
  run_short(self.s,job);run_short(self.s,job)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM short_runs').fetchone()[0],2)
 def test_backoff_starts_at_failure_not_start_of_long_run(self):
  aid=automations.save(self.s,'universe',dict(name='Work',kind='agent',config=dict(agent=self.roles['source'],prompt='Research topic')))
  run=automations.launch(self.s,'universe',aid);now=time.time()
  self.s.db.execute('UPDATE automation_runs SET created=? WHERE id=?',(now-7200,run['run']))
  for _ in range(automations.MAX_RESUMES+1):  # resumed from where it stopped until the resumes run out
   self.s.db.execute("UPDATE jobs SET status='failed',error='quota',finished=? WHERE id=?",(now,run['jobs'][0]));self.s.db.commit();automations.reconcile(self.s)
  health=failure_health(self.s,aid,now+1);self.assertGreater(health['retry_at'],now+290)
  self.assertEqual(failure_health(self.s,aid,now+301)['retry_at'],0)
 def test_source_handoff_retries_do_not_reserve_source_twice(self):
  from source_policy import submit
  data=dict(mode='explicit',topic='Real topic',sources=[dict(id='abcdefghijk',url='https://www.youtube.com/watch?v=abcdefghijk',metadata={})],news=[],max_age_hours=72)
  one=submit(self.s,'universe',data,origin='research:one');two=submit(self.s,'universe',data,origin='research:one')
  self.assertEqual(one['run'],two['run']);self.assertEqual(self.s.db.execute('SELECT count(*) FROM source_handoffs').fetchone()[0],1)

class EvidenceCoverageTests(unittest.TestCase):
 def test_bounded_catalog_keeps_context_near_end_of_long_footage(self):
  from editorial import covered_windows
  units=[dict(start=i,end=i+1) for i in range(200)]
  selected=covered_windows(units,48)
  self.assertEqual(len(selected),48);self.assertEqual(len({u['start'] for u in selected}),48)
  self.assertEqual(selected[0]['start'],0);self.assertEqual(selected[-1]['end'],200)
  self.assertGreater(sum(b['start']==a['end'] for a,b in zip(selected,selected[1:])),40)
 def test_literal_newline_is_not_a_topic_keyword(self):
  from clip_farm import research_spec
  self.assertEqual(research_spec('john anderson\\n')['terms'],['john','anderson'])

class ModelWaitTests(unittest.TestCase):
 def test_model_outage_is_bounded_and_saved_turn_can_resume(self):
  from studio import Studio
  from commander import enqueue,schema
  from supervisor_runtime import wait_for_model,continue_turn
  with tempfile.TemporaryDirectory() as root:
   s=Studio(Path(root));self.addCleanup(s.db.close);schema(s);jid=enqueue(s,'universe','List the projects','auto',global_mode=True)
   job=s.rows('SELECT * FROM jobs WHERE id=?',(jid,))[0];tid=json.loads(job['payload'])['turn']
   for _ in range(4):self.assertTrue(wait_for_model(s,job,ValueError('A helyi AI nem válaszolt az időkereten belül.')))
   self.assertEqual(s.rows('SELECT status FROM jobs WHERE id=?',(jid,))[0]['status'],'blocked')
   self.assertEqual(s.rows('SELECT status FROM command_turns WHERE id=?',(tid,))[0]['status'],'attention')
   self.assertEqual(continue_turn(s,tid),jid)
   self.assertEqual(s.rows('SELECT status FROM jobs WHERE id=?',(jid,))[0]['status'],'queued')

class ModelManifestTests(unittest.TestCase):
 def test_only_appledouble_sidecars_are_moved_and_repair_is_idempotent(self):
  from model_manifest import repair_sidecars
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);models=root/'models';manifests=models/'manifests/registry/library/qwen';manifests.mkdir(parents=True)
   actual=manifests/'14b';actual.write_text('{"layers":[]}')
   metadata=manifests/'._14b';metadata.write_bytes(b'\x00\x05\x16\x07metadata')
   unrelated=manifests/'._custom';unrelated.write_text('not AppleDouble')
   external=root/'external';external.write_bytes(b'\x00\x05\x16\x07external');(manifests/'._link').symlink_to(external)
   self.assertEqual(repair_sidecars(models,root),1);self.assertTrue(actual.exists());self.assertTrue(unrelated.exists());self.assertTrue(external.exists())
   self.assertEqual(len(list((root/'backups').rglob('._14b'))),1);self.assertEqual(repair_sidecars(models,root),0)

class DeadlineTests(unittest.TestCase):
 def test_short_hybrid_request_still_tries_cloud(self):
  import connections,ai_runtime
  with tempfile.TemporaryDirectory() as root,patch('connections.ROOT',Path(root)):
   connections.save(dict(provider='groq',enabled=True,key='test-not-real-key',mode='hybrid',share_context=True))
   with patch('ai_runtime.cloud_chat',return_value=dict(model='groq/test',message=dict(content='ok'))) as cloud:
    self.assertEqual(ai_runtime.request('api/chat',dict(model='auto',messages=[]),8)['model'],'groq/test')
    self.assertLessEqual(cloud.call_args.args[2],8)
 def test_local_timeout_reserves_time_for_other_model(self):
  import connections,ai_runtime
  with tempfile.TemporaryDirectory() as root,patch('connections.ROOT',Path(root)):
   now=[100.];budgets=[]
   def local(route,data,timeout):
    budgets.append(timeout)
    if len(budgets)==1:now[0]+=timeout;raise ValueError('A modell nem válaszolt az időkereten belül.')
    return dict(model=data['model'])
   with patch('ai_runtime.time.monotonic',side_effect=lambda:now[0]),patch('model_hub.models',return_value=[dict(name='qwen2.5:14b'),dict(name='qwen3.5:9b')]),patch('model_hub.request',side_effect=local):
    ai_runtime.request('api/chat',dict(model='auto',messages=[]),60)
   self.assertEqual(len(budgets),2);self.assertGreater(budgets[1],15);self.assertLessEqual(sum(budgets),60)

class ConcurrentAdmissionTests(unittest.TestCase):
 setUp=fixture.AutoTests.setUp
 def test_two_connections_admit_one_production_for_same_origin(self):
  import threading
  from studio import Studio
  barrier=threading.Barrier(2);results=[];errors=[]
  def context(*args):barrier.wait(timeout=5);return {}
  def submit():
   s=Studio(self.s.root)
   try:results.append(submit_short(s,'universe','Same video request',origin='same-origin'))
   except Exception as error:errors.append(str(error))
   finally:s.db.close()
  with patch('growth.context',side_effect=context):
   workers=[threading.Thread(target=submit) for _ in range(2)]
   for worker in workers:worker.start()
   for worker in workers:worker.join(8)
  self.assertFalse(errors,errors);self.assertEqual(len(results),2)
  self.assertEqual(results[0]['run'],results[1]['run']);self.assertEqual(self.s.db.execute('SELECT count(*) FROM short_runs').fetchone()[0],1)

class SourceQualityTests(unittest.TestCase):
 def test_black_source_is_excluded_and_partly_black_hook_is_rejected(self):
  from editorial import unit_catalog,feasible_story
  track=dict(source=dict(duration=20),quality=dict(black_intervals=[dict(start=0,end=2),dict(start=4,end=4.5)]),transcript=dict(segments=[dict(start=0,end=2,text='Blank opening.'),dict(start=4,end=8,text='Partly blank opening.'),dict(start=9,end=14,text='Visible context.'),dict(start=15,end=20,text='Visible ending.')]))
  style=dict(max_shot_seconds=6,min_seconds=10,max_seconds=30,min_shots=2,max_shots=6,target_seconds=15)
  catalog=unit_catalog([track],style)
  self.assertTrue(all(u['start']!=0 for u in catalog));self.assertFalse(catalog[0]['opening_visible'])
  with self.assertRaisesRegex(ValueError,'fekete'):feasible_story(dict(hook=0,sequence=[1,2]),catalog,style)
  self.assertTrue(feasible_story(dict(hook=1,sequence=[2]),catalog,style))
 def test_black_intervals_are_measured_and_silence_logs_are_not_visual_evidence(self):
  from source_quality import black_intervals
  self.assertEqual(black_intervals('[blackdetect] black_start:0 black_end:1.8 black_duration:1.8\n[silencedetect] silence_start:2 silence_end:5'),[dict(start=0,end=1.8)])
