"""Bounded public clip sources, explicit provenance and project isolation."""
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid
from urllib.parse import urlsplit,parse_qs

NETWORK_TOOLS={'find_stream_clips','download_stream_clip'}


def youtube_id(value):
    if not isinstance(value,str):return None
    parsed=urlsplit(value)
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):return None
    if parsed.hostname=='youtu.be':candidate=parsed.path.lstrip('/').split('/')[0]
    elif parsed.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
        candidate=parse_qs(parsed.query).get('v',[''])[0] if parsed.path=='/watch' else parsed.path.split('/')[2] if parsed.path.startswith(('/shorts/','/live/')) else ''
    else:return None
    return candidate if re.fullmatch(r'[A-Za-z0-9_-]{11}',candidate) else None


def twitch_id(value):
    """A public Twitch clip or past broadcast (twc:<slug>, twv:<digits>). A live channel is not a source."""
    if not isinstance(value,str):return None
    parsed=urlsplit(value)
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):return None
    parts=[p for p in parsed.path.split('/') if p]
    slug=None
    if parsed.hostname=='clips.twitch.tv' and len(parts)==1:slug=parts[0]
    elif parsed.hostname in ('twitch.tv','www.twitch.tv','m.twitch.tv'):
        if len(parts)==3 and parts[1]=='clip':slug=parts[2]
        elif len(parts)==2 and parts[0]=='videos' and parts[1].isdigit():return 'twv:'+parts[1]
    return 'twc:'+slug if slug and re.fullmatch(r'[A-Za-z0-9_-]{6,120}',slug) else None


def source_id(value):
    return youtube_id(value) or twitch_id(value)


def source_url(identifier):
    if identifier.startswith('twc:'):return 'https://clips.twitch.tv/'+identifier[4:]
    if identifier.startswith('twv:'):return 'https://www.twitch.tv/videos/'+identifier[4:]
    return 'https://www.youtube.com/watch?v='+identifier


def valid_source_id(identifier):
    return isinstance(identifier,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{11}|twc:[A-Za-z0-9_-]{6,120}|twv:\d{1,20}',identifier))


def schema(studio):
    studio.db.executescript('''
    CREATE TABLE IF NOT EXISTS clip_candidates(id TEXT PRIMARY KEY,project TEXT,video_id TEXT,metadata TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS clip_downloads(project TEXT,video_id TEXT,path TEXT,created REAL,PRIMARY KEY(project,video_id));
    CREATE TABLE IF NOT EXISTS short_runs(id TEXT PRIMARY KEY,project TEXT,query TEXT,data TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS short_automation(project TEXT PRIMARY KEY,enabled INTEGER DEFAULT 0,query TEXT,interval INTEGER DEFAULT 180,daily_limit INTEGER DEFAULT 3,next_run REAL DEFAULT 0,last_error TEXT DEFAULT '');
    ''')


def access_blocked(message):
    return any(term in str(message).casefold() for term in ('confirm you’re not a bot',"confirm you're not a bot",'youtube_auth_required','sign in to confirm'))

def cached_sources(studio,pid,query,limit=2,full_source=False):
    from short_style import source_matches
    result=[];identifier=source_id(query)
    for row in studio.rows('SELECT * FROM clip_downloads WHERE project=? ORDER BY created DESC',(pid,)):
        try:
            file=Path(row['path']).resolve();base=(studio.root/'projects'/pid).resolve()
            if base not in file.parents or not file.is_file() or file.stat().st_size==0:continue
            manifest=file.with_name('source.json');data=json.loads(manifest.read_text());meta=data['metadata'];duration=float(data['downloaded_duration'])
            if meta.get('id')!=row['video_id'] or not math.isfinite(duration) or duration<10:continue
            if identifier and meta['id']!=identifier:continue
            if not identifier and not source_matches(query,meta):continue
            if studio.safe_path(pid,data['project_file']).resolve()!=file:continue
            if full_source and not data.get('coverage',{}).get('complete'):continue
            result.append(dict(source_video=data['project_file'],manifest=str(manifest.relative_to(base)),duration=duration,metadata=meta,coverage=data.get('coverage',{}),reused_verified_download=True))
            if len(result)>=limit:break
        except (OSError,ValueError,KeyError,TypeError):continue
    return result


def network(studio,job,request):
    runtime=studio.root/'media-runtime/bin/python';node=studio.root/'media-runtime/bin/node'
    if not runtime.is_file() or not node.is_file():raise ValueError('Az internetes klipkereső futtatója nincs telepítve.')
    progress=studio.root/'logs'/('network-'+job+'.json');progress.parent.mkdir(exist_ok=True)
    request=dict(request,node=str(node),progress=str(progress));label='Kliprészlet letöltése' if request['operation']=='download' else 'Nyilvános videók keresése'
    studio.job_stage(job,'network',label,input_text=json.dumps({k:v for k,v in request.items() if k not in ('node','progress','directory')},ensure_ascii=False))
    if studio.cancelled(job):raise ValueError('A feladat leállítva.')
    with progress.with_suffix('.log').open('ab') as errors:
        process=subprocess.Popen([str(runtime),str(Path(__file__).with_name('clip_runtime.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,env=dict(os.environ,YTDLP_NO_PLUGINS='1'),start_new_session=True)
        start=time.monotonic();first=True;last=-1
        try:
            while True:
                try:raw,_=process.communicate(json.dumps(request).encode() if first else None,timeout=1);break
                except subprocess.TimeoutExpired:
                    first=False
                    if studio.cancelled(job):raise ValueError('A hálózati feldolgozás leállítva.')
                    if time.monotonic()-start>(7200 if request.get('full_source') else 600):raise ValueError('A hálózati feldolgozás időkerete lejárt.')
                    if progress.exists():
                        try:report=json.loads(progress.read_text());mb=round(report.get('downloaded_bytes',0)/1024**2)
                        except (OSError,ValueError):continue
                        if mb!=last:studio.job_stage(job,'network',label+' · '+str(mb)+' MB');last=mb
                    if request.get('directory') and sum(p.stat().st_size for p in Path(request['directory']).glob('*') if p.is_file())>(9*1024**3 if request.get('full_source') else 700*1024**2):raise ValueError('A teljes forrás letöltéséhez nincs elegendő engedélyezett tárhely; részletet nem jelölünk teljesnek.')
        except BaseException:os.killpg(process.pid,signal.SIGKILL);process.communicate();raise
    if studio.cancelled(job):raise ValueError('A hálózati feldolgozás leállítva.')
    try:response=json.loads(raw)
    except ValueError:raise ValueError('A klipkereső nem adott érvényes választ. Részletek a helyi hálózati naplóban.')
    if process.returncode or not response.get('ok'):
        message=response.get('message','A nyilvános forrás nem tölthető le.')
        if access_blocked(message):raise ValueError('YOUTUBE_AUTH_REQUIRED: A YouTube emberi ellenőrzést vagy bejelentkezést kér. Automatikus újrapróbálás leállítva. Használj helyi forrásvideót vagy később próbáld újra.')
        raise ValueError(message)
    return response['result']


def find_clips(studio,agent,args,job):
    if 'find_stream_clips' not in agent['tools']:raise ValueError('A klipkeresés nincs engedélyezve.')
    query=args.get('query')
    if not isinstance(query,str) or not 2<=len(query.strip())<=200:raise ValueError('2–200 karakteres keresőkifejezés vagy nyilvános YouTube-link szükséges.')
    identifier=source_id(query.strip())
    if '://' in query and not identifier:raise ValueError('Közvetlen forrásként csak https YouTube- vagy Twitch-link adható meg.')
    schema(studio);results=[];failure=None
    try:data={'candidates':[]} if args.get('web_only') and not identifier else network(studio,job,dict(operation='search',query=query.strip(),video_id=identifier))
    except Exception as exc:
        if studio.cancelled(job):raise
        failure=exc;data={'candidates':[]}
    # Independent discovery through configured Tavily / public search, not an LLM-invented URL.
    if not data.get('candidates') and not identifier:
        studio.job_stage(job,'web_discovery','További videóforrások keresése a weben',query)
        try:
            from research import search
            found=search('site:youtube.com/watch '+query,8,studio.root)
            entries=[]
            for hit in found.get('results',[]):
                vid=youtube_id(hit.get('url',''))
                if vid:entries.append(dict(id=vid,title=hit.get('title',''),description=hit.get('content',''),channel='',url='https://www.youtube.com/watch?v='+vid,duration=None,discovery='web'))
            data={'candidates':entries}
        except Exception:
            if studio.cancelled(job):raise
            if failure:raise failure
    if not data.get('candidates') and failure:raise failure
    for entry in data['candidates'][:6]:
        if not valid_source_id(entry.get('id','')):continue
        cid=uuid.uuid4().hex
        studio.db.execute('INSERT INTO clip_candidates VALUES(?,?,?,?,?)',(cid,agent['project'],entry['id'],json.dumps(entry,ensure_ascii=False),time.time()))
        used=bool(studio.db.execute('SELECT 1 FROM clip_downloads WHERE project=? AND video_id=?',(agent['project'],entry['id'])).fetchone())
        results.append(dict(candidate_id=cid,used=used,**entry))
    studio.db.commit()
    if not results:raise ValueError('Nem található nyilvános, feldolgozható klip ehhez a kereséshez.')
    return results


def download_clip(studio,agent,args,job):
    if 'download_stream_clip' not in agent['tools']:raise ValueError('A klipletöltés nincs engedélyezve.')
    schema(studio)
    row=studio.db.execute('SELECT * FROM clip_candidates WHERE project=? AND id=?',(agent['project'],args.get('candidate_id'))).fetchone()
    if not row:raise ValueError('A keresőből kapott, ehhez a projekthez tartozó candidate_id szükséges.')
    start=args.get('start',0);duration=args.get('duration',180)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (start,duration)) or not 0<=start<=86400 or not 10<=duration<=600:raise ValueError('Kezdés: 0–86400 s; letöltendő részlet: 10–600 s.')
    # A retry reuses the exact checked interval instead of downloading another copy.
    full_source=args.get('full_source') is True
    prior=cached_sources(studio,agent['project'],source_url(row['video_id']),1,full_source=full_source)
    if prior:
        saved=prior[0];manifest=json.loads(studio.safe_path(agent['project'],saved['manifest']).read_text())
        same_range=full_source and saved.get('coverage',{}).get('complete') or abs(float(manifest.get('downloaded_start',0))-start)<.05 and saved['duration']>=min(duration,float(saved['metadata'].get('duration') or duration)-start)-.5
        if same_range:
            if args.get('max_age_hours'):
                from source_policy import require_fresh
                require_fresh(saved['metadata'],max_age_hours=args['max_age_hours'])
                if manifest.get('source_handoff')!=args.get('source_handoff'):raise ValueError('Ezt a hírforrást már másik gyártás használta.')
            return saved
    directory=studio.safe_path(agent['project'],'sources/'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
    result=network(studio,job,dict(operation='download',video_id=row['video_id'],start=0 if full_source else start,duration=duration,full_source=full_source,directory=str(directory),max_age_hours=args.get('max_age_hours')))
    path=Path(result['file']).resolve()
    if directory.resolve() not in path.parents or not path.is_file():raise ValueError('A letöltött forrás elérési útja érvénytelen.')
    if result['metadata'].get('id')!=row['video_id']:raise ValueError('A letöltött forrás azonosítója nem egyezik a keresési találattal.')
    manifest=directory/'source.json';data={k:v for k,v in result.items() if k!='file'};data['project_file']=str(path.relative_to(studio.root/'projects'/agent['project']));data['source_review']='PUBLIC_SOURCE_LOCAL_EDIT_ONLY; publication rights not verified';data['source_handoff']=args.get('source_handoff');manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    for file,kind in [(path,'video'),(manifest,'text')]:studio.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,agent['project'],file.name,str(file),kind,time.time(),job))
    studio.db.execute('INSERT OR REPLACE INTO clip_downloads VALUES(?,?,?,?)',(agent['project'],row['video_id'],str(path),time.time()));studio.db.commit()
    return dict(source_video=data['project_file'],manifest=str(manifest.relative_to(studio.root/'projects'/agent['project'])),duration=result['downloaded_duration'],metadata=result['metadata'],coverage=result.get('coverage',{}))
