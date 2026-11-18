import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from edit_contract import compile_request,caption_pages


class EditContractTests(unittest.TestCase):
    def request(self):
        return dict(duration=3,layout='cover',segments=[dict(source='real.mp4',start=2,duration=1.333,beat='hook',evidence=dict(unit_id=4)),dict(source='real.mp4',start=8,duration=1.667,beat='payoff')],words=[dict(start=0,end=.7,text='True'),dict(start=.8,end=1.3,text='hook.'),dict(start=2,end=2.8,text='Payoff.')],caption_preset=dict(box=[108,1320,864,1580],anchor=[486,1560],font_size=76))

    def test_cumulative_frames_and_evidence_are_preserved(self):
        c=compile_request(self.request())
        self.assertEqual(c['output']['duration_frames'],90)
        self.assertEqual(c['timeline'][0]['end_frame'],c['timeline'][1]['start_frame'])
        self.assertEqual(c['timeline'][-1]['end_frame'],90)
        self.assertEqual(c['timeline'][0]['evidence']['unit_id'],4)
        self.assertEqual(c['timeline'][1]['source_in_seconds'],8)
        self.assertFalse(c['policy']['arbitrary_zoom'])

    def test_invalid_timing_and_unsafe_caption_box_rejected(self):
        for start,end in [(float('nan'),1),(True,1),(-1,1),(1,1),(2,4)]:
            r=self.request();r['words']=[dict(start=start,end=end,text='Actual')]
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):compile_request(r)
        r=self.request();r['caption_preset']['anchor']=[486,1900]
        with self.assertRaises(ValueError):compile_request(r)

    def test_words_are_output_timed_and_untrusted_markup_is_plain_text(self):
        r=self.request();r['words'][0]['text']='{\\pos(1,1)}<script>hello</script>'
        c=compile_request(r);words=[w for p in c['captions']['pages'] for w in p['words']]
        self.assertEqual(words[0]['text'],'hello');self.assertEqual(words[0]['start_frame'],0)
        self.assertTrue(all(w['end_frame']<=90 for w in words))
        self.assertEqual(len(r['words']),3)

    def test_unordered_words_do_not_silently_animate_the_wrong_time(self):
        r=self.request();r['words'].reverse()
        with self.assertRaises(ValueError):compile_request(r)

    def test_caption_pages_do_not_leak_the_next_sentence_into_the_hook(self):
        c=compile_request(self.request());texts=[' '.join(w['text'] for w in p['words']) for p in c['captions']['pages']]
        self.assertIn('True hook.',texts);self.assertIn('Payoff.',texts)

    def test_contract_is_a_serializable_plan_not_code(self):
        c=compile_request(self.request());self.assertEqual(json.loads(json.dumps(c))['schema_version'],'orbit.edit.v1')


class MediaExtensionTests(unittest.TestCase):
    def test_local_narration_validation_bounds(self):
        from narration import validate
        self.assertEqual(validate(dict(text='English narration'))['voice'],3)
        for args in (dict(text=''),dict(text='a'*1801),dict(text='Hello',voice=True),dict(text='Hello',voice=28),dict(text='Hello',speed=float('nan'))):
            with self.assertRaises(ValueError):validate(args)

    def test_stock_urls_cannot_redirect_to_internal_or_arbitrary_hosts(self):
        from stock_media import media_url
        for url in ('http://videos.pexels.com/a','https://127.0.0.1/a','https://videos.pexels.com.evil.test/a','https://user@videos.pexels.com/a','https://videos.pexels.com:8080/a'):
            with self.assertRaises(ValueError):media_url(url)
        self.assertEqual(media_url('https://videos.pexels.com/video-files/a.mp4'),'https://videos.pexels.com/video-files/a.mp4')

    def test_missing_stock_key_is_not_replaced_with_unrelated_footage(self):
        from stock_media import search
        with tempfile.TemporaryDirectory() as folder:
            s=MagicMock(root=Path(folder))
            with self.assertRaisesRegex(ValueError,'API-kulcs'):search(s,'ocean')

    def test_render_quality_rejects_decode_error(self):
        from render_quality import verify_export
        with patch('render_quality.subprocess.run',return_value=MagicMock(returncode=1,stderr='invalid data')):
            with self.assertRaises(ValueError):verify_export('ffmpeg','output.mp4',3)

    def test_static_scene_is_reported_not_mislabelled_as_failure(self):
        from render_quality import verify_export
        with patch('render_quality.subprocess.run',return_value=MagicMock(returncode=0,stderr='freeze_start: 1.0\nPeak level dB: -2.3')):
            r=verify_export('ffmpeg','output.mp4',4)
            self.assertEqual(r['full_decode'],'passed');self.assertEqual(r['longest_stationary_seconds'],3)

    def test_renderer_settings_are_bounded(self):
        from short_style import validated,DEFAULT
        for engine in ('auto','ffmpeg','remotion'):self.assertEqual(validated(DEFAULT,dict(render_engine=engine))['render_engine'],engine)
        with self.assertRaises(ValueError):validated(DEFAULT,dict(render_engine='shell-command'))
