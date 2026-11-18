"""Local versioned procedural memory; guidance never grants tools or permissions."""
import json,re,time,uuid
from model_router import normalized

BUILTINS=[
 dict(id='mail-review',title='Levelek és reggeli értesítés',description='Read, search or schedule actionable mailbox review.',tags=['email','level','postafiok','telegram','inbox'],steps=['Distinguish reading mail now from creating a recurring task. Scheduling requests use the task manager, never an answer-only mailbox model.','For literal lookup search synchronized sender, recipients, subject and body; disclose bounded remote coverage.','For daily Telegram review use the supported email_review handler and exact Europe/Budapest daily_time. Keep no-important-mail results quiet.'],verification=['Read back the saved schedule and enabled flag.','A queued Telegram message is not a delivery receipt. Never send email without explicit authorization.']),
 dict(id='project-audit',title='Projekt és ügynökök ellenőrzése',description='Audit and repair the exact named project.',tags=['projekt','project','ugynok','agent','optimaliz'],steps=['Resolve the visible project name from the complete directory. Ask only for real ambiguity.','Read actual agents, prompts, inputs, automations and recent errors before changes.','Apply only requested scoped changes; start a workflow only when the user requests execution.'],verification=['Verify persisted settings and actual queued job IDs.','Changing an agent prompt is not an application-code change.']),
 dict(id='shorts-story',title='Shorts történet és ellenőrzés',description='Source-grounded short-form editing.',tags=['shorts','youtube','vagas','video','hook','felirat'],steps=['Inspect the complete available transcript and source observations; retain the original core context.','Build a grounded hook, setup and payoff using exact source intervals and requested duration.','Use the existing team and renderer. Preserve gameplay context and justify face zooms and effects.'],verification=['Inspect real render, audio continuity, portrait framing and caption safe areas.','Queued production is not a finished video. Preserve publication policy.']),
 dict(id='evidence-research',title='Forrásalapú kutatás',description='Fresh evidence and useful research results.',tags=['kutat','research','trend','forras','keress'],steps=['Identify subject, recency window and the user goal.','Use actual web evidence with source URLs and dates; reject off-topic or duplicate material.','Save findings and uncertainty separately from proposals.'],verification=['Check source relevance and publication dates.','Do not claim guaranteed demand, profit or virality.']),
 dict(id='site-media',title='Weboldal saját képpel és videóval',description='Build a web page, app or landing page that needs its own generated picture or video.',tags=['weboldal','website','landing','oldal','honlap','hero','banner','kep','video','web'],steps=['Plan the page first: decide which pictures or clips it needs and give each a file name next to the page, for example <creations_folder>/<name>/hero.png.','Return one generate_image (or generate_video) action per asset with save_as set to that exact path; write English visual prompts that fit the page topic and palette.','Return the write_file action for index.html in the same folder AFTER the asset actions; reference each asset by its relative file name and give every image a meaningful alt text.','Keep the page complete and self-contained apart from those assets: inline CSS and JavaScript, responsive layout.'],verification=['Every asset the HTML references has a matching action with the same file name.','The reply names the page and the generated assets.']),
 dict(id='web-research-machine',title='Kutatás kulcs nélkül, a saját géppel',description='Research on the public web when no search API or key is connected.',tags=['keress','kutat','internet','interneten','web','neten','utananez','research','search','forras','api'],steps=['Use the {"search":"query"} read; without a connected search API the app searches through the Mac\'s own browser in the background (no window, no mouse), so never tell the user that searching is impossible for lack of a key.','Open the most relevant results with the {"url":"https://..."} read and base the answer on what the pages say; pages that need JavaScript are rendered by the same browser.','When the task needs a data service again and again, use {"learn_skill":"goal"} once so it becomes a reusable skill.','A robot check or a login wall is never bypassed: report that source as unavailable and use another one.'],verification=['Every factual claim has a source URL that was actually read.','No account, password or CAPTCHA was involved.']),
]
STOP=set('hogy vagy egy ezt azt nekem kell most majd meg legyen lesz van volt mint ami amit akkor ahol csak the and for with this that from into you your have make please keszits csinalj legyen szeretnek kerlek'.split())
MATCH=.2            # lexical similarity a skill needs to be offered without a tag hit
MAX_EXPERIENCE=300

def words(text):
 """Content words cut to five letters, so Hungarian endings (weboldalt, weboldalra, weboldalhoz) meet in one stem."""
 return [w[:5] for w in re.findall(r'[a-z0-9]{3,}',normalized(text)) if w not in STOP]

def similarity(a,b):
 a,b=set(a),set(b)
 return len(a&b)/((len(a)*len(b))**.5) if a and b else 0.

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS assistant_skills(id TEXT PRIMARY KEY,data TEXT,enabled INTEGER,version INTEGER,updated REAL);
 CREATE TABLE IF NOT EXISTS assistant_skill_versions(id TEXT,version INTEGER,data TEXT,created REAL,PRIMARY KEY(id,version));''')
 for b in BUILTINS:
  d=dict(b,source='builtin',status='published')
  s.db.execute('INSERT OR IGNORE INTO assistant_skills VALUES(?,?,?,?,?)',(b['id'],json.dumps(d,ensure_ascii=False),1,1,0 if d['id'] in ('site-media','web-research-machine') else time.time()))
 s.db.commit()

def listing(s,published_only=False):
 schema(s);out=[]
 for row in s.rows('SELECT * FROM assistant_skills ORDER BY updated DESC,id'):
  d=dict(json.loads(row['data']),enabled=bool(row['enabled']),version=row['version'],updated=row['updated'])
  if d.get('api'):
   from skill_api import has_key
   d['has_key']=has_key(s,d['id'])
  if not published_only or d['enabled'] and d['status']=='published':out.append(d)
 return out

def validate(data):
 if not isinstance(data,dict):raise ValueError('Érvénytelen munkamódszer.')
 sid=str(data.get('id') or uuid.uuid4().hex)
 if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',sid):raise ValueError('Érvénytelen azonosító.')
 title=str(data.get('title') or '').strip();description=str(data.get('description') or '').strip()
 steps=data.get('steps');verification=data.get('verification');tags=data.get('tags',[]);status=data.get('status','draft')
 if not 2<=len(title)<=100 or len(description)>500:raise ValueError('Adj rövid nevet és leírást.')
 for name,values in [('Lépések',steps),('Ellenőrzés',verification)]:
  if not isinstance(values,list) or not 1<=len(values)<=12 or any(not isinstance(x,str) or not x.strip() or len(x)>1200 for x in values):raise ValueError(name+': 1–12 nem üres sor szükséges, soronként legfeljebb 1200 karakter.')
 if not isinstance(tags,list) or len(tags)>12 or any(not isinstance(x,str) or not 1<=len(x)<=50 for x in tags):raise ValueError('Érvénytelen címkék.')
 if status not in ('draft','published'):raise ValueError('Ismeretlen állapot.')
 d=dict(id=sid,title=title,description=description,steps=steps,verification=verification,tags=tags,status=status,source='taught')
 if len(json.dumps(d))>14000 or re.search(r'sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{25,}|BEGIN .*PRIVATE KEY',json.dumps(d)):raise ValueError('A munkamódszer túl hosszú vagy titkos kulcsot tartalmaz.')
 return d

def store(s,d):
 """Writes a validated skill as a new version; the previous version is kept."""
 schema(s);sid=d['id']
 old=s.db.execute('SELECT * FROM assistant_skills WHERE id=?',(sid,)).fetchone()
 if old and json.loads(old['data']).get('source')=='builtin':raise ValueError('A beépített munkamódszer másolatként menthető saját néven.')
 version=(old['version']+1) if old else 1
 if old:s.db.execute('INSERT OR IGNORE INTO assistant_skill_versions VALUES(?,?,?,?)',(sid,old['version'],old['data'],time.time()))
 s.db.execute('INSERT INTO assistant_skills VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,version=excluded.version,updated=excluded.updated',(sid,json.dumps(d,ensure_ascii=False),1,version,time.time()));s.db.commit();return dict(id=sid,version=version)

def save(s,data):
 schema(s);d=validate(data)
 old=s.db.execute('SELECT data FROM assistant_skills WHERE id=?',(d['id'],)).fetchone()
 prior=json.loads(old['data']) if old else {}
 # Editing a learned API skill keeps its API description and test record.
 if prior.get('source')=='learned':d.update(source='learned',**{k:prior[k] for k in ('api','learned') if k in prior})
 return store(s,d)

def toggle(s,sid,enabled):
 schema(s)
 if type(enabled) is not bool:raise ValueError('Logikai kapcsoló szükséges.')
 if not s.db.execute('UPDATE assistant_skills SET enabled=?,updated=? WHERE id=?',(int(enabled),time.time(),sid)).rowcount:raise ValueError('Ismeretlen munkamódszer.')
 s.db.commit();return dict(id=sid,enabled=enabled)

def relevance(d,prompt,asked):
 """Tag hits plus meaning overlap with the skill's title, description and tags. No model is asked: the model server
 holds one model, and an embedding call would evict the chat model."""
 tags=sum(bool(re.search(r'\b'+re.escape(normalized(t)),prompt)) for t in d['tags'] if normalized(t))
 close=similarity(asked,words(d['title']+' '+d['description']+' '+' '.join(d['tags'])))
 return tags+(close if close>=MATCH else 0)+(.01*min(d.get('uses',0),20))*(tags>0 or close>=MATCH)

def select(s,prompt,limit=3):
 """The few skills that fit this request; several can apply at once and are meant to be used together."""
 p=normalized(prompt);asked=words(prompt)
 scored=[(relevance(d,p,asked),d) for d in listing(s,True)]
 out=[]
 for score,d in sorted(scored,key=lambda x:(-x[0],x[1]['id'])):
  if not score or len(out)>=limit:continue
  item=dict(id=d['id'],title=d['title'],version=d['version'],steps=d['steps'],verification=d['verification'])
  if d.get('api'):
   from skill_api import summary
   item['api']=summary(s,d);item['how']='Call with the read {"skill_call":{"skill":"'+d['id']+'","endpoint":"...","params":{}}}.'
  out.append(item)
 return out

def dispatch(s,op,args):
 args=args or {}
 if op=='skill_key_save':
  from skill_api import key_save
  return key_save(s,args.get('id'),args.get('key'))
 if op=='skill_test':
  from skill_api import call
  return call(s,args.get('id'),args.get('endpoint'),args.get('params') or {})
 if op=='skill_list':return dict(skills=listing(s))
 if op=='skill_save':return save(s,args.get('skill'))
 if op=='skill_toggle':return toggle(s,args.get('id'),args.get('enabled'))
 raise ValueError('Ismeretlen munkamódszer-művelet.')

PLAIN=dict(generate_image='generate_image: one picture per asset the result needs; set save_as next to the file that will use it',
 generate_video='generate_video: one short clip per asset the result needs; set save_as next to the file that will use it',
 write_file='write_file: one complete file',run_command='run_command: one exact command in the working folder',
 graph_run='graph_run: hand the brief to the project team from its first agent',agent_run='agent_run: give the task to the fitting agent',
 start_shorts='start_shorts: start the Shorts production for the topic',show_artifact='show_artifact: show the finished media in the chat')
IGNORED={'memory_save','preferences_save','computer'}

def learn_from_turn(s,prompt,actions):
 """What worked once is known from then on: a finished request that combined two or more kinds of action is kept as a
 reusable method (the order of the steps, never their content or any secret). The same combination for a similar
 request only counts one more use. Guidance only: a method never grants a tool or a permission."""
 kinds=[]
 for a in actions:
  kind=a.get('type')
  if not kind or kind in IGNORED:continue
  label=kind+(':'+str(a.get('operation')) if kind=='app_action' and a.get('operation') else '')
  if not kinds or kinds[-1][0]!=label:kinds.append((label,a))
 if len({k for k,_ in kinds})<2 or not isinstance(prompt,str) or len(prompt.strip())<12:return None
 schema(s);signature='+'.join(k for k,_ in kinds);asked=words(prompt)
 for row in s.rows('SELECT id,data FROM assistant_skills'):
  d=json.loads(row['data'])
  if d.get('source')=='experience' and d.get('signature')==signature and similarity(asked,words(d['description']))>=.5:
   d['uses']=d.get('uses',1)+1
   s.db.execute('UPDATE assistant_skills SET data=?,updated=? WHERE id=?',(json.dumps(d,ensure_ascii=False),time.time(),row['id']));s.db.commit()
   return dict(id=row['id'],uses=d['uses'],new=False)
 if s.db.execute("SELECT count(*) FROM assistant_skills WHERE json_extract(data,'$.source')='experience'").fetchone()[0]>=MAX_EXPERIENCE:return None
 steps=[]
 for label,a in kinds[:12]:
  line=PLAIN.get(label.split(':')[0],label)
  if label.startswith('write_file') and a.get('path'):line+=' ('+(re.search(r'\.[A-Za-z0-9]{1,6}$',str(a['path'])) or [''])[0].lstrip('.')+')'
  if label.startswith('app_action:'):line='app_action '+label.split(':',1)[1]
  steps.append(line)
 seen=[];[seen.append(w) for w in asked if w not in seen]
 try:
  d=validate(dict(id='exp-'+uuid.uuid4().hex[:12],title=('Tanult: '+' '.join(prompt.split()))[:100],description=' '.join(prompt.split())[:400],
                  tags=seen[:12],steps=steps,verification=['Every step returned a result and the reply names what was made.'],status='published'))
 except ValueError:return None
 d.update(source='experience',signature=signature,uses=1)
 store(s,d);return dict(id=d['id'],uses=1,new=True)
