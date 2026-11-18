"""A still for every video (owner, 12 Nov: "a videók az orbitban mindenhol egyből jelenjenek meg"), cached in thumbs/.
Reached through project_app (poster_get), which the native app already lets through."""
import base64
import re
import subprocess
from pathlib import Path


def poster(s, aid, pid=None):
    row = s.db.execute('SELECT * FROM artifacts WHERE id=?' + (' AND project=?' if pid else ''), (aid, pid) if pid else (aid,)).fetchone()
    if not row or row['kind'] != 'video':
        return None
    path = Path(row['path'])
    base = (s.root / 'projects' / row['project']).resolve()
    if not path.is_file() or base not in path.resolve().parents:
        return None
    thumb = s.root / 'thumbs' / (re.sub(r'[^A-Za-z0-9_-]', '', row['id']) + '.jpg')
    if not thumb.is_file() or thumb.stat().st_mtime < path.stat().st_mtime:
        ffmpeg = s.root / 'media-runtime/bin/ffmpeg'
        if not ffmpeg.is_file():
            return None
        thumb.parent.mkdir(parents=True, exist_ok=True)
        for at in ('0.6', '0'):
            done = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-ss', at, '-i', str(path), '-frames:v', '1',
                                   '-vf', 'scale=480:-2', str(thumb)], capture_output=True, timeout=30)
            if done.returncode == 0 and thumb.is_file() and thumb.stat().st_size:
                break
        else:
            return None
    return 'data:image/jpeg;base64,' + base64.b64encode(thumb.read_bytes()).decode()


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'poster_get':
        return dict(poster=poster(s, str(args.get('id') or ''), args.get('project')))
    raise ValueError('Ismeretlen művelet.')
