import contextlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scene_production
import stickman_studio as studio
import story_contract as contract


def shot(text, place='room'):
    return dict(say=text, kind='medium', place=place, hud='', sound='none',
                actors=[dict(who='main', action='idle', expression='neutral', prop='none', x=.3)])


class Contract(unittest.TestCase):
    def test_ending_mission_and_conditions_invalidate_review(self):
        plan = dict(title='A story', mission='One goal', resolution='Old ending', conditions=[])
        for field in ('mission', 'resolution', 'ending', 'conditions'):
            changed = dict(plan, **{field: 'different'})
            self.assertNotEqual(studio.fingerprint(plan), studio.fingerprint(changed))

    def test_required_dog_and_representative_crowd_survive_editorial_pass(self):
        plan = dict(title='You guide 500 people with a dog', mission='You have 45 minutes.')
        shots = [shot('The crowd queues behind you.'), shot('The dog waits.')]
        contract.finalize(plan, shots)
        self.assertTrue(all(any(a.get('entity_id') == 'story_dog' for a in s['actors']) for s in shots))
        self.assertEqual(shots[0]['crowd']['total'], 500)
        self.assertLessEqual(shots[0]['crowd']['count'], 30)
        self.assertEqual(contract.problems(plan, shots), [])

    def test_elevator_is_not_a_car_and_floor_jump_is_rejected(self):
        plan = dict(title='A dog in an elevator')
        shots = [shot('The car stops on Floor 39.'), shot('The car drops one final floor. The doors open onto the lobby.')]
        shots[0]['moving'] = [dict(kind='vehicle', what='car stops')]
        contract.finalize(plan, shots)
        self.assertEqual(shots[0]['moving'], [])
        self.assertEqual(plan['contract']['status'], 'needs_revision')
        self.assertIn('39', plan['contract']['errors'][0])

    def test_instrument_and_target_are_not_swapped(self):
        shots = [shot('You point the light at the green EXIT sign.'), shot('You use the hotel’s fire hose.')]
        shots[0]['actors'][0]['prop'] = 'sign'
        shots[1]['actors'][0]['tool'] = 'hotel'
        contract.reconcile(shots, {})
        self.assertEqual([s['actors'][0]['prop'] for s in shots], ['flashlight', 'hose'])
        self.assertNotIn('tool', shots[1]['actors'][0])

    def test_explicit_seconds_override_minutes_without_invented_interpolation(self):
        shots = [shot('You have 45 minutes.'), shot('You wait.'), shot('At 38 seconds remaining, you open it.'), shot('You wait.')]
        contract.reconcile(shots, dict(mission='You have 45 minutes.'))
        self.assertEqual([s['hud'] for s in shots], ['MINUTES LEFT: 45', 'MINUTES LEFT: 45', 'SECONDS LEFT: 38', 'SECONDS LEFT: 38'])

    def test_invalid_engineer_index_cannot_become_verified(self):
        plan = dict(title='Story', premise='Room', places=[], chapters=[dict(title='Door', summary='Closed', solution='Open it', steps=[])])
        with patch('inference_gate.lease', return_value=contextlib.nullcontext()), patch.object(studio, 'ask', return_value=dict(chapters=[dict(index=999, problem='bad')])):
            studio.engineer_review(SimpleNamespace(root=Path('/tmp')), {}, plan)
        self.assertEqual(plan['engineering']['status'], 'invalid_review')

    def test_engineer_fix_resynchronizes_old_ending_before_verification(self):
        plan = dict(title='Rescue', premise='Stuck in a lift', mission='Move it manually', resolution='Use a hose as lever',
                    ending='The hose works', places=[], chapters=[dict(title='Brake', summary='Stuck', solution='Use a hose', steps=[])])
        fix = dict(chapters=[dict(index=0, problem='Wrong tool', solution='Use the intercom and wait for a technician.',
                                  steps=[dict(do='You press the button.', result='It connects.'),
                                         dict(do='You describe the problem.', result='A technician is sent.'),
                                         dict(do='You wait inside.', result='The technician arrives.')])])
        context = dict(title='Wait for rescue', premise='You are stuck in a lift.', mission='You must contact the technician.',
                       goal='Get rescued by the technician.', question='Will the technician arrive?',
                       resolution='The technician opens the door.', ending='You leave with the technician.', conditions=[])
        with patch('inference_gate.lease', return_value=contextlib.nullcontext()), patch.object(studio, 'ask', side_effect=[fix, context, dict(chapters=[])]) as ask:
            studio.engineer_review(SimpleNamespace(root=Path('/tmp')), {}, plan)
        self.assertEqual(ask.call_count, 3)
        self.assertNotIn('hose', plan['resolution'])
        self.assertEqual(plan['engineering']['status'], 'verified')

    def test_no_pose_without_target_counts_as_performed(self):
        s = shot('You pull the lever.')
        s['actors'][0]['action'] = 'pull'
        self.assertEqual(studio.event_report(dict(shots=[s]))['performed'], 0)

    def test_measured_scene_counts_as_performed_only_with_contact_evidence(self):
        s = shot('You press the red button.')
        contract.finalize({}, [s])
        s.update(start=0, end=2)
        scene_production.compile_shots([s])
        plan = dict(shots=[s], scene_evidence=dict(scenes={'scene:0': dict(passed=True, contact_samples=20)}))
        self.assertEqual(studio.event_report(plan)['performed'], 1)
        plan['scene_evidence']['scenes']['scene:0']['contact_samples'] = 0
        self.assertEqual(studio.event_report(plan)['performed'], 0)

    def test_alignment_retains_interpolated_confidence_and_no_overlap(self):
        text = 'You press the button now.'
        words = [dict(w=w, s=i*.2, e=i*.2+.25, ok=i != 2) for i,w in enumerate(text.split())]
        out, basis = studio.spoken_words(text, dict(out='line'), 0, 2, 1,
                                        dict(line=dict(coverage=.8, words=words)))
        self.assertEqual(basis, 'partial')
        self.assertEqual(out[2]['basis'], 'interpolated')
        self.assertTrue(all(a['e'] <= b['s'] for a,b in zip(out,out[1:])))


class Production(unittest.TestCase):
    def test_controlled_state_persists_and_real_joints_follow_targets(self):
        import numpy as np
        import cv2
        import stickman_rig as rig
        for width, height in ((640, 360), (360, 640)):
            for action in scene_production.SUPPORTED:
                shots = [dict(start=i*2, end=(i+1)*2, controlled=dict(action=action, target='control')) for i in range(2)]
                scene_production.compile_shots(shots)
                self.assertEqual(shots[1]['controlled']['state_before'], shots[0]['controlled']['state_after'])
                records = {}
                for s in shots:
                    for n in range(60):
                        image, measured = scene_production.draw(np, cv2, np.zeros((height,width,3),np.uint8), s,
                                                                dict(main=rig.MAIN), n/30, 30)
                        scene_production.accumulate(records, measured)
                self.assertTrue(all(r['passed'] for r in records.values()), records)

    def test_normal_renderer_records_controlled_scene_evidence(self):
        import stickman_render
        import stickman_rig as rig
        ffmpeg = Path.home()/'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'
        if not ffmpeg.exists():
            self.skipTest('media runtime not installed')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            s = shot('You press the red button.')
            contract.finalize({}, [s])
            s.update(start=0, end=1.5)
            result = stickman_render.render(dict(width=320, height=480, fps=30, shots=[s],
                                                designs=dict(main=rig.MAIN), ffmpeg=str(ffmpeg),
                                                output=str(folder/'video.mp4'), quality_output=str(folder/'quality.json')))
            evidence = json.loads((folder/'quality.json').read_text())
            self.assertTrue((folder/'video.mp4').stat().st_size > 1000)
            self.assertTrue(evidence['scenes']['scene:0']['passed'])
            self.assertEqual(result['frames'], 45)


if __name__ == '__main__':
    unittest.main()
