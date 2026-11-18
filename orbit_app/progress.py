"""Durable execution observations, not inferred model thoughts or simulated progress."""
import json
import time
import uuid

class ProgressMixin:
    def progress_schema(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS job_runtime(job TEXT PRIMARY KEY,phase TEXT,label TEXT,updated REAL,input TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS job_log(id INTEGER PRIMARY KEY,job TEXT,kind TEXT,label TEXT,details TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS log_job ON job_log(job,id);
        CREATE TABLE IF NOT EXISTS handoff_receipts(id TEXT PRIMARY KEY,project TEXT,job TEXT,parent TEXT,connection TEXT,data TEXT,created REAL,UNIQUE(job,parent,connection));
        CREATE INDEX IF NOT EXISTS receipt_project ON handoff_receipts(project,created);
        ''')
    def job_stage(self,job,phase,label,details='',input_text=None):
        previous=self.db.execute('SELECT phase,label FROM job_runtime WHERE job=?',(job,)).fetchone()
        self.db.execute("INSERT INTO job_runtime(job,phase,label,updated,input) VALUES(?,?,?,?,?) ON CONFLICT(job) DO UPDATE SET phase=excluded.phase,label=excluded.label,updated=excluded.updated,input=CASE WHEN ? IS NULL THEN job_runtime.input ELSE excluded.input END",(job,phase,label,time.time(),input_text or '',input_text))
        last=self.db.execute('SELECT kind,label FROM job_log WHERE job=? ORDER BY id DESC LIMIT 1',(job,)).fetchone()
        # A job waiting for the model lease is retried every few seconds; each retry used to log
        # starting/processing/waiting again (thousands of identical rows). Log the wait once.
        repeat=last is not None and ((last['kind'],last['label'])==(phase,label) or (last['kind']=='waiting' and phase in ('starting','processing')))
        if not repeat and (not previous or previous['phase']!=phase or previous['label']!=label):
            self.db.execute('INSERT INTO job_log(job,kind,label,details,created) VALUES(?,?,?,?,?)',(job,phase,label,str(details)[:24000],time.time()))
        self.db.commit()
    def record_handoff(self,job,parent,connection,data):
        self.db.execute('INSERT OR IGNORE INTO handoff_receipts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,job['project'],job['id'],parent,connection,json.dumps(data,ensure_ascii=False),time.time()))
        self.db.commit()
    def progress_snapshot(self,pid,jobs):
        runtime={r['job']:r for r in self.rows('SELECT r.job,r.phase,r.label,r.updated FROM job_runtime r JOIN jobs j ON j.id=r.job WHERE j.project=?',(pid,))}
        for job in jobs:job['runtime']=runtime.get(job['id'])
        # Complete each visible graph run, even if unrelated chat jobs fill the recent list.
        runs={}
        for job in jobs:
            if job['kind'] in ('graph','pipeline','youtube_upload'):
                run=json.loads(job['payload']).get('run')
                if run:runs[run]=True
        workflows=[]
        for run in list(runs)[:5]:
            members=self.rows("SELECT id,agent,status,prompt,error,created,started,finished,payload FROM jobs WHERE project=? AND kind IN ('graph','pipeline','youtube_upload') AND json_extract(payload,'$.run')=? ORDER BY created",(pid,run))
            for job in members:job['runtime']=runtime.get(job['id'])
            workflows.append({'id':run,'jobs':members})
        research=self.rows("SELECT * FROM jobs WHERE project=? AND json_extract(payload,'$.farm_research')=1 ORDER BY created DESC LIMIT 8",(pid,))
        for job in research:
            payload=json.loads(job['payload']);child=payload.get('production_submission',{}).get('run')
            group=next((w for w in workflows if w['id']==child),None)
            if child and not group:
                members=self.rows("SELECT * FROM jobs WHERE project=? AND json_extract(payload,'$.run')=? ORDER BY created",(pid,child))
                if members:
                    for member in members:member['runtime']=runtime.get(member['id'])
                    group={'id':child,'jobs':members};workflows.append(group)
            job['runtime']=runtime.get(job['id'])
            if group:group['jobs'].insert(0,job)
            else:workflows.append({'id':'research:'+job['id'],'jobs':[job]})
        workflows.sort(key=lambda w:max(j['created'] for j in w['jobs']),reverse=True)
        workflows=workflows[:8]
        receipts=self.rows('SELECT id,job,parent,connection,created FROM handoff_receipts WHERE project=? ORDER BY created DESC LIMIT 100',(pid,))
        return {'workflow_runs':workflows,'handoff_receipts':receipts}
    def job_detail(self,pid,jid):
        row=self.db.execute('SELECT * FROM jobs WHERE project=? AND id=?',(pid,jid)).fetchone()
        if not row:raise ValueError('Ismeretlen projektfeladat.')
        result=dict(row);runtime=self.db.execute('SELECT * FROM job_runtime WHERE job=?',(jid,)).fetchone()
        result['runtime']=dict(runtime) if runtime else None
        result['log']=self.rows('SELECT kind,label,details,created FROM job_log WHERE job=? ORDER BY id DESC LIMIT 40',(jid,))
        packets=self.rows('SELECT * FROM handoff_receipts WHERE project=? AND job=? ORDER BY created',(pid,jid))
        for packet in packets:packet['data']=json.loads(packet['data'])
        result['received']=packets
        pending=[]
        for spec in json.loads(row['payload']).get('handoffs',[]):
            parent=self.db.execute('SELECT id,agent,status,result FROM jobs WHERE project=? AND id=?',(pid,spec['parent'])).fetchone()
            if parent:pending.append({'connection':spec['connection'],'instructions':spec['instructions'],'task':spec['task'],'parent':dict(parent),'received':any(p['parent']==parent['id'] and p['connection']==spec['connection'] for p in packets)})
        if row['dependency']:
            parent=self.db.execute('SELECT id,agent,status,result FROM jobs WHERE project=? AND id=?',(pid,row['dependency'])).fetchone()
            if parent:pending.append({'connection':None,'instructions':'Az előző lépés eredménye','task':row['prompt'],'parent':dict(parent),'received':bool(runtime and runtime['input'])})
        result['handoffs']=pending
        return result
