"""17 Nov: the errors found in the "Trapped in a hospital when the power dies" Short, one test each."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stickman_studio as st
from studio import Studio


def shot(say, kind='wide', place='ward', **extra):
    return dict(dict(say=say, kind=kind, place=place, hud='', actors=[dict(who='main', action='idle', expression='neutral', prop='none', x=.5)], sound='none'), **extra)


class Hospital(unittest.TestCase):
    def test_a_power_cut_darkens_the_place_and_the_lights_come_back(self):
        shots = st.fx_from_words([shot('Every screen has just gone black.'), shot('The ventilator stops because there is no power.'), shot('The lights flicker on.')])
        self.assertEqual(shots[0]['fx'], 'dark')
        self.assertEqual(shots[1]['fx'], 'dark_hold')
        self.assertEqual(shots[2]['fx'], 'lights_on')

    def test_carrying_a_hose_does_not_spray_water(self):
        shots = st.fx_from_words([shot('You grab the heavy red hose. It is thick and stiff.'), shot('The red fire hose cabinet is open.')])
        self.assertTrue(all(x.get('fx') != 'spray' for x in shots))
        self.assertEqual(st.fx_from_words([shot('The hose sprays across the ice.')])[0]['fx'], 'spray')

    def test_adverbs_and_pronouns_are_not_painted_as_tools(self):
        shots = [shot('You carry it back to the patient\'s bed.'), shot('You tie one end tightly around the patient\'s mask.'), shot('You hold the other end and pump it.'),
                 shot('You grab a snow shovel.')]
        st.find_tools(shots)
        self.assertEqual([x['actors'][0].get('tool') for x in shots], [None, None, None, 'snow shovel'])

    def test_a_cue_stays_only_when_the_words_make_the_sound(self):
        shots = [shot('You have 5 hours to keep the air moving.', 'card', sound='footsteps'), shot('You pump it like a bellows.', 'medium', sound='splat'),
                 shot('You run to the corridor.', 'wide', sound='footsteps'), shot('The heavy steel doors have dropped into place.', 'medium', sound='boom')]
        st.sound_check(shots)
        self.assertEqual([x['sound'] for x in shots], ['none', 'none', 'footsteps', 'boom'])

    def test_pumping_and_tying_are_working_movements(self):
        shots = [shot('You hold the other end and pump it like a bellows.', 'medium'), shot('You keep pumping, arm after arm.', 'medium')]
        shots = st.plausible(shots, None)
        self.assertEqual([x['actors'][0]['action'] for x in shots], ['crank', 'crank'])

    def test_the_countdown_is_shown_when_the_writer_left_it_empty(self):
        shots = [shot('It is 2:00 AM.'), shot('You have 5 hours to keep the air moving.', 'card')] + [shot('You do step %d.' % n) for n in range(8)]
        st.fill_counter(shots, dict(counter='HOURS', mission='You have 5 hours to keep the air moving in this sealed room.'))
        self.assertEqual(shots[0]['hud'], '')
        self.assertEqual(shots[1]['hud'], 'HOURS LEFT: 5')
        self.assertTrue(int(shots[-1]['hud'].split(':')[1]) <= 2)
        values = [int(x['hud'].split(':')[1]) for x in shots[1:]]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_a_counter_the_writer_filled_is_not_touched(self):
        shots = [shot('x', hud='DAY 3')]
        self.assertEqual(st.fill_counter(shots, dict(counter='DAY', mission='You have 5 days.'))[0]['hud'], 'DAY 3')

    def test_a_resolution_that_only_retells_the_shots_is_not_added(self):
        shots = [shot('You uncoil the fire hose.'), shot('You tie one end around the patient\'s mask.'), shot('You pump air into the mask until the last tank empties.'),
                 shot('7:01 AM. The lights flicker on.')]
        before = len(shots)
        st.frame_story(shots, dict(resolution='You use the fire hose to pump air into the mask just as the last tank empties.', mission=''))
        self.assertEqual(len(shots), before)
        st.frame_story(shots, dict(resolution='The rescue team breaks the door and carries the patient out.', mission=''))
        self.assertEqual(len(shots), before + 1)

    def test_the_patient_lies_in_the_bed_of_every_wide_shot_after_the_mention(self):
        shots = [shot('You are alone in the main ward.'), shot('Keep the patient breathing.', 'medium'), shot('You wait.'), shot('You pump.', 'close')]
        st.add_patient(shots)
        self.assertEqual(len(shots[0]['actors']), 1)
        self.assertEqual(len(shots[2]['actors']), 2)
        patient = shots[2]['actors'][1]
        self.assertEqual((patient['who'], patient['action']), ('extra:person', 'sleep'))
        self.assertEqual(len(shots[3]['actors']), 1)


class Looping(unittest.TestCase):
    def test_a_looping_answer_is_asked_again_more_strictly(self):
        calls = []

        def fake(kind, path, request, timeout=0):
            calls.append((request['options']['temperature'], request['options']['repeat_penalty']))
            if len(calls) < 3:
                raise ValueError('A terv túl hosszú lett. Részleges műveletsor nem hajtható végre; kérj kisebb lépéseket.')
            return dict(message=dict(content='{"a": 1}'))

        with tempfile.TemporaryDirectory() as tmp:
            s = Studio(Path(tmp))
            self.addCleanup(s.db.close)
            job = dict(id='j', agent='a')
            with patch('studio.local_api', side_effect=fake), patch.object(s, 'agent', return_value=dict(model='auto')), patch.object(s, 'cancelled', return_value=False), patch.object(s, 'job_stage'):
                self.assertEqual(st.ask(s, job, 'x', {}, {}, temperature=.85), dict(a=1))
        self.assertEqual(len(calls), 3)
        self.assertLess(calls[2][0], calls[0][0])
        self.assertGreater(calls[2][1], calls[0][1])

    def test_other_errors_are_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Studio(Path(tmp))
            self.addCleanup(s.db.close)
            with patch('studio.local_api', side_effect=ValueError('A helyi AI válasza túllépte az időkeretet.')) as api, patch.object(s, 'agent', return_value=dict(model='auto')):
                with self.assertRaises(ValueError):
                    st.ask(s, dict(id='j', agent='a'), 'x', {}, {})
            self.assertEqual(api.call_count, 1)


if __name__ == '__main__':
    unittest.main()


class Review17Nov(unittest.TestCase):
    def test_only_real_events_make_a_sound_and_at_the_word(self):
        self.assertIsNone(st.sound_event('The lights flicker. Sparks fly.'))             # a picture effect is silent
        self.assertIsNone(st.sound_event('You walk to the corridor and look around.'))
        self.assertEqual(st.sound_event('The heavy door slams shut behind you.')['key'], 'slam')
        self.assertEqual(st.sound_event('Somebody knocks twice.')['key'], 'knock')
        self.assertEqual(st.sound_event('The freezer hums.')['what'], 'a freezer humming steadily')
        shot = dict(start=10., end=14.)
        words = [dict(w='The', s=10.2, e=10.3), dict(w='door', s=10.4, e=10.6), dict(w='slams', s=11.1, e=11.4), dict(w='shut', s=11.5, e=11.8)]
        self.assertEqual(st.event_time(words, shot, st.sound_event('The door slams shut.')), 11.1)

    def test_a_changed_object_is_shown_painted(self):
        shots = [shot('You walk in.'), shot('The rope is thicker than it was yesterday.', 'medium'), shot('You pull it.')]
        st.state_inserts(shots, limit=1)
        self.assertEqual(shots[1]['kind'], 'insert')
        self.assertIn('rope', shots[1]['insert_what'])
        self.assertEqual(shots[1]['actors'], [])
        self.assertEqual(shots[0]['kind'], 'wide')
        same = [shot('You are thicker than yesterday.')]
        self.assertEqual(st.state_inserts(same, limit=1)[0]['kind'], 'wide')      # a person is not painted as an object

    def test_a_complicated_place_is_shown_not_walked(self):
        shots = [shot('The mine has two levels and one air shaft.', 'medium'), shot('You grab the lantern from the wall.', 'medium')]
        shots[0]['actors'][0]['action'] = 'walk'
        shots[0]['actors'][0]['to'] = .7
        st.explain_space(shots)
        self.assertEqual(shots[0]['kind'], 'top')
        self.assertNotIn('to', shots[0]['actors'][0])
        self.assertNotEqual(shots[0]['actors'][0]['action'], 'walk')
        self.assertEqual(shots[1]['kind'], 'medium')

    def test_the_story_cannot_leave_the_power_out(self):
        o = dict(hook='x', premise='The power dies in the hospital.', mission='You have 5 hours.', goal='g', chapters=[dict(summary='The ventilator stops.', solution='You pump air by hand.',
                 steps=[dict(do='You pump the bag.', result='The patient breathes.')])], resolution='At dawn the staff arrives.', ending='e', low_point='l')
        self.assertIn('lights are out', st.unhandled(o))
        o['chapters'][0]['steps'].append(dict(do='You hold a flashlight in your teeth.', result='You can see the bag.'))
        o['conditions'] = [dict(problem='The power is out.', handled_by='You use a flashlight from the nurse desk.')]
        self.assertEqual(st.unhandled(o), '')

    def test_overused_tropes_are_banned_for_the_next_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Studio(Path(tmp))
            self.addCleanup(s.db.close)
            rows = [dict(title='Trapped When The Power Dies', premise='A blackout seals you in.')] * 3 + [dict(title='Farm Day', premise='Goats get out.')]
            with patch.object(st, 'recent', return_value=rows):
                banned = st.overused(s, 'p')
        self.assertIn('power', banned)
        self.assertIn('locked', banned)
        self.assertNotIn('flood', banned)

    def test_a_failed_review_is_not_a_passed_review(self):
        shots = [shot('You do step %d.' % n) for n in range(6)]
        outline = dict(mission='m')
        with tempfile.TemporaryDirectory() as tmp:
            from types import SimpleNamespace
            s = SimpleNamespace(root=Path(tmp), job_stage=lambda *a: None)
            with patch.object(st, 'ask', side_effect=ValueError('A helyi AI válasza túllépte az időkeretet.')):
                st.review_logic(s, dict(id='j', agent='a'), shots, outline)
            self.assertEqual(outline['review']['status'], 'not_verified')
            with patch.object(st, 'ask', return_value=dict(problems=[], fixes=[])):
                st.review_logic(s, dict(id='j', agent='a'), shots, outline)
            self.assertEqual(outline['review']['status'], 'verified')


class Ferry17Nov(unittest.TestCase):
    """The errors of the 4:45 ferry video, one test each."""

    def test_the_countdown_follows_the_mission_and_the_narrated_time(self):
        shots = [shot('The water comes in.'), shot('You have 60 minutes to move this ferry.', 'card')] + [shot('You do step %d.' % n) for n in range(10)] + [shot('Minute 58. The propellers clear the mud.'), shot('Done.')]
        st.fill_counter(shots, dict(counter='', mission='You have 60 minutes to move this ferry to open water.'))
        self.assertEqual(shots[0]['hud'], '')
        self.assertEqual(shots[1]['hud'], 'MINUTES LEFT: 60')
        self.assertEqual(shots[-2]['hud'], 'MINUTES LEFT: 2')                  # minute 58 of 60
        values = [int(x['hud'].split(':')[1]) for x in shots[1:]]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_a_sparse_wrong_counter_is_replaced(self):
        shots = [shot('x')] * 10
        shots = [dict(s_, hud='') for s_ in shots]
        shots[8]['hud'] = 'MINUTE LEFT: 8'
        st.fill_counter(shots, dict(counter='', mission='You have 10 minutes to leave.'))
        self.assertTrue(all(x['hud'] for x in shots))

    def test_cold_words_stay_out_of_a_warm_river_story(self):
        shots = [shot('The air is freezing.'), shot('The steering wheel is frozen solid.'), shot('The panel is cold and wet.')]
        st.climate_fix(shots, dict(premise='A storm surge floods a ferry on a river.', places=[dict(look='A concrete car deck.')]))
        self.assertEqual([x['say'] for x in shots], ['The air is damp.', 'The steering wheel is stuck solid.', 'The panel is wet.'])
        cold = [shot('The air is freezing.')]
        st.climate_fix(cold, dict(premise='A blizzard cuts off the hut.', places=[]))
        self.assertEqual(cold[0]['say'], 'The air is freezing.')

    def test_garbage_tools_props_and_vehicles_are_gone(self):
        shots = [shot('You raise your arms high.'), shot('You swing the wrench down hard.'), shot('You swing again. Harder this time.'), shot('You grab the bolt cutters.')]
        st.find_tools(shots)
        self.assertEqual([x['actors'][0].get('tool') for x in shots], [None, None, None, 'bolt cutters'])
        can = [shot('The pin is out. You can steer now.', 'close')]
        self.assertEqual(st.plausible(can, None)[0]['actors'][0]['prop'], 'none')
        tin = [shot('You pick up the can.', 'medium')]
        self.assertEqual(st.plausible(tin, None)[0]['actors'][0]['prop'], 'can')
        moves = st.clean_shot(dict(say='You swing the wrench down hard.', kind='medium', place='bridge', moving=[dict(kind='vehicle', what='steering wheel', where='center')]), [dict(id='bridge')], '')
        self.assertNotIn('moving', moves)

    def test_a_label_never_ends_on_a_hanging_word(self):
        shots = [shot('x', 'card', card=dict(type='stat', value='10', label='seconds hold there for')), shot('y', 'card', card=dict(type='stat', value='50%', label='climbs to'))]
        st.fix_labels(shots)
        self.assertEqual(shots[0]['card']['label'], 'seconds')
        self.assertEqual(shots[1]['card']['label'], 'climbs')

    def test_the_resolution_must_finish_the_last_problem(self):
        chapters = [dict(title='The sandbar', summary='The ship grounds on a sandbar.', solution='You drag the ship off the mud with the anchor chain.', steps=[dict(do='You drop the anchor chain.', result='The ship slides off the mud.')]),
                    dict(title='The leak', summary='The hatch leaks again.', solution='You weld a steel plate over the gap.', steps=[dict(do='You weld the plate.', result='The water stops.')])]
        o = dict(chapters=chapters, resolution='At minute 58 the anchor chain drags the ship off the mud of the sandbar.')
        self.assertIn('LAST problem', st.resolution_problem(o))
        self.assertEqual(st.resolution_problem(dict(o, resolution='The welded plate holds and the water stops for good.')), '')

    def test_real_events_that_were_silent_now_sound(self):
        for text, key in (('You pull the large red lever down.', 'lever'), ('The metal gate slides into the water.', 'slide'), ('You swing the wrench down hard.', 'strike'),
                          ('It sputters once. Then it roars to life.', 'roar'), ('The heavy chain drops into the river.', 'chain'), ('You cut the lock on the hawse pipe.', 'snap')):
            self.assertEqual(st.sound_event(text)['key'], key, text)
        self.assertIsNone(st.sound_event('She hits the button.'))

    def engineer(self, answers):
        out = dict(title='t', premise='p', places=[dict(id='a', look='deck')], chapters=[
            dict(title='Weight', summary='too heavy', solution='You push three cars overboard and the bow rises two metres.', steps=[dict(do='You push the cars.', result='The bow rises.')]),
            dict(title='Leak', summary='leak', solution='You weld a plate.', steps=[dict(do='You weld.', result='Dry.')])])
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            s = SimpleNamespace(root=Path(tmp), job_stage=lambda *a: None)
            effect = [a if not isinstance(a, Exception) else a for a in answers]
            with patch.object(st, 'ask', side_effect=effect) as ask:
                st.engineer_review(s, dict(id='j', agent='a'), out)
        return out, ask.call_count

    FIX = dict(chapters=[dict(index=0, problem='Three cars weigh nothing against a ferry.', solution='You move the heavy cargo to the stern with the deck winch to trim the bow by 20 cm.',
                              steps=[dict(do='You hook the winch to the first truck.', result='The cable tightens.'), dict(do='You pull it two bays back.', result='The bow lifts a little.'),
                                     dict(do='You chock its wheels.', result='It stays put.')])])

    def test_a_fixed_outline_is_read_again_and_only_then_verified(self):
        out, calls = self.engineer([self.FIX, dict(chapters=[])])
        self.assertEqual(calls, 2)
        self.assertEqual(out['engineering']['status'], 'verified')
        self.assertIn('winch', out['chapters'][0]['solution'])
        self.assertEqual(out['chapters'][1]['solution'], 'You weld a plate.')
        self.assertEqual(out['engineering']['version'], st.fingerprint(out))

    def test_an_objection_without_a_valid_answer_is_needs_revision_not_checked(self):
        bad = dict(chapters=[dict(index=0, problem='Dangerous and useless ramp.', solution='no', steps=[])])
        out, calls = self.engineer([bad])
        self.assertEqual(out['engineering']['status'], 'needs_revision')
        self.assertIn('Dangerous', out['engineering']['problems'][0])
        self.assertEqual(out['chapters'][0]['solution'], 'You push three cars overboard and the bow rises two metres.')     # nothing was replaced by rubbish

    def test_a_fix_that_still_gets_an_objection_stays_needs_revision(self):
        out, _ = self.engineer([self.FIX, self.FIX])
        self.assertEqual(out['engineering']['status'], 'needs_revision')

    def test_an_unreadable_or_failed_review_is_never_verified(self):
        self.assertEqual(self.engineer([dict(verdict='fine')])[0]['engineering']['status'], 'invalid_review')
        self.assertEqual(self.engineer([ValueError('A helyi AI válasza túllépte az időkeretet.')])[0]['engineering']['status'], 'not_checked')


class Audit17Nov(unittest.TestCase):
    """The seven reproduced problems of the audit."""

    def test_a_negated_or_hypothetical_event_makes_no_sound(self):
        self.assertIsNone(st.sound_event('The door does not slam. You keep it still.'))
        self.assertIsNone(st.sound_event('If the glass breaks, they will hear you.'))
        self.assertIsNone(st.sound_event('The alarm never goes off.'))
        self.assertEqual(st.sound_event('The door slams.')['key'], 'slam')

    def test_the_rope_stays_a_rope_when_it_is_carried(self):
        shots = [shot('You grab the rope.', 'medium'), shot('You carry it to the door.', 'medium')]
        st.plausible(shots, None)
        self.assertEqual(shots[0]['actors'][0]['prop'], 'rope')
        self.assertEqual(shots[1]['actors'][0]['prop'], 'rope')

    def test_two_states_of_one_object_are_two_inserts(self):
        import tempfile
        from types import SimpleNamespace
        plan = dict(kind='short', places=[], shots=[shot('a', 'insert', insert_what='a close up of the rope, intact and dry'), shot('b', 'insert', insert_what='a close up of the rope, broken and wet')])
        with tempfile.TemporaryDirectory() as tmp:
            s = SimpleNamespace(root=Path(tmp), safe_path=lambda pid, rel: Path(tmp) / rel, job_stage=lambda *a: None)
            captured = []
            with patch.object(st, 'flux_images', side_effect=lambda s_, j, r, items, *a, **k: captured.extend(items)):
                st.paint_inserts(s, dict(project='p', id='j'), 'run', plan)
        self.assertEqual(len(captured), 2)
        self.assertNotEqual(plan['shots'][0]['insert'], plan['shots'][1]['insert'])

    def test_zero_zombies_stay_zero(self):
        out = st.clean_shot(dict(say='Nobody is there.', kind='wide', place='a', crowd=dict(kind='zombie', count=0, action='walk')), [dict(id='a')], '')
        self.assertNotIn('crowd', out)

    def test_the_countdown_reaches_zero_at_the_stated_end(self):
        shots = [shot('x'), shot('You have 60 minutes.', 'card'), shot('Minute 30.'), shot('Minute 60. It is over.'), shot('Quiet.')]
        st.fill_counter(shots, dict(counter='', mission='You have 60 minutes to leave.'))
        self.assertEqual(shots[3]['hud'], 'MINUTES LEFT: 0')
        self.assertEqual(shots[4]['hud'], 'MINUTES LEFT: 0')
        self.assertEqual(shots[2]['hud'], 'MINUTES LEFT: 30')

    def test_two_hands_on_sentences_become_two_shots(self):
        shots = [shot('You grab the rope. You pull the lever.', 'medium'), shot('You grab the rope. You grab the box.', 'medium'), shot('You walk in. It is dark.', 'medium')]
        st.split_actions(shots)
        self.assertEqual([x['say'] for x in shots], ['You grab the rope.', 'You pull the lever.', 'You grab the rope. You grab the box.', 'You walk in. It is dark.'])

    def test_a_number_in_a_hands_on_sentence_stays_an_action(self):
        shots = [shot('You carry 3 liters of water to the door.', 'medium')] + [shot('Filler %d.' % n, 'medium') for n in range(8)]
        st.ensure_cards(shots, 'short')
        self.assertEqual(shots[0]['kind'], 'medium')


class Alignment(unittest.TestCase):
    def test_known_words_get_the_times_whisper_heard(self):
        import align_runtime as al
        heard = [dict(word=' The', start=.1, end=.3), dict(word=' door', start=.35, end=.7), dict(word=' slams', start=.9, end=1.3), dict(word='shut.', start=1.35, end=1.8)]
        words, coverage = al.match('The door slams shut.', heard)
        self.assertEqual(coverage, 1.0)
        self.assertEqual([round(w['s'], 2) for w in words], [.1, .35, .9, 1.35])

    def test_a_word_whisper_missed_gets_a_time_between_its_neighbours(self):
        import align_runtime as al
        heard = [dict(word='The', start=0., end=.2), dict(word='slams', start=1.0, end=1.4)]
        words, coverage = al.match('The heavy door slams', heard)
        self.assertEqual(coverage, .5)
        self.assertFalse(words[1]['ok'])
        self.assertTrue(.2 <= words[1]['s'] < words[2]['s'] <= 1.0)

    def test_the_timeline_uses_real_times_when_they_cover_the_line_and_says_so(self):
        plan = dict(shots=[dict(say='The door slams shut.', kind='medium'), dict(say='Quiet now.', kind='medium')])
        lines = [dict(out='/a.wav'), dict(out='/b.wav')]
        aligned = {'/a.wav': dict(coverage=1.0, words=[dict(w='The', s=.1, e=.3), dict(w='door', s=.35, e=.7), dict(w='slams', s=.9, e=1.3), dict(w='shut.', s=1.35, e=1.8)])}
        words, placed = st.timeline(plan, lines, [2.0, 1.2], 1.0, aligned)
        self.assertEqual(plan['alignment']['basis'], 'partial')
        self.assertEqual(plan['alignment']['aligned'], 1)
        slams = next(w for w in words if w['w'] == 'slams')
        self.assertAlmostEqual(slams['s'], st.LEAD + .9, places=3)
        plan2 = dict(shots=[dict(say='A b.', kind='medium')])
        st.timeline(plan2, [dict(out='/z.wav')], [1.0], 1.0, None)
        self.assertEqual(plan2['alignment']['basis'], 'estimated')


class Evidence(unittest.TestCase):
    def test_the_event_report_lists_key_actions_without_a_picture(self):
        shots = [shot('You pull the lever.', 'medium'), shot('You pull the rope.', 'medium'), shot('You carry 3 liters of water.', 'card'), shot('It is quiet.', 'wide')]
        shots[0]['actors'][0]['action'] = 'pull'
        shots[1]['actors'][0]['action'] = 'look_around'
        rep = st.event_report(dict(shots=shots))
        self.assertEqual((rep['key_actions'], rep['performed'], rep['neutral_substituted'], rep['replaced_by_card_or_insert']), (3, 0, 1, 1))
        self.assertEqual(rep['planned'], 3)
        self.assertEqual({d['shot'] for d in rep['details']}, {0, 1, 2})

    def test_every_step_records_the_code_version_and_says_when_they_differ(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            s = SimpleNamespace(safe_path=lambda pid, rel: Path(tmp) / rel)
            job = dict(project='p')
            first = st.note_version(s, job, 'r', 'hook', dict(a=1))
            self.assertTrue(first['consistent'])
            with patch.object(st, 'code_version', return_value='other'):
                second = st.note_version(s, job, 'r', 'render', dict(a=1))
            self.assertFalse(second['consistent'])
            self.assertEqual(set(second['steps']), {'hook', 'render'})


class SceneEngine(unittest.TestCase):
    """The controlled scene engine (audit 17 Nov, steps 3-5)."""

    def test_the_arm_reaches_exactly_where_it_can_and_reports_what_it_cannot(self):
        import scene_events as ev
        import stickman_rig as rig
        p = dict(rig.pose('idle', 0., 1., 0))
        j = rig.skeleton(p, 400, 640, 470, 1)
        for target in ((j['shoulder'][0] + 100, j['shoulder'][1] + 10), (j['shoulder'][0] + 60, j['shoulder'][1] - 70)):
            a1, a2, miss = ev.reach_arm(j['shoulder'], target, 1, 470)
            hand = rig.skeleton(dict(p, fs=a1, fe=a2), 400, 640, 470, 1)['fhand']
            self.assertAlmostEqual(hand[0], target[0], delta=.01)
            self.assertAlmostEqual(hand[1], target[1], delta=.01)
            self.assertEqual(miss, 0.)
        far = ev.reach_arm(j['shoulder'], (j['shoulder'][0] + 400, j['shoulder'][1]), 1, 470)
        self.assertGreater(far[2], 100)                     # too far: the miss is reported, never hidden

    def test_an_impossible_event_is_refused(self):
        import scene_events as ev
        good = dict(reach=18, contact=30, turn_start=36, turn_end=58, settle=68)
        ev.compile_event(ev.turn_control('E', 'hero', 'w', 0, 35, good, release=300), {'w': 1})
        with self.assertRaises(ValueError):
            ev.compile_event(ev.turn_control('E', 'hero', 'w', 0, 35, dict(good, contact=10), release=300), {'w': 1})      # contact before reach
        with self.assertRaises(ValueError):
            ev.compile_event(ev.turn_control('E', 'hero', 'missing', 0, 35, good, release=300), {'w': 1})

    def test_nothing_changes_before_the_contact_and_the_hand_follows_the_phases(self):
        import scene_events as ev
        import scene_objects as obj
        e = ev.compile_event(ev.turn_control('E', 'hero', 'w', 0, 35, dict(reach=18, contact=30, turn_start=36, turn_end=58, settle=68), release=300,
                                              effects=[dict(type='state_change', frame=61, field='lamp.state', value='on')]), {'w': 1})
        w, lamp = obj.wheel('w', (0, 0), 10, [160, 200]), 'off'
        self.assertEqual(ev.state_at(e, 20, w, lamp), dict(wheel=0, lamp='off'))
        self.assertEqual(ev.state_at(e, 59, w, lamp)['lamp'], 'off')
        self.assertEqual(ev.state_at(e, 61, w, lamp)['lamp'], 'on')
        self.assertAlmostEqual(ev.state_at(e, 100, w, lamp)['wheel'], 35)
        self.assertEqual([ev.hand_weight(e, f) for f in (0, 17, 30, 100, 300)], [0, 0, 1, 1, 1])
        self.assertLess(ev.hand_weight(e, 312), 1.)

    def test_the_grip_points_turn_with_the_wheel(self):
        import scene_objects as obj
        w = obj.wheel('w', (100, 100), 50, [180], 0)
        self.assertAlmostEqual(obj.grip_points(w)[0][0], 50, delta=.01)
        w['rotation'] = 90
        self.assertAlmostEqual(obj.grip_points(w)[0][1], 50, delta=.01)

    def test_a_wheel_out_of_reach_is_not_placed(self):
        import scene_templates as tpl
        with patch.object(tpl.rig, 'UPPER', .02), patch.object(tpl.rig, 'FORE', .02):
            with self.assertRaises(ValueError):
                tpl.place_wheel((400, 340), [0., 35.], [160., 205.], 74.)

    def test_the_checks_fail_on_a_scene_that_did_not_happen(self):
        import scene_quality as q
        event = dict(frames=dict(contact=30, turn_start=36, release=300), parameters=dict(from_deg=0, to_deg=35), effects=[dict(type='state_change', field='lamp.state', frame=61)])
        frame = lambda n, hands: dict(n=n, wheel=0., lamp='off', lamp_bgr=[90, 90, 90], hands=hands, grips=[(10, 10), (20, 20)], hands_screen=[(5, 5), (6, 6)], caption=(0, 0, 1, 1), contact_rects=[(100, 100, 110, 110)])
        rec = dict(event=event, fps=30, hero_height=450, cut_frame=2, click_onset_s=None, size=(1280, 720), expected_seconds=12,
                   frames=[frame(n, [(60, 60), (20, 20)]) for n in range(0, 360)])
        report = q.verify_turn_control(rec)
        failed = {c['name'] for c in report['checks'] if not c['passed']}
        self.assertFalse(report['passed'])
        self.assertTrue({'hand_on_grip_error_px_vs_hero_height', 'wheel_reaches_target_angle_deg', 'lamp_change_is_visible_in_the_picture', 'sound_at_contact_frames'} <= failed)

    def test_the_pilot_video_passes_every_measurement(self):
        import tempfile
        import scene_templates as tpl
        ffmpeg = Path(sys.executable).with_name('ffmpeg')
        if not ffmpeg.is_file():
            self.skipTest('nincs médiafuttató ffmpeg')
        with tempfile.TemporaryDirectory() as tmp:
            report = tpl.turn_control_pilot(tmp, str(ffmpeg))
            self.assertTrue((Path(tmp) / 'turn_control.mp4').is_file())
        failed = [c['name'] for c in report['checks'] if not c['passed']]
        self.assertEqual(failed, [])
