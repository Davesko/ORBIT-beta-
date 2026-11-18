import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from studio import Studio
import self_improve


class SelfImproveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.pid = self.s.create_project('Shorts', 'Videók')
        self.agent = self.s.save_agent(dict(project=self.pid, name='A', role='A', room='bridge'))
        self.agent = self.agent if isinstance(self.agent, str) else self.agent['id']

    def fail(self, error, n, kind='graph', step=None):
        for i in range(n):
            jid = self.s.enqueue(self.agent, 'x', kind, payload=dict(**({'auto_step': step} if step else {})))
            self.s.db.execute("UPDATE jobs SET status='failed',error=?,started=created,finished=created+5 WHERE id=?", (error.replace('{i}', str(1000 + i)), jid))
        self.s.db.commit()

    def test_a_project_in_the_kuka_is_neither_analysed_nor_improved(self):
        self.fail('Hiba {i}', 3)
        self_improve.save(self.s, self.pid, [dict(title='Jobb képek', why='w', evidence='e', size='S', area='quality')], 'model')
        self.assertIn(self.pid, self_improve.scopes(self.s))
        self.assertTrue(any(i['scope'] == self.pid for i in self_improve.listing(self.s)['ideas']))
        self.s.db.execute('DELETE FROM projects WHERE id=?', (self.pid,))   # what the Kuka leaves: jobs and ideas, no project row
        self.s.db.commit()
        self.assertNotIn(self.pid, self_improve.scopes(self.s))
        self.assertFalse(any(i['scope'] == self.pid for i in self_improve.listing(self.s)['ideas']))

    def test_recurring_error_with_different_numbers_becomes_one_measured_idea(self):
        self.fail('A forrás 12{i} mp-nél megszakadt (job a1b2c3d4e5{i})', 4, step='source')
        data = self_improve.facts(self.s, self.pid)
        self.assertEqual(data['recurring_errors'][0]['count'], 4)
        self.assertEqual(data['shorts_stopped_at'], {'source': 4})
        ideas = self_improve.rule_ideas(self.pid, data)
        self.assertTrue(any('4×' in i['title'] for i in ideas))
        self.assertTrue(any('Internetes klipkeresés' in i['title'] for i in ideas))
        self.assertEqual(self_improve.save(self.s, self.pid, ideas, 'measured'), len(ideas))
        self.assertEqual(self_improve.save(self.s, self.pid, ideas, 'measured'), 0)

    def test_follow_on_stops_are_not_the_cause_and_counts_update_one_card(self):
        self.fail('Every scene needs a different opening_image.', 3)
        self.fail('Az előző lépés nem fejeződött be sikeresen.', 9)
        data = self_improve.facts(self.s, self.pid)
        self.assertEqual([e['example'] for e in data['recurring_errors']], ['Every scene needs a different opening_image.'])
        self_improve.save(self.s, self.pid, self_improve.rule_ideas(self.pid, data), 'measured')
        self.fail('Every scene needs a different opening_image.', 2)
        self_improve.save(self.s, self.pid, self_improve.rule_ideas(self.pid, self_improve.facts(self.s, self.pid)), 'measured')
        titles = [r['title'] for r in self.s.rows("SELECT title FROM improvement_ideas WHERE status='new'")]
        self.assertEqual(titles, ['Visszatérő hiba megszüntetése (5×)'])
        self.s.db.execute("INSERT INTO improvement_ideas VALUES('old',?,'Visszatérő hiba megszüntetése (52×)','','Az előző lépés nem fejeződött be sikeresen.','M','reliability','measured','new',0,0)", (self.pid,))
        self_improve.retire(self.s, self.pid)
        self.assertEqual(self.s.db.execute("SELECT status FROM improvement_ideas WHERE id='old'").fetchone()[0], 'dismissed')

    def test_model_ideas_are_saved_and_failure_keeps_measured_part(self):
        self.fail('Hiba {i}', 3)
        reply = dict(message=dict(content=json.dumps(dict(ideas=[dict(title='Gyorsabb átirat', why='Rövidebb várakozás.', evidence='3 hiba', size='S', area='speed'), 'junk']))))
        with patch('studio.local_api', return_value=reply):
            added = self_improve.analyse(self.s, self.pid)
        self.assertEqual(added, 2)
        titles = [i['title'] for g in self_improve.listing(self.s)['groups'] for i in g['ideas']]
        self.assertIn('Gyorsabb átirat', titles)
        job = dict(id='j', payload=json.dumps(dict(scope=self.pid)))
        with patch('studio.local_api', side_effect=ValueError('nincs modell')):
            self.assertIn('mért javaslat', self_improve.run_job(self.s, job))

    def test_accept_gives_a_chat_request_and_dismiss_hides(self):
        self_improve.save(self.s, 'orbit', [dict(title='Gyorsabb chat', why='Kevesebb várakozás.', evidence='5 lassú válasz')], 'model')
        idea = self_improve.listing(self.s)['groups'][0]['ideas'][0]
        r = self_improve.dispatch(self.s, 'improve_set', dict(id=idea['id'], status='accepted'))
        self.assertIn('az ORBIT appban', r['request'])
        self.assertIn('csak írd le', r['request'])
        self_improve.dispatch(self.s, 'improve_set', dict(id=idea['id'], status='dismissed'))
        self.assertEqual(self_improve.listing(self.s)['groups'], [])
        with self.assertRaises(ValueError):
            self_improve.dispatch(self.s, 'improve_set', dict(id=idea['id'], status='törölve'))

    def test_idle_time_is_used_by_day_too_and_never_queues_twice(self):
        day = time.time()
        busy = self.s.enqueue(self.s.rows('SELECT id FROM agents LIMIT 1')[0]['id'], 'más munka')
        self.assertFalse(self_improve.schedule(self.s, day))
        self.s.db.execute("UPDATE jobs SET status='done',finished=? WHERE id=?", (day - 30, busy));self.s.db.commit()
        self.assertFalse(self_improve.schedule(self.s, day), 'something finished half a minute ago')
        self.s.db.execute('UPDATE jobs SET finished=? WHERE id=?', (day - 600, busy));self.s.db.commit()
        night = day
        self.assertTrue(self_improve.schedule(self.s, night))
        self.assertFalse(self_improve.schedule(self.s, night))
        job = self.s.db.execute("SELECT payload FROM jobs WHERE kind='assist'").fetchone()
        self.assertEqual(json.loads(job[0])['scope'], 'orbit')

    def test_run_now_shows_measured_ideas_at_once(self):
        self.fail('Ugyanaz', 3)
        r = self_improve.dispatch(self.s, 'improve_run', dict(scope=self.pid))
        self.assertTrue(r['queued'])
        self.assertGreaterEqual(r['added'], 1)
        self.assertTrue(self_improve.dispatch(self.s, 'improve_run', dict(scope=self.pid))['queued'])
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='assist'").fetchone()[0], 1)

    def test_urgent_first_duplicates_merged_and_fixed_cards_leave(self):
        now = time.time()
        self.fail('Friss hiba ami most is jön', 3)
        self_improve.save(self.s, self.pid, self_improve.rule_ideas(self.pid, self_improve.facts(self.s, self.pid)), 'measured')
        self_improve.save(self.s, 'orbit', self_improve.rule_ideas('orbit', self_improve.facts(self.s, 'orbit')), 'measured')
        self_improve.save(self.s, 'orbit', [dict(title='Szebb gombok', why='Kellemesebb.', evidence='ízlés')], 'model')
        old = dict(title='Visszatérő hiba megszüntetése (4×)', why='régi', evidence='Régi hiba ami már nem jön elő soha', area='reliability', size='M')
        self_improve.save(self.s, 'orbit', [old], 'measured')
        self.s.db.execute("UPDATE improvement_ideas SET created=? WHERE evidence LIKE 'Régi hiba%'", (now - 3 * 86400,));self.s.db.commit()
        data = self_improve.listing(self.s, now)
        self.assertEqual(data['ideas'][0]['urgency'], 'sos')
        self.assertEqual(data['ideas'][0].get('also'), 1, 'the project copy is folded into one card')
        self.assertEqual([i['title'] for i in data['done']], [old['title']])
        self.assertIn('Megoldva', [a['kind'] for a in data['activity']['recent']])
        self.assertEqual(self_improve.listing(self.s, now + 2 * 86400)['done'], [], 'finished cards leave after a day')

    def test_activity_shows_what_orbit_does_for_itself(self):
        agent = self.s.rows('SELECT id FROM agents LIMIT 1')[0]['id']
        a = self.s.enqueue(agent, 'Önfejlesztő elemzés · orbit', 'assist', payload=dict(task='self_improve', scope='orbit'))
        b = self.s.enqueue(agent, self_improve.SELF_TASK + ' az ORBIT appban: Gyorsabb chat. Cél: x')
        self.s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?", (time.time(), a))
        self.s.db.execute("INSERT INTO job_log(job,kind,label,details,created) VALUES(?,?,?,?,?)", (b, 'recovering', 'Átmeneti modellhiba · újrapróbálás 1/3', '', time.time()));self.s.db.commit()
        got = self_improve.activity(self.s)
        self.assertEqual([(x['kind'], x['state']) for x in got['live']], [('Ötletelés', 'most fut'), ('Fejlesztés', 'sorban áll')])
        self.assertEqual(got['recent'][0]['kind'], 'Hibakezelés')

    def test_what_needs_program_code_is_set_aside_not_retried(self):
        from commander import schema
        schema(self.s)
        self_improve.save(self.s, 'orbit', [dict(title='Gyorsabb modellválasztás', why='x', evidence='y')], 'model')
        idea = self_improve.listing(self.s)['ideas'][0]
        self_improve.dispatch(self.s, 'improve_set', dict(id=idea['id'], status='accepted'))
        cols = [c[1] for c in self.s.db.execute('PRAGMA table_info(command_turns)')]
        values = dict(id='t1', prompt=self_improve.SELF_TASK + ' az ORBIT appban: Gyorsabb modellválasztás. Cél: x', status='done', created=time.time(), actions='[]',
                      response='A fejlesztés nem valósítható meg: az alkalmazás belső programkódját kell módosítani.')
        self.s.db.execute('INSERT INTO command_turns(' + ','.join(cols) + ') VALUES(' + ','.join('?' * len(cols)) + ')', tuple(values.get(c, '') for c in cols));self.s.db.commit()
        data = self_improve.listing(self.s)
        self.assertEqual((data['ideas'], [d['title'] for d in data['developer']]), ([], ['Gyorsabb modellválasztás']))
        self.assertIn('Gyorsabb modellválasztás', (self.s.root / 'developer-inbox.md').read_text())


if __name__ == '__main__':
    unittest.main()
