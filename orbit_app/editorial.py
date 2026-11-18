"""Grounded story beats and conservative camera/effect budgets."""
import math,re
from difflib import SequenceMatcher
from short_style import MIN_EDIT_UNIT_SECONDS,DURATION_TOLERANCE_SECONDS,duration_allowed

def speech_coverage(transcript,start,end):
 intervals=[]
 for seg in transcript.get('segments',[]):
  for w in seg.get('words') or [seg]:
   try:a=max(start,float(w['start']));b=min(end,float(w['end']))
   except (KeyError,TypeError,ValueError):continue
   if math.isfinite(a) and math.isfinite(b) and b>a:intervals.append((a,b))
 intervals.sort();merged=[]
 for a,b in intervals:
  if merged and a<=merged[-1][1]+.15:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
  else:merged.append((a,b))
 return min(1,sum(b-a for a,b in merged)/max(.1,end-start))

def timed_units(transcript,max_seconds):
 tokens=[]
 for seg in transcript.get('segments',[]):
  for word in seg.get('words',[]):
   try:a=float(word['start']);b=float(word['end']);text=str(word.get('word',word.get('text',''))).strip()
   except (KeyError,ValueError,TypeError):continue
   if text and all(math.isfinite(x) for x in (a,b)) and 0<=a<b:tokens.append(dict(start=a,end=b,text=text,speaker=word.get('speaker')))
 if not tokens:return None
 units=[];current=None
 def emit(boundary):
  if current and current['end']>current['start']:units.append(dict(current,boundary=boundary))
 for word in tokens:
  if word['end']-word['start']>max_seconds:continue
  if current and (word['start']-current['end']>1.1 or word['end']-current['start']>max_seconds or current.get('speaker') and word.get('speaker') and current['speaker']!=word['speaker']):
   emit('speaker_change' if current.get('speaker') and word.get('speaker') and current['speaker']!=word['speaker'] else 'pause' if word['start']-current['end']>1.1 else 'window');current=None
  if current:current.update(end=max(current['end'],word['end']),text=current['text']+' '+word['text'])
  else:current=dict(word)
  if re.search(r'[.!?…]["\x27)]?$',word['text']):emit('sentence');current=None
 emit('source_end')
 return units

def story_units(transcript,max_seconds=12):
 timed=timed_units(transcript,max_seconds)
 if timed is not None:return timed
 units=[];current=None
 for seg in transcript.get('segments',[]):
  try:a=float(seg['start']);b=float(seg['end']);text=str(seg.get('text','')).strip()
  except (KeyError,TypeError,ValueError):continue
  if not text or not all(math.isfinite(x) for x in (a,b)) or b<=a:continue
  if current and (a-current['end']>1.1 or b-current['start']>max_seconds):
   if re.search(r'[.!?…]["\x27)]?$',current['text']):units.append(current)
   current=None
  if current:current.update(end=b,text=current['text']+' '+text)
  else:current=dict(start=a,end=b,text=text)
  if re.search(r'[.!?…]["\x27)]?$',text) and b-current['start']<=max_seconds:units.append(current);current=None
 return units

def scene_kind(observation,start,end):
 """A mixed compilation needs a per-shot policy, not one genre for the whole file."""
 if not isinstance(observation,dict):return 'unknown'
 frames=[f for f in observation.get('frames',[]) if start<=f.get('seconds',-1)<=end]
 text=' '.join(str(f.get('action','')) for f in frames).casefold()
 if re.search(r'\b(gameplay|minecraft|valorant|game hud|first-person|in a game|game footage)\b',text):return 'gameplay'
 if re.search(r'\b(facecam|inset)\b',text) and re.search(r'\b(video player|screen|footage|interface|clip)\b',text):return 'screen_content'
 if re.search(r'\b(sings?|singing|dancing|runway|catwalk)\b',text):return 'performance'
 return observation.get('content_type','unknown')

def camera_plan(shots,tracks,observations):
 """A tracker finds people, not the active speaker. Uncertainty must retain context."""
 total=sum(x['end']-x['start'] for x in shots);close=0;previous=False;plan=[];accents=0;since_accent=10
 for i,shot in enumerate(shots):
  transcript=tracks[shot['source']]['transcript'];coverage=speech_coverage(transcript,shot['start'],shot['end'])
  obs=observations[shot['source']] if shot['source']<len(observations) else {}
  kind=scene_kind(obs,shot['start'],shot['end'])
  visible=any(shot['start']<=f.get('seconds',-1)<=shot['end'] and f.get('has_person') is True for f in obs.get('frames',[])) if isinstance(obs,dict) else False
  duration=shot['end']-shot['start'];budget=.22 if kind=='gameplay' else .35
  speaker=shot.get('zoom_justified') is True and shot.get('framing')=='speaker' and coverage>=.6 and visible and not previous and close+duration<=total*budget
  if kind=='gameplay' and shot.get('beat') not in ('hook','payoff'):speaker=False
  if speaker:close+=duration
  effect=shot.get('effect','none') if speaker else 'none'
  # Only a grounded reveal/reaction receives punctuation, never an index pattern.
  meaningful=shot.get('beat') in ('payoff','reaction')
  accent=meaningful and not shot.get('preserve_pause') and since_accent>=4 and accents<max(1,int(total/12))
  if not accent:effect='none'
  # The social formula's accents (comedy.social_polish) sit on approved beats and keep their own spacing.
  formula=shot.get('formula_sound') is True and not shot.get('preserve_pause')
  sound=shot.get('sound','none') if accent or formula else 'none'
  if effect!='none' or sound!='none' and not formula:accents+=1;since_accent=0
  else:since_accent+=duration
  plan.append(dict(shot=i,base_follow=kind in ('talking_head','performance','fashion'),zoom_justified=bool(speaker and effect=='punch-in'),framing='speaker' if speaker else 'wide',speech_coverage=round(coverage,3),content_type=kind,effect=effect,reason=shot.get('reason',''),transition=shot.get('transition','cut') if not shot.get('preserve_pause') else 'cut',sound=sound,sound_delay=shot.get('sound_delay',0),preserve_pause=bool(shot.get('preserve_pause'))))
  previous=speaker
 return plan

CAPTION_THEMES={
 'clean':dict(font='Arial',font_size=72,highlight='#BFA3FF',animation='fade',treatment='minimal'),
 'gaming':dict(font='Trebuchet MS',font_size=76,highlight='#67E8F9',animation='word-pop',treatment='pill'),
 'energetic':dict(font='Arial',font_size=80,highlight='#FFD166',animation='word-pop',treatment='impact'),
 'story':dict(font='Georgia',font_size=72,highlight='#FFB7A5',animation='fade')}

def caption_theme(name):return dict(CAPTION_THEMES.get(name,CAPTION_THEMES['clean']))

def validate_masks(masks):
 if not isinstance(masks,list) or len(masks)>3:raise ValueError('Legfeljebb három kitakarási terület adható meg.')
 result=[]
 for m in masks:
  values=[m.get(k) for k in ('x','y','w','h')]
  if any(type(v) not in (float,int) or not math.isfinite(v) for v in values):raise ValueError('Érvénytelen kitakarási koordináta.')
  x,y,w,h=values
  if not 0<=x<1 or not 0<=y<1 or not 0<w<=.5 or not 0<h<=.5 or x+w>1 or y+h>1 or w*h>.18:raise ValueError('A kitakarás túl nagy vagy kilóg a képből.')
  if not isinstance(m.get('reason'),str) or not m['reason'].strip():raise ValueError('A kitakarás indoklása szükséges.')
  result.append(dict(x=x,y=y,w=w,h=h,reason=m['reason'][:250]))
 return result

def stable_privacy_masks(observation,start,end):
 """Only stationary, independently sampled private-data regions; no guessed person cutouts."""
 frames=[f for f in observation.get('frames',[]) if start<=f.get('seconds',-1)<=end]
 if len(frames)<2:return []
 result=[];aspect=observation.get('aspect_ratio',16/9)
 for region in frames[0].get('redactions',[]):
  if region.get('kind') not in ('private_email','phone_number') or region.get('confidence',0)<.95:continue
  keys=('x','y','w','h')
  if not all(type(region.get(k)) in (int,float) and math.isfinite(region[k]) for k in keys):continue
  match=any(r.get('kind')==region['kind'] and r.get('confidence',0)>=.95 and all(type(r.get(k)) in (int,float) and abs(r[k]-region[k])<.02 for k in keys) for f in frames[1:] for r in f.get('redactions',[]))
  if not match:continue
  x,y,w,h=[region[k] for k in keys]
  if aspect>=1080/1920:
   frac=1080/aspect/1920;y=(1-frac)/2+y*frac;h*=frac
  else:
   frac=1920*aspect/1080;x=(1-frac)/2+x*frac;w*=frac
  try:result.extend(validate_masks([dict(x=x,y=y,w=w,h=h,reason=region['kind'])]))
  except ValueError:continue
 return result[:3]

def visual_led(observation):
 """Visible singing/dancing/runway evidence takes priority over soundtrack lyrics."""
 if not isinstance(observation,dict):return False
 frames=observation.get('frames',[])
 if len(frames)<2:return False
 described=sum(bool(re.search(r'\b(sings?|singing|dancing|dances?|runway|catwalk)\b',str(f.get('action','')),re.I)) for f in frames if isinstance(f,dict))
 return described>=max(2,len(frames)*.6)

def phrase_groups(units,max_seconds):
 """Join micro-utterances without hiding independent sentences from the editor."""
 grouped=[]
 for unit in units:
  previous=grouped[-1] if grouped else None
  same_voice=previous and (not previous.get('speaker') or not unit.get('speaker') or previous['speaker']==unit['speaker'])
  micro=previous and min(previous['end']-previous['start'],unit['end']-unit['start'])<=1.2 and unit['end']-previous['start']<=4.5
  continuation=previous and previous.get('boundary')=='window'
  if previous and same_voice and (micro or continuation) and 0<=unit['start']-previous['end']<=.45 and unit['end']-previous['start']<=max_seconds:
   grouped[-1].update(end=unit['end'],text=grouped[-1]['text']+' '+unit['text'],boundary=unit.get('boundary','sentence'))
  else:grouped.append(dict(unit))
 return grouped

def covered_windows(units,limit):
 """Bounded context from start/middle/end, retaining adjacent complete utterances."""
 if limit<=0:return []
 if len(units)<=limit:return units
 blocks=min(4,max(1,limit//3));selected=[]
 for i in range(blocks):
  size=limit//blocks+(i<limit%blocks)
  start=round(i*(len(units)-size)/max(1,blocks-1))
  selected.extend(units[start:start+size])
 return selected

def complete_speech_windows(units,limit):
 """Sample complete sentence clusters, never leave a length-split clause orphaned."""
 if limit<=0:return []
 clusters=[]
 for unit in units:
  if clusters and unit.get('starts_mid_sentence'):clusters[-1].append(unit)
  else:clusters.append([unit])
 clusters=[c for c in clusters if len(c)<=limit and c[-1].get('boundary')!='window']
 if sum(map(len,clusters))<=limit:return [u for c in clusters for u in c]
 blocks=min(3,max(1,limit//4));picked=set();remaining=limit
 for b in range(blocks):
  budget=remaining//(blocks-b);anchor=round(b*(len(clusters)-1)/max(1,blocks-1));order=list(range(anchor,len(clusters))) if b<blocks-1 else list(range(anchor,-1,-1))
  for index in order:
   if index in picked:continue
   size=len(clusters[index])
   if size>budget:break
   picked.add(index);remaining-=size;budget-=size
 if not picked and clusters:picked.add(min(range(len(clusters)),key=lambda i:abs(i-len(clusters)//2)))
 return [u for index in sorted(picked) for u in clusters[index]]

def complete_sentences(choice,catalog):
 """Restore only immediate transcript continuations; never invent an interval."""
 if not isinstance(choice,dict) or type(choice.get('hook')) is not int:return choice
 raw=[choice['hook']]+list(choice.get('sequence',[])) if isinstance(choice.get('sequence',[]),list) else []
 if any(type(i) is not int or not 0<=i<len(catalog) for i in raw):return choice
 raw=[raw[0]]+[i for i in raw[1:] if i!=raw[0]]
 if len(set(raw))!=len(raw):return choice
 ordered=[]
 for uid in raw:
  if uid in ordered:continue
  unit=catalog[uid];chain=[uid];seen={uid}
  while unit.get('starts_mid_sentence'):
   prev=next((i for i,u in enumerate(catalog) if i not in seen and u['source']==unit['source'] and u.get('boundary')=='window' and -.05<=unit['start']-u['end']<=1.1),None)
   if prev is None:break
   chain.insert(0,prev);seen.add(prev);unit=catalog[prev]
  unit=catalog[chain[-1]]
  while unit.get('boundary')=='window':
   nxt=next((i for i,u in enumerate(catalog) if i not in seen and u['source']==unit['source'] and u.get('starts_mid_sentence',True) and -.05<=u['start']-unit['end']<=1.1),None)
   if nxt is None:break
   chain.append(nxt);seen.add(nxt);unit=catalog[nxt]
  ordered.extend(i for i in chain if i not in ordered)
 return dict(choice,hook=ordered[0],sequence=ordered[1:]) if ordered else choice


CURIOSITY=re.compile(r"\b(?:why|how|what|wait|never|nobody|secret|insane|crazy|unbelievable|actually|finally|worst|best|first time|no way|miért|hogyan|mi a|várj|soha|senki|titok|durva|hihetetlen|végre|legjobb|legrosszabb|először)\b",re.I)
OPENING_NOISE=re.compile(r"^(?:welcome|hey guys|hi guys|what's up|subscribe|like and|sziasztok|üdv|iratkozz)",re.I)

def hook_signals(unit,transcript):
 """Deterministic opening cues (0-10): measured vocal energy plus textual curiosity markers.

 A prior for ranking candidates the editor still judges; not a virality prediction.
 """
 text=unit['text'].strip();words=[w for seg in transcript.get('segments',[]) for w in seg.get('words',[]) if unit['start']<=w.get('start',-1)<unit['end']]
 score=0.0;cues=[]
 levels=(transcript.get('audio_context') or {}).get('loudness') or {}
 db=levels.get('db') or [];step=levels.get('step') or .5
 if db:
  window=db[int(unit['start']/step):max(int(unit['start']/step)+1,int(unit['end']/step))]
  voiced=sorted(x for x in db if x>-60)
  if window and voiced:
   lift=max(window)-voiced[len(voiced)//2]
   if lift>=4:score+=min(3,lift/3);cues.append('energy+'+str(int(lift))+'dB')
 if '?' in text:score+=1.5;cues.append('question')
 if '!' in text:score+=1;cues.append('exclaim')
 if re.search(r'\d',text):score+=.5;cues.append('number')
 if CURIOSITY.search(text):score+=1.5;cues.append('curiosity')
 rate=len(words)/max(.5,unit['end']-unit['start'])
 if rate>=3.2:score+=.5;cues.append('fast')
 if 3<=len(text.split())<=16:score+=1;cues.append('concise')
 if OPENING_NOISE.search(text):score-=3;cues.append('greeting')
 if unit.get('starts_mid_sentence'):score-=3;cues.append('mid_sentence')
 if unit.get('opening_visible') is False:score-=3
 return round(max(0,min(10,score)),1),cues

def unit_catalog(tracks,style,observations=None,full=False):
 catalog=[]
 for source,track in enumerate(tracks):
  units=story_units(__import__('transcript_quality').reliable(track['transcript']),style['max_shot_seconds'])
  # A short final word (e.g. a negation or noun) must not vanish at the render minimum.
  for index,unit in enumerate(units):
   if unit['end']-unit['start']<MIN_EDIT_UNIT_SECONDS:
    right=units[index+1]['start'] if index+1<len(units) else track.get('source',{}).get('duration',unit['end'])
    unit['end']=min(right,max(unit['end'],unit['start']+MIN_EDIT_UNIT_SECONDS+.001))
    if unit['end']-unit['start']<MIN_EDIT_UNIT_SECONDS:
     left=units[index-1]['end'] if index else 0
     unit['start']=max(left,unit['end']-MIN_EDIT_UNIT_SECONDS-.001)
  obs=(observations or [{}]*len(tracks))[source] if source<len(observations or []) else {}
  frames=obs.get('frames',[]) if isinstance(obs,dict) else []
  speech=phrase_groups(units,style['max_shot_seconds']);visual=[]
  if frames:
   duration=track.get('source',{}).get('duration',0);last_end=0
   for f in frames:
    t=f.get('seconds');action=f.get('action')
    if type(t) not in (int,float) or not math.isfinite(t) or not isinstance(action,str) or not action.strip() or not 0<=t<duration:continue
    start=max(last_end,t-style['max_shot_seconds']/2,0);end=min(duration,start+style['max_shot_seconds'])
    if not start<=t<end or end-start<MIN_EDIT_UNIT_SECONDS:continue
    visual.append(dict(start=start,end=end,text='Visual sample at '+str(t)+'s: '+action,boundary='visual_sample'));last_end=end
  if visual and visual_led(obs):speech=[]  # Captions still use the real transcript later.
  else:
   # A visual sample supplements speech; it must not create a second overlapping
   # representation that the editor can accidentally concatenate with that speech.
   gaps=[]
   for window in visual:
    sample=next((f['seconds'] for f in frames if window['start']<=f.get('seconds',-1)<window['end']),None)
    if sample is None:continue
    if any(u['start']<=sample<u['end'] for u in speech):continue
    start,end=window['start'],window['end']
    for u in speech:
     if u['end']<=sample:start=max(start,u['end'])
     elif u['start']>sample:end=min(end,u['start'])
    if end-start>=MIN_EDIT_UNIT_SECONDS:gaps.append(dict(window,start=start,end=end))
   visual=gaps
  # Retain neighboring transcript context even when the bounded catalogue skips a window.
  for index,unit in enumerate(speech):
   before=speech[index-1] if index else None;after=speech[index+1] if index+1<len(speech) else None
   unit['starts_mid_sentence']=bool(before and before.get('boundary')=='window' and unit['start']-before['end']<=1.1)
   unit['context_before']=before['text'][-200:] if before else ''
   unit['context_after']=after['text'][:200] if after else ''
  limit=max(1,len(speech)+len(visual)) if full else max(1,48//max(1,len(tracks)))
  units=sorted(complete_speech_windows(speech,max(0,limit-len(visual)))+covered_windows(visual,limit),key=lambda u:u['start'])
  for u in units:
   blanks=track.get('quality',{}).get('black_intervals',[])
   blank_seconds=sum(max(0,min(u['end'],b['end'])-max(u['start'],b['start'])) for b in blanks)
   # Keep whole utterances; never silently trim speech to hide a blank frame.
   if blank_seconds>=.8*(u['end']-u['start']):continue
   opening_visible=not any(min(u['start']+.4,b['end'])-max(u['start'],b['start'])>.2 for b in blanks)
   if MIN_EDIT_UNIT_SECONDS<=u['end']-u['start']<=style['max_shot_seconds']:
    catalog.append(dict(id=len(catalog),source=source,start=u['start'],end=u['end'],seconds=round(u['end']-u['start'],2),text=u['text'][:360],boundary=u.get('boundary','sentence'),opening_visible=opening_visible,starts_mid_sentence=u.get('starts_mid_sentence',False),context_before=u.get('context_before',''),context_after=u.get('context_after','')))
 for index,u in enumerate(catalog):
  # Adjacent catalogue IDs already carry the exact words; avoid tripling local context.
  previous=catalog[index-1] if index and catalog[index-1]['source']==u['source'] else None
  following=catalog[index+1] if index+1<len(catalog) and catalog[index+1]['source']==u['source'] else None
  if previous and 0<=u['start']-previous['end']<=1.1:u['previous_id']=previous['id'];u.pop('context_before',None)
  if following and 0<=following['start']-u['end']<=1.1:u['next_id']=following['id'];u.pop('context_after',None)
  obs=observations[u['source']] if observations and u['source']<len(observations) else {}
  speakers={w.get('speaker') for seg in tracks[u['source']]['transcript'].get('segments',[]) for w in seg.get('words',[]) if w.get('speaker') and u['start']<=w.get('start',-1)<u['end']}
  u['speaker']=next(iter(speakers)) if len(speakers)==1 else 'mixed' if speakers else None
  if u.get('boundary')!='visual_sample':u['hook_score'],u['hook_cues']=hook_signals(u,tracks[u['source']]['transcript'])
  u['visual_samples']=[dict(seconds=f['seconds'],action=str(f.get('action',''))[:350]) for f in obs.get('frames',[]) if type(f.get('seconds')) in (int,float) and u['start']<=f['seconds']<u['end']] if isinstance(obs,dict) else []
  if isinstance(obs,dict):u['scene_boundaries']=[scene['start'] for scene in obs.get('scene_map',{}).get('scenes',[]) if u['start']<=scene.get('start',-1)<=u['end']]
 return catalog if full else catalog[:48]

def compile_story(choice,catalog,style):
 if not isinstance(choice,dict) or type(choice.get('hook')) is not int:raise ValueError('A történetnek valós hook-jelenetet kell kijelölnie.')
 ids=choice.get('sequence',[])
 if not isinstance(ids,list):raise ValueError('Hiányzik a jelenetsorrend.')
 ids=[choice['hook']]+[x for x in ids if x!=choice['hook']]
 if len(set(ids))!=len(ids) or any(type(i) is not int or not 0<=i<len(catalog) for i in ids):raise ValueError('Ismeretlen vagy ismételt jelenetazonosító.')
 if catalog[choice['hook']].get('starts_mid_sentence'):raise ValueError('A hook egy félbehagyott mondat folytatása. Válassz önálló mondatkezdést.')
 if catalog[choice['hook']].get('opening_visible') is False:raise ValueError('A hook fekete forrásképpel kezdődik. Válassz látható nyitású jelenetet.')
 # Models select story anchors; deterministic expansion restores adjacent setup rather than
 # asking a language model to do duration arithmetic or padding with repeated footage.
 duration=sum(catalog[i]['seconds'] if 'seconds' in catalog[i] else catalog[i]['end']-catalog[i]['start'] for i in ids)
 while not choice.get('strict_story') and (duration<style['min_seconds'] or len(ids)<style['min_shots']) and len(ids)<style['max_shots']:
  candidates=[u for u in catalog if u['id'] not in ids and u['source']==catalog[ids[-1]]['source'] and duration+u['seconds']<=style['max_seconds']]
  if not candidates:break
  def distance(u):
   return min((abs(u['start']-catalog[i]['end']) if u['source']==catalog[i]['source'] else 10000+u['start']) for i in ids)
  chosen=min(candidates,key=distance);ids.append(chosen['id']);duration+=chosen['seconds']
 for n,i in enumerate(ids):
  for j in ids[n+1:]:
   if catalog[i]['source']==catalog[j]['source'] and min(catalog[i]['end'],catalog[j]['end'])-max(catalog[i]['start'],catalog[j]['start'])>.05:raise ValueError('A kiválasztott jelenetek átfedik egymást; ne ismételd ugyanazt a forrásképet.')
 # A length-based chunk boundary is not a narrative cut. Continue the sentence.
 for n,uid in enumerate(ids):
  unit=catalog[uid];previous=catalog[ids[n-1]] if n else None;following=catalog[ids[n+1]] if n+1<len(ids) else None
  if previous and previous['source']!=unit['source'] and unit.get('boundary')!='visual_sample':
   text=unit['text'].strip().casefold()
   if len(text.split())<=6 or re.match(r"^(?:of course|yes[,.! ]|no[,.! ]|exactly|absolutely|that's right|i (?:do|will)[.! ]|sure[,.! ])",text):raise ValueError('Külön forrásból származó rövid válasz nem kapcsolható másik beszélgetéshez. Válassz önálló részletet vagy az eredeti jelenetet.')
  if unit.get('starts_mid_sentence') and not (previous and previous['source']==unit['source'] and -.05<=unit['start']-previous['end']<=1.1):raise ValueError('A vágás mondat közepén kezdődne. Tartsd meg a közvetlen előzményt.')
  if unit.get('boundary')=='window' and not (following and following['source']==unit['source'] and following.get('starts_mid_sentence',True) and -.05<=following['start']-unit['end']<=1.1):raise ValueError('A vágás félbeszakítaná a mondatot. Tartsd meg a folytatását vagy válassz másik teljes részletet.')
 shots=[]
 for n,i in enumerate(ids):
  u=catalog[i];beat='hook' if n==0 else 'payoff' if len(ids)==2 else 'ending' if n==len(ids)-1 else 'payoff' if n==len(ids)-2 else 'context'
  shots.append(dict(unit_id=i,source=u['source'],start=u['start'],end=u['end'],beat=beat,framing='wide',reason=u['text'][:180],effect='none',transition='cut',sound='none'))
 duration=sum(x['end']-x['start'] for x in shots)
 if not duration_allowed(duration,style) or not style['min_shots']<=len(shots)<=style['max_shots']:raise ValueError('A történeti terv nem teljesíti a kért hosszt vagy jelenetszámot.')
 return dict(shots=shots,unit_ids=ids,duration=round(duration,3),selection='grounded_story_units',caption_theme=choice.get('caption_theme') if choice.get('caption_theme') in CAPTION_THEMES else 'clean',outline=dict(hook=catalog[choice['hook']]['text'][:350],context=str(choice.get('context',''))[:350],payoff=str(choice.get('payoff',''))[:350],ending=catalog[ids[-1]]['text'][:350]))


def reviewed_choice(review,choice):
 """Keep evidence rejection distinct from a malformed model response."""
 if not isinstance(review,dict):raise ValueError('A szerkesztő válasza nem JSON objektum.')
 if review.get('approved') is False:
  reason=review.get('removed_reason')
  raise ValueError('Szerkesztői javítás szükséges: '+(reason.strip()[:900] if isinstance(reason,str) and reason.strip() else 'A modell nem indokolta az elutasítást.'))
 if review.get('approved') is not True:raise ValueError('A szerkesztőnek approved JSON logikai értéket kell visszaadnia.')
 revised=review.get('plan')
 if revised is None:revised=choice
 if not isinstance(revised,dict):raise ValueError('A jóváhagyott plan mezőnek hook és sequence mezős objektumnak kell lennie.')
 if not review.get('beats') and isinstance(revised.get('beats'),list):review['beats']=revised['beats']
 return clean_choice(revised)

def clean_choice(choice):
 """Models often repeat the hook as the first sequence item or list an ID twice; that is the
 same plan, not a reordering, so drop the repeats before comparing it with the assembled story."""
 if not isinstance(choice,dict) or not isinstance(choice.get('sequence'),list):return choice
 seen={choice.get('hook')};sequence=[]
 for i in choice['sequence']:
  if i in seen:continue
  seen.add(i);sequence.append(i)
 return dict(choice,sequence=sequence) if sequence!=choice['sequence'] else choice

def apply_editorial_review(plan,review,catalog,payoff_ids=()):
 """Bind humor claims and edits to real catalog IDs. Model scores are editorial opinions."""
 if not isinstance(review,dict) or review.get('approved') is not True:raise ValueError('A szerkesztő nem hagyta jóvá a történet és csattanó összefüggését.')
 candidates=review.get('hook_candidates',[])
 if not isinstance(candidates,list) or not 1<=len(candidates)<=3:raise ValueError('Hiányzik az összehasonlított hook-javaslat.')
 checked=[]
 for c in candidates:
  if not isinstance(c,dict) or type(c.get('id')) is not int or c['id'] not in range(len(catalog)) or not isinstance(c.get('reason'),str) or not c['reason'].strip():raise ValueError('Nem igazolt hook-javaslat.')
  checked.append(dict(id=c['id'],reason=c['reason'][:300]))
 own=review.get('plan') if isinstance(review.get('plan'),dict) else {}
 if plan['unit_ids'][0] not in [c['id'] for c in checked]:
  # The reviewer's own approved plan opens on this hook: that is a reviewed choice.
  if own.get('hook')!=plan['unit_ids'][0]:raise ValueError('A kiválasztott hook nem szerepel az összehasonlított jelöltek között.')
  checked=[dict(id=own['hook'],reason=str(own.get('context') or 'A szerkesztő által jóváhagyott nyitás.')[:300])]+checked[:2]
  review['hook_candidates']=checked
 notes=review.get('beats',[])
 if not isinstance(notes,list):raise ValueError('Érvénytelen szerkesztői ütemterv.')
 seen=set()
 for note in notes:
  if not isinstance(note,dict):raise ValueError('Érvénytelen szerkesztői megjegyzés.')
  uid=note.get('id')
  # Beat notes only style shots; a note for a dropped or repeated unit is ignored, not fatal.
  if type(uid) is not int or uid not in plan['unit_ids'] or uid in seen:continue
  seen.add(uid);shot=plan['shots'][plan['unit_ids'].index(uid)]
  if note.get('beat') in ('context','payoff','reaction','ending') and shot['beat']!='hook':shot['beat']=note['beat']
  from smart_framing import cutaway
  shot['cutaway']=cutaway(note,catalog[uid],catalog)
  shot['preserve_pause']=note.get('preserve_pause') is True
  shot['reason']=str(note.get('reason') or shot['reason'])[:300]
  shot['transition']='wipe' if note.get('transition')=='wipe' and not shot.get('preserve_pause') and shot['beat']=='context' else 'cut'
  from sfx import CHOICES as SOUND_CHOICES,seconds as sound_seconds
  shot['sound']=note.get('sound') if note.get('sound') in SOUND_CHOICES else 'none'
  # End punctuation, rather than an accent over the start of every spoken sentence.
  shot['sound_delay']=max(0,shot['end']-shot['start']-(sound_seconds(shot['sound']) or .18))
  intentional=note.get('camera')=='speaker' and note.get('effect')=='punch-in' and shot['beat'] in ('hook','payoff','reaction') and not shot['preserve_pause']
  shot['zoom_justified']=intentional
  shot['framing']='speaker' if intentional else 'wide'
  shot['effect']='punch-in' if intentional else 'none'
  if shot['preserve_pause']:shot['sound']='none';shot['effect']='none'
 if not any(s['beat']=='payoff' for s in plan['shots']):
  # Full-content summaries carry the surveyed outcome IDs; mark those real units as the payoff.
  for shot,uid in zip(plan['shots'],plan['unit_ids']):
   if uid in payoff_ids and shot['beat']!='hook':shot['beat']='payoff'
 if not any(s['beat']=='payoff' for s in plan['shots']):raise ValueError('A tervből hiányzik a valós csattanó.')
 # The displayed outline quotes selected evidence; model explanations remain separate.
 payoff_index=max(i for i,shot in enumerate(plan['shots']) if shot['beat']=='payoff')
 plan['outline'].update(context=catalog[plan['unit_ids'][1]]['text'],payoff=catalog[plan['unit_ids'][payoff_index]]['text'],ending=catalog[plan['unit_ids'][-1]]['text'])
 plan['storyboard']=storyboard(plan,catalog)
 plan['editorial_review']=dict(approved=True,hook_candidates=checked,humor_type=review.get('humor_type') if review.get('humor_type') in ('irony','deadpan','misdirection','reaction','absurd','situational','none') else 'none',joke_setup=str(review.get('joke_setup',''))[:350],payoff_evidence=str(review.get('payoff_evidence',''))[:350],removed_reason=str(review.get('removed_reason',''))[:350],assessment='model_editorial_opinion_not_audience_measurement')
 return plan

TERMINAL=re.compile(r'[.!?…]["\'”’)\]]*\s*$')

def _overlaps(unit,ids,catalog):
 return any(catalog[i]['source']==unit['source'] and min(catalog[i]['end'],unit['end'])-max(catalog[i]['start'],unit['start'])>.05 for i in ids)

def _insert(ids,uid,catalog):
 """Place a restored unit chronologically after its closest selected predecessor (the hook stays first)."""
 unit=catalog[uid];body=ids[1:]
 before=[n for n,i in enumerate(body) if catalog[i]['source']==unit['source'] and catalog[i]['start']<unit['start']]
 position=max(before)+1 if before else next((n for n,i in enumerate(body) if catalog[i]['source']==unit['source']),len(body))
 return [ids[0]]+body[:position]+[uid]+body[position:]

def complete_ending(ids,catalog,style):
 """A question or unfinished last line keeps its real, immediately following answer."""
 ids=list(ids)
 for _ in range(2):
  last=catalog[ids[-1]];text=last['text'].strip()
  if last.get('boundary')=='visual_sample' or TERMINAL.search(text) and not text.endswith('?'):break
  nxt=next((u for u in catalog if u['id'] not in ids and u['source']==last['source'] and -.05<=u['start']-last['end']<=1.1 and u.get('boundary')!='visual_sample'),None)
  seconds=sum(catalog[i]['seconds'] for i in ids)
  if not nxt or seconds+nxt['seconds']>style['max_seconds'] or len(ids)>=style['max_shots'] or _overlaps(nxt,ids,catalog):break
  ids.append(nxt['id'])
 return ids

def expand_context(ids,catalog,style):
 """Reach the requested length with the selection's own surrounding source context.

 Preference: missing context between selected parts, then setup before the first. The approved
 ending is never moved; only complete_ending may append its immediate continuation. Survey importance breaks ties. Never repeats footage, never
 adds another source, never exceeds max_seconds.
 """
 ids=list(ids);seconds=sum(catalog[i]['seconds'] for i in ids)
 for _ in range(len(catalog)):
  if seconds>=style['min_seconds'] and len(ids)>=style['min_shots'] or len(ids)>=style['max_shots']:break
  sources={catalog[i]['source'] for i in ids};best=None
  for u in catalog:
   if u['id'] in ids or u['source'] not in sources or seconds+u['seconds']>style['max_seconds'] or _overlaps(u,ids,catalog):continue
   chosen=sorted((catalog[i] for i in ids if catalog[i]['source']==u['source']),key=lambda x:x['start'])
   first,last=chosen[0],chosen[-1]
   # The approved ending stays the ending: only missing context between or before the parts.
   if first['end']<=u['start'] and u['end']<=last['start']:kind,gap=3,0
   elif u['end']<=first['start']:kind,gap=1,first['start']-u['end']
   else:continue
   if gap>45:continue
   score=kind*2+u.get('importance',3)-gap/15
   if best is None or score>best[0]:best=(score,u['id'])
  if best is None:break
  ids=_insert(ids,best[1],catalog);seconds+=catalog[best[1]]['seconds']
 return ids

def only_additions(approved,final):
 """True when final keeps every approved unit in the same order and only inserts real units."""
 it=iter(final)
 return bool(approved) and final[:1]==approved[:1] and all(any(x==y for y in it) for x in approved)

def cover_sources(ids,catalog,style):
 """Every operator-supplied source contributes its strongest self-contained moment."""
 ids=list(ids);value=lambda u:u.get('hook_score',0)+2*u.get('importance',3)
 for source in sorted({u['source'] for u in catalog}-{catalog[i]['source'] for i in ids}):
  options=sorted((u for u in catalog if u['source']==source and not u.get('starts_mid_sentence') and u.get('boundary')!='visual_sample'),key=lambda u:(len(u['text'].split())<=6,-value(u),u['start']))
  if not options:raise ValueError('Az egyik megadott videóból nincs felhasználható, önálló részlet.')
  pick=options[0]
  # Make room by dropping the weakest middle units of over-represented sources (never hook or ending).
  while sum(catalog[i]['seconds'] for i in ids)+pick['seconds']>style['max_seconds'] or len(ids)>=style['max_shots']:
   counts={}
   for i in ids:counts[catalog[i]['source']]=counts.get(catalog[i]['source'],0)+1
   middle=[i for i in ids[1:-1] if counts[catalog[i]['source']]>1]
   if not middle:raise ValueError('A megadott videók legfontosabb részletei együtt túl hosszúak.')
   ids.remove(min(middle,key=lambda i:value(catalog[i])))
  later=[n for n,i in enumerate(ids) if n and catalog[i]['source']>source]
  position=later[0] if later else len(ids)
  ids=ids[:position]+[pick['id']]+ids[position:]
 return ids

def feasible_story(choice,catalog,style):
 """Adapt per-run targets to an approved real story, never add filler or fake timestamps."""
 if not isinstance(choice,dict) or type(choice.get('hook')) is not int:raise ValueError('Valós hook-azonosító szükséges.')
 choice=complete_sentences(choice,catalog)
 sequence=choice.get('sequence',[])
 if not isinstance(sequence,list) or any(type(i) is not int for i in sequence):raise ValueError('Egész jelenetazonosítók szükségesek.')
 ids=[choice['hook']]+[i for i in sequence if i!=choice['hook']]
 if len(ids)!=len(set(ids)) or any(not 0<=i<len(catalog) for i in ids):raise ValueError('Ismeretlen vagy ismételt jelenet.')
 if not choice.get('fixed_sequence'):
  # The model chooses meaning; length arithmetic and adjacent context are restored here.
  if style.get('length_policy','adaptive')!='adaptive' and (sum(catalog[i]['seconds'] for i in ids)<style['min_seconds'] or len(ids)<style['min_shots']):
   ids=expand_context(ids,catalog,style)
  ids=complete_ending(ids,catalog,style)
  if style.get('require_all_sources'):ids=cover_sources(ids,catalog,style)
  if ids!=[choice['hook']]+[i for i in sequence if i!=choice['hook']]:
   choice=complete_sentences(dict(choice,hook=ids[0],sequence=ids[1:]),catalog);ids=[choice['hook']]+choice['sequence']
 seconds=sum(catalog[i]['end']-catalog[i]['start'] for i in ids);effective=dict(style)
 if style.get('length_policy','adaptive')=='adaptive' and 12<=seconds<=style['max_seconds'] and len(ids)>=2:
  effective['min_seconds']=min(style['min_seconds'],int(seconds));effective['min_shots']=min(style['min_shots'],len(ids))
  effective['target_seconds']=max(effective['min_seconds'],min(style['target_seconds'],round(seconds)))
 plan=compile_story(dict(choice,strict_story=True),catalog,effective)
 return plan,effective

def context_windows(catalog,style,hook=None):
 """Alternative contiguous source context for the model to review, never auto-approved."""
 windows=[]
 anchors=[u for u in catalog if u['id']==hook]+[u for u in catalog if u['id']!=hook]
 for anchor in anchors:
  neighbors=[u for u in catalog if u.get('boundary')!='visual_sample' and u['source']==anchor['source'] and anchor['start']-15<=u['start']<=anchor['end']+45]
  neighbors.sort(key=lambda u:u['start']);ids=[];total=0;end=None
  for u in neighbors:
   if end is not None and u['start']-end>2:
    if anchor['id'] in ids:break
    ids=[];total=0
   if total+u['seconds']>style['max_seconds'] or len(ids)>=style['max_shots']:break
   ids.append(u['id']);total+=u['seconds'];end=u['end']
  if anchor['id'] not in ids or total<12 or len(ids)<2:continue
  sequence=[i for i in ids if i!=anchor['id']]
  signature=tuple(sorted(ids))
  if any(tuple(sorted([w['hook']]+w['sequence']))==signature for w in windows):continue
  proposed=dict(hook=anchor['id'],sequence=sequence)
  try:valid,_=feasible_story(proposed,catalog,style)
  except ValueError:continue
  sequence=valid['unit_ids'][1:]
  windows.append(dict(hook=valid['unit_ids'][0],sequence=sequence,context='Contiguous real source context; editor must verify meaning.',payoff='Editor must identify a real payoff in these units.',caption_theme='clean',available_seconds=round(total,2)))
  if len(windows)>=3:break
 return windows

def duration_candidates(catalog,style,hook=None):
 """Offer only complete adjacent-context options that already pass timing checks.

 The editor must still approve their meaning; timing never implies semantic approval.
 """
 result=[];seen=set();visual_options=[];groups=[]
 for source in sorted({u['source'] for u in catalog}):
  units=[u for u in catalog if u['source']==source and u.get('boundary')=='visual_sample'];total=0;ids=[]
  for u in units:
   if total+u['seconds']<=style['max_seconds'] and len(ids)<style['max_shots']:ids.append(u['id']);total+=u['seconds']
  if len(ids)>=2:visual_options.append(dict(hook=ids[0],sequence=ids[1:],context='Sampled visual montage from one source; verify thematic coherence, not continuous action.',payoff='Editor must identify an evidenced visual highlight.',caption_theme='clean'))
 # A compilation can contain multiple COMPLETE source moments. Offer this
 # grounded chronological alternative instead of unrelated fixed sample windows.
 compilation_options=[]
 for source in sorted({u['source'] for u in catalog}):
  compilation=[];total=0;seen_lines=set()
  for unit in sorted((u for u in catalog if u['source']==source),key=lambda u:u['start']):
   text=re.sub(r'\s+',' ',unit['text'].casefold()).strip()
   if re.search(r'^(welcome to|please subscribe|like and subscribe)',text):continue
   if re.fullmatch(r'(?:u+m+|u+h+|e+r+m+|h+m+|uhh?)[.!?… ]*',text):continue
   if re.search(r'[-—–]\s*$',text):continue
   if len(text.split())>=15 and any(len(prior.split())>=15 and SequenceMatcher(None,prior,text).ratio()>=.84 for prior in seen_lines):continue
   if len(text.split())>=6 and text in seen_lines:continue
   if total+unit['seconds']>style['max_seconds'] or len(compilation)>=style['max_shots']:continue
   compilation.append(unit['id']);total+=unit['seconds'];seen_lines.add(text)
  compilation_options += [dict(hook=compilation[0],sequence=compilation[1:],context='Chronological compilation of evidenced complete source utterances and visual context. Different episodes must not be presented as one dialogue.',payoff='Editor must identify the real highlight and supported closing moment.',caption_theme='clean')] if len(compilation)>=2 else []
 for choice in visual_options+context_windows(catalog,style,hook)+context_windows(catalog,style)+compilation_options:
  signature=tuple([choice['hook']]+choice['sequence'])
  if signature in seen:continue
  try:plan,effective=feasible_story(choice,catalog,style)
  except ValueError:continue
  variants=[choice]
  ids=[choice['hook']]+choice['sequence']
  for uid in ids:
   if uid!=choice['hook'] and catalog[uid].get('visual_samples'):variants.append(dict(choice,hook=uid,sequence=[i for i in ids if i!=uid]))
  groups.append((variants,plan))
 # Offer different sources/context first, then opening variants.
 for offset in range(max((len(v) for v,_ in groups),default=0)):
  for variants,plan in groups:
   if offset>=len(variants):continue
   variant=variants[offset]
   try:plan,_=feasible_story(variant,catalog,style)
   except ValueError:continue
   variant=dict(variant,hook=plan['unit_ids'][0],sequence=plan['unit_ids'][1:])
   signature=tuple([variant['hook']]+variant['sequence'])
   if signature in seen:continue
   seen.add(signature);result.append(dict(variant,candidate_id=len(result),verified_seconds=plan['duration'],verified_units=len(plan['unit_ids'])))
   if len(result)>=6:return result

 return result


def candidate_review_input(topic,candidates,catalog,style):
 """Fresh content-review evidence; discarded draft errors cannot contaminate it."""
 checked=[];ids=set()
 for candidate in candidates:
  plan,_=feasible_story(candidate,catalog,style)
  ordered=[candidate['hook']]+candidate['sequence'];ids.update(ordered)
  checked.append(dict(candidate,candidate_id=len(checked),verified_seconds=plan['duration'],
   verified_units=len(plan['unit_ids']),non_overlapping=True,
   intervals=[dict(id=i,source=catalog[i]['source'],start=catalog[i]['start'],end=catalog[i]['end']) for i in ordered]))
 if not checked:raise ValueError('Nincs időben ellenőrzött szerkesztési jelölt.')
 return dict(topic=topic,selection_rule='Choose exactly one alternative. Never combine candidates.',
  validation=dict(authority='server_interval_validator',scope='each candidate independently',
   checks=['unique units','no overlapping intervals within the same source','duration','shot count']),
  catalog=[u for u in catalog if u['id'] in ids],candidates=checked,
  requirements=dict(min_seconds=style['min_seconds'],max_seconds=style['max_seconds'],length_policy=style.get('length_policy','adaptive')))


def storyboard(plan,catalog):
 """An inspectable timeline bound to the exact selected transcript/visual evidence."""
 result=[];cursor=0
 payoff_index=max((i for i,s in enumerate(plan['shots']) if s['beat']=='payoff'),default=max(1,len(plan['shots'])-2))
 for index,(uid,shot) in enumerate(zip(plan['unit_ids'],plan['shots'])):
  unit=catalog[uid];duration=shot['end']-shot['start']
  phase='hook' if index==0 else 'ending' if index==len(plan['shots'])-1 else 'payoff' if index==payoff_index else 'context' if index==1 else 'development'
  result.append(dict(phase=phase,unit_id=uid,source=shot['source'],source_start=shot['start'],source_end=shot['end'],output_start=round(cursor,3),output_end=round(cursor+duration,3),evidence=unit['text'],purpose=shot['reason']))
  cursor+=duration
 return result
