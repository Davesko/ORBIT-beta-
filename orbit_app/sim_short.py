"""ORBIT's own 2D ball-physics short renderer (vertical 1080x1920, collision sounds, no narration).

A simulation spec (see BLOCKS) is simulated several times without drawing, the best run is picked and only that one is
rendered frame by frame. Runs in the media runtime (numpy, OpenCV, Pillow):
    python3 sim_short.py spec.json out.mp4
Written for ORBIT; Kobold's Szimgyár works the same way with its own engine, nothing of its code is used here.
"""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

W, H, FPS, SUB = 1080, 1920, 30, 4
CX, CY = W / 2, H * 0.53
R_MAX = 470

CONTAINERS = ('circle', 'ring', 'box', 'hexagon', 'cup', 'pegboard', 'empty')
WHEN = ('ball_wall', 'ball_ball', 'every_seconds', 'escape')
WHAT = ('split', 'grow', 'shrink', 'speed_up', 'new_ball', 'gap_grow', 'container_shrink', 'container_grow', 'color_change')
ENDS = ('ball_count', 'escape', 'time', 'full', 'last_ball')
COUNTERS = ('balls', 'hits', 'escaped', 'time', 'none')
INSTRUMENTS = ('marimba', 'piano', 'bell', '8bit', 'pop', 'pluck')
PALETTES = {'neon': ['#ff3d7f', '#3dd6ff', '#b4ff3d', '#ffd23d', '#b06bff'], 'pastel': ['#ffb3c7', '#a8e6ff', '#c9ffb3', '#fff0a8', '#d9c2ff'],
            'sunset': ['#ff6b3d', '#ff3d6b', '#ffb23d', '#ff8fd0', '#ffd9a8'], 'mono': ['#ffffff', '#d8d8d8', '#bdbdbd', '#f0f0f0', '#e0e0e0']}

BLOCKS = """ORBIT simulation engine (vertical 1080x1920 short, 30 fps, collision sounds, no narration). Write ONE JSON spec:
{"title": "short English title", "question": "the on-screen hook question, max 60 chars, English",
 "container": {"type": "circle|ring|box|hexagon|cup|pegboard|empty", "size": 0.3-1.0, "rotation_speed": -180..180 (deg/s),
               "gap_degrees": 0-120 (opening in ring/circle/hexagon; balls escape through it), "shrink_per_second": 0-0.08},
 "balls": {"count": 1-40, "radius": 8-80, "speed": 200-1600, "bounciness": 0.6-1.08, "color": "rainbow|single|team"},
 "gravity": 0-2500,
 "rule": {"when": "ball_wall|ball_ball|every_seconds|escape", "what": "split|grow|shrink|speed_up|new_ball|gap_grow|container_shrink|container_grow|color_change",
          "value": number (seconds for every_seconds; amount for grow/shrink/speed), "probability": 0-1, "cooldown": 0-5},
 "end": {"type": "ball_count|escape|time|full|last_ball", "value": number},
 "counter": "balls|hits|escaped|time|none",
 "sound": {"instrument": "marimba|piano|bell|8bit|pop|pluck", "melody": "pentatonic|rising"},
 "palette": "neon|pastel|sunset|mono", "max_seconds": 15-70}
One container, one continuous process, exactly one main rule. The end condition must answer the question."""


def _num(x, lo, hi, default):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(x) else max(lo, min(hi, x))


def _pick(x, allowed, default):
    x = str(x or '').lower()
    return next((a for a in allowed if a == x), next((a for a in allowed if a in x or x in a), default)) if x else default


def _find(d, *keys):
    """A value from a free-form plan: the first key that appears anywhere (nested) in it."""
    if isinstance(d, dict):
        for k, v in d.items():
            if any(key in str(k).lower() for key in keys) and not isinstance(v, (dict, list)):
                return v
        for v in d.values():
            got = _find(v, *keys)
            if got is not None:
                return got
    return None


def normalize(spec):
    """Any plan (ORBIT spec or an agent's free-form JSON) → a safe, complete spec."""
    spec = spec if isinstance(spec, dict) else {}
    text = json.dumps(spec, ensure_ascii=False).lower()
    c, b, r, e, snd = (spec.get(k) if isinstance(spec.get(k), dict) else {} for k in ('container', 'balls', 'rule', 'end', 'sound'))
    env = spec.get('environment') if isinstance(spec.get('environment'), dict) else {}
    ctype = c.get('type') or env.get('type') or _find(spec, 'container', 'arena') or ''
    ctype = 'hexagon' if 'hex' in str(ctype).lower() or (not c.get('type') and 'hexagon' in text) else _pick(ctype, CONTAINERS, 'ring' if 'gap' in text or 'escape' in text else 'circle')
    shrink = _num(c.get('shrink_per_second'), 0, .08, .012 if 'shrink' in text else 0)
    when = _pick(r.get('when') or ('ball_wall' if 'wall' in text else 'every_seconds' if 'timer' in text else ''), WHEN, 'ball_wall')
    what = _pick(r.get('what') or ('split' if 'split' in text else 'grow' if 'grow' in text else ''), WHAT, 'split')
    end_type = _pick(e.get('type') or ('ball_count' if what in ('split', 'new_ball') else ''), ENDS, 'time')
    out = dict(
        title=str(spec.get('title') or _find(spec, 'title') or 'Simulation')[:80],
        question=str(spec.get('question') or _find(spec, 'question', 'hook') or '')[:70],
        container=dict(type=ctype, size=_num(c.get('size'), .3, 1, .9), rotation_speed=_num(c.get('rotation_speed'), -180, 180, 30 if ctype in ('ring', 'hexagon') else 0),
                       gap_degrees=_num(c.get('gap_degrees'), 0, 120, 28 if ctype == 'ring' else 0), shrink_per_second=shrink),
        balls=dict(count=int(_num(b.get('count', _find(spec, 'initial_count', 'count')), 1, 40, 1)), radius=_num(b.get('radius'), 8, 80, 34),
                   speed=_num(b.get('speed'), 200, 1600, 700), bounciness=_num(b.get('bounciness', _find(spec, 'restitution', 'bounc')), .6, 1.08, .72 if ctype == 'cup' else 1.0),
                   color=_pick(b.get('color'), ('rainbow', 'single', 'team'), 'rainbow')),
        gravity=_num(spec.get('gravity') if not isinstance(spec.get('gravity'), dict) else None, 0, 2500, 900),
        rule=dict(when=when, what=what, value=_num(r.get('value'), 0, 60, 2 if when == 'every_seconds' else 1), probability=_num(r.get('probability'), 0, 1, 1),
                  cooldown=_num(r.get('cooldown'), 0, 5, .15)),
        end=dict(type=end_type, value=_num(e.get('value', _find(spec, 'max_balls', 'threshold')), 1, 1500, 300 if end_type == 'ball_count' else 30)),
        counter=_pick(spec.get('counter'), COUNTERS, 'balls' if what in ('split', 'new_ball') else 'hits'),
        sound=dict(instrument=_pick(snd.get('instrument'), INSTRUMENTS, 'marimba'), melody=_pick(snd.get('melody'), ('pentatonic', 'rising'), 'pentatonic')),
        palette=_pick(spec.get('palette'), tuple(PALETTES), 'neon'),
        max_seconds=_num(spec.get('max_seconds'), 15, 70, 45))
    if out['rule']['when'] == 'ball_ball' and out['balls']['count'] < 2:
        out['balls']['count'] = 2
    if not out['question']:
        out['_question_default'] = True
        out['question'] = question(out)
    if out['end']['type'] == 'escape' and out['container']['gap_degrees'] == 0:
        out['container']['gap_degrees'] = 24
    return out


class Sim:
    """Balls inside one container. Positions in pixels, y down."""

    def __init__(self, spec, seed):
        import numpy as np
        self.np, self.s, self.rng = np, spec, np.random.default_rng(seed)
        c, b = spec['container'], spec['balls']
        self.R = R_MAX * c['size']
        self.angle, self.t = 0.0, 0.0
        self.gap = math.radians(c['gap_degrees'])
        n = b['count']
        a = self.rng.uniform(0, 2 * math.pi, n)
        self.p = np.stack([CX + np.cos(a) * self.R * .3 * (n > 1), CY + np.sin(a) * self.R * .3 * (n > 1)], 1).astype(float)
        d = self.rng.uniform(0, 2 * math.pi, n)
        self.v = np.stack([np.cos(d), np.sin(d)], 1) * b['speed']
        self.r = np.full(n, b['radius'], float)
        self.col = (np.arange(n) % 5) if b['color'] != 'single' else np.zeros(n, int)
        self.hits = self.escaped = 0
        self.events = []          # (time, kind, ball index)
        self.cool = 0.0
        self.ended = None
        self.pegs = [(CX + x * self.R * .5, CY + y * self.R * .45) for y in (-1, 0, 1) for x in ((-1, 0, 1) if y != 0 else (-.5, .5))] if c['type'] == 'pegboard' else []

    # walls ---------------------------------------------------------------
    def polygon(self):
        t = self.s['container']['type']
        if t == 'hexagon':
            return [(CX + self.R * math.cos(self.angle + k * math.pi / 3), CY + self.R * math.sin(self.angle + k * math.pi / 3)) for k in range(6)]
        if t in ('box', 'pegboard', 'cup'):
            h = self.R
            pts = [(-h, -h), (h, -h), (h, h), (-h, h)]
            ca, sa = math.cos(self.angle), math.sin(self.angle)
            return [(CX + x * ca - y * sa, CY + x * sa + y * ca) for x, y in pts]
        return None

    def in_gap(self, ang):
        if self.gap <= 0:
            return False
        d = (ang - (self.angle - math.pi / 2) + math.pi) % (2 * math.pi) - math.pi
        return abs(d) < self.gap / 2

    def walls(self):
        np, p, v, r = self.np, self.p, self.v, self.r
        bounce = self.s['balls']['bounciness']
        hit = np.zeros(len(r), bool)
        gone = np.zeros(len(r), bool)
        t = self.s['container']['type']
        if t == 'empty':
            out = (p[:, 1] - r > H) | (p[:, 0] < -100) | (p[:, 0] > W + 100)
            return hit, out
        poly = self.polygon()
        if poly is None:            # circle / ring
            d = p - [CX, CY]
            dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
            over = dist + r > self.R
            ang = np.arctan2(d[:, 1], d[:, 0])
            through = np.array([self.in_gap(a) for a in ang]) if self.gap > 0 else np.zeros(len(r), bool)
            gone = (dist - r > self.R + 4) & through if self.gap > 0 else np.zeros(len(r), bool)
            if self.gap > 0:
                gone |= dist - r > self.R + 4 + 60      # pushed far out by a shrink: treat as escaped
            col = over & ~through & ~gone
            nrm = d / dist[:, None]
            vn = (v * nrm).sum(1)
            col &= vn > 0
            v[col] -= (1 + bounce) * vn[col, None] * nrm[col]
            p[col] = (CX, CY) + nrm[col] * (self.R - r[col])[:, None]
            hit |= col
            return hit, gone
        edges = list(zip(poly, poly[1:] + poly[:1]))
        if t == 'cup':
            edges = [e for i, e in enumerate(edges) if i != 0]   # open top
        if self.gap > 0 and t == 'hexagon':
            edges = edges[1:]                                     # one side open
        inside = np.ones(len(r), bool)
        for (x1, y1), (x2, y2) in edges:
            ex, ey = x2 - x1, y2 - y1
            L = math.hypot(ex, ey)
            nx, ny = -ey / L, ex / L                              # inward normal (clockwise in screen coords)
            if (CX - x1) * nx + (CY - y1) * ny < 0:
                nx, ny = -nx, -ny
            dist = (p[:, 0] - x1) * nx + (p[:, 1] - y1) * ny
            along = ((p[:, 0] - x1) * ex + (p[:, 1] - y1) * ey) / L
            on = (along > -r) & (along < L + r)
            col = on & (dist < r) & (dist > -r * 2)
            vn = v[:, 0] * nx + v[:, 1] * ny
            col &= vn < 0
            v[col, 0] -= (1 + bounce) * vn[col] * nx
            v[col, 1] -= (1 + bounce) * vn[col] * ny
            push = (r - dist)[col]
            p[col, 0] += push * nx
            p[col, 1] += push * ny
            hit |= col
            inside &= dist > -r * 2
        closed = t in ('box', 'pegboard') or (t == 'hexagon' and self.gap <= 0)
        if closed and (~inside).any():                # a shrinking wall must not delete balls: put them back inside
            out = ~inside
            k = int(out.sum())
            ang = self.rng.uniform(0, 2 * math.pi, k)
            rad = self.rng.uniform(0, self.R * .4, k)
            p[out, 0] = CX + np.cos(ang) * rad
            p[out, 1] = CY + np.sin(ang) * rad
            inside[:] = True
        gone = ~inside | (p[:, 1] > H + 200) | (p[:, 1] < -400)
        for px, py in self.pegs:
            d = p - [px, py]
            dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
            col = dist < r + 18
            nrm = d / dist[:, None]
            vn = (v * nrm).sum(1)
            col &= vn < 0
            v[col] -= (1 + bounce) * vn[col, None] * nrm[col]
            p[col] = (px, py) + nrm[col] * (r[col] + 18)[:, None]
            hit |= col
        return hit, gone

    def pairs(self):
        np, p, v, r = self.np, self.p, self.v, self.r
        n = len(r)
        if n < 2:
            return []
        if n <= 160:
            i, j = np.triu_indices(n, 1)
        else:                                     # sweep: neighbours in x order only
            order = np.argsort(p[:, 0])
            i = np.concatenate([order[:-k] for k in range(1, 9)])
            j = np.concatenate([order[k:] for k in range(1, 9)])
        d = p[j] - p[i]
        dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
        touch = dist < r[i] + r[j]
        i, j, d, dist = i[touch], j[touch], d[touch], dist[touch]
        if not len(i):
            return []
        nrm = d / dist[:, None]
        rel = ((v[i] - v[j]) * nrm).sum(1)
        app = rel > 0
        m_i, m_j = r[i] ** 2, r[j] ** 2
        imp = (2 * rel / (m_i + m_j))[:, None] * nrm
        np.add.at(v, i[app], -(imp * m_j[:, None])[app])
        np.add.at(v, j[app], (imp * m_i[:, None])[app])
        over = (r[i] + r[j] - dist)[:, None] * nrm / 2
        np.add.at(p, i, -over)
        np.add.at(p, j, over)
        return list(i[app])

    # rule -----------------------------------------------------------------
    def apply(self, idx):
        np, rule = self.np, self.s['rule']
        if self.t < self.cool or self.rng.random() > rule['probability'] or idx >= len(self.r):
            return
        self.cool = self.t + rule['cooldown']
        what, val = rule['what'], rule['value']
        if what in ('split', 'new_ball') and len(self.r) < 1500:
            r = max(7.0, self.r[idx] * (.82 if what == 'split' else 1))
            if what == 'split':
                self.r[idx] = r
            a = self.rng.uniform(0, 2 * math.pi)
            sp = max(np.hypot(*self.v[idx]), self.s['balls']['speed'] * .7)
            pos = self.p[idx] if what == 'split' else np.array([CX, CY - self.R * .4])
            self.p = np.vstack([self.p, pos + [math.cos(a) * 2, math.sin(a) * 2]])
            self.v = np.vstack([self.v, [math.cos(a) * sp, math.sin(a) * sp]])
            self.r = np.append(self.r, r)
            self.col = np.append(self.col, (self.col[idx] + 1) % 5 if self.s['balls']['color'] != 'single' else 0)
            self.events.append((self.t, 'add', idx))
        elif what == 'grow':
            self.r[idx] = min(self.R * .9, self.r[idx] + max(1, val))
        elif what == 'shrink':
            self.r[idx] = max(5, self.r[idx] - max(1, val))
        elif what == 'speed_up':
            self.v[idx] *= 1 + min(.3, max(.02, val / 20))
        elif what == 'gap_grow':
            self.gap = min(math.radians(170), self.gap + math.radians(max(1, val)))
        elif what == 'container_shrink':
            self.R = max(60, self.R - max(1, val))
        elif what == 'container_grow':
            self.R = min(R_MAX, self.R + max(1, val))
        elif what == 'color_change':
            self.col[idx] = (self.col[idx] + 1) % 5

    def step(self, dt):
        np, s = self.np, self.s
        self.t += dt
        self.angle += math.radians(s['container']['rotation_speed']) * dt
        if s['container']['shrink_per_second']:
            self.R = max(120, self.R * (1 - s['container']['shrink_per_second'] * dt))
            np.minimum(self.r, self.R * .25, out=self.r)
        self.v[:, 1] += s['gravity'] * dt
        cap = 2600
        sp = np.hypot(self.v[:, 0], self.v[:, 1])
        fast = sp > cap
        self.v[fast] *= (cap / sp[fast])[:, None]
        self.p += self.v * dt
        hit, gone = self.walls()
        touched = self.pairs()
        rule = s['rule']
        for i in np.flatnonzero(hit)[:6]:
            self.hits += 1
            self.events.append((self.t, 'wall', int(i)))
            if rule['when'] == 'ball_wall':
                self.apply(int(i))
        for i in touched[:4]:
            self.hits += 1
            self.events.append((self.t, 'ball', int(i)))
            if rule['when'] == 'ball_ball':
                self.apply(int(i))
        if rule['when'] == 'every_seconds' and self.t >= self.cool + max(.2, rule['value']):
            self.apply(int(self.rng.integers(len(self.r))))
        if gone.any():
            for i in np.flatnonzero(gone):
                self.escaped += 1
                self.events.append((self.t, 'escape', int(i)))
                if rule['when'] == 'escape':
                    self.apply(int(i))
            keep = ~gone[:len(self.r)] if len(gone) == len(self.r) else np.ones(len(self.r), bool)
            keep = np.concatenate([keep, np.ones(len(self.r) - len(keep), bool)])
            self.p, self.v, self.r, self.col = self.p[keep], self.v[keep], self.r[keep], self.col[keep]
        self.check_end()

    def fill(self):
        area = {'box': 4, 'pegboard': 4, 'cup': 4, 'hexagon': 2.6}.get(self.s['container']['type'], math.pi) * self.R ** 2
        return float(math.pi * (self.r ** 2).sum() / max(1.0, area))

    def check_end(self):
        e = self.s['end']
        kind, val = e['type'], e['value']
        if kind == 'ball_count' and len(self.r) >= val:
            self.ended = f'{len(self.r)} BALLS!'
        elif kind == 'escape' and self.escaped >= max(1, val):
            self.ended = 'ESCAPED!' if val <= 1 else f'{self.escaped} ESCAPED!'
        elif kind == 'full' and self.fill() >= .5:
            self.ended = 'FULL!'
        elif kind == 'last_ball' and len(self.r) <= 1:
            self.ended = 'LAST ONE!'
        elif kind == 'time' and self.t >= val:
            self.ended = f'{self.counter_text()}'
        elif len(self.r) == 0:
            self.ended = 'ALL GONE!'
        elif self.t >= self.s['max_seconds']:
            self.ended = 'TIME UP'

    def counter_text(self):
        c = self.s['counter']
        return {'balls': f'{len(self.r)} balls', 'hits': f'{self.hits} hits', 'escaped': f'{self.escaped} escaped',
                'time': f'{self.t:4.1f}s', 'none': ''}[c]


def run(spec, seed, frames=None):
    sim = Sim(spec, seed)
    dt = 1 / (FPS * SUB)
    while sim.ended is None:
        for _ in range(SUB):
            sim.step(dt)
            if sim.ended:
                break
        if frames is not None:
            frames(sim)
    return sim


def score(spec, sim):
    """Higher is better: the question is answered (not a time-out), late enough for tension, lively throughout."""
    t = sim.t
    answered = sim.ended not in ('TIME UP',) and spec['end']['type'] != 'time'
    good_len = 1 - min(1, abs(t - min(spec['max_seconds'] * .75, 40)) / 30)
    busy = min(1, len(sim.events) / max(1, t * 6))
    return answered * 2 + good_len + busy


def reachable(spec):
    """A goal the physics cannot reach ends in a limp time-out; the target is tuned to what a run really reaches."""
    e = spec['end']
    if e['type'] not in ('ball_count', 'escape'):
        return spec
    runs = [run(spec, seed) for seed in range(3)]
    target = min(spec['max_seconds'] * .8, 40)
    if e['type'] == 'ball_count':
        ends = sorted(r.t for r in runs)
        if all(r.ended != 'TIME UP' for r in runs) and ends[1] >= min(20, target * .6):
            return spec
        # A goal reached in a few seconds wastes the tension, an unreachable one ends limp: the goal is what a run
        # reaches at the short's ideal length.
        probe = json.loads(json.dumps(spec))
        probe['end']['value'], probe['max_seconds'] = 10 ** 6, target
        reached = sorted(len(run(probe, seed).r) for seed in range(3))[1]
        e['value'] = max(5, int(reached * .95) // 5 * 5)
    elif any(r.ended != 'TIME UP' for r in runs):
        return spec
    else:
        e['value'] = max(1, int(sorted(r.escaped for r in runs)[1] * .8))
        if not any(r.escaped for r in runs):
            spec['container']['gap_degrees'] = max(30, spec['container']['gap_degrees'] * 1.5)
    spec['question'] = question(spec)                # the hook must ask what the run really answers
    return spec


def question(spec):
    e, b = spec['end'], spec['balls']
    return {'ball_count': f"Can {b['count']} ball{'s' if b['count'] > 1 else ''} become {int(e['value'])}?",
            'escape': 'Will it escape?' if e['value'] <= 1 else f"Can {int(e['value'])} balls escape?",
            'full': 'Will it fill up?', 'last_ball': 'Which one survives?'}.get(e['type'], 'What happens next?')


def choose(spec, tries=6):
    reachable(spec)
    best = max(((score(spec, run(spec, seed)), seed) for seed in range(tries)), key=lambda x: x[0])
    return best[1]


# drawing ------------------------------------------------------------------------
def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (4, 2, 0))   # BGR for OpenCV


def text_layer(spec):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Black.ttf', 74)
    except OSError:
        font = ImageFont.load_default()
    words, lines, cur = spec['question'].upper().split(), [], ''
    for w_ in words:
        if d.textlength((cur + ' ' + w_).strip(), font=font) > W - 140:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + ' ' + w_).strip()
    lines.append(cur)
    y = 150
    for line in lines[:3]:
        tw = d.textlength(line, font=font)
        d.text(((W - tw) / 2, y), line, font=font, fill=(255, 255, 255, 255), stroke_width=7, stroke_fill=(0, 0, 0, 255))
        y += 92
    return np.array(img)


def render(spec, seed, out, tmp):
    import cv2
    import numpy as np
    pal = [_rgb(c) for c in PALETTES[spec['palette']]]
    layer = text_layer(spec)
    alpha = layer[:, :, 3:4] / 255.0
    rgb = layer[:, :, [2, 1, 0]].astype(np.float32)
    base = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        k = y / H
        base[y] = (int(28 + 20 * k), int(14 + 8 * k), int(16 + 30 * (1 - k)))
    ff = Path(sys.executable).with_name('ffmpeg')
    ff = str(ff) if ff.exists() else 'ffmpeg'
    silent = Path(tmp) / 'video.mp4'
    proc = subprocess.Popen([ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', str(silent)], stdin=subprocess.PIPE)
    trail = base.copy()

    def draw(sim, final=None):
        nonlocal trail
        frame = cv2.addWeighted(trail, .72, base, .28, 0)
        poly = sim.polygon()
        white = (245, 245, 245)
        t = spec['container']['type']
        if poly is None and t != 'empty':
            start = math.degrees(sim.angle - math.pi / 2 + sim.gap / 2)
            span = 360 - math.degrees(sim.gap)
            cv2.ellipse(frame, (int(CX), int(CY)), (int(sim.R), int(sim.R)), 0, start, start + span, white, 8, cv2.LINE_AA)
        elif poly is not None:
            pts = [(int(x), int(y)) for x, y in poly]
            segs = list(zip(pts, pts[1:] + pts[:1]))
            if t == 'cup':
                segs = segs[1:]
            if t == 'hexagon' and sim.gap > 0:
                segs = segs[1:]
            for a, b in segs:
                cv2.line(frame, a, b, white, 8, cv2.LINE_AA)
        for px, py in sim.pegs:
            cv2.circle(frame, (int(px), int(py)), 18, white, -1, cv2.LINE_AA)
        for (x, y), r, c in zip(sim.p, sim.r, sim.col):
            if -100 < x < W + 100 and -100 < y < H + 100:
                cv2.circle(frame, (int(x), int(y)), max(2, int(r)), pal[int(c) % 5], -1, cv2.LINE_AA)
        trail = frame.copy()
        out_f = (frame.astype(np.float32) * (1 - alpha) + rgb * alpha).astype(np.uint8)
        label = final or sim.counter_text()
        if label:
            size = 2.6 if final else 2.0
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, size, 6)
            yy = int(CY + R_MAX + 190) if not final else int(CY)
            cv2.putText(out_f, label, ((W - tw) // 2, yy), cv2.FONT_HERSHEY_DUPLEX, size, (0, 0, 0), 14, cv2.LINE_AA)
            cv2.putText(out_f, label, ((W - tw) // 2, yy), cv2.FONT_HERSHEY_DUPLEX, size, (255, 255, 255), 6, cv2.LINE_AA)
        proc.stdin.write(out_f.tobytes())

    sim = run(spec, seed, frames=draw)
    for _ in range(int(FPS * 1.8)):
        draw(sim, final=sim.ended)
    proc.stdin.close()
    proc.wait()
    length = sim.t + 1.8
    audio = Path(tmp) / 'audio.wav'
    write_audio(spec, sim.events, length, audio)
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', str(silent), '-i', str(audio), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', str(out)], check=True)
    return dict(seconds=round(length, 1), ending=sim.ended, balls=int(len(sim.r)), hits=sim.hits, escaped=sim.escaped, seed=seed)


# sound --------------------------------------------------------------------------
def note(instrument, freq, rate=44100):
    import numpy as np
    n = int(rate * (.5 if instrument in ('bell', 'piano') else .25))
    t = np.arange(n) / rate
    if instrument == '8bit':
        w = np.sign(np.sin(2 * np.pi * freq * t)) * .5
        env = np.exp(-t * 14)
    elif instrument == 'pop':
        w = np.sin(2 * np.pi * (freq * 1.5) * t * (1 + 2 * np.exp(-t * 40)))
        env = np.exp(-t * 30)
    elif instrument == 'bell':
        w = np.sin(2 * np.pi * freq * t) + .5 * np.sin(2 * np.pi * freq * 2.76 * t) + .25 * np.sin(2 * np.pi * freq * 5.4 * t)
        env = np.exp(-t * 5)
    elif instrument == 'pluck':
        w = sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, 6))
        env = np.exp(-t * 11)
    elif instrument == 'piano':
        w = np.sin(2 * np.pi * freq * t) + .4 * np.sin(2 * np.pi * freq * 2 * t) + .15 * np.sin(2 * np.pi * freq * 3 * t)
        env = np.exp(-t * 6)
    else:  # marimba
        w = np.sin(2 * np.pi * freq * t) + .3 * np.sin(2 * np.pi * freq * 4 * t) * np.exp(-t * 30)
        env = np.exp(-t * 12)
    attack = np.minimum(1, t / .004)
    return w * env * attack


def write_audio(spec, events, length, path, rate=44100):
    import numpy as np
    buf = np.zeros(int(rate * (length + 1)), np.float32)
    scale = [0, 2, 4, 7, 9]
    base = 261.63
    step, last, cache = 0, -1.0, {}
    inst = spec['sound']['instrument']
    for t, kind, _ in events:
        if t - last < (.045 if kind != 'add' else .02):
            continue
        last = t
        if spec['sound']['melody'] == 'rising':
            k = min(step, 30)
        else:
            k = step % 15
        step += 1
        semis = scale[k % 5] + 12 * (k // 5)
        f = base * 2 ** (semis / 12) * (1.5 if kind == 'add' else 1)
        key = round(f, 1)
        if key not in cache:
            cache[key] = note(inst, f, rate).astype(np.float32)
        w = cache[key] * (.35 if kind != 'escape' else .6)
        i = int(t * rate)
        buf[i:i + len(w)] += w[:len(buf) - i]
    end = int(max(0, length - 1.8) * rate)
    chord = sum(note('bell', base * 2 ** (s / 12), rate) for s in (0, 4, 7, 12)) * .25
    buf[end:end + len(chord)] += chord[:len(buf) - end].astype(np.float32)
    peak = float(np.abs(buf).max()) or 1
    pcm = (np.tanh(buf / peak * 1.4) * 0.85 * 32767).astype(np.int16)
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm.tobytes())


def main(spec_path, out_path):
    import tempfile
    spec = normalize(json.loads(Path(spec_path).read_text(encoding='utf-8')))
    seed = choose(spec)
    with tempfile.TemporaryDirectory() as tmp:
        result = render(spec, seed, out_path, tmp)
    result['spec'] = spec
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
