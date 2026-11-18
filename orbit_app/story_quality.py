"""Story quality for viral short animations: a written formula, an independent critic, and lessons learned from the owner.

Every new episode idea is written with the viral formula and the owner's own lessons in the prompt, then scored by
a separate critic call against a fixed rubric plus measured checks (a hook caption that gives away the payoff, a
payoff caption that says something the scene does not show, a support character with no role in the twist, a face
colour that disappears into the background, missing reaction or loop). A weak idea is rewritten with the critique,
the best one is kept, and its report travels with the episode.

Lessons come from the owner: the feedback buttons on a finished video, or what they say about a story in the chat.
Each piece of feedback becomes one to three short general rules, kept per project and applied to every later idea.
Nothing here promises virality; it raises the floor of what reaches the render.
"""
import hashlib
import json
import re
import time

VIRAL_RULES = '''Viral short formula (speech-driven 2D duo, 30-50 s, owner's reference Shorts, 13 Nov):
1. The first line is a complete, relatable shower thought or question the viewer instantly understands and wants to repeat.
2. The hook caption is that first thought (or its tension), never the last joke.
3. The story is in the words: every beat is one new, true-sounding stupid-genius thought about an ordinary thing, each a little more unhinged.
4. Every character has a job: the one who just wants to eat or sleep reacts dry and annoyed, and sometimes gets dragged in.
5. A reaction beat (a short annoyed or dragged-in answer) right before the last joke.
6. The last joke is the dumbest and best: a pun or impossible logic that still follows the pattern set up.
7. Pictures only illustrate what is said: one simple drawing of the key thing of each line.
8. The last beat loops back (a one-word reaction or the running gag), so the video invites a rewatch.
9. Never a metaphor about bodies, a fantasy event or a plot that needs explaining; readable silhouettes on a phone.'''

RUBRIC = ('hook', 'curiosity', 'clarity', 'causality', 'character_roles', 'twist', 'caption_fit', 'loop', 'readability')
CRITIC = '''You are a strict short-form comedy editor. Score this episode idea 0-10 on each criterion: hook (stops the
scroll in 1 s), curiosity (the viewer wants the ending; the hook caption does not reveal it), clarity (every line
understood at first hearing, no metaphors or plot to explain), causality (escalation and twist follow from the setup), character_roles (every character
matters; the calm one pays off), twist (surprising yet earned), caption_fit (each caption matches its picture),
loop (ending returns to the start), readability (silhouettes, colours, one prop on a phone). Apply the owner's
lessons strictly. Be harsh and calibrated: an ordinary decent short scores 6, 8 means clearly strong, 9-10 only an
exceptional idea with nothing left to fix. If your own fix would change the story, the idea is not above 7. Check
the beats against each other: an event that contradicts an earlier beat (an object both swallowed and still outside)
is a causality failure. Return JSON {"scores":{criterion:int},"problems":["short concrete problems"],"fix":"one paragraph:
how to rewrite it into a stronger idea"}.'''
PASS = 8.0
COLOURS = ('purple', 'grey', 'gray', 'orange', 'red', 'yellow', 'blue', 'green', 'pink', 'white', 'black', 'teal', 'brown', 'violet')


def schema(s):
    s.db.execute('CREATE TABLE IF NOT EXISTS story_lessons(id TEXT PRIMARY KEY,project TEXT,lesson TEXT,source TEXT,uses INTEGER DEFAULT 0,created REAL)')
    s.db.commit()


def lessons(s, pid, limit=14):
    schema(s)
    return [r['lesson'] for r in s.rows('SELECT lesson FROM story_lessons WHERE project=? ORDER BY created DESC LIMIT ?', (pid, limit))]


def _words(text):
    return {w for w in re.findall(r'[a-z]{4,}', str(text or '').lower()) if w not in ('with', 'that', 'this', 'from', 'into', 'their', 'there', 'while')}


def checks(idea, profile=None):
    """Measured problems that need no model."""
    out = []
    hook_cap, pay_cap = idea.get('hook_caption', ''), idea.get('payoff_caption', '')
    payoff = ' '.join(str(idea.get(k, '')) for k in ('payoff', 'twist', 'loop'))
    spoil = re.search(r'\b(popped|exploded|burst|it all out|fell|flew|was gone|turned into|ended)\b', hook_cap, re.I)
    if spoil or len(_words(hook_cap) & _words(payoff)) >= 2:
        out.append('The hook caption gives away the outcome; it must create curiosity instead.')
    if pay_cap and not (_words(pay_cap) & _words(payoff + ' ' + idea.get('escalation', ''))):
        out.append('The payoff caption does not describe what the payoff shows.')
    art = (profile or {}).get('art') or {}
    support = str(art.get('support') or '')
    name = re.match(r'\s*([A-Z][a-z]+)', support)
    # The support character must DO something in the escalation or twist, not just be there ("Pip and Dot float").
    if name:
        who = name.group(1)
        acting = re.search(r'\b' + who + r"(?:'s)?\s+(?:\w+ly\s+)?(?!and\b|is\b|are\b|was\b|floats?\b|watch\w*|stares?\b|looks?\b|stands?\b)[a-z]+s\b", ' '.join(str(idea.get(k, '')) for k in ('escalation', 'reaction', 'twist', 'payoff', 'loop')))
        if who in idea.get('premise', '') and not acting:
            out.append('The support character ' + who + ' only watches; give ' + who + ' the action that causes or delivers the twist.')
    # An object swallowed / gone in the payoff cannot still be outside or back in the loop.
    gone = re.search(r'\b(?:sucks? up|swallows?|eats?|devours?|pops?|destroys?|vanish\w*|disappear\w*)\s+(?:the\s+)?(?:\w+\s+){0,3}?(\w+)\b', str(idea.get('payoff', '')) + ' ' + str(idea.get('twist', '')), re.I)
    if gone and re.search(r'\b' + re.escape(gone.group(1)) + r'\b[^.]{0,60}\b(?:still|stuck to|outside|remains?|back on)\b', str(idea.get('loop', '')), re.I):
        out.append('The loop contradicts the payoff: the ' + gone.group(1) + ' is gone in the payoff but still there in the loop.')
    world = str(art.get('world') or '').lower()
    for colour in COLOURS:
        if re.search(r'\bface\w*\b[^.]{0,30}\b' + colour + r'\b|\bturns? ' + colour + r'\b', ' '.join(str(idea.get(k, '')) for k in ('hook', 'escalation')), re.I) and colour in world:
            out.append('A ' + colour + ' face on a ' + colour + ' background will not read on a phone; use a contrasting colour.')
            break
    # The local video model melts any body that changes shape; such a beat comes back as a glitching shot.
    morph = re.search(r'\b(flatten\w*|pancake|melt\w*|morph\w*|stretch\w* (?:like|into)|turns? into|transform\w*|inflat\w*|deflat\w*|liquef\w*)\b',
                      ' '.join(str(idea.get(k, '')) for k in ('hook', 'escalation', 'reaction', 'twist', 'payoff', 'loop')), re.I)
    if morph:
        out.append('A body that changes shape ("' + morph.group(1) + '") cannot be animated cleanly; show the consequence with a pose, a face or a falling object.')
    if not str(idea.get('reaction') or '').strip():
        out.append('There is no reaction beat before the twist.')
    if not str(idea.get('loop') or '').strip():
        out.append('There is no loop back to the opening.')
    return out


def critique(s, job, idea, profile, project_lessons):
    from autonomous import ask_json
    data = dict(idea={k: idea.get(k) for k in ('premise', 'hook', 'setup', 'escalation', 'reaction', 'payoff', 'twist', 'loop', 'hook_caption', 'payoff_caption')},
                cast=(profile or {}).get('art'), owner_lessons=project_lessons, viral_formula=VIRAL_RULES)
    from execution_queue import DeferredExecution
    try:
        raw = ask_json(s, job, CRITIC, data)
    except DeferredExecution:
        raise
    except Exception:
        raw = {}
    scores = raw.get('scores') if isinstance(raw, dict) else {}
    scores = {k: max(0, min(10, int(scores.get(k, 5)))) if isinstance(scores, dict) and isinstance(scores.get(k), (int, float)) else 5 for k in RUBRIC}
    measured = checks(idea, profile)
    problems = [str(p)[:200] for p in (raw.get('problems') or [] if isinstance(raw, dict) else [])][:6] + measured
    # Each measured problem costs half a point, so a pretty score cannot hide a broken caption or a missing loop.
    total = round(sum(scores.values()) / len(scores) - .5 * len(measured), 2)
    return dict(total=total, scores=scores, problems=problems, measured=measured, fix=str(raw.get('fix') or '')[:900] if isinstance(raw, dict) else '')


def improve(s, job, generate, idea, profile, rounds=2):
    """Critique → rewrite with the critique while below PASS; returns (best idea, report)."""
    project_lessons = lessons(s, job['project'])
    best, best_report = idea, critique(s, job, idea, profile, project_lessons)
    history = [best_report['total']]
    for _ in range(rounds):
        if best_report['total'] >= PASS and not best_report['measured']:
            break
        s.job_stage(job['id'], 'story_review', 'Történet-ellenőrzés · ' + str(best_report['total']) + '/10 · átírás a kritika alapján')
        candidate = generate(dict(critic_problems=best_report['problems'], critic_fix=best_report['fix'], previous_idea=best))
        if not candidate:
            continue
        report = critique(s, job, candidate, profile, project_lessons)
        history.append(report['total'])
        if report['total'] > best_report['total']:
            best, best_report = candidate, report
    best_report['history'] = history
    s.job_stage(job['id'], 'story_review', 'Történet-ellenőrzés kész · ' + str(best_report['total']) + '/10')
    return best, best_report


LEARN = '''The owner gave feedback on a short animated story. Turn it into 1-3 short, GENERAL rules for writing future
episodes (English, imperative, max 160 characters each), e.g. "The hook caption must create curiosity, never reveal the
outcome." Only rules the feedback supports; no episode-specific details. Return JSON {"lessons":["..."]}.'''


def learn(s, pid, feedback, idea=None, source='feedback'):
    """Stores the general lessons in a piece of owner feedback. Returns the new lessons."""
    from studio import local_api
    from assist_jobs import chat_model
    from assistant_resilience import json_object
    schema(s)
    feedback = str(feedback or '').strip()
    if len(feedback) < 3:
        return []
    r = local_api('ollama', 'api/chat', dict(model=chat_model(), _orbit_wait=60, stream=False, format='json', think=False, keep_alive='10m',
                                             options=dict(num_ctx=4096, num_predict=400, temperature=0),
                                             messages=[dict(role='system', content=LEARN), dict(role='user', content='Feedback: ' + feedback + ('\nStory: ' + json.dumps(idea, ensure_ascii=False)[:2500] if idea else ''))]), timeout=120)
    try:
        found = json_object(r.get('message', {}).get('content', '') or '{}').get('lessons') or []
    except ValueError:
        found = []
    existing = {re.sub(r'\W+', ' ', l.casefold()).strip() for l in lessons(s, pid, 200)}
    added = []
    for lesson in found[:3]:
        lesson = str(lesson).strip()[:200]
        key = re.sub(r'\W+', ' ', lesson.casefold()).strip()
        if len(lesson) < 12 or key in existing:
            continue
        s.db.execute('INSERT INTO story_lessons VALUES(?,?,?,?,0,?)', (hashlib.sha256((pid + key).encode()).hexdigest()[:16], pid, lesson, source, time.time()))
        existing.add(key)
        added.append(lesson)
    s.db.commit()
    return added


def latest_idea(s, pid):
    row = s.db.execute("SELECT result FROM jobs WHERE project=? AND status='done' AND json_extract(payload,'$.story_step')='hook' ORDER BY finished DESC LIMIT 1", (pid,)).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except ValueError:
        return None
