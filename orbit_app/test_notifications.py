import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import notifications,telegram_control
class NotificationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  self.s.db.execute('CREATE TABLE IF NOT EXISTS short_runs(id TEXT PRIMARY KEY,project TEXT,query TEXT,data TEXT,created REAL)')
  self.s.db.execute("INSERT INTO short_runs VALUES('r1','universe','ISHOWSPEED best moments','{}',0)");self.s.db.commit()
 def job(self,kind,status,step=None,error=''):
  jid=kind+str(step)+status;payload=dict(run='r1',auto_step=step) if step else dict(run='r1')
  self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,error,payload) VALUES(?,?,?,?,?,?,?,?)',(jid,'universe','a',kind,status,'p',error,json.dumps(payload)));self.s.db.commit()
  return dict(id=jid,kind=kind,project='universe')
 def send(self,*jobs):
  sent=[]
  cfg=dict(mode='local',providers=dict(telegram=dict(notifications=True,chat_id='1')))
  with patch('connections.settings',return_value=cfg),patch('connections.allowed',return_value=True),patch('connections.http',side_effect=lambda *a,**k:sent.append(a[2]['text']) or dict(ok=True)):
   for j in jobs:notifications.notify(self.s,j)
  return sent
 def test_stops_and_failures_never_notify(self):
  sent=self.send(self.job('graph','done','layout'),self.job('command','done'),self.job('media_analysis','done'),self.job('graph','failed','selection','A helyi AI nem válaszolt az időkereten belül.'),
                 self.job('graph','failed'),self.job('youtube_upload','failed',error='quota'))
  self.assertEqual(sent,[])
 def test_any_project_finished_video_is_sent_once(self):
  pid=self.s.create_project('Animációs stúdió')
  j=self.job('graph','done');self.s.db.execute("UPDATE jobs SET project=?,payload=? WHERE id=?",(pid,json.dumps(dict(run='x',story_step='render')),j['id']))
  self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('a1',pid,'The Shadow Entity.mp4','/nope.mp4','video',0,j['id']));self.s.db.commit()
  chat=self.job('command_apply','done');self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('a2','universe','Wan · generált videó.mp4','/nope2.mp4','video',0,chat['id']));self.s.db.commit()
  sent=self.send(j,j,chat)
  self.assertEqual(len(sent),2);self.assertIn('Animációs stúdió',sent[0]);self.assertIn('The Shadow Entity',sent[0])
 def test_finished_video_message(self):
  sent=self.send(self.job('graph','done','verify'))
  self.assertTrue(sent[0].startswith('✅ Elkészült egy új videó'))
 def test_telegram_text_is_clean(self):
  t=telegram_control.tidy('A **misszió** (ID: 64faf0e673cf4ca2b0305bc13a07efaa) fut\n## Állapot\n- egy\n\n\n\nKorábban elkészült: []')
  self.assertEqual(t,'A misszió fut\nÁllapot\n• egy')
if __name__=='__main__':unittest.main()
