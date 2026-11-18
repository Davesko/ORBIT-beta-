"""Fixed local 9:16 MP4 renderer. Arguments are validated by the project tool."""
import json
from pathlib import Path
import subprocess
import tempfile
import shutil


CAPTION_PRESET = dict(name='social-safe-v1', box=[108, 880, 864, 1220],
                      anchor=[486, 1200], font_size=72, max_lines=2,
                      animation='fade-scale-in')


def write_ass(source, target, preset=None):
    preset=preset or CAPTION_PRESET
    import html
    import re
    from PIL import ImageFont
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 60)
    # Conservative shared layout: reserve the bottom controls and right action rail.
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,108,216,720,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def stamp(seconds):
        cs = round(seconds * 100)
        return '%d:%02d:%02d.%02d' % (cs//360000, cs//6000%60, cs//100%60, cs%100)
    def seconds(v):
        return v[0]*3600+v[1]*60+v[2]+v[3]/1000
    events = []
    for block in re.split(r'\n\s*\n', source.read_text(encoding='utf-8-sig').strip()):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            match = re.fullmatch(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', line.strip())
            if not match:
                continue
            values = list(map(int, match.groups()))
            begin, end = seconds(values[:4]), seconds(values[4:])
            if end <= begin:
                break
            text = html.unescape(re.sub(r'<[^>]*>|\{[^}]*\}', '', ' '.join(lines[i+1:])))
            text = text.replace('\\', ' ').replace('{', '').replace('}', '')
            text = ''.join(c for c in text if c.isprintable())
            # Measure actual glyphs, including single long words; leave outline padding.
            wrapped, current = [], ''
            for word in text.split():
                pieces, piece = [], ''
                for char in word:
                    if piece and font.getlength(piece+char) > 716:
                        pieces.append(piece); piece = ''
                    piece += char
                pieces.append(piece)
                for piece in pieces:
                    candidate = (current+' '+piece).strip()
                    if current and font.getlength(candidate) > 716:
                        wrapped.append(current); current = piece
                    else:
                        current = candidate
            if current:
                wrapped.append(current)
            groups = [wrapped[n:n+2] for n in range(0, len(wrapped), 2)]
            weight = sum(len(' '.join(group)) for group in groups)
            cursor = begin
            for n, group in enumerate(groups):
                finish = end if n == len(groups)-1 else cursor+(end-begin)*len(' '.join(group))/weight
                if round(finish*100) <= round(cursor*100):
                    continue
                ms = (finish-cursor)*1000
                fade, transition = min(90, int(ms/4)), min(130, int(ms/3))
                tags = ((r'{\an2\pos(%d,%d)\clip(%d,%d,%d,%d)\q2'%tuple(preset['anchor']+preset['box']))
                        + r'\fad(%d,%d)\fscx96\fscy96\t(0,%d,\fscx100\fscy100)}'
                        % (fade, min(70, int(ms/4)), transition))
                events.append('Dialogue: 0,'+stamp(cursor)+','+stamp(finish)+',Default,,0,0,0,,'+tags+r'\N'.join(group))
                cursor = finish
            break
    if not events:
        raise ValueError('Nincs megjeleníthető felirat.')
    target.write_text(header+'\n'.join(events), encoding='utf-8')


def frame_geometry(layout):
    if layout=='cover':return 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
    return 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x10191d'


def render(request):
    import imageio_ffmpeg
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    output=Path(request['output'])
    from edit_contract import compile_request
    contract=compile_request(request)
    engine='ffmpeg';engine_note=None
    with tempfile.TemporaryDirectory(prefix='orbit-render-') as directory:
        tmp=Path(directory)
        # Fit preserves gameplay/UI; cover intentionally crops edges.
        geometry=frame_geometry(request['layout'])
        filters=geometry+',setsar=1'
        if request.get('segments'):
            from montage import render_montage
            from remotion_runtime import ready,finish
            use_motion=request.get('render_engine','auto')!='ffmpeg' and bool(request.get('words')) and ready()
            if request.get('render_engine')=='remotion' and not use_motion:
                engine_note='Remotion unavailable; deterministic ASS captions used.'
            if use_motion:
                base=tmp/'base.mp4'
                phase=Path(request['progress']+'.phase');phase.write_text('base')
                render_montage(dict(request,output=str(base),words=[]),ffmpeg,tmp,geometry)
                try:
                    Path(request['progress']).write_text('out_time_us='+str(round(request['duration']*.65*1e6))+'\n')
                    phase.write_text('graphics')
                    finish(base,output,contract,request['progress'],ffmpeg,tmp)
                    engine='ffmpeg+remotion'
                except (OSError,RuntimeError,subprocess.SubprocessError) as exc:
                    # Retry only the graphics pass, never source acquisition or LLM planning.
                    output.unlink(missing_ok=True)
                    phase.write_text('fallback')
                    from montage import write_word_captions
                    write_word_captions(request['words'],tmp/'captions.ass',request.get('highlight_color','#BFA3FF'),request.get('caption_preset'))
                    subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(base),'-vf','ass=filename=captions.ass','-c:v','libx264','-crf','18','-preset','fast','-c:a','copy','-movflags','+faststart','-progress',request['progress'],'-n',str(output)],cwd=tmp,check=True,timeout=1200,stdout=subprocess.DEVNULL)
                    shutil.copyfile(tmp/'captions.ass',output.with_suffix('.ass'))
                    engine_note='Remotion graphics pass failed; ASS fallback: '+type(exc).__name__
            else:render_montage(request,ffmpeg,tmp,geometry)
        if request.get('subtitle') and not request.get('segments'):
            # Canonical generated filename avoids filter/path injection. Only SubRip accepted.
            shutil.copyfile(request['subtitle'],tmp/'captions.srt')
            write_ass(tmp/'captions.srt',tmp/'captions.ass',request.get('caption_preset'))
            filters+=',ass=filename=captions.ass'
        command=[ffmpeg,'-nostdin','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm','-ss',str(request['start']),'-i',request['source'],'-t',str(request['duration']),'-map','0:v:0','-map','0:a:0?','-vf',filters,'-r','30','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart','-progress',request['progress'],'-n',str(output)]
        if not request.get('segments'):subprocess.run(command,cwd=tmp,check=True,timeout=1800,stdout=subprocess.DEVNULL)
        # Validate the resulting media, not just the existence of a filename.
        import cv2
        video=cv2.VideoCapture(str(output));frames=video.get(cv2.CAP_PROP_FRAME_COUNT);fps=video.get(cv2.CAP_PROP_FPS)
        width=round(video.get(cv2.CAP_PROP_FRAME_WIDTH));height=round(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        video.set(cv2.CAP_PROP_POS_MSEC,500);ok,frame=video.read();video.release()
        if not ok:raise ValueError('A renderkimenet képkockája nem olvasható.')
        cv2.imwrite(str(output.with_suffix('.jpg')),cv2.resize(frame,(270,480)),[cv2.IMWRITE_JPEG_QUALITY,85])
        actual=frames/fps if fps else 0
        if abs(fps-30)>.01:raise ValueError('A kimenet nem egyenletes, 30 fps-es videó; nem jelöljük késznek.')
        if (width,height)!=(1080,1920) or actual<0.5:raise ValueError('A renderkimenet nem érvényes 1080×1920 videó.')
        if actual+0.2<request['duration']:raise ValueError('A forrás rövidebb a kiválasztott klipnél. Rövidebb tartományt adj meg.')
        from render_quality import verify_export
        quality=verify_export(ffmpeg,output,actual)
        return dict(render_engine=engine,render_fallback=engine_note,quality=quality,edit_contract=contract['schema_version'],frame_timing='cfr-30',decoded_frames=round(frames),extra_zoom_shots=sum(x.get('effect')=='punch-in' or bool(x.get('face_focus')) for x in request.get('segments',[])),tracked_shots=sum(bool(x.get('reframe')) for x in request.get('segments',[])),width=width,height=height,duration=actual,fps=fps,bytes=output.stat().st_size,layout=request['layout'],captions=bool(request.get('subtitle') or request.get('words')),caption_style=(request.get('caption_preset') or (__import__('montage').WORD_PRESET if request.get('words') else CAPTION_PRESET if request.get('subtitle') else None)),shot_count=len(request.get('segments',[])) or 1,word_events=len(request.get('words',[])))

if __name__=='__main__':
    import sys
    try:print(json.dumps({'ok':True,'result':render(json.loads(sys.stdin.read(2*1024*1024)))}))
    except Exception as exc:print(json.dumps({'ok':False,'message':str(exc)}));sys.exit(1)
