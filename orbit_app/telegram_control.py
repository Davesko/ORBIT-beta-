"""Owner-paired Telegram transport. Same assistant/agent jobs, never a second execution engine."""
import hashlib,hmac,json,re,secrets,time,urllib.request,urllib.error
import connections

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS telegram_owner(chat INTEGER PRIMARY KEY,user INTEGER,project TEXT,target TEXT DEFAULT 'assistant');
 CREATE TABLE IF NOT EXISTS telegram_pair(hash TEXT,expires REAL);
 CREATE TABLE IF NOT EXISTS telegram_inbox(id INTEGER PRIMARY KEY,chat INTEGER,user INTEGER,text TEXT,status TEXT DEFAULT 'pending',job TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS telegram_outbox(id TEXT PRIMARY KEY,chat INTEGER,text TEXT,status TEXT DEFAULT 'pending');
 CREATE TABLE IF NOT EXISTS telegram_transport(key TEXT PRIMARY KEY,value TEXT);''')
 for name in ('project','target'):
  if name not in [r[1] for r in s.db.execute('PRAGMA table_info(telegram_inbox)')]:s.db.execute('ALTER TABLE telegram_inbox ADD COLUMN '+name+' TEXT')
 s.db.commit()

def api(root,method,payload):
 if not connections.allowed('telegram',root):raise ValueError('A Telegram-kapcsolat nincs engedélyezve.')
 token=connections.secret('telegram',root)
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):raise ValueError('Telegram-átirányítás tiltva.')
 try:
  req=urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=22) as response:data=json.loads(response.read(2*1024*1024))
  if not data.get('ok'):raise ValueError('Telegram API-hiba.')
  return data['result']
 except Exception:raise ValueError('A Telegram nem elérhető. Ellenőrizd a bot tokenjét, az internetet és hogy nincs-e másik botfogadó vagy webhook.') from None

def status(s):
 schema(s);owner=s.db.execute('SELECT chat,project,target FROM telegram_owner LIMIT 1').fetchone()
 return dict(paired=bool(owner),owner=dict(owner) if owner else None,configured=bool(connections.secret('telegram',s.root)),enabled=connections.allowed('telegram',s.root),unsent=s.db.execute("SELECT count(*) FROM telegram_outbox WHERE status!='sent'").fetchone()[0])

def pair(s):
 schema(s)
 bot=api(s.root,'getMe',{})
 code=secrets.token_urlsafe(18);s.db.execute('DELETE FROM telegram_pair');s.db.execute('INSERT INTO telegram_pair VALUES(?,?)',(hashlib.sha256(code.encode()).hexdigest(),time.time()+600));s.db.commit()
 return dict(url='https://t.me/'+bot['username']+'?start='+code,expires=time.time()+600)

def unpair(s):
 schema(s);s.db.execute('DELETE FROM telegram_owner');s.db.execute('DELETE FROM telegram_pair');s.db.execute("UPDATE telegram_inbox SET status='revoked' WHERE status='pending'");s.db.execute("UPDATE telegram_outbox SET status='revoked' WHERE status='pending'");s.db.commit()

def tidy(text):
 """Plain, readable phone text: no markdown markers, raw IDs or empty bookkeeping lines."""
 text=str(text or '')
 text=re.sub(r'\*\*(.+?)\*\*',r'\1',text);text=re.sub(r'(?m)^#{1,6}\s*','',text);text=text.replace('`','')
 text=re.sub(r'\s*\((?:ID|azonosító)[:= ]*[0-9a-f]{12,}\)','',text,flags=re.I);text=re.sub(r'\b[0-9a-f]{32}\b','',text)
 text=re.sub(r'(?m)^\s*Korábban elkészült:\s*\[\]\s*$','',text)
 text=re.sub(r'(?m)^(\s*)[-*] ',r'\1• ',text)
 return re.sub(r'\n{3,}','\n\n',text).strip()

def out(s,key,chat,text):
 text=tidy(text)
 # Never echo provider credentials, even if accidentally present in a model reply.
 for provider in connections.PROVIDERS:
  value=connections.secret(provider,s.root)
  if value:text=text.replace(value,'[titkos kulcs]')
 for n in range(0,len(text),3500):s.db.execute('INSERT OR IGNORE INTO telegram_outbox VALUES(?,?,?,?)',(str(key)+':'+str(n//3500),chat,text[n:n+3500],'pending'))
 s.db.commit()

def ingest(s,update):
 schema(s)
 msg=update.get('message',{});uid=update.get('update_id')
 if type(uid) is not int:return
 if msg.get('chat',{}).get('type')!='private':return
 chat=msg['chat'].get('id');user=msg.get('from',{}).get('id');text=msg.get('text','')
 if type(chat) is not int or chat!=user or not isinstance(text,str):return
 owner=s.db.execute('SELECT * FROM telegram_owner LIMIT 1').fetchone()
 if text.startswith('/start ') and (not owner or (owner['chat']==chat and owner['user']==user)):
  code=text.split(' ',1)[1].strip();p=s.db.execute('SELECT * FROM telegram_pair WHERE expires>?',(time.time(),)).fetchone()
  if p and hmac.compare_digest(p['hash'],hashlib.sha256(code.encode()).hexdigest()):
   project=s.db.execute('SELECT id FROM projects ORDER BY created LIMIT 1').fetchone()[0]
   s.db.execute('INSERT OR REPLACE INTO telegram_owner VALUES(?,?,?,?)',(chat,user,project,'assistant'));s.db.execute('DELETE FROM telegram_pair');s.db.commit()
   connections.save(dict(provider='telegram',chat_id=str(chat)),s.root)
   out(s,'paired:'+str(uid),chat,'ORBIT csatlakoztatva. A fő asszisztensnek írsz. /projects · /agents · /assistant · /status · /help');return
 if not owner or owner['chat']!=chat or owner['user']!=user:return
 s.db.execute('INSERT OR IGNORE INTO telegram_inbox(id,chat,user,text,created,project,target) VALUES(?,?,?,?,?,?,?)',(uid,chat,user,text[:12000],time.time(),owner['project'],owner['target']));s.db.commit()

def dispatch(s,row):
 owner=s.db.execute('SELECT * FROM telegram_owner WHERE chat=? AND user=?',(row['chat'],row['user'])).fetchone()
 if not owner:return 'A párosítás megszűnt.',None
 pid=owner['project'];text=row['text'].strip();parts=text.split(maxsplit=1);cmd=parts[0].split('@')[0].lower() if parts else '';arg=parts[1].strip() if len(parts)>1 else ''
 if cmd in ('/start','/help'):return 'Írj üzenetet a kiválasztott asszisztensnek.\n/projects: projektlista\n/project N: projektváltás\n/agents: ügynöklista\n/agent N vagy név: ügynök kiválasztása\n/assistant: fő asszisztens\n/status: futó feladatok\n/cancel AZONOSÍTÓ: leállítás\n/approve AZONOSÍTÓ: műveleti terv jóváhagyása\n/ma: a nap összefoglalója\n/termek: az épülő termék állapota\n/esti: esti összefoglaló 22:00-kor be/ki',None
 if cmd in ('/projects','/project'):
  projects=s.rows('SELECT id,name FROM projects ORDER BY created')
  if cmd=='/projects':return '\n'.join(str(i+1)+'. '+p['name'] for i,p in enumerate(projects))+'\nVáltás: /project 1',None
  chosen=projects[int(arg)-1] if arg.isdigit() and 1<=int(arg)<=len(projects) else next((p for p in projects if p['id']==arg or p['name'].casefold()==arg.casefold()),None)
  if not chosen:raise ValueError('Ismeretlen projekt. /projects')
  s.db.execute("UPDATE telegram_owner SET project=?,target='assistant' WHERE chat=?",(chosen['id'],row['chat']));s.db.commit();return 'Projekt: '+chosen['name']+' · fő asszisztens',None
 if cmd in ('/agents','/agent'):
  agents=s.rows('SELECT id,name,role FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid',(pid,))
  if cmd=='/agents':return '\n'.join(str(i+1)+'. '+a['name']+' · '+a['role'] for i,a in enumerate(agents))+'\nVáltás: /agent 1',None
  chosen=agents[int(arg)-1] if arg.isdigit() and 1<=int(arg)<=len(agents) else next((a for a in agents if a['id']==arg or a['name'].casefold()==arg.casefold()),None)
  if not chosen:raise ValueError('Ismeretlen ügynök. /agents')
  s.db.execute('UPDATE telegram_owner SET target=? WHERE chat=?',(chosen['id'],row['chat']));s.db.commit();return 'Most neki írsz: '+chosen['name'],None
 if cmd=='/assistant':
  s.db.execute("UPDATE telegram_owner SET target='assistant' WHERE chat=?",(row['chat'],));s.db.commit();return 'A fő asszisztensnek írsz, projektközi rálátással.',None
 if cmd in ('/esti','/evening'):
  from daily_report import toggle_evening
  return ('🌙 Esti összefoglaló bekapcsolva: minden este 22:00 után megkapod a nap összefoglalóját. Kikapcsolás: /esti' if toggle_evening(s) else 'Esti összefoglaló kikapcsolva.'),None
 if cmd in ('/termek','/product'):
  from venture_build import product_text
  return product_text(s),None
 if cmd in ('/ma','/today'):
  from daily_report import today
  return today(s),None
 if cmd=='/status':
  jobs=s.rows("SELECT id,status,prompt FROM jobs WHERE project=? AND status IN ('queued','running') ORDER BY created LIMIT 12",(pid,))
  return '\n'.join(j['id'][:8]+' · '+j['status']+' · '+j['prompt'][:100] for j in jobs) or 'Nincs futó feladat ebben a projektben.',None
 if cmd=='/cancel':
  jobs=s.rows("SELECT id FROM jobs WHERE project=? AND status IN ('queued','running') AND id LIKE ?",(pid,arg+'%')) if re.fullmatch(r'[a-f0-9]{8,32}',arg) else []
  if len(jobs)!=1:raise ValueError('Adj meg egy egyértelmű feladatazonosítót a /status listából.')
  s.cancel(jobs[0]['id']);return 'Leállítás kérve.',None
 if cmd=='/approve':
  from commander import schema as cs,approve
  cs(s);turns=s.rows("SELECT id FROM command_turns WHERE project=? AND status='review' AND id LIKE ?",(pid,arg+'%')) if re.fullmatch(r'[a-f0-9]{8,32}',arg) else []
  if len(turns)!=1:raise ValueError('Nincs ilyen jóváhagyásra váró műveleti terv.')
  return 'Jóváhagyás elküldve.',approve(s,pid,turns[0]['id'],True)
 if text.startswith('/'):raise ValueError('Ismeretlen parancs. /help')
 pid=row.get('project') or pid
 target=row.get('target') or owner['target']
 existing=s.db.execute("SELECT id FROM jobs WHERE json_extract(payload,'$.telegram_update')=?",(row['id'],)).fetchone()
 if existing:return 'A feladat már sorban áll.',existing[0]
 if target=='assistant':
  from commander import enqueue
  if s.db.execute("SELECT 1 FROM jobs WHERE kind IN ('command','command_apply','control_apply') AND status IN ('queued','running')").fetchone():return None,None
  jid=enqueue(s,pid,text,'auto',global_mode=True,origin=row['id'])
 else:
  a=s.db.execute('SELECT * FROM agents WHERE id=? AND project=? AND id NOT IN (SELECT id FROM agent_archive)',(target,pid)).fetchone()
  if not a:raise ValueError('Az ügynök már nem aktív. /agents vagy /assistant')
  jid=s.enqueue(a['id'],text,'chat',payload=dict(telegram_update=row['id']))
 return '⏳ Dolgozom rajta…',jid

def process(s):
 schema(s)
 for row in s.rows("SELECT * FROM telegram_inbox WHERE status='pending' ORDER BY CASE WHEN text LIKE '/%' THEN 0 ELSE 1 END,id LIMIT 20"):
  try:reply,jid=dispatch(s,row)
  except Exception:reply,jid='A kérés most nem hajtható végre. Ellenőrizd a kiválasztott projektet és ügynököt az ORBIT-ban. /status · /help',None
  if reply is None:continue
  s.db.execute("UPDATE telegram_inbox SET status='handled',job=? WHERE id=?",(jid,row['id']));s.db.commit();out(s,'ack:'+str(row['id']),row['chat'],reply)
 for row in s.rows("SELECT i.*,j.status AS job_status,j.result,j.error,j.kind,j.payload FROM telegram_inbox i JOIN jobs j ON j.id=i.job WHERE i.status='handled' AND j.status IN ('done','failed','cancelled','blocked')"):
  text=row['result'] or row['error'] or row['job_status']
  if row['kind']=='command':
   from commander import schema as cs
   cs(s);turn=s.db.execute('SELECT * FROM command_turns WHERE id=?',(json.loads(row['payload']).get('turn'),)).fetchone()
   if turn:
    if turn['status'] in ('queued_apply','applying'):
     follow=s.db.execute("SELECT id FROM jobs WHERE kind IN ('command_apply','control_apply') AND json_extract(payload,'$.turn')=? ORDER BY created DESC LIMIT 1",(turn['id'],)).fetchone()
     if follow:
      # Follow the execution silently; the user gets one final answer, not a progress message.
      s.db.execute('UPDATE telegram_inbox SET job=? WHERE id=?',(follow[0],row['id']));s.db.commit();continue
    text=turn['response'] or text
    if turn['status']=='review':
     try:steps=[a.get('operation') or a.get('type') for a in json.loads(turn['actions'] or '[]')]
     except ValueError:steps=[]
     text+='\n\nJóváhagyás kell hozzá: /approve '+turn['id'][:12]+('\nLépések: '+', '.join(str(x) for x in steps if x) if steps else '')
  out(s,'result:'+str(row['id']),row['chat'],text[:14000]);s.db.execute("UPDATE telegram_inbox SET status='replied' WHERE id=?",(row['id'],));s.db.commit()
 for row in s.rows("SELECT * FROM telegram_outbox WHERE status='pending' ORDER BY rowid LIMIT 10"):
  owner=s.db.execute('SELECT 1 FROM telegram_owner WHERE chat=?',(row['chat'],)).fetchone()
  if not owner:continue
  s.db.execute("UPDATE telegram_outbox SET status='sending' WHERE id=?",(row['id'],));s.db.commit()
  try:api(s.root,'sendMessage',dict(chat_id=row['chat'],text=row['text'],link_preview_options=dict(is_disabled=True)));state='sent'
  except Exception:state='uncertain'
  s.db.execute('UPDATE telegram_outbox SET status=? WHERE id=?',(state,row['id']));s.db.commit()

def loop(stop):
 from studio import Studio
 s=Studio();schema(s)
 while not stop.is_set():
  try:
   if not connections.allowed('telegram',s.root):stop.wait(5);continue
   process(s)
   row=s.db.execute("SELECT value FROM telegram_transport WHERE key='offset'").fetchone();offset=int(row[0]) if row else 0
   updates=api(s.root,'getUpdates',dict(offset=offset,timeout=15,allowed_updates=['message'],limit=30))
   for update in updates:
    ingest(s,update)
    s.db.execute("INSERT OR REPLACE INTO telegram_transport VALUES('offset',?)",(str(update['update_id']+1),));s.db.commit()
  except Exception:stop.wait(10)
 s.db.close()
