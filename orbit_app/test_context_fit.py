import unittest
from inference_stream import fit
class FitTests(unittest.TestCase):
 def test_task_survives_and_tools_shrink_first(self):
  task='TASK-START '+('context '*1500)+' TASK-END'
  msgs=[dict(role='system',content='rules'),dict(role='user',content=task),dict(role='assistant',content='',tool_calls=[{'function':{'name':'web_search','arguments':{'query':'x'}}}]),dict(role='tool',content='R1 '+'x'*12000),dict(role='tool',content='R2 '+'y'*12000)]
  out=fit(msgs,dict(num_ctx=8192,num_predict=1800))
  total=sum(len(m.get('content') or '') for m in out)
  self.assertLessEqual(total,(8192-1800-400)*2.4)
  user=out[1]['content'];self.assertTrue(user.startswith('TASK-START'));self.assertTrue(user.endswith('TASK-END'))
  self.assertTrue(all(m['role']!='tool' or len(m['content'])<12003 for m in out));self.assertEqual(len(out),5)
 def test_unresolvable_overflow_terminates(self):
  # Many messages just above the floor (the final no-tools round): this used to spin forever.
  msgs=[dict(role='user',content='u'*3020)]+[dict(role='tool',content='t'*1520) for _ in range(30)]
  out=fit(msgs,dict(num_ctx=8192,num_predict=1024))
  self.assertEqual(len(out),31);self.assertTrue(all(len(m['content'])<=3020 for m in out))
 def test_long_tool_loop_keeps_the_task_and_shrinks_newer_results(self):
  # A research step after several tool rounds overflowed; Ollama then cut the task itself and
  # refused the request ("no user query found in messages"). Now nothing is dropped: newer results
  # shrink to short notes, so the task and the cached older messages stay as they were.
  import json
  call=lambda n:dict(role='assistant',content='',tool_calls=[{'function':{'name':'read_web','arguments':{'url':'https://example.com/'+str(n)}}}])
  msgs=[dict(role='system',content='rules'),dict(role='user',content='TASK '+'feladat '*1200)]
  for n in range(4):msgs+=[call(n),dict(role='tool',content='R%d '%n+'z'*1520),dict(role='tool',content='S%d '%n+'w'*1520)]
  tools=[{'type':'function','function':{'name':'read_web','description':'d'*900,'parameters':{}}}]
  out=fit(msgs,dict(num_ctx=4096,num_predict=1024),tools)
  total=sum(len(m.get('content') or '') for m in out)+sum(len(json.dumps(m.get('tool_calls',''))) for m in out)
  self.assertLessEqual(total,(4096-1024-400)*2.4-len(json.dumps(tools)))
  self.assertTrue(out[1]['content'].startswith('TASK'),'the task survives');self.assertEqual(len(out),len(msgs),'nothing is dropped')
  self.assertTrue(out[-2]['content'].startswith('R3 '),'the latest result keeps its beginning')
  for i,m in enumerate(out):
   if m['role']=='tool':self.assertIn(out[i-1]['role'],('tool','assistant'),'no orphaned tool result')
 def test_review_loop_with_web_pages_stays_stable_to_the_last_round(self):
  # Measured: the first version still re-cut an earlier page once the floors overflowed, and the
  # final round (no tools) had a different room because the tools were larger than allowed for.
  import json
  tools=[{'type':'function','function':{'name':n,'description':'x'*120,'parameters':{'type':'object','properties':{'query':{'type':'string','description':'y'*60}},'required':['query'],'additionalProperties':False}}} for n in ('project_files','read_file','read_web','web_search')]
  opts=dict(num_ctx=16384,num_predict=1800);convo=[dict(role='system',content='S'*4000),dict(role='user',content='U'*15000)];prev=None
  for n in range(5):
   final=n==4
   if final:convo.append(dict(role='user',content='Tool budget used.'))
   out=fit(convo,opts,None if final else tools)
   if prev is not None:self.assertEqual(out[:len(prev)],prev,'round '+str(n))
   size=sum(len(m.get('content') or '') for m in out)+sum(len(json.dumps(m.get('tool_calls',''))) for m in out)
   self.assertLessEqual(size,(16384-1800-400)*2.4-(0 if final else len(json.dumps(tools))))
   prev=out;convo+=[dict(role='assistant',content='',tool_calls=[{'function':{'name':'read_web','arguments':{'url':'u%d'%n}}}]),dict(role='tool',content='É'*12000)]
 def test_review_reading_four_files_per_round_stays_stable(self):
  # A review read 12 files (~55k characters) in three rounds; the fallback then dropped older pages.
  import json
  tools=[{'type':'function','function':{'name':n,'description':'x'*120,'parameters':{'type':'object','properties':{'query':{'type':'string','description':'y'*60}},'required':['query'],'additionalProperties':False}}} for n in ('project_files','read_file','read_web','web_search')]
  opts=dict(num_ctx=16384,num_predict=1800);convo=[dict(role='system',content='S'*4000),dict(role='user',content='U'*13000)];prev=None
  for n in range(5):
   final=n==4
   if final:convo.append(dict(role='user',content='Tool budget used.'))
   out=fit(convo,opts,None if final else tools)
   if prev is not None:self.assertEqual(out[:len(prev)],prev,'round '+str(n))
   size=sum(len(m.get('content') or '') for m in out)+sum(len(json.dumps(m.get('tool_calls',''))) for m in out)
   self.assertLessEqual(size,(16384-1800-400)*2.4-(0 if final else len(json.dumps(tools))))
   prev=out;convo.append(dict(role='assistant',content='',tool_calls=[{'function':{'name':'read_file','arguments':{'name':'f%d_%d.py'%(n,k)}}} for k in range(4)]))
   convo+=[dict(role='tool',content='def x():\n  return "É"\n'*300) for k in range(4)]
 def test_small_prompt_untouched(self):
  msgs=[dict(role='user',content='hi')];self.assertEqual(fit(msgs,dict(num_ctx=8192)),msgs)
if __name__=='__main__':unittest.main()
