"""render_simulation: an agent's simulation plan → a real 1080x1920 MP4 in the project (ORBIT's own sim_short engine)."""
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

ENGINE = Path(__file__).with_name('sim_short.py')
RUNNER = Path(__file__).with_name('szim_run.py')   # Kobold's Szimgyár engine, ported (szim_engine / szim_recipes)


def run_simulation(studio, agent, args, job):
    if 'render_simulation' not in agent['tools']:
        raise ValueError('Az ügynökön nincs engedélyezve a szimulációs render.')
    pid = agent['project']
    runtime = studio.root / 'media-runtime/bin/python3'
    if args.get('guide'):
        done = subprocess.run([str(runtime), '-I', str(RUNNER), 'knowledge', str(studio.root / 'projects' / pid)], capture_output=True, text=True, timeout=120)
        return dict(guide=done.stdout[-12000:] or done.stderr[-400:])
    if args.get('recipe'):
        done = subprocess.run([str(runtime), '-I', str(RUNNER), 'recipe', str(studio.root / 'projects' / pid), str(args.get('topic') or '')] + ([args['recipe']] if isinstance(args.get('recipe'), str) and args['recipe'] != 'true' else []),
                              capture_output=True, text=True, timeout=300)
        if done.returncode:
            raise ValueError('A recept-választás nem sikerült: ' + (done.stderr or done.stdout)[-400:])
        plan = json.loads(done.stdout.strip().splitlines()[-1])
        if not plan.get('spec'):
            return dict(experiment=True, note='A tanult döntés szabad kísérlet: írj új specet a guide építőelemeiből, és add meg a spec mezőben.')
        args = dict(args, spec=plan['spec'], recipe_note=plan.get('miert'))
    spec = args.get('spec')
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            spec = None
    if not isinstance(spec, dict) and args.get('plan'):
        path = studio.safe_path(pid, args['plan'])
        if not path.is_file() or path.stat().st_size > 200000:
            raise ValueError('A szimulációs tervfájl nem található (project_files listázza).')
        spec = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(spec, dict):
        raise ValueError('Adj meg egy szimulációs tervet: spec (JSON objektum) vagy plan (projektbeli JSON-fájl).')
    if studio.cancelled(job):
        raise ValueError('A feladat leállítva.')
    base = studio.root / 'projects' / pid / 'simulations'
    base.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '-', str(spec.get('title') or 'simulation').lower()).strip('-')[:40] or 'simulation'
    stem = f'{slug}-{uuid.uuid4().hex[:6]}'
    spec_path, out = base / (stem + '.json'), base / (stem + '.mp4')
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding='utf-8')
    started = time.time()
    if 'palya' in spec or 'szabalyok' in spec:   # Kobold's SPEC (palya / labdak / szabalyok): the ported Szimgyár engine
        done = subprocess.run([str(runtime), '-I', str(RUNNER), 'render', str(spec_path), str(out), str(base / ('work-' + stem))] + (['--strict'] if args.get('recipe') else []),
                              capture_output=True, text=True, timeout=2400)
        if done.returncode == 3:
            spec_path.unlink(missing_ok=True)
            raise ValueError('QUALITY_GATE: ' + done.stderr[-300:])
        if done.returncode or not out.is_file():
            raise ValueError('A szimuláció renderelése nem sikerült: ' + (done.stderr or done.stdout)[-500:])
        result = json.loads(done.stdout.strip().splitlines()[-1])
        meres = result['meres']
        record = dict(id=stem, cim=result['spec'].get('cim') or spec.get('cim') or slug, allapot='kesz', letrehozva=time.time(),
                      szim=dict(spec=result['spec'], mag=result['mag'], meres=meres), video=out.name)
        spec_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
        aid = uuid.uuid4().hex
        studio.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)', (aid, pid, out.name, str(out), 'video', time.time(), job))
        studio.db.commit()
        record['artifact'] = aid
        spec_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
        gate = meres.get('minoseg') or {}
        return dict(saved=str(out.relative_to(studio.root / 'projects' / pid)), seconds=meres.get('hossz'), ending=meres.get('vege_ido'),
                    balls=meres.get('labdak_max'), question=result['spec'].get('kerdes'), quality=gate.get('pont'), quality_ok=gate.get('jo'),
                    quality_problems=gate.get('hibak'), recipe=args.get('recipe_note') or result['spec'].get('recept'),
                    render_seconds=round(time.time() - started))
    done = subprocess.run([str(runtime), '-I', str(ENGINE), str(spec_path), str(out)], capture_output=True, text=True, timeout=1200)
    if done.returncode or not out.is_file():
        raise ValueError('A szimuláció renderelése nem sikerült: ' + (done.stderr or done.stdout)[-400:])
    result = json.loads(done.stdout.strip().splitlines()[-1])
    spec_path.write_text(json.dumps(result['spec'], ensure_ascii=False, indent=1), encoding='utf-8')
    studio.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)', (uuid.uuid4().hex, pid, out.name, str(out), 'video', time.time(), job))
    studio.db.commit()
    return dict(saved=str(out.relative_to(studio.root / 'projects' / pid)), seconds=result['seconds'], ending=result['ending'],
                balls=result['balls'], question=result['spec']['question'], render_seconds=round(time.time() - started))


def plan_from(content, prompt):
    """The simulation plan in an agent's reply (a JSON object), else the task's own words for the engine to read."""
    text = str(content or '')
    for start in [i for i, c in enumerate(text) if c == '{'][:20]:
        depth = 0
        for end in range(start, len(text)):
            depth += {'{': 1, '}': -1}.get(text[end], 0)
            if depth == 0:
                try:
                    found = json.loads(text[start:end + 1])
                except ValueError:
                    break
                if isinstance(found, dict) and len(json.dumps(found)) > 40:
                    return found
                break
    words = (str(prompt) + ' ' + text)[:2000]
    title = re.search(r'([A-Z][\w-]+(?:[ -][A-Z][\w-]+){0,3})', ' '.join(str(prompt).split()[1:]))
    return dict(title=title.group(1) if title else 'Simulation', notes=words)
