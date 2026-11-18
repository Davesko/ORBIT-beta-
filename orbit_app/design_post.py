"""Turn a FLUX render into a print-ready file. Runs in ORBIT's image runtime (it has Pillow); the worker's
own Python does not.

    python design_post.py apparel|coloring|art SOURCE OUT THUMB
    python design_post.py book OUT.pdf PAGE.png [PAGE.png ...]

apparel  transparent background (the render is asked for on plain white), trimmed, up to 4096 px: the size
         print-on-demand shops ask for.
coloring pure black lines on white, centred on an A4 page at 300 dpi, for a printable colouring book.
art      upscaled to 4096 px, opaque.
"""
import sys
from PIL import Image, ImageFilter, ImageOps

A4 = (2480, 3508)
LONG = 4096


def upscale(img, long=LONG):
    scale = long / max(img.size)
    return img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS) if scale > 1 else img


def apparel(img):
    rgba = img.convert('RGBA')
    gray = ImageOps.grayscale(img)
    # Near-white becomes transparent with a soft edge, so lines keep their antialiasing.
    alpha = gray.point(lambda v: 0 if v >= 245 else 255 if v <= 215 else int((245 - v) * 255 / 30))
    rgba.putalpha(alpha)
    box = alpha.getbbox()
    if not box:
        raise ValueError('a kép üres (csak fehér háttér)')
    rgba = rgba.crop(box)
    pad = round(max(rgba.size) * 0.05)
    canvas = Image.new('RGBA', (rgba.width + 2 * pad, rgba.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(rgba, (pad, pad), rgba)
    return upscale(canvas)


def coloring(img):
    lines = ImageOps.grayscale(img).filter(ImageFilter.MedianFilter(3)).point(lambda v: 0 if v < 150 else 255)
    box = ImageOps.invert(lines).getbbox()
    if box:
        lines = lines.crop(box)
    room = (A4[0] - 200, A4[1] - 200)
    scale = min(room[0] / lines.width, room[1] / lines.height)
    lines = lines.resize((round(lines.width * scale), round(lines.height * scale)), Image.LANCZOS).point(lambda v: 0 if v < 128 else 255)
    page = Image.new('L', A4, 255)
    page.paste(lines, ((A4[0] - lines.width) // 2, (A4[1] - lines.height) // 2))
    return page


def thumb(img, path):
    t = img.convert('RGBA')
    t.thumbnail((320, 320))
    back = Image.new('RGB', t.size, (236, 236, 240))
    back.paste(t, (0, 0), t)
    back.save(path, 'JPEG', quality=80)


def main(args):
    if args[0] == 'book':
        pages = [Image.open(p).convert('L') for p in args[2:]]
        pages[0].save(args[1], 'PDF', resolution=300, save_all=True, append_images=pages[1:])
        return
    kind, source, out, small = args
    img = Image.open(source)
    done = apparel(img) if kind == 'apparel' else coloring(img) if kind == 'coloring' else upscale(img.convert('RGB'))
    done.save(out, 'PNG', dpi=(300, 300))
    thumb(done, small)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as exc:
        print(str(exc)[:300], file=sys.stderr)
        sys.exit(1)
