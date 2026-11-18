"""Szimgyár project app: the owner's preferences and video types for Kobold's ported simulation factory.

Settings live in the project folder (szimgyar_settings.json); the engine (szim_run.py in the media runtime) reads them when it
picks a recipe variant. Production runs as a no-model assist job; ratings (approved / rejected + note) are stored in the video's
record and are what the recipe learner and the designer agents learn from.
"""
import json
import subprocess
import time
from pathlib import Path

NAME = 'Szimgyár'
DEFAULTS = dict(recipes={}, palettes=[], seconds_min=25, seconds_max=45, batch=1)   # sound is not a setting: always the viral top
_catalog = {}


def project(s):
    row = s.db.execute('SELECT id FROM projects WHERE name=?', (NAME,)).fetchone()
    if not row:
        raise ValueError('Nincs Szimgyár projekt.')
    return row[0]


def base(s, pid):
    return s.root / 'projects' / pid


def runtime(s):
    return str(s.root / 'media-runtime/bin/python3')


def catalog(s):
    if not _catalog:
        run = subprocess.run([runtime(s), '-I', str(Path(__file__).with_name('szim_run.py')), 'catalog'], capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise ValueError('A Szimgyár motor nem indul: ' + (run.stderr or run.stdout)[-300:])
        _catalog.update(json.loads(run.stdout))
    return _catalog


def settings(s, pid):
    try:
        saved = json.loads((base(s, pid) / 'szimgyar_settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def save_settings(s, pid, patch):
    cat, cur = catalog(s), settings(s, pid)
    new = dict(cur)
    for key, allowed in (('palettes', cat['palettes']),):
        if key in patch:
            new[key] = [x for x in patch[key] if x in allowed][:40]
    if isinstance(patch.get('recipes'), dict):
        ids = {r['azon'] for r in cat['recipes']}
        new['recipes'] = {k: bool(v) for k, v in patch['recipes'].items() if k in ids}
        if not any(new['recipes'].get(i, True) for i in ids):
            raise ValueError('Legalább egy videótípusnak bekapcsolva kell maradnia.')
    for key, lo, hi in (('seconds_min', 15, 60), ('seconds_max', 15, 70), ('batch', 1, 10)):
        if key in patch:
            new[key] = max(lo, min(hi, int(patch[key])))
    if new['seconds_max'] < new['seconds_min']:
        raise ValueError('A maximális hossz nem lehet rövidebb a minimálisnál.')
    (base(s, pid) / 'szimgyar_settings.json').write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding='utf-8')
    return dict(message='A preferenciák elmentve.', settings=new)


def videos(s, pid):
    out = []
    for path in sorted((base(s, pid) / 'simulations').glob('*.json'), key=lambda p: -p.stat().st_mtime):
        try:
            rec = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        szim = rec.get('szim') if isinstance(rec, dict) else None
        if not szim or not rec.get('artifact'):
            continue
        m = szim.get('meres') or {}
        out.append(dict(id=path.stem, artifact=rec['artifact'], title=rec.get('cim') or path.stem, state=rec.get('allapot') or 'kesz', note=rec.get('megjegyzes') or '',
                        recipe=(szim['spec'] or {}).get('recept') or '', seconds=m.get('hossz'), balls=m.get('labdak_max'), quality=(m.get('minoseg') or {}).get('pont'),
                        created=rec.get('letrehozva') or path.stat().st_mtime))
    return out[:80]


def snapshot(s, pid=None):
    pid = pid or project(s)
    cat, cfg, vids = catalog(s), settings(s, pid), videos(s, pid)
    stats = {}
    for v in vids:
        e = stats.setdefault(v['recipe'], dict(made=0, approved=0, rejected=0))
        e['made'] += 1
        e['approved'] += v['state'] == 'jovahagyva'
        e['rejected'] += v['state'] == 'elvetve'
    busy = s.rows("SELECT id,status,prompt FROM jobs WHERE project=? AND kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='szim_make'", (pid,))
    return dict(settings=cfg, catalog=cat, videos=vids, stats=stats, busy=[dict(id=j['id'], status=j['status'], label=j['prompt']) for j in busy], project=pid)


def make(s, pid, args):
    cat = catalog(s)
    recipe = str(args.get('recipe') or '')
    if recipe and recipe not in {r['azon'] for r in cat['recipes']}:
        raise ValueError('Ismeretlen videótípus.')
    count = max(1, min(10, int(args.get('count') or settings(s, pid)['batch'])))
    agent = s.db.execute('SELECT id FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid LIMIT 1', (pid,)).fetchone()
    if not agent:
        raise ValueError('A Szimgyár projektben nincs ügynök, aminek a nevén a gyártás futhat.')
    label = f'Szimgyár: {count} videó' + (f' ({recipe})' if recipe else '')
    s.enqueue(agent[0], label, 'assist', payload=dict(task='szim_make', local_only=True, recipe=recipe, count=count, topic=str(args.get('topic') or '')[:200]))
    return dict(message=f'Sorba állt: {count} videó. Néhány perc egy videó, a Videók oldalon jelenik meg.')


def ideas(s, pid, args):
    """The agent chain (idea -> design -> critic -> simulator) for a free, new idea; needs the local model."""
    rows = s.rows('SELECT id,tools FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid', (pid,))
    start = next((r['id'] for r in rows if 'web_search' in r['tools']), rows[0]['id'] if rows else None)
    if not start:
        raise ValueError('A Szimgyár projektben nincs ügynök.')
    topic = str(args.get('topic') or '').strip()[:300] or 'a mai legfelkapottabb szimulációs videók'
    s.enqueue_graph(pid, start, 'Szimgyár: 1 videó, téma: ' + topic)
    return dict(message='Az ügynökláncot elindítottam (ötlet, terv, bírálat, szimuláció). A helyi modell dolgozik, ez hosszabb.')


def rate(s, pid, args):
    vid = str(args.get('id') or '')
    if not vid.isalnum() and not all(c.isalnum() or c in '-_' for c in vid):
        raise ValueError('Ismeretlen videó.')
    state = args.get('state')
    if state not in ('jovahagyva', 'elvetve', 'kesz'):
        raise ValueError('Ismeretlen állapot.')
    path = base(s, pid) / 'simulations' / (vid + '.json')
    if not path.is_file():
        raise ValueError('Ismeretlen videó.')
    rec = json.loads(path.read_text(encoding='utf-8'))
    rec['allapot'], rec['megjegyzes'], rec['dontes_ido'] = state, str(args.get('note') or '')[:600], time.time()
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding='utf-8')
    return dict(message={'jovahagyva': 'Jóváhagyva: a következő videók ebből tanulnak.', 'elvetve': 'Elvetve: a rendszer kerüli ezt a kombinációt.', 'kesz': 'Visszaállítva.'}[state])


def dispatch(s, op, args=None):
    args = args or {}
    pid = project(s)
    if op == 'szim_snapshot':
        return snapshot(s, pid)
    if op == 'szim_save':
        return save_settings(s, pid, args.get('settings') or {})
    if op == 'szim_make':
        return make(s, pid, args)
    if op == 'szim_ideas':
        return ideas(s, pid, args)
    if op == 'szim_rate':
        return rate(s, pid, args)
    raise ValueError('Ismeretlen Szimgyár-művelet.')


def run_job(s, job):
    """Assist job (no model): picks a recipe variant that follows the preferences and renders it, count times."""
    from sim_tools import run_simulation
    payload = json.loads(job['payload'])
    pid = job['project']
    agent = dict(id=job['agent'], project=pid, tools=['render_simulation'])
    done = []
    for _ in range(int(payload.get('count') or 1)):
        if s.cancelled(job['id']):
            break
        args = dict(recipe=payload.get('recipe') or True, topic=payload.get('topic') or '')
        for _try in range(5):   # the quality gate runs before rendering: a weak variant is cheap to replace
            try:
                done.append(run_simulation(s, agent, args, job['id']).get('saved'))
                break
            except ValueError as error:
                if not str(error).startswith('QUALITY_GATE'):
                    raise
    return f'Szimgyár: {len(done)} videó elkészült.'
