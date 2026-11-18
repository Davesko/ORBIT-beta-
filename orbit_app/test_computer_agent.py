import json
import time
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import computer_agent as agent
import hands
from studio import Studio

APPS = {'google chrome': 'Google Chrome', 'safari': 'Safari', 'spotify': 'Spotify', 'notes': 'Notes'}


class FastPlanTests(unittest.TestCase):
    def plan(self, prompt):
        return agent.fast_plan(prompt, APPS)

    def test_open_browser_with_site_typo_and_suffixes(self):
        self.assertEqual(self.plan('nyisd meg a google chormeot és nyisd meg benne a youtubeot'), [dict(op='open_url', args=dict(url='https://www.youtube.com', app='Google Chrome'))])
        self.assertEqual(self.plan('nyisd meg a youtubeot safariban'), [dict(op='open_url', args=dict(url='https://www.youtube.com', app='Safari'))])
        self.assertEqual(self.plan('nyisd meg a telex.hu-t'), [dict(op='open_url', args=dict(url='https://telex.hu'))])
        self.assertEqual(self.plan('nyisd meg a spotifyt'), [dict(op='open_app', args=dict(name='Spotify'))])
        self.assertEqual(self.plan('nyisd meg a jegyzeteket'), [dict(op='open_app', args=dict(name='Notes'))])

    def test_complex_or_internal_requests_are_not_fast(self):
        self.assertIsNone(self.plan('nyisd meg a youtubeot és keress rá a macskákra'))
        self.assertIsNone(self.plan('nyisd meg a valamiprogramot amit nem ismerek'))
        self.assertFalse(agent.wants('nyisd meg az orbit projektet'))
        self.assertFalse(agent.wants('készíts egy shorts videót'))
        self.assertTrue(agent.wants('kattints a bejelentkezés gombra'))


class FakeHands:
    """A loopback stand-in for ORBIT Hands."""
    def __init__(self, replies):
        self.replies = replies
        self.seen = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            data = b''
            while not data.endswith(b'\n'):
                data += c.recv(65536)
            req = json.loads(data)
            self.seen.append(req)
            c.sendall((json.dumps(self.replies(req)) + '\n').encode())
            c.close()


class OperateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        aid = self.s.save_agent(dict(project='universe', name='A', role='A', room='bridge'))
        self.job = dict(id=self.s.enqueue(aid if isinstance(aid, str) else aid['id'], 'x', 'command'))

    def serve(self, replies):
        fake = FakeHands(replies)
        self.addCleanup(fake.sock.close)
        p = patch.object(hands, 'PORT', fake.port)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def screen(self, req):
        if req['cmd'] == 'elements':
            return dict(ok=True, app='Google Chrome', window='YouTube', elements=[dict(i=0, role='TextField', label='Keresés', x=400, y=90, w=300, h=30, press=False), dict(i=1, role='Button', label='Vásárlás', x=500, y=300, w=80, h=30, press=True)])
        return dict(ok=True)

    def test_look_act_verify_loop_until_done(self):
        fake = self.serve(self.screen)
        answers = iter([dict(action='click', index=0, why='keresőmező'), dict(action='type', text='macskák'), dict(action='key', combo='return'), dict(action='done', say='Rákerestem a macskákra.')])
        with patch.object(agent, 'resolve_goal', return_value=None), patch.object(agent, 'target_app', return_value=None), patch.object(agent, '_ask', side_effect=lambda *a: next(answers)), patch('time.sleep'):
            reply = agent.operate(self.s, self.job, 'keress rá a youtube-on a macskákra')
        self.assertIn('Rákerestem', reply)
        self.assertEqual([r['cmd'] for r in fake.seen if r['cmd'] not in ('elements', 'ocr', 'show')], ['click', 'type', 'key'])

    def test_final_buttons_and_secrets_stop_for_the_owner(self):
        self.serve(self.screen)
        with patch.object(agent, 'resolve_goal', return_value=None), patch.object(agent, '_ask', return_value=dict(action='click', index=1)), patch('time.sleep'):
            self.assertIn('te nyomd meg', agent.operate(self.s, self.job, 'vedd meg'))
        with patch.object(agent, 'resolve_goal', return_value=None), patch.object(agent, '_ask', return_value=dict(action='type', text='jelszó: titok123')), patch('time.sleep'):
            self.assertIn('nem gépelek', agent.operate(self.s, self.job, 'lépj be'))

    def test_a_show_me_a_site_request_opens_the_right_page_directly(self):
        self.serve(self.screen)
        with patch.object(agent, 'resolve_goal', return_value=dict(url='https://trends.google.com/trending?geo=HU', app='Safari', say='Megnyitottam a Google Trends oldalt.')), patch('computer.run') as run:
            reply = agent.operate(self.s, self.job, 'keress egy weboldalt a legfrissebb trendekkel safariban')
        self.assertIn('trends.google.com', reply)
        self.assertEqual(run.call_args.args[1:], ('open_url', dict(url='https://trends.google.com/trending?geo=HU', app='Safari')))

    def test_repeating_an_action_without_effect_stops_and_typing_can_submit(self):
        fake = self.serve(self.screen)
        with patch.object(agent, 'resolve_goal', return_value=None), patch.object(agent, 'target_app', return_value=None), patch.object(agent, '_ask', return_value=dict(action='type', text='trendek', submit=True)), patch('time.sleep'):
            reply = agent.operate(self.s, self.job, 'keress trendeket')
        # The same text is never typed twice: the second identical step ends the typing part.
        self.assertIn('Beírtam a szöveget', reply)
        self.assertEqual([r['cmd'] for r in fake.seen].count('type'), 1)
        with patch.object(agent, 'resolve_goal', return_value=None), patch.object(agent, 'target_app', return_value=None), patch.object(agent, '_ask', return_value=dict(action='click', index=0)) as ask, patch('time.sleep'):
            reply = agent.operate(self.s, self.job, 'kattints a keresőre')
        self.assertIn('nem hozott változást', reply)
        self.assertIn('no - try something different', ask.call_args.args[5])
        self.assertEqual([r.get('combo') for r in fake.seen if r['cmd'] == 'key'][:1], ['return'])

    def test_missing_permission_names_it_and_opens_settings(self):
        fake = self.serve(lambda req: dict(ok=False, error='permission:accessibility') if req['cmd'] == 'elements' else dict(ok=True))
        with self.assertRaises(hands.HandsError) as ctx:
            hands.look()
        self.assertIn('Kisegítő lehetőségek', str(ctx.exception))
        self.assertIn('request', [r['cmd'] for r in fake.seen])

    def test_chat_runs_open_requests_without_the_planner(self):
        import commander
        with patch('computer.run', return_value=dict(opened=True)) as run, patch('computer_agent.installed_apps', return_value=APPS):
            jid = commander.enqueue(self.s, 'universe', 'nyisd meg a google chromeot és benne a youtubeot', global_mode=True)
            reply = commander.run(self.s, dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()))
        self.assertIn('youtube.com', reply)
        self.assertEqual(run.call_args.args[1:], ('open_url', dict(url='https://www.youtube.com', app='Google Chrome')))


if __name__ == '__main__':
    unittest.main()


class SmarterRoutingTests(unittest.TestCase):
    def test_own_pages_and_file_tasks_are_not_guessed_as_apps(self):
        apps = dict(APPS, ollama='Ollama', photos='Photos')
        self.assertIsNone(agent.fast_plan('akkor nyisd meg az instagram oldalamat', apps))
        self.assertIsNone(agent.fast_plan('nyisd meg az asztalomon a legnagyobb méretű képet', apps))
        self.assertEqual(agent.fast_plan('nyisdd meg a safarit', apps), [dict(op='open_app', args=dict(name='Safari'))])

    def test_a_named_mac_app_is_a_computer_task_even_with_projekt(self):
        with patch.object(agent, 'installed_apps', return_value={'davinci resolve': 'DaVinci Resolve'}):
            self.assertTrue(agent.wants('nyisdd meg a davincit és exportálj egy üres projektben egy fekete videót'))
            self.assertFalse(agent.wants('nyisd meg az orbit projektet'))
            self.assertFalse(agent.wants('készíts egy shorts videót'))

    def test_find_files_sorts_by_size_or_date_in_personal_folders_only(self):
        with tempfile.TemporaryDirectory() as tmp, patch('pathlib.Path.home', return_value=Path(tmp)):
            desk = Path(tmp) / 'Desktop'
            desk.mkdir()
            (desk / 'kicsi.jpg').write_bytes(b'x' * 10)
            (desk / 'nagy.png').write_bytes(b'x' * 5000)
            (desk / 'level.pdf').write_bytes(b'x' * 100)
            self.assertTrue(agent.find_files('~/Desktop', 'image', 'largest')[0]['path'].endswith('nagy.png'))
            self.assertEqual(len(agent.find_files('~/Desktop', 'pdf')), 1)
            with self.assertRaises(ValueError):
                agent.find_files('/etc', 'any')

    def test_open_and_analyse_reads_the_page(self):
        s = unittest.mock.Mock()
        with patch.object(agent, 'resolve_goal', return_value=dict(url='https://example-studio.art', app=None, say='Megnyitottam.')), \
             patch('computer.run'), patch.object(agent, '_wave'), patch.object(agent, 'analyse_page', return_value='1. A nyitóoldal lassú.') as analyse:
            reply = agent.operate(s, dict(id='j'), 'nyisd meg a example-studio.art oldalamat és elemezd mit kéne javítani')
        self.assertIn('A nyitóoldal lassú', reply)
        analyse.assert_called_once()


class MemoryAndPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)

    def test_a_correction_fixes_the_fact_and_drops_the_notes(self):
        import commander
        for key, text in (('site', 'The user runs a website called example-studoi.art.'), ('note1', 'A helyes weboldal címe: example-studio.art. A example-studoi.art hibás cím.'), ('name', 'A felhasználó neve Anna.')):
            commander.memory_save(self.s, dict(key=key, content=text))
        result = commander.memory_correct(self.s, dict(wrong='example-studoi.art', right='example-studio.art'))
        left = {r['key']: r['content'] for r in self.s.rows('SELECT key,content FROM assistant_memory')}
        self.assertEqual(left['site'], 'The user runs a website called example-studio.art.')
        self.assertNotIn('note1', left)
        self.assertIn('name', left)
        self.assertIn('note1', result['changed'])

    def test_steps_without_a_type_do_not_fail_the_plan(self):
        import commander
        actions = commander.prepare(self.s, 'universe', [dict(url='https://www.instagram.com'), dict(foo=1)], global_mode=True)
        self.assertEqual(actions, [dict(type='computer', op='open_url', args=dict(url='https://www.instagram.com'))])


class ChatLogFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)

    def test_write_task_composes_once_opens_a_new_note_and_verifies(self):
        calls = []
        state = dict(text='')

        def fake(cmd, timeout=30, **a):
            calls.append((cmd, a))
            if cmd == 'type':
                state['text'] = a['text']
            if cmd == 'elements':
                return dict(ok=True, elements=[dict(i=3, role='TextArea', label=state['text'], x=1, y=1, w=400, h=300, focused=True)])
            return dict(ok=True)
        with patch('hands.call', side_effect=fake), patch('computer.run'), patch.object(agent, 'compose', return_value='Szia! Ez egy rövid bemutatkozás.'), patch('time.sleep'):
            reply = agent.write_task(self.s, dict(id='j'), 'nyisd meg a jegyzet appot és írj bele egy rövid üzenetet')
        self.assertIn('Beírtam egy új jegyzetbe', reply)
        self.assertEqual([c for c, _ in calls].count('type'), 1)
        self.assertIn(('key', dict(combo='cmd+n')), calls)

    def test_quick_scroll_and_folder_need_no_model(self):
        with patch('hands.call', return_value=dict(ok=True)) as call, patch.object(agent, 'target_app', return_value='Safari'):
            self.assertIn('2×', agent.fast_scroll(self.s, dict(id='j'), 'görgess lejjebb 2 nagy görgetést'))
            self.assertEqual(call.call_args.kwargs['times'], 6)
            self.assertIn('aljára', agent.fast_scroll(self.s, dict(id='j'), 'görgess le a lap aljára'))
            self.assertEqual(call.call_args.kwargs['combo'], 'end')
        with tempfile.TemporaryDirectory() as tmp, patch('pathlib.Path.home', return_value=Path(tmp)), patch('computer.run') as run:
            (Path(tmp) / 'Desktop' / 'Astroshoot').mkdir(parents=True)
            self.assertIn('Astroshoot', agent.fast_folder(self.s, dict(id='j'), 'navigálj számítógépem asztalán az ASTROSHOOT mappára'))
            self.assertEqual(run.call_args.args[1], 'open_file')

    def test_only_explicit_requests_operate_the_mac(self):
        mission = ('Valósítsd meg most ezt a fejlesztést a(z) „GTA6 farm” projektben: A Shorts-gyártás ne álljon meg itt: Kész videó '
                   'ellenőrzése. Cél: ez a lépés állította meg a legtöbb videót. Olvasd el a naplót, és nézd meg, mit kell javítani.')
        self.assertFalse(agent.wants(mission));self.assertFalse(agent.asked(mission));self.assertFalse(agent.wants_web(mission))
        self.assertFalse(agent.wants('Ez a lépés a legfontosabb a forgatókönyvben, mit gondolsz, hogyan legyen jobb a videók hangja és a zene?'))
        for plain in ('mi a véleményed a mai videóról?', 'írj egy rövid verset a macskákról', 'mennyi az idő Tokióban?'):
            self.assertFalse(agent.asked(plain), plain)
        for explicit in ('nyisd meg a youtubeot', 'kattints a lejátszás gombra', 'írj bele a jegyzetbe egy listát', 'görgess le'):
            self.assertTrue(agent.asked(explicit), explicit)
        self.assertTrue(agent.wants('mi van ezen az oldalon?'))

    def test_planner_computer_actions_need_an_explicit_request(self):
        import commander
        steps = [dict(type='computer', op='open_url', args=dict(url='https://www.youtube.com')), dict(type='computer', op='front', args={})]
        self.assertEqual([a['op'] for a in commander.prepare(self.s, 'universe', steps, global_mode=True, user_request='mi a legújabb hír a YouTube-ról?')], ['front'])
        self.assertEqual([a['op'] for a in commander.prepare(self.s, 'universe', steps, global_mode=True, user_request='nyisd meg a youtube-ot')], ['open_url', 'front'])

    def test_opening_a_page_shows_no_pointer(self):
        with patch.object(agent, '_wave', side_effect=AssertionError('no cursor for an open')), patch('computer.run') as run:
            self.assertIn('youtube', agent._handle(self.s, dict(id='j'), 'nyisd meg a youtubeot').lower())
        self.assertEqual(run.call_args.args[1], 'open_url')

    def test_screen_questions_and_requests_route_right(self):
        import quick_status
        self.assertTrue(agent.wants('mit tud ez a github projekt?'))
        self.assertIsNone(quick_status.answer(self.s, 'Hogyha elkészült egy tartalom akkor a videót is küldd el telegramon.'))

    def test_improvement_auto_mode_queues_one_task_a_night(self):
        import self_improve
        self.s.save_agent(dict(project='universe', name='A', role='A', room='bridge'))
        self_improve.save(self.s, 'orbit', [dict(title='Gyorsabb chat', why='Kevesebb várakozás.', evidence='5 lassú válasz', size='S')], 'measured')
        night = time.mktime(time.strptime('2026-11-09 02:00', '%Y-%m-%d %H:%M'))
        self.assertFalse(self_improve.auto_apply(self.s, night))
        self_improve.set_auto(self.s, True)
        self.assertTrue(self_improve.auto_apply(self.s, night))
        self.assertFalse(self_improve.auto_apply(self.s, night + 60))
        prompt = self.s.db.execute("SELECT prompt FROM jobs WHERE kind='command'").fetchone()[0]
        self.assertIn('Valósítsd meg most', prompt)


class ControlIndicatorTests(unittest.TestCase):
    def test_menu_bar_is_told_begin_and_end_and_stop_ends_the_task(self):
        seen = []

        def fake(cmd, timeout=30, **a):
            seen.append(cmd)
            if cmd == 'activate':
                raise hands.Stopped('Leállítottad a gépvezérlést (Esc vagy a menüsor). Nem folytatom.')
            return dict(ok=True)
        with patch('hands.call', side_effect=fake), patch.object(agent, 'fast_scroll', return_value=None), patch.object(agent, 'fast_folder', return_value=None), \
             patch.object(agent, 'fast_plan', return_value=None), patch.object(agent, 'resolve_goal', return_value=None), patch.object(agent, 'write_task', return_value=None), \
             patch.object(agent, 'target_app', return_value='Safari'):
            reply = agent.handle(unittest.mock.Mock(), dict(id='j'), 'kattints a gombra a Safariban')
        self.assertIn('Leállítottad', reply)
        self.assertEqual(seen[0], 'begin')
        self.assertEqual(seen[-1], 'end')

    def test_a_stopped_reply_raises_stopped(self):
        fake = FakeHands(lambda req: dict(ok=False, error='stopped'))
        self.addCleanup(fake.sock.close)
        with patch.object(hands, 'PORT', fake.port):
            with self.assertRaises(hands.Stopped):
                hands.call('click', index=1)

    def test_style_must_be_known(self):
        with self.assertRaises(hands.HandsError):
            hands.dispatch(None, 'hands_style', dict(name='egér'))
