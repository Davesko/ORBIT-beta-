import unittest
from unittest.mock import patch
import model_hub
class HubTests(unittest.TestCase):
 def tearDown(self):model_hub._cache=(None,[],[])
 def test_first_inventory_is_not_empty_during_process_start(self):
  model_hub._cache=(None,[],[])
  with patch('model_hub.time.monotonic',return_value=.1),patch('model_hub.inventory',return_value=([dict(name='qwen3.8:27b')],[])) as inventory:
   self.assertEqual(model_hub.models()[0]['name'],'qwen3.8:27b');model_hub.models();self.assertEqual(inventory.call_count,1)
 def test_inference_timeout_is_not_mislabeled_as_disconnected_ssd(self):
  with patch('model_hub.models',return_value=[dict(name='qwen3.8:27b',port=11434)]),patch('model_hub.release_other'),patch('model_hub.raw',side_effect=TimeoutError()):
   with self.assertRaisesRegex(ValueError,'modellhívási hiba'):model_hub.request('api/chat',dict(model='qwen3.8:27b'))
if __name__=='__main__':unittest.main()
