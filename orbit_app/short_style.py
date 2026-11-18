"""Persistent editing brief shared by the supervisor and the deterministic render pipeline."""
import json,re,time,math
MIN_EDIT_UNIT_SECONDS=.35
DURATION_TOLERANCE_SECONDS=.25

def duration_allowed(duration,style):
 return type(duration) in (int,float) and math.isfinite(duration) and style['min_seconds']-DURATION_TOLERANCE_SECONDS<=duration<=style['max_seconds']+DURATION_TOLERANCE_SECONDS

DEFAULT=dict(render_engine='auto',length_policy='adaptive',editing='montage',source_count=2,min_shots=4,max_shots=24,max_shot_seconds=7,target_seconds=75,min_seconds=60,max_seconds=90,caption_position='lower-third',captions='word-highlight',highlight_color='#35F2C5',safe_box=[108,1320,864,1580],language='en',visual_analysis=True,subject_tracking=True,publish_to_youtube=False,review_before_upload=True,portrait_framing='fill',made_for_kids=False)
def schema(s):s.db.execute('CREATE TABLE IF NOT EXISTS short_styles(project TEXT PRIMARY KEY,data TEXT,updated REAL)');s.db.commit()
def get(s,pid):
 schema(s);row=s.db.execute('SELECT data FROM short_styles WHERE project=?',(pid,)).fetchone();data=dict(DEFAULT,**(json.loads(row[0]) if row else {}))
 if row and 'min_seconds' not in json.loads(row[0]):data.update(min_seconds=60,max_seconds=90,target_seconds=75,max_shots=24,caption_position='lower-third',safe_box=[108,1320,864,1580])
 return data
def validated(base,settings):
 data=dict(base)
 if not isinstance(settings,dict) or set(settings)-set(DEFAULT):raise ValueError('Ismeretlen videóstílus-beállítás.')
 data.update(settings)
 if data.get('render_engine') not in ('auto','ffmpeg','remotion'):raise ValueError('Ismeretlen renderelőmotor.')
 if data['portrait_framing'] not in ('fill','context'):raise ValueError('Ismeretlen álló képkivágás.')
 if any(type(data[key]) is not bool for key in ('visual_analysis','subject_tracking','publish_to_youtube','review_before_upload','made_for_kids')):raise ValueError('A képi elemzés és követés beállítása logikai érték legyen.')
 if data['length_policy'] not in ('adaptive','strict'):raise ValueError('Ismeretlen hosszkezelés.')
 if data['editing'] not in ('montage','single') or data['captions'] not in ('word-highlight','plain'):raise ValueError('Ismeretlen vágási vagy feliratstílus.')
 for key,low,high in [('source_count',1,3),('min_shots',2,10),('max_shots',2,32),('max_shot_seconds',2,12),('target_seconds',10,180),('min_seconds',10,180),('max_seconds',10,180)]:
  if type(data[key])!=int or not low<=data[key]<=high:raise ValueError('Érvénytelen videóstílus: '+key)
 if not data['min_seconds']<=data['target_seconds']<=data['max_seconds'] or data['max_shots']*data['max_shot_seconds']<data['min_seconds']:raise ValueError('A kért hossz nem teljesíthető ezekkel a vágási korlátokkal.')
 if data['caption_position'] not in ('lower-third','center'):raise ValueError('Ismeretlen feliratpozíció.')
 data['safe_box']=[108,1320,864,1580] if data['caption_position']=='lower-third' else [108,880,864,1220]
 if data['min_shots']>data['max_shots']:raise ValueError('A jelenetszám határai hibásak.')
 if not re.fullmatch(r'#[0-9A-Fa-f]{6}',data['highlight_color'])  or data['language'] not in ('en','hu','auto'):raise ValueError('Érvénytelen feliratbeállítás.')
 return data

def save(s,pid,settings):
 s.project(pid);schema(s);data=validated(get(s,pid),settings)
 s.db.execute('INSERT OR REPLACE INTO short_styles VALUES(?,?,?)',(pid,json.dumps(data),time.time()));s.db.commit();return data

def recognize(s,text):
 p=text.casefold()
 if not ('shorts' in p and any(x in p for x in ('felirat','caption','vág','cut')) and any(x in p for x in ('akarok','szeretn','legyen','állíts','allits','változt','valtozt'))):return None
 rows=[x for x in s.rows('SELECT id,name FROM projects') if 'shorts' in x['name'].casefold()]
 if len(rows)!=1:return None
 return rows[0]['id']

def select_montage(choice,tracks,style):
 """Ground every cut in real source bounds; require multiple distinct moments."""
 found=[];limits={i:float(t['source']['duration']) for i,t in enumerate(tracks)}
 if any(not math.isfinite(v) or v<=0 for v in limits.values()):raise ValueError('Érvénytelen forrásidőtartam.')
 for item in choice.get('shots',[])[:style['max_shots']] if isinstance(choice,dict) else []:
  try:
   source=int(item['source']);start=float(item['start']);end=float(item['end'])
   if not all(math.isfinite(v) for v in (start,end)) or source not in limits or not 0<=start<end<=limits[source]+.05 or not 1<=end-start<=style['max_shot_seconds']+.05:continue
   from editorial import story_units
   units=story_units(tracks[source].get('transcript',{}),style['max_shot_seconds'])
   nearby=[u for u in units if abs(u['start']-start)<=1.0 and abs(u['end']-end)<=1.5]
   if nearby:
    unit=min(nearby,key=lambda u:abs(u['start']-start)+abs(u['end']-end));start,end=unit['start'],unit['end']
   if not 1<=end-start<=style['max_shot_seconds']+.05:continue
   if any(source==x['source'] and min(end,x['end'])>max(start,x['start'])+.1 for x in found):continue
   found.append(dict(source=source,start=round(start,3),end=round(end,3),reason=str(item.get('reason',''))[:300],effect=item.get('effect') if item.get('effect') in ('punch-in','spotlight') else 'none',framing='speaker' if item.get('framing')=='speaker' else 'wide',beat=item.get('beat') if item.get('beat') in ('hook','context','payoff','ending') else 'context',transition='fade' if item.get('transition')=='fade' else 'cut',sound=item.get('sound') if item.get('sound') in ('pop','whoosh') else 'none'))
  except (KeyError,ValueError,TypeError,OverflowError):continue
 if len(found)>=style['min_shots'] and style['min_seconds']<=sum(x['end']-x['start'] for x in found)<=style['max_seconds']:return dict(shots=found,caption_theme=choice.get('caption_theme') if choice.get('caption_theme') in ('clean','gaming','energetic','story') else 'clean',outline={k:str((choice.get('outline') if isinstance(choice.get('outline'),dict) else {}).get(k,''))[:350] for k in ('hook','context','payoff','ending')},selection='local_ai',duration=round(sum(x['end']-x['start'] for x in found),3))
 # Honest fallback: choose separated real speech windows, never reuse an unrelated test clip.
 candidates=[]
 for index,track in enumerate(tracks):
  from editorial import story_units
  units=story_units(track['transcript'],style['max_shot_seconds']) or track['transcript'].get('segments',[])
  for segment in units:
   try:start=float(segment['start']);end=float(segment['end'])
   except (ValueError,TypeError,KeyError):continue
   if not math.isfinite(start) or not math.isfinite(end):continue
   start=max(0,start);end=min(limits[index],end,start+style['max_shot_seconds']);text=segment.get('text','').lower()
   if end-start<1:continue
   score=sum(text.count(w) for w in ('what','wait','wow','no','oh','crazy','bro','laugh','why','yes'))+min(1,len(text.split())/20)
   candidates.append((score,index,start,end))
 candidates.sort(reverse=True);found=[]
 for score,index,start,end in candidates:
  if any(index==x['source'] and min(end,x['end'])>max(start,x['start'])-.35 for x in found):continue
  remaining=style['max_seconds']-sum(x['end']-x['start'] for x in found)
  if remaining<1:break
  end=min(end,start+remaining)
  found.append(dict(source=index,start=round(start,3),end=round(end,3),reason='Valós beszéd és reakciószavak alapján választott részlet.'))
  if len(found)>=style['max_shots'] or (len(found)>=style['min_shots'] and sum(x['end']-x['start'] for x in found)>=style['target_seconds']):break
 if len(found)<style['min_shots']:raise ValueError('A forrásokban nincs elég különálló beszédrészlet a feszes montázshoz. További forrás szükséges; egyetlen hosszú klippel nem helyettesítjük.')
 if sum(x['end']-x['start'] for x in found)<style['min_seconds']-.05:raise ValueError('Nincs elegendő igazolt részlet a kért '+str(style['min_seconds'])+'–'+str(style['max_seconds'])+' másodperchez. Rövidebb videót nem jelölünk késznek; több releváns forrás szükséges.')
 found.sort(key=lambda x:(x['source'],x['start']))
 return dict(shots=found,selection='speech_reaction_fallback',duration=round(sum(x['end']-x['start'] for x in found),3))


def requested_settings(text):
 """Extract explicit constraints, never mistake a complained-about duration for a target."""
 p=text.casefold().replace(',', '.')
 result={}
 if re.search(r'\b(2\s?okos|magyar|hungarian)\b',p):result['language']='hu'
 elif re.search(r'\b(angol|english)\b',p):result['language']='en'
 match=re.search(r'(\d+(?:\.\d+)?)\s*(?:mp|másodperc|seconds?|sec|perc|minutes?)?\s*(?:-|–|—|to|és)\s*(\d+(?:\.\d+)?)\s*(másodperc|mp|seconds?|sec|s\b|perc|minutes?)',p)
 if match:
  lo,hi=map(float,match.group(1,2));factor=60 if match.group(3) in ('perc','minute','minutes') else 1
  lo,hi=round(lo*factor),round(hi*factor)
  if 10<=lo<=hi<=180:result.update(min_seconds=lo,max_seconds=hi,target_seconds=round((lo+hi)/2),max_shots=32)
 if any(x in p for x in ('alsó harmad','alsó tartomány','lower third','bottom third','lejjebb')):result['caption_position']='lower-third'
 elif any(x in p for x in ('felirat középen','captions in the center')):result['caption_position']='center'
 return result


def caption_preset(style):
 box=style['safe_box']
 return dict(name='tiktok-word-v3',box=box,anchor=[486,box[3]-20],font_size=72,max_lines=2,animation='word-pop',timing='whisper-words',highlight=style['highlight_color'])


def validate_output(manifest,style):
 duration=manifest.get('duration',0)
 if not duration_allowed(duration,style):raise ValueError('A videó hossza nem teljesíti a kért '+str(style['min_seconds'])+'–'+str(style['max_seconds'])+' másodpercet.')
 if manifest.get('caption_style',{}).get('anchor')!=caption_preset(style)['anchor']:raise ValueError('A felirat helye nem egyezik a mentett projektbeállítással.')


def source_matches(query,candidate):
 """Conservative subject gate, metadata is evidence, never executable instructions."""
 import unicodedata
 def norm(value):return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(c))
 q=norm(query);body=norm(' '.join(str(candidate.get(k,'') or '') for k in ('title','description','channel')))
 if '://' in q:return True  # An explicit source URL is already selected by the user.
 aliases=[(('2okos','2 okos','ket okos'),('2okos','2 okos','ket okos')), (('messi','lionel'),('messi','lionel')), (('xqc',),('xqc',)), (('ronaldo','cristiano'),('ronaldo','cristiano')), (('ishowspeed','ishow speed','speed'),('ishowspeed','ishow speed','speed')), (('kai cenat','kai'),('kai cenat','kai')), (('zlatan',),('zlatan',))]
 matched=False
 for query_names,names in aliases:
  if any(re.search(r'\b'+re.escape(n)+r'\b',q) for n in query_names):
   matched=True
   if not any(re.search(r'\b'+re.escape(n)+r'\b',body) for n in names):return False
 if matched:return True
 ignored={'best','top','moments','highlights','funny','stream','streamer','clips','video','seconds','caption','captions','lower','third','english','magyar','hungarian','stream','highlight','legjobb','pillanatok','reszletek','video','keszits','the','and','to','of','in','a'}
 terms=[x for x in re.findall(r'[a-z0-9]{3,}',q) if x not in ignored]
 return bool(terms) and sum(x in body for x in terms)>=max(1,(len(terms)+1)//2)
