"""Compile evidenced editorial choices into a finite, frame-based renderer contract.

Models choose catalog IDs in editorial_schemas; they never author executable code,
paths, invented word times or renderer expressions. This is the deterministic IR.
"""
import math
from montage import frame_budgets, groups, clean
from creative_direction import events

VERSION = 'orbit.edit.v1'
POLICY = '''Editing execution contract (v1): Use one grounded story, with an immediately
understandable hook, necessary context, development and a real payoff. Compare up to
three real opening candidates. Do not invent an outcome or splice a false exchange.
Aim for interest within the first three seconds, not a mandatory three-second cut.
Pacing follows sentence ends, speaker turns and visible events. A 1.5–2.5 second
change is an experiment, never a rule that overrides meaning or deadpan timing.
Avoid continuous zoom. Gameplay and demonstrations must remain understandable.
Use accents only for evidenced reactions/reveals; silence is valid. Preserve original
speech unless narration was explicitly requested. A natural loop is optional; never
truncate the payoff or manufacture connecting dialogue to force a loop. Captions
use real word timing, short groups and the saved safe area. Stock or AI imagery is
illustration, never evidence of a real event. Renderer failures retry only the failed
render step. Do not promise virality or infer algorithmic causality from raw views.'''


def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Érvénytelen idővonalérték: '+label)
    return value


def caption_pages(words, preset, duration, fps=30):
    """Shared line grouping for ASS and Remotion; times refer to the final output."""
    previous=-1
    for word in words:
        a=finite(word.get('start'), 'word.start');b=finite(word.get('end'), 'word.end')
        if a<0 or b<=a or b>duration+.05 or a<previous-.001:
            raise ValueError('A szóidőzítés kilóg a vágási tervből vagy rendezetlen.')
        previous=a
    box=preset['box'];pages=[]
    for group in groups(words,preset.get('font_size',76),preset.get('font','Arial'),
                        max_width=min(680,(box[2]-box[0]-24)/1.08)):
        items=[]
        for i,word in enumerate(group):
            a=round(word['start']*fps)
            b=round((group[i+1]['start'] if i+1<len(group) else word['end'])*fps)
            items.append(dict(text=clean(word.get('text',word.get('word',''))),
                              start_frame=a,end_frame=max(a+1,min(round(duration*fps),b))))
        pages.append(dict(start_frame=items[0]['start_frame'],end_frame=items[-1]['end_frame'],words=items))
    return pages


def compile_request(request):
    """Validated final contract used by BOTH local renderers and saved beside MP4."""
    shots=request.get('segments',[])
    budgets=frame_budgets(shots) if shots else [round(finite(request['duration'],'duration')*30)]
    total=sum(budgets)
    if total<=0 or abs(total/30-request['duration'])>.05:raise ValueError('Eltérő idővonalhossz.')
    cursor=0;timeline=[]
    for i,(shot,frames) in enumerate(zip(shots,budgets)):
        start=finite(shot['start'],'source.start');duration=finite(shot['duration'],'source.duration')
        if start<0 or duration<=0:raise ValueError('Érvénytelen forrástartomány.')
        timeline.append(dict(id='shot_'+str(i),start_frame=cursor,end_frame=cursor+frames,
            source_in_seconds=start,source_out_seconds=start+duration,
            evidence=shot.get('evidence',{}),role=shot.get('beat','context'),
            cut_reason=shot.get('edit_reason','approved_story_beat'),
            layout=shot.get('layout',request['layout']),composition=shot.get('composition'),
            zoom=shot.get('effect','none'),face_focus=shot.get('face_focus'),sound=shot.get('sound','none'),sound_delay=shot.get('sound_delay',0),transition=shot.get('transition','cut'),
            broll=dict(source=shot.get('visual_source'),start=shot.get('visual_start'),
                       kind='verified_illustration' if shot.get('visual_source') else 'none')))
        cursor+=frames
    preset=dict(request.get('caption_preset') or {})
    if request.get('words'):
        box=preset.get('box',[]);anchor=preset.get('anchor',[])
        if len(box)!=4 or len(anchor)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in box+anchor):raise ValueError('Érvénytelen feliratterület.')
        if not (0<=box[0]<box[2]<=1080 and 0<=box[1]<box[3]<=1920 and box[0]<=anchor[0]<=box[2] and box[1]<=anchor[1]<=box[3]):raise ValueError('A felirat nincs biztonságos területen.')
    return dict(schema_version=VERSION,output=dict(width=1080,height=1920,fps=30,duration_frames=total),
        story=request.get('story',{}),timeline=timeline,effects=events(timeline),
        captions=dict(preset=preset,pages=caption_pages(request.get('words',[]),preset,total/30) if request.get('words') else []),
        policy=dict(loop='natural_only',pacing='semantic_boundaries',source_audio='preserve',
                    arbitrary_zoom=False,viral_guarantee=False))
