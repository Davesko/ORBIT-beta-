"""Create a local voice, original instrumental bed and synchronized effect mix."""
import hashlib
import itertools
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from narration import engine

RATE=24000
TAU=math.tau
MUSIC={
    'suspense':(92,(0,3,7,10),52),
    'pulse':(116,(0,4,7,9),56),
    'wonder':(100,(0,2,7,9),60),
    'meme':(128,(0,3,7,10),55),
    'chaos':(152,(0,1,5,6,10),57),
    'sneaky':(96,(0,3,6,7,10),50),
    'happy':(120,(0,4,7,11),62),
    'epic':(84,(0,3,7,8),45),
}
# Kokoro v1.0 speaker ids by name (see story_episode.VOICES).
VOICE_IDS={'am_puck':18,'am_echo':12,'am_fenrir':14,'am_onyx':17,'am_adam':11,'am_liam':15,'am_michael':16,'am_eric':13,
           'af_sky':10,'af_bella':2,'af_heart':3,'af_nova':7,'af_jessica':4,'bm_lewis':27,'bm_george':26,'bm_fable':25,
           'bf_emma':21,'bf_alice':20}


def fade(samples,ms=8):
    """Short linear fade in and out: a sound that starts or stops at full level clicks."""
    samples=np.array(samples,dtype=np.float32)
    n=min(len(samples)//2,round(RATE*ms/1000))
    if n>1:
        ramp=np.linspace(0,1,n,dtype=np.float32)
        samples[:n]*=ramp if samples.ndim==1 else ramp[:,None]
        samples[-n:]*=ramp[::-1] if samples.ndim==1 else ramp[::-1][:,None]
    return samples


def clock(count):
    return np.arange(count,dtype=np.float64)/RATE


def lofi(count,seed):
    """A slow, swung lo-fi loop: soft seventh-chord pads, a muffled kick and brushed hats (no crackle: it read as glitches)."""
    rng=np.random.default_rng(seed)
    bpm=76;beat=60/bpm;sound=np.zeros((count,2),dtype=np.float32)
    chords=((57,60,64,67),(55,59,62,65),(53,57,60,64),(52,55,59,62))
    bar=round(4*beat*RATE)
    release=round(RATE*.6)
    for index,start in enumerate(range(0,count,bar)):
        n=min(count-start,bar+release);t=clock(n)
        pad=sum(np.sin(TAU*440*2**((m-69)/12)*t)*(.6 if i else 1) for i,m in enumerate(chords[index%4]))
        pad=pad*np.minimum(t*3,1)*np.exp(-t*.55)*.016
        tail=np.clip((bar+release-np.arange(n))/release,0,1)  # rings over the bar line, then fades to silence
        pad=pad*tail
        sound[start:start+n]+=np.column_stack((pad,pad*.92))
    for k in range(int(count/RATE/beat)+1):
        at=round(k*beat*RATE+(beat*RATE*.12 if k%2 else 0))
        if at>=count:break
        if k%2==0:
            n=min(count-at,RATE//5);t=clock(n)
            kick=.12*np.sin(TAU*(52*t+18*(1-np.exp(-30*t))))*np.exp(-18*t)*np.minimum(t/.008,1)
            sound[at:at+n]+=kick[:,None]
        n=min(count-at,RATE//30)
        hat=rng.normal(0,.012,n)*np.exp(-clock(n)*120)*np.minimum(clock(n)/.002,1)
        sound[at:at+n,0]+=hat;sound[at:at+n,1]+=hat*.7
    t=clock(count)
    sound*=np.minimum(np.minimum(t/.4,(count/RATE-t)/.6),1)[:,None]
    return sound


def bed(count,mood,seed):
    if mood=='lofi':return lofi(count,seed)
    bpm,scale,base=MUSIC.get(mood,MUSIC['meme'])
    rng=np.random.default_rng(seed)
    sound=np.zeros((count,2),dtype=np.float32)
    unit=round(30*RATE/bpm)
    melody=rng.choice(scale,size=8)
    for index,start in enumerate(range(0,count,unit)):
        n=min(count-start,unit*2)
        t=clock(n)
        midi=base+int(melody[index%len(melody)])
        hz=440*2**((midi-69)/12)
        envelope=np.minimum(t*75,1)*np.exp(-t*(3.4 if mood=='wonder' else 6))
        tone=(np.sin(TAU*hz*t)+.22*np.sin(TAU*2*hz*t))*envelope*.045
        if index%4==0:
            tone+=np.sin(TAU*hz/2*t)*envelope*.037
        pan=.34 if index%2 else .66
        sound[start:start+n]+=np.column_stack((tone*(1-pan),tone*pan))
    t=clock(count)
    sound*=np.minimum(np.minimum(t/.2,(count/RATE-t)/.4),1)[:,None]
    return sound


EFFECT_SECONDS={'vine_boom':1.6,'bruh':.9,'shutdown':2.3,'startup':2.,'critical_error':.9,'sad_trombone':2.6,'airhorn':1.4,
                'crickets':2.2,'bonk':.45,'dun_dun':2.1,'boom':.5,'game_over':.9,'snore':1.2,'scratch':.35,'ding':.7,'splat':.3,'zap':.35,'glass':.6,'footsteps':.6,
                'door':.4,'power_up':.7,'error':.35,'win':.8,'coins':.5}


def meme(name,count):
    """Original meme-style effects (13 Nov). Each copies the GESTURE of a well-known meme sound (the deep boom after a
    line, a computer powering off, a sad trombone) with its own notes and synthesis, never a recorded clip."""
    t=clock(count);rng=np.random.default_rng(len(name)*7)
    env=lambda a,d:np.minimum(t/a,1)*np.exp(-t/d)
    if name=='vine_boom':
        # A huge, slightly distorted low hit with a long tail.
        body=np.sin(TAU*(62*t-16*t*t))+.5*np.sin(TAU*(124*t-30*t*t))+.25*rng.normal(0,1,count)*np.exp(-40*t)
        return .34*np.tanh(2.6*body*env(.004,.42))
    if name=='shutdown':
        # Four warm descending pad chords, the feel of a desktop powering off.
        out=np.zeros(count);step=count//4
        for i,(a,b,c) in enumerate(((659,831,988),(554,698,831),(494,622,740),(415,523,622))):
            u=clock(count-i*step);k=np.minimum(u/.03,1)*np.exp(-u/(.5 if i<3 else 1.1))
            out[i*step:]+=.035*k*(np.sin(TAU*a*u)+np.sin(TAU*b*u)+.7*np.sin(TAU*c*u)+.3*np.sin(TAU*a*2*u))
        return out
    if name=='startup':
        out=np.zeros(count);step=count//5
        for i,f in enumerate((392,523,659,784,1046)):
            u=clock(count-i*step);out[i*step:]+=.04*np.minimum(u/.02,1)*np.exp(-u/.9)*(np.sin(TAU*f*u)+.4*np.sin(TAU*f*1.5*u))
        return out
    if name=='critical_error':
        # Two harsh dissonant beeps, like a system error box popping up.
        on=((t<.16)|((t>.26)&(t<.46)))
        return .05*(np.sign(np.sin(TAU*370*t))+np.sign(np.sin(TAU*523*t)))*on*np.minimum(t*400,1)
    if name=='sad_trombone':
        out=np.zeros(count);marks=(0,.45,.9,1.35)
        for i,(start,f) in enumerate(zip(marks,(392,370,349,330))):
            u=np.clip(t-start,0,None);length=.4 if i<3 else 1.2
            vib=1+.012*np.sin(TAU*5.5*u)*(i==3);gate=(t>=start)&(u<length)
            saw=2*((f*vib*u)%1)-1
            out+=.05*saw*gate*np.minimum(u/.04,1)*np.exp(-np.clip(u-length*.6,0,None)*6)*(1-.25*np.sin(TAU*3*u))
        return out
    if name=='airhorn':
        out=np.zeros(count)
        for start,length in ((0,.18),(.24,.18),(.48,.8)):
            u=np.clip(t-start,0,None);gate=(t>=start)&(u<length)
            tone=sum(np.sign(np.sin(TAU*f*u)) for f in (466,587,698))
            out+=.03*tone*gate*np.minimum(u/.01,1)
        return .14*np.tanh(out*14)
    if name=='crickets':
        chirp=np.sin(TAU*4400*t)*(np.sin(TAU*28*t)>0)*((t%.9)<.22)
        return .05*chirp*np.minimum(t/.05,1)
    if name=='bonk':
        return .16*np.sin(TAU*(520*t-900*t*t))*np.exp(-24*t)+.05*rng.normal(0,1,count)*np.exp(-90*t)
    if name=='dun_dun':
        out=np.zeros(count)
        for start,f,d in ((0,110,.35),(.45,104,.35),(.9,98,1.1)):
            u=np.clip(t-start,0,None);gate=t>=start
            out+=.07*gate*np.tanh(2*(np.sin(TAU*f*u)+.6*np.sin(TAU*f*2*u)+.3*np.sin(TAU*f*3*u)))*np.minimum(u/.01,1)*np.exp(-u/d)
        return out
    return None


def effect(name,count):
    t=clock(count)
    if name=='none':return np.zeros(count)
    made=meme('vine_boom' if name=='bruh' else name,count)    # "bruh" is spoken in the mix; here it is its boom
    if made is not None:return made
    if name=='impact':
        return .13*np.sin(TAU*(100*t-70*t*t))*np.exp(-20*t)
    if name=='boom':
        return .30*np.sin(TAU*(78*t-42*t*t))*np.exp(-10*t)*np.minimum(t*100,1)
    if name=='record_stop':
        return .08*np.sin(TAU*(1100*t-1700*t*t))*np.exp(-10*t)*np.minimum(t*250,1)
    if name=='whoosh':
        return .045*(np.sin(TAU*(350*t+2200*t*t))+.45*np.sin(TAU*733*t))*np.sin(np.pi*t/t[-1])**2
    rng=np.random.default_rng(len(name))
    if name=='crunch':
        bursts=sum(np.clip(np.sin(np.pi*(t-i*.055)/.03),0,None)*((t>i*.055)&(t<i*.055+.03)) for i in range(4))
        return .09*rng.normal(0,1,count)*bursts*np.exp(-6*t)
    if name=='pop':
        return .1*np.sin(TAU*(900*t-2500*t*t))*np.exp(-40*t)
    if name=='glitch':
        return .05*np.sign(np.sin(TAU*(110+70*np.floor(t*36))*t))*np.exp(-5*t)
    if name=='ding':
        return .07*np.sin(TAU*1318*t)*np.exp(-6*t)+.03*np.sin(TAU*2637*t)*np.exp(-9*t)
    if name=='scratch':
        return .06*np.sin(TAU*(900*t-1900*t*t))*(.55+.45*rng.random(count))*np.exp(-3.5*t)
    if name=='game_over':
        step=max(1,count//4);out=np.zeros(count)
        for i,f in enumerate((784,659,523,392)):
            seg=.06*np.sign(np.sin(TAU*f*clock(step)))*np.exp(-clock(step)*4)
            out[i*step:i*step+step]=seg[:len(out[i*step:i*step+step])]
        return out
    if name=='snore':
        return .05*rng.normal(0,1,count)*np.sin(np.pi*np.minimum(t/max(t[-1],1e-3),1))**2*(.6+.4*np.sin(TAU*28*t))
    if name=='splat':
        return .14*rng.normal(0,1,count)*np.exp(-14*t)*np.minimum(t*150,1)
    if name=='zap':
        return .05*np.sin(TAU*(1800*t-3000*t*t))*np.exp(-9*t)
    # Fallbacks for cues that normally come from recordings (sfx_library).
    if name=='glass':
        return .06*rng.normal(0,1,count)*np.exp(-9*t)+.04*np.sin(TAU*3100*t)*np.exp(-12*t)
    if name in ('footsteps','door'):
        steps=(0,.32) if name=='footsteps' else (0,)
        return sum(.12*np.sin(TAU*(90 if name=='door' else 140)*(t-s))*np.exp(-30*np.clip(t-s,0,None))*(t>=s) for s in steps)
    if name=='power_up':
        return .05*np.sin(TAU*(400*t+900*t*t))*np.minimum(t*80,1)*np.exp(-2*t)
    if name=='error':
        return .045*np.sign(np.sin(TAU*220*t))*((t<.12)|((t>.18)&(t<.3)))
    notes={'reveal':(700,1046),'tick':(1200,1800),'chime':(523,784),'coins':(1568,2093),'win':(784,1175)}
    a,b=notes[name]
    return .075*(np.sin(TAU*a*t)+.4*np.sin(TAU*b*t))*np.exp(-13*t)*np.minimum(t*250,1)


def fit_voice(samples,source_rate,room,ffmpeg):
    samples=np.asarray(samples,dtype=np.float32)
    if source_rate!=RATE:
        source=np.arange(len(samples))/source_rate
        samples=np.interp(clock(round(len(samples)*RATE/source_rate)),source,samples)
    ratio=len(samples)/room
    if ratio<=1:return samples
    if ratio>1.48:
        raise ValueError('A narráció túl hosszú a jóváhagyott jelenethez.')
    result=subprocess.run([str(ffmpeg),'-nostdin','-v','error','-f','f32le','-ar',str(RATE),'-ac','1','-i','pipe:0',
                           '-af',f'atempo={ratio*1.025:.5f}','-f','f32le','pipe:1'],
                          input=np.asarray(samples,dtype='<f4').tobytes(),capture_output=True,timeout=30,check=True)
    accelerated=np.frombuffer(result.stdout,dtype='<f4')
    if len(accelerated)>room:
        raise ValueError('A narráció nem fér el a jóváhagyott jelenetben.')
    return accelerated


def voiceover(tts,scenes,count,voice_id,ffmpeg):
    """Keep complete lines and let natural speech bridge a cut when it needs to."""
    gap=round(RATE*.13)
    cues=[]
    at=0
    for scene in scenes:
        if scene['voice']:
            speech=tts.generate(text=scene['voice'],sid=voice_id,speed=1.12)
            samples=np.asarray(speech.samples,dtype=np.float32)
            audible=np.flatnonzero(np.abs(samples)>.003)
            if len(audible):
                pad=round(speech.sample_rate*.045)
                samples=samples[max(0,audible[0]-pad):audible[-1]+pad+1]
                cues.append((at+round(RATE*.08),samples,speech.sample_rate))
        at+=scene['frames']*RATE//24
    if not cues:return []
    minimum=1 if len(cues)==1 else 2
    for size in range(len(cues),minimum-1,-1):
        for selected in itertools.combinations(cues,size):
            sizes=[math.ceil(len(samples)*RATE/rate/1.4) for _,samples,rate in selected]
            available=count-gap
            schedule=[]
            for (preferred,samples,rate),needed in zip(reversed(selected),reversed(sizes)):
                if available<needed:
                    break
                start=min(preferred,available-needed)
                schedule.append((start,samples,rate,available-start))
                available=start-gap
            if len(schedule)==size:
                return [(start,fit_voice(samples,rate,room,ffmpeg)) for start,samples,rate,room in reversed(schedule)]
    raise ValueError('Két teljes narrációs mondat sem fér el az epizódban. Rövid narrációt adj meg vagy kérj hosszabb videót.')


def load(path,ffmpeg,channels=1):
    """Any audio file as float32 at the mix rate."""
    raw=subprocess.run([str(ffmpeg),'-nostdin','-v','error','-i',str(path),'-f','f32le','-ar',str(RATE),'-ac',str(channels),'pipe:1'],
                       capture_output=True,timeout=120,check=True).stdout
    data=np.frombuffer(raw,dtype='<f4').copy()
    return data.reshape(-1,channels) if channels>1 else data


REFERENCE_LINE='Hey. So here is the thing, okay? I am just going to say it the way I always say it. That is how I talk, man.'


def references(model,cast,folder):
    """A short clip of each character in their own Kokoro voice: the timbre Chatterbox clones for every line."""
    tts=engine(model);out={}
    for role,item in cast.items():
        speech=tts.generate(text=REFERENCE_LINE,sid=VOICE_IDS.get(item.get('voice'),18),speed=item.get('speed',1.0))
        path=Path(folder)/f'voice-{role}.wav'
        with wave.open(str(path),'wb') as stream:
            stream.setparams((1,2,speech.sample_rate,0,'NONE','not compressed'))
            stream.writeframes((np.clip(np.asarray(speech.samples),-1,1)*32767).astype('<i2').tobytes())
        out[role]=str(path)
    return out


_spoken={}


def speak(tts,text,cast,ffmpeg,audio=None):
    key=(id(tts),text,json.dumps(cast,sort_keys=True),str(audio))
    # The cache keeps the voice object itself: an id() alone is reused once a voice is freed, and a new voice then got an OLD
    # voice's audio back (the flaky test_too_much_dialogue_is_refused_not_cut, 17 Nov).
    held=_spoken.get(key)
    if held is None or held[0] is not tts:_spoken[key]=(tts,_speak(tts,text,cast,ffmpeg,audio))
    return _spoken[key][1]


def _speak(tts,text,cast,ffmpeg,audio=None):
    """A rendered Chatterbox line when there is one, otherwise the character's Kokoro voice (tags removed)."""
    if audio and Path(audio).is_file():
        samples=load(audio,ffmpeg)
        audible=np.flatnonzero(np.abs(samples)>.003)
        if len(audible):samples=samples[max(0,audible[0]-round(RATE*.04)):audible[-1]+round(RATE*.04)+1]
        return fade(samples,12)
    text=' '.join(re.sub(r'\[[^\]]*\]',' ',text).split()) or text
    speech=tts.generate(text=text,sid=VOICE_IDS.get(cast['voice'],18),speed=cast.get('speed',1.0))
    samples=np.asarray(speech.samples,dtype=np.float32)
    audible=np.flatnonzero(np.abs(samples)>.003)
    if len(audible):
        pad=round(speech.sample_rate*.04)
        samples=samples[max(0,audible[0]-pad):audible[-1]+pad+1]
    if speech.sample_rate!=RATE:
        samples=np.interp(clock(round(len(samples)*RATE/speech.sample_rate)),np.arange(len(samples))/speech.sample_rate,samples).astype(np.float32)
    # No pitch shifting: asetrate+atempo smeared the voice. Characters differ by voice, speed and delivery.
    return fade(samples,12)


class NeedsTime(ValueError):
    """The conversation does not fit even sped up: the episode needs this many more samples (owner's run, 12 Nov)."""
    def __init__(self,extra):
        super().__init__('A párbeszéd nem fér el az epizódban; rövidebb mondatok vagy hosszabb videó kell.');self.extra=int(extra)


MAX_STRETCH=2.2        # an episode may grow to keep its lines at a natural pace, never past 90 seconds
MAX_SECONDS=90
NATURAL=1.06           # 13 Nov: 22 s of speech squeezed into 18 s ran at 268 wpm; the reference Shorts talk at 156-190


def stretch(plan,extra):
    """Make every shot proportionally longer so each line is heard at a natural pace inside its own shot (holding only
    the last shot pushed the lines after their pictures). Returns False when the cap is reached."""
    frames=math.ceil(extra*24/RATE)+6
    if plan['frames']+frames>min(plan.get('base_frames',plan['frames'])*MAX_STRETCH,MAX_SECONDS*24):return False
    plan.setdefault('base_frames',plan['frames'])
    total=plan['frames'];added=0
    for scene in plan['scenes'][:-1]:
        more=frames*scene['frames']//total;scene['frames']+=more;added+=more
    plan['scenes'][-1]['frames']+=frames-added;plan['frames']+=frames
    return True


def dialogue(tts,plan,count,ffmpeg,squeeze=NATURAL):
    """Each character's lines in their own voice, in story order, never overlapping. A line starts with its shot and
    may run into the next one; when the whole conversation would not fit, the lines are sped up together (max 1.35x)."""
    cast=plan.get('voices') or {}
    gap=round(RATE*.12);cues=[];at=0
    for scene in plan['scenes']:
        for line in scene.get('lines') or []:
            cues.append((at+round(RATE*.15),speak(tts,line['text'],cast.get(line['speaker'],{}),ffmpeg,line.get('audio')),line['speaker']))
        at+=scene['frames']*RATE//24
    if not cues:return []
    speech=sum(len(c[1]) for c in cues)+gap*len(cues)
    factor=max(1.,speech/(count*.94))
    if factor>squeeze:
        raise NeedsTime(speech/.94-count)
    if factor>1:cues=[(p,fit_voice(x,RATE,math.floor(len(x)/factor),ffmpeg),w) for p,x,w in cues]
    # Forward: no line before its shot or before the previous line ends. Backward: the last line ends inside the episode.
    starts=[];cursor=0
    for preferred,samples,_ in cues:
        starts.append(max(preferred,cursor));cursor=starts[-1]+len(samples)+gap
    limit=count
    for i in range(len(cues)-1,-1,-1):
        starts[i]=min(starts[i],limit-len(cues[i][1]));limit=starts[i]-gap
    if starts[0]<0:
        raise NeedsTime(-starts[0]+RATE//4)
    placed=[(start,samples,speaker) for start,(_,samples,speaker) in zip(starts,cues)]
    return placed


# 13 Nov (owner: "nagyon eltérnek a hangerők"): every part was scaled by its PEAK, so speech sat at about -33 dB RMS
# while a vine boom hit -15 and the music bed was as loud as the voices. Now each part is set by how loud it SOUNDS
# (RMS of its active part) to a target under the voices, and the finished mix is normalised to -14 LUFS.
VOICE_DB=-20.          # every line of every character, the same
MUSIC_DB=-31.          # the bed between lines; -6 dB more under speech (about 17 dB below the voices)
DUCK=.5
# 15 Nov (owner: "hangosak"): effects sat 3-6 dB under the voices, with tails of two seconds and more. The reference
# Shorts keep an effect about 9-12 dB under the voice and under a second long; only the punchline's sound is nearer.
EFFECT_DB={'vine_boom':-27.,'bruh':-25.,'airhorn':-31.,'critical_error':-31.,'sad_trombone':-29.,'shutdown':-30.,
           'startup':-30.,'dun_dun':-29.,'bonk':-29.,'crickets':-33.,'footsteps':-34.,'door':-32.,'snore':-32.,'boom':-28.,
           'impact':-29.,'whoosh':-32.,'pop':-31.,'tick':-34.}
EFFECT_DEFAULT_DB=-31.
EFFECT_MAX_SECONDS=1.3     # a cue is an accent, not a jingle: longer ones fade out here
LOUDNESS=-14.          # TikTok / YouTube Shorts playback level


def loudness(samples):
    """RMS in dB of the audible part: 20 ms blocks within 30 dB of the loudest one (silence does not count)."""
    x=np.asarray(samples,dtype=np.float32)
    if x.ndim>1:x=x.mean(1)
    n=max(1,RATE//50);blocks=len(x)//n
    if blocks<1:return -120.
    energy=np.mean(np.square(x[:blocks*n].reshape(blocks,n)),axis=1)+1e-12
    keep=energy[energy>=energy.max()*1e-3]
    return float(10*np.log10(np.mean(keep)))


def level(samples,target,peak=.9):
    """samples set to the target loudness (dB RMS), never past the peak limit."""
    x=np.asarray(samples,dtype=np.float32)
    if not x.size or not np.any(x):return x
    gain=10**((target-loudness(x))/20)
    top=float(np.max(np.abs(x)))*gain
    if top>peak:gain*=peak/top
    return (x*gain).astype(np.float32)


def normalise(path,ffmpeg):
    """Two-pass EBU R128 loudnorm of the finished mix to -14 LUFS, true peak -1.5 dB; the mix stays as it is if
    ffmpeg cannot do it."""
    try:
        probe=subprocess.run([str(ffmpeg),'-nostdin','-hide_banner','-i',str(path),'-af',f'loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11:print_format=json',
                              '-f','null','-'],capture_output=True,text=True,timeout=120)
        m=json.loads(probe.stderr[probe.stderr.rindex('{'):probe.stderr.rindex('}')+1])
        out=Path(path).with_name(Path(path).stem+'-norm.wav')
        subprocess.run([str(ffmpeg),'-nostdin','-v','error','-y','-i',str(path),'-af',
                        f"loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
                        '-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(out)],check=True,capture_output=True,timeout=120)
        out.replace(path)
        return float(m['input_i'])
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        return None


def score(plan,count,ffmpeg):
    """The episode's own ACE-Step track when it was composed, else the synthesized bed for the mood."""
    path=plan.get('music_file')
    if path and Path(path).is_file() and ffmpeg is not None:
        music=load(path,ffmpeg,2)[:count]
        music=np.pad(music,((0,count-len(music)),(0,0)))
        music=level(music,MUSIC_DB)  # a bed under the voices, not a song on top of them
        t=clock(count)
        return (music*np.minimum(np.minimum(t/.3,(count/RATE-t)/.8),1)[:,None]).astype(np.float32)
    seed=int.from_bytes(hashlib.sha256(plan['title'].encode()).digest()[:4],'big')
    return level(bed(count,plan['profile']['music'],seed),MUSIC_DB)


def cue_sound(plan,index,name,count,ffmpeg):
    """A real recording for the cue when the library has one, else the synthesized effect."""
    path=(plan.get('sfx_files') or {}).get(str(index))   # index is the scene, or "scene:cue" for a cue of its list
    if path and Path(path).is_file() and ffmpeg is not None:
        sample=load(path,ffmpeg)[:count]
        return level(sample,EFFECT_DB.get(name,EFFECT_DEFAULT_DB))
    return level(np.asarray(effect(name,count),dtype=np.float32),EFFECT_DB.get(name,EFFECT_DEFAULT_DB))


EFFECT_LEVEL={'boom':.3,'glass':.18,'game_over':.25,'win':.2,'impact':.16}


def speech_timeline(placed,output):
    """Who speaks when and how loud, one value per video frame: the rig's mouths follow the real voice."""
    step=RATE//24
    cues=[]
    for start,audio,speaker in placed:
        levels=[float(np.sqrt(np.mean(audio[i:i+step]**2))) for i in range(0,len(audio),step)]
        top=max(levels+[1e-6])
        cues.append(dict(speaker=speaker,start=start/RATE,envelope=[round(min(1,v/top*1.15),3) for v in levels]))
    Path(output).with_name('story-speech.json').write_text(json.dumps(cues))


BIG_ACTIONS=('walk_in','walk_out','run_in','pace','sneak','jump','run','crouch','push','slap','handshake','hug','faint','dance','hat_off')


def tighten(plan,model,ffmpeg,output):
    """15 Nov (owner: "sok hatásszünet amikor nem kell akkor is"): shots had a fixed length whatever was said in them,
    so a one-second "Krix." sat in seven seconds of nothing. A shot now lasts as long as its lines take (plus a
    breath), or as long as its action needs when nobody speaks; it never grows here. The new lengths go to the render
    the same way a stretched episode's do. Narrated shots keep their length."""
    if plan['profile'].get('arc')!='meme' or any(sc.get('voice') for sc in plan['scenes']):return False
    lines=[l for sc in plan['scenes'] for l in sc.get('lines') or []]
    if not lines:return False          # a wordless episode's shot lengths are its visual plan
    tts=engine(model) if any(not l.get('audio') for l in lines) else None
    cast=plan.get('voices') or {}
    fast=any(sc.get('pace')=='fast' for sc in plan['scenes'])
    changed=False
    for sc in plan['scenes']:
        said=sum(len(speak(tts,l['text'],cast.get(l['speaker'],{}),ffmpeg,l.get('audio')))/RATE+.12 for l in sc.get('lines') or [])
        acting=sc.get('acting') or {}
        moving=any(acting.get(r) in BIG_ACTIONS for r in ('lead','support')) or acting.get('prop') not in (None,'none')
        action=(2.4 if moving else 1.5) if fast else (2.6 if moving else 1.8)
        need=max(said+.15+(.3 if fast else .45) if said else 0,action)
        if sc.get('beat')=='twist':need+=.5            # the punchline may land
        frames=min(sc['frames'],math.ceil(need*24))
        if sc['frames']-frames>=12:sc['frames']=frames;changed=True      # half a second or more of waiting; less is not worth a re-time
    if changed:
        plan['frames']=sum(sc['frames'] for sc in plan['scenes'])
        plan['base_frames']=plan['frames']
        Path(output).with_name('story-mix-frames.json').write_text(json.dumps(dict(frames=plan['frames'],scenes=[sc['frames'] for sc in plan['scenes']])))
    return changed


def mix(plan,model,ffmpeg,output):
    """The episode's soundtrack. When the lines do not fit, the last shot is held longer (up to MAX_STRETCH) and the
    new shot lengths go next to the mix (story-mix-frames.json) so the render uses the same timing."""
    tighten(plan,model,ffmpeg,output)
    for _ in range(3):
        try:
            return mix_once(plan,model,ffmpeg,output)
        except NeedsTime as short:
            if not stretch(plan,short.extra):break
            Path(output).with_name('story-mix-frames.json').write_text(json.dumps(dict(frames=plan['frames'],scenes=[sc['frames'] for sc in plan['scenes']])))
    return mix_once(plan,model,ffmpeg,output,squeeze=1.35)     # at the 90 s cap: sped up as before, never failed


MEME_LATE=('vine_boom','bruh','sad_trombone','crickets','dun_dun','bonk')


def bruh(model,room):
    """A deep, flat "bruh" in a voice no character uses (am_onyx, slowed): the meme reaction as a sound effect."""
    try:
        speech=engine(model).generate(text='Bruh.',sid=VOICE_IDS.get('am_onyx',17),speed=.78)
        samples=np.asarray(speech.samples,dtype=np.float32)
        if speech.sample_rate!=RATE:
            samples=np.interp(clock(round(len(samples)*RATE/speech.sample_rate)),np.arange(len(samples))/speech.sample_rate,samples).astype(np.float32)
        audible=np.flatnonzero(np.abs(samples)>.003)
        if len(audible):samples=samples[audible[0]:audible[-1]+1]
        return (samples[:room]*(.22/max(.05,float(np.max(np.abs(samples)))))).astype(np.float32)
    except Exception:
        return np.asarray(effect('vine_boom',room))


def mix_once(plan,model,ffmpeg,output,squeeze=NATURAL):
    lines=[line for scene in plan['scenes'] for line in scene.get('lines') or []]
    needs_tts=any(scene.get('voice') for scene in plan['scenes']) or any(not line.get('audio') for line in lines)
    tts=engine(model) if needs_tts else None
    count=plan['frames']*RATE//24
    music=score(plan,count,ffmpeg)
    voice=np.zeros(count,dtype=np.float32)
    effects=np.zeros(count,dtype=np.float32)
    duck=np.ones(count,dtype=np.float32)
    start=0
    voice_id=3 if plan['profile']['arc'] in ('mystery','choice') else 1
    for index,scene in enumerate(plan['scenes']):
        length=scene['frames']*RATE//24
        # A scene's cue list (story_episode.sound_cues): every sound at the moment of the action it belongs to.
        # A plan made before cue lists keeps its single model-picked cue, placed after the line it answers.
        listed=scene.get('cues')
        if listed is None:
            listed=[dict(frac=.64 if scene['sfx'] in ('chime','reveal','boom') else .72 if scene['sfx'] in MEME_LATE else 0.,name=scene['sfx'])] if scene['sfx']!='none' else []
        cue_start=start
        for k,item in enumerate(listed):
            name=item['name']
            cue_offset=min(max(0,length-RATE//5),round(length*item['frac']) if 'frac' in item else round(RATE*item.get('at',0)))
            key=f'{index}:{k}' if scene.get('cues') is not None else index
            room=min(length-cue_offset+RATE//2,count-start-cue_offset,round(RATE*min(EFFECT_MAX_SECONDS,1.3 if (plan.get('sfx_files') or {}).get(str(key)) else EFFECT_SECONDS.get(name,.25))))
            if room<=RATE//50:continue
            cue=level(bruh(model,room),EFFECT_DB['bruh']) if name=='bruh' else cue_sound(plan,key,name,room,ffmpeg)
            cue_start=start+cue_offset
            cue=fade(cue,5)
            tail=min(len(cue),RATE//4)
            cue[-tail:]*=np.linspace(1,0,tail)          # no hard stop where a long recording was cut
            effects[cue_start:cue_start+len(cue)]+=cue[:max(0,count-cue_start)]
        if scene.get('beat')=='twist' and plan['profile']['arc']=='meme' and listed:
            a,b=max(start,cue_start-RATE//5),min(count,cue_start+len(cue))
            ramp=np.ones(b-a,dtype=np.float32)*.12;edge=min(RATE//20,(b-a)//2)
            if edge>1:ramp[:edge]=np.linspace(1,.12,edge);ramp[-edge:]=np.linspace(.12,1,edge)
            music[a:b]*=ramp[:,None]
        start+=length
    spoken=voiceover(tts,plan['scenes'],count,voice_id,ffmpeg) if any(scene.get('voice') for scene in plan['scenes']) else []
    placed=dialogue(tts,plan,count,ffmpeg,squeeze) if lines else []
    spoken+=[(start,audio) for start,audio,_ in placed]
    speech_timeline(placed,output)
    for offset,audio in spoken:
        end=offset+len(audio)
        voice[offset:end]+=level(audio,VOICE_DB)
        left=max(0,offset-RATE//20);right=min(count,end+RATE//8)
        duck[left:offset]=np.minimum(duck[left:offset],np.linspace(1,DUCK,offset-left,endpoint=False))
        duck[offset:end]=DUCK
        duck[end:right]=np.minimum(duck[end:right],np.linspace(DUCK,1,right-end,endpoint=False))
    final=music*duck[:,None]+voice[:,None]+effects[:,None]
    peak=float(np.max(np.abs(final)))
    if peak>.95:final*=.95/peak
    with wave.open(str(output),'wb') as stream:
        stream.setparams((2,2,RATE,0,'NONE','not compressed'))
        stream.writeframes((final*32767).astype('<i2').tobytes())
    if ffmpeg is not None:normalise(output,ffmpeg)


if __name__=='__main__':
    if sys.argv[1]=='refs':
        print(json.dumps(references(Path(sys.argv[2]),json.loads(sys.argv[3]),Path(sys.argv[4]))))
    else:
        mix(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
