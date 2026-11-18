"""Jarvis hands: the main assistant controls this Mac through macOS's own tools.

open (web pages, apps, files), pbcopy/pbpaste (clipboard), System Events (typing and shortcuts in the front app),
textutil (reading and writing .docx/.rtf/.txt/.md/.html documents) and screencapture. Nothing is installed.

Lines that stay with the owner, whatever the request says: no passwords, card or account numbers are typed; nothing
is typed into password managers, Keychain or System Settings; no purchase, payment, sending or publishing is
confirmed by a keystroke here (the assistant prepares, the owner presses the final button); no file is deleted.
Typing and shortcuts need the Accessibility permission for ORBIT in System Settings; without it the error says so.
"""
import json
import re
import subprocess
import time
from pathlib import Path

HOME = Path.home()
DOC_ROOTS = [HOME / 'Desktop', HOME / 'Documents', HOME / 'Downloads']
DOC_TYPES = {'.txt': 'txt', '.md': 'txt', '.rtf': 'rtf', '.docx': 'docx', '.doc': 'doc', '.html': 'html', '.odt': 'odt', '.rtfd': 'rtfd'}
PROTECTED_APPS = re.compile(r'keychain|kulcskarika|1password|bitwarden|lastpass|dashlane|system settings|rendszerbeállítások|system preferences|terminal|iterm', re.I)
SECRET = re.compile(r'\b(?:\d[ -]?){13,19}\b|\b[A-Z]{2}\d{2}[A-Z0-9 ]{11,30}\b|(?:password|jelszó|jelszo|passwd|pin)\s*[:=]', re.I)
KEYS = {'return': 36, 'enter': 36, 'tab': 48, 'space': 49, 'delete': 51, 'backspace': 51, 'escape': 53, 'esc': 53,
        'left': 123, 'right': 124, 'down': 125, 'up': 126, 'home': 115, 'end': 119, 'pageup': 116, 'pagedown': 121}
MODS = {'cmd': 'command down', 'command': 'command down', 'ctrl': 'control down', 'control': 'control down',
        'alt': 'option down', 'option': 'option down', 'shift': 'shift down'}
# Shortcuts that would quit, close, delete or send are not pressed by the assistant.
BLOCKED_SHORTCUTS = {'cmd+q', 'cmd+w', 'cmd+delete', 'cmd+backspace', 'cmd+shift+delete', 'cmd+option+escape', 'cmd+shift+q', 'cmd+enter', 'cmd+return', 'cmd+shift+d'}
OPS = ('open_url', 'open_app', 'open_file', 'clipboard_get', 'clipboard_set', 'type_text', 'key', 'copy', 'paste', 'select_all',
       'front', 'screenshot', 'doc_read', 'doc_write', 'reveal')


def _run(args, input_text=None, timeout=20):
    r = subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        err = (r.stderr or r.stdout).strip()
        if 'not allowed' in err or '1002' in err or '-1719' in err or 'assistive' in err.lower():
            raise ValueError('A gépeléshez és billentyűparancsokhoz engedély kell: Rendszerbeállítások → Adatvédelem és biztonság → Kisegítő lehetőségek → kapcsold be az ORBIT-ot (és a Python-t, ha listázza). Utána próbáld újra.')
        raise ValueError(err[:400] or 'A művelet nem sikerült.')
    return r.stdout


def _osa(script, timeout=20):
    return _run(['/usr/bin/osascript', '-e', script], timeout=timeout).strip()


def _quote(text):
    return '"' + str(text).replace('\\', '\\\\').replace('"', '\\"') + '"'


def front():
    """The app and window in front, so the assistant knows where it would type."""
    try:
        app = _osa('tell application "System Events" to get name of first application process whose frontmost is true')
    except ValueError:
        app = ''
    try:
        window = _osa('tell application "System Events" to tell (first application process whose frontmost is true) to get name of front window') if app else ''
    except ValueError:
        window = ''
    return dict(app=app, window=window)


def _guard_typing(text=''):
    current = front()
    if PROTECTED_APPS.search(current['app'] + ' ' + current['window']):
        raise ValueError('Ebbe az alkalmazásba (' + current['app'] + ') az ORBIT nem gépel és nem nyom billentyűt: jelszavak, kulcsok és rendszerbeállítások maradnak a tiéd.')
    if text and SECRET.search(text):
        raise ValueError('Jelszót, kártya- vagy számlaszámot az ORBIT nem gépel be; ezt tedd meg te.')
    return current


def doc_path(s, path, write=False):
    """Documents in the usual personal folders or in folders granted under Mappák."""
    p = Path(str(path or '')).expanduser().resolve()
    from commander import roots,schema
    schema(s)
    allowed = [r.resolve() for r in DOC_ROOTS] + [Path(r) for r in roots(s)]
    if not any(p == r or r in p.parents for r in allowed):
        raise ValueError('Ez a hely nincs engedélyezve. Dokumentumot az Asztalon, a Dokumentumokban, a Letöltésekben vagy a Mappák alatt megadott helyen kezelek.')
    if p.suffix.lower() not in DOC_TYPES:
        raise ValueError('Támogatott dokumentum: ' + ', '.join(sorted(DOC_TYPES)))
    if write and p.exists() and not p.is_file():
        raise ValueError('Ez nem fájl.')
    return p


def doc_read(s, path):
    p = doc_path(s, path)
    if not p.is_file():
        raise ValueError('Nincs ilyen dokumentum: ' + str(p))
    if p.suffix.lower() in ('.txt', '.md'):
        text = p.read_text(errors='replace')
    else:
        text = _run(['/usr/bin/textutil', '-convert', 'txt', '-stdout', str(p)], timeout=60)
    return dict(path=str(p), text=text[:60000], truncated=len(text) > 60000)


def doc_write(s, path, content, mode='replace'):
    """Writes text into a document; an existing file is kept as a .bak copy first. mode append adds to the end."""
    p = doc_path(s, path, write=True)
    if not isinstance(content, str) or len(content) > 400000:
        raise ValueError('A tartalom szöveg legyen (legfeljebb 400 000 karakter).')
    if mode == 'append' and p.exists():
        content = doc_read(s, p)['text'].rstrip('\n') + '\n\n' + content
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        backup = p.with_name(p.name + '.' + time.strftime('%Y%m%d-%H%M%S') + '.bak')
        backup.write_bytes(p.read_bytes())
    else:
        backup = None
    kind = DOC_TYPES[p.suffix.lower()]
    if kind == 'txt':
        p.write_text(content)
    else:
        import html
        import tempfile
        body = ''.join('<p>' + html.escape(line) + '</p>' if line.strip() else '<p><br></p>' for line in content.split('\n'))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'doc.html'
            source.write_text('<html><head><meta charset="utf-8"></head><body>' + body + '</body></html>')
            _run(['/usr/bin/textutil', '-convert', kind, '-output', str(p), str(source)], timeout=60)
    return dict(path=str(p), bytes=p.stat().st_size, backup=str(backup) if backup else None)


def press(combo):
    combo = re.sub(r'\s+', '', str(combo or '').lower())
    if combo in BLOCKED_SHORTCUTS:
        raise ValueError('Ezt a billentyűparancsot (' + combo + ') az ORBIT nem nyomja meg: bezárna, törölne vagy elküldene valamit. Ezt tedd meg te.')
    parts = combo.split('+')
    key, mods = parts[-1], [MODS[m] for m in parts[:-1] if m in MODS]
    if len(mods) != len(parts) - 1 or not key:
        raise ValueError('Ismeretlen billentyűparancs: ' + combo)
    using = (' using {' + ', '.join(mods) + '}') if mods else ''
    if key in KEYS:
        _osa('tell application "System Events" to key code ' + str(KEYS[key]) + using)
    elif len(key) == 1:
        _osa('tell application "System Events" to keystroke ' + _quote(key) + using)
    else:
        raise ValueError('Ismeretlen billentyű: ' + key)
    return dict(pressed=combo)


def opened(s, op, target):
    """Every app, page or file ORBIT opens is written down with who asked, so an unexpected window can be traced."""
    import inspect
    try:
        chain = ' < '.join(f'{Path(f.filename).stem}.{f.function}' for f in inspect.stack()[2:8] if 'orbit' in f.filename.lower() or 'Orbit' in f.filename)
        log = s.root / 'logs' / 'opened.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + '\t' + op + '\t' + str(target)[:300] + '\t' + chain + '\n')
    except Exception:   # a log never blocks the action
        pass


def run(s, op, args=None):
    args = args or {}
    if op not in OPS:
        raise ValueError('Ismeretlen gépvezérlési művelet: ' + str(op))
    if op in ('open_url', 'open_app', 'open_file', 'reveal'):
        opened(s, op, args.get('url') or args.get('name') or args.get('path'))
    if op == 'open_url':
        url = str(args.get('url') or '').strip()
        if not re.match(r'^https?://[^\s]+$', url):
            raise ValueError('Csak http(s) webcímet nyitok meg.')
        _run(['/usr/bin/open'] + (['-a', args['app']] if args.get('app') else []) + [url])
        return dict(opened=url)
    if op == 'open_app':
        name = str(args.get('name') or '').strip()
        if not name or PROTECTED_APPS.search(name) and 'terminal' not in name.lower():
            raise ValueError('Ezt az alkalmazást nem nyitom meg helyetted.')
        _run(['/usr/bin/open', '-a', name])
        return dict(opened=name)
    if op in ('open_file', 'reveal'):
        p = Path(str(args.get('path') or '')).expanduser()
        if not p.exists():
            raise ValueError('Nincs ilyen fájl vagy mappa: ' + str(p))
        _run(['/usr/bin/open'] + (['-R'] if op == 'reveal' else []) + [str(p)])
        return dict(opened=str(p))
    if op == 'clipboard_get':
        return dict(text=_run(['/usr/bin/pbpaste'])[:20000])
    if op == 'clipboard_set':
        text = str(args.get('text') or '')
        if SECRET.search(text):
            raise ValueError('Jelszót vagy kártyaszámot nem teszek a vágólapra.')
        _run(['/usr/bin/pbcopy'], input_text=text)
        return dict(copied=len(text))
    if op == 'front':
        return front()
    if op == 'screenshot':
        out = s.root / 'projects/universe/screenshots' / ('screen-' + time.strftime('%Y%m%d-%H%M%S') + '.png')
        out.parent.mkdir(parents=True, exist_ok=True)
        _run(['/usr/sbin/screencapture', '-x', str(out)])
        return dict(path=str(out))
    if op == 'doc_read':
        return doc_read(s, args.get('path'))
    if op == 'doc_write':
        return doc_write(s, args.get('path'), args.get('content'), args.get('mode', 'replace'))
    # Everything below acts in the front app, through ORBIT Hands (its own permission, the yarn cursor shows it).
    if op in ('type_text', 'key', 'copy', 'paste', 'select_all'):
        return _hands_act(s, op, args)
    if args.get('app'):
        _run(['/usr/bin/open', '-a', str(args['app'])])
        time.sleep(.8)
    if op == 'type_text':
        text = str(args.get('text') or '')
        if not text or len(text) > 20000:
            raise ValueError('1–20 000 karakteres szöveget adj meg.')
        where = _guard_typing(text)
        # Pasting is fast and keeps accents exactly; the clipboard is restored afterwards.
        try:
            old = _run(['/usr/bin/pbpaste'])
        except ValueError:
            old = None
        _run(['/usr/bin/pbcopy'], input_text=text)
        press('cmd+v')
        time.sleep(.3)
        if old is not None:
            _run(['/usr/bin/pbcopy'], input_text=old)
        return dict(typed=len(text), app=where['app'])
    _guard_typing()
    if op == 'key':
        return press(args.get('combo'))
    if op == 'copy':
        press('cmd+c')
        time.sleep(.3)
        return dict(text=_run(['/usr/bin/pbpaste'])[:20000])
    if op == 'paste':
        return press('cmd+v')
    if op == 'select_all':
        return press('cmd+a')


def state(s):
    """For the planner's read: what is in front and on the clipboard now."""
    out = front()
    try:
        out['clipboard'] = _run(['/usr/bin/pbpaste'])[:2000]
    except ValueError:
        out['clipboard'] = ''
    try:
        out['running_apps'] = [a.strip() for a in _osa('tell application "System Events" to get name of every application process whose background only is false').split(',')][:30]
    except ValueError:
        out['running_apps'] = []
    out['document_folders'] = [str(p) for p in DOC_ROOTS]
    return out


def _hands_act(s, op, args):
    import hands
    if args.get('app'):
        _run(['/usr/bin/open', '-a', str(args['app'])])
        time.sleep(.8)
    if op == 'type_text':
        text = str(args.get('text') or '')
        if not text or len(text) > 20000:
            raise ValueError('1–20 000 karakteres szöveget adj meg.')
        where = _guard_typing(text)
        hands.call('type', text=text, timeout=120)
        return dict(typed=len(text), app=where['app'])
    _guard_typing()
    if op == 'key':
        combo = re.sub(r'\s+', '', str(args.get('combo') or '').lower())
        if combo in BLOCKED_SHORTCUTS:
            raise ValueError('Ezt a billentyűparancsot (' + combo + ') az ORBIT nem nyomja meg: bezárna, törölne vagy elküldene valamit. Ezt tedd meg te.')
        hands.call('key', combo=combo)
        return dict(pressed=combo)
    if op == 'copy':
        hands.call('key', combo='cmd+c')
        time.sleep(.3)
        return dict(text=_run(['/usr/bin/pbpaste'])[:20000])
    hands.call('key', combo='cmd+v' if op == 'paste' else 'cmd+a')
    return dict(ok=True)
