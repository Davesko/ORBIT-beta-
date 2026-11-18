"""The first start on a new Mac: a name to call the user, a local model that suits the machine, and what to try first."""

def done(s):
 import memory_brain
 memory_brain.schema(s)
 if s.db.execute("SELECT value FROM memory_settings WHERE key='setup_done'").fetchone():return True
 # Someone who already uses ORBIT needs no welcome.
 return bool(s.db.execute('SELECT 1 FROM command_turns LIMIT 1').fetchone())

def status(s):
 import model_finder
 st=model_finder.status(s);chat=[m for m in st['installed']]
 from connections import settings
 cloud=[p for p,v in settings()['providers'].items() if v.get('enabled') and p in ('groq','gemini','openrouter','deepseek')]
 return dict(done=done(s),machine=st['machine'],ollama=st['ollama'],models=len(chat),cloud=bool(cloud) and settings()['mode']!='local',pulling=st['pulling'])

def finish(s,name=''):
 import memory_brain
 memory_brain.schema(s);name=' '.join(str(name or '').split())[:60]
 if name:memory_brain.remember(s,'user-name','The user is called '+name+'.','A neved: '+name+'.','identity',source='manual')
 s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('setup_done','1')");s.db.commit();return dict(done=True)

def dispatch(s,op,args=None):
 args=args or {}
 if op=='setup_status':return status(s)
 if op=='setup_finish':return finish(s,args.get('name'))
 raise ValueError('Ismeretlen beállítási művelet.')
