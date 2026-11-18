"""Public YouTube discovery/download in an isolated runtime; no login, cookies or plugins."""
import json
import os
from pathlib import Path
import re
import sys
import time

from clip_sources import source_url,twitch_id,valid_source_id


def compact(info,identifier=None):
    keys=('id','title','duration','channel','channel_id','uploader','uploader_id','upload_date','timestamp','view_count','like_count','language','license','availability','categories')
    result={key:info.get(key) for key in keys}
    # Twitch reports its own numeric id; the pipeline's id is the one the source was registered with.
    if identifier:result['id']=identifier
    result['url']=source_url(str(result.get('id','')))
    result['description']=str(info.get('description',''))[:3000]
    return result


def execute(request):
    os.environ['YTDLP_NO_PLUGINS']='1'
    os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')
    import yt_dlp
    import imageio_ffmpeg
    from yt_dlp.utils import download_range_func
    class QuietLog:
        def debug(self,*args):pass
        def info(self,*args):pass
        def warning(self,message):print(str(message)[:2000],file=sys.stderr)
        def error(self,message):print(str(message)[:2000],file=sys.stderr)
    opts={'quiet':True,'no_warnings':False,'logger':QuietLog(),'noplaylist':True,'socket_timeout':20,'retries':1,'extractor_retries':1,'fragment_retries':1,'remote_components':set(),'cachedir':False,'ffmpeg_location':imageio_ffmpeg.get_ffmpeg_exe(),'js_runtimes':{'node':{'path':request['node']}}}
    if request['operation']=='twitch_clips':
        # A channel's most viewed clips of a period: what its viewers themselves picked as the best moments.
        if not re.fullmatch(r'[A-Za-z0-9_]{2,25}',request['channel']) or request.get('range') not in ('24hr','7d','30d','all'):raise ValueError('Érvénytelen Twitch-csatorna vagy időszak.')
        opts.update(extract_flat=True,skip_download=True,playlistend=min(int(request.get('limit',12)),30))
        with yt_dlp.YoutubeDL(opts) as downloader:
            info=downloader.extract_info('https://www.twitch.tv/'+request['channel']+'/clips?filter=clips&range='+request['range'],download=False)
        out=[]
        for e in info.get('entries') or []:
            identifier=twitch_id((e or {}).get('url'))
            if identifier:out.append(dict(id=identifier,url=source_url(identifier),title=e.get('title') or '',duration=e.get('duration'),view_count=e.get('view_count'),timestamp=e.get('timestamp'),channel=request['channel']))
        return {'candidates':out}
    if request['operation']=='youtube_recent':
        # Newest uploads first; a date-sorted results page needs no API quota or login.
        from urllib.parse import quote_plus
        opts.update(extract_flat=True,skip_download=True,playlistend=min(int(request.get('limit',8)),20))
        with yt_dlp.YoutubeDL(opts) as downloader:
            info=downloader.extract_info('https://www.youtube.com/results?search_query='+quote_plus(request['query'][:160])+'&sp=CAI%253D',download=False)
        return {'candidates':[compact(e) for e in info.get('entries') or [] if e and re.fullmatch(r'[A-Za-z0-9_-]{11}',e.get('id','')) and not e.get('is_live') and e.get('live_status')!='is_live']}
    if request['operation']=='probe':
        # Full public metadata of one source, with its game and most-replayed curve when the platform reports them.
        if not valid_source_id(request['video_id']):raise ValueError('Érvénytelen videóazonosító.')
        with yt_dlp.YoutubeDL(opts) as downloader:
            info=downloader.extract_info(source_url(request['video_id']),download=False)
        return dict(compact(info,request['video_id']),live_status=info.get('live_status'),heatmap=[dict(start=h.get('start_time'),end=h.get('end_time'),value=h.get('value')) for h in info.get('heatmap') or []])
    if request['operation']=='search':
        query=request['query']
        if request.get('video_id'):
            with yt_dlp.YoutubeDL(opts) as downloader:
                info=downloader.extract_info(source_url(request['video_id']),download=False)
                return {'candidates':[compact(info,request['video_id'])]}
        opts.update(extract_flat=True,skip_download=True)
        with yt_dlp.YoutubeDL(opts) as downloader:
            info=downloader.extract_info('ytsearch6:'+query,download=False)
            return {'candidates':[compact(e) for e in info.get('entries',[]) if e and re.fullmatch(r'[A-Za-z0-9_-]{11}',e.get('id','')) and not e.get('is_live')]}
    if request['operation']!='download':raise ValueError('Ismeretlen hálózati feladat.')
    identifier=request['video_id']
    if not valid_source_id(identifier):raise ValueError('Érvénytelen videóazonosító.')
    output=Path(request['directory']);output.mkdir(parents=True,exist_ok=True)
    import shutil
    # A Twitch clip is one short file: always whole, and worth its full resolution.
    clip=identifier.startswith('twc:')
    full=request.get('full_source') is True or clip
    budget=min(8*1024**3,max(0,shutil.disk_usage(output).free-4*1024**3)) if full else 500*1024**2
    if full and budget<512*1024**2:raise ValueError('Nincs elegendő szabad tárhely a teljes forráshoz.')
    def progress(status):
        downloaded=status.get('downloaded_bytes',0)
        if downloaded>budget:raise ValueError('A teljes forrás letöltésének tárhelykerete betelt; nem használunk helyette csonka részletet.')
        report={'status':status.get('status'),'downloaded_bytes':downloaded,'total_bytes':status.get('total_bytes') or status.get('total_bytes_estimate'),'updated':time.time()}
        target=Path(request['progress']);temp=target.with_suffix('.tmp');temp.write_text(json.dumps(report));os.replace(temp,target)
    opts.update(format='bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]',merge_output_format='mp4',outtmpl=str(output/'source.%(ext)s'),force_keyframes_at_cuts=not full,max_filesize=budget,progress_hooks=[progress],overwrites=False)
    if clip:opts['format']='best[height<=1080]/best'
    # A window deep inside a long stream: ffmpeg seeks a direct file in seconds (150 s at 2.5 h of a 5.7 h stream: 85 s),
    # while through an HLS playlist it had not finished after 10 minutes. The pipeline works from the file it gets, so
    # the cut needs no re-encoding.
    if not full and request['start']>0:
        opts['format']='bestvideo[height<=720][ext=mp4][protocol=https]+bestaudio[ext=m4a][protocol=https]/best[height<=720][protocol=https]/'+opts['format']
        opts['force_keyframes_at_cuts']=False
    if not full:opts['download_ranges']=download_range_func(None,[(request['start'],request['start']+request['duration'])])
    url=source_url(identifier)
    with yt_dlp.YoutubeDL(opts) as downloader:
        info=downloader.extract_info(url,download=False)
        if info.get('is_live') or info.get('live_status')=='is_live':raise ValueError('Lezárt nyilvános felvételt vagy klipet válassz, ne élő adást.')
        if info.get('availability') in ('private','subscriber_only','premium_only','needs_auth'):raise ValueError('A forrás nem érhető el nyilvánosan, fiók nélkül.')
        original=float(info.get('duration') or 0)
        if original and request['start']>=original:raise ValueError('A kezdés a forrás időtartamán kívül van.')
        if request.get('max_age_hours'):
            from source_policy import require_fresh
            require_fresh(compact(info,identifier),max_age_hours=request['max_age_hours'])
        downloader.process_ie_result(info,download=True)
    files=[p for p in output.iterdir() if p.suffix.lower() in ('.mp4','.mkv','.webm') and not '.part' in p.name]
    if len(files)!=1:raise ValueError('Nem keletkezett egyetlen, ellenőrizhető videófájl.')
    import cv2
    capture=cv2.VideoCapture(str(files[0]));fps=capture.get(cv2.CAP_PROP_FPS);duration=capture.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps else 0;ok,_=capture.read();capture.release()
    if not ok or duration<2:raise ValueError('A letöltött videó nem játszható le vagy túl rövid.')
    complete=bool(full and original>0 and duration>=original-max(2,original*.001))
    if full and not complete:raise ValueError('A teljes forrás letöltése nem igazolható. A részleges videót nem tekintjük teljes bemenetnek.')
    return {'file':str(files[0]),'metadata':compact(info,identifier),'downloaded_start':0 if full else request['start'],'downloaded_duration':duration,'coverage':dict(complete=complete,original_seconds=original,downloaded_seconds=duration,mode='full_source' if full else 'excerpt'),'bytes':files[0].stat().st_size}

if __name__=='__main__':
    try:print(json.dumps({'ok':True,'result':execute(json.loads(sys.stdin.read(20000)))},ensure_ascii=False,allow_nan=False))
    except Exception as exc:print(json.dumps({'ok':False,'message':str(exc)[:2000]},ensure_ascii=False));sys.exit(1)
