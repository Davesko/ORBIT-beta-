"""Pinned image/video checkpoints for the local ComfyUI model store."""
import errno
import hashlib
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.request
from pathlib import Path

# Published Hugging Face LFS SHA-256 digests; never load arbitrary repositories or pickle.
PACKS = {
    'sdxl': ('SDXL Base 1.0', 'Képgenerálás', 'stabilityai/stable-diffusion-xl-base-1.0', 'f298da3', (
        ('sd_xl_base_1.0.safetensors', 'checkpoints/sd_xl_base_1.0.safetensors', 6_938_078_334,
         '31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b'),
    )),
    'wan21': ('Wan 2.1 T2V 1.3B', 'Szövegből videó', 'Comfy-Org/Wan-2.1', '123acf1cc74bccbb9bfff8ac1ee72edc08c2341d', (
        ('split_files/diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors', 'diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors',
         2_838_104_528, '6f999b0d6cb9a72b3d98ac386ed96f57f8cecae13994a69232514ea4974ad5fd'),
        ('split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
         6_735_906_897, 'c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68'),
        ('split_files/vae/wan_2.1_vae.safetensors', 'vae/wan_2.1_vae.safetensors',
         253_815_318, '2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b'),
    )),
}

_, _, WAN_REPO, WAN_REVISION, wan_files = PACKS['wan21']
WAN_ENCODER, WAN_VAE = wan_files[1:]


def split_file(path, size, digest):
    return ('split_files/'+path, path, size, digest)


WAN_VISION = split_file('clip_vision/clip_vision_h.safetensors', 1_264_219_396,
                        '64a7ef761bfccbadbaa3da77366aac4185a6c58fa5de5f589b42a65bcc21f161')
PACKS.update({
    'wan21-i2v': ('Wan 2.1 I2V 14B FP8', 'Képből videó', WAN_REPO, WAN_REVISION, (
        split_file('diffusion_models/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors', 16_397_245_448,
                   '0ca75338e7a47ca7cacddb7e626647e65829c497387f718ecb6ea0bae456944a'),
        WAN_ENCODER, WAN_VAE, WAN_VISION,
    )),
    'wan22': ('Wan 2.2 TI2V 5B', 'Szövegből vagy képből videó', 'Comfy-Org/Wan-2.2', 'ee6f4a40737a995bf5818954cfce6d59443b0f04', (
        split_file('diffusion_models/wan2.2_ti2v_5B_fp16.safetensors', 9_999_658_848,
                   '456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e'),
        WAN_ENCODER,
        split_file('vae/wan2.2_vae.safetensors', 1_409_400_960,
                   'e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156'),
    )),
    'wan21-camera': ('Wan 2.1 Fun Camera 1.3B', 'Képből videó, vezérelhető kamerával', WAN_REPO, WAN_REVISION, (
        split_file('diffusion_models/wan2.1_fun_camera_v1.1_1.3B_bf16.safetensors', 3_232_727_784,
                   '1a648f6fbb543dd6ac9f2f9af1ca4bc1bbe460482ee4d7984d50565699e97398'),
        WAN_ENCODER, WAN_VAE, WAN_VISION,
    )),
    'wan21-t2v-14b': ('Wan 2.1 T2V 14B FP8', 'Szövegből videó', WAN_REPO, WAN_REVISION, (
        split_file('diffusion_models/wan2.1_t2v_14B_fp8_scaled.safetensors', 14_293_896_178,
                   '2e39adde59c5e0e90edbb35873126b0d67928b5c11c501e384e976d6dc597cce'),
        WAN_ENCODER, WAN_VAE,
    )),
    'svd-xt': ('Stable Video Diffusion XT', 'Képből videó', 'stabilityai/stable-video-diffusion-img2vid-xt', '9e43909513c6714f1bc78bcb44d96e733cd242aa', (
        ('svd_xt.safetensors', 'checkpoints/svd_xt.safetensors', 9_559_625_980,
         'b2652c23d64a1da5f14d55011b9b6dce55f2e72e395719f1cd1f8a079b00a451'),
    )),
    'mochi': ('Mochi Preview FP8', 'Szövegből videó', 'Comfy-Org/Mochi-Preview', 'ed4b8585dc4d3204397291c35e100884686178d6', (
        ('all_in_one/mochi_preview_fp8_scaled.safetensors', 'checkpoints/mochi_preview_fp8_scaled.safetensors', 15_841_792_490,
         'c1eb0ba4ded8df12ebbeb938c7b88a910fc380214923abcacbaab6984fa81e92'),
    )),
})


def folder(s):
    import model_hub
    cfg = model_hub.config()
    if cfg:
        if not model_hub.online() or not cfg.get('base'):
            raise ValueError('A letöltéshez csatlakoztasd a külső modelltárat.')
        return Path(cfg['base']) / 'comfy-models'
    return s.root / 'models' / 'comfy-models'


def catalog(s):
    try: root = folder(s)
    except ValueError: root = None
    items = []
    for key, (name, purpose, repo, _, files) in PACKS.items():
        total = sum(f[2] for f in files)
        remaining = missing_bytes(root, files) if root else None
        items.append(dict(id=key, name=name, purpose=purpose, engine='ComfyUI',
                          category='video' if 'videó' in purpose.casefold() else 'image',
                          gb=round(total/1e9, 1), ready=remaining == 0,
                          download_gb=round(remaining/1e9, 1) if remaining is not None else None,
                          path=str(root) if root else None, repo=repo, source='https://huggingface.co/'+repo))
    return items


def missing_bytes(root, files):
    return sum(size for _, local, size, digest in files if not verified(root/local, size, digest))


def search(s, category, query):
    def words(text):
        plain = unicodedata.normalize('NFKD', text.casefold()).encode('ascii', 'ignore').decode()
        plain = re.sub(r'(?<=\d)\.(?=\d)', '', plain)
        return re.findall(r'[a-z0-9]+', plain)

    terms = words(str(query or '')[:100])
    items = []
    for item in catalog(s):
        if item['category'] != category:
            continue
        keys = words(' '.join((item['name'], item['purpose'], item['repo'], item['id'])))
        if 'szövegből' in item['purpose'].casefold():
            keys.extend(('t2v', 'text', 'to', 'video'))
        if 'képből' in item['purpose'].casefold():
            keys.extend(('i2v', 'image', 'to', 'video'))
        keywords, compact = ' '.join(keys), ''.join(keys)
        if all(term in keywords or term in compact for term in terms):
            items.append(item)
    return items


def storage_error(error):
    if error.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        raise ValueError('Az ORBIT nem tud írni a modelltárba. A Macen nyisd meg az ORBIT-ot, és ellenőrizd a külső meghajtó engedélyét a Rendszerbeállítások → Adatvédelem és biztonság → Fájlok és mappák alatt.') from error
    raise error


def enqueue(s,key,foreground=False):
    if key not in PACKS:raise ValueError('Ismeretlen generálómodell.')
    root=folder(s)
    files=PACKS[key][4]
    try:
        remaining=missing_bytes(root,files)
        if not remaining:raise ValueError('Ez a modellcsomag már letöltődött.')
        root.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(root).free < remaining*1.1:
            raise ValueError('Nincs elég hely a modelltárban.')
        # Check the actual destination before asking the model host for gigabytes of data.
        for parent in {(root/local).parent for _,local,_,_ in files}:
            parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryFile(dir=parent):pass
    except OSError as error:
        storage_error(error)
    with s.db:
        s.db.execute('BEGIN IMMEDIATE')
        if s.db.execute("SELECT 1 FROM jobs WHERE kind='model_pull' AND status IN ('queued','running')").fetchone():
            raise ValueError('Már van folyamatban modellletöltés.')
        agent=s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
        if not agent:raise ValueError('Nincs elérhető ügynök a letöltéshez.')
        job=s.enqueue(agent[0],'Modell telepítése: '+PACKS[key][0],'model_pull',
                      payload=dict(generation_pack=key),commit=False)
        if foreground:
            # The app owns this job from the first commit, so launchd cannot claim it.
            s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?",(time.time(),job))
    return dict(job=job)


def run_foreground(s, job_id, key):
    job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone())
    try:
        if s.cancelled(job_id):return
        s.job_stage(job_id,'starting','Letöltés előkészítése')
        result=download(s,job,key)
    except Exception as error:
        s.finish(job,error=str(error)[:1500])
    else:
        s.finish(job,result)


def verified(target,size,digest):
    try:return target.is_file() and target.stat().st_size==size and target.with_suffix('.orbit-sha256').read_text()==digest
    except OSError:return False


def download(s,job,key):
    try:
        return download_files(s,job,key)
    except OSError as error:
        storage_error(error)


def download_files(s,job,key):
    import connections
    if connections.under_test():raise ValueError('Tesztfutás: modellletöltés letiltva.')
    name,_,repo,revision,files=PACKS[key]
    root=folder(s)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    total=sum(f[2] for f in files);done=0;last=0
    for remote,local,size,digest in files:
        if s.cancelled(job['id']):return ''
        target=root/local
        target.parent.mkdir(parents=True,exist_ok=True)
        if verified(target,size,digest):
            done+=size;continue
        if shutil.disk_usage(target.parent).free<size*1.1:raise ValueError('Elfogyott a hely a modelltárban.')
        part=target.with_suffix('.part')
        try:
            url=f'https://huggingface.co/{repo}/resolve/{revision}/{remote}'
            checksum=hashlib.sha256();count=0
            with opener.open(url,timeout=60) as response,part.open('wb') as out:
                while True:
                    if s.cancelled(job['id']):return ''
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>size*1.02:raise ValueError('A letöltött fájl nagyobb a közzétett méretnél.')
                    checksum.update(chunk);out.write(chunk)
                    if time.monotonic()-last>1:
                        s.job_stage(job['id'],'download',f'{name} · {min(99,round(100*(done+count)/total))}%')
                        last=time.monotonic()
            if count!=size or checksum.hexdigest()!=digest:raise ValueError('A fájl mérete vagy ellenőrzőösszege eltér a közzétett értéktől.')
            if s.cancelled(job['id']):return ''
            part.replace(target);target.with_suffix('.orbit-sha256').write_text(digest);done+=size
        finally:part.unlink(missing_ok=True)
    (root/('.orbit-'+key)).touch()
    return name+' letöltve.'
