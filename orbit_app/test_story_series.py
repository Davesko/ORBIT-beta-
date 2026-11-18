import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import story_animation,story_series as ss,trend_radar as tr,story_episode

class SeriesTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name));self.addCleanup(self.s.db.close)
  self.pid=story_animation.separate(self.s) or story_animation.project(self.s)
 def mira(self,**kw):
  return dict(dict(name='Mira',look='short round human, pink round head, black bob hair, yellow raincoat, big round glasses, bouncy',persona='Mira, the upstairs neighbour, a cheerful know-it-all who corrects everyone and is wrong half the time.',voice=dict(voice='af_bella',speed=1.0,pitch=0)),**kw)
 def test_default_bible_is_the_projects_pair_and_main_pair_stars(self):
  b=ss.bible(self.s,self.pid);self.assertEqual([c['name'] for c in b['characters']],['Krix','Dale'])
  c=ss.cast_for(self.s,self.pid,'csinálj egy videót');self.assertEqual(c['ids'],['krix','dale']);self.assertTrue(c['lead'].startswith('Krix: '))
  self.assertTrue(story_episode.art_valid(dict(lead=c['lead'],support=c['support'],world='x'*12,palette='y'*12,signature_prop='z'*12)))
 def test_third_character_joins_and_a_request_naming_her_casts_her(self):
  ss.save_character(self.s,self.pid,self.mira())
  self.assertEqual(len(ss.bible(self.s,self.pid)['characters']),3)
  c=ss.cast_for(self.s,self.pid,'Készíts egy videót Mira és Dale vitájáról');self.assertEqual(c['names'],dict(lead='Mira',support='Dale'))
  self.assertNotEqual(c['voices']['lead']['voice'],c['voices']['support']['voice'])
  one=ss.cast_for(self.s,self.pid,'Mira elmeséli a napját');self.assertEqual(one['ids'],['mira','krix'])
  tagged=ss.cast_for(self.s,self.pid,'[ORBIT-RUN] videó [szereplők:dale,mira]');self.assertEqual(tagged['ids'],['dale','mira'])
  self.assertEqual(ss.cast_for(self.s,self.pid,'bármi',['krix','mira'])['ids'],['krix','mira'])
  with self.assertRaises(ValueError):ss.save_character(self.s,self.pid,self.mira())
  with self.assertRaises(ValueError):ss.save_character(self.s,self.pid,dict(name='X',look='short',persona='p',voice=dict(voice='nope')))
  ss.remove_character(self.s,self.pid,'mira')
  with self.assertRaises(ValueError):ss.remove_character(self.s,self.pid,'krix')
 def test_format_from_request_tag_words_or_rotation(self):
  b=ss.bible(self.s,self.pid)
  self.assertEqual(ss.pick_format(b,'csinálj videót'),'gag')      # the visual gag is the default until the owner picks one
  ss.save_settings(self.s,self.pid,dict(formats=dict(fixed='bro_logic')));self.assertEqual(ss.pick_format(ss.bible(self.s,self.pid),'csinálj videót'),'bro_logic')
  self.assertEqual(ss.pick_format(b,'csinálj videót a mai hírekből'),'news')
  self.assertEqual(ss.pick_format(b,'Top 3 legrosszabb reggeli'),'ranking')
  self.assertEqual(ss.pick_format(b,'videó [formátum:debate]'),'debate')
  ss.save_settings(self.s,self.pid,dict(formats=dict(mode='rotate',enabled=['bro_logic','news'])))
  b=ss.bible(self.s,self.pid);self.assertEqual([ss.pick_format(b,'videó',n) for n in range(3)],['bro_logic','news','bro_logic'])
  self.assertIs(ss.guidance('bro_logic'),story_episode.MEME_GUIDANCE);self.assertIn('today\'s news',ss.guidance('news'));self.assertIn('VISUAL GAG',ss.guidance('gag'));self.assertIn('sneak',ss.acting('gag'))
 def test_tags_are_stripped_from_the_request(self):
  raw='[ORBIT-RUN] Készíts egy új saját animációs shortot: a reggeli kávé [formátum:news] [szereplők:krix,dale] [trend:Outlook is down]'
  self.assertEqual(ss.tags(raw),{'formátum':'news','szereplők':'krix,dale','trend':'Outlook is down'})
  self.assertEqual(story_animation.owner_topic(ss.strip(raw)),'a reggeli kávé')
  self.assertEqual(story_animation.owner_topic(ss.strip('[ORBIT-RUN] Készíts egy új saját animációs shortot. A témát a friss trendekből válaszd.')) if not story_animation.autopilot_brief('A témát a friss trendekből válaszd.') else '','')
 def test_idea_context_carries_cast_format_lore_and_memory(self):
  ss.save_settings(self.s,self.pid,dict(lore=['Krix lives in Dale\'s flat and pays no rent.']))
  hook=story_animation.agent_ids(self.pid)['hook']
  jid=self.s.enqueue(hook,'x','graph',payload=dict(story_step='hook',story_brief='b'));self.s.db.execute("UPDATE jobs SET status='done',finished=?,result=? WHERE id=?",(time.time(),json.dumps(dict(premise='Krix asks why a pizza box is square',payoff_caption='Because the truck is',trend='pizza')),jid));self.s.db.commit()
  job=dict(project=self.pid,agent=hook,payload=json.dumps(dict(story_brief='csinálj egy videót a mai hírekből')))
  ctx=story_animation.episode_ideas(self.s,job,'csinálj egy videót a mai hírekből')
  self.assertEqual(ctx['series_format'],'news');self.assertEqual(ctx['cast_ids'],['krix','dale']);self.assertEqual(ctx['series_lore'],['Krix lives in Dale\'s flat and pays no rent.'])
  self.assertEqual(ctx['series_memory'][0]['about'],'Krix asks why a pizza box is square');self.assertIn('Krix',ctx['characters']['lead'])
 def test_episode_from_the_studio_page_writes_its_choices_into_the_request(self):
  with self.assertRaises(ValueError):ss.start_episode(self.s,self.pid,dict(format='news'))
  out=ss.start_episode(self.s,self.pid,dict(format='news',trend='League of Legends new dawn',cast=['dale','krix']))
  brief=json.loads(self.s.rows("SELECT payload FROM jobs WHERE json_extract(payload,'$.story_step')='hook'")[0]['payload'])['story_brief']
  self.assertEqual(ss.tags(brief),{'formátum':'news','szereplők':'dale,krix','trend':'League of Legends new dawn'});self.assertTrue(out['run'])
  with self.assertRaises(ValueError):ss.start_episode(self.s,self.pid,dict())      # one episode at a time
 def test_studio_project_has_the_series_page(self):
  import project_apps
  self.assertEqual(project_apps.describe(self.s,self.pid)['app'],'series')
  snap=project_apps.dispatch(self.s,self.pid,'series_snapshot',dict(project=self.pid))['result']
  self.assertEqual(len(snap['characters']),2);self.assertEqual(len(snap['format_list']),7);self.assertFalse(snap['busy'])

RAW=[dict(topic='outlook down',headlines=['Microsoft Outlook is down for thousands of users'],urls=['https://example.com/a'],source='Google Trends US',weight=3,searches=200000),
     dict(topic='Outlook outage hits Microsoft users',headlines=['Outlook outage hits Microsoft users'],urls=[],source='Google News',weight=1,hint='tech'),
     dict(topic='Outlook',headlines=[],urls=[],source='Wikipedia (legolvasottabb)',weight=.8),
     dict(topic='arsenal vs chelsea',headlines=['Arsenal 2-1 Chelsea'],urls=[],source='Google Trends GB',weight=3),
     dict(topic='man dies in crash',headlines=['x'],urls=[],source='Google News',weight=1),
     dict(topic='Some Old Page',headlines=[],urls=[],source='Wikipedia (legolvasottabb)',weight=.8),
     dict(topic='++CLIP XXX viral video 737332258',headlines=[],urls=[],source='Google News',weight=1)]
PAGE=dict(text='Sign up for our newsletter today and never miss a story again. Microsoft said the Outlook outage began at 9 a.m. and affected about 37,000 users worldwide. '
               'Engineers rolled back a configuration change and Outlook service returned within three hours. The weather was nice.')

class RadarTests(unittest.TestCase):
 def test_same_event_merges_across_sources_and_junk_is_dropped(self):
  d=tr.build(RAW,reader=lambda url:PAGE,now=1.0)
  self.assertEqual(len(d['items']),1);i=d['items'][0]
  self.assertEqual(len(i['sources']),3);self.assertEqual(i['kind'],'tech')
  self.assertEqual(len(i['facts']),1);self.assertIn('37,000',i['facts'][0]);self.assertEqual(i['read_from'],['https://example.com/a'])
 def test_writer_gets_facts_and_no_used_trend(self):
  items=tr.build(RAW,reader=lambda url:PAGE)['items']
  w=tr.for_writer(items);self.assertEqual(w[0]['trend'],'outlook down');self.assertIn('Microsoft Outlook is down for thousands of users',w[0]['what_happened']);self.assertTrue(any('37,000' in x for x in w[0]['what_happened']))
  self.assertEqual(tr.for_writer(items,['Outlook down']),[])
  self.assertEqual(tr.match(items,'the Outlook outage')['topic'],'outlook down');self.assertIsNone(tr.match(items,'a new pizza'))
 def test_refresh_keeps_the_last_list_and_never_reads_the_web_in_tests(self):
  with tempfile.TemporaryDirectory() as d:
   s=type('S',(),{'root':Path(d)})()
   with patch.object(tr,'collect',side_effect=AssertionError('network')):self.assertEqual(tr.refresh(s)['items'],[])
   with patch.object(tr,'collect',return_value=(RAW,{})),patch.object(tr,'read_facts',return_value=([],[])):self.assertEqual(len(tr.refresh(s,force=True)['items']),1)
   with patch.object(tr,'collect',return_value=([],dict(news='down'))):self.assertEqual(len(tr.refresh(s,force=True)['items']),1)

if __name__=='__main__':unittest.main()
