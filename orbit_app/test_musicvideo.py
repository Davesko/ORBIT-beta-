"""Videoklip stúdió: clips are editable JSON, the budget adds up, the director's answer fills the plan, the song is measured."""
import json
import math
import time
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import musicvideo as mv
import project_apps
from studio import Studio

RUNTIME = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin'


class MusicVideo(unittest.TestCase):
    def setUp(self):
        language = patch('language_bridge.translate_many', side_effect=lambda texts, root: list(texts))
        language.start()
        self.addCleanup(language.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.s = Studio(Path(self.temp.name))
        self.pid = mv.ensure(self.s)

    def tearDown(self):
        self.s.db.close()
        self.temp.cleanup()

    def op(self, name, **args):
        return project_apps.dispatch(self.s, self.pid, name, args)['result']

    def test_the_project_has_its_own_app(self):
        self.assertEqual(mv.ensure(self.s), self.pid)
        app = project_apps.describe(self.s, self.pid)
        self.assertEqual(app['app'], 'clip')
        self.assertTrue(app['installed'])
        self.assertIn('Rendező', [a['name'] for a in self.s.rows('SELECT name FROM agents WHERE project=?', (self.pid,))])

    def test_create_edit_and_budget(self):
        clip = self.op('clip_create', title='Éjszakai Budapest')['clip']
        lines = [dict(category='Stáb', item='Operatőr', qty=2, unit='nap', rate=140000), dict(category='Helyszín', item='loft · Budapest', qty=1, unit='nap', rate=150000)]
        r = self.op('clip_save', clip=clip['id'], patch=dict(direction='sötét, neon', notes='jegyzet', lyrics='la la', budget=dict(lines=lines, contingency=10, currency='HUF')))
        self.assertEqual(r['budget']['subtotal'], 430000)
        self.assertEqual(r['budget']['total'], 473000)
        self.assertEqual(r['clip']['song']['lyrics'], 'la la')
        self.assertTrue(all(l['id'] for l in r['clip']['budget']['lines']))
        snap = self.op('clip_snapshot', clip=clip['id'])
        self.assertEqual(snap['clips'][0]['title'], 'Éjszakai Budapest')

    def test_other_projects_cannot_use_clip_ops(self):
        with self.assertRaises(ValueError):
            project_apps.dispatch(self.s, 'universe', 'clip_snapshot', {})

    def test_the_directors_answer_fills_story_board_and_budget(self):
        clip = self.op('clip_create', title='Teszt')['clip']
        answer = dict(concepts=[dict(title='Neon', logline='Egy éjszaka a városban', why='illik a tempóhoz')] * 2,
                      story=dict(logline='Egy éjszaka', synopsis='...', beats=[dict(time='0:00-0:20', text='intro')]),
                      storyboard=[dict(start=i * 5, end=i * 5 + 5, shot='közeli', description='arc', camera='kézi', location='tető', image_prompt='face') for i in range(6)],
                      moodboard=[dict(prompt='neon rooftop', note='fő hangulat')] * 4, palette=['#112233', 'bad', '#ff00aa'],
                      location_needs=[dict(type='tető', description='éjszakai jelenet', city='Budapest', days=1)],
                      crew=[dict(role='Operatőr', days=1, count=1), dict(role='Színész / szereplő', days=1, count=2)], references=[dict(title='Drive', note='fények')])
        job = dict(id='j', payload=json.dumps(dict(task='clip_think', project=self.pid, clip=clip['id'])))
        with patch.object(mv, 'ask', return_value=answer), patch.object(self.s, 'job_stage'):
            mv.run_think(self.s, job)
        c = mv.load(self.s, self.pid, clip['id'])
        self.assertEqual(len(c['storyboard']), 6)
        self.assertEqual(c['palette'], ['#112233', '#ff00aa'])
        items = {l['item'] for l in c['budget']['lines']}
        self.assertIn('Operatőr', items)
        self.assertTrue(any(l['category'] == 'Helyszín' for l in c['budget']['lines']))
        self.assertTrue(any(l['category'] == 'Szereplők' and l['qty'] == 2 for l in c['budget']['lines']))

    def test_any_new_plan_gets_its_pictures_and_the_people_on_screen_are_budgeted(self):
        """13 Nov: after a "rewrite the story" plan the "Slow down" storyboard stayed without pictures, and its budget had
        neither the two girls of the direction nor a camera."""
        clip = self.op('clip_create', title='Slow down')['clip']
        self.op('clip_save', clip=clip['id'], patch=dict(direction='Latin lüktetés, max 250 ezer forint, szerepeljen benne 2 lány.'))
        answer = dict(concepts=[dict(title='Tető', logline='x', why='y')], story=dict(logline='x', synopsis='', beats=[]),
                      storyboard=[dict(start=0, end=5, shot='közeli', description='arc', camera='kézi', location='tető', image_prompt='face')],
                      moodboard=[dict(prompt='neon', note='')], palette=['#112233'], location_needs=[dict(type='tető', city='Budapest', days=1)],
                      crew=[dict(role='Operatőr', days=1, count=1)], references=[])
        job = dict(id='j', payload=json.dumps(dict(task='clip_think', project=self.pid, clip=clip['id'], focus='írd újra a sztorit')))
        with patch.object(mv, 'ask', return_value=answer), patch.object(self.s, 'job_stage'):
            mv.run_think(self.s, job)
        tasks = [r['task'] for r in self.s.rows("SELECT json_extract(payload,'$.task') task FROM jobs WHERE status='queued'")]
        self.assertIn('clip_images', tasks)              # not a chain, still drawn
        self.assertNotIn('clip_locations', tasks)        # places only with the full plan
        lines = mv.load(self.s, self.pid, clip['id'])['budget']['lines']
        self.assertTrue(any(l['category'] == 'Szereplők' and l['qty'] == 2 for l in lines))
        self.assertTrue(any(l['category'] == 'Technika' for l in lines))

    def test_more_than_sixteen_missing_pictures_continue_in_a_next_job(self):
        clip = self.op('clip_create', title='Sok kép')['clip']
        c = mv.load(self.s, self.pid, clip['id'])
        c['storyboard'] = [dict(id=f's{i}', artifact=None, start=i, end=i + 1, image_prompt='shot') for i in range(18)]
        mv.store(self.s, self.pid, c)
        jid = self.s.enqueue(self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'], 'x', 'assist',
                             payload=dict(task='clip_images', project=self.pid, clip=clip['id'], which='storyboard'))
        job = dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())
        with patch('design_studio.flux'), patch.object(self.s, 'job_stage'):
            mv.run_images(self.s, job)
        c = mv.load(self.s, self.pid, clip['id'])
        self.assertEqual(sum(1 for x in c['storyboard'] if x['artifact']), 16)
        follow = self.s.rows("SELECT payload FROM jobs WHERE status='queued' AND json_extract(payload,'$.task')='clip_images' AND id!=?", (jid,))
        self.assertEqual(len(follow), 1)

    def test_an_older_budget_shows_and_fills_what_a_shoot_needs(self):
        clip = self.op('clip_create', title='Régi terv')['clip']
        self.op('clip_save', clip=clip['id'], patch=dict(direction='szerepeljen benne 2 lány'))
        snap = self.op('clip_snapshot', clip=clip['id'])
        self.assertEqual({l['item'] for l in snap['missing']}, {'Színész / szereplő', 'Kamera szett bérlés'})
        after = self.op('clip_budget_fill', clip=clip['id'])
        self.assertEqual(after['missing'], [])
        self.assertTrue(any(l['category'] == 'Szereplők' and l['qty'] == 2 for l in after['clip']['budget']['lines']))

    def test_the_dossier_groups_the_shots_by_place_for_the_crew(self):
        needs = [dict(type='bár / raktár (elhagyatott üzlet)', city='Budapest', description='neonos hűtőszekrények, polcok'), dict(type='utca', city='Budapest')]
        board = [dict(start=0, end=10, location='Polcok közötti árnyékos tér', camera='kézi'), dict(start=10, end=20, location='Budapesti utca, éjszaka'),
                 dict(start=20, end=35, location='Hűtőszekrények sorában', camera='drón'), dict(start=35, end=40, location='Ajtó melletti sötét sarok')]
        order = mv.shooting_order(board, needs)
        self.assertEqual([(g['place'], g['shots'], g['seconds']) for g in order],
                         [('bár / raktár (elhagyatott üzlet) · Budapest', [1, 3, 4], 30.), ('utca · Budapest', [2], 10.)])
        self.assertEqual(order[0]['cameras'], ['kézi', 'drón'])
        self.assertEqual([g['place'] for g in mv.shooting_order(board, [needs[0]])], ['bár / raktár (elhagyatott üzlet) · Budapest', 'Külső helyszín (utca / szabad tér)'])

    def test_the_locations_tab_gets_the_shooting_order(self):
        clip = self.op('clip_create', title='Sorrend')['clip']
        c = mv.load(self.s, self.pid, clip['id'])
        c['storyboard'] = [dict(id='a', start=0, end=5, location='tető'), dict(id='b', start=5, end=9, location='utca')]
        c['location_needs'] = [dict(type='tető', city='Budapest')]
        mv.store(self.s, self.pid, c)
        snap = self.op('clip_snapshot', clip=clip['id'])
        self.assertEqual([g['place'] for g in snap['shooting']], ['tető · Budapest', 'Külső helyszín (utca / szabad tér)'])
        self.assertIn('d.shooting', (Path(mv.__file__).with_name('web') / 'clip_studio_ui.js').read_text(encoding='utf-8'))

    def test_role_names_written_differently_still_get_the_indie_rate(self):
        clip = self.op('clip_create', title='Keret')['clip']
        c = mv.load(self.s, self.pid, clip['id'])
        c['budget'].update(cap=400000, contingency=5, lines=[
            dict(id='a', category='Stáb', item='Rendező / Operatőr', qty=2, unit='nap', rate=150000),
            dict(id='b', category='Szereplők', item='Színész / Szereplő', qty=4, unit='fő/nap', rate=50000),
            dict(id='c', category='Stáb', item='Fókusz / Asszisztens', qty=1, unit='nap', rate=60000),
            dict(id='d', category='Stáb', item='Saját sor', qty=1, unit='nap', rate=90000, owner=True)])
        mv.store(self.s, self.pid, c)
        out = self.op('clip_fit', clip=clip['id'])
        lines = {l['item']: l['rate'] for l in out['clip']['budget']['lines']}
        self.assertEqual((lines['Rendező / Operatőr'], lines['Színész / Szereplő'], lines['Fókusz / Asszisztens']), (50000, 20000, 20000))
        self.assertEqual(lines['Saját sor'], 90000)          # the owner's own line is never touched
        self.assertFalse(out['budget']['over'])

    def test_a_short_story_is_stretched_to_the_end_of_the_song(self):
        beats = [dict(time=t, text='x') for t in ('0:00-0:25', '0:25-1:08', '1:08-1:52')]
        out = [b['time'] for b in mv.fit_beats(beats, 152.3)]
        self.assertTrue(out[-1].endswith('2:32'))
        self.assertEqual(out[0][:4], '0:00')
        kept = [b['time'] for b in mv.fit_beats([dict(time='0:00-2:20', text='x')], 152.3)]
        self.assertEqual(kept, ['0:00-2:20'])          # within 85%: left as the director wrote it

    def test_story_beats_stay_inside_the_song_in_order(self):
        beats = [dict(time=t, text='x') for t in ('0:00-0:25', '0:24-0:54', '2:52-3:22', '3:22-3:52')]
        out = [b['time'] for b in mv.fit_beats(beats, 152.3)]
        self.assertEqual(out[0][:4], '0:00')
        self.assertEqual(out[-1][-4:], '2:32')
        ends = [int(t.split('-')[1].split(':')[0]) * 60 + int(t.split('-')[1].split(':')[1]) for t in out]
        starts = [int(t.split('-')[0].split(':')[0]) * 60 + int(t.split('-')[0].split(':')[1]) for t in out]
        self.assertTrue(all(s >= e for s, e in zip(starts[1:], ends)))

    def test_a_picked_location_price_goes_into_the_budget(self):
        clip = self.op('clip_create', title='Teszt')['clip']
        self.op('clip_save', clip=clip['id'], patch=dict(budget=dict(lines=[dict(category='Helyszín', item='tető · Budapest', qty=1, unit='nap', rate=150000)], contingency=0),
                                                       locations=[dict(id='abcdefabcdef', name='Tetőterasz', type='tető', price_day=90000)]))
        r = self.op('clip_pick_location', clip=clip['id'], location='abcdefabcdef')
        self.assertEqual(r['budget']['total'], 90000)

    @unittest.skipUnless((RUNTIME / 'ffmpeg').is_file(), 'media runtime missing')
    def test_the_song_is_measured(self):
        song = Path(self.temp.name) / 'song.wav'
        rate = 22050
        with wave.open(str(song), 'wb') as w:
            w.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            frames = bytearray()
            for i in range(rate * 30):
                t = i / rate
                beat = 1.0 if (t * 2) % 1 < .08 else .15            # 120 BPM clicks
                loud = .3 if t < 12 else .9                          # a quiet part, then a loud one
                v = int(32767 * loud * beat * math.sin(2 * math.pi * 220 * t))
                frames += v.to_bytes(2, 'little', signed=True)
            w.writeframes(bytes(frames))
        done = subprocess.run([str(RUNTIME / 'python3'), '-I', '-c', mv.ANALYSE, str(RUNTIME / 'ffmpeg'), str(song)], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertAlmostEqual(result['duration'], 30, delta=.5)
        self.assertTrue(result['bpm'] and 110 <= result['bpm'] <= 130, result['bpm'])
        self.assertGreaterEqual(len(result['parts']), 2)


    def test_a_wav_song_can_be_imported_and_attached(self):
        import media_tools
        song = Path(self.temp.name) / 'demo.wav'
        with wave.open(str(song), 'wb') as w:
            w.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'));w.writeframes(b'\0\0' * 8000)
        media_tools.import_media(self.s, self.pid, str(song))
        audio = self.op('clip_snapshot')['audio']
        self.assertEqual(audio[0]['name'], 'demo.wav')
        clip = self.op('clip_create', title='Wav')['clip']
        with patch.object(self.s, 'enqueue'):
            snap = self.op('clip_song', clip=clip['id'], artifact=audio[0]['id'])
        self.assertEqual(snap['clip']['song']['name'], 'demo.wav')
        self.assertIn("call('import_media_file')", (Path(__file__).with_name('web') / 'clip_studio_ui.js').read_text(encoding='utf-8'))


    def test_the_budget_ceiling_is_read_and_kept(self):
        self.assertEqual(mv.budget_cap('Latin lüktetés, max 250 ezer forint, 2 lány.'), 250000)
        self.assertEqual(mv.budget_cap('keret: 1,5 millió'), 1500000)
        self.assertIsNone(mv.budget_cap('2 lány, 3 perc, 1 nap'))
        clip = mv.blank('Slow down')
        crew = [dict(role=r, days=1, count=1) for r in ('Rendező', 'Operatőr', 'Operatőr-asszisztens / fókuszhúzó', 'Gaffer (világosító)', 'Világosító asszisztens',
                'Gyártásvezető', 'Smink', 'Stylist / jelmez', 'Díszlet / art director', 'Kamera szett bérlés', 'Objektív szett', 'Fény csomag', 'Gimbal / stabilizátor', 'Kisbusz / szállítás')]
        clip['budget']['lines'] = mv.plan_lines(crew, [dict(type='loft', city='Budapest', days=1)])
        self.assertEqual(sum(l['item'] == 'Kisbusz / szállítás' for l in clip['budget']['lines']), 1)   # not twice
        clip['budget']['cap'] = 250000
        self.assertGreater(mv.budget(clip)['total'], 250000)
        mv.fit_budget(clip)
        self.assertLessEqual(mv.budget(clip)['total'], 250000)
        self.assertFalse(mv.budget(clip)['over'])

    def test_the_director_is_asked_for_creative_concepts_within_the_ceiling(self):
        self.assertIn('never as the idea itself', mv.CREATIVE)
        self.assertIn('HARD BUDGET CEILING: 250000', mv.money_rules(250000))
        self.assertEqual(len(set(mv.lenses(1))), 3)

    def test_more_concepts_are_added_next_to_the_old_ones(self):
        clip = self.op('clip_create', title='Slow down')['clip']
        self.op('clip_save', clip=clip['id'], patch=dict(concepts=[dict(title='Loft', logline='x', why='y')]))
        job = dict(id='j', payload=json.dumps(dict(task='clip_concepts', project=self.pid, clip=clip['id'])))
        new = dict(concepts=[dict(title='Mosoda', logline='Két lány egy éjszakai mosodában', why='olcsó'), dict(title='Loft', logline='x', why='y')])
        with patch.object(mv, 'ask', return_value=new), patch.object(self.s, 'job_stage'):
            mv.run_concepts(self.s, job)
        self.assertEqual([k['title'] for k in mv.load(self.s, self.pid, clip['id'])['concepts']], ['Loft', 'Mosoda'])

    def test_the_main_assistant_can_drive_a_clip(self):
        self.op('clip_create', title='Slow down')
        with patch.object(self.s, 'enqueue'):
            r = mv.act(self.s, dict(type='videoklip', op='concepts', clip='slow down', text='merészebb'))
        self.assertIn('Slow down', r['message'])
        r = mv.act(self.s, dict(type='videoklip', op='budget', clip='Slow down', text='max 250 ezer'))
        self.assertIn('250 000', r['message'])
        with self.assertRaises(ValueError):
            mv.act(self.s, dict(type='videoklip', op='think', clip='nincs ilyen klip'))
        import assistant_tools
        self.assertIn('videoklip', assistant_tools.ACTION_CONTRACTS)


    def test_a_chat_sentence_about_a_clip_goes_straight_to_the_studio(self):
        self.op('clip_create', title='Slow down')
        a = mv.route(self.s, 'a slow down kliphez keress több koncepciót')
        self.assertEqual((a['type'], a['op'], a['clip']), ('videoklip', 'concepts', 'Slow down'))
        self.assertEqual(mv.route(self.s, 'Slow down: a keret max 250 ezer')['op'], 'budget')
        self.assertEqual(mv.route(self.s, 'keress helyszínt a slow down videoklipnek')['op'], 'locations')
        self.assertIsNone(mv.route(self.s, 'milyen idő lesz holnap?'))
        self.assertIsNone(mv.route(self.s, 'lassíts le egy kicsit'))


    def test_a_concept_replans_everything_and_the_old_plan_stays_a_version(self):
        clip = self.op('clip_create', title='Slow down')['clip']
        old = [dict(title='Loft', logline='x', why='y'), dict(title='Mosoda', logline='Két lány egy éjszakai mosodában', why='olcsó', look='neon', look_prompt='laundromat')]
        self.op('clip_save', clip=clip['id'], patch=dict(concepts=old, moodboard=[dict(prompt='loft light', note='')]))
        mosoda = next(k for k in mv.load(self.s, self.pid, clip['id'])['concepts'] if k['title'] == 'Mosoda')
        with patch.object(self.s, 'enqueue') as queued:
            self.op('clip_plan_concept', clip=clip['id'], concept=mosoda['id'])
        payload = queued.call_args.kwargs['payload']
        self.assertTrue(payload['chain'])
        answer = dict(concepts=[dict(title='Más', logline='z', why='w', look='l', look_prompt='p')] * 2, story=dict(logline='Mosoda éjjel', synopsis='', beats=[]),
                      storyboard=[dict(start=0, end=5, shot='totál', description='mosoda', camera='kézi', location='mosoda')] * 6,
                      moodboard=[dict(prompt='laundromat at night neon', note='')] * 4, palette=[], location_needs=[], crew=[], references=[])
        job = dict(id='j', payload=json.dumps(dict(task='clip_think', project=self.pid, clip=clip['id'], concept=mosoda, chain=False)))
        with patch.object(mv, 'ask', return_value=answer), patch.object(self.s, 'job_stage'):
            mv.run_think(self.s, job)
        c = mv.load(self.s, self.pid, clip['id'])
        self.assertEqual(c['concepts'][0]['title'], 'Mosoda')
        self.assertEqual(c['moodboard'][0]['prompt'], 'laundromat at night neon')
        self.assertEqual(c['versions'][0]['plan']['moodboard'][0]['prompt'], 'loft light')
        r = self.op('clip_restore', clip=clip['id'], version=c['versions'][0]['id'])
        self.assertEqual(r['clip']['moodboard'][0]['prompt'], 'loft light')

    def test_empty_clips_are_reused_and_a_dossier_is_written(self):
        a = self.op('clip_create')['clip']
        b = self.op('clip_create', title='Második')['clip']
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(b['title'], 'Második')
        r = self.op('clip_export', clip=b['id'])
        path = self.s.db.execute('SELECT path FROM artifacts WHERE id=?', (r['artifact'],)).fetchone()[0]
        self.assertIn('Második', Path(path).read_text(encoding='utf-8'))


    def test_plan_from_concept_switches_at_once(self):
        clip = self.op('clip_create', title='Váltás')['clip']
        self.op('clip_save', clip=clip['id'], patch=dict(concepts=[dict(title='A', logline='a', why=''), dict(title='B', logline='b sztori', why='')],
                                                       moodboard=[dict(prompt='old', note='')], storyboard=[dict(start=0, end=5, shot='x')]))
        b = next(k for k in mv.load(self.s, self.pid, clip['id'])['concepts'] if k['title'] == 'B')
        with patch.object(self.s, 'enqueue'):
            self.op('clip_plan_concept', clip=clip['id'], concept=b['id'])
        c = mv.load(self.s, self.pid, clip['id'])
        self.assertEqual((c['concepts'][0]['title'], c['chosen'], c['replanning'], c['story']['logline']), ('B', 0, 'B', 'b sztori'))
        self.assertEqual((c['moodboard'], c['storyboard']), ([], []))
        self.assertEqual(mv.hungarian_title("A 'Betörő' Buszjárat (The Striking Bus Route)"), "A 'Betörő' Buszjárat")
        self.assertIn('Mood:', mv.image_prompt(dict(c, mood='hazy night'), 'moodboard', 'two women on a tram'))


    def test_more_mood_pictures_follow_the_owners_prompt(self):
        clip = self.op('clip_create', title='Mood')['clip']
        with patch.object(self.s, 'enqueue') as queued:
            self.op('clip_moods', clip=clip['id'], prompt='két lány a busz hátsó ablakánál', count=2)
        payload = queued.call_args.kwargs['payload']
        self.assertEqual((payload['task'], payload['count']), ('clip_moods', 2))
        job = dict(id='j', payload=json.dumps(payload))
        answer = dict(moodboard=[dict(prompt='two girls at the back window of a night bus, blue dawn light', note='hajnal'), dict(prompt='close-up', note='x')])
        with patch.object(mv, 'ask', return_value=answer), patch.object(mv, 'run_images') as drawn, patch.object(self.s, 'job_stage'):
            mv.run_moods(self.s, job)
        c = mv.load(self.s, self.pid, clip['id'])
        self.assertEqual([m['prompt'] for m in c['moodboard']][:1], ['two girls at the back window of a night bus, blue dawn light'])
        self.assertTrue(drawn.called)


class Activity(unittest.TestCase):
    def test_running_and_queued_work_of_every_project_is_listed(self):
        import activity_now
        with tempfile.TemporaryDirectory() as root:
            with patch('language_bridge.translate_many', side_effect=lambda texts, root: list(texts)):
                s = Studio(Path(root))
                agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()[0]
                s.enqueue(agent, 'Videoklip · a Rendező tervez', 'assist', payload=dict(task='clip_think'))
                s.db.execute("UPDATE jobs SET status='running',started=? WHERE status='queued'", (time.time() - 75,))
                s.db.commit()
                d = activity_now.snapshot(s)
                s.db.close()
        self.assertEqual(d['running'], 1)
        self.assertEqual(d['items'][0]['title'], 'A Rendező tervez')
        self.assertGreaterEqual(d['items'][0]['seconds'], 75)


if __name__ == '__main__':
    unittest.main()
