import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from commander import schema,prepare,safe_path,approve,apply,state,queue

class CommandTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name)/'orbit');self.addCleanup(self.s.db.close);schema(self.s);self.base=self.s.root/'projects/universe';self.base.mkdir(parents=True,exist_ok=True)
 def turn(self,actions):
  prepared=prepare(self.s,'universe',actions);self.s.db.execute('INSERT INTO command_turns VALUES(?,?,?,?,?,?,?,?,?)',('turn','universe','request','test','Proposed',json.dumps(prepared),'review','',0));self.s.db.commit();return prepared
 def run_turn(self):
  jid=approve(self.s,'universe','turn');job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone());return apply(self.s,job)
 def test_paths_cannot_escape_via_parent_or_symlink(self):
  with self.assertRaises(ValueError):safe_path(self.s,str(self.base/'../../../outside'))
  (self.base/'link').symlink_to(self.tmp.name)
  with self.assertRaises(ValueError):safe_path(self.s,str(self.base/'link/secret.txt'))
 def test_review_does_not_write_until_approved_and_keeps_backup(self):
  p=self.base/'note.txt';p.write_text('before\n');plan=self.turn([dict(type='write_file',path=str(p),content='after\n')]);self.assertIn('-before',plan[0]['diff']);self.assertEqual(p.read_text(),'before\n')
  self.run_turn();self.assertEqual(p.read_text(),'after\n');self.assertEqual((self.s.root/'backups/commander/turn/0-note.txt').read_text(),'before\n')
  with self.assertRaises(ValueError):approve(self.s,'universe','turn')
 def test_stale_file_change_is_preserved(self):
  p=self.base/'note.txt';p.write_text('before');self.turn([dict(type='write_file',path=str(p),content='after')]);p.write_text('user change')
  with self.assertRaises(ValueError):self.run_turn()
  self.assertEqual(p.read_text(),'user change')
 def test_access_revocation_invalidates_prepared_write(self):
  outside=Path(self.tmp.name)/'work';outside.mkdir();self.s.db.execute('INSERT INTO command_roots VALUES(?,?)',(str(outside),0));self.s.db.commit();self.turn([dict(type='write_file',path=str(outside/'new.txt'),content='text')]);self.s.db.execute('DELETE FROM command_roots');self.s.db.commit()
  with self.assertRaises(ValueError):self.run_turn()
  self.assertFalse((outside/'new.txt').exists())
 def test_approved_command_and_audit(self):
  self.turn([dict(type='run_command',cwd=str(self.base),command="printf 'verified'")]);self.run_turn();self.assertTrue(any(a['label']=='Parancskimenet' and a['detail']=='verified' for a in state(self.s,'universe')['audit']))
 def test_chat_can_build_and_schedule_a_new_project(self):
  def agent(aid):return dict(id=aid,name=aid,role='Writer',room='bridge',model='qwen2.5:14b',tools=['project_files','read_file','write_file'],prompt='Work on the project',interval=0,color='#81ffc1')
  self.turn([dict(type='project_create',name='Built from chat',description='test'),dict(type='agent_save',agent=agent('writer-one')),dict(type='agent_save',agent=agent('writer-two')),dict(type='recipe_save',name='Daily work',agents=['writer-one','writer-two'],prompt='Review the project and write a report',interval=180)])
  self.run_turn();pid=self.s.db.execute("SELECT id FROM projects WHERE name='Built from chat'").fetchone()[0]
  self.assertEqual(self.s.agent('writer-one')['project'],pid)
  recipe=self.s.db.execute('SELECT * FROM recipes WHERE project=?',(pid,)).fetchone();self.assertEqual(recipe['interval'],180)

 def test_global_chat_can_target_another_owned_project(self):
  pid=self.s.create_project('Other target','test')
  a=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,))[0]
  agent=self.s.agent(a['id']);agent['role']='Updated from global chat'
  self.turn([dict(type='agent_save',project=pid,agent=agent)]);self.run_turn()
  self.assertEqual(self.s.agent(a['id'])['role'],'Updated from global chat')

 def test_rejected_plan_cannot_execute(self):
  self.turn([]);self.s.db.execute("UPDATE command_turns SET status='rejected'");self.s.db.commit()
  with self.assertRaises(ValueError):approve(self.s,'universe','turn')
if __name__=='__main__':unittest.main()
