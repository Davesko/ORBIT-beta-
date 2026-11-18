"""Moving things in a stickman scene, drawn in code over the painted place.

The owner (16 Nov) asked for elements that move in the picture, "not only my examples but everything such a video
can need": a fire truck that sprays water, a button or a sign that lights up, rain, a car that drives past. A FLUX
plate is a still painting, so whatever moves is drawn here, in the same flat ink style as the characters, from a
small spec the writer (or the words of the sentence) gives a shot:

    dict(kind='vehicle', what='fire truck', where='left', colour='red', label='AIRPORT FIRE')

`kind` is one of MOTIONS; `where` is left / center / right / top / bottom / hand / back; `colour` is a colour word;
`label` is a short text on the thing (a sign, a truck, a burst word like CLUNK). Every function is deterministic in
(t, seed), so consecutive frames continue each other and a re-render is identical."""
import math
import random
import re
from pathlib import Path

INK = (30, 30, 30)
COLOURS = dict(red=(60, 60, 210), orange=(40, 140, 240), yellow=(60, 200, 245), green=(90, 170, 80), teal=(150, 150, 40),
               blue=(190, 120, 50), purple=(150, 80, 130), pink=(170, 140, 240), white=(245, 245, 245), grey=(150, 150, 150),
               gray=(150, 150, 150), black=(40, 40, 40), brown=(50, 90, 140), gold=(60, 180, 220), silver=(200, 200, 200))
MOTIONS = ('fire', 'smoke', 'steam', 'sparks', 'splash', 'drip', 'bubbles', 'dust', 'debris', 'confetti', 'leaves', 'fog',
           'glow', 'blink', 'flash_text', 'burst', 'shockwave', 'beam', 'searchlight', 'spray', 'pour', 'rising_water',
           'speed_lines', 'zzz', 'sweat', 'exclaim', 'question', 'hearts', 'notes', 'twinkle', 'birds', 'clouds',
           'vehicle', 'plane', 'boat', 'ball', 'fan', 'wheel', 'door_slide', 'pendulum', 'flag', 'pulse_ring', 'clock')
OBJECTS = ('vehicle', 'plane', 'boat', 'ball', 'fan', 'wheel', 'door_slide', 'pendulum', 'flag', 'clock', 'birds', 'clouds', 'rising_water', 'fog', 'confetti', 'leaves', 'speed_lines')   # need the whole frame
BEHIND = ('door_slide', 'vehicle', 'plane', 'boat', 'clouds', 'birds', 'fan', 'clock', 'flag', 'pendulum', 'searchlight')   # scenery: behind the figures
WHERE = ('left', 'center', 'right', 'top', 'bottom', 'hand', 'back')


# Kenney Particle Pack 1.1 (CC0, kenney.nl): flame, smoke, spark, star, magic and light textures, white on transparent.
# Found when the owner asked to look for ready libraries (16 Nov); the code-drawn versions stay as the fallback.
TEXTURES = {}
FOLDER = [None]


def use_textures(folder):
    FOLDER[0] = folder if folder and Path(folder).is_dir() else None


def texture(np, cv2, name):
    if not FOLDER[0]:
        return None
    if name not in TEXTURES:
        path = Path(FOLDER[0]) / (name + '.png')
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED) if path.is_file() else None
        TEXTURES[name] = img if img is not None and img.ndim == 3 and img.shape[2] == 4 else None
    return TEXTURES[name]


def stamp(np, cv2, frame, name, x, y, size, tint, alpha=1., angle=0., add=False):
    """One particle texture, tinted, scaled to size pixels, turned, laid over the frame (added for light)."""
    tex = texture(np, cv2, name)
    if tex is None or size < 2:
        return False
    s = max(2, int(size))
    small = cv2.resize(tex, (s, s), interpolation=cv2.INTER_AREA)
    if angle:
        m = cv2.getRotationMatrix2D((s / 2, s / 2), angle, 1.)
        small = cv2.warpAffine(small, m, (s, s), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    H, W = frame.shape[:2]
    x0, y0 = int(x - s / 2), int(y - s / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + s), min(H, y0 + s)
    if xa >= xb or ya >= yb:
        return True
    part = small[ya - y0:yb - y0, xa - x0:xb - x0].astype(np.float32)
    lum = part[..., :3].mean(2, keepdims=True) / 255.
    a = part[..., 3:4] / 255. * alpha
    colour_ = np.array(tint, np.float32) * lum
    region = frame[ya:yb, xa:xb].astype(np.float32)
    region = region + colour_ * a if add else region * (1 - a) + colour_ * a
    frame[ya:yb, xa:xb] = np.clip(region, 0, 255).astype(np.uint8)
    return True


def colour(name, fallback=(245, 245, 245)):
    return COLOURS.get(str(name or '').lower(), fallback)


def anchor(where, W, H, hand=None, facing=1):
    """A point on screen for a where-word; hand is the main character's hand when he is in the shot."""
    if where == 'hand' and hand:
        return hand[0] + facing * W * .03, hand[1]
    return dict(left=(W * .22, H * .55), right=(W * .78, H * .55), top=(W * .5, H * .2), bottom=(W * .5, H * .85),
                back=(W * .5, H * .45)).get(where, (W * .5, H * .5))


def _blur_add(np, cv2, frame, layer, sigma, alpha=1.):
    layer = cv2.GaussianBlur(layer, (0, 0), max(1., sigma))
    cv2.addWeighted(layer, alpha, frame, 1, 0, frame)


def _soft(np, cv2, frame, puffs, tint, H, alpha=.85):
    """Soft blobs (smoke, steam, fog, dust) drawn at quarter size, blurred and laid over the frame."""
    h, w = frame.shape[:2]
    small = np.zeros((h // 4, w // 4), np.uint8)
    for x, y, r, a in puffs:
        cv2.circle(small, (int(x / 4), int(y / 4)), max(1, int(r / 4)), int(255 * max(0., min(1., a))), -1)
    small = cv2.GaussianBlur(small, (0, 0), max(1., H / 200))
    m = cv2.resize(small, (w, h)).astype(np.float32)[..., None] / 255 * alpha
    frame[:] = (frame * (1 - m) + np.array(tint, np.float32) * m).astype(np.uint8)


def _text(cv2, frame, text, x, y, size, fill, stroke=INK, angle=0):
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = size / 30.
    th = max(2, int(size / 10))
    (tw, tht), _ = cv2.getTextSize(text, font, scale, th)
    org = (int(x - tw / 2), int(y + tht / 2))
    cv2.putText(frame, text, org, font, scale, stroke, th + max(3, int(size / 8)), cv2.LINE_AA)
    cv2.putText(frame, text, org, font, scale, fill, th, cv2.LINE_AA)


def draw(np, cv2, frame, spec, t, u, W, H, seed=0, hand=None, facing=1):
    kind = spec.get('kind')
    x, y = anchor(spec.get('where'), W, H, hand, facing)
    c = colour(spec.get('colour'))
    label = str(spec.get('label') or '')[:22].upper()
    rnd = random.Random(seed)
    lw = max(2, int(H * .005))
    if kind == 'fire' and texture(np, cv2, 'flame_01') is not None:
        for k in range(9):
            b = random.Random(seed * 17 + k)
            phase = (t * b.uniform(1.6, 2.4) + b.random()) % 1
            px = x + b.uniform(-.05, .05) * W + math.sin(t * 7 + k) * W * .006
            py = y - phase * H * .16
            size = H * (.42 * (1 - phase) + .1) * (1 + .1 * math.sin(t * 13 + k))
            tone = (70, 190 + int(60 * (1 - phase)), 255)
            stamp(np, cv2, frame, f'flame_0{1 + k % 6}', px, py, size, tone, 1., angle=b.uniform(-15, 15), add=True)
            stamp(np, cv2, frame, f'flame_0{1 + k % 6}', px, py, size * .6, (200, 250, 255), .8, angle=b.uniform(-10, 10), add=True)
        stamp(np, cv2, frame, 'light_01', x, y - H * .05, H * .4, (60, 140, 255), .35 + .1 * math.sin(t * 11), add=True)
    elif kind == 'fire':
        layer = np.zeros_like(frame)
        for k in range(26):
            b = random.Random(seed * 17 + k)
            phase = (t * b.uniform(1.4, 2.2) + b.random()) % 1
            px = x + b.uniform(-.06, .06) * W + math.sin(t * 6 + k) * W * .005
            py = y - phase * H * .22
            r = H * .05 * (1 - phase) + H * .01
            tone = (40, 120 + int(120 * (1 - phase)), 250) if phase < .7 else (60, 60, 60)
            cv2.circle(layer, (int(px), int(py)), int(r), tone, -1, cv2.LINE_AA)
        _blur_add(np, cv2, frame, layer, H / 90)
    elif kind in ('smoke', 'steam') and texture(np, cv2, 'smoke_01') is not None:
        for k in range(10):
            b = random.Random(seed * 31 + k)
            phase = (t * .33 + k / 10) % 1
            px = x + b.uniform(-.03, .03) * W + phase * W * .06 * (1 if k % 2 else -1)
            py = y - phase * H * .5
            tone = (95, 95, 100) if kind == 'smoke' else (250, 250, 250)
            for _ in range(2):      # the textures are faint on their own
                stamp(np, cv2, frame, f'smoke_{1 + k % 10:02d}', px, py, H * (.12 + .4 * phase), tone, min(1., (1 - phase) ** .6 * 1.3), angle=phase * 90 + k * 30)
    elif kind in ('smoke', 'steam', 'dust', 'fog'):
        puffs = []
        n = 12 if kind != 'fog' else 18
        for k in range(n):
            b = random.Random(seed * 31 + k)
            phase = (t * (.35 if kind != 'fog' else .05) + k / n) % 1
            if kind == 'fog':
                puffs.append(((b.random() * 1.2 - .1 + phase * .3) % 1.2 * W, H * b.uniform(.45, .95), H * b.uniform(.12, .22), .45))
            elif kind == 'dust':
                puffs.append((x + (b.random() - .5) * W * .3 * (.3 + phase), y - phase * H * .08, H * (.03 + .08 * phase), (1 - phase) * .7))
            else:
                puffs.append((x + b.uniform(-.03, .03) * W + phase * W * .05 * (1 if k % 2 else -1), y - phase * H * .5,
                              H * (.04 + .14 * phase), (1 - phase) ** .6))
        tint = dict(smoke=(90, 90, 95), steam=(245, 245, 245), dust=(150, 175, 190), fog=(230, 228, 225))[kind]
        _soft(np, cv2, frame, puffs, tint, H, .8 if kind != 'fog' else .5)
    elif kind == 'sparks' and texture(np, cv2, 'spark_01') is not None:
        for burst in range(int(t * 3) + 1):
            b = random.Random(seed * 77 + burst)
            age = t - burst / 3
            if not 0 <= age < .45:
                continue
            stamp(np, cv2, frame, f'spark_0{1 + burst % 7}', x, y, H * .18 * (1 - age * 1.5), (120, 230, 255), 1 - age * 2, angle=b.uniform(0, 360), add=True)
            for _ in range(10):
                ang = b.uniform(-math.pi, 0)
                sp = H * b.uniform(.25, .7)
                stamp(np, cv2, frame, 'star_07', x + math.cos(ang) * sp * age, y + math.sin(ang) * sp * age + H * .9 * age * age, H * .03,
                      (150, 240, 255), 1 - age * 2, add=True)
    elif kind == 'sparks':
        for burst in range(int(t * 3) + 1):
            b = random.Random(seed * 77 + burst)
            age = t - burst / 3
            if not 0 <= age < .45:
                continue
            for _ in range(16):
                ang = b.uniform(-math.pi, 0)
                sp = H * b.uniform(.25, .7)
                p0 = (x + math.cos(ang) * sp * age, y + math.sin(ang) * sp * age + H * .9 * age * age)
                a1 = max(0, age - .045)
                p1 = (x + math.cos(ang) * sp * a1, y + math.sin(ang) * sp * a1 + H * .9 * a1 * a1)
                cv2.line(frame, (int(p1[0]), int(p1[1])), (int(p0[0]), int(p0[1])), (80, 220, 255), lw, cv2.LINE_AA)
    elif kind == 'twinkle' and texture(np, cv2, 'star_01') is not None:
        for k in range(8):
            b = random.Random(seed * 13 + k)
            glow = abs(math.sin(t * 3 + k * 1.7))
            stamp(np, cv2, frame, f'star_0{1 + k % 9}', x + b.uniform(-.2, .2) * W, y + b.uniform(-.2, .1) * H, H * .06 * (.5 + glow), (255, 255, 255), glow, angle=t * 40, add=True)
    elif kind in ('splash', 'drip', 'bubbles', 'debris', 'confetti', 'leaves', 'twinkle'):
        n = dict(splash=22, drip=5, bubbles=14, debris=12, confetti=40, leaves=10, twinkle=10)[kind]
        for k in range(n):
            b = random.Random(seed * 13 + k)
            if kind == 'splash':
                period = .6
                age = (t + b.random() * .1) % period
                ang = b.uniform(-math.pi * .95, -math.pi * .05)
                sp = H * b.uniform(.2, .55)
                px, py = x + math.cos(ang) * sp * age, y + math.sin(ang) * sp * age + H * 1.6 * age * age
                cv2.circle(frame, (int(px), int(py)), max(2, int(H * .007)), (230, 200, 120), -1, cv2.LINE_AA)
            elif kind == 'drip':
                phase = (t * .8 + k / n) % 1
                px, py = x + (k - n / 2) * W * .03, y - H * .15 + phase * H * .3
                cv2.ellipse(frame, (int(px), int(py)), (max(2, int(H * .006)), max(3, int(H * .011))), 0, 0, 360, (220, 170, 90), -1, cv2.LINE_AA)
            elif kind == 'bubbles':
                phase = (t * .4 + k / n) % 1
                px, py = x + b.uniform(-.08, .08) * W + math.sin(t * 3 + k) * W * .01, y - phase * H * .45
                cv2.circle(frame, (int(px), int(py)), max(2, int(H * (.006 + .012 * b.random()))), (240, 230, 210), max(1, lw // 2), cv2.LINE_AA)
            elif kind == 'debris':
                phase = (t * b.uniform(.6, 1.1) + b.random()) % 1
                px, py = x + b.uniform(-.25, .25) * W, phase * H * 1.1 - H * .05
                s = H * b.uniform(.008, .02)
                ang = t * 5 + k
                pts = np.array([(px + s * math.cos(ang + q * 2.1), py + s * math.sin(ang + q * 2.1)) for q in range(3)], np.int32)
                cv2.fillPoly(frame, [pts], (110, 120, 130), cv2.LINE_AA)
            elif kind == 'confetti':
                phase = (t * b.uniform(.25, .45) + b.random()) % 1
                px = b.random() * W + math.sin(t * 2 + k) * W * .02
                py = phase * H * 1.1 - H * .05
                tone = list(COLOURS.values())[k % 10]
                cv2.rectangle(frame, (int(px), int(py)), (int(px + H * .012), int(py + H * .006 * (1 + math.sin(t * 9 + k)))), tone, -1)
            elif kind == 'leaves':
                phase = (t * b.uniform(.15, .3) + b.random()) % 1
                px, py = (phase * 1.4 - .2) * W, b.uniform(.1, .8) * H + math.sin(t * 2 + k) * H * .04
                cv2.ellipse(frame, (int(px), int(py)), (max(3, int(H * .012)), max(2, int(H * .006))), (t * 200 + k * 50) % 180, 0, 360,
                            (60, 140, 110) if k % 2 else (40, 120, 200), -1, cv2.LINE_AA)
            else:
                px, py = x + b.uniform(-.2, .2) * W, y + b.uniform(-.2, .1) * H
                s = H * .02 * abs(math.sin(t * 4 + k * 1.7))
                cv2.line(frame, (int(px - s), int(py)), (int(px + s), int(py)), (255, 255, 255), lw, cv2.LINE_AA)
                cv2.line(frame, (int(px), int(py - s)), (int(px), int(py + s)), (255, 255, 255), lw, cv2.LINE_AA)
    elif kind in ('glow', 'blink', 'pulse_ring'):
        pulse = .5 + .5 * math.sin(t * (7 if kind == 'blink' else 3))
        if kind == 'pulse_ring':
            for k in range(3):
                ph = (t * .8 + k / 3) % 1
                cv2.circle(frame, (int(x), int(y)), int(H * (.03 + .2 * ph)), c, max(1, int(lw * (1 - ph) * 2)), cv2.LINE_AA)
        else:
            layer = np.zeros_like(frame)
            tone = c if spec.get('colour') else (120, 255, 170)
            cv2.circle(layer, (int(x), int(y)), int(H * (.05 + .03 * pulse)), tone, -1, cv2.LINE_AA)
            _blur_add(np, cv2, frame, layer, H / 40, .55 + .45 * (pulse if kind == 'blink' else .6))
    elif kind == 'flash_text':
        if label and (int(t * 3) % 2 == 0 or u > .6):
            _text(cv2, frame, label, x, y, H * .07, c if spec.get('colour') else (80, 80, 230))
    elif kind == 'burst':
        # a comic sound word with a star behind it (the references: CLUNK)
        grow = min(1., u / .15)
        r = H * .12 * grow
        pts = np.array([(x + r * (1 if q % 2 == 0 else .55) * math.cos(q * math.pi / 8), y + r * (1 if q % 2 == 0 else .55) * math.sin(q * math.pi / 8))
                        for q in range(16)], np.int32)
        cv2.fillPoly(frame, [pts], (90, 220, 250), cv2.LINE_AA)
        cv2.polylines(frame, [pts], True, INK, lw, cv2.LINE_AA)
        if label:
            _text(cv2, frame, label, x, y, H * .065 * grow, (245, 245, 245))
    elif kind == 'shockwave':
        ph = min(1., u * 1.5)
        cv2.ellipse(frame, (int(x), int(y)), (int(W * .4 * ph), int(H * .08 * ph)), 0, 0, 360, (245, 245, 245), max(1, int(lw * 2 * (1 - ph))), cv2.LINE_AA)
    elif kind in ('beam', 'searchlight', 'spray', 'pour'):
        if kind == 'searchlight':
            ang = math.sin(t * .9) * .6
            tip = (x + math.sin(ang) * H * .9, y + math.cos(ang) * H * .9)
            layer = np.zeros_like(frame)
            side = H * .12
            pts = np.array([(x, y), (tip[0] - side, tip[1]), (tip[0] + side, tip[1])], np.int32)
            cv2.fillPoly(layer, [pts], (200, 245, 255))
            _blur_add(np, cv2, frame, layer, H / 60, .35)
        elif kind == 'pour':
            layer = np.zeros_like(frame)
            cv2.line(layer, (int(x), int(y)), (int(x), int(H * .95)), (230, 190, 110), max(6, int(H * .02)), cv2.LINE_AA)
            _blur_add(np, cv2, frame, layer, H / 150, .9)
        else:
            reach = min(1., t / .35)
            length = W * .55
            pts = np.array([(x + facing * length * q * reach, y - H * .16 * math.sin(q * reach * math.pi * .9) + H * .22 * (q * reach) ** 2) if kind == 'spray'
                            else (x + facing * W * .9 * q, y - H * .18 * q) for q in [i / 27 for i in range(28)]], np.int32)
            tone = (255, 250, 245) if kind == 'spray' else c if spec.get('colour') else (90, 90, 255)
            layer = np.zeros_like(frame)
            cv2.polylines(layer, [pts], False, tone, max(8, int(H * .03)), cv2.LINE_AA)
            _blur_add(np, cv2, frame, layer, H / 120, .8)
            cv2.polylines(frame, [pts], False, tone, max(3, int(H * .008)), cv2.LINE_AA)
    elif kind == 'rising_water':
        level = H * (1 - (.12 + .3 * u))
        layer = frame.copy()
        wave = np.array([(int(q), int(level + math.sin(q / W * 18 + t * 3) * H * .008)) for q in range(0, W + 20, 20)] + [(W, H), (0, H)], np.int32)
        cv2.fillPoly(layer, [wave], (200, 150, 70))
        cv2.addWeighted(layer, .45, frame, .55, 0, frame)
    elif kind == 'speed_lines':
        for k in range(18):
            b = random.Random(seed + k)
            yy = b.uniform(.1, .9) * H
            xx = ((t * 3 + b.random()) % 1) * W * 1.3 - W * .15
            cv2.line(frame, (int(xx), int(yy)), (int(xx - W * .15), int(yy)), (240, 240, 240), lw, cv2.LINE_AA)
    elif kind in ('zzz', 'sweat', 'exclaim', 'question', 'hearts', 'notes'):
        hx, hy = (hand[0], hand[1] - H * .2) if hand else (x, y - H * .15)
        if kind == 'zzz':
            for k in range(3):
                ph = (t * .5 + k / 3) % 1
                _text(cv2, frame, 'Z', hx + ph * W * .05, hy - ph * H * .12, H * (.03 + .03 * ph), (245, 245, 245))
        elif kind == 'sweat':
            ph = (t * .9) % 1
            cv2.ellipse(frame, (int(hx + W * .03), int(hy + ph * H * .06)), (max(2, int(H * .007)), max(3, int(H * .012))), 0, 0, 360, (240, 210, 140), -1, cv2.LINE_AA)
        elif kind in ('exclaim', 'question'):
            pop = min(1., u / .12)
            _text(cv2, frame, '!' if kind == 'exclaim' else '?', hx, hy - H * .03, H * .09 * pop, (60, 200, 245))
        else:
            for k in range(3):
                ph = (t * .4 + k / 3) % 1
                px, py = hx + math.sin(t * 2 + k) * W * .02, hy - ph * H * .15
                if kind == 'hearts':
                    s = H * .015
                    cv2.circle(frame, (int(px - s * .5), int(py)), int(s * .6), (90, 80, 230), -1, cv2.LINE_AA)
                    cv2.circle(frame, (int(px + s * .5), int(py)), int(s * .6), (90, 80, 230), -1, cv2.LINE_AA)
                    cv2.fillPoly(frame, [np.array([(px - s, py + s * .1), (px + s, py + s * .1), (px, py + s * 1.2)], np.int32)], (90, 80, 230), cv2.LINE_AA)
                else:
                    cv2.circle(frame, (int(px), int(py)), max(2, int(H * .01)), INK, -1, cv2.LINE_AA)
                    cv2.line(frame, (int(px + H * .009), int(py)), (int(px + H * .009), int(py - H * .035)), INK, lw, cv2.LINE_AA)
    elif kind in ('birds', 'clouds'):
        for k in range(6 if kind == 'birds' else 4):
            b = random.Random(seed * 5 + k)
            sp = b.uniform(.04, .09) if kind == 'birds' else b.uniform(.01, .025)
            px = ((b.random() + t * sp) % 1.3 - .15) * W
            py = b.uniform(.08, .3) * H
            if kind == 'birds':
                flap = math.sin(t * 9 + k) * H * .01
                s = H * .015
                cv2.polylines(frame, [np.array([(px - s, py - flap), (px, py), (px + s, py - flap)], np.int32)], False, INK, lw, cv2.LINE_AA)
            else:
                for q in range(3):
                    cv2.ellipse(frame, (int(px + q * H * .05), int(py)), (int(H * .06), int(H * .03)), 0, 0, 360, (245, 245, 245), -1, cv2.LINE_AA)
    elif kind in ('vehicle', 'plane', 'boat', 'ball'):
        what = str(spec.get('what') or '').lower()
        moving = spec.get('moving', True)
        direction = -1 if spec.get('where') == 'right' else 1
        travel = (u - .5) * W * .6 * direction if moving else 0
        px = x + travel
        if kind == 'vehicle':
            body = c if spec.get('colour') else colour('red' if re.search(r'fire|ambulance', what) else 'yellow' if 'bus' in what or 'taxi' in what else 'blue')
            L, Hh = W * .26, H * .12
            top = H * .86 - Hh          # on the floor line of a wide shot, not in the air
            cv2.rectangle(frame, (int(px - L / 2), int(top)), (int(px + L / 2), int(top + Hh)), body, -1)
            cv2.rectangle(frame, (int(px - L / 2), int(top)), (int(px + L / 2), int(top + Hh)), INK, lw)
            cab = (px + direction * L * .3, top + Hh * .15)
            cv2.rectangle(frame, (int(cab[0] - L * .1), int(cab[1])), (int(cab[0] + L * .1), int(cab[1] + Hh * .45)), (110, 70, 40), -1)
            cv2.line(frame, (int(px - L / 2), int(top + Hh * .7)), (int(px + L / 2), int(top + Hh * .7)), (245, 245, 245), lw)
            spin = t * 8 * direction
            for wx in (px - L * .32, px + L * .32):
                cv2.circle(frame, (int(wx), int(top + Hh)), int(Hh * .28), INK, -1, cv2.LINE_AA)
                cv2.line(frame, (int(wx), int(top + Hh)), (int(wx + math.cos(spin) * Hh * .2), int(top + Hh + math.sin(spin) * Hh * .2)), (160, 160, 160), lw)
            if label:
                _text(cv2, frame, label, px - direction * L * .08, top + Hh * .42, H * .03, (245, 245, 245))
            if 'fire' in what and (spec.get('spray') or 'spray' in what or 'water' in what):
                draw(np, cv2, frame, dict(kind='spray', where='center'), t, u, W, H, seed, hand=(px + direction * L * .1, top), facing=direction)
        elif kind == 'plane':
            py = H * (.2 - .06 * u)
            s = H * .06
            cv2.ellipse(frame, (int(px), int(py)), (int(s * 2.2), int(s * .45)), 0, 0, 360, (240, 240, 240), -1, cv2.LINE_AA)
            cv2.ellipse(frame, (int(px), int(py)), (int(s * 2.2), int(s * .45)), 0, 0, 360, INK, lw, cv2.LINE_AA)
            cv2.fillPoly(frame, [np.array([(px - s * .3, py), (px + s * .3, py), (px - s * .5, py + s * 1.1)], np.int32)], (200, 200, 200), cv2.LINE_AA)
        elif kind == 'boat':
            bob = math.sin(t * 2) * H * .01
            s = H * .08
            hull = np.array([(px - s * 2, y + bob), (px + s * 2, y + bob), (px + s * 1.4, y + s * .7 + bob), (px - s * 1.4, y + s * .7 + bob)], np.int32)
            cv2.fillPoly(frame, [hull], c if spec.get('colour') else (60, 60, 200), cv2.LINE_AA)
            cv2.polylines(frame, [hull], True, INK, lw, cv2.LINE_AA)
            cv2.rectangle(frame, (int(px - s * .6), int(y - s * .7 + bob)), (int(px + s * .6), int(y + bob)), (240, 240, 240), -1)
        else:
            bounce = abs(math.sin(t * 5)) * H * .15
            cv2.circle(frame, (int(px), int(y + H * .2 - bounce)), int(H * .03), c if spec.get('colour') else (60, 60, 210), -1, cv2.LINE_AA)
            cv2.circle(frame, (int(px), int(y + H * .2 - bounce)), int(H * .03), INK, lw, cv2.LINE_AA)
    elif kind in ('fan', 'wheel', 'clock'):
        r = H * .08
        cv2.circle(frame, (int(x), int(y)), int(r), (235, 235, 235) if kind != 'wheel' else INK, -1, cv2.LINE_AA)
        cv2.circle(frame, (int(x), int(y)), int(r), INK, lw, cv2.LINE_AA)
        if kind == 'clock':
            for hand_len, speed in ((.8, 6.), (.5, .5)):
                a = t * speed - math.pi / 2
                cv2.line(frame, (int(x), int(y)), (int(x + math.cos(a) * r * hand_len), int(y + math.sin(a) * r * hand_len)), INK, lw, cv2.LINE_AA)
        else:
            for k in range(3 if kind == 'fan' else 6):
                a = t * (9 if kind == 'fan' else 5) + k * 2 * math.pi / (3 if kind == 'fan' else 6)
                tip = (x + math.cos(a) * r * .9, y + math.sin(a) * r * .9)
                if kind == 'fan':
                    cv2.ellipse(frame, (int((x + tip[0]) / 2), int((y + tip[1]) / 2)), (int(r * .45), int(r * .15)), math.degrees(a), 0, 360, c if spec.get('colour') else (150, 150, 150), -1, cv2.LINE_AA)
                else:
                    cv2.line(frame, (int(x), int(y)), (int(tip[0]), int(tip[1])), (170, 170, 170), lw, cv2.LINE_AA)
    elif kind == 'door_slide':
        gap = W * .12 * (u if spec.get('open', True) else 1 - u)
        for side in (-1, 1):
            cv2.rectangle(frame, (int(x + side * gap), int(y - H * .25)), (int(x + side * (gap + W * .12)), int(y + H * .2)), (200, 210, 215), -1)
            cv2.rectangle(frame, (int(x + side * gap), int(y - H * .25)), (int(x + side * (gap + W * .12)), int(y + H * .2)), INK, lw)
    elif kind == 'pendulum':
        a = math.sin(t * 2.2) * .5
        tip = (x + math.sin(a) * H * .25, H * .05 + math.cos(a) * H * .25)
        cv2.line(frame, (int(x), int(H * .05)), (int(tip[0]), int(tip[1])), INK, lw, cv2.LINE_AA)
        layer = np.zeros_like(frame)
        cv2.circle(layer, (int(tip[0]), int(tip[1]) + int(H * .03)), int(H * .12), (170, 235, 250), -1)
        _blur_add(np, cv2, frame, layer, H / 40, .35)
        cv2.circle(frame, (int(tip[0]), int(tip[1])), int(H * .025), (120, 230, 250), -1, cv2.LINE_AA)
        cv2.circle(frame, (int(tip[0]), int(tip[1])), int(H * .025), INK, lw, cv2.LINE_AA)
    elif kind == 'flag':
        pole = (x, y - H * .2)
        cv2.line(frame, (int(x), int(y + H * .1)), (int(pole[0]), int(pole[1])), INK, lw, cv2.LINE_AA)
        pts = [(pole[0] + q * W * .09, pole[1] + math.sin(q * 5 - t * 6) * H * .012 * q) for q in [i / 10 for i in range(11)]]
        pts += [(px_, py_ + H * .07) for px_, py_ in reversed(pts)]
        cv2.fillPoly(frame, [np.array(pts, np.int32)], c if spec.get('colour') else (60, 60, 210), cv2.LINE_AA)
    return frame

