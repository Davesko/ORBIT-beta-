import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

import story_animation as sa

FFMPEG = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'


class CleanRenderTests(unittest.TestCase):
    def test_clean_profile_keeps_each_scene_whole(self):
        plan = dict(scenes=[dict(frames=132, beat='setup'), dict(frames=40, beat='twist')])
        self.assertEqual([s['parts'] for s in sa.shots_for(plan)], [2, 2, 1])
        self.assertEqual([s['frames'] for s in sa.shots_for(plan, limit=10**6)], [132, 40])

    def test_hold_pads_the_last_pose(self):
        shot = dict(frames=48, beat='setup')
        self.assertIn('tpad=stop_mode=clone', sa.edit_filter(shot, True, hold=True))
        self.assertNotIn('tpad', sa.edit_filter(shot, True))
        twist = dict(frames=48, beat='twist', scene_frames=48, scene_offset=0)
        self.assertTrue(sa.edit_filter(twist, True, hold=True).startswith('[0:v]tpad'))

    def test_border_drift_flags_a_melting_background(self):
        import story_motion
        ref = np.full((288, 160), 120, np.uint8)
        calm = [ref.copy() for _ in range(4)]
        noisy = [np.clip(ref + np.random.default_rng(i).integers(-60, 60, ref.shape), 0, 255).astype(np.uint8) for i in range(4)]
        self.assertLess(np.mean(story_motion.drift(calm, ref)), story_motion.DRIFT_LIMIT)
        self.assertGreater(np.mean(story_motion.drift(noisy, ref)), story_motion.DRIFT_LIMIT)

    def test_presence_drops_when_the_character_leaves(self):
        import story_motion
        stage = np.full((288, 160), 150, np.uint8)
        with_cast = stage.copy(); with_cast[100:220, 60:100] = 20
        self.assertGreater(story_motion.presence(with_cast, 150.0), .05)
        self.assertLess(story_motion.presence(stage, 150.0), story_motion.presence(with_cast, 150.0) * story_motion.STAYS)

    @unittest.skipUnless(FFMPEG.is_file(), 'needs the ORBIT ffmpeg')
    def test_still_fallback_has_the_exact_frame_count(self):
        with tempfile.TemporaryDirectory() as d:
            ref, out = Path(d) / 'r.png', Path(d) / 'o.mp4'
            subprocess.run([str(FFMPEG), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=purple:s=480x832', '-frames:v', '1', str(ref)], check=True)
            sa.still_motion(FFMPEG, ref, out, 49, (480, 832))
            probe = subprocess.run([str(FFMPEG), '-v', 'error', '-i', str(out), '-f', 'null', '-progress', 'pipe:1', '-'], capture_output=True, text=True).stdout
            self.assertIn('frame=49', probe)


if __name__ == '__main__':
    unittest.main()
