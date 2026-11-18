import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from clip_farm import configure,PROJECT,start_research
from autonomous import role_agents
from assembly_plan import build

class FarmTests(unittest.TestCase):
 def test_isolated_project_has_full_team_disabled_schedule_and_keeps_user_project(self):
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close)
   original=s.project('universe');result=configure(s)
   self.assertTrue(result['created']);self.assertEqual(s.project('universe'),original)
   self.assertEqual(len(role_agents(s,PROJECT)),8)
   agents=s.rows('SELECT * FROM agents WHERE project=?',(PROJECT,))
   self.assertEqual(len(agents),9);self.assertTrue(all(a['model']=='auto' and a['interval']==0 for a in agents))
   self.assertEqual(len(s.rows('SELECT * FROM rooms WHERE project=? AND archived=0',(PROJECT,))),5)
   a=s.db.execute('SELECT * FROM automations WHERE project=?',(PROJECT,)).fetchone()
   self.assertFalse(a['enabled']);self.assertEqual(json.loads(a['config'])['source_policy'],'current_news')
   self.assertEqual(s.rows('SELECT * FROM jobs WHERE project=?',(PROJECT,)),[])
   self.assertFalse(configure(s)['created']);self.assertEqual(len(s.rows('SELECT * FROM agents WHERE project=?',(PROJECT,))),9)
 def test_main_start_researches_first_and_preserves_requested_style(self):
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close);configure(s)
   from bridge import dispatch
   from source_policy import policy_for_job
   result=dispatch(dict(action='short_start',project=PROJECT,query='2okos friss stream esemény',requirements=dict(language='hu')),s)
   job=s.db.execute('SELECT * FROM jobs WHERE id=?',(result['job'],)).fetchone()
   self.assertEqual(s.agent(job['agent'])['name'],'Pulse');self.assertEqual(policy_for_job(s,job['id']),'current_news')
   self.assertEqual(json.loads(job['payload'])['requirements']['language'],'hu')
   self.assertEqual(start_research(s,PROJECT,'Another topic')['job'],result['job'])
   self.assertIsNone(start_research(s,'universe','Topic'))
 def test_research_without_render_does_not_count_as_produced_video(self):
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close);setup=configure(s)
   from automations import launch,reconcile
   launched=launch(s,PROJECT,setup['automation']);job=s.claim(('chat','scheduled'));self.assertIsNotNone(job)
   s.finish(job,'No fresh eligible source.');reconcile(s)
   row=s.db.execute('SELECT * FROM automation_runs WHERE id=?',(launched['run'],)).fetchone()
   self.assertEqual(row['status'],'failed');self.assertIn('napi videócélba',row['error'])
 def test_research_is_visible_before_production_and_empty_results_fail_honestly(self):
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close);configure(s)
   result=start_research(s,PROJECT,'Victoria Secret show')
   snap=s.snapshot(PROJECT);self.assertTrue(any(r['jobs'][0]['id']==result['job'] for r in snap['workflow_runs']))
   with patch('research.search',return_value=dict(results=[])):
    s.run_next(('chat',))
   row=s.db.execute('SELECT status,error FROM jobs WHERE id=?',(result['job'],)).fetchone()
   self.assertEqual(row['status'],'failed');self.assertIn('Nem készült videó',row['error'])
   self.assertTrue(s.rows('SELECT id FROM artifacts WHERE project=?',(PROJECT,)))
 def test_evidence_handoff_starts_team_without_model_tool_loop(self):
  with tempfile.TemporaryDirectory() as root,patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts)):
   s=Studio(Path(root));self.addCleanup(s.db.close);configure(s)
   result=start_research(s,PROJECT,'Victoria Secret show');job=s.claim(('chat',))
   report=dict(url='https://example.com/story',title='Victoria Secret show opens',content='Victoria Secret event',published_at=__import__('time').time())
   from clip_farm import run_research
   # Live Google Trends changed which searches ran (and so the order of the mocked tool answers) from day to day.
   with patch.object(s,'tool',side_effect=[dict(results=[report]),dict(results=[report]),[dict(id='abcdefghijk',url='https://www.youtube.com/watch?v=abcdefghijk')]]),patch('source_policy.bundle',return_value=dict(topic=report['title'])),patch('source_policy.submit',return_value=dict(run='real-production',jobs={'source':'source-job'})) as submit,\
        patch('google_trends_source.seeds',return_value=dict(items=[])):
    answer=run_research(s,job)
   self.assertIn('átadva',answer);self.assertEqual(submit.call_count,1)
   saved=json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(result['job'],)).fetchone()[0]);self.assertEqual(saved['production_submission']['run'],'real-production')
 def test_render_handoff_preserves_evidence_and_rejects_drift(self):
  data={'query':'a real event','tracks':[{'source':{'source_video':'sources/a.mp4','duration':20,'metadata':{'url':'https://example.com/a'}}}], 'montage':{'shots':[{'source':0,'start':2,'end':10,'beat':'hook'}]}}
  request={'duration':8,'segments':[{'source_video':'sources/a.mp4','start':2,'duration':8}]}
  plan=build(data,request,[{'segments':[{'start':2,'end':5,'text':'Real speech.'}]}])
  self.assertEqual(plan['timeline'][0]['speech'][0]['text'],'Real speech.');self.assertEqual(plan['request'],request)
  invalid=copy.deepcopy(request);invalid['segments'][0]['source_video']='unrelated.mp4'
  with self.assertRaises(ValueError):build(data,invalid,[{}])
  invalid=copy.deepcopy(request);invalid['duration']=9
  with self.assertRaises(ValueError):build(data,invalid,[{}])

class ResearchIntentTests(unittest.TestCase):
 def test_breaking_news_typo_is_general_news_not_brakes(self):
  from clip_farm import research_spec
  spec=research_spec('Braking news');self.assertFalse(spec['gaming']);self.assertEqual(spec['terms'],[]);self.assertTrue(all('braking' not in q for q in spec['queries']))
 def test_streamer_gaming_rejects_netflix_but_accepts_gaming_event(self):
  from clip_farm import research_spec,report_matches
  spec=research_spec('streamer gaming')
  self.assertFalse(report_matches(dict(title='Netflix film chief exits as streamer shuffles ranks',content='Netflix streaming movies'),spec))
  self.assertTrue(report_matches(dict(title='Twitch gaming creators announce new charity tournament',content='gaming esports event'),spec))
