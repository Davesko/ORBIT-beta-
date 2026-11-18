"""ORBIT server base for API products (provided by ORBIT, do not edit; ORBIT restores it).

Usage in server.py:
    from orbit_server_base import JSONHandler, main
    class Handler(JSONHandler):
        def get_health(self):return 200,{'ok':True}
        def post_extract(self,data):return 200,{'netto':100}
    def checks(call):
        status,body=call('POST','/extract',{'text':'Nettó: 100'});assert status==200,body
    if __name__=='__main__':main(Handler,checks)

GET /health calls get_health(), POST /extract calls post_extract(data) with the parsed JSON body;
dashes in the path become underscores and / calls get_index(). Each method returns (status, dict).
Replies are UTF-8 JSON (accents are fine), unknown routes give 404, invalid JSON 400, an exception
500. With REQUIRE_KEY=True, POST requests need the X-API-Key header or a Bearer token equal to the
API_KEY or ORBIT_TEST_API_KEY environment variable.

python3 server.py --self-test  starts the server on a free port, calls GET /health and checks(call),
                               then stops (exit code 0 when everything passed).
python3 server.py --port 8080  serves until stopped (PORT in the environment works too).
Standard library only.
"""
import json,os,sys,threading,urllib.error,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

MAX_BODY=1024*1024

class JSONHandler(BaseHTTPRequestHandler):
    REQUIRE_KEY=False

    def log_message(self,*args):pass

    def reply(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def route(self,method):
        name=self.path.split('?',1)[0].strip('/').replace('-','_').replace('/','_') or 'index'
        return getattr(self,method+'_'+name,None)

    def authorized(self):
        key=os.environ.get('API_KEY') or os.environ.get('ORBIT_TEST_API_KEY')
        if not self.REQUIRE_KEY:return True
        if not key:return False
        sent=self.headers.get('X-API-Key') or (self.headers.get('Authorization') or '').replace('Bearer ','',1)
        return sent==key

    def handle_method(self,method):
        handler=self.route(method)
        if handler is None:return self.reply(404,{'error':'Ismeretlen végpont: '+self.path})
        try:
            if method=='post':
                if not self.authorized():return self.reply(401,{'error':'Hiányzó vagy hibás API-kulcs.'})
                size=int(self.headers.get('Content-Length') or 0)
                if size>MAX_BODY:return self.reply(413,{'error':'Túl nagy kérés.'})
                try:data=json.loads(self.rfile.read(size) or b'{}')
                except ValueError:return self.reply(400,{'error':'Érvénytelen JSON.'})
                status,body=handler(data)
            else:status,body=handler()
        except Exception as exc:
            return self.reply(500,{'error':type(exc).__name__+': '+str(exc)[:200]})
        self.reply(status,body)

    def do_GET(self):self.handle_method('get')
    def do_POST(self):self.handle_method('post')

def serve(handler,port):
    server=ThreadingHTTPServer(('127.0.0.1',port),handler)
    return server

def caller(port):
    def call(method,path,data=None,headers=None):
        hdr={'Content-Type':'application/json'};hdr.update(headers or {})
        key=os.environ.get('API_KEY') or os.environ.get('ORBIT_TEST_API_KEY')
        if key:hdr.setdefault('X-API-Key',key)
        body=None if data is None else json.dumps(data,ensure_ascii=False).encode('utf-8')
        req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=body,headers=hdr,method=method)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=10) as r:return r.status,json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b'{}')
    return call

def self_test(handler,checks=None):
    # A key-protected API still tests itself: without a configured key a temporary one is used.
    if not (os.environ.get('API_KEY') or os.environ.get('ORBIT_TEST_API_KEY')):os.environ['ORBIT_TEST_API_KEY']='orbit-self-test-key'
    server=serve(handler,0);port=server.server_address[1]
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        call=caller(port)
        if getattr(handler,'get_health',None):
            status,body=call('GET','/health');assert status==200,('GET /health',status,body)
        if checks:checks(call)
    except AssertionError as exc:
        print('SELF-TEST FAILED:',exc);return 1
    finally:
        server.shutdown();server.server_close()
    print('SELF-TEST OK');return 0

def main(handler,checks=None,argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if '--self-test' in argv:sys.exit(self_test(handler,checks))
    port=int(argv[argv.index('--port')+1]) if '--port' in argv else int(os.environ.get('PORT') or 0)
    if not port:print('Használat: python3 server.py --self-test | --port 8080');return
    server=serve(handler,port);print('Fut: http://127.0.0.1:'+str(port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

class _Demo(JSONHandler):
    REQUIRE_KEY=True
    def get_health(self):return 200,{'ok':True}
    def post_echo(self,data):return 200,{'szöveg':data.get('text','')}

def _checks(call):
    status,body=call('POST','/echo',{'text':'Érvénytelen? Nem.'});assert status==200 and body=={'szöveg':'Érvénytelen? Nem.'},body
    status,body=call('POST','/echo',{'text':'x'},{'X-API-Key':'rossz'});assert status==401,body
    status,body=call('GET','/nincs');assert status==404,body

if __name__=='__main__':
    os.environ.setdefault('ORBIT_TEST_API_KEY','orbit-demo-key')
    main(_Demo,_checks)
