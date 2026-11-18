import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import automation_intent as ai
from studio import Studio


class ScheduleTests(unittest.TestCase):
    def test_times_intervals_days_and_ranges(self):
        now = time.mktime(time.strptime('2026-11-08 10:00', '%Y-%m-%d %H:%M'))
        a = ai.schedule('minden reggel 8-kor nézd meg a telexet', now)
        self.assertEqual((a['daily_time'], a['interval'], a['run_now']), ('08:00', 1440, False))
        b = ai.schedule('hétköznap este 9-kor írj összefoglalót', now)
        self.assertEqual((b['daily_time'], b['plan']['weekdays']), ('21:00', [0, 1, 2, 3, 4]))
        c = ai.schedule('30 percenként ellenőrizd a bitcoin árfolyamát', now)
        self.assertEqual((c['interval'], c['daily_goal'], c['run_now']), (30, 48, True))
        d = ai.schedule('fusson le egymás után 3 szor', now)
        self.assertEqual((d['daily_goal'], d['plan']['end_date']), (3, '2026-11-08'))
        e = ai.schedule('mostantól holnap éjszakáig készíts animációkat', now)
        self.assertEqual((e['interval'], e['plan']['end_date']), (180, '2026-11-09'))

    def test_what_counts_as_an_automation_request(self):
        for p in ('minden reggel 8-kor foglald össze a híreket', 'óránként nézd meg az index.hu-t', 'állíts be egy automatizációt ami naponta ír egy verset'):
            self.assertTrue(ai.wants(p), p)
        for p in ('nyisd meg a youtube-ot', 'létrehoztad az automatizációt?', '[ORBIT-RUN] minden reggel nézd meg a híreket', 'állítsd le az automatizációt'):
            self.assertFalse(ai.wants(p), p)
        self.assertTrue(ai.asks_about('milyen automatizációk futnak?'))


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.s.save_agent(dict(project='universe', name='A', role='A', room='bridge'))
        self.job = dict(id=self.s.enqueue(self.s.rows("SELECT id FROM agents LIMIT 1")[0]['id'], 'x', 'command'))

    def test_creates_an_enabled_task_and_runs_it_now_once(self):
        with patch.object(ai, 'extract', return_value=('nézd meg az index.hu főoldalát és szólj, ha nagy hír van', 'Index-figyelő')):
            reply = ai.create(self.s, self.job, 'óránként nézd meg az index.hu-t és szólj ha nagy hír van')
        self.assertIn('Beállítottam és bekapcsoltam', reply)
        self.assertIn('óránként', reply)
        a = self.s.rows('SELECT * FROM automations')[0]
        cfg = json.loads(a['config'])
        self.assertEqual((a['kind'], a['enabled'], a['interval']), ('assistant', 1, 60))
        self.assertTrue(cfg['prompt'].startswith('[ORBIT-RUN]'))
        runs = self.s.rows('SELECT * FROM automation_runs')
        self.assertEqual(len(runs), 1)
        self.assertGreater(a['next_run'], time.time() + 3000)
        cmd = self.s.rows("SELECT prompt FROM jobs WHERE kind='command' AND prompt LIKE '[ORBIT-RUN]%'")
        self.assertEqual(len(cmd), 1)
        self.assertIn('Index-figyelő', ai.overview(self.s))

    def test_a_clock_time_waits_for_its_time(self):
        with patch.object(ai, 'extract', return_value=('foglald össze a Telex 5 legfontosabb hírét', 'Reggeli hírek')):
            reply = ai.create(self.s, self.job, 'minden reggel 8-kor foglald össze a telex 5 legfontosabb hírét')
        self.assertIn('Első futás', reply)
        self.assertEqual(self.s.rows('SELECT * FROM automation_runs'), [])

    def test_the_chat_creates_it_without_the_planner(self):
        import commander
        with patch.object(ai, 'extract', return_value=('írj egy rövid verset', 'Napi vers')):
            jid = commander.enqueue(self.s, 'universe', 'minden este 9-kor írj nekem egy rövid verset', global_mode=True)
            reply = commander.run(self.s, dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()))
        self.assertIn('Napi vers', reply)
        self.assertEqual(len(self.s.rows('SELECT * FROM automations')), 1)


class WebAnswerTests(unittest.TestCase):
    def test_news_questions_go_headless_and_blocked_pages_use_the_feed(self):
        import computer_agent as ca
        self.assertTrue(ca.wants_web('nézd meg a telex főoldalát és foglald össze a híreket'))
        self.assertFalse(ca.wants_web('nyisd meg a telexet safariban'))
        self.assertTrue(ca.blocked('Just a moment... Cloudflare'))
        with patch.object(ca, 'read_feed', return_value='Hírfolyam:\n- Fontos hír'), patch('research.read', return_value=dict(text='Just a moment')), \
             patch('studio.local_api', return_value=dict(message=dict(content='1. Fontos hír'))):
            reply = ca.web_answer(unittest.mock.Mock(), dict(id='j'), 'nézd meg a telex főoldalát és foglald össze a híreket')
        self.assertIn('Fontos hír', reply)
        self.assertIn('telex.hu', reply)


if __name__ == '__main__':
    unittest.main()


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.s.save_agent(dict(project='universe', name='A', role='A', room='bridge'))
        self.job = dict(id=self.s.enqueue(self.s.rows("SELECT id FROM agents LIMIT 1")[0]['id'], 'x', 'command'))
        with patch.object(ai, 'extract', return_value=('készíts egy stoner 2D animációs shortot', 'Stoner animációk')):
            self.reply = ai.create(self.s, self.job, 'indíts egy automatizációt ami stoner 2d animációs shortsokat készít, a cél 3 sikeres videó')
        import automations
        self.auto = automations
        self.aid = self.s.rows('SELECT id FROM automations')[0]['id']

    def finish(self, video):
        import automations
        run = self.s.rows("SELECT * FROM automation_runs WHERE status IN ('starting','running') ORDER BY created DESC")[0]
        for j in automations.members(self.s, automations.decode(run)):
            self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?", (j['id'],))
            turn = json.loads(j['payload']).get('turn')
            if turn:
                self.s.db.execute("UPDATE command_turns SET status='done' WHERE id=?", (turn,))
            if video:
                self.s.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)", ('v' + j['id'], 'universe', 'x.mp4', '/x.mp4', 'video', time.time(), j['id']))
        self.s.db.commit()
        automations.reconcile(self.s)

    def test_runs_follow_each_other_until_the_goal_and_only_videos_count(self):
        self.assertIn('cél: 3 sikeres videó', self.reply)
        self.finish(video=True)
        self.auto.tick(self.s)
        self.finish(video=False)  # finished without a video: does not count
        self.auto.tick(self.s)
        last = self.s.rows("SELECT prompt FROM jobs WHERE kind='command' AND prompt LIKE '[ORBIT-RUN]%' ORDER BY created DESC LIMIT 1")[0]['prompt']
        self.assertIn('előző futás nem sikerült', last)
        self.finish(video=True)
        self.auto.tick(self.s)
        self.finish(video=True)
        self.auto.tick(self.s)
        a = self.auto.get(self.s, 'universe', self.aid)
        self.assertFalse(a['enabled'])
        self.assertEqual(self.auto.goal_progress(self.s, a)['done'], 3)
        self.assertIn('3/3', ai.overview(self.s))

    def test_too_many_failures_stop_it_with_a_reason(self):
        # The test moves run times back; the goal counts from the beginning.
        self.s.db.execute("UPDATE automations SET config=json_set(config,'$.goal.since',0)")
        self.s.db.commit()
        for _ in range(self.auto.GOAL_FAST_RETRIES + 1):
            self.finish(video=False)
            self.auto.tick(self.s)
        # After the quick retries it pauses before the next attempt.
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM automation_runs WHERE status IN ('starting','running')").fetchone()[0], 0)
        self.s.db.execute('UPDATE automation_runs SET created=created-700')
        self.s.db.commit()
        for _ in range(10):
            self.auto.tick(self.s)
            if self.s.db.execute("SELECT count(*) FROM automation_runs WHERE status IN ('starting','running')").fetchone()[0]:
                self.finish(video=False)
                self.s.db.execute('UPDATE automation_runs SET created=created-700')
                self.s.db.commit()
        a = self.auto.get(self.s, 'universe', self.aid)
        self.assertFalse(a['enabled'])
        self.assertIn('egymás utáni sikertelen futás', a['last_error'])


class ConvertTests(unittest.TestCase):
    def test_a_goal_for_an_existing_automation_converts_it(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        s = Studio(Path(temp.name))
        self.addCleanup(s.db.close)
        s.save_agent(dict(project='universe', name='A', role='A', room='bridge'))
        import automations
        automations.save(s, 'universe', dict(name='Stoner 2D animáció generálása', kind='assistant', config=dict(scope='global', prompt='[ORBIT-RUN] készíts stoner animációt'), enabled=True, interval=120, daily_goal=10))
        job = dict(id=s.enqueue(s.rows('SELECT id FROM agents LIMIT 1')[0]['id'], 'x', 'command'))
        with patch.object(ai, 'extract', return_value=('készíts stoner 2D animációt', 'Stoner 2D animáció')):
            reply = ai.create(s, job, 'a stoner 2d animáció automatizáció célja legyen 10 sikeres videó')
        self.assertIn('átállítottam célra: 10 sikeres videó', reply)
        rows = s.rows('SELECT config FROM automations')
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]['config'])['goal']['target'], 10)
