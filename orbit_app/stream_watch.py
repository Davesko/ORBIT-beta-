"""Élő adás figyelő: watches the biggest streamers' live broadcasts and cuts out the moments their chat exploded at.

The owner (14 Nov): from the day GTA 6 comes out, follow the top streamers' live broadcasts and clip the best scenes,
found from chat peaks instead of picture analysis, with the part before and after the peak (the idea of VodMine).

How a moment is found, without any model:
- A small listener reads the public chat of the channels that are live right now (stream_watch_runtime.py) and keeps
  five-second counts: messages, people, and laugh / hype / shock / fail reactions.
- Each chat is measured against its own last ten minutes (median and spread), so a huge chat does not flag everything
  and a small one can still have a peak. A peak needs to be several times the channel's normal, from many people.
- The moment starts where the chat began to rise, minus the seconds viewers need to see and type; the clip takes the
  seconds before it (the cause) and after it (the reaction).
- The clip is cut from the broadcast's own recording while the broadcast is still running: nothing is recorded
  continuously, so the disk stays free.

A found moment becomes a raw clip in this project; a Short is made from it by the Clip Farm's team (captions, facecam
layout), and publishing always waits for the owner in the Publikálás page. Before the game's launch nothing in its
category is touched: early footage can only be a leak.
"""
import json, math, re, subprocess, sys, time, uuid
from pathlib import Path

KIND = 'streamwatch'
NAME = 'Élő adás figyelő'
CONFIG = 'workspace/watch.json'
BUCKET = 5
DEFAULT = dict(
    enabled=False,
    channels=['kaicenat', 'caseoh_', 'jynxzi', 'xqc', 'stableronaldo', 'jasontheween', 'plaqueboymax', 'summit1g', 'zackrawrr', 'lirik', 'hasanabi', 'agent00', 'shroud', 'tarik', 'ishowspeed', 'illojuan', 'rubius', 'ibai', 'auronplay', 'ludwig', 'valkyrae', 'sodapoppin', 'asmongold', 'tfue', 'nickmercs', 'timthetatman', 'esfandtv', 'mizkif', 'ohnepixel',
                'yt:ishowspeed', 'yt:kaicenat', 'yt:markiplier', 'yt:ludwig', 'yt:pewdiepie', 'yt:rubius', 'yt:valkyrae', 'yt:dream', 'yt:sidemen'],
    game='Grand Theft Auto VI',      # only while the channel plays this; empty = any game (rehearsal)
    not_before='2026-11-19',         # the launch day; the gate opens at the first midnight on Earth (UTC+13)
    sensitivity=2.0,                 # how many spreads above the channel's own normal a peak must be
    before=12, after=12,             # seconds kept before the chat started to rise and after it calmed down
    per_hour=2,                      # at most this many moments per channel per hour (the best ones)
    min_score=15.0,                  # a moment weaker than this is not kept at all
    auto_fetch=True,                 # download the raw clip of every moment by itself
    produce_min_score=18.0,          # only moments at least this strong are downloaded and made into a Short
    max_per_day=120,                  # and at most this many Shorts per rolling 24 hours (the best first)
    auto_produce=True,               # also start a Short from it by itself
    auto_post=False,                 # off: every Short waits for the owner in the Publikálás page
    keep_days=7,
)
LEAD = 1.0        # the chat's first rise lags the action by about a second: measured on 15 clips (the loudness onset sits within 1 s of the detected rise)
KINDS = dict(funny='Nevetés', hype='Hype', shock='Döbbenet', fail='Bukás', peak='Chat-csúcs')
_last = {}


def schema(s):
    s.db.executescript("""
    CREATE TABLE IF NOT EXISTS stream_moments(id TEXT PRIMARY KEY,project TEXT NOT NULL,channel TEXT NOT NULL,vod TEXT,at REAL,start REAL,duration REAL,
        score REAL,kind TEXT,detail TEXT,status TEXT NOT NULL,file TEXT,job TEXT,production TEXT,error TEXT DEFAULT '',created REAL,game TEXT DEFAULT '');
    CREATE INDEX IF NOT EXISTS stream_moments_project ON stream_moments(project,at);
    """)
    s.db.commit()


def ensure(s):
    """The watcher's project exists once; its kind gives the Műhely its own app. A deleted one is not recreated."""
    schema(s)
    row = s.db.execute('SELECT id FROM projects WHERE kind=?', (KIND,)).fetchone()
    if row:
        return row[0]
    if s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_trash'").fetchone() and \
            s.db.execute("SELECT 1 FROM project_trash WHERE json_extract(data,'$.kind')=?", (KIND,)).fetchone():
        return None
    pid = s.create_project(NAME, 'A legnagyobb streamerek élő adásait figyeli, és a chat-csúcsoknál kivágja a legjobb jeleneteket.', KIND)
    return pid


def folder(s, pid):
    path = s.root / 'stream-watch' / pid
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings(s, pid):
    try:
        saved = json.loads(s.safe_path(pid, CONFIG).read_text())
    except (OSError, ValueError):
        saved = {}
    return clean(dict(DEFAULT, **(saved if isinstance(saved, dict) else {})))


def clean(cfg):
    num = lambda key, lo, hi: min(hi, max(lo, float(cfg.get(key)) if isinstance(cfg.get(key), (int, float)) and not isinstance(cfg.get(key), bool) else DEFAULT[key]))
    channels = []
    for c in cfg.get('channels') if isinstance(cfg.get('channels'), list) else DEFAULT['channels']:
        c = str(c).strip().lower()
        yt = re.match(r'^(?:https?://)?(?:www\.)?youtube\.com/@([a-z0-9_.\-]+)', c)
        c = 'yt:' + yt.group(1) if yt else re.sub(r'^https?://(www\.)?twitch\.tv/', '', c).strip('/@ ')
        if re.fullmatch(r'yt:[a-z0-9_.\-]{2,40}|[a-z0-9_]{2,25}', c) and c not in channels:
            channels.append(c)
    day = str(cfg.get('not_before') or '')
    return dict(enabled=cfg.get('enabled') is True, channels=channels[:60], game=' '.join(str(cfg.get('game') or '').split())[:80],
                not_before=day if re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) else '',
                sensitivity=num('sensitivity', 1.5, 10), min_score=num('min_score', 0, 40), before=int(num('before', 5, 90)), after=int(num('after', 3, 60)),
                per_hour=int(num('per_hour', 1, 30)), auto_fetch=cfg.get('auto_fetch') is not False, produce_min_score=num('produce_min_score', 0, 100), max_per_day=int(num('max_per_day', 1, 400)), auto_produce=cfg.get('auto_produce') is not False, auto_post=cfg.get('auto_post') is True,
                keep_days=int(num('keep_days', 1, 60)))


def save(s, pid, patch):
    if not isinstance(patch, dict):
        raise ValueError('Érvénytelen beállítás.')
    cfg = clean(dict(settings(s, pid), **{k: v for k, v in patch.items() if k in DEFAULT}))
    path = s.safe_path(pid, CONFIG)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    _last.pop(pid, None)
    return cfg


def gate_open(cfg, now=None):
    """Before the launch a broadcast in the game's category can only be early (leaked) material: it is not watched."""
    if not cfg['not_before'] or not cfg['game']:
        return True
    import calendar
    opens = calendar.timegm(time.strptime(cfg['not_before'], '%Y-%m-%d')) - 13 * 3600
    return (now or time.time()) >= opens


def same_game(game, wanted):
    norm = lambda t: re.sub(r'[^a-z0-9]+', ' ', str(t).lower()).strip()
    return not wanted or norm(wanted) == norm(game)


# ---------------------------------------------------------------- detection (pure)

def median(values):
    values = sorted(values)
    n = len(values)
    return 0.0 if not n else values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def detect(buckets, cfg, now=None):
    """Chat peaks in one channel's five-second buckets (dicts with t, n, users and the reaction counts).

    Every 15-second window is compared with the ten minutes before it. Returns moments ordered by time:
    at (when the chat began to rise), end (when it calmed), score, kind, z, rate, normal, people.
    A peak still rising at the end of the data is left for the next round, so its end is real."""
    if not buckets:
        return []
    by = {int(b['t']): b for b in buckets}
    first, last = min(by), max(by)
    times = list(range(first, last + BUCKET, BUCKET))
    empty = dict(n=0, users=0, funny=0, hype=0, shock=0, fail=0, clip=0)
    row = [by.get(t, empty) for t in times]
    rate = [sum(row[j]['n'] for j in range(max(0, i - 2), i + 1)) for i in range(len(row))]      # messages in the last 15 s
    base, spread, z = [], [], []
    for i in range(len(row)):
        past = rate[max(0, i - 124):max(0, i - 4)]                # ten minutes, ending 20 s before now
        if len(past) < 36:                                        # three minutes of history before anything is judged
            base.append(None); spread.append(None); z.append(0.0)
            continue
        m = median(past)
        mad = median([abs(x - m) for x in past]) * 1.4826
        floor = max(1.5, m * .25)                                 # a dead-quiet chat must not turn two messages into a peak
        base.append(m); spread.append(max(mad, floor)); z.append((rate[i] - m) / max(mad, floor))
    out = []
    i = 0
    need = cfg['sensitivity']
    while i < len(row):
        if base[i] is None or z[i] < need or rate[i] < max(6, base[i] * 1.6):
            i += 1
            continue
        start = i
        while start > 0 and base[start - 1] is not None and z[start - 1] >= 1.5:
            start -= 1
        end = i
        top = i
        while end + 1 < len(row) and z[end + 1] >= 1.5:
            end += 1
            if z[end] > z[top]:
                top = end
        if end >= len(row) - 1 and (now is None or now - times[end] < 20):
            break                                                 # still going: decide when it has ended
        span = row[max(0, start - 2):end + 1]
        people = max(b['users'] for b in span)
        if people >= 4:
            tally = {k: sum(b[k] for b in span) for k in ('funny', 'hype', 'shock', 'fail')}
            total = sum(b['n'] for b in span) or 1
            lead = max(tally, key=tally.get)
            kind = lead if tally[lead] >= max(3, total * .12) else 'peak'
            clip_calls = sum(b['clip'] for b in span)
            import math
            zs = z[top] if z[top] <= 10 else 10 + 3 * math.log2(z[top] / 10)      # a chat that was silent before makes z explode: compress above 10
            score = zs * math.log10(10 + people) * (1 + min(.5, tally[lead] / total)) + min(3, clip_calls * .5)
            out.append(dict(at=times[max(0, start - 2)], end=times[end] + BUCKET, score=round(score, 2), kind=kind, z=round(z[top], 1), rate=rate[top],
                            normal=round(base[top], 1), people=people, clip_calls=clip_calls, reactions=tally))
        i = end + 1
    return out


def window(moment, started, cfg):
    """Where the clip sits in the broadcast's recording: the cause before the chat rose, the reaction after it."""
    begin = moment['at'] - LEAD - cfg['before'] - started
    finish = moment['end'] - LEAD + cfg['after'] - started
    begin = max(0.0, begin)
    length = min(60.0, max(20.0, finish - begin))
    return round(begin, 1), round(length, 1)


# ---------------------------------------------------------------- processes

def spawn(args, python='/usr/bin/python3', stdin=None, log=None):
    with open(log or '/dev/null', 'ab') as errors:
        process = subprocess.Popen([python, str(Path(__file__).with_name('stream_watch_runtime.py')), *args],
                                   stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True)
        if stdin is not None:
            process.stdin.write(json.dumps(stdin).encode())
            process.stdin.close()
    return process


def live_state(s, pid):
    try:
        data = json.loads((folder(s, pid) / 'live.json').read_text())
    except (OSError, ValueError):
        data = {}
    return dict(checked=float(data.get('checked') or 0), channels={c['channel']: c for c in data.get('channels') or [] if isinstance(c, dict) and c.get('channel')})


def listener_alive(s, pid):
    try:
        return time.time() - (folder(s, pid) / 'listener.heartbeat').stat().st_mtime < 45
    except OSError:
        return False


def buckets(s, pid, channel, since):
    import sqlite3
    path = folder(s, pid) / 'chat.sqlite'
    if not path.is_file():
        return []
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=5)
    try:
        rows = db.execute('SELECT t,n,users,funny,hype,shock,fail,clip FROM buckets WHERE channel=? AND t>=? ORDER BY t', (channel, int(since))).fetchall()
    except sqlite3.Error:
        return []
    finally:
        db.close()
    return [dict(zip(('t', 'n', 'users', 'funny', 'hype', 'shock', 'fail', 'clip'), r)) for r in rows]


def watching(cfg, live, now=None):
    """Channels that are live, in the wanted game, after the launch gate."""
    if not cfg['enabled'] or not gate_open(cfg, now):
        return []
    return [c for c in cfg['channels'] if (live['channels'].get(c) or {}).get('live') and same_game((live['channels'][c]).get('game') or '', cfg['game'])]


def tick(s, now=None):
    if not _last.get('ensured'):
        _last['ensured'] = True
        ensure(s)
    schema(s)
    now = now or time.time()
    import autonomy
    hold = autonomy.paused(s)
    for (pid,) in s.db.execute('SELECT id FROM projects WHERE kind=?', (KIND,)).fetchall():
        if now - _last.get(pid, 0) < 10:
            continue
        _last[pid] = now
        cfg = settings(s, pid)
        if hold:
            cfg = dict(cfg, enabled=False)
        base = folder(s, pid)
        live = live_state(s, pid)
        runtime = s.root / 'media-runtime/bin/python'
        if cfg['enabled'] and cfg['channels'] and now - live['checked'] > 150 and runtime.is_file():
            stamp = base / 'probe.started'
            if not stamp.exists() or now - stamp.stat().st_mtime > 120:
                stamp.touch()
                spawn(['probe'], str(runtime), dict(channels=cfg['channels'], out=str(base / 'live.json')), base / 'probe.log')
        active = watching(cfg, live, now)
        # The listener ends by itself when this file stops being refreshed or lists nothing for long.
        if cfg['enabled'] or (base / 'listen.json').exists():
            (base / 'listen.json').write_text(json.dumps(dict(updated=now if cfg['enabled'] else 0, channels=active,
                                                              videos={c: live['channels'][c].get('vod') for c in active if c.startswith('yt:')})))
        if active and not listener_alive(s, pid):
            stamp = base / 'listener.started'
            if not stamp.exists() or now - stamp.stat().st_mtime > 40:
                stamp.touch()
                spawn(['listen', str(base)], log=base / 'listener.log')
        for channel in active:
            found = detect(buckets(s, pid, channel, now - 15 * 60), cfg, now)
            record(s, pid, channel, live['channels'][channel], found, cfg, now)
        advance(s, pid, cfg, live, now)
        prune(s, pid, cfg, now)


def record(s, pid, channel, state, found, cfg, now):
    for m in found:
        if m['score'] < cfg['min_score']:
            continue
        if s.db.execute('SELECT 1 FROM stream_moments WHERE project=? AND channel=? AND abs(at-?)<90', (pid, channel, m['at'])).fetchone():
            continue
        hour = s.db.execute('SELECT count(*) FROM stream_moments WHERE project=? AND channel=? AND at>?', (pid, channel, m['at'] - 3600)).fetchone()[0]
        if hour >= cfg['per_hour']:
            # A full hour keeps only its best: a stronger moment replaces the weakest one that has not been used yet.
            weakest = s.db.execute("SELECT id,score FROM stream_moments WHERE project=? AND channel=? AND at>? AND status='found' ORDER BY score LIMIT 1", (pid, channel, m['at'] - 3600)).fetchone()
            if not weakest or weakest['score'] >= m['score']:
                continue
            s.db.execute('DELETE FROM stream_moments WHERE id=?', (weakest['id'],))
        started = float(state.get('vod_started') or state.get('started') or 0)
        start, length = window(m, started, cfg) if started else (None, None)
        s.db.execute('INSERT INTO stream_moments(id,project,channel,vod,at,start,duration,score,kind,detail,status,created,game) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (uuid.uuid4().hex[:16], pid, channel, state.get('vod') or '', m['at'], start, length, m['score'], m['kind'],
                      json.dumps(dict({k: m[k] for k in ('z', 'rate', 'normal', 'people', 'clip_calls', 'reactions', 'end')}, viewers=state.get('viewers'))), 'found', now, state.get('game') or ''))
    s.db.commit()


def agent_of(s, pid):
    row = s.db.execute('SELECT id FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid LIMIT 1', (pid,)).fetchone()
    if not row:
        raise ValueError('A figyelő projektjében nincs ügynök.')
    return row[0]


def fetch(s, mid):
    """Queues the download of a moment's raw clip from the broadcast recording."""
    m = moment(s, mid)
    if m['status'] not in ('found', 'failed'):
        return dict(message='Ez a pillanat már le van töltve vagy épp töltődik.')
    if not m['vod'] or m['start'] is None:
        raise ValueError('Ehhez az adáshoz nincs nyilvános felvétel (a streamer kikapcsolta), ezért nem vágható ki.')
    jid = s.enqueue(agent_of(s, m['project']), 'Élő adás · pillanat letöltése · ' + m['channel'], 'assist', payload=dict(task='watch_fetch', moment=mid, local_only=True), commit=False)
    s.db.execute("UPDATE stream_moments SET status='fetching',job=?,error='' WHERE id=?", (jid, mid))
    s.db.commit()
    return dict(message='A részlet letöltése sorba állt.', job=jid)


def production_active(s):
    """Is the Clip Farm busy with a Short right now (one at a time: the strongest moment goes next, not the oldest)."""
    from clip_farm import PROJECT
    return bool(s.db.execute("SELECT 1 FROM jobs WHERE project=? AND status IN ('queued','running') AND json_extract(payload,'$.auto_step') IS NOT NULL", (PROJECT,)).fetchone())


def sync_production(s, pid):
    """A moment whose Short was started is 'produced' once its run has no job left, or 'failed' if the verification never finished."""
    for m in s.rows("SELECT id FROM stream_moments WHERE project=? AND status='producing'", (pid,)):
        run = s.db.execute("SELECT id FROM short_runs WHERE json_extract(data,'$.origin') LIKE ? ORDER BY created DESC LIMIT 1", ('watch:' + m['id'] + '%',)).fetchone()
        if not run:
            continue
        jobs = s.rows("SELECT status,json_extract(payload,'$.auto_step') step FROM jobs WHERE json_extract(payload,'$.run')=?", (run['id'],))
        if not jobs or any(j['status'] in ('queued', 'running') for j in jobs):
            continue
        ok = any(j['step'] == 'verify' and j['status'] == 'done' for j in jobs)
        tries = s.db.execute("SELECT count(*) FROM short_runs WHERE json_extract(data,'$.origin') LIKE ?", ('watch:' + m['id'] + '%',)).fetchone()[0]
        if not ok and tries < 2 and s.db.execute('SELECT file FROM stream_moments WHERE id=?', (m['id'],)).fetchone()[0]:
            s.db.execute("UPDATE stream_moments SET status='ready',production=NULL,error='' WHERE id=?", (m['id'],))      # one more attempt, from the same clip
            continue
        s.db.execute('UPDATE stream_moments SET status=?,error=? WHERE id=?', ('produced' if ok else 'failed', '' if ok else 'A Short gyártása nem fejeződött be.', m['id']))
    s.db.commit()


def advance(s, pid, cfg, live, now):
    """Best first, not in order: the strongest ready moment becomes the next Short (one at a time), and the strongest found one is downloaded.
    Weak moments (below produce_min_score) are listed but never downloaded or produced, and at most max_per_day Shorts a day."""
    import autonomy
    if autonomy.paused(s):
        return
    sync_production(s, pid)
    floor = cfg['produce_min_score']
    if cfg['auto_produce'] and not production_active(s):
        made = s.db.execute("SELECT count(*) FROM stream_moments WHERE project=? AND production IS NOT NULL AND status IN ('producing','produced') AND created>?", (pid, now - 86400)).fetchone()[0]
        best = sorted(s.rows("SELECT id,score,detail FROM stream_moments WHERE project=? AND status='ready' AND production IS NULL AND file IS NOT NULL AND score>=?", (pid, floor)), key=lambda r: -rank(r['score'], moment_viewers(r)))[:1] if made < cfg['max_per_day'] else []
        if best:
            try:
                produce(s, best[0]['id'])
            except ValueError as error:
                s.db.execute('UPDATE stream_moments SET error=? WHERE id=?', (str(error)[:300], best[0]['id']))
                s.db.commit()
    if not cfg['auto_fetch'] or s.db.execute("SELECT 1 FROM stream_moments WHERE project=? AND status='fetching'", (pid,)).fetchone():
        return
    # A small buffer of downloaded clips is enough: the next fetch is chosen when a place frees up, so a stronger moment can still overtake.
    if s.db.execute("SELECT count(*) FROM stream_moments WHERE project=? AND status='ready' AND production IS NULL", (pid,)).fetchone()[0] >= 2:
        return
    for m in sorted(s.rows("SELECT * FROM stream_moments WHERE project=? AND status='found' AND vod!='' AND start IS NOT NULL AND at>? AND score>=?", (pid, now - 6 * 3600, floor)), key=lambda r: -rank(r['score'], moment_viewers(r)))[:5]:
        state = live['channels'].get(m['channel']) or {}
        # The recording runs a little behind the broadcast: the strongest waits for it rather than a weaker one jumping ahead.
        if state.get('vod') == m['vod'] and state.get('live') and now - m['at'] < cfg['after'] + 150:
            return
        try:
            fetch(s, m['id'])
        except ValueError:
            continue
        return


def run_job(s, job):
    payload = json.loads(job['payload'])
    m = moment(s, payload['moment'])
    pid = m['project']
    out = s.safe_path(pid, 'sources/moments/' + m['channel'].replace(':', '-') + '-' + time.strftime('%m%d-%H%M%S', time.localtime(m['at'])) + '.mp4')
    st = live_state(s, pid)['channels'].get(m['channel']) or {}
    # The window's absolute start: the broadcast's start plus the offset (YouTube cuts by clock time), or from the chat's own clock.
    abs_start = (float(st['vod_started']) + float(m['start'])) if st.get('vod') == m['vod'] and st.get('vod_started') and m['start'] is not None else m['at'] - (LEAD + settings(s, pid)['before'])
    s.job_stage(job['id'], 'download', 'Részlet letöltése · ' + m['channel'] + ' · ' + str(round(m['duration'])) + ' mp')
    try:
        done = subprocess.run([str(s.root / 'media-runtime/bin/python'), str(Path(__file__).with_name('stream_watch_runtime.py')), 'fetch'],
                              input=json.dumps(dict(vod=m['vod'], start=m['start'], duration=m['duration'], out=str(out), platform='youtube' if m['channel'].startswith('yt:') else 'twitch', abs_start=abs_start)), capture_output=True, text=True, timeout=300)
        result = json.loads(done.stdout.strip().splitlines()[-1])
        if not result.get('ok'):
            raise ValueError(result.get('message') or 'A letöltés nem sikerült.')
    except (ValueError, IndexError, subprocess.TimeoutExpired) as error:
        text = 'A letöltés időkerete lejárt.' if isinstance(error, subprocess.TimeoutExpired) else str(error)[:300] or 'A letöltő nem adott választ.'
        # "Not there yet" is not a failure: the recording catches up and the next round tries again.
        status = 'found' if 'még nem ér el' in text and time.time() - m['at'] < 3600 else 'failed'
        s.db.execute('UPDATE stream_moments SET status=?,error=? WHERE id=?', (status, text, m['id']))
        s.db.commit()
        if status == 'found':
            return 'A felvétel még nem tart itt; később újra megpróbálom.'
        raise ValueError(text)
    path = Path(result['result']['file'])
    yt = m['channel'].startswith('yt:')
    link = ('https://www.youtube.com/watch?v=' + m['vod'] + '&t=' if yt else 'https://www.twitch.tv/videos/' + m['vod'] + '?t=') + str(int(m['start'])) + 's'
    path.with_suffix('.source.json').write_text(json.dumps(dict(origin='stream_watch', platform='youtube' if yt else 'twitch', channel=m['channel'].replace('yt:', ''), url=link,
                                                                title=(result['result'].get('title') or m['channel'])[:160], game=m['game'], moment=m['id'],
                                                                rise=round(LEAD + settings(s, pid)['before'], 1) if m['start'] and m['start'] > 0 else None), ensure_ascii=False))
    s.db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?,?)', (uuid.uuid5(uuid.NAMESPACE_URL, str(path)).hex, pid, path.name, str(path), 'video', time.time(), job['id']))
    s.db.execute("UPDATE stream_moments SET status='ready',file=?,error='' WHERE id=?", (str(path.relative_to(s.root / 'projects' / pid)), m['id']))
    s.db.commit()
    return 'Pillanat kivágva: ' + m['channel'] + ' · ' + KINDS.get(m['kind'], m['kind']) + ' · ' + path.name


def source_note(path):
    """What the watcher wrote next to a clip it cut: whose broadcast it is and where the moment sits in it."""
    try:
        data = json.loads(Path(path).with_suffix('.source.json').read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get('origin') == 'stream_watch' else None


def campaign(data):
    """A Short made from a watcher clip is edited like a stream clip: whole, captions and facecam layout, no story model."""
    meta = ((data.get('source') or {}).get('metadata') or {})
    return dict(kind='gta6_stream', platform=meta.get('platform') or 'twitch') if meta.get('origin') == 'stream_watch' else {}


def produce(s, mid):
    """Hands the raw clip to the Clip Farm's team: a 9:16 Short with captions. Publishing still waits for the owner."""
    m = moment(s, mid)
    if m['status'] not in ('ready', 'produced', 'producing') or not m['file']:
        raise ValueError('Előbb le kell tölteni a részletet.')
    if m['production']:
        return dict(message='Ebből a pillanatból már készül vagy készült Short.')
    from clip_farm import PROJECT
    if not s.db.execute('SELECT 1 FROM projects WHERE id=?', (PROJECT,)).fetchone():
        raise ValueError('A Short elkészítéséhez a Clip Farm projekt csapata kell, de az a projekt nincs meg.')
    import gta6, raw_footage, shutil
    from execution_queue import submit_short
    source = s.safe_path(m['project'], m['file'])
    names = raw_footage.resolve_files(s, PROJECT, [str(source)])
    note = source.with_suffix('.source.json')
    if note.is_file():
        shutil.copy2(note, s.safe_path(PROJECT, names[0]).with_suffix('.source.json'))
    brief = (m['channel'].replace('yt:', '') + ' · ' + (m['game'] or 'élő adás') + ' · ' + KINDS.get(m['kind'], 'chat-csúcs'))[:200]
    tries = s.db.execute("SELECT count(*) FROM short_runs WHERE json_extract(data,'$.origin') LIKE ?", ('watch:' + mid + '%',)).fetchone()[0]
    origin = 'watch:' + mid + (':r' + str(tries) if tries else '')      # a failed attempt must not block a new one (the same origin returns the old run)
    out = submit_short(s, PROJECT, brief, dict(gta6.FORMAT, min_seconds=12, **(dict(publish_to_youtube=True, review_before_upload=False) if settings(s, m['project'])['auto_post'] else {})), origin, local_files=names)
    s.db.execute("UPDATE stream_moments SET status='producing',production=? WHERE id=?", (str(out.get('job') or out.get('run') or 'started'), mid))
    s.db.commit()
    return dict(message='A Short gyártása elindult a Clip Farm csapatával. A kész videó a Publikálás oldalon vár rád.')


NAMES = dict(kaicenat='Kai Cenat', ishowspeed='IShowSpeed', xqc='xQc', caseoh='CaseOh', jynxzi='Jynxzi', stableronaldo='StableRonaldo', jasontheween='JasonTheWeen',
             plaqueboymax='Plaqueboymax', zackrawrr='Zack Rawrr', hasanabi='HasanAbi', agent00='Agent00', summit1g='summit1g', nickmercs='NICKMERCS', tfue='Tfue',
             timthetatman='TimTheTatman', esfandtv='EsfandTV', ohnepixel='ohnePixel', pewdiepie='PewDiePie', illojuan='IlloJuan', rubius='Rubius', ibai='Ibai', auronplay='AuronPlay')


def is_gta(game):
    return bool(re.search(r'grand theft auto\s*(6|vi)\b|\bgta\s*-?\s*(6|vi)\b', str(game or ''), re.I))


_MASK = [(re.compile(r'\b(f+u+c+k\w*)', re.I), lambda m: m.group(1)[0] + '*' * (len(m.group(1)) - 2) + m.group(1)[-1]),
         (re.compile(r'\b(sh[i1]t\w*|b[i1]tch\w*|a+ss+h[o0]le\w*|d[i1]ck\w*|c[o0]ck\w*|pussy|cunt\w*)\b', re.I), lambda m: m.group(1)[0] + '*' * (len(m.group(1)) - 2) + m.group(1)[-1])]
_SLUR = re.compile(r'n[i1]gg|f[a4]gg?[o0]t|retard|tranny', re.I)


def clean_title(text):
    """Strong language costs a Short its reach and its monetisation: it is starred out, and a slur drops the line altogether."""
    text = str(text or '')
    if _SLUR.search(text):
        return ''
    for pattern, repl in _MASK:
        text = pattern.sub(repl, text)
    return text


def audience_factor(viewers):
    """Bigger audience, bigger pull: 100 viewers 0.72, 1 000 about 1.0, 10 000 1.4, 100 000 1.8 (unknown counts as 1 000)."""
    v = float(viewers) if isinstance(viewers, (int, float)) and viewers >= 0 else 1000.0
    return round(0.6 + 0.4 * math.log10(1 + v / 100), 3)


def rank(score, viewers):
    return float(score or 0) * audience_factor(viewers)


def moment_viewers(row):
    try:
        return json.loads(row['detail'] or '{}').get('viewers')
    except (ValueError, TypeError):
        return None


def streamer_title(title, channel, game='Grand Theft Auto VI'):
    """The title of a stream Short: 'Streamer | line | GTA6'. The game tag is only added when the clip really is from GTA 6
    (a rehearsal clip from another game must not be sold as GTA 6)."""
    name = re.sub(r'^yt:', '', str(channel or '')).strip('@ _').lower()
    shown = NAMES.get(name) or name.capitalize()
    is_gta = bool(re.search(r'grand theft auto\s*(6|vi)\b|\bgta\s*-?\s*(6|vi)\b', str(game or ''), re.I))
    body = clean_title(' '.join(str(title or '').split()))
    body = re.sub(r'\s*#?\bGTA\s*-?\s*(6|VI)\b', '', body, flags=re.I)
    for who in sorted({name, shown}, key=len, reverse=True):
        if who:
            body = re.sub(r'\b' + re.escape(who) + r"(?:['\u2019]s)?_?\b", '', body, flags=re.I)
    body = re.sub(r'^[\s|\-\u2013:,_]+|[\s|\-\u2013:,_]+$', '', body)
    head = shown + ' | ' if shown else ''
    tail = ' | GTA6' if is_gta else ''
    body = body[:max(0, 90 - len(head) - len(tail))].rstrip(' |-\u2013:,_')
    return (head + body + tail) if body else (head + ('GTA6' if is_gta else '')).rstrip(' |')[:90]


def moment(s, mid):
    row = s.db.execute('SELECT * FROM stream_moments WHERE id=?', (str(mid),)).fetchone()
    if not row:
        raise ValueError('Ismeretlen pillanat.')
    return dict(row)


def dismiss(s, mid):
    m = moment(s, mid)
    if m['file'] and not m['production']:
        path = s.safe_path(m['project'], m['file'])
        s.db.execute('DELETE FROM artifacts WHERE project=? AND path=?', (m['project'], str(path)))
        path.unlink(missing_ok=True)
        path.with_suffix('.source.json').unlink(missing_ok=True)
    s.db.execute("UPDATE stream_moments SET status='dismissed',file=NULL WHERE id=?", (mid,))
    s.db.commit()
    return dict(message='Elvetve.')


def prune(s, pid, cfg, now):
    """Raw clips nobody used are removed after keep_days; a clip a Short was made from stays with its Short."""
    for m in s.rows("SELECT id FROM stream_moments WHERE project=? AND status IN ('ready','found','failed') AND production IS NULL AND created<?", (pid, now - cfg['keep_days'] * 86400)):
        dismiss(s, m['id'])


def chart(s, pid, channel, now, minutes=30):
    rows = buckets(s, pid, channel, now - minutes * 60)
    by = {r['t']: r['n'] for r in rows}
    start = int((now - minutes * 60) // 15) * 15
    return [dict(t=t, n=sum(by.get(t + k, 0) for k in (0, 5, 10))) for t in range(start, int(now), 15)]


def snapshot(s, pid, channel=None):
    schema(s)
    now = time.time()
    cfg = settings(s, pid)
    live = live_state(s, pid)
    active = watching(cfg, live, now)
    import autonomy
    channels = []
    for c in cfg['channels']:
        st = live['channels'].get(c) or {}
        channels.append(dict(channel=c, live=bool(st.get('live')), viewers=st.get('viewers') if st.get('live') else None, game=st.get('game') or '', title=st.get('title') or '', started=st.get('started'),
                             recording=bool(st.get('vod')), watching=c in active,
                             moments=s.db.execute("SELECT count(*) FROM stream_moments WHERE project=? AND channel=? AND at>? AND status!='dismissed'", (pid, c, now - 86400)).fetchone()[0]))
    channels.sort(key=lambda c: (not c['live'], -(c['viewers'] or 0)))     # the biggest audience first
    focus = channel if channel in cfg['channels'] else (active[0] if active else None)
    moments = []
    for m in s.rows("SELECT * FROM stream_moments WHERE project=? AND status!='dismissed' ORDER BY at DESC LIMIT 80", (pid,)):
        try:
            detail = json.loads(m['detail'] or '{}')
        except ValueError:
            detail = {}
        artifact = None
        if m['file']:
            row = s.db.execute('SELECT id FROM artifacts WHERE project=? AND path=?', (pid, str(s.safe_path(pid, m['file'])))).fetchone()
            artifact = row[0] if row else None
        moments.append(dict(id=m['id'], channel=m['channel'], at=m['at'], duration=m['duration'], score=m['score'], kind=m['kind'], kind_label=KINDS.get(m['kind'], m['kind']),
                            status=m['status'], error=m['error'], game=m['game'], artifact=artifact, produced=bool(m['production']), viewers=detail.get('viewers'),
                            why=('A chat addig alig írt (15 mp alatt átlag ' + str(detail.get('normal')) + ' üzenet), most ' if float(detail.get('normal') or 0) < 1.5 else 'A chat a szokásos ' + str(detail.get('normal')) + ' üzenet helyett ') + str(detail.get('rate')) + ' üzenetet írt 15 mp alatt, ' + str(detail.get('people')) + ' embertől.'
                                + (' ' + str(detail['clip_calls']) + ' néző kérte, hogy vágják ki.' if detail.get('clip_calls') else '')))
    return dict(settings=cfg, channels=channels, moments=moments, focus=focus, chart=chart(s, pid, focus, now) if focus else [],
                gate_open=gate_open(cfg, now), paused=autonomy.paused(s), listener=listener_alive(s, pid), checked=live['checked'],
                counts=dict(live=sum(c['live'] for c in channels), watching=len(active), today=sum(1 for m in moments if m['at'] > now - 86400),
                            ready=sum(m['status'] == 'ready' for m in moments)),
                defaults=dict(game=DEFAULT['game'], not_before=DEFAULT['not_before']))


def dispatch(s, op, args=None):
    args = args or {}
    schema(s)
    pid = str(args.get('project') or '') or (s.db.execute('SELECT id FROM projects WHERE kind=?', (KIND,)).fetchone() or [None])[0]
    if not pid or s.project(pid).get('kind') != KIND:
        raise ValueError('Ez nem élő adás figyelő projekt.')
    if op == 'watch_snapshot':
        return snapshot(s, pid, args.get('channel'))
    if op == 'watch_save':
        cfg = save(s, pid, args.get('patch'))
        return dict(settings=cfg, message='A figyelő ' + ('be van kapcsolva.' if cfg['enabled'] else 'ki van kapcsolva.') if 'enabled' in (args.get('patch') or {}) else 'Mentve.')
    if op == 'watch_fetch':
        return fetch(s, args.get('id'))
    if op == 'watch_produce':
        return produce(s, args.get('id'))
    if op == 'watch_dismiss':
        return dismiss(s, args.get('id'))
    raise ValueError('Ismeretlen figyelő-művelet.')
