"""Önműködés (owner, 13 Nov): one list of every self-starting process and one master pause, on the Autopilóta page."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import autonomy
from studio import Studio

WEB = Path(__file__).with_name('web')


class Autonomy(unittest.TestCase):
    def setUp(self):
        language = patch('language_bridge.translate_many', side_effect=lambda texts, root: list(texts))
        language.start()
        self.addCleanup(language.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.s.db.close)
        import self_improve
        import autopilot_hub
        self_improve.schema(self.s)
        autopilot_hub.schema(self.s)

    def item(self, eid):
        return next(i for g in autonomy.overview(self.s)['groups'] for i in g['items'] if i['id'] == eid)

    def test_switches_show_their_real_state_and_flip_through_their_own_feature(self):
        import self_improve
        self_improve.set_auto(self.s, True)
        self.assertTrue(self.item('self_improve')['on'])
        self.assertEqual(self.item('self_improve')['power'], 'code')
        autonomy.toggle(self.s, 'self_improve', False)
        self.assertEqual(self_improve.settings(self.s).get('auto'), 'off')
        autonomy.toggle(self.s, 'autopilot', True)
        import autopilot_hub
        self.assertTrue(autopilot_hub.mode(self.s))

    def test_a_project_automation_is_listed_under_its_project_and_can_be_switched_off(self):
        import automations
        automations.schema(self.s)
        pid = self.s.create_project('GTA farm', 'x')
        self.s.db.execute("INSERT INTO automations(id,project,name,kind,config,enabled,interval,plan,runtime_minutes,daily_goal,next_run,last_error,created,archived) "
                          "VALUES('a1',?,'Streamklipek','short','{}',1,180,'{}',60,3,?,'',?,0)", (pid, time.time() + 600, time.time()))
        self.s.db.commit()
        group = next(g for g in autonomy.overview(self.s)['groups'] if g['name'] == 'GTA farm')
        self.assertEqual([i['name'] for i in group['items']], ['Streamklipek'])
        autonomy.toggle(self.s, 'automation:a1', False)
        self.assertEqual(self.s.db.execute("SELECT enabled FROM automations WHERE id='a1'").fetchone()[0], 0)

    def test_the_orbit_comes_first_and_a_project_is_one_group(self):
        import growth
        pid = self.s.create_project('Shorts', 'x')
        growth.schema(self.s)
        self.s.db.execute("INSERT INTO growth_settings VALUES(?,?,?)", (pid, '{"enabled": true}', time.time()))
        self.s.db.commit()
        names = [g['name'] for g in autonomy.overview(self.s)['groups']]
        self.assertEqual(names[0], 'Az ORBIT maga')
        self.assertEqual(names.count('Shorts'), 1)

    def test_the_master_pause_holds_every_self_starting_service_but_not_upkeep(self):
        import scheduler_services
        autonomy.set_paused(self.s, True)
        called = []
        with patch('self_improve.tick', side_effect=lambda s: called.append('self_improve')), patch('autopilot_hub.tick', side_effect=lambda s: called.append('autopilot')), \
                patch('storage_guard.check', side_effect=lambda s: called.append('storage')), patch('growth.tick', side_effect=lambda s: called.append('growth')):
            health = scheduler_services.tick(self.s)
        self.assertIn('storage', called)
        self.assertNotIn('self_improve', called)
        self.assertNotIn('autopilot', called)
        self.assertNotIn('growth', called)
        self.assertTrue(health['autopilot'].get('paused'))
        autonomy.set_paused(self.s, False)
        with patch('self_improve.tick', side_effect=lambda s: called.append('self_improve2')):
            scheduler_services.tick(self.s)
        self.assertIn('self_improve2', called)


    def test_the_main_chat_lists_pauses_and_resumes(self):
        self.assertEqual(autonomy.route('mi fut most magától?')['op'], 'list')
        self.assertEqual(autonomy.route('állíts le minden önműködőt')['op'], 'pause')
        self.assertEqual(autonomy.route('kapcsold vissza az összes önműködőt')['op'], 'resume')
        self.assertIsNone(autonomy.route('készíts egy videót a macskámról'))
        autonomy.act(self.s, dict(op='pause'))
        self.assertTrue(autonomy.paused(self.s))
        self.assertIn('szünetel', autonomy.act(self.s, dict(op='list'))['message'])
        autonomy.act(self.s, dict(op='resume'))
        self.assertFalse(autonomy.paused(self.s))

    def test_it_lives_on_the_autopilot_page_without_a_new_menu_item(self):
        ui = (WEB / 'autopilot_hub_ui.js').read_text(encoding='utf-8')
        self.assertIn("op('autonomy_overview')", ui)
        self.assertIn('Minden önműködő', ui)
        index = (WEB / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('navAutonomy', index)
        from project_apps import TOOL_ROUTES
        self.assertIn(('autonomy_', 'autonomy'), TOOL_ROUTES)
        self.assertIn('autonomy.py', (WEB.parent / 'install.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()


class HaltTests(Autonomy):
    def test_halt_pauses_cancels_everything_and_holds_posts(self):
        pid = self.s.create_project('Teszt', 'x', 'other')
        agent = self.s.db.execute('SELECT id FROM agents WHERE project=? LIMIT 1', (pid,)).fetchone()[0]
        j1 = self.s.enqueue(agent, 'Egy munka', 'assist', payload=dict(task='watch_fetch'), commit=True)
        j2 = self.s.enqueue(agent, 'Másik munka', 'assist', payload=dict(task='szim_make'), commit=True)
        out = autonomy.dispatch(self.s, 'autonomy_halt')
        self.assertTrue(out['paused'])
        self.assertEqual({r['status'] for r in self.s.rows('SELECT status FROM jobs WHERE id IN (?,?)', (j1, j2))}, {'cancelled'})
        self.assertEqual(out['queued'], [])
        self.assertIn('Minden leállítva', out['message'])

    def test_watcher_does_nothing_while_paused(self):
        import stream_watch
        pid = stream_watch.ensure(self.s)
        autonomy.set_paused(self.s, True)
        self.s.db.execute("INSERT INTO stream_moments(id,project,channel,vod,at,start,duration,score,kind,detail,status,created,game) VALUES('m1',?,'xqc','1',1,1,30,20,'funny','{}','found',?,'GTA')", (pid, time.time()))
        self.s.db.commit()
        stream_watch.advance(self.s, pid, stream_watch.settings(self.s, pid), dict(channels={}), time.time())
        self.assertEqual(self.s.db.execute("SELECT status FROM stream_moments WHERE id='m1'").fetchone()[0], 'found')
