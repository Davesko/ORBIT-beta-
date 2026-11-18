"""Project-scoped, evidence-only Shorts feedback. No invented retention or causal claims."""
import json,math,re,subprocess,time
from pathlib import Path

def number(value):
 try:
  n=float(value)
  return n if math.isfinite(n) and n>=0 else None
 except (ValueError,TypeError):return None

def recommendation(videos):
 eligible=[v for v in videos if v.get('status')=='processed' and 24<=v.get('age_hours',0)<=72 and (number(v.get('engaged_views')) or 0)>=100 and number(v.get('average_view_percentage')) is not None]
 result=dict(status='collecting',sample_size=len(eligible),change=None,reason='Még nincs legalább 3, 24–72 órás videó elegendő nézési adattal. Nem következtetünk néhány megtekintésből.',instruction='Keep the current format. Select the best grounded story; do not infer success from raw view counts.')
 if len(eligible)<3:
  # Not enough fresh, comparable videos for a controlled test: use what older uploads show.
  learned=lessons(videos)
  if learned:return dict(status='learned',sample_size=max(l['sample'] for l in learned),change=None,lessons=learned,
   reason='A csatorna eddigi videóiból: '+' '.join(l['text'] for l in learned),instruction=' '.join(l['instruction'] for l in learned)+' These are channel observations, not guarantees; never sacrifice the story or truth for them.')
  return result
 # Compare only similar lengths and the same requested topic; raw reach is not hook quality.
 newest=max(eligible,key=lambda v:v.get('published_at',''))
 peers=[v for v in eligible if v.get('topic')==newest.get('topic') and v.get('topic') and (number(newest.get('duration')) or 0)>0 and .75<=((number(v.get('duration')) or 0)/float(newest['duration']))<=1.33]
 if len(peers)<3:return dict(result,reason='Van nézési adat, de még nincs három összehasonlítható témájú és hosszúságú videó.')
 avg=sum(float(v['average_view_percentage']) for v in peers)/len(peers)
 best=max(peers,key=lambda v:float(v['average_view_percentage']))
 if float(best['average_view_percentage'])>=avg+10 and best.get('editorial',{}).get('humor_type') not in (None,'none'):
  return dict(status='exploratory_test',sample_size=len(peers),change='hook_mechanism',reason='A hasonló videók közül az egyik lényegesen magasabb megtekintett arányt ért el. A következő teszt ennek hook-felépítését vizsgálja; az összefüggés még nem bizonyít ok-okozatot.',best_video=best['id'],evidence_ids=[v['id'] for v in peers],instruction='Test ONLY the successful hook mechanism as a hypothesis, where supported by the new source. Do not copy unrelated quotes or invent a joke. Keep caption style and other settings stable.',reference_editorial=best['editorial'])
 return dict(status='exploratory_test',sample_size=len(peers),change='setup_density' if avg<60 else None,reason=('A hasonló videók átlagos megtekintett aránya %.1f%%. '%avg)+('Következő teszt: rövidebb magyarázó felvezetés; a poénhoz szükséges információ maradjon.' if avg<60 else 'Nincs elegendő bizonyíték irányváltáshoz; a jelenlegi felépítés marad.'),instruction='Test only a more concise setup, preserving the joke and real payoff. Keep other style choices stable. This is a hypothesis, not proof of improvement.' if avg<60 else result['instruction'],evidence_ids=[v['id'] for v in peers],average_view_percentage=round(avg,2))

BANDS=dict(
 duration=(lambda v:number(v.get('duration')),[(0,30,'30 mp alatti'),(30,46,'30–45 mp-es'),(46,61,'46–60 mp-es'),(61,1e9,'60 mp feletti')],'Keep the Short {label} long (about {lo:.0f}-{hi:.0f} s) when the story allows; that length held viewers best.'),
 hook=(lambda v:number((v.get('edit_traits') or {}).get('hook_seconds')),[(0,5,'5 mp alatti nyitású'),(5,10.01,'5–10 mp-es nyitású'),(10.01,1e9,'10 mp feletti nyitású')],'Make the opening hook {label} ({lo:.0f}-{hi:.0f} s before the story starts).'))
CATEGORIES=dict(humor=(lambda v:(v.get('editorial') or {}).get('humor_type'),'Prefer {value} humor/moments when the source offers them.'),
 captions=(lambda v:(v.get('edit_traits') or {}).get('caption_theme'),'Use the {value} caption theme.'))

def lessons(videos):
 """What measurably held viewers longer on this channel: trait groups compared by average view
 percentage. Needs at least two videos on each side and an 8-point gap; no causal claim."""
 data=[v for v in videos if v.get('status')=='processed' and (number(v.get('age_hours')) or 0)>=24 and (number(v.get('views')) or 0)>=20 and number(v.get('average_view_percentage')) is not None]
 out=[]
 def compare(name,groups,make):
  groups={k:g for k,g in groups.items() if len(g)>=2}
  if len(groups)<2:return
  avg={k:sum(float(v['average_view_percentage']) for v in g)/len(g) for k,g in groups.items()}
  best=max(avg,key=avg.get);worst=min(avg,key=avg.get)
  if avg[best]-avg[worst]<8:return
  out.append(dict(trait=name,best=best,best_avg=round(avg[best],1),worst=worst,worst_avg=round(avg[worst],1),sample=sum(len(g) for g in groups.values()),**make(best)))
 for name,(get,bands,template) in BANDS.items():
  groups={}
  for v in data:
   x=get(v)
   if x is None:continue
   lo,hi,label=next(b for b in bands if b[0]<=x<b[1]);groups.setdefault(label,[]).append(v)
  bounds={label:(lo,min(hi,120)) for lo,hi,label in bands}
  compare(name,groups,lambda best:dict(instruction=template.format(label=best.split(' ')[0],lo=bounds[best][0],hi=bounds[best][1])))
 for name,(get,template) in CATEGORIES.items():
  groups={}
  for v in data:
   x=get(v)
   if x:groups.setdefault(str(x),[]).append(v)
  compare(name,groups,lambda best:dict(instruction=template.format(value=best)))
 for l in out:l['text']=l['best']+(' videók' if l['trait'] in ('duration','hook') else ' ('+l['trait']+')')+': átlag '+str(l['best_avg'])+'% megnézve, szemben a(z) '+l['worst']+' '+str(l['worst_avg'])+'%-ával ('+str(l['sample'])+' videó).'
 return out

def read(root,pid):
 try:return json.loads((Path(root)/'integrations/youtube'/pid/'feedback.json').read_text())
 except (OSError,ValueError):return dict(status='not_collected',videos=[],recommendation=recommendation([]))

def refresh(studio,pid,force=False):
 base=studio.root/'integrations/youtube'/pid
 if not (base/'status.json').exists():return read(studio.root,pid)
 cached=read(studio.root,pid)
 if not force and time.time()-cached.get('collected_at',0)<3600:return cached
 records=[]
 for f in sorted(base.glob('receipt-*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
  try:
   receipt=json.loads(f.read_text());vid=receipt.get('id','')
   if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):continue
   job=studio.db.execute("SELECT payload FROM jobs WHERE id=? AND project=? AND status='done'",(receipt.get('job'),pid)).fetchone()
   if not job:continue
   payload=json.loads(job['payload']);run=studio.db.execute('SELECT query,data FROM short_runs WHERE id=? AND project=?',(payload.get('run'),pid)).fetchone()
   data=json.loads(run['data']) if run else {}
   if vid not in [r['id'] for r in records]:records.append(dict(id=vid,topic=run['query'] if run else '',duration=data.get('render',{}).get('metadata',{}).get('duration'),editorial=data.get('montage',{}).get('editorial_review',{}),experiment=data.get('experiment') or {},edit_traits=__import__('editing_experiments').traits(data)))
  except (OSError,ValueError,KeyError):continue
  if len(records)>=50:break
 request=dict(videos=records)
 try:
  p=subprocess.run([str(studio.root/'media-runtime/bin/python'),str(Path(__file__).with_name('youtube_runtime.py')),'metrics',str(studio.root),pid],input=json.dumps(request),capture_output=True,text=True,timeout=120)
  result=json.loads(p.stdout)
  if not result.get('ok'):raise ValueError('YouTube-mérés nem elérhető; az előző igazolt adatok maradnak.')
  result.update(collected_at=time.time());result['recommendation']=recommendation(result['videos'])
  from youtube_runtime import atomic_json
  atomic_json(base/'feedback.json',result)
  history=base/'feedback-history';history.mkdir(exist_ok=True)
  atomic_json(history/(time.strftime('%Y%m%d-%H')+'.json'),result)
  return result
 except (OSError,ValueError,subprocess.TimeoutExpired):
  return dict(cached,collection_error='A mérés most nem elérhető. A gyártás folytatható, bizonyíték nélküli optimalizálás nélkül.')

def poll_all():
 from studio import Studio
 s=Studio()
 try:
  for path in (s.root/'integrations/youtube').glob('*/status.json'):
   try:refresh(s,path.parent.name)
   except Exception:continue
 finally:s.db.close()
