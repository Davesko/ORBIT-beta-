"""Daily housekeeping of files ORBIT itself produces. Models and user media are never deleted;
unused models are only reported so the owner can decide."""
import json,os,shutil,time
from pathlib import Path

KEEP_DEPLOY_BACKUPS=10
LOG_LIMIT=20*1024*1024
LOG_KEEP=5*1024*1024
UNUSED_DAYS=7

def prune_deploy_backups(root):
 """Deploy backups are code copies that git also holds; keep the newest few."""
 folder=Path(root)/'backups';removed=0
 if not folder.is_dir():return 0
 deploys=sorted((p for p in folder.iterdir() if p.is_dir() and p.name.startswith('deploy-')),key=lambda p:p.name,reverse=True)
 for old in deploys[KEEP_DEPLOY_BACKUPS:]:
  shutil.rmtree(old,ignore_errors=True);removed+=1
 return removed

def trim_logs(root):
 """Keep the tail of oversized service logs (the model server log grows without bound)."""
 trimmed=[]
 for log in (Path(root)/'logs').glob('*.log'):
  try:
   if log.stat().st_size<=LOG_LIMIT:continue
   # Rewrite in place: the service keeps its file handle open, so replacing the file would
   # leave it writing into a deleted file and the log would silently stop.
   with open(log,'r+b') as f:
    f.seek(-LOG_KEEP,os.SEEK_END);tail=f.read();tail=tail[tail.find(b'\n')+1:]
    f.seek(0);f.write(tail);f.truncate()
   trimmed.append(log.name)
  except OSError:continue
 return trimmed

def repair_sidecars(root):
 """macOS keeps writing "._name" files on the exFAT model SSD; the model server only cleans
 them at its own start, so this daily pass keeps the manifest folders clean in between."""
 try:store=json.loads((Path(root)/'model-storage.json').read_text())['ollama']
 except (OSError,ValueError,KeyError):return 0
 if not Path(store).is_dir():return 0
 from model_manifest import repair_sidecars as repair
 return repair(store,root)

def unused_models(s,now=None):
 """Installed local models no job has used for a week (suggestions only)."""
 now=now or time.time()
 try:
  from model_hub import models
  installed=[m for m in models() if m.get('storage') in ('SSD','Belső') or m.get('port')]
 except Exception:return []
 out=[]
 for m in installed:
  if 'embedding' in m['name']:continue
  last=s.db.execute("SELECT max(created) FROM jobs WHERE json_extract(payload,'$.selected_model')=? OR json_extract(payload,'$.agent_snapshot.model')=?",(m['name'],m['name'])).fetchone()[0]
  pinned=s.db.execute('SELECT 1 FROM agents WHERE model=?',(m['name'],)).fetchone()
  if not pinned and (not last or now-last>UNUSED_DAYS*86400):out.append(dict(name=m['name'],gb=round(m.get('size',0)/1e9,1),last_used=last))
 return out

STALE_BLOCKED=7*86400


def close_stale_blocked(s,now):
 """Steps that waited over a week on a failed or stopped step never run; they are closed so lists show live work only.
 Nothing is deleted: the job, its log and its files stay, only the status changes from blocked to cancelled."""
 changed=s.db.execute("""UPDATE jobs SET status='cancelled',finished=?,error=CASE WHEN error='' OR error IS NULL
                          THEN 'Lezárva: egy hétnél régebb óta várt egy megállt lépésre.' ELSE error END
                          WHERE status='blocked' AND kind!='command' AND created<?""",(now,now-STALE_BLOCKED)).rowcount
 s.db.commit();return changed


def tick(s,now=None):
 now=now or time.time();path=Path(s.root)/'housekeeping.json'
 try:st=json.loads(path.read_text())
 except (OSError,ValueError):st={}
 if now-st.get('ran',0)<86400:return st
 st=dict(ran=now,deploy_backups_removed=prune_deploy_backups(s.root),logs_trimmed=trim_logs(s.root),sidecars_quarantined=repair_sidecars(s.root),unused_models=unused_models(s,now),stale_blocked_closed=close_stale_blocked(s,now))
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(st,ensure_ascii=False));os.replace(tmp,path);return st
