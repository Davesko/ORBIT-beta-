import json
import tempfile
import unittest
from pathlib import Path
from studio import Studio
from bridge import dispatch
from media_tools import import_media, run_media_tool, media_models

class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Studio(Path(self.temp.name)/'orbit');self.addCleanup(self.s.db.close)
        self.a=self.s.agent(self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'])
    def test_import_binary_and_queue_permission(self):
        source=Path(self.temp.name)/'test.wav';source.write_bytes(b'RIFFtest')
        name=import_media(self.s,'universe',str(source))
        self.assertEqual(self.s.safe_path('universe',name).read_bytes(),source.read_bytes())
        request=dict(action='media_analyze',project='universe',agent=self.a['id'],operation='transcribe_media',name=name)
        with self.assertRaises(ValueError):dispatch(request,self.s)
        self.a['tools'].append('transcribe_media');self.s.save_agent(self.a)
        job=dispatch(request,self.s)['job']
        claimed=self.s.claim(('media_analysis',));self.assertEqual(claimed['id'],job)
        self.assertEqual(json.loads(claimed['payload'])['args']['name'],name)
    def test_reject_escape_unsupported_and_unauthorized(self):
        self.a['tools'].append('detect_faces');self.s.save_agent(self.a)
        job=self.s.enqueue(self.a['id'],'test')
        for name in ('../../secret.png','/tmp/outside.png'):
            with self.assertRaises(ValueError):run_media_tool(self.s,self.a,'detect_faces',{'name':name},job)
        with self.assertRaises(ValueError):run_media_tool(self.s,self.a,'transcribe_media',{'name':'a.wav'},job)
        bad=Path(self.temp.name)/'remote.m3u8';bad.write_text('https://example.invalid')
        with self.assertRaises(ValueError):import_media(self.s,'universe',str(bad))
    def test_reject_bad_timestamps_before_process(self):
        source=Path(self.temp.name)/'face.png';source.write_bytes(b'not an image')
        name=import_media(self.s,'universe',str(source));self.a['tools'].append('detect_faces')
        job=self.s.enqueue(self.a['id'],'test')
        for timestamps in ([],[float('nan')],[-1],[True],list(range(13)),['0']):
            with self.assertRaises(ValueError):run_media_tool(self.s,self.a,'detect_faces',dict(name=name,timestamps=timestamps),job)
    def test_snapshot_models_not_chat_models(self):
        response=dispatch(dict(action='snapshot',project='universe'),self.s)
        self.assertEqual(len(response['media_models']),5)
        self.assertTrue(any('Kokoro' in item['name'] for item in response['media_models']))
        self.assertFalse(any(m['ready'] for m in response['media_models']))

    def test_a_hung_model_ssd_does_not_break_the_main_request(self):
        # 2026-11-01: the exFAT model SSD hung (20 s waits, then EINTR) and every snapshot failed, so the app
        # showed no projects at all. The probe answers in 2 s and the snapshot loads without the model list.
        import model_hub,os,time
        from unittest.mock import patch
        root=Path(self.temp.name)/'orbit';(root/'model-storage.json').write_text(json.dumps(dict(base='/Volumes/Teszt/ORBIT-Models')))
        def hung(path):
            time.sleep(5);raise InterruptedError(4,'Interrupted system call',path)
        with patch('model_hub.os.listdir',side_effect=hung):
            started=time.time();self.assertFalse(model_hub.answers('/Volumes/Teszt/ORBIT-Models',root,timeout=.3))
            self.assertLess(time.time()-started,2)
            started=time.time();kokoro=media_models(root)[-1];self.assertLess(time.time()-started,1,'the answer is cached')
        self.assertFalse(kokoro['ready']);self.assertIn('az SSD nem válaszol',kokoro['purpose'])
        with patch('model_hub.os.listdir',side_effect=FileNotFoundError):self.assertTrue(model_hub.answers('/Volumes/Nincs',root),'an unplugged disk is not hung')
        with patch('media_tools.media_models',side_effect=InterruptedError(4,'Interrupted system call')):
            response=dispatch(dict(action='snapshot',project='universe'),self.s)
        self.assertEqual(response['media_models'],[]);self.assertTrue(response['projects'])
    def test_a_disk_the_model_server_still_serves_from_is_not_hung(self):
        # 1 Nov 18:10: the restarted worker could not list the SSD, the shell did in 3 ms, the model server
        # served from it, and the Autopilot waited 30 minutes for a disk that worked.
        import model_hub
        from unittest.mock import patch
        root=Path(self.temp.name)/'orbit';(root/'model-storage.json').write_text(json.dumps(dict(base='/Volumes/T/ORBIT-Models',mount='/Volumes/T')))
        with patch('model_hub.os.path.ismount',return_value=True),patch('model_hub.answers',return_value=False) as listing:
            with patch('model_hub.raw',return_value=dict(models=[dict(name='qwen3.8:27b')])):self.assertFalse(model_hub.ssd_hung(root))
            self.assertEqual(listing.call_count,0,'a serving model server makes listing the disk unnecessary')
            (root/'ssd-hung.json').unlink()
            with patch('model_hub.raw',side_effect=TimeoutError):self.assertTrue(model_hub.ssd_hung(root))
        with patch('model_hub.os.listdir',side_effect=PermissionError):self.assertTrue(model_hub.answers('/Volumes/Tiltott',root),'a refusal is an answer, not a stall')
    def test_no_model_error_names_the_hung_ssd(self):
        import model_hub,model_router
        from unittest.mock import patch
        self.assertIn('Válaszd le',model_hub.HUNG_MESSAGE)
        with patch('model_hub.ssd_hung',return_value=True),self.assertRaises(ValueError) as e:model_router.choose('Szia',[],quality={})
        self.assertEqual(str(e.exception),model_hub.HUNG_MESSAGE)

if __name__=='__main__':unittest.main()
