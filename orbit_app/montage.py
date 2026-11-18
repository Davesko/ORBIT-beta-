"""Word-timed social captions and frame-accurate multi-source edit assembly."""
from sfx import NAMES as SFX_NAMES
import html,json,re,subprocess
from pathlib import Path
WORD_PRESET=dict(name='tiktok-word-v2',box=[108,880,864,1220],anchor=[486,1200],font_size=72,max_lines=2,animation='word-pop',timing='whisper-words',highlight='#35F2C5')
def clean(text):return ''.join(c for c in html.unescape(re.sub(r'<[^>]*>|\{[^}]*\}','',str(text))).replace('\\',' ') if c.isprintable()).strip()
def ass_stamp(seconds):
 cs=max(0,round(seconds*100));return '%d:%02d:%02d.%02d'%(cs//360000,cs//6000%60,cs//100%60,cs%100)
def groups(words,font_size=72,font_name='Arial',max_width=680):
 try:
  from PIL import ImageFont
  font=ImageFont.truetype('/System/Library/Fonts/Supplemental/'+font_name+' Bold.ttf',font_size)
  width=font.getlength
 except (ImportError,OSError):
  # The supervisor uses system Python; conservative bounds avoid a Pillow dependency.
  width=lambda text:sum(font_size if c.isupper() else font_size*.8 for c in text)
 current=[]
 for word in words:
  word=dict(word,text=clean(word.get('text',word.get('word',''))))
  if not word['text'] or word['end']<=word['start']:continue
  if current and (len(current)>=4 or re.search(r'[.!?…][\"\x27)]?$',current[-1]['text']) or width(' '.join(w['text'] for w in current+[word]))>max_width or word['start']-current[-1]['end']>.45):yield current;current=[]
  current.append(word)
 if current:yield current

def write_word_captions(words,target,color='#35F2C5',preset=None):
 preset=preset or WORD_PRESET
 if not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):raise ValueError('Érvénytelen feliratszín.')
 rgb=color[1:];active='&H'+rgb[4:6]+rgb[2:4]+rgb[0:2]+'&';events=[]
 header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,60,&H00FFFFFF,&H0035F2C5,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,108,216,720,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
 font=preset.get('font','Arial');size=preset.get('font_size',72)
 if font not in ('Arial','Trebuchet MS','Georgia') or size not in range(44,85):raise ValueError('Érvénytelen feliratprofil.')
 header=header.replace('Style: Default,Arial,60,','Style: Default,'+font+','+str(size)+',')
 for group in groups(words,size,font,max_width=min(680,(preset['box'][2]-preset['box'][0]-24)/1.08)):
  for i,word in enumerate(group):
   start=float(word['start']);end=float(group[i+1]['start']) if i+1<len(group) else float(word['end'])
   if end<=start:end=float(word['end'])
   tokens=[]
   for n,w in enumerate(group):
    if n==i:tokens.append(r'{\c'+active+r'\fscx108\fscy108\t(0,90,\fscx100\fscy100)}'+w['text']+r'{\rDefault}')
    else:tokens.append(w['text'])
   if preset.get('animation')=='fade':tokens=[(r'{\c'+active+'}'+w['text']+r'{\rDefault}') if n==i else w['text'] for n,w in enumerate(group)]
   tags=r'{\an2\pos(%d,%d)\clip(%d,%d,%d,%d)\q2}'%tuple(preset['anchor']+preset['box'])
   events.append('Dialogue: 0,'+ass_stamp(start)+','+ass_stamp(end)+',Default,,0,0,0,,'+tags+(r'{\fad(35,35)}' if preset.get('animation')=='fade' else '')+' '.join(tokens))
 if not events:raise ValueError('Nincs valós szóidőzítés a felirathoz.')
 Path(target).write_text(header+'\n'.join(events),encoding='utf-8');return len(events)

def remap_words(shots):
 """Normalize ASR ordering at ingress, then map onto actual cumulative frame cuts.
 Overlapping Whisper windows may repeat words or arrive out of order. Never invent
 replacement speech or timestamps; reject non-finite values and retain real times.
 """
 import math
 result=[];cursor=0
 for shot,frames in zip(shots,frame_budgets(shots)):
  transcript=json.loads(Path(shot['transcript']).read_text()) if shot.get('transcript') else {}
  start,end=shot['start'],shot['start']+min(shot['duration'],frames/30)
  candidates=[];seen=set()
  for segment in transcript.get('segments',[]):
   if segment.get('usable_for_story') is False:continue
   for word in segment.get('words',[]):
    begin,finish=float(word['start']),float(word['end'])
    if not all(math.isfinite(v) for v in (begin,finish)) or finish<=begin:raise ValueError('Invalid source word timing')
    if finish<=start or begin>=end:continue
    text=clean(word.get('word',word.get('text','')))
    key=(round(begin,3),round(finish,3),text)
    if key in seen or not text:continue
    seen.add(key);candidates.append((begin,finish,text))
  for begin,finish,text in sorted(candidates):
   result.append(dict(start=round(cursor/30+max(start,begin)-start,6),end=round(cursor/30+min(end,finish)-start,6),text=text))
  cursor+=frames
 return result

def write_srt(words,target):
 def stamp(value):
  value=max(0,round(value*1000));return '%02d:%02d:%02d,%03d'%(value//3600000,value//60000%60,value//1000%60,value%1000)
 blocks=[]
 for group in groups(words):blocks.append(str(len(blocks)+1)+'\n'+stamp(group[0]['start'])+' --> '+stamp(group[-1]['end'])+'\n'+' '.join(w['text'] for w in group))
 if not blocks:raise ValueError('Nincs időzített szöveg a montázshoz.')
 Path(target).write_text('\n\n'.join(blocks),encoding='utf-8')

def shot_effect_filter(shot):
 # Cropping effects are deliberately withheld without a reliable tracked subject.
 if not shot.get('reframe'):return ''
 if shot.get('effect')=='punch-in':
  return "zoompan=z='1+0.09*min(min(on/6,1),max(0,(%.3f-on)/6))':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps=30,"%min(42,float(shot['duration'])*30)
 if shot.get('effect')=='spotlight':return 'vignette=PI/6,'
 return ''

def coalesce_continuous_shots(shots):
 """Adjacent transcript units are not new video cuts; keep their audio continuous."""
 result=[]
 for original in shots:
  shot=dict(original);previous=result[-1] if result else None
  continuous=previous and previous['source']==shot['source'] and abs(previous['start']+previous['duration']-shot['start'])<.001
  compatible=continuous and not previous.get('face_focus') and not shot.get('face_focus') and not previous.get('visual_source') and not shot.get('visual_source') and not shot.get('visual_cut') and previous.get('composition')==shot.get('composition') and previous.get('layout','cover')==shot.get('layout','cover') and all(x.get('effect','none')=='none' and x.get('sound','none')=='none' and not x.get('masks') and x.get('transition','cut')=='cut' for x in (previous,shot))
  if compatible and bool(previous.get('reframe'))==bool(shot.get('reframe')):
   offset=previous['duration']
   if shot.get('reframe'):previous['reframe']=list(previous['reframe'])+[dict(p,seconds=round(offset+p['seconds'],6)) for p in shot['reframe']]
   previous['duration']+=shot['duration']
  else:result.append(shot)
 return result

def frame_budgets(shots,fps=30):
 """Round cumulative boundaries, so many short cuts cannot accumulate AV drift."""
 cursor=0.;previous=0;result=[]
 for shot in shots:
  cursor+=shot['duration'];end=round(cursor*fps)
  if end<=previous:raise ValueError('A jelenet túl rövid egy teljes képkockához.')
  result.append(end-previous);previous=end
 return result

def render_montage(request,ffmpeg,tmp,geometry):
 shots=coalesce_continuous_shots(request['segments']);budgets=frame_budgets(shots)
 command=[ffmpeg,'-nostdin','-v','error'];filters=[];labels=[];input_index=0
 for i,shot in enumerate(shots):
  frames=budgets[i];seconds=frames/30;samples=frames*1600
  # Input -t leaves a small decode guard. Filters own the exact end frame/sample.
  narration_index=input_index;input_index+=1
  command+=['-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm','-ss',str(shot['start']),'-t',str(max(shot['duration'],seconds)+.1),'-i',shot['source']]
  visual_index=narration_index
  if shot.get('visual_source'):
   visual_index=input_index;input_index+=1
   command+=['-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm','-ss',str(shot['visual_start']),'-t',str(max(shot['duration'],seconds)+.1),'-i',shot['visual_source']]
  from video_intelligence import crop_filter
  from video_render import frame_geometry
  shot_geometry=crop_filter(shot['reframe']) if shot.get('reframe') else frame_geometry(shot.get('layout',request['layout']))
  effect=shot_effect_filter(dict(shot,duration=seconds))
  from editorial import validate_masks
  for mask in validate_masks(shot.get('masks',[])):
   effect+='drawbox=x=%d:y=%d:w=%d:h=%d:color=black:t=fill,'%(round(mask['x']*1080),round(mask['y']*1920),max(2,round(mask['w']*1080)),max(2,round(mask['h']*1920)))
  if shot.get('transition')=='fade':effect+="fade=t=in:st=0:d=0.08,fade=t=out:st=%.6f:d=0.08,"%max(0,seconds-.08)
  if shot.get('face_focus'):
   from reaction_framing import validate as validate_focus
   focus=validate_focus(shot['face_focus'],shot['duration']);x,y,w,h=focus['box']
   filters.append('[%d:v]setpts=PTS-STARTPTS,split=2[wideRaw%d][faceRaw%d]'%(visual_index,i,i))
   if shot.get('composition'):
    from smart_framing import filters as composition_filters
    filters.extend(composition_filters('[wideRaw%d]'%i,'[wide%d]'%i,shot['composition'],'focusstack%d'%i))
   else:filters.append('[wideRaw%d]%s,setsar=1[wide%d]'%(i,shot_geometry,i))
   filters.append('[faceRaw%d]crop=w=trunc(iw*%.6f/2)*2:h=trunc(ih*%.6f/2)*2:x=trunc(iw*%.6f/2)*2:y=trunc(ih*%.6f/2)*2,scale=1080:1920,setsar=1[face%d]'%(i,w,h,x,y,i))
   filters.append("[wide%d][face%d]overlay=0:0:enable='between(t,%.3f,%.3f)',fps=30,trim=end_frame=%d,%ssettb=AVTB,setpts=N/(30*TB)[v%d]"%(i,i,focus['start'],focus['end'],frames,effect,i))
  elif shot.get('composition'):
   from smart_framing import filters as composition_filters
   filters.append('[%d:v]setpts=PTS-STARTPTS[raw%d]'%(visual_index,i))
   filters.extend(composition_filters('[raw%d]'%i,'[composed%d]'%i,shot['composition'],'stack%d'%i))
   filters.append('[composed%d]fps=30,trim=end_frame=%d,%ssettb=AVTB,setpts=N/(30*TB)[v%d]'%(i,frames,effect,i))
  else:filters.append('[%d:v]setpts=PTS-STARTPTS,%s,setsar=1,fps=30,trim=end_frame=%d,%ssettb=AVTB,setpts=N/(30*TB)[v%d]'%(visual_index,shot_geometry,frames,effect,i))
  probe=subprocess.run([ffmpeg,'-hide_banner','-i',shot['source']],capture_output=True,text=True,timeout=20)
  if 'Audio:' in probe.stderr:
   audio='[%d:a]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,apad=whole_len=%d,atrim=end_sample=%d,asetpts=N/SR/TB'%(narration_index,samples,samples)
   # Only real discontinuities get a 6ms de-click, never a fade on every sentence.
   if i>0:audio+=',afade=t=in:st=0:d=0.006'
   if i<len(shots)-1:audio+=',afade=t=out:st=%.6f:d=0.006'%max(0,seconds-.006)
   filters.append(audio+'[a%d]'%i)
  else:filters.append('anullsrc=r=48000:cl=stereo,atrim=end_sample=%d,asetpts=N/SR/TB[a%d]'%(samples,i))
  if shot.get('sound') in SFX_NAMES:
   from sfx import filter_for,latest_start
   delay=min(max(0,shot.get('sound_delay',0)),latest_start(shot['sound'],seconds))
   filters.append(filter_for(shot['sound'],delay,'sfx%d'%i))
   filters.append('[a%d]asplit=2[voice%d][duck%d]'%(i,i,i))
   filters.append('[sfx%d][duck%d]sidechaincompress=threshold=0.025:ratio=8:attack=5:release=120[quiet%d]'%(i,i,i))
   filters.append('[voice%d][quiet%d]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[mix%d]'%(i,i,i))
   labels.append('[v%d][mix%d]'%(i,i))
  else:labels.append('[v%d][a%d]'%(i,i))
 filters.append(''.join(labels)+'concat=n=%d:v=1:a=1[base][sound]'%len(shots))
 if request.get('words'):
  write_word_captions(request['words'],tmp/'captions.ass',request.get('highlight_color','#35F2C5'),request.get('caption_preset'));filters.append('[base]ass=filename=captions.ass[out]')
 else:filters.append('[base]null[out]')
 command+=['-filter_complex',';'.join(filters),'-map','[out]','-map','[sound]','-t',str(sum(budgets)/30),'-r','30','-fps_mode','cfr','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart','-progress',request['progress'],'-n',request['output']]
 subprocess.run(command,cwd=tmp,check=True,timeout=1800,stdout=subprocess.DEVNULL)
 if request.get('words'):
  import shutil
  shutil.copyfile(tmp/'captions.ass',Path(request['output']).with_suffix('.ass'))
