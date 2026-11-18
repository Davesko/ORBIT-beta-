"""Durable direct-source handoff, verified publication dates and project-scoped deduplication."""
import datetime,email.utils,json,math,re,subprocess,time,uuid
from pathlib import Path
MAX_AGE_HOURS=72

def published_time(value):
 if type(value) in (float,int):return float(value) if math.isfinite(value) and value>0 else None
 if not isinstance(value,str):return None
 try:
  if re.fullmatch(r'\d{8}',value):return datetime.datetime.strptime(value,'%Y%m%d').replace(tzinfo=datetime.timezone.utc).timestamp()
  result=datetime.datetime.fromisoformat(value.replace('Z','+00:00'));return result.replace(tzinfo=result.tzinfo or datetime.timezone.utc).timestamp()
 except ValueError:
  try:return email.utils.parsedate_to_datetime(value).timestamp()
  except (ValueError,TypeError,AttributeError):return None

def require_fresh(meta,now=None,max_age_hours=MAX_AGE_HOURS):
 now=now or time.time();stamp=published_time(meta.get('published_at')) or published_time(meta.get('timestamp')) or published_time(meta.get('upload_date'))
 if stamp is None or not -300<=now-stamp<=max_age_hours*3600:raise ValueError('A hírforrás videója régi, vagy nem igazolható a publikálási dátuma. Legfeljebb '+str(max_age_hours)+' órás, dátummal ellenőrzött forrás szükséges.')
 return stamp

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS verified_news(project TEXT,url TEXT,data TEXT,checked REAL,PRIMARY KEY(project,url));
 CREATE TABLE IF NOT EXISTS source_handoffs(id TEXT PRIMARY KEY,project TEXT,bundle TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS news_source_use(project TEXT,video_id TEXT,handoff TEXT,run TEXT,created REAL,PRIMARY KEY(project,video_id));
 CREATE TABLE IF NOT EXISTS source_requests(project TEXT,origin TEXT,handoff TEXT,PRIMARY KEY(project,origin));''');s.db.commit()

def policy_for_job(s,jobid):
 row=s.db.execute('SELECT project,payload,prompt FROM jobs WHERE id=?',(jobid,)).fetchone()
 if not row:return None
 p=json.loads(row['payload']);rid=p.get('automation_run')
 if p.get('current_news') is True:return 'current_news'
 if not rid:return None
 a=s.db.execute('SELECT a.name,a.kind,a.config FROM automation_runs r JOIN automations a ON a.id=r.automation WHERE r.id=? AND r.project=?',(rid,row['project'])).fetchone()
 if not a:return None
 from model_router import normalized
 cfg=json.loads(a['config']);label=normalized(a['name']+' '+str(cfg.get('prompt','')))
 if cfg.get('source_policy')=='current_news' or cfg.get('topic_source')=='trends' or ('trend' in label and re.search(r'video|short|gyart',label)):return 'current_news'
 return None

def remember_news(s,pid,results):
 schema(s);out=[]
 from clip_sources import youtube_id
 for hit in results:
  url=hit.get('url','');stamp=published_time(hit.get('published_at'))
  if not url.startswith('https://') or youtube_id(url) or stamp is None or not -300<=time.time()-stamp<=MAX_AGE_HOURS*3600:continue
  item=dict(url=url,title=str(hit.get('title',''))[:500],content=str(hit.get('content',''))[:2500],published_at=stamp,published_at_iso=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc).isoformat(),checked_at=time.time())
  s.db.execute('INSERT OR REPLACE INTO verified_news VALUES(?,?,?,?)',(pid,url,json.dumps(item,ensure_ascii=False),time.time()));out.append(item)
 s.db.commit();return out

def news_for(s,pid,urls):
 schema(s);out=[]
 for url in urls[:5]:
  row=s.db.execute('SELECT data FROM verified_news WHERE project=? AND url=?',(pid,url)).fetchone()
  if row:
   item=json.loads(row[0])
   try:require_fresh(item)
   except ValueError:continue
   out.append(item)
 return out

def matching_news(meta,news):
 from model_router import normalized
 stop=set('the and that this with from for after over about into says said latest breaking news video highlights moments today stream streamer official watch update live viral streaming clips clip compilation youtube twitch'.split())
 text=normalized(str(meta.get('title',''))+' '+str(meta.get('description',''))[:1500]);words=set(re.findall(r'\w{3,}',text))-stop
 # Require actual event words in common with a dated news report, not merely a year or 'viral'.
 for item in news:
  terms=set(re.findall(r'\w{3,}',normalized(item.get('title',''))))-stop;terms={w for w in terms if not w.isdigit()}
  shared=sorted(words&terms)
  if len(shared)>=min(3,max(2,len(terms)//2)):return dict(news_url=item['url'],shared_terms=shared[:12])
 return None

def lookup_videos(s,pid,urls):
 from clip_sources import youtube_id
 ids=list(dict.fromkeys(youtube_id(u) for u in urls));ids=[i for i in ids if i]
 if not ids:return []
 request=dict(ids=ids[:5]);p=subprocess.run([str(s.root/'media-runtime/bin/python'),str(Path(__file__).with_name('youtube_runtime.py')),'source_metadata',str(s.root),pid],input=json.dumps(request),capture_output=True,text=True,timeout=30)
 try:data=json.loads(p.stdout)
 except ValueError:raise ValueError('A videólinkek dátumellenőrzése nem elérhető. Régi vagy ismeretlen korú forrást nem helyettesítünk be.')
 if not data.get('ok'):raise ValueError('A videólinkek dátumellenőrzése nem sikerült.')
 return data.get('videos',[])

def bundle(s,pid,sources,topic,news=None,mode='explicit',metadata=None):
 from clip_sources import source_id,source_url
 schema(s)
 from clip_sources import schema as clip_schema
 clip_schema(s)
 if mode not in ('explicit','current_news'):raise ValueError('Ismeretlen forráspolitika.')
 if not isinstance(sources,list) or not 1<=len(sources)<=5 or any(not isinstance(u,str) or not source_id(u) for u in sources):raise ValueError('1–5 konkrét https YouTube- vagy Twitch-link szükséges.')
 urls=list(dict.fromkeys(source_url(source_id(u)) for u in sources))
 metas=metadata if metadata is not None else lookup_videos(s,pid,urls) if mode=='current_news' else []
 checked=[];errors=[]
 for url in urls:
  identifier=source_id(url);meta=next((m for m in metas if m.get('id')==identifier),{})
  if mode=='current_news':
   try:
    if not news:raise ValueError('Hiányzik a dátummal ellenőrzött hírcikk.')
    for report in news:require_fresh(report)
    require_fresh(meta)
    if s.db.execute('SELECT 1 FROM clip_downloads WHERE project=? AND video_id=?',(pid,identifier)).fetchone() or s.db.execute('SELECT 1 FROM news_source_use WHERE project=? AND video_id=?',(pid,identifier)).fetchone():raise ValueError('Ezt a videóforrást a projekt már használta; másik friss link szükséges.')
    match=matching_news(meta,news or [])
    if not match:raise ValueError('A videó metaadatai nem kapcsolódnak eléggé az ellenőrzött friss hírhez.')
   except ValueError as e:errors.append(str(e));continue
  else:match=None
  checked.append(dict(url=url,id=identifier,metadata=meta,news_match=match))
 if not checked:raise ValueError('Nincs új, friss és hírhez igazolt videólink. '+(' '.join(dict.fromkeys(errors))[:700] or 'Előbb végezz dátumszűrt hírkeresést, majd annak konkrét videólinkjeit add át.'))
 if mode=='current_news' and not news:raise ValueError('A trendalapú gyártáshoz ellenőrzött friss hírcikk is szükséges.')
 return dict(version=1,mode=mode,topic=str(topic)[:200],created_at=time.time(),max_age_hours=MAX_AGE_HOURS,sources=checked,news=(news or [])[:5],rejected=errors[:5])

def persist(s,pid,data,origin=None):
 schema(s);hid=uuid.uuid4().hex
 s.db.execute('BEGIN IMMEDIATE')
 try:
  if origin:
   prior=s.db.execute('SELECT handoff FROM source_requests WHERE project=? AND origin=?',(pid,origin)).fetchone()
   if prior:s.db.rollback();return prior[0]
  if data['mode']=='current_news' or data.get('research',{}).get('kind') in ('youtube_public','gta6_stream'):
   for item in data['sources']:
    if s.db.execute('SELECT 1 FROM news_source_use WHERE project=? AND video_id=?',(pid,item['id'])).fetchone():raise ValueError('Ezt a forrást már egy másik gyártás lefoglalta.')
    s.db.execute('INSERT INTO news_source_use VALUES(?,?,?,?,?)',(pid,item['id'],hid,None,time.time()))
  s.db.execute('INSERT INTO source_handoffs VALUES(?,?,?,?)',(hid,pid,json.dumps(data,ensure_ascii=False),time.time()))
  if origin:s.db.execute('INSERT INTO source_requests VALUES(?,?,?)',(pid,origin,hid))
  s.db.commit()
 except Exception:s.db.rollback();raise
 return hid

def resolve(s,pid,hid):
 schema(s);row=s.db.execute('SELECT bundle FROM source_handoffs WHERE project=? AND id=?',(pid,hid)).fetchone()
 if not row:raise ValueError('A forrásátadás nem ehhez a projekthez tartozik.')
 data=json.loads(row[0])
 if data['mode']=='current_news' or data.get('research',{}).get('kind')=='youtube_public':
  for item in data['sources']:require_fresh(item['metadata'],max_age_hours=data['max_age_hours'])
  for item in data.get('news',[]):require_fresh(item,max_age_hours=data['max_age_hours'])
 return data

def release(s,pid,hid):
 s.db.execute('DELETE FROM source_requests WHERE project=? AND handoff=?',(pid,hid))
 s.db.execute('DELETE FROM news_source_use WHERE project=? AND handoff=? AND run IS NULL',(pid,hid));s.db.commit()

def submit(s,pid,data,requirements=None,origin=None):
 from execution_queue import submit_short
 hid=persist(s,pid,data,origin)
 try:return submit_short(s,pid,data['sources'][0]['url'],requirements,origin,source_handoff=hid)
 except Exception:release(s,pid,hid);raise


def source_step(s,agent,job,data):
 """No broad search, unrelated cache fallback, or duplicate source substitution."""
 from clip_sources import download_clip
 from execution_queue import DeferredExecution
 handoff=resolve(s,job['project'],data['source_handoff']);data['source_bundle']=handoff;data.setdefault('sources',[]);errors=[]
 for item in handoff['sources']:
  if any(x.get('metadata',{}).get('id')==item['id'] for x in data['sources']):continue
  try:
   # Registration preserves the verified URL and API publication metadata.
   cid=uuid.uuid4().hex;s.db.execute('INSERT INTO clip_candidates VALUES(?,?,?,?,?)',(cid,job['project'],item['id'],json.dumps(dict(item['metadata'],id=item['id'],url=item['url'])),time.time()));s.db.commit()
   source=download_clip(s,agent,dict(candidate_id=cid,start=(item.get('window') or {}).get('start',0),full_source=data.get('content_scope')=='full_content' and not item.get('window'),duration=(item.get('window') or {}).get('duration') or min(180,item['metadata'].get('duration') or 180),max_age_hours=handoff['max_age_hours'] if handoff['mode']=='current_news' or handoff.get('research',{}).get('kind')=='youtube_public' else None,source_handoff=data['source_handoff']),job['id'])
   if handoff.get('research',{}).get('kind')=='youtube_public':require_fresh(source['metadata'],max_age_hours=handoff['max_age_hours'])
   if handoff['mode']=='current_news':
    require_fresh(source['metadata'],max_age_hours=handoff['max_age_hours'])
    if not matching_news(source['metadata'],handoff.get('news',[])):raise ValueError('A letöltött videó metaadatai nem igazolják a friss híreseményt.')
   data['sources'].append(source)
  except DeferredExecution:raise
  except Exception as exc:errors.append(str(exc));s.job_stage(job['id'],'source_rejected','Forráslink elutasítva · következő ellenőrzött link',str(exc)[:500])
  if s.cancelled(job['id']):raise ValueError('Leállítva.')
 if not data['sources']:raise ValueError('Az átadott linkekből nincs friss, elérhető forrás. '+(' | '.join(errors))[:900])
 data['source']=data['sources'][0];return json.dumps(dict(sources=data['sources'],news=handoff.get('news'),policy=handoff['mode']),ensure_ascii=False)


def agent_submit(s,pid,args,job):
 from clip_sources import source_id
 from execution_queue import submit_short
 payload=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=? AND project=?',(job,pid)).fetchone()[0]);rid=payload.get('automation_run')
 origin='automation:'+rid if rid else None
 if payload.get('farm_research') and payload.get('production_submission'):return dict(payload['production_submission'],existing=True)
 if rid:
  # An agent retry must refer to its existing production, not submit another video.
  previous=s.rows("SELECT id,payload,kind FROM jobs WHERE project=? AND json_extract(payload,'$.automation_run')=? AND (kind='short_request' OR json_extract(payload,'$.auto_step') IS NOT NULL)",(pid,rid))
  if previous:return dict(existing=True,jobs={str(i):r['id'] for i,r in enumerate(previous)},run=json.loads(previous[0]['payload']).get('run'))
 current=policy_for_job(s,job)=='current_news';query=args.get('query','');sources=args.get('sources')
 if sources is None:sources=list(dict.fromkeys(u.rstrip('.,);]') for u in re.findall(r'https://[^\s<>"\[\]]+',query) if source_id(u.rstrip('.,);]'))))
 if not isinstance(sources,list):raise ValueError('A sources mező videólinkek listája legyen.')
 if current and not sources:raise ValueError('A friss hírhez konkrét videólinkek szükségesek: sources=[linkek], news_urls=[web_search hírlinkek]. Általános keresőkifejezést nem indítunk helyettük.')
 if not sources:return submit_short(s,pid,query,origin=origin)
 urls=args.get('news_urls',[])
 if not isinstance(urls,list) or any(not isinstance(u,str) for u in urls):raise ValueError('A news_urls mező hírlinkek listája legyen.')
 data=bundle(s,pid,sources,query,news_for(s,pid,urls),mode='current_news' if current else 'explicit')
 result=submit(s,pid,data,payload.get('requirements'),origin=origin)
 if payload.get('farm_research'):
  payload['production_submission']=result;s.db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),job));s.db.commit()
 return result


def video_search_query(headline):
 """Use event terms rather than a full newspaper headline plus publisher suffix."""
 title=re.split(r'\s+[|–—]\s+|\s+-\s+',headline)[0]
 stop=set('the and for with from after before about into its their this that these those says said say she he they her his has have had was were will would could should back square one new latest news unveiled unveils following participates following meeting in on at a an to of is are be it s'.split())
 words=[w for w in re.findall(r"[\w]+(?:['’][\w]+)?",title) if w.casefold() not in stop and not w.casefold().endswith(('’s',"'s"))]
 # Names at the front are particularly important; retain enough event terms for disambiguation.
 return ' '.join(words[:8])[:180] or headline[:180]

def discover_news_videos(s,pid,query):
 """Search the dated API catalogue around verified news; no unrestricted ytsearch."""
 if not isinstance(query,str) or not 2<=len(query)<=180:raise ValueError('2–180 karakteres friss esemény szükséges.')
 schema(s)
 reports=news_for(s,pid,[r[0] for r in s.db.execute('SELECT url FROM verified_news WHERE project=? ORDER BY checked DESC LIMIT 5',(pid,))])
 if not reports:raise ValueError('Előbb a web_search eszközzel keress dátummal igazolt, friss hírt.')
 request=dict(topics=[query],news={query:reports},event_queries={query:video_search_query(query)},max_video_seconds=1800)
 p=subprocess.run([str(s.root/'media-runtime/bin/python'),str(Path(__file__).with_name('youtube_runtime.py')),'trend_samples',str(s.root),pid],input=json.dumps(request),capture_output=True,text=True,timeout=55)
 try:result=json.loads(p.stdout)
 except ValueError:raise ValueError('A friss videók keresése nem elérhető. Régi forrással nem helyettesítjük.')
 if not result.get('ok'):raise ValueError('A friss videók keresése nem sikerült. '+str(result.get('message',''))[:350])
 from clip_sources import schema as clip_schema
 clip_schema(s);out=[]
 for meta in result.get('samples',{}).get(query,{}).get('videos',[]):
  if s.db.execute('SELECT 1 FROM clip_downloads WHERE project=? AND video_id=?',(pid,meta['id'])).fetchone() or s.db.execute('SELECT 1 FROM news_source_use WHERE project=? AND video_id=?',(pid,meta['id'])).fetchone():continue
  cid=uuid.uuid4().hex;s.db.execute('INSERT INTO clip_candidates VALUES(?,?,?,?,?)',(cid,pid,meta['id'],json.dumps(meta),time.time()))
  out.append(dict(meta,candidate_id=cid,news_match=matching_news(meta,reports)))
 s.db.commit();return out
