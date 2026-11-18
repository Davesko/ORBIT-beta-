import datetime,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import clip_farm,clip_sources,gta6,project_apps

def at(text):return datetime.datetime.fromisoformat(text+'+00:00').timestamp()
PRE=at('2026-11-02T12:00:00');LIVE=at('2026-11-20T12:00:00')
CFG=dict(gta6.DEFAULT)
def clip(title='CRAZY POLICE CHASE',categories=('Grand Theft Auto VI',),timestamp=LIVE-3600,**kw):
 return dict(title=title,categories=list(categories),timestamp=timestamp,duration=45,**kw)

class SourceTests(unittest.TestCase):
 def test_twitch_clips_and_broadcasts_are_sources_next_to_youtube(self):
  self.assertEqual(clip_sources.source_id('https://www.twitch.tv/caseoh_/clip/AuspiciousChimp-pGaXsigABq'),'twc:AuspiciousChimp-pGaXsigABq')
  self.assertEqual(clip_sources.source_id('https://clips.twitch.tv/AuspiciousChimp-pGaXsigABq'),'twc:AuspiciousChimp-pGaXsigABq')
  self.assertEqual(clip_sources.source_id('https://www.twitch.tv/videos/2917289316'),'twv:2917289316')
  self.assertEqual(clip_sources.source_id('https://www.youtube.com/watch?v=u9Ak0a715jQ'),'u9Ak0a715jQ')
  self.assertEqual(clip_sources.source_url('twc:AuspiciousChimp-pGaXsigABq'),'https://clips.twitch.tv/AuspiciousChimp-pGaXsigABq')
  for bad in ('https://www.twitch.tv/caseoh_','http://clips.twitch.tv/AuspiciousChimp','https://evil.example/clip/x','https://www.twitch.tv/videos/abc'):
   self.assertIsNone(clip_sources.source_id(bad),bad)
  self.assertTrue(clip_sources.valid_source_id('twv:2917289316'));self.assertFalse(clip_sources.valid_source_id('twc:../../etc'))

class ClassifyTests(unittest.TestCase):
 def test_leaked_footage_never_passes(self):
  # The owner asked for leaked footage too. On the August 2026 leak Rockstar sent takedowns within hours and Take-Two
  # subpoenaed Microsoft and Discord; a channel posting it collects strikes just before the launch.
  for title in ('GTA 6 LEAKED gameplay','GTA 6 leak reaction','GTA VI kiszivárgott felvétel','GTA 6 early access footage','gta 6 dev build gameplay','GTA 6 pre-release footage','Cyberleek GTA 6 map'):
   for now in (PRE,LIVE):
    ok,why=gta6.classify(clip(title),CFG,now);self.assertFalse(ok,title);self.assertIn('Kiszivárgott',why)
  self.assertFalse(gta6.classify(clip('GTA 6 reaction',description='watch the leaked map here'),CFG,LIVE)[0],'a leak in the description counts too')
 def test_before_the_launch_only_reactions_and_hype(self):
  self.assertTrue(gta6.classify(clip('reacting to the GTA 6 trailer'),CFG,PRE)[0])
  self.assertFalse(gta6.classify(clip('GTA 6 gameplay first look'),CFG,PRE)[0],'real gameplay cannot exist yet')
  self.assertFalse(gta6.classify(clip('so funny'),CFG,PRE)[0],'no reaction or hype in the title')
 def test_after_the_launch_real_streams_of_the_game(self):
  self.assertTrue(gta6.classify(clip('CRAZY POLICE CHASE'),CFG,LIVE)[0],'the Twitch category proves the game')
  self.assertTrue(gta6.classify(clip('first time in gta 6',categories=()),CFG,LIVE)[0],'YouTube has only the title')
  self.assertFalse(gta6.classify(clip('POLICE CHASE',categories=('Fortnite',)),CFG,LIVE)[0],'another game')
  self.assertFalse(gta6.classify(clip('POLICE CHASE',categories=()),CFG,LIVE)[0],'nothing shows it is GTA 6')
  self.assertFalse(gta6.classify(clip('GTA 5 police chase',categories=('Grand Theft Auto VI',)),CFG,LIVE)[0],'a GTA 5 clip in the wrong category')
  self.assertFalse(gta6.classify(clip('GTA 6 realistic fan-made concept'),CFG,LIVE)[0])
  self.assertFalse(gta6.classify(clip('GTA 6 is finally here',timestamp=PRE),CFG,LIVE)[0],'made before the launch')
  self.assertFalse(gta6.classify(clip('GTA 6 n word moment'),CFG,LIVE)[0],'not fit for a channel')
 def test_the_rehearsal_runs_on_any_game_on_screen(self):
  self.assertTrue(gta6.classify(clip('big crash',categories=('Grand Theft Auto V',),timestamp=PRE),CFG,PRE,rehearsal=True)[0])
  self.assertTrue(gta6.classify(clip('big crash',categories=('Fortnite',)),CFG,PRE,rehearsal=True)[0])
  self.assertFalse(gta6.classify(clip('big crash',categories=('Just Chatting',)),CFG,PRE,rehearsal=True)[0],'no gameplay to frame')
  self.assertFalse(gta6.classify(clip('GTA V leaked mission',categories=('Grand Theft Auto V',)),CFG,PRE,rehearsal=True)[0])
 def test_the_gate_opens_when_the_first_time_zone_reaches_the_date(self):
  self.assertEqual(gta6.phase(CFG,at('2026-11-18T10:59:00')),'pre');self.assertEqual(gta6.phase(CFG,at('2026-11-18T11:01:00')),'live')
  self.assertEqual(gta6.phase(dict(gta6.DEFAULT,release_date='2027-02-01'),LIVE),'pre','a new date moves the gate')
 def test_most_replayed_window_of_a_long_stream(self):
  heat=[dict(start=0,value=1.0),dict(start=1452.4,value=.72),dict(start=8922.0,value=.98)]
  self.assertEqual(gta6.most_replayed(heat,20749),dict(start=8892,duration=150,replayed=.98),'the video start is everyone\'s start, not a highlight')
  self.assertIsNone(gta6.most_replayed([],20749))
 def test_a_twitch_clip_stays_whole(self):
  track=dict(source=dict(duration=44.5),transcript=dict(segments=[dict(text='oh my god'),dict(text='the cops are here')]))
  plan=gta6.whole_clip([track],gta6.FORMAT)
  self.assertEqual((plan['selection'],plan['duration'],plan['shots'][0]['start'],plan['shots'][0]['end']),('whole_stream_clip',44.5,0.0,44.5))
  self.assertEqual(plan['outline']['hook'],'oh my god the cops are here')
  self.assertEqual(gta6.whole_clip([dict(track,source=dict(duration=90))],gta6.FORMAT)['duration'],59.0,'the format\'s limit')
  with self.assertRaisesRegex(ValueError,'túl rövid'):gta6.whole_clip([dict(track,source=dict(duration=10))],gta6.FORMAT)
 def test_a_long_stream_keeps_its_liveliest_stretch_at_sentence_ends(self):
  # 2 Nov: the story director failed on a stream's chat ("a fragmented conversation") after a long wait for the model.
  said=[dict(start=float(t),end=float(t)+4.5,text='ok') for t in range(0,60,5)]+[dict(start=float(t),end=float(t)+4.5,text='no way no way the cops are here oh my god') for t in range(60,105,5)]+[dict(start=float(t),end=float(t)+4.5,text='ok') for t in range(105,150,5)]
  track=dict(source=dict(duration=150),transcript=dict(segments=said));plan=gta6.stream_cut([track],gta6.FORMAT,'youtube');shot=plan['shots'][0]
  self.assertEqual(plan['selection'],'liveliest_stream_span');self.assertGreaterEqual(shot['start'],55);self.assertLessEqual(shot['end'],110)
  self.assertGreaterEqual(plan['duration'],gta6.FORMAT['target_seconds']);self.assertLessEqual(plan['duration'],gta6.FORMAT['max_seconds']);self.assertIn(shot['start'],[x['start'] for x in said]);self.assertIn(shot['end'],[x['end'] for x in said])
  self.assertIn('no way',plan['outline']['hook'])
  quiet=gta6.stream_cut([dict(track,transcript=dict(segments=[]))],gta6.FORMAT,'youtube');self.assertEqual((quiet['shots'][0]['start'],quiet['duration']),(0.0,35.0),'gameplay without talk still gives a clip')
  self.assertEqual(gta6.stream_cut([dict(track,source=dict(duration=40))],gta6.FORMAT,'twitch')['selection'],'whole_stream_clip')
  with self.assertRaisesRegex(ValueError,'túl rövid'):gta6.stream_cut([dict(track,source=dict(duration=10))],gta6.FORMAT,'youtube')
 def test_a_stable_face_is_the_facecam_on_top_of_the_game(self):
  from smart_framing import validate
  def frame(*boxes):return dict(width=1920,height=1080,faces=[dict(box=b) for b in boxes])
  cam=[120,600,110,130]
  layout=gta6.stream_layout([frame(cam),frame([122,602,108,128],[900,300,60,70]),frame(cam),frame(),frame([118,598,112,132])])
  self.assertEqual(layout['mode'],'stack');self.assertEqual(layout['top_fraction'],.3);validate(layout)
  x,y,w,h=layout['regions'][0];self.assertLess(x,120/1920);self.assertLess(y,600/1080);self.assertGreater(x+w,230/1920);self.assertGreater(y+h,730/1080)
  self.assertAlmostEqual(layout['regions'][1][2],.452,places=2,msg='the game band keeps the middle of the picture')
  self.assertIsNone(gta6.stream_layout([frame(),frame(),frame()]),'no face, no stack')
  self.assertIsNone(gta6.stream_layout([frame([100*i,100,80,90]) for i in range(1,6)]),'a moving face (a character) is not a facecam')
  self.assertIsNone(gta6.stream_layout([frame([500,100,800,900])]*5),'a full-screen camera is not a corner of a game')
  self.assertIsNone(gta6.stream_layout([frame(cam)]),'too few frames to say')
 def test_the_sources_file_is_read_leniently(self):
  # The owner and the agents edit it by hand: what cannot be used is skipped, never an error on launch day.
  out=gta6.parse_sources('# x\n## Twitch-csatornák\n- https://www.twitch.tv/Caseoh_/\n- @xQc\n- a b\n- xqc\n## YouTube-keresések\n- GTA 6 stream\n## Megjelenés\n- 2027-02-01\n## Klipek időszaka\n- 7d\n')
  self.assertEqual((out['channels'],out['queries'],out['release_date'],out['clip_range']),(['caseoh_','xqc'],['GTA 6 stream'],'2027-02-01','7d'))
  self.assertEqual(gta6.parse_sources('nonsense')['channels'],gta6.DEFAULT['channels'])
  bad=gta6.parse_sources('## Megjelenés\n- holnap\n## Klipek időszaka\n- ever\n');self.assertEqual((bad['release_date'],bad['clip_range']),(gta6.RELEASE_DATE,'24hr'))
  self.assertEqual(gta6.parse_sources(gta6.sources_text()),dict(gta6.DEFAULT),'what is written is read back')

class FarmTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  translate=patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts));translate.start();self.addCleanup(translate.stop)
  self.s=Studio(Path(tmp.name));self.addCleanup(self.s.db.close);clip_farm.configure(self.s);gta6._checked['at']=0
  path=gta6.sources_path(self.s);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(gta6.sources_text(dict(gta6.DEFAULT,channels=['caseoh_','jynxzi'],queries=['GTA 6 stream'])))
 def reader(self,clips=None,videos=None,details=None):
  clips=clips or {};details=details or {}
  def read(request):
   if request['operation']=='twitch_clips':return dict(candidates=clips.get(request['channel'],[]))
   if request['operation']=='youtube_recent':return dict(candidates=videos or [])
   return details[request['video_id']]
  return read
 def twitch(self,slug,views,channel='caseoh_',title='clip'):
  return dict(id='twc:'+slug,url='https://clips.twitch.tv/'+slug,title=title,duration=40,view_count=views,timestamp=LIVE-600,channel=channel)
 def test_the_most_viewed_real_gta6_clip_wins(self):
  clips={'caseoh_':[self.twitch('LowViewsAaaa',100),self.twitch('OtherGameBbb',9000),self.twitch('LeakedOneCcc',99000,title='GTA 6 LEAK')],'jynxzi':[self.twitch('BigChaseDddd',5000,'jynxzi')]}
  details={'twc:LowViewsAaaa':dict(categories=['Grand Theft Auto VI'],timestamp=LIVE-600),'twc:OtherGameBbb':dict(categories=['Fortnite'],timestamp=LIVE-600),'twc:BigChaseDddd':dict(categories=['Grand Theft Auto VI'],timestamp=LIVE-600)}
  found,rejected,errors=gta6.discover(self.s,gta6.settings(self.s),now=LIVE,read_source=self.reader(clips,details=details))
  self.assertEqual([c['id'] for c in found],['twc:BigChaseDddd','twc:LowViewsAaaa'])
  self.assertEqual({r['title']:r['reason'] for r in rejected}['GTA 6 LEAK'],'Kiszivárgott anyagra utal.');self.assertIn('Más játék',[r for r in rejected if r['reason'].startswith('Más')][0]['reason'])
 def test_one_source_failing_does_not_stop_the_others(self):
  def read(request):
   if request.get('channel')=='caseoh_':raise ValueError('HTTP 404')
   return self.reader({'jynxzi':[self.twitch('BigChaseDddd',5000,'jynxzi')]},details={'twc:BigChaseDddd':dict(categories=['Grand Theft Auto VI'],timestamp=LIVE-600)})(request)
  found,_,errors=gta6.discover(self.s,gta6.settings(self.s),now=LIVE,read_source=read)
  self.assertEqual(len(found),1);self.assertIn('caseoh_: HTTP 404',errors)
 def test_a_long_youtube_stream_gives_its_most_replayed_part(self):
  video=dict(id='u9Ak0a715jQ',url='https://www.youtube.com/watch?v=u9Ak0a715jQ',title='GTA 6 first time playing',duration=20000,view_count=900000,channel='Fanum')
  short=dict(video,id='shortvideo1',duration=300,title='GTA 6 best moments')
  # The first rehearsal chose a 10.8-million-view walkthrough with no commentary: an upload, not a stream.
  upload=dict(video,id='walkthrough',title='GTA 6 walkthrough no commentary',view_count=10800000)
  details={'u9Ak0a715jQ':dict(title=video['title'],timestamp=LIVE-7200,duration=20000,live_status='was_live',categories=['Entertainment'],heatmap=[dict(start=9000,value=1.0)]),
           'walkthrough':dict(title=upload['title'],timestamp=LIVE-7200,duration=20000,live_status='not_live',categories=['Gaming'],heatmap=[dict(start=9000,value=1.0)])}
  found,rejected,_=gta6.discover(self.s,gta6.settings(self.s),now=LIVE,read_source=self.reader(videos=[upload,video,short],details=details))
  self.assertEqual([c['id'] for c in found],['u9Ak0a715jQ'],'a short upload is usually someone else\'s compilation')
  self.assertEqual(found[0]['window']['start'],8970);self.assertNotIn('heatmap',found[0])
  self.assertIn('Nem élő adás',rejected[0]['reason'])
 def test_a_clip_beats_any_youtube_view_count(self):
  video=dict(id='u9Ak0a715jQ',url='https://www.youtube.com/watch?v=u9Ak0a715jQ',title='GTA 6 first time playing',duration=20000,view_count=50000000,channel='Fanum')
  details={'u9Ak0a715jQ':dict(title=video['title'],timestamp=LIVE-7200,duration=20000,live_status='was_live',heatmap=[dict(start=9000,value=1.0)]),'twc:BigChaseDddd':dict(categories=['Grand Theft Auto VI'],timestamp=LIVE-600)}
  found,_,_=gta6.discover(self.s,gta6.settings(self.s),now=LIVE,read_source=self.reader({'jynxzi':[self.twitch('BigChaseDddd',300,'jynxzi')]},[video],details))
  self.assertEqual([c['id'] for c in found],['twc:BigChaseDddd','u9Ak0a715jQ'])
 def research_job(self,**payload):
  from app_capabilities import roles
  jid=self.s.enqueue(roles(self.s,gta6.PROJECT)['research'],'x','chat',payload=dict(gta6=True,farm_research=True,requirements=gta6.FORMAT,**payload))
  return dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
 def test_research_hands_the_clip_to_production_with_the_brief_and_no_model(self):
  best=dict(self.twitch('BigChaseDddd',5000,'jynxzi',title='GTA 6 police chase'),platform='twitch',score=5000,categories=['Grand Theft Auto VI'])
  job=self.research_job()
  with patch('gta6.discover',return_value=([best],[],[])),patch('source_policy.submit',return_value=dict(run='r1',jobs={})) as submit,patch('studio.local_api') as model:
   out=clip_farm.run_research(self.s,job)
  handoff=submit.call_args.args[2];self.assertIn('jynxzi',out);model.assert_not_called()
  self.assertEqual((handoff['mode'],handoff['research']['kind'],handoff['sources'][0]['id']),('explicit','gta6_stream','twc:BigChaseDddd'))
  self.assertIn('No story spoilers',handoff['brief'])
  self.assertEqual(submit.call_args.args[3],dict(gta6.FORMAT,portrait_framing='fill',visual_analysis=False,subject_tracking=False),'a clip waits for no vision model')
  self.assertEqual(json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])['production_submission']['run'],'r1')
  self.s.db.execute("UPDATE jobs SET status='done'");self.s.db.commit()
  video=dict(id='u9Ak0a715jQ',url='https://www.youtube.com/watch?v=u9Ak0a715jQ',title='GTA 6 first time playing',channel='jynxzi',platform='youtube',score=9,duration=20000,window=dict(start=8892,duration=150,replayed=.9))
  with patch('gta6.discover',return_value=([video],[],[])),patch('source_policy.submit',return_value=dict(run='r2',jobs={})) as submit:
   clip_farm.run_research(self.s,self.research_job())
  self.assertEqual(submit.call_args.args[2]['sources'][0]['window']['start'],8892);self.assertIs(submit.call_args.args[3]['visual_analysis'],False,'a long stream waits for no vision model either')
 def test_no_clip_is_an_honest_failure_and_a_leak_link_is_refused(self):
  with patch('gta6.discover',return_value=([],[],['caseoh_: HTTP 500'])):
   with self.assertRaisesRegex(ValueError,'nincs új, ellenőrzött GTA 6-klip.*HTTP 500'):clip_farm.run_research(self.s,self.research_job())
  self.s.db.execute("UPDATE jobs SET status='done'");self.s.db.commit()
  job=self.research_job(link='https://clips.twitch.tv/LeakedOneCcc')
  with patch('gta6.runtime',return_value=clip('GTA 6 leaked gameplay')),patch('source_policy.submit') as submit:
   with self.assertRaisesRegex(ValueError,'Kiszivárgott'):clip_farm.run_research(self.s,job)
  submit.assert_not_called()
 def test_the_same_clip_is_not_used_twice(self):
  from source_policy import bundle,persist
  data=bundle(self.s,gta6.PROJECT,['https://clips.twitch.tv/BigChaseDddd'],'t',mode='explicit',metadata=[dict(id='twc:BigChaseDddd',title='x')])
  data['research']=dict(kind='gta6_stream');persist(self.s,gta6.PROJECT,data)
  self.assertTrue(gta6.used(self.s,'twc:BigChaseDddd'))
  found,_,_=gta6.discover(self.s,gta6.settings(self.s),now=LIVE,read_source=self.reader({'caseoh_':[self.twitch('BigChaseDddd',5000)]}))
  self.assertEqual(found,[])
 def test_the_team_is_set_for_gta6_once_and_stays_off(self):
  # The owner (2 Nov): this is an automation of the Clip Farm's agents, not a separate page.
  # The owner renamed three of them (TRENDI, DONI, ZOMB): an agent is found by its step, never by its name.
  self.s.db.execute("UPDATE agents SET name='TRENDI' WHERE name='Pulse' AND project=?",(gta6.PROJECT,));self.s.db.commit()
  self.assertTrue(gta6.ensure(self.s));agents={a['name']:a for a in self.s.rows('SELECT name,role,prompt,interval FROM agents WHERE project=?',(gta6.PROJECT,))}
  self.assertEqual(len(agents),len(gta6.AGENTS));self.assertEqual(agents['TRENDI']['role'],'GTA 6-klipkutató')
  for agent in agents.values():
   self.assertEqual(agent['interval'],0,agent['name']);self.assertRegex(agent['prompt'],'GTA 6|stream|broadcast|clip|source',agent['name'])
  self.assertIn('Grand Theft Auto VI',agents['TRENDI']['prompt']);self.assertIn('never a source',agents['TRENDI']['prompt'])
  self.assertIn('Never mention leaks',agents['Reach']['prompt']);self.assertIn('stays whole',agents['Scout']['prompt']);self.assertIn('facecam on top',agents['Pixel']['prompt'])
  self.assertIn('approval',agents['Vega']['prompt'])
  from app_capabilities import roles
  self.assertEqual(self.s.agent(roles(self.s,gta6.PROJECT)['research'])['name'],'TRENDI','the renewed role text does not lose the step')
  from automations import listing
  jobs={a['name']:a for a in listing(self.s,gta6.PROJECT)['automations']}
  for name in (gta6.AUTOMATION,gta6.REHEARSAL_AUTOMATION):self.assertFalse(jobs[name]['enabled'],'video automation stays off until the owner switches it on')
  self.assertIn('Twitch-csatornák',gta6.sources_path(self.s).read_text());self.assertIn(gta6.AUTOMATION,self.s.safe_path(gta6.PROJECT,'workspace/CLIP-FARM.md').read_text())
  self.s.db.execute("UPDATE agents SET prompt='saját' WHERE name='TRENDI' AND project=?",(gta6.PROJECT,));self.s.db.commit()
  self.assertFalse(gta6.ensure(self.s));self.assertEqual(self.s.db.execute("SELECT prompt FROM agents WHERE name='TRENDI' AND project=?",(gta6.PROJECT,)).fetchone()[0],'saját','the owner\'s later edit stays')
 def test_the_workshop_has_no_gta6_tab(self):
  self.assertEqual(project_apps.describe(self.s,gta6.PROJECT)['app'],'workspace');self.assertFalse((Path(gta6.__file__).parent/'web'/'gta6_ui.js').exists())
  with self.assertRaisesRegex(ValueError,'nincs saját alkalmazása'):project_apps.dispatch(self.s,gta6.PROJECT,'status')
 def test_launch_tells_the_owner_once_and_starts_nothing_by_itself(self):
  with patch('gta6.notify') as notify,patch('gta6.start') as start:
   gta6.tick(self.s,PRE);notify.assert_not_called()
   gta6._checked['at']=0;gta6.tick(self.s,LIVE);gta6._checked['at']=0;gta6.tick(self.s,LIVE+120)
  notify.assert_called_once();self.assertIn(gta6.AUTOMATION,notify.call_args.args[0]);start.assert_not_called()
  self.assertFalse(gta6.automation(self.s)['enabled'])
 def test_three_days_before_the_launch_it_lists_what_is_missing(self):
  soon=gta6.release_time(gta6.settings(self.s))-2*gta6.DAY
  with patch('gta6.notify') as notify,patch('gta6.readiness',return_value=[dict(ok=False,title='YouTube',fix='csatlakozz újra'),dict(ok=True,title='Lemez',fix='')]):
   gta6.tick(self.s,soon);gta6._checked['at']=0;gta6.tick(self.s,soon+120)
  notify.assert_called_once();self.assertIn('csatlakozz újra',notify.call_args.args[0]);self.assertNotIn('Lemez',notify.call_args.args[0])
 def test_an_armed_automation_wakes_at_the_launch_despite_earlier_quiet_searches(self):
  from workflow_health import failure_health
  gta6.ensure(self.s);job=gta6.automation(self.s);self.s.db.execute('UPDATE automations SET enabled=1,next_run=? WHERE id=?',(LIVE+9999,job['id']))
  for i,(status,error) in enumerate((('failed','Nincs klip.'),('cancelled','A beállított futási idő lejárt.'))):
   self.s.db.execute('INSERT INTO automation_runs VALUES(?,?,?,?,?,?,?,?)',('r'+str(i),job['id'],gta6.PROJECT,'[]',LIVE-3600-i,LIVE,status,error))
  self.s.db.commit();self.assertEqual(failure_health(self.s,job['id'],LIVE)['failures'],2)
  with patch('gta6.notify') as notify:gta6.tick(self.s,LIVE)
  self.assertEqual(failure_health(self.s,job['id'],LIVE)['failures'],0);self.assertIn('elkezdték',notify.call_args.args[0])
  self.assertLessEqual(self.s.db.execute('SELECT next_run FROM automations WHERE id=?',(job['id'],)).fetchone()[0],LIVE)
 def test_the_automation_runs_the_gta6_research_and_counts_verified_videos(self):
  import automations
  gta6.ensure(self.s);job=gta6.automation(self.s)
  out=automations.launch(self.s,gta6.PROJECT,job['id'],manual=True);row=self.s.db.execute("SELECT id,payload FROM jobs WHERE project=? AND json_extract(payload,'$.gta6')=1",(gta6.PROJECT,)).fetchone()
  payload=json.loads(row[1]);self.assertEqual(payload['automation_run'],self.s.db.execute('SELECT id FROM automation_runs WHERE automation=?',(job['id'],)).fetchone()[0])
  self.assertIsNot(payload['rehearsal'],True);self.assertEqual(out['jobs'],[row[0]])
  best=dict(self.twitch('BigChaseDddd',5000,'jynxzi',title='GTA 6 police chase'),platform='twitch',score=5000,categories=['Grand Theft Auto VI'])
  claimed=self.s.rows('SELECT * FROM jobs WHERE id=?',(row[0],))[0]
  with patch('gta6.discover',return_value=([best],[],[])),patch('source_policy.submit',return_value=dict(run='r1',jobs={})) as submit:clip_farm.run_research(self.s,claimed)
  self.assertEqual(submit.call_args.kwargs['origin'],'automation:'+payload['automation_run'])
 def test_a_gta_topic_typed_anywhere_goes_through_the_same_rules(self):
  out=clip_farm.start_research(self.s,gta6.PROJECT,'GTA 6 stream klipek');self.assertTrue(out['queued'])
  self.assertTrue(json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(out['job'],)).fetchone()[0])['gta6'])
  self.assertTrue(gta6.wants('Grand Theft Auto VI'));self.assertFalse(gta6.wants('időjárás a héten'))
 def test_readiness_points_to_the_automation(self):
  with patch('model_hub.online',return_value=True),patch('model_hub.ssd_hung',return_value=False):
   ids={i['id']:i for i in gta6.readiness(self.s)}
  self.assertEqual(set(ids),{'youtube','disk','model','speech','telegram','rehearsal'})
  self.assertFalse(ids['youtube']['ok']);self.assertIn('Kapcsolatok',ids['youtube']['fix']);self.assertIn(gta6.REHEARSAL_AUTOMATION,ids['rehearsal']['fix'])
 def test_rehearsal_counts_only_when_the_video_is_finished(self):
  job=gta6.start(self.s,rehearsal=True)['job']
  self.assertIs(json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0])['requirements']['publish_to_youtube'],False,'a rehearsal never enters the upload queue')
  row=lambda:self.s.db.execute('SELECT id,status,error,created,payload FROM jobs WHERE id=?',(job,)).fetchone()
  self.assertEqual(gta6.rehearsal_outcome(self.s,row()),'running')
  self.s.db.execute("UPDATE jobs SET status='done',payload=json_set(payload,'$.production_submission.run','r9') WHERE id=?",(job,));self.s.db.commit()
  self.assertEqual(gta6.rehearsal_outcome(self.s,row()),'running','the research handed over, no video yet')
  from clip_sources import schema
  schema(self.s);self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('r9',gta6.PROJECT,'q',json.dumps(dict(render=dict(saved='renders/a.mp4'),metadata=dict(title='T'))),0))
  from app_capabilities import roles
  step=self.s.enqueue(roles(self.s,gta6.PROJECT)['research'],'step','graph',payload=dict(run='r9',auto_step='verify'))
  self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(step,));self.s.db.commit()
  self.assertEqual(gta6.rehearsal_outcome(self.s,row()),'done')
  self.s.db.execute("UPDATE jobs SET status='failed',error='render' WHERE id=?",(step,));self.s.db.commit()
  self.assertEqual(gta6.rehearsal_outcome(self.s,row()),'failed')

if __name__=='__main__':unittest.main()
