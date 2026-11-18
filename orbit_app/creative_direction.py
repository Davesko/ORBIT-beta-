"""Compile reviewer decisions into bounded visual events, never executable model code."""
POLICY = '''Creative execution v2: First read the complete-source overview and ranked
omissions. Preserve essential setup, context and outcome. The semantic editor owns
story IDs and beat purpose; the camera agent owns observed visual regions; the
renderer owns exact frames. Choose clean for explanation/news, gaming for gameplay,
energetic for evidenced action, story for restrained narrative/deadpan. Use one
coherent style per video. A face is not proof of a speaker. Preserve the game or
screen while emphasizing a reaction briefly. Never add zoom for speech alone.
Sound accents (pop, whoosh, boom, riser, ding, scratch, rewind, glitch, shutter) mark an evidenced reveal, punchline, twist or scene change; preserve_pause
prohibits added accents. Use transition wipe only at a genuine context/scene change, otherwise cut. Transitions must not delete speech or change the duration.
Typography emphasizes real words only; no invented hook text. Every effect retains
its source unit, reason, frame range and target. Missing visual evidence means a
context-preserving layout, not a fabricated subject. Silence and hard cuts are valid.'''


def events(timeline):
    result=[]
    for shot in timeline:
        start,end=shot['start_frame'],shot['end_frame']
        evidence=shot.get('evidence') or {}
        reason=evidence.get('reason') or shot.get('cut_reason') or 'Approved editorial beat'
        def add(kind,a,b,target,parameters):
            a=max(start,int(a));b=min(end,int(b))
            if b>a:result.append(dict(type=kind,start_frame=a,end_frame=b,target=target,
                parameters=parameters,reason=reason,source_unit=evidence.get('unit_id'),shot=shot['id']))
        if shot.get('composition'):add('layout',start,end,'observed_regions',shot['composition'])
        focus=shot.get('face_focus')
        if focus:add('face_focus',start+round(focus['start']*30),start+round(focus['end']*30),'observed_face',focus)
        elif shot.get('zoom')=='punch-in':add('punch_in',start,min(end,start+42),'tracked_crop',dict(max_scale=1.09,attack_frames=6,release_frames=6))
        if shot.get('transition')=='wipe':add('wipe',start,start+8,'boundary',dict(color='#111827'))
        if shot.get('sound') in __import__('sfx').NAMES:
            a=start+round(shot.get('sound_delay',0)*30)
            add('sound',a,a+max(3,round(__import__('sfx').seconds(shot['sound'])*30)),'audio',dict(preset=shot['sound'],duck_under_speech=True))
    return result
