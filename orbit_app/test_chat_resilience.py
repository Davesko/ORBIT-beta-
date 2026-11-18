import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import ai_runtime,commander,missions
class ChatResilienceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
 def test_quota_and_disabled_providers_count_as_unavailable(self):
  for e in ('Gemini: A szolgáltatói kvóta vagy sebességkorlát elérve.','Ez a felhőkapcsolat nincs beállítva, ki van kapcsolva vagy kvótavárakozásban van.','HTTP 429 rate limit'):self.assertTrue(ai_runtime.unavailable(ValueError(e)))
  self.assertFalse(ai_runtime.unavailable(ValueError('A modell válasza nem teljes JSON-objektum.')))
 def test_explicit_cloud_model_falls_back_to_automatic_routing(self):
  calls=[]
  def fake(route,data=None,timeout=8):
   calls.append(data['model'])
   return {'message':{'content':'szia'},'model':'qwen3.5:9b'}
  cfg=dict(mode='hybrid',preferred='gemini',share_context=True,providers=dict(gemini=dict(enabled=True,model='gemini-x')))
  with patch('connections.settings',return_value=cfg),patch('connections.allowed',return_value=False),patch('ai_runtime.local_job',return_value=False),patch('ai_runtime.record'):
   real=ai_runtime.request
   def wrapped(route,data=None,timeout=8):
    if data.get('model')=='auto':return fake(route,data,timeout)
    return real(route,data,timeout)
   with patch('ai_runtime.request',side_effect=wrapped):
    r=ai_runtime.request('api/chat',dict(model='gemini/gemini-x',messages=[dict(role='user',content='hello')]),60)
  self.assertEqual(r['message']['content'],'szia');self.assertEqual(calls,['auto'])
 def test_fallback_note_names_the_unavailable_model(self):
  self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,payload) VALUES(?,?,?,?,?,?,?)',('j','universe','a','command','running','p',json.dumps(dict(model_fallback=dict(requested='gemini/gemini-x',reason='Gemini: kvóta elérve')))));self.s.db.commit()
  self.assertIn('Gemini: elfogyott a kerete',commander.fallback_note(self.s,dict(id='j')))
if __name__=='__main__':unittest.main()
