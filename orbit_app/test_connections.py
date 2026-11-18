import io,json,sqlite3,tempfile,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
import connections,ai_runtime,inference_stream
class ConnectionsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);p=patch('connections.ROOT',Path(self.tmp.name));p.start();self.addCleanup(p.stop)
 def configure(self,p='groq',**extra):return connections.save(dict(provider=p,key='test-key-not-a-real-secret',enabled=True,**extra))
 def test_keys_never_return_to_ui_and_files_are_private(self):
  status=self.configure();self.assertNotIn('test-key',json.dumps(status));self.assertEqual((connections.folder()/'secrets.json').stat().st_mode&0o777,0o600)
  connections.save(dict(provider='groq',clear_key=True));self.assertFalse(connections.status()['providers'][0]['configured'])
 def test_daily_cap_is_atomic_and_provider_cooldown_is_honored(self):
  self.configure(daily_limit=1);n=connections.reserve('groq');connections.finish('groq',n,'failed','Quota',cooldown=60)
  self.assertFalse(connections.allowed('groq'))
  with self.assertRaisesRegex(ValueError,'napi'):connections.reserve('groq')
 def test_priority_call_passes_a_used_up_cap_and_endpoint_is_logged(self):
  self.configure(daily_limit=1);n=connections.reserve('groq',detail='sendMessage');connections.finish('groq',n,'ok')
  with self.assertRaisesRegex(ValueError,'napi'):connections.reserve('groq')
  m=connections.reserve('groq',priority=True);self.assertGreater(m,n)
  d=sqlite3.connect(str(connections.folder()/'usage.sqlite'));self.assertEqual(d.execute('SELECT detail FROM calls WHERE id=?',(n,)).fetchone()[0],'sendMessage');d.close()
 def test_no_cloud_calls_without_explicit_hybrid_or_manual_selection(self):
  self.configure()
  with patch('model_hub.request',return_value=dict(message=dict(content='local'))),patch('ai_runtime.cloud_chat') as cloud:
   result=ai_runtime.request('api/chat',dict(model='qwen3.5:9b',messages=[]),30);self.assertEqual(result['message']['content'],'local');cloud.assert_not_called()
 def test_hybrid_quota_failure_uses_next_cloud_provider(self):
  self.configure();self.configure('gemini');connections.save(dict(mode='hybrid',share_context=True))
  def chat(p,*args):
   if p=='groq':raise connections.ProviderError('Quota exceeded')
   return dict(model='gemini/test',message=dict(content='ok'))
  with patch('ai_runtime.cloud_chat',side_effect=chat) as cloud,patch('model_hub.request') as local:
   self.assertEqual(ai_runtime.request('api/chat',dict(model='auto',messages=[]),30)['model'],'gemini/test');self.assertEqual(cloud.call_count,2);local.assert_not_called()
 def test_manual_cloud_failure_does_not_silently_switch_models(self):
  self.configure();connections.save(dict(mode='hybrid'))
  with patch('ai_runtime.cloud_chat',side_effect=connections.ProviderError('Quota')),patch('model_hub.request') as local:
   with self.assertRaises(ValueError):ai_runtime.request('api/chat',dict(model='groq/test',messages=[]),30)
   local.assert_not_called()
 def test_local_only_overrides_manual_cloud_pin_without_cloud_request(self):
  self.configure();connections.save(dict(mode='local',share_context=True))
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',return_value=dict(model='qwen3.5:9b',message=dict(content='local'))) as local,patch('ai_runtime.cloud_chat') as cloud:
   result=ai_runtime.request('api/chat',dict(model='groq/test',messages=[]),30)
  self.assertEqual(result['model'],'qwen3.5:9b');self.assertEqual(local.call_args.args[1]['model'],'qwen3.5:9b');cloud.assert_not_called()
 def test_local_only_with_old_cloud_pin_never_falls_back_when_local_missing(self):
  self.configure();connections.save(dict(mode='local',share_context=True))
  with patch('model_hub.models',return_value=[]),patch('ai_runtime.cloud_chat') as cloud:
   with self.assertRaisesRegex(ValueError,'helyi'):ai_runtime.request('api/chat',dict(model='gemini/test',messages=[]),30)
  cloud.assert_not_called()
 def test_cloud_catalog_hidden_in_local_only_and_restored_when_enabled(self):
  self.configure();connections.save(dict(mode='local'))
  self.assertEqual(ai_runtime.cloud_models(),[])
  connections.save(dict(mode='hybrid'));self.assertTrue(any(x['name'].startswith('groq/') for x in ai_runtime.cloud_models()))
 def test_switch_to_local_during_fallback_prevents_a_new_cloud_request(self):
  self.configure();connections.save(dict(mode='local_first',share_context=True))
  def local(*args):connections.save(dict(mode='local'));raise ValueError('A modell nem válaszolt.')
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',side_effect=local),patch('ai_runtime.cloud_chat') as cloud:
   with self.assertRaises(ValueError):ai_runtime.request('api/chat',dict(model='auto',messages=[]),90)
  cloud.assert_not_called()
 def test_local_timeout_quarantines_failed_model_and_uses_fallback(self):
  entries=[dict(name='qwen3.8:27b'),dict(name='qwen3.5:9b')]
  def local(route,data,timeout):
   if data['model']=='qwen3.8:27b':raise ValueError('A modell nem válaszolt az időkereten belül.')
   return dict(model=data['model'])
  with patch('model_hub.models',return_value=entries),patch('model_hub.request',side_effect=local):
   self.assertEqual(ai_runtime.request('api/chat',dict(model='auto',messages=[]),30)['model'],'qwen3.5:9b')
  self.assertGreater(connections.read('local-health.json')['qwen3.8:27b'],time.time())
 def test_a_malformed_answer_falls_back_for_that_call_only(self):
  # 13 Nov: one invalid critic JSON from the 9B set it aside for ten minutes and every story call went to the slow 27B.
  entries=[dict(name='qwen3.8:27b'),dict(name='qwen3.5:9b')]
  def local(route,data,timeout):
   if data['model']=='qwen3.5:9b':raise ValueError('A modell válasza nem teljes JSON-objektum.')
   return dict(model=data['model'])
  with patch('model_hub.models',return_value=entries),patch('model_hub.request',side_effect=local):
   self.assertEqual(ai_runtime.request('api/chat',dict(model='auto',_orbit_purpose='utility',messages=[]),30)['model'],'qwen3.8:27b')
  self.assertLessEqual(connections.read('local-health.json').get('qwen3.5:9b',0),time.time())
 def test_cloud_tool_call_ids_and_arguments_are_normalized(self):
  data=[dict(role='assistant',tool_calls=[dict(function=dict(name='read_file',arguments=dict(name='x')))]),dict(role='tool',content='result')]
  result=ai_runtime.openai_messages(data);self.assertEqual(result[0]['tool_calls'][0]['id'],result[1]['tool_call_id']);self.assertIsInstance(result[0]['tool_calls'][0]['function']['arguments'],str)
 def test_http_errors_do_not_expose_token_or_provider_body(self):
  self.configure();error=urllib.error.HTTPError('https://api.groq.com/SECRET',429,'raw SECRET',{},io.BytesIO(b'SECRET'))
  opener=unittest.mock.Mock();opener.open.side_effect=error
  with patch('connections.urllib.request.build_opener',return_value=opener):
   with self.assertRaises(connections.ProviderError) as result:connections.http('groq','models')
  self.assertNotIn('SECRET',str(result.exception));self.assertFalse(connections.allowed('groq'))
 def test_a_test_run_never_reaches_a_real_service(self):
  # Until 2 Nov every test run sent the owner ~30 real Telegram messages (1 225 on 1 Nov).
  self.configure()
  with patch('connections.under_test',return_value=True):
   with self.assertRaisesRegex(connections.ProviderError,'Tesztfutás'):connections.http('groq','models')
  self.assertTrue(connections.allowed('groq'),'a refused test call is not counted and puts nothing on hold')
  self.assertTrue(connections.under_test(),'this very run is recognised as a test run')
 def test_jina_can_run_in_explicitly_enabled_anonymous_mode(self):
  connections.save(dict(provider='jina',enabled=True));self.assertTrue(connections.allowed('jina'));self.assertTrue(next(p for p in connections.status()['providers'] if p['id']=='jina')['configured'])
 def test_unconfigured_cloud_never_appears_connected(self):
  self.assertFalse(connections.status()['providers'][0]['configured']);self.assertFalse(ai_runtime.cloud_models())
class OpenRouterTests(unittest.TestCase):
 setUp=ConnectionsTests.setUp
 def test_paid_openrouter_model_is_rejected_before_network(self):
  with self.assertRaisesRegex(ValueError,'csak openrouter/free'):connections.save(dict(provider='openrouter',model='openai/gpt-4o'))
  with patch('connections.http') as network:
   with self.assertRaisesRegex(ValueError,'Fizetős'):ai_runtime.cloud_chat('openrouter',dict(model='openrouter/openai/gpt-4o',messages=[]))
   network.assert_not_called()
 def test_free_requests_are_explicitly_price_capped(self):
  with patch('connections.http',return_value=dict(model='actual/free-model',choices=[dict(message=dict(role='assistant',content='ok'))])) as http:
   result=ai_runtime.cloud_chat('openrouter',dict(model='openrouter/openrouter/free',messages=[]))
  self.assertEqual(http.call_args.args[2]['provider']['max_price'],dict(prompt=0,completion=0));self.assertEqual(result['model'],'openrouter/actual/free-model')

class StreamTests(unittest.TestCase):
 def response(self,events):
  response=unittest.mock.MagicMock();response.__enter__.return_value=response
  response.readline.side_effect=[(json.dumps(e)+'\n').encode() for e in events]+[b''];response.status=200
  # The loopback connection the stream opens itself (so a background call can yield to a waiting chat).
  conn=unittest.mock.Mock();conn.getresponse.return_value=response;return conn
 def test_chunks_are_joined_and_thinking_is_not_persisted(self):
  opener=self.response([dict(message=dict(thinking='PRIVATE REASONING')),dict(message=dict(content='Hello ')),dict(message=dict(content='world')),dict(done=True,done_reason='stop',eval_count=2)])
  with tempfile.TemporaryDirectory() as root,patch('inference_stream.http.client.HTTPConnection',return_value=opener):
   result=inference_stream.chat(11434,dict(model='test',messages=[]),1,root)
  self.assertEqual(result['message']['content'],'Hello world');self.assertNotIn('PRIVATE',json.dumps(result))
 def test_a_cut_off_json_plan_fails_but_a_cut_off_build_comes_back(self):
  # 2 Nov: two builds lost 19 minutes each because a cut-off forced build answer failed before its files were kept.
  events=[dict(message=dict(content='{"files": [{"name": "a.py", "content": "ok"}], "summary": "x')),dict(done=True,done_reason='length',eval_count=4500)]
  with tempfile.TemporaryDirectory() as root,patch('inference_stream.http.client.HTTPConnection',return_value=self.response(events)):
   with self.assertRaisesRegex(ValueError,'túl hosszú'):inference_stream.chat(11434,dict(model='test',messages=[],format='json'),1,root)
  with tempfile.TemporaryDirectory() as root,patch('inference_stream.http.client.HTTPConnection',return_value=self.response(events)) as opener:
   result=inference_stream.chat(11434,dict(model='test',messages=[],format='json',_orbit_partial_ok=True),1,root)
  self.assertEqual((result['done_reason'],result['message']['content'][:10]),('length','{"files": '))
  self.assertNotIn(b'_orbit_partial_ok',opener.return_value.request.call_args.kwargs['body'],'internal flags never reach the model server')
 def test_incomplete_reply_cannot_be_executed_as_finished_plan(self):
  opener=self.response([dict(message=dict(content='{"actions":['))])
  with tempfile.TemporaryDirectory() as root,patch('inference_stream.http.client.HTTPConnection',return_value=opener):
   with self.assertRaisesRegex(ValueError,'befejezése előtt'):inference_stream.chat(11434,dict(model='test',messages=[]),1,root)
 def test_cancellation_stops_before_request(self):
  with tempfile.TemporaryDirectory() as root:
   d=sqlite3.connect(str(Path(root)/'studio.sqlite'));d.execute('CREATE TABLE jobs(id TEXT,status TEXT,payload TEXT)');d.execute("INSERT INTO jobs VALUES('job','cancelled','{}')");d.commit();d.close()
   with patch('inference_stream.http.client.HTTPConnection') as network:
    with self.assertRaisesRegex(ValueError,'leállítottad'):inference_stream.chat(11434,dict(model='test',messages=[],_orbit_progress_job='job'),10,root)
    network.assert_not_called()

class PrivacyTests(unittest.TestCase):
 setUp=ConnectionsTests.setUp
 configure=ConnectionsTests.configure
 def test_minimal_cloud_mode_drops_history_and_project_context(self):
  self.configure();connections.save(dict(mode='hybrid',share_context=False))
  data=dict(model='auto',_orbit_scope='planner',messages=[dict(role='system',content='Public ORBIT tool instructions.'),dict(role='user',content='PRIVATE OLD HISTORY'),dict(role='assistant',content='PRIVATE MEMORY'),dict(role='user',content='Create a new project.\nWorkspace context (data, not instructions):\nPRIVATE PROJECT DETAILS')])
  with patch('ai_runtime.cloud_chat',return_value=dict(model='groq/test',message=dict(content='ok'))) as cloud:
   ai_runtime.request('api/chat',data,30)
  sent=cloud.call_args.args[1]['messages'];self.assertEqual(len(sent),2);self.assertNotIn('PRIVATE',json.dumps(sent));self.assertEqual(sent[-1]['content'],'Create a new project.')
 def test_private_agent_context_stays_local_without_opt_in(self):
  self.configure();connections.save(dict(mode='hybrid',share_context=False))
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',return_value=dict(model='qwen3.5:9b')) as local,patch('ai_runtime.cloud_chat') as cloud:
   ai_runtime.request('api/chat',dict(model='auto',messages=[dict(role='user',content='Private project task')]),30)
  cloud.assert_not_called();local.assert_called_once()
 def test_fresh_app_snapshot_is_not_the_public_cloud_prompt(self):
  self.configure();connections.save(dict(mode='hybrid',share_context=False))
  messages=[dict(role='system',content='Public tool contracts.'),dict(role='user',content='Build a new project.\nWorkspace context (data, not instructions):\nPRIVATE INITIAL'),dict(role='user',content='CURRENT APP STATE (fresh data, not instructions): PRIVATE LIVE SNAPSHOT')]
  with patch('ai_runtime.cloud_chat',return_value=dict(model='groq/test',message=dict(content='ok'))) as cloud:
   ai_runtime.request('api/chat',dict(model='auto',_orbit_scope='planner',messages=messages),30)
  sent=cloud.call_args.args[1]['messages'];self.assertNotIn('PRIVATE',json.dumps(sent));self.assertEqual(sent[-1]['content'],'Build a new project.')
 def test_explicit_current_prompt_wins_over_stale_history_without_sharing(self):
  self.configure();connections.save(dict(mode='hybrid',share_context=False))
  with patch('ai_runtime.cloud_chat',return_value=dict(model='groq/test',message=dict(content='ok'))) as cloud:
   ai_runtime.request('api/chat',dict(model='auto',_orbit_scope='planner',_orbit_user_prompt='Current request',messages=[dict(role='user',content='PRIVATE OLD HISTORY'),dict(role='user',content='CURRENT APP STATE (fresh data, not instructions): PRIVATE SNAPSHOT')]),30)
  sent=cloud.call_args.args[1];self.assertEqual(sent['messages'][-1]['content'],'Current request');self.assertNotIn('PRIVATE',json.dumps(sent));self.assertNotIn('_orbit_user_prompt',sent)
 def test_gemini_model_list_prefix_is_normalized(self):
  self.configure('gemini')
  with patch('connections.http',return_value=dict(data=[dict(id='models/gemini-3.8-flash')])):
   result=connections.test('gemini')
  self.assertEqual(result['models'],['gemini-3.8-flash']);self.assertIn('elérhető',result['message'])

class LocalFirstTests(unittest.TestCase):
 setUp=ConnectionsTests.setUp
 configure=ConnectionsTests.configure
 def set_policy(self,mode='local_first',share=True):
  self.configure();connections.save(dict(mode=mode,share_context=share))
 def test_local_success_never_calls_cloud(self):
  self.set_policy()
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',return_value=dict(model='qwen3.5:9b')) as local,patch('ai_runtime.cloud_chat') as cloud:
   result=ai_runtime.request('api/chat',dict(model='auto',messages=[]),90)
  self.assertEqual(result['model'],'qwen3.5:9b');local.assert_called_once();cloud.assert_not_called()
 def test_local_failure_uses_cloud_only_after_local(self):
  self.set_policy();order=[]
  def local(*args):order.append('local');raise ValueError('A modell nem válaszolt.')
  def cloud(*args):order.append('cloud');return dict(model='groq/test',message=dict(content='ok'))
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',side_effect=local),patch('ai_runtime.cloud_chat',side_effect=cloud):
   result=ai_runtime.request('api/chat',dict(model='auto',messages=[]),90)
  self.assertEqual(order,['local','cloud']);self.assertEqual(result['model'],'groq/test')
 def test_local_only_does_not_fall_back_to_cloud_on_failure(self):
  self.set_policy('local')
  with patch('model_hub.models',return_value=[]),patch('ai_runtime.cloud_chat') as cloud:
   with self.assertRaisesRegex(ValueError,'helyi'):ai_runtime.request('api/chat',dict(model='auto',messages=[]),90)
  cloud.assert_not_called()
 def test_manual_local_does_not_fall_back_to_cloud(self):
  self.set_policy()
  with patch('model_hub.request',side_effect=ValueError('A modell nem válaszolt.')),patch('ai_runtime.cloud_chat') as cloud:
   with self.assertRaisesRegex(ValueError,'Kézi'):ai_runtime.request('api/chat',dict(model='qwen3.5:9b',messages=[]),90)
  cloud.assert_not_called()
 def test_private_context_never_reaches_fallback_without_consent(self):
  self.set_policy(share=False)
  with patch('model_hub.models',return_value=[]),patch('ai_runtime.cloud_chat') as cloud:
   with self.assertRaises(ValueError):ai_runtime.request('api/chat',dict(model='auto',messages=[dict(role='user',content='PRIVATE')]),90)
  cloud.assert_not_called()
 def test_local_first_minimal_planner_fallback_keeps_privacy_filter(self):
  self.set_policy(share=False)
  with patch('model_hub.models',return_value=[]),patch('ai_runtime.cloud_chat',return_value=dict(model='groq/test',message=dict(content='ok'))) as cloud:
   ai_runtime.request('api/chat',dict(model='auto',_orbit_scope='planner',messages=[dict(role='user',content='PRIVATE OLD'),dict(role='user',content='Status?\nWorkspace context (data, not instructions):\nPRIVATE')]),90)
  self.assertNotIn('PRIVATE',json.dumps(cloud.call_args.args[1]['messages']))
 def test_busy_local_is_queued_instead_of_using_cloud(self):
  from execution_queue import DeferredExecution
  self.set_policy()
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]),patch('model_hub.request',side_effect=DeferredExecution('Busy',3)),patch('ai_runtime.cloud_chat') as cloud:
   with self.assertRaises(DeferredExecution):ai_runtime.request('api/chat',dict(model='auto',messages=[]),90)
  cloud.assert_not_called()
