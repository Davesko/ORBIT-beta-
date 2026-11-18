"""Illustrated shots: every cut is a full painted picture with the characters in it, brought to life by the camera.

The look of viral 2D "stickman edition" Shorts comes from many detailed pictures and fast cuts, not from a puppet. Each
key picture is painted by FLUX; here it is moved like an animated panel: a slow push, pull or pan with eased speed, a
little handheld drift, a breathing scale on the subject, a punch-in on a beat, and a whip, pop or flash into the next
cut. Runs in media-runtime (numpy, cv2). Input JSON on argv[1]; writes clip-<n>.mp4 to `folder`."""
import json
import math
import random
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1080, 1920, 24
MOVES = ('push', 'pull', 'pan_left', 'pan_right', 'rise', 'push')


def ease(u):
    u = max(0., min(1., u))
    return u * u * (3 - 2 * u)


def framing(move, u, punch, rng_phase, t):
    """Zoom and centre offset (fractions of the picture) for one frame of a key picture."""
    e = ease(u)
    zoom = dict(push=1.06 + .16 * e, pull=1.22 - .16 * e).get(move, 1.14)
    dx = dict(pan_left=.06 - .12 * e, pan_right=-.06 + .12 * e).get(move, 0.)
    dy = -.05 + .07 * e if move == 'rise' else 0.
    zoom *= 1 + .012 * math.sin(t * 2.1 + rng_phase) + punch      # breathing and a punch-in
    dx += .004 * math.sin(t * 1.3 + rng_phase)                    # handheld drift
    dy += .004 * math.cos(t * 1.1 + rng_phase * 2)
    return zoom, dx, dy


def frame_of(np, cv2, picture, zoom, dx, dy):
    h, w = picture.shape[:2]
    scale = max(W / w, H / h) * zoom
    cx, cy = w / 2 + dx * w, h / 2 + dy * h
    matrix = np.float32([[scale, 0, W / 2 - cx * scale], [0, scale, H / 2 - cy * scale]])
    return cv2.warpAffine(picture, matrix, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def run(request):
    import numpy as np
    import cv2
    from story_puppet import transition, TRANSITIONS
    rng = random.Random(request.get('seed', 7))
    folder, ffmpeg, written = Path(request['folder']), request['ffmpeg'], []
    for index, shot in enumerate(request['shots'], 1):
        out = folder / f'clip-{index}.mp4'
        pictures = [cv2.imread(p) for p in shot['pictures']]
        frames = shot['frames']
        cut_at = [round(frames * i / len(pictures)) for i in range(len(pictures) + 1)]
        encoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', str(out)], stdin=subprocess.PIPE)
        for k, picture in enumerate(pictures):
            move, phase = rng.choice(MOVES), rng.random() * 6
            arrive = 'cut' if index == 1 and k == 0 else rng.choice(TRANSITIONS)
            span = cut_at[k + 1] - cut_at[k]
            beat = shot.get('beat') == 'twist' and k == len(pictures) - 1
            for f in range(span):
                u, t = f / max(1, span - 1), (cut_at[k] + f) / FPS
                punch = .1 * max(0, 1 - f / 5) if beat else 0.
                zoom, dx, dy = framing(move, u, punch, phase, t)
                if arrive == 'pop' and f < 6:
                    zoom *= 1 + .18 * (1 - f / 6) ** 2
                frame = frame_of(np, cv2, picture, zoom, dx, dy)
                transition(np, cv2, frame, arrive, f, 1 if (index + k) % 2 else -1)
                encoder.stdin.write(frame.tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise ValueError(f'clip {index} did not encode')
        written.append(str(out))
    return dict(clips=written)


if __name__ == '__main__':
    print(json.dumps(run(json.loads(sys.argv[1]))))
