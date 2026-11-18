"""Project-scoped render preparation, progress and artifact registration."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid


def progress_percent(values, duration):
    """FFmpeg may report N/A before timestamps are available."""
    for key in ('out_time_us', 'out_time_ms'):
        try:
            elapsed = float(values.get(key, 'N/A')) / 1e6
            if math.isfinite(elapsed):
                return max(0, min(99, round(elapsed / duration * 100)))
        except (ValueError, TypeError):
            continue
    return None


def render_arguments(studio,pid,args,minimum_duration=1):
    source=studio.safe_path(pid,args.get('source_video') or args.get('name'))
    if not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.mkv','.webm'):raise ValueError('A bemeneti videó fájlútvonalát add meg (például inputs/media/abc.mp4), ne a videó címét. A project_files eszköz listázza a valódi fájlneveket.')
    def number(key,low,high):
        value=args.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Érvénytelen '+key+' érték.')
        return float(value)
    start=number('start',0,86400);duration=number('duration',minimum_duration,180)
    layout=args.get('layout','fit')
    if layout not in ('fit','cover'):raise ValueError('Ismeretlen képelrendezés.')
    subtitle=None
    if args.get('subtitle'):
        subtitle=studio.safe_path(pid,args['subtitle'])
        if not subtitle.is_file() or subtitle.suffix.lower()!='.srt' or subtitle.stat().st_size>1024*1024:raise ValueError('Legfeljebb 1 MB-os projektbeli SRT felirat szükséges.')
        content=subtitle.read_text(encoding='utf-8')
        if '-->' not in content:raise ValueError('Érvénytelen SRT-felirat.')
    return dict(source=str(source),start=start,duration=duration,layout=layout,subtitle=str(subtitle) if subtitle else None)


def shifted_subtitles(source,start,duration,dest):
    import re
    def parse(value):
        h,m,s,ms=map(int,re.split('[:,.]',value));return h*3600+m*60+s+ms/1000
    def stamp(value):
        value=round(value*1000);return '%02d:%02d:%02d,%03d'%(value//3600000,value//60000%60,value//1000%60,value%1000)
    blocks=[]
    for block in re.split(r'\n\s*\n',Path(source).read_text().strip()):
        lines=block.splitlines()
        match=next((re.fullmatch(r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})',line.strip()) for line in lines if '-->' in line),None)
        if not match:continue
        begin,end=map(parse,match.groups());begin=max(0,begin-start);end=min(duration,end-start)
        if end>begin:
            index=next(i for i,line in enumerate(lines) if line.strip()==match.string)
            text='\n'.join(lines[index+1:])
            # Strip ASS override tags from untrusted subtitle text.
            text=re.sub(r'\{[^}]*\}','',text)
            blocks.append(str(len(blocks)+1)+'\n'+stamp(begin)+' --> '+stamp(end)+'\n'+text)
    if not blocks:raise ValueError('A felirat nem fed át a kiválasztott videórészlettel.')
    dest.write_text('\n\n'.join(blocks));return dest


def run_render(studio,agent,args,job):
    if 'render_short' not in agent['tools']:raise ValueError('Az ügynökön nincs engedélyezve a videórender.')
    args=dict(args);args['name']=args.get('source_video') or args.get('name')
    request=render_arguments(studio,agent['project'],args)
    from short_style import get,caption_preset
    from short_style import validated,MIN_EDIT_UNIT_SECONDS,duration_allowed
    style=validated(get(studio,agent['project']),args.get('requirements',{}))
    request['caption_preset']=caption_preset(style)
    request['render_engine']=style.get('render_engine','auto')
    request['story']=args.get('story',{})
    if args.get('caption_theme'):
        from editorial import caption_theme
        request['caption_preset'].update(caption_theme(args['caption_theme']))
    if args.get('segments'):
        if not isinstance(args['segments'],list) or not 2<=len(args['segments'])<=32:raise ValueError('A montázshoz 2–32 vágás szükséges.')
        shots=[]
        for segment in args['segments']:
            part=render_arguments(studio,agent['project'],dict(segment,layout=segment.get('layout',args.get('layout','cover'))),minimum_duration=MIN_EDIT_UNIT_SECONDS)
            transcript=studio.safe_path(agent['project'],segment['transcript'])
            if not transcript.is_file() or transcript.suffix!='.json' or transcript.stat().st_size>4*1024*1024:raise ValueError('Hiányzó vagy túl nagy szóidőzítés.')
            if segment.get('visual_source_video'):
                visual=render_arguments(studio,agent['project'],dict(source_video=segment['visual_source_video'],start=segment.get('visual_start'),duration=part['duration'],layout='cover'),minimum_duration=MIN_EDIT_UNIT_SECONDS)
                part.update(visual_source=visual['source'],visual_start=visual['start'])
            if segment.get('composition'):
                from smart_framing import validate
                part['composition']=validate(segment['composition'])
            if segment.get('face_focus'):
                from reaction_framing import validate as validate_face_focus
                part['face_focus']=validate_face_focus(segment['face_focus'],part['duration'])
            part['visual_cut']=segment.get('visual_cut') is True
            part.update(beat=segment.get('beat','context'),edit_reason=segment.get('edit_reason','approved_story_beat'),evidence=segment.get('evidence',{}))
            if segment.get('reframe'):
                from video_intelligence import crop_filter
                crop_filter(segment['reframe']);part['reframe']=segment['reframe']
            effect=segment.get('effect','none')
            if effect not in ('none','punch-in','spotlight'):raise ValueError('Ismeretlen jeleneteffekt.')
            part['effect']=effect
            from editorial import validate_masks
            part['masks']=validate_masks(segment.get('masks',[]))
            from sfx import CHOICES as SOUND_CHOICES,seconds as sound_seconds
            for key,values in [('transition',('cut','fade','wipe')),('sound',SOUND_CHOICES)]:
                value=segment.get(key,values[0])
                if value not in values:raise ValueError('Ismeretlen vágási effekt.')
                part[key]=value
            delay=segment.get('sound_delay',0)
            room=max(0,part['duration']-(sound_seconds(part['sound']) or .18))
            if type(delay) not in (int,float) or not math.isfinite(delay) or delay<0:raise ValueError('Érvénytelen hangeffekt-időzítés.')
            part['sound_delay']=min(delay,room) if part['sound']!='none' else 0
            part['transcript']=str(transcript);shots.append(part)
        duration=sum(x['duration'] for x in shots)
        if not 10<=duration<=180:raise ValueError('A montázs hossza 10–180 másodperc legyen.')
        from montage import remap_words
        request.update(segments=shots,words=remap_words(shots),duration=duration,start=0,subtitle=None,highlight_color=request['caption_preset'].get('highlight',args.get('highlight_color','#35F2C5')))
        if not request['words']:raise ValueError('A szavankénti felirathoz hiányzik a Whisper szóidőzítése.')

    enforce_contract=bool(args.get('requirements')) or bool(studio.db.execute('SELECT 1 FROM short_styles WHERE project=?',(agent['project'],)).fetchone())
    if enforce_contract and not duration_allowed(request['duration'],style):
        raise ValueError('A kért renderhossz eltér a mentett '+str(style['min_seconds'])+'–'+str(style['max_seconds'])+' másodperces gyártási beállítástól. A rövidebb videót nem rendereljük kész eredményként.')
    runtime=studio.root/'media-runtime/bin/python'
    if not runtime.is_file():raise ValueError('A médiafuttató nincs telepítve.')
    name='renders/short-'+uuid.uuid4().hex[:12]+'.mp4'
    output=studio.safe_path(agent['project'],name);output.parent.mkdir(parents=True,exist_ok=True)
    progress=studio.root/'logs'/('render-'+job+'.progress');progress.parent.mkdir(exist_ok=True)
    request.update(output=str(output),progress=str(progress))
    subtitle=None
    if request.get('words'):
        from montage import write_srt
        subtitle=output.with_suffix('.srt');write_srt(request['words'],subtitle)
    elif request['subtitle']:
        subtitle=output.with_suffix('.srt');shifted_subtitles(request['subtitle'],request['start'],request['duration'],subtitle);request['subtitle']=str(subtitle)
    from edit_contract import compile_request
    request['edit_contract']=compile_request(request)
    if studio.cancelled(job):raise ValueError('A feladat leállítva.')
    studio.job_stage(job,'render','Videó renderelése · 0%',input_text=json.dumps(dict(args),ensure_ascii=False))
    log=progress.with_suffix('.log')
    try:
        with log.open('ab') as errors:
            process=subprocess.Popen([str(runtime),str(Path(__file__).with_name('video_render.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True)
            payload=json.dumps(request).encode();first=True;start=time.monotonic();last=-1
            try:
                while True:
                    try:raw,_=process.communicate(payload if first else None,timeout=1);break
                    except subprocess.TimeoutExpired:
                        first=False
                        if studio.cancelled(job):raise ValueError('A render leállítva.')
                        if time.monotonic()-start>1800:raise ValueError('A render túllépte a 30 perces időkeretet.')
                        if progress.exists():
                            values=dict(line.split('=',1) for line in progress.read_text().splitlines() if '=' in line)
                            percent=progress_percent(values,request['duration'])
                            phase=progress.with_suffix(progress.suffix+'.phase')
                            phase_name=phase.read_text() if phase.is_file() else ''
                            if percent is not None and phase_name=='base':percent=round(percent*.65)
                            if percent is not None and phase_name=='fallback':percent=65+round(percent*.3)
                            if percent is not None and percent>last:studio.job_stage(job,'render',('Animált feliratok' if phase_name=='graphics' else 'Feliratozás · tartalék render' if phase_name=='fallback' else 'Videó renderelése')+' · '+str(percent)+'%');last=percent
            except BaseException:
                os.killpg(process.pid,signal.SIGKILL);process.communicate();raise
        response=json.loads(raw)
        if process.returncode or not response.get('ok'):raise ValueError(response.get('message','Renderhiba.'))
        if studio.cancelled(job):raise ValueError('A render leállítva.')
        if enforce_contract:
            from short_style import validate_output
            validate_output(response['result'],style)
        manifest=output.with_suffix('.json');manifest.write_text(json.dumps(dict(response['result'],source=args['name'],start=request['start'],requested_duration=request['duration'],segments=args.get('segments',[])),ensure_ascii=False,indent=2))
        timeline=output.with_suffix('.timeline.json');timeline.write_text(json.dumps(request['edit_contract'],ensure_ascii=False,indent=2))
        paths=[(output,'video'),(manifest,'text'),(timeline,'text')]+([(subtitle,'text')] if subtitle else [])
        if output.with_suffix('.ass').is_file():paths.append((output.with_suffix('.ass'),'text'))
        for path,kind in paths:studio.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,agent['project'],path.name,str(path),kind,time.time(),job))
        studio.db.commit()
        return {'saved':name,'files':[str(p.relative_to(studio.root/'projects'/agent['project'])) for p,_ in paths],'metadata':response['result']}
    except BaseException:
        # Partial private outputs are never exposed in the gallery as completed media.
        output.unlink(missing_ok=True);output.with_suffix('.jpg').unlink(missing_ok=True);output.with_suffix('.ass').unlink(missing_ok=True)
        if subtitle:subtitle.unlink(missing_ok=True)
        raise
