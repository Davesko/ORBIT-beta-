import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
from commander import enqueue,run,prepare,schema
class ChatControlTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def test_manual_model_is_used_without_translation_roundtrip(self):
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b'),dict(name='qwen3.8:27b')]):jid=enqueue(self.s,'universe','Mi a különbség a hasonlat és a metafora között?','qwen3.5:9b',global_mode=True)
  job=dict(self.s.db.execute('select * from jobs where id=?',(jid,)).fetchone())
  with patch('language_bridge.translate_many',side_effect=AssertionError('No mandatory translation')),patch('studio.local_api',return_value=dict(message=dict(content=json.dumps(dict(kind='reply',reply='A hasonlat nyíltan hasonlít, a metafora azonosít.'))))) as api:run(self.s,job)
  self.assertEqual(api.call_count,1);self.assertEqual(api.call_args.args[2]['model'],'qwen3.5:9b')
  self.assertEqual(api.call_args.args[2]['options']['num_ctx'],4096)
  self.assertNotIn('CURRENT APP STATE',str(api.call_args.args[2]['messages']))
  self.assertEqual(api.call_args.args[2]['format']['properties']['kind']['enum'],['reply','delegate'])
  self.assertEqual(api.call_args.args[2]['_orbit_purpose'],'interactive')
 def test_a_failed_previous_task_does_not_slow_an_unrelated_question(self):
  from commander import direct_conversation
  jid=enqueue(self.s,'universe','Mi a különbség a hasonlat és a metafora között?','auto',global_mode=True)
  job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  turn=json.loads(job['payload'])['turn'];row=dict(self.s.db.execute('SELECT * FROM command_turns WHERE id=?',(turn,)).fetchone())
  response=dict(message=dict(content=json.dumps(dict(kind='reply',reply='A hasonlat összevet, a metafora azonosít.'))))
  with patch('studio.local_api',return_value=response) as api:
   self.assertTrue(direct_conversation(self.s,row,job,dict(automatic=True),[dict(status='failed',prompt='Régi feladat',response='')]))
  api.assert_called_once()
 def test_interactive_routing_and_background_admission(self):
  from model_router import choose
  from inference_gate import interactive_pending,yield_for_chat
  from execution_queue import DeferredExecution
  names=['qwen3.5:9b','gemma4:26b','qwen3.8:27b-q4_K_M']
  self.assertEqual(choose('Magyarázd el röviden.',names,purpose='interactive')['model'],'qwen3.5:9b')
  self.assertEqual(choose('Magyarázd el röviden.',names,requested='gemma4:26b',purpose='interactive')['model'],'gemma4:26b')
  self.assertFalse(interactive_pending(self.s.root))
  enqueue(self.s,'universe','Egy rövid kérdés.','auto')
  self.assertTrue(interactive_pending(self.s.root))
  with self.assertRaises(DeferredExecution):yield_for_chat(self.s.root)
 def test_greeting_skips_planning_but_action_intent_does_not(self):
  from commander import conversation_candidate
  jid=enqueue(self.s,'universe','Szia!','qwen3.5:9b',global_mode=True)
  job=dict(self.s.db.execute('select * from jobs where id=?',(jid,)).fetchone())
  with patch('studio.local_api',side_effect=AssertionError('No model needed for a greeting')):
   self.assertEqual(run(self.s,job),'Szia! Miben segíthetek?')
  self.assertFalse(conversation_candidate('Szia, keresd meg a friss leveleimet.'))
  self.assertTrue(conversation_candidate('Mit jelent az, hogy körkörös érvelés?'))

 def test_mixed_script_reply_gets_one_local_fallback(self):
  jid=enqueue(self.s,'universe','Mi a különbség a hasonlat és a metafora között?','gemma:12b',global_mode=True)
  job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  def response(reply):return dict(message=dict(content=json.dumps(dict(kind='reply',reply=reply))))
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('studio.local_api',side_effect=[response('A hasonlat الآخر.'),response('A hasonlat nyílt összevetés.')]) as api:
   self.assertEqual(run(self.s,job),'A hasonlat nyílt összevetés.')
  self.assertEqual([call.args[2]['model'] for call in api.call_args_list],['gemma:12b','qwen3.5:9b'])
  from commander import mixed_script_reply
  self.assertFalse(mixed_script_reply('Fordítsd le arabra.','مرحبا'))
 def test_chat_has_priority_over_old_background_jobs(self):
  agent=self.s.rows('select id from agents')[0]['id'];self.s.enqueue(agent,'older background','graph')
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]):jid=enqueue(self.s,'universe','hello','auto')
  self.assertEqual(self.s.claim(('graph','command'))['id'],jid)
 def test_agent_delete_hides_and_disables_without_destroying_history(self):
  agent=self.s.snapshot('universe')['agents'][0];jid=self.s.enqueue(agent['id'],'original task')
  dispatch(dict(action='agent_archive',project='universe',id=agent['id']),self.s)
  self.assertNotIn(agent['id'],[a['id'] for a in self.s.snapshot('universe')['agents']]);self.assertEqual(self.s.db.execute('select status from jobs where id=?',(jid,)).fetchone()[0],'cancelled')
  with self.assertRaises(ValueError):self.s.enqueue(agent['id'],'new task')
  dispatch(dict(action='agent_restore',project='universe',id=agent['id']),self.s);self.assertIn(agent['id'],[a['id'] for a in self.s.snapshot('universe')['agents']])
 def test_new_agents_can_be_scheduled_in_same_plan(self):
  actions=[dict(type='project_create',name='Teszt'),dict(type='agent_save',agent=dict(id='a-new',name='A')),dict(type='agent_save',agent=dict(id='b-new',name='B')),dict(type='recipe_save',name='Team',agents=['a-new','b-new'],prompt='Research',interval=60)]
  self.assertEqual(len(prepare(self.s,'universe',actions,True)),4)
if __name__=='__main__':unittest.main()

class LifecycleTests(unittest.TestCase):
 setUp=ChatControlTests.setUp
 def test_room_agent_and_automation_lifecycle(self):
  s=self.s;pid='universe';room=s.save_room(pid,dict(name='Próba szoba',sub='Teszt'))
  aid=s.save_agent(dict(project=pid,name='Tesztkutató',room=room,model='auto',prompt='Summarize verified inputs.',tools=['project_files','read_file'],interval=60))
  members=[aid,s.snapshot(pid)['agents'][0]['id']]
  rid=s.save_recipe(pid,'Kutatás',members,'Summarize the project.',60)
  result=dispatch(dict(action='recipe_run',project=pid,id=rid),s);self.assertTrue(result['job'])
  self.assertEqual(s.db.execute("select count(*) from jobs where kind='pipeline' and status='queued'").fetchone()[0],2)
  dispatch(dict(action='recipe_pause',project=pid,id=rid),s);self.assertEqual(s.db.execute('select interval from recipes where id=?',(rid,)).fetchone()[0],0)
  dispatch(dict(action='agent_archive',project=pid,id=aid),s)
  dispatch(dict(action='room_archive',project=pid,id=room,move_to='bridge'),s)
  self.assertEqual(s.db.execute('select archived from rooms where id=? and project=?',(room,pid)).fetchone()[0],1)
  dispatch(dict(action='room_restore',project=pid,id=room),s);dispatch(dict(action='agent_restore',project=pid,id=aid),s)

class RepeatedReadTests(unittest.TestCase):
 setUp=ChatControlTests.setUp
 def test_agent_uses_existing_evidence_instead_of_repeating_file_reads(self):
  aid=self.s.snapshot('universe')['agents'][0]['id'];jid=self.s.enqueue(aid,'List project files, then summarize.')
  tool=dict(message=dict(role='assistant',tool_calls=[dict(function=dict(name='project_files',arguments={}))]))
  with patch('studio.local_api',side_effect=[tool,tool,dict(message=dict(content='Összefoglaló kész.'))]),patch.object(self.s,'tool',return_value=dict(files=['brief.md'])) as execute:
   self.s.run_next(('chat',))
  self.assertEqual(execute.call_count,1);self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'done')

class AgentMutationSafetyTests(unittest.TestCase):
 setUp=ChatControlTests.setUp
 def test_unrequested_model_and_tool_changes_are_not_applied(self):
  agent=self.s.snapshot('universe')['agents'][0];agent['model']='auto';self.s.save_agent(agent)
  action=dict(type='agent_save',project='universe',agent=dict(id=agent['id'],model='qwen3.8:27b',tools=[],room='media',role='Más szerep',prompt='Improve editing.'))
  result=prepare(self.s,'universe',[action],user_request='Legyen több zoom a videóban.')[0]['agent']
  self.assertEqual(result['model'],'auto');self.assertEqual(result['room'],agent['room']);self.assertTrue(set(agent['tools'])<=set(result['tools']))
