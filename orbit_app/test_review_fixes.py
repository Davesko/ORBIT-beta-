import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from commander import prepare,schema,image_size

class ReviewFixTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)

 def test_image_size_keeps_the_shape_at_a_renderable_size(self):
  self.assertEqual(image_size(768,768),(768,768))
  self.assertEqual(image_size(1920,1080),(1024,576))
  self.assertEqual(image_size('1024','512'),(1024,512))
  self.assertEqual(image_size(100,100),(256,256))
  self.assertEqual(image_size(None,'x'),(768,768))
  for w,h in [(4000,300),(300,4000),(1000,1000),(513,777)]:
   a,b=image_size(w,h)
   self.assertTrue(256<=a<=1024 and 256<=b<=1024 and a%64==0 and b%64==0,(w,h,a,b))

 def test_planned_image_size_is_fitted_not_rejected(self):
  out=prepare(self.s,'universe',[dict(type='generate_image',prompt='A red fox',width=1920,height=1080)])
  self.assertEqual((out[0]['width'],out[0]['height']),(1024,576))

 def test_flat_agent_fields_are_nested_before_execution(self):
  # A model sent {"type":"agent_save","name":...}; the approved plan then stopped with KeyError 'agent'.
  out=prepare(self.s,'universe',[dict(type='agent_save',project='universe',name='Grafika Megjelenítő',role='Megjelenítő',room='bridge',prompt='List the graphics.',tools=['read_file'])],allow_new_agents=True)
  self.assertEqual(out[0]['agent']['name'],'Grafika Megjelenítő')
  self.assertEqual(out[0]['project'],'universe')
  self.assertNotIn('name',out[0])
  from bridge import dispatch
  self.assertTrue(dispatch(dict(out[0],action='agent_save',project='universe'),self.s)['ok'])

 def test_empty_agent_save_is_a_planning_error(self):
  with self.assertRaises(ValueError):prepare(self.s,'universe',[dict(type='agent_save',project='universe')])

 def test_unknown_artifact_error_tells_the_model_what_to_use(self):
  with self.assertRaises(ValueError) as ctx:prepare(self.s,'universe',[dict(type='show_artifact',project='universe',id='nincs')])
  self.assertIn('generate_image',str(ctx.exception))

 def test_malformed_tool_call_xml_is_retried(self):
  from missions import _transient
  self.assertTrue(_transient('A helyi modell elutasította a kérést (500: XML syntax error on line 4: element <function> closed by </parameter>).'))

 def test_memory_learning_waits_after_a_cut_answer(self):
  import memory_brain
  memory_brain.schema(self.s)
  from commander import enqueue
  enqueue(self.s,'universe','Mostantól hívj Annának.','auto',global_mode=True)
  self.s.db.execute("UPDATE command_turns SET status='done'");self.s.db.commit()
  job=dict(id='memjob')
  with patch('studio.local_api',side_effect=ValueError('A terv túl hosszú lett. Részleges műveletsor nem hajtható végre; kérj kisebb lépéseket.')):
   result=memory_brain.learn(self.s,job)
  self.assertIn('újrapróbálásra',result)
  self.assertTrue(self.s.db.execute("SELECT 1 FROM memory_settings WHERE key='learn_retry'").fetchone())
  self.assertFalse(self.s.db.in_transaction)

 def test_product_check_runs_without_holding_the_write_lock(self):
  import venture_build,inspect
  src=inspect.getsource(venture_build)
  i=src.index('check=product_check.run(product)')
  self.assertIn('s.db.commit()',src[i-200:i])

if __name__=='__main__':unittest.main()

class StoryOrderTests(unittest.TestCase):
 def scenes(self,beats):
  from story_animation import BIBLE
  pick=lambda k:next(iter(BIBLE[k]))
  return [dict(beat=b,set=pick('sets'),actor=pick('cast'),action=pick('actions'),prop=pick('props'),caption='Scene '+str(i)) for i,b in enumerate(beats)]
 def test_labelled_beats_out_of_order_are_put_in_story_order(self):
  from story_animation import storyboard,BEATS
  plan=storyboard(dict(scenes=self.scenes(['payoff','Hook','context','escalation'])),18)
  text=json.dumps(plan)
  self.assertLess(text.index('Scene 1'),text.index('Scene 2'));self.assertLess(text.index('Scene 3'),text.index('Scene 0'))
 def test_unlabelled_scenes_keep_their_place(self):
  from story_animation import storyboard
  plan=storyboard(dict(scenes=self.scenes([None,None,None,None])),18)
  text=json.dumps(plan);self.assertLess(text.index('Scene 0'),text.index('Scene 3'))
 def test_wrong_beats_are_still_refused(self):
  from story_animation import storyboard
  with self.assertRaises(ValueError):storyboard(dict(scenes=self.scenes(['hook','hook','context','payoff'])),18)

class ModelShareTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def test_design_lane_waits_for_a_queued_chat_request(self):
  import design_studio
  from commander import enqueue
  self.assertFalse(design_studio.busy(self.s))
  enqueue(self.s,'universe','Szia, mi újság?','auto',global_mode=True)
  self.assertTrue(design_studio.busy(self.s))
 def test_assist_jobs_hold_the_model_lease(self):
  import assist_jobs,fcntl
  from execution_queue import DeferredExecution
  held=[]
  def fake(s,job):
   with open(Path(s.root).resolve()/'model-session.lock','a') as f:
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);held.append(False);fcntl.flock(f,fcntl.LOCK_UN)
    except BlockingIOError:held.append(True)
   return 'ok'
  with patch('assist_jobs._run',side_effect=fake):self.assertEqual(assist_jobs.run(self.s,dict(id='j',payload='{}')),'ok')
  self.assertEqual(held,[True])
  with open(Path(self.s.root).resolve()/'model-session.lock','a') as f:
   fcntl.flock(f,fcntl.LOCK_EX)
   import threading
   errors=[]
   t=threading.Thread(target=lambda:errors.append(self._try(assist_jobs)));t.start();t.join()
   fcntl.flock(f,fcntl.LOCK_UN)
  self.assertIsInstance(errors[0],DeferredExecution);self.assertGreaterEqual(errors[0].seconds,30)
 def _try(self,assist_jobs):
  try:assist_jobs.run(self.s,dict(id='j',payload=json.dumps(dict(task='memory_learn'))))
  except Exception as e:return e

class RepairLoopTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def test_the_same_plan_error_stops_after_two_corrections(self):
  from commander import enqueue,run
  from execution_queue import DeferredExecution
  jid=enqueue(self.s,'universe','Mutasd meg a tegnapi képet a projektben.','qwen3.5:9b',global_mode=True)
  job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  bad=dict(message=dict(content=json.dumps(dict(reply='Itt a kép.',reads=[],actions=[dict(type='show_artifact',project='universe',id='nincs-ilyen')]))))
  with patch('studio.local_api',return_value=bad) as api,patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.brief',return_value={}):
   for _ in range(12):
    try:run(self.s,job);break
    except DeferredExecution:pass
  turn=self.s.db.execute("SELECT status,response FROM command_turns").fetchone()
  self.assertEqual(turn[0],'attention');self.assertIn('Ismeretlen projektalkotás',turn[1])
  self.assertLessEqual(api.call_count,4)

class AutopilotSpeedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def test_cycle_lookups_use_the_mission_step_index(self):
  # The Autopilot and Creations tabs took 11-19 s: each cycle's job was found by parsing every job's JSON.
  import missions,re,inspect,venture,venture_build
  missions.schema(self.s)
  self.assertTrue(self.s.db.execute("SELECT 1 FROM sqlite_master WHERE name='jobs_mission_step'").fetchone())
  for src in (inspect.getsource(venture_build.timeline),inspect.getsource(venture.history)):
   sql=re.search(r'\(SELECT finished-started FROM jobs j.*?LIMIT 1\)|SELECT result FROM jobs WHERE kind=.mission_agent.*?LIMIT 1',src,re.S).group(0).strip('()')
   sql=sql.replace('r.id','?').replace("=?",'=?')
   plan=' '.join(str(tuple(r)) for r in self.s.db.execute('EXPLAIN QUERY PLAN '+sql,[ 'x']*sql.count('?')).fetchall())
   self.assertIn('jobs_mission_step',plan,sql)
 def test_creations_asks_only_for_the_light_status(self):
  text=(Path(__file__).parent/'web/creations_ui.js').read_text()
  self.assertIn("call('enterprise_status',{scope:'business_lab',head:true})",text)
