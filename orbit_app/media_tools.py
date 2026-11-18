"""Bounded project media tools; no model-supplied shell commands or network inputs."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

MEDIA_EXTENSIONS={'.mp4':'video','.mov':'video','.mkv':'video','.webm':'video','.mp3':'audio','.wav':'audio','.m4a':'audio','.aiff':'audio','.flac':'audio','.ogg':'audio','.aif':'audio','.aac':'audio','.opus':'audio','.png':'image','.jpg':'image','.jpeg':'image','.webp':'image'}
MEDIA_TOOLS={'transcribe_media','detect_faces','track_subject','analyze_video'}


def media_models(root):
    root=Path(root);models=root/'models'
    runtime=(root/'media-runtime/bin/python').is_file()
    entries=[dict(name='Whisper large-v3-turbo MLX',purpose='Angol átirat és szóidőzítés · Echo',ready=runtime and (models/'whisper-large-v3-turbo/weights.safetensors').is_file() and (models/'whisper-large-v3-turbo/config.json').is_file(),size=sum(p.stat().st_size for p in (models/'whisper-large-v3-turbo').glob('*') if p.is_file())),dict(name='YuNet',purpose='Arcdobozok képeken és videómintákon · Pixel',ready=runtime and (models/'face_detection_yunet_2023mar.onnx').is_file(),size=(models/'face_detection_yunet_2023mar.onnx').stat().st_size if (models/'face_detection_yunet_2023mar.onnx').is_file() else 0)]

    entries.append(dict(name='YOLOX-S + ByteTrack',purpose='Helyi szereplőkövetés és mozgó képkivágás · Pixel',ready=runtime and (models/'object_detection_yolox_2022nov.onnx').is_file(),size=(models/'object_detection_yolox_2022nov.onnx').stat().st_size if (models/'object_detection_yolox_2022nov.onnx').is_file() else 0))
    entries.append(dict(name='Sherpa-ONNX · beszélőváltások',purpose='Névtelen hangcsoportok és beszélőváltások · Echo',ready=runtime and (models/'speaker-segmentation.onnx').is_file() and (models/'speaker-embedding.onnx').is_file(),size=sum((models/n).stat().st_size for n in ('speaker-segmentation.onnx','speaker-embedding.onnx') if (models/n).is_file())))
    from narration import model_path
    from model_hub import answers
    kokoro=model_path(root);entry=dict(name='Kokoro v1 · helyi narráció',purpose='Angol narráció · 28 hang · API nélkül',ready=False,size=0)
    # Kokoro lives on the model SSD; a hung disk must not take the app's main data request down with it.
    if str(kokoro).startswith('/Volumes/') and not answers(kokoro.parent.parent,root):entry['purpose']+=' · az SSD nem válaszol'
    else:
        try:entry.update(ready=runtime and (kokoro/'model.onnx').is_file() and (kokoro/'voices.bin').is_file(),size=sum(p.stat().st_size for p in kokoro.glob('*') if p.is_file()))
        except OSError:entry['purpose']+=' · nem olvasható'
    entries.append(entry)
    return entries


def import_media(studio,pid,source):
    import shutil
    source=Path(source).resolve(strict=True)
    extension=source.suffix.lower()
    if extension not in MEDIA_EXTENSIONS or not source.is_file():raise ValueError('Támogatott helyi videót, hangot vagy képet válassz.')
    if source.stat().st_size>8*1024**3:raise ValueError('Egy médiafájl legfeljebb 2 GB lehet. Hosszú streamből előbb rövidebb részletet válassz.')
    name='inputs/media/'+uuid.uuid4().hex[:10]+extension
    dest=studio.safe_path(pid,name);dest.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as src,dest.open('xb') as target:shutil.copyfileobj(src,target,1024*1024)
    studio.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,source.name,str(dest),MEDIA_EXTENSIONS[extension],time.time(),'import'));studio.db.commit()
    return name


def run_media_tool(studio,agent,operation,args,job):
    from inference_gate import lease
    with lease(studio.root):return _run_media_tool(studio,agent,operation,args,job)

def _run_media_tool(studio,agent,operation,args,job):
    if operation not in MEDIA_TOOLS or operation not in agent['tools']:raise ValueError('Nincs engedélyezve ez a médiaeszköz.')
    source=studio.safe_path(agent['project'],args.get('name'))
    if not source.is_file() or source.suffix.lower() not in MEDIA_EXTENSIONS:raise ValueError('A projektbe importált médiafájl neve szükséges.')
    if source.stat().st_size>8*1024**3:raise ValueError('Legfeljebb 8 GB-os média dolgozható fel; a bemenetet nem csonkítjuk.')
    if operation=='transcribe_media' and MEDIA_EXTENSIONS[source.suffix.lower()]=='image':raise ValueError('Átirathoz hang vagy videó szükséges.')
    language=args.get('language','auto')
    if language not in ('auto','en','hu'):raise ValueError('Átirat nyelve: auto, en vagy hu.')
    timestamps=args.get('timestamps',[0,5,10])
    if not isinstance(timestamps,list) or not 1<=len(timestamps)<=12 or any(isinstance(t,bool) or not isinstance(t,(int,float)) or not 0<=t<=86400 for t in timestamps):raise ValueError('1–12 időpont szükséges, másodpercben (0–86400).')
    if operation in ('track_subject','analyze_video') and MEDIA_EXTENSIONS[source.suffix.lower()]!='video':raise ValueError('Ehhez helyi videófájl szükséges.')
    vision={}
    analysis_mode=args.get('analysis_mode','focus')
    if analysis_mode not in ('overview','focus'):raise ValueError('Ismeretlen képi elemzési mód.')
    if operation=='analyze_video':
        from model_hub import models,release_other
        from video_intelligence import select_vision_model
        model=select_vision_model(models())
        vision=dict(vision_model=model['name'],vision_port=model['port']);release_other(model['port'])
    runtime=studio.root/'media-runtime/bin/python'
    if not runtime.is_file():raise ValueError('A helyi médiafuttató nincs telepítve.')
    if studio.cancelled(job):raise ValueError('A feladat leállítva.')
    env=dict(os.environ,HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OPENCV_IO_MAX_IMAGE_PIXELS='40000000')
    # Logs stay on disk; stdout is bounded by the fixed local adapter's JSON output.
    studio.job_stage(job,'media',{'transcribe_media':'Whisper · beszéd átírása','detect_faces':'YuNet · arcdobozok keresése','track_subject':'YOLOX + ByteTrack · szereplőkövetés','analyze_video':'Jelenetfelismerés + helyi képi modell'}[operation],input_text=json.dumps(args,ensure_ascii=False))
    log=studio.root/'logs'/('media-'+job+'.log');log.parent.mkdir(exist_ok=True)
    with log.open('ab') as errors:
        process=subprocess.Popen([str(runtime),str(Path(__file__).with_name('media_inference.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,env=env,start_new_session=True)
        request=json.dumps(dict(operation=operation,source=str(source),models=str(studio.root/'models'),timestamps=timestamps,language=language,analysis_mode=analysis_mode,**vision)).encode()
        start=time.monotonic();first=True
        try:
            while True:
                try:
                    output,_=process.communicate(request if first else None,timeout=1);break
                except subprocess.TimeoutExpired:
                    first=False
                    if studio.cancelled(job):raise ValueError('A feladat leállítva.')
                    if time.monotonic()-start>1800:raise ValueError('A médiafeldolgozás túllépte a 30 perces időkeretet.')
        except BaseException:
            import signal
            os.killpg(process.pid,signal.SIGKILL);process.communicate();raise
    if len(output)>20*1024**2:raise ValueError('Túl nagy átirat. Rövidebb részlettel próbáld.')
    try:response=json.loads(output)
    except ValueError:raise ValueError('A médiafuttató nem adott érvényes választ. Részletek a helyi naplóban.')
    if not response.get('ok') or process.returncode:raise ValueError(response.get('message','Helyi feldolgozási hiba.'))
    if studio.cancelled(job):raise ValueError('A feladat leállítva.')
    result=response['result'];result['source']=str(source.relative_to(studio.root/'projects'/agent['project']))
    prefix='results/'+operation+'-'+uuid.uuid4().hex[:12]
    outputs=[(prefix+'.json',json.dumps(result,ensure_ascii=False,indent=2))]
    if operation=='transcribe_media':
        def stamp(seconds):
            ms=max(0,round(float(seconds)*1000));return '%02d:%02d:%02d,%03d'%(ms//3600000,ms//60000%60,ms//1000%60,ms%1000)
        segments=result.get('segments',[])
        outputs.append((prefix+'.srt','\n\n'.join(str(i+1)+'\n'+stamp(s['start'])+' --> '+stamp(s['end'])+'\n'+s['text'].strip() for i,s in enumerate(segments))))
    for name,content in outputs:
        target=studio.safe_path(agent['project'],name);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('x') as handle:handle.write(content)
        studio.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,agent['project'],Path(name).name,str(target),'text',time.time(),job))
    studio.db.commit()
    summary=result.get('text','')[:10000] if operation=='transcribe_media' else result
    if operation=='track_subject':summary={k:result[k] for k in ('engine','duration','samples','tracks','note')}
    return dict(files=[name for name,_ in outputs],summary=summary)
