"""Stable agent roles and current, credential-free application capabilities."""
import time,re
STAGES=('producer','source','transcript','selection','layout','render','metadata','verify')
LABELS={'producer':'Gyártásirányító','research':'Trendkutató','source':'Forrásgyűjtés','transcript':'Beszédfelismerés','selection':'Jelenetszerkesztés','layout':'Képkivágás','render':'Renderelés','metadata':'Cím és leírás','verify':'Ellenőrzés'}
HINTS={'producer':('Nova','Producer'),'research':('Pulse','Trend researcher'),'source':('Atlas','Forrásszerkesztő'),'transcript':('Echo','Átiratgazda'),'selection':('Scout','Klipszerkesztő'),'layout':('Pixel','Videószerkesztő'),'render':('Lex','Felirat- és hangszerkesztő'),'metadata':('Reach','Cím- és csomagszerkesztő'),'verify':('Vega','Végellenőr')}

def roles(s,pid):
 agents=s.rows('SELECT id,name,role,room FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid',(pid,));active={a['id']:a for a in agents};stored={}
 if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='project_agent_roles'").fetchone():stored={r['role']:r['agent'] for r in s.rows('SELECT role,agent FROM project_agent_roles WHERE project=?',(pid,))}
 found={}
 for key,(name,title) in HINTS.items():
  if key in stored:
   if stored[key] in active:found[key]=stored[key]
   continue
  match=next((a for a in agents if a['role']==title),None) or next((a for a in agents if a['name']==name),None)
  if key=='producer' and not match:match=next((a for a in agents if a['room']=='bridge'),None)
  if match:found[key]=match['id']
 return found

def bind(s,pid):
 assignments=roles(s,pid)
 if not all(k in assignments for k in STAGES):return False
 s.db.execute('CREATE TABLE IF NOT EXISTS project_agent_roles(project TEXT,role TEXT,agent TEXT,PRIMARY KEY(project,role))')
 for role,aid in assignments.items():s.db.execute('INSERT OR IGNORE INTO project_agent_roles VALUES(?,?,?)',(pid,role,aid))
 s.db.commit();return True

def project_capabilities(s,pid):
 assignments=roles(s,pid);missing=[k for k in STAGES if k not in assignments]
 agents={a['id']:a for a in s.rows('SELECT id,name,role,model FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive)',(pid,))}
 order=(('research',) if 'research' in assignments else ())+STAGES
 return dict(roles=assignments,shorts_available=not missing,missing_roles=[LABELS[k] for k in missing],chain=[dict(stage=k,label=LABELS[k],**agents[assignments[k]]) for k in order if k in assignments],operations=['production_resume','project_role_save','agent_run','graph_run','room_save','agent_save','workflow_automation_save']+(['start_shorts'] if not missing else []))

def status(s):
 observed=time.time();projects=[]
 for project in s.rows('SELECT id,name,kind FROM projects ORDER BY created'):
  pid=project['id'];cap=project_capabilities(s,pid)
  active=s.rows("SELECT j.id,j.agent,a.name,j.kind,j.status,j.error,j.created,r.label,r.phase FROM jobs j LEFT JOIN agents a ON a.id=j.agent LEFT JOIN job_runtime r ON r.job=j.id WHERE j.project=? AND j.status IN ('running','queued') ORDER BY j.created LIMIT 30",(pid,))
  failures=s.rows("SELECT j.id,a.name,j.kind,j.error,j.finished,json_extract(j.payload,'$.auto_step') stage,json_extract(j.payload,'$.story_step') story_stage FROM jobs j LEFT JOIN agents a ON a.id=j.agent WHERE j.project=? AND j.status='failed' ORDER BY j.finished DESC LIMIT 2",(pid,))
  projects.append(dict(project,capabilities=cap,active_jobs=active,recent_failures=failures))
 try:age=max(0,observed-(s.root/'worker.heartbeat').stat().st_mtime)
 except OSError:age=None
 return dict(observed_at=observed,worker_alive=age is not None and age<20,worker_age_seconds=age,projects=projects,active_count=sum(len(p['active_jobs']) for p in projects),rules='Current DB state, not model memory. A controller reply is not a completed production. Never restart a completed action to recover a failed later stage. Archived bound roles require explicit replacement.')

def status_answer(s,prompt,exclude_job=None):
 from model_router import normalized
 p=normalized(prompt).strip(' .?!')
 if not (re.fullmatch(r'(?:az app |az alkalmazas |a rendszer )?allapota|rendszerallapot|mi fut (?:most|jelenleg)|milyen projektek(?:et)?(?: latsz)?|mely(?:ik)? (?:ugynokok|agentek) dolgoznak(?: most)?|mi akadt el|most mi generalodik|mi generalodik|(?:most )?mi keszul(?: most| jelenleg)?|van (?:eppen )?futo feladat',p) or re.search(r'\b(?:sorold fel|mutasd meg)\b.{0,35}\b(?:projekteket|futo feladatokat|aktiv ugynokoket)\b',p)):return None
 if re.search(r'\b(indits|keszits|generalj|torolj|modosits)\b',p):return None
 data=status(s);lines=['A háttérfolyamat '+('elérhető.' if data['worker_alive'] else 'állapota most nem igazolt; ellenőrizd a háttérfolyamatot.')]
 for project in data['projects']:
  jobs=[j for j in project['active_jobs'] if j['id']!=exclude_job];working=[j['name'] or 'Ügynök' for j in jobs if j['status']=='running'];waiting=sum(j['status']=='queued' for j in jobs)
  lines.append(project['name']+': '+(', '.join(working)+' dolgozik' if working else 'nincs futó feladat')+(' · '+str(waiting)+' várakozik' if waiting else '')+'.')
  if 'akadt' in p and project['recent_failures']:
   fail=project['recent_failures'][0];lines.append('Legutóbbi hiba ('+str(fail['name'] or 'feladat')+'): '+str(fail['error'])[:250])
 from zoneinfo import ZoneInfo
 import datetime
 lines.append('Ellenőrizve: '+datetime.datetime.fromtimestamp(data['observed_at'],ZoneInfo('Europe/Budapest')).strftime('%H:%M:%S')+' · Budapest. A várakozó feladat még nem készült el.')
 return '\n\n'.join(lines)


def assign_role(s,pid,role,aid):
 s.project(pid)
 if role not in HINTS:raise ValueError('Ismeretlen projekt-szerepkör.')
 agent=s.agent(aid)
 if agent['project']!=pid or s.db.execute('SELECT 1 FROM agent_archive WHERE id=?',(aid,)).fetchone():raise ValueError('A projekt aktív ügynökét válaszd.')
 existing=roles(s,pid)
 if role in STAGES and any(key in STAGES and key!=role and value==aid for key,value in existing.items()):raise ValueError('Egy gyártási ügynök egy gyártási szerepet tölthet be.')
 s.db.execute('CREATE TABLE IF NOT EXISTS project_agent_roles(project TEXT,role TEXT,agent TEXT,PRIMARY KEY(project,role))')
 s.db.execute('INSERT OR REPLACE INTO project_agent_roles VALUES(?,?,?)',(pid,role,aid));s.db.commit();s.event(pid,'Szerepkör hozzárendelve: '+LABELS[role]+' → '+agent['name'])
 return project_capabilities(s,pid)
