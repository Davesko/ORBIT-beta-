import gzip,json,sys,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import product_check,site_recorder

PAGES={'/':'<html><title>Minta Bolt</title><a href="/aszf">ÁSZF</a> <a href="/kapcsolat?utm_source=fb">Kapcsolat</a> <a href="/tilos-aszf">Tiltott ÁSZF</a> <a href="https://masik.example/aszf">Külső ÁSZF</a> <a href="/termek">Termék</a></html>',
 '/aszf':'<p>Békéltető testület</p>','/kapcsolat':'<p>info@minta.hu</p>','/tilos-aszf':'<p>titok</p>','/robots.txt':'User-agent: *\nDisallow: /tilos'}

class Site(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  # Like Cloudflare: Python's default User-Agent gets 403, even for robots.txt.
  if self.headers.get('User-Agent','').startswith('Python-urllib'):self.send_response(403);self.end_headers();return
  path=self.path.split('?')[0];body=PAGES.get(path)
  if body is None:self.send_response(404);self.end_headers();return
  self.send_response(200);self.send_header('Content-Type','text/plain' if path.endswith('.txt') else 'text/html; charset=utf-8');self.end_headers();self.wfile.write(body.encode())

class RecorderTests(unittest.TestCase):
 def setUp(self):
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Site);threading.Thread(target=self.server.serve_forever,daemon=True).start()
  self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
  self.url='http://127.0.0.1:'+str(self.server.server_address[1])
 def test_records_the_same_site_legal_pages_within_robots(self):
  # A concierge request names a site anyone could type in; ORBIT's own fetcher reads it, not product code.
  r=site_recorder.record(self.url,words=r'ászf|aszf|kapcsolat',max_pages=7,delay=0)
  asked=[p[0] for p in r['pages']]
  self.assertEqual(asked,[self.url,self.url+'/aszf',self.url+'/kapcsolat'],'home, legal pages; tracking dropped; robots and other sites respected')
  self.assertIn('Békéltető',r['pages'][1][2])
 def test_robots_is_read_with_orbits_user_agent(self):
  # Python's own robots reader sent its default User-Agent; the 403 it got meant "disallow all".
  r=site_recorder.robots_for(self.url)
  self.assertTrue(r.can_fetch(site_recorder.UA,self.url+'/aszf'));self.assertFalse(r.can_fetch(site_recorder.UA,self.url+'/tilos-aszf'))
  PAGES.pop('/robots.txt');self.addCleanup(PAGES.__setitem__,'/robots.txt','User-agent: *\nDisallow: /tilos')
  self.assertTrue(site_recorder.robots_for(self.url).can_fetch(site_recorder.UA,self.url+'/aszf'),'no robots.txt: no rules')
 def test_the_report_runs_offline_on_the_recording(self):
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  r=site_recorder.record(self.url,words=r'ászf',delay=0)
  with tempfile.TemporaryDirectory() as d:
   Path(d,'report.py').write_text('''import gzip,json,os,sys,urllib.request
host=sys.argv[1].split('//')[1]
data=json.load(gzip.open('realdata/'+host+'.json.gz','rt'))
print('oldalak:',len(data['pages']),'offline:',os.environ.get('ORBIT_OFFLINE'))
try:urllib.request.urlopen('https://example.com',timeout=5);print('net: elérhető')
except Exception:print('net: tiltva')
''')
   out=product_check.run_report(d,r,['report.py',r['url']])
   self.assertTrue(out['ok'],out);self.assertIn('oldalak: 2 offline: 1',out['output']);self.assertIn('net: tiltva',out['output'])
   self.assertFalse(Path(d,'realdata').exists(),'the product folder is left as it was')
   with self.assertRaises(ValueError):product_check.run_report(d,r,['../report.py'])

if __name__=='__main__':unittest.main()
