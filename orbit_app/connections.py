"""Native-only provider configuration; secrets never enter agent context or the UI response."""
import sys,contextlib,datetime,fcntl,json,os,re,sqlite3,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path.home()/'Library/Application Support/Orbit'
PROVIDERS={
 'pexels':dict(name='Pexels · stock videók',signup='https://www.pexels.com/api/',base='https://api.pexels.com/v1/'),
 'groq':dict(name='Groq',model='openai/gpt-oss-120b',signup='https://console.groq.com/keys',base='https://api.groq.com/openai/v1/'),
 'openrouter':dict(name='OpenRouter · ingyenes',model='openrouter/free',signup='https://openrouter.ai/settings/keys',base='https://openrouter.ai/api/v1/'),
 'gemini':dict(name='Gemini',model='gemini-3.8-flash',signup='https://aistudio.google.com/api-keys',base='https://generativelanguage.googleapis.com/v1beta/openai/'),
 'tavily':dict(name='Tavily',signup='https://app.tavily.com/',base='https://api.tavily.com/'),
 'jina':dict(name='Jina Reader',signup='https://jina.ai/reader/',base='https://r.jina.ai/'),
 'telegram':dict(name='Telegram',signup='https://t.me/BotFather',base='https://api.telegram.org/'),
 'deepseek':dict(name='DeepSeek · olcsó felhő',model='deepseek-flash',signup='https://platform.deepseek.com/api_keys',base='https://api.deepseek.com/'),
 'etsy':dict(name='Etsy · grafikák feltöltése',signup='https://www.etsy.com/developers/your-apps',base='https://api.etsy.com/v3/application/'),
 'stripe':dict(name='Stripe · bevétel (csak olvasás)',signup='https://dashboard.stripe.com/apikeys',base='https://api.stripe.com/v1/'),
 'cloudflare':dict(name='Cloudflare · élesítés',signup='https://dash.cloudflare.com/profile/api-tokens',base='https://api.cloudflare.com/client/v4/'),
}
def folder(root=None):
 p=Path(root or ROOT)/'connections';p.mkdir(parents=True,exist_ok=True,mode=0o700);return p
@contextlib.contextmanager
def lock(root=None):
 with (folder(root)/'settings.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX);yield

def read(name,root=None):
 try:return json.loads((folder(root)/name).read_text())
 except (OSError,ValueError):return {}
def atomic(name,data,root=None):
 base=folder(root);fd,tmp=tempfile.mkstemp(dir=base)
 try:
  with os.fdopen(fd,'w') as f:json.dump(data,f)
  os.chmod(tmp,0o600);os.replace(tmp,base/name)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def settings(root=None):
 data=read('settings.json',root);return dict(mode=data.get('mode','local'),preferred=data.get('preferred','groq'),share_context=bool(data.get('share_context',False)),providers=data.get('providers',{}))
def secret(provider,root=None):return read('secrets.json',root).get(provider,'')
def save(data,root=None):
 if set(data)-{'mode','preferred','provider','enabled','key','clear_key','model','chat_id','notifications','daily_limit','share_context'}:raise ValueError('Ismeretlen kapcsolatbeállítás.')
 with lock(root):
  c=settings(root);keys=read('secrets.json',root)
  if 'mode' in data:
   if data['mode'] not in ('local','local_first','hybrid'):raise ValueError('Ismeretlen AI üzemmód.')
   c['mode']=data['mode']
  if 'share_context' in data:
   if type(data['share_context'])!=bool:raise ValueError('Logikai megosztási beállítás szükséges.')
   c['share_context']=data['share_context']
  if 'preferred' in data:
   if data['preferred'] not in ('groq','gemini','openrouter','deepseek'):raise ValueError('Ismeretlen elsődleges AI.')
   c['preferred']=data['preferred']
  if data.get('provider'):
   p=data['provider']
   if p not in PROVIDERS:raise ValueError('Ismeretlen szolgáltató.')
   old=c['providers'].get(p,{});item=dict(old)
   for key in ('enabled','notifications'):
    if key in data:
     if type(data[key])!=bool:raise ValueError('Logikai kapcsoló szükséges.')
     item[key]=data[key]
   if 'model' in data:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}',data['model']):raise ValueError('Érvénytelen modellnév.')
    if p=='openrouter' and data['model']!='openrouter/free' and not data['model'].endswith(':free'):raise ValueError('OpenRouterhez csak openrouter/free vagy :free végű modell használható.')
    item['model']=data['model']
   if 'chat_id' in data:
    if data['chat_id'] and not re.fullmatch(r'-?[0-9]{1,25}|@[A-Za-z0-9_]{3,64}',str(data['chat_id'])):raise ValueError('Érvénytelen Telegram chat ID.')
    item['chat_id']=str(data['chat_id'])
   if 'daily_limit' in data:
    if type(data['daily_limit'])!=int or not 1<=data['daily_limit']<=1000:raise ValueError('A napi korlát 1–1000 hívás lehet.')
    item['daily_limit']=data['daily_limit']
   if data.get('key'):
    key=data['key'].strip()
    if not 10<=len(key)<=512 or any(c.isspace() for c in key):raise ValueError('Érvénytelen API-kulcs.')
    if p=='telegram' and not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',key):raise ValueError('Érvénytelen bot token.')
    # Revenue is read-only: only a restricted Stripe key (rk_...) is accepted, never a full secret key.
    if p=='stripe' and not key.startswith(('rk_live_','rk_test_')):raise ValueError('Csak korlátozott (rk_ kezdetű), olvasási jogú Stripe-kulcs adható meg.')
    # Etsy asks for both parts of the app's key in one header.
    if p=='etsy' and not re.fullmatch(r'[A-Za-z0-9]+:[A-Za-z0-9]+',key):raise ValueError('Az Etsy-kulcs „keystring:shared secret” alakú legyen.')
    keys[p]=key;item.pop('checked',None)
   if data.get('clear_key'):keys.pop(p,None);item.pop('checked',None)
   c['providers'][p]=item
  atomic('secrets.json',keys,root);atomic('settings.json',c,root)
 return status(root)
def db(root=None):
 d=sqlite3.connect(str(folder(root)/'usage.sqlite'),timeout=5)
 d.execute('CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,provider TEXT,created REAL,status TEXT,detail TEXT)')
 d.execute('CREATE TABLE IF NOT EXISTS cooldown(provider TEXT PRIMARY KEY,until REAL)');return d

def allowed(provider,root=None):
 c=settings(root)['providers'].get(provider,{})
 if not c.get('enabled') or (provider!='jina' and not secret(provider,root)):return False
 d=db(root)
 try:
  row=d.execute('SELECT until FROM cooldown WHERE provider=?',(provider,)).fetchone()
  return not row or row[0]<time.time()
 finally:d.close()
def reserve(provider,root=None,detail='',priority=False):
 d=db(root)
 try:
  d.execute('BEGIN IMMEDIATE');midnight=datetime.datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
  count=d.execute('SELECT count(*) FROM calls WHERE provider=? AND created>=?',(provider,midnight)).fetchone()[0]
  limit=settings(root)['providers'].get(provider,{}).get('daily_limit',50 if provider in ('tavily','openrouter') else 500 if provider in ('cloudflare','etsy') else 100)
  # priority: the once-a-day owner report must not be crowded out by other traffic.
  if count>=limit and not priority:raise ValueError('Elérted az ORBIT-ban beállított napi '+PROVIDERS[provider]['name']+' híváskorlátot.')
  # Tavily basic search costs one credit; leave headroom under the published free allowance.
  if provider=='tavily':
   month=datetime.datetime.now().astimezone().replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
   if d.execute("SELECT count(*) FROM calls WHERE provider='tavily' AND created>=?",(month,)).fetchone()[0]>=900:raise ValueError('Az ORBIT havi Tavily keresési kerete elfogyott (900 hívás).')
  n=d.execute("INSERT INTO calls(provider,created,status,detail) VALUES(?,?,'started',?)",(provider,time.time(),detail[:80])).lastrowid;d.commit();return n
 finally:d.close()
def finish(provider,call,status,detail='',root=None,cooldown=0):
 d=db(root)
 try:
  d.execute("UPDATE calls SET status=?,detail=trim(coalesce(detail,'')||' '||?) WHERE id=?",(status,detail[:160],call))
  if cooldown:d.execute('INSERT OR REPLACE INTO cooldown VALUES(?,?)',(provider,time.time()+cooldown))
  d.commit()
 finally:d.close()
def status(root=None):
 c=settings(root);d=db(root);result=[]
 try:
  midnight=datetime.datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
  for p,meta in PROVIDERS.items():
   item=c['providers'].get(p,{});cool=d.execute('SELECT until FROM cooldown WHERE provider=?',(p,)).fetchone()
   last=d.execute('SELECT status,detail,created FROM calls WHERE provider=? ORDER BY id DESC LIMIT 1',(p,)).fetchone()
   result.append(dict(id=p,name=meta['name'],signup=meta['signup'],configured=(p=='jina' or bool(secret(p,root))),enabled=bool(item.get('enabled')),model=item.get('model',meta.get('model','')),chat_id=item.get('chat_id',''),notifications=bool(item.get('notifications')),daily_limit=item.get('daily_limit',50 if p in ('tavily','openrouter') else 100),used_today=d.execute('SELECT count(*) FROM calls WHERE provider=? AND created>=?',(p,midnight)).fetchone()[0],checked=item.get('checked'),cooldown_until=cool[0] if cool else 0,last=dict(status=last[0],detail=last[1],at=last[2]) if last else None))
 finally:d.close()
 return dict(mode=c['mode'],preferred=c['preferred'],share_context=c['share_context'],providers=result)
class ProviderError(ValueError):pass
def under_test():
 """Running under the test runner (python -m unittest, or a test_*.py file)."""
 f=str(getattr(sys.modules.get('__main__'),'__file__','') or '')
 return Path(f).name.startswith('test_') or (Path(f).name=='__main__.py' and Path(f).parent.name=='unittest')
def http(provider,path='',payload=None,root=None,timeout=20,headers=None,text_response=False,testing=False,priority=False,on_text=None):
 if provider not in PROVIDERS:raise ValueError('Ismeretlen szolgáltató.')
 key=secret(provider,root)
 if not key and provider!='jina':raise ProviderError('Hiányzó '+PROVIDERS[provider]['name']+' API-kulcs.')
 if not testing and not allowed(provider,root):raise ProviderError(PROVIDERS[provider]['name']+': kikapcsolva vagy átmenetileg várakozik.')
 # The endpoint (never the key or payload) shows later what used up a daily limit.
 # A test may never reach a real service: until 2 Nov every test run sent the owner ~30 real Telegram messages
 # (1 225 on 1 Nov), because connections reads the real settings whatever root a test's Studio uses. A test that
 # replaces the network itself still runs.
 if under_test() and not type(urllib.request.build_opener).__module__.startswith('unittest'):
  raise ProviderError('Tesztfutás: valódi külső hívás nem indul ('+PROVIDERS[provider]['name']+').')
 frame=sys._getframe(1);caller=frame.f_globals.get('__name__','?')+':'+str(frame.f_lineno)
 call=reserve(provider,root,str(path).split('?')[0]+' '+caller,priority)
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kw):raise ProviderError('A szolgáltató átirányítása tiltva.')
 hdr={'Content-Type':'application/json','User-Agent':'ORBIT/2.2'}
 if key and provider in ('groq','gemini','openrouter','deepseek','jina','cloudflare','stripe'):hdr['Authorization']='Bearer '+key
 if provider=='pexels':hdr['Authorization']=key
 if provider=='etsy':hdr['x-api-key']=key
 if headers:hdr.update(headers)
 if provider=='tavily' and payload is not None:payload=dict(payload,api_key=key)
 url=PROVIDERS[provider]['base']+('bot'+key+'/' if provider=='telegram' else '')+path
 try:
  req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers=hdr)
  with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=timeout) as response:
   if on_text:
    from reply_stream import read_sse
    result=read_sse(response,on_text,timeout);finish(provider,call,'ok',root=root);return result
   raw=response.read(3*1024*1024+1)
  if len(raw)>3*1024*1024:raise ProviderError('Túl nagy szolgáltatásválasz.')
  result=raw.decode('utf-8') if text_response else json.loads(raw)
  finish(provider,call,'ok',root=root);return result
 except urllib.error.HTTPError as e:
  label={401:'Hibás vagy visszavont API-kulcs.',403:'Nincs jogosultság vagy a régió/csomag nem támogatott.',404:'A modell vagy API-végpont nem elérhető.',429:'A szolgáltatói kvóta vagy sebességkorlát elérve.'}.get(e.code,'A szolgáltató hibát jelzett (HTTP '+str(e.code)+').')
  try:delay=min(600,max(15,int(e.headers.get('Retry-After','60'))))
  except ValueError:delay=60
  size=None
  if e.code==413:
   # Only the two numbers are kept ("Limit 8000, Requested 12345"); the body is never stored.
   try:found=re.search(r'Limit\s+(\d+),\s*Requested\s+(\d+)',e.read(4000).decode('utf-8','replace'))
   except OSError:found=None
   if found:size=(int(found.group(1)),int(found.group(2)))
  # A too-large request says nothing about availability: no cooldown, so a smaller retry can go.
  finish(provider,call,'failed',label,root,cooldown=delay if e.code==429 else 300 if e.code in (401,403) else 0 if e.code in (400,413) else 20)
  error=ProviderError(PROVIDERS[provider]['name']+': '+label);error.size=size;error.code=e.code;raise error from None
 except Exception:
  finish(provider,call,'failed','A kapcsolat megszakadt vagy a szolgáltató nem válaszolt.',root,cooldown=30)
  raise ProviderError(PROVIDERS[provider]['name']+': a kapcsolat megszakadt vagy a szolgáltató nem válaszolt.') from None

def test(provider,root=None):
 if provider in ('groq','gemini','openrouter','deepseek'):
  if provider=='openrouter':http(provider,'key',root=root,testing=True)
  result=http(provider,'models',root=root,testing=True);names=[x['id'][7:] if provider=='gemini' and x['id'].startswith('models/') else x['id'] for x in result.get('data',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)]
  if provider=='openrouter':names=sorted(set(['openrouter/free']+[x['id'] for x in result.get('data',[]) if x.get('id','').endswith(':free') and float(x.get('pricing',{}).get('prompt','-1'))==0 and float(x.get('pricing',{}).get('completion','-1'))==0]))
  configured=settings(root)['providers'].get(provider,{}).get('model',PROVIDERS[provider]['model'])
  available=configured in names
 elif provider=='pexels':http(provider,'videos/search?query=nature&per_page=1',root=root,testing=True);names=[]
 elif provider=='telegram':
  result=http(provider,'getMe',root=root,testing=True)
  if not result.get('ok'):raise ProviderError('A bot hitelesítése sikertelen.')
 elif provider=='tavily':http(provider,'search',dict(query='Tavily official documentation',max_results=1,search_depth='basic'),root,testing=True);names=[]
 elif provider=='stripe':
  if 'available' not in http(provider,'balance',root=root,testing=True):raise ProviderError('A Stripe-kulcs nem látja az egyenleget (Balance: Read jog kell).')
  names=[]
 elif provider=='etsy':http(provider,'openapi-ping',root=root,testing=True);names=[]
 elif provider=='cloudflare':
  # The token must be active and see exactly the account ORBIT will publish into.
  if not http(provider,'user/tokens/verify',root=root,testing=True).get('success'):raise ProviderError('A Cloudflare-token nem aktív.')
  accounts=http(provider,'accounts',root=root,testing=True).get('result') or []
  if not accounts:raise ProviderError('A token nem lát Cloudflare-fiókot; adj neki fiókszintű jogosultságot.')
  names=[]
 else:http(provider,'https://example.com',root=root,text_response=True,testing=True);names=[]
 with lock(root):
  c=settings(root);c['providers'].setdefault(provider,{})['checked']=time.time();atomic('settings.json',c,root)
 return dict(ok=True,message=('Hitelesítés ellenőrizve. A kiválasztott modell elérhető.' if available else 'A kulcs működik, de válassz másik modellt az elérhető listából.') if provider in ('groq','gemini','openrouter') else 'Kapcsolat ellenőrizve. Üzenetet és videót nem küldtem.',models=names if provider in ('groq','gemini','openrouter') else [])
