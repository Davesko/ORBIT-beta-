import io,json,unittest
from reply_stream import extract,read_sse
class ReplyStreamTests(unittest.TestCase):
 def test_partial_only_human_reply(self):
  self.assertEqual(extract('{"reads":[],"reply":"Szia, vil'),'Szia, vil')
  self.assertEqual(extract('{"actions":[{"prompt":"secret","reply":"hidden"}],"reply":"Hi"}'),'Hi')
  self.assertEqual(extract('{"actions":[{"reply":"hidden'), '')
 def test_escapes(self):
  self.assertEqual(extract('{"reply":"A\\nB\\u00e9'), 'A\nBé')
  self.assertEqual(extract('{"reply":"A\\u00'), 'A')
 def test_sse_actual_deltas(self):
  rows=[dict(choices=[dict(delta=dict(content=t),finish_reason=None)]) for t in ['{"reply":"','hello','"}']]
  rows.append(dict(choices=[dict(delta={},finish_reason='stop')]))
  seen=[];out=read_sse(io.BytesIO(b''.join(b'data: '+json.dumps(x).encode()+b'\n\n' for x in rows)+b'data: [DONE]\n'),seen.append)
  self.assertEqual(len(seen),3);self.assertEqual(out['choices'][0]['message']['content'],'{"reply":"hello"}')
 def test_truncated_stream_not_success(self):
  with self.assertRaises(ValueError):read_sse(io.BytesIO(b'data: [DONE]\n'),lambda _:None)
