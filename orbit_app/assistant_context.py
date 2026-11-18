"""Live, bounded app facts and typed read contracts for every supervisor planning slice.
Private credentials are never context. Large objects remain available through scoped reads.
"""
import datetime,json,re,time
from pathlib import Path
from assistant_tools import READ_CONTRACT
from assistant_tools import APP_OPERATION_DOCS as OPERATIONS

def document(path):
 try:
  if path.stat().st_size>2_000_000:return {}
  data=json.loads(path.read_text());return data if isinstance(data,dict) else {}
 except (OSError,ValueError):return {}

def snapshot(s):
 from short_feedback import read as feedback
 projects=[]
 for p in s.rows('SELECT id,name,kind FROM projects ORDER BY created'):
  pid=p['id'];f=feedback(s.root,pid);channel=document(s.root/'integrations/youtube'/pid/'status.json');trends=document(s.root/'projects'/pid/'insights/trends.json')
  auto=[]
  if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='automations'").fetchone():auto=s.rows('SELECT id,name,kind,enabled,next_run,substr(last_error,1,180) last_error FROM automations WHERE project=? AND archived=0',(pid,))
  from app_capabilities import project_capabilities
  projects.append(dict(p,capabilities=project_capabilities(s,pid),agents=s.db.execute('SELECT count(*) FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive)',(pid,)).fetchone()[0],jobs=s.rows("SELECT id,agent,kind,status FROM jobs WHERE project=? AND status IN ('queued','running') ORDER BY created LIMIT 12",(pid,)),automations=auto,youtube=dict(connected=bool(channel.get('connected')),channel=channel.get('channel'),channel_id=channel.get('channel_id'),measured_at=f.get('collected_at'),channel_totals=f.get('channel'),tracked_video_views=sum(v.get('views') or 0 for v in f.get('videos',[])),tracked_video_count=len(f.get('videos',[])),analytics_status=f.get('analytics_status')),trends=dict(status=trends.get('status','not_collected'),collected_at=trends.get('collected_at'),topics=[dict(id=i.get('id'),topic=i.get('topic'),score=i.get('opportunity_score')) for i in trends.get('items',[])[:3]])))
 try:worker_age=time.time()-(s.root/'worker.heartbeat').stat().st_mtime
 except OSError:worker_age=None
 from missions import listing as mission_listing
 missions=mission_listing(s)
 missions=dict(missions,missions=[dict(id=m['id'],project=m['project'],name=m['name'],status=m['status'],goal=m['goal'][:250],run=m['run'],steps=[dict(node=x['node'],project=x['project'],state=x['state'],error=x['error'][:180]) for x in m.get('steps',[])]) for m in missions['missions'][:8]])
 # Measured Autopilot times: asked how long a cycle takes, the assistant guessed "1-2 minutes" (it is ~20).
 try:
  from venture_build import autopilot_now
  autopilot=autopilot_now(s)
 except Exception:autopilot=None
 return dict(assistant='ORBIT',missions=missions,autopilot=autopilot,scheduler=document(s.root/'scheduler-health.json'),architecture=dict(control='commander.py supervises all projects through validated bridge.py actions, durable jobs and an action journal. Agent/team automation is project-scoped; physical source edits remain reviewed.',media='autonomous.py owns the existing Shorts team; editorial.py validates source-grounded cuts; video_intelligence.py observes scenes; render_tools.py and montage.py render actual media.',growth='growth.py owns Pulse and trend settings; short_feedback.py and youtube_runtime.py supply measured YouTube data; publication.py owns approval and upload policy.',freshness='worker.py updates the saved app snapshot every 15 seconds; a fresh DB snapshot is also supplied before every model planning slice. Provider measurements have separate collected_at timestamps.'),observed_at=time.time(),worker_alive=worker_age is not None and worker_age<20,projects=projects,reads=READ_CONTRACT,operations=OPERATIONS,rules='This snapshot supersedes older app facts. Never infer measurements from chat history. These are current DB facts and timestamped cached provider measurements, not live remote telemetry. Use app reads for details. Missing is unknown, never zero. Project context applies to all projects, not only the open page. Use exact IDs and supported typed operations; never invent a tool. Credentials are managed by Connections, not sent to the model.')

def publish(s):
 path=s.root/'assistant-live-context.json'
 if path.exists() and time.time()-path.stat().st_mtime<15:return
 from youtube_runtime import atomic_json
 atomic_json(path,snapshot(s))

def planning_snapshot(s):
 """Complete project directory, compact live facts; details stay readable by ID."""
 full=snapshot(s);projects=[]
 for p in full['projects']:
  projects.append(dict(id=p['id'],name=p['name'],kind=p['kind'],capabilities=dict(shorts_available=p['capabilities']['shorts_available'],missing_roles=p['capabilities']['missing_roles']),agents=[dict(id=a['id'],name=a['name'],role=a['role'],model=a['model']) for a in s.rows('SELECT id,name,role,model FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive)',(p['id'],))],active_jobs=p['jobs'],youtube=p['youtube'],trends=p['trends'],automations=p['automations']))
 return dict(assistant='ORBIT',observed_at=full['observed_at'],worker_alive=full['worker_alive'],scheduler=full['scheduler'],projects=projects,missions=full['missions'],autopilot=full['autopilot'],operations=list(full['operations']),reads=list(full['reads']),rules=full['rules'])

def read_app(s,pid,name,refresh=False):
 s.project(pid)
 if name in ('email','mail','inbox'):name='emails'
 if name=='skills':
  from assistant_skills import listing
  from skill_api import summary
  return dict(skills=[summary(s,d) if d.get('api') else d for d in listing(s,True)],drafts_needing_key=[summary(s,d) for d in listing(s) if d.get('api') and d['status']!='published'])
 if name=='tasks':
  from automations import task_directory
  return task_directory(s)
 if name=='emails':
  import email_hub
  email_hub.schema(s)
  return dict(accounts=email_hub.status(s),messages=email_hub.listing(s,view='inbox'),coverage='Locally synchronized messages, not guaranteed complete remote history')
 if name=='missions':
  from missions import listing
  return listing(s,detail=True)
 if name=='economics':
  from missions import evaluate
  return evaluate(s,pid)
 if name=='editing':
  from editing_memory import read
  from edit_review import detail
  items=s.rows("SELECT id,name FROM artifacts WHERE project=? AND kind='video' AND path LIKE '%/renders/%' ORDER BY created DESC LIMIT 3",(pid,))
  return dict(preferences=read(s,pid),videos=[dict(item,review=detail(s,pid,item['id'])) for item in items])
 if name=='model_evaluations':
  from model_evaluation import status
  return status(s,pid)
 if name=='metrics':
  from short_feedback import read
  result=dict(measurements=read(s.root,pid),observed_at=time.time())
  if refresh:
   from growth import enqueue
   result['refresh']=enqueue(s,pid,'growth_metrics')
  return result
 if name=='trends':
  from growth import listing
  return listing(s,pid)
 if name=='publication':
  from publication import listing
  return listing(s,pid)
 if name=='automations':
  from automations import listing
  return listing(s,pid)
 if name=='youtube':
  from youtube import read_state
  return read_state(s.root,pid)
 if name=='overview':return snapshot(s)
 if name=='autopilot':
  # Where the Autopilot is and how long things take, measured from job times (never guessed).
  from venture_build import autopilot_now
  return autopilot_now(s) or dict(text='Az Autopilóta most nem épít terméket.')
 if name=='today':
  # The same day summary as the Telegram /ma command and the app's "Ma" button.
  from daily_report import today
  return dict(summary=today(s))
 raise ValueError('Ismeretlen app-adatnézet. Használd az aktuális eszközjegyzéket.')

def metric_question(prompt):
 from model_router import normalized
 p=normalized(prompt)
 if re.search(r'\b(ma|tegnap|heten|honapban|napban|oraban|today|yesterday|week|month|legutobbi|utolso|latest|egyedi|unique|tiktok|instagram|facebook|melyik)\b',p):return False
 if len(p)>350 or re.search(r'\b(fejlesz\w*|programoz\w*|epits\w*|poszt\w*|tolts\w*|keszits\w*|torolj\w*|allits\w*|ha|pelda|example)\b',p):return False
 return bool(re.search(r'(mennyi|hany|mekkora|how many|total|ossz)',p) and re.search(r'(megtekint|neztek|nezetseg|view|nezettseg|watched)',p) and re.search(r'(video|short|youtube|csatorna|channel)',p))

def target_projects(s,pid,prompt,global_mode):
 all=s.rows('SELECT id,name FROM projects');named=[p for p in all if p['name'].casefold() in prompt.casefold() or re.search(r'(?<!\w)'+re.escape(p['id'])+r'(?!\w)',prompt)]
 if named:return named
 connected=[p for p in all if document(s.root/'integrations/youtube'/p['id']/'status.json').get('connected')]
 return connected if global_mode else [p for p in all if p['id']==pid]

def measured_answer(s,job,row,global_mode):
 """Counts use a typed read lane, without asking an LLM to invent a plan or arithmetic."""
 if not metric_question(row['prompt']):return None
 from short_feedback import read
 from growth import enqueue
 from execution_queue import DeferredExecution
 targets=target_projects(s,job['project'],row['prompt'],global_mode)
 if not targets:return 'Jelenleg nincs csatlakoztatott YouTube-csatorna. A Kapcsolatok → YouTube alatt tudod bekötni.'
 payload=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]);pending=payload.get('metrics_refresh')
 if pending:
  active=[s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone() for jid in pending['jobs']]
  if any(r and r[0] in ('queued','running') for r in active) and time.time()-pending['started']<30:raise DeferredExecution('A YouTube aktuális számait kérem le.',2)
 else:
  jobs=[]
  for p in targets:
   data=read(s.root,p['id'])
   if time.time()-data.get('collected_at',0)>60:jobs.append(enqueue(s,p['id'],'growth_metrics')['job'])
  if jobs:
   payload['metrics_refresh']=dict(started=time.time(),jobs=jobs)
   s.db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),job['id']));s.db.commit()
   raise DeferredExecution('A YouTube aktuális számait kérem le.',2)
 lines=[];seen=set();total=0;complete=True
 def fmt(n):return format(round(n),',').replace(',',' ')
 for p in targets:
  data=read(s.root,p['id']);channel=data.get('channel') or {};name=channel.get('title') or p['name'];cid=channel.get('id') or p['id']
  if cid in seen:continue
  seen.add(cid);views=channel.get('views')
  video_rows=data.get('videos',[]);known_views=sum(v.get('views') or 0 for v in video_rows)
  if isinstance(views,(int,float)) and known_views>views:
   lines.append(name+': a követett '+str(len(video_rows))+' videódon **'+fmt(known_views)+' megtekintés** látszik összesen. A YouTube csatornaszámlálója még alacsonyabb értéket mutat, ezért most a videónkénti adatokat használom.');complete=False
  elif isinstance(views,(int,float)):
   lines.append(name+': **'+fmt(views)+' megtekintés** összesen a csatornán.');total+=views
  else:
   videos=data.get('videos',[])
   if videos:lines.append(name+': az ORBIT által követett '+str(len(videos))+' videón **'+fmt(sum(v.get('views') or 0 for v in videos))+' megtekintés**. A teljes csatornaszám most nem elérhető.')
   else:lines.append(name+': még nincs elérhető mérés. A csatornakapcsolat és a frissítési feladat állapota az Elérés és trendek oldalon látható.')
   complete=False
  stamp=data.get('collected_at')
  if stamp:
   from zoneinfo import ZoneInfo
   lines.append('Mérés: '+datetime.datetime.fromtimestamp(stamp,ZoneInfo('Europe/Budapest')).strftime('%Y. %m. %d. %H:%M')+' (Budapest).'+(' Ez korábbi adat; a friss mérés még nem érkezett meg.' if time.time()-stamp>120 else ''))
 if complete and len(seen)>1:lines.insert(0,'Összesen **'+fmt(total)+' megtekintés** a csatlakoztatott csatornákon.')
 lines.append('Ez megtekintésszám, nem az egyedi nézők száma.')
 return '\n\n'.join(lines)
