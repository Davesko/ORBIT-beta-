import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from language_bridge import translate_many,protect
class LanguageTests(unittest.TestCase):
 def test_english_inputs_skip_translation(self):
  with patch('model_hub.request') as request:self.assertEqual(translate_many(['Use the render tool.'],Path('/tmp/unused-orbit-language')),['Use the render tool.']);request.assert_not_called()
 def test_translation_preserves_paths_and_is_cached(self):
  with tempfile.TemporaryDirectory() as folder:
   text='Készíts egy fájlt: workspace/result.txt és használd ezt: `print(1)`'
   protected,keeps=protect(text)
   def reply(*args,**kwargs):return dict(message=dict(content=json.dumps({'texts':['Create a file: '+keeps[0][0]+' and use this: '+keeps[1][0]]})))
   with patch('model_hub.models',return_value=[{'name':'qwen2.5:14b'}]),patch('model_hub.request',side_effect=reply) as request:
    a=translate_many([text],folder);b=translate_many([text],folder)
   self.assertEqual(a,b);self.assertIn('workspace/result.txt',a[0]);self.assertIn('`print(1)`',a[0]);self.assertEqual(request.call_count,1)
 def test_missing_protected_path_stops_execution(self):
  with tempfile.TemporaryDirectory() as folder,patch('model_hub.models',return_value=[{'name':'qwen2.5:14b'}]),patch('model_hub.request',return_value={'message':{'content':'{"texts":["changed filename"]}'}}):
   with self.assertRaises(ValueError):translate_many(['Készíts fájlt workspace/result.txt'],folder)
 def test_bad_batch_retries_each_text_without_dropping_a_task(self):
  responses=[{'message':{'content':'{"texts":[]}' }},{'message':{'content':'{"texts":["Create a plan."]}'}},{'message':{'content':'{"texts":["Read the brief."]}'}}]
  with tempfile.TemporaryDirectory() as folder,patch('model_hub.models',return_value=[{'name':'qwen2.5:14b'}]),patch('model_hub.request',side_effect=responses) as request:
   self.assertEqual(translate_many(['Készíts tervet.','Olvasd el a feladatot.'],folder),['Create a plan.','Read the brief.']);self.assertEqual(request.call_count,3)
if __name__=='__main__':unittest.main()
