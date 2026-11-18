"""Persistent domain-independent business R&D. Receipts, drafts and explicit uncertainty."""
import ast,json,re,time,uuid
from pathlib import PurePosixPath
PID='orbit-business-lab'
ORIGIN='orbit:business-lab'
GOAL='Find, design and build 100% fully automated, software-driven digital businesses (AI micro-SaaS, automated content/data pipelines, algorithmic arbitrage, programmatic SEO networks, API-first micro-services) that AI agents can build, run, maintain and continuously improve with zero to minimal human intervention. Revenue is unknown until verified.'
RESEARCH='''You are an expert Autonomous AI Business Architect, Software Engineer and Systems Operator. In this cycle research ONE 100% fully automated, software-driven digital business in the scouting category given in the context (print-on-demand graphics, printable colouring pages and templates, AI micro-SaaS, automated content/data pipelines, algorithmic arbitrage, programmatic SEO networks, API-first micro-services, developer tools, automated media generation and similar). ORBIT can draw images itself with its local image model, so products it makes completely itself and that a marketplace sells (it prints, takes the payment and ships) are especially relevant.
CRITICAL CONSTRAINTS: (1) No human in the loop: reject anything that needs human physical presence, 1-on-1 calls, manual consulting, physical logistics or human customer support. (2) 100% automatable pipeline: market research, data collection, core processing, product generation, deployment, distribution and self-monitoring must run via Python scripts, APIs, LLM calls and webhooks. (3) Self-improving feedback loop: telemetry, error handling, user-feedback analysis and continuous prompt/code optimization are part of the design. (4) Low operational overhead: high margin, minimal paid API cost (local Ollama models, efficient routing), low-maintenance infrastructure.
Use web_search/read_web for real demand evidence (competitors and their prices, search interest, communities asking for it) and cite the actual returned URLs. Call tools through the tool interface, never by printing JSON. Read previous cycle evidence and operator direction; do not repeat known ideas. Write the brief in Hungarian, covering: 1) system overview and value proposition (concept and category, problem and automated solution, target audience and monetization); 2) end-to-end architecture (data ingestion and trigger, processing and AI logic, output and delivery channel); 3) autonomous operations (automated QA and error handling, self-optimization from metrics); 4) feasibility (tech stack, running costs versus revenue potential, a fully automated 48-hour validation test). Distinguish evidence from hypotheses; never fabricate demand, metrics or income. Accounts, payments, domains and publishing remain owner actions; design everything else to run unattended.'''
BUILD='''You are an expert Autonomous AI Business Architect and Software Engineer. Turn the research into ONE concrete, 100% automated, software-driven business design (no human in the loop, every phase automatable with Python, APIs, LLM calls and webhooks, a self-improving feedback loop, low running cost with local models where possible). Prefer products ORBIT can make completely itself (code, text, and images from its local image model) and sell through a platform that takes the payment and delivers (print-on-demand marketplaces, Etsy or Gumroad downloads, Amazon KDP); use business_type digital for those. Follow the scouting category in the context and propose a NEW idea there (idea_id "new"); a translation or rewording of a known idea is not new. If the researched idea needs manual work, redesign it to remove the human or replace it. Write every text value in Hungarian (keep product names and URLs as they are). Return JSON only: {"business_type":"saas|digital|trading|toolkit","category":"AI micro-SaaS|print-on-demand graphics|printables|content pipeline|data pipeline|programmatic SEO|API micro-service|developer tool|media generation|algorithmic arbitrage|other","idea_id":"the idea_id from known_ideas when you revise that idea (keep its exact name too), or \"new\"","name":"concept name","problem":"problem","offer":"the automated solution","buyer":"target audience","revenue_model":"monetization (Stripe subscription, pay-per-use, ads, affiliate) – unverified","architecture":{"ingestion":"data ingestion and trigger (cron, webhook, RSS, API)","processing":"processing and AI logic (which local/remote models and agents)","delivery":"output and automatic delivery channel"},"autonomy":{"qa":"automated QA and error handling (hallucination, API failure, broken output detection)","self_optimization":"metrics collected and how prompts/code/pipelines are refined automatically"},"tech_stack":"languages, APIs, hosting, databases","costs":"estimated monthly running costs","revenue_potential":"revenue potential with assumptions","validation":"a 100% automated 48-hour validation test with pass/fail metric","human_steps":["anything that would still need a human apart from the owner's one-time account, payment, domain and publishing setup; empty if none"],"automation_level":0-100,"evidence":["observed evidence with URL or explicitly unknown"],"hypothesis":"falsifiable assumption","progress":"what improved this cycle","decision":"continue|pivot|ready_for_validation","next_action":"next automated step","files":[{"name":"README.md","content":"system design brief in the four-part format"}]}. 1-3 files, each <=4500 characters, total <=8000; allowed .md .txt .json .py .html .css .js. These are local DRAFTS, not deployed. Never label model confidence as proven demand, never fabricate transactions or metrics, never purchase, send messages or publish.'''
REVIEW='Independently criticize the business design. First check the hard constraints: any human-in-the-loop step (manual delivery, calls, consulting, logistics, human support), any phase that cannot run from Python/APIs/LLMs/webhooks, a missing or vague self-improvement loop, or running costs that erase the margin. Then judge unsupported demand, weak differentiation, overoptimistic revenue and self-confirmation. Specify the next concrete improvement or pivot and a measurable automated acceptance test. Do not equate an attractive plan or syntax-valid file with a working business. Return a short Hungarian summary with evidence, violated constraints, unresolved questions and next action. Before scoring, use web_search to look for what already solves this problem for the buyer: free tools, government or official systems (for example tax-authority services), built-in features of software they already use, and big-vendor APIs; name what you found. Start your reply with one line exactly in this form, and repeat it as the last line: SCORE demand=N competition=N margin=N automation=N speed=N solved=N (each 1-5; 5 is best for the first five; competition=5 means little competition, speed=5 means it can be validated within days; solved=5 means a free, official or already-used solution fully solves it, solved=1 means nothing does). Demand above 2 needs concrete evidence such as paying competitors, real search or community requests; generic market-size reports score at most 2.'
PROMPTS=dict(research=RESEARCH,build=BUILD,review=REVIEW)
# Preferred first: the smartest local model that fits this Mac; the 9B is the fallback.
MODELS=('qwen3.8:27b-q4_K_M','qwen3.8:27b','qwen3.5:9b')
MODEL=MODELS[-1]

FAST_MODELS=('qwen3.5:9b',)
def pin_model(s):
 """Fixed models instead of 'auto' routing (which swapped between four models mid-cycle and
 caused most timeouts). The builder and the critic get the strongest model; the planner only
 summarises search results and picks the next milestone, so it runs on the ~3x faster 9B:
 one model swap per cycle. A planner retry runs on the strong model (see retry_model)."""
 try:
  from model_hub import models
  installed={m['name'] for m in models()}
 except Exception:return
 strong=next((m for m in MODELS if m in installed),'auto');fast=next((m for m in FAST_MODELS if m in installed),strong)
 changed=s.db.execute('UPDATE agents SET model=? WHERE project=? AND name IN (?,?) AND model!=?',(strong,PID,'Építő','Kritikus',strong)).rowcount
 changed+=s.db.execute('UPDATE agents SET model=? WHERE project=? AND name=? AND model!=?',(fast,PID,'Piackutató',fast)).rowcount
 if changed:s.db.commit()

def retry_model(s):
 """The strong model, for a step whose fast-model attempt failed its contract."""
 return s.db.execute("SELECT model FROM agents WHERE project=? AND name='Építő'",(PID,)).fetchone()[0]

def cycle_mode(s,cycle):
 """Decide build/explore once per cycle so planner, builder and critic work on the same thing."""
 import venture_build
 path=s.safe_path(PID,'workspace/ventures/cycle-modes.json')
 try:modes=json.loads(path.read_text())
 except (OSError,ValueError):modes={}
 key=str(cycle)
 if key not in modes:
  modes[key]=venture_build.plan_cycle(s,cycle)
  keep=sorted(modes,key=lambda k:int(k) if k.isdigit() else 0)[-40:]
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({k:modes[k] for k in keep}))
 return modes[key]

def prompt_for(s,node,default,cycle=0):
 import venture_build
 pin_model(s)
 mode=cycle_mode(s,cycle) if cycle else ('build' if venture_build.active(s) else 'explore')
 if mode=='build' and not venture_build.active(s):mode='explore'  # legacy record without an idea id
 if mode.startswith('maintain:'):return venture_build.MAINTAIN_PROMPTS.get(node,default)
 return (venture_build.PROMPTS if mode.startswith('build') else PROMPTS).get(node,default)

def cycle_focus(s,cycle):
 """The product a cycle works on: the current build, a finished product being improved, or none."""
 import venture_build
 mode=cycle_mode(s,cycle) if cycle else ('build' if venture_build.active(s) else 'explore')
 if mode.startswith('maintain:'):return venture_build.focus_for(s,mode.split(':',1)[1])
 # A cycle finishes the product it started on, even if the operator switched meanwhile.
 if mode.startswith('build:'):return venture_build.active(s) if (venture_build.read(s) or {}).get('idea_id')==mode[6:] and venture_build.active(s) else venture_build.focus_for(s,mode[6:])
 return venture_build.active(s) if mode=='build' else None
OPEN_GAP='Még nincs meghatározva – a következő ciklus pótolja.'

def plain(value):
 """Models often answer a text field with a small table ({"hosting":"20 USD",...}); keep it readable."""
 if isinstance(value,dict):return '; '.join(f'{k}: {plain(v)}' for k,v in value.items())
 if isinstance(value,list):return '; '.join(plain(v) for v in value)
 return '' if value is None else str(value)

HUMAN=('manual','manuális','konzult','consult','coach','1-on-1','személyes','telefon','phone call','fizikai','raktár','warehouse','ügyfélszolgálat','customer support','tanácsadó','tanácsadás','jóváhagy','approval','approve','human review','emberi ellenőrzés','kézi ')
# Publishing stays the owner's step by rule (ORBIT never publishes), so uploading to a marketplace is no recurring
# human work in the product's delivery: the marketplace prints, takes the payment and ships.
SETUP=('egyszeri','one-time','one time','setup','beállítás','fiók','account','regisztr','api key','api-kulcs','kulcs','domain','token','feltölt','upload','közzété','publish','listáz','listing')
def automated(plan):
 """A plan qualifies for automatic implementation only if no human works in its delivery.
 The model's own automation_level is not enough: an offer that needs approvals, calls or
 manual work in normal operation is rejected even when rated highly."""
 level=plan.get('automation_level')
 # The owner's one-time setup (accounts, keys, domain) is allowed; recurring human work is not.
 steps=plan.get('human_steps') or []
 if isinstance(steps,str):steps=[steps]
 if any(not any(w in str(x).casefold() for w in SETUP) or any(w in str(x).casefold() for w in HUMAN) for x in steps):return False
 # 'problem' describes the customer's manual work today, not how the product is delivered;
 # plain 'hívás' is also an API call ('5 Ft/hívás'), so only 'telefon…' marks phone work.
 text=' '.join(str(plan.get(k) or '') for k in ('name','offer','revenue_model')).casefold()
 if any(w in text for w in HUMAN):return False
 if isinstance(level,(int,float)):return level>=85
 return None

def parse_plan(text):
 if isinstance(text,dict):value=text
 else:
  m=re.search(r'\{.*\}',str(text or ''),re.S)
  try:value=json.loads(m.group(0)) if m else None
  except ValueError:return None
 return value if isinstance(value,dict) and isinstance(value.get('name'),str) and len(value['name'].strip())>3 and value['name'].strip().casefold() not in ('new','idea name') and value.get('offer') else None

# Legacy plans had no idea_id and alternate Hungarian/English names for one business.
STEMS=(('táplálkoz','nutrition'),('nutrition','nutrition'),('étrend','nutrition'),('diet','nutrition'),('marketing','marketing'),('hirdet','marketing'),('könyvel','accounting'),('accounting','accounting'),('fordít','translation'),('translat','translation'),('ügyfélszolg','support'),('support','support'),('oktat','education'),('tutor','education'),('education','education'),('ingatlan','realestate'),('real estate','realestate'),('egészség','health'),('fitness','fitness'),('edzés','fitness'),('recept','recipe'),('recipe','recipe'),('webshop','ecommerce'),('e-commerce','ecommerce'),('ecommerce','ecommerce'),('jog','legal'),('legal','legal'),('hr ','hr'),('recruit','hr'),('toboroz','hr'),('video','video'),('videó','video'),('content','content'),('tartalom','content'))
def topics(name):
 text=' '+str(name).casefold()+' '
 return {topic for stem,topic in STEMS if stem in text}

def same_idea(a,b):
 x,y=topics(a),topics(b)
 if x and y:return len(x&y)/len(x|y)>=.5
 return str(a).strip().casefold()==str(b).strip().casefold()

def known_ideas(s,pid):
 """Ideas saved so far (newest first) with stable ids, read from the versioned result files."""
 ideas=[]
 root=s.safe_path(pid,'workspace/ventures')
 files=sorted(root.glob('*/result.json'),key=lambda f:f.stat().st_mtime,reverse=True) if root.is_dir() else []
 for f in files:
  try:v=json.loads(f.read_text())
  except (OSError,ValueError):continue
  if v.get('mode')=='build':continue
  iid=v.get('idea_id');name=v.get('name','')
  hit=next((i for i in ideas if (iid and i['idea_id']==iid) or (not iid and same_idea(i['name'],name))),None)
  # Files come newest first, so the last version seen is the idea's first appearance.
  if hit:hit['versions']+=1;hit['first']=f.stat().st_mtime
  else:ideas.append(dict(idea_id=iid or f.parent.name[:8],name=name,decision=v.get('decision'),versions=1,automated=automated(v),first=f.stat().st_mtime))
 return ideas

def assign_idea(s,pid,value):
 known=known_ideas(s,pid);asked=str(value.get('idea_id') or '').strip()
 hit=next((i for i in known if i['idea_id']==asked),None) or next((i for i in known if same_idea(i['name'],value.get('name',''))),None)
 return hit['idea_id'] if hit else uuid.uuid4().hex[:8]

def printed_call(text):
 import re
 return len(text)<800 and bool(re.match(r'\s*(?:```(?:json)?)?\s*\{\s*"name"\s*:',text)) and '"arguments"' in text

def history(s,mid,limit=500):
 """Every cycle's real work for the operator: research brief, plan or its blocker, critique."""
 runs=s.rows('SELECT id,cycle,status,error,created,finished FROM orbit_mission_runs WHERE mission=? ORDER BY cycle DESC LIMIT ?',(mid,limit))
 cycles=[];ideas={}
 for run in runs:
  item=dict(run=run['id'],cycle=run['cycle'],status=run['status'],error=(run['error'] or '')[:400],created=run['created'],finished=run['finished'])
  for st in s.rows('SELECT node,state,result,error FROM orbit_mission_steps WHERE run=?',(run['id'],)):
   content=json.loads(st['result'] or '{}').get('content')
   if st['node']=='build' and isinstance(content,dict) and content.get('mode')=='build':
    item['milestone']={k:content.get(k) for k in ('milestone_id','title','summary','status','idea','idea_id')}
    item['milestone']['files']=[f.split('/')[-1] for f in content.get('files',[])]
    item['build']=dict(state=st['state'],error='')
   elif st['node']=='build':
    plan=parse_plan(content) if st['state']=='done' else None
    if plan is None:
     # A rejected plan is still work the operator should see; read the builder's own answer.
     job=s.db.execute("SELECT result FROM jobs WHERE kind='mission_agent' AND json_extract(payload,'$.mission_run')=? AND json_extract(payload,'$.mission_node')='build' AND project=? AND +status='done' ORDER BY created DESC LIMIT 1",(run['id'],PID)).fetchone()
     plan=parse_plan(job[0]) if job else None
    item['build']=dict(state=st['state'],error=(st['error'] or '')[:300])
    if plan:
     brief={k:plain(plan.get(k))[:900] for k in ('name','category','problem','buyer','offer','revenue_model','architecture','autonomy','tech_stack','costs','revenue_potential','hypothesis','validation','progress','next_action','decision','business_type','automation_level','human_steps')}
     brief['evidence']=[plain(x)[:400] for x in (plan.get('evidence') or [])[:8]] if isinstance(plan.get('evidence'),list) else []
     files=plan.get('files') or []
     brief['files']=[f if isinstance(f,str) else dict(name=str(f.get('name',''))[:80],preview=str(f.get('content',''))[:1500]) for f in files[:4] if isinstance(f,(str,dict))]
     brief['saved']=st['state']=='done';item['idea']=brief
     iid=plan.get('idea_id') if plan.get('idea_id') not in (None,'','new') else None
     key=next((k for k,v in ideas.items() if (iid and v.get('idea_id')==iid) or same_idea(v['name'],brief['name'])),None)
     if key is None:ideas[len(ideas)]=dict(brief,idea_id=iid,cycles=[run['cycle']],versions=1,names=[brief['name']])
     else:
      g=ideas[key];g['cycles'].append(run['cycle']);g['versions']+=1;g['saved']=g['saved'] or brief['saved']
      g['idea_id']=g.get('idea_id') or iid
      if brief['name'] not in g['names']:g['names'].append(brief['name'])
   elif isinstance(content,str) and st['state']=='done':
    # A printed tool call is not research; say so instead of showing raw JSON.
    item[st['node']]='A kutató ebben a körben nem adott értékelhető összefoglalót (eszközhívást írt ki szöveg helyett).' if printed_call(content) else content[:2000]
   else:item[st['node']+'_state']=st['state']
  cycles.append(item)
 return cycles,list(ideas.values())

def context(s,mission,pid,cycle=0):
 import venture_build
 f=cycle_focus(s,cycle)
 if f:return venture_build.context(s,mission,f)
 direction=(venture_build.read(s) or {}).get('next_direction') or mission.get('goal','').partition('Operator direction: ')[2]
 label,hint=('Operator-directed research',direction) if direction else venture_build.sector(cycle)
 scout=dict(sector=label,sector_focus=hint,rule='Find a NEW opportunity in this sector this cycle. Do not repeat or reword any idea in known_ideas; use idea_id "new".')
 rows=s.rows("SELECT st.result FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.state='done' ORDER BY r.cycle DESC,st.updated DESC LIMIT 6",(mission['id'],))
 previous=[]
 for row in rows:
  value=json.loads(row['result']).get('content',{})
  if isinstance(value,dict):
   # Project-relative paths let the builder read_file its own earlier drafts instead of restarting.
   value=dict(value,files=[f.split('/projects/'+pid+'/',1)[-1] for f in value.get('files',[])])
  if len(json.dumps(previous+[value]))<=5000:previous.append(value)
 return dict(goal=GOAL+(('\nOperator direction: '+direction) if direction else ''),scouting=scout,known_ideas=known_ideas(s,pid)[:30],previous=previous,recent_failures=s.rows("SELECT st.node,st.error FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.error!='' ORDER BY st.updated DESC LIMIT 3",(mission['id'],)),projects=s.rows('SELECT id,name,description FROM projects'),avoid_recent_failures=pitfalls(s,mission['id']),revenue='unverified',instruction='Continue saved work; previous model statements are hypotheses unless backed by actual evidence. Use read_file on the listed previous files to improve them rather than rewriting from scratch.')

# Recurring failures turned into one concrete instruction each for the next cycles.
PITFALLS=(
 (('Legfeljebb 4',),'Return at most 4 files per result; put the rest in the next cycle.'),
 (('EOF while','EOL while','unexpected EOF','triple-quoted','invalid syntax','unterminated'),'Generated code was cut off or had an unclosed string: close every string, bracket and triple quote; prefer fewer, shorter, complete files over long ones.'),
 (('érvényes ügynökeredmény','üres választ','nem teljes JSON'),'Answer with the complete JSON result object itself, not only reasoning or a plan of what you will write.'),
 (('bizonyíték',),'Evidence must be a flat list of short strings.'),
 (('Ismeretlen mérföldkő',),'Use a milestone_id exactly as listed in the roadmap.'),
 (('Nem engedélyezett fájl',),'Use only the allowed file types and names.'),
)
def pitfalls(s,mid,days=3):
 """The lab's own recent failure messages, counted and mapped to advice (newest knowledge first)."""
 rows=s.rows("SELECT detail FROM orbit_mission_events WHERE mission=? AND kind IN ('retry_scheduled','attention') AND created>?",(mid,time.time()-days*86400))
 seen={}
 for r in rows:
  try:err=json.loads(r['detail']).get('error','')
  except ValueError:continue
  for keys,advice in PITFALLS:
   if any(k in err for k in keys):seen[advice]=seen.get(advice,0)+1;break
 return [dict(times=n,advice=a) for a,n in sorted(seen.items(),key=lambda x:-x[1])][:4]

NO_WORK='Nincs elkészült munka: a válasz csak leírás volt, edits/files nélkül. Add vissza a teljes JSON-t (milestone_id, edits: [{name, find, replace}] vagy files, summary), és a leírt javítást csere-blokkal végezd el.'

def save_result(s,pid,run,value):
 import venture_build
 # In a build cycle an answer with files or edits is a build result even without milestone_id: a
 # reply cut at its length limit lost the id at its end and was then rejected as a business plan.
 if isinstance(value,dict) and (value.get('milestone_id') or (value.get('files') or value.get('edits')) and not (value.get('name') or value.get('offer'))):
  row=s.db.execute('SELECT cycle FROM orbit_mission_runs WHERE id=?',(run,)).fetchone()
  f=cycle_focus(s,row[0] if row else 0)
  if f:return venture_build.save(s,run,value,f,enforce=True)
 if not isinstance(value,dict):raise ValueError('Strukturált üzleti kísérlet szükséges.')
 if not (value.get('name') or value.get('offer')):
  row=s.db.execute('SELECT cycle FROM orbit_mission_runs WHERE id=?',(run,)).fetchone()
  # A build answer that only described its fix ({"text": "A hibát … megtaláltam …"}, cycle 220) was read as a
  # business plan, and the retry was told "Hiányos üzleti terv: name", which points a builder the wrong way.
  if cycle_focus(s,row[0] if row else 0):raise ValueError(NO_WORK)
 result={};missing=[]
 for key in ('name','problem','buyer','offer','revenue_model','costs','hypothesis','validation','progress','next_action'):
  v=value.get(key)
  if isinstance(v,(list,dict)):v=plain(v)
  if isinstance(v,str) and len(v.strip())>1600:v=v.strip()[:1597]+'…'
  if not isinstance(v,str) or len(v.strip())<2:
   # The idea and offer are the work itself; other gaps are recorded and filled next cycle
   # instead of discarding a whole cycle of research and drafts.
   if key in ('name','offer'):raise ValueError('Hiányos üzleti terv: '+key)
   missing.append(key);v=OPEN_GAP
  result[key]=v.strip()
 result['missing_fields']=missing;result['idea_id']=assign_idea(s,pid,value)
 for key in ('category','architecture','autonomy','tech_stack','revenue_potential'):
  if value.get(key) not in (None,'',{},[]):result[key]=plain(value[key])[:1600]
 steps=value.get('human_steps');result['human_steps']=[plain(x)[:300] for x in steps[:8]] if isinstance(steps,list) else []
 level=value.get('automation_level');result['automation_level']=max(0,min(100,int(level))) if isinstance(level,(int,float)) else None
 result['automated']=automated(result)
 bt=value.get('business_type');result['business_type']=bt if bt in ('service','dropshipping','trading','toolkit') else None
 result['decision']=value.get('decision') if value.get('decision') in ('continue','pivot','ready_for_validation') else 'continue';evidence=value.get('evidence',[])
 # Evidence often comes as {"source":..,"url":..} objects or a single string; keep it readable.
 if not isinstance(evidence,list):evidence=[evidence] if evidence else []
 result['evidence']=[plain(x)[:1600] for x in evidence[:12] if plain(x).strip()]
 files=value.get('files')
 if not isinstance(files,list):raise ValueError('Legfeljebb 4 konkrét eredményfájl adható meg.')
 validated=[];names=set();total=0;broken=[]
 # The builder often names an earlier draft by its project path; the revision is saved by
 # file name, and a repeated name keeps the last (most revised) version.
 picked={}
 for f in files:
  if isinstance(f,dict) and isinstance(f.get('name'),str) and '..' not in f['name'] and not f['name'].startswith('/'):picked[PurePosixPath(f['name']).name]=dict(f,name=PurePosixPath(f['name']).name)
  elif not isinstance(f,str):picked[str(len(picked))+'?']=f if isinstance(f,dict) else {}
  # A bare name refers to an existing draft that was not revised this cycle.
 # Extra files cost the whole ~80-minute cycle when rejected; keep the first four instead.
 picked=dict(list(picked.items())[:4])
 for f in picked.values():
  name=f.get('name','');content=f.get('content');path=PurePosixPath(name)
  if path.name!=name or '\\' in name or path.suffix not in ('.md','.txt','.json','.py','.html','.css','.js') or name in names:raise ValueError('Érvénytelen vagy ismételt fájlnév.')
  if not isinstance(content,str) or not 2<=len(content)<=12000:raise ValueError('Üres vagy túl nagy fejlesztési fájl.')
  # A draft with a broken quote is still the cycle's work: keep it, flag it for the next cycle.
  try:
   if path.suffix=='.py':ast.parse(content)
   if path.suffix=='.json':json.loads(content)
  except (SyntaxError,ValueError) as exc:broken.append(name+': '+str(exc)[:120])
  names.add(name);total+=len(content);validated.append((name,content))
 if total>24000:raise ValueError('Túl nagy munkacsomag.')
 # Deterministic revision path makes reconciliation replay idempotent.
 folder=s.safe_path(pid,'workspace/ventures/'+run);folder.mkdir(parents=True,exist_ok=True)
 for name,content in validated:
  target=folder/name;target.write_text(content)
  if not s.db.execute('SELECT 1 FROM artifacts WHERE project=? AND path=?',(pid,str(target))).fetchone():s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,name,str(target),'text',time.time(),None))
 result.update(broken_files=broken,files=[str(folder/n) for n,_ in validated],revenue_status='unverified',validation_status='draft_only',created=time.time())
 (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));s.db.commit()
 import venture_build
 venture_build.note_idea(s,result)
 return result

CACHE_RATE=150

def pace(s,mid,hours=6):
 """Average cycle and step minutes over the last day, so every speed-up is visible and measured."""
 since=time.time()-hours*3600
 runs=s.rows("SELECT finished-created AS d FROM orbit_mission_runs WHERE mission=? AND status='done' AND finished>=?",(mid,since))
 if not runs:return None
 steps={r['node']:round(r['m'],1) for r in s.rows("""SELECT json_extract(payload,'$.mission_node') AS node,avg(finished-started)/60.0 AS m FROM jobs
  WHERE kind='mission_agent' AND status='done' AND finished>=? AND json_extract(payload,'$.mission_run') IN (SELECT id FROM orbit_mission_runs WHERE mission=?) GROUP BY node""",(since,mid)) if r['node']}
 # Measured token use per step: the largest prompt and reply, and how often a reply hit its cap.
 tokens={}
 for r in s.rows("""SELECT json_extract(payload,'$.mission_node') AS node,payload FROM jobs WHERE kind='mission_agent' AND status='done' AND finished>=?
  AND json_extract(payload,'$.mission_run') IN (SELECT id FROM orbit_mission_runs WHERE mission=?)""",(since,mid)):
  rounds=json.loads(r['payload']).get('rounds') or []
  if not rounds or not r['node']:continue
  t=tokens.setdefault(r['node'],dict(jobs=0,max_prompt=0,max_output=0,capped=0,later_rounds=0,cache_hits=0))
  t['jobs']+=1;t['max_prompt']=max(t['max_prompt'],*(x.get('prompt') or 0 for x in rounds));t['max_output']=max(t['max_output'],*(x.get('output') or 0 for x in rounds))
  t['capped']+=sum(x.get('stop')=='length' for x in rounds)
  # A later round that read its prompt far faster than a fresh read (~45-70 tokens/s on the 27B)
  # reused the server's cached prefix.
  later=[x for x in rounds[1:] if x.get('read_s') is not None and x.get('prompt')]
  t['later_rounds']+=len(later);t['cache_hits']+=sum(x['prompt']/max(x['read_s'],.1)>CACHE_RATE for x in later)
 return dict(hours=hours,cycles=len(runs),minutes=round(sum(r['d'] for r in runs)/len(runs)/60),steps=steps,tokens=tokens)

def status_head(s):
 """The control bar only needs the mission and the latest step states."""
 if not s.db.execute("SELECT 1 FROM sqlite_master WHERE name='orbit_missions'").fetchone():return None
 row=s.db.execute('SELECT id,status,next_run,updated FROM orbit_missions WHERE origin=?',(ORIGIN,)).fetchone()
 if not row:return None
 data=dict(row)
 run=s.db.execute('SELECT id,cycle,status FROM orbit_mission_runs WHERE mission=? ORDER BY cycle DESC LIMIT 1',(row['id'],)).fetchone()
 data['run']=dict(run) if run else None
 data['steps']=s.rows('SELECT node,state,updated FROM orbit_mission_steps WHERE run=?',(run['id'],)) if run else []
 from missions import production_active
 data['paused_for_video']=row['status']=='active' and production_active(s)
 try:cached=json.loads((s.root/'ssd-hung.json').read_text())
 except (OSError,ValueError):cached={}
 data['waiting_for_ssd']=row['status']=='active' and time.time()-cached.get('at',0)<60 and bool(cached.get('hung'))
 return data

def status(s,compact=False):
 from missions import schema,listing
 schema(s);row=s.db.execute('SELECT id FROM orbit_missions WHERE origin=?',(ORIGIN,)).fetchone()
 if not row:return None
 m=next((m for m in listing(s,PID,not compact)['missions'] if m['id']==row[0]),None)
 if m:
  import venture_build
  m['next_direction']=(venture_build.read(s) or {}).get('next_direction','')
  if not compact:m['summary']=summary(s,m['id'])
  m['scope']='business_lab'
  from missions import production_active
  m['paused_for_video']=m['status']=='active' and production_active(s)
  from missions import ssd_waiting
  m['waiting_for_ssd']=m['status']=='active' and ssd_waiting(s)
  m['cycles_done']=s.db.execute("SELECT count(*) FROM orbit_mission_runs WHERE mission=? AND status='done'",(m['id'],)).fetchone()[0]
  cycles,m['ideas']=history(s,m['id']);m['cycles']=cycles[:30]
  steps={x['node']:x['state'] for x in m.get('steps') or []}
  m['feed']=activity(m['cycles'],steps)
  m['pace']=pace(s,m['id'])
  known=known_ideas(s,PID)
  for i in m['ideas']:
   if not i.get('idea_id'):i['idea_id']=next((k['idea_id'] for k in known if same_idea(k['name'],i['name'])),None)
  sc=idea_scores(s,m['id'])
  for i in m['ideas']:i['score']=sc.get(i.get('idea_id'))
  import venture_build
  saved=venture_build.read(s) or {}
  f=(saved if saved.get('mode')=='build' else None) if compact else venture_build.active(s)
  m['mode']='build' if f else 'explore'
  m['focus']=venture_build.view(s,m['id'],f) if f else None
  cyc=(m.get('run') or {}).get('cycle')
  try:m['cycle_mode']=json.loads(s.safe_path(PID,'workspace/ventures/cycle-modes.json').read_text()).get(str(cyc))
  except (OSError,ValueError):m['cycle_mode']=None
  m['portfolio']=[]
  for iid in (() if compact else venture_build.portfolio(s)):
   pf=venture_build.focus_for(s,iid)
   if pf:
    v=venture_build.view(s,m['id'],pf)
    m['portfolio'].append({k:v[k] for k in ('idea_id','name','type_label','done','total','folder','previews','owner_actions','measurements','launch','traffic')})
  m['projects']=projects(s,m['id'],cycles,m['ideas'],f,known=known)
  if compact:m['portfolio']=[p for p in m['projects'] if p['state']=='finished']
  if m['focus']:m['focus']['work']=next((p['work'] for p in m['projects'] if p['idea_id']==m['focus'].get('idea_id')),None)
  r=venture_build.read(s) or {};m['explore_reason']=r.get('reason') if not f and r.get('auto_explore') else None
  try:
   import revenue
   m['revenue']=revenue.label(revenue.read(s))
  except Exception:m['revenue']=None
  if compact:return m
  m['latest_idea']=None;m['files_count']=0
  for row in s.rows("SELECT st.result FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.node='build' AND st.state='done' ORDER BY r.cycle DESC",(m['id'],)):
   value=json.loads(row['result']).get('content')
   if not isinstance(value,dict):continue
   m['files_count']+=len(value.get('files',[]))
   if m['latest_idea'] is None:m['latest_idea']={k:value.get(k) for k in ('name','buyer','offer','decision','next_action','progress')}
 return m

def project_cycles(cycles,f):
 """The cycles that built this product, newest first: its milestone builds and the research that named it."""
 return [c for c in cycles if (c.get('milestone') or {}).get('idea_id')==f['idea_id'] or same_idea((c.get('idea') or {}).get('name') or '',f['name'])]

def run_times(s,now=None):
 """How long the AI worked in each Autopilot cycle, by step: its jobs' running time, never the wait in the queue.
 A job still running counts up to now, in whole minutes, so the open page is not redrawn at every poll."""
 now=now or int(time.time()/60)*60;times={};active=set()
 for run,node,started,finished,status in s.db.execute("SELECT json_extract(payload,'$.mission_run'),json_extract(payload,'$.mission_node'),started,finished,status FROM jobs WHERE project=? AND kind='mission_agent' AND started IS NOT NULL",(PID,)):
  end=finished or (now if status=='running' else None)
  if run and end:
   parts=times.setdefault(run,{});parts[node or 'build']=parts.get(node or 'build',0)+max(0,end-started)
   if status=='running':active.add(run)
 return times,active

def drawing_seconds(s,f):
 """The time FLUX spent on the project's pictures, from when each started until its file was finished."""
 import venture_build
 total=count=0
 try:
  base=s.safe_path(PID,venture_build.folder(f)+'/designs');render=json.loads((base/'render.json').read_text())
 except (OSError,ValueError):return 0,0
 for design,entry in render.items():
  try:
   if entry.get('done'):total+=min(1800,max(0,(base/(design+'.png')).stat().st_mtime-entry['at']));count+=1
  except (OSError,KeyError,TypeError):pass
 return total,count

def project_work(s,f,own,clock=None):
 """The AI's total working time on one project. Which cycles belong to it is remembered, so the total survives the
 cycles falling out of the recent history."""
 s.db.execute('CREATE TABLE IF NOT EXISTS venture_work(run TEXT,idea TEXT,PRIMARY KEY(run,idea))')
 # Read first: this runs inside status reads, and an open write transaction would lock out the whole app.
 known={r[0] for r in s.db.execute('SELECT run FROM venture_work WHERE idea=?',(f['idea_id'],)).fetchall()}
 new=[(c['run'],f['idea_id']) for c in own if c.get('run') and c['run'] not in known]
 if new:
  s.db.executemany('INSERT OR IGNORE INTO venture_work VALUES(?,?)',new);s.db.commit()
 times,active=clock or run_times(s);parts={};running=False
 for row in s.db.execute('SELECT run FROM venture_work WHERE idea=?',(f['idea_id'],)).fetchall():
  for node,seconds in times.get(row[0],{}).items():parts[node]=parts.get(node,0)+seconds
  running=running or row[0] in active
 drawn,count=drawing_seconds(s,f)
 if drawn:parts['drawing']=drawn
 return dict(total=round(sum(parts.values())),parts={k:round(v) for k,v in parts.items()},drawn=count,running=running)

PROJECT_STATE={'building':'Most ezt építi','finished':'Elkészült','queued':'Sorra kerül','paused':'Félretéve'}

def projects(s,mid,cycles,ideas,focus,known=None):
 """Every idea the Autopilot has built files for, most recent work first, so the owner can open an
 earlier project too, not only the current one."""
 import venture_build
 r=venture_build.read(s) or {};out=[];clock=run_times(s)
 try:folders={p.name for p in s.safe_path(PID,'workspace').glob('product-*') if p.is_dir()}
 except (OSError,ValueError):return []
 scores={i.get('idea_id'):i.get('score') for i in ideas if i.get('idea_id')}
 for idea in (known_ideas(s,PID) if known is None else known):
  if venture_build.folder(idea).split('/')[-1] not in folders or any(p['idea_id']==idea['idea_id'] for p in out):continue
  f=dict(idea_id=idea['idea_id'],name=idea['name'])
  f['type']=venture_build.classify(venture_build.plan_text(s,f))
  ms,_=venture_build.progress(s,mid,f);own=project_cycles(cycles,f)
  state='building' if focus and focus['idea_id']==f['idea_id'] else 'finished' if f['idea_id'] in r.get('finished',[]) else 'queued' if f['idea_id'] in r.get('queue',[]) else 'paused'
  out.append(dict(idea_id=f['idea_id'],name=f['name'],type_label=venture_build.TYPES.get(f.get('type'),'Szolgáltatás'),state=state,state_label=PROJECT_STATE[state],
   done=sum(m['state'] in ('done','skipped') for m in ms),total=len(ms),cycles=len(own),last=max([c.get('finished') or c.get('created') or 0 for c in own] or [0]),score=(scores.get(f['idea_id']) or {}).get('total'),work=project_work(s,f,own,clock)))
 out.sort(key=lambda p:(p['state']!='building',-p['last']))
 return out

def project(s,idea_id):
 """One project's full page, as the current build shows it (steps, checks, previews, launch, owner
 to-dos), with its research and its own cycles: for opening earlier projects from the Autopilot page."""
 import venture_build
 row=s.db.execute('SELECT id FROM orbit_missions WHERE origin=?',(ORIGIN,)).fetchone()
 f=venture_build.focus_for(s,str(idea_id or ''))
 if not row or not f:raise ValueError('Ismeretlen projekt.')
 v=venture_build.view(s,row[0],f)
 cycles,ideas=history(s,row[0])
 v['work']=project_work(s,f,project_cycles(cycles,f))
 v['cycles']=project_cycles(cycles,f)[:40]
 v['idea']=next((i for i in ideas if i.get('idea_id')==f['idea_id'] or same_idea(i['name'],f['name'])),None)
 cur=venture_build.read(s) or {}
 v['current']=cur.get('mode')=='build' and cur.get('idea_id')==f['idea_id']
 return v

SCORE_KEYS=('demand','competition','margin','automation','speed')
def parse_score(text):
 """The critic's 1-5 ratings; None if the line is missing or malformed."""
 # The prose often says "score" too, so only a complete uppercase SCORE line counts (the last one).
 found=None
 for m in re.finditer(r'\bSCORE\b([^\n]*)',str(text or '')):
  vals={k.lower():int(v) for k,v in re.findall(r'(demand|competition|margin|automation|speed|solved)\s*[=:]\s*([1-5])',m.group(1),re.I)}
  # 'solved' (an existing free/official solution) is a veto, not part of the 25-point total.
  if set(SCORE_KEYS)<=set(vals):found=dict(vals,total=sum(vals[k] for k in SCORE_KEYS))
 return found

def idea_scores(s,mid):
 """Latest critic score per idea_id, from cycles where the plan and its critique ran together."""
 scores={}
 for run in s.rows('SELECT id,cycle FROM orbit_mission_runs WHERE mission=? ORDER BY cycle',(mid,)):
  steps={x['node']:x for x in s.rows('SELECT node,state,result FROM orbit_mission_steps WHERE run=?',(run['id'],))}
  b,r=steps.get('build'),steps.get('review')
  if not b or not r or b['state']!='done' or r['state']!='done':continue
  plan=json.loads(b['result'] or '{}').get('content');review=json.loads(r['result'] or '{}').get('content')
  if not isinstance(plan,dict) or plan.get('mode')=='build' or not plan.get('idea_id'):continue
  sc=parse_score(review)
  if sc:scores[plan['idea_id']]=dict(sc,cycle=run['cycle'])
 return measured_demand(s,scores)

def measured_demand(s,scores):
 """A real launch result outranks the critic's guess: passed -> demand 5, failed -> 1."""
 import venture_build,launch
 for iid in scores:
  st=launch.read_state(s,venture_build.folder(dict(idea_id=iid)))
  verdict=((st or {}).get('stats') or {}).get('verdict',{}).get('status')
  if verdict in ('passed','failed') and iid in scores:
   sc=dict(scores[iid],demand=5 if verdict=='passed' else 1,measured=verdict)
   sc['total']=sum(sc[k] for k in SCORE_KEYS);scores[iid]=sc
 return {iid:dict(sc,note=score_note(sc)) for iid,sc in scores.items()}

def score_note(sc):
 """What a score means, carried with it. The critic gave five ideas the same 1-2-2-4-3 without evidence,
 and the assistant presented that 12 (of 25) as a high score with broad demand."""
 parts=[str(sc['total'])+'/25, '+('a kereslet valódi oldalteszten mérve' if sc.get('measured') else 'a kritikus becslése, nem piaci adat')]
 if not sc.get('measured') and sc['demand']<=2:parts.append('nincs igazolt kereslet (kereslet '+str(sc['demand'])+'/5)')
 if sc['competition']<=2:parts.append('erős verseny (verseny '+str(sc['competition'])+'/5)')
 if 'solved' not in sc:parts.append('nem értékelte, megoldja-e már ingyenes vagy hivatalos eszköz')
 elif sc['solved']>=4:parts.append('valószínűleg már létezik ingyenes vagy hivatalos megoldás')
 return '; '.join(parts)

STEP_HU={'research':'kutat/tervez','build':'épít','review':'ellenőriz'}
def activity(cycles,running_steps=None):
 """Plain-language log: one line per cycle, newest first, so the operator sees what happened."""
 feed=[]
 for c in cycles:
  ms=c.get('milestone');idea=c.get('idea')
  if c['status']=='running':
   now=next((STEP_HU.get(k) for k,v in (running_steps or {}).items() if v in ('waiting','dispatching')),None)
   text=('Most '+now+': ' if now else 'Folyamatban: ')+(ms['title'] if ms else (idea or {}).get('name') or 'új kör');icon='▶'
  elif ms:
   verdict='javítandó' if re.search(r'VERDICT:\s*revise',c.get('review') or '',re.I) else 'elfogadva' if c.get('review') else 'elkészült'
   icon='–' if ms.get('status')=='skipped' else '🔨';text=('Kihagyta: ' if ms.get('status')=='skipped' else 'Megépítette: ')+ms['title']+(' · '+', '.join(ms.get('files') or []) if ms.get('files') else '')+(' · tesztelő: '+verdict if ms.get('status')!='skipped' else '')
  elif idea:
   icon='🔍';text='Ötletet dolgozott ki: '+idea['name']
  else:
   icon='⚠️';text='Elakadt, később újrapróbálja: '+(c.get('build',{}).get('error') or c.get('error') or 'nem készült eredmény')[:120]
  feed.append(dict(cycle=c['cycle'],at=c.get('finished') or c.get('created'),icon=icon,text=text,status=c['status']))
 return feed

def report(s):
 """What is measured about the Autopilot, for the main assistant to assess it from facts. Nothing here is a guess."""
 m=status(s)
 if not m:return dict(status='not_started')
 scored=sorted(m.get('ideas',[]),key=lambda i:-((i.get('score') or {}).get('total') or 0))
 ideas=[dict(name=i['name'][:80],type=i.get('business_type') or 'service',score=(i.get('score') or {}).get('total'),**{k:(i.get('score') or {}).get(k) for k in SCORE_KEYS},measured=(i.get('score') or {}).get('measured'),cycles=len(i.get('cycles',[])),problem=str(i.get('problem') or '')[:140],revenue_model=str(i.get('revenue_model') or '')[:100]) for i in scored[:12]]
 runs=s.rows('SELECT status,count(*) AS n FROM orbit_mission_runs WHERE mission=? GROUP BY status',(m['id'],))
 errors=[r['error'][:120] for r in s.rows("SELECT error FROM orbit_mission_runs WHERE mission=? AND status='failed' AND error!='' ORDER BY cycle DESC LIMIT 4",(m['id'],))]
 projects=[dict(name=p['name'][:60],type=p['type_label'],state=p['state_label'],steps=str(p['done'])+'/'+str(p['total']),cycles=p['cycles'],ai_hours=round(p['work']['total']/3600,1),score=p.get('score')) for p in m.get('projects',[])]
 f=m.get('focus') or {}
 live=[dict(name=p['name'][:60],launch=(p.get('launch') or {}).get('status'),verdict=(((p.get('launch') or {}).get('stats') or {}).get('verdict') or {}).get('status')) for p in m.get('portfolio') or []]
 return dict(status=m['status'],mode=m.get('mode'),revenue=m.get('revenue') or 'nincs igazolt bevétel',cycles_by_status={r['status']:r['n'] for r in runs},recent_failures=errors,score_scale='five criteria 1-5 each, total out of 25: '+', '.join(SCORE_KEYS)+'; given by its own critic unless measured says otherwise',ideas=ideas,projects=projects,launched=live,building=dict(name=f.get('name'),next=(f.get('next') or {}).get('title'),waiting_for_owner=[a['title'] for a in f.get('owner_actions',[])][:8]) if f else None,recent=[str(x['cycle'])+'. kör: '+x['text'][:120] for x in m.get('feed',[])[:6]])

def brief(s):
 """Small, plain state for the assistant: what runs now, what is being built, what happened."""
 m=status(s)
 if not m:return dict(status='not_started',next_direction=(__import__('venture_build').read(s) or {}).get('next_direction','') if s.db.execute('SELECT 1 FROM projects WHERE id=?',(PID,)).fetchone() else '',hint='Start with enterprise_save settings {"scope":"business_lab","enabled":true}.')
 now=next((dict(step=x['node'],state=x['state']) for x in m.get('steps') or [] if x['state'] in ('waiting','dispatching')),None)
 out=dict(next_direction=m.get('next_direction'),id=m.get('id'),status=m['status'],mode=m.get('mode'),cycle=(m.get('run') or {}).get('cycle'),cycles_done=m.get('cycles_done'),now=now,paused_for_video=m.get('paused_for_video'),
  ideas=[dict(idea_id=i.get('idea_id'),name=i['name'],type=i.get('business_type') or 'service',cycles=len(i.get('cycles',[])),score=(i.get('score') or {}).get('total')) for i in m.get('ideas',[])],
  feed=[str(f['cycle'])+'. kör: '+f['text'] for f in m.get('feed',[])[:10]],revenue=m.get('revenue') or 'nincs igazolt bevétel')
 live=lambda x:{k:(x or {}).get(k) for k in ('status','url')}|{'verdict':(((x or {}).get('stats') or {}).get('verdict') or {}).get('status')} if x else None
 out['portfolio']=[dict(name=p['name'],type=p['type_label'],done=p['done'],total=p['total'],launch=live(p.get('launch'))) for p in m.get('portfolio') or []]
 f=m.get('focus')
 if f:
  meas=f.get('measurements') or {}
  out['building']=dict(launch=(f.get('launch') or {}).get('status'),idea_id=f['idea_id'],name=f['name'],type=f['type_label'],done=f['done'],total=f['total'],
   milestones=[x['title']+': '+x['state'] for x in f['milestones']],owner_actions=[a['title'] for a in f['owner_actions']],queue=f.get('queue'),
   measured={k:{kk:v.get(kk) for kk in ('verdict','return_pct','profit_per_order','margin_pct','virtual_value','status') if kk in v} for k,v in meas.items() if isinstance(v,dict)})
 return out

def summary(s,mid):
 rows=s.rows('SELECT cycle,status,error FROM orbit_mission_runs WHERE mission=? ORDER BY cycle DESC',(mid,))
 latest=s.rows("SELECT st.node,st.state,st.result,st.error FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? ORDER BY r.cycle DESC,st.updated DESC LIMIT 9",(mid,))
 lines=['ORBIT üzleti műhely · '+str(sum(r['status']=='done' for r in rows))+' lezárt kutatási ciklus.']
 for st in latest:
  v=json.loads(st['result']).get('content')
  if isinstance(v,dict) and v.get('name'):
   lines+=['Ötlet: '+v['name'],'Előrelépés: '+v['progress'],'Következő lépés: '+v['next_action'],'Mentett fájlok: '+str(len(v.get('files',[])))];break
 review=next((json.loads(x['result']).get('content') for x in latest if x['node']=='review' and x['state']=='done'),None)
 if isinstance(review,str):lines.append(review[:2400])
 errors=[r['error'] for r in rows[:3] if r['error']]
 if errors:lines.append('Legutóbbi akadály: '+errors[0][:600])
 lines.append('Igazolt bevétel: még nincs adat. A tervek és prototípusok mentve; a következő indítás innen folytatódik.')
 return '\n\n'.join(lines)

def direction_for(s,idea_id):
 from venture_build import read
 return ((read(s) or {}).get('directions') or {}).get(idea_id,'')

def steer(s,target,direction,start=False):
 """Record an operator brief for the next scout or one product. Running cycles keep their target."""
 from venture_build import read,write,choose,focus_for
 from missions import schema
 schema(s)
 if not isinstance(direction,str) or not 2<=len(direction.strip())<=2000:
  raise ValueError('2–2000 karakteres irány szükséges.')
 direction=direction.strip()
 if target=='current':target=(read(s) or {}).get('idea_id')
 if target!='next' and not focus_for(s,target):raise ValueError('Jelölj meg egy meglévő Autopilóta-projektet.')
 if not s.db.execute('SELECT 1 FROM projects WHERE id=?',(PID,)).fetchone():
  s.create_project('ORBIT · Üzleti műhely',GOAL,'general',PID)
 if target=='next':
  choose(s,'scout')
  write(s,dict(read(s) or {},next_direction=direction))
 else:
  choose(s,target)
  focus=read(s) or {}
  write(s,dict(focus,directions=dict(focus.get('directions') or {},**{target:direction})))
 if start:configure(s,{'enabled':True})
 return dict(target=target,direction=direction,started=bool(start))

def chat_steering(s,prompt):
 """Resolve direct operator instructions without relying on the language model for the mutation."""
 from model_router import normalized
 line=prompt.strip()
 launch=re.fullmatch(r'Autopilóta indítása · (.+)',line,re.I|re.S)
 if launch:return 'next',launch[1],True
 explicit=re.fullmatch(r'Autopilóta irány · (következő projekt|jelenlegi projekt|projekt [a-f0-9]+):\s*(.+)',line,re.I|re.S)
 if explicit:
  target=explicit[1].casefold()
  target={'következő projekt':'next','jelenlegi projekt':'current'}.get(target,target.split()[-1])
  return target,explicit[2],False
 plain=normalized(line)
 if ('autopilot' not in plain or '?' in line or '\n' in line or
     re.search(r'\b(ne|mellett|utana|kozben|emellett|aztan|majd)\b',plain)):return None
 match=re.match(r'^(?:a )?kovetkezo autopilot\w* projekt (?:foglalkozzon|dolgozzon)\s+(.+)',plain)
 if match:return 'next',line[match.start(1):],False
 return None

def configure(s,data):
 if 'workshop_import' in data:
  from project_apps import import_venture
  return import_venture(s,data['workshop_import'])
 if 'steer' in data:
  intent=data['steer']
  if not isinstance(intent,dict):raise ValueError('Érvénytelen Autopilóta-utasítás.')
  return dict(steering=steer(s,intent.get('target'),intent.get('direction'),data.get('enabled') is True))
 from missions import schema,save,start,pause,definition,job_ids
 schema(s);old=s.db.execute('SELECT * FROM orbit_missions WHERE origin=?',(ORIGIN,)).fetchone()
 direction=data.get('direction')
 if direction is not None and (not isinstance(direction,str) or not 2<=len(direction.strip())<=2000):raise ValueError('2–2000 karakteres irány szükséges.')
 if 'focus' in data:
  import venture_build
  venture_build.choose(s,data['focus'])
 if data.get('checkout'):
  # The owner's checkout link for a finished product's buy buttons (kept in launch-form.json, which builders cannot write).
  import venture_build,launch
  d=data['checkout'] if isinstance(data['checkout'],dict) else {};f=venture_build.focus_for(s,str(d.get('idea_id') or ''))
  if not f:raise ValueError('Ismeretlen projekt.')
  url=str(d.get('url') or '').strip()
  if url and not launch.checkout(dict(checkout_url=url)):raise ValueError('A vásárlási link https:// kezdetű webcím legyen (pl. Stripe fizetési link, Gumroad vagy piactéri termékoldal).')
  path=s.safe_path(PID,venture_build.folder(f)+'/'+launch.FORM_FILE)
  try:cfg=json.loads(path.read_text())
  except (OSError,ValueError):cfg={}
  cfg=dict(cfg if isinstance(cfg,dict) else {},checkout_url=url,checkout_label=str(d.get('label') or cfg.get('checkout_label') or 'Megveszem')[:60])
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(cfg,ensure_ascii=False,indent=1))
  return dict(checkout=url)
 if data.get('concierge_sent'):
  # The owner sent a prepared report themselves; ORBIT never sends it.
  import concierge
  d=data['concierge_sent'] if isinstance(data['concierge_sent'],dict) else {}
  return dict(concierge=concierge.mark_sent(s,str(d.get('idea_id') or ''),str(d.get('key') or '')))
 if data.get('milestone_done'):
  # The owner did a roadmap step themselves; the Autopilot continues with the next one.
  import venture_build
  d=data['milestone_done'];f=venture_build.focus_for(s,d.get('idea_id')) if isinstance(d,dict) else None
  if not f:raise ValueError('Ismeretlen projekt.')
  return dict(owner_done=venture_build.mark_done(s,f,d.get('milestone'),d.get('done',True) is not False,d.get('files') or [],d.get('note') or ''))
 if data.get('launch') or data.get('unlaunch') or data.get('refresh_launch'):
  # Publishing happens only here, from the operator's explicit click in the Autopilot page.
  import venture_build,launch
  iid=data.get('launch') or data.get('unlaunch') or data.get('refresh_launch')
  f=venture_build.focus_for(s,iid)
  if not f:raise ValueError('Ismeretlen projekt.')
  if data.get('launch'):return dict(launch=launch.launch(s,f))
  if data.get('unlaunch'):return dict(launch=launch.stop(s,f))
  return dict(launch=launch.refresh(s,venture_build.folder(f),force=True))
 if old:
  mid=old['id']
  if direction:
   s.db.execute('UPDATE orbit_missions SET goal=?,updated=? WHERE id=?',(GOAL+'\nOperator direction: '+direction,time.time(),mid));s.db.commit()
  if data.get('enabled') is False:
   pause(s,PID,mid)
   for run in s.rows("SELECT id FROM orbit_mission_runs WHERE mission=? AND status='running'",(mid,)):
    for st in s.rows("SELECT * FROM orbit_mission_steps WHERE run=? AND state IN ('waiting','dispatching')",(run['id'],)):
     for jid in set(job_ids(s,st)+([st['dispatch']] if st['dispatch'] else [])):s.cancel(jid)
     s.db.execute("UPDATE orbit_mission_steps SET state='pending',receipt='{}',dispatch=NULL,attempts=0,retry_at=0,error='' WHERE run=? AND node=?",(run['id'],st['node']))
   s.db.commit();report=summary(s,mid)
   path=s.safe_path(PID,'workspace/ventures/STOP-SUMMARY.md');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(report)
   return dict(id=mid,status='paused',summary=report)
  if data.get('enabled') is True:return start(s,PID,mid)
  return dict(id=mid)
 if data.get('enabled') is not True:raise ValueError('Előbb indítsd el az üzleti műhelyt.')
 if not s.db.execute('SELECT 1 FROM projects WHERE id=?',(PID,)).fetchone():s.create_project('ORBIT · Üzleti műhely',GOAL,'general',PID)
 agents=s.rows('SELECT id,name FROM agents WHERE project=?',(PID,));by={a['name']:a['id'] for a in agents}
 ids=[]
 for name,role,room,prompt in [('Piackutató','Üzleti kutató','research',RESEARCH),('Építő','Prototípus-tervező','workshop',BUILD),('Kritikus','Független értékelő','bridge',REVIEW)]:
  ids.append(s.save_agent(dict(id=by.get(name),project=PID,name=name,role=role,room=room,model='auto',color='#ad8aee',tools=['project_files','read_file','web_search','read_web'],prompt=prompt,interval=0)))
 nodes=[dict(id='research',kind='agent',agent=ids[0],prompt=RESEARCH),dict(id='build',kind='venture',agent=ids[1],prompt=BUILD,output='json',after=['research']),dict(id='review',kind='agent',agent=ids[2],prompt=REVIEW,after=['build'])]
 mid=save(s,PID,dict(name='ORBIT · Bevételi lehetőségek',goal=GOAL+('\nOperator direction: '+direction if direction else ''),spec=dict(nodes=nodes,continuous=True,exploration=True,recover_failures=True,local_only=True,interval_minutes=5,daily_cycles=24,max_cycles=1,run_minutes=120,max_attempts=3)),ORIGIN)
 return start(s,PID,mid)
