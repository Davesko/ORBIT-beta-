"""Project-scoped publication review with explicit approval and upload deduplication."""
import json,time
from pathlib import Path

def schema(s):
 s.db.execute('CREATE TABLE IF NOT EXISTS publication_reviews(artifact TEXT PRIMARY KEY,project TEXT,run TEXT,title TEXT,description TEXT,made_for_kids INTEGER,job TEXT,created REAL,approved REAL)');s.db.commit()

def prepare(s,pid,artifact,metadata,run=None,made_for_kids=False):
 from youtube import validate_short
 schema(s)
 row=s.db.execute("SELECT * FROM artifacts WHERE id=? AND project=? AND kind='video'",(artifact,pid)).fetchone()
 if not row:raise ValueError('Nem található kész projektvideó.')
 path=Path(row['path']).resolve();base=(s.root/'projects'/pid).resolve()
 if base not in path.parents or path.relative_to(base).parts[0]!='renders':raise ValueError('Csak renderelt projektvideó publikálható.')
 validate_short(path)
 title=str(metadata.get('title') or row['name'])[:100];description=str(metadata.get('description',''))[:3500]
 s.db.execute('INSERT INTO publication_reviews VALUES(?,?,?,?,?,?,NULL,?,NULL) ON CONFLICT(artifact) DO UPDATE SET run=excluded.run,title=excluded.title,description=excluded.description,made_for_kids=excluded.made_for_kids WHERE publication_reviews.project=excluded.project AND publication_reviews.approved IS NULL AND publication_reviews.job IS NULL',(artifact,pid,run,title,description,int(made_for_kids),time.time()));s.db.commit()
 return artifact

def approve(s,pid,artifact,title=None,description=None,made_for_kids=None,retry=False,confirmed_absent=False):
 from youtube import queue_upload
 schema(s)
 s.db.execute('BEGIN IMMEDIATE')
 try:
  row=s.db.execute('SELECT * FROM publication_reviews WHERE artifact=? AND project=?',(artifact,pid)).fetchone()
  if not row:raise ValueError('Nincs ellenőrzésre előkészített videó ebben a projektben.')
  title=row['title'] if title is None else title;description=row['description'] if description is None else description
  kids=bool(row['made_for_kids']) if made_for_kids is None else made_for_kids
  result=queue_upload(s,pid,artifact,title,description,kids,'public',run_id=row['run'],retry=retry,confirmed_absent=confirmed_absent)
  s.db.execute('UPDATE publication_reviews SET title=?,description=?,made_for_kids=?,job=?,approved=COALESCE(approved,?) WHERE artifact=? AND project=?',(title,description,int(kids),result['job'],time.time(),artifact,pid));s.db.commit();return result
 except Exception:s.db.rollback();raise

def listing(s,pid):
 from short_style import get
 from youtube import read_state,upload_status_text
 schema(s)
 # Backfill completed productions, without uploading or touching their media.
 if s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='short_runs'").fetchone():
  for row in s.rows("SELECT id,data FROM short_runs WHERE project=? AND json_extract(data,'$.complete')=1 ORDER BY created DESC LIMIT 200",(pid,)):
   d=json.loads(row['data']);name=d.get('render',{}).get('saved')
   if not name:continue
   a=s.db.execute("SELECT id FROM artifacts WHERE project=? AND path=? AND kind='video'",(pid,str(s.root/'projects'/pid/name))).fetchone()
   if not a:continue
   meta=dict(d.get('metadata',{}));url=d.get('source',{}).get('metadata',{}).get('url','')
   if url and url not in meta.get('description',''):meta['description']=meta.get('description','')+'\nForrás: '+url
   try:prepare(s,pid,a['id'],meta,row['id'],d.get('style',{}).get('made_for_kids',False))
   except (ValueError,OSError):continue
 # Standalone rendered creations also need a visible manual review entry.
 for a in s.rows("SELECT a.id,a.name FROM artifacts a WHERE a.project=? AND a.kind='video' AND a.id NOT IN (SELECT artifact FROM publication_reviews) AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.id=a.job AND json_extract(j.payload,'$.auto_step') IS NOT NULL) ORDER BY created DESC LIMIT 200",(pid,)):
  try:prepare(s,pid,a['id'],dict(title=a['name']))
  except (ValueError,OSError):continue
 connection=read_state(s.root,pid);items=[]
 for row in s.rows('SELECT r.*,a.name,a.path,a.kind,a.job render_job,a.created media_created FROM publication_reviews r JOIN artifacts a ON a.id=r.artifact AND a.project=r.project WHERE r.project=? ORDER BY a.created DESC LIMIT 200',(pid,)):
  producer=s.db.execute('SELECT payload FROM jobs WHERE id=? AND project=?',(row['render_job'],pid)).fetchone()
  if producer:
   payload=json.loads(producer['payload'])
   if payload.get('auto_step') and payload.get('run') and not s.db.execute("SELECT 1 FROM short_runs WHERE id=? AND project=? AND json_extract(data,'$.complete')=1",(payload['run'],pid)).fetchone():continue
  name=str(Path(row['path']).relative_to(s.root/'projects'/pid))
  job=s.db.execute("SELECT id,status,error FROM jobs WHERE project=? AND kind='youtube_upload' AND json_extract(payload,'$.name')=? ORDER BY created DESC LIMIT 1",(pid,name)).fetchone()
  status={'done':'published','queued':'queued','running':'uploading','failed':'failed','cancelled':'cancelled'}.get(job['status'],'pending') if job else 'pending'
  receipt=next((u for u in connection['uploads'] if job and u.get('job')==job['id']),{})
  if job and not receipt:
   try:receipt=json.loads((s.root/'integrations/youtube'/pid/('receipt-'+job['id']+'.json')).read_text())
   except (OSError,ValueError):pass
  manifest=Path(row['path']).with_suffix('.json')
  try:duration=json.loads(manifest.read_text()).get('duration')
  except (OSError,ValueError):duration=None
  items.append(dict(id=row['artifact'],project=pid,kind='video',name=row['name'],title=row['title'],description=row['description'],made_for_kids=bool(row['made_for_kids']),created=row['media_created'],duration=duration,status=status,error=job['error'] if job else '',video_id=receipt.get('id'),url=receipt.get('url'),privacy=receipt.get('privacy'),youtube_status=upload_status_text(receipt) if receipt else '',shorts_status=receipt.get('shorts_status','unconfirmed'),processing_failure=receipt.get('processing_failure')))
 return dict(items=items,style=get(s,pid),connected=connection['connected'],channel=connection['channel'])

def settings(s,pid,mode):
 if mode not in ('review','auto','local'):raise ValueError('Ismeretlen publikálási mód.')
 from short_style import save
 values=dict(publish_to_youtube=mode!='local',review_before_upload=mode!='auto')
 style=save(s,pid,values)
 if s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='automations'").fetchone():
  for row in s.rows("SELECT id,config FROM automations WHERE project=? AND kind='shorts' AND archived=0",(pid,)):
   config=json.loads(row['config']);config.setdefault('requirements',{}).update(values)
   s.db.execute('UPDATE automations SET config=? WHERE id=?',(json.dumps(config),row['id']))
  s.db.commit()
 return style
