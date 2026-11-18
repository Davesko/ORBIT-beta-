"""Expose only the top-level human reply from an incomplete JSON plan."""
import json,sqlite3,time
from pathlib import Path

def extract(raw):
 decoder=json.JSONDecoder();i=raw.find('{')
 if i<0:return ''
 i+=1
 while i<len(raw):
  while i<len(raw) and raw[i] in ' \n\r\t,':i+=1
  try:key,end=decoder.raw_decode(raw,i)
  except ValueError:return ''
  if not isinstance(key,str):return ''
  i=end
  while i<len(raw) and raw[i].isspace():i+=1
  if i>=len(raw) or raw[i]!=':':return ''
  i+=1
  while i<len(raw) and raw[i].isspace():i+=1
  if key=='reply':
   if i>=len(raw) or raw[i]!='"':return ''
   out=[];i+=1
   while i<len(raw):
    c=raw[i]
    if c=='"':break
    if c=='\\':
     length=6 if i+1<len(raw) and raw[i+1]=='u' else 2
     if i+length>len(raw):break
     try:out.append(json.loads('"'+raw[i:i+length]+'"'))
     except ValueError:break
     i+=length
    else:out.append(c);i+=1
   return ''.join(out).encode('utf-8','replace').decode('utf-8')[:18000]
  try:_,i=decoder.raw_decode(raw,i)
  except ValueError:return ''
 return ''

def publish(root,jobid,raw):
 if not jobid or not (Path(root)/'studio.sqlite').exists():return
 db=sqlite3.connect(str(Path(root)/'studio.sqlite'),timeout=2)
 try:
  row=db.execute('SELECT kind,status,payload FROM jobs WHERE id=?',(jobid,)).fetchone()
  if not row or row[0]!='command' or row[1]!='running':return
  payload=json.loads(row[2]);payload['reply_preview']=extract(raw);payload['reply_preview_at']=time.time()
  db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),jobid));db.commit()
 except sqlite3.OperationalError:pass  # Preview contention must not interrupt model execution.
 finally:db.close()

def read_sse(response,on_text,timeout=90):
 content='';model='';finish=None;usage={};total=0;deadline=time.monotonic()+timeout
 for line in response:
  if time.monotonic()>deadline:raise TimeoutError('A felhőválasz időkerete lejárt.')
  total+=len(line)
  if total>3*1024*1024:raise ValueError('Túl nagy modellválasz.')
  if not line.startswith(b'data:'):continue
  data=line[5:].strip()
  if data==b'[DONE]':break
  event=json.loads(data)
  if event.get('error'):raise ValueError('A felhőmodell adatfolyama hibát jelzett.')
  model=event.get('model') or model;usage=event.get('usage') or usage
  for choice in event.get('choices',[]):
   if choice.get('index',0)!=0:continue
   delta=choice.get('delta',{})
   if delta.get('content'):content+=delta['content'];on_text(content)
   if delta.get('tool_calls'):raise ValueError('Nem támogatott eszközhívás a válasz-adatfolyamban.')
   finish=choice.get('finish_reason') or finish
 if not finish:raise ValueError('A felhőválasz befejezés előtt megszakadt.')
 return dict(model=model,choices=[dict(message=dict(role='assistant',content=content),finish_reason=finish)],usage=usage)
