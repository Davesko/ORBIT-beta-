import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from assistant_resilience import json_object,compact_context,retry_plan,recover_interrupted
from action_journal import begin,complete
from execution_queue import submit_short,run_short,DeferredExecution
class ResilienceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name)/'orbit');self.addCleanup(self.s.db.close)
  from commander import schema
  schema(self.s)
  self.a=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
 def test_invalid_or_empty_plan_is_not_executed(self):
  for value in (None,'','{"actions":[','[]'):
   with self.assertRaises(ValueError):json_object(value)
  self.assertEqual(json_object('```json\n{"reply":"ok","actions":[]}\n```')['reply'],'ok')
 def test_compact_context_preserves_valid_ids_without_json_slicing(self):
  c=compact_context(dict(overview=dict(projects=[dict(id=str(i),name='Project '+str(i),description='x'*4000) for i in range(60)],agents=[dict(id='a'+str(i),name='Name',project='0',role='x'*500) for i in range(100)])))
  self.assertLess(len(json.dumps(c)),16000);self.assertTrue(c['overview']['projects'][0]['id']=='0')
 def test_completed_mutation_is_checkpointed_and_not_replayed(self):
  action=dict(type='project_create',name='A real project')
  self.assertIsNone(begin(self.s,'turn',0,action,'universe'));complete(self.s,'turn',0,dict(project='created'),'created')
  result=begin(self.s,'turn',0,action,'universe');self.assertEqual(result['target'],'created')
  with self.assertRaises(ValueError):begin(self.s,'turn',0,dict(action,name='Changed plan'),'universe')
 def test_ambiguous_execution_is_not_blindly_repeated(self):
  action=dict(type='run_command',command='example');begin(self.s,'turn',0,action,'universe')
  with self.assertRaises(ValueError):begin(self.s,'turn',0,action,'universe')
 def test_busy_video_request_is_queued_and_deduplicated(self):
  self.s.enqueue(self.a,'An existing production','graph')
  one=submit_short(self.s,'universe','A real video topic',origin='turn:0');two=submit_short(self.s,'universe','A real video topic',origin='turn:0')
  self.assertEqual(one['job'],two['job']);self.assertTrue(one['queued'])
  job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(one['job'],)).fetchone())
  with self.assertRaises(DeferredExecution):run_short(self.s,job)
 def test_interrupted_planning_recovers_but_execution_is_not_replayed(self):
  jid=self.s.enqueue(self.a,'Human request','command',payload=dict(turn='turn'))
  self.s.db.execute("INSERT INTO command_turns VALUES(?,?,?,?,?,?,?,?,?)",('turn','universe','Human request','auto','','[]','running',jid,time.time()));self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));self.s.db.commit()
  recover_interrupted(self.s);self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'queued')
 def test_an_interrupted_story_step_runs_again_at_most_twice(self):
  jid=self.s.enqueue(self.a,'story','graph',payload=dict(story_step='sound',run='r1'))
  status=lambda:self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0]
  for expected in ('queued','queued','failed'):
   self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));self.s.db.commit()
   recover_interrupted(self.s);self.assertEqual(status(),expected)
 def test_bad_json_local_model_uses_fallback(self):
  import connections
  import ai_runtime
  with patch('inference_gate.lease',return_value=__import__('contextlib').nullcontext()),patch('connections.settings',return_value=dict(mode='local',share_context=True,preferred='groq',providers={})),patch('model_hub.models',return_value=[dict(name='qwen3.8:27b'),dict(name='qwen3.5:9b')]),patch('ai_runtime.unresponsive_models',return_value=set()),patch('connections.read',return_value={}),patch('connections.atomic'),patch('model_hub.request',side_effect=[dict(message=dict(content=None)),dict(message=dict(content='{"reply":"recovered"}'))]) as local:
   result=ai_runtime.request('api/chat',dict(model='auto',format='json',messages=[dict(role='user',content='Create a room')]),90)
  self.assertEqual(json.loads(result['message']['content'])['reply'],'recovered');self.assertEqual(local.call_count,2)

class IntentScopeTests(unittest.TestCase):
 def test_hungarian_agent_reply_request_never_changes_video_settings(self):
  from commander import schema,run,queue
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder)/'orbit');schema(s)
   aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];turn='intent'
   jid=queue(s,'universe','command','Test',dict(turn=turn,route=dict(task='chat',automatic=True),global_mode=True))
   s.db.execute('INSERT INTO command_global VALUES(?)',(turn,));s.db.execute('INSERT INTO command_turns VALUES(?,?,?,?,?,?,?,?,?)',(turn,'universe','Adj egy feladatot az ügynöknek: válaszoljon két rövid magyar mondatban. Ne módosítson beállítást.','auto','','[]','queued',jid,time.time()));s.db.commit()
   proposal=dict(reply='Feladat kiosztása.',reads=[],actions=[dict(type='agent_run',project='universe',agent=aid,prompt='Reply with two short Hungarian sentences.')])
   with patch('studio.local_api',return_value=dict(message=dict(content=json.dumps(proposal)))),patch('model_hub.brief',return_value={}):run(s,dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
   actions=json.loads(s.db.execute('SELECT actions FROM command_turns WHERE id=?',(turn,)).fetchone()[0]);self.assertEqual([a['type'] for a in actions],['agent_run']);s.db.close()

class RestartCompletionTests(unittest.TestCase):
 def test_completed_apply_is_reconciled_from_journal_without_execution(self):
  from commander import schema
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder)/'orbit');schema(s);aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];jid=s.enqueue(aid,'apply','command_apply',payload=dict(turn='turn'))
   action=dict(type='project_create',name='created')
   s.db.execute('INSERT INTO command_turns VALUES(?,?,?,?,?,?,?,?,?)',('turn','universe','request','auto','Verified completion',json.dumps([action]),'done',jid,time.time()));s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));s.db.commit();begin(s,'turn',0,action,'universe');complete(s,'turn',0,dict(project='created'),'created');recover_interrupted(s)
   self.assertEqual(s.db.execute('SELECT status,result FROM jobs WHERE id=?',(jid,)).fetchone()[0],'done');s.db.close()
