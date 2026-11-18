"""Fresh public research with real URLs, cache and bounded provider fallbacks."""
import hashlib,json,time
from pathlib import Path
import connections
from public_web import valid_url

CACHE_DAYS=3

def search(query,limit=6,root=None,fresh_news=False):
 if not isinstance(query,str) or not 2<=len(query)<=300:raise ValueError('2–300 karakteres keresés szükséges.')
 limit=max(1,min(8,int(limit)));path=connections.folder(root)/'research-cache';path.mkdir(exist_ok=True)
 key=hashlib.sha256((' '.join(query.casefold().split())+str(limit)+str(fresh_news)).encode()).hexdigest();cache=path/(key+'.json')
 try:
  saved=json.loads(cache.read_text())
  # Market research barely changes within days; reusing it keeps the small monthly search quota
  # for new questions. News stays fresh.
  if time.time()-saved['retrieved_at']<(300 if fresh_news else CACHE_DAYS*86400) and saved.get('results') and (fresh_news or not saved.get('provider_errors')):return dict(saved,cached=True)
 except (OSError,ValueError,KeyError):pass
 errors=[];result=None
 if connections.allowed('tavily',root):
  try:
   params=dict(query=query,max_results=limit,search_depth='basic',include_answer=False)
   if fresh_news:params.update(topic='news',days=3)
   data=connections.http('tavily','search',params,root)
   result=dict(provider='Tavily',results=[dict(title=x.get('title',''),url=valid_url(x['url']),content=str(x.get('content',''))[:2500],published_at=x.get('published_date')) for x in data.get('results',[])[:limit]])
  except (ValueError,OSError) as e:errors.append(str(e))
 if result is None:
  from public_web import search as public_search
  try:found=public_search(query,limit)
  except (ValueError,OSError) as e:found=[];errors.append('Nyilvános webkeresés: '+type(e).__name__)
  result=dict(provider='Nyilvános webkeresés',results=found)
  if not found:
   # No key, no usable feed: the Mac's own browser searches, headless (no window, no mouse, no accounts).
   import browser_web
   try:found=browser_web.search(query,limit)
   except (ValueError,OSError) as e:found=[];errors.append('Saját böngésző: '+type(e).__name__)
   if found:result=dict(provider='Saját böngésző (háttérben)',results=found)
 if fresh_news:
  from source_policy import published_time,MAX_AGE_HOURS
  result['results']=[x for x in result['results'] if (published_time(x.get('published_at')) is not None and -300<=time.time()-published_time(x['published_at'])<=MAX_AGE_HOURS*3600)]
  if not result['results']:
   try:
    result['results']=news_rss(query,limit)
    if result['results']:result['provider']='Google News RSS'
   except (ValueError,OSError,TimeoutError) as exc:errors.append('Google News RSS: '+type(exc).__name__)
  result['source_policy']='current_news'
 result.update(query=query,retrieved_at=time.time(),cached=False,provider_errors=errors);cache.write_text(json.dumps(result,ensure_ascii=False));return result

def news_rss(query,limit=6):
 """Dated public Google News results when provider quota or date coverage is empty."""
 from public_web import fetch
 from urllib.parse import quote
 import xml.etree.ElementTree as ET
 from source_policy import published_time,MAX_AGE_HOURS
 raw,_=fetch('https://news.google.com/rss/search?q='+quote(query+' when:3d')+'&hl=en-US&gl=US&ceid=US:en',1500000)
 out=[]
 for item in ET.fromstring(raw).findall('./channel/item'):
  stamp=published_time(item.findtext('pubDate'));url=item.findtext('link') or '';title=item.findtext('title') or ''
  if stamp is None or not -300<=time.time()-stamp<=MAX_AGE_HOURS*3600 or not title or not url.startswith('https://'):continue
  out.append(dict(title=title,url=valid_url(url),content=title,published_at=stamp,date_source='Google News RSS pubDate'))
  if len(out)>=limit:break
 return out

def read(url,root=None):
 url=valid_url(url)
 if connections.allowed('jina',root):
  try:
   text=connections.http('jina',url,root=root,text_response=True,headers={'X-Return-Format':'text'})
   return dict(url=url,text=text[:18000],provider='Jina Reader',retrieved_at=time.time())
  except (ValueError,OSError):pass
 from public_web import read as public_read
 try:page=public_read(url)
 except (ValueError,OSError):page=dict(url=url,text='')
 if len(page.get('text') or '')<200:
  # A page that is empty without JavaScript is rendered by the Mac's own browser, headless.
  import browser_web
  rendered=browser_web.read(url)
  if len(rendered['text'])>len(page.get('text') or ''):
   return dict(page,text=rendered['text'],provider='Saját böngésző (háttérben)',retrieved_at=time.time())
  if not page.get('text'):raise ValueError('Az oldal nem olvasható: '+url)
 return dict(page,provider='Közvetlen oldalolvasás',retrieved_at=time.time())
