import json,tempfile,unittest
from pathlib import Path
from montage import remap_words,shot_effect_filter
from creative_direction import events
from reaction_framing import focus
class CreativeTests(unittest.TestCase):
 def test_word_windows_sorted_deduped_and_frame_aligned(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'words.json'
   p.write_text(json.dumps(dict(segments=[dict(words=[dict(start=.2,end=.3,word='second'),dict(start=0,end=.1,word='first')]),dict(words=[dict(start=.2,end=.3,word='second')])])) )
   words=remap_words([dict(transcript=str(p),start=0,duration=.35)]*32)
   self.assertEqual(len(words),64)
   self.assertEqual([w['text'] for w in words[:2]],['first','second'])
   self.assertAlmostEqual(words[2]['start'],10/30,places=6)
   self.assertTrue(all(a['start']<=b['start'] for a,b in zip(words,words[1:])))
   self.assertLessEqual(words[-1]['end'],round(32*.35*30)/30)
 def test_nonfinite_timing_not_silently_invented(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'words.json';p.write_text(json.dumps(dict(segments=[dict(words=[dict(start=0,end=float('nan'),word='bad')])])))
   with self.assertRaises(ValueError):remap_words([dict(transcript=str(p),start=0,duration=2)])
 def test_events_keep_evidence_and_do_not_retime_source(self):
  shot=dict(id='shot_2',start_frame=45,end_frame=75,evidence=dict(unit_id=12,reason='Observed reveal'),zoom='punch-in',transition='wipe',sound='pop',sound_delay=.9)
  result=events([shot]);self.assertEqual(len(result),3)
  self.assertTrue(all(45<=e['start_frame']<e['end_frame']<=75 for e in result))
  self.assertTrue(all(e['source_unit']==12 for e in result));self.assertEqual(shot['end_frame'],75)
 def test_speech_and_face_alone_do_not_prove_reaction(self):
  observation=dict(frames=[dict(seconds=t,faces=[dict(box=[.4,.2,.1,.1])],action='Person talking') for t in (0,.5)])
  self.assertIsNone(focus(dict(start=0,end=2,beat='hook'),observation,1))
 def test_punch_has_bounded_hold_release_not_whole_shot_oscillation(self):
  f=shot_effect_filter(dict(reframe=[1],effect='punch-in',duration=10))
  self.assertIn('42.000',f);self.assertNotIn('sin',f)
 def test_screen_facecam_uses_evidenced_pip_and_rejects_unknown_mode(self):
  from smart_framing import composition,filters,validate
  obs=dict(aspect_ratio=16/9,frames=[dict(seconds=t,regions=[dict(kind='speaker',confidence=.95,box=[0,0,.25,.4]),dict(kind='screen',confidence=.95,box=[.3,0,.7,1])]) for t in (0,1)])
  c=composition(obs,0,2);self.assertEqual(c['mode'],'pip')
  self.assertIn('overlay=x=684:y=108',';'.join(filters('[in]','[out]',c,'p')))
  with self.assertRaises(ValueError):validate(dict(c,mode='arbitrary'))
if __name__=='__main__':unittest.main()
