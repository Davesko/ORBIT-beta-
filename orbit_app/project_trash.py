"""The project list is the owner's: add, rename and delete, from the app's own window only.

Deleting moves a project to the trash. Its row leaves `projects`, so every list, the assistant's context and the
schedules stop seeing it, while its work and files stay until restored. Emptying it is the only permanent step and
asks for the name to be typed. The assistant and the agents cannot reach any of this (commander has no such action).
"""
import json,os,shutil,time
from pathlib import Path
import project_apps
from studio import text

HOME='universe'
PROTECTED={HOME:'Az alapprojekt: ide tér vissza az ORBIT, és ide érkezik a Telegram is.',
 'orbit-business-lab':'Itt dolgozik az Autopilóta, ezért nem törölhető. Átnevezni lehet.'}
# Rows that belong to a project through one of its jobs, missions, assistant turns or production runs.
CHILDREN=(('jobs',(('job_dependencies','job'),('job_runtime','job'),('job_log','job'),('command_links','job'),('notification_delivery','job'))),
 ('orbit_missions',(('orbit_mission_runs','mission'),('orbit_mission_events','mission'))),
 ('command_turns',(('command_audit','turn_id'),('command_global','turn_id'),('command_display','turn_id'),('command_action_journal','turn'),('supervisor_sessions','turn'),('command_links','turn_id'))),
 ('short_runs',(('editing_assignments','run'),)))

def schema(s):
 s.db.execute('CREATE TABLE IF NOT EXISTS project_trash(id TEXT PRIMARY KEY,data TEXT,deleted REAL,purged REAL)');s.db.commit()

def tables(s):
 return {r[0]:[c[1] for c in s.db.execute('PRAGMA table_info("'+r[0]+'")')] for r in s.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

def gone(s,pid):
 """A project the owner deleted must not come back with the next setup or update."""
 schema(s)
 return bool(s.db.execute('SELECT 1 FROM project_trash WHERE id=?',(pid,)).fetchone())

def millions_running():
 root=project_apps.MILLIONS
 if not (root/'core'/'ui_bridge.py').is_file():return False
 try:return json.loads((root/'power.json').read_text()).get('on') is not False
 except (OSError,ValueError):return True

def refusal(s,project):
 """Why this project cannot be deleted right now, in the owner's words; None when it can."""
 pid=project['id']
 if pid in PROTECTED:return PROTECTED[pid]
 if project['kind']=='trading' and millions_running():return 'A MiLLIONS még be van kapcsolva. Előbb állítsd le a fő kapcsolójával, különben a háttérben tovább futna.'
 busy=s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND status IN ('queued','running')",(pid,)).fetchone()[0]
 if busy:return str(busy)+' munka fut vagy vár ebben a projektben. Várd meg vagy állítsd le őket, utána törölhető.'
 for row in s.rows("SELECT name,spec FROM orbit_missions WHERE project!=? AND status='active'",(pid,)) if 'orbit_missions' in tables(s) else []:
  if pid in (row['spec'] or ''):return 'A(z) „'+row['name']+'” küldetés erre a projektre támaszkodik. Előbb azt állítsd le.'
 return None

def stop_schedules(s,pid,have):
 """Everything that would start work here later goes off; none of it comes back on by itself."""
 stopped=0
 for table,change,live in (('automations','enabled=0','enabled=1'),('recipes','interval=0','interval>0'),('agents','interval=0','interval>0'),('short_automation','enabled=0','enabled=1')):
  if table in have:stopped+=s.db.execute('UPDATE '+table+' SET '+change+' WHERE project=? AND '+live,(pid,)).rowcount
 if 'orbit_missions' in have:stopped+=s.db.execute("UPDATE orbit_missions SET status='paused' WHERE project=? AND status='active'",(pid,)).rowcount
 if 'growth_settings' in have:
  for row in s.rows('SELECT data FROM growth_settings WHERE project=?',(pid,)):
   data=json.loads(row['data'] or '{}')
   if data.get('enabled'):
    s.db.execute('UPDATE growth_settings SET data=? WHERE project=?',(json.dumps(dict(data,enabled=False)),pid));stopped+=1
 return stopped

def trash(s,pid):
 schema(s);project=s.project(pid);why=refusal(s,project)
 if why:raise ValueError(why)
 have=tables(s)
 try:
  stopped=stop_schedules(s,pid,have)
  s.db.execute('INSERT OR REPLACE INTO project_trash VALUES(?,?,?,NULL)',(pid,json.dumps(project),time.time()))
  s.db.execute('DELETE FROM projects WHERE id=?',(pid,))
  if 'telegram_owner' in have:s.db.execute('UPDATE telegram_owner SET project=? WHERE project=?',(HOME,pid))
  s.db.commit()
 except Exception:
  s.db.rollback();raise
 s.event(HOME,'🗑 „'+project['name']+'” a kukába került.')
 return dict(project=pid,stopped=stopped,message='„'+project['name']+'” a kukába került, a fájljai megmaradtak.'+(' '+str(stopped)+' időzítése leállt.' if stopped else ''))

def trashed(s,pid):
 row=s.db.execute('SELECT data FROM project_trash WHERE id=? AND purged IS NULL',(pid,)).fetchone()
 if not row:raise ValueError('Ez a projekt nincs a kukában.')
 return json.loads(row[0])

def restore(s,pid):
 schema(s);p=trashed(s,pid)
 s.db.execute('INSERT INTO projects(id,name,description,kind,created) VALUES(?,?,?,?,?)',(pid,p['name'],p['description'],p['kind'],p['created']))
 s.db.execute('DELETE FROM project_trash WHERE id=?',(pid,));s.db.commit();s.ensure_rooms(pid)
 s.event(pid,'Visszaállítva a kukából.')
 return dict(project=pid,message='„'+p['name']+'” visszakerült. Az időzítései kikapcsolva maradtak, az Automatizációknál kapcsolhatod vissza őket.')

def purge(s,pid,confirm):
 """Permanent. Reached only from the owner's window, after typing the project's name."""
 schema(s);p=trashed(s,pid)
 if str(confirm or '').strip()!=p['name']:raise ValueError('A végleges törléshez pontosan a projekt nevét írd be.')
 have=tables(s)
 try:
  for parent,children in CHILDREN:
   if parent in have:
    for child,column in children:
     if child in have:s.db.execute('DELETE FROM '+child+' WHERE '+column+' IN (SELECT id FROM '+parent+' WHERE project=?)',(pid,))
  for table,columns in have.items():
   if 'project' in columns:s.db.execute('DELETE FROM "'+table+'" WHERE project=?',(pid,))
  s.db.execute('UPDATE project_trash SET data=?,purged=? WHERE id=?',('',time.time(),pid))
  s.db.commit()
 except Exception:
  s.db.rollback();raise
 folder=s.root/'projects'/Path(pid).name
 if folder.is_dir() and not folder.is_symlink():shutil.rmtree(folder,ignore_errors=True)
 left=folder.exists()
 return dict(project=pid,message='„'+p['name']+'” véglegesen törölve.'+(' A mappáját nem sikerült teljesen eltávolítani: '+str(folder) if left else ''))

def edit(s,pid,name,description=None):
 project=s.project(pid);name=text(name,80)
 if s.db.execute('SELECT 1 FROM projects WHERE lower(name)=lower(?) AND id!=?',(name,pid)).fetchone():raise ValueError('Már van ilyen nevű projekt.')
 s.db.execute('UPDATE projects SET name=?,description=? WHERE id=?',(name,project['description'] if description is None else str(description)[:1000],pid));s.db.commit()
 return dict(project=pid,message='Elmentve: „'+name+'”.')

def folder_size(path):
 total=0
 for base,_,files in os.walk(path):
  for name in files:
   try:total+=os.lstat(os.path.join(base,name)).st_size
   except OSError:pass
 return total

def listing(s):
 schema(s);have=tables(s);projects=[]
 def count(table,where,pid):return s.db.execute('SELECT count(*) FROM '+table+' WHERE project=? AND '+where,(pid,)).fetchone()[0] if table in have else 0
 for p in s.rows('SELECT id,name,description,kind FROM projects ORDER BY created'):
  projects.append(dict(p,agents=count('agents','1=1',p['id']),busy=count('jobs',"status IN ('queued','running')",p['id']),scheduled=count('automations','enabled=1',p['id']),protected=PROTECTED.get(p['id'],'')))
 bin=[]
 for row in s.rows('SELECT id,data,deleted FROM project_trash WHERE purged IS NULL ORDER BY deleted DESC'):
  p=json.loads(row['data']);bin.append(dict(id=row['id'],name=p['name'],description=p['description'],deleted=row['deleted'],size=folder_size(s.root/'projects'/Path(row['id']).name)))
 return dict(projects=projects,trash=bin)

def dispatch(s,op,args=None):
 args=args or {};target=str(args.get('target') or '')
 if op=='project_list':return listing(s)
 if op=='project_edit':return edit(s,target,args.get('name'),args.get('description'))
 if op=='project_trash':return trash(s,target)
 if op=='project_restore':return restore(s,target)
 if op=='project_purge':return purge(s,target,args.get('confirm'))
 raise ValueError('Ismeretlen projektművelet.')
