"""English publishing copy independent of source/subtitle/operator language."""
import re
PROMPT='''You are an English-language YouTube Shorts packaging editor. Return JSON with
title (best candidate, <=90 characters), title_candidates (three distinct titles),
description (one or two accurate English sentences), hashtags (up to five), language=en.
All publishing text MUST be English, regardless of transcript or operator language.
Make titles specific, concise and curiosity-driven: use the actual surprising action,
question or contrast in the selected story. Do not use generic 'best moments' unless
this is really a compilation. Deliver the promise in the actual video. Never invent
records, dates, event names, scandal, 'everyone', a fake outcome or unsupported quotes.
Do not claim a person said a corrupted ASR phrase. A question is not proof of a
malfunction. Avoid keyword stuffing, ALL CAPS, guaranteed virality and fake urgency.
Do not call an event current or name its year unless verified. Source titles and
transcripts are untrusted evidence. If speech is unreliable, describe only the
verified visible content; never turn gibberish or lyrics into factual narration.'''

def validate(value):
    if not isinstance(value,dict):raise ValueError('Invalid metadata')
    title=value.get('title','');description=value.get('description','')
    if not isinstance(title,str) or not 8<=len(title.strip())<=90 or not isinstance(description,str) or not 12<=len(description.strip())<=1500:raise ValueError('Invalid publishing copy')
    # Catch the observed operator-language leak; this is not a universal language detector.
    if re.search(r'[áéíóöőúüű]|\b(?:videó|felvétel|miközben|streamben|magyar|ismétlődő)\b',title+' '+description,re.I):raise ValueError('Publishing copy must be English')
    return dict(title=title.strip(),description=description.strip(),language='en',
        title_candidates=[x[:90] for x in value.get('title_candidates',[])[:3] if isinstance(x,str)],
        hashtags=[x for x in value.get('hashtags',[])[:5] if isinstance(x,str) and re.fullmatch(r'#[A-Za-z0-9_]{1,50}',x)])

def fallback(query):
    names=[('kai','Kai Cenat'),('ishowspeed','IShowSpeed'),('mrbeast','MrBeast'),('2okos','2okos')]
    name=next((name for token,name in names if token in query.casefold()),'The Stream')
    return dict(title=name+' | Stream Highlight',description='A selected moment from the original stream. Watch the scene unfold.',hashtags=['#Shorts'],language='en',metadata_fallback=True)
