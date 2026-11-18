import unittest
from editorial import complete_ending,expand_context,feasible_story,hook_signals
from content_survey import rankings,repair_overview
from short_style import DEFAULT
def unit(i,start,end,text,source=0,**extra):return dict(id=i,source=source,start=start,end=end,seconds=round(end-start,2),text=text,boundary='sentence',**extra)
class StoryAssemblyTests(unittest.TestCase):
 def setUp(self):
  texts=['Today we test the new car.','It costs 30000 dollars.','The engine sounds strange.','Why is it smoking?','Because the oil was empty.','So we fixed it.','And it finally drives perfectly.','Subscribe for more.']
  self.catalog=[unit(i,i*6.0,i*6.0+5.5,t) for i,t in enumerate(texts)]
  self.style=dict(DEFAULT,min_seconds=30,max_seconds=45,target_seconds=38,min_shots=3,max_shots=12,length_policy='strict')
 def test_short_strict_story_is_expanded_with_bridging_context_not_rejected(self):
  plan,_=feasible_story(dict(hook=3,sequence=[0,6]),self.catalog,self.style)
  self.assertGreaterEqual(plan['duration'],30);self.assertEqual(plan['unit_ids'][0],3)
  body=plan['unit_ids'][1:];self.assertEqual(body,sorted(body))
  self.assertTrue({1,2}&set(body),'gap between selected parts is filled first')
  self.assertNotIn(3,body)
 def test_adaptive_policy_keeps_model_length(self):
  plan,_=feasible_story(dict(hook=0,sequence=[1,2]),self.catalog,dict(self.style,length_policy='adaptive'))
  self.assertEqual(plan['unit_ids'],[0,1,2])
 def test_question_ending_receives_its_real_answer(self):
  self.assertEqual(complete_ending([0,2,3],self.catalog,self.style),[0,2,3,4])
  self.assertEqual(complete_ending([0,6],self.catalog,self.style),[0,6])
 def test_expansion_respects_max_seconds_and_other_sources(self):
  other=self.catalog+[unit(8,0,5.5,'Other source line.',source=1)]
  ids=expand_context([0,1],other,dict(self.style,min_seconds=200,max_seconds=40))
  self.assertLessEqual(sum(other[i]['seconds'] for i in ids),40);self.assertNotIn(8,ids)
 def test_fixed_hook_revision_body_is_not_extended(self):
  plan,_=feasible_story(dict(hook=0,sequence=[1,2],fixed_sequence=True),self.catalog,dict(self.style,min_seconds=15,min_shots=3))
  self.assertEqual(plan['unit_ids'],[0,1,2])
 def test_overview_repair_includes_outcome_and_ends_on_it(self):
  ranks={i:dict(id=i,importance=5 if i in (1,6) else 2) for i in range(8)}
  raw=dict(required_ids=[1,2,7],outcome_ids=[6],ranked_ids=[6,1,2])
  fixed=repair_overview(raw,self.catalog,ranks,45)
  self.assertIn(6,fixed['required_ids']);self.assertEqual(max(fixed['required_ids']),6);self.assertIn(7,fixed['ranked_ids'])
  tight=repair_overview(dict(raw,required_ids=[0,1,2,3,4,6]),self.catalog,ranks,12)
  self.assertEqual(tight['required_ids'],[1,6])
  with self.assertRaises(ValueError):repair_overview(dict(raw,required_ids=[6],outcome_ids=[6]),self.catalog,ranks,3)
 def test_partial_rankings_are_completed_but_garbage_rejected(self):
  ranks=rankings([dict(id=i,importance=4,role='context') for i in range(9)],set(range(10)))
  self.assertEqual(len(ranks),10);self.assertTrue(ranks[9]['imputed'])
  with self.assertRaises(ValueError):rankings([dict(id=1,importance=9,role='x')],set(range(10)))
 def test_hook_signals_reward_energy_and_curiosity_penalize_greetings(self):
  transcript=dict(segments=[],audio_context=dict(loudness=dict(step=.5,db=[-30]*40+[-14]*4+[-30]*40)))
  loud=hook_signals(unit(0,20,22,'Why is it smoking?'),transcript)
  quiet=hook_signals(unit(1,0,2,'Welcome back to the channel'),transcript)
  self.assertGreater(loud[0],quiet[0]);self.assertIn('question',loud[1]);self.assertTrue(any(c.startswith('energy') for c in loud[1]));self.assertIn('greeting',quiet[1])
  self.assertTrue(hook_signals(unit(2,0,2,'No loudness data here?'),dict(segments=[]))[0]>0)
class ApprovalLoopTests(unittest.TestCase):
 """An approved plan completed with real adjacent units must not loop back to review."""
 def setUp(self):
  texts=['Setup line here.','The plan begins now.','Will it actually work?','Yes, it finally works.','Extra trailing chatter.']
  self.catalog=[unit(i,i*5.0,i*5.0+4.8,t) for i,t in enumerate(texts)]
 def test_only_additions(self):
  from editorial import only_additions
  self.assertTrue(only_additions([0,2],[0,1,2,3]))
  self.assertFalse(only_additions([0,2,3],[0,3,2]))
  self.assertFalse(only_additions([0,2],[1,0,2]))
  self.assertFalse(only_additions([0,2],[0,1]))
 def test_full_content_ending_accepts_answer_after_outcome_only(self):
  from story_director import check_story
  director=dict(status='full_content_summary',required_ids=[1,2],ending_ids=[2])
  check_story(dict(unit_ids=[0,1,2,3]),director,self.catalog)
  with self.assertRaises(ValueError):check_story(dict(unit_ids=[0,1,2,3,4,]),dict(director,ending_ids=[1]),self.catalog)
 def test_expansion_never_moves_the_approved_ending(self):
  ids=expand_context([1,2],self.catalog,dict(DEFAULT,min_seconds=20,max_seconds=60,min_shots=2,max_shots=10,length_policy='strict'))
  self.assertEqual(ids[-1],2);self.assertIn(0,ids)
class ReviewerShapeTests(unittest.TestCase):
 """Real failures from 2026-10-29: the reviewer repeats the hook, forgets required beats."""
 def setUp(self):
  texts=['Intro to the stream.','We start the challenge now.','Halfway there already.','Like and subscribe for more streams!','He keeps going strong.','He finishes all one hundred.','Chat goes wild.']
  self.catalog=[unit(i,i*10.0,i*10.0+9.5,t) for i,t in enumerate(texts)]
  self.style=dict(DEFAULT,min_seconds=30,max_seconds=60,target_seconds=45,min_shots=3,max_shots=12,length_policy='strict')
  self.director=dict(status='full_content_summary',required_ids=[1,5],ending_ids=[5],payoff_ids=[5])
 def test_repeated_hook_and_ids_are_the_same_plan(self):
  from editorial import clean_choice
  self.assertEqual(clean_choice(dict(hook=1,sequence=[1,2,2,5]))['sequence'],[2,5])
 def test_summary_plan_gets_required_beats_stops_at_outcome_and_drops_ads(self):
  from story_director import enforce_summary,check_story
  bound=enforce_summary(dict(hook=2,sequence=[3,4,6]),self.director,self.catalog,self.style)
  self.assertEqual(bound['sequence'],[1,4,5])
  plan,_=feasible_story(bound,self.catalog,self.style);check_story(plan,self.director,self.catalog)
  self.assertEqual(enforce_summary(dict(hook=2,sequence=[4],fixed_sequence=True),self.director,self.catalog,self.style)['sequence'],[4])
if __name__=='__main__':unittest.main()
