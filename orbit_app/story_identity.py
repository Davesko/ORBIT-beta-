"""The cast's identity colours, taken from the series bible text (e.g. Pip's orange head and red cap).

The motion check uses them to see whether the character is still on screen at the end of a clip. Colours shared with
the background or the prop are ignored, so a yellow drill never counts as the cast. (Identity between shots is judged
by a vision model in story_animation.judge: colour histograms proved unreliable on flat cartoon backgrounds.)"""
import re

try:  # The worker's own Python only parses colour words; measuring runs in the media runtime that has OpenCV.
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None

# OpenCV hue is 0-180.
HUES = {
    'red': ((0, 8), (170, 180)), 'orange': ((9, 22),), 'yellow': ((23, 35),), 'green': ((36, 85),),
    'teal': ((86, 100),), 'cyan': ((86, 100),), 'blue': ((101, 130),), 'purple': ((131, 160),),
    'violet': ((131, 160),), 'pink': ((161, 169),), 'magenta': ((161, 169),),
}
MIN_SHARE = .0015


def colours(text):
    words = re.findall(r'[a-z]+', str(text).lower())
    return [w for w in dict.fromkeys(words) if w in HUES]


def cast_colours(lead, support, cast, prop=''):
    names = {'lead': colours(lead), 'support': colours(support)}
    picked = names['lead'] + names['support'] if cast == 'both' else names.get(cast, [])
    shared = set(colours(prop))
    return [c for c in dict.fromkeys(picked) if c not in shared]


def mask(bgr, name):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    out = np.zeros(h.shape, bool)
    for lo, hi in HUES[name]:
        out |= (h >= lo) & (h <= hi)
    return out & (s >= 90) & (v >= 70)


def border(image):
    height, width = image.shape[:2]
    yy, xx = np.mgrid[:height, :width]
    return (xx < width * .06) | (xx > width * .94) | (yy < height * .05)


def usable(anchor, names):
    """Identity colours that are visible in the anchor and are not the background colour."""
    edge = border(anchor)
    return [n for n in names if mask(anchor, n).mean() >= MIN_SHARE and mask(anchor, n)[edge].mean() < .05]


def share(bgr, names):
    return {n: round(float(mask(bgr, n).mean()), 5) for n in names}


def read(path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('A képet nem lehet beolvasni: ' + str(path))
    return image


