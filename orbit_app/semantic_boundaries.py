"""Local text embeddings flag likely topic changes alongside measured cuts or pauses."""
import hashlib,json,math,re
STOP=set('a an the and or but so of to in on at for with from as is are was were be been it its this that these those i me my myself you your he him his she her we us our they them their do did does dont not no yes oh ah god wait where why what who how let back know went wins would could should will just now then really yeah okay yep course'.split())
def cosine(a,b):
 if not a or len(a)!=len(b):return None
 norm=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b));return sum(x*y for x,y in zip(a,b))/norm if norm else None

def apply(catalog,observations,vectors):
 for i,u in enumerate(catalog):
  if not i or catalog[i-1]['source']!=u['source'] or u.get('boundary')=='visual_sample':continue
  prior=catalog[i-1];gap=u['start']-prior['end'];similarity=cosine(vectors[i-1],vectors[i])
  if similarity is None:continue
  obs=observations[u['source']] if u['source']<len(observations) else {}
  cut=any(prior['end']-.2<=s.get('start',-100)<=u['start']+.5 for s in obs.get('scene_map',{}).get('scenes',[]))
  content=lambda text:{t for t in re.findall(r'[a-z]+',text.casefold()) if len(t)>2 and t not in STOP}
  novel=len(content(u['text'])-content(prior['text']))
  u['semantic_link']=dict(similarity=round(similarity,3),new_content_terms=novel,source_cut=bool(cut),gap=round(gap,3))
  # This is a conservative event-boundary hint, not semantic ground truth.
  if similarity<.45 and novel>=3 and (cut or gap>=.8):u['event_break']=True
 return catalog

def enrich(s,job,data,catalog):
 key=hashlib.sha256(json.dumps(dict(version=2,units=[(u['source'],u['start'],u['end'],u['text']) for u in catalog]),sort_keys=True).encode()).hexdigest();saved=data.get('semantic_boundaries',{})
 if saved.get('fingerprint')==key:
  for unit,fields in zip(catalog,saved['units']):unit.update({k:v for k,v in fields.items() if k=='event_break'})
  return
 if not catalog or all(u.get('boundary')=='visual_sample' for u in catalog):return
 from execution_queue import DeferredExecution
 try:
  from model_hub import models,request
  model=next((m['name'] for m in models() if 'embedding' in m['name'] or 'embed' in m['name']),None)
  if not model:return
  from inference_gate import lease
  s.job_stage(job['id'],'semantic_boundaries','Témaváltások ellenőrzése · helyi jelentéselemzés')
  with lease(s.root):result=request('api/embed',dict(model=model,input=[u['text'][:700] for u in catalog],dimensions=256,keep_alive=0),timeout=90)
  vectors=result.get('embeddings',[])
  if len(vectors)!=len(catalog) or any(not isinstance(v,list) or any(type(x) not in (float,int) or not math.isfinite(x) for x in v) for v in vectors):return
  apply(catalog,data.get('visual_analysis',[]),vectors)
  data['semantic_boundaries']=dict(fingerprint=key,model=model,units=[{k:u[k] for k in ('semantic_link','event_break') if k in u} for u in catalog])
  for unit in catalog:unit.pop('semantic_link',None)
 except DeferredExecution:raise
 except (ValueError,OSError,TypeError):return
