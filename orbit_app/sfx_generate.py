"""Sound effects made from a text description with Stable Audio 3 Small SFX in the local ComfyUI.

Owner, 16 Nov: the sounds must not be "a few downloaded ones" but always made or found to fit the story. The studio
first looks in this cache of everything made before (it grows into the channel's own library), then in the recorded
packs, and only what is still missing is generated here, all of one episode's sounds in one engine start. The model is
Stability AI's Stable Audio 3 Small SFX (Stability AI Community License: free below US$1M yearly revenue, outputs
usable commercially), from the Comfy-Org repackage. When the model is missing or the engine fails, the caller keeps
the code-made sound, so an episode never waits on this."""
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CHECKPOINT = 'checkpoints/stable_audio_3_small_sfx.safetensors'
ENCODER = 'text_encoders/t5gemma_b_b_ul2.safetensors'
STEPS = 8
LICENCE = 'Stable Audio 3 Small SFX · Stability AI Community License'


def models(s):
    from generation_downloads import folder
    return folder(s)


def ready(s):
    try:
        base = models(s)
    except ValueError:
        return False
    return (base / CHECKPOINT).is_file() and (base / ENCODER).is_file()


def cache(s):
    folder = s.root / 'sfx-made'
    folder.mkdir(exist_ok=True)
    return folder


def key(prompt):
    return hashlib.sha256(prompt.lower().encode()).hexdigest()[:20]


def describe(what, place_look='', seconds=2.):
    """The writer's few words ("metal shutter rolling down") as a sound-designer prompt, the form the model was taught
    with: source, material, space, how it moves, and its length."""
    what = ' '.join(str(what or '').split()).rstrip('.')
    look = str(place_look or '').lower()
    space = ('outdoors, open air' if re.search(r'\b(street|outside|outdoor|roof|field|beach|forest|road|yard|deck|runway|mountain|square|parking)\b', look)
             else 'inside a large echoing room' if re.search(r'\b(warehouse|hall|store|supermarket|hangar|church|station|tunnel|gym|stadium|mall)\b', look)
             else 'indoors, close perspective')
    length = max(1, min(12, int(round(seconds))))
    return f'{what[:1].upper() + what[1:]}, {space}, realistic sound effect, clean recording, no music, no voice. Length: {length} seconds'


def lookup(s, prompt):
    path = cache(s) / (key(prompt) + '.wav')
    return str(path) if path.is_file() else None


def similar(s, what):
    """A sound made before for nearly the same words (the cache index keeps the writer's words)."""
    index = cache(s) / 'index.json'
    try:
        known = json.loads(index.read_text())
    except (OSError, ValueError):
        return None
    words = {w for w in re.findall(r'[a-z]+', str(what).lower()) if len(w) > 2}
    best, top = None, 0.
    for item in known:
        other = {w for w in re.findall(r'[a-z]+', item.get('what', '').lower()) if len(w) > 2}
        if not words or not other:
            continue
        score = len(words & other) / len(words | other)
        if score > top and Path(item['file']).is_file():
            best, top = item['file'], score
    return best if top >= .6 else None


def remember(s, what, prompt, file):
    try:
        import asset_library
        asset_library.add(s, 'sound', file, what + ' — ' + prompt, extra=dict(engine=LICENCE))
    except Exception:
        pass
    _index(s, what, prompt, file)


def _index(s, what, prompt, file):
    index = cache(s) / 'index.json'
    try:
        known = json.loads(index.read_text())
    except (OSError, ValueError):
        known = []
    known = [x for x in known if x.get('file') != file] + [dict(what=what, prompt=prompt, file=file, made=time.time())]
    tmp = index.with_suffix('.tmp')
    tmp.write_text(json.dumps(known[-3000:], ensure_ascii=False))
    tmp.replace(index)


def graph(prompt, seconds, seed, number):
    return {
        '1': dict(class_type='CheckpointLoaderSimple', inputs=dict(ckpt_name=Path(CHECKPOINT).name)),
        '2': dict(class_type='CLIPLoader', inputs=dict(clip_name=Path(ENCODER).name, type='stable_audio', device='default')),
        '3': dict(class_type='CLIPTextEncode', inputs=dict(text=prompt, clip=['2', 0])),
        '4': dict(class_type='CLIPTextEncode', inputs=dict(text='', clip=['2', 0])),
        '5': dict(class_type='EmptyLatentAudio', inputs=dict(seconds=float(seconds), batch_size=1)),
        '6': dict(class_type='KSampler', inputs=dict(model=['1', 0], positive=['3', 0], negative=['4', 0], latent_image=['5', 0], seed=int(seed),
                                                     steps=STEPS, cfg=1.0, sampler_name='lcm', scheduler='simple', denoise=1.0)),
        '7': dict(class_type='VAEDecodeAudio', inputs=dict(samples=['6', 0], vae=['1', 2])),
        '8': dict(class_type='SaveAudio', inputs=dict(audio=['7', 0], filename_prefix=f'orbit-sfx-{number}')),
    }


def api(port, route, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b'{}')


def make(s, job, wanted, budget=900):
    """wanted: [dict(what, prompt, seconds, seed)] -> {prompt: wav path} for everything that was made in time.
    One ComfyUI start for all of them; each finished sound is kept in the cache at once."""
    done = {}
    todo = [w for w in wanted if not lookup(s, w['prompt'])]
    for w in wanted:
        if lookup(s, w['prompt']):
            done[w['prompt']] = lookup(s, w['prompt'])
    if not todo or not ready(s):
        return done
    runtime = s.root / 'comfy-runtime'
    base = models(s)
    log = s.root / 'logs' / f'sfx-{job["id"] if job else "manual"}.log'
    log.parent.mkdir(exist_ok=True)
    ffmpeg = s.root / 'media-runtime/bin/ffmpeg'
    deadline = time.time() + budget
    with tempfile.TemporaryDirectory(prefix='sfx-', dir=runtime) as directory, log.open('wb') as stream:
        work = Path(directory)
        config = work / 'model-paths.yaml'
        config.write_text(json.dumps({'orbit': {'base_path': str(base), 'checkpoints': 'checkpoints', 'text_encoders': 'text_encoders'}}))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        engine = subprocess.Popen([str(runtime / 'venv/bin/python'), str(runtime / 'ComfyUI/main.py'), '--listen', '127.0.0.1',
                                   '--port', str(port), '--base-directory', str(work), '--extra-model-paths-config', str(config),
                                   '--offline', '--disable-all-custom-nodes', '--disable-metadata', '--preview-method', 'none'],
                                  cwd=runtime / 'ComfyUI', stdout=stream, stderr=subprocess.STDOUT,
                                  env={**os.environ, 'PYTORCH_ENABLE_MPS_FALLBACK': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'})
        try:
            while engine.poll() is None and time.time() < deadline:
                try:
                    api(port, 'system_stats')
                    break
                except (OSError, ValueError):
                    time.sleep(1)
            if engine.poll() is not None or time.time() >= deadline:
                return done
            queued = {}
            for n, w in enumerate(todo):
                try:
                    remote = api(port, 'prompt', {'prompt': graph(w['prompt'], w['seconds'], w.get('seed', n), n)}).get('prompt_id')
                except urllib.error.HTTPError as error:
                    stream.write(b'\nrejected: ' + error.read(1200))
                    return done
                queued[remote] = (n, w)
            while queued and engine.poll() is None and time.time() < deadline:
                for remote, (n, w) in list(queued.items()):
                    history = api(port, 'history/' + remote).get(remote)
                    if not history:
                        continue
                    del queued[remote]
                    if history.get('status', {}).get('status_str') == 'error':
                        continue
                    files = list((work / 'output').rglob(f'orbit-sfx-{n}_*'))
                    if not files:
                        continue
                    target = cache(s) / (key(w['prompt']) + '.wav')
                    subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(files[0]), '-ar', '48000', '-ac', '2',
                                    '-t', f"{float(w['seconds']):.2f}", str(target)], check=True, capture_output=True, timeout=60)
                    done[w['prompt']] = str(target)
                    remember(s, w['what'], w['prompt'], str(target))
                if job:
                    s.job_stage(job['id'], 'story_sound', f'Stable Audio · hangeffektek generálása ({len(done)}/{len(wanted)})')
                time.sleep(1.5)
            return done
        finally:
            if engine.poll() is None:
                engine.terminate()
                try:
                    engine.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    engine.kill()
                    engine.wait()
