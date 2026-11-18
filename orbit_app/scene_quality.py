"""Did the scene HAPPEN? (audit 17 Nov, section 13): a finished MP4 is a technical result; these checks measure the geometry, the
states and the sound of a controlled scene from what was actually drawn and mixed. A check never passes by default: a missing
measurement is a failed check."""


def check(name, value, limit, ok, note=''):
    return dict(name=name, value=value if value is None else round(float(value), 4), limit=limit, passed=bool(ok and value is not None), note=note)


def rect_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def verify_turn_control(rec):
    """`rec` is what the render recorded: per-frame hand/grip points, wheel angle, lamp colour, camera, caption rectangles, the
    audio onsets and the event. Returns {checks, passed}."""
    ev, fps = rec['event'], rec['fps']
    f = ev['frames']
    frames = rec['frames']
    height = rec['hero_height']
    checks = []
    held = [x for x in frames if f['contact'] <= x['n'] <= f['release']]
    worst = max((max(((h[0] - g[0]) ** 2 + (h[1] - g[1]) ** 2) ** .5 for h, g in zip(x['hands'], x['grips'])) for x in held), default=None)
    checks.append(check('hand_on_grip_error_px_vs_hero_height', None if worst is None else worst / height, '<= 0.01', worst is not None and worst / height <= .01, 'both hands, every frame from contact to release'))
    first_change = next((x['n'] for x in frames if abs(x['wheel'] - ev['parameters']['from_deg']) > 1e-6), None)
    checks.append(check('object_changes_only_after_contact', first_change, f"> contact ({f['contact']})", first_change is not None and first_change > f['contact']))
    final = frames[-1]['wheel'] if frames else None
    checks.append(check('wheel_reaches_target_angle_deg', None if final is None else abs(final - ev['parameters']['to_deg']), '<= 0.01', final is not None and abs(final - ev['parameters']['to_deg']) <= .01))
    lamp_frame = next((e['frame'] for e in ev['effects'] if e.get('field') == 'lamp.state'), None)
    before = next((x for x in frames if x['n'] == (lamp_frame or 0) - 3), None)
    after = next((x for x in frames if x['n'] == (lamp_frame or 0) + 3), None)
    seen = bool(before and after and before['lamp_bgr'][1] < 130 and after['lamp_bgr'][1] > 170 and after['lamp_bgr'][1] > after['lamp_bgr'][2] + 40)
    checks.append(check('lamp_change_is_visible_in_the_picture', 1 if seen else 0, '== 1', seen, 'sampled from the rendered pixels around the effect frame'))
    cut = rec.get('cut_frame')
    a, b = next((x for x in frames if x['n'] == cut - 1), None), next((x for x in frames if x['n'] == cut), None)
    same = bool(a and b and abs(a['wheel'] - b['wheel']) < 1e-9 and a['lamp'] == b['lamp'])
    checks.append(check('state_survives_the_cut', 1 if same else 0, '== 1', same, 'wheel angle and lamp state identical on both sides of the cut'))
    onset = rec.get('click_onset_s')
    if onset is None:
        checks.append(check('sound_at_contact_frames', None, '<= 2', False, 'no click found in the mixed audio'))
    else:
        want = next((e['frame'] for e in ev['effects'] if e.get('type') == 'sound' and e.get('role') == 'metal_click'), f['contact'])
        off = abs(onset * fps - want)
        checks.append(check('sound_at_contact_frames', off, '<= 2', off <= 2, 'onset measured in the mixed WAV'))
    clash = [x['n'] for x in held if any(rect_overlap(x['caption'], r) for r in x['contact_rects'])]
    checks.append(check('caption_never_covers_the_contact', len(clash), '== 0', not clash))
    inside = all(0 <= h[0] <= rec['size'][0] and 0 <= h[1] <= rec['size'][1] for x in held for h in x['hands_screen'])
    checks.append(check('both_hands_visible_during_the_grip', 1 if inside else 0, '== 1', inside))
    secs = len(frames) / fps
    checks.append(check('duration_seconds', secs, '12 +/- 0.2', abs(secs - rec['expected_seconds']) <= .2))
    return dict(checks=checks, passed=all(c['passed'] for c in checks))
