"""Narration and mix of a stickman episode (media runtime: numpy, Kokoro through narration.engine).

The references (15 Nov): one calm male narrator talking to "you" at 144-180 words a minute, a quiet tense score
under him, a few sounds only where something happens. Here: every shot's line is one clip (Chatterbox Turbo
renders them in the voice runtime when it is installed, Kokoro otherwise), trimmed of its silence; the mix places
them on the timeline, lays the score 26 dB under the voice and the effects 10 dB under it, and normalises to -14 LUFS.

Run: python3 stickman_audio.py <command> <request.json>
  reference  {kokoro, voice, speed, out}             a clip of the narrator voice for Chatterbox to clone
  kokoro     {kokoro, voice, speed, lines:[{text,out}]}
  trim       {lines:[{out}]}                          -> {seconds:[...]}  (silence cut from both ends, in place)
  mix        {ffmpeg, seconds, lines:[{out,at}], music, mood, effects:[{file,at}], output}"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

import story_audio as sa

REFERENCE = ('It is two in the morning. You are stacking cans in aisle seven, and the front doors have just slid open. '
             'You have one hour. Then the lights go out.')
VOICE_DB = -17.
MUSIC_DB = -43.
EFFECT_DB = -29.


def write(path, samples, rate=sa.RATE):
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        out.writeframes((np.clip(np.asarray(samples, np.float32), -1, 1) * 32767).astype('<i2').tobytes())


def kokoro_say(tts, text, voice, speed):
    speech = tts.generate(text=text, sid=sa.VOICE_IDS.get(voice, 16), speed=speed)
    samples = np.asarray(speech.samples, dtype=np.float32)
    if speech.sample_rate != sa.RATE:
        samples = np.interp(sa.clock(round(len(samples) * sa.RATE / speech.sample_rate)), np.arange(len(samples)) / speech.sample_rate, samples).astype(np.float32)
    return samples


def reference(req):
    from narration import engine
    write(req['out'], kokoro_say(engine(Path(req['kokoro'])), REFERENCE, req.get('voice', 'am_michael'), float(req.get('speed', 1.0))))
    return dict(out=req['out'])


def kokoro(req):
    from narration import engine
    tts = engine(Path(req['kokoro']))
    for line in req['lines']:
        write(line['out'], kokoro_say(tts, line['text'], req.get('voice', 'am_michael'), float(req.get('speed', 1.0))))
    return dict(lines=len(req['lines']))


def trim(req):
    seconds = []
    for line in req['lines']:
        path = Path(line['out'])
        if not path.is_file():
            seconds.append(0.)
            continue
        x = sa.load(path, req.get('ffmpeg', 'ffmpeg'))
        loud = np.flatnonzero(np.abs(x) > .004)
        if len(loud):
            pad = round(sa.RATE * .03)
            x = x[max(0, loud[0] - pad):loud[-1] + pad + 1]
        x = sa.fade(x, 10)
        write(path, x)
        seconds.append(round(len(x) / sa.RATE, 3))
    return dict(seconds=seconds)


def place(track, clip, at):
    start = max(0, int(round(at * sa.RATE)))
    end = min(len(track), start + len(clip))
    if end > start:
        track[start:end] += clip[:end - start]


AMBIENT_DB = -33


def weather_sound(kind, seconds, seed):
    """Rain, wind, snow or a storm made from filtered noise (no recording needed), faded in and out."""
    n = max(1, int(seconds * sa.RATE))
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n).astype(np.float32)
    def low(x, a):
        from scipy.signal import lfilter
        return lfilter([1 - a], [1, -a], x).astype(np.float32)
    try:
        slow = 0.5 + 0.5 * np.sin(np.linspace(0, seconds * .7, n) * 2 * np.pi + seed) * np.sin(np.linspace(0, seconds * .23, n) * 2 * np.pi)
        if kind in ('rain', 'storm'):
            hiss = white - low(white, .6)
            drops = (rng.random(n) > .9993).astype(np.float32) * rng.standard_normal(n).astype(np.float32) * 3
            sound = hiss * .6 + low(drops, .3)
            if kind == 'storm':
                sound += low(rng.standard_normal(n).astype(np.float32), .995) * 8 * slow
        elif kind == 'wind':
            sound = low(white, .995) * 9 * (.4 + .6 * slow)
        else:
            sound = low(white, .997) * 6 * (.3 + .4 * slow)
    except ImportError:
        sound = white * .2
    sound = sound.astype(np.float32)
    sound = sa.level(sound, AMBIENT_DB)
    fade = min(n // 2, sa.RATE)
    if fade:
        sound[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        sound[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return sound


SYNTHS = ('whoosh', 'hum', 'buzz', 'creak', 'rumble', 'beep', 'siren', 'alarm', 'ratchet', 'drip', 'splash', 'engine', 'hiss',
          'crackle', 'thud', 'ring', 'click', 'heartbeat', 'knock', 'squeak', 'static', 'thunder', 'roll', 'pour', 'wind', 'rain')


def synth(kind, seconds, seed=0):
    """A sound made in code when no recording fits (owner, 16 Nov: always able to make the sound the story needs).
    Each is a few lines of filtered noise and tones, at the effect level of the mix."""
    from scipy.signal import lfilter
    rate = sa.RATE
    n = max(1, int(seconds * rate))
    tt = np.arange(n, dtype=np.float32) / rate
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)
    low = lambda x, a: lfilter([1 - a], [1, -a], x).astype(np.float32)
    env = lambda attack, decay: np.minimum(1, tt / max(1e-3, attack)) * np.exp(-tt / max(1e-3, decay))
    if kind == 'whoosh':
        x = (noise - low(noise, .9)) * np.sin(np.pi * np.clip(tt / seconds, 0, 1)) ** 2
    elif kind == 'hum':
        x = sum(np.sin(2 * np.pi * f * tt) / (k + 1) for k, f in enumerate((60, 120, 180))) + low(noise, .99) * .5
    elif kind == 'buzz':
        x = np.sign(np.sin(2 * np.pi * 120 * tt)) * .4 + (noise - low(noise, .5)) * .1
    elif kind == 'creak':
        f = 180 + 90 * np.sin(2 * np.pi * .7 * tt)
        x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / rate)) * (rng.random(n) > .4) * np.sin(np.pi * np.clip(tt / seconds, 0, 1))
        x = low(x.astype(np.float32), .7)
    elif kind in ('rumble', 'thunder'):
        x = low(noise, .998) * 12 * (env(.05, seconds * .6) if kind == 'thunder' else 1)
    elif kind == 'beep':
        x = np.sin(2 * np.pi * 1000 * tt) * ((tt % .5) < .15)
    elif kind == 'siren':
        x = np.sin(2 * np.pi * np.cumsum(650 + 250 * np.sin(2 * np.pi * .5 * tt)) / rate)
    elif kind == 'alarm':
        x = np.sign(np.sin(2 * np.pi * 880 * tt)) * .5 * ((tt % .4) < .2)
    elif kind in ('ratchet', 'roll'):
        rate_ = 14 if kind == 'ratchet' else 30
        clicks = ((tt * rate_) % 1 < .01).astype(np.float32)
        x = low(clicks * 8, .3) + (low(noise, .97) * 2 if kind == 'roll' else 0)
    elif kind == 'drip':
        x = np.zeros(n, np.float32)
        for k in range(max(1, int(seconds * 1.5))):
            at = int((k / 1.5 + rng.random() * .2) * rate)
            m = min(n - at, int(rate * .08))
            if m > 0:
                q = np.arange(m) / rate
                x[at:at + m] += np.sin(2 * np.pi * (900 + 1500 * q / .08) * q) * np.exp(-q / .02)
    elif kind == 'splash':
        x = (noise - low(noise, .8)) * env(.01, .35)
    elif kind == 'engine':
        x = sum(np.sin(2 * np.pi * f * tt + k) for k, f in enumerate((45, 90, 135))) * (.7 + .3 * np.sin(2 * np.pi * 8 * tt)) + low(noise, .95)
    elif kind in ('hiss', 'pour'):
        x = (noise - low(noise, .6)) * (.6 if kind == 'hiss' else .3) + (low(noise, .9) * .5 if kind == 'pour' else 0)
    elif kind == 'crackle':
        x = low((rng.random(n) > .996).astype(np.float32) * rng.standard_normal(n).astype(np.float32) * 6, .2) + low(noise, .99) * .6
    elif kind == 'thud':
        x = np.sin(2 * np.pi * 60 * tt) * env(.003, .12) + low(noise, .9) * env(.002, .05)
    elif kind == 'ring':
        x = (np.sin(2 * np.pi * 1300 * tt) + np.sin(2 * np.pi * 1700 * tt)) * ((tt % 2) < 1) * (np.sin(2 * np.pi * 20 * tt) > 0)
    elif kind == 'click':
        x = (noise - low(noise, .5)) * env(.0005, .01)
    elif kind == 'heartbeat':
        beat = ((tt % .9) < .08) | (((tt - .22) % .9) < .07)
        x = low(np.sin(2 * np.pi * 50 * tt) * beat, .6)
    elif kind == 'knock':
        x = np.zeros(n, np.float32)
        for k in range(3):
            at = int(k * .28 * rate)
            m = min(n - at, int(rate * .1))
            if m > 0:
                q = np.arange(m) / rate
                x[at:at + m] += np.sin(2 * np.pi * 140 * q) * np.exp(-q / .025)
    elif kind == 'squeak':
        x = np.sin(2 * np.pi * np.cumsum(1800 + 900 * np.sin(2 * np.pi * 3 * tt)) / rate) * env(.01, .25)
    elif kind == 'static':
        x = (noise - low(noise, .3)) * (.5 + .5 * (rng.random(n) > .5))
    else:
        return weather_sound(kind, seconds, seed)
    x = np.asarray(x, np.float32)
    fade = min(n // 3, int(rate * .03))
    if fade:
        x[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        x[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return sa.level(x, EFFECT_DB)


def mix(req):
    ffmpeg = req['ffmpeg']
    count = int(round(float(req['seconds']) * sa.RATE)) + sa.RATE // 2
    voice = np.zeros(count, np.float32)
    for line in req['lines']:
        if Path(line['out']).is_file():
            place(voice, sa.level(sa.load(line['out'], ffmpeg), VOICE_DB), float(line['at']))
    effects = np.zeros(count, np.float32)
    for item in req.get('effects') or []:
        if item.get('synth'):
            try:
                place(effects, synth(item['synth'], float(item.get('seconds') or 1.2), int(item.get('seed') or 0)), float(item['at']))
            except Exception:
                pass
            continue
        try:
            clip = sa.load(item['file'], ffmpeg)[:int(sa.RATE * float(item.get('seconds') or 1.4))]
        except Exception:
            continue
        clip = sa.fade(clip, 60)
        place(effects, sa.level(clip, EFFECT_DB), float(item['at']))
    for item in req.get('ambience') or []:
        place(effects, weather_sound(item['kind'], float(item['end']) - float(item['start']), hash(item['kind']) % 1000), float(item['start']))
    music = np.zeros(count, np.float32)
    if req.get('music') and Path(req['music']).is_file():
        loop = sa.load(req['music'], ffmpeg)
        if len(loop) > sa.RATE * 4:
            # the score loops with a two-second crossfade when the episode is longer than the track
            cross = sa.RATE * 2
            pos = 0
            while pos < count:
                piece = loop.copy()
                if pos:
                    piece[:cross] *= np.linspace(0, 1, cross, dtype=np.float32)
                    n = min(cross, count - pos)
                    music[pos:pos + n] *= np.linspace(1, 0, cross, dtype=np.float32)[:n]
                place(music, piece, pos / sa.RATE)
                pos += len(loop) - cross
    elif req.get('mood'):
        music = sa.bed(count, req['mood'], 7).mean(1).astype(np.float32)
    if np.any(music):
        music = sa.level(music, MUSIC_DB)
        # a little lower still while the narrator speaks
        env = np.convolve((np.abs(voice) > .01).astype(np.float32), np.ones(sa.RATE // 5, np.float32) / (sa.RATE // 5), 'same')
        music *= 1 - .35 * np.clip(env * 3, 0, 1)
        fade = min(len(music), sa.RATE * 2)
        music[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    out = voice + effects + music
    peak = float(np.max(np.abs(out))) or 1.
    if peak > .95:
        out *= .95 / peak
    stereo = np.column_stack((out, out))
    path = Path(req['output'])
    with wave.open(str(path), 'wb') as w:
        w.setparams((2, 2, sa.RATE, 0, 'NONE', 'not compressed'))
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype('<i2').tobytes())
    measured = sa.normalise(path, ffmpeg)
    return dict(output=str(path), seconds=round(count / sa.RATE, 2), input_lufs=measured)


if __name__ == '__main__':
    command, request = sys.argv[1], json.loads(Path(sys.argv[2]).read_text())
    print(json.dumps(dict(reference=reference, kokoro=kokoro, trim=trim, mix=mix)[command](request)))
