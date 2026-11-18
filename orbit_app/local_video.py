"""Bounded, offline Wan text-to-video rendering using a private ComfyUI process."""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from generation_downloads import PACKS, folder, missing_bytes

STEPS = 20
FRAMES = 41
FPS = 16
SIZES = {'portrait': (288, 512), 'landscape': (512, 288), 'square': (384, 384)}
TEXT_MODELS = ('wan21', 'wan21-t2v-14b', 'wan22')
IMAGE_MODELS = ('wan21-camera', 'wan21-i2v', 'wan22')
DEFAULT_VIDEO_MODEL = 'wan22'
WAN_ALIASES = (
    (r'wan\s*2[. -]?2\s*(?:ti2v\s*)?(?:5b\s*)?(?:fp16\s*)?(?:comfyui\s*)?', 'wan22'),
    (r'wan\s*2[. -]?1\s*(?:fun\s*camera|camera)\s*(?:1[. -]?3b\s*)?(?:bf16\s*)?', 'wan21-camera'),
    (r'wan\s*2[. -]?1\s*i2v\s*(?:480p\s*)?14b\s*(?:fp8\s*)?', 'wan21-i2v'),
    (r'wan\s*2[. -]?1\s*(?:t2v\s*)?14b\s*(?:fp8\s*)?', 'wan21-t2v-14b'),
    (r'wan\s*2[. -]?1\s*(?:t2v\s*)?(?:1[. -]?3b\s*)?(?:bf16\s*)?', 'wan21'),
)


def requested_model(prompt):
    """Resolve a user-specified checkpoint without substituting another variant."""
    from model_router import normalized
    words = re.sub(r'[_-]', ' ', normalized(prompt))
    wan = re.search(r'\bwan\s*2[. ]?\d+\b', words)
    if wan:
        for pattern, key in WAN_ALIASES:
            match = re.match(pattern, words[wan.start():])
            if match and not re.match(r'\s*(?:fun|camera|control|animate|[tai]i?2v|[a-z]?\d+[a-z]|gguf|mlx|quant\w*|fp\d+|bf\d+)\b',
                                     words[wan.start()+match.end():]):
                return key
        raise ValueError('A kért Wan-változathoz nincs bekötött videófuttató. A pontos modellnévhez tartozó futtatót kell használni.')
    other = re.search(r'\b(?:ltx(?:\s*(?:video|\d+(?:\.\d+)?))?|hunyuanvideo|cogvideox|mochi|sora|kling|veo|videollama|video\s*llama|stable video diffusion|svd\s*xt)\b', words)
    named = re.search(r'(?:\bmodel(?:l)?\s*:\s*([^\n,;]+)|["“„]([^"”]+)["”]\s+modell(?:el|t))', words)
    if not named and not other:
        named=re.search(r'\b([a-z][\w./:-]+)\s+modell(?:el|t)\b',words)
        if named and named[1] in ('a','az','egy','ezzel','azzal','melyik','helyi','lokalis','lokal','local','automata',
                                  'automatikus','generalo','videogeneralo','adott','masik','jobb','bizonyos','uj','ilyen','olyan','legjobb'):
            named=None
    if other or named:
        name = other[0] if other else next(value.strip() for value in named.groups() if value)
        if name in TEXT_MODELS or name in IMAGE_MODELS:
            return name
        raise ValueError(f'A kért videómodellhez ({name[:80]}) nincs bekötött futtató ebben a videós folyamatban.')
    return None


def video_model(key, image=False):
    available = IMAGE_MODELS if image else TEXT_MODELS
    selected = key or DEFAULT_VIDEO_MODEL
    if not isinstance(selected,str):
        raise ValueError('A videómodellhez pontos modellnév szükséges.')
    if selected not in available:
        mode = 'képből videóhoz' if image else 'közvetlen szövegből videóhoz'
        raise ValueError(f'A kért {PACKS[selected][0] if selected in PACKS else selected} modell {mode} nem használható ebben a folyamatban.')
    return selected


def model_fps(key):
    return 24 if key=='wan22' else FPS


def orientation(prompt):
    from model_router import normalized
    words = normalized(prompt)
    dimensions = resolution(prompt)
    if dimensions:
        w, h = dimensions
        return 'portrait' if h>w else 'landscape' if w>h else 'square'
    if re.search(r'9\s*[:/x×-]\s*16|\b(allo|fuggoleges|portrait|vertical)\b', words):
        return 'portrait'
    if re.search(r'1\s*[:/x×-]\s*1|\b(negyzetes|square)\b', words):
        return 'square'
    return 'landscape'


def resolution(prompt):
    match = re.search(r'\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b', prompt, re.I)
    return tuple(map(int, match.groups())) if match else None


def requested_seconds(prompt):
    from model_router import normalized
    words = normalized(prompt)
    match = re.search(r'\b(\d+(?:[.,]\d+)?)\s*[-–]?\s*(masodperc\w*|mp|sec\w*|s|perc\w*|min\w*)\b', words)
    if match:
        return float(match[1].replace(',', '.'))*(60 if match[2].startswith(('perc','min')) else 1)
    return 30 if re.search(r'\bfel\s+perc\w*\b',words) else None


def video_spec(prompt, aspect, model='wan21'):
    seconds = requested_seconds(prompt)
    if seconds is not None and not 0.5 <= seconds <= 5:
        raise ValueError('A helyi Wan egy klipben 0,5–5 másodpercet tud ebben a beállításban. Hosszabb, jelenetekből álló animációhoz használd a YouTube Shorts → Történetműhely feladatot.')
    fps=model_fps(model)
    frames = round(FRAMES/FPS*fps) if seconds is None else round(seconds * fps)
    size = resolution(prompt) or SIZES[aspect]
    if any(n%2 or not 256<=n<=1920 for n in size):
        raise ValueError('A videó mérete 256–1920 közötti páros képpontérték legyen.')
    w,h = SIZES[aspect]
    if size[0]*h != size[1]*w:
        raise ValueError('A helyi Wan 9:16, 16:9 vagy 1:1 képarányú videót készít.')
    return frames, size


def graph(prompt, aspect, frames=FRAMES, *, model='wan21', steps=STEPS, image=None, size=None):
    width, height = size or SIZES[aspect]
    files=PACKS[model][4]
    result = {
        '1': dict(class_type='UNETLoader', inputs=dict(unet_name=Path(files[0][1]).name, weight_dtype='default')),
        '2': dict(class_type='CLIPLoader', inputs=dict(clip_name=Path(files[1][1]).name, type='wan', device='default')),
        '3': dict(class_type='VAELoader', inputs=dict(vae_name=Path(files[2][1]).name)),
        '4': dict(class_type='CLIPTextEncode', inputs=dict(clip=['2', 0], text=prompt)),
        '5': dict(class_type='CLIPTextEncode', inputs=dict(clip=['2', 0], text='watermark, subtitles, static image, low quality, deformed anatomy, flicker, duplicate people')),
        '6': dict(class_type='EmptyHunyuanLatentVideo', inputs=dict(width=width, height=height, length=1+4*((frames+2)//4), batch_size=1)),
        '7': dict(class_type='ModelSamplingSD3', inputs=dict(model=['1', 0], shift=8.0)),
        '8': dict(class_type='KSampler', inputs=dict(model=['7', 0], positive=['4', 0], negative=['5', 0], latent_image=['6', 0],
                  seed=secrets.randbits(48), steps=steps, cfg=6.0, sampler_name='uni_pc', scheduler='simple', denoise=1.0)),
        '9': dict(class_type='VAEDecodeTiled', inputs=dict(samples=['8', 0], vae=['3', 0], tile_size=256, overlap=64, temporal_size=32, temporal_overlap=8)),
        '10': dict(class_type='CreateVideo', inputs=dict(images=['9', 0], fps=model_fps(model))),
        '11': dict(class_type='SaveVideo', inputs=dict(video=['10', 0], filename_prefix='orbit-wan', format='auto')),
    }
    if model=='wan22':
        latent=result['6']['inputs']
        latent['vae']=['3',0]
        result['6']['class_type']='Wan22ImageToVideoLatent'
        result['8']['inputs']['cfg']=5.0
        # Match the native TI2V template. Wan 2.2 uses a different, 16x spatial VAE;
        # the small Wan 2.1 tile/overlap configuration can tear its decoded frames.
        # ComfyUI's ordinary decoder has its own OOM fallback when tiling is needed.
        result['9']=dict(class_type='VAEDecode',inputs=dict(samples=['8',0],vae=['3',0]))
        if image:
            result['12']=dict(class_type='LoadImage',inputs=dict(image=image))
            latent['start_image']=['12',0]
    elif model=='wan21-i2v':
        result=camera_graph(prompt,frames,image,'Static',steps,(width,height),model=model)
        result['6']['class_type']='WanImageToVideo'
        del result['6']['inputs']['camera_conditions'],result['15']
    return result


def camera_graph(prompt, frames, image, move, steps, size, *, model='wan21-camera'):
    result=graph(prompt,'portrait',frames)
    width,height=size
    length=result['6']['inputs']['length']
    files=PACKS[model][4]
    result['1']['inputs']['unet_name']=Path(files[0][1]).name
    result['12']=dict(class_type='LoadImage',inputs=dict(image=image))
    result['13']=dict(class_type='CLIPVisionLoader',inputs=dict(clip_name=Path(files[-1][1]).name))
    result['14']=dict(class_type='CLIPVisionEncode',inputs=dict(clip_vision=['13',0],image=['12',0],crop='none'))
    result['15']=dict(class_type='WanCameraEmbedding',inputs=dict(camera_pose=move,width=width,height=height,length=length,speed=.5))
    result['6']=dict(class_type='WanCameraImageToVideo',inputs=dict(positive=['4',0],negative=['5',0],vae=['3',0],width=width,
                     height=height,length=length,batch_size=1,start_image=['12',0],clip_vision_output=['14',0],camera_conditions=['15',0]))
    result['8']['inputs'].update(positive=['6',0],negative=['6',1],latent_image=['6',2],steps=steps)
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('A helyi videómotor átirányítását elutasítottam.')


def api(port, route, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/{route}',
              data=json.dumps(body).encode() if body is not None else None,
              headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def log_tail(path):
    with path.open('rb') as file:
        file.seek(max(0, path.stat().st_size - 20000))
        return file.read().decode(errors='replace')


def render(s, job, runtime, models, prompt, aspect, frames, size, *, reference=None, move='Static', steps=STEPS, destination=None, model=None):
    logs = s.root / 'logs'
    logs.mkdir(exist_ok=True)
    log = logs / ('wan-' + job['id'] + ('-'+destination.stem if destination is not None else '') + '.log')
    model=video_model(model,image=reference is not None)
    model_name=PACKS[model][0]
    with tempfile.TemporaryDirectory(prefix='render-', dir=runtime) as directory, log.open('wb') as stream:
        work = Path(directory)
        config = work / 'model-paths.yaml'
        config.write_text(json.dumps({'orbit': {'base_path': str(models), 'diffusion_models': 'diffusion_models',
                                                'text_encoders': 'text_encoders', 'vae': 'vae','clip_vision':'clip_vision'}}))
        if reference is not None:
            (work/'input').mkdir()
            shutil.copyfile(reference,work/'input/first-frame.png')
            workflow=(camera_graph(prompt,frames,'first-frame.png',move,steps,size) if model=='wan21-camera'
                      else graph(prompt,aspect,frames,model=model,steps=steps,image='first-frame.png',size=size))
        else:
            workflow=graph(prompt,aspect,frames,model=model,steps=steps)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        args = [str(runtime/'venv/bin/python'), str(runtime/'ComfyUI/main.py'), '--listen', '127.0.0.1',
                '--port', str(port), '--base-directory', str(work), '--extra-model-paths-config', str(config),
                '--offline', '--disable-all-custom-nodes', '--disable-metadata', '--preview-method', 'none']
        env = {**os.environ, 'PYTORCH_ENABLE_MPS_FALLBACK': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
        engine = subprocess.Popen(args, cwd=runtime/'ComfyUI', env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline and engine.poll() is None:
                if s.cancelled(job['id']):
                    raise ValueError('A videógenerálás leállt.')
                try:
                    api(port, 'system_stats')
                    break
                except (OSError, ValueError):
                    time.sleep(1)
            else:
                raise ValueError('A helyi videómotor nem indult el. Napló: ' + log.name + ' · ' + log_tail(log)[-700:])
            try:
                response = api(port, 'prompt', {'prompt': workflow})
            except urllib.error.HTTPError as error:
                raise ValueError('A Wan munkafolyamatot a ComfyUI elutasította: ' + error.read(1600).decode(errors='replace')) from error
            remote = response.get('prompt_id')
            if not remote:
                raise ValueError('A helyi videómotor nem adott futásazonosítót.')
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline and engine.poll() is None:
                if s.cancelled(job['id']):
                    raise ValueError('A videógenerálás leállt.')
                history = api(port, 'history/' + remote).get(remote)
                if history:
                    status = history.get('status', {})
                    if status.get('status_str') == 'error':
                        details = next((x[1].get('exception_message') for x in status.get('messages', []) if x[0]=='execution_error'), '')
                        raise ValueError('Wan videógenerálási hiba: ' + str(details or log.name)[:650])
                    break
                progress = re.findall(r'\b(\d+)/'+str(steps)+r'\b', log_tail(log))
                prefix=destination.stem+' · ' if destination is not None else ''
                label = f'{prefix}{model_name} · {progress[-1]}/{steps} mintavételi lépés' if progress else f'{prefix}{model_name} · modellek betöltése és renderelés'
                s.job_stage(job['id'], 'video', label)
                time.sleep(3)
            else:
                raise ValueError('A helyi videórender megszakadt vagy elérte a 30 perces keretet. Napló: ' + log.name)
            videos = list((work/'output').glob('orbit-wan_*.mp4'))
            if len(videos) != 1 or not videos[0].stat().st_size:
                raise ValueError('A helyi videómotor nem készített lejátszható MP4-fájlt.')
            video, = videos
            ffmpeg = s.root/'media-runtime/bin/ffmpeg'
            output = work/'verified.mp4'
            s.job_stage(job['id'], 'video_check', 'Kért képarány és pontos képkockaszám ellenőrzése')
            result = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-progress', 'pipe:1', '-i', str(video),
                '-vf', f'scale={size[0]}:{size[1]}:flags=lanczos,setsar=1', '-frames:v', str(frames),
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)],
                capture_output=True, text=True, timeout=90)
            if result.returncode:
                raise ValueError('A kért videóformátum exportálása sikertelen: '+result.stderr[-400:])
            encoded_frames = re.findall(r'^frame=\s*(\d+)\s*$', result.stdout, re.M)
            if not encoded_frames or int(encoded_frames[-1])!=frames:
                raise ValueError('A Wan rövidebb klipet adott a kértnél.')
            from render_quality import verify_export
            verify_export(str(ffmpeg), output, frames/model_fps(model))
            if s.cancelled(job['id']):
                raise ValueError('A videógenerálás leállt.')
            destination = destination or s.safe_path(job['project'], 'media/wan-'+job['id']+'.mp4')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(output), destination)
            return destination
        finally:
            if engine.poll() is None:
                engine.terminate()
                try:
                    engine.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    engine.kill()
                    engine.wait()


def generate(s, job, action):
    from inference_gate import lease
    from language_bridge import translate_many
    from model_hub import unload
    from studio import uid
    runtime = s.root/'comfy-runtime'
    original=action.get('format_request',action['prompt'])
    model=video_model(action.get('video_model') or requested_model(original))
    model_name, _, _, _, files=PACKS[model]
    frames, size = video_spec(original, action['orientation'],model)
    if not (s.root/'media-runtime/bin/ffmpeg').is_file():
        raise ValueError('A pontos videóformátum exportálásához az ORBIT FFmpeg futtatója szükséges.')
    if not (runtime/'venv/bin/python').is_file() or not (runtime/'ComfyUI/main.py').is_file():
        raise ValueError('A helyi videófuttató nincs telepítve. A Wan modellfájlok mellé az ORBIT ComfyUI futtatója is szükséges.')
    models = folder(s)
    if missing_bytes(models, files):
        raise ValueError(f'A kért {model_name} modell fájljai nem olvashatók. A Modellek oldalon telepítsd ezt a modellt, vagy ellenőrizd az SSD-t.')
    with lease(s.root):
        s.job_stage(job['id'], 'prompt', 'Videóleírás előkészítése angolul')
        prompt, = translate_many([action['prompt']], s.root)
        unload()
        s.job_stage(job['id'], 'video', model_name+' · helyi videómotor indítása')
        output = render(s, job, runtime, models, prompt, action['orientation'], frames, size,model=model)
    s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',
                 (uid(), job['project'], model_name+' · generált videó.mp4', str(output), 'video', time.time(), job['id']))
    s.db.commit()
    return str(output)


def desktop_lane():
    """Only the desktop process claims jobs that need its removable-volume permission."""
    import fcntl
    import sqlite3
    from studio import ROOT, Studio

    parent = os.getppid()
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT/'video-worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        s = Studio()
        # This process keeps the code it started with. After an update it steps aside when idle (10 Nov: it rendered
        # with the old video engine for hours); the background worker, restarted with the new code, takes the jobs over.
        stamp = lambda: max((p.stat().st_mtime for p in Path(__file__).parent.glob('*.py')), default=0)
        loaded = stamp()
        while os.getppid() == parent:
            if stamp() != loaded:
                return
            try:
                # Avoid the write transaction on idle polls.
                pending = s.db.execute("SELECT 1 FROM jobs WHERE kind IN ('command_apply','graph') AND status='queued' AND json_extract(payload,'$.foreground_video')=1 LIMIT 1").fetchone()
                if pending and s.run_next(('command_apply','graph'), foreground_video=True):
                    continue
            except sqlite3.Error:
                s.db.rollback()
            time.sleep(2)


if __name__ == '__main__':
    desktop_lane()
