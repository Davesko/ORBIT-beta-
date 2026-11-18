import json,tempfile,unittest
from pathlib import Path
from youtube import needs_reconnect
class ReconnectAttentionTests(unittest.TestCase):
 def project(self,root,pid,connected,auth=None,client=True):
  d=Path(root)/'integrations/youtube'/pid;d.mkdir(parents=True)
  if client:(d/'client.json').write_text('{}')
  (d/'status.json').write_text(json.dumps(dict(connected=connected)))
  if auth is not None:(d/'auth.json').write_text(json.dumps(auth))
 def test_only_lost_logins_need_the_owner(self):
  with tempfile.TemporaryDirectory() as root:
   self.project(root,'revoked',False,dict(status='failed',error='A YouTube-belépés lejárt'))
   self.project(root,'fine',True,dict(status='done'))
   self.project(root,'left',False)  # a deliberate disconnect removes auth.json
   self.project(root,'noclient',False,dict(status='failed',error='x'),client=False)
   self.assertEqual([x['project'] for x in needs_reconnect(root)],['revoked'])
   self.assertIn('lejárt',needs_reconnect(root)[0]['error'])
if __name__=='__main__':unittest.main()
