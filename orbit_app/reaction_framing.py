"""Short face emphasis grounded in local detections; never equate a person with a voice."""
import math,re

def detect(frames,models):
    import cv2
    model=models/'face_detection_yunet_2023mar.onnx'
    if not model.is_file():return {}
    result={}
    for seconds,image in frames:
        h,w=image.shape[:2]
        detector=cv2.FaceDetectorYN.create(str(model),'',(w,h),.8,.3,1000)
        _,faces=detector.detect(image)
        result[seconds]=[] if faces is None else [dict(box=[float(f[0])/w,float(f[1])/h,float(f[2])/w,float(f[3])/h],confidence=float(f[14])) for f in faces if f[14]>=.8]
    return result

def validate(value,duration):
    if not isinstance(value,dict):raise ValueError('Invalid face focus')
    box=value.get('box',[]);a=value.get('start');b=value.get('end')
    if len(box)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) for x in box+[a,b]):raise ValueError('Invalid face focus coordinates')
    x,y,w,h=box
    if not (0<=x<1 and 0<=y<1 and .02<w<=1 and .02<h<=1 and x+w<=1.001 and y+h<=1.001 and 0<=a<b<=duration+.001 and b-a<=1.6):raise ValueError('Face focus exceeds source or time limits')
    return dict(box=box,start=a,end=b,reason=str(value.get('reason',''))[:240])

def focus(shot,observation,coverage):
    if shot.get('preserve_pause') or shot.get('cutaway') or shot['end']-shot['start']<.65:return None
    frames=[f for f in observation.get('frames',[]) if shot['start']<=f.get('seconds',-1)<=shot['end']]
    anchors=[f['faces'][0]['box'] for f in frames if len(f.get('faces',[]))==1]
    anchor=anchors[0] if anchors else None
    selected=[]
    for frame in frames:
        faces=sorted(frame.get('faces',[]),key=lambda f:f['box'][2]*f['box'][3],reverse=True)
        if not faces:continue
        regions=[r['box'] for r in frame.get('regions',[]) if r.get('kind')=='speaker' and r.get('confidence',0)>=.85]
        insets=[f for f in faces if any(x<=f['box'][0]+f['box'][2]/2<=x+w and y<=f['box'][1]+f['box'][3]/2<=y+h for x,y,w,h in regions)]
        nearby=[] if anchor is None else [f for f in faces if abs(f['box'][0]+f['box'][2]/2-anchor[0]-anchor[2]/2)<.15 and abs(f['box'][1]+f['box'][3]/2-anchor[1]-anchor[3]/2)<.15]
        if len(insets)==1:chosen=insets[0]
        elif len(nearby)==1:chosen=nearby[0]
        elif len(faces)==1:chosen=faces[0]
        elif faces[0]['box'][2]*faces[0]['box'][3]>=1.8*faces[1]['box'][2]*faces[1]['box'][3]:chosen=faces[0]
        else:continue
        selected.append((frame,chosen['box']))
    if len(selected)<2:return None
    first=selected[0][1]
    if any(abs((b[0]+b[2]/2)-(first[0]+first[2]/2))>.12 or abs((b[1]+b[3]/2)-(first[1]+first[3]/2))>.12 for _,b in selected[1:]):return None
    reaction=any(re.search(r'\b(laugh\w*|surpris\w*|shout\w*|gasps?|open mouth|react\w*)\b',f.get('action',''),re.I) for f,_ in selected)
    if not (reaction or shot.get('zoom_justified')):return None
    # Close-ups punctuate hooks/reactions or short spoken beats, not every long sentence.
    if not reaction and not shot.get('zoom_justified') and shot.get('beat') not in ('hook','payoff','reaction') and shot['end']-shot['start']>4:return None
    box=[sum(b[i] for _,b in selected)/len(selected) for i in range(4)];x,y,w,h=box
    aspect=observation.get('aspect_ratio',16/9)
    ch=min(1,max(h*3,w*aspect*16/9,.28));cw=min(1,ch/aspect*9/16)
    cx=x+w/2;cy=y+h*.7
    crop=[max(0,min(1-cw,cx-cw/2)),max(0,min(1-ch,cy-ch*.38)),cw,ch]
    duration=shot['end']-shot['start'];a=max(0,min(duration-.65,selected[0][0]['seconds']-shot['start']))
    return validate(dict(box=crop,start=round(a,3),end=round(min(duration,a+1.4),3),reason='Visible reaction emphasis' if reaction else 'Brief focus on a stable prominent face during speech; voice identity not inferred'),duration)

def apply(shots,tracks,observations,plans):
    elapsed=0;last=-10;used=0;total=sum(s['end']-s['start'] for s in shots)
    from editorial import speech_coverage
    for shot,plan in zip(shots,plans):
        obs=observations[shot['source']] if shot['source']<len(observations) else {}
        candidate=focus(shot,obs,speech_coverage(tracks[shot['source']]['transcript'],shot['start'],shot['end']))
        budget=.18 if plan.get('content_type')=='gameplay' else .28
        if candidate and elapsed-last>=4 and used+candidate['end']-candidate['start']<=max(1.4,total*budget):
            plan['face_focus']=candidate;plan['effect']='none';plan['zoom_justified']=True
            used+=candidate['end']-candidate['start'];last=elapsed
        elapsed+=shot['end']-shot['start']
