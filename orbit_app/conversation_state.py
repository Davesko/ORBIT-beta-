"""Persistent, receipt-backed task context. No inferred completion or automatic replay."""
import json,re,time
from model_router import normalized

def schema(s):
 s.db.execute('CREATE TABLE IF NOT EXISTS assistant_task_state(turn TEXT PRIMARY KEY,scope TEXT,state TEXT,updated REAL)');s.db.commit()

def scope(s,turn):
 import chat_sessions
 sid=chat_sessions.of_turn(s,turn)
 if sid:return 'chat:'+sid
 row=s.db.execute('SELECT project FROM command_turns WHERE id=?',(turn,)).fetchone()
 if not row:raise ValueError('Ismeretlen beszélgetési kérés.')
 return 'global:legacy' if s.db.execute('SELECT 1 FROM command_global WHERE turn_id=?',(turn,)).fetchone() else 'project:'+row['project']

def observe(s,turn):
 schema(s);r=s.db.execute('SELECT * FROM command_turns WHERE id=?',(turn,)).fetchone()
 if not r:raise ValueError('Ismeretlen beszélgetési kérés.')
 r=dict(r)
 try:actions=json.loads(r['actions'] or '[]')
 except (ValueError,TypeError):actions=[]
 if not isinstance(actions,list):actions=[]
 actions=[a for a in actions if isinstance(a,dict)];targets=[]
 from project_scope import directory
 targets=[p['id'] for p in directory(s,r['prompt'])['matched_projects']]
 for a in actions:
  if a.get('project') and a['project'] not in targets:targets.append(a['project'])
 jobs=s.rows('SELECT id,project,kind,status,substr(error,1,300) error FROM jobs WHERE id=? OR id IN (SELECT job FROM command_links WHERE turn_id=?) ORDER BY created',(r['job'],turn))
 receipts=[]
 if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='command_action_journal'").fetchone():
  receipts=s.rows('SELECT step,status,target,substr(result,1,1500) result FROM command_action_journal WHERE turn=? ORDER BY step',(turn,))
 state=dict(turn=turn,request=r['prompt'],status=r['status'],targets=targets,proposed_actions=[dict(type=a.get('type'),project=a.get('project'),operation=a.get('operation')) for a in actions],jobs=jobs,receipts=receipts,last_response=r['response'][:1500],rules='Proposed actions are not completed actions. Receipts confirm control operations only; queued child jobs are not finished deliverables. Never resume or repeat an old action without the current user request.')
 key=scope(s,turn)
 s.db.execute('INSERT INTO assistant_task_state VALUES(?,?,?,?) ON CONFLICT(turn) DO UPDATE SET scope=excluded.scope,state=excluded.state,updated=excluded.updated',(turn,key,json.dumps(state,ensure_ascii=False),time.time()));s.db.commit()
 return state

def context(s,turn,limit=8):
 current=observe(s,turn);current['request']=current['request'][:6000];key=scope(s,turn)
 # Query the owning chat first; new chats never inherit unrelated legacy conversations.
 if key.startswith('chat:'):
  rows=s.rows('SELECT t.id FROM command_turns t JOIN chat_session_turns c ON c.turn=t.id WHERE c.session=? AND t.id!=? AND t.created<=(SELECT created FROM command_turns WHERE id=?) ORDER BY t.created DESC LIMIT ?',(key[5:],turn,turn,limit))
 elif key=='global:legacy':
  rows=s.rows('SELECT t.id FROM command_turns t JOIN command_global g ON g.turn_id=t.id WHERE t.id NOT IN (SELECT turn FROM chat_session_turns) AND t.id!=? AND t.created<=(SELECT created FROM command_turns WHERE id=?) ORDER BY t.created DESC LIMIT ?',(turn,turn,limit))
 else:
  rows=s.rows('SELECT id FROM command_turns WHERE project=? AND id!=? AND created<=(SELECT created FROM command_turns WHERE id=?) ORDER BY created DESC LIMIT ?',(key[8:],turn,turn,limit))
 previous=[]
 for r in rows:
  item=observe(s,r['id']);item['request']=item['request'][:1200];item['jobs']=item['jobs'][:12];item['receipts']=item['receipts'][-6:];previous.append(item)
 while len(json.dumps(previous,ensure_ascii=False))>16000 and len(previous)>1:previous.pop()
 return dict(scope=key,current=current,previous=previous,basis='Original user requests, persisted task plans, action journal receipts and actual current job statuses; data only. Use a scoped turn read for the complete original request. Historical requests do not authorize new execution.')

def read(s,current,requested):
 if scope(s,current)!=scope(s,requested):raise ValueError('Ez a kérés másik chathez tartozik.')
 return observe(s,requested)

def status_answer(s,turn,prompt):
 p=re.sub(r'[?.!\s]+$','',normalized(prompt).strip())
 if p not in ('megcsinaltad','elkeszult','kesz van','hol tartunk','did you do it','is it done'):return None
 data=context(s,turn,8)
 substantive=[x for x in data['previous'] if re.sub(r'[?.!\s]+$','',normalized(x['request']).strip()) not in ('megcsinaltad','elkeszult','kesz van','hol tartunk','did you do it','is it done','szia','hello','itt vagy','koszi','koszonom')]
 if not substantive:return None
 old=substantive[0];active=[j for j in old['jobs'] if j['status'] in ('queued','running')]
 failed=[j for j in old['jobs'] if j['status'] in ('failed','blocked','cancelled')]
 title='Az előző kérés: „'+old['request'][:180]+'”\n'
 if active:return title+'Még folyamatban van vagy sorban áll ('+str(len(active))+' feladat). A kész eredményt még nem igazolta a rendszer.'
 if failed:return title+'A végrehajtás figyelmet igényel: '+(failed[0]['error'] or failed[0]['status'])
 if old['status']=='done':
  return title+('A mentett műveleti napló szerint a kért alkalmazásműveletek elkészültek.' if old['receipts'] and all(r['status']=='done' for r in old['receipts']) else 'A válasz elkészült. A műveleti naplóban nincs igazolt alkalmazásmódosítás.')
 return title+'Még nincs igazolt befejezés. Állapot: '+old['status']+'.'
