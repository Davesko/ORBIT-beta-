import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import telegram_control as tg
class TelegramTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name)/'orbit');self.addCleanup(self.s.db.close);tg.schema(self.s)
 def message(self,uid=1,user=123,text='Hello',kind='private'):
  return dict(update_id=uid,message=dict(chat=dict(id=user,type=kind),**{'from':dict(id=user)},text=text))
 def pair(self):
  with patch('telegram_control.api',return_value=dict(username='orbit_test_bot')):link=tg.pair(self.s)['url']
  tg.ingest(self.s,self.message(text='/start '+link.split('=')[1]));return link
 def test_unpaired_and_group_messages_cannot_execute(self):
  tg.ingest(self.s,self.message());self.assertEqual(self.s.db.execute('select count(*) from telegram_inbox').fetchone()[0],0)
  self.pair();tg.ingest(self.s,self.message(2,999,'steal everything'));tg.ingest(self.s,self.message(3,123,'command','group'))
  self.assertEqual(self.s.db.execute('select count(*) from telegram_inbox').fetchone()[0],0)
 def test_single_use_pairing_and_replay_dedup(self):
  link=self.pair();tg.ingest(self.s,self.message(2,999,'/start '+link.split('=')[1]));self.assertEqual(self.s.db.execute('select chat from telegram_owner').fetchone()[0],123)
  tg.ingest(self.s,self.message(3));tg.ingest(self.s,self.message(3));self.assertEqual(self.s.db.execute('select count(*) from telegram_inbox').fetchone()[0],1)
 def test_agent_messages_keep_original_project_and_target(self):
  self.pair();agent=self.s.rows('select id from agents where project=?',('universe',))[0]['id'];self.s.db.execute('update telegram_owner set target=?',(agent,));self.s.db.commit()
  tg.ingest(self.s,self.message(2,text='Do this'));row=self.s.rows('select * from telegram_inbox')[0]
  reply,jid=tg.dispatch(self.s,row);self.assertTrue(jid)
  _,again=tg.dispatch(self.s,row);self.assertEqual(jid,again)
  payload=json.loads(self.s.db.execute('select payload from jobs where id=?',(jid,)).fetchone()[0]);self.assertEqual(payload['telegram_update'],2)
 def test_today_command_answers_without_starting_work(self):
  self.pair();tg.ingest(self.s,self.message(2,text='/ma'));row=self.s.rows('select * from telegram_inbox')[0]
  reply,jid=tg.dispatch(self.s,row)
  self.assertTrue(reply.startswith('📋 ORBIT ma'));self.assertIsNone(jid,'a summary starts no job')
 def test_revocation_disables_pending_control(self):
  self.pair();tg.ingest(self.s,self.message(2));tg.unpair(self.s);self.assertFalse(tg.status(self.s)['paired']);self.assertEqual(self.s.db.execute('select status from telegram_inbox').fetchone()[0],'revoked')
 def test_uncertain_send_is_not_blindly_duplicated(self):
  self.pair()
  with patch('telegram_control.api',side_effect=ValueError('network')):tg.process(self.s)
  self.assertEqual(self.s.db.execute('select status from telegram_outbox').fetchone()[0],'uncertain')
  with patch('telegram_control.api') as send:tg.process(self.s);send.assert_not_called()
