"""Per-channel scheduling for the Publikálás page.

Every account (channel) has its own posting times ("slots"), a daily limit and the video types it takes. The planner
only PROPOSES: it fills each channel's next free slots with videos of the types that channel takes, and nothing is
queued until the owner confirms the proposal (publish_plan_apply). The same video on several channels is staggered by
at least two hours so one upload never competes with its own copy.
"""
import json, re, time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Budapest')       # the posting times are Budapest time, summer time included, on whatever Mac or zone ORBIT runs (audit 17 Nov)

DEFAULT_SLOTS = dict(youtube=['18:00'], instagram=['19:00'], tiktok=['20:00'], facebook=['12:00'])
STAGGER = 2 * 3600


def meta(row):
    try:
        return json.loads(row['meta'] or '{}')
    except ValueError:
        return {}


def settings(s, row, types_from_routes=None):
    m = meta(row)
    slots = [x for x in (m.get('slots') or DEFAULT_SLOTS.get(row['platform'], ['18:00'])) if re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', str(x))]
    types = m.get('types')
    if types is None:
        types = types_from_routes or []
    return dict(slots=sorted(set(slots)) or ['18:00'], per_day=int(m.get('per_day') or max(1, len(slots))), types=list(types))


def parse_slots(items):
    """Posting times from whatever the owner typed or pasted: '00:00, 02:00, 4:00;06.00', a list, trailing commas - all fine."""
    if isinstance(items, str):
        items = re.split(r'[,;\s]+', items)
    out = set()
    for x in items or []:
        m = re.fullmatch(r'(\d{1,2})[:.](\d{2})', str(x).strip())
        if m and int(m[1]) <= 23 and int(m[2]) <= 59:
            out.add('%02d:%02d' % (int(m[1]), int(m[2])))
    return sorted(out)


def every_slots(hours, start='00:00', end='23:59'):
    """'Every 2 hours from 00:00 to 22:00' as a list of times (hours may be 0.5 steps, 0.5-12)."""
    first, last = parse_slots([start]) or ['00:00'], parse_slots([end]) or ['23:59']
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not 0.5 <= hours <= 12:
        raise ValueError('Az időköz 0,5 és 12 óra között lehet.')
    t = int(first[0][:2]) * 60 + int(first[0][3:])
    stop = int(last[0][:2]) * 60 + int(last[0][3:])
    out = []
    while t <= stop and len(out) < 48:
        out.append('%02d:%02d' % divmod(t, 60))
        t += int(round(hours * 60))
    return out


def save(s, aid, slots=None, per_day=None, types=None, every=None):
    import publish_hub as hub
    import publish_library as lib
    row = hub.account(s, aid)
    m = meta(row)
    if isinstance(every, dict):
        slots = every_slots(every.get('hours'), every.get('start') or '00:00', every.get('end') or '23:59')
    if slots is not None:
        clean = parse_slots(slots)
        if not 1 <= len(clean) <= 48:
            raise ValueError('Adj meg 1–48 közzétételi időpontot (ÓÓ:PP), vesszővel elválasztva, vagy válaszd a „minden N órában” lehetőséget.')
        m['slots'] = clean
        if per_day is None:
            m.pop('per_day', None)          # the daily limit follows the number of times until the owner sets it
    if per_day is not None:
        if not isinstance(per_day, int) or isinstance(per_day, bool) or not 1 <= per_day <= 48:
            raise ValueError('A napi korlát 1–48 videó lehet.')
        m['per_day'] = per_day
    if types is not None:
        if not isinstance(types, list) or set(types) - set(lib.TYPE_IDS):
            raise ValueError('Ismeretlen videótípus.')
        m['types'] = types
    s.db.execute('UPDATE social_accounts SET meta=? WHERE id=?', (json.dumps(m), aid))
    s.db.commit()
    got = settings(s, hub.account(s, aid))
    return dict(message='Mentve: ' + str(len(got['slots'])) + ' időpont naponta (' + ', '.join(got['slots'][:6]) + (' …' if len(got['slots']) > 6 else '') + '), legfeljebb ' + str(got['per_day']) + ' videó.', slots=got['slots'], per_day=got['per_day'])


def busy_times(s, aid, since):
    return [r['scheduled'] for r in s.rows("SELECT scheduled FROM social_posts WHERE account=? AND scheduled>? AND status IN ('scheduled','queued','uploading')", (aid, since - 86400))]


def next_slot(s, aid, after=0, taken=()):
    import publish_hub as hub
    row = hub.account(s, aid)
    st = settings(s, row)
    start = max(time.time() + 300, after)
    busy = busy_times(s, aid, start) + list(taken)
    day = datetime.fromtimestamp(start, TZ).date()
    for offset in range(75):
        d = day + timedelta(days=offset)
        today = [b for b in busy if datetime.fromtimestamp(b, TZ).date() == d]
        count = len(today)
        for hhmm in st['slots']:
            h, m = map(int, hhmm.split(':'))
            at = datetime(d.year, d.month, d.day, h, m, tzinfo=TZ).timestamp()
            if at < start or count >= st['per_day']:
                continue
            if any(abs(at - b) < 1800 for b in busy):
                continue
            return at
    raise ValueError('Nincs szabad időpont a következő 75 napban.')


def freshness(v, now=None):
    """Stream moments go stale: a clip loses half its pull every two days (never below 35 %), so a slightly weaker but fresh one can go first."""
    age_h = max(0.0, ((now or time.time()) - (v.get('created') or 0)) / 3600)
    return max(0.35, 0.5 ** (age_h / 48)) if v.get('type') == 'clip' else 1.0


def suggest(s, days=7, per_account=None):
    """A proposal: for every connected channel, the next free slots filled with videos of the types it takes."""
    import publish_hub as hub
    accs = [a for a in hub.accounts(s) if a['status'] == 'connected']
    floor = auto_settings(s)['min_score']
    # Best first: the highest-scored video takes the next free slot. A video below the floor or an unchecked story is never proposed.
    vids = sorted([v for v in hub.videos(s) if not v['hidden'] and (not v.get('quality') or v['quality']['status'] == 'verified') and v.get('score', 0) >= floor],
                  key=lambda v: (-v.get('score', 0) * freshness(v), -(v.get('created') or 0)))
    horizon = time.time() + days * 86400
    taken_by_video, taken_by_account, items = {}, {}, []
    for a in accs:
        if not a['types']:
            continue
        count = 0
        limit = per_account or min(300, max(14, len(a['slots']) * days))
        for v in vids:
            if count >= limit:
                break
            if v['type'] not in a['types'] or (a['platform'] != 'youtube' and v['short'] is False):
                continue
            if any(p['account'] == a['id'] and p['status'] in ('queued', 'uploading', 'scheduled', 'published') for p in v['posts']):
                continue
            try:
                at = next_slot(s, a['id'], after=taken_by_video.get(v['id'], 0) + STAGGER if v['id'] in taken_by_video else 0, taken=taken_by_account.get(a['id'], ()))
            except ValueError:
                break
            if at > horizon:
                break
            taken_by_account.setdefault(a['id'], []).append(at)
            taken_by_video[v['id']] = max(at, taken_by_video.get(v['id'], 0))
            text = v['variants'].get(a['platform']) or dict(title=v['title'], caption=v['caption'])
            items.append(dict(video=v['id'], video_title=v['title'] or v['name'], type=v['type'], score=v.get('score', 0), account=a['id'], account_label=a['label'], platform=a['platform'],
                              when=at, title=text['title'], caption=text['caption']))
            count += 1
    items.sort(key=lambda i: i['when'])
    return dict(items=items, days=days)


def apply(s, items):
    """The owner confirmed the proposal (possibly edited): queue every entry with its own time and text."""
    import publish_hub as hub
    if not isinstance(items, list) or not 1 <= len(items) <= 600:
        raise ValueError('Nincs elfogadható ütemezési tétel.')
    done, failed, ids = 0, [], []
    by_video = {}
    for it in items:
        by_video.setdefault(str(it.get('video')), []).append(dict(account=it.get('account'), when=it.get('when'), title=it.get('title'), caption=it.get('caption')))
    for vid, plan in by_video.items():
        for entry in plan:
            try:
                out = hub.post(s, vid, None, '', '', 'public', False, None, plan=[entry], accept_unverified=False)
                done += sum(not p['existing'] for p in out['posts'])
                ids.extend(p['id'] for p in out['posts'] if not p['existing'])
            except ValueError as error:
                failed.append(str(error)[:160])
    msg = str(done) + ' közzététel ütemezve.' + (' Nem sikerült: ' + str(len(failed)) + ' (' + failed[0] + ')' if failed else '')
    return dict(message=msg, done=done, failed=failed, ids=ids)


def reschedule(s, post_id, when):
    p = s.db.execute('SELECT * FROM social_posts WHERE id=?', (str(post_id),)).fetchone()
    if not p or p['status'] != 'scheduled':
        raise ValueError('Csak ütemezett közzététel időpontja módosítható.')
    when = float(when)
    if not time.time() + 30 <= when <= time.time() + 90 * 86400:
        raise ValueError('Az új időpont a következő 90 napban legyen.')
    s.db.execute('UPDATE social_posts SET scheduled=? WHERE id=?', (when, p['id']))
    s.db.commit()
    return dict(message='Időpont módosítva.')


def calendar(s, days=60):
    import publish_hub as hub
    names = {}
    for p in s.rows("SELECT * FROM social_posts WHERE (status IN ('scheduled','queued','uploading') OR (status IN ('published','failed') AND COALESCE(finished,created)>?)) ORDER BY COALESCE(scheduled,finished,created)", (time.time() - 14 * 86400,)):
        a = s.db.execute('SELECT label FROM social_accounts WHERE id=?', (p['account'],)).fetchone()
        v = s.db.execute('SELECT name,project FROM artifacts WHERE id=?', (p['artifact'],)).fetchone()
        names[p['id']] = dict(id=p['id'], video=p['artifact'], account=p['account'], account_label=a['label'] if a else '?', platform=p['platform'], status=p['status'],
                              when=p['scheduled'] or p['finished'] or p['created'], title=p['title'] or (v['name'] if v else ''), url=p['url'], error=p['error'])
    return list(names.values())


# ---------------------------------------------------------------- automatic scheduling (off until the owner switches it on)

AUTO_FILE = 'publish-auto.json'
_auto = {'at': 0}


def auto_settings(s):
    try:
        data = json.loads((s.root / AUTO_FILE).read_text())
    except (OSError, ValueError):
        data = {}
    floor = data.get('min_score')
    return dict(enabled=data.get('enabled') is True, min_score=int(floor) if isinstance(floor, (int, float)) and not isinstance(floor, bool) and 0 <= floor <= 100 else 55,
                ahead_hours=int(data.get('ahead_hours') or 24))


def auto_save(s, enabled=None, min_score=None):
    cur = auto_settings(s)
    if enabled is not None:
        cur['enabled'] = enabled is True
    if min_score is not None:
        if not isinstance(min_score, (int, float)) or isinstance(min_score, bool) or not 0 <= min_score <= 100:
            raise ValueError('A legalacsonyabb pontszám 0-100 lehet.')
        cur['min_score'] = int(min_score)
    (s.root / AUTO_FILE).write_text(json.dumps(cur))
    _auto['at'] = 0
    return dict(auto=cur, message='Automatikus ütemezés: ' + ('be van kapcsolva.' if cur['enabled'] else 'ki van kapcsolva.'))


def auto_mark(s, ids):
    s.db.execute('CREATE TABLE IF NOT EXISTS social_auto(post TEXT PRIMARY KEY,created REAL)')
    for i in ids:
        s.db.execute('INSERT OR IGNORE INTO social_auto VALUES(?,?)', (i, time.time()))
    s.db.commit()


def auto_cancel_future(s, now, keep_minutes=30):
    """Posts the automatic planner scheduled and that are still more than half an hour away are taken back, so the slot goes to the best
    video of the moment (a better one may have been made and checked since). A post closer than that stays: it is on its way out."""
    s.db.execute('CREATE TABLE IF NOT EXISTS social_auto(post TEXT PRIMARY KEY,created REAL)')
    import publish_hub as hub
    n = 0
    for r in s.rows("SELECT p.id FROM social_posts p JOIN social_auto a ON a.post=p.id WHERE p.status='scheduled' AND p.scheduled>?", (now + keep_minutes * 60,)):
        try:
            hub.cancel(s, r['id'])
            n += 1
        except ValueError:
            pass
    return n


def auto_tick(s, now=None):
    """With the switch on, every channel's next slots (within `ahead_hours`) are filled with the best-scored unposted videos.
    The pool is large (many Shorts are made, few are posted): whenever the pool changes the not-yet-close slots are planned again, so each slot
    goes to the best checked video there is at that time. Each video goes once per channel, in the channel's own times and daily limit."""
    now = now or time.time()
    cfg = auto_settings(s)
    if not cfg['enabled'] or now - _auto['at'] < 600:
        return 0
    _auto['at'] = now
    import publish_hub as hub
    floor = cfg['min_score']
    pool = [v for v in hub.videos(s) if not v['hidden'] and v.get('score', 0) >= floor and v['state'] in ('new', 'scheduled') and (not v.get('quality') or v['quality']['status'] == 'verified')]
    sig = (len(pool), max([v.get('created') or 0 for v in pool] or [0]), tuple(sorted(v['id'] for v in pool))[:40])
    if sig != _auto.get('sig'):
        auto_cancel_future(s, now)
        _auto['sig'] = sig
    items = [i for i in suggest(s, days=3)['items'] if i['when'] <= now + cfg['ahead_hours'] * 3600]
    if not items:
        return 0
    out = apply(s, items)
    auto_mark(s, out.get('ids', []))
    return out['done']
