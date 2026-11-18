import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import commander,first_run,model_finder

MAC=dict(chip='Apple M4',ram_gb=16,usable_gb=10.0,bandwidth=120,disk_free_gb=100.0,disk='Belső lemez',needs_disk=False)

class FirstRunTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);self.s=Studio(root);self.addCleanup(self.s.db.close)
  for p in (patch('connections.ROOT',root),patch('model_hub.ROOT',root),patch('model_finder.machine',return_value=MAC),patch('model_hub.models',return_value=[]),patch('model_hub.inventory',return_value=([],[dict(port=11434,available=False)]))):
   p.start();self.addCleanup(p.stop)
 def op(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']
 def test_a_new_user_is_welcomed_once_and_told_what_is_missing(self):
  st=self.op('setup_status');self.assertEqual((st['done'],st['models'],st['ollama'],st['cloud']),(False,0,False,False))
  self.op('setup_finish',name=' Anna ');self.assertTrue(self.op('setup_status')['done'])
  row=dict(self.s.db.execute("SELECT content,kind,source FROM assistant_memory WHERE key='user-name'").fetchone());self.assertEqual(row,dict(content='The user is called Anna.',kind='identity',source='manual'))
 def test_someone_already_using_it_gets_no_welcome(self):
  commander.enqueue(self.s,'universe','szia',global_mode=True);self.assertTrue(self.op('setup_status')['done'])
 def test_a_fresh_install_is_not_the_owners_workshop(self):
  names={r['id'] for r in self.s.rows('SELECT id FROM projects')}-{'millions'};self.assertEqual(names,{'universe'},'no Clip Farm or Autopilot lab on a new Mac; MiLLIONS only where it is installed')
 def test_the_packaged_list_holds_every_new_module(self):
  source=(Path(first_run.__file__).parent/'install.py').read_text()
  for name in ('first_run.py','email_hub.py','model_finder.py','memory_brain.py','assist_jobs.py','canvas.py','chat_sessions.py'):self.assertIn("'"+name+"'",source,name)

if __name__=='__main__':unittest.main()
