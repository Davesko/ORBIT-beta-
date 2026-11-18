"""Cover images for videos, made in the isolated media runtime (Pillow, OpenCV, ffmpeg).

Runs as `thumb_runtime.py` with a JSON request on stdin and one JSON line on stdout.
Request: source, out (folder), hook (text), short (bool), count. It picks the sharpest, most colourful frames
(never a black or blurry one) and builds up to three differently styled covers: big hook text, a punchy zoom and a
clean framed one. No model is involved, so nothing is evicted from the chat model's memory.
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

FONTS = ['/System/Library/Fonts/Supplemental/Impact.ttf', '/System/Library/Fonts/Supplemental/Arial Black.ttf',
         '/System/Library/Fonts/HelveticaNeue.ttc', '/System/Library/Fonts/Helvetica.ttc']
ACCENTS = [(255, 214, 10), (0, 220, 130), (255, 96, 64), (80, 190, 255)]


def duration(ffmpeg, src):
    err = subprocess.run([ffmpeg, '-hide_banner', '-i', src], capture_output=True, text=True).stderr
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 10.0


def grab(ffmpeg, src, at, path):
    done = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', '%.2f' % at, '-i', src, '-frames:v', '1', str(path)], capture_output=True, timeout=40)
    return done.returncode == 0 and Path(path).is_file()


def score(img):
    import cv2, numpy as np
    small = cv2.resize(img, (320, int(320 * img.shape[0] / img.shape[1])))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sharp = min(cv2.Laplacian(gray, cv2.CV_64F).var() / 400.0, 1.5)
    b, g, r = [small[:, :, i].astype('float') for i in range(3)]
    rg, yb = r - g, 0.5 * (r + g) - b
    color = min((np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 80.0, 1.5)
    mean = gray.mean()
    light = 1.0 - abs(mean - 125) / 125.0
    if mean < 18 or mean > 238:
        return 0.0
    return sharp * 0.5 + color * 0.35 + light * 0.3 + min(gray.std() / 60.0, 1) * 0.2


def font(size):
    from PIL import ImageFont
    for path in FONTS:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def wrap(draw, text, fnt, width):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=fnt) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def cover(img, w, h, zoom=1.0):
    from PIL import Image
    ratio = max(w / img.width, h / img.height) * zoom
    big = img.resize((int(img.width * ratio) + 1, int(img.height * ratio) + 1), Image.LANCZOS)
    x, y = (big.width - w) // 2, (big.height - h) // 2
    return big.crop((x, y, x + w, y + h))


def headline(canvas, text, box, accent, stroke=True, align='left'):
    """Largest font whose wrapped text (at most 3 lines) fits the box."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    size = int((y1 - y0) / 1.1)
    while size > 28:
        fnt = font(size)
        lines = wrap(draw, text, fnt, x1 - x0)
        if len(lines) <= 3 and len(lines) * size * 1.08 <= (y1 - y0) and all(draw.textlength(l, font=fnt) <= x1 - x0 for l in lines):
            break
        size -= 6
    fnt = font(size)
    lines = wrap(draw, text, fnt, x1 - x0)
    total = len(lines) * size * 1.08
    y = y1 - total if align == 'bottom' else y0
    for i, line in enumerate(lines):
        fill = accent if i == len(lines) - 1 and len(lines) > 1 else (255, 255, 255)
        draw.text((x0, y + i * size * 1.08), line, font=fnt, fill=fill, stroke_width=max(3, size // 14) if stroke else 0, stroke_fill=(10, 10, 10))


def gradient(canvas, top=0.45, strength=215):
    from PIL import Image
    w, h = canvas.size
    mask = Image.linear_gradient('L').resize((w, h))
    start = int(h * top)
    shade = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    shade.putalpha(mask.point(lambda v: int(strength * max(0, (v / 255 * h - start)) / max(1, h - start))))
    return Image.alpha_composite(canvas.convert('RGBA'), shade).convert('RGB')


def style_hook(frame, w, h, hook, accent, short):
    canvas = gradient(cover(frame, w, h), 0.42)
    pad = int(w * 0.06)
    headline(canvas, hook, (pad, int(h * 0.60), w - pad, int(h * 0.93)), accent, align='bottom')
    from PIL import ImageDraw
    ImageDraw.Draw(canvas).rectangle((pad, int(h * 0.945), pad + int(w * 0.18), int(h * 0.955)), fill=accent)
    return canvas


def style_pop(frame, w, h, hook, accent, short):
    from PIL import ImageEnhance, ImageDraw
    canvas = ImageEnhance.Contrast(ImageEnhance.Color(cover(frame, w, h, 1.22)).enhance(1.45)).enhance(1.12)
    canvas = gradient(canvas, 0.0, 120)
    pad = int(w * 0.06)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, w - 1, h - 1), outline=accent, width=max(8, w // 90))
    band = int(h * (0.30 if short else 0.36))
    draw.rectangle((0, h - band, w, h), fill=(8, 8, 12))
    draw.rectangle((0, h - band, w, h - band + max(8, h // 100)), fill=accent)
    headline(canvas, hook, (pad, h - band + int(band * 0.14), w - pad, h - int(band * 0.10)), accent)
    return canvas


def style_frame(frame, w, h, hook, accent, short):
    from PIL import Image, ImageFilter, ImageDraw
    back = cover(frame, w, h, 1.4).filter(ImageFilter.GaussianBlur(28))
    back = Image.blend(back, Image.new('RGB', (w, h), (14, 14, 22)), 0.5)
    inner_h = int(h * (0.62 if short else 0.70))
    inner_w = int(w * 0.88)
    inset = cover(frame, inner_w, inner_h)
    mask = Image.new('L', inset.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, inset.width - 1, inset.height - 1), radius=int(w * 0.035), fill=255)
    x, y = (w - inner_w) // 2, int(h * 0.05)
    ImageDraw.Draw(back).rounded_rectangle((x - 8, y - 8, x + inner_w + 8, y + inner_h + 8), radius=int(w * 0.04), fill=accent)
    back.paste(inset, (x, y), mask)
    headline(back, hook, (x, y + inner_h + int(h * 0.025), x + inner_w, h - int(h * 0.03)), (255, 255, 255), align='left')
    return back


def main():
    from PIL import Image
    import cv2
    req = json.loads(sys.stdin.read(20000))
    ffmpeg = str(Path(sys.executable).with_name('ffmpeg'))
    src, out = req['source'], Path(req['out'])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('thumb-*.jpg'):
        old.unlink()
    total = duration(ffmpeg, src)
    short = bool(req.get('short'))
    w, h = (1080, 1920) if short else (1280, 720)
    hook = ' '.join(str(req.get('hook') or '').upper().split())[:60] or 'NÉZD MEG!'
    tmp = Path(tempfile.mkdtemp(prefix='thumbs-'))
    frames = []
    count = 14
    for i in range(count):
        at = total * (0.06 + 0.88 * i / (count - 1))
        path = tmp / ('f%02d.png' % i)
        if grab(ffmpeg, src, at, path):
            img = cv2.imread(str(path))
            if img is not None:
                frames.append((score(img), at, path))
    if not frames:
        raise ValueError('A videóból nem sikerült képkockát kivenni.')
    frames.sort(reverse=True)
    picked = []
    for sc, at, path in frames:
        if all(abs(at - p[1]) > total * 0.12 for p in picked):
            picked.append((sc, at, path))
        if len(picked) == 3:
            break
    while len(picked) < 3:
        picked.append(picked[len(picked) % len(picked)])
    styles = [('hook', style_hook), ('pop', style_pop), ('frame', style_frame)]
    result = []
    for i, ((sc, at, path), (name, fn)) in enumerate(zip(picked, styles)):
        img = fn(Image.open(path).convert('RGB'), w, h, hook, ACCENTS[i % len(ACCENTS)], short)
        file = out / ('thumb-%d.jpg' % i)
        img.save(file, quality=88)
        small = img.resize((480, int(480 * h / w)))
        small.save(out / ('thumb-%d-s.jpg' % i), quality=80)
        result.append(dict(file=file.name, style=name, at=round(at, 1)))
    for f in tmp.glob('*'):
        f.unlink()
    tmp.rmdir()
    return dict(thumbs=result, width=w, height=h)


if __name__ == '__main__':
    try:
        print(json.dumps(dict(ok=True, **main())), flush=True)
    except Exception as exc:
        print(json.dumps(dict(ok=False, message=str(exc)[:300] if isinstance(exc, ValueError) else 'A borítókép készítése nem sikerült [' + type(exc).__name__ + '] ' + str(exc)[:160])))
        sys.exit(1)
