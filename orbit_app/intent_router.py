"""Understanding what the owner wants made, from what each workflow does instead of from trigger words.

Clear requests are routed at once. When the wording does not settle it, the local model reads the request next to a
description of every workflow and picks one from a closed list, or says it is unsure, and then ORBIT asks one short
question instead of guessing. A correction ("nem klip, saját videó") is remembered with the earlier request, and
similar requests see it as an example from then on. A new workflow needs only a description here."""
import json
import re
import time

WORKFLOWS = {
    'own': ('Saját animáció', 'ORBIT invents, writes, voices and animates an ORIGINAL video itself in the Animációs stúdió. Nothing is cut from '
            'existing footage. A linked video, if any, is only a reference for style, tone or humour.'),
    'clip': ('Klipvágás', 'ORBIT cuts a subtitled Short out of EXISTING footage in the YouTube Shorts project: a streamer, a show, a topic to find '
             'clips for, or a linked video that is the source material itself.'),
    'gta6': ('GTA 6 clip farm', 'The separate GTA 6 clip farm project: fresh GTA 6 stream moments turned into clips. Only when GTA 6 or the clip farm is meant.'),
}
SCHEMA = {'type': 'object', 'required': ['workflow', 'reason', 'question'], 'additionalProperties': False, 'properties': {
    'workflow': {'type': 'string', 'enum': list(WORKFLOWS) + ['unsure']}, 'reason': {'type': 'string', 'maxLength': 200},
    'question': {'type': 'string', 'maxLength': 200}}}
LAUNCH = r'\b(vagj\w*|vagd\w*|kezdj\w*|kezd el|kezdd\w*|inditsd\w*|indits\w*|keszits\w*|generalj\w*|csinalj\w*|gyarts\w*|futtasd\w*|kell(?:ene)? (?:egy|nekem)|szeretnek|akarok|start|create|generate|make)\b'
MEDIA = r'\b(video\w*|shorts?\w*|animaci\w*|klip\w*|reels?|tiktok\w*|rajzfilm\w*)\b'
QUESTION = 'Saját, generált animációt készítsek, vagy meglévő felvételből vágjak Shortsot?'


def schema(s):
    s.db.execute('CREATE TABLE IF NOT EXISTS intent_examples(id INTEGER PRIMARY KEY,prompt TEXT,workflow TEXT,source TEXT,created REAL)')
    s.db.commit()


def candidate(prompt):
    """A request to make a video, as opposed to a question or a remark about one."""
    from model_router import normalized
    p = normalized(prompt)
    if not (re.search(LAUNCH, p) and re.search(MEDIA, p)):
        return False
    # "kezdj el videót gyártani: What did ancient humans do?" is an order whose topic is a question.
    return not p.rstrip().endswith('?') or bool(re.search(LAUNCH, ' '.join(p.split()[:5])))


def examples(s, prompt, limit=4):
    from assistant_skills import similarity, words
    schema(s)
    asked = words(prompt)
    scored = [(similarity(asked, words(r['prompt'])), r) for r in s.rows('SELECT prompt,workflow FROM intent_examples ORDER BY created DESC LIMIT 400')]
    return [dict(request=r['prompt'][:300], workflow=r['workflow']) for score, r in sorted(scored, key=lambda x: -x[0])[:limit] if score >= .3]


def remember(s, prompt, workflow, source='correction'):
    if workflow not in WORKFLOWS or not isinstance(prompt, str) or not 8 <= len(prompt.strip()):
        return
    schema(s)
    text = ' '.join(prompt.split())[:600]
    if not s.db.execute('SELECT 1 FROM intent_examples WHERE prompt=? AND workflow=?', (text, workflow)).fetchone():
        s.db.execute('INSERT INTO intent_examples(prompt,workflow,source,created) VALUES(?,?,?,?)', (text, workflow, source, time.time()))
        s.db.commit()


def ask_model(s, job, prompt, known):
    from studio import local_api
    system = ('Decide which ORBIT workflow the owner wants. Judge by what they want to END UP WITH, not by single words. '
              'Workflows: ' + json.dumps({k: v[1] for k, v in WORKFLOWS.items()}, ensure_ascii=False) + ' '
              'Earlier requests the owner confirmed or corrected (follow them for similar wording): ' + json.dumps(known, ensure_ascii=False) + ' '
              'When the request names no source (no streamer, show, channel, event or linked source video) and does not say it should be original or generated, it fits both: answer "unsure". Also answer "unsure" when two workflows fit equally and put ONE short Hungarian question in "question"; otherwise leave question empty. Return JSON only.')
    request = {'model': 'auto', '_orbit_purpose': 'utility', '_orbit_budget': 45, '_orbit_job': job['id'], 'stream': False, 'think': False, 'format': SCHEMA,
               'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt[:1500]}],
               'options': {'num_ctx': 4096, 'num_predict': 160, 'temperature': 0}, 'keep_alive': '5m'}
    return json.loads(local_api('ollama', 'api/chat', request, timeout=90).get('message', {}).get('content', '{}'))


def project_workflow(s, pid):
    if not pid or pid == 'universe':
        return None
    row = s.db.execute('SELECT name FROM projects WHERE id=?', (pid,)).fetchone()
    if not row:
        return None
    from model_router import normalized
    name = normalized(row[0])
    if 'animacio' in name or 'studio' in name or 'tortenet' in name:
        return 'own'
    if 'gta' in name or 'clip farm' in name or 'farm' in name:
        return 'gta6'
    if 'shorts' in name:
        return 'clip'
    return None


def understand(s, job, prompt, ask=None):
    """dict(workflow, by, question): by is 'words' for an unmistakable request, 'example' for a remembered one, 'model' otherwise.
    None when this is not a request to make a video."""
    from story_animation import video_intent
    if not candidate(prompt):
        return None
    clear = video_intent(prompt)
    if clear:
        return dict(workflow=clear, by='words', question='')
    # The open project tells what "kezdj el videót gyártani" means: the studio makes its own, the clip project cuts clips.
    here = project_workflow(s, job.get('project'))
    if here:
        return dict(workflow=here, by='project', question='')
    known = examples(s, prompt)
    if known and len({e['workflow'] for e in known[:2]}) == 1:
        from assistant_skills import similarity, words
        if similarity(words(prompt), words(known[0]['request'])) >= .75:
            return dict(workflow=known[0]['workflow'], by='example', question='')
    from execution_queue import DeferredExecution
    try:
        answer = (ask or ask_model)(s, job, prompt, known)
    except DeferredExecution:
        raise
    except Exception:
        return None  # the model is not reachable: the caller keeps its own rules
    workflow = answer.get('workflow') if isinstance(answer, dict) else None
    if workflow in WORKFLOWS:
        return dict(workflow=workflow, by='model', question='', reason=str(answer.get('reason') or '')[:200])
    if workflow == 'unsure':
        return dict(workflow='unsure', by='model', question=(str(answer.get('question') or '').strip() or QUESTION)[:200])
    return None


CORRECTION = r'\b(nem (?:ezt|azt|klip\w*|vagas\w*|animaci\w*|sajat\w*)|rossz (?:folyamat\w*|helyre)|felreertett\w*|nem (?:ertetted|jol))\b'


def learn_correction(s, project, prompt, workflow):
    """When the owner corrects a route, the earlier request (last 20 minutes, same project, routed elsewhere) is the lesson."""
    from model_router import normalized
    if workflow not in WORKFLOWS or not re.search(CORRECTION, normalized(prompt)):
        return None
    schema(s)
    row = s.db.execute("""SELECT t.prompt,json_extract(j.payload,'$.workflow') routed FROM command_turns t JOIN jobs j ON json_extract(j.payload,'$.turn')=t.id
                          WHERE t.project=? AND t.created>? AND j.kind='command' AND json_extract(j.payload,'$.workflow') IS NOT NULL
                          ORDER BY t.created DESC LIMIT 1 OFFSET 1""", (project, time.time() - 1200)).fetchone()
    if row and row['routed'] != workflow:
        remember(s, row['prompt'], workflow)
        return row['prompt']
    return None


CAPABILITIES = ('\nHOW TO CHOOSE (judge by what the owner wants to end up with, not by single words): '
                'a picture -> generate_image; an original video ORBIT makes itself -> graph_run from the Animációs stúdió Hook agent; a Short cut from existing footage -> start_shorts; '
                'a web page, app, game or document -> write_file in creations_folder, with generate_image/generate_video save_as for the assets it needs; '
                'facts from the internet -> the search and url reads (they work without any API key), and learn_skill for a data service needed again; '
                'something that should happen repeatedly or at a time -> workflow_automation_save; '
                'a LARGE, multi-step or open-ended goal (build a business idea, research and then produce, "kezdd el kidolgozni") -> project_create when it needs its own place, then mission_save with start=true so the agents work through it step by step on their own; never try to do such a goal in one giant plan, and never answer it with advice only. '
                'A question about what is running or why something waits is answered from live state. When two workflows fit equally, ask one short question.')
SELF_NOTE = ('\nThis is an ORBIT self-improvement task. You cannot edit ORBIT\'s own program code. Do what actions can do: agent prompts (agent_save), methods (skill_save), '
             'automations, missions, settings. If the fix needs a change in program code, say so in one plain sentence and summarise in 3-5 lines what a developer should change; '
             'never ask the owner for an invented permission and never claim the fix is done.')
