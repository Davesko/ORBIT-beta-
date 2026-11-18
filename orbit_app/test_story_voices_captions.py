"""Dialogue in each character's own voice, boxless captions that cover nothing, matching music and effects,
the brief's own cast, and style learned from a reference Short."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import story_episode as episode


def meme_draft(lines=True,music='lofi'):
    scenes=[dict(setting='Messy living room with a sagging couch',opening_image=f'Two stickmen slump on the couch, moment {i}.',
                 visual_action=f'Zed reaches for a chip bag with his left arm, try {i}.',visible_result=f'The chip bag tips onto the rug, step {i}.',
                 camera='Static',cast='both',voice='',caption='' if i else 'x',sfx='crunch',
                 lines=[dict(speaker='lead',text=f'Bro, level {i} is impossible.'),dict(speaker='support',text=f'Pause it. Snack break number {i}.'),
                        dict(speaker='lead',text='third line is dropped')] if lines else [])
            for i in range(6)]
    return dict(title='Couch Legends',story_prop='A giant orange bag of cheese chips.',music=music,scenes=scenes)


def premise():
    selected=episode.meme_profile(18,episode.SERIES)
    return dict(profile=selected,art=dict(selected['art'],voices=dict(lead=dict(voice='am_echo',speed=1.,pitch=-1))),
                hook_caption='HE HAS NOT MOVED IN 9 HOURS',payoff_caption='THE PIZZA WAS PLAYING',custom_cast=True,caption_position='top')


class DialoguePlanTests(unittest.TestCase):
    def test_lines_voices_music_and_reference_settings_reach_the_plan(self):
        plan=episode.plan(meme_draft(),premise(),18)
        self.assertEqual([l['speaker'] for l in plan['scenes'][1]['lines']],['lead','support'])
        self.assertEqual(plan['profile']['music'],'lofi')
        self.assertEqual(plan['voices']['lead'],dict(voice='am_echo',speed=1.,pitch=-1))
        self.assertEqual(plan['voices']['support'],episode.SERIES_VOICES['support'])
        self.assertEqual((plan['caption_position'],plan['custom_cast']),('top',True))
        again=episode.plan(plan,plan,18,repair=True)
        self.assertEqual((again['profile']['music'],again['voices'],again['scenes'][1]['lines']),(plan['profile']['music'],plan['voices'],plan['scenes'][1]['lines']))
        _,motion=episode.prompts(plan,plan['scenes'][1],'')
        self.assertTrue(motion.startswith('Pip and Dot talks with clear open-and-close mouth'))

    def test_the_narrator_never_repeats_the_dialogue(self):
        draft=meme_draft()
        draft['scenes'][1]['voice']="Zig: 'Bro, level 1 is impossible.' / Zog: 'Pause it.'"
        draft['scenes'][2]['voice']='Bro, level 2 is impossible.'
        draft['scenes'][3]['voice']='Meanwhile, the pizza had other plans.'
        plan=episode.plan(draft,premise(),18)
        self.assertEqual([s['voice'] for s in plan['scenes'][1:4]],['','','Meanwhile, the pizza had other plans.'])

    def test_voice_names_emoji_and_repeated_effects_are_cleaned(self):
        draft=meme_draft()
        for s in draft['scenes']:s['voice']='am_echo';s['sfx']='glitch'
        draft['scenes'][1]['caption']='Is that console... hungry?! 🍕'
        plan=episode.plan(draft,premise(),18)
        self.assertEqual({s['voice'] for s in plan['scenes']},{''})
        # A shot with spoken lines shows those lines as timed subtitles, not a separate card (owner 12 Nov).
        self.assertEqual(plan['scenes'][1]['caption'],'' if plan['scenes'][1]['lines'] else 'Is that console... hungry?!')
        self.assertEqual([s['sfx'] for s in plan['scenes']],['glitch','glitch','none','none','vine_boom','none'])
        import story_captions
        self.assertEqual(story_captions.drawable('PIZZA MODE! 🍕🔥'),'PIZZA MODE!')

    def test_a_line_is_said_once(self):
        draft=meme_draft()
        draft['scenes'][5]['lines']=[dict(speaker='lead',text='Bro, level 1 is impossible!'),dict(speaker='support',text='New line.')]
        plan=episode.plan(draft,premise(),18)
        self.assertEqual(plan['scenes'][5]['lines'],[dict(speaker='support',text='New line.')])  # the copy of shot 2's line is dropped

    def test_bad_lines_and_moods_are_dropped(self):
        draft=meme_draft(music='death-metal');draft['scenes'][0]['lines']=[dict(speaker='narrator',text='hi'),'x',dict(speaker='lead',text='  ')]
        plan=episode.plan(draft,premise(),18)
        self.assertEqual(plan['scenes'][0]['lines'],[]);self.assertEqual(plan['profile']['music'],'meme')

    def test_two_characters_never_share_a_voice(self):
        v=episode.voices(dict(lead=dict(voice='am_puck',speed=3,pitch=0),support=dict(voice='am_puck',speed=1,pitch=0)))
        self.assertEqual(v['lead']['speed'],1.08);self.assertNotEqual(v['lead']['voice'],v['support']['voice'])
        self.assertTrue(v['support']['voice'].startswith('am_'))

    def test_the_duo_sounds_lively_and_can_be_told_apart(self):
        # 13 Nov: am_echo + am_puck cloned to 101 and 108 Hz, monotone; the reference duo talks at ~140 and ~195 Hz.
        for lead,support in (('am_echo','am_puck'),('am_onyx','am_adam'),('af_sky','af_nova'),('bm_lewis','bm_lewis')):
            v=episode.voices(dict(lead=dict(voice=lead),support=dict(voice=support)))
            self.assertNotIn(v['lead']['voice'],episode.FLAT);self.assertNotIn(v['support']['voice'],episode.FLAT)
            self.assertGreaterEqual(abs(episode.PITCH[v['lead']['voice']][0]-episode.PITCH[v['support']['voice']][0]),35)
        self.assertEqual(set(episode.PITCH),set(episode.VOICES))

    def test_schema_asks_for_lines_and_music(self):
        shape=episode.schema(episode.MEME_BEATS,meme=True)
        self.assertIn('music',shape['required']);self.assertIn('lines',shape['properties']['scenes']['items']['required'])

    def test_a_big_body_action_needs_a_reason_in_the_shot(self):
        lines=[dict(speaker='lead',text="Bro, shouldn't we be able to jump off the tracks?"),dict(speaker='support',text='Really?')]
        out=episode.calm(dict(lead='crouch',support='cry',prop='none'),lines,'a cloud shaped like a train','escalation')
        self.assertEqual(out,dict(lead='talk',support='talk',prop='none'))           # 13 Nov: crouching at a question
        out=episode.calm(dict(lead='jump',support='laugh',prop='none'),lines,'x','twist')
        self.assertEqual(out['lead'],'jump');self.assertEqual(out['support'],'laugh')  # the line says jump; laugh is small
        self.assertEqual(episode.calm(dict(lead='walk_in',support='idle'),[], 'x','hook')['lead'],'walk_in')

    def test_a_long_thought_is_shown_a_phrase_at_a_time(self):
        import story_animation as sa
        line="Dude, why are deliveries on a ship called cargo, but in a car it's called a shipment?"
        parts=sa.phrases(line)
        self.assertEqual(' '.join(parts),line)
        self.assertTrue(all(2<=len(p.split())<=7 for p in parts),parts)
        self.assertEqual(sa.phrases('Really?'),['Really?'])
        times=sa.phrase_times(line,2.,8.)
        self.assertEqual(times[0][1],2.);self.assertAlmostEqual(times[-1][2],8.,places=2)

    def test_subtitles_come_from_the_lines(self):
        import story_animation as sa
        self.assertEqual(sa.caption_text(dict(caption='',lines=[dict(speaker='lead',text='Bro.'),dict(speaker='support',text='What?')])),'Bro. What?')
        self.assertEqual(sa.caption_text(dict(caption='HOOK',lines=[dict(speaker='lead',text='Bro.')])),'HOOK')


class FakeTTS:
    def __init__(self,seconds=.8):self.seconds,self.calls=seconds,[]
    def generate(self,text,sid,speed):
        self.calls.append((text,sid,speed))
        return SimpleNamespace(samples=np.full(round(24000*self.seconds),.2,np.float32),sample_rate=24000)


class AudioTests(unittest.TestCase):
    def test_each_character_speaks_in_order_with_their_voice_and_no_overlap(self):
        import story_audio
        plan=episode.plan(meme_draft(),premise(),18)
        tts=FakeTTS()
        placed=story_audio.dialogue(tts,plan,plan['frames']*1000,None)
        self.assertEqual(len(placed),sum(len(s['lines']) for s in plan['scenes']))
        self.assertEqual(tts.calls[0][1:],(12,1.))  # am_echo, lead speed: never slower than normal (owner 12 Nov)
        self.assertEqual(tts.calls[1][1],story_audio.VOICE_IDS['af_sky'])
        for (a,sa,_),(b,_,_) in zip(placed,placed[1:]):self.assertLessEqual(a+len(sa),b)

    def test_too_much_dialogue_is_refused_not_cut(self):
        import story_audio
        plan=episode.plan(meme_draft(),premise(),18)
        with self.assertRaisesRegex(ValueError,'párbeszéd'):
            story_audio.dialogue(FakeTTS(3),plan,plan['frames']*1000,None)

    def test_no_sound_starts_or_stops_at_full_level(self):
        """The test mix stuttered at every cut: effects and voice clips switched on and off at full level."""
        import story_audio
        tone=np.full(2400,.5,np.float32)
        faded=story_audio.fade(tone,8)
        self.assertEqual((faded[0],faded[-1]),(0,0));self.assertAlmostEqual(float(faded[1200]),.5)
        line=story_audio.speak(FakeTTS(.5),'Bro.',dict(voice='am_echo',speed=.9),None)
        self.assertLess(abs(float(line[0]))+abs(float(line[-1])),1e-3)
        for name in episode.CUES:
            cue=story_audio.fade(story_audio.effect(name,round(24000*story_audio.EFFECT_SECONDS.get(name,.25))),5)
            self.assertLess(abs(float(cue[0]))+abs(float(cue[-1])),1e-3,name)
        bed=story_audio.lofi(24000*14,3)
        bar=round(4*60/76*24000)
        for edge in (bar,2*bar,3*bar):  # chords ring over the bar line instead of stopping
            self.assertGreater(float(np.abs(bed[edge-480:edge,0]).max()),.002)

    def test_every_cue_and_mood_renders(self):
        import story_audio
        for name in episode.CUES:
            n=round(24000*story_audio.EFFECT_SECONDS.get(name,.25))
            cue=np.asarray(story_audio.effect(name,n));self.assertEqual(len(cue),n,name);self.assertTrue(np.isfinite(cue).all(),name)
        for mood in episode.MOODS:
            bed=story_audio.bed(24000*3,mood,1);self.assertEqual(bed.shape,(72000,2));self.assertLess(np.abs(bed).max(),1)


class CaptionTests(unittest.TestCase):
    def test_caption_never_covers_the_character(self):
        import story_captions as c
        frame=np.full((192,108,3),120,np.uint8);frame[29:144,20:88]=10  # a big character (the background still dominates), free only above the head
        mask=c.content([frame])
        box=c.choose(mask,c.boxes('Bro, the marshmallow is fighting back.'))
        self.assertEqual(c.score(mask,box),0)
        self.assertLessEqual(box[3],29/192+.01)
        empty=c.content([np.full((192,108,3),120,np.uint8)])
        best=c.choose(empty,c.boxes('Short line'))
        self.assertEqual((best[4],c.zone(best)),(84,'top'))  # full size at the top when nothing is in the way
        side=np.full((192,108,3),120,np.uint8);side[0:150,0:34]=10  # character on the left: a narrow box on the right
        box=c.choose(c.content([side]),c.boxes('Bro, the marshmallow is fighting back.'))
        self.assertEqual(c.score(c.content([side]),box),0)

    def test_a_rig_clip_mask_lets_the_caption_lie_on_the_painted_background(self):
        """13 Nov: on busy painted plates captions shrank into a corner; only what the rig drew must stay clear."""
        import story_captions as c, tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / 'cut-1.mp4'
            mask = np.zeros((192, 108), np.uint8); mask[40:150, 10:98] = 255          # characters in the middle
            Image.fromarray(mask).save(Path(folder) / 'cut-1-mask.png')
            with patch('story_captions.sample', side_effect=AssertionError('the video is not measured')):
                placed = c.place('ffmpeg', video, Path(folder) / 'c.png', 'Landlord said no sugar.')
        self.assertEqual(placed['covered'], 0)
        self.assertGreaterEqual(placed['box'][4], 70)
        self.assertAlmostEqual((placed['box'][0] + placed['box'][2]) / 2, .5, places=2)

    def test_preferred_zone_from_the_reference_wins_when_free(self):
        import story_captions as c
        empty=c.content([np.full((192,108,3),120,np.uint8)])
        self.assertEqual(c.zone(c.choose(empty,c.boxes('Line'),'middle')),'middle')

    def test_caption_has_no_box(self):
        import story_captions as c
        image=np.asarray(c.render('Bro the pizza is staring at me','middle'))
        alpha=image[...,3]
        top,bottom=c.BANDS['middle']
        band=alpha[round(top*c.H):round(bottom*c.H)]
        self.assertGreater((band>200).mean(),.01)
        self.assertLess((band>200).mean(),.35)  # text strokes only, not a filled card
        self.assertEqual(alpha[:round(top*c.H)-60].max(),0)
        punch=np.asarray(c.render('THE PIZZA WAS PLAYING','top',punchline=True))
        self.assertTrue(((punch[...,0]>240)&(punch[...,2]<90)&(punch[...,3]==255)).any())  # yellow fill


class CastAndReferenceTests(unittest.TestCase):
    def test_custom_cast_unless_the_series_cast_is_named(self):
        import story_animation as sa
        self.assertTrue(sa.custom_cast('két stoner stickman a kanapén',dict(custom_cast=True)))
        self.assertFalse(sa.custom_cast('Pip és Dot a kanapén',dict(custom_cast=True)))
        # 13 Nov (owner): the project's named pair in every episode; "két szereplővel" is not a request for new ones.
        self.assertFalse(sa.custom_cast('bármi',dict(custom_cast=True)))
        self.assertFalse(sa.custom_cast('Készíts egy brainrot shortot a mai trendből, két szereplővel.',{}))
        self.assertTrue(sa.custom_cast('Készíts videót új szereplőkkel a strandon.',{}))
        self.assertFalse(sa.custom_cast(sa.DEFAULT_BRIEF,{}))

    def test_owner_described_cast_never_gets_the_series_cast(self):
        import story_animation as sa
        brief='Készíts vicces stickman videót: kettő stoner stickman karakter ül egy kanapén, PS5-ön játszanak.'
        self.assertTrue(sa.brief_cast(brief));self.assertTrue(sa.custom_cast(brief,dict(custom_cast=False)))
        self.assertFalse(sa.brief_cast(sa.DEFAULT_BRIEF));self.assertFalse(sa.brief_cast('Készíts egy 18 másodperces stickman mémvideót.'));self.assertFalse(sa.brief_cast('Pip és Dot új kalandja'))
        from studio import Studio
        with tempfile.TemporaryDirectory() as d:
            s=Studio(Path(d));self.addCleanup(s.db.close)
            pid=s.create_project('YouTube Shorts','Test');team=sa.install_team(s,pid)
            context=sa.episode_ideas(s,dict(project=pid,agent=team['agents'][0],payload='{}'),brief)
            self.assertIsNone(context['profile']['art']);self.assertIn('never use Pip or Dot',context['cast'])
            plain=sa.episode_ideas(s,dict(project=pid,agent=team['agents'][0],payload='{}'),sa.DEFAULT_BRIEF)
            self.assertTrue(plain['profile']['art']['lead'].startswith('Krix:'))          # the project's fixed kobold
            self.assertTrue(plain['profile']['art']['support'].startswith('Dale:'))
            self.assertIn('Krix',plain['characters']['lead'])
            fixed=episode.cast(s,pid)
            # a project still holding the first, unedited design gets the new eyes; an edited pair is kept
            path=s.safe_path(pid,episode.CAST_FILE);old=json.loads(path.read_text())
            path.write_text(json.dumps(dict(old,version=1,lead=episode.OLD_LEADS[0])))
            self.assertEqual(episode.cast(s,pid)['lead'],episode.CAST['lead'])
            path.write_text(json.dumps(dict(old,version=1,lead='Krix: my own kobold design, purple skin, round head')))
            self.assertIn('purple',episode.cast(s,pid)['lead'])
            path.write_text(json.dumps(old))
            fixed=episode.cast(s,pid)
            self.assertGreaterEqual(abs(episode.PITCH[fixed['voices']['lead']['voice']][0]-episode.PITCH[fixed['voices']['support']['voice']][0]),35)
            import story_puppet
            krix=story_puppet.design(fixed['lead'],(0,0,0));dale=story_puppet.design(fixed['support'],(0,0,0))
            self.assertEqual((krix['ears'],krix['nose'],krix['fangs'],krix['energy']),('pointy','hook',True,'jittery'))
            self.assertEqual((dale['ears'],dale['energy'],dale['sleepy']),(None,'calm',True))
            self.assertIsNotNone(dale['tie']);self.assertGreater(dale['size'],krix['size'])

    def test_reference_link_and_style_profile(self):
        import story_reference as r
        self.assertEqual(r.reference_url('ilyen stílusban: https://www.youtube.com/shorts/abcDEF12345?feature=share.'),
                         'https://www.youtube.com/shorts/abcDEF12345?feature=share')
        self.assertIsNone(r.reference_url('nincs link'))
        with tempfile.TemporaryDirectory() as d:
            frame=Path(d)/'f.jpg';frame.write_bytes(b'jpg')
            facts=dict(duration=30,cuts=14,seconds_per_shot=2,frames=[dict(seconds=1,path=str(frame))])
            reply=dict(visual_style='flat',humor='deadpan',tone='chill',pacing='fast',structure='hook-turn',dialogue_style='two friends',
                       caption_style='outlined white',caption_position='middle',music_mood='lofi',sfx_style='few',summary='s')
            with patch('model_hub.request',return_value={'message':{'content':json.dumps(reply)}}) as req:
                style=r.describe(facts,'some words',m:='qwen3.5:9b',episode.MOODS)
            self.assertEqual((style['caption_position'],style['music_mood']),('middle','lofi'))
            sent=req.call_args[0][1]
            self.assertEqual(sent['model'],m);self.assertIn('Never retell its jokes',sent['messages'][0]['content'])

    def test_reference_style_requests_go_to_the_story_studio(self):
        from story_animation import production_request
        self.assertTrue(production_request('Készíts stickman animációt ennek a hangvétele alapján: https://youtube.com/shorts/abcdefghijk'))
        self.assertFalse(production_request('Vágj klipet ebből: https://youtube.com/shorts/abcdefghijk'))


if __name__=='__main__':
    unittest.main()
