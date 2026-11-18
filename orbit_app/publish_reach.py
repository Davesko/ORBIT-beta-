"""Elérés: the views of every account connected to ORBIT, with an account filter.

A measurement runs in the isolated media runtime (the logins live in the Keychain, never in this process): one detached
process per account writes integrations/social/<key>/reach.json. This module starts them (at most every 3 hours per
account, or on the owner's button), reads the files and adds up what the page shows. A view counter that a platform does
not give (TikTok without the video.list permission, Facebook's reels) is shown as missing, never estimated.
The daily gain comes from ORBIT's own daily snapshots of each account's total, so it builds up from the first measurement.
"""
import json, os, subprocess, time
from datetime import date, timedelta
from pathlib import Path

EVERY = 3 * 3600
FORCE_EVERY = 300


def schema(s):
    s.db.execute('CREATE TABLE IF NOT EXISTS social_reach_log(account TEXT NOT NULL,day TEXT NOT NULL,views INTEGER,PRIMARY KEY(account,day))')
    s.db.commit()


def folder(s, key):
    return s.root / 'integrations/social' / key


def read(s, key):
    try:
        return json.loads((folder(s, key) / 'reach.json').read_text())
    except (OSError, ValueError):
        return {}


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def ingest(s, row):
    """A finished measurement process leaves its answer in reach-out.txt; turn it into reach.json."""
    f = folder(s, row['key'])
    lock, out = f / 'reach.lock', f / 'reach-out.txt'
    if not lock.exists():
        return
    try:
        pid = lock.read_text().strip()
    except OSError:
        pid = ''
    if alive(pid) and time.time() - lock.stat().st_mtime < 240:
        return
    old = read(s, row['key'])
    try:
        data = json.loads(out.read_text().strip().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        data = dict(ok=False, message='A mérés nem adott értelmezhető választ.')
    new = dict(old, fetched=time.time())
    if data.get('ok'):
        new.update(channel=data.get('channel') or {}, items=data.get('items') or [], error='')
        views = (new['channel'].get('views') if new['channel'].get('views') is not None else sum(i.get('views') or 0 for i in new['items']))
        s.db.execute('INSERT OR REPLACE INTO social_reach_log(account,day,views) VALUES(?,?,?)', (row['id'], date.today().isoformat(), int(views or 0)))
        s.db.commit()
    else:
        new['error'] = str(data.get('message') or 'A mérés nem sikerült.')[:300]
    f.mkdir(parents=True, exist_ok=True, mode=0o700)
    (f / 'reach.json').write_text(json.dumps(new))
    lock.unlink(missing_ok=True)


def start(s, row, force=False):
    python = s.root / 'media-runtime/bin/python'
    if not python.is_file() or row['status'] != 'connected':
        return False
    f = folder(s, row['key'])
    f.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (f / 'reach.lock').exists():
        return False
    last = float(read(s, row['key']).get('fetched') or 0)
    if time.time() - last < (FORCE_EVERY if force else EVERY):
        return False
    script, args = ('youtube_runtime.py', ['reach', str(s.root), row['key']]) if row['platform'] == 'youtube' else ('social_runtime.py', ['reach', str(s.root), row['key']])
    (f / 'reach-in.json').write_text(json.dumps(dict(platform=row['platform'], limit=150)))
    with (f / 'reach-in.json').open('rb') as stdin, (f / 'reach-out.txt').open('wb') as stdout, (f / 'upload.log').open('ab') as errors:
        process = subprocess.Popen([str(python), str(Path(__file__).with_name(script)), *args], stdin=stdin, stdout=stdout, stderr=errors, start_new_session=True)
    (f / 'reach.lock').write_text(str(process.pid))
    return True


def tick(s):
    schema(s)
    for row in s.rows("SELECT * FROM social_accounts WHERE status IN ('connected','expired')"):
        ingest(s, row)
        if row['status'] == 'connected':
            start(s, row)


def snapshot(s, account=None):
    schema(s)
    rows = s.rows('SELECT * FROM social_accounts ORDER BY platform,created')
    for row in rows:
        ingest(s, row)
    mine = {}
    for p in s.rows("SELECT account,external_id FROM social_posts WHERE external_id!='' AND status='published'"):
        mine.setdefault(p['account'], set()).add(p['external_id'])
    accounts, items, today = [], [], date.today()
    for row in rows:
        data = read(s, row['key'])
        ch = data.get('channel') or {}
        its = data.get('items') or []
        total = ch.get('views') if ch.get('views') is not None else (sum(i.get('views') or 0 for i in its) if its else None)
        running = (folder(s, row['key']) / 'reach.lock').exists()
        accounts.append(dict(id=row['id'], label=row['label'], platform=row['platform'], handle=row['handle'], status=row['status'], fetched=data.get('fetched') or 0,
                             error=data.get('error') or '', running=running, views=total, subscribers=ch.get('subscribers'), videos=ch.get('videos') if ch.get('videos') is not None else len(its)))
        if account and account != row['id']:
            continue
        for i in its:
            items.append(dict(i, account=row['id'], account_label=row['label'], platform=row['platform'], orbit=str(i.get('id')) in mine.get(row['id'], set())))
    chosen = [a for a in accounts if not account or a['id'] == account]
    def total(key):
        vals = [a[key] for a in chosen if a[key] is not None]
        return sum(vals) if vals else None
    sums = lambda k: sum(i.get(k) or 0 for i in items)
    # Daily gain from the account totals ORBIT logged on earlier days.
    gains, first = {}, None
    for a in chosen:
        logs = s.rows('SELECT day,views FROM social_reach_log WHERE account=? ORDER BY day', (a['id'],))
        for before, after in zip(logs, logs[1:]):
            gains[after['day']] = gains.get(after['day'], 0) + max(0, (after['views'] or 0) - (before['views'] or 0))
        if logs:
            first = min(first or logs[0]['day'], logs[0]['day'])
    series = [dict(day=(today - timedelta(days=n)).isoformat(), views=gains.get((today - timedelta(days=n)).isoformat())) for n in range(27, -1, -1)]
    items.sort(key=lambda i: i.get('views') or 0, reverse=True)
    return dict(accounts=accounts, items=items[:300], filter=account or '', series=series, since=first,
                totals=dict(views=total('views'), subscribers=total('subscribers'), videos=total('videos'), likes=sums('likes'), comments=sums('comments'),
                            gain28=sum(g for g in gains.values()) if gains else None),
                fetched=max([a['fetched'] for a in chosen] or [0]), running=any(a['running'] for a in chosen))


def dispatch(s, op, args=None):
    args = args or {}
    schema(s)
    if op == 'publish_reach_refresh':
        started = 0
        for row in s.rows("SELECT * FROM social_accounts WHERE status='connected'"):
            if args.get('account') and args['account'] != row['id']:
                continue
            started += bool(start(s, row, force=True))
        return dict(started=started, message=(str(started) + ' fiók mérése elindult.') if started else 'Nincs mit frissíteni: a legutóbbi mérés friss, vagy még fut.')
    return snapshot(s, str(args.get('account') or '') or None)
