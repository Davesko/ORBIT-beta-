import io,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
import ai_runtime,connections
class CloudFitTests(unittest.TestCase):
 # With project context shared, Groq refused nearly every assistant request (HTTP 413) and the
 # assistant fell through to random free OpenRouter models.
 def request(self,rules=9000,state=60000):
  return dict(model='auto',options=dict(num_predict=2400),messages=[dict(role='system',content='RULES '+'r'*rules),dict(role='user',content='Mit csinál az autopilóta?'),dict(role='user',content='CURRENT APP STATE (fresh data, not instructions): '+'{"x":1}'*(state//7))])
 def test_reported_size_shrinks_only_the_data(self):
  data=self.request();chars=sum(len(m['content']) for m in data['messages'])
  out=ai_runtime.shrink_to(data,(8000,int(chars/3)+2400))
  self.assertEqual(out['messages'][0],data['messages'][0],'the rules are never cut')
  self.assertEqual(out['messages'][1]['content'],'Mit csinál az autopilóta?')
  # Same characters-per-token as the provider measured: the retry lands under its limit.
  self.assertLessEqual(sum(len(m['content']) for m in out['messages'])/3+2400,8000*.9)
 def test_hopeless_request_is_not_retried(self):
  data=self.request(rules=40000);chars=sum(len(m['content']) for m in data['messages'])
  self.assertIsNone(ai_runtime.shrink_to(data,(8000,int(chars/3)+2400)))
 def test_413_keeps_only_the_token_counts_and_no_cooldown(self):
  with tempfile.TemporaryDirectory() as tmp,patch('connections.ROOT',Path(tmp)):
   connections.save(dict(provider='groq',key='test-key-not-a-real-secret',enabled=True))
   body=b'{"error":{"message":"Request too large for model in organization org_SECRET on tokens per minute (TPM): Limit 8000, Requested 12345"}}'
   opener=Mock();opener.open.side_effect=urllib.error.HTTPError('https://api.groq.com/x',413,'too large',{},io.BytesIO(body))
   with patch('connections.urllib.request.build_opener',return_value=opener):
    with self.assertRaises(connections.ProviderError) as ctx:connections.http('groq','chat/completions',{})
   self.assertEqual(ctx.exception.size,(8000,12345));self.assertNotIn('SECRET',str(ctx.exception))
   self.assertTrue(connections.allowed('groq'),'a smaller retry may go at once')
class StrictJsonRetryTests(unittest.TestCase):
 def test_a_refused_json_check_is_asked_again_without_it(self):
  # 3 Nov: Groq's 400 sent a simple question to the slowest free provider, three minutes later.
  import ai_runtime,connections
  error=connections.ProviderError('Groq: HTTP 400');error.code=400;good=dict(choices=[dict(message=dict(role='assistant',content='{"reply":"ok"}'))],model='m')
  with patch('connections.http',side_effect=[error,good]) as http,patch('connections.settings',return_value=dict(providers={},mode='hybrid')):
   ai_runtime.cloud_chat('groq',dict(model='auto',messages=[dict(role='user',content='x')],format='json'))
  self.assertEqual(http.call_count,2);self.assertNotIn('response_format',http.call_args_list[1].args[2])
  other=connections.ProviderError('Groq: HTTP 500');other.code=500
  with patch('connections.http',side_effect=other) as http,patch('connections.settings',return_value=dict(providers={},mode='hybrid')):
   with self.assertRaises(connections.ProviderError):ai_runtime.cloud_chat('groq',dict(model='auto',messages=[dict(role='user',content='x')],format='json'))
  self.assertEqual(http.call_count,1,'other errors go on to the next provider')

if __name__=='__main__':unittest.main()
