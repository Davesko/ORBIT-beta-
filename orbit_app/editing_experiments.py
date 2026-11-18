"""One project experiment at a time; assignments and actual edit traits remain auditable."""
import hashlib,json,time,uuid

def schema(s):
 s.db.executescript('''CREATE TABLE IF NOT EXISTS editing_experiments(id TEXT PRIMARY KEY,project TEXT,parameter TEXT,baseline TEXT,recommendation TEXT,status TEXT,created REAL); CREATE UNIQUE INDEX IF NOT EXISTS one_edit_experiment ON editing_experiments(project) WHERE status='active'; CREATE TABLE IF NOT EXISTS editing_assignments(run TEXT PRIMARY KEY,experiment TEXT,variation TEXT,topic TEXT,created REAL);''')
def fingerprint(style):
 keys=('target_seconds','min_seconds','max_seconds','caption_position','highlight_color','portrait_framing','language')
 return json.dumps({k:style.get(k) for k in keys},sort_keys=True)
def assign(s,pid,run,topic,style,feedback):
 """Caller owns the production transaction; no schema mutation or commit here."""
 rec=feedback.get('recommendation',{});active=s.db.execute("SELECT * FROM editing_experiments WHERE project=? AND status='active'",(pid,)).fetchone();baseline=fingerprint(style)
 if active and active['baseline']!=baseline:
  s.db.execute("UPDATE editing_experiments SET status='settings_changed' WHERE id=?",(active['id'],));active=None
 if not active and rec.get('status')=='exploratory_test' and rec.get('sample_size',0)>=3 and rec.get('change') in ('hook_mechanism','setup_density'):
  eid=uuid.uuid4().hex;s.db.execute('INSERT INTO editing_experiments VALUES(?,?,?,?,?,?,?)',(eid,pid,rec['change'],baseline,json.dumps(rec),'active',time.time()));active=s.db.execute('SELECT * FROM editing_experiments WHERE id=?',(eid,)).fetchone()
 if not active:return None
 n=s.db.execute('SELECT count(*) FROM editing_assignments WHERE experiment=?',(active['id'],)).fetchone()[0];variation='control' if n%2==0 else 'test'
 s.db.execute('INSERT INTO editing_assignments VALUES(?,?,?,?,?)',(run,active['id'],variation,topic,time.time()))
 recommendation=json.loads(active['recommendation']);instruction=recommendation.get('instruction','') if variation=='test' else 'Control condition: retain the ordinary grounded editing approach. Do not apply the experimental hook/setup recommendation. Keep captions and duration settings unchanged.'
 return dict(id=active['id'],parameter=active['parameter'],variation=variation,instruction=instruction,baseline=json.loads(active['baseline']),caption_theme='clean',assessment='One requested editorial change; not proof of successful implementation or causality.')
def traits(data):
 shots=data.get('montage',{}).get('shots',[])
 return dict(hook_seconds=round(shots[0]['end']-shots[0]['start'],3) if shots else None,setup_seconds=round(sum(s['end']-s['start'] for s in shots if s.get('beat')=='context'),3),caption_theme=data.get('montage',{}).get('caption_theme'),render_segments=data.get('pacing',{}).get('render_segments'),experiment=data.get('experiment'))
def summarize(s,pid,videos):
 schema(s);row=s.db.execute("SELECT * FROM editing_experiments WHERE project=? ORDER BY created DESC LIMIT 1",(pid,)).fetchone()
 if not row:return dict(status='collecting',reason='Kísérlet akkor indul, ha van elég összehasonlítható nézési adat. Egyszerre egy szerkesztési tulajdonságot tesztelünk.')
 from short_feedback import number
 eligible=[v for v in videos if (v.get('experiment') or {}).get('id')==row['id'] and v.get('status')=='processed' and 24<=v.get('age_hours',0)<=72 and (number(v.get('engaged_views')) or 0)>=100 and number(v.get('average_view_percentage')) is not None]
 groups={}
 for variation in ('control','test'):
  values=[v for v in eligible if (v.get('experiment') or {}).get('variation')==variation];groups[variation]=dict(count=len(values),average_view_percentage=round(sum(v['average_view_percentage'] for v in values)/len(values),2) if values else None)
 comparable=[]
 for a in eligible:
  peers=[b for b in eligible if b.get('topic')==a.get('topic') and (b.get('experiment') or {}).get('variation')!=(a.get('experiment') or {}).get('variation') and (number(a.get('duration')) or 0)>0 and .75<=((number(b.get('duration')) or 0)/a['duration'])<=1.33]
  if peers:comparable.append(a)
 sufficient=all(sum((v.get('experiment') or {}).get('variation')==k for v in comparable)>=3 for k in groups)
 return dict(id=row['id'],status='observational_result' if sufficient else row['status'],parameter=row['parameter'],groups=groups,reason='Van összehasonlítható eredmény; ez megfigyelés, nem bizonyított ok-okozati hatás.' if sufficient else 'Várunk legalább 3–3 hasonló témájú, hosszúságú és korú kontroll- és tesztvideó nézési adataira.',causal=False)
