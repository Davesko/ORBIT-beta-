"""Local, read-only search across app objects and registered project text files."""
import unicodedata
from pathlib import Path


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c))


def search(s,query):
    query=' '.join(str(query or '').split())[:120]
    terms=fold(query).split()[:8]
    if len(query)<2:return dict(results=[])
    import chat_sessions
    chat_sessions.schema(s)
    s.db.create_function('orbit_search_fold',1,fold)
    tables={r[0] for r in s.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    results=[]
    def add(entry_type,title,detail='',**target):
        text=str(detail or '');at=fold(text).find(terms[0]);start=max(0,at-55)
        results.append(dict(type=entry_type,title=str(title or 'Névtelen')[:160],excerpt=('…' if start else '')+text[start:start+220],**target))
    def rows(table,columns,where='1=1',join=''):
        if table not in tables:return []
        expression=" || ' ' || ".join('COALESCE('+col+",'')" for col in columns)
        checks=' AND '.join("orbit_search_fold("+expression+") LIKE ? ESCAPE '\\'" for _ in terms)
        values=['%'+t.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%' for t in terms]
        return s.rows('SELECT t.* FROM '+table+' t '+join+' WHERE ('+where+') AND '+checks+' LIMIT 12',values)
    for r in rows('command_turns',['t.prompt','t.response'],
                  "t.project IN (SELECT id FROM projects) AND NOT EXISTS (SELECT 1 FROM chat_session_turns c JOIN chat_archives a ON a.session=c.session WHERE c.turn=t.id)"):
        sid=chat_sessions.of_turn(s,r['id']) or chat_sessions.LEGACY
        add('chat',r['prompt'],r['response'],session=sid,turn=r['id'],project=r['project'])
    for r in rows('projects',['t.name','t.description']):add('project',r['name'],r['description'],project=r['id'])
    for r in rows('agents',['t.name','t.role','t.prompt'],
                  't.project IN (SELECT id FROM projects)'+(' AND t.id NOT IN (SELECT id FROM agent_archive)' if 'agent_archive' in tables else '')):
        add('agent',r['name'],r['role'],project=r['project'],id=r['id'])
    for r in rows('rooms',['t.name','t.sub'],'t.archived=0 AND t.project IN (SELECT id FROM projects)'):
        add('room',r['name'],r['sub'],project=r['project'],id=r['id'])
    for r in rows('automations',['t.name','t.config'],'t.archived=0 AND (t.project IS NULL OR t.project IN (SELECT id FROM projects))'):
        add('task',r['name'],'Bekapcsolva' if r['enabled'] else 'Kikapcsolva',project=r['project'],id=r['id'])
    for r in rows('emails',['t.subject','t.sender','t.sender_name','t.body'],'t.removed=0'):
        add('email',r['subject'],(r['sender_name'] or '')+' · '+(r['snippet'] or ''),id=r['id'])
    for r in rows('assistant_memory',['t.key','t.content']):add('memory',r['key'],r['content'],id=r['key'])
    # File contents are scoped to registered artifacts under their own project root.
    # Never scan model weights, credentials, external folders or arbitrary file paths.
    if 'artifacts' in tables:
        found=set()
        for r in rows('artifacts',['t.name'],'t.project IN (SELECT id FROM projects)'):
            add('file',r['name'],project=r['project'],id=r['id'],kind=r['kind']);found.add(r['id'])
        for r in s.rows('SELECT a.* FROM artifacts a JOIN projects p ON p.id=a.project ORDER BY a.created DESC LIMIT 1200'):
            if r['id'] in found:continue
            title=r['name'];content='';matched=all(t in fold(title) for t in terms)
            if not matched and r['kind']=='text':
                try:
                    path=Path(r['path']).resolve();base=(s.root/'projects'/r['project']).resolve()
                    if base not in path.parents or not path.is_file() or path.stat().st_size>256*1024:continue
                    content=path.read_text(encoding='utf-8');matched=all(t in fold(title+' '+content) for t in terms)
                except (OSError,UnicodeError):continue
            if matched:add('file',title,content,project=r['project'],id=r['id'],kind=r['kind'])
            if len(results)>=75:break
    return dict(results=results[:75],scope='Chats, projects, agents, rooms, tasks, synchronized emails, memory and the newest 1200 registered files (text contents up to 256 KB).')


def dispatch(s,op,args=None):
    if op!='search_all':raise ValueError('Ismeretlen keresési művelet.')
    return search(s,(args or {}).get('query'))
