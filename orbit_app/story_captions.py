"""Shorts captions: outlined text with no box, placed where it covers nothing.

The caption is drawn as bold white (or yellow for the punchline) text with a thick black outline and a soft shadow,
the usual Shorts look. Its place is chosen per clip from frames sampled across the whole animated shot: a
caption-sized box slides from the top to above YouTube's controls, full width or two-thirds width at the left,
centre or right, and the box with the least drawn content wins, so a face, a hand or the prop is not covered.
Runs in the media runtime (Pillow + NumPy)."""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
# Vertical bands as fractions of the frame; YouTube's own UI covers roughly the bottom 18% and the right edge.
BANDS = {'top': (.08, .30), 'middle': (.38, .60), 'bottom': (.60, .80)}
PREFERENCE = ('top', 'bottom', 'middle')
SIDE = 70


def font(size):
    for path in ('/System/Library/Fonts/Supplemental/Arial Black.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def wrap(draw, text, face, limit):
    rows = ['']
    for word in text.split():
        test = (rows[-1] + ' ' + word).strip()
        if rows[-1] and draw.textlength(test, font=face) > limit:
            rows.append(word)
        else:
            rows[-1] = test
    return rows


def content(frames):
    """Union over the clip of drawn content: pixels far from the background colour, plus edges."""
    union = None
    for frame in frames:
        grey = frame.astype(np.float32).mean(axis=2)
        h, w = grey.shape
        # The background is the most common tone of the frame; an edge sample fails when a character touches the edge.
        counts = np.bincount((grey // 8).astype(int).ravel(), minlength=32)
        background = float(np.argmax(counts) * 8 + 4)
        mask = np.abs(grey - background) > 38
        mask[:, 1:] |= np.abs(np.diff(grey, axis=1)) > 45
        union = mask if union is None else union | mask
    return union


SIZES = (84, 70, 58)
TOP, LIMIT = .045, .88   # down to the floor band under the characters, still above YouTube's bottom controls


def boxes(text):
    """Candidate caption boxes as (x0, y0, x1, y1, size): full width or two-thirds width at the left, centre or right,
    at three text sizes, sliding from the top to above YouTube's bottom controls."""
    out = []
    for size in SIZES:
        for width, xs in ((.9, (.5,)), (.62, (.33, .5, .67))):
            rows = len(layout(text, round(width * W) - 30, size)[1]) if text else 1
            height = (rows * size * 1.18 + 24) / H
            y = TOP
            while y + height <= LIMIT:
                for x in xs:
                    out.append((round(x - width / 2, 3), round(y, 3), round(x + width / 2, 3), round(y + height, 3), size))
                y += .01
    return out


def score(mask, box):
    h, w = mask.shape
    x0, y0, x1, y1 = box[:4]
    area = mask[round(y0 * h):round(y1 * h), round(x0 * w):round(x1 * w)]
    return float(area.mean()) if area.size else 1.


def zone(box):
    middle = (box[1] + box[3]) / 2
    return 'top' if middle < .34 else 'middle' if middle < .58 else 'bottom'


def cost(mask, box):
    """Covered content first; then a smaller size, a narrow box and a lower position cost a little."""
    size = box[4] if len(box) > 4 else SIZES[0]
    # A big caption matters more than a little overlap (13 Nov: small captions squeezed into a corner on painted plates).
    return score(mask, box) * 3 + (SIZES[0] - size) / SIZES[0] * .18 + (.02 if box[2] - box[0] < .8 else 0) + abs((box[0] + box[2]) / 2 - .5) * .12 + box[1] * .01


def choose(mask, candidates, preferred=None):
    """The cheapest box; a preferred zone wins when it covers nearly as little."""
    ranked = sorted(candidates, key=lambda b: (round(cost(mask, b), 4), b[1]))
    best = ranked[0]
    if preferred:
        same = [b for b in ranked if zone(b) == preferred]
        if same and score(mask, same[0]) <= score(mask, best) + .02:
            return same[0]
    return best


def layout(text, width_px, size=84):
    draw = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    face = font(size)
    rows = wrap(draw, text, face, width_px)
    while (len(rows) > 3 or max(draw.textlength(r, font=face) for r in rows) > width_px) and size > 40:
        size -= 4
        face = font(size)
        rows = wrap(draw, text, face, width_px)
    return face, rows


# Emoji and pictographs: the caption font has no glyphs for them and would draw empty boxes.
UNDRAWABLE = re.compile('[\U00010000-\U0010FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]')


def drawable(text):
    return ' '.join(UNDRAWABLE.sub('', str(text)).split())


STOP = set('that this with what your just have from they them then there their about would could should really never always cause because into over were been dont didnt cant wont youre thats isnt'.split())


def keyword(text):
    """The word the reference shorts light up: the longest content word of the line."""
    words = [re.sub(r"[^\w']", '', w) for w in text.split()]
    words = [w for w in words if len(w) >= 4 and w.lower().replace("'", '') not in STOP]
    return max(words, key=len).lower() if words else ''


def render(text, box, punchline=False, highlight=None):
    image = Image.new('RGBA', (W, H))
    text = drawable(text)
    if not text:
        return image
    if isinstance(box, str):
        top, bottom = BANDS[box]
        box = (.06, top, .94, bottom)
    x0, y0, x1, y1 = box[:4]
    face, rows = layout(text, round((x1 - x0) * W) - 30, box[4] if len(box) > 4 else SIZES[0])
    size = face.size
    line = round(size * 1.18)
    cx, cy = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H
    first = cy - (len(rows) - 1) * line / 2
    white, yellow = (255, 255, 255, 255), (255, 221, 51, 255)
    fill = yellow if punchline else white
    stroke = max(6, size // 9)
    shadow = Image.new('RGBA', (W, H))
    shade = ImageDraw.Draw(shadow)
    for i, row in enumerate(rows):
        shade.text((cx + 6, first + i * line + 8), row, anchor='mm', font=face, fill=(0, 0, 0, 150),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    draw = ImageDraw.Draw(image)
    space = draw.textlength(' ', font=face)
    for i, row in enumerate(rows):
        # Word by word, so one keyword can be lit in yellow like the reference shorts.
        words = row.split(' ')
        widths = [draw.textlength(w, font=face) for w in words]
        x = cx - (sum(widths) + space * (len(words) - 1)) / 2
        for word, width in zip(words, widths):
            lit = highlight and re.sub(r"[^\w']", '', word).lower() == highlight
            draw.text((x, first + i * line), word, anchor='lm', font=face, fill=yellow if lit else fill,
                      stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            x += width + space
    return image


def sample(ffmpeg, video, count=6):
    """Frames spread over the whole clip, small and in RGB."""
    raw = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-i', str(video), '-vf', 'fps=4,scale=108:192',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, timeout=90, check=True).stdout
    frames = np.frombuffer(raw, np.uint8)
    frames = frames[:frames.size // (108 * 192 * 3) * 108 * 192 * 3].reshape(-1, 192, 108, 3)
    if not len(frames):
        raise ValueError('A felirat helyének kiválasztásához nincs képkocka.')
    picks = np.linspace(0, len(frames) - 1, min(count, len(frames))).round().astype(int)
    return [frames[i] for i in picks]


def place(ffmpeg, video, output, text, preferred=None, punchline=False, highlight=False):
    # A rig render leaves the mask of what it drew over the painted plate next to the clip: a caption may lie on the
    # background (it is outlined), only the characters and pictures are kept clear. Other clips are measured.
    drawn = Path(str(video)).with_name(Path(str(video)).stem + '-mask.png')
    mask = np.asarray(Image.open(drawn).convert('L').resize((108, 192))) > 127 if drawn.is_file() else content(sample(ffmpeg, video))
    text = drawable(text)
    box = choose(mask, boxes(text), preferred)
    render(text, box, punchline, keyword(text) if highlight else None).save(output)
    return dict(box=box, zone=zone(box), covered=round(score(mask, box), 4))


if __name__ == '__main__':
    request = json.loads(sys.argv[1])
    print(json.dumps(place(request['ffmpeg'], request['video'], request['output'], request['text'],
                           request.get('preferred'), request.get('punchline', False), request.get('highlight', False))))
