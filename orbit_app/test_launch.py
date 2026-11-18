import json,shutil,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import launch,venture,venture_build

NODE=Path.home()/'Library/Application Support/Orbit/media-runtime/bin/node'
PAGE='<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body><h1>Számla API</h1><a href="#">Kipróbálom</a><div id="pricing"><button>Pro 12900 Ft</button></div><script>alert("x")</script></body></html>'

class LaunchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  venture.configure(self.s,dict(enabled=True))
  self.scores=patch('venture.idea_scores',side_effect=lambda s,mid:{i['idea_id']:dict(demand=3,competition=3,margin=4,automation=5,speed=4,total=19) for i in venture.known_ideas(s,venture.PID)})
  self.scores.start();self.addCleanup(self.scores.stop)
  plan=dict(name='Számla API',problem='p',buyer='b',offer='Automatikus számlakinyerés API',revenue_model='r',costs='c',hypothesis='h',validation='v',progress='p',next_action='n',decision='continue',evidence=[],automation_level=95,human_steps=[],files=[dict(name='README.md',content='terv')])
  venture.save_result(self.s,venture.PID,'r1',plan);self.f=venture_build.active(self.s)
  venture_build.save(self.s,'r2',dict(milestone_id='landing',summary='Kész értékesítő oldal.',files=[dict(name='index.html',content=PAGE),dict(name='styles.css',content='h1{color:#0b6} body{margin:0}')]))
  self.product=self.s.safe_path(venture.PID,venture_build.folder(self.f))
 def buy(self,url='https://buy.stripe.com/test_abc'):
  return venture.configure(self.s,dict(checkout=dict(idea_id=self.f['idea_id'],url=url)))
 def test_a_finished_product_sells_without_a_waitlist(self):
  # The owner (1 Nov): launched pages should sell the finished product, not collect a waitlist.
  with self.assertRaisesRegex(launch.LaunchError,'vásárlási linket'):launch.bundle(self.product)
  with self.assertRaisesRegex(ValueError,'https://'):self.buy('http://nem-biztonsagos.hu')
  self.assertEqual(self.buy()['checkout'],'https://buy.stripe.com/test_abc')
  index=launch.bundle(self.product)['/index.html']['body']
  self.assertNotIn('data-orbit-signup',index);self.assertNotIn('várólist',index)
  self.assertIn('id="orbit-buy"',index,'a page without a buy link gets a buy button');self.assertIn('href="https://buy.stripe.com/test_abc"',index)
  (self.product/'index.html').write_text(PAGE.replace('<a href="#">Kipróbálom</a>','<a class="cta" href="#" data-orbit-checkout>Megveszem</a>'))
  index=launch.bundle(self.product)['/index.html']['body']
  self.assertIn('data-orbit-checkout href="https://buy.stripe.com/test_abc" target="_blank" rel="noopener">Megveszem</a>',index);self.assertNotIn('id="orbit-buy"',index)
  with self.assertRaisesRegex(ValueError,'Nem engedélyezett fájl'):
   venture_build.save(self.s,'r9',dict(milestone_id='landing',summary='Kész értékesítő oldal.',files=[dict(name='launch-form.json',content='{"checkout_url": "https://mas.hu"}')]))
  self.assertEqual(launch.verdict(dict(view=200,paid=5),time.time(),'buy')['status'],'passed','a selling page has no sign-ups; its buy clicks decide')
 def test_bundle_inlines_css_strips_model_scripts_adds_waitlist_and_privacy(self):
  pages=launch.bundle(self.product,waitlist=True);index=pages['/index.html']['body']
  self.assertIn('<style>h1{color:#0b6} body{margin:0}</style>',index);self.assertNotIn('alert("x")',index)
  self.assertIn('data-orbit-signup',index);self.assertIn("navigator.sendBeacon('/api/e'",index);self.assertIn('/adatvedelem',pages)
  empty=Path(self.tmp.name)/'empty';empty.mkdir()
  with self.assertRaises(launch.LaunchError):launch.bundle(empty,waitlist=True)
 @unittest.skipUnless(NODE.is_file(),'node runtime missing')
 def test_worker_counts_events_dedupes_signups_and_serves_pages(self):
  work=Path(self.tmp.name)/'w';work.mkdir()
  (work/'worker.mjs').write_text(launch.worker_source(launch.bundle(self.product,waitlist=True)))
  (work/'run.mjs').write_text('''import w from './worker.mjs';
const store=new Map();const env={STATS:{get:async k=>store.has(k)?store.get(k):null,put:async(k,v)=>{store.set(k,v)}}};
const req=(p,body)=>new Request('https://x.workers.dev'+p,body?{method:'POST',body:JSON.stringify(body)}:{});
const page=await w.fetch(req('/'),env);const html=await page.text();
await w.fetch(req('/api/e',{t:'view',src:'fb_ads'}),env);await w.fetch(req('/api/e',{t:'view',src:'fb_ads'}),env);await w.fetch(req('/api/e',{t:'hack'}),env);
const a=await w.fetch(req('/api/signup',{email:'A@Example.com',src:'fb_ads'}),env);await w.fetch(req('/api/signup',{email:'a@example.com'}),env);
const bad=await w.fetch(req('/api/signup',{email:'nope'}),env);const missing=await w.fetch(req('/nincs'),env);
console.log(JSON.stringify({status:page.status,hasTitle:html.includes('Számla API'),views:store.get('c:view'),src:store.get('s:fb_ads:view'),signups:store.get('c:signup'),hack:store.get('c:hack')||null,ok:(await a.json()).ok,bad:bad.status,missing:missing.status}));''')
  out=json.loads(subprocess.run([str(NODE),'run.mjs'],cwd=work,capture_output=True,text=True,timeout=30,check=True).stdout)
  self.assertEqual(out,dict(status=200,hasTitle=True,views='2',src='2',signups='1',hack=None,ok=True,bad=400,missing=404))
 def test_launch_stop_refresh_and_measured_demand(self):
  calls=[];kv={'c:view':b'150','c:signup':b'15','c:paid':b'4','c:cta':b'30','s:fb:view':b'150'}
  def fake(method,path,body=None,headers=None,root=None,raw=False,timeout=30):
   calls.append((method,path.split('?')[0]))
   if path=='accounts':return [dict(id='acc1')]
   if path.endswith('/storage/kv/namespaces') and method=='POST':return dict(id='ns1')
   if path.endswith('/workers/subdomain'):return dict(subdomain='example')
   if '/keys?prefix=c%3A' in path:return [dict(name=k) for k in kv if k.startswith('c:')]
   if '/keys?prefix=s%3A' in path:return [dict(name=k) for k in kv if k.startswith('s:')]
   if '/values/' in path:return kv[launch.urllib.parse.unquote(path.rsplit('/',1)[1])]
   return {}
  with patch('launch.cf',side_effect=fake),patch('launch.notify') as note:
   self.buy()
   st=venture.configure(self.s,dict(launch=self.f['idea_id']))['launch']
   self.assertEqual((st['status'],st['mode']),('live','buy'));self.assertTrue(st['url'].startswith('https://orbit-szamla-api-'));self.assertTrue(st['url'].endswith('.example.workers.dev'))
   self.assertIn(('PUT','accounts/acc1/workers/scripts/'+st['script']),calls)
   # pretend the page has been live for two days, then read the numbers
   state=launch.read_state(self.s,venture_build.folder(self.f));state['launched']=time.time()-50*3600;launch.write_state(self.s,venture_build.folder(self.f),state)
   r=venture.configure(self.s,dict(refresh_launch=self.f['idea_id']))['launch']
   self.assertEqual(r['stats']['verdict']['status'],'passed');self.assertEqual(r['stats']['sources']['fb']['view'],150);note.assert_called_once()
   self.scores.stop()
   sc=venture.measured_demand(self.s,{self.f['idea_id']:dict(demand=2,competition=3,margin=4,automation=5,speed=4,total=18)})
   self.assertEqual(sc[self.f['idea_id']]['demand'],5);self.assertEqual(sc[self.f['idea_id']]['measured'],'passed')
   self.scores.start()
   stop=venture.configure(self.s,dict(unlaunch=self.f['idea_id']))['launch'];self.assertEqual(stop['status'],'stopped')
   self.assertIn(('DELETE','accounts/acc1/workers/scripts/'+st['script']),calls)
 def test_the_owner_is_told_when_the_live_site_is_behind(self):
  # The site went live once (2026-10-31 03:54); the Autopilot then rebuilt the sales page and nothing said so.
  def fake(method,path,body=None,headers=None,root=None,raw=False,timeout=30):
   if path=='accounts':return [dict(id='acc1')]
   if path.endswith('/storage/kv/namespaces') and method=='POST':return dict(id='ns1')
   if path.endswith('/workers/subdomain'):return dict(subdomain='example')
   return {}
  folder=venture_build.folder(self.f)
  with patch('launch.cf',side_effect=fake),patch('launch.refresh',side_effect=lambda s,folder,**k:launch.read_state(s,folder)):
   self.buy()
   self.assertIsNone(launch.staleness(self.s,folder,None),'not live: nothing to compare')
   st=venture.configure(self.s,dict(launch=self.f['idea_id']))['launch']
   self.assertEqual(launch.staleness(self.s,folder,st),dict(stale=False,changed=[],since=st['updated']))
   self.assertEqual(venture_build.publish_step(dict(previews=[1],ready=True,launch=st),launch.staleness(self.s,folder,st)),[],'live and current: no step')
   time.sleep(.01);(self.product/'index.html').write_text(PAGE.replace('Pro 12900 Ft','Pro 9900 Ft'))
   up=launch.staleness(self.s,folder,st);self.assertEqual((up['stale'],up['changed']),(True,['index.html']))
   mid=self.s.db.execute('SELECT id FROM orbit_missions WHERE origin=?',(venture.ORIGIN,)).fetchone()
   v=venture_build.view(self.s,mid[0] if mid else None,self.f)
   self.assertEqual(v['owner_actions'][0]['title'],'Élő oldal frissítése az új változatra');self.assertEqual(v['owner_actions'][0]['relaunch'],'update')
   self.assertIn('(index.html)',v['owner_actions'][0]['why']);self.assertTrue(v['live_update']['stale'])
   venture.configure(self.s,dict(launch=self.f['idea_id']))
   self.assertFalse(launch.staleness(self.s,folder,launch.read_state(self.s,folder))['stale'],'republished by the owner: current again')
  # an older state without a fingerprint falls back to file times
  self.assertTrue(launch.staleness(self.s,folder,dict(status='live',updated=0))['stale'])
  ready=venture_build.publish_step(dict(previews=[1],ready=True,launch=None),None)
  self.assertEqual(ready[0]['relaunch'],'first');self.assertEqual(venture_build.publish_step(dict(previews=[],ready=True,launch=None),None),[])
 @unittest.skipUnless(NODE.is_file(),'node runtime missing')
 def test_a_concierge_waitlist_asks_for_the_site_and_keeps_it(self):
  # TermékA: "send me the report for my shop" needs the shop's address with the sign-up.
  pages=launch.bundle(self.product,waitlist=True)
  self.assertNotIn('name="site"',pages['/index.html']['body'],'without a form config the waitlist is unchanged')
  (self.product/'launch-form.json').write_text(json.dumps(dict(heading='Kérd az ingyenes ellenőrzést',text='E-mailben elküldjük a jelentést.',site_label='A webáruházad címe',site_placeholder='https://a-boltod.hu',thanks='Köszönjük! Hamarosan küldjük.',purpose='elkészítsük és e-mailben elküldjük az ellenőrzés eredményét')))
  pages=launch.bundle(self.product,waitlist=True);index=pages['/index.html']['body']
  self.assertIn('Kérd az ingyenes ellenőrzést',index);self.assertIn('<input type="url" name="site" required placeholder="https://a-boltod.hu"',index)
  self.assertIn('Ha megadod a weboldalad címét, azt arra használjuk, hogy elkészítsük és e-mailben elküldjük az ellenőrzés eredményét.',pages['/adatvedelem']['body'])
  with self.assertRaisesRegex(ValueError,'Nem engedélyezett fájl'):
   venture_build.save(self.s,'r9',dict(milestone_id='landing',summary='Kész értékesítő oldal.',files=[dict(name='launch-form.json',content='{"heading": "Más szöveg itt"}')]))
  work=Path(self.tmp.name)/'w2';work.mkdir()
  (work/'worker.mjs').write_text(launch.worker_source(pages))
  (work/'run.mjs').write_text('''import w from './worker.mjs';
const store=new Map();const env={STATS:{get:async k=>store.has(k)?store.get(k):null,put:async(k,v)=>{store.set(k,v)}}};
const req=(p,body)=>new Request('https://x.workers.dev'+p,{method:'POST',body:JSON.stringify(body)});
await w.fetch(req('/api/signup',{email:'a@bolt.hu',src:'fb',site:'https://a-bolt.hu'}),env);
await w.fetch(req('/api/signup',{email:'b@bolt.hu',site:'javascript:alert(1)'}),env);
console.log(JSON.stringify({a:JSON.parse(store.get('e:a@bolt.hu')).site,b:JSON.parse(store.get('e:b@bolt.hu')).site}));''')
  out=json.loads(subprocess.run([str(NODE),'run.mjs'],cwd=work,capture_output=True,text=True,timeout=30,check=True).stdout)
  self.assertEqual(out,dict(a='https://a-bolt.hu',b=''),'only a web address is kept')
 def test_verdicts(self):
  now=time.time()
  self.assertEqual(launch.verdict(dict(view=40),now-3600)['status'],'running')
  self.assertEqual(launch.verdict(dict(view=40),now-49*3600)['status'],'low_traffic')
  self.assertEqual(launch.verdict(dict(view=200,signup=5,paid=1),now)['status'],'failed')
 def test_launch_needs_enabled_cloudflare_connection(self):
  with patch('connections.secret',return_value='tok'),patch('connections.settings',return_value=dict(providers={})):
   with self.assertRaisesRegex(launch.LaunchError,'Kapcsold be'):launch.cf('GET','accounts')
 def test_never_overwrites_or_deletes_a_foreign_worker(self):
  name=launch.slug(self.f['name'],self.f['idea_id']);self.assertTrue(name.startswith('orbit-'))
  def fake(method,path,body=None,headers=None,root=None,raw=False,timeout=30):
   if path=='accounts':return [dict(id='acc1')]
   if path.endswith('/workers/scripts') and method=='GET':return [dict(id=name),dict(id='my-website')]
   raise AssertionError('no write may happen: '+method+' '+path)
  self.buy()
  with patch('launch.cf',side_effect=fake):
   with self.assertRaisesRegex(launch.LaunchError,'nem írom felül'):launch.launch(self.s,self.f)
  launch.write_state(self.s,venture_build.folder(self.f),dict(status='live',script='my-website',account='acc1'))
  with patch('launch.cf',side_effect=fake):
   with self.assertRaisesRegex(launch.LaunchError,'Csak az ORBIT'):launch.stop(self.s,self.f)
 def test_traffic_kit_gets_tracked_links_and_budget_cap(self):
  kit=dict(channels=[dict(source='FB Ads!',name='Facebook',type='paid',budget_eur=200,audience='KKV-tulajdonosok',copy='Próbáld ki'),dict(name='LinkedIn poszt',type='post',copy='Új eszköz')])
  (self.product/'traffic-kit.json').write_text(json.dumps(kit))
  out=launch.traffic_kit(self.s,venture_build.folder(self.f),'https://orbit-x.example.workers.dev')
  self.assertEqual(out[0]['source'],'fb_ads');self.assertEqual(out[0]['budget_eur'],50);self.assertEqual(out[0]['link'],'https://orbit-x.example.workers.dev/?utm_source=fb_ads')
  self.assertEqual(out[1]['source'],'linkedin_poszt');self.assertIsNone(launch.traffic_kit(self.s,venture_build.folder(self.f))[0]['link'])
if __name__=='__main__':unittest.main()
