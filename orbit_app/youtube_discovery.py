"""Bounded public YouTube research. Custom ratios require recorded platform approval."""
import datetime,hashlib,json,math,statistics,time
from pathlib import Path


def permission(root):
    try:v=json.loads((Path(root)/'integrations/youtube/analytics-policy.json').read_text())
    except (OSError,ValueError):v={}
    return v.get('approved') is True and isinstance(v.get('approval_reference'),str) and len(v['approval_reference'])>=8


def stamp(value):
    try:return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,AttributeError,TypeError):return None


def count(value):
    try:
        n=int(value)
        return n if n>=0 else None
    except (ValueError,TypeError,OverflowError):return None


def compare(video,history,approved=False):
    if not approved:return dict(status='approval_required',ratio=None,outlier=None)
    age=video.get('age_hours');duration=video.get('duration');views=video.get('views')
    if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in (age,duration,views)):return dict(status='insufficient_data',ratio=None,outlier=None)
    # Compare observed counts at similar upload ages; never reconstruct historical views.
    peers={}
    for p in history:
        if p.get('id')==video['id'] or p.get('channel_id')!=video.get('channel_id'):continue
        a=p.get('age_hours');d=p.get('duration');v=p.get('views')
        if not all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in (a,d,v)):continue
        if .75<=a/age<=1.33 and .75<=d/duration<=1.33:
            previous=peers.get(p['id'])
            if previous is None or abs(a-age)<abs(previous['age_hours']-age):peers[p['id']]=p
    if len(peers)<10:return dict(status='insufficient_comparable_history',sample_size=len(peers),ratio=None,outlier=None)
    median=statistics.median(p['views'] for p in peers.values())
    if median<100:return dict(status='baseline_too_small',sample_size=len(peers),ratio=None,outlier=None)
    ratio=views/median
    return dict(status='observed_comparison',sample_size=len(peers),median_views=median,ratio=round(ratio,2),outlier=ratio>=5,
                assessment='ORBIT comparison, not a YouTube metric or proof of hook quality. Short-form format is not confirmed by duration alone.')


def discover(service,request,now=None):
    """At most three search calls, one detail call and one channel call."""
    now=now or time.time();queries=list(dict.fromkeys(str(q).strip()[:160] for q in request.get('queries',[]) if str(q).strip()))[:3]
    country=request.get('country','US');after=datetime.datetime.fromtimestamp(now-72*3600,datetime.timezone.utc).isoformat();found={};errors=[]
    for query in queries:
        try:
            result=service.search().list(part='snippet',q=query,type='video',order='date',publishedAfter=after,
                videoDuration='short',relevanceLanguage='en',regionCode=country,maxResults=10).execute()
            for hit in result.get('items',[]):
                vid=hit.get('id',{}).get('videoId')
                if vid:found.setdefault(vid,[]).append(query)
        except Exception:errors.append('search_unavailable:'+query)
    if not found:return dict(ok=True,videos=[],errors=errors,queries=queries)
    from youtube_runtime import duration_seconds
    items=service.videos().list(part='snippet,contentDetails,statistics',id=','.join(found)).execute().get('items',[])
    channels=list(dict.fromkeys(v.get('snippet',{}).get('channelId') for v in items));channels=[c for c in channels if c]
    sizes={}
    if channels:
        try:
            for c in service.channels().list(part='statistics',id=','.join(channels)).execute().get('items',[]):
                stats=c.get('statistics',{});sizes[c['id']]=None if stats.get('hiddenSubscriberCount') else count(stats.get('subscriberCount'))
        except Exception:errors.append('channel_sizes_unavailable')
    videos=[]
    for item in items:
        info=item.get('snippet',{});published=stamp(info.get('publishedAt'));duration=duration_seconds(item.get('contentDetails',{}).get('duration'))
        if published is None or not -300<=now-published<=72*3600 or duration is None or not 10<=duration<=180:continue
        subscribers=sizes.get(info.get('channelId'))
        if subscribers is not None and not 1000<=subscribers<=1000000:continue
        stats=item.get('statistics',{});views=count(stats.get('viewCount'))
        if views is None:continue
        videos.append(dict(id=item['id'],url='https://www.youtube.com/watch?v='+item['id'],title=info.get('title',''),
            description=info.get('description','')[:1000],published_at=info.get('publishedAt'),age_hours=round(max(0,now-published)/3600,2),
            duration=duration,views=views,likes=count(stats.get('likeCount')),comments=count(stats.get('commentCount')),
            channel=info.get('channelTitle'),channel_id=info.get('channelId'),subscribers=subscribers,
            queries=found.get(item['id'],[]),observed_at=now,format='short_form_candidate_not_confirmed_shorts'))
    videos.sort(key=lambda v:v['views'],reverse=True)
    return dict(ok=True,videos=videos,queries=queries,errors=errors,
        limitations=['Views are public counts, not retention or proof of a successful hook.','Duration does not certify Shorts classification.','Missing subscriber counts remain unknown.'])


def record(s,pid,result):
    s.db.execute('CREATE TABLE IF NOT EXISTS youtube_research_observations(project TEXT,video TEXT,observed REAL,data TEXT,PRIMARY KEY(project,video,observed))')
    cutoff=time.time()-30*86400;s.db.execute('DELETE FROM youtube_research_observations WHERE observed<?',(cutoff,))
    history=[json.loads(r['data']) for r in s.rows('SELECT data FROM youtube_research_observations WHERE project=? AND observed>=?',(pid,cutoff))]
    allowed=permission(s.root)
    for v in result.get('videos',[]):
        v['comparison']=compare(v,history,allowed)
        raw={k:value for k,value in v.items() if k!='comparison'}
        s.db.execute('INSERT OR REPLACE INTO youtube_research_observations VALUES(?,?,?,?)',(pid,v['id'],v['observed_at'],json.dumps(raw)))
    s.db.commit();result['advanced_metrics_enabled']=allowed
    result['comparison_note']='Az ORBIT összehasonlításai külön jelölést kapnak.' if allowed else 'Az outlier-arány még nincs aktiválva: nincs rögzített YouTube-jóváhagyás. A nyilvános videóadatok kutatása használható.'
    result['collected_at']=time.time();return result
