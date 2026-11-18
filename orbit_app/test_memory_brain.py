import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import commander,memory_brain as mb

def answer(items):return dict(message=dict(content=json.dumps(dict(memories=items),ensure_ascii=False)))

class MemoryCase(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.s=Studio(Path(tmp.name));self.addCleanup(self.s.db.close);mb.schema(self.s);mb._pace['at']=0;self.n=0
 def turn(self,prompt,status='done'):
  self.n+=1;self.s.db.execute('INSERT INTO command_turns VALUES(?,?,?,?,?,?,?,?,?)',('t'+str(self.n),'universe',prompt,'auto','ok','[]',status,'j',time.time()+self.n));self.s.db.commit();return 't'+str(self.n)
 def job(self):return dict(id='job1')
 def learn(self,items):
  with patch('studio.local_api',return_value=answer(items)) as call:out=mb.learn(self.s,self.job())
  return out,call

class LearningTests(MemoryCase):
 def test_it_learns_from_the_users_words_only(self):
  # The owner (3 Nov): the more the app is used, the more it learns and understands them.
  self.turn('A kisfiam 6 éves, neki keresek színezőket');pasted=self.turn('x'*(mb.LONG_PASTE+1))
  out,call=self.learn([dict(kind='fact',key='has-son',content='The user has a six year old son.',display='Van egy hatéves fia.'),dict(kind='weird',key='k',content='Something new here today.',display='Új dolog.')])
  self.assertIn('2 új',out);sent=call.call_args_list[0].args[2]
  self.assertNotIn('x'*50,json.dumps(sent),'a long paste is not the user talking about themselves');self.assertIs(sent['format'],'json')
  rows={r['key']:r for r in self.s.rows('SELECT * FROM assistant_memory')};self.assertEqual((rows['has-son']['kind'],rows['has-son']['source']),('fact','auto'));self.assertEqual(rows['k']['kind'],'fact','an unknown kind becomes a plain fact')
  self.assertEqual(mb.unseen(self.s),[],'each message is read once');self.assertTrue(pasted)
 def test_secrets_are_never_stored(self):
  for content in ('The password is hunter2','A jelszavam: titok123','API key sk-abcdefgh1234','Card 4111 1111 1111 1111','IBAN HU42 1177'):
   self.assertFalse(mb.remember(self.s,'x',content,content),content)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM assistant_memory').fetchone()[0],0)
  with self.assertRaisesRegex(ValueError,'Jelszót'):mb.save(self.s,None,'A jelszavam titok123','fact')
 def test_the_same_thing_twice_strengthens_the_memory(self):
  self.assertTrue(mb.remember(self.s,'a','The user likes short answers.','Rövid válaszokat szeret.','preference'))
  self.assertFalse(mb.remember(self.s,'b','The user likes short answers!','Rövid válaszokat szeret!','preference'))
  self.assertEqual(self.s.rows('SELECT key,uses FROM assistant_memory'),[dict(key='a',uses=1)])
 def test_what_the_user_says_about_themselves_is_learned_at_once(self):
  # 3 Nov: "from now on use my name" waited for the next round while the assistant said it could not remember.
  now=time.time();self.s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('learned_at',?)",(str(now),));self.s.db.commit()
  self.turn('Mostantól Kovács Annanak hívj');self.assertTrue(mb.tick(self.s,now+1))
 def test_a_portrait_grows_from_what_is_known_and_stays_the_owners_once_edited(self):
  self.turn('Színezőket csinálok gyerekeknek')
  answers=iter([answer([dict(kind='project',key='coloring',content='The user makes coloring pages for children.',display='Színezőket készít gyerekeknek.')]),dict(message=dict(content=json.dumps(dict(content='The user makes coloring pages.',display='Színezőket készítesz.'))))])
  with patch('studio.local_api',side_effect=lambda *a,**k:next(answers)):mb.learn(self.s,self.job())
  got=mb.listing(self.s);self.assertEqual(got['profile']['display'],'Színezőket készítesz.');self.assertEqual(got['total'],1,'the portrait is not one of the memories');self.assertEqual(got['memories'][0]['key'],'coloring')
  self.assertEqual(mb.recall(self.s,'bármi más')[0],dict(kind='profile',content='The user makes coloring pages.'),'who the user is goes first')
  self.assertEqual(mb.note(self.s)['text'],'Színezőket készít gyerekeknek.','the chat tells it was noted')
  mb.save(self.s,mb.PROFILE,'Saját szavaimmal','identity');self.turn('Mostantól rövid választ kérek')
  with patch('studio.local_api',return_value=answer([dict(kind='preference',key='short',content='The user wants short answers.',display='Rövid válaszokat kér.')])) as call:mb.learn(self.s,self.job())
  # Learning and linking the new memory into the graph; no third call rewriting the portrait.
  self.assertNotIn('Write who this user is',str(call.call_args_list),'an edited portrait is not rewritten');self.assertEqual(mb.listing(self.s)['profile']['display'],'Saját szavaimmal')
 def test_old_history_is_read_quietly(self):
  self.turn('Régi dolog');self.s.db.execute("UPDATE command_turns SET created=?",(time.time()-5*86400,));self.s.db.commit();self.learn([dict(kind='fact',key='k',content='The user owns a cat named Mici today.',display='Van egy Mici nevű macskád.')])
  self.assertIsNone(mb.note(self.s))
 def test_a_broken_model_answer_changes_nothing(self):
  self.turn('valami')
  with patch('studio.local_api',return_value=dict(message=dict(content='nem json'))):mb.learn(self.s,self.job())
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM assistant_memory').fetchone()[0],0)
  self.assertIsNone(mb.parse(dict(message=dict(content=json.dumps(dict(memories='x'))))))
  self.assertEqual(len(mb.unseen(self.s)),1)
 def test_full_memory_drops_the_least_useful_automatic_one_never_the_owners(self):
  with patch('memory_brain.LIMIT',3):
   mb.save(self.s,None,'A saját emlékem marad','fact');mb.remember(self.s,'used','Alpha beta gamma delta','Alpha beta gamma delta');mb.remember(self.s,'idle','Omega sigma lambda kappa','Omega sigma lambda kappa')
   self.s.db.execute("UPDATE assistant_memory SET uses=5 WHERE key='used'");mb.remember(self.s,'new','Pizza pasta salad bread','Pizza pasta salad bread')
  keys={r['key'] for r in self.s.rows('SELECT key FROM assistant_memory')};self.assertNotIn('idle',keys);self.assertIn('used',keys);self.assertIn('new',keys);self.assertEqual(len(keys),3)
 def test_learning_waits_for_enough_messages_and_can_be_off(self):
  now=time.time();self.turn('egy');self.s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('learned_at',?)",(str(now),));self.s.db.commit()
  self.assertFalse(mb.tick(self.s,now),'one message and a recent round: it waits')
  self.turn('kettő');self.turn('három');mb._pace['at']=0;self.assertFalse(mb.tick(self.s,now+1),'even a long history is read a little at a time')
  mb._pace['at']=0;self.assertTrue(mb.tick(self.s,now+mb.EAGER_PACE+1))
  job=self.s.db.execute("SELECT payload FROM jobs WHERE kind='assist'").fetchone();self.assertTrue(json.loads(job[0])['local_only'],'what it learns from never leaves the Mac')
  mb._pace['at']=0;self.assertFalse(mb.tick(self.s,now+mb.EAGER_PACE+2),'never twice at once')
  self.s.db.execute("UPDATE jobs SET status='done' WHERE kind='assist'");self.s.db.commit();mb.dispatch(self.s,'memory_enable',dict(on=False));mb._pace['at']=0;self.assertFalse(mb.tick(self.s,now+mb.EAGER_PACE+3));self.assertFalse(mb.listing(self.s)['enabled'])

class RecallTests(MemoryCase):
 def test_what_the_message_is_about_comes_first_and_counts(self):
  mb.remember(self.s,'cook','The user likes Italian cooking.','Szereti az olasz konyhát.');mb.remember(self.s,'name','The user is called Anna.','Anna a neve.','identity')
  for i in range(20):mb.remember(self.s,'other'+str(i),'Unrelated number '+str(i)+' zebra'+str(i),'Más '+str(i)+' zebra'+str(i))
  got=mb.recall(self.s,'Which cooking recipes would suit me?',limit=3)
  self.assertEqual(got[0]['content'],'The user likes Italian cooking.');self.assertEqual(got[1]['content'],'The user is called Anna.','who the user is always helps');self.assertLessEqual(len(got),3)
  self.assertEqual(self.s.db.execute("SELECT uses FROM assistant_memory WHERE key='cook'").fetchone()[0],1);self.assertEqual(self.s.db.execute("SELECT uses FROM assistant_memory WHERE key='name'").fetchone()[0],0,'only what the message was about counts as used')
 def test_hungarian_endings_match(self):
  mb.remember(self.s,'c','A kutyáknak készít színezőket.','A kutyáknak készít színezőket.')
  self.assertEqual(mb.recall(self.s,'kutyák színező',limit=1)[0]['content'],'A kutyáknak készít színezőket.')
 def test_old_memories_survive_the_new_columns(self):
  self.s.db.execute("INSERT INTO assistant_memory(key,content,display,updated) VALUES('old','Prefers Hungarian','Magyarul',1)");self.s.db.commit();commander.memory_save(self.s,dict(key='old',content='Prefers Hungarian replies',display='Magyarul válaszolj'))
  row=dict(self.s.db.execute("SELECT * FROM assistant_memory WHERE key='old'").fetchone());self.assertEqual((row['content'],row['kind'],row['source']),('Prefers Hungarian replies','preference','manual'))

class VectorTests(MemoryCase):
 def test_graph_recall_expands_a_semantic_match_once(self):
  mb.remember(self.s,'seed','Animation narration: preferred dramatic dialogue.', 'Animation narration: preferred dramatic dialogue.')
  mb.remember(self.s,'neighbor','Animation narration: keep vocal stems separate.', 'Animation narration: keep vocal stems separate.')
  import memory_graph
  # Both memories name the same entity; the graph, not shared word stems, connects them.
  memory_graph.link(self.s,'seed',[dict(name='Narration',type='topic')],[dict(**{'from':'user','relation':'prefers','to':'Narration'})])
  memory_graph.link(self.s,'neighbor',[dict(name='narration',type='topic')],[])
  with patch('memory_brain.semantic_scores',return_value={'seed':.9}) as semantic:
   memories=mb.recall(self.s,'offline sound workflow',limit=1,relevant_only=True,graph_limit=1)
  contents=[m['content'] for m in memories]
  self.assertEqual(contents[0],'Animation narration: preferred dramatic dialogue.')
  self.assertIn('Animation narration: keep vocal stems separate.',contents)
  self.assertIn('the user prefers Narration',contents)
  semantic.assert_called_once()
 def test_semantic_recall_and_invalidation(self):
  keep=mb.save(self.s,None,'Kizárólag helyi modelleket használok.','fact')['key']
  mb.save(self.s,None,'A műhely címe ORBIT.','fact')
  def vectors(port,inputs,timeout):
   return [[1.,0.] if 'helyi' in text or 'offline' in text else [0.,1.] for text in inputs]
  with patch('model_hub.models',return_value=[dict(name=mb.EMBED_MODEL,port=11435)]),patch('memory_brain.embed',side_effect=vectors),patch('memory_brain.resident',return_value=True):
   mb.index_vectors(self.s)
   self.assertIn('helyi',mb.recall(self.s,'offline inference',limit=1)[0]['content'])
   mb.save(self.s,keep,'Most már a felhőt is használom.','fact')
   self.assertEqual(mb.listing(self.s)['embedding']['indexed'],1)
   mb.dispatch(self.s,'memory_delete',{'key':keep})
   with patch('memory_brain.embed',side_effect=TimeoutError):
    self.assertIn('műhely',mb.recall(self.s,'műhely címe',limit=1)[0]['content'])

  # A cold embedding model is never asked: loading it would unload the chat model.
  with patch('memory_brain.resident',return_value=False),patch('memory_brain.embed',side_effect=AssertionError('cold model asked')):
   self.assertEqual(mb.semantic_scores(self.s,'offline inference please'),{})

class PageTests(MemoryCase):
 def op(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']
 def test_the_page_lists_edits_and_removes(self):
  key=self.op('memory_save',display='Szereti a kávét',kind='preference')['key'];mb.remember(self.s,'auto1','The user lives in Pécs.','Pécsett él.')
  data=self.op('memory_list');self.assertEqual((data['total'],data['counts']['preference'],data['enabled']),(2,1,True))
  self.assertEqual([m['key'] for m in self.op('memory_list',kind='preference')['memories']],[key]);self.assertEqual(len(self.op('memory_list',query='pécs')['memories']),1)
  self.op('memory_save',key=key,display='Szereti a teát',kind='fact');row=next(m for m in self.op('memory_list')['memories'] if m['key']==key);self.assertEqual((row['display'],row['kind'],row['source']),('Szereti a teát','fact','manual'))
  self.op('memory_delete',key=key);self.assertEqual(self.op('memory_list')['total'],1)
 def test_tidy_merges_twins(self):
  self.s.db.execute("INSERT INTO assistant_memory(key,content,display,updated,uses) VALUES('a','The user drives a blue car','Kék autója van',1,4),('b','The user drives a blue car!','Kék autója van!',2,1),('c','Something else entirely','Más dolog',3,0)");self.s.db.commit()
  self.assertEqual(self.op('memory_tidy')['merged'],1);self.assertEqual(self.s.rows("SELECT uses FROM assistant_memory WHERE key='a'"),[dict(uses=5)])
 def test_the_assistant_cannot_reach_the_page(self):
  source=(Path(mb.__file__).parent/'commander.py').read_text();self.assertNotIn("'memory_delete'",source);self.assertNotIn("'memory_enable'",source)
 def test_graph_filters_project_and_forgets_deleted_nodes(self):
  pid=self.s.create_project('YouTube Shorts','test')
  a=self.op('memory_save',display='YouTube Shorts: kontrasztos animáció és narráció.',kind='preference')['key']
  b=self.op('memory_save',display='Kontrasztos animáció a cél.',kind='goal')['key']
  graph=self.op('memory_graph')
  # Model-free layer: the ORBIT project named in the memory is an entity at once.
  self.assertIn(dict(source='m:'+a,target='project:'+pid,relation='mentions',label='említi',type='mention'),graph['links'])
  self.assertTrue(any(l['source']=='user' and l['target']=='m:'+b for l in graph['links']))
  self.assertTrue(any(l['source']=='user' and l['target']=='project:'+pid and l['type']=='derived' for l in graph['links']))
  self.assertEqual({node['id'] for node in self.op('memory_graph',project=pid)['nodes']},{'user','m:'+a,'project:'+pid})
  self.op('memory_delete',key=a)
  self.assertEqual({n['id'] for n in self.op('memory_graph',project=pid)['nodes']},{'user'})
  self.assertEqual(self.s.rows('SELECT memory FROM memory_mentions WHERE memory=?',(a,)),[])
 def test_explicit_preference_correction_replaces_auto_only(self):
  mb.remember(self.s,'caption','Use white captions.','Fehér felirat.','preference',now=10)
  self.assertTrue(mb.remember(self.s,'caption','Use yellow captions.','Sárga felirat.','preference',now=12,correction_at=11))
  mb.save(self.s,'caption','A saját beállításom.','preference')
  self.assertFalse(mb.remember(self.s,'caption','Use red captions.','Piros felirat.','preference',correction_at=time.time()+1))
  self.assertEqual(self.s.db.execute("SELECT display FROM assistant_memory WHERE key='caption'").fetchone()[0],'A saját beállításom.')

if __name__=='__main__':unittest.main()
