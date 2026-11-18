import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import stickman_studio as st
import story_animation
from studio import Studio


class Line(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.pid = story_animation.separate(self.s) or story_animation.project(self.s)
        story_animation.install_team(self.s, self.pid)

    def test_deadline_is_the_next_time_that_clock_time_comes(self):
        now = time.mktime((2026, 11, 16, 4, 5, 0, 0, 0, -1))
        self.assertEqual(time.localtime(st.until_today('12:00', now))[2:5], (16, 12, 0))
        self.assertEqual(time.localtime(st.until_today('03:00', now))[2:5], (17, 3, 0))
        with self.assertRaises(ValueError):
            st.until_today('dél')

    def test_it_starts_one_at_a_time_and_stops_at_the_deadline(self):
        with patch.object(self.s, 'enqueue_graph', return_value=dict(run='r1')) as enqueue:
            st.start_batch(self.s, self.pid, time.time() + 8 * 3600, 'long', 10)
            self.assertEqual(enqueue.call_count, 1)
            self.assertIn('[stickman:long:600]', enqueue.call_args[0][2])
            self.assertEqual(st.batch(self.s, self.pid)['runs'], ['r1'])
        line = st.batch(self.s, self.pid)
        line['until'] = time.time() - 1
        st.save_batch(self.s, self.pid, line)
        st.tick_project(self.s, self.pid)
        self.assertFalse(st.batch(self.s, self.pid)['on'])
        self.assertIn('határidő', st.batch(self.s, self.pid)['note'])

    def test_no_new_video_when_it_would_not_finish_in_time(self):
        with patch.object(self.s, 'enqueue_graph', return_value=dict(run='r1')) as enqueue:
            st.start_batch(self.s, self.pid, time.time() + 3600, 'long', 10)    # one hour, an episode needs about 150 min
            self.assertEqual(enqueue.call_count, 0)
        self.assertFalse(st.batch(self.s, self.pid)['on'])
        self.assertIn('nem érne el', st.batch(self.s, self.pid)['note'])

    def test_the_master_pause_holds_it(self):
        import autonomy
        with patch.object(self.s, 'enqueue_graph', return_value=dict(run='r1')) as enqueue:
            autonomy.set_paused(self.s, True)
            st.start_batch(self.s, self.pid, time.time() + 8 * 3600, 'long', 10)
            self.assertEqual(enqueue.call_count, 0)
            self.assertTrue(st.batch(self.s, self.pid)['on'])
        listed = [e for e in autonomy.entries(self.s) if e['id'].startswith('stickman:')]
        self.assertEqual(len(listed), 1)
        autonomy.toggle(self.s, listed[0]['id'], False)
        self.assertFalse(st.batch(self.s, self.pid)['on'])



class Sounds(unittest.TestCase):
    def test_found_then_generated_then_made_in_code(self):
        import tempfile
        from types import SimpleNamespace
        import sfx_generate
        import sfx_library
        with tempfile.TemporaryDirectory() as d:
            s = SimpleNamespace(root=Path(d))
            plan = dict(places=[dict(id='a', look='inside the store')], shots=[
                dict(start=0, end=3, say='A metal shutter slams.', sound='door', sound_what='heavy metal impact', place='a'),
                dict(start=4, end=7, say='The freezers hum.', sound='none', sound_what='freezer humming', place='a'),
                dict(start=8, end=11, say='A seagull cries.', sound='none', sound_what='seagull cry', place='a')])
            files = ['/x/impact-sounds/Audio/impactMetal_heavy_001.ogg']
            def fake_make(s_, job, wanted, budget=900):
                return {w['prompt']: '/made/hum.wav' for w in wanted if 'freezer' in w['what']}
            with patch.object(sfx_library, 'index', return_value=files), patch.object(sfx_generate, 'make', side_effect=fake_make):
                got = st.effects(s, plan, 'run1')
        self.assertEqual(got[0]['file'], files[0])                     # a recording that clearly fits
        self.assertEqual((got[1]['file'], got[1].get('generated')), ('/made/hum.wav', True))
        self.assertEqual(len(got), 2)                                  # nothing fits the gull and no code sound either: silence, not a wrong sound

    def test_the_editor_fixes_only_what_is_wrong(self):
        shots = [dict(say=t, kind='wide') for t in ('You find four bars.', 'You eat one every twelve hours.', 'That lasts four days.', 'First problem. The door.', 'Rations? Zero.')]
        shots[3]['kind'] = 'title'
        fixes = dict(problems=['4 bars at one per 12 hours last 2 days'], fixes=[dict(index=2, say='That lasts two days.')])
        import tempfile
        from types import SimpleNamespace
        outline = dict(mission='m')
        with tempfile.TemporaryDirectory() as d, patch.object(st, 'ask', side_effect=[fixes, dict(fixes=[], problems=[])]):
            st.review_logic(SimpleNamespace(root=Path(d), job_stage=lambda *a: None), dict(id='j', agent='a'), shots, outline)
        self.assertEqual(outline['review']['status'], 'verified')
        self.assertEqual([x['say'] for x in shots], ['You find four bars.', 'You eat one every twelve hours.', 'That lasts two days.', 'First problem. The door.', 'Rations? Zero.'])

    def test_the_prompt_is_a_sound_designer_description(self):
        import sfx_generate
        p = sfx_generate.describe('metal shutter rolling down', 'a big supermarket at night', 4.2)
        self.assertTrue(p.startswith('Metal shutter rolling down, inside a large echoing room'))
        self.assertTrue(p.endswith('Length: 4 seconds'))


if __name__ == '__main__':
    unittest.main()


class Recover(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.pid = story_animation.separate(self.s) or story_animation.project(self.s)
        story_animation.install_team(self.s, self.pid)

    def test_a_stopped_episode_of_the_line_is_resumed_once_before_a_new_one(self):
        import json
        agent = story_animation.agent_ids(self.pid)['render']
        jid = self.s.enqueue(agent, 'render', 'graph', payload=dict(run='old', story_step='render'))
        self.s.db.execute("UPDATE jobs SET status='failed',error='x' WHERE id=?", (jid,))
        self.s.db.commit()
        st.save_batch(self.s, self.pid, dict(on=True, kind='long', minutes=10, until=time.time() + 8 * 3600, runs=['old']))
        with patch.object(self.s, 'enqueue_graph', return_value=dict(run='new')) as enqueue:
            self.assertEqual(st.tick_project(self.s, self.pid), dict(resumed='old'))
            self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?', (jid,)).fetchone()[0], 'queued')
            self.assertEqual(enqueue.call_count, 0)

    def test_an_optional_picture_that_fails_twice_is_left_out(self):
        job = dict(id='j', project=self.pid)
        out = self.s.safe_path(self.pid, 'runs/r/stickman/insert-x.png')
        out.parent.mkdir(parents=True, exist_ok=True)
        with patch('design_studio.flux', side_effect=ValueError('timed out after 900 seconds')) as flux, patch('model_hub.unload'), patch('time.sleep'), patch.object(self.s, 'cancelled', return_value=False):
            st.flux_images(self.s, job, 'r', [(out, 'p', 'tárgy', 1)], (64, 64), optional=True)
            self.assertEqual(flux.call_count, 3)
            with self.assertRaises(ValueError):
                st.flux_images(self.s, job, 'r', [(out, 'p', 'hely', 1)], (64, 64))


class Resume(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.pid = story_animation.separate(self.s) or story_animation.project(self.s)
        story_animation.install_team(self.s, self.pid)

    def test_a_timed_out_part_is_asked_again_and_finished_parts_are_kept(self):
        import json
        import stickman_rig as rig
        job = dict(id='j1', agent=story_animation.agent_ids(self.pid)['script'], project=self.pid, payload=json.dumps(dict(run='run1', story_step='script')))
        outline = dict(kind='long', sections=[dict(name='opening', words=20), dict(name='chapter 1', words=20, chapter=0), dict(name='ending', words=20)],
                       places=[dict(id='a', name='A', look='x' * 20)], chapters=[dict(title='The door', label='PROBLEM 1', say='First problem. The door.')],
                       title='T', hook='h', question='q', premise='p', goal='g', counter='', running_line='', support=dict(needed=False), low_point='l', ending='e')
        cfg = dict(main=rig.MAIN, support=rig.SUPPORT)
        part = dict(shots=[dict(say='You open the door and you walk into the dark hall slowly now.', kind='wide', place='a', you=dict(action='walk', face='neutral')),
                           dict(say='The lights hum above you and the floor is cold under your feet.', kind='close', place='a', you=dict(action='idle', face='worried'))])
        calls = []

        def answer(*a, **k):
            calls.append(1)
            if 'You are the story editor' in a[2]:
                return dict(fixes=[], problems=[])
            if len(calls) == 2:
                raise ValueError('A modellhívás időkerete elfogyott; a mentett feladat később folytatható.')
            if len(calls) == 4:
                raise ValueError('the step stops here')
            lines = [('You open the door and you walk into the dark hall slowly now.', 'The lights hum above you and the floor is cold under your feet.'),
                     ('A copper pipe drips beside a rusted valve wheel near the stairs.', 'You twist that wheel until steam stops leaking from every joint.'),
                     ('Rain hammers against tall windows while sirens fade far away.', 'You finally breathe out, because morning light reaches the city.')][len(calls) % 3]
            return dict(shots=[dict(x, say=line) for x, line in zip(part['shots'], lines)])   # every part tells something new
        with patch.object(st, 'ask', side_effect=answer), patch('time.sleep'), patch.object(self.s, 'cancelled', return_value=False):
            with self.assertRaises(ValueError):
                st.write_sections(self.s, job, cfg, outline)
        folder = self.s.safe_path(self.pid, 'runs/run1/stickman/sections')
        self.assertEqual(sorted(p.name for p in folder.glob('part-*.json')), ['part-0.json', 'part-1.json'])
        calls.clear()
        calls.extend([1, 1, 1, 1])      # past the scripted faults
        with patch.object(st, 'ask', side_effect=answer) as model:
            shots = st.write_sections(self.s, job, cfg, outline)
        self.assertEqual(model.call_count, 2)          # only the ending was written again, then the editor read it once
        self.assertEqual(shots[2]['kind'], 'title')


class Length(unittest.TestCase):
    def test_a_short_script_gets_its_thinnest_part_written_longer(self):
        import contextlib
        places = [dict(id='a', name='A', look='x' * 20)]
        outline = dict(sections=[dict(name='opening', words=40), dict(name='ending', words=40)], places=places, chapters=[])
        short = [st.clean_shot(dict(say='You wake up.', kind='wide', place='a'), places, '')]
        fine = [st.clean_shot(dict(say=' '.join(['word'] * 38) + '.', kind='wide', place='a'), places, '')]
        parts = [dict(name='opening', words=40, shots=short), dict(name='ending', words=40, shots=fine)]
        longer = dict(shots=[dict(say='You wake up on a cold steel floor and the alarm is ringing in the dark.', kind='wide', place='a'),
                             dict(say='The clock on the wall says four in the morning and the door is locked from outside.', kind='close', place='a')])
        job = dict(id='j', project='p')

        class S:
            root = Path('/tmp')
            def job_stage(self, *a): pass
        with patch.object(st, 'ask', return_value=longer) as model, patch('inference_gate.lease', return_value=contextlib.nullcontext()):
            shots = st.top_up(S(), job, {}, outline, short + fine, parts, 'write')
        self.assertGreaterEqual(model.call_count, 1)
        self.assertTrue(shots[0]['say'].startswith('You wake up on a cold steel floor'))
        self.assertGreater(st.words_of(shots), st.words_of(short + fine))

class Counted(Line):
    def finish(self, run):
        """Mark the episode `run` as fully made (no job of it is running, its render is done)."""
        self.s.db.execute("UPDATE jobs SET status='done' WHERE project=? AND json_extract(payload,'$.run')=?", (self.pid, run))

    def test_count_without_deadline_starts_that_many_one_after_another(self):
        runs = iter(['r1', 'r2', 'r3'])
        with patch.object(self.s, 'enqueue_graph', side_effect=lambda *a, **k: dict(run=next(runs))) as enqueue:
            st.start_batch(self.s, self.pid, None, 'short', 50, count=3)
            self.assertEqual(enqueue.call_count, 1)
            line = st.batch(self.s, self.pid)
            self.assertTrue(line['on'] and not line['deadline'] and line['count'] == 3)
            for _ in range(2):
                st.tick_project(self.s, self.pid)          # nothing running (no jobs were really queued): next one starts
            self.assertEqual(enqueue.call_count, 3)
            st.tick_project(self.s, self.pid)
            self.assertEqual(enqueue.call_count, 3)
        line = st.batch(self.s, self.pid)
        self.assertFalse(line['on'])
        self.assertIn('/ 3', line['note'])

    def test_a_mixed_line_alternates_short_and_long(self):
        runs = iter(['r1', 'r2'])
        with patch.object(self.s, 'enqueue_graph', side_effect=lambda *a, **k: dict(run=next(runs))) as enqueue:
            st.start_batch(self.s, self.pid, None, 'mix', 0, count=2)
            st.tick_project(self.s, self.pid)
        briefs = [c[0][2] for c in enqueue.call_args_list]
        self.assertIn('[stickman:short:', briefs[0])
        self.assertIn('[stickman:long:', briefs[1])

    def test_it_needs_a_deadline_or_a_count(self):
        with self.assertRaises(ValueError):
            st.start_batch(self.s, self.pid, None, 'long', 10, count=0)

    def test_an_active_line_keeps_the_mac_awake(self):
        with patch.object(self.s, 'enqueue_graph', return_value=dict(run='r1')):
            self.assertFalse(st.batch_active(self.s))
            st.start_batch(self.s, self.pid, None, 'short', 50, count=2)
            self.assertTrue(st.batch_active(self.s))


class BusyAnswer(Line):
    def test_a_running_video_is_named_and_can_be_stopped(self):
        import json as _json
        self.assertEqual(st.busy_text(self.s, self.pid), '')
        agent = self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1', (self.pid,))[0]['id']
        jid = self.s.enqueue(agent, 'x', 'graph', payload=dict(story_step='script', run='r'))
        self.s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?", (time.time() - 600, jid))
        self.s.db.commit()
        text = st.busy_text(self.s, self.pid)
        self.assertIn('narráció és jelenetek', text)
        self.assertIn('10 perce', text)
        self.assertEqual(st.snapshot(self.s, self.pid)['running'][0]['id'], jid)
        with self.assertRaises(ValueError) as ctx:
            st.start(self.s, self.pid, dict(kind='short'))
        self.assertIn('leállítsd', str(ctx.exception).replace('állítsd le', 'leállítsd')) if False else self.assertIn('Már készül egy videó', str(ctx.exception))
