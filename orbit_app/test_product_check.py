import json,sys,tempfile,unittest
from pathlib import Path
import product_check
SERVER='''import json,os,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def reply(self,code,data):
  b=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b)
 def do_GET(self):self.reply(200,{'ok':True}) if self.path=='/health' else self.reply(404,{'error':'nincs'})
 def do_POST(self):
  if self.headers.get('X-API-Key')!=os.environ.get('ORBIT_TEST_API_KEY'):return self.reply(401,{'error':'kulcs'})
  x=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.reply(200,{'total':sum(x['items'])})
if '--self-test' in sys.argv:print('ok');sys.exit(0)
HTTPServer(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])),H).serve_forever()
'''
class ErrorLineTests(unittest.TestCase):
 def test_the_line_that_names_the_error_is_chosen(self):
  # A JSON report used to leave just "}" as the error given to the builder.
  self.assertEqual(product_check.error_line('{\n "results": [\n  {"file": "a.py", "error": "ValueError: rossz"}\n ]\n}\n'),'a.py: ValueError: rossz')
  self.assertEqual(product_check.error_line('Traceback (most recent call last):\n  File "/p/ocr.py", line 210, in <module>\n  File "/p/ocr.py", line 172, in self_test\n    assert r["afa"], f"afa: {r[\'afa\']}"\nAssertionError: afa: None\n'),'ocr.py:172 (in self_test) → AssertionError: afa: None')
  self.assertEqual(product_check.error_line('ok rendben\n}\n'),'ok rendben')
  self.assertEqual(product_check.error_line('valid-input: status=None FAIL\n  local: OK\n  health: FAIL\nPipeline self-test: FAIL\n'),'valid-input: status=None FAIL; health: FAIL → Pipeline self-test: FAIL')
  # Cycle 166: the builder was given only "OCR SELF-TEST FAIL (2 hiba)".
  self.assertEqual(product_check.error_line('brutto: expected 63500.0, got None\ntext_brutto: expected 1270.0, got None\nOCR SELF-TEST FAIL (2 hiba)\n'),'brutto: expected 63500.0, got None; text_brutto: expected 1270.0, got None → OCR SELF-TEST FAIL (2 hiba)');self.assertEqual(product_check.error_line('',3),'kilépési kód 3')
 def test_a_json_report_gives_its_failed_checks(self):
  # selfimprove.py: the builder got '"stderr": "Traceback…' and never saw the report's own smoke.json complaint.
  report=json.dumps(dict(files=9,smoke_json_ok=False,smoke_json_errors=['smoke.json: a tobbeset nem lista'],results=[dict(file='billing.py',self_test='PASS'),
   dict(file='ocr.py',self_test='FAIL',exit_code=1,stderr='Traceback (most recent call last):\n  File "/p/ocr.py", line 174, in self_test\n    assert r1["brutto"] == 63500.0\nAssertionError: brutto: None\n')]),indent=2)
  line=product_check.error_line('Futtatás…\n'+report)
  self.assertEqual(line,'smoke.json: a tobbeset nem lista; ocr.py: self_test FAIL – ocr.py:174 (in self_test) → AssertionError: brutto: None')
  self.assertEqual(product_check.error_line('{"ok": true}\nTraceback (most recent call last):\n  File "/p/a.py", line 3, in <module>\nValueError: rossz\n'),'a.py:3 (in <module>) → ValueError: rossz','not a report: the usual line')
 def test_the_error_comes_from_the_whole_output_not_the_kept_tail(self):
  import tempfile,sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  with tempfile.TemporaryDirectory() as d:
   Path(d,'report.py').write_text('import json,sys\nprint(json.dumps(dict(smoke_errors=["smoke.json: rossz"],results=[dict(file="x.py",self_test="PASS",note="n"*80) for _ in range(40)]),indent=2));sys.exit(1)\n')
   r=product_check.run(d)['results'][0]
   self.assertFalse(r['ok']);self.assertLessEqual(len(r['output']),1500);self.assertEqual(product_check.problem(r),'smoke.json: rossz')
class CleanRunTests(unittest.TestCase):
 def test_every_run_starts_clean_and_leaves_the_product_untouched(self):
  # TermékA's runner.py cached into the product folder; the next self-test found the old job cached and failed.
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  with tempfile.TemporaryDirectory() as d:
   Path(d,'a.py').write_text("import os,sys\nos.makedirs('state',exist_ok=True)\nif os.path.exists('state/job.json'):sys.exit('first not cached: expected False, got True')\nopen('state/job.json','w').write('{}')\nprint('ok')\n")
   for _ in range(2):self.assertTrue(product_check.run(d)['results'][0]['ok'])
   self.assertFalse(Path(d,'state').exists(),'the product folder is left as it was')
class LaunchPageTests(unittest.TestCase):
 def test_a_sales_page_works_as_launched_and_speaks_to_customers(self):
  # TermékA's page: a check form calling /check with fetch (dead once launched) and "Offline (ORBIT) mode ... POST /check".
  with tempfile.TemporaryDirectory() as d:
   Path(d,'radar.py').write_text('x=1\n')
   Path(d,'index.html').write_text('<h1>TermékA</h1><form><input type="url"><button>Ellenőrzés</button></form><p>Offline (ORBIT) módban csak a mentett minták ellenőrizhetők. Az API: POST /check.</p><script>fetch("/check")</script>')
   bad=product_check.promises(d)['pages']['index.html']
   self.assertTrue(bad[0].startswith('nem működő űrlap: az élesített oldal statikus'));self.assertIn('fejlesztői szöveg a vevőknek szóló oldalon („…',bad[1]);self.assertIn('Offline (ORBIT) módban',bad[1])
   Path(d,'index.html').write_text('<h1>TermékA</h1><p>A jelentés 10 tételt ellenőriz, jogszabályi hivatkozással.</p><a data-orbit-checkout href="#">Megveszem</a>')
   self.assertEqual(product_check.promises(d),dict(ok=True,pages={}),'a static page with a buy link is fine')
   # The owner wants the finished product on sale, not announced (1 Nov): waitlist and "coming soon" copy is sent back.
   Path(d,'index.html').write_text('<h1>TermékA</h1><p>Hamarosan indul – iratkozz fel a várólistára.</p><button>Feliratkozom</button>')
   self.assertIn('várólistás vagy „hamarosan” szöveg a kész termék oldalán',product_check.promises(d)['pages']['index.html'][0])
class TrafficKitTests(unittest.TestCase):
 def test_ads_promise_only_what_the_launched_page_does(self):
  # TermékA's ads: "Beírod a boltod címét, és azonnal látod" while the launched page only takes sign-ups.
  with tempfile.TemporaryDirectory() as d:
   Path(d,'radar.py').write_text('x=1\n')
   kit=lambda *copies:Path(d,'traffic-kit.json').write_text(json.dumps(dict(channels=[dict(name='Csatorna '+str(i),copy=c) for i,c in enumerate(copies)])))
   kit('Beírod a boltod címét, és azonnal látod a hiányzókat.','Iratkozz fel: e-mailben küldjük a boltod jelentését.')
   r=product_check.promises(d)
   self.assertFalse(r['ok']);self.assertIn('Csatorna 0 („Beírod”)',r['pages']['traffic-kit.json'][0]);self.assertNotIn('Csatorna 1',r['pages']['traffic-kit.json'][0])
   kit('A megvásárolt jelentést e-mailben küldjük a boltod címére.')
   self.assertEqual(product_check.promises(d),dict(ok=True,pages={}),'an honest kit passes')
class OfflineTests(unittest.TestCase):
 def test_product_code_is_told_it_runs_offline(self):
  # TermékA's API fetched real pages in the sandbox and failed with 'urlopen error'.
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  with tempfile.TemporaryDirectory() as d:
   Path(d,'a.py').write_text("import os,sys\nprint('offline='+os.environ.get('ORBIT_OFFLINE','?'))\n")
   r=product_check.run(d)['results'][0]
   self.assertTrue(r['ok']);self.assertIn('offline=1',r['output'])
class PromiseTests(unittest.TestCase):
 def test_a_page_may_promise_only_what_the_code_does(self):
  # TermékB's page promised Tesseract/PaddleOCR OCR and its code had none, yet it counted as ready.
  with tempfile.TemporaryDirectory() as d:
   self.assertIsNone(product_check.promises(d),'no page, nothing to compare')
   Path(d,'index.html').write_text('<h1>Számla API</h1><p>Helyi OCR (Tesseract hu), webhook-visszahívás, 99,9% rendelkezésre állás.</p><script>var ai="AI"</script>')
   Path(d,'engine.py').write_text('import re\ndef run(x):return x\n')
   r=product_check.promises(d)
   said=' („Számla API Helyi OCR (Tesseract hu), webhook-visszahívás, 99,9% rendelkezésre állás.”)'
   self.assertEqual(r,dict(ok=False,pages={'index.html':['az oldal ígéri: Tesseract OCR, de a kódban nincs nyoma'+said,'az oldal ígéri: OCR (szövegfelismerés képről), de a kódban nincs nyoma'+said,'az oldal ígéri: webhook, de a kódban nincs nyoma'+said,'az oldal ígéri: rendelkezésre állás (SLA), de a termék ezt nem méri'+said]}))
   Path(d,'engine.py').write_text('import pytesseract\ndef image_to_string(x):return pytesseract.image_to_string(x)\ndef send_webhook(u):pass\n')
   self.assertEqual(product_check.promises(d)['pages']['index.html'],['az oldal ígéri: rendelkezésre állás (SLA), de a termék ezt nem méri'+said],'script text and kept promises do not count')
   Path(d,'index.html').write_text('<h1>Számla API</h1><p>PDF-ből olvas, JSON-t ad vissza.</p>')
   self.assertEqual(product_check.promises(d),dict(ok=True,pages={}))
   # TermékA's FAQ: an honest "not yet" is not a promise (three cycles failed on it)
   Path(d,'index.html').write_text('<p>Van már fizetési lehetőség? Még nem. A fizetési csatlakozás (pl. bankkártyás fizetés) a következő mérföldkövek egyike, és most még nem működik.</p>')
   self.assertEqual(product_check.promises(d),dict(ok=True,pages={}))
   Path(d,'index.html').write_text('<p>Nem kell regisztrálni. Fizess kényelmesen bankkártyás fizetéssel.</p>')
   self.assertFalse(product_check.promises(d)['ok'],'a plain "nem" elsewhere does not hide a promise')
class SmokeTests(unittest.TestCase):
 def setUp(self):
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
  (self.p/'server.py').write_text(SERVER);(self.p/'example-input.json').write_text('{"items": [1, 2]}')
 def test_server_answers_its_smoke_requests(self):
  (self.p/'smoke.json').write_text(json.dumps(dict(requests=[dict(method='GET',path='/health'),dict(method='POST',path='/sum',json_file='example-input.json',expect_keys=['total'])])))
  c=product_check.run(self.p);self.assertTrue(c['ok'],c);self.assertEqual(len(c['smoke']['results']),2)
  self.assertIn('Élő próba: 2/2 kérés sikeres',product_check.summary(c))
 def test_interactive_api_returns_actual_response_and_validates_input(self):
  (self.p/'smoke.json').write_text('{"requests": [{"method": "POST", "path": "/sum", "json_file": "example-input.json"}]}')
  cases=product_check.api_examples(self.p)
  post=next(r for r in cases if r['method']=='POST')
  response=product_check.try_api(self.p,post['index'],json.dumps(post['body']))
  self.assertEqual(response['status'],200,response)
  self.assertIsInstance(json.loads(response['body']),dict)
  with self.assertRaisesRegex(ValueError,'érvénytelen JSON'):
   product_check.try_api(self.p,post['index'],'{')
  with self.assertRaises(ValueError):
   product_check.try_api(self.p,999,'{}')
 def test_smoke_honors_unauthenticated_requests(self):
  source=SERVER.replace(" def do_POST(self):"," def do_POST(self):\n  if self.headers.get('X-API-Key') or self.headers.get('Authorization'):\n   raise AssertionError('unexpected authentication')\n  self.send_response(401);self.end_headers();return")
  (self.p/'server.py').write_text(source)
  (self.p/'smoke.json').write_text(json.dumps(dict(requests=[dict(method='POST',path='/sum',no_auth=True,expect=401)])))
  result=product_check.smoke(self.p)
  self.assertTrue(result['ok'],result)
 def test_wrong_answer_fails_the_check_with_a_reason(self):
  (self.p/'smoke.json').write_text(json.dumps(dict(requests=[dict(method='POST',path='/sum',json_file='example-input.json',expect_keys=['netto']),dict(method='GET',path='/nope')])))
  c=product_check.run(self.p);self.assertFalse(c['ok'])
  s=product_check.summary(c);self.assertIn('hiányzó mezők: netto',s);self.assertIn('GET /nope → 404',s)
 def test_server_that_does_not_start_is_reported(self):
  (self.p/'server.py').write_text("import sys\nif '--self-test' in sys.argv:sys.exit(0)\nraise SystemExit('boom')\n")
  (self.p/'smoke.json').write_text('{"requests": [{"path": "/health"}]}')
  c=product_check.run(self.p);self.assertFalse(c['ok']);self.assertIn('nem indult el',c['smoke']['note'])
 def test_server_that_exits_instead_of_serving_is_explained(self):
  # The TermékB server printed "Server started." and quit; "did not start" misled the builder.
  (self.p/'server.py').write_text("import sys\nprint('Server started.')\n")
  (self.p/'smoke.json').write_text('{"requests": [{"path": "/health"}]}')
  c=product_check.run(self.p);self.assertFalse(c['ok']);self.assertIn('azonnal kilépett',c['smoke']['note']);self.assertIn('serve_forever',c['smoke']['note'])
 def test_builder_style_expectations_are_understood(self):
  # The builder wrote "body" and "expect": {"status": "ok"}; the runner crashed on int(dict).
  (self.p/'smoke.json').write_text(json.dumps(dict(requests=[dict(method='GET',path='/health',expect=dict(ok=True)),dict(method='POST',path='/sum',body=dict(items=[1,2]),expect=dict(total=3)),dict(method='POST',path='/sum',body=dict(items=[1]),expect=dict(total=9)),dict(path='/health',expect='nem szám')])))
  c=product_check.run(self.p);r=c['smoke']['results']
  self.assertEqual([x['ok'] for x in r],[True,True,False,False])
  self.assertIn('total (várt 9, kapott 1)',r[2]['error']);self.assertIn('HTTP-státusz (szám) vagy az elvárt válaszmezők',r[3]['error'])
if __name__=='__main__':unittest.main()
