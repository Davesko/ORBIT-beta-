"""Hand-drawn style character animation for story shorts, rendered by code instead of a video model.

Characters are rigs: every body part follows its pose target through a spring, so a pose change anticipates, overshoots
and settles like drawn animation, and every action keeps cycling for the whole shot, so nothing ever freezes. Identity
and location cannot drift (one rig, one painted background plate), mouths follow the real voice track, and a whole
episode renders in about a minute on the CPU.

Runs in media-runtime (numpy, cv2). Input is one JSON document on argv[1]; writes clip-<n>.mp4 to `folder`."""
import hashlib
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1080, 1920, 24
GROUND = 1500
BOIL_FPS = 8
ACTIONS = ('idle', 'talk', 'point', 'shrug', 'facepalm', 'phone', 'game', 'shock', 'laugh', 'cry', 'rage', 'dance', 'faint', 'nod', 'stare',
           'walk_in', 'walk_out', 'run_in', 'pace', 'sneak', 'jump', 'run', 'crouch', 'push', 'slap', 'handshake', 'hug', 'hat_off')
DEPTHS = (((1., 0.), (1., 0.)), ((1., 0.), (.78, 120.)), ((.78, 120.), (1., 0.)), ((.86, 70.), (.86, 70.)), ((1., 0.), (1., 0.)))
INTERACT = ('push', 'slap', 'handshake', 'hug')   # done TO the other character: the actor walks up to them first
MOVING = ('walk_in', 'walk_out', 'run_in', 'pace', 'sneak', 'run') + INTERACT
CONTACT = .75
OFFSTAGE = 780
PROP_MOTIONS = ('none', 'wobble', 'bounce', 'grow', 'shake', 'fly_in')
COLOURS = {'yellow': (70, 215, 250), 'green': (95, 200, 95), 'lime': (70, 235, 170), 'blue': (225, 120, 40), 'red': (55, 60, 225),
           'orange': (40, 145, 245), 'purple': (190, 70, 140), 'pink': (180, 130, 245), 'teal': (165, 170, 40), 'grey': (150, 145, 140),
           'gray': (150, 145, 140), 'black': (45, 40, 40), 'white': (240, 240, 240), 'brown': (50, 95, 140), 'tan': (130, 180, 225)}
INK = (28, 24, 24)
GARMENT = r'hoodie|sweatshirt|sweater|jacket|shirt|t-shirt|tee|dress|coat|vest|tank'

# Pose values: x y (root offset), lean, tilt (head), squash, hand/foot offsets, and the face.
REST = dict(x=0., y=0., lean=0., tilt=0., squash=1., lx=-85., ly=225., rx=85., ry=225., lf=-60., rf=60., lfy=0., rfy=0., look=0., brow=0., eye=1.)
# Motion capture (story_mocap): real actors' movement for the body, the rig keeps the face, timing beats and the drawing.
TRACKS = None
MOCAP_KEYS = ('lx', 'ly', 'rx', 'ry', 'lf', 'rf', 'lfy', 'rfy', 'y', 'lean', 'tilt')
CONTINUOUS = ('idle', 'stare', 'talk')
ONE_SHOT = ('point', 'shrug', 'facepalm', 'shock', 'laugh', 'cry', 'rage', 'nod')   # played once, timed to the line            # these follow the episode clock, so a cut does not restart them
GAIT_OF = dict(walk_in='walk', walk_out='walk', pace='walk', push='walk', slap='walk', handshake='walk', hug='walk',
               run='run', run_in='run', sneak='sneak')
STRIDE = dict(walk=2.4, sneak=2.2, run=1.25)       # stage walks are brisker than the studio takes: longer strides


def number(key):
    return int(key, 16)


def ease_noise(t, seed):
    return math.sin(t * 2.1 + seed) * .6 + math.sin(t * 3.7 + seed * 2.3) * .4


def action_pose(name, t, length, talking, side):
    """Targets for this moment. Each action keeps changing over its whole length: there is no last frame to hold."""
    beat = int(t / .42)
    swing = 1 if beat % 2 else -1
    p, mouth = {}, None
    if name == 'talk' or (talking and name in ('idle', 'stare')):
        p = dict(lx=-110 - 40 * (beat % 3 == 0), ly=120 + 45 * swing, rx=110 + 30 * (beat % 3 == 1), ry=130 - 45 * swing, tilt=5 * swing, lean=3 * swing, brow=.3 * swing)
    elif name == 'point':
        reach = 260 + 22 * math.sin(t * 7)
        p = dict(rx=reach * side, ry=-25 + 14 * swing, lx=-70 * side, ly=210, lean=-6 * -side, brow=-.5, tilt=4 * side)
        mouth = 'grin'
    elif name == 'shrug':
        up = (beat % 3) != 2
        p = dict(lx=-190, ly=25 if up else 190, rx=190, ry=25 if up else 190, tilt=9 * swing, brow=.9 if up else .1, squash=.95 if up else 1.02)
        mouth = 'flat'
    elif name == 'facepalm':
        hit = t > .45
        p = dict(rx=-70 * side if hit else 150, ry=-175 if hit else 40, lean=10 * math.sin(t * 2), tilt=-16 + 6 * math.sin(t * 3.1) if hit else 5, brow=-.8, eye=.25 if hit else 1)
        mouth = 'frown'
    elif name == 'phone':
        p = dict(lx=-30, ly=45, rx=25, ry=30 + 12 * math.sin(t * 9), tilt=15 + 3 * math.sin(t * 1.7), eye=.65, look=.0, brow=-.1)
    elif name == 'game':
        p = dict(lx=-52 + 8 * math.sin(t * 13), ly=62 + 6 * math.sin(t * 17), rx=52 - 8 * math.sin(t * 11), ry=62 + 6 * math.cos(t * 15), lean=7 * math.sin(t * 1.9), tilt=5 * math.sin(t * 2.3), eye=.8, brow=-.4)
        mouth = 'flat'
    elif name == 'shock':
        p = dict(y=-120 if t < .3 else 6 * math.sin(t * 42), lx=-230, ly=-60, rx=230, ry=-60, squash=1.16 if t < .3 else 1. + .03 * math.sin(t * 42), eye=1.55, brow=1.)
        mouth = 'o'
    elif name == 'laugh':
        p = dict(y=-26 * abs(math.sin(t * 9)), lean=(-10 if t < length * .55 else 16) + 5 * math.sin(t * 18), lx=-55, ly=175, rx=55, ry=175, eye=.15, brow=.6, tilt=8 * math.sin(t * 9))
        mouth = 'grin'
    elif name == 'cry':
        p = dict(lx=-40, ly=-135 + 12 * math.sin(t * 14), rx=40, ry=-135 + 12 * math.cos(t * 14), tilt=-10, y=4 * math.sin(t * 24), eye=.2, brow=.9, squash=.96 + .02 * math.sin(t * 7))
        mouth = 'frown'
    elif name == 'rage':
        p = dict(lx=-215 + 24 * math.sin(t * 22), ly=-90 + 45 * math.sin(t * 16), rx=215 - 24 * math.sin(t * 19), ry=-90 - 45 * math.sin(t * 16), y=-14 * abs(math.sin(t * 11)), lean=7 * math.sin(t * 13), eye=1.15, brow=-1.)
        mouth = 'o'
    elif name == 'dance':
        p = dict(x=42 * math.sin(t * 5.4), y=-36 * abs(math.sin(t * 5.4)), lean=13 * math.sin(t * 5.4), lx=-180, ly=-90 * math.sin(t * 5.4) + 60, rx=180, ry=90 * math.sin(t * 5.4) + 60, tilt=-12 * math.sin(t * 5.4), lf=-95, rf=95, eye=.3, brow=.5)
        mouth = 'grin'
    elif name == 'faint':
        wobble = min(1, t / max(.5, length * .4))
        p = dict(lean=8 * math.sin(t * 8) * (1 - wobble) + 82 * wobble ** 3 * side, y=120 * wobble ** 3, lx=-150, ly=160, rx=150, ry=160, eye=max(.05, 1 - wobble), brow=.5)
        mouth = 'o'
    elif name == 'nod':
        p = dict(tilt=14 * math.sin(t * 7), y=4 * math.sin(t * 7), eye=.8, brow=.2, lx=-70, ly=205, rx=70, ry=205)
        mouth = 'flat'
    elif name == 'stare':
        p = dict(eye=1.25 if beat % 5 != 4 else .8, brow=-.15 * swing, tilt=2 * swing)
        mouth = 'flat'
    elif name == 'run':
        p = dict(lean=12 * side * (1 if math.cos(t * 2.6) > 0 else -1), brow=-.3, eye=1.1)
        mouth = 'o'
    elif name == 'crouch':
        dip = ease(t / .4)
        p = dict(y=135 * dip, squash=1 - .2 * dip, lx=-120, ly=150, rx=120, ry=150, lean=4 * math.sin(t * 3), eye=1.2, brow=.4)
        mouth = 'flat'
    elif name in ('push', 'slap'):
        u = t - CONTACT
        if name == 'push':
            reach = 240 if u > -.15 else 90
            p = dict(lx=side * 190 * (reach > 100) - 40, ly=40, rx=side * reach, ry=30, lean=(12 if 0 < u < .4 else 3) * side, brow=-.9, eye=1.1)
        else:
            swing = -150 if u < -.12 else 245 if u < .2 else 120
            p = dict(rx=side * swing, ry=-150 if u < -.12 else -40, lx=-side * 60, ly=200, lean=(-8 if u < -.12 else 10) * side, brow=-1, eye=1.15)
        mouth = 'grin' if u > .3 else 'flat'
    elif name in ('handshake', 'hug'):
        u = t - CONTACT
        if name == 'handshake':
            p = dict(rx=side * 165, ry=60 + (22 * math.sin(u * 16) if u > 0 else 0), lx=-side * 50, ly=210, eye=1., brow=.4)
        else:
            close = ease(u / .3)
            p = dict(lx=side * (60 + 120 * close), ly=40, rx=side * (60 + 150 * close), ry=20, lean=8 * side * close, eye=.35 if u > 0 else 1, brow=.6)
        mouth = 'grin'
    elif name in ('hit_push', 'hit_slap'):
        u = max(0., t - CONTACT)
        hard = 1. if name == 'hit_push' else .6
        p = dict(lean=-side * 26 * hard * max(0, 1 - u / 1.6), tilt=-side * (28 if name == 'hit_slap' else 10) * max(0, 1 - u / 1.2), lx=-side * 120, ly=-20, rx=side * 60, ry=60,
                 eye=.15 if u < .5 else 1.3, brow=1., y=-20 * max(0, 1 - u * 3))
        mouth = 'o'
    elif name == 'hat_off':
        lift = ease((t - .35) / .35) * (1 - ease((t - max(1.6, length - .7)) / .4))
        p = dict(rx=side * 40, ry=-330 + 40 * (1 - lift) - 110 * lift, lx=-70, ly=205, tilt=-6 * side * lift, eye=1., brow=.5)
        mouth = 'grin'
    elif name == 'jump':
        hop = abs(math.sin(t * 4.4))
        p = dict(y=-170 * hop, squash=1.12 if hop > .55 else .9, lx=-200, ly=-110 * hop + 120, rx=200, ry=-110 * hop + 120, eye=1.2, brow=.7)
        mouth = 'grin'
    elif name == 'run_in':
        p = dict(lean=14 * side, brow=-.4, eye=1.15)
        mouth = 'o' if t < 1 else None
    elif name == 'sneak':
        p = dict(squash=.9, lx=-40, ly=70, rx=40, ry=70, tilt=-6, eye=1.2, brow=.4, lean=6 * side)
        mouth = 'flat'
    return p, mouth


def ease(u):
    u = max(0., min(1., u))
    return u * u * (3 - 2 * u)


def travel(name, t, length, side, gap=440.):
    """Where a walking character is, as an offset from their mark: they really cross the stage instead of standing."""
    if name in ('push', 'slap'):
        return side * max(0., gap - 250) * ease(t / CONTACT)
    if name in ('handshake', 'hug'):
        return side * max(0., gap - (230 if name == 'handshake' else 170)) / 2 * ease(t / CONTACT)
    if name == 'hit_push':
        return -side * 300 * ease((t - CONTACT) / .35)
    if name == 'hit_slap':
        return -side * 70 * ease((t - CONTACT) / .2)
    if name == 'run':
        return side * 120 + 300 * math.sin(t * 2.6) * side

    if name == 'walk_in':
        return -side * OFFSTAGE * (1 - ease(t / min(1.9, max(.8, length * .55))))
    if name == 'run_in':
        return -side * OFFSTAGE * (1 - ease(t / min(.9, max(.5, length * .35))))
    if name == 'walk_out':
        span = min(1.9, max(.8, length * .5))
        return -side * OFFSTAGE * ease((t - (length - span)) / span)
    if name == 'pace':
        return 190 * math.sin(t * 1.45)
    if name == 'sneak':
        return -side * 330 * (1 - ease(t / max(1., length * .9)))
    return None


class Spring:
    """Slightly underdamped follower. This is what makes motion read as animated instead of interpolated."""
    def __init__(self, value):
        self.value, self.speed = value, 0.

    def step(self, target, stiffness=.17, damping=.73):
        self.speed = (self.speed + (target - self.value) * stiffness) * damping
        self.value += self.speed
        return self.value


def word_colour(text, pattern, fallback):
    found = re.search(r'\b(' + '|'.join(COLOURS) + r')\b[\w\s-]{0,18}?\b(?:' + pattern + r')\b', text, re.I)
    return COLOURS[found.group(1).lower()] if found else fallback


def design(text, fallback):
    """A rig's look from the art director's description, so a new cast needs no new drawing code. What the text does
    not say (head shape, hairstyle, build) is chosen from the description's own hash: two characters rarely look alike,
    and one character looks the same in every shot."""
    code = int(hashlib.sha256(text.encode()).hexdigest()[:10], 16)
    pick = lambda options, shift: options[(code >> shift) % len(options)]
    has = lambda pattern: bool(re.search(pattern, text, re.I))
    brim_hat = has(r'\b(?:hat|fedora|stetson|sombrero|slouch hat|sun ?hat|cowboy hat|bowler)\b') and not has(r'\bcap\b|beanie')
    cap = None if brim_hat else word_colour(text, 'cap|beanie', None)
    brim = word_colour(text, 'hat|fedora|stetson|sombrero|bowler', COLOURS['tan']) if brim_hat else None
    head = 'square' if has(r'square|boxy|blocky|rectang') else 'oval' if has(r'oval|egg|long face|tall head') else 'round' if has(r'round') else pick(('round', 'square', 'oval', 'round'), 0)
    hair = ('none' if cap or brim_hat else 'bald' if has(r'bald|no hair|shaved') else 'spiky' if has(r'messy|spiky|wild|mohawk') else 'afro' if has(r'afro|curly|curls|fluffy|puff')
            else 'long' if has(r'long hair|ponytail|braid|pigtail') else 'bun' if has(r'\bbun\b|top ?knot') else 'bob' if has(r'\bbob\b|bowl|fringe|flat [a-z]* ?hair|short hair')
            else 'tuft' if has(r'tuft|single hair|antenna') else 'parted' if has(r'side-parted|side part|neat hair|combed') else pick(('spiky', 'bob', 'long', 'bun', 'afro', 'tuft', 'bald'), 4))
    kobold = has(r'kobold|goblin|gremlin|\bimp\b')
    if kobold and not has(r'hair|tuft|mohawk|bun|afro|cap|beanie|hat'):
        hair = 'tuft'
    return dict(brim=brim, mustache=has(r'mustache|moustache'), collar=has(r'collar|shirt|uniform|jacket|coat|suit|blouse'),
                belt=has(r'belt|uniform|soldier|overalls|suspenders|trousers'), boots=has(r'boots'),
                skin=word_colour(text, 'head|face|skin', fallback), hair_colour=word_colour(text, 'hair|tuft|beard|bun|curls|ponytail', COLOURS['black']),
                cloth=word_colour(text, GARMENT, None), cap=cap, head=head, hair=hair,
                glasses=has(r'glasses|spectacles') and not has('sunglasses|shades'), shades=has(r'sunglasses|shades'), headphones=has(r'headphones|headset'),
                beard=has(r'beard|goatee|stubble|mustache|moustache'), bow=has(r'bow ?tie|\bbow\b'), skirt=has(r'dress|skirt'),
                sleepy=has(r'sleepy|half-closed|tired'),
                squint=has(r'narrow(?:ed)? eyes|squint|slit eyes|narrowed'), red_eyes=has(r'bloodshot|red-rimmed|reddish eyes|slightly red'),
                # 13 Nov (owner): richer, more personal characters; one of the pair is a kobold.
                ears='pointy' if kobold or has(r'pointed ears|pointy ears|elf ears') else None, nose='hook' if kobold or has(r'hooked nose|big nose|long nose') else None,
                fangs=kobold or has(r'fang|tusk'), iris=word_colour(text, 'eyes?', None), freckles=has(r'freckle|warts?\b'), tie=word_colour(text, 'tie|necktie', COLOURS['blue']) if has(r'\b(?:neck)?tie\b') and not has(r'bow ?tie') else None,
                hood=has(r'hoodie|hooded'), ragged=has(r'ragged|torn|patched|scruffy'),
                energy='jittery' if has(r'jitter|restless|hyper|twitch|fidget|manic') else 'calm' if has(r'\bcalm|slow|tired|deadpan|lazy|chill') else 'normal',
                hunch=has(r'hunch|stoop|crouched posture'),
                size=1.1 if has(r'\btall\b|lanky') else .8 if kobold else .88 if has(r'\bshort\b|tiny|small|little') else pick((1., .94, 1.06, 1.), 8),
                girth=1.28 if has(r'chubby|round body|bulky|big|wide|stocky') else .86 if has(r'thin|skinny|slim') else pick((1., 1.12, .92, 1.), 11))


class View:
    """Fixed-point (subpixel) drawing through the camera: without subpixels slow motion jitters by whole pixels."""
    SHIFT = 4

    def __init__(self, cv2, image, zoom, cx, cy, wiggle):
        self.cv2, self.image, self.zoom, self.cx, self.cy, self.wiggle = cv2, image, zoom, cx, cy, wiggle
        self.local = None   # (pivot x, scale, lift): a character further back is drawn smaller and higher

    def point(self, x, y, boil=True):
        if self.local:
            px, k, lift = self.local
            x, y = px + (x - px) * k, GROUND - lift + (y - GROUND) * k
        dx, dy = self.wiggle(x, y) if boil else (0, 0)
        return (int(((x + dx - self.cx) * self.zoom + W / 2) * 16), int(((y + dy - self.cy) * self.zoom + H / 2) * 16))

    @property
    def k(self):
        return self.local[1] if self.local else 1.

    def line(self, a, b, colour, width):
        self.cv2.line(self.image, self.point(*a), self.point(*b), colour, max(1, round(width * self.zoom * self.k)), self.cv2.LINE_AA, self.SHIFT)

    def path(self, points, colour, width):
        for a, b in zip(points, points[1:]):
            self.line(a, b, colour, width)

    def disc(self, centre, radius, colour):
        self.cv2.circle(self.image, self.point(*centre), int(radius * self.zoom * self.k * 16), colour, -1, self.cv2.LINE_AA, self.SHIFT)

    def oval(self, centre, axes, angle, colour, thickness=-1):
        self.cv2.ellipse(self.image, self.point(*centre), (int(axes[0] * self.zoom * self.k * 16), int(axes[1] * self.zoom * self.k * 16)), angle, 0, 360, colour,
                         thickness if thickness < 0 else max(1, round(thickness * self.zoom * self.k)), self.cv2.LINE_AA, self.SHIFT)

    def poly(self, points, colour):
        import numpy as np
        self.cv2.fillPoly(self.image, [np.array([self.point(*p) for p in points], np.int32)], colour, self.cv2.LINE_AA, self.SHIFT)


def joint(a, b, first, second, bend):
    """Two-bone elbow/knee: the joint that reaches b from a; bend picks the side."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    reach = max(1e-3, math.hypot(dx, dy))
    if reach >= first + second:
        scale = (first + second) * .999 / reach
        b = (a[0] + dx * scale, a[1] + dy * scale)
        dx, dy, reach = b[0] - a[0], b[1] - a[1], (first + second) * .999
    along = (first ** 2 - second ** 2 + reach ** 2) / (2 * reach)
    height = math.sqrt(max(0, first ** 2 - along ** 2))
    return (a[0] + along * dx / reach - bend * height * dy / reach, a[1] + along * dy / reach + bend * height * dx / reach), b


def rotate(point, centre, degrees):
    angle = math.radians(degrees)
    x, y = point[0] - centre[0], point[1] - centre[1]
    return centre[0] + x * math.cos(angle) - y * math.sin(angle), centre[1] + x * math.sin(angle) + y * math.cos(angle)


class Rig:
    def __init__(self, look, home, facing):
        self.look, self.home, self.facing, self.side = look, home, facing, facing
        self.stride, self.walking, self.last_x, self.hat_lift = 0., False, 0., 0.
        self.pose = {key: Spring(value) for key, value in REST.items()}
        self.open = Spring(0.)
        self.blink_at = 1.3 + random.random() * 2
        self.variant, self.phase, self.mocap, self.gait = int(home) // 7 % 5, 0., False, False

    def snap_root(self):
        self.last_hands = None                     # a cut may change the pose at once
        for key in ('x', 'y'):
            self.pose[key].value, self.pose[key].speed = 0., 0.
        self.last_x, self.walking, self.facing = None, False, self.side

    def update(self, name, t, length, clock, level, gap=440.):
        talking = level > .03
        # 13 Nov (owner: "nagyon hirtelen, felesleges, túlzó"): starting or stopping a line switched the captured clip
        # from one frame to the next; now idle and talk cross-fade over about a third of a second.
        self.talk_w = getattr(self, 'talk_w', 0.)
        self.talk_w += ((1. if talking else 0.) - self.talk_w) * .12
        base = 'talk' if self.talk_w > .5 else 'idle'
        # A gesture (shrug, point, facepalm...) is played ONCE, when the line it belongs to starts (a listener reacts a
        # beat after the other one starts talking), then the body settles back; it no longer loops for the whole shot.
        g = 1.
        if name in ONE_SHOT:
            start = getattr(self, 'onset', None)
            start = .5 if start is None else start
            dur = min(2.2, max(1.1, TRACKS.length(name, self.variant) if TRACKS else 1.8))
            u = t - start
            g = 0. if u < 0 else ease(u / .35) * (1 - ease((u - dur) / .5))
        target, mouth = action_pose(name if g > .5 else base if name in ONE_SHOT else name, t, length, talking, self.side)
        if name in ONE_SHOT and 0. < g < 1.:
            other, _ = action_pose(base, t, length, talking, self.side)
            target = {k: other.get(k, REST[k]) * (1 - g) + target.get(k, REST[k]) * g for k in set(target) | set(other)}
        self.hat_lift = (ease((t - .35) / .35) * (1 - ease((t - max(1.6, length - .7)) / .4))) if name == 'hat_off' else 0.
        idle = ease_noise(clock, self.home)
        values = {}
        for key, base_value in REST.items():
            stiff = .3 if key in ('tilt', 'eye', 'brow') else .17
            values[key] = self.pose[key].step(target.get(key, base_value), stiff, .7)
        self.mocap = self.gait = False
        gesture = (name if g > .5 else base) if name in ONE_SHOT else ('talk' if talking and name in ('idle', 'stare') else name)
        row = None
        if TRACKS:
            if name in ONE_SHOT or name in ('idle', 'stare', 'talk'):
                calm = TRACKS.gesture('idle', clock, self.side, self.variant)
                speech = TRACKS.gesture('talk', clock, self.side, self.variant)
                if calm and speech:
                    row = {k: calm[k] * (1 - self.talk_w) + speech[k] * self.talk_w for k in MOCAP_KEYS}
                else:
                    row = calm or speech
                act = TRACKS.gesture(name, max(0., t - (getattr(self, 'onset', None) or .5)), self.side, self.variant, loop=False) if name in ONE_SHOT and g > 0 else None
                if row and act:
                    row = {k: row[k] * (1 - g) + act[k] * g for k in MOCAP_KEYS}
                elif act:
                    row = act
                w = 1.
            else:
                row = TRACKS.gesture(gesture, clock if gesture in CONTINUOUS else t, self.side, self.variant)
                w = 1. if gesture in CONTINUOUS else ease(t / .35)
        if row:
            for key in MOCAP_KEYS:
                values[key] = values[key] * (1 - w) + row[key] * w
                self.pose[key].value = values[key]
            self.mocap = True
        if name not in INTERACT and not name.startswith('hit_'):
            # 13 Nov (owner: "furán mozognak"): the captured talk swung the inner hand ~310 px out, across a partner
            # 440 px away, on every line. Talking is a small gesture, and no hand reaches into the other character.
            if gesture in ('talk', 'idle', 'stare'):
                for key in ('lx', 'ly', 'rx', 'ry'):
                    values[key] = REST[key] + (values[key] - REST[key]) * .5
            elif name in ONE_SHOT:
                for key in ('lx', 'ly', 'rx', 'ry'):
                    values[key] = REST[key] + (values[key] - REST[key]) * .75      # a readable gesture, not a big swing
            limit = gap * (.48 if name == 'point' else .32)
            for key in ('lx', 'rx'):
                if values[key] * self.side > limit:
                    values[key] = limit * self.side
            values['lean'] = max(-10., min(10., values['lean'])) if gesture in ('talk', 'idle', 'stare', 'nod', 'point') else values['lean']
            # Real hands do not teleport: at most 24 px a frame (about 0.6 m/s on screen); the captured takes had
            # single-frame jumps of 90 px (13 Nov, "túlzó"). A hit or a push stays fast.
            last = getattr(self, 'last_hands', None)
            if last:
                for key in ('lx', 'ly', 'rx', 'ry'):
                    values[key] = last[key] + max(-24., min(24., values[key] - last[key]))
            for key in ('lx', 'ly', 'rx', 'ry', 'lean'):
                self.pose[key].value = values[key]
        self.last_hands = {key: values[key] for key in ('lx', 'ly', 'rx', 'ry')}
        away = travel(name, t, length, self.side, gap)
        if away is not None:
            # Walking is placed exactly (a spring would lag a whole stage width), and the legs step by distance covered.
            values['x'] = self.pose['x'].value = away
            step = 0. if self.last_x is None else away - self.last_x
            self.walking = abs(step) > .8
            if self.walking:
                self.stride += abs(step) / 62
                self.facing = 1 if step > 0 else -1
                kind = GAIT_OF.get(name, 'walk')
                row, cycle = TRACKS.gait(kind, self.phase, self.facing, self.variant) if TRACKS else (None, None)
                if row:
                    k = STRIDE.get(kind, 2.)
                    self.phase += abs(step) / (cycle * k)
                    values.update(lx=row['lx'], ly=row['ly'], rx=row['rx'], ry=row['ry'], lf=row['lf'] * k, rf=row['rf'] * k,
                                  lfy=row['lfy'] * k ** .5, rfy=row['rfy'] * k ** .5, lean=row['lean'] + 4 * self.facing)
                    values['y'] += row['y']
                    self.gait = self.mocap = True
                else:
                    swing = math.sin(self.stride)
                    values.update(lx=-70 - 70 * swing, ly=205, rx=70 + 70 * swing, ry=205)
                    values['y'] -= 9 * abs(math.cos(self.stride))
                    values['lean'] += 5 * self.facing
            else:
                self.facing = self.side
        else:
            self.walking = False
        self.last_x = values['x'] if away is not None else None
        # Personal movement (13 Nov): a jittery character fidgets, twitches its head and bounces on its toes; a calm
        # one breathes slowly and barely moves; a hunched one leans towards whoever it talks to.
        energy = self.look.get('energy', 'normal')
        k, rate = {'jittery': (1.5, 1.3), 'calm': (.45, .6)}.get(energy, (1., 1.))
        values['y'] += 5 * k ** .5 * math.sin(clock * 2.4 * rate + self.home)       # breathing
        values['lean'] += 1.6 * idle * k + (7. * self.facing if self.look.get('hunch') and not getattr(self, 'seated', False) else 0.)
        if getattr(self, 'seated', False) and name not in INTERACT:
            # Side by side on a couch a lean towards the other put Krix's head on Dale's (13 Nov): sit upright.
            values['lean'] = max(-4., min(4., values['lean']))
        values['ly'] += 7 * k * math.sin(clock * 2.4 * rate + 1)
        values['ry'] += 7 * k * math.sin(clock * 2.4 * rate + 2)
        values['tilt'] += 2.2 * idle * k + (9 * level * k ** .5 * math.sin(clock * 15))
        if energy == 'jittery':
            # Restless but smooth: a light weight shift and a head that keeps tilting (the stepped twitch and the
            # abs-sine bounce read as glitches, owner 13 Nov).
            values['y'] -= 4 * (1 + math.sin(clock * 3.6 + self.home)) / 2
            values['tilt'] += 2.5 * math.sin(clock * 2.9) * math.sin(clock * .8 + self.home)
        if clock > self.blink_at:
            values['eye'] *= .08
            if clock > self.blink_at + .1:
                self.blink_at = clock + (.7 + random.random() * 1.4 if self.look.get('energy') == 'jittery' else 1.6 + random.random() * 3)
        self.mouth, self.level = mouth, self.open.step(level, .5, .55)
        self.values = values

    def draw(self, view, seated):
        v, look = self.values, self.look
        root = (self.home + v['x'], GROUND + v['y'] - (195 if seated else 0))
        squash = v['squash']
        size = look['size']
        torso = 225 * size / squash
        leg = 290 * size
        hip = (root[0], root[1] - (0 if seated else leg) + (leg - leg * squash) * .2)
        chest = rotate((hip[0], hip[1] - torso), hip, v['lean'])
        shoulder_l, shoulder_r = rotate((chest[0] - 62, chest[1] + 26), chest, v['lean']), rotate((chest[0] + 62, chest[1] + 26), chest, v['lean'])
        cloth = look['cloth'] or INK
        width = 150 * look['girth'] if look['cloth'] else 20
        # Legs first: the body covers the hips.
        for side, key in ((-1, 'lf'), (1, 'rf')):
            start = (hip[0] + side * 34, hip[1])
            if seated:
                foot = (hip[0] + side * 110 + side * 14, GROUND - 6 + 5 * math.sin(view.time * 2 + side))
                knee = (hip[0] + side * 128, hip[1] - 16)
            elif self.mocap:
                # Captured feet: placed and lifted as the actor's were, knees bending the way the body faces.
                foot = (root[0] + v[key], GROUND - max(0., v[key + 'y']))
                knee, foot = joint(start, foot, leg * .52, leg * .52, -self.facing * .9)
            elif self.walking:
                phase = self.stride + (0 if side < 0 else math.pi)
                foot = (root[0] + 95 * math.sin(phase), GROUND - 46 * max(0, math.cos(phase)))
                knee, foot = joint(start, foot, leg * .52, leg * .52, -self.facing * .9)
            else:
                foot = (root[0] + v[key], GROUND - max(0, -v['y'] * .55))
                knee, foot = joint(start, foot, leg * .52, leg * .52, -side * .9)
            view.path([start, knee, foot], INK, 25)
            toe = (self.facing if self.walking or self.mocap else side)
            if look['boots']:
                view.poly([(foot[0] - 22, foot[1] - 46), (foot[0] + 22, foot[1] - 46), (foot[0] + 22 + toe * 26, foot[1] + 14), (foot[0] - 22, foot[1] + 14)], (40, 55, 85))
            view.oval((foot[0] + toe * 24, foot[1] + 5), (54 if look['boots'] else 50, 24 if look['boots'] else 22), 0, INK)
            if not look['boots'] and not look.get('ears'):
                view.path([(foot[0] - 22 + toe * 4, foot[1] + 20), (foot[0] + 66 * toe if toe > 0 else foot[0] - 66, foot[1] + 20)], (245, 245, 245), 9)   # sneaker sole
        if look['skirt'] and look['cloth']:
            hem = [(hip[0] - width * .82, hip[1] + 150), (hip[0] + width * .82, hip[1] + 150), (hip[0] + width * .5, hip[1] - 20), (hip[0] - width * .5, hip[1] - 20)]
            view.poly([(hem[0][0] - 9, hem[0][1] + 9), (hem[1][0] + 9, hem[1][1] + 9), (hem[2][0] + 9, hem[2][1]), (hem[3][0] - 9, hem[3][1])], INK)
            view.poly(hem, cloth)
        self.limb(view, shoulder_l, (chest[0] + v['lx'], chest[1] + v['ly']), -1, look, width)
        # Torso as a soft capsule with an inked edge.
        body = [hip, chest]
        view.path(body, INK, width + 16)
        view.disc(hip, (width + 16) / 2, INK), view.disc(chest, (width + 16) / 2, INK)
        view.path(body, cloth, width)
        view.disc(hip, width / 2, cloth), view.disc(chest, width / 2, cloth)
        if look['cloth']:
            shade = tuple(int(c * .78) for c in cloth)
            edge = [(p[0] + width * .3, p[1]) for p in body]
            view.path(edge, shade, width * .32)
            if look['belt']:
                waist = (hip[0] + (chest[0] - hip[0]) * .18, hip[1] + (chest[1] - hip[1]) * .18)
                view.path([(waist[0] - width * .52, waist[1]), (waist[0] + width * .52, waist[1])], INK, 30)
                view.path([(waist[0] - width * .48, waist[1]), (waist[0] + width * .48, waist[1])], (40, 55, 80), 20)
                view.oval(waist, (16, 13), 0, (60, 170, 210))
        neck = rotate((chest[0], chest[1] - 8), chest, v['lean'])
        if look['cloth'] and look['collar']:
            light = tuple(min(255, int(c * 1.18 + 20)) for c in cloth)
            for d in (-1, 1):
                tri = [(neck[0], neck[1] + 34), (neck[0] + d * 58, neck[1] - 6), (neck[0] + d * 20, neck[1] - 14)]
                view.poly([(x + d * 4, y + 4) for x, y in tri], INK)
                view.poly(tri, light)
        if look['cloth'] and look.get('hood'):
            hood = tuple(int(c * .8) for c in cloth)
            view.oval((neck[0], neck[1] + 10), (width * .62, 44), v['lean'], INK)
            view.oval((neck[0], neck[1] + 8), (width * .54, 34), v['lean'], hood)
            for d in (-1, 1):
                top = rotate((neck[0] + d * 22, neck[1] + 30), chest, 0)
                view.path([top, (top[0] + d * 4, top[1] + 92)], (245, 245, 245), 8)
                view.disc((top[0] + d * 4, top[1] + 96), 8, (245, 245, 245))
        if look.get('tie'):
            knot = (neck[0], neck[1] + 26)
            blade = [(knot[0] - 16, knot[1] + 10), (knot[0] + 16, knot[1] + 10), (knot[0] + 30 + 8 * math.sin(view.time * 2), knot[1] + 150), (knot[0] + 6, knot[1] + 178), (knot[0] - 14, knot[1] + 148)]
            view.poly([(x + 5, y + 5) for x, y in blade], INK)
            view.poly(blade, look['tie'])
            view.oval(knot, (20, 16), 0, tuple(int(c * .7) for c in look['tie']))
        if look['cloth'] and look.get('ragged'):
            for i in range(-2, 3):
                hem = (hip[0] + i * width * .22, hip[1] + width * .3)
                tri = [(hem[0] - 20, hem[1] - 20), (hem[0] + 20, hem[1] - 20), (hem[0] + 4 * (i % 2 * 2 - 1), hem[1] + 34)]
                view.poly([(x, y + 7) for x, y in tri], INK)
                view.poly(tri, cloth)
        head = rotate((neck[0], neck[1] - 138), neck, v['lean'] * .6 + v['tilt'] * .5)
        self.limb(view, shoulder_r, (chest[0] + v['rx'], chest[1] + v['ry']), 1, look, width)
        if look['bow']:
            for d in (-1, 1):
                view.poly([(neck[0], neck[1] + 20), (neck[0] + d * 62, neck[1] - 12), (neck[0] + d * 62, neck[1] + 52)], (60, 60, 225))
            view.disc((neck[0], neck[1] + 20), 14, INK)
        self.head(view, head, v)

    def limb(self, view, shoulder, hand, side, look, width):
        elbow, hand = joint(shoulder, hand, 135, 135, -side * .8)
        sleeve = 44 if look['cloth'] else 20
        view.path([shoulder, elbow, hand], INK, sleeve + 13)
        if look['cloth']:
            view.path([shoulder, elbow, hand], look['cloth'], sleeve)
        view.disc(hand, 32, INK), view.disc(hand, 25, look['skin'])
        thumb = (hand[0] - side * 22, hand[1] - 24)
        view.disc(thumb, 15, INK), view.disc(thumb, 9, look['skin'])

    def head(self, view, c, v):
        look, tilt = self.look, v['tilt']
        at = lambda dx, dy: rotate((c[0] + dx, c[1] + dy), c, tilt)
        radius, hair, tone = 134, look['hair'], look['hair_colour']
        arc = lambda r, a0, a1: [at(math.cos(math.radians(a)) * r, math.sin(math.radians(a)) * r) for a in range(a0, a1 + 1, 8)]

        def skull(r, colour):
            if look['head'] == 'square':
                view.poly([at(-r, -r * .92), at(r, -r * .92), at(r, r * .92), at(-r, r * .92)], colour)
                for corner in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    view.disc(at(corner[0] * r * .78, corner[1] * r * .72), r * .26, colour)
            elif look['head'] == 'oval':
                view.oval(c, (r * .86, r * 1.1), tilt, colour)
            else:
                view.disc(c, r, colour)
        # Hair that sits behind the head.
        if hair == 'spiky':
            for i in range(9):
                angle = math.radians(-168 + i * 19.5)
                tip = (radius + 62 + 16 * (i % 2)) + self.pose['y'].speed * .9
                base = radius - 16
                left, right = angle - .16, angle + .16
                view.poly([at(math.cos(left) * base, math.sin(left) * base), at(math.cos(angle) * tip, math.sin(angle) * tip), at(math.cos(right) * base, math.sin(right) * base)], tone)
        elif hair == 'afro':
            view.disc(at(0, -46), radius * 1.3, INK)
            view.disc(at(0, -46), radius * 1.3 - 9, tone)
        elif hair == 'long':
            sway = self.pose['x'].speed * .6
            view.poly([at(-radius - 22, -60), at(radius + 22, -60), at(radius + 30 - sway, radius + 96), at(-radius - 30 - sway, radius + 96)], INK)
            view.poly([at(-radius - 13, -60), at(radius + 13, -60), at(radius + 20 - sway, radius + 86), at(-radius - 20 - sway, radius + 86)], tone)
        elif hair == 'bun':
            view.disc(at(0, -radius - 40), 62, INK)
            view.disc(at(0, -radius - 40), 53, tone)
        if look.get('ears') == 'pointy':
            # Long kobold ears reaching out and up; a jittery body makes them flick.
            flick = 10 * math.sin(view.time * 9 + self.home) if look.get('energy') == 'jittery' else 0.
            inner = tuple(min(255, int(c * .7 + 70)) for c in (150, 120, 235))
            for d in (-1, 1):
                root_a, root_b = at(d * (radius - 30), -58), at(d * (radius - 18), 34)
                tip = at(d * (radius + 150), -128 + flick * d)
                view.poly([root_a, tip, root_b], INK)
                view.poly([at(d * (radius - 22), -44), at(d * (radius + 118), -112 + flick * d), at(d * (radius - 12), 20)], look['skin'])
                view.poly([at(d * (radius + 4), -30), at(d * (radius + 82), -92 + flick * d), at(d * (radius + 6), 4)], inner)
        skull(radius + 9, INK)
        skull(radius, look['skin'])
        # A soft cheek shadow on the far side gives the flat head some volume.
        shade = tuple(int(c * .93) for c in look['skin'])
        view.oval(at(-self.facing * radius * .5, radius * .42), (radius * .3, radius * .22), tilt, shade)
        if look.get('freckles'):
            for fx, fy in ((-70, 34), (-52, 48), (-84, 52), (70, 34), (52, 48), (84, 52)):
                view.disc(at(fx, fy), 6, tuple(int(c * .62) for c in look['skin']))
        # Hair and hats that sit on top of the head; the face below the brows stays readable.
        lift = getattr(self, 'hat_lift', 0.)
        if look['cap'] and lift > 0:
            # The cap rides up with the hand that took it off; hair shows underneath.
            if hair == 'none':
                view.poly(arc(radius, -164, -16) + [at(radius, -88), at(-radius, -88)], tone)
            base_at = at
            at = lambda dx, dy: base_at(dx + self.side * 30 * lift, dy - 175 * lift)
            arc = lambda r, a0, a1: [at(math.cos(math.radians(a)) * r, math.sin(math.radians(a)) * r) for a in range(a0, a1 + 1, 8)]
        if look['cap'] or hair in ('bob', 'long', 'bun'):
            colour = look['cap'] or tone
            low = -92 if look['cap'] else -74
            view.poly(arc(radius + 9, -164, -16) + [at(radius + 9, low + 8), at(-radius - 9, low + 8)], INK)
            view.poly(arc(radius, -164, -16) + [at(radius, low), at(-radius, low)], colour)
            if look['cap']:
                view.path([at(-self.facing * 60, -92), at(-self.facing * (radius + 56), -86)], INK, 34)
                view.path([at(-self.facing * 60, -92), at(-self.facing * (radius + 46), -86)], colour, 18)
                if lift > 0:
                    at = base_at
                    arc = lambda r, a0, a1: [at(math.cos(math.radians(a)) * r, math.sin(math.radians(a)) * r) for a in range(a0, a1 + 1, 8)]
            elif hair == 'bob':
                for d in (-1, 1):
                    view.path([at(d * (radius - 4), -70), at(d * (radius + 4), 46)], INK, 40)
                    view.path([at(d * (radius - 4), -70), at(d * (radius + 4), 40)], tone, 24)
        elif hair == 'tuft':
            view.poly([at(-26, -radius + 6), at(0, -radius - 74 - self.pose['y'].speed), at(26, -radius + 6)], tone)
        elif hair == 'parted':
            s = -self.facing
            view.poly(arc(radius + 10, -172, -8) + [at(radius + 6, -66), at(s * 30, -96), at(-radius - 6, -60)], INK)
            view.poly(arc(radius, -170, -10) + [at(radius - 4, -74), at(s * 30, -104), at(-radius + 4, -68)], tone)
            view.path([at(s * 34, -radius + 6), at(s * 52, -100)], tuple(int(c * .7) for c in tone), 7)      # the parting
        if look['headphones']:
            view.path(arc(radius + 26, -170, -10), INK, 26)
            for d in (-1, 1):
                view.disc(at(d * (radius + 14), 4), 46, INK)
                view.disc(at(d * (radius + 14), 4), 34, (70, 70, 80))
        if look['beard']:
            view.poly(arc(radius - 4, 18, 162), tone)
        if look['brim']:
            lift = getattr(self, 'hat_lift', 0.)
            hx, hy = self.side * 30 * lift, -175 * lift
            hat = lambda dx, dy: at(dx + hx, dy + hy)
            band = tuple(int(c * .55) for c in look['brim'])
            view.poly([hat(-radius * .78, -radius * .62), hat(-radius * .62, -radius * 1.32), hat(radius * .62, -radius * 1.32), hat(radius * .78, -radius * .62)], INK)
            view.poly([hat(-radius * .7, -radius * .64), hat(-radius * .56, -radius * 1.24), hat(radius * .56, -radius * 1.24), hat(radius * .7, -radius * .64)], look['brim'])
            view.path([hat(-radius * .72, -radius * .76), hat(radius * .72, -radius * .76)], band, 26)
            view.oval(hat(0, -radius * .6), (radius * 1.55, radius * .3), tilt, INK)
            view.oval(hat(0, -radius * .62), (radius * 1.48, radius * .23), tilt, look['brim'])
        gaze = self.facing * 12 + v['look'] * 18
        openness = max(.05, min(1.6, v['eye'] * (.62 if look['sleepy'] else 1) * (.55 if look.get('squint') else 1)))
        white = (205, 212, 248) if look.get('red_eyes') else (250, 250, 250)      # a pink, slightly bloodshot white
        for side in (-1, 1):
            eye = at(side * 54 + gaze * .5, -16)
            view.oval(eye, (34, max(3, 38 * openness)), tilt, white)
            if look.get('red_eyes') and openness > .2:
                for vein in (-1, 1):
                    view.path([at(side * 54 + gaze * .5 + vein * 30, -16 + vein * 3), at(side * 54 + gaze * .5 + vein * 18, -14)], (70, 80, 215), 3)
            view.oval(eye, (34, max(3, 38 * openness)), tilt, INK, 7)
            if openness > .22:
                if look.get('iris'):
                    view.disc(at(side * 54 + gaze * 1.2, -14), min(26, 30 * openness), look['iris'])
                view.disc(at(side * 54 + gaze * 1.2, -14), min(18, 24 * openness) * (.6 if look.get('iris') else 1), INK)
                view.disc(at(side * 54 + gaze * 1.2 + 6, -22), min(6, 8 * openness), (255, 255, 255))   # catchlight
            if look['sleepy'] and openness > .22:
                edge = -16 - 38 * openness * .25
                lid = [at(side * 54 - 38 + gaze * .5, -16 - 42 * openness), at(side * 54 + 38 + gaze * .5, -16 - 42 * openness),
                       at(side * 54 + 38 + gaze * .5, edge), at(side * 54 - 38 + gaze * .5, edge)]
                view.poly(lid, look['skin'])
                view.path([lid[3], lid[2]], INK, 9)                                                       # heavy, tired lid
            if look.get('squint') and openness > .1:
                view.path([at(side * 54 - 34 + gaze * .5, -16 + 38 * openness * .85), at(side * 54 + 34 + gaze * .5, -16 + 38 * openness * .85)], INK, 8)
            brow = v['brow'] - (.35 if look.get('squint') else 0.)
            inner, outer = at(side * 20 + gaze * .4, -62 - brow * 16 + (max(0, -brow) * 18)), at(side * 88 + gaze * .4, -62 - brow * 16 - (max(0, -brow) * 18))
            view.path([inner, outer], INK, 13)
        if look['shades']:
            for side in (-1, 1):
                view.oval(at(side * 54, -16), (46, 34), tilt, INK)
            view.path([at(-20, -22), at(20, -22)], INK, 10)
        elif look['glasses']:
            for side in (-1, 1):
                view.oval(at(side * 54, -16), (48, 48), tilt, INK, 9)
            view.path([at(-8, -16), at(8, -16)], INK, 8)
        if look.get('nose') == 'hook':
            n = self.facing
            tip = [at(gaze * .7 - n * 4, -4), at(gaze * .7 + n * 96, 44), at(gaze * .7 + n * 58, 66), at(gaze * .7 - n * 18, 52)]
            view.poly([(x + 5, y + 5) for x, y in tip], INK)
            view.poly(tip, tuple(int(c * .74) for c in look['skin']))
            view.path(tip[1:] + tip[:1], INK, 7)
            view.disc(at(gaze * .7 + n * 26, 54), 7, INK)
        self.draw_mouth(view, at, gaze)
        if look.get('fangs'):
            x = gaze * .6
            for d in (-1, 1):
                fang = [at(x + d * 22, 66), at(x + d * 38, 66), at(x + d * 30, 92)]
                view.poly([(px, py + 3) for px, py in fang], INK)
                view.poly(fang, (250, 250, 240))

    def draw_mouth(self, view, at, gaze):
        level, kind = self.level, self.mouth
        x, y = gaze * .6, 70
        if self.look.get('mustache'):
            tone = self.look['hair_colour'] if self.look['hair_colour'] != COLOURS['black'] else (40, 60, 95)
            for d in (-1, 1):
                view.poly([at(x, y - 26), at(x + d * 62, y - 14), at(x + d * 52, y + 4), at(x, y - 8)], tone)
        if level > .06 or kind == 'o':
            height = max(level * 58, 40 if kind == 'o' else 0)
            view.oval(at(x, y), (34 + level * 14, height), 0, INK)
            view.oval(at(x, y + height * .42), (22, height * .42), 0, (70, 70, 220))
        elif kind == 'grin':
            view.poly([at(x - 66, y - 18), at(x + 66, y - 18), at(x + 42, y + 34), at(x, y + 44), at(x - 42, y + 34)], INK)
            view.poly([at(x - 54, y - 12), at(x + 54, y - 12), at(x + 44, y + 4), at(x - 44, y + 4)], (250, 250, 250))
        elif kind == 'frown':
            view.path([at(x - 44, y + 22), at(x - 18, y + 2), at(x + 18, y + 2), at(x + 44, y + 22)], INK, 12)
        elif kind == 'flat':
            view.path([at(x - 36, y + 6), at(x + 36, y + 2)], INK, 12)
        else:
            view.path([at(x - 42, y - 6), at(x - 16, y + 12), at(x + 16, y + 12), at(x + 42, y - 6)], INK, 12)


def couch(view):
    wood, seat = (35, 65, 105), (60, 85, 135)
    view.poly([(90, 1095), (990, 1095), (1005, 1400), (75, 1400)], INK)
    view.poly([(104, 1108), (976, 1108), (990, 1388), (90, 1388)], seat)
    for left in (40, 915):
        view.poly([(left, 1205), (left + 125, 1205), (left + 125, 1500), (left, 1500)], INK)
        view.poly([(left + 12, 1217), (left + 113, 1217), (left + 113, 1488), (left + 12, 1488)], wood)
    view.poly([(150, 1295), (930, 1295), (930, 1500), (150, 1500)], INK)
    view.poly([(162, 1307), (918, 1307), (918, 1488), (162, 1488)], wood)


def prop_placement(motion, t, length):
    x, y, scale, angle = 540., 1600., 1., 0.
    if motion == 'wobble':
        angle = 7 * math.sin(t * 8)
    elif motion == 'bounce':
        y -= 90 * abs(math.sin(t * 5.5))
        scale = 1 + .06 * math.sin(t * 11)
    elif motion == 'grow':
        scale = 1 + .85 * min(1, t / max(.4, length * .8)) ** 2 + .03 * math.sin(t * 18)
    elif motion == 'shake':
        x += 20 * math.sin(t * 40)
        angle = 5 * math.sin(t * 33)
    elif motion == 'fly_in':
        arrive = min(1, t / .55)
        x += (1 - arrive) ** 3 * 900
        angle = (1 - arrive) * 200 + 4 * math.sin(t * 6)
    return x, y, scale, angle


class _Flat:
    zoom, cx, cy = 1., W / 2, H / 2


FLAT = _Flat()   # screen space: the illustration does not move with the camera


def insert_placement(t, index, zoom=1., crowd=None):
    """The picture of what is said (owner 12 Nov, after the reference shorts): it pops in above the characters a moment
    after the shot starts and then floats gently, like a drawn thought."""
    side = 540 + (90 if index % 2 else -90)
    pop = min(1., max(0., (t - .18) / .32))
    c = 1.9   # ease-out-back: a small overshoot, then it settles
    scale = max(.01, 1 + (c + 1) * (pop - 1) ** 3 + c * (pop - 1) ** 2) if pop > 0 else .01
    # Large and in the clear upper half, like the reference shorts' drawn pictures; the captions live on the floor band
    # now, so the picture may start near the top. Its base stays above the heads (about y 640 in a close set-up).
    if zoom >= 1.3:
        # A close set-up brings the heads up into the picture's place (13 Nov, "why am i pixelating": a face sat on the
        # lead's head): the picture goes smaller to the top corner away from the characters on screen.
        side = W * (.75 if (crowd if crowd is not None else W / 2) < W / 2 else .25)
        return side, 470 + 6 * math.sin(t * 2.2), scale * .68, 2. * math.sin(t * 1.3)
    return side, 615 + 8 * math.sin(t * 2.2), scale, 2.5 * math.sin(t * 1.3)


def composite(np, cv2, frame, sprite, x, y, scale, angle, view):
    """The prop sprite through the same camera as the rigs, standing on its base."""
    h, w = sprite.shape[:2]
    size = scale * view.zoom
    matrix = cv2.getRotationMatrix2D((w / 2, h), -angle, size)
    matrix[0, 2] += (x - view.cx) * view.zoom + W / 2 - w / 2
    matrix[1, 2] += (y - view.cy) * view.zoom + H / 2 - h
    layer = cv2.warpAffine(sprite, matrix, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    alpha = layer[..., 3:].astype(np.float32) / 255
    frame[:] = (layer[..., :3] * alpha + frame * (1 - alpha)).astype(np.uint8)


def load_sprite(np, cv2, path, height, width=None):
    """White-background FLUX prop to RGBA: only white connected to the border is removed, so white inside the prop stays."""
    image = cv2.imread(str(path))
    h, w = image.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)] + [(x, h - 1) for x in range(0, w, max(1, w // 12))] + [(0, h // 2), (w - 1, h // 2)]
    for seed in seeds:
        if not mask[seed[1] + 1, seed[0] + 1]:
            cv2.floodFill(image, mask, seed, 0, (26, 26, 26), (26, 26, 26), flags)
    alpha = 255 - mask[1:-1, 1:-1]
    # A painted floor shadow or white ground patch under the feet is not part of the character (11 Nov: white ovals).
    low = int(h * .82)
    pale = (image[low:].min(axis=2) > 205)
    alpha[low:][pale] = 0
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    ys, xs = np.where(alpha > 40)
    sprite = np.dstack((image, alpha))[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    scale = height / sprite.shape[0]
    if width and sprite.shape[1] * scale > width:
        scale = width / sprite.shape[1]      # a wide prop (a lying bear) must not fill the floor between the two (13 Nov)
    return cv2.resize(sprite, (max(1, round(sprite.shape[1] * scale)), max(1, round(sprite.shape[0] * scale))), interpolation=cv2.INTER_AREA)


VIEWS = dict(wide=(1., 960), two=(1.2, 1000), close=(1.55, 930), low=(1.3, 1150))
TRANSITIONS = ('whip', 'pop', 'flash', 'cut')


def cuts(shot, frames, speaking, seed):
    """Camera set-ups inside one shot, cut where the talking passes to the other character (like the reference Shorts:
    the picture goes to whoever speaks), never more often than every two seconds. Returns [(first frame, view, who,
    move)]. While somebody walks the camera stays wide enough to see it."""
    rng = random.Random(seed)
    acting = shot.get('acting') or {}
    travelling = any(acting.get(role) in MOVING + ('jump', 'dance', 'faint', 'crouch') for role in ('lead', 'support'))
    framing = str(shot.get('framing', '')).lower()
    first = 'close' if 'close' in framing and not travelling else 'two' if 'two' in framing or 'medium' in framing else 'wide'
    def voice(at):
        window = {role: sum(speaking[role][at:at + 12]) for role in ('lead', 'support')}
        return max(window, key=window.get) if max(window.values()) > .25 else None
    turns, last, current = [0], 0, voice(0)
    for at in range(12, frames - 36, 6):
        now = voice(at)
        if now and now != current and at - last >= 48:
            turns.append(at);last = at
        current = now or current
    if shot.get('pace') == 'fast':
        # A visual gag is cut like the reference Shorts: a new set-up every 1.2-1.6 seconds, the action wide enough to
        # read and the reaction close on the face.
        step = rng.choice((30, 34, 38))
        turns = list(range(0, max(1, frames - 20), step))
    elif len(turns) == 1:
        # Nobody changes: one calm set-up, or two when the shot is long.
        turns += [frames // 2] if frames > 220 else []
    plan, view = [], first
    for i, at in enumerate(turns):
        who = voice(at) or (shot.get('cast') if shot.get('cast') in ('lead', 'support') else rng.choice(('lead', 'support')))
        plan.append((at, view, who, 'hold' if i % 2 else 'push'))
        options = ['wide', 'two'] if travelling and (shot.get('pace') != 'fast' or i + 2 < len(turns)) else [v for v in ('two', 'close') if v != view]
        view = rng.choice([v for v in options if v != view] or options)
    return plan


def camera(plan, frame_no, frames, shot, positions):
    """Zoom and centre for one frame from the cut plan: each set-up eases in or out a little instead of sitting still."""
    index = max(i for i, c in enumerate(plan) if c[0] <= frame_no)
    start, view, who, move = plan[index]
    end = plan[index + 1][0] if index + 1 < len(plan) else frames
    u = (frame_no - start) / max(1, end - start)
    zoom, cy = VIEWS[view]
    focus = 540 if view == 'wide' else (positions['lead'] + positions['support']) / 2 if view == 'two' and shot.get('cast') == 'both' else positions[who]
    zoom *= dict(push=1 + .05 * ease(u), pull=1.05 - .05 * ease(u), drift=1.02, hold=1.)[move]
    if move == 'drift':
        focus += 40 * (u - .5)
    if shot.get('beat') == 'twist':
        # The punchline gets a slow push-in instead of a 0.2 s zoom jolt (owner 13 Nov: "hirtelen").
        zoom *= 1 + .06 * ease((frame_no / FPS - frames / FPS * .3) / 1.2)
    half, halfh = W / 2 / zoom, H / 2 / zoom
    return zoom, min(max(focus, half), W - half), min(max(cy, halfh), H - halfh)


def transition(np, cv2, frame, kind, frame_no, direction):
    """How a new shot arrives: a whip from the side, a white flash, or a plain cut (the pop is a camera zoom)."""
    if kind == 'whip' and frame_no < 6:
        u = 1 - frame_no / 6
        shift = np.float32([[1, 0, direction * W * u * u], [0, 1, 0]])
        moved = cv2.warpAffine(frame, shift, (W, H), borderMode=cv2.BORDER_REPLICATE)
        size = max(1, int(140 * u)) | 1
        frame[:] = cv2.blur(moved, (size, 1))
    elif kind == 'flash' and frame_no < 5:
        strength = .8 * (1 - frame_no / 5)
        frame[:] = cv2.addWeighted(frame, 1 - strength, np.full_like(frame, 255), strength, 0)


def envelopes(speech, frames):
    """Per-speaker mouth level for every frame, from the mix's speech timeline."""
    levels = {'lead': [0.] * frames, 'support': [0.] * frames}
    for cue in speech:
        start = round(cue['start'] * FPS)
        for i, value in enumerate(cue['envelope']):
            if 0 <= start + i < frames:
                levels[cue['speaker']][start + i] = value
    return levels


def run(request):
    import numpy as np
    import cv2
    global TRACKS
    random.seed(request.get('seed', 7))
    if request.get('mocap'):
        import story_mocap
        TRACKS = story_mocap.load(request['mocap'])
    shots, folder, ffmpeg = request['shots'], Path(request['folder']), request['ffmpeg']
    plates = [cv2.resize(cv2.imread(p), (W, H), interpolation=cv2.INTER_CUBIC) for p in (request.get('plates') or [request['plate']])]
    sprite = load_sprite(np, cv2, request['prop'], request.get('prop_height', 300), request.get('prop_width', 260)) if request.get('prop') else None
    art = request['art']
    inserts = {}
    def insert_sprite(path):
        if path not in inserts:
            inserts[path] = load_sprite(np, cv2, path, request.get('insert_height', 400), request.get('insert_width', 600)) if path and Path(path).is_file() else None
        return inserts[path]
    rigs = dict(lead=Rig(design(art['lead'], COLOURS['yellow']), 320., 1), support=Rig(design(art['support'], COLOURS['green']), 760., -1))
    total = sum(s['frames'] for s in shots)
    levels = envelopes(request.get('speech', []), total)
    done, written = 0, []
    jitter = random.Random(request.get('seed', 7) + 11)
    for index, shot in enumerate(shots, 1):
        out = folder / f'clip-{index}.mp4'
        encoder = subprocess.Popen([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', str(out)], stdin=subprocess.PIPE)
        for rig in rigs.values():
            rig.snap_root()
        length = shot['frames'] / FPS
        acting, cast = shot.get('acting') or {}, shot.get('cast', 'both')
        visible = ('lead', 'support') if cast == 'both' else (cast,) if cast in rigs else ()
        speaking = {role: levels[role][done:done + shot['frames']] for role in rigs}
        # When each one's line starts in this shot: a speaker gestures on it, a listener reacts a beat later.
        starts = {role: next((i / FPS for i, v in enumerate(speaking[role]) if v > .03), None) for role in rigs}
        for role, other in (('lead', 'support'), ('support', 'lead')):
            rigs[role].onset = starts[role] if starts[role] is not None else (starts[other] + 1.2 if starts[other] is not None else None)
        # Space: in some shots one character stands further back, smaller and higher, so the picture has depth.
        together = any((acting.get(r) in INTERACT) for r in rigs) or shot.get('seated')
        layout = ((1., 0.), (1., 0.))   # owner 12 Nov: random depth jumps read as chaotic; both stand on one floor line
        depth = dict(lead=layout[0], support=layout[1])
        plan = cuts(shot, shot['frames'], speaking, request.get('seed', 7) * 31 + index)
        arrive = 'cut'
        foreground = None    # what is drawn over the plate (rigs, prop, picture): the caption avoids only this (13 Nov)
        for frame_no in range(shot['frames']):
            t, clock = frame_no / FPS, (done + frame_no) / FPS
            zoom, cx, cy = camera(plan, frame_no, shot['frames'], shot, {role: rig.home + rig.pose['x'].value for role, rig in rigs.items()})
            if arrive == 'pop' and frame_no < 7:
                zoom *= 1 + .24 * (1 - frame_no / 7) ** 2
                cx, cy = min(max(cx, W / 2 / zoom), W - W / 2 / zoom), min(max(cy, H / 2 / zoom), H - H / 2 / zoom)
            boil_tick = int(clock * BOIL_FPS)
            def wiggle(x, y, tick=boil_tick):
                # Small line wobble that changes a few times a second: the "drawn by hand" quiver.
                return (math.sin(x * .017 + y * .011 + tick * 2.3) * 1.3, math.cos(x * .013 - y * .019 + tick * 1.7) * 1.3)
            scale = zoom
            drift = 1.012 + .006 * math.sin(clock * .7)
            matrix = np.float32([[scale * drift, 0, W / 2 - cx * scale * drift], [0, scale * drift, H / 2 - cy * scale * drift]])
            frame = cv2.warpAffine(plates[min(len(plates) - 1, int(shot.get('plate', 0)))], matrix, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            sample_mask = frame_no % 6 == 0
            backdrop = cv2.resize(frame, (108, 192), interpolation=cv2.INTER_AREA).astype(np.int16) if sample_mask else None
            view = View(cv2, frame, zoom, cx, cy, wiggle)
            view.time = clock
            seated = bool(shot.get('seated'))
            if seated:
                couch(view)
            moves = {role: acting.get(role, 'idle') for role in rigs}
            for role, other in (('lead', 'support'), ('support', 'lead')):
                if role in visible and other in visible:
                    if moves[role] in ('push', 'slap') and t >= CONTACT and moves[other] not in INTERACT:
                        moves[other] = 'hit_' + moves[role]          # the one who is pushed or slapped reacts
                    elif moves[role] in ('handshake', 'hug') and moves[other] in ('idle', 'stare', 'talk', 'nod'):
                        moves[other] = moves[role]                   # a handshake takes two
            gap = abs(rigs['support'].home - rigs['lead'].home)
            for name in sorted(visible, key=lambda n: depth[n][0]):   # the one further back is drawn first
                rig = rigs[name]
                level = levels[name][done + frame_no]
                rig.seated = seated
                rig.update(moves[name], t, length, clock, level, gap)
                k, lift = depth[name]
                view.local = None if seated or k == 1. else (rig.home + rig.values['x'], k, lift)
                if not seated:
                    view.oval((rig.home + rig.values['x'], GROUND + 18), (150, 24), 0, (0, 0, 0))
                rig.draw(view, seated)
                view.local = None
            if sprite is not None and acting.get('prop', 'none') != 'none':
                composite(np, cv2, frame, sprite, *prop_placement(acting['prop'], t, length), view)
            picture = insert_sprite(shot.get('insert'))
            if picture is not None:
                on_screen = [(rigs[n].home + rigs[n].values['x'] - cx) * zoom + W / 2 for n in visible]
                composite(np, cv2, frame, picture, *insert_placement(t, index, zoom, sum(on_screen) / len(on_screen) if on_screen else None), FLAT)
            if sample_mask:
                drawn = np.abs(cv2.resize(frame, (108, 192), interpolation=cv2.INTER_AREA).astype(np.int16) - backdrop).max(axis=2) > 24
                foreground = drawn if foreground is None else foreground | drawn
            transition(np, cv2, frame, arrive, frame_no, 1 if index % 2 else -1)
            encoder.stdin.write(frame.tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise ValueError(f'clip {index} did not encode')
        written.append(str(out))
        if foreground is not None:
            cv2.imwrite(str(folder / f'clip-{index}-mask.png'), foreground.astype(np.uint8) * 255)
        done += shot['frames']
    return dict(clips=written, frames=done)


if __name__ == '__main__':
    print(json.dumps(run(json.loads(sys.argv[1]))))
