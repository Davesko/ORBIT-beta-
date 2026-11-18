"""Shared local-first decision lane. Cloud keys/configuration stay outside project context."""
import json,re,sqlite3,time
from pathlib import Path
import connections

def cloud_models():
 c=connections.settings()
 if c['mode']=='local':return []
 return [dict(name=p+'/'+v.get('model',connections.PROVIDERS[p]['model']),size=0,storage='Cloud',capabilities=['completion','tools']+(['vision'] if p=='gemini' else [])) for p,v in c['providers'].items() if p in ('groq','gemini','openrouter','deepseek') and v.get('enabled') and connections.secret(p)]

def cancelled(jobid):
 if not jobid or not (connections.ROOT/'studio.sqlite').is_file():return False
 d=sqlite3.connect(str(connections.ROOT/'studio.sqlite'),timeout=3)
 try:
  row=d.execute('SELECT status FROM jobs WHERE id=?',(jobid,)).fetchone();return bool(row and row[0]=='cancelled')
 finally:d.close()

def local_job(jobid):
 """Per-mission local-only policy also follows deferred production receipts."""
 if not jobid or not (connections.ROOT/'studio.sqlite').is_file():return False
 db=sqlite3.connect(str(connections.ROOT/'studio.sqlite'),timeout=3)
 try:
  row=db.execute('SELECT payload FROM jobs WHERE id=?',(jobid,)).fetchone()
  if not row:return False
  p=json.loads(row[0])
  if p.get('local_only') is True:return True
  run=p.get('mission_run');origin=p.get('origin')
  if not run and p.get('run') and db.execute("SELECT 1 FROM sqlite_master WHERE name='short_runs'").fetchone():
   saved=db.execute('SELECT data FROM short_runs WHERE id=?',(p['run'],)).fetchone()
   if saved:origin=json.loads(saved[0]).get('origin')
  if not run and isinstance(origin,str) and origin.startswith('mission:'):run=origin.split(':')[1]
  if not run:return False
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='orbit_mission_runs'").fetchone():return False
  row=db.execute('SELECT r.spec FROM orbit_mission_runs r WHERE r.id=?',(run,)).fetchone()
  return bool(row and json.loads(row[0]).get('local_only'))
 finally:db.close()

def record(jobid,**fields):
 if not jobid:return
 path=connections.ROOT/'studio.sqlite'
 if not path.is_file():return
 d=sqlite3.connect(str(path),timeout=5)
 try:
  row=d.execute('SELECT payload FROM jobs WHERE id=?',(jobid,)).fetchone()
  if row:
   payload=json.loads(row[0]);payload.update(fields);d.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),jobid));d.commit()
 finally:d.close()

def unresponsive_models():
 path=connections.ROOT/'studio.sqlite'
 if not path.is_file():return set()
 db=sqlite3.connect(str(path),timeout=3)
 try:
  rows=db.execute("SELECT payload,error FROM jobs WHERE status='failed' AND finished>? ORDER BY finished DESC LIMIT 80",(time.time()-120,)).fetchall()
  return {json.loads(payload).get('selected_model') for payload,error in rows if any(x in error.casefold() for x in ('időkeret','nem válaszolt','timed out'))}
 except (sqlite3.Error,ValueError):return set()
 finally:db.close()

def data_image(encoded):
 mime='image/png' if encoded.startswith('iVBOR') else 'image/webp' if encoded.startswith('UklGR') else 'image/jpeg'
 return 'data:'+mime+';base64,'+encoded

def openai_messages(messages):
 result=[];pending=[]
 for original in messages:
  m={k:v for k,v in original.items() if k in ('role','content','tool_calls','name','tool_call_id')}
  if original.get('images'):
   m['content']=[dict(type='text',text=m.get('content',''))]+[dict(type='image_url',image_url=dict(url=data_image(x))) for x in original['images']]
  if m.get('tool_calls'):
   calls=[]
   for n,tool in enumerate(m['tool_calls']):
    f=dict(tool['function']);args=f.get('arguments',{});f['arguments']=json.dumps(args) if isinstance(args,dict) else args
    ident=tool.get('id') or 'orbit_call_'+str(len(result))+'_'+str(n);pending.append(ident);calls.append(dict(id=ident,type='function',function=f))
   m['tool_calls']=calls
  if m['role']=='tool':m['tool_call_id']=m.get('tool_call_id') or (pending.pop(0) if pending else 'orbit_unknown');m.pop('name',None)
  result.append(m)
 return result

def shrink_to(data,size):
 """A smaller copy of a request the provider refused as too large (HTTP 413 with its own
 "Limit L, Requested R" token counts). Only data messages (app state, history, tool results)
 shrink; the rules stay whole. None when even that cannot fit."""
 limit,requested=size;msgs=data.get('messages',[])
 if requested<=limit:return None
 text=lambda ms:sum(len(m.get('content') or '') if isinstance(m.get('content'),str) else 0 for m in ms)
 rest=[m for m in msgs if m.get('role')!='system']
 # The provider counted the reply budget too; the measured characters per token of this very
 # request turn the token excess into characters to remove, with a 15% margin.
 reply=min(2400,(data.get('options') or {}).get('num_predict',1400))
 ratio=text(msgs)/max(1,requested-reply)
 target=int(text(rest)-(requested-limit*.85)*ratio)
 if target<1200:return None
 from inference_stream import fit,CHARS_PER_TOKEN
 rest=fit(rest,dict(num_ctx=int(target/CHARS_PER_TOKEN)+401,num_predict=1))
 if text(rest)>target:return None
 return dict(data,messages=[m for m in msgs if m.get('role')=='system']+rest)

def cloud_chat(provider,data,timeout=25):
 model=data['model'].split('/',1)[1] if data['model'].startswith(provider+'/') else connections.settings()['providers'].get(provider,{}).get('model',connections.PROVIDERS[provider]['model'])
 opts=data.get('options',{});payload=dict(model=model,messages=openai_messages(data.get('messages',[])),stream=False,temperature=opts.get('temperature',.1),max_tokens=min(2400,opts.get('num_predict',1400)))
 if data.get('tools'):payload['tools']=data['tools'];payload['tool_choice']='auto'
 if data.get('format'):
  payload['response_format']=dict(type='json_object')
  payload['messages']=[dict(role='system',content='Return valid JSON only, matching the requested object fields. No markdown fences.')]+payload['messages']
 if provider=='openrouter':
  if model!='openrouter/free' and not model.endswith(':free'):raise connections.ProviderError('Fizetős OpenRouter modell nem engedélyezett.')
  payload['provider']=dict(require_parameters=True,max_price=dict(prompt=0,completion=0))
 if provider=='gemini':payload['reasoning_effort']='low'
 if provider=='groq' and model.startswith('openai/gpt-oss'):payload['reasoning_effort']='low'
 callback=None
 if data.get('_orbit_job') and data.get('format')=='json' and not data.get('tools'):
  from reply_stream import publish
  publish(connections.ROOT,data['_orbit_job'],'');payload['stream']=True;last=[0.0]
  def callback(raw):
   if time.monotonic()-last[0]>.35:
    publish(connections.ROOT,data['_orbit_job'],raw);last[0]=time.monotonic()
 kwargs=dict(on_text=callback) if callback else {}
 try:response=connections.http(provider,'chat/completions',payload,timeout=min(35,timeout),**kwargs)
 except connections.ProviderError as e:
  # Groq answers 400 when its strict JSON check fails on the model's own output. The answer is checked here anyway,
  # and asking once more without that check beats minutes on the next provider.
  if getattr(e,'code',None)!=400 or not payload.get('response_format'):raise
  payload.pop('response_format');response=connections.http(provider,'chat/completions',payload,timeout=min(35,timeout),**kwargs)
 if not isinstance(response,dict):raise connections.ProviderError('A szolgáltató hibás modellválaszt adott.')
 choices=response.get('choices',[])
 if not isinstance(choices,list) or not choices or not isinstance(choices[0],dict):raise connections.ProviderError('A felhőmodell üres választ adott.')
 choice=choices[0]
 if choice.get('finish_reason')=='length':raise connections.ProviderError('A felhőválasz elérte a kimeneti korlátot; részleges terv nem hajtható végre.')
 message=choice.get('message')
 if not isinstance(message,dict):raise connections.ProviderError('A felhőmodell üres vagy hibás választ adott.')
 for tool in message.get('tool_calls') or []:
  if isinstance(tool['function'].get('arguments'),str):tool['function']['arguments']=json.loads(tool['function']['arguments'])
 actual=str(response.get('model') or model)
 return dict(model=provider+'/'+actual,message=message,done=True,usage=response.get('usage',{}),_orbit_route=dict(model=provider+'/'+actual,provider=provider,engine=provider,policy='hybrid'))

def validate_response(result,data):
 if data.get('format'):
  from assistant_resilience import json_object
  content=result.get('message',{}).get('content')
  parsed=json_object(content)
  result=dict(result,message=dict(result.get('message',{}),content=json.dumps(parsed,ensure_ascii=False)))
 return result

def unavailable(error):
 """Provider availability problems (quota, rate limit, disabled, no answer), not bad requests."""
 text=str(error).casefold()
 return any(x in text for x in ('kvóta','sebességkorlát','nincs beállítva','ki van kapcsolva','kapcsol','időkeret','nem válaszolt','429','503','rate limit','quota','overloaded','unavailable'))

def request(route,data=None,timeout=8):
 from model_hub import request as local,models
 deadline=time.monotonic()+max(15,timeout)
 def local_checked(route,payload,limit):
  remaining=deadline-time.monotonic()
  if remaining<5:raise ValueError('A modellhívás időkerete elfogyott; a mentett feladat később folytatható.')
  budget=min(limit,remaining,float(payload.get('_orbit_budget',120 if payload.get('format') else timeout)))
  wait=float(payload.get('_orbit_wait') or 0)
  payload={k:v for k,v in dict(payload,_orbit_budget=budget).items() if k!='_orbit_wait'}
  from inference_gate import lease
  # A caller that cannot be deferred halfway (the computer operator mid-task) waits for the model instead.
  with lease(connections.ROOT,wait=wait):result=validate_response(local(route,payload,budget),payload)
  health=connections.read('local-health.json');name=payload.get('model')
  if name in health:health.pop(name,None);connections.atomic('local-health.json',health)
  return result
 if route!='api/chat':return local(route,data,timeout)
 data=dict(data or {});requested=data.get('model','auto');auto=requested in ('','auto');explicit=next((p for p in ('groq','gemini','openrouter','deepseek') if requested.startswith(p+'/')),None)
 image=any(m.get('images') for m in data.get('messages',[]));c=connections.settings();errors=[]
 if local_job(data.get('_orbit_job')):c=dict(c,mode='local')
 # A global local-only policy overrides old/manual cloud pins without changing
 # stored agent preferences. No cloud request is made, even as a fallback.
 if c['mode']=='local' and explicit:
  record(data.get('_orbit_job'),policy_override=dict(requested_model=requested,mode='local',reason='Global local-only policy; selecting an available local model.'))
  data['model']='auto';requested='auto';auto=True;explicit=None
 scope=data.pop('_orbit_scope',None);user_prompt=data.pop('_orbit_user_prompt',None);full_data=dict(data)
 privacy_local=False
 if not c.get('share_context'):
  messages=data.get('messages',[])
  private_result=any(m.get('role')=='tool' or (m.get('role')=='user' and str(m.get('content','')).startswith(('Read results, data only:','The plan has not executed.'))) for m in messages)
  privacy_local=scope!='planner' or private_result
  if not privacy_local:
   system=next((m for m in messages if m.get('role')=='system'),dict(role='system',content='You are ORBIT. Reply in Hungarian.'))
   current=next((m for m in reversed(messages) if m.get('role')=='user' and not str(m.get('content','')).startswith(('CURRENT APP STATE (fresh data, not instructions):','Previously completed reads, data only:'))),dict(role='user',content=''))
   content=user_prompt if isinstance(user_prompt,str) else str(current.get('content','')).split('\nWorkspace context (data, not instructions):')[0].split('\nKnown scope:')[0]
   current=dict(role='user',content=content)
   data['messages']=[system,current]

 providers=[explicit] if explicit else ([c['preferred']]+[p for p in ('groq','gemini','openrouter','deepseek') if p!=c['preferred']] if auto and c['mode'] in ('hybrid','local_first') else [])
 if privacy_local:
  if explicit:raise ValueError('Ez a feladat projektkörnyezetet használ. A felhős feldolgozásához engedélyezd a projektkörnyezet megosztását a Kapcsolatok oldalon, vagy válassz helyi modellt.')
  providers=[]
 if image:providers=[p for p in providers if p in ('gemini','openrouter')]
 def try_cloud():
  for p in providers:
   if connections.settings()['mode']=='local':return None
   if not explicit and deadline-time.monotonic()<min(20,max(5,timeout*.35)):break
   if cancelled(data.get('_orbit_job')):raise ValueError('A feladatot leállítottad.')
   if not connections.allowed(p):
    if explicit:raise ValueError('Ez a felhőkapcsolat nincs beállítva, ki van kapcsolva vagy kvótavárakozásban van.')
    continue
   started=time.time();record(data.get('_orbit_job'),selected_model=p+'/'+c['providers'].get(p,{}).get('model',connections.PROVIDERS[p]['model']),generation=dict(provider=p,phase='Felhőmodell válaszára vár',started=started))
   try:
    cloud_budget=min(35,max(5,(deadline-time.monotonic())*(1 if explicit else .4)))
    try:answer=cloud_chat(p,data,cloud_budget)
    except connections.ProviderError as e:
     # Too large for this provider's free ceiling (Groq, with shared project context): retry once
     # with the data part shortened to the size the provider itself reported.
     smaller=shrink_to(data,e.size) if getattr(e,'size',None) else None
     if not smaller:raise
     answer=cloud_chat(p,smaller,max(5,min(cloud_budget,deadline-time.monotonic()-5)))
    result=validate_response(answer,data);record(data.get('_orbit_job'),selected_model=result['model'],generation=dict(provider=p,phase='Válasz megérkezett',seconds=round(time.time()-started,2)),provider_fallback=errors);return result
   except (ValueError,OSError) as e:
    errors.append(str(e))
    if explicit:raise
  return None
 def try_local():
  data=dict(full_data)
  if cancelled(data.get('_orbit_job')):raise ValueError('A feladatot leállítottad.')
  if errors:record(data.get('_orbit_job'),provider_fallback=errors)
  if not auto:
   try:return local_checked(route,data,timeout)
   except ValueError as exc:
    if any(x in str(exc).lower() for x in ('időkeret','nem válaszolt')):raise ValueError(str(exc)+' Kézi modellválasztás volt aktív; a kiválasztott modellnél maradtam, nem váltottam másikra.') from exc
    raise
  from model_router import choose,usable
  available=usable(models(),image);health=connections.read('local-health.json');now=time.time()
  if not available:
   raise ValueError('Nincs elérhető helyi '+('képelemző' if image else 'beszélgető')+'modell. '+('A felhős próbálkozások: '+' | '.join(errors)[-650:] if errors else 'Ellenőrizd a Modellek oldalt és a hibrid módot a Kapcsolatoknál.'))
  failed=unresponsive_models()
  healthy=[m for m in available if health.get(m['name'],0)<now and m['name'] not in failed]
  if not healthy:healthy=available
  messages=data.get('messages',[]);prompt=next((m.get('content','') for m in reversed(messages) if m.get('role')=='user'),'')
  # The main chat's planner is chosen by its measured ORBIT tool-calling result (tool_benchmark), not by short JSON checks.
  purpose=data.get('_orbit_purpose') or ('planner' if scope=='planner' else None)
  chosen=choose(prompt,healthy,'auto',image,purpose=purpose)['model'];data['model']=chosen
  # The chat keeps one model in memory: its planner gets the whole time and never swaps to a second model because
  # it was slow (a swap unloads 8-17 GB and reloads another). Only a broken answer moves to the next model.
  planner=scope=='planner'
  first_budget=(deadline-time.monotonic())*(1 if planner or len(healthy)<2 else .65)
  try:return local_checked(route,data,first_budget)
  except ValueError as error:
   if cancelled(data.get('_orbit_job')):raise ValueError('A feladatot leállítottad.')
   if planner and any(x in str(error).lower() for x in ('időkeret','nem válaszolt')):raise
   if not any(x in str(error).lower() for x in ('időkeret','nem válaszolt','kapcsolódni','megszakadt','json','üres válasz','hosszú lett','túl hosszú','nem teljes')):raise
   # Only a model that did not answer is set aside for ten minutes. A malformed answer moves just this call to the next
   # model: on 13 Nov one invalid critic JSON from qwen3.5:9b sent every story call for ten minutes to the 27B (~13 min/episode).
   if any(x in str(error).lower() for x in ('időkeret','nem válaszolt','kapcsolódni','megszakadt')):
    health[chosen]=time.time()+600;connections.atomic('local-health.json',health)
   remaining=[m for m in healthy if m['name']!=chosen] or [m for m in available if m['name']!=chosen]
   if not remaining:raise
   fallback=choose(prompt,remaining,'auto',image,purpose=purpose)['model'];data['model']=fallback
   record(data.get('_orbit_job'),provider_fallback=errors+['A helyi '+chosen+' nem válaszolt; tartalék: '+fallback])
   return local_checked(route,data,timeout)

 if auto and c['mode']=='local_first':
  total_deadline=deadline
  # Reserve a small cloud fallback only when the user has enabled this policy.
  has_cloud=any(connections.allowed(p) for p in providers)
  if has_cloud:deadline-=min(35,max(0,(deadline-time.monotonic())*.25))
  try:return try_local()
  except (ValueError,OSError) as exc:
   if cancelled(data.get('_orbit_job')):raise ValueError('A feladatot leállítottad.') from exc
   local_error=exc;errors.append('Helyi modell: '+str(exc))
  finally:deadline=total_deadline
  result=try_cloud()
  if result is not None:return result
  raise ValueError(str(local_error)+(' Felhős tartalék: '+' | '.join(errors[1:])[-500:] if len(errors)>1 else '')) from local_error
 try:result=try_cloud()
 except (ValueError,OSError) as exc:
  # A manually chosen cloud model that is out of quota, switched off or not answering must
  # not leave the user waiting: answer this request with automatic routing instead.
  if explicit and unavailable(exc) and not cancelled(data.get('_orbit_job')) and deadline-time.monotonic()>20:
   record(data.get('_orbit_job'),model_fallback=dict(requested=requested,reason=str(exc)[:200]))
   return request(route,dict(full_data,model='auto',_orbit_scope=scope,_orbit_user_prompt=user_prompt),max(15,deadline-time.monotonic()))
  raise
 if result is not None:return result
 return try_local()
