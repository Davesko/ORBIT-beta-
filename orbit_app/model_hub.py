"""Verified local model inventory and explicit routing across two loopback stores."""
import json,os,socket,sqlite3,threading,time,urllib.request
from pathlib import Path
ROOT=Path.home()/'Library/Application Support/Orbit'
def raw(port,route,data=None,timeout=8):
 if route=='api/chat' and data is not None and not data.get('stream'):
  from inference_stream import chat
  return chat(port,data,timeout,ROOT)
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):raise ValueError('Átirányítás tiltva.')
 request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/'+route,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=timeout) as response:return json.loads(response.read(16*1024*1024))
def config():
 try:return json.loads((ROOT/'model-storage.json').read_text())
 except (OSError,ValueError):return {}
def online():
 c=config();return bool(c.get('mount') and os.path.ismount(c['mount']))
def answers(path,root=None,timeout=2.0,ttl=30):
 """Whether a folder on the model disk answers within timeout. On 2026-11-01 the exFAT model SSD hung: every
 read waited 20 s and then failed with EINTR, which took the app's main data request (snapshot) down. A
 missing folder is an answer; the result is kept ttl seconds so the frequent UI requests do not each wait."""
 cache=Path(root or ROOT)/'ssd-probe.json';path=str(path)
 try:
  c=json.loads(cache.read_text())
  if c.get('path')==path and 0<=time.time()-c.get('at',0)<ttl:return bool(c.get('ok'))
 except (OSError,ValueError):pass
 box={}
 def look():
  try:os.listdir(path);box['ok']=True
  # A missing folder or a refused listing is an answer; only a stall (EINTR, EIO, no reply) is a hung disk.
  except (FileNotFoundError,PermissionError):box['ok']=True
  except OSError as exc:box['ok']=False;box['error']=type(exc).__name__
 probe=threading.Thread(target=look,daemon=True);probe.start();probe.join(timeout)
 ok=box.get('ok',False)
 try:cache.write_text(json.dumps(dict(path=path,at=time.time(),ok=ok,error=box.get('error') or ('' if 'ok' in box else 'timeout'))))
 except OSError:pass
 return ok
# On 2026-11-01 a forced unmount and remount did not help: every exFAT disk (all served by macOS FSKit) hung the
# same way, 20 s then EINTR, so the stuck part was macOS's exFAT handler, which only a restart clears.
SSD_PORT=11435
HUNG_MESSAGE='A modelleket tároló SSD csatlakoztatva van, de nem válaszol. Válaszd le (Kiadás), húzd ki, és csatlakoztasd újra; ha utána sem válaszol, indítsd újra a Macet (a macOS exFAT-kezelője akadhatott el).'
def ssd_hung(root=None):
 """The model SSD is mounted but does not answer (as opposed to unplugged). The model server serving from it is
 asked first: the worker's own listing of the SSD timed out at 18:10 and again at 19:15 on 1 Nov while the disk
 and the server worked (18:10 cost the Autopilot 30 minutes), so the disk is listed only when the server is silent."""
 base=Path(root or ROOT)
 try:c=json.loads((base/'model-storage.json').read_text())
 except (OSError,ValueError):return False
 if not (c.get('base') and c.get('mount') and os.path.ismount(c['mount'])):return False
 cache=base/'ssd-hung.json'
 try:
  h=json.loads(cache.read_text())
  if 0<=time.time()-h.get('at',0)<30:return bool(h.get('hung'))
 except (OSError,ValueError):pass
 try:serving=bool(raw(SSD_PORT,'api/tags',timeout=3).get('models'))
 except Exception:serving=False
 hung=not serving and not answers(c['base'],root)
 try:cache.write_text(json.dumps(dict(at=time.time(),hung=hung,serving=serving)))
 except OSError:pass
 return hung
def inventory():
 result={};services=[]
 for port in (11434,11435):
  if port==11435 and not online():services.append(dict(port=port,available=False,message='Az SSD nincs csatlakoztatva.'));continue
  try:
   found=raw(port,'api/tags',timeout=3).get('models',[])
   services.append(dict(port=port,available=True,models=len(found)))
   for m in found:
    m=dict(m,storage='SSD' if port==11435 else 'Belső',port=port)
    result[m['name']]=m
  except Exception:services.append(dict(port=port,available=False,message='A helyi modellkiszolgáló nem válaszol.'))
 return list(result.values()),services
_cache=(None,[],[])
def models():
 global _cache
 if _cache[0] is not None and time.monotonic()-_cache[0]<3:return [dict(m) for m in _cache[1]]
 found,services=inventory();_cache=(time.monotonic(),found,services);return found

def release_other(port):
 other=11434 if port==11435 else 11435
 try:
  for m in raw(other,'api/ps',timeout=2).get('models',[]):raw(other,'api/generate',dict(model=m['name'],keep_alive=0),timeout=15)
 except Exception:pass

def request(route,data=None,timeout=8):
 if route=='api/tags':return {'models':models()}
 data=dict(data or {});purpose=data.pop('_orbit_purpose',None);jobid=data.pop('_orbit_job',None);model=data.get('model','')
 available=models()
 chosen=None
 if model=='auto':
  from model_router import choose
  messages=data.get('messages',[]);last=next((m for m in reversed(messages) if m.get('role')=='user'),{})
  chosen=choose(last.get('content',''),available,'auto',bool(last.get('images')),purpose=purpose);model=chosen['model'];data['model']=model
 if route=='api/pull':
  if not online():raise ValueError('A letöltéshez csatlakoztasd a beállított modelltárat.')
  port=11435
 else:
  entry=next((m for m in available if m['name']==model),None)
  if not entry:raise ValueError('A modell jelenleg nem érhető el: '+model+'. Ellenőrizd a Modellek oldalon az SSD és a kiszolgáló állapotát.')
  port=entry.get('port',11435 if entry.get('storage')=='SSD' else 11434)
 if jobid and (ROOT/'studio.sqlite').is_file():
  try:
   db=sqlite3.connect(str(ROOT/'studio.sqlite'),timeout=5);db.execute("UPDATE jobs SET payload=json_set(payload,'$.selected_model',?) WHERE id=?",(model,jobid));db.commit();db.close()
  except sqlite3.Error:pass
 if route=='api/chat':
  release_other(port)
  if jobid:data['_orbit_progress_job']=jobid
 try:result=raw(port,route,data,timeout)
 except (TimeoutError,socket.timeout) as error:raise ValueError('A helyi AI nem válaszolt az időkereten belül. Ez modellhívási hiba; nem jelenti az SSD leválasztását.') from error
 except urllib.error.HTTPError as error:
  # The server answered and refused this request (for example a prompt without the task). That
  # is not a connection failure: reporting it as one made self-heal restart the model server.
  try:reason=json.loads(error.read(4000) or b'{}').get('error','')
  except (ValueError,OSError):reason=''
  raise ValueError('A helyi modell elutasította a kérést ('+str(error.code)+(': '+str(reason)[:200] if reason else '')+').') from error
 except urllib.error.URLError as error:
  if isinstance(error.reason,(TimeoutError,socket.timeout)):raise ValueError('A helyi AI válasza túllépte az időkeretet. Az SSD állapota külön ellenőrizhető a Modellek oldalon.') from error
  raise ValueError('A helyi AI kiszolgálóhoz nem sikerült kapcsolódni. Ellenőrizd a Modellek oldalon a kiszolgáló állapotát.') from error
 if route=='api/chat':result['_orbit_route']=chosen or dict(model=model,policy='quality')
 return result

def unload():
 for port in (11434,11435):
  try:
   for m in raw(port,'api/ps',timeout=2).get('models',[]):raw(port,'api/generate',dict(model=m['name'],keep_alive=0),timeout=20)
  except Exception:pass

def status():
 c=config();downloads={};mounted=online();readable=False;hung=ssd_hung()
 try:readable=mounted and not hung and Path(c.get('ollama','/nonexistent')).is_dir()
 except OSError:pass
 try:downloads=json.loads((ROOT/'model-downloads.json').read_text())
 except (OSError,ValueError):pass
 found,services=inventory();image=Path(c.get('images','/nonexistent'))/'flux-schnell-4bit'
 from media_tools import media_models
 return dict(media_models=media_models(ROOT),config=c,mounted=mounted,readable=readable,checked_at=time.time(),downloads=downloads,models=found,services=services,flux_ready=mounted and (image/'.orbit-ready').is_file(),flux_path=str(image),message='SSD csatlakoztatva, a modelltár olvasható.' if readable else HUNG_MESSAGE if hung else 'Az SSD nincs csatlakoztatva vagy a modelltár nem olvasható.')

def brief():
 info=status();return dict({k:info[k] for k in ('mounted','readable','checked_at','services','message')},model_store=info['config'].get('base'),models=[dict(name=m['name'],storage=m['storage']) for m in info['models']])


def loaded_chat_model():
 """The text model already in memory on either server, if any: a background job that uses it causes no swap."""
 from model_router import usable
 names={m['name'] for m in usable(models())}
 for port in (SSD_PORT,11434):
  try:
   for m in raw(port,'api/ps',timeout=1).get('models',[]):
    name=m.get('name') or m.get('model')
    if name in names and 'embed' not in name:return name
  except Exception:continue
 return None
