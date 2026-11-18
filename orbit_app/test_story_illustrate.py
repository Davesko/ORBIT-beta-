"""Painted panels: every key picture becomes moving footage of exactly the shot's length."""
import json,subprocess,tempfile,unittest
from pathlib import Path

import story_illustrate as panels

RUNTIME=Path.home()/'Library/Application Support/Orbit/media-runtime/bin'


class Panels(unittest.TestCase):
    def test_camera_moves_and_never_holds_still(self):
        seen={panels.framing(m,u,0,1.,u*2) for m in panels.MOVES for u in (0,.5,1)}
        self.assertGreater(len(seen),10)
        zoom,dx,dy=panels.framing('push',1,.1,0,0)
        self.assertGreater(zoom,1.2)

    @unittest.skipUnless((RUNTIME/'ffmpeg').is_file(),'media runtime not installed')
    def test_two_pictures_make_one_clip_of_the_exact_length(self):
        with tempfile.TemporaryDirectory() as d:
            make=f"import cv2,numpy as np\nfor i in range(2):cv2.imwrite('{d}/p%d.png'%i,np.full((1024,576,3),60+i*90,np.uint8))"
            subprocess.run([str(RUNTIME/'python3'),'-c',make],check=True)
            request=dict(ffmpeg=str(RUNTIME/'ffmpeg'),folder=d,seed=3,shots=[dict(frames=30,beat='twist',pictures=[f'{d}/p0.png',f'{d}/p1.png'])])
            subprocess.run([str(RUNTIME/'python3'),str(Path(panels.__file__)),json.dumps(request)],check=True,capture_output=True,cwd=str(Path(panels.__file__).parent))
            probe=subprocess.run([str(RUNTIME/'ffmpeg'),'-i',f'{d}/clip-1.mp4','-map','0:v','-f','null','-'],capture_output=True,text=True).stderr
            import re
            self.assertEqual(re.findall(r'frame=\s*(\d+)',probe)[-1],'30')


class Cutout(unittest.TestCase):
    def test_characters_move_and_the_camera_cuts_often(self):
        import random,story_cutout as cut
        still=cut.body('idle',1.,4.,1,420.,0.,0.)
        walking=[cut.body('walk_in',t/24,4.,1,420.,0.,0.) for t in range(0,48,6)]
        self.assertGreater(len({round(b[0]) for b in walking}),4,'a walk changes position')
        self.assertNotEqual(cut.body('jump',.35,4.,1,420.,0.,0.)[1],0)
        self.assertEqual(cut.pose_of('hit_push',1.5),'shock')
        plan=cut.views(96,dict(lead=[0.]*96,support=[0.]*96),'both',random.Random(2))
        self.assertGreaterEqual(len(plan),3);self.assertTrue(all(a[1]!=b[1] for a,b in zip(plan,plan[1:])))
        import story_animation as sa
        needs=sa.sprite_poses([dict(cast='both',acting=dict(lead='push',support='stare')),dict(cast='lead',acting=dict(lead='run'))])
        self.assertIn(('support','shock'),needs);self.assertEqual(needs[:2],[('lead','idle'),('support','idle')])


if __name__=='__main__':
    unittest.main()
