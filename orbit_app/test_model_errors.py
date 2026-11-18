import io,unittest,urllib.error
from unittest import mock
import model_hub
class ModelErrorTests(unittest.TestCase):
 def call(self,exc):
  with mock.patch.object(model_hub,'models',return_value=[dict(name='m',storage='SSD',port=11435)]),mock.patch.object(model_hub,'release_other'),mock.patch.object(model_hub,'raw',side_effect=exc):
   with self.assertRaises(ValueError) as ctx:model_hub.request('api/chat',dict(model='m',messages=[]))
  return str(ctx.exception)
 def test_refused_request_is_not_a_connection_failure(self):
  # Self-heal restarts the model server after repeated "nem sikerült kapcsolódni" errors; a
  # malformed request must never count as one.
  msg=self.call(urllib.error.HTTPError('u',400,'Bad Request',{},io.BytesIO(b'{"error":"no user query found in messages"}')))
  self.assertIn('elutasította',msg);self.assertIn('no user query',msg);self.assertNotIn('kapcsolódni',msg)
 def test_refused_connection_still_reported(self):
  self.assertIn('kapcsolódni',self.call(urllib.error.URLError(ConnectionRefusedError())))
if __name__=='__main__':unittest.main()
