import json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from short_style import DEFAULT,requested_settings,select_montage,validated,caption_preset,validate_output,source_matches,save,get
from media_inference import finite_json,valid_interval
from montage import write_word_captions
from studio import Studio
from commander import prepare,enqueue,run,schema

class ProductionContractTests(unittest.TestCase):
 def test_explicit_hungarian_ranges(self):
  for text in ('1-1,5 perces videót kérek','60mp - 90mp között','60 to 90 seconds'):
   with self.subTest(text=text):
    data=requested_settings(text);self.assertEqual((data['min_seconds'],data['max_seconds']),(60,90))
 def test_complaint_is_not_new_duration(self):
  data=requested_settings('összesen 17 mp a videó, a szöveg az alsó harmadban legyen')
  self.assertNotIn('min_seconds',data);self.assertEqual(data['caption_position'],'lower-third')
 def test_short_ai_plan_cannot_pass(self):
  tracks=[dict(source=dict(duration=40),transcript=dict(segments=[]))]
  choice=dict(shots=[dict(source=0,start=i*5,end=i*5+4) for i in range(4)])
  with self.assertRaisesRegex(ValueError,'részlet|beszédrészlet'):select_montage(choice,tracks,DEFAULT)
 def test_valid_duration_is_accepted(self):
  shots=[dict(source=0,start=i*7,end=i*7+6) for i in range(10)]
  result=select_montage(dict(shots=shots),[dict(source=dict(duration=100))],DEFAULT)
  self.assertEqual(result['duration'],60)
 def test_unrelated_or_partial_subject_rejected(self):
  q='IShowSpeed meets Cristiano Ronaldo top moments'
  for title in ("Zlatan bicycle kick",'Cristiano Ronaldo lie detector interview'):
   self.assertFalse(source_matches(q,dict(title=title)))
  self.assertTrue(source_matches(q,dict(title='IShowSpeed finally meets Cristiano Ronaldo')))
 def test_layout_is_encoded_in_ass_and_checked(self):
  preset=caption_preset(DEFAULT)
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/'captions.ass';write_word_captions([dict(start=0,end=1,text='Hello')],dest,preset=preset)
   self.assertIn(r'\pos(486,1560)\clip(108,1320,864,1580)',dest.read_text())
  validate_output(dict(duration=75,caption_style=preset),DEFAULT)
  for manifest in (dict(duration=17,caption_style=preset),dict(duration=75,caption_style=dict(anchor=[486,1200]))):
   with self.assertRaises(ValueError):validate_output(manifest,DEFAULT)
 def test_nonfinite_whisper_data_remains_valid_json(self):
  result=finite_json(dict(prob=float('nan'),score=float('inf'),start=0,end=1))
  json.dumps(result,allow_nan=False);self.assertIsNone(result['prob']);self.assertTrue(valid_interval(result));self.assertFalse(valid_interval(dict(start=None,end=1)))
 def test_impossible_settings_rejected(self):
  with self.assertRaises(ValueError):validated(DEFAULT,dict(min_seconds=90,max_seconds=60))

class ControlContractTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close);schema(self.s)
 def test_settings_persist_for_next_run(self):
  save(self.s,'universe',dict(min_seconds=40,max_seconds=60,target_seconds=50,caption_position='lower-third'))
  self.assertEqual(get(self.s,'universe')['min_seconds'],40)
 def test_graph_preflight_does_not_leave_new_agents(self):
  with self.assertRaisesRegex(ValueError,'kapcsolata'):
   prepare(self.s,'universe',[dict(type='agent_save',agent=dict(id='new',name='New')),dict(type='graph_run',agent='new')])
  self.assertFalse(self.s.db.execute("SELECT 1 FROM agents WHERE id='new'").fetchone())
 def test_editor_without_render_tool_rejected(self):
  with self.assertRaisesRegex(ValueError,'render_short'):
   prepare(self.s,'universe',[dict(type='agent_save',agent=dict(id='new',name='New',role='Videószerkesztő',tools=['read_web']))])
 def test_empty_plan_never_claims_completed_edit(self):
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]):jid=enqueue(self.s,'universe','Javítsd a hibás JSON fájlt','qwen3.5:9b')
  job=dict(self.s.db.execute('select * from jobs where id=?',(jid,)).fetchone())
  response=dict(message=dict(content=json.dumps(dict(reply='A JSON-t javítottam.',actions=[],reads=[]))))
  from execution_queue import DeferredExecution
  with patch('studio.local_api',return_value=response):
   for _ in range(12):
    try:run(self.s,job);break
    except DeferredExecution:pass
  text=self.s.db.execute('select response from command_turns where job=?',(jid,)).fetchone()[0]
  self.assertIn('Nem hajtottam végre',text)

class ExactSettingsTests(ControlContractTests):
 def test_exact_settings_do_not_require_an_available_model(self):
  self.s.db.execute("UPDATE projects SET name='YouTube Shorts' WHERE id='universe'");self.s.db.commit()
  with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]):jid=enqueue(self.s,'universe','Állítsd be a YouTube Shorts videót 60–90 másodpercre, a feliratot az alsó harmadba. Ne indíts videót.','qwen3.5:9b')
  job=dict(self.s.db.execute('select * from jobs where id=?',(jid,)).fetchone())
  with patch('studio.local_api',side_effect=AssertionError('Settings require no inference')):run(self.s,job)
  self.assertEqual(get(self.s,'universe')['min_seconds'],60)
  self.assertEqual(self.s.db.execute('select status from command_turns where job=?',(jid,)).fetchone()[0],'done')
 def test_delegated_short_render_cannot_bypass_saved_duration(self):
  from render_tools import run_render
  save(self.s,'universe',dict(min_seconds=60,max_seconds=90,target_seconds=75))
  source=self.s.safe_path('universe','inputs/test.mp4');source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(b'fixture')
  agent=dict(project='universe',tools=['render_short'])
  with patch('render_tools.subprocess.Popen',side_effect=AssertionError('Must reject before rendering')):
   with self.assertRaisesRegex(ValueError,'renderhossz'):
    run_render(self.s,agent,dict(source_video='inputs/test.mp4',start=0,duration=17,layout='fit'),'test-job')
