import json,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from commander import schema,enqueue,run,state,approve,prepare,apply,english_image_prompt,overview,memory_save,preferences_save,retry_agent
from model_router import choose,task_type
MODELS=['qwen2.5:14b','qwen2.5-coder:14b','qwen2.5vl:7b']
class RoutingTests(unittest.TestCase):
 def test_task_mapping_and_manual_media_switch(self):
  self.assertEqual(choose('Fejlessz egy Python alkalmazást',MODELS)['model'],'qwen2.5-coder:14b')
  route=choose('Generálj egy képet egy zöld koboldról',MODELS,'qwen2.5-coder:14b');self.assertEqual(route['engine'],'FLUX.1 Schnell');self.assertTrue(route['automatic'])
  self.assertEqual(choose('Mi van ezen?',MODELS,image=True)['model'],'qwen2.5vl:7b')
  self.assertEqual(choose('Szia',MODELS)['model'],'qwen2.5:14b')
 def test_discussion_does_not_start_generation(self):
  self.assertEqual(task_type('Hogyan tudok képet generálni?'),'chat')
  self.assertEqual(task_type('Milyen modell tud videót generálni?'),'chat')
  self.assertEqual(task_type('Készíts egy Shorts videót a Speed klipből'),'video')
 def test_unavailable_model_fallback_is_explicit(self):
  r=choose('Írj kódot',['qwen2.5:14b']);self.assertTrue(r['fallback'])
  with self.assertRaises(ValueError):choose('Analyze', ['qwen2.5-coder:14b'],image=True)

class PersonalTests(unittest.TestCase):
 def setUp(self):
  language=patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts));language.start();self.addCleanup(language.stop)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name)/'orbit');self.addCleanup(self.s.db.close);schema(self.s)
  self.models=patch('model_hub.models',return_value=[dict(name=m) for m in MODELS]);self.models.start();self.addCleanup(self.models.stop)
 def test_global_conversation_survives_project_switch(self):
  enqueue(self.s,'universe','Szia','auto',global_mode=True)
  other=self.s.create_project('Other','Other work')
  a=state(self.s,'universe',True);b=state(self.s,other,True)
  self.assertEqual(a['turns'][0]['id'],b['turns'][0]['id'])
  self.assertFalse(state(self.s,other)['turns'])
 def test_ambiguous_global_mutation_cannot_target_open_project(self):
  with self.assertRaises(ValueError):prepare(self.s,'universe',[dict(type='agent_run',agent='random',prompt='work')],True)
 def test_image_request_auto_queues_local_render_without_review(self):
  jid=enqueue(self.s,'universe','Generálj egy képet egy zöld gömbről','auto',global_mode=True)
  job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  response=dict(message=dict(content=json.dumps(dict(reply='image plan',reads=[],actions=[dict(type='generate_image',prompt='A green orb',width=512,height=512)]))))
  with patch('studio.local_api',return_value=response):run(self.s,job)
  turn=state(self.s,'universe',True)['turns'][0];self.assertEqual(turn['status'],'queued_apply');self.assertEqual(turn['actions'][0]['project'],'universe')
  self.assertEqual(turn['actions'][0]['prompt'],'Generálj egy képet egy zöld gömbről')
  self.assertEqual(self.s.db.execute('SELECT kind FROM jobs WHERE id=?',(turn['job'],)).fetchone()[0],'command_apply')
 def test_global_approval_uses_original_job_project(self):
  jid=enqueue(self.s,'universe','Írj kódot','auto',global_mode=True)
  t=self.s.db.execute('SELECT id FROM command_turns WHERE job=?',(jid,)).fetchone()[0]
  self.s.db.execute("UPDATE command_turns SET status='review'");self.s.db.commit();other=self.s.create_project('Other','desc')
  new=approve(self.s,other,t,True);self.assertEqual(self.s.db.execute('SELECT project FROM jobs WHERE id=?',(new,)).fetchone()[0],'universe')
 def test_image_prompt_is_translated_before_rendering(self):
  jid=enqueue(self.s,'universe','Szia','auto',global_mode=True);job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  with patch('studio.local_api',return_value={'message':{'content':'{"prompt":"A glowing green crystal orb in a dark studio"}'}}) as api:
   text=english_image_prompt(self.s,job,'Zöld kristálygömb egy sötét stúdióban')
  self.assertIn('green crystal orb',text);self.assertEqual(api.call_args.args[2]['format']['required'],['prompt'])

 def test_latest_finished_video_opens_without_model_read_loop(self):
  pid=self.s.create_project('YouTube Shorts','clips');aid=uuid.uuid4().hex
  self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(aid,pid,'ready.mp4',str(self.s.root/'projects'/pid/'renders/ready.mp4'),'video',time.time(),'render-child'));self.s.db.commit()
  jid=enqueue(self.s,'universe','Mutasd meg a YouTube Shorts projekt legutóbbi kész videóját.','auto',global_mode=True)
  job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  with patch('studio.local_api',side_effect=AssertionError('No planning call needed')):run(self.s,job)
  turn=state(self.s,'universe',True)['turns'][0];self.assertEqual(turn['status'],'queued_apply');self.assertEqual(turn['actions'][0]['id'],aid)

 def test_global_overview_contains_agents_and_architecture(self):
  other=self.s.create_project('Other','clips');data=overview(self.s)
  self.assertTrue(any(a['project']==other for a in data['agents']));self.assertIn('delegation',data['architecture']);self.assertIn('recent_jobs',data)

 def test_named_agent_resolves_only_inside_named_project(self):
  other=self.s.create_project('Other','clips')
  plan=prepare(self.s,'universe',[dict(type='agent_run',project='Other',agent='Atlas',prompt='Read the project brief.')],True)
  self.assertEqual(plan[0]['project'],other);self.assertEqual(self.s.agent(plan[0]['agent'])['project'],other)
  wrong=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  with self.assertRaises(ValueError):prepare(self.s,'universe',[dict(type='agent_run',project=other,agent=wrong,prompt='work')],True)

 def test_internal_delegation_auto_queues_and_creates_linked_agent_job(self):
  jid=enqueue(self.s,'universe','Ask Atlas to read the brief','auto',global_mode=True);job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
  response=dict(message=dict(content=json.dumps(dict(reply='Delegating',reads=[],actions=[dict(type='agent_run',project='universe',agent='Atlas',prompt='Read the project brief and report gaps in Hungarian.')]))))
  with patch('studio.local_api',return_value=response):run(self.s,job)
  turn=state(self.s,'universe',True)['turns'][0];self.assertEqual(turn['status'],'queued_apply')
  apply_job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(turn['job'],)).fetchone());apply(self.s,apply_job)
  updated=state(self.s,'universe',True)['turns'][0];children=[j for j in updated['linked_jobs'] if j['id']!=apply_job['id']];self.assertEqual(len(children),1)
  child=self.s.db.execute('SELECT agent,prompt FROM jobs WHERE id=?',(children[0]['id'],)).fetchone();self.assertEqual(self.s.agent(child['agent'])['name'],'Atlas');self.assertIn('Read the project brief',child['prompt']);self.assertIn('Original user request and constraints:',child['prompt']);self.assertIn('Ask Atlas to read the brief',child['prompt'])
  self.s.db.execute("UPDATE jobs SET status='failed' WHERE id=?",(children[0]['id'],));self.s.db.commit()
  retry=retry_agent(self.s,turn['id'],children[0]['id']);self.assertEqual(self.s.db.execute('SELECT prompt FROM jobs WHERE id=?',(retry,)).fetchone()[0],child['prompt'])
  with self.assertRaises(ValueError):retry_agent(self.s,turn['id'],children[0]['id'])

 def test_app_action_cannot_override_scope_or_publish(self):
  for action in [dict(type='app_action',project='universe',operation='youtube_upload',args={}),dict(type='app_action',project='universe',operation='pipeline',args={'project':'elsewhere'})]:
   with self.assertRaises(ValueError):prepare(self.s,'universe',[action],True)

 def test_personal_memory_and_preferences_persist_and_validate(self):
  memory_save(self.s,dict(key='language',content='Prefer Hungarian replies.',display='Magyar válaszokat kérek.'));preferences_save(self.s,dict(theme='violet',motion=False))
  self.assertEqual(state(self.s,'universe',True)['memory'][0]['display'],'Magyar válaszokat kérek.');self.assertEqual(overview(self.s)['preferences']['theme'],'violet')
  with self.assertRaises(ValueError):preferences_save(self.s,dict(theme='bad',motion=True))
  self.assertFalse(overview(self.s)['preferences']['motion'])

 def test_video_artifact_from_linked_job_is_returned_to_global_chat(self):
  jid=enqueue(self.s,'universe','Szia','auto',global_mode=True);turn=self.s.db.execute('SELECT id FROM command_turns WHERE job=?',(jid,)).fetchone()[0]
  aid=uuid.uuid4().hex;self.s.db.execute('INSERT INTO command_links VALUES(?,?)',(turn,'render-child'));self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(aid,'universe','ready.mp4',str(self.s.root/'projects/universe/renders/ready.mp4'),'video',time.time(),'render-child'));self.s.db.commit()
  self.assertEqual(state(self.s,'universe',True)['turns'][0]['artifacts'][0]['id'],aid)
if __name__=='__main__':unittest.main()
