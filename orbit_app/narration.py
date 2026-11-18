"""Explicit local narration tool; never silently replaces a source speaker."""
import json,subprocess,time,uuid
from pathlib import Path


def model_path(root):
    try:config=json.loads((Path(root)/'model-storage.json').read_text())
    except (OSError,ValueError):config={}
    return Path(config['base'])/'audio/kokoro-multi-lang-v1_0' if config.get('base') else Path(root)/'models/kokoro-multi-lang-v1_0'


def validate(args):
    text=args.get('text');voice=args.get('voice',3);speed=args.get('speed',1.)
    if not isinstance(text,str) or not 1<=len(text.strip())<=1800:raise ValueError('A helyi narrációhoz 1–1800 karakteres angol szöveget adj meg.')
    if type(voice) is not int or not 0<=voice<=27:raise ValueError('Érvénytelen angol hangazonosító (0–27).')
    if type(speed) not in (int,float) or not .8<=speed<=1.2:raise ValueError('A beszédtempó 0,8–1,2 lehet.')
    return dict(text=text.strip(),voice=voice,speed=speed)


def synthesize(s,agent,args,job):
    payload=validate(args);model=model_path(s.root)
    if not (model/'model.onnx').is_file():raise ValueError('A Kokoro hangmodell nem érhető el. Ellenőrizd az SSD-t és a Modellek oldalt.')
    name='renders/narration-'+uuid.uuid4().hex[:12]+'.wav';output=s.safe_path(agent['project'],name);output.parent.mkdir(parents=True,exist_ok=True)
    payload.update(model=str(model),output=str(output))
    s.job_stage(job,'narration','Helyi angol narráció készítése')
    from inference_gate import lease
    with lease(s.root):
        result=subprocess.run([str(s.root/'media-runtime/bin/python'),str(Path(__file__).resolve()),'synthesize'],input=json.dumps(payload),capture_output=True,text=True,timeout=180)
    if result.returncode or not output.is_file():
        output.unlink(missing_ok=True);raise ValueError('A helyi narráció nem készült el; a videó eredeti hangját nem módosítottuk.')
    metadata=json.loads(result.stdout)
    if s.cancelled(job):output.unlink(missing_ok=True);raise ValueError('A narráció leállítva.')
    s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,agent['project'],output.name,str(output),'audio',time.time(),job));s.db.commit()
    return dict(saved=name,**metadata,instruction='Narration is an audio asset. Transcribe and align it before planning a narrated video; never invent word times.')


def engine(model):
    import sherpa_onnx
    p=Path(model)
    config=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(model=str(p/'model.onnx'),voices=str(p/'voices.bin'),
            tokens=str(p/'tokens.txt'),data_dir=str(p/'espeak-ng-data'),lexicon=str(p/'lexicon-us-en.txt')),
        num_threads=2))
    if not config.validate():raise ValueError('Invalid Kokoro configuration')
    return sherpa_onnx.OfflineTts(config)


def generate(payload):
    import wave,numpy as np
    audio=engine(payload['model']).generate(text=payload['text'],sid=payload['voice'],speed=payload['speed'])
    with wave.open(payload['output'],'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(audio.sample_rate)
        f.writeframes((np.clip(audio.samples,-1,1)*32767).astype('<i2').tobytes())
    return dict(engine='kokoro-local',sample_rate=audio.sample_rate,duration=len(audio.samples)/audio.sample_rate,voice=payload['voice'])


if __name__=='__main__':
    import sys
    print(json.dumps(generate(json.loads(sys.stdin.read(32768)))))
