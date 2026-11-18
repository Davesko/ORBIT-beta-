"""Project-scoped repeatable workflows with durable runs, independent schedules and deadlines."""
import json,time,uuid,datetime,re
from zoneinfo import ZoneInfo

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS automations(id TEXT PRIMARY KEY,project TEXT,name TEXT,kind TEXT,config TEXT,enabled INTEGER,interval INTEGER,plan TEXT,runtime_minutes INTEGER,daily_goal INTEGER,next_run REAL,last_error TEXT,created REAL,archived INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS automation_runs(id TEXT PRIMARY KEY,automation TEXT,project TEXT,jobs TEXT,created REAL,deadline REAL,status TEXT,error TEXT);
 CREATE INDEX IF NOT EXISTS automation_project ON automations(project,archived);
 CREATE TABLE IF NOT EXISTS automation_migrations(key TEXT PRIMARY KEY);''')

def decode(row):
 r=dict(row)
 if 'enabled' in r:r['enabled']=bool(r['enabled'])
 for k in ('config','plan','jobs'):
  if k in r:r[k]=json.loads(r[k])
 return r

def get(s,pid,aid):
 schema(s);r=s.db.execute('SELECT * FROM automations WHERE id=? AND project=? AND archived=0',(aid,pid)).fetchone()
 if not r:raise ValueError('Nem található automatizáció ebben a projektben.')
 return decode(r)

def validate(s,pid,d):
 s.project(pid)
 if not isinstance(d,dict) or not isinstance(d.get('config',{}),dict):raise ValueError('Az automatizáció és beállításai objektumok legyenek.')
 if type(d.get('enabled',False)) is not bool:raise ValueError('A bekapcsolás logikai érték legyen.')
 kind=d.get('kind','agent');cfg=dict(d.get('config',{}));name=str(d.get('name','')).strip()
 if not name or len(name)>100:raise ValueError('Adj meg legfeljebb 100 karakteres nevet.')
 if kind not in ('assistant','agent','graph','recipe','shorts'):raise ValueError('Ismeretlen folyamatfajta.')
 if cfg.get('scope')=='global' and kind!='assistant':raise ValueError('Projekt nélkül ORBIT asszisztens-feladat hozható létre.')
 if cfg.get('daily_time') is not None and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',str(cfg['daily_time'])):raise ValueError('Érvénytelen napi időpont.')
 if kind in ('agent','graph'):
  a=s.agent(cfg.get('agent'))
  if a['project']!=pid or s.db.execute('SELECT 1 FROM agent_archive WHERE id=?',(a['id'],)).fetchone():raise ValueError('A projekt aktív ügynökét válaszd.')
 elif kind=='assistant':
  if cfg.get('scope') not in (None,'project','global'):raise ValueError('Ismeretlen feladathatókör.')
  if cfg.get('scope')=='global' and pid!='universe':raise ValueError('A projekt nélküli feladat az ORBIT asszisztenshez tartozik.')
  if cfg.get('handler') not in (None,'email_review'):raise ValueError('Ismeretlen ORBIT-feladat.')
 elif kind=='recipe':
  if not s.db.execute('SELECT 1 FROM recipes WHERE project=? AND id=?',(pid,cfg.get('recipe'))).fetchone():raise ValueError('A projekt mentett láncát válaszd.')
 else:
  from autonomous import role_agents
  role_agents(s,pid)
  if not 2<=len(str(cfg.get('query','')).strip())<=200:raise ValueError('Adj meg videótémát vagy forráslinket.')
  if cfg.get('topic_source','fixed') not in ('fixed','trends'):raise ValueError('Ismeretlen témaforrás.')
  from short_style import validated,get as style
  cfg['requirements']=validated(style(s,pid),cfg.get('requirements',{}))
 if cfg.get('goal') is not None:
  g=cfg['goal']
  if not isinstance(g,dict) or type(g.get('target')) is not int or not 1<=g['target']<=500 or g.get('output','any') not in ('any','video'):raise ValueError('A cél 1–500 sikeres futás legyen.')
 if kind!='shorts' and (not isinstance(cfg.get('prompt'),str) or not cfg['prompt'].strip() or len(cfg['prompt'])>12000):raise ValueError('Írd le a pontos feladatot, legfeljebb 12000 karakterrel.')
 from autonomous import validate_plan
 plan=validate_plan(d.get('plan',{}))
 for k,lo,hi,default in [('interval',5,10080,180),('runtime_minutes',1,1440,120),('daily_goal',1,48,3)]:
  v=d.get(k,default)
  if type(v) is not int or not lo<=v<=hi:raise ValueError(k+': '+str(lo)+'–'+str(hi)+' közötti egész szám szükséges.')
 return dict(name=name,kind=kind,config=cfg,enabled=bool(d.get('enabled',False)),interval=d.get('interval',180),plan=plan,runtime_minutes=d.get('runtime_minutes',120),daily_goal=d.get('daily_goal',3))

def next_due(timestamp,a):
 from autonomous import next_slot
 clock=a.get('config',{}).get('daily_time')
 if not clock:return next_slot(timestamp,a.get('plan',{}))
 local=datetime.datetime.fromtimestamp(timestamp,ZoneInfo('Europe/Budapest'))
 for n in range(370):
  day=local.date()+datetime.timedelta(days=n)
  candidate=datetime.datetime.combine(day,datetime.time.fromisoformat(clock),local.tzinfo).timestamp()
  if candidate>=timestamp and next_slot(candidate,a.get('plan',{}))==candidate:return candidate
 return None

def save(s,pid,d):
 schema(s);aid=d.get('id')
 if aid:get(s,pid,aid)
 v=validate(s,pid,d);aid=aid or uuid.uuid4().hex
 from autonomous import next_slot
 due=next_due(time.time(),v) if v['enabled'] else 0
 if due is None:raise ValueError('A megadott időszak már véget ért.')
 s.db.execute('INSERT INTO automations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,config=excluded.config,enabled=excluded.enabled,interval=excluded.interval,plan=excluded.plan,runtime_minutes=excluded.runtime_minutes,daily_goal=excluded.daily_goal,next_run=excluded.next_run,last_error=\'\'',(aid,pid,v['name'],v['kind'],json.dumps(v['config']),int(v['enabled']),v['interval'],json.dumps(v['plan']),v['runtime_minutes'],v['daily_goal'],due,'',time.time()));s.db.commit();return aid

def tag(s,jobs,rid):
 for jid in jobs:
  row=s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()
  if row:
   p=json.loads(row[0]);p['automation_run']=rid;s.db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(p),jid))
 s.db.commit()

def launch(s,pid,aid,manual=False,repair=''):
 a=get(s,pid,aid)
 if repair:
  # Self-repair: the next attempt knows exactly what went wrong last time.
  a['config']=dict(a['config'],prompt=a['config'].get('prompt','')+'\n\nAz előző futás nem sikerült, ezt a hibát kerüld el vagy javítsd ki most: '+str(repair)[:600])
 # BEGIN IMMEDIATE reserves a run before enqueue methods commit; other callers see it.
 s.db.execute('BEGIN IMMEDIATE')
 if s.db.execute("SELECT 1 FROM automation_runs WHERE automation=? AND status IN ('starting','running')",(aid,)).fetchone():
  s.db.rollback();raise ValueError('Ez az automatizáció már fut.')
 rid=uuid.uuid4().hex;t=time.time()
 s.db.execute('INSERT INTO automation_runs VALUES(?,?,?,?,?,?,?,?)',(rid,aid,pid,'[]',t,t+a['runtime_minutes']*60,'starting',''));s.db.commit()
 try:
  cfg=a['config'];kind=a['kind']
  # Revalidate saved IDs at execution time, after agent or recipe edits.
  validate(s,pid,a)
  if kind=='assistant':
   if cfg.get('handler')=='email_review':
    from email_hub import agent_id
    jobs=[s.enqueue(agent_id(s),cfg['prompt'],'assist',payload=dict(task='scheduled_email_review',local_only=True,automation_run=rid,automation_id=aid))]
   else:
    from commander import enqueue
    jobs=[enqueue(s,pid,cfg['prompt'],'auto',global_mode=True)]
  elif kind=='shorts':
   from execution_queue import submit_short
   query=cfg['query']
   if cfg.get('topic_source')=='trends':
    from growth import choose_topic
    selected=choose_topic(s,pid,reserve=False);query=selected['query']
   if cfg.get('topic_source')=='trends':
    from source_policy import submit
    result=submit(s,pid,selected['source_bundle'],cfg['requirements'],'automation:'+rid)
   else:result=submit_short(s,pid,query,cfg['requirements'],'automation:'+rid)
   jobs=list(result.get('jobs',{}).values()) or [result['job']]
   if cfg.get('topic_source')=='trends':
    s.db.execute('INSERT OR REPLACE INTO growth_topics VALUES(?,?,?)',(pid,selected['evidence']['topic'].casefold(),time.time()));s.db.commit()
  elif kind=='recipe':
   r=s.db.execute('SELECT * FROM recipes WHERE id=? AND project=?',(cfg['recipe'],pid)).fetchone()
   last=s.enqueue_pipeline(pid,json.loads(r['agents']),cfg['prompt'],r['id']);run=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(last,)).fetchone()[0])['run'];jobs=[x['id'] for x in s.rows("SELECT id FROM jobs WHERE project=? AND json_extract(payload,'$.run')=?",(pid,run))]
  elif kind=='graph':jobs=list(s.enqueue_graph(pid,cfg['agent'],cfg['prompt'])['jobs'].values())
  else:
   from clip_farm import PROJECT,start_research
   if pid==PROJECT and cfg.get('campaign')=='gta6':
    from gta6 import start as start_gta6
    jobs=[start_gta6(s,rehearsal=cfg.get('rehearsal') is True,automation_run=rid)['job']]
   elif pid==PROJECT and cfg.get('require_verified_video'):
    topic=cfg.get('research_topic') or cfg['prompt']
    if len(topic)>200:topic='streamer gaming news'
    started=start_research(s,pid,topic,cfg.get('requirements'),automation_run=rid);jobs=[started['job']]
   else:
    from workflow_health import production_task
    if production_task(s,pid,cfg['agent'],cfg['prompt']):
     from execution_queue import submit_short
     result=submit_short(s,pid,cfg['prompt'],cfg.get('requirements'),'automation:'+rid)
     jobs=list(result.get('jobs',{}).values()) or [result['job']]
    else:jobs=[s.enqueue(cfg['agent'],cfg['prompt'],'scheduled',payload=dict(automation_run=rid))]
  tag(s,jobs,rid);s.db.execute("UPDATE automation_runs SET jobs=?,status='running' WHERE id=?",(json.dumps(jobs),rid));s.db.commit()
  return dict(run=rid,jobs=jobs)
 except Exception as exc:
  s.db.execute("UPDATE automation_runs SET status='failed',error=? WHERE id=?",(str(exc),rid));s.db.execute('UPDATE automations SET last_error=? WHERE id=?',(str(exc),aid));s.db.commit();raise

def members(s,r):
 jobs=s.rows("SELECT j.id,j.project,j.agent,a.name,j.kind,j.status,j.prompt,j.error,j.payload,j.created,rt.label,rt.phase FROM jobs j LEFT JOIN agents a ON a.id=j.agent LEFT JOIN job_runtime rt ON rt.job=j.id WHERE json_extract(j.payload,'$.automation_run')=? ORDER BY j.created",(r['id'],))
 # Follow assistant execution and spawned work across projects, not only its planning job.
 turns={json.loads(j['payload']).get('turn') for j in jobs};turns.discard(None)
 for turn in turns:
  for child in s.rows("SELECT j.id,j.project,j.agent,a.name,j.kind,j.status,j.prompt,j.error,j.payload,j.created,rt.label,rt.phase FROM jobs j LEFT JOIN agents a ON a.id=j.agent LEFT JOIN job_runtime rt ON rt.job=j.id WHERE json_extract(j.payload,'$.turn')=? OR j.id IN (SELECT job FROM command_links WHERE turn_id=?)",(turn,turn)):
   if child['id'] not in {j['id'] for j in jobs}:jobs.append(child)
 # Uploads are spawned later and belong to the same production run.
 refs={json.loads(j['payload']).get('run') for j in jobs};refs.discard(None)
 ids={j['id'] for j in jobs}
 for ref in refs:
  for j in s.rows("SELECT j.id,j.project,j.agent,a.name,j.kind,j.status,j.prompt,j.error,j.payload,j.created,rt.label,rt.phase FROM jobs j LEFT JOIN agents a ON a.id=j.agent LEFT JOIN job_runtime rt ON rt.job=j.id WHERE json_extract(j.payload,'$.run')=? ORDER BY j.created",(ref,)):
   if j['id'] not in ids:jobs.append(j);ids.add(j['id'])
 return jobs

def stop(s,pid,aid,archive=False,cancel=False):
 get(s,pid,aid);s.db.execute('UPDATE automations SET enabled=0,archived=? WHERE id=?',(int(archive),aid));s.db.commit()
 if cancel:
  for r in s.rows("SELECT * FROM automation_runs WHERE automation=? AND status IN ('starting','running')",(aid,)):
   for j in members(s,r):
    if j['status'] in ('queued','running'):s.cancel(j['id'])
   s.db.execute("UPDATE automation_runs SET status='cancelled',error='A felhasználó leállította.' WHERE id=?",(r['id'],))
  s.db.commit()

def toggle(s,pid,aid,enabled):
 """Change only scheduling state; never overwrite a stale task definition from a UI poll."""
 if type(enabled) is not bool:raise ValueError('A bekapcsolás logikai érték legyen.')
 a=get(s,pid,aid)
 if not enabled:stop(s,pid,aid);return dict(id=aid,enabled=False)
 validate(s,pid,a)
 from autonomous import next_slot
 due=next_due(time.time(),a)
 if due is None:raise ValueError('A feladat időszaka már véget ért. Módosítsd az ütemezést.')
 s.db.execute('UPDATE automations SET enabled=1,next_run=? WHERE id=?',(due,aid));s.db.commit()
 return dict(id=aid,enabled=True)

def task_directory(s):
 """Global view over the existing project-owned scheduler, without another execution engine."""
 projects=s.rows('SELECT id,name FROM projects ORDER BY name');tasks=[]
 for p in projects:
  for a in listing(s,p['id'])['automations']:
   a['scope']=a['config'].get('scope','project');a['project_name']='ORBIT asszisztens · projekt nélkül' if a['scope']=='global' else p['name'];tasks.append(a)
 return dict(projects=projects,automations=tasks)

def task_context(s,pid):
 data=listing(s,pid)
 from app_capabilities import project_capabilities
 from short_style import get as style
 return dict(agents=data['agents'],recipes=data['recipes'],shorts_available=project_capabilities(s,pid)['shorts_available'],style=style(s,pid))

STALL=45*60          # a running job silent this long is stuck
MAX_RESUMES=3        # resumes of one run from where it stopped before it counts as failed

def stalled(s,j):
 """A running job that logged no progress for STALL seconds."""
 last=s.db.execute('SELECT max(created) FROM job_log WHERE job=?',(j['id'],)).fetchone()[0]
 started=s.db.execute('SELECT started FROM jobs WHERE id=?',(j['id'],)).fetchone()
 last=max(last or 0,(started[0] if started else 0) or 0)
 return bool(last) and time.time()-last>STALL

def resume(s,r,jobs):
 """Continues a stopped run from where it stopped: the failed, cancelled and blocked steps run again and reuse
 everything already made (a story render keeps its finished scenes). False once a step has been resumed MAX_RESUMES times."""
 # A cancelled step was stopped by the owner (9 Nov: a stopped Wan render came back twice and held the GPU for hours).
 if any(j['status']=='cancelled' for j in jobs):return False
 stopped=[j for j in jobs if j['status'] in ('failed','blocked')]
 if not stopped:return False
 counts={j['id']:json.loads(j['payload']).get('resumed',0) for j in stopped}
 if max(counts.values())>=MAX_RESUMES:return False
 cause=next((j['error'] for j in stopped if j['status']=='failed' and j['error']),'') or next((j['error'] for j in stopped if j['error']),'')
 for j in stopped:
  p=json.loads(j['payload']);p['resumed']=counts[j['id']]+1;p['resume_reason']=str(cause)[:300]
  p['retry_at']=time.time()+60*2**counts[j['id']]  # 1, 2, 4 minutes: a busy model or a quota gets time to recover
  s.db.execute("UPDATE jobs SET status='queued',error='',started=NULL,finished=NULL,payload=? WHERE id=?",(json.dumps(p),j['id']))
 s.db.execute("UPDATE automation_runs SET status='running',error='' WHERE id=?",(r['id'],));s.db.commit()
 s.event(r['project'],'Automatizáció folytatása ugyanonnan · '+str(max(counts.values())+1)+'. alkalommal · ok: '+str(cause)[:160])
 return True

def reconcile(s):
 for r in s.rows("SELECT * FROM automation_runs WHERE status IN ('starting','running')"):
  jobs=members(s,r);active=[j for j in jobs if j['status'] in ('queued','running')]
  status=None;error=''
  # 9 Nov: the 2-hour runtime cut a Shorts render off while it drew its last scene and the video was lost.
  # The owner: never stop a model while it generates, no time limit; detect a fault, fix it and continue.
  # So the runtime no longer cancels anything; a step that stops making progress counts as failed and resumes.
  stuck=[j for j in active if j['status']=='running' and stalled(s,j)]
  for j in stuck:
   s.db.execute("UPDATE jobs SET status='failed',error=?,finished=? WHERE id=? AND status='running'",('Elakadt: '+str(STALL//60)+' perce nem haladt.',time.time(),j['id']))
  if stuck:s.db.commit();continue
  if active:continue
  elif jobs:
   failed=next((j for j in jobs if j['status']!='done'),None);status='failed' if failed else 'done';error=failed['error'] if failed else ''
  elif time.time()-r['created']>60:status='failed';error='A folyamatindítás megszakadt; ellenőrizd a naplót újraindítás előtt.'
  if status=='done':
   turns={json.loads(j['payload']).get('turn') for j in jobs};turns.discard(None)
   for turn in turns:
    t=s.db.execute('SELECT status,response FROM command_turns WHERE id=?',(turn,)).fetchone()
    if t and t['status'] not in ('done',):status='failed';error='Az ORBIT feladat figyelmet igényel: '+t['status']
  if status=='done':
   definition=s.db.execute('SELECT config FROM automations WHERE id=?',(r['automation'],)).fetchone()
   if definition and json.loads(definition['config']).get('require_verified_video') is True:
    verified=any(j['status']=='done' and json.loads(j['payload']).get('auto_step')=='verify' for j in jobs)
    if not verified:status='failed';error='A kutatás befejeződött, de nem készült ellenőrzött videó. Ez nem számít a napi videócélba; a következő ütemezett kutatás újra keres.'
  if status=='done':
   definition=s.db.execute('SELECT config FROM automations WHERE id=?',(r['automation'],)).fetchone()
   goal=(json.loads(definition['config']) if definition else {}).get('goal') or {}
   if goal.get('output')=='video':
    ids=[j['id'] for j in jobs]
    made=s.db.execute('SELECT 1 FROM artifacts WHERE kind=\'video\' AND job IN (%s) LIMIT 1'%','.join('?'*len(ids)),ids).fetchone() if ids else None
    if not made:status='failed';error='A futás véget ért, de nem készült kész videó; ez nem számít a célba.'
  if status=='failed' and jobs and resume(s,r,jobs):continue
  if status=='failed' and any(j['status']=='cancelled' for j in jobs):status='cancelled';error='A felhasználó leállította.'
  if status:
   s.db.execute('UPDATE automation_runs SET status=?,error=? WHERE id=?',(status,error,r['id']));s.db.execute('UPDATE automations SET last_error=? WHERE id=?',(error,r['automation']));s.db.commit()

def day_start():
 t=datetime.datetime.now(ZoneInfo('Europe/Budapest'));return t.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()

GOAL_FAST_RETRIES=3      # failures in a row restarted at once
GOAL_MAX_FAILURES=8      # then it stops and tells the owner instead of spinning

def goal_progress(s,a):
 since=a['config'].get('goal',{}).get('since',0)
 runs=s.rows('SELECT status,error FROM automation_runs WHERE automation=? AND created>=? ORDER BY created',(a['id'],since))
 done=sum(r['status']=='done' for r in runs);streak=0
 for r in reversed(runs):
  if r['status'] in ('failed','cancelled'):streak+=1
  elif r['status']=='done':break
 last_error=next((r['error'] for r in reversed(runs) if r['status'] in ('failed','cancelled') and r['error']),'')
 return dict(done=done,target=int(a['config']['goal'].get('target',1)),failures_in_a_row=streak,last_error=last_error,attempts=len(runs))

def goal_step(s,a,t):
 """Run after run until the target number of successful results exists; a failed run restarts at once with its error."""
 if any(r['status'] in ('starting','running') for r in s.rows('SELECT status FROM automation_runs WHERE automation=?',(a['id'],))):return
 g=goal_progress(s,a)
 if g['done']>=g['target']:
  s.db.execute("UPDATE automations SET enabled=0,next_run=0,last_error='' WHERE id=?",(a['id'],));s.db.commit()
  s.event(a['project'],'Automatizáció célja teljesítve · '+a['name']+' · '+str(g['done'])+'/'+str(g['target']));return
 if g['failures_in_a_row']>=GOAL_MAX_FAILURES:
  s.db.execute('UPDATE automations SET enabled=0,next_run=0,last_error=? WHERE id=?',('Megállt '+str(g['failures_in_a_row'])+' egymás utáni sikertelen futás után ('+str(g['done'])+'/'+str(g['target'])+' kész). Utolsó hiba: '+g['last_error'][:300],a['id']));s.db.commit()
  s.event(a['project'],'Automatizáció megállt · '+a['name']+' · '+str(g['done'])+'/'+str(g['target']));return
 if g['failures_in_a_row']>GOAL_FAST_RETRIES:
  # After the quick retries, a short pause lets a busy model or a slow source recover.
  last=s.db.execute('SELECT created FROM automation_runs WHERE automation=? ORDER BY created DESC LIMIT 1',(a['id'],)).fetchone()
  if last and t-last['created']<600:return
 try:launch(s,a['project'],a['id'],repair=g['last_error'] if g['failures_in_a_row'] else '')
 except Exception as exc:s.db.execute('UPDATE automations SET last_error=? WHERE id=?',(str(exc),a['id']));s.db.commit()

def tick(s):
 schema(s);migrate(s);reconcile(s)
 from autonomous import next_slot
 t=time.time()
 for a in [decode(r) for r in s.rows("SELECT * FROM automations WHERE enabled=1 AND archived=0 AND json_extract(config,'$.goal.target') IS NOT NULL")]:
  goal_step(s,a,t)
 for a in [decode(r) for r in s.rows("SELECT * FROM automations WHERE enabled=1 AND archived=0 AND next_run<=? AND json_extract(config,'$.goal.target') IS NULL",(t,))]:
  slot=next_slot(t,a['plan'])
  if slot is None:s.db.execute('UPDATE automations SET enabled=0,next_run=0 WHERE id=?',(a['id'],));s.db.commit();continue
  if slot>t:s.db.execute('UPDATE automations SET next_run=? WHERE id=?',(slot,a['id']));s.db.commit();continue
  from workflow_health import failure_health
  health=failure_health(s,a['id'],t)
  if health['retry_at']:
   due=next_slot(health['retry_at'],a['plan'])
   s.db.execute('UPDATE automations SET next_run=?,enabled=? WHERE id=?',(due or 0,int(due is not None),a['id']));s.db.commit();continue
  rows=s.rows('SELECT status FROM automation_runs WHERE automation=? AND created>=?',(a['id'],day_start()))
  if any(r['status'] in ('starting','running') for r in s.rows('SELECT status FROM automation_runs WHERE automation=?',(a['id'],))):continue
  due=next_due(t+1,a) if a['config'].get('daily_time') else next_slot(t+a['interval']*60,a['plan'])
  s.db.execute('UPDATE automations SET next_run=?,enabled=? WHERE id=?',(due or 0,int(due is not None),a['id']));s.db.commit()
  if sum(r['status']=='done' for r in rows)>=a['daily_goal'] or len(rows)>=a['daily_goal']*3:continue
  try:launch(s,a['project'],a['id'])
  except Exception as exc:s.db.execute('UPDATE automations SET last_error=? WHERE id=?',(str(exc),a['id']));s.db.commit()

def listing(s,pid):
 schema(s);s.project(pid);result=[]
 for a in [decode(r) for r in s.rows('SELECT * FROM automations WHERE project=? AND archived=0 ORDER BY created',(pid,))]:
  from workflow_health import failure_health,production_task
  a['health']=failure_health(s,a['id'])
  production=a['kind']=='shorts' or (a['kind']=='agent' and production_task(s,pid,a['config'].get('agent'),a['config'].get('prompt','')))
  a['execution_kind']='shorts' if production else a['kind']
  if production or a['config'].get('require_verified_video'):
   from app_capabilities import roles
   from autonomous import STEPS
   bound=roles(s,pid);order=([('research','Trendkutatás')] if a['config'].get('require_verified_video') else [])+STEPS
   a['workflow']=[dict(role=role,label=label,agent=bound[role],name=s.agent(bound[role])['name']) for role,label in order if role in bound]
  a['runs']=[]
  for r in s.rows('SELECT * FROM automation_runs WHERE automation=? ORDER BY created DESC LIMIT 5',(a['id'],)):
   r=decode(r);r['steps']=[]
   for j in members(s,r):
    step={k:v for k,v in j.items() if k!='payload'}
    parents={p['parent'] for p in s.rows('SELECT parent FROM job_dependencies WHERE job=?',(j['id'],))}
    legacy=s.db.execute('SELECT dependency FROM jobs WHERE id=?',(j['id'],)).fetchone()
    if legacy and legacy[0]:parents.add(legacy[0])
    from workflow_health import explain_step
    step['execution']=explain_step(s,j)
    step['parents']=sorted(parents);r['steps'].append(step)
   a['runs'].append(r)
  today=s.rows('SELECT status FROM automation_runs WHERE automation=? AND created>=?',(a['id'],day_start()));a['today']=dict(completed=sum(r['status']=='done' for r in today),attempts=len(today));result.append(a)
 from workflow_health import control_health
 return dict(control=control_health(s),automations=result,agents=[dict(id=a['id'],name=a['name']) for a in s.rows('SELECT id,name FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive)',(pid,))],recipes=[dict(id=r['id'],name=r['name'],agents=json.loads(r['agents']),prompt=r['prompt']) for r in s.rows('SELECT * FROM recipes WHERE project=?',(pid,))])

def migrate(s):
 """Adopt legacy timers without duplicating their schedulers or changing enabled state."""
 schema(s)
 from autonomous import plan_schema,next_slot
 plan_schema(s)
 def adopt(key,pid,values,due):
  aid='legacy-'+key
  existing=s.db.execute('SELECT id FROM automations WHERE id=?',(aid,)).fetchone()
  if existing:values['id']=aid
  enabled=values['enabled']
  if enabled and next_slot(time.time(),values.get('plan',{})) is None:values['enabled']=False
  saved=save(s,pid,values)
  if saved!=aid:
   s.db.execute('UPDATE automations SET id=? WHERE id=?',(aid,saved))
  if values['enabled'] and due:s.db.execute('UPDATE automations SET next_run=? WHERE id=?',(due,aid))
  s.db.execute('INSERT OR IGNORE INTO automation_migrations VALUES(?)',(key,));s.db.commit()
 for r in s.rows('SELECT * FROM short_automation'):
  key='short:'+r['project']
  if s.db.execute('SELECT 1 FROM automation_migrations WHERE key=?',(key,)).fetchone() and not r['enabled']:continue
  if r['query']:
   from short_style import get as style
   adopt(key,r['project'],dict(name='Automata videóstúdió',kind='shorts',config=dict(query=r['query'],requirements=style(s,r['project'])),enabled=bool(r['enabled']),interval=r['interval'],daily_goal=r.get('daily_goal') or r['daily_limit'],plan=json.loads(r['plan'] or '{}'),runtime_minutes=180),r['next_run'])
   s.db.execute('UPDATE short_automation SET enabled=0 WHERE project=?',(r['project'],));s.db.commit()
 for r in s.rows('SELECT * FROM recipes WHERE interval>0'):
  adopt('recipe:'+r['id'],r['project'],dict(name=r['name'],kind='recipe',config=dict(recipe=r['id'],prompt=r['prompt']),enabled=True,interval=r['interval'],daily_goal=48,runtime_minutes=120),r['next_run'])
  s.db.execute('UPDATE recipes SET interval=0,next_run=0 WHERE id=?',(r['id'],));s.db.commit()
 for r in s.rows('SELECT * FROM agents WHERE interval>0 AND id NOT IN (SELECT id FROM agent_archive)'):
  adopt('agent:'+r['id'],r['project'],dict(name=r['name']+' · ismétlődő feladat',kind='agent',config=dict(agent=r['id'],prompt=r['prompt']),enabled=True,interval=r['interval'],daily_goal=48,runtime_minutes=120),r['next_run'])
  aid='legacy-agent:'+r['id']
  for old in s.rows("SELECT id,status,created FROM jobs WHERE agent=? AND kind='scheduled' AND created>=? AND json_extract(payload,'$.automation_run') IS NULL",(r['id'],day_start())):
   rid='legacy-job:'+old['id'];status='running' if old['status'] in ('queued','running') else old['status']
   s.db.execute('INSERT OR IGNORE INTO automation_runs VALUES(?,?,?,?,?,?,?,?)',(rid,aid,r['project'],json.dumps([old['id']]),old['created'],time.time()+7200,status,''));s.db.commit();tag(s,[old['id']],rid)
  s.db.execute('UPDATE agents SET interval=0,next_run=0 WHERE id=?',(r['id'],));s.db.commit()
