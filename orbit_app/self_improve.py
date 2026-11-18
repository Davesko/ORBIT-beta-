"""ORBIT's own improvement analyst: per project and for the app itself, what could get better, from measured facts.

Every night (and on request) one scope at a time is analysed: a project that was active in the last week, or ORBIT
itself. First the facts are measured without a model (failure rates, recurring errors, slow steps, chat waiting
times, the owner's editing feedback); repeated errors already become proposals here. Then the local model reads the
facts and proposes up to three concrete improvements, each tied to its evidence. Proposals only: nothing is changed
by this module. The owner accepts one (it goes to the main chat as a request), dismisses it, or marks it done.
"""
import hashlib
import json
import re
import time

WEEK = 7 * 86400
STATES = ('new', 'accepted', 'dismissed', 'done', 'developer')
LABELS = dict(new='új', accepted='elfogadva', dismissed='elvetve', done='kész', developer='fejlesztőre vár')
NEEDS_CODE = re.compile(r'programk[oó]d|k[oó]dm[oó]dos[ií]t|fejleszt[oő]i beavatkoz|fejleszt[oő]nek|forr[aá]sk[oó]d|nem val[oó]s[ií]that[oó] meg', re.I)
NIGHT_HOURS = range(1, 6)
PROMPT = '''You are ORBIT's improvement analyst. ORBIT is a local macOS AI studio: a main chat assistant, agent teams in
projects (YouTube Shorts production, an Autopilot that builds digital products, trading practice with virtual money),
local models only. You receive measured facts about ONE scope (a project, or the ORBIT app itself) from the last 7
days. Propose at most 3 concrete improvements that would most help this scope, ordered by value. Each must be
grounded in the supplied facts (quote the number or error it addresses), be specific (what to change, where in the
workflow), and be feasible locally. Do not propose spending money, publishing, contacting people, live trading or
handling accounts and keys; those stay with the owner. Do not repeat an idea from existing_ideas. If the facts show
nothing worth improving, return an empty list.
Return JSON {"ideas":[{"title":"short Hungarian title (max 80 chars)","why":"Hungarian: what it improves and how, 1-2
sentences","evidence":"Hungarian: the measured fact it rests on","size":"S|M|L","area":"speed|reliability|quality|ux|growth"}]}'''


def schema(s):
    s.db.execute('''CREATE TABLE IF NOT EXISTS improvement_ideas(id TEXT PRIMARY KEY,scope TEXT,title TEXT,why TEXT,evidence TEXT,
                    size TEXT,area TEXT,source TEXT,status TEXT,created REAL,updated REAL)''')
    s.db.execute('CREATE TABLE IF NOT EXISTS improvement_runs(scope TEXT PRIMARY KEY,analysed REAL,facts TEXT)')
    s.db.commit()


def _key(scope, title):
    plain = re.sub(r'[^a-z0-9]+', ' ', __import__('model_router').normalized(title)).strip()
    return hashlib.sha256((scope + '|' + plain).encode()).hexdigest()[:16]


CASCADE = 'Az előző lépés nem fejeződött be'
COUNT = re.compile(r'\s*\(\d+×\)')


def _error_key(text):
    """The same error with different numbers, IDs or paths counts as one."""
    text = re.sub(r'[0-9a-f]{8,}', '#', str(text or '').split('\n')[0])
    return re.sub(r'\d+(?:[.,]\d+)?', 'N', text)[:140].strip()


def facts(s, scope, now=None):
    """Measured, model-free facts for one scope."""
    now = now or time.time()
    since = now - WEEK
    where, args = ("project=?", [scope]) if scope != 'orbit' else ("1=1", [])
    out = dict(scope=scope, days=7)
    if scope != 'orbit':
        try:
            p = s.project(scope)
            out['project'] = dict(name=p.get('name'), description=str(p.get('description') or '')[:300])
        except Exception:
            out['project'] = dict(name=scope)
    rows = s.rows('SELECT kind,status,count(*) AS n,avg(CASE WHEN finished>started AND started>0 THEN finished-started END) AS run,'
                  'avg(CASE WHEN started>created THEN started-created END) AS wait FROM jobs WHERE ' + where + ' AND created>=? GROUP BY kind,status', tuple(args + [since]))
    kinds = {}
    for r in rows:
        k = kinds.setdefault(r['kind'], dict(total=0, failed=0, run_seconds=None, wait_seconds=None))
        k['total'] += r['n']
        if r['status'] in ('failed', 'blocked'):
            k['failed'] += r['n']
        if r['status'] == 'done':
            k['run_seconds'] = round(r['run'] or 0, 1)
            k['wait_seconds'] = round(r['wait'] or 0, 1)
    out['jobs'] = {k: v for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]['total'])[:12]}
    errors = {}
    for r in s.rows("SELECT kind,error FROM jobs WHERE " + where + " AND created>=? AND status IN ('failed','blocked') AND error!=''", tuple(args + [since])):
        if str(r['error']).startswith(CASCADE):
            continue
        key = _error_key(r['error'])
        e = errors.setdefault(key, dict(kind=r['kind'], count=0, example=str(r['error'])[:300]))
        e['count'] += 1
    out['recurring_errors'] = sorted(errors.values(), key=lambda e: -e['count'])[:8]
    if scope == 'orbit':
        chats = s.rows("SELECT started-created AS wait,finished-started AS run FROM jobs WHERE kind='command' AND status='done' AND created>=? AND started>0 AND finished>0", (since,))
        if chats:
            waits = sorted(c['wait'] for c in chats)
            runs = sorted(c['run'] for c in chats)
            out['main_chat'] = dict(answers=len(chats), median_wait_s=round(waits[len(waits) // 2], 1), slow_waits_over_60s=sum(w > 60 for w in waits),
                                    median_answer_s=round(runs[len(runs) // 2], 1), answers_over_60s=sum(r > 60 for r in runs))
        try:
            health = json.loads((s.root / 'scheduler-health.json').read_text())['services']
            out['unhealthy_services'] = [k for k, v in health.items() if not v.get('ok')]
        except (OSError, ValueError, KeyError):
            pass
    else:
        if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='short_runs'").fetchone():
            stops = s.rows("SELECT coalesce(json_extract(payload,'$.auto_step'),json_extract(payload,'$.story_step')) AS step,count(*) AS n FROM jobs WHERE project=? AND kind='graph' AND status='failed' AND created>=? AND coalesce(json_extract(payload,'$.auto_step'),json_extract(payload,'$.story_step')) IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", (scope, since))
            if stops:
                out['shorts_stopped_at'] = {r['step']: r['n'] for r in stops}
            done = s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND kind='graph' AND status='done' AND json_extract(payload,'$.auto_step')='verify' AND created>=?", (scope, since)).fetchone()[0]
            if done or stops:
                out['shorts_finished'] = done
        if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='editing_feedback'").fetchone():
            notes = s.rows('SELECT tag,note FROM editing_feedback WHERE project=? AND created>=? ORDER BY created DESC LIMIT 8', (scope, since))
            if notes:
                out['owner_feedback'] = [dict(tag=n['tag'], note=str(n['note'] or '')[:200]) for n in notes]
    return out


def rule_ideas(scope, data):
    """Proposals that need no model: an error that keeps coming back, a step that keeps stopping."""
    ideas = []
    for e in data.get('recurring_errors', []):
        if e['count'] >= 3:
            ideas.append(dict(title='Visszatérő hiba megszüntetése (' + str(e['count']) + '×)', area='reliability', size='M',
                              why='Ugyanez a hiba egy hét alatt ' + str(e['count']) + '-szor állította meg a(z) ' + e['kind'] + ' feladatokat; a gyökérok javításával ezek a futások végigmennének.',
                              evidence=e['example'][:300]))
    chat = data.get('main_chat') or {}
    if chat.get('slow_waits_over_60s', 0) >= 3:
        ideas.append(dict(title='A fő chat kevesebbet várjon a modellre', area='speed', size='M',
                          why='A chatválaszok egy része több mint egy percig sorban állt, mert más feladat használta a modellt.',
                          evidence=str(chat['slow_waits_over_60s']) + ' válasz várt 60 mp-nél tovább (medián várakozás: ' + str(chat['median_wait_s']) + ' mp).'))
    stops = data.get('shorts_stopped_at') or {}
    if stops:
        step, n = max(stops.items(), key=lambda kv: kv[1])
        if n >= 2:
            from autonomous import STEPS
            label = dict(STEPS).get(step, step)
            ideas.append(dict(title='A Shorts-gyártás ne álljon meg itt: ' + label, area='reliability', size='M',
                              why='Ez a lépés állította meg a legtöbb videót; erre célzott javítás több kész Shortot jelent.',
                              evidence=str(n) + ' megállás a(z) „' + label + '” lépésnél, ' + str(data.get('shorts_finished', 0)) + ' kész videó mellett.'))
    return ideas[:3]


def save(s, scope, ideas, source):
    schema(s)
    now = time.time()
    added = 0
    for idea in ideas:
        title = str(idea.get('title') or '').strip()[:100]
        if len(title) < 4:
            continue
        basis = COUNT.sub('', title)
        if basis != title:
            # A recurring-error card is one per error; its count changes from night to night.
            basis += '|' + _error_key(idea.get('evidence'))
        iid = _key(scope, basis)
        if s.db.execute('SELECT 1 FROM improvement_ideas WHERE id=?', (iid,)).fetchone():
            s.db.execute('UPDATE improvement_ideas SET title=?,evidence=?,updated=? WHERE id=? AND status=?', (title, str(idea.get('evidence') or '')[:500], now, iid, 'new'))
            continue
        size = idea.get('size') if idea.get('size') in ('S', 'M', 'L') else 'M'
        area = idea.get('area') if idea.get('area') in ('speed', 'reliability', 'quality', 'ux', 'growth') else 'quality'
        s.db.execute('INSERT INTO improvement_ideas VALUES(?,?,?,?,?,?,?,?,?,?,?)', (iid, scope, title, str(idea.get('why') or '')[:600],
                     str(idea.get('evidence') or '')[:500], size, area, source, 'new', now, now))
        added += 1
    s.db.commit()
    return added


def model_ideas(s, scope, data, job=None):
    from studio import local_api
    from assist_jobs import chat_model
    existing = [r['title'] for r in s.rows('SELECT title FROM improvement_ideas WHERE scope=? ORDER BY created DESC LIMIT 20', (scope,))]
    response = local_api('ollama', 'api/chat', dict(model=chat_model(), **({'_orbit_job': job['id']} if job else {}), stream=False, format='json', think=False, keep_alive='5m',
                         options=dict(num_ctx=6144, num_predict=1200, temperature=.2),
                         messages=[dict(role='system', content=PROMPT), dict(role='user', content=json.dumps(dict(facts=data, existing_ideas=existing), ensure_ascii=False))]), timeout=300)
    from assistant_resilience import json_object
    raw = json_object(response.get('message', {}).get('content', '') or '{}')
    ideas = raw.get('ideas') if isinstance(raw, dict) else None
    return [i for i in ideas if isinstance(i, dict)][:3] if isinstance(ideas, list) else []


def retire(s, scope):
    """Dismisses open cards that only counted follow-on stops, and older copies of a recurring-error card."""
    rows = s.rows("SELECT id,title,evidence FROM improvement_ideas WHERE scope=? AND status='new' ORDER BY updated DESC", (scope,))
    seen = set()
    for r in rows:
        base = COUNT.sub('', r['title'])
        if str(r['evidence'] or '').startswith(CASCADE) or (base != r['title'] and (base, r['evidence']) in seen):
            s.db.execute("UPDATE improvement_ideas SET status='dismissed',updated=? WHERE id=?", (time.time(), r['id']))
        seen.add((base, r['evidence']))
    s.db.commit()


def analyse(s, scope, job=None, use_model=True):
    """One scope: facts, rule-based ideas, then the model's ideas. Returns the number of new proposals."""
    schema(s)
    retire(s, scope)
    data = facts(s, scope)
    added = save(s, scope, rule_ideas(scope, data), 'measured')
    if use_model:
        added += save(s, scope, model_ideas(s, scope, data, job), 'model')
    s.db.execute('INSERT OR REPLACE INTO improvement_runs VALUES(?,?,?)', (scope, time.time(), json.dumps(data, ensure_ascii=False)))
    s.db.commit()
    return added


def scopes(s, now=None):
    """ORBIT itself and every project that did real work in the last week."""
    now = now or time.time()
    # Only projects that still exist: a project moved to the Kuka kept being analysed and improved (13 Nov, "TermékE").
    active = [r['project'] for r in s.rows("SELECT j.project,count(*) AS n FROM jobs j JOIN projects p ON p.id=j.project WHERE j.created>=? "
                                           "AND j.project NOT IN ('universe','') GROUP BY j.project HAVING n>=3 ORDER BY n DESC", (now - WEEK,))]
    return ['orbit'] + active


def due(s, now=None):
    """The scope analysed longest ago, if it was not analysed in the last 20 hours."""
    schema(s)
    now = now or time.time()
    last = {r['scope']: r['analysed'] for r in s.rows('SELECT scope,analysed FROM improvement_runs')}
    for scope in sorted(scopes(s, now), key=lambda x: last.get(x, 0)):
        if now - last.get(scope, 0) >= ANALYSE_EVERY:
            return scope
    return None


IDLE = 180                 # seconds without any other work before ORBIT uses the time for itself
ANALYSE_EVERY = 6 * 3600   # one scope is looked at again after this long
APPLY_GAP = 1800           # pause between two improvements it carries out itself
APPLY_PER_DAY = 6


def idle(s, now=None):
    """Nothing else is running or waiting, and nothing finished in the last three minutes: free time."""
    now = now or time.time()
    if s.db.execute("""SELECT 1 FROM jobs WHERE status IN ('queued','running') AND NOT (kind='assist' AND json_extract(payload,'$.task')='self_improve')
                       AND coalesce(json_extract(payload,'$.retry_at'),0)<=? LIMIT 1""", (now + 600,)).fetchone():
        return False
    last = s.db.execute("SELECT max(finished) FROM jobs WHERE kind NOT IN ('assist','mission_dispatch')").fetchone()[0] or 0
    return now - last >= IDLE


def schedule(s, now=None):
    """In every idle stretch, day or night: one background analysis at a time, never while one is queued or running."""
    now = now or time.time()
    if not idle(s, now):
        return False
    if s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='self_improve'").fetchone():
        return False
    scope = due(s, now)
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    if not scope or not agent:
        return False
    s.enqueue(agent[0], 'Önfejlesztő elemzés · ' + scope, 'assist', payload=dict(task='self_improve', scope=scope, local_only=True))
    return True


_pace = dict(at=0)


def tick(s, now=None):
    """Called every few seconds by the scheduler; looks at most every five minutes."""
    now = now or time.time()
    if now - _pace['at'] < 300:
        return False
    _pace['at'] = now
    return schedule(s, now) or auto_apply(s, now)


def run_job(s, job):
    scope = json.loads(job['payload']).get('scope') or 'orbit'
    try:
        added = analyse(s, scope, job)
    except Exception as exc:
        from execution_queue import DeferredExecution
        if isinstance(exc, DeferredExecution):
            raise
        # The measured part is still useful when the model fails.
        added = analyse(s, scope, job, use_model=False)
        return 'Önfejlesztő elemzés (' + scope + '): ' + str(added) + ' mért javaslat; a modell most nem válaszolt.'
    return 'Önfejlesztő elemzés (' + scope + '): ' + str(added) + ' új javaslat.'


SELF_TASK = 'Valósítsd meg most ezt a fejlesztést'
URGENCY = dict(sos=0, high=1, normal=2, low=3)
URGENCY_LABEL = dict(sos='SOS', high='fontos', normal='normál', low='ráér')
QUIET = 48 * 3600          # an error that stayed away this long counts as fixed
SHOW_DONE = 24 * 3600      # finished cards stay visible this long, then leave the list
ACTIVITY = {'recovering': 'Hibakezelés', 'resuming': 'Folytatás', 'json_repair': 'Válasz javítása', 'skill': 'Skill használata',
            'network': 'Keresés a weben', 'youtube_research': 'Kutatás', 'tool_error': 'Eszközhiba kezelése', 'empty_reply': 'Üres válasz újrakérése'}
AUDIT = ('Új skill tanulása', 'Új munkamódszer megtanulva', 'Tanult skill hívása', 'Megjegyzett javítás', 'Kérés megértése')


def occurrences(s, idea, now):
    """How often and how recently the measured error behind a card happened: (last time, count in 24 h)."""
    text = str(idea.get('evidence') or '').split('\n')[0][:60]
    if idea.get('source') != 'measured' or len(text) < 12:
        return None
    row = s.db.execute("SELECT max(created),sum(created>=?) FROM jobs WHERE status='failed' AND created>=? AND substr(error,1,?)=?",
                       (now - 86400, now - WEEK, len(text), text)).fetchone()
    return (row[0] or 0, row[1] or 0)


def urgency(s, idea, now):
    seen = occurrences(s, idea, now)
    if seen is None:
        return 'low' if re.search(r'wait_seconds|várakozás', str(idea.get('evidence') or '') + str(idea.get('title') or '')) else 'normal'
    last, today = seen
    return 'sos' if today >= 2 else 'high' if now - last < 3 * 86400 else 'normal'


def resolve(s, now=None):
    """Cards leave by themselves: a measured error that has not come back for two days is fixed, whoever fixed it."""
    now = now or time.time()
    closed = 0
    for r in s.rows("SELECT * FROM improvement_ideas WHERE status IN ('new','accepted') AND source='measured'"):
        seen = occurrences(s, dict(r), now)
        if seen is not None and now - r['created'] > QUIET and now - seen[0] > QUIET:
            closed += s.db.execute("UPDATE improvement_ideas SET status='done',updated=? WHERE id=?", (now, r['id'])).rowcount
    s.db.commit()
    return closed + triage(s, now)


def triage(s, now=None):
    """What the assistant tried and could not do with its own actions needs a change in program code. Such a card is
    set aside as "waiting for a developer" (and written to developer-inbox.md) instead of being tried again every day."""
    now = now or time.time()
    if not s.db.execute("SELECT 1 FROM sqlite_master WHERE name='command_turns'").fetchone():
        return 0
    moved = 0
    for r in s.rows("SELECT * FROM improvement_ideas WHERE status='accepted'"):
        turn = s.db.execute("SELECT response FROM command_turns WHERE status='done' AND prompt LIKE ? AND prompt LIKE ? ORDER BY created DESC LIMIT 1",
                            ('%' + SELF_TASK + '%', '%' + r['title'] + '%')).fetchone()
        if turn and NEEDS_CODE.search(str(turn[0] or '')):
            moved += s.db.execute("UPDATE improvement_ideas SET status='developer',updated=? WHERE id=?", (now, r['id'])).rowcount
    s.db.commit()
    if moved:
        rows = s.rows("SELECT scope,title,why,evidence FROM improvement_ideas WHERE status='developer' ORDER BY updated DESC")
        text = '# Fejlesztőre váró tételek\n\nEzeket az ORBIT megpróbálta, de programkód-módosítás kell hozzájuk.\n\n' + ''.join(
            '- **' + x['title'] + '** (' + x['scope'] + ')\n  - Miért: ' + str(x['why'])[:300] + '\n  - Alap: ' + str(x['evidence'])[:300] + '\n' for x in rows)
        try:
            (s.root / 'developer-inbox.md').write_text(text)
        except OSError:
            pass
    return moved


def activity(s, now=None):
    """What ORBIT is doing for itself right now and did in the last day: analysis, carrying out an improvement,
    learning a skill, searching, recovering from a fault, healing itself. Read from the job table, logs and audit."""
    now = now or time.time()
    schema(s)
    live = []
    for r in s.rows("""SELECT j.id,j.kind,j.status,j.prompt,j.payload,j.started,j.created,rt.label FROM jobs j LEFT JOIN job_runtime rt ON rt.job=j.id
                       WHERE j.status IN ('running','queued') ORDER BY j.status DESC,j.created LIMIT 40"""):
        payload = json.loads(r['payload'] or '{}')
        prompt = str(r['prompt'] or '').replace('[ORBIT-RUN]', '').lstrip()
        if payload.get('task') == 'self_improve':
            what, text = 'Ötletelés', 'Fejlesztési lehetőségek keresése · ' + str(payload.get('scope') or 'orbit')
        elif prompt.startswith(SELF_TASK):
            what, text = 'Fejlesztés', prompt[len(SELF_TASK):].split(' Cél:')[0].strip(' :')[:160]
        elif payload.get('transient_retry') or payload.get('recovery_attempt') or payload.get('resumed') or payload.get('planner_retry'):
            what, text = 'Hibakezelés', 'Újrapróbálás hiba után · ' + prompt.split('\n')[-1][:120]
        else:
            continue
        live.append(dict(kind=what, text=text, state='most fut' if r['status'] == 'running' else 'sorban áll', detail=str(r['label'] or ''), at=r['started'] or r['created']))
    recent = []
    for r in s.rows("SELECT kind,label,details,created FROM job_log WHERE created>=? AND kind IN (%s) ORDER BY id DESC LIMIT 40" % ','.join('?' * len(ACTIVITY)),
                    (now - 86400, *ACTIVITY)):
        recent.append(dict(kind=ACTIVITY[r['kind']], text=str(r['label'] or '')[:160], at=r['created']))
    audited = s.rows("SELECT label,created,detail FROM command_audit WHERE created>=? AND label IN (%s) ORDER BY created DESC LIMIT 30" % ','.join('?' * len(AUDIT)),
                     (now - 86400, *AUDIT)) if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='command_audit'").fetchone() else []
    for r in audited:
        recent.append(dict(kind='Tanulás' if 'tanul' in r['label'].lower() or 'jegyzett' in r['label'].lower() else 'Megértés' if 'megért' in r['label'].lower() else 'Skill',
                           text=(r['label'] + (' · ' + str(r['detail'])[:120] if r['detail'] else ''))[:200], at=r['created']))
    try:
        import self_heal
        for e in self_heal.state(s).get('events', []):
            if now - e.get('at', 0) < 86400:
                recent.append(dict(kind='Önjavítás', text=str(e.get('text'))[:200], at=e['at']))
    except Exception:
        pass
    for r in s.rows("SELECT title,updated FROM improvement_ideas WHERE status='done' AND updated>=? ORDER BY updated DESC LIMIT 10", (now - 86400,)):
        recent.append(dict(kind='Megoldva', text=r['title'], at=r['updated']))
    recent.sort(key=lambda x: -x['at'])
    merged = []
    for item in recent:  # the same line repeated in a row is one entry with a count
        if merged and merged[-1]['kind'] == item['kind'] and merged[-1]['text'] == item['text']:
            merged[-1]['times'] = merged[-1].get('times', 1) + 1
        else:
            merged.append(item)
    return dict(live=live, recent=merged[:30])


def listing(s, now=None):
    schema(s)
    now = now or time.time()
    resolve(s, now)
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    name_of = lambda k: 'ORBIT app' if k == 'orbit' else names.get(k, k)
    rows = s.rows("SELECT * FROM improvement_ideas WHERE status IN ('new','accepted','developer') OR status='done' AND updated>=? ORDER BY updated DESC LIMIT 300", (now - SHOW_DONE,))
    runs = {r['scope']: r['analysed'] for r in s.rows('SELECT scope,analysed FROM improvement_runs')}
    working = {str(r['prompt']) for r in s.rows("SELECT prompt FROM jobs WHERE kind='command' AND status IN ('queued','running')")}
    ideas, done, seen, developer = [], [], {}, []
    for r in rows:
        if r['scope'] not in ('orbit', 'universe') and r['scope'] not in names:
            continue      # the project is deleted or in the Kuka: its ideas are neither shown nor carried out
        idea = dict(r, status_label=LABELS[r['status']], scope_name=name_of(r['scope']))
        if r['status'] == 'done':
            done.append(idea)
            continue
        if r['status'] == 'developer':
            developer.append(idea)
            continue
        # The same problem measured in ORBIT and in a project is one card, not two.
        same = (COUNT.sub('', r['title']) if r['source'] == 'measured' else r['id'], str(r['evidence'])[:80] if r['source'] == 'measured' else '')
        if same in seen:
            seen[same]['also'] = seen[same].get('also', 0) + 1
            continue
        seen[same] = idea
        idea['urgency'] = urgency(s, idea, now)
        idea['urgency_label'] = URGENCY_LABEL[idea['urgency']]
        idea['working'] = any(idea['title'] in p for p in working)
        ideas.append(idea)
    ideas.sort(key=lambda i: (not i['working'], URGENCY[i['urgency']], i['status'] != 'accepted', -i['updated']))
    groups = {}
    for idea in ideas:
        groups.setdefault(idea['scope'], []).append(idea)
    order = ['orbit'] + sorted((k for k in groups if k != 'orbit'), key=name_of)
    return dict(ideas=ideas, done=done, developer=developer, activity=activity(s, now), counts={k: sum(i['urgency'] == k for i in ideas) for k in URGENCY},
                groups=[dict(scope=k, name=name_of(k), analysed=runs.get(k), ideas=groups[k]) for k in order if k in groups],
                pending=bool(s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='self_improve'").fetchone()),
                scopes=[dict(scope=x, name='ORBIT app' if x == 'orbit' else names.get(x, x)) for x in scopes(s)])


def request_text(idea, names):
    where = 'az ORBIT appban' if idea['scope'] == 'orbit' else 'a(z) „' + names.get(idea['scope'], idea['scope']) + '” projektben'
    # A task, not a rule: the assistant read the old wording ("look at it and prepare") as a standing instruction.
    return ('Valósítsd meg most ezt a fejlesztést ' + where + ': ' + idea['title'] + '. Cél: ' + idea['why'] + ' Mért alap: ' + idea['evidence'] +
            ' Lépések: olvasd be az érintett projektet, beállítást vagy fájlt, végezd el a változtatást a megfelelő műveletekkel, majd írd meg röviden, mit változtattál és hogyan ellenőrizhető. '
            'Ami pénzt, publikálást, fiókot vagy kulcsot érint, azt ne hajtsd végre, csak írd le, mit kell nekem megtennem.')


def settings(s):
    schema(s)
    s.db.execute('CREATE TABLE IF NOT EXISTS improvement_settings(key TEXT PRIMARY KEY,value TEXT)')
    return {r['key']: r['value'] for r in s.rows('SELECT key,value FROM improvement_settings')}


def set_auto(s, on):
    settings(s)
    s.db.execute("INSERT OR REPLACE INTO improvement_settings VALUES('auto',?)", ('on' if on else 'off',))
    s.db.commit()
    return dict(auto=bool(on))


def auto_apply(s, now=None):
    """With auto mode on: one proposal a night goes to the main chat as a task and is carried out."""
    import datetime
    now = now or time.time()
    cfg = settings(s)
    if cfg.get('auto') != 'on' or not idle(s, now):
        return False
    # Free time is used for this by day as well, a few times a day with a pause in between, never one after another.
    night = datetime.date.fromtimestamp(now).isoformat()
    try:
        tally = json.loads(cfg.get('auto_tally') or '{}')
    except ValueError:
        tally = {}
    if tally.get('day') != night:
        tally = dict(day=night, count=0, at=0)
    # Past the day's count a free machine keeps going at half pace (owner, 11 Nov), up to three times the count.
    gap = APPLY_GAP * (2 if tally['count'] >= APPLY_PER_DAY else 1)
    if tally['count'] >= APPLY_PER_DAY * 3 or now - tally.get('at', 0) < gap:
        return False
    if s.db.execute("SELECT 1 FROM jobs WHERE kind='command' AND status IN ('queued','running') AND prompt LIKE ?", ('%' + SELF_TASK + '%',)).fetchone():
        return False
    if s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='self_improve'").fetchone():
        return False
    waiting = [i for i in listing(s, now)['ideas'] if i['status'] == 'new']
    if not waiting:
        return False
    row = waiting[0]  # the list is already in order of urgency
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    import commander
    commander.enqueue(s, 'universe', request_text(dict(row), names), global_mode=True, origin='improve:' + row['id'])
    s.db.execute("UPDATE improvement_ideas SET status='accepted',updated=? WHERE id=?", (now, row['id']))
    s.db.execute("INSERT OR REPLACE INTO improvement_settings VALUES('last_auto',?)", (night,))
    tally.update(count=tally['count'] + 1, at=now)
    s.db.execute("INSERT OR REPLACE INTO improvement_settings VALUES('auto_tally',?)", (json.dumps(tally),))
    s.db.commit()
    return True


def dispatch(s, op, args=None):
    args = args or {}
    schema(s)
    if op == 'improve_list':
        return dict(listing(s), auto=settings(s).get('auto') == 'on')
    if op == 'improve_lessons':
        import story_quality
        story_quality.schema(s)
        names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
        return dict(lessons=[dict(r, project_name=names.get(r['project'], r['project'])) for r in s.rows('SELECT id,project,lesson,source,created FROM story_lessons ORDER BY created DESC LIMIT 60')])
    if op == 'improve_lesson_forget':
        import story_quality
        story_quality.schema(s)
        s.db.execute('DELETE FROM story_lessons WHERE id=?', (str(args.get('id') or ''),))
        s.db.commit()
        return dict(ok=True)
    if op == 'improve_auto':
        return set_auto(s, bool(args.get('on')))
    if op == 'improve_run':
        scope = args.get('scope') or 'orbit'
        if scope not in scopes(s) and not s.db.execute('SELECT 1 FROM projects WHERE id=?', (scope,)).fetchone():
            raise ValueError('Ismeretlen projekt.')
        if s.db.execute("SELECT 1 FROM jobs WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task')='self_improve' AND json_extract(payload,'$.scope')=?", (scope,)).fetchone():
            return dict(queued=True, message='Ez az elemzés már fut.')
        agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
        if not agent:
            raise ValueError('Nincs háttérügynök az elemzéshez.')
        # The measured proposals appear at once; the model's ideas follow when the model is free.
        added = save(s, scope, rule_ideas(scope, facts(s, scope)), 'measured')
        s.enqueue(agent[0], 'Önfejlesztő elemzés · ' + scope, 'assist', payload=dict(task='self_improve', scope=scope, local_only=True))
        return dict(queued=True, added=added, message='Elemzés elindult; a mért javaslatok már látszanak, a modell ötletei néhány perc múlva jönnek.')
    if op == 'improve_set':
        status = args.get('status')
        if status not in STATES:
            raise ValueError('Ismeretlen állapot.')
        row = s.db.execute('SELECT * FROM improvement_ideas WHERE id=?', (args.get('id'),)).fetchone()
        if not row:
            raise ValueError('A javaslat nem található.')
        s.db.execute('UPDATE improvement_ideas SET status=?,updated=? WHERE id=?', (status, time.time(), row['id']))
        s.db.commit()
        result = dict(id=row['id'], status=status)
        if status == 'accepted':
            names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
            result['request'] = request_text(dict(row), names)
        return result
    raise ValueError('Ismeretlen önfejlesztési művelet.')
