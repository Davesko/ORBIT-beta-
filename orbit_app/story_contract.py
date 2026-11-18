"""Final, deterministic story/entity contract. No model calls or production writes."""
import hashlib
import json
import re


STORY_FIELDS = ('title', 'hook', 'premise', 'goal', 'mission', 'question', 'resolution',
                'ending', 'conditions', 'chapters', 'places', 'support')


def digest(plan, shots=None):
    body = {k: plan.get(k) for k in STORY_FIELDS}
    if shots is not None:
        body['narration'] = [x.get('say', '') for x in shots]
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def reconcile(shots, plan):
    """Preserve mandatory entities and typed objects after all legacy editorial passes."""
    premise = ' '.join(str(plan.get(k) or '') for k in ('title', 'premise', 'hook'))
    dog = bool(re.search(r'\b(dog|dane|puppy)\b', premise, re.I))
    people = re.search(r'\b(\d+)\s+(people|visitors|swimmers)\b', premise, re.I)
    crowd_total = int(people.group(1)) if people else 0
    elevator = bool(re.search(r'\belevator|\blift\b', premise, re.I))
    manifest = []
    if dog:
        manifest.append(dict(id='story_dog', kind='dog'))
    if crowd_total > 1:
        manifest.append(dict(id='story_crowd', kind='person', total=crowd_total))
    for shot in shots:
        text = shot.get('say', '')
        actors = shot.setdefault('actors', [])
        main = next((a for a in actors if a.get('who') == 'main'), None)
        kind = shot.get('kind')
        if dog and kind in ('wide', 'medium', 'top'):
            if not any(a.get('who') == 'extra:dog' for a in actors):
                x = .72 if not main or main.get('x', .3) < .5 else .25
                actors.append(dict(who='extra:dog', entity_id='story_dog', action='idle',
                                   expression='neutral', prop='none', x=x))
        if crowd_total > 1 and kind in ('wide', 'medium', 'top', 'crowd') and re.search(
                r'crowd|people|visitors|swimmers|they |queue|line|last person', text, re.I):
            # A representative crowd, explicitly distinguished from the narrative total.
            shot['crowd'] = dict(kind='person', count=min(24, crowd_total), total=crowd_total,
                                 entity_id='story_crowd', action='walk' if re.search(r'move|walk|outside', text, re.I) else 'idle',
                                 avoid=[a.get('x', .5) for a in actors])
            if kind == 'medium':
                shot['kind'] = 'wide'
        if elevator:
            shot['moving'] = [m for m in shot.get('moving', []) if not (
                m.get('kind') == 'vehicle' and re.search(r'\bcar\b', m.get('what', ''), re.I)
                and not re.search(r'road|street|truck|taxi', text, re.I))]
        if not main:
            continue
        # The instrument is not the object pointed AT.
        if re.search(r'point\w* (the )?(light|flashlight|torch)', text, re.I):
            main.update(action='point', prop='flashlight')
            main.pop('tool', None)
        if re.search(r'\b(fire )?hose\b', text, re.I) and re.search(r'\byou\b', text, re.I):
            main['prop'] = 'hose'
            main.pop('tool', None)
        if re.search(r'\byou\s+(?:\w+ly\s+)?(press|push|tap)\b[^.!?]*\bbutton\b', text, re.I):
            main.update(action='reach', prop='none')
            main.pop('tool', None)
            shot['kind'] = 'medium'
            shot['controlled'] = dict(action='press_button', target='button:' + shot.get('place', 'room'),
                                      actor='main', state_before='off', state_after='on')
        elif re.search(r'\byou\s+(?:\w+ly\s+)?(turn|crank|rotate)\b[^.!?]*\b(wheel|valve|dial)\b', text, re.I):
            main.update(action='crank', prop='none')
            main.pop('tool', None)
            shot['kind'] = 'medium'
            shot['controlled'] = dict(action='turn_control', target='wheel:' + shot.get('place', 'room'),
                                      actor='main', delta_deg=35.)
    plan['entities'] = manifest
    repair_clock(shots, plan)
    return shots


def repair_clock(shots, plan):
    """Explicit narrative anchors only; never fabricate time from a shot index."""
    mission = str(plan.get('mission') or '')
    m = re.search(r'\b(\d+)\s+(seconds?|minutes?|hours?)\b', mission, re.I)
    total = int(m.group(1)) * {'s': 1, 'm': 60, 'h': 3600}[m.group(2)[0].lower()] if m else None
    remaining = total
    floor = None
    for shot in shots:
        text = shot.get('say', '')
        left = re.search(r'\b(\d+)\s+(seconds?|minutes?|hours?)\s+(remaining|left)\b', text, re.I)
        elapsed = re.search(r'\b(minute|hour|second)\s+(\d+)\b', text, re.I)
        reset = re.search(r'\byou have\s+(\d+)\s+(seconds?|minutes?|hours?)\b', text, re.I)
        if reset:
            remaining = int(reset.group(1)) * {'s': 1, 'm': 60, 'h': 3600}[reset.group(2)[0].lower()]
        if left:
            remaining = int(left.group(1)) * {'s': 1, 'm': 60, 'h': 3600}[left.group(2)[0].lower()]
        elif elapsed and total is not None:
            remaining = max(0, total - int(elapsed.group(2)) * {'s': 1, 'm': 60, 'h': 3600}[elapsed.group(1)[0].lower()])
        f = re.search(r'\bfloor\s+(\d+)\b', text, re.I)
        if f:
            floor = int(f.group(1))
        if total is not None and remaining is not None:
            shot['hud'] = ('MINUTES LEFT: ' + str(remaining // 60) if remaining >= 60 and remaining % 60 == 0
                           else 'SECONDS LEFT: ' + str(remaining))
        elif floor is not None:
            shot['hud'] = 'FLOOR ' + str(floor)


def problems(plan, shots):
    errors = []
    text = ' '.join(s.get('say', '') for s in shots)
    for entity in plan.get('entities', []):
        if entity['kind'] == 'dog' and not any(a.get('entity_id') == entity['id'] for s in shots for a in s.get('actors', [])):
            errors.append('A történet kutyája hiányzik a képi tervből.')
        if entity.get('total') and not any(s.get('crowd', {}).get('entity_id') == entity['id'] for s in shots):
            errors.append('A történet tömege hiányzik a képi tervből.')
    floor = None
    for s in shots:
        line = s.get('say', '')
        f = re.search(r'\bfloor\s+(\d+)\b', line, re.I)
        if f:
            floor = int(f.group(1))
        if floor is not None and floor > 1 and re.search(r'one (final |last |more )?floor', line, re.I) and re.search(r'lobby|ground floor', line, re.I):
            errors.append('Egy emeletnyi mozgás nem vezethet a(z) %d. emeletről a földszintre.' % floor)
    return errors


def finalize(plan, shots):
    reconcile(shots, plan)
    errors = problems(plan, shots)
    plan['contract'] = dict(version=2, story_hash=digest(plan, shots), errors=errors,
                            status='needs_revision' if errors else 'validated')
    return plan['contract']
