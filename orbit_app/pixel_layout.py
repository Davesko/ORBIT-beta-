"""One-time visual layout migration. Agent IDs, tools, connections and schedules are untouched."""
import time

def migrate(s):
 s.db.execute('CREATE TABLE IF NOT EXISTS design_migrations(project TEXT,key TEXT,created REAL,PRIMARY KEY(project,key))');s.db.commit()
 changed=[]
 for project in s.rows('SELECT id FROM projects'):
  pid=project['id']
  if s.db.execute("SELECT 1 FROM design_migrations WHERE project=? AND key='pixel-workshop-v1'",(pid,)).fetchone():continue
  rooms=s.rows('SELECT * FROM rooms WHERE project=? AND archived=0 ORDER BY CASE decor WHEN \'research\' THEN 0 WHEN \'office\' THEN 1 WHEN \'command\' THEN 1 WHEN \'editing\' THEN 2 WHEN \'media\' THEN 2 WHEN \'audio\' THEN 4 ELSE 3 END,id',(pid,))
  cols=3 if len(rooms)>=5 else 2;x=0;y=0;row_height=0
  s.db.execute('BEGIN IMMEDIATE')
  try:
   for i,r in enumerate(rooms):
    if i and i%cols==0:x=0;y+=row_height+2;row_height=0
    # Compact, varied rooms leave a visible shared corridor and readable character targets.
    w,h=(12,9) if r['decor'] in ('editing','media','command') else (10,8)
    if r['decor']=='audio':w,h=10,8
    floor={'research':'#3d3540','editing':'#343444','media':'#343444','audio':'#353140','marketing':'#403641','office':'#3b3440'}.get(r['decor'],'#3a3340')
    s.db.execute('UPDATE rooms SET x=?,y=?,width=?,height=?,floor=?,wall=?,accent=? WHERE project=? AND id=?',(x,y,w,h,floor,'#38394d','#ad8aee',pid,r['id']));x+=w+2;row_height=max(row_height,h)
   s.db.execute('INSERT INTO design_migrations VALUES(?,?,?)',(pid,'pixel-workshop-v1',time.time()));s.db.commit();changed.append(pid)
  except Exception:s.db.rollback();raise
 return changed
