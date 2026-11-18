"""What ORBIT is doing right now, in every project (owner, 12 Nov: "állandó tevékenység figyelő a fő chatben").

One cheap read for the main chat's activity strip: running and queued jobs of all projects with their project, agent,
a short title, the latest stage line and how long they have been running, plus the active goal automations.
Reached through project_app (activity_now), which the native shell already lets through."""
import json
import re
import time

TASKS = {'clip_song': 'Zene elemzése', 'clip_think': 'A Rendező tervez', 'clip_concepts': 'Új koncepciók', 'clip_images': 'Klip-képek rajzolása',
         'clip_locations': 'Helyszínkeresés', 'self_improve': 'Önfejlesztő elemzés', 'autopilot_tune': 'Ügynök finomhangolása',
         'trading_agents_run': 'TradingAgents-elemzés', 'trading_agents_install': 'TradingAgents telepítése', 'email_briefing': 'Levelek átnézése',
         'memory_learn': 'Memória tanulása', 'memory_index': 'Memória indexelése', 'kobold_learn': 'Kobold-tanulás', 'model_benchmark': 'Modellmérés'}
STEPS = {'hook': 'Ötlet', 'art': 'Szereplők', 'script': 'Forgatókönyv', 'continuity': 'Ellenőrzés', 'sound': 'Hang', 'render': 'Animáció'}


def title(job, payload):
    task = payload.get('task')
    if task in TASKS:
        return TASKS[task] + (' · ' + payload['ticker'] if payload.get('ticker') else '')
    if payload.get('story_step'):
        return 'Animáció · ' + STEPS.get(payload['story_step'], payload['story_step'])
    text = re.sub(r'\[ORBIT-RUN\]\s*', '', str(job['prompt'] or '')).strip()
    text = re.sub(r'^A folyamat közös célja:\s*', '', text)
    return (text.split('\n')[0][:70] or job['kind'] or 'Munka')


def snapshot(s, now=None):
    now = now or time.time()
    names = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM projects')}
    agents = {r['id']: r['name'] for r in s.rows('SELECT id,name FROM agents')}
    rows = s.rows("SELECT id,project,agent,kind,status,prompt,created,started,payload FROM jobs WHERE status IN ('running','queued') "
                  "ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, coalesce(started,created) LIMIT 40")
    items = []
    for r in rows:
        try:
            payload = json.loads(r['payload'] or '{}')
        except ValueError:
            payload = {}
        # A story run is six chained jobs: only its running step and the first waiting one are worth a line.
        stage = s.db.execute('SELECT label FROM job_log WHERE job=? ORDER BY created DESC LIMIT 1', (r['id'],)).fetchone()
        items.append(dict(id=r['id'], status=r['status'], project=names.get(r['project'], r['project'] or ''), agent=agents.get(r['agent'], ''),
                          title=title(r, payload), stage=(stage[0] if stage else '')[:120], run=payload.get('run'),
                          seconds=round(now - (r['started'] or r['created'] or now)) if r['status'] == 'running' else round(now - (r['created'] or now))))
    seen, compact = set(), []
    for it in items:
        if it['run'] and it['status'] == 'queued' and it['run'] in seen:
            continue      # the later steps of a chain that is already shown
        if it['run']:
            seen.add(it['run'])
        compact.append(it)
    goals = []
    try:
        for a in s.rows("SELECT name,project,config FROM automations WHERE enabled=1 AND archived=0"):
            cfg = json.loads(a['config'] or '{}')
            goals.append(dict(name=a['name'], project=names.get(a['project'], ''), goal=(cfg.get('goal') or {}).get('target')))
    except Exception:
        pass
    running = sum(i['status'] == 'running' for i in items)
    return dict(running=running, queued=len(items) - running, items=compact[:14], automations=goals[:8], at=now)


def dispatch(s, op, args=None):
    if op == 'activity_now':
        return snapshot(s)
    raise ValueError('Ismeretlen művelet.')
