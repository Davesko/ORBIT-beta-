"""Optional licensed stock illustration; never a substitute for event evidence."""
import json,time,uuid,urllib.parse,urllib.request


def media_url(url):
    p=urllib.parse.urlsplit(url)
    host=p.hostname or ''
    if p.scheme!='https' or not (host in ('videos.pexels.com','player.vimeo.com') or host.endswith('.vimeocdn.com')) or p.username or p.password or p.port not in (None,443):raise ValueError('Ismeretlen stock médiakiszolgáló.')
    return url


def search(s,query):
    if not isinstance(query,str) or not 2<=len(query.strip())<=160:raise ValueError('Adj meg egy rövid, konkrét stock keresést.')
    from connections import http
    result=http('pexels','videos/search?'+urllib.parse.urlencode(dict(query=query.strip(),orientation='portrait',per_page=5)),root=s.root)
    return dict(illustration_only=True,credit='Videos provided by Pexels · https://www.pexels.com',
        videos=[dict(id=v['id'],url=v.get('url'),duration=v.get('duration'),author=v.get('user',{}).get('name')) for v in result.get('videos',[]) if type(v.get('id')) is int])


def download(s,agent,args,job):
    vid=args.get('video_id')
    if type(vid) is not int or not 1<=vid<=10**12:raise ValueError('A keresésből kapott Pexels videóazonosítót add meg.')
    reason=args.get('reason','')
    if not isinstance(reason,str) or not 12<=len(reason)<=400:raise ValueError('Írd le, melyik állítást illusztrálja a B-roll; nem bizonyíték.')
    from connections import http
    meta=http('pexels','videos/videos/'+str(vid),root=s.root)
    files=[f for f in meta.get('video_files',[]) if f.get('file_type')=='video/mp4' and type(f.get('width')) is int and 360<=f['width']<=1920]
    if not files:raise ValueError('Nincs megfelelő MP4 stock változat.')
    chosen=min(files,key=lambda f:abs(f['width']-1080));url=media_url(chosen.get('link',''))
    name='inputs/media/stock-'+uuid.uuid4().hex[:12]+'.mp4';output=s.safe_path(agent['project'],name);output.parent.mkdir(parents=True,exist_ok=True)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            media_url(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(urllib.request.Request(url,headers={'User-Agent':'ORBIT/2.5'}),timeout=30) as response,output.open('xb') as target:
            size=0;deadline=time.monotonic()+120
            while True:
                if s.cancelled(job):raise ValueError('A stock letöltés leállítva.')
                chunk=response.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>250*1024*1024 or time.monotonic()>deadline:raise ValueError('Túl nagy vagy túl lassú stock videó.')
                target.write(chunk)
        if size<1024:raise ValueError('Üres stock videó.')
    except BaseException:output.unlink(missing_ok=True);raise
    credit=dict(provider='Pexels',video_id=vid,url=meta.get('url'),author=meta.get('user',{}).get('name'),illustration_only=True,reason=reason)
    output.with_suffix('.source.json').write_text(json.dumps(credit,ensure_ascii=False,indent=2))
    s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,agent['project'],output.name,str(output),'video',time.time(),job));s.db.commit()
    return dict(saved=name,credit=credit,next_step='Analyze this local video before selecting a cutaway; stock imagery is not evidence of the reported event.')
