"""A completed mutation is never replayed just because a later action failed."""
import hashlib,json,time

def schema(s):
 s.db.execute('CREATE TABLE IF NOT EXISTS command_action_journal(turn TEXT,step INTEGER,digest TEXT,status TEXT,result TEXT,target TEXT,updated REAL,PRIMARY KEY(turn,step))');s.db.commit()

def begin(s,turn,index,action,target):
 schema(s);digest=hashlib.sha256(json.dumps(action,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 row=s.db.execute('SELECT * FROM command_action_journal WHERE turn=? AND step=?',(turn,index)).fetchone()
 if row:
  if row['digest']!=digest:raise ValueError('A műveleti terv megváltozott; új jóváhagyás szükséges.')
  if row['status']=='done':return dict(result=json.loads(row['result']),target=row['target'])
  raise ValueError('A korábbi művelet kimenetele ellenőrzést igényel. Nem ismétlem meg vakon; a már elkészült lépések megmaradtak.')
 s.db.execute('INSERT INTO command_action_journal VALUES(?,?,?,?,?,?,?)',(turn,index,digest,'executing','null',target,time.time()));s.db.commit();return None

def complete(s,turn,index,result,target):
 s.db.execute("UPDATE command_action_journal SET status='done',result=?,target=?,updated=? WHERE turn=? AND step=?",(json.dumps(result,ensure_ascii=False),target,time.time(),turn,index));s.db.commit()
