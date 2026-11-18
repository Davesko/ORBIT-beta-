"""Skill libraries from the web: public collections of SKILL.md work methods, matched to the owner's projects.

ORBIT reads the libraries as text (git clone, read only): nothing in them is run, scripts and code stay on disk unread.
A library skill becomes an ORBIT work method (steps + checks) when it fits a project. From the two vetted default
libraries a close fit is adopted as usable; anything else, and every skill from a library the owner adds, waits as a
draft on the Skillek page. Third-party text is data: the owner sees where every method came from.
"""
import json
import re
import subprocess
import time
from pathlib import Path

SOURCES = [
    dict(repo='anthropics/skills', title='Anthropic Agent Skills', license='Apache-2.0', trusted=True),
    dict(repo='obra/superpowers', title='Superpowers munkamódszerek', license='MIT', trusted=True),
]
REFRESH = 7 * 86400
FIT = .36            # the description must share this much meaning with a project to count as a fit
USABLE = .6         # a vetted skill this close to a project is adopted as usable, below it as a draft
PER_RUN = 3
# Project texts are often Hungarian while library skills are English: a few domain words are bridged both ways.
BRIDGE = {
    'video': 'video', 'videó': 'video', 'short': 'video', 'animáció': 'animation art', 'animacio': 'animation art', 'rajz': 'art drawing design',
    'kép': 'image design visual', 'kep': 'image design visual', 'grafika': 'design visual art', 'design': 'design', 'márka': 'brand',
    'marka': 'brand', 'arculat': 'brand design', 'logó': 'brand logo', 'webshop': 'web frontend shop', 'weboldal': 'web frontend page',
    'oldal': 'web page', 'honlap': 'web page frontend', 'terv': 'plan planning', 'tervez': 'plan design', 'ötlet': 'brainstorm idea',
    'otlet': 'brainstorm idea', 'hiba': 'debug bug', 'javít': 'debug fix', 'javit': 'debug fix', 'ellenőr': 'verify review check',
    'ellenor': 'verify review check', 'teszt': 'test testing', 'szöveg': 'writing document', 'szoveg': 'writing document', 'cikk': 'writing article',
    'dokumentum': 'document docx', 'pdf': 'pdf document', 'prezentáció': 'slides presentation pptx', 'táblázat': 'spreadsheet xlsx',
    'tablazat': 'spreadsheet xlsx', 'kutat': 'research', 'elemz': 'analysis analyze', 'kód': 'code', 'kod': 'code', 'fejleszt': 'development code',
    'app': 'app web', 'játék': 'game web interactive', 'jatek': 'game web interactive', 'etsy': 'shop product listing design', 'termék': 'product',
    'termek': 'product', 'színező': 'coloring art drawing', 'szinezo': 'coloring art drawing', 'poszter': 'poster design visual', 'zene': 'music audio',
    'hang': 'audio sound', 'kommunikáció': 'communication writing', 'levél': 'email writing communication', 'csatorna': 'channel content',
}


# What a known library skill is good for, as words a project of that kind uses (Hungarian and English).
DOMAINS = {
    'brainstorming': r'otlet|idea|hook|kreativ|tema|forgatokonyv|script|story|tortenet|koncepc',
    'writing-plans': r'terv|plan|lepes|pipeline|lanc|munkafolyamat|workflow',
    'executing-plans': r'terv|plan|lepes|pipeline|lanc|munkafolyamat|workflow',
    'verification-before-completion': r'ellenor|verif|minoseg|quality|biral|review|hiba',
    'systematic-debugging': r'hiba|debug|javit|elakad|fail|error|stabil',
    'canvas-design': r'poszter|poster|grafika|design|kep|image|thumbnail|boritokep|vizual|illusztr',
    'algorithmic-art': r'generativ|animac|szimulac|fizika|particle|minta|pattern|art',
    'theme-factory': r'szin|paletta|tema|stilus|style|arculat',
    'brand-guidelines': r'marka|brand|arculat|logo|csatorna|channel',
    'frontend-design': r'weboldal|webshop|honlap|landing|frontend|ui\b|felulet',
    'web-artifacts-builder': r'weboldal|webshop|honlap|landing|app\b|jatek|interaktiv',
    'webapp-testing': r'weboldal|webshop|honlap|webapp|teszt',
    'doc-coauthoring': r'dokumentum|cikk|jelentes|riport|leiras|szoveg',
    'pdf': r'\\bpdf|szamla|invoice',
    'xlsx': r'tablazat|excel|xlsx|szamla|kimutat|penzugy',
    'docx': r'\\bword\\b|docx|szerzodes',
    'pptx': r'prezent|\\bdiak?\\b|slide|pptx',
    'slack-gif-creator': r'gif|animac|meme|rovid video|loop',
    'internal-comms': r'level|email|kommunikac|hirlevel',
}
GENERAL = ('verification-before-completion', 'brainstorming', 'writing-plans', 'systematic-debugging')


def schema(s):
    s.db.executescript('''CREATE TABLE IF NOT EXISTS skill_library(id TEXT PRIMARY KEY,source TEXT,name TEXT,description TEXT,body TEXT,url TEXT,
        license TEXT,scripts INTEGER,updated REAL);
        CREATE TABLE IF NOT EXISTS skill_library_settings(key TEXT PRIMARY KEY,value TEXT);''')
    s.db.commit()


def setting(s, key, default=None):
    schema(s)
    row = s.db.execute('SELECT value FROM skill_library_settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(s, key, value):
    schema(s)
    s.db.execute('INSERT OR REPLACE INTO skill_library_settings VALUES(?,?)', (key, json.dumps(value, ensure_ascii=False)))
    s.db.commit()


def sources(s):
    return SOURCES + [dict(x, trusted=False) for x in setting(s, 'extra_sources', [])]


def add_source(s, url):
    m = re.fullmatch(r'\s*(?:https://github\.com/)?([A-Za-z0-9_.-]{1,60})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?/?\s*', str(url or ''))
    if not m:
        raise ValueError('Egy nyilvános GitHub-repót adj meg, például https://github.com/anthropics/skills')
    repo = m.group(1) + '/' + m.group(2)
    extra = [x for x in setting(s, 'extra_sources', []) if x['repo'] != repo]
    if any(x['repo'] == repo for x in SOURCES):
        return dict(repo=repo, note='Ez a könyvtár már benne van.')
    extra.append(dict(repo=repo, title=repo, license='?'))
    set_setting(s, 'extra_sources', extra)
    got = refresh(s, only=repo)
    return dict(repo=repo, skills=got.get(repo, 0), note=f'Hozzáadva: {repo} · {got.get(repo, 0)} skill. Az innen átvettek piszkozatként várnak.')


def folder(s, repo):
    return s.root / 'skill-library' / repo.replace('/', '__')


def fetch(s, repo, run=subprocess.run):
    """A shallow clone (or pull) of a public GitHub repository; only its text is read afterwards."""
    path = folder(s, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(GIT_TERMINAL_PROMPT='0', PATH='/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin')
    if (path / '.git').is_dir():
        done = run(['git', '-C', str(path), 'pull', '--ff-only', '-q'], capture_output=True, text=True, timeout=180, env=env)
    else:
        done = run(['git', 'clone', '-q', '--depth', '1', 'https://github.com/' + repo + '.git', str(path)], capture_output=True, text=True, timeout=300, env=env)
    if done.returncode and not (path / '.git').is_dir():
        raise ValueError('A könyvtár nem tölthető le: ' + repo + ' (' + (done.stderr or '')[-200:] + ')')
    return path


def parse(text):
    """SKILL.md: YAML-like front matter (name, description) and a markdown body."""
    meta, body = {}, text
    m = re.match(r'\s*---\s*\n(.*?)\n---\s*\n(.*)', text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            kv = re.match(r'\s*([A-Za-z_-]+)\s*:\s*(.*)', line)
            if kv:
                meta[kv.group(1).lower()] = kv.group(2).strip().strip('"\'')
    return meta, body


def refresh(s, only=None, run=subprocess.run):
    schema(s)
    counts = {}
    for src in sources(s):
        if only and src['repo'] != only:
            continue
        try:
            path = fetch(s, src['repo'], run=run)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            counts[src['repo']] = 0
            set_setting(s, 'error:' + src['repo'], str(error)[:300])
            continue
        n = 0
        for md in sorted(path.rglob('SKILL.md'))[:400]:
            if any(part.startswith('.') or part in ('template', 'node_modules') for part in md.relative_to(path).parts):
                continue
            try:
                meta, body = parse(md.read_text(encoding='utf-8', errors='replace')[:60000])
            except OSError:
                continue
            name = meta.get('name') or md.parent.name
            if not meta.get('description'):
                continue
            rel = md.parent.relative_to(path)
            lic = next((p for p in (md.parent / 'LICENSE.txt', md.parent / 'LICENSE', path / 'LICENSE') if p.is_file()), None)
            scripts = sum(1 for p in md.parent.rglob('*') if p.suffix in ('.py', '.js', '.sh', '.ts'))
            sid = (src['repo'] + '/' + str(rel)).lower()
            s.db.execute('INSERT OR REPLACE INTO skill_library VALUES(?,?,?,?,?,?,?,?,?)',
                         (sid, src['repo'], name[:80], meta['description'][:1000], body[:40000], f'https://github.com/{src["repo"]}/tree/HEAD/{rel}',
                          meta.get('license') or (lic.read_text(errors='replace')[:80].split('\n')[0] if lic else src.get('license', '?')), scripts, time.time()))
            n += 1
        counts[src['repo']] = n
        s.db.commit()
    set_setting(s, 'refreshed', time.time())
    return counts


def _words(text):
    from assistant_skills import words
    from model_router import normalized
    t = normalized(text)
    extra = ' '.join(v for k, v in BRIDGE.items() if normalized(k) in t)
    return words(text + ' ' + extra)


def project_texts(s):
    """What each of the owner's projects is about: its name, description and its agents' roles and briefs."""
    from autopilot_hub import user_projects
    out = {}
    active = user_projects(s)
    others = [r['id'] for r in s.rows("SELECT id FROM projects WHERE id NOT IN ('orbit','universe','orbit-business-lab') AND id NOT LIKE 'venture-%' ORDER BY created DESC")]
    trashed = {r[0] for r in s.db.execute("SELECT name FROM sqlite_master WHERE name='project_trash'").fetchall()}
    if trashed:
        gone = {r[0] for r in s.db.execute('SELECT * FROM project_trash').fetchall()}
        others = [x for x in others if x not in gone]
    for pid in list(dict.fromkeys(active + others))[:30]:
        p = s.db.execute('SELECT name,description FROM projects WHERE id=?', (pid,)).fetchone()
        if not p:
            continue
        agents = s.rows('SELECT name,role,prompt FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) LIMIT 16', (pid,))
        out[pid] = dict(name=p['name'], text=' '.join([p['name'], p['description'] or ''] + [a['name'] + ' ' + a['role'] + ' ' + (a['prompt'] or '')[:400] for a in agents]))
    return out


def adopted(s):
    import assistant_skills
    return {d.get('library', {}).get('id') for d in assistant_skills.listing(s) if d.get('library')}


def matches(s, limit=12):
    """Library skills whose description is covered by a project's own words, weighted by how rare each word is in the
    library ("use", "when", "claude" count for little, "brand", "animation", "debug" for much)."""
    import math
    schema(s)
    from model_router import normalized
    texts = project_texts(s)
    projects = {pid: (v['name'], set(_words(v['text']))) for pid, v in texts.items()}
    plain = {pid: normalized(v['text']) for pid, v in texts.items()}
    have = adopted(s)
    rows = s.rows('SELECT id,source,name,description,url,license,scripts FROM skill_library')
    docs = {r['id']: set(_words(r['name'].replace('-', ' ') + ' ' + r['description'])) for r in rows}
    df = {}
    for ws in docs.values():
        for w in ws:
            df[w] = df.get(w, 0) + 1
    n = max(1, len(docs))
    idf = {w: math.log((n + 1) / (c + .5)) for w, c in df.items()}
    found = []
    for r in rows:
        skill = docs[r['id']]
        total = sum(idf[w] for w in skill) or 1
        domain = DOMAINS.get(r['name'])
        def fit(pid, words):
            hit = bool(domain and re.search(domain, plain[pid]))
            return sum(idf[w] for w in skill & words) / total * (1.6 if hit else .7) + (.35 if hit else 0)
        best = max(((fit(pid, words), pid, name) for pid, (name, words) in projects.items()), default=(0, None, None))
        if best[0] >= FIT:
            found.append(dict(r, score=round(best[0], 3), project=best[1], project_name=best[2], adopted=r['id'] in have))
    found.sort(key=lambda x: -x['score'])
    return found[:limit]


PROCESS = re.compile(r'process|step|workflow|how to|checklist|phase|the (?:iron )?law|procedure|method|approach|instructions|guidelines|rules|core|overview', re.I)
CHECK = re.compile(r'verif|check|test|review|quality|red flags|common mistakes|before (?:you )?(?:finish|claim)|pitfall', re.I)
NOISE = re.compile(r'^(?:"|\'|e\.g\.|example|bad:|good:|❌|✅|<|\|)', re.I)


def to_method(row, project_name=None):
    """A SKILL.md body → ORBIT steps and checks (at most 12 each): numbered items of the process sections first, then
    their bullets; checks from verification / red-flag sections. Code blocks and examples are left out."""
    body = re.sub(r'```.*?```', ' ', row['body'], flags=re.S)
    # A list item wrapped over several lines is one item.
    body = re.sub(r'\n[ \t]+(?![-*]\s|\d+[.)]\s)(?=\S)', ' ', body)
    sections, head = [], ''
    for line in body.splitlines():
        h = re.match(r'\s*#{1,4}\s+(.*)', line)
        if h:
            head = h.group(1).strip()
            continue
        item = re.match(r'\s*(\d+[.)]|[-*])\s+(.{15,})', line)
        if item:
            text = re.sub(r'\*\*|__|`', '', item.group(2)).strip()
            if not NOISE.search(text):
                sections.append((head, item.group(1)[0].isdigit(), text[:600]))
    def rank(x):
        head, numbered, _ = x
        return (0 if PROCESS.search(head) else 1, 0 if numbered else 1)
    steps, checks, seen = [], [], set()
    for head, numbered, text in sorted(sections, key=rank):
        if text in seen:
            continue
        seen.add(text)
        if CHECK.search(head) and len(checks) < 12:
            checks.append(text)
        elif len(steps) < 12 and not CHECK.search(head):
            steps.append(text)
    if len(steps) < 2:
        steps += [x.strip()[:600] for x in re.split(r'\n\s*\n', body) if len(x.strip()) > 60 and not x.strip().startswith('#')][:6 - len(steps)]
    steps = steps[:12] or [row['description'][:600]]
    if not checks:
        checks = ['Az eredmény teljesíti a forrás-skill célját: ' + row['description'][:400]]
    title = re.sub(r'[-_]+', ' ', row['name']).strip().capitalize()
    return dict(id='lib-' + re.sub(r'[^a-z0-9]+', '-', row['id'])[-70:].strip('-'), title=title[:100],
                description=(row['description'][:420] + (' · Projekt: ' + project_name if project_name else ''))[:500],
                steps=steps, verification=checks[:12], tags=[t for t in re.split(r'[-_ ]+', row['name'].lower()) if len(t) > 2][:6] + (['projekt:' + project_name[:40]] if project_name else []))


def adopt(s, lib_id, project=None, usable=False):
    import assistant_skills
    schema(s)
    row = s.db.execute('SELECT * FROM skill_library WHERE id=?', (lib_id,)).fetchone()
    if not row:
        raise ValueError('Nincs ilyen skill a könyvtárban.')
    name = s.db.execute('SELECT name FROM projects WHERE id=?', (project,)).fetchone() if project else None
    data = to_method(dict(row), name[0] if name else None)
    data['status'] = 'published' if usable else 'draft'
    d = assistant_skills.validate(data)
    d.update(source='library', library=dict(id=row['id'], repo=row['source'], url=row['url'], license=row['license'], scripts_not_run=row['scripts']))
    saved = assistant_skills.store(s, d)
    return dict(saved, title=d['title'], status=d['status'], url=row['url'])


def scout(s, now=None):
    """One Autopilot step for "learn skills that help my projects": refresh the libraries weekly, adopt the best
    fits not taken yet, and note in each project what was learned. Needs no model."""
    import autopilot_hub
    now = now or time.time()
    if now - (setting(s, 'refreshed', 0) or 0) > REFRESH or not s.db.execute('SELECT 1 FROM skill_library LIMIT 1').fetchone():
        refresh(s)
    trusted = {x['repo'] for x in sources(s) if x.get('trusted')}
    picked = [m for m in matches(s, 40) if not m['adopted']][:PER_RUN]
    done = []
    for m in picked:
        usable = m['source'] in trusted and m['score'] >= USABLE
        got = adopt(s, m['id'], m['project'], usable=usable)
        autopilot_hub.note(s, m['project'], 'Skill tanulva' if usable else 'Skill-javaslat',
                           f'{got["title"]} ({m["source"]}) · ' + ('használható' if usable else 'piszkozat, jóváhagyásra vár'))
        done.append(f'„{got["title"]}” → {m["project_name"]}' + ('' if usable else ' (piszkozat)'))
    if not done:
        return 'A skillkönyvtárakban most nem volt új, a projektjeidhez illő skill.'
    return 'Új skillek a projektjeidhez: ' + '; '.join(done) + '.'


def overview(s):
    schema(s)
    counts = {r['source']: r['n'] for r in s.rows('SELECT source,count(*) n FROM skill_library GROUP BY source')}
    return dict(sources=[dict(x, skills=counts.get(x['repo'], 0), error=setting(s, 'error:' + x['repo'])) for x in sources(s)],
                refreshed=setting(s, 'refreshed'), matches=matches(s, 12))


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'skilllib_overview':
        return overview(s)
    if op == 'skilllib_refresh':
        return dict(counts=refresh(s), **overview(s))
    if op == 'skilllib_add':
        return add_source(s, args.get('url'))
    if op == 'skilllib_adopt':
        return adopt(s, args.get('id'), args.get('project'), usable=False)
    if op == 'skilllib_scout':
        return dict(note=scout(s))
    raise ValueError('Ismeretlen skillkönyvtár-művelet.')
