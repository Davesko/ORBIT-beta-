"""Local anonymous voice turns and measured transcript pause evidence."""
import math,wave
from pathlib import Path

def annotate(result,turns):
 words=[w for seg in result.get('segments',[]) for w in seg.get('words',[])]
 for word in words:
  overlaps=[(max(0,min(word['end'],t['end'])-max(word['start'],t['start'])),t['speaker']) for t in turns]
  if overlaps:
   duration,speaker=max(overlaps)
   if duration/max(.001,word['end']-word['start'])>=.6:word['speaker']=speaker
  probability=word.get('probability')
  if type(probability) in (int,float) and probability<.45:word['uncertain']=True
 pauses=[dict(start=a['end'],end=b['start'],seconds=round(b['start']-a['end'],3)) for a,b in zip(words,words[1:]) if .25<=b['start']-a['end']<=10]
 result['audio_context']=dict(speaker_turns=turns,pauses=pauses,uncertain_words=sum(w.get('uncertain') is True for w in words),speaker_scope='Anonymous voice clusters within this source; no person identity or visible-face association.')
 return result

def loudness(wav_path,step=.5):
 """Measured RMS level (dBFS, integer) per half second: a cheap excitement cue, not a meaning claim."""
 import numpy as np
 with wave.open(str(wav_path)) as wav:
  if wav.getsampwidth()!=2 or wav.getnchannels()!=1:raise ValueError('16 bites mono PCM szükséges.')
  rate=wav.getframerate();audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype=np.int16).astype('float32')/32768
 size=max(1,int(rate*step));frames=len(audio)//size
 if not frames:return dict(step=step,db=[])
 rms=np.sqrt(np.mean(audio[:frames*size].reshape(frames,size)**2,axis=1))
 return dict(step=step,db=[int(x) for x in np.maximum(-90,np.round(20*np.log10(np.maximum(rms,1e-6))))])

def diarize(wav_path,models):
 import numpy as np,sherpa_onnx
 segmentation=Path(models)/'speaker-segmentation.onnx';embedding=Path(models)/'speaker-embedding.onnx'
 if not segmentation.is_file() or not embedding.is_file():return [],'not_installed'
 cfg=sherpa_onnx.OfflineSpeakerDiarizationConfig(segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation))),embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding)),clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1,threshold=.5),min_duration_on=.3,min_duration_off=.5)
 if not cfg.validate():raise ValueError('Érvénytelen beszélőszétválasztó modellbeállítás.')
 sd=sherpa_onnx.OfflineSpeakerDiarization(cfg)
 with wave.open(str(wav_path)) as wav:
  if wav.getframerate()!=sd.sample_rate or wav.getnchannels()!=1 or wav.getsampwidth()!=2:raise ValueError('A beszélőszétválasztóhoz 16 kHz mono PCM hang szükséges.')
  # Short source clips only; long podcasts keep their transcript without this optional pass.
  audio=np.frombuffer(wav.readframes(min(wav.getnframes(),sd.sample_rate*600)),dtype=np.int16).astype('float32')/32768
 turns=[dict(start=round(r.start,3),end=round(r.end,3),speaker='speaker_'+str(r.speaker)) for r in sd.process(audio).sort_by_start_time() if r.end>r.start]
 return turns,'available'
