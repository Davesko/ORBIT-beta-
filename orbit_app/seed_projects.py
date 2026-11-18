"""The starting projects of a fresh ORBIT: their rooms, agents (with prompts) and links, nothing else.
No jobs, files, memories, accounts or schedules travel with them. Used by the public build (seed/projects.json)."""
import json,time
from pathlib import Path
SEED=Path(__file__).with_name('seed')/'projects.json'
# Only the real data folder is seeded; a test's temporary ORBIT stays empty unless it asks.
FORCE=False
ROOMS=('id','name','sub','x','y','width','height','decor','floor','wall','accent')
AGENTS=('id','name','role','room','color','prompt','tools')
LINKS=('id','source','target','name','mode','instructions','task','output_kind')

def export(s,projects):
 out=[]
 for pid in projects:
  p=s.db.execute('SELECT id,name,description,kind FROM projects WHERE id=?',(pid,)).fetchone()
  if not p:raise ValueError('Nincs ilyen projekt: '+pid)
  live="id NOT IN (SELECT id FROM agent_archive)"
  out.append(dict(project=dict(p),
   rooms=[{k:r[k] for k in ROOMS} for r in s.rows('SELECT * FROM rooms WHERE project=? AND COALESCE(archived,0)=0',(pid,))],
   agents=[dict({k:r[k] for k in AGENTS},tools=json.loads(r['tools'] or '[]'),model='auto',interval=0) for r in s.rows(f'SELECT * FROM agents WHERE project=? AND {live} ORDER BY name',(pid,))],
   links=[{k:r[k] for k in LINKS} for r in s.rows('SELECT * FROM connections WHERE project=? AND COALESCE(archived,0)=0',(pid,))]))
 return dict(version=1,projects=out)

def load(s,path=None):
 """Into an empty ORBIT only. Returns how many projects were created."""
 path=path or SEED
 if not Path(path).is_file():return 0
 data=json.loads(Path(path).read_text());made=0;now=time.time()
 for item in data.get('projects',[]):
  p=item['project']
  if s.db.execute('SELECT 1 FROM projects WHERE id=?',(p['id'],)).fetchone():continue
  s.db.execute('INSERT INTO projects VALUES(?,?,?,?,?)',(p['id'],p['name'],p.get('description',''),p.get('kind','general'),now))
  for r in item.get('rooms',[]):
   s.db.execute('INSERT OR REPLACE INTO rooms(project,'+','.join(ROOMS)+',archived) VALUES(?,'+','.join('?'*len(ROOMS))+',0)',(p['id'],*[r.get(k) for k in ROOMS]))
  for a in item.get('agents',[]):
   s.db.execute('INSERT OR REPLACE INTO agents(id,project,name,role,model,room,color,prompt,tools,interval,next_run) VALUES(?,?,?,?,?,?,?,?,?,0,0)',
                (a['id'],p['id'],a['name'],a.get('role',''),a.get('model','auto'),a.get('room','bridge'),a.get('color','#8be4ff'),a.get('prompt',''),json.dumps(a.get('tools',[]))))
  for l in item.get('links',[]):
   s.db.execute('INSERT OR REPLACE INTO connections(project,'+','.join(LINKS)+',archived) VALUES(?,'+','.join('?'*len(LINKS))+',0)',(p['id'],*[l.get(k) for k in LINKS]))
  made+=1
 s.db.commit()
 return made
