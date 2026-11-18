import unittest,tempfile,json,time
from pathlib import Path
from unittest.mock import patch,MagicMock
from short_feedback import recommendation,read,refresh
from editorial import compile_story,apply_editorial_review,camera_plan
class FeedbackTests(unittest.TestCase):
 def video(self,id='abc',**kw):
  return dict(dict(id=id,topic='same topic',duration=40,status='processed',age_hours=30,engaged_views=200,average_view_percentage=45,published_at='2026-10-19'),**kw)
 def test_no_retention_inference_from_views_or_fresh_upload(self):
  videos=[self.video(str(i),views=100000,engaged_views=None,average_view_percentage=None) for i in range(5)]
  self.assertIsNone(recommendation(videos)['change'])
  self.assertIsNone(recommendation([self.video(str(i),age_hours=1) for i in range(5)])['change'])
 def test_comparable_sample_is_cautious_single_variable_experiment(self):
  r=recommendation([self.video(str(i)) for i in range(3)])
  self.assertEqual(r['status'],'exploratory_test');self.assertEqual(r['change'],'setup_density');self.assertEqual(len(r['evidence_ids']),3)
  self.assertIsNone(recommendation([self.video(str(i),topic=str(i)) for i in range(3)])['change'])
 def test_missing_and_nonfinite_metrics_never_mean_failure(self):
  self.assertIsNone(recommendation([self.video(str(i),average_view_percentage=float('nan')) for i in range(3)])['change'])
 def test_read_is_project_scoped(self):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root)/'integrations/youtube/first';p.mkdir(parents=True);(p/'feedback.json').write_text('{"status":"first"}')
   self.assertEqual(read(root,'second')['status'],'not_collected')
class ComedyEditorTests(unittest.TestCase):
 def setup_plan(self):
  catalog=[dict(id=i,source=0,start=i*4,end=i*4+4,seconds=4,text='Real line %d.'%i) for i in range(4)]
  style=dict(min_seconds=10,max_seconds=20,min_shots=3,max_shots=5)
  return catalog,compile_story(dict(hook=2,sequence=[0,3],strict_story=True),catalog,style)
 def test_preserves_editorial_order_without_padding(self):
  c,p=self.setup_plan();self.assertEqual(p['unit_ids'],[2,0,3])
  with self.assertRaises(ValueError):compile_story(dict(hook=2,sequence=[0],strict_story=True),c,dict(min_seconds=10,max_seconds=20,min_shots=3,max_shots=5))
 def test_deadpan_preserves_pause_and_silence(self):
  c,p=self.setup_plan();review=dict(approved=True,hook_candidates=[dict(id=2,reason='Grounded opening')],humor_type='deadpan',beats=[dict(id=0,beat='payoff',preserve_pause=True,sound='pop')])
  p=apply_editorial_review(p,review,c);self.assertEqual(p['shots'][1]['sound'],'none');self.assertTrue(p['shots'][1]['preserve_pause'])
 def test_fabricated_hook_is_rejected(self):
  c,p=self.setup_plan()
  with self.assertRaises(ValueError):apply_editorial_review(p,dict(approved=True,hook_candidates=[dict(id=99,reason='Fake')]),c)
 def test_effects_follow_payoff_not_modulo_shot_index(self):
  tracks=[dict(transcript=dict(segments=[dict(start=0,end=20,text='Real speech')]))]
  shots=[dict(source=0,start=i*4,end=i*4+4,framing='wide',beat='payoff' if i==1 else 'context',sound='pop') for i in range(4)]
  result=camera_plan(shots,tracks,[])
  self.assertEqual(result[1]['sound'],'pop');self.assertEqual(result[0]['sound'],'none');self.assertEqual(result[3]['sound'],'none')

class AdaptiveStoryTests(unittest.TestCase):
 def test_short_approved_story_adapts_per_run_without_filler(self):
  from editorial import feasible_story
  catalog=[dict(id=i,source=0,start=i*6,end=(i+1)*6,seconds=6,text='Real line.') for i in range(3)]
  style=dict(min_seconds=60,max_seconds=90,target_seconds=75,min_shots=4,max_shots=24,length_policy='adaptive')
  plan,effective=feasible_story(dict(hook=0,sequence=[1,2]),catalog,style)
  self.assertEqual(plan['duration'],18);self.assertEqual(effective['min_seconds'],18);self.assertEqual(style['min_seconds'],60)
  with self.assertRaises(ValueError):feasible_story(dict(hook=0,sequence=[1,2]),catalog,dict(style,length_policy='strict'))

class WordBoundaryTests(unittest.TestCase):
 def test_sentence_inside_unpunctuated_segment_is_not_discarded(self):
  from editorial import story_units
  t=dict(segments=[dict(start=0,end=15,text='A completed sentence. And then unfinished',words=[dict(start=0,end=2,word='A completed'),dict(start=2,end=4,word='sentence.'),dict(start=5,end=9,word='And then'),dict(start=9,end=15,word='unfinished')])])
  units=story_units(t,12);self.assertEqual(units[0]['text'],'A completed sentence.');self.assertEqual(units[0]['boundary'],'sentence');self.assertTrue(all(u['end']-u['start']<=12 for u in units))
