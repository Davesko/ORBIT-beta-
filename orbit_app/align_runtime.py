"""Real word times of the narration: Whisper (MLX, word_timestamps) listens to each TTS clip and its words are matched to the
KNOWN text. Runs as `align_runtime.py align <request.json>` in the media runtime and prints one JSON line.

A time is an estimate of Whisper's, never an exact truth (audit 17 Nov): every line carries its coverage (how many of the known
words were found in what Whisper heard), and a line below the threshold stays with the length-weighted estimate.
Numbers and times written as digits are compared in the form the TTS reads them (speakable text is what is aligned).
"""
import difflib, json, re, sys
from pathlib import Path


def norm(word):
    return re.sub(r"[^a-z0-9']", '', str(word).lower())


def match(text, heard):
    """Known words -> heard times. `heard` = [{word, start, end}]. Unmatched words get a time between their matched neighbours
    (confidence 0). Returns (words [{w, s, e, ok}], coverage 0..1)."""
    known = text.split()
    keys = [norm(w) for w in known]
    heard = [h for h in heard if norm(h.get('word', '')) and isinstance(h.get('start'), (int, float)) and isinstance(h.get('end'), (int, float))]
    out = [None] * len(known)
    blocks = difflib.SequenceMatcher(None, keys, [norm(h['word']) for h in heard], autojunk=False).get_matching_blocks()
    for a, b, size in blocks:
        for k in range(size):
            out[a + k] = dict(w=known[a + k], s=float(heard[b + k]['start']), e=float(heard[b + k]['end']), ok=True)
    matched = sum(1 for x in out if x)
    if not matched:
        return [dict(w=w, s=0., e=0., ok=False) for w in known], 0.
    # fill every run of missed words linearly between its matched neighbours
    i = 0
    while i < len(out):
        if out[i]:
            i += 1
            continue
        j = i
        while j < len(out) and not out[j]:
            j += 1
        before = out[i - 1] if i > 0 else None
        after = out[j] if j < len(out) else None
        n = j - i
        lo = before['e'] if before else max(0., after['s'] - .25 * n)
        hi = after['s'] if after else lo + .25 * n
        hi = max(lo, hi)
        for k in range(n):
            out[i + k] = dict(w=known[i + k], s=lo + (hi - lo) * k / n, e=lo + (hi - lo) * (k + 1) / n, ok=False)
        i = j
    return out, matched / len(known)


def align(request):
    import os
    # Whisper calls `ffmpeg` by name: the runtime's own binary comes first on the path
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    import mlx_whisper
    model = request['model']
    result = {}
    for line in request['lines']:
        try:
            r = mlx_whisper.transcribe(line['out'], path_or_hf_repo=model, language='en', word_timestamps=True, verbose=None, condition_on_previous_text=False)
            heard = [w for seg in r.get('segments', []) for w in seg.get('words', [])]
            words, coverage = match(line['text'], heard)
            result[line['out']] = dict(words=words, coverage=round(coverage, 3))
        except Exception as exc:          # one unreadable clip keeps its estimate
            result[line['out']] = dict(words=[], coverage=0., error=type(exc).__name__)
    return dict(ok=True, lines=result)


if __name__ == '__main__':
    try:
        print(json.dumps(align(json.loads(Path(sys.argv[2]).read_text()))))
    except Exception as exc:
        print(json.dumps(dict(ok=False, message=str(exc)[:300])))
        sys.exit(1)
