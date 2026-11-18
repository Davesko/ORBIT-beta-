"""Controlled scene templates (audit 17 Nov, step 4): `turn_control` - a figure grips a wall valve wheel with BOTH hands, turns it by
an angle and a lamp changes. One event drives the arms (inverse kinematics onto the wheel's grip points), the wheel's angle, the
lamp, the click and the creak; the whole world (background, wheel, lamp, figure) is drawn on one layer and the camera is one
transform of that layer, so the hands and the rim never drift apart. Captions are drawn after the camera.

Run in the media runtime (OpenCV, NumPy, ffmpeg): `python3 scene_templates.py turn_control <output folder>`; prints the report as JSON.
"""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import scene_events as ev
import scene_objects as obj
import scene_quality as quality
import stickman_rig as rig

W, H, FPS = 1280, 720, 30
FACING = 1
FOOT_X, GROUND, SIZE = 380., 640., 470.
SECONDS = 12.0
CUT = 180            # frame where the second shot (closer camera) starts


def background(cv2, np):
    frame = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        k = y / H
        frame[y, :] = (int(150 - 40 * k), int(158 - 36 * k), int(150 - 44 * k))
    cv2.rectangle(frame, (0, int(GROUND)), (W, H), (96, 104, 100), -1)
    cv2.line(frame, (0, int(GROUND)), (W, int(GROUND)), (40, 44, 44), 3)
    for x in (80, 150, 1090, 1170):            # pipes on the far wall
        cv2.rectangle(frame, (x, 40), (x + 22, int(GROUND)), (112, 122, 134), -1)
        cv2.rectangle(frame, (x, 40), (x + 22, int(GROUND)), (40, 44, 44), 2)
    cv2.rectangle(frame, (560, 150), (1010, 520), (126, 134, 128), -1)         # the panel the wheel is mounted on
    cv2.rectangle(frame, (560, 150), (1010, 520), (40, 44, 44), 3)
    return frame


def rest_hands(design):
    p = dict(rig.pose('idle', 0., 1., 0), lean=6.)
    j = rig.skeleton(p, FOOT_X, GROUND, SIZE, FACING)
    return p, j


def place_wheel(shoulder, rotations, grips, radius):
    """The wheel centre that keeps every grip point within comfortable reach over the whole turn (searched, then asserted)."""
    reach = (rig.UPPER + rig.FORE) * SIZE
    best = None
    for dx in range(110, 260, 5):
        for dy in range(-70, 71, 5):
            centre = (shoulder[0] + dx, shoulder[1] + dy)
            worst = 0.
            for rot in rotations:
                w = obj.wheel('w', centre, radius, grips, rot)
                for g in obj.grip_points(w):
                    worst = max(worst, math.hypot(g[0] - shoulder[0], g[1] - shoulder[1]))
            nearest = min(math.hypot(g[0] - shoulder[0], g[1] - shoulder[1]) for rot in rotations for g in obj.grip_points(obj.wheel('w', centre, radius, grips, rot)))
            if worst > reach * .93 or nearest < reach * .55:
                continue          # out of reach, or squeezed against the body (the arms would be hidden)
            score = abs(worst - reach * .86)
            if best is None or score < best[0]:
                best = (score, centre)
    if best is None:
        raise ValueError('A kerék nem helyezhető a kar elérésén belülre.')
    return best[1]


def synth_audio(events, seconds, sr=48000):
    import numpy as np
    n = int(seconds * sr)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(7)

    def put(at, sig):
        i = int(at * sr)
        sig = sig[:max(0, n - i)]
        out[i:i + len(sig)] += sig
    for e in events:
        t0 = e['frame'] / FPS
        if e.get('role') == 'metal_click':
            k = np.arange(int(.12 * sr)) / sr
            put(t0, (np.exp(-k * 70) * (.7 * np.sin(2 * np.pi * 1800 * k) + .5 * rng.standard_normal(len(k)))).astype(np.float32) * .9)
        elif e.get('role') == 'metal_creak':
            length = e.get('seconds', .75)
            k = np.arange(int(length * sr)) / sr
            env = np.sin(np.pi * k / length) ** 2
            put(t0, (env * (.22 * np.sin(2 * np.pi * (260 + 90 * np.sin(k * 9)) * k) + .05 * rng.standard_normal(len(k)))).astype(np.float32))
        elif e.get('role') == 'lamp_ding':
            k = np.arange(int(.5 * sr)) / sr
            put(t0, (np.exp(-k * 7) * .35 * np.sin(2 * np.pi * 1320 * k)).astype(np.float32))
    peak = float(np.abs(out).max()) or 1.
    return (out / peak * .7), sr


def click_onset(signal, sr, after=.5):
    import numpy as np
    window = int(sr * .004)
    env = np.convolve(np.abs(signal), np.ones(window) / window, 'same')
    start = int(after * sr)
    peak = float(env[start:].max())
    hits = np.nonzero(env[start:] > peak * .35)[0]
    return None if not len(hits) else (start + int(hits[0])) / sr


def turn_control_pilot(folder, ffmpeg):
    import cv2
    import numpy as np
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    design = dict(rig.MAIN)
    p0, j0 = rest_hands(design)
    shoulder = j0['shoulder']
    grips_deg = [160., 205.]
    radius = 74.
    to_deg = 35.
    centre = place_wheel(shoulder, [0., to_deg / 2, to_deg], grips_deg, radius)
    wheel = obj.wheel('valve_wheel', centre, radius, grips_deg, 0.)
    lamp = obj.lamp('status_lamp', (centre[0] + 190, centre[1] - 120), 22., 'off')
    frames_ = dict(reach=18, contact=30, turn_start=36, turn_end=58, settle=68)
    event = ev.compile_event(ev.turn_control('E01', 'hero', 'valve_wheel', 0., to_deg, frames_, release=300, effects=[
        dict(type='state_change', frame=61, field='lamp.state', value='on'),
        dict(type='sound', anchor='contact', offset_frames=1, role='metal_click'),
        dict(type='sound', anchor='turn_start', offset_frames=0, role='metal_creak', seconds=(frames_['turn_end'] - frames_['turn_start']) / FPS),
        dict(type='sound', frame=61, role='lamp_ding')]), {'valve_wheel': wheel})
    hero_height = SIZE * (rig.THIGH + rig.SHIN + rig.TORSO + rig.SHOULDER + rig.HEAD_R * 2)
    bg = background(cv2, np)
    total = int(SECONDS * FPS)
    silent = folder / 'turn_control-silent.mp4'
    encoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '17', str(silent)], stdin=subprocess.PIPE)
    records = []
    focus2 = ((centre[0] + FOOT_X) / 2, centre[1] + 40)
    captions = {0: 'You grab the wheel with both hands.', CUT: 'And turn it. The lamp comes on.'}
    for n in range(total):
        t = n / FPS
        state = ev.state_at(event, n, wheel, 'off')
        wheel['rotation'], lamp['state']['value'] = state['wheel'], state['lamp']
        frame = bg.copy()
        cv = rig.Canvas(cv2, frame)
        obj.draw(cv, wheel)
        obj.draw(cv, lamp)
        p = dict(rig.pose('idle', t, 1., 0), lean=6.)
        j_rest = rig.skeleton(p, FOOT_X, GROUND, SIZE, FACING)
        weight = ev.hand_weight(event, n)
        grips = obj.grip_points(wheel)
        for side, grip, key in (('f', grips[0], 'fs'), ('b', grips[1], 'bs')):
            rest = j_rest[side + 'hand']
            target = (rest[0] + (grip[0] - rest[0]) * weight, rest[1] + (grip[1] - rest[1]) * weight)
            a1, a2, miss = ev.reach_arm(j_rest['shoulder'], target, FACING, SIZE)
            p[key], p[key[0] + 'e'] = a1, a2
        expression = 'relieved' if state['lamp'] == 'on' else 'determined'
        j = rig.draw_figure(cv, design, p, FOOT_X, GROUND, SIZE, FACING, expression, t=t, seed=3, prop='none')
        z = 1.0 if n < CUT else 1.3 + .06 * ev.ease((n - CUT) / (total - CUT))
        fx, fy = (W / 2, H / 2) if n < CUT else focus2
        fx, fy = min(max(fx, W / 2 / z), W - W / 2 / z), min(max(fy, H / 2 / z), H - H / 2 / z)      # the camera never looks past the drawn world
        M = np.array([[z, 0, W / 2 - z * fx], [0, z, H / 2 - z * fy]], np.float32)
        out = cv2.warpAffine(frame, M, (W, H), flags=cv2.INTER_LINEAR)
        to_screen = lambda q: (M[0, 0] * q[0] + M[0, 2], M[1, 1] * q[1] + M[1, 2])
        text = captions[0 if n < CUT else CUT]
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 1.0, 2)
        tx, ty = (W - tw) // 2, H - 44
        cv2.putText(out, text, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(out, text, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        lc = to_screen(lamp['centre'])
        lamp_bgr = [int(v) for v in out[int(lc[1]), int(lc[0])]]
        hands = [j['fhand'], j['bhand']]
        encoder.stdin.write(out.tobytes())
        wb = obj.bounds(wheel)
        records.append(dict(n=n, wheel=state['wheel'], lamp=state['lamp'], lamp_bgr=lamp_bgr, hands=hands, grips=grips, hands_screen=[to_screen(h) for h in hands],
                            caption=(tx, ty - th, tx + tw, ty + 8),
                            contact_rects=[(*to_screen((wb[0], wb[1])), *to_screen((wb[2], wb[3])))] + [(*[c - 10 for c in to_screen(h)], *[c + 10 for c in to_screen(h)]) for h in hands]))
    encoder.stdin.close()
    encoder.wait()
    audio, sr = synth_audio(event['effects'], SECONDS)
    wav = folder / 'turn_control.wav'
    with wave.open(str(wav), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((audio * 32767).astype('<i2').tobytes())
    final = folder / 'turn_control.mp4'
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', str(silent), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', str(final)], check=True)
    silent.unlink(missing_ok=True)
    # the click is measured in the audio that was MIXED, not read from the plan
    import wave as _w
    with _w.open(str(wav)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768
    rec = dict(event=event, fps=FPS, frames=records, hero_height=hero_height, cut_frame=CUT, click_onset_s=click_onset(data, sr), size=(W, H), expected_seconds=SECONDS)
    report = quality.verify_turn_control(rec)
    report.update(scene='turn_control', video=str(final), seconds=SECONDS, event=dict(id=event['id'], frames=event['frames']), note=(
        'Mechanikai próba: kéztől a tárgyig és a hangig egy eseményből vezérelve. Nem történet; a pilot a hajtott kerék forgatását és az állapotváltozást igazolja.'))
    (folder / 'turn_control-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


if __name__ == '__main__':
    if sys.argv[1] != 'turn_control':
        raise SystemExit('ismeretlen jelenet')
    print(json.dumps(turn_control_pilot(sys.argv[2], str(Path(sys.executable).with_name('ffmpeg')))))
