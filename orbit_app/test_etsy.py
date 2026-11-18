import io,json,subprocess,sys,tempfile,time,unittest,urllib.error,urllib.parse
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import connections,etsy,venture_build

IDEA='abc123'
def listing(design,**kw):
 return dict(dict(id=design,marketplace='Etsy',title='TermékE Színezőlap – '+design+' (A4, 4–7 éves)',description='Egy kis asztronauta lebeg.',tags=['színezőlap','űr','4-7 éves'],price='4,99 EUR (unverified)',products=['PDF download']),**kw)

class EtsyCase(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  for p in (patch('connections.ROOT',root),):
   p.start();self.addCleanup(p.stop)
  self.s=Studio(root);self.addCleanup(self.s.db.close);self.s.create_project('Műhely','',pid=venture_build.PID);etsy._pace['at']=0
  self.product=self.s.safe_path(venture_build.PID,'workspace/product-'+IDEA);(self.product/'designs').mkdir(parents=True)
  self.calls=[];self.fail={}
  send=patch('etsy.send',side_effect=self.fake_send);send.start();self.addCleanup(send.stop)
  files=patch('etsy.build_files',side_effect=self.fake_files);files.start();self.addCleanup(files.stop)
  self.items([listing('astronaut'),listing('rocket')])
 def items(self,rows,drawn=None):
  (self.product/'listings.json').write_text(json.dumps(dict(shop={},listings=rows),ensure_ascii=False))
  for r in rows:
   if drawn is None or r['id'] in drawn:(self.product/'designs'/(r['id']+'.png')).write_bytes(b'png')
 def fake_files(self,s,product,design):
  a=Path(self.tmp.name)/(design+'.jpg');b=Path(self.tmp.name)/(design+'.pdf');a.write_bytes(b'jpg');b.write_bytes(b'pdf');return dict(preview=a,pdf=b)
 def fake_send(self,req,timeout=60):
  self.calls.append(req);path=req.full_url.split('/application/')[-1]
  for pattern,code in self.fail.items():
   if pattern in req.full_url:raise urllib.error.HTTPError(req.full_url,code,'x',Message(),io.BytesIO(json.dumps(dict(error='Etsy says no')).encode()))
  if 'oauth/token' in req.full_url:return json.dumps(dict(access_token='1.new',refresh_token='1.next',expires_in=3600)).encode()
  if path=='seller-taxonomy/nodes':return json.dumps(dict(results=[dict(id=1,name='Art',children=[dict(id=2078,name='Digital Prints',children=[])]),dict(id=9,name='Books',children=[dict(id=1234,name='Coloring Books',children=[])])])).encode()
  if path=='users/me':return json.dumps(dict(user_id=5,shop_id=77)).encode()
  if path=='shops/77':return json.dumps(dict(shop_name='UrKaland',currency_code='EUR',url='https://www.etsy.com/shop/UrKaland')).encode()
  if req.get_method()=='POST' and path=='shops/77/listings':return json.dumps(dict(listing_id=1000+len([c for c in self.calls if c.full_url.endswith('/listings')]))).encode()
  return b'{}'
 def login(self,currency='EUR'):
  connections.save(dict(provider='etsy',enabled=True,key='keystring1:secret456'))
  connections.atomic(etsy.TOKEN,dict(access_token='1.live',refresh_token='1.ref',expires_at=time.time()+3000))
  etsy.update_state(shop=dict(id=77,name='UrKaland',currency=currency,url=''))
 def tick(self,at=None):
  etsy._pace['at']=0;return etsy.tick(self.s,at or time.time())
 def row(self,design='astronaut'):return etsy.row_of(self.s,IDEA,design)
 def sent(self,method,suffix):return [c for c in self.calls if c.get_method()==method and c.full_url.endswith(suffix)]

class UploadTests(EtsyCase):
 def test_nothing_happens_until_the_owner_connected_their_shop(self):
  self.assertFalse(self.tick());self.assertEqual(self.calls,[])
  self.assertFalse(etsy.view(self.s,IDEA)['connected'])
 def test_a_finished_picture_goes_up_as_a_free_draft(self):
  # The owner (2 Nov): "ne kelljen nekem feltöltenem a grafikákat, hanem egyből feltöltse ő".
  self.login();self.assertTrue(self.tick())
  create=self.sent('POST','/shops/77/listings')[0];form=dict(urllib.parse.parse_qsl(create.data.decode()))
  self.assertEqual((form['type'],form['who_made'],form['when_made'],form['should_auto_renew'],form['price'],form['taxonomy_id']),('download','i_did','made_to_order','false','4.99','1234'))
  self.assertIn('mesterséges intelligencia',form['description'],'Etsy requires the disclosure');self.assertEqual(form['tags'],'színezőlap,űr,4-7 éves')
  self.assertEqual(create.get_header('X-api-key'),'keystring1:secret456');self.assertEqual(create.get_header('Authorization'),'Bearer 1.live')
  self.assertEqual(len(self.sent('POST','/listings/1001/images')),1);self.assertEqual(len(self.sent('POST','/listings/1001/files')),1)
  self.assertIn(b'name="image"',self.sent('POST','/images')[0].data);self.assertIn(b'application/pdf',self.sent('POST','/files')[0].data)
  self.assertEqual(self.row()['state'],'draft');self.assertEqual(self.sent('PATCH','/listings/1001'),[],'a draft is free and not public')
  self.assertEqual(self.tick(),True);self.assertEqual(self.row('rocket')['state'],'draft')
  n=len(self.calls);self.assertFalse(self.tick());self.assertEqual(len(self.calls),n,'all drafts are up and nothing goes live by itself')
  v=etsy.view(self.s,IDEA);self.assertEqual((v['drafts'],v['live'],v['left']),(2,0,0))
 def test_a_draft_goes_live_only_when_the_owner_says_and_at_a_pace(self):
  self.login();self.items([listing('p'+str(i)) for i in range(7)])
  for _ in range(7):self.tick()
  self.assertEqual(etsy.view(self.s,IDEA)['drafts'],7)
  etsy.dispatch(self.s,'etsy_settings',dict(idea=IDEA,live=True))
  for _ in range(9):self.tick()
  live=[c for c in self.calls if c.get_method()=='PATCH'];self.assertEqual(len(live),etsy.DAILY_LIVE,'going live is capped per day')
  self.assertEqual(live[0].data,b'state=active');v=etsy.view(self.s,IDEA);self.assertEqual((v['live'],v['drafts']),(5,2));self.assertTrue(next(r for r in v['rows'] if r['state']=='active')['listing'])
 def test_a_failure_resumes_and_never_makes_a_second_listing(self):
  self.login();self.fail['/images']=500;self.tick();row=self.row()
  self.assertEqual((row['listing_id'],row['step'],row['state'],row['tries']),('1001','created','failed',1));self.assertIn('Etsy says no',row['error'])
  now=time.time();self.assertFalse(self.tick(now+60),'it waits before trying again')
  self.fail.clear();self.assertTrue(self.tick(now+etsy.COOLDOWN+1));self.assertEqual(self.row()['state'],'draft')
  self.assertEqual(len([c for c in self.sent('POST','/shops/77/listings')]),1);self.assertEqual(self.row()['tries'],0)
 def test_repeated_failure_stops_and_the_owner_can_retry(self):
  self.login();self.fail['/shops/77/listings']=403;self.items([listing('astronaut')])
  now=time.time()
  for i in range(5):self.tick(now+i*(etsy.COOLDOWN+1))
  self.assertEqual(len(self.sent('POST','/shops/77/listings')),etsy.TRIES);self.assertTrue(next(r for r in etsy.view(self.s,IDEA)['rows'])['stuck'])
  self.fail.clear();etsy.dispatch(self.s,'etsy_retry',dict(idea=IDEA));self.assertTrue(self.tick());self.assertEqual(self.row()['state'],'draft')
 def test_a_price_in_another_currency_waits_for_the_owner(self):
  self.login('HUF');self.tick();self.assertIn('nem a bolt pénznemében',self.row()['error']);self.assertEqual(self.sent('POST','/shops/77/listings'),[])
  etsy.dispatch(self.s,'etsy_settings',dict(idea=IDEA,price='1990'));etsy.dispatch(self.s,'etsy_retry',dict(idea=IDEA));self.tick()
  self.assertEqual(dict(urllib.parse.parse_qsl(self.sent('POST','/shops/77/listings')[0].data.decode()))['price'],'1990.00')
  for bad in ('sok','0','-1'):
   with self.assertRaises(ValueError):etsy.dispatch(self.s,'etsy_settings',dict(idea=IDEA,price=bad))
 def test_only_downloads_that_are_drawn_and_free_of_brands_go_up(self):
  self.login()
  self.items([listing('notdrawn'),listing('shirt',products=['t-shirt']),listing('kdp',marketplace='Amazon KDP'),listing('bat',title='Batman színező'),listing('good')],drawn=['bat','good','shirt','kdp'])
  v=etsy.view(self.s,IDEA);self.assertEqual({r['id']:r['state'] for r in v['rows']},dict(notdrawn='waiting',bat='new',good='new'))
  self.tick();self.assertIn('Védett márka',self.row('bat')['error'])
 def test_the_text_fits_etsys_rules(self):
  self.assertEqual(etsy.clean_title('A: b: c & d & e + f'),'A: b c & d e + f');self.assertEqual(len(etsy.clean_title('x'*300)),140)
  tags=etsy.clean_tags(['ok','OK','a_b','túl hosszú címke ami nem fér bele','4-7 éves','#jel']+[str(i)+'x' for i in range(20)])
  self.assertLessEqual(len(tags),13);self.assertEqual(tags[:3],['ok','ab','túl hosszú címke ami']);self.assertTrue(all(len(t)<=20 for t in tags));self.assertIn('4-7 éves',tags);self.assertIn('jel',tags)
 def test_the_owner_can_turn_the_upload_off(self):
  self.login();etsy.dispatch(self.s,'etsy_settings',dict(idea=IDEA,auto=False));self.assertFalse(self.tick());self.assertEqual(self.calls,[])
  self.assertFalse(etsy.settings(self.s,IDEA)['auto']);self.assertFalse(etsy.settings(self.s,IDEA)['live'])

class ConnectTests(EtsyCase):
 def test_a_short_lived_token_is_renewed(self):
  self.login();connections.atomic(etsy.TOKEN,dict(access_token='1.old',refresh_token='1.ref',expires_at=time.time()-5))
  self.assertEqual(etsy.access(),'1.new');sent=dict(urllib.parse.parse_qsl(self.calls[0].data.decode()))
  self.assertEqual((sent['grant_type'],sent['client_id'],sent['refresh_token']),('refresh_token','keystring1','1.ref'));self.assertEqual(connections.read(etsy.TOKEN)['refresh_token'],'1.next')
  self.assertEqual(etsy.access(),'1.new');self.assertEqual(len(self.calls),1)
 def test_the_key_has_both_parts(self):
  with self.assertRaisesRegex(ValueError,'keystring:shared secret'):connections.save(dict(provider='etsy',enabled=True,key='onlythekeystring'))
 def test_the_return_address_is_an_orbit_worker_made_once(self):
  with patch('launch.account',return_value='acc'),patch('launch.cf',side_effect=lambda m,p,*a,**k:dict(subdomain='example') if p.endswith('workers/subdomain') else {}) as cf:
   url=etsy.dispatch(self.s,'etsy_callback')['callback'];self.assertEqual(etsy.dispatch(self.s,'etsy_callback')['callback'],url)
  self.assertEqual(url,'https://orbit-etsy-login.example.workers.dev/');self.assertEqual(sum(c.args[0]=='PUT' for c in cf.call_args_list),1,'made once')
  self.assertTrue(all('orbit-' in c.args[1] or c.args[1].endswith('subdomain') for c in cf.call_args_list));self.assertIn('127.0.0.1:'+str(etsy.PORT),etsy.LOGIN_WORKER)
  self.assertNotIn('secret',etsy.LOGIN_WORKER)
 @unittest.skipUnless((Path(sys.executable).parent/'node').exists(),'node is in the media runtime')
 def test_the_address_is_a_website_and_a_way_back(self):
  # The owner (2 Nov): Etsy's app form asks for a website URL, and ORBIT has none.
  with tempfile.TemporaryDirectory() as tmp:
   worker=Path(tmp)/'worker.mjs';worker.write_text(etsy.LOGIN_WORKER)
   check=Path(tmp)/'check.mjs';check.write_text('''import w from './worker.mjs';
const site=await w.fetch(new Request('https://orbit.example/'));const back=await w.fetch(new Request('https://orbit.example/?code=c1&state=s%201'));const no=await w.fetch(new Request('https://orbit.example/?error=access_denied'));
console.log(JSON.stringify({site:site.status,type:site.headers.get('content-type'),text:await site.text(),back:back.status,to:back.headers.get('location'),no:no.headers.get('location')}));''')
   out=json.loads(subprocess.run([str(Path(sys.executable).parent/'node'),str(check)],capture_output=True,text=True,check=True).stdout)
  self.assertEqual((out['site'],out['back']),(200,302));self.assertIn('text/html',out['type']);self.assertIn('personal desktop tool',out['text']);self.assertIn('not endorsed or certified by Etsy',out['text'])
  self.assertEqual(out['to'],'http://127.0.0.1:'+str(etsy.PORT)+'/etsy?code=c1&state=s%201');self.assertEqual(out['no'],'http://127.0.0.1:'+str(etsy.PORT)+'/etsy?error=access_denied')
 def test_the_login_opens_the_browser_with_pkce_and_no_secret(self):
  connections.save(dict(provider='etsy',enabled=True,key='keystring1:secret456'))
  with self.assertRaisesRegex(ValueError,'visszatérési'):etsy.connect(self.s)
  etsy.update_state(callback='https://orbit-etsy-login.example.workers.dev/')
  with patch('etsy.subprocess.Popen') as listen,patch('etsy.subprocess.run') as run:etsy.connect(self.s)
  listen.assert_called_once();link=run.call_args.args[0][1];query=dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(link).query))
  self.assertTrue(link.startswith(etsy.CONSENT));self.assertEqual((query['code_challenge_method'],query['client_id'],query['scope']),('S256','keystring1','listings_r listings_w shops_r'))
  self.assertNotIn('secret456',link);self.assertIn('%20',link);self.assertNotEqual(query['code_challenge'],connections.read(etsy.PENDING)['verifier'])
  self.assertEqual(query['state'],connections.read(etsy.PENDING)['state'])
 def test_only_the_login_started_here_counts(self):
  connections.save(dict(provider='etsy',enabled=True,key='keystring1:secret456'))
  connections.atomic(etsy.PENDING,dict(state='good',verifier='v',redirect='https://x/',at=time.time()))
  for code,state in (('c','bad'),('','good'),('c',None)):
   with self.assertRaisesRegex(ValueError,'nem érvényes'):etsy.finish_login(code,state)
  self.assertEqual(self.calls,[])
  connections.atomic(etsy.PENDING,dict(state='good',verifier='v',redirect='https://x/',at=time.time()-1000))
  with self.assertRaisesRegex(ValueError,'nem érvényes'):etsy.finish_login('c','good')
  connections.atomic(etsy.PENDING,dict(state='good',verifier='v',redirect='https://x/',at=time.time()));etsy.finish_login('c','good')
  self.assertEqual(connections.read(etsy.STATE)['shop'],dict(id=77,name='UrKaland',currency='EUR',url='https://www.etsy.com/shop/UrKaland'));self.assertTrue(etsy.connected())
  sent=dict(urllib.parse.parse_qsl(self.calls[0].data.decode()));self.assertEqual((sent['code'],sent['code_verifier']),('c','v'));self.assertEqual(connections.read(etsy.PENDING),{},'a login is used once')
  self.assertEqual(etsy.disconnect()['message'][:8],'Az ORBIT');self.assertFalse(etsy.connected())
 def test_an_account_without_a_shop_is_told_so(self):
  connections.save(dict(provider='etsy',enabled=True,key='keystring1:secret456'));connections.atomic(etsy.PENDING,dict(state='g',verifier='v',redirect='https://x/',at=time.time()))
  real=etsy.send
  with patch('etsy.send',side_effect=lambda req,timeout=60:json.dumps(dict(user_id=5,shop_id=None)).encode() if req.full_url.endswith('users/me') else real(req,timeout)):
   with self.assertRaisesRegex(ValueError,'nincs megnyitott bolt'):etsy.finish_login('c','g')

class BoundaryTests(EtsyCase):
 def test_only_the_owners_window_reaches_it(self):
  source=(Path(etsy.__file__).parent/'commander.py').read_text()
  self.assertNotIn('etsy',source.lower(),'the assistant has no such action');self.assertNotIn("'project_app'",source)
  out=dispatch(dict(action='project_app',project='universe',op='etsy_status',args=dict(idea=IDEA)),self.s);self.assertEqual((out['app'],out['result']['total']),('etsy',2))
  self.assertFalse(out['result']['settings']['live'],'going live starts switched off')
 def test_only_etsys_own_pages_open(self):
  with patch('etsy.subprocess.run') as run:
   etsy.dispatch(self.s,'etsy_open',dict(target='drafts'));etsy.dispatch(self.s,'etsy_open',dict(target='listing:123'))
   for bad in ('https://evil.example','listing:1;rm','',None):
    with self.assertRaises(ValueError):etsy.dispatch(self.s,'etsy_open',dict(target=bad))
  self.assertEqual(run.call_args_list[1].args[0][1],'https://www.etsy.com/listing/123');self.assertEqual(run.call_count,2)
 def test_a_test_never_reaches_etsy(self):
  patch.stopall()
  with self.assertRaisesRegex(ValueError,'Tesztfutás'):etsy.send(None)

class FileTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  try:import PIL
  except ImportError:raise unittest.SkipTest('Pillow is in the image runtime')
 def test_the_shop_picture_is_marked_and_the_pdf_is_a_printable_page(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'lap.png';Image.new('L',(2480,3508),255).save(source);tool=str(Path(etsy.__file__).with_name('etsy_files.py'))
   subprocess.run([sys.executable,tool,'preview',str(source),tmp+'/lap.jpg'],check=True);subprocess.run([sys.executable,tool,'pdf',str(source),tmp+'/lap.pdf'],check=True)
   shown=Image.open(tmp+'/lap.jpg');self.assertEqual(max(shown.size),2000);self.assertLess(shown.convert('L').getextrema()[0],250,'the mark is on the picture')
   self.assertTrue(Path(tmp+'/lap.pdf').read_bytes().startswith(b'%PDF'))

if __name__=='__main__':unittest.main()
