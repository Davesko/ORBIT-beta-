"""ACE-Step music, Chatterbox voices and recorded effects in the story mix, each with a safe fallback."""
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import sfx_library
import story_episode as episode
import story_music
import story_voices

FFMPEG = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/ffmpeg'


def tone(path, seconds=1., rate=24000, channels=1, level=.5):
    t = np.arange(round(seconds * rate)) / rate
    x = (np.sin(2 * np.pi * 330 * t) * level).astype(np.float32)
    x = np.repeat(x[:, None], channels, axis=1) if channels > 1 else x
    with wave.open(str(path), 'wb') as w:
        w.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        w.writeframes((x * 32767).astype('<i2').tobytes())
    return path


class MusicTests(unittest.TestCase):

    def test_every_score_key_is_one_the_ace_step_node_accepts(self):
        import story_music
        allowed = {f'{r} {q}' for q in ('major', 'minor') for r in story_music.ROOTS}
        keys = set(story_music.KEYS) | {v[2] for v in story_music.MOODS.values()}
        self.assertTrue(keys <= allowed, keys - allowed)
        self.assertEqual(story_music.keyscale('F sharp minor'), 'F# minor')   # refused by ComfyUI on 13 Nov
        self.assertEqual(story_music.graph('x', 10, 100, 'B flat major', 1)['4']['inputs']['keyscale'], 'Bb major')
    def test_every_episode_gets_its_own_prompt_and_seed(self):
        plan = dict(title='Couch Legends', profile=dict(music='lofi'), music_prompt='Sleepy lo-fi with a kazoo melody',
                    reference=dict(music_mood='chaos'))
        tags, bpm, key = story_music.prompt(plan)
        self.assertTrue(tags.startswith('Sleepy lo-fi with a kazoo melody, '))
        self.assertNotIn('Lo-fi hip hop beat', tags, 'the fixed mood sentence no longer makes every track alike')
        self.assertIn('instrumental, no vocals', tags);self.assertIn('frantic slapstick', tags)
        self.assertTrue(60 <= bpm <= 170 and key in story_music.KEYS)
        other = story_music.prompt(dict(plan, title='Rent Day', music_prompt='Nervous ticking groove'))
        self.assertNotEqual((tags, bpm), (other[0], other[1]))
        scary = story_music.prompt(dict(title='x', profile=dict(music='suspense'), music_prompt='eerie'))
        self.assertIn('Tense suspense underscore', scary[0]);self.assertEqual(scary[2], 'C minor')
        self.assertNotEqual(story_music.seed(plan, 'run-a'), story_music.seed(plan, 'run-b'))

    def test_graph_is_comfyuis_ace_step_15_workflow(self):
        g = story_music.graph('lofi', 24.5, 78, 'A minor', 7)
        self.assertEqual(g['4']['class_type'], 'TextEncodeAceStepAudio1.5')
        self.assertEqual((g['4']['inputs']['lyrics'], g['4']['inputs']['duration'], g['6']['inputs']['seconds']), ('[Instrumental]', 24.5, 24.5))
        self.assertEqual((g['3']['inputs']['type'], g['3']['inputs']['clip_name2']), ('ace', 'qwen_1.7b_ace15.safetensors'))
        self.assertEqual((g['7']['inputs']['steps'], g['7']['inputs']['cfg']), (8, 1))
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(story_music.ready(d))
            for f in story_music.FILES:(Path(d) / f).parent.mkdir(parents=True, exist_ok=True);(Path(d) / f).write_bytes(b'x')
            self.assertTrue(story_music.ready(d))


class VoiceTests(unittest.TestCase):
    def test_only_supported_nonverbal_tags_are_kept(self):
        self.assertEqual(story_voices.clean('Bro. [Laugh] The pizza [looks at camera] moved [sigh].'), 'Bro. [laugh] The pizza moved [sigh].')

    def test_subtitles_never_show_tags(self):
        import story_animation as sa
        self.assertEqual(sa.caption_text(dict(caption='', lines=[dict(speaker='lead', text='[laugh] Bro, it moved.')])), 'Bro, it moved.')


class EffectLibraryTests(unittest.TestCase):
    def test_cues_map_to_recordings_and_vary_by_episode(self):
        files = ['/x/Audio/impactPunch_heavy_000.ogg', '/x/Audio/impactPunch_heavy_001.ogg', '/x/Audio/lowFrequency_explosion_000.ogg',
                 '/x/Male/game_over.ogg', '/x/Female/game_over.ogg', '/x/Audio/impactPunch_heavy_backup.txt', '/x/Pizzicato jingles/jingles_PIZZI03.ogg']
        self.assertEqual(sfx_library.matches(files, 'impactPunch_heavy'), files[:2])
        self.assertEqual(sfx_library.matches(files, 'Male/game_over'), ['/x/Male/game_over.ogg'])
        self.assertEqual(sfx_library.matches(files, 'Pizzicato jingles/'), [files[-1]])
        picks = {sfx_library.pick(files, 'boom', f'run{i}:3') for i in range(12)}
        self.assertGreater(len(picks), 1)
        self.assertIsNone(sfx_library.pick(files, 'crunch', 'x'))  # no recording: stays synthesized
        for cue in sfx_library.CUES:self.assertIn(cue, episode.CUES)


@unittest.skipUnless(FFMPEG.is_file(), 'needs the ORBIT ffmpeg')
class MixTests(unittest.TestCase):
    def test_mix_uses_the_composed_score_recorded_effects_and_rendered_lines(self):
        import story_audio
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            plan = dict(title='T', frames=96, profile=dict(arc='meme', music='lofi'), voices=episode.SERIES_VOICES,
                        music_file=str(tone(d / 'music.wav', 5, channels=2, level=.8)), sfx_files={'0': str(tone(d / 'fx.wav', .4))},
                        scenes=[dict(frames=48, beat='hook', sfx='boom', voice='', lines=[dict(speaker='lead', text='[laugh] Bro.', audio=str(tone(d / 'l.wav', .6)))]),
                                dict(frames=48, beat='twist', sfx='crunch', voice='', lines=[])])
            with patch.object(story_audio, 'engine', side_effect=AssertionError('no Kokoro needed')):
                story_audio.mix(plan, None, FFMPEG, d / 'mix.wav')
            with wave.open(str(d / 'mix.wav')) as w:
                x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2).mean(1) / 32767
            self.assertEqual(len(x), 96000)
            self.assertGreater(np.abs(x[:24000]).max(), .1)
            music = story_audio.score(plan, 96000, FFMPEG)
            self.assertAlmostEqual(story_audio.loudness(music), story_audio.MUSIC_DB, delta=1.)  # a bed by loudness (13 Nov), not a song on top
            self.assertLess(abs(float(music[0, 0])) + abs(float(music[-1, 0])), 1e-3)

    def test_missing_files_fall_back_to_synthesis(self):
        import story_audio
        plan = dict(title='T', profile=dict(music='meme'), music_file='/nope.wav', sfx_files={'0': '/nope.ogg'})
        self.assertEqual(story_audio.score(plan, 24000, FFMPEG).shape, (24000, 2))
        self.assertEqual(len(story_audio.cue_sound(plan, 0, 'pop', 2400, FFMPEG)), 2400)


class AssetFallbackTests(unittest.TestCase):
    def test_audio_step_reports_each_engine_and_falls_back(self):
        import story_animation as sa
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            s = SimpleNamespace(root=d, job_stage=lambda *a, **k: None)
            plan = dict(title='T', frames=48, profile=dict(music='lofi'), voices=episode.SERIES_VOICES,
                        scenes=[dict(frames=48, sfx='boom', lines=[dict(speaker='lead', text='Bro.')])])
            with patch('story_music.compose', side_effect=ValueError('Az ACE-Step 1.5 zenemodell nincs telepítve.')), \
                 patch('model_hub.config', return_value=dict(base=str(d))), patch('model_hub.unload'):
                report = sa.sound_assets(s, dict(id='j'), plan, 'run', d, d / 'kokoro')
        self.assertEqual(report['music']['engine'], 'synthesized lofi');self.assertIn('ACE-Step', report['music']['fallback'])
        self.assertEqual(report['voices'], dict(engine='Kokoro', fallback='Chatterbox Turbo nincs telepítve'))
        self.assertEqual(plan['sfx_files'], {});self.assertNotIn('music_file', plan)


if __name__ == '__main__':
    unittest.main()
