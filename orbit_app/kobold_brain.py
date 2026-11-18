"""A smarter Kobold link: share what is needed, ask when stuck, report what really worked.

All of it rides on kobold-orbit/1 as it is (info, question, answer, skill, receipt), so Kobold reads it today:
  * IGÉNY (info, category "warning", tags ["igeny", "needs"]): once a day, what fails repeatedly in ORBIT now. Kobold
    answers it with the skills or lessons that fit; ORBIT does the same with Kobold's needs, and sends nothing else.
  * SEGÍTSÉG (question, origin "assistant"): a failure seen at least twice is asked about once a week, with its context.
    The answer becomes an improvement card, so ORBIT's own improvement loop acts on it.
  * Mért visszajelzés (receipt "worked"/"failed"): what ORBIT took over from Kobold is reported with real counts.
Nothing here limits either side (owner, 11 Nov): it decides only what is worth sending.
"""
import hashlib
import json
import re
import time

NEED_EVERY = 86400
HELP_AGAIN = 7 * 86400
FEEDBACK_EVERY = 86400
NEED_TAGS = ('igeny', 'needs')
NEED_MARK = re.compile(r'^\s*IG[EÉ]NY\b', re.I)
HELP_MARK = 'SEGÍTSÉG:'


def schema(s):
    s.db.executescript('''CREATE TABLE IF NOT EXISTS kobold_help(key TEXT PRIMARY KEY,question TEXT,area TEXT,problem TEXT,asked REAL,
        answer TEXT,answered REAL);
        CREATE TABLE IF NOT EXISTS kobold_feedback(message TEXT PRIMARY KEY,sent REAL,uses INTEGER,ok INTEGER);''')
    s.db.commit()


# 1. Needs ------------------------------------------------------------------------------------------------------------
def needs(s, now=None, days=3, limit=6):
    """What failed at least twice in the last days, per place and error (model-free, numbers and ids folded)."""
    from self_improve import _error_key
    now = now or time.time()
    rows = s.rows("""SELECT j.kind,coalesce(a.name,'') agent,coalesce(p.name,j.project) project,j.error,j.prompt FROM jobs j
                     LEFT JOIN agents a ON a.id=j.agent LEFT JOIN projects p ON p.id=j.project
                     WHERE j.status='failed' AND coalesce(j.finished,j.created)>? AND j.error!=''""", (now - days * 86400,))
    groups = {}
    for r in rows:
        key = (r['project'], r['agent'], _error_key(r['error']))
        g = groups.setdefault(key, dict(project=r['project'], agent=r['agent'], kind=r['kind'], error=str(r['error']).split('\n')[0][:300],
                                       task=re.sub(r'\[ORBIT-RUN\]\s*', '', str(r['prompt'] or ''))[:220], count=0))
        g['count'] += 1
    found = sorted((g for g in groups.values() if g['count'] >= 2), key=lambda g: -g['count'])[:limit]
    for g in found:
        g['key'] = hashlib.sha256('|'.join((g['project'], g['agent'], _error_key(g['error']))).encode()).hexdigest()[:16]
        g['area'] = g['project'] + (' · ' + g['agent'] if g['agent'] else '')
    return found


def share_needs(s, now=None):
    import kobold_link as link
    now = now or time.time()
    if now - (link.setting(s, 'needs_at', 0) or 0) < NEED_EVERY:
        return None
    found = needs(s, now)
    link.set_setting(s, 'needs_at', now)
    if not found:
        return None
    digest = hashlib.sha256(json.dumps([g['key'] for g in found]).encode()).hexdigest()[:16]
    if link.setting(s, 'needs_digest') == digest:
        return None
    link.set_setting(s, 'needs_digest', digest)
    text = 'IGÉNY (ORBIT): ezek akadnak el most nálam. Ha van rá bevált skilled vagy tanulságod, küldd; ha nincs, nem kell válasz.\n' + '\n'.join(
        f'- {g["area"]}: {g["error"][:200]} ({g["count"]}× / 3 nap)' for g in found)
    return link.send(s, 'info', 'Mi akad el most az ORBIT-ban', dict(category='warning', text=text[:2000], evidence=f'{sum(g["count"] for g in found)} hibás futás, {len(found)} visszatérő hiba',
                                                                       tags=list(NEED_TAGS)))


def answer_needs(s, message):
    """Kobold's IGÉNY: only the ORBIT skills that fit a listed need go back, as replies to it; nothing when none fits."""
    import assistant_skills
    import kobold_link as link
    lines = [x.strip('-• ').strip() for x in message['body'].get('text', '').splitlines()[1:] if len(x.strip()) > 8] or [message['body'].get('text', '')]
    sent = []
    for line in lines[:8]:
        for d in assistant_skills.select(s, line, limit=2):
            full = next((x for x in assistant_skills.listing(s, True) if x['id'] == d['id']), None)
            if full and shareable(full) and d['id'] not in sent:
                link.send_skill(s, d['id'], reply_to=message['id'])
                sent.append(d['id'])
    return sent


# 2. Help when stuck ----------------------------------------------------------------------------------------------------
def ask_help(s, now=None):
    """A failure seen twice is asked about (once a week per failure), with what was being done."""
    import kobold_link as link
    schema(s)
    now = now or time.time()
    asked = 0
    for g in needs(s, now, days=2, limit=3):
        row = s.db.execute('SELECT asked FROM kobold_help WHERE key=?', (g['key'],)).fetchone()
        if row and now - row[0] < HELP_AGAIN:
            continue
        text = (f'{HELP_MARK} {g["area"]} {g["count"]}× elakadt ugyanígy: „{g["error"][:300]}”.\n'
                f'Feladat, amin dolgozott: {g["task"]}\n'
                'Mi működött nálad hasonló helyzetben? Ha van rá skilled vagy beállításod, írd le lépésekben (vagy küldd skillként).')
        sent = link.send(s, 'question', 'Segítség kell: ' + g['area'][:80], dict(text=text[:4000], origin='assistant'))
        if sent['status'] == 'sent':
            s.db.execute('INSERT OR REPLACE INTO kobold_help VALUES(?,?,?,?,?,?,?)', (g['key'], sent['id'], g['area'], g['error'], now, None, None))
            asked += 1
    s.db.commit()
    return asked


def on_answer(s, message):
    """Kobold's answer to a SEGÍTSÉG question becomes an improvement card for the place that failed."""
    schema(s)
    row = s.db.execute('SELECT * FROM kobold_help WHERE question=?', (message.get('reply_to'),)).fetchone()
    if not row:
        return False
    answer = str(message['body'].get('text', ''))[:3000]
    s.db.execute('UPDATE kobold_help SET answer=?,answered=? WHERE key=?', (answer, time.time(), row['key']))
    s.db.commit()
    import self_improve
    scope = 'orbit'
    hit = s.db.execute('SELECT id FROM projects WHERE name=?', (row['area'].split(' · ')[0],)).fetchone()
    if hit:
        scope = hit[0]
    self_improve.save(s, scope, [dict(title=('Kobold tanácsa: ' + row['area'])[:100], why='Kobold javaslata erre a visszatérő hibára: ' + answer[:500],
                                       evidence=row['problem'][:500], size='S', area='reliability')], 'kobold')
    try:
        import autopilot_hub
        autopilot_hub.note(s, scope if scope != 'orbit' else 'universe', 'Kobold-tanács', row['area'] + ': ' + answer[:300])
    except Exception:
        pass
    return True


# 3. Measured feedback ---------------------------------------------------------------------------------------------------
def usage(s, since):
    """For every skill or workshop taken from Kobold: how often it was used since `since`, and how often it went well."""
    out = {}
    for r in s.rows("SELECT id,note FROM kobold_messages WHERE direction='in' AND type='skill' AND status='adopted'"):
        note = r['note'] or ''
        project = re.search(r'ORBIT-projekt: (\S+)', note)
        skill = re.search(r'ORBIT-skill: (\S+)', note)
        if project:
            got = s.db.execute("SELECT count(*),sum(status='done') FROM jobs WHERE project=? AND status IN ('done','failed') AND coalesce(finished,created)>?",
                               (project.group(1), since)).fetchone()
        else:
            sid = skill.group(1) if skill else None
            if not sid:
                sid = 'kobold-' + json.loads(s.db.execute('SELECT data FROM kobold_messages WHERE id=?', (r['id'],)).fetchone()[0])['body'].get('skill_id', '')
            # A skill listed for a turn is not yet used: only turns about the skill's subject count (11 Nov: the SpaceX skill was
            # listed beside nine failed Autopilot turns about something else and got a wrong "failed").
            from assistant_skills import similarity, words, listing
            d = next((x for x in listing(s) if x['id'] == sid), None)
            about = words((d or {}).get('title', '') + ' ' + (d or {}).get('description', '') + ' ' + ' '.join((d or {}).get('tags') or []))
            jobs = s.rows("SELECT status,prompt FROM jobs WHERE status IN ('done','failed') AND coalesce(finished,created)>? AND payload LIKE ?",
                          (since, '%"id": "' + sid + '"%'))
            hits = [j for j in jobs if about and similarity(words(j['prompt']), about) >= .2]
            got = (len(hits), sum(j['status'] == 'done' for j in hits))
        if got and got[0]:
            out[r['id']] = (int(got[0]), int(got[1] or 0))
    return out


def report_feedback(s, now=None):
    import kobold_link as link
    schema(s)
    now = now or time.time()
    if now - (link.setting(s, 'feedback_at', 0) or 0) < FEEDBACK_EVERY:
        return 0
    since = link.setting(s, 'feedback_at', 0) or now - FEEDBACK_EVERY
    link.set_setting(s, 'feedback_at', now)
    sent = 0
    for mid, (uses, ok) in usage(s, since).items():
        status = 'worked' if ok * 2 >= uses else 'failed'
        link.receipt(s, mid, status, f'Az ORBIT-ban az elmúlt napban {uses}× futott, ebből {ok} sikeres ({round(100 * ok / uses)}%).')
        s.db.execute('INSERT OR REPLACE INTO kobold_feedback VALUES(?,?,?,?)', (mid, now, uses, ok))
        sent += 1
    s.db.commit()
    return sent


# 7. Only what is ORBIT's own and proven goes out --------------------------------------------------------------------------
def shareable(d):
    """Library skills come from the web (Kobold can fetch them itself), Kobold's own come back from Kobold: neither is resent.
    A method Kobold reported as failing is not resent until it has a new version."""
    sid = str(d.get('id', ''))
    return not (d.get('source') == 'library' or sid.startswith('lib-') or sid.startswith('kobold-'))


def tick(s, now=None):
    now = now or time.time()
    for step in (share_needs, ask_help, report_feedback):
        try:
            step(s, now)
        except Exception as error:     # one failing step never stops the link
            import kobold_link as link
            link.set_setting(s, 'brain_error', f'{step.__name__}: {str(error)[:300]}')


def on_message(s, message):
    kind, body = message['type'], message.get('body') or {}
    if kind == 'info' and (set(body.get('tags') or []) & set(NEED_TAGS) or NEED_MARK.search(body.get('text', ''))):
        return answer_needs(s, message)
    if kind == 'answer':
        return on_answer(s, message)
    return None


def overview(s):
    schema(s)
    return dict(needs=needs(s), help=[dict(r) for r in s.rows('SELECT area,problem,asked,answer,answered FROM kobold_help ORDER BY asked DESC LIMIT 10')],
                feedback=[dict(r) for r in s.rows('SELECT * FROM kobold_feedback ORDER BY sent DESC LIMIT 10')])
