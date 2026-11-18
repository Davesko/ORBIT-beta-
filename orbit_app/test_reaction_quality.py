import unittest
from unittest.mock import patch
from reaction_framing import focus,validate

class ReactionQualityTests(unittest.TestCase):
 def observation(self,faces=None):
  faces=faces if faces is not None else [dict(box=[.4,.2,.12,.2],confidence=.95)]
  return dict(aspect_ratio=16/9,frames=[dict(seconds=t,faces=faces,action='Person laughs',regions=[]) for t in (.1,1.8)])
 def test_visible_reaction_can_receive_a_closeup_without_speech(self):
  f=focus(dict(start=0,end=2,beat='reaction'),self.observation(),0)
  self.assertIsNotNone(f);self.assertLessEqual(f['end']-f['start'],1.4)
 def test_two_ambiguous_faces_do_not_get_a_fake_speaker_assignment(self):
  faces=[dict(box=[x,.2,.12,.2],confidence=.95) for x in (.2,.6)]
  self.assertIsNone(focus(dict(start=0,end=2,beat='hook'),self.observation(faces),1))
 def test_pause_and_missing_visual_evidence_preserve_wide_frame(self):
  self.assertIsNone(focus(dict(start=0,end=2,beat='hook',preserve_pause=True),self.observation(),1))
  self.assertIsNone(focus(dict(start=0,end=2,beat='hook'),self.observation([]),1))
 def test_spoken_hook_requires_explicit_editorial_emphasis(self):
  obs=self.observation()
  for f in obs['frames']:f['action']='Person talking to camera'
  self.assertIsNone(focus(dict(start=0,end=2,beat='hook'),obs,.9))
  self.assertIsNotNone(focus(dict(start=0,end=2,beat='hook',zoom_justified=True),obs,.9))
 def test_face_crop_must_be_inside_source_and_brief(self):
  for v in (dict(box=[0,0,2,1],start=0,end=1),dict(box=[0,0,.5,.5],start=0,end=2)):
   with self.assertRaises(ValueError):validate(v,3)
 def test_scene_duration_is_always_passed_as_seconds(self):
  import video_intelligence
  from unittest.mock import MagicMock
  cap=MagicMock();cap.get.side_effect=[60,10800]
  manager=MagicMock();left=MagicMock();left.get_seconds.return_value=0;right=MagicMock();right.get_seconds.return_value=180
  manager.get_scene_list.return_value=[(left,right)]
  with patch('cv2.VideoCapture',return_value=cap),patch('scenedetect.open_video'),patch('scenedetect.SceneManager',return_value=manager),patch('scenedetect.FrameTimecode') as timecode:
   result=video_intelligence.detect_scene_map('fixture.mp4')
  self.assertIs(type(timecode.call_args.args[0]),float);self.assertEqual(timecode.call_args.args[0],180.0)
  self.assertEqual(result['scenes'][-1]['end'],180)
 def test_bad_repetition_is_not_story_evidence(self):
  from transcript_quality import reliable
  r=reliable(dict(segments=[dict(text='tiszlom '*20),dict(text='A clear real sentence.')]))
  self.assertEqual(len(r['segments']),1);self.assertEqual(r['segments'][0]['text'],'A clear real sentence.')
 def test_metadata_language_independent_from_subtitle_language(self):
  from short_metadata import validate
  value=validate(dict(title='Kai Did Not Expect That Question',description='A moment from the stream, with the original exchange.',language='hu',hashtags=['#Shorts']))
  self.assertEqual(value['language'],'en')
  with self.assertRaises(ValueError):validate(dict(title='Kai Cenat ismétlődő szöveg',description='A videóban a streamer beszél.'))
