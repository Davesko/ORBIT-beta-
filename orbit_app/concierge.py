"""Concierge requests from a launched product's waitlist: ORBIT prepares each answer, the owner sends it.

A visitor leaves an email and a site ("send me the report for my shop"). Every half hour ORBIT reads the new
sign-ups from the product's Cloudflare KV, records the site with its own fetcher (site_recorder), runs the
product's report command offline in the sandbox, and puts the report with a ready email into the owner's
list. ORBIT never sends anything. Emails stay on this Mac, outside the project files the models can read.
"""
import hashlib,json,time,urllib.parse,urllib.request

EVERY=1800
PER_TICK=3
RETRIES=2

def store_path(s,idea_id):return s.root/'private'/'concierge'/(str(idea_id)+'.json')

def load(s,idea_id):
 try:return json.loads(store_path(s,idea_id).read_text())
 except (OSError,ValueError):return {}

def save(s,idea_id,data):
 path=store_path(s,idea_id);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=1));tmp.replace(path)

def key_of(email):return hashlib.sha1(email.encode()).hexdigest()[:12]

def signups(state,root=None):
 """The waitlist entries kept by the launched worker (e:<email> -> {at, src, site})."""
 import launch
 base='accounts/'+state['account']+'/storage/kv/namespaces/'+state['namespace']
 out=[]
 for k in (launch.cf('GET',base+'/keys?prefix=e%3A&limit=200',root=root) or [])[:200]:
  try:v=json.loads(launch.cf('GET',base+'/values/'+urllib.request.quote(k['name'],safe=''),root=root,raw=True) or b'{}')
  except ValueError:v={}
  out.append(dict(email=k['name'][2:],at=v.get('at'),src=v.get('src') or '',site=v.get('site') or ''))
 return out

def form(product):
 try:cfg=json.loads((product/'launch-form.json').read_text())
 except (OSError,ValueError):return None
 cmd=cfg.get('report_command') if isinstance(cfg,dict) else None
 return cfg if isinstance(cmd,list) and cmd and all(isinstance(a,str) for a in cmd) else None

def process(s,f,state,root=None,limit=PER_TICK,getter=None):
 """Take in new sign-ups and prepare up to limit reports; returns how many were prepared."""
 import venture_build,site_recorder,product_check
 product=s.safe_path(venture_build.PID,venture_build.folder(f));cfg=form(product)
 if not cfg:return 0
 data=load(s,f['idea_id'])
 for su in signups(state,root):
  k=key_of(su['email'])
  if k not in data:data[k]=dict(email=su['email'],site=su['site'],src=su['src'],at=su['at'],status='new' if su['site'] else 'nosite')
 done=0
 for k,item in sorted(data.items(),key=lambda x:x[1].get('at') or 0):
  # A failed request is tried once more (it may have failed on ORBIT's side); then it goes to the owner.
  if not (item['status']=='new' or item['status']=='failed' and item.get('tries',1)<RETRIES) or done>=limit:continue
  item['tries']=item.get('tries',1 if item['status']=='failed' else 0)+1
  try:
   rec=site_recorder.record(item['site'],words=cfg.get('record_links') or None,max_pages=int(cfg.get('record_pages') or 7),getter=getter)
   out=product_check.run_report(product,rec,[a.replace('{site}',rec['url']) for a in cfg['report_command']])
   ok=bool(out.get('ok')) and bool((out.get('output') or '').strip())
   item.update(status='ready' if ok else 'failed',report=(out.get('output') or '')[:20000],error=(out.get('error') or '')[:500],prepared=time.time())
  except Exception as exc:
   item.update(status='failed',error=str(exc)[:500],prepared=time.time())
  done+=1
 save(s,f['idea_id'],data)
 return done

def actions(s,f):
 """Ready reports, and requests ORBIT could not check, as owner to-dos, each with the email to send."""
 out=[]
 for k,item in load(s,f['idea_id']).items():
  host=urllib.parse.urlparse(item['site']).netloc or item['site']
  if item.get('status')=='failed' and item.get('tries',1)>=RETRIES:
   # Without this the visitor got nothing and the owner saw nothing (the first request, 2026-11-01).
   out.append(dict(title='Válasz a kérésre: '+host+' (nem sikerült ellenőrizni)',kind='contact',concierge=k,count=1,variants=[],cycle=0,
    why='A várólistán kérte ('+(item.get('src') or 'direkt')+'), de az ORBIT kétszer sem tudta ellenőrizni: '+(item.get('error') or 'ismeretlen hiba')+'. Elküldeni te tudod: az ORBIT senkinek nem ír.',
    draft='Címzett: '+item['email']+'\nTárgy: A(z) '+host+' webáruház ellenőrzése\n\nKedves Érdeklődő!\n\nKöszönjük, hogy kérted az ingyenes ellenőrzést. A(z) '+host+' oldalát most nem tudtuk automatikusan ellenőrizni'+(' (az oldal nem engedi az automatikus olvasást)' if 'robots' in (item.get('error') or '') else '')+'. Ha szeretnéd, küldd el a webáruház címét és az ÁSZF-oldal linkjét válaszlevélben, és kézzel nézzük át.\n\nÜdvözlettel:\n[a neved]'))
   continue
  if item.get('status')!='ready':continue
  out.append(dict(title='Jelentés elküldése: '+host,kind='contact',concierge=k,count=1,variants=[],cycle=0,
   why='A várólistán kérte ('+(item.get('src') or 'direkt')+'), az ORBIT elkészítette a jelentést. Elküldeni te tudod: az ORBIT senkinek nem ír.',
   draft='Címzett: '+item['email']+'\nTárgy: A(z) '+host+' webáruház ellenőrzése\n\nKedves Érdeklődő!\n\nKöszönjük, hogy kérted az ingyenes ellenőrzést. Az eredmény:\n\n'+item['report'].strip()+'\n\nÜdvözlettel:\n[a neved]'))
 return out

STATUS_HU={'new':'⏳ készül','ready':'✅ levél kész · Rád vár','sent':'✉️ elküldve','failed':'⚠️ nem sikerült · Rád vár','nosite':'– nem adott meg címet'}

def requests(s,f):
 """Every waitlist request with where it stands, newest first, for the Autopilot page. A sent report used to
 vanish from the page; emails stay on this Mac (the worker stores 'at' in milliseconds)."""
 out=[]
 for k,item in load(s,f['idea_id']).items():
  status=item.get('status') or 'new'
  if status=='failed' and item.get('tries',1)<RETRIES:status='new'
  at=item.get('at') or 0;at=at/1000 if at>1e11 else at
  out.append(dict(key=k,email=item.get('email',''),site=urllib.parse.urlparse(item.get('site') or '').netloc or item.get('site') or '',src=item.get('src') or 'direkt',at=at,status=status,label=STATUS_HU.get(status,status),sent=item.get('sent')))
 return sorted(out,key=lambda r:-r['at'])[:50]

def mark_sent(s,idea_id,key):
 data=load(s,idea_id)
 if key not in data:raise ValueError('Ismeretlen kérés.')
 data[key].update(status='sent',sent=time.time());save(s,idea_id,data);return data[key]['status']

def tick(s,now=None):
 """Every half hour: new sign-ups of every live product with a report command get their report prepared."""
 import venture_build,launch
 now=now or time.time();mark=s.root/'private'/'concierge'/'_last'
 try:
  if now-mark.stat().st_mtime<EVERY:return
 except OSError:pass
 mark.parent.mkdir(parents=True,exist_ok=True);mark.write_text(str(now))
 ids=list(dict.fromkeys([x for x in [(venture_build.active(s) or {}).get('idea_id')]+venture_build.portfolio(s) if x]))
 for iid in ids:
  f=venture_build.focus_for(s,iid)
  state=launch.read_state(s,venture_build.folder(f)) if f else None
  if state and state.get('status')=='live':process(s,f,state)
