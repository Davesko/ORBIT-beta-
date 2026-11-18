import unittest,tempfile,threading,json,urllib.request,urllib.error
from pathlib import Path
import mobile_server
class MobileTests(unittest.TestCase):
 def test_secret_persistent_private(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);a=mobile_server.token(p);self.assertGreater(len(a),40);self.assertEqual(a,mobile_server.token(p));self.assertEqual((p/'integrations/mobile/access.key').stat().st_mode&0o777,0o600)
 def test_all_palette_text_pairs(self):
  def luminance(h):
   v=[int(h[i:i+2],16)/255 for i in (1,3,5)];v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v];return sum(a*b for a,b in zip(v,(.2126,.7152,.0722)))
  for name,_,c in json.loads((Path(__file__).parent/'web/palettes.json').read_text()):
   for foreground in c[3:5]:
    for bg in c[:3]:
     a,b=sorted([luminance(foreground),luminance(bg)])
     self.assertGreaterEqual((b+.05)/(a+.05),4.5,(name,foreground,bg))
 def test_http_denies_unauthorized_and_cross_origin(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);server=mobile_server.serve(0,root);threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_address[1])
   try:
    with urllib.request.urlopen(base+'/') as r:self.assertIn(b'ORBIT',r.read())
    for path,headers,payload,expected in [('/api/state',{},None,401),('/api/chat',{'Authorization':'Bearer '+mobile_server.token(root),'Origin':'https://evil.example'},b'{}',403),('/api/chat',{'Authorization':'Bearer '+mobile_server.token(root)},b'{}',400)]:
     with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(urllib.request.Request(base+path,data=payload,headers=headers))
     self.assertEqual(caught.exception.code,expected)
   finally:server.shutdown();server.server_close()
