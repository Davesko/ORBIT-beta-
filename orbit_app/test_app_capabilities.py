import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from clip_farm import configure,PROJECT,start_research
from app_capabilities import roles,status,assign_role,project_capabilities
from autonomous import role_agents

class CapabilityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.translation=patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts));self.translation.start();self.addCleanup(self.translation.stop)
  self.s=Studio(Path(self.temp.name));self.addCleanup(self.s.db.close);configure(self.s)
 def test_renames_and_custom_role_titles_preserve_execution_bindings(self):
  original=roles(self.s,PROJECT)
  for i,aid in enumerate(original.values()):
   agent=self.s.agent(aid);agent.update(name='Saját '+str(i),role='Egyéni '+str(i));self.s.save_agent(agent)
  self.assertEqual(roles(self.s,PROJECT),original)
  self.assertEqual(role_agents(self.s,PROJECT)['source'],original['source'])
  started=start_research(self.s,PROJECT,'Gaming events');job=self.s.db.execute('SELECT agent FROM jobs WHERE id=?',(started['job'],)).fetchone();self.assertEqual(job['agent'],original['research'])
  self.assertEqual(len(self.s.snapshot(PROJECT)['capabilities']['chain']),9)
 def test_archive_does_not_silently_replace_bound_role_and_rebinding_is_explicit(self):
  original=roles(self.s,PROJECT);aid=original['source'];self.s.db.execute('INSERT INTO agent_archive VALUES(?,?,?,?)',(aid,PROJECT,'{}',__import__('time').time()));self.s.db.commit()
  self.assertIn('Forrásgyűjtés',project_capabilities(self.s,PROJECT)['missing_roles'])
  replacement=self.s.save_agent(dict(project=PROJECT,name='Új forrásgyűjtő',role='Kutató',room='research',tools=['find_stream_clips','download_stream_clip']))
  self.assertNotIn('source',roles(self.s,PROJECT));assign_role(self.s,PROJECT,'source',replacement)
  self.assertEqual(role_agents(self.s,PROJECT)['source'],replacement)
  with self.assertRaises(ValueError):assign_role(self.s,PROJECT,'source',original['render'])
 def test_live_system_question_uses_actual_state_without_model_or_actions(self):
  from commander import enqueue
  jid=enqueue(self.s,PROJECT,'Mi fut most?','auto',global_mode=True)
  with patch('studio.local_api',side_effect=AssertionError('No model should invent app facts')):self.s.run_next(('command',))
  row=self.s.db.execute('SELECT status,response,actions FROM command_turns WHERE job=?',(jid,)).fetchone()
  self.assertEqual(row['status'],'done');self.assertEqual(json.loads(row['actions']),[]);self.assertIn('Clip Farm',row['response'])
  self.assertIn('capabilities',status(self.s)['projects'][-1])
