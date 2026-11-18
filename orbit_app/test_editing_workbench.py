import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from autonomous import plan_schema
from short_style import DEFAULT

class WorkbenchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);plan_schema(self.s)
  self.agent=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  for name in ('Echo','Scout','Lex','Reach','Vega'):self.s.save_agent(dict(project='universe',name=name,role=name,room='bridge',model='auto',tools=['project_files']))
  source=self.s.safe_path('universe','source.mp4');source.write_bytes(b'source');self.s.safe_path('universe','words.json').write_text('{}')
  self.data=dict(complete=True,style=dict(DEFAULT,publish_to_youtube=True,review_before_upload=False),source=dict(source_video='source.mp4'),tracks=[dict(source=dict(source_video='source.mp4',duration=20),transcript_file='words.json')],montage=dict(shots=[dict(source=0,start=0,end=5,beat='hook'),dict(source=0,start=6,end=12,beat='payoff')]),render=dict(saved='renders/old.mp4'))
  self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('parent','universe','real topic',json.dumps(self.data),time.time()))
  jid=self.s.enqueue(self.agent,'old render','graph',payload=dict(run='parent',auto_step='render'));self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(jid,));self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('video','universe','old.mp4',str(self.s.safe_path('universe','renders/old.mp4')),'video',time.time(),jid));self.s.db.commit()
 def test_feedback_scoped_and_double_click_deduplicated(self):
  from editing_memory import save,read
  save(self.s,'universe','video','weak_hook');save(self.s,'universe','video','weak_hook')
  self.assertEqual(read(self.s,'universe')['counts']['weak_hook'],1)
  other=self.s.create_project('Other')
  with self.assertRaises(ValueError):save(self.s,other,'video','good')
  self.assertFalse(read(self.s,other)['instructions'])
 def test_caption_revision_preserves_parent_and_cannot_autopublish(self):
  from edit_review import revise
  a=revise(self.s,'universe','video','captions','request-123');b=revise(self.s,'universe','video','captions','request-123')
  self.assertEqual(a['run'],b['run']);self.assertEqual(set(a['jobs']),{'render','verify'})
  data=json.loads(self.s.db.execute('SELECT data FROM short_runs WHERE id=?',(a['run'],)).fetchone()[0]);self.assertFalse(data['style']['publish_to_youtube']);self.assertNotIn('complete',data)
  self.assertEqual(json.loads(self.s.db.execute("SELECT data FROM short_runs WHERE id='parent'").fetchone()[0]),self.data)
 def test_revision_cannot_start_over_an_active_production(self):
  from edit_review import revise
  self.s.enqueue(self.agent,'active','graph',payload=dict(auto_step='source'))
  with self.assertRaises(ValueError):revise(self.s,'universe','video','framing','request-456')
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM short_runs').fetchone()[0],1)
 def test_only_hook_changes_fixed_body(self):
  from edit_review import fixed_hook_choice
  revision=dict(kind='hook',fixed_body=[dict(source=0,start=6,end=12)],old_hook=dict(source=0,start=0,end=5))
  catalog=[dict(id=0,source=0,start=0,end=5),dict(id=1,source=0,start=6,end=12),dict(id=2,source=0,start=13,end=18)]
  choice=fixed_hook_choice(dict(hook=2,sequence=[0]),catalog,revision);self.assertEqual(choice['sequence'],[1])
  with self.assertRaises(ValueError):fixed_hook_choice(dict(hook=0),catalog,revision)
 def test_experiment_assignments_alternate_and_do_not_claim_causality(self):
  from editing_experiments import schema,assign,summarize
  schema(self.s);feedback=dict(recommendation=dict(status='exploratory_test',sample_size=3,change='setup_density',instruction='Only concise setup'))
  a=assign(self.s,'universe','r1','topic',DEFAULT,feedback);b=assign(self.s,'universe','r2','topic',DEFAULT,feedback);self.s.db.commit()
  self.assertEqual(a['id'],b['id']);self.assertEqual((a['variation'],b['variation']),('control','test'));self.assertEqual(a['baseline'],b['baseline'])
  report=summarize(self.s,'universe',[]);self.assertFalse(report['causal']);self.assertEqual(report['groups']['test']['count'],0)
 def test_changed_operator_settings_end_old_experiment(self):
  from editing_experiments import schema,assign
  schema(self.s);f=dict(recommendation=dict(status='exploratory_test',sample_size=3,change='hook_mechanism'))
  a=assign(self.s,'universe','r1','topic',DEFAULT,f);b=assign(self.s,'universe','r2','topic',dict(DEFAULT,highlight_color='#000000'),f)
  self.assertNotEqual(a['id'],b['id']);self.assertEqual(self.s.db.execute("SELECT status FROM editing_experiments WHERE id=?",(a['id'],)).fetchone()[0],'settings_changed')
 def test_benchmark_does_not_execute_returned_code(self):
  import model_evaluation as e
  response=lambda route,data,timeout:dict(message=dict(content=json.dumps(e.CASES[len(calls)][2])))
  calls=[]
  def ask(route,data,timeout):
   expected=e.CASES[len(calls)][2];calls.append(data);return dict(message=dict(content=json.dumps(expected)))
  jid=self.s.enqueue(self.agent,'measure','model_evaluation',payload=dict(model='local/test',results=[]));job=self.s.claim(('model_evaluation',))
  with patch('model_hub.request',side_effect=ask):e.run(self.s,job)
  report=json.loads((self.s.root/'model-quality.json').read_text())['models']['local/test'];self.assertEqual(report['utility']['passed'],6);self.assertEqual(len(calls),18)
  self.assertTrue(all(c['model']=='local/test' for c in calls))

class StoryAndFramingTests(unittest.TestCase):
 def test_director_rejects_hallucinated_ids(self):
  from story_director import validate
  with self.assertRaises(ValueError):validate(dict(event_id=0,premise='A real premise',viewer_question='What actually happens?',resolution='Actual selected resolution',hook_candidates=[99],payoff_ids=[0],ending_ids=[0]),[dict(id=0,source=0,start=0,end=5,text='Real scene.')])
 def test_pacing_preserves_words_and_total_source_duration(self):
  from story_director import pace
  plan=dict(shots=[dict(source=0,start=0,end=10,beat='context')]);words=[dict(start=0,end=2.5,word='Setup.'),dict(start=3,end=5.5,word='Development.'),dict(start=6,end=9.5,word='Payoff!')]
  shots,report=pace(plan,[dict(transcript=dict(segments=[dict(words=words)]))],[])
  self.assertGreater(len(shots),1);self.assertEqual(sum(x['end']-x['start'] for x in shots),10)
  self.assertTrue(all(not any(w['start']<s['end']<w['end'] for w in words) for s in shots))
 def test_deadpan_pause_is_not_mechanically_chopped(self):
  from story_director import pace
  shots,_=pace(dict(shots=[dict(source=0,start=0,end=10,beat='payoff',preserve_pause=True)]),[dict(transcript=dict(segments=[]))],[]);self.assertEqual(len(shots),1)
 def test_two_independent_observations_required_for_split(self):
  from smart_framing import composition
  r=[dict(kind='subject',box=[0,0,.45,1],confidence=.95),dict(kind='subject',box=[.55,0,.45,1],confidence=.95)];obs=dict(aspect_ratio=1.78,frames=[dict(seconds=1,regions=r)])
  self.assertIsNone(composition(obs,0,4));obs['frames'].append(dict(seconds=3,regions=copy.deepcopy(r)));self.assertEqual(composition(obs,0,4)['mode'],'stack')
 def test_overlapping_regions_are_not_stacked(self):
  from smart_framing import composition
  r=[dict(kind='subject',box=[0,0,1,1],confidence=.95)]*2;self.assertIsNone(composition(dict(aspect_ratio=1.7,frames=[dict(seconds=t,regions=r) for t in (1,3)]),0,4))
 def test_speaker_labels_do_not_imply_person_identity(self):
  from audio_context import annotate
  result=annotate(dict(segments=[dict(words=[dict(start=0,end=1,word='No.',probability=.2),dict(start=2,end=3,word='Yes.')])]),[dict(start=0,end=1.5,speaker='speaker_0'),dict(start=1.5,end=3,speaker='speaker_1')])
  words=result['segments'][0]['words'];self.assertEqual(words[0]['speaker'],'speaker_0');self.assertTrue(words[0]['uncertain']);self.assertEqual(len(result['audio_context']['pauses']),1)
 def test_distant_compilation_episodes_cannot_fake_one_story(self):
  from story_director import event_catalog,check_story
  catalog=[dict(id=0,source=0,start=0,end=10,text='Compilation intro.'),dict(id=1,source=0,start=100,end=110,text='A different challenge.'),dict(id=2,source=0,start=170,end=180,text='An unrelated ending.')]
  self.assertEqual(len(event_catalog(catalog)),3)
  with self.assertRaisesRegex(ValueError,'külön események'):check_story(dict(unit_ids=[0,1,2]),{},catalog)
 def test_visual_montage_does_not_require_a_spoken_story(self):
  from story_director import event_catalog
  c=[dict(id=i,source=0,start=i*30,end=i*30+10,text='A visible runway outfit.',boundary='visual_sample') for i in range(3)]
  self.assertEqual(len(event_catalog(c)),1)
 def test_director_candidate_keeps_its_resolution(self):
  from story_director import repair_candidates
  c=[dict(id=i,source=0,start=i*5,end=(i+1)*5,text='An actual story sentence.',seconds=5,boundary='sentence') for i in range(5)]
  d=dict(hook_candidates=[0],context_ids=[1],development_ids=[2],payoff_ids=[3],ending_ids=[4],premise='A real conflict.',resolution='An actual resolution.')
  candidates=repair_candidates(d,c,dict(min_seconds=20,max_seconds=40,target_seconds=30,min_shots=2,max_shots=8,length_policy='adaptive'))
  self.assertTrue(candidates);self.assertTrue(all(3 in x['sequence'] and x['sequence'][-1]==4 for x in candidates))
 def test_cutaway_requires_visual_evidence_and_retains_narration_contract(self):
  from smart_framing import cutaway
  catalog=[dict(id=0,source=0,start=0,end=4),dict(id=1,source=1,start=5,end=10,visual_samples=[dict(seconds=6),dict(seconds=9)])]
  value=cutaway(dict(cutaway_id=1,cutaway_reason='The two sampled frames illustrate this same point.'),catalog[0],catalog)
  self.assertEqual(value['source'],1);self.assertEqual(value['end']-value['start'],4)
  catalog[1]['visual_samples']=[];self.assertIsNone(cutaway(dict(cutaway_id=1,cutaway_reason='Too little evidence for this clip.'),catalog[0],catalog))
 def test_promotional_teaser_is_not_an_actual_hook(self):
  from story_director import promotional
  self.assertTrue(promotional("It's a secret so you'll want to stick around."))
  self.assertTrue(promotional("A video I haven't even uploaded yet on the main channel."))
  self.assertFalse(promotional("Jimmy, we're actually sinking!"))
 def test_editorial_benchmark_needs_real_operator_examples(self):
  from model_evaluation import editorial_cases
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close)
  self.assertEqual(editorial_cases(s,'universe'),[])
 def test_pacing_retimes_sound_to_the_actual_piece(self):
  from story_director import pace
  plan=dict(shots=[dict(source=0,start=0,end=10,beat='payoff',sound='pop',sound_delay=9.82,transition='fade')]);words=[dict(start=i,end=i+1,word='Sentence.') for i in (0,3,6,9)]
  shots,_=pace(plan,[dict(transcript=dict(segments=[dict(words=words)]))],[])
  self.assertGreater(len(shots),1);self.assertTrue(all(0<=p['sound_delay']<=max(0,p['end']-p['start']-.18) for p in shots));self.assertEqual(sum(p['sound']=='pop' for p in shots),1);self.assertEqual(shots[-1]['transition'],'fade')
 def test_running_generation_question_uses_typed_status(self):
  from app_capabilities import status_answer
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close)
  self.assertIn('nincs futó feladat',status_answer(s,'Most mi generálódik?'))
 def test_semantic_break_needs_independent_pause_or_scene_evidence(self):
  from semantic_boundaries import apply
  from story_director import event_catalog
  c=[dict(id=0,source=0,start=0,end=5,text='The wasp is back in the room.'),dict(id=1,source=0,start=6,end=12,text='Who received the election votes from the jury?')]
  apply(c,[],[[1.,0.],[0.,1.]])
  self.assertTrue(c[1]['event_break']);self.assertEqual(len(event_catalog(c)),2)
  c[1]['start']=5.1;c[1].pop('event_break');apply(c,[],[[1.,0.],[0.,1.]])
  self.assertNotIn('event_break',c[1])
 def test_editorial_stage_honors_manually_selected_agent_model(self):
  from autonomous import ask_json
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);a=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];s.db.execute("UPDATE agents SET model='qwen2.5:14b' WHERE id=?",(a,));s.db.commit();jid=s.enqueue(a,'test');job=dict(s.db.execute('select * from jobs where id=?',(jid,)).fetchone())
  with patch('studio.local_api',return_value=dict(message=dict(content='{"ok":true}'))) as api:ask_json(s,job,'Read only.',{})
  self.assertEqual(api.call_args.args[2]['model'],'qwen2.5:14b')
 def test_hook_teaser_allows_flashback_but_body_keeps_causal_order(self):
  from story_director import check_story
  c=[dict(id=i,source=0,start=i*5,end=i*5+5,text='A real event.') for i in range(4)]
  check_story(dict(unit_ids=[3,0,1,2]),{},c)
  with self.assertRaisesRegex(ValueError,'időrendben'):check_story(dict(unit_ids=[3,2,0,1]),{},c)
 def test_review_schema_and_visual_evidence_are_scoped_to_selected_event(self):
  from autonomous import ask_json,EDITOR_REVIEW
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close);a=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];jid=s.enqueue(a,'test');job=dict(s.db.execute('select * from jobs where id=?',(jid,)).fetchone())
  c=[dict(id=i,source=0,start=t,end=t+5,text='An actual incident.',visual_samples=[dict(seconds=t+1,action='Actual matching frame.')]) for i,t in enumerate((0,5,100,105))]
  with patch('studio.local_api',return_value=dict(message=dict(content='{}'))) as api:ask_json(s,job,EDITOR_REVIEW,dict(catalog=c,director=dict(event_id=1),visual_observations=[dict(summary='A different source-wide scene.')]))
  request=api.call_args.args[2];evidence=json.loads(request['messages'][1]['content']);self.assertEqual([u['id'] for u in evidence['catalog']],[2,3]);self.assertEqual(request['format']['properties']['plan']['properties']['hook']['enum'],[2,3]);self.assertNotIn('different source-wide',json.dumps(evidence));self.assertTrue(all(f['seconds']>=100 for o in evidence['visual_observations'] for f in o['frames']))
 def test_adjacent_sentences_remain_individually_selectable(self):
  from editorial import phrase_groups
  units=[dict(start=0,end=3,text='An unrelated introduction.',boundary='sentence',speaker='speaker_0'),dict(start=3.1,end=6,text='The actual incident begins!',boundary='sentence',speaker='speaker_0'),dict(start=6.1,end=6.5,text='No!',boundary='sentence',speaker='speaker_1')]
  grouped=phrase_groups(units,12);self.assertEqual(len(grouped),3);self.assertEqual(grouped[1]['text'],'The actual incident begins!')
 def test_independent_review_can_improve_hook_within_same_event(self):
  from story_director import check_story
  c=[dict(id=i,source=0,start=i*5,end=i*5+5,text='An actual incident.') for i in range(4)]
  d=dict(event_id=0,hook_candidates=[0],payoff_ids=[3],ending_ids=[3]);p=dict(unit_ids=[1,2,3])
  with self.assertRaises(ValueError):check_story(p,d,c)
  check_story(p,d,c,dict(approved=True,hook_candidates=[dict(id=1,reason='The actual incident starts here.')]))
 def test_rejected_story_repairs_same_event_once_without_padding(self):
  from story_director import repair_rejected_event
  c=[dict(id=i,source=0,start=i*5,end=i*5+5,text='A self-contained actual sentence.',seconds=5) for i in range(6)]
  data=dict(director=dict(event_id=0,hook_candidates=[0],context_ids=[1,2],development_ids=[3],payoff_ids=[4],ending_ids=[5]))
  options=repair_rejected_event(data,c,dict(min_seconds=20,max_seconds=40,target_seconds=30,min_shots=2,max_shots=8,length_policy='adaptive'),'The draft mixes subplots.')
  self.assertTrue(options);self.assertTrue(all(o['verified_seconds']==15 for o in options));self.assertTrue(data['director']['repair_attempted']);self.assertEqual(repair_rejected_event(data,c,{},'Again'),[])
 def test_channel_teaser_is_removed_from_body_as_well_as_hook(self):
  from story_director import check_story
  c=[dict(id=i,source=0,start=i*5,end=i*5+5,text=text) for i,text in enumerate(['The actual incident begins.','Stick around to see our next video!','The incident ends here.'])]
  with self.assertRaisesRegex(ValueError,'reklámot'):check_story(dict(unit_ids=[0,1,2]),{},c)
