"""The studio's own library of everything it has generated, kept for later videos.

Owner, 16 Nov: "minden videóhoz legenerált asseteket jegyezze meg a rendszer és tárolja el, hogy később lehessen
használni mindent". Owner, 16 Nov (later): the library is for the tools and the mechanics, not
the backgrounds. Every object close-up, every held tool (a FLUX icon cut out for the hand), every mechanic (what moved
and what was heard when a sentence said something happened) and every generated sound is kept here with the words it
was made from, its kind, its shape and where it came from; backgrounds are painted fresh for every video. Before a new one is made,
the studio looks for a near match (the same content words, the same shape): a match is reused as it is, so the channel
builds up its own consistent world and each reuse saves a FLUX or audio run. Index: library.jsonl, one JSON line per
asset, appended (never rewritten in place), newest wins."""
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

KINDS = ('insert', 'tool', 'mechanic', 'sound', 'music')   # objects and mechanics; backgrounds are painted fresh for every video
STOP = set('a an the of in on at to and with for from by is are be this that its it your you into over under near very large small big '
           'little old new one two three some no not only clear open empty seen view background painted cartoon flat style simple wide '
           'shot camera picture image people figures text logos'.split())


def root(s):
    folder = s.root / 'asset-library'
    folder.mkdir(exist_ok=True)
    return folder


def words(text):
    return {w for w in re.findall(r'[a-z]+', str(text or '').lower()) if len(w) > 2 and w not in STOP}


def entries(s):
    path = root(s) / 'library.jsonl'
    out = {}
    try:
        for line in path.read_text().splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            out[item['id']] = item
    except OSError:
        return []
    return [x for x in out.values() if Path(x['file']).is_file()]


def add(s, kind, source, text, shape='', origin='', extra=None):
    """Copy a generated file into the library (unless the same bytes are already there) and index it. A mechanic has no
    file of its own: source is None and the recipe is in extra."""
    if kind not in KINDS:
        return None
    if source is None:
        digest = hashlib.sha256((kind + json.dumps(extra or {}, sort_keys=True) + str(text)).encode()).hexdigest()[:24]
        folder = root(s) / kind
        folder.mkdir(exist_ok=True)
        target = folder / (digest + '.json')
        target.write_text(json.dumps(dict(text=text, **(extra or {})), ensure_ascii=False))
    else:
        source = Path(source)
        if not source.is_file():
            return None
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:24]
        folder = root(s) / kind
        folder.mkdir(exist_ok=True)
        target = folder / (digest + source.suffix.lower())
        if not target.is_file():
            tmp = target.with_suffix(target.suffix + '.tmp')
            shutil.copy2(source, tmp)
            tmp.replace(target)
    item = dict(id=digest, kind=kind, file=str(target), text=' '.join(str(text or '').split())[:600], shape=shape, origin=origin,
                made=time.time(), **(extra or {}))
    with (root(s) / 'library.jsonl').open('a') as stream:
        stream.write(json.dumps(item, ensure_ascii=False) + '\n')
    return item


def find(s, kind, text, shape='', least=.7, avoid=()):
    """The best earlier asset of this kind and shape whose words match the request at least `least` (Jaccard)."""
    want = words(text)
    if not want:
        return None
    best, top = None, 0.
    for item in entries(s):
        if item['kind'] != kind or (shape and item.get('shape') and item['shape'] != shape) or item['file'] in avoid:
            continue
        have = words(item.get('text'))
        if not have:
            continue
        score = len(want & have) / len(want | have)
        if score > top:
            best, top = item, score
    return dict(best, score=round(top, 3)) if best and top >= least else None


def summary(s):
    counts = {}
    for item in entries(s):
        counts[item['kind']] = counts.get(item['kind'], 0) + 1
    return counts
