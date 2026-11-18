"""Videoklip stúdió (owner, 12 Nov): a project for planning music videos.

One clip = one JSON file under projects/<pid>/clips/<id>.json: the song (an imported audio file, analysed for length,
tempo, energy and parts; lyrics pasted by the owner), the owner's direction and free notes, concepts, the story, a
moodboard, references, a storyboard, Hungarian locations and a budget. Everything is editable by hand; the AI fills or
extends it on request:
  * clip_think   — listens to the analysed song, the lyrics and the direction, writes concepts, story, storyboard, moodboard
                   prompts, palette, references, location needs and crew/gear needs (local model, JSON answer);
  * clip_images  — local FLUX draws the moodboard and the storyboard frames that have no picture yet;
  * clip_locations — searches the web for rentable Hungarian locations for each location need and records the links.
The budget is computed here from editable lines (HUF). Day rates are Hungarian market estimates the owner overwrites;
nothing is booked, paid or sent to anyone.
"""
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

NAME = 'Videoklip stúdió'
KIND = 'musicvideo'
SECTIONS = ('overview', 'song', 'concept', 'moodboard', 'storyboard', 'locations', 'budget', 'notes')

# Indicative Hungarian day rates (HUF, 2026) for a small independent music video; the owner edits every line.
RATES = {
    'Rendező': 150000, 'Operatőr': 140000, 'Operatőr-asszisztens / fókuszhúzó': 60000, 'Gaffer (világosító)': 70000,
    'Világosító asszisztens': 45000, 'Gyártásvezető': 70000, 'Smink': 45000, 'Stylist / jelmez': 50000,
    'Díszlet / art director': 80000, 'Vágó (napi)': 60000, 'Színkorrektor (napi)': 80000, 'Drón operátor': 90000,
    'Színész / szereplő': 50000, 'Statiszta': 15000, 'Táncos': 40000, 'Koreográfus': 70000,
    'Kamera szett bérlés': 80000, 'Objektív szett': 40000, 'Fény csomag': 60000, 'Drón bérlés': 50000,
    'Gimbal / stabilizátor': 20000, 'Füstgép / effekt': 15000, 'Kisbusz / szállítás': 35000, 'Catering (fő/nap)': 6000,
}
LOCATION_DAY = {'stúdió': 120000, 'lakás': 80000, 'loft': 150000, 'iroda': 100000, 'bár': 150000, 'klub': 200000,
                'étterem': 150000, 'gyár': 180000, 'raktár': 120000, 'tető': 150000, 'kastély': 300000, 'erdő': 30000,
                'tó': 40000, 'utca': 50000, 'parkoló': 60000, 'templom': 150000, 'uszoda': 200000, 'tornaterem': 80000}
CATEGORIES = ('Stáb', 'Szereplők', 'Technika', 'Helyszín', 'Utómunka', 'Logisztika', 'Egyéb')


def folder(s, pid):
    path = s.safe_path(pid, 'clips')
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure(s):
    """The Videoklip stúdió project exists once; its kind gives the Műhely its own app."""
    row = s.db.execute('SELECT id FROM projects WHERE kind=?', (KIND,)).fetchone()
    if row:
        return row[0]
    pid = s.create_project(NAME, 'Videoklipek tervezése: zene, irány, koncepció, moodboard, storyboard, helyszínek és költségvetés.', KIND)
    s.save_agent(dict(project=pid, name='Rendező', role='Videoklip-rendező', room='bridge', color='#ff9f6e', model='auto',
                      prompt=('You are a music video director. Read the song analysis, lyrics and the owner direction; propose concepts '
                              'that can really be shot in Hungary on the given budget, with a clear visual story that follows the music.'),
                      tools=['project_files', 'read_file', 'write_file', 'web_search', 'read_web']))
    return pid


def new_id():
    return uuid.uuid4().hex[:12]


def blank(title='Új videoklip'):
    now = time.time()
    return dict(id=new_id(), title=title[:120], artist='', created=now, updated=now, song=dict(artifact=None, name='', duration=None,
                bpm=None, parts=[], lyrics=''), direction='', notes='', concepts=[], chosen=0, story=dict(logline='', synopsis='', beats=[]),
                palette=[], moodboard=[], references=[], storyboard=[], location_needs=[], locations=[],
                budget=dict(lines=[], contingency=10, currency='HUF'), log=[])


def path_of(s, pid, cid):
    if not re.fullmatch(r'[a-f0-9]{12}', str(cid or '')):
        raise ValueError('Ismeretlen klip.')
    return folder(s, pid) / f'{cid}.json'


def load(s, pid, cid):
    p = path_of(s, pid, cid)
    if not p.is_file():
        raise ValueError('Ismeretlen klip.')
    return json.loads(p.read_text(encoding='utf-8'))


def store(s, pid, clip):
    clip['updated'] = time.time()
    for k in clip.get('concepts') or []:
        if isinstance(k, dict) and not k.get('id'):
            k['id'] = new_id()
    p = path_of(s, pid, clip['id'])
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(clip, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(p)
    return clip


def note(clip, text):
    clip.setdefault('log', []).insert(0, dict(at=time.time(), text=str(text)[:300]))
    del clip['log'][30:]


def listing(s, pid):
    out = []
    for p in sorted(folder(s, pid).glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            c = json.loads(p.read_text(encoding='utf-8'))
        except ValueError:
            continue
        if c.get('archived'):
            continue
        out.append(dict(id=c['id'], title=c.get('title'), artist=c.get('artist'), updated=c.get('updated'), song=c.get('song', {}).get('name'),
                        total=budget(c)['total'], cover=next((m.get('artifact') for m in c.get('moodboard', []) if m.get('artifact')), None)))
    return out


def budget(clip):
    lines = clip.get('budget', {}).get('lines', [])
    by = {}
    subtotal = 0
    for line in lines:
        try:
            value = float(line.get('qty') or 0) * float(line.get('rate') or 0)
        except (TypeError, ValueError):
            value = 0
        line['total'] = round(value)
        subtotal += value
        by[line.get('category') or 'Egyéb'] = by.get(line.get('category') or 'Egyéb', 0) + value
    reserve = subtotal * float(clip.get('budget', {}).get('contingency') or 0) / 100
    cap = clip.get('budget', {}).get('cap')
    return dict(subtotal=round(subtotal), reserve=round(reserve), total=round(subtotal + reserve), by_category={k: round(v) for k, v in by.items()},
                cap=cap, over=bool(cap and subtotal + reserve > cap))


EDITABLE = ('title', 'artist', 'direction', 'notes', 'chosen', 'palette', 'concepts', 'story', 'moodboard', 'references', 'storyboard',
            'location_needs', 'locations', 'budget')


def save(s, pid, cid, patch):
    clip = load(s, pid, cid)
    for key, value in (patch or {}).items():
        if key == 'lyrics':
            clip['song']['lyrics'] = str(value)[:12000]
        elif key in EDITABLE:
            clip[key] = value
    if 'direction' in (patch or {}) and not (patch.get('budget') or {}).get('cap'):
        found = budget_cap(clip.get('direction'))
        if found:
            clip['budget']['cap'] = found
    for item_list in ('moodboard', 'references', 'storyboard', 'locations'):
        for item in clip.get(item_list) or []:
            if isinstance(item, dict) and not item.get('id'):
                item['id'] = new_id()
    for line in clip['budget'].get('lines', []):
        if not line.get('id'):
            line['id'] = new_id()
    return dict(clip=store(s, pid, clip), budget=budget(clip))


# ---------------------------------------------------------------- the song
ANALYSE = r'''
import json, subprocess, sys
import numpy as np
ffmpeg, path = sys.argv[1], sys.argv[2]
rate = 11025
raw = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(rate), '-f', 'f32le', '-'], capture_output=True, check=True, timeout=300).stdout
x = np.frombuffer(raw, np.float32)
duration = len(x) / rate
hop = rate // 2
rms = np.array([float(np.sqrt(np.mean(x[i:i + hop] ** 2))) for i in range(0, len(x) - hop, hop)]) if len(x) > hop else np.zeros(1)
energy = (rms / (rms.max() or 1)).round(3)
# tempo: autocorrelation of the onset strength (positive energy change in 23 ms frames)
f = 256
frames = np.array([float(np.sum(np.abs(x[i:i + f]))) for i in range(0, len(x) - f, f)]) if len(x) > f else np.zeros(2)
onset = np.maximum(0, np.diff(frames)); onset -= onset.mean()
fps = rate / f
bpm = None
if len(onset) > fps * 8:
    seg = onset[: int(fps * 90)]
    ac = np.correlate(seg, seg, 'full')[len(seg) - 1:]
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)
    lag = lo + int(np.argmax(ac[lo:hi])) if hi > lo else 0
    bpm = round(60 * fps / lag, 1) if lag else None
# parts: smooth the energy and cut where the 8-second level jumps
k = 16
smooth = np.convolve(energy, np.ones(k) / k, 'same') if len(energy) > k else energy
cuts = [0]
for i in range(k, len(smooth) - k, 4):
    if abs(smooth[i] - smooth[cuts[-1]]) > .22 and i - cuts[-1] >= 24:
        cuts.append(i)
cuts.append(len(smooth))
parts = []
for a, b in zip(cuts, cuts[1:]):
    level = float(np.mean(energy[a:b])) if b > a else 0
    parts.append(dict(start=round(a * .5, 1), end=round(b * .5, 1), energy=round(level, 2)))
top = max((p['energy'] for p in parts), default=1) or 1
for i, p in enumerate(parts):
    p['label'] = 'Intro' if i == 0 and len(parts) > 2 else 'Outro' if i == len(parts) - 1 and len(parts) > 2 else ('Refrén / csúcs' if p['energy'] >= .8 * top else 'Verze / átvezetés')
print(json.dumps(dict(duration=round(duration, 1), bpm=bpm, parts=parts, energy=energy[::2].tolist()[:400])))
'''


def attach_song(s, pid, cid, artifact):
    clip = load(s, pid, cid)
    row = s.db.execute("SELECT * FROM artifacts WHERE id=? AND project=? AND kind IN ('audio','video')", (artifact, pid)).fetchone()
    if not row:
        raise ValueError('Válassz egy hangfájlt a projekt fájljai közül.')
    clip['song'].update(artifact=row['id'], name=row['name'], duration=None, bpm=None, parts=[])
    note(clip, 'Zene csatolva: ' + row['name'])
    store(s, pid, clip)
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    s.enqueue(agent[0], 'Videoklip · zene elemzése', 'assist', payload=dict(task='clip_song', project=pid, clip=cid, local_only=True))
    return clip


def analyse_song(s, job):
    p = json.loads(job['payload'])
    clip = load(s, p['project'], p['clip'])
    row = s.db.execute('SELECT path FROM artifacts WHERE id=?', (clip['song'].get('artifact'),)).fetchone()
    if not row:
        raise ValueError('A klip zenéje nem található.')
    runtime = s.root / 'media-runtime/bin'
    s.job_stage(job['id'], 'audio', 'A zene hossza, tempója, energiája és részei')
    done = subprocess.run([str(runtime / 'python3'), '-I', '-c', ANALYSE, str(runtime / 'ffmpeg'), row['path']], capture_output=True, text=True, timeout=400)
    if done.returncode:
        raise ValueError('A zene elemzése nem sikerült: ' + done.stderr[-300:])
    result = json.loads(done.stdout)
    clip = load(s, p['project'], p['clip'])
    clip['song'].update(result)
    note(clip, f"Zene elemezve: {result['duration']} mp, ~{result.get('bpm') or '?'} BPM, {len(result['parts'])} rész")
    store(s, p['project'], clip)
    return f"A zene elemezve: {result['duration']} mp, ~{result.get('bpm') or '?'} BPM."


# ---------------------------------------------------------------- the AI director
THINK_SCHEMA = {'type': 'object', 'required': ['concepts', 'story', 'storyboard', 'moodboard', 'palette', 'location_needs', 'crew', 'references'],
    'properties': {
        'concepts': {'type': 'array', 'minItems': 2, 'maxItems': 3, 'items': {'type': 'object', 'required': ['title', 'logline', 'why', 'look', 'look_prompt'],
                     'properties': {'title': {'type': 'string'}, 'logline': {'type': 'string'}, 'why': {'type': 'string'},
                                    'look': {'type': 'string'}, 'look_prompt': {'type': 'string'}}}},
        'story': {'type': 'object', 'required': ['logline', 'synopsis', 'beats'], 'properties': {'logline': {'type': 'string'}, 'synopsis': {'type': 'string'},
                  'beats': {'type': 'array', 'maxItems': 8, 'items': {'type': 'object', 'required': ['time', 'text'], 'properties': {'time': {'type': 'string'}, 'text': {'type': 'string'}}}}}},
        'storyboard': {'type': 'array', 'minItems': 6, 'maxItems': 12, 'items': {'type': 'object', 'required': ['start', 'end', 'shot', 'description', 'camera', 'location'],
                       'properties': {'start': {'type': 'number'}, 'end': {'type': 'number'}, 'shot': {'type': 'string'}, 'description': {'type': 'string'},
                                      'camera': {'type': 'string'}, 'location': {'type': 'string'}, 'image_prompt': {'type': 'string'}}}},
        'moodboard': {'type': 'array', 'minItems': 4, 'maxItems': 6, 'items': {'type': 'object', 'required': ['prompt', 'note'],
                      'properties': {'prompt': {'type': 'string'}, 'note': {'type': 'string'}}}},
        'mood': {'type': 'string'},
        'palette': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}},
        'location_needs': {'type': 'array', 'maxItems': 5, 'items': {'type': 'object', 'required': ['type', 'description', 'days'],
                           'properties': {'type': {'type': 'string'}, 'description': {'type': 'string'}, 'city': {'type': 'string'}, 'days': {'type': 'number'}}}},
        'crew': {'type': 'array', 'maxItems': 12, 'items': {'type': 'object', 'required': ['role', 'days', 'count'],
                 'properties': {'role': {'type': 'string'}, 'days': {'type': 'number'}, 'count': {'type': 'number'}}}},
        'references': {'type': 'array', 'maxItems': 4, 'items': {'type': 'object', 'required': ['title', 'note'],
                       'properties': {'title': {'type': 'string'}, 'note': {'type': 'string'}}}}}}

# The plan is asked in two smaller answers: everything but the storyboard, then the storyboard. One answer with all of it ran
# past the local model's output limit ("A terv túl hosszú lett"): four "Ebből tervezz" runs failed so on 12 Nov.
PLAN_SCHEMA = dict(THINK_SCHEMA, required=['concepts', 'story', 'moodboard', 'palette', 'mood', 'location_needs', 'crew', 'references'],
                   properties={k: v for k, v in THINK_SCHEMA['properties'].items() if k != 'storyboard'})
CONCEPT_PLAN_SCHEMA = dict(PLAN_SCHEMA, required=[k for k in PLAN_SCHEMA['required'] if k != 'concepts'],
                           properties={k: v for k, v in PLAN_SCHEMA['properties'].items() if k != 'concepts'})
BOARD_SCHEMA = {'type': 'object', 'required': ['storyboard'], 'properties': {'storyboard': THINK_SCHEMA['properties']['storyboard']}}


def think(s, pid, cid, focus='', chain=False, concept=None):
    clip = load(s, pid, cid)
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    s.enqueue(agent[0], 'Videoklip · a Rendező gondolkodik', 'assist', payload=dict(task='clip_think', project=pid, clip=cid, focus=str(focus)[:600], chain=bool(chain),
                                                                                    concept=concept, local_only=True))
    note(clip, 'A Rendező gondolkodik' + (': ' + focus[:80] if focus else ''))
    store(s, pid, clip)
    return dict(message='A Rendező dolgozik rajta; pár perc múlva itt lesz.')


def ask(s, system, data, schema, budget=420, temperature=.6, length=5200):
    from studio import local_api
    from assist_jobs import chat_model
    reply = local_api('ollama', 'api/chat', {'model': chat_model(), '_orbit_purpose': 'utility', '_orbit_budget': budget, 'stream': False, 'think': False,
                                             'format': schema, 'messages': [{'role': 'system', 'content': system},
                                                                            {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
                                             'options': {'num_ctx': 16384, 'num_predict': length, 'temperature': temperature}, 'keep_alive': '5m'}, timeout=budget + 60)
    return json.loads(reply.get('message', {}).get('content', '{}'))


# ---------------------------------------------------------------- the budget cap
def budget_cap(text):
    """The owner's ceiling in HUF from free text ("max 250 ezer forint", "250k", "1,5 millió", "300 000 Ft"), or None.
    Only a number next to a money word or a budget word counts, so "2 lány" or "3 perc" are not a budget."""
    text = str(text or '')
    best = None
    for m in re.finditer(r'(?:(max(?:imum)?\.?|legfeljebb|keret\w*|budget\w*|költségvetés\w*|költség\w*)\s*:?\s*)?'
                         r'(\d{1,3}(?:[ .]\d{3})+|\d+(?:[.,]\d+)?)\s*(millió|milla|ezer|e|k|m)?\s*(ft|forint|huf)?\b', text, re.I):
        lead, number, unit, money = m.group(1), m.group(2), (m.group(3) or '').lower(), m.group(4)
        if not (lead or money or unit in ('ezer', 'millió', 'milla', 'k')):
            continue
        value = float(number.replace(' ', '').replace('.', '') if re.fullmatch(r'\d{1,3}(?:[ .]\d{3})+', number) else number.replace(',', '.'))
        value *= {'millió': 1e6, 'milla': 1e6, 'm': 1e6, 'ezer': 1e3, 'e': 1e3, 'k': 1e3}.get(unit, 1)
        if 10000 <= value <= 500e6:
            best = value if best is None else min(best, value)
    return round(best) if best else None


# Indie / low-budget rates: friends' rates, own gear, free places. Used when the plan must fit a small ceiling.
LOW_RATES = {'Rendező': 0, 'Operatőr': 50000, 'Operatőr-asszisztens / fókuszhúzó': 20000, 'Gaffer (világosító)': 25000, 'Világosító asszisztens': 15000,
             'Gyártásvezető': 0, 'Smink': 20000, 'Stylist / jelmez': 15000, 'Díszlet / art director': 20000, 'Vágó (napi)': 25000,
             'Színkorrektor (napi)': 25000, 'Drón operátor': 40000, 'Színész / szereplő': 20000, 'Statiszta': 0, 'Táncos': 20000,
             'Koreográfus': 25000, 'Kamera szett bérlés': 25000, 'Objektív szett': 10000, 'Fény csomag': 15000, 'Drón bérlés': 20000,
             'Gimbal / stabilizátor': 8000, 'Füstgép / effekt': 6000, 'Kisbusz / szállítás': 15000, 'Catering (fő/nap)': 3000,
             'Catering': 3000, 'Vágás és színkorrekció': 25000}
# What goes first when the plan is over the ceiling (the least needed for a small shoot).
DROP_ORDER = ('Díszlet / art director', 'Gyártásvezető', 'Világosító asszisztens', 'Operatőr-asszisztens / fókuszhúzó', 'Színkorrektor (napi)',
              'Drón operátor', 'Drón bérlés', 'Koreográfus', 'Objektív szett', 'Füstgép / effekt', 'Gimbal / stabilizátor', 'Stylist / jelmez',
              'Gaffer (világosító)', 'Kisbusz / szállítás', 'Statiszta')


def role_stems(name):
    return {w[:5] for w in re.findall(r'[a-záéíóöőúüű]{4,}', str(name or '').lower())} - {'bérl', 'napi', 'szett', 'csoma'}


def low_rate(item):
    """The indie rate for a line even when the AI wrote the role its own way ("Rendező / Operatőr", "Színész / Szereplő",
    "Fókusz / Asszisztens"): exact name first, then the roles that share a word stem; a combined role takes the higher one
    (13 Nov: none matched exactly and a 400 000 Ft clip stayed at 773 850 Ft)."""
    if item in LOW_RATES:
        return LOW_RATES[item]
    folded = {k.lower(): v for k, v in LOW_RATES.items()}
    if str(item or '').lower() in folded:
        return folded[str(item).lower()]
    mine = role_stems(item)
    hits = [v for k, v in LOW_RATES.items() if mine & role_stems(k)]
    return max(hits) if hits else None


def same_role(item, role):
    return item == role or bool(role_stems(item) & role_stems(role)) and len(role_stems(role)) <= 2


def fit_budget(clip):
    """Bring the AI's lines under the owner's ceiling: indie rates first, then free or cheap places, a smaller reserve,
    then the least needed roles. The owner's own lines are never touched. Returns what was done, in Hungarian."""
    cap = clip['budget'].get('cap')
    if not cap or budget(clip)['total'] <= cap:
        return []
    done = []
    ai = [l for l in clip['budget']['lines'] if not l.get('owner')]
    for l in ai:
        low = low_rate(l.get('item'))
        if low is not None and low < (l.get('rate') or 0):
            l['rate'] = low
            l['note'] = 'Kis költségvetésű ár (barát / saját eszköz)'
    done.append('kis költségvetésű díjak')
    if budget(clip)['total'] > cap:
        for l in ai:
            if l.get('category') == 'Helyszín':
                l['rate'] = min(l.get('rate') or 0, 20000)
                l['note'] = 'Ingyenes vagy olcsó hely: közterület, ismerős lakása, nyitvatartáson kívüli üzlet'
        done.append('ingyenes / olcsó helyszín')
    if budget(clip)['total'] > cap:
        clip['budget']['contingency'] = min(float(clip['budget'].get('contingency') or 0), 5)
        done.append('5% tartalék')
    for role in DROP_ORDER:
        if budget(clip)['total'] <= cap:
            break
        line = next((l for l in clip['budget']['lines'] if not l.get('owner') and same_role(l.get('item'), role)), None)
        if line:
            clip['budget']['lines'].remove(line)
            done.append(role + ' nélkül')
    for l in clip['budget']['lines']:
        if budget(clip)['total'] <= cap:
            break
        if not l.get('owner') and l.get('item') in ('Catering', 'Vágás és színkorrekció') and float(l.get('qty') or 0) > 1:
            l['qty'] = max(1, round(float(l['qty']) / 2))
    total = budget(clip)['total']
    done.append(('belefér: ' if total <= cap else 'még így is több: ') + f'{total:,} Ft / {cap:,} Ft'.replace(',', ' '))
    return done


# ---------------------------------------------------------------- creative directions
LENSES = ('one continuous take that travels through places', 'a surreal visual metaphor for the song\'s feeling', 'a tiny story with a twist ending',
          'performance in a place where nobody expects music (laundromat, tram, swimming pool, supermarket at night)',
          'a 90s / Y2K home-video or TV-show parody', 'a fashion editorial with bold graphic framing', 'a dance that infects strangers one by one',
          'time running backwards or looping', 'split screen / mirror: two worlds that meet in the chorus', 'documentary vérité of a real night out',
          'a fake commercial or game show', 'nature against the city: Lake Balaton, forest or Hortobágy plains', 'light painting and darkness, shot almost only with practical lights',
          'a road movie in a borrowed car across Hungary', 'a heist / mission story told with no dialogue', 'stop-motion or photo-sequence look shot on a phone')


def lenses(seed, n=3):
    import random
    return random.Random(seed).sample(LENSES, n)


CREATIVE = ('Think like an award-winning, very creative music video director: every concept must be a surprising, specific, visual idea, '
            'not a description of the cast or the genre. Use each creative lens in lenses for one concept, so the concepts are really '
            'different from each other. Treat the owner direction as constraints and taste (cast count, budget, mood), never as the idea itself: '
            'if two girls must appear, invent a world, a relationship or a game for them; do not just film them dancing. '
            'Avoid the obvious (generic loft, club, rooftop at sunset) unless the twist makes it fresh. ')


MOOD_RULES = ('mood: 6-10 English words for the feeling of the song and the concept (for example "slow sensual heat, late night, intimate, '
              'hazy, nostalgic"). moodboard: exactly 6 English image prompts that SHOW THE MOOD of this concept, each a different kind of picture: '
              '1 the place wide with its light, 2 a close portrait with emotion, 3 wardrobe and styling detail, 4 a texture or prop detail, '
              '5 the light and colour study, 6 a moment of movement (dance, motion blur). Each prompt names the subject, the action, the place, '
              'the time of day, the light source, the colours and the lens, and fits the cast in the owner direction; note: one Hungarian line why. ')


def hungarian_title(text):
    """'A Betörő Buszjárat (The Striking Bus Route)' -> 'A Betörő Buszjárat'."""
    return re.sub(r'\s*\((?:the |a |an )?[A-Za-z][^)]*\)\s*$', '', str(text or '')).strip()


def money_rules(cap):
    if not cap:
        return 'No budget ceiling was given: plan a small independent production. '
    return (f'HARD BUDGET CEILING: {cap} HUF for everything (crew, cast, gear, places, food, post). Design the concepts for this money: '
            'a tiny crew (often the director shoots, one camera operator with own gear), free places (streets, nature, friends\' flats, '
            'shops after hours), natural or practical light, one shooting day. The crew list must fit the ceiling; say in why how the idea stays cheap. ')


def run_think(s, job):
    p = json.loads(job['payload'])
    clip = load(s, p['project'], p['clip'])
    song = clip['song']
    cap = clip['budget'].get('cap') or budget_cap(' '.join(str(clip.get(k) or '') for k in ('direction', 'notes')))
    clip['budget']['cap'] = cap
    s.job_stage(job['id'], 'model', 'A Rendező a zenén és az irányon gondolkodik')
    data = dict(title=clip.get('title'), artist=clip.get('artist'), song=dict(name=song.get('name'), duration_seconds=song.get('duration'), bpm=song.get('bpm'),
                parts=song.get('parts'), lyrics=(song.get('lyrics') or '')[:6000]), owner_direction=clip.get('direction'), owner_notes=(clip.get('notes') or '')[:3000],
                budget_ceiling_huf=cap, lenses=lenses(time.time()), focus=p.get('focus') or '', current_story=clip.get('story'),
                crew_roles=list(RATES), location_types=list(LOCATION_DAY))
    system = ('You are a Hungarian music video director and producer. From the song analysis (length, tempo, energy parts), the lyrics and the '
              'owner direction, plan a music video that can really be shot in Hungary. ' + CREATIVE + money_rules(cap) +
              'Write in Hungarian (concept titles too, no English translation in brackets) except moodboard prompt and mood, which are English. '
              'concepts: 3 different directions; story follows the first concept, at most 8 beats timed to the song parts (time like "0:00-0:25"); '
              + MOOD_RULES +
              'palette: hex colours; location_needs: places needed (type from location_types, city in Hungary, shooting days); crew: only people '
              'and gear from crew_roles that this idea really needs, with days and head count; references: well-known films, photographers or '
              'music videos whose look fits (title + why). Keep every text short. If focus is given, change only that part and keep the rest '
              'consistent with current_story. Return JSON only.')
    concept = p.get('concept')
    schema = PLAN_SCHEMA
    if isinstance(concept, dict):
        # "Ebből tervezz": the whole plan follows this concept (owner 12 Nov: a new concept needs a new moodboard too).
        data['plan_this_concept'] = {k: concept.get(k) for k in ('title', 'logline', 'look', 'why')}
        data.pop('current_story', None)
        system += (' plan_this_concept is the concept the owner chose: story, moodboard, palette, mood, locations and crew must all follow it.')
        schema = CONCEPT_PLAN_SCHEMA
    answer = ask(s, system, data, schema, temperature=.85)
    s.job_stage(job['id'], 'model', 'A Rendező megírja a storyboardot')
    board = ask(s, 'You are a Hungarian music video director. Write the storyboard for this plan: 6-12 shots that cover the whole song '
                   '(start/end seconds from 0 to the song length, following the song parts and the story beats), each with shot size, camera '
                   'move, location and a short Hungarian description (max 25 words), plus image_prompt: an English cinematic still prompt for '
                   'the shot (subject, action, place, light, colour, lens). Return JSON only.',
                dict(song=dict(duration_seconds=song.get('duration'), bpm=song.get('bpm'), parts=song.get('parts')), story=answer.get('story'),
                     concept=data.get('plan_this_concept') or (answer.get('concepts') or [{}])[0], mood=answer.get('mood'), owner_direction=clip.get('direction')),
                BOARD_SCHEMA, budget=300, temperature=.7, length=4200)
    answer['storyboard'] = board.get('storyboard') or []
    clip = load(s, p['project'], p['clip'])
    if not clip.get('replanning'):
        remember(clip)
    clip['replanning'] = None
    clip['mood'] = str(answer.get('mood') or clip.get('mood') or '')[:300]
    clip['budget']['cap'] = cap
    if isinstance(concept, dict):
        others = [k for k in clip['concepts'] if k.get('title') != concept.get('title')]
        clip['concepts'] = [dict(concept)] + others
    else:
        clip['concepts'] = [dict(k, title=hungarian_title(k.get('title'))) for k in answer.get('concepts') or []] or clip['concepts']
    clip['chosen'] = 0
    clip['story'] = answer.get('story') or clip['story']
    if isinstance(clip['story'], dict):
        clip['story']['beats'] = fit_beats(clip['story'].get('beats') or [], song.get('duration'))
    clip['palette'] = [c for c in answer.get('palette') or [] if re.fullmatch(r'#[0-9a-fA-F]{6}', str(c))] or clip.get('palette', [])
    keep = {m['prompt']: m for m in clip.get('moodboard', [])}
    clip['moodboard'] = [keep.get(m['prompt']) or dict(id=new_id(), prompt=m['prompt'], note=m.get('note', ''), artifact=None) for m in answer.get('moodboard') or []] + \
        [m for m in clip.get('moodboard', []) if m.get('owner')]
    clip['storyboard'] = [dict(id=new_id(), artifact=None, note='', **{k: sh.get(k) for k in ('start', 'end', 'shot', 'description', 'camera', 'location', 'image_prompt')})
                          for sh in answer.get('storyboard') or []] or clip['storyboard']
    clip['location_needs'] = answer.get('location_needs') or clip.get('location_needs', [])
    clip['references'] = [r for r in clip.get('references', []) if r.get('owner')] + [dict(id=new_id(), title=r['title'], note=r.get('note', '')) for r in answer.get('references') or []]
    clip['budget']['lines'] = [l for l in clip['budget'].get('lines', []) if l.get('owner')] + plan_lines(answer.get('crew') or [], clip['location_needs'],
                                                                                                          ' '.join(str(x or '') for x in (clip.get('direction'), (concept or {}).get('logline') if isinstance(concept, dict) else '')))
    clip['budget']['contingency'] = clip['budget'].get('contingency', 10)
    fitted = fit_budget(clip)
    note(clip, 'A Rendező elkészítette a tervet' + (f" ({p['focus'][:60]})" if p.get('focus') else '') + ('; keretbe illesztve: ' + ', '.join(fitted) if fitted else ''))
    store(s, p['project'], clip)
    # The plan is saved first, then its pictures are drawn. Every new plan replaces the storyboard with frames without a
    # picture, so the drawing follows any plan, not only a full one (13 Nov: "Slow down" was left with 12 empty frames).
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    if any(not x.get('artifact') for x in clip['moodboard'] + clip['storyboard']):
        s.enqueue(agent[0], 'Videoklip · képek rajzolása', 'assist', payload=dict(task='clip_images', project=p['project'], clip=p['clip'], which='all', local_only=True))
    if p.get('chain') and clip.get('location_needs'):
        s.enqueue(agent[0], 'Videoklip · helyszínkeresés', 'assist', payload=dict(task='clip_locations', project=p['project'], clip=p['clip'], local_only=True))
    return 'A Rendező terve kész: ' + str((clip['story'] or {}).get('logline', ''))[:160]


PLAN_KEYS = ('concepts', 'chosen', 'story', 'palette', 'moodboard', 'storyboard', 'location_needs', 'locations', 'budget', 'references')


def remember(clip):
    """The plan before a re-plan becomes a version (at most six), so a concept that was dropped can come back."""
    if not clip.get('concepts') and not clip.get('storyboard'):
        return
    title = (clip['concepts'][clip.get('chosen') or 0].get('title') if clip.get('concepts') else '') or 'Korábbi terv'
    clip.setdefault('versions', []).insert(0, dict(id=new_id(), at=time.time(), title=title, plan=json.loads(json.dumps({k: clip.get(k) for k in PLAN_KEYS}))))
    del clip['versions'][6:]


def restore(s, pid, cid, vid):
    clip = load(s, pid, cid)
    version = next((v for v in clip.get('versions', []) if v.get('id') == vid), None)
    if not version:
        raise ValueError('Ismeretlen változat.')
    clip['versions'].remove(version)
    remember(clip)
    clip.update(version['plan'])
    note(clip, 'Visszaállítva: ' + version['title'])
    store(s, pid, clip)
    return dict(clip=clip, budget=budget(clip))


SELF_ADDED = re.compile(r'catering|kisbusz|szállítás|vágó|színkorrektor', re.I)   # added once below, not again from the crew list


NUMBER = {'egy': 1, 'két': 2, 'kettő': 2, 'ketto': 2, 'három': 3, 'harom': 3, 'négy': 4, 'negy': 4, 'öt': 5, 'ot': 5, 'hat': 6}
PEOPLE = r'lány\w*|fiú\w*|nő\b|nők\w*|férfi\w*|táncos\w*|szereplő\w*|modell\w*|színész\w*|girls?|boys?|dancers?|models?|actors?'


def performers(text):
    """How many people appear on screen besides the artist, from the owner's words ("2 lány", "három táncos")."""
    text = str(text or '').lower()
    total = 0
    for m in re.finditer(r'(\d+|' + '|'.join(NUMBER) + r')\s+(?:\w+\s+)?(' + PEOPLE + r')', text):
        n = m.group(1)
        total += int(n) if n.isdigit() else NUMBER[n]
    if not total and re.search(PEOPLE, text):
        total = 1
    return min(total, 30)


def missing_lines(clip):
    """Lines a real shoot needs that this budget lacks: the people the direction names, a camera. Shown to the owner,
    added only on their click (a plan made before 13 Nov had neither for the "2 lány" clip)."""
    lines = clip['budget'].get('lines') or []
    out = []
    cast = performers(' '.join(str(clip.get(k) or '') for k in ('direction', 'notes')))
    if cast and not any(l.get('category') == 'Szereplők' for l in lines):
        out.append(dict(id=new_id(), category='Szereplők', item='Színész / szereplő', qty=cast, unit='fő/nap', rate=LOW_RATES['Színész / szereplő'],
                        note=f'{cast} szereplő az irány szerint; ismerősnél 0 Ft'))
    if not any(l.get('category') == 'Technika' for l in lines):
        out.append(dict(id=new_id(), category='Technika', item='Kamera szett bérlés', qty=1, unit='nap', rate=LOW_RATES['Kamera szett bérlés'], note='Saját kamerával 0 Ft'))
    return out


def plan_lines(crew, needs, direction=''):
    """Budget lines for the plan: people and gear (each once), places, food, transport and post. Whoever appears on
    screen and a camera are always on it (13 Nov: the "2 lány" clip had neither, the total looked cheaper than it is)."""
    lines, seen = [], set()
    for c in crew:
        role = str(c.get('role') or '').strip()
        if not role or role in seen or SELF_ADDED.search(role):
            continue
        seen.add(role)
        rate = RATES.get(role) or next((v for k, v in RATES.items() if role.lower()[:6] in k.lower()), 50000)
        category = ('Szereplők' if re.search(r'színész|statiszta|táncos|szereplő', role, re.I) else
                    'Technika' if re.search(r'bérlés|szett|csomag|gimbal|stabiliz|füstgép|effekt', role, re.I) else 'Stáb')
        unit = 'nap'
        lines.append(dict(id=new_id(), category=category, item=role, qty=max(1, float(c.get('days') or 1)) * max(1, float(c.get('count') or 1)), unit=unit, rate=rate, note='AI-becslés'))
    for need in needs:
        kind = str(need.get('type') or '').lower()
        rate = next((v for k, v in LOCATION_DAY.items() if k in kind), 100000)
        lines.append(dict(id=new_id(), category='Helyszín', item=f"{need.get('type')} · {need.get('city') or 'Budapest'}", qty=max(1, float(need.get('days') or 1)), unit='nap', rate=rate, note='Becslés; a talált helyszín ára felülírja'))
    people = sum(float(c.get('count') or 1) for c in crew if not re.search(r'bérlés|szett|csomag|gimbal|stabiliz|füstgép|effekt|busz', str(c.get('role')), re.I)) or 4
    days = max([float(n.get('days') or 1) for n in needs] or [1])
    cast = performers(direction)
    if cast and not any(l['category'] == 'Szereplők' for l in lines):
        lines.append(dict(id=new_id(), category='Szereplők', item='Színész / szereplő', qty=cast * days, unit='fő/nap', rate=RATES['Színész / szereplő'],
                          note=f'{cast} szereplő az irány szerint; ismerősnél 0 Ft'))
        people += cast
    if not any(l['category'] == 'Technika' for l in lines):
        lines.append(dict(id=new_id(), category='Technika', item='Kamera szett bérlés', qty=days, unit='nap', rate=RATES['Kamera szett bérlés'],
                          note='Saját kamerával 0 Ft'))
    lines.append(dict(id=new_id(), category='Logisztika', item='Catering', qty=people * days, unit='fő/nap', rate=RATES['Catering (fő/nap)'], note='AI-becslés'))
    lines.append(dict(id=new_id(), category='Logisztika', item='Kisbusz / szállítás', qty=days, unit='nap', rate=RATES['Kisbusz / szállítás'], note='AI-becslés'))
    lines.append(dict(id=new_id(), category='Utómunka', item='Vágás és színkorrekció', qty=3, unit='nap', rate=(RATES['Vágó (napi)'] + RATES['Színkorrektor (napi)']) // 2, note='AI-becslés'))
    return lines


# ---------------------------------------------------------------- more concepts
CONCEPTS_SCHEMA = {'type': 'object', 'required': ['concepts'], 'properties': {'concepts': THINK_SCHEMA['properties']['concepts']}}


def more_concepts(s, pid, cid, focus=''):
    clip = load(s, pid, cid)
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    s.enqueue(agent[0], 'Videoklip · új koncepciók', 'assist', payload=dict(task='clip_concepts', project=pid, clip=cid, focus=str(focus)[:600], local_only=True))
    note(clip, 'Új koncepciókat kértél' + (': ' + focus[:80] if focus else ''))
    store(s, pid, clip)
    return dict(message='A Rendező új, eddigiektől eltérő koncepciókon gondolkodik.')


def run_concepts(s, job):
    """Three new concepts next to the existing ones; the chosen concept, story and board stay as they are."""
    p = json.loads(job['payload'])
    clip = load(s, p['project'], p['clip'])
    cap = clip['budget'].get('cap') or budget_cap(' '.join(str(clip.get(k) or '') for k in ('direction', 'notes')))
    s.job_stage(job['id'], 'model', 'A Rendező új koncepciókon gondolkodik')
    data = dict(song=dict(name=clip['song'].get('name'), duration_seconds=clip['song'].get('duration'), bpm=clip['song'].get('bpm'), parts=clip['song'].get('parts'),
                lyrics=(clip['song'].get('lyrics') or '')[:4000]), owner_direction=clip.get('direction'), owner_notes=(clip.get('notes') or '')[:2000],
                budget_ceiling_huf=cap, lenses=lenses(time.time() + 7), focus=p.get('focus') or '',
                existing_concepts_to_avoid=[dict(title=k.get('title'), logline=k.get('logline')) for k in clip.get('concepts', [])])
    system = ('You are a Hungarian music video director. Invent 3 NEW concepts for this song, each clearly different from existing_concepts_to_avoid '
              'and from each other. ' + CREATIVE + money_rules(cap) + 'Hungarian titles and text. If focus is given, follow it. Return JSON only.')
    answer = ask(s, system, data, CONCEPTS_SCHEMA, budget=300, temperature=1.0)
    clip = load(s, p['project'], p['clip'])
    fresh = [dict(k, title=hungarian_title(k['title'])) for k in answer.get('concepts') or [] if k.get('title') and hungarian_title(k['title']) not in {c.get('title') for c in clip['concepts']}]
    clip['concepts'] = clip['concepts'] + fresh
    note(clip, f'{len(fresh)} új koncepció')
    store(s, p['project'], clip)
    return f'{len(fresh)} új koncepció a(z) „{clip["title"]}” kliphez.'


# ---------------------------------------------------------------- pictures
def images(s, pid, cid, which='all'):
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    s.enqueue(agent[0], 'Videoklip · képek rajzolása', 'assist', payload=dict(task='clip_images', project=pid, clip=cid, which=which, local_only=True))
    return dict(message='A képek a helyi FLUX-szal készülnek (képenként kb. fél perc).')


def run_images(s, job):
    from design_studio import flux
    p = json.loads(job['payload'])
    pid = p['project']
    clip = load(s, pid, p['clip'])
    palette = ', '.join(clip.get('palette') or [])
    todo = []
    if p.get('which') in ('all', 'concepts'):
        todo += [('concepts', k.get('id') or k['title'], k.get('look_prompt') or k.get('logline'), 768, 512) for k in clip.get('concepts', []) if not k.get('artifact') and (k.get('look_prompt') or k.get('logline'))][:6 if p.get('which') == 'concepts' else 0]
    if p.get('which') in ('all', 'moodboard'):
        todo += [('moodboard', m['id'], m['prompt'], 768, 512) for m in clip.get('moodboard', []) if not m.get('artifact') and m.get('prompt')]
    if p.get('which') in ('all', 'storyboard'):
        todo += [('storyboard', sh['id'], sh.get('image_prompt') or sh.get('description'), 768, 432) for sh in clip.get('storyboard', []) if not sh.get('artifact') and (sh.get('image_prompt') or sh.get('description'))]
    out = s.safe_path(pid, 'clips/images')
    out.mkdir(parents=True, exist_ok=True)
    made = 0
    for n, (where, iid, prompt, w, h) in enumerate(todo[:16], 1):
        if s.cancelled(job['id']):
            break
        s.job_stage(job['id'], 'image', f'FLUX · {where} {n}/{min(16, len(todo))}')
        target = out / f'{clip["id"]}-{iid}.png'
        flux(s, image_prompt(clip, where, prompt), w, h, int(time.time()) % 100000, target, steps=6)
        aid = uuid.uuid4().hex
        s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)', (aid, pid, f'{clip["title"]} · {where} · {n}.png', str(target), 'image', time.time(), job['id']))
        s.db.commit()
        clip = load(s, pid, p['clip'])
        for item in clip.get(where, []):
            if item.get('id') == iid or (where == 'concepts' and item.get('title') == iid):
                item['artifact'] = aid
        store(s, pid, clip)
        made += 1
    clip = load(s, pid, p['clip'])
    note(clip, f'{made} kép elkészült')
    store(s, pid, clip)
    if len(todo) > 16 and made and not s.cancelled(job['id']):
        # One job draws at most 16; the rest follows in the next one (13 Nov: two "Slow down" frames were left empty).
        agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
        s.enqueue(agent[0], 'Videoklip · képek rajzolása (folytatás)', 'assist', payload=dict(task='clip_images', project=pid, clip=p['clip'], which=p.get('which') or 'all', local_only=True))
    return f'{made} kép elkészült a videoklip-tervhez.'


def image_prompt(clip, where, prompt):
    """A mood picture, not a stock photo: the shot itself, then the concept's look, the song's feeling and the palette, and a
    photographic finish (owner 12 Nov: "nem elég jó hangulatot közvetítenek")."""
    concept = (clip.get('concepts') or [{}])[clip.get('chosen') or 0] if clip.get('concepts') else {}
    bpm = clip.get('song', {}).get('bpm') or 0
    tempo = 'slow, sensual, unhurried' if bpm and bpm < 96 else 'driving, energetic' if bpm and bpm > 125 else 'rhythmic, flowing'
    mood = clip.get('mood') or ''
    palette = ', '.join(clip.get('palette') or [])
    finish = ('cinematic film still from a music video, shot on 35mm, anamorphic lens, shallow depth of field, natural film grain, '
              'motivated practical light, rich colour grading, atmospheric haze, emotional, editorial photography'
              if where != 'storyboard' else 'storyboard keyframe, cinematic composition, music video shot, clear staging')
    look = '' if where == 'concepts' else concept.get('look_prompt') or ''
    return (f"{prompt}. Mood: {mood}. Feeling: {tempo}. Look: {look}. "
            f"Colour palette: {palette}. {finish}. No text, no letters, no logos, no watermark.")[:1500]


MOODS_SCHEMA = {'type': 'object', 'required': ['moodboard'], 'properties': {'moodboard': {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': {
    'type': 'object', 'required': ['prompt', 'note'], 'properties': {'prompt': {'type': 'string'}, 'note': {'type': 'string'}}}}}}


def more_moods(s, pid, cid, prompt='', count=3):
    """More mood pictures for the chosen concept, steered by the owner's own prompt (owner 12 Nov)."""
    clip = load(s, pid, cid)
    count = max(1, min(6, int(count or 3)))
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    s.enqueue(agent[0], 'Videoklip · új moodboard-képek', 'assist', payload=dict(task='clip_moods', project=pid, clip=cid, prompt=str(prompt or '')[:600], count=count, local_only=True))
    note(clip, f'{count} új moodboard-képet kértél' + (': ' + str(prompt)[:80] if prompt else ''))
    store(s, pid, clip)
    return dict(message=f'{count} új moodboard-kép készül' + (' a kérésed szerint.' if prompt else ' a koncepcióhoz.'))


def run_moods(s, job):
    p = json.loads(job['payload'])
    clip = load(s, p['project'], p['clip'])
    concept = (clip.get('concepts') or [{}])[clip.get('chosen') or 0] if clip.get('concepts') else {}
    s.job_stage(job['id'], 'model', 'A Rendező új moodboard-képeket ír')
    answer = ask(s, 'You are a music video director building a moodboard. Write exactly count new English image prompts that show the MOOD of this '
                    'concept, different from existing_prompts. owner_request is what the owner wants to see: follow it closely if given. Each prompt names '
                    'the subject, action, place, time of day, light source, colours and lens; note: one Hungarian line. Return JSON only.',
                 dict(count=p.get('count', 3), owner_request=p.get('prompt') or '', concept={k: concept.get(k) for k in ('title', 'logline', 'look')},
                      mood=clip.get('mood'), palette=clip.get('palette'), owner_direction=clip.get('direction'),
                      existing_prompts=[m.get('prompt') for m in clip.get('moodboard', []) if m.get('prompt')][:12]),
                 MOODS_SCHEMA, budget=200, temperature=.9, length=1800)
    fresh = [dict(id=new_id(), prompt=m['prompt'], note=m.get('note', ''), artifact=None, owner=True, asked=p.get('prompt') or '')
             for m in (answer.get('moodboard') or [])[:p.get('count', 3)] if m.get('prompt')]
    if not fresh and p.get('prompt'):
        fresh = [dict(id=new_id(), prompt=p['prompt'], note='A te promptod', artifact=None, owner=True)]
    clip = load(s, p['project'], p['clip'])
    clip['moodboard'] = [m for m in clip.get('moodboard', []) if m.get('prompt')] + fresh
    store(s, p['project'], clip)
    # The pictures right after, in the same job, so they appear together.
    run_images(s, dict(job, payload=json.dumps(dict(task='clip_images', project=p['project'], clip=p['clip'], which='moodboard'))))
    return f'{len(fresh)} új moodboard-kép.'


# ---------------------------------------------------------------- Hungarian locations
PRICE = re.compile(r'(\d[\d\s.]{2,9})\s*(?:Ft|HUF|forint)', re.I)


def locations(s, pid, cid):
    clip = load(s, pid, cid)
    if not clip.get('location_needs'):
        raise ValueError('Előbb kérj tervet a Rendezőtől, vagy írd be, milyen helyszín kell.')
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    s.enqueue(agent[0], 'Videoklip · helyszínkeresés', 'assist', payload=dict(task='clip_locations', project=pid, clip=cid, local_only=True))
    return dict(message='Magyarországi helyszíneket keresek a weben.')


def run_locations(s, job):
    import research
    p = json.loads(job['payload'])
    clip = load(s, p['project'], p['clip'])
    found = [l for l in clip.get('locations', []) if l.get('owner') or l.get('picked')]
    seen = {l.get('url') for l in found}
    for i, need in enumerate(clip.get('location_needs', [])[:5], 1):
        city = need.get('city') or 'Budapest'
        query = f"forgatási helyszín bérlés {need.get('type')} {city}"
        s.job_stage(job['id'], 'research', f'Helyszínkeresés {i}: {query}')
        try:
            results = research.search(query, 6, s.root).get('results', [])
        except (ValueError, OSError):
            results = []
        for r in results[:4]:
            url = r.get('url')
            if not url or url in seen:
                continue
            seen.add(url)
            text = ' '.join(str(r.get(k) or '') for k in ('title', 'content'))
            price = None
            m = PRICE.search(text)
            if m:
                try:
                    price = int(re.sub(r'\D', '', m.group(1)))
                except ValueError:
                    price = None
            found.append(dict(id=new_id(), name=str(r.get('title') or url)[:140], place=city, type=need.get('type'), need=need.get('description'),
                              url=url, snippet=str(r.get('content') or '')[:400], price_day=price, source='webkeresés', note=''))
    clip = load(s, p['project'], p['clip'])
    clip['locations'] = found
    note(clip, f'{len(found)} helyszínjelölt a webről')
    store(s, p['project'], clip)
    return f'{len(found)} helyszínjelölt.'


def pick_location(s, pid, cid, lid):
    """A picked location's price (when known) replaces the estimate of the matching budget line."""
    clip = load(s, pid, cid)
    loc = next((l for l in clip.get('locations', []) if l.get('id') == lid), None)
    if not loc:
        raise ValueError('Ismeretlen helyszín.')
    loc['picked'] = not loc.get('picked')
    if loc['picked'] and loc.get('price_day'):
        for line in clip['budget']['lines']:
            if line.get('category') == 'Helyszín' and str(loc.get('type') or '').lower()[:5] in str(line.get('item') or '').lower():
                line.update(rate=loc['price_day'], note='Ár: ' + loc['name'][:60])
                break
    store(s, pid, clip)
    return dict(clip=clip, budget=budget(clip))


# ---------------------------------------------------------------- entry points
def snapshot(s, pid, cid=None):
    clips = listing(s, pid)
    current = None
    if cid or clips:
        try:
            current = load(s, pid, cid or clips[0]['id'])
        except ValueError:
            current = load(s, pid, clips[0]['id']) if clips else None
    audio = [dict(id=r['id'], name=r['name']) for r in s.rows("SELECT id,name FROM artifacts WHERE project=? AND kind='audio' ORDER BY created DESC LIMIT 40", (pid,))]
    running = [dict(r) for r in s.rows("SELECT id,status,json_extract(payload,'$.task') task,json_extract(payload,'$.clip') clip FROM jobs WHERE kind='assist' "
                                       "AND status IN ('queued','running') AND json_extract(payload,'$.task') LIKE 'clip_%' AND json_extract(payload,'$.project')=?", (pid,))]
    failed = []
    if current:
        failed = [dict(r) for r in s.rows("SELECT id,json_extract(payload,'$.task') task,error,finished FROM jobs WHERE kind='assist' AND status='failed' "
                                          "AND json_extract(payload,'$.task') LIKE 'clip_%' AND json_extract(payload,'$.clip')=? AND finished>? ORDER BY finished DESC LIMIT 3",
                                          (current['id'], max(time.time() - 7200, current.get('updated', 0) - 5)))]
    return dict(clips=clips, clip=current, budget=budget(current) if current else None, missing=missing_lines(current) if current else [], shooting=shooting_order(current.get('storyboard'), current.get('location_needs')) if current else [], audio=audio, running=running, failed=failed, rates=RATES, categories=CATEGORIES)


def dispatch(s, pid, op, args=None):
    args = args or {}
    if op == 'clip_snapshot':
        return snapshot(s, pid, args.get('clip'))
    if op == 'clip_create':
        title = str(args.get('title') or '').strip() or 'Új videoklip'
        # An untouched empty clip is reused instead of piling up "Új videoklip" entries (owner had three).
        empty = next((c for c in (load(s, pid, x['id']) for x in listing(s, pid)) if not c['song'].get('artifact') and not c.get('direction')
                      and not c.get('concepts') and not c.get('notes') and c.get('title') == 'Új videoklip'), None)
        clip = empty or blank(title)
        clip['title'] = title[:120]
        store(s, pid, clip)
        return snapshot(s, pid, clip['id'])
    if op == 'clip_full':
        return think(s, pid, args.get('clip'), str(args.get('focus') or ''), chain=True) | dict(message='A Rendező végigtervezi a klipet, utána magától megrajzolja a képeket és helyszínt keres.')
    if op == 'clip_plan_concept':
        clip = load(s, pid, args.get('clip'))
        concept = next((k for k in clip.get('concepts', []) if k.get('id') == args.get('concept')), None)
        if not concept:
            raise ValueError('Ismeretlen koncepció.')
        # Everything switches to the new concept at once (owner 12 Nov: "nem látok változást"): the old plan becomes a version,
        # the concept leads, and the story, moodboard and storyboard wait for the director's new plan.
        remember(clip)
        clip['concepts'] = [concept] + [k for k in clip['concepts'] if k is not concept]
        clip['chosen'] = 0
        clip['story'] = dict(logline=concept.get('logline', ''), synopsis='', beats=[])
        clip['moodboard'] = [m for m in clip.get('moodboard', []) if m.get('owner')]
        clip['storyboard'] = []
        clip['locations'] = [l for l in clip.get('locations', []) if l.get('owner')]
        clip['replanning'] = concept['title']
        store(s, pid, clip)
        think(s, pid, clip['id'], 'Tervezz mindent ebből a koncepcióból: ' + concept['title'], chain=True, concept=concept)
        return dict(message=f'A Rendező a „{concept["title"]}” koncepcióból újratervezi a sztorit, a moodboardot, a storyboardot, a helyszíneket és a költségvetést; a mostani terv változatként megmarad.')
    if op == 'clip_fit':
        clip = load(s, pid, args.get('clip'))
        done = fit_budget(clip)
        note(clip, 'Keretbe illesztve: ' + ', '.join(done) if done else 'A költségvetés már a kereten belül van')
        store(s, pid, clip)
        return dict(snapshot(s, pid, clip['id']), message=('Keretbe illesztve: ' + ', '.join(done)) if done else 'Már a kereten belül van.')
    if op == 'clip_budget_fill':
        clip = load(s, pid, args.get('clip'))
        added = missing_lines(clip)
        clip['budget']['lines'] += added
        note(clip, 'Pótolt tételek: ' + ', '.join(l['item'] for l in added) if added else 'Nem hiányzott tétel')
        store(s, pid, clip)
        return snapshot(s, pid, clip['id'])
    if op == 'clip_restore':
        return restore(s, pid, args.get('clip'), args.get('version'))
    if op == 'clip_export':
        return export(s, pid, args.get('clip'))
    if op == 'clip_save':
        return save(s, pid, args.get('clip'), args.get('patch'))
    if op == 'clip_archive':
        clip = load(s, pid, args.get('clip'))
        clip['archived'] = not clip.get('archived')
        store(s, pid, clip)
        return snapshot(s, pid)
    if op == 'clip_song':
        attach_song(s, pid, args.get('clip'), args.get('artifact'))
        return snapshot(s, pid, args.get('clip'))
    if op == 'clip_think':
        return think(s, pid, args.get('clip'), str(args.get('focus') or ''))
    if op == 'clip_concepts':
        return more_concepts(s, pid, args.get('clip'), str(args.get('focus') or ''))
    if op == 'clip_images':
        return images(s, pid, args.get('clip'), args.get('which') if args.get('which') in ('all', 'moodboard', 'storyboard', 'concepts') else 'all')
    if op == 'clip_moods':
        return more_moods(s, pid, args.get('clip'), args.get('prompt') or '', args.get('count') or 3)
    if op == 'clip_locations':
        return locations(s, pid, args.get('clip'))
    if op == 'clip_pick_location':
        return pick_location(s, pid, args.get('clip'), args.get('location'))
    raise ValueError('Ismeretlen videoklip-művelet.')


def run_job(s, job):
    task = json.loads(job['payload']).get('task')
    try:
        return run_task(s, job, task)
    except Exception as error:
        from execution_queue import DeferredExecution
        if isinstance(error, DeferredExecution):
            raise
        p = json.loads(job['payload'])
        try:
            clip = load(s, p['project'], p['clip'])
            clip['replanning'] = None
            note(clip, 'Hiba: ' + str(error)[:200])
            store(s, p['project'], clip)
        except Exception:
            pass
        raise


def run_task(s, job, task):
    return {'clip_song': analyse_song, 'clip_think': run_think, 'clip_concepts': run_concepts, 'clip_moods': run_moods, 'clip_images': run_images, 'clip_locations': run_locations}[task](s, job)


# ---------------------------------------------------------------- the main assistant's handle
def find_clip(s, pid, name):
    from model_router import normalized
    clips = listing(s, pid)
    if not clips:
        raise ValueError('A Videoklip stúdióban még nincs klip.')
    key = normalized(str(name or '')).strip()
    if not key:
        return clips[0]
    exact = [c for c in clips if normalized(c.get('title') or '') == key]
    near = exact or [c for c in clips if key in normalized(c.get('title') or '') or normalized(c.get('title') or '') in key]
    if not near:
        raise ValueError('Nem találom ezt a klipet. A klipjeid: ' + ', '.join('„' + (c.get('title') or 'Névtelen') + '”' for c in clips[:12]))
    return near[0]


def act(s, a):
    """{"type":"videoklip","op":...,"clip":"title","text":"..."} from the main chat (owner, 12 Nov)."""
    pid = ensure(s)
    op = a.get('op')
    text = str(a.get('text') or '').strip()
    if op == 'list':
        return dict(clips=[dict(title=c['title'], song=c.get('song'), total=c.get('total')) for c in listing(s, pid)])
    if op == 'create':
        clip = blank(text or str(a.get('clip') or 'Új videoklip'))
        store(s, pid, clip)
        return dict(message=f'Létrehoztam a(z) „{clip["title"]}” klipet a Videoklip stúdióban.', clip=clip['title'])
    clip = find_clip(s, pid, a.get('clip'))
    cid, title = clip['id'], clip['title']
    if op == 'concepts':
        more_concepts(s, pid, cid, text)
        return dict(message=f'A Rendező új koncepciókon dolgozik a(z) „{title}” kliphez; pár perc múlva a Koncepció fülön lesznek.')
    if op == 'think':
        think(s, pid, cid, text)
        return dict(message=f'A Rendező újragondolja a(z) „{title}” klipet' + (f' ({text[:80]})' if text else '') + '.')
    if op == 'full':
        think(s, pid, cid, text, chain=True)
        return dict(message=f'A Rendező végigtervezi a(z) „{title}” klipet, utána megrajzolja a képeket és helyszínt keres.')
    if op == 'export':
        r = export(s, pid, cid)
        return dict(message=f'Elkészült a(z) „{title}” gyártási dossziéja; az Alkotások között és a Videoklip stúdióban is megnyithatod.', artifact=r['artifact'])
    if op == 'images':
        images(s, pid, cid, 'all')
        return dict(message=f'A(z) „{title}” moodboard- és storyboard-képei készülnek.')
    if op == 'locations':
        locations(s, pid, cid)
        return dict(message=f'Helyszíneket keresek a(z) „{title}” kliphez.')
    if op == 'direction':
        full = load(s, pid, cid)
        save(s, pid, cid, dict(direction=(full.get('direction') + '\n' if full.get('direction') else '') + text))
        return dict(message=f'Hozzáírtam az irányhoz a(z) „{title}” klipnél.')
    if op == 'note':
        full = load(s, pid, cid)
        save(s, pid, cid, dict(notes=(full.get('notes') + '\n' if full.get('notes') else '') + text))
        return dict(message=f'Felírtam a jegyzetek közé a(z) „{title}” klipnél.')
    if op == 'budget':
        cap = budget_cap(text) or budget_cap(text + ' Ft')
        if not cap:
            raise ValueError('Írd meg a keretet forintban, például „max 250 ezer Ft”.')
        full = load(s, pid, cid)
        full['budget']['cap'] = cap
        fitted = fit_budget(full)
        store(s, pid, full)
        return dict(message=f'A(z) „{title}” kerete {cap:,} Ft'.replace(',', ' ') + ('; ' + ', '.join(fitted) if fitted else '.'))
    raise ValueError('Ismeretlen videoklip-művelet.')


OP_WORDS = (('full', r'teljes(?:en)?\b.*terv|tervezd meg teljesen|mindent tervezz'), ('export', r'doss?zi[ée]|export'), ('concepts', r'koncepci|ötlet'), ('locations', r'helysz[ií]n'), ('budget', r'\bkeret|k[öo]lts[ée]gvet|budget|\bmax(?:imum)?\b.*\d'),
            ('images', r'\bk[ée]p(?:ek|et)?\b|moodboard|storyboard|rajzol'), ('note', r'jegyzet|[ií]rd fel|jegyezd'), ('direction', r'\bir[aá]ny'),
            ('think', r'gondold|tervezd|[uú]jra|dolgozd ki|sztori|t[öo]rt[ée]net'), ('list', r'milyen klip|klipjeim|list[aá]zd'))


def route(s, text):
    """A main-chat sentence that names one of the clips (or says videoklip) and what to do with it, as a videoklip action.
    The local model answered "keress több koncepciót a Slow down kliphez" in prose instead of using the studio (12 Nov)."""
    from model_router import normalized
    row = s.db.execute('SELECT id FROM projects WHERE kind=?', (KIND,)).fetchone()
    if not row:
        return None
    p = normalized(text or '')
    clips = listing(s, row[0])
    named = next((c for c in sorted(clips, key=lambda c: -len(c.get('title') or '')) if len(normalized(c.get('title') or '')) >= 3
                  and normalized(c.get('title') or '') not in ('uj videoklip',) and normalized(c.get('title') or '') in p), None)
    if not named and not re.search(r'videokli?p|\bklip\w*', p):
        return None
    op = next((o for o, pattern in OP_WORDS if re.search(pattern, p)), None)
    if not op:
        return None
    return dict(type='videoklip', op=op, clip=named['title'] if named else '', text=text.strip()[:1200])


# ---------------------------------------------------------------- production dossier
TIME = re.compile(r'(\d+):(\d{1,2})\s*[-–]\s*(\d+):(\d{1,2})')


def fit_beats(beats, duration):
    """Story beats inside the song, one after the other (13 Nov: a 2:32 song had beats up to 3:52, overlapping)."""
    if not duration or not beats:
        return beats
    spans = []
    for b in beats:
        m = TIME.search(str(b.get('time') or ''))
        spans.append((int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])) if m else None)
    ends = [e for s_e in spans if s_e for e in s_e[1:]]
    if not ends:
        return beats
    k = float(duration) / max(ends)
    if k <= 1 / .85:
        k = min(1., k)        # a story that ends before 85% of the song is stretched to its end (13 Nov: 1:52 of a 2:32 song)
    clock = lambda x: f'{int(x) // 60}:{int(x) % 60:02d}'
    out, last = [], 0
    for b, span in zip(beats, spans):
        if not span:
            out.append(b)
            continue
        start = max(last, round(span[0] * k))
        end = min(round(float(duration)), max(start + 1, round(span[1] * k)))
        out.append(dict(b, time=f'{clock(start)}-{clock(end)}'))
        last = end
    if k > 1 and out and TIME.search(str(out[-1].get('time') or '')):
        m = TIME.search(out[-1]['time'])
        out[-1] = dict(out[-1], time=f'{m[1]}:{m[2]}-{clock(round(float(duration)))}')
    return out


OUTDOOR = re.compile(r'\b(utc\w*|tet\w*|park\w*|erd\w*|kint\w*|kül\w*|street|roof\w*|outdoor\w*|híd\w*|part\w*|mező\w*|tó\b|folyó\w*)', re.I)


def stems(text):
    return {w[:5] for w in re.findall(r'[a-záéíóöőúüű]{4,}', str(text or '').lower())}


def shooting_order(storyboard, needs=()):
    """The storyboard regrouped the way a crew shoots it: by real place (the clip's location needs), in the order the
    places first appear, each with its frame numbers, camera moves and the finished screen time it has to deliver. The
    shot's own location text is a set description ("polcok közötti tér"), so it is matched to the needs by words; an
    outdoor word sends an unmatched shot to the outdoor place, anything else to the main place."""
    places = [' '.join(f"{n.get('type') or ''} {('· ' + n['city']) if n.get('city') else ''}".split()) for n in needs or [] if n.get('type')]
    cities = set().union(*[stems(n.get('city')) for n in needs or []] or [set()]) | {'budap', 'magya'}
    words = [stems(f"{n.get('type')} {n.get('description') or ''}") - cities for n in needs or [] if n.get('type')]
    kind = lambda text: (OUTDOOR.search(text).group(0)[:3].lower() if OUTDOOR.search(text) else None)
    groups = {}
    for i, sh in enumerate(storyboard or [], 1):
        text = f"{sh.get('location') or ''} {sh.get('description') or ''}"
        if places:
            score = [len((stems(text) - cities) & w) for w in words]
            best = max(range(len(places)), key=lambda k: score[k])
            place = places[best]
            if not score[best]:
                # No shared word: an outdoor shot goes to an outdoor place of the same kind (street to street, not to a roof).
                same = next((p for p in places if kind(text) and kind(p) == kind(text)), None)
                place = same or ('Külső helyszín (utca / szabad tér)' if kind(text) else places[0])
        else:
            place = 'Külső helyszín' if OUTDOOR.search(text) else 'Fő helyszín'
        g = groups.setdefault(place, dict(place=place, shots=[], seconds=0., cameras=[]))
        g['shots'].append(i)
        try:
            g['seconds'] += max(0., float(sh.get('end') or 0) - float(sh.get('start') or 0))
        except (TypeError, ValueError):
            pass
        camera = ' '.join(str(sh.get('camera') or '').split())[:50]
        if camera and camera not in g['cameras']:
            g['cameras'].append(camera)
    for g in groups.values():
        g['seconds'] = round(g['seconds'], 1)
    return list(groups.values())


def embedded(path, edge=900):
    """A picture inside the dossier itself, scaled down, so the file can be sent to the crew as it is."""
    import base64
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as folder:
            small = Path(folder) / 'p.jpg'
            subprocess.run(['/usr/bin/sips', '-Z', str(edge), '-s', 'format', 'jpeg', '-s', 'formatOptions', '72', str(path), '--out', str(small)],
                           capture_output=True, timeout=60, check=True)
            return 'data:image/jpeg;base64,' + base64.b64encode(small.read_bytes()).decode()
    except (OSError, subprocess.SubprocessError):
        return None


def export(s, pid, cid):
    """One HTML page for the crew: concept, story, beats, storyboard with frames, places, crew and budget, notes."""
    import html
    clip = load(s, pid, cid)
    b = budget(clip)
    esc = lambda x: html.escape(str(x or ''))
    paths = {r['id']: r['path'] for r in s.rows("SELECT id,path FROM artifacts WHERE project=? AND kind='image'", (pid,))}
    cache = {}

    def pic(aid):
        if aid not in paths:
            return ''
        if aid not in cache:
            cache[aid] = embedded(paths[aid]) or 'file://' + paths[aid]
        return f'<img src="{html.escape(cache[aid])}">'
    tc = lambda x: f'{int(float(x or 0)) // 60}:{int(float(x or 0)) % 60:02d}'
    k = (clip.get('concepts') or [{}])[clip.get('chosen') or 0] if clip.get('concepts') else {}
    parts = [f'<h1>{esc(clip["title"])}</h1><p class="m">{esc(clip.get("artist"))} · {esc(clip["song"].get("name"))} · {tc(clip["song"].get("duration"))} · {esc(clip["song"].get("bpm"))} BPM</p>',
             f'<h2>Koncepció: {esc(k.get("title"))}</h2><p>{esc(k.get("logline"))}</p><p class="m">{esc(k.get("look"))}</p>',
             '<div class="pal">' + ''.join(f'<i style="background:{esc(c)}"></i>' for c in clip.get('palette') or []) + '</div>',
             f'<h2>Sztori</h2><p><b>{esc(clip["story"].get("logline"))}</b></p><p>{esc(clip["story"].get("synopsis"))}</p>',
             '<table>' + ''.join(f'<tr><td>{esc(x.get("time"))}</td><td>{esc(x.get("text"))}</td></tr>' for x in fit_beats(clip['story'].get('beats') or [], clip['song'].get('duration'))) + '</table>',
             '<h2>Moodboard</h2><div class="grid">' + ''.join(f'<figure>{pic(m.get("artifact"))}<figcaption>{esc(m.get("note") or m.get("prompt"))}</figcaption></figure>' for m in clip.get('moodboard') or []) + '</div>',
             '<h2>Storyboard</h2>' + ''.join(f'<div class="shot">{pic(sh.get("artifact"))}<div><b>#{i + 1} · {tc(sh.get("start"))}–{tc(sh.get("end"))} · {esc(sh.get("shot"))} · {esc(sh.get("camera"))}</b>'
                                             f'<p>{esc(sh.get("description"))}</p><p class="m">{esc(sh.get("location"))} {esc(sh.get("note"))}</p></div></div>' for i, sh in enumerate(clip.get('storyboard') or [])),
             '<h2>Forgatási sorrend</h2><p class="m">Helyszínenként: így egy helyen minden beállítás egyszerre felvehető.</p><table>' +
             ''.join(f'<tr><td><b>{esc(g["place"])}</b></td><td>#{", #".join(str(n) for n in g["shots"])}</td><td>{esc(" · ".join(g["cameras"]))}</td>'
                     f'<td class="r">{tc(g["seconds"])}</td></tr>' for g in shooting_order(clip.get('storyboard'), clip.get('location_needs'))) + '</table>',
             '<h2>Helyszínek</h2><ul>' + ''.join(f'<li><b>{esc(l.get("name"))}</b> · {esc(l.get("place"))} · {esc(l.get("url"))} {("· " + esc(l.get("price_day")) + " Ft/nap") if l.get("price_day") else ""} {esc(l.get("note"))}</li>'
                                                for l in clip.get('locations') or [] if l.get('picked')) + '</ul>',
             '<h2>Költségvetés</h2><table>' + ''.join(f'<tr><td>{esc(l.get("category"))}</td><td>{esc(l.get("item"))}</td><td>{esc(l.get("qty"))} {esc(l.get("unit"))}</td><td class="r">{round(float(l.get("qty") or 0) * float(l.get("rate") or 0)):,} Ft</td></tr>'.replace(',', ' ')
                                                  for l in clip['budget'].get('lines') or []) + f'<tr><td colspan=3><b>Összesen, tartalékkal</b></td><td class="r"><b>{b["total"]:,} Ft</b></td></tr></table>'.replace(',', ' '),
             f'<h2>Jegyzetek</h2><pre>{esc(clip.get("notes"))}</pre>']
    style = ('body{font:15px/1.5 -apple-system,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#1d1b26}h1{font-size:34px;margin:0}'
             'h2{margin-top:34px;border-bottom:1px solid #ddd;padding-bottom:6px}.m{color:#777}.pal i{display:inline-block;width:36px;height:36px;border-radius:8px;margin-right:6px}'
             'table{border-collapse:collapse;width:100%}td{border-bottom:1px solid #eee;padding:6px 8px;vertical-align:top}.r{text-align:right}'
             '.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}figure{margin:0}img{width:100%;border-radius:8px}figcaption{font-size:12px;color:#777}'
             '.shot{display:grid;grid-template-columns:260px 1fr;gap:14px;margin:12px 0}pre{white-space:pre-wrap;font:inherit}@media print{h2{break-after:avoid}.shot{break-inside:avoid}}')
    out = s.safe_path(pid, f'clips/{clip["id"]}-dosszie.html')
    out.write_text(f'<!doctype html><meta charset="utf-8"><title>{esc(clip["title"])} · gyártási dosszié</title><style>{style}</style>' + ''.join(parts), encoding='utf-8')
    row = s.db.execute('SELECT id FROM artifacts WHERE project=? AND path=?', (pid, str(out))).fetchone()
    aid = row[0] if row else uuid.uuid4().hex
    if not row:
        s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)', (aid, pid, f'{clip["title"]} · gyártási dosszié.html', str(out), 'text', time.time(), 'clip-export'))
        s.db.commit()
    return dict(artifact=aid, message='A gyártási dosszié elkészült; megnyitom.')
