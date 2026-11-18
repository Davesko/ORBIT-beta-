"""An original instrumental score per episode with ACE-Step 1.5 (MIT/Apache-2.0) in the local ComfyUI.

Every episode gets its own track: the prompt comes from the story (the writer's music_prompt, the chosen mood, a
reference Short's music feel) and the seed from the run, so no two episodes share a score. The graph is ComfyUI's
official ACE-Step 1.5 split workflow (turbo model, 8 steps). When the model is not installed or the engine fails,
the caller keeps the synthesized bed, so an episode never waits on music."""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

FILES = ('diffusion_models/acestep_v1.5_turbo.safetensors', 'text_encoders/qwen_0.6b_ace15.safetensors',
         'text_encoders/qwen_1.7b_ace15.safetensors', 'vae/ace_1.5_vae.safetensors')
STEPS = 8
# Mood -> (genre and instruments, tempo, key). The writer's music_prompt refines it.
MOODS = {
    'meme': ('Punchy quirky comedy underscore, staccato pizzicato strings, bouncy bass, light percussion, playful', 124, 'C major'),
    'lofi': ('Lo-fi hip hop beat, dusty swung drums, warm Rhodes electric piano chords, mellow bass, relaxed and lazy', 78, 'A minor'),
    'chaos': ('Frantic slapstick chase music, fast brass stabs, xylophone runs, rapid snare, cartoon energy', 160, 'D minor'),
    'sneaky': ('Sneaky cartoon heist music, tiptoe pizzicato, muted trumpet, walking upright bass, finger snaps', 96, 'E minor'),
    'happy': ('Upbeat cheerful ukulele pop, hand claps, glockenspiel, bright and sunny', 118, 'G major'),
    'epic': ('Over-the-top epic orchestral trailer music, huge drums, choir pads, heroic brass, dramatic', 90, 'D minor'),
    'suspense': ('Tense suspense underscore, ticking percussion, low strings ostinato, eerie synth pad', 92, 'C minor'),
    'pulse': ('Driving electronic pulse, analog synth arpeggio, tight drums, modern and energetic', 116, 'F minor'),
    'wonder': ('Whimsical wonder score, celesta, harp, soft strings, magical and curious', 100, 'F major'),
}


FLAVOURS = ('funky slap bass and clavinet groove', '8-bit chiptune arpeggios', 'jazzy brushed drums and walking upright bass', 'trap hi-hats with a deep 808',
            'bossa nova nylon guitar and shaker', 'synthwave arpeggios and gated drums', 'kazoo and tuba comedy march', 'ukulele strum with whistling',
            'boom bap drums with vinyl piano chops', 'disco strings and four-on-the-floor kick', 'reggae offbeat organ skank', 'latin percussion with brass stabs',
            'surf rock twang guitar', 'house piano stabs and claps', 'marimba and hand drums', 'drum and bass breakbeat with sub bass', 'accordion polka bounce',
            'garage rock fuzz guitar riff')
KEYS = ('C major', 'G major', 'D major', 'A minor', 'E minor', 'F major', 'Bb major', 'D minor', 'F# minor')


def ready(models):
    return all((Path(models) / f).is_file() for f in FILES)


def prompt(plan):
    mood = plan.get('profile', {}).get('music', 'meme')
    base, bpm, key = MOODS.get(mood, MOODS['meme'])
    trend = plan.get('music_trend')
    if trend and trend.get('style'):
        # 13 Nov (owner): the score follows what is trending now (music_trends), in its genre's own production style.
        seed_text = str(plan.get('title')) + trend['title']
        key = KEYS[int(hashlib.sha256(seed_text.encode()).hexdigest()[8:10], 16) % len(KEYS)]
        tags = trend['style'] + ', catchy loopable hook, high energy, instrumental, no vocals, short-form video background music, clean mix'
        return tags[:600], int(trend.get('bpm') or bpm), key
    extra = str(plan.get('music_prompt') or '').strip()
    reference = (plan.get('reference') or {}).get('music_mood')
    # The same mood words gave near-identical tracks episode after episode (10 Nov). The writer's own description leads,
    # a flavour picked from the episode itself colours it, and only the story-critical moods keep their fixed base.
    seed_text = str(plan.get('title')) + extra
    flavour = FLAVOURS[int(hashlib.sha256(seed_text.encode()).hexdigest()[:6], 16) % len(FLAVOURS)]
    keep_base = mood in ('suspense', 'epic', 'wonder') or not extra
    bpm = max(70, min(170, bpm + (int(hashlib.sha256(seed_text.encode()).hexdigest()[6:8], 16) % 37) - 18))
    key = KEYS[int(hashlib.sha256(seed_text.encode()).hexdigest()[8:10], 16) % len(KEYS)] if mood not in ('suspense', 'epic') else key
    tags = ', '.join(x for x in (extra, base if keep_base else '', flavour if mood not in ('suspense', 'epic') else '',
                                 'instrumental, no vocals, short-form video background music, clean mix') if x)
    if reference and reference != mood and reference in MOODS:
        tags += ', with a hint of ' + MOODS[reference][0].split(',')[0].lower()
    return tags[:600], bpm, key


def seed(plan, run):
    return int(hashlib.sha256(f"{run}:{plan.get('title')}:{plan.get('music_prompt')}".encode()).hexdigest()[:12], 16)


def keyscale(key):
    """ACE-Step only takes "F# minor" / "Bb major" (13 Nov: 'F sharp minor' and 'B flat major' were refused, the score failed)."""
    root, _, quality = str(key or 'C major').strip().partition(' ')
    root = root[:1].upper() + root[1:].replace('sharp', '#').replace('flat', 'b')
    quality = quality.replace('sharp ', '#').replace('flat ', 'b')
    if quality.startswith(('#', 'b')):
        root, quality = root + quality[0], quality[1:].strip()
    quality = 'minor' if 'min' in quality.lower() else 'major'
    return f'{root} {quality}' if root in ROOTS else f'C {quality}'


ROOTS = ('C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B')


def graph(tags, seconds, bpm, key, number):
    return {
        '1': dict(class_type='UNETLoader', inputs=dict(unet_name=Path(FILES[0]).name, weight_dtype='default')),
        '2': dict(class_type='ModelSamplingAuraFlow', inputs=dict(model=['1', 0], shift=3)),
        '3': dict(class_type='DualCLIPLoader', inputs=dict(clip_name1=Path(FILES[1]).name, clip_name2=Path(FILES[2]).name,
                                                            type='ace', device='default')),
        '4': dict(class_type='TextEncodeAceStepAudio1.5', inputs=dict(
            clip=['3', 0], tags=tags, lyrics='[Instrumental]', seed=number, bpm=bpm, duration=seconds, timesignature='4',
            language='en', keyscale=keyscale(key), generate_audio_codes=True, cfg_scale=2.0, temperature=.85, top_p=.9, top_k=0, min_p=0.)),
        '5': dict(class_type='ConditioningZeroOut', inputs=dict(conditioning=['4', 0])),
        '6': dict(class_type='EmptyAceStep1.5LatentAudio', inputs=dict(seconds=seconds, batch_size=1)),
        '7': dict(class_type='KSampler', inputs=dict(model=['2', 0], positive=['4', 0], negative=['5', 0], latent_image=['6', 0],
                                                     seed=number, steps=STEPS, cfg=1, sampler_name='euler', scheduler='simple', denoise=1)),
        '8': dict(class_type='VAELoader', inputs=dict(vae_name=Path(FILES[3]).name)),
        '9': dict(class_type='VAEDecodeAudio', inputs=dict(samples=['7', 0], vae=['8', 0])),
        '10': dict(class_type='SaveAudio', inputs=dict(audio=['9', 0], filename_prefix='orbit-music')),
    }


def api(port, route, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def compose(s, job, plan, run, destination, seconds):
    """Render the score to destination (WAV, 24 kHz stereo). No time limit: it waits while the engine is alive and
    reports progress; a crashed engine or a ComfyUI error is an error the caller recovers from."""
    from generation_downloads import folder
    models = folder(s)
    if not ready(models):
        raise ValueError('Az ACE-Step 1.5 zenemodell nincs telepítve.')
    runtime = s.root / 'comfy-runtime'
    tags, bpm, key = prompt(plan)
    number = seed(plan, run)
    log = s.root / 'logs' / f'ace-{job["id"]}.log'
    log.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='music-', dir=runtime) as directory, log.open('wb') as stream:
        work = Path(directory)
        config = work / 'model-paths.yaml'
        config.write_text(json.dumps({'orbit': {'base_path': str(models), 'diffusion_models': 'diffusion_models',
                                                'text_encoders': 'text_encoders', 'vae': 'vae'}}))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        engine = subprocess.Popen([str(runtime / 'venv/bin/python'), str(runtime / 'ComfyUI/main.py'), '--listen', '127.0.0.1',
                                   '--port', str(port), '--base-directory', str(work), '--extra-model-paths-config', str(config),
                                   '--offline', '--disable-all-custom-nodes', '--disable-metadata', '--preview-method', 'none'],
                                  cwd=runtime / 'ComfyUI', stdout=stream, stderr=subprocess.STDOUT,
                                  env={**os.environ, 'PYTORCH_ENABLE_MPS_FALLBACK': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'})
        try:
            while engine.poll() is None:
                try:
                    api(port, 'system_stats')
                    break
                except (OSError, ValueError):
                    time.sleep(1)
            if engine.poll() is not None:
                raise ValueError('A zenemotor nem indult el. Napló: ' + log.name)
            try:
                remote = api(port, 'prompt', {'prompt': graph(tags, seconds, bpm, key, number)}).get('prompt_id')
            except urllib.error.HTTPError as error:
                raise ValueError('Az ACE-Step munkafolyamatot a ComfyUI elutasította: ' + error.read(1200).decode(errors='replace')) from error
            while engine.poll() is None:
                history = api(port, 'history/' + remote).get(remote)
                if history:
                    status = history.get('status', {})
                    if status.get('status_str') == 'error':
                        detail = next((m[1].get('exception_message') for m in status.get('messages', []) if m[0] == 'execution_error'), '')
                        raise ValueError('ACE-Step zenegenerálási hiba: ' + str(detail)[:500])
                    break
                s.job_stage(job['id'], 'story_sound', 'ACE-Step 1.5 · saját zene komponálása ehhez az epizódhoz')
                time.sleep(3)
            else:
                raise ValueError('A zenemotor leállt generálás közben. Napló: ' + log.name)
            files = list((work / 'output').rglob('orbit-music*'))
            if len(files) != 1:
                raise ValueError('A zenemotor nem adott hangfájlt.')
            ffmpeg = s.root / 'media-runtime/bin/ffmpeg'
            subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(files[0]), '-ar', '24000', '-ac', '2',
                            '-t', f'{seconds:.3f}', str(destination)], check=True, capture_output=True, timeout=120)
            return dict(engine='ACE-Step 1.5 turbo', tags=tags, bpm=bpm, key=key, seed=number)
        finally:
            if engine.poll() is None:
                engine.terminate()
                try:
                    engine.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    engine.kill()
                    engine.wait()
