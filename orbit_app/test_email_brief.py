import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import commander,email_brief as eb,email_hub as eh
from test_email_hub import FakeBox,FakeServer,raw

def model(payload):return patch('studio.local_api',return_value=dict(message=dict(content=json.dumps(payload,ensure_ascii=False))))

class Case(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  p=patch('connections.ROOT',root);p.start();self.addCleanup(p.stop)
  self.s=Studio(root);self.addCleanup(self.s.db.close);eb.schema(self.s);self.now=time.time()
  self.box=FakeBox({1:raw('Mikor fizetsz?',sender='Anna Kiss <anna@ceg.hu>',body='Kérlek küldd el a számlát péntekig.',when=self.now-5*86400),2:raw('Akciós cipők',sender='shop@bolt.hu',headers={'List-Id':'<x>'},when=self.now-3600),3:raw('Találkozó',sender='Péter <peter@ceg.hu>',body='Jó neked a szerda?',when=self.now-3600)})
  self.server=FakeServer()
  for name,value in (('imap_open',self.box),('smtp_open',self.server)):
   q=patch('email_hub.'+name,return_value=value);q.start();self.addCleanup(q.stop)
  self.aid=dispatch(dict(action='project_app',project='universe',op='email_connect',args=dict(address='en@gmail.com',password='abcd')),self.s)['result']['account']
  eh.sync(self.s,eh.account(self.s,self.aid))
 def op(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']
 def mail(self,subject):return dict(self.s.db.execute('SELECT * FROM emails WHERE subject=?',(subject,)).fetchone())
 def brief(self,items,summary='Két dolog vár rád.'):
  with model(dict(summary=summary,items=items)) as call:out=eb.run(self.s,dict(id='j'))
  return out,call
 def yesterday(self):
  self.s.db.execute('UPDATE command_turns SET created=?',(self.now-3*86400,));self.s.db.commit()
 def chat(self,prompt,session=''):
  r=dispatch(dict(action='command_send',project='universe',prompt=prompt,**{'global':True},session=session),self.s)
  return r,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(r['job'],)).fetchone())

class BriefingTests(Case):
 def test_it_points_at_what_needs_the_owner_and_only_real_letters(self):
  # The owner (3 Nov): on entering, what to do from the mail, or an important letter they forgot.
  self.assertEqual([c['subject'] for c in eb.candidates(self.s)],['Találkozó','Mikor fizetsz?'],'no newsletter')
  out,call=self.brief([dict(email='e1',task='Válaszolj Péternek a szerdáról',why='Választ vár'),dict(email='e2',task='Küldd el a számlát',why='Péntek a határidő'),dict(email='e99',task='Kitalált'),dict(email='e1',task='Kétszer'),dict(task='')])
  sent=call.call_args.args[2];self.assertIn('2 teendő',out);self.assertIs(sent['format'],'json');self.assertIsNone(sent.get('tools'),'the model that reads a letter can do nothing');self.assertIn('untrusted',sent['messages'][0]['content'])
  b=eb.for_chat(self.s,'');self.assertEqual([(i['subject'],i['kind']) for i in b['items']],[('Találkozó','todo'),('Mikor fizetsz?','forgotten')],'days old and unanswered is forgotten');self.assertEqual(b['summary'],'2 dolog vár rád a leveleid alapján.')
 def test_shops_without_list_headers_are_still_adverts(self):
  # 3 Nov, the owner's real mailbox: 18 of 30 candidates were one shop, and they pushed the real letters out.
  self.box.letters[5]=raw('11.11 akció',sender='AliExpress <ae@newarrival.aliexpress.com>',body='Nagy akció! Leiratkozás itt.',when=self.now)
  self.box.letters[6]=raw('Kártyája lejár',sender='Szolgáltató <info@greengo.com>',body='A bankkártyája 30 nap múlva lejár.',when=self.now);eh.sync(self.s,eh.account(self.s,self.aid))
  subjects=[c['subject'] for c in eb.candidates(self.s)];self.assertIn('Kártyája lejár',subjects);self.assertNotIn('11.11 akció',subjects);self.assertEqual(self.mail('11.11 akció')['bulk'],1)
 def test_a_letter_about_pictures_does_not_pick_the_vision_model(self):
  import assist_jobs
  with patch('model_hub.models',return_value=[dict(name='qwen2.5vl:7b',capabilities=['completion','vision']),dict(name='qwen3.5:9b',capabilities=['completion'])]):self.assertEqual(assist_jobs.chat_model(),'qwen3.5:9b')
  with patch('model_hub.models',side_effect=OSError('no server')):self.assertEqual(assist_jobs.chat_model(),'auto')
 def test_what_is_over_stays_off_the_list(self):
  # 3 Nov, the real mailbox: it listed appointments that had passed, and said so itself.
  out,_=self.brief([dict(email='e1',task='Válaszolj Péternek',why='Választ vár'),dict(email='e2',task='Nézd meg a foglalást',why='Az időpont már elmúlt')])
  self.assertEqual([i['task'] for i in eb.for_chat(self.s,'')['items']],['Válaszolj Péternek']);self.assertEqual(eb.for_chat(self.s,'')['summary'],'1 dolog vár rád a leveleid alapján.','the count is ours, so it cannot disagree with the list')
 def test_it_runs_only_on_the_local_model(self):
  self.assertTrue(eb.maybe_queue(self.s,self.now));job=self.s.db.execute("SELECT payload FROM jobs WHERE kind='assist' ORDER BY rowid DESC LIMIT 1").fetchone()[0];self.assertIs(json.loads(job)['local_only'],True)
  self.assertFalse(eb.maybe_queue(self.s,self.now+1),'never twice at once')
 def test_it_is_ready_before_the_owner_looks_but_not_constantly(self):
  self.brief([]);self.s.db.execute("UPDATE jobs SET status='done' WHERE kind='assist'");self.s.db.commit()
  self.assertFalse(eb.maybe_queue(self.s,self.now+10),'nothing new');self.assertFalse(eb.maybe_queue(self.s,self.now+60),'a fresh one stands')
  self.box.letters[4]=raw('Új levél',sender='Béla <bela@ceg.hu>',when=self.now);eh.sync(self.s,eh.account(self.s,self.aid))
  self.assertFalse(eb.maybe_queue(self.s,self.now+60),'new mail, but it waits half an hour');self.assertTrue(eb.maybe_queue(self.s,self.now+eb.MIN_GAP+5))
  self.s.db.execute("UPDATE jobs SET status='done' WHERE kind='assist'");self.s.db.commit();self.brief([])
  self.assertTrue(eb.maybe_queue(self.s,time.time()+eb.STALE+5),'and at least once a day')
 def test_no_mailbox_no_card(self):
  self.op('email_disconnect',account=self.aid);self.assertIsNone(eb.for_chat(self.s,''));self.assertFalse(eb.maybe_queue(self.s,self.now))

class WhenItShowsTests(Case):
 def setUp(self):
  super().setUp();self.brief([dict(email='e1',task='Válaszolj Péternek')])
 def test_it_shows_when_the_owner_has_not_chatted_today_or_starts_a_new_chat(self):
  # The owner: not always, only when they have not chatted that day, or start a new chat.
  self.assertTrue(eb.for_chat(self.s,'earlier')['items'],'no chat today: in the open chat too')
  sid=self.chat('Szia')[0]['session'];self.assertIsNone(eb.for_chat(self.s,sid),'after the first message it steps aside');self.assertIsNone(eb.for_chat(self.s,'earlier'))
  self.assertTrue(eb.for_chat(self.s,'')['items'],'a new chat shows it again')
  self.yesterday();self.assertTrue(eb.for_chat(self.s,sid)['items'],'a chat from yesterday does not count as today')
  self.assertIsNone(eb.for_chat(self.s,None),'other callers never get it')
 def test_it_reaches_the_chat_page(self):
  self.assertTrue(commander.state(self.s,'universe',True,'')['briefing']['items']);self.assertIsNone(commander.state(self.s,'universe',True)['briefing'])
 def test_hidden_is_hidden_until_there_is_news(self):
  b=eb.for_chat(self.s,'');self.op('briefing_dismiss',id=b['id']);self.assertTrue(eb.for_chat(self.s,'')['items'],'a new chat restores even a formerly global dismissal');self.assertIsNone(eb.for_chat(self.s,'earlier'))
  self.brief([dict(email='e1',task='Új elemzés')]);self.assertEqual(eb.for_chat(self.s,'')['items'][0]['task'],'Új elemzés')
 def test_named_empty_chat_gets_reminders_even_after_activity_today(self):
  import chat_sessions
  self.chat('Szia')
  empty=chat_sessions.ensure(self.s,None,'Új chat')
  self.assertTrue(eb.for_chat(self.s,empty)['items'])
 def test_done_and_answered_letters_leave_the_card(self):
  peter=self.mail('Találkozó')['id'];self.op('briefing_done',email=peter);self.assertEqual(eb.for_chat(self.s,'')['items'],[]);self.assertNotIn(peter,[c['id'] for c in eb.candidates(self.s)],'and it does not come back')
 def test_a_letter_answered_from_the_phone_counts_as_answered(self):
  anna=self.mail('Mikor fizetsz?');self.box.sent[9]=('In-Reply-To: '+anna['message_id']+'\r\n\r\n').encode();eh.sync(self.s,eh.account(self.s,self.aid))
  self.assertEqual(self.mail('Mikor fizetsz?')['replied'],1);self.assertEqual([c['subject'] for c in eb.candidates(self.s)],['Találkozó'])
  self.assertEqual(eh.account(self.s,self.aid)['last_sent_uid'],9);self.assertEqual(self.box.folder,'"[Gmail]/Sent Mail"',"the mailbox's own folder name")
 def test_older_mail_arrives_a_little_at_a_time(self):
  self.box.letters[0]=raw('Régi fontos',sender='Zsuzsa <zs@ceg.hu>',when=self.now-20*86400)
  self.box.letters={k:self.box.letters[k] for k in sorted(self.box.letters)};eh.sync(self.s,eh.account(self.s,self.aid))
  self.assertEqual(self.mail('Régi fontos')['sender'],'zs@ceg.hu')

class ChatTests(Case):
 def test_daily_telegram_request_creates_task_instead_of_answering_mail(self):
  prompt='Hozz létre egy automatizált feladatot minden nap reggel 8 ra email átolvasót, ha fontos email van Telegram chatben leírod nekem.'
  _,job=self.chat(prompt)
  with patch('studio.local_api',side_effect=AssertionError('Scheduling must not review mail now')):commander.run(self.s,job)
  turn=self.s.rows('SELECT * FROM command_turns ORDER BY created DESC')[0]
  a=json.loads(turn['actions'])[0]
  self.assertEqual(a['type'],'workflow_automation_save');self.assertEqual(a['automation']['config']['scope'],'global');self.assertEqual(a['automation']['config']['daily_time'],'08:00')
 def test_morning_review_silence_real_results_and_deduplication(self):
  mail=self.mail('Találkozó');state=dict(paired=True,configured=True,enabled=True,owner=dict(chat=7))
  job=dict(id='morning',payload=json.dumps(dict(automation_id='daily')))
  with patch('email_hub.sync'),patch('telegram_control.status',return_value=state),patch('email_brief.ask',return_value=dict(items=[])),patch('telegram_control.out') as send:
   eb.scheduled_review(self.s,job);send.assert_not_called()
  with patch('email_hub.sync'),patch('telegram_control.status',return_value=state),patch('email_brief.ask',return_value=dict(items=[dict(email='e1',task='Válaszolj.',why='Egyeztetés'),dict(email='unknown',task='Invented')])),patch('telegram_control.out') as send:
   eb.scheduled_review(self.s,job);eb.scheduled_review(self.s,job)
   self.assertEqual(send.call_count,2);self.assertEqual(send.call_args_list[0].args[1],send.call_args_list[1].args[1]);self.assertNotIn('Invented',send.call_args.args[3])
 def test_failed_sync_is_not_silently_reported_as_no_important_mail(self):
  with patch('telegram_control.status',return_value=dict(paired=True,configured=True,enabled=True)),patch('email_hub.sync',side_effect=ValueError('Mail offline')),patch('telegram_control.out') as send:
   with self.assertRaisesRegex(ValueError,'Mail offline'):eb.scheduled_review(self.s,dict(id='j',payload='{}'))
   send.assert_not_called()
 def test_exact_user_searches_do_not_ask_a_model_or_deny_email_access(self):
  self.s.db.execute("UPDATE emails SET sender_name='IPON',subject='IPON rendelés' WHERE subject='Találkozó'");self.s.db.commit()
  for prompt,expected in [('keres meg nekem az IPON al kapcsolatos emailjeimet.','IPON rendelés'),('keresd meg nekem az emailjeim között Matuz al való beszélgetéseimet.','teljes postafiókban')]:
   _,job=self.chat(prompt)
   with patch('studio.local_api',side_effect=AssertionError('Literal mail search needs no model')):
    answer=commander.run(self.s,job)
   self.assertIn(expected,answer)
 def run_chat(self,prompt,answer):
  r,job=self.chat(prompt)
  with model(answer) as call:commander.run(self.s,job)
  turn=json.loads(job['payload'])['turn'];return r,turn,dict(self.s.db.execute('SELECT status,response,actions FROM command_turns WHERE id=?',(turn,)).fetchone()),call
 def test_the_assistant_answers_about_the_mail_from_the_mail(self):
  # The owner (3 Nov): the main assistant handles my emails.
  r,turn,row,call=self.run_chat('Mit írt Anna a levelében?',dict(reply='Anna a számlát kéri péntekig.',emails=['e1'],drafts=[]))
  self.assertEqual((row['status'],row['response'],row['actions']),('done','Anna a számlát kéri péntekig.','[]'))
  sent=call.call_args.args[2];body=json.loads(sent['messages'][1]['content']);self.assertEqual(body['letters'][0]['subject'],'Mikor fizetsz?','the letter it talks about comes first');self.assertIsNone(sent.get('tools'))
  self.assertIs(json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(r['job'],)).fetchone()[0])['local_only'],True,'the letters stay on this Mac whatever model the chat is set to')
  cards=commander.state(self.s,'universe',True,r['session'])['turns'][0]['emails'];self.assertEqual([c['subject'] for c in cards],['Mikor fizetsz?'])
 def test_a_reply_written_in_the_chat_waits_for_the_owner(self):
  r,turn,row,call=self.run_chat('Írj választ Annának a levelére, hogy holnap küldöm',dict(reply='A válasz kész, a Küldés gombbal küldheted.',emails=['e1'],drafts=[dict(email='e1',body='Kedves Anna! Holnap küldöm.'),dict(email='e77',body='Kitalált')]))
  self.assertEqual(self.server.sent,[],'nothing is sent from the chat');anna=self.mail('Mikor fizetsz?');self.assertEqual((anna['draft'],anna['draft_state']),('Kedves Anna! Holnap küldöm.','ready'))
  self.assertEqual(commander.state(self.s,'universe',True,r['session'])['turns'][0]['emails'][0]['draft'],'Kedves Anna! Holnap küldöm.')
 def test_the_short_names_stay_out_of_the_answer(self):
  r,turn,row,call=self.run_chat('Van fontos levelem?',dict(reply='Fontos a levele (e1), a többi (e2, e3) nem. Az e2 is ráér.',emails=[],drafts=[]))
  self.assertNotRegex(row['response'],r'\be\d+\b')
 def test_other_requests_go_the_normal_way(self):
  for prompt in ('Építs egy email-küldő alkalmazást','Milyen idő lesz holnap?','Javítsd az email oldalt az appban'):
   self.assertFalse(eb.about_mail(self.s,prompt),prompt)
  for prompt in ('Van fontos levelem?','Nézd át az emailjeimet','Mit írt Anna az emailben?','Mi van a gmailemben?'):
   self.assertTrue(eb.about_mail(self.s,prompt),prompt)
  self.op('email_disconnect',account=self.aid);self.assertFalse(eb.about_mail(self.s,'Van fontos levelem?'),'without a mailbox the assistant answers as before')
 def test_a_broken_model_answer_is_said_plainly(self):
  r,job=self.chat('Van fontos levelem?')
  with patch('studio.local_api',return_value=dict(message=dict(content='nem json'))):commander.run(self.s,job)
  turn=json.loads(job['payload'])['turn'];self.assertIn('helyi modell',self.s.db.execute('SELECT response FROM command_turns WHERE id=?',(turn,)).fetchone()[0])

if __name__=='__main__':unittest.main()
