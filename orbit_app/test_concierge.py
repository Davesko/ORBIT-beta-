import json,sys,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import concierge,launch,venture,venture_build

class Shop(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  body={'/':'<title>Minta Bolt</title><a href="/aszf">ÁSZF</a>','/aszf':'<p>Békéltető testület</p>','/robots.txt':''}.get(self.path.split('?')[0])
  if body is None:self.send_response(404);self.end_headers();return
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body.encode())

REPORT='''import gzip,json,sys
host=sys.argv[1].split('//')[1]
pages=json.load(gzip.open('realdata/'+host+'.json.gz','rt'))['pages']
print('Jelentés: '+str(len(pages))+' oldal, békéltető: '+('igen' if any('Békéltető' in p[2] for p in pages) else 'nem'))
'''

class ConciergeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  venture.configure(self.s,dict(enabled=True))
  plan=dict(name='Bolt Radar',problem='p',buyer='b',offer='Webáruház-ellenőrzés',revenue_model='r',costs='c',hypothesis='h',validation='v',progress='p',next_action='n',decision='continue',evidence=[],automation_level=90,human_steps=[],files=[dict(name='README.md',content='terv')])
  with patch('venture.idea_scores',return_value={}):iid=venture.save_result(self.s,venture.PID,'r1',plan)['idea_id']
  venture_build.choose(self.s,iid);self.f=venture_build.active(self.s);self.product=self.s.safe_path(venture.PID,venture_build.folder(self.f));self.product.mkdir(parents=True,exist_ok=True)
  (self.product/'report.py').write_text(REPORT)
  (self.product/'launch-form.json').write_text(json.dumps(dict(heading='Kérd az ellenőrzést',report_command=['report.py','{site}'],record_links='aszf',record_pages=5)))
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Shop);threading.Thread(target=self.server.serve_forever,daemon=True).start()
  self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
  self.site='http://127.0.0.1:'+str(self.server.server_address[1])
 def test_a_request_becomes_a_report_and_an_email_the_owner_sends(self):
  # TermékA's concierge offer: the visitor leaves an address, ORBIT prepares, the owner sends.
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  people=[dict(email='a@bolt.hu',site=self.site,src='fb',at=1),dict(email='b@bolt.hu',site='',src='direkt',at=2)]
  with patch('concierge.signups',return_value=people):
   self.assertEqual(concierge.process(self.s,self.f,dict(status='live')),1)
   self.assertEqual(concierge.process(self.s,self.f,dict(status='live')),0,'a prepared request is not redone')
  acts=concierge.actions(self.s,self.f);self.assertEqual(len(acts),1,'no site, no report')
  a=acts[0];self.assertEqual(a['kind'],'contact');self.assertIn('127.0.0.1',a['title'])
  self.assertIn('Címzett: a@bolt.hu',a['draft']);self.assertIn('Jelentés: 2 oldal, békéltető: igen',a['draft'])
  self.assertNotIn(str(self.s.root/'projects'),str(concierge.store_path(self.s,self.f['idea_id'])),'emails stay out of the project files')
  self.assertEqual(venture.configure(self.s,dict(concierge_sent=dict(idea_id=self.f['idea_id'],key=a['concierge'])))['concierge'],'sent')
  self.assertEqual(concierge.actions(self.s,self.f),[])
 def test_a_request_orbit_cannot_check_is_retried_once_then_goes_to_the_owner(self):
  # The first real request (2026-11-01) failed and nobody saw it: no report, no email, no to-do.
  people=[dict(email='a@bolt.hu',site='https://tiltott.example',src='fb_ads',at=1)]
  with patch('concierge.signups',return_value=people),patch('site_recorder.record',side_effect=PermissionError('a robots.txt nem engedi')) as rec:
   for _ in range(3):concierge.process(self.s,self.f,dict(status='live'))
  self.assertEqual(rec.call_count,2,'one retry, then it waits for the owner')
  a=concierge.actions(self.s,self.f);self.assertEqual(len(a),1)
  self.assertIn('nem sikerült ellenőrizni',a[0]['title']);self.assertIn('Címzett: a@bolt.hu',a[0]['draft']);self.assertIn('nem engedi az automatikus olvasást',a[0]['draft'])
  venture.configure(self.s,dict(concierge_sent=dict(idea_id=self.f['idea_id'],key=a[0]['concierge'])));self.assertEqual(concierge.actions(self.s,self.f),[])
 def test_every_request_stays_listed_with_where_it_stands(self):
  # A sent report used to vanish from the page; the owner could not see who had asked for what.
  concierge.save(self.s,self.f['idea_id'],dict(a=dict(email='a@bolt.hu',site='https://a-bolt.hu',src='fb_ads',at=1793537419026,status='sent',sent=5),
   b=dict(email='b@bolt.hu',site='https://b-bolt.hu',src='',at=1793537500000,status='failed',tries=1),c=dict(email='c@bolt.hu',site='',src='direkt',at=1793537600000,status='nosite')))
  r=concierge.requests(self.s,self.f)
  self.assertEqual([(x['site'],x['status']) for x in r],[('','nosite'),('b-bolt.hu','new'),('a-bolt.hu','sent')],'newest first; a failure still to be retried is in progress')
  self.assertEqual(r[2]['at'],1793537419.026,'the worker stores milliseconds');self.assertEqual(r[1]['src'],'direkt');self.assertIn('elküldve',r[2]['label'])
  self.assertEqual(venture_build.view(self.s,venture_build.mission_id(self.s),self.f)['requests'],r)
 def test_sign_ups_come_from_the_worker_store_and_the_service_runs_half_hourly(self):
  kv={'e:a@bolt.hu':json.dumps(dict(at=5,src='fb',site='https://a-bolt.hu')).encode()}
  def fake(method,path,body=None,headers=None,root=None,raw=False,timeout=30):
   if '/keys?prefix=e%3A' in path:return [dict(name=k) for k in kv]
   return kv[launch.urllib.parse.unquote(path.rsplit('/',1)[1])]
  with patch('launch.cf',side_effect=fake):
   self.assertEqual(concierge.signups(dict(account='acc',namespace='ns')),[dict(email='a@bolt.hu',at=5,src='fb',site='https://a-bolt.hu')])
  launch.write_state(self.s,venture_build.folder(self.f),dict(status='live',account='acc',namespace='ns'))
  with patch('concierge.process',return_value=0) as run:
   concierge.tick(self.s,now=time.time());concierge.tick(self.s,now=time.time()+60)
   self.assertEqual(run.call_count,1,'at most every half hour')

if __name__=='__main__':unittest.main()
