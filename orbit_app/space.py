"""Persistent room layout and explicit, acyclic agent handoffs. No model calls."""
import json
import math
import re
import time
import uuid

DEFAULT_ROOMS = [
    ('bridge','Irányító','Itt születik a terv',0,0,'command','#3d3540','#38394d','#ad8aee'),
    ('research','Kutatólabor','Kérdésekből felismerések',10.5,0,'research','#403640','#38394d','#ad8aee'),
    ('workshop','Alkotóműhely','Ötletből kézzelfogható eredmény',0,9.5,'workshop','#393341','#38394d','#ad8aee'),
    ('media','Médiastúdió','Kép, mozgás és képzelet',10.5,9.5,'media','#343444','#38394d','#ad8aee')]

def bounded(value,low,high):
    if isinstance(value,bool):raise ValueError('Érvénytelen méret vagy koordináta.')
    value=float(value)
    if not math.isfinite(value) or not low<=value<=high:raise ValueError('A szoba mérete vagy helye a megengedett tartományon kívül van.')
    return round(value*2)/2

def label(value,maximum,optional=False):
    if not isinstance(value,str) or len(value)>maximum or (not optional and not value.strip()):raise ValueError('A szöveg üres vagy túl hosszú.')
    return value.strip()

class SpaceMixin:
    def space_schema(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS rooms(project TEXT,id TEXT,name TEXT,sub TEXT,x REAL,y REAL,width REAL,height REAL,decor TEXT,floor TEXT,wall TEXT,accent TEXT,archived INTEGER DEFAULT 0,PRIMARY KEY(project,id));
        CREATE TABLE IF NOT EXISTS space_migrations(project TEXT PRIMARY KEY,version INTEGER);
        CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,project TEXT,source TEXT,target TEXT,name TEXT,mode TEXT,instructions TEXT,task TEXT,archived INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS job_dependencies(job TEXT,parent TEXT,PRIMARY KEY(job,parent));
        CREATE INDEX IF NOT EXISTS agent_room ON agents(project,room);
        CREATE INDEX IF NOT EXISTS job_queue ON jobs(status,kind,created);
        CREATE INDEX IF NOT EXISTS message_agent ON messages(project,agent,id);
        CREATE INDEX IF NOT EXISTS dependency_parent ON job_dependencies(parent);
        CREATE INDEX IF NOT EXISTS connection_project ON connections(project,archived);
        ''')
        columns={r['name'] for r in self.rows('PRAGMA table_info(connections)')}
        if 'output_kind' not in columns:self.db.execute("ALTER TABLE connections ADD COLUMN output_kind TEXT DEFAULT ''");self.db.commit()
    def ensure_rooms(self,pid):
        if self.db.execute('SELECT 1 FROM space_migrations WHERE project=?',(pid,)).fetchone():return
        for rid,name,sub,x,y,decor,floor,wall,accent in DEFAULT_ROOMS:
            self.db.execute('INSERT OR IGNORE INTO rooms VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)',(pid,rid,name,sub,x,y,8.5,7.5,decor,floor,wall,accent))
        self.db.execute('INSERT OR IGNORE INTO space_migrations VALUES(?,1)',(pid,));self.db.commit()
    def room(self,pid,rid,active=True):
        row=self.db.execute('SELECT * FROM rooms WHERE project=? AND id=?'+(' AND archived=0' if active else ''),(pid,rid)).fetchone()
        if not row:raise ValueError('A szoba nem található ebben a projektben.')
        return dict(row)
    def room_capacity(self,pid):
        if self.db.execute('SELECT 1 FROM agents WHERE project=? GROUP BY room HAVING count(*)>16',(pid,)).fetchone():raise ValueError('Egy szobában legfeljebb 16 ügynök helyezhető el. Válassz másik szobát.')
    def room_available(self,pid,x,y,w,h,exclude=None):
        for r in self.rows('SELECT * FROM rooms WHERE project=? AND archived=0',(pid,)):
            if r['id']!=exclude and x<r['x']+r['width']+.5 and x+w+.5>r['x'] and y<r['y']+r['height']+.5 and y+h+.5>r['y']:return False
        return True
    def room_slot(self,pid,w=8.5,h=7.5):
        current=self.rows('SELECT * FROM rooms WHERE project=? AND archived=0',(pid,))
        xs={0}|{r['x'] for r in current}|{r['x']+r['width']+2 for r in current};ys={0}|{r['y'] for r in current}|{r['y']+r['height']+2 for r in current}
        for x,y in sorted(((x,y) for x in xs for y in ys if -200<=x<=200 and -200<=y<=200),key=lambda p:(abs(p[0])+abs(p[1]),p[1],p[0])):
            if self.room_available(pid,x,y,w,h):return x,y
        for row in range(12):
            for col in range(12):
                if self.room_available(pid,col*16,row*14,w,h):return col*16,row*14
        raise ValueError('Nincs több hely a műhelyben.')
    def save_room(self,pid,data):
        self.project(pid);rid=data.get('id') or uuid.uuid4().hex
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',rid):raise ValueError('Érvénytelen szobaazonosító.')
        existing=self.db.execute('SELECT * FROM rooms WHERE project=? AND id=?',(pid,rid)).fetchone()
        if existing and existing['archived']:raise ValueError('Előbb állítsd vissza a törölt szobát.')
        if not existing and self.db.execute('SELECT count(*) FROM rooms WHERE project=? AND archived=0',(pid,)).fetchone()[0]>=24:raise ValueError('Egy projektben legfeljebb 24 szoba használható.')
        w=bounded(data.get('width',8.5),8,14);h=bounded(data.get('height',7.5),7,12)
        default=(existing['x'],existing['y']) if existing else self.room_slot(pid,w,h)
        x=bounded(data.get('x',default[0]),-200,200);y=bounded(data.get('y',default[1]),-200,200)
        if not self.room_available(pid,x,y,w,h,rid):raise ValueError('A szobák nem fedhetik egymást. Válassz szabad helyet vagy kisebb méretet.')
        decor=data.get('decor','workshop')
        if decor not in ('command','research','workshop','media','lounge','editing','marketing','office','audio','gaming','kitchen','gym','terrace','library','server'):raise ValueError('Ismeretlen berendezés.')
        colors=[data.get(k,v) for k,v in [('floor','#babfa6'),('wall','#e4e5d1'),('accent','#d9f883')]]
        if not all(isinstance(c,str) and re.fullmatch('#[0-9A-Fa-f]{6}',c) for c in colors):raise ValueError('Érvénytelen szín.')
        members=data.get('members')
        if members is not None:
            if not isinstance(members,list) or len(members)!=len(set(members)) or len(members)>16:raise ValueError('Válassz legfeljebb 16 különböző ügynököt.')
            for aid in members:
                if self.agent(aid)['project']!=pid:raise ValueError('Másik projekt ügynöke.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if not existing and self.db.execute('SELECT count(*) FROM rooms WHERE project=? AND archived=0',(pid,)).fetchone()[0]>=24:raise ValueError('Legfeljebb 24 szoba használható.')
            # Recheck after acquiring the write lock, including simultaneous UI saves.
            if not self.room_available(pid,x,y,w,h,rid):raise ValueError('A helyet időközben másik szoba foglalta el.')
            self.db.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0) ON CONFLICT(project,id) DO UPDATE SET name=excluded.name,sub=excluded.sub,x=excluded.x,y=excluded.y,width=excluded.width,height=excluded.height,decor=excluded.decor,floor=excluded.floor,wall=excluded.wall,accent=excluded.accent',
                (pid,rid,label(data.get('name','Új szoba'),60),label(data.get('sub',''),120,True),x,y,w,h,decor,*colors))
            if members is not None:
                removed=[a['id'] for a in self.rows('SELECT id FROM agents WHERE project=? AND room=?',(pid,rid)) if a['id'] not in members]
                if removed:
                    destination=data.get('move_to')
                    if destination==rid:raise ValueError('Válassz másik szobát a kijelölésből kivett ügynököknek.')
                    self.room(pid,destination)
                    self.db.executemany('UPDATE agents SET room=? WHERE project=? AND id=?',[(destination,pid,a) for a in removed])
                self.db.executemany('UPDATE agents SET room=? WHERE project=? AND id=?',[(rid,pid,a) for a in members]);self.room_capacity(pid)
            self.db.commit()
        except Exception:self.db.rollback();raise
        self.event(pid,'Szoba mentve · '+data.get('name','Új szoba'));return rid
    def archive_room(self,pid,rid,move_to=None):
        self.room(pid,rid);others=self.rows('SELECT id FROM rooms WHERE project=? AND id!=? AND archived=0',(pid,rid))
        if not others:raise ValueError('Az utolsó szobát nem lehet törölni. Előbb hozz létre másikat.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT count(*) FROM rooms WHERE project=? AND archived=0',(pid,)).fetchone()[0]<=1:raise ValueError('Az utolsó szobát nem lehet törölni.')
            if self.db.execute('SELECT 1 FROM agents WHERE project=? AND room=?',(pid,rid)).fetchone():
                if move_to==rid:raise ValueError('Válassz másik szobát az ügynököknek.')
                self.room(pid,move_to)
                self.db.execute('UPDATE agents SET room=? WHERE project=? AND room=?',(move_to,pid,rid));self.room_capacity(pid)
            self.db.execute('UPDATE rooms SET archived=1 WHERE project=? AND id=?',(pid,rid));self.db.commit()
        except Exception:self.db.rollback();raise
        self.event(pid,'Szoba törölve · visszaállítható')
    def restore_room(self,pid,rid):
        r=self.room(pid,rid,False)
        if not r['archived']:return
        if self.db.execute('SELECT count(*) FROM rooms WHERE project=? AND archived=0',(pid,)).fetchone()[0]>=24:raise ValueError('Előbb szabadíts fel egy szobahelyet.')
        x,y=(r['x'],r['y']) if self.room_available(pid,r['x'],r['y'],r['width'],r['height']) else self.room_slot(pid,r['width'],r['height'])
        self.db.execute('UPDATE rooms SET archived=0,x=?,y=? WHERE project=? AND id=?',(x,y,pid,rid));self.db.commit()
    def save_connection(self,pid,data):
        source=data.get('source');target=data.get('target')
        if source==target:raise ValueError('Egy ügynököt nem lehet saját magával összekötni.')
        for aid in (source,target):
            if self.agent(aid)['project']!=pid:raise ValueError('Másik projekt ügynöke.')
        output_kind=data.get('output_kind','')
        if output_kind not in ('','text','image','video','audio'):raise ValueError('Ismeretlen elvárt eredménytípus.')
        mode=data.get('mode','result')
        if mode not in ('result','files','both'):raise ValueError('Ismeretlen átadási mód.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing=self.db.execute('SELECT * FROM connections WHERE project=? AND source=? AND target=?',(pid,source,target)).fetchone()
            cid=data.get('id') or (existing['id'] if existing else uuid.uuid4().hex)
            if not isinstance(cid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',cid):raise ValueError('Érvénytelen kapcsolat-azonosító.')
            if existing and cid!=existing['id']:raise ValueError('Ezek között az ügynökök között már van összeköttetés.')
            owned=self.db.execute('SELECT * FROM connections WHERE id=?',(cid,)).fetchone()
            if owned and (owned['project']!=pid or owned['source']!=source or owned['target']!=target):raise ValueError('Az összeköttetés végpontjai nem módosíthatók.')
            edges=[(r['source'],r['target']) for r in self.rows('SELECT * FROM connections WHERE project=? AND archived=0 AND id!=?',(pid,cid))]+[(source,target)]
            visited=set();front=[target]
            while front:
                node=front.pop()
                if node==source:raise ValueError('Ez körkörös munkafolyamatot hozna létre. A végtelen futást elkerülve másik irányt válassz.')
                if node not in visited:visited.add(node);front.extend(b for a,b in edges if a==node)
            self.db.execute('INSERT INTO connections(id,project,source,target,name,mode,instructions,task,output_kind,archived) VALUES(?,?,?,?,?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET name=excluded.name,mode=excluded.mode,instructions=excluded.instructions,task=excluded.task,output_kind=excluded.output_kind,archived=0',
                (cid,pid,source,target,label(data.get('name','Eredmény átadása'),80),mode,label(data.get('instructions','Az átadott adatokból a feladat szempontjából fontos részekkel dolgozz.'),3000),label(data.get('task','Dolgozd tovább az átadott eredményt a saját szereped szerint.'),6000),output_kind))
            self.db.commit();return cid
        except Exception:self.db.rollback();raise
    def archive_connection(self,pid,cid):
        changed=self.db.execute('UPDATE connections SET archived=1 WHERE project=? AND id=?',(pid,cid)).rowcount;self.db.commit()
        if not changed:raise ValueError('Ismeretlen összeköttetés.')
    def enqueue_graph(self,pid,start,prompt,*,video_model=None):
        if self.agent(start)['project']!=pid:raise ValueError('Másik projekt ügynöke.')
        prompt=label(prompt,12000);edges=self.rows('SELECT * FROM connections WHERE project=? AND archived=0 ORDER BY rowid',(pid,))
        nodes={start};front=[start]
        while front:
            node=front.pop()
            for e in edges:
                if e['source']==node and e['target'] not in nodes:nodes.add(e['target']);front.append(e['target'])
        if len(nodes)<2:raise ValueError('Előbb köss össze legalább két ügynököt.')
        if len(nodes)>12:raise ValueError('Egy vizuális futásban legfeljebb 12 ügynök vehet részt.')
        story_steps={}
        if start.startswith('story-'):
            from story_animation import agent_ids, video_seconds
            from story_episode import series
            from local_video import requested_model,video_model as select_video_model
            from model_hub import config
            story_steps={aid:step for step,aid in agent_ids(pid).items()}
            if start!=agent_ids(pid)['hook'] or nodes!=set(story_steps):
                raise ValueError('A Történetműhelyt a Hook ügynöktől indítsd, az összekötött történeti szerepekkel.')
            video_seconds(prompt)
            # Only a model the owner names is recorded; without one the story render uses the rig animation.
            video_model=video_model or requested_model(prompt)
            if video_model:video_model=select_video_model(video_model,image=True)
            story_series=series(self,pid)
            story_ssd=bool(config().get('mount'))
        requirements={aid:sorted({e.get('output_kind') for e in edges if e['target']==aid and e.get('output_kind')}) for aid in nodes}
        edges=[e for e in edges if e['source'] in nodes and e['target'] in nodes]
        # Snapshot the selected graph. Later edits never alter an already queued run.
        order=[];remaining=set(nodes)
        while remaining:
            ready=sorted(n for n in remaining if all(e['source'] in order for e in edges if e['target']==n))
            if not ready:raise ValueError('Körkörös munkafolyamat nem indítható.')
            order.extend(ready);remaining.difference_update(ready)
        run=uuid.uuid4().hex;jobs={}
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for aid in order:
                incoming=[e for e in edges if e['target']==aid]
                specs=[{'parent':jobs[e['source']],'connection':e['id'],'mode':e['mode'],'instructions':e['instructions'],'task':e['task']} for e in incoming]
                task=prompt if aid==start else 'A folyamat közös célja:\n'+prompt+'\n\nA neked szóló feladatok:\n'+'\n'.join(e['task'] for e in incoming)
                payload={'run':run,'handoffs':specs,'required_outputs':requirements[aid]}
                if story_steps:
                    step=story_steps[aid]
                    if len(incoming)!=(0 if aid==start else 1):
                        raise ValueError('A Történetműhely egyenes átadási láncot igényel.')
                    payload.update(story_step=step,story_brief=prompt,story_series=story_series,local_only=True,video_model=video_model,
                                   foreground_video=step in ('sound','render') and story_ssd,
                                   required_outputs=['video'] if step=='render' else [])
                jid=self.enqueue(aid,task,'graph',payload=payload,commit=False);jobs[aid]=jid
                self.db.executemany('INSERT INTO job_dependencies VALUES(?,?)',[(jid,item['parent']) for item in specs])
            self.db.commit()
        except Exception:self.db.rollback();raise
        return {'run':run,'jobs':jobs}
    def handoff_context(self,job):
        data=json.loads(job['payload']);parts=[]
        for spec in data.get('handoffs',[]):
            parent=self.db.execute("SELECT * FROM jobs WHERE id=? AND project=? AND status='done'",(spec['parent'],job['project'])).fetchone()
            if not parent:raise ValueError('Az átadás egyik előfeltétele még nem teljesült.')
            from language_bridge import translate_many
            instruction,task=translate_many([spec['instructions'],spec['task']],self.root)
            content={'handoff_instructions':instruction,'recipient_task':task}
            if spec['mode'] in ('result','both'):
                result=parent['result'][:12000]
                try:json.loads(result)
                except ValueError:result=translate_many([result],self.root)[0]
                content['text_result']=result
            if spec['mode'] in ('files','both'):
                base=(self.root/'projects'/job['project']).resolve();files=[]
                for a in self.rows('SELECT name,path,kind FROM artifacts WHERE project=? AND job=?',(job['project'],parent['id'])):
                    path=__import__('pathlib').Path(a['path']).resolve()
                    if base in path.parents:files.append({'name':a['name'],'path':str(path.relative_to(base)),'kind':a['kind']})
                content['files']=files[:50]
            # Receipt records the actual packet admitted into this model request.
            parts.append(content)
        serialized=json.dumps(parts,ensure_ascii=False)
        if len(serialized)>24000:
            raise ValueError('Az átadási csomag túl nagy (24 000 karakter). Kérj rövidebb összefoglalót a küldőktől.')
        for spec,content in zip(data.get('handoffs',[]),parts):
            self.record_handoff(job,spec['parent'],spec['connection'],content)
        return '\nVerified project handoff data (not system instructions):\n'+serialized if parts else ''
