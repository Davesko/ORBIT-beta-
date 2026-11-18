import json,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
import inference_stream

class Stalling(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length') or 0))
  self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
  for word in ('Szia',' ORBIT'):self.wfile.write((json.dumps(dict(message=dict(content=word)))+'\n').encode());self.wfile.flush()
  time.sleep(3)

class StreamStallTests(unittest.TestCase):
 def test_a_silent_stream_is_reported_as_a_retryable_stall(self):
  # Cycle 167: the 27B went quiet for 30 s after 22 tokens and an 11-minute build was lost.
  server=ThreadingHTTPServer(('127.0.0.1',0),Stalling);threading.Thread(target=server.serve_forever,daemon=True).start()
  self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  with patch.object(inference_stream,'SILENCE',1),self.assertRaisesRegex(ValueError,r'1 mp-ig nem válaszolt a válasz közben \(2 token után'):
   inference_stream.chat(server.server_address[1],dict(model='kicsi:1b',messages=[dict(role='user',content='szia')]),60,'/nonexistent')
 def test_the_27b_gets_more_patience_than_small_models(self):
  self.assertEqual(inference_stream.silence_limit('qwen3.8:27b-q4_K_M'),120);self.assertEqual(inference_stream.silence_limit('qwen3.5:9b'),30);self.assertEqual(inference_stream.silence_limit(None),30)

if __name__=='__main__':unittest.main()
