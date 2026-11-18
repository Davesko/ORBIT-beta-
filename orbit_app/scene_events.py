"""Events of a controlled scene: ONE event drives the hand, the object's state, the sound and the cut (audit 17 Nov, step 3-5).

An event has phases in frames (reach -> contact -> turn_start -> turn_end -> settle, then release); the pose follows from it
(arm inverse kinematics onto the object's grip points), the object only changes AFTER contact, and every sound and state change
is anchored to a phase frame. The compile step refuses an impossible order instead of drawing something close to it.
"""
import math

import stickman_rig as rig

PHASES = ('reach', 'contact', 'turn_start', 'turn_end', 'settle')


def ease(u):
    u = min(1., max(0., u))
    return u * u * (3 - 2 * u)


def turn_control(event_id, actor, target, from_deg, to_deg, frames, release, effects=()):
    return dict(id=event_id, action='turn_control', actor=actor, target=target, parameters=dict(hands='both', from_deg=from_deg, to_deg=to_deg),
                frames=dict(frames, release=release), effects=list(effects), outcome_visible=True)


def compile_event(event, known_objects):
    """Raises ValueError for a missing target or a phase order that cannot be played; returns the event with absolute effect frames."""
    if event.get('target') not in known_objects:
        raise ValueError('Az esemény olyan tárgyra hivatkozik, ami nincs a jelenetben: ' + str(event.get('target')))
    f = event['frames']
    order = [f[k] for k in PHASES] + [f['release']]
    if any(b < a for a, b in zip(order, order[1:])):
        raise ValueError('Az esemény fázisai nem követik egymást: előkészítés ≤ érintkezés ≤ forgás ≤ megnyugvás ≤ elengedés.')
    out = dict(event, effects=[])
    for e in event.get('effects') or []:
        frame = e['frame'] if 'frame' in e else f[e['anchor']] + int(e.get('offset_frames', 0))
        out['effects'].append(dict(e, frame=frame))
    return out


def wheel_angle(event, frame):
    f, p = event['frames'], event['parameters']
    return p['from_deg'] + (p['to_deg'] - p['from_deg']) * ease((frame - f['turn_start']) / max(1, f['turn_end'] - f['turn_start']))


def hand_weight(event, frame):
    """0 = hand at rest, 1 = on the grip: reaching eases in until contact, the grip holds until release, then lets go."""
    f = event['frames']
    if frame < f['reach']:
        return 0.
    if frame < f['contact']:
        return ease((frame - f['reach']) / max(1, f['contact'] - f['reach']))
    if frame <= f['release']:
        return 1.
    return 1. - ease((frame - f['release']) / 24.)


def state_at(event, frame, base_wheel, base_lamp):
    """The object states at a frame. Nothing changes before the contact; the lamp follows its effect frame."""
    f = event['frames']
    wheel = base_wheel['rotation'] if frame < f['turn_start'] else wheel_angle(event, frame)
    lamp = base_lamp
    for e in event['effects']:
        if e.get('type') == 'state_change' and e.get('field') == 'lamp.state' and frame >= e['frame']:
            lamp = e['value']
    return dict(wheel=wheel, lamp=lamp)


# ------------------------------------------------------------------ arm inverse kinematics

def reach_arm(shoulder, target, facing, size, elbow_down=True):
    """Angles (shoulder, elbow) in the rig's convention that put the hand on `target`. Returns (a1_deg, a2_deg, error_px): the
    error is 0 when the target is within the arm's reach and the distance short of it otherwise."""
    u_len, f_len = rig.UPPER, rig.FORE
    tu, tv = (target[0] - shoulder[0]) * facing / size, (target[1] - shoulder[1]) / size
    d = math.hypot(tu, tv)
    reach = u_len + f_len
    miss = max(0., d - reach * .999) * size
    d = min(max(d, abs(u_len - f_len) * 1.001), reach * .999)
    phi = math.atan2(tu, tv)
    alpha = math.acos(max(-1., min(1., (u_len ** 2 + d ** 2 - f_len ** 2) / (2 * u_len * d))))
    best = None
    for a1 in (phi - alpha, phi + alpha):
        ev = math.cos(a1) * u_len            # elbow's v (down is positive)
        if best is None or (ev > best[1] if elbow_down else ev < best[1]):
            best = (a1, ev)
    a1 = best[0]
    eu, ev = math.sin(a1) * u_len, math.cos(a1) * u_len
    a12 = math.atan2(tu - eu, tv - ev)
    a2 = math.degrees(a12 - a1)
    a2 = (a2 + 180) % 360 - 180
    return math.degrees(a1), a2, miss


def hand_positions(p, foot_x, ground, size, facing):
    j = rig.skeleton(p, foot_x, ground, size, facing)
    return j
