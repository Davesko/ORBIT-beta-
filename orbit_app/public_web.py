"""Bounded public-page retrieval; no cookies, private-network access or script execution."""
import html,ipaddress,re,socket,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from html.parser import HTMLParser

def valid_url(url):
 p=urllib.parse.urlsplit(str(url))
 if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):raise ValueError('Nyilvános http/https webcím szükséges.')
 for item in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('Helyi vagy privát hálózati cím nem olvasható webes forrásként.')
 return url
class PageText(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.parts=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style','noscript'):self.skip+=1
  if tag=='a':self.links.extend(v for k,v in attrs if k=='href' and v)
 def handle_endtag(self,tag):
  if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.parts.append(data)
def fetch(url,limit=700000):
 class PublicRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,req,fp,code,msg,headers,newurl):valid_url(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
 valid_url(url);request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; ORBIT research; public pages only)','Accept':'text/html,application/xml,text/plain'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),PublicRedirect()).open(request,timeout=20) as response:
  kind=response.headers.get_content_type()
  if kind not in ('text/html','text/plain','application/xml','text/xml','application/rss+xml'):raise ValueError('Csak nyilvános szöveges oldal olvasható.')
  raw=response.read(limit+1)
  if len(raw)>limit:raw=raw[:limit]
  return raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'),response.url

def read(url):
 raw,final=fetch(url);parser=PageText();parser.feed(raw);text=re.sub(r'\s+',' ',' '.join(parser.parts)).strip()
 emails=sorted(set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',html.unescape(raw))))
 emails=[e for e in emails if not re.search(r'\.(png|jpg|jpeg|webp|svg)$',e,re.I)][:20]
 links=[]
 for href in parser.links:
  link=urllib.parse.urljoin(final,href);p=urllib.parse.urlsplit(link)
  if p.scheme in ('http','https') and p.hostname==urllib.parse.urlsplit(final).hostname and any(w in p.path.lower() for w in ('contact','kontakt','about','impress','kapcsolat')) and link not in links:links.append(link)
 return dict(url=final,text=text[:18000],emails=emails,contact_links=links[:5])

def search(query,limit=8):
 if not isinstance(query,str) or not 2<=len(query)<=300:raise ValueError('2–300 karakteres keresési kérés szükséges.')
 url='https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query)
 raw,_=fetch(url);root=ET.fromstring(raw);results=[]
 for item in root.findall('.//item'):
  link=item.findtext('link','');title=item.findtext('title','');description=item.findtext('description','')
  if urllib.parse.urlsplit(link).scheme not in ('http','https'):continue
  results.append(dict(title=title,url=link,description=description[:1500]))
  if len(results)>=limit:break
 return results
