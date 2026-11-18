"""Small Ollama output grammars bind local editorial decisions to actual evidence IDs."""
def obj(properties,required=None):return dict(type='object',properties=properties,required=list(properties) if required is None else required,additionalProperties=False)
def text(size=400):return dict(type='string',maxLength=size)
def ids(values,minimum=0,maximum=12):return dict(type='array',items=dict(type='integer',enum=list(dict.fromkeys(values))),minItems=minimum,maxItems=maximum)
def rank(events):return obj(dict(event_id=dict(type='integer',enum=[e['id'] for e in events]),reason=text(300)))
def director(event,hooks):
 values=event['unit_ids'];return obj(dict(event_id=dict(type='integer',enum=[event['id']]),premise=text(),viewer_question=text(),resolution=text(),hook_candidates=ids(hooks,1,3),context_ids=ids(values),development_ids=ids(values),payoff_ids=ids(values,1,4),ending_ids=ids(values,1,4),omit_ids=ids(values,0,48),pacing=dict(type='string',enum=['measured','brisk','energetic'])))
def candidate_review(candidates):
 values=list(dict.fromkeys(i for c in candidates for i in [c['hook']]+c['sequence']));hooks=[c['hook'] for c in candidates]
 note=obj(dict(id=dict(type='integer',enum=values),beat=dict(type='string',enum=['context','payoff','reaction','ending']),reason=text(180),preserve_pause=dict(type='boolean'),sound=dict(type='string',enum=list(__import__('sfx').CHOICES))))
 return obj(dict(approved=dict(type='boolean'),candidate_id=dict(type='integer',enum=list(range(len(candidates)))),hook_candidates=dict(type='array',minItems=1,maxItems=3,items=obj(dict(id=dict(type='integer',enum=hooks),reason=text(180)))),humor_type=dict(type='string',enum=['none','irony','deadpan','misdirection','reaction','absurd','situational']),joke_setup=text(250),payoff_evidence=text(250),removed_reason=text(400),beats=dict(type='array',minItems=1,maxItems=4,items=note)))

def full_review(catalog):
 values=[u['id'] for u in catalog]
 ident=dict(type='integer',enum=values)
 note=obj(dict(id=ident,beat=dict(type='string',enum=['context','payoff','reaction','ending']),reason=text(180),preserve_pause=dict(type='boolean'),sound=dict(type='string',enum=list(__import__('sfx').CHOICES)),transition=dict(type='string',enum=['cut','wipe']),camera=dict(type='string',enum=['wide','speaker']),effect=dict(type='string',enum=['none','punch-in']),cutaway_id=ident,cutaway_reason=text(180)),required=['id','beat','reason','preserve_pause','sound'])
 plan=obj(dict(hook=ident,sequence=ids(values,1,11),context=text(250),payoff=text(250),caption_theme=dict(type='string',enum=['clean','gaming','energetic','story'])))
 return obj(dict(approved=dict(type='boolean'),hook_candidates=dict(type='array',minItems=1,maxItems=3,items=obj(dict(id=ident,reason=text(180)))),humor_type=dict(type='string',enum=['none','irony','deadpan','misdirection','reaction','absurd','situational']),joke_setup=text(250),payoff_evidence=text(250),removed_reason=text(400),plan=plan,beats=dict(type='array',minItems=1,maxItems=8,items=note)))
