import unittest

import story_mocap
import story_puppet


BVH = """HIERARCHY
ROOT Hips
{
	OFFSET 0 0 0
	CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation
	JOINT Spine
	{
		OFFSET 0 2 0
		CHANNELS 3 Zrotation Yrotation Xrotation
		End Site
		{
			OFFSET 0 1 0
		}
	}
}
MOTION
Frames: 2
Frame Time: 0.5
0 10 0 0 0 0 0 0 0
1 10 0 90 0 0 0 0 0
"""


class MocapParse(unittest.TestCase):
    def test_parse_reads_joints_and_frames(self):
        joints, frames, step = story_mocap.parse(BVH)
        self.assertEqual([j['name'] for j in joints], ['Hips', 'Spine', 'Spine_end'])
        self.assertEqual(joints[1]['parent'], 0)
        self.assertEqual(len(frames), 2)
        self.assertEqual(step, .5)

    def test_tracks_mirror_swaps_sides(self):
        row = [10, 20, 30, 40, -50, 60, 5, 0, 3, 8, 2]
        tracks = story_mocap.Tracks(dict(keys=list(story_mocap.KEYS), gestures=dict(talk=[dict(frames=[row, row])])))
        right = tracks.gesture('talk', 0, 1)
        left = tracks.gesture('talk', 0, -1)
        self.assertEqual(right['lx'], 10)
        self.assertEqual(left['lx'], -30)
        self.assertEqual(left['rx'], -10)
        self.assertEqual(left['lfy'], 0)
        self.assertEqual(left['lean'], -8)
        self.assertIsNone(tracks.gesture('faint', 0, 1))


class RigUsesMocap(unittest.TestCase):
    def tearDown(self):
        story_puppet.TRACKS = None

    def test_captured_gesture_drives_the_hands(self):
        row = [-200, 40, 210, 30, -70, 70, 0, 0, 0, 5, 0]
        story_puppet.TRACKS = story_mocap.Tracks(dict(keys=list(story_mocap.KEYS), gestures=dict(talk=[dict(frames=[row] * 5)], shrug=[dict(frames=[row] * 5)])))
        rig = story_puppet.Rig(story_puppet.design('man in blue hoodie', (0, 0, 0)), 320., 1)
        rig.update('shrug', 1., 3., 1., 0.)
        self.assertTrue(rig.mocap)
        self.assertLess(rig.values['lx'], -160)          # the captured shrug shows (at 3/4 size, 13 Nov)
        talker = story_puppet.Rig(story_puppet.design('man in blue hoodie', (0, 0, 0)), 320., 1)
        talker.update('talk', 1., 3., 1., 0.)
        self.assertTrue(talker.mocap)
        self.assertGreater(talker.values['lx'], -190)     # talking is a smaller version of the captured gesture (13 Nov)

    def test_without_tracks_the_hand_made_pose_stays(self):
        rig = story_puppet.Rig(story_puppet.design('man in blue hoodie', (0, 0, 0)), 320., 1)
        rig.update('talk', 1., 3., 1., 0.)
        self.assertFalse(rig.mocap)


class StudioLook(unittest.TestCase):
    def test_rig_is_the_default_again(self):
        from story_animation import studio_look
        self.assertEqual(studio_look('Készíts egy stickman történetet'), 'rig')
        self.assertEqual(studio_look('festett kivágott szereplőkkel'), 'cutout')
        self.assertEqual(studio_look('állóképes panelekkel'), 'panels')


if __name__ == '__main__':
    unittest.main()
