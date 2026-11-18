import ast,tempfile,unittest
from pathlib import Path
import venture_build as vb
class BytesLiteralRepairTests(unittest.TestCase):
 # The 27B kept writing accented Hungarian text into bytes literals, so server.py never started.
 def test_accented_bytes_literal_becomes_encoded_text(self):
  src="import sys\nmsg=b'{\"error\":\"Érvénytelen JSON\"}'\nraw=rb'\\d+ Ft – ok'\nplain=b'ascii only'\n"
  out=vb.fix_bytes_literals(src)
  ast.parse(out)
  ns={};exec(compile(out,'x','exec'),ns)
  self.assertEqual(ns['msg'],'{"error":"Érvénytelen JSON"}'.encode());self.assertEqual(ns['raw'],'\\d+ Ft – ok'.encode())
  self.assertIn("plain=b'ascii only'",out,'valid literals are untouched')
 def test_other_code_is_left_alone(self):
  self.assertIsNone(vb.fix_bytes_literals("x=1\n"),'nothing to repair')
  self.assertIsNone(vb.fix_bytes_literals("def f(:\n"),'a different syntax error is not guessed at')
 def test_product_folder_is_repaired_in_place(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'server.py').write_text("w=b'Hiba: ő'\n");(Path(d)/'ok.py').write_text("x=1\n")
   self.assertEqual(vb.repair_product(d),['server.py']);ast.parse((Path(d)/'server.py').read_text())
class EditSyntaxTests(unittest.TestCase):
 def test_patch_that_breaks_python_is_refused(self):
  # A block once turned a line into 'self.state = "HALF_OPEN" = "HALF_OPEN"'.
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'server.py').write_text('state = "OPEN"\n')
   out,bad=vb.apply_edits(Path(d),[dict(name='server.py',find='"OPEN"',replace='"HALF_OPEN" = "HALF_OPEN"')])
   self.assertEqual(out,{});self.assertIn('szintaxishiba',bad[0]);self.assertIn('1. sor',bad[0])
   out,bad=vb.apply_edits(Path(d),[dict(name='server.py',find='"OPEN"',replace='"HALF_OPEN"')])
   self.assertEqual(out,{'server.py':'state = "HALF_OPEN"\n'});self.assertEqual(bad,[])
 def test_patch_on_a_file_with_accented_bytes_is_repaired_too(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'server.py').write_text("msg=b'Hiba'\n")
   out,_=vb.apply_edits(Path(d),[dict(name='server.py',find="b'Hiba'",replace="b'Érvénytelen'")])
   ast.parse(out['server.py']);self.assertIn(".encode('utf-8')",out['server.py'])
class TruncatedAnswerTests(unittest.TestCase):
 # 16:35: the answer hit its length limit and a JSON repair then ran for 25 minutes.
 cut='{"milestone_id": "api", "summary": "Javítás", "edits": [{"name": "server.py", "find": "a = 1", "replace": "a = 2"}, {"name": "ocr.py", "find": "x", "repl'
 def test_complete_edit_blocks_survive_a_cut(self):
  kept=vb.salvage(self.cut)
  self.assertEqual(kept['milestone_id'],'api');self.assertEqual(kept['edits'],[dict(name='server.py',find='a = 1',replace='a = 2')])
 def test_cut_before_the_milestone_id_still_keeps_the_work(self):
  # Cycle 158: summary and edits came first, the id was at the end and was cut off.
  cut='{"summary": "Az ocr.py latin-1 kódolását UTF-8-ra cseréltem.", "edits": [{"name": "ocr.py", "find": "latin-1", "replace": "utf-8"}], "acceptance": ["ocr.py --self-te'
  kept=vb.salvage(cut)
  self.assertEqual(kept['milestone_id'],'');self.assertEqual(kept['edits'],[dict(name='ocr.py',find='latin-1',replace='utf-8')])
 def test_truncated_answer_skips_the_model_repair(self):
  from unittest.mock import patch
  from studio import Studio
  s=Studio(Path(tempfile.mkdtemp()));self.addCleanup(s.db.close)
  with patch('studio.local_api',side_effect=AssertionError('no repair call')):
   out=s.repair_json(dict(id='j'),dict(model='qwen3.8:27b-q4_K_M'),self.cut,truncated=True)
  import json;self.assertEqual(json.loads(out)['edits'][0]['replace'],'a = 2')
class FixTargetTests(unittest.TestCase):
 def test_a_failed_live_test_is_fixed_in_the_server(self):
  # The builder kept editing smoke.json (the expectations) while server.py answered 501.
  self.assertEqual(vb.fix_targets_of({'smoke.json':'Élő próba: GET /health → 501','ocr.py':'x'}),['server.py','ocr.py'])
  self.assertEqual(vb.fix_targets_of({'validate.py':'x'}),['validate.py'])
  self.assertEqual(vb.fix_targets_of({'smoke.json':'x','server.py':'y'}),['server.py'])
  order=vb.fix_targets_of({'selfimprove.py':'"self_test": "FAIL", ocr.py','ocr.py':'AssertionError: afa','pipeline.py':'ImportError: cannot import name','smoke.json':'Élő próba'})
  self.assertEqual(order,['server.py','pipeline.py','ocr.py','selfimprove.py'],'server, then load errors, then real errors, derivative last')
class NextMilestoneTests(unittest.TestCase):
 def ms(self,*rows):return [dict(id=i,state=s,code_errors=e) for i,s,e in rows]
 def test_broken_code_comes_first(self):
  m=self.ms(('engine','done',{}),('tests','revise',{}),('pipeline','revise',{'pipeline.py':'x'}),('pay','pending',{}))
  self.assertEqual(vb.next_milestone(m),'pipeline')
 def test_a_file_that_cannot_load_outranks_everything(self):
  m=self.ms(('engine','revise',{'validate.py':'AssertionError: x'}),('api','done',{'pipeline.py':'ImportError: cannot import name …'}),('pay','pending',{}))
  self.assertEqual(vb.next_milestone(m),'api')
 def test_next_step_names_the_milestone_and_its_broken_files(self):
  m=[dict(id='engine',title='Működő mag',state='revise',code_errors={'validate.py':'x','ocr.py':'y'}),dict(id='pay',title='Fizetés',state='pending',code_errors={})]
  self.assertEqual(vb.next_step(m),dict(id='engine',title='Működő mag',fix=['ocr.py','validate.py']))
  self.assertIsNone(vb.next_step([dict(id='a',title='A',state='done',code_errors={})]))
 def test_then_revisions_then_closed_but_broken_then_pending(self):
  self.assertEqual(vb.next_milestone(self.ms(('a','done',{}),('b','pending',{}),('c','revise',{}))),'c')
  self.assertEqual(vb.next_milestone(self.ms(('a','done',{}),('b','pending',{}))),'b')
  self.assertEqual(vb.next_milestone(self.ms(('api','done',{'server.py':'x'}),('b','skipped',{}))),'api')
  self.assertEqual(vb.next_milestone(self.ms(('engine','done',{'ocr.py':'AssertionError: afa'}),('billing','pending',{}))),'engine','no new feature on broken code')
  self.assertIsNone(vb.next_milestone(self.ms(('a','done',{}))))
if __name__=='__main__':unittest.main()
