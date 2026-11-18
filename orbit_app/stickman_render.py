"""Renders a stickman episode timeline into one silent MP4 (the media runtime's numpy, OpenCV and Pillow).

Shot kinds, from the two reference videos (15 Nov):
- wide: the painted place with the characters small in it (the establishing and most action shots)
- medium: the place pushed in, the characters at two thirds of the frame
- close: head and shoulders on a dark, blurred version of the place with a soft light behind the head
- insert: a painted close-up of one object (a button, a sign, a lock), with its label
- card: a flat infographic on cream paper (a big number, bars, a grid of days, a checklist, a versus, a counter)
- title: a chapter card ("PROBLEM 1 / THE GLASS")
Over every shot: a counter in the corner when the story keeps one (DAY 12), one spoken word of caption at a time, a
light paper grain and vignette.

Run: python3 stickman_render.py request.json"""
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import stickman_fx as moving_fx
import stickman_rig as rig

FONTS = {
    'caption': ('/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Black.ttf'),
    'title': ('/System/Library/Fonts/Supplemental/Arial Black.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
    'body': ('/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf'),
    'label': ('/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
}
PAPER = (208, 232, 244)      # BGR of #F4E8D0, the cards' cream
INK_TEXT = (43, 43, 43)
ACCENT = (59, 70, 200)       # a muted red
BLUE = (158, 110, 61)
GREY = (190, 196, 200)

# Layout per orientation: figure height and ground line as fractions of the frame height, per shot kind.
LAYOUT = {
    'landscape': dict(wide=(.34, .9), medium=(.64, .985), close=(1.5, None), top=(.13, .66), crowd=(.27, .86), caption=.84),
    'portrait': dict(wide=(.25, .8), medium=(.46, .9), close=(1.0, None), top=(.1, .62), crowd=(.19, .76), caption=.72),
}


def font(kind, size):
    from PIL import ImageFont
    for path in FONTS[kind]:
        if Path(path).is_file():
            return ImageFont.truetype(path, int(size))
    return ImageFont.load_default()


def text_image(text, kind, size, fill=(255, 255, 255), stroke=0, stroke_fill=(20, 20, 20), max_width=None):
    """RGBA numpy image of a text line, shrunk until it fits max_width."""
    import numpy as np
    from PIL import Image, ImageDraw
    while True:
        f = font(kind, size)
        box = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=f, stroke_width=stroke)
        w, h = box[2] - box[0], box[3] - box[1]
        if not max_width or w <= max_width or size < 14:
            break
        size *= .92
    img = Image.new('RGBA', (w + 4, h + 4), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - box[0], 2 - box[1]), text, font=f, fill=fill + (255,), stroke_width=stroke, stroke_fill=stroke_fill + (255,))
    return np.array(img)[:, :, [2, 1, 0, 3]]


def paste(frame, rgba, x, y, alpha=1.):
    """Alpha-composite an RGBA image with its top-left corner at (x, y), clipped to the frame."""
    import numpy as np
    h, w = rgba.shape[:2]
    H, W = frame.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    part = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = part[:, :, 3:4].astype(np.float32) / 255. * alpha
    roi = frame[y0:y1, x0:x1, :3]
    roi[:] = (roi * (1 - a) + part[:, :, :3] * a).astype(np.uint8)


def ease(u):
    u = min(1., max(0., u))
    return u * u * (3 - 2 * u)


# ------------------------------------------------------------------ backgrounds

class Plates:
    def __init__(self, cv2, np, paths, W, H):
        self.cv2, self.np, self.W, self.H = cv2, np, W, H
        self.paths = paths or {}
        self.cache, self.dark = {}, {}

    def get(self, place):
        if place not in self.cache:
            path = self.paths.get(place) or self.paths.get(str(place).split('@')[0]) or next(iter(self.paths.values()), None)
            img = self.cv2.imread(str(path)) if path and Path(path).is_file() else None
            self.cache[place] = self.cover(img) if img is not None else self.fallback(place)
        return self.cache[place]

    def cover(self, img, W=None, H=None):
        W, H = W or self.W, H or self.H
        h, w = img.shape[:2]
        k = max(W / w, H / h)
        img = self.cv2.resize(img, (int(math.ceil(w * k)), int(math.ceil(h * k))), interpolation=self.cv2.INTER_CUBIC)
        y, x = (img.shape[0] - H) // 2, (img.shape[1] - W) // 2
        return img[y:y + H, x:x + W].copy()

    def fallback(self, place):
        """A plain wall and floor in a colour of its own when no painted plate exists (and for the tests)."""
        np, W, H = self.np, self.W, self.H
        r = random.Random(str(place))
        wall = np.array([r.randint(120, 200), r.randint(120, 190), r.randint(110, 180)], np.float32)
        img = np.zeros((H, W, 3), np.float32)
        horizon = int(H * .72)
        for y in range(H):
            img[y] = wall * (.82 + .18 * y / horizon) if y < horizon else wall * .55 * (1 - .25 * (y - horizon) / (H - horizon))
        return img.astype(np.uint8)

    def blurred(self, place):
        """The close-up ground: the place itself, only a little soft and a little darker, so it stays readable
        (owner, 16 Nov: "a közeli kép egy nagyon elmosott kép, ez ne így legyen, lássuk a hátteret")."""
        if place not in self.dark:
            cv2, np = self.cv2, self.np
            img = self.get(place)
            img = cv2.GaussianBlur(img, (0, 0), max(1., self.H * .0035)).astype(np.float32) * .86
            self.dark[place] = np.clip(img, 0, 255).astype(np.uint8)
        return self.dark[place]

    def view(self, img, zoom, cx, cy, shake=(0, 0)):
        cv2, np = self.cv2, self.np
        m = np.float32([[zoom, 0, self.W / 2 - cx * zoom + shake[0]], [0, zoom, self.H / 2 - cy * zoom + shake[1]]])
        return cv2.warpAffine(img, m, (self.W, self.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ------------------------------------------------------------------ cards

def card_image(np, card, W, H, progress):
    """A flat infographic on cream paper. progress (0-1) animates what grows: bars, grid cells, list rows, a count."""
    frame = np.full((H, W, 3), PAPER, np.uint8)
    kind = card.get('type', 'stat')
    unit = H / 1080. if W >= H else W / 720.     # a phone shows a vertical card small: bigger type (16 Nov trial)
    top = H * (.2 if W >= H else .28)
    def centred(text, kind_, size, y, colour=INK_TEXT, max_w=W * .86):
        img = text_image(str(text), kind_, size * unit, fill=tuple(int(c) for c in colour[::-1]), max_width=max_w)
        paste(frame, img, (W - img.shape[1]) / 2, y)
        return y + img.shape[0]
    title = str(card.get('title') or '').upper()
    note = str(card.get('note') or '')
    if kind == 'title':
        y = H * .36
        y = centred(str(card.get('label') or '').upper(), 'label', 40, y, (120, 120, 120)) + 18 * unit
        centred(title or str(card.get('text') or '').upper(), 'title', 96, y)
        return frame
    if not title and kind in ('list', 'bars', 'grid', 'versus') and card.get('label'):
        title = str(card['label']).upper()        # "STATION STATUS" was never drawn above its list (16 Nov Short)
    if title:
        top = centred(title, 'title', 54, top) + 40 * unit
    if kind == 'stat':
        value = str(card.get('value') or '')
        y = centred(value, 'title', 190, top + 30 * unit, ACCENT)
        y = centred(str(card.get('label') or '').upper(), 'label', 52, y + 24 * unit)
    elif kind == 'counter':
        a, b = card.get('from', 0), card.get('to', 0)
        try:
            a, b = float(a), float(b)
            value = f"{int(round(a + (b - a) * ease(progress))):,}"
        except (TypeError, ValueError):
            value = str(card.get('to') or '')
        label = str(card.get('label') or '').upper()
        # the label above, the number big under it (16 Nov Short: one long line shrunk to a thin strip on a phone)
        y = top + 40 * unit
        if label:
            y = centred(label, 'label', 64, y, (120, 120, 120)) + 24 * unit
        y = centred(value, 'title', 330, y, ACCENT)
    elif kind == 'meter':
        import cv2
        try:
            a, b = float(card.get('from', 100)), float(card.get('to', 0))
        except (TypeError, ValueError):
            a, b = 100., 0.
        top_ = max(1., max(a, b)) if str(card.get('unit', '%')) != '%' else 100.
        v = a + (b - a) * ease(progress)
        frac = min(1., max(0., v / top_))
        colour = (80, 175, 70) if frac > .5 else (40, 190, 235) if frac > .2 else (60, 60, 210)
        icon = card.get('icon', 'battery')
        bw, bh = (W * .36, H * .26) if W >= H else (W * .62, H * .13)
        x0, y0 = (W - bw) / 2, top + 20 * unit
        lw = max(3, int(8 * unit))
        cv2.rectangle(frame, (int(x0), int(y0)), (int(x0 + bw), int(y0 + bh)), INK_TEXT, lw, cv2.LINE_AA)
        if icon == 'battery':
            cv2.rectangle(frame, (int(x0 + bw), int(y0 + bh * .3)), (int(x0 + bw + bw * .05), int(y0 + bh * .7)), INK_TEXT, -1, cv2.LINE_AA)
        pad = lw * 2
        if frac > 0:
            cv2.rectangle(frame, (int(x0 + pad), int(y0 + pad)), (int(x0 + pad + (bw - 2 * pad) * frac), int(y0 + bh - pad)), colour, -1)
        if icon != 'battery':
            for k in range(1, 10):
                xx = int(x0 + bw * k / 10)
                cv2.line(frame, (xx, int(y0 + bh * .7)), (xx, int(y0 + bh - lw)), INK_TEXT, max(1, lw // 3))
        unit_text = str(card.get('unit', '%'))[:6]
        number = f'{v:.0f}{unit_text}' if unit_text == '%' else f'{v:,.0f} {unit_text}'.strip()
        y = centred(number, 'title', 150, y0 + bh + 30 * unit, colour if frac <= .2 else INK_TEXT)
        if card.get('label'):
            y = centred(str(card['label']).upper(), 'label', 46, y + 10 * unit)
        top = y
    elif kind == 'bars':
        rows = (card.get('rows') or [])[:4]
        x0, x1 = W * .18, W * .82
        y = top + 20 * unit
        for k, row in enumerate(rows):
            grow = ease(progress * len(rows) - k * .6)
            label = text_image(str(row.get('label') or ''), 'body', 34 * unit, fill=INK_TEXT[::-1], max_width=W * .5)
            paste(frame, label, x0, y)
            y += label.shape[0] + 10 * unit
            bar_h = 46 * unit
            import cv2
            cv2.rectangle(frame, (int(x0), int(y)), (int(x1), int(y + bar_h)), (90, 90, 90), max(2, int(3 * unit)))
            try:
                value = min(1., max(0., float(row.get('value', 0))))
            except (TypeError, ValueError):
                value = 0.
            fill = int(x0 + 4 + (x1 - x0 - 8) * value * grow)
            if fill > x0 + 4:
                cv2.rectangle(frame, (int(x0 + 4), int(y + 4)), (fill, int(y + bar_h - 4)), BLUE if k % 2 == 0 else ACCENT, -1)
            text = str(row.get('text') or '')
            if text:
                t = text_image(text, 'body', 30 * unit, fill=INK_TEXT[::-1])
                paste(frame, t, x1 - t.shape[1] - 10 * unit, y + (bar_h - t.shape[0]) / 2)
            y += bar_h + 34 * unit
        top = y
    elif kind == 'grid':
        import cv2
        try:
            total = max(1, min(400, int(card.get('total') or 100)))
            marked = max(0, min(total, int(card.get('marked') or 0)))
        except (TypeError, ValueError):
            total, marked = 100, 1
        cols = max(1, int(math.ceil(math.sqrt(total * (2.4 if W >= H else 1.)))))
        rows = int(math.ceil(total / cols))
        area_w, area_h = W * .7, H * .42
        cell = min(area_w / cols, area_h / rows)
        x0 = (W - cell * cols) / 2
        shown = int(total * ease(progress * 1.4))
        for i in range(shown):
            r_, c_ = divmod(i, cols)
            x, y = x0 + c_ * cell, top + r_ * cell
            hit = i >= total - marked
            cv2.rectangle(frame, (int(x + cell * .12), int(y + cell * .12)), (int(x + cell * .88), int(y + cell * .88)),
                          ACCENT if hit else (150, 150, 150), -1 if hit else max(1, int(cell * .08)), cv2.LINE_AA)
        top += rows * cell + 30 * unit
    elif kind == 'list':
        import cv2
        items = (card.get('items') or [])[:6]
        y = top
        for k, item in enumerate(items):
            if progress * (len(items) + .5) < k + .4:
                break
            text = item.get('text') if isinstance(item, dict) else str(item)
            mark = item.get('mark', 'dot') if isinstance(item, dict) else 'dot'
            t = text_image(str(text), 'body', 58 * unit, fill=INK_TEXT[::-1], max_width=W * .62)
            x = W * .22
            cy = y + t.shape[0] / 2
            s = 16 * unit
            if mark == 'check':
                cv2.polylines(frame, [np.int32([[x - 2.6 * s, cy], [x - 1.7 * s, cy + s], [x - .2 * s, cy - s]])], False, (60, 150, 60), max(2, int(5 * unit)), cv2.LINE_AA)
            elif mark == 'cross':
                cv2.line(frame, (int(x - 2.4 * s), int(cy - s)), (int(x - .4 * s), int(cy + s)), ACCENT, max(2, int(5 * unit)), cv2.LINE_AA)
                cv2.line(frame, (int(x - .4 * s), int(cy - s)), (int(x - 2.4 * s), int(cy + s)), ACCENT, max(2, int(5 * unit)), cv2.LINE_AA)
            else:
                cv2.circle(frame, (int(x - 1.4 * s), int(cy)), int(s * .55), INK_TEXT, -1, cv2.LINE_AA)
            paste(frame, t, x, y)
            y += t.shape[0] + 30 * unit
        top = y
    elif kind == 'versus':
        import cv2
        for side, key in ((0, 'left'), (1, 'right')):
            item = card.get(key) or {}
            cx = W * (.3 if side == 0 else .7)
            a = text_image(str(item.get('label') or '').upper(), 'label', 46 * unit, fill=INK_TEXT[::-1], max_width=W * .36)
            paste(frame, a, cx - a.shape[1] / 2, top + 20 * unit)
            if progress > .25 + side * .25:
                b = text_image(str(item.get('value') or ''), 'title', 110 * unit, fill=(ACCENT if side else BLUE)[::-1], max_width=W * .38)
                paste(frame, b, cx - b.shape[1] / 2, top + 100 * unit)
        cv2.line(frame, (W // 2, int(top)), (W // 2, int(top + 260 * unit)), (150, 150, 150), max(2, int(4 * unit)))
        top += 300 * unit
    if note and progress > .5:
        centred(note, 'body', 34, max(top, H * .7), (110, 110, 110))
    return frame


class Cards:
    STEPS = 18

    def __init__(self, np, W, H):
        self.np, self.W, self.H = np, W, H
        self.cache = {}

    def get(self, card, t, length=2.):
        # a meter or a counter changes over the whole shot, the viewer watches it fall or climb (owner, 16 Nov: "a
        # battery százalékát animációval láthattuk volna, hogy droppol"); everything else builds up in 1.2 s
        slow = card.get('type') in ('meter', 'counter')
        progress = min(1., t / (max(1.2, length * .85) if slow else 1.2))
        steps = self.STEPS * 5 if slow else self.STEPS
        step = int(progress * steps)
        key = (json.dumps(card, sort_keys=True), step)
        if key not in self.cache:
            if len(self.cache) > 80:
                self.cache.clear()
            self.cache[key] = card_image(self.np, card, self.W, self.H, step / steps)
        return self.cache[key]


# ------------------------------------------------------------------ the timeline

def actor_design(who, designs, seed):
    if who in ('main', 'support'):
        return designs[who]
    kind = who.split(':', 1)[1] if ':' in who else 'person'
    return rig.extra_design(kind if kind in rig.EXTRAS else 'person', seed)


def speaking(words, t):
    for w in words:
        if w['s'] <= t <= w['e']:
            return True
    return False


def draw_crowd(cv, shot, W, H, layout, t, seed):
    crowd = shot.get('crowd') or {}
    count = max(0, min(30, int(crowd.get('count') or 0)))
    if not count:
        return
    kind = crowd.get('kind') if crowd.get('kind') in rig.EXTRAS else 'person'
    action = rig.action_of(crowd.get('action') or ('shamble' if kind == 'zombie' else 'idle'))
    size, ground = layout['crowd']
    r = random.Random(seed)
    people = []
    avoid = [float(a) for a in crowd.get('avoid') or []]
    for i in range(count):
        depth = r.random()
        x = r.uniform(.03, .97)
        for _ in range(6):
            if all(abs(x - a) > .09 for a in avoid):
                break
            x = r.uniform(.03, .97)
        people.append((depth, x, i))
    for depth, x, i in sorted(people):
        k = .72 + .28 * depth
        g = H * (ground - .07 * (1 - depth))
        d = rig.extra_design(kind, seed * 97 + i)
        facing = 1 if (crowd.get('face') or ('right' if r.random() < .5 else 'left')) == 'right' else -1
        drift = (t * .03 * facing) if action in ('shamble', 'walk') else 0.
        rig.draw_figure(cv, d, rig.pose(action, t + i * .37, 4., seed=i), (x + drift) * W, g, size * H * k * d['height'], facing,
                        rig.expression_of(crowd.get('expression') or ('neutral' if kind != 'zombie' else 'scared')), t=t + i, seed=seed + i, shadow=depth > .3)


def draw_ladder(cv, x, ground, size, H):
    """A wooden ladder from the floor to the top of the frame, behind the climber."""
    half, step = size * .2, size * .14
    colour, lw = (52, 98, 140), max(3., size * .022)
    for side in (-1, 1):
        cv.line((x + side * half, ground + size * .01), (x + side * half, -10), colour, lw)
        cv.line((x + side * half, ground + size * .01), (x + side * half, -10), rig.INK, max(1., lw * .25))
    y = ground - step * .6
    while y > -step:
        cv.line((x - half, y), (x + half, y), colour, lw * .8)
        y -= step


def draw_big_crowd(cv, shot, W, H, t, seed):
    """A low camera in the middle of a crowd: three rows, the front one so close that it is cut by the frame."""
    crowd = shot.get('crowd') or {}
    kind = crowd.get('kind') if crowd.get('kind') in rig.EXTRAS else 'person'
    action = rig.action_of(crowd.get('action') or ('shamble' if kind == 'zombie' else 'idle'))
    r = random.Random(seed)
    tall = H > W
    rows = ((.34, .62, 9), (.55, .8, 6), (.92, 1.12, 4)) if not tall else ((.22, .6, 5), (.36, .78, 4), (.6, 1.02, 3))
    n = 0
    for size, ground, count in rows:
        for i in range(count):
            n += 1
            x = (i + .5 + r.uniform(-.3, .3)) / count
            d = rig.extra_design(kind, seed * 31 + n)
            facing = 1 if r.random() < .5 else -1
            rig.draw_figure(cv, d, rig.pose(action, t + n * .41, 4., seed=n), x * W, H * ground, size * H * d['height'], facing,
                            rig.expression_of(crowd.get('expression') or ('neutral' if kind != 'zombie' else 'scared')), t=t + n, seed=seed + n)


def peep(np, cv2, frame, kind, t):
    """The picture seen through a slot, a peephole, a window or binoculars: everything else is the dark door."""
    H, W = frame.shape[:2]
    mask = np.zeros((H, W), np.uint8)
    if kind == 'peephole':
        cv2.circle(mask, (W // 2, H // 2), int(min(W, H) * .36), 255, -1, cv2.LINE_AA)
    elif kind == 'binoculars':
        for dx in (-.17, .17):
            cv2.circle(mask, (int(W * (.5 + dx)), H // 2), int(min(W, H) * .3), 255, -1, cv2.LINE_AA)
    elif kind == 'window':
        cv2.rectangle(mask, (int(W * .14), int(H * .14)), (int(W * .86), int(H * .86)), 255, -1)
    else:
        h = .3 if W >= H else .16
        cv2.rectangle(mask, (int(W * .05), int(H * (.5 - h / 2))), (int(W * .95), int(H * (.5 + h / 2))), 255, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), 3)
    k = (mask.astype(np.float32) / 255.)[..., None]
    dark = np.full_like(frame, (18, 18, 20))
    out = (frame * k + dark * (1 - k)).astype(np.uint8)
    rim = cv2.Canny(mask, 50, 150)
    out[cv2.dilate(rim, np.ones((7, 7), np.uint8)) > 0] = (70, 70, 74)
    if kind == 'window':
        cv2.line(out, (W // 2, int(H * .14)), (W // 2, int(H * .86)), (70, 70, 74), max(4, W // 120))
        cv2.line(out, (int(W * .14), H // 2), (int(W * .86), H // 2), (70, 70, 74), max(4, W // 120))
    return out


SIGN_STYLES = dict(exit=((46, 139, 87), (250, 250, 250)), warning=((242, 193, 78), (30, 30, 30)), danger=((200, 70, 59), (250, 250, 250)),
                   info=((245, 245, 240), (40, 40, 40)), screen=((30, 40, 50), (120, 240, 160)))


def draw_sign(np, cv2, frame, sign, kind, W, H):
    """A readable sign in the picture (EXIT, DANGER, a screen's text): FLUX misspells letters, so text is drawn here."""
    text = str(sign.get('text') or '').upper()[:24]
    if not text:
        return
    bg, fg = SIGN_STYLES.get(sign.get('style'), SIGN_STYLES['info'])
    size = H * (.085 if kind in ('insert', 'close') else .055) if W >= H else W * .085
    img = text_image(text + (' →' if sign.get('style') == 'exit' else ''), 'title', size, fill=fg)
    pad = int(img.shape[0] * .45)
    board = np.zeros((img.shape[0] + pad * 2, img.shape[1] + pad * 3, 4), np.uint8)
    board[..., :3] = bg[::-1]
    board[..., 3] = 255
    cv2.rectangle(board, (0, 0), (board.shape[1] - 1, board.shape[0] - 1), (30, 30, 30, 255), max(3, pad // 3))
    paste(board, img, pad * 1.5, pad)
    y = H * (.12 if kind in ('insert', 'close', 'top') else .16)
    paste(frame, board, (W - board.shape[1]) / 2, y)


def _shade(np, frame, factor, tint=None):
    out = frame.astype(np.float32) * factor
    if tint is not None:
        out += np.array(tint, np.float32) * (1 - factor)
    np.clip(out, 0, 255, out=out)
    frame[:] = out.astype(np.uint8)


def effect(np, cv2, frame, fx, t, W, H, at=None, facing=1, seed=0):
    """What the narration says happens to the place is seen (owner, 16 Nov: "olyanok is látszódjanak, hogy fény
    flickerel"). shake: vibration arcs (a door being hit); alarm: a pulsing red light; flicker: the light stutters;
    dark: the lights die; lights_on: the light comes back; sparks: a burst from where the hands are; steam: soft puffs
    rising; beam: a light beam from the hand across the frame. `at` is the main character's hand on screen."""
    hx, hy = at if at else (W * .5, H * .55)
    rnd = random.Random(seed)
    if fx == 'flicker':
        # mostly on, with short irregular drops, like a failing tube
        k = int(t * 14)
        drop = random.Random(seed * 1000 + k).random()
        level = .42 if drop < .28 else .7 if drop < .4 else 1.
        if level < 1:
            _shade(np, frame, level, (20, 10, 5))
    elif fx in ('dark', 'dark_hold'):
        level = 1 - .7 * (min(1., t / .5) if fx == 'dark' else 1.)
        _shade(np, frame, level, (25, 10, 5))
    elif fx == 'lights_on':
        level = .3 + .7 * min(1., max(0., (t - .15) / .45))
        if t < .5 and int(t * 16) % 3 == 0:
            level = .45
        if level < 1:
            _shade(np, frame, level, (25, 10, 5))
    elif fx == 'sparks':
        size = max(2, int(H * .004))
        for burst in range(int(t * 3) + 1):
            b = random.Random(seed * 77 + burst)
            age = t - burst / 3
            if not 0 <= age < .45:
                continue
            for _ in range(16):
                ang = b.uniform(-math.pi, 0) if b.random() < .8 else b.uniform(0, math.pi)
                speed = H * b.uniform(.25, .7)
                x0 = hx + math.cos(ang) * speed * age
                y0 = hy + math.sin(ang) * speed * age + H * .9 * age * age
                tail = .045
                x1 = hx + math.cos(ang) * speed * max(0, age - tail)
                y1 = hy + math.sin(ang) * speed * max(0, age - tail) + H * .9 * max(0, age - tail) ** 2
                colour = (80, 220, 255) if b.random() < .6 else (200, 250, 255)
                cv2.line(frame, (int(x1), int(y1)), (int(x0), int(y0)), colour, size, cv2.LINE_AA)
        if (t * 3) % 1 < .12:
            cv2.circle(frame, (int(hx), int(hy)), int(H * .03), (200, 250, 255), -1, cv2.LINE_AA)
    elif fx == 'steam':
        small = np.zeros((H // 4, W // 4), np.uint8)
        sx, sy = (rnd.uniform(.2, .8) * W, H * .62) if not at else (hx + facing * W * .12, hy)
        for k in range(14):
            b = random.Random(seed * 31 + k)
            phase = (t * .6 + k / 14) % 1
            x = sx + b.uniform(-.03, .03) * W + phase * W * .07 * (1 if k % 2 else -1)
            y = sy - phase * H * .55
            r = H * (.05 + .15 * phase)
            cv2.circle(small, (int(x / 4), int(y / 4)), max(1, int(r / 4)), int(255 * (1 - phase) ** .5), -1)
        small = cv2.GaussianBlur(small, (0, 0), max(1., H / 200))
        a = cv2.resize(small, (W, H)).astype(np.float32)[..., None] / 255 * .9
        frame[:] = (frame * (1 - a) + np.float32(245) * a).astype(np.uint8)
    elif fx == 'beam':
        end = (int(hx + facing * W * .9), int(hy - H * .18))
        glow = np.zeros_like(frame)
        cv2.line(glow, (int(hx), int(hy)), end, (60, 60, 255), max(6, int(H * .018)), cv2.LINE_AA)
        glow = cv2.GaussianBlur(glow, (0, 0), max(2., H / 140))
        cv2.add(frame, glow, frame)
        cv2.line(frame, (int(hx), int(hy)), end, (120, 120, 255), max(2, int(H * .004)), cv2.LINE_AA)
    elif fx == 'spray':
        # a jet of water or foam from the hand (a hose, an extinguisher), an arc that lands and splashes
        size = max(2, int(H * .004))
        length = W * .55
        reach = min(1., t / .35)
        pts = []
        for k in range(28):
            q = k / 27 * reach
            pts.append((hx + facing * length * q, hy - H * .16 * math.sin(q * math.pi * .9) + H * .22 * q * q))
        arr = np.array(pts, np.int32)
        glow = np.zeros_like(frame)
        cv2.polylines(glow, [arr], False, (255, 240, 220), max(8, int(H * .03)), cv2.LINE_AA)
        glow = cv2.GaussianBlur(glow, (0, 0), max(2., H / 120))
        cv2.addWeighted(glow, .8, frame, 1, 0, frame)
        cv2.polylines(frame, [arr], False, (255, 250, 245), max(3, int(H * .01)), cv2.LINE_AA)
        end = pts[-1]
        for k in range(18):
            b = random.Random(seed * 13 + k + int(t * 20) * 31)
            ang = b.uniform(-math.pi, 0)
            d = H * b.uniform(.01, .07)
            cv2.circle(frame, (int(end[0] + math.cos(ang) * d), int(end[1] + math.sin(ang) * d)), size, (255, 245, 235), -1, cv2.LINE_AA)
    elif fx == 'blink':
        # a button, a light or a sign lights up: a soft pulsing glow (centre of an object close-up, else above the hand)
        cx, cy = (W * .5, H * .42) if not at else (hx + facing * W * .06, hy - H * .08)
        pulse = .5 + .5 * math.sin(t * 7)
        glow = np.zeros_like(frame)
        cv2.circle(glow, (int(cx), int(cy)), int(H * (.05 + .03 * pulse)), (120, 255, 170), -1, cv2.LINE_AA)
        glow = cv2.GaussianBlur(glow, (0, 0), max(3., H / 40))
        cv2.addWeighted(glow, .55 + .45 * pulse, frame, 1, 0, frame)
    if fx == 'shake':
        beat = abs(math.sin(t * 9))
        for side in (-1, 1):
            for k in range(3):
                r = H * (.2 + .07 * k) * (1 + .05 * beat)
                cv2.ellipse(frame, (int(W / 2 + side * H * (.08 + .06 * k)), int(H * .52)), (int(r * .35), int(r)), 0, -40 if side > 0 else 140, 40 if side > 0 else 220,
                            (245, 245, 245), max(3, int(H * .006)), cv2.LINE_AA)
    elif fx == 'alarm':
        a = .22 * abs(math.sin(t * 4))
        red = np.zeros_like(frame)
        red[:] = (40, 40, 220)
        cv2.addWeighted(red, a, frame, 1 - a, 0, frame)


def weather(np, cv2, frame, kind, t, W, H, seed):
    """Rain, snow, wind or a storm over the scene (owner, 16 Nov: "ha egy helyszín igényli, tudjon esni eső, havazni,
    szél effekt"), drawn from seeded particles so every frame of a shot continues the last one."""
    rnd = random.Random(seed)
    if kind in ('rain', 'storm'):
        layer = np.zeros_like(frame)
        n = 160 if kind == 'rain' else 240
        slant = .18 if kind == 'rain' else .35
        for _ in range(n):
            x0, y0, speed = rnd.uniform(-.2, 1.1) * W, rnd.uniform(0, 1) * H, rnd.uniform(1.6, 2.4) * H
            y = (y0 + speed * t) % (H * 1.1) - H * .05
            x = x0 + slant * (y - y0)
            x = x % (W * 1.2) - W * .1
            ln = H * rnd.uniform(.03, .06)
            cv2.line(layer, (int(x), int(y)), (int(x - slant * ln), int(y - ln)), (235, 225, 210), max(1, int(H * .0022)), cv2.LINE_AA)
        cv2.addWeighted(layer, .55, frame, 1, 0, frame)
        if kind == 'storm':
            flash = random.Random(seed + int(t * 2)).random()
            if flash < .08 and (t * 2) % 1 < .18:
                frame[:] = np.clip(frame.astype(np.int16) + 90, 0, 255).astype(np.uint8)
            else:
                frame[:] = (frame * .82).astype(np.uint8)
    elif kind == 'snow':
        for _ in range(140):
            x0, y0, speed, r = rnd.uniform(0, 1) * W, rnd.uniform(0, 1) * H, rnd.uniform(.08, .2) * H, rnd.uniform(.003, .008) * H
            y = (y0 + speed * t) % H
            x = (x0 + math.sin(t * 1.3 + x0) * W * .015 + t * W * .02) % W
            cv2.circle(frame, (int(x), int(y)), max(1, int(r)), (250, 250, 250), -1, cv2.LINE_AA)
    elif kind == 'wind':
        layer = np.zeros_like(frame)
        for k in range(14):
            b = random.Random(seed * 7 + k)
            y = b.uniform(.08, .9) * H
            phase = (t * b.uniform(.6, 1.1) + b.random()) % 1
            x = (phase * 1.6 - .3) * W
            ln = W * b.uniform(.08, .18)
            pts = np.array([(int(x + q * ln), int(y + math.sin(q * 6 + t * 4) * H * .01)) for q in [i / 12 for i in range(13)]], np.int32)
            cv2.polylines(layer, [pts], False, (240, 240, 240), max(1, int(H * .003)), cv2.LINE_AA)
            if k % 3 == 0:
                cv2.ellipse(frame, (int(x + ln), int(y)), (max(2, int(H * .008)), max(1, int(H * .004))), (t * 300 + k * 40) % 180, 0, 360, (60, 130, 90), -1, cv2.LINE_AA)
        cv2.addWeighted(layer, .5, frame, 1, 0, frame)


def reach(cv2, frame, mode, u, W, H, colour=(30, 30, 30)):
    """A stickman arm reaching into an object close-up from the lower right to press or grab what is shown (the
    references show the hand pressing the shutter button and turning the key)."""
    come = min(1., u / .35)
    come = 1 - (1 - come) ** 3
    tx, ty = W * .52, H * .47
    if mode == 'press' and u > .4:
        bob = math.sin((u - .4) * 18) * .5 + .5
        tx -= W * .01 * bob
        ty += H * .015 * bob
    sx, sy = W * 1.05, H * 1.05
    hx, hy = sx + (tx - sx) * come, sy + (ty - sy) * come
    elbow = ((sx + hx) / 2 + W * .05, (sy + hy) / 2 + H * .06)
    th = max(6, int(H * .03))
    cv2.line(frame, (int(sx), int(sy)), (int(elbow[0]), int(elbow[1])), colour, th, cv2.LINE_AA)
    cv2.line(frame, (int(elbow[0]), int(elbow[1])), (int(hx), int(hy)), colour, th, cv2.LINE_AA)
    cv2.circle(frame, (int(hx), int(hy)), int(th * 1.35), colour, -1, cv2.LINE_AA)


FURNITURE = dict(lie=('bed', 'sofa', 'couch', 'bench', 'mattress'), sleep=('bed', 'sofa', 'couch', 'bench', 'mattress'),
                 sit=('chair', 'sofa', 'couch', 'bench', 'stool', 'bed', 'seat'))


def on_furniture(measured, action, kind):
    """Where on the measured furniture a lying or sitting figure goes: (x, ground) as fractions, or None."""
    if not measured or action not in FURNITURE or kind not in ('wide', 'top'):
        return None
    for obj in measured.get('objects') or []:
        if any(w in obj.get('name', '') for w in FURNITURE[action]):
            x1, y1, x2, y2 = obj['box']
            if kind == 'top':
                return (x1 + x2) / 2, y1 + (y2 - y1) * .62, x2 - x1
            if action == 'sit':
                return (x1 + x2) / 2, y2 - (y2 - y1) * .02, x2 - x1        # feet on the floor in front, the hip lands at seat height
            return (x1 + x2) / 2, y1 + (y2 - y1) * .55, x2 - x1
    return None


def cutout(np, cv2, path):
    """A tool painted on a plain white background as a BGRA sprite: the white connected to the border becomes clear,
    the object is cropped to its outline."""
    img = cv2.imread(str(path))
    if img is None:
        return None
    h, w = img.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if mask[seed[1] + 1, seed[0] + 1] == 0 and img[seed[1], seed[0]].min() > 200:
            cv2.floodFill(img, mask, seed, (0, 0, 0), (22, 22, 22), (22, 22, 22), cv2.FLOODFILL_MASK_ONLY | (255 << 8) | 8)
    alpha = 255 - mask[1:-1, 1:-1]
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    ys, xs = np.where(alpha > 40)
    if not len(xs) or len(xs) > .8 * h * w:
        return None          # nothing cut out, or the background was not plain
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return np.dstack([img[y0:y1, x0:x1], alpha[y0:y1, x0:x1]])


TRAVEL = ('walk', 'run', 'sneak', 'carry', 'shamble')


def route(actor, kind):
    """Where an actor starts and ends in a shot. Walking always goes somewhere (owner, 16 Nov: "többször csak a képernyő
    közepén van a karakter és egyhelyben sétál"): with no destination given he crosses a third of the frame the way he
    faces."""
    x0 = float(actor.get('x', .5))
    action = rig.action_of(actor.get('action'))
    if actor.get('to') is not None:
        return x0, float(actor['to'])
    if action in TRAVEL and actor.get('depth') == 'away' and kind == 'wide':
        return x0, x0 + (.5 - x0) * .6          # into the picture, towards the vanishing point
    if action in TRAVEL and actor.get('depth') == 'toward' and kind == 'wide':
        return x0, x0 + (x0 - .5) * .4
    if action in TRAVEL and kind not in ('close',):
        facing = -1 if actor.get('face') == 'left' else 1
        step = .34 if action != 'run' else .5
        x1 = x0 + facing * step
        if not .1 <= x1 <= .9:
            x1 = x0 - facing * step
        return x0, min(.9, max(.1, x1))
    return x0, x0


def render(request):
    import numpy as np
    import cv2
    import scene_production
    W, H, fps = int(request['width']), int(request['height']), int(request.get('fps', 30))
    orientation = 'portrait' if H > W else 'landscape'
    layout = LAYOUT[orientation]
    designs = request['designs']
    plates = Plates(cv2, np, request.get('plates'), W, H)
    inserts = {k: v for k, v in (request.get('inserts') or {}).items() if v and Path(v).is_file()}
    insert_cache = {}
    moving_fx.use_textures(request.get('vfx'))
    tools = {}
    for name, path in (request.get('tools') or {}).items():
        sprite = cutout(np, cv2, path) if path and Path(path).is_file() else None
        if sprite is not None:
            tools[name] = sprite
    cards = Cards(np, W, H)
    shots = request['shots']
    scene_production.compile_shots(shots, fps)
    scene_records = {}
    words = request.get('words') or []
    total = int(math.ceil(shots[-1]['end'] * fps)) if shots else 0
    seed = int(request.get('seed', 7))
    output = Path(request['output'])
    progress = Path(request['progress']) if request.get('progress') else None
    encoder = subprocess.Popen([request['ffmpeg'], '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                                '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-tune', 'animation', '-pix_fmt', 'yuv420p',
                                '-movflags', '+faststart', str(output)], stdin=subprocess.PIPE)
    # paper grain and vignette, the "drawn" feel of the references
    rng = np.random.default_rng(seed)
    grains = [rng.integers(0, 9, (H, W, 1), dtype=np.uint8).repeat(3, 2) for _ in range(3)]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1 - .28 * np.clip(np.sqrt(((xx - W / 2) / (W * .62)) ** 2 + ((yy - H / 2) / (H * .62)) ** 2) - .45, 0, 1)
    vignette = (vig[..., None].repeat(3, 2) * 255).astype(np.uint8)
    word_cache = {}
    caption_y = layout['caption'] * H
    caption_size = (H / 1080.) * 74 if W >= H else (W / 1080.) * 92
    hud_cache = {}
    word_index = 0
    shot_index = 0
    for frame_no in range(total):
        t = frame_no / fps
        while shot_index < len(shots) - 1 and t >= shots[shot_index]['end']:
            shot_index += 1
        shot = shots[shot_index]
        local = t - shot['start']
        length = max(.1, shot['end'] - shot['start'])
        u = local / length
        kind = shot.get('kind', 'wide')
        place = shot.get('place')
        hand = None
        if kind == 'top' and str(place) + '@top' not in (request.get('plates') or {}):
            kind = 'wide'      # no painted bird's-eye view of this place
        cam = shot.get('camera', 'push')
        shake = (0, 0)
        if cam == 'shake' and local < .5:
            amp = (1 - local / .5) * H * .012
            shake = (math.sin(local * 63) * amp, math.cos(local * 51) * amp)
        if shot.get('controlled'):
            frame, measurement = scene_production.draw(np, cv2, plates.get(place), shot, designs, local, fps)
            scene_production.accumulate(scene_records, measurement)
        elif kind in ('card', 'title'):
            frame = cards.get(shot.get('card') or dict(type='title', title=shot.get('text', '')), local, length).copy()
        elif kind == 'insert' and shot.get('insert') in inserts:
            key = shot['insert']
            if key not in insert_cache:
                insert_cache[key] = plates.cover(cv2.imread(inserts[key]))
            zoom = 1.02 + .06 * ease(u)
            frame = plates.view(insert_cache[key], zoom, W / 2, H / 2, shake)
            if shot.get('hand'):
                reach(cv2, frame, shot['hand'], u, W, H)
            label = str(shot.get('label') or '').upper()[:28]
            if label:
                img = text_image(label, 'label', H * .075, fill=(250, 250, 250), stroke=int(H * .006), stroke_fill=(30, 30, 30), max_width=W * .8)
                paste(frame, img, (W - img.shape[1]) / 2, H * .12)
        else:
            if kind == 'insert':
                kind = 'medium'
            actors = shot.get('actors') or []
            # the camera follows where the actors are now, so a walk across a medium shot stays in the picture
            xs = []
            for a in actors:
                a0, a1 = route(a, kind)
                xs.append(a0 + (a1 - a0) * (u if rig.action_of(a.get('action')) != 'run' else min(1., u * 1.25)))
            xs = xs or [.5]
            pov = shot.get('pov') if kind == 'pov' else None
            if kind == 'pov':
                kind = 'crowd' if shot.get('crowd') else 'medium'
            if kind == 'close':
                # the place behind the face, pushed in towards where the character stands
                focus = sum(xs) / len(xs)
                zoom = 1.45 + .05 * ease(u)
                cx = min(max(W * (.25 + .5 * focus), W / 2 / zoom), W - W / 2 / zoom)
                frame = plates.view(plates.blurred(place), zoom, cx, H * .45, shake)
            elif kind == 'top':
                frame = plates.view(plates.get(str(place) + '@top'), 1.0 + .05 * ease(u), W / 2, H / 2, shake)
            elif kind == 'crowd':
                frame = plates.view(plates.get(place), 1.3 + .04 * ease(u), W / 2, H * .4, shake)
            else:
                zoom0, zoom1 = (1.0, 1.05) if kind == 'wide' else (1.5, 1.56)
                if cam == 'pull':
                    zoom0, zoom1 = zoom1, zoom0
                zoom = zoom0 + (zoom1 - zoom0) * ease(u)
                focus = sum(xs) / len(xs)
                cx = W / 2 + (focus - .5) * W * (.0 if kind == 'wide' else .35)
                if cam in ('pan_left', 'pan_right'):
                    cx += (1 if cam == 'pan_right' else -1) * W * .04 * (ease(u) - .5)
                cy = H * (.5 if kind == 'wide' else .6)
                cx = min(max(cx, W / 2 / zoom), W - W / 2 / zoom)
                cy = min(max(cy, H / 2 / zoom), H - H / 2 / zoom)
                frame = plates.view(plates.get(place), zoom, cx, cy, shake)
            for n, spec in enumerate(shot.get('moving') or []):
                if isinstance(spec, dict) and spec.get('kind') in moving_fx.BEHIND and kind not in ('close',):
                    moving_fx.draw(np, cv2, frame, spec, local, u, W, H, seed=seed + shot_index * 7 + n)
            cv = rig.Canvas(cv2, frame)
            if kind in ('wide', 'top'):
                draw_crowd(cv, shot, W, H, layout if kind == 'wide' else dict(layout, crowd=layout['top']), local, seed + shot_index * 13)
            elif kind == 'crowd':
                draw_big_crowd(cv, shot, W, H, local, seed + shot_index * 13)
                actors = [a for a in actors if a.get('who') == 'main'][:1]
            figure, ground = layout['medium' if kind == 'crowd' else kind]
            # the size a person has in this painting, measured on the plate by the vision model (owner, 16 Nov: "a
            # méretarány most sem elég jó, pl. az ágy top shotnál az ember nem méretarányos"); a bad reading is kept
            # within bounds so it can never shrink or blow up the character
            measured = (request.get('scales') or {}).get(str(place) + ('@top' if kind == 'top' else ''))
            if measured and kind in ('wide', 'medium', 'top', 'crowd') and measured.get('person'):
                base = layout['top' if kind == 'top' else 'wide'][0]
                ratio = min(3. if kind == 'top' else 2., max(.6, float(measured['person']) / .92 / base))
                figure *= ratio
                if kind == 'wide' and measured.get('floor'):
                    ground = min(.97, max(.72, float(measured['floor'])))
            for k, actor in enumerate(actors[:4]):
                who = actor.get('who', 'main')
                d = actor_design(who, designs, seed + k)
                size = figure * H * d.get('height', 1.)
                if kind == 'close':
                    size = figure * H * (1. if len(actors) == 1 else .8)
                    size = min(size, H * .38 / (rig.HEAD_R * 2.3))      # landscape close-ups cut the beanie off at the top (17 Nov ferry video)
                    head_above = (rig.THIGH + rig.SHIN + .02 + rig.TORSO + rig.HEAD_R * .9) * size
                    g = H * .42 + head_above
                else:
                    g = H * ground
                if kind in ('wide', 'medium', 'crowd'):
                    # the head (with its beanie) always stays in the picture (17 Nov Short: heads cut off by the top edge)
                    size = min(size, max(.1, g - H * .05) / (rig.THIGH + rig.SHIN + rig.TORSO + rig.HEAD_R * 3.2))
                if actor.get('depth') in ('away', 'toward') and kind == 'wide':
                    # walking into the picture (down a hall, along a street) or out of it towards the camera
                    q = ease(u) if actor['depth'] == 'away' else 1 - ease(u)
                    size *= 1 - .45 * q
                    g -= (g - H * .62) * .55 * q
                x0, x1 = route(actor, kind)
                action = rig.action_of(actor.get('action'))
                rest = on_furniture(measured, action, kind) if who == 'main' or (who.startswith('extra') and action in ('lie', 'sleep')) else None
                if rest and who.startswith('extra'):
                    size = min(size, max(.05, rest[2]) * W * .8)      # a patient is as long as the bed they lie in (17 Nov)
                if rest:
                    # lying or sitting goes onto the bed, sofa or chair the painting has, not next to it; a lying body
                    # stretches back from its feet, so the feet go half a body forward of the middle
                    facing_ = -1 if actor.get('face') == 'left' else 1
                    x0 = x1 = rest[0] + (facing_ * .46 * size / W if action in ('lie', 'sleep') else 0.)
                    g = rest[1] * H
                travel = action in ('walk', 'run', 'sneak', 'carry', 'shamble') and abs(x1 - x0) > .01
                x = x0 + (x1 - x0) * (u if action != 'run' else min(1., u * 1.25)) if travel else x0
                facing = -1 if actor.get('face') == 'left' else 1
                if travel:
                    facing = 1 if x1 > x0 else -1
                p = rig.pose(action, local, length, seed=k)
                if rest:
                    p['on_furniture'] = True
                if action == 'climb':
                    draw_ladder(cv, x * W + facing * size * .06, g, size, H)
                    if kind != 'close':
                        p['lift'] = .62 * ease(u)       # he really goes up the ladder during the shot
                if not travel and action in ('walk', 'run', 'shamble', 'carry', 'sneak') and kind != 'wide':
                    p = rig.pose(action, local, length, seed=k)   # walking on the spot reads as walking in a closer shot
                talk = 0.
                if actor.get('talk') and speaking(words, t):
                    talk = .5 + .5 * abs(math.sin(t * 13 + k))
                if who.split(':', 1)[-1] in rig.ANIMALS:
                    rig.draw_animal(cv, who.split(':', 1)[-1], x * W, g, size, facing, t, moving=travel)
                    continue
                rig.draw_figure(cv, d, p, x * W, g, size, facing, rig.expression_of(actor.get('expression')), t=t, seed=seed + k * 7 + (0 if who == 'main' else 3),
                                talking=talk, prop=rig.prop_of(actor.get('prop')), shadow=kind != 'close', tool=tools.get(actor.get('tool')))
                if who == 'main' or hand is None:
                    hand = (x * W + facing * size * .22, g - size * (rig.THIGH + rig.SHIN + rig.TORSO * .55), facing)
            if pov:
                frame = peep(np, cv2, frame, pov, local)
        for n, spec in enumerate([] if shot.get('controlled') else (shot.get('moving') or [])):
            if isinstance(spec, dict) and spec.get('kind') in moving_fx.BEHIND:
                continue           # drawn behind the characters
            big = spec.get('kind') in moving_fx.OBJECTS if isinstance(spec, dict) else False
            # nothing burns, smokes or steams in front of a face (16 Nov Short: flames over the close-up)
            big = big or (spec.get('kind') in ('fire', 'smoke', 'steam', 'dust', 'debris', 'fog') if isinstance(spec, dict) else False) and kind == 'close'
            if kind not in ('card', 'title') and not (big and kind in ('close', 'insert')) and isinstance(spec, dict) and spec.get('kind') in moving_fx.MOTIONS:
                moving_fx.draw(np, cv2, frame, spec, local, u, W, H, seed=seed + shot_index * 7 + n, hand=hand[:2] if hand else None, facing=hand[2] if hand else 1)
        if shot.get('weather') and kind not in ('card', 'title', 'insert'):
            weather(np, cv2, frame, shot['weather'], t, W, H, seed + 5)
        if shot.get('sign') and kind not in ('card', 'title'):
            draw_sign(np, cv2, frame, shot['sign'], kind, W, H)
        if shot.get('fx') and kind not in ('card', 'title') and not shot.get('controlled'):
            effect(np, cv2, frame, shot['fx'], local, W, H, at=hand[:2] if hand else None, facing=hand[2] if hand else 1, seed=seed + shot_index)
        # the corner counter
        crowd_total = (shot.get('crowd') or {}).get('total')
        if crowd_total and crowd_total > shot['crowd'].get('count', 0):
            label = text_image(str(crowd_total) + ' PEOPLE', 'label', H * .035,
                               fill=(245, 245, 245), stroke=2, max_width=W * .35)
            paste(frame, label, W - label.shape[1] - W * .025, H * .035)
        hud = str(shot.get('hud') or '').upper()[:24]
        if hud and kind not in ('title',):
            if hud not in hud_cache:
                img = text_image(hud, 'label', H * .048 if W >= H else W * .06, fill=(40, 40, 40))
                pad = int(img.shape[0] * .45)
                box = np.zeros((img.shape[0] + pad * 2, img.shape[1] + pad * 2, 4), np.uint8)
                box[..., :3] = (236, 244, 248)
                box[..., 3] = 235
                cv2.rectangle(box, (0, 0), (box.shape[1] - 1, box.shape[0] - 1), (60, 60, 60, 255), max(2, pad // 4))
                paste(box, img, pad, pad)
                hud_cache[hud] = box
            paste(frame, hud_cache[hud], W * .025, H * .035 if W >= H else H * .05)
        # one word of caption at a time
        if request.get('caption', True):
            while word_index < len(words) - 1 and words[word_index]['e'] < t:
                word_index += 1
            w = words[word_index] if words else None
            if w and w['s'] - .02 <= t <= w['e'] + .12 and kind not in ('title',):
                text = w['w'].upper()
                if text not in word_cache:
                    numeric = any(ch.isdigit() for ch in text)
                    word_cache[text] = text_image(text, 'caption', caption_size, fill=(255, 214, 70) if numeric else (255, 255, 255),
                                                  stroke=max(3, int(caption_size * .1)), stroke_fill=(25, 25, 25), max_width=W * .9)
                img = word_cache[text]
                y = caption_y if kind not in ('card',) else H * .88
                paste(frame, img, (W - img.shape[1]) / 2, y - img.shape[0] / 2)
        frame = cv2.multiply(frame, vignette, scale=1 / 255.)
        # one still grain: a changing one looked the same and tripled the file size (16 Nov trial: 18 Mbit/s)
        frame = cv2.add(frame, grains[0])
        frame = cv2.subtract(frame, grains[1])
        encoder.stdin.write(frame.tobytes())
        if progress and frame_no % 60 == 0:
            progress.write_text(json.dumps(dict(frame=frame_no, total=total)))
    encoder.stdin.close()
    if encoder.wait() != 0:
        raise ValueError('a videó kódolása nem sikerült')
    evidence = dict(renderer=scene_production.VERSION, scenes=scene_records,
                    passed=all(x['passed'] for x in scene_records.values()))
    if request.get('quality_output'):
        Path(request['quality_output']).write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    if not evidence['passed']:
        raise ValueError('A vezérelt művelet kontakt- vagy állapotellenőrzése nem sikerült.')
    return dict(output=str(output), frames=total, seconds=round(total / fps, 2), controlled=evidence)


def still(request):
    """One frame of a shot as PNG: the settings page and the tests look at it."""
    import numpy as np
    import cv2
    req = dict(request)
    out = Path(req['output'])
    req['output'] = str(out.with_suffix('.mp4'))
    render(req)
    cap = cv2.VideoCapture(req['output'])
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(req.get('frame', 15)))
    ok, frame = cap.read()
    cap.release()
    Path(req['output']).unlink(missing_ok=True)
    if ok:
        cv2.imwrite(str(out), frame)
    return dict(output=str(out))


if __name__ == '__main__':
    if sys.argv[1] == 'sheet':
        spec = json.loads(Path(sys.argv[2]).read_text())
        print(json.dumps(dict(output=rig.sheet(spec['output'], spec['designs']))))
    else:
        req = json.loads(Path(sys.argv[1]).read_text())
        print(json.dumps(still(req) if req.get('still') else render(req)))
