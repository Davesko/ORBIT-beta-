import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import commander,chat_sessions,conversation_state as tasks,assistant_skills as skills,assistant_tools as tools

class FoundationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);commander.schema(self.s)
 def turn(self,prompt,session):
  job=commander.enqueue(self.s,'universe',prompt,'auto',global_mode=True,session=session)
  return json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0])['turn'],job
 def test_capability_forms_and_execution_admission_have_one_source(self):
  self.assertIs(commander.APP_ACTIONS,tools.APP_ACTIONS)
  self.assertEqual(set(tools.BRIDGE_ACTIONS)-set(tools.ACTION_CONTRACTS),set())
  self.assertEqual(tools.AUTO_APP-set(tools.ACTION_CONTRACTS),set())
  self.assertIn('emails',tools.READ_CONTRACT);self.assertIn('skills',tools.READ_CONTRACT)
  shortlist=tools.catalog('Keresd meg az emailt')
  self.assertNotIn('generate_image',shortlist['actions']);self.assertIn('generate_image',shortlist['all_action_types'])
  self.assertIn('generate_image',tools.catalog(full=True)['actions'])
  with self.assertRaises(ValueError):commander.prepare(self.s,'universe',[dict(type='invented')])
 def test_old_constraints_survive_more_than_three_turns_and_restart(self):
  sid=chat_sessions.ensure(self.s,None,'Video')
  first,_=self.turn('Use only GTA6 sources. Duration 45 seconds. Never publish automatically.',sid)
  for i in range(5):self.turn('Follow-up '+str(i),sid)
  current,_=self.turn('What was the required duration?',sid)
  other=Studio(self.s.root)
  try:context=tasks.context(other,current)
  finally:other.db.close()
  self.assertTrue(any(x['turn']==first and '45 seconds' in x['request'] for x in context['previous']))
 def test_chat_isolation_and_scope_checked_full_turn_reads(self):
  a=chat_sessions.ensure(self.s,None,'A');b=chat_sessions.ensure(self.s,None,'B')
  first,_=self.turn('Private task A',a);second,_=self.turn('New independent task',b)
  self.assertEqual(tasks.context(self.s,second)['previous'],[])
  with self.assertRaises(ValueError):tasks.read(self.s,second,first)
 def test_bad_historical_plan_does_not_break_task_context(self):
  sid=chat_sessions.ensure(self.s,None,'A');old,_=self.turn('Old request',sid)
  self.s.db.execute('UPDATE command_turns SET actions=? WHERE id=?',('{broken',old));self.s.db.commit()
  new,_=self.turn('Continue the conversation',sid)
  self.assertEqual(tasks.context(self.s,new)['previous'][0]['proposed_actions'],[])
 def test_followup_reports_queued_work_not_fabricated_completion(self):
  sid=chat_sessions.ensure(self.s,None,'Task');first,job=self.turn('Make a video',sid)
  self.s.db.execute("UPDATE command_turns SET status='done' WHERE id=?",(first,));self.s.db.commit()
  greeting,greet_job=self.turn('itt vagy?',sid)
  self.s.db.execute("UPDATE command_turns SET status='done' WHERE id=?",(greeting,));self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(greet_job,));self.s.db.commit()
  second,_=self.turn('megcsináltad?',sid)
  answer=tasks.status_answer(self.s,second,'megcsináltad?');self.assertIn('sorban',answer)
  with patch('studio.local_api',side_effect=AssertionError('Status must be read from receipts')):
   commander.run(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=(SELECT job FROM command_turns WHERE id=?)',(second,)).fetchone()))
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM command_action_journal').fetchone()[0] if self.s.db.execute("SELECT 1 FROM sqlite_master WHERE name='command_action_journal'").fetchone() else 0,0)
 def test_deleting_chat_hides_but_preserves_recoverable_task_context(self):
  sid=chat_sessions.ensure(self.s,None,'A');turn,job=self.turn('A task',sid)
  self.s.db.execute("UPDATE command_turns SET status='done' WHERE id=?",(turn,));self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(job,));self.s.db.commit()
  tasks.observe(self.s,turn);chat_sessions.remove(self.s,sid)
  self.assertIsNotNone(self.s.db.execute('SELECT 1 FROM assistant_task_state WHERE turn=?',(turn,)).fetchone())
  self.assertEqual(commander.state(self.s,'universe',True,sid)['turns'],[])
  chat_sessions.restore(self.s,sid)
  self.assertEqual(commander.state(self.s,'universe',True,sid)['turns'][0]['id'],turn)
 def test_draft_disabled_and_versions_of_skills(self):
  spec=dict(title='Egyedi riport',description='Reusable method',steps=['Read the actual input.'],verification=['Check the saved result.'],tags=['egyedi'],status='draft')
  first=skills.save(self.s,spec)
  self.assertEqual(skills.select(self.s,'egyedi'),[])
  spec.update(id=first['id'],status='published');second=skills.save(self.s,spec)
  self.assertEqual(second['version'],2);self.assertEqual(skills.select(self.s,'egyedi')[0]['version'],2)
  skills.toggle(self.s,first['id'],False);self.assertEqual(skills.select(self.s,'egyedi'),[])
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM assistant_skill_versions WHERE id=?',(first['id'],)).fetchone()[0],1)
 def test_skill_validation_and_public_api(self):
  from project_apps import dispatch
  self.assertGreaterEqual(len(dispatch(self.s,'universe','skill_list',{})['result']['skills']),4)
  with self.assertRaises(ValueError):skills.save(self.s,dict(title='Invalid',steps=['Do it'],verification=[],tags=[]))
  with self.assertRaises(ValueError):skills.save(self.s,dict(id='mail-review',title='Override builtin'))
 def test_assistant_can_prepare_skill_only_as_inactive_draft(self):
  spec=dict(title='Tanított módszer',description='A user-requested procedure.',steps=['Read input.'],verification=['Check output.'],tags=['custom'],status='published')
  plan=commander.prepare(self.s,'universe',[dict(type='app_action',project='universe',operation='skill_save',args=dict(skill=spec))],True,user_request='Mentsd el ezt munkamódszerként.')
  self.assertEqual(plan[0]['args']['skill']['status'],'draft')
  self.assertEqual(len([x for x in skills.listing(self.s) if x['source']!='builtin']),0,'planning must not save skills')
 def test_planner_receives_live_task_context_and_selected_skills(self):
  sid=chat_sessions.ensure(self.s,None,'Project');turn,job=self.turn('Nézd át a projekt ügynökeit és javasolj javítást.',sid)
  reply=dict(message=dict(content=json.dumps(dict(reply='Ellenőrizhető javaslat.',reads=[],actions=[]))))
  with patch('studio.local_api',return_value=reply) as api:commander.run(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()))
  messages=api.call_args.args[2]['messages'];context=next(m['content'] for m in messages if m.get('content','').startswith('TASK CONTEXT AND METHODS'))
  self.assertIn('project-audit',context);self.assertIn(turn,context)
