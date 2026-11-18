"""Read the complete source before selecting a duration-budgeted, faithful summary."""
import hashlib,json

POLICY='''CURRENT MODE: full-content summary, not one isolated incident. The complete source has been surveyed in chronological batches. Preserve its main subject, essential context and actual central outcome. Required IDs are mandatory; priority IDs are editorial judgments, not audience measurements. Shorten by removing repetition, side issues and low-priority material, never the context that changes the source meaning. Different episodes may appear as a clearly chronological summary/compilation, never as a fabricated conversation or causal event. The opening hook must relate to the full source's actual central point. Keep the original speech and complete thoughts. Never invent narration or claim that sampled visual frames cover every frame.'''

def _save(s,job,data):
 s.db.execute('UPDATE short_runs SET data=? WHERE id=? AND project=?',(json.dumps(data,ensure_ascii=False),json.loads(job['payload'])['run'],job['project']));s.db.commit()

def _defer(s,job,data):
 _save(s,job,data)
 from execution_queue import DeferredExecution
 raise DeferredExecution('A teljes forrás tartalmi feltérképezése folytatódik a mentett ponttól.',1)

def rankings(ranks,allowed):
 """Keep valid per-unit judgments; a few omitted units get a neutral rank instead of a failed survey."""
 valid={}
 for r in ranks:
  if isinstance(r,dict) and type(r.get('id')) is int and r['id'] in allowed and r['id'] not in valid and type(r.get('importance')) is int and 1<=r['importance']<=5 and r.get('role') in ('context','development','outcome','aside'):valid[r['id']]=dict(id=r['id'],importance=r['importance'],role=r['role'])
 if len(valid)<max(1,.7*len(allowed)):raise ValueError('Érvénytelen vagy hiányos tartalmi fontossági rangsor.')
 return [valid.get(i) or dict(id=i,importance=3,role='development',imputed=True) for i in sorted(allowed)]

def repair_overview(raw,catalog,ranks,max_seconds):
 """Mechanical consistency fixes of a model overview; meaning is never invented.

 Outcomes join the required set, required side threads after the last outcome stay ranked
 but optional, and the lowest-importance required context yields when the budget is tight.
 """
 outcomes=list(raw['outcome_ids']);last=max(outcomes);importance=lambda i:ranks[i]['importance'] if i in ranks else 3
 required=list(dict.fromkeys([i for i in raw['required_ids'] if i<=last]+outcomes))
 context=sorted((i for i in required if i not in outcomes),key=lambda i:(-importance(i),i))
 while len(required)>6 or sum(catalog[i]['seconds'] for i in required)>max_seconds:
  if not context:raise ValueError('A lényegi jelenetek együtt túl hosszúak. Válassz tömörebb, valós kontextust és eredményt.')
  required.remove(context.pop())
 if len(required)<2:
  extra=next((i for i in sorted(raw['ranked_ids'],key=lambda i:-importance(i)) if i<last and i not in required and sum(catalog[x]['seconds'] for x in required+[i])<=max_seconds),None)
  if extra is None:raise ValueError('A lényegi összefoglalóhoz kontextus és eredmény is szükséges.')
  required.append(extra)
 repaired=dict(raw,required_ids=sorted(required),ranked_ids=list(dict.fromkeys(list(raw['ranked_ids'])+[i for i in raw['required_ids'] if i not in required]))[:24])
 if repaired['required_ids']!=sorted(raw['required_ids']):repaired['server_repair']=dict(original_required_ids=raw['required_ids'],reason='outcome inclusion, ending on the outcome, duration budget')
 return repaired

HIGHLIGHT='''CURRENT MODE: the owner's own raw footage, cut into ONE strong Short. Do NOT summarize the whole recording. Find the single best self-contained moment: a joke, a funny reaction, a surprise or the most interesting claim. Understand each joke: who sets up which expectation, what breaks it (the turn), the punchline, and the reaction that confirms it (humor cues: laughter, reaction_after, comic_pause, turn, surprise are measured timing evidence, not proof). Importance 5 = part of the strongest bit (its setup, punchline or reaction); 1 = dead air, repetition, technical talk, greetings. Required IDs form that ONE bit in order: the setup it needs, the punchline and the reaction. Outcome IDs carry the punchline/reaction. main_context = the situation in one sentence; core_message = why the moment works (the joke or surprise mechanism). Keep the original speech; never invent narration.'''

def mode_policy(data):
 return HIGHLIGHT if data.get('edit_goal')=='highlight' else POLICY

def survey(s,job,data,catalog,ask):
 """One persisted map/reduce call per scheduler slice, no discarded tail of a transcript."""
 from editorial_schemas import obj,text,ids as id_array
 key=hashlib.sha256(json.dumps(dict(version=1,units=catalog,duration={k:data['style'][k] for k in ('min_seconds','max_seconds','target_seconds')}),sort_keys=True).encode()).hexdigest()
 state=data.get('content_survey',{})
 if state.get('fingerprint')!=key:state=dict(fingerprint=key,batches=[],levels=[]);data['content_survey']=state
 if state.get('overview'):return state
 batches=[catalog[i:i+20] for i in range(0,len(catalog),20)]
 if len(state['batches'])<len(batches):
  index=len(state['batches']);batch=batches[index];allowed={u['id'] for u in batch}
  s.job_stage(job['id'],'content_survey','Teljes tartalom áttekintése · '+str(index+1)+'/'+str(len(batches)))
  response_schema=obj(dict(summary=text(500),rankings=dict(type='array',minItems=len(batch),maxItems=len(batch),items=obj(dict(id=dict(type='integer',enum=sorted(allowed)),importance=dict(type='integer',minimum=1,maximum=5),role=dict(type='string',enum=['context','development','outcome','aside']))))))
  raw=ask(s,job,'Read EVERY supplied source unit. These are consecutive parts of a longer source, not independently complete stories. Identify what the source is doing and what would change its meaning if omitted. Return {"summary":"concise faithful section summary, <=300 characters","rankings":[{"id":integer,"importance":1..5,"role":"context|development|outcome|aside"}]}. Include EVERY supplied ID exactly once. Importance 5 means essential to understanding the source; 1 is repetition or peripheral material. Do not invent events, context or causal links. '+mode_policy(data),dict(_response_schema=response_schema,source_units=[{k:u.get(k) for k in ('id','source','start','end','text','context_before','context_after','humor','hook_score') if u.get(k) is not None} for u in batch],part=index+1,total_parts=len(batches)))
  ranks=raw.get('rankings',[]) if isinstance(raw,dict) else []
  if not isinstance(raw,dict) or not isinstance(raw.get('summary'),str) or not raw['summary'].strip() or not isinstance(ranks,list):raise ValueError('A teljes tartalom minden egységének fontossági értékelése szükséges.')
  ranks=rankings(ranks,allowed)
  state['batches'].append(dict(summary=raw['summary'][:500],rankings=ranks,ids=sorted(allowed)))
  _defer(s,job,data)
 # Hierarchically reduce all section summaries; every section enters this tree.
 if not state['levels']:
  state['levels']=[[dict(summary=b['summary'],ids=[r['id'] for r in sorted(b['rankings'],key=lambda r:-r['importance'])[:5]]) for b in state['batches']]]
 level=state['levels'][-1]
 if len(level)>8:
  pending=state.setdefault('reduction',[]);groups=[level[i:i+8] for i in range(0,len(level),8)]
  group=groups[len(pending)];allowed={i for g in group for i in g['ids']}
  raw=ask(s,job,'Summarize ALL supplied chronological sections faithfully, preserving the central topic, necessary context and actual outcomes. Return {"summary":"<=500 characters","ids":[up to 8 supplied IDs carrying the central context and outcome]}. Do not turn peripheral reactions into the main theme.',dict(_response_schema=obj(dict(summary=text(700),ids=id_array(sorted(allowed),1,8))),sections=group))
  ids=raw.get('ids',[]) if isinstance(raw,dict) else []
  if not isinstance(raw,dict) or not isinstance(raw.get('summary'),str) or not ids or any(type(i) is not int or i not in allowed for i in ids) or len(ids)>8:raise ValueError('A teljes tartalom összesítése nem igazolt forrásegységekre hivatkozik.')
  pending.append(dict(summary=raw['summary'][:700],ids=list(dict.fromkeys(ids))))
  if len(pending)==len(groups):state['levels'].append(pending);state.pop('reduction',None)
  _defer(s,job,data)
 ranks={r['id']:r for b in state['batches'] for r in b['rankings']}
 # The entire source has already entered the reduction tree. Bound the final
 # evidence packet across sections, rather than overflowing a local 8k context.
 candidates=set(i for section in level for i in list(dict.fromkeys(section['ids'][:2]+section['ids'][-2:])))
 candidates.update(r['id'] for r in sorted(ranks.values(),key=lambda r:-r['importance'])[:16])
 overview_schema=obj(dict(main_context=text(600),core_message=text(600),required_ids=id_array(sorted(candidates),2,6),outcome_ids=id_array(sorted(candidates),1,3),ranked_ids=id_array(sorted(candidates),1,24),omission_policy=text(600)))
 raw=ask(s,job,'Use the complete-source section summaries to design a FAITHFUL compressed overview. Return {"main_context":"central subject and necessary setup","core_message":"what the entire source is fundamentally about, including actual outcome","required_ids":[2..6 supplied IDs essential to preserve the main context and central outcome],"outcome_ids":[1..3 required IDs carrying the actual outcome],"ranked_ids":[up to 24 supplied IDs in decreasing editorial importance],"omission_policy":"what can be omitted as duration decreases without changing meaning"}. Required ID durations together must leave room within the maximum output seconds. Prefer complete short units. The final ending may come from near the source end; do not focus only on its opening. No invented narration. '+mode_policy(data),dict(_response_schema=overview_schema,sections=level,units=[dict(id=i,seconds=catalog[i]['seconds'],text=catalog[i]['text'],source=catalog[i]['source'],start=catalog[i]['start'],importance=ranks[i]['importance'],**({'humor':catalog[i]['humor']} if catalog[i].get('humor') else {})) for i in sorted(candidates)],max_seconds=data['style']['max_seconds'],target_seconds=data['style']['target_seconds'],previous_error=state.get('overview_error')))
 try:
  if not isinstance(raw,dict):raise ValueError('Strukturált teljes tartalmi terv szükséges.')
  for k in ('main_context','core_message','omission_policy'):
   if not isinstance(raw.get(k),str) or len(raw[k].strip())<8:raise ValueError('A teljes forrás fő kontextusa és lényege hiányzik.')
  for k,low,high in (('required_ids',2,6),('outcome_ids',1,3),('ranked_ids',1,24)):
   ids=raw.get(k)
   # A repeated or unknown ID is dropped: with few candidates the local model pads the list to the schema's limit.
   if not isinstance(ids,list):raise ValueError('Érvénytelen összefoglalási hivatkozás: '+k)
   ids=list(dict.fromkeys(i for i in ids if type(i) is int and i in candidates))[:high]
   if len(ids)<low:raise ValueError('Érvénytelen összefoglalási hivatkozás: '+k)
   raw[k]=ids
  raw=repair_overview(raw,catalog,ranks,data['style']['max_seconds'])
 except (ValueError,TypeError) as exc:
  state['overview_error']=str(exc);state['overview_repairs']=state.get('overview_repairs',0)+1
  if state['overview_repairs']<3:_defer(s,job,data)
  raise
 state['overview']=raw;state['reviewed_units']=len(catalog);state['total_units']=len(catalog);state['visual_scope']='Sampled timestamped visual observations; full original-language transcript units surveyed.'
 _save(s,job,data);return state

def shortlist(catalog,state):
 """Only compress AFTER full survey. Keep source IDs for an inspectable omission log."""
 overview=state['overview'];chosen=list(dict.fromkeys(overview['required_ids']+overview['ranked_ids']))
 for uid in list(chosen):
  for neighbor in (uid-1,uid+1):
   if 0<=neighbor<len(catalog) and catalog[neighbor]['source']==catalog[uid]['source'] and neighbor not in chosen and len(chosen)<48:chosen.append(neighbor)
 chosen=sorted(chosen);remap={old:i for i,old in enumerate(chosen)};result=[]
 for old in chosen:
  unit=dict(catalog[old],id=remap[old],global_id=old)
  for key in ('previous_id','next_id'):
   previous=unit.pop(key,None)
   if previous in remap:unit[key]=remap[previous]
   elif type(previous) is int and 0<=previous<len(catalog):unit['context_before' if key=='previous_id' else 'context_after']=catalog[previous]['text']
  result.append(unit)
 ranks={r['id']:r for b in state.get('batches',[]) for r in b['rankings']}
 for unit in result:
  if unit['global_id'] in ranks:unit['importance']=ranks[unit['global_id']]['importance'];unit['role']=ranks[unit['global_id']]['role']
 required=[remap[i] for i in overview['required_ids']];outcomes=[remap[i] for i in overview['outcome_ids']];ranked=[remap[i] for i in overview['ranked_ids']]
 # Opening: an important, self-contained line with the strongest measured/textual hook cues.
 pool=[i for i in ranked[:10] if i not in outcomes and not result[i].get('starts_mid_sentence')] or ranked[:3]
 hooks=sorted(pool,key=lambda i:-(result[i].get('hook_score',0)+2*result[i].get('importance',3)-ranked.index(i)*.3))[:3]
 director=dict(status='full_content_summary',event_id=None,premise=overview['main_context'],resolution=overview['core_message'],required_ids=required,hook_candidates=hooks,context_ids=[i for i in required if i not in outcomes],development_ids=ranked,payoff_ids=outcomes,ending_ids=outcomes,omit_ids=[],summary_policy=overview['omission_policy'],assessment='Full source mapped before duration-based selection; editorial meaning still requires review.')
 return result,director

def candidates(director,catalog,style):
 from editorial import feasible_story
 from story_director import check_story
 results=[]
 for hook in [i for i in dict.fromkeys(director['hook_candidates']+director['required_ids']) if i not in director['ending_ids']][:6]:
  selected=list(dict.fromkeys([hook]+director['required_ids']))
  ending=max(director['ending_ids'])
  for extra in director['development_ids']:
   if extra in selected or extra>ending:continue
   if sum(catalog[i]['seconds'] for i in selected+[extra])<=style['max_seconds'] and len(selected)<style['max_shots']:selected.append(extra)
  body=sorted(i for i in selected if i!=hook)
  choice=dict(hook=hook,sequence=body,context=director['premise'],payoff=director['resolution'],caption_theme='clean')
  try:plan,_=feasible_story(choice,catalog,style);check_story(plan,director,catalog)
  except ValueError:continue
  results.append(dict(choice,hook=plan['unit_ids'][0],sequence=plan['unit_ids'][1:],candidate_id=len(results),verified_seconds=plan['duration'],verified_units=len(plan['unit_ids'])))
 return results
