"""Opt-in outcome notifications. No arbitrary recipient or message tool for agents.

Only finished videos (from any project) and successful YouTube uploads are worth a phone
notification. Stopped or failed work never notifies (the owner, 11 Nov: no messages about stops). Internal steps, analyses and chat-command
bookkeeping never notify (chat requests already get their own reply). One message per run.
"""
import json
import connections

def _title(studio,payload):
 row=studio.db.execute('SELECT query,data FROM short_runs WHERE id=?',(payload.get('run'),)).fetchone() if payload.get('run') else None
 if not row:return ''
 try:data=json.loads(row['data'])
 except ValueError:data={}
 meta=data.get('metadata') if isinstance(data.get('metadata'),dict) else {}
 return str(meta.get('title') or (data.get('source_bundle') or {}).get('topic') or row['query'] or '')[:120]

def _reason(error):
 e=str(error or '').strip().split('\n')[0]
 if 'időkeret' in e or 'nem válaszolt' in e:return 'a helyi AI nem válaszolt időben'
 if 'kapcsolódni' in e:return 'a helyi AI nem volt elérhető'
 return (e[:140]+'…') if len(e)>140 else e or 'ismeretlen hiba'

def message(studio,job,row):
 """(dedupe key, text) for an outcome worth a notification, otherwise None."""
 payload=json.loads(row['payload'] or '{}')
 title=_title(studio,payload)
 quoted='\n„'+title+'”' if title else ''
 if job['kind']=='graph':
  if row['status']=='done' and payload.get('auto_step')=='verify':
   return 'run:'+str(payload.get('run')),'✅ Elkészült egy új videó'+quoted+'\nAz ORBIT Publikálás fülén nézheted meg.'
  if row['status']=='done' and not payload.get('auto_step'):return made_video(studio,job)
  return None
 if job['kind']=='youtube_upload':
  if row['status']=='done':return 'upload:'+job['id'],'📤 Feltöltve a YouTube-ra'+quoted
  return None
 if row['status']=='done':return made_video(studio,job)
 return None

def made_video(studio,job):
 """A video this job created (an own animation, a chat-generated clip, any project), keyed by the file."""
 art=studio.db.execute("SELECT a.id,a.name,a.path,p.name project FROM artifacts a LEFT JOIN projects p ON p.id=a.project WHERE a.job=? AND a.kind='video' ORDER BY a.created DESC LIMIT 1",(job['id'],)).fetchone()
 if not art:return None
 name=str(art['name'] or '').rsplit('.',1)[0][:120]
 return 'video:'+art['id'],'✅ Elkészült egy új videó'+(' · '+art['project'] if art['project'] else '')+('\n„'+name+'”' if name else '')

def finished_video(studio,payload):
 """The rendered MP4 of a finished run, when it fits a Telegram bot upload (50 MB)."""
 row=studio.db.execute('SELECT project,data FROM short_runs WHERE id=?',(payload.get('run'),)).fetchone() if payload.get('run') else None
 if not row:return None
 try:saved=(json.loads(row['data']).get('render') or {}).get('saved')
 except ValueError:return None
 if not saved:return None
 try:path=studio.safe_path(row['project'],saved)
 except Exception:return None
 return path if path.is_file() and path.stat().st_size<=49*1024*1024 else None

def artifact_file(studio,aid):
 from pathlib import Path
 row=studio.db.execute('SELECT path FROM artifacts WHERE id=?',(aid,)).fetchone()
 path=Path(row['path']) if row and row['path'] else None
 return path if path and path.is_file() and path.stat().st_size<=49*1024*1024 else None

def send_video(path,chat_id,caption,timeout=120):
 """sendVideo as multipart upload to the owner's own paired chat."""
 import urllib.request,uuid
 token=connections.secret('telegram')
 if not token:raise ValueError('Nincs Telegram-token.')
 boundary='orbit'+uuid.uuid4().hex
 def field(name,value):return ('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"\r\n\r\n'+str(value)+'\r\n').encode()
 body=field('chat_id',chat_id)+field('caption',caption[:1000])+field('supports_streaming','true')
 body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="video"; filename="'+path.name+'"\r\nContent-Type: video/mp4\r\n\r\n').encode()+path.read_bytes()+('\r\n--'+boundary+'--\r\n').encode()
 req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendVideo',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as r:return json.loads(r.read(1024*1024)).get('ok') is True

def notify(studio,job):
 cfg=connections.settings()['providers'].get('telegram',{})
 if not cfg.get('notifications') or not cfg.get('chat_id') or not connections.allowed('telegram'):return
 if job['kind'] not in ('graph','youtube_upload','command_apply','control_apply','media'):return
 row=studio.db.execute('SELECT status,error,payload FROM jobs WHERE id=?',(job['id'],)).fetchone()
 if not row or row['status'] not in ('done','failed'):return
 found=message(studio,job,row)
 if not found:return
 key,text=found
 studio.db.execute('CREATE TABLE IF NOT EXISTS notification_delivery(job TEXT PRIMARY KEY,status TEXT)')
 # Keyed by run, so one production sends at most one message however many steps end.
 changed=studio.db.execute("INSERT OR IGNORE INTO notification_delivery VALUES(?,'sending')",(key,)).rowcount;studio.db.commit()
 if not changed:return
 try:
  payload=json.loads(row['payload'] or '{}')
  video=(finished_video(studio,payload) if key.startswith('run:') else artifact_file(studio,key[6:]) if key.startswith('video:') else None) if row['status']=='done' and cfg.get('send_video',True) else None
  # The owner asked for the finished video itself on Telegram, not only the notice; the text goes along as caption.
  sent=False
  if video:
   try:sent=send_video(video,cfg['chat_id'],text)
   except Exception:sent=False
  if not sent:
   data=connections.http('telegram','sendMessage',dict(chat_id=cfg['chat_id'],text=text+('\n(A videó túl nagy a Telegramhoz, az ORBIT-ban nézheted meg.)' if key.startswith(('run:','video:')) and row['status']=='done' and not video else ''),disable_notification=False),timeout=10)
   sent=bool(data.get('ok'))
  status='sent' if sent else 'failed'
 except Exception:status='failed'
 studio.db.execute('UPDATE notification_delivery SET status=? WHERE job=?',(status,key));studio.db.commit()
