"""Instagram, Facebook Page and TikTok posting in the isolated media runtime. Tokens live in the macOS Keychain.

Runs as `social_runtime.py <action> <root> <account key>` with a JSON request on stdin and one JSON line on stdout.
Only the platforms' own documented endpoints are called, with the owner's own token:

- Instagram Reels: container with upload_type=resumable, the file to rupload.facebook.com, then media_publish.
  A token starting with IG is an "Instagram API with Instagram Login" token (graph.instagram.com); any other is a
  Facebook Login token whose page carries the Instagram professional account (graph.facebook.com).
- Facebook Page Reels: video_reels start, upload, finish.
- TikTok: Login Kit for desktop (PKCE, local callback) and the Content Posting API with FILE_UPLOAD. An app TikTok
  has not audited may only post privately; the privacy levels TikTok offers for the account are read first.

Never logs or returns a token, an authorization code or a response body that may carry one.
"""
import hashlib, json, os, secrets, sys, time
from pathlib import Path
from urllib import error, parse, request as urlrequest

GRAPH = 'v21.0'
SERVICE = 'hu.orbit.social'
TIKTOK_PORT = 8765
TIKTOK_REDIRECT = 'http://localhost:%d/callback/' % TIKTOK_PORT
TIKTOK_SCOPES = 'user.info.basic,video.publish,video.upload'
HOSTS = ('graph.instagram.com', 'graph.facebook.com', 'rupload.facebook.com', 'open.tiktokapis.com', 'open-upload.tiktokapis.com')


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    with os.fdopen(os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as handle:
        json.dump(data, handle)
    os.replace(temp, path)


def store():
    import keyring
    from keyring.backends.macOS import Keyring
    keyring.set_keyring(Keyring())
    return keyring


def saved(key):
    raw = store().get_password(SERVICE, key)
    if not raw:
        raise ValueError('A fiók mentett belépése nem található a Kulcskarikában. Csatlakoztasd újra.')
    return json.loads(raw)


def save(key, data):
    store().set_password(SERVICE, key, json.dumps(data))


class Refused(ValueError):
    pass


def http(url, data=None, headers=None, method=None, timeout=60, raw=False):
    """One HTTPS call to a known platform host. Errors carry the platform's own message, never the request."""
    host = parse.urlsplit(url).hostname or ''
    if parse.urlsplit(url).scheme != 'https' or not (host in HOSTS or host.endswith('.tiktokapis.com') or host.endswith('.tiktokcdn.com') or host.endswith('.tiktokcdn-us.com')):
        raise ValueError('Nem engedélyezett cím.')
    body = data if isinstance(data, (bytes, type(None))) else parse.urlencode(data).encode()
    req = urlrequest.Request(url, data=body, headers=headers or {}, method=method or ('POST' if body is not None else 'GET'))
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            text = response.read(2_000_000)
            if raw:
                return response.status, dict(response.headers), text
            return json.loads(text or b'{}')
    except error.HTTPError as exc:
        try:
            detail = json.loads(exc.read(20000))
        except ValueError:
            detail = {}
        inner = detail.get('error') if isinstance(detail.get('error'), dict) else detail
        message = str(inner.get('error_user_msg') or inner.get('message') or inner.get('error_description') or inner.get('code') or '')[:300]
        raise Refused('A platform elutasította a kérést (' + str(exc.code) + ')' + (': ' + message if message else '.')) from None
    except error.URLError:
        raise ValueError('A platform nem érhető el. Ellenőrizd a hálózatot.') from None


def progress(req, percent, **extra):
    if req.get('progress'):
        atomic_json(req['progress'], dict(percent=percent, **extra))


# ---------------------------------------------------------------- Meta

def meta_host(token):
    return 'graph.instagram.com' if token.startswith('IG') else 'graph.facebook.com'


def verify(key, req):
    token, platform = req['token'], req['platform']
    if platform == 'tiktok':
        info = tiktok_user(token)
        save(key, dict(platform='tiktok', token=token, saved=time.time()))
        return dict(handle=info.get('display_name') or 'TikTok', external_id=info.get('open_id') or '')
    if platform == 'instagram' and token.startswith('IG'):
        me = http('https://graph.instagram.com/' + GRAPH + '/me?' + parse.urlencode(dict(fields='user_id,username', access_token=token)))
        if not me.get('user_id'):
            raise ValueError('Ez a token nem Instagram-fiókhoz tartozik.')
        save(key, dict(platform='instagram', token=token, user=str(me['user_id']), saved=time.time()))
        return dict(handle='@' + str(me.get('username') or ''), external_id=str(me['user_id']), expires=time.time() + 60 * 86400)
    pages = http('https://graph.facebook.com/' + GRAPH + '/me/accounts?' + parse.urlencode(
        dict(fields='name,id,access_token,instagram_business_account{id,username}', access_token=token))).get('data') or []
    if platform == 'instagram':
        page = next((p for p in pages if p.get('instagram_business_account')), None)
        if not page:
            raise ValueError('Ehhez a tokenhez nem tartozik olyan Facebook-oldal, amelyhez Instagram üzleti vagy alkotói fiók van kötve.')
        ig = page['instagram_business_account']
        save(key, dict(platform='instagram', token=page.get('access_token') or token, user=str(ig['id']), saved=time.time()))
        return dict(handle='@' + str(ig.get('username') or ''), external_id=str(ig['id']))
    if not pages:
        raise ValueError('Ehhez a tokenhez nem tartozik kezelhető Facebook-oldal.')
    page = pages[0]
    save(key, dict(platform='facebook', token=page.get('access_token') or token, user=str(page['id']), saved=time.time()))
    return dict(handle=str(page.get('name') or ''), external_id=str(page['id']))


def fresh_instagram(key, data):
    """An Instagram Login token lives 60 days and can be renewed once it is a day old; renew it when half is gone."""
    if data['token'].startswith('IG') and time.time() - float(data.get('saved') or 0) > 30 * 86400:
        try:
            out = http('https://graph.instagram.com/refresh_access_token?' + parse.urlencode(dict(grant_type='ig_refresh_token', access_token=data['token'])))
            if out.get('access_token'):
                data = dict(data, token=out['access_token'], saved=time.time())
                save(key, data)
        except ValueError:
            pass
    return data


def upload_bytes(url, token, path, req):
    size = os.path.getsize(path)
    with open(path, 'rb') as stream:
        body = stream.read()
    progress(req, 10, transfer_started=True)
    out = http(url, body, {'Authorization': 'OAuth ' + token, 'offset': '0', 'file_size': str(size), 'Content-Type': 'application/octet-stream'}, timeout=900)
    progress(req, 70, transfer_started=True)
    return out


def post_instagram(key, req):
    data = fresh_instagram(key, saved(key))
    token, user, host = data['token'], data['user'], meta_host(data['token'])
    base = 'https://' + host + '/' + GRAPH + '/'
    made = http(base + user + '/media', dict(media_type='REELS', upload_type='resumable', caption=req.get('caption') or '', share_to_feed='true', access_token=token))
    container = str(made.get('id') or '')
    if not container:
        raise ValueError('Az Instagram nem adott feltöltési azonosítót.')
    upload_bytes(made.get('uri') or 'https://rupload.facebook.com/ig-api-upload/' + GRAPH + '/' + container, token, req['source'], req)
    for _ in range(90):
        state = http(base + container + '?' + parse.urlencode(dict(fields='status_code,status', access_token=token)))
        if state.get('status_code') == 'FINISHED':
            break
        if state.get('status_code') in ('ERROR', 'EXPIRED'):
            raise ValueError('Az Instagram nem tudta feldolgozni a videót: ' + str(state.get('status') or state['status_code'])[:200])
        time.sleep(4)
    else:
        raise ValueError('Az Instagram feldolgozása nem fejeződött be időben. Nézd meg a fiókban, mielőtt újra próbálod.')
    progress(req, 90, transfer_started=True)
    done = http(base + user + '/media_publish', dict(creation_id=container, access_token=token))
    media = str(done.get('id') or '')
    if not media:
        raise ValueError('Az Instagram nem igazolta vissza a közzétételt.')
    progress(req, 100, id=media)
    url = ''
    try:
        url = http(base + media + '?' + parse.urlencode(dict(fields='permalink', access_token=token))).get('permalink') or ''
    except ValueError:
        pass
    return dict(id=media, url=url)


def post_facebook(key, req):
    data = saved(key)
    token, page = data['token'], data['user']
    base = 'https://graph.facebook.com/' + GRAPH + '/' + page + '/video_reels'
    start = http(base, dict(upload_phase='start', access_token=token))
    video = str(start.get('video_id') or '')
    if not video or not start.get('upload_url'):
        raise ValueError('A Facebook nem adott feltöltési azonosítót.')
    progress(req, 5, id=video)
    upload_bytes(start['upload_url'], token, req['source'], req)
    http(base, dict(upload_phase='finish', video_id=video, video_state='PUBLISHED', description=req.get('caption') or '', access_token=token))
    progress(req, 100, id=video)
    return dict(id=video, url='https://www.facebook.com/reel/' + video)


# ---------------------------------------------------------------- TikTok

def tiktok_api(path, token, body=None):
    out = http('https://open.tiktokapis.com' + path, json.dumps(body or {}).encode() if body is not None else None,
               {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json; charset=UTF-8'})
    err = out.get('error') or {}
    if err.get('code') not in (None, 'ok'):
        raise Refused('A TikTok elutasította a kérést: ' + str(err.get('message') or err.get('code'))[:300])
    return out.get('data') or {}


def tiktok_user(token):
    out = http('https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name', headers={'Authorization': 'Bearer ' + token})
    return (out.get('data') or {}).get('user') or {}


def tiktok_token(data, key):
    if time.time() < float(data.get('expires') or 0) - 120 or not data.get('refresh'):
        return data['token']
    out = http('https://open.tiktokapis.com/v2/oauth/token/', dict(client_key=data['client_key'], client_secret=data['client_secret'],
                                                                  grant_type='refresh_token', refresh_token=data['refresh']),
               {'Content-Type': 'application/x-www-form-urlencoded'})
    if not out.get('access_token'):
        raise ValueError('A TikTok-belépés lejárt. Csatlakoztasd újra a fiókot.')
    data.update(token=out['access_token'], refresh=out.get('refresh_token') or data['refresh'], expires=time.time() + float(out.get('expires_in') or 86400))
    save(key, data)
    return data['token']


def tiktok_connect(root, key, req):
    """Desktop login: opens nothing itself. Writes the authorization address for the app, then waits for the callback."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    folder = Path(root) / 'integrations/social' / key
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    # TikTok's desktop flow wants the SHA-256 of the verifier as a hex string (not base64url).
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    url = 'https://www.tiktok.com/v2/auth/authorize/?' + parse.urlencode(dict(
        client_key=req['client_key'], scope=TIKTOK_SCOPES, response_type='code', redirect_uri=TIKTOK_REDIRECT, state=state,
        code_challenge=challenge, code_challenge_method='S256'))
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            query = parse.parse_qs(parse.urlsplit(self.path).query)
            valid = parse.urlsplit(self.path).path.rstrip('/') == '/callback' and secrets.compare_digest(query.get('state', [''])[0], state)
            self.send_response(200 if valid else 400)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(('A bejelentkezés válasza megérkezett. Visszatérhetsz az ORBIT appba.' if valid else 'Érvénytelen bejelentkezési válasz.').encode())
            if valid:
                result.update(code=query.get('code', [''])[0], error=query.get('error', [''])[0])
    try:
        server = HTTPServer(('127.0.0.1', TIKTOK_PORT), Callback)
    except OSError:
        raise ValueError('A %d-es helyi kapu foglalt; zárd be, ami használja, és próbáld újra.' % TIKTOK_PORT) from None
    server.timeout = 1
    atomic_json(folder / 'auth.json', dict(status='waiting', created=time.time()))
    print(json.dumps(dict(ok=True, url=url, redirect=TIKTOK_REDIRECT)), flush=True)
    # The app has its answer; the rest runs detached from it.
    if os.fork():
        os._exit(0)
    os.setsid()
    for fd in (0, 1, 2):
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        start = time.monotonic()
        while not result and time.monotonic() - start < 300:
            server.handle_request()
        if not result.get('code'):
            raise ValueError('A bejelentkezés megszakadt vagy lejárt.')
        out = http('https://open.tiktokapis.com/v2/oauth/token/', dict(client_key=req['client_key'], client_secret=req['client_secret'], code=result['code'],
                                                                      grant_type='authorization_code', redirect_uri=TIKTOK_REDIRECT, code_verifier=verifier),
                   {'Content-Type': 'application/x-www-form-urlencoded'})
        if not out.get('access_token'):
            raise ValueError('A TikTok nem adott hozzáférést: ' + str(out.get('error_description') or out.get('error') or '')[:200])
        user = tiktok_user(out['access_token'])
        save(key, dict(platform='tiktok', token=out['access_token'], refresh=out.get('refresh_token'), expires=time.time() + float(out.get('expires_in') or 86400),
                       client_key=req['client_key'], client_secret=req['client_secret'], saved=time.time()))
        atomic_json(folder / 'auth.json', dict(status='done', handle=user.get('display_name') or 'TikTok', external_id=out.get('open_id') or user.get('open_id') or '', created=time.time()))
    except Exception as exc:
        atomic_json(folder / 'auth.json', dict(status='failed', error=str(exc)[:300] if isinstance(exc, ValueError) else 'A TikTok-bejelentkezés nem sikerült.', created=time.time()))
    finally:
        server.server_close()
    os._exit(0)


def post_tiktok(key, req):
    data = saved(key)
    token = tiktok_token(data, key)
    creator = tiktok_api('/v2/post/publish/creator_info/query/', token, {})
    options = creator.get('privacy_level_options') or []
    wanted = {'public': 'PUBLIC_TO_EVERYONE', 'unlisted': 'MUTUAL_FOLLOW_FRIENDS', 'private': 'SELF_ONLY'}[req.get('privacy') or 'public']
    level = wanted if wanted in options else 'SELF_ONLY' if 'SELF_ONLY' in options else (options or [wanted])[0]
    size = os.path.getsize(req['source'])
    init = tiktok_api('/v2/post/publish/video/init/', token, dict(
        post_info=dict(title=(req.get('caption') or req.get('title') or '')[:2200], privacy_level=level, disable_duet=False, disable_comment=False, disable_stitch=False),
        source_info=dict(source='FILE_UPLOAD', video_size=size, chunk_size=size, total_chunk_count=1)))
    publish = str(init.get('publish_id') or '')
    if not publish or not init.get('upload_url'):
        raise ValueError('A TikTok nem adott feltöltési címet.')
    progress(req, 5, id=publish)
    with open(req['source'], 'rb') as stream:
        body = stream.read()
    http(init['upload_url'], body, {'Content-Type': 'video/mp4', 'Content-Range': 'bytes 0-%d/%d' % (size - 1, size)}, method='PUT', timeout=900, raw=True)
    progress(req, 80, id=publish)
    note = ''
    for _ in range(45):
        state = tiktok_api('/v2/post/publish/status/fetch/', token, dict(publish_id=publish))
        if state.get('status') == 'PUBLISH_COMPLETE':
            break
        if state.get('status') == 'FAILED':
            raise ValueError('A TikTok nem tette közzé a videót: ' + str(state.get('fail_reason') or '')[:200])
        time.sleep(4)
    else:
        note = 'A TikTok még dolgozik rajta; a fiókban ellenőrizd.'
    progress(req, 100, id=publish)
    private = level == 'SELF_ONLY' and wanted != 'SELF_ONLY'
    return dict(id=publish, url='', note=note or ('A TikTok ennél az alkalmazásnál csak privát közzétételt enged (nem auditált alkalmazás): a videó privátként került fel.' if private else ''))


# ---------------------------------------------------------------- reach (public counters of the account's own posts)

def reach_instagram(key, req):
    data = fresh_instagram(key, saved(key))
    token, user = data['token'], data['user']
    base = 'https://' + meta_host(token) + '/' + GRAPH + '/'
    profile = {}
    try:
        profile = http(base + user + '?' + parse.urlencode(dict(fields='followers_count,media_count', access_token=token)))
    except ValueError:
        pass
    media = http(base + user + '/media?' + parse.urlencode(dict(fields='id,caption,permalink,timestamp,like_count,comments_count,media_product_type', limit=30, access_token=token))).get('data') or []
    items = []
    for m in media:
        views = None
        for metric in ('views', 'plays', 'impressions'):
            try:
                rows = http(base + m['id'] + '/insights?' + parse.urlencode(dict(metric=metric, access_token=token))).get('data') or []
                if rows and rows[0].get('values'):
                    views = int(rows[0]['values'][0].get('value') or 0)
                    break
            except ValueError:
                continue
        items.append(dict(id=m['id'], title=(m.get('caption') or '')[:120], url=m.get('permalink') or '', published=m.get('timestamp'), views=views,
                          likes=m.get('like_count'), comments=m.get('comments_count')))
    return dict(channel=dict(subscribers=profile.get('followers_count'), videos=profile.get('media_count'), views=sum(i['views'] or 0 for i in items)), items=items)


def reach_facebook(key, req):
    data = saved(key)
    token, page = data['token'], data['user']
    base = 'https://graph.facebook.com/' + GRAPH + '/'
    info = {}
    try:
        info = http(base + page + '?' + parse.urlencode(dict(fields='fan_count,followers_count', access_token=token)))
    except ValueError:
        pass
    videos = http(base + page + '/videos?' + parse.urlencode(dict(fields='id,description,created_time,permalink_url,views', limit=30, access_token=token))).get('data') or []
    items = [dict(id=v['id'], title=(v.get('description') or '')[:120], url=('https://www.facebook.com' + v['permalink_url']) if str(v.get('permalink_url', '')).startswith('/') else v.get('permalink_url', ''),
                  published=v.get('created_time'), views=v.get('views'), likes=None, comments=None) for v in videos]
    return dict(channel=dict(subscribers=info.get('followers_count') or info.get('fan_count'), videos=len(items), views=sum(i['views'] or 0 for i in items)), items=items)


def reach_tiktok(key, req):
    data = saved(key)
    token = tiktok_token(data, key)
    user = {}
    try:
        user = (http('https://open.tiktokapis.com/v2/user/info/?fields=follower_count,video_count', headers={'Authorization': 'Bearer ' + token}).get('data') or {}).get('user') or {}
    except ValueError:
        pass
    try:
        out = tiktok_api('/v2/video/list/?fields=id,title,create_time,view_count,like_count,comment_count,share_count,share_url', token, dict(max_count=20))
    except ValueError as exc:
        raise ValueError('A TikTok-megtekintések lekéréséhez a TikTok-alkalmazásnak „video.list” jogosultság kell (és a fiókot újra kell csatlakoztatni). ' + str(exc)[:120]) from None
    items = [dict(id=v['id'], title=(v.get('title') or '')[:120], url=v.get('share_url') or '', published=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(v.get('create_time') or 0)),
                  views=v.get('view_count'), likes=v.get('like_count'), comments=v.get('comment_count')) for v in out.get('videos') or []]
    return dict(channel=dict(subscribers=user.get('follower_count'), videos=user.get('video_count'), views=sum(i['views'] or 0 for i in items)), items=items)


def main():
    action, root, key = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key):
        raise ValueError('Érvénytelen fiók.')
    req = json.loads(sys.stdin.read(20000) or '{}')
    if action == 'verify':
        return verify(key, req)
    if action == 'tiktok_connect':
        return tiktok_connect(root, key, req)
    if action == 'forget':
        try:
            store().delete_password(SERVICE, key)
        except Exception as exc:
            if type(exc).__name__ != 'PasswordDeleteError':
                raise
        return {}
    if action == 'reach':
        return dict(tiktok=reach_tiktok, instagram=reach_instagram, facebook=reach_facebook)[req['platform']](key, req)
    if action == 'post':
        if not Path(req['source']).is_file():
            raise ValueError('A videófájl nem található.')
        return dict(tiktok=post_tiktok, instagram=post_instagram, facebook=post_facebook)[req['platform']](key, req)
    raise ValueError('Ismeretlen művelet.')


if __name__ == '__main__':
    try:
        print(json.dumps(dict(ok=True, **(main() or {}))), flush=True)
    except Exception as exc:
        safe = isinstance(exc, ValueError)
        print(json.dumps(dict(ok=False, message=str(exc)[:400] if safe else 'A művelet nem sikerült [' + type(exc).__name__ + ']', diagnostic_type=type(exc).__name__)))
        sys.exit(1)
