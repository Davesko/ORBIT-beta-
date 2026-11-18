"""What the posted videos really achieved, fed back into the score.

The score starts as an estimate from the chat peak, the format and the checker's verdict. Once the accounts' own reach
measurements (Elérés: views per posted video) exist, this module learns which STREAMERS' clips do better on the owner's
channels than the average, and the score gets a 'history' part for them. It needs real data before it says anything:
at least 5 measured posts overall and at least 1 for the streamer; with fewer the part is simply left out.
"""
import time
from pathlib import Path

_cache = {}
MIN_ALL, SHRINK, MIN_AGE = 5, 2.0, 12 * 3600


def history(s):
    """{'mean': average views of a measured post, 'n': measured posts, 'by': {streamer: (mean, n)}} (cached for ten minutes)."""
    hit = _cache.get(str(s.root))
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    out = dict(mean=0.0, n=0, by={})
    try:
        import publish_hub as hub, publish_library as lib, publish_reach as reach
        views = {}
        for acc in s.rows('SELECT id,key FROM social_accounts'):
            for item in reach.read(s, acc['key']).get('items') or []:
                if item.get('views') is not None:
                    views[(acc['id'], str(item.get('id')))] = float(item['views'])
        samples = {}
        for p in s.rows("SELECT artifact,account,external_id,finished FROM social_posts WHERE status='published' AND external_id!=''"):
            v = views.get((p['account'], str(p['external_id'])))
            if v is None or time.time() - (p['finished'] or 0) < MIN_AGE:
                continue
            row = s.db.execute('SELECT * FROM artifacts WHERE id=?', (p['artifact'],)).fetchone()
            run = lib.run_of(s, dict(row), Path(row['path']).resolve()) if row else None
            who = ((run or {}).get('moment') or {}).get('channel') or ''
            samples.setdefault(who, []).append(v)
        allv = [v for vs in samples.values() for v in vs]
        if allv:
            out['mean'], out['n'] = sum(allv) / len(allv), len(allv)
            out['by'] = {who: (sum(vs) / len(vs), len(vs)) for who, vs in samples.items() if who}
    except Exception:
        pass
    _cache[str(s.root)] = (time.time(), out)
    return out


def factor(hist, streamer):
    """How much better (>1) or worse (<1) than average this streamer's clips did, shrunk towards 1 while there is little data. None = unknown."""
    if not hist or hist['n'] < MIN_ALL or not hist['mean'] or streamer not in hist['by']:
        return None
    mean, n = hist['by'][streamer]
    return max(0.25, min(4.0, ((mean * n + hist['mean'] * SHRINK) / (n + SHRINK)) / hist['mean']))
