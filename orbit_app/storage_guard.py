"""Unattended-run safety: free disk space and keep the Mac awake while ORBIT works.

Disk: below LOW new cycles/schedules are not admitted (running work continues). Below PRUNE,
already-used downloaded source videos older than SOURCE_AGE are removed, oldest first. Their
source.json manifest and the clip_downloads history stay, so dedup is unchanged and cache reuse
simply skips the missing file. Renders, results, backups and project files are never touched.
Sleep: while an objective is active one `caffeinate -i -w <worker pid>` assertion is held.
"""
import json,os,shutil,subprocess,time
from pathlib import Path
GB=1024**3
LOW=6*GB
PRUNE=10*GB
SOURCE_AGE=72*3600
CHECK_EVERY=600
_state=dict(checked=0,free=None,awake=None)

def free(root):return shutil.disk_usage(str(root)).free

def storage_ok(s):
 """Cached (CHECK_EVERY) answer; admission callers must stay cheap."""
 if _state['free'] is None or time.time()-_state['checked']>=CHECK_EVERY:maintain(s)
 return _state['free']>=LOW

def check(s):
 if not storage_ok(s):raise ValueError('Kevés a szabad hely ('+str(round(_state['free']/GB,1))+' GB). Új ciklus és ütemezett gyártás csak '+str(LOW//GB)+' GB felett indul; a futó munka folytatódik.')
 return True

def prune_sources(s,target):
 busy={r['project'] for r in s.rows("SELECT DISTINCT project FROM jobs WHERE status IN ('queued','running')")}
 cutoff=time.time()-SOURCE_AGE;candidates=[]
 for project in (s.root/'projects').glob('*'):
  if project.name in busy:continue
  for media in project.glob('sources/*/source.*'):
   if media.suffix=='.json' or not media.is_file():continue
   stat=media.stat()
   if stat.st_mtime<cutoff:candidates.append((stat.st_mtime,stat.st_size,media))
 removed=[]
 for _,size,media in sorted(candidates):
  if free(s.root)>=target:break
  try:media.unlink();removed.append(dict(path=str(media),bytes=size))
  except OSError:continue
 return removed

def maintain(s):
 before=free(s.root);removed=prune_sources(s,PRUNE) if before<PRUNE else []
 after=free(s.root);_state.update(checked=time.time(),free=after)
 report=dict(observed_at=time.time(),free_bytes=after,low_threshold=LOW,prune_threshold=PRUNE,admission_paused=after<LOW,removed_sources=removed[-50:],removed_bytes=sum(r['bytes'] for r in removed))
 if removed or after<LOW:
  previous=s.root/'storage-health.json'
  try:old=json.loads(previous.read_text())
  except (OSError,ValueError):old={}
  report['total_removed_bytes']=old.get('total_removed_bytes',0)+report['removed_bytes']
 from youtube_runtime import atomic_json
 atomic_json(s.root/'storage-health.json',report)
 return report

def keep_awake(s):
 """Hold one idle-sleep assertion while any objective is active; it dies with the worker."""
 active=bool(s.db.execute("SELECT 1 FROM orbit_missions WHERE status='active' LIMIT 1").fetchone())
 if not active:
  try:
   import stickman_studio;active=stickman_studio.batch_active(s)
  except Exception:pass
 proc=_state['awake']
 if active and (proc is None or proc.poll() is not None):
  _state['awake']=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 elif not active and proc is not None:
  if proc.poll() is None:proc.terminate()
  _state['awake']=None
 return active
