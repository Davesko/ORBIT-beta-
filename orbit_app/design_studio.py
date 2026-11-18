"""ORBIT renders a digital product's designs itself: print-on-demand graphics, colouring pages, wall art.

The builder writes designs.json in the product folder (an English image description per design); ORBIT
renders each with its local FLUX model and makes it print-ready (design_post.py): designs/<id>.png, a
thumbnail, and for colouring pages one printable designs/coloring-book.pdf. Rendering waits until the
Autopilot is not using the model, one design at a time. Nothing is uploaded or listed anywhere: selling
through a marketplace is the owner's step.
"""
import hashlib,json,os,re,subprocess,time,uuid
from pathlib import Path

MAX=24
TRIES=2
# Each kind gets a fixed style suffix and render size (FLUX schnell, 4 steps, ~70 s on the M4).
KINDS={'apparel':(', flat vector illustration, bold clean shapes, limited colour palette, one centred graphic, isolated on a plain pure white background, no text, no letters, no watermark, no t-shirt, no mockup',768,1024),
 'coloring':(', black and white colouring book page for children, thick clean black outlines, no shading, no grey, no colour fill, simple large shapes, plain white background, no text',768,1024),
 'art':(', high quality illustration, no text, no watermark',1024,768)}
KIND_HU={'apparel':'ruhagrafika','coloring':'színező','art':'grafika'}
# Print-on-demand shops take down designs that use brands or characters someone owns; ORBIT does not render them.
PROTECTED=re.compile(r'disney|marvel|pixar|pok[eé]mon|pikachu|nintendo|super mario|zelda|star ?wars|harry potter|hogwarts|mickey|minnie|spider-?man|batman|superman|barbie|hello kitty|peppa|paw patrol|bluey|frozen|minecraft|fortnite|roblox|lego|nike|adidas|coca-?cola|ferrari|lamborghini|\bnfl\b|\bnba\b|fifa',re.I)

def spec(product):
 """The builder's design list [{id, title, kind, prompt}], cleaned and capped."""
 try:data=json.loads((Path(product)/'designs.json').read_text())
 except (OSError,ValueError):return []
 items=data.get('designs') if isinstance(data,dict) else data
 out=[];seen=set()
 for d in items if isinstance(items,list) else []:
  if not isinstance(d,dict):continue
  i=re.sub(r'[^a-z0-9-]','',str(d.get('id') or '').lower().replace(' ','-'))[:40]
  prompt=str(d.get('prompt') or '').strip()
  if not i or i in seen or len(prompt)<10:continue
  seen.add(i);out.append(dict(id=i,title=str(d.get('title') or i)[:120],kind=d.get('kind') if d.get('kind') in KINDS else 'art',prompt=prompt[:900]))
 return out[:MAX]

def key(d):return hashlib.sha1((d['kind']+'|'+d['prompt']).encode()).hexdigest()[:12]

def state(product):
 try:return json.loads((Path(product)/'designs'/'render.json').read_text())
 except (OSError,ValueError):return {}

def save_state(product,st):
 path=Path(product)/'designs'/'render.json';path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(st,ensure_ascii=False,indent=1));tmp.replace(path)

def pending(product):
 """Designs still to render: new or changed prompts, and failures not yet retried."""
 st=state(product);out=[]
 for d in spec(product):
  e=st.get(d['id']) or {}
  if e.get('key')!=key(d) or not e.get('done') and e.get('tries',0)<TRIES:out.append(d)
 return out

def post(s,args):
 """design_post.py in ORBIT's image runtime, which has Pillow."""
 return subprocess.run([str(s.root/'image-runtime/bin/python'),str(Path(__file__).with_name('design_post.py'))]+[str(a) for a in args],capture_output=True,text=True,timeout=300)

def flux(s,prompt,w,h,seed,output,init=None,strength=None,steps=4):
 from model_hub import status,unload
 info=status()
 if not info['flux_ready']:raise ValueError('A FLUX képmodell nincs kész, vagy az SSD nincs csatlakoztatva.')
 # The local chat model leaves the memory to FLUX (~8 GB); the Autopilot reloads it in ~3 s.
 unload()
 cmd=[str(s.root/'image-runtime/bin/mflux-generate'),'--model',info['flux_path'],'--base-model','schnell','--prompt',prompt,'--steps',str(steps),'--width',str(w),'--height',str(h),'--seed',str(seed),'--low-ram','--output',str(output)]
 if init:cmd+=['--image-path',str(init),'--image-strength',str(strength if strength is not None else .4)]
 env=dict(os.environ,HF_HUB_OFFLINE='1',HF_HOME=str(Path(info['config']['base'])/'huggingface-cache'),MPLCONFIGDIR=str(s.root/'logs/matplotlib'))
 r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=900)
 if r.returncode or not Path(output).is_file():raise ValueError('A képgenerálás nem sikerült: '+(r.stderr or r.stdout or '')[-300:])

def render(s,product,d,pid='orbit-business-lab'):
 """Render one design into designs/<id>.png and register it as a creation of the business lab."""
 product=Path(product);out=product/'designs';(out/'thumbs').mkdir(parents=True,exist_ok=True)
 st=state(product);old=st.get(d['id']) or {}
 entry=dict(key=key(d),title=d['title'],kind=d['kind'],at=time.time(),done=False,tries=(old.get('tries',0) if old.get('key')==key(d) else 0)+1)
 if PROTECTED.search(d['prompt']+' '+d['title']):
  entry.update(error='Védett márka vagy karakter szerepel benne; a POD-oldalak törlik az ilyet, ezért nem készült el.',tries=TRIES)
 else:
  suffix,w,h=KINDS[d['kind']];raw=out/(d['id']+'.raw.png');final=out/(d['id']+'.png')
  try:
   flux(s,d['prompt']+suffix,w,h,int(key(d),16)%100000,raw)
   r=post(s,[d['kind'],raw,final,out/'thumbs'/(d['id']+'.jpg')])
   if r.returncode:raise ValueError('Az utófeldolgozás nem sikerült: '+(r.stderr or '')[-300:])
   entry.update(done=True,error='')
   s.db.execute('DELETE FROM artifacts WHERE project=? AND path=?',(pid,str(final)))
   s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,d['title']+'.png',str(final),'image',time.time(),'design'));s.db.commit()
  except (ValueError,OSError,subprocess.SubprocessError) as exc:entry.update(error=str(exc)[:400])
  finally:raw.unlink(missing_ok=True)
 st[d['id']]=entry;save_state(product,st)
 book(s,product)
 return entry

def book(s,product):
 """All colouring pages done: bind them into one printable PDF (rebuilt when a page changes)."""
 product=Path(product);st=state(product)
 pages=[d for d in spec(product) if d['kind']=='coloring']
 if not pages or not all((st.get(d['id']) or {}).get('done') and (st.get(d['id']) or {}).get('key')==key(d) for d in pages):return None
 pdf=product/'designs'/'coloring-book.pdf';files=[product/'designs'/(d['id']+'.png') for d in pages]
 if pdf.is_file() and pdf.stat().st_mtime>=max(f.stat().st_mtime for f in files):return pdf
 r=post(s,['book',pdf]+files)
 return pdf if r.returncode==0 else None

def summary(s,product,pid='orbit-business-lab'):
 """For the Autopilot page: every design with its state and a link to the rendered image."""
 product=Path(product);items=spec(product)
 if not items:return None
 st=state(product);arts={r['path']:r['id'] for r in s.rows('SELECT id,path FROM artifacts WHERE project=? AND job=?',(pid,'design'))}
 out=[]
 for d in items:
  e=st.get(d['id']) or {};fresh=e.get('key')==key(d)
  out.append(dict(id=d['id'],title=d['title'],kind=KIND_HU[d['kind']],done=bool(fresh and e.get('done')),error=e.get('error','') if fresh else '',
   artifact=arts.get(str(product/'designs'/(d['id']+'.png'))) if fresh and e.get('done') else None))
 return dict(items=out,done=sum(x['done'] for x in out),total=len(out),failed=sum(bool(x['error']) and not x['done'] for x in out),book=(product/'designs'/'coloring-book.pdf').is_file())

def busy(s):
 """The Autopilot or the assistant is using the model; rendering would make it wait or defer it.
 A chat request still waiting counts too: it waits for the model this lane holds, and checking only
 running jobs let one design follow another for many minutes while the owner's question sat queued."""
 from inference_gate import interactive_pending
 if interactive_pending(s.root):return True
 return bool(s.db.execute("SELECT 1 FROM jobs WHERE (status='running' AND kind IN ('mission_agent','command','command_apply','chat','media_analysis','model_evaluation')) OR (status='queued' AND kind IN ('command_apply','chat')) LIMIT 1").fetchone())

def work(s):
 """Render at most one design of any business-lab product; None when there is nothing to do or no room."""
 from inference_gate import lease
 from execution_queue import DeferredExecution
 if busy(s):return None
 try:root=s.safe_path('orbit-business-lab','workspace')
 except (OSError,ValueError):return None
 for designs in sorted(root.glob('product-*/designs.json')):
  todo=pending(designs.parent)
  if not todo:continue
  try:
   with lease(s.root):return render(s,designs.parent,todo[0])
  except DeferredExecution:return None
 return None
