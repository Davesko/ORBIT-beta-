"""Szimgyár runner (media-runtime python): Kobold's physics engine (szim_engine) and recipe learner (szim_recipes) for ORBIT.

    python3 -I szim_run.py render <spec.json> <out.mp4> [workdir]   -> last stdout line: {"spec","mag","meres"}
    python3 -I szim_run.py recipe <project_dir> [topic] [recipe_id] -> last stdout line: {"mod","recept","spec","miert"}
    python3 -I szim_run.py catalog                                  -> recipes + the choosable values (palettes, instruments, melodies)
    python3 -I szim_run.py knowledge <project_dir>                  -> prints the building blocks + proven examples text
    python3 -I szim_run.py schema                                   -> prints the spec JSON schema

Videos of a project are the records <project_dir>/simulations/*.json that carry a "szim" object (spec, mag, meres);
"allapot" (kesz / jovahagyva / elvetve) and "megjegyzes" in the record steer what the recipes and the designer learn.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault('ORBIT_SZIM_ADAT', str(Path.home() / 'Library/Application Support/Orbit/szimgyar'))
rt_bin = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin'
os.environ['PATH'] = str(rt_bin) + os.pathsep + os.environ.get('PATH', '')

import szim_engine as S  # noqa: E402


def clips(project_dir):
    """Kobold's 'klipek' view of a project's simulation records."""
    out = []
    for path in sorted(Path(project_dir, 'simulations').glob('*.json')):
        try:
            rec = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and (rec.get('szim') or {}).get('spec'):
            rec.setdefault('id', path.stem)
            rec.setdefault('allapot', 'kesz')
            rec.setdefault('letrehozva', path.stat().st_mtime)
            out.append(rec)
    return out


def settings_of(project_dir):
    try:
        return json.loads(Path(project_dir, 'szimgyar_settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def catalog():
    import szim_recipes as R
    recipes = [dict(azon=r['azon'], nev=r['nev'], ikon=r.get('ikon', ''), leiras=r.get('leiras', '')) for r in R.osszes()]
    return dict(recipes=recipes, palettes=list(S.PALETTAK), containers=list(S.PALYAK))


TREND_INSTRUMENTS = ['pop', 'koppanas', 'buborek', 'vizcsepp', 'boing', '8bit', 'xilofon']
_trend = {}


def trend_ready():
    """Refresh the viral-sound library when it is stale (top TikTok songs + meme sounds); True if a song is available."""
    if 'ok' not in _trend:
        try:
            import szim_trendhang as T
            if T.friss_kell():
                T.frissit(naplo=lambda text: print('  ' + text, file=sys.stderr, flush=True))
            _trend['ok'] = bool(T.zenek())
        except Exception as error:
            print('trend refresh failed: ' + str(error)[:300], file=sys.stderr)
            _trend['ok'] = False
    return _trend['ok']


def apply_settings(plan, cfg):
    """The owner's preferences on top of a recipe variant: palettes, sounds, length. Physics stays the proven recipe."""
    import random
    spec = plan['spec']
    pal = [x for x in cfg.get('palettes') or [] if x in S.PALETTAK]
    if pal and spec.get('paletta') not in pal:
        spec['paletta'] = random.choice(pal)
    # Sound is never a setting: the freshest viral TikTok song under the video, short meme sounds on the bounces.
    hang = spec.setdefault('hang', {})
    hang['zene'] = 'trend' if trend_ready() else 'nincs'
    hang['meme'] = 'trend' if trend_ready() else 'nincs'
    if hang.get('hangszer') not in TREND_INSTRUMENTS:
        hang['hangszer'] = random.choice(TREND_INSTRUMENTS)
    hang['dallam'] = random.choice(['meret', 'veletlen'])
    lo, hi = int(cfg.get('seconds_min') or 0), int(cfg.get('seconds_max') or 0)
    if spec.get('hossz') and lo and hi >= lo:
        spec['hossz'] = max(lo, min(hi, spec['hossz']))
    return plan


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    cmd = argv[0]
    if cmd == 'render':
        spec = json.loads(Path(argv[1]).read_text(encoding='utf-8'))
        out = argv[2]
        work = argv[3] if len(argv) > 3 and argv[3] != '--strict' else str(Path(out).parent / ('work-' + Path(out).stem))
        started = time.time()
        try:
            res = S.keszit(spec, out, munka=work, halad=lambda text: print('  ' + text, file=sys.stderr, flush=True), szigoru='--strict' in argv)
        except S.MinosegHiba as hiba:
            print(str(hiba), file=sys.stderr)
            raise SystemExit(3)
        res['render_s'] = round(time.time() - started, 1)
        print(json.dumps(res, ensure_ascii=False))
    elif cmd == 'recipe':
        import random
        import szim_recipes as R
        cfg = settings_of(argv[1])
        off = {k for k, v in (cfg.get('recipes') or {}).items() if v is False}
        every = R.osszes
        R.osszes = lambda: [r for r in every() if r['azon'] not in off] or every()
        shots = clips(argv[1])
        topic = argv[2] if len(argv) > 2 else ''
        wanted = argv[3] if len(argv) > 3 else ''
        if wanted:
            r = R.recept(wanted)
            if not r:
                raise SystemExit('Ismeretlen recept: ' + wanted)
            plan = {'mod': 'recept', 'recept': r, 'spec': R.valtozat(r, random.Random(), tapasztalat=R.ertek_tapasztalat(shots, r)),
                    'miert': f"{r.get('ikon', '')} {r['nev']} (kézi választás)"}
        else:
            # a free experiment needs an agent to write a new spec; unattended production sticks to proven recipes
            plan = R.terv(shots, topic, kiserlet_arany=0.0)
            if not plan.get('spec'):
                plan = R.terv(shots, '', kiserlet_arany=0.0)
        print(json.dumps(apply_settings(plan, cfg), ensure_ascii=False))
    elif cmd == 'trends':
        import szim_trendhang as T
        T.frissit(naplo=lambda text: print('  ' + text, file=sys.stderr, flush=True))
        print(json.dumps(T.osszefoglalo() if isinstance(T.osszefoglalo(), (dict, list)) else str(T.osszefoglalo()), ensure_ascii=False))
    elif cmd == 'catalog':
        print(json.dumps(catalog(), ensure_ascii=False))
    elif cmd == 'knowledge':
        print(S.tudas(clips(argv[1])))
    elif cmd == 'schema':
        print(json.dumps(S.spec_sema(), ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
