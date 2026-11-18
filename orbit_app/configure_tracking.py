"""Download and verify the pinned official YOLOX model onto the configured SSD."""
from pathlib import Path
import urllib.request,hashlib,json,os
root=Path.home()/'Library/Application Support/Orbit'
config=json.loads((root/'model-storage.json').read_text())
assert os.path.ismount(config['mount']),'SSD unavailable'
base=Path(config['base'])/'vision';base.mkdir(parents=True,exist_ok=True)
name='object_detection_yolox_2022nov.onnx';repo='https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/'
pointer=urllib.request.urlopen(repo+name,timeout=30).read().decode();expected=next(x.split('sha256:')[1] for x in pointer.splitlines() if 'oid sha256:' in x);size=int(next(x.split()[1] for x in pointer.splitlines() if x.startswith('size ')))
assert expected=='c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063','Upstream model changed; review before updating'
url='https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/'+name
part=base/(name+'.part');digest=hashlib.sha256()
with urllib.request.urlopen(url,timeout=60) as src,part.open('wb') as dst:
 while True:
  chunk=src.read(1024*1024)
  if not chunk:break
  digest.update(chunk);dst.write(chunk)
assert digest.hexdigest()==expected and part.stat().st_size==size,'Invalid model digest'
part.replace(base/name)
license_data=urllib.request.urlopen(repo+'LICENSE',timeout=30).read();(base/'YOLOX-LICENSE.txt').write_bytes(license_data)
link=root/'models'/name
if not link.exists():link.symlink_to(base/name)
receipt=dict(name='YOLOX-S OpenCV ONNX',path=str(base/name),bytes=size,sha256=expected,source=url,license='Apache-2.0',tracker='supervision 0.27.0 ByteTrack')
(base/'tracking-model.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
