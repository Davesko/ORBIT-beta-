import os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import missions,storage_guard,venture
class StorageGuardTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  storage_guard._state.update(checked=0,free=None);self.addCleanup(storage_guard._state.update,checked=0,free=None)
 def source(self,pid,name,age):
  d=self.s.root/'projects'/pid/'sources'/name;d.mkdir(parents=True);(d/'source.json').write_text('{}');m=d/'source.mp4';m.write_bytes(b'x'*10)
  os.utime(m,(time.time()-age,)*2);return m
 def test_low_disk_blocks_new_cycles_only(self):
  venture.configure(self.s,dict(enabled=True))
  with patch('storage_guard.free',return_value=1024**3):
   missions.tick(self.s);self.assertFalse(self.s.rows('SELECT id FROM orbit_mission_runs'))
   with self.assertRaises(ValueError):storage_guard.check(self.s)
  storage_guard._state.update(checked=0)
  with patch('storage_guard.free',return_value=100*1024**3):missions.tick(self.s)
  self.assertEqual(len(self.s.rows('SELECT id FROM orbit_mission_runs')),1)
 def test_prune_keeps_manifests_recent_and_busy_projects(self):
  pid=self.s.rows('SELECT id FROM projects')[0]['id']
  old=self.source(pid,'old',4*86400);new=self.source(pid,'new',3600)
  with patch('storage_guard.free',return_value=1024**3):report=storage_guard.maintain(self.s)
  self.assertFalse(old.exists());self.assertTrue(old.with_name('source.json').exists());self.assertTrue(new.exists());self.assertEqual(report['removed_bytes'],10)
  busy=self.source(pid,'busy',4*86400);aid=self.s.rows('SELECT id FROM agents WHERE project=?',(pid,))[0]['id'];self.s.enqueue(aid,'work','chat')
  with patch('storage_guard.free',return_value=1024**3):storage_guard.maintain(self.s)
  self.assertTrue(busy.exists())
 def test_no_pruning_with_enough_space(self):
  pid=self.s.rows('SELECT id FROM projects')[0]['id'];old=self.source(pid,'old',9*86400)
  with patch('storage_guard.free',return_value=100*1024**3):storage_guard.maintain(self.s)
  self.assertTrue(old.exists())
 def test_keep_awake_follows_active_objectives(self):
  class Proc:
   def __init__(self,*a,**k):self.done=None
   def poll(self):return self.done
   def terminate(self):self.done=0
  missions.schema(self.s);storage_guard._state['awake']=None
  with patch('subprocess.Popen',side_effect=Proc) as popen:
   self.assertFalse(storage_guard.keep_awake(self.s));popen.assert_not_called()
   venture.configure(self.s,dict(enabled=True));self.assertTrue(storage_guard.keep_awake(self.s));storage_guard.keep_awake(self.s);self.assertEqual(popen.call_count,1)
   proc=storage_guard._state['awake'];venture.configure(self.s,dict(enabled=False));storage_guard.keep_awake(self.s);self.assertEqual(proc.done,0);self.assertIsNone(storage_guard._state['awake'])
if __name__=='__main__':unittest.main()
