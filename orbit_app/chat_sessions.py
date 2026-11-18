"""Chats: the main assistant's single conversation split into separate chats the owner can open, rename and delete."""
import time,uuid

LEGACY='earlier'

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS chat_sessions(id TEXT PRIMARY KEY,title TEXT,created REAL,updated REAL);
 CREATE TABLE IF NOT EXISTS chat_archives(session TEXT PRIMARY KEY,archived REAL);
 CREATE TABLE IF NOT EXISTS chat_session_turns(turn TEXT PRIMARY KEY,session TEXT);
 CREATE INDEX IF NOT EXISTS chat_session_turns_session ON chat_session_turns(session);''');s.db.commit()

def title_of(prompt):
 text=' '.join(str(prompt or '').split())
 return (text[:48].rsplit(' ',1)[0] if len(text)>48 and ' ' in text[:48] else text[:48]) or 'Új chat'

def ensure(s,session,prompt=''):
 """The chat a new message belongs to; a new message without one starts a new chat."""
 schema(s);session=str(session or '')
 if s.db.execute('SELECT 1 FROM chat_archives WHERE session=?',(session,)).fetchone():raise ValueError('Ez a chat törölve van. Előbb állítsd vissza a törölt chatek közül.')
 if session==LEGACY:return LEGACY
 if session and s.db.execute('SELECT 1 FROM chat_sessions WHERE id=?',(session,)).fetchone():return session
 sid=uuid.uuid4().hex;now=time.time();s.db.execute('INSERT INTO chat_sessions VALUES(?,?,?,?)',(sid,title_of(prompt),now,now));s.db.commit();return sid

def assign(s,turn,session):
 schema(s)
 if session==LEGACY:return
 s.db.execute('INSERT OR REPLACE INTO chat_session_turns VALUES(?,?)',(turn,session));s.db.execute('UPDATE chat_sessions SET updated=? WHERE id=?',(time.time(),session));s.db.commit()

def of_turn(s,turn):
 schema(s);row=s.db.execute('SELECT session FROM chat_session_turns WHERE turn=?',(turn,)).fetchone()
 return row[0] if row else None

def listing(s):
 schema(s);out=s.rows('SELECT c.id,c.title,c.updated,count(t.turn) AS turns FROM chat_sessions c LEFT JOIN chat_session_turns t ON t.session=c.id WHERE c.id NOT IN (SELECT session FROM chat_archives) GROUP BY c.id ORDER BY c.updated DESC LIMIT 200')
 earlier=s.db.execute('SELECT count(*),max(t.created) FROM command_turns t JOIN command_global g ON g.turn_id=t.id WHERE t.id NOT IN (SELECT turn FROM chat_session_turns)').fetchone()
 if earlier[0]:out.append(dict(id=LEGACY,title='Korábbi beszélgetés',updated=earlier[1],turns=earlier[0]))
 return dict(chats=out)

def rename(s,session,title):
 schema(s);title=' '.join(str(title or '').split())[:80]
 if not title:raise ValueError('Adj nevet a chatnek.')
 if session==LEGACY or not s.db.execute('UPDATE chat_sessions SET title=? WHERE id=?',(title,session)).rowcount:raise ValueError('Ez a chat nem nevezhető át.')
 s.db.commit();return dict(id=session,title=title)

def remove(s,session):
 """Recoverable deletion: retain the complete conversation and all associated files."""
 schema(s)
 if session==LEGACY:turns=[r[0] for r in s.db.execute('SELECT t.id FROM command_turns t JOIN command_global g ON g.turn_id=t.id WHERE t.id NOT IN (SELECT turn FROM chat_session_turns)').fetchall()]
 else:turns=[r[0] for r in s.db.execute('SELECT turn FROM chat_session_turns WHERE session=?',(session,)).fetchall()]
 busy=[t for t in turns if s.db.execute("SELECT 1 FROM command_turns WHERE id=? AND status IN ('queued','running','queued_apply','applying')",(t,)).fetchone()]
 if busy:raise ValueError('Ebben a chatben még fut egy kérés. Várd meg vagy állítsd le.')
 for turn in turns:
  if s.db.execute("SELECT 1 FROM command_links c JOIN jobs j ON j.id=c.job WHERE c.turn_id=? AND j.status IN ('queued','running')",(turn,)).fetchone():
   raise ValueError('Ebben a chatben még fut egy kérés. Várd meg vagy állítsd le.')
 with s.db:
  if session==LEGACY:
   session=uuid.uuid4().hex;now=time.time()
   s.db.execute('INSERT INTO chat_sessions VALUES(?,?,?,?)',(session,'Korábbi beszélgetés',now,now))
   s.db.executemany('INSERT INTO chat_session_turns VALUES(?,?)',[(t,session) for t in turns])
  elif not s.db.execute('SELECT 1 FROM chat_sessions WHERE id=?',(session,)).fetchone():raise ValueError('A chat nem található.')
  s.db.execute('INSERT OR IGNORE INTO chat_archives VALUES(?,?)',(session,time.time()))
 return dict(removed=len(turns),restore_id=session)

def archived(s):
 schema(s)
 return dict(chats=s.rows('SELECT c.id,c.title,a.archived FROM chat_sessions c JOIN chat_archives a ON a.session=c.id ORDER BY a.archived DESC LIMIT 200'))

def restore(s,session):
 schema(s)
 with s.db:
  if not s.db.execute('DELETE FROM chat_archives WHERE session=?',(session,)).rowcount:raise ValueError('A törölt chat nem található.')
 return dict(id=session)

def visible(s,turn):
 schema(s)
 return not s.db.execute('SELECT 1 FROM chat_session_turns c JOIN chat_archives a ON a.session=c.session WHERE c.turn=?',(turn,)).fetchone()

def search(s,query,limit=30):
 """Across every chat, newest first."""
 schema(s);query=' '.join(str(query or '').split())
 if len(query)<2:return dict(results=[])
 like='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';out=[]
 for row in s.rows("SELECT t.id,t.prompt,t.response,t.created,COALESCE(c.session,?) AS session FROM command_turns t JOIN command_global g ON g.turn_id=t.id LEFT JOIN chat_session_turns c ON c.turn=t.id WHERE (t.prompt LIKE ? ESCAPE '\\' OR t.response LIKE ? ESCAPE '\\') AND COALESCE(c.session,'') NOT IN (SELECT session FROM chat_archives) ORDER BY t.created DESC LIMIT ?",(LEGACY,like,like,limit)):
  out.append(dict(turn=row['id'],session=row['session'],prompt=row['prompt'][:160],response=row['response'][:200],created=row['created']))
 return dict(results=out)

def dispatch(s,op,args=None):
 args=args or {}
 if op=='chat_list':return listing(s)
 if op=='chat_rename':return rename(s,args.get('id'),args.get('title'))
 if op=='chat_delete':return remove(s,args.get('id'))
 if op=='chat_archived':return archived(s)
 if op=='chat_restore':return restore(s,args.get('id'))
 if op=='chat_search':return search(s,args.get('query'))
 raise ValueError('Ismeretlen chatművelet.')
