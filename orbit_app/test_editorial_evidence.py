import unittest
from unittest.mock import MagicMock
from editorial_evidence import missing_samples,enrich
class EvidenceTests(unittest.TestCase):
 def test_only_missing_selected_shots_are_sampled_with_bounded_budget(self):
  catalog=[dict(source=0,start=i*2,end=i*2+2,visual_samples=[{}] if i==0 else []) for i in range(30)]
  samples=missing_samples(catalog,dict(hook=0,sequence=list(range(1,30))))
  self.assertEqual(len(samples[0]),12);self.assertNotIn(1,samples[0])
 def test_enrichment_uses_actual_frames_once_without_fabricating_missing_samples(self):
  s=MagicMock();s.tool.return_value={'summary':{'frames':[dict(seconds=3,action='Visible gesture'),dict(seconds=100,action='Unrequested frame')]}}
  data=dict(style={'visual_analysis':True},visual_analysis=[{'frames':[]}]);catalog=[dict(source=0,start=2,end=4,visual_samples=[])]
  self.assertTrue(enrich(s,{},dict(id='job'),data,[dict(source={'source_video':'actual.mp4'})],catalog,dict(hook=0,sequence=[])))
  self.assertEqual(len(data['visual_analysis'][0]['frames']),1)
  self.assertFalse(enrich(s,{},dict(id='job'),data,[],catalog,dict(hook=0,sequence=[])));self.assertEqual(s.tool.call_count,1)
