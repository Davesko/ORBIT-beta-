"""The live stream watcher's three small processes.

listen <dir>   Reads the public chat of the channels in <dir>/listen.json (Twitch chat, read-only, no login) and
               writes five-second counts into <dir>/chat.sqlite. Standard library only, so the system Python runs it.
               It never stores who wrote what: only how many messages, from how many people, and how many of them
               were a laugh, hype, shock or fail reaction. It stops by itself when the app stops refreshing listen.json.
probe          (media runtime) Which of the channels are live, since when, in which game, and their broadcast recording.
fetch          (media runtime) Downloads one window of a broadcast recording (also while the broadcast still runs).
"""
import json, os, re, sqlite3, sys, threading, time, urllib.request
from pathlib import Path

BUCKET = 5
# What a chat writes when something happens. Emote names are matched as whole words, case kept where it matters.
REACTIONS = dict(
    funny=re.compile(r'\b(lul\w*|lol+|lmao+|lmfao+|kekw*|omegalul|icant|haha+\w*|xd+|rofl|pepelaugh|dead)\b|😂|🤣|💀', re.I),
    hype=re.compile(r'\b(pog\w*|w+|ww+|letsgo+|lets go+|holy|insane|goat\w*|clutch|ez|gg|sheesh+|hype|fire)\b|🔥', re.I),
    shock=re.compile(r'\b(wtf+|what+|nah+|no way|bro+|omg+|monka\w*|ayo+|huh+|yo+)\b|\?{3,}|😱|😳', re.I),
    fail=re.compile(r'\b(f|rip|l+|sadge|oof+|bruh+|not like this|throw\w*|choke\w*|aware)\b', re.I),
    clip=re.compile(r'\bclip\b|\bclip (it|that)\b|\bclipped\b', re.I),
)
CHANNEL = re.compile(r'yt:[a-z0-9_.\-]{2,40}|[a-z0-9_]{2,25}')
GAME = re.compile(r'grand theft auto\s*(6|vi)\b|\bgta\s*-?\s*(6|vi)\b', re.I)


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(temp, path)


def classify(text):
    return [name for name, pattern in REACTIONS.items() if pattern.search(text)]


class Counter:
    """Five-second buckets per channel. A person counts at most twice per bucket, so one spammer is not a peak."""

    def __init__(self):
        self.open = {}
        self.lock = threading.Lock()

    def add(self, channel, user, text, at):
        with self.lock:
            self._add(channel, user, text, at)

    def _add(self, channel, user, text, at):
        key = (channel, int(at // BUCKET) * BUCKET)
        b = self.open.setdefault(key, dict(n=0, users={}, funny=0, hype=0, shock=0, fail=0, clip=0))
        seen = b['users'].get(user, 0)
        b['users'][user] = seen + 1
        if seen >= 2:
            return
        b['n'] += 1
        for name in classify(text):
            b[name] += 1

    def closed(self, now):
        """Buckets that can no longer change (a message may arrive a few seconds late)."""
        with self.lock:
            done = [(k, v) for k, v in self.open.items() if k[1] + BUCKET + 3 <= now]
            for k, _ in done:
                del self.open[k]
        return [(c, t, v['n'], len(v['users']), v['funny'], v['hype'], v['shock'], v['fail'], v['clip']) for (c, t), v in done]


def database(folder):
    db = sqlite3.connect(str(Path(folder) / 'chat.sqlite'), timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS buckets(channel TEXT,t INTEGER,n INTEGER,users INTEGER,funny INTEGER,hype INTEGER,shock INTEGER,fail INTEGER,clip INTEGER,PRIMARY KEY(channel,t))')
    db.commit()
    return db


def parse(line):
    """(channel, user, text, unix time) of a chat line, or None."""
    if ' PRIVMSG #' not in line:
        return None
    tags = ''
    if line.startswith('@'):
        tags, _, line = line[1:].partition(' ')
    try:
        prefix, _, rest = line.partition(' PRIVMSG #')
        channel, _, text = rest.partition(' :')
        user = prefix.lstrip(':').split('!', 1)[0]
    except ValueError:
        return None
    sent = re.search(r'(?:^|;)tmi-sent-ts=(\d{10,13})', tags)
    at = int(sent.group(1)) / 1000 if sent else time.time()
    return channel.strip().lower(), user, text, at


def wanted(folder):
    """The channels to listen to, or None when the app no longer asks for any (then the listener ends)."""
    try:
        data = json.loads((Path(folder) / 'listen.json').read_text())
    except (OSError, ValueError):
        return None
    if time.time() - float(data.get('updated') or 0) > 600:
        return None
    return [c for c in data.get('channels') or [] if isinstance(c, str) and CHANNEL.fullmatch(c)][:60]


def listen(folder):
    import socket, ssl
    folder = Path(folder)
    db = database(folder)
    counter = Counter()
    lock = folder / 'listener.pid'
    lock.write_text(str(os.getpid()))
    threading.Thread(target=youtube_chats, args=(folder, lock), daemon=True).start()
    wait = 2
    while True:
        channels = wanted(folder)
        if channels is None:
            return
        channels = [c for c in channels if not c.startswith('yt:')]
        if not channels:
            (folder / 'listener.heartbeat').touch()
            time.sleep(10)
            continue
        try:
            raw = socket.create_connection(('irc.chat.twitch.tv', 6697), timeout=15)
            sock = ssl.create_default_context().wrap_socket(raw, server_hostname='irc.chat.twitch.tv')
            sock.sendall(b'CAP REQ :twitch.tv/tags\r\nNICK justinfan%d\r\n' % (10000 + os.getpid() % 80000))
            joined = set()
            sock.settimeout(2)
            buffer = b''
            checked = flushed = 0
            last_data = time.time()
            while True:
                now = time.time()
                if now - checked > 20:
                    checked = now
                    channels = wanted(folder)
                    if channels is None:
                        return
                    channels = [c for c in channels if not c.startswith('yt:')]
                    if lock.read_text().strip() != str(os.getpid()):
                        return   # a newer listener took over
                    for c in [c for c in channels if c not in joined][:15]:
                        sock.sendall(b'JOIN #' + c.encode() + b'\r\n')
                        joined.add(c)
                    for c in [c for c in joined if c not in channels]:
                        sock.sendall(b'PART #' + c.encode() + b'\r\n')
                        joined.discard(c)
                try:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise OSError('closed')
                    buffer += chunk
                    last_data = now
                except socket.timeout:
                    if now - last_data > 400:
                        raise OSError('silent')
                *lines, buffer = buffer.split(b'\r\n')
                for line in lines:
                    if line.startswith(b'PING'):
                        sock.sendall(b'PONG :tmi.twitch.tv\r\n')
                        continue
                    item = parse(line.decode('utf-8', 'replace'))
                    if item and item[0] in joined:
                        counter.add(*item)
                if now - flushed > 5:
                    flushed = now
                    rows = counter.closed(now)
                    if rows:
                        db.executemany('INSERT OR REPLACE INTO buckets VALUES(?,?,?,?,?,?,?,?,?)', rows)
                    db.execute('DELETE FROM buckets WHERE t<?', (int(now) - 6 * 3600,))
                    db.commit()
                    (folder / 'listener.heartbeat').touch()
                    wait = 2
        except OSError:
            time.sleep(wait)
            wait = min(60, wait * 2)



# ---------------------------------------------------------------- YouTube live chat (public page, no login, no key of ours)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15', 'Accept-Language': 'en-US,en;q=0.9'}


def yt_text(renderer):
    out = []
    for run in (renderer.get('message') or {}).get('runs') or []:
        if 'text' in run:
            out.append(run['text'])
        elif run.get('emoji'):
            e = run['emoji']
            out.append(e.get('emojiId') if e.get('emojiId') and not str(e['emojiId']).startswith('UC') else ' '.join(e.get('shortcuts') or [''])[:40])
    return ''.join(out)


def yt_next(data):
    for item in (((data.get('continuationContents') or {}).get('liveChatContinuation') or data.get('contents', {}).get('liveChatRenderer') or {}).get('continuations') or []):
        for key in ('invalidationContinuationData', 'timedContinuationData', 'reloadContinuationData'):
            if item.get(key, {}).get('continuation'):
                return item[key]['continuation'], int(item[key].get('timeoutMs') or 2000)
    return None, 3000


def yt_start(video):
    req = urllib.request.Request('https://www.youtube.com/live_chat?is_popout=1&v=' + video, headers=HEADERS)
    html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    blob = re.search(r'(?:window\["ytInitialData"\]|var ytInitialData)\s*=\s*(\{.+?\});\s*</script>', html, re.S)
    if not key or not blob:
        raise OSError('no chat page')
    token, _ = yt_next(json.loads(blob.group(1)))
    if not token:
        raise OSError('no chat continuation')
    return key.group(1), token


def yt_poll(channel, video, counter, still):
    """One live video's chat: every message is counted the moment it arrives."""
    seen = set()
    wait = 3
    while still():
        try:
            key, token = yt_start(video)
            while still() and token:
                body = json.dumps({'context': {'client': {'clientName': 'WEB', 'clientVersion': '2.20260101.00.00', 'hl': 'en'}}, 'continuation': token}).encode()
                req = urllib.request.Request('https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key=' + key, data=body, headers=dict(HEADERS, **{'Content-Type': 'application/json'}))
                data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace'))
                for action in ((data.get('continuationContents') or {}).get('liveChatContinuation') or {}).get('actions') or []:
                    item = (action.get('addChatItemAction') or {}).get('item') or {}
                    r = item.get('liveChatTextMessageRenderer') or item.get('liveChatPaidMessageRenderer')
                    if not r or r.get('id') in seen:
                        continue
                    seen.add(r.get('id'))
                    at = int(r.get('timestampUsec') or 0) / 1e6 or time.time()
                    counter.add(channel, r.get('authorExternalChannelId') or '?', yt_text(r), at)
                if len(seen) > 5000:
                    seen.clear()
                token, ms = yt_next(data)
                wait = 3
                time.sleep(min(5, max(1.0, ms / 1000)))
            time.sleep(wait)
        except (OSError, ValueError, KeyError):
            time.sleep(wait)
            wait = min(60, wait * 2)


def videos_now(folder):
    try:
        data = json.loads((Path(folder) / 'listen.json').read_text())
        if time.time() - float(data.get('updated') or 0) > 600:
            return {}
        return {c: v for c, v in (data.get('videos') or {}).items() if c in (data.get('channels') or []) and str(c).startswith('yt:') and re.fullmatch(r'[\w-]{11}', str(v))}
    except (OSError, ValueError):
        return {}


def youtube_chats(folder, lock):
    """Follows the YouTube channels listen.json names (with their live video) and writes their five-second counts."""
    db = database(folder)
    counter = Counter()
    workers = {}
    flushed = 0
    while True:
        try:
            if lock.read_text().strip() != str(os.getpid()):
                return
        except OSError:
            return
        videos = videos_now(folder)
        for c, v in videos.items():
            if c not in workers or workers[c][1] != v or not workers[c][0].is_alive():
                th = threading.Thread(target=yt_poll, args=(c, v, counter, lambda c=c, v=v: videos_now(folder).get(c) == v), daemon=True)
                th.start()
                workers[c] = (th, v)
        now = time.time()
        if now - flushed > 5:
            flushed = now
            rows = counter.closed(now)
            if rows:
                db.executemany('INSERT OR REPLACE INTO buckets VALUES(?,?,?,?,?,?,?,?,?)', rows)
                db.commit()
        time.sleep(2)


def downloader(extra=None):
    os.environ['YTDLP_NO_PLUGINS'] = '1'
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    import yt_dlp, imageio_ffmpeg

    class Quiet:
        def debug(self, *a): pass
        def info(self, *a): pass
        def warning(self, *a): pass
        def error(self, *a): pass
    opts = {'quiet': True, 'no_warnings': True, 'logger': Quiet(), 'noplaylist': True, 'socket_timeout': 20, 'retries': 1, 'cachedir': False,
            'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe()}
    opts.update(extra or {})
    return yt_dlp.YoutubeDL(opts)


def probe_youtube(channel):
    out = dict(channel=channel, live=False, checked=time.time(), platform='youtube')
    try:
        with downloader({'skip_download': True}) as d:
            info = d.extract_info('https://www.youtube.com/@' + channel[3:] + '/live', download=False)
    except Exception as exc:
        if not re.search(r'not currently live|will begin|premiere', str(exc)):
            out['error'] = str(exc)[:160]
        return out
    if not info.get('is_live'):
        return out
    began = info.get('release_timestamp') or info.get('timestamp')
    text = str(info.get('title') or '') + ' ' + str(info.get('description') or '')[:1500]
    out.update(live=True, started=began, title=str(info.get('title') or '')[:200], vod=str(info.get('id') or ''), vod_duration=0, vod_started=began,
               game='Grand Theft Auto VI' if GAME.search(text) else '', viewers=info.get('concurrent_view_count'))
    return out


def twitch_viewers(channel):
    """How many people watch right now. Twitch gives no count without an API key, so the public DecAPI counter is asked
    (one small GET per live channel, at most every few minutes); None when it does not answer."""
    try:
        req = urllib.request.Request('https://decapi.me/twitch/viewercount/' + channel, headers={'User-Agent': 'orbit-stream-watch'})
        text = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', 'replace').strip()
        return int(text) if re.fullmatch(r'\d{1,9}', text) else None
    except Exception:
        return None


def probe_channel(channel):
    if channel.startswith('yt:'):
        return probe_youtube(channel)
    out = dict(channel=channel, live=False, checked=time.time())
    try:
        with downloader({'skip_download': True}) as d:
            info = d.extract_info('https://www.twitch.tv/' + channel, download=False)
    except Exception as exc:
        if 'not currently live' not in str(exc):
            out['error'] = str(exc)[:160]
        return out
    if not info.get('is_live'):
        return out
    out.update(live=True, started=info.get('timestamp'), title=str(info.get('description') or info.get('title') or '')[:200])
    out['viewers'] = twitch_viewers(channel)
    try:
        with downloader({'skip_download': True, 'extract_flat': True, 'playlistend': 1}) as d:
            entry = ((d.extract_info('https://www.twitch.tv/' + channel + '/videos?filter=archives&sort=time', download=False).get('entries')) or [None])[0]
        if entry:
            with downloader({'skip_download': True}) as d:
                vod = d.extract_info(entry['url'], download=False)
            # The recording of this very broadcast starts within a minute of it; an older one is another day's stream.
            if vod.get('is_live') or abs(float(vod.get('timestamp') or 0) - float(out['started'] or 0)) < 120:
                chapters = [str(c.get('title') or '') for c in vod.get('chapters') or [] if c.get('title')]
                out.update(vod=str(vod.get('id') or '').lstrip('v'), vod_duration=float(vod.get('duration') or 0), vod_started=vod.get('timestamp'),
                           game=chapters[-1] if chapters else '')
    except Exception as exc:
        out['vod_error'] = str(exc)[:160]
    return out


def probe(request):
    channels = [c for c in request.get('channels') or [] if isinstance(c, str) and CHANNEL.fullmatch(c)][:60]
    result = dict(checked=time.time(), channels=[probe_channel(c) for c in channels])
    if request.get('out'):
        atomic_json(request['out'], result)
    return result


def twitch_direct(vod, start, duration, out):
    """A Twitch recording is a list of 10-second fMP4 segments: download only the ones that hold the window and cut them exactly.
    (yt-dlp's range download of a running broadcast took over ten minutes for a 30 second clip; this takes a few seconds.)"""
    import subprocess, tempfile
    import imageio_ffmpeg
    with downloader({'skip_download': True, 'format': 'best[height<=720]/best'}) as d:
        info = d.extract_info('https://www.twitch.tv/videos/' + vod, download=False)
    url, headers = info['url'], info.get('http_headers') or {}
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=30).read()
    text = get(url).decode('utf-8', 'replace')
    base = url.rsplit('/', 1)[0] + '/'
    full = lambda name: name if name.startswith('http') else base + name
    init = re.search(r'#EXT-X-MAP:URI="([^"]+)"', text)
    segments = re.findall(r'#EXTINF:([\d.]+),[^\n]*\n([^#\s][^\n]*)', text)
    if not segments:
        raise ValueError('A felvétel lejátszási listája üres.')
    at, chosen, first = 0.0, [], None
    for length, name in segments:
        length = float(length)
        if at + length > start and at < start + duration:
            chosen.append(name.strip())
            first = at if first is None else first
        at += length
    if at < start + duration - 2 or not chosen:
        raise ValueError('A felvétel még nem ér el eddig a pillanatig.')
    with tempfile.TemporaryDirectory() as tmp:
        joined = Path(tmp) / 'joined.mp4'
        with open(joined, 'wb') as fh:
            if init:
                fh.write(get(full(init.group(1))))
            for name in chosen:
                fh.write(get(full(name)))
        out = Path(out)
        target = out.with_suffix('.mp4')
        done = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(joined), '-ss', str(round(start - first, 2)), '-t', str(duration),
                               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(target)],
                              capture_output=True, text=True, timeout=240)
        if done.returncode != 0 or not target.is_file() or target.stat().st_size < 50_000:
            raise ValueError('A részlet vágása nem sikerült: ' + done.stderr[-200:])
    return dict(file=str(target), bytes=target.stat().st_size, title=str(info.get('title') or '')[:200], uploader=str(info.get('uploader') or '')[:80])


def hls_segments(url, headers, window_start, window_end):
    """The segments of one HLS playlist that hold [window_start, window_end] (unix times), with the first one's start time.
    Times come from EXT-X-PROGRAM-DATE-TIME, counted on with EXTINF."""
    import calendar
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=30).read()
    text = get(url).decode('utf-8', 'replace')
    base = url.rsplit('/', 1)[0] + '/'
    full = lambda name: name if name.startswith('http') else base + name
    init = re.search(r'#EXT-X-MAP:URI="([^"]+)"', text)
    at, chosen, first, pending = None, [], None, None
    for line in text.splitlines():
        if line.startswith('#EXT-X-PROGRAM-DATE-TIME:'):
            stamp = line.split(':', 1)[1].strip().replace('Z', '+0000')
            stamp = re.sub(r'([+-]\d\d):(\d\d)$', r'\1\2', stamp)
            at = calendar.timegm(time.strptime(stamp[:19], '%Y-%m-%dT%H:%M:%S')) + (float('0' + stamp[19:stamp.index('+') if '+' in stamp[19:] else len(stamp)]) if stamp[19:20] == '.' else 0)
        elif line.startswith('#EXTINF:'):
            pending = float(line[8:].split(',')[0])
        elif line and not line.startswith('#') and pending is not None:
            if at is not None and at + pending > window_start and at < window_end:
                chosen.append(full(line.strip()))
                first = at if first is None else first
            at = at + pending if at is not None else None
            pending = None
    if not chosen:
        raise ValueError('A felvétel még nem ér el eddig a pillanatig.')
    return (full(init.group(1)) if init else None), chosen, first


def youtube_direct(vod, abs_start, duration, out):
    """A YouTube live is HLS: a video playlist and an audio playlist. Only the segments of the window are downloaded and cut exactly
    (yt-dlp cannot cut a running YouTube live: 'This format cannot be partially downloaded')."""
    import subprocess, tempfile
    import imageio_ffmpeg
    with downloader({'skip_download': True}) as d:
        info = d.extract_info('https://www.youtube.com/watch?v=' + vod, download=False)
    headers = info.get('http_headers') or {}
    hls = [f for f in info.get('formats') or [] if f.get('protocol') in ('m3u8_native', 'm3u8')]
    video = max([f for f in hls if f.get('vcodec') not in (None, 'none') and (f.get('height') or 0) <= 720], key=lambda f: f.get('height') or 0, default=None)
    audio = max([f for f in hls if f.get('vcodec') in (None, 'none') and f.get('acodec') not in ('none',)], key=lambda f: f.get('abr') or f.get('tbr') or 0, default=None) \
        or max([f for f in hls if f.get('vcodec') in (None, 'none')], key=lambda f: f.get('tbr') or 0, default=None)
    if not video:
        raise ValueError('A YouTube-adásnak nincs letölthető HLS-képe.')
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=30).read()
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for name, fmt in (('v', video), ('a', audio)):
            if not fmt:
                continue
            init, segs, first = hls_segments(fmt['url'], headers, abs_start, abs_start + duration)
            path = Path(tmp) / (name + '.mp4')
            with open(path, 'wb') as fh:
                if init:
                    fh.write(get(init))
                for u in segs:
                    fh.write(get(u))
            files.append((path, max(0.0, abs_start - first)))
        out = Path(out)
        target = out.with_suffix('.mp4')
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error']
        for path, offset in files:
            cmd += ['-ss', str(round(offset, 2)), '-i', str(path)]
        cmd += ['-t', str(duration), '-map', '0:v:0'] + (['-map', '1:a:0'] if len(files) > 1 else ['-map', '0:a?']) + \
               ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(target)]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if done.returncode != 0 or not target.is_file() or target.stat().st_size < 50_000:
            raise ValueError('A YouTube-részlet vágása nem sikerült: ' + done.stderr[-200:])
    return dict(file=str(target), bytes=target.stat().st_size, title=str(info.get('title') or '')[:200], uploader=str(info.get('uploader') or '')[:80])


def fetch(request):
    from yt_dlp.utils import download_range_func
    vod = str(request['vod'])
    youtube = request.get('platform') == 'youtube'
    if not re.fullmatch(r'[\w-]{11}' if youtube else r'\d{6,14}', vod):
        raise ValueError('Érvénytelen felvételazonosító.')
    start, duration = max(0.0, float(request['start'])), float(request['duration'])
    if not 5 <= duration <= 180:
        raise ValueError('Egy részlet 5–180 másodperc lehet.')
    out = Path(request['out'])
    out.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    if shutil.disk_usage(out.parent).free < 3 * 1024 ** 3:
        raise ValueError('Kevés a szabad tárhely (3 GB alatt), nem töltök le új részletet.')
    opts = {'format': 'best[height<=720]/best', 'outtmpl': str(out.with_suffix('')) + '.%(ext)s', 'overwrites': True,
            'download_ranges': download_range_func(None, [(start, start + duration)])}
    if youtube:
        opts.update(format='bv*[height<=720]+ba/b[height<=720]/b', live_from_start=True, merge_output_format='mp4')
    if youtube and request.get('abs_start'):
        try:
            return youtube_direct(vod, float(request['abs_start']), duration, out)
        except ValueError:
            raise
        except Exception:
            pass          # the yt-dlp route below is the fallback
    if not youtube:
        try:
            return twitch_direct(vod, start, duration, out)
        except ValueError:
            raise
        except Exception:
            pass          # anything unexpected: the slower yt-dlp route below still works
    with downloader(opts) as d:
        info = d.extract_info(('https://www.youtube.com/watch?v=' if youtube else 'https://www.twitch.tv/videos/') + vod, download=False)
        if float(info.get('duration') or 0) < start + duration - 2 and not (youtube and info.get('is_live')):
            raise ValueError('A felvétel még nem ér el eddig a pillanatig.')
        d.process_ie_result(info, download=True)
    files = [p for p in out.parent.glob(out.stem + '.*') if p.suffix.lower() in ('.mp4', '.mkv', '.ts', '.webm')]
    if len(files) != 1 or files[0].stat().st_size < 50_000:
        raise ValueError('A részlet letöltése nem sikerült.')
    return dict(file=str(files[0]), bytes=files[0].stat().st_size, title=str(info.get('title') or '')[:200], uploader=str(info.get('uploader') or '')[:80])


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'listen':
        listen(sys.argv[2])
        sys.exit(0)
    try:
        request = json.loads(sys.stdin.read(20000) or '{}')
        print(json.dumps(dict(ok=True, result=dict(probe=probe, fetch=fetch)[action](request)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps(dict(ok=False, message=str(exc)[:400])))
        sys.exit(1)
