"""Controlled 2D scene objects (audit 17 Nov, step 3-4): an object that can be gripped, turned or changed is its OWN object with a
stable id, a world position, grip points and a state. The painted background is only the untouched environment.

Everything here is plain data and geometry (no drawing library needed for the maths); `draw` functions take the rig's Canvas.
World coordinates are pixels of the world layer; the camera is applied to the finished world layer, never to single objects.
"""
import math

WHEEL_RIM = (74, 74, 82)         # BGR
INK = (30, 30, 30)


def wheel(object_id, centre, radius, grips_deg, rotation_deg=0.):
    """A wall-mounted valve wheel seen face-on. Grip angles are positions on the rim in screen degrees (0 = right, 90 = down) at
    rotation 0; turning the wheel moves every grip along the rim."""
    return dict(id=object_id, type='wheel', version=1, centre=tuple(centre), radius=float(radius), grips=list(grips_deg), rotation=float(rotation_deg),
                parent=None, state=dict())


def lamp(object_id, centre, radius, state='off'):
    return dict(id=object_id, type='lamp', version=1, centre=tuple(centre), radius=float(radius), state=dict(value=state), parent=None, rotation=0., grips=[])


def point_on_rim(obj, degrees):
    a = math.radians(degrees)
    return (obj['centre'][0] + obj['radius'] * math.cos(a), obj['centre'][1] + obj['radius'] * math.sin(a))


def grip_points(obj):
    """Where each grip is NOW (after the wheel's rotation)."""
    return [point_on_rim(obj, g + obj['rotation']) for g in obj['grips']]


def bounds(obj):
    """The object's bounding box (x0, y0, x1, y1) for visibility and overlap checks."""
    r = obj['radius'] * (1.12 if obj['type'] == 'wheel' else 1.0)
    return (obj['centre'][0] - r, obj['centre'][1] - r, obj['centre'][0] + r, obj['centre'][1] + r)


def draw_wheel(cv, obj):
    cx, cy = obj['centre']
    r = obj['radius']
    lw = max(3., r * .13)
    cv.circle((cx, cy), r * 1.08, (206, 206, 212))
    cv.circle((cx, cy), r, WHEEL_RIM, max(3, int(lw)))
    cv.circle((cx, cy), r * 1.08, INK, 2)
    for k in range(4):
        a = math.radians(obj['rotation'] + k * 90 + 45)
        cv.line((cx, cy), (cx + math.cos(a) * r, cy + math.sin(a) * r), WHEEL_RIM, lw * .55)
    cv.circle((cx, cy), r * .2, (60, 60, 70))
    # a marker on the rim so a turn can be SEEN (and measured) in the picture
    m = point_on_rim(obj, obj['rotation'] - 90)
    cv.circle(m, r * .1, (40, 40, 220))


def draw_lamp(cv, obj):
    on = obj['state']['value'] == 'on'
    cx, cy = obj['centre']
    r = obj['radius']
    if on:
        cv.circle((cx, cy), r * 1.9, (180, 230, 190))
    cv.circle((cx, cy), r * 1.25, (50, 50, 56))
    cv.circle((cx, cy), r, (60, 200, 80) if on else (92, 92, 100))
    cv.circle((cx, cy), r * 1.25, INK, 2)


def draw(cv, obj):
    {'wheel': draw_wheel, 'lamp': draw_lamp}[obj['type']](cv, obj)
