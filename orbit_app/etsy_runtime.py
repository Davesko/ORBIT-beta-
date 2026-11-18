"""Waits on this Mac for the browser to come back from Etsy's consent page, then ends. Started by etsy.connect."""
import html,http.server,sys,time,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import etsy

class Back(http.server.BaseHTTPRequestHandler):
 done=False
 def log_message(self,*args):pass
 def do_GET(self):
  url=urllib.parse.urlsplit(self.path);query=dict(urllib.parse.parse_qsl(url.query))
  if url.path!='/etsy':self.send_error(404);return
  try:
   if query.get('error'):raise etsy.EtsyError('Az Etsy nem adott engedélyt ('+query['error'][:80]+').')
   etsy.finish_login(query.get('code'),query.get('state'))
   text='Kész: az ORBIT csatlakozott az Etsy-boltodhoz. Ezt az ablakot bezárhatod.'
  except (ValueError,KeyError,OSError) as exc:
   text=str(exc)[:300];etsy.update_state(login='error',login_error=text)
  page=('<!doctype html><meta charset="utf-8"><title>ORBIT · Etsy</title><body style="font:16px -apple-system,sans-serif;margin:15vh auto;max-width:34em;padding:0 16px"><h1>ORBIT · Etsy</h1><p>'+html.escape(text)+'</p>').encode()
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(page)));self.end_headers();self.wfile.write(page)
  Back.done=True

def main():
 try:server=http.server.HTTPServer(('127.0.0.1',etsy.PORT),Back)
 except OSError:return  # An earlier login is still listening; it reads the same pending login.
 server.timeout=5;end=time.time()+900
 while not Back.done and time.time()<end:server.handle_request()
 server.server_close()

if __name__=='__main__':main()
