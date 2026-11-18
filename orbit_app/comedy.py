"""Joke structure from measured evidence, and the social-video formula applied to an approved edit.

humor_cues() reads what the transcript and the audio actually show: laughter words, a loud reaction right after a
line, a comic pause before the last words, a turn word ("but", "kiderült"). These are cues for the editor model, not a
claim that something is funny. social_polish() then punctuates an already approved story with local sound effects:
it never adds, removes or reorders footage, and an intentional pause stays silent.
"""
import re

LAUGH = re.compile(r'\b(?:ha(?:ha)+h?|he(?:he)+|hi(?:hi)+|xd+|lol|lmao|rofl)\b|[\[(](?:nevet\w*|röhög\w*|laugh\w*|taps\w*|applause)[\])]|\bnevet(?:és|ek|nek|ünk)\b', re.I)
TURN = re.compile(r'\b(?:de|viszont|csakhogy|kiderült|aztán|erre|hirtelen|but|actually|turns out|then|suddenly|plot twist|wait)\b', re.I)
SURPRISE = re.compile(r'\b(?:mi(?:\s+a)?\s+(?:fasz|franc|fene)|úristen|te jó ég|nem hiszem el|komolyan|what the|oh my god|no way|wtf|omg)\b', re.I)

GUIDE = '''Humor and social formula. Each catalog unit may carry humor cues measured from the audio and transcript:
laughter (laughter words in the line), reaction_after (a loud audience/speaker reaction within 2.5 s after the line),
comic_pause (a deliberate pause before the final words), turn (a contrast word), surprise (an exclamation). A cue is
evidence of timing, not proof that something is funny; read the actual words to understand the joke: who sets up
which expectation, what breaks it, and how the reaction confirms it. A punchline needs its setup; never cut the setup
or step on the pause before the punchline. End on the reaction or a short button line, not on dead air.
Hook formula (choose ONE, the strongest supported by evidence): (1) cold open: a 1-3 s teaser of the real reaction or
surprise, then the story from its start; (2) the setup line that opens a question or conflict immediately; (3) a bold
real claim. A hook must not give away the punchline in words. Prefer a hook understandable without context.'''


def _words(transcript):
    return [w for seg in transcript.get('segments', []) for w in seg.get('words', []) if type(w.get('start')) in (int, float) and type(w.get('end')) in (int, float)]


def _lift(levels, start, end):
    """Loudest level in [start,end) above the median voiced level (dB), or None without measurements."""
    db = (levels or {}).get('db') or []
    step = (levels or {}).get('step') or .5
    voiced = sorted(x for x in db if x > -60)
    window = db[int(start / step):max(int(start / step) + 1, int(end / step))]
    if not window or not voiced:
        return None
    return max(window) - voiced[len(voiced) // 2]


def humor_cues(unit, transcript):
    """Measured cues for one catalog unit; an empty list when nothing is evidenced."""
    text = unit.get('text') or ''
    cues = []
    if LAUGH.search(text):
        cues.append('laughter')
    if SURPRISE.search(text):
        cues.append('surprise')
    if TURN.search(text):
        cues.append('turn')
    words = _words(transcript)
    inside = [w for w in words if unit['start'] <= w['start'] < unit['end']]
    after = [w for w in words if unit['end'] <= w['start'] < unit['end'] + 2.5]
    if len(inside) >= 4:
        # A pause of at least 0.5 s right before the last one to three words: classic comic timing.
        tail = inside[-4:]
        if any(b['start'] - a['end'] >= .5 for a, b in zip(tail, tail[1:])):
            cues.append('comic_pause')
    levels = (transcript.get('audio_context') or {}).get('loudness')
    lift = _lift(levels, unit['end'], unit['end'] + 2.5)
    if (lift is not None and lift >= 6) or any(LAUGH.search(w.get('word', '')) for w in after):
        cues.append('reaction_after')
    return cues


def annotate(catalog, tracks):
    """Adds humor cues to speech units in place; units with no cue get no field, so plain sources stay unchanged."""
    for unit in catalog:
        if unit.get('boundary') == 'visual_sample':
            continue
        cues = humor_cues(unit, tracks[unit['source']].get('transcript') or {})
        if cues:
            unit['humor'] = cues
    return catalog


def _sound(shot, name, at_end):
    from sfx import seconds
    length = shot['end'] - shot['start']
    if length < seconds(name) + .05:
        return False
    shot['sound'] = name
    shot['sound_delay'] = round(max(0, length - seconds(name)), 3) if at_end else 0
    shot['sound_at'] = 'end' if at_end else 'start'
    shot['formula_sound'] = True
    return True


def social_polish(plan, catalog, style):
    """Sound accents on the approved story's real beats. Returns the list of applied accents (for the timeline)."""
    if (style or {}).get('edit_formula', 'social') != 'social':
        return []
    shots = plan.get('shots') or []
    ids = plan.get('unit_ids') or []
    applied = []

    def free(shot):
        return shot.get('sound', 'none') == 'none' and not shot.get('preserve_pause')

    def cues(index):
        uid = ids[index] if index < len(ids) else None
        return set(catalog[uid].get('humor', [])) if type(uid) is int and 0 <= uid < len(catalog) else set()

    payoff = [i for i, s in enumerate(shots) if s.get('beat') == 'payoff']
    if payoff:
        p = payoff[-1]
        found = cues(p)
        # The punchline lands on its last word: a bass hit for a joke or reveal, a scratch for a sudden turn.
        name = 'scratch' if 'turn' in found and 'reaction_after' not in found else 'boom'
        if free(shots[p]) and _sound(shots[p], name, at_end=True):
            applied.append(dict(shot=p, sound=name, reason='payoff'))
        # Tension rises into the payoff cut.
        if p > 0 and free(shots[p - 1]) and shots[p - 1].get('beat') != 'hook' and _sound(shots[p - 1], 'riser', at_end=True):
            applied.append(dict(shot=p - 1, sound='riser', reason='build into payoff'))
    # Cold open: a hook taken from later in the source jumps back with a rewind.
    if len(shots) > 1 and len(ids) > 1 and type(ids[0]) is int and type(ids[1]) is int:
        hook, nxt = catalog[ids[0]], catalog[ids[1]]
        if hook['source'] == nxt['source'] and hook['start'] > nxt['start'] and free(shots[1]) and _sound(shots[1], 'rewind', at_end=False):
            applied.append(dict(shot=1, sound='rewind', reason='cold open'))
    for i, shot in enumerate(shots):
        if shot.get('transition') == 'wipe' and free(shot) and _sound(shot, 'whoosh', at_end=False):
            applied.append(dict(shot=i, sound='whoosh', reason='scene change'))
        elif shot.get('beat') == 'reaction' and 'laughter' in cues(i) and free(shot) and _sound(shot, 'pop', at_end=False):
            applied.append(dict(shot=i, sound='pop', reason='reaction'))
    plan['social_formula'] = applied
    return applied
