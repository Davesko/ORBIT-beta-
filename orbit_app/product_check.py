"""Run the code the Autopilot built, so a milestone counts as built only if its code really runs.

Every product .py file must pass `python3 file.py --self-test` offline, and test_*.py files run
under unittest. The run is sandboxed: no network except localhost (an API server may test itself),
writes only inside the product folder, no inherited environment (no secrets), 60 s per file.
"""
import json,os,re,shutil,socket,subprocess,sys,tempfile,time,urllib.error,urllib.request
from contextlib import contextmanager
from pathlib import Path

TIMEOUT=60
SANDBOX='/usr/bin/sandbox-exec'

def profile(folder,tmp):
 return ('(version 1)(allow default)(deny network*)'
  # Only localhost: a broader "local ip" rule also matched outbound internet connections.
  '(allow network-bind network-inbound (local ip "localhost:*"))(allow network-outbound (remote ip "localhost:*") (remote unix-socket))'
  '(deny file-write*)(allow file-write* (subpath "'+str(folder)+'") (subpath "'+str(tmp)+'") (literal "/dev/null"))')

def copy_of(folder,tmp):
 """A fresh copy of the product to run in. TermékA's runner.py kept its cache in the product folder, so
 every later self-test found the previous run's job already cached and failed; tests now start clean and
 leave the product folder as it was."""
 work=Path(tempfile.mkdtemp(prefix='p-',dir=tmp))/'product'
 shutil.copytree(folder,work,ignore=shutil.ignore_patterns('__pycache__'),symlinks=True)
 return work

def run_report(folder,recording,args):
 """Run a product's report command offline in the sandbox on a recording ORBIT made (site_recorder), so the
 product code never reaches the requested site itself. args: the product .py file and its arguments."""
 folder=Path(folder).resolve()
 if not args or not re.fullmatch(r'[\w.-]+\.py',str(args[0])) or not (folder/str(args[0])).is_file():raise ValueError('Érvénytelen jelentésparancs.')
 if not os.path.exists(SANDBOX):return dict(ok=None,output='',error='A homokozó nem érhető el; a jelentés nem készült el.')
 import site_recorder
 with tempfile.TemporaryDirectory(prefix='orbit-report-') as tmp:
  tmp=str(Path(tmp).resolve());work=copy_of(folder,tmp);site_recorder.save(recording,work)
  env=dict(PATH='/usr/bin:/bin',HOME=tmp,TMPDIR=tmp,PYTHONDONTWRITEBYTECODE='1',LANG='en_US.UTF-8',ORBIT_OFFLINE='1')
  try:p=subprocess.run([SANDBOX,'-p',profile(work,tmp),sys.executable,'-E','-s']+[str(a) for a in args],cwd=str(work),env=env,capture_output=True,text=True,timeout=TIMEOUT)
  except subprocess.TimeoutExpired:return dict(ok=False,output='',error='Időtúllépés: '+str(TIMEOUT)+' s alatt nem készült el.')
  return dict(ok=p.returncode==0,output=(p.stdout or '')[-20000:],error=(p.stderr or '')[-1500:])

def command(path):
 if path.name.startswith('test_'):return [sys.executable,'-E','-s','-m','unittest',path.stem]
 return [sys.executable,'-E','-s',path.name,'--self-test']

def run(folder):
 """{ok, results:[{file, ok, code, output}]} for every product .py file, or ok=None when the
 sandbox is unavailable (the code is then not executed at all)."""
 folder=Path(folder).resolve();files=sorted(folder.glob('*.py'))
 if not files:return dict(ok=None,results=[],note='Nincs futtatható Python-fájl.')
 if not os.path.exists(SANDBOX):return dict(ok=None,results=[],note='A homokozó nem érhető el; a kód nem futott.')
 results=[]
 with tempfile.TemporaryDirectory(prefix='orbit-check-') as tmp:
  tmp=str(Path(tmp).resolve())
  # ORBIT_OFFLINE tells product code the sandbox has no internet: a TermékA check fetched real pages
  # and failed with 'urlopen error'; such code uses its recorded data (realdata/) here instead.
  env=dict(PATH='/usr/bin:/bin',HOME=tmp,TMPDIR=tmp,PYTHONDONTWRITEBYTECODE='1',LANG='en_US.UTF-8',ORBIT_OFFLINE='1')
  for path in files:
   work=copy_of(folder,tmp)
   try:
    p=subprocess.run([SANDBOX,'-p',profile(work,tmp)]+command(work/path.name),cwd=str(work),env=env,capture_output=True,text=True,timeout=TIMEOUT)
    out=(p.stdout+'\n'+p.stderr).strip();code=p.returncode
   except subprocess.TimeoutExpired:out='Időtúllépés: '+str(TIMEOUT)+' s alatt nem állt le (a --self-test ne indítson tartós szervert).';code=-1
   finally:shutil.rmtree(work.parent,ignore_errors=True)
   # The error line comes from the whole output: a JSON report's start is cut from the kept tail.
   results.append(dict(file=path.name,ok=code==0,code=code,output=out[-1500:],error=error_line(out,code) if code else ''))
 shutil.rmtree(folder/'__pycache__',ignore_errors=True)
 out=dict(ok=all(r['ok'] for r in results),results=results)
 live=smoke(folder)
 if live:out.update(smoke=live,ok=out['ok'] and live['ok'])
 return out

TEST_KEY='orbit-smoke-test-key'
def free_port():
 with socket.socket() as sk:sk.bind(('127.0.0.1',0));return sk.getsockname()[1]

def api_cases(folder):
 """Read only the checked-in test contract, never a user-supplied URL."""
 spec=folder/'smoke.json'
 if not (folder/'server.py').is_file() or not spec.is_file() or spec.is_symlink():return []
 reqs=json.loads(spec.read_text()).get('requests')
 if not isinstance(reqs,list) or not reqs:raise ValueError('A smoke.json nem tartalmaz API-kéréseket.')
 cases=reqs[:10]
 for r in cases:
  if not isinstance(r,dict) or str(r.get('method','GET')).upper() not in ('GET','POST') or not re.fullmatch(r'/[^\s#]*',str(r.get('path','/'))):
   raise ValueError('A smoke.json érvénytelen API-végpontot tartalmaz.')
 return cases

def request_body(folder,r):
 if r.get('json_file'):
  src=(folder/str(r['json_file'])).resolve()
  if folder.resolve() not in src.parents or src.stat().st_size>1024*1024:raise ValueError('Érvénytelen API-mintafájl.')
  return json.loads(src.read_bytes())
 return r.get('json',r.get('body'))

def api_examples(folder):
 try:return [dict(index=i,method=str(r.get('method','GET')).upper(),path=r.get('path','/'),body=request_body(folder,r)) for i,r in enumerate(api_cases(folder))]
 except (OSError,ValueError,AttributeError):return []

def api_profile(tmp,port):
 # Generated product code sees its copy and the Python runtime, plus one loopback listener.
 home=json.dumps(str(Path.home()))
 runtime=json.dumps(str(Path(sys.base_prefix).resolve()))
 return ('(version 1)(allow default)(deny file-read* (subpath '+home+') (subpath "/Volumes"))'
         '(allow file-read* (subpath '+runtime+'))'
         '(deny file-write*)(allow file-write* (subpath '+json.dumps(tmp)+') (literal "/dev/null"))'
         '(deny network*)(allow network-bind network-inbound (local ip "localhost:'+str(port)+'"))')

@contextmanager
def api_server(folder,boot=12):
 if not os.path.exists(SANDBOX):raise ValueError('A homokozó nem érhető el.')
 port=free_port()
 with tempfile.TemporaryDirectory(prefix='orbit-api-') as tmp:
  tmp=str(Path(tmp).resolve());work=copy_of(folder,tmp)
  if not (work/'server.py').is_file() or (work/'server.py').is_symlink():raise ValueError('A terméknek nincs futtatható server.py fájlja.')
  env=dict(PATH='/usr/bin:/bin',HOME=tmp,TMPDIR=tmp,PYTHONDONTWRITEBYTECODE='1',LANG='en_US.UTF-8',ORBIT_TEST_API_KEY=TEST_KEY,API_KEY=TEST_KEY,PORT=str(port),ORBIT_OFFLINE='1')
  with open(Path(tmp)/'server.log','w+b') as log:
   proc=subprocess.Popen([SANDBOX,'-p',api_profile(tmp,port),str(Path(sys.executable).resolve()),'-E','-s','server.py','--port',str(port)],cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:
    deadline=time.monotonic()+boot
    while proc.poll() is None and time.monotonic()<deadline:
     try:
      with socket.create_connection(('127.0.0.1',port),timeout=.4):pass
      break
     except OSError:time.sleep(.15)
    else:
     log.seek(0,os.SEEK_END);log.seek(max(0,log.tell()-400));detail=log.read(400).decode(errors='replace').strip()
     if proc.returncode==0:raise ValueError('A szerver --port módban azonnal kilépett; folyamatosan futnia kell (serve_forever).')
     raise ValueError('A szerver nem indult el: '+(detail or ('kilépési kód '+str(proc.returncode) if proc.returncode is not None else 'indítási időtúllépés')))
    yield work,port
   finally:
    import signal
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    proc.wait()

def smoke(folder,boot=20):
 folder=Path(folder).resolve()
 if not (folder/'server.py').is_file() or not (folder/'smoke.json').exists() or not os.path.exists(SANDBOX):return None
 try:
  reqs=api_cases(folder)
  if not reqs:raise ValueError('A szerverhez smoke.json és ellenőrzött API-minta szükséges.')
  with api_server(folder,boot) as (work,port):results=[call(work,port,r) for r in reqs]
 except (OSError,ValueError,AttributeError) as exc:return dict(ok=False,results=[],note=str(exc))
 return dict(ok=all(r['ok'] for r in results),results=results)

def try_api(folder,index,body):
 cases=api_cases(folder)
 if type(index) is not int or not 0<=index<len(cases):raise ValueError('Ismeretlen API-példa.')
 case=cases[index];r=dict(method=case.get('method','GET'),path=case.get('path','/'))
 if r['method']=='POST':
  if not isinstance(body,str) or len(body.encode())>128*1024:raise ValueError('Adj meg legfeljebb 128 KB JSON-t.')
  try:r['json']=json.loads(body)
  except ValueError:raise ValueError('A bemenet érvénytelen JSON.') from None
 with api_server(folder) as (work,port):return call(work,port,r,include_body=True)

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def call(folder,port,r,include_body=False):
 method=str(r.get('method','GET')).upper();path='/'+str(r.get('path','/')).lstrip('/');body=None
 label=method+' '+path
 try:
  if r.get('json_file'):
   src=(folder/str(r['json_file'])).resolve()
   if folder not in src.parents:raise ValueError('a json_file a termék mappáján kívül van')
   body=src.read_bytes()
  elif 'json' in r or 'body' in r:body=json.dumps(r['json'] if 'json' in r else r['body']).encode()
  hdr={'Content-Type':'application/json'}
  if r.get('no_auth') is not True:hdr.update({'X-API-Key':TEST_KEY,'Authorization':'Bearer '+TEST_KEY})
  req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=body,headers=hdr,method=method)
  t0=time.time()
  try:
   with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=10 if include_body else 15) as resp:status=resp.status;raw=resp.read(1024*1024)
  except urllib.error.HTTPError as e:status=e.code;raw=e.read(1024*1024)
  ms=round((time.time()-t0)*1000)
  try:data=json.loads(raw)
  except ValueError:data=None
  expect=r.get('expect',r.get('expect_status',200));missing=[];wrong=[]
  # "expect" is either the HTTP status or, as builders often write it, the response fields that must
  # match ({"status": "ok"}); then any HTTP status may carry them (an error answer is often 422).
  if isinstance(expect,dict):
   wrong=[k+' (várt '+json.dumps(v,ensure_ascii=False)+', kapott '+json.dumps(data.get(k) if isinstance(data,dict) else None,ensure_ascii=False)+')' for k,v in expect.items() if not isinstance(data,dict) or data.get(k)!=v]
   ok=not wrong
  else:
   try:ok=status==int(expect)
   except (TypeError,ValueError):return dict(request=label,status=status,ms=ms,ok=False,error='A smoke.json "expect" mezője HTTP-státusz (szám) vagy az elvárt válaszmezők objektuma legyen.')
  if ok and r.get('expect_keys'):
   missing=[k for k in r['expect_keys'] if not isinstance(data,dict) or k not in data]
   ok=not missing
  error='hiányzó mezők: '+', '.join(missing) if missing else 'eltérő mezők: '+'; '.join(wrong)[:180] if wrong else '' if ok else raw.decode('utf-8','replace')[:200]
  result=dict(request=label,status=status,ms=ms,ok=ok,error=error)
  if include_body:result['body']=raw[:48000].decode('utf-8','replace')
  return result
 except Exception as exc:return dict(request=label,status=None,ms=None,ok=False,error=str(exc)[:200])

FAILED_WORDS=('FAIL','FAILED','ERROR','HIBA')

def report_problems(output):
 """The failed checks of a JSON report a test runner printed, each with its own error. selfimprove.py
 prints one; the builder was given only '"stderr": "Traceback…' and never saw the report's own
 complaint about smoke.json under the copied traceback of ocr.py."""
 lines=str(output or '').splitlines()
 start=next((i for i,l in enumerate(lines) if l.lstrip().startswith('{')),None)
 if start is None:return []
 try:data=json.loads('\n'.join(lines[start:]))
 except ValueError:return []
 out=[]
 def walk(x,label):
  if isinstance(x,list):
   for y in x:walk(y,label)
  elif isinstance(x,dict):
   label=str(x.get('file') or x.get('name') or label)
   detail=next((x[k] for k in ('error','stderr','output','message') if isinstance(x.get(k),str) and x[k].strip()),'')
   failed=[k for k,v in x.items() if isinstance(v,str) and v.strip().upper() in FAILED_WORDS]
   if failed:out.append(label+': '+', '.join(failed)+' FAIL'+(' – '+error_line(detail,json_report=False) if detail else ''))
   elif isinstance(x.get('error'),str) and x['error'].strip():out.append(label+': '+error_line(x['error'],json_report=False))
   for k,v in x.items():
    if re.search(r'errors?$',k,re.I) and k!='error' and v:
     out.extend(str(e)[:160] for e in (v if isinstance(v,list) else [v]) if isinstance(e,str) and e.strip())
    elif isinstance(v,(dict,list)):walk(v,k)
 walk(data,'')
 return list(dict.fromkeys(out))

def error_line(output,code=None,json_report=True):
 """The line that says what went wrong: the last one naming an error, else the last meaningful line
 (a JSON report used to leave just "}" as the error the builder was given)."""
 if json_report and (problems:=report_problems(output)):return '; '.join(problems)[:300]
 lines=[l.strip() for l in str(output or '').splitlines() if l.strip()]
 named=[l for l in lines if re.search(r'Error|Exception|FAIL|assert|Traceback|hiba',l,re.I) and not l.startswith('Traceback')]
 meaningful=[l for l in lines if len(re.findall(r'\w',l))>=4]
 line=(named or meaningful or ['kilépési kód '+str(code)])[-1]
 # A generic closing "self-test: FAIL" says nothing; the specific failing checks above it do.
 if re.search(r'self[-_ ]?test\W*:?\W*FAIL',line,re.I):
  # The self-tests now print every mismatch ("brutto: expected 63500.0, got None") before the verdict.
  specific=[l for l in lines if l!=line and not re.search(r'self[-_ ]?test',l,re.I) and (re.search(r'FAIL',l) and l in named or re.search(r'\b(expected|got|várt|kapott)\b',l,re.I))]
  if specific:return ('; '.join(specific)+' → '+line)[:300]
 # Where it failed: the innermost traceback frame before that line ("ocr.py:172 (in self_test)"),
 # so the builder can find the failing check instead of guessing from "afa: None".
 if line in lines:
  frames=[re.search(r'File "([^"]+)", line (\d+)(?:, in (\S+))?',l) for l in lines[:lines.index(line)]]
  frame=next((f for f in reversed(frames) if f),None)
  if frame:line=frame.group(1).rsplit('/',1)[-1]+':'+frame.group(2)+(' (in '+frame.group(3)+')' if frame.group(3) else '')+' → '+line
 return line

def problem(r):
 """The error line of one file's run (older records only kept the output tail)."""
 return r.get('error') or error_line(r.get('output'),r.get('code'))

# Technical promises a sales page makes and the code that would keep them. TermékB's page promised
# Tesseract/PaddleOCR, webhooks and card payments while its code had none; it still counted as ready.
# Code None: a promise the product cannot measure (uptime), always reported.
CLAIMS=(
 ('Tesseract OCR',r'\btesseract\b',r'tesseract'),
 ('PaddleOCR',r'paddle\s*-?ocr',r'paddleocr'),
 ('EasyOCR',r'\beasyocr\b',r'easyocr'),
 ('OCR (szövegfelismerés képről)',r'\bOCR\b|szövegfelismer',r'tesseract|paddleocr|easyocr|ocrmypdf|image_to_string|textract|vision\.googleapis'),
 ('webhook',r'\bwebhook',r'webhook'),
 ('mesterséges intelligencia',r'\bAI\b|mesterséges intelligen|\bGPT\b|\bLLM\b|gépi tanul',r'ollama|openai|anthropic|\bllm\b|/api/chat|/api/generate|sklearn|torch'),
 ('kártyás fizetés (Stripe)',r'\bstripe\b|bankkártyás fizetés|kártyás fizetés',r'stripe'),
 ('rendelkezésre állás (SLA)',r'\b99[.,]9+\s*%|\bSLA\b|\buptime\b',None),
)

INSTANT=re.compile(r'azonnal|\b\d+\s*perc alatt|beírod|ellenőrizd\b|próbáld ki|kattints,? és|instantly|in \d+ minutes|try it now',re.I)
DEAD_SCRIPT=re.compile(r'fetch\s*\(|XMLHttpRequest|axios\.',re.I)
DEV_TEXT=re.compile(r'\bORBIT\b|POST /\w|GET /\w|localhost|127\.0\.0\.1|--self-test|ORBIT_OFFLINE',re.I)
# A finished product page sells now. TermékA's page (1 Nov) asked visitors to join a waitlist "until it starts";
# the owner wants the product ready, not announced.
WAITLIST_TEXT=re.compile(r'várólist|hamarosan|feliratkoz(?:ás|om|hat|z)|értesítünk|korai hozzáférés|amint elindul|elérhető lesz|early access|waitlist|coming soon|join the list|notify me',re.I)
NOT_YET=re.compile(r'még nem|nem működik|nem elérhető|még nincs|nincs még|hamarosan|később|következő mérföldk|tervezet|tervezett|coming soon|not yet|not available',re.I)

def page_text(html):
 html=re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>',' ',html)
 import html as h
 return re.sub(r'\s+',' ',h.unescape(re.sub(r'<[^>]+>',' ',html)))

def promises(folder):
 """{ok, pages:{name:[unkept promises]}} for the product's HTML pages, or None without pages."""
 folder=Path(folder);pages=sorted(folder.glob('*.html'))
 if not pages and not (folder/'traffic-kit.json').is_file():return None
 code=' '.join(p.read_text(errors='replace') for p in folder.glob('*.py') if p.name!='orbit_server_base.py').casefold()
 out={}
 for page in pages:
  html=page.read_text(errors='replace');text=page_text(html)
  sentences=re.split(r'(?<=[.!?])\s+',text)
  bad=[]
  # The launched page is static: ORBIT strips the page's scripts and no API runs behind it. TermékA's
  # "Ellenőrzés" button and its own waitlist form called /check with fetch and would do nothing live.
  scripts=' '.join(re.findall(r'(?is)<script\b[^>]*>(.*?)</script>',html))
  if DEAD_SCRIPT.search(scripts) and re.search(r'<form\b|<button\b',html,re.I):
   bad.append('nem működő űrlap: az élesített oldal statikus (az ORBIT kiveszi a szkripteket, és nincs mögötte API), így az űrlap és a gomb nem fog működni; a vásárlás legyen <a data-orbit-checkout> link, a bemutató statikus minta')
  wait=WAITLIST_TEXT.search(text)
  if wait:bad.append('várólistás vagy „hamarosan” szöveg a kész termék oldalán („…'+text[max(0,wait.start()-50):wait.end()+50].strip()+'…”): az oldal a kész terméket adja el most, kijelentő módban, Megveszem gombbal (<a data-orbit-checkout>)')
  dev=DEV_TEXT.search(text)
  if dev:bad.append('fejlesztői szöveg a vevőknek szóló oldalon („…'+text[max(0,dev.start()-50):dev.end()+50].strip()+'…”)')
  for name,claim,marker in CLAIMS:
   # A sentence that says the feature does not exist yet is honest, not a promise: TermékA's FAQ said
   # card payment "most még nem működik" and the check kept failing the page for three cycles.
   said=next((x for x in sentences if re.search(claim,x,re.I) and not NOT_YET.search(x)),None)
   if said and (marker is None or not re.search(marker,code,re.I)):
    bad.append('az oldal ígéri: '+name+(', de a termék ezt nem méri' if marker is None else ', de a kódban nincs nyoma')+' („'+said.strip()[:140]+'”)')
  if bad:out[page.name]=bad
 # The ads must not promise what the launched page cannot do: TermékA's five channels said "type your
 # shop's address and see the result at once" while the launched page only takes waitlist sign-ups.
 kit=folder/'traffic-kit.json'
 if kit.is_file():
  try:channels=json.loads(kit.read_text()).get('channels') or []
  except (ValueError,AttributeError):channels=[]
  instant=[(c.get('name') or '?',m.group(0)) for c in channels if isinstance(c,dict) for m in [INSTANT.search(str(c.get('copy') or ''))] if m]
  if instant:out['traffic-kit.json']=['a hirdetés azonnali, kipróbálható eredményt ígér, de az élesített oldal statikus (szkriptek nélkül), azonnal kipróbálható eszköz nincs rajta: '+'; '.join(n+' („'+w+'”)' for n,w in instant[:5])+' – ígérje azt, amit a megvásárolt termék ad']
 return dict(ok=not out,pages=out)

def summary(check):
 """One Hungarian line for the milestone summary, with the first error for the builder."""
 if not check or check.get('ok') is None:return (check or {}).get('note','')
 good=sum(r['ok'] for r in check['results']);line='ORBIT futtatás: '+str(good)+'/'+str(len(check['results']))+' fájl hibátlanul lefutott.'
 bad=[r for r in check['results'] if not r['ok']]
 if bad:line+=' Hibás: '+'; '.join(r['file']+' → '+problem(r)[:300] for r in bad[:3])
 live=check.get('smoke')
 if live:
  done=[r for r in live['results'] if r['ok']];times=[r['ms'] for r in live['results'] if r.get('ms') is not None]
  line+=' Élő próba: '+(live['note'] if live.get('note') else str(len(done))+'/'+str(len(live['results']))+' kérés sikeres'+(', átlag '+str(round(sum(times)/len(times)))+' ms' if times else ''))+'.'
  failed=[r for r in live['results'] if not r['ok']]
  if failed:line+=' Hibás kérés: '+'; '.join(r['request']+' → '+str(r['status'])+' '+r['error'][:150] for r in failed[:3])
 # An owner's acceptance test on real data reports "Valós minta: X/Y" (TermékA realcheck.py); it is the
 # one measure here that is not the product's own example data.
 real=next((m.group(0) for r in check['results'] for m in [re.search(r'Valós minta: \d+/\d+',r.get('output') or '')] if m),None)
 if real:line+=' '+real+'.'
 kept=check.get('promises')
 if kept and not kept['ok']:line+=' Ígéret-ellenőrzés: '+'; '.join(n+': '+', '.join(v) for n,v in kept['pages'].items())+'.'
 return line
