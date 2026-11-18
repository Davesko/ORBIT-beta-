"""What ORBIT learns about its user: the more it is used, the better it knows them.

After conversations a local model picks out lasting facts from the user's own words (never from pasted text, web pages,
emails or agents' output) and keeps them with what kind they are, how often they helped and when. For each new message
only the relevant ones go into the assistant's context. Everything is visible and editable on the Memória page, stays on
this Mac, and learning can be switched off.
"""
import json,math,re,struct,time,unicodedata,uuid

KINDS=('identity','preference','goal','fact','project')
WEIGHT=dict(identity=3,preference=2,goal=1.5,project=1,fact=1)
LIMIT=400
BATCH=10;LONG_PASTE=1500
PACE=90;EAGER=3;EAGER_PACE=45;HISTORY_DAYS=60;TICK=20;PROFILE='user-profile';PROFILE_EVERY=3600
EXPLICIT=re.compile(r'\b(mostantol|jegyezd meg|ne felejtsd|a nevem|engem .{0,20}hivnak|szolits|hivj|mindig|soha ne|remember|from now on|my name)\b')
SENSITIVE=re.compile(r'jelsz[aoó]|password|passcode|api[ -]?key|token|secret|titkos|kártyaszám|card number|bankszámla|iban|cvv|pin[- ]?k[oó]d|\b(?:\d[ -]?){13,19}\b|sk-[a-z0-9]{8,}|rk_(?:live|test)_',re.I)
_pace={'at':0}
EMBED_MODEL='qwen3-embedding:0.6b'
EMBED_BATCH=12
EMBED_RETRY=300


def schema(s):
 from commander import schema as base
 base(s)
 have={c[1] for c in s.db.execute('PRAGMA table_info(assistant_memory)')}
 for column,kind in (('kind',"TEXT DEFAULT 'preference'"),('source',"TEXT DEFAULT 'manual'"),('uses','INTEGER DEFAULT 0'),('last_used','REAL'),('created','REAL')):
  if column not in have:s.db.execute('ALTER TABLE assistant_memory ADD COLUMN '+column+' '+kind)
 s.db.execute('CREATE TABLE IF NOT EXISTS memory_seen(turn TEXT PRIMARY KEY,at REAL)')
 s.db.execute('CREATE TABLE IF NOT EXISTS memory_settings(key TEXT PRIMARY KEY,value TEXT)');s.db.commit()
 if not s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_vectors'").fetchone():vector_schema(s)

def vector_schema(s):
 s.db.executescript("""
 CREATE TABLE IF NOT EXISTS memory_vectors(key TEXT PRIMARY KEY, model TEXT NOT NULL, port INTEGER NOT NULL, vector BLOB NOT NULL);
 CREATE TRIGGER IF NOT EXISTS memory_vector_delete AFTER DELETE ON assistant_memory
 BEGIN DELETE FROM memory_vectors WHERE key=OLD.key; END;
 CREATE TRIGGER IF NOT EXISTS memory_vector_update AFTER UPDATE OF content,display ON assistant_memory
 BEGIN DELETE FROM memory_vectors WHERE key=OLD.key; END;
 """)

def pending_vectors(s):
 return s.rows("""SELECT m.key,m.content,m.display FROM assistant_memory m
 LEFT JOIN memory_vectors v ON m.key=v.key AND v.model=?
 WHERE m.key!=? AND v.key IS NULL ORDER BY m.updated DESC LIMIT ?""",(EMBED_MODEL,PROFILE,EMBED_BATCH))

def embed(port,inputs,timeout):
 from model_hub import raw
 reply=raw(port,'api/embed',dict(model=EMBED_MODEL,input=inputs,keep_alive='1m'),timeout=timeout)
 vectors=reply['embeddings']
 if len(vectors)!=len(inputs):raise ValueError('Hiányos embedding válasz.')
 result=[]
 for v in vectors:
  if not 1<=len(v)<=4096:raise ValueError('Érvénytelen embedding méret.')
  norm=math.sqrt(sum(x*x for x in v))
  if not norm or not math.isfinite(norm):raise ValueError('Érvénytelen embedding.')
  result.append([x/norm for x in v])
 return result

def resident(port,name):
 """Whether the model is loaded right now; asking costs nothing and loads nothing."""
 from model_hub import raw
 try:return any(name in (m.get('name'),m.get('model')) for m in raw(port,'api/ps',timeout=.5).get('models',[]))
 except Exception:return False

def index_vectors(s):
 from model_hub import models
 schema(s)
 entry=next((m for m in models() if m.get('name')==EMBED_MODEL),None)
 if not entry:return 'A jelentésalapú kereséshez telepítsd a Qwen3 Embedding 0.6B modellt.'
 rows=pending_vectors(s);port=entry['port']
 if not rows:return 'A memória indexe naprakész.'
 vectors=embed(port,[r['display']+'\n'+r['content'] for r in rows],20)
 # A simultaneous edit/delete must never restore an obsolete vector.
 for row,v in zip(rows,vectors):
  s.db.execute("""INSERT OR REPLACE INTO memory_vectors(key,model,port,vector)
   SELECT key,?,?,? FROM assistant_memory WHERE key=? AND content=? AND display=?""",
   (EMBED_MODEL,port,struct.pack('<%sf'%len(v),*v),row['key'],row['content'],row['display']))
 s.db.commit()
 return 'Memóriaindex frissítve.'

def semantic_scores(s,prompt):
 if len(prompt.strip())<8 or SENSITIVE.search(prompt):return {}
 rows=s.rows('SELECT key,port,vector FROM memory_vectors WHERE model=?',(EMBED_MODEL,))
 if not rows:return {}
 # This call is optional and stays on loopback. A cold/missing model falls back to keywords.
 try:
  ports=sorted({r['port'] for r in rows},reverse=True)
  # The model server holds ONE model (OLLAMA_MAX_LOADED_MODELS=1): asking a cold embedding model
  # unloaded the chat model, then gave up after 1.5 s. Every chat round paid a full reload of a
  # 16 GB model for nothing (61 times on 6-7 Nov). Only a resident embedding model is asked.
  if not resident(ports[0],EMBED_MODEL):return {}
  query='Instruct: Retrieve relevant saved facts, preferences, and goals about the user.\nQuery: '+prompt[:1600]
  q=embed(ports[0],[query],1.5)[0]
 except (OSError,ValueError,KeyError,TypeError):return {}
 fmt='<%sf'%len(q)
 return {r['key']:sum(a*b for a,b in zip(q,struct.unpack(fmt,r['vector']))) for r in rows if len(r['vector'])==4*len(q)}

def enabled(s):
 schema(s);row=s.db.execute("SELECT value FROM memory_settings WHERE key='learning'").fetchone()
 return not row or row[0]!='off'

def words(text):
 """Rough stems, enough to match Hungarian and English endings without a language model."""
 plain=''.join(c for c in unicodedata.normalize('NFKD',str(text).casefold()) if not unicodedata.combining(c))
 return {w[:5] for w in re.findall(r'[a-z0-9]{4,}',plain)}

def recall(s,prompt='',limit=14,count=True,now=None,relevant_only=False,graph_limit=0):
 """The memories worth knowing for this message: what it talks about first, then who the user is."""
 schema(s);now=now or time.time();wanted=words(prompt);scored=[];profile=None;semantic=semantic_scores(s,prompt)
 identity_request=bool(wanted&words('nevem hivnak rolam szolits'))
 for row in s.rows('SELECT key,content,display,kind,source,uses,last_used,updated FROM assistant_memory'):
  if row['key']==PROFILE:
   profile=row;continue
  overlap=len(wanted&words(row['content']+' '+row['display']+' '+row['key']))
  age=(now-(row['last_used'] or row['updated'] or now))/86400
  relevance=max(0,semantic.get(row['key'],0)-.20)*18
  scored.append((overlap*3+relevance+WEIGHT.get(row['kind'],1)+min(row['uses'] or 0,10)*.1-min(age,60)*.01,bool(overlap or relevance or identity_request and row['kind']=='identity'),row))
 scored.sort(key=lambda item:-item[0]);chosen=[item for item in scored if item[1] or not relevant_only][:limit]
 if count:
  hits=[row['key'] for _,overlap,row in chosen if overlap]
  if hits:
   s.db.executemany('UPDATE assistant_memory SET uses=COALESCE(uses,0)+1,last_used=? WHERE key=?',[(now,k) for k in hits]);s.db.commit()
 # Who the user is goes first, whatever the message is about.
 result=([dict(kind='profile',content=profile['content'][:900])] if profile and (not relevant_only or wanted&words(' '.join([profile['content'],profile['display']])) or wanted&words('nevem szolits emlekszel rolam preferencia')) else [])+[dict(kind=row['kind'],content=row['content'][:350]) for _,_,row in chosen]
 if graph_limit and chosen:
  from memory_graph import related
  seeds=[row['key'] for _,relevant,row in chosen if relevant]
  if seeds:result.extend(related(s,prompt,limit=graph_limit,seeds=seeds))
 return result

def similar(a,b):
 x,y=words(a),words(b)
 return bool(x and y) and len(x&y)/len(x|y)>=.7

def remember(s,key,content,display,kind='fact',source='auto',now=None,correction_at=None):
 """A new memory, or a stronger old one. Returns False when nothing new was stored."""
 schema(s);now=now or time.time();content=' '.join(str(content or '').split())[:600];display=' '.join(str(display or content).split())[:600]
 kind=kind if kind in KINDS else 'fact';key=re.sub(r'[^a-z0-9_-]+','-',str(key or '').casefold()).strip('-')[:80] or uuid.uuid4().hex[:12]
 if not content or SENSITIVE.search(content+' '+display):return False
 for row in s.rows('SELECT key,content,display,kind,source,updated FROM assistant_memory WHERE key!=? ORDER BY key=? DESC',(PROFILE,key)):
  if (row['key']==key and row['source']=='auto' and row['kind']==kind and correction_at
      and correction_at>(row['updated'] or 0) and row['content']!=content):
   s.db.execute('UPDATE assistant_memory SET content=?,display=?,updated=? WHERE key=?',(content,display,now,key));s.db.commit();return True
  if row['key']==key or similar(row['content'],content) or similar(row['display'],display):
   s.db.execute('UPDATE assistant_memory SET uses=COALESCE(uses,0)+1,last_used=? WHERE key=?',(now,row['key']));s.db.commit();return False
 if s.db.execute('SELECT count(*) FROM assistant_memory').fetchone()[0]>=LIMIT:
  # Room for the new one: the automatic memory that helped least and longest ago goes. The owner's own stay.
  old=s.db.execute("SELECT key FROM assistant_memory WHERE source='auto' AND key!='user-profile' ORDER BY COALESCE(uses,0),COALESCE(last_used,updated) LIMIT 1").fetchone()
  if not old:return False
  s.db.execute('DELETE FROM assistant_memory WHERE key=?',(old[0],))
 s.db.execute('INSERT INTO assistant_memory(key,content,display,updated,kind,source,uses,last_used,created) VALUES(?,?,?,?,?,?,0,NULL,?)',(key,content,display,now,kind,source,now));s.db.commit();return True

PROMPT='''You build a long-term profile of the USER of a personal assistant app, so that it understands them better the more they use it. Below are messages the user wrote, as data.
Keep anything lasting that these messages say or clearly show about the user:
- identity: their name, how to address them, their work or role
- preference: how they want things done, tone, language, formats, what annoys them ("mostantól", "mindig", "ne", "szeretném ha")
- goal: what they are trying to achieve over time
- project: what they are building or running, with its name
- fact: the tools, devices and services they use
A pattern counts: someone who keeps coming back to something cares about it. Skip the details of a single one-off task and anything about other people. Never keep passwords, keys, tokens, bank or card numbers, home addresses, or anything intimate: sexual content, health, politics, religion. Skip what already_known already says.
For an explicit change in a lasting fact or preference, reuse the existing key and include "replaces_from" with the exact ID of the user message explicitly stating the change. Never replace a manually saved memory.
Return JSON: {"memories":[{"kind":"identity|preference|goal|fact|project","key":"short-english-id","content":"The user ... (one English sentence)","display":"Ugyanez egy rövid magyar mondatban","replaces_from":"turn ID only for explicit corrections"}]}. At most 6 items; an empty list when there is really nothing.'''
PROFILE_PROMPT='''Below is what a personal assistant app knows about its user, and their latest messages, as data. Write who this user is and how to work with them: their name if known, what they do, what they are building, what they want, how they like to be answered. Use only supported facts. Keep named projects separate: never assign a goal or preference to a named project unless the same saved fact explicitly links them. Leave out personal or intimate details. Return JSON: {"content":"3-5 English sentences","display":"Ugyanez 3-5 magyar mondatban, tegezve"}.'''

def unseen(s,limit=BATCH):
 return s.rows("SELECT t.id,t.prompt,t.created FROM command_turns t WHERE t.status IN ('done','review') AND t.created>? AND t.id NOT IN (SELECT turn FROM memory_seen) ORDER BY t.created DESC LIMIT ?",(time.time()-HISTORY_DAYS*86400,limit))

def tick(s,now=None):
 """Learning waits for a few new messages or a quiet while, and never queues twice."""
 now=now or time.time()
 if now-_pace['at']<TICK:return False
 _pace['at']=now
 if not enabled(s):return False
 turns=unseen(s,EAGER)
 if not turns:
  import memory_graph
  return schedule_index(s,now) or memory_graph.schedule(s,now)
 retry=s.db.execute("SELECT value FROM memory_settings WHERE key='learn_retry'").fetchone()
 if retry and now<float(retry[0]):return schedule_index(s,now)
 from model_router import normalized
 last=s.db.execute("SELECT value FROM memory_settings WHERE key='learned_at'").fetchone();since=now-float(last[0]) if last else PACE
 # "From now on call me..." is learned at once; a long history a little at a time, next to the real work.
 told=any(EXPLICIT.search(normalized(t['prompt'])) for t in turns)
 if not told and since<(EAGER_PACE if len(turns)>=EAGER else PACE):return False
 if s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='memory_learn'").fetchone():return False
 agent=s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
 if not agent:return False
 s.enqueue(agent[0],'Memória frissítése','assist',payload=dict(task='memory_learn',local_only=True));return True

def schedule_index(s,now):
 last=s.db.execute("SELECT value FROM memory_settings WHERE key='index_attempt'").fetchone()
 if last and now-float(last[0])<EMBED_RETRY:return False
 if not pending_vectors(s) or s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='memory_index'").fetchone():return False
 agent=s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
 if not agent:return False
 s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('index_attempt',?)",(str(now),));s.db.commit()
 s.enqueue(agent[0],'Memóriakeresés frissítése','assist',payload=dict(task='memory_index',local_only=True))
 return True

def learn(s,job):
 """The job behind tick: one local model call. A failure leaves the messages for the next round."""
 from studio import local_api
 from assist_jobs import chat_model
 turns=unseen(s);now=time.time()
 from model_router import normalized
 eligible={t['id']:t for t in turns if len(t['prompt'])<=LONG_PASTE and not SENSITIVE.search(t['prompt'])}
 own=[t['prompt'] for t in eligible.values()]
 added=0;fresh=None
 if own:
  known=s.rows('SELECT key,display,source FROM assistant_memory WHERE key!=? ORDER BY COALESCE(last_used,updated) DESC LIMIT 30',(PROFILE,))
  user_messages=[dict(id=t['id'],text=t['prompt']) for t in eligible.values()]
  try:response=local_api('ollama','api/chat',dict(model=chat_model(),_orbit_job=job['id'],messages=[dict(role='system',content=PROMPT),dict(role='user',content=json.dumps(dict(user_messages=user_messages,already_known=known),ensure_ascii=False))],stream=False,format='json',think=False,keep_alive='5m',options=dict(num_ctx=4096,num_predict=1400,temperature=.1)),timeout=240)
  except ValueError as error:
   # Six items in two languages did not fit the old 500-token answer; a cut answer is retried later.
   if 'túl hosszú' not in str(error):raise
   response=None
  items=parse(response) if response else None
  if items is None:
   s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('learn_retry',?)",(str(now+EMBED_RETRY),));s.db.commit()
   return 'A memóriamodell hibás választ adott. Az üzenetek megmaradtak újrapróbálásra.'
  for item in items:
   turn=item.get('replaces_from')
   evidence=eligible.get(turn) if isinstance(turn,str) else None
   correction=evidence['created'] if evidence and EXPLICIT.search(normalized(evidence['prompt'])) else None
   if remember(s,item.get('key'),item.get('content'),item.get('display'),item.get('kind'),correction_at=correction):
    added+=1;fresh=fresh or item.get('display')
 s.db.executemany('INSERT OR IGNORE INTO memory_seen VALUES(?,?)',[(t['id'],now) for t in turns])
 s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('learned_at',?)",(str(now),))
 # Said just now: the chat tells the owner it was noted. Reading the old history stays quiet.
 if fresh and any(t['created']>now-900 for t in turns):s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('last_note',?)",(json.dumps(dict(text=str(fresh)[:200],at=now),ensure_ascii=False),))
 s.db.commit()
 if added or not s.db.execute('SELECT 1 FROM assistant_memory WHERE key=?',(PROFILE,)).fetchone():write_profile(s,job,own,now)
 if added:
  # New memories go into the graph in the same round: their entities and relations are known at once.
  import memory_graph
  try:memory_graph.extract(s,job)
  except Exception:pass  # optional: the background round links them later
 return 'Memória frissítve: '+str(added)+' új emlék.'

def write_profile(s,job,recent,now=None):
 """A short portrait from everything known so far. Once the owner has edited it, it is theirs."""
 from studio import local_api
 from assist_jobs import chat_model
 now=now or time.time();old=s.db.execute('SELECT source,updated FROM assistant_memory WHERE key=?',(PROFILE,)).fetchone()
 if old and (old['source']=='manual' or now-(old['updated'] or 0)<PROFILE_EVERY):return False
 known=[m['content'] for m in s.rows('SELECT content FROM assistant_memory WHERE key!=? ORDER BY COALESCE(uses,0) DESC,updated DESC LIMIT 40',(PROFILE,))]
 if not known:return False
 try:r=local_api('ollama','api/chat',dict(model=chat_model(),_orbit_job=job['id'],messages=[dict(role='system',content=PROFILE_PROMPT),dict(role='user',content=json.dumps(dict(known=known,latest_messages=recent[:10]),ensure_ascii=False))],stream=False,format='json',think=False,keep_alive='5m',options=dict(num_ctx=4096,num_predict=900,temperature=.2)),timeout=240)
 except ValueError as error:
  if 'túl hosszú' in str(error):return False
  raise
 try:
  item=json.loads(r['message']['content'])
  content=' '.join(str(item['content']).split())[:900];display=' '.join(str(item['display']).split())[:900]
 except (KeyError,TypeError,ValueError):return False
 if not content or not display or SENSITIVE.search(content+' '+display):return False
 s.db.execute('INSERT OR REPLACE INTO assistant_memory(key,content,display,updated,kind,source,uses,created) VALUES(?,?,?,?,?,?,0,?)',(PROFILE,content,display,now,'identity','auto',now));s.db.commit();return True

def note(s):
 """What was just noted from the owner's last words, for the chat."""
 schema(s);row=s.db.execute("SELECT value FROM memory_settings WHERE key='last_note'").fetchone()
 try:return json.loads(row[0]) if row else None
 except ValueError:return None

def parse(response):
 try:
  raw=response['message']['content'] if isinstance(response,dict) else str(response)
  items=json.loads(raw).get('memories')
 except (KeyError,TypeError,ValueError,AttributeError):return None
 return [i for i in items if isinstance(i,dict)][:5] if isinstance(items,list) else None

def tidy(s):
 """Merges memories that say the same thing, keeping the one used most."""
 schema(s);rows=s.rows('SELECT key,content,display,uses FROM assistant_memory WHERE key!=? ORDER BY COALESCE(uses,0) DESC,COALESCE(last_used,updated) DESC',(PROFILE,));kept=[];gone=0
 for row in rows:
  twin=next((k for k in kept if similar(k['content'],row['content']) or similar(k['display'],row['display'])),None)
  if twin:
   s.db.execute('UPDATE assistant_memory SET uses=COALESCE(uses,0)+? WHERE key=?',(row['uses'] or 0,twin['key']));s.db.execute('DELETE FROM assistant_memory WHERE key=?',(row['key'],));gone+=1
  else:kept.append(row)
 s.db.commit();return dict(merged=gone,message=(str(gone)+' ismétlődő emléket összevontam.') if gone else 'Nem találtam ismétlődést.')

def listing(s,query='',kind=''):
 schema(s);rows=s.rows('SELECT key,content,display,kind,source,uses,last_used,updated,created FROM assistant_memory ORDER BY COALESCE(last_used,updated) DESC')
 profile=next((r for r in rows if r['key']==PROFILE),None);rows=[r for r in rows if r['key']!=PROFILE]
 last=s.db.execute("SELECT value FROM memory_settings WHERE key='learned_at'").fetchone()
 counts={k:sum(r['kind']==k for r in rows) for k in KINDS};total=len(rows)
 if kind in KINDS:rows=[r for r in rows if r['kind']==kind]
 if str(query or '').strip():
  q=str(query).casefold();rows=[r for r in rows if q in r['display'].casefold() or q in r['content'].casefold()]
 waiting=s.db.execute("SELECT count(*) FROM command_turns WHERE status IN ('done','review') AND created>? AND id NOT IN (SELECT turn FROM memory_seen)",(time.time()-HISTORY_DAYS*86400,)).fetchone()[0]
 indexed=s.db.execute('SELECT count(*) FROM memory_vectors WHERE model=?',(EMBED_MODEL,)).fetchone()[0]
 return dict(embedding=dict(model=EMBED_MODEL,indexed=indexed),enabled=enabled(s),total=total,counts=counts,limit=LIMIT,memories=rows,waiting=waiting,profile=profile,learned_at=float(last[0]) if last else None)

def save(s,key,display,kind):
 """The owner's own words, kept as they are."""
 schema(s);display=' '.join(str(display or '').split())
 if not 2<=len(display)<=600:raise ValueError('Írj be egy rövid emléket.')
 if SENSITIVE.search(display):raise ValueError('Jelszót, kulcsot vagy bankkártya-adatot nem tárolok a memóriában.')
 kind=kind if kind in KINDS else 'fact';now=time.time()
 if key and s.db.execute('UPDATE assistant_memory SET display=?,content=?,kind=?,source=?,updated=? WHERE key=?',(display,display,kind,'manual',now,key)).rowcount:
  s.db.commit();return dict(key=key)
 key=uuid.uuid4().hex[:12];s.db.execute('INSERT INTO assistant_memory(key,content,display,updated,kind,source,uses,created) VALUES(?,?,?,?,?,?,0,?)',(key,display,display,now,kind,'manual',now));s.db.commit();return dict(key=key)

def dispatch(s,op,args=None):
 args=args or {}
 if op=='memory_list':return listing(s,args.get('query'),args.get('kind'))
 if op=='memory_graph':
  from memory_graph import build
  return build(s,str(args.get('query') or '')[:160],args.get('kind') or '',args.get('project') or '')
 if op=='memory_relink':
  # Read every memory again into the graph (after a better model, or on request).
  import memory_graph
  memory_graph.schema(s);s.db.execute('DELETE FROM memory_graph_done');s.db.execute("DELETE FROM memory_settings WHERE key='graph_retry'");s.db.commit()
  return dict(pending=len(memory_graph.pending(s,500)))
 if op=='memory_save':return save(s,args.get('key'),args.get('display'),args.get('kind'))
 if op=='memory_delete':
  schema(s);s.db.execute('DELETE FROM assistant_memory WHERE key=?',(str(args.get('key') or ''),));s.db.commit();return dict(deleted=True)
 if op=='memory_enable':
  schema(s);s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('learning',?)",('on' if args.get('on') is True else 'off',));s.db.commit();return dict(enabled=enabled(s))
 if op=='memory_tidy':return tidy(s)
 raise ValueError('Ismeretlen memóriaművelet.')
