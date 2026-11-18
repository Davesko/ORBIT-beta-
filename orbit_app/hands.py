"""Client of ORBIT Hands (OrbitHands.swift): the assistant's own mouse, keyboard and eyes on this Mac.

ORBIT Hands is a separate small app in ~/Applications with its own macOS permissions, so the grants survive ORBIT
updates: it is rebuilt only when its own source changes (an ad-hoc signed app loses its grants on every rebuild).
"""
import hashlib
import json
import os
import plistlib
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

PORT = 11460
APP = Path.home() / 'Applications/ORBIT Hands.app'
SOURCE = Path(__file__).with_name('OrbitHands.swift')
BUNDLE_ID = 'hu.orbit.hands'
PERMISSIONS = dict(
    accessibility=dict(label='Kisegítő lehetőségek', why='kattintás, gépelés és billentyűparancsok a saját egerével'),
    screen=dict(label='Képernyőfelvétel', why='a képernyőn lévő szöveg és gombok felismerése, ahol az app nem ad UI-fát'),
)


class HandsError(ValueError):
    pass


class Stopped(HandsError):
    pass


STYLES = dict(orbit='ORBIT mag', yarn='Fonalgombolyag')


def source_hash(path=SOURCE):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def installed_hash():
    try:
        return plistlib.loads((APP / 'Contents/Info.plist').read_bytes()).get('OrbitSourceHash')
    except (OSError, ValueError):
        return None


def install(source=SOURCE, app=APP, force=False):
    """Builds ORBIT Hands.app when its source changed. Returns True when a new build was installed."""
    digest = source_hash(source)
    if not force and installed_hash() == digest and (app / 'Contents/MacOS/OrbitHands').is_file():
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        binary = tmp / 'OrbitHands'
        r = subprocess.run(['/usr/bin/swiftc', '-O', str(source), '-o', str(binary), '-framework', 'AppKit', '-framework', 'Carbon',
                            '-framework', 'Vision', '-module-cache-path', str(tmp / 'cache')], capture_output=True, text=True, timeout=600)
        if r.returncode:
            raise HandsError('Az ORBIT Hands fordítása nem sikerült: ' + r.stderr[-1500:])
        bundle = tmp / 'ORBIT Hands.app'
        (bundle / 'Contents/MacOS').mkdir(parents=True)
        (bundle / 'Contents/Resources').mkdir()
        shutil.copy2(binary, bundle / 'Contents/MacOS/OrbitHands')
        icon = Path(__file__).with_name('runtime') / 'Orbit.icns'
        if icon.is_file():
            shutil.copy2(icon, bundle / 'Contents/Resources/Orbit.icns')
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(dict(
            CFBundleIdentifier=BUNDLE_ID, CFBundleName='ORBIT Hands', CFBundleDisplayName='ORBIT Hands', CFBundleExecutable='OrbitHands',
            CFBundlePackageType='APPL', CFBundleShortVersionString='1.0', CFBundleVersion=digest, CFBundleIconFile='Orbit.icns',
            LSUIElement=True, LSMinimumSystemVersion='13.0', OrbitSourceHash=digest,
            NSAppleEventsUsageDescription='Az ORBIT asszisztens a kérésedre kezeli az alkalmazásokat.')))
        # Ad-hoc signing ties macOS permissions to this build's hash, so every rebuild silently lost them. A designated
        # requirement on the bundle identifier keeps the owner's grants across builds.
        r = subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', '--identifier', BUNDLE_ID,
                            '-r=designated => identifier "' + BUNDLE_ID + '"', str(bundle)], capture_output=True, text=True)
        if r.returncode:
            raise HandsError('Az ORBIT Hands aláírása nem sikerült: ' + r.stderr[-500:])
        stop()
        app.parent.mkdir(parents=True, exist_ok=True)
        if app.exists():
            shutil.rmtree(app)
        shutil.copytree(bundle, app, symlinks=True)
    return True


def stop():
    subprocess.run(['/usr/bin/pkill', '-x', 'OrbitHands'], capture_output=True)
    time.sleep(.3)


def call(cmd, timeout=30, **args):
    """One command to ORBIT Hands; starts the app when it is not running."""
    payload = (json.dumps(dict(cmd=cmd, **args), ensure_ascii=False) + '\n').encode()
    for attempt in range(2):
        try:
            with socket.create_connection(('127.0.0.1', PORT), timeout=3) as sock:
                sock.settimeout(timeout)
                sock.sendall(payload)
                data = b''
                while not data.endswith(b'\n'):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            reply = json.loads(data or b'{}')
            if not reply.get('ok'):
                error = str(reply.get('error') or 'Az ORBIT Hands nem válaszolt.')
                if error == 'stopped':
                    raise Stopped('Leállítottad a gépvezérlést (Esc vagy a menüsor). Nem folytatom.')
                if error.startswith('permission:'):
                    which = error.split(':', 1)[1]
                    raise HandsError('Ehhez az ORBIT Hands-nek kell a(z) „' + PERMISSIONS[which]['label'] + '” engedély (' + PERMISSIONS[which]['why'] + '). Megnyitottam a beállítást: kapcsold be az ORBIT Hands-et, majd kérd újra.') if _ask(which) else HandsError(error)
                raise HandsError(error)
            return reply
        except (ConnectionRefusedError, socket.timeout, FileNotFoundError, OSError) as exc:
            if isinstance(exc, HandsError):
                raise
            if attempt:
                raise HandsError('Az ORBIT Hands nem indult el. Ellenőrizd a Beállítások → Gépvezérlés részt.') from exc
            start()


def _ask(which):
    try:
        call('request', which=which)
    except HandsError:
        return False
    return True


def start():
    if not (APP / 'Contents/MacOS/OrbitHands').is_file():
        install()
    subprocess.run(['/usr/bin/open', '-g', str(APP)], capture_output=True)
    for _ in range(40):
        try:
            with socket.create_connection(('127.0.0.1', PORT), timeout=.3):
                return True
        except OSError:
            time.sleep(.15)
    return False


def status():
    """For the Settings page: what ORBIT Hands may do now."""
    try:
        s = call('status', timeout=5)
    except HandsError as exc:
        return dict(installed=APP.is_dir(), running=False, accessibility=False, screen=False, error=str(exc), permissions=PERMISSIONS, app=str(APP))
    return dict(installed=True, running=True, accessibility=bool(s.get('accessibility')), screen=bool(s.get('screen')), ax_probe=s.get('ax_probe'), permissions=PERMISSIONS, app=str(APP),
                style=s.get('style', 'orbit'), styles=STYLES)


def request(which):
    """Shows the macOS prompt and opens the exact Settings pane where ORBIT Hands is switched on."""
    if which not in PERMISSIONS:
        raise HandsError('Ismeretlen engedély.')
    call('request', which=which)
    return status()


def look(app=None, limit=120, text=True):
    """What is on screen: the front window's controls (numbered) and, where they are few, the visible text."""
    view = call('elements', limit=limit, **({'app': app} if app else {}))
    out = dict(app=view.get('app'), window=view.get('window'), elements=view.get('elements', []), has_window=view.get('has_window', True),
               window_frame=view.get('window_frame') or {}, windows=view.get('windows'), displays=view.get('displays') or [])
    if text and len(out['elements']) < 8:
        try:
            out['texts'] = call('ocr', limit=120).get('texts', [])
        except HandsError as exc:
            out['texts_error'] = str(exc)
    return out


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'hands_status':
        # macOS applies a new Screen Recording grant only to a freshly started app.
        if args.get('restart'):
            stop()
            start()
        return status()
    if op == 'hands_request':
        return request(args.get('which'))
    if op == 'hands_settings':
        call('settings', which=args.get('which', 'accessibility'))
        return dict(ok=True)
    if op == 'hands_install':
        built = install(force=bool(args.get('force')))
        start()
        return dict(status(), built=built)
    if op == 'hands_reset':
        # The owner's button: ORBIT Hands' own stale entries only, then the macOS prompt again.
        for service in ('Accessibility', 'ScreenCapture', 'PostEvent'):
            subprocess.run(['/usr/bin/tccutil', 'reset', service, BUNDLE_ID], capture_output=True)
        stop()
        start()
        call('request', which=args.get('which', 'accessibility'))
        return status()
    if op == 'hands_style':
        if args.get('name') not in STYLES:
            raise HandsError('Ismeretlen kurzorstílus.')
        call('style', name=args['name'])
        call('point', x=float(args.get('x', 900)), y=float(args.get('y', 500)))
        return status()
    if op == 'hands_test':
        call('show')
        return dict(ok=True)
    raise HandsError('Ismeretlen gépvezérlési beállítás.')
