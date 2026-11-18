"""The stickman look of the animation studio: one main character, one recurring second character and any number of
extras, drawn in code so every episode shows exactly the same people.

The owner (15 Nov, with two long reference videos: "Zombie Outbreak" in a supermarket and "Every passenger on your
plane"): the old puppets moved and looked wrong. From now on only stickmen: a round white head with a neutral but
characterful face, thick black line limbs, a coloured top; small, simple movements that always fit what the narrator
says. What the references do, measured: a shot every 3.3-3.6 s, the character small in a wide painted place or big
in a close-up on a dark blurred ground, flat infographic cards, one word of caption at a time.

Pose angles are degrees from straight down; positive turns a limb towards where the character faces. "front" is the
limb nearer the facing direction. Everything is in units of the figure height F (feet to the top of the head).
The drawing functions need numpy and OpenCV (media runtime); the vocabulary and the pose maths are plain Python so the
studio core and the tests can check a script without them."""
import math
import random

# ------------------------------------------------------------------ vocabulary the writer may use

ACTIONS = ('idle', 'walk', 'run', 'sneak', 'talk', 'point', 'shrug', 'look_around', 'think', 'panic', 'celebrate', 'sit',
           'crouch', 'push', 'pull', 'carry', 'pick_up', 'throw', 'type', 'eat', 'drink', 'sleep', 'lie', 'wave', 'knock',
           'climb', 'fall', 'jump', 'nod', 'shake_head', 'shiver', 'cry', 'laugh', 'swing', 'read', 'phone', 'crank', 'lift',
           'facepalm', 'scream', 'stare', 'dance', 'shamble', 'hold',
           # from the figures/stix pose library (MIT, Cherif Yaya / Bassime Ledath), turned into this rig's joint angles
           'cheer', 'arms_up', 'reach', 'present', 'hands_hips', 'thumbs_up', 'pat', 'whisper', 'bow', 'kneel', 'slump', 'handshake',
           'write', 'telescope', 'arms_crossed')
EXPRESSIONS = ('neutral', 'happy', 'sad', 'scared', 'angry', 'surprised', 'worried', 'determined', 'tired', 'smug',
               'disgusted', 'crying', 'laughing', 'thinking', 'sleeping', 'confused', 'relieved')
PROPS = ('none', 'phone', 'flashlight', 'box', 'bag', 'key', 'paper', 'cup', 'can', 'bat', 'book', 'laptop', 'torch',
         'umbrella', 'money', 'wrench', 'bottle', 'food', 'map', 'crowbar', 'radio', 'clock', 'sign', 'rope', 'bucket',
         'hammer', 'extinguisher', 'hose', 'lantern', 'mirror', 'tape', 'cart')
EXTRAS = ('person', 'zombie', 'guard', 'worker', 'doctor', 'soldier', 'kid', 'elder', 'chef', 'alien', 'robot', 'shadow',
          'cat', 'dog', 'bird', 'mouse')
ANIMALS = ('cat', 'dog', 'bird', 'mouse')
HAIR = ('signature', 'none', 'tuft', 'spiky', 'bun', 'long', 'curly', 'cap', 'beanie', 'helmet', 'bald', 'ponytail', 'hood')
TOPS = ('hoodie', 'tshirt', 'jacket', 'vest', 'dress', 'coat', 'apron', 'uniform', 'sweater')
MARKS = ('bandaid', 'pencil', 'freckles', 'scar')
ACCESSORIES = ('none', 'glasses', 'scarf', 'badge', 'headphones', 'backpack', 'lanyard', 'mustache', 'bowtie')

# Words a local writer actually uses, mapped onto the vocabulary (the 9B model says "walks", "running away", "smiles").
ACTION_WORDS = {
    'cheers': 'cheer', 'cheer': 'cheer', 'hooray': 'cheer', 'raise': 'arms_up', 'surrender': 'arms_up', 'reach': 'reach', 'stretch': 'reach',
    'offer': 'present', 'present': 'present', 'show': 'present', 'hand': 'present', 'thumbs': 'thumbs_up', 'pat': 'pat', 'whisper': 'whisper',
    'bow': 'bow', 'kneel': 'kneel', 'slump': 'slump', 'sag': 'slump', 'handshake': 'handshake', 'shake': 'handshake', 'write': 'write',
    'sign': 'write', 'scribble': 'write', 'telescope': 'telescope', 'spyglass': 'telescope', 'fold': 'arms_crossed',
    'pump': 'crank', 'pumps': 'crank', 'pumping': 'crank', 'tie': 'crank', 'ties': 'crank', 'tying': 'crank', 'squeeze': 'crank', 'squeezes': 'crank',
    'stand': 'idle', 'standing': 'idle', 'wait': 'idle', 'waiting': 'idle', 'listen': 'idle', 'watch': 'stare', 'look': 'stare',
    'walking': 'walk', 'walks': 'walk', 'step': 'walk', 'enter': 'walk', 'leave': 'walk', 'approach': 'walk', 'pace': 'walk',
    'running': 'run', 'runs': 'run', 'flee': 'run', 'chase': 'run', 'sprint': 'run', 'rush': 'run', 'escape': 'run',
    'tiptoe': 'sneak', 'creep': 'sneak', 'speak': 'talk', 'say': 'talk', 'explain': 'talk', 'argue': 'talk', 'shout': 'scream',
    'yell': 'scream', 'search': 'look_around', 'scan': 'look_around', 'check': 'look_around', 'wonder': 'think', 'plan': 'think',
    'freak': 'panic', 'win': 'celebrate', 'seat': 'sit', 'sitting': 'sit', 'hide': 'crouch',
    'duck': 'crouch', 'shove': 'push', 'drag': 'pull', 'grab': 'pick_up', 'take': 'pick_up', 'collect': 'pick_up', 'toss': 'throw',
    'typing': 'type', 'computer': 'type', 'eating': 'eat', 'drinking': 'drink', 'sleeping': 'sleep', 'rest': 'sit', 'lay': 'lie',
    'lying': 'lie', 'greet': 'wave', 'bang': 'knock', 'hammer': 'knock', 'trip': 'fall', 'collapse': 'fall', 'faint': 'fall',
    'leap': 'jump', 'agree': 'nod', 'refuse': 'shake_head', 'cold': 'shiver', 'tremble': 'shiver', 'shake': 'shiver', 'sob': 'cry',
    'giggle': 'laugh', 'hit': 'swing', 'fight': 'swing', 'attack': 'swing', 'strike': 'swing', 'study': 'read', 'call': 'phone',
    'text': 'phone', 'turn': 'crank', 'wind': 'crank', 'raise': 'lift', 'stagger': 'shamble', 'lurch': 'shamble', 'zombie': 'shamble',
    'count': 'point', 'show': 'point', 'hold': 'hold', 'carrying': 'carry', 'move': 'walk', 'work': 'type', 'build': 'crank', 'fix': 'crank',
    # 16 Nov (owner): "figyeljen minden ilyesmire": every verb a narrator uses for a body movement gets its movement
    'scale': 'climb', 'ascend': 'climb', 'descend': 'climb', 'hang': 'climb', 'haul': 'pull', 'pry': 'pull', 'lever': 'pull', 'yank': 'pull',
    'crawl': 'sneak', 'squeeze': 'sneak', 'slip': 'sneak', 'kick': 'push', 'slam': 'push', 'barricade': 'push', 'brace': 'push', 'lean': 'push',
    'stack': 'carry', 'pile': 'carry', 'load': 'carry', 'drag': 'pull', 'swing': 'swing', 'smash': 'swing', 'break': 'swing', 'chop': 'swing',
    'tape': 'crank', 'tie': 'crank', 'screw': 'crank', 'unscrew': 'crank', 'dig': 'swing', 'wave': 'wave', 'signal': 'wave', 'hug': 'shiver',
    'shout': 'scream', 'whisper': 'talk', 'tell': 'talk', 'ask': 'talk', 'listen': 'idle', 'freeze': 'stare', 'wait': 'idle', 'stare': 'stare',
    'nap': 'sleep', 'doze': 'sleep', 'wake': 'sit', 'sink': 'sit', 'kneel': 'crouch', 'duck': 'crouch', 'dive': 'jump', 'vault': 'jump', 'hop': 'jump',
}
EXPRESSION_WORDS = {
    'calm': 'neutral', 'blank': 'neutral', 'serious': 'determined', 'focused': 'determined', 'smile': 'happy', 'smiling': 'happy',
    'glad': 'happy', 'joy': 'happy', 'excited': 'happy', 'proud': 'smug', 'upset': 'sad', 'unhappy': 'sad', 'afraid': 'scared',
    'terrified': 'scared', 'fear': 'scared', 'nervous': 'worried', 'anxious': 'worried', 'uneasy': 'worried', 'mad': 'angry',
    'furious': 'angry', 'shocked': 'surprised', 'amazed': 'surprised', 'exhausted': 'tired', 'sleepy': 'tired', 'gross': 'disgusted',
    'tears': 'crying', 'laugh': 'laughing', 'puzzled': 'confused', 'curious': 'thinking', 'asleep': 'sleeping', 'relief': 'relieved',
}
PROP_WORDS = {'flash': 'flashlight', 'lamp': 'flashlight', 'torchlight': 'flashlight', 'crate': 'box', 'package': 'box',
              'parcel': 'box', 'backpack': 'bag', 'sack': 'bag', 'keys': 'key', 'note': 'paper', 'letter': 'paper', 'list': 'paper',
              'ticket': 'paper', 'pass': 'paper', 'mug': 'cup', 'coffee': 'cup', 'tin': 'can', 'cans': 'can', 'stick': 'bat',
              'club': 'bat', 'notebook': 'book', 'computer': 'laptop', 'flame': 'torch', 'cash': 'money',
              'coin': 'money', 'tool': 'wrench', 'spanner': 'wrench', 'snack': 'food', 'sandwich': 'food',
              'apple': 'food', 'pizza': 'food', 'bread': 'food', 'walkie': 'radio', 'alarm': 'clock', 'cable': 'rope',
              'chain': 'rope', 'wire': 'rope', 'hanger': 'rope', 'laser': 'flashlight', 'pointer': 'flashlight', 'trolley': 'cart',
              'candle': 'lantern', 'duct': 'tape', 'mallet': 'hammer', 'axe': 'hammer', 'firehose': 'hose'}


def word_of(value, allowed, words, default):
    """The vocabulary word for whatever the writer wrote ("Walking slowly" -> walk)."""
    text = str(value or '').lower().replace('-', '_').strip()
    if text in allowed:
        return text
    for token in text.replace('_', ' ').replace(',', ' ').split():
        if token in allowed:
            return token
        if token in words:
            return words[token]
        for stem in (token[:-1] if token.endswith('s') else '', token[:-2] if token.endswith('es') else ''):
            if stem in allowed:
                return stem
            if stem in words:
                return words[stem]
        if token.endswith('ing') and token[:-3] in allowed:
            return token[:-3]
    return default


def action_of(value):
    return word_of(value, ACTIONS, ACTION_WORDS, 'idle')


def expression_of(value):
    return word_of(value, EXPRESSIONS, EXPRESSION_WORDS, 'neutral')


def prop_of(value):
    return word_of(value, PROPS, PROP_WORDS, 'none')


# ------------------------------------------------------------------ the two recurring characters

# 16 Nov (owner): "találj ki egy fő karakter kinézetet és védjegyeket, amik kicsit személyessé teszik, és legyen egy sapkája".
# Kip: a rust-red beanie with a cream fold, a pompom and a pencil tucked in the fold (he is the one who plans), three
# black strands poking out at the front, a plaster on the cheek (he has been through things), a mustard hoodie.
MAIN = dict(name='Kip', role='main', skin='#FFFFFF', hair='signature', hair_colour='#C9452E', hat_band='#F1E6CF', top='hoodie', top_colour='#E3A42B',
            second_colour='#B97A12', legs='#1E1E1E', accessory='none', marks=['pencil', 'bandaid'], height=1.0, eyes='dot',
            about='Kip, the ordinary guy who always finds a way: calm, slightly tired, one eyebrow ready to rise. Rust-red beanie with a pencil in the fold, plaster on the cheek, mustard hoodie.')
SUPPORT = dict(name='Mara', role='support', skin='#FFFFFF', hair='bun', hair_colour='#6B4A32', top='jacket', top_colour='#2F7F86',
               second_colour='#F2F2F2', legs='#1E1E1E', accessory='badge', height=.96, eyes='dot',
               about='A gyakorlatias társ, aki mindig tudja, mit kell tenni. Kontyos barna haj, türkiz dzseki, kitűző.')

HEX = __import__('re').compile(r'^#[0-9A-Fa-f]{6}$')


def clean_design(value, base):
    """A character design from the owner's settings page, every field checked against its own list."""
    d = dict(base)
    if not isinstance(value, dict):
        return d
    name = ' '.join(str(value.get('name') or '').split())[:20]
    if name:
        d['name'] = name
    for key, allowed in (('hair', HAIR), ('top', TOPS), ('accessory', ACCESSORIES)):
        if value.get(key) in allowed:
            d[key] = value[key]
    if isinstance(value.get('marks'), list):
        d['marks'] = [m for m in MARKS if m in value['marks']]
    for key in ('skin', 'hair_colour', 'top_colour', 'second_colour', 'legs', 'hat_band'):
        if isinstance(value.get(key), str) and HEX.match(value[key]):
            d[key] = value[key].upper()
    if value.get('eyes') in ('dot', 'round', 'sleepy'):
        d['eyes'] = value['eyes']
    try:
        d['height'] = min(1.1, max(.8, float(value.get('height', d['height']))))
    except (TypeError, ValueError):
        pass
    about = ' '.join(str(value.get('about') or '').split())[:300]
    if about:
        d['about'] = about
    return d


def extra_design(kind, seed):
    """An extra: a stranger, a zombie, a guard. Seeded, so the same crowd member keeps the same clothes in a shot."""
    r = random.Random(seed)
    muted = ['#7B8FA6', '#A26769', '#6D8B74', '#B7A57A', '#8E7DBE', '#C98B5B', '#5E7A8C', '#9C6B98', '#7C9A6A', '#B9806B']
    hair = r.choice(['none', 'bun', 'long', 'curly', 'ponytail', 'bald', 'spiky'])
    d = dict(name=kind, role='extra', skin='#FFFFFF', hair=hair, hair_colour=r.choice(['#2B2B2B', '#5A3E2B', '#8A6A44', '#B0B0B0']),
             top=r.choice(['tshirt', 'jacket', 'sweater', 'coat', 'dress']), top_colour=r.choice(muted), second_colour='#EDEDED',
             legs='#1E1E1E', accessory='none', height=r.uniform(.9, 1.02), eyes='dot', kind=kind)
    if kind == 'zombie':
        d.update(skin=r.choice(['#B8C4A4', '#A9B79B', '#C2C7B0']), eyes='zombie')
    elif kind == 'guard':
        d.update(hair='cap', hair_colour='#24324A', top='uniform', top_colour='#2F4466', accessory='badge')
    elif kind == 'worker':
        d.update(hair='helmet', hair_colour='#F2B233', top='vest', top_colour='#E8772E')
    elif kind == 'doctor':
        d.update(top='coat', top_colour='#F4F4F4', second_colour='#7DB4C9')
    elif kind == 'soldier':
        d.update(hair='helmet', hair_colour='#556B3A', top='uniform', top_colour='#64754A')
    elif kind == 'kid':
        d.update(height=r.uniform(.62, .72))
    elif kind == 'elder':
        d.update(hair_colour='#D6D6D6', hair=r.choice(['bald', 'curly', 'bun']), top='sweater')
    elif kind == 'chef':
        d.update(hair='beanie', hair_colour='#FFFFFF', top='apron', top_colour='#F4F4F4', second_colour='#D9D9D9')
    elif kind == 'alien':
        d.update(skin='#9EDC8C', hair='none', eyes='round', top='tshirt', top_colour='#5A5A8C')
    elif kind == 'robot':
        d.update(skin='#C9D1D9', hair='none', eyes='round', top='uniform', top_colour='#7D8B99')
    elif kind == 'shadow':
        d.update(skin='#2A2A2A', hair='none', top='coat', top_colour='#2A2A2A', eyes='glow')
    return d


# ------------------------------------------------------------------ poses

BASE = dict(lean=0., tilt=0., turn=0., bs=-7., be=6., fs=7., fe=-6., bh=-4., bk=0., fh=5., fk=0., lift=0., dx=0., spin=0.,
            hand=None)


def wave(t, freq, phase=0.):
    return math.sin((t * freq + phase) * math.tau)


# Joint positions from figures/src/figures.js (MIT; its pose library comes from stix, MIT). Hip at 0,0, y down, x towards
# where the figure faces; neck, head, back arm (la), front arm (ra), back leg (ll), front leg (rl) as [elbow/knee, hand/foot].
FIGURES = dict(
    cheer=dict(la=[[-22, -58], [-30, -76]], ra=[[22, -58], [30, -76]]),
    arms_up=dict(la=[[-10, -65], [-8, -80]], ra=[[10, -65], [8, -80]]),
    reach=dict(ra=[[30, -25], [45, -20]]),
    present=dict(la=[[20, -28], [38, -32]], ra=[[22, -24], [42, -28]]),
    hands_hips=dict(la=[[-24, -22], [-10, -6]], ra=[[24, -22], [10, -6]]),
    thumbs_up=dict(ra=[[22, -30], [24, -50]]),
    pat=dict(ra=[[24, -42], [44, -44]]),
    whisper=dict(neck=[7, -41], head=[11, -58], ra=[[16, -30], [16, -50]]),
    bow=dict(neck=[16, -38], head=[28, -50], la=[[6, -22], [10, -6]], ra=[[22, -22], [26, -6]]),
    kneel=dict(ll=[[-20, 22], [-38, 30]], rl=[[16, 30], [14, 53]]),
    slump=dict(neck=[6, -40], head=[12, -55], la=[[-12, -18], [-12, -2]], ra=[[18, -18], [18, -2]]),
    handshake=dict(ra=[[24, -26], [40, -24]]),
    write=dict(la=[[-10, -18], [8, -8]], ra=[[22, -22], [36, -14]], ll=[[-22, 2], [-24, 30]], rl=[[24, 2], [24, 30]], seated=True),
    telescope=dict(la=[[16, -34], [30, -46]], ra=[[18, -30], [30, -40]]),
    arms_crossed=dict(la=[[14, -26], [4, -24]], ra=[[12, -28], [6, -25]]),
)


def figures_pose(name):
    """A figures/stix pose as this rig's angles: each limb's direction from its joint (0 = down, 90 = forward)."""
    src = FIGURES[name]
    neck = src.get('neck', [0, -42])
    shoulder = (neck[0] * .9, neck[1] + 5)
    deg = lambda a, b: math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))
    out = dict(lean=math.degrees(math.atan2(neck[0], -neck[1])))
    if 'head' in src:
        out['tilt'] = math.degrees(math.atan2(src['head'][0] - neck[0], -(src['head'][1] - neck[1]))) - out['lean']
    for limb_, (s_, e_) in (('ra', ('fs', 'fe')), ('la', ('bs', 'be'))):
        if limb_ in src:
            elbow, hand = src[limb_]
            up = deg(shoulder, elbow)
            out[s_] = up
            out[e_] = deg(elbow, hand) - up
    for limb_, (h_, k_) in (('rl', ('fh', 'fk')), ('ll', ('bh', 'bk'))):
        if limb_ in src:
            knee, foot = src[limb_]
            up = deg((0, 0), knee)
            out[h_] = up
            out[k_] = deg(knee, foot) - up
    if src.get('seated'):
        # the source is drawn half from the front: seen from the side both thighs go forward
        out['seated'] = True
        out['bh'], out['bk'] = out.get('fh', 85.) - 6, out.get('fk', -85.) + 4
    return out


FIGURE_ANGLES = {}


def pose(action, t, length, seed=0):
    """The pose of an action at t seconds into a shot of the given length. Every action loops or settles, so a shot of
    any length works, and a tiny breath keeps even a still pose alive."""
    p = dict(BASE)
    breath = wave(t, .28, seed * .13)
    p['lean'] += breath * 1.2
    p['bs'] -= breath * 2
    p['fs'] += breath * 2
    u = min(1., t / max(.3, length))
    a = action
    if a in ('idle', 'stare', 'hold'):
        p['tilt'] = wave(t, .11, seed * .3) * 3
        if a == 'hold':
            p.update(fs=40., fe=55.)
    elif a in ('walk', 'shamble', 'sneak', 'carry'):
        f = {'walk': 0.95, 'shamble': .55, 'sneak': .6, 'carry': .85}[a]
        s = wave(t, f)
        c = wave(t, f, .25)
        amp = {'walk': 24, 'shamble': 14, 'sneak': 18, 'carry': 20}[a]
        p.update(fh=amp * s, bh=-amp * s, fk=-max(0., -c) * 38, bk=-max(0., c) * 38)
        p['lift'] = abs(c) * .012
        p.update(fs=-amp * .8 * s, bs=amp * .8 * s, fe=14., be=14.)
        if a == 'shamble':
            p.update(fs=88. + 4 * s, fe=-4., bs=82. - 4 * s, be=-2., tilt=10 + 3 * c, lean=6.)
        elif a == 'sneak':
            p.update(lean=18., fh=p['fh'] + 18, bh=p['bh'] + 18, fk=p['fk'] - 40, bk=p['bk'] - 40, fs=35., fe=60., bs=20., be=60.)
            p['lift'] = -.06
        elif a == 'carry':
            p.update(fs=55., fe=35., bs=50., be=40., lean=-3.)
    elif a == 'run':
        s = wave(t, 1.6)
        c = wave(t, 1.6, .25)
        p.update(lean=14., fh=42 * s + 8, bh=-42 * s + 8, fk=-max(0., -c) * 80 - 10, bk=-max(0., c) * 80 - 10,
                 fs=-55 * s, fe=85., bs=55 * s, be=85., lift=abs(c) * .04)
    elif a == 'talk':
        g = max(0., wave(t, .45, seed * .2))
        p.update(fs=25 + 35 * g, fe=60 + 30 * g, tilt=wave(t, .6) * 4, lean=2.)
    elif a == 'point':
        r = min(1., t / .35)
        p.update(fs=7 + 88 * r, fe=-6 + 6 * r, lean=4 * r, tilt=-3.)
    elif a == 'shrug':
        r = min(1., t / .4) if t < length - .5 else max(0., (length - t) / .5)
        p.update(fs=20 + 30 * r, fe=-20 - 80 * r, bs=-20 - 30 * r, be=20 + 80 * r, tilt=8 * r)
    elif a == 'look_around':
        p['turn'] = math.copysign(min(1., abs(wave(t, .35)) * 1.6), wave(t, .35))
        p['tilt'] = wave(t, .35) * 5
    elif a == 'think':
        p.update(fs=40., fe=150., tilt=10., turn=.3, bs=30., be=70.)
    elif a == 'panic':
        s = wave(t, 2.2)
        p.update(fs=150 + 20 * s, fe=20 * s, bs=-150 + 20 * s, be=-20 * s, lift=max(0., wave(t, 2.2, .1)) * .03,
                 tilt=s * 6, spin=s * 1.5)
    elif a == 'celebrate':
        j = max(0., wave(t, 1.1))
        p.update(fs=155., fe=15., bs=-155., be=-15., lift=j * .08, fk=-30 * j, bk=-30 * j)
    elif a in ('sit', 'type', 'eat', 'drink', 'read'):
        p.update(fh=88., fk=-88., bh=84., bk=-84., seated=True)
        if a == 'type':
            p.update(fs=50., fe=40 + 6 * wave(t, 3.), bs=46., be=44 + 6 * wave(t, 3., .5), tilt=-6.)
        elif a in ('eat', 'drink'):
            up = max(0., wave(t, .4))
            p.update(fs=30 + 20 * up, fe=60 + 75 * up, tilt=-3 * up)
        elif a == 'read':
            p.update(fs=40., fe=70., bs=36., be=74., tilt=-12.)
    elif a == 'crouch':
        p.update(fh=70., fk=-125., bh=55., bk=-115., lean=22., fs=40., fe=50., bs=30., be=55., tilt=-4.)
        p['turn'] = wave(t, .3) * .6
    elif a == 'push':
        j = wave(t, 1.8) * 2
        p.update(lean=26., fs=88. + j, fe=-4., bs=82. + j, be=-2., fh=20., fk=-25., bh=-32., bk=-8.)
    elif a == 'pull':
        j = wave(t, 1.6) * 3
        p.update(lean=-20. + j, fs=75., fe=10., bs=70., be=15., fh=26., fk=-12., bh=-18., bk=-10.)
    elif a == 'pick_up':
        r = math.sin(min(1., t / max(.8, length * .6)) * math.pi)
        p.update(lean=55 * r, fh=25 * r, fk=-50 * r, bh=15 * r, bk=-45 * r, fs=7 + 50 * r, fe=-6 + 10 * r, tilt=-10 * r)
    elif a == 'throw':
        k = t / max(.6, length)
        if k < .4:
            r = k / .4
            p.update(fs=7 - 140 * r, fe=40 * r, lean=-8 * r)
        else:
            r = min(1., (k - .4) / .15)
            p.update(fs=-133 + 230 * r, fe=40 - 40 * r, lean=-8 + 22 * r, fh=15 * r, bh=-15 * r)
    elif a in ('sleep', 'lie', 'fall'):
        r = 1. if a != 'fall' else min(1., t / .5) ** 2
        p.update(spin=-86 * r, fs=10., fe=-10., bs=-10., be=10.)
        p['lift'] = 0.
    elif a == 'wave':
        p.update(fs=150., fe=25 * wave(t, 1.6), tilt=5.)
    elif a == 'knock':
        k = max(0., wave(t, 2.))
        p.update(fs=70., fe=60 + 40 * k, lean=4.)
    elif a == 'climb':
        # hand over hand up a ladder (owner, 16 Nov: "amikor azt mondja létrát mászik, valójában nem azt teszi"):
        # one arm reaches high for the next rung while the other pulls, the opposite knee steps up; the renderer
        # draws the ladder and lifts the body over the shot
        s = wave(t, .9)
        # the arms open to both sides of the big head, as if holding the two rails, one hand higher than the other
        reach = 22 * s
        p.update(lean=4., tilt=-6., fs=138. + reach, fe=-28. + 18 * max(0., -s), bs=-138. + reach, be=28. - 18 * max(0., s),
                 fh=62. * max(0., -s) + 8, fk=-95. * max(0., -s), bh=62. * max(0., s) + 8, bk=-95. * max(0., s), lift=0.)
    elif a == 'jump':
        j = max(0., wave(t, .8))
        p.update(lift=j * .14, fs=120 * j, bs=-120 * j, fk=-40 * j, bk=-40 * j, fh=20 * j, bh=20 * j)
    elif a == 'nod':
        p['tilt'] = -8 * max(0., wave(t, 1.2))
    elif a == 'shake_head':
        p['turn'] = wave(t, 1.6) * .8
    elif a == 'shiver':
        j = wave(t, 7.)
        p.update(fs=-20 + j * 2, fe=130., bs=20 + j * 2, be=-130., tilt=j * 1.5, spin=j * .8)
    elif a == 'cry':
        j = wave(t, 3.)
        p.update(fs=60., fe=130., bs=-60., be=-130., tilt=12 + j * 2, lean=8.)
    elif a == 'laugh':
        j = wave(t, 3.)
        p.update(lean=-10 + j * 3, fs=35., fe=95., bs=-35., be=-95., tilt=-10 + j * 3, lift=max(0., j) * .01)
    elif a == 'swing':
        k = (t * .9) % 1.
        r = math.sin(k * math.pi)
        p.update(fs=-60 + 170 * r, fe=20., bs=40 * r, be=60., lean=10 * r, fh=15., bh=-20.)
    elif a == 'phone':
        p.update(fs=40., fe=140., tilt=6., turn=.2)
    elif a == 'crank':
        p.update(fs=70 + 18 * wave(t, .9), fe=30 + 30 * wave(t, .9, .25), lean=10., bs=10., fh=12., bh=-14.)
    elif a == 'lift':
        r = min(1., t / .8)
        p.update(fs=40 + 130 * r, fe=30 - 20 * r, bs=-40 - 130 * r, be=-30 + 20 * r, lean=-4 * r)
    elif a == 'facepalm':
        p.update(fs=35., fe=150., tilt=14., lean=6.)
    elif a in FIGURES:
        if a not in FIGURE_ANGLES:
            FIGURE_ANGLES[a] = figures_pose(a)
        settle = min(1., t / .35)          # the figures engine springs into a pose in about 0.4 s
        for k, v in FIGURE_ANGLES[a].items():
            p[k] = v if k == 'seated' else p.get(k, 0.) + (v - p.get(k, 0.)) * (1 - (1 - settle) ** 3)
        if a in ('cheer', 'arms_up'):
            # the big head hides arms that only go straight up: they open out to both sides of it
            e = 1 - (1 - settle) ** 3
            p.update(fs=110 * e + p['fs'] * (1 - e), fe=55 * e, bs=-110 * e + p['bs'] * (1 - e), be=-55 * e)
            if a == 'cheer':
                p['fs'] += wave(t, 2.2) * 8
                p['bs'] -= wave(t, 2.2) * 8
            p['lift'] = abs(wave(t, 1.6)) * .02 if a == 'cheer' else 0.
        elif a == 'bow':
            p.update(lean=18 * (1 - (1 - settle) ** 3), tilt=6., fs=12., fe=-6., bs=-8., be=8.)
        elif a == 'kneel':
            # one knee on the floor, the other foot flat in front (the source pose reads as a lunge from the side)
            p.update(fh=80., fk=-80., bh=-8., bk=-82., lean=4.)
        elif a == 'whisper':
            p['tilt'] += wave(t, .8) * 2
    elif a == 'scream':
        j = wave(t, 6.)
        p.update(fs=40., fe=150., bs=-40., be=-150., lean=-6., tilt=j * 2)
    elif a == 'dance':
        s = wave(t, 1.)
        p.update(fs=90 + 60 * s, fe=40., bs=-90 + 60 * s, be=-40., lean=8 * s, lift=max(0., wave(t, 2.)) * .03, fh=15 * s, bh=-15 * s)
    return p


def blinking(t, seed):
    """Eyes close for 0.12 s every 2.5-4.5 s."""
    r = random.Random(seed)
    at = r.uniform(.4, 2.)
    while at < t + .2:
        if at <= t < at + .12:
            return True
        at += r.uniform(2.5, 4.5)
    return False


# ------------------------------------------------------------------ drawing (OpenCV)

INK = (30, 30, 30)


def bgr(hex_colour):
    h = hex_colour.lstrip('#')
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def shade(colour, k):
    return tuple(max(0, min(255, int(c * k))) for c in colour)


class Canvas:
    """Integer-safe anti-aliased drawing on a BGR frame (sub-pixel coordinates through cv2's shift)."""
    SHIFT = 3

    def __init__(self, cv2, frame):
        self.cv2, self.frame = cv2, frame
        self.k = 1 << self.SHIFT

    def p(self, pt):
        return (int(round(pt[0] * self.k)), int(round(pt[1] * self.k)))

    def line(self, a, b, colour, width):
        self.cv2.line(self.frame, self.p(a), self.p(b), colour, max(1, int(round(width))), self.cv2.LINE_AA, self.SHIFT)

    def circle(self, c, r, colour, width=-1):
        self.cv2.circle(self.frame, self.p(c), max(1, int(round(r * self.k))), colour, -1 if width < 0 else max(1, int(round(width))), self.cv2.LINE_AA, self.SHIFT)

    def ellipse(self, c, axes, angle, colour, width=-1, start=0, end=360):
        self.cv2.ellipse(self.frame, self.p(c), (max(1, int(round(axes[0] * self.k))), max(1, int(round(axes[1] * self.k)))), angle, start, end,
                         colour, -1 if width < 0 else max(1, int(round(width))), self.cv2.LINE_AA, self.SHIFT)

    def poly(self, pts, colour, outline=None, width=2):
        import numpy as np
        arr = np.array([self.p(q) for q in pts], dtype=np.int32)
        self.cv2.fillPoly(self.frame, [arr], colour, self.cv2.LINE_AA, self.SHIFT)
        if outline is not None:
            self.cv2.polylines(self.frame, [arr], True, outline, max(1, int(round(width))), self.cv2.LINE_AA, self.SHIFT)

    def polyline(self, pts, colour, width, closed=False):
        import numpy as np
        arr = np.array([self.p(q) for q in pts], dtype=np.int32)
        self.cv2.polylines(self.frame, [arr], closed, colour, max(1, int(round(width))), self.cv2.LINE_AA, self.SHIFT)


def limb(origin, angle, length, facing, size):
    rad = math.radians(angle)
    return (origin[0] + math.sin(rad) * length * size * facing, origin[1] + math.cos(rad) * length * size)


def rotate_about(pt, centre, degrees):
    r = math.radians(degrees)
    x, y = pt[0] - centre[0], pt[1] - centre[1]
    return (centre[0] + x * math.cos(r) - y * math.sin(r), centre[1] + x * math.sin(r) + y * math.cos(r))


HEAD_R, TORSO, SHOULDER, UPPER, FORE, THIGH, SHIN = .135, .27, .03, .16, .15, .19, .19


def skeleton(p, foot_x, ground, size, facing):
    """Joint positions for a pose: the standing leg keeps the feet on the ground, a jump lifts the whole body."""
    def reach(h, k):
        return THIGH * math.cos(math.radians(h)) + SHIN * math.cos(math.radians(h + k))
    seated = p.get('seated')
    hip_height = (SHIN + .02) if seated else max(reach(p['fh'], p['fk']), reach(p['bh'], p['bk']))
    hip = (foot_x, ground - (hip_height + p['lift'] + .015) * size)
    up = math.radians(p['lean'])
    neck = (hip[0] + math.sin(up) * TORSO * size * facing, hip[1] - math.cos(up) * TORSO * size)
    shoulder = (neck[0] - math.sin(up) * SHOULDER * size * facing, neck[1] + math.cos(up) * SHOULDER * size)
    j = dict(hip=hip, neck=neck, shoulder=shoulder)
    for side, s, e in (('f', 'fs', 'fe'), ('b', 'bs', 'be')):
        elbow = limb(shoulder, p[s], UPPER, facing, size)
        j[side + 'elbow'], j[side + 'hand'] = elbow, limb(elbow, p[s] + p[e], FORE, facing, size)
    for side, h, k in (('f', 'fh', 'fk'), ('b', 'bh', 'bk')):
        knee = limb(hip, p[h], THIGH, facing, size)
        j[side + 'knee'], j[side + 'foot'] = knee, limb(knee, p[h] + p[k], SHIN, facing, size)
    head_angle = p['lean'] + p['tilt']
    hr = math.radians(head_angle)
    j['head'] = (neck[0] + math.sin(hr) * (HEAD_R * .92) * size * facing, neck[1] - math.cos(hr) * (HEAD_R * .92) * size)
    j['head_angle'] = head_angle * facing
    if p['spin']:
        pivot = hip if abs(p['spin']) < 20 else (foot_x, ground - .03 * size)
        for key, value in list(j.items()):
            if isinstance(value, tuple):
                j[key] = rotate_about(value, pivot, p['spin'] * facing)
        j['head_angle'] += p['spin'] * facing
        if abs(p['spin']) > 45:
            # lying down: the body rests on the floor, not on the pivot point
            low = max(v[1] for v in j.values() if isinstance(v, tuple))
            shift = ground - low - .01 * size
            for key, value in list(j.items()):
                if isinstance(value, tuple):
                    j[key] = (value[0], value[1] + shift)
    return j


def draw_face(cv, centre, r, angle, facing, d, expression, p, t, seed, talking):
    """Eyes, brows and mouth of one of the 17 expressions, turned a little towards where the character looks."""
    look = facing * (.32 + .3 * p['turn'])
    def at(dx, dy):
        return rotate_about((centre[0] + dx * r, centre[1] + dy * r), centre, angle)
    e = expression
    eye_y = -.02
    spread = .3
    eyes = d.get('eyes', 'dot')
    closed = blinking(t, seed) and e not in ('sleeping', 'laughing')
    lw = max(1.5, r * .085)
    for side in (-1, 1):
        c = at(look + side * spread, eye_y)
        if e == 'sleeping' or closed:
            cv.line(at(look + side * spread - .11, eye_y), at(look + side * spread + .11, eye_y), INK, lw)
        elif e in ('laughing', 'happy') and e == 'laughing':
            cv.ellipse(c, (r * .12, r * .1), angle, INK, lw, 180, 360)
        elif e == 'surprised' or eyes == 'round':
            cv.circle(c, r * .15, (255, 255, 255))
            cv.circle(c, r * .15, INK, lw * .8)
            cv.circle((c[0] + facing * r * .03, c[1]), r * .07, INK)
        elif eyes == 'zombie':
            cv.circle(c, r * .13, (70, 80, 70))
            cv.circle(c, r * .05, (225, 230, 225))
        elif eyes == 'glow':
            cv.circle(c, r * .1, (80, 240, 250))
        else:
            ry = r * (.085 if e != 'tired' and eyes != 'sleepy' else .05)
            cv.ellipse(c, (r * .075, ry * 1.2), angle, INK)
            if e in ('tired', 'smug') or eyes == 'sleepy':
                cv.line(at(look + side * spread - .12, eye_y - .07), at(look + side * spread + .12, eye_y - .07), INK, lw)
    # brows: inner end height, outer end height (negative is up)
    brows = dict(neutral=(-.27, -.27), happy=(-.31, -.3), sad=(-.34, -.24), scared=(-.38, -.27), angry=(-.18, -.32),
                 surprised=(-.42, -.4), worried=(-.33, -.25), determined=(-.22, -.29), tired=(-.24, -.24), smug=(-.24, -.33),
                 disgusted=(-.2, -.27), crying=(-.36, -.24), laughing=(-.33, -.3), thinking=(-.27, -.36), sleeping=(-.25, -.25),
                 confused=(-.36, -.22), relieved=(-.3, -.27)).get(e, (-.27, -.27))
    if eyes not in ('zombie', 'glow'):
        for side in (-1, 1):
            inner, outer = brows
            if e in ('thinking', 'confused', 'smug') and side == 1:
                inner, outer = inner - .07, outer - .06
            x0 = look + side * spread
            cv.line(at(x0 - side * .08, inner), at(x0 + side * .14, outer), INK, lw * 1.05)
    m = at(look * .9, .36)
    mw = r * .2
    if talking and e not in ('sleeping',):
        cv.ellipse(m, (mw * .55, r * (.06 + .09 * talking)), angle, (60, 40, 50))
        cv.ellipse(m, (mw * .55, r * (.06 + .09 * talking)), angle, INK, lw * .8)
    elif e in ('happy', 'relieved'):
        cv.ellipse(at(look * .9, .26), (mw * .9, r * .14), angle, INK, lw, 20, 160)
    elif e == 'laughing':
        cv.ellipse(at(look * .9, .3), (mw, r * .16), angle, (60, 40, 50), -1, 0, 180)
        cv.ellipse(at(look * .9, .3), (mw, r * .16), angle, INK, lw, 0, 180)
        cv.line(at(look * .9 - .2, .3), at(look * .9 + .2, .3), INK, lw)
    elif e in ('sad', 'crying', 'disgusted'):
        cv.ellipse(at(look * .9, .45), (mw * .8, r * .1), angle, INK, lw, 200, 340)
    elif e in ('surprised', 'scared') or eyes == 'zombie':
        cv.ellipse(m, (mw * .45, r * (.12 if e == 'surprised' or eyes == 'zombie' else .08)), angle, (60, 40, 50))
        cv.ellipse(m, (mw * .45, r * (.12 if e == 'surprised' or eyes == 'zombie' else .08)), angle, INK, lw * .8)
    elif e == 'angry':
        cv.ellipse(at(look * .9, .44), (mw * .7, r * .08), angle, INK, lw, 200, 340)
    elif e == 'smug':
        cv.ellipse(at(look * .9 + .05, .3), (mw * .7, r * .09), angle, INK, lw, 10, 120)
    elif e in ('worried', 'confused'):
        pts = [at(look * .9 + dx, .37 + .03 * math.sin(dx * 30)) for dx in (-.14, -.07, 0, .07, .14)]
        cv.polyline(pts, INK, lw)
    elif e == 'sleeping':
        cv.line(at(look * .9 - .06, .37), at(look * .9 + .06, .37), INK, lw)
    elif eyes == 'glow':
        pass
    else:
        cv.line(at(look * .9 - .1, .36), at(look * .9 + .1, .36), INK, lw)
    if e in ('scared', 'worried') and eyes != 'zombie':
        drop = at(-facing * .75, -.25)
        cv.ellipse(drop, (r * .07, r * .11), angle, (230, 200, 120))
    if e == 'crying':
        for side in (-1, 1):
            c = at(look + side * spread, .12 + (t * .9 % .5))
            cv.ellipse(c, (r * .045, r * .08), angle, (235, 190, 120))


def draw_hair(cv, centre, r, angle, facing, d, behind):
    hair, colour = d.get('hair', 'none'), bgr(d.get('hair_colour', '#1E1E1E'))
    def at(dx, dy):
        return rotate_about((centre[0] + dx * r, centre[1] + dy * r), centre, angle)
    lw = max(2., r * .1)
    if behind:
        if hair == 'long':
            cv.poly([at(-1.05, -.2), at(1.05, -.2), at(1.12, 1.15), at(-1.12, 1.15)], colour, INK, lw * .8)
        elif hair == 'ponytail':
            cv.ellipse(at(-facing * 1.05, .15), (r * .32, r * .6), angle - facing * 25, colour)
            cv.ellipse(at(-facing * 1.05, .15), (r * .32, r * .6), angle - facing * 25, INK, lw * .8)
        elif hair == 'bun':
            cv.circle(at(0, -1.18), r * .42, colour)
            cv.circle(at(0, -1.18), r * .42, INK, lw * .8)
        elif hair == 'hood':
            cv.circle(at(0, .05), r * 1.22, colour)
            cv.circle(at(0, .05), r * 1.22, INK, lw * .8)
        return
    if hair == 'tuft':
        for dx, bend in ((-.18, -.45), (0., .1), (.2, .5)):
            base = at(dx, -.95)
            mid = at(dx + bend * .25, -1.25)
            tip = at(dx + bend * .45, -1.38)
            cv.polyline([base, mid, tip], colour, lw * 1.05)
    elif hair == 'spiky':
        pts = []
        for k in range(7):
            a = math.radians(-160 + k * 23.3)
            pts.append(at(math.cos(a) * 1.02, math.sin(a) * 1.02))
            b = math.radians(-160 + k * 23.3 + 11.6)
            pts.append(at(math.cos(b) * 1.4, math.sin(b) * 1.4))
        pts.append(at(math.cos(math.radians(3)) * 1.02, math.sin(math.radians(3)) * 1.02))
        cv.poly(pts + [at(.6, -.2), at(-.6, -.2)], colour, INK, lw * .7)
    elif hair in ('bun', 'long', 'ponytail', 'curly', 'beanie', 'cap', 'helmet', 'signature'):
        if hair == 'curly':
            for k in range(9):
                a = math.radians(-175 + k * 21)
                cv.circle(at(math.cos(a) * .98, math.sin(a) * .98), r * .3, colour)
            cv.ellipse(centre, (r * 1.0, r * 1.0), angle, colour, -1, 185, 355)
        elif hair == 'signature':
            # three strands at the temple under the beanie, the beanie, its cream fold, the pompom, the pencil; the fold
            # sits above the brows so the face keeps all its expressions
            for dx in (.5, .64, .78):
                cv.polyline([at(facing * dx, -.5), at(facing * (dx + .1), -.36), at(facing * (dx + .04), -.27)], INK, lw * .9)
            cv.ellipse(at(0, -.5), (r * 1.02, r * .95), angle, colour, -1, 180, 360)
            cv.ellipse(at(0, -.5), (r * 1.02, r * .95), angle, INK, lw * .8, 180, 360)
            for k in (-.55, -.2, .15, .5):
                cv.line(at(k, -1.15 + abs(k) * .4), at(k, -.7), shade(colour, .8), lw * .5)
            band = bgr(d.get('hat_band', '#F1E6CF'))
            cv.poly([at(-1.06, -.68), at(1.06, -.68), at(1.0, -.42), at(-1.0, -.42)], band, INK, lw * .8)
            cv.circle(at(-facing * .25, -1.5), r * .2, band)
            cv.circle(at(-facing * .25, -1.5), r * .2, INK, lw * .7)
            if 'pencil' in (d.get('marks') or []):
                a0, a1 = at(-facing * .55, -.56), at(-facing * 1.45, -.9)
                cv.line(a0, a1, (60, 190, 240), lw * 1.5)
                cv.line(a1, at(-facing * 1.6, -.96), INK, lw * 1.1)
                cv.line(a0, at(-facing * .45, -.52), (170, 170, 230), lw * 1.5)
        elif hair == 'beanie':
            cv.ellipse(at(0, -.25), (r * 1.06, r * 1.0), angle, colour, -1, 180, 360)
            cv.ellipse(at(0, -.25), (r * 1.06, r * 1.0), angle, INK, lw * .8, 180, 360)
            cv.poly([at(-1.1, -.38), at(1.1, -.38), at(1.1, -.12), at(-1.1, -.12)], shade(colour, .85), INK, lw * .8)
        elif hair == 'cap':
            cv.ellipse(at(0, -.3), (r * 1.03, r * .85), angle, colour, -1, 180, 360)
            cv.ellipse(at(0, -.3), (r * 1.03, r * .85), angle, INK, lw * .8, 180, 360)
            cv.poly([at(facing * .2, -.36), at(facing * 1.55, -.3), at(facing * 1.5, -.18), at(facing * .2, -.24)], colour, INK, lw * .8)
        elif hair == 'helmet':
            cv.ellipse(at(0, -.18), (r * 1.12, r * 1.05), angle, colour, -1, 180, 360)
            cv.ellipse(at(0, -.18), (r * 1.12, r * 1.05), angle, INK, lw * .8, 180, 360)
            cv.line(at(-1.2, -.18), at(1.2, -.18), INK, lw)
        else:
            # a hair cap over the top third of the head, with a fringe that dips towards where the character faces
            arc = [at(math.cos(math.radians(a)) * 1.04, math.sin(math.radians(a)) * 1.04) for a in range(192, 349, 6)]
            fringe = [at(.92, -.36), at(.45 * facing, -.5), at(-.1 * facing, -.42), at(-.6 * facing, -.5), at(-.92, -.36)]
            if facing < 0:
                fringe = [at(.92, -.36), at(.6, -.5), at(.1, -.42), at(-.45, -.5), at(-.92, -.36)]
            cv.poly(arc + fringe, colour)
            cv.polyline(arc, INK, lw * .8)


def draw_torso(cv, j, size, facing, d):
    colour, second = bgr(d.get('top_colour', '#E3A42B')), bgr(d.get('second_colour', '#FFFFFF'))
    top = d.get('top', 'tshirt')
    hip, neck = j['hip'], j['neck']
    ax, ay = neck[0] - hip[0], neck[1] - hip[1]
    length = math.hypot(ax, ay) or 1.
    nx, ny = -ay / length, ax / length
    def at(along, across):
        return (hip[0] + ax * along + nx * across * size, hip[1] + ay * along + ny * across * size)
    w_top, w_bot = .088, .098
    bottom = -.08 if top in ('tshirt', 'vest', 'uniform', 'jacket', 'sweater', 'hoodie') else -.35 if top in ('dress', 'coat') else -.12
    flare = .13 if top == 'dress' else .095 if top == 'coat' else w_bot
    outline = max(2., size * .012)
    shape = [at(.98, -w_top), at(.98, w_top), at(bottom, flare), at(bottom, -flare)]
    if top == 'hoodie':
        cv.ellipse(at(1.02, 0), (size * .085, size * .045), 0, shade(colour, .82))
        cv.ellipse(at(1.02, 0), (size * .085, size * .045), 0, INK, outline)
    cv.poly(shape, colour, INK, outline)
    lw = max(1.5, size * .008)
    if top in ('jacket', 'coat', 'vest', 'uniform'):
        cv.line(at(.95, 0), at(bottom + .02, 0), shade(colour, .6) if top != 'jacket' else INK, lw)
    if top == 'jacket':
        cv.poly([at(.97, -.025), at(.97, .025), at(.6, 0)], second)
    if top == 'hoodie':
        cv.poly([at(.25, -.045), at(.25, .045), at(.05, .055), at(.05, -.055)], shade(colour, .85), INK, lw)
        cv.line(at(.95, -.02), at(.72, -.025), INK, lw)
        cv.line(at(.95, .02), at(.72, .025), INK, lw)
    if top == 'apron':
        cv.poly([at(.75, -.05), at(.75, .05), at(-.1, .065), at(-.1, -.065)], second, INK, lw)
    if top == 'uniform':
        for k in (.75, .5, .25):
            cv.circle(at(k, 0), size * .006, (210, 200, 120))
    if top == 'sweater':
        for k in (.1, .9):
            cv.line(at(k, -w_bot), at(k, w_bot), shade(colour, .78), lw)
    acc = d.get('accessory', 'none')
    if acc in ('badge', 'lanyard'):
        if acc == 'lanyard':
            cv.line(at(.97, -.03), at(.62, 0), (200, 120, 40), lw)
            cv.line(at(.97, .03), at(.62, 0), (200, 120, 40), lw)
        b = at(.55 if acc == 'lanyard' else .72, .035 * facing)
        cv.poly([(b[0] - size * .02, b[1] - size * .014), (b[0] + size * .02, b[1] - size * .014),
                 (b[0] + size * .02, b[1] + size * .014), (b[0] - size * .02, b[1] + size * .014)], (245, 245, 245), INK, lw * .7)
    if acc == 'scarf':
        cv.poly([at(1.0, -.08), at(1.0, .08), at(.88, .08), at(.88, -.08)], second, INK, lw)
        cv.poly([at(.9, .02 * facing), at(.9, .06 * facing), at(.6, .07 * facing), at(.6, .03 * facing)], second, INK, lw)
    if acc == 'bowtie':
        c = at(.95, 0)
        cv.poly([c, (c[0] - size * .03, c[1] - size * .015), (c[0] - size * .03, c[1] + size * .015)], (60, 60, 200))
        cv.poly([c, (c[0] + size * .03, c[1] - size * .015), (c[0] + size * .03, c[1] + size * .015)], (60, 60, 200))


def draw_figure(cv, d, p, foot_x, ground, size, facing, expression='neutral', t=0., seed=0, talking=0., prop='none', shadow=True, tool=None):
    """One character: shadow, back limbs, torso, front limbs, head with hair and face, and a held prop."""
    j = skeleton(p, foot_x, ground, size, facing)
    lw = max(2.5, size * .02)
    legs = bgr(d.get('legs', '#1E1E1E'))
    if shadow and abs(p.get('spin', 0)) < 45:
        soft_shadow(cv, (foot_x, ground + size * .006), size * .15 * (1 - min(.5, p['lift'] * 3)), size * .022)
    if p.get('seated') and not p.get('on_furniture'):
        seat = (j['hip'][0] - facing * size * .03, j['hip'][1] + size * .03)
        cv.poly([(seat[0] - size * .12, seat[1]), (seat[0] + size * .12, seat[1]), (seat[0] + size * .12, ground), (seat[0] - size * .12, ground)],
                (64, 84, 110), INK, max(2., size * .01))
    if d.get('accessory') == 'backpack':
        c = j['hip'][0] * .45 + j['neck'][0] * .55 - facing * size * .09, j['hip'][1] * .45 + j['neck'][1] * .55
        cv.poly([(c[0] - size * .05, c[1] - size * .1), (c[0] + size * .05, c[1] - size * .1), (c[0] + size * .05, c[1] + size * .09),
                 (c[0] - size * .05, c[1] + size * .09)], shade(bgr(d.get('second_colour', '#888888')), .7), INK, max(2., size * .01))
    head_r = HEAD_R * size
    draw_hair(cv, j['head'], head_r, j['head_angle'], facing, d, behind=True)
    for side in ('b',):
        cv.line(j['hip'], j[side + 'knee'], legs, lw)
        cv.line(j[side + 'knee'], j[side + 'foot'], legs, lw)
        foot(cv, j, side, size, facing, legs, lw, p)
        cv.line(j['shoulder'], j[side + 'elbow'], INK, lw)
        cv.line(j[side + 'elbow'], j[side + 'hand'], INK, lw)
    cv.line(j['hip'], j['neck'], INK, lw)
    draw_torso(cv, j, size, facing, d)
    cv.line(j['hip'], j['fknee'], legs, lw)
    cv.line(j['fknee'], j['ffoot'], legs, lw)
    foot(cv, j, 'f', size, facing, legs, lw, p)
    if tool is not None:
        draw_tool(cv, tool, j, size, facing)
    elif prop != 'none':
        draw_prop(cv, prop, j, size, facing, t)
    cv.line(j['shoulder'], j['felbow'], INK, lw)
    cv.line(j['felbow'], j['fhand'], INK, lw)
    for side in ('f', 'b'):
        cv.circle(j[side + 'hand'], lw * .62, INK)
    cv.circle(j['head'], head_r, bgr(d.get('skin', '#FFFFFF')))
    cv.circle(j['head'], head_r, INK, max(2.5, size * .016))
    draw_hair(cv, j['head'], head_r, j['head_angle'], facing, d, behind=False)
    draw_face(cv, j['head'], head_r, j['head_angle'], facing, d, expression, p, t, seed, talking)
    marks = d.get('marks') or []
    if 'bandaid' in marks and expression != 'sleeping':
        c = rotate_about((j['head'][0] - facing * .48 * head_r, j['head'][1] + .2 * head_r), j['head'], j['head_angle'])
        cv.ellipse(c, (head_r * .2, head_r * .085), j['head_angle'] - facing * 20, (150, 200, 238))
        cv.ellipse(c, (head_r * .2, head_r * .085), j['head_angle'] - facing * 20, INK, max(1., head_r * .035))
        cv.line((c[0] - head_r * .03, c[1] - head_r * .04), (c[0] + head_r * .03, c[1] + head_r * .04), (110, 160, 210), max(1., head_r * .03))
    if 'freckles' in marks:
        for dx, dy in ((-.1, .14), (.02, .18), (.14, .14)):
            for side in (-1, 1):
                cv.circle(rotate_about((j['head'][0] + (facing * .3 + side * .32 + dx) * head_r, j['head'][1] + dy * head_r), j['head'], j['head_angle']), head_r * .025, (120, 150, 190))
    if 'scar' in marks:
        a = rotate_about((j['head'][0] + facing * .5 * head_r, j['head'][1] - .45 * head_r), j['head'], j['head_angle'])
        cv.line(a, (a[0] + facing * head_r * .12, a[1] + head_r * .2), INK, max(1., head_r * .04))
    acc = d.get('accessory')
    if acc == 'glasses':
        look = facing * .32
        for side in (-1, 1):
            c = rotate_about((j['head'][0] + (look + side * .3) * head_r, j['head'][1] - .02 * head_r), j['head'], j['head_angle'])
            cv.circle(c, head_r * .2, INK, max(1.5, head_r * .07))
    elif acc == 'headphones':
        cv.ellipse(j['head'], (head_r * 1.1, head_r * 1.1), j['head_angle'], INK, max(2., head_r * .12), 190, 350)
        for side in (-1, 1):
            c = rotate_about((j['head'][0] + side * head_r * 1.02, j['head'][1]), j['head'], j['head_angle'])
            cv.ellipse(c, (head_r * .16, head_r * .3), j['head_angle'], (60, 60, 200))
    elif acc == 'mustache':
        c = rotate_about((j['head'][0] + facing * .3 * head_r, j['head'][1] + .26 * head_r), j['head'], j['head_angle'])
        cv.ellipse(c, (head_r * .26, head_r * .09), j['head_angle'], bgr(d.get('hair_colour', '#1E1E1E')))
    if expression == 'sleeping':
        draw_zzz(cv, j['head'], head_r, t)
    return j


def soft_shadow(cv, centre, rx, ry, alpha=.28):
    """A see-through contact shadow: only the small box around it is blended."""
    import numpy as np
    h, w = cv.frame.shape[:2]
    x0, x1 = int(max(0, centre[0] - rx - 2)), int(min(w, centre[0] + rx + 3))
    y0, y1 = int(max(0, centre[1] - ry - 2)), int(min(h, centre[1] + ry + 3))
    if x1 <= x0 or y1 <= y0:
        return
    roi = cv.frame[y0:y1, x0:x1]
    mask = np.zeros(roi.shape[:2], np.uint8)
    cv.cv2.ellipse(mask, (int(centre[0] - x0), int(centre[1] - y0)), (max(1, int(rx)), max(1, int(ry))), 0, 0, 360, 255, -1, cv.cv2.LINE_AA)
    k = (mask.astype(np.float32) / 255. * alpha)[..., None]
    roi[:] = (roi * (1 - k)).astype(np.uint8)


def foot(cv, j, side, size, facing, colour, lw, p):
    f = j[side + 'foot']
    if abs(p.get('spin', 0)) > 45:
        return
    cv.line(f, (f[0] + facing * size * .045, f[1]), colour, lw * 1.15)


def draw_zzz(cv, centre, r, t):
    for k in range(3):
        u = (t * .5 + k / 3) % 1.
        pos = (centre[0] + r * (1.0 + u * 1.2), centre[1] - r * (1.0 + u * 1.6))
        s = r * (.18 + .12 * u)
        cv.polyline([(pos[0] - s, pos[1] - s), (pos[0] + s, pos[1] - s), (pos[0] - s, pos[1] + s), (pos[0] + s, pos[1] + s)], INK, max(1.5, r * .07))


def draw_prop(cv, prop, j, size, facing, t):
    """A small held object, drawn at the front hand (two-handed things between both hands)."""
    h = j['fhand']
    b = j['bhand']
    s = size
    lw = max(1.5, s * .009)
    if prop in ('box', 'bucket') and True:
        c = ((h[0] + b[0]) / 2, (h[1] + b[1]) / 2 - s * .02)
        w = s * .14
        if prop == 'box':
            cv.poly([(c[0] - w / 2, c[1] - w * .8), (c[0] + w / 2, c[1] - w * .8), (c[0] + w / 2, c[1] + w * .2), (c[0] - w / 2, c[1] + w * .2)],
                    (90, 150, 200), INK, lw)
            cv.line((c[0] - w / 2, c[1] - w * .45), (c[0] + w / 2, c[1] - w * .45), (70, 120, 170), lw)
        else:
            cv.poly([(c[0] - w * .45, c[1] - w * .6), (c[0] + w * .45, c[1] - w * .6), (c[0] + w * .35, c[1] + w * .2), (c[0] - w * .35, c[1] + w * .2)],
                    (150, 150, 150), INK, lw)
        return
    if prop == 'laptop':
        c = ((h[0] + b[0]) / 2, (h[1] + b[1]) / 2)
        cv.poly([(c[0] - s * .07, c[1]), (c[0] + s * .07, c[1]), (c[0] + s * .06, c[1] - s * .09), (c[0] - s * .06, c[1] - s * .09)], (80, 80, 80), INK, lw)
        cv.poly([(c[0] - s * .05, c[1] - s * .015), (c[0] + s * .05, c[1] - s * .015), (c[0] + s * .045, c[1] - s * .08), (c[0] - s * .045, c[1] - s * .08)], (200, 170, 110))
        return
    if prop in ('paper', 'map', 'book', 'sign'):
        c = (h[0] * .6 + b[0] * .4, h[1] * .6 + b[1] * .4 - s * .03)
        w, ht = (s * .09, s * .11) if prop != 'sign' else (s * .16, s * .1)
        colour = {'paper': (245, 245, 240), 'map': (170, 215, 225), 'book': (60, 60, 170), 'sign': (235, 240, 245)}[prop]
        cv.poly([(c[0] - w / 2, c[1] - ht / 2), (c[0] + w / 2, c[1] - ht / 2), (c[0] + w / 2, c[1] + ht / 2), (c[0] - w / 2, c[1] + ht / 2)], colour, INK, lw)
        if prop in ('paper', 'sign'):
            for k in range(3):
                y = c[1] - ht * .25 + k * ht * .22
                cv.line((c[0] - w * .35, y), (c[0] + w * .3, y), (150, 150, 150), lw * .8)
        return
    dx, dy = h[0] - j['felbow'][0], h[1] - j['felbow'][1]
    n = math.hypot(dx, dy) or 1.
    ux, uy = dx / n, dy / n
    if prop == 'phone':
        cv.poly([(h[0] - s * .018, h[1] - s * .04), (h[0] + s * .018, h[1] - s * .04), (h[0] + s * .018, h[1] + s * .02), (h[0] - s * .018, h[1] + s * .02)], (40, 40, 40), INK, lw)
        cv.poly([(h[0] - s * .012, h[1] - s * .033), (h[0] + s * .012, h[1] - s * .033), (h[0] + s * .012, h[1] + s * .01), (h[0] - s * .012, h[1] + s * .01)], (230, 200, 140))
    elif prop in ('flashlight', 'torch'):
        tip = (h[0] + ux * s * .07, h[1] + uy * s * .07)
        if prop == 'flashlight':
            cv.line(h, tip, (60, 60, 60), lw * 3)
            beam = [tip, (tip[0] + (ux * .6 - uy * .18) * s, tip[1] + (uy * .6 + ux * .18) * s), (tip[0] + (ux * .6 + uy * .18) * s, tip[1] + (uy * .6 - ux * .18) * s)]
            overlay_poly(cv, beam, (170, 235, 250), .28)
        else:
            cv.line(h, (h[0], h[1] - s * .09), (40, 70, 110), lw * 2.4)
            flick = 1 + .15 * math.sin(t * 17)
            cv.ellipse((h[0], h[1] - s * .12), (s * .025 * flick, s * .045 * flick), 0, (40, 140, 250))
            cv.ellipse((h[0], h[1] - s * .115), (s * .012, s * .025), 0, (120, 230, 255))
    elif prop in ('bat', 'crowbar', 'umbrella', 'wrench'):
        tip = (h[0] + ux * s * .3, h[1] + uy * s * .3)
        colour = {'bat': (60, 120, 170), 'crowbar': (70, 70, 200), 'umbrella': (40, 40, 40), 'wrench': (150, 150, 150)}[prop]
        cv.line((h[0] - ux * s * .03, h[1] - uy * s * .03), tip, colour, lw * (3 if prop == 'bat' else 2))
        if prop == 'wrench':
            cv.circle(tip, s * .022, colour, lw * 1.5)
    elif prop in ('cup', 'can', 'bottle'):
        w, ht = (s * .03, s * .045) if prop != 'bottle' else (s * .025, s * .08)
        colour = {'cup': (245, 245, 245), 'can': (60, 60, 190), 'bottle': (190, 160, 90)}[prop]
        cv.poly([(h[0] - w / 2, h[1] - ht), (h[0] + w / 2, h[1] - ht), (h[0] + w / 2, h[1] + s * .005), (h[0] - w / 2, h[1] + s * .005)], colour, INK, lw)
    elif prop == 'key':
        cv.circle((h[0], h[1] - s * .015), s * .012, (60, 190, 230), lw * 1.4)
        cv.line((h[0], h[1] - s * .003), (h[0] + ux * s * .04, h[1] + uy * s * .04), (60, 190, 230), lw * 1.4)
    elif prop == 'money':
        cv.poly([(h[0] - s * .04, h[1] - s * .02), (h[0] + s * .04, h[1] - s * .02), (h[0] + s * .04, h[1] + s * .015), (h[0] - s * .04, h[1] + s * .015)], (110, 190, 120), INK, lw)
    elif prop == 'food':
        cv.circle((h[0], h[1] - s * .015), s * .028, (70, 80, 210))
        cv.circle((h[0], h[1] - s * .015), s * .028, INK, lw)
    elif prop == 'bag':
        cv.poly([(h[0] - s * .05, h[1] + s * .02), (h[0] + s * .05, h[1] + s * .02), (h[0] + s * .06, h[1] + s * .13), (h[0] - s * .06, h[1] + s * .13)], (80, 130, 160), INK, lw)
    elif prop == 'radio':
        cv.poly([(h[0] - s * .02, h[1] - s * .05), (h[0] + s * .02, h[1] - s * .05), (h[0] + s * .02, h[1] + s * .02), (h[0] - s * .02, h[1] + s * .02)], (50, 50, 50), INK, lw)
        cv.line((h[0] + s * .012, h[1] - s * .05), (h[0] + s * .012, h[1] - s * .09), INK, lw)
    elif prop == 'clock':
        cv.circle(h, s * .035, (240, 240, 240))
        cv.circle(h, s * .035, INK, lw)
        cv.line(h, (h[0], h[1] - s * .025), INK, lw)
        cv.line(h, (h[0] + s * .018, h[1]), INK, lw)
    elif prop == 'rope':
        pts = [(h[0] + k * s * .02, h[1] + math.sin(k * 1.2 + t * 3) * s * .015 + k * s * .02) for k in range(8)]
        cv.polyline(pts, (60, 140, 190), lw * 1.6)
    elif prop == 'hammer':
        tip = (h[0] + ux * s * .22, h[1] + uy * s * .22)
        cv.line((h[0] - ux * s * .03, h[1] - uy * s * .03), tip, (60, 110, 160), lw * 2.2)
        px, py = -uy, ux
        cv.poly([(tip[0] - px * s * .05 - ux * s * .02, tip[1] - py * s * .05 - uy * s * .02), (tip[0] + px * s * .05 - ux * s * .02, tip[1] + py * s * .05 - uy * s * .02),
                 (tip[0] + px * s * .05 + ux * s * .03, tip[1] + py * s * .05 + uy * s * .03), (tip[0] - px * s * .05 + ux * s * .03, tip[1] - py * s * .05 + uy * s * .03)],
                (110, 110, 110), INK, lw)
    elif prop == 'extinguisher':
        cv.poly([(h[0] - s * .03, h[1] - s * .02), (h[0] + s * .03, h[1] - s * .02), (h[0] + s * .03, h[1] + s * .13), (h[0] - s * .03, h[1] + s * .13)], (50, 50, 210), INK, lw)
        cv.line((h[0], h[1] - s * .02), (h[0] + ux * s * .08, h[1] - s * .05), INK, lw * 1.6)
    elif prop == 'hose':
        pts = [(h[0] - ux * s * (.02 + k * .05) + math.sin(k * .9) * s * .02, h[1] + k * s * .05) for k in range(10)]
        cv.polyline(pts, (40, 170, 220), lw * 3)
        cv.line(h, (h[0] + ux * s * .06, h[1] + uy * s * .06), (150, 150, 150), lw * 3)
    elif prop == 'lantern':
        c = (h[0], h[1] + s * .06)
        overlay_poly(cv, [(c[0] - s * .12, c[1] - s * .12), (c[0] + s * .12, c[1] - s * .12), (c[0] + s * .12, c[1] + s * .12), (c[0] - s * .12, c[1] + s * .12)], (170, 235, 250), .18)
        cv.poly([(c[0] - s * .025, c[1] - s * .04), (c[0] + s * .025, c[1] - s * .04), (c[0] + s * .025, c[1] + s * .04), (c[0] - s * .025, c[1] + s * .04)], (200, 245, 255), INK, lw)
        cv.line((c[0] - s * .03, c[1] - s * .04), (c[0] + s * .03, c[1] - s * .04), (150, 150, 60), lw * 2.5)
        cv.line((c[0] - s * .03, c[1] + s * .04), (c[0] + s * .03, c[1] + s * .04), (150, 150, 60), lw * 2.5)
        cv.line(h, (c[0], c[1] - s * .04), INK, lw)
    elif prop == 'mirror':
        cv.circle(h, s * .03, (235, 215, 190))
        cv.circle(h, s * .03, INK, lw)
        cv.line((h[0] - s * .012, h[1] - s * .012), (h[0] + s * .004, h[1] - s * .02), (255, 255, 255), lw)
    elif prop == 'tape':
        cv.circle(h, s * .022, (170, 170, 170), lw * 2.2)
    elif prop == 'cart':
        # a shopping cart pushed in front: handle at the hand, basket ahead, wheels on the floor
        floor = j.get('ffoot', (h[0], h[1] + s * .45))[1]
        ahead = facing
        x0 = h[0]
        x1 = x0 + ahead * s * .42
        top = h[1] + s * .02
        cv.line((x0, h[1]), (x0 + ahead * s * .04, top), INK, lw * 1.6)
        basket = [(x0 + ahead * s * .04, top), (x1, top), (x1 - ahead * s * .04, top + s * .2), (x0 + ahead * s * .08, top + s * .2)]
        cv.poly(basket, (225, 225, 225), INK, lw)
        for k in range(1, 4):
            xx = x0 + ahead * s * (.04 + k * .095)
            cv.line((xx, top), (xx - ahead * s * .01, top + s * .2), (150, 150, 150), lw * .7)
        cv.line((x0 + ahead * s * .08, top + s * .2), (x0 + ahead * s * .08, floor - s * .03), INK, lw)
        cv.line((x1 - ahead * s * .04, top + s * .2), (x1 - ahead * s * .06, floor - s * .03), INK, lw)
        for xx in (x0 + ahead * s * .08, x1 - ahead * s * .06):
            cv.circle((xx, floor - s * .02), s * .02, INK)


def draw_tool(cv, sprite, j, size, facing):
    """A painted tool from the library (a snow shovel, a flare, a fire axe) held in the front hand, turned along the
    forearm and sized to the figure (owner, 16 Nov: the characters hold and use whatever object the story needs)."""
    import numpy as np
    cv2 = cv.cv2
    frame = cv.frame
    h, w = sprite.shape[:2]
    target = max(8., size * .3)
    scale = target / max(h, w)
    small = cv2.resize(sprite, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    if facing < 0:
        small = small[:, ::-1]
    hx, hy = j['fhand']
    ex, ey = j['felbow']
    angle = math.degrees(math.atan2(hy - ey, hx - ex))
    turn = -(angle - (0 if facing > 0 else 180)) * .5        # half way between upright and along the arm
    sh, sw = small.shape[:2]
    side = int(math.hypot(sh, sw)) + 2
    pad = np.zeros((side, side, 4), np.uint8)
    pad[(side - sh) // 2:(side - sh) // 2 + sh, (side - sw) // 2:(side - sw) // 2 + sw] = small
    m = cv2.getRotationMatrix2D((side / 2, side / 2), turn, 1.)
    pad = cv2.warpAffine(pad, m, (side, side), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    x0, y0 = int(hx - side / 2), int(hy - side / 2)
    H, W = frame.shape[:2]
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + side), min(H, y0 + side)
    if xa >= xb or ya >= yb:
        return
    part = pad[ya - y0:yb - y0, xa - x0:xb - x0]
    alpha = part[..., 3:4].astype(np.float32) / 255
    frame[ya:yb, xa:xb] = (frame[ya:yb, xa:xb] * (1 - alpha) + part[..., :3] * alpha).astype(np.uint8)


ANIMAL_SIZE = dict(cat=.34, dog=.45, bird=.14, mouse=.12)


def draw_animal(cv, kind, x, ground, size, facing, t, moving=False, colour='#2B2B2B'):
    """A small animal in the same ink style (after the stix animal library, MIT: a body line, a round head, ears that
    tell the kind, four legs with a walk cycle, a tail). size is the human figure's size; the animal scales from it."""
    s = size * ANIMAL_SIZE.get(kind, .3)
    lw = max(2., size * .014)
    ink = bgr(colour) if colour.startswith('#') else INK
    f = facing
    step = math.sin(t * 9) if moving else 0.
    if kind == 'bird':
        hop = abs(math.sin(t * 6)) * s * .25 if moving else 0.
        body = (x, ground - s * .45 - hop)
        cv.ellipse(body, (s * .45, s * .3), 0, (90, 90, 90))
        cv.circle((body[0] + f * s * .4, body[1] - s * .25), s * .2, (90, 90, 90))
        cv.poly([(body[0] + f * s * .58, body[1] - s * .28), (body[0] + f * s * .78, body[1] - s * .22), (body[0] + f * s * .58, body[1] - s * .18)], (40, 160, 230))
        wing = math.sin(t * 14) * s * .2 if moving else 0.
        cv.line((body[0], body[1] - s * .05), (body[0] - f * s * .35, body[1] - s * .2 - wing), INK, lw)
        for k in (-1, 1):
            cv.line((body[0] + k * s * .08, body[1] + s * .28), (body[0] + k * s * .1, ground - hop), INK, lw * .7)
        cv.circle((body[0] + f * s * .45, body[1] - s * .29), lw * .5, INK)
        return
    tall = s * (.32 if kind != 'mouse' else .2)
    hip = (x - f * s * .42, ground - tall)
    chest = (x + f * s * .38, ground - tall * 1.05)
    cv.line(hip, chest, ink, lw * 1.6)
    for k, base in enumerate((hip, hip, chest, chest)):
        swing = (step if k % 2 == 0 else -step) * s * .12 * (1 if k < 2 else -1)
        off = (k % 2) * s * .06 * f
        cv.line((base[0] + off, base[1]), (base[0] + off + swing, ground), ink, lw)
    head = (chest[0] + f * s * .16, chest[1] - s * .16)
    r = s * (.17 if kind != 'mouse' else .14)
    cv.circle(head, r, (245, 245, 245))
    cv.circle(head, r, ink, lw)
    if kind == 'cat':
        for k in (-.5, .45):
            cv.poly([(head[0] + k * r - r * .3, head[1] - r * .7), (head[0] + k * r, head[1] - r * 1.6), (head[0] + k * r + r * .3, head[1] - r * .7)], (245, 245, 245), ink, lw * .8)
        for k in (-1, 0, 1):
            cv.line((head[0] + f * r * .9, head[1] + r * .2), (head[0] + f * r * 1.8, head[1] + r * (.2 + .25 * k)), ink, lw * .5)
        tail = [(hip[0] - f * s * (.05 + .07 * q), hip[1] - s * .09 * q * q - math.sin(t * 2 + q) * s * .03) for q in range(6)]
    elif kind == 'dog':
        cv.ellipse((head[0] - f * r * .55, head[1] - r * .1), (r * .3, r * .7), 15 * f, (90, 130, 170))
        cv.ellipse((head[0] + f * r * 1.05, head[1] + r * .25), (r * .45, r * .3), 0, (245, 245, 245))
        cv.circle((head[0] + f * r * 1.45, head[1] + r * .2), lw * .7, INK)
        wag = math.sin(t * 12) * s * .08
        tail = [(hip[0] - f * s * .05 * q, hip[1] - s * .05 * q + wag * q / 5) for q in range(6)]
    else:
        for k in (-.3, .3):
            cv.circle((head[0] + k * r, head[1] - r * .9), r * .45, (200, 180, 230))
            cv.circle((head[0] + k * r, head[1] - r * .9), r * .45, ink, lw * .7)
        tail = [(hip[0] - f * s * .08 * q, hip[1] + s * .02 * q + math.sin(t * 4 + q) * s * .02) for q in range(8)]
    cv.polyline(tail, ink, lw)
    cv.circle((head[0] + f * r * .45, head[1] - r * .15), lw * .55, INK)


def overlay_poly(cv, pts, colour, alpha):
    import numpy as np
    layer = cv.frame.copy()
    arr = np.array([cv.p(q) for q in pts], dtype=np.int32)
    cv.cv2.fillPoly(layer, [arr], colour, cv.cv2.LINE_AA, cv.SHIFT)
    cv.cv2.addWeighted(layer, alpha, cv.frame, 1 - alpha, 0, cv.frame)


def sheet(path, designs, width=1600, height=900):
    """A character sheet for the settings page: each character in a row of expressions and poses."""
    import numpy as np
    import cv2
    frame = np.full((height, width, 3), (208, 232, 244), np.uint8)
    cv = Canvas(cv2, frame)
    rows = len(designs)
    looks = (('idle', 'neutral'), ('talk', 'happy'), ('point', 'determined'), ('shrug', 'confused'), ('panic', 'scared'), ('think', 'thinking'))
    for r, d in enumerate(designs):
        ground = height * (r + 1) / rows - 40
        size = (height / rows - 70) * d.get('height', 1.)
        for k, (action, face) in enumerate(looks):
            x = width * (k + .5) / len(looks)
            draw_figure(cv, d, pose(action, .9 + k * .37, 3., seed=k), x, ground, size, 1 if k % 2 == 0 else -1, face, t=.9, seed=k + 1)
        cv2.putText(frame, d.get('name', ''), (24, int(ground - size + 30)), cv2.FONT_HERSHEY_DUPLEX, 1.1, (40, 40, 40), 2, cv2.LINE_AA)
    cv2.imwrite(str(path), frame)
    return str(path)
