"""Conservative, independently observed visual regions for portrait composition."""
import math

def region(value):
 box=value.get('box',[]) if isinstance(value,dict) else []
 if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (float,int) or not math.isfinite(v) for v in box):return None
 x,y,w,h=box
 if not 0<=x<1 or not 0<=y<1 or w<.1 or h<.1 or x+w>1.001 or y+h>1.001 or value.get('kind') not in ('game','speaker','subject','screen') or type(value.get('confidence')) not in (int,float) or value['confidence']<.85:return None
 return dict(kind=value['kind'],box=box,confidence=min(1,value['confidence']))

def composition(observation,start,end):
 frames=[f for f in observation.get('frames',[]) if start-.1<=f.get('seconds',-10)<=end+.1]
 if len(frames)<2 or observation.get('aspect_ratio',1)<1.2:return None
 result=[]
 for first in frames[0].get('regions',[]):
  r=region(first)
  if not r:continue
  if any(any((q:=region(v)) and q['kind']==r['kind'] and all(abs(a-b)<.06 for a,b in zip(q['box'],r['box'])) for v in f.get('regions',[])) for f in frames[1:]):result.append(r)
 for i,a in enumerate(result):
  for b in result[i+1:]:
   ax,ay,aw,ah=a['box'];bx,by,bw,bh=b['box'];overlap=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
   if overlap>.1*min(aw*ah,bw*bh):continue
   if {a['kind'],b['kind']}=={'game','speaker'}:
    speaker=a if a['kind']=='speaker' else b;game=b if b['kind']=='game' else a
    return dict(mode='stack',regions=[speaker['box'],game['box']],top_fraction=.3,reason='Visible facecam and game preserved in a portrait stack.')
   if {a['kind'],b['kind']}=={'screen','speaker'}:
    speaker=a if a['kind']=='speaker' else b;screen=b if b['kind']=='screen' else a
    return dict(mode='pip',regions=[speaker['box'],screen['box']],top_fraction=.3,reason='Readable screen with a separate observed facecam inset.')
   if a['kind']==b['kind']=='subject':return dict(mode='stack',regions=[a['box'],b['box']],top_fraction=.5,reason='Two separately observed comparison subjects remain visible.')
 return None

def validate(value):
 if not isinstance(value,dict) or value.get('mode') not in ('stack','pip') or value.get('top_fraction') not in (.3,.5):raise ValueError('Érvénytelen osztott képelrendezés.')
 boxes=value.get('regions',[])
 if not isinstance(boxes,list) or len(boxes)!=2 or any(region(dict(box=b,kind='subject',confidence=1)) is None for b in boxes):raise ValueError('Hiányzó képkivágási területek.')
 return dict(mode=value['mode'],regions=boxes,top_fraction=value['top_fraction'])

def filters(input_label,output_label,value,prefix):
 v=validate(value)
 if v['mode']=='pip':
  parts=[f'{input_label}split=2[{prefix}a][{prefix}b]']
  for suffix,box in zip(('a','b'),v['regions']):
   x,y,w,h=box
   geom='scale=288:384:force_original_aspect_ratio=increase,crop=288:384' if suffix=='a' else 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x10191d'
   parts.append(f'[{prefix}{suffix}]crop=w=trunc(iw*{w}/2)*2:h=trunc(ih*{h}/2)*2:x=trunc(iw*{x}/2)*2:y=trunc(ih*{y}/2)*2,{geom},setsar=1[{prefix}{suffix}o]')
  parts.append(f'[{prefix}bo][{prefix}ao]overlay=x=684:y=108{output_label}');return parts
 height=round(1920*v['top_fraction']/2)*2;parts=[f'{input_label}split=2[{prefix}a][{prefix}b]']
 for suffix,box,h in zip(('a','b'),v['regions'],(height,1920-height)):
  x,y,w,bh=box
  parts.append(f'[{prefix}{suffix}]crop=w=trunc(iw*{w}/2)*2:h=trunc(ih*{bh}/2)*2:x=trunc(iw*{x}/2)*2:y=trunc(ih*{y}/2)*2,scale=1080:{h}:force_original_aspect_ratio=increase,crop=1080:{h},setsar=1[{prefix}{suffix}o]')
 parts.append(f'[{prefix}ao][{prefix}bo]vstack=inputs=2{output_label}');return parts

def cutaway(note,primary,catalog):
 """A reviewer may use a different evidenced visual while retaining original narration."""
 uid=note.get('cutaway_id');reason=note.get('cutaway_reason')
 if type(uid) is not int or not 0<=uid<len(catalog) or uid==primary.get('id') or not isinstance(reason,str) or len(reason.strip())<12:return None
 visual=catalog[uid]
 if visual['source']==primary['source']:return None
 samples=visual.get('visual_samples',[])
 if len(samples)<2 or visual['end']-visual['start']<primary['end']-primary['start']:return None
 return dict(source=visual['source'],start=visual['start'],end=visual['start']+primary['end']-primary['start'],reason=reason[:300],assessment='Model-reviewed visual illustration; original narration retained, not independent proof of an event.')
