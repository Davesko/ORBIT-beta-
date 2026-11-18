"""Conservative natural-language intake for existing video workflows, not an LLM plan."""
import json,re,time
from model_router import normalized

LAUNCH=r'\b(generalj|generaljon|generaljatok|keszits|keszitsd|keszitsen|keszitsenek|keszitsetek|indits|inditsd|inditson|csinalj|csinaljon|vagj|vagd|vagjon|start|generate|create|make)\b'
VIDEO=r'\b(video\w*|shorts?\w*|youtube|klip\w*|clip\s+farm)\b'

# Common nouns that take -ról/-ről but are never the requested person or channel.
GENERIC=re.compile(r'^(?:stream\w*|video\w*|ad[aá]s\w*|klip\w*|anyag\w*|hiba\w*|mukodes\w*|projekt\w*|streamer\w*|youtuber\w*|csatorn\w*|tem\w*|trend\w*|mostani\w*|friss\w*|tegnapi\w*|legutobbi\w*|uj\w*|\d+\w*)$')
STOP=set('egy a az es video videot videok shorts shortsot youtube keszits generalj indits funny best moments highlights legjobb vicces pillanatok'.split())

def subject(prompt):
    # "ISHOWSPEED - ről", "MrBeast-ről": a hyphenated suffix names the subject explicitly.
    match=re.search(r'([\w.]+(?:\s+[\w.]+)?)\s*[-–]\s*(?:r[oó]l|r[őö]l)\b',prompt,re.I)
    if match:
        words=[w for w in match[1].split() if normalized(w) not in STOP and not GENERIC.match(normalized(w))]
        if words:return ' '.join(words[-2:])
    match=re.search(r'([\w.-]+(?:\s+[\w.-]+){0,2})\s+(?:youtuber|streamer)\w*',prompt,re.I)
    if match:
        words=match[1].split();stop=set('egy a az video videot videok shorts shortsot keszits generalj indits funny best moments'.split())
        words=[w for w in words if normalized(w) not in stop]
        if words:return ' '.join(words[-2:])
    match=re.search(r'\b([\w.-]{2,40}?)(?:ról|ről)\b',prompt,re.I)
    if not match:match=re.search(r'\b([\w.-]{2,40})\s+(?:ról|ről)\b',prompt,re.I)
    if match and not GENERIC.match(normalized(match[1])):
        return match[1].rstrip('-')
    # An all-caps channel/person token ("best moments ISHOWSPEED videót").
    for token in re.findall(r'\b[A-Z][A-Z0-9_.]{2,30}\b',prompt):
        if normalized(token) not in STOP and not GENERIC.match(normalized(token)):return token
    return None

def query(prompt):
    who=subject(prompt)
    if not who:return None
    p=normalized(prompt)
    flavor='funny moments' if 'funny' in p or 'vicces' in p else 'best moments' if 'best' in p or 'legjobb' in p else 'highlights'
    year=re.search(r'\b(20[2-3]\d)\b',p)
    freshness=' latest stream' if re.search(r'\b(friss\w*|legutobbi\w*|latest|mostani\w*|aktualis\w*|current|uj)\b',p) else ' '+year[1]+' stream' if year else ''
    return (who+freshness+' '+flavor)[:200]

def continuation(s,pid,prompt):
    """A subject-only reply can complete a recent blocked production brief."""
    p=normalized(prompt)
    if re.search(LAUNCH,p) or not query(prompt) or len(prompt)>200:return None
    if not s.db.execute("SELECT 1 FROM sqlite_master WHERE name='command_turns'").fetchone():return None
    rows=s.rows('SELECT prompt,status,created FROM command_turns WHERE project=? AND prompt<>? ORDER BY created DESC LIMIT 3',(pid,prompt))
    if not rows:return None
    prior=rows[0]
    if time.time()-prior['created']>3600 or prior['status'] not in ('attention','failed'):return None
    old=normalized(prior['prompt'])
    if not re.search(LAUNCH,old) or not re.search(VIDEO,old):return None
    before=subject(prior['prompt']);now=subject(prompt)
    if before and normalized(before)!=normalized(now):return None
    return dict(topic=query(prompt),constraints_from=prior['prompt'])

def placeholder(reply):
    return bool(re.fullmatch(r'\s*(Hungarian (?:user-facing )?reply|Hungarian response|magyar v[aá]lasz|your reply(?: here)?|reply|\.\.\.)[.!]?\s*',str(reply),re.I))


def resume_plan(s,pid,prompt,global_mode=False):
    p=normalized(prompt)
    if not re.search(r'\b(folytasd|folytassad|continue|resume)\b',p) or re.search(r'\b(ne|nem|not|dont|pelda|example|fejlesz\w*)\b',p) or prompt.rstrip().endswith('?'):return None
    who=subject(prompt)
    if not who:return None
    if not s.db.execute("SELECT 1 FROM sqlite_master WHERE name='short_runs'").fetchone():return None
    rows=s.rows('SELECT id,project,query,data FROM short_runs ORDER BY created DESC LIMIT 30')
    for row in rows:
        if not global_mode and row['project']!=pid:continue
        if normalized(who) not in normalized(row['query']):continue
        jobs=s.rows("SELECT id,status,json_extract(payload,'$.auto_step') stage FROM jobs WHERE project=? AND json_extract(payload,'$.run')=? ORDER BY created",(row['project'],row['id']))
        if any(j['status'] in ('queued','running') for j in jobs):return None
        failed=next((j for j in jobs if j['status']=='failed'),None)
        if failed and failed['stage'] in ('selection','layout'):
            return [dict(type='app_action',project=row['project'],operation='production_resume',args=dict(id=failed['id']))]
        return None
    return None
