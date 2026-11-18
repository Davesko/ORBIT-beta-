import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import self_heal
class SelfHealTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
 def test_restarts_dead_model_server_after_three_checks_once_per_half_hour(self):
  now=time.time()
  with patch('self_heal.mounted',return_value=True),patch('self_heal.model_alive',return_value=False),patch('self_heal.restart_models',return_value=True) as r:
   for i in range(3):self_heal.tick(self.s,now+i*60)
   self.assertEqual(r.call_count,1)
   for i in range(3,8):self_heal.tick(self.s,now+i*60)
   self.assertEqual(r.call_count,1,'rate limited')
  self.assertIn('újraindítva',self_heal.summary(self.s)['last_event']['text'])
 def test_no_restart_when_ssd_missing_or_server_fine(self):
  with patch('self_heal.mounted',return_value=False),patch('self_heal.restart_models') as r:
   for i in range(5):self_heal.tick(self.s)
  r.assert_not_called()
 def test_stuck_lab_job_is_released_as_retryable(self):
  old=time.time()-4000
  self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,started,payload) VALUES(?,?,?,?,?,?,?,?)',('j1','orbit-business-lab','a','mission_agent','running','p',old,'{}'))
  self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,started,payload) VALUES(?,?,?,?,?,?,?,?)',('j2','universe','a','graph','running','p',old,'{}'));self.s.db.commit()
  with patch('self_heal.mounted',return_value=False),patch('self_heal.restart_worker') as restart:self_heal.tick(self.s)
  restart.assert_called_once()
  self.assertFalse(self_heal.restart_worker({}),'never signals a process other than the worker')
  self.assertEqual(self.s.db.execute("SELECT status FROM jobs WHERE id='j1'").fetchone()[0],'failed')
  self.assertEqual(self.s.db.execute("SELECT status FROM jobs WHERE id='j2'").fetchone()[0],'running','video work is never touched')
  self.assertIn('beragadt',self.s.db.execute("SELECT error FROM jobs WHERE id='j1'").fetchone()[0].casefold())
if __name__=='__main__':unittest.main()
