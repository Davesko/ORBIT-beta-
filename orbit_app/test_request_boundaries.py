import json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import commander,request_intent,model_router,mail_search,automations
class RequestBoundaries(unittest.TestCase):
 def test_image_concept_never_short(self):
  p='Készíts egy elegáns koncepcióképet egy videókliphez a helyi FLUX modellel.'
  self.assertEqual(model_router.task_type(p),'image');self.assertFalse(request_intent.allow_shortcut(p))
 def test_video_generation_not_editing(self):
  self.assertEqual(request_intent.media_intent('generálj egy videót a helyi modellel amiben egy nő sétál'),'generate_video')
  self.assertFalse(request_intent.allow_shortcut('hf.co/ManishThota/Ollama_Video_llama_7B:F16 modellel generálj egy videót'))
 def test_wan_keeps_explicit_format_and_rejects_unsupported_length(self):
  import local_video as video
  prompt='Generálj egy 4,5 másodperces 1080×1920 pixeles videót.'
  aspect=video.orientation(prompt)
  self.assertEqual(aspect,'portrait')
  self.assertEqual(video.video_spec(prompt,aspect),(72,(1080,1920)))
  self.assertEqual(video.graph(prompt,aspect,72)['6']['inputs']['length'],73)
  with self.assertRaisesRegex(ValueError,'0,5–5'):video.video_spec('10 mp álló', 'portrait')
 def test_named_video_checkpoints_are_bound_to_their_own_graph(self):
  import local_video as video
  self.assertEqual(video.requested_model('A Wan 2.2 TI2V 5B FP16 modellel dolgozz.'),'wan22')
  self.assertEqual(video.requested_model('Wan 2.1 I2V 14B FP8 modellel.'),'wan21-i2v')
  self.assertEqual(video.requested_model('Wan 2.1 T2V 14B FP8 modellel.'),'wan21-t2v-14b')
  self.assertIsNone(video.requested_model('Helyi modellel generálj egy videót.'))
  for name in ('Wan 2.2 TI2V 5B MLX Q8', 'Wan 2.2 Fun 5B Control', 'Wan 2.2 I2V A14B', 'LTX 2.5','„Unknown”'):
   with self.subTest(name=name),self.assertRaisesRegex(ValueError,'futtató'):
    video.requested_model('Készíts egy videót a '+name.replace('„','"').replace('”','"')+' modellel.')
  self.assertEqual(video.video_spec('4 mp, 9:16','portrait','wan22')[0],96)
  text=video.graph('Action','portrait',96,model='wan22')
  image=video.graph('Action','portrait',96,model='wan22',image='start.png')
  self.assertEqual(text['1']['inputs']['unet_name'],'wan2.2_ti2v_5B_fp16.safetensors')
  self.assertEqual(text['6']['class_type'],'Wan22ImageToVideoLatent')
  self.assertEqual(image['9'],{'class_type':'VAEDecode','inputs':{'samples':['8',0],'vae':['3',0]}})
  self.assertEqual(text['10']['inputs']['fps'],24)
  self.assertNotIn('start_image',text['6']['inputs'])
  self.assertEqual(image['6']['inputs']['start_image'],['12',0])
  self.assertEqual(video.graph('Action','portrait',32,model='wan21-i2v',image='start.png')['6']['class_type'],'WanImageToVideo')
 def test_assistant_and_hook_keep_the_requested_video_model(self):
  from bridge import dispatch
  import story_animation as story
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));self.addCleanup(s.db.close)
   pid=s.create_project('YouTube Shorts','test');hook=story.install_team(s,pid)['agents'][0]
   prompts=('Készíts 4 másodperces videót Wan 2.2 TI2V 5B modellel.',
            'Készíts egy animált történetet Wan 2.2 TI2V 5B modellel, 20 mp legyen.')
   for prompt,action_type in zip(prompts,('generate_video','graph_run')):
    commander.enqueue(s,'universe',prompt,global_mode=True)
    with patch('studio.local_api',side_effect=AssertionError('Named video production should not need a planner')):
     self.assertTrue(s.run_next(('command',)))
    row=s.db.execute('SELECT status,actions FROM command_turns ORDER BY created DESC LIMIT 1').fetchone()
    action,=json.loads(row['actions'])
    self.assertEqual((row['status'],action['type'],action['video_model']),('queued_apply',action_type,'wan22'))
   result=dispatch(dict(action='chat',project=pid,agent=hook,prompt=prompts[1]),s)
   self.assertEqual(s.db.execute("SELECT json_extract(payload,'$.video_model') FROM jobs WHERE json_extract(payload,'$.run')=? AND json_extract(payload,'$.story_step')='render'",(result['run'],)).fetchone()[0],'wan22')
   with self.assertRaisesRegex(ValueError,'futtató'):
    dispatch(dict(action='chat',project=pid,agent=hook,prompt=prompts[1].replace('5B','5B MLX Q8')),s)
 def test_story_shots_use_distinct_actions_and_real_image_conditioning(self):
  import local_video,story_animation as story
  scene=dict(set='cafe',actor='milo',action='react',prop='coffee',blocking='left',camera='Static')
  draft=dict(title='Café',scenes=[dict(scene,framing=framing,caption=f'Line {i}.',
        visual_action=f'The character performs distinct action {i}.',visible_result=f'Visible result {i}.')
        for i,framing in enumerate(story.FRAMINGS)])
  plan=story.script_plan(draft,{},20)
  shots=story.shots_for(plan)
  self.assertEqual(sum(shot['frames'] for shot in shots),480)
  self.assertEqual(len(shots),5)
  self.assertTrue(all(shot['frames']<=120 for shot in shots))
  draft['scenes'][1]['caption']=draft['scenes'][0]['caption']
  self.assertEqual(story.script_plan(draft,{},20)['scenes'][1]['caption'],'')
  graph=local_video.camera_graph('Action',32,'reference.png','Pan Left',12,(288,512))
  self.assertEqual(graph['6']['class_type'],'WanCameraImageToVideo')
  self.assertEqual(graph['6']['inputs']['start_image'],['12',0])
  self.assertEqual(graph['8']['inputs']['latent_image'],['6',2])
  for shot in draft['scenes']:shot['framing']='wide'
  with self.assertRaisesRegex(ValueError,'három képkivágás'):story.script_plan(draft,{},20)
 def test_story_team_is_separate_and_installed_by_chat(self):
  import story_animation as story
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));self.addCleanup(s.db.close)
   pid=s.create_project('YouTube Shorts','test')
   s.save_room(pid,dict(id=story.ROOM,name='Történetműhely',width=11,height=9))
   plot=story.agent_ids(pid)['script']
   s.save_agent(dict(id=plot,project=pid,room=story.ROOM,name='Plot',role='Történet és jelenetterv',prompt='My existing storyboard instructions.'))
   original={a['id'] for a in s.rows('SELECT id FROM agents WHERE project=?',(pid,))}
   prompt='épyts egy második agent csapatot a youtubeshort projektbe történetalapú animációhoz.'
   commander.enqueue(s,pid,prompt,global_mode=True)
   with patch('studio.local_api',side_effect=AssertionError('Story setup should bypass the planner')):
    self.assertTrue(s.run_next(('command',)))
    self.assertTrue(s.run_next(('command_apply',)))
   team=story.install_team(s,pid)
   self.assertEqual({a['id'] for a in s.rows('SELECT id FROM agents WHERE project=?',(pid,))},original|set(team['agents']))
   self.assertEqual(len(team['rooms']),5)
   self.assertEqual([s.agent(a)['name'] for a in team['agents']],['Hook','Art','Plot','Ink','Sound','Frame'])
   self.assertEqual({s.agent(a)['room'] for a in team['agents']},set(team['rooms']))
   self.assertEqual(s.agent(plot)['prompt'],'My existing storyboard instructions.')
   run=s.enqueue_graph(pid,team['agents'][0],'Make a 7-second original animation.')
   jobs=s.rows("SELECT payload FROM jobs WHERE json_extract(payload,'$.run')=? ORDER BY rowid",(run['run'],))
   self.assertEqual([json.loads(j['payload'])['story_step'] for j in jobs],list(story.ROLES))
   self.assertEqual(json.loads(jobs[-1]['payload'])['required_outputs'],['video'])
   task=s.db.execute('SELECT config FROM automations WHERE id=?',(team['task'],)).fetchone()
   self.assertEqual(json.loads(task[0])['prompt'],story.DEFAULT_BRIEF)
   context=story.episode_ideas(s,dict(project=pid,agent=team['agents'][0]),story.DEFAULT_BRIEF)
   self.assertIn('idea_angle',context)
   idea=dict(premise='Milo buys the same gadget again.',hook='It breaks immediately.',escalation='Bea looks at the box.',payoff='He paid for a used box.',hook_caption='Broken before opening!',payoff_caption='The receipt is inside.')
   self.assertTrue(story.valid_idea(idea,context))
   context['recent_ideas_to_avoid']=[dict(premise=idea['premise'])]
   self.assertFalse(story.valid_idea(idea,context))
 def test_original_episode_has_varied_visuals_and_exact_audio_timing(self):
  import story_episode as episode
  profile=episode.profile(0,6)
  self.assertNotEqual(profile['style'],episode.profile(1,6)['style'])
  self.assertNotEqual(profile['arc'],episode.profile(1,6)['arc'])
  art={k:f'Distinct reference for {k}' for k in episode.ART_FIELDS}
  scenes=[dict(setting='Night train carriage',opening_image=f'Fox looks at station sign {i}.',
               visual_action=f'The fox presses the switch marked {i}.',visible_result=f'The lamp number {i} lights up.',
               camera='Static',cast='lead',voice='Look.',caption='Look.',sfx='chime') for i in range(4)]
  draft=dict(title='A Sign of Life',scenes=scenes)
  premise=dict(profile=profile,art=art)
  plan=episode.plan(draft,premise,6)
  self.assertEqual(plan['frames'],144)
  self.assertEqual([s['framing'] for s in plan['scenes']],['detail','wide','close','two-shot'])
  opening,motion=episode.prompts(plan,plan['scenes'][0],'The carriage is dark.')
  self.assertIn(art['lead'],opening)
  self.assertIn(scenes[0]['opening_image'],opening)
  self.assertIn(scenes[0]['visible_result'],motion)
  scenes[1]['opening_image']=scenes[0]['opening_image']
  # A repeated first frame starts where the previous shot ended instead of failing the whole episode.
  self.assertEqual(episode.plan(draft,premise,6)['scenes'][1]['opening_image'],scenes[0]['visible_result'])
  scenes[2]['visual_action']=scenes[1]['visual_action']
  with self.assertRaisesRegex(ValueError,'visual_action of misdirection repeats clue'):
   episode.plan(draft,premise,6)
  repaired=episode.plan(draft,premise,6,repair=True)['scenes']
  self.assertNotEqual(repaired[1]['visual_action'],repaired[2]['visual_action'])
 def test_kokoro_sample_lists_can_be_mixed(self):
  from types import SimpleNamespace
  import story_audio
  rate=story_audio.RATE
  voice=story_audio.fit_voice([.1,-.25],rate,100,None)
  self.assertEqual((voice*.5).tolist()[1],-.125)
  tts=SimpleNamespace(generate=lambda **_:SimpleNamespace(samples=[.1]*round(rate*1.4),sample_rate=rate))
  scenes=[dict(frames=24,voice='Long opening'),dict(frames=48,voice=''),dict(frames=48,voice='Last line')]
  first,last=story_audio.voiceover(tts,scenes,rate*5,1,None)
  self.assertGreater(first[0]+len(first[1]),rate)
  self.assertLess(first[0]+len(first[1]),last[0])
  self.assertLess(last[0]+len(last[1]),rate*5)
 def test_plain_short_and_automatic_video_requests_start_story_without_planner(self):
  import story_animation as story
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));self.addCleanup(s.db.close)
   pid=s.create_project('YouTube Shorts','test');team=story.install_team(s,pid)
   for prompt in ('készíts egy saját videót egy történettel a youtube shorts projektben',
                  'Indíts egy YouTube Shorts ötletet.','Indíts automata videógenerálást.','Indítsd el a YouTube Shortsot.',
                  'készíts egy animált történetet, 25 mp legyen,',
                  'készíts egy animált történetet a youtube shorts projektben, 25 mp legyen,'):
    commander.enqueue(s,'universe',prompt,global_mode=True)
    with patch('studio.local_api',side_effect=AssertionError('Story launch should bypass the planner')):
     self.assertTrue(s.run_next(('command',)))
    row=s.db.execute('SELECT actions,status FROM command_turns ORDER BY created DESC LIMIT 1').fetchone()
    action,=json.loads(row['actions'])
    self.assertEqual((row['status'],action['type'],action['project'],action['agent']),('queued_apply','graph_run',pid,team['agents'][0]))
   for other in ('Készíts egy GTA 6 Shorts videót.', 'Vágj Shortot ebből: https://youtu.be/abcdef12345',
                 'Készíts 4 másodperces videót a Wan modellel.', 'Indíts automata videógenerálást minden nap.'):
    self.assertFalse(story.production_request(other))
 def test_hook_chat_starts_graph_only_for_an_explicit_production_request(self):
  from bridge import dispatch
  import story_animation as story
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));self.addCleanup(s.db.close)
   pid=s.create_project('YouTube Shorts','test');team=story.install_team(s,pid)
   hook=team['agents'][0]
   prompt='indíts egy youtube shorts ötletet, 20-30 mp hosszú videó, animált történetmesélés.'
   self.assertEqual(story.video_seconds(prompt),25)
   start=dispatch(dict(action='chat',project=pid,agent=hook,prompt=prompt),s)
   self.assertEqual(start['job'],start['jobs'][hook])
   rows=s.rows("SELECT kind,payload FROM jobs WHERE json_extract(payload,'$.run')=? ORDER BY rowid",(start['run'],))
   self.assertEqual([(r['kind'],json.loads(r['payload'])['story_step']) for r in rows],
                    [('graph',step) for step in story.ROLES])
   self.assertTrue(all(json.loads(r['payload'])['story_brief']==prompt for r in rows))
   for note in ('Írj egy forgatókönyvet.', 'Készíts csak egy forgatókönyvet egy animált történethez.',
                'Holnap készíts egy animált történetet.', 'Ne készíts animált történetet.',
                'Készíts egy képet a Történetműhelyben.'):
    self.assertNotIn('run',dispatch(dict(action='chat',project=pid,agent=hook,prompt=note),s))
   self.assertNotIn('run',dispatch(dict(action='chat',project=pid,agent=team['agents'][1],prompt=prompt),s))
   self.assertIn('run',dispatch(dict(action='agent_run',project=pid,agent=hook),s))
 def test_story_sound_can_resume_without_rerunning_story_planning(self):
  from bridge import dispatch
  import story_animation as story
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));self.addCleanup(s.db.close)
   pid=s.create_project('YouTube Shorts','test')
   agents=story.install_team(s,pid)['agents']
   run=s.enqueue_graph(pid,agents[0],story.DEFAULT_BRIEF)
   for agent,status in zip(agents,['done','done','done','done','failed','blocked']):
    s.db.execute('UPDATE jobs SET status=? WHERE id=?',(status,run['jobs'][agent]))
   s.db.commit()
   sound=run['jobs'][agents[-2]]
   reply=dispatch(dict(action='production_resume',project=pid,id=sound),s)
   self.assertEqual(list(reply['jobs'].values()),[sound,run['jobs'][agents[-1]]])
   rows=s.rows("SELECT status FROM jobs WHERE json_extract(payload,'$.run')=? ORDER BY rowid",(run['run'],))
   self.assertEqual([r['status'] for r in rows],['done','done','done','done','queued','queued'])
   self.assertTrue(dispatch(dict(action='production_resume',project=pid,id=sound),s)['existing'])
 def test_vertical_video_goes_directly_to_local_renderer_and_appears_in_chat(self):
  import local_video
  prompt='generállj egy 9:16 álló formátumú videót, amiben egy 3d animált videó ahol egy lány ugrál egy réten.'
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));self.addCleanup(s.db.close)
   commander.enqueue(s,'universe',prompt,global_mode=True)
   with patch('studio.local_api',side_effect=AssertionError('The assistant planner must not be called')), \
        patch('model_hub.config',return_value={'mount':'/Volumes/model-store'}):
    self.assertTrue(s.run_next(('command',)))
   row=s.db.execute('SELECT id,actions,status FROM command_turns').fetchone()
   self.assertEqual(row['status'],'queued_apply')
   action,=json.loads(row['actions'])
   self.assertEqual((action['type'],action['orientation']),('generate_video','portrait'))
   width,height=local_video.SIZES[action['orientation']]
   self.assertEqual(width*16,height*9)
   self.assertFalse(s.run_next(('command_apply',)))
   def create_video(s,job,_):
    path=s.safe_path(job['project'],'media/test.mp4');path.parent.mkdir()
    path.touch()
    s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',
                 ('sample-video',job['project'],path.name,str(path),'video',0,job['id']))
    s.db.commit()
    return str(path)
   with patch('local_video.generate',side_effect=create_video) as render:
    self.assertTrue(s.run_next(('command_apply',),foreground_video=True))
   render.assert_called_once()
   self.assertEqual(s.db.execute('SELECT status FROM command_turns WHERE id=?',(row['id'],)).fetchone()[0],'done')
   turn,=commander.state(s,'universe',True)['turns']
   self.assertEqual(turn['artifacts'][0]['id'],'sample-video')
 def test_compound_is_not_one_video(self):
  self.assertFalse(request_intent.allow_shortcut('Holnap készíts 3 shorts videót GTA6 témában, közben elemezd az emailjeimet'))
 def test_named_mail_queries(self):
  self.assertEqual(mail_search.search_request('keresd meg nekem az emailjeim között Matuz al való beszélgetéseimet.'),'matuz')
  self.assertEqual(mail_search.search_request('keres meg nekem az IPON al kapcsolatos emailjeimet.'),'ipon')
 def test_preflight_prevents_wrong_action(self):
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));commander.schema(s)
   with self.assertRaisesRegex(ValueError,'generatív'):commander.prepare(s,'universe',[dict(type='start_shorts',project='universe',query='woman')],True,user_request='generálj egy videót a helyi modellel')
   s.db.close()
 def test_email_search_older_and_sent(self):
  import email_hub
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));email_hub.schema(s)
   s.db.execute("INSERT INTO emails(id,account,folder,uid,sender,sender_name,recipients,subject,body,date) VALUES('old','a','Sent',1,'me','Me','matuz@example.com','Régi beszélgetés','Hello',1)")
   self.assertEqual(mail_search.find(s,'Matuz')[0]['id'],'old');s.db.close()
 def test_general_automation_without_agent(self):
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));s.project('universe')
   a=automations.save(s,'universe',dict(name='Kutatás',kind='assistant',config=dict(prompt='Research dropshipping products and draft a website plan'),enabled=False,daily_goal=1))
   with patch('commander.enqueue',return_value='queued-job') as enqueue:
    automations.launch(s,'universe',a,manual=True)
    self.assertTrue(enqueue.call_args.kwargs['global_mode'])
   s.db.close()
 def test_private_graph_uses_saved_memory(self):
  import memory_brain,personal_graph
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Path(d));memory_brain.schema(s)
   memory_brain.save(s,None,'I prefer local models and local automation','preference')
   g=personal_graph.export(s);self.assertEqual(len(g['nodes']),1)
   self.assertEqual((Path(d)/'private/memory-graph/graph.json').stat().st_mode&0o777,0o600);s.db.close()
