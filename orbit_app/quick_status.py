"""Instant answers to the questions asked most often in the main chat, read from the live state, no model.

"Hogy áll a shorts?", "Elkészült a videó?", "Hol tart az Autopilóta?", "Mi történt éjszaka?" waited up to minutes
for the local model while another job used it, and the answer was in the database all along. A question that asks
for an action ("készíts", "indítsd") is never answered here; it goes to the planner as before.
"""
import datetime
import json
import re
import time

ACTION = re.compile(r'\b(kuld\w*|legyen|hogyha|ha elkeszul\w*|mostantol|fejleszt\w*|szeretnem|akarom|kellene|allitsd be|automatikusan|telegram\w*|indits\w*|keszits\w*|csinalj\w*|generalj\w*|vagj\w*|modosits\w*|allitsd\w*|torold|allitsd le|start|make|create|keress\w*|irj\w*)\b')
VIDEO = re.compile(r'\b(shorts?|videot?|videok|videom|klip\w*|vagas\w*)\b')
PROGRESS = re.compile(r'\b(hogy all\w*|hol tart\w*|meddig tart|elkeszult|kesz (?:van|lett|e)|megvan|mi a helyzet|allapot\w*|halad\w*|hogy halad\w*)\b')
AUTOPILOT = re.compile(r'\bautopilot\w*|\bautopilota\w*')
NIGHT = re.compile(r'\bmi (?:tortent|volt|ujsag)\b.{0,30}\b(ejjel|ejszaka|ma|tegnap ota|amig (?:nem voltam|aludtam)|reggel ota)\b|\bmi tortent (?:ma|ejjel|ejszaka)\b')


def _norm(prompt):
    from model_router import normalized
    return re.sub(r'\s+', ' ', normalized(prompt)).strip(' .?!')


def _ago(ts):
    minutes = int((time.time() - ts) // 60)
    if minutes < 1:
        return 'most'
    if minutes < 60:
        return str(minutes) + ' perce'
    return str(minutes // 60) + ' órája'


def video_status(s, project=None):
    rows = s.rows("SELECT r.id,r.project,r.query,r.created,p.name FROM short_runs r LEFT JOIN projects p ON p.id=r.project"
                  + (" WHERE r.project=?" if project else "") + " ORDER BY r.created DESC LIMIT 2", (project,) if project else ())
    if not rows:
        return None
    from autonomous import STEPS
    labels = dict(STEPS)
    lines = []
    for run in rows:
        jobs = s.rows("SELECT status,error,result,json_extract(payload,'$.auto_step') AS step,finished FROM jobs WHERE project=? AND kind='graph' AND json_extract(payload,'$.run')=? ORDER BY created", (run['project'], run['id']))
        if not jobs:
            continue
        done = sum(j['status'] == 'done' for j in jobs)
        head = '🎬 „' + run['query'][:80] + '” (' + (run['name'] or run['project']) + ', ' + _ago(run['created']) + ' indult)'
        failed = next((j for j in jobs if j['status'] in ('failed', 'blocked') and j['error']), None)
        active = next((j for j in jobs if j['status'] == 'running'), None) or next((j for j in jobs if j['status'] == 'queued'), None)
        if done == len(jobs):
            data = s.db.execute('SELECT data FROM short_runs WHERE id=?', (run['id'],)).fetchone()
            video = (json.loads(data[0]).get('render') or {}).get('saved') if data else None
            lines.append(head + '\n   ✅ Elkészült' + (' · ' + video if video else '') + '. Az Alkotásokban megnézheted.')
        elif failed:
            lines.append(head + '\n   ⚠️ Megállt itt: ' + labels.get(failed['step'], failed['step'] or 'lépés') + ' · ' + failed['error'][:220])
        elif active:
            state = 'most ezen dolgozik' if active['status'] == 'running' else 'erre a lépésre vár'
            lines.append(head + '\n   ⏳ ' + str(done) + '/' + str(len(jobs)) + ' lépés kész · ' + state + ': ' + labels.get(active['step'], active['step'] or 'lépés'))
        else:
            lines.append(head + '\n   ' + str(done) + '/' + str(len(jobs)) + ' lépés kész.')
    return '\n\n'.join(lines) if lines else None


WORK = re.compile(r'\b(?:mi|min|mit|ki|kik) (?:\w+ ){0,3}(?:dolgozik|dolgoznak|fut|futnak|csinal|megy)\b|\bmiert (?:\w+ ){0,3}(?:var\w*|all\w*|nem (?:megy|halad\w*|mukod\w*|indul\w*))\b'
                  r'|\bai ?-?ra var\w*|\bnem tudnak mukodni\b|\bnem latom\b.{0,60}\b(?:futas\w*|halad\w*|javitas\w*|eredmeny\w*)|\bmiert van\b|\bez miert\b')


def wait_reason(s, job, running):
    """Why a queued job has not started, from the same facts the scheduler uses."""
    payload = json.loads(job['payload'] or '{}')
    parent = s.db.execute("""SELECT a.name, p.status FROM job_dependencies d JOIN jobs p ON p.id=d.parent LEFT JOIN agents a ON a.id=p.agent
                             WHERE d.job=? AND p.status!='done' LIMIT 1""", (job['id'],)).fetchone()
    if parent:
        state = dict(queued='még sorban áll', running='most dolgozik', failed='hibával megállt', cancelled='le lett állítva', blocked='megállt').get(parent[1], parent[1])
        return 'előbb ' + str(parent[0] or 'az előző lépés') + ' lépése kell, az ' + state
    retry = payload.get('retry_at') or 0
    if retry > time.time():
        return 'újrapróbálja ' + str(int(retry - time.time())) + ' mp múlva' + (' (' + str(payload['generation']['phase'])[:80] + ')' if isinstance(payload.get('generation'), dict) and payload['generation'].get('phase') else '')
    if running:
        return 'a gépen egyszerre egy modell dolgozik, ez a(z) ' + running[0]['who'] + ' után következik'
    return 'indulásra kész, másodperceken belül elindul'


def work_status(s):
    """What is running and what waits on what, from the job table. No model is asked, so nothing is invented."""
    rows = s.rows("""SELECT j.id,j.kind,j.status,j.prompt,j.payload,j.started,j.created,a.name agent,p.name project,rt.label
                     FROM jobs j LEFT JOIN agents a ON a.id=j.agent LEFT JOIN projects p ON p.id=j.project LEFT JOIN job_runtime rt ON rt.job=j.id
                     WHERE j.status IN ('running','queued') AND j.kind NOT IN ('command','assist') ORDER BY j.status DESC,j.created LIMIT 14""")
    who = lambda r: (str(r['agent'] or r['kind']) + (' · ' + r['project'] if r['project'] else ''))
    running = [dict(r, who=who(r)) for r in rows if r['status'] == 'running']
    queued = [r for r in rows if r['status'] == 'queued']
    if not rows:
        last = s.db.execute("""SELECT j.status,j.error,j.finished,a.name FROM jobs j LEFT JOIN agents a ON a.id=j.agent
                               WHERE j.kind NOT IN ('command','assist','control_apply') AND j.finished IS NOT NULL ORDER BY j.finished DESC LIMIT 1""").fetchone()
        tail = ''
        if last:
            tail = ' Az utolsó feladat (' + str(last[3] or 'ügynök') + ') ' + _ago(last[2]) + ' ' + dict(done='elkészült', failed='hibával állt meg: ' + str(last[1] or '')[:160], cancelled='le lett állítva', blocked='megállt egy előző lépés miatt').get(last[0], last[0]) + '.'
        return 'Most semmi nem fut és semmi nem áll sorban: az ügynökök szabadok.' + tail
    lines = []
    if running:
        lines.append('Most dolgozik:')
        lines += ['• ' + r['who'] + ' — ' + str(r['label'] or 'feldolgozás') + ' (' + _ago(r['started'] or r['created']) + ' indult)' for r in running]
    else:
        lines.append('Most éppen egyik ügynök sem dolgozik.')
    if queued:
        lines.append('Sorban áll:')
        lines += ['• ' + who(r) + ' — ' + wait_reason(s, r, running) for r in queued[:8]]
    return '\n'.join(lines)


def answer(s, prompt, project=None):
    """A Hungarian answer from live state, or None when the question needs the planner."""
    p = _norm(prompt)
    if p and len(p) <= 200 and WORK.search(p) and not re.search(r'\b(indits\w*|keszits\w*|csinalj\w*|generalj\w*|javitsd\w*|allitsd\w*)\b', p):
        return work_status(s)
    if not p or len(p) > 120 or ACTION.search(p):
        return None
    if NIGHT.search(p):
        from daily_report import compose
        now = time.time()
        since = now - 12 * 3600 if re.search(r'ejjel|ejszaka|aludtam', p) else datetime.datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return compose(s, now, since=since, title='🕘 Ez történt ' + ('éjszaka' if since == now - 12 * 3600 else 'ma') + ' · ' + datetime.datetime.fromtimestamp(now).strftime('%H:%M'))
    if AUTOPILOT.search(p) and (PROGRESS.search(p) or re.search(r'\bmit csinal\b|\bmerre\b|\bmi van\b', p)):
        from daily_report import today
        return today(s)
    if VIDEO.search(p) and PROGRESS.search(p):
        scoped = project if project and project != 'universe' and s.db.execute('SELECT 1 FROM short_runs WHERE project=? LIMIT 1', (project,)).fetchone() else None
        return video_status(s, scoped) or 'Még nem indult videógyártás. Szólj, miről készüljön Short, vagy csatolj egy saját felvételt.'
    return None
