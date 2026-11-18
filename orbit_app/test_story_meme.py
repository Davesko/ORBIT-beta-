import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import story_episode as episode
from studio import Studio


class MemeProductionTests(unittest.TestCase):
    def test_stickman_requests_use_original_production_without_stealing_clip_edits(self):
        from story_animation import production_request
        self.assertTrue(production_request('Készíts egy 18 másodperces 2D stickman mémvideót.'))
        self.assertTrue(production_request('Generate an original stickman short.'))
        self.assertFalse(production_request('Vágj egy stickman Shorts videót ebből: https://youtube.com/watch?v=test'))
        self.assertFalse(production_request('Csak egy stickman storyboard tervet készíts.'))

    def test_series_is_snapshotted_into_each_job(self):
        import story_animation as story
        with tempfile.TemporaryDirectory() as directory:
            s=Studio(Path(directory))
            self.addCleanup(s.db.close)
            pid=s.create_project('YouTube Shorts','Test')
            team=story.install_team(s,pid)
            ids=story.agent_ids(pid)
            s.save_agent(dict(s.agent(ids['art']),prompt=story.LEGACY_PROMPTS['art']))
            s.save_agent(dict(s.agent(ids['script']),prompt='Keep my custom project direction.'))
            story.install_team(s,pid)
            self.assertEqual(s.agent(ids['art'])['prompt'],story.MEME_PROMPTS['art'])
            self.assertEqual(s.agent(ids['script'])['prompt'],'Keep my custom project direction.')
            run=s.enqueue_graph(pid,team['agents'][0],story.DEFAULT_BRIEF)
            file=s.safe_path(pid,episode.SERIES_FILE)
            changed=json.loads(file.read_text())
            changed['lead']='A new round blue stickman head with black limbs and large white eyes.'
            file.write_text(json.dumps(changed))
            rows=s.rows("SELECT payload FROM jobs WHERE json_extract(payload,'$.run')=?",(run['run'],))
            self.assertEqual(len(rows),6)
            for row in rows:
                self.assertEqual(json.loads(row['payload'])['story_series']['lead'],episode.SERIES['lead'])

    def test_meme_timing_actions_and_caption_style(self):
        from story_render import caption_image
        selected=episode.meme_profile(18,episode.SERIES)
        scenes=[dict(setting='Sparse grey room with a purple wall',opening_image=f'Pip stands beside object number {i}.',
                     visual_action=f'Pip points his right arm at object {i}.',visible_result=f'The object {i} is tilted to the right.',
                     camera='Zoom In',cast='lead',voice='',caption='ONE LITTLE BUTTON',sfx='none')
                for i in range(6)]
        premise=dict(profile=selected,art=selected['art'],hook_caption='THIS BUTTON STEALS YOUR HAT',payoff_caption='IT STOLE THE WRONG ONE')
        plan=episode.plan(dict(title='One little button',story_prop='A large red round button in a square black wall plate.',scenes=scenes),premise,18)
        self.assertEqual(sum(scene['frames'] for scene in plan['scenes']),432)
        self.assertLessEqual(plan['scenes'][0]['frames'],48)
        self.assertTrue(all(scene['frames']<=120 and scene['camera']=='Static' for scene in plan['scenes']))
        self.assertEqual(plan['scenes'][4]['sfx'],'vine_boom')    # the meme boom (13 Nov)
        self.assertEqual(plan['scenes'][0]['caption'],premise['hook_caption'])
        self.assertEqual(episode.plan(plan,plan,18)['scenes'][4]['caption'],premise['payoff_caption'])
        caption=caption_image(plan['scenes'][0],meme=True)
        self.assertEqual(caption.getpixel((45,170)),(255,219,54,255))
        self.assertEqual(caption.getpixel((0,0))[3],0)

    def test_global_camera_motion_is_not_character_motion(self):
        from story_motion import measure
        rng=np.random.default_rng(4)
        texture=rng.integers(0,255,(288,160),dtype=np.uint8)
        camera=[cv2.warpAffine(texture,np.float32([[1,0,i*2],[0,1,0]]),(160,288),borderMode=cv2.BORDER_REFLECT) for i in range(5)]
        self.assertFalse(measure(camera)['passed'])
        frames=[]
        for i in range(5):
            frame=np.full((288,160),130,np.uint8)
            cv2.circle(frame,(65+i*4,120),19,20,-1)
            cv2.line(frame,(65+i*4,140),(65+i*4,210),20,5)
            frames.append(frame)
        self.assertTrue(measure(frames)['passed'])

    def test_silent_visual_comedy_keeps_its_full_music_and_effect_track(self):
        import story_audio
        plan=dict(title='Silent reaction',frames=144,profile=dict(arc='meme',music='meme'),
                  scenes=[dict(frames=72,voice='',beat='hook',sfx='whoosh'),
                          dict(frames=72,voice='',beat='twist',sfx='boom')])
        with tempfile.TemporaryDirectory() as directory,patch('story_audio.engine',side_effect=AssertionError('No narration requested')):
            output=Path(directory)/'mix.wav'
            story_audio.mix(plan,None,None,output)
            with wave.open(str(output)) as sound:
                self.assertEqual((sound.getnframes(),sound.getnchannels()),(144000,2))


if __name__=='__main__':
    unittest.main()
