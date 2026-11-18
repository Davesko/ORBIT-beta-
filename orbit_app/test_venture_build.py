import json,tempfile,unittest,unittest.mock
from pathlib import Path
from studio import Studio
import venture,venture_build
class VentureBuildTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  self.mid=venture.configure(self.s,dict(enabled=True))['id']
  # Every saved idea passes the critic unless a test checks scoring itself.
  from unittest.mock import patch
  self.scores=patch('venture.idea_scores',side_effect=lambda s,mid:{i['idea_id']:dict(demand=4,competition=3,margin=4,automation=5,speed=4,total=20) for i in venture.known_ideas(s,venture.PID)})
  self.scores.start();self.addCleanup(self.scores.stop)
 def plan(self,**kw):return dict(dict(name='AI táplálkozási terv',problem='Nincs idő étrendet tervezni',buyer='Dolgozó felnőttek',offer='4 hetes személyre szabott terv',revenue_model='Havi díj (nem igazolt)',costs='Idő',hypothesis='Fizetnek érte',validation='10 előfizető',progress='Terv',next_action='Építés',decision='continue',evidence=[],automation_level=95,human_steps=[],files=[dict(name='README.md',content='terv')]),**kw)
 def milestone(self,**kw):return dict(dict(milestone_id='landing',summary='Kész értékesítő oldal valódi szöveggel.',files=[dict(name='workspace/x/index.html',content='<!doctype html><title>Terv</title><h1>Étrend</h1>')],acceptance=['mobilon olvasható'],status='done',owner_actions=[dict(title='Domain megvásárlása',why='Közzétételhez',draft='1. Válassz nevet')]),**kw)
 def test_no_idea_means_explore_then_best_idea_is_implemented(self):
  self.assertIsNone(venture_build.active(self.s));self.assertEqual(venture.prompt_for(self.s,'build','x'),venture.BUILD)
  venture.save_result(self.s,venture.PID,'r1',self.plan())
  f=venture_build.active(self.s);self.assertEqual(f['name'],'AI táplálkozási terv')
  self.assertEqual(venture.prompt_for(self.s,'build','x'),venture_build.BUILD)
  c=venture.context(self.s,dict(id=self.mid,goal='g'),venture.PID);self.assertEqual(c['mode'],'implementation');self.assertEqual(len(c['roadmap']),10)
  self.assertEqual(c['focus']['plan']['offer'],'4 hetes személyre szabott terv')
 def test_milestone_files_go_to_the_product_folder_and_actions_wait_for_owner(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  r=venture.save_result(self.s,venture.PID,'r2',self.milestone())
  self.assertEqual(r['milestone_id'],'landing');p=Path(r['files'][0]);self.assertEqual(p.name,'index.html');self.assertIn('product-',str(p.parent))
  self.assertEqual(r['owner_actions'][0]['title'],'Domain megvásárlása')
  # without a mission run there is no open milestone to fall back to
  with self.assertRaises(ValueError):venture.save_result(self.s,venture.PID,'r3',self.milestone(milestone_id='nope'))
  with self.assertRaises(ValueError):venture.save_result(self.s,venture.PID,'r3',self.milestone(files=[dict(name='x.exe',content='echo hello world here')]))
  # a plan answer during implementation is still saved as a plan, not mistaken for a milestone
  self.assertIn('idea_id',venture.save_result(self.s,venture.PID,'r4',self.plan()))
 def test_progress_follows_build_and_tester_verdict(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  import missions,time
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('run1',self.mid,1,m['spec'],'done',time.time(),time.time()))
  content=venture_build.save(self.s,'run1',self.milestone())
  for node,result in (('build',dict(content=content)),('review',dict(content='VERDICT: revise\nA gomb nem működik.'))):
   self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",('run1',node,'done',json.dumps(result)))
  self.s.db.commit()
  ms,actions=venture_build.progress(self.s,self.mid,f);landing=next(x for x in ms if x['id']=='landing')
  self.assertEqual(landing['state'],'revise');self.assertEqual(actions[0]['title'],'Domain megvásárlása')
  for n in (2,3):
   rid='run'+str(n);self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',(rid,self.mid,n,m['spec'],'done',time.time(),time.time()))
   for node,result in (('build',dict(content=content)),('review',dict(content='VERDICT: revise'))):self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",(rid,node,'done',json.dumps(result)))
  self.s.db.commit();landing=next(x for x in venture_build.progress(self.s,self.mid,f)[0] if x['id']=='landing')
  self.assertEqual(landing['state'],'done');self.assertIn('Három',landing['note'])
  v=venture.status(self.s);self.assertEqual(v['mode'],'build');self.assertEqual(v['focus']['total'],10);self.assertIn('Étrend',next(x for x in v['focus']['milestones'] if x['id']=='landing')['files'][0]['preview'])
  b=venture.brief(self.s);self.assertEqual(b['building']['owner_actions'],['Domain megvásárlása']);self.assertLess(len(json.dumps(b,ensure_ascii=False)),6000)
 def test_operator_can_switch_back_to_exploring(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());iid=venture_build.active(self.s)['idea_id']
  venture.configure(self.s,dict(focus='explore'));self.assertIsNone(venture_build.active(self.s))
  venture.configure(self.s,dict(focus=iid));self.assertEqual(venture_build.active(self.s)['idea_id'],iid)
  with self.assertRaises(ValueError):venture.configure(self.s,dict(focus='missing'))
 def test_type_roadmaps_backtest_skip_and_auto_advance(self):
  from unittest.mock import patch
  from test_strategy_lab import rows
  import missions,time
  venture.save_result(self.s,venture.PID,'r1',self.plan(name='SOL trend stratégia',business_type='trading',offer='Szabályalapú altcoin stratégia'))
  f=venture_build.active(self.s);self.assertEqual(f['type'],'trading');self.assertEqual(venture_build.roadmap(f)[0][0],'thesis')
  strategy=json.dumps(dict(coin='SOL',interval='1d',rules=dict(type='sma_cross',fast=5,slow=20)))
  with patch('strategy_lab.candles',return_value=rows()):
   r=venture_build.save(self.s,'run-s',dict(milestone_id='strategy',summary='Szabályok rögzítve gépi formában.',files=[dict(name='strategy.json',content=strategy)]))
   self.assertTrue(any(p.endswith('backtest.json') for p in r['files']));self.assertIn('ORBIT backtest',r['summary'])
   p=venture_build.save(self.s,'run-p',dict(milestone_id='paper',summary='Virtuális teszt indul a szabályokkal.',files=[dict(name='paper-review.md',content='Elindítva, figyeljük az eredményt.')]))
   self.assertTrue(venture_build.paper_started(self.s,f))
  with self.assertRaises(ValueError):venture_build.save(self.s,'x',dict(milestone_id='landing',summary='Rossz típusú mérföldkő.',files=[dict(name='a.md',content='xxxxxxxxxxxxxxxxxxxxxxxx')]))
  sk=venture_build.save(self.s,'run-k',dict(milestone_id='risk',summary='Nem releváns ennél az ötletnél.',status='skipped',files=[]))
  self.assertEqual(sk['status'],'skipped')
  # every milestone finished -> next idea is picked automatically
  venture.configure(self.s,dict(focus='explore'));venture.save_result(self.s,venture.PID,'r2',self.plan(name='Kerámia bögre webshop',business_type='dropshipping',offer='Bögre dropshipping'))
  venture.configure(self.s,dict(focus=f['idea_id']))
  m=missions.definition(self.s,venture.PID,self.mid)
  for n,(k,_,_,_) in enumerate(venture_build.roadmap(f)):
   rid='auto'+str(n);self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',(rid,self.mid,n+1,m['spec'],'done',time.time(),time.time()))
   c=dict(mode='build',idea_id=f['idea_id'],milestone_id=k,status='done',files=[],summary='kész')
   self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",(rid,'build','done',json.dumps(dict(content=c))))
  self.s.db.commit()
  nxt=venture_build.active(self.s);self.assertNotEqual(nxt['idea_id'],f['idea_id']);self.assertEqual(nxt['type'],'dropshipping');self.assertIn(f['idea_id'],nxt['finished'])
 def test_every_fifth_cycle_scouts_and_ready_ideas_are_queued(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());venture_build.active(self.s)
  self.assertEqual(venture.prompt_for(self.s,'build','x',4),venture_build.BUILD);self.assertEqual(venture.prompt_for(self.s,'build','x',6),venture.BUILD)
  venture.configure(self.s,dict(focus='explore'));self.assertEqual(venture.prompt_for(self.s,'review','x',4),venture_build.TEST,'a cycle keeps the mode it started with')
  c=venture.context(self.s,dict(id=self.mid,goal='g'),venture.PID,6);self.assertNotIn('roadmap',c);self.assertEqual(c['scouting']['sector'],venture_build.sector(6)[0])
  self.assertNotEqual(venture_build.sector(6),venture_build.sector(9))
  r=venture.save_result(self.s,venture.PID,'r9',self.plan(name='Kripto backtest szolgáltatás XYZ',decision='ready_for_validation',idea_id='new',offer='Más ajánlat'))
  self.assertIn(r['idea_id'],venture_build.read(self.s)['queue'])
 def test_truncated_milestone_keeps_complete_files(self):
  raw='```json\n{"milestone_id":"landing","summary":"Kész oldal mobilra.","files":[{"name":"index.html","content":"<!doctype html><h1>Szia \\"ORBIT\\"</h1>"},{"name":"styles.css","content":"body{color:'
  v=venture_build.salvage(raw);self.assertEqual(v['milestone_id'],'landing');self.assertEqual(v['status'],'partial')
  self.assertEqual([f['name'] for f in v['files']],['index.html']);self.assertIn('"ORBIT"',v['files'][0]['content'])
  self.assertIsNone(venture_build.salvage('{"name":"x"}'))
 def test_human_delivery_ideas_are_not_built_automatically(self):
  venture.save_result(self.s,venture.PID,'h1',self.plan(name='Személyes táplálkozási tanácsadás',offer='Manuális heti konzultáció',automation_level=40,human_steps=['heti hívás']))
  self.assertIsNone(venture_build.active(self.s))
  r=venture.save_result(self.s,venture.PID,'a1',self.plan(name='Számla-feldolgozó API',offer='Automatikus PDF-számla kinyerés API-n',business_type='saas',category='API micro-service',architecture=dict(ingestion='webhook',processing='Ollama',delivery='JSON API'),autonomy=dict(qa='séma-ellenőrzés',self_optimization='hibaarány alapján prompt-javítás')))
  self.assertTrue(r['automated']);self.assertIn('ingestion: webhook',r['architecture'])
  f=venture_build.active(self.s);self.assertEqual(f['name'],'Számla-feldolgozó API');self.assertEqual(f['type'],'saas');self.assertEqual(venture_build.roadmap(f)[0][0],'design')
 def test_non_automated_auto_focus_switches_to_scouting(self):
  venture.save_result(self.s,venture.PID,'h1',self.plan(name='Kódellenőrző API',automation_level=95,human_steps=[]))
  f=venture_build.active(self.s);self.assertTrue(f)
  # the same idea later turns out to need people -> the system stops building it and scouts
  venture.save_result(self.s,venture.PID,'h2',self.plan(name='Kódellenőrző API',idea_id=f['idea_id'],automation_level=30,human_steps=['személyes konzultáció']))
  self.assertIsNone(venture_build.active(self.s));self.assertTrue(venture_build.read(self.s)['auto_explore'])
  self.assertTrue(venture.status(self.s)['explore_reason'])
 def test_critic_score_decides_which_idea_is_built(self):
  self.scores.stop()
  import missions,time
  self.assertEqual(venture.parse_score('ok\nSCORE demand=4 competition=3 margin=5 automation=5 speed=2')['total'],19)
  self.assertIsNone(venture.parse_score('SCORE demand=9 competition=3'))
  m=missions.definition(self.s,venture.PID,self.mid)
  def cycle(n,plan,review):
   rid='sc'+str(n);self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',(rid,self.mid,n,m['spec'],'done',time.time(),time.time()))
   saved=venture.save_result(self.s,venture.PID,rid,plan)
   for node,c in (('build',saved),('review',review)):self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",(rid,node,'done',json.dumps(dict(content=c))))
   self.s.db.commit();return saved
  a=cycle(1,self.plan(name='Gyakori de gyenge API',offer='API A'),'SCORE demand=1 competition=2 margin=2 automation=3 speed=2')
  cycle(2,self.plan(name='Gyakori de gyenge API',offer='API A',idea_id=a['idea_id']),'SCORE demand=1 competition=2 margin=2 automation=3 speed=2')
  self.assertIsNone(venture_build.active(self.s),'a weak idea is not built, however often it was revisited')
  b=cycle(3,self.plan(name='Ritka de erős SEO-hálózat',offer='SEO B'),'SCORE demand=2 competition=4 margin=4 automation=5 speed=4')
  self.assertEqual(venture_build.active(self.s)['idea_id'],b['idea_id'],'unproven demand does not block: the launch test measures it')
  self.assertEqual(next(i for i in venture.status(self.s)['ideas'] if i['idea_id']==b['idea_id'])['score']['total'],19)
 def test_a_score_says_what_it_means(self):
  # Five ideas got the same 1-2-2-4-3 without evidence; the assistant called that 12 (of 25) high, with broad demand.
  note=venture.score_note(dict(venture.parse_score('SCORE demand=1 competition=2 margin=2 automation=4 speed=3')))
  self.assertEqual(note,'12/25, a kritikus becslése, nem piaci adat; nincs igazolt kereslet (kereslet 1/5); erős verseny (verseny 2/5); nem értékelte, megoldja-e már ingyenes vagy hivatalos eszköz')
  self.assertEqual(venture.score_note(dict(demand=5,competition=4,margin=3,automation=4,speed=4,solved=1,total=20,measured='passed')),'20/25, a kereslet valódi oldalteszten mérve')
  self.assertIn('valószínűleg már létezik ingyenes vagy hivatalos megoldás',venture.score_note(dict(demand=3,competition=3,margin=3,automation=4,speed=3,solved=5,total=16)))
 def test_prose_mentioning_score_does_not_hide_the_score_line(self):
  text='A self-improvement score, külső visszacsatolás nincs.\nSCORE demand=1 competition=2 margin=2 automation=3 speed=2'
  self.assertEqual(venture.parse_score(text)['total'],10)
  self.assertEqual(venture.parse_score('SCORE demand=2 competition=2 margin=2 automation=4 speed=2\nszöveg…')['automation'],4,'a truncated review keeps the leading line')
 def test_already_solved_problem_is_not_built(self):
  sc=venture.parse_score('SCORE demand=4 competition=4 margin=4 automation=5 speed=4 solved=5')
  self.assertEqual(sc['total'],21);self.assertEqual(sc['solved'],5)
  self.assertFalse(venture_build.buildable(sc));self.assertTrue(venture_build.buildable(dict(sc,solved=2)))
  self.assertTrue(venture_build.buildable(venture.parse_score('SCORE demand=4 competition=4 margin=4 automation=5 speed=4')),'older scores without the field still count')
 def test_recurring_failures_become_advice_for_next_cycles(self):
  import missions,time
  for err in ('EOF while scanning triple-quoted string literal (<unknown>, line 8)','unexpected EOF while parsing','Legfeljebb 4 konkrét eredményfájl adható meg.','A szöveg üres vagy túl hosszú.'):
   missions.log(self.s,self.mid,'r',None,'retry_scheduled',dict(error=err))
  self.s.db.commit();p=venture.pitfalls(self.s,self.mid)
  self.assertEqual(p[0]['times'],2);self.assertIn('unclosed string',p[0]['advice']);self.assertEqual(len(p),2,'infrastructure errors are not the model\'s to avoid')
  venture.save_result(self.s,venture.PID,'r1',self.plan())
  self.assertEqual(venture.context(self.s,dict(id=self.mid,goal='g'),venture.PID)['avoid_recent_failures'],p)
 def test_owner_setup_is_not_human_work(self):
  ok=self.plan(human_steps=['Az owner egyszeri beállítása: Stripe fiók, domain, API key'])
  self.assertTrue(venture.automated(ok))
  self.assertFalse(venture.automated(self.plan(human_steps=['Minden ügyfél fiókját kézi ellenőrzés után aktiváljuk'])))
  self.assertFalse(venture.automated(self.plan(human_steps=['Heti konzultáció az ügyféllel'])))
  self.assertTrue(venture.automated(self.plan(offer='REST API, pay-per-call, webhook-visszahívás',revenue_model='5 Ft/hívás',problem='A könyvelők kézi adatrögzítéssel töltik a napot')))
  self.assertFalse(venture.automated(self.plan(offer='Telefonos ügyfélkezelés AI-jal')))
 def test_best_of_several_mediocre_ideas_is_built_instead_of_scouting_forever(self):
  self.scores.stop()
  import missions,time
  m=missions.definition(self.s,venture.PID,self.mid)
  def cycle(n,plan,review):
   rid='mc'+str(n);self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',(rid,self.mid,n,m['spec'],'done',time.time(),time.time()))
   saved=venture.save_result(self.s,venture.PID,rid,plan)
   for node,c in (('build',saved),('review',review)):self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",(rid,node,'done',json.dumps(dict(content=c))))
   self.s.db.commit();return saved
  cycle(1,self.plan(name='Számlakövető API',offer='Késedelmes számlák követése API-n'),'SCORE demand=1 competition=2 margin=3 automation=4 speed=2')
  best=cycle(2,self.plan(name='Árfigyelő szolgáltatás',offer='Webshop árváltozás riasztás e-mailben'),'SCORE demand=2 competition=3 margin=3 automation=4 speed=2')
  self.assertIsNone(venture_build.active(self.s),'two mediocre ideas are not enough to compare')
  cycle(3,self.plan(name='Promptfigyelő pipeline',offer='LLM kimenetek regressziós tesztje'),'SCORE demand=1 competition=2 margin=2 automation=2 speed=2')
  self.assertEqual(venture_build.active(self.s)['idea_id'],best['idea_id'])
 def built(self,n,value,review='VERDICT: accept'):
  """Save a milestone through a real mission run, as the worker does."""
  import missions,time
  m=missions.definition(self.s,venture.PID,self.mid);rid='b'+str(n)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',(rid,self.mid,n,m['spec'],'done',time.time(),time.time()))
  content=venture_build.save(self.s,rid,value)
  for node,result in (('build',dict(content=content)),('review',dict(content=review))):
   self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",(rid,node,'done',json.dumps(result)))
  self.s.db.commit();return content
 def state(self,f,mid):return next(m for m in venture_build.progress(self.s,self.mid,f)[0] if m['id']==mid)['state']
 def test_product_code_is_really_run_and_failures_go_back(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys,json\ndef run(x):return {'total':sum(x)}\nif __name__=='__main__' and '--self-test' in sys.argv:\n assert run([1,2])=={'total':3};print('ok')\n"
  r=self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=ok),dict(name='example-input.json',content='{"items": [1, 2, 3]}')],owner_actions=[]))
  self.assertTrue(r['checks']['ok']);self.assertIn('1/1 fájl hibátlanul',r['summary']);self.assertEqual(self.state(f,'engine'),'done')
  bad="import sys,urllib.request\nimport engine\nif '--self-test' in sys.argv:urllib.request.urlopen('https://example.com',timeout=5)\n"
  r=self.built(2,self.milestone(milestone_id='api',files=[dict(name='server.py',content=bad)],owner_actions=[]))
  self.assertFalse(r['checks']['ok'],'no network inside the sandbox');self.assertEqual(r['checks']['failed'],['server.py'])
  self.assertEqual(self.state(f,'api'),'revise','a failed run reopens the milestone even when the tester accepted it')
  srv="import http.server,threading,urllib.request,sys\nif '--self-test' in sys.argv:\n h=http.server.HTTPServer(('127.0.0.1',0),http.server.SimpleHTTPRequestHandler);threading.Thread(target=h.serve_forever,daemon=True).start()\n assert urllib.request.urlopen('http://127.0.0.1:%d/'%h.server_port,timeout=5).status==200;h.shutdown()\n"
  r=self.built(3,self.milestone(milestone_id='api',files=[dict(name='server.py',content=srv)],owner_actions=[]))
  self.assertTrue(r['checks']['ok'],r['summary']);self.assertEqual(self.state(f,'api'),'done','a server may test itself on localhost')
  r=self.built(4,self.milestone(milestone_id='pipeline',files=[dict(name='runner.py',content="print('unterminated)\n")],owner_actions=[]))
  self.assertIn('runner.py',r['checks']['failed']);self.assertIn('SyntaxError',r['summary'],'the builder gets the error instead of losing the cycle')
 def test_a_broken_file_reopens_only_the_milestone_that_wrote_it(self):
  # One old failing file used to mark every later milestone "javítandó".
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="import sys\nassert len([1])==5, 'Kérdések száma: 1'\n")],owner_actions=[]))
  r=self.built(2,self.milestone(milestone_id='api',files=[dict(name='server.py',content=ok)],owner_actions=[]))
  self.assertEqual(r['checks']['failed'],['validate.py']);self.assertIn('Kérdések száma',r['checks']['errors']['validate.py'])
  ms={m['id']:m for m in venture_build.progress(self.s,self.mid,f)[0]}
  self.assertEqual(ms['api']['state'],'done','its own server.py runs');self.assertEqual(ms['engine']['state'],'revise')
  self.assertIn('Kérdések száma',ms['engine']['code_errors']['validate.py'])
  self.s.db.execute('UPDATE orbit_mission_steps SET updated=?',(__import__('time').time(),));self.s.db.commit()
  ran={m['title']:m['ran'] for m in venture_build.recent_builds(self.s,self.mid,0)}
  self.assertIs(ran[ms['api']['title']],True,'the morning report does not blame the API build for validate.py')
  row=next(x for x in venture_build.compact_roadmap(f,list(ms.values())) if x['id']=='engine')
  self.assertIn('validate.py',row['code_errors'],'the builder is told exactly what to fix')
  self.built(3,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content=ok)],owner_actions=[]))
  self.assertEqual(self.state(f,'engine'),'done')
 def test_product_health_shows_the_newest_code_run(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.assertIsNone(venture_build.product_health(self.s,self.mid,f))
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=ok)],owner_actions=[]))
  self.built(2,self.milestone(milestone_id='api',files=[dict(name='server.py',content="raise SystemExit(3)\n")],owner_actions=[]))
  h=venture_build.product_health(self.s,self.mid,f)
  # engine.py, the broken server.py and ORBIT's server base that came with it
  self.assertEqual((h['ok'],h['files_ok'],h['files'],h['failed']),(False,2,3,['server.py']))
 def test_a_working_file_is_never_replaced_by_a_broken_one(self):
  # A later build once broke a server.py that had run cleanly; the product went backwards.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok v1')\n"
  self.built(1,self.milestone(milestone_id='api',files=[dict(name='server.py',content=ok)],owner_actions=[]))
  r=self.built(2,self.milestone(milestone_id='api',files=[dict(name='server.py',content="raise SystemExit('broken v2')\n")],owner_actions=[]))
  product=self.s.safe_path(venture.PID,venture_build.folder(f))
  self.assertEqual((product/'server.py').read_text(),ok,'the working version is back')
  self.assertEqual(r['regressions'],['server.py']);self.assertTrue(r['checks']['ok']);self.assertIn('Regresszió megakadályozva',r['summary'])
  self.assertIn('broken v2',(venture_build._path(self.s,'b2')/'server.py').read_text(),'the broken attempt stays in the cycle folder')
  # A file that was already failing may be replaced by another attempt.
  self.built(3,self.milestone(milestone_id='pipeline',files=[dict(name='runner.py',content="raise SystemExit(1)\n")],owner_actions=[]))
  r=self.built(4,self.milestone(milestone_id='pipeline',files=[dict(name='runner.py',content="raise SystemExit(2)\n")],owner_actions=[]))
  self.assertEqual(r['regressions'],[]);self.assertIn('SystemExit(2)',(product/'runner.py').read_text())
 def test_builder_can_patch_existing_files_with_exact_blocks(self):
  # Writing whole files out again took most of a 27B build; small fixes now go as find/replace.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  v1="import sys\nPRICE=100\nNAME='a'\nif __name__=='__main__' and '--self-test' in sys.argv:assert PRICE>0;print('ok')\n"
  self.built(1,self.milestone(milestone_id='api',files=[dict(name='server.py',content=v1),dict(name='notes.md',content='# Jegyzet\nNAME a NAME a NAME\n')],owner_actions=[]))
  product=self.s.safe_path(venture.PID,venture_build.folder(f))
  edits=[dict(name='server.py',find='PRICE=100',replace='PRICE=120'),dict(name='notes.md',find='NAME a',replace='x')]
  r=self.built(2,self.milestone(milestone_id='api',files=[],edits=edits,owner_actions=[]))
  self.assertIn('PRICE=120',(product/'server.py').read_text());self.assertIn("NAME='a'",(product/'server.py').read_text(),'the rest is untouched')
  self.assertEqual((product/'notes.md').read_text(),'# Jegyzet\nNAME a NAME a NAME\n','an ambiguous block changes nothing')
  self.assertIn('Csere-blokkokkal javítva: server.py',r['summary']);self.assertIn('több helyen szerepel (2 találat)',r['summary']);self.assertTrue(r['checks']['ok'])
  with self.assertRaisesRegex(ValueError,'Egyik csere-blokk sem illeszkedett'):
   self.built(3,self.milestone(milestone_id='api',files=[],edits=[dict(name='server.py',find='NOT THERE',replace='x')],owner_actions=[]))
 def test_edit_blocks_are_validated(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'a.py').write_text('x=1\n')
   with self.assertRaises(ValueError):venture_build.apply_edits(Path(d),[dict(name='../a.py',find='x',replace='y')])
   self.assertEqual(venture_build.apply_edits(Path(d),[dict(name='a.py',find='x=1',replace='x=2')],skip={'a.py'}),({},[]),'a full file wins over edits')
   self.assertEqual(venture_build.apply_edits(Path(d),[dict(name='b.py',find='x',replace='y')])[1],['b.py (nincs ilyen fájl)'])
   with self.assertRaises(ValueError):venture_build.apply_edits(Path(d),[dict(path='/etc/a.py',find='x',replace='y')])
 def test_a_build_that_names_files_with_path_is_saved(self):
  # Cycle 163: a correct 26-minute build wrote {"path": "ocr.py", ...} and was rejected whole.
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'a.py').write_text('x=1\ny=2\n')
   out,bad=venture_build.apply_edits(Path(d),[dict(path='a.py',find='x=1',replace='x=3'),dict(file='a.py',find='y=2',replace='y=4'),dict(path='a.py',find='z')])
   self.assertEqual(out,{'a.py':'x=3\ny=4\n'});self.assertEqual(bad,['3. csere-blokk (hiányzik a name, find vagy replace mező)'])
  text='{"milestone_id":"engine","edits":[{"path":"ocr.py","find":"a\\\\s*b","replace":"a[\\\\s:]*b"}],"files":[{"file":"x.md","content":"# X"}],"summary":"Javítva'
  got=venture_build.salvage(text)
  self.assertEqual(got['edits'],[dict(name='ocr.py',find='a\\s*b',replace='a[\\s:]*b')]);self.assertEqual(got['files'],[dict(name='x.md',content='# X')])
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.built(1,self.milestone(milestone_id='landing',files=[dict(path='index.html',content='<!doctype html><title>Teszt</title><h1>Számlakivonat</h1><p>Kész.</p>')],owner_actions=[]))
  self.assertTrue((self.s.safe_path(venture.PID,venture_build.folder(f))/'index.html').is_file(),'a "path" key saves the file too')
 def test_recurring_code_errors_reach_the_builder_with_advice(self):
  # validate.py failed with the same assertion in twelve builds in a row.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  bad="import sys\nfrom server import Handler\n"
  for n in (1,2):self.built(n,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="assert len([1])==5, 'Kérdések száma: 1'\n"),dict(name='runner.py',content=bad)],owner_actions=[]))
  self.built(3,self.milestone(milestone_id='api',files=[dict(name='other.py',content="raise SystemExit('egyszeri')\n")],owner_actions=[]))
  found={(x['file'],x['error']):x for x in venture_build.recurring_code_errors(self.s,self.mid,f)}
  hit=next(v for (fn,err),v in found.items() if fn=='validate.py' and err.endswith('AssertionError: Kérdések száma: 1'))
  self.assertEqual(hit['builds'],3);self.assertIn('never delete or weaken the test',hit['advice'])
  self.assertTrue(any(k[0]=='runner.py' and 'No module named' in k[1] for k in found),found)
  self.assertFalse(any(k[0]=='other.py' for k in found),'a one-off error is not a pattern yet')
  import venture as v
  self.assertIn('recurring_code_errors',v.context(self.s,dict(id=self.mid,goal='g'),venture.PID))
 def test_api_products_get_the_orbit_server_base(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  server="from orbit_server_base import JSONHandler, main\nclass Handler(JSONHandler):\n REQUIRE_KEY=True\n def get_health(self):return 200,{'ok':True}\n def post_extract(self,data):return 200,{'netto':int(data.get('netto',0)),'üzenet':'Kész'}\ndef checks(call):\n s,b=call('POST','/extract',{'netto':5});assert s==200 and b['netto']==5,b\nif __name__=='__main__':main(Handler,checks)\n"
  smoke='{"requests":[{"path":"/health"},{"method":"POST","path":"/extract","json":{"netto":7},"expect_keys":["netto"]}]}'
  r=self.built(1,self.milestone(milestone_id='api',files=[dict(name='server.py',content=server),dict(name='smoke.json',content=smoke),dict(name='orbit_server_base.py',content="print('a builder rewrite')\n")],owner_actions=[]))
  product=self.s.safe_path(venture.PID,venture_build.folder(f))
  self.assertIn('class JSONHandler',(product/'orbit_server_base.py').read_text(),'the base is restored after the build')
  self.assertTrue(r['checks']['ok'],r['summary']);self.assertIn('Élő próba: 2/2 kérés sikeres',r['summary'])
 def test_the_owners_real_data_test_is_read_only_and_guards_the_engine(self):
  # TermékA: realcheck.py measures radar.py on real webshops. A build must neither rewrite its labels
  # nor keep an engine change that makes it fail; the engine goes back, not the untouched test.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  product=self.s.safe_path(venture.PID,venture_build.folder(f));product.mkdir(parents=True,exist_ok=True)
  engine="LIMIT=5\nimport sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  check="# ORBIT-PROTECTED: a tulajdonos valós mércéje\nimport sys,engine\nif '--self-test' in sys.argv:\n assert engine.LIMIT==5,'LIMIT: várt 5, kapott '+str(engine.LIMIT)\n print('SELF-TEST OK')\n"
  (product/'check.py').write_text(check)
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=engine)],owner_actions=[]))
  r=self.built(2,self.milestone(milestone_id='engine',files=[dict(name='check.py',content="import sys\nprint('mindig jó')\n")],owner_actions=[]))
  self.assertEqual((product/'check.py').read_text(),check,'the protected test is unchanged');self.assertIn('Védett fájl, az ORBIT nem engedte módosítani',r['summary'])
  r=self.built(3,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=engine.replace('LIMIT=5','LIMIT=6'))],owner_actions=[]))
  self.assertEqual((product/'engine.py').read_text(),engine,'the engine change that broke the test went back')
  self.assertTrue(r['checks']['ok']);self.assertEqual(r['regressions'],['engine.py'])
  self.assertIn('check.py korábban hibátlanul futott, ehhez a kör nem nyúlt',r['summary']);self.assertIn('LIMIT: várt 5, kapott 6',r['summary'])
  # a failure this build did not cause leaves the build's work in place
  (product/'check.py').write_text(check.replace("engine.LIMIT==5","engine.LIMIT==7"))
  r=self.built(4,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=engine.replace('print(\'ok\')','print(\'ok v4\')'))],owner_actions=[]))
  self.assertIn('ok v4',(product/'engine.py').read_text());self.assertFalse(r['checks']['ok']);self.assertEqual(r['regressions'],[])
 def test_a_step_the_owner_did_is_not_built_again(self):
  # TermékA: the owner's tested engine existed, the Autopilot saw "engine" open and wrote a second one.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  first=venture_build.next_milestone(venture_build.progress(self.s,self.mid,f)[0])
  r=venture.configure(self.s,dict(milestone_done=dict(idea_id=f['idea_id'],milestone=first,files=['radar.py'],note='Valós adaton mérve.')))
  self.assertEqual(r['owner_done'][first]['files'],['radar.py'])
  ms=venture_build.progress(self.s,self.mid,f)[0];m=next(x for x in ms if x['id']==first)
  self.assertEqual((m['state'],m['by_owner'],m['summary']),('done',True,'A tulajdonos elkészítette. Valós adaton mérve.'))
  self.assertNotEqual(venture_build.next_milestone(ms),first,'the Autopilot moves on')
  with self.assertRaisesRegex(ValueError,'Nem engedélyezett fájl'):
   venture_build.save(self.s,'x',dict(milestone_id='landing',summary='Kész értékesítő oldal.',files=[dict(name='orbit-milestones.json',content='{"landing": {"files": []}}')]))
  # the owner's file breaking later reopens the owner's step
  product=self.s.safe_path(venture.PID,venture_build.folder(f));(product/'radar.py').write_text("raise SystemExit('radar törött')\n")
  self.built(1,self.milestone(milestone_id='landing',owner_actions=[]))
  m=next(x for x in venture_build.progress(self.s,self.mid,f)[0] if x['id']==first)
  self.assertEqual(m['state'],'revise');self.assertIn('radar.py',m['code_errors'])
  (product/'radar.py').rename(product/'radar-regi.txt')
  m=next(x for x in venture_build.progress(self.s,self.mid,f)[0] if x['id']==first)
  self.assertEqual((m['state'],m['code_errors']),('done',{}),'a failing file set aside leaves nothing to fix')
  venture.configure(self.s,dict(milestone_done=dict(idea_id=f['idea_id'],milestone=first,done=False)))
  self.assertNotIn(first,venture_build.owner_done(self.s,f))
  with self.assertRaises(ValueError):venture.configure(self.s,dict(milestone_done=dict(idea_id=f['idea_id'],milestone='nincs')))
 def test_unparseable_file_goes_back_to_its_last_working_version(self):
  # Cycle 148 left server.py with an invalid line; the API could not start for hours.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys\nSTATE='OPEN'\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=ok)],owner_actions=[]))
  product=self.s.safe_path(venture.PID,venture_build.folder(f))
  (product/'engine.py').write_text("self.state = 'HALF_OPEN' = 'HALF_OPEN'\n")  # broken outside a build
  r=self.built(2,self.milestone(milestone_id='api',files=[dict(name='other.py',content=ok)],owner_actions=[]))
  self.assertEqual((product/'engine.py').read_text(),ok);self.assertIn('visszaállította az utolsó hibátlanul futó változatot',r['summary'])
  # A broken rewrite of the now working file in a build is stopped by the regression guard.
  r=self.built(3,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content="import sys\nvalue = = 1  # broken on purpose\n")],owner_actions=[]))
  self.assertEqual((product/'engine.py').read_text(),ok);self.assertIn('Regresszió megakadályozva',r['summary'])
 def test_failed_live_test_reopens_the_api_milestone(self):
  # GET /health answered 501 while every file passed its self-test; the API was still "done".
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  server="from orbit_server_base import JSONHandler, main\nclass Handler(JSONHandler):\n def get_status(self):return 200,{'ok':True}\nif __name__=='__main__':main(Handler)\n"
  r=self.built(1,self.milestone(milestone_id='api',files=[dict(name='server.py',content=server),dict(name='smoke.json',content='{"requests":[{"path":"/health"}]}')],owner_actions=[]))
  self.assertIn('smoke.json',r['checks']['failed']);self.assertIn('GET /health → 404',r['checks']['errors']['smoke.json'])
  ms={m['id']:m for m in venture_build.progress(self.s,self.mid,f)[0]}
  self.assertEqual(ms['api']['state'],'revise');self.assertIn('Élő próba',ms['api']['code_errors']['smoke.json'])
 def test_timeline_and_selected_milestone_wins(self):
  import sys,time
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="raise SystemExit('Kérdések száma: 1')\n")],owner_actions=[]))
  # The builder labels its fix 'billing'; ORBIT had selected the broken engine step.
  import missions
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('b2',self.mid,2,m['spec'],'done',time.time(),time.time()))
  r=venture_build.save(self.s,'b2',self.milestone(milestone_id='billing',files=[dict(name='validate.py',content=ok)],owner_actions=[]),enforce=True)
  self.assertEqual(r['milestone_id'],'engine');self.assertIn('az ORBIT a kijelölt',r['summary'])
  self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",('b2','build','done',json.dumps(dict(content=r))));self.s.db.commit()
  tl=venture_build.timeline(self.s,self.mid,f)
  self.assertEqual([(e['cycle'],e['files_ok'],e['files'],e['ok']) for e in tl],[(1,0,1,False),(2,1,1,True)])
 def test_planner_milestone_wins_over_the_builders_label(self):
  # Cycles 149-151: the planner asked for the API, the builder filed the work as 'billing'.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  for n,brief in ((1,'**milestone_id**: api\n\nDeliverable…'),(2,'**Milestone:** `api` (state: revise)')):
   self.built(n,self.milestone(milestone_id='billing',files=[dict(name='server.py',content=ok)],owner_actions=[]))
   self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",('b'+str(n),'research','done',json.dumps(dict(content=brief))))
  self.s.db.commit()
  ms={m['id']:m for m in venture_build.progress(self.s,self.mid,f)[0]}
  self.assertEqual(ms['billing']['state'],'pending','an unbuilt step is not done')
  self.assertEqual(ms['api']['cycles'],[1,2])
 def test_owner_todos_are_ranked_and_merged(self):
  acts=[dict(title='Webhook végpont publikálása (HTTPS)',kind='publish',cycle=152),dict(title='Élő webhook végpont publikálása (HTTPS)',kind='publish',cycle=151),
   dict(title='Stripe-fiók létrehozása és API-key beállítása',kind='account',cycle=152),dict(title='Stripe-fiók és a STRIPE_WEBHOOK_SECRET / STRIPE_API_KEY beállítása',kind='account',cycle=151),
   dict(title='Stripe Price objectek létrehozása',kind='money',cycle=152),dict(title='Árazás és jogi (ÁFA, szerződés) jóváhagyás',kind='legal',cycle=149),
   dict(title='Landing page publikálása',kind='publish',cycle=120)]
  out=venture_build.rank_owner_actions(acts)
  self.assertEqual([(a['kind'],a['count']) for a in out],[('money',1),('legal',1),('account',2),('publish',2),('publish',1)])
  self.assertEqual(out[3]['title'],'Webhook végpont publikálása (HTTPS)','the newest wording is kept');self.assertEqual(out[3]['variants'],['Élő webhook végpont publikálása (HTTPS)'])
 def test_earlier_projects_stay_listed_and_open_in_full(self):
  # The owner can open any project the Autopilot built files for, not only the current one.
  a=venture.save_result(self.s,venture.PID,'r1',self.plan(name='Számla API',offer='Számla adatkinyerés API-n'))
  self.assertEqual(venture_build.active(self.s)['idea_id'],a['idea_id'])
  self.built(1,self.milestone(owner_actions=[dict(title='Domain megvásárlása',kind='money')]))
  b=venture.save_result(self.s,venture.PID,'r2',self.plan(name='Webshop ellenőrző',offer='Webáruházak automatikus jogi ellenőrzése'))
  venture.configure(self.s,dict(focus=b['idea_id']))
  self.built(2,self.milestone(files=[dict(name='index.html',content='<!doctype html><h1>Radar</h1>')]))
  st=venture.status(self.s)
  self.assertEqual([(p['name'],p['state']) for p in st['projects']],[('Webshop ellenőrző','building'),('Számla API','paused')])
  old=st['projects'][1];self.assertEqual((old['done'],old['total'],old['cycles']),(1,10,1));self.assertEqual(old['state_label'],'Félretéve')
  v=venture.project(self.s,a['idea_id'])
  self.assertFalse(v['current']);self.assertEqual(v['name'],'Számla API');self.assertEqual([c['cycle'] for c in v['cycles']],[1])
  self.assertIn('Étrend',v['previews'][0]['html']);self.assertEqual(v['owner_actions'][-1]['title'],'Domain megvásárlása')
  self.assertTrue(venture.project(self.s,b['idea_id'])['current'])
  with self.assertRaises(ValueError):venture.project(self.s,'missing')
 def test_owner_todos_without_kind_do_not_break_the_page(self):
  # Early builds saved owner steps without a kind; ranking them raised KeyError for the whole project.
  out=venture_build.rank_owner_actions([dict(title='Domain megvásárlása',cycle=2),dict(title='Domain megvásárlása most',cycle=1),dict(title='Stripe-fiók',kind='account',cycle=3)])
  self.assertEqual([(a['title'],a['count']) for a in out],[('Stripe-fiók',1),('Domain megvásárlása',2)])
 def test_builder_cannot_re_add_an_open_todo_in_new_words(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  first=[dict(title='Stripe-fiók létrehozása és API-key beállítása',kind='account')]
  self.built(1,self.milestone(milestone_id='design',owner_actions=first))
  r=self.built(2,self.milestone(milestone_id='landing',owner_actions=[dict(title='Stripe-fiók és STRIPE_API_KEY beállítása',kind='account'),dict(title='Domain megvásárlása',kind='money')]))
  self.assertEqual([a['title'] for a in r['owner_actions']],['Domain megvásárlása'])
 def test_builder_is_pointed_at_the_broken_files(self):
  # The builder kept re-editing selfimprove.py while ocr.py and pipeline.py stayed broken.
  import sys,time,missions
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="raise SystemExit('Kérdések száma: 1')\n")],owner_actions=[]))
  ms=venture_build.progress(self.s,self.mid,f)[0]
  row=next(r for r in venture_build.compact_roadmap(f,ms,focus=venture_build.next_milestone(ms)) if 'goal' in r)
  self.assertEqual(row['fix_first'][0].split('/')[-1],'validate.py');self.assertEqual(row['files'][0],row['fix_first'][0])
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('b2',self.mid,2,m['spec'],'done',time.time(),time.time()))
  r=venture_build.save(self.s,'b2',self.milestone(milestone_id='engine',files=[dict(name='selfimprove.py',content=ok)],owner_actions=[]),enforce=True)
  self.assertIn('nem a hibás fájlokat javította (validate.py)',r['summary'])
 def test_build_task_gets_the_whole_broken_files(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  broken="raise SystemExit('Kérdések száma: 1')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content=broken),dict(name='big.py',content='x=1\n'+'# '+'y'*9000+'\nraise SystemExit(2)\n')],owner_actions=[]))
  files=venture_build.broken_files(self.s,self.mid,1,budget=5000)
  self.assertEqual(files,{'validate.py':broken},'only whole files within the budget')
  self.assertEqual(venture_build.broken_files(self.s,self.mid,1,budget=0),{})
 def test_build_retries_share_everything_but_the_end_of_their_task(self):
  # The model server reuses a prompt only up to its first changed character. The failure counts came first
  # and changed every attempt, so each retry of cycle 208 re-read ~9 500 tokens (~3 min).
  import time,missions
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('c1',self.mid,1,m['spec'],'running',time.time(),time.time()+3600))
  for node,state,result in (('research','done',dict(content='Építsd meg az értékesítő oldalt.')),('build','dispatching',{}),('review','pending',{})):
   self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,project,state,result) VALUES(?,?,?,?,?)",('c1',node,venture.PID,state,json.dumps(result)))
  self.s.db.commit()
  def attempt(times,error):
   self.s.db.execute("UPDATE orbit_mission_steps SET state='dispatching',error=?,receipt='{}' WHERE run='c1' AND node='build'",(error,));self.s.db.commit()
   aid=self.s.rows('SELECT id FROM agents WHERE project=? ORDER BY rowid',(venture.PID,))[0]['id']
   jid=self.s.enqueue(aid,'ORBIT · build','mission_dispatch',payload=dict(mission_run='c1',mission_node='build'))
   with unittest.mock.patch('venture.pitfalls',return_value=[dict(times=times,advice='Answer with the complete JSON result object.')]),unittest.mock.patch.object(venture,'cycle_focus',return_value=f):
    missions.dispatch(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()))
   return self.s.rows("SELECT prompt FROM jobs WHERE kind='mission_agent' ORDER BY created DESC,rowid DESC")[0]['prompt']
  first,second=attempt(69,''),attempt(72,'Hiányos eredmény.')
  same=next(i for i,(x,y) in enumerate(zip(first,second)) if x!=y)
  self.assertGreaterEqual(same,first.index('\nRecent failures to avoid (data):'),'only the closing part differs')
  self.assertNotIn('avoid_recent_failures',first[:first.index('\nRecent failures to avoid')].split('Saved business-lab context (data):')[1])
  self.assertGreater(second.index('Diagnostic (data): Hiányos eredmény.'),second.index('\nRecent failures to avoid'),'the retry note is in the closing part')
 def test_a_described_fix_is_not_read_as_a_business_plan(self):
  # Cycle 220: {"text": "A hibát … megtaláltam …"} got "Hiányos üzleti terv: name" as its retry note.
  import time,missions
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('d7',self.mid,7,m['spec'],'running',time.time(),time.time()))
  self.s.db.commit()
  with unittest.mock.patch.object(venture,'cycle_focus',return_value=f),self.assertRaises(ValueError) as e:
   venture.save_result(self.s,venture.PID,'d7',dict(text='A hibát a snippet vágásában találtam meg.'))
  self.assertEqual(str(e.exception),venture.NO_WORK);self.assertIn('edits',venture.NO_WORK)
  with unittest.mock.patch.object(venture,'cycle_focus',return_value=None),self.assertRaises(ValueError) as e:
   venture.save_result(self.s,venture.PID,'d7',dict(text='nincs terv'))
  self.assertIn('Hiányos üzleti terv',str(e.exception),'outside a build a plan is still expected')
 def test_build_answer_without_id_is_not_mistaken_for_a_business_plan(self):
  import time,missions
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('b9',self.mid,9,m['spec'],'done',time.time(),time.time()))
  self.s.db.commit()
  with unittest.mock.patch.object(venture,'cycle_focus',return_value=f):
   r=venture.save_result(self.s,venture.PID,'b9',dict(summary='Kész értékesítő oldal valódi szöveggel.',files=[dict(name='index.html',content='<h1>TermékB</h1>'+'x'*40)]))
  self.assertEqual(r['mode'],'build');self.assertTrue(r['milestone_id'])
 def test_tester_gets_the_files_this_build_changed(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.built(1,self.milestone(milestone_id='design',files=[dict(name='index.html',content='<h1>TermékB</h1>'+'x'*40),dict(name='offer.md',content='# Ajánlat\n'+'y'*9500)],owner_actions=[]))
  files=venture_build.changed_files(self.s,'b1',budget=5000)
  self.assertEqual(list(files),['index.html'],'only whole files within the budget');self.assertTrue(files['index.html'].startswith('<h1>'))
  self.assertEqual(venture_build.changed_files(self.s,'nope'),{})
 def test_fix_mode_brief_is_written_by_orbit(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.assertIsNone(venture_build.fix_brief(self.s,self.mid,1),'no broken code, the planner plans')
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="raise SystemExit('Kérdések száma: 1')\n")],owner_actions=[]))
  brief=venture_build.fix_brief(self.s,self.mid,1)
  self.assertTrue(brief.startswith('milestone_id: engine'));self.assertIn('- validate.py: Kérdések száma: 1',brief);self.assertNotIn('first failed assert',brief)
  self.built(2,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="import sys\nif '--self-test' in sys.argv:\n assert 1+1==3, 'brutto: None'\n")],owner_actions=[]))
  brief=venture_build.fix_brief(self.s,self.mid,2)
  self.assertIn('AssertionError: brutto: None',brief);self.assertIn('The self-test of validate.py stops at its first failed assert',brief)
 def test_a_fix_mode_build_is_judged_by_the_measured_code_run(self):
  # Cycles 162-164: the 27B tester took 8-9 minutes of a 20-minute fix cycle to restate the code run.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="raise SystemExit('Kérdések száma: 1')\n")],owner_actions=[]))
  self.assertIsNone(venture_build.measured_review(self.s,'b1'),'no fix brief: the model tester reviews new work')
  def fix(n,content):
   brief=venture_build.fix_brief(self.s,self.mid,n)
   self.built(n,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content=content)],owner_actions=[]))
   self.s.db.execute("INSERT OR REPLACE INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)",('b'+str(n),'research','done',json.dumps(dict(content=brief))));self.s.db.commit()
   return venture_build.measured_review(self.s,'b'+str(n))
  verdict=fix(2,"raise SystemExit('Kérdések száma: 2')\n")
  self.assertTrue(verdict.startswith('VERDICT: revise\nORBIT mérés'));self.assertIn('validate.py → Kérdések száma: 2',verdict)
  verdict=fix(3,"import sys\nif '--self-test' in sys.argv:print('ok')\n")
  self.assertTrue(verdict.startswith('VERDICT: accept\n'));self.assertIn('ORBIT futtatás: 1/1',verdict)
 def test_an_unkept_promise_reopens_the_page_and_blocks_ready(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  r=self.built(1,self.milestone(milestone_id='landing',files=[dict(name='index.html',content='<!doctype html><h1>Étrend</h1><p>Mesterséges intelligencia tervezi, webhook értesít.</p>'),dict(name='engine.py',content="import sys\nif '--self-test' in sys.argv:print('ok')\n")],owner_actions=[]))
  self.assertFalse(r['checks']['ok']);self.assertIn('index.html',r['checks']['failed'])
  err=r['checks']['errors']['index.html']
  self.assertTrue(err.startswith('Ígéret-ellenőrzés: az oldal ígéri: webhook, de a kódban nincs nyoma („'));self.assertIn('az oldal ígéri: mesterséges intelligencia, de a kódban nincs nyoma',err)
  self.assertIn('Mesterséges intelligencia tervezi, webhook értesít.',err,'the builder sees the sentence to change')
  self.assertIn('Ígéret-ellenőrzés: index.html:',r['summary'])
  self.assertEqual(venture_build.fix_targets_of(r['checks']['errors']),['index.html'])
  brief=venture_build.fix_brief(self.s,self.mid,2);self.assertIn('- index.html: Ígéret-ellenőrzés',brief);self.assertIn('promise nothing the launched page cannot do',brief)
  self.assertFalse(venture_build.view(self.s,self.mid,f)['ready'])
  r=self.built(2,self.milestone(milestone_id='landing',files=[dict(name='index.html',content='<!doctype html><h1>Étrend</h1><p>Heti étrend a megadott adatokból.</p>')],owner_actions=[]))
  self.assertTrue(r['checks']['ok'],'an honest page passes')
 def test_a_check_failing_again_points_at_the_tests_own_arithmetic(self):
  # TermékA: "rate at limit: expected True, got False" in two builds; the test made 11 calls before the 10th.
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  bad=lambda v:"raise SystemExit('rate at limit: expected True, got False → SELF-TEST FAIL (1 hiba)')\n#"+v+"\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='server.py',content=bad('1'))],owner_actions=[]))
  self.assertNotIn('re-derive its expected value',venture_build.fix_brief(self.s,self.mid,2),'one failure is not a pattern')
  self.built(2,self.milestone(milestone_id='engine',files=[dict(name='server.py',content=bad('2'))],owner_actions=[]))
  brief=venture_build.fix_brief(self.s,self.mid,3)
  self.assertIn('The same check in server.py has failed in 2 builds although the code changed: re-derive its expected value',brief)
  self.assertIn("test's own arithmetic",venture_build.recurring_code_errors(self.s,self.mid,f)[0]['advice'])
 def test_real_data_accuracy_reaches_the_owner(self):
  # TermékA's realcheck.py measured 16/16 on real webshops while ORBIT kept saying "not measured on real data".
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  check=lambda ok,total:"import sys\nprint('Valós minta: %d/%d kézzel ellenőrzött tétel egyezik.')\nsys.exit(%d)\n"%(ok,total,0 if ok==total else 1)
  r=self.built(1,self.milestone(milestone_id='engine',files=[dict(name='realcheck.py',content=check(3,4))],owner_actions=[]))
  self.assertIn('Valós minta: 3/4.',r['summary'])
  h=venture_build.product_health(self.s,self.mid,f);self.assertEqual((h['real_ok'],h['real']),(3,4));self.assertFalse(venture_build.ready(h))
  self.built(2,self.milestone(milestone_id='engine',files=[dict(name='realcheck.py',content=check(4,4))],owner_actions=[]))
  v=venture_build.view(self.s,self.mid,f);self.assertTrue(v['ready']);self.assertEqual(v['health']['real'],4)
  self.assertIn('a valós mintán 4/4 kézzel ellenőrzött tétel egyezik',venture_build.eta(self.s,self.mid,f)['text'])
  self.assertIn('valós minta 4/4',venture_build.product_text(self.s))
  self.assertEqual(venture_build.real_note(dict(real=None)),'valódi adaton még nincs mérve')
 def test_the_sales_page_comes_right_after_the_api_and_a_cycle_keeps_its_milestone(self):
  # TermékB built billing, self-QA and tests for hours before any visitor said whether anyone wanted it.
  import time
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.assertEqual([k for k,_,_,_ in venture_build.roadmap(f)][:5],['design','engine','api','landing','validation'])
  m=__import__('missions').definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('c7',self.mid,7,m['spec'],'running',time.time(),time.time()+3600));self.s.db.commit()
  self.assertEqual(venture_build.remember_milestone(self.s,self.mid,7),'design')
  self.assertEqual(venture_build.remembered_milestone(self.s,7,f),'design')
  # the roadmap changed while the cycle ran (a deploy): the build is still filed under the cycle's milestone
  path=self.s.safe_path(venture.PID,'workspace/ventures/cycle-milestones.json')
  path.write_text(json.dumps({'7':dict(idea_id=f['idea_id'],milestone='api')}))
  r=venture_build.save(self.s,'c7',self.milestone(milestone_id='design',files=[dict(name='architecture.md',content='# Terv\nRészletes rendszerterv.')],owner_actions=[]),f,enforce=True)
  self.assertEqual(r['milestone_id'],'api')
 def test_a_large_existing_file_is_to_be_edited_not_rewritten(self):
  # 10 of 53 builds hit the reply limit, mostly rewriting 12-13 thousand characters of existing files.
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  big='# Leírás\n'+'Egy hosszú sor a termékről. '*120
  self.built(1,self.milestone(milestone_id='design',files=[dict(name='architecture.md',content=big)],owner_actions=[]))
  self.assertEqual(venture_build.file_sizes(self.s,f)['architecture.md'],len(big))
  r=self.built(2,self.milestone(milestone_id='design',files=[dict(name='architecture.md',content=big+' Még egy mondat.')],owner_actions=[]))
  self.assertEqual(r['rewrites'],['architecture.md']);self.assertIn('Teljes újraírás csere-blokk helyett: architecture.md',r['summary'])
  r=self.built(3,self.milestone(milestone_id='design',files=[],edits=[dict(name='architecture.md',find='# Leírás',replace='# Rendszerterv')],owner_actions=[]))
  self.assertEqual(r['rewrites'],[],'an edit is not a rewrite')
 def test_a_disputed_legal_citation_without_a_source_is_not_acted_on(self):
  # Cycle 191: the tester called the correct Ekertv. 4. § wrong, with no source (and a Polish word).
  wrong="VERDICT: revise\n(2) az `Ekertv. 4. §` hivatkozás nem egyezik a tényleges jogszabályi alappal (a 2013. évi V. törvény a właściwa hivatkozás)."
  self.assertIn('forrás nélkül vitat egy jogszabályi hivatkozást',venture_build.legal_caution(wrong))
  self.assertEqual(venture_build.legal_caution(wrong+' Forrás: https://njt.hu/jogszabaly/2001-108-00-00'),'','a sourced objection goes through')
  self.assertEqual(venture_build.legal_caution('VERDICT: revise\nAz api_errors items-ellenőrzése hiányzik.'),'','not a legal dispute')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.built(1,self.milestone(milestone_id='design',files=[dict(name='architecture.md',content='# Terv\nRészletes rendszerterv.')],owner_actions=[]),review=wrong)
  m=next(x for x in venture_build.progress(self.s,self.mid,f)[0] if x['id']=='design')
  self.assertIn('[ORBIT: a tesztelő forrás nélkül vitat',m['review']);self.assertEqual(m['state'],'revise')
 def test_a_fix_the_measure_does_not_see_reaches_the_owner(self):
  # TermékA: the builder "removed the Stripe promise" twice while the (wrong) check kept failing the page.
  err='Ígéret-ellenőrzés: az oldal ígéri: kártyás fizetés (Stripe), de a kódban nincs nyoma'
  h=[(195,{'index.html':err},'Bővítettem a rácsot.'),(196,{'index.html':err},'Javítottam az oldalt: eltávolítottam a Stripe/kártyás fizetésre utaló ígéretet. A többi változatlan.')]
  self.assertEqual(venture_build.contradictions(h),[('index.html','Javítottam az oldalt: eltávolítottam a Stripe/kártyás fizetésre utaló ígéretet',err,196)])
  self.assertEqual(venture_build.contradictions([h[0],(196,{'index.html':err},'Új szekciót írtam.')]),[],'no fix claimed')
  self.assertEqual(venture_build.contradictions([h[0],(196,{'index.html':'más hiba'},h[1][2])]),[],'the error changed')
  import sys
  if sys.platform!='darwin':return
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  bad="raise SystemExit('LIMIT: expected 5, got 6 → SELF-TEST FAIL (1 hiba)')\n#"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=bad+'1')],owner_actions=[]))
  self.built(2,self.milestone(milestone_id='engine',summary='Kijavítottam az engine.py LIMIT értékét.',files=[dict(name='engine.py',content=bad+'2')],owner_actions=[]))
  acts=venture_build.progress(self.s,self.mid,f)[1]
  a=next(x for x in acts if x['title'].startswith('Ellentmondás'))
  self.assertIn('(engine.py)',a['title']);self.assertIn('Kijavítottam az engine.py LIMIT értékét',a['draft'])
 def test_a_stuck_error_escalates_instead_of_looping(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  for n in range(1,7):self.built(n,self.milestone(milestone_id='engine',files=[dict(name='validate.py',content="raise SystemExit('Kérdések száma: 1')\n")],owner_actions=[]))
  ms,acts=venture_build.progress(self.s,self.mid,f);engine=next(m for m in ms if m['id']=='engine')
  self.assertTrue(engine['stuck']);self.assertNotEqual(venture_build.next_milestone(ms),'engine','no endless fix loop')
  self.assertTrue(any(a['title']=='Makacs hiba: validate.py' and 'Kérdések száma' in a['draft'] for a in acts))
 def test_measured_times_answer_how_long_it_takes(self):
  # Asked "how long until it finishes?", the assistant guessed "1-2 minutes" for a 20-minute cycle.
  import sys,time,assistant_context
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='a.py',content="raise SystemExit('A hiba')\n"),dict(name='b.py',content="raise SystemExit('B hiba')\n")],owner_actions=[]))
  self.built(2,self.milestone(milestone_id='engine',files=[dict(name='a.py',content="import sys\nif '--self-test' in sys.argv:print('ok')\n")],owner_actions=[]))
  now=time.time();aid=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(venture.PID,))[0]['id']
  def job(run,node,start,seconds,status='done',fixed=None):
   p=dict(mission_run=run,mission_node=node,**(dict(fixed_result=fixed) if fixed else {}))
   self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,created,started,finished,payload) VALUES(?,?,?,?,?,?,?,?,?,?)',(run+node,venture.PID,aid,'mission_agent',status,'x',start,start,start+seconds if status=='done' else None,json.dumps(p)))
  for i,run in enumerate(('b1','b2')):
   base=now-7200+i*1500;job(run,'research',base,60);job(run,'build',base+60,600);job(run,'review',base+660,480)
  m=__import__('missions').definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('b3',self.mid,3,m['spec'],'running',now-400,now+3600))
  brief=venture_build.fix_brief(self.s,self.mid,3)
  for node,state,result in (('research','done',dict(content=brief)),('build','waiting',{}),('review','pending',{})):
   self.s.db.execute('INSERT INTO orbit_mission_steps(run,node,state,result) VALUES(?,?,?,?)',('b3',node,state,json.dumps(result)))
  job('b3','research',now-400,0,fixed=brief);job('b3','build',now-300,0,status='running');self.s.db.commit()
  e=venture_build.eta(self.s,self.mid,f,now=now)
  self.assertEqual(e['step'],dict(node='build',label='építés',cycle=3,usual_minutes=10,measured=False,state='fut',minutes=5))
  self.assertEqual(e['cycle_left_minutes'],5,'the rest of the build; a fix-mode review is measured, not modelled')
  self.assertEqual(e['cycle_minutes'],19);self.assertEqual((e['failing'],e['trend'],e['cycles_left'],e['ready_minutes']),(1,'csökken',1,19))
  self.assertEqual(e['text'],'3. kör: építés fut 5 perce (szokásosan kb. 10 perc) · a kör várhatóan kb. 5 perc múlva ér véget · egy kör átlagosan kb. 19 perc · még 1 hibás ellenőrzés, a hibák száma csökken (2 → 1): kb. 1 kör (≈ 19 perc) múlva lehet kész')
  self.assertIn('⏱ 3. kör: építés fut',venture_build.product_text(self.s),'the /termek answer')
  self.assertEqual(venture_build.view(self.s,self.mid,f)['eta']['step']['node'],'build')
  live=assistant_context.snapshot(self.s)['autopilot'];self.assertEqual(live['failing'],1);self.assertIn('never guess',live['note'])
  self.assertEqual(assistant_context.read_app(self.s,venture.PID,'autopilot')['text'],e['text'])
 def test_a_new_failure_is_called_a_step_back_not_progress(self):
  # Cycle 171: billing.py failed after three clean builds, and the estimate called it progress.
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  e=lambda c,ok,failed,errors:dict(cycle=c,files=11,files_ok=ok,live=3,live_ok=3,failed=failed,errors=errors)
  with unittest.mock.patch.object(venture_build,'timeline',return_value=[e(168,11,[],{}),e(169,11,[],{}),e(170,11,[],{}),e(171,10,['billing.py'],{'billing.py':'free_limit: expected 50, got 100'})]):
   est=venture_build.eta(self.s,self.mid,f)
  self.assertEqual(est['trend'],'nő');self.assertIn('új hiba jelent meg (billing.py)',est['text']);self.assertNotIn('haladás',est['text'])
  # the same files failing with fewer failed values is progress (TermékA server.py: 5 → 2)
  s5={'server.py':'a; b; c; d; e → SELF-TEST FAIL (5 hiba)','smoke.json':'Élő próba: POST /check → 502'};s2={'server.py':'a; b → SELF-TEST FAIL (2 hiba)','smoke.json':'Élő próba: POST /check → 502'}
  with unittest.mock.patch.object(venture_build,'timeline',return_value=[dict(e(180,10,['server.py','smoke.json'],s5),live_ok=1),dict(e(182,10,['server.py','smoke.json'],s2),live_ok=1)]):
   est=venture_build.eta(self.s,self.mid,f)
  self.assertEqual((est['trend'],est['weight'],est['previous_weight']),('csökken',3,6));self.assertIn('a hibák száma csökken (6 → 3)',est['text']);self.assertNotIn('új hiba',est['text'])
 def test_owner_hears_once_when_the_product_passes_everything(self):
  import sys
  if sys.platform!='darwin':self.skipTest('macOS sandbox')
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.assertFalse(venture_build.ready(dict(ok=True,files=3,files_ok=2,live=None)))
  self.assertFalse(venture_build.ready(dict(ok=True,files=2,files_ok=2,live=3,live_ok=2)))
  ok="import sys\nif __name__=='__main__' and '--self-test' in sys.argv:print('ok')\n"
  sent=[];cfg=dict(mode='local',providers=dict(telegram=dict(notifications=True,chat_id='1')))
  with unittest.mock.patch('connections.settings',return_value=cfg),unittest.mock.patch('connections.allowed',return_value=True),unittest.mock.patch('connections.http',side_effect=lambda *a,**k:sent.append(a[2]['text'])):
   self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=ok)],owner_actions=[]))
   self.built(2,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=ok)],owner_actions=[]))
  self.assertEqual(len(sent),1,'one message, not one per build');self.assertIn('átment a saját ellenőrzésein',sent[0]);self.assertIn('valódi adaton',sent[0])
  self.assertTrue(venture_build.view(self.s,self.mid,f)['ready'])
 def test_pace_averages_recent_cycles_and_steps(self):
  import time,json as j
  now=time.time()
  for n,(minutes,build) in enumerate(((30,15),(20,9)),1):
   rid='p'+str(n);self.s.db.execute("INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline,finished) VALUES(?,?,?,?,?,?,?,?)",(rid,self.mid,900+n,'{}','done',now-minutes*60-60,now,now-60))
   self.s.db.execute("INSERT INTO jobs(id,project,agent,kind,status,prompt,created,started,finished,payload) VALUES(?,?,?,?,?,?,?,?,?,?)",('j'+str(n),venture.PID,'a','mission_agent','done','p',now-3600,now-build*60-60,now-60,j.dumps(dict(mission_run=rid,mission_node='build'))))
  old='old';self.s.db.execute("INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline,finished) VALUES(?,?,?,?,?,?,?,?)",(old,self.mid,800,'{}','done',now-30*3600,now,now-29*3600))
  self.s.db.commit()
  p=venture.pace(self.s,self.mid)
  self.assertEqual((p['cycles'],p['minutes'],p['steps']['build']),(2,25,12.0),'only the last hours count')
  self.s.db.execute("UPDATE jobs SET payload=json_set(payload,'$.rounds',json(?)) WHERE id='j1'",(j.dumps([dict(round=1,prompt=4800,output=7000,stop='length'),dict(round=2,prompt=5100,output=300,stop='stop')]),));self.s.db.commit()
  self.assertEqual(venture.pace(self.s,self.mid)['tokens']['build'],dict(jobs=1,max_prompt=5100,max_output=7000,capped=1,later_rounds=0,cache_hits=0))
  rounds=[dict(round=1,prompt=4972,output=15,stop='stop',read_s=101.0),dict(round=2,prompt=8124,output=36,stop='stop',read_s=68.0),dict(round=3,prompt=8768,output=37,stop='stop',read_s=12.9)]
  self.s.db.execute("UPDATE jobs SET payload=json_set(payload,'$.rounds',json(?)) WHERE id='j1'",(j.dumps(rounds),));self.s.db.commit()
  b=venture.pace(self.s,self.mid)['tokens']['build'];self.assertEqual((b['later_rounds'],b['cache_hits']),(2,1),'round 3 read 8768 tokens in 12.9 s: a cache hit')
 def test_owner_list_keeps_only_real_owner_steps(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  acts=[dict(title=t,kind='account') for t in ('Futtasd a self-testet','Indítsd a servert','ORBIT sandbox-ban lefuttatni a server.py-t','Landing page publikálása')]
  r=self.built(1,self.milestone(milestone_id='design',owner_actions=acts))
  self.assertEqual([a['title'] for a in r['owner_actions']],['Landing page publikálása'])
  self.assertEqual([a['title'] for a in venture_build.progress(self.s,self.mid,f)[1]],['Landing page publikálása'])
 def test_build_prompt_stays_within_the_job_limit(self):
  # Long plans and tester notes once pushed every build step over the 12 000-character job limit.
  long='x'*3000
  venture.save_result(self.s,venture.PID,'r1',self.plan(offer=long,problem=long,architecture=long,tech_stack=long,costs=long,hypothesis=long));f=venture_build.active(self.s)
  for n,mid in enumerate(('design','engine','api','pipeline'),1):self.built(n,self.milestone(milestone_id=mid,owner_actions=[]),review='VERDICT: revise\n'+'y'*3000)
  import missions,venture as v
  c=v.context(self.s,dict(id=self.mid,goal='g'),venture.PID);size=len(missions.dumps(c))
  self.assertLess(size,9000);self.assertEqual([r['id'] for r in c['roadmap'] if 'goal' in r],[c['next_milestone']],'only the milestone to work on now is detailed')
  aid=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(venture.PID,))[0]['id']
  self.assertTrue(self.s.enqueue(aid,'z'*20000,'mission_agent',limit=24000))
  with self.assertRaises(ValueError):self.s.enqueue(aid,'z'*20000)
 def test_scouting_waits_while_ideas_are_queued(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.assertEqual(venture_build.plan_cycle(self.s,3),'explore')
  venture_build.write(self.s,dict(venture_build.read(self.s),queue=['a1','b2']))
  self.assertTrue(venture_build.plan_cycle(self.s,3).startswith('build:'))
 def test_try_button_runs_the_product_and_report_lists_builds(self):
  import bridge,sys,daily_report
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  with self.assertRaises(ValueError):bridge.dispatch(dict(action='venture_try',idea_id=f['idea_id']),self.s)
  ok="import sys\nif '--self-test' in sys.argv:print('ok')\n"
  self.built(1,self.milestone(milestone_id='engine',files=[dict(name='engine.py',content=ok)],owner_actions=[]))
  if sys.platform=='darwin':
   r=bridge.dispatch(dict(action='venture_try',idea_id=f['idea_id']),self.s);self.assertIn('1/1 fájl hibátlanul',r['summary'])
  self.s.db.execute("UPDATE orbit_mission_steps SET updated=?",(__import__('time').time(),));self.s.db.commit()
  self.assertEqual(venture_build.recent_builds(self.s,self.mid,0)[0]['title'],'Működő mag')
  self.assertIn('Működő mag · 1 fájl',daily_report.compose(self.s))
 def test_product_folder_opens_only_by_idea_id(self):
  import bridge
  from unittest.mock import patch
  with patch('bridge.subprocess.run') as run:
   r=bridge.dispatch(dict(action='venture_folder',idea_id='b0e22e5f'),self.s)
  self.assertTrue(r['path'].endswith('workspace/product-b0e22e5f'));self.assertEqual(run.call_args[0][0][0],'/usr/bin/open')
  for bad in ('../x','',None,'a/b'):
   with self.assertRaises(ValueError):bridge.dispatch(dict(action='venture_folder',idea_id=bad),self.s)
 def test_wrong_milestone_id_goes_to_the_next_open_milestone(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  r=self.built(1,self.milestone(milestone_id=f['idea_id'],owner_actions=[]))
  self.assertEqual(r['milestone_id'],'design')
 def test_partial_milestone_is_finished_before_moving_on(self):
  venture.save_result(self.s,venture.PID,'r1',self.plan());f=venture_build.active(self.s)
  self.built(1,self.milestone(status='partial'));self.assertEqual(self.state(f,'landing'),'revise')
 def test_lab_agents_use_one_model(self):
  from unittest.mock import patch
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b'),dict(name='qwen2.5:14b')]):venture.pin_model(self.s)
  self.assertEqual({r['model'] for r in self.s.rows("SELECT model FROM agents WHERE project=? AND name IN ('Piackutató','Építő','Kritikus')",(venture.PID,))},{'qwen3.5:9b'})
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b'),dict(name='qwen3.8:27b-q4_K_M')]):venture.pin_model(self.s)
  self.assertEqual({r['model'] for r in self.s.rows("SELECT model FROM agents WHERE project=? AND name='Kritikus'",(venture.PID,))},{'qwen3.8:27b-q4_K_M'},'the smarter installed model wins')
  model=lambda n:self.s.rows('SELECT model FROM agents WHERE project=? AND name=?',(venture.PID,n))[0]['model']
  self.assertEqual(model('Építő'),'qwen3.8:27b-q4_K_M');self.assertEqual(model('Piackutató'),'qwen3.5:9b','the planner runs on the fast model')
  self.assertEqual(venture.retry_model(self.s),'qwen3.8:27b-q4_K_M')
  from studio import model_slowness
  self.assertEqual((model_slowness('qwen3.8:27b-q4_K_M'),model_slowness('qwen3.5:9b'),model_slowness('auto')),(4,1,1))
  with patch('model_hub.models',return_value=[dict(name='qwen2.5:14b')]):venture.pin_model(self.s)
  self.assertEqual({r['model'] for r in self.s.rows("SELECT model FROM agents WHERE project=? AND name='Építő'",(venture.PID,))},{'auto'})
 def test_finished_products_keep_improving_in_parallel_and_can_be_previewed(self):
  a=venture.save_result(self.s,venture.PID,'p1',self.plan(name='Számla API',offer='Számlakinyerés API'))
  f=venture_build.active(self.s)
  venture_build.save(self.s,'p2',dict(milestone_id='landing',summary='Kész értékesítő oldal.',files=[dict(name='index.html',content='<!doctype html><link rel="stylesheet" href="styles.css"><h1>Számla API</h1><script>alert(1)</script>'),dict(name='styles.css',content='h1{color:#0b6;font-size:40px}')]))
  pv=venture_build.web_previews(self.s,f)
  self.assertEqual(pv[0]['name'],'index.html');self.assertIn('<style>h1{color:#0b6',pv[0]['html']);self.assertTrue(pv[0]['artifact'])
  # mark the first product finished, start a second one: cycles interleave build, scouting and upkeep
  venture.configure(self.s,dict(focus='explore'))
  venture_build.write(self.s,dict(venture_build.read(self.s),finished=[f['idea_id']],mode='explore',auto_explore=True))
  b=venture.save_result(self.s,venture.PID,'p3',self.plan(name='SEO hálózat',offer='Programmatikus SEO'))
  g=venture_build.active(self.s);self.assertEqual(g['idea_id'],b['idea_id'])
  plans={c:venture_build.plan_cycle(self.s,c) for c in range(1,10)}
  self.assertEqual(plans[3],'explore');self.assertEqual(plans[5],'maintain:'+f['idea_id']);self.assertEqual(plans[4],'build:'+g['idea_id'])
  self.assertEqual(venture.prompt_for(self.s,'research','x',5),venture_build.MAINTAIN_PLAN)
  self.assertEqual(venture.context(self.s,dict(id=self.mid,goal='g'),venture.PID,5)['focus']['idea_id'],f['idea_id'])
  # an improvement saved in a maintenance cycle lands in the finished product, not the current build
  import missions,time
  m=missions.definition(self.s,venture.PID,self.mid)
  self.s.db.execute('INSERT INTO orbit_mission_runs(id,mission,cycle,spec,status,created,deadline) VALUES(?,?,?,?,?,?,?)',('mt5',self.mid,5,m['spec'],'running',time.time(),time.time()));self.s.db.commit()
  r=venture.save_result(self.s,venture.PID,'mt5',dict(milestone_id='landing',summary='Javított hero szöveg.',files=[dict(name='index.html',content='<!doctype html><h1>Számla API 2</h1>')]))
  self.assertEqual(r['idea_id'],f['idea_id']);self.assertEqual(venture_build.read(self.s)['idea_id'],b['idea_id'])
  st=venture.status(self.s);self.assertEqual(st['portfolio'][0]['name'],'Számla API');self.assertIn('Számla API 2',st['portfolio'][0]['previews'][0]['html'])
  self.assertEqual(venture.brief(self.s)['portfolio'][0]['name'],'Számla API')
 def test_approval_based_offer_is_not_automated_and_scout_restarts_search(self):
  r=venture.save_result(self.s,venture.PID,'w1',self.plan(name='Árnyék-Ügynök widget',offer='Javításokat készít, majd csak jóváhagyásra kerül élesítésre.'))
  self.assertFalse(r['automated'])
  ok=venture.save_result(self.s,venture.PID,'w2',self.plan(name='Árfigyelő API',offer='Automatikus árfigyelés API-n'))
  f=venture_build.active(self.s);self.assertEqual(f['idea_id'],ok['idea_id'])
  old=venture.save_result(self.s,venture.PID,'w0',self.plan(name='Régi pontozott ötlet',offer='Automatikus riport API-n'))
  import time;time.sleep(.01)
  venture.configure(self.s,dict(focus='scout'))
  st=venture_build.read(self.s);self.assertIn(ok['idea_id'],st['skip']);self.assertTrue(st['auto_explore'])
  # 1 Nov 21:52: the owner's new search started building an old, already scored idea at once.
  self.assertIsNone(venture_build.active(self.s),'neither the skipped idea nor an older scored one ('+old['idea_id']+') is built after a new search')
  n=venture.save_result(self.s,venture.PID,'w3',self.plan(name='Programmatikus SEO hálózat',offer='Automatikus SEO oldalak'))
  self.assertEqual(venture_build.active(self.s)['idea_id'],n['idea_id'],'a new qualified idea is built automatically')
if __name__=='__main__':unittest.main()
