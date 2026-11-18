"""Inspect exact production evidence and create non-destructive partial revisions."""
import copy,json,time,uuid
from pathlib import Path

def locate(s,pid,artifact):
 row=s.db.execute("SELECT * FROM artifacts WHERE project=? AND id=? AND kind='video'",(pid,artifact)).fetchone()
 if not row:raise ValueError('Ismeretlen projektvideó.')
 job=s.db.execute('SELECT payload FROM jobs WHERE project=? AND id=?',(pid,row['job'])).fetchone();run=json.loads(job['payload']).get('run') if job else None
 saved=s.db.execute('SELECT * FROM short_runs WHERE id=? AND project=?',(run,pid)).fetchone() if run else None
 return dict(row),dict(saved) if saved else None

def detail(s,pid,artifact):
 from editing_memory import read
 item,run=locate(s,pid,artifact);data=json.loads(run['data']) if run else {};montage=data.get('montage',{});timeline=[];cursor=0
 storyboard=montage.get('storyboard',[])
 for i,shot in enumerate(montage.get('shots',[])):
  b=storyboard[i] if i<len(storyboard) else {};end=cursor+shot['end']-shot['start']
  timeline.append(dict(index=i,phase=b.get('phase',shot.get('beat','context')),start=round(cursor,3),end=round(end,3),text=b.get('evidence',shot.get('reason','')),reason=b.get('purpose',shot.get('reason','')),source=shot['source'],source_start=shot['start'],source_end=shot['end']));cursor=end
 active=s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND status IN ('queued','running') AND json_extract(payload,'$.auto_step') IS NOT NULL",(pid,)).fetchone()[0]
 try:explained=why(s,pid,data,montage,timeline)
 except Exception:explained={}  # Explanations are optional; review and revision must stay available.
 return dict(artifact=artifact,run=run['id'] if run else None,topic=run['query'] if run else item['name'],timeline=timeline,outline=montage.get('outline',{}),director=data.get('director',{}),pacing=data.get('pacing',{}),feedback=read(s,pid,artifact),can_revise=bool(run and data.get('complete') and not active),active=bool(active),revision=data.get('revision'),experiment=data.get('experiment'),why=explained)

OMIT_REASON={'aside':'Mellékszál, nem változtat a lényegen','context':'A kontextus egy része, rövidebb változat is elég','development':'Kibontás, a hossz miatt kimaradt','outcome':'Eredmény ismétlése'}

def why(s,pid,data,montage,timeline):
 """Explain an existing cut from saved evidence only: lengths, core message, hook cues, omissions."""
 tracks=data.get('tracks',[])
 for track in tracks:
  if 'transcript' not in track and track.get('transcript_file'):
   try:track['transcript']=json.loads(s.safe_path(pid,track['transcript_file']).read_text())
   except (OSError,ValueError):track['transcript']={}
 source_seconds=sum(float(t.get('source',{}).get('duration') or 0) for t in tracks)
 output_seconds=round(sum(b['end']-b['start'] for b in timeline),1)
 overview=data.get('content_overview') or {}
 summary=montage.get('content_summary') or {}
 result=dict(sources=len(tracks),source_seconds=round(source_seconds,1),output_seconds=output_seconds,
  main_context=overview.get('main_context') or montage.get('outline',{}).get('context',''),core_message=overview.get('core_message') or montage.get('outline',{}).get('payoff',''),
  omission_policy=summary.get('omission_policy') or overview.get('omission_policy',''),analyzed_units=summary.get('analyzed_units'),omitted_units=summary.get('omitted_units'),omitted=[],hook_cues=[])
 if timeline and tracks:
  from editorial import hook_signals
  first=timeline[0];track=tracks[first['source']] if first['source']<len(tracks) else tracks[0]
  score,cues=hook_signals(dict(start=first['source_start'],end=first['source_end'],text=first['text'] or ''),track.get('transcript') or {})
  result.update(hook_score=score,hook_cues=cues)
 selected=set(summary.get('selected_global_ids') or [])
 ranks={r['id']:r for b in (data.get('content_survey') or {}).get('batches',[]) for r in b.get('rankings',[])}
 if selected and ranks and tracks:
  from editorial import unit_catalog
  catalog=unit_catalog(tracks,data.get('requested_style') or data['style'],data.get('visual_analysis',[]),full=True)
  left=[(ranks[u['id']]['importance'],u) for u in catalog if u['id'] not in selected and u['id'] in ranks and u.get('boundary')!='visual_sample']
  for importance,u in sorted(left,key=lambda x:(x[0],x[1]['start']))[:4]:
   role=ranks[u['id']]['role'];reason='Ismétlődő vagy kevésbé fontos rész' if importance<=1 else OMIT_REASON.get(role,'A hossz miatt kimaradt')
   result['omitted'].append(dict(at=round(u['start'],1),text=u['text'][:140],reason=reason,importance=importance))
 return result

def revise(s,pid,artifact,kind,request_id):
 from autonomous import role_agents,STEPS,plan_schema
 from execution_queue import DeferredExecution
 if kind not in ('story','hook','framing','captions'):raise ValueError('Ismeretlen javítási cél.')
 if not isinstance(request_id,str) or not 8<=len(request_id)<=100:raise ValueError('Hiányzó javításazonosító.')
 plan_schema(s);origin='revision:'+request_id
 existing=s.db.execute("SELECT id FROM short_runs WHERE project=? AND json_extract(data,'$.origin')=?",(pid,origin)).fetchone()
 if existing:return dict(run=existing['id'],existing=True)
 _,parent=locate(s,pid,artifact)
 if not parent:raise ValueError('Ehhez a videóhoz nem maradt meg a gyártási terv.')
 data=json.loads(parent['data'])
 if not data.get('complete'):raise ValueError('Csak befejezett videó javítható.')
 for track in data.get('tracks',[]):
  for name in (track['source']['source_video'],track['transcript_file']):
   if not s.safe_path(pid,name).is_file():raise ValueError('A javításhoz hiányzik egy mentett forrás.')
 roles=role_agents(s,pid);stages=['selection','layout','render','metadata','verify'] if kind in ('story','hook') else ['layout','render','verify'] if kind=='framing' else ['render','verify']
 data=copy.deepcopy(data);data.update(origin=origin,automatic=False,revision=dict(parent_run=parent['id'],parent_artifact=artifact,kind=kind,created=time.time()))
 if kind=='hook':data['revision']['fixed_body']=copy.deepcopy(data['montage']['shots'][1:]);data['revision']['old_hook']=copy.deepcopy(data['montage']['shots'][0])
 for key in ('complete','render','youtube','publication_review','assembly_plan'):data.pop(key,None)
 if kind in ('story','hook'):
  for key in ('selection_checkpoint','montage','camera_plan','director','pacing'):data.pop(key,None)
 data['style'].update(publish_to_youtube=False,review_before_upload=True)
 s.db.execute('BEGIN IMMEDIATE')
 try:
  existing=s.db.execute("SELECT id FROM short_runs WHERE project=? AND json_extract(data,'$.origin')=?",(pid,origin)).fetchone()
  if existing:s.db.rollback();return dict(run=existing['id'],existing=True)
  if s.db.execute("SELECT 1 FROM jobs WHERE project=? AND status IN ('queued','running') AND json_extract(payload,'$.auto_step') IS NOT NULL",(pid,)).fetchone():raise ValueError('A projektben még folyamatban van egy videó. A visszajelzésed elmentve; a javítás utána indítható.')
  run=uuid.uuid4().hex;s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',(run,pid,parent['query'],json.dumps(data),time.time()));jobs={};previous=None
  for stage in stages:
   jid=s.enqueue(roles[stage],'Videójavítás · '+dict(STEPS)[stage],'graph',dependency=previous,payload=dict(run=run,auto_step=stage),commit=False);jobs[stage]=jid;previous=jid
  s.db.commit();return dict(run=run,jobs=jobs,existing=False)
 except Exception:s.db.rollback();raise

def fixed_hook_choice(choice,catalog,revision):
 """A hook-only request cannot silently replace the rest of the video."""
 if not revision or revision.get('kind')!='hook':return choice
 ids=[]
 for shot in revision['fixed_body']:
  hits=[u['id'] for u in catalog if u['source']==shot['source'] and abs(u['start']-shot['start'])<.05 and abs(u['end']-shot['end'])<.05]
  if not hits:raise ValueError('A megtartandó jelenetsor nem illeszthető az új katalógushoz.')
  ids.append(hits[0])
 hook=choice.get('hook')
 if hook in ids:raise ValueError('A hook nem ismételheti meg a változatlan középrészt.')
 old=revision['old_hook']
 if type(hook) is int and 0<=hook<len(catalog):
  u=catalog[hook]
  if u['source']==old['source'] and abs(u['start']-old['start'])<.05:raise ValueError('Új, a korábbitól eltérő nyitást válassz.')
 return dict(choice,sequence=ids,fixed_sequence=True)
