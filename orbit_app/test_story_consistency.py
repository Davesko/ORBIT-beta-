"""Consistent cast and location across an episode, and scripts that never replay earlier beats."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import story_episode as episode
import story_identity as identity

PURPLE=(150,90,120)  # BGR purple-grey stage


def stage(cast=True,background=PURPLE,drill=True):
    image=np.zeros((416,240,3),np.uint8);image[:]=background
    if drill:cv2.rectangle(image,(150,250),(200,330),(30,200,240),-1)  # yellow-handled drill (BGR yellow)
    if cast:
        cv2.circle(image,(90,180),26,(20,120,250),-1)      # orange head
        cv2.rectangle(image,(66,148),(114,160),(30,30,220),-1)  # red cap
        cv2.line(image,(90,206),(90,300),(0,0,0),4)
    return image


def meme_premise():
    selected=episode.meme_profile(18,episode.SERIES)
    return dict(profile=selected,art=selected['art'],hook_caption='THIS DRILL IS TOO MUCH',payoff_caption='A TOOTHPICK WINS')


def scenes(n=6):
    return [dict(setting=f'Purple stage variant {i}',opening_image=f'Pip stands beside the drill, pose number {i}.',
                 visual_action=f'Pip pushes the drill forward with both arms, attempt {i}.',
                 visible_result=f'The drill tips over to the right, step {i}.',camera='Static',cast='lead',voice='',
                 caption=f'Line {i}',sfx='none') for i in range(n)]


class ScriptIntegrityTests(unittest.TestCase):
    def plan(self,shots,repair=False):
        return episode.plan(dict(title='Drill',story_prop='A black drill with a yellow handle.',scenes=shots),meme_premise(),18,repair=repair)

    def test_a_script_that_replays_its_first_half_is_refused_even_on_repair(self):
        shots=scenes()
        for i in (3,4,5):
            shots[i]=dict(shots[i-3],caption=shots[i]['caption'])
        with self.assertRaisesRegex(ValueError,'never copy earlier beats'):
            self.plan(shots,repair=True)

    def test_one_repeat_is_repaired_on_the_last_attempt(self):
        shots=scenes();shots[2]['visual_action']=shots[1]['visual_action']
        with self.assertRaisesRegex(ValueError,'visual_action of escalation repeats setup'):
            self.plan(shots)
        repaired=self.plan(shots,repair=True)['scenes']
        self.assertNotEqual(repaired[1]['visual_action'],repaired[2]['visual_action'])

    def test_shape_changes_are_sent_back_to_the_writer(self):
        shots=scenes();shots[4]['visible_result']='The drill deflates into a limp piece of rubber.'
        with self.assertRaisesRegex(ValueError,'twist \\("deflates"\\)'):
            self.plan(shots)
        self.assertEqual(self.plan(shots,repair=True)['scenes'][4]['visible_result'],shots[4]['visible_result'])

    def test_each_caption_appears_once(self):
        shots=scenes()
        shots[2]['caption']='A toothpick wins!';shots[3]['caption']='Line 1';shots[5]['caption']='this drill is too much'
        captions=[s['caption'] for s in self.plan(shots)['scenes']]
        self.assertEqual(captions,['THIS DRILL IS TOO MUCH','Line 1','','','A TOOTHPICK WINS',''])

    def test_every_shot_is_drawn_in_one_locked_location(self):
        plan=self.plan(scenes())
        self.assertEqual(plan['location'],'Purple stage variant 0')
        for shot in plan['scenes']:
            still,motion=episode.prompts(plan,shot,'start')
            self.assertIn('Purple stage variant 0',still)
            self.assertNotIn('variant '+str(plan['scenes'].index(shot)),still) if plan['scenes'].index(shot) else None
        anchor=episode.anchor_prompt(plan)
        for text in (plan['art']['lead'],plan['art']['support'],plan['art']['signature_prop'],'Purple stage variant 0'):
            self.assertIn(text,anchor)
        self.assertEqual(episode.plan(plan,plan,18,repair=True)['location'],plan['location'])  # continuity keeps it


class IdentityTests(unittest.TestCase):
    def test_identity_colours_come_from_the_bible_minus_the_prop(self):
        art=episode.SERIES
        self.assertEqual(identity.cast_colours(art['lead'],art['support'],'lead'),['orange','red'])
        self.assertEqual(identity.cast_colours(art['lead'],art['support'],'both'),['orange','red','purple'])
        self.assertEqual(identity.cast_colours(art['lead'],art['support'],'lead','A red toolbox'),['orange'])

    def test_background_hue_is_not_an_identity_colour(self):
        self.assertEqual(identity.usable(stage(),['orange','red','purple']),['orange','red'])

    def test_presence_counts_the_cast_not_the_drill(self):
        import story_motion
        with_cast,only_drill=stage(),stage(cast=False)
        self.assertGreater(story_motion.cast_presence(with_cast,['orange','red']),.01)
        self.assertEqual(story_motion.cast_presence(only_drill,['orange','red']),0)


class AnchorFrameTests(unittest.TestCase):
    def run_frame(self,verdicts,cast='lead'):
        import story_animation as sa
        from types import SimpleNamespace
        calls=[];verdicts=iter(verdicts)
        def fake_flux(s,prompt,w,h,seed,output,init=None,strength=None,steps=4):
            calls.append((seed,init,strength,steps));Path(output).write_bytes(b'png')
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);anchor=d/'anchor.png';anchor.write_bytes(b'a')
            with patch('design_studio.flux',fake_flux),patch.object(sa,'judge',lambda *a:dict(next(verdicts))):
                result=sa.consistent_frame(SimpleNamespace(root=d),dict(art=episode.SERIES),dict(cast=cast),'p',anchor,7,(240,416),d/'ref.png',d/'identity.json','qwen3.5:9b')
            self.assertTrue((d/'ref.png').is_file());self.assertEqual(sorted(p.name for p in d.glob('ref-*')),[])
            return result,calls,json.loads((d/'identity.json').read_text())

    def test_free_shots_are_redrawn_until_the_cast_matches_the_sheet(self):
        bad=dict(passed=False,problems=['skin coloured head'])
        result,calls,report=self.run_frame([bad,dict(passed=True,problems=[])])
        self.assertTrue(result['passed']);self.assertEqual(result['attempt'],'free1')
        self.assertEqual(calls,[(7,None,None,4),(8,None,None,4)])  # free composition: no init image
        self.assertEqual(len(report['tries']),2)

    def test_no_matching_seed_falls_back_to_the_model_sheet(self):
        import story_animation as sa
        bad=[dict(passed=False,problems=['x']*3)]*sa.IDENTITY_TRIES
        result,calls,report=self.run_frame(bad+[dict(passed=True,problems=[])])
        self.assertEqual(result['attempt'],'anchored')
        self.assertEqual(calls[-1][1:],(calls[-1][1],sa.ANCHOR_STRENGTH,sa.ANCHOR_STEPS));self.assertIsNotNone(calls[-1][1])
        self.assertEqual(len(report['tries']),sa.IDENTITY_TRIES+1)

    def test_verdict_only_counts_the_cast_in_the_shot(self):
        import story_animation as sa
        reply=lambda v:{'message':{'content':json.dumps(v)}}
        with tempfile.TemporaryDirectory() as d:
            a,f=Path(d)/'a.png',Path(d)/'f.png';a.write_bytes(b'a');f.write_bytes(b'f')
            plan=dict(art=episode.SERIES,location='Purple stage')
            v=dict(lead_matches=True,support_matches=None,same_location=True,extra_characters=False,problems=[])
            with patch('model_hub.request',return_value=reply(v)) as req:
                self.assertTrue(sa.judge(plan,dict(cast='lead'),a,f,'qwen3.5:9b')['passed'])
                self.assertFalse(sa.judge(plan,dict(cast='both'),a,f,'qwen3.5:9b')['passed'])  # Dot is needed but absent
                self.assertEqual(len(req.call_args[0][1]['messages'][0]['images']),2)
            for bad in (dict(support_matches=True,same_location=False),dict(support_matches=False),dict(extra_characters=True)):
                with patch('model_hub.request',return_value=reply(dict(v,**bad))):
                    self.assertFalse(sa.judge(plan,dict(cast='lead'),a,f,'qwen3.5:9b')['passed'],bad)

    def test_flux_img2img_arguments(self):
        import design_studio
        from types import SimpleNamespace
        seen={}
        def run(cmd,**kw):
            seen['cmd']=cmd;Path(cmd[cmd.index('--output')+1]).write_bytes(b'x');return SimpleNamespace(returncode=0,stderr='',stdout='')
        with tempfile.TemporaryDirectory() as d,patch('model_hub.status',return_value=dict(flux_ready=True,flux_path='m',config=dict(base=d))),\
             patch('model_hub.unload'),patch.object(design_studio.subprocess,'run',run):
            design_studio.flux(SimpleNamespace(root=Path(d)),'p',480,832,1,Path(d)/'o.png',init=Path(d)/'a.png',strength=.35,steps=10)
        cmd=seen['cmd']
        self.assertEqual(cmd[cmd.index('--image-path')+1],str(Path(d)/'a.png'))
        self.assertEqual((cmd[cmd.index('--image-strength')+1],cmd[cmd.index('--steps')+1]),('0.35','10'))


if __name__=='__main__':
    unittest.main()
