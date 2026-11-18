"""Private ORBIT memory graph and indexed one-hop retrieval."""
import json
import os
import tempfile
import time
from collections import Counter,defaultdict

STOP = {'user','likes','prefe','wants','always','would','using','about','their','szeret','haszn','mind','tudja','legye','fonto','thems','there'}


def terms(text):
    from memory_brain import words
    return words(text)-STOP


def sync(s):
    from memory_brain import schema,SENSITIVE
    schema(s)
    if not s.db.execute("SELECT 1 FROM sqlite_master WHERE name='personal_graph_docs'").fetchone():
        s.db.executescript("""
        CREATE TABLE IF NOT EXISTS personal_graph_docs(key TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS personal_graph_terms(term TEXT,key TEXT,PRIMARY KEY(term,key));
        CREATE INDEX IF NOT EXISTS personal_graph_by_memory ON personal_graph_terms(key);
        CREATE TRIGGER IF NOT EXISTS personal_graph_delete AFTER DELETE ON assistant_memory BEGIN
          DELETE FROM personal_graph_terms WHERE key=OLD.key;
          DELETE FROM personal_graph_docs WHERE key=OLD.key;
        END;
        CREATE TRIGGER IF NOT EXISTS personal_graph_update AFTER UPDATE OF content,display ON assistant_memory BEGIN
          DELETE FROM personal_graph_terms WHERE key=OLD.key;
          DELETE FROM personal_graph_docs WHERE key=OLD.key;
        END;
        """)
    dirty=s.rows("""SELECT m.key,m.content,m.display FROM assistant_memory m
                    LEFT JOIN personal_graph_docs d ON d.key=m.key WHERE d.key IS NULL""")
    if not dirty:return
    with s.db:
        s.db.execute('BEGIN IMMEDIATE')
        for row in dirty:
            current=s.db.execute('SELECT content,display FROM assistant_memory WHERE key=?',(row['key'],)).fetchone()
            if current is None or tuple(current)!=(row['content'],row['display']):continue
            text=(row['content'] or '')+' '+(row['display'] or '')
            if not SENSITIVE.search(text):
                s.db.executemany('INSERT OR IGNORE INTO personal_graph_terms VALUES(?,?)',
                                 [(term,row['key']) for term in terms(text)])
            s.db.execute('INSERT OR IGNORE INTO personal_graph_docs VALUES(?)',(row['key'],))


def build(s,query='',kind='',project=''):
    from memory_brain import SENSITIVE
    from model_router import normalized
    import re
    sync(s)
    projects=s.rows("SELECT id,name FROM projects WHERE id!='universe' AND length(name)>=3 ORDER BY name")
    requested=normalized(query).strip()
    nodes=[];links=[];seen=set()
    for row in s.rows('SELECT key,content,display,kind,source,updated FROM assistant_memory ORDER BY updated DESC,key'):
        title=row['display'] or row['content']
        body=normalized(row['content']+' '+title)
        if SENSITIVE.search(row['content']+' '+title) or requested not in body or (kind and kind!=row['kind']):continue
        references=[p for p in projects if row['key']!='user-profile'
                    and re.search(r'(?<!\w)'+re.escape(normalized(p['name']))+r'(?!\w)',body)]
        if project and not any(p['id']==project for p in references):continue
        nodes.append(dict(id=row['key'],label=title,kind=row['kind'],content=row['content'],source=row['source'],
                          updated=row['updated'],source_file='private-memory'))
        seen.add(row['key'])
        for p in references:
            pid='project:'+p['id']
            if pid not in seen:
                nodes.append(dict(id=pid,label=p['name'],kind='project_ref',source='project'))
                seen.add(pid)
            links.append(dict(source=row['key'],target=pid,relation='mentions_project',confidence='MENTION'))
    postings=defaultdict(list)
    for row in s.rows('SELECT term,key FROM personal_graph_terms'):
        if row['key'] in seen:postings[row['term']].append(row['key'])
    shared=Counter()
    for keys in postings.values():
        if not 2<=len(keys)<=24:continue
        for i,left in enumerate(keys):
            for right in keys[i+1:]:
                shared[left,right]+=1
    degree=Counter()
    for (left,right),count in sorted(shared.items(),key=lambda entry:-entry[1]):
        if count<2 or max(degree[left],degree[right])>=5:continue
        links.append(dict(source=left,target=right,relation='related_topic',confidence='INFERRED',
                          confidence_score=min(.85,.35+count*.1)))
        degree[left]+=1;degree[right]+=1
    return dict(directed=False,multigraph=False,graph=dict(kind='private_user_memory',observed_at=time.time()),
                nodes=nodes,links=links,projects=projects)


def export(s):
    graph=build(s);folder=s.root/'private'/'memory-graph'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w',dir=folder,delete=False,encoding='utf-8') as stream:
        temp=stream.name
        json.dump(graph,stream,ensure_ascii=False)
    os.replace(temp,folder/'graph.json')
    return graph


def related(s,prompt,*,limit,seeds):
    from memory_brain import SENSITIVE
    if not seeds or SENSITIVE.search(prompt):return []
    sync(s)
    keys=list(seeds)[:6]
    marks=','.join('?'*len(keys))
    rows=s.rows(f"""WITH seeds AS (
       SELECT key FROM personal_graph_docs WHERE key IN ({marks})
    ), topics AS (
       SELECT DISTINCT term FROM personal_graph_terms JOIN seeds USING(key)
       WHERE term IN (SELECT term FROM personal_graph_terms GROUP BY term HAVING count(*) BETWEEN 2 AND 24)
    )
    SELECT m.kind,m.content FROM topics t JOIN personal_graph_terms p ON p.term=t.term
      JOIN assistant_memory m ON m.key=p.key WHERE m.key NOT IN (SELECT key FROM seeds)
      AND m.key!='user-profile' GROUP BY m.key HAVING count(*)>=2
      ORDER BY count(*) DESC,m.updated DESC,m.key LIMIT ?""",(*keys,limit))
    return [dict(kind=row['kind'],content=row['content'][:350]) for row in rows]
