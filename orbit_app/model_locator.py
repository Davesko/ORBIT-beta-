"""Finds the AI models already on this Mac, so a new ORBIT can use them at once.

Three kinds are recognised:
- a running Ollama (port 11434): its models appear in ORBIT by themselves;
- an Ollama model folder (manifests/ + blobs/), on the internal disk or an external drive: ORBIT serves it as its
  second model store on port 11435, read in place, nothing copied;
- GGUF files (LM Studio, downloads): they can be imported into Ollama, which copies them into Ollama's own store.

Nothing is downloaded or deleted here. The owner picks the folder; ORBIT only reads it."""
import json,os,plistlib,subprocess,time
from pathlib import Path

HOME=Path.home()
ROOT=HOME/'Library/Application Support/Orbit'
OLLAMA_APP=next((p for p in (Path('/Applications/Ollama.app'),HOME/'Applications/Ollama.app') if p.is_dir()),None)
GGUF_PLACES=[HOME/'.lmstudio/models',HOME/'.cache/lm-studio/models',HOME/'Library/Application Support/LM Studio/models',HOME/'Downloads',HOME/'Models',HOME/'models']
SSD_AGENT='hu.orbit.ssd-models'

def ollama_cli():
 for p in ((OLLAMA_APP/'Contents/Resources/ollama') if OLLAMA_APP else None,Path('/usr/local/bin/ollama'),Path('/opt/homebrew/bin/ollama')):
  if p and p.is_file():return str(p)
 return None

def running():
 import model_hub
 try:return [m['name'] for m in model_hub.raw(11434,'api/tags',timeout=2).get('models',[])]
 except Exception:return None

def ollama_models(folder):
 """Model names in an Ollama store, read from its manifests; empty when it is not one."""
 folder=Path(folder);man=folder/'manifests'
 if not man.is_dir() or not (folder/'blobs').is_dir():return []
 names=[]
 for f in man.glob('*/*/*/*'):
  if f.is_file() and not f.name.startswith('.'):
   host,ns,model,tag=f.relative_to(man).parts
   names.append((model if ns=='library' else ns+'/'+model)+':'+tag if host!='hf.co' else 'hf.co/'+ns+'/'+model+':'+tag)
 return sorted(set(names))

def _walk(base,depth,want,deadline,found,limit=60):
 try:entries=list(os.scandir(base))
 except OSError:return
 for e in entries:
  if time.monotonic()>deadline or len(found)>=limit:return
  if e.name.startswith('.') and e.name!='.ollama':continue
  try:
   if e.is_dir(follow_symlinks=False):
    if want=='ollama' and (Path(e.path)/'manifests').is_dir() and (Path(e.path)/'blobs').is_dir():found.append(e.path)
    elif depth>0 and e.name not in ('node_modules','Library','.Trash','System','private'):_walk(e.path,depth-1,want,deadline,found,limit)
   elif want=='gguf' and e.name.lower().endswith('.gguf') and e.stat().st_size>50_000_000:found.append(e.path)
  except OSError:continue

def scan(s=None):
 """What is on this Mac now. Bounded: at most a few seconds, external drives a few folders deep."""
 deadline=time.monotonic()+4
 stores=[]
 for p in [HOME/'.ollama/models']:
  if ollama_models(p):stores.append(str(p))
 volumes=[str(v) for v in Path('/Volumes').glob('*') if v.is_dir() and os.path.ismount(v) and v.name!='Macintosh HD']
 for v in volumes:_walk(v,3,'ollama',deadline,stores)
 ggufs=[]
 for p in GGUF_PLACES:
  if p.is_dir():_walk(str(p),3,'gguf',deadline,ggufs)
 for v in volumes:_walk(v,2,'gguf',deadline,ggufs)
 import model_hub
 c=model_hub.config()
 live=running()
 return dict(ollama_installed=bool(OLLAMA_APP or ollama_cli()),ollama_running=live is not None,running_models=live or [],
             stores=[dict(path=p,models=ollama_models(p),default=p==str(HOME/'.ollama/models'),connected=c.get('ollama')==p) for p in dict.fromkeys(stores)],
             gguf=[dict(path=p,name=Path(p).stem,gb=round(os.path.getsize(p)/1e9,1)) for p in dict.fromkeys(ggufs)][:40],
             connected=c.get('ollama'))

def start_ollama():
 if not OLLAMA_APP:raise ValueError('Az Ollama nincs telepítve. Töltsd le az ollama.com oldalról, majd próbáld újra.')
 subprocess.Popen(['/usr/bin/open','-a',str(OLLAMA_APP)])
 return dict(started=True,message='Az Ollama indul; néhány másodperc múlva a modelljei megjelennek.')

def mount_of(path):
 p=Path(path).resolve()
 while not os.path.ismount(p):p=p.parent
 return str(p)

def ssd_agent(root=ROOT):
 """The model server for a chosen folder, as a LaunchAgent of this user (the same one the original ORBIT uses)."""
 plist=HOME/'Library/LaunchAgents'/(SSD_AGENT+'.plist');core=root/'core'
 if not (core/'ssd_server.py').is_file():return False
 data=dict(Label=SSD_AGENT,ProgramArguments=['/usr/bin/python3',str(core/'ssd_server.py')],RunAtLoad=True,KeepAlive=True,ThrottleInterval=15,
           StandardOutPath=str(root/'logs/ssd-models.out.log'),StandardErrorPath=str(root/'logs/ssd-models.err.log'))
 (root/'logs').mkdir(parents=True,exist_ok=True);plist.parent.mkdir(parents=True,exist_ok=True)
 fresh=not plist.exists()
 if fresh:plist.write_bytes(plistlib.dumps(data))
 uid=str(os.getuid())
 if fresh:subprocess.run(['/bin/launchctl','bootstrap','gui/'+uid,str(plist)],capture_output=True)
 else:subprocess.run(['/bin/launchctl','kickstart','-k','gui/'+uid+'/'+SSD_AGENT],capture_output=True)
 return True

def use(s,path,root=ROOT):
 """Connects the chosen folder. An Ollama store is served in place; a GGUF folder lists what can be imported."""
 path=Path(str(path or '')).expanduser()
 if not path.is_dir():raise ValueError('Ez a mappa nem érhető el.')
 for candidate in (path,path/'models',path/'ollama',path/'.ollama/models'):
  names=ollama_models(candidate)
  if names:
   if candidate.resolve()==(HOME/'.ollama/models').resolve():
    if running() is None and OLLAMA_APP:start_ollama()
    return dict(kind='ollama-default',models=names,message='Ez az Ollama saját modellmappája: '+str(len(names))+' modell. Az Ollama futása közben az ORBIT magától látja őket.')
   if not OLLAMA_APP:raise ValueError('A mappában '+str(len(names))+' Ollama-modell van, de a kiszolgálásukhoz az ingyenes Ollama app kell. Telepítsd az ollama.com oldalról.')
   cfg=dict(mount=mount_of(candidate),base=str(candidate.parent),ollama=str(candidate),images=str(candidate.parent/'images'))
   root.mkdir(parents=True,exist_ok=True);tmp=root/'model-storage.json.tmp';tmp.write_text(json.dumps(cfg,indent=1));tmp.replace(root/'model-storage.json')
   ssd_agent(root)
   return dict(kind='ollama-store',models=names,path=str(candidate),message=str(len(names))+' modell bekötve innen: '+str(candidate)+'. A mappát az ORBIT helyben olvassa, semmit nem másol.')
 ggufs=[];_walk(str(path),3,'gguf',time.monotonic()+4,ggufs)
 if ggufs:return dict(kind='gguf',files=[dict(path=p,name=Path(p).stem,gb=round(os.path.getsize(p)/1e9,1)) for p in ggufs],message=str(len(ggufs))+' GGUF-modellfájl található. Importálással az Ollama tárába kerülnek (ez másolat, a szabad hely kell hozzá).')
 raise ValueError('Ebben a mappában nem találtam AI-modellt (Ollama-tárat vagy .gguf fájlt).')

def import_gguf(s,path,name='',root=ROOT):
 """Copies one GGUF file into Ollama's store under a name; runs in the background, the Models page shows it when done."""
 path=Path(str(path or ''))
 if not path.is_file() or path.suffix.lower()!='.gguf':raise ValueError('Válassz egy .gguf modellfájlt.')
 cli=ollama_cli()
 if not cli:raise ValueError('Az importáláshoz az Ollama app kell. Telepítsd az ollama.com oldalról.')
 if running() is None:raise ValueError('Indítsd el az Ollamát, majd próbáld újra.')
 import re
 import unicodedata
 plain=''.join(c for c in unicodedata.normalize('NFKD',(name or path.stem).casefold()) if not unicodedata.combining(c))
 name=re.sub(r'[^a-z0-9._-]+','-',plain).strip('-')[:60] or 'imported'
 work=root/'imports';work.mkdir(parents=True,exist_ok=True);(root/'logs').mkdir(parents=True,exist_ok=True)
 modelfile=work/(name+'.Modelfile');modelfile.write_text('FROM '+str(path)+'\n')
 with (root/'logs'/('import-'+name+'.log')).open('w') as log:
  subprocess.Popen([cli,'create',name,'-f',str(modelfile)],stdout=log,stderr=log,env=dict(os.environ,OLLAMA_HOST='127.0.0.1:11434'),start_new_session=True)
 return dict(name=name,message='Importálás elindult: '+name+'. Nagy fájlnál néhány percig tart; utána a Modellek között látod.')

def dispatch(s,op,args=None):
 args=args or {}
 if op=='locator_scan':return scan(s)
 if op=='locator_start':return start_ollama()
 if op=='locator_use':return use(s,args.get('path'))
 if op=='locator_import':return import_gguf(s,args.get('path'),args.get('name',''))
 raise ValueError('Ismeretlen modellkeresési művelet.')
