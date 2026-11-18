"""Local sound-effect library for Shorts: every effect is synthesized by FFmpeg, nothing is downloaded or licensed.

Each preset is an aevalsrc expression in t (seconds) and a duration. The montage mixes it under speech with a
sidechain duck, so an accent never covers what someone is saying. Names stay short: they travel through the
editor's JSON, the frame contract and the timeline sidecar.
"""

PRESETS = {
    # A soft bubble: emphasis on a reveal or a caption word.
    'pop': dict(expression='0.035*sin(2*PI*800*t)*exp(-32*t)', seconds=.18, label='pop'),
    # A short air sweep: a cut between scenes.
    'whoosh': dict(expression='0.025*sin(2*PI*(350*t+1800*t*t))*sin(PI*t/0.18)', seconds=.18, label='suhanás'),
    # A falling bass hit: lands the punchline or the big reveal.
    'boom': dict(expression='0.11*sin(2*PI*(48*t+9*(1-exp(-9*t))))*exp(-4.2*t)+0.02*(random(0)*2-1)*exp(-40*t)', seconds=.6, label='basszusütés'),
    # Rising noise and tone: builds tension into the payoff cut.
    'riser': dict(expression='(0.018*(random(1)*2-1)+0.02*sin(2*PI*(180*t+260*t*t)))*pow(t/1.2,2)', seconds=1.2, label='feszültségemelő'),
    # A bright bell: a correct answer, an idea, a "gotcha".
    'ding': dict(expression='0.05*sin(2*PI*1318*t)*exp(-6*t)+0.022*sin(2*PI*2637*t)*exp(-9*t)', seconds=.7, label='csengő'),
    # A record scratch: the sudden twist or an awkward stop.
    'scratch': dict(expression='0.05*sin(2*PI*(900*t-1900*t*t))*(0.55+0.45*random(2))*exp(-3.5*t)', seconds=.35, label='lemezkarc'),
    # A tape rewind: a cold open that jumps back to the start of the story.
    'rewind': dict(expression='0.035*sin(2*PI*(1700*t-1700*t*t))*sin(PI*t/0.45)', seconds=.45, label='visszatekerés'),
    # A digital stutter: gaming fails and glitches.
    'glitch': dict(expression='0.04*sgn(sin(2*PI*(110+70*floor(t*36))*t))*exp(-5*t)', seconds=.3, label='glitch'),
    # A camera shutter: a freeze or a "caught on camera" moment.
    'shutter': dict(expression='0.09*(random(3)*2-1)*(exp(-140*t)+0.6*exp(-140*abs(t-0.06)))', seconds=.12, label='fényképező'),
}
NAMES = tuple(PRESETS)
CHOICES = ('none',) + NAMES


def seconds(name):
    return PRESETS[name]['seconds'] if name in PRESETS else 0.


def filter_for(name, delay, label):
    """An FFmpeg filter chain producing the effect as [label], delayed by delay seconds (stereo, 48 kHz)."""
    preset = PRESETS[name]
    milliseconds = max(0, round(delay * 1000))
    return "aevalsrc='%s':s=48000:d=%.3f,pan=stereo|c0=c0|c1=c0,adelay=%d|%d[%s]" % (preset['expression'], preset['seconds'], milliseconds, milliseconds, label)


def latest_start(name, shot_seconds):
    """The last delay at which the whole effect still fits inside the shot."""
    return max(0., shot_seconds - seconds(name))
