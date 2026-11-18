"""Fill evidence gaps for the proposed real shots, with a bounded, checkpointed budget."""
import math

def missing_samples(catalog,choice,candidates=()):
 chosen=choice if isinstance(choice,dict) else candidates[0] if candidates else {}
 ids=[chosen.get('hook')]+(chosen.get('sequence') if isinstance(chosen.get('sequence'),list) else [])
 groups={}
 for uid in dict.fromkeys(i for i in ids if type(i) is int and 0<=i<len(catalog)):
  unit=catalog[uid]
  if unit.get('visual_samples'):continue
  t=round((unit['start']+unit['end'])/2,3)
  if math.isfinite(t):groups.setdefault(unit['source'],[]).append(t)
 return {index:sorted(set(times))[:12] for index,times in groups.items()}

def enrich(s,agent,job,data,tracks,catalog,choice,candidates=()):
 from execution_queue import DeferredExecution
 if data.get('evidence_enrichment_attempted') or not data['style'].get('visual_analysis',True):return False
 samples=missing_samples(catalog,choice,candidates)
 if not samples:return False
 data['evidence_enrichment_attempted']=True
 while len(data.setdefault('visual_analysis',[]))<len(tracks):data['visual_analysis'].append({})
 changed=False
 for index,times in samples.items():
  s.job_stage(job['id'],'evidence_gap','Hiányzó snittbizonyíték ellenőrzése · '+str(len(times))+' képkocka')
  try:
   actual=s.tool(agent,'analyze_video',dict(name=tracks[index]['source']['source_video'],timestamps=times,analysis_mode='focus'),job['id'])['summary']
   old=data['visual_analysis'][index];old=old if isinstance(old,dict) else {}
   frames={float(f['seconds']):f for f in old.get('frames',[]) if isinstance(f,dict) and type(f.get('seconds')) in (int,float)}
   before=len(frames)
   for frame in actual.get('frames',[]):
    if isinstance(frame,dict) and type(frame.get('seconds')) in (int,float) and frame.get('action') and any(abs(frame['seconds']-t)<.1 for t in times):frames[float(frame['seconds'])]=frame
   old['frames']=[frames[t] for t in sorted(frames)];data['visual_analysis'][index]=old;changed=changed or len(frames)>before
  except DeferredExecution:
   data.pop('evidence_enrichment_attempted',None);raise
  except Exception as exc:
   if s.cancelled(job['id']):raise
   s.job_stage(job['id'],'evidence_unavailable','A hiányzó képi bizonyíték nem volt pótolható',str(exc)[:300])
 return changed
