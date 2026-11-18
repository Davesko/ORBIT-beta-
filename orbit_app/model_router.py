"""One capability-aware, quality-first policy for the supervisor and every agent."""
import json,re,unicodedata
from pathlib import Path
CATALOG={
 'qwen3.8:27b':dict(chat=98,code=98,vision=98),
 'qwen3.8:27b-q4_K_M':dict(chat=98,code=98,vision=98,interactive=75),
 'qwen3-coder:30b':dict(chat=87,code=96),
 'gemma4:31b':dict(chat=95,code=90,vision=95),
 'gemma4:26b':dict(chat=93,code=88,vision=93,interactive=90),
 'gemma4:12b':dict(chat=85,code=80,vision=85),
 'qwen3.5:27b':dict(chat=94,code=91,vision=94),
 'qwen3-vl:8b':dict(chat=76,code=65,vision=83),
 'qwen3-vl:8b-instruct':dict(chat=76,code=65,vision=83),
 'qwen3.5:9b':dict(chat=83,code=77,vision=85,utility=98,interactive=100),
 'qwen3.5:4b':dict(chat=72,code=65,vision=75,utility=91,interactive=94),
 'qwen2.5:14b':dict(chat=70,code=55,utility=75),
 'qwen2.5-coder:14b':dict(chat=60,code=74,utility=70),
 'qwen2.5vl:7b':dict(chat=55,code=45,vision=68,utility=65),
 'gemma3:12b':dict(chat=62,code=45,vision=65,utility=60),
}
def normalized(text):return ''.join(c for c in unicodedata.normalize('NFKD',str(text).lower()) if not unicodedata.combining(c))
def task_type(prompt,image=False):
 p=normalized(prompt)
 info=bool(re.search(r'\b(hogyan|milyen|lehet-e|how to|can i|what is)\b',p))
 verbs=r'\b(general\w*|keszit\w*|hozz letre|rajzolj|alkoss|csinalj|kreal\w*|kernek|szeretnek|indits\w*|start|generate|create|draw|make|render)\b'
 create=any(not re.search(r"\b(ne|nem|not|do not|don.t)\s+(?:\w+\s+){0,2}$",p[max(0,m.start()-35):m.start()]) for m in re.finditer(verbs,p)) and not info
 # "képes" (capable) is not "kép" (image); do not divert video briefs to FLUX.
 if create and re.search(r'\b(kep(?:et|ek|eket|bol|eket|generalas\w*)?|foto\w*|rajzot|illusztracio\w*|image|picture|photo|portrait|logo|poszter|plakat|wallpaper|konceptkep\w*|koncepcio\w*kep\w*|imgae)\b',p):return 'image'
 if create and re.search(r'\b(video\w*|shorts?|klip\w*|clip)\b',p):return 'video'
 if image:return 'vision'
 if re.search(r'\b(kod|kodot|kodolas\w*|kodol\w*|fejlesz\w*|automatiz\w*|programoz\w*|alkalmazas\w*|appot|epits|website|debug|bug|script|python|javascript|typescript|swift|api|html|css|sql)\b',p):return 'code'
 return 'chat'
def reports(root=None):
 try:return json.loads((Path(root or Path.home()/'Library/Application Support/Orbit')/'model-quality.json').read_text()).get('models',{})
 except (OSError,ValueError):return {}
def usable(available,image=False):
 """An embedding service being online does not mean a chat model is available."""
 result=[]
 for m in available:
  m=dict(name=m) if isinstance(m,str) else m
  name=m.get('name','');caps=m.get('capabilities',[]);profile=CATALOG.get(name,{})
  if any(x in name.lower() for x in ('embedding','embed','rerank','cloud')):continue
  if not profile and 'completion' not in caps:continue
  if image and 'vision' not in profile and 'vision' not in caps:continue
  result.append(m)
 return result
def choose(prompt,available,requested='auto',image=False,purpose=None,quality=None):
 task=task_type(prompt,image);cap='vision' if image or task=='vision' else 'code' if task=='code' else 'chat'
 purpose=purpose or cap;quality=reports() if quality is None else quality
 entries=[dict(name=m) if isinstance(m,str) else m for m in available]
 entries=[m for m in entries if not any(x in m['name'].lower() for x in ('embedding','embed','rerank','cloud'))]
 auto=requested in ('','auto',None) or image or task in ('image','video')
 if not auto:
  if not any(m['name']==requested for m in entries):raise ValueError('A kiválasztott modell nem érhető el.')
  selected=requested;calibrated=False
 else:
  candidates=[]
  for entry in entries:
   name=entry['name'];profile=CATALOG.get(name,{})
   capabilities=entry.get('capabilities',[])
   if cap=='vision' and 'vision' not in profile and 'vision' not in capabilities:continue
   if not profile and 'completion' not in capabilities:continue
   score=profile.get(purpose,profile.get(cap,50)-(15 if purpose=='utility' else 0));evaluation=quality.get(name,{}).get(purpose,quality.get(name,{}).get(cap,{}))
   if evaluation.get('total',0)>=5:
    ratio=evaluation.get('passed',0)/evaluation['total'];score=score+min(5,ratio*5) if ratio==1 else score-60*(1-ratio)
    latency=evaluation.get('seconds')
    # The owner waits for the planner: there its speed weighs more than in background work.
    if type(latency) in (int,float) and latency>0:score-=min(12,latency/10) if purpose=='planner' else min(5,latency/20)
   candidates.append((score,name,bool(evaluation.get('total',0)>=5)))
  if not candidates:
   # The models on a hung SSD are not missing: say what the owner can actually do (2026-11-01).
   import model_hub
   if model_hub.ssd_hung():raise ValueError(model_hub.HUNG_MESSAGE)
   raise ValueError('Nincs megfelelő helyi képi modell.' if cap=='vision' else 'Nincs elérhető helyi beszélgetőmodell. Ellenőrizd a Modellek oldalt.')
  _,selected,calibrated=max(candidates,key=lambda x:(x[0],x[1]))
 best=next((n for n,v in sorted(CATALOG.items(),key=lambda x:x[1].get(cap,0),reverse=True) if cap in v),None)
 return dict(task=task,model=selected,engine='FLUX.1 Schnell' if task=='image' else selected,automatic=auto,fallback=selected!=best,calibrated=calibrated,policy='interactive' if auto and purpose=='interactive' else 'quality',reason='Saját feladatpróbákkal ellenőrzött választás' if calibrated else 'Rövid beszélgetéshez ajánlott gyors helyi modell' if auto and purpose=='interactive' else 'Képesség és minőség szerint ajánlott helyi modell')
