"""Durable user requests; busy workers are a queue state, not a failed instruction."""
import json,time
class DeferredExecution(Exception):
 def __init__(self,message,seconds=20):super().__init__(message);self.seconds=seconds

def submit_short(s,pid,query,requirements=None,origin=None,source_handoff=None,local_files=None):
 from autonomous import start,production_receipt
 from clip_sources import schema
 schema(s)
 if origin:
  receipt=production_receipt(s,pid,origin)
  if receipt:return receipt
  old=s.db.execute("SELECT id FROM jobs WHERE project=? AND kind='short_request' AND json_extract(payload,'$.origin')=?",(pid,origin)).fetchone()
  if old:return dict(job=old[0],queued=True,existing=True)
 busy=s.db.execute("SELECT 1 FROM jobs WHERE project=? AND kind IN ('graph','youtube_upload') AND status IN ('queued','running')",(pid,)).fetchone()
 automation_run=origin.split(':',1)[1] if isinstance(origin,str) and origin.startswith('automation:') else None
 if source_handoff:
  from source_policy import resolve
  resolve(s,pid,source_handoff)
 if not busy:
  try:return start(s,pid,query,requirements=requirements,origin=origin,**(dict(source_handoff=source_handoff) if source_handoff else {}),**(dict(automation_run=automation_run) if automation_run else {}),**(dict(local_files=local_files) if local_files else {}))
  except DeferredExecution:pass
 if not isinstance(query,str) or not 2<=len(query.strip())<=200:raise ValueError('2–200 karakteres videótémát vagy YouTube-linket adj meg.')
 if requirements:
  from short_style import validated,get
  validated(get(s,pid),requirements)
 # Repeating the same planned action must not submit the same request twice.
 aid=s.rows('SELECT id FROM agents WHERE project=? ORDER BY rowid LIMIT 1',(pid,))[0]['id']
 s.db.execute('BEGIN IMMEDIATE')
 try:
  receipt=production_receipt(s,pid,origin)
  if receipt:s.db.rollback();return receipt
  old=s.db.execute("SELECT id FROM jobs WHERE project=? AND kind='short_request' AND json_extract(payload,'$.origin')=?",(pid,origin)).fetchone() if origin else None
  if old:s.db.rollback();return dict(job=old[0],queued=True,existing=True)
  count=s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND kind='short_request' AND status IN ('queued','running')",(pid,)).fetchone()[0]
  if count>=5:raise ValueError('Öt videókérés már várakozik. A meglévő kérések állapotát a chatben követheted.')
  jid=s.enqueue(aid,'Várakozó videókérés · '+query,'short_request',payload=dict(query=query,requirements=requirements,origin=origin,automation_run=automation_run,source_handoff=source_handoff,**(dict(local_files=local_files) if local_files else {})),commit=False)
  s.db.commit()
 except Exception:s.db.rollback();raise
 s.job_stage(jid,'waiting','A videókérés sorban áll · a jelenlegi videó után indul')
 return dict(job=jid,queued=True)

def run_short(s,job):
 p=json.loads(job['payload'])
 from autonomous import start,production_receipt
 origin=p.get('origin') or 'queue:'+job['id']
 result=production_receipt(s,job['project'],origin)
 if not result:
  if s.db.execute("SELECT 1 FROM jobs WHERE project=? AND id!=? AND kind IN ('graph','youtube_upload') AND status IN ('queued','running')",(job['project'],job['id'])).fetchone():raise DeferredExecution('A jelenlegi videó készül; a kérés biztonságosan sorban áll.',30)
  result=start(s,job['project'],p['query'],requirements=p.get('requirements'),origin=origin,**(dict(source_handoff=p['source_handoff']) if p.get('source_handoff') else {}),**(dict(automation_run=p['automation_run']) if p.get('automation_run') else {}),**(dict(local_files=p['local_files']) if p.get('local_files') else {}))
 if p.get('automation_run'):
  from automations import tag
  tag(s,list(result['jobs'].values()),p['automation_run'])
 links=s.rows('SELECT turn_id FROM command_links WHERE job=?',(job['id'],)) if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='command_links'").fetchone() else []
 for row in links:
  for jid in result['jobs'].values():s.db.execute('INSERT OR IGNORE INTO command_links VALUES(?,?)',(row['turn_id'],jid))
 s.db.commit();return 'A sorban álló videógyártás elindult. Futás: '+result['run']

def defer(s,job,exc):
 row=s.db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()
 p=json.loads(row[0] if row else job['payload']);p['retry_at']=time.time()+exc.seconds
 p['generation']=dict(phase=str(exc),provider='scheduler')
 changed=s.db.execute("UPDATE jobs SET status='queued',started=NULL,finished=NULL,error='',payload=? WHERE id=? AND status IN ('running','queued')",(json.dumps(p),job['id'])).rowcount
 if not changed:s.db.rollback();return
 if job['kind']=='command' and p.get('turn'):
  s.db.execute("UPDATE command_turns SET status='queued',response=? WHERE id=? AND status NOT IN ('done','queued_apply','applying','review','attention','cancelled')",('A kérésed megmaradt. '+str(exc),p['turn']))
 s.db.commit();s.job_stage(job['id'],'waiting',str(exc))
