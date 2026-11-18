"""Publikálás-központ: every finished video of every project, posted to several accounts on several platforms.

The owner (14 Nov): one general Publishing page where the videos made in all projects can be connected to more than
one YouTube account and to Instagram / TikTok accounts, so several channels are managed and one video goes to several
places.

- An account is a row in social_accounts; its login never enters the database or a project. YouTube logins are the
  same Google OAuth as before, kept in the Keychain under the account's own key (a project's old channel connection
  is listed as an account as it is, without a new login). Instagram, Facebook and TikTok tokens are kept in the
  Keychain by social_runtime.py.
- A post is one video going to one account (social_posts). Nothing is posted without the owner pressing the button:
  a route (project -> accounts) only pre-selects the accounts, and a scheduled post is an order the owner gave.
- The same video is never sent twice to the same account; a failed post can be retried, and one that already got an
  id from the platform cannot (the owner checks the platform first).
"""
import json, re, subprocess, time, uuid
from pathlib import Path

import publish_library as lib
import publish_plan as plan
import publish_score as pubscore
import publish_learn as learn

PLATFORMS = {
    'youtube': dict(label='YouTube', kinds='Shorts és videó', login='google'),
    'instagram': dict(label='Instagram', kinds='Reels', login='token'),
    'facebook': dict(label='Facebook-oldal', kinds='Reels', login='token'),
    'tiktok': dict(label='TikTok', kinds='videó', login='tiktok'),
}
PRIVACY = ('public', 'unlisted', 'private')
# What each platform accepts for a caption; the title is YouTube's own field.
LIMITS = dict(youtube=5000, instagram=2200, facebook=2200, tiktok=2200)
MAX_BYTES = 1024 ** 3
UNTESTED = 'Ez a csatlakozó a hivatalos leírás szerint készült, de éles fiókkal még nem volt kipróbálva: az első feltöltést ellenőrizd a platformon.'


def schema(s):
    s.db.executescript("""
    CREATE TABLE IF NOT EXISTS social_accounts(id TEXT PRIMARY KEY,platform TEXT NOT NULL,label TEXT NOT NULL,key TEXT NOT NULL UNIQUE,
        handle TEXT DEFAULT '',external_id TEXT DEFAULT '',status TEXT DEFAULT 'new',error TEXT DEFAULT '',created REAL,meta TEXT DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS social_posts(id TEXT PRIMARY KEY,artifact TEXT NOT NULL,project TEXT NOT NULL,account TEXT NOT NULL,platform TEXT NOT NULL,
        title TEXT,caption TEXT,privacy TEXT,made_for_kids INTEGER DEFAULT 0,status TEXT NOT NULL,job TEXT,url TEXT DEFAULT '',external_id TEXT DEFAULT '',
        error TEXT DEFAULT '',created REAL,scheduled REAL,finished REAL);
    CREATE INDEX IF NOT EXISTS social_posts_artifact ON social_posts(artifact,account);
    CREATE TABLE IF NOT EXISTS social_routes(project TEXT NOT NULL,account TEXT NOT NULL,PRIMARY KEY(project,account));
    """)
    s.db.commit()
    lib.schema(s)


def runtime(s, script, args, payload=None, timeout=60):
    """One call into the isolated media runtime (Keychain and network live there, never in the app's own process)."""
    python = s.root / 'media-runtime/bin/python'
    if not python.is_file():
        raise ValueError('A médiafuttató nincs telepítve, a fiókok kezeléséhez szükség van rá.')
    done = subprocess.run([str(python), str(Path(__file__).with_name(script)), *args], input=json.dumps(payload or {}),
                          capture_output=True, text=True, timeout=timeout)
    try:
        out = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ValueError('A fiókkezelő nem adott értelmezhető választ.') from None
    if not out.get('ok'):
        raise ValueError(str(out.get('message') or 'A művelet nem sikerült.')[:500])
    return out


# ---------------------------------------------------------------- accounts

def adopt_project_channels(s):
    """A YouTube channel connected to a project before the hub existed is an account too: same login, no new sign-in."""
    base = s.root / 'integrations/youtube'
    if not base.is_dir():
        return
    known = {r['key'] for r in s.rows("SELECT key FROM social_accounts WHERE platform='youtube'")}
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    for folder in sorted(base.iterdir()):
        if folder.name in known or folder.name not in names:
            continue
        try:
            status = json.loads((folder / 'status.json').read_text())
        except (OSError, ValueError):
            continue
        if not status.get('channel'):
            continue
        twin = s.db.execute("SELECT id FROM social_accounts WHERE platform='youtube' AND ((?!='' AND external_id=?) OR lower(handle)=lower(?) OR lower(label)=lower(?))",
                            (str(status.get('channel_id') or ''), str(status.get('channel_id') or ''), str(status['channel']), str(status['channel']))).fetchone()
        if twin:
            # The same channel connected again (for example from a project) is the same account: its sign-in is picked up by merge_duplicates.
            s.db.execute('INSERT OR IGNORE INTO social_routes(project,account) VALUES(?,?)', (folder.name, twin['id']))
            continue
        s.db.execute('INSERT OR IGNORE INTO social_accounts(id,platform,label,key,handle,external_id,status,created,meta) VALUES(?,?,?,?,?,?,?,?,?)',
                     ('acct-' + uuid.uuid4().hex[:12], 'youtube', str(status['channel'])[:80], folder.name, str(status['channel'])[:80],
                      str(status.get('channel_id') or ''), 'connected' if status.get('connected') else 'expired', time.time(),
                      json.dumps(dict(project=folder.name))))
        s.db.execute('INSERT OR IGNORE INTO social_routes SELECT ?,id FROM social_accounts WHERE key=?', (folder.name, folder.name))
    s.db.commit()


def merge_duplicates(s):
    """One channel is one account. A channel connected twice (reconnecting makes a second sign-in folder) is folded into the oldest
    account: its posts and project routes move there, and when only the newer sign-in works, the old account takes it over."""
    rows = s.rows("SELECT * FROM social_accounts ORDER BY created")
    groups = {}
    for r in rows:
        ident = (r['external_id'] or '').strip() or (r['handle'] or '').strip().lower()
        if ident:
            groups.setdefault((r['platform'], ident.lower()), []).append(dict(r))
    for group in groups.values():
        keep, others = group[0], group[1:]
        for dup in others:
            if s.db.execute("SELECT 1 FROM social_posts WHERE account=? AND status IN ('queued','uploading')", (dup['id'],)).fetchone():
                continue
            s.db.execute('UPDATE social_posts SET account=? WHERE account=?', (keep['id'], dup['id']))
            s.db.execute('INSERT OR IGNORE INTO social_routes SELECT project,? FROM social_routes WHERE account=?', (keep['id'], dup['id']))
            s.db.execute('DELETE FROM social_routes WHERE account=?', (dup['id'],))
            s.db.execute('DELETE FROM social_reach_log WHERE account=?', (dup['id'],)) if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='social_reach_log'").fetchone() else None
            s.db.execute('DELETE FROM social_accounts WHERE id=?', (dup['id'],))
            if dup['status'] == 'connected' and keep['status'] != 'connected':
                s.db.execute("UPDATE social_accounts SET key=?,status='connected',handle=?,external_id=?,error='' WHERE id=?",
                             (dup['key'], dup['handle'] or keep['handle'], dup['external_id'] or keep['external_id'], keep['id']))
                keep.update(key=dup['key'], status='connected')
    s.db.commit()


def account(s, aid):
    row = s.db.execute('SELECT * FROM social_accounts WHERE id=?', (str(aid),)).fetchone()
    if not row:
        raise ValueError('Ismeretlen fiók.')
    return dict(row)


def youtube_state(s, row):
    from youtube import read_state
    state = read_state(s.root, row['key'])
    status = 'connected' if state['connected'] else 'waiting' if state['auth_pending'] else 'expired' if state.get('error') else 'new'
    if (status, state.get('channel') or row['handle']) != (row['status'], row['handle']):
        s.db.execute('UPDATE social_accounts SET status=?,handle=?,external_id=?,error=? WHERE id=?',
                     (status, state.get('channel') or row['handle'], state.get('channel_id') or row['external_id'], state.get('error') or '', row['id']))
        s.db.commit()
    return dict(status=status, handle=state.get('channel') or row['handle'], error=state.get('error') or '', configured=state['configured'])


def accounts(s):
    schema(s)
    adopt_project_channels(s)
    for row in s.rows("SELECT * FROM social_accounts WHERE platform='youtube'"):
        youtube_state(s, row)          # learns each sign-in's channel, so a second sign-in of the same channel is recognised
    merge_duplicates(s)
    out = []
    routes = s.rows('SELECT project,account FROM social_routes')
    names = {r['id']: (r['name'], r['kind'] if 'kind' in r.keys() else '') for r in s.rows('SELECT * FROM projects')}
    for row in s.rows('SELECT * FROM social_accounts ORDER BY platform,created'):
        item = dict(id=row['id'], platform=row['platform'], platform_label=PLATFORMS[row['platform']]['label'], label=row['label'],
                    handle=row['handle'], status=row['status'], error=row['error'], created=row['created'], configured=True,
                    note='' if row['platform'] == 'youtube' else UNTESTED)
        if row['platform'] == 'youtube':
            item.update(youtube_state(s, row))
        try:
            meta = json.loads(row['meta'] or '{}')
        except ValueError:
            meta = {}
        item['legacy_project'] = meta.get('project')
        derived = sorted({lib.type_of(names.get(r['project'], ('', ''))[0], names.get(r['project'], ('', ''))[1], '') for r in routes if r['account'] == row['id']} - {'other'})
        item.update(plan.settings(s, row, derived))
        item['posts'] = s.db.execute("SELECT count(*) FROM social_posts WHERE account=? AND status='published'", (row['id'],)).fetchone()[0]
        out.append(item)
    return out


def shared_google_client(s):
    """The Google OAuth desktop client is one per owner: any already imported copy serves every YouTube account."""
    base = s.root / 'integrations/youtube'
    for path in sorted(base.glob('*/client.json')) if base.is_dir() else []:
        return path
    return None


def account_add(s, platform, label=''):
    schema(s)
    if platform not in PLATFORMS:
        raise ValueError('Ismeretlen platform.')
    if s.db.execute('SELECT count(*) FROM social_accounts').fetchone()[0] >= 40:
        raise ValueError('Legfeljebb 40 fiók kezelhető.')
    aid = 'acct-' + uuid.uuid4().hex[:12]
    label = ' '.join(str(label or '').split())[:80] or PLATFORMS[platform]['label'] + '-fiók'
    s.db.execute('INSERT INTO social_accounts(id,platform,label,key,created) VALUES(?,?,?,?,?)', (aid, platform, label, aid, time.time()))
    s.db.commit()
    return dict(id=aid, message='Fiók hozzáadva. Most csatlakoztasd.')


def account_connect(s, aid, args=None, opener=None):
    """Starts the platform's own sign-in. YouTube and TikTok open the browser; Instagram and Facebook take the token the
    owner created in their own Meta developer page (typed into ORBIT's window, stored only in the Keychain)."""
    row = account(s, aid)
    args = args or {}
    opener = opener or (lambda url: subprocess.run(['/usr/bin/open', url], check=False, capture_output=True))
    if row['platform'] == 'youtube':
        import shutil
        from youtube import connect, folder
        target = folder(s.root, row['key']) / 'client.json'
        if not target.exists():
            source = shared_google_client(s)
            if not source:
                raise ValueError('Előbb importáld egyszer a Google OAuth JSON-t: Kapcsolatok → YouTube. Utána bármennyi csatorna csatlakoztatható.')
            shutil.copy2(source, target)
            target.chmod(0o600)
        url = connect(s.root, row['key'])
        if not url.startswith('https://accounts.google.com/'):
            raise ValueError('Érvénytelen bejelentkezési cím.')
        opener(url)
        s.db.execute("UPDATE social_accounts SET status='waiting',error='' WHERE id=?", (aid,))
        s.db.commit()
        return dict(message='A böngészőben megnyílt a Google-bejelentkezés. Válaszd ki azt a csatornát, amelyiket ehhez a fiókhoz kötöd.')
    if row['platform'] == 'tiktok' and not args.get('token'):
        key, secret = str(args.get('client_key') or '').strip(), str(args.get('client_secret') or '').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', key) or not 8 <= len(secret) <= 200:
            raise ValueError('Add meg a saját TikTok fejlesztői alkalmazásod Client key és Client secret értékét.')
        out = runtime(s, 'social_runtime.py', ['tiktok_connect', str(s.root), row['key']], dict(client_key=key, client_secret=secret), timeout=20)
        if not str(out.get('url', '')).startswith('https://www.tiktok.com/'):
            raise ValueError('Érvénytelen bejelentkezési cím.')
        opener(out['url'])
        s.db.execute("UPDATE social_accounts SET status='waiting',error='' WHERE id=?", (aid,))
        s.db.commit()
        return dict(message='A böngészőben megnyílt a TikTok-bejelentkezés. A TikTok-alkalmazásodban a ' + out.get('redirect', '') + ' címnek engedélyezve kell lennie.')
    token = str(args.get('token') or '').strip()
    if not 20 <= len(token) <= 600 or re.search(r'\s', token):
        raise ValueError('Illeszd be a hozzáférési tokent (szóköz nélkül).')
    out = runtime(s, 'social_runtime.py', ['verify', str(s.root), row['key']], dict(platform=row['platform'], token=token), timeout=20)
    s.db.execute("UPDATE social_accounts SET status='connected',handle=?,external_id=?,error='',meta=? WHERE id=?",
                 (str(out.get('handle') or '')[:80], str(out.get('external_id') or '')[:64], json.dumps(dict(connected=time.time(), expires=out.get('expires'))), aid))
    s.db.commit()
    return dict(message='Csatlakoztatva: ' + str(out.get('handle') or row['label']))


def refresh_waiting(s):
    """A browser sign-in finishes outside ORBIT; its result file says how it went."""
    for row in s.rows("SELECT * FROM social_accounts WHERE platform='tiktok' AND status='waiting'"):
        try:
            state = json.loads((s.root / 'integrations/social' / row['key'] / 'auth.json').read_text())
        except (OSError, ValueError):
            continue
        if state.get('status') == 'done':
            s.db.execute("UPDATE social_accounts SET status='connected',handle=?,external_id=?,error='' WHERE id=?",
                         (str(state.get('handle') or '')[:80], str(state.get('external_id') or '')[:64], row['id']))
        elif state.get('status') == 'failed' or time.time() - float(state.get('created') or 0) > 320:
            s.db.execute("UPDATE social_accounts SET status='new',error=? WHERE id=?", (str(state.get('error') or 'A bejelentkezés lejárt.')[:300], row['id']))
    s.db.commit()


def account_remove(s, aid):
    row = account(s, aid)
    if s.db.execute("SELECT 1 FROM social_posts WHERE account=? AND status IN ('queued','uploading')", (aid,)).fetchone():
        raise ValueError('Ennek a fióknak épp fut feltöltése. Várd meg vagy állítsd le előbb.')
    try:
        if row['platform'] == 'youtube':
            runtime(s, 'youtube_runtime.py', ['disconnect', str(s.root), row['key']], timeout=20)
        else:
            runtime(s, 'social_runtime.py', ['forget', str(s.root), row['key']], timeout=20)
    except ValueError:
        pass   # a login already gone must not keep the account in the list
    s.db.execute('DELETE FROM social_routes WHERE account=?', (aid,))
    s.db.execute("DELETE FROM social_posts WHERE account=? AND status IN ('scheduled','failed','cancelled')", (aid,))
    s.db.execute('DELETE FROM social_accounts WHERE id=?', (aid,))
    s.db.commit()
    return dict(message='A fiók leválasztva erről a gépről. A platformon lévő videók megmaradnak.')


def account_rename(s, aid, label):
    account(s, aid)
    label = ' '.join(str(label or '').split())[:80]
    if not label:
        raise ValueError('Adj nevet a fióknak.')
    s.db.execute('UPDATE social_accounts SET label=? WHERE id=?', (label, aid))
    s.db.commit()
    return dict(message='Átnevezve.')


def route(s, pid, aid, on):
    s.project(pid)
    account(s, aid)
    if on:
        s.db.execute('INSERT OR IGNORE INTO social_routes VALUES(?,?)', (pid, aid))
    else:
        s.db.execute('DELETE FROM social_routes WHERE project=? AND account=?', (pid, aid))
    s.db.commit()
    return dict(message='Mentve.')


# ---------------------------------------------------------------- videos

def video_file(s, artifact):
    row = s.db.execute("SELECT * FROM artifacts WHERE id=? AND kind='video'", (str(artifact),)).fetchone()
    if not row:
        raise ValueError('Nem található kész videó.')
    path = lib.finished_ok(s, row)
    if not path:
        raise ValueError('Csak elkészült videó tehető közzé (render vagy szimuláció).')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('A videó nagyobb 1 GB-nál.')
    return dict(row), path


def facts(path, s=None, aid=None):
    if s is not None and aid:
        return lib.facts(s, aid, path, [5])
    try:
        m = json.loads(path.with_suffix('.json').read_text())
        width, height, duration = int(m['width']), int(m['height']), float(m['duration'])
    except (OSError, ValueError, KeyError, TypeError):
        return dict(width=None, height=None, duration=None, short=None)
    return dict(width=width, height=height, duration=round(duration, 1), short=height > width and duration <= 180)


def upload_text(s, row):
    return lib.upload_text(s, row)


def suggestion(s, row, kind='other', short=None, path=None):
    review = None
    if s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='publication_reviews'").fetchone():
        review = s.db.execute('SELECT title,description,made_for_kids FROM publication_reviews WHERE artifact=?', (row['id'],)).fetchone()
    inf = lib.info(s, row, path or Path(row['path']), kind)
    if review and review['title'] and not inf['title']:
        inf['title'] = review['title']
    if review and review['description'] and not inf['description']:
        inf['description'] = review['description']
    made = lib.copy_for(inf, kind, bool(short), 'youtube')
    return dict(title=made['title'], caption=made['caption'], hook=inf['hook'], made_for_kids=bool(review['made_for_kids']) if review else False,
                variants=lib.variants(inf, kind, bool(short)))


def project_channel_posts(s, row, path):
    """Uploads made on the project's own page before the hub (or from its review list) count as published too."""
    base = s.root / 'projects' / row['project']
    try:
        name = str(path.relative_to(base.resolve()))
    except ValueError:
        return []
    out = []
    for job in s.rows("SELECT id,status FROM jobs WHERE project=? AND kind='youtube_upload' AND json_extract(payload,'$.name')=? AND json_extract(payload,'$.social_post') IS NULL ORDER BY created DESC LIMIT 1", (row['project'], name)):
        url = ''
        try:
            url = json.loads((s.root / 'integrations/youtube' / row['project'] / ('receipt-' + job['id'] + '.json')).read_text()).get('url', '')
        except (OSError, ValueError):
            pass
        status = {'done': 'published', 'queued': 'queued', 'running': 'uploading', 'failed': 'failed', 'cancelled': 'cancelled'}.get(job['status'], 'queued')
        out.append(dict(id='project-' + job['id'], account=None, account_key=row['project'], platform='youtube', status=status, url=url, error='', legacy=True))
    return out


def videos(s, limit=400):
    schema(s)
    names = {r['id']: (r['name'], r['kind'] if 'kind' in r.keys() else '') for r in s.rows('SELECT * FROM projects')}
    gone = set()
    if s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_trash'").fetchone():
        gone = {r['id'] for r in s.rows('SELECT id FROM project_trash')}
    keys = {r['key']: r['id'] for r in s.rows('SELECT id,key FROM social_accounts')}
    posts = {}
    for p in s.rows('SELECT * FROM social_posts ORDER BY created'):
        posts.setdefault(p['artifact'], []).append({k: p[k] for k in ('id', 'account', 'platform', 'status', 'url', 'error', 'scheduled', 'finished', 'title')})
    metas = {r['artifact']: r for r in s.rows('SELECT * FROM social_video_meta')}
    hist = learn.history(s)
    budget = [25]
    seen, out = set(), []
    for row in s.rows("SELECT * FROM artifacts WHERE kind='video' AND " + lib.FINISHED_SQL + " ORDER BY created DESC LIMIT ?", (limit * 2,)):
        if row['project'] not in names or row['project'] in gone:
            continue
        path = lib.finished_ok(s, row)
        if not path or str(path) in seen:
            continue
        seen.add(str(path))
        pname, pkind = names[row['project']]
        kind = lib.type_of(pname, pkind, path)
        mine = list(posts.get(row['id'], []))
        for legacy in project_channel_posts(s, row, path):
            legacy['account'] = keys.get(legacy.pop('account_key'))
            if not any(p['account'] == legacy['account'] and p['status'] == 'published' for p in mine):
                mine.append(legacy)
        has = lambda *st: any(p['status'] in st for p in mine)
        state = 'active' if has('queued', 'uploading') else 'scheduled' if has('scheduled') else 'published' if has('published') else 'failed' if has('failed') else 'new'
        f = lib.facts(s, row['id'], path, budget)
        meta = metas.get(row['id'])
        try:
            thumbs = json.loads(meta['thumbs'] or '[]') if meta else []
        except ValueError:
            thumbs = []
        sug = suggestion(s, row, kind, f['short'], path)
        run = lib.run_of(s, row, path) if kind == 'clip' else None
        mom = run['moment'] if run else None
        rated = pubscore.compute(kind, f, sug['title'], run, mom, learn.factor(hist, (mom or {}).get('channel')) if mom else None)
        quality = lib.quality(s, row, path, kind)
        if quality and quality['status'] != 'verified':
            rated['score'] = min(rated['score'], 39)
        out.append(dict(id=row['id'], project=row['project'], project_name=pname, name=row['name'], created=row['created'], bytes=path.stat().st_size,
                        type=kind, state=state, posts=mine, hidden=bool(meta and meta['hidden']), thumbs=len(thumbs), thumb=meta['thumb'] if meta else 0,
                        quality=quality, score=rated['score'], score_parts=rated['parts'], score_basis=rated['basis'],
                        **f, **sug))
        if len(out) >= limit:
            break
    s.db.commit()
    return out


# ---------------------------------------------------------------- posting

def post(s, artifact, targets, title, caption='', privacy='public', made_for_kids=False, when=None, plan=None, accept_unverified=False):
    """Queues one video to the chosen accounts. The owner pressed the button: this is the approval.

    `plan` gives every account its own time and text: [{account, when, title, caption}]; `when` None means now."""
    schema(s)
    row, path = video_file(s, artifact)
    if plan is None:
        plan = [dict(account=a, when=when) for a in (targets if isinstance(targets, list) else [])]
    if not isinstance(plan, list) or not 1 <= len(plan) <= 12:
        raise ValueError('Válassz legalább egy fiókot.')
    if privacy not in PRIVACY or type(made_for_kids) is not bool:
        raise ValueError('Érvénytelen láthatóság vagy célközönség.')
    quality = lib.quality(s, row, path, lib.type_of(s.project(row['project']).get('name'), '', path))
    if quality and quality['status'] != 'verified' and accept_unverified is not True:
        raise ValueError('Ennek a történetnek nincs sikeres, végleges ellenőrzése (' + quality['status'] + ': ' + (quality['note'] or 'nem ellenőrzött') + '). Nézd át, majd jelöld, hogy vállalod.')
    info = facts(path, s, artifact)
    made, seen = [], set()
    for item in plan:
        aid = item.get('account')
        if aid in seen:
            continue
        seen.add(aid)
        acc = account(s, aid)
        platform = acc['platform']
        t = ' '.join(str(item.get('title') if item.get('title') is not None else title or '').split())
        c = str(item.get('caption') if item.get('caption') is not None else caption or '').strip()
        scheduled = None
        if item.get('when') is not None:
            scheduled = float(item['when'])
            if not time.time() - 60 <= scheduled <= time.time() + 90 * 86400:
                raise ValueError(acc['label'] + ': az ütemezett időpont a következő 90 napban legyen.')
            if scheduled < time.time() + 30:
                scheduled = None
        if (youtube_state(s, acc)['status'] if platform == 'youtube' else acc['status']) != 'connected':
            raise ValueError(acc['label'] + ': a fiók nincs csatlakoztatva.')
        if platform == 'youtube' and not 1 <= len(t) <= 100:
            raise ValueError('A YouTube-hoz 1–100 karakteres cím kell.')
        if len(c) > LIMITS[platform]:
            raise ValueError(PLATFORMS[platform]['label'] + ': a szöveg legfeljebb ' + str(LIMITS[platform]) + ' karakter lehet.')
        if platform != 'youtube' and info['short'] is False:
            raise ValueError(PLATFORMS[platform]['label'] + ': álló, legfeljebb 3 perces videó tehető közzé.')
        old = s.db.execute("SELECT id,status,external_id FROM social_posts WHERE artifact=? AND account=? ORDER BY created DESC LIMIT 1", (artifact, aid)).fetchone()
        if old and old['status'] in ('queued', 'uploading', 'scheduled', 'published'):
            made.append(dict(id=old['id'], account=aid, existing=True))
            continue
        if old and old['external_id']:
            raise ValueError(acc['label'] + ': ez a videó már kapott azonosítót a platformtól. Ellenőrizd ott, mielőtt újra feltöltöd.')
        pid = uuid.uuid4().hex
        s.db.execute('INSERT INTO social_posts(id,artifact,project,account,platform,title,caption,privacy,made_for_kids,status,created,scheduled) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                     (pid, artifact, row['project'], aid, platform, t[:100], c, privacy, int(made_for_kids), 'scheduled' if scheduled else 'queued', time.time(), scheduled))
        if not scheduled:
            enqueue(s, pid)
        made.append(dict(id=pid, account=aid, existing=False, scheduled=scheduled))
    s.db.commit()
    fresh = [m for m in made if not m['existing']]
    later = sum(bool(m['scheduled']) for m in fresh)
    msg = 'Ez a videó ezekre a fiókokra már fel van adva.' if not fresh else (str(len(fresh)) + ' feltöltés: ' + (str(later) + ' ütemezve' if later else '') + (', ' if later and later < len(fresh) else '') + (str(len(fresh) - later) + ' most indul' if later < len(fresh) else '') + '.')
    return dict(posts=made, message=msg)


def enqueue(s, post_id):
    p = s.db.execute('SELECT * FROM social_posts WHERE id=?', (post_id,)).fetchone()
    agent = s.db.execute('SELECT id FROM agents WHERE project=? ORDER BY rowid LIMIT 1', (p['project'],)).fetchone()
    if not agent:
        raise ValueError('A videó projektjében nincs ügynök, amelyik a feltöltést vinné.')
    acc = account(s, p['account'])
    jid = s.enqueue(agent['id'], PLATFORMS[p['platform']]['label'] + '-feltöltés · ' + acc['label'] + ' · ' + (p['title'] or 'videó'), 'youtube_upload',
                    payload=dict(social_post=post_id, platform=p['platform']), commit=False)
    s.db.execute("UPDATE social_posts SET status='queued',job=?,error='' WHERE id=?", (jid, post_id))
    return jid


def publish_now(s, post_id):
    """A scheduled post goes out now: its time is dropped and the upload is queued like any other."""
    p = s.db.execute('SELECT * FROM social_posts WHERE id=?', (str(post_id),)).fetchone()
    if not p or p['status'] != 'scheduled':
        raise ValueError('Csak ütemezett közzététel indítható azonnal.')
    s.db.execute('UPDATE social_posts SET scheduled=NULL WHERE id=?', (p['id'],))
    enqueue(s, p['id'])
    s.db.commit()
    return dict(message='A feltöltés most indul.')


def cancel(s, post_id):
    p = s.db.execute('SELECT * FROM social_posts WHERE id=?', (str(post_id),)).fetchone()
    if not p:
        raise ValueError('Ismeretlen feltöltés.')
    if p['status'] == 'scheduled':
        s.db.execute('DELETE FROM social_posts WHERE id=?', (p['id'],))
    elif p['status'] == 'queued' and s.db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status='queued'", (p['job'],)).rowcount:
        s.db.execute("UPDATE social_posts SET status='cancelled',finished=? WHERE id=?", (time.time(), p['id']))
    else:
        raise ValueError('Ez a feltöltés már fut vagy lezárult; a platformon ellenőrizd.')
    s.db.commit()
    return dict(message='Visszavonva.')


def retry(s, post_id, confirmed_absent=False):
    p = s.db.execute('SELECT * FROM social_posts WHERE id=?', (str(post_id),)).fetchone()
    if not p or p['status'] not in ('failed', 'cancelled'):
        raise ValueError('Csak sikertelen vagy leállított feltöltés próbálható újra.')
    if p['external_id']:
        raise ValueError('A videó már kapott azonosítót a platformtól. Ne töltsd fel újra; ellenőrizd ott.')
    if confirmed_absent is not True:
        raise ValueError('Előbb ellenőrizd és jelöld, hogy a videó nem került fel.')
    enqueue(s, p['id'])
    s.db.commit()
    return dict(message='Újra sorba állt.')


def run_post(s, job):
    """The upload lane's work for one post. The platform's id is saved before anything else can fail."""
    import os, signal
    payload = json.loads(job['payload'])
    p = s.db.execute('SELECT * FROM social_posts WHERE id=?', (payload['social_post'],)).fetchone()
    if not p:
        raise ValueError('A feltöltés adatai nem találhatók.')
    acc = account(s, p['account'])
    _, path = video_file(s, p['artifact'])
    folder = s.root / 'integrations/social' / acc['key']
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    progress = folder / ('upload-' + job['id'] + '.json')
    label = PLATFORMS[p['platform']]['label']
    request = dict(source=str(path), title=p['title'] or '', description=p['caption'] or '', caption=p['caption'] or '', made_for_kids=bool(p['made_for_kids']),
                   privacy=p['privacy'] or 'public', progress=str(progress), platform=p['platform'], category=payload.get('category') or category_for(s, p['project']))
    cover = lib.thumb_file(s, dict(id=p['artifact'], project=p['project']))
    if cover and p['platform'] == 'youtube':
        request['thumbnail'] = str(cover)
    script, args = ('youtube_runtime.py', ['upload', str(s.root), acc['key']]) if p['platform'] == 'youtube' else ('social_runtime.py', ['post', str(s.root), acc['key']])
    s.db.execute("UPDATE social_posts SET status='uploading' WHERE id=?", (p['id'],))
    s.db.commit()
    s.job_stage(job['id'], 'upload', label + '-feltöltés indítása · ' + acc['label'])
    def fail(message, external=''):
        s.db.execute("UPDATE social_posts SET status='failed',error=?,external_id=COALESCE(NULLIF(?,''),external_id),finished=? WHERE id=?", (str(message)[:500], external, time.time(), p['id']))
        s.db.commit()
    with (folder / 'upload.log').open('ab') as errors:
        process = subprocess.Popen([str(s.root / 'media-runtime/bin/python'), str(Path(__file__).with_name(script)), *args],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, start_new_session=True)
        raw = json.dumps(request).encode()
        first = True
        start = time.monotonic()
        last = -1
        try:
            while True:
                try:
                    output, _ = process.communicate(raw if first else None, timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    if s.cancelled(job['id']):
                        raise ValueError('Feltöltés leállítva. Ha az átvitel már befejeződött, ellenőrizd a platformon.')
                    if time.monotonic() - start > 3600:
                        raise ValueError('A feltöltés időkerete lejárt. Újraindítás előtt ellenőrizd a platformon.')
                    try:
                        percent = json.loads(progress.read_text()).get('percent', 0)
                    except (OSError, ValueError):
                        percent = last
                    if percent != last:
                        s.job_stage(job['id'], 'upload', label + '-feltöltés · ' + acc['label'] + ' · ' + str(percent) + '%')
                        last = percent
        except BaseException as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.communicate()
            fail(error, saved_id(progress))
            raise
    try:
        data = json.loads(output.decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        data = dict(ok=False, message='A feltöltő nem adott értelmezhető választ.')
    external = str(data.get('id') or saved_id(progress))
    if not data.get('ok'):
        fail(data.get('message') or 'Feltöltési hiba.', external)
        raise ValueError(str(data.get('message') or 'Feltöltési hiba.')[:400])
    info = facts(path, s, p['artifact'])
    url = data.get('url') or ''
    if p['platform'] == 'youtube':
        url = ('https://www.youtube.com/shorts/' if info['short'] else 'https://www.youtube.com/watch?v=') + external
    s.db.execute("UPDATE social_posts SET status='published',external_id=?,url=?,error='',finished=? WHERE id=?", (external, url, time.time(), p['id']))
    s.db.commit()
    return label + ' · ' + acc['label'] + ' · feltöltve' + (' · ' + url if url else '')


def saved_id(progress):
    try:
        return str(json.loads(Path(progress).read_text()).get('id') or '')
    except (OSError, ValueError):
        return ''


def category_for(s, pid):
    """YouTube's category: stream clips are Gaming, own animation is Film & Animation, anything else People & Blogs."""
    name = str(s.project(pid).get('name') or '').lower()
    return '1' if 'anim' in name or 'történet' in name else '20' if re.search(r'clip|klip|gta|stream|shorts|adás', name) else '22'


def tick(s, now=None):
    """Scheduled posts whose time has come go to the upload lane; a post whose job died is marked failed."""
    schema(s)
    now = now or time.time()
    refresh_waiting(s)
    import autonomy
    held = autonomy.paused(s)         # the master pause holds every scheduled post: it goes out after the owner resumes
    for p in ([] if held else s.rows("SELECT id FROM social_posts WHERE status='scheduled' AND scheduled<=? ORDER BY scheduled LIMIT 5", (now,))):
        try:
            enqueue(s, p['id'])
        except ValueError as error:
            s.db.execute("UPDATE social_posts SET status='failed',error=?,finished=? WHERE id=?", (str(error)[:300], now, p['id']))
    for p in s.rows("SELECT p.id,j.status,j.error FROM social_posts p JOIN jobs j ON j.id=p.job WHERE p.status IN ('queued','uploading') AND j.status IN ('failed','cancelled')"):
        s.db.execute('UPDATE social_posts SET status=?,error=?,finished=? WHERE id=?', (p['status'], str(p['error'] or '')[:500], now, p['id']))
    s.db.commit()
    try:
        if not held:
            plan.auto_tick(s, now)
    except Exception:
        pass   # a planning error must never stop scheduled posts
    try:
        import publish_reach as reach
        reach.tick(s)
    except Exception:
        pass   # a reach measurement must never stop scheduled posts


def snapshot(s):
    schema(s)
    refresh_waiting(s)
    accs = accounts(s)
    routes = {}
    for r in s.rows('SELECT project,account FROM social_routes'):
        routes.setdefault(r['project'], []).append(r['account'])
    vids = videos(s)
    shown = [v for v in vids if not v['hidden']]
    count = lambda st: sum(v['state'] == st for v in shown)
    types = []
    for t_ in lib.TYPES:
        mine = [v for v in shown if v['type'] == t_['id']]
        if mine or t_['id'] != 'other':
            types.append(dict(t_, total=len(mine), new=sum(v['state'] == 'new' for v in mine), scheduled=sum(v['state'] == 'scheduled' for v in mine)))
    for a_ in accs:
        a_['upcoming'] = plan.upcoming(s, a_['id'], vids) if a_['status'] == 'connected' else []
    return dict(accounts=accs, videos=vids, routes=routes, types=types, calendar=plan.calendar(s),
                platforms=[dict(id=k, label=v['label'], kinds=v['kinds'], login=v['login']) for k, v in PLATFORMS.items()],
                google_client=bool(shared_google_client(s)), auto=plan.auto_settings(s),
                counts=dict(new=count('new'), active=count('active'), scheduled=count('scheduled'), published=count('published'), failed=count('failed'),
                            hidden=sum(v['hidden'] for v in vids)))


def dispatch(s, op, args=None):
    args = args or {}
    schema(s)
    if op == 'publish_snapshot':
        return snapshot(s)
    if op == 'publish_account_add':
        return account_add(s, args.get('platform'), args.get('label'))
    if op == 'publish_account_connect':
        return account_connect(s, args.get('id'), args)
    if op == 'publish_account_remove':
        return account_remove(s, args.get('id'))
    if op == 'publish_account_rename':
        return account_rename(s, args.get('id'), args.get('label'))
    if op == 'publish_route':
        return route(s, str(args.get('project')), args.get('account'), args.get('on') is True)
    if op == 'publish_post':
        return post(s, args.get('video'), args.get('accounts'), args.get('title'), args.get('caption'), args.get('privacy') or 'public',
                    args.get('made_for_kids') is True, args.get('when'), plan=args.get('plan'), accept_unverified=args.get('accept_unverified') is True)
    if op == 'publish_account_plan':
        return plan.save(s, args.get('id'), args.get('slots'), None, args.get('types'), args.get('every'), args.get('auto') if 'auto' in args else None)
    if op == 'publish_plan_suggest':
        return plan.suggest(s, int(args.get('days') or 7))
    if op == 'publish_plan_fill':
        return plan.fill(s, args.get('account'))
    if op == 'publish_plan_apply':
        return plan.apply(s, args.get('items'))
    if op == 'publish_reschedule':
        return plan.reschedule(s, args.get('id'), args.get('when'))
    if op == 'publish_next_slot':
        return dict(when=plan.next_slot(s, args.get('account'), float(args.get('after') or 0)))
    if op == 'publish_hide':
        lib.set_hidden(s, str(args.get('video')), args.get('hidden') is True)
        return dict(message='Mentve.')
    if op == 'publish_thumbs':
        row, path = video_file(s, args.get('video'))
        f = facts(path, s, row['id'])
        hook = lib.cover_hook(args.get('title')) or ' '.join(str(args.get('hook') or '').split())[:60]
        if not hook:
            hook = lib.info(s, row, path, lib.type_of(s.project(row['project']).get('name'), '', path))['hook']
        lib.make_thumbs(s, row, path, hook, bool(f['short']))
        return dict(message='Három borítókép elkészült.', count=3)
    if op == 'publish_thumb_pick':
        row, _ = video_file(s, args.get('video'))
        s.db.execute('UPDATE social_video_meta SET thumb=? WHERE artifact=?', (int(args.get('index') or 0), row['id']))
        s.db.commit()
        return dict(message='A borítókép kiválasztva.')
    if op == 'publish_thumb_get':
        row, _ = video_file(s, args.get('video'))
        out = []
        for i in range(3):
            f = lib.thumb_file(s, row, i, small=True)
            if f:
                out.append(lib.thumb_data(f))
        return dict(thumbs=out)
    if op == 'publish_thumb_open':
        row, _ = video_file(s, args.get('video'))
        f = lib.thumb_file(s, row)
        if not f:
            raise ValueError('Ehhez a videóhoz még nincs borítókép.')
        subprocess.run(['/usr/bin/open', '-R', str(f)], check=False, capture_output=True)
        return dict(message='Megnyitva a Finderben.')
    if op in ('publish_reach', 'publish_reach_refresh'):
        import publish_reach as reach
        return reach.dispatch(s, op, args)
    if op == 'publish_auto':
        return plan.auto_save(s, args.get('enabled') if 'enabled' in args else None, args.get('min_score') if 'min_score' in args else None, args.get('account'))
    if op == 'publish_now':
        return publish_now(s, args.get('id'))
    if op == 'publish_cancel':
        return cancel(s, args.get('id'))
    if op == 'publish_retry':
        return retry(s, args.get('id'), args.get('confirmed_absent') is True)
    if op == 'publish_open_url':
        url = str(args.get('url') or '')
        if not re.match(r'https://(www\.)?(youtube\.com|instagram\.com|facebook\.com|tiktok\.com)/', url):
            raise ValueError('Ehhez nincs megnyitható cím.')
        subprocess.run(['/usr/bin/open', url], check=False, capture_output=True)
        return dict(opened=url)
    if op == 'publish_open':
        p = s.db.execute('SELECT url FROM social_posts WHERE id=?', (str(args.get('id')),)).fetchone()
        if not p or not re.match(r'https://(www\.)?(youtube\.com|instagram\.com|facebook\.com|tiktok\.com)/', p['url'] or ''):
            raise ValueError('Ehhez a feltöltéshez nincs megnyitható cím.')
        subprocess.run(['/usr/bin/open', p['url']], check=False, capture_output=True)
        return dict(opened=p['url'])
    raise ValueError('Ismeretlen publikálási művelet.')
