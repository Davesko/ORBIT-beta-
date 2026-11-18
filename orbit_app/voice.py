"""Hungarian voice for the main assistant ("Jarvis"): speech in, speech out, all on this Mac.

Speech recognition: ORBIT's own Whisper large-v3-turbo (mlx) with language fixed to Hungarian.
Speech output: the macOS Hungarian voice (Tünde). Audio files live only in Orbit/voice and are pruned; nothing leaves the machine.
Runs under the bridge's system Python 3.9, so the mlx model is called in the media runtime.
"""
import json,os,re,subprocess,time,uuid
from pathlib import Path

ROOT=Path.home()/'Library/Application Support/Orbit'
MAX_AUDIO=25*1024*1024
MAX_SPEAK=900
KEEP_SECONDS=3600

def folder(root=None):
 p=Path(root or ROOT)/'voice';p.mkdir(parents=True,exist_ok=True);return p

def prune(root=None):
 now=time.time()
 for f in folder(root).iterdir():
  try:
   if now-f.stat().st_mtime>KEEP_SECONDS:f.unlink()
  except OSError:pass

def recording(path,root=None):
 """Only a recording the app itself wrote into Orbit/voice may be transcribed."""
 p=Path(str(path or '')).resolve();base=folder(root).resolve()
 if base not in p.parents or not p.is_file() or p.suffix.lower() not in ('.m4a','.wav','.webm','.caf'):raise ValueError('Ismeretlen hangfelvétel.')
 if not 0<p.stat().st_size<=MAX_AUDIO:raise ValueError('A felvétel üres vagy túl hosszú.')
 return p

def runtime_python(root=None):
 return Path(root or ROOT)/'media-runtime/bin/python3'

def whisper_model(root=None):
 """The Whisper turbo weights ORBIT already uses for subtitles (internal models folder first)."""
 try:base=json.loads((Path(root or ROOT)/'model-storage.json').read_text()).get('base')
 except (OSError,ValueError):base=None
 for p in [Path(root or ROOT)/'models/whisper-large-v3-turbo']+([Path(base)/'audio/whisper-large-v3-turbo'] if base else []):
  if (p/'weights.safetensors').is_file():return p
 return Path(root or ROOT)/'models/whisper-large-v3-turbo'

WHISPER='''import json,sys,mlx_whisper
r=mlx_whisper.transcribe(sys.argv[1],path_or_hf_repo=sys.argv[2],language="hu",task="transcribe",condition_on_previous_text=False,verbose=None)
print(json.dumps({"text":r.get("text","")}))'''

def transcribe(path,root=None):
 """Hungarian text of a recording, and which engine produced it."""
 p=recording(path,root);prune(root)
 model=whisper_model(root)
 if not model.is_dir():raise ValueError('A helyi beszédfelismerő modell nem érhető el (csatlakoztasd a modell-SSD-t).')
 env=dict(os.environ,PATH=str(runtime_python(root).parent)+':/usr/bin:/bin',PYTHONDONTWRITEBYTECODE='1')
 try:r=subprocess.run([str(runtime_python(root)),'-c',WHISPER,str(p),str(model)],capture_output=True,text=True,timeout=180,env=env)
 except subprocess.TimeoutExpired:raise ValueError('A beszédfelismerés túl sokáig tartott.') from None
 if r.returncode!=0:raise ValueError('A beszédfelismerés nem sikerült: '+(r.stderr.strip().splitlines() or ['ismeretlen hiba'])[-1][:200])
 text=json.loads(r.stdout.strip().splitlines()[-1]).get('text','').strip()
 return dict(text=text,engine='Whisper (helyi)')

def speakable(text):
 """Plain sentences for speech: no markdown, links, code or tables; long answers are cut at a sentence."""
 t=re.sub(r'```.*?```',' ',str(text or ''),flags=re.S)
 t=re.sub(r'`([^`]*)`',r'\1',t);t=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',t);t=re.sub(r'https?://\S+','',t)
 t=re.sub(r'^\s*\|.*\|\s*$','',t,flags=re.M);t=re.sub(r'^\s*#+\s*','',t,flags=re.M);t=re.sub(r'^\s*[-*•]\s+','',t,flags=re.M)
 t=re.sub(r'[*_>#]+','',t);t=re.sub(r'\s+',' ',t).strip()
 if len(t)>MAX_SPEAK:
  cut=t[:MAX_SPEAK];end=max(cut.rfind('. '),cut.rfind('! '),cut.rfind('? '))
  t=(cut[:end+1] if end>200 else cut)+' A többit a képernyőn olvashatod.'
 return t

def speak(text,root=None):
 """A WAV file with the Hungarian spoken answer; the app plays it natively."""
 t=speakable(text)
 if not t:raise ValueError('Nincs felolvasható szöveg.')
 prune(root);out=folder(root)/('say-'+uuid.uuid4().hex+'.wav')
 try:subprocess.run(['/usr/bin/say','-v','Tünde','--file-format=WAVE','--data-format=LEI16@22050','-o',str(out),t],check=True,capture_output=True,timeout=60)
 except (subprocess.CalledProcessError,subprocess.TimeoutExpired):raise ValueError('A magyar hang nem érhető el (Rendszerbeállítások → Kisegítő lehetőségek → Felolvasott tartalom → Tünde).') from None
 return dict(path=str(out),engine='macOS · Tünde')

def status(root=None):
 return dict(whisper=whisper_model(root).is_dir(),folder=str(folder(root)))
