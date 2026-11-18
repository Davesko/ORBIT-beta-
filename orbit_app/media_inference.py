"""Isolated Apple Silicon media inference. Called with fixed paths by ORBIT core."""
import json
import math
import os
import sys
from pathlib import Path


def finite_json(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {k:finite_json(v) for k,v in value.items()}
    if isinstance(value,list):return [finite_json(v) for v in value]
    return value

def valid_interval(value):
    return all(isinstance(value.get(k),(int,float)) and math.isfinite(value[k]) for k in ('start','end')) and 0<=value['start']<value['end']

def execute(request):
    import imageio_ffmpeg
    import subprocess
    import tempfile
    source = Path(request['source'])
    model_root = Path(request['models'])
    if request['operation'] in ('track_subject','analyze_video'):
        from video_intelligence import track_subject,analyze_video
        return (track_subject if request['operation']=='track_subject' else analyze_video)(request)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Whisper invokes `ffmpeg` by name; use only our bundled, fixed executable.
    with tempfile.TemporaryDirectory(prefix='orbit-media-') as temporary:
        tmp = Path(temporary)
        (tmp/'ffmpeg').symlink_to(ffmpeg)
        os.environ['PATH'] = str(tmp)+os.pathsep+os.environ.get('PATH','')
        if request['operation'] == 'transcribe_media':
            import wave
            audio=tmp/'source.wav'
            subprocess.run([ffmpeg,'-nostdin','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm,mp3,wav,aiff,flac,ogg','-i',str(source),'-vn','-ar','16000','-ac','1',str(audio)],check=True,timeout=300,capture_output=True)
            with wave.open(str(audio)) as wav:
                if wav.getnframes()==0:raise ValueError('A médiafájl nem tartalmaz olvasható hangot.')
                audio_seconds=wav.getnframes()/wav.getframerate()
            import mlx_whisper
            result = mlx_whisper.transcribe(str(audio), path_or_hf_repo=str(model_root/'whisper-large-v3-turbo'), language=None, word_timestamps=True, verbose=None, condition_on_previous_text=False)
            result=finite_json(result)
            from transcript_quality import assess
            assess(result)
            result['language_policy']=dict(requested=request.get('language','auto'),detected=result.get('language'),mode='detect_original_speech_never_force_operator_language')
            result['segments']=[s for s in result.get('segments',[]) if valid_interval(s)]
            for segment in result['segments']:segment['words']=[w for w in segment.get('words',[]) if valid_interval(w)]
            from audio_context import annotate,diarize
            try:turns,speaker_status=diarize(audio,model_root)
            except (ImportError,ValueError,RuntimeError):turns=[];speaker_status='unavailable'
            annotate(result,turns);result['audio_context']['speaker_status']=speaker_status
            from audio_context import loudness
            try:result['audio_context']['loudness']=loudness(audio)
            except (ImportError,ValueError,OSError):pass
            return {'coverage':dict(mode='full_audio',processed_audio_seconds=audio_seconds),'transcript_quality':result['transcript_quality'],'language_policy':result['language_policy'],'audio_context':result['audio_context'],'engine':'Whisper large-v3-turbo MLX','language':result.get('language'), 'text':result.get('text',''), 'segments':result.get('segments',[])}
        if request['operation'] != 'detect_faces':
            raise ValueError('Ismeretlen médiafeladat.')
        import cv2
        frames=[]
        if source.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
            image=cv2.imread(str(source));frames=[(0.0,image)]
        else:
            # Selected timestamps only; detections are observations, never identity/tracking.
            for i, timestamp in enumerate(request.get('timestamps',[0,5,10])):
                frame=tmp/(str(i)+'.png')
                subprocess.run([ffmpeg,'-nostdin','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm,mp3,wav,aiff,flac,ogg','-ss',str(timestamp),'-i',str(source),'-frames:v','1','-vf','scale=1920:1920:force_original_aspect_ratio=decrease',str(frame)],check=True,timeout=60,capture_output=True)
                frames.append((timestamp,cv2.imread(str(frame))))
        observations=[]
        for timestamp,image in frames:
            if image is None:raise ValueError('Nem olvasható képkocka ezen az időpontban: '+str(timestamp))
            h,w=image.shape[:2]
            if max(h,w)>1920:
                image=cv2.resize(image,(round(w*1920/max(h,w)),round(h*1920/max(h,w))));h,w=image.shape[:2]
            detector=cv2.FaceDetectorYN.create(str(model_root/'face_detection_yunet_2023mar.onnx'),'',(w,h),0.85,0.3,5000)
            _,faces=detector.detect(image)
            observations.append({'seconds':timestamp,'width':w,'height':h,'faces':[] if faces is None else [{'box':[float(v) for v in f[:4]],'landmarks':[[float(f[n]),float(f[n+1])] for n in range(4,14,2)],'confidence':float(f[14])} for f in faces]})
        return {'engine':'YuNet 2023mar / OpenCV','observations':observations,'note':'Arcdobozok a jelzett mintaképkockákon. Nem személyazonosítás vagy folyamatos arckövetés.'}

if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.read(20000))
        result=execute(request)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'message':str(exc)}));sys.exit(1)
