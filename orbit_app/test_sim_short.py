"""ORBIT's own ball-physics short engine: free-form plans are made safe, goals reachable, and a real MP4 comes out."""
import json,subprocess,tempfile,unittest
from pathlib import Path

import sim_short

MEDIA=Path.home()/'Library/Application Support/Orbit/media-runtime/bin'


class Spec(unittest.TestCase):
    def test_a_free_form_agent_plan_becomes_a_complete_engine_spec(self):
        spec=sim_short.normalize({'simulation_metadata':{'title':'Hex-Shrink Pulse'},'environment':{'type':'Hexagonal_Shrinking_Void'},
                                  'entity_logic':{'initial_count':1,'growth_pattern':'exponential_split','max_balls_threshold':500}})
        self.assertEqual((spec['container']['type'],spec['rule']['what'],spec['end']['type'],spec['balls']['count']),('hexagon','split','ball_count',1))
        self.assertGreater(spec['container']['shrink_per_second'],0)
        self.assertTrue(spec['question'])

    def test_a_reply_without_a_tool_call_still_yields_a_plan(self):
        import sim_tools
        self.assertEqual(sim_tools.plan_from('Here: {"container": {"type": "ring", "gap_degrees": 30}, "end": {"type": "escape"}} done','x')['container']['type'],'ring')
        plan=sim_tools.plan_from('A render kész.','Render the approved Hex-Shrink Pulse concept: one ball splits on every wall hit inside a shrinking hexagon')
        self.assertEqual(plan['title'],'Hex-Shrink Pulse')
        self.assertEqual(sim_short.normalize(plan)['container']['type'],'hexagon')

    def test_nonsense_is_clamped(self):
        spec=sim_short.normalize({'balls':{'count':10**6,'radius':-5,'speed':'fast'},'gravity':1e9,'max_seconds':9999,'container':{'type':'volcano'}})
        self.assertEqual((spec['balls']['count'],spec['balls']['radius'],spec['gravity'],spec['max_seconds']),(40,8,2500,70))
        self.assertIn(spec['container']['type'],sim_short.CONTAINERS)


@unittest.skipUnless((MEDIA/'python3').exists() and (MEDIA/'ffmpeg').exists(),'media runtime')
class Render(unittest.TestCase):
    def test_a_spec_renders_to_a_vertical_mp4_with_sound_and_a_real_ending(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec=Path(tmp)/'s.json';out=Path(tmp)/'s.mp4'
            spec.write_text(json.dumps({'container':{'type':'ring','gap_degrees':40,'rotation_speed':90,'size':.5},'balls':{'count':3,'speed':1200},
                                        'gravity':600,'end':{'type':'escape','value':1},'max_seconds':15}))
            done=subprocess.run([str(MEDIA/'python3'),'-I',str(Path(sim_short.__file__)),str(spec),str(out)],capture_output=True,text=True,timeout=300)
            self.assertEqual(done.returncode,0,done.stderr)
            result=json.loads(done.stdout.strip().splitlines()[-1])
            self.assertNotEqual(result['ending'],'TIME UP')
            probe=subprocess.run([str(MEDIA/'ffmpeg'),'-i',str(out)],capture_output=True,text=True).stderr
            self.assertIn('1080x1920',probe);self.assertIn('Audio: aac',probe)
