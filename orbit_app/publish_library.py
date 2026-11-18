"""The Publikálás video library: which files count as finished videos, what type each is, its facts, ready-made
texts per platform and cover images.

Finished means: a render (renders/), a Szimgyár simulation (simulations/) or a generated clip of the universe
(projects/universe/media/). Sources, inputs and cut moments never show up. Text and covers are made without a model
(a model call would evict the chat model); the owner edits them before anything goes out.
"""
import json, re, subprocess, time
from pathlib import Path

TYPES = [
    dict(id='sim', label='Szimuláció', icon='◍', hint='Szimgyár: labdás, pörgős szimulációk'),
    dict(id='story', label='Animáció', icon='✎', hint='Animációs stúdió: sztorik, sorozat'),
    dict(id='clip', label='Vágott klip', icon='✂', hint='Clip Farm, YouTube Shorts, élő adás pillanatok'),
    dict(id='music', label='Videoklip', icon='♫', hint='Videoklip stúdió'),
    dict(id='gen', label='Generált videó', icon='✧', hint='Saját univerzum: MI-generált klipek'),
    dict(id='other', label='Egyéb', icon='▫', hint='Minden más kész videó'),
]
TYPE_IDS = [t['id'] for t in TYPES]
FINISHED_SQL = "(path LIKE '%/renders/%' OR path LIKE '%/simulations/%' OR path LIKE '%/projects/universe/media/%')"
STOP = set('the a an and or of to in on is it for with this that you your are can will from at by be as was how what why not no yes'
           ' egy az és de hogy ez a ami ahogy mint volt van nem igen meg még már ide oda'.split())


def schema(s):
    s.db.executescript("""
    CREATE TABLE IF NOT EXISTS social_video_meta(artifact TEXT PRIMARY KEY,mtime REAL DEFAULT 0,width INTEGER,height INTEGER,duration REAL,
        hidden INTEGER DEFAULT 0,thumb INTEGER DEFAULT 0,thumbs TEXT DEFAULT '[]',hook TEXT DEFAULT '');
    """)
    s.db.commit()


def type_of(project_name, project_kind, path):
    name = (project_name or '').lower()
    p = str(path)
    if 'szimgy' in name or '/simulations/' in p:
        return 'sim'
    if 'animáci' in name or 'stickman' in name or 'történet' in name:
        return 'story'
    if project_kind == 'musicvideo' or 'videoklip' in name:
        return 'music'
    if '/projects/universe/' in p or 'univerzum' in name:
        return 'gen'
    if re.search(r'clip|shorts|adás|stream', name):
        return 'clip'
    return 'other'


def finished_ok(s, row):
    """Path rule shared by listing and posting: only a finished MP4 inside its own project folder."""
    path = Path(row['path']).resolve()
    base = (s.root / 'projects' / row['project']).resolve()
    if base not in path.parents or path.suffix.lower() != '.mp4' or not path.is_file():
        return None
    first = path.relative_to(base).parts[0]
    if first in ('renders', 'simulations') or (row['project'] == 'universe' and first == 'media'):
        return path
    return None


# ---------------------------------------------------------------- facts

def probe(s, path):
    ffmpeg = s.root / 'media-runtime/bin/ffmpeg'
    if not ffmpeg.is_file():
        return {}
    try:
        err = subprocess.run([str(ffmpeg), '-hide_banner', '-i', str(path)], capture_output=True, text=True, timeout=20).stderr
    except (OSError, subprocess.SubprocessError):
        return {}
    d = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err)
    v = re.search(r'Video:.*?,\s*(\d{2,5})x(\d{2,5})', err)
    if not d or not v:
        return {}
    w, h = int(v[1]), int(v[2])
    if re.search(r'rotation of -?(90|270)', err):
        w, h = h, w
    return dict(width=w, height=h, duration=round(int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]), 1))


def facts(s, aid, path, budget):
    """Sidecar json (width/height/duration) first, then the cached probe, then one ffmpeg look (budget limits new probes per call)."""
    try:
        m = json.loads(path.with_suffix('.json').read_text())
        w, h, d = int(m['width']), int(m['height']), float(m['duration'])
    except (OSError, ValueError, KeyError, TypeError):
        w = h = d = None
    mtime = path.stat().st_mtime
    row = s.db.execute('SELECT * FROM social_video_meta WHERE artifact=?', (aid,)).fetchone()
    if w is None:
        if row and row['width'] and row['mtime'] == mtime:
            w, h, d = row['width'], row['height'], row['duration']
        elif budget[0] > 0:
            budget[0] -= 1
            got = probe(s, path)
            if got:
                w, h, d = got['width'], got['height'], got['duration']
                s.db.execute('INSERT INTO social_video_meta(artifact,mtime,width,height,duration) VALUES(?,?,?,?,?) ON CONFLICT(artifact) DO UPDATE SET mtime=?,width=?,height=?,duration=?',
                             (aid, mtime, w, h, d, mtime, w, h, d))
    if w is None:
        return dict(width=None, height=None, duration=None, short=None)
    return dict(width=w, height=h, duration=round(d, 1), short=h > w and d <= 180)


# ---------------------------------------------------------------- what the video is about

def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def upload_text(s, row):
    found = s.db.execute("SELECT path FROM artifacts WHERE project=? AND job=? AND name LIKE '%feltöltési szöveg.txt' LIMIT 1", (row['project'], row['job'])).fetchone()
    if not found:
        return {}
    try:
        text = Path(found['path']).read_text()[:6000]
    except OSError:
        return {}
    part = lambda name: (re.search(name + r':\n(.*?)(?:\n\n|\Z)', text, re.S) or [None, ''])[1].strip()
    return dict(title=part('CÍM')[:100], description=part('LEÍRÁS')[:1500], hashtags=part('HASHTAGEK')[:300])


_RUNS = {}


def _viewers(detail):
    try:
        return json.loads(detail or '{}').get('viewers')
    except (ValueError, TypeError):
        return None


def runs(s):
    """Every Short the Clip Farm made, by its rendered file: title/description/hashtags of the publishing package, how it was framed,
    and the watcher moment it came from. One query, cached for a few seconds, because the video list asks for every video."""
    now = time.time()
    hit = _RUNS.get(str(s.root))
    if hit and now - hit[0] < 15:
        return hit[1]
    out = {}
    try:
        rows = s.db.execute("SELECT id,project,json_extract(data,'$.render.saved') saved,json_extract(data,'$.metadata') meta,json_extract(data,'$.origin') origin,"
                            "json_extract(data,'$.render.metadata.layout') layout,json_extract(data,'$.render.metadata.captions') captions,"
                            "json_extract(data,'$.render.metadata.quality.full_decode') decode,json_extract(data,'$.complete') complete FROM short_runs "
                            "WHERE json_extract(data,'$.render.saved') IS NOT NULL").fetchall()
    except Exception:
        rows = []
    moments = {}
    try:
        moments = {r['id']: dict(score=r['score'], kind=r['kind'], channel=r['channel'], game=r['game'], viewers=_viewers(r['detail'])) for r in s.db.execute("SELECT id,score,kind,channel,game,detail FROM stream_moments").fetchall()}
    except Exception:
        pass
    for r in rows:
        try:
            meta = json.loads(r['meta']) if r['meta'] else {}
        except ValueError:
            meta = {}
        origin = str(r['origin'] or '')
        out[(r['project'], r['saved'])] = dict(run=r['id'], title=str(meta.get('title') or ''), description=str(meta.get('description') or ''),
                                               hashtags=' '.join(meta.get('hashtags') or []), layout=r['layout'], captions=bool(r['captions']), decode=r['decode'],
                                               complete=str(read_json(s.root / 'projects' / r['project'] / 'runs' / r['id'] / 'quality-check.json').get('status') or '').startswith('READY'), origin=origin, moment=moments.get(origin[6:].split(':')[0]) if origin.startswith('watch:') else None)
    _RUNS[str(s.root)] = (now, out)
    return out


def run_of(s, row, path):
    try:
        rel = str(Path(path).relative_to((s.root / 'projects' / row['project']).resolve()))
    except ValueError:
        return None
    return runs(s).get((row['project'], rel))


def clean_name(name):
    stem = re.sub(r'\.[A-Za-z0-9]{2,4}$', '', str(name or ''))
    stem = re.sub(r'[-_]+[0-9a-f]{5,8}$', '', stem)
    return ' '.join(re.sub(r'[-_]+', ' ', stem).split()).strip()


def info(s, row, path, kind):
    """Title, hook (the short line for the cover) and topic words for one video, from what its project saved next to it."""
    out = dict(title='', hook='', topic='', description='', hashtags='')
    if kind == 'sim':
        rec = read_json(path.with_suffix('.json'))
        spec = (rec.get('szim') or {}).get('spec') or rec
        out['title'] = str(rec.get('cim') or rec.get('title') or spec.get('title') or '')[:100]
        out['hook'] = str(spec.get('kerdes') or spec.get('question') or '')[:80]
        rule = spec.get('rule') or {}
        out['topic'] = ' '.join(str(x) for x in (spec.get('palette'), rule.get('what'), (spec.get('container') or {}).get('type')) if x)
    copy = upload_text(s, row)
    if copy:
        out.update({k: v for k, v in copy.items() if v})
    made = run_of(s, row, path) if kind == 'clip' else None
    if made and made['title']:
        out.update({k: made[k] for k in ('title', 'description', 'hashtags') if made[k]})
    if made and made['title'] and made['moment'] and made['moment'].get('channel'):
        # A stream Short's title is always 'Streamer | line | GTA6', also for the ones made before that rule existed.
        import stream_watch
        game = made['moment'].get('game') or ''
        out['title'] = stream_watch.streamer_title(made['title'], made['moment']['channel'], game)
        tags = [t for t in made['hashtags'].split() if t.lower() != '#gta6']
        out['hashtags'] = ' '.join((['#GTA6'] if stream_watch.is_gta(game) else []) + tags)[:300]
    if kind == 'clip':
        side = read_json(path.with_suffix('.source.json')) or read_json(path.with_name(path.stem + '.source.json'))
        out['title'] = out['title'] or str(side.get('title') or '')[:100]
    if not out['title']:
        out['title'] = clean_name(row['name']) or clean_name(path.name)
    out['hook'] = out['hook'] or out['title']
    return out


def quality(s, row, path, kind):
    """What the maker reported about the story of an animation (stickman-render-check.json): checked, fixed, or NOT checked.
    A video the maker could not check is shown as such, never as accepted (plan 17 Nov)."""
    if kind != 'story' or not path.name.startswith('stickman-'):
        return None
    run = path.stem[len('stickman-'):]
    report = read_json(s.root / 'projects' / row['project'] / 'runs' / run / 'stickman-render-check.json')
    review = report.get('story_review') if isinstance(report.get('story_review'), dict) else None
    if not report:
        return None
    status = (review or {}).get('status') or 'not_verified'
    engineering = (report.get('engineering') or {}).get('status')
    note = str((review or {}).get('note') or '')
    if engineering in ('needs_revision', 'invalid_review', 'not_checked'):
        status, note = engineering, 'mérnöki ellenőrzés: ' + str((report.get('engineering') or {}).get('note') or engineering)
    elif status == 'fixed':
        status = 'not_verified'       # changed after the check and not read again: not a verified text
    production = report.get('production') or {}
    if production and production.get('status') != 'verified':
        status, note = 'not_verified', 'Vizuális ellenőrzést igényel: %s nem igazolt művelet.' % production.get('unverified_actions', '?')
    return dict(status=status, note=note[:160], timing=report.get('timing') or 'estimated')


def language(text):
    return 'hu' if re.search(r'[áéíóöőúüű]', text.lower()) or re.search(r'\b(és|egy|hogy|nem|vagy|szerint)\b', text.lower()) else 'en'


def words(text, n=3):
    seen, out = set(), []
    for w in re.findall(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{4,}", text):
        k = w.lower()
        if k not in STOP and k not in seen:
            seen.add(k)
            out.append(w)
    return out[:n]


BASE_TAGS = dict(sim=['#satisfying', '#simulation', '#oddlysatisfying'], story=['#animation', '#story', '#cartoon'],
                 clip=['#clips', '#viral', '#funny'], music=['#musicvideo', '#newmusic'], gen=['#aiart', '#aivideo'], other=['#video'])
CTA = dict(en=['Do you think it works? Tell me in the comments!', 'Follow for more.'], hu=['Szerinted sikerül? Írd meg kommentben!', 'Kövess, ha tetszett.'])


def copy_for(inf, kind, short, platform):
    """One platform's title and caption: hook first, one line of call to action, a few fitting hashtags."""
    title = (inf['title'] or inf['hook'])[:100]
    lang = language(inf['hook'] + ' ' + inf['title'])
    tags = list(dict.fromkeys(BASE_TAGS.get(kind, ['#video']) + ['#' + w.lower() for w in words(inf['title'] + ' ' + inf['topic'], 2)]))
    if platform == 'youtube':
        tags = (['#shorts'] if short else []) + tags
    if inf.get('description'):
        body = inf['description']
        hashtags = inf.get('hashtags') or ' '.join(tags[:5])
    else:
        first = inf['hook'] if inf['hook'] and inf['hook'] != title else title
        body = first + ('\n\n' + CTA[lang][0] if platform != 'tiktok' else '') + ('\n' + CTA[lang][1] if platform in ('youtube', 'facebook') else '')
        hashtags = ' '.join(tags[:{'youtube': 5, 'instagram': 5, 'facebook': 3, 'tiktok': 4}.get(platform, 4)])
    caption = (body + ('\n\n' + hashtags if hashtags and hashtags not in body else '')).strip()
    if platform == 'youtube' and short and '#shorts' not in caption.lower():
        caption += ' #shorts'
    return dict(title=title, caption=caption[:2200])


def variants(inf, kind, short):
    return {p: copy_for(inf, kind, short, p) for p in ('youtube', 'instagram', 'facebook', 'tiktok')}


# ---------------------------------------------------------------- covers

def thumb_dir(s, row):
    return s.root / 'projects' / row['project'] / 'publish' / re.sub(r'[^A-Za-z0-9_-]', '', row['id'])


def cover_hook(title, limit=60):
    """The cover's text follows the (edited) title: 'Streamer | line | GTA6' becomes 'Streamer · line · GTA6', and when it is
    too long the middle goes first so the first and last parts (streamer, game) stay."""
    parts = [p.strip() for p in re.split(r'\s*\|\s*', ' '.join(str(title or '').split())) if p.strip()]
    if not parts:
        return ''
    while len(' · '.join(parts)) > limit and len(parts) > 2:
        parts.pop(len(parts) // 2)
    text = ' · '.join(parts)
    if len(text) > limit:
        text = text[:limit].rsplit(' ', 1)[0].rstrip(' ·,-') or text[:limit]
    return text


def make_thumbs(s, row, path, hook, short):
    python = s.root / 'media-runtime/bin/python'
    if not python.is_file():
        raise ValueError('A médiafuttató nincs telepítve, a borítóképekhez szükség van rá.')
    folder = thumb_dir(s, row)
    done = subprocess.run([str(python), '-I', str(Path(__file__).with_name('thumb_runtime.py'))], capture_output=True, text=True, timeout=180,
                          input=json.dumps(dict(source=str(path), out=str(folder), hook=hook, short=short)))
    try:
        out = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ValueError('A borítókészítő nem adott értelmezhető választ.') from None
    if not out.get('ok'):
        raise ValueError(out.get('message') or 'A borítókép nem készült el.')
    s.db.execute('INSERT INTO social_video_meta(artifact,thumbs,thumb,hook) VALUES(?,?,0,?) ON CONFLICT(artifact) DO UPDATE SET thumbs=?,thumb=0,hook=?',
                 (row['id'], json.dumps(out['thumbs']), hook, json.dumps(out['thumbs']), hook))
    s.db.commit()
    return out['thumbs']


def thumb_file(s, row, index=None, small=False):
    meta = s.db.execute('SELECT thumb,thumbs FROM social_video_meta WHERE artifact=?', (row['id'],)).fetchone()
    if not meta:
        return None
    try:
        items = json.loads(meta['thumbs'] or '[]')
    except ValueError:
        return None
    i = meta['thumb'] if index is None else int(index)
    if not 0 <= i < len(items):
        return None
    name = items[i]['file']
    if small:
        name = name.replace('.jpg', '-s.jpg')
    path = thumb_dir(s, row) / name
    return path if path.is_file() else None


def thumb_data(path):
    import base64
    return 'data:image/jpeg;base64,' + base64.b64encode(Path(path).read_bytes()).decode()


def set_hidden(s, aid, hidden):
    s.db.execute('INSERT INTO social_video_meta(artifact,hidden) VALUES(?,?) ON CONFLICT(artifact) DO UPDATE SET hidden=?', (aid, int(bool(hidden)), int(bool(hidden))))
    s.db.commit()
