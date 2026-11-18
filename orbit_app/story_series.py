"""The animation studio's series brain: a cast of two or more fixed characters, several video formats they can star
in, the series' own lore and a memory of what has already happened.

The owner (14 Nov): the studio felt "dumb", working on one basic principle. He wants a series for YouTube with two or
more consistent characters who can be put into several kinds of videos, and episodes that know about fresh news and
viral events.

- Cast: every character of the project lives in story-studio/bible.json with a fixed look (the rig draws it from
  these words, so it is identical in every episode), a personality and a voice. Two of them are on screen in an
  episode: the ones the request names, otherwise the main pair. The rig, the voices and the captions work with a
  lead and a support, so an episode has two speaking characters; the series can have as many as the owner adds.
- Formats: the same characters in different kinds of videos (bro logic, today's news, a debate, a top three, a
  narrated explainer, a story time). A format is a way of writing; the rendering is the same rig.
- Lore and memory: permanent facts of the series the writers must respect, and the earlier episodes, so a new one
  can call back to an old one and never repeats it.
- Trends come from trend_radar with the facts behind them, so an episode about a real event says what happened.
"""
import json, re, time
import story_episode

BIBLE_FILE = 'story-studio/bible.json'
TAG = re.compile(r'\s*\[(formátum|szereplők|trend):([^\]]{1,200})\]')

COMMON = ('Write an original 2D stickman cartoon Short for TikTok, Reels and Shorts, for a Gen Z / Gen Alpha feed. THE STORY IS IN THE '
          'DIALOGUE: the viewer must get every joke from the words alone, at first hearing. One ordinary place, two characters: lead and '
          'support, in exactly the personalities and names given in characters. Every line is one complete, instantly understood thought. '
          'premise is the situation and what the episode is about. Never metaphors about bodies, never fantasy events, no moral lesson, no '
          'dated slang, no slurs, no cruelty about real private people. Original lines only: never reuse a known joke or any line from these '
          'instructions; every line is about this episode\'s own topic. ')
# 15 Nov (owner, with four reference Shorts: scared of his own shadow, the mosquito inside the net, the principal and the
# chips, overthinker vs doer): "minőségben nagyon elmarad". What those do and ours did not: ONE situation understood in
# the first second without a word; a body that wants something and an obstacle that fights back; every beat a physical
# action with a new framing (a cut every 1-1.5 s, close-ups of a scared or smug face); a false victory and a backfire
# the viewer sees coming one second too late; 10-25 seconds; hardly any words; sounds only for what is seen.
# Ours: 36 seconds of two characters standing at a couch, hands on hips, talking philosophy, one pose per 7-second shot.
GAG = ('Write an original 2D stickman cartoon Short of 15-20 seconds: a VISUAL GAG that works with the sound off, like a silent slapstick '
       'cartoon. ONE everyday situation everyone knows in one second (trying to sleep, sneaking a snack, a mosquito in the room, a scary noise at '
       'night, the last slice, a stuck door, a wobbly chair, hiding something from a teacher or a boss). lead WANTS one concrete physical thing; ONE '
       'obstacle fights back: an object, an animal, his own shadow, or support (who is the obstacle, the victim or the unimpressed witness, in his '
       'own personality). Structure, one beat each: hook = the threat or the goal in the very first second, as an action with a terrified, greedy or '
       'smug face, never an introduction; setup = the first attempt; escalation = a bigger, dumber attempt with the same object; reaction = false '
       'victory, lead is smug and relaxes; twist = the plan backfires through its own logic, cause and effect the viewer sees coming one second too '
       'late (the mosquito is inside the net; the slipper bounces back; the principal eats the chips himself); loop = the aftermath pose, which '
       'returns to the opening picture. premise names the situation, what lead wants, the obstacle and the backfire in one or two plain sentences. '
       'Every beat is a PHYSICAL ACTION of a body: sneaks, runs in, jumps, crouches, pushes, slaps, points, faints, recoils in shock, rages, cries, '
       'dances; never two characters standing and talking. One prop carries the gag from the first beat to the last (story_prop). '
       'Words: at most one line per beat, 1-6 words, a reaction or exclamation that anyone understands ("Nope.", "Got you.", "Why is it INSIDE?"), '
       'and at least two beats with no words at all. hook_caption is the situation as a short title a viewer would tap ("He thought the net would '
       'save him"); payoff_caption says the backfire. The place is ONE specific, richly described location with its time of day and light (for example '
       '"a dim living room at night lit by one yellow table lamp, a half-open door, a staircase in shadow"), and each shot\'s setting is a different '
       'corner or angle of that same place. No metaphors, no fantasy events, no moral, no slurs, nothing cruel about real people. Original only: '
       'never reuse a known cartoon\'s gag or any example from these instructions. ')
GAG_ACTING = ('This is rig animation: each shot sets lead_action and support_action (what the body does for the WHOLE shot), prop_motion (how the '
              'prop behaves: fly_in when it is thrown or lands, bounce, shake, wobble, grow; none hides it) and seated. Pick the action that IS the beat: '
              'sneak or walk_in to approach, run_in or run to flee or chase, jump for a scare or a pounce, crouch to hide, push or slap for a hit, '
              'point to accuse, shock for a recoil, faint for a knockout, rage, cry, laugh or dance for the result; the other character reacts in the '
              'same shot (shock, stare, laugh, facepalm). No two shots in a row with the same action. visual_action names who does what to which '
              'object in plain words. show is always empty. ')
GAG_RULES = (' FOR THIS FORMAT, overriding anything above: lines has at most ONE line of 1-6 words per shot and at least two shots have an empty '
             'lines list; caption is always empty; sfx is none except one meme sound on the twist (every other sound is added from the actions); '
             'each shot setting names a different corner or angle of the one location, with its light.')
GAG_SECONDS = 18

FORMATS = {
    'gag': dict(label='Képi poén', about='Szavak nélkül is érthető, 15–20 másodperces akciójelenet: egy szereplő akar valamit, egy tárgy vagy a társa visszavág, a terv a saját logikája szerint sül el visszafelé. Az alapformátum.', trend='optional', guidance=GAG),
    'bro_logic': dict(label='Bro logic', about='Beszélgetős formátum: a főszereplő zuhanyfilozófiát kérdez, a másik csak a nyugalmát akarná.', trend='optional', guidance=None),
    'news': dict(label='Mai hír', about='A páros egy valódi, friss hírre vagy virális eseményre reagál: az egyik félreérti, a másik a tényekkel helyreteszi.', trend='required',
                 guidance='FORMAT "today\'s news": lead bursts in with one real thing that happened today (the trend) and explains it completely wrong but with '
                          'total confidence; support, dry and tired, corrects him with what actually happened, using only the facts in what_happened. '
                          'Each beat: one real fact of the event said plainly (name the company, app, game, show or person), then lead\'s dumb conclusion from it. '
                          'The viewer must recognise the real news in the first line. The last beat is lead\'s worst possible takeaway and a one- or two-word '
                          'reaction from support. Never invent numbers, quotes or events that are not in what_happened. '),
    'debate': dict(label='Vita', about='Egy hétköznapi „ez vagy az” kérdésben a két szereplő két oldalon áll, három körben, egyre nagyobb érvekkel.', trend='optional',
                   guidance='FORMAT "debate": the two argue the two sides of one silly everyday either/or question about the topic (which is better, which '
                            'is worse, which came first). Three rounds: each round both give one argument of 8-16 words, each sharper and more unhinged than '
                            'the last, lead with wild confidence, support with dry logic. The twist: a third answer nobody argued for wins, or both turn out '
                            'to mean the same thing. End on a short line that restarts the argument. '),
    'ranking': dict(label='Top 3', about='A főszereplő rangsorol három dolgot a témából, magabiztosan rossz indoklással; az első hely abszurd, de megcáfolhatatlan.', trend='optional',
                    guidance='FORMAT "top three": lead ranks three things about the topic from number three to number one, saying the number out loud each '
                             'time ("Number three: ..."), each with a confident, wrong but oddly convincing reason of 10-18 words; support objects in 2-8 '
                             'words after each. Number one is absurd and undeniable. The last line is support giving up or agreeing against his will. '),
    'explainer': dict(label='Magyarázó', about='Mesélős „észrevetted már…” vagy „hogyan csinálták…” videó narrátorral, a szereplők eljátsszák.', trend='optional',
                      guidance='FORMAT "narrated explainer": ' + story_episode.EXPLAINER),
    'storytime': dict(label='Sztori', about='A főszereplő elmeséli, mi történt vele ma; a másik száraz kérdésekkel szakítja meg, a végén kiderül, ki okozta a bajt.', trend='optional',
                      guidance='FORMAT "story time": lead tells what happened to him today as a small story in the past tense ("So I walk into..."), one step per '
                               'beat, each step a worse decision made with full confidence; support interrupts with one dry question of 2-8 words per beat. '
                               'The twist reveals that lead caused the whole problem himself, or that it happened to support. End on a line that loops back to the opening. '),
}
FORMAT_WORDS = (('news', r'\b(h[ií]r\w*|news|friss esem\w*|vir[aá]lis esem\w*|mi t[oö]rt[eé]nt)\b'), ('debate', r'\b(vita\w*|vit[aá]z\w*|debate|\bvs\b|melyik a jobb)\b'),
                ('ranking', r'\b(top ?\d|rangsor\w*|ranking|toplista)\b'), ('storytime', r'\b(sztori\w*|storytime|story time|elmes[eé]l\w*|pov)\b'),
                ('explainer', r'\b(magyar[aá]z\w*|explainer|ismeretterjeszt\w*)\b'))


def default_bible(s, pid):
    old = story_episode.cast(s, pid)
    chars = []
    for role in ('lead', 'support'):
        name = old['names'][role]
        look = old[role].split(':', 1)[1].strip() if ':' in old[role] else old[role]
        chars.append(dict(id=slug(name), name=name, look=look, persona=old['persona'][role], voice=dict(old['voices'][role]), main=True))
    return dict(version=1, characters=chars, lore=[], formats=dict(mode='fixed', fixed='gag', enabled=list(FORMATS)))


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')[:24] or 'szereplo'


def valid_character(c):
    return (isinstance(c, dict) and isinstance(c.get('name'), str) and 1 <= len(c['name'].strip()) <= 24 and ':' not in c['name']
            and isinstance(c.get('look'), str) and 10 <= len(c['look'].strip()) and len(c['name'].strip()) + 2 + len(c['look'].strip()) <= 180
            and isinstance(c.get('persona'), str) and 10 <= len(c['persona'].strip()) <= 400
            and isinstance(c.get('voice'), dict) and c['voice'].get('voice') in story_episode.VOICES)


def bible(s, pid):
    path = s.safe_path(pid, BIBLE_FILE)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or len([c for c in data.get('characters') or [] if valid_character(c)]) < 2:
        data = default_bible(s, pid)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    chars = []
    for c in data['characters']:
        if valid_character(c) and c.get('id') not in [x['id'] for x in chars]:
            chars.append(dict(id=str(c.get('id') or slug(c['name'])), name=c['name'].strip(), look=' '.join(c['look'].split()), persona=' '.join(c['persona'].split()),
                              voice=dict(voice=c['voice']['voice'], speed=c['voice'].get('speed', 1.0), pitch=c['voice'].get('pitch', 0)), main=bool(c.get('main')),
                              says=[str(x)[:60] for x in c.get('says') or [] if str(x).strip()][:4]))
    formats = data.get('formats') if isinstance(data.get('formats'), dict) else {}
    enabled = [f for f in formats.get('enabled') or list(FORMATS) if f in FORMATS] or ['bro_logic']
    return dict(version=1, characters=chars[:12], lore=[' '.join(str(x).split())[:200] for x in data.get('lore') or [] if str(x).strip()][:20],
                formats=dict(mode='rotate' if formats.get('mode') == 'rotate' else 'fixed', chosen=bool(formats.get('chosen')),
                             # until the owner picks a format himself, the default is the visual gag (15 Nov)
                             fixed=formats.get('fixed') if formats.get('chosen') and formats.get('fixed') in FORMATS else 'gag', enabled=enabled))


def write(s, pid, data):
    path = s.safe_path(pid, BIBLE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


# ---------------------------------------------------------------- the request's own choices

def tags(brief):
    return {k: v.strip() for k, v in TAG.findall(str(brief or ''))}


def strip(brief):
    """The request without the studio's own [formátum:…] [szereplők:…] [trend:…] marks."""
    return TAG.sub('', str(brief or '')).strip()


def pick_cast(b, brief, ids=None):
    chars = b['characters']
    by = {c['id']: c for c in chars}
    chosen = [by[i] for i in ids or [] if i in by]
    if len(chosen) < 2:
        wanted = [by[i] for i in re.split(r'[,; ]+', tags(brief).get('szereplők', '')) if i in by]
        low = strip(brief).lower()
        named = sorted((c for c in chars if re.search(r'(?<!\w)' + re.escape(c['name'].lower()) + r'(?!\w)', low)), key=lambda c: low.find(c['name'].lower()))
        chosen = list({c['id']: c for c in chosen + wanted + named}.values())
    mains = [c for c in chars if c['main']] or chars
    for c in mains + chars:
        if len(chosen) >= 2:
            break
        if c not in chosen:
            chosen.append(c)
    return chosen[:2]


def cast_for(s, pid, brief='', ids=None):
    """The two characters of an episode, in the shape the rest of the studio reads (lead, support, persona, voices, names)."""
    lead, support = pick_cast(bible(s, pid), brief, ids)
    voices = story_episode.voices(dict(lead=lead['voice'], support=support['voice']))
    persona = lambda c: c['persona'] + (' Typical lines: ' + ' / '.join('"' + x + '"' for x in c['says']) + '.' if c['says'] else '')
    return dict(lead=lead['name'] + ': ' + lead['look'], support=support['name'] + ': ' + support['look'],
                persona=dict(lead=persona(lead)[:480], support=persona(support)[:480]), voices=voices,
                names=dict(lead=lead['name'], support=support['name']), ids=[lead['id'], support['id']])


def pick_format(b, brief, count=0):
    wanted = tags(brief).get('formátum')
    if wanted in FORMATS:
        return wanted
    from model_router import normalized
    low = normalized(strip(brief))
    for name, pattern in FORMAT_WORDS:
        if re.search(pattern, low) or re.search(pattern, strip(brief), re.I):
            return name
    f = b['formats']
    if f['mode'] == 'rotate':
        return f['enabled'][count % len(f['enabled'])]
    return f['fixed']


def guidance(name):
    """The writing rules of a format. Bro logic keeps the studio's own tuned text."""
    g = FORMATS.get(name or 'bro_logic', FORMATS['bro_logic'])['guidance']
    if name == 'gag':
        return g
    return story_episode.MEME_GUIDANCE if not g else g + COMMON


def acting(name):
    """How the rig is directed: a visual gag moves, a dialogue format stays calm."""
    return GAG_ACTING if name == 'gag' else story_episode.ACTING + story_episode.EXPLAINER


def run_format(s, job, payload):
    """The format of the episode a step belongs to: chosen at the idea step, read back from it by the later steps."""
    if payload.get('story_step') != 'hook' and payload.get('run'):
        row = s.db.execute("SELECT result FROM jobs WHERE project=? AND status='done' AND json_extract(payload,'$.run')=? AND json_extract(payload,'$.story_step')='hook'",
                           (job['project'], payload['run'])).fetchone()
        try:
            return json.loads(row[0]).get('series_format') if row else None
        except ValueError:
            return None
    count = s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND agent=? AND status='done' AND json_extract(payload,'$.story_step')='hook'", (job['project'], job['agent'])).fetchone()[0]
    return pick_format(bible(s, job['project']), payload.get('story_brief') or '', count)


def memory(s, pid, limit=10):
    """What earlier episodes were about, newest first, from the finished idea steps."""
    rows = s.rows("""SELECT result,finished FROM jobs WHERE project=? AND status='done' AND json_extract(payload,'$.story_step')='hook'
                     ORDER BY finished DESC LIMIT ?""", (pid, limit))
    total = s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND status='done' AND json_extract(payload,'$.story_step')='hook'", (pid,)).fetchone()[0]
    out = []
    for i, row in enumerate(rows):
        try:
            idea = json.loads(row['result'])
        except ValueError:
            continue
        if isinstance(idea, dict) and idea.get('premise'):
            out.append(dict(episode=total - i, about=str(idea['premise'])[:200], punchline=str(idea.get('payoff_caption') or '')[:140], trend=str(idea.get('trend') or '')[:120],
                            format=idea.get('series_format') or 'bro_logic', cast=idea.get('cast_names') or [], finished=row['finished']))
    return out


def writer_context(s, pid, brief, count):
    """Everything the series adds to an idea request: who stars, in which format, the lore and the earlier episodes."""
    b = bible(s, pid)
    cast = cast_for(s, pid, brief)
    fmt = pick_format(b, brief, count)
    past = memory(s, pid, 8)
    context = dict(format=fmt, cast=cast, lore=b['lore'],
                   memory=[dict(episode=m['episode'], about=m['about'], punchline=m['punchline']) for m in past])
    return context


LORE_RULE = (' series_lore lists permanent facts of this series: stay consistent with them. series_memory lists earlier episodes: never repeat '
             'one, and one short callback to an earlier episode is welcome only when it fits the line naturally.')


# ---------------------------------------------------------------- the studio's own page

def save_character(s, pid, data):
    b = bible(s, pid)
    if not isinstance(data, dict):
        raise ValueError('Érvénytelen szereplő.')
    name = ' '.join(str(data.get('name') or '').split())
    voice = data.get('voice') if isinstance(data.get('voice'), dict) else {}
    c = dict(id=str(data.get('id') or ''), name=name, look=' '.join(str(data.get('look') or '').split()), persona=' '.join(str(data.get('persona') or '').split()),
             voice=dict(voice=voice.get('voice'), speed=min(1.08, max(1.0, float(voice.get('speed') or 1.0))), pitch=int(min(4, max(-4, float(voice.get('pitch') or 0))))),
             main=data.get('main') is True, says=[' '.join(str(x).split())[:60] for x in data.get('says') or [] if str(x).strip()][:4])
    if not valid_character(c):
        raise ValueError('A szereplőhöz kell: név (legfeljebb 24 betű), külső angolul (névvel együtt legfeljebb 180 karakter), személyiség (10–400 karakter) és egy hang a listából.')
    old = next((x for x in b['characters'] if x['id'] == c['id']), None)
    if old:
        b['characters'][b['characters'].index(old)] = c
    else:
        if len(b['characters']) >= 12:
            raise ValueError('Legfeljebb 12 szereplő lehet egy sorozatban.')
        c['id'] = slug(name)
        if any(x['id'] == c['id'] or x['name'].lower() == name.lower() for x in b['characters']):
            raise ValueError('Ilyen nevű szereplő már van.')
        b['characters'].append(c)
    if c['main']:
        # The main pair is two characters: marking a third makes the oldest main an ordinary cast member.
        mains = [x for x in b['characters'] if x['main'] and x['id'] != c['id']]
        for x in mains[:-1]:
            x['main'] = False
    write(s, pid, b)
    return dict(message='Szereplő mentve. A következő epizódtól így szerepel.', id=c['id'])


def remove_character(s, pid, cid):
    b = bible(s, pid)
    if len(b['characters']) <= 2:
        raise ValueError('Legalább két szereplő kell a sorozathoz.')
    left = [c for c in b['characters'] if c['id'] != cid]
    if len(left) == len(b['characters']):
        raise ValueError('Ismeretlen szereplő.')
    b['characters'] = left
    write(s, pid, b)
    return dict(message='A szereplő kikerült a sorozatból. A kész epizódok megmaradnak.')


def save_settings(s, pid, patch):
    b = bible(s, pid)
    if isinstance(patch.get('lore'), list):
        b['lore'] = [' '.join(str(x).split())[:200] for x in patch['lore'] if str(x).strip()][:20]
    f = patch.get('formats')
    if isinstance(f, dict):
        if f.get('mode') in ('rotate', 'fixed'):
            b['formats']['mode'] = f['mode']
        if f.get('fixed') in FORMATS:
            b['formats']['fixed'] = f['fixed']
            b['formats']['chosen'] = True
        if isinstance(f.get('enabled'), list):
            b['formats']['enabled'] = [x for x in FORMATS if x in f['enabled']] or ['bro_logic']
    write(s, pid, b)
    return dict(message='Mentve.')


def start_episode(s, pid, args):
    """One episode from the studio page: an optional trend, format, pair and topic, written into the request."""
    import story_animation
    hook = story_animation.agent_ids(pid)['hook']
    if not s.db.execute('SELECT 1 FROM agents WHERE id=? AND id NOT IN (SELECT id FROM agent_archive)', (hook,)).fetchone():
        raise ValueError('Az Animációs stúdió ötletgazdája nincs meg ebben a projektben.')
    if s.db.execute("SELECT 1 FROM jobs WHERE project=? AND status IN ('queued','running') AND json_extract(payload,'$.story_step') IS NOT NULL", (pid,)).fetchone():
        import stickman_studio
        raise ValueError(stickman_studio.busy_text(s, pid) or 'Már készül egy epizód.')
    b = bible(s, pid)
    topic = ' '.join(str(args.get('topic') or '').split())[:300]
    trend = ' '.join(str(args.get('trend') or '').split())[:160].replace(']', ')')
    fmt = args.get('format') if args.get('format') in FORMATS else None
    ids = [c for c in args.get('cast') or [] if c in {x['id'] for x in b['characters']}][:2]
    if fmt == 'news' and not trend and not topic:
        raise ValueError('A „Mai hír” formátumhoz válassz egy trendet a radarról, vagy írd be a hírt.')
    brief = '[ORBIT-RUN] Készíts egy új saját animációs shortot' + (': ' + topic if topic else '. A témát a friss trendekből válaszd.')
    if fmt:
        brief += ' [formátum:' + fmt + ']'
    if len(ids) == 2:
        brief += ' [szereplők:' + ','.join(ids) + ']'
    if trend:
        brief += ' [trend:' + trend + ']'
    run = s.enqueue_graph(pid, hook, brief)
    return dict(message='Az epizód elindult. A Műhely folyamatábráján követhető, a kész videó a Publikálás oldalon vár.', run=run.get('run'))


def snapshot(s, pid):
    import trend_radar
    b = bible(s, pid)
    radar = trend_radar.saved(s)
    running = s.rows("SELECT id,status FROM jobs WHERE project=? AND status IN ('queued','running') AND json_extract(payload,'$.story_step') IS NOT NULL LIMIT 1", (pid,))
    refreshing = bool(s.db.execute("SELECT 1 FROM jobs WHERE project=? AND kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='watch_radar'", (pid,)).fetchone())
    return dict(characters=b['characters'], lore=b['lore'], formats=b['formats'],
                format_list=[dict(id=k, label=v['label'], about=v['about'], trend=v['trend']) for k, v in FORMATS.items()],
                voices=[dict(id=k, label=v[1]) for k, v in story_episode.VOICES.items()],
                radar=dict(updated=radar.get('updated') or 0, items=radar['items'][:20], refreshing=refreshing),
                episodes=memory(s, pid, 30), busy=bool(running))


def studio_project(s, args):
    import story_animation
    pid = str((args or {}).get('project') or '') or story_animation.project(s)
    if pid != story_animation.project(s):
        raise ValueError('Ez nem az Animációs stúdió projektje.')
    return pid


def dispatch(s, op, args=None):
    args = args or {}
    pid = studio_project(s, args)
    if op == 'series_snapshot':
        return snapshot(s, pid)
    if op.startswith('series_stickman'):
        # 16 Nov: the stickman studio (one main character, narrated second-person stories, Shorts and long videos)
        import stickman_studio
        if op == 'series_stickman':
            return stickman_studio.snapshot(s, pid)
        if op == 'series_stickman_save':
            return stickman_studio.save_settings(s, pid, args.get('settings') or {})
        if op == 'series_stickman_sheet':
            return dict(image=stickman_studio.sheet(s, pid))
        if op == 'series_stickman_start':
            return stickman_studio.start(s, pid, args)
        if op == 'series_stickman_batch':
            until = stickman_studio.until_today(args.get('until')) if str(args.get('until') or '').strip() else None
            return stickman_studio.start_batch(s, pid, until, args.get('kind') or 'long', args.get('minutes') or 10, args.get('topic') or '', args.get('count') or 0)
        if op == 'series_stickman_pilot':
            return stickman_studio.scene_pilot(s, pid)
        if op == 'series_stickman_batch_stop':
            return stickman_studio.stop_batch(s, pid, 'A tulajdonos leállította.')
    if op == 'series_character_save':
        return save_character(s, pid, args.get('character'))
    if op == 'series_character_remove':
        return remove_character(s, pid, str(args.get('id')))
    if op == 'series_save':
        return save_settings(s, pid, args)
    if op == 'series_episode':
        return start_episode(s, pid, args)
    if op == 'series_radar':
        # Reading the sources takes longer than a window call may: a small background job does it (no model).
        agent = s.db.execute('SELECT id FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid LIMIT 1', (pid,)).fetchone()
        if not s.db.execute("SELECT 1 FROM jobs WHERE project=? AND kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='watch_radar'", (pid,)).fetchone():
            s.enqueue(agent[0], 'Trendradar frissítése', 'assist', payload=dict(task='watch_radar', local_only=True))
        return dict(message='A trendradar frissül, fél perc múlva itt lesz.')
    raise ValueError('Ismeretlen sorozat-művelet.')
