import json,unittest
from unittest.mock import patch
from conversation_intake import query
from editorial import cover_sources,feasible_story
from short_style import DEFAULT
def unit(i,source,start,text,**extra):return dict(id=i,source=source,start=start,end=start+5,seconds=5,text=text,boundary='sentence',**extra)
class IntakeTests(unittest.TestCase):
 def test_real_operator_prompts_keep_the_streamer(self):
  self.assertEqual(query('készíts egy youtube shorts best moments videót ISHOWSPEED - ről , egy mostani streamjéről.'),'ISHOWSPEED latest stream best moments')
  self.assertEqual(query('készíts egy youtube shorts best moments ISHOWSPEED  videót, egy 2026 os streamről.'),'ISHOWSPEED 2026 stream best moments')
  self.assertEqual(query('készíts egy youtube shorts best moments videót ishowspeed - ről , egy mostani streamjéről.'),'ishowspeed latest stream best moments')
  self.assertEqual(query('generálj shorts videót MrBeast-ről'),'MrBeast highlights')
 def test_generic_nouns_are_not_subjects(self):
  self.assertIsNone(query('készíts shorts videót a mostani streamről'))
  self.assertIsNone(query('Generálj egy trend alapján egy youtube shorts videót.'))
class MultiSourceTests(unittest.TestCase):
 def setUp(self):
  from test_supervisor_runtime import SupervisorTests
  self.fixture=SupervisorTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.s=self.fixture.s;self.pid=self.fixture.shorts()
 def test_two_links_and_brief_are_all_forwarded(self):
  from supervisor_runtime import explicit_short_plan
  prompt='https://www.youtube.com/watch?v=7p5LxFdc-Qg\nhttps://www.youtube.com/watch?v=LnUJj_B88OI\n\nezt a kettő videót vágd össze egy youtube shorts videóra. Cinematic , hangeffektekkel.'
  action=explicit_short_plan(self.s,'universe',prompt,True)[-1]
  self.assertEqual(len(action['sources']),2);self.assertIn('Cinematic',action['query']);self.assertNotIn('https',action['query'])
  single=explicit_short_plan(self.s,'universe','vágd meg shorts videóra: https://www.youtube.com/watch?v=7p5LxFdc-Qg',True)[-1]
  self.assertNotIn('sources',single);self.assertIn('youtube.com',single['query'])
class CoverSourcesTests(unittest.TestCase):
 def test_missing_source_gets_its_strongest_moment(self):
  catalog=[unit(i,0,i*5.0,'Line '+str(i)+'.') for i in range(8)]+[unit(8,1,0,'Quiet intro.',hook_score=1),unit(9,1,5,'Why did the whole engine suddenly explode?',hook_score=6),unit(10,1,10,'Ok.',hook_score=9)]
  style=dict(DEFAULT,min_seconds=20,max_seconds=30,min_shots=3,max_shots=12,length_policy='strict',require_all_sources=True)
  plan,_=feasible_story(dict(hook=2,sequence=[3,4,5,6,7]),catalog,style)
  self.assertIn(9,plan['unit_ids']);self.assertLessEqual(plan['duration'],30);self.assertEqual(plan['unit_ids'][0],2)
 def test_unusable_source_is_reported(self):
  catalog=[unit(0,0,0,'A.'),unit(1,0,5,'B.'),unit(2,1,0,'cont',starts_mid_sentence=True)]
  with self.assertRaises(ValueError):cover_sources([0,1],catalog,dict(DEFAULT,max_seconds=30,max_shots=10))
class YieldTests(unittest.TestCase):
 def setUp(self):
  from test_supervisor_runtime import SupervisorTests
  self.fixture=SupervisorTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.s=self.fixture.s
 def test_business_cycle_keeps_budget_while_video_is_produced(self):
  import missions,venture,time
  missions.schema(self.s);venture.configure(self.s,dict(enabled=True));missions.tick(self.s)
  run=self.s.rows('SELECT id,deadline FROM orbit_mission_runs')[0]
  self.s.db.execute('UPDATE orbit_mission_runs SET deadline=? WHERE id=?',(time.time()+5,run['id']));self.s.db.commit()
  aid=self.s.rows('SELECT id FROM agents LIMIT 1')[0]['id'];self.s.enqueue(aid,'render','graph',payload=dict(run='x',auto_step='render'))
  self.assertTrue(missions.production_active(self.s));missions.tick(self.s)
  after=self.s.rows('SELECT status,deadline FROM orbit_mission_runs')[0]
  self.assertEqual(after['status'],'running');self.assertGreater(after['deadline'],time.time()+25*60)
 def test_worker_runs_business_agents_in_their_own_yielding_lane(self):
  from pathlib import Path
  source=(Path(__file__).parent/'worker.py').read_text()
  self.assertIn("args=(('mission_agent',),True)",source);self.assertNotIn("'model_evaluation','mission_agent'",source)
if __name__=='__main__':unittest.main()
