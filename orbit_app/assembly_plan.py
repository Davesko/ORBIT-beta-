"""Human-readable evidence accompanies the exact deterministic renderer request."""
import math

def build(data,request,transcripts):
 tracks=data.get('tracks',[]);shots=data.get('edit_shots',data.get('montage',{}).get('shots',[]));segments=request.get('segments',[])
 if not shots or len(shots)!=len(segments):raise ValueError('A vágási terv és a render szegmensei eltérnek.')
 timeline=[];cursor=0
 for i,(shot,segment) in enumerate(zip(shots,segments)):
  source=shot['source']
  if type(source) is not int or not 0<=source<len(tracks):raise ValueError('Ismeretlen forrás a vágási tervben.')
  track=tracks[source];start=shot['start'];end=shot['end'];duration=end-start
  if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,end,duration)) or not 0<=start<end<=track['source']['duration']+.05:raise ValueError('Érvénytelen forrásidő a vágási tervben.')
  if segment['source_video']!=track['source']['source_video'] or abs(segment['start']-start)>.001 or abs(segment['duration']-duration)>.002:raise ValueError('A render eltér az ellenőrzött vágási tervtől.')
  speech=[dict(start=x['start'],end=x['end'],text=x.get('text','')) for x in transcripts[source].get('segments',[]) if x['end']>start and x['start']<end]
  timeline.append(dict(index=i,output_start=round(cursor,3),output_end=round(cursor+duration,3),source_index=source,source_url=track['source'].get('metadata',{}).get('url'),source_video=segment['source_video'],source_start=start,source_end=end,beat=shot.get('beat','context'),reason=shot.get('reason',''),speech=speech,render=segment))
  cursor+=duration
 if abs(cursor-request['duration'])>.05:raise ValueError('A teljes renderhossz eltér a történeti tervtől.')
 return dict(version=2,contract='orbit.edit.v1',story=request.get('story',{}),topic=(data.get('source_bundle') or {}).get('topic') or data.get('query'),duration=round(cursor,3),caption_theme=request.get('caption_theme','clean'),timeline=timeline,request=request)
