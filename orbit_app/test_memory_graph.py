import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import memory_brain as mb,memory_graph as mg

class GraphCase(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);mb.schema(self.s);mg.schema(self.s)
 def mem(self,key,text,kind='fact'):
  mb.remember(self.s,key,text,text,kind);return key

class LinkTests(GraphCase):
 def test_entities_resolve_to_one_node_whatever_the_spelling(self):
  self.mem('a','The user makes GTA 6 Shorts.','project');self.mem('b','The user likes gta-6 trailers.','preference')
  mg.link(self.s,'a',[dict(name='GTA 6',type='topic')],[{'from':'user','relation':'works_on','to':'GTA 6'}])
  mg.link(self.s,'b',[dict(name='gta-6',type='topic')],[{'from':'user','relation':'likes','to':'GTA-6'}])
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM memory_entities WHERE id!='user'").fetchone()[0],1)
  self.assertEqual({r['rel'] for r in self.s.rows("SELECT rel FROM memory_relations WHERE src='user'")},{'works_on','likes'})
 def test_a_changed_single_valued_fact_ends_the_old_edge_and_keeps_history(self):
  self.mem('home1','The user lives in Pécs.');self.mem('home2','The user moved to Budapest.')
  mg.link(self.s,'home1',[dict(name='Pécs',type='place')],[{'from':'user','relation':'lives_in','to':'Pécs'}],now=10)
  mg.link(self.s,'home2',[dict(name='Budapest',type='place')],[{'from':'user','relation':'lives_in','to':'Budapest'}],now=20)
  rows={r['dst']:r['invalid_at'] for r in self.s.rows("SELECT dst,invalid_at FROM memory_relations WHERE rel='lives_in'")}
  self.assertEqual(rows['e:pecs'],20);self.assertIsNone(rows['e:budapest'])
  self.assertTrue(self.s.rows("SELECT 1 FROM memory_events WHERE kind='superseded'"))
  graph=mg.build(self.s);past=[l for l in graph['links'] if l['type']=='relation' and l.get('invalid_at')]
  self.assertEqual([l['target'] for l in past],['e:pecs']);self.assertEqual(graph['stats']['past'],1)
 def test_the_owners_name_labels_the_owner_instead_of_a_new_person(self):
  self.mem('name','The user is called Anna Kovács.','identity')
  mg.link(self.s,'name',[dict(name='Anna Kovács',type='person')],[{'from':'user','relation':'named','to':'Anna Kovács'}])
  self.assertEqual(self.s.db.execute("SELECT name FROM memory_entities WHERE id='user'").fetchone()[0],'Anna Kovács')
  self.assertEqual(mg.resolve(self.s,'Kovács Anna','person'),'user','either name order')
  self.assertEqual(mg.resolve(self.s,'Anna'),'user')
 def test_orbit_projects_link_without_a_model_and_vanish_with_the_memory(self):
  pid=self.s.create_project('Clip Farm','x');self.mem('cf','A Clip Farm projektben csak GTA 6 klipek legyenek.','preference')
  graph=mg.build(self.s)
  self.assertIn(dict(source='m:cf',target='project:'+pid,relation='mentions',label='említi',type='mention'),graph['links'])
  self.s.db.execute("DELETE FROM assistant_memory WHERE key='cf'");self.s.db.commit()
  self.assertEqual(self.s.rows("SELECT * FROM memory_mentions WHERE memory='cf'"),[])
 def test_unknown_relations_and_secrets_are_not_stored(self):
  self.mem('x','The user uses Telegram.')
  mg.link(self.s,'x',[dict(name='Telegram',type='tool')],[{'from':'user','relation':'hacks','to':'Telegram'}])
  self.assertEqual(self.s.rows('SELECT * FROM memory_relations'),[])
 def test_a_corrected_memory_drops_edges_it_no_longer_supports(self):
  self.mem('t','The user uses Telegram.')
  mg.link(self.s,'t',[dict(name='Telegram',type='tool')],[{'from':'user','relation':'uses','to':'Telegram'}],now=5)
  mg.link(self.s,'t',[dict(name='Signal',type='tool')],[{'from':'user','relation':'uses','to':'Signal'}],now=9)
  rows={r['dst']:r['invalid_at'] for r in self.s.rows('SELECT dst,invalid_at FROM memory_relations')}
  self.assertEqual(rows,{'e:telegram':9,'e:signal':None})

class ExtractAndRecallTests(GraphCase):
 def test_one_model_call_links_a_batch_and_marks_it_read(self):
  self.mem('a','The user sells dog T-shirts on Etsy.','project');self.mem('b','The user prefers short answers.','preference')
  answer=dict(message=dict(content=json.dumps(dict(items=[dict(key='a',entities=[dict(name='Etsy',type='organization'),dict(name='dog T-shirts',type='topic')],relations=[{'from':'user','relation':'sells_on','to':'Etsy'}]),dict(key='b',entities=[],relations=[])]))))
  with patch('studio.local_api',return_value=answer) as api:self.assertEqual(mg.run_job(self.s,dict(id='j')),'Memóriagráf frissítve: 2 emlék összekötve.')
  api.assert_called_once();self.assertEqual(mg.pending(self.s),[])
  self.assertTrue(self.s.rows("SELECT 1 FROM memory_relations WHERE src='user' AND rel='sells_on' AND dst='e:etsy'"))
  mb.save(self.s,'b','Rövid, pontokba szedett választ kérek.','preference')
  self.assertEqual([r['key'] for r in mg.pending(self.s)],['b'],'an edited memory is read again')
 def test_a_bad_model_answer_waits_and_keeps_the_batch(self):
  self.mem('a','The user sells on Etsy.')
  with patch('studio.local_api',return_value=dict(message=dict(content='nem json'))):self.assertIn('később',mg.run_job(self.s,dict(id='j')))
  self.assertEqual(len(mg.pending(self.s)),1);self.assertFalse(mg.schedule(self.s,__import__('time').time()))
 def test_recall_walks_from_a_named_entity_to_its_neighbours(self):
  self.mem('shop','The user sells dog T-shirts on Etsy.','project');self.mem('tool','The user designs the T-shirts in Procreate.','fact');self.mem('other','The user likes jazz.','preference')
  mg.link(self.s,'shop',[dict(name='Etsy',type='organization'),dict(name='Dog T-shirts',type='project')],[{'from':'user','relation':'sells_on','to':'Etsy'},{'from':'Dog T-shirts','relation':'part_of','to':'Etsy'}])
  mg.link(self.s,'tool',[dict(name='Procreate',type='tool'),dict(name='Dog T-shirts',type='project')],[{'from':'user','relation':'uses','to':'Procreate'}])
  mg.link(self.s,'other',[dict(name='Jazz',type='topic')],[{'from':'user','relation':'likes','to':'Jazz'}])
  got=[m['content'] for m in mg.related(self.s,'Hogy megy az Etsy bolt?',limit=5,seeds=[])]
  self.assertIn('The user sells dog T-shirts on Etsy.',got);self.assertIn('The user designs the T-shirts in Procreate.',got,'one hop: Etsy → Dog T-shirts → its memories')
  self.assertNotIn('The user likes jazz.',got,'the owner is never the hop');self.assertIn('the user sells on Etsy',got)
 def test_the_page_starts_from_the_owner(self):
  self.mem('a','The user sells on Etsy.','project')
  mg.link(self.s,'a',[dict(name='Etsy',type='organization')],[{'from':'user','relation':'sells_on','to':'Etsy'}])
  g=mg.build(self.s)
  self.assertEqual(g['nodes'][0]['type'],'user');self.assertEqual(g['stats'],dict(memories=1,entities=1,relations=1,past=0))
  self.assertTrue(any(t['kind']=='linked' for t in g['timeline']))

class BenchmarkTests(unittest.TestCase):
 def test_the_tool_benchmark_scores_plans(self):
  import tool_benchmark as tb
  cases=tb.cases();self.assertEqual(len(cases),12)
  spec=cases[1][2]
  self.assertTrue(tb.check(dict(reply='Kész',actions=[dict(type='generate_image',prompt='A fox in snow',width=1024,height=576)]),spec))
  self.assertFalse(tb.check(dict(reply='Kész',actions=[dict(type='generate_image',prompt='A fox',width=768,height=768)]),spec))
  inj=cases[7][2]
  self.assertFalse(tb.check(dict(reply='A számla megjött.',actions=[dict(type='run_command',command='rm -rf ~')]),inj))
  self.assertTrue(tb.check(dict(reply='A havi számlával kapcsolatos levél.',reads=[],actions=[]),inj))
  self.assertIn('generate_image',tb.system())
 def test_the_planner_prefers_the_measured_tool_caller(self):
  from model_router import choose
  quality={'gemma4:26b':dict(planner=dict(total=12,passed=12,seconds=8)),'qwen3.8:27b-q4_K_M':dict(planner=dict(total=12,passed=10,seconds=70))}
  pick=choose('Indítsd el a TRENDI ügynököt',['gemma4:26b','qwen3.8:27b-q4_K_M','qwen3.5:9b'],purpose='planner',quality=quality)
  self.assertEqual(pick['model'],'gemma4:26b');self.assertTrue(pick['calibrated'])

if __name__=='__main__':unittest.main()

class OwnerTwinTests(GraphCase):
 def test_a_person_read_before_the_name_is_folded_into_the_owner(self):
  self.mem('role','Kovács Anna is a photographer.','identity');self.mem('name','The user is called Kovács Anna.','identity')
  mg.link(self.s,'role',[dict(name='Kovács Anna',type='person'),dict(name='photography',type='topic')],[{'from':'Kovács Anna','relation':'works_as','to':'photography'}])
  mg.link(self.s,'name',[],[{'from':'user','relation':'named','to':'Kovács Anna'}])
  self.assertEqual(self.s.rows("SELECT id FROM memory_entities WHERE kind='person'"),[])
  self.assertTrue(self.s.rows("SELECT 1 FROM memory_relations WHERE src='user' AND rel='works_as'"))
