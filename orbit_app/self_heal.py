"""Self-healing supervision: restart a dead local model server, release stuck lab jobs.

Runs every scheduler tick. Each action is rate-limited and recorded in self-heal.json so the
app can show what was repaired. It never touches video renders, uploads or user commands.
"""
import json,os,signal,subprocess,sys,time,urllib.request
from pathlib import Path

MODEL_URL='http://127.0.0.1:11435/api/version'
AGENT='hu.orbit.ssd-models'
RESTART_GAP=1800
STUCK=50*60

def state(s):
 try:return json.loads((s.root/'self-heal.json').read_text())
 except (OSError,ValueError):return dict(fails=0,last_restart=0,events=[])

def save(s,st):
 st['events']=st.get('events',[])[-20:];st['checked']=time.time()
 tmp=s.root/'self-heal.json.tmp';tmp.write_text(json.dumps(st,ensure_ascii=False));os.replace(tmp,s.root/'self-heal.json')

def event(st,text):st.setdefault('events',[]).append(dict(at=time.time(),text=text))

def model_alive():
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(MODEL_URL,timeout=5) as r:return r.status==200
 except Exception:return False

def mounted(s):
 try:return os.path.ismount(json.loads((s.root/'model-storage.json').read_text())['mount'])
 except (OSError,ValueError,KeyError):return False

def restart_models():
 return subprocess.run(['launchctl','kickstart','-k','gui/'+str(os.getuid())+'/'+AGENT],capture_output=True,text=True,timeout=30).returncode==0

def recent_connection_failures(s,now):
 return s.db.execute("SELECT count(*) FROM jobs WHERE status='failed' AND finished>=? AND (error LIKE '%nem sikerült kapcsolódni%' OR error LIKE '%kiszolgálóhoz%')",(now-600,)).fetchone()[0]

def release_stuck(s,st,now):
 """A lab agent job with no recorded progress for 50 minutes is failed with a retryable reason."""
 rows=s.rows("""SELECT j.id,j.prompt FROM jobs j WHERE j.kind='mission_agent' AND j.status='running' AND j.started<?
  AND coalesce((SELECT max(created) FROM job_log WHERE job=j.id),j.started)<?""",(now-STUCK,now-STUCK))
 for r in rows:
  if s.db.execute("UPDATE jobs SET status='failed',error=?,finished=? WHERE id=? AND status='running'",('Beragadt feladat: 50 perce nem volt előrehaladás; időkeret lejárt, újrapróbálom.',now,r['id'])).rowcount:
   event(st,'Beragadt Autopilóta-lépés lezárva és újrapróbálásra küldve.')
 s.db.commit();return len(rows)

def restart_worker(st):
 """A released job's thread may still be blocked or spinning inside this process, holding the
 model lease. Stop the worker; launchd (KeepAlive) starts a fresh one and interrupted jobs are
 requeued at startup. Only acts inside the worker process itself."""
 if Path(sys.argv[0]).name!='worker.py':return False
 event(st,'Az ORBIT háttérfolyamat újraindul a beragadt szál miatt.')
 os.kill(os.getpid(),signal.SIGTERM);return True

def tick(s,now=None):
 now=now or time.time();st=state(s)
 if mounted(s):
  alive=model_alive()
  st['fails']=0 if alive else st.get('fails',0)+1
  failures=recent_connection_failures(s,now)
  if (st['fails']>=3 or (alive and failures>=3)) and now-st.get('last_restart',0)>RESTART_GAP:
   ok=restart_models();st['last_restart']=now;st['fails']=0
   event(st,'Helyi AI-szerver újraindítva'+(' (nem válaszolt)' if not alive else ' (ismétlődő kapcsolódási hibák)')+('' if ok else ' – sikertelen'))
 released=release_stuck(s,st,now)
 if released:restart_worker(st)
 save(s,st);return st

def summary(s):
 st=state(s);last=(st.get('events') or [None])[-1]
 return dict(last_event=last,recent=bool(last and time.time()-last['at']<3600))
