"""The Autopilot over the whole app: the owner's standing goals, everything that is running, and a supervisor that
uses idle time to move those goals forward.

A goal is a sentence from the owner ("dolgozz a saját animációkon", "javítsd a hibákat"). In every idle stretch the
supervisor takes the goal that waited longest and does one concrete thing for it: a new own animation, a self-repair
round, or a task handed to the main assistant, which can plan, research, learn skills and start missions. Everything
it starts is an ordinary job, so it shows up in the live list. It never spends money, publishes, contacts people or
handles accounts; such steps are written down for the owner instead."""
import json
import re
import time
import uuid

KINDS = dict(own_video='Saját animáció', repair='Hibajavítás és fejlesztés', general='Általános cél', projects='Projektek folyamatos fejlesztése', skills='Skillek tanulása')
GAP = dict(own_video=2700, repair=1800, general=3600, projects=3600, skills=3600)   # pause before the same goal gets its next step
PER_DAY = dict(own_video=16, repair=24, general=12, projects=16, skills=8)
DEFAULT_GOAL = 'Dolgozz folyamatosan a projektjeimen: nézd át őket sorban, és minden körben javíts rajtuk valamit (ügynök-utasítás, modell, skill, API, hiányzó ügynök, automatizáció).'
PACE = 120
FREE_FACTOR = 3   # past the day's count a free machine keeps working, at half pace, up to this many times the count
GOAL_MARK = 'Autopilóta-cél:'
STANDING = (r'\b(dolgozz|foglalkozz|fejleszd|fejlessz|haladj|tanulj|javitsd|figyeld|keszits\w*|gyarts\w*)\b.{0,140}'
            r'\b(ejszaka|ejjel|folyamatosan|magadtol|onalloan|a hatterben|amig nem szolok|mostantol|minden nap|naponta|szabadidodben|kozben)\b'
            r'|\b(ejszaka|ejjel|folyamatosan|mostantol|a hatterben)\b.{0,60}\b(dolgozz|foglalkozz|fejleszd|fejlessz|haladj|javitsd)\b')
_pace = dict(at=0)


def schema(s):
    s.db.execute('''CREATE TABLE IF NOT EXISTS autopilot_goals(id TEXT PRIMARY KEY,text TEXT,kind TEXT,enabled INTEGER,created REAL,
                    last_run REAL,runs INTEGER,day TEXT,today INTEGER,last_note TEXT)''')
    s.db.execute('CREATE TABLE IF NOT EXISTS autopilot_settings(key TEXT PRIMARY KEY,value TEXT)')
    s.db.execute('CREATE TABLE IF NOT EXISTS autopilot_log(id INTEGER PRIMARY KEY,project TEXT,kind TEXT,text TEXT,at REAL)')
    s.db.commit()


def kind_of(text):
    from model_router import normalized
    p = normalized(text)
    # "tanulj új skilleket / munkamódszereket a projektjeimhez": the skill scout, not the planner (it failed 9 of 9 on 11 Nov).
    if re.search(r'\bskill\w*|munkamodszer\w*|kepesseg\w*', p) and re.search(r'tanul\w*|sajatits\w*|elsajatit\w*|keres\w*|gyujt\w*|import\w*|szerez\w*', p):
        return 'skills'
    # "a legkisebb hibával generáljon" is about making videos; only an asked-for repair (javítsd, debug) is repair work.
    studio = re.search(r'animaci\w*|sajat video\w*|rajzfilm\w*|stickman|tortenet\w*|studio\w*', p)
    if studio and (re.search(r'general\w*|keszit\w*|keszits\w*|gyart\w*|teszt\w*', p) or not re.search(r'debug\w*|javit\w*|hibakeres\w*', p)):
        return 'own_video'
    if re.search(r'\bhib\w*|debug\w*|javit\w*|stabil\w*|megbizhato\w*|onfejl\w*|onjavit\w*', p):
        return 'repair'
    return 'general'


def standing_goal(prompt):
    """A request to keep working on something unattended, as opposed to a single task or a question."""
    from model_router import normalized
    p = normalized(prompt)
    return bool(len(p) <= 700 and not p.rstrip().endswith('?') and re.search(STANDING, p))


def note(s, project, kind, text):
    """What the Autopilot did in a project, for the per-project view."""
    schema(s)
    s.db.execute('INSERT INTO autopilot_log(project,kind,text,at) VALUES(?,?,?,?)', (project or 'universe', kind, str(text)[:400], time.time()))
    s.db.commit()


def project_log(s, limit=6):
    schema(s)
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    out = {}
    for r in s.rows('SELECT project,kind,text,at FROM autopilot_log ORDER BY id DESC LIMIT 200'):
        items = out.setdefault(r['project'], [])
        if len(items) < limit:
            items.append(dict(kind=r['kind'], text=r['text'], at=r['at']))
    return [dict(project=k, name=names.get(k, 'ORBIT'), items=v) for k, v in sorted(out.items(), key=lambda kv: -kv[1][0]['at'])]


def mode(s):
    schema(s)
    row = s.db.execute("SELECT value FROM autopilot_settings WHERE key='mode'").fetchone()
    return (row[0] if row else 'on') == 'on'


def set_mode(s, on):
    schema(s)
    s.db.execute("INSERT OR REPLACE INTO autopilot_settings VALUES('mode',?)", ('on' if on else 'off',))
    s.db.commit()
    return dict(mode=bool(on))


def goals(s):
    schema(s)
    return [dict(r, enabled=bool(r['enabled']), kind_label=KINDS.get(r['kind'], r['kind'])) for r in s.rows('SELECT * FROM autopilot_goals ORDER BY created')]


def goal_add(s, text):
    schema(s)
    text = ' '.join(str(text or '').split())[:600]
    if len(text) < 8:
        raise ValueError('Írd le egy mondatban, min dolgozzon az Autopilóta.')
    if re.search(r'sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{25,}', text):
        raise ValueError('A cél nem tartalmazhat kulcsot.')
    same = s.db.execute('SELECT id FROM autopilot_goals WHERE text=?', (text,)).fetchone()
    if same:
        s.db.execute('UPDATE autopilot_goals SET enabled=1 WHERE id=?', (same[0],))
        s.db.commit()
        return dict(id=same[0], existing=True)
    gid = uuid.uuid4().hex[:12]
    s.db.execute('INSERT INTO autopilot_goals VALUES(?,?,?,?,?,?,?,?,?,?)', (gid, text, kind_of(text), 1, time.time(), 0, 0, '', 0, ''))
    s.db.commit()
    return dict(id=gid, kind=kind_of(text), existing=False)


def goal_set(s, gid, enabled):
    schema(s)
    if not s.db.execute('UPDATE autopilot_goals SET enabled=? WHERE id=?', (int(bool(enabled)), str(gid))).rowcount:
        raise ValueError('Ismeretlen cél.')
    s.db.commit()
    return dict(id=gid, enabled=bool(enabled))


def goal_remove(s, gid):
    schema(s)
    if not s.db.execute('DELETE FROM autopilot_goals WHERE id=?', (str(gid),)).rowcount:
        raise ValueError('Ismeretlen cél.')
    s.db.commit()
    return dict(removed=gid)


def find(s, text):
    """The goal the owner means by a few words (for stopping or removing one from the chat)."""
    from assistant_skills import similarity, words
    asked = words(text or '')
    scored = sorted(((similarity(asked, words(g['text'])), g) for g in goals(s)), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] >= .3 else None


STEP_LABEL = dict(hook='ötlet', art='szereplők', script='forgatókönyv', continuity='folytonosság', sound='hang', render='animáció')


def live(s):
    """Everything running or queued in the whole app, one line per piece of work (a six-step video is one line)."""
    rows = s.rows("""SELECT j.id,j.kind,j.status,j.prompt,j.payload,j.started,j.created,j.project,a.name agent,p.name project_name,rt.label
                     FROM jobs j LEFT JOIN agents a ON a.id=j.agent LEFT JOIN projects p ON p.id=j.project LEFT JOIN job_runtime rt ON rt.job=j.id
                     WHERE j.status IN ('running','queued') ORDER BY j.created LIMIT 120""")
    groups = {}
    tables = bool(s.db.execute("SELECT 1 FROM sqlite_master WHERE name='orbit_mission_runs'").fetchone())
    for r in rows:
        payload = json.loads(r['payload'] or '{}')
        prompt = str(r['prompt'] or '').replace('[ORBIT-RUN]', '').strip()
        last = prompt.split('\n')[-1][:140]
        if payload.get('story_step'):
            key, what, title = 'run:' + str(payload.get('run')), 'Saját animáció', str(payload.get('story_brief') or last)[:140]
        elif payload.get('auto_step'):
            key, what, title = 'run:' + str(payload.get('run')), 'Klip Shorts', last
        elif r['kind'] in ('mission_agent', 'mission_dispatch'):
            run = str(payload.get('mission_run') or payload.get('run') or r['id'])
            named = s.db.execute('SELECT m.name FROM orbit_mission_runs x JOIN orbit_missions m ON m.id=x.mission WHERE x.id=?', (run,)).fetchone() if tables else None
            title = (named[0] if named else 'Önállóan futó munka') + (' · ' + str(payload['mission_node']) if payload.get('mission_node') else '') + (' · ' + str(r['agent']) if r['agent'] else '')
            key, what = 'mission:' + run, 'Küldetés'
        elif payload.get('task') == 'self_improve':
            key, what, title = r['id'], 'Ötletelés', 'Fejlesztési lehetőségek keresése · ' + str(payload.get('scope') or 'orbit')
        elif r['kind'] in ('command', 'command_apply', 'control_apply'):
            if GOAL_MARK in prompt:
                what, title = 'Autopilóta-lépés', prompt.split(GOAL_MARK, 1)[1].split(' Amit megtehetsz:')[0].split('. Tedd meg')[0].strip()[:140]
            elif prompt.startswith('Valósítsd meg most ezt a fejlesztést'):
                what, title = 'Fejlesztés', prompt.split(':', 1)[-1].split(' Cél:')[0].strip()[:140]
            else:
                what, title = 'Chat-kérés', prompt[:140]
            key = 'turn:' + str(payload.get('turn') or r['id'])
        elif r['kind'] == 'assist':
            continue
        else:
            key, what, title = r['id'], str(r['agent'] or r['kind']), last
        g = groups.setdefault(key, dict(kind=what, title=title, project=r['project_name'] or '', project_id=r['project'], running=False, since=r['created'], detail='', waiting=0, job=r['id']))
        if r['status'] == 'running':
            step = STEP_LABEL.get(payload.get('story_step'), '')
            g.update(running=True, job=r['id'], since=r['started'] or r['created'], detail=' · '.join(x for x in (step, str(r['label'] or '')) if x)[:160])
        else:
            g['waiting'] += 1
    out = sorted(groups.values(), key=lambda g: (not g['running'], g['since']))
    for g in out:
        g['state'] = 'most fut' if g['running'] else 'sorban áll'
    return out


def finished(s, now=None, limit=8):
    now = now or time.time()
    rows = s.rows("""SELECT a.name,a.kind,a.created,p.name project FROM artifacts a LEFT JOIN projects p ON p.id=a.project
                     WHERE a.created>=? AND a.kind IN ('video','image') AND a.name NOT LIKE 'flux-%' ORDER BY a.created DESC LIMIT ?""", (now - 86400, limit))
    return [dict(text=r['name'], kind='Videó' if r['kind'] == 'video' else 'Kép', project=r['project'] or '', at=r['created']) for r in rows]


def overview(s, now=None):
    import missions
    import self_improve
    now = now or time.time()
    listed = self_improve.listing(s, now)
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    plans = []
    for m in missions.listing(s)['missions']:
        steps = m.get('steps') or []
        current = next((st for st in steps if st['state'] in ('running', 'queued', 'waiting', 'attention')), None)
        plans.append(dict(id=m['id'], project=m['project'], project_name=names.get(m['project'], m['project']), name=m['name'], status=m['status'],
                          done=sum(st['state'] == 'done' for st in steps), total=len(steps), step=current['node'] if current else '',
                          error=(current or {}).get('error', '')[:200] if current else ''))
    listed_goals = goals(s)
    for g in listed_goals:
        g['next_in'] = next_in(g, now) if g['enabled'] else None
    return dict(mode=mode(s), live=live(s), projects=project_log(s), goals=listed_goals, missions=plans, finished=finished(s, now), recent=listed['activity']['recent'][:12],
                improve=dict(counts=listed['counts'], total=len(listed['ideas']), top=[i for i in listed['ideas'] if i['urgency'] in ('sos', 'high')][:3],
                             auto=self_improve.settings(s).get('auto') == 'on'), idle=self_improve.idle(s, now))


ABILITIES = ('Amit megtehetsz: olvasd be a projektet és az ügynökeit; írd át egy ügynök utasítását vagy modelljét agent_save művelettel, ha jobban teljesítene; '
             'tanulj meg egy szolgáltatást learn_skill-lel, ha egy API vagy adatforrás segítene; vegyél fel új segédügynököt, ha hiányzik egy szerep; '
             'indíts próbafuttatást; mentsd el, amit tanultál. A Történetműhely hat lépéses láncához (Hook, Art, Plot, Ink, Sound, Frame) új ügynököt ne köss be, '
             'azok utasítását viszont szabadon javíthatod. Ami pénzt, publikálást, fiókot, kulcsot vagy emberek megkeresését érinti, azt ne hajtsd végre, csak írd le. '
             'Ne kérdezz vissza. A végén egy-két mondatban írd meg, mit változtattál és miért.')


# The owner's direction for the animation studio (12 Nov, after two reference shorts): the Autopilot tuned the Plot agent
# six times a night towards "more movement" and the episodes got chaotic; this is what it should aim for instead.
STUDIO_DIRECTION = ('Make the next animated Shorts brainrot comedy built on one current viral trend or news moment, told as one clear, fast story: the dialogue never stops, every line moves the '
                    'story, each shot shows a drawn picture (show) of exactly what is said, the subtitle is the spoken line, and the '
                    'acting is calm and readable (the speaker gestures to the line, the listener reacts; bodies travel only when '
                    'the story needs it). Pick a topic different from the recent episode titles.')
# A rewrite that forces busy movement or a home-made output format broke the studio once (Plot, 12 Nov night).
FORCED = re.compile(r'at least (?:two|three|\d+) (?:distinct )?(?:physical )?movements|avoid static poses|output must be a json|'
                    r'force (?:at least|a minimum)|strictly forbid repeating', re.I)


TUNE_SCHEMA = {'type': 'object', 'required': ['agent', 'prompt', 'reason'], 'additionalProperties': False, 'properties': {
    'agent': {'type': 'string'}, 'prompt': {'type': 'string', 'maxLength': 2400}, 'reason': {'type': 'string', 'maxLength': 300}}}


def evidence(s, pid, limit=6):
    """What a project's agents produced and where they failed lately, short enough for a local model."""
    failed = [str(r['error'])[:200] for r in s.rows("SELECT error FROM jobs WHERE project=? AND status='failed' AND error!='' ORDER BY finished DESC LIMIT ?", (pid, limit))]
    made = [str(r['name'])[:120] for r in s.rows("SELECT name FROM artifacts WHERE project=? ORDER BY created DESC LIMIT ?", (pid, limit))]
    titles = []
    for r in s.rows("SELECT result FROM jobs WHERE project=? AND status='done' AND json_extract(payload,'$.story_step')='continuity' ORDER BY finished DESC LIMIT 4", (pid,)):
        try:
            plan = json.loads(r['result'])
            titles.append(dict(title=plan.get('title'), captions=[x.get('caption') for x in plan.get('scenes', []) if x.get('caption')][:3],
                               actions=[x.get('acting') for x in plan.get('scenes', [])][:6]))
        except (ValueError, TypeError):
            pass
    lessons = []
    try:
        import story_quality
        lessons = story_quality.lessons(s, pid, 8)
    except Exception:
        pass
    return dict(recent_failures=failed, recent_outputs=made, recent_episodes=titles, owner_lessons=lessons)


def tune(s, pid, aim, ask=None):
    """One agent of the project gets a better prompt, chosen and written by the local model from the project's own
    results. A closed answer shape, so a small model cannot wander off into reading; the change is applied here, kept
    as a revision (orbit_agent_revisions) and can be undone. Returns a short Hungarian note."""
    rows = [dict(r) for r in s.rows("SELECT * FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive) ORDER BY rowid LIMIT 12", (pid,))]
    if not rows:
        return 'Ebben a projektben nincs ügynök.'
    data = dict(aim=aim, agents=[dict(id=a['id'], name=a['name'], role=a['role'], prompt=str(a['prompt'])[:1400]) for a in rows], **evidence(s, pid))
    shape = dict(TUNE_SCHEMA, properties=dict(TUNE_SCHEMA['properties'], agent={'type': 'string', 'enum': [a['id'] for a in rows] + ['none']}))
    system = ('You improve one agent of an AI production team. Read the aim, the agents and the evidence of recent results and failures. Pick the ONE '
              'agent whose instructions, if improved, would help the aim most, and write its complete new instructions in English: keep its job and '
              'any output format it must follow, add concrete guidance that fixes what the evidence shows (story clarity, humour, pacing, '
              'trends, fewer failures). Never invent a new output format and never demand a number of body movements per shot. Never add publishing, spending, accounts or contacting people. Answer agent="none" only if nothing would help. '
              'reason: one Hungarian sentence for the owner. Return JSON only.')
    if ask is None:
        from studio import local_api
        reply = local_api('ollama', 'api/chat', {'model': 'auto', '_orbit_purpose': 'utility', '_orbit_budget': 240, 'stream': False, 'think': False, 'format': shape,
                                                 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
                                                 'options': {'num_ctx': 8192, 'num_predict': 1400, 'temperature': .3}, 'keep_alive': '5m'}, timeout=300)
        answer = json.loads(reply.get('message', {}).get('content', '{}'))
    else:
        answer = ask(system, data, shape)
    target = next((a for a in rows if a['id'] == answer.get('agent')), None)
    prompt = ' '.join(str(answer.get('prompt') or '').split())
    if not target or len(prompt) < 80:
        return 'Most nem talált olyan ügynököt, amelyen érdemes lett volna változtatni.'
    if FORCED.search(prompt) and not FORCED.search(str(target['prompt'])):
        return 'A javasolt utasítás erőltetett mozgást vagy saját kimeneti formátumot írt volna elő; nem változtattam.'
    if prompt == ' '.join(str(target['prompt']).split()):
        return 'A javasolt utasítás megegyezett a jelenlegivel; nem változtattam.'
    s.save_agent(dict(s.agent(target['id']), prompt=prompt))
    text = 'Átírtam a(z) ' + target['name'] + ' ügynök utasítását: ' + (str(answer.get('reason') or '').strip()[:200] or 'jobb eredményért.')
    note(s, pid, 'Ügynök fejlesztve', text)
    return text


def tune_job(s, job):
    payload = json.loads(job['payload'])
    note = tune(s, payload['project'], payload.get('aim') or '')
    gid = payload.get('goal')
    if gid:
        s.db.execute('UPDATE autopilot_goals SET last_note=? WHERE id=?', (note, gid))
        s.db.commit()
    return note


def queue_tune(s, goal, pid, aim):
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    if not agent:
        return None
    s.enqueue(agent[0], 'Autopilóta · ügynökfejlesztés · ' + pid, 'assist', payload=dict(task='autopilot_tune', project=pid, aim=aim[:600], goal=goal['id'], local_only=True))
    return True


def ask_assistant(s, goal, text, project='universe'):
    import commander
    commander.enqueue(s, project, '[ORBIT-RUN] ' + GOAL_MARK + ' ' + text + ' ' + ABILITIES, global_mode=True, origin='autopilot:' + goal['id'])


def user_projects(s):
    import self_improve
    skip = {'orbit', 'universe', 'orbit-business-lab'}
    return [p for p in self_improve.scopes(s) if p not in skip and not p.startswith('venture-')]


def ensure_default(s):
    """A continuous project-improvement goal exists from the start; deleting it is respected."""
    schema(s)
    if s.db.execute("SELECT value FROM autopilot_settings WHERE key='default_seeded'").fetchone():
        return
    s.db.execute("INSERT OR REPLACE INTO autopilot_settings VALUES('default_seeded','1')")
    s.db.commit()
    if not any(g['kind'] == 'projects' for g in goals(s)):
        gid = goal_add(s, DEFAULT_GOAL)['id']
        s.db.execute("UPDATE autopilot_goals SET kind='projects' WHERE id=?", (gid,))
        s.db.commit()


def step_for(s, goal, now):
    """Do one concrete thing for a goal. Returns a short Hungarian note of what was started."""
    if goal['kind'] == 'projects':
        names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
        pool = user_projects(s)
        if not pool:
            return None
        pid = pool[(goal['runs'] or 0) % len(pool)]
        queue_tune(s, goal, pid, 'Make the project "' + names.get(pid, pid) + '" produce better results with fewer failures.')
        return 'A(z) „' + names.get(pid, pid) + '” projekt ügynökeinek fejlesztése elindult.'
    if goal['kind'] == 'skills' or (goal['kind'] == 'general' and kind_of(goal['text']) == 'skills'):
        import skill_library
        text = skill_library.scout(s, now)
        note(s, 'universe', 'Skillkeresés', text)
        return text
    if goal['kind'] == 'own_video' and (goal['runs'] or 0) % 2 == 1:
        # Every other step improves the studio itself instead of only producing another episode.
        import story_animation
        pid = story_animation.project(s)
        queue_tune(s, goal, pid, 'Owner goal: ' + goal['text'] + ' ' + STUDIO_DIRECTION)
        return 'Az Animációs stúdió ügynökeinek fejlesztése elindult.'
    if goal['kind'] == 'own_video':
        import story_animation
        pid = story_animation.project(s)
        hook = story_animation.agent_ids(pid)['hook']
        if not s.db.execute('SELECT 1 FROM agents WHERE id=? AND id NOT IN (SELECT id FROM agent_archive)', (hook,)).fetchone():
            return None
        run = s.enqueue_graph(pid, hook, '[ORBIT-RUN] Készíts egy új, az eddigiektől eltérő saját animációs shortot. Az irány, amit a tulajdonos megadott: ' + goal['text'])
        note(s, pid, 'Videó indítva', 'Új saját animáció a cél alapján (' + run['run'][:8] + ').')
        return 'Új saját animáció indult (' + run['run'][:8] + ').'
    if goal['kind'] == 'repair':
        import self_improve
        if self_improve.settings(s).get('auto') != 'on':
            self_improve.set_auto(s, True)
        if self_improve.auto_apply(s, now):
            return 'A legsürgősebb fejlesztési tétel megvalósítása elindult.'
        return 'Hibakeresés indult.' if self_improve.schedule(s, now) else None
    ask_assistant(s, goal, goal['text'] + '. Tedd meg most a következő hasznos, konkrét lépést e cél felé (kutatás, skill, ügynök, küldetés, fájl).')
    return 'A fő asszisztens megkapta a következő lépést.'


def next_in(goal, now):
    """Seconds until the goal may take its next step on a free machine (0: now), None when it is done for today.
    The daily count was meant for a machine the owner uses: when ORBIT is free it goes on at half pace (owner, 11 Nov:
    "ha szabad a gép akkor sem látom hogy csinálná")."""
    import datetime
    kind = goal['kind'] if goal['kind'] in GAP else 'general'
    today = goal['today'] if goal['day'] == datetime.date.fromtimestamp(now).isoformat() else 0
    gap = GAP[kind]
    if today >= PER_DAY[kind] * FREE_FACTOR:
        return None
    if today >= PER_DAY[kind]:
        gap *= 2
    return max(0, gap - (now - (goal['last_run'] or 0)))


def tick(s, now=None):
    """Called every few seconds by the scheduler. In an idle stretch, one step for the goal that waited longest."""
    import datetime
    import self_improve
    now = now or time.time()
    if now - _pace['at'] < PACE:
        return False
    _pace['at'] = now
    if not mode(s):
        return False
    ensure_default(s)
    if not self_improve.idle(s, now):
        return False
    day = datetime.date.fromtimestamp(now).isoformat()
    for goal in sorted((g for g in goals(s) if g['enabled']), key=lambda g: g['last_run'] or 0):
        today = goal['today'] if goal['day'] == day else 0
        wait = next_in(goal, now)
        if wait is None or wait > 0:
            continue
        try:
            note = step_for(s, goal, now)
        except ValueError as error:
            note = 'Nem indult: ' + str(error)[:160]
        s.db.execute('UPDATE autopilot_goals SET last_run=?,runs=runs+?,day=?,today=?,last_note=? WHERE id=?',
                     (now, int(bool(note) and not str(note).startswith('Nem indult')), day, today + 1, note or 'Most nem volt mit indítani.', goal['id']))
        s.db.commit()
        if note and not note.startswith('Nem indult'):
            return True
    return False


def act(s, action):
    """The main assistant's handle on the Autopilot: {"type":"autopilot","op":...}."""
    op = action.get('op')
    if op == 'mode':
        return set_mode(s, action.get('on') is not False)
    if op == 'goal_add':
        return goal_add(s, action.get('text'))
    if op in ('goal_remove', 'goal_pause', 'goal_resume'):
        goal = next((g for g in goals(s) if g['id'] == action.get('id')), None) or find(s, action.get('text'))
        if not goal:
            raise ValueError('Nem találom ezt a célt az Autopilóta céljai között.')
        return goal_remove(s, goal['id']) if op == 'goal_remove' else goal_set(s, goal['id'], op == 'goal_resume')
    raise ValueError('Ismeretlen Autopilóta-művelet.')


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'autopilot_overview':
        return overview(s)
    if op == 'autopilot_mode':
        return set_mode(s, bool(args.get('on')))
    if op == 'autopilot_goal_add':
        return goal_add(s, args.get('text'))
    if op == 'autopilot_goal_set':
        return goal_set(s, args.get('id'), args.get('enabled'))
    if op == 'autopilot_goal_remove':
        return goal_remove(s, args.get('id'))
    raise ValueError('Ismeretlen Autopilóta-művelet.')
