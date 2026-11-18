import unittest
from editorial import camera_plan,story_units,caption_theme,validate_masks
class EditorialTests(unittest.TestCase):
 def test_complete_sentence_units(self):
  t={'segments':[dict(start=0,end=2,text='Here is'),dict(start=2,end=4,text='the result!'),dict(start=5,end=6,text='Unfinished')]}
  self.assertEqual(story_units(t),[dict(start=0.,end=4.,text='Here is the result!')])
 def test_gameplay_and_unknown_keep_full_frame(self):
  tracks=[dict(transcript=dict(segments=[dict(start=0,end=20,text='speech')]))]
  shots=[dict(source=0,start=i*4,end=i*4+4,framing='speaker',beat='context',effect='punch-in') for i in range(4)]
  obs=[dict(content_type='gameplay',frames=[dict(seconds=i*4+1,has_person=True) for i in range(4)])]
  self.assertTrue(all(p['framing']=='wide' for p in camera_plan(shots,tracks,obs)))
  self.assertTrue(all(p['framing']=='wide' for p in camera_plan(shots,tracks,[])))
 def test_closeups_are_speech_grounded_and_budgeted(self):
  tracks=[dict(transcript=dict(segments=[dict(start=0,end=20,text='speech')]))]
  shots=[dict(source=0,start=i*4,end=i*4+4,framing='speaker',beat='hook',effect='punch-in') for i in range(5)]
  obs=[dict(content_type='talking_head',frames=[dict(seconds=i*4+1,has_person=True) for i in range(5)])]
  self.assertLessEqual(sum(p['framing']=='speaker' for p in camera_plan(shots,tracks,obs)),1)
 def test_captions_and_masks_bounded(self):
  self.assertEqual(caption_theme('invented font'),caption_theme('clean'))
  with self.assertRaises(ValueError):validate_masks([dict(x=0,y=0,w=1,h=1,reason='hide all')])
  with self.assertRaises(ValueError):validate_masks([dict(x=.1,y=.1,w=.1,h=.1,reason='')])
  self.assertEqual(len(validate_masks([dict(x=.1,y=.1,w=.1,h=.1,reason='Private phone number')])),1)

class PrivacyMaskTests(unittest.TestCase):
 def test_requires_two_agreeing_samples_and_keeps_gameplay_unmasked(self):
  from editorial import stable_privacy_masks
  r=dict(kind='private_email',x=.1,y=.1,w=.2,h=.05,confidence=.99)
  obs=dict(aspect_ratio=16/9,frames=[dict(seconds=1,redactions=[r])])
  self.assertEqual(stable_privacy_masks(obs,0,4),[])
  obs['frames'].append(dict(seconds=3,redactions=[r]))
  self.assertEqual(len(stable_privacy_masks(obs,0,4)),1)
  r['kind']='gameplay_ui';self.assertEqual(stable_privacy_masks(obs,0,4),[])

class StoryCatalogTests(unittest.TestCase):
 def test_hook_uses_real_complete_units_and_duration(self):
  from editorial import compile_story
  style=dict(min_seconds=10,max_seconds=20,min_shots=2,max_shots=4)
  c=[dict(text='Actual hook!',source=0,start=0,end=5),dict(text='Real payoff.',source=0,start=6,end=12)]
  r=compile_story(dict(hook=0,sequence=[1],caption_theme='gaming'),c,style)
  self.assertEqual(r['outline']['hook'],'Actual hook!');self.assertEqual(r['shots'][0]['beat'],'hook')
  with self.assertRaises(ValueError):compile_story(dict(hook=5,sequence=[1]),c,style)

class NarrativeBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.style=dict(min_seconds=4,max_seconds=30,target_seconds=20,min_shots=2,max_shots=8)
  self.catalog=[dict(id=0,text='When I opened',source=0,start=0,end=3,seconds=3,boundary='window'),dict(id=1,text='the box, it was empty.',source=0,start=3,end=6,seconds=3,boundary='sentence',starts_mid_sentence=True),dict(id=2,text='But the prize was underneath!',source=0,start=7,end=11,seconds=4,boundary='sentence')]
 def test_rejects_a_hook_that_starts_mid_sentence(self):
  from editorial import feasible_story
  plan,_=feasible_story(dict(hook=1,sequence=[2]),self.catalog,self.style)
  self.assertEqual(plan['unit_ids'],[0,1,2])
 def test_rejects_cutting_away_from_an_unfinished_sentence(self):
  from editorial import feasible_story
  plan,_=feasible_story(dict(hook=0,sequence=[2]),self.catalog,self.style)
  self.assertEqual(plan['unit_ids'],[0,1,2])
  self.catalog[1]['start']=20
  with self.assertRaisesRegex(ValueError,'félbeszakítaná'):feasible_story(dict(hook=0,sequence=[2]),self.catalog,self.style)
 def test_keeps_context_and_maps_hook_to_first_output_frame(self):
  from editorial import feasible_story,storyboard
  plan,_=feasible_story(dict(hook=0,sequence=[1,2]),self.catalog,self.style)
  timeline=storyboard(plan,self.catalog)
  self.assertEqual(timeline[0]['phase'],'hook');self.assertEqual(timeline[0]['output_start'],0)
  self.assertEqual(timeline[-1]['phase'],'ending');self.assertEqual(timeline[-1]['output_end'],10)
  self.assertEqual(timeline[1]['evidence'],self.catalog[1]['text'])
 def test_short_negation_is_preserved_in_catalogue(self):
  from editorial import unit_catalog
  tracks=[dict(transcript=dict(segments=[dict(words=[dict(start=0,end=.2,word='No.'),dict(start=.25,end=2,word='That is not true.')])]))]
  units=unit_catalog(tracks,dict(max_shot_seconds=12))
  self.assertTrue(units[0]['text'].startswith('No.'))
 def test_larger_caption_groups_follow_selected_font_metrics(self):
  from montage import groups,write_word_captions
  import tempfile
  from pathlib import Path
  words=[dict(start=i,end=i+.8,text='Extraordinary') for i in range(4)]
  large=list(groups(words,80));small=list(groups(words,44))
  self.assertGreaterEqual(len(large),len(small))
  preset=dict(font='Arial',font_size=80,anchor=[486,1560],box=[108,1320,864,1580],animation='word-pop')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'large.ass';write_word_captions(words,path,preset=preset)
   text=path.read_text();self.assertIn('Style: Default,Arial,80,',text);self.assertIn(r'\clip(108,1320,864,1580)',text)
 def test_role_prompt_migration_preserves_custom_request_and_is_idempotent(self):
  from short_prompt_contract import role_prompt
  p=role_prompt('Use the current user brief.','selection')
  self.assertEqual(role_prompt(p,'selection'),p);self.assertTrue(p.startswith('Use the current user brief.'))
  self.assertIn('Narrative role (v2):',p)
 def test_sentence_window_sampling_never_orphans_a_continuation(self):
  from editorial import complete_speech_windows
  units=[]
  for i in range(18):units.append(dict(id=i,start=i,end=i+1,boundary='window' if i%2==0 else 'sentence',starts_mid_sentence=i%2==1))
  sampled=complete_speech_windows(units,8);ids={u['id'] for u in sampled}
  self.assertLessEqual(len(sampled),8)
  self.assertTrue(all((u['id']-1 in ids) if u['starts_mid_sentence'] else (u['id']+1 in ids) for u in sampled))
  self.assertIn(0,ids);self.assertIn(17,ids)
 def test_duplicate_requested_units_still_rejected_after_sentence_repair(self):
  from editorial import feasible_story
  with self.assertRaisesRegex(ValueError,'ismételt'):feasible_story(dict(hook=0,sequence=[1,1,2]),self.catalog,self.style)
 def test_candidate_search_passes_bad_windows_to_find_valid_other_source(self):
  from editorial import duration_candidates
  c=self.catalog+[dict(id=3,text='Clear setup.',source=1,start=0,end=7,seconds=7,boundary='sentence'),dict(id=4,text='Real ending.',source=1,start=7,end=14,seconds=7,boundary='sentence')]
  c[1]['start']=20
  candidates=duration_candidates(c,self.style)
  self.assertTrue(any(x['hook']==3 and 4 in x['sequence'] for x in candidates))
 def test_different_video_answer_cannot_fake_a_conversation(self):
  from editorial import feasible_story
  catalog=[dict(id=0,text='What do you think of this casting?',source=0,start=0,end=7,seconds=7,boundary='sentence'),dict(id=1,text='Of course I will.',source=1,start=0,end=5,seconds=5,boundary='sentence')]
  with self.assertRaisesRegex(ValueError,'Külön forrás'):feasible_story(dict(hook=0,sequence=[1]),catalog,self.style)
 def test_tiny_final_noun_is_not_removed_by_render_minimum(self):
  from editorial import unit_catalog
  tracks=[dict(source=dict(duration=10),transcript=dict(segments=[dict(words=[dict(start=0,end=6.9,word='He was chosen for this'),dict(start=6.9,end=7.22,word='role.'),dict(start=7.5,end=9,word='A new sentence.')])]))]
  units=unit_catalog(tracks,dict(max_shot_seconds=7))
  self.assertTrue(any('role.' in u['text'] for u in units))
