import urllib.request,json,hashlib,os
from pathlib import Path
root=Path.home()/'Library/Application Support/Orbit/models';root.mkdir(parents=True,exist_ok=True)
revision='a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb'
manifest=[]
for filename in ['config.json','weights.safetensors']:
    target=root/'whisper-large-v3-turbo'/filename;target.parent.mkdir(exist_ok=True)
    url=f'https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/{revision}/{filename}'
    print('Downloading',filename,flush=True)
    with urllib.request.urlopen(url,timeout=120) as src, target.with_suffix('.part').open('wb') as out:
        while chunk:=src.read(4*1024*1024):out.write(chunk)
    os.replace(target.with_suffix('.part'),target)
    manifest.append(dict(file=str(target.relative_to(root)),bytes=target.stat().st_size,sha256=hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),source=url))
revision='47534e27c9851bb1128ccc0102f1145e27f23f98'
url=f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{revision}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
target=root/'face_detection_yunet_2023mar.onnx'
with urllib.request.urlopen(url,timeout=60) as src:target.write_bytes(src.read())
manifest.append(dict(file=target.name,bytes=target.stat().st_size,sha256=hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),source=url))
(root/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2),flush=True)
