import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import canvas,chat_sessions,commander

class CanvasCase(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.s=Studio(Path(tmp.name));self.addCleanup(self.s.db.close);commander.schema(self.s)
  self.folder=canvas.creations_folder(self.s);(self.folder/'snake').mkdir(parents=True)
  self.path=self.folder/'snake'/'index.html';self.path.write_text('<canvas></canvas>')
  self.s.db.execute("INSERT INTO artifacts VALUES('a1','universe','index.html',?,'text',1,'j')",(str(self.path),));self.s.db.commit()
 def op(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']

class FileTests(CanvasCase):
 def test_a_file_opens_edits_and_undoes(self):
  # The owner (3 Nov): the main chat shows the code or the requested work next to the conversation.
  f=self.op('canvas_read',id='a1');self.assertEqual((f['language'],f['content'],f['version'],f['can_undo'],f['previewable']),('html','<canvas></canvas>',1,False,True))
  f=self.op('canvas_save',id='a1',content='<p>új</p>');self.assertEqual((f['version'],f['can_undo'],self.path.read_text()),(2,True,'<p>új</p>'))
  self.assertEqual(self.op('canvas_save',id='a1',content='<p>új</p>')['version'],2,'no change, no new version')
  f=self.op('canvas_undo',id='a1');self.assertEqual((f['content'],f['version'],f['can_undo']),('<canvas></canvas>',1,False))
  with self.assertRaisesRegex(ValueError,'korábbi'):self.op('canvas_undo',id='a1')
 def test_only_text_files_the_app_knows_open(self):
  self.s.db.execute("INSERT INTO artifacts VALUES('v1','universe','clip.mp4',?,'video',1,'j')",(str(self.path),));self.s.db.commit()
  for bad in ('v1','nincs',None):
   with self.assertRaises(ValueError):self.op('canvas_read',id=bad)
  self.path.unlink()
  with self.assertRaisesRegex(ValueError,'nincs a helyén'):self.op('canvas_read',id='a1')
 def test_the_big_and_the_binary_stay_out(self):
  with patch('canvas.LIMIT',5):
   with self.assertRaisesRegex(ValueError,'túl nagy'):self.op('canvas_read',id='a1')
  self.path.write_bytes(b'\xff\xfe\x00bad')
  with self.assertRaisesRegex(ValueError,'nem szöveges'):self.op('canvas_read',id='a1')
 def test_it_opens_outside_on_the_owners_click(self):
  with patch('canvas.subprocess.run') as run:self.op('canvas_open',id='a1')
  self.assertEqual(run.call_args.args[0],['/usr/bin/open',str(self.path)])
 def test_only_new_work_in_the_creations_folder_skips_review(self):
  inside=dict(type='write_file',path=str(self.folder/'poem'/'vers.md'),content='x')
  self.assertTrue(canvas.is_creation(self.s,inside))
  for bad in (dict(inside,path=str(self.folder/'x.command')),dict(inside,path=str(self.s.root/'projects'/'universe'/'other.md')),dict(inside,path=str(self.folder)+'/../../../../etc.md'),dict(type='run_command',command='rm -rf /'),dict(inside,path='/tmp/x.md')):
   self.assertFalse(canvas.is_creation(self.s,bad),bad)

class ChatFlowTests(CanvasCase):
 def test_a_written_file_shows_up_in_its_chat(self):
  target=self.folder/'vers'/'vers.md'
  turn='t1';self.s.db.execute("INSERT INTO command_turns VALUES('t1','universe','írj verset','auto','','[]','done','job1',1)");self.s.db.execute("INSERT INTO command_global VALUES('t1')")
  actions=commander.prepare(self.s,'universe',[dict(type='write_file',path=str(target),content='Vers')],True)
  self.s.db.execute('UPDATE command_turns SET actions=?,status=? WHERE id=?',(json.dumps(actions),'queued_apply',turn));self.s.db.commit()
  agent=self.s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()[0]
  jid=self.s.enqueue(agent,'x','command_apply',payload=dict(turn=turn));self.s.db.execute('UPDATE command_turns SET job=? WHERE id=?',(jid,turn));self.s.db.commit()
  commander._apply(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  self.assertEqual(target.read_text(),'Vers');files=[a for a in commander.state(self.s,'universe',True)['turns'][0]['artifacts'] if a['kind']=='text']
  self.assertEqual([(a['name'],a['project']) for a in files],[('vers.md','universe')]);self.assertIn('Elkészült: vers.md',self.s.db.execute("SELECT response FROM command_turns WHERE id='t1'").fetchone()[0]);self.assertEqual(self.op('canvas_read',id=files[0]['id'])['language'],'markdown')
 def test_what_the_assistant_changes_can_be_undone(self):
  # The file exists, is registered, and the assistant writes over it.
  self.s.db.execute("INSERT INTO command_turns VALUES('t2','universe','javítsd','auto','','[]','done','job2',1)");self.s.db.execute("INSERT INTO command_global VALUES('t2')")
  actions=commander.prepare(self.s,'universe',[dict(type='write_file',path=str(self.path),content='<p>javított</p>')],True)
  self.s.db.execute('UPDATE command_turns SET actions=?,status=? WHERE id=?',(json.dumps(actions),'queued_apply','t2'))
  agent=self.s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()[0]
  jid=self.s.enqueue(agent,'x','command_apply',payload=dict(turn='t2'));self.s.db.execute("UPDATE command_turns SET job=? WHERE id='t2'",(jid,));self.s.db.commit()
  commander._apply(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  got=self.op('canvas_read',id='a1');self.assertEqual((got['content'],got['version'],got['can_undo']),('<p>javított</p>',2,True))
  self.assertEqual(self.op('canvas_undo',id='a1')['content'],'<canvas></canvas>')
  self.assertEqual([a['id'] for a in commander.state(self.s,'universe',True)['turns'][0]['artifacts'] if a['kind']=='text'],['a1'],'it shows up in the chat that changed it')
 def test_a_new_app_is_named_after_its_folder(self):
  self.s.db.execute("INSERT INTO command_turns VALUES('t3','universe','építs','auto','','[]','done','job3',1)")
  target=self.folder/'tetris'/'index.html';actions=commander.prepare(self.s,'universe',[dict(type='write_file',path=str(target),content='x')],True)
  self.s.db.execute('UPDATE command_turns SET actions=?,status=? WHERE id=?',(json.dumps(actions),'queued_apply','t3'))
  agent=self.s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()[0]
  jid=self.s.enqueue(agent,'x','command_apply',payload=dict(turn='t3'));self.s.db.execute("UPDATE command_turns SET job=? WHERE id='t3'",(jid,));self.s.db.commit()
  commander._apply(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  self.assertEqual(self.s.db.execute('SELECT name FROM artifacts WHERE path=?',(str(target),)).fetchone()[0],'tetris/index.html')
 def test_the_open_file_goes_with_the_request(self):
  # 3 Nov: with a cloud model's size limit the context was cut and it asked which file was meant.
  sent=[]
  def fake(service,route,data=None,timeout=8):
   sent.append(data);return dict(message=dict(content=json.dumps(dict(reply='Rendben.',reads=[],actions=[]))))
  jid=commander.enqueue(self.s,'universe','Javítsd ki',global_mode=True,open_file='a1')
  self.assertEqual(json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['route']['task'],'code','changing a file needs a long answer')
  with patch('studio.local_api',side_effect=fake),patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):commander.run(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  messages=sent[0]['messages'];user=next(m['content'] for m in messages if m['role']=='user' and 'Workspace context' in m['content']);self.assertLess(user.index(str(self.path)),user.index('Workspace context'),'above anything a size limit may cut');self.assertLess(user.index('<canvas></canvas>'),user.index('Workspace context'),'its text comes along: no read step, no question')
  self.assertIn('creations_folder: '+str(self.folder),messages[0]['content']);self.assertEqual(sent[0]['options']['num_predict'],9000)
  self.assertNotIn('business_lab',user,'nothing that a size limit would cut the file for');self.assertEqual([m['role'] for m in messages if m['role']=='assistant'],[],'an earlier question about the file does not get repeated')
 def test_the_prompt_tells_the_model_where_builds_go(self):
  from assistant_resilience import planner_system
  self.assertIn('creations_folder',planner_system(commander.SYSTEM),'the planner keeps only the action lines')

class AnswerYourselfTests(unittest.TestCase):
 def test_a_question_gets_an_answer_not_an_agent(self):
  # The owner (3 Nov): asked to assess the Autopilot, the assistant started a critic agent instead of answering.
  run=[dict(type='agent_run',agent='x')]
  for prompt in ('nézd meg az autópilóta eredményeit és működését, vizsgáld meg hogy mennyire jók az ötletei és javasolj javításokat hozzá.','Mik a legjobb ötletek az autopilotban?','Miért állt le a gyártás?','Elemezd a múlt heti videókat'):
   self.assertTrue(commander.answer_yourself(prompt,run),prompt)
  for prompt in ('Add át a Kritikus ügynöknek, nézze meg az ötleteket','Készíts egy videót a GTA 6-ról','Indítsd el az ügynököt, és vizsgálja meg','Írj egy cikket'):
   self.assertFalse(commander.answer_yourself(prompt,run),prompt)
  self.assertFalse(commander.answer_yourself('Mik a legjobb ötletek?',[dict(type='memory_save')]),'only agents are kept out')
 def test_a_read_named_oddly_still_reads_the_app(self):
  # 3 Nov: the model wrote {"project":"owner project ID","type":"today"}, got an error and judged the Autopilot from nothing.
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  self.assertEqual(commander.tidy_read(s,dict(project='owner project ID',type='today')),dict(project='owner project ID',app='today'))
  self.assertEqual(commander.tidy_read(s,dict(project='universe',app='autopilot')),dict(project='universe',app='autopilot'),'a real project stays')
  self.assertEqual(commander.tidy_read(s,dict(path='/x')),dict(path='/x'))
 def test_a_question_about_the_autopilot_goes_straight_to_the_model_with_its_data(self):
  # The owner (3 Nov): this is for the main assistant to answer, no agent, no question back.
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  verdict='A legerősebb ötlet az TermékE 19 ponttal, de igazolt bevétel még nincs, és a pontokat a saját kritikusa adta.'
  jid=commander.enqueue(s,'universe','nézd meg az autópilóta eredményeit, mennyire jók az ötletei?',global_mode=True);turn=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['turn']
  with patch('venture.report',return_value=dict(status='paused',ideas=[dict(name='TermékE',score=19)])),patch('studio.local_api',return_value=dict(message=dict(content=verdict))) as call:
   commander.run(s,dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  self.assertEqual(call.call_count,1);sent=call.call_args.args[2];self.assertIn('TermékE',sent['messages'][1]['content']);self.assertNotIn('format',sent,'plain text, not a plan');self.assertIsNone(sent.get('tools'));self.assertNotIn('write_file',sent['messages'][0]['content'])
  row=dict(s.db.execute('SELECT status,response,actions FROM command_turns WHERE id=?',(turn,)).fetchone());self.assertEqual(row,dict(status='done',response=verdict,actions='[]'))
  self.assertEqual(s.db.execute("SELECT count(*) FROM jobs WHERE kind='chat'").fetchone()[0],0)
 def test_no_transaction_is_open_while_waiting_for_the_model(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s);seen=[]
  def fake(service,route,data=None,timeout=8):
   seen.append(s.db.in_transaction);return dict(message=dict(content=json.dumps(dict(kind='reply',reply='A hasonlat nyíltan hasonlít, a metafora azonosít.'))))
  jid=commander.enqueue(s,'universe','Miben különbözik a metafora és a hasonlat?',global_mode=True)
  with patch('studio.local_api',side_effect=fake),patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):commander.run(s,dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  self.assertEqual(seen,[False],'nothing waits for a model holding the database')
 def test_the_assistant_knows_the_user_whatever_the_size_limit(self):
  # 3 Nov: asked "what am I called", it said the name was not saved, though it was: the size limit had cut the context.
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  import memory_brain
  memory_brain.remember(s,'name','The user is called Kovács Anna.','A neved Kovács Anna.','identity');sent=[]
  def fake(service,route,data=None,timeout=8):
   sent.append(data);return dict(message=dict(content=json.dumps(dict(reply='Kovács Anna, így hívnak téged.',reads=[],actions=[]))))
  jid=commander.enqueue(s,'universe','Hogy hívnak engem?',global_mode=True)
  with patch('studio.local_api',side_effect=fake),patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):commander.run(s,dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  self.assertIn('Kovács Anna',sent[0]['messages'][0]['content'],'in the rules, which a size limit keeps whole')
 def test_a_copied_status_mark_stays_out_of_the_answer(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  jid=commander.enqueue(s,'universe','Hogy hívnak?',global_mode=True);turn=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['turn']
  with patch('studio.local_api',return_value=dict(message=dict(content=json.dumps(dict(reply='Annának hívnak. · Execution status: done',reads=[],actions=[]))))),patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):commander.run(s,dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  self.assertEqual(s.db.execute('SELECT response FROM command_turns WHERE id=?',(turn,)).fetchone()[0],'Annának hívnak.')
 def test_only_questions_about_the_autopilot_take_the_short_way(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  with patch('venture.report',return_value=dict(status='paused')),patch('studio.local_api',side_effect=AssertionError('no model')):
   for prompt in ('Állítsd le az Autopilótát','Indítsd el az Autopilótát','Készíts új ötletet az Autopilótának','Milyen idő lesz holnap?'):
    self.assertIsNone(commander.assess_autopilot(s,dict(prompt=prompt,model='auto'),dict(id='j'),dict(automatic=True)),prompt)
  with patch('venture.report',return_value=dict(status='not_started')),patch('studio.local_api',side_effect=AssertionError('no model')):
   self.assertIsNone(commander.assess_autopilot(s,dict(prompt='Mik a legjobb ötletek?',model='auto'),dict(id='j'),dict(automatic=True)),'nothing to assess yet')
  with patch('venture.report',return_value=dict(status='paused')),patch('studio.local_api',side_effect=ValueError('down')):
   self.assertIsNone(commander.assess_autopilot(s,dict(prompt='Mik a legjobb ötletek?',model='auto'),dict(id='j'),dict(automatic=True)),'a failed model falls back to the normal way')
 def test_a_question_about_the_autopilot_comes_with_its_data(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  with patch('venture.report',return_value=dict(status='paused',ideas=[dict(name='SpecForge',score=19)])):
   note=commander.request_notes(s,'Mennyire jók az Autopilóta ötletei?',{})
   self.assertIn('SpecForge',note);self.assertIn('not workflow automations',note)
   self.assertEqual(commander.request_notes(s,'Milyen idő lesz holnap?',{}),'','other questions stay short')
 def test_the_answer_it_wrote_is_kept(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);commander.schema(s)
  plan=dict(reply='Az ötletek gyengék: a SpecForge-nak nincs mért kereslete, ezért először a keresletet kell megmérni, és csak utána építeni tovább.',reads=[],actions=[dict(type='agent_run',project='universe',agent='Nova',prompt='Criticize')])
  jid=commander.enqueue(s,'universe','Vizsgáld meg, mennyire jók az ötletek',global_mode=True);turn=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['turn']
  with patch('studio.local_api',return_value=dict(message=dict(content=json.dumps(plan)))),patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):commander.run(s,dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
  row=dict(s.db.execute('SELECT status,response,actions FROM command_turns WHERE id=?',(turn,)).fetchone());self.assertEqual((row['status'],row['actions']),('done','[]'));self.assertIn('SpecForge',row['response'])
  self.assertEqual(s.db.execute("SELECT count(*) FROM jobs WHERE kind='chat'").fetchone()[0],0,'no agent was started')

class ChatTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.s=Studio(Path(tmp.name));self.addCleanup(self.s.db.close);commander.schema(self.s)
 def send(self,prompt,session=''):return dispatch(dict(action='command_send',project='universe',prompt=prompt,**{'global':True},session=session),self.s)
 def op(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']
 def test_a_new_chat_starts_empty_and_keeps_its_own_messages(self):
  # The owner (3 Nov): a chats folder and new chats, like the reference app.
  first=self.send('Első téma: kertészkedés')['session'];self.assertEqual(self.send('Még egy kérdés',first)['session'],first)
  second=self.send('Második téma')['session'];self.assertNotEqual(first,second)
  state=lambda sid:[t['prompt'] for t in commander.state(self.s,'universe',True,sid)['turns']]
  self.assertEqual(sorted(state(first)),['Első téma: kertészkedés','Még egy kérdés']);self.assertEqual(state(second),['Második téma']);self.assertEqual(state(''),[],'a new chat is empty')
  self.assertEqual(self.op('chat_list')['chats'][0]['id'],second);self.assertEqual({c['title'] for c in self.op('chat_list')['chats']},{'Első téma: kertészkedés','Második téma'})
 def test_earlier_conversations_stay_reachable(self):
  commander.enqueue(self.s,'universe','Régi kérdés',global_mode=True);self.send('Új')
  self.assertEqual([t['prompt'] for t in commander.state(self.s,'universe',True,'earlier')['turns']],['Régi kérdés'])
  self.assertEqual(self.op('chat_list')['chats'][-1],dict(id='earlier',title='Korábbi beszélgetés',updated=self.op('chat_list')['chats'][-1]['updated'],turns=1))
  self.assertEqual(len(commander.state(self.s,'universe',True)['turns']),2,'callers without a chat still see everything')
 def test_rename_search_and_delete(self):
  sid=self.send('Macskák és kutyák')['session'];self.s.db.execute("UPDATE command_turns SET status='done'");self.s.db.commit()
  self.op('chat_rename',id=sid,title='  Állatok  ');self.assertEqual(self.op('chat_list')['chats'][0]['title'],'Állatok')
  with self.assertRaises(ValueError):self.op('chat_rename',id='earlier',title='x')
  with self.assertRaises(ValueError):self.op('chat_rename',id=sid,title='   ')
  self.assertEqual(self.op('chat_search',query='macsk')['results'][0]['session'],sid);self.assertEqual(self.op('chat_search',query='x')['results'],[]);self.assertEqual(self.op('chat_search',query='100%')['results'],[])
  self.assertEqual(self.op('chat_delete',id=sid)['removed'],1);self.assertEqual(self.op('chat_list')['chats'],[]);self.assertEqual(commander.state(self.s,'universe',True)['turns'],[])
 def test_a_running_chat_is_not_deleted(self):
  sid=self.send('Fut')['session']
  with self.assertRaisesRegex(ValueError,'még fut'):self.op('chat_delete',id=sid)

if __name__=='__main__':unittest.main()
