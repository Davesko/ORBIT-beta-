"""The rig animation engine: continuous motion for the whole shot, voice-driven mouths, and the plan fields it needs."""
import unittest

import story_episode
import story_puppet as rig


class Rig(unittest.TestCase):
    def test_motion_is_smooth_through_lines_gestures_and_loops(self):
        """13 Nov (owner): "nagyon hirtelen, felesleges, túlzó". The captured talk loop jumped ~100 px every four
        seconds, a line start switched clips in one frame, and gestures looped all shot long."""
        import os
        import story_mocap
        tracks = story_mocap.load(os.path.expanduser('~/Library/Application Support/Orbit/mocap/tracks.json'))
        if not tracks:
            self.skipTest('no mocap tracks installed')
        old, rig.TRACKS = rig.TRACKS, tracks
        self.addCleanup(setattr, rig, 'TRACKS', old)
        for action in ('talk', 'shrug', 'point', 'facepalm'):
            actor = rig.Rig(rig.design('Krix: kobold, jittery and restless', rig.COLOURS['green']), 320., 1)
            actor.onset = 1.
            prev, worst = None, 0.
            for frame in range(240):
                level = .3 if 24 <= frame < 96 or 130 <= frame < 200 else 0.
                actor.update(action, frame / 24, 10., frame / 24, level, 440.)
                if prev:
                    worst = max(worst, *(abs(actor.values[k] - prev[k]) for k in ('lx', 'ly', 'rx', 'ry')))
                    self.assertLess(abs(actor.values['tilt'] - prev['tilt']), 6, action)
                prev = dict(actor.values)
            self.assertLess(worst, 32, action)
        # a gesture is played once: long after the line started the body is back to talking
        actor = rig.Rig(rig.design('A: round head', rig.COLOURS['yellow']), 320., 1);actor.onset = .5
        for frame in range(200):
            actor.update('shrug', frame / 24, 9., frame / 24, .3, 440.)
        talker = rig.Rig(rig.design('A: round head', rig.COLOURS['yellow']), 320., 1)
        for frame in range(200):
            talker.update('talk', frame / 24, 9., frame / 24, .3, 440.)
        self.assertLess(abs(actor.values['ly'] - talker.values['ly']), 40)

    def test_the_kobold_has_narrowed_slightly_red_eyes(self):
        import story_episode
        krix = rig.design(story_episode.CAST['lead'], rig.COLOURS['green'])
        self.assertTrue(krix['squint']);self.assertTrue(krix['red_eyes']);self.assertEqual(krix['iris'], rig.COLOURS['yellow'])
        self.assertEqual(krix['head'], 'oval')
        self.assertFalse(rig.design(story_episode.CAST['support'], rig.COLOURS['green'])['red_eyes'])

    def test_talking_never_reaches_into_the_other_character(self):
        import os
        import story_mocap
        tracks = story_mocap.load(os.path.expanduser('~/Library/Application Support/Orbit/mocap/tracks.json'))
        if not tracks:
            self.skipTest('no mocap tracks installed')
        old, rig.TRACKS = rig.TRACKS, tracks
        self.addCleanup(setattr, rig, 'TRACKS', old)
        for side in (1, -1):
            actor = rig.Rig(rig.design('A: round head', rig.COLOURS['yellow']), 320. if side > 0 else 760., side)
            reach = 0.
            for name in ('talk', 'idle', 'point', 'shrug'):
                for frame in range(0, 240, 2):
                    actor.update(name, frame / 24, 10., frame / 24, .2, 440.)
                    reach = max(reach, actor.values['lx'] * side, actor.values['rx'] * side)
                    self.assertLessEqual(abs(actor.values['lean']), 12 if name != 'shrug' else 40)
            self.assertLessEqual(reach, 440 * .48 + 1)      # captured talk reached 310 px towards a partner 440 px away

    def test_every_action_keeps_moving_to_the_end_of_a_shot(self):
        for name in rig.ACTIONS:
            spot = rig.Rig(rig.design('round yellow head, blue hoodie', rig.COLOURS['yellow']), 300., 1)
            late = []
            for frame in range(96):
                spot.update(name, frame / 24, 4., frame / 24, 0.)
                if frame >= 72:
                    late.append(tuple(spot.values.values()))
            self.assertGreater(len(set(late)), 20, name)

    def test_look_comes_from_the_description(self):
        look = rig.design('Zag: round green head, backwards red cap, baggy grey sweatshirt', rig.COLOURS['yellow'])
        self.assertEqual((look['skin'], look['cap'], look['cloth']), (rig.COLOURS['green'], rig.COLOURS['red'], rig.COLOURS['grey']))
        mira = rig.design('Mira: tall oval pink head, long purple hair, round glasses, yellow dress', rig.COLOURS['yellow'])
        self.assertEqual((mira['head'], mira['hair'], mira['glasses'], mira['skirt'], mira['size']), ('oval', 'long', True, True, 1.1))
        looks = {(d['head'], d['hair'], d['size'], d['girth']) for d in (rig.design(f'Character {i}: a person', rig.COLOURS['yellow']) for i in range(12))}
        self.assertGreaterEqual(len(looks), 6, 'undescribed characters still differ from each other')
        self.assertEqual(rig.design('Bo: a person', (1, 2, 3)), rig.design('Bo: a person', (1, 2, 3)))

    def test_walking_crosses_the_stage_and_the_camera_keeps_cutting(self):
        self.assertAlmostEqual(rig.travel('walk_in', 0, 4., 1), -rig.OFFSTAGE)
        self.assertAlmostEqual(rig.travel('walk_in', 3.9, 4., 1), 0)
        self.assertAlmostEqual(rig.travel('walk_out', 4., 4., -1), rig.OFFSTAGE)
        self.assertIsNone(rig.travel('talk', 1, 4., 1))
        walker = rig.Rig(rig.design('A: round head', rig.COLOURS['yellow']), 320., 1)
        walker.snap_root()
        for frame in range(30):
            walker.update('walk_in', frame / 24, 4., frame / 24, 0.)
        self.assertTrue(walker.walking);self.assertGreater(walker.stride, 3)
        quiet = dict(lead=[0.] * 240, support=[0.] * 240)
        plan = rig.cuts(dict(framing='wide', cast='both', acting=dict(lead='talk', support='stare')), 240, quiet, 5)
        self.assertEqual(len(plan), 2);self.assertGreaterEqual(len({c[1] for c in plan}), 2)   # calm: no random cut storm (13 Nov)
        turn = dict(lead=[.3] * 100 + [0.] * 140, support=[0.] * 110 + [.3] * 90 + [0.] * 40)
        talk = rig.cuts(dict(framing='two', cast='both', acting=dict(lead='talk', support='talk')), 240, turn, 5)
        self.assertEqual([c[2] for c in talk], ['lead', 'support'])             # the picture goes to whoever speaks
        self.assertTrue(96 <= talk[1][0] <= 112, talk)
        moving = rig.cuts(dict(framing='close', cast='both', acting=dict(lead='walk_in', support='stare')), 240, quiet, 5)
        self.assertTrue(all(c[1] in ('wide', 'two') for c in moving), 'a walk is never hidden by a close-up')
        zoom, cx, cy = rig.camera(plan, 10, 240, dict(cast='both'), dict(lead=320., support=760.))
        self.assertTrue(.9 < zoom < 2 and 0 < cx < rig.W)

    def test_speech_opens_the_right_mouth_only(self):
        levels = rig.envelopes([dict(speaker='lead', start=.5, envelope=[.4, .9])], 24)
        self.assertEqual(levels['lead'][12:14], [.4, .9])
        self.assertEqual(max(levels['support']), 0)

    def test_acting_survives_replanning_and_defaults_safely(self):
        first = story_episode.acting(dict(lead_action='shock', support_action='laugh', prop_motion='grow'))
        self.assertEqual(story_episode.acting(first)['acting'], first['acting'])
        self.assertEqual(story_episode.acting(dict(lead_action='fly'))['acting'], dict(lead='idle', support='idle', prop='none'))

    def test_staging_keeps_the_punchline_and_shows_the_prop(self):
        shots=[dict(beat=b,caption='recharging is a scam' if b=='twist' else '',lines=[dict(speaker='support',text='Recharging is a scam.')] if b=='reaction' else [],
                    acting=dict(lead='shock',support='talk',prop='none')) for b in ('hook','reaction','twist','loop')]
        story_episode.staging(shots)
        self.assertEqual(shots[1]['lines'],[])
        lead=[s['acting']['lead'] for s in shots]
        self.assertTrue(all(a!=b for a,b in zip(lead,lead[1:])) and max(map(lead.count,lead))<=2,lead)
        self.assertEqual(shots[0]['acting']['support'],'stare')
        self.assertEqual((shots[2]['acting']['prop'],shots[3]['acting']['prop']),('fly_in','wobble'))


    def test_actions_are_read_from_the_shot_text(self):
        shots=[dict(beat='hook',caption='',lines=[],visual_action="Pip's mouth forms an O of terror; Dot holds the toothbrush",acting=dict(lead='talk',support='idle',prop='none')),
               dict(beat='twist',caption='',lines=[dict(speaker='support',text='just a toothbrush')],visual_action='Dot clicks a switch on the nightstand',acting=dict(lead='idle',support='idle',prop='fly_in'))]
        story_episode.staging(shots,dict(lead='Pip',support='Dot'))
        self.assertEqual([s['acting']['lead'] for s in shots],['shock','stare'])
        self.assertEqual([s['acting']['support'] for s in shots],['idle','point'])
        wide=[dict(beat='setup',caption='',cast='lead',framing='close',lines=[dict(speaker='support',text='hm')],visual_action='',acting=dict(lead='idle',support='idle',prop='none'))]
        story_episode.staging(wide,dict(lead='Pip',support='Dot'))
        # Owner 12 Nov: calm acting; the silent listener watches the speaker instead of being made to walk in.
        self.assertEqual((wide[0]['cast'],wide[0]['acting']),('both',dict(lead='stare',support='talk',prop='none')))

    def test_a_push_reaches_the_other_and_the_other_reacts(self):
        self.assertAlmostEqual(rig.travel('push', rig.CONTACT, 4., 1, 440.), 190.)
        self.assertLess(rig.travel('hit_push', rig.CONTACT + 1, 4., -1, 440.), 0) if False else self.assertGreater(rig.travel('hit_push', rig.CONTACT + 1, 4., -1, 440.), 0)
        self.assertAlmostEqual(rig.travel('handshake', rig.CONTACT, 4., -1, 440.), -105.)
        for name in ('push', 'slap', 'handshake', 'hug', 'hit_push', 'hit_slap', 'crouch', 'hat_off', 'run'):
            pose, _ = rig.action_pose(name, 1.2, 4., False, 1)
            self.assertTrue(pose, name)
        capped = rig.Rig(rig.design('Ty: round head, red cap', rig.COLOURS['yellow']), 300., 1)
        capped.update('hat_off', 1.0, 4., 1.0, 0.)
        self.assertGreater(capped.hat_lift, .5)
        story = [dict(beat='hook', caption='', lines=[], visual_action='Pip slaps Dot and takes off his cap', acting=dict(lead='talk', support='idle', prop='none'))]
        story_episode.staging(story, dict(lead='Pip', support='Dot'))
        self.assertEqual(story[0]['acting']['lead'], 'slap')

    def test_shots_are_grouped_into_at_most_three_places(self):
        import story_animation
        shots=[dict(setting=s) for s in ('a dark cave with a small fire','inside the dark cave near the fire','a green jungle clearing','a riverbank at sunset','a busy market')]
        spots=story_animation.places(shots,'cave')
        self.assertEqual(len(spots),3);self.assertEqual([s['plate'] for s in shots[:3]],[0,0,1])
        look=rig.design('Old farmer: round white head, tan sun hat, brown mustache, beige shirt with suspenders, boots',rig.COLOURS['white'])
        self.assertEqual((look['brim'] is not None,look['cap'],look['mustache'],look['boots'],look['collar']),(True,None,True,True,True))

    def test_the_owners_topic_and_explainer_format_are_kept(self):
        import story_animation as sa
        self.assertEqual(sa.owner_topic('kezdj el videót gyártani: What did ancient humans do when they were bored?'),'What did ancient humans do when they were bored?')
        self.assertTrue(sa.explainer('How Meat Was Cooked 10,000 Years Ago (Stickman Edition)'))
        self.assertTrue(sa.explainer(sa.owner_topic('kezdj el videót gyártani: What did ancient humans do when they were bored?')))
        self.assertFalse(sa.explainer('két haver a kanapén PS5-öznek'))
        self.assertEqual(sa.owner_topic(sa.DEFAULT_BRIEF),'')

    def test_an_explainer_gets_narration_and_more_than_one_place(self):
        shots=[dict(beat=b,setting='a prehistoric cave',visual_action=f'Rex holds a raw steak over the fire and waits, step {i}. Then more.',voice='',caption='',lines=[])
               for i,b in enumerate(('hook','setup','escalation','reaction','twist','loop'))]
        story_episode.narrate(shots)
        self.assertTrue(all(len(s['voice'].split())>=5 for s in shots))
        self.assertEqual(shots[1]['caption'],shots[1]['voice'][:75])
        self.assertGreaterEqual(len({s['setting'] for s in shots}),3)


class Recovery(unittest.TestCase):
    def test_copied_beats_are_found_by_action_or_result(self):
        scenes=[dict(visual_action=f'a{i}',visible_result=f'r{i}') for i in range(3)]
        scenes+=[dict(visual_action='a0',visible_result='new'),dict(visual_action='x',visible_result='r1'),dict(visual_action='y',visible_result='z')]
        self.assertEqual(story_episode.copied(scenes),[3,4])

    def test_only_the_copied_shots_are_written_again(self):
        from unittest.mock import patch
        import story_animation
        beats=story_episode.MEME_BEATS
        shot=lambda i:dict(setting='A dark bedroom with one small lamp',opening_image=f'Pip sits up in bed, moment number {i}.',
                           visual_action=f'Pip lifts the blanket slowly, attempt {i}.',visible_result=f'The blanket slides down, step {i}.',
                           camera='Static',cast='both',voice='',caption='',sfx='none',lines=[],lead_action='shock',support_action='stare',prop_motion='none',seated=False)
        scenes=[shot(i) for i in range(6)]
        scenes[4]=dict(shot(4),visual_action=scenes[1]['visual_action'],visible_result=scenes[1]['visible_result'])
        draft=dict(title='T',story_prop='A yellow electric toothbrush.',music='suspense',music_prompt='eerie low strings',scenes=scenes)
        selected=story_episode.meme_profile(24,story_episode.SERIES)
        premise=dict(art=selected['art'],profile=selected)
        asked={}
        def fake(s,job,instruction,data):
            asked.update(data);return dict(scenes=[shot(9)])
        with patch('autonomous.ask_json',fake):
            plan=story_animation.rewrite_copied(None,None,'write',dict(premise=premise),draft,selected,24)
        self.assertEqual(asked['rewrite_beats'],[beats[4]])
        self.assertIn('attempt 9',plan['scenes'][4]['visual_action'])

    def test_wan_runs_only_when_the_request_names_it(self):
        import story_animation
        self.assertFalse(story_animation.model_named('készíts egy videót a helyi video generáló modellel, ijesztő hangulatban'))
        self.assertTrue(story_animation.model_named('készíts stickman videót a Wan 2.2 modellel'))
        self.assertEqual(story_animation.brief_mood('egy ijesztő hangulatú videó'),'suspense')
        self.assertIsNone(story_animation.brief_mood('két haver a kanapén'))

    def test_announced_work_without_an_action_is_caught(self):
        import commander
        self.assertTrue(commander.PROMISE.search('Most megvizsgálom az ügynököt, és úgy alakítom át a promptot.'))
        self.assertIsNone(commander.PROMISE.search('Elkészült a videó, megtalálod az Alkotások között.'))


if __name__ == '__main__':
    unittest.main()
