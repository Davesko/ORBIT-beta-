import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import housekeeping
class HousekeepingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
 def test_keeps_newest_deploy_backups_and_other_backups(self):
  b=self.s.root/'backups'
  for i in range(14):(b/('deploy-2026103%02d-x'%i)).mkdir(parents=True)
  (b/'before-important').mkdir()
  self.assertEqual(housekeeping.prune_deploy_backups(self.s.root),4)
  left=sorted(p.name for p in b.iterdir());self.assertIn('before-important',left);self.assertIn('deploy-202610313-x',left);self.assertNotIn('deploy-202610300-x',left)
 def test_trims_only_oversized_logs_keeping_the_tail(self):
  logs=self.s.root/'logs';logs.mkdir(exist_ok=True)
  big=logs/'ssd-models.err.log';big.write_bytes((b'x'*99+b'\n')*300000+b'LAST LINE\n');(logs/'small.log').write_text('ok')
  handle=open(big,'ab')  # a running service keeps writing to the same file
  self.assertEqual(housekeeping.trim_logs(self.s.root),['ssd-models.err.log'])
  self.assertLessEqual(big.stat().st_size,housekeeping.LOG_KEEP);self.assertTrue(big.read_bytes().endswith(b'LAST LINE\n'));self.assertEqual((logs/'small.log').read_text(),'ok')
  handle.write(b'AFTER TRIM\n');handle.close();self.assertTrue(big.read_bytes().endswith(b'AFTER TRIM\n'),'the service still writes into the visible log')
 def test_unused_models_are_reported_not_deleted(self):
  now=time.time()
  self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,created,payload) VALUES(?,?,?,?,?,?,?,?)',('j','u','a','chat','done','p',now-3600,json.dumps(dict(selected_model='qwen3.5:9b'))));self.s.db.commit()
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b',size=7e9,storage='SSD'),dict(name='qwen2.5:14b',size=9e9,storage='SSD'),dict(name='qwen3-embedding:0.6b',size=6e8,storage='SSD')]):
   idle=housekeeping.unused_models(self.s,now)
  self.assertEqual([m['name'] for m in idle],['qwen2.5:14b'])
 def test_daily_pass_quarantines_manifest_sidecars(self):
  store=self.s.root/'ssd/ollama';(store/'manifests-v2/ollama.com/library/qwen3.5').mkdir(parents=True)
  (self.s.root/'model-storage.json').write_text(json.dumps(dict(ollama=str(store))))
  meta=store/'manifests-v2/ollama.com/library/qwen3.5/._9b';meta.write_bytes(b'\x00\x05\x16\x07'+b'\x00'*80)
  model=store/'manifests-v2/ollama.com/library/qwen3.5/9b';model.write_text('{}')
  self.assertEqual(housekeeping.repair_sidecars(self.s.root),1)
  self.assertFalse(meta.exists());self.assertTrue(model.exists());self.assertEqual(len(list((self.s.root/'backups').rglob('._9b'))),1)
 def test_week_old_blocked_steps_are_closed_and_nothing_is_deleted(self):
  pid=self.s.create_project('P');aid=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,))[0]['id']
  old=self.s.enqueue(aid,'old');new=self.s.enqueue(aid,'new');now=time.time()
  self.s.db.execute("UPDATE jobs SET status='blocked',created=? WHERE id=?",(now-8*86400,old))
  self.s.db.execute("UPDATE jobs SET status='blocked' WHERE id=?",(new,));self.s.db.commit()
  self.assertEqual(housekeeping.close_stale_blocked(self.s,now),1)
  self.assertEqual([r[0] for r in self.s.db.execute('SELECT status FROM jobs WHERE id IN (?,?) ORDER BY created',(old,new))],['cancelled','blocked'])
if __name__=='__main__':unittest.main()
