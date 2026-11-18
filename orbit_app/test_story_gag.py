"""15 Nov: the visual-gag format, sounds tied to actions, shots as long as their lines, fast cutting."""
import json,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
import numpy as np
import story_episode as episode,story_series,story_puppet,story_audio,story_animation

def draft():
 shot=lambda action,line,la='talk',sa='stare',sfx='none',prop='none':dict(setting='a dim living room at night, the doorway',opening_image='Krix stands in the doorway '+action,visual_action=action,visible_result='after '+action,
  camera='Static',cast='both',voice='',caption='A card nobody needs',sfx=sfx,lines=[dict(speaker='lead',text=line)] if line else [],lead_action=la,support_action=sa,prop_motion=prop,seated=False,show='a phone at 99%')
 return dict(title='Shadow',story_prop='one grey felt slipper with a white star patch',music='sneaky',music_prompt='pizzicato strings and soft woodblocks, tiptoe tempo',scenes=[
  shot('Krix tiptoes into the room while Dale stares','Nope nope nope nope nope nope nope nope nope'),
  shot('Krix crouches behind the couch',''),
  shot('Krix runs across the room','Got you.',la='run'),
  shot('Krix laughs and dances','',la='laugh'),
  shot('Krix slaps the shadow and the slipper flies back','Why?!',la='slap',sa='shock',sfx='vine_boom',prop='fly_in'),
  shot('Krix faints on the rug','',la='faint',sfx='airhorn')])

def premise(fmt='gag'):
 art=dict(lead='Krix: kobold, small and hunched, oval green head, huge pointed ears',support='Dale: tall lanky human, pale tan oval head, glasses',world='A dim living room at night lit by one lamp',palette='Deep blue shadows, warm yellow lamp light',signature_prop='One grey felt slipper')
 return dict(art=art,profile=episode.meme_profile(18,dict(episode.SERIES,**{k:art[k] for k in episode.ART_FIELDS})),series_format=fmt,hook_caption='He thought the dark was empty',payoff_caption='It was his own shadow')

class GagPlanTests(unittest.TestCase):
 def test_bodies_do_what_the_action_says_and_nothing_is_calmed(self):
  plan=episode.plan(draft(),premise(),18)
  acts=[s['acting']['lead'] for s in plan['scenes']]
  self.assertEqual(acts[:3],['sneak','crouch','run']);self.assertEqual(acts[4:],['slap','faint'])
  self.assertTrue(all(s['pace']=='fast' and s['show']=='' for s in plan['scenes']))
  self.assertEqual(len(plan['scenes'][0]['lines'][0]['text'].split()),8)          # one short line at most
  self.assertTrue(all(not s['caption'] for s in plan['scenes'] if not s['lines']))
 def test_dialogue_format_is_still_calm(self):
  plan=episode.plan(draft(),premise('bro_logic'),18)
  self.assertNotIn('pace',plan['scenes'][2]);self.assertEqual(plan['scenes'][0]['show'],'a phone at 99%')
 def test_sounds_belong_to_what_is_seen(self):
  plan=episode.plan(draft(),premise(),18)
  cues=[[c['name'] for c in s['cues']] for s in plan['scenes']]
  self.assertEqual(cues[2],['footsteps']);self.assertIn('impact',cues[4]);self.assertIn('vine_boom',cues[4]);self.assertIn('whoosh',cues[4])
  self.assertNotIn('airhorn',cues[5]);self.assertEqual(cues[5],['whoosh','impact'])       # a meme sound only on the twist
  self.assertEqual(cues[3],[])                                                         # a laugh needs no effect
  kept=episode.sound_cues(dict(cast='lead',beat='setup',sfx='glass',acting=dict(lead='talk'),visual_action='Krix drops the vase and it shatters',lines=[]))
  self.assertEqual(kept,[dict(at=.2,name='glass')])
  self.assertEqual(episode.sound_cues(dict(cast='lead',beat='setup',sfx='glass',acting=dict(lead='talk'),visual_action='Krix talks about taxes',lines=[])),[])

class Voice:
 sample_rate=24000
 def __init__(self,seconds):self.samples=(np.sin(np.arange(int(24000*seconds))/20)*.3).astype(np.float32)
class TTS:
 def generate(self,text,sid,speed):return Voice(.5*len(text.split()))

class SoundTests(unittest.TestCase):
 def plan(self):
  line=lambda text:[dict(speaker='lead',text=text)]
  return dict(title='T',frames=4*168,profile=dict(arc='meme',music='meme'),voices=dict(lead=dict(voice='am_liam',speed=1.0)),scenes=[
   dict(frames=168,beat='hook',sfx='none',lines=line('Krix.'),acting=dict(lead='talk',support='stare',prop='none'),cues=[]),
   dict(frames=168,beat='setup',sfx='none',lines=[],acting=dict(lead='run',support='stare',prop='none'),cues=[dict(at=.05,name='footsteps')]),
   dict(frames=168,beat='twist',sfx='vine_boom',lines=line('one two three four five'),acting=dict(lead='slap',support='shock',prop='none'),cues=[dict(frac=.75,name='impact'),dict(frac=.72,name='vine_boom')]),
   dict(frames=168,beat='loop',sfx='none',lines=line('Really?'),acting=dict(lead='stare',support='nod',prop='none'),cues=[])])
 def test_a_shot_lasts_as_long_as_its_line_or_its_action(self):
  plan=self.plan()
  with tempfile.TemporaryDirectory() as d,patch('story_audio.engine',return_value=TTS()):
   out=Path(d)/'mix.wav';self.assertTrue(story_audio.tighten(plan,None,None,out))
   fit=json.loads((Path(d)/'story-mix-frames.json').read_text())
  seconds=[f/24 for f in fit['scenes']]
  self.assertLess(seconds[0],2.);self.assertAlmostEqual(seconds[1],2.6,delta=.05);self.assertGreater(seconds[2],2.9);self.assertLess(seconds[2],4.);self.assertEqual(fit['frames'],plan['frames'])
  self.assertLess(plan['frames']/24,11)                                   # 28 s of mostly waiting became under 11
 def test_wordless_and_narrated_episodes_keep_their_lengths(self):
  plan=self.plan()
  for sc in plan['scenes']:sc['lines']=[]
  with tempfile.TemporaryDirectory() as d:self.assertFalse(story_audio.tighten(plan,None,None,Path(d)/'mix.wav'))
  self.assertEqual(plan['frames'],672)
 def test_effects_stay_under_the_voice_and_short(self):
  self.assertTrue(all(story_audio.EFFECT_DB.get(n,story_audio.EFFECT_DEFAULT_DB)<=story_audio.VOICE_DB-5 for n in episode.CUES))
  plan=self.plan()
  with tempfile.TemporaryDirectory() as d,patch('story_audio.engine',return_value=TTS()):
   out=Path(d)/'mix.wav';story_audio.mix(plan,None,None,out)
   with wave.open(str(out)) as w:self.assertAlmostEqual(w.getnframes()/24000,plan['frames']/24,delta=.05)

class CutTests(unittest.TestCase):
 def test_a_gag_shot_is_cut_every_second_and_a_half_and_ends_on_a_face(self):
  quiet=dict(lead=[0.]*200,support=[0.]*200)
  slow=story_puppet.cuts(dict(framing='wide',cast='both',acting=dict(lead='run',support='shock')),96,quiet,1)
  fast=story_puppet.cuts(dict(framing='wide',cast='both',pace='fast',acting=dict(lead='run',support='shock')),96,quiet,1)
  self.assertEqual(len(slow),1);self.assertGreaterEqual(len(fast),3)
  self.assertTrue(all(b[0]-a[0]>=30 for a,b in zip(fast,fast[1:])));self.assertTrue(all(a[1]!=b[1] for a,b in zip(fast,fast[1:])))
 def test_backgrounds_are_lit_for_their_place(self):
  self.assertIn('night',story_animation.plate_light('a dim living room at night lit by one lamp'));self.assertIn('bright',story_animation.plate_light('a school classroom'))
  self.assertIn('daylight',story_animation.plate_light('a park bench'))

if __name__=='__main__':unittest.main()
