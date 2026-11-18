import json,tempfile,unittest
from pathlib import Path
from short_style import select_montage,DEFAULT
from montage import remap_words,write_word_captions
class MontageTests(unittest.TestCase):
 def test_reject_overlapping_and_require_multiple_real_moments(self):
  tracks=[dict(source=dict(duration=30),transcript=dict(segments=[dict(start=i,end=i+3,text='wow what bro') for i in (0,5,10,15)]))]
  result=select_montage(dict(shots=[dict(source=0,start=0,end=5),dict(source=0,start=1,end=6)]),tracks,dict(DEFAULT,min_seconds=10,max_seconds=20,target_seconds=15))
  self.assertGreaterEqual(len(result['shots']),4)
  for a,b in zip(sorted(result['shots'],key=lambda x:x['start']),sorted(result['shots'],key=lambda x:x['start'])[1:]):self.assertLessEqual(a['end'],b['start'])
 def test_word_timing_is_remapped_at_cuts(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'transcript.json';p.write_text(json.dumps(dict(segments=[dict(words=[dict(start=3,end=3.5,word='Hello'),dict(start=9,end=9.5,word='world')])])));
   words=remap_words([dict(transcript=str(p),start=2,duration=2),dict(transcript=str(p),start=8,duration=2)])
   self.assertEqual([x['start'] for x in words],[1,3]);self.assertEqual([x['text'] for x in words],['Hello','world'])
   output=Path(tmp)/'captions.ass';self.assertEqual(write_word_captions(words,output),2)
   text=output.read_text();self.assertIn(r'\clip(108,880,864,1220)',text);self.assertIn(r'\c&H C5F235&'.replace(' ',''),text);self.assertIn(r'\t(0,90',text)
 def test_insufficient_material_is_not_presented_as_montage(self):
  with self.assertRaises(ValueError):select_montage({},[dict(source=dict(duration=10),transcript=dict(segments=[]))],DEFAULT)
if __name__=='__main__':unittest.main()

class MontageContinuityTests(unittest.TestCase):
 def test_transcript_windows_join_without_creating_a_cut(self):
  from montage import coalesce_continuous_shots,frame_budgets
  shots=[dict(source='actual.mp4',start=2,duration=2.37,layout='cover',reframe=[dict(seconds=0,center=.4),dict(seconds=2,center=.45)]),dict(source='actual.mp4',start=4.37,duration=.9,layout='cover',reframe=[dict(seconds=0,center=.45),dict(seconds=.5,center=.5)]),dict(source='actual.mp4',start=8,duration=1.23,layout='cover')]
  merged=coalesce_continuous_shots(shots);self.assertEqual(len(merged),2);self.assertAlmostEqual(merged[0]['duration'],3.27);self.assertEqual(merged[0]['reframe'][2]['seconds'],2.37)
  self.assertEqual(sum(frame_budgets(merged)),135)
 def test_intentional_effects_source_changes_and_gaps_remain_cuts(self):
  from montage import coalesce_continuous_shots
  for change in (dict(effect='punch-in'),dict(sound='pop'),dict(source='other.mp4'),dict(start=4.2),dict(layout='fit')):
   shots=[dict(source='actual.mp4',start=2,duration=2,layout='cover'),dict(source='actual.mp4',start=4,duration=2,layout='cover',**{k:v for k,v in change.items() if k not in ('source','start','layout')})]
   shots[1].update(change);self.assertEqual(len(coalesce_continuous_shots(shots)),2)
 def test_cumulative_rounding_does_not_accumulate_drift(self):
  from montage import frame_budgets
  lengths=[.35]*32;frames=frame_budgets([dict(duration=d) for d in lengths]);self.assertEqual(sum(frames),round(sum(lengths)*30));self.assertLessEqual(max(frames)-min(frames),1)
