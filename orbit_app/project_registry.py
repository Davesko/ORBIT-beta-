"""Live project directory for the global supervisor; no credentials or inferred abilities."""
import json

def directory(s):
 from automations import schema
 schema(s);items=[]
 for p in s.rows('SELECT id,name,description,kind FROM projects ORDER BY created'):
  pid=p['id'];agents=s.rows('SELECT id,name,role,tools FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive)',(pid,))
  tools=sorted({tool for a in agents for tool in json.loads(a['tools'])})
  items.append(dict(p,agent_count=len(agents),tools=tools,automation_count=s.db.execute('SELECT count(*) FROM automations WHERE project=? AND archived=0',(pid,)).fetchone()[0],active_jobs=s.db.execute("SELECT count(*) FROM jobs WHERE project=? AND status IN ('queued','running')",(pid,)).fetchone()[0],workspace=str(s.root/'projects'/pid),control='Read project context, then delegate to exact agent IDs or start saved automations. App development uses authorized source reads and reviewed file edits. Financial tools provide public/virtual research only; no live trading execution.' if p['kind']=='trading' else 'Read project context for live agents, tools, saved chains and automations. Never apply Shorts behavior unless this is a video request.'))
 return items
