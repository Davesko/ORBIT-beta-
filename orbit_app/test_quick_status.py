import json
import tempfile
import time
import unittest
from pathlib import Path

from studio import Studio
from autonomous import role_agents, start
import quick_status


class QuickStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name) / 'orbit')
        self.addCleanup(self.s.db.close)
        for name in ('Echo', 'Scout', 'Lex', 'Reach', 'Vega'):
            self.s.save_agent(dict(project='universe', name=name, role=name, room='bridge', tools=['project_files', 'transcribe_media', 'render_short']))
        roles = role_agents(self.s, 'universe')
        for role in ('producer', 'source'):
            a = self.s.agent(roles[role])
            a['tools'] += ['find_stream_clips', 'download_stream_clip', 'start_short_production']
            self.s.save_agent(a)

    def test_actions_and_small_talk_go_to_the_planner(self):
        for prompt in ('Készíts egy shorts videót IShowSpeedről', 'Szia', 'megcsináltad?', 'indítsd az autopilótát', 'írj egy videó forgatókönyvet'):
            self.assertIsNone(quick_status.answer(self.s, prompt), prompt)

    def test_no_video_yet_is_said_plainly(self):
        self.assertIn('Még nem indult', quick_status.answer(self.s, 'Hogy áll a shorts?'))

    def test_running_failed_and_finished_runs(self):
        run = start(self.s, 'universe', 'IShowSpeed funny highlights')
        first = self.s.claim(('graph',))
        self.s.finish(first, 'ok')
        text = quick_status.answer(self.s, 'Elkészült a videó?')
        self.assertIn('IShowSpeed funny highlights', text)
        self.assertIn('1/8 lépés kész', text)
        self.assertIn('Internetes klipkeresés', text)
        second = self.s.claim(('graph',))
        self.s.finish(second, error='Nincs elérhető forrás')
        self.assertIn('⚠️ Megállt itt: Internetes klipkeresés', quick_status.answer(self.s, 'hol tart a videó'))
        self.s.db.execute("UPDATE jobs SET status='done',error=''")
        self.s.db.execute('UPDATE short_runs SET data=? WHERE id=?', (json.dumps(dict(render=dict(saved='renders/x.mp4'))), run['run']))
        self.s.db.commit()
        self.assertIn('✅ Elkészült · renders/x.mp4', quick_status.answer(self.s, 'kész van a short?'))

    def test_night_and_autopilot_use_the_daily_report(self):
        self.assertIn('Ez történt éjszaka', quick_status.answer(self.s, 'Mi történt éjszaka?'))
        self.assertIn('ORBIT ma', quick_status.answer(self.s, 'Hol tart az autopilóta?'))


if __name__ == '__main__':
    unittest.main()
