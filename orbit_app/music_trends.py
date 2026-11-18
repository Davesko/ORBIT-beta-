"""What music is trending right now, as a style for the episode's own original score.

Owner, 13 Nov: "ne ennyire lofi ugyanaz a zene menjen alatta, hanem trendi zenék, és csak akkor ha aktuális".
Seven of the last ten episodes had the same slow lofi bed. A trending song itself cannot go into the video (it is
copyrighted), so:

* the daily global Spotify chart (kworb.net, a public page) gives the songs that are new or climbing today,
* each artist's genre tags come from MusicBrainz (public, 1 request a second, a generic app name),
* the episode's ACE-Step score is written in that genre's production style, never the song's melody or words,
* the upload text names the song, so the owner can add the real sound from TikTok's / YouTube's own licensed library.

A chart older than three days is not "current": then no trend is used and the episode keeps its own upbeat mood.
Nothing personal is ever sent: only the chart page and artist names.
"""
import datetime
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request

CHART = 'https://kworb.net/spotify/country/global_daily.html'
FRESH_DAYS = 3
AGENT = 'ORBIT-music-trends/1.0 (local desktop app)'

# Genre tag -> how the score should sound (production, groove, instruments) and a typical tempo.
STYLES = (
    (r'reggaeton|dembow|latin trap|urbano', 'modern reggaeton dembow groove, punchy kick and snare pattern, deep sub bass, plucked latin synth hook', 95),
    (r'latin|salsa|bachata|cumbia|regional mexican|corrido', 'bright modern latin pop groove, congas and shakers, nylon guitar riff, punchy bass', 104),
    (r'phonk', 'drift phonk, distorted cowbell melody, heavy 808 bass, hard trap drums', 130),
    (r'trap|drill|rap|hip hop|hip-hop', 'modern trap beat, crisp rolling hi-hats, booming 808, dark synth bell hook', 140),
    (r'k-pop|j-pop', 'glossy k-pop dance production, layered synths, big drops, tight claps', 120),
    (r'afrobeats?|amapiano', 'afrobeats groove, log drum bass, shakers and syncopated percussion, warm keys', 108),
    (r'house|edm|electronic|dance\b|techno|electro', 'upbeat club house groove, four-on-the-floor kick, offbeat bass, catchy synth stab hook', 124),
    (r'hyperpop', 'hyperpop, pitched-up synth leads, distorted bass, glitchy drums, chaotic energy', 150),
    (r'christmas|holiday', 'festive pop groove, sleigh bells, bright piano, bouncy bass', 120),
    (r'country|folk|americana', 'upbeat modern country pop, banjo and acoustic guitar riff, stomp-clap drums', 112),
    (r'metal|nu metal|hard rock|alternative metal', 'driving heavy guitar riff, big rock drums, energetic', 140),
    (r'rock|indie(?! pop)|alternative|grunge|emo|punk', 'energetic indie rock groove, jangly electric guitar riff, driving drums, bass', 128),
    (r'r&b|rnb|soul', 'smooth modern r&b groove, snappy drums, warm synth bass, silky keys', 98),
    (r'dream pop|bedroom pop|indie pop', 'dreamy indie pop groove, washed-out synths, laid-back drums, warm bass, catchy', 104),
    (r'dance-pop|electropop|synth-?pop', 'bright dance-pop production, punchy drums, catchy synth hook, pulsing bass', 120),
    (r'pop', 'glossy modern pop production, punchy drums, catchy synth and guitar hook, bouncy bass', 116),
)


def _get(url, accept='text/html'):
    from public_web import valid_url
    valid_url(url)
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept': accept})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20) as response:
        return response.read(2_000_000).decode('utf-8', errors='replace')


def parse_chart(page):
    """(chart day, rows) from the kworb daily page: position, movement, 'Artist - Title', days on chart."""
    day = re.search(r'(20\d\d)/(\d\d)/(\d\d)', page)
    rows = []
    for raw in re.findall(r'<tr>(.*?)</tr>', page, re.S)[1:]:
        cells = [re.sub(r'<[^>]+>', '', html.unescape(c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', raw, re.S)]
        if len(cells) < 4 or ' - ' not in cells[2]:
            continue
        artist, title = cells[2].split(' - ', 1)
        rows.append(dict(pos=int(cells[0]) if cells[0].isdigit() else 999, move=cells[1], artist=artist.strip(), title=title.strip(),
                         days=int(cells[3]) if cells[3].isdigit() else 9999))
    return (datetime.date(int(day[1]), int(day[2]), int(day[3])).isoformat() if day else None), rows


def rising(rows, limit=8):
    """Songs that are trending now: new or re-entered, or climbing at least five places; new songs first."""
    def climb(row):
        m = row['move']
        return 50 if m in ('NEW', 'RE') else int(m[1:]) if m.startswith('+') and m[1:].isdigit() else 0
    picked = [r for r in rows if climb(r) >= 5 and r['pos'] <= 120]
    picked.sort(key=lambda r: (-(climb(r) + (40 if r['days'] <= 120 else 0)), r['pos']))
    return picked[:limit]


def artist_tags(name):
    query = urllib.parse.quote(f'artist:"{name}"')
    data = json.loads(_get(f'https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json&limit=1', 'application/json'))
    artists = data.get('artists') or []
    tags = sorted(artists[0].get('tags') or [], key=lambda t: -t.get('count', 0)) if artists else []
    return [t['name'] for t in tags][:6]


def style_for(tags):
    """The artist's strongest tag decides (Lana Del Rey's "indie pop" before a weaker "electronic")."""
    for tag in tags:
        for pattern, style, bpm in STYLES:
            if re.search(pattern, tag.lower()):
                return style, bpm
    return None, None


def refresh(root, now=None):
    """Today's trending styles, fetched at most once a day into music-trends.json (with the artists' tags kept)."""
    path = root / 'music-trends.json'
    today = (now or datetime.date.today()).isoformat()
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    if saved.get('fetched') == today:
        return saved
    try:
        day, rows = parse_chart(_get(CHART))
    except Exception:
        return saved                       # offline: keep yesterday's list; current() decides if it is still fresh
    known = saved.get('tags') or {}
    items = []
    for row in rising(rows):
        artist = re.split(r'\s*(?:,|&| x | feat\.? | ft\.? )\s*', row['artist'])[0]
        if artist not in known:
            try:
                known[artist] = artist_tags(artist)
            except Exception:
                known[artist] = []
            time.sleep(1.1)               # MusicBrainz: at most one request a second
        style, bpm = style_for(known[artist])
        if style:
            items.append(dict(artist=row['artist'], title=row['title'], tags=known[artist], style=style, bpm=bpm, move=row['move']))
    data = dict(fetched=today, chart_day=day, items=items, tags=dict(list(known.items())[-200:]))
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    except OSError:
        pass
    return data


def current(root, now=None):
    """The trending styles only while the chart is at most FRESH_DAYS old; otherwise nothing ("csak ha aktuális")."""
    data = refresh(root, now)
    day = data.get('chart_day')
    try:
        age = ((now or datetime.date.today()) - datetime.date.fromisoformat(day)).days
    except (TypeError, ValueError):
        return []
    return data.get('items') or [] if 0 <= age <= FRESH_DAYS else []


def pick(root, seed, recent=(), now=None):
    """One trending song for this episode, a different one than the last episodes used when possible."""
    items = current(root, now)
    fresh = [i for i in items if i['style'] not in recent] or items
    if not fresh:
        return None
    return fresh[int(hashlib.sha256(str(seed).encode()).hexdigest()[:8], 16) % len(fresh)]
