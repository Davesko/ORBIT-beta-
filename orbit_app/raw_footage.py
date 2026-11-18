"""Shorts from the owner's own raw footage: no search, no download, the files the owner chose.

A file is either a path on this Mac (the native picker or a chat attachment gives one) or a file already inside a
project. Files outside the Shorts project are copied into its inputs/media folder, so the production only ever reads
its own project. The run then goes through the usual pipeline in highlight mode: the whole recording is read, the
strongest self-contained moment (a joke, a reaction, a surprise) is found and cut, never a summary of everything.
"""
import hashlib
import re
import subprocess
from pathlib import Path

VIDEO = {'.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi', '.mpeg', '.mpg'}
MAX_FILES = 5
DEFAULT_BRIEF = 'Saját nyers felvétel · a legjobb pillanat'


def probe_duration(s, path):
    ffmpeg = s.root / 'media-runtime/bin/ffmpeg'
    out = subprocess.run([str(ffmpeg if ffmpeg.is_file() else 'ffmpeg'), '-hide_banner', '-i', str(path)], capture_output=True, text=True, timeout=30).stderr
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', out)
    if not m or 'Video:' not in out:
        raise ValueError('Ez a fájl nem olvasható videó: ' + Path(path).name)
    return round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), 3)


def resolve_files(s, pid, files, from_project=None):
    """Project-relative video names inside pid; outside files are copied in (never moved or changed)."""
    if isinstance(files, str):
        files = [files]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES or any(not isinstance(f, str) or not f.strip() for f in files):
        raise ValueError('Adj meg 1–%d saját videófájlt.' % MAX_FILES)
    from media_tools import import_media
    base = (s.root / 'projects' / pid).resolve()
    names = []
    for item in files:
        item = item.strip()
        candidates = []
        if item.startswith('/') or item.startswith('~'):
            candidates.append(Path(item).expanduser())
        else:
            candidates.append(s.safe_path(pid, item))
            if from_project and from_project != pid:
                candidates.append(s.safe_path(from_project, item))
        path = next((c for c in candidates if c.is_file()), None)
        if path is None:
            raise ValueError('Nem találom ezt a videót: ' + item)
        if path.suffix.lower() not in VIDEO:
            raise ValueError('Csak videófájlból vágok Shortot: ' + path.name)
        path = path.resolve()
        names.append(str(path.relative_to(base)) if base in path.parents else import_media(s, pid, path))
    return list(dict.fromkeys(names))


def sources(s, pid, names):
    """Source records shaped like a verified download, so every later step works unchanged."""
    result = []
    for name in names:
        path = s.safe_path(pid, name)
        digest = hashlib.sha256((name + str(path.stat().st_size)).encode()).hexdigest()[:16]
        row = s.db.execute("SELECT name FROM artifacts WHERE project=? AND path=?", (pid, str(path))).fetchone()
        title = Path(row[0] if row else name).stem
        duration = probe_duration(s, path)
        metadata = dict(id='local-' + digest, title=title, channel='Saját felvétel', url='', duration=duration, origin='owner_footage')
        # A clip the live stream watcher cut carries whose broadcast it is; the Short credits that streamer.
        from stream_watch import source_note
        note = source_note(path)
        if note:
            metadata.update(title=str(note.get('title') or title)[:160], channel=str(note.get('channel') or '')[:80], url=str(note.get('url') or '')[:300], origin='stream_watch', game=str(note.get('game') or '')[:80], rise=note.get('rise') if isinstance(note.get('rise'), (int, float)) else None)
        result.append(dict(source_video=name, duration=duration, coverage={}, local=True, metadata=metadata))
    return result


def submit(s, pid, files, brief='', requirements=None, origin=None, from_project=None):
    names = resolve_files(s, pid, files, from_project)
    brief = (brief or '').strip()[:200]
    if len(brief) < 2:
        brief = DEFAULT_BRIEF
    from execution_queue import submit_short
    return submit_short(s, pid, brief, requirements, origin, local_files=names)
