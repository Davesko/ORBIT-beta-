"""Native-only YouTube configuration and upload queue. Credentials never enter projects."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import math


def validate_short(path):
    try:
        manifest=json.loads(path.with_suffix('.json').read_text())
        width,height,duration=(manifest[k] for k in ('width','height','duration'))
        valid=width==1080 and height==1920 and isinstance(duration,(int,float)) and math.isfinite(duration) and 0<duration<=180
        valid=valid and manifest['bytes']==path.stat().st_size
    except (OSError,ValueError,KeyError,TypeError):valid=False
    if not valid:raise ValueError('YouTube Shorts feltöltéshez ellenőrzött 1080×1920-as, legfeljebb 3 perces videó szükséges. Rendereld újra Shorts formátumban.')


def folder(root,pid):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',pid):raise ValueError('Érvénytelen projekt.')
    path=Path(root)/'integrations/youtube'/pid;path.mkdir(parents=True,exist_ok=True,mode=0o700);return path


def save_config(root,pid,raw):
    if len(raw)>20000:raise ValueError('Túl nagy OAuth-konfiguráció.')
    data=json.loads(raw);client=data.get('installed',{})
    if not re.fullmatch(r'[A-Za-z0-9._-]+\.apps\.googleusercontent\.com',client.get('client_id','')):raise ValueError('Google Desktop app OAuth JSON szükséges.')
    if client.get('auth_uri')!='https://accounts.google.com/o/oauth2/auth' and client.get('auth_uri')!='https://accounts.google.com/o/oauth2/v2/auth':raise ValueError('Érvénytelen Google-hitelesítési cím.')
    if client.get('token_uri')!='https://oauth2.googleapis.com/token':raise ValueError('Érvénytelen Google-tokenvégpont.')
    if not isinstance(client.get('client_secret'),str) or len(client['client_secret'])>1000:raise ValueError('Hiányzó kliensadat.')
    path=folder(root,pid)/'client.json'
    with os.fdopen(os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as handle:json.dump({'installed':client},handle)


def upload_status_text(receipt):
    state=receipt.get('processing_status')
    if state=='failed' or receipt.get('processing') in ('failed','rejected','deleted'):
        return 'YouTube-feldolgozási hiba · ellenőrizd a YouTube Studiót'
    if state=='processing' or receipt.get('processing')=='uploaded':
        return 'Feltöltve · a YouTube még feldolgozza'
    if state=='succeeded' or receipt.get('processing')=='processed':
        return 'YouTube-feldolgozás kész'
    return 'Feltöltve · feldolgozás ellenőrzése szükséges'


def schedule_upload_refresh(root,pid,base):
    # A native UI read must never wait for a network request or restart an upload.
    runtime=Path(root)/'media-runtime/bin/python';stamp=base/'verification.started'
    if not runtime.is_file() or not any(base.glob('receipt-*.json')):return
    try:
        if stamp.exists() and time.time()-stamp.stat().st_mtime<60:return
        stamp.touch(mode=0o600)
        with (base/'verification.log').open('ab') as errors:
            subprocess.Popen([str(runtime),str(Path(__file__).with_name('youtube_runtime.py')),'refresh_uploads',str(root),pid],stdout=subprocess.DEVNULL,stderr=errors,start_new_session=True)
    except OSError:pass


def read_state(root,pid):
    base=folder(root,pid)
    def load(name):
        try:return json.loads((base/name).read_text())
        except (OSError,ValueError):return {}
    saved=load('status.json');auth=load('auth.json')
    if saved.get('connected'):schedule_upload_refresh(root,pid,base)
    return dict(configured=(base/'client.json').is_file(),connected=bool(saved.get('connected')),channel=saved.get('channel'),channel_id=saved.get('channel_id'),auth_pending=auth.get('status')=='waiting' and time.time()-auth.get('created',0)<310,error=auth.get('error',''),upload_policy='explicit_visibility_with_receipt',uploads=[json.loads(p.read_text()) for p in sorted(base.glob('receipt-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]])


def needs_reconnect(root):
    """Projects whose saved YouTube login was lost or revoked. A deliberate disconnect removes
    auth.json, so it never appears here; every later upload of these projects would fail."""
    base=Path(root)/'integrations/youtube';out=[]
    if not base.is_dir():return out
    for folder_path in sorted(base.iterdir()):
        try:
            if not (folder_path/'client.json').is_file() or not (folder_path/'auth.json').is_file():continue
            status=json.loads((folder_path/'status.json').read_text()) if (folder_path/'status.json').is_file() else {}
            auth=json.loads((folder_path/'auth.json').read_text())
        except (OSError,ValueError):continue
        if not status.get('connected') and auth.get('status')=='failed' and auth.get('error'):out.append(dict(project=folder_path.name,error=str(auth['error'])[:300]))
    return out


def connect(root,pid):
    base=folder(root,pid)
    if not (base/'client.json').exists():raise ValueError('Előbb importáld a Google Cloud Desktop app OAuth JSON-fájlt.')
    if read_state(root,pid)['auth_pending']:raise ValueError('A belépés már folyamatban van a böngészőben.')
    path=base/'auth.json';path.unlink(missing_ok=True)
    log=base/'connection.log'
    with log.open('ab') as errors:
        process=subprocess.Popen([str(Path(root)/'media-runtime/bin/python'),str(Path(__file__).with_name('youtube_runtime.py')),'connect',str(root),pid],stdout=subprocess.DEVNULL,stderr=errors,start_new_session=True)
    for _ in range(40):
        if path.exists():
            data=json.loads(path.read_text())
            if data.get('url'):return data['url']
            if data.get('error'):raise ValueError(data['error'])
        if process.poll() is not None:raise ValueError('A YouTube-csatlakozó nem indult el. Részletek a helyi kapcsolatnaplóban.')
        time.sleep(.1)
    raise ValueError('A böngészős bejelentkezés nem indult el időben.')


def upload_job(studio,job):
    import signal
    payload=json.loads(job['payload'])
    if payload.get('social_post'):
        # A post of the Publikálás-központ: any platform, the account's own login.
        from publish_hub import run_post
        return run_post(studio,job)
    base=folder(studio.root,job['project']);progress=base/('upload-'+job['id']+'.json')
    source=studio.safe_path(job['project'],payload['name'])
    if not source.is_file():raise ValueError('A renderelt videó nem található.')
    validate_short(source)
    request=dict(source=str(source),title=payload['title'],description=payload['description'],made_for_kids=payload['made_for_kids'],privacy=payload.get('privacy','private'),progress=str(progress))
    studio.job_stage(job['id'],'upload','YouTube-feltöltés indítása · '+request['privacy'],input_text=json.dumps(payload,ensure_ascii=False))
    with (base/'upload.log').open('ab') as errors:
        process=subprocess.Popen([str(studio.root/'media-runtime/bin/python'),str(Path(__file__).with_name('youtube_runtime.py')),'upload',str(studio.root),job['project']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True)
        raw=json.dumps(request).encode();first=True;start=time.monotonic();last=-1
        try:
            while True:
                try:output,_=process.communicate(raw if first else None,timeout=1);break
                except subprocess.TimeoutExpired:
                    first=False
                    if studio.cancelled(job['id']):raise ValueError('Feltöltés leállítva. Ha az átvitel már befejeződött, ellenőrizd a YouTube Studiót.')
                    if time.monotonic()-start>3600:raise ValueError('A feltöltés időkerete lejárt. Újraindítás előtt ellenőrizd a YouTube Studiót.')
                    if progress.exists():
                        data=json.loads(progress.read_text());percent=data.get('percent',0)
                        if percent!=last:studio.job_stage(job['id'],'upload','YouTube-feltöltés · '+request['privacy']+' · '+str(percent)+'%');last=percent
        except BaseException:os.killpg(process.pid,signal.SIGKILL);process.communicate();raise
    data=json.loads(output)
    if not data.get('ok'):raise ValueError(data.get('message','YouTube-feltöltési hiba.')+' ['+str(data.get('diagnostic_type','unknown'))+']')
    receipt=json.loads(progress.read_text())
    receipt.update(job=job['id'],title=payload['title'],created=time.time(),format='shorts_eligible',shorts_status='unconfirmed',url='https://www.youtube.com/shorts/'+data['id'],studio_url='https://studio.youtube.com/video/'+data['id']+'/edit')
    from youtube_runtime import atomic_json
    atomic_json(base/('receipt-'+job['id']+'.json'),receipt)
    if receipt.get('privacy')!=request['privacy']:raise ValueError('Feltöltve, de a tényleges láthatóság eltér a kéréstől: '+str(receipt.get('privacy'))+' · '+receipt['studio_url']+' · Ne töltsd fel újra.')
    return 'YouTube-videó feltöltve · '+str(receipt.get('privacy'))+' · '+receipt['url']

def queue_upload(studio,pid,artifact_id,title,description='',made_for_kids=False,privacy='public',run_id=None,retry=False,confirmed_absent=False):
    """Single upload lane, project-scoped artifacts and duplicate protection."""
    if privacy not in ('public','private','unlisted'):raise ValueError('Érvénytelen YouTube-láthatóság.')
    if not read_state(studio.root,pid)['connected']:raise ValueError('Előbb csatlakoztasd a YouTube-csatornát.')
    row=studio.db.execute("SELECT * FROM artifacts WHERE id=? AND project=? AND kind='video'",(artifact_id,pid)).fetchone()
    if not row:raise ValueError('Renderelt projektvideót válassz.')
    base=(studio.root/'projects'/pid).resolve();path=Path(row['path']).resolve()
    if base not in path.parents or path.relative_to(base).parts[0]!='renders' or path.suffix!='.mp4' or not path.is_file():raise ValueError('Csak meglévő renderelt MP4 tölthető fel.')
    validate_short(path)
    if not isinstance(title,str) or not title.strip() or len(title)>100:raise ValueError('1–100 karakteres cím szükséges.')
    if len(description.encode())>5000 or type(made_for_kids) is not bool:raise ValueError('Érvénytelen leírás vagy célközönség.')
    name=str(path.relative_to(base))
    previous=studio.db.execute("SELECT id,status FROM jobs WHERE project=? AND kind='youtube_upload' AND json_extract(payload,'$.name')=? ORDER BY created DESC LIMIT 1",(pid,name)).fetchone()
    if previous and previous['status'] in ('queued','running','done'):return dict(job=previous['id'],existing=True)
    if previous and not retry:raise ValueError('Ehhez a videóhoz már volt feltöltési kísérlet. Ellenőrizd a YouTube Studiót az ismételt feltöltés előtt; az app nem hoz létre automatikusan másolatot.')
    if previous and retry:
        if previous['status'] not in ('failed','cancelled'):raise ValueError('Csak sikertelen vagy leállított feltöltés próbálható újra.')
        base=folder(studio.root,pid)
        for prefix in ('receipt-','upload-'):
            try:record=json.loads((base/(prefix+previous['id']+'.json')).read_text())
            except FileNotFoundError:continue
            except (OSError,ValueError):raise ValueError('A feltöltési nyugta nem olvasható; előbb ellenőrizd a YouTube Studiót.')
            if record.get('id'):raise ValueError('A videó már kapott YouTube-azonosítót. Ne töltsd fel újra; ellenőrizd a YouTube Studióban.')
        if confirmed_absent is not True:raise ValueError('Az újrapróbálás előtt ellenőrizd és jelöld, hogy a videó nincs fent a YouTube Studióban.')
    aid=studio.rows('SELECT id FROM agents WHERE project=? ORDER BY rowid LIMIT 1',(pid,))[0]['id']
    jid=studio.enqueue(aid,'YouTube-feltöltés · '+title,'youtube_upload',payload=dict(name=name,title=title.strip(),description=description,made_for_kids=made_for_kids,privacy=privacy,run=run_id))
    return dict(job=jid,existing=False)
