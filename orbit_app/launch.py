"""Owner-approved launch of an Autopilot product as a Cloudflare Worker with a waitlist and
cookie-free measurement, plus the hourly read-back that turns visits into a validation verdict.

Nothing here runs on its own: launch() and stop() are called only from the operator's click.
Scope: only orbit-* Workers scripts and orbit-* KV namespaces it created itself; DNS, zones,
Pages projects and any other script in the account are never read or changed.
The worker is ORBIT's fixed template (not model-written code); product pages are embedded as
static text. Visitors' e-mails stay in the owner's Cloudflare KV; ORBIT reads counts only.
"""
import hashlib,json,re,time,uuid,urllib.error,urllib.request
from pathlib import Path,PurePosixPath
import connections

PID='orbit-business-lab'
BASE='https://api.cloudflare.com/client/v4/'
STALE=3600
# Default 48-hour fake-door thresholds (see the validation milestone).
THRESHOLDS=dict(visitors=100,signup_rate=8.0,paid_rate=2.0,hours=48)

class LaunchError(ValueError):pass

def cf(method,path,body=None,headers=None,root=None,raw=False,timeout=30):
 """One Cloudflare API call with the owner's token; errors become readable Hungarian text."""
 token=connections.secret('cloudflare',root)
 if not token:raise LaunchError('Előbb add meg a Cloudflare-tokent a Kapcsolatok oldalon.')
 if not connections.settings(root)['providers'].get('cloudflare',{}).get('enabled'):raise LaunchError('Kapcsold be a Cloudflare-kapcsolatot a Kapcsolatok oldalon.')
 hdr={'Authorization':'Bearer '+token,'User-Agent':'ORBIT/2.5'}
 if headers:hdr.update(headers)
 data=body if isinstance(body,(bytes,type(None))) else json.dumps(body).encode()
 if body is not None and not isinstance(body,bytes):hdr.setdefault('Content-Type','application/json')
 req=urllib.request.Request(BASE+path,data=data,headers=hdr,method=method)
 call=connections.reserve('cloudflare',root)
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as r:payload=r.read(4*1024*1024)
  connections.finish('cloudflare',call,'ok',root=root)
 except urllib.error.HTTPError as e:
  detail=''
  try:detail='; '.join(x.get('message','') for x in json.loads(e.read(65536)).get('errors',[]))
  except Exception:pass
  connections.finish('cloudflare',call,'failed',str(e.code)+' '+detail,root=root)
  hint={401:'A Cloudflare-token hibás vagy lejárt.',403:'A tokennek nincs elég jogosultsága (Workers Scripts és Workers KV Storage: Edit).',404:'A Cloudflare-erőforrás nem található.'}.get(e.code,'Cloudflare-hiba ('+str(e.code)+').')
  raise LaunchError(hint+(' '+detail if detail else '')) from None
 except OSError:
  connections.finish('cloudflare',call,'failed','network',root=root)
  raise LaunchError('A Cloudflare nem érhető el; ellenőrizd az internetkapcsolatot.') from None
 if raw:return payload
 value=json.loads(payload or b'{}')
 if isinstance(value,dict) and value.get('success') is False:
  raise LaunchError('Cloudflare: '+'; '.join(x.get('message','') for x in value.get('errors',[])))
 return value.get('result') if isinstance(value,dict) and 'result' in value else value

def account(root=None):
 accounts=cf('GET','accounts',root=root) or []
 if not accounts:raise LaunchError('A token nem lát Cloudflare-fiókot.')
 return accounts[0]['id']

def slug(name,idea_id):
 import unicodedata
 plain=unicodedata.normalize('NFKD',name.casefold()).encode('ascii','ignore').decode()  # Számla -> szamla
 base=re.sub(r'[^a-z0-9]+','-',plain)[:30].strip('-') or 'orbit'
 # Every ORBIT resource is prefixed, so it can never be confused with the owner's own sites.
 return ('orbit-'+base+'-'+re.sub(r'[^a-z0-9]','',str(idea_id).lower())[:6]).strip('-')[:60]

PRIVACY='''<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Adatkezelés</title><style>body{font:16px/1.6 system-ui;max-width:720px;margin:40px auto;padding:0 18px;color:#1d1d1f}</style></head><body><h1>Adatkezelési tájékoztató</h1>
<p>Ez az oldal egy készülő szolgáltatás bemutatója. A várólistára feliratkozáskor megadott e-mail-címet kizárólag arra használjuk, hogy értesítsünk az indulásról. Harmadik félnek nem adjuk át, és bármikor kérheted a törlését válaszlevélben.</p>
<p>Az oldal sütiket nem használ. Névtelen látogatásszámot és gombkattintásokat mérünk (forrásmegjelöléssel, például hirdetés neve), személyes azonosítás nélkül.</p>
<p>Az adatokat a szolgáltatás üzemeltetője a Cloudflare tárhelyén tárolja.</p><p><a href="/">Vissza</a></p></body></html>'''

WAITLIST='''<section id="orbit-waitlist" style="max-width:560px;margin:48px auto;padding:24px;border:1px solid #d0d0d8;border-radius:14px;font:16px/1.5 system-ui;background:#fff;color:#1d1d1f">
<h2 style="margin:0 0 6px;font-size:22px">Hamarosan indul – iratkozz fel a várólistára</h2>
<p style="margin:0 0 14px;color:#555">Az indulásról és a korai hozzáférésről e-mailben értesítünk.</p>
<form data-orbit-signup style="display:flex;flex-wrap:wrap;gap:8px"><input type="email" name="email" required placeholder="E-mail-címed" style="flex:1;min-width:220px;padding:12px;border:1px solid #bbb;border-radius:10px;font-size:16px">
<button type="submit" style="padding:12px 18px;border:0;border-radius:10px;background:#111;color:#fff;font-weight:600;font-size:16px">Feliratkozom</button>
<label style="flex-basis:100%;font-size:13px;color:#555"><input type="checkbox" required> Elfogadom az <a href="/adatvedelem">adatkezelési tájékoztatót</a>.</label></form>
<p data-orbit-thanks hidden style="margin:12px 0 0;font-weight:600">Köszönjük! Feliratkoztál a várólistára.</p></section>'''

TRACKER='''<script>(function(){var q=new URLSearchParams(location.search),src=(q.get('utm_source')||q.get('src')||document.referrer.replace(/^https?:\\/\\/([^/]+).*$/,'$1')||'direkt').slice(0,40);
function send(t){try{navigator.sendBeacon('/api/e',JSON.stringify({t:t,src:src,p:location.pathname}))}catch(e){}}send('view');
document.addEventListener('click',function(e){var el=e.target.closest('a,button');if(!el||el.closest('#orbit-waitlist'))return;var paid=el.hasAttribute('data-orbit-checkout')||el.closest('[id*=pric],[class*=pric],[id*=ar],[class*=csomag],[id*=csomag]')||/ft|€|eur|\\$|csomag|előfizet/i.test(el.textContent);send(paid?'paid':'cta');
if((el.getAttribute('href')||'').match(/^(#|$|https?:\\/\\/(forms\\.|docs\\.google))/)||el.tagName==='BUTTON'){var w=document.getElementById('orbit-waitlist');if(w){e.preventDefault();w.scrollIntoView({behavior:'smooth'});}}},true);
document.addEventListener('submit',function(e){var f=e.target,m=f.querySelector('input[type=email]');if(!m)return;e.preventDefault();
var site=f.querySelector('[name=site]');fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:m.value,src:src,site:site?site.value:''})}).then(function(){f.hidden=true;var t=f.parentNode.querySelector('[data-orbit-thanks]');if(t)t.hidden=false;else f.insertAdjacentHTML('afterend','<p><b>Köszönjük! Feliratkoztál.</b></p>');});},true);})();</script>'''

WORKER='''const PAGES=__PAGES__;
const KINDS=new Set(['view','cta','paid']);
async function bump(env,key){const n=parseInt(await env.STATS.get(key)||'0',10)+1;await env.STATS.put(key,String(n));}
export default{async fetch(req,env){
 const url=new URL(req.url);
 if(url.pathname==='/api/e'&&req.method==='POST'){
  let d={};try{d=JSON.parse(await req.text())}catch(e){}
  if(KINDS.has(d.t)){const src=String(d.src||'direkt').replace(/[^\\w.-]/g,'').slice(0,40)||'direkt';await bump(env,'c:'+d.t);await bump(env,'s:'+src+':'+d.t);}
  return new Response(null,{status:204});}
 if(url.pathname==='/api/signup'&&req.method==='POST'){
  let d={};try{d=await req.json()}catch(e){}
  const email=String(d.email||'').trim().toLowerCase();
  if(!/^[^@\\s]{1,64}@[^@\\s]{1,190}\\.[a-z]{2,24}$/.test(email))return Response.json({ok:false},{status:400});
  const key='e:'+email;
  const site=/^https?:\\/\\/[^\\s]{3,190}$/.test(String(d.site||'').trim())?String(d.site).trim():'';
  if(!(await env.STATS.get(key))){await env.STATS.put(key,JSON.stringify({at:Date.now(),src:String(d.src||'').slice(0,40),site:site}));await bump(env,'c:signup');await bump(env,'s:'+(String(d.src||'direkt').replace(/[^\\w.-]/g,'').slice(0,40)||'direkt')+':signup');}
  return Response.json({ok:true});}
 const page=PAGES[url.pathname]||PAGES[url.pathname.replace(/\\/$/,'')+'.html']||(url.pathname==='/'?PAGES['/index.html']:null);
 if(!page)return new Response('Nem található',{status:404,headers:{'content-type':'text/plain; charset=utf-8'}});
 return new Response(page.body,{headers:{'content-type':page.type,'cache-control':'public, max-age=300','x-robots-tag':'noindex'}});
}};'''

# A product can ask its waitlist for the visitor's site (a concierge offer: "send me the report for my shop").
# The owner writes launch-form.json in the product folder; builders cannot write it.
FORM_FILE='launch-form.json'

def form_config(product):
 try:cfg=json.loads((Path(product)/FORM_FILE).read_text())
 except (OSError,ValueError):return None
 return {k:str(cfg.get(k) or '')[:400] for k in ('heading','text','site_label','site_placeholder','thanks','purpose','checkout_url','checkout_label')} if isinstance(cfg,dict) else None

# A finished product sells: every <a data-orbit-checkout> on the page goes to the owner's checkout link (Stripe Payment
# Link, Gumroad, a marketplace page), and a page without one gets a buy button. No waitlist is added then.
BUY_BLOCK='<section id="orbit-buy" style="max-width:560px;margin:48px auto;padding:24px;text-align:center;font:16px/1.5 system-ui"><a data-orbit-checkout href="__URL__" target="_blank" rel="noopener" style="display:inline-block;padding:14px 26px;border-radius:12px;background:#111;color:#fff;font-weight:700;text-decoration:none">__LABEL__</a></section>'
NEED_CHECKOUT='Add meg a vásárlási linket (Stripe fizetési link, Gumroad vagy piactéri termékoldal): az oldal kész termékként, Megveszem gombbal kerül ki, várólista nélkül.'

def checkout(cfg):
 url=(cfg or {}).get('checkout_url') or ''
 return url if re.match(r'^https://[^\s"<>]{4,380}$',url) else ''

def point_checkout(html,url):
 """(html, count): every data-orbit-checkout link aimed at the owner's checkout."""
 def aim(m):
  tag=re.sub(r'\s(?:href|target|rel)\s*=\s*(["\']).*?\1','',m.group(0),flags=re.I|re.S)
  return tag[:-1].rstrip()+' href="'+escape(url)+'" target="_blank" rel="noopener">'
 return re.subn(r'<a\b[^>]*\bdata-orbit-checkout\b[^>]*>',aim,html,flags=re.I)

def escape(text):return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def waitlist_html(cfg):
 """The waitlist block; with a form config it also asks for the visitor's site."""
 if not cfg:return WAITLIST
 html=WAITLIST
 if cfg['heading']:html=html.replace('Hamarosan indul – iratkozz fel a várólistára',escape(cfg['heading']))
 if cfg['text']:html=html.replace('Az indulásról és a korai hozzáférésről e-mailben értesítünk.',escape(cfg['text']))
 if cfg['thanks']:html=html.replace('Köszönjük! Feliratkoztál a várólistára.',escape(cfg['thanks']))
 site=('<input type="url" name="site" required placeholder="'+escape(cfg['site_placeholder'] or 'https://')+'" aria-label="'+escape(cfg['site_label'] or 'Weboldal címe')+'" style="flex-basis:100%;padding:12px;border:1px solid #bbb;border-radius:10px;font-size:16px">')
 return html.replace('<input type="email"',site+'<input type="email"',1)

def privacy_html(cfg):
 if not cfg or not cfg['purpose']:return PRIVACY
 return PRIVACY.replace('<p>Az oldal sütiket nem használ.','<p>Ha megadod a weboldalad címét, azt arra használjuk, hogy '+escape(cfg['purpose'].rstrip('.'))+'. A címet és az e-mail-címet a kérés teljesítése után kérésedre töröljük.</p><p>Az oldal sütiket nem használ.',1)

def bundle(product,waitlist=False):
 """Pages served by the worker: product HTML with CSS inlined and the tracker added; the buy buttons go to the
 owner's checkout link. Only a product already live with a waitlist (waitlist=True) keeps it."""
 product=Path(product);pages={};cfg=form_config(product);url=checkout(cfg);aimed=0
 if not url and not waitlist:raise LaunchError(NEED_CHECKOUT)
 htmls=sorted(product.glob('*.html'),key=lambda p:(p.name!='index.html',p.name))
 if not htmls:raise LaunchError('Ebben a projektben még nincs weboldal (index.html); előbb az értékesítő oldal mérföldkőnek kell elkészülnie.')
 for page in htmls[:8]:
  html=page.read_text()[:300000]
  def inline(m):
   css=product/PurePosixPath(m.group(1)).name
   return '<style>'+css.read_text()[:200000]+'</style>' if css.is_file() and css.suffix=='.css' else ''
  html=re.sub(r'<link[^>]+href=["\']([^"\']+\.css)["\'][^>]*>',inline,html,flags=re.I)
  html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.I|re.S)  # model-written scripts are not published
  if url:
   html,n=point_checkout(html,url);aimed+=n
   add=('' if n or page.name!='index.html' else BUY_BLOCK.replace('__URL__',escape(url)).replace('__LABEL__',escape((cfg or {}).get('checkout_label') or 'Megveszem')))+TRACKER
  else:add=('' if 'data-orbit-signup' in html or page.name!='index.html' else waitlist_html(cfg))+TRACKER
  html=re.sub(r'</body>',add+'</body>',html,count=1,flags=re.I) if re.search(r'</body>',html,re.I) else html+add
  pages['/'+page.name]=dict(type='text/html; charset=utf-8',body=html)
 if not url and not any('data-orbit-signup' in p['body'] or 'type="email"' in p['body'] for p in pages.values()):raise LaunchError('A várólista nem illeszthető be az oldalba.')
 pages['/adatvedelem']=dict(type='text/html; charset=utf-8',body=privacy_html(cfg))
 pages['/robots.txt']=dict(type='text/plain',body='User-agent: *\nDisallow: /api/\n')
 size=sum(len(p['body']) for p in pages.values())
 if size>900000:raise LaunchError('Az oldal túl nagy a feltöltéshez (max. ~900 KB).')
 return pages

def worker_source(pages):return WORKER.replace('__PAGES__',json.dumps(pages,ensure_ascii=False))

def fingerprint(pages):return hashlib.sha256(json.dumps(pages,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]

def staleness(s,folder,state):
 """Whether the live site shows an older version than the product's pages now: the Autopilot keeps
 rebuilding the sales page after the owner published it once, and nothing said the site was behind.
 Republishing stays the owner's decision; this only says what changed since."""
 if not state or state.get('status')!='live':return None
 product=s.safe_path(PID,folder)
 try:pages=bundle(product,waitlist=state.get('mode','waitlist')=='waitlist')
 except (LaunchError,OSError):return None
 changed=sorted(p.name for p in list(product.glob('*.html'))+list(product.glob('*.css')) if p.stat().st_mtime>(state.get('updated') or 0))
 stale=fingerprint(pages)!=state['fingerprint'] if state.get('fingerprint') else bool(changed)
 return dict(stale=stale,changed=changed if stale else [],since=state.get('updated'))

def multipart(parts):
 boundary='orbit'+uuid.uuid4().hex
 out=b''
 for name,ctype,data in parts:
  out+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"; filename="'+name+'"\r\nContent-Type: '+ctype+'\r\n\r\n').encode()+data+b'\r\n'
 return out+('--'+boundary+'--\r\n').encode(),'multipart/form-data; boundary='+boundary

def state_path(s,folder):return s.safe_path(PID,folder+'/launch.json')
def read_state(s,folder):
 try:return json.loads(state_path(s,folder).read_text())
 except (OSError,ValueError):return None
def write_state(s,folder,value):
 p=state_path(s,folder);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=1))

def launch(s,f,root=None):
 """Publish one product. Called only from the operator's explicit confirmation."""
 import venture_build
 folder=venture_build.folder(f);product=s.safe_path(PID,folder)
 old=read_state(s,folder) or {}
 # A product already live with a waitlist may keep it until the owner gives a checkout link.
 pages=bundle(product,waitlist=old.get('status')=='live' and old.get('mode','waitlist')=='waitlist')
 mode='buy' if checkout(form_config(product)) else 'waitlist'
 acc=account(root);name=old.get('script') or slug(f['name'],f['idea_id'])
 # Safety: only ever write a worker ORBIT created for this product; never touch other scripts.
 existing={w.get('id') for w in (cf('GET','accounts/'+acc+'/workers/scripts',root=root) or [])}
 if name in existing and old.get('script')!=name:raise LaunchError('Már létezik ilyen nevű Cloudflare Worker ('+name+'), amit nem az ORBIT hozott létre ehhez a projekthez; nem írom felül.')
 if not name.startswith('orbit-'):raise LaunchError('Az ORBIT csak orbit- kezdetű workert kezelhet.')
 ns=old.get('namespace')
 if not ns:
  ns=cf('POST','accounts/'+acc+'/storage/kv/namespaces',dict(title='orbit-'+name),root=root)['id']
 meta=dict(main_module='worker.js',compatibility_date='2024-09-23',bindings=[dict(type='kv_namespace',name='STATS',namespace_id=ns)])
 body,ctype=multipart([('metadata','application/json',json.dumps(meta).encode()),('worker.js','application/javascript+module',worker_source(pages).encode())])
 cf('PUT','accounts/'+acc+'/workers/scripts/'+name,body,{'Content-Type':ctype},root=root,timeout=60)
 cf('POST','accounts/'+acc+'/workers/scripts/'+name+'/subdomain',dict(enabled=True),root=root)
 try:sub=cf('GET','accounts/'+acc+'/workers/subdomain',root=root)['subdomain']
 except (LaunchError,KeyError,TypeError):raise LaunchError('A Cloudflare-fiókodban még nincs workers.dev aldomain. Nyisd meg egyszer a Cloudflare Workers oldalát, válassz aldomaint, majd próbáld újra.') from None
 url='https://'+name+'.'+sub+'.workers.dev'
 state=dict(status='live',url=url,script=name,account=acc,namespace=ns,launched=old.get('launched') or time.time(),updated=time.time(),pages=sorted(pages),fingerprint=fingerprint(pages),stats=old.get('stats'),idea_id=f['idea_id'],name=f['name'],mode=mode)
 write_state(s,folder,state);return state

def stop(s,f,root=None):
 import venture_build
 folder=venture_build.folder(f);state=read_state(s,folder)
 if not state or state.get('status')!='live':raise LaunchError('Ez a projekt nincs élesítve.')
 if not str(state.get('script','')).startswith('orbit-'):raise LaunchError('Csak az ORBIT által létrehozott worker vehető le.')
 try:cf('DELETE','accounts/'+state['account']+'/workers/scripts/'+state['script'],root=root)
 except LaunchError as e:
  if 'nem található' not in str(e):raise
 # Measurements and the waitlist stay in the owner's KV; only the public page is removed.
 state=dict(state,status='stopped',stopped=time.time());write_state(s,folder,state);return state

def verdict(stats,launched,mode='waitlist'):
 v=stats.get('view',0);signup=stats.get('signup',0);paid=stats.get('paid',0)
 hours=(time.time()-launched)/3600 if launched else 0
 rates=dict(signup_rate=round(100*signup/v,1) if v else 0.0,paid_rate=round(100*paid/v,1) if v else 0.0)
 if v>=THRESHOLDS['visitors']:
  # A page that sells has no sign-ups: its buy clicks decide (verified sales come from Stripe).
  ok=rates['paid_rate']>=THRESHOLDS['paid_rate'] and (mode=='buy' or rates['signup_rate']>=THRESHOLDS['signup_rate'])
  return dict(rates,status='passed' if ok else 'failed',hours=round(hours,1))
 if hours>=THRESHOLDS['hours']:return dict(rates,status='low_traffic',hours=round(hours,1))
 return dict(rates,status='running',hours=round(hours,1))

def refresh(s,folder,root=None,force=False):
 """Read counters from KV at most hourly; return the (possibly cached) state with a verdict."""
 state=read_state(s,folder)
 if not state or state.get('status') not in ('live','stopped'):return state
 if not force and state.get('stats') and time.time()-state['stats'].get('at',0)<STALE:return state
 base='accounts/'+state['account']+'/storage/kv/namespaces/'+state['namespace']
 try:
  keys=[k['name'] for k in (cf('GET',base+'/keys?prefix=c%3A&limit=100',root=root) or [])]
  counts={k[2:]:int(cf('GET',base+'/values/'+urllib.request.quote(k,safe=''),root=root,raw=True) or b'0') for k in keys}
  src=[k['name'] for k in (cf('GET',base+'/keys?prefix=s%3A&limit=200',root=root) or [])]
  sources={}
  for k in src[:60]:
   _,name,kind=k.split(':',2);sources.setdefault(name,{})[kind]=int(cf('GET',base+'/values/'+urllib.request.quote(k,safe=''),root=root,raw=True) or b'0')
 except (LaunchError,ValueError) as e:
  state['stats']=dict(state.get('stats') or {},error=str(e)[:200],at=time.time());write_state(s,folder,state);return state
 previous=(state.get('stats') or {}).get('verdict',{}).get('status')
 stats=dict(counts=counts,sources=sources,at=time.time());stats['verdict']=verdict(counts,state.get('launched'),state.get('mode','waitlist'))
 state['stats']=stats;write_state(s,folder,state)
 if stats['verdict']['status']!=previous and stats['verdict']['status'] in ('passed','failed','low_traffic'):notify(state)
 return state

def notify(state):
 """One Telegram line when the validation reaches a verdict."""
 cfg=connections.settings()['providers'].get('telegram',{})
 if not cfg.get('notifications') or not cfg.get('chat_id') or not connections.allowed('telegram'):return
 v=state['stats']['verdict'];c=state['stats']['counts']
 head={'passed':'✅ Átment a validációs teszt','failed':'❌ Nem ment át a validációs teszt','low_traffic':'⚠️ Kevés látogató a validációs teszten'}[v['status']]
 text=head+'\n„'+state['name']+'”\n'+str(c.get('view',0))+' látogató · '+str(c.get('signup',0))+' feliratkozó ('+str(v['signup_rate'])+'%) · fizetős kattintás '+str(v['paid_rate'])+'%'
 try:connections.http('telegram','sendMessage',dict(chat_id=cfg['chat_id'],text=text),timeout=10)
 except Exception:pass

def traffic_kit(s,folder,url=None):
 """Channels from the product's traffic-kit.json with a trackable link per source once live."""
 try:kit=json.loads(s.safe_path(PID,folder+'/traffic-kit.json').read_text())
 except (OSError,ValueError):return []
 out=[]
 for ch in (kit.get('channels') if isinstance(kit,dict) else kit) or []:
  if not isinstance(ch,dict):continue
  src=re.sub(r'[^\w.-]','',str(ch.get('source') or ch.get('name') or 'csatorna').lower().replace(' ','_'))[:40] or 'csatorna'
  budget=ch.get('budget_eur')
  out.append(dict(source=src,name=str(ch.get('name') or src)[:80],type='paid' if ch.get('type')=='paid' else 'post',
   budget_eur=min(50,max(0,float(budget))) if isinstance(budget,(int,float)) else 0,audience=str(ch.get('audience') or '')[:300],
   copy=str(ch.get('copy') or '')[:2000],link=(url+'/?utm_source='+src) if url else None))
 return out[:6]
