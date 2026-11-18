import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import voice
class VoiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  (self.root/'models/whisper-large-v3-turbo').mkdir(parents=True);(self.root/'models/whisper-large-v3-turbo/weights.safetensors').write_bytes(b'x')
  self.rec=voice.folder(self.root)/'rec-1.m4a';self.rec.write_bytes(b'audio')
 def test_only_own_recordings_are_transcribed(self):
  for bad in ('/etc/passwd',str(self.root/'x.m4a'),str(voice.folder(self.root)/'../models/whisper-large-v3-turbo/weights.safetensors'),''):
   with self.assertRaises(ValueError):voice.recording(bad,self.root)
  self.assertEqual(voice.recording(str(self.rec),self.root),self.rec.resolve())
 def test_local_whisper_is_forced_to_hungarian(self):
  done=subprocess.CompletedProcess([],0,stdout='{"text": " Szia Orbit! "}\n',stderr='')
  with patch('voice.subprocess.run',return_value=done) as run:
   r=voice.transcribe(str(self.rec),self.root)
  self.assertEqual(r,dict(text='Szia Orbit!',engine='Whisper (helyi)'));self.assertIn('language="hu"',run.call_args[0][0][2])
 def test_speech_text_is_plain_and_bounded(self):
  t=voice.speakable('## Cím\n**Kész.** Nézd meg: [itt](https://x.hu) `kód`\n```py\nprint(1)\n```\n| a | b |\n- első pont')
  self.assertEqual(t,'Cím Kész. Nézd meg: itt kód első pont')
  long=voice.speakable('Ez egy mondat. '*200);self.assertLess(len(long),voice.MAX_SPEAK+60);self.assertTrue(long.endswith('a képernyőn olvashatod.'))
 def test_fallback_voice_is_hungarian_tunde(self):
  with patch('voice.subprocess.run') as run:
   r=voice.speak('Szia!',self.root)
  self.assertEqual(run.call_args[0][0][:3],['/usr/bin/say','-v','Tünde']);self.assertTrue(r['path'].startswith(str(voice.folder(self.root))))
class SpokenRequestTests(unittest.TestCase):
 def test_spoken_flag_reaches_the_command_job(self):
  import commander
  from studio import Studio
  s=Studio(Path(tempfile.mkdtemp()));self.addCleanup(s.db.close)
  jid=commander.enqueue(s,'universe','Mit csinál az autopilóta?',spoken=True)
  self.assertTrue(json.loads(s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])['spoken'])
  self.assertIn('read aloud in Hungarian',open(commander.__file__,encoding='utf-8').read())
if __name__=='__main__':unittest.main()
