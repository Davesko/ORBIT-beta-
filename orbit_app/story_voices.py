"""Expressive character lines with Chatterbox Turbo (MIT) on Apple Silicon, in ORBIT's separate voice runtime.

Each character has a short reference clip in their own Kokoro voice; Chatterbox clones that timbre and speaks the
line with natural delivery, including paralinguistic tags such as [laugh], [chuckle] or [sigh]. One process loads
the model once and renders every line of the episode. Input and output are JSON on stdin/stdout.

Run: voice-runtime/bin/python story_voices.py < request.json
request: {"model": dir, "lines": [{"text": str, "ref": wav, "out": wav}]}"""
import json
import re
import sys
from pathlib import Path

TAGS = ('laugh', 'chuckle', 'sigh', 'gasp', 'cough', 'groan', 'sniff', 'clear throat', 'shush')
TAG = re.compile(r'\[(?:' + '|'.join(TAGS) + r')\]', re.I)


def clean(text):
    """Keep supported nonverbal tags, drop any other bracketed stage direction."""
    kept = TAG.sub(lambda m: '[\0' + m.group(0)[1:-1].lower() + ']', text)
    kept = re.sub(r'\[(?!\0)[^\]]*\]', '', kept).replace('\0', '')
    return ' '.join(kept.split())


def main(request):
    import wave
    import numpy as np
    from mlx_audio.tts.utils import load_model
    model = load_model(Path(request['model']))
    done = []
    for line in request['lines']:
        chunks = [np.asarray(result.audio, dtype=np.float32)
                  for result in model.generate(text=clean(line['text']), ref_audio=line['ref'], temperature=.8)]
        audio = np.concatenate(chunks) if chunks else np.zeros(1, np.float32)
        with wave.open(line['out'], 'wb') as out:
            out.setparams((1, 2, model.sample_rate, 0, 'NONE', 'not compressed'))
            out.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())
        done.append(dict(out=line['out'], seconds=round(len(audio) / model.sample_rate, 3)))
    return dict(engine='Chatterbox Turbo (MLX)', sample_rate=model.sample_rate, lines=done)


if __name__ == '__main__':
    print(json.dumps(main(json.loads(sys.stdin.read()))))
