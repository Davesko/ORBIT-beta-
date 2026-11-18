"""Controlled actions used by the normal stickman renderer, in either orientation."""
import math

import scene_events as events
import scene_objects as objects
import stickman_rig as rig

VERSION = 'controlled-2d-v1'
SUPPORTED = ('press_button', 'turn_control')


def compile_shots(shots, fps=30):
    states = {}
    for index, shot in enumerate(shots):
        spec = shot.get('controlled')
        if not spec:
            continue
        if spec.get('action') not in SUPPORTED or not spec.get('target'):
            raise ValueError('Nem támogatott vagy célpont nélküli vezérelt művelet.')
        count = max(12, round((shot['end'] - shot['start']) * fps))
        target = spec['target']
        before = states.get(target, spec.get('from_deg', 0.) if spec['action'] == 'turn_control' else 'off')
        after = float(spec.get('to_deg', float(before) + spec.get('delta_deg', 35.))) if spec['action'] == 'turn_control' else 'on'
        spec.update(id='scene:%d' % index, renderer=VERSION, state_before=before, state_after=after,
                    frames=dict(reach=round(count * .08), contact=round(count * .30),
                                change=round(count * .36), finish=round(count * .65), release=count - 1))
        states[target] = after
    return shots


def draw(np, cv2, background, shot, designs, local, fps):
    """Draw a whole world first, then apply ONE camera. Measure the drawn joints."""
    spec = shot['controlled']
    if spec.get('renderer') != VERSION or spec.get('action') not in SUPPORTED:
        raise ValueError('A vezérelt jelenet nincs lefordítva.')
    H, W = background.shape[:2]
    frame = background.copy()
    size = min(H * .48, W * .70)
    ground, foot = H * .76, W * .28
    p = dict(rig.pose('idle', 0., 1., 0), lean=0., tilt=0., fs=7., bs=7.)
    rest = rig.skeleton(p, foot, ground, size, 1)
    shoulder = rest['shoulder']
    centre = (shoulder[0] + size * (.215 if spec['action'] == 'turn_control' else .30), shoulder[1] + size * .025)
    cv = rig.Canvas(cv2, frame)
    # The physical controls are rendered objects, not controls baked into the plate.
    cv2.rectangle(frame, (int(centre[0] - size * .17), int(centre[1] - size * .21)),
                  (min(W - 1, int(centre[0] + size * .24)), int(centre[1] + size * .23)),
                  (142, 152, 148), -1)
    f = spec['frames']
    n = max(0, round(local * fps))
    weight = events.ease((n - f['reach']) / max(1, f['contact'] - f['reach']))
    progress = events.ease((n - f['change']) / max(1, f['finish'] - f['change']))
    action = spec['action']
    if action == 'turn_control':
        angle = float(spec['state_before']) + (float(spec['state_after']) - float(spec['state_before'])) * progress
        control = objects.wheel(spec['target'], centre, size * .095, [160., 205.], angle)
        targets = objects.grip_points(control)
        objects.draw(cv, control)
        sides = [('f', 'fs'), ('b', 'bs')]
        state = angle
    else:
        on = spec['state_before'] == 'on' or n >= f['change']
        control = objects.lamp(spec['target'], centre, size * .047, 'on' if on else 'off')
        objects.draw(cv, control)
        targets = [centre]
        sides = [('f', 'fs')]
        state = 'on' if on else 'off'
    for (side, key), target in zip(sides, targets):
        origin = rest[side + 'hand']
        aim = tuple(a + (b - a) * weight for a, b in zip(origin, target))
        a1, a2, _ = events.reach_arm(shoulder, aim, 1, size)
        p[key], p[side + 'e'] = a1, a2
    design = designs.get('main', rig.MAIN)
    joints = rig.draw_figure(cv, design, p, foot, ground, size, 1, 'determined', t=local, prop='none')
    for a in shot.get('actors', []):
        kind = a.get('who', '').split(':')[-1]
        if kind in rig.ANIMALS:
            rig.draw_animal(cv, kind, W * .12, ground, size * .45, 1, local)
    zoom = 1. if shot.get('camera') == 'static' else 1. + .035 * events.ease(local / max(.1, shot['end'] - shot['start']))
    matrix = np.array([[zoom, 0, W * (1 - zoom) / 2], [0, zoom, H * (1 - zoom) / 2]], np.float32)
    frame = cv2.warpAffine(frame, matrix, (W, H), borderMode=cv2.BORDER_REPLICATE)
    errors = [math.dist(joints[side + 'hand'], target) * zoom for (side, _), target in zip(sides, targets)]
    measured = dict(id=spec['id'], renderer=VERSION, target=spec['target'],
                    contact=n >= f['contact'], error_px=max(errors), limit_px=size * .01,
                    state=state, expected_state=spec['state_after'],
                    finished=n >= f['finish'], hands=len(targets))
    return frame, measured


def accumulate(records, measured):
    rec = records.setdefault(measured['id'], dict(renderer=VERSION, target=measured['target'],
                            samples=0, contact_samples=0, max_error_px=0., limit_px=measured['limit_px'],
                            state_verified=False))
    rec['samples'] += 1
    if measured['contact']:
        rec['contact_samples'] += 1
        rec['max_error_px'] = max(rec['max_error_px'], measured['error_px'])
    if measured['finished']:
        actual, expected = measured['state'], measured['expected_state']
        rec['state_verified'] = actual == expected if isinstance(expected, str) else abs(actual - expected) < .01
    rec['passed'] = rec['contact_samples'] > 0 and rec['max_error_px'] <= rec['limit_px'] and rec['state_verified']
    return rec
