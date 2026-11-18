"""Trendradar: what the internet talks about right now, with the facts behind each item.

The animation writer used to get a list of bare headlines ("Outlook down"), so an episode about a real event could
only guess what happened. The radar reads several public sources, merges the items that are about the same thing,
ranks them by how many places carry them and how many people search them, and reads the news behind the top ones:
each trend comes with a few plain sentences of what actually happened and where that was read.

Sources (public, no login, no key): Google Trending Now (US and UK, with search volume and its own news links),
Google News searches for viral / entertainment / gaming / tech items, Hacker News' front page and Wikipedia's most
read articles of yesterday. Nothing here calls a model: the facts are sentences from the articles themselves.

Tragedies, crime, politics and private people are filtered out before anything reaches a writer.
"""
import json, math, re, time, urllib.request
from pathlib import Path

FILE = 'trend-radar.json'
MAX_AGE = 3 * 3600
NEWS_QUERIES = (('viral video', 'meme'), ('went viral', 'meme'), ('tiktok trend', 'meme'), ('new game release', 'gaming'), ('gaming news', 'gaming'),
                ('movie trailer', 'show'), ('app outage down', 'tech'), ('new phone launch', 'tech'), ('celebrity moment', 'celebrity'))
STOP = set('''the a an and or of to in on for with from by at as is are was were be been it its this that these those his her their our your you they we he she
 after before over under about into out up down new says said say will would could should has have had not no yes how why what when where who which than then
 just more most very amid vs live news video watch today week year day first last top best big full official update report reports
 viral tiktok trend trending star clip original instagram youtube meme memes goes went viral'''.split())
# A fixture, a table or a betting page is searched a lot and says nothing a cartoon can use; neither does spam or a non-English item.
FIXTURE = re.compile(r'\bvs?\.?\b|\s[-–]\s|\b(football|soccer|basketball|baseball|hockey|cricket|rugby|match|score|scores|stats|standings|fixtures?|odds|lineups?|league (one|two|1|2)|posiciones|contra|partido|resultados?|futbol|fútbol)\b', re.I)
JUNK = re.compile(r'\+\+|xxx|\bmms\b|\d{6,}|!!|\b(porn|leaked? video|full video link|onlyfans)\b', re.I)
FOREIGN = re.compile(r'\b(de|del|la|el|los|las|que|para|con|por|une?|les|des|der|die|und|não|em|da|do)\b', re.I)


def usable(topic):
    topic = str(topic)
    return (3 <= len(topic) <= 110 and not FIXTURE.search(topic) and not JUNK.search(topic) and len(FOREIGN.findall(topic)) < 2
            and sum(ord(c) > 127 for c in topic) <= 2)

KIND_WORDS = dict(
    gaming=r'\b(game|gaming|xbox|playstation|ps5|nintendo|switch|steam|fortnite|minecraft|roblox|gta|league of legends|valorant|dlc|patch|esports?)\b',
    tech=r'\b(app|iphone|android|ai|chatgpt|openai|google|microsoft|apple|meta|outage|down|update|server|tesla|robot|chip)\b',
    show=r'\b(trailer|season|episode|movie|film|series|netflix|disney|marvel|anime|box office|premiere)\b',
    music=r'\b(song|album|tour|concert|single|spotify|grammy|rapper|singer|band)\b',
    sport=r'\b(nba|nfl|fifa|uefa|league|cup|final|match|goal|championship|olympic\w*|f1|ufc)\b',
    meme=r'\b(meme|viral|tiktok|trend|challenge|brainrot)\b')
KIND_LABEL = dict(gaming='Játék', tech='Tech', show='Film / sorozat', music='Zene', sport='Sport', meme='Mém / virális', celebrity='Híresség', other='Egyéb')


def words(text):
    return {w for w in re.findall(r'[a-z0-9]{3,}', str(text).lower()) if w not in STOP}


def safe(text):
    """Light items only: no tragedy, crime, politics or market noise, and nothing the writer cannot read."""
    from story_animation import GRIM, SENSITIVE, NON_LATIN
    return bool(text) and not GRIM.search(text) and not SENSITIVE.search(text) and not NON_LATIN.search(text)


def kind_of(text, hint='other'):
    low = str(text).lower()
    for kind, pattern in KIND_WORDS.items():
        if re.search(pattern, low):
            return kind
    return hint


def get_json(url, timeout=12):
    from public_web import valid_url
    request = urllib.request.Request(valid_url(url), headers={'User-Agent': 'ORBIT research (public pages only)', 'Accept': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read(3_000_000))


# ---------------------------------------------------------------- sources: each returns raw items

def google_trending(geo):
    from public_web import fetch
    from growth import parse_feed
    raw, _ = fetch('https://trends.google.com/trending/rss?geo=' + geo, 1500000)
    out = []
    for item in parse_feed(raw):
        volume = item.get('google_search_traffic') or 0
        out.append(dict(topic=item['topic'], headlines=item.get('news_titles') or [], urls=item.get('news_urls') or [], source='Google Trends ' + geo,
                        weight=2 + min(3, math.log10(max(volume, 1000)) - 3), searches=volume))
    return out


def google_news():
    from research import news_rss
    out = []
    for query, hint in NEWS_QUERIES:
        try:
            found = news_rss(query, 5)
        except Exception:
            continue
        for x in found:
            title = re.sub(r'\s+[-–|]\s+[^-–|]{2,40}$', '', x['title']).strip()      # "Headline - Publisher"
            out.append(dict(topic=title, headlines=[title], urls=[], source='Google News', weight=1.0, hint=hint))
    return out


def hacker_news():
    ids = get_json('https://hacker-news.firebaseio.com/v0/topstories.json')[:12]
    out = []
    for i in ids:
        try:
            item = get_json('https://hacker-news.firebaseio.com/v0/item/%d.json' % int(i), timeout=6)
        except Exception:
            continue
        if item and item.get('title') and (item.get('score') or 0) >= 150:
            url = str(item.get('url') or '')
            out.append(dict(topic=item['title'], headlines=[item['title']], urls=[url] if url.startswith('https://') else [], source='Hacker News',
                            weight=1 + min(2, (item['score']) / 500), hint='tech'))
    return out


def wikipedia_top(now=None):
    day = time.gmtime((now or time.time()) - 86400)
    data = get_json('https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/%04d/%02d/%02d' % (day.tm_year, day.tm_mon, day.tm_mday))
    out = []
    for a in (data.get('items') or [{}])[0].get('articles', [])[:60]:
        name = str(a.get('article') or '')
        if ':' in name or name in ('Main_Page', 'Special:Search') or name.startswith('List_of'):
            continue
        title = name.replace('_', ' ')
        out.append(dict(topic=title, headlines=[], urls=[], source='Wikipedia (legolvasottabb)', weight=.8, searches=a.get('views')))
        if len(out) >= 25:
            break
    return out


SOURCES = (('google_us', lambda: google_trending('US')), ('google_gb', lambda: google_trending('GB')), ('news', google_news),
           ('hacker_news', hacker_news), ('wikipedia', wikipedia_top))


# ---------------------------------------------------------------- merge, rank, read

def merge(raw):
    """Items about the same thing become one trend. Two items match when the shorter one's words are mostly in the other."""
    groups = []
    for item in raw:
        text = item['topic'] + ' ' + ' '.join(item.get('headlines') or [])
        if not safe(text) or not usable(item['topic']):
            continue
        key = words(item['topic'])
        if not key:
            continue
        home = None
        for g in groups:
            shared = key & g['key']
            if len(shared) >= max(1, min(2, len(key), len(g['key']))) and len(shared) >= .6 * min(len(key), len(g['key'])):
                home = g
                break
        if home is None:
            home = dict(key=set(), topic=item['topic'], headlines=[], urls=[], sources=[], heat=0.0, searches=0, hint=item.get('hint') or 'other')
            groups.append(home)
        # Wikipedia only says a page is read a lot; it confirms a trend, it does not start one on its own.
        home['key'] |= key
        if item['source'] not in home['sources']:
            home['sources'].append(item['source'])
            home['heat'] += item['weight']
        home['searches'] = max(home['searches'], int(item.get('searches') or 0) if item['source'].startswith('Google Trends') else 0)
        for h in item.get('headlines') or []:
            if h and h not in home['headlines'] and safe(h) and not JUNK.search(h) and len(FOREIGN.findall(h)) < 3:
                home['headlines'].append(h)
        for u in item.get('urls') or []:
            if u not in home['urls']:
                home['urls'].append(u)
        if item.get('hint') and home['hint'] == 'other':
            home['hint'] = item['hint']
    out = [g for g in groups if g['sources'] != ['Wikipedia (legolvasottabb)']]
    # A few hundred searches is one town's evening; a trend only Google lists needs real volume.
    out = [g for g in out if not all(x.startswith('Google Trends') for x in g['sources']) or g['searches'] >= 2000]
    for g in out:
        g['heat'] = round(g['heat'] + (.5 if len(g['sources']) > 1 else 0), 2)
    out.sort(key=lambda g: -g['heat'])
    return out


def sentences(text, key, limit=3):
    """Plain sentences of an article that are about the trend: the facts a writer may state."""
    out = []
    for raw in re.split(r'(?<=[.!?])\s+(?=[A-Z"“])', re.sub(r'\s+', ' ', text)):
        s = raw.strip()
        if not 50 <= len(s) <= 240 or s.count(' ') < 7 or re.search(r'cookie|subscribe|sign up|newsletter|advertis|privacy|©|all rights reserved|click here|read more|\bbet(s|ting)?\b|\bodds\b|up next|highlights|compatible|\d{1,2}:\d{2}|[\U0001F300-\U0001FAFF]', s, re.I) or len(FOREIGN.findall(s)) >= 3:
            continue
        if len(words(s) & key) >= min(2, len(key)) and safe(s) and s not in out:
            out.append(s)
            if len(out) >= limit:
                break
    return out


def read_facts(group, reader=None):
    if reader is None:
        from public_web import read as reader
    facts, used = [], []
    for url in group['urls'][:2]:
        try:
            page = reader(url)
        except Exception:
            continue
        found = sentences(page.get('text') or '', group['key'])
        if found:
            facts += [f for f in found if f not in facts]
            used.append(url)
        if len(facts) >= 3:
            break
    return facts[:4], used


def build(raw, reader=None, read_top=8, now=None):
    items = []
    for n, g in enumerate(merge(raw)[:24]):
        facts, used = read_facts(g, reader) if n < read_top and g['urls'] else ([], [])
        headline = g['headlines'][0] if g['headlines'] else g['topic']
        kind = kind_of(g['topic'] + ' ' + headline, g['hint'])
        items.append(dict(id=re.sub(r'[^a-z0-9]+', '-', g['topic'].lower()).strip('-')[:48] or str(n), topic=g['topic'][:120], headline=headline[:200],
                          headlines=[h[:200] for h in g['headlines'][:4]], facts=facts, read_from=used, sources=g['sources'], heat=g['heat'],
                          searches=g['searches'], kind=kind, kind_label=KIND_LABEL.get(kind, 'Egyéb')))
    return dict(updated=now or time.time(), items=items)


def collect():
    raw, errors = [], {}
    for name, source in SOURCES:
        try:
            raw += source()
        except Exception as exc:
            errors[name] = str(exc)[:160]
    return raw, errors


def saved(s):
    try:
        data = json.loads((s.root / FILE).read_text())
    except (OSError, ValueError):
        return dict(updated=0, items=[])
    return data if isinstance(data, dict) and isinstance(data.get('items'), list) else dict(updated=0, items=[])


def refresh(s, force=False):
    """The radar, read again when it is older than three hours. A failed read keeps the last good list."""
    old = saved(s)
    if not force and time.time() - float(old.get('updated') or 0) < MAX_AGE and old['items']:
        return old
    from connections import under_test
    if under_test() and not force:
        return old          # a test never reads the live web
    raw, errors = collect()
    if not raw:
        return dict(old, errors=errors)
    data = dict(build(raw), errors=errors)
    if data['items']:
        tmp = s.root / (FILE + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(s.root / FILE)
        return data
    return dict(old, errors=errors)


def for_writer(items, recent_trends=(), limit=8):
    """The radar as the writer gets it: the trend and what happened, without the ones recent episodes used."""
    from model_router import normalized
    used = [normalized(str(t))[:40] for t in recent_trends if t]
    out = []
    for item in items:
        name = normalized(item['topic'])
        if any(u and (u[:24] in name or name[:24] in u) for u in used):
            continue
        # The headline says what it is; the article sentences add what actually happened.
        what = list(dict.fromkeys((item.get('headlines') or [item.get('headline')])[:2] + (item.get('facts') or [])[:2]))
        out.append(dict(trend=item['topic'], what_happened=[w for w in what if w][:4], talked_about_in=len(item.get('sources') or [])))
        if len(out) >= limit:
            break
    return out


def match(items, trend):
    """The radar item an idea's trend names, by shared words."""
    key = words(trend)
    best, score = None, 0
    for item in items:
        shared = len(key & words(item['topic'] + ' ' + item.get('headline', '')))
        if shared > score:
            best, score = item, shared
    return best if best and score >= (1 if len(key) <= 2 else 2) else None
