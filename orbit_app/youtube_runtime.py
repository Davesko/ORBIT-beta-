"""Google OAuth PKCE and resumable private uploads. Tokens live in macOS Keychain."""
import json
import os
from pathlib import Path
import secrets
import sys
import time

BASE_SCOPES=['https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube.readonly']
ANALYTICS_SCOPE='https://www.googleapis.com/auth/yt-analytics.readonly'
SCOPES=BASE_SCOPES+[ANALYTICS_SCOPE]


def atomic_json(path,data):
    temp=path.with_suffix('.tmp')
    with os.fdopen(os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as handle:json.dump(data,handle)
    os.replace(temp,path)


def store():
    import keyring
    from keyring.backends.macOS import Keyring
    keyring.set_keyring(Keyring());return keyring


REVOKED='A YouTube-belépés lejárt: a Google visszavonta a mentett hozzáférést. Csatlakoztasd újra a csatornát az ORBIT-ban. Ha a Google Cloud-alkalmazásod „Testing” módban van, ez 7 naponként megismétlődik; „In production” módban nem.'

def credentials(pid):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    raw=store().get_password('hu.orbit.youtube',pid)
    if not raw:
        base=Path.home()/'Library/Application Support/Orbit/integrations/youtube'/pid
        if base.is_dir():
            atomic_json(base/'status.json',dict(connected=False))
            atomic_json(base/'auth.json',dict(status='failed',error='A mentett YouTube-belépés nem található a Kulcskarikában. Csatlakoztasd újra a csatornát.',created=time.time()))
        raise ValueError('A mentett YouTube-belépés nem található. Csatlakoztasd újra a csatornát.')
    result=Credentials.from_authorized_user_info(json.loads(raw),json.loads(raw).get('scopes') or BASE_SCOPES)
    if not result.valid:
        if not result.refresh_token:raise ValueError('Új YouTube-bejelentkezés szükséges.')
        try:result.refresh(Request())
        except Exception as exc:
            if type(exc).__name__!='RefreshError':raise
            # Google revoked the saved login (apps in "Testing" mode lose it every 7 days). Show the
            # channel as disconnected so the app asks for a new login instead of retrying forever.
            base=Path.home()/'Library/Application Support/Orbit/integrations/youtube'/pid
            if base.is_dir():
                atomic_json(base/'status.json',dict(connected=False))
                atomic_json(base/'auth.json',dict(status='failed',error=REVOKED,created=time.time()))
            raise ValueError(REVOKED) from None
        store().set_password('hu.orbit.youtube',pid,result.to_json())
    return result


def safe_auth_error(stage,exc):
    # Never persist exception bodies, authorization codes, URLs or tokens.
    status=getattr(getattr(exc,'resp',None),'status',None)
    if stage=='channel_missing':return 'A Google-belépés sikerült, de ehhez a fiókhoz még nincs YouTube-csatorna. Hozz létre egy csatornát a YouTube-on, majd csatlakozz újra.'
    if stage=='keychain':return 'A Google-belépés sikerült, de a macOS Kulcskarika nem engedte a hozzáférés mentését. Engedélyezd az ORBIT helyi hitelesítőadat-mentését.'
    if stage=='callback':return 'A Google-engedélyezés megszakadt vagy lejárt. Ellenőrizd, hogy a saját fiókod tesztfelhasználó, és mindkét YouTube-engedélyt megadtad.'
    if stage=='channel' and status==403:return 'A Google-belépés után a YouTube API megtagadta a csatorna olvasását (403). Ellenőrizd az API engedélyezését és a YouTube-olvasási engedélyt.'
    if stage=='channel':return 'A Google-belépés után nem sikerült lekérni a YouTube-csatornát. Ellenőrizd a csatornát és az internetkapcsolatot.'
    code=getattr(exc,'error',None)
    if code in ('invalid_grant','invalid_client','access_denied'):return 'A Google-tokenváltás nem sikerült ('+code+'). Új bejelentkezés szükséges az elmentett Desktop klienssel.'
    return 'A Google-tokenváltás nem sikerült. Új bejelentkezés szükséges. A hozzáférési adatokat nem naplózzuk.'


def connect(root,pid):
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from http.server import HTTPServer,BaseHTTPRequestHandler
    from urllib.parse import urlsplit,parse_qs
    base=root/'integrations/youtube'/pid
    flow=InstalledAppFlow.from_client_config(json.loads((base/'client.json').read_text()),SCOPES,autogenerate_code_verifier=True)
    result={};expected=secrets.token_urlsafe(32)
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            query=parse_qs(urlsplit(self.path).query)
            valid=urlsplit(self.path).path=='/callback' and secrets.compare_digest(query.get('state',[''])[0],expected)
            self.send_response(200 if valid else 400);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers()
            self.wfile.write(('A bejelentkezés válasza megérkezett. Visszatérhetsz az ORBIT appba.' if valid else 'Érvénytelen bejelentkezési válasz.').encode())
            if valid:result.update(code=query.get('code',[''])[0],error=query.get('error',[''])[0])
    server=HTTPServer(('127.0.0.1',0),Callback);server.timeout=1
    flow.redirect_uri='http://127.0.0.1:'+str(server.server_port)+'/callback'
    url,_=flow.authorization_url(state=expected,access_type='offline',prompt='select_account consent')
    atomic_json(base/'auth.json',dict(status='waiting',url=url,created=time.time()))
    stage='callback'
    try:
        start=time.monotonic()
        while not result and time.monotonic()-start<300:server.handle_request()
        if not result or result.get('error') or not result.get('code'):raise ValueError('A bejelentkezés megszakadt vagy lejárt. Indítsd újra az appból.')
        stage='token';flow.fetch_token(code=result['code'])
        stage='channel'
        channel=build('youtube','v3',credentials=flow.credentials,cache_discovery=False).channels().list(part='snippet',mine=True).execute()
        items=channel.get('items',[])
        if not items:
            stage='channel_missing'
            raise ValueError('Ehhez a Google-fiókhoz nem érhető el YouTube-csatorna.')
        stage='keychain';store().set_password('hu.orbit.youtube',pid,flow.credentials.to_json())
        atomic_json(base/'status.json',dict(connected=True,channel=items[0]['snippet']['title'],channel_id=items[0]['id']))
        atomic_json(base/'auth.json',dict(status='done',created=time.time()))
    except Exception as exc:
        atomic_json(base/'auth.json',dict(status='failed',stage=stage,error=safe_auth_error(stage,exc),created=time.time()))
    finally:server.server_close()


def verified_upload_fields(item):
    """The Data API reports processing, not a definitive Shorts classification."""
    status=item.get('status',{});processing=item.get('processingDetails',{})
    return dict(privacy=status.get('privacyStatus','unknown'),
                processing=status.get('uploadStatus','unknown'),
                processing_status=processing.get('processingStatus','unknown'),
                processing_failure=processing.get('processingFailureReason') or status.get('rejectionReason') or status.get('failureReason'),
                youtube_duration=item.get('contentDetails',{}).get('duration'),checked_at=time.time())


def refresh_uploads(root,pid):
    from googleapiclient.discovery import build
    import re
    base=root/'integrations/youtube'/pid
    paths=sorted(base.glob('receipt-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
    records=[]
    for path in paths:
        try:data=json.loads(path.read_text())
        except (OSError,ValueError):continue
        if re.fullmatch(r'[A-Za-z0-9_-]{11}',data.get('id','')):records.append((path,data))
    if not records:return
    import httplib2,google_auth_httplib2
    transport=google_auth_httplib2.AuthorizedHttp(credentials(pid),http=httplib2.Http(timeout=20))
    service=build('youtube','v3',http=transport,cache_discovery=False)
    items=service.videos().list(part='status,processingDetails,contentDetails',id=','.join(d['id'] for _,d in records)).execute().get('items',[])
    by_id={item['id']:item for item in items}
    for path,data in records:
        if data['id'] in by_id:
            data.update(verified_upload_fields(by_id[data['id']]))
            atomic_json(path,data)


def upload(root,pid,request):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import httplib2
    import google_auth_httplib2
    http=httplib2.Http(timeout=60)
    # YouTube uses 308 as resumable-upload progress, without Location.
    # Let googleapiclient process it instead of following it as a redirect.
    http.redirect_codes=set(http.redirect_codes)-{308}
    transport=google_auth_httplib2.AuthorizedHttp(credentials(pid),http=http)
    service=build('youtube','v3',http=transport,cache_discovery=False)
    privacy=request.get('privacy','private')
    if privacy not in ('public','private','unlisted'):raise ValueError('Érvénytelen láthatóság.')
    body={'snippet':{'title':request['title'],'description':request['description'],'categoryId':str(request.get('category') or '20')},'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':request['made_for_kids']}}
    operation=service.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(request['source'],mimetype='video/mp4',chunksize=4*1024*1024,resumable=True))
    response=None
    atomic_json(Path(request['progress']),dict(percent=0,transfer_started=True))
    while response is None:
        status,response=operation.next_chunk(num_retries=3)
        if status:atomic_json(Path(request['progress']),dict(percent=round(status.progress()*100),transfer_started=True))
    if not response.get('id'):raise ValueError('A YouTube nem adott vissza videóazonosítót.')
    # Save the returned ID before a follow-up request; never lose an uploaded video.
    receipt=dict(percent=100,id=response['id'],requested_privacy=privacy,privacy=response.get('status',{}).get('privacyStatus','unknown'),processing=response.get('status',{}).get('uploadStatus','unknown'))
    atomic_json(Path(request['progress']),receipt)
    try:
        actual=service.videos().list(part='status,processingDetails,contentDetails',id=response['id']).execute().get('items',[])
        if actual:receipt.update(verified_upload_fields(actual[0]))
    except Exception:receipt['verification']='A visszaellenőrzés nem sikerült; a videóazonosító megvan. Ne töltsd fel újra.'
    cover=request.get('thumbnail')
    if cover and Path(cover).is_file():
        try:
            service.thumbnails().set(videoId=response['id'],media_body=MediaFileUpload(cover,mimetype='image/jpeg')).execute()
            receipt['thumbnail']='ok'
        except Exception as exc:receipt['thumbnail']='A borítóképet a YouTube nem fogadta el ('+type(exc).__name__+'); a csatornának igazoltnak kell lennie.'
    atomic_json(Path(request['progress']),receipt)
    return response['id']

def duration_seconds(value):
    import re
    match=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?',str(value))
    return sum(float(x or 0)*scale for x,scale in zip(match.groups(),(3600,60,1))) if match else None


def source_metadata(pid,request):
    from googleapiclient.discovery import build
    import httplib2,google_auth_httplib2,re
    ids=[i for i in request.get('ids',[])[:5] if isinstance(i,str) and re.fullmatch(r'[A-Za-z0-9_-]{11}',i)]
    if not ids:return dict(ok=True,videos=[])
    transport=google_auth_httplib2.AuthorizedHttp(credentials(pid),http=httplib2.Http(timeout=15))
    service=build('youtube','v3',http=transport,cache_discovery=False)
    items=service.videos().list(part='snippet,contentDetails',id=','.join(ids)).execute().get('items',[])
    return dict(ok=True,videos=[dict(id=i['id'],url='https://www.youtube.com/watch?v='+i['id'],title=i.get('snippet',{}).get('title',''),description=i.get('snippet',{}).get('description','')[:3000],published_at=i.get('snippet',{}).get('publishedAt'),duration=duration_seconds(i.get('contentDetails',{}).get('duration'))) for i in items])


def discovery(pid,request):
    from googleapiclient.discovery import build
    import httplib2,google_auth_httplib2
    from youtube_discovery import discover
    transport=google_auth_httplib2.AuthorizedHttp(credentials(pid),http=httplib2.Http(timeout=15))
    return discover(build('youtube','v3',http=transport,cache_discovery=False),request)


def trend_samples(pid,request):
    from googleapiclient.discovery import build
    from datetime import datetime,timezone,timedelta
    import httplib2,google_auth_httplib2,re
    transport=google_auth_httplib2.AuthorizedHttp(credentials(pid),http=httplib2.Http(timeout=15))
    service=build('youtube','v3',http=transport,cache_discovery=False);samples={}
    since=(datetime.now(timezone.utc)-timedelta(hours=72)).isoformat().replace('+00:00','Z')
    max_duration=request.get('max_video_seconds',180)
    if type(max_duration) is not int or not 180<=max_duration<=1800:raise ValueError('Invalid source duration limit.')
    for topic in request.get('topics',[])[:3]:
        if not isinstance(topic,str) or not 2<=len(topic)<=180:continue
        found=service.search().list(part='snippet',q=str(request.get('event_queries',{}).get(topic) or topic)[:200],type='video',videoDuration='any' if max_duration>180 else 'short',publishedAfter=since,regionCode=request.get('country','US'),maxResults=10,order='relevance').execute().get('items',[])
        ids=[i.get('id',{}).get('videoId') for i in found];ids=[i for i in ids if i]
        videos=[]
        if ids:
            items=service.videos().list(part='snippet,contentDetails,statistics',id=','.join(ids)).execute().get('items',[])
            words=set(re.findall(r'\w{3,}',topic.casefold()))-{'the','and','for','with'}
            for item in items:
                duration=duration_seconds(item.get('contentDetails',{}).get('duration'));snippet=item.get('snippet',{});title=snippet.get('title','')
                text=(title+' '+snippet.get('description','')[:500]).casefold()
                from source_policy import require_fresh,matching_news
                try:require_fresh(dict(published_at=snippet.get('publishedAt')))
                except ValueError:continue
                news=request.get('news',{}).get(topic,[])
                if not matching_news(dict(title=title,description=snippet.get('description','')),news):continue
                if duration is None or not 10<=duration<=max_duration or words and sum(w in text for w in words)<min(2,len(words)):continue
                videos.append(dict(id=item['id'],title=title,description=snippet.get('description','')[:1500],url='https://www.youtube.com/watch?v='+item['id'],published_at=snippet.get('publishedAt'),duration=duration,views=int(item.get('statistics',{}).get('viewCount',0)),channel=snippet.get('channelTitle')))
        samples[topic]=dict(status='available',videos=videos,window_days=3,maximum_results=10,query=topic,note='Source videos up to '+str(max_duration)+' seconds; vertical aspect ratio and Shorts classification are not exposed here. This is a bounded sample, not total supply.')
    return dict(ok=True,samples=samples)


def reach(pid,request):
    """Channel totals and the latest uploads of the whole channel (also videos not made in ORBIT) with their public counters."""
    from googleapiclient.discovery import build
    import httplib2,google_auth_httplib2
    transport=google_auth_httplib2.AuthorizedHttp(credentials(pid),http=httplib2.Http(timeout=20))
    service=build('youtube','v3',http=transport,cache_discovery=False)
    num=lambda v:int(v) if str(v or '').isdigit() else None
    channel=service.channels().list(part='snippet,statistics,contentDetails',mine=True).execute().get('items',[])
    if not channel:raise ValueError('Ehhez a belépéshez nem tartozik YouTube-csatorna.')
    c=channel[0];stats=c.get('statistics',{})
    out=dict(channel=dict(title=c.get('snippet',{}).get('title',''),subscribers=num(stats.get('subscriberCount')),views=num(stats.get('viewCount')),videos=num(stats.get('videoCount'))),items=[])
    uploads=c.get('contentDetails',{}).get('relatedPlaylists',{}).get('uploads')
    ids=[]
    token=None
    while uploads and len(ids)<int(request.get('limit') or 150):
        page=service.playlistItems().list(part='contentDetails',playlistId=uploads,maxResults=50,pageToken=token).execute()
        ids+=[i['contentDetails']['videoId'] for i in page.get('items',[])]
        token=page.get('nextPageToken')
        if not token:break
    for i in range(0,len(ids),50):
        for item in service.videos().list(part='snippet,statistics,contentDetails',id=','.join(ids[i:i+50])).execute().get('items',[]):
            st=item.get('statistics',{});sn=item.get('snippet',{})
            out['items'].append(dict(id=item['id'],title=sn.get('title','')[:120],url='https://www.youtube.com/watch?v='+item['id'],published=sn.get('publishedAt'),
                views=num(st.get('viewCount')),likes=num(st.get('likeCount')),comments=num(st.get('commentCount'))))
    return out

def metrics(pid,request):
    from googleapiclient.discovery import build
    from datetime import datetime,timezone,timedelta
    creds=credentials(pid)
    import httplib2,google_auth_httplib2
    transport=google_auth_httplib2.AuthorizedHttp(creds,http=httplib2.Http(timeout=15))
    service=build('youtube','v3',http=transport,cache_discovery=False)
    channel=None
    try:
        listed=service.channels().list(part='snippet,statistics',mine=True).execute().get('items',[])
        if isinstance(listed,list) and listed:
            entry=listed[0];stats=entry.get('statistics',{})
            from short_feedback import number
            channel=dict(id=entry['id'],title=entry.get('snippet',{}).get('title',''),views=number(stats.get('viewCount')),video_count=number(stats.get('videoCount')),subscribers=number(stats.get('subscriberCount')),measured_at=time.time())
    except Exception:pass
    records={v['id']:v for v in request.get('videos',[])[:50] if isinstance(v,dict) and __import__('re').fullmatch(r'[A-Za-z0-9_-]{11}',v.get('id',''))}
    if not records:return dict(ok=True,videos=[],channel=channel,analytics_status='no_tracked_videos')
    items=service.videos().list(part='snippet,status,statistics,contentDetails',id=','.join(records)).execute().get('items',[])
    videos=[];now=datetime.now(timezone.utc)
    for item in items:
        stats=item.get('statistics',{});snippet=item.get('snippet',{});published=snippet.get('publishedAt')
        try:age=(now-datetime.fromisoformat(published.replace('Z','+00:00'))).total_seconds()/3600
        except (ValueError,TypeError,AttributeError):continue
        from short_feedback import number
        videos.append(dict(records[item['id']],published_at=published,age_hours=round(age,2),status=item.get('status',{}).get('uploadStatus'),views=number(stats.get('viewCount')),likes=number(stats.get('likeCount')),comments=number(stats.get('commentCount')),engaged_views=None,average_view_duration=None,average_view_percentage=None,subscribers_gained=None,shares=None,title=snippet.get('title',''),retention=[]))
    analytics_status='authorization_required';series=[];countries=[];traffic=[];report_errors=[]
    if creds.has_scopes([ANALYTICS_SCOPE]):
        try:
            analytics=build('youtubeAnalytics','v2',http=transport,cache_discovery=False)
            result=analytics.reports().query(ids='channel==MINE',startDate=(now-timedelta(days=90)).date().isoformat(),endDate=now.date().isoformat(),dimensions='video',metrics='engagedViews,averageViewDuration,averageViewPercentage,subscribersGained,shares',filters='video=='+','.join(records)).execute()
            columns=[c['name'] for c in result.get('columnHeaders',[])]
            rows={r[0]:dict(zip(columns,r)) for r in result.get('rows',[])}
            for v in videos:
                row=rows.get(v['id'],{})
                for dest,key in [('engaged_views','engagedViews'),('average_view_duration','averageViewDuration'),('average_view_percentage','averageViewPercentage'),('subscribers_gained','subscribersGained'),('shares','shares')]:v[dest]=number(row.get(key))
            analytics_status='available'
            def report(dimensions,metrics,filters='',sort=None,max_results=None):
                kwargs=dict(ids='channel==MINE',startDate=(now-timedelta(days=28)).date().isoformat(),endDate=now.date().isoformat(),dimensions=dimensions,metrics=metrics)
                if filters:kwargs['filters']=filters
                if sort:kwargs['sort']=sort
                if max_results:kwargs['maxResults']=max_results
                try:
                    data=analytics.reports().query(**kwargs).execute();cols=[c['name'] for c in data.get('columnHeaders',[])]
                    return [dict(zip(cols,row)) for row in data.get('rows',[])]
                except Exception:report_errors.append(dimensions);return []
            subset='video=='+','.join(records)
            series=report('day','views,engagedViews,estimatedMinutesWatched',subset)
            countries=report('country','views',subset,'-views',10)
            traffic=report('insightTrafficSourceType','views',subset)
            for video in sorted(videos,key=lambda v:v.get('views') or 0,reverse=True)[:2]:
                video['retention']=report('elapsedVideoTimeRatio','audienceWatchRatio,relativeRetentionPerformance','video=='+video['id'])
        except Exception:analytics_status='unavailable_or_api_not_enabled'
    return dict(ok=True,videos=videos,channel=channel,analytics_status=analytics_status,series=series,countries=countries,traffic=traffic,report_errors=report_errors,period_days=28,limitations=['No swipe-away or hook-retention metric is inferred from public view counts.','Analytics may be delayed; missing is not zero.'])

if __name__=='__main__':
    try:
        action,root,pid=sys.argv[1:4];root=Path(root)
        if action=='connect':connect(root,pid)
        elif action=='disconnect':
            try:store().delete_password('hu.orbit.youtube',pid)
            except Exception as exc:
                if type(exc).__name__!='PasswordDeleteError':raise
            atomic_json(root/'integrations/youtube'/pid/'status.json',dict(connected=False));print(json.dumps({'ok':True}))
        elif action=='refresh_uploads':refresh_uploads(root,pid);print(json.dumps({'ok':True}))
        elif action=='source_metadata':print(json.dumps(source_metadata(pid,json.loads(sys.stdin.read(10000)))))
        elif action=='discovery':print(json.dumps(discovery(pid,json.loads(sys.stdin.read(10000)))))
        elif action=='trend_samples':print(json.dumps(trend_samples(pid,json.loads(sys.stdin.read(10000)))))
        elif action=='reach':print(json.dumps(dict(ok=True,**reach(pid,json.loads(sys.stdin.read(3000) or '{}')))))
        elif action=='metrics':print(json.dumps(metrics(pid,json.loads(sys.stdin.read(30000)))))
        elif action=='upload':print(json.dumps({'ok':True,'id':upload(root,pid,json.loads(sys.stdin.read(20000)))}))
        else:raise ValueError('Ismeretlen YouTube-művelet.')
    except Exception as exc:
        code=getattr(getattr(exc,'resp',None),'status',None)
        message={401:'Lejárt YouTube-belépés. Csatlakozz újra.',403:'A YouTube megtagadta a feltöltést: ellenőrizd a kvótát, a csatorna jogosultságait és az API engedélyezését.',400:'A YouTube elutasította a videót vagy a metaadatokat.'}.get(code,'YouTube-kapcsolati hiba. Ellenőrizd a fiókot és a hálózatot; a részleges feltöltést a YouTube Studióban keresd.')
        # ORBIT's own messages (missing or revoked login, bad input) are already safe and precise.
        if isinstance(exc,ValueError) and code is None:message=str(exc)[:400]
        print(json.dumps({'ok':False,'message':message+' ['+type(exc).__name__+']','diagnostic_type':type(exc).__name__}));sys.exit(1)
