"""Etsy: the Autopilot's finished graphics reach the owner's shop without uploading them by hand.

Through the official Open API and the owner's own Etsy app and consent; ORBIT never sees the Etsy password. A listing
is uploaded as a draft: free, and nobody sees it. A draft goes live only if the owner switched that on for the project,
because every live listing costs Etsy's listing fee and is public under the owner's name. Renewal stays off, so nothing
is charged again by itself. Going live is capped per day: Etsy reportedly suspends shops for mass-listing AI output.

These controls are reached only from the app's own window (project_apps): the assistant and the agents have no way here.
"""
import base64,datetime,hashlib,json,re,secrets,subprocess,sys,time,urllib.error,urllib.parse,urllib.request,uuid
from pathlib import Path
import connections

API=connections.PROVIDERS['etsy']['base']
CONSENT='https://www.etsy.com/oauth/connect'
TOKEN_URL='https://api.etsy.com/v3/public/oauth/token'
SCOPES='listings_r listings_w shops_r'
PORT=8757
WORKER='orbit-etsy-login'
TOKEN,PENDING,STATE='etsy-token.json','etsy-pending.json','etsy.json'
DAILY_DRAFTS=30;DAILY_LIVE=5;TRIES=3;PACE=120;COOLDOWN=900
FEE='0,20 USD'
DISCLOSURE='A grafika mesterséges intelligencia segítségével készült.\n\nDigitális letöltés: nyomtatható PDF, fizikai terméket nem küldünk.'
DRAFTS_URL='https://www.etsy.com/your/shops/me/tools/listings/state:draft'
_pace={'at':0}

class EtsyError(ValueError):pass

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS etsy_uploads(idea TEXT,design TEXT,listing_id TEXT,state TEXT,step TEXT,title TEXT,error TEXT DEFAULT '',tries INTEGER DEFAULT 0,uploaded REAL,published REAL,updated REAL,PRIMARY KEY(idea,design));
 CREATE TABLE IF NOT EXISTS etsy_settings(idea TEXT PRIMARY KEY,data TEXT);''');s.db.commit()

def send(req,timeout=60):
 """The one place that reaches Etsy. A test run never does."""
 if connections.under_test():raise EtsyError('Tesztfutás: valódi Etsy-hívás nem indul.')
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as r:return r.read(8*1024*1024)

def reason(e):
 try:detail=str(json.loads(e.read(65536)).get('error') or '')[:300]
 except Exception:detail=''
 hint={401:'Az Etsy-belépés lejárt vagy hibás; csatlakozz újra.',403:'Az Etsy nem engedélyezte ezt a műveletet (az Etsy-alkalmazásod még jóváhagyásra várhat).',404:'Az Etsy nem találja ezt az elemet.',429:'Az Etsy most túl sok kérést kapott; később újra próbálom.'}.get(e.code,'Az Etsy hibát jelzett ('+str(e.code)+').')
 return hint+(' '+detail if detail else '')

def form_token(data,root=None):
 req=urllib.request.Request(TOKEN_URL,data=urllib.parse.urlencode(data).encode(),headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'ORBIT'},method='POST')
 try:return json.loads(send(req,30))
 except urllib.error.HTTPError as e:raise EtsyError(reason(e)) from None
 except OSError:raise EtsyError('Az Etsy nem érhető el; ellenőrizd az internetkapcsolatot.') from None

def keystring(root=None):
 key=connections.secret('etsy',root)
 if not key:raise EtsyError('Előbb add meg az Etsy-alkalmazásod kulcsát.')
 return key.split(':')[0]

def store_tokens(t,root=None):
 connections.atomic(TOKEN,dict(access_token=t['access_token'],refresh_token=t['refresh_token'],expires_at=time.time()+int(t.get('expires_in') or 3600)),root)

def access(root=None):
 t=connections.read(TOKEN,root)
 if not t.get('refresh_token'):raise EtsyError('Még nem léptél be az Etsybe az ORBIT-ból.')
 if t.get('expires_at',0)-60>time.time():return t['access_token']
 store_tokens(form_token(dict(grant_type='refresh_token',client_id=keystring(root),refresh_token=t['refresh_token']),root),root)
 return connections.read(TOKEN,root)['access_token']

def multipart(fields,files):
 boundary='orbit'+uuid.uuid4().hex;out=b''
 for name,value in fields.items():
  out+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"\r\n\r\n'+str(value)+'\r\n').encode()
 for name,filename,ctype,data in files:
  out+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"; filename="'+filename+'"\r\nContent-Type: '+ctype+'\r\n\r\n').encode()+data+b'\r\n'
 return out+('--'+boundary+'--\r\n').encode(),'multipart/form-data; boundary='+boundary

def call(method,path,form=None,fields=None,files=None,root=None,auth=True,timeout=60):
 key=connections.secret('etsy',root)
 if not key:raise EtsyError('Előbb add meg az Etsy-alkalmazásod kulcsát.')
 headers={'x-api-key':key,'User-Agent':'ORBIT'};data=None
 if auth:headers['Authorization']='Bearer '+access(root)
 if files:data,headers['Content-Type']=multipart(fields or {},files)
 elif form is not None:data=urllib.parse.urlencode(form).encode();headers['Content-Type']='application/x-www-form-urlencoded'
 handle=connections.reserve('etsy',root,method+' '+re.sub(r'\d+','#',path))
 try:raw=send(urllib.request.Request(API+path,data=data,headers=headers,method=method),timeout)
 except urllib.error.HTTPError as e:
  message=reason(e);connections.finish('etsy',handle,'failed',message[:200],root=root);raise EtsyError(message) from None
 except OSError:
  connections.finish('etsy',handle,'failed','network',root=root);raise EtsyError('Az Etsy nem érhető el; ellenőrizd az internetkapcsolatot.') from None
 connections.finish('etsy',handle,'ok',root=root)
 return json.loads(raw or b'{}')

# Connecting: Etsy accepts only a registered https:// return address, so a tiny orbit- worker sends the browser back to
# this Mac. It holds nothing: the code it passes on is useless without the verifier that stays here (PKCE).
# Without a login in the address it shows what ORBIT is: Etsy's app form also asks for a website, and the owner has none.
LOGIN_PAGE='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ORBIT</title>
<body style="font:16px/1.5 -apple-system,'Segoe UI',sans-serif;max-width:36em;margin:12vh auto;padding:0 16px">
<h1>ORBIT</h1>
<p>ORBIT is a personal desktop tool. Its owner uses it to upload their own digital products to their own Etsy shop through the Etsy Open API. It has no other users and keeps no buyer data.</p>
<p><small>The term "Etsy" is a trademark of Etsy, Inc. This application uses the Etsy API but is not endorsed or certified by Etsy, Inc.</small></p>
'''
LOGIN_WORKER='''const PAGE=%s;
export default {async fetch(request){
 const url=new URL(request.url);
 if(url.searchParams.has('code')||url.searchParams.has('error'))return new Response(null,{status:302,headers:{location:'http://127.0.0.1:%d/etsy'+url.search,'referrer-policy':'no-referrer','cache-control':'no-store'}});
 return new Response(PAGE,{headers:{'content-type':'text/html;charset=utf-8'}});
}};
'''%(json.dumps(LOGIN_PAGE),PORT)

def callback_url(deploy=False,root=None):
 saved=connections.read(STATE,root).get('callback')
 if saved or not deploy:return saved or ''
 import launch
 acc=launch.account(root)
 body,ctype=launch.multipart([('metadata','application/json',json.dumps(dict(main_module='worker.js',compatibility_date='2024-09-23',bindings=[])).encode()),('worker.js','application/javascript+module',LOGIN_WORKER.encode())])
 launch.cf('PUT','accounts/'+acc+'/workers/scripts/'+WORKER,body,{'Content-Type':ctype},root=root,timeout=60)
 launch.cf('POST','accounts/'+acc+'/workers/scripts/'+WORKER+'/subdomain',dict(enabled=True),root=root)
 try:sub=launch.cf('GET','accounts/'+acc+'/workers/subdomain',root=root)['subdomain']
 except (launch.LaunchError,KeyError,TypeError):raise EtsyError('A Cloudflare-fiókodban még nincs workers.dev aldomain. Nyisd meg egyszer a Cloudflare Workers oldalát, válassz aldomaint, majd próbáld újra.') from None
 url='https://'+WORKER+'.'+sub+'.workers.dev/'
 update_state(root,callback=url);return url

def update_state(root=None,**changes):
 with connections.lock(root):connections.atomic(STATE,dict(connections.read(STATE,root),**changes),root)

def connect(s,root=None):
 client=keystring(root);url=callback_url(root=root)
 if not url:raise EtsyError('Előbb hozd létre a visszatérési címet, és írd be az Etsy-alkalmazásodba.')
 verifier=base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b'=').decode()
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode();state=secrets.token_urlsafe(24)
 connections.atomic(PENDING,dict(state=state,verifier=verifier,redirect=url,at=time.time()),root);update_state(root,login='waiting',login_error='')
 subprocess.Popen([sys.executable,str(Path(__file__).with_name('etsy_runtime.py'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
 link=CONSENT+'?'+urllib.parse.urlencode(dict(response_type='code',client_id=client,redirect_uri=url,scope=SCOPES,state=state,code_challenge=challenge,code_challenge_method='S256'),quote_via=urllib.parse.quote)
 subprocess.run(['/usr/bin/open',link],check=False,capture_output=True)
 return dict(message='Megnyílt az Etsy a böngészőben. Lépj be, és engedélyezd az ORBIT-ot.')

def finish_login(code,state,root=None):
 """The browser came back. Only the login this Mac started, within 15 minutes, counts."""
 p=connections.read(PENDING,root)
 if not p or not code or not secrets.compare_digest(str(state or ''),p['state']) or time.time()-p['at']>900:raise EtsyError('Ez a belépés már nem érvényes. Indítsd újra az ORBIT-ból.')
 store_tokens(form_token(dict(grant_type='authorization_code',client_id=keystring(root),redirect_uri=p['redirect'],code=code,code_verifier=p['verifier']),root),root)
 connections.atomic(PENDING,{},root)
 me=call('GET','users/me',root=root)
 if not me.get('shop_id'):raise EtsyError('Ehhez az Etsy-fiókhoz még nincs megnyitott bolt. Nyisd meg a boltot, majd csatlakozz újra.')
 shop=call('GET','shops/'+str(me['shop_id']),root=root)
 update_state(root,login='done',login_error='',shop=dict(id=me['shop_id'],name=shop.get('shop_name') or '',currency=shop.get('currency_code') or '',url=shop.get('url') or ''))

def disconnect(root=None):
 connections.atomic(TOKEN,{},root);update_state(root,shop=None,login='',login_error='')
 return dict(message='Az ORBIT kilépett az Etsyből. A már feltöltött listák megmaradnak a boltodban.')

def connected(root=None):
 return bool(connections.read(TOKEN,root).get('refresh_token') and (connections.read(STATE,root).get('shop') or {}).get('id') and connections.allowed('etsy',root))

# What to upload
def product_folder(s,idea):
 import venture_build
 return s.safe_path(venture_build.PID,venture_build.folder(dict(idea_id=idea)))

def key_of(idea):return re.sub(r'[^a-z0-9]','',str(idea or '').lower())[:16]

def listings(product):
 """The project's own Etsy listings that are downloads. A print-on-demand shirt needs a printing partner, not this."""
 try:rows=json.loads((Path(product)/'listings.json').read_text()).get('listings') or []
 except (OSError,ValueError,AttributeError):return []
 return [r for r in rows if isinstance(r,dict) and str(r.get('marketplace') or '').casefold()=='etsy' and r.get('id') and re.search(r'pdf|download|digital|letölt',str(r.get('products') or ''),re.I)]

def clean_title(text):
 text=re.sub(r'\s+',' ',str(text or '')).strip()
 for mark in '%:&+':
  first=text.find(mark)
  if first>=0:text=text[:first+1]+text[first+1:].replace(mark,' ')
 return re.sub(r'\s+',' ',text)[:140].strip()

def clean_tags(tags):
 out=[]
 for tag in tags if isinstance(tags,list) else []:
  tag=re.sub(r"[^\w\s\-'™©®]|_",'',str(tag)).strip()[:20].strip()
  if tag and tag.casefold() not in [x.casefold() for x in out]:out.append(tag)
 return out[:13]

def price_of(item,currency,cfg):
 if cfg.get('price'):return float(cfg['price'])
 found=re.search(r'(\d+(?:[.,]\d+)?)\s*([A-Za-z]{3})',str(item.get('price') or ''))
 if found and currency and found.group(2).upper()==currency.upper():return float(found.group(1).replace(',','.'))
 raise EtsyError('A javasolt ár nem a bolt pénznemében van ('+str(currency or '?')+'). Add meg az árat a projekt Etsy-részénél.')

def taxonomy(root=None):
 """Etsy's own category for a printable colouring page, looked up once."""
 saved=connections.read(STATE,root).get('taxonomy')
 if saved:return saved
 nodes=[];stack=list(call('GET','seller-taxonomy/nodes',root=root,auth=False).get('results') or [])
 while stack:
  node=stack.pop();nodes.append(node);stack.extend(node.get('children') or [])
 for wanted in ('coloring','colouring','digital prints','prints'):
  found=next((n for n in nodes if wanted in str(n.get('name') or '').casefold()),None)
  if found:
   update_state(root,taxonomy=found['id']);return found['id']
 raise EtsyError('Nem találtam megfelelő Etsy-kategóriát.')

def build_files(s,product,design):
 """The shop picture and the buyer's file. Made once, next to the design."""
 out=Path(product)/'etsy-feltoltes';out.mkdir(exist_ok=True);png=Path(product)/'designs'/(design+'.png')
 made={}
 for mode,name in (('preview',design+'.jpg'),('pdf',design+'.pdf')):
  target=out/name;made[mode]=target
  if not target.is_file():
   r=subprocess.run([str(s.root/'image-runtime/bin/python'),str(Path(__file__).with_name('etsy_files.py')),mode,str(png),str(target)],capture_output=True,text=True,timeout=120)
   if r.returncode or not target.is_file():raise EtsyError('A feltöltendő fájl nem készült el: '+(r.stderr or '')[-200:])
 return made

def row_of(s,idea,design):
 row=s.db.execute('SELECT * FROM etsy_uploads WHERE idea=? AND design=?',(idea,design)).fetchone()
 return dict(row) if row else None

def mark(s,idea,design,**fields):
 if not row_of(s,idea,design):s.db.execute('INSERT INTO etsy_uploads(idea,design) VALUES(?,?)',(idea,design))
 fields['updated']=time.time()
 s.db.execute('UPDATE etsy_uploads SET '+','.join(k+'=?' for k in fields)+' WHERE idea=? AND design=?',list(fields.values())+[idea,design]);s.db.commit()

def upload(s,idea,item,cfg,root=None):
 """One listing to a draft, step by step, so a failure resumes where it stopped and never makes a second listing."""
 from design_studio import PROTECTED
 shop=connections.read(STATE,root)['shop'];base='shops/'+str(shop['id'])+'/listings';design=str(item['id']);row=row_of(s,idea,design) or {}
 title=clean_title(item.get('title'));text=str(item.get('description') or '').strip()
 if not title or not text:raise EtsyError('A listából hiányzik a cím vagy a leírás.')
 if PROTECTED.search(title+' '+text):raise EtsyError('Védett márka vagy karakter szerepel a szövegben; az Etsy törölné, ezért nem töltöm fel.')
 product=product_folder(s,idea);files=build_files(s,product,design);listing=row.get('listing_id')
 if not listing:
  made=call('POST',base,form=dict(quantity=999,title=title,description=text+'\n\n'+DISCLOSURE,price='%.2f'%price_of(item,shop.get('currency'),cfg),who_made='i_did',when_made='made_to_order',is_supply='false',taxonomy_id=taxonomy(root),type='download',should_auto_renew='false',tags=','.join(clean_tags(item.get('tags')))),root=root)
  listing=str(made['listing_id']);mark(s,idea,design,listing_id=listing,state='uploading',step='created',title=title,uploaded=time.time(),error='')
  row=row_of(s,idea,design)
 path=base+'/'+listing
 if row.get('step')=='created':
  call('POST',path+'/images',fields=dict(rank=1),files=[('image',design+'.jpg','image/jpeg',files['preview'].read_bytes())],root=root);mark(s,idea,design,step='image');row=row_of(s,idea,design)
 if row.get('step')=='image':
  call('POST',path+'/files',fields=dict(name=design+'.pdf',rank=1),files=[('file',design+'.pdf','application/pdf',files['pdf'].read_bytes())],root=root)
  mark(s,idea,design,step='file',state='draft',error='',tries=0)

def publish(s,idea,design,root=None):
 row=row_of(s,idea,design);shop=connections.read(STATE,root)['shop']
 call('PATCH','shops/'+str(shop['id'])+'/listings/'+row['listing_id'],form=dict(state='active'),root=root)
 mark(s,idea,design,state='active',published=time.time(),error='',tries=0)

# Settings
def settings(s,idea):
 """A finished picture goes up by itself as a draft; going live only if the owner said so."""
 schema(s);row=s.db.execute('SELECT data FROM etsy_settings WHERE idea=?',(idea,)).fetchone();saved=json.loads(row[0]) if row else {}
 return dict(auto=saved.get('auto',True) is True,live=saved.get('live',False) is True,price=saved.get('price'))

def save_settings(s,idea,args):
 cfg=settings(s,idea)
 if 'auto' in args:cfg['auto']=args['auto'] is True
 if 'live' in args:cfg['live']=args['live'] is True
 if 'price' in args:
  price=args['price']
  try:price=round(float(str(price).replace(',','.')),2) if price not in (None,'') else None
  except ValueError:raise EtsyError('Az ár szám legyen.') from None
  if price is not None and price<=0:raise EtsyError('Az ár nullánál nagyobb legyen.')
  cfg['price']=price
 s.db.execute('INSERT OR REPLACE INTO etsy_settings VALUES(?,?)',(idea,json.dumps(cfg)));s.db.commit()
 return dict(settings=cfg)

def midnight():
 return datetime.datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()

def ideas(s):
 import venture_build
 try:folders=s.safe_path(venture_build.PID,'workspace').glob('product-*/listings.json')
 except (OSError,ValueError):return []
 return sorted(p.parent.name[8:] for p in folders)

def tick(s,now=None):
 """One step at a time: a listing to a draft, or a draft to live where the owner switched that on."""
 now=now or time.time()
 if now-_pace['at']<PACE:return False
 _pace['at']=now
 if not connected():return False
 if now<connections.read(STATE).get('retry_at',0):return False
 schema(s);start=midnight()
 uploaded=s.db.execute('SELECT count(*) FROM etsy_uploads WHERE uploaded>=?',(start,)).fetchone()[0]
 published=s.db.execute('SELECT count(*) FROM etsy_uploads WHERE published>=?',(start,)).fetchone()[0]
 for idea in ideas(s):
  cfg=settings(s,idea)
  if not cfg['auto'] and not cfg['live']:continue
  product=product_folder(s,idea)
  for item in listings(product):
   design=str(item['id']);row=row_of(s,idea,design) or {}
   if not (product/'designs'/(design+'.png')).is_file() or row.get('state')=='active' or row.get('tries',0)>=TRIES:continue
   going_live=row.get('state')=='draft'
   if going_live and (not cfg['live'] or published>=DAILY_LIVE):continue
   if not going_live and (not cfg['auto'] or (not row.get('listing_id') and uploaded>=DAILY_DRAFTS)):continue
   try:
    if going_live:publish(s,idea,design)
    else:upload(s,idea,item,cfg)
   except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
    mark(s,idea,design,state=row.get('state') or 'failed',error=str(exc)[:400],tries=row.get('tries',0)+1,title=row.get('title') or clean_title(item.get('title')));update_state(retry_at=now+COOLDOWN)
   return True
 return False

LABEL={'draft':'Piszkozat az Etsyn','active':'Élő az Etsyn','uploading':'Feltöltés közben','failed':'Nem sikerült'}

def view(s,idea):
 schema(s);idea=key_of(idea);product=product_folder(s,idea);items=listings(product);cfg=settings(s,idea);state=connections.read(STATE)
 rows=[]
 for item in items:
  design=str(item['id']);row=row_of(s,idea,design) or {};ready=(product/'designs'/(design+'.png')).is_file()
  status=row.get('state') or ('new' if ready else 'waiting')
  rows.append(dict(id=design,title=row.get('title') or clean_title(item.get('title')),state=status,label=LABEL.get(status) or ('Sorra kerül' if ready else 'A rajz még nem készült el'),error=row.get('error') or '',stuck=row.get('tries',0)>=TRIES,listing=row.get('listing_id') if status=='active' else ''))
 count=lambda *states:sum(r['state'] in states for r in rows)
 start=midnight()
 return dict(applicable=bool(items),configured=bool(connections.secret('etsy')),connected=connected(),shop=state.get('shop'),callback=state.get('callback') or '',login=state.get('login') or '',login_error=state.get('login_error') or '',settings=cfg,
  total=len(rows),drafts=count('draft','uploading'),live=count('active'),left=count('new','failed'),waiting=count('waiting'),rows=rows,daily_live=DAILY_LIVE,fee=FEE,
  uploaded_today=s.db.execute('SELECT count(*) FROM etsy_uploads WHERE uploaded>=?',(start,)).fetchone()[0],published_today=s.db.execute('SELECT count(*) FROM etsy_uploads WHERE published>=?',(start,)).fetchone()[0],
  retry_at=state.get('retry_at') or 0)

def open_page(target):
 """Only Etsy's own pages, in the owner's browser."""
 target=str(target or '');listing=re.fullmatch(r'listing:(\d{1,20})',target)
 url={'apps':connections.PROVIDERS['etsy']['signup'],'drafts':DRAFTS_URL}.get(target) or ('https://www.etsy.com/listing/'+listing.group(1) if listing else None)
 if not url:raise ValueError('Ismeretlen Etsy-oldal.')
 subprocess.run(['/usr/bin/open',url],check=False,capture_output=True);return dict(opened=url)

def dispatch(s,op,args=None):
 args=args or {};idea=key_of(args.get('idea'))
 if op=='etsy_open':return open_page(args.get('target'))
 if op=='etsy_status':return view(s,idea)
 if op=='etsy_callback':return dict(callback=callback_url(deploy=True))
 if op=='etsy_connect':return connect(s)
 if op=='etsy_disconnect':return disconnect()
 if op=='etsy_settings':return save_settings(s,idea,args)
 if op=='etsy_retry':
  schema(s);s.db.execute("UPDATE etsy_uploads SET tries=0,error='' WHERE idea=?",(idea,));s.db.commit();update_state(retry_at=0)
  return dict(message='Újrapróbálom a sikerteleneket.')
 raise ValueError('Ismeretlen Etsy-művelet.')
