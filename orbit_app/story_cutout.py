"""Cut-out animation: painted characters move in front of a still painted background.

Each character is a set of FLUX-painted pose cut-outs taken from one character sheet, so they look the same in every
shot. The background plate never moves; the characters walk, run, hop, lean, get knocked back, bounce while they talk
and swap pose on the beat. The camera reframes with hard cuts every second or so (wide, two-shot, close on the speaker)
for a fast Shorts rhythm. Runs in media-runtime (numpy, cv2). Input JSON on argv[1]; writes clip-<n>.mp4."""
import json
import math
import random
import subprocess
import sys
from pathlib import Path

from story_puppet import CONTACT, INTERACT, TRANSITIONS, ease, envelopes, load_sprite, transition, travel

W, H, FPS = 1080, 1920, 24
FLOOR = 1640            # where the feet stand on the plate
HEIGHT = 780            # a character's painted height in the wide view
HOMES = dict(lead=330., support=750.)
LEAN = dict(run=9, run_in=10, push=8, slap=6, hit_push=-16, hit_slap=-10, rage=4, sneak=6, walk_in=4, walk_out=4, pace=3)


def pose_of(name, t):
    """Which painted pose a moment uses: the action's own pose, or the reaction after being hit."""
    return 'shock' if name.startswith('hit_') and t >= CONTACT else name


def body(name, t, length, side, gap, level, phase):
    """(x offset, y offset, rotation degrees, x scale, y scale) of a cut-out for one frame."""
    x = travel(name, t, length, side, gap) or 0.
    y, rot, sx, sy = 0., 0., 1., 1.
    breathe = .012 * math.sin(t * 2.6 + phase)
    sy += breathe
    sx -= breathe * .5
    if name in ('walk_in', 'walk_out', 'run_in', 'run', 'pace', 'sneak') or name in INTERACT and t < CONTACT:
        step = abs(math.sin(t * (13 if 'run' in name else 8)))
        y -= (22 if 'run' in name else 12) * step
        rot += 2.5 * math.sin(t * (13 if 'run' in name else 8))
    if name == 'jump':
        hop = abs(math.sin(t * 4.4))
        y -= 190 * hop
        sy, sx = (1.08, .94) if hop > .5 else (.9, 1.08)
    if name == 'dance':
        rot += 10 * math.sin(t * 5.4)
        y -= 30 * abs(math.sin(t * 5.4))
    if name == 'faint':
        rot += -side * 80 * ease((t - length * .3) / .5)
    if name in ('shock', 'rage'):
        x += 6 * math.sin(t * 40) if t < .6 else 0
    if name.startswith('hit_') and t >= CONTACT:
        rot += -side * 14 * max(0, 1 - (t - CONTACT) / 1.2)
    if name == 'crouch':
        sy -= .18 * ease(t / .35)
    rot += side * LEAN.get(name, 0)
    y -= 14 * level * abs(math.sin(t * 14))                          # speech bounce
    return x, y, rot, sx, sy


def paste(np, cv2, frame, sprite, foot_x, foot_y, height, rot, sx, sy, flip):
    h, w = sprite.shape[:2]
    if flip:
        sprite = sprite[:, ::-1]
    k = height / h
    matrix = cv2.getRotationMatrix2D((w / 2, h), rot, 1.)
    matrix[:, :2] *= np.array([[k * sx], [k * sy]], np.float32)
    matrix[0, 2] = foot_x - (matrix[0, 0] * w / 2 + matrix[0, 1] * h)
    matrix[1, 2] = foot_y - (matrix[1, 0] * w / 2 + matrix[1, 1] * h)
    layer = cv2.warpAffine(sprite, matrix, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    alpha = layer[..., 3:].astype(np.float32) / 255
    frame[:] = (layer[..., :3] * alpha + frame * (1 - alpha)).astype(np.uint8)


def views(frames, speaking, cast, rng):
    """Hard cuts every 22-34 frames between wide, two-shot and a close-up on whoever speaks."""
    out, at, last = [], 0, None
    while at < frames:
        span = min(frames - at, rng.randint(22, 34))
        if frames - at - span < 14:
            span = frames - at
        loud = {r: sum(speaking[r][at:at + span]) for r in ('lead', 'support')}
        who = max(loud, key=loud.get) if max(loud.values()) > .4 else cast if cast in ('lead', 'support') else rng.choice(('lead', 'support'))
        options = [v for v in ('wide', 'two', 'close') if v != last]
        view = rng.choice(options)
        out.append((at, view, who))
        last, at = view, at + span
    return out


def camera(view, who, xs):
    if view == 'wide':
        return 1., W / 2, H / 2
    if view == 'two':
        return 1.3, (xs['lead'] + xs['support']) / 2, FLOOR - HEIGHT * .62
    return 1.7, xs[who], FLOOR - HEIGHT * .82


def run(request):
    import numpy as np
    import cv2
    rng = random.Random(request.get('seed', 7))
    folder, ffmpeg = Path(request['folder']), request['ffmpeg']
    plates = [cv2.resize(cv2.imread(p), (W, H), interpolation=cv2.INTER_CUBIC) for p in request['plates']]
    sprites = {role: {pose: load_sprite(np, cv2, path, 1100) for pose, path in poses.items()} for role, poses in request['sprites'].items()}
    shots = request['shots']
    levels = envelopes(request.get('speech', []), sum(s['frames'] for s in shots))
    done, written = 0, []
    for index, shot in enumerate(shots, 1):
        out = folder / f'clip-{index}.mp4'
        encoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', str(out)], stdin=subprocess.PIPE)
        frames, length = shot['frames'], shot['frames'] / FPS
        acting, cast = shot.get('acting') or {}, shot.get('cast', 'both')
        visible = ('lead', 'support') if cast == 'both' else (cast,)
        speaking = {r: levels[r][done:done + frames] for r in ('lead', 'support')}
        plan = views(frames, speaking, cast, rng)
        plate = plates[min(len(plates) - 1, int(shot.get('plate', 0)))]
        arrive = 'cut' if index == 1 else rng.choice(TRANSITIONS)
        gap = HOMES['support'] - HOMES['lead']
        for f in range(frames):
            t = f / FPS
            moves = {r: acting.get(r, 'idle') for r in ('lead', 'support')}
            for role, other in (('lead', 'support'), ('support', 'lead')):
                if role in visible and other in visible and moves[role] in ('push', 'slap') and t >= CONTACT and moves[other] not in INTERACT:
                    moves[other] = 'hit_' + moves[role]
            state = {r: body(moves[r], t, length, 1 if r == 'lead' else -1, gap, speaking[r][f] if f < len(speaking[r]) else 0, 1.7 if r == 'lead' else .4) for r in visible}
            xs = {r: HOMES[r] + (state[r][0] if r in state else 0) for r in ('lead', 'support')}
            cut = max(c for c in plan if c[0] <= f)
            zoom, cx, cy = camera(cut[1], cut[2], xs)
            if f - cut[0] < 3 and cut[0]:
                zoom *= 1.03                                               # a cut lands with a tiny settle
            if arrive == 'pop' and f < 6:
                zoom *= 1 + .2 * (1 - f / 6) ** 2
            zoom = max(1., zoom)
            half, halfh = W / 2 / zoom, H / 2 / zoom
            cx, cy = min(max(cx, half), W - half), min(max(cy, halfh), H - halfh)
            # Everything is drawn on a full-size stage first, then the camera crops it, so the background stays still.
            stage = plate.copy()
            for role in visible:
                x, y, rot, sx, sy = state[role]
                pose = pose_of(moves[role], t)
                own = sprites[role]
                art = own[pose] if pose in own else own['idle'] if 'idle' in own else next(iter(own.values()))
                paste(np, cv2, stage, art, HOMES[role] + x, FLOOR + y, HEIGHT, rot, sx, sy, flip=False)
            matrix = np.float32([[zoom, 0, W / 2 - cx * zoom], [0, zoom, H / 2 - cy * zoom]])
            frame = cv2.warpAffine(stage, matrix, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            transition(np, cv2, frame, arrive, f, 1 if index % 2 else -1)
            encoder.stdin.write(frame.tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise ValueError(f'clip {index} did not encode')
        written.append(str(out))
        done += frames
    return dict(clips=written)


if __name__ == '__main__':
    print(json.dumps(run(json.loads(sys.argv[1]))))
