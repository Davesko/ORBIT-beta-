"""Quarantine macOS AppleDouble sidecars; never modify actual Ollama manifests/blobs."""
import fcntl,os,shutil,time,uuid
from pathlib import Path

def repair_sidecars(models,root):
 """Move macOS "._name" metadata files out of the manifest folders (newer Ollama versions use
 manifests-v2 next to manifests); Ollama reads them as broken model names and logs warnings on
 every model list. Only real AppleDouble files are moved, into backups, never deleted."""
 models=Path(models);root=Path(root)
 folders=[models/n for n in ('manifests','manifests-v2') if (models/n).is_dir()]
 if not folders:return 0
 backup=root/'backups'/'ollama-sidecars';backup.mkdir(parents=True,exist_ok=True)
 with (backup/'repair.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  destination=backup/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);count=0
  for manifest in folders:
   for directory,dirs,files in os.walk(manifest,followlinks=False):
    dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
    for name in files:
     if not name.startswith('._'):continue
     path=Path(directory)/name
     if path.is_symlink():continue
     try:
      with path.open('rb') as handle:header=handle.read(4)
      if header!=b'\x00\x05\x16\x07':continue
      target=destination/manifest.name/path.relative_to(manifest);target.parent.mkdir(parents=True,exist_ok=True)
      shutil.move(str(path),str(target));count+=1
     except OSError:continue
  return count
