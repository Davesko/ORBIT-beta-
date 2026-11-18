import unittest,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from short_style import source_matches,requested_settings,select_montage,DEFAULT
from montage import shot_effect_filter
class ContextUpgradeTests(unittest.TestCase):
 def test_subject_names_and_language(self):
  self.assertTrue(source_matches('magyar 2okos stream highlight',dict(title='2OKOS legjobb stream pillanatok')))
  self.assertTrue(source_matches('2okos funny stream highlights, Hungarian text',dict(title='2 OKOS stream highlights')))
  self.assertFalse(source_matches('2okos funny stream highlights, Hungarian text',dict(title='IShowSpeed funny stream')))
  self.assertFalse(source_matches('Messi highlights',dict(title='Ronaldo best moments')))
  self.assertEqual(requested_settings('magyar 2okos highlights')['language'],'hu')
 def test_effects_require_tracking_and_are_bounded(self):
  self.assertEqual(shot_effect_filter(dict(effect='punch-in',duration=4)), '')
  self.assertIn('0.09',shot_effect_filter(dict(effect='punch-in',duration=4,reframe=[1])))
  self.assertEqual(shot_effect_filter(dict(effect='untrusted',duration=4,reframe=[1])), '')
 def test_validated_context_effect_passes_through(self):
  style=dict(DEFAULT,min_seconds=10,target_seconds=10,max_seconds=20,min_shots=2)
  tracks=[dict(source=dict(duration=30),transcript=dict(segments=[]))]
  result=select_montage(dict(shots=[dict(source=0,start=0,end=5,reason='Setup',effect='none'),dict(source=0,start=6,end=11,reason='Reaction',effect='punch-in')]),tracks,style)
  self.assertEqual(result['shots'][1]['effect'],'punch-in')
 def test_web_discovery_used_when_youtube_has_no_result(self):
  import clip_sources,sqlite3,tempfile
  class Studio:
   def __init__(self,root):self.root=Path(root);self.db=sqlite3.connect(':memory:')
   def cancelled(self,j):return False
   def job_stage(self,*a,**kw):pass
  with tempfile.TemporaryDirectory() as root:
   s=Studio(root);clip_sources.schema(s)
   with patch('clip_sources.network',return_value={'candidates':[]}),patch('research.search',return_value={'results':[dict(url='https://www.youtube.com/watch?v=abcdefghijk',title='2okos stream',content='real web result')]}):
    result=clip_sources.find_clips(s,dict(project='p',tools=['find_stream_clips']),dict(query='2okos stream'),'job')
   self.assertEqual(result[0]['id'],'abcdefghijk');self.assertEqual(result[0]['discovery'],'web')
