"""Private companion, loopback only; put an authenticated HTTPS VPN proxy in front."""
import argparse,hmac,json,secrets,os,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from studio import Studio,ROOT
WEB=Path(__file__).with_name('mobile')

def token(root=ROOT):
 p=root/'integrations/mobile/access.key';p.parent.mkdir(parents=True,exist_ok=True)
 try:
  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
 except FileExistsError:pass
 return p.read_text().strip()

def serve(port=47832,root=ROOT):
 secret=token(root)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,code,body,kind='application/json'):
   raw=json.dumps(body,ensure_ascii=False).encode() if kind=='application/json' else body
   self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(raw)
  def auth(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+secret)
  def do_GET(self):
   if self.path in ('/','/app.js','/style.css','/manifest.webmanifest','/icon.svg'):
    name='index.html' if self.path=='/' else self.path[1:];mime={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.webmanifest':'application/manifest+json','.svg':'image/svg+xml'}
    return self.send(200,(WEB/name).read_bytes(),mime[Path(name).suffix])
   if self.path!='/api/state':return self.send(404,dict(error='Nem található.'))
   if not self.auth():return self.send(401,dict(error='Kapcsolódási kulcs szükséges.'))
   s=Studio(root)
   try:
    projects=s.rows('SELECT id,name,description FROM projects')
    jobs=s.rows('SELECT id,project,kind,status,prompt,error,created FROM jobs ORDER BY created DESC LIMIT 40')
    from commander import state
    chat=state(s,'universe',True)
    return self.send(200,dict(projects=projects,jobs=jobs,turns=chat.get('turns',[]),observed_at=time.time()))
   except Exception:return self.send(500,dict(error='Az ORBIT állapota most nem olvasható.'))
   finally:s.db.close()
  def do_POST(self):
   if self.path!='/api/chat':return self.send(404,dict(error='Nem található.'))
   if not self.auth():return self.send(401,dict(error='Hibás kapcsolódási kulcs.'))
   origin=self.headers.get('Origin')
   if origin and urlsplit(origin).netloc!=self.headers.get('Host'):return self.send(403,dict(error='Idegen eredetű kérés.'))
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=20000:raise ValueError()
    data=json.loads(self.rfile.read(size));prompt=data.get('prompt');rid=data.get('id')
    if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=6000 or not isinstance(rid,str) or len(rid)>80:raise ValueError()
   except (ValueError,TypeError):return self.send(400,dict(error='Érvénytelen üzenet.'))
   s=Studio(root)
   try:
    from commander import enqueue,schema
    schema(s);s.db.execute('CREATE TABLE IF NOT EXISTS mobile_requests(id TEXT PRIMARY KEY,job TEXT)');s.db.commit()
    # One HTTP writer thread owns admission to avoid double submissions.
    with server.admission:
     prior=s.db.execute('SELECT job FROM mobile_requests WHERE id=?',(rid,)).fetchone()
     if prior:return self.send(200,dict(job=prior[0]))
     job=enqueue(s,'universe',prompt.strip(),'auto',None,True)
     s.db.execute('INSERT INTO mobile_requests VALUES(?,?)',(rid,job));s.db.commit()
    return self.send(200,dict(job=job))
   except Exception:return self.send(500,dict(error='Az üzenetet nem sikerült átadni.'))
   finally:s.db.close()
 import threading
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.admission=threading.Lock();return server
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=47832);args=p.parse_args();serve(args.port).serve_forever()
