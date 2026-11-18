import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import clip_farm,growth,missions,project_apps,project_trash,telegram_control

class ProjectTrashTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  self.pid=self.s.create_project('Kísérlet','Próba')
  self.s.safe_path(self.pid,'workspace/notes.md').parent.mkdir(parents=True,exist_ok=True);self.s.safe_path(self.pid,'workspace/notes.md').write_text('x')
  self.millions=patch('project_apps.MILLIONS',Path(self.tmp.name)/'ReszvenyAI');self.millions.start();self.addCleanup(self.millions.stop)
 def call(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']
 def names(self):return [p['name'] for p in self.call('project_list')['projects']]
 def test_a_project_can_be_renamed(self):
  # The owner (2 Nov): projects can be deleted, added and their names edited.
  self.call('project_edit',target=self.pid,name='Új név',description='Más');p=self.s.project(self.pid)
  self.assertEqual((p['name'],p['description']),('Új név','Más'));self.assertIn('Új név',self.names())
  self.call('project_edit',target=self.pid,name='Még újabb');self.assertEqual(self.s.project(self.pid)['description'],'Más','left out, it stays')
  with self.assertRaisesRegex(ValueError,'Már van'):self.call('project_edit',target=self.pid,name='saját UNIVERZUM')
  with self.assertRaises(ValueError):self.call('project_edit',target=self.pid,name='  ')
 def test_deleting_is_recoverable_and_leaves_the_files(self):
  out=self.call('project_trash',target=self.pid);self.assertIn('kukába',out['message'])
  self.assertNotIn('Kísérlet',self.names());self.assertEqual([p['name'] for p in self.call('project_list')['trash']],['Kísérlet'])
  self.assertTrue((self.s.root/'projects'/self.pid/'workspace/notes.md').exists())
  self.assertEqual(len(self.s.rows('SELECT id FROM agents WHERE project=?',(self.pid,))),3,'the team waits in the trash')
  with self.assertRaises(ValueError):self.s.project(self.pid)
  self.assertIn('kikapcsolva',self.call('project_restore',target=self.pid)['message'])
  self.assertEqual(self.s.project(self.pid)['name'],'Kísérlet');self.assertEqual(self.call('project_list')['trash'],[])
 def test_deleting_stops_what_would_start_later(self):
  from automations import save,listing
  aid=self.s.rows('SELECT id FROM agents WHERE project=?',(self.pid,))[0]['id']
  save(self.s,self.pid,dict(name='Óránként',kind='agent',config=dict(agent=aid,prompt='x'),enabled=True,interval=60))
  self.s.db.execute('UPDATE agents SET interval=30 WHERE id=?',(aid,))
  growth.schema(self.s);self.s.db.execute('INSERT INTO growth_settings VALUES(?,?,?)',(self.pid,json.dumps(dict(enabled=True,other=1)),0))
  telegram_control.schema(self.s);self.s.db.execute('INSERT INTO telegram_owner VALUES(1,1,?,?)',(self.pid,'assistant'));self.s.db.commit()
  out=self.call('project_trash',target=self.pid);self.assertEqual(out['stopped'],3)
  self.assertEqual(self.s.db.execute('SELECT enabled FROM automations WHERE project=?',(self.pid,)).fetchone()[0],0)
  self.assertEqual(self.s.db.execute('SELECT interval FROM agents WHERE id=?',(aid,)).fetchone()[0],0)
  self.assertEqual(json.loads(self.s.db.execute('SELECT data FROM growth_settings').fetchone()[0]),dict(enabled=False,other=1))
  self.assertEqual(self.s.db.execute('SELECT project FROM telegram_owner').fetchone()[0],'universe','Telegram does not keep pointing at it')
  import automations
  automations.tick(self.s)
  self.call('project_restore',target=self.pid)
  self.assertFalse(listing(self.s,self.pid)['automations'][0]['enabled'],'a restored project starts nothing by itself')
 def test_what_cannot_be_deleted_says_why(self):
  for pid,why in (('universe','alapprojekt'),):
   with self.assertRaisesRegex(ValueError,why):self.call('project_trash',target=pid)
  self.assertEqual(self.s.project('universe')['id'],'universe')
  listed={p['id']:p for p in self.call('project_list')['projects']};self.assertTrue(listed['universe']['protected']);self.assertFalse(listed[self.pid]['protected'])
  job=self.s.enqueue(self.s.rows('SELECT id FROM agents WHERE project=?',(self.pid,))[0]['id'],'x','chat')
  with self.assertRaisesRegex(ValueError,'1 munka fut'):self.call('project_trash',target=self.pid)
  self.assertEqual(self.call('project_list')['projects'][-1]['busy'],1)
  self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(job,))
  missions.schema(self.s);self.s.db.execute("INSERT INTO orbit_missions(id,project,name,goal,spec,status) VALUES('m','universe','Küldetés','g',?,'active')",(json.dumps(dict(nodes=[dict(project=self.pid)])),));self.s.db.commit()
  with self.assertRaisesRegex(ValueError,'Küldetés'):self.call('project_trash',target=self.pid)
  self.s.db.execute("UPDATE orbit_missions SET status='draft'");self.s.db.commit();self.call('project_trash',target=self.pid)
 def test_millions_must_be_switched_off_first(self):
  # Its workers run on their own: without the row the owner would have no switch left to stop them.
  trading=self.s.create_project('Labor','',kind='trading');root=project_apps.MILLIONS;(root/'core').mkdir(parents=True);(root/'core'/'ui_bridge.py').write_text('')
  with self.assertRaisesRegex(ValueError,'fő kapcsolójával'):self.call('project_trash',target=trading)
  (root/'power.json').write_text(json.dumps(dict(on=True)))
  with self.assertRaisesRegex(ValueError,'fő kapcsolójával'):self.call('project_trash',target=trading)
  (root/'power.json').write_text(json.dumps(dict(on=False)));self.call('project_trash',target=trading)
 def test_emptying_the_trash_asks_for_the_name_and_leaves_others_alone(self):
  other=self.s.create_project('Másik','');aid=self.s.rows('SELECT id FROM agents WHERE project=?',(self.pid,))[0]['id']
  job=self.s.enqueue(aid,'x','chat');self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(job,))
  self.s.db.commit()
  with self.assertRaisesRegex(ValueError,'nincs a kukában'):self.call('project_purge',target=self.pid,confirm='Kísérlet')
  self.call('project_trash',target=self.pid)
  for wrong in ('kísérlet','',None):
   with self.assertRaisesRegex(ValueError,'nevét'):self.call('project_purge',target=self.pid,confirm=wrong)
  self.assertTrue((self.s.root/'projects'/self.pid).exists())
  self.call('project_purge',target=self.pid,confirm='Kísérlet')
  self.assertFalse((self.s.root/'projects'/self.pid).exists())
  for table in ('agents','jobs','events','rooms'):
   self.assertEqual(self.s.db.execute('SELECT count(*) FROM '+table+' WHERE project=?',(self.pid,)).fetchone()[0],0,table)
  self.assertEqual(len(self.s.rows('SELECT id FROM agents WHERE project=?',(other,))),3);self.assertEqual(self.call('project_list')['trash'],[])
  with self.assertRaises(ValueError):self.call('project_restore',target=self.pid)
 def test_a_deleted_builtin_project_does_not_come_back(self):
  clip_farm.configure(self.s);self.assertEqual(clip_farm.configure(self.s)['created'],False)
  self.call('project_trash',target=clip_farm.PROJECT);self.assertFalse(clip_farm.configure(self.s)['created'])
  self.assertNotIn('Clip Farm',self.names())
  self.call('project_purge',target=clip_farm.PROJECT,confirm='Clip Farm');self.assertFalse(clip_farm.configure(self.s)['created'],'not after emptying the trash either')
 def test_the_background_stays_healthy_without_the_project(self):
  import gta6
  clip_farm.configure(self.s);gta6._checked['at']=0;gta6.tick(self.s);self.call('project_trash',target=clip_farm.PROJECT)
  gta6._checked['at']=0;self.assertFalse(gta6.tick(self.s))
  import automations
  automations.tick(self.s);self.s.snapshot('universe')
  self.assertNotIn(clip_farm.PROJECT,[p['id'] for p in self.s.rows('SELECT id FROM projects')])
 def test_only_the_owner_window_can_delete(self):
  source=(Path(project_trash.__file__).parent/'commander.py').read_text()
  for op in project_apps.PROJECT_OPS:self.assertNotIn(op,source,'the assistant has no such action')
  self.assertNotIn("'project_app'",source)
  web=Path(project_trash.__file__).parent/'web'
  self.assertIn('manageProjects',(web/'index.html').read_text());self.assertIn('projects_ui.js',(web/'index.html').read_text())
  self.assertEqual(project_apps.describe(self.s,self.pid)['app'],'workspace','project management is separate from the workspace')

if __name__=='__main__':unittest.main()
