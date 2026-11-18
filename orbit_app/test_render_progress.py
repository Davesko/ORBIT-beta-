import unittest
from render_tools import progress_percent

class RenderProgressTests(unittest.TestCase):
    def test_unknown_timestamp_is_not_a_render_failure(self):
        for value in ('N/A', '', 'nan', 'inf', None):
            with self.subTest(value=value):
                self.assertIsNone(progress_percent({'out_time_us': value}, 10))
        self.assertEqual(progress_percent({'out_time_us':'2500000'},10),25)

    def test_legacy_microsecond_key_and_bounds(self):
        self.assertEqual(progress_percent({'out_time_us':'N/A','out_time_ms':'2500000'},10),25)
        self.assertEqual(progress_percent({'out_time_us':'-100'},10),0)
        self.assertEqual(progress_percent({'out_time_us':'20000000'},10),99)

if __name__ == '__main__':
    unittest.main()

class RenderTimingContractTests(unittest.TestCase):
    def test_complete_subsecond_speech_unit_and_rounding_tolerance_reach_renderer(self):
        import tempfile,json
        from pathlib import Path
        from studio import Studio
        from render_tools import run_render,render_arguments
        from short_style import DEFAULT,duration_allowed
        with tempfile.TemporaryDirectory() as folder:
            s=Studio(Path(folder));self.addCleanup(s.db.close)
            video=s.safe_path('universe','real.mp4');video.write_bytes(b'video fixture')
            words=s.safe_path('universe','real.json');words.write_text(json.dumps(dict(segments=[dict(words=[dict(start=0,end=.9,word='Actual')])])))
            segments=[dict(source_video='real.mp4',start=0,duration=.9,transcript='real.json',sound='pop',sound_delay=.720000000000002),dict(source_video='real.mp4',start=1,duration=49.06,transcript='real.json')]
            style=dict(DEFAULT,min_seconds=50,max_seconds=100,target_seconds=75,length_policy='strict')
            args=dict(source_video='real.mp4',start=0,duration=49.96,requirements=style,segments=segments)
            # Missing media runtime is deliberately beyond ALL request validation.
            with self.assertRaisesRegex(ValueError,'médiafuttató'):run_render(s,dict(project='universe',tools=['render_short']),args,'job')
            self.assertTrue(duration_allowed(49.96,style));self.assertFalse(duration_allowed(49.5,style))
            with self.assertRaises(ValueError):render_arguments(s,'universe',segments[0])
            for invalid in (.1,0,-1,float('nan'),True):
                args['segments'][0]['duration']=invalid
                with self.assertRaisesRegex(ValueError,'duration'):run_render(s,dict(project='universe',tools=['render_short']),args,'job')
