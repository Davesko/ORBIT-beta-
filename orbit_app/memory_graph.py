"""The owner's memory as a temporal knowledge graph (the approach of Zep/Graphiti and Mem0's graph memory,
built independently and kept on this Mac).

Nodes are entities: the owner ("user"), people, projects, organizations, tools, places and topics. Edges are
typed relations from a fixed vocabulary (works_on, uses, prefers, wants...), each carrying the memory it came
from. A changed single-valued fact (where the owner lives) does not overwrite the old edge: the old one gets an
invalid_at time and stays visible as "korábban". Every memory also records which entities it mentions.

Learning has two layers:
- instantly, without a model: ORBIT project names found in a memory become project entities;
- in the background, with the local model: entities and relations are extracted from each memory (new ones as
  they are learned, older ones a batch at a time while the model is free).

Recall walks the graph: entities named in the message, then their direct neighbours, then the memories that
mention any of them. The owner is never used as a hop, since every memory connects through them."""
import hashlib,json,re,time,unicodedata

KINDS={'user':'Te','person':'Személy','project':'Projekt','organization':'Szervezet','tool':'Eszköz','place':'Hely','topic':'Téma'}
RELATIONS={
 'named':'neve','is':'egy','works_as':'foglalkozása','works_on':'dolgozik rajta','builds':'építi','uses':'használja',
 'prefers':'előnyben részesíti','likes':'kedveli','dislikes':'nem kedveli','wants':'célja','lives_in':'itt él',
 'located_in':'itt található','part_of':'része','about':'témája','publishes_on':'itt publikál','sells_on':'itt árul',
 'owns':'birtokolja','knows':'ismeri','related_to':'kapcsolódik'}
# One value at a time: a new one ends the old edge instead of standing beside it.
FUNCTIONAL={'named','lives_in','located_in'}
# A memory's kind says how the owner relates to what it mentions when the model named no relation.
KIND_RELATION={'identity':'is','preference':'prefers','goal':'wants','project':'works_on','fact':'related_to'}
USER_NAMES={'user','theuser','owner','felhasznalo','te','en','me','i','az user'}
BATCH=8

PROMPT='''Turn each saved memory about a user into a small knowledge graph. Use only what the memory states.
Entities: short canonical names (max 40 characters), proper nouns as written (e.g. "GTA 6", "YouTube Shorts", "Telegram").
Entity types: person, project, organization, tool, place, topic. The user themself is always the entity "user".
Relations: from one entity to another, relation from this list only: '''+', '.join(RELATIONS)+'''.
Use "named" only for the user's own name. Reuse a name from existing_entities, exactly as written, whenever it means the same thing (one entity for "9:16 videos" and "9:16 vertical videos"). At most 4 entities and 3 relations per memory. Skip vague words (thing, content, video in general).
Return JSON: {"items":[{"key":"memory key","entities":[{"name":"...","type":"..."}],"relations":[{"from":"user or entity name","relation":"...","to":"entity name"}]}]}'''


def norm(name):
 plain=''.join(c for c in unicodedata.normalize('NFKD',str(name or '').casefold()) if not unicodedata.combining(c))
 return re.sub(r'[^a-z0-9]+','',plain)


def schema(s):
 if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_relations'").fetchone():return
 s.db.executescript("""
 CREATE TABLE IF NOT EXISTS memory_entities(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,aliases TEXT NOT NULL DEFAULT '[]',project TEXT,created REAL,updated REAL);
 CREATE TABLE IF NOT EXISTS memory_mentions(memory TEXT,entity TEXT,PRIMARY KEY(memory,entity));
 CREATE INDEX IF NOT EXISTS memory_mentions_entity ON memory_mentions(entity);
 CREATE TABLE IF NOT EXISTS memory_relations(id INTEGER PRIMARY KEY,src TEXT NOT NULL,rel TEXT NOT NULL,dst TEXT NOT NULL,memory TEXT,valid_from REAL,invalid_at REAL,created REAL,UNIQUE(src,rel,dst,memory));
 CREATE INDEX IF NOT EXISTS memory_relations_src ON memory_relations(src);
 CREATE INDEX IF NOT EXISTS memory_relations_dst ON memory_relations(dst);
 CREATE TABLE IF NOT EXISTS memory_graph_done(key TEXT PRIMARY KEY,hash TEXT,at REAL);
 CREATE TABLE IF NOT EXISTS memory_events(id INTEGER PRIMARY KEY,at REAL,kind TEXT,memory TEXT,detail TEXT);
 CREATE TRIGGER IF NOT EXISTS memory_graph_forget AFTER DELETE ON assistant_memory BEGIN
   DELETE FROM memory_mentions WHERE memory=OLD.key;
   DELETE FROM memory_relations WHERE memory=OLD.key;
   DELETE FROM memory_graph_done WHERE key=OLD.key;
 END;
 """)
 now=time.time()
 s.db.execute("INSERT OR IGNORE INTO memory_entities(id,name,kind,aliases,created,updated) VALUES('user','Te','user','[]',?,?)",(now,now))
 s.db.commit()


def digest(row):return hashlib.sha1(((row['content'] or '')+'\n'+(row['display'] or '')).encode()).hexdigest()[:16]


def event(s,kind,memory,detail):
 s.db.execute('INSERT INTO memory_events(at,kind,memory,detail) VALUES(?,?,?,?)',(time.time(),kind,memory,str(detail)[:300]))


def _entities(s):
 rows=s.rows('SELECT id,name,kind,aliases,project FROM memory_entities')
 for r in rows:r['aliases']=set(json.loads(r['aliases'] or '[]'))|{norm(r['name'])}
 return rows


def resolve(s,name,kind='topic',now=None,known=None):
 """The entity this name means: the owner, an ORBIT project, an existing entity or a new one."""
 n=norm(name);now=now or time.time()
 if not n or len(n)<2:return None
 known=known if known is not None else _entities(s)
 user=next(r for r in known if r['id']=='user')
 if n in USER_NAMES or n in user['aliases'] or kind=='person' and norm(' '.join(reversed(str(name).split()))) in user['aliases']:return 'user'
 hit=next((r for r in known if n in r['aliases']),None)
 if hit:return hit['id']
 project=next((p for p in s.rows("SELECT id,name FROM projects WHERE id!='universe'") if norm(p['name'])==n),None)
 kind=kind if kind in KINDS and kind!='user' else 'topic'
 eid=('project:'+project['id']) if project else 'e:'+n[:40]
 if project:kind='project'
 label=' '.join(str(name).split())[:40]
 if s.db.execute('SELECT 1 FROM memory_entities WHERE id=?',(eid,)).fetchone():return eid
 s.db.execute('INSERT INTO memory_entities(id,name,kind,aliases,project,created,updated) VALUES(?,?,?,?,?,?,?)',
              (eid,project['name'] if project else label,kind,json.dumps([n]),project['id'] if project else None,now,now))
 known.append(dict(id=eid,name=label,kind=kind,aliases={n},project=project['id'] if project else None))
 return eid


def projects_in(s,text):
 body=' '+re.sub(r'[^a-z0-9]+',' ',''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c)))+' '
 found=[]
 for p in s.rows("SELECT id,name FROM projects WHERE id!='universe' AND length(name)>=3"):
  words=' '+re.sub(r'[^a-z0-9]+',' ',''.join(c for c in unicodedata.normalize('NFKD',p['name'].casefold()) if not unicodedata.combining(c))).strip()+' '
  if words.strip() and words in body:found.append(p['name'])
 return found


def link(s,key,entities,relations,now=None):
 """Stores what one memory says. Edges this memory no longer supports end now; nothing is silently lost."""
 from memory_brain import SENSITIVE
 schema(s);now=now or time.time()
 row=s.db.execute('SELECT key,content,display,kind FROM assistant_memory WHERE key=?',(key,)).fetchone()
 if not row:return 0
 text=(row['content'] or '')+' '+(row['display'] or '')
 known=_entities(s);mentioned=set();kept=set()
 if not SENSITIVE.search(text):
  for r in [r for r in (relations or []) if isinstance(r,dict) and r.get('relation')=='named']:
   # The owner's name becomes their label and aliases (both name orders), never a separate person.
   name=' '.join(str(r.get('to') or '').split())[:40]
   if len(norm(name))>=2:
    user=next(x for x in known if x['id']=='user');parts=name.split()
    aliases=sorted((user['aliases']-{norm(user['name'])})|{norm(name),norm(' '.join(reversed(parts)))}|{norm(x) for x in parts if len(norm(x))>=3})
    s.db.execute("UPDATE memory_entities SET name=?,aliases=?,updated=? WHERE id='user'",(name,json.dumps(aliases),now))
    user['aliases']|=set(aliases);user['name']=name
    # A person read earlier under the owner's name was the owner all along: fold it in.
    for twin in [x for x in known if x['kind']=='person' and x['aliases']&user['aliases']]:
     for col in ('src','dst'):s.db.execute(f"UPDATE OR IGNORE memory_relations SET {col}='user' WHERE {col}=?",(twin['id'],))
     s.db.execute('DELETE FROM memory_relations WHERE src=? OR dst=?',(twin['id'],twin['id']))
     s.db.execute("UPDATE OR IGNORE memory_mentions SET entity='user' WHERE entity=?",(twin['id'],));s.db.execute('DELETE FROM memory_mentions WHERE entity=?',(twin['id'],))
     s.db.execute("DELETE FROM memory_mentions WHERE entity='user'");s.db.execute('DELETE FROM memory_entities WHERE id=?',(twin['id'],));known.remove(twin)
  for e in list(entities or [])[:6]+[dict(name=p,type='project') for p in projects_in(s,text)]:
   if isinstance(e,dict) and isinstance(e.get('name'),str):
    eid=resolve(s,e['name'],e.get('type'),now,known)
    if eid:mentioned.add(eid)
  for r in list(relations or [])[:4]:
   if not isinstance(r,dict) or r.get('relation') not in RELATIONS:continue
   rel=r['relation']
   if rel=='named':continue
   src=resolve(s,r.get('from'),'topic',now,known);dst=resolve(s,r.get('to'),'topic',now,known)
   if not src or not dst or src==dst:continue
   mentioned.update({src,dst}-{'user'});kept.add((src,rel,dst))
   if rel in FUNCTIONAL:
    for old in s.rows('SELECT id,dst FROM memory_relations WHERE src=? AND rel=? AND dst!=? AND invalid_at IS NULL',(src,rel,dst)):
     s.db.execute('UPDATE memory_relations SET invalid_at=? WHERE id=?',(now,old['id']))
     event(s,'superseded',key,f'{src} {rel}: {old["dst"]} → {dst}')
   fresh=s.db.execute('INSERT OR IGNORE INTO memory_relations(src,rel,dst,memory,valid_from,invalid_at,created) VALUES(?,?,?,?,?,NULL,?)',(src,rel,dst,key,now,now)).rowcount
   if not fresh:s.db.execute('UPDATE memory_relations SET invalid_at=NULL WHERE src=? AND rel=? AND dst=? AND memory=?',(src,rel,dst,key))
 mentioned.discard('user')
 for old in s.rows('SELECT id,src,rel,dst FROM memory_relations WHERE memory=? AND invalid_at IS NULL',(key,)):
  if (old['src'],old['rel'],old['dst']) not in kept and relations is not None:s.db.execute('UPDATE memory_relations SET invalid_at=? WHERE id=?',(now,old['id']))
 if relations is not None or mentioned:
  s.db.execute('DELETE FROM memory_mentions WHERE memory=?',(key,))
  s.db.executemany('INSERT OR IGNORE INTO memory_mentions VALUES(?,?)',[(key,e) for e in mentioned])
 if relations is not None:
  s.db.execute('INSERT OR REPLACE INTO memory_graph_done VALUES(?,?,?)',(key,digest(row),now))
  event(s,'linked',key,', '.join(sorted(mentioned))[:300] or 'nincs entitás')
 s.db.commit()
 return len(mentioned)


def pending(s,limit=BATCH):
 schema(s)
 rows=s.rows("SELECT m.key,m.content,m.display,d.hash FROM assistant_memory m LEFT JOIN memory_graph_done d ON d.key=m.key WHERE m.key!='user-profile' ORDER BY m.updated DESC")
 return [r for r in rows if r['hash']!=digest(r)][:limit]


def instant(s):
 """The model-free layer, for memories the model has not read yet: their ORBIT project mentions."""
 schema(s)
 for r in s.rows("SELECT m.key FROM assistant_memory m WHERE m.key!='user-profile' AND m.key NOT IN (SELECT key FROM memory_graph_done) AND m.key NOT IN (SELECT memory FROM memory_mentions)"):
  link(s,r['key'],[],None)


def parse(raw):
 try:items=json.loads(raw).get('items')
 except (TypeError,ValueError,AttributeError):return None
 return [i for i in items if isinstance(i,dict) and isinstance(i.get('key'),str)] if isinstance(items,list) else None


def extract(s,job,rows=None):
 """One local-model call for a batch of memories. Returns how many were linked; None when the model failed."""
 from studio import local_api
 from assist_jobs import chat_model
 rows=rows if rows is not None else pending(s)
 if not rows:return 0
 data=[dict(key=r['key'],text=r['content']) for r in rows]
 try:response=local_api('ollama','api/chat',dict(model=chat_model(),_orbit_job=job['id'],messages=[dict(role='system',content=PROMPT),dict(role='user',content=json.dumps(dict(existing_entities=[e['name'] for e in s.rows("SELECT name FROM memory_entities WHERE id!='user' ORDER BY updated DESC LIMIT 80")],memories=data),ensure_ascii=False))],stream=False,format='json',think=False,keep_alive='5m',options=dict(num_ctx=4096,num_predict=1800,temperature=0)),timeout=240)
 except ValueError as error:
  if 'túl hosszú' in str(error):return None
  raise
 items=parse(response.get('message',{}).get('content','') if isinstance(response,dict) else '')
 if items is None:return None
 by={i['key']:i for i in items};done=0
 for r in rows:
  item=by.get(r['key'],{})
  ents=[e for e in item.get('entities',[]) if isinstance(e,dict)] if isinstance(item.get('entities'),list) else []
  rels=[x for x in item.get('relations',[]) if isinstance(x,dict)] if isinstance(item.get('relations'),list) else []
  # Nothing named still counts as read: the memory then belongs to the owner through its kind.
  link(s,r['key'],ents,rels);done+=1
 return done


def run_job(s,job):
 rows=pending(s)
 if not rows:return 'A memóriagráf naprakész.'
 done=extract(s,job,rows)
 if done is None:
  s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('graph_retry',?)",(str(time.time()+600),));s.db.commit()
  return 'A memóriagráf most nem frissült; később újrapróbálom.'
 return f'Memóriagráf frissítve: {done} emlék összekötve.'


def schedule(s,now):
 """Queues one background linking round while older memories wait, never two at once."""
 schema(s)
 retry=s.db.execute("SELECT value FROM memory_settings WHERE key='graph_retry'").fetchone()
 if retry and now<float(retry[0]):return False
 if not pending(s,1):return False
 if s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task') IN ('memory_graph','memory_learn')").fetchone():return False
 agent=s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
 if not agent:return False
 s.enqueue(agent[0],'Memóriagráf építése','assist',payload=dict(task='memory_graph',local_only=True));return True


def sentence(s,src,rel,dst,names):
 who=lambda e:'the user' if e=='user' else names.get(e,e)
 return f"{who(src)} {rel.replace('_',' ')} {who(dst)}"


def related(s,prompt,*,limit,seeds):
 """Graph recall: entities named in the message and in the seed memories, one hop further, and the
 memories and relations around them."""
 from memory_brain import SENSITIVE
 if SENSITIVE.search(prompt or ''):return []
 schema(s);instant(s)
 known=[e for e in _entities(s) if e['id']!='user']
 text=' '+re.sub(r'[^a-z0-9]+',' ',''.join(c for c in unicodedata.normalize('NFKD',str(prompt).casefold()) if not unicodedata.combining(c)))+' '
 compact=norm(prompt)
 hits={e['id'] for e in known if any(len(a)>=4 and (a in compact) for a in e['aliases']) or (len(norm(e['name']))>=3 and ' '+' '.join(re.findall(r'[a-z0-9]+',''.join(c for c in unicodedata.normalize('NFKD',e['name'].casefold()) if not unicodedata.combining(c))))+' ' in text)}
 seeds=list(seeds or [])[:6]
 if seeds:
  marks=','.join('?'*len(seeds))
  hits|={r['entity'] for r in s.rows(f'SELECT entity FROM memory_mentions WHERE memory IN ({marks})',seeds)}
 if not hits:return []
 marks=','.join('?'*len(hits))
 edges=s.rows(f"SELECT DISTINCT src,rel,dst FROM memory_relations WHERE invalid_at IS NULL AND (src IN ({marks}) OR dst IN ({marks}))",[*hits,*hits])
 near={x for e in edges for x in (e['src'],e['dst'])}-hits-{'user'}
 score={}
 for ids,weight in ((hits,2),(near,1)):
  if not ids:continue
  m=','.join('?'*len(ids))
  for r in s.rows(f'SELECT memory,count(*) n FROM memory_mentions WHERE entity IN ({m}) GROUP BY memory',list(ids)):
   score[r['memory']]=score.get(r['memory'],0)+weight*r['n']
 for k in seeds:score.pop(k,None)
 rows=[]
 if score:
  m=','.join('?'*len(score))
  rows=s.rows(f"SELECT key,kind,content,uses,updated FROM assistant_memory WHERE key IN ({m}) AND key!='user-profile'",list(score))
  rows.sort(key=lambda r:(-score[r['key']],-(r['uses'] or 0),-(r['updated'] or 0)))
 names={e['id']:e['name'] for e in known}
 facts=[dict(kind='relation',content=sentence(s,e['src'],e['rel'],e['dst'],names)) for e in edges[:4]]
 return facts+[dict(kind=r['kind'],content=r['content'][:350]) for r in rows[:limit]]


def build(s,query='',kind='',project=''):
 """Everything the Memória page draws: the owner in the middle, entities, memories, typed edges, history."""
 from memory_brain import SENSITIVE
 from model_router import normalized
 schema(s);instant(s)
 q=normalized(query or '').strip()
 memories=[dict(r) for r in s.rows("SELECT key,content,display,kind,source,uses,updated,created FROM assistant_memory WHERE key!='user-profile' ORDER BY updated DESC")]
 memories=[m for m in memories if not SENSITIVE.search((m['content'] or '')+' '+(m['display'] or ''))]
 entities={e['id']:e for e in _entities(s)}
 mentions=s.rows('SELECT memory,entity FROM memory_mentions')
 relations=s.rows('SELECT src,rel,dst,memory,valid_from,invalid_at FROM memory_relations ORDER BY valid_from')
 by_memory={}
 for m in mentions:by_memory.setdefault(m['memory'],set()).add(m['entity'])
 if kind:memories=[m for m in memories if m['kind']==kind]
 if project:
  pid='project:'+project
  memories=[m for m in memories if pid in by_memory.get(m['key'],())]
 if q:
  touched={e for e,v in entities.items() if q in normalized(v['name'])}
  memories=[m for m in memories if q in normalized(m['content']+' '+m['display']) or by_memory.get(m['key'],set())&touched]
 keys={m['key'] for m in memories}
 used={e for k in keys for e in by_memory.get(k,())}
 if not (kind or project or q):used|={r['src'] for r in relations}|{r['dst'] for r in relations}
 used.discard('user')
 nodes=[dict(id='user',label=entities['user']['name'] if 'user' in entities else 'Te',type='user',group='user')]
 degree={}
 for e in sorted(used):
  if e in entities:nodes.append(dict(id=e,label=entities[e]['name'],type='entity',group=entities[e]['kind'],project=entities[e].get('project')))
 for m in memories:
  nodes.append(dict(id='m:'+m['key'],key=m['key'],label=m['display'] or m['content'],type='memory',group=m['kind'],source=m['source'],uses=m['uses'] or 0,created=m['created'] or m['updated']))
 links=[];explicit=set()
 grouped={}
 for r in relations:
  if r['memory'] and r['memory'] not in keys and (kind or project or q):continue
  if r['src'] not in used|{'user'} or r['dst'] not in used|{'user'}:continue
  g=grouped.setdefault((r['src'],r['rel'],r['dst']),dict(source=r['src'],target=r['dst'],relation=r['rel'],label=RELATIONS.get(r['rel'],r['rel']),type='relation',evidence=0,valid=0,valid_from=r['valid_from'],invalid_at=None,ended=0,memories=[]))
  g['evidence']+=1
  if r['memory']:g['memories'].append('m:'+r['memory'])
  if r['invalid_at'] is None:g['valid']+=1
  else:g['ended']=max(g['ended'],r['invalid_at'])
  explicit.add((r['src'],r['dst']));explicit.add((r['dst'],r['src']))
 for g in grouped.values():
  # An edge is history only when no memory supports it any more.
  g['invalid_at']=None if g['valid'] else g['ended'];del g['valid'],g['ended']
 links.extend(grouped.values())
 kinds={m['key']:m['kind'] for m in memories}
 for m in memories:
  ents=by_memory.get(m['key'],set())-{'user'}
  if not ents:links.append(dict(source='user',target='m:'+m['key'],relation=KIND_RELATION.get(m['kind'],'related_to'),label=RELATIONS[KIND_RELATION.get(m['kind'],'related_to')],type='memory'))
  for e in ents:
   if e in used:links.append(dict(source='m:'+m['key'],target=e,relation='mentions',label='említi',type='mention'))
 # An entity the owner has no stated relation to still belongs to them through the memories that mention it.
 for e in used:
  if ('user',e) in explicit:continue
  ks=[k for k in keys if e in by_memory.get(k,())]
  if ks:
   strongest=max(ks,key=lambda k:{'goal':4,'project':3,'preference':2,'identity':2}.get(kinds[k],1))
   rel=KIND_RELATION.get(kinds[strongest],'related_to')
   links.append(dict(source='user',target=e,relation=rel,label=RELATIONS[rel],type='derived',evidence=len(ks)))
 for l in links:
  for end in (l['source'],l['target']):degree[end]=degree.get(end,0)+1
 for n in nodes:n['degree']=degree.get(n['id'],0)
 events=s.rows('SELECT at,kind,memory,detail FROM memory_events ORDER BY id DESC LIMIT 30')
 learned=s.rows("SELECT key,display,created,source FROM assistant_memory WHERE key!='user-profile' ORDER BY COALESCE(created,updated) DESC LIMIT 12")
 timeline=sorted([dict(at=e['at'],kind=e['kind'],memory=e['memory'],detail=e['detail']) for e in events]+[dict(at=l['created'],kind='learned',memory=l['key'],detail=l['display']) for l in learned if l['created']],key=lambda x:-(x['at'] or 0))[:30]
 return dict(nodes=nodes,links=links,kinds=KINDS,relations=RELATIONS,timeline=timeline,
             pending=len(pending(s,500)),projects=s.rows("SELECT id,name FROM projects WHERE id!='universe' AND length(name)>=3 ORDER BY name"),
             stats=dict(memories=len(memories),entities=len(used),relations=sum(1 for l in links if l['type']=='relation' and not l.get('invalid_at')),past=sum(1 for l in links if l['type']=='relation' and l.get('invalid_at'))))
