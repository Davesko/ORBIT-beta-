import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import studio
class BuildReadCapTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.s=Studio(Path(tmp.name));self.addCleanup(self.s.db.close)
 def test_json_build_reads_at_most_two_files(self):
  # The 27B read four or five files, one per round, each round re-reading the whole prompt.
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  s.db.execute("UPDATE agents SET tools=? WHERE id=?",(json.dumps(['read_file']),aid));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='json',agent_snapshot=snap,allowed_tools=['read_file']))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  read=lambda n:dict(function=dict(name='read_file',arguments=dict(name=n)))
  replies=[dict(message=dict(content='',tool_calls=[read('a.py')])),dict(message=dict(content='',tool_calls=[read('b.py'),read('c.py')])),dict(message=dict(content='{"done": true}'))]
  sent=[]
  def answer(*a,**k):sent.append(a[2]);return replies.pop(0)
  with patch('studio.local_api',side_effect=answer),patch.object(Studio,'tool',return_value=dict(content='x')) as tool,patch.object(Studio,'repair_json',side_effect=lambda job,agent,c,**kw:c):
   out=s._run_agent(job)
  self.assertEqual(out,'{"done": true}');self.assertEqual(tool.call_count,2,'the third read is refused')
  self.assertEqual(sent[-1]['tools'],sent[0]['tools'],'the tool list stays: it is part of the cached prompt prefix')
  self.assertIn('File read budget used',sent[-1]['messages'][-1]['content'])
 def test_closing_round_keeps_tools_listed_but_runs_none(self):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  s.db.execute("UPDATE agents SET tools=? WHERE id=?",(json.dumps(['web_search']),aid));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'review','mission_agent',payload=dict(output_contract='text',agent_snapshot=snap,allowed_tools=['web_search']))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  search=lambda q:dict(message=dict(content='',tool_calls=[dict(function=dict(name='web_search',arguments=dict(query=q)))]))
  replies=[search('a'),search('b'),search('c'),search('d'),search('e'),dict(message=dict(content='Végső értékelés'))]
  sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(results=[])) as tool:
   self.assertEqual(s._run_agent(job),'Végső értékelés')
  self.assertEqual(tool.call_count,4,'no tool runs after the budget')
  self.assertTrue(all(r.get('tools')==sent[0]['tools'] for r in sent),'the same tool list in every round (cached prefix)')
  self.assertIn('no tool was run',sent[-1]['messages'][-1]['content'],'the extra call got a refusal as its tool result')
 def test_review_reads_at_most_four_files(self):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  s.db.execute("UPDATE agents SET tools=? WHERE id=?",(json.dumps(['read_file']),aid));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'review','mission_agent',payload=dict(output_contract='text',agent_snapshot=snap,allowed_tools=['read_file']))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  read=lambda n:dict(function=dict(name='read_file',arguments=dict(name=n)))
  replies=[dict(message=dict(content='',tool_calls=[read('a.py'),read('b.py'),read('c.py'),read('d.py')])),dict(message=dict(content='',tool_calls=[read('e.py'),read('f.py')])),dict(message=dict(content='VERDICT: accept'))]
  sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(content='x')) as tool:
   self.assertEqual(s._run_agent(job),'VERDICT: accept')
  self.assertEqual(tool.call_count,4);self.assertTrue(any('write your complete review now' in str(m.get('content')) for m in sent[-1]['messages']))
 def test_model_that_keeps_calling_tools_gets_no_tool_list(self):
  # 16:30: after its two reads the builder asked for more files twice and the job ended empty.
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  s.db.execute("UPDATE agents SET tools=? WHERE id=?",(json.dumps(['read_file']),aid));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='json',agent_snapshot=snap,allowed_tools=['read_file']))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  read=lambda n:dict(function=dict(name='read_file',arguments=dict(name=n)))
  replies=[dict(message=dict(content='',tool_calls=[read('a.py'),read('b.py')])),dict(message=dict(content='',tool_calls=[read('c.py')])),dict(message=dict(content='{"done": true}'))]
  sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(content='x')),patch.object(Studio,'repair_json',side_effect=lambda job,agent,c,**kw:c):
   self.assertEqual(s._run_agent(job),'{"done": true}')
  self.assertIn('tools',sent[2],'the refused call is answered and the cached tool list stays')
  self.assertIn('Tool budget used: no tool was run',sent[2]['messages'][-1]['content'])
 def test_model_insisting_on_tools_after_a_refusal_must_answer_in_json(self):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  s.db.execute("UPDATE agents SET tools=? WHERE id=?",(json.dumps(['read_file']),aid));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='json',agent_snapshot=snap,allowed_tools=['read_file']))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  read=lambda n:dict(function=dict(name='read_file',arguments=dict(name=n)))
  replies=[dict(message=dict(content='',tool_calls=[read('a.py'),read('b.py')])),dict(message=dict(content='',tool_calls=[read('c.py')])),dict(message=dict(content='',tool_calls=[read('d.py')])),dict(message=dict(content='{"done": true}'))]
  sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(content='x')) as tool,patch.object(Studio,'repair_json',side_effect=lambda job,agent,c,**kw:c):
   self.assertEqual(s._run_agent(job),'{"done": true}')
  self.assertEqual(tool.call_count,2);self.assertIn('tools',sent[2]);self.assertEqual(sent[3].get('format'),'json','asked again after the refusal: JSON only')
 def build_job(self,tool):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  s.db.execute("UPDATE agents SET tools=? WHERE id=?",(json.dumps([tool]),aid));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='json',agent_snapshot=snap,allowed_tools=[tool]))
  return dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
 def test_asking_for_the_same_file_again_ends_the_reading(self):
  # 1 Nov 16:04: index.html was read, asked for three more times (a round each), and the build ended empty.
  job=self.build_job('read_file');again=dict(message=dict(content='',tool_calls=[dict(function=dict(name='read_file',arguments=dict(name='index.html')))]))
  replies=[again,again,again,again,dict(message=dict(content='{"done": true}'))];sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(content='x')) as tool,patch.object(Studio,'repair_json',side_effect=lambda job,agent,c,**kw:c):
   self.assertEqual(self.s._run_agent(job),'{"done": true}')
  self.assertEqual(tool.call_count,1);self.assertTrue(any('You already have that result above' in str(m.get('content')) for m in sent[-1]['messages']))
  self.assertEqual(sent[-1].get('format'),'json','the last answer can only be JSON (no mission node: plain JSON)')
  self.assertEqual(sent[-1]['tools'],sent[0]['tools'],'the tool list stays: it is part of the cached prompt')
  self.assertGreaterEqual(sent[-1]['_orbit_budget'],420,'a build budget, not the 120 s of a short JSON request')
 def test_a_forced_build_answer_has_the_shape_of_a_build(self):
  # Cycle 220: the forced JSON round answered {"text": "<the fix, described>"}, with no edit in it.
  job=self.build_job('read_file');p=json.loads(job['payload']);p['mission_node']='build'
  self.s.db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(p),job['id']));self.s.db.commit();job['payload']=json.dumps(p)
  again=dict(message=dict(content='',tool_calls=[dict(function=dict(name='read_file',arguments=dict(name='a.py')))]))
  replies=[again,again,again,again,dict(message=dict(content='{"milestone_id": "tests", "edits": [], "files": [], "summary": "x"}'))];sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(content='x')),patch.object(Studio,'repair_json',side_effect=lambda job,agent,c,**kw:c):
   self.s._run_agent(job)
  self.assertEqual(sent[-1]['format'],studio.BUILD_SCHEMA);self.assertIn('edits',sent[-1]['format']['required'])
  self.assertIs(sent[-1]['_orbit_partial_ok'],True,'a cut-off build answer is salvaged, not failed')
 def test_a_tool_call_in_the_last_round_still_gets_its_answer_round(self):
  # In 8 of 19 empty builds (30 Oct-1 Nov) the model's sixth reply was one more tool call, and the request
  # to answer had no round left.
  job=self.build_job('web_search');ask=lambda q:dict(message=dict(content='',tool_calls=[dict(function=dict(name='web_search',arguments=dict(query=q)))]))
  replies=[ask('a'),ask('b'),ask('c'),ask('d'),ask('e'),ask('f'),dict(message=dict(content='{"done": true}'))];sent=[]
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or replies.pop(0)),patch.object(Studio,'tool',return_value=dict(results=[])),patch.object(Studio,'repair_json',side_effect=lambda job,agent,c,**kw:c):
   self.assertEqual(self.s._run_agent(job),'{"done": true}')
  self.assertEqual(len(sent),7);self.assertEqual(sent[-1].get('format'),'json')
 def test_review_reply_is_capped_to_what_is_used(self):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  sent=[]
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='json',mission_node='build',agent_snapshot=dict(snap,tools=[]),allowed_tools=[],reply_budget=7500))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or dict(message=dict(content='{"milestone_id": "x"}'))):s._run_agent(job)
  self.assertEqual(sent[-1]['options']['num_predict'],7500,'a retry after a cut answer gets more room')
  for node,expected in (('review',studio.REVIEW_REPLY),('research',1800)):
   jid=s.enqueue(aid,node,'mission_agent',payload=dict(output_contract='text',mission_node=node,agent_snapshot=dict(snap,tools=[]),allowed_tools=[]))
   job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
   with patch('studio.local_api',side_effect=lambda *x,**k:sent.append(x[2]) or dict(message=dict(content='VERDICT: accept'))):s._run_agent(job)
   self.assertEqual(sent[-1]['options']['num_predict'],expected,node)
 def test_orbit_written_brief_needs_no_model_call(self):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'research','mission_agent',payload=dict(output_contract='text',mission_node='research',agent_snapshot=snap,allowed_tools=[],fixed_result='milestone_id: engine\n\nORBIT fix brief'))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  with patch('studio.local_api',side_effect=AssertionError('no model call')):self.assertTrue(s._run_agent(job).startswith('milestone_id: engine'))
  jid=s.enqueue(aid,'review','mission_agent',payload=dict(output_contract='text',mission_node='review',agent_snapshot=snap,allowed_tools=[],fixed_result='VERDICT: accept\nORBIT mérés',fixed_stage='Az ORBIT a mért kódfuttatásból írta meg az ítéletet (modellhívás nélkül)'))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  with patch('studio.local_api',side_effect=AssertionError('no model call')):self.assertEqual(s._run_agent(job),'VERDICT: accept\nORBIT mérés')
 def test_token_use_is_recorded_per_round(self):
  s=self.s;aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='text',agent_snapshot=dict(snap,tools=[]),allowed_tools=[]))
  job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  reply=dict(message=dict(content='Kész'),prompt_eval_count=4700,eval_count=2900,done_reason='length',total_duration=61_500_000_000,prompt_eval_duration=20_400_000_000)
  with patch('studio.local_api',return_value=reply):self.assertEqual(s._run_agent(job),'Kész')
  rounds=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['rounds']
  self.assertEqual(rounds,[dict(round=1,prompt=4700,output=2900,stop='length',seconds=61.5,read_s=20.4)])
 def test_waiting_retries_are_logged_once(self):
  s=self.s
  for _ in range(5):
   for kind,label in (('starting','Feladat előkészítése'),('processing','Helyi feldolgozás folyamatban'),('waiting','A helyi modell másik feladaton dolgozik')):s.job_stage('j1',kind,label)
  s.job_stage('j1','model','A helyi modell válaszára vár')
  self.assertEqual([r['kind'] for r in s.rows("SELECT kind FROM job_log WHERE job='j1' ORDER BY id")],['starting','processing','waiting','model'])
if __name__=='__main__':unittest.main()
