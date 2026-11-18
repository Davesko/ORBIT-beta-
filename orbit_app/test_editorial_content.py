import unittest
from editorial import reviewed_choice
from autonomous import EDITOR_REVIEW

class ContentReviewTests(unittest.TestCase):
 def test_rejection_preserves_real_reason(self):
  with self.assertRaisesRegex(ValueError,'missing visual evidence'):
   reviewed_choice({'approved':False,'plan':None,'removed_reason':'missing visual evidence'}, {'hook':0,'sequence':[1]})
 def test_approved_null_plan_uses_proposal_without_bypassing_approval(self):
  p={'hook':0,'sequence':[1]}
  self.assertIs(reviewed_choice({'approved':True,'plan':None},p),p)
  with self.assertRaises(ValueError):reviewed_choice({'plan':p},p)
 def test_string_plan_rejected(self):
  with self.assertRaises(ValueError):reviewed_choice({'approved':True,'plan':'looks good'}, {})
 def test_noncomedy_contract(self):
  self.assertIn('A joke is NOT required',EDITOR_REVIEW)
  self.assertIn('sampled timestamps',EDITOR_REVIEW)

class VisualAndRoutingTests(unittest.TestCase):
 def test_visual_only_catalog_uses_real_samples_not_fake_words(self):
  from editorial import unit_catalog
  tracks=[dict(source=dict(duration=60),transcript=dict(text='',segments=[]))]
  cat=unit_catalog(tracks,dict(max_shot_seconds=12),[dict(frames=[dict(seconds=10,action='A model walks on the runway.'),dict(seconds=35,action='A singer stands on stage.')])])
  self.assertEqual(len(cat),2);self.assertEqual(cat[0]['boundary'],'visual_sample');self.assertIn('10s',cat[0]['text']);self.assertEqual(cat[1]['visual_samples'][0]['seconds'],35)
 def test_embedding_only_healthy_list_cannot_hide_real_chat_models(self):
  from model_router import usable,choose
  models=[dict(name='qwen3-embedding:0.6b'),dict(name='qwen3.5:9b')]
  self.assertEqual(len(usable(models)),1);self.assertEqual(usable(models[:1]),[])
  self.assertEqual(choose('Review a plan',usable(models))['model'],'qwen3.5:9b')
 def test_rounding_tolerance_does_not_pad_short(self):
  from editorial import feasible_story
  catalog=[dict(id=i,source=0,start=i*7.137142857,end=(i+1)*7.137142857,seconds=7.137142857,text='Actual timed sentence.') for i in range(7)]
  plan,style=feasible_story(dict(hook=0,sequence=list(range(1,7))),catalog,dict(min_seconds=50,max_seconds=60,target_seconds=55,min_shots=4,max_shots=12,length_policy='strict'))
  self.assertAlmostEqual(plan['duration'],49.96);self.assertEqual(style['min_seconds'],50)
 def test_temporarily_unhealthy_chat_is_retried_when_only_embedding_is_healthy(self):
  import ai_runtime
  from unittest.mock import patch
  models=[dict(name='qwen3-embedding:0.6b'),dict(name='qwen3.5:9b')]
  with patch('inference_gate.lease',return_value=__import__('contextlib').nullcontext()),patch('model_hub.models',return_value=models),patch('model_hub.request',return_value={'message':{'content':'{"ok":true}'}}) as api,patch('connections.settings',return_value=dict(mode='local',share_context=True,preferred='groq',providers={})),patch('connections.read',return_value={'qwen3.5:9b':99999999999}),patch('ai_runtime.unresponsive_models',return_value={'qwen3.5:9b'}),patch('connections.atomic'):
   result=ai_runtime.request('api/chat',dict(model='auto',format='json',messages=[dict(role='user',content='Review evidence')]),timeout=90)
  self.assertEqual(api.call_args.args[1]['model'],'qwen3.5:9b');self.assertIn('ok',result['message']['content'])
 def test_timing_repair_candidates_are_prevalidated_and_need_editor_approval(self):
  from editorial import duration_candidates,feasible_story,reviewed_choice
  from autonomous import TIMING_REPAIR
  cat=[dict(id=i,source=0,start=i*10,end=(i+1)*10,seconds=10,text='Actual context sentence.') for i in range(8)]
  style=dict(min_seconds=50,max_seconds=90,target_seconds=70,min_shots=4,max_shots=12,length_policy='strict')
  candidates=duration_candidates(cat,style);self.assertTrue(candidates)
  for c in candidates:self.assertGreaterEqual(feasible_story(c,cat,style)[0]['duration'],49.75)
  with self.assertRaises(ValueError):reviewed_choice(dict(approved=False,removed_reason='Not coherent'),candidates[0])
  self.assertIn('Do not shorten',TIMING_REPAIR)
 def test_lyrics_do_not_hide_visual_fashion_candidates(self):
  from editorial import unit_catalog,duration_candidates
  tracks=[dict(source=dict(duration=180),transcript=dict(segments=[dict(start=0,end=5,text='Unrelated soundtrack lyric.')]))]
  obs=[dict(frames=[dict(seconds=t,action='A runway model wears a distinctive outfit.') for t in (18,54,90,126,162)])]
  style=dict(max_shot_seconds=12,min_seconds=50,max_seconds=100,target_seconds=75,min_shots=4,max_shots=32,length_policy='strict')
  cat=unit_catalog(tracks,style,obs);self.assertTrue(any(u['boundary']=='visual_sample' for u in cat));options=duration_candidates(cat,style)
  self.assertTrue(options);self.assertEqual(options[0]['verified_seconds'],60);self.assertEqual(options[0]['verified_units'],5)
 def test_speech_and_visual_overlap_cannot_duplicate_footage(self):
  from editorial import feasible_story
  cat=[dict(id=0,source=0,start=0,end=10,seconds=10,text='Actual speech'),dict(id=1,source=0,start=5,end=15,seconds=10,text='Actual frame')]
  with self.assertRaisesRegex(ValueError,'átfedik'):feasible_story(dict(hook=0,sequence=[1]),cat,dict(min_seconds=12,max_seconds=30,target_seconds=20,min_shots=2,max_shots=6,length_policy='strict'))

 def test_candidate_review_isolates_alternatives_and_rejects_actual_overlap(self):
  from editorial import candidate_review_input
  cat=[dict(id=i,source=0,start=i*12,end=(i+1)*12,seconds=12,text='Observed action') for i in range(5)]
  style=dict(min_seconds=50,max_seconds=100,target_seconds=75,min_shots=4,max_shots=10,length_policy='strict')
  choices=[dict(hook=0,sequence=[1,2,3,4]),dict(hook=1,sequence=[0,2,3,4])]
  evidence=candidate_review_input('fashion',choices,cat,style)
  self.assertNotIn('correction',evidence);self.assertEqual(len(evidence['candidates']),2)
  self.assertTrue(all(c['non_overlapping'] and c['verified_seconds']==60 for c in evidence['candidates']))
  cat[1]=dict(cat[1],start=6,end=18)
  with self.assertRaisesRegex(ValueError,'átfedik'):candidate_review_input('fashion',choices,cat,style)
 def test_candidates_offer_both_sources_before_opening_variants(self):
  from editorial import unit_catalog,duration_candidates
  tracks=[dict(source=dict(duration=180),transcript=dict(segments=[])) for _ in range(2)]
  obs=[dict(frames=[dict(seconds=t,action='Actual runway moment.') for t in (18,54,90,126,162)]) for _ in tracks]
  style=dict(max_shot_seconds=12,min_seconds=50,max_seconds=100,target_seconds=75,min_shots=4,max_shots=32,length_policy='strict')
  cat=unit_catalog(tracks,style,obs);options=duration_candidates(cat,style)
  self.assertEqual(cat[options[0]['hook']]['source'],0);self.assertEqual(cat[options[1]['hook']]['source'],1)
 def test_performance_uses_visible_events_instead_of_a_story_invented_from_lyrics(self):
  from editorial import unit_catalog
  track=dict(source=dict(duration=60),transcript=dict(segments=[dict(start=0,end=6,text='Unrelated song lyric.')]))
  observations=[dict(content_type='gameplay',frames=[dict(seconds=10,action='A performer sings into a microphone on stage.'),dict(seconds=30,action='A model walks down the runway.'),dict(seconds=50,action='A performer dances on stage.')])]
  catalog=unit_catalog([track],dict(max_shot_seconds=12),observations)
  self.assertTrue(catalog);self.assertTrue(all(u['boundary']=='visual_sample' for u in catalog));self.assertNotIn('Unrelated song lyric.',str(catalog))
 def test_portrait_fill_does_not_imply_an_extra_face_zoom(self):
  from editorial import feasible_story,apply_editorial_review
  cat=[dict(id=i,source=0,start=i*7,end=(i+1)*7,seconds=7,text='Actual scene.') for i in range(3)]
  choice=dict(hook=0,sequence=[1,2]);style=dict(min_seconds=20,max_seconds=30,target_seconds=25,min_shots=2,max_shots=4)
  plan,_=feasible_story(choice,cat,style);self.assertTrue(all(s['effect']=='none' and s['framing']=='wide' for s in plan['shots']))
  review=dict(approved=True,hook_candidates=[dict(id=0,reason='Supported opening')],beats=[dict(id=1,beat='payoff',reason='A clear reaction')])
  plan=apply_editorial_review(plan,review,cat);self.assertEqual(plan['shots'][1]['effect'],'none')
  review['beats'][0].update(camera='speaker',effect='punch-in');plan=apply_editorial_review(plan,review,cat);self.assertEqual(plan['shots'][1]['effect'],'punch-in')
 def test_mixed_compilation_keeps_gameplay_out_of_the_facecam_crop(self):
  from editorial import scene_kind,camera_plan
  obs=dict(content_type='mixed',frames=[dict(seconds=5,action='Minecraft gameplay with a facecam inset at the bottom right.',has_person=True),dict(seconds=25,action='The main video player shows police footage with a facecam inset.',has_person=True)])
  self.assertEqual(scene_kind(obs,0,10),'gameplay');self.assertEqual(scene_kind(obs,20,30),'screen_content')
  shots=[dict(source=0,start=0,end=10,framing='wide',effect='none'),dict(source=0,start=20,end=30,framing='wide',effect='none')]
  cameras=camera_plan(shots,[dict(transcript=dict(segments=[]))],[obs]);self.assertTrue(all(p['base_follow'] is False for p in cameras));self.assertTrue(all(p['effect']=='none' for p in cameras))
 def test_visual_observation_supplements_speech_without_duplicate_source_intervals(self):
  from editorial import unit_catalog
  tracks=[dict(source=dict(duration=40),transcript=dict(segments=[dict(start=10,end=15,text='A real complete setup.'),dict(start=20,end=25,text='A real complete response.')]))]
  observations=[dict(frames=[dict(seconds=18,action='A gameplay scene with a facecam.')])]
  cat=unit_catalog(tracks,dict(max_shot_seconds=12),observations)
  for i,a in enumerate(cat):
   for b in cat[i+1:]:self.assertLessEqual(min(a['end'],b['end'])-max(a['start'],b['start']),0)
  visual=next(u for u in cat if u['boundary']=='visual_sample');self.assertEqual((visual['start'],visual['end']),(15,20))
 def test_short_neighboring_utterances_are_not_chopped_into_word_sized_shots(self):
  from editorial import phrase_groups
  units=[dict(start=0,end=1,text='Look.',boundary='sentence'),dict(start=1.2,end=2,text='There it is!',boundary='sentence'),dict(start=4,end=5,text='A later reaction.',boundary='sentence')]
  grouped=phrase_groups(units,12);self.assertEqual(len(grouped),2);self.assertEqual(grouped[0]['end'],2);self.assertEqual(grouped[0]['text'],'Look. There it is!')
 def test_candidate_does_not_end_on_filler_or_repeat_a_long_passage(self):
  from editorial import duration_candidates
  repeated='This is a complete spoken scene with enough actual words to establish a situation and describe its real outcome.'
  cat=[dict(id=i,source=0,start=i*10,end=(i+1)*10,seconds=10,text=text,boundary='sentence') for i,text in enumerate([repeated,'Another complete context sentence.',repeated+' Yes.','A clear closing reaction.','Ummm','I want to explain -'])]
  style=dict(min_seconds=20,max_seconds=60,target_seconds=35,min_shots=2,max_shots=12,length_policy='strict')
  candidates=duration_candidates(cat,style);self.assertTrue(candidates)
  compilation=next(c for c in candidates if c['context'].startswith('Chronological compilation'))
  ids=[compilation['hook']]+compilation['sequence'];self.assertNotIn(2,ids);self.assertNotIn(4,ids);self.assertNotIn(5,ids)
