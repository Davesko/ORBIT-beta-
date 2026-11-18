"""The score of a finished video (0-100) shown in Publikálás, and the ranking the scheduler uses.

It is an ESTIMATE of how well the video can do, made only from what is known before it is posted - not a measured result:
- chat (40): how hard the streamer's chat exploded at this moment (the watcher's own score of the moment) - the best predictor we have
- format (20): a vertical Short of the right length (20-45 s is best)
- frame (15): facecam on top / game below and word-highlight captions
- title (15): streamer name + game in the title, short enough, not a file name
- check (10): the checker's verdict: the render decoded cleanly and the publishing package passed
- audience (15): how many people watched the broadcast (100 000 viewers = full marks)
- history (15): only once real views exist: how this streamer's earlier clips did on the owner's channels (publish_learn)
A part that does not apply to a video (a simulation has no chat) is left out; such a video is scaled to at most 70, so it never beats a proven chat peak.
A video the checker did not pass can never score 40 or more, so the scheduler never picks it.
"""
import math, re

PARTS = (('chat', 'Chat-reakció', 40), ('format', 'Formátum és hossz', 20), ('frame', 'Kép és felirat', 15), ('title', 'Cím', 15), ('check', 'Ellenőrzés', 10), ('history', 'Eddigi eredmény', 15), ('audience', 'Nézőszám', 15))


def part(key, got, note):
    spec = next(p for p in PARTS if p[0] == key)
    return dict(key=key, label=spec[1], got=round(max(0.0, min(float(spec[2]), float(got))), 1), max=spec[2], note=note)


def compute(kind, facts, title, run, moment, history=None):
    """run: what the Short's production recorded (or None); moment: the watcher's moment row (or None)."""
    parts = []
    if moment is not None:
        parts.append(part('chat', 40 * (1 - math.exp(-float(moment['score'] or 0) / 20)), 'a chat %s pontú csúcsot adott (%s)' % (round(float(moment['score'] or 0), 1), moment['kind'])))
    if moment is not None and moment.get('viewers'):
        v = float(moment['viewers'])
        parts.append(part('audience', 15 * min(1.0, math.log10(1 + v / 100) / 3), '%s néző volt az adásban' % format(int(v), ',').replace(',', ' ')))
    duration = facts.get('duration')
    if facts.get('short') is True and duration:
        got = 20 if 20 <= duration <= 45 else 14 if duration <= 59 else 9 if duration <= 90 else 4
        note = 'álló Short, %d mp' % round(duration) + ('' if 20 <= duration <= 45 else ' (20-45 mp az ideális)')
    elif facts.get('short') is False:
        got, note = 6, 'fekvő vagy hosszú videó'
    else:
        got, note = 8, 'a hossz ismeretlen'
    parts.append(part('format', got, note))
    if run:
        layout, captions = run.get('layout'), bool(run.get('captions'))
        got = (8 if layout == 'stack' else 4 if layout else 0) + (7 if captions else 0)
        parts.append(part('frame', got, ('facecam felül' if layout == 'stack' else 'a teljes kép keretben' if layout else 'nincs képkivágás-adat') + (' · szavankénti felirat' if captions else ' · nincs felirat')))
    t = str(title or '').strip()
    junk = bool(re.fullmatch(r'(short|clip|video)?[\s_-]*[0-9a-f]{8,}', t.lower())) or not t
    if junk:
        got, note = 0, 'nincs valódi cím'
    elif re.search(r'\|\s*GTA\s?6\s*$', t) and ' | ' in t:
        got, note = 15, 'streamer + játék a címben'
    else:
        got, note = (9 if len(t) <= 70 else 5), 'van cím' + ('' if len(t) <= 70 else ', de hosszú')
    parts.append(part('title', got, note))
    checked = None
    if run is not None:
        checked = bool(run.get('complete')) and run.get('decode') == 'passed'
        parts.append(part('check', 10 if checked else 6 if run.get('complete') else 0, 'az ellenőrző átengedte' if checked else 'az ellenőrzés nem teljes' if run.get('complete') else 'az ellenőrző nem engedte át'))
    if history is not None:       # learned from the real reach of earlier posts of this streamer (publish_learn)
        parts.append(part('history', 15 * min(1.0, history / 2), 'ennek a streamernek a videói a saját csatornáidon átlag %s%%-án teljesítettek' % round(history * 100)))
    avail = sum(p['max'] for p in parts)
    # Without chat data only the structure is judged, so such a video can never look as good as a proven chat peak (max 70).
    ceiling = 100 if moment is not None else 70
    total = round(ceiling * sum(p['got'] for p in parts) / avail) if avail else 0
    basis = 'chat-csúcs alapján' if moment is not None else 'chat-adat nélkül (formátum, kép, cím, ellenőrzés)'
    if moment is not None and not re.search(r'grand theft auto\s*(6|vi)\b|\bgta\s*-?\s*(6|vi)\b', str(moment.get('game') or ''), re.I):
        total, basis = min(total, 39), 'NEM GTA 6 tartalom (' + (moment.get('game') or 'ismeretlen játék') + ') - nem kerül automatikus ütemezésbe'
    if run is not None and not run.get('complete'):
        total = min(total, 39)
    return dict(score=total, parts=parts, basis=basis)
