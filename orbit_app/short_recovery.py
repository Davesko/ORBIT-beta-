"""Bounded recovery for idempotent production stages; never blindly retry a publication."""
import json,time

class SourceEvidenceError(ValueError):
 """Explicit source-evidence failure, never a timing/JSON/model failure."""


def recover(s,job,error):
 if job['kind']!='graph':return False
 payload=json.loads(job['payload']);step=payload.get('auto_step')
 if not step or s.cancelled(job['id']):return False
 row=s.db.execute('SELECT data FROM short_runs WHERE id=? AND project=?',(payload.get('run'),job['project'])).fetchone()
 if not row:return False
 attempt=payload.get('recovery_attempt',0)
 if attempt<2:
  payload.update(recovery_attempt=attempt+1,retry_at=time.time()+min(120,20*(attempt+1)),last_recovery_error=str(error)[:500])
  s.db.execute("UPDATE jobs SET status='queued',payload=?,error='',started=NULL,finished=NULL WHERE id=?",(json.dumps(payload),job['id']));s.db.commit()
  s.job_stage(job['id'],'recovering','Automatikus javítás · '+str(attempt+1)+'/2',str(error)[:500]);return True
 data=json.loads(row['data'])
 # A timing-valid selection can contradict an earlier director interpretation.
 # Re-plan the evidence once, instead of replaying the identical cached brief.
 story_conflict=any(x in str(error) for x in ('tényleges csúcspontja','nem zárja le','hook-jelöltjeitől','külön események'))
 if step=='selection' and story_conflict and data.get('story_replans',0)<1:
  data['story_replans']=data.get('story_replans',0)+1
  director=data.pop('director',{})
  if type(director.get('event_id')) is int:
   data.setdefault('director_rejections',[]).append(dict(event_id=director['event_id'],catalog_key=director.get('catalog_key'),reason=str(error)[:700]))
  data.pop('selection_checkpoint',None)
  s.db.execute('UPDATE short_runs SET data=? WHERE id=?',(json.dumps(data),payload['run']))
  payload.update(recovery_attempt=0,retry_at=time.time()+30,last_recovery_error=str(error)[:700])
  s.db.execute("UPDATE jobs SET status='queued',payload=?,error='',started=NULL,finished=NULL WHERE id=?",(json.dumps(payload),job['id']));s.db.commit()
  s.job_stage(job['id'],'recovering','ORBIT új történetet tervez a mentett forrásból');return True
 infrastructure=any(x in str(error).casefold() for x in ('nincs elérhető helyi beszélgetőmodell','nem válaszolt','időkeret','kiszolgálóhoz','kvóta','nincs megfelelő helyi képi modell'))
 if infrastructure:return False  # New footage cannot repair an unavailable model server.
 if step=='selection' and isinstance(error,SourceEvidenceError) and data.get('source_refreshes',0)<1:
  data['source_refreshes']=data.get('source_refreshes',0)+1
  for key in ('sources','source','tracks','transcript','subtitle','visual_analysis','selection_checkpoint','montage','reframes','camera_plan','render','metadata','complete','youtube'):data.pop(key,None)
  s.db.execute('UPDATE short_runs SET data=? WHERE id=?',(json.dumps(data),payload['run']))
  for j in s.rows("SELECT id,payload FROM jobs WHERE project=? AND json_extract(payload,'$.run')=?",(job['project'],payload['run'])):
   p=json.loads(j['payload'])
   if p.get('auto_step') in ('source','transcript','selection','layout','render','metadata','verify'):
    p.update(recovery_attempt=0,retry_at=time.time()+30)
    s.db.execute("UPDATE jobs SET status='queued',error='',result='',started=NULL,finished=NULL,payload=? WHERE id=?",(json.dumps(p),j['id']))
  s.db.commit();s.job_stage(job['id'],'recovering','Új releváns forrás keresése · a történet újratervezése');return True
 return False

def resume_story(s,pid,job,payload):
 """Retry a local story media stage while preserving its approved upstream plan."""
 jid=job['id'];run=payload['run']
 with s.db:
  s.db.execute('BEGIN IMMEDIATE')
  current=s.db.execute('SELECT status FROM jobs WHERE id=? AND project=?',(jid,pid)).fetchone()
  if not current:raise ValueError('A feladat nem található ebben a projektben.')
  status=current[0]
  if status in ('queued','running'):return dict(job=jid,run=run,existing=True)
  if status!='failed':raise ValueError('A Történetműhelyben a hibás lépést válaszd a folytatáshoz.')
  if s.db.execute('SELECT 1 FROM agent_archive WHERE id=?',(job['agent'],)).fetchone():
   raise ValueError('A feladat ügynöke archiválva van.')
  if s.db.execute("""SELECT 1 FROM job_dependencies d JOIN jobs p ON p.id=d.parent
                     WHERE d.job=? AND p.status!='done'""",(jid,)).fetchone():
   raise ValueError('A mentett jelenetterv vagy hangkeverés még nem készült el.')
  jobs=[jid]
  if payload['story_step']=='sound':
   jobs.extend(r['id'] for r in s.rows("""SELECT id FROM jobs WHERE project=? AND status='blocked'
                   AND json_extract(payload,'$.run')=? AND json_extract(payload,'$.story_step')='render'""",(pid,run)))
  s.db.executemany("""UPDATE jobs SET status='queued',error='',result='',started=NULL,finished=NULL
                      WHERE id=? AND project=?""",[(key,pid) for key in jobs])
 s.job_stage(jid,'resuming','Folytatás a mentett jelenettervből')
 return dict(job=jid,run=run,jobs={str(i):key for i,key in enumerate(jobs)})

def resume(s,pid,jid):
 """Explicitly resume a read/planning stage from saved inputs, never an upload."""
 row=s.db.execute('SELECT * FROM jobs WHERE id=? AND project=?',(jid,pid)).fetchone()
 if not row:raise ValueError('A feladat nem található ebben a projektben.')
 job=dict(row);payload=json.loads(job['payload']);step=payload.get('auto_step')
 if job['kind']=='graph' and payload.get('story_step') in ('sound','render'):
  return resume_story(s,pid,job,payload)
 if job['kind']!='graph' or step not in ('selection','layout'):raise ValueError('Csak a jelenettervezés vagy képkivágás folytatható innen; a render és feltöltés külön ellenőrzést igényel.')
 if job['status'] in ('queued','running'):return dict(job=jid,existing=True)
 if job['status'] not in ('failed','blocked'):raise ValueError('Ez a lépés már elkészült vagy le lett állítva.')
 if s.db.execute('SELECT 1 FROM agent_archive WHERE id=?',(job['agent'],)).fetchone():raise ValueError('A feladat ügynöke archiválva van.')
 run=payload.get('run');saved=s.db.execute('SELECT data FROM short_runs WHERE id=? AND project=?',(run,pid)).fetchone()
 if not saved:raise ValueError('Nincs mentett gyártási bemenet.')
 data=json.loads(saved['data']);tracks=data.get('tracks',[])
 if not tracks:raise ValueError('Hiányzik a mentett forrás- és átiratcsomag.')
 for track in tracks:
  for name in (track['source']['source_video'],track['transcript_file']):
   if not s.safe_path(pid,name).is_file():raise ValueError('Hiányzó mentett bemenet: '+name)
 parents=s.rows('SELECT parent FROM job_dependencies WHERE job=?',(jid,))
 if job['dependency']:parents.append(dict(parent=job['dependency']))
 for parent in parents:
  prior=s.db.execute('SELECT status FROM jobs WHERE id=? AND project=?',(parent['parent'],pid)).fetchone()
  if not prior or prior['status']!='done':raise ValueError('Előbb a hiányzó bemenetet előállító lépést kell befejezni.')
 s.db.execute('BEGIN IMMEDIATE')
 try:
  if s.db.execute("SELECT 1 FROM jobs WHERE project=? AND status IN ('queued','running') AND kind IN ('graph','short_request','youtube_upload')",(pid,)).fetchone():raise ValueError('A projektben már van aktív videógyártás vagy feltöltés.')
  data=json.loads(saved['data']);data.pop('selection_checkpoint',None)
  if step=='selection':data.pop('evidence_enrichment_attempted',None)
  s.db.execute('UPDATE short_runs SET data=? WHERE id=? AND project=?',(json.dumps(data),run,pid))
  order=['producer','source','transcript','selection','layout','render','metadata','verify'];resumed=[]
  for sibling in s.rows("SELECT id,status,payload FROM jobs WHERE project=? AND json_extract(payload,'$.run')=?",(pid,run)):
   p=json.loads(sibling['payload']);stage=p.get('auto_step')
   if stage in order[order.index(step):] and sibling['status'] in ('failed','blocked'):
    p.pop('retry_at',None);p['recovery_attempt']=0
    s.db.execute("UPDATE jobs SET status='queued',error='',result='',started=NULL,finished=NULL,payload=? WHERE id=?",(json.dumps(p),sibling['id']));resumed.append(sibling['id'])
  s.db.commit()
 except Exception:s.db.rollback();raise
 s.job_stage(jid,'resuming','Folytatás a mentett, ellenőrzött bemenetből','Upstream source downloads/transcripts remain intact; publication policy is unchanged.')
 return dict(job=jid,run=run,jobs={str(i):key for i,key in enumerate(resumed)})
