import json,time,unittest
from unittest.mock import patch
from pathlib import Path
from execution_queue import DeferredExecution
from content_survey import survey,shortlist,candidates
from story_director import check_story

class FullContentTests(unittest.TestCase):
 def setUp(self):
  from test_supervisor_runtime import SupervisorTests
  from autonomous import plan_schema
  self.f=SupervisorTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s;plan_schema(self.s)
  self.style=dict(min_seconds=20,max_seconds=50,target_seconds=40,min_shots=2,max_shots=12,max_shot_seconds=12,length_policy='adaptive')
  self.catalog=[dict(id=i,source=0,start=i*10,end=i*10+5,seconds=5,text='A complete original statement number '+str(i)+'.',boundary='sentence',opening_visible=True) for i in range(220)]
  aid=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];self.jid=self.s.enqueue(aid,'Full source','graph',payload=dict(run='survey',auto_step='selection'));self.job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(self.jid,)).fetchone())
  self.data=dict(style=self.style);self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('survey','universe','Whole source',json.dumps(self.data),time.time()));self.s.db.commit()
 def test_every_unit_including_tail_is_surveyed_once_before_selection(self):
  seen=[];calls=[]
  def ask(s,j,p,v):
   calls.append(v)
   if 'source_units' in v:
    ids=[u['id'] for u in v['source_units']];seen.extend(ids)
    return dict(summary='A section of the complete original source.',rankings=[dict(id=i,importance=5 if i in (0,219) else 2,role='outcome' if i==219 else 'context' if i==0 else 'aside') for i in ids])
   if 'max_seconds' not in v:
    ids=[i for section in v['sections'] for i in section['ids']]
    return dict(summary='Combined source context and actual ending.',ids=list(dict.fromkeys([ids[0],ids[-1]])))
   return dict(main_context='The original premise must be preserved.',core_message='The central outcome is at the very end.',required_ids=[0,219],outcome_ids=[219],ranked_ids=[0,219]+[u['id'] for u in v['units'] if u['id'] not in (0,219)][:3],omission_policy='Remove repeated explanations and peripheral material first.')
  for _ in range(30):
   try:state=survey(self.s,self.job,self.data,self.catalog,ask);break
   except DeferredExecution:self.data=json.loads(self.s.db.execute('SELECT data FROM short_runs WHERE id=\'survey\'').fetchone()[0])
  else:self.fail('Survey failed to complete')
  self.assertEqual(seen,list(range(220)));self.assertEqual(state['reviewed_units'],220)
  short,director=shortlist(self.catalog,state)
  self.assertLessEqual(len(short),48);self.assertIn(219,[u['global_id'] for u in short])
  options=candidates(director,short,self.style);self.assertTrue(options)
  from editorial import feasible_story
  for option in options:
   plan,_=feasible_story(option,short,self.style);check_story(plan,director,short)
   self.assertTrue({0,219}<={short[i]['global_id'] for i in plan['unit_ids']});self.assertLessEqual(plan['duration'],50)
 def test_missing_unit_is_not_accepted_as_complete_survey(self):
  def ask(*args):return dict(summary='An incomplete map',rankings=[dict(id=0,importance=5,role='context')])
  with self.assertRaises(ValueError):survey(self.s,self.job,self.data,self.catalog,ask)
  self.assertFalse(self.data['content_survey']['batches'])
 def test_full_catalog_keeps_all_source_sections(self):
  from editorial import unit_catalog
  transcript=dict(segments=[dict(start=i*5,end=i*5+4,text='This is a complete independent original sentence.') for i in range(120)])
  tracks=[dict(source=dict(duration=600),transcript=transcript)]
  self.assertLessEqual(len(unit_catalog(tracks,self.style)),48)
  full=unit_catalog(tracks,self.style,full=True);self.assertGreater(len(full),48);self.assertGreater(full[-1]['start'],500)
 def test_partial_cached_excerpt_cannot_replace_complete_source(self):
  from clip_sources import schema,cached_sources
  schema(self.s);p=self.s.safe_path('universe','sources/sample/source.mp4');p.parent.mkdir(parents=True);p.write_bytes(b'actual local file')
  data=dict(project_file='sources/sample/source.mp4',downloaded_start=0,downloaded_duration=180,metadata=dict(id='CIY9PO0IODU',duration=2527),coverage=dict(complete=False))
  p.with_name('source.json').write_text(json.dumps(data));self.s.db.execute('INSERT INTO clip_downloads VALUES(?,?,?,?)',('universe','CIY9PO0IODU',str(p),time.time()));self.s.db.commit()
  self.assertEqual(len(cached_sources(self.s,'universe','https://www.youtube.com/watch?v=CIY9PO0IODU')),1)
  self.assertEqual(cached_sources(self.s,'universe','https://www.youtube.com/watch?v=CIY9PO0IODU',full_source=True),[])
 def test_full_summary_does_not_drop_essential_outcome(self):
  d=dict(status='full_content_summary',required_ids=[0,219],ending_ids=[219])
  with self.assertRaises(ValueError):check_story(dict(unit_ids=[0,1,2]),d,self.catalog)
  check_story(dict(unit_ids=[0,130,219]),d,self.catalog)
 def test_production_uses_full_survey_then_reviews_the_shortlisted_summary(self):
  from autonomous import run_step
  from short_style import DEFAULT
  from editorial import unit_catalog
  style=dict(DEFAULT,editing='single',min_seconds=15,max_seconds=50,target_seconds=40,length_policy='adaptive')
  transcript=dict(segments=[dict(start=i*5,end=i*5+4,text='A complete factual original sentence number '+str(i)+'.') for i in range(100)])
  path=self.s.safe_path('universe','transcript.json');path.write_text(json.dumps(transcript))
  track=dict(source=dict(source_video='original.mp4',duration=500),transcript_file='transcript.json',subtitle='source.srt')
  catalog=unit_catalog([dict(track,transcript=transcript)],style,[{}],full=True);last=len(catalog)-1
  state=dict(overview=dict(main_context='Actual complete source premise.',core_message='Actual central source outcome.',required_ids=[0,last],outcome_ids=[last],ranked_ids=[0,last,10,20,30],omission_policy='Remove repetition and side issues first.'))
  data=dict(content_scope='full_content',query='Whole source',source_quality={},style=style,source=track['source'],tracks=[track],visual_analysis=[{}])
  self.s.db.execute('UPDATE short_runs SET data=? WHERE id=\'survey\'',(json.dumps(data),));self.s.db.commit()
  def answer(s,j,p,v):
   c=v['candidates'][0]
   return dict(approved=True,candidate_id=0,hook_candidates=[dict(id=c['hook'],reason='Actual central context')],beats=[dict(id=c['sequence'][-1],beat='payoff',reason='Original result')],humor_type='none',payoff_evidence='The source outcome is preserved.')
  with patch('source_quality.annotate'),patch('semantic_boundaries.enrich'),patch('content_survey.survey',return_value=state) as read,patch('autonomous.ask_json',side_effect=answer):run_step(self.s,self.job)
  self.assertGreater(len(read.call_args.args[3]),48)
  result=json.loads(self.s.db.execute('SELECT data FROM short_runs WHERE id=\'survey\'').fetchone()[0])['montage']['content_summary']
  self.assertIn(last,result['selected_global_ids']);self.assertEqual(result['analyzed_units'],len(catalog))
