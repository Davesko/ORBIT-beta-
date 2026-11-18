import hashlib,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from autonomous import run_step,plan_schema
from editorial import unit_catalog
from short_style import DEFAULT

class SelectionRepairTests(unittest.TestCase):
 def test_invalid_draft_goes_to_fresh_valid_candidates_before_content_review(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));self.addCleanup(s.db.close);plan_schema(s)
   aid=s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
   transcript=s.safe_path('universe','input.json');transcript.write_text(json.dumps(dict(segments=[])))
   style=dict(DEFAULT,min_seconds=50,max_seconds=100,max_shot_seconds=12,length_policy='strict')
   source=dict(source_video='actual.mp4',duration=180)
   data=dict(query='fashion',style=style,source=source,tracks=[dict(source=source,transcript_file='input.json',subtitle='input.srt')],visual_analysis=[dict(frames=[dict(seconds=t,action='A runway model wearing wings.') for t in (18,54,90,126,162)])])
   s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','fashion',json.dumps(data),time.time()));s.db.commit()
   jid=s.enqueue(aid,'selection','graph',payload=dict(run='run',auto_step='selection'));job=s.claim(('graph',));inputs=[]
   def answer(studio,job,instruction,evidence):
    inputs.append(evidence)
    if len(inputs)==1:return dict(hook=0,sequence=[999]) # unknown unit: not repairable by expansion
    self.assertNotIn('correction',evidence)
    self.assertEqual(evidence['validation']['authority'],'server_interval_validator')
    c=evidence['candidates'][1]
    return dict(approved=True,candidate_id=c['candidate_id'],hook_candidates=[dict(id=c['hook'],reason='Actual visible wings')],beats=[dict(id=c['sequence'][-1],beat='payoff',reason='Closing runway view')],humor_type='none',payoff_evidence='Visible runway view')
   with patch('semantic_boundaries.enrich'),patch('story_director.direct',side_effect=lambda s,j,d,c,a:d.setdefault('director',{})),patch('source_quality.annotate',side_effect=lambda s,j,t,d:d.setdefault('source_quality',{})),patch('autonomous.ask_json',side_effect=answer):run_step(s,job)
   final=json.loads(s.db.execute('SELECT data FROM short_runs').fetchone()[0])
   self.assertEqual(len(inputs),2);self.assertEqual(final['montage']['duration'],60)
   self.assertEqual(final['tracks'],data['tracks']);self.assertEqual(final['source'],data['source'])

 def test_workspace_migration_removes_stale_rules_and_preserves_originals(self):
  from short_project_files import sync
  from short_prompt_contract import upgraded_prompt
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder)/'orbit');self.addCleanup(s.db.close)
   path=s.safe_path('universe','workspace/subtitle_render_settings.txt');path.parent.mkdir(parents=True,exist_ok=True);path.write_text('MarginV=20 old setting')
   source=s.safe_path('universe','workspace/sources.json');source.write_text(json.dumps(dict(collection_enabled=False,streamers=[dict(name='Saved suggestion')])))
   old=s.safe_path('universe','workspace/publishing-package-old.md');old.write_text('Upload: NOT connected. Historical test.')
   backup=Path(folder)/'backup';sync(s,'universe',backup);sync(s,'universe',backup)
   self.assertEqual((backup/'project-files'/path.name).read_text(),'MarginV=20 old setting')
   self.assertNotIn('MarginV=20',path.read_text());self.assertIn('PRODUCTION-CONTRACT.md',path.read_text())
   self.assertEqual(json.loads(source.read_text())['streamers'][0]['name'],'Saved suggestion')
   self.assertNotIn('collection_enabled',json.loads(source.read_text()));self.assertFalse(json.loads(source.read_text())['historical_collection_enabled'])
   self.assertTrue(old.read_text().startswith('# Historical reference'));self.assertEqual((backup/'project-files'/old.name).read_text(),'Upload: NOT connected. Historical test.')
   self.assertTrue(s.safe_path('universe','workspace/SOURCE-OF-TRUTH.json').is_file())
   prompt='Custom role.\n\nContent-aware production contract (v2): old instructions'
   result=upgraded_prompt(prompt);self.assertNotIn('(v2)',result);self.assertEqual(upgraded_prompt(result),result);self.assertIn('Custom role.',result)
