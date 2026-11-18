"""The Frame agent's character sheet and start frames are visible in its work panel while it renders."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio import Studio

FFMPEG = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'
NODE = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/node'


@unittest.skipUnless(FFMPEG.is_file(), 'needs the ORBIT ffmpeg')
class PreviewTests(unittest.TestCase):
    def test_sheet_and_frames_are_listed_in_order_with_verdicts_and_survive_the_render(self):
        import story_animation as sa
        with tempfile.TemporaryDirectory() as d:
            s = Studio(Path(d));self.addCleanup(s.db.close)
            pid = s.create_project('YouTube Shorts', 'Test');team = sa.install_team(s, pid)
            run = s.enqueue_graph(pid, team['agents'][0], 'Készíts egy vicces stickman videót')['run']
            job = dict(s.rows("SELECT * FROM jobs WHERE json_extract(payload,'$.story_step')='render'")[0])
            png = Path(d) / 'frame.png'
            subprocess.run([str(FFMPEG), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=purple:s=480x832', '-frames:v', '1', str(png)], check=True)
            sa.preview(s, job, run, FFMPEG, png, 'shot-2', '2/6. jelenet nyitóképe', dict(passed=False, problems=['Dot hair'], attempt='free3'))
            sa.preview(s, job, run, FFMPEG, png, 'anchor', 'Karakterlap · szereplők és helyszín')
            sa.preview(s, job, run, FFMPEG, png, 'shot-1', '1/6. jelenet nyitóképe', dict(passed=True, problems=[], attempt='free0'))
            sa.preview(s, job, run, FFMPEG, png, 'shot-1', '1/6. jelenet nyitóképe', dict(passed=True, problems=[], attempt='free1'))  # redrawn: replaced
            frames = sa.previews(s, pid, job['id'])
            self.assertEqual([f['key'] for f in frames], ['anchor', 'shot-1', 'shot-2'])
            self.assertTrue(frames[0]['image'].startswith('data:image/jpeg;base64,'))
            self.assertEqual(frames[1]['check']['attempt'], 'free1');self.assertFalse(frames[2]['check']['passed'])
            self.assertLess(len(frames[0]['image']), 60000)  # small thumbnails, the panel refreshes often
            from bridge import dispatch
            self.assertEqual(len(dispatch(dict(action='story_frames', project=pid, id=job['id']), s)['frames']), 3)

    def test_other_jobs_and_unsafe_manifest_entries_show_nothing(self):
        import story_animation as sa
        with tempfile.TemporaryDirectory() as d:
            s = Studio(Path(d));self.addCleanup(s.db.close)
            pid = s.create_project('YouTube Shorts', 'Test');team = sa.install_team(s, pid)
            run = s.enqueue_graph(pid, team['agents'][0], 'Készíts egy vicces stickman videót')['run']
            job = s.rows("SELECT * FROM jobs WHERE json_extract(payload,'$.story_step')='render'")[0]
            folder = s.safe_path(pid, f'runs/{run}/previews');folder.mkdir(parents=True)
            (Path(d) / 'secret.jpg').write_bytes(b'x')
            (folder / 'manifest.json').write_text(json.dumps([dict(key='anchor', label='x', file='../../../../secret.jpg')]))
            self.assertEqual(sa.previews(s, pid, job['id']), [])
            with self.assertRaises(ValueError):sa.previews(s, pid, 'nope')


@unittest.skipUnless(NODE.is_file(), 'needs node')
class PanelScriptTests(unittest.TestCase):
    def test_progress_panel_script_parses_and_calls_the_gallery(self):
        source = Path(__file__).with_name('web') / 'progress_ui.js'
        subprocess.run([str(NODE), '--check', str(source)], check=True)
        text = source.read_text()
        self.assertIn("storyFrames(root,d,job.id)", text);self.assertIn("call('story_frames'", text)


if __name__ == '__main__':
    unittest.main()
