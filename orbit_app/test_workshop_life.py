"""The workshop's new rooms, the easy room delete and the moving themes (owner, 12 Nov)."""
import json
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch

from bridge import dispatch
from studio import Studio

WEB = Path(__file__).with_name('web')
NEW_ROOMS = ('gaming', 'kitchen', 'gym', 'terrace', 'library', 'server')
MOTION_THEMES = ('meteor', 'wave', 'coder', 'campfire')


class NewRooms(unittest.TestCase):
    def setUp(self):
        language = patch('language_bridge.translate_many', side_effect=lambda texts, root: list(texts))
        language.start()
        self.addCleanup(language.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.s = Studio(Path(self.temp.name))
        self.pid = 'universe'

    def tearDown(self):
        self.s.db.close()
        self.temp.cleanup()

    def req(self, action, **kwargs):
        return dispatch(dict(action=action, project=self.pid, **kwargs), self.s)

    def test_every_new_room_type_can_be_saved(self):
        for decor in NEW_ROOMS:
            rid = self.req('room_save', room={'name': decor, 'width': 9, 'height': 8, 'decor': decor, 'floor': '#333333',
                                              'wall': '#222222', 'accent': '#ffffff', 'members': []})['id']
            self.assertEqual(self.s.room(self.pid, rid)['decor'], decor)

    def test_a_deleted_room_comes_back_with_restore(self):
        rid = self.req('room_save', room={'name': 'Konyha', 'width': 9, 'height': 8, 'decor': 'kitchen', 'floor': '#333333',
                                          'wall': '#222222', 'accent': '#ffffff', 'members': []})['id']
        self.req('room_archive', id=rid, move_to='bridge')
        self.assertEqual(self.s.room(self.pid, rid, False)['archived'], 1)
        self.req('room_restore', id=rid)
        self.assertEqual(self.s.room(self.pid, rid)['archived'], 0)


class WebWiring(unittest.TestCase):
    def test_every_new_room_type_has_furniture_and_an_editor_choice(self):
        life = (WEB / 'pixel_life.js').read_text(encoding='utf-8')
        editor = (WEB / 'space_ui.js').read_text(encoding='utf-8')
        for decor in NEW_ROOMS:
            self.assertIn(f"case '{decor}'", life)
            self.assertIn(f"value:'{decor}'", editor)

    def test_motion_themes_are_listed_allowed_and_drawn(self):
        settings = (WEB / 'settings_ui.js').read_text(encoding='utf-8')
        themes = json.loads(re.search(r'colorThemes=(\[.*?\]);', settings).group(1))
        ids = {t['id'] for t in themes}
        motion = (WEB / 'theme_motion.js').read_text(encoding='utf-8')
        css = (WEB / 'theme_motion.css').read_text(encoding='utf-8')
        commander = (WEB.parent / 'commander.py').read_text(encoding='utf-8')
        for theme in MOTION_THEMES:
            self.assertIn(theme, ids)
            self.assertIn(f"'{theme}'", commander)
            self.assertIn(theme + ':{', motion)
            self.assertIn(f':root[data-theme="{theme}"]', css)

    def test_new_layers_load_after_the_ones_they_extend(self):
        index = (WEB / 'index.html').read_text(encoding='utf-8')
        self.assertLess(index.index('pixel_office.js'), index.index('pixel_life.js'))
        self.assertLess(index.index('settings_ui.js'), index.index('theme_motion.js'))
        self.assertIn('pixel_life.css', index)
        self.assertIn('theme_motion.css', index)

    def test_only_a_running_job_sends_a_character_to_work(self):
        life = (WEB / 'pixel_life.js').read_text(encoding='utf-8')
        self.assertIn("filter(j=>j.status==='running')", life)
        self.assertNotIn("['work',", life)   # 'work' is never offered as an idle choice



class NightFixes(unittest.TestCase):
    def test_an_improvement_task_about_the_studio_is_not_a_video_order(self):
        from story_animation import production_request
        task = ('Valósítsd meg most ezt a fejlesztést a(z) „Animációs stúdió” projektben: Optimalizáljuk a grafikon futási idejét. '
                'Mért alap: run_seconds: 103.7, a 103,7 másodperces futási idő túl hosszú.')
        self.assertFalse(production_request(task))
        self.assertTrue(production_request('Készíts egy 18 másodperces 2D stickman mémvideót.'))

    def test_the_autopilot_does_not_force_busy_movement_on_the_studio(self):
        import autopilot_hub
        bad = ("Plan the beats. Strictly forbid repeating the same action; force at least two distinct physical movements per scene; "
               "avoid static poses. Output must be a JSON object with keys: 'beats'.")
        self.assertTrue(autopilot_hub.FORCED.search(bad))
        self.assertIn('show', autopilot_hub.STUDIO_DIRECTION)

    def test_a_topic_used_twice_lately_is_not_used_again(self):
        from story_animation import repeated_topic
        recent = [dict(premise='A dev cancels a subscription that renews itself.'), dict(premise='The subscription ghost haunts his card.'),
                  dict(premise='Roommates fight over the last slice.')]
        self.assertTrue(repeated_topic('another subscription renews without asking', recent))
        self.assertFalse(repeated_topic('a pigeon steals breakfast from a cafe table', recent))
        # Story words are no topic: on 12 Nov evening "actually" and "stickmen" blocked every new idea.
        story = [dict(premise='Two stickmen actually attempt the viral highlighter trend'), dict(premise='Two stickmen actually fight a sentient trash bag')]
        self.assertFalse(repeated_topic('two stickmen actually try a new netflix dance', story))
        self.assertTrue(repeated_topic('x', [dict(premise='p', trend='Liquid highlighter')], trend='liquid highlighter'))


class StudioPictures(unittest.TestCase):
    def test_spoken_lines_become_timed_subtitles(self):
        from story_animation import caption_text, line_timing
        shot = dict(caption='Something else', lines=[dict(speaker='lead', text='[sigh] I cancelled it.')])
        self.assertEqual(caption_text(shot, timed=True), '')
        plan = dict(scenes=[shot, dict(lines=[dict(speaker='support', text='It renewed.')])])
        timing = line_timing(plan, [dict(start=.2, envelope=[0] * 24), dict(start=1.5, envelope=[0] * 12)])
        self.assertEqual(timing, [('I cancelled it.', .2, 1.2), ('It renewed.', 1.5, 2.0)])

    def test_the_keyword_is_lit(self):
        import story_captions
        self.assertEqual(story_captions.keyword('My card is declined three times!'), 'declined')
        image = story_captions.render('My card is declined', (.05, .1, .95, .3, 84), highlight='declined')
        colours = {px[:3] for px in image.getdata() if px[3] == 255}
        self.assertIn((255, 221, 51), colours)

    def test_the_picture_pops_in_and_settles(self):
        import story_puppet
        self.assertLess(story_puppet.insert_placement(0, 1)[2], .05)
        self.assertAlmostEqual(story_puppet.insert_placement(2, 1)[2], 1., places=3)
        # A close set-up: smaller, in the top corner away from the characters (13 Nov: a face sat on the lead's head).
        x, y, scale, _ = story_puppet.insert_placement(2, 1, zoom=1.55, crowd=700)
        self.assertLess(x, 540)
        self.assertLess(y, 615)
        self.assertLess(scale, .8)



class TrendStories(unittest.TestCase):
    def test_an_autopilot_brief_is_a_direction_not_a_topic(self):
        from story_animation import autopilot_brief
        self.assertTrue(autopilot_brief('[ORBIT-RUN] Készíts egy új shortot. Az irány, amit a tulajdonos megadott: legyen vicces'))
        self.assertTrue(autopilot_brief('Készíts brainrot videót a mai virális trendekből'))
        self.assertFalse(autopilot_brief('Készíts videót arról, hogyan főztek az ősemberek'))

    def test_a_trend_episode_must_name_its_trend(self):
        from story_animation import valid_idea
        idea = dict(premise='A cat runs a hedge fund', hook='h', escalation='e', payoff='p', hook_caption='Cat CEO again', payoff_caption='The fund was tuna')
        self.assertFalse(valid_idea(idea, dict(must_use_trend=True, recent_ideas_to_avoid=[])))
        self.assertTrue(valid_idea(dict(idea, trend='Cat memes'), dict(must_use_trend=True, recent_ideas_to_avoid=[])))

    def test_agent_chat_opens_at_the_newest_message(self):
        life = (WEB / 'pixel_life.js').read_text(encoding='utf-8')
        self.assertIn("if(view==='chat'){stick=true", life)


    def test_a_card_that_is_also_spoken_is_dropped(self):
        import story_episode
        self.assertIn("in spoken:shot['caption']=''", (WEB.parent / 'story_episode.py').read_text(encoding='utf-8'))
        self.assertEqual(story_episode.caption_key("It's giving hydration!"), story_episode.caption_key("it's giving hydration"))


    def test_used_trends_are_not_offered_again(self):
        from story_animation import fresh_trends
        trending = ['TikTok is obsessed with liquid highlighter to brighten the undereyes', 'Viral Chicago trend being replicated in London', 'Brain stacking is the new TikTok trend']
        recent = [dict(trend='liquid highlighter trend for undereyes'), dict(trend='TikTok is obsessed with liquid highlighter to brighten the undereyes - but')]
        left = fresh_trends(trending, recent)
        self.assertEqual(sorted(left), sorted(trending[1:]))


class Mixing(unittest.TestCase):
    """13 Nov (owner): "a zene és a hangok ... legyenek kikeverve, mert most nagyon eltérnek a hangerők"."""
    def test_parts_are_set_by_how_loud_they_sound(self):
        import numpy as np
        import story_audio as sa
        t = np.arange(sa.RATE) / sa.RATE
        quiet = (.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        loud = (.6 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        self.assertAlmostEqual(sa.loudness(sa.level(quiet, sa.VOICE_DB)), sa.loudness(sa.level(loud, sa.VOICE_DB)), places=1)
        padded = np.concatenate([np.zeros(sa.RATE, np.float32), loud])
        self.assertAlmostEqual(sa.loudness(padded), sa.loudness(loud), places=1)      # silence does not lower a line
        for name in ('vine_boom', 'bruh', 'airhorn', 'crickets', 'sad_trombone'):
            cue = sa.level(np.asarray(sa.effect(name, round(sa.RATE * sa.EFFECT_SECONDS[name])), np.float32), sa.EFFECT_DB.get(name, -26.))
            self.assertLess(sa.loudness(cue), sa.VOICE_DB, name)                       # a meme hit never drowns the line
        self.assertLess(sa.MUSIC_DB, sa.VOICE_DB - 10)

    def test_the_finished_mix_is_normalised_for_the_platforms(self):
        import json
        import subprocess
        import tempfile
        import wave
        import numpy as np
        import story_audio as sa
        ffmpeg = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'
        if not ffmpeg.is_file():
            self.skipTest('no ffmpeg')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'm.wav'
            t = np.arange(sa.RATE * 4) / sa.RATE
            x = (.05 * np.sin(2 * np.pi * 300 * t) * (1 + np.sin(2 * np.pi * .5 * t)) / 2).astype(np.float32)
            with wave.open(str(path), 'wb') as w:
                w.setparams((2, 2, sa.RATE, 0, 'NONE', 'not compressed'))
                w.writeframes((np.repeat(x[:, None], 2, 1) * 32767).astype('<i2').tobytes())
            sa.normalise(path, ffmpeg)
            e = subprocess.run([str(ffmpeg), '-hide_banner', '-i', str(path), '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
            measured = json.loads(e[e.rindex('{'):e.rindex('}') + 1])
            self.assertAlmostEqual(float(measured['input_i']), sa.LOUDNESS, delta=1.)
            self.assertLessEqual(float(measured['input_tp']), -1.)


class ShowerThoughtIdeas(unittest.TestCase):
    def test_the_formats_own_words_are_not_a_repeated_topic_and_a_whole_thought_fits(self):
        import story_animation as sa
        recent = [dict(premise='Two stickmen on a bench, Lead keeps interrupting with questions about the IKEA effect.'),
                  dict(premise='Two stickmen on a park bench, Lead keeps interrupting with questions about the Microsoft outage.')]
        idea = dict(premise='Krix keeps interrupting Dale\'s nap with questions about the price of eggs.', hook='h', escalation='e', payoff='p',
                    hook_caption='Dale, if eggs cost more than chickens now, are we technically rich if we own a chicken?',
                    payoff_caption='So the chicken is the landlord?', trend='egg prices')
        self.assertIsNone(sa.idea_problem(idea, dict(recent_ideas_to_avoid=recent, must_use_trend=True)))
        self.assertIn('trend', sa.idea_problem(dict(idea, trend=''), dict(recent_ideas_to_avoid=[], must_use_trend=True)))


class LongDialogue(unittest.TestCase):
    def test_lines_that_do_not_fit_hold_the_last_shot_instead_of_failing(self):
        """12 Nov 18:50 a whole episode failed in the sound step: "A párbeszéd nem fér el az epizódban"."""
        import numpy as np
        import story_audio as sa
        plan = dict(frames=240, scenes=[dict(frames=120, lines=[dict(speaker='lead', text='a')]), dict(frames=120, lines=[dict(speaker='support', text='b')])], voices={})
        long_line = np.ones(round(sa.RATE * 6.5), dtype=np.float32)
        with patch('story_audio.speak', return_value=long_line), patch('story_audio.fit_voice', side_effect=lambda x, rate, n, ff: x[:n]):
            with self.assertRaises(sa.NeedsTime) as short:
                sa.dialogue(None, plan, plan['frames'] * sa.RATE // 24, None)
            self.assertTrue(sa.stretch(plan, short.exception.extra))
            self.assertGreater(plan['scenes'][-1]['frames'], 120)
            self.assertGreater(plan['scenes'][0]['frames'], 120)        # every shot grows, the lines stay with their pictures
            self.assertEqual(plan['frames'], sum(sc['frames'] for sc in plan['scenes']))
            placed = sa.dialogue(None, plan, plan['frames'] * sa.RATE // 24, None)
        self.assertEqual(len(placed), 2)
        self.assertLessEqual(placed[-1][0] + len(placed[-1][1]), plan['frames'] * sa.RATE // 24)

    def test_lines_are_never_sped_up_while_the_episode_can_grow(self):
        import numpy as np
        import story_audio as sa
        plan = dict(frames=240, scenes=[dict(frames=240, lines=[dict(speaker='lead', text='a')])], voices={})
        line = np.ones(round(sa.RATE * 11), dtype=np.float32)          # 11 s of speech in a 10 s episode
        with patch('story_audio.speak', return_value=line):
            with self.assertRaises(sa.NeedsTime):
                sa.dialogue(None, plan, plan['frames'] * sa.RATE // 24, None)

    def test_an_episode_never_grows_past_its_cap(self):
        import story_audio as sa
        plan = dict(frames=24 * 20, scenes=[dict(frames=24 * 20)])
        self.assertFalse(sa.stretch(plan, sa.RATE * 30))
        self.assertEqual(plan['frames'], 24 * 20)


class StorySpeed(unittest.TestCase):
    def test_story_steps_give_the_fast_model_time_to_answer(self):
        """13 Nov: qwen3.5:9b missed a 90 s slot, the 27B took over at ~130 s a call and an episode took 26 minutes."""
        import autonomous
        seen = {}
        def fake(service, route, request, timeout=8):
            seen.update(budget=request['_orbit_budget'], timeout=timeout, purpose=request['_orbit_purpose'], length=request['options']['num_predict'])
            return dict(message=dict(content='{}'))
        studio = unittest.mock.MagicMock()
        studio.agent.return_value = dict(model='auto')
        studio.cancelled.return_value = False
        with patch('studio.local_api', side_effect=fake):
            autonomous.ask_json(studio, dict(id='j', agent='a', payload=json.dumps(dict(story_step='hook'))), 'Write.', dict(x=1))
        self.assertEqual((seen['budget'], seen['timeout'], seen['purpose']), (200, 300, 'utility'))
        self.assertEqual(seen['length'], 900)   # an idea cannot ramble on until the slot runs out

    def test_small_pictures_are_drawn_small(self):
        # Pictures and the prop show at most ~400 px high: drawing them at 512 saves about two minutes an episode.
        source = (WEB.parent / 'story_animation.py').read_text(encoding='utf-8')
        self.assertIn("jobs.append((pictures[show],512,512,", source)
        self.assertIn("jobs.append((prop,512,512,", source)

class PublishCopy(unittest.TestCase):
    def test_every_episode_gets_ready_to_paste_upload_text(self):
        import story_animation as sa
        hook = dict(hook_caption='POV: the sky is just a balloon', payoff_caption="It's giving helium leak",
                    premise='Two stickmen treat the sky as a balloon and escalate until their',
                    trend="Portland newscaster reflects on viral 'exploding whale' video - Oregon Public Broadcasting - OPB")
        copy = sa.publish_copy(dict(title='The Whale'), hook)
        self.assertEqual(copy['title'], 'POV: the sky is just a balloon')
        self.assertIn("It's giving helium leak.", copy['description'])
        self.assertNotIn('escalate until', copy['description'])        # the internal premise is not for viewers
        self.assertNotIn('OPB', copy['description'])
        self.assertEqual(copy['hashtags'][:4], ['#shorts', '#animation', '#funny', '#brainrot'])
        self.assertIn('#portland', copy['hashtags'])
        self.assertNotIn('#reflects', copy['hashtags'])
        self.assertIn('feltölteni neked kell', copy['text'])

class PunchUp(unittest.TestCase):
    def plan(self):
        return dict(scenes=[dict(beat=b, frames=72, visual_action='x', show='Anxious lying on the floor.', lines=[dict(speaker='lead', text='You good?')]) for b in ('hook', 'twist')])

    def test_fresh_lines_and_concrete_pictures_replace_the_weak_ones(self):
        import story_animation as sa
        out = dict(scenes=[dict(lines=[dict(speaker='lead', text='Crunchy carrot. No sugar allowed today.')], show='a crushed candy cane under a boot'),
                           dict(lines=[dict(speaker='lead', text='I ate the whole sugar box.')], show='a limp feeling of regret')])
        with patch('story_animation.punch_writer', return_value=out) as ask:
            plan = sa.punch_up(None, dict(id='j'), self.plan(), dict(hook_caption='POV: no sugar', payoff_caption='You dream of sugar'))
        self.assertEqual(plan['scenes'][0]['lines'][0]['text'], 'Crunchy carrot. No sugar allowed today.')
        self.assertEqual(plan['scenes'][0]['show'], 'a crushed candy cane under a boot')
        self.assertEqual(plan['scenes'][1]['show'], 'Anxious lying on the floor.')        # a feeling is not a picture: kept
        self.assertNotIn('You good?', json.dumps(ask.call_args[0][3]))                     # the old lines are not shown to it

    def test_a_wrong_answer_keeps_the_writers_version(self):
        import story_animation as sa
        with patch('story_animation.punch_writer', return_value=dict(scenes=[dict(lines=[dict(speaker='lead', text='x')], show='a cat')])):
            plan = sa.punch_up(None, dict(id='j'), self.plan(), {})
        self.assertEqual(plan['scenes'][0]['lines'][0]['text'], 'You good?')


if __name__ == '__main__':
    unittest.main()
