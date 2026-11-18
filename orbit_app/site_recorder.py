"""Record a public website with ORBIT's own fetcher, so product code never needs the network.

A concierge request ("send me the report for my shop") names a site anyone could type in. The Autopilot's
code must not reach that address itself: it runs offline in the sandbox on what ORBIT recorded here
(ORBIT_OFFLINE=1, realdata/<host>.json.gz with [[asked url, final url, html], ...]). The recorder keeps to
the same site, respects robots.txt, waits between requests and caps sizes.
"""
import gzip,json,re,time,urllib.error,urllib.parse,urllib.request,urllib.robotparser
from pathlib import Path

UA='ORBIT-Recorder/1.0 (requested page check)'
MAX_BYTES=2*1024*1024
TRACKING=re.compile(r'^(?:_ga|_gl|utm_\w+|fbclid|gclid|mc_\w+)$',re.I)

def site_of(netloc):
 parts=netloc.lower().split(':')[0].split('.')
 return '.'.join(parts[-3:] if len(parts)>2 and parts[-2] in ('co','com','org','gov') else parts[-2:])

def clean(url):
 u=urllib.parse.urlparse(url)
 query=urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(u.query) if not TRACKING.match(k)])
 return urllib.parse.urlunparse((u.scheme,u.netloc,u.path,'',query,''))

def host_of(url):return urllib.parse.urlparse(url).netloc.lower().removeprefix('www.')

def links(html,base):
 out=[]
 for m in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',html,re.I|re.S):
  text=re.sub(r'<[^>]+>',' ',m.group(2))
  out.append((clean(urllib.parse.urljoin(base,m.group(1))),re.sub(r'\s+',' ',text).strip()))
 return out

def fetch(url,robots=None):
 if robots is not None and not robots.can_fetch(UA,url):raise PermissionError('a robots.txt nem engedi')
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html'})
 with urllib.request.urlopen(req,timeout=15) as r:
  if 'html' not in (r.headers.get('Content-Type') or 'text/html'):raise ValueError('nem HTML')
  raw=r.read(MAX_BYTES+1)[:MAX_BYTES]
  return r.geturl(),raw.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')

def robots_for(site):
 """robots.txt read with ORBIT's own User-Agent. RobotFileParser.read() sends Python's default one, which
 Cloudflare answers with 403, and a 403 means "disallow all": the first TermékA request (2026-11-01, a
 site whose robots.txt has no rules at all) failed with "a robots.txt nem engedi". None: no robots.txt read."""
 robots=urllib.robotparser.RobotFileParser(urllib.parse.urljoin(site,'/robots.txt'))
 try:
  with urllib.request.urlopen(urllib.request.Request(robots.url,headers={'User-Agent':UA}),timeout=15) as r:
   robots.parse(r.read(512*1024).decode('utf-8',errors='replace').splitlines())
 except urllib.error.HTTPError as exc:
  # The same rule as Python's own reader, but for ORBIT's request: 401/403 forbid, a missing file allows.
  if exc.code in (401,403):robots.disallow_all=True
  else:robots.allow_all=True
 except Exception:return None
 return robots

def record(site,words=None,max_pages=7,delay=1.0,getter=None):
 """{url, recorded, pages:[[asked, final, html]], notes} for the site's home page and the same-site pages
 whose link text or path matches words (a regex), at most max_pages in all."""
 if not re.match(r'^https?://',site):site='https://'+site
 robots=None
 if getter is None:
  robots=robots_for(site)
  getter=lambda u:fetch(u,robots)
 start=clean(site);pages=[];notes=[]
 final,html=getter(start);pages.append([start,final,html])
 if words and max_pages>1:
  home=site_of(urllib.parse.urlparse(final).netloc);seen={start,final}
  for url,text in links(html,final):
   u=urllib.parse.urlparse(url)
   if len(pages)>=max_pages:break
   if u.scheme not in ('http','https') or site_of(u.netloc)!=home or url in seen:continue
   if not re.search(words,text+' '+urllib.parse.unquote(u.path),re.I):continue
   seen.add(url)
   if robots is not None:time.sleep(delay)
   try:got,body=getter(url);pages.append([url,got,body])
   except Exception as exc:notes.append(url+': '+str(exc)[:80])
 return dict(url=start,recorded=time.strftime('%Y-%m-%d %H:%M'),pages=pages,notes=notes)

def save(recording,folder):
 """Write the recording where offline product code finds it: <folder>/realdata/<host>.json.gz."""
 path=Path(folder)/'realdata'/(host_of(recording['url'])+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(recording,f,ensure_ascii=False)
 return path
