"""Project apps: a kind of project can bring its own workshop view instead of the agent map.

MiLLIONS (projects of kind 'trading') is the first. Its research and paper-trading engine runs on its own
(the MiLLIONS launch agents, data in ~/Library/Application Support/ReszvenyAI); the Műhely shows and steers it
through the MiLLIONS JSON bridge. Virtual money only: MiLLIONS holds no exchange keys and signs no orders, and
ORBIT passes through only the operations listed here.
"""
import hashlib,json,os,re,shutil,subprocess,time,uuid
from pathlib import Path

MILLIONS=Path.home()/'Library/Application Support/ReszvenyAI'
# Read and paper-only controls. The bridge's own model calls (analyze, demo, evaluate) and its model server
# switch (start, stop) stay out: they would load a second large model next to ORBIT's.
MILLIONS_OPS=('dashboard_snapshot','activity','risk_settings','save_risk','monitor_start','monitor_stop','paper_start','paper_stop','copy_best','mode_off','stop_all',
 'paper_status','fast_start','fast_stop','paper_flatten','research_start','research_stop','research_ensure','trader_preview',
 'trader_check','copy_start','fast_settings','save_fast_settings','news_sources','save_news_sources','power_on','power_off')
APPS={'trading':dict(app='millions',title='MiLLIONS',subtitle='Gyakorló kereskedés virtuális pénzzel',
 pages=[('overview','Áttekintés'),('fast','Gyors AI'),('copy','Másolás'),('market','Hírek és piac'),('details','Haladó')]),
 'musicvideo':dict(app='clip',title='Videoklip',subtitle='Zene, irány, koncepció, moodboard, storyboard, helyszínek és költségvetés',
 pages=[('overview','Áttekintés'),('song','Zene és irány'),('concept','Koncepció és sztori'),('moodboard','Moodboard'),('storyboard','Storyboard'),('locations','Helyszínek'),('budget','Költségvetés'),('notes','Jegyzetek')]),
 'streamwatch':dict(app='watch',title='Élő adás figyelő',subtitle='Chat-csúcsok a figyelt streamerek élő adásaiban, kivágott jelenetek',
 pages=[('overview','Áttekintés'),('moments','Pillanatok'),('channels','Csatornák'),('settings','Beállítások')])}

# Managing the project list itself goes through the same bridge action (the native shell lets only known actions through).
PROJECT_OPS=('project_list','project_edit','project_trash','project_restore','project_purge')

# The Etsy shop: same reason, and the assistant has no way to these either.
ETSY_OPS=('etsy_status','etsy_callback','etsy_connect','etsy_disconnect','etsy_settings','etsy_retry','etsy_open')

# The owner's own tools in the main menu. Reached only from the app's window, like the ones above.
TOOL_ROUTES=(('kobold_','kobold_link'),('autopilot_','autopilot_hub'),('hands_','hands'),('improve_','self_improve'),('search_','app_search'),('skilllib_','skill_library'),('skill_','assistant_skills'),('chat_','chat_sessions'),('canvas_','canvas'),('memory_','memory_brain'),('finder_','model_finder'),('email_','email_hub'),('setup_','first_run'),('briefing_','email_brief'),('locator_','model_locator'),('trading_agents_','trading_agents'),('poster_','media_posters'),('activity_','activity_now'),('autonomy_','autonomy'),('publish_','publish_hub'),('watch_','stream_watch'),('series_','story_series'),('szim_','szim_app'),('update_','updater'))

def describe(s,pid):
 """The project's own app, or None when the Műhely shows the agent map."""
 app=APPS.get(s.project(pid).get('kind'))
 if not app and s.db.execute('SELECT 1 FROM projects WHERE id=? AND name=?',(pid,'Animációs stúdió')).fetchone():
  # The animation studio keeps its agent map; its Projekt tab is the series page (cast, formats, trend radar, episodes).
  # 16 Nov: rebuilt as the stickman studio (one main character, narrated second-person stories, Shorts and long videos).
  app=dict(app='series',title='Stickman stúdió',subtitle='Egy főszereplő, minden videóban új történet',pages=[('start','Új videó'),('cast','Szereplők'),('episodes','Videók')])
 if not app and s.db.execute('SELECT 1 FROM projects WHERE id=? AND name=?',(pid,'Szimgyár')).fetchone():
  app=dict(app='szim',title='Szimgyár',subtitle='Fizikai szimulációs shortok: videótípusok, preferenciák, gyártás',pages=[('make','Gyártás'),('types','Videótípusok'),('prefs','Preferenciák'),('videos','Videók')])
 if not app:return dict(app='workspace',title='Projekt',subtitle='A projekt saját munkaterülete',pages=[],installed=True)
 return dict(app,pages=[dict(id=i,label=l) for i,l in app['pages']],installed=app['app']!='millions' or (MILLIONS/'core'/'ui_bridge.py').is_file())

def millions(op,args=None,root=None,run=None):
 root=root or MILLIONS;run=run or subprocess.run
 if op not in MILLIONS_OPS:raise ValueError('Ezt a MiLLIONS-műveletet az ORBIT nem indítja.')
 bridge=Path(root)/'core'/'ui_bridge.py'
 if not bridge.is_file():raise ValueError('A MiLLIONS nincs telepítve ezen a gépen.')
 request=dict(action=op)
 # settings: a JSON object as text (copy size, fast-AI profile, news sources); MiLLIONS validates it.
 for key in ('symbol','news','settings'):
  if key in (args or {}):request[key]=(args[key] if isinstance(args[key],str) else json.dumps(args[key]))[:8000]
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
 try:r=run(['/usr/bin/python3',str(bridge)],input=json.dumps(request),capture_output=True,text=True,timeout=90,cwd=str(bridge.parent),env=env)
 except subprocess.TimeoutExpired:raise ValueError('A MiLLIONS nem válaszolt 90 másodpercen belül.') from None
 try:out=json.loads(r.stdout)
 except ValueError:raise ValueError('A MiLLIONS nem adott értelmezhető választ: '+(r.stderr or r.stdout or '')[-300:]) from None
 if out.get('ok') is False:raise ValueError(str(out.get('message') or 'A MiLLIONS-művelet nem sikerült.')[:500])
 return out

def workshop_id(idea):
 if not isinstance(idea,str) or not re.fullmatch(r'[a-f0-9]{1,16}',idea):raise ValueError('Ismeretlen Autopilóta-projekt.')
 return 'venture-'+idea

def transferable(root):
 return [p for p in root.rglob('*') if p.is_file() and
  not any(part.is_symlink() for part in [p,*p.parents] if root in part.parents) and
  p.name not in {'launch.json','launch-form.json'} and
  all(part!='__pycache__' and (not part.startswith('.') or part=='.env.example') for part in p.relative_to(root).parts)]

def write_import(path,write):
 if path.exists():return
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name('.import-'+uuid.uuid4().hex)
 try:
  write(tmp)
  # Link without replacing an edit that may have arrived during import.
  try:os.link(tmp,path)
  except FileExistsError:pass
 finally:tmp.unlink(missing_ok=True)

def venture_transfer(s,idea,focus):
 import venture,venture_build
 from missions import schema
 schema(s)
 pid=venture_build.PID
 product=s.safe_path(pid,venture_build.folder(focus))
 revisions=s.safe_path(pid,'workspace/ventures')
 files=[('workspace/product/'+p.relative_to(product).as_posix(),p) for p in transferable(product)]
 run_ids=set();plans=[]
 for result in sorted(revisions.glob('*/result.json')):
  if result.is_symlink() or result.parent.is_symlink():continue
  try:plan=json.loads(result.read_text())
  except (OSError,ValueError):continue
  if not isinstance(plan,dict):continue
  if plan.get('idea_id')!=idea and (plan.get('idea_id') or plan.get('name')!=focus['name']):continue
  run=result.parent.name;run_ids.add(run)
  if plan.get('mode')!='build':plans.append(plan)
  files.extend(('workspace/autopilot/revisions/'+run+'/'+p.relative_to(result.parent).as_posix(),p) for p in transferable(result.parent))
 mid=venture_build.mission_id(s)
 # A completed cycle's own evidence can be copied without truncating the research or test outputs.
 runs=[]
 if mid:
  rows=s.rows("""SELECT r.* FROM orbit_mission_runs r WHERE r.mission=? AND
   EXISTS (SELECT 1 FROM orbit_mission_steps b WHERE b.run=r.id AND b.node='build'
    AND json_valid(b.result) AND json_extract(b.result,'$.content.idea_id')=?) ORDER BY r.cycle""",(mid,idea))
  all_runs={r['id']:r for r in rows}
  for run in run_ids:
   if run not in all_runs:
    row=s.db.execute('SELECT * FROM orbit_mission_runs WHERE id=? AND mission=?',(run,mid)).fetchone()
    if row:all_runs[run]=dict(row)
  for r in sorted(all_runs.values(),key=lambda r:r['cycle']):
   rid=r['id']
   runs.append(dict(run=r,steps=s.rows('SELECT * FROM orbit_mission_steps WHERE run=? ORDER BY updated,node',(rid,)),
                    events=s.rows('SELECT * FROM orbit_mission_events WHERE run=? ORDER BY id',(rid,))))
 plans.sort(key=lambda p:p.get('created') or 0)
 return files,runs,plans[-1] if plans else {},venture.direction_for(s,idea)

def import_venture(s,idea):
 """Keep a writable product copy and a local archive of the attributable Autopilot work."""
 import venture_build,launch
 pid=workshop_id(idea)
 f=venture_build.focus_for(s,idea)
 if not f:raise ValueError('Ismeretlen Autopilóta-projekt.')
 files,runs,plan,direction=venture_transfer(s,idea,f)
 if not files and not runs and not plan:raise ValueError('Ehhez az ötlethez még nincs átvehető munka.')
 s.db.execute('CREATE TABLE IF NOT EXISTS workshop_imports(project TEXT PRIMARY KEY,idea TEXT NOT NULL UNIQUE)')
 existing=bool(s.db.execute('SELECT 1 FROM workshop_imports WHERE project=?',(pid,)).fetchone())
 if not s.db.execute('SELECT 1 FROM projects WHERE id=?',(pid,)).fetchone():
  s.create_project(f['name'][:80],str(plan.get('offer') or 'Autopilótából átvett munkapéldány.')[:1000],'venture',pid)
 pending=[(path,source) for path,source in files if not s.safe_path(pid,path).exists()]
 if sum(source.stat().st_size for _,source in pending)>1024**3:raise ValueError('Az átvételhez legfeljebb 1 GB új fájl másolható egyszerre.')
 for relative,source in pending:write_import(s.safe_path(pid,relative),lambda p:shutil.copy2(source,p))
 live=launch.read_state(s,venture_build.folder(f)) or {}
 public={k:live[k] for k in ('status','url','mode','launched','updated','stats') if k in live}
 meta=dict(name=f['name'],idea_id=idea,type=f.get('type'),direction=direction,plan=plan,publication=public,files=len(files),runs=len(runs),run_states={state:sum(r['run']['status']==state for r in runs) for state in {r['run']['status'] for r in runs}})
 for run in runs:
  raw=json.dumps(run,ensure_ascii=False,indent=2);revision=hashlib.sha256(raw.encode()).hexdigest()[:10]
  row=run['run'];path=s.safe_path(pid,f"workspace/autopilot/runs/{row['cycle']}-{revision}.json")
  write_import(path,lambda p:p.write_text(raw))
 summary=s.safe_path(pid,'workspace/autopilot/Atadas.json')
 summary.parent.mkdir(parents=True,exist_ok=True)
 tmp=summary.with_name('.handoff-'+uuid.uuid4().hex)
 try:tmp.write_text(json.dumps(meta,ensure_ascii=False,indent=2));tmp.replace(summary)
 finally:tmp.unlink(missing_ok=True)
 s.db.execute('INSERT OR IGNORE INTO workshop_imports VALUES(?,?)',(pid,idea));s.db.commit()
 return dict(project=pid,existing=existing,copied=len(pending),runs=len(runs))

def workspace_api_root(s,pid):
 from product_check import api_examples
 custom=s.safe_path(pid,'workspace/app')
 examples=api_examples(custom)
 if examples:return custom,examples
 imported=s.safe_path(pid,'workspace/product')
 return imported,api_examples(imported)

def workspace(s,pid):
 from canvas import LANGUAGES
 import workspace_app
 p=s.project(pid);base=s.root/'projects'/pid
 own=s.rows('SELECT id,name,path,kind FROM artifacts WHERE project=? ORDER BY created DESC',(pid,))
 seen={a['path'] for a in own}
 from media_tools import MEDIA_EXTENSIONS
 for area in ('product','app','autopilot','api-results'):
  for f in sorted((base/'workspace'/area).rglob('*')):
   if not f.is_file() or f.is_symlink() or str(f) in seen or any(p.startswith('.') for p in f.relative_to(base).parts):continue
   if not f.resolve().is_relative_to(base.resolve()):continue
   ext=f.suffix.lower()
   kind=MEDIA_EXTENSIONS.get(ext,'text' if ext in LANGUAGES else 'document')
   aid=uuid.uuid5(uuid.NAMESPACE_URL,str(f)).hex
   s.db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?,?)',(aid,pid,f.name,str(f),kind,time.time(),'workshop'))
   own.append(dict(id=aid,name=f.name,path=str(f),kind=kind))
 s.db.commit()
 idea=pid[len('venture-'):] if p['kind']=='venture' and pid.startswith('venture-') else None
 progress=None
 if idea:
  import venture_build
  focus=venture_build.focus_for(s,idea);mid=venture_build.mission_id(s)
  if focus and mid:
   stages,_=venture_build.progress(s,mid,focus)
   progress=dict(done=sum(x['state'] in ('done','skipped') for x in stages),total=len(stages))
 try:handoff=json.loads((base/'workspace/autopilot/Atadas.json').read_text())
 except (OSError,ValueError):handoff={}
 if not isinstance(handoff,dict):handoff={}
 files=[]
 for item in own:
  path=Path(item['path'])
  if not path.is_file() or not path.resolve().is_relative_to(base.resolve()):continue
  relative=str(path.relative_to(base)) if path.is_relative_to(base) else item['name']
  category='archive' if relative.startswith('workspace/autopilot/') else 'api' if relative.startswith('workspace/api-results/') else 'web' if path.suffix.lower() in ('.html','.htm') else 'notes' if path.suffix.lower() in ('.txt','.md') else 'code' if item['kind']=='text' else item['kind']
  files.append(dict(id=item['id'],name=item['name'],kind=item['kind'],category=category,path=relative))
 return dict(project=p,handoff={k:handoff.get(k) for k in ('direction','files','runs','run_states')}|{'offer':(handoff.get('plan') or {}).get('offer')},app=workspace_app.describe(s,pid),idea_id=idea,progress=progress,files=files,
   api_examples=workspace_api_root(s,pid)[1], jobs=s.rows('SELECT id,prompt,status FROM jobs WHERE project=? ORDER BY created DESC LIMIT 8',(pid,)))

def workspace_note(s,pid):
 from studio import uid
 path=s.safe_path(pid,'workspace/Projektvászon.md')
 if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# Projektvászon\n\n## Cél\n\n## Következő lépések\n')
 row=s.db.execute('SELECT id FROM artifacts WHERE project=? AND path=?',(pid,str(path))).fetchone()
 if row:return dict(id=row[0])
 aid=uid();s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(aid,pid,path.name,str(path),'text',time.time(),'workshop'));s.db.commit()
 return dict(id=aid)

def dispatch(s,pid,op,args=None):
 if op=='workspace_import':return dict(app='workspace',result=import_venture(s,(args or {}).get('idea_id')))
 if op=='workspace_snapshot':return dict(app='workspace',result=workspace(s,pid))
 if op=='workspace_app_data':
  from workspace_app import data
  return dict(app='workspace',result=data(s,pid,args or {}))
 if op=='workspace_note':return dict(app='workspace',result=workspace_note(s,pid))
 if op=='workspace_api':
  from product_check import try_api
  args=args or {}
  result=try_api(workspace_api_root(s,pid)[0],args.get('index'),args.get('body'))
  if args.get('record') is True:
   path=s.safe_path(pid,'workspace/api-results/'+time.strftime('%Y-%m-%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json')
   write_import(path,lambda p:p.write_text(json.dumps(dict(index=args.get('index'),input=args.get('body'),response=result),ensure_ascii=False,indent=2)))
  return dict(app='workspace',result=result)
 if op.startswith('clip_'):
  import musicvideo
  if s.project(pid).get('kind')!=musicvideo.KIND:raise ValueError('Ez nem videoklip-projekt.')
  return dict(app='clip',result=musicvideo.dispatch(s,pid,op,args))
 if op in PROJECT_OPS:
  import project_trash
  return dict(app='projects',result=project_trash.dispatch(s,op,args))
 if op in ETSY_OPS:
  import etsy
  return dict(app='etsy',result=etsy.dispatch(s,op,args))
 for prefix,module in TOOL_ROUTES:
  if op.startswith(prefix):return dict(app=module,result=__import__(module).dispatch(s,op,args))
 kind=s.project(pid).get('kind')
 if kind=='trading':return dict(app='millions',result=millions(op,args))
 raise ValueError('Ennek a projektnek nincs saját alkalmazása.')
