"""Real human motion for the stickman rig: CMU motion capture clips turned into rig pose tracks.

The rig's hand-written poses read as "code animation". Motion capture gives the weight, timing and overlap of a real
actor (a walk that rolls through the feet, a laugh that shakes the shoulders), and the rig still draws the character, so
the cast stays exactly the same in every frame and every episode.

Source: Carnegie Mellon University Graphics Lab Motion Capture Database (mocap.cs.cmu.edu), BVH conversion by B. Hahne
(cgspeed), mirrored at github.com/meshula/cmu-mocap. "This data is free for use in research and commercial projects";
credit: CMU Graphics Lab Motion Capture Database.

Runs in media-runtime (numpy). `story_mocap.py build <folder>` downloads the few clips used (about 8 MB, once) and writes
<folder>/tracks.json. Each track frame is the rig's own values:
  lx ly rx ry  hands relative to the chest      lf rf  feet relative to the hips (x)
  lfy rfy      foot lift above the ground       y      hip drop (down is +)     lean tilt  degrees
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/meshula/cmu-mocap/master/data/{:03d}/{}.bvh'
CREDIT = 'Mozgásrögzítés: CMU Graphics Lab Motion Capture Database (mocap.cs.cmu.edu)'
FPS = 24
KEYS = ('lx', 'ly', 'rx', 'ry', 'lf', 'rf', 'lfy', 'rfy', 'y', 'lean', 'tilt')
VERSION = 4
# Rig proportions (story_puppet): hip to ground 290, arm 135 + 135, shoulders 62 to the side and 26 under the chest.
LEG, ARM, SHOULDER_X, SHOULDER_Y = 290., 270., 62., 26.

# action -> clips. Gestures are seen three-quarter on; walks and runs from the side, as one looping gait cycle.
GESTURES = dict(idle=['111_28', '113_21'], stare=['111_28'], talk=['18_08', '19_08'], point=['14_24'], shrug=['141_21', '111_25'],
                phone=['80_25'], shock=['79_73'], laugh=['80_44', '79_70'], cry=['80_45', '79_72'], rage=['18_10', '80_48'],
                dance=['111_05', '113_04'], crouch=['111_17'], jump=['91_39'])
GAITS = dict(walk=['91_29', '91_34'], sneak=['91_18'], run=['02_03', '09_02'])
# Window lengths (s) for gestures; a longer window is chosen where the motion is a slow one.
WINDOW = dict(idle=4., stare=4., talk=4., dance=4., cry=4., laugh=3., rage=3.)


def parse(text):
    """BVH -> joints (name, parent, offset, channels) and frames (list of float lists), frame time."""
    tokens = text.split()
    joints, stack, i = [], [], 0
    while tokens[i] != 'MOTION':
        word = tokens[i]
        if word in ('ROOT', 'JOINT'):
            joints.append(dict(name=tokens[i + 1], parent=stack[-1] if stack else None, offset=(0., 0., 0.), channels=[]))
            i += 2
        elif word == 'End':
            joints.append(dict(name=joints[stack[-1]]['name'] + '_end', parent=stack[-1], offset=(0., 0., 0.), channels=[]))
            i += 2
        elif word == '{':
            stack.append(len(joints) - 1)
            i += 1
        elif word == '}':
            stack.pop()
            i += 1
        elif word == 'OFFSET':
            joints[stack[-1]]['offset'] = tuple(float(x) for x in tokens[i + 1:i + 4])
            i += 4
        elif word == 'CHANNELS':
            n = int(tokens[i + 1])
            joints[stack[-1]]['channels'] = tokens[i + 2:i + 2 + n]
            i += 2 + n
        else:
            i += 1
    count = int(tokens[i + 2])
    step = float(tokens[i + 5])
    values = tokens[i + 6:]
    width = sum(len(j['channels']) for j in joints)
    frames = [[float(x) for x in values[k * width:(k + 1) * width]] for k in range(count)]
    return joints, frames, step


def positions(joints, frames, step, np):
    """World positions of every joint, resampled to 24 fps: array (frames, joints, 3), Y up."""
    data = np.array(frames, dtype=np.float64)
    want = np.arange(0, (len(frames) - 1) * step, 1 / FPS)
    pick = np.minimum(np.round(want / step).astype(int), len(frames) - 1)
    data = data[pick]
    n = len(data)

    def axis(name, angle):
        c, s = np.cos(angle), np.sin(angle)
        m = np.zeros((n, 3, 3))
        a, b = {'X': (1, 2), 'Y': (2, 0), 'Z': (0, 1)}[name]
        k = 3 - a - b
        m[:, k, k] = 1
        m[:, a, a], m[:, a, b], m[:, b, a], m[:, b, b] = c, -s, s, c
        return m
    out = np.zeros((n, len(joints), 3))
    rot = [None] * len(joints)
    col = 0
    for j, joint in enumerate(joints):
        local = np.tile(np.eye(3), (n, 1, 1))
        pos = np.tile(np.array(joint['offset']), (n, 1))
        for ch in joint['channels']:
            v = data[:, col]
            col += 1
            if ch.endswith('position'):
                pos[:, 'XYZ'.index(ch[0])] = v + joint['offset']['XYZ'.index(ch[0])] if joint['parent'] is not None else v
            else:
                local = local @ axis(ch[0], np.radians(v))
        if joint['parent'] is None:
            rot[j], out[:, j] = local, pos
        else:
            p = joint['parent']
            out[:, j] = out[:, p] + np.einsum('nij,nj->ni', rot[p], pos)
            rot[j] = rot[p] @ local
    return out


def body_frames(joints, world, np, side_view):
    """Rig values per frame, the character turned to screen right."""
    at = {j['name']: i for i, j in enumerate(joints)}
    get = lambda name: world[:, at[name]]
    hips, neck, head = get('Hips'), get('Neck1'), get('Head')
    lhip, rhip = get('LeftUpLeg'), get('RightUpLeg')
    lankle, rankle = get('LeftFoot'), get('RightFoot')
    lsh, rsh, lhand, rhand = get('LeftArm'), get('RightArm'), get('LeftHand'), get('RightHand')
    # Heading from the hips' left-right line, smoothed over half a second so turning in place is not jitter.
    lateral = lhip - rhip
    lateral[:, 1] = 0
    kernel = np.ones(13) / 13
    for c in (0, 2):
        lateral[:, c] = np.convolve(np.pad(lateral[:, c], 6, mode='edge'), kernel, mode='valid')
    lateral /= np.linalg.norm(lateral, axis=1, keepdims=True) + 1e-9
    up = np.array([0., 1., 0.])
    forward = np.cross(lateral, up)
    theta = math.radians(85 if side_view else 35)
    a, b = math.cos(theta), math.sin(theta)

    def screen(p, origin):
        d = p - origin
        lat, fwd, height = (d * lateral).sum(1), (d * forward).sum(1), d[:, 1]
        return np.stack([lat * a + fwd * b, -height], 1)
    offset = lambda name: math.dist((0, 0, 0), joints[at[name]]['offset'])
    leg = offset('LeftLeg') + offset('LeftFoot')
    arm = offset('LeftForeArm') + offset('LeftHand')
    s, sa = LEG / leg, ARM / arm
    ground = np.percentile(np.minimum(lankle[:, 1], rankle[:, 1]), 5)
    stand = np.percentile(hips[:, 1], 90)
    chest = screen(neck, hips)
    # Facing screen right, the character's left side is the far, screen-right side: mocap Left drives the rig's r keys.
    hand_r = screen(lhand, lsh) * sa + [SHOULDER_X, SHOULDER_Y]
    hand_l = screen(rhand, rsh) * sa + [-SHOULDER_X, SHOULDER_Y]
    foot_r, foot_l = screen(lankle, hips)[:, 0] * s, screen(rankle, hips)[:, 0] * s
    torso = chest
    lean = np.degrees(np.arctan2(torso[:, 0], -torso[:, 1]))
    head_v = screen(head, neck)
    tilt = np.clip(np.degrees(np.arctan2(head_v[:, 0], -head_v[:, 1])) - lean, -25, 25)
    values = dict(lx=hand_l[:, 0], ly=hand_l[:, 1], rx=hand_r[:, 0], ry=hand_r[:, 1], lf=foot_l, rf=foot_r,
                  lfy=np.maximum(0, (rankle[:, 1] - ground) * s), rfy=np.maximum(0, (lankle[:, 1] - ground) * s),
                  y=(stand - hips[:, 1]) * s, lean=np.clip(lean, -35, 35), tilt=tilt)
    # Distance walked along the body's own heading, step by step (a figure-eight walk returns to where it started).
    step_along = (np.diff(hips, axis=0) * forward[1:]).sum(1)
    travel = np.concatenate([[0.], np.cumsum(step_along)]) * s
    return np.stack([values[k] for k in KEYS], 1), travel


def window(track, length, np, skip=12):
    """The busiest stretch of the clip (CMU takes start and end in a calibration pose), looped by a short crossfade."""
    n = min(len(track) - 2 * skip, int(length * FPS))
    if n < FPS:
        return track
    motion = np.abs(np.diff(track[:, :4], axis=0)).sum(1)
    best, at = -1, skip
    for start in range(skip, len(track) - skip - n, 3):
        e = motion[start:start + n].sum()
        if e > best:
            best, at = e, start
    piece = track[at:at + n].copy()
    fade = min(8, n // 4)
    for k in range(fade):
        w = (k + 1) / (fade + 1)
        piece[n - fade + k] = piece[n - fade + k] * (1 - w) + piece[k] * w
    return piece


def gait_cycle(track, travel, np, skip=24):
    skip = min(skip, len(track) // 6)
    """One stride (left and right step) from the steadiest part of a walk: period from the feet's autocorrelation."""
    signal = track[skip:-skip, KEYS.index('lf')] - track[skip:-skip, KEYS.index('rf')]
    signal = signal - signal.mean()
    best, period = -1e18, FPS
    for p in range(int(FPS * .45), int(FPS * 2.2)):
        c = (signal[:-p] * signal[p:]).mean()
        if c > best:
            best, period = c, p
    middle = skip + (len(signal) - period) // 2
    cycle = track[middle:middle + period].copy()
    # The distance a stride covers is the one that keeps the standing foot planted: each frame the body moves on by what
    # the lower foot slides back (the hips' own path is unreliable on turning takes).
    lf, rf, lfy, rfy = (KEYS.index(k) for k in ('lf', 'rf', 'lfy', 'rfy'))
    distance = 0.
    for k in range(period):
        a, b = cycle[k], cycle[(k + 1) % period]
        foot, lift = (lf, lfy) if a[lfy] <= a[rfy] else (rf, rfy)
        distance += a[foot] - b[foot]
    return cycle, max(60., abs(float(distance)))


def fetch(name, folder):
    path = folder / 'bvh' / (name + '.bvh')
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        subject = int(name.split('_')[0])
        request = urllib.request.Request(BASE.format(subject, name), headers={'User-Agent': 'ORBIT-studio'})
        with urllib.request.urlopen(request, timeout=60) as reply:
            data = reply.read()
        if b'HIERARCHY' not in data[:200]:
            raise ValueError(name + ': not a BVH file')
        tmp = path.with_suffix('.part')
        tmp.write_bytes(data)
        tmp.replace(path)
    return path.read_text(errors='replace')


def build(folder):
    import numpy as np
    folder = Path(folder)
    out = folder / 'tracks.json'
    if out.is_file():
        try:
            if json.loads(out.read_text()).get('version') == VERSION:
                return json.loads(out.read_text())
        except ValueError:
            pass
    result, failed = dict(version=VERSION, credit=CREDIT, fps=FPS, keys=list(KEYS), gestures={}, gaits={}), []
    for kind, table in (('gestures', GESTURES), ('gaits', GAITS)):
        for action, clips in table.items():
            for name in clips:
                try:
                    joints, frames, step = parse(fetch(name, folder))
                    world = positions(joints, frames, step, np)
                    track, travel = body_frames(joints, world, np, kind == 'gaits')
                    if kind == 'gaits':
                        cycle, distance = gait_cycle(track, travel, np)
                        result['gaits'].setdefault(action, []).append(dict(clip=name, travel=round(distance, 1), frames=np.round(cycle, 1).tolist()))
                    else:
                        piece = window(track, WINDOW.get(action, 2.5), np)
                        result['gestures'].setdefault(action, []).append(dict(clip=name, frames=np.round(piece, 1).tolist()))
                except Exception as error:     # one missing clip leaves that action to the hand-made pose
                    failed.append(f'{name}: {str(error)[:120]}')
    result['failed'] = failed
    if result['gestures'] or result['gaits']:
        out.write_text(json.dumps(result))
    return result


class Tracks:
    """Lookup used by the rig: a gesture at time t, or a gait at a phase of its stride."""
    def __init__(self, data):
        self.data = data or {}
        self.keys = self.data.get('keys', list(KEYS))

    def _row(self, frames, pos, mirror, loop=True):
        n = len(frames)
        if not loop:
            pos = min(max(0., pos), n - 1.001)          # a gesture played once holds its last pose
        # A captured take does not end where it starts: looping it jumped the hand ~100 px every four seconds
        # (13 Nov, "nagyon hirtelen"). The loop is n - L frames long and its first L frames cross-fade from the
        # take's tail, so the end runs straight into the start.
        L = min(24, n // 4) if loop else 0
        span = max(1, n - L)
        p = pos % span if loop else pos
        def at(q):
            i = int(q) % n
            j, w = min(i + 1, n - 1), q - int(q)
            return [frames[i][c] * (1 - w) + frames[j][c] * w for c in range(len(self.keys))]
        if L and p < L:
            head, tail, w = at(p), at(p + span), p / L
            values = [h * w + s * (1 - w) for h, s in zip(head, tail)]
        else:
            values = at(p)
        row = {k: values[c] for c, k in enumerate(self.keys)}
        if mirror:
            # Facing screen left: the picture is flipped, so left and right swap as well.
            row = dict(row, lx=-row['rx'], ly=row['ry'], rx=-row['lx'], ry=row['ly'], lf=-row['rf'], rf=-row['lf'], lfy=row['rfy'], rfy=row['lfy'],
                       lean=-row['lean'], tilt=-row['tilt'])
        return row

    def gesture(self, action, t, side, variant=0, loop=True):
        options = self.data.get('gestures', {}).get(action)
        if not options:
            return None
        frames = options[variant % len(options)]['frames']
        return self._row(frames, t * FPS + (variant * 17 if loop else 0), side < 0, loop)

    def length(self, action, variant=0):
        """Seconds of one captured gesture take."""
        options = self.data.get('gestures', {}).get(action)
        return len(options[variant % len(options)]['frames']) / FPS if options else 0.

    def gait(self, action, phase, side, variant=0):
        options = self.data.get('gaits', {}).get(action)
        if not options:
            return None, None
        pick = options[variant % len(options)]
        frames = pick['frames']
        return self._row(frames, (phase % 1.) * len(frames), side < 0), pick['travel']


def load(path):
    try:
        return Tracks(json.loads(Path(path).read_text())) if path and Path(path).is_file() else None
    except (OSError, ValueError):
        return None


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'build':
        done = build(sys.argv[2])
        print(json.dumps(dict(gestures=sorted(done.get('gestures', {})), gaits=sorted(done.get('gaits', {})), failed=done.get('failed', []))))
