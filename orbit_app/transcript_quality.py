"""Flag unreliable ASR instead of treating hallucinated repetition as a story."""
import collections,re

def assess(result):
    bad=[]
    for i,segment in enumerate(result.get('segments',[])):
        tokens=re.findall(r"\w+",segment.get('text','').casefold());counts=collections.Counter(tokens)
        repetition=len(tokens)>=12 and sum(n for _,n in counts.most_common(2))/len(tokens)>.72
        words=segment.get('words',[])
        uncertain=bool(words) and sum(w.get('probability',1)<.35 for w in words)/len(words)>.65
        silent=segment.get('no_speech_prob',0)>.75 and segment.get('avg_logprob',0)<-1
        if repetition or uncertain or silent:bad.append(i)
        segment['usable_for_story']=not (repetition or uncertain or silent)
        segment['asr_warning']='repetitive_or_uncertain_speech' if i in bad else None
    result['transcript_quality']=dict(version=1,unreliable_segments=bad,
        note='Unreliable speech is not narrative evidence. A real chant may still be visual/audio material; do not invent its words or meaning.')
    return result

def reliable(result):
    import copy
    result=assess(copy.deepcopy(result))
    result['segments']=[s for s in result.get('segments',[]) if s['usable_for_story']]
    return result
