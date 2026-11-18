"""Operator feedback is project-scoped evidence, never a model-generated preference."""
import json,time,uuid
TAGS={'weak_story':'Gyenge történet / poén','viral':'Ez virális lehet','weak_hook':'Gyenge hook','missing_context':'Hiányzó kontextus','bad_framing':'Rossz képkivágás','too_many_effects':'Túl sok effekt','slow_pacing':'Lassú ritmus','good':'Jó lett'}
RULES={'weak_story':'Build one clear joke with an earned twist and a loop.','viral':'Keep what made this one work: the hook, the twist and the pace.','weak_hook':'Choose a brief self-contained hook with an immediate question or conflict; retain the actual payoff.','missing_context':'Preserve who, what and why, and the cause before the response.','bad_framing':'Preserve all task-relevant subjects and screen/game context; prefer evidenced split layouts over cutting off a subject.','too_many_effects':'Use clean cuts. Keep sound accents and extra punch-ins rare and specifically justified.','slow_pacing':'Remove redundant setup and greetings; use complete short utterances and meaningful visual changes while preserving causal links.'}
def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS editing_feedback(id TEXT PRIMARY KEY,project TEXT,artifact TEXT,run TEXT,tag TEXT,note TEXT,created REAL); CREATE INDEX IF NOT EXISTS feedback_project ON editing_feedback(project,created); CREATE TABLE IF NOT EXISTS editing_preferences(project TEXT PRIMARY KEY,notes TEXT,updated REAL);''')
def save(s,pid,artifact,tag,note=''):
 schema(s);s.project(pid)
 if tag not in TAGS:raise ValueError('Ismeretlen videós visszajelzés.')
 if not isinstance(note,str) or len(note)>1200:raise ValueError('Legfeljebb 1200 karakteres megjegyzést írj.')
 row=s.db.execute("SELECT a.job FROM artifacts a WHERE a.id=? AND a.project=? AND a.kind='video'",(artifact,pid)).fetchone()
 if not row:raise ValueError('A videó nem található ebben a projektben.')
 job=s.db.execute('SELECT payload FROM jobs WHERE id=?',(row['job'],)).fetchone();run=json.loads(job['payload']).get('run') if job else None
 previous=s.db.execute('SELECT id FROM editing_feedback WHERE project=? AND artifact=? AND tag=? AND note=? ORDER BY created DESC LIMIT 1',(pid,artifact,tag,note.strip())).fetchone()
 if not previous:s.db.execute('INSERT INTO editing_feedback VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,artifact,run,tag,note.strip(),time.time()))
 s.db.commit()
 # Feedback on an original story video also teaches the story writer (general rules, kept per project).
 if not previous and (note.strip() or tag in ('weak_story','viral','weak_hook')):
  try:
   import story_quality
   if job and json.loads(job['payload']).get('story_step'):
    story_quality.learn(s,pid,TAGS[tag]+(': '+note.strip() if note.strip() else ''),story_quality.latest_idea(s,pid))
  except Exception:pass
 return read(s,pid,artifact)
def preferences(s,pid,notes):
 schema(s);s.project(pid)
 if not isinstance(notes,str) or len(notes)>2000:raise ValueError('Legfeljebb 2000 karakteres szerkesztési útmutatót adj meg.')
 s.db.execute('INSERT INTO editing_preferences VALUES(?,?,?) ON CONFLICT(project) DO UPDATE SET notes=excluded.notes,updated=excluded.updated',(pid,notes.strip(),time.time()));s.db.commit();return read(s,pid)
def read(s,pid,artifact=None):
 schema(s);rows=s.rows('SELECT tag,note,artifact,created FROM editing_feedback WHERE project=? ORDER BY created DESC LIMIT 40',(pid,));pref=s.db.execute('SELECT notes,updated FROM editing_preferences WHERE project=?',(pid,)).fetchone()
 counts={t:sum(r['tag']==t for r in rows) for t in TAGS};instructions=[RULES[t] for t in RULES if counts[t]]
 return dict(notes=pref['notes'] if pref else '',updated=pref['updated'] if pref else None,counts=counts,instructions=instructions,feedback=[dict(r,label=TAGS[r['tag']]) for r in rows if artifact is None or r['artifact']==artifact],scope='Operator preferences for this project, not proof of audience performance.')
