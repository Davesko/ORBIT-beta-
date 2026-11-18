import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import research
class ResearchCacheTests(unittest.TestCase):
 def test_market_research_is_reused_for_days_news_is_not(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
  calls=[]
  def fake(provider,path,params,root):calls.append(params['query']);return dict(results=[dict(title='t',url='https://example.com/a',content='c')])
  with patch('connections.allowed',return_value=True),patch('connections.http',side_effect=fake):
   research.search('Hungarian invoice OCR API',root=root);r=research.search('  hungarian invoice ocr API ',root=root)
   self.assertTrue(r['cached']);self.assertEqual(len(calls),1)
   with patch('research.time.time',return_value=time.time()+4*86400):research.search('Hungarian invoice OCR API',root=root)
   self.assertEqual(len(calls),2)
class EmptyAnswerTests(unittest.TestCase):
 def test_answer_in_reasoning_channel_is_not_lost(self):
  import io,json,inference_stream
  lines=[json.dumps(dict(message=dict(thinking='{"a": 1}'))),json.dumps(dict(done=True,done_reason='stop',message={}))]
  class R(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*a):return False
  body=R(('\n'.join(lines)+'\n').encode())
  body.status=200
  conn=__import__('unittest.mock').mock.Mock();conn.getresponse.return_value=body
  with patch('inference_stream.http.client.HTTPConnection',return_value=conn),patch('inference_stream.progress'):
   meta=inference_stream.chat(1,dict(model='m',messages=[dict(role='user',content='x')]),30,'/nonexistent')
  self.assertEqual(meta['message']['content'],'');self.assertEqual(meta['message']['thinking'],'{"a": 1}')
class EmptyReplyRetryTests(unittest.TestCase):
 def test_empty_final_reply_is_asked_again_in_the_same_job(self):
  import json,tempfile
  from studio import Studio
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close)
  aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];s.db.execute("UPDATE agents SET tools='[]' WHERE id=?",(aid,));s.db.commit()
  a=s.agent(aid);snap={k:a[k] for k in ('id','project','name','prompt','model','tools')}
  jid=s.enqueue(aid,'build','mission_agent',payload=dict(output_contract='text',agent_snapshot=snap,allowed_tools=[],model_override='strong:27b'))
  seen=[];job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  replies=[dict(message=dict(content=''),done_reason='stop',prompt_eval_count=9000,eval_count=0),dict(message=dict(content='Kész eredmény'))]
  with patch('studio.local_api',side_effect=lambda *a,**k:seen.append(a[2]['model']) or replies.pop(0)):out=s._run_agent(job)
  self.assertEqual(set(seen),{'strong:27b'},'the retry model wins over the snapshot')
  self.assertEqual(out,'Kész eredmény');self.assertFalse(replies)
  log=s.rows("SELECT details FROM job_log WHERE job=? AND kind='empty_reply'",(jid,));self.assertEqual(json.loads(log[0]['details'])['prompt_eval_count'],9000)
if __name__=='__main__':unittest.main()
