"""Automations from plain Hungarian, reliably: "minden reggel 8-kor nézd meg a Telex főoldalát és foglald össze".

The general planner often promised an automation and created none (or saved a Shorts style instead). Here the
schedule is read deterministically from the words, one small model call separates the task itself from its
timing, and a real, enabled ORBIT task is saved. Its runs go through the main assistant, so anything the chat can
do (news lookups, research, computer control, Shorts, email drafts, multi-step work) can be automated.
"""
import datetime
import json
import re
import time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Budapest')
RUN_MARK = '[ORBIT-RUN]'
SCHEDULE = re.compile(r'\b(utemez\w*|idozit\w*|minden (?:nap|reggel|este|ejjel|ejszaka|delben|delutan|oraban|oran|percben|heten|hetfon|kedden|szerdan|csutortokon|penteken|szombaton|vasarnap|hetkoznap|hetvegen)\w*|'
                      r'naponta|napi rendszeresseggel|orankent|percenkent|hetente|havonta|\d+\s*(?:percenkent|orankent|naponta)|ismeteld|fusson le \w+|holnapig|mostantol\b.{0,60}\b(?:ig|naponta|orankent)|'
                      r'figyeld (?:folyamatosan|minden)|ertesits,? ha|rendszeresen|hetkoznap\w*|hetvegen\w*|reggelente|estenkent|delutanonkent|hetfonkent|'
                      r'(?:hetfon|kedden|szerdan|csutortokon|penteken|szombaton|vasarnap)\w* (?:reggel|este|delben|\d))\b')
# "Automata videógenerálást", "a clip farm automatizálásával": a one-off start, not a schedule. An automation noun with
# a set-up verb is.
SETUP = re.compile(r'\b(automatizaci\w*|automatizalt feladat\w*|automata feladat\w*|utemezett feladat\w*)\b')
SETUP_VERB = re.compile(r'\b(allits\w*|beallit\w*|hozz letre|hozd letre|keszits\w*|indits\w*|csinalj\w*|letrehoz\w*|uj)\b')
QUESTION = re.compile(r'(\?\s*$|\b(beallitottad|letrehoztad|elinditottad|fut(?:nak)? (?:mar )?az?|milyen automatiz\w*|mik az automatiz\w*|hol (?:latom|vannak)|hogy all\w*|hol tart\w*)\b)')
STOP = re.compile(r'\b(allitsd le|kapcsold ki|torold|szuntesd meg|ne fusson)\b.*\bautomatiz\w*|\bautomatiz\w*.*\b(allitsd le|kapcsold ki|leallit\w*)\b')
WEEKDAYS = dict(hetfo=0, kedd=1, szerda=2, csutortok=3, pentek=4, szombat=5, vasarnap=6)
NUMBERS = dict(egy=1, ket=2, ketto=2, harom=3, negy=4, ot=5, hat=6, het=7, nyolc=8, kilenc=9, tiz=10, tizenket=12, tizenketto=12)

EXTRACT = '''From the user's request to automate something, separate WHAT must be done each run from WHEN. Return JSON
{"task":"the complete task for ONE run, in Hungarian, imperative (e.g. "nézd meg a telex.hu főoldalát és foglald össze..."), with every detail, source, constraint, output format
and recipient the user gave, but WITHOUT the schedule words and WITHOUT asking to create an automation",
"name":"short Hungarian title (max 60 chars)"}. JSON only.'''


GOAL = re.compile(r'\b(\d+|' + '|'.join(NUMBERS) + r')\s*(?:db|darab)?\s*(sikeres|kesz|elkeszult|jo|uj|hibatlan)?\s*(\w*(?:video|short|epizod|animaci|futas|eredmeny|kep|cikk|poszt)\w*)\b')
VIDEO_WORDS = re.compile(r'(video|short|epizod|animaci)')


def goal(prompt):
    """dict(target, output) for "10 sikeres videó legyen", "amíg nincs 15 kész short", or None."""
    p = norm(prompt)
    m = GOAL.search(p)
    if not m or not _number(m.group(1)):
        return None
    automated = bool(re.search(r'\b(automatiz\w*|amig|ameddig|sikeres|celja|cel\b|legyen|osszesen|egymas utan|folyamatosan)\b', p))
    if not automated:
        return None
    return dict(target=min(500, _number(m.group(1))), output='video' if VIDEO_WORDS.search(m.group(3)) else 'any')


def norm(text):
    from model_router import normalized
    return re.sub(r'\s+', ' ', normalized(text)).strip()


def wants(prompt):
    if RUN_MARK in prompt or prompt.lstrip().startswith('Valósítsd meg most ezt a fejlesztést'):
        return False
    p = norm(prompt)
    timed = bool(SCHEDULE.search(p)) or bool(SETUP.search(p) and SETUP_VERB.search(p)) or bool(goal(prompt))
    return timed and not QUESTION.search(p) and not STOP.search(p) and len(p) < 3000


def asks_about(prompt):
    if RUN_MARK in prompt:
        return False
    p = norm(prompt)
    return bool(re.search(r'\bautomatiz\w*|\bfeladat(?:ok|aim|ot)\b', p)) and bool(QUESTION.search(p))


def _number(word):
    return int(word) if word.isdigit() else NUMBERS.get(word)


def schedule(prompt, now=None):
    """dict(interval, daily_time, plan, daily_goal, run_now) read from the words."""
    p = norm(prompt)
    now = now or time.time()
    today = datetime.datetime.fromtimestamp(now, ZONE).date()
    out = dict(interval=1440, daily_time=None, plan=dict(start_date=today.isoformat(), end_date='', weekdays=list(range(7)), from_time='00:00', to_time='23:59'), daily_goal=1, run_now=False)
    # Clock time: "8-kor", "8:30-kor", "reggel 7 órakor", "este 9-kor".
    m = re.search(r'\b(\d{1,2})(?:[:.](\d{2}))?\s*(?:-?kor|orakor|ora(?:kor)?)\b', p) or re.search(r'\b(?:reggel|este|delutan|ejjel|ejszaka)\s+(\d{1,2})(?:[:.](\d{2}))?\b', p)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if re.search(r'\b(este|delutan)\b', p) and hour < 12:
            hour += 12
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            out['daily_time'] = '%02d:%02d' % (hour, minute)
    elif re.search(r'\breggel\w*\b', p):
        out['daily_time'] = '08:00'
    elif re.search(r'\beste\w*\b', p):
        out['daily_time'] = '20:00'
    elif re.search(r'\bdelben\b', p):
        out['daily_time'] = '12:00'
    every = re.search(r'\b(\d+|' + '|'.join(NUMBERS) + r')\s*(percenkent|orankent|naponta)\b', p)
    if every and _number(every.group(1)):
        n = _number(every.group(1))
        out['interval'] = dict(percenkent=n, orankent=n * 60, naponta=n * 1440)[every.group(2)]
        out['daily_time'] = None if every.group(2) != 'naponta' else out['daily_time']
    elif re.search(r'\borankent|minden oraban|minden oran\b', p):
        out['interval'], out['daily_time'] = 60, None
    elif re.search(r'\bpercenkent\b', p):
        out['interval'], out['daily_time'] = 5, None
    elif re.search(r'\bhetente|minden heten\b', p):
        out['interval'] = 10080
    if out['interval'] < 1440:
        out['daily_goal'] = min(48, max(1, 1440 // out['interval']))
    days = [d for name, d in WEEKDAYS.items() if re.search(r'\b' + name + r'\w*', p)]
    if re.search(r'\bhetkoznap\w*', p):
        days = [0, 1, 2, 3, 4]
    elif re.search(r'\bhetvege\w*', p):
        days = [5, 6]
    if days:
        out['plan']['weekdays'] = sorted(set(days))
    if re.search(r'\bholnap(?:i)?\s*(?:ejjel|ejszaka|estig|ejfelig|ig|delig)|\bholnapig\b', p):
        out['plan']['end_date'] = (today + datetime.timedelta(days=1)).isoformat()
    elif re.search(r'\bma (?:estig|ejjelig|ejfelig)|\bmara\b', p):
        out['plan']['end_date'] = today.isoformat()
    # A count is a repeat order only next to a run verb ("fusson le 3-szor", "3-szor egymás után", "ismételd 5 alkalommal"),
    # never a number in the task's own text ("a hiba 11-szer állította meg").
    m = re.search(r'\b(?:fusson le|fusd le|ismeteld|ismetelje|csinald meg|keszitsd el)\s+(?:\w+\s+){0,3}?(\d+|' + '|'.join(NUMBERS) + r')\s*-?\s*(?:szor|szer|alkalommal)\b', p) or \
        re.search(r'\b(\d+|' + '|'.join(NUMBERS) + r')\s*-?\s*(?:szor|szer)\s+egymas utan\b', p)
    if m and _number(m.group(1)):
        # "Fusson le egymás után 3-szor": a short series today.
        out['daily_goal'] = min(48, _number(m.group(1)))
        if not out['daily_time'] and out['interval'] >= 1440:
            out['interval'] = 10
        if not out['plan']['end_date']:
            out['plan']['end_date'] = today.isoformat()
    # "Mostantól holnap éjszakáig ..." with no frequency: keep working through the period, every 3 hours.
    if out['plan']['end_date'] and out['interval'] == 1440 and not out['daily_time'] and out['daily_goal'] == 1:
        out['interval'], out['daily_goal'] = 180, 8
    # Without a clock time the first run starts now ("mostantól", a series, a repeating interval).
    out['run_now'] = not out['daily_time']
    return out


def extract(s, prompt):
    from studio import local_api
    from assist_jobs import chat_model
    from assistant_resilience import json_object
    r = local_api('ollama', 'api/chat', dict(model=chat_model(), _orbit_wait=90, stream=False, format='json', think=False, keep_alive='10m',
                                             options=dict(num_ctx=4096, num_predict=500, temperature=0),
                                             messages=[dict(role='system', content=EXTRACT), dict(role='user', content=prompt)]), timeout=120)
    data = json_object(r.get('message', {}).get('content', '') or '{}')
    task = str(data.get('task') or '').strip()
    name = str(data.get('name') or '').strip()[:60]
    return task, name


def describe(a):
    when = ('minden nap ' + a['config']['daily_time'] + '-kor') if a['config'].get('daily_time') else (
        'óránként' if a['interval'] == 60 else str(a['interval']) + ' percenként' if a['interval'] < 1440 else 'naponta' if a['interval'] == 1440 else 'hetente')
    days = a['plan'].get('weekdays', list(range(7)))
    if days != list(range(7)):
        names = ['hétfő', 'kedd', 'szerda', 'csütörtök', 'péntek', 'szombat', 'vasárnap']
        when += ' (' + ', '.join(names[d] for d in days) + ')'
    if a['plan'].get('end_date'):
        when += ', ' + a['plan']['end_date'] + '-ig'
    if a['daily_goal'] > 1 and a['interval'] < 1440:
        when += ', legfeljebb ' + str(a['daily_goal']) + '× naponta'
    return when


def create(s, job, prompt):
    """Saves and enables the automation; the first run starts now when no clock time was given."""
    import automations
    plan = schedule(prompt)
    target = goal(prompt)
    if target:
        # A goal needs no repetition settings: runs follow each other until the target is met.
        target['since'] = time.time()
        plan.update(interval=5, daily_time=None, daily_goal=48, run_now=True)
        plan['plan']['end_date'] = ''
    s.job_stage(job['id'], 'automation_plan', 'Automatizáció · a feladat és az időzítés értelmezése')
    task, name = extract(s, prompt)
    if len(task) < 8:
        return 'Az időzítést értettem, de azt nem, hogy minden alkalommal pontosan mit csináljak. Írd le egy mondatban a feladatot.'
    # A run is marked, so its own wording can never set up another automation.
    task = RUN_MARK + ' ' + task
    if target:
        existing = same_automation(s, prompt, name)
        if existing:
            # "A stoner automatizáció célja legyen 10 sikeres videó": the existing task gets the goal.
            cfg = dict(existing['config'], goal=target)
            cfg.pop('daily_time', None)
            automations.save(s, existing['project'], dict(existing, config=cfg, enabled=True, interval=5, daily_goal=48, runtime_minutes=max(240, existing.get('runtime_minutes', 120)),
                                                          plan=dict(existing['plan'], end_date='')))
            a = automations.get(s, existing['project'], existing['id'])
            automations.goal_step(s, a, time.time())
            unit = 'sikeres videó' if target['output'] == 'video' else 'sikeres futás'
            return ('A meglévő „' + a['name'] + '” automatizációt átállítottam célra: ' + str(target['target']) + ' ' + unit + '. Ismétlést nem kell megadnod: '
                    'a futások egymás után jönnek, hiba után azonnal újraindul a hibával együtt, és a cél elérésekor leáll.')
    config = dict(scope='global', prompt=task, **({'daily_time': plan['daily_time']} if plan['daily_time'] else {}), **({'goal': target} if target else {}))
    saved = automations.save(s, 'universe', dict(name=name or task[:60], kind='assistant', config=config, enabled=True, interval=plan['interval'],
                                                 plan=plan['plan'], runtime_minutes=240 if target else 120, daily_goal=plan['daily_goal']))
    aid = saved.get('id') if isinstance(saved, dict) else saved
    a = automations.get(s, 'universe', aid)
    started = ''
    if target:
        automations.goal_step(s, a, time.time())
        unit = 'sikeres videó' if target['output'] == 'video' else 'sikeres futás'
        return ('Beállítottam és elindítottam: „' + a['name'] + '” · cél: ' + str(target['target']) + ' ' + unit + '.'
                ' A futások egymás után jönnek, amíg a cél meg nincs; ' + ('csak a ténylegesen elkészült videó számít. ' if target['output'] == 'video' else '') +
                'Ha egy futás hibára fut, azonnal újraindul, és a következő megkapja az előző hibáját, hogy kijavítsa. Sok egymás utáni hiba után megáll és szól.'
                '\nAz állást itt kérdezheted („hogy áll az automatizáció?”), vagy a Feladatok oldalon látod.')
    if plan['run_now']:
        try:
            automations.launch(s, 'universe', aid, manual=True)
            # The scheduler must not start the same run again: the next one is one interval later.
            from autonomous import next_slot
            nxt = next_slot(time.time() + a['interval'] * 60, a['plan'])
            s.db.execute('UPDATE automations SET next_run=? WHERE id=?', (nxt or 0, aid))
            s.db.commit()
            started = ' Az első futás most elindult; az eredményt itt, a chatben kapod meg.'
        except Exception as exc:
            started = ' Az első futás nem indult el: ' + str(exc)[:200]
    else:
        due = datetime.datetime.fromtimestamp(a['next_run'], ZONE).strftime('%m.%d. %H:%M') if a.get('next_run') else ''
        started = (' Első futás: ' + due + '.') if due else ''
    return ('Beállítottam és bekapcsoltam az automatizációt: „' + a['name'] + '” · ' + describe(a) + '.' + started +
            '\nMinden futás eredménye itt, a fő chatben jelenik meg; a Feladatok oldalon szüneteltetheted vagy módosíthatod.')


def same_automation(s, prompt, name):
    """An existing automation the request is about: its name's words appear in the request."""
    import automations
    automations.schema(s)
    words = lambda t: {w for w in re.findall(r'[a-z0-9]{4,}', norm(t)) if w not in ('automatizacio', 'automatizaciot', 'automatizacio', 'legyen', 'sikeres', 'video', 'videot', 'generalasa', 'keszitese')}
    asked = words(prompt) | words(name)
    best = None
    for r in s.rows('SELECT * FROM automations WHERE archived=0'):
        a = automations.decode(r)
        common = len(words(a['name']) & asked)
        if common >= 2 and (not best or common > best[0]):
            best = (common, a)
    return best[1] if best else None


def overview(s):
    import automations
    automations.schema(s)
    rows = [automations.decode(r) for r in s.rows('SELECT * FROM automations WHERE archived=0 ORDER BY created DESC')]
    if not rows:
        return 'Még nincs beállított automatizáció. Írd le, mit és mikor csináljak (pl. „minden reggel 8-kor foglald össze a Telex főoldalát”).'
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    lines = []
    for a in rows[:12]:
        last = s.db.execute('SELECT status,created FROM automation_runs WHERE automation=? ORDER BY created DESC LIMIT 1', (a['id'],)).fetchone()
        state = '▶︎ be' if a['enabled'] else '⏸ ki'
        when = describe(a) if a['kind'] == 'assistant' else ('naponta' if a['interval'] >= 1440 else str(a['interval']) + ' percenként')
        if a['config'].get('goal'):
            g = automations.goal_progress(s, a)
            when = 'cél: ' + str(g['done']) + '/' + str(g['target']) + (' kész videó' if a['config']['goal'].get('output') == 'video' else ' sikeres futás') + (' · ' + str(g['failures_in_a_row']) + ' hiba egymás után' if g['failures_in_a_row'] else '')
        lines.append(state + ' · „' + a['name'] + '” (' + names.get(a['project'], a['project']) + ') · ' + when +
                     (' · utolsó futás: ' + {'done': 'kész', 'failed': 'hiba', 'running': 'fut', 'starting': 'indul'}.get(last['status'], last['status']) if last else ' · még nem futott'))
    return 'Automatizációk:\n' + '\n'.join(lines)
