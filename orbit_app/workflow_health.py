"""Deterministic production admission and bounded schedule recovery."""
import json,re,time

def production_task(s,pid,agent,prompt):
 from app_capabilities import roles,project_capabilities
 from model_router import normalized
 if not project_capabilities(s,pid)['shorts_available'] or roles(s,pid).get('producer')!=agent:return False
 text=normalized(prompt)
 if re.search(r'\b(ne|nem|not|explain|hogyan|milyen|elemezd|analyze|describe|prompt|beallitas|settings|status|allapot|mennyi|miert|why|how|list|sorold|ellenorizd|check)\b',text) or '?' in text:return False
 return bool(re.search(r'\b(video|videot|videokat|shorts?|klip|clip|montage|highlights?)\b',text)) and len(prompt.strip())<=200

def failure_health(s,aid,now=None):
 now=time.time() if now is None else now;rows=s.rows("SELECT id,status,error,created FROM automation_runs WHERE automation=? AND status NOT IN ('starting','running') ORDER BY created DESC LIMIT 8",(aid,))
 failures=[]
 for row in rows:
  if row['status']!='failed' and not (row['status']=='cancelled' and row['error']=='A beállított futási idő lejárt.'):break
  failures.append(row)
 if not failures:return dict(failures=0,retry_at=0,label='')
 # A bounded pause is visible; a new probe is permitted later, not every scheduler tick.
 last=failures[0];delay=min(21600,300*2**min(len(failures)-1,6))
 finished=s.db.execute("SELECT max(finished) FROM jobs WHERE json_extract(payload,'$.automation_run')=?",(last['id'],)).fetchone()[0]
 until=max(last['created'],finished or 0)+delay
 return dict(failures=len(failures),retry_at=until if until>now else 0,label=('Ismétlődő hiba után várakozik · '+str(len(failures))+' sikertelen futás') if until>now else '')

def explain_step(s,job):
 import json,time,datetime
 from zoneinfo import ZoneInfo
 p=json.loads(job['payload']);status=job['status'];error=job.get('error') or '';lower=error.casefold();category='workflow';action='A napló és a mentett bemenet ellenőrizhető.'
 for words,kind,advice in [(("ssd","meghajtó"),'storage','Csatlakoztasd a modelltár SSD-jét.'),(("youtube","oauth","sign in","bot","hitelesítés"),'youtube','A Kapcsolatok → YouTube alatt ellenőrizd a kapcsolatot.'),(("kvóta","quota","429"),'quota','Várd meg a kvóta visszaállását, vagy használj helyi modellt.'),(("modell","időkeret","kiszolgáló"),'model','Ellenőrizd a helyi modellek elérhetőségét. A mentett források megmaradtak.'),(("forrás","friss hírt","letölthető"),'source','A forráskeresési napló mutatja, mely témához vagy oldalhoz nincs megfelelő elérhető videó.')]:
  if any(w in lower for w in words):category=kind;action=advice;break
 label={'done':'Elkészült','running':'Dolgozik','queued':'Sorban áll','failed':'Javítást igényel','blocked':'Az előző lépésre vár','cancelled':'Leállítva'}.get(status,status)
 if status=='queued' and p.get('retry_at',0)>time.time():label='Újrapróbálás: '+datetime.datetime.fromtimestamp(p['retry_at'],ZoneInfo('Europe/Budapest')).strftime('%H:%M')
 elif status=='queued':
  parents=s.rows('SELECT p.status,p.prompt FROM job_dependencies d JOIN jobs p ON p.id=d.parent WHERE d.job=?',(job['id'],))
  if any(x['status']!='done' for x in parents):label='Az előző ügynök eredményére vár'
 generation=p.get('generation',{})
 if status=='running' and generation.get('phase'):label=generation['phase']
 can_resume=(status in ('failed','blocked') and p.get('auto_step') in ('selection','layout')) or (status=='failed' and p.get('story_step') in ('sound','render'))
 return dict(label=label,category=category,action=action if error else '',retry_at=p.get('retry_at'),model=p.get('selected_model'),generation=generation,can_resume=can_resume)

def control_health(s):
 import os,time
 from model_hub import config
 from connections import settings
 try:age=time.time()-(s.root/'worker.heartbeat').stat().st_mtime
 except OSError:age=None
 cfg=config();mount=cfg.get('mount');return dict(worker_alive=age is not None and age<20,worker_age=round(age,1) if age is not None else None,ssd_mounted=os.path.ismount(mount) if mount else None,mode=settings(s.root)['mode'])
