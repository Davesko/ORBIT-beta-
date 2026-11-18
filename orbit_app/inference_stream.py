"""Incremental Ollama reads: active output is not mistaken for a stalled model."""
import http.client,json,re,socket,sqlite3,threading,time,urllib.error,urllib.request
from pathlib import Path

def progress(root,jobid,phase,started,tokens=0):
 if not jobid or not (Path(root)/'studio.sqlite').is_file():return
 d=sqlite3.connect(str(Path(root)/'studio.sqlite'),timeout=3)
 try:
  row=d.execute('SELECT status,payload FROM jobs WHERE id=?',(jobid,)).fetchone()
  if row:
   if row[0]=='cancelled':raise ValueError('A feladatot leállítottad.')
   payload=json.loads(row[1]);payload['generation']=dict(provider='local',phase=phase,seconds=round(time.monotonic()-started,1),tokens=tokens)
   d.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),jobid));d.commit()
 finally:d.close()

# Hungarian text, URLs and JSON tokenize denser than English (about 2.3-2.6 characters per
# token with Qwen); 3.0 let research prompts overflow and Ollama then cut the task itself.
CHARS_PER_TOKEN=2.4
MARK='\n…[ORBIT: rövidítve a kontextusablakhoz]…\n'
# Tool loops: share of the room the opening (rules + task) may keep, room kept free for the next
# round's new content, the smallest size a later message is cut to, and room for tool definitions.
OPENING_SHARE=.95
RESERVE=2000
LATER_FLOOR=1200
MIN_KEEP=300
TINY_KEEP=120
TINY_SLACK=1500
TOOLS_ALLOWANCE=2500

def fit(messages,options,tools=None):
 """Keep the prompt inside the context window. Ollama otherwise drops the oldest messages,
 the task itself included ("no user query found"). Tool outputs shrink first, then the middle
 of the longest user/system text; the first and last parts of every message are kept. If that
 is still too much, the oldest tool exchanges go, never the task or the latest results."""
 ctx=int(options.get('num_ctx') or 8192);room=int((ctx-int(options.get('num_predict') or 1024)-400)*CHARS_PER_TOKEN)-len(json.dumps(tools or []))
 msgs=[dict(m) for m in messages]
 size=lambda:sum(len(m.get('content') or '') if isinstance(m.get('content'),str) else 0 for m in msgs)+sum(len(json.dumps(m.get('tool_calls',''))) for m in msgs)
 def shrink(m,keep):
  # Only a real reduction counts: the marker itself adds characters, so a message just above
  # the floor would otherwise be "shortened" forever without getting smaller.
  c=m['content'];head=int(keep*.7);out=c[:head]+MARK+c[-(keep-head):]
  if len(out)>=len(c):return False
  m['content']=out;return True
 def squeeze(kinds,floor):
  while size()>room:
   cands=[m for m in msgs if m.get('role') in kinds and isinstance(m.get('content'),str) and len(m['content'])>floor+len(MARK)]
   if not cands:break
   m=max(cands,key=lambda x:len(x['content']))
   if not shrink(m,max(floor,len(m['content'])-(size()-room)-200)):break
 if tools or any(m.get('role') in ('assistant','tool') for m in msgs):stable_cuts(msgs,options,tools,shrink)
 else:squeeze(('tool',),1500);squeeze(('user','system'),3000)
 dropped=0
 while size()>room:
  calls=[i for i,m in enumerate(msgs) if m.get('role')=='assistant' and m.get('tool_calls')]
  if len(calls)<2:break
  i=calls[0];j=i+1
  while j<len(msgs) and msgs[j].get('role')=='tool':j+=1
  del msgs[i:j];dropped+=1
 if dropped and msgs and msgs[0].get('role')=='system' and isinstance(msgs[0].get('content'),str):
  msgs[0]['content']+='\n[ORBIT: '+str(dropped)+' korábbi eszközhívás eredménye kimaradt a kontextusablak miatt.]'
 squeeze(('tool',),500)
 # Last resort for very small windows: the rules and the task themselves, down to a short core.
 squeeze(('user','system'),1500)
 return msgs

def stable_cuts(msgs,options,tools,shrink):
 """Agent tool loops re-send the whole conversation every round, and the model server reuses its
 cached prefix only while the earlier messages stay byte-identical (measured on the 27B: 69 s of
 prompt reading drops to 20 s). So every cut here depends only on what came before a message,
 never on later tool results or on whether tools are still offered: the opening (rules + task)
 is cut once, by a fixed share of the room; each later message when it is first sent."""
 text=lambda ms:sum(len(m.get('content') or '') if isinstance(m.get('content'),str) else 0 for m in ms)+sum(len(json.dumps(m.get('tool_calls',''))) for m in ms)
 stable=int((int(options.get('num_ctx') or 8192)-int(options.get('num_predict') or 1024)-400)*CHARS_PER_TOKEN)-max(TOOLS_ALLOWANCE,len(json.dumps(tools or [])))
 first=next((i for i,m in enumerate(msgs) if m.get('role') in ('assistant','tool')),len(msgs))
 opening=msgs[:first];cap=int(stable*OPENING_SHARE)
 while text(opening)>cap:
  cands=[m for m in opening if isinstance(m.get('content'),str) and len(m['content'])>3000+len(MARK)]
  if not cands:break
  m=max(cands,key=lambda x:len(x['content']))
  if not shrink(m,max(3000,len(m['content'])-(text(opening)-cap)-200)):break
 used=text(opening)
 for m in msgs[first:]:
  # Room for later rounds first; once it runs out, what is left, down to a short excerpt.
  # When the room is used up, newer messages shrink to a short note instead of the fallback dropping
  # older ones: older messages are what the server has cached.
  avail=stable-used
  keep=avail-RESERVE if avail-RESERVE>=LATER_FLOOR else avail-TINY_SLACK if avail-TINY_SLACK>=MIN_KEEP else TINY_KEEP
  if isinstance(m.get('content'),str) and len(m['content'])>keep+len(MARK):shrink(m,keep)
  used+=text([m])

# How long a stream may stay silent mid-answer before the call counts as stalled. The 27B (5 tokens/s)
# once went quiet for 30 s after 22 tokens and an 11-minute build was lost with it (cycle 167).
SILENCE=30
SLOW_SILENCE=120

def silence_limit(model):
 m=re.search(r':(\d+)b',str(model or ''))
 return SLOW_SILENCE if m and int(m.group(1))>=20 else SILENCE

def chat(port,data,timeout,root):
 data=dict(data);jobid=data.pop('_orbit_progress_job',None);partial_ok=data.pop('_orbit_partial_ok',False);data['stream']=True
 # Preserve system rules and the current request; bound only old history and tool outputs.
 history=data.get('messages',[])
 data['messages']=fit([dict(m,content=m['content'][:12000]) if m.get('role')=='tool' and isinstance(m.get('content'),str) else m for m in history],data.get('options') or {},data.get('tools'))
 quiet=silence_limit(data.get('model'));started=time.monotonic();requested_budget=data.pop('_orbit_budget',None);budget=min(1800,max(5,float(requested_budget))) if requested_budget else max(15,min(1800,timeout))
 from reply_stream import publish
 publish(root,jobid,'')
 progress(root,jobid,'Modell betöltése és bemenet feldolgozása',started)
 # Ollama answers only after loading the model and reading the whole prompt: a 27B model needs
 # well over a minute for that, so the first byte may take up to the call's own budget.
 # A loopback connection opened here (not by urllib), so a background call can hand the model to a waiting chat at
 # any moment, even while the model is still reading the prompt: closing the socket makes Ollama stop generating.
 from inference_gate import is_background,chat_waiting
 conn=http.client.HTTPConnection('127.0.0.1',int(port),timeout=min(600,max(5,min(timeout,budget))))
 try:conn.connect()
 except OSError as error:raise urllib.error.URLError(error) from error
 # http.client may hand the socket to the response and forget it; keep our own reference.
 sock=conn.sock;watch=threading.Event();yielded=[]
 def watchdog():
  while not watch.wait(2):
   if chat_waiting(root):
    yielded.append(True)
    try:sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
    return
 if is_background():threading.Thread(target=watchdog,daemon=True).start()
 try:
  return _stream(conn,port,data,timeout,budget,quiet,started,root,jobid,partial_ok)
 except Exception as error:
  if yielded:
   from execution_queue import DeferredExecution
   raise DeferredExecution('A chat elsőbbséget kapott: ez a háttérfeladat átadta neki a helyi modellt, és utána folytatódik.',15) from None
  raise
 finally:
  watch.set();conn.close()

def _stream(conn,port,data,timeout,budget,quiet,started,root,jobid,partial_ok):
 from reply_stream import publish
 last=0;tokens=0;content=[];thinking=[];calls=[];meta={};done=False
 try:
  conn.request('POST','/api/chat',body=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
  response=conn.getresponse()
 except socket.timeout as error:raise urllib.error.URLError(error) from error
 except OSError as error:raise urllib.error.URLError(error) from error
 if response.status>=400:raise urllib.error.HTTPError('http://127.0.0.1:'+str(port)+'/api/chat',response.status,response.reason,response.headers,response)
 with response:
  total=0
  while True:
   if time.monotonic()-started>budget:raise TimeoutError('A teljes modellfuttatás időkerete lejárt.')
   try:response.fp.raw._sock.settimeout(min(quiet,max(.2,budget-(time.monotonic()-started))))
   except (AttributeError,OSError):pass
   try:line=response.readline(2*1024*1024+1)
   except TimeoutError as error:
    if time.monotonic()-started>=budget:raise
    # Said precisely (and still "nem válaszolt", so the step is retried as a transient failure).
    raise ValueError('A helyi modell '+str(quiet)+' mp-ig nem válaszolt a válasz közben ('+str(tokens)+' token után, '+str(round(time.monotonic()-started))+' mp-nél); átmeneti akadás, a lépés újrapróbálható.') from error
   if not line:break
   total+=len(line)
   if total>8*1024*1024 or len(line)>2*1024*1024:raise ValueError('Túl nagy helyi modellválasz.')
   if not line.strip():continue
   event=json.loads(line)
   if event.get('error'):raise ValueError('A helyi modell hibát jelzett: '+str(event['error'])[:300])
   msg=event.get('message',{})
   # Once the model writes, the answer is finished rather than cut off by the reading-time budget; only a real
   # stall (no new token for the silence limit) stops it.
   if (msg.get('content') or msg.get('thinking')) and not tokens:budget=max(budget,time.monotonic()-started+600)
   if msg.get('content'):content.append(msg['content']);tokens+=1
   # Some local models answer into the reasoning channel even with think=False; keep it as a fallback.
   if msg.get('thinking'):thinking.append(msg['thinking']);tokens+=1
   if msg.get('tool_calls'):calls.extend(msg['tool_calls'])
   if time.monotonic()-last>.35:
    publish(root,jobid,''.join(content))
    progress(root,jobid,'Válasz készül' if content or calls else 'Bemenet feldolgozása',started,tokens);last=time.monotonic()
   if event.get('done'):meta=event;done=True;break
 if not done:raise ValueError('A modellkapcsolat a válasz befejezése előtt megszakadt. Részleges tervet nem hajtottam végre.')
 # A build answer cut off at its limit still holds complete files: its caller keeps those (salvage) and retries the rest
 # with a shorter-answer note. Any other cut-off JSON plan is never executed.
 if meta.get('done_reason')=='length' and data.get('format') and not partial_ok:raise ValueError('A terv túl hosszú lett. Részleges műveletsor nem hajtható végre; kérj kisebb lépéseket.')
 meta['message']=dict(role='assistant',content=''.join(content))
 # Reasoning is never kept, except when it is the whole answer.
 if thinking and not content:meta['message']['thinking']=''.join(thinking)
 if calls:meta['message']['tool_calls']=calls
 progress(root,jobid,'Válasz megérkezett',started,tokens);return meta
