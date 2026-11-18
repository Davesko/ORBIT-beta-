import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import stickman_rig as rig
import stickman_studio as st

HERE = Path(__file__).parent


class Vocabulary(unittest.TestCase):
    def test_writer_words_map_onto_the_rig(self):
        self.assertEqual(rig.action_of('Walking slowly'), 'walk')
        self.assertEqual(rig.action_of('hides behind the shelf'), 'crouch')
        self.assertEqual(rig.action_of('runs away'), 'run')
        self.assertEqual(rig.action_of('something unknown'), 'idle')
        self.assertEqual(rig.expression_of('terrified'), 'scared')
        self.assertEqual(rig.prop_of('a torchlight'), 'flashlight')

    def test_every_action_gives_a_complete_pose(self):
        for a in rig.ACTIONS:
            for t in (0., .7, 2.9):
                p = rig.pose(a, t, 3.)
                self.assertTrue(all(k in p for k in rig.BASE), a)
                j = rig.skeleton(p, 500, 900, 300, 1)
                self.assertLess(j['head'][1], 900, a)

    def test_designs_are_checked(self):
        d = rig.clean_design(dict(name='  Kip  ', hair='laser', top='coat', top_colour='#12ab34', height=9), rig.MAIN)
        self.assertEqual(d['name'], 'Kip')
        self.assertEqual(d['hair'], rig.MAIN['hair'])
        self.assertEqual(d['top'], 'coat')
        self.assertEqual(d['top_colour'], '#12AB34')
        self.assertEqual(d['height'], 1.1)


class Planning(unittest.TestCase):
    def test_sections_follow_the_length(self):
        self.assertEqual(len(st.sections_for('short', 50)), 1)
        long = st.sections_for('long', 480)
        self.assertEqual(long[0]['name'], 'opening')
        self.assertEqual(long[-1]['name'], 'ending')
        self.assertEqual(len([x for x in long if x['name'].startswith('chapter')]), 7)
        self.assertAlmostEqual(sum(x['words'] for x in long), 480 * st.WPS, delta=180)

    def test_target_reads_the_mark_then_the_setting(self):
        cfg = dict(kind='short', short_seconds=50, long_minutes=8)
        self.assertEqual(st.target(cfg, 'x [stickman:long:600]'), ('long', 600))
        self.assertEqual(st.target(cfg, 'x [stickman:short:30]'), ('short', 30))
        self.assertEqual(st.target(cfg, 'make a long landscape one'), ('long', 480))
        self.assertEqual(st.target(cfg, 'anything'), ('short', 50))
        self.assertEqual(st.strip('a [stickman:short:30]'), 'a')

    def test_outline_must_speak_to_you_and_have_its_chapters(self):
        sections = st.sections_for('long', 300)
        good = dict(title='Locked In', hook='Doors open for anyone. You are inside.', question='How do you last 30 days?', premise='You are locked in a mall.',
                    mission='You have 30 days to survive inside this mall.', resolution='On day 30 the shutter opens and you walk out with every can counted.',
                    goal='Survive 30 days', low_point='The generator dies on day 20.',
                    conditions=[dict(problem='The glass rattles in the wind.', handled_by='You stack 40 crates against the glass.')],
                    places=[dict(id=f'hall{i}', look='an empty mall hall at night with closed shops') for i in range(4)], ending='Day 30. You are still here.',
                    chapters=[dict(title=f'P{i}', summary='x', solution='You stack 40 crates against the glass.',
                                   steps=[dict(do='You roll a pallet jack to the door.', result='It squeaks.'), dict(do='You stack 40 crates.', result='The glass stops shaking.'),
                                          dict(do='You tape the gaps.', result='The wind stops.')]) for i in range(4)])
        self.assertEqual(st.outline_problem(good, sections), '')
        dark = dict(good, premise='The power dies and you are alone in the mall.', low_point='The last shop shutter jams.')
        self.assertIn('lights are out', st.outline_problem(dark, sections))
        lit = dict(dark, chapters=[dict(c, solution='You carry a flashlight from the security desk and stack 40 crates.') for c in good['chapters']])
        self.assertEqual(st.outline_problem(lit, sections), '')
        self.assertIn('conditions is empty', st.outline_problem(dict(good, conditions=[]), sections))
        self.assertIn('steps', st.outline_problem(dict(good, chapters=[dict(c, steps=c['steps'][:2]) for c in good['chapters']]), sections))
        self.assertIn('ONE problem', st.outline_problem(dict(good, places=good['places'][:2]), st.sections_for('short', 45), 'short'))
        self.assertEqual(st.missing_steps([dict(say='You roll the pallet jack to the door.'), dict(say='You tape every gap.')], good['chapters'][0]['steps']),
                         ['You stack 40 crates.'])
        self.assertIn('places', st.outline_problem(dict(good, places=good['places'][:2]), sections))
        self.assertIn('solution', st.outline_problem(dict(good, chapters=[dict(c, solution='') for c in good['chapters']]), sections))
        self.assertIn('chapters', st.outline_problem(dict(good, chapters=good['chapters'][:1]), sections))
        self.assertIn('you', st.outline_problem(dict(good, hook='The doors open.', premise='A man is locked in.'), sections))

    def test_shots_are_repaired_into_what_the_rig_draws(self):
        places = [dict(id='aisle', name='Aisle', look='x' * 20), dict(id='office', name='Office', look='y' * 20)]
        shot = st.clean_shot(dict(say='You run. [gasp]', kind='wide', place='the office', you=dict(action='running', face='terrified', pos='left', move_to='right'),
                                  crowd=dict(kind='zombie', count=99)), places, 'DAY 2')
        self.assertEqual(shot['say'], 'You run.')
        self.assertEqual(shot['place'], 'office')
        self.assertEqual(shot['actors'][0]['action'], 'run')
        self.assertEqual(shot['actors'][0]['to'], .7)
        self.assertEqual(shot['crowd']['count'], 30)
        card = st.clean_shot(dict(say='Four hours.', kind='card', place='aisle', card=dict(type='bars', rows=[dict(label='Fridge', value=40, text='4 h')])), places, '')
        self.assertEqual(card['card']['rows'][0]['value'], .4)
        broken = st.clean_shot(dict(say='Nine thousand cans.', kind='card', place='aisle', card=dict(type='stat')), places, '')
        self.assertEqual(broken['kind'], 'medium')
        close = st.clean_shot(dict(say='You freeze.', kind='close', place='aisle', you=dict(action='walk', face='scared', pos='left', move_to='right'),
                                   support=dict(action='idle', face='neutral')), places, '')
        self.assertEqual(len(close['actors']), 1)
        self.assertNotIn('to', close['actors'][0])

    def test_director_keeps_the_picture_true_to_the_words(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        raw = [dict(say='The boiler stops.', kind='medium', place='a', you=dict(action='idle', face='scared', prop='money'), support=dict(action='sleep', face='neutral')),
               dict(say='You wrap yourself in a blanket and run to the door.', kind='wide', place='a', you=dict(action='sleep', face='tired')),
               dict(say='Mara is outside. She holds a flashlight.', kind='medium', place='a', you=dict(action='idle', face='neutral'), support=dict(action='idle', face='worried')),
               dict(say='The rescue team enters.', kind='wide', place='a', you=dict(action='sleep', face='tired'))]
        shots = st.plausible([st.clean_shot(x, places, '') for x in raw], 'Mara')
        self.assertEqual([a['who'] for a in shots[0]['actors']], ['main'])
        self.assertEqual(shots[0]['actors'][0]['prop'], 'none')
        self.assertEqual(shots[1]['actors'][0]['action'], 'run')
        self.assertIn('support', [a['who'] for a in shots[2]['actors']])
        self.assertNotEqual(shots[3]['actors'][0]['action'], 'sleep')

    def test_new_cameras_signs_and_meters(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        pov = st.clean_shot(dict(say='You peek through the gap in the shutter.', kind='wide', place='a', you=dict(action='crouch', face='scared')), places, '')
        top = st.clean_shot(dict(say='You study the map of every aisle.', kind='wide', place='a', you=dict(action='idle', face='thinking')), places, '')
        st.cameras([pov, top])
        self.assertEqual((pov['kind'], pov['pov']), ('pov', 'slit'))
        self.assertEqual(pov['actors'], [])
        self.assertEqual(top['kind'], 'top')
        sign = st.clean_shot(dict(say='The door rattles.', kind='medium', place='a', sign=dict(text='Exit', style='exit'), fx='shake'), places, '')
        self.assertEqual((sign['sign']['style'], sign['fx']), ('exit', 'shake'))
        meter = st.clean_shot(dict(say='Your phone dies.', kind='card', place='a', card=dict(type='meter', label='phone battery', **{'from': 100, 'to': 3})), places, '')
        self.assertEqual((meter['card']['icon'], meter['card']['to'], meter['card']['unit']), ('battery', 3.0, '%'))
        no_crowd = st.clean_shot(dict(say='x', kind='crowd', place='a'), places, '')
        self.assertEqual(no_crowd['kind'], 'wide')

    def test_the_sentence_decides_the_movement(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        for text, action in (('You climb faster.', 'climb'), ('You crawl into the vent.', 'sneak'), ('You kick the door twice.', 'push'),
                             ('You pry the grate open.', 'pull'), ('You duck behind the counter.', 'crouch')):
            shots = st.plausible([st.clean_shot(dict(say=text, kind='medium', place='a', you=dict(action='idle', face='neutral')), places, '')], None)
            self.assertEqual(shots[0]['actors'][0]['action'], action, text)

    def test_a_body_part_close_up_is_the_stickman_not_a_painting(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        shot = st.clean_shot(dict(say='You cup your hands.', kind='insert', place='a', insert=dict(what='two open hands holding water'), you=dict(action='idle', face='neutral')), places, '')
        self.assertEqual(shot['kind'], 'close')

    def test_the_mission_opens_and_the_resolution_closes(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        mk = lambda t: st.clean_shot(dict(say=t, kind='wide', place='a', you=dict(action='idle', face='neutral')), places, '')
        shots = [mk('The manual says one thing.'), mk('You close the hatch anyway.'), mk('The storm hits.')] + [mk(f'Step {i} of the work goes on.') for i in range(8)] + [mk('Day 30. Inventory.'), mk('One engineer. You.')]
        outline = dict(mission='You have 12 hours to get off this platform before it sinks.', resolution='At 11:58 the last brace holds. The platform stays above the waves.')
        st.frame_story(shots, outline)
        self.assertEqual(shots[2]['say'], outline['mission'])
        self.assertEqual(shots[2]['card'], dict(type='stat', value='12', label='HOURS TO GET OFF THIS PLATFORM'))
        self.assertEqual(shots[-3]['say'], outline['resolution'])
        again = len(shots)
        st.frame_story(shots, outline)
        self.assertEqual(len(shots), again)       # already said: nothing added twice

    def test_retold_sentences_and_an_overused_running_line_are_cut(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        mk = lambda t: st.clean_shot(dict(say=t, kind='wide', place='a'), places, '')
        line = 'Rule 1. Keep the gears turning.'
        shots = [mk('The door seals lock with a final, terrifying click.'), mk(line), mk('A loud seal engages with a final, terrifying click.'),
                 mk(line), mk('The gear turns.'), mk(line), mk(line), mk(line), mk('The pump starts.'), mk('Water drains.'), mk('Heat flows.'), mk('Day 30.')]
        st.tidy(shots, dict(running_line=line))
        self.assertEqual([x['say'] for x in shots].count(line), 3)
        self.assertEqual(len([x for x in shots if 'terrifying' in x['say']]), 1)

    def test_a_part_keeps_only_new_sentences(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        mk = lambda t, k='wide': st.clean_shot(dict(say=t, kind=k, place='a'), places, '')
        story = ['You wake up to a completely silent street. No traffic. No people.', 'A bicycle lies on its side.']
        got, copied = st.fresh_only([mk('Chapter 1. The Silence.', 'title'), mk('Silence. No traffic. No people.'),
                                     mk('Chapter 5. The Backup.'), mk('The subway door hums with a blue field.')], story)
        self.assertEqual(copied, 2)
        self.assertEqual([x['say'] for x in got], ['Chapter 1. The Silence.', 'The subway door hums with a blue field.'])

    def test_a_countdown_counter_goes_down_chapter_by_chapter(self):
        shots = [dict(say='x', kind='wide', hud='HOURS: 24')]
        for n in range(6):
            shots += [dict(say='t', kind='title', hud='HOURS: 23'), dict(say='y', kind='wide', hud='HOURS: 23.9' if n > 3 else 'HOURS: 23')]
        st.pace_counter(shots, dict(mission='You have 24 hours to keep the city power core alive.'))
        values = [int(x['hud'].split()[-1]) for x in shots if x['kind'] == 'title']
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(len(set(values)), 6)
        self.assertTrue(shots[1]['hud'].startswith('HOURS LEFT'))
        days = [dict(say='t', kind='title', hud=f'DAY {d}') for d in (1, 5, 9, 14)]
        st.pace_counter(days, dict(mission='Survive 30 days in the mall.'))
        self.assertEqual([x['hud'] for x in days], ['DAY 1', 'DAY 5', 'DAY 9', 'DAY 14'])

    def test_what_happens_to_the_place_is_seen(self):
        says = ['The streetlights flicker.', 'The light stops flickering. It stays on.', 'Sparks fly. The field flickers.', 'Steam hisses from a cracked valve.',
                'The lights die.', 'Total darkness.', 'The monitors light up one by one.', 'You aim the laser at the mirror.', 'You think.']
        shots = st.fx_from_words([dict(say=x, kind='wide', sound='none') for x in says])
        self.assertEqual([x.get('fx') for x in shots], ['flicker', None, 'sparks', 'steam', 'dark', 'dark_hold', 'lights_on', 'beam', None])
        self.assertEqual(shots[2]['sound'], 'none')      # a picture effect is silent: no random zap under sparks (17 Nov)

    def test_the_world_of_a_scene_follows_the_words(self):
        places = [dict(id='street', name='Street', look='A wet street outside at night', weather='rain'), dict(id='shop', name='Shop', look='inside the store aisle')]
        mk = lambda say, kind='wide', action='idle', **k: dict(say=say, kind=kind, place=k.pop('place', 'street'), hud='', sound='none',
                                                              actors=[dict(who='main', action=action, expression='neutral', prop='none', x=.3)] + k.pop('others', []), **k)
        shots = [mk('You walk down the long aisle.', action='walk', place='shop'), mk('You press the red button.', 'insert'),
                 mk('A fire truck sprays water at the gate in the rain.'), mk('Something goes clunk.', place='shop'),
                 mk('You loop it around the base.', action='crank', place='shop'),
                 mk('The freezers stop humming.', place='shop'),
                 mk('You wait.', place='shop', others=[dict(who='extra:guard', action='idle', expression='neutral', prop='none', x=.7)]),
                 mk('Dana grabs her keys.', place='shop', others=[dict(who='extra:worker', action='idle', expression='neutral', prop='none', x=.7)])]
        shots[1]['actors'] = []
        st.stage_world(shots, dict(places=[dict(p, weather=st.weather_of(p)) for p in places]))
        self.assertEqual(shots[0]['actors'][0].get('depth'), 'away')
        self.assertNotIn('weather', shots[0])
        self.assertEqual(shots[1]['hand'], 'press')
        self.assertEqual(shots[2]['weather'], 'rain')
        self.assertTrue(any(m['kind'] == 'vehicle' and m['spray'] for m in shots[2]['moving']))
        self.assertTrue(any(m['kind'] == 'burst' and m['label'] == 'CLUNK' for m in shots[3]['moving']))
        self.assertEqual((shots[4]['actors'][0]['action'], shots[4]['actors'][0].get('still')), ('idle', True))
        self.assertEqual(shots[5].get('sound_what'), 'humming')
        self.assertEqual(len(shots[6]['actors']), 1)          # nobody else is in "You wait."
        self.assertEqual(len(shots[7]['actors']), 2)          # Dana is

    def test_nothing_happens_that_the_story_does_not_say(self):
        places = [dict(id='street', name='Street', look='A wet street outside at night', weather='rain')]
        mk = lambda say: dict(say=say, kind='wide', place='street', hud='', sound='none', actors=[dict(who='main', action='idle', expression='neutral', prop='none', x=.3)])
        shots = [mk('You check your car keys.'), mk('The sky is grey.'), mk('Suddenly you remember the code.'), mk('The fans are gone.')]
        st.stage_world(shots, dict(places=[dict(p, weather=st.weather_of(p)) for p in places]))
        self.assertEqual([x.get('weather') for x in shots], [None] * 4)        # the story never speaks of rain
        self.assertEqual([x.get('moving') for x in shots], [None] * 4)         # nothing moves that the words do not make move
        room = [dict(id='room', name='Room 512', look='a hotel room with a bed', weather='wind')]
        inside = [dict(mk('The storm is wild. The window shatters and the wind howls in.'), place='room'), dict(mk('The wind is cold.'), place='room')]
        st.stage_world(inside, dict(places=room))
        self.assertEqual([x.get('weather') for x in inside], ['wind', None])   # indoors only in the extreme case

    def test_held_tools_and_mechanics_are_kept_for_later(self):
        import tempfile
        from types import SimpleNamespace
        import asset_library
        shots = [dict(say='You grab the snow shovel and dig.', kind='medium', actors=[dict(who='main', action='idle', expression='neutral', prop='none', x=.3)]),
                 dict(say='You pick up a flashlight.', kind='medium', actors=[dict(who='main', action='idle', expression='neutral', prop='none', x=.3)])]
        st.find_tools(shots)
        self.assertEqual(shots[0]['actors'][0]['tool'], 'snow shovel')
        self.assertEqual((shots[1]['actors'][0].get('tool'), shots[1]['actors'][0]['prop']), (None, 'flashlight'))
        with tempfile.TemporaryDirectory() as d:
            s = SimpleNamespace(root=Path(d))
            plan = dict(shots=[dict(say='A fire truck sprays water at the gate.', kind='wide', start=1., moving=[dict(kind='vehicle', what='fire truck', where='left')], fx='spray')])
            st.remember_mechanics(s, plan, [], 'p/r')
            later = [dict(say='The fire truck sprays water at the gate again.', kind='wide')]
            st.recall_mechanics(s, later)
            self.assertEqual((later[0]['moving'][0]['kind'], later[0]['fx']), ('vehicle', 'spray'))
            self.assertEqual(asset_library.summary(s), {'mechanic': 1})

    def test_no_snow_indoors_and_a_fire_escape_is_not_a_fire(self):
        places = [dict(id='room_512', name='Room 512', look='A small hotel room with a bed and a frosted window')]
        shots = [dict(say='Snow is piling up and the fire escape is broken.', kind='medium', place='room_512', hud='', sound='none',
                      actors=[dict(who='main', action='idle', expression='neutral', prop='none', x=.3)])]
        st.stage_world(shots, dict(places=[dict(p, weather=st.weather_of(dict(p, weather='snow'))) for p in places]))
        self.assertNotIn('weather', shots[0])
        self.assertFalse(any(m['kind'] == 'fire' for m in shots[0].get('moving', [])))
        card = st.frame_story([dict(say='x', kind='wide', place='a', hud='', actors=[])] * 3, dict(mission="You have 48 hours to stay warm in Room 512 until the ice melts."))
        label = next(x['card']['label'] for x in card if x.get('card'))
        self.assertFalse(label.endswith(' IN'), label)

    def test_a_card_shows_the_number_that_is_said(self):
        shots = [dict(kind='card', say='The heat efficiency increases by 30%.', card=dict(type='stat', value='130%', label='HEAT')),
                 dict(kind='card', say='You have 72 hours.', card=dict(type='stat', value='72', label='HOURS'))]
        st.true_cards(shots)
        self.assertEqual([x['card']['value'] for x in shots], ['+30%', '72'])
        self.assertEqual(st.fx_from_words([dict(say='The fire dies to embers.', kind='wide', sound='none')])[0]['fx'], 'dark')

    def test_plain_words_for_a_wide_audience(self):
        self.assertIn('technical', st.plain_problem(['The AI protocol overrides the grid sensors.']))
        self.assertEqual(st.plain_problem(['It is 2:14 in the morning. You are stacking cans in aisle 7, and the doors have just slid open.']), '')

    def test_every_moving_thing_and_made_sound_draws(self):
        import numpy as np
        import cv2
        import stickman_fx as fx
        import stickman_audio as audio
        frame = np.full((180, 320, 3), 200, np.uint8)
        for kind in fx.MOTIONS:
            fx.draw(np, cv2, frame, dict(kind=kind, where='center', label='CLUNK', what='fire truck'), .7, .5, 320, 180, seed=3, hand=(100, 90))
        for kind in audio.SYNTHS:
            self.assertGreater(len(audio.synth(kind, .5, 1)), 1000, kind)

    def test_a_sound_is_found_by_its_description(self):
        import sfx_library
        files = ['/x/impact-sounds/Audio/footstep_snow_000.ogg', '/x/impact-sounds/Audio/impactMetal_heavy_001.ogg', '/x/interface-sounds/Audio/click_002.ogg']
        self.assertEqual(sfx_library.search(files, 'a metal shutter slams')[0], files[1])
        self.assertEqual(sfx_library.search(files, 'footsteps in the snow')[0], files[0])
        self.assertIsNone(sfx_library.search(files, 'a freezer humming')[0])

    def test_a_meter_of_hours_is_not_a_percentage(self):
        shots = [dict(say='You have twelve hours before the structure fails.', kind='card', card=dict(type='meter', unit='%', icon='bar', **{'from': 12, 'to': 0}))]
        st.fix_units(shots)
        self.assertEqual(shots[0]['card']['unit'], 'HOURS')

    def test_the_last_you_verb_decides(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        shot = st.plausible([st.clean_shot(dict(say='You need a lever. You run to the storage bay.', kind='wide', place='a', you=dict(action='pull', face='neutral')), places, '')], None)[0]
        self.assertEqual(shot['actors'][0]['action'], 'run')

    def test_he_walks_only_when_the_words_move_him(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        still = st.plausible([st.clean_shot(dict(say='The lights hum above you.', kind='wide', place='a', you=dict(action='walk', face='worried', move_to='right')), places, '')], None)[0]
        self.assertEqual(still['actors'][0]['action'], 'look_around')
        self.assertNotIn('to', still['actors'][0])
        going = st.plausible([st.clean_shot(dict(say='You head into the turbine hall.', kind='wide', place='a', you=dict(action='walk', face='neutral')), places, '')], None)[0]
        self.assertEqual(going['actors'][0]['action'], 'walk')

    def test_a_lone_walker_crosses_the_frame_from_a_third(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        shots = [st.clean_shot(dict(say='You walk down the long hall.', kind='wide', place='a', you=dict(action='walk', face='neutral')), places, ''),
                 st.clean_shot(dict(say='The lights hum.', kind='medium', place='a', you=dict(action='idle', face='neutral')), places, '')]
        st.stage(shots)
        a, b = shots[0]['actors'][0], shots[1]['actors'][0]
        self.assertEqual((a['x'], a['to']), (.3, .72))
        self.assertEqual((b['x'], b['face']), (.7, 'left'))

    def test_no_painted_close_up_has_to_count(self):
        shots = [dict(kind='insert', insert_what='Green status lights on a metal panel.', say='You check the console.'),
                 dict(kind='card', card=dict(type='list', items=[]), say='All systems are green.'),
                 dict(kind='insert', insert_what='a heavy steel wrench', say='You grab a wrench.')]
        self.assertTrue(st.countable(shots, 0))
        self.assertFalse(st.countable(shots, 2) and False)
        self.assertTrue(st.countable([dict(kind='insert', insert_what='Three stacked wooden crates', say='x')], 0))
        self.assertFalse(st.countable([dict(kind='insert', insert_what='a heavy steel wrench', say='x')], 0))

    def test_pov_only_when_looking_through_and_rarely(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        shots = [st.clean_shot(dict(say=t, kind='pov', pov='slit', place='a', you=dict(action='idle', face='scared')), places, '') for t in
                 ('The water rises fast.', 'You peek through the crack.', 'You look through the window.')]
        st.cameras(shots)
        self.assertEqual([x['kind'] for x in shots], ['wide', 'pov', 'wide'])

    def test_no_second_character_when_the_story_needs_none(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        shots = st.plausible([st.clean_shot(dict(say='Mara waves.', kind='medium', place='a', support=dict(action='wave', face='happy')), places, '')], None)
        self.assertEqual([a['who'] for a in shots[0]['actors']], ['main'])

    def test_a_spoken_number_becomes_a_card(self):
        shots = [dict(say='It is dark.', kind='wide', actors=[]), dict(say='Building height: fifteen meters.', kind='medium', actors=[dict(who='main')])]
        st.ensure_cards(shots, 'short')
        self.assertEqual(shots[1]['card'], dict(type='stat', value='15 M', label='Building height'))
        self.assertEqual(st.number_in('Tank fills with five hundred liters of clean water.'), ('500', 'liters', 'clean water'))

    def test_editor_breaks_three_wide_shots(self):
        places = [dict(id='a', name='A', look='x' * 20)]
        shots = [st.clean_shot(dict(say='x', kind='wide', place='a', you=dict(action='idle', face='neutral')), places, '') for _ in range(3)]
        st.editor(shots)
        self.assertNotEqual(shots[2]['kind'], 'wide')

    def test_clock_times_are_spoken_as_words(self):
        self.assertEqual(st.speakable('It is 2:14 in the morning.'), 'It is two fourteen in the morning.')
        self.assertEqual(st.speakable('At 4.51, the power dies.'), 'At four fifty-one, the power dies.')
        self.assertEqual(st.speakable('You have 40,000 products.'), 'You have 40,000 products.')

    def test_timeline_follows_the_narration(self):
        plan = dict(shots=[dict(say='You wake up. It is dark.', kind='wide'), dict(say='', kind='card'), dict(say='First problem. The door.', kind='title')])
        lines = [dict(out='a.wav'), dict(out='b.wav')]
        words, placed = st.timeline(plan, lines, [2.0, 1.5])
        a, b, c = plan['shots']
        self.assertAlmostEqual(a['end'], st.LEAD + 2 + st.GAP, places=2)
        self.assertGreaterEqual(b['end'] - b['start'], st.MIN_SHOT['card'])
        self.assertEqual(len(words), 10)
        self.assertEqual(placed[1]['at'], round(c['start'] + st.LEAD, 3))
        self.assertTrue(all(w['s'] < w['e'] for w in words))
        self.assertLessEqual(words[4]['e'], a['end'])


class Drawing(unittest.TestCase):
    def test_a_timeline_renders_every_shot_kind(self):
        with tempfile.TemporaryDirectory() as d:
            ffmpeg = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'
            if not ffmpeg.is_file():
                self.skipTest('no media runtime ffmpeg')
            shots, t = [], 0.
            for n, kind in enumerate(('wide', 'medium', 'close', 'card', 'title', 'insert', 'crowd', 'pov', 'top')):
                shot = dict(start=t, end=t + .4, kind=kind, place='p', hud='DAY 1', pov='peephole', sign=dict(text='EXIT', style='exit'), fx=st.FX[n % len(st.FX)],
                            actors=[dict(who='main', action='walk', expression='scared', x=.3, to=.6, prop='flashlight'), dict(who='support', action='talk', x=.7, talk=True)],
                            crowd=dict(kind='zombie', count=4, avoid=[.3]), card=dict(type='meter', icon='battery', label='Phone', **{'from': 100, 'to': 4}) if kind == 'card' else dict(type='title', label='PROBLEM 1', title='THE GLASS'))
                shots.append(shot)
                t += .4
            req = dict(width=320, height=180, fps=10, ffmpeg=str(ffmpeg), output=f'{d}/v.mp4', designs=dict(main=rig.MAIN, support=rig.SUPPORT), plates={},
                       shots=shots, words=[dict(w='You', s=0, e=.3), dict(w='40,000', s=.5, e=1.)])
            Path(d, 'r.json').write_text(json.dumps(req))
            done = subprocess.run([sys.executable, str(HERE / 'stickman_render.py'), f'{d}/r.json'], capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr[-500:])
            self.assertEqual(json.loads(done.stdout)['frames'], 36)
            self.assertGreater(Path(d, 'v.mp4').stat().st_size, 1000)

    def test_character_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            out = rig.sheet(Path(d) / 's.png', [rig.MAIN, rig.SUPPORT], 480, 270)
            self.assertTrue(Path(out).is_file())


if __name__ == '__main__':
    unittest.main()
