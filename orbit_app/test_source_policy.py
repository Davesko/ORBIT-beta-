import datetime,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from studio import Studio
import source_policy as policy
from clip_sources import schema as clip_schema

def report():return dict(url='https://example.com/news/launch',title='Minecraft copper golem update launches',published_at=time.time()-100,content='New update launch details')
def video(identifier='abcdefghijk',age=100,title='Minecraft copper golem update launches'):
 return dict(id=identifier,url='https://www.youtube.com/watch?v='+identifier,title=title,description='The new copper golem launch',published_at=time.time()-age,duration=90)
def fixture(s):
 news=policy.remember_news(s,'universe',[report()]);v=video()
 return dict(id='a',topic='Minecraft update',published_at=time.time()-100,google_search_traffic=20000,verified_news=news,sample=dict(status='available',videos=[v]))

class SourcePolicyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Studio(Path(self.tmp.name));self.addCleanup(self.tmp.cleanup);self.addCleanup(self.s.db.close);clip_schema(self.s)
 def bundle(self,v=None):
  v=v or video();return policy.bundle(self.s,'universe',[v['url']],'Minecraft update',policy.remember_news(self.s,'universe',[report()]),mode='current_news',metadata=[v])
 def test_old_missing_future_and_invalid_dates_rejected(self):
  for meta in ({},{'upload_date':'20250819'},{'published_at':time.time()+10000},{'timestamp':float('nan')},{'published_at':'N/A'}):
   with self.assertRaises(ValueError):policy.require_fresh(meta)
  policy.require_fresh(dict(upload_date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')))
 def test_recent_reupload_unrelated_news_and_expired_news_rejected(self):
  for v in (video(age=365*86400),video(title='Basketball world championship finals')):
   v['description']='Unrelated footage' if 'Basketball' in v['title'] else v['description']
   with self.assertRaises(ValueError):self.bundle(v)
  with self.assertRaises(ValueError):policy.bundle(self.s,'universe',[video()['url']],'Minecraft',news=[dict(report(),published_at=time.time()-4*86400)],mode='current_news',metadata=[video()])
 def test_manual_explicit_old_links_remain_allowed(self):
  v=video(age=365*86400);b=policy.bundle(self.s,'universe',[v['url']],'Historical clip');self.assertEqual(b['mode'],'explicit')
 def test_research_news_must_be_dated_and_project_scoped(self):
  self.assertEqual(policy.remember_news(self.s,'universe',[dict(report(),published_at=None)]),[])
  policy.remember_news(self.s,'universe',[report()]);self.s.create_project('Other','Other','general','other')
  self.assertEqual(policy.news_for(self.s,'other',[report()['url']]),[])
 def test_multiple_links_persist_resolve_and_cannot_be_reserved_twice(self):
  vs=[video(),video('lmnopqrstuv')];b=policy.bundle(self.s,'universe',[v['url'] for v in vs],'Minecraft',policy.remember_news(self.s,'universe',[report()]),mode='current_news',metadata=vs)
  hid=policy.persist(self.s,'universe',b);self.assertEqual([v['url'] for v in policy.resolve(self.s,'universe',hid)['sources']],[v['url'] for v in vs])
  with self.assertRaises(ValueError):policy.persist(self.s,'universe',b)
  with self.assertRaises(ValueError):policy.resolve(self.s,'other',hid)
 def test_already_downloaded_source_is_never_selected_for_news_again(self):
  self.s.db.execute('INSERT INTO clip_downloads VALUES(?,?,?,?)',('universe','abcdefghijk','any',time.time()));self.s.db.commit()
  with self.assertRaises(ValueError):self.bundle()
 def test_failed_enqueue_releases_unstarted_reservation(self):
  with patch('execution_queue.submit_short',side_effect=ValueError('queue full')):
   with self.assertRaises(ValueError):policy.submit(self.s,'universe',self.bundle())
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM news_source_use').fetchone()[0],0)
 def test_execution_revalidates_expired_bundle(self):
  b=self.bundle();hid=policy.persist(self.s,'universe',b)
  with patch('source_policy.time.time',return_value=time.time()+4*86400):
   with self.assertRaises(ValueError):policy.resolve(self.s,'universe',hid)
 def test_source_step_downloads_only_handed_off_links_without_search_fallback(self):
  b=self.bundle();hid=policy.persist(self.s,'universe',b);aid=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];jid=self.s.enqueue(aid,'test');job=dict(id=jid,project='universe');data=dict(source_handoff=hid)
  with patch('clip_sources.find_clips',side_effect=AssertionError('must not search')),patch('clip_sources.download_clip',return_value=dict(metadata=video(),source_video='source.mp4')) as download:
   policy.source_step(self.s,self.s.agent(aid),job,data)
   self.assertEqual(download.call_args.args[2]['max_age_hours'],72);self.assertEqual(data['sources'][0]['metadata']['id'],'abcdefghijk')
  with patch('clip_sources.download_clip',side_effect=ValueError('unavailable')),patch('clip_sources.cached_sources',side_effect=AssertionError('no unrelated cache')):
   with self.assertRaises(ValueError):policy.source_step(self.s,self.s.agent(aid),job,dict(source_handoff=hid))
 def scheduled(self):
  import automations
  aid=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];auto=automations.save(self.s,'universe',dict(name='trend video',kind='agent',config=dict(agent=aid,prompt='Make current trend shorts')))
  rid=automations.launch(self.s,'universe',auto);return self.s.agent(aid),rid['jobs'][0],rid['run']
 def test_agent_automation_checks_direct_link_old_source_and_no_keyword_bypass(self):
  a,j,rid=self.scheduled();self.assertEqual(policy.policy_for_job(self.s,j),'current_news')
  with self.assertRaises(ValueError):self.s.tool(dict(a,tools=['start_short_production']),'start_short_production',dict(query='Minecraft highlights'),j)
  policy.remember_news(self.s,'universe',[report()])
  with patch('source_policy.lookup_videos',return_value=[video(age=365*86400)]),patch('execution_queue.submit_short',side_effect=AssertionError('must reject before queue')):
   with self.assertRaises(ValueError):policy.agent_submit(self.s,'universe',dict(query=video()['url'],news_urls=[report()['url']]),j)
 def test_agent_handoff_keeps_urls_and_automation_identity(self):
  a,j,rid=self.scheduled();policy.remember_news(self.s,'universe',[report()])
  with patch('source_policy.lookup_videos',return_value=[video()]),patch('execution_queue.submit_short',return_value=dict(job='queued')) as submit:
   policy.agent_submit(self.s,'universe',dict(query='Minecraft copper golem update',sources=[video()['url']],news_urls=[report()['url']]),j)
   self.assertEqual(submit.call_args.args[2],video()['url']);self.assertEqual(submit.call_args.args[4],'automation:'+rid);self.assertTrue(submit.call_args.kwargs['source_handoff'])
 def test_agent_web_search_requests_dated_news(self):
  a,j,_=self.scheduled()
  with patch('research.search',return_value=dict(results=[report()])) as search:
   self.s.tool(dict(a,tools=['web_search']),'web_search',dict(query='Minecraft copper update'),j)
   self.assertIs(search.call_args.kwargs['fresh_news'],True)
  self.assertEqual(len(policy.news_for(self.s,'universe',[report()['url']])),1)
 def test_agent_retry_does_not_start_second_production(self):
  a,j,rid=self.scheduled();self.s.enqueue(a['id'],'started','graph',payload=dict(automation_run=rid,auto_step='source',run='existing'))
  with patch('source_policy.bundle',side_effect=AssertionError('must return existing run')):
   result=policy.agent_submit(self.s,'universe',dict(query='Minecraft'),j)
  self.assertTrue(result['existing']);self.assertEqual(result['run'],'existing')
 def test_stale_download_rejected_before_media_bytes(self):
  import sys,types,clip_runtime
  dl=MagicMock();dl.extract_info.return_value=dict(id='abcdefghijk',title='old',duration=90,upload_date='20250819')
  ytdlp=types.ModuleType('yt_dlp');ytdlp.YoutubeDL=MagicMock();ytdlp.YoutubeDL.return_value.__enter__.return_value=dl
  utils=types.ModuleType('yt_dlp.utils');utils.download_range_func=MagicMock();ffmpeg=types.ModuleType('imageio_ffmpeg');ffmpeg.get_ffmpeg_exe=lambda:'ffmpeg'
  with patch.dict(sys.modules,{'yt_dlp':ytdlp,'yt_dlp.utils':utils,'imageio_ffmpeg':ffmpeg}),patch.dict('os.environ'):
   with self.assertRaises(ValueError):clip_runtime.execute(dict(operation='download',video_id='abcdefghijk',directory=self.tmp.name,node='node',start=0,duration=90,max_age_hours=72))
  dl.process_ie_result.assert_not_called()
 def test_retry_reuses_same_verified_interval_without_network_download(self):
  from clip_sources import download_clip
  aid=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];job=self.s.enqueue(aid,'retry');agent=dict(self.s.agent(aid),tools=['download_stream_clip'])
  path=self.s.safe_path('universe','sources/cached/source.mp4');path.parent.mkdir(parents=True);path.write_bytes(b'verified cached video')
  data=dict(metadata=video(),downloaded_start=0,downloaded_duration=90,project_file='sources/cached/source.mp4',source_handoff='same-handoff');path.with_name('source.json').write_text(json.dumps(data))
  self.s.db.execute('INSERT INTO clip_downloads VALUES(?,?,?,?)',('universe','abcdefghijk',str(path),time.time()));self.s.db.execute('INSERT INTO clip_candidates VALUES(?,?,?,?,?)',('candidate','universe','abcdefghijk',json.dumps(video()),time.time()));self.s.db.commit()
  with patch('clip_sources.network',side_effect=AssertionError('must reuse cached download')):
   result=download_clip(self.s,agent,dict(candidate_id='candidate',start=0,duration=90,max_age_hours=72,source_handoff='same-handoff'),job)
   self.assertTrue(result['reused_verified_download'])
   with self.assertRaises(ValueError):download_clip(self.s,agent,dict(candidate_id='candidate',start=0,duration=90,max_age_hours=72,source_handoff='another-handoff'),job)

class SourceQueryTests(unittest.TestCase):
 def test_event_query_omits_publisher_and_headline_padding(self):
  q=policy.video_search_query('Christina Applegate says she’s back at square one after misdiagnosis - Central Oregon Daily')
  self.assertIn('Christina Applegate',q);self.assertIn('misdiagnosis',q);self.assertNotIn('Oregon',q);self.assertNotIn('square',q)
