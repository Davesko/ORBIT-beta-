"""Durable supervisor turns: one planning slice, cumulative evidence, no replay of effects."""
import json,time,re
from execution_queue import DeferredExecution

MAX_CYCLES=10

def schema(s):
 s.db.execute('CREATE TABLE IF NOT EXISTS supervisor_sessions(turn TEXT PRIMARY KEY,state TEXT,updated REAL)');s.db.commit()

def load(s,turn):
 schema(s);r=s.db.execute('SELECT state FROM supervisor_sessions WHERE turn=?',(turn,)).fetchone();return json.loads(r[0]) if r else {}

def save(s,turn,state):
 schema(s);s.db.execute('INSERT INTO supervisor_sessions VALUES(?,?,?) ON CONFLICT(turn) DO UPDATE SET state=excluded.state,updated=excluded.updated',(turn,json.dumps(state,ensure_ascii=False),time.time()));s.db.commit()

def compact(value,depth=0):
 if depth>8:return 'Read the exact object separately for deeper details.'
 if isinstance(value,str):return value[:10000]
 if isinstance(value,list):return [compact(v,depth+1) for v in value[:25]]
 if isinstance(value,dict):return {k:compact(v,depth+1) for k,v in value.items() if k not in ('image','images','base64','poster')}
 return value

def evidence(cache):
 """Keep complete JSON values; old reads remain on disk and can be retrieved by key."""
 result=[];size=0
 for key,value in reversed(list(cache.items())):
  item=dict(read=json.loads(key),result=compact(value));length=len(json.dumps(item,ensure_ascii=False))
  if size+length>18000 and result:continue
  result.insert(0,item);size+=length
  if size>=18000:break
 return result

def yield_turn(s,job,turn,messages,cache,cycle,repeats=0,delay=1,label='A terv következő lépésének előkészítése'):
 if cycle>=MAX_CYCLES:return attention(s,turn,'A modell még nem adott egyértelmű, végrehajtható tervet. A kérés és a megszerzett adatok megmaradtak; pontosítás vagy másik modell szükséges.')
 save(s,turn,dict(messages=messages,cache=cache,cycle=cycle,repeats=repeats))
 s.db.execute("UPDATE command_turns SET status='queued',response=? WHERE id=?",('A kérésed megmaradt. '+label+'.',turn));s.db.commit();s.job_stage(job['id'],'planning',label)
 raise DeferredExecution(label,delay)

def attention(s,turn,reason):
 s.db.execute("UPDATE command_turns SET status='attention',response=? WHERE id=?",(reason,turn));s.db.commit();return reason

def wait_for_model(s,job,error):
 """Only pure planning can wait/retry automatically; no application action is replayed."""
 if job['kind']!='command' or s.cancelled(job['id']):return False
 row=s.db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone();p=json.loads(row[0]);turn=p.get('turn')
 state=s.db.execute('SELECT status FROM command_turns WHERE id=?',(turn,)).fetchone()
 if not state or state[0] in ('done','applying','queued_apply','review','cancelled','attention'):return False
 if not any(x in str(error).casefold() for x in ('időkeret','nem válaszolt','nincs elérhető','nem érhető el','nem sikerült kapcsolódni','kapcsolat','kiszolgáló','kvóta')):return False
 attempt=p.get('model_waits',0)+1
 if attempt>3:
  message='Három újrapróbálás után sincs válaszoló modell. A kérés és a mentett adatok megmaradtak. Ellenőrizd a Kapcsolatok / Modellek állapotát, majd válaszd a Folytatás gombot.'
  attention(s,turn,message)
  s.db.execute("UPDATE jobs SET status='blocked',error=?,finished=? WHERE id=?",(message,time.time(),job['id']));s.db.commit()
  s.job_stage(job['id'],'attention','Modellkapcsolat javítására vár',str(error)[:500]);return True
 delay=min(300,10*2**min(attempt-1,5));p.update(model_waits=attempt,retry_at=time.time()+delay,last_model_error=str(error)[:500],generation=dict(provider='scheduler',phase='Modellre vár · újrapróbálás '+str(delay)+' mp múlva'))
 changed=s.db.execute("UPDATE jobs SET status='queued',error='',started=NULL,finished=NULL,payload=? WHERE id=? AND status IN ('running','queued')",(json.dumps(p),job['id'])).rowcount
 if not changed:s.db.rollback();return False
 s.db.execute("UPDATE command_turns SET status='queued',response=? WHERE id=?",('A modellre várok; a kérésed és a már elvégzett olvasások megmaradtak. Automatikusan újrapróbálom, vagy választhatsz másik modellt.',turn));s.db.commit();s.job_stage(job['id'],'waiting_model','Modellre vár · automatikus újrapróbálás '+str(delay)+' mp múlva',str(error)[:500]);return True

def explicit_short_plan(s,pid,prompt,global_mode=False):
 """A typed existing workflow needs no agent discovery or repeated LLM planning.

 Only an explicit subject field or YouTube URL is accepted. Unclear prose still uses AI.
 """
 from request_intent import allow_shortcut
 if not allow_shortcut(prompt):return None
 from model_router import normalized
 p=normalized(prompt)
 # A request to configure THEN generate needs a validated change plan first.
 if re.search(r'\b(optimaliz\w*|modosits\w*|allits\w*|javits\w*|configure|optimize|fix)\b',p):return None
 from conversation_intake import continuation,query as natural_query,LAUNCH,VIDEO
 follow=continuation(s,pid,prompt)
 if re.search(r'\b(?:millions|billions|bevetel|nyereseg|befektet\w*|tradel\w*|tobb projekt|hosszu tavu)\b',p):return None
 if not follow and (not re.search(VIDEO,p) or not re.search(LAUNCH,p)):return None
 if re.search(r'\b(ne|nem|not|don.t)\s+(?:\w+\s+){0,2}(general|keszit|indit|start|generate|create)',p):return None
 # Setup requests and quoted examples are not an instruction to launch production.
 if re.search(r'\b(fejlesz\w*|alkalmazas\w*|appot|applikacio\w*|design|debug|script|kodot|build an app)\b',p):return None
 if prompt.rstrip().endswith('?') or re.search(r'\b(prompt|pelda|example|hiba|error|ha |amikor|when|if |mukodesi proba)\b',p):return None
 from clip_sources import youtube_id
 links=[]
 for found in re.finditer(r'https://(?:www\.)?(?:youtube\.com/watch\?[^\s]+|youtu\.be/[^\s]+|youtube\.com/shorts/[^\s]+)',prompt,re.I):
  link=found.group(0).rstrip('.,);')
  if youtube_id(link) and youtube_id(link) not in {youtube_id(x) for x in links}:links.append(link)
 topic=links[0] if links else None
 # The rest of the message (style, effects, "use both") is the editor's creative brief.
 brief=re.sub(r'\s+',' ',re.sub(r'https://\S+','',prompt)).strip(' .,\n')[:200]
 if not topic and follow:topic=follow['topic']
 if not topic:
  m=re.search(r'(?:f[oő]\s*t[eé]ma|topic)\s*:\s*(.+)',prompt,re.I|re.S)
  if not m:
   natural=re.search(r'(?:ami|amely)\s+(?:a[z]?\s+)?(.+?)\s+(?:r[oó]l|r[őö]l)\s+sz[oó]l',prompt,re.I)
   if natural and 'clip farm' in p:topic=natural.group(1).strip()
   else:topic=natural_query(prompt)
  else:topic=re.split(r'(?:[.!?]\s+|\n)(?=(?:a\s+)?(?:vide[oó]\w*|vicde[oó]\w*|hossz|felirat|caption|length|duration|poszt|publish))',m.group(1),maxsplit=1,flags=re.I)[0].strip(' .\n')
 if not isinstance(topic,str) or not 2<=len(topic)<=200:return None
 from app_capabilities import project_capabilities
 candidates=[p for p in s.rows('SELECT id,name FROM projects') if project_capabilities(s,p['id'])['shorts_available']]
 named=[x for x in candidates if x['name'].casefold() in prompt.casefold()]
 if len(named)==1:candidates=named
 elif not global_mode and any(x['id']==pid for x in candidates):candidates=[x for x in candidates if x['id']==pid]
 elif 'clip farm' not in p:candidates=[x for x in candidates if 'shorts' in x['name'].casefold()]
 if len(candidates)!=1:return None
 target=candidates[0]['id']
 from autonomous import role_agents
 try:role_agents(s,target)
 except ValueError:return None
 from short_style import requested_settings
 settings=requested_settings(follow['constraints_from']) if follow else {}
 settings.update(requested_settings(prompt))
 if 'min_seconds' in settings:settings['length_policy']='strict'
 if re.search(r'\b(ne|nem|not|don.t)\s+(poszt|tolts|toltse|publish|upload)',p):settings['publish_to_youtube']=False
 elif re.search(r'\b(posztold|posztolja|toltsd fel|toltse fel|publish|upload)\b',p):settings['publish_to_youtube']=True
 actions=[]
 if settings:actions.append(dict(type='short_style_save',project=target,settings=settings))
 action=dict(type='start_shorts',project=target,query=topic)
 if len(links)>1:action.update(sources=links[:5],query=brief if len(brief)>=8 else 'Combine every supplied video into one Short')
 if 'clip farm' in p and not re.search(r'\b(friss|aktualis|hir|hirek|trend|breaking|latest|current)\b',p):action['source_mode']='topic'
 actions.append(action)
 return actions

def continue_turn(s,turn,model='auto'):
 if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}',model):raise ValueError('Érvénytelen modellnév.')
 old=load(s,turn)
 s.db.execute('BEGIN IMMEDIATE')
 try:
  row=s.db.execute('SELECT * FROM command_turns WHERE id=?',(turn,)).fetchone()
  if not row or row['status'] not in ('attention','failed','queued'):raise ValueError('Csak tervezésre váró kérés folytatható.')
  if json.loads(row['actions']):raise ValueError('Ez a kérés végrehajtási tervet tartalmaz; ellenőrizd a műveleti naplót ismétlés előtt.')
  job=s.db.execute("SELECT * FROM jobs WHERE kind='command' AND json_extract(payload,'$.turn')=? ORDER BY created DESC LIMIT 1",(turn,)).fetchone()
  if not job or job['status']=='running':raise ValueError('A modell még ezen a kérésen dolgozik.')
  state=dict(cache=old.get('cache',{}),cycle=0,repeats=0)
  s.db.execute('INSERT INTO supervisor_sessions VALUES(?,?,?) ON CONFLICT(turn) DO UPDATE SET state=excluded.state,updated=excluded.updated',(turn,json.dumps(state,ensure_ascii=False),time.time()))
  from model_router import task_type
  p=json.loads(job['payload']);p.pop('retry_at',None);p.pop('model_waits',None);p['resumed_at']=time.time()
  task=task_type(row['prompt'],bool(p.get('image')))
  p['route']=dict(p.get('route',{}),task=task,engine='FLUX.1 Schnell' if task=='image' else model,model=model,automatic=model=='auto');p['generation']=dict(phase='A mentett kérés folytatása',provider='scheduler')
  s.db.execute("UPDATE jobs SET status='queued',error='',result='',started=NULL,finished=NULL,payload=? WHERE id=?",(json.dumps(p),job['id']))
  s.db.execute("UPDATE command_turns SET status='queued',response='A mentett adatokkal folytatom a kérésedet.',model=? WHERE id=?",(model,turn));s.db.commit();return job['id']
 except Exception:s.db.rollback();raise
