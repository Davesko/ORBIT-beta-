"""Frissítés: the installed ORBIT updates itself with one click, from a plain download - no git, no GitHub login.

How it works
- The repository carries a file `orbit_app/BUILD` (written by the export, a sortable stamp like 20261118190000-ab12cd3).
  `check` reads the one on GitHub and compares it with the installed one (install.json -> build).
- `apply` downloads the repository as a ZIP, unpacks it to <Orbit data>/updates/<build>/ and runs `./install.sh --update` there in
  the background (it recompiles the app, sets up the video runtime if something changed, copies the new files; chats, memories,
  projects and accounts are untouched). install.json then points to the new folder. The app has to be restarted afterwards.
- The source (`owner/repo`) is written into install.json by the installer (from the UPDATE_SOURCE file of the repository).
- A public repository needs nothing else. A PRIVATE one needs a read-only access key (GitHub fine-grained token with "Contents: read"),
  saved once in <Orbit data>/update-token (the Settings card has a field for it); after that it is one click as well.
An ORBIT installed before this existed (it only knows `git pull`) has to be installed once from a fresh download of the repository.
"""
import io, json, re, shutil, subprocess, time, urllib.error, urllib.request, zipfile
from pathlib import Path

INSTALL = 'install.json'
LOG = 'logs/update.log'
TOKEN = 'update-token'


def info(s):
    try:
        data = json.loads((s.root / INSTALL).read_text())
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def token(s):
    try:
        value = (s.root / TOKEN).read_text().strip()
    except OSError:
        return ''
    return value if re.fullmatch(r'[A-Za-z0-9_\-]{20,255}', value) else ''


def headers(s, raw=False):
    h = {'User-Agent': 'orbit-updater', 'Accept': 'application/vnd.github.raw' if raw else 'application/vnd.github+json'}
    if token(s):
        h['Authorization'] = 'Bearer ' + token(s)
    return h


def http_get(url, head, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=timeout).read()


def source_of(s):
    src = str(info(s).get('source') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+', src):
        raise ValueError('Ennek a telepítésnek nincs frissítési forrása. Töltsd le a tárat újra (Code → Download ZIP), és futtasd benne: ./install.sh')
    return src, str(info(s).get('branch') or 'main')


def remote_build(s):
    src, branch = source_of(s)
    try:
        text = http_get('https://api.github.com/repos/%s/contents/orbit_app/BUILD?ref=%s' % (src, branch), headers(s, raw=True), 30).decode().strip()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise ValueError('A frissítési forrás nem érhető el (a tár privát, vagy rossz a frissítési kulcs). Add meg a frissítési kulcsot a Frissítés kártyán, vagy a tár tulajdonosa tegye nyilvánossá.') from None
        raise ValueError('A GitHub nem válaszolt (%s). Próbáld újra később.' % error.code) from None
    except (urllib.error.URLError, OSError):
        raise ValueError('Nincs internetkapcsolat, vagy a GitHub nem érhető el.') from None
    if not re.fullmatch(r'\d{14}-[0-9a-f]{4,40}', text):
        raise ValueError('A frissítési forrás verziófájlja nem értelmezhető.')
    return text


def check(s):
    """Is there something newer upstream (read-only)."""
    current = str(info(s).get('build') or '')
    version = info(s).get('version') or ''
    try:
        latest = remote_build(s)
    except ValueError as error:
        return dict(available=False, version=version, build=current, error=str(error)[:300], needs_key=('privát' in str(error)), checked=time.time())
    return dict(available=latest > current if current else True, version=version, build=current, latest=latest, checked=time.time())


def download(s):
    src, branch = source_of(s)
    try:
        raw = http_get('https://api.github.com/repos/%s/zipball/%s' % (src, branch), headers(s), 600)
    except (urllib.error.URLError, OSError) as error:
        raise ValueError('A letöltés nem sikerült: ' + str(error)[:160]) from None
    return raw


def apply(s):
    state = check(s)
    if state.get('error'):
        raise ValueError(state['error'])
    if not state['available']:
        return dict(message='Már a legfrissebb verziót használod.', **state)
    raw = download(s)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError('A letöltött frissítés nem érvényes ZIP.') from None
    names = archive.namelist()
    top = names[0].split('/')[0] + '/'
    if top + 'install.sh' not in names or top + 'orbit_app/BUILD' not in names:
        raise ValueError('A letöltött csomag nem ORBIT telepítő.')
    folder = s.root / 'updates' / state['latest']
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for member in archive.infolist():
        target = (folder / member.filename[len(top):]).resolve()
        if not member.filename.startswith(top) or folder.resolve() not in target.parents and target != folder.resolve():
            continue
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
    for script in folder.glob('*.sh'):
        script.chmod(0o755)
    # Older update folders are removed (the last two stay).
    olds = sorted([p for p in (s.root / 'updates').iterdir() if p.is_dir() and p != folder])
    for p in olds[:-1]:
        shutil.rmtree(p, ignore_errors=True)
    log = s.root / LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('')
    with open(log, 'ab') as out:
        subprocess.Popen(['/bin/bash', '-lc', 'cd "$0" && /bin/bash ./install.sh --update', str(folder)], stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)
    return dict(message='A frissítés elindult (1-3 perc, a videós rész változása esetén tovább). Ha kész, zárd be és nyisd meg újra az ORBIT-ot (Cmd+Q).', started=True)


def save_token(s, value):
    value = str(value or '').strip()
    if not value:
        (s.root / TOKEN).unlink(missing_ok=True)
        return dict(message='A frissítési kulcs törölve.')
    if not re.fullmatch(r'[A-Za-z0-9_\-]{20,255}', value):
        raise ValueError('Ez nem hasonlít GitHub hozzáférési kulcsra.')
    path = s.root / TOKEN
    path.write_text(value)
    path.chmod(0o600)
    return dict(message='A frissítési kulcs elmentve.')


def status(s):
    try:
        text = (s.root / LOG).read_text()[-1500:]
    except OSError:
        text = ''
    return dict(log=text, finished='✓ Kész' in text, failed=bool(text) and ('error' in text.lower() or 'fatal' in text.lower()) and '✓ Kész' not in text)


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'update_check':
        return check(s)
    if op == 'update_apply':
        return apply(s)
    if op == 'update_token':
        return save_token(s, args.get('value'))
    if op == 'update_status':
        return dict(status(s), version=info(s).get('version') or '')
    raise ValueError('Ismeretlen frissítési művelet.')
