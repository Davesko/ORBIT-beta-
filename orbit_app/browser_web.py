"""Web search and page reading through the Mac's own Chrome, for when no search API or key is available.

Chrome runs headless with a throwaway profile: no window opens, the mouse and the owner's tabs, cookies and accounts
are never touched. A robot check or consent wall is reported as "no result" and never worked around."""
import base64
import html
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

BROWSERS = ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser')
WALL = re.compile(r'captcha|unusual traffic|are you a robot|verify you are human|anomaly detected', re.I)
LIMIT = 3_000_000


def browser():
    return next((path for path in BROWSERS if Path(path).is_file()), None)


def dump(url, seconds=30, run=None):
    """The rendered HTML of a public page, or '' when no browser is installed or it gave nothing in time."""
    from public_web import valid_url
    url = valid_url(url)
    path = browser()
    if not path and run is None:
        return ''
    profile = tempfile.mkdtemp(prefix='orbit-browser-')
    try:
        command = [path or 'chrome', '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
                   '--user-data-dir=' + profile, '--virtual-time-budget=6000', '--dump-dom', url]
        done = (run or subprocess.run)(command, capture_output=True, timeout=seconds)
        return done.stdout[:LIMIT].decode(errors='replace') if done.returncode == 0 else ''
    except (subprocess.TimeoutExpired, OSError):
        return ''
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def text_of(fragment):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', fragment)).split())


def target(link):
    """Bing wraps results in a redirect that carries the real address base64-encoded in u=a1…"""
    link = html.unescape(link)
    wrapped = re.search(r'[?&]u=a1([A-Za-z0-9_-]+)', link)
    if 'bing.com/ck/' in link and wrapped:
        raw = wrapped.group(1)
        try:
            link = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode()
        except (ValueError, UnicodeDecodeError):
            return None
    parts = urllib.parse.urlsplit(link)
    return link if parts.scheme in ('http', 'https') and parts.hostname and not parts.hostname.endswith('bing.com') else None


def parse(page, limit=8):
    if WALL.search(page[:200000]) and '<li class="b_algo"' not in page:
        return []
    results = []
    for block in re.findall(r'<li class="b_algo".*?</li>', page, re.S):
        head = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        link = target(head.group(1)) if head else None
        if not link or any(r['url'] == link for r in results):
            continue
        body = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        results.append(dict(title=text_of(head.group(2))[:300], url=link, description=text_of(body.group(1))[:1500] if body else ''))
        if len(results) >= limit:
            break
    return results


def search(query, limit=8, run=None):
    if not isinstance(query, str) or not 2 <= len(query) <= 300:
        raise ValueError('2–300 karakteres keresési kérés szükséges.')
    return parse(dump('https://www.bing.com/search?q=' + urllib.parse.quote(query), run=run), limit)


def read(url, run=None):
    """Visible text of a page that needs JavaScript to render."""
    page = dump(url, run=run)
    if not page or WALL.search(page[:200000]):
        return dict(url=url, text='')
    body = re.sub(r'<(script|style|noscript|svg)\b.*?</\1>', ' ', page, flags=re.S | re.I)
    return dict(url=url, text=text_of(body)[:18000])
