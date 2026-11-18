"""Modellkereső: which local models run well on this very machine, and one click to download and use them.

Searches Hugging Face's GGUF models and has Ollama pull them, so a finished download is in the model list by itself.
The fit is computed from the file size and this Mac's memory; the speed is an estimate from its memory bandwidth until the
owner measures it. Gated models are left out: they would need an account.
"""
import json,platform,re,shutil,subprocess,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
import connections,model_hub

HF='https://huggingface.co/api/'
# Memory bandwidth in GB/s bounds how fast a Mac runs a model of a given size.
BANDWIDTH={'M1':68,'M1 Pro':200,'M1 Max':400,'M1 Ultra':800,'M2':100,'M2 Pro':200,'M2 Max':400,'M2 Ultra':800,'M3':100,'M3 Pro':150,'M3 Max':400,'M3 Ultra':800,'M4':120,'M4 Pro':273,'M4 Max':546,'M5':153}
RESERVED=6
QUANTS=('Q4_K_M','Q5_K_M','Q6_K','Q8_0','Q3_K_M','Q4_0','Q4_K_S','Q5_K_S','Q2_K','F16','BF16')
SKIP=re.compile(r'embed|rerank|whisper|tts|clip-|vision-only|qwen[-_]image|flux|stable[-_]diffusion|(?:^|/)wan[\d._-]|diffusion',re.I)
NON_CHAT={'text-to-image','image-to-image','text-to-video','image-to-video','text-to-audio','automatic-speech-recognition'}

def chat_candidate(row):
 return not (row.get('gated') or row.get('private') or SKIP.search(row.get('id',row.get('repo',''))) or row.get('pipeline_tag') in NON_CHAT or NON_CHAT.intersection(row.get('tags') or []))
PUBLISHERS=('unsloth','bartowski','ggml-org','lmstudio-community','Qwen','google')
NOT_FOR_ALL=re.compile(r'uncensored|abliterated|nsfw|erotic|roleplay',re.I)
FILE='model-finder.json'
CACHE_HOURS=6
PULL_NAME=re.compile(r'^hf\.co/[A-Za-z0-9._-]{1,80}/[A-Za-z0-9._-]{1,100}:[A-Za-z0-9._-]{1,30}$')
HELP={'ollama':'https://ollama.com/download'}

def get(path,params=None,timeout=15):
 """The one place that reaches Hugging Face. A test run never does."""
 if connections.under_test():raise ValueError('Tesztfutás: valódi hálózati hívás nem indul.')
 url=HF+path+('?'+urllib.parse.urlencode(params) if params else '')
 req=urllib.request.Request(url,headers={'User-Agent':'ORBIT'})
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as r:return json.loads(r.read(6*1024*1024))
 except (urllib.error.URLError,OSError,ValueError):raise ValueError('A modellkereső most nem éri el a Hugging Face-t. Ellenőrizd az internetkapcsolatot.') from None

def sysctl(name):
 try:return subprocess.run(['/usr/sbin/sysctl','-n',name],capture_output=True,text=True,timeout=3).stdout.strip()
 except (OSError,subprocess.SubprocessError):return ''

def machine():
 chip=sysctl('machdep.cpu.brand_string') or platform.processor() or 'Ismeretlen gép'
 try:ram=int(sysctl('hw.memsize'))/1024**3
 except ValueError:ram=0
 name=re.sub(r'^Apple\s+','',chip);band=BANDWIDTH.get(name) or BANDWIDTH.get(' '.join(name.split()[:2]))
 c=model_hub.config();ssd=bool(c.get('mount') and model_hub.online());where=Path(c['base']) if ssd and c.get('base') else Path.home()
 try:free=shutil.disk_usage(where).free/1024**3
 except OSError:free=0
 return dict(chip=chip,ram_gb=round(ram),usable_gb=round(max(ram-RESERVED,ram*.6),1),bandwidth=band,disk_free_gb=round(free,1),disk=('Külső modelltár' if ssd else 'Belső lemez'),needs_disk=bool(c) and not ssd)

def fit(size_bytes,m=None):
 """How a model of this size runs here: fast, good, tight or not at all."""
 m=m or machine();gb=size_bytes/1024**3;need=gb*1.2+1
 usable=m['usable_gb'] or 1
 level='fast' if need<=usable*.5 else 'good' if need<=usable*.8 else 'tight' if need<=usable else 'no'
 speed=round(m['bandwidth']/gb) if m.get('bandwidth') and gb>0 else None
 label={'fast':'Gyorsan fut','good':'Jól fut','tight':'Elfut, de szűkös','no':'Nem fut el ezen a gépen'}[level]
 return dict(level=level,label=label,need_gb=round(need,1),size_gb=round(gb,1),speed=speed if level!='no' else None)

def quant_of(name):
 found=re.search(r'(?<![A-Za-z0-9])((?:[QqFf]\d+[A-Za-z0-9_]*)|(?:BF16))(?:-\d+-of-\d+)?\.gguf$',name)
 return found.group(1).upper() if found else None

def variants(repo,m=None):
 """A repository's sizes and qualities, the one recommended for this machine first."""
 if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}/[A-Za-z0-9._-]{1,100}',str(repo or '')):raise ValueError('Ismeretlen modell.')
 m=m or machine();found=[]
 for f in get('models/'+repo+'/tree/main?recursive=1'):
  name=f.get('path','').rsplit('/',1)[-1]
  if not name.endswith('.gguf') or 'mmproj' in name.lower():continue
  q=quant_of(name)
  if q:found.append((name[:name.upper().rfind(q)].rstrip('-._'),q,int(f.get('size') or (f.get('lfs') or {}).get('size') or 0)))
 # A repository may also hold draft or stripped builds of the same model; the plain one has the shortest name.
 main=min((x[0] for x in found),key=len,default='');sizes={}
 for prefix,q,size in found:
  if prefix==main:sizes[q]=sizes.get(q,0)+size
 out=[dict(quant=q,name='hf.co/'+repo+':'+q,size=size,fit=fit(size,m)) for q,size in sizes.items() if size]
 rank={q:i for i,q in enumerate(QUANTS)}
 usable=[o for o in out if o['fit']['level'] in ('fast','good')]
 out.sort(key=lambda o:(o not in usable,rank.get(o['quant'],len(QUANTS)),o['size']))
 return dict(repo=repo,variants=out,best=out[0]['quant'] if out and out[0]['fit']['level']!='no' else None)

def clean(row):
 return dict(repo=row['id'],downloads=row.get('downloads') or 0,likes=row.get('likes') or 0,updated=row.get('lastModified') or '')

def search(query='',limit=50):
 params=dict(filter='gguf',sort='downloads',direction='-1',limit=str(max(limit*2,20)))
 if str(query or '').strip():params['search']=str(query).strip()[:80]
 rows=get('models',params)
 return [clean(r) for r in rows if chat_candidate(r)][:limit]

def store(root=None):
 try:return json.loads((Path(root or model_hub.ROOT)/FILE).read_text())
 except (OSError,ValueError):return {}

def keep(data,root=None):
 path=Path(root or model_hub.ROOT)/FILE;tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.replace(path)

def recommend(limit=12,now=None,refresh=False):
 """The most used models of well-known publishers that suit this machine. Asked at most every few hours."""
 now=now or time.time();saved=store();cached=saved.get('recommended') or {}
 if not refresh and cached.get('version')==2 and cached.get('items') and now-cached.get('at',0)<CACHE_HOURS*3600:return [r for r in cached['items'] if chat_candidate(r)]
 m=machine();items=[];seen=set();rows=[]
 for author in PUBLISHERS:
  try:rows+=get('models',dict(author=author,filter='gguf',sort='downloads',direction='-1',limit='10'))
  except ValueError:pass
 for row in sorted(rows,key=lambda r:-(r.get('downloads') or 0)):
  name=row['id'].split('/')[-1];family=re.sub(r'[-_.]?gguf$','',name,flags=re.I).casefold()
  if family in seen or not chat_candidate(row) or NOT_FOR_ALL.search(name):continue
  seen.add(family)
  try:v=variants(row['id'],m)
  except ValueError:continue
  best=v['variants'][0] if v['best'] else None
  if best and best['fit']['level'] in ('fast','good') and best['fit']['size_gb']>=1:items.append(dict(clean(row),best=best))
  if len(items)>=limit:break
 keep(dict(saved,recommended=dict(at=now,items=items,version=2)));return items

def installed(m=None):
 m=m or machine();results=store().get('measured') or {};out=[]
 for row in model_hub.models():
  if SKIP.search(row['name']):continue
  out.append(dict(name=row['name'],size=row.get('size') or 0,storage=row.get('storage') or '',fit=fit(row.get('size') or 0,m),measured=results.get(row['name'])))
 return out

def status(s):
 m=machine();services=model_hub.inventory()[1]
 row=s.db.execute("SELECT j.id,j.prompt,j.status,r.label FROM jobs j LEFT JOIN job_runtime r ON r.job=j.id WHERE j.kind='model_pull' AND j.status IN ('queued','running') ORDER BY j.created DESC LIMIT 1").fetchone()
 failed=s.db.execute("""SELECT error,prompt FROM
  (SELECT status,error,prompt,finished FROM jobs WHERE kind='model_pull' ORDER BY created DESC LIMIT 1)
  WHERE status='failed' AND finished>?""",(time.time()-3600,)).fetchone()
 percent=re.search(r'(\d+)%',row['label'] or '') if row else None
 from generation_downloads import catalog
 return dict(generation=catalog(s),machine=m,ollama=any(x.get('available') for x in services),installed=installed(m),pulling=dict(job=row['id'],name=row['prompt'].split(': ',1)[-1],label=row['label'] or 'Várakozik',percent=int(percent.group(1)) if percent else None) if row else None,failed=dict(name=failed['prompt'].split(': ',1)[-1],error=failed['error'][:300]) if failed else None)

def pull(s,name,size=0):
 """Starts the download. Disk space is checked first, a half-finished model on a full disk helps nobody."""
 name=str(name or '').strip()
 if not PULL_NAME.match(name):raise ValueError('Ismeretlen modellnév.')
 if s.db.execute("SELECT 1 FROM jobs WHERE kind='model_pull' AND status IN ('queued','running')").fetchone():raise ValueError('Már van folyamatban modellletöltés.')
 m=machine()
 if m['needs_disk']:raise ValueError('A beállított modelltár nincs csatlakoztatva. Csatlakoztasd, és próbáld újra.')
 gb=int(size or 0)/1024**3
 if gb and gb*1.1>m['disk_free_gb']:raise ValueError('Nincs elég hely: '+str(round(gb,1))+' GB kell, '+str(m['disk_free_gb'])+' GB szabad ('+m['disk']+').')
 agent=s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
 if not agent:raise ValueError('Nincs elérhető ügynök a letöltéshez.')
 return dict(job=s.enqueue(agent[0],'Modell telepítése: '+name,'model_pull',payload=dict(model=name)))

def remove(name):
 """A downloaded model off the disk, on the owner's click. It can be downloaded again."""
 row=next((m for m in model_hub.models() if m['name']==name),None)
 if not row:raise ValueError('Ez a modell már nincs a gépen.')
 if connections.under_test():raise ValueError('Tesztfutás: nem törlök modellt.')
 req=urllib.request.Request('http://127.0.0.1:'+str(row.get('port') or 11434)+'/api/delete',data=json.dumps(dict(model=name)).encode(),headers={'Content-Type':'application/json'},method='DELETE')
 urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=30).read()
 return dict(removed=name,message='A(z) '+name+' lekerült a gépről.')

def queue_benchmark(s,name):
 if not any(m['name']==name for m in model_hub.models()):raise ValueError('Ez a modell nincs a gépen.')
 agent=s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
 if s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='model_benchmark'").fetchone():raise ValueError('Már fut egy sebességmérés.')
 return dict(job=s.enqueue(agent[0],'Sebességmérés: '+name,'assist',payload=dict(task='model_benchmark',model=name,local_only=True)))

def benchmark(s,job):
 """A short real answer, timed by the model server itself."""
 from studio import local_api
 name=json.loads(job['payload'])['model']
 r=local_api('ollama','api/chat',dict(model=name,_orbit_job=job['id'],messages=[dict(role='user',content='Write three sentences about the sea.')],stream=False,think=False,keep_alive='1m',options=dict(num_predict=120,num_ctx=2048)),timeout=300)
 speed=round(r.get('eval_count',0)/(r.get('eval_duration') or 1)*1e9,1)
 if speed<=0:raise ValueError('A mérés nem adott eredményt.')
 saved=store();saved.setdefault('measured',{})[name]=dict(tokens_per_second=speed,at=time.time());keep(saved)
 return name+': '+str(speed)+' token/mp'

def open_help(target):
 url=HELP.get(str(target or ''))
 if not url:raise ValueError('Ismeretlen oldal.')
 subprocess.run(['/usr/bin/open',url],check=False,capture_output=True);return dict(opened=url)

def dispatch(s,op,args=None):
 args=args or {}
 if op=='finder_status':return status(s)
 if op=='finder_recommend':return dict(items=recommend(refresh=bool(args.get('refresh'))))
 if op=='finder_search':
  category=args.get('category')
  if category in ('video','image'):
   from generation_downloads import search as generation_search
   return dict(items=generation_search(s,category,args.get('query')))
  return dict(items=search(args.get('query')))
 if op=='finder_variants':return variants(args.get('repo'))
 if op=='finder_generation_pull':
  from generation_downloads import enqueue
  return enqueue(s,args.get('id'))
 if op=='finder_pull':return pull(s,args.get('name'),args.get('size'))
 if op=='finder_delete':return remove(args.get('name'))
 if op=='finder_benchmark':return queue_benchmark(s,args.get('name'))
 if op=='finder_open':return open_help(args.get('target'))
 raise ValueError('Ismeretlen modellművelet.')
