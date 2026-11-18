import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio import Studio
from autonomous import start, role_agents, run_step

FFMPEG = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'


def transcript(words, db=None):
    t = dict(segments=[dict(start=words[0][1], end=words[-1][2], text=' '.join(w[0] for w in words), words=[dict(word=w, start=a, end=b) for w, a, b in words])])
    if db is not None:
        t['audio_context'] = dict(loudness=dict(step=.5, db=db))
    return t


class SoundLibraryTests(unittest.TestCase):
    def test_every_preset_is_allowed_everywhere(self):
        import sfx
        import editorial_schemas
        self.assertIn('boom', sfx.CHOICES)
        self.assertEqual(sfx.CHOICES[0], 'none')
        self.assertIn("__import__('sfx').CHOICES", Path(editorial_schemas.__file__).read_text())
        for name in sfx.NAMES:
            chain = sfx.filter_for(name, 1.25, 'x')
            self.assertIn('adelay=1250|1250[x]', chain)
            self.assertGreater(sfx.seconds(name), 0)
        self.assertEqual(sfx.latest_start('riser', 1.0), 0)

    @unittest.skipUnless(FFMPEG.is_file(), 'ffmpeg runtime missing')
    def test_every_preset_renders_audible_audio(self):
        import sfx
        for name in sfx.NAMES:
            chain = sfx.filter_for(name, 0, 'out').rsplit('[', 1)[0]
            out = subprocess.run([str(FFMPEG), '-hide_banner', '-filter_complex', chain + ',volumedetect', '-f', 'null', '-'], capture_output=True, text=True, timeout=30)
            self.assertEqual(out.returncode, 0, name + out.stderr[-300:])
            level = float(out.stderr.split('max_volume:')[1].split('dB')[0])
            self.assertGreater(level, -40, name)
            self.assertLess(level, -3, name)


class HumorTests(unittest.TestCase):
    def test_laughter_pause_turn_and_reaction_are_measured(self):
        from comedy import humor_cues
        words = [('Azt', 0, .3), ('hittem', .3, .6), ('nyertünk,', .6, 1.0), ('de', 1.1, 1.3), ('aztán', 1.3, 1.6), ('kiderült...', 1.7, 2.2), ('pizza', 3.0, 3.4), ('volt', 3.4, 3.8), ('haha', 4.2, 4.6)]
        t = transcript(words, db=[-30] * 8 + [-14] * 4 + [-30] * 4)
        cues = humor_cues(dict(start=0, end=3.9, text='Azt hittem nyertünk, de aztán kiderült... pizza volt'), t)
        self.assertIn('turn', cues)
        self.assertIn('comic_pause', cues)
        self.assertIn('reaction_after', cues)
        self.assertEqual(humor_cues(dict(start=0, end=1, text='Szia, ma a boltba megyünk.'), transcript([('Szia', 0, .4), ('ma', .5, .7)])), [])
        self.assertIn('laughter', humor_cues(dict(start=0, end=1, text='hahaha ez nagyon jó'), transcript([('hahaha', 0, .5)])))

    def test_annotate_leaves_plain_units_untouched(self):
        from comedy import annotate
        catalog = [dict(id=0, source=0, start=0, end=1, text='Plain line.'), dict(id=1, source=0, start=1, end=2, text='Visual sample', boundary='visual_sample')]
        annotate(catalog, [dict(transcript=transcript([('Plain', 0, .4)]))])
        self.assertNotIn('humor', catalog[0])
        self.assertNotIn('humor', catalog[1])


class SocialFormulaTests(unittest.TestCase):
    def plan(self, pause=False):
        catalog = [dict(id=0, source=0, start=10, end=12, text='a'), dict(id=1, source=0, start=0, end=3, text='b'), dict(id=2, source=0, start=3, end=6, text='c'), dict(id=3, source=0, start=6, end=8, text='d', humor=['reaction_after'])]
        shots = [dict(unit_id=0, source=0, start=10, end=12, beat='hook'), dict(unit_id=1, source=0, start=0, end=3, beat='context'), dict(unit_id=2, source=0, start=3, end=6, beat='context'), dict(unit_id=3, source=0, start=6, end=8, beat='payoff', preserve_pause=pause)]
        return dict(unit_ids=[0, 1, 2, 3], shots=shots), catalog

    def test_cold_open_build_and_punchline_get_their_accents(self):
        from comedy import social_polish
        plan, catalog = self.plan()
        applied = social_polish(plan, catalog, {})
        self.assertEqual({a['sound'] for a in applied}, {'rewind', 'riser', 'boom'})
        payoff = plan['shots'][3]
        self.assertEqual(payoff['sound'], 'boom')
        self.assertAlmostEqual(payoff['sound_delay'], 2 - .6, 3)
        self.assertEqual(plan['shots'][1]['sound_at'], 'start')

    def test_deadpan_pause_and_restrained_style_stay_silent(self):
        from comedy import social_polish
        plan, catalog = self.plan(pause=True)
        social_polish(plan, catalog, {})
        self.assertNotIn('sound', plan['shots'][3])
        plan, catalog = self.plan()
        self.assertEqual(social_polish(plan, catalog, dict(edit_formula='restrained')), [])
        self.assertFalse(any('sound' in s for s in plan['shots']))

    def test_camera_plan_and_pacing_keep_formula_accents(self):
        from editorial import camera_plan
        from story_director import pace
        shots = [dict(source=0, start=0, end=3, beat='context', sound='rewind', sound_delay=0, sound_at='start', formula_sound=True)]
        plan = camera_plan(shots, [dict(transcript=dict(segments=[]))], [{}])
        self.assertEqual(plan[0]['sound'], 'rewind')
        shots[0]['formula_sound'] = False
        self.assertEqual(camera_plan(shots, [dict(transcript=dict(segments=[]))], [{}])[0]['sound'], 'none')
        paced, _ = pace(dict(shots=[dict(shots[0], formula_sound=True, end=9)]), [dict(transcript=dict(segments=[]))], [dict(scene_map=dict(scenes=[dict(start=4)]))])
        self.assertEqual(paced[0]['sound'], 'rewind')
        self.assertEqual(paced[0]['sound_delay'], 0)
        self.assertTrue(all(p['sound'] == 'none' for p in paced[1:]))


@unittest.skipUnless(FFMPEG.is_file(), 'ffmpeg runtime missing')
class RawFootageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name) / 'orbit')
        self.addCleanup(self.s.db.close)
        (self.s.root / 'media-runtime/bin').mkdir(parents=True)
        (self.s.root / 'media-runtime/bin/ffmpeg').symlink_to(FFMPEG)
        for name in ('Echo', 'Scout', 'Lex', 'Reach', 'Vega'):
            self.s.save_agent(dict(project='universe', name=name, role=name, room='bridge', tools=['project_files', 'read_file', 'write_file', 'transcribe_media', 'detect_faces', 'render_short']))
        roles = role_agents(self.s, 'universe')
        for role in ('producer', 'source'):
            a = self.s.agent(roles[role])
            a['tools'] += ['find_stream_clips', 'download_stream_clip', 'start_short_production']
            self.s.save_agent(a)
        self.video = Path(self.temp.name) / 'nyers felvétel.mov'
        subprocess.run([str(FFMPEG), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=10:duration=3', '-f', 'lavfi', '-i', 'sine=d=3', '-shortest', str(self.video)], check=True)

    def test_owner_footage_is_copied_in_and_replaces_search(self):
        from raw_footage import submit
        result = submit(self.s, 'universe', [str(self.video)], '')
        data = json.loads(self.s.db.execute('SELECT data FROM short_runs WHERE id=?', (result['run'],)).fetchone()[0])
        self.assertEqual(data['edit_goal'], 'highlight')
        source = data['local_sources'][0]
        self.assertTrue(source['source_video'].startswith('inputs/media/'))
        self.assertAlmostEqual(source['duration'], 3, 0)
        self.assertEqual(source['metadata']['title'], 'nyers felvétel')
        self.assertTrue(self.video.is_file())
        producer = self.s.claim(('graph',))
        self.s.finish(producer, 'ok')
        job = self.s.claim(('graph',))
        self.assertEqual(json.loads(job['payload'])['auto_step'], 'source')
        message = run_step(self.s, job)
        self.assertIn('Saját nyers felvétel', message)
        data = json.loads(self.s.db.execute('SELECT data FROM short_runs WHERE id=?', (result['run'],)).fetchone()[0])
        self.assertEqual(data['source']['source_video'], source['source_video'])

    def test_bad_inputs_are_refused(self):
        from raw_footage import resolve_files
        text = Path(self.temp.name) / 'x.txt'
        text.write_text('x')
        for files in ([], [str(text)], ['/nincs/ilyen.mov'], ['a.mov'] * 6):
            with self.assertRaises(ValueError):
                resolve_files(self.s, 'universe', files)

    def test_survey_switches_to_highlight_policy(self):
        from content_survey import mode_policy, POLICY, HIGHLIGHT
        self.assertIs(mode_policy({}), POLICY)
        self.assertIs(mode_policy(dict(edit_goal='highlight')), HIGHLIGHT)


if __name__ == '__main__':
    unittest.main()
