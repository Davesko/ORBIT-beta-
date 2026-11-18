"""Main-chat failures of 11 Nov: open-then-scroll, a typo'd open, a simulation render request, ORBIT's own opens logged."""
import json,tempfile,unittest
from pathlib import Path
from unittest import mock

import computer_agent
import computer
from studio import Studio


class OpenThenScroll(unittest.TestCase):
    def test_the_page_is_opened_before_scrolling(self):
        ran=[];keys=[]
        def call(cmd,**k):
            keys.append((cmd,k));return {'ok':True}
        job={'id':'j'}
        s=mock.Mock()
        with mock.patch.object(computer,'run',lambda s,op,args:ran.append((op,args))),mock.patch('hands.call',call),mock.patch('time.sleep'):
            out=computer_agent.open_then(s,job,'nyisd meg a safariban a telex.hu t és görgess a legaljára az oldalnak.')
        self.assertEqual(ran,[('open_url',{'url':'https://telex.hu','app':'Safari'})])
        self.assertIn(('point',{'app':'Safari','timeout':5}),keys,'the cursor flies to the window')
        self.assertIn(('key',{'combo':'end'}),keys)
        self.assertIn('telex.hu',out)

    def test_a_plain_scroll_is_not_taken(self):
        self.assertIsNone(computer_agent.open_then(mock.Mock(),{'id':'j'},'görgess le kettőt'))

    def test_typos_of_open_are_understood(self):
        self.assertEqual(computer_agent.fast_plan('niysd meg a davinci resolveot')[0]['op'],'open_app')
        self.assertEqual(computer_agent.norm('nyiss egy lapot'),'nyiss egy lapot')


class Logged(unittest.TestCase):
    def test_every_open_is_written_down(self):
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(computer,'_run',lambda *a,**k:''):
            s=mock.Mock();s.root=Path(tmp)
            computer.run(s,'open_app',{'name':'Safari'})
            self.assertIn('open_app\tSafari',(Path(tmp)/'logs/opened.log').read_text())


class SimulationRender(unittest.TestCase):
    def test_a_render_request_goes_to_the_named_projects_simulator(self):
        import commander
        with tempfile.TemporaryDirectory() as tmp:
            s=Studio(Path(tmp));self.addCleanup(s.db.close)
            pid=s.create_project('Koboldtól: Szimgyár')
            aid=s.save_agent(dict(project=pid,name='Szimulátor',role='r',room='bridge',prompt='p',tools=['render_simulation']))
            (s.root/'projects'/pid).mkdir(parents=True,exist_ok=True);(s.root/'projects'/pid/'plan.json').write_text('{}')
            reply=commander.simulation_request(s,{'project':'universe'},'a szimgyárban elkészült terv alapján rendereld le a videót.')
            self.assertIn('Szimgyár',reply)
            job=s.db.execute("SELECT prompt FROM jobs WHERE agent=?",(aid,)).fetchone()
            self.assertIn('plan.json',job[0])
            self.assertIsNone(commander.simulation_request(s,{'project':'universe'},'mikor lesz a következő indítás?'))
