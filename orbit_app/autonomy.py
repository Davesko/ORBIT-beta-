"""Önműködés (owner, 13 Nov): every process that starts work by itself, in one list, with one master pause.

The owner did not know the Önfejlesztés was on; almost every project has its own automation. This module only reads
each feature's own switch and flips it through that feature's own function: no feature is rewritten. The list lives on
the Autopilóta page (no new menu item, owner: "ne legyen ennyi külön fül").

The master pause ("Minden önműködő szüneteltetése") is one flag the self-starting parts check before they start new work:
the scheduler's autonomous services, scheduled automations, agent and recipe intervals, the Shorts automation, the mail
auto-reply and the design renderer. What the owner asks for still runs.
Upkeep (storage, keep-awake, self-heal, housekeeping, context) and the Kobold link keep running.
"""
import json
import time

PAUSABLE = ('schedules', 'growth', 'missions', 'self_improve', 'autopilot', 'gta6', 'etsy', 'concierge', 'memory', 'stickman')
POWER = {'analyse': 'Csak elemez, nem változtat', 'draft': 'Piszkozatot készít, nem küld', 'make': 'Tartalmat gyárt a gépen',
         'code': 'Kódot és beállítást módosít', 'send': 'Küldhet vagy feltölthet'}


def schema(s):
    s.db.execute('CREATE TABLE IF NOT EXISTS autonomy_settings(key TEXT PRIMARY KEY,value TEXT)')
    s.db.commit()


def paused(s):
    try:
        row = s.db.execute("SELECT value FROM autonomy_settings WHERE key='paused'").fetchone()
    except Exception:
        return False
    return bool(row and row[0] == '1')


def set_paused(s, on):
    schema(s)
    s.db.execute("INSERT OR REPLACE INTO autonomy_settings VALUES('paused',?)", ('1' if on else '0',))
    s.db.execute("INSERT OR REPLACE INTO autonomy_settings VALUES('paused_at',?)", (str(time.time()) if on else '',))
    s.db.commit()
    return dict(paused=bool(on))


def table(s, name):
    return bool(s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def entry(id_, group, name, what, power, on, toggle=True, last=None, next_=None, note='', page=None):
    return dict(id=id_, group=group, name=name, what=what, power=power, power_label=POWER[power], on=bool(on), toggle=toggle,
                last=last, next=next_, note=note, page=page)


def entries(s):
    """Every self-starting process with its own state, grouped: the ORBIT itself first, then each project."""
    orbit = 'Az ORBIT maga'
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    names['universe'] = orbit     # the internal store of project-free work belongs to the ORBIT itself
    out = []
    if table(s, 'autopilot_settings'):
        row = s.db.execute("SELECT value FROM autopilot_settings WHERE key='mode'").fetchone()
        out.append(entry('autopilot', orbit, 'Autopilóta', 'Szabad gépidőben lépéseket tesz a céljaidért.', 'make', row and row[0] == 'on', page='autopilot'))
    if table(s, 'improvement_settings'):
        row = s.db.execute("SELECT value FROM improvement_settings WHERE key='auto'").fetchone()
        out.append(entry('self_improve', orbit, 'Önfejlesztés', 'Szabad gépidőben megvalósít egy fejlesztési javaslatot az appon vagy egy projekten.', 'code',
                         row and row[0] == 'on'))
    if table(s, 'memory_settings'):
        row = s.db.execute("SELECT value FROM memory_settings WHERE key='learning'").fetchone()
        out.append(entry('memory', orbit, 'Memória-tanulás', 'A beszélgetéseidből tartós tényeket jegyez meg rólad.', 'analyse', not row or row[0] != 'off', page='memory'))
    if table(s, 'email_accounts'):
        for r in s.rows('SELECT id,address,auto_mode FROM email_accounts'):
            mode = r['auto_mode'] or 'off'
            out.append(entry('mail:' + r['id'], orbit, 'Automatikus levélválasz · ' + r['address'],
                             {'draft': 'Az új levelekre válaszpiszkozatot ír.', 'send': 'Az engedélyezett feladóknak magától válaszol.'}.get(mode, 'Az új levelekre magától válaszolhat.'),
                             'send' if mode == 'send' else 'draft', mode != 'off', toggle=mode != 'off',
                             note='' if mode != 'off' else 'Bekapcsolni az Email oldalon lehet, ott adod meg, kinek és mit.', page='email'))
    out.append(entry('design', orbit, 'Termékgrafikák rajzolása', 'Ha egy digitális termékhez vár rajz, a helyi képmodell megrajzolja.', 'make', True, toggle=False,
                     note='Csak akkor dolgozik, ha van rajzra váró terv; a főkapcsoló ezt is megállítja.'))
    # Each project's own automations.
    if table(s, 'automations'):
        for r in s.rows('SELECT id,project,name,enabled,next_run,last_error FROM automations WHERE archived=0 ORDER BY project,name'):
            out.append(entry('automation:' + r['id'], names.get(r['project'], 'Törölt projekt'), r['name'], 'Ütemezett automatizálás.', 'make', r['enabled'],
                             next_=r['next_run'] or None, note=(r['last_error'] or '')[:160]))
    if table(s, 'short_automation'):
        for r in s.rows('SELECT project,enabled,next_run,last_error FROM short_automation'):
            out.append(entry('shorts:' + r['project'], names.get(r['project'], 'Törölt projekt'), 'Shorts-automata', 'Magától keres klipeket és vág belőlük Shortsot.', 'make',
                             r['enabled'], next_=r['next_run'] or None, note=(r['last_error'] or '')[:160]))
    if table(s, 'growth_settings'):
        for r in s.rows('SELECT project,data FROM growth_settings'):
            try:
                on = json.loads(r['data']).get('enabled')
            except ValueError:
                on = False
            if r['project'] in names:
                out.append(entry('growth:' + r['project'], names[r['project']], 'Trendfigyelő', 'Rendszeresen letölti a keresési trendeket és témaötleteket ad.', 'analyse', on, page='growth'))
    for r in s.rows("SELECT id,project,name,interval FROM agents WHERE interval>0"):
        out.append(entry('agent:' + r['id'], names.get(r['project'], 'Törölt projekt'), 'Ügynök időzítve · ' + r['name'], f'{r["interval"]} percenként magától dolgozik.', 'make', True))
    try:
        import stickman_studio, story_animation, story_series
        spid = story_animation.project(s)
        if spid in names and s.safe_path(spid, story_series.BIBLE_FILE).is_file():
            line = stickman_studio.batch(s, spid)
            if line.get('on'):
                out.append(entry('stickman:' + spid, names[spid], 'Stickman gyártósor', ('Egymás után gyárt ' + (f"{line['count']} videót" if line.get('count') else 'videókat') + (f", {time.strftime('%H:%M', time.localtime(line['until']))}-ig" if line.get('deadline', True) else '')
                                 + {'long': f", {line['minutes']} perces fekvő", 'short': f", {line['minutes']} mp-es álló", 'mix': ', Short és hosszú váltogatva'}.get(line['kind'], '') + '; feltölteni nem tölt fel.'), 'make', True, page='app:' + spid))
    except Exception:
        pass
    import stream_watch
    for (pid,) in s.db.execute('SELECT id FROM projects WHERE kind=?', (stream_watch.KIND,)).fetchall():
        if pid in names:
            out.append(entry('stream_watch:' + pid, names[pid], 'Élő adás figyelő', 'Olvassa a figyelt streamerek nyilvános chatjét, a csúcsoknál kivágja a jelenetet; feltölteni nem tölt fel.',
                             'make', stream_watch.settings(s, pid)['enabled'], page='app:' + pid))
    try:
        import publish_plan
        cfg = publish_plan.auto_settings(s)
        out.append(entry('publish_auto', orbit, 'Automatikus ütemezés (Publikálás)', 'A legjobb pontszámú ellenőrzött videót a csatornák következő szabad időpontjára ütemezi; az ütemezett feltöltés az időpontban megy ki.',
                         'send', cfg['enabled'], page='publishing'))
    except Exception:
        pass
    if table(s, 'orbit_missions'):
        for r in s.rows("SELECT id,project,name,status,next_run FROM orbit_missions WHERE status IN ('active','running','paused')"):
            out.append(entry('mission:' + r['id'], names.get(r['project'], orbit), 'Küldetés · ' + (r['name'] or ''), 'Több lépéses cél, amit az ORBIT magától visz végig.', 'make',
                             r['status'] in ('active', 'running'), next_=r['next_run'] or None))
    return out


def toggle(s, eid, on):
    """Flip one process through its own feature's function."""
    on = bool(on)
    kind, _, rest = str(eid).partition(':')
    if kind == 'autopilot':
        import autopilot_hub
        autopilot_hub.set_mode(s, on)
    elif kind == 'self_improve':
        import self_improve
        self_improve.set_auto(s, on)
    elif kind == 'memory':
        s.db.execute("INSERT OR REPLACE INTO memory_settings VALUES('learning',?)", ('on' if on else 'off',))
        s.db.commit()
    elif kind == 'mail':
        if on:
            raise ValueError('Az automatikus választ az Email oldalon kapcsold be: ott adod meg, kinek és mit válaszoljon.')
        s.db.execute("UPDATE email_accounts SET auto_mode='off' WHERE id=?", (rest,))
        s.db.commit()
    elif kind == 'automation':
        import automations
        row = s.db.execute('SELECT project FROM automations WHERE id=?', (rest,)).fetchone()
        if not row:
            raise ValueError('Ismeretlen automatizálás.')
        automations.toggle(s, row[0], rest, on)
    elif kind == 'shorts':
        s.db.execute('UPDATE short_automation SET enabled=?,next_run=CASE WHEN ? THEN ? ELSE next_run END WHERE project=?', (int(on), int(on), time.time() + 60, rest))
        s.db.commit()
    elif kind == 'growth':
        import growth
        growth.save(s, rest, dict(enabled=on))
    elif kind == 'agent':
        if on:
            raise ValueError('Az ügynök időzítését az ügynök beállításainál adhatod meg újra.')
        s.db.execute('UPDATE agents SET interval=0 WHERE id=?', (rest,))
        s.db.commit()
    elif kind == 'stickman':
        if on:
            raise ValueError('A gyártósort a Stickman stúdió oldalán indíthatod, határidővel.')
        import stickman_studio
        stickman_studio.stop_batch(s, rest, 'Az Önműködés listáról leállítva.')
    elif kind == 'stream_watch':
        import stream_watch
        stream_watch.save(s, rest, dict(enabled=on))
    elif kind == 'publish_auto':
        import publish_plan
        publish_plan.auto_save(s, on)
    elif kind == 'mission':
        s.db.execute('UPDATE orbit_missions SET status=? WHERE id=?', ('active' if on else 'paused', rest))
        s.db.commit()
    else:
        raise ValueError('Ez a folyamat itt nem kapcsolható.')
    return overview(s)


def running(s):
    """What the ORBIT is working on right now that it started by itself (the owner's own chat requests are not listed)."""
    rows = s.rows("SELECT j.id,j.project,j.kind,j.prompt,j.started,j.payload,p.name pname FROM jobs j LEFT JOIN projects p ON p.id=j.project "
                  "WHERE j.status='running' ORDER BY j.started")
    out = []
    for r in rows:
        try:
            payload = json.loads(r['payload'] or '{}')
        except ValueError:
            payload = {}
        origin = str(payload.get('telegram_update') or '')
        auto = r['kind'] in ('scheduled', 'graph', 'short_request') or payload.get('task') in ('self_improve', 'autopilot_tune', 'memory_learn', 'kobold_learn', 'watch_fetch', 'szim_make') \
            or origin.startswith(('improve:', 'autopilot:', 'automation:')) or bool(payload.get('automation') or payload.get('auto_step') or payload.get('goal'))
        if not auto:
            continue
        import activity_now
        out.append(dict(id=r['id'], project=r['project'], project_name=r['pname'] or '', title=activity_now.title(dict(r), payload)[:120],
                        seconds=round(time.time() - (r['started'] or time.time()))))
    return out


def queued(s, limit=30):
    """What waits to start (everything the ORBIT queued: it all stops with the big stop button)."""
    out = []
    for r in s.rows("SELECT j.id,j.project,j.kind,j.prompt,p.name pname FROM jobs j LEFT JOIN projects p ON p.id=j.project WHERE j.status='queued' ORDER BY j.created LIMIT ?", (limit,)):
        out.append(dict(id=r['id'], project_name=r['pname'] or '', title=str(r['prompt'] or r['kind'])[:120]))
    return out


def watchers(s):
    """The live stream watcher in plain numbers: is it listening, to how many channels, is a download waiting."""
    import stream_watch
    out = []
    for (pid,) in s.db.execute('SELECT id FROM projects WHERE kind=?', (stream_watch.KIND,)).fetchall():
        cfg = stream_watch.settings(s, pid)
        live = stream_watch.live_state(s, pid)
        out.append(dict(project=pid, enabled=cfg['enabled'], listening=len(stream_watch.watching(dict(cfg, enabled=cfg['enabled'] and not paused(s)), live)),
                        live=sum(1 for c in live['channels'].values() if c.get('live')), listener=stream_watch.listener_alive(s, pid),
                        moments=s.db.execute("SELECT count(*) FROM stream_moments WHERE project=? AND status IN ('found','fetching','ready','producing')", (pid,)).fetchone()[0]))
    return out


def held_posts(s):
    try:
        return s.db.execute("SELECT count(*) FROM social_posts WHERE status='scheduled'").fetchone()[0]
    except Exception:
        return 0


def halt(s):
    """THE stop button: pause everything self-starting, cancel every running and waiting job, silence the live stream
    listener and hold the scheduled posts. Nothing starts again until the owner presses resume."""
    import os, signal
    set_paused(s, True)
    jobs = s.rows("SELECT id,status FROM jobs WHERE status IN ('queued','running')")
    for j in jobs:
        s.cancel(j['id'])
    listeners = 0
    try:
        import stream_watch
        for (pid,) in s.db.execute('SELECT id FROM projects WHERE kind=?', (stream_watch.KIND,)).fetchall():
            base = stream_watch.folder(s, pid)
            (base / 'listen.json').write_text(json.dumps(dict(updated=0, channels=[], videos={})))
            try:
                os.kill(int((base / 'listener.pid').read_text().strip()), signal.SIGTERM)
                listeners += 1
            except (OSError, ValueError):
                pass
    except Exception:
        pass
    try:
        import stream_watch
        stream_watch.schema(s)
        s.db.execute("UPDATE stream_moments SET status='found' WHERE status='fetching'")   # a cancelled download is tried again after the resume
    except Exception:
        pass
    s.db.commit()
    out = overview(s)
    out['message'] = ('Minden leállítva. Megszakítva: %d munka, leállított figyelő: %d, tartott ütemezett feltöltés: %d. Semmi nem indul, amíg nem nyomod meg a Folytatást.'
                      % (sum(j['status'] == 'running' for j in jobs) + sum(j['status'] == 'queued' for j in jobs), listeners, held_posts(s)))
    return out


def overview(s):
    schema(s)
    items = entries(s)
    groups, by = [], {}
    for it in items:
        if it['group'] not in by:
            by[it['group']] = dict(name=it['group'], items=[])
            groups.append(by[it['group']])
        by[it['group']]['items'].append(it)
    groups.sort(key=lambda g: (g['name'] != 'Az ORBIT maga', g['name'] == 'Törölt projekt'))
    return dict(paused=paused(s), on=sum(1 for i in items if i['on']), total=len(items), groups=groups, running=running(s), powers=POWER,
                queued=queued(s), watchers=watchers(s), held_posts=held_posts(s))


def stop_job(s, jid):
    row = s.db.execute('SELECT id FROM jobs WHERE id=? AND status IN (\'queued\',\'running\')', (jid,)).fetchone()
    if not row:
        raise ValueError('Ez a munka már nem fut.')
    s.cancel(jid)
    return overview(s)


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'autonomy_overview':
        return overview(s)
    if op == 'autonomy_halt':
        return halt(s)
    if op == 'autonomy_pause':
        set_paused(s, args.get('on') is not False)
        return overview(s)
    if op == 'autonomy_toggle':
        return toggle(s, args.get('id'), args.get('on'))
    if op == 'autonomy_stop':
        return stop_job(s, args.get('job'))
    raise ValueError('Ismeretlen önműködés-művelet.')


def act(s, a):
    """{"type":"onmukodes","op":"list|pause|resume"} from the main chat."""
    op = a.get('op')
    if op == 'pause':
        set_paused(s, True)
        return dict(message='Minden önműködő folyamatot szüneteltettem. Amit te kérsz, az ugyanúgy fut; az Autopilóta oldalon kapcsolhatod vissza.')
    if op == 'resume':
        set_paused(s, False)
        return dict(message='Az önműködő folyamatok újra a saját beállításuk szerint futnak.')
    o = overview(s)
    on = [f'{i["name"]} ({g["name"]})' for g in o['groups'] for i in g['items'] if i['on']]
    head = 'Minden önműködő szünetel. ' if o['paused'] else ''
    now = '; most fut: ' + ', '.join(r['title'] for r in o['running']) if o['running'] else ''
    return dict(message=head + (f'{len(on)} önműködő folyamat van bekapcsolva: ' + ', '.join(on) if on else 'Egy önműködő folyamat sincs bekapcsolva') + now + '.')


def route(text):
    from model_router import normalized
    import re
    p = normalized(text or '')
    if not re.search(r'onmukod|automatiz|automatik|autopilot|magatol|hatterben fut|onallo', p):
        return None
    if re.search(r'(allits|allitsd|szuneteltes|kapcsold ki|kapcsolj ki|allj le|leallit)\w*.*(minden|osszes|mind)|(minden|osszes)\w*.*(allits|szuneteltes|kapcsold ki|leallit)', p):
        return dict(type='onmukodes', op='pause')
    if re.search(r'(inditsd|kapcsold vissza|folytasd|engedd)\w*.*(minden|osszes|onmukod)', p):
        return dict(type='onmukodes', op='resume')
    if re.search(r'\bmi fut|mik futnak|mi van bekapcsolva|milyen .*(fut|be van|bekapcsolva)|mely\w* .*(fut|bekapcsolva)|listaz|mutasd|hany .*(fut|bekapcsolva)', p):
        return dict(type='onmukodes', op='list')
    return None
