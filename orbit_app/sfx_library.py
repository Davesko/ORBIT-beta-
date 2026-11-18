"""Real recorded sound effects for story cues, from the Kenney CC0 packs on the model SSD.

Each story cue maps to sample-name patterns. A variant is picked by a stable hash of the episode and the shot, so
episodes do not all share one recording. Cues with no fitting recording (crunch, snore, whoosh) stay synthesized.
The packs are CC0 (public domain): usable in commercial videos without attribution."""
import hashlib
import re
from pathlib import Path

FOLDER = 'audio/sfx-kenney'
CUES = {
    'impact': ('impactPunch_medium', 'impactSoft_medium', 'impactGeneric_light'),
    'boom': ('lowFrequency_explosion', 'impactPunch_heavy'),
    'pop': ('pluck', 'drop'),
    'glitch': ('glitch', 'computerNoise'),
    'ding': ('bong', 'confirmation', 'correct'),
    'scratch': ('scratch',),
    'game_over': ('Male/game_over', 'Male/you_lose', 'Female/game_over'),
    'splat': ('slime', 'impactSoft_heavy'),
    'zap': ('zap', 'laserSmall', 'zapTwoTone'),
    'reveal': ('Pizzicato jingles/',),
    'tick': ('tick', 'switch'),
    'chime': ('Steel jingles/', 'threeTone'),
    'record_stop': ('phaserDown',),
    'glass': ('impactGlass_heavy', 'impactGlass_medium'),
    'coins': ('handleCoins',),
    'power_up': ('powerUp', 'Male/power_up'),
    'footsteps': ('footstep_carpet', 'footstep_wood'),
    'door': ('doorOpen', 'doorClose'),
    'error': ('error', 'wrong'),
    'win': ('Male/you_win', 'Hit jingles/'),
}


def root(base):
    return Path(base) / FOLDER if base else None


def index(base):
    folder = root(base)
    if not folder or not folder.is_dir():
        return []
    import time
    for attempt in range(3):
        # An external SSD can interrupt a directory walk (10 Nov: "Interrupted system call" stopped a whole episode).
        try:
            return sorted(str(p) for p in folder.rglob('*') if p.suffix.lower() in ('.ogg', '.wav')
                          and not p.name.startswith('._') and '/zips/' not in str(p))
        except OSError:
            time.sleep(2 * (attempt + 1))
    return []  # the synthesized effects still work


def matches(files, pattern):
    """Files whose name (or folder/name) starts with the pattern, as in impactPunch_medium_003.ogg."""
    out = []
    for path in files:
        parts = Path(path).parts
        tail = parts[-2] + '/' + parts[-1]
        if pattern.endswith('/'):
            if tail.startswith(pattern):
                out.append(path)
        elif re.match(re.escape(pattern) + r'(?:_?\d+)?\.(?:ogg|wav)$', parts[-1]) or re.match(re.escape(pattern) + r'(?:_?\d+)?\.(?:ogg|wav)$', tail):
            out.append(path)
    return out


def pick(files, cue, key):
    """One recording for the cue, chosen by a stable hash of key; None when the cue has no recording."""
    candidates = [f for pattern in CUES.get(cue, ()) for f in matches(files, pattern)]
    if not candidates:
        return None
    return candidates[int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(candidates)]


# Free-text search over every recording on the disk (owner, 16 Nov: "ne egy párat tölts le, hanem mindig tudjon a
# projekthez illően keresni"): the writer names the sound ("a metal shutter rolling down"), the words are matched
# against the file and folder names with a few synonyms, and the best recording wins. Too weak a match returns None,
# and the caller makes the sound itself (stickman_audio.synth) rather than playing something unrelated.
SYNONYMS = {
    'metal': ('metal', 'plate', 'tin', 'bell'), 'steel': ('metal', 'plate'), 'shutter': ('metal', 'plate'), 'door': ('door',),
    'glass': ('glass',), 'window': ('glass',), 'wood': ('wood', 'plank'), 'box': ('wood', 'soft'), 'crate': ('wood',),
    'punch': ('punch',), 'hit': ('punch', 'impact'), 'thud': ('soft', 'impact'), 'fall': ('soft', 'impact', 'drop'),
    'step': ('footstep',), 'footsteps': ('footstep',), 'walk': ('footstep',), 'run': ('footstep',), 'snow': ('snow',),
    'grass': ('grass',), 'concrete': ('concrete',), 'carpet': ('carpet',), 'click': ('click', 'switch', 'tick'),
    'button': ('click', 'switch', 'select'), 'switch': ('switch', 'click'), 'beep': ('tone', 'bong', 'confirmation'),
    'alarm': ('error', 'alarm'), 'error': ('error', 'wrong'), 'coin': ('coin', 'chip'), 'money': ('coin', 'chip'),
    'cards': ('card',), 'dice': ('dice', 'die'), 'laser': ('laser', 'zap'), 'electric': ('zap', 'laser'), 'spark': ('zap',),
    'power': ('powerup', 'power'), 'win': ('win', 'jingle'), 'magic': ('jingle', 'chime'), 'bell': ('bell', 'bong'),
    'explosion': ('explosion', 'heavy'), 'boom': ('explosion', 'heavy'), 'slime': ('slime',), 'splash': ('slime', 'soft'),
    'paper': ('card',), 'book': ('card', 'soft'), 'chain': ('metal', 'chip'), 'key': ('metal', 'chip'), 'lock': ('metal', 'door'),
}


def search(files, text, key=''):
    """(path, score) of the recording that best fits a free-text sound description, or (None, 0)."""
    words = [w for w in re.findall(r'[a-z]+', str(text or '').lower()) if len(w) > 2]
    terms = set()
    for w in words:
        terms.update(SYNONYMS.get(w, ()) or SYNONYMS.get(w.rstrip('s'), ()) or (w,))
    if not terms:
        return None, 0
    best, top = [], 0
    for path in files:
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', '/'.join(Path(path).parts[-3:])).lower()
        score = sum(2 if re.search(r'\b' + re.escape(t), name) else 1 if t in name else 0 for t in terms)
        if score > top:
            best, top = [path], score
        elif score == top and score:
            best.append(path)
    if top < 2:
        return None, top
    return best[int(hashlib.sha256((key or text).encode()).hexdigest()[:8], 16) % len(best)], top
