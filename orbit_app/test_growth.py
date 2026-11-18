import datetime,email.utils,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from growth import parse_feed,relevant,opportunity,settings,save,read,choose_topic,enqueue,tick,summary
from video_intelligence import scene_sample_times,select_vision_model

class GrowthTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Studio(Path(self.tmp.name));self.addCleanup(self.tmp.cleanup);self.addCleanup(self.s.db.close)
 def cache(self,items,age=0):
  p=self.s.safe_path('universe','insights/trends.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(dict(collected_at=time.time()-age,items=items)))
 def item(self,topic='Minecraft update',sample=True):
  from test_source_policy import fixture
  item=fixture(self.s);item['topic']=topic
  if not sample:item['sample']=dict(status='unavailable',videos=[])
  return item
 def test_rss_freshness_traffic_and_malformed_dates(self):
  date=email.utils.formatdate(time.time()-100,usegmt=True)
  raw=f'<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item><title>Minecraft</title><pubDate>{date}</pubDate><ht:approx_traffic>20K+</ht:approx_traffic></item><item><title>Old</title><pubDate>invalid</pubDate></item></channel></rss>'
  data=parse_feed(raw);self.assertEqual(len(data),1);self.assertEqual(data[0]['google_search_traffic'],20000)
 def test_settings_and_cache_are_project_scoped(self):
  self.s.create_project('Other','Other','general','other')
  save(self.s,'universe',dict(enabled=True,country='GB'));self.assertFalse(settings(self.s,'other')['enabled']);self.assertEqual(read(self.s,'other')['items'],[])
  for data in (dict(interval_minutes=1),dict(country='ZZ'),dict(enabled='yes')):
   with self.assertRaises(ValueError):save(self.s,'universe',data)
 def test_no_gap_score_without_competition_evidence(self):
  result=opportunity(self.item(),dict(status='unavailable',videos=[]));self.assertIsNone(result['opportunity_score'])
  result=opportunity(self.item(),dict(status='available',videos=[]));self.assertIsNone(result['opportunity_score']);self.assertIn('No combined score',result['reason'])
 def test_no_stale_or_duplicate_topic_and_no_source_no_production(self):
  self.cache([self.item()],age=90000)
  with self.assertRaises(ValueError):choose_topic(self.s,'universe')
  self.cache([self.item(sample=False)])
  with self.assertRaises(ValueError):choose_topic(self.s,'universe')
  self.cache([self.item()]);self.assertEqual(choose_topic(self.s,'universe',reserve=True)['query'],'https://www.youtube.com/watch?v=abcdefghijk')
  with self.assertRaises(ValueError):choose_topic(self.s,'universe')
 def test_research_is_durable_deduplicated_and_scheduler_throttled(self):
  save(self.s,'universe',dict(enabled=True));tick(self.s);tick(self.s)
  jobs=self.s.rows("SELECT * FROM jobs WHERE kind='growth_research'");self.assertEqual(len(jobs),1)
  self.assertEqual(enqueue(self.s,'universe')['job'],jobs[0]['id'])
  self.assertEqual(self.s.rows("SELECT name FROM agents WHERE role='Trend researcher'")[0]['name'],'Pulse')
 def test_summary_missing_is_not_zero(self):
  r=summary(dict(videos=[dict(views=10,engaged_views=None),dict(views=20,engaged_views=None)]));self.assertEqual(r['totals']['views'],30);self.assertIsNone(r['totals']['engaged_views'])
 def test_topic_filter_uses_words_not_substrings(self):
  self.assertTrue(relevant('Minecraft update','minecraft, kai cenat'));self.assertFalse(relevant('Complicated foreign name','cat'))

class SceneSamplingTests(unittest.TestCase):
 def test_real_scene_coverage_is_bounded_ordered_and_has_context(self):
  times=scene_sample_times([(0,4),(4,10)],10);self.assertEqual(times,sorted(set(times)));self.assertLessEqual(len(times),12);self.assertIn(2,times);self.assertIn(7,times)
  self.assertTrue(all(0<=x<10 for x in times))
  times=scene_sample_times([(i,i+1) for i in range(100)],100);self.assertEqual(len(times),12);self.assertGreater(times[-1],95)
 def test_local_vision_does_not_load_27b_on_top_of_media_memory(self):
  chosen=select_vision_model([dict(name='qwen3.8:27b',size=18000000000,port=11435),dict(name='qwen3.5:9b',size=7000000000,port=11435)])
  self.assertEqual(chosen['name'],'qwen3.5:9b')
  with self.assertRaises(ValueError):select_vision_model([dict(name='qwen3-embedding:0.6b')])

class TrendAutomationTests(unittest.TestCase):
 def test_failed_queue_does_not_consume_topic_success_does(self):
  import automations
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));agent=s.rows('SELECT id FROM agents LIMIT 1')[0]['id'];growth_job=s.enqueue(agent,'fixture')
   from test_source_policy import fixture
   p=s.safe_path('universe','insights/trends.json');p.parent.mkdir();p.write_text(json.dumps(dict(collected_at=time.time(),items=[fixture(s)])))
   with patch('autonomous.role_agents',return_value={}):
    aid=automations.save(s,'universe',dict(name='Trend',kind='shorts',config=dict(topic_source='trends',query='Fresh verified project trend')))
    with patch('execution_queue.submit_short',side_effect=ValueError('queue full')):
     with self.assertRaises(ValueError):automations.launch(s,'universe',aid)
    self.assertEqual(s.db.execute('SELECT count(*) FROM growth_topics').fetchone()[0],0)
    with patch('execution_queue.submit_short',return_value=dict(job=growth_job)) as submit:
     automations.launch(s,'universe',aid)
     self.assertEqual(submit.call_args.args[2],'https://www.youtube.com/watch?v=abcdefghijk')
    self.assertEqual(s.db.execute('SELECT count(*) FROM growth_topics').fetchone()[0],1)
   s.db.close()
