"""Original episode briefs, visual continuity and timed multimodal storyboards."""
import math
import re
import json

MEME_LOOK = ('Clean flat 2D digital cartoon, thick black outlines, round expressive stickman faces, '
             'thin black stick limbs, bold solid colors, flat shading, sparse purple and grey backgrounds. '
             'Readable graphic silhouettes, playful absurd internet comedy, no gradients or photorealism.')
from story_puppet import ACTIONS as RIG_ACTIONS, PROP_MOTIONS

SERIES_FILE = 'story-studio/series-v2.json'
CAST_FILE = 'story-studio/cast.json'
# 13 Nov (owner): the same two named characters in every video of a project, richer designs, a big difference between
# them in mood, speech, clothes and movement, and one of them a kobold. The rig reads these descriptions (story_puppet.design).
CAST = {
    'version': 2,   # 2: narrowed, slightly red kobold eyes (owner 13 Nov)
    'lead': 'Krix: kobold, small and hunched, oval green head, huge pointed ears, hooked nose, tiny fangs, narrowed yellow eyes slightly bloodshot, ragged orange hoodie, jittery and restless',
    'support': 'Dale: tall lanky human, pale tan oval head, tired half-closed eyes, neat side-parted brown hair, glasses, white office shirt with loose blue tie, calm and slow',
    'persona': {
        'lead': 'Krix, a kobold who moved in with a human and takes the human world completely literally: fast, raspy, overexcited, '
                'asks cursed shower-thought questions with total confidence, says "bro" and "wait wait wait", calls Dale "Dale" or "human".',
        'support': 'Dale, a burnt-out office worker in his thirties: slow, flat and dry, sighs, answers in as few words as possible, '
                   'only wants his coffee, his nap or five minutes of quiet; says "Krix." when he has had enough.'},
    'voices': {'lead': {'voice': 'am_fenrir', 'speed': 1.08, 'pitch': 0}, 'support': {'voice': 'bm_lewis', 'speed': 1.0, 'pitch': 0}},
}

OLD_LEADS = ('Krix: kobold, small and hunched, green skin, huge pointed ears, big hooked nose, two tiny fangs, wide yellow eyes, ragged orange hoodie, jittery and restless',)


def cast(s, pid):
    """The project's fixed pair, written once into the project (the owner may edit it there) and read for every episode."""
    path = s.safe_path(pid, CAST_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x') as stream:
            json.dump(CAST, stream, ensure_ascii=False, indent=2)
    except FileExistsError:
        pass
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    if data.get('version') == 1 and data.get('lead') == OLD_LEADS[0]:
        # The owner has not edited the pair: the new default design replaces the old one.
        data = dict(data, version=CAST['version'], lead=CAST['lead'])
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except OSError:
            pass
    ok = all(isinstance(data.get(k), str) and 10 <= len(data[k]) <= 180 for k in ('lead', 'support')) and isinstance(data.get('persona'), dict)
    data = data if ok else CAST
    return dict(lead=data['lead'], support=data['support'], persona={r: str(data['persona'].get(r) or CAST['persona'][r])[:400] for r in ('lead', 'support')},
                voices=voices(data.get('voices') or CAST['voices']), names={r: name_of(data[r], r) for r in ('lead', 'support')})
SERIES = {
    'version': 2,
    'name': 'ORBIT Stickman Shorts',
    'look': MEME_LOOK,
    'lead': 'Pip: orange round head, red baseball cap with brim facing left, large white eyes, thin black stick body and limbs.',
    'support': 'Dot: pale grey round head, tiny purple triangular hair tuft, large white eyes, thin black stick body and limbs.',
    'world': 'A sparse purple-grey cartoon stage with a few large everyday objects and clean empty space behind the characters.',
    'palette': 'Black outlines, orange and grey faces, red cap, purple-grey backgrounds, yellow caption cards.',
    'signature_prop': 'One simple oversized everyday object, described in this episode premise; preserve its shape and color across shots.',
}
MEME_BEATS = ('hook','setup','escalation','reaction','twist','loop')
MEME_GUIDANCE = (
    # 13 Nov (owner, with two reference Shorts): "not brainrot enough, the story is in what they SAY; simple but it hooks".
    # The references: a couch duo where one keeps asking real shower-thought questions ("Why is it cargo on a ship but a
    # shipment in a car?") and the other just wants to eat his sandwich; and a narrated "Have you ever noticed someone
    # who..." observation that turns with "It's not X. It's Y." Both run ~50 s, one line is one complete thought, and the
    # pictures only illustrate what is said. Our episodes were metaphors nobody could follow ("my spine is beef").
    'Write an original 2D stickman cartoon Short for TikTok, Reels and Shorts, for a Gen Z / Gen Alpha feed. THE STORY IS '
    'IN THE DIALOGUE: the viewer must get every joke from the words alone, at first hearing. '
    'Format (brainrot "bro logic"): one ordinary place (a couch, a kitchen, a bus stop), two characters. lead is a '
    'completely serious overthinker (in the personality given in characters) who keeps saying real shower thoughts: stupid-genius questions and '
    'observations about ordinary things everyone knows (words, food, school, cars, photos, sleep, phones, animals, '
    'games), each a COMPLETE, instantly understood thought of 10-20 words that is actually true or logically '
    'undeniable, the kind of line people repeat to a friend, about the episode\'s own topic. Patterns: '
    '"why is X called Y but Z", "if X then why Y", "is X because of Y or is Y because of X", "what happens if you do X '
    'and Y at the same time", "X is technically Y". support has one simple goal (eat a sandwich, sleep, finish a game) '
    'that lead keeps interrupting; support answers short, dry and annoyed (2-10 words), sometimes gets dragged in and '
    'answers seriously, which is funnier. Every beat is a NEW thought, each a little more unhinged than the last, all '
    'in the same calm deadpan; the support\'s goal is the running gag and pays off at the end. The last beat is one '
    'final dumb pun or impossible logic from lead and a one- or two-word reaction ("Really?") that loops the video. '
    'premise is only that ordinary situation (where they sit, what support is trying to do) plus what lead\'s thoughts '
    'are about; a trend is the TOPIC of the thoughts, never a literal physical version of it (13 Nov: a weather '
    '"storm train" became a real train on their house). Pick support\'s goal fresh each time (a bowl of cereal, a nap, '
    'a ranked match, homework, a face mask, a phone call with mum), not always food. '
    'Never metaphors about bodies, never fantasy events, never a plot that needs explaining, no moral lesson, no '
    'dated slang, no "fellow kids" tone, no slurs, no cruelty about real private people. Original lines only: never '
    'reuse a known joke, a reference video\'s line or any line from these instructions (13 Nov: an example line came back '
    'reversed as the hook); every line is about this episode\'s own topic. '
)
EXPLAINER = ('Narrated like the best "have you ever noticed" Shorts: the first line names a relatable person or habit '
             '("Have you ever noticed someone who never posts photos?"), then two or three plain observations, a turn ("It\'s '
             'not X. Sometimes it\'s Y."), and a short quotable last line. When the brief is a question or asks how something was done ("What did ancient humans do when they were bored?", '
             '"How meat was cooked 10,000 years ago"), make a narrated story explainer: every shot gets a narrator line in voice (8-16 '
             'words, curious, dry and funny, one clear fact or step), caption repeats that narrator line as the subtitle, the two '
             'characters act it out with few or no own lines, and the setting moves along the story through two or three '
             'clearly different places (for example a cave, a forest, a campfire), each described in the shot setting. ')
ACTING = ('This is rig animation: each shot sets lead_action and support_action (what the body does for the WHOLE shot), '
          'prop_motion (how the prop behaves, none hides it) and seated (true when they sit on the couch for that shot). '
          'Act out the line, like a good dialogue cartoon: the speaker talks with a gesture that fits what they say '
          '(talk, point, shrug, facepalm, phone, laugh, rage), the listener reacts (stare, nod, shock, laugh, cry). '
          'Keep the characters in place most of the time: bodies only travel when the story needs it '
          '(walk_in to arrive, walk_out to leave, run or jump for one big moment), at most two travelling actions per '
          'episode. Calm, readable acting beats busy movement. '
          'show: one concrete object or tiny scene that illustrates what is SAID in the shot, drawn as a picture that '
          'pops up next to the characters so the viewer sees the words (for example "a credit card with a red DECLINED '
          'stamp", "a phone screen showing 0 likes", "five streaming app logos"); different in every shot, never text alone. ')

STYLES = (
    ('clay', 'Tactile stop-motion clay puppets, sculpted surfaces, practical amber lighting', 'suspense'),
    ('ink', 'High-contrast graphic novel animation, expressive black ink, bold spot colors', 'pulse'),
    ('paper', 'Layered cut-paper animation, visible paper fibers, rich colored shadow planes', 'wonder'),
    ('miniature', 'Cinematic miniature 3D diorama, soft depth of field, expressive toy-like characters', 'pulse'),
    ('watercolor', 'Animated watercolor illustration, expressive washes, light pigment texture', 'wonder'),
    ('pixel', 'Crisp hand-crafted pixel animation, limited vivid palette, coherent square-pixel shapes', 'suspense'),
)
ARCS = (
    ('mystery', ('hook','clue','misdirection','reveal','resolution')),
    ('comedy', ('hook','setup','escalation','payoff')),
    ('discovery', ('hook','question','experiment','result','takeaway')),
    ('choice', ('hook','stakes','attempt','choice','consequence')),
)
SHOT_ORDER = {
    'mystery': ('detail','wide','close','overhead','two-shot'),
    'comedy': ('close','wide','two-shot','detail'),
    'discovery': ('detail','two-shot','overhead','close','wide'),
    'choice': ('close','wide','detail','two-shot','overhead'),
    'meme': ('close','wide','two-shot','close','wide','detail'),
}
CAMERA = ('Static','Pan Left','Pan Right','Zoom In','Zoom Out')
CUES = ('none','impact','reveal','tick','whoosh','chime','boom','record_stop',
        'pop','crunch','glitch','ding','scratch','game_over','snore','splat','zap',
        'glass','coins','power_up','footsteps','door','error','win',
        # Meme sound effects (owner, 13 Nov: "a lényeg a meme hangok"), original synthesized versions: no copyrighted clips.
        'vine_boom','bruh','shutdown','startup','critical_error','sad_trombone','airhorn','crickets','bonk','dun_dun')
MEME_CUES = ('vine_boom','bruh','shutdown','startup','critical_error','sad_trombone','airhorn','crickets','bonk','dun_dun')
# Kokoro v1.0 English speaker ids (verified against the model's speaker_names metadata).
VOICES = {
    'am_puck': (18,'playful cartoonish young American male'), 'am_echo': (12,'mellow laid-back American male'),
    'am_fenrir': (14,'rough gravelly American male'), 'am_onyx': (17,'very low slow American male'),
    'am_adam': (11,'deep American male'), 'am_liam': (15,'young casual American male'),
    'am_michael': (16,'warm friendly American male'), 'am_eric': (13,'confident American male'),
    'af_sky': (10,'bright young American female'), 'af_bella': (2,'energetic American female'),
    'af_heart': (3,'warm American female'), 'af_nova': (7,'clear crisp American female'),
    'af_jessica': (4,'casual American female'), 'bm_lewis': (27,'deadpan British male'),
    'bm_george': (26,'posh British male'), 'bm_fable': (25,'storyteller British male'),
    'bf_emma': (21,'calm British female'), 'bf_alice': (20,'dry British female'),
}
# Median pitch (Hz) and pitch spread of each voice cloned by Chatterbox, measured 13 Nov on the same reference line.
# Flat voices (spread < 60) made the lines monotone; two voices closer than 35 Hz (am_echo 107 + am_puck 123 cloned to
# 101-108 Hz) could not be told apart, while the reference duo talks at about 140 and 195 Hz.
PITCH = {'af_bella': (198, 70), 'af_heart': (198, 89), 'af_jessica': (209, 133), 'af_nova': (166, 91), 'af_sky': (164, 119),
         'am_adam': (124, 47), 'am_echo': (107, 78), 'am_eric': (160, 88), 'am_fenrir': (140, 98), 'am_liam': (124, 127),
         'am_michael': (120, 57), 'am_onyx': (87, 34), 'am_puck': (123, 55), 'bf_alice': (231, 138), 'bf_emma': (179, 50),
         'bm_fable': (120, 91), 'bm_george': (146, 77), 'bm_lewis': (104, 69)}
FLAT = {v for v, (_, spread) in PITCH.items() if spread < 60}
SERIES_VOICES = {'lead': dict(voice='am_liam', speed=1.0, pitch=0), 'support': dict(voice='af_sky', speed=1.0, pitch=0)}
MOODS = ('meme','lofi','chaos','sneaky','happy','epic','suspense','pulse','wonder')


def voices(value):
    """A {lead, support} voice cast: Kokoro voice name, speed 0.8-1.2 and a cartoon pitch shift of -4..+4 semitones."""
    out={}
    for role in ('lead','support'):
        item=value.get(role) if isinstance(value,dict) else None
        item=item if isinstance(item,dict) and item.get('voice') in VOICES else SERIES_VOICES[role]
        speed=item.get('speed',1.0);pitch=item.get('pitch',0)
        out[role]=dict(voice=item['voice'],
                       speed=min(1.08,max(1.,float(speed))) if isinstance(speed,(int,float)) and not isinstance(speed,bool) else 1.0,
                       pitch=min(4,max(-4,int(pitch))) if isinstance(pitch,(int,float)) and not isinstance(pitch,bool) else 0)
    for role in ('lead','support'):
        if out[role]['voice'] in FLAT:
            # The nearest lively voice of the same accent and gender keeps the character, with a delivery that moves.
            v=out[role]['voice'];hz=PITCH[v][0]
            out[role]['voice']=min((x for x in PITCH if x[:2]==v[:2] and x not in FLAT),key=lambda x:abs(PITCH[x][0]-hz),default=v)
    lead=out['lead']['voice']
    if out['support']['voice']==lead or abs(PITCH[out['support']['voice']][0]-PITCH[lead][0])<35:
        # Two characters must be told apart by ear: the support gets the closest lively voice of its own kind 35+ Hz away.
        v=out['support']['voice'];hz=PITCH[v][0]
        pool=[x for x in PITCH if x not in FLAT and x!=lead and abs(PITCH[x][0]-PITCH[lead][0])>=35]
        out['support']['voice']=min(pool,key=lambda x:(x[:2]!=v[:2],x[1]!=v[1],abs(PITCH[x][0]-hz)))
    return out


def name_of(description,fallback):
    head=str(description).split(':',1)[0].strip()
    return head if ':' in str(description) and 1<=len(head)<=24 else fallback


def series(s,pid):
    """Versioned project data, snapshotted into a run before any model starts."""
    path=s.safe_path(pid,SERIES_FILE)
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x') as stream:
            json.dump(SERIES,stream,ensure_ascii=False,indent=2)
    except FileExistsError:
        pass
    try:
        data=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError) as error:
        raise ValueError('A Történetműhely karakterbibliája nem olvasható. Ellenőrizd a story-studio/series-v2.json fájlt.') from error
    if (not isinstance(data,dict) or not art_valid(data) or not isinstance(data.get('look'),str)
        or not 20<=len(data['look'])<=700 or data.get('version')!=2
        or not isinstance(data.get('name'),str) or not 1<=len(data['name'])<=100):
        raise ValueError('A Történetműhely karakterbibliája hibás. Ellenőrizd a story-studio/series-v2.json fájlt.')
    return {key:data[key] for key in SERIES}


def meme_profile(seconds, bible):
    return dict(style='stickman_2d',look=bible['look'],music='meme',arc='meme',
                beats=MEME_BEATS if seconds>=10 else ('hook','setup','twist','loop'),
                art={key:bible[key] for key in ART_FIELDS},series_name=bible['name'],series_version=bible['version'])


def profile(index, seconds):
    style,look,music=STYLES[index%len(STYLES)]
    arc,beats=ARCS[index%len(ARCS)]
    if seconds<10:
        beats=(beats[0],beats[1],beats[2],beats[-1])
    return dict(style=style,look=look,music=music,arc=arc,beats=beats)


def text_field(lo,hi):
    return {'type':'string','minLength':lo,'maxLength':hi}


ART_FIELDS={k:text_field(10,180) for k in ('lead','support','world','palette','signature_prop')}
ART_SCHEMA={'type':'object','required':list(ART_FIELDS),'properties':ART_FIELDS,'additionalProperties':False}
SHOT_FIELDS={
    'setting':text_field(12,140), 'opening_image':text_field(18,210),
    'visual_action':text_field(15,210),'visible_result':text_field(10,140),
    'camera':{'type':'string','enum':CAMERA},
    'cast':{'type':'string','enum':('lead','support','both','none')},
    'voice':text_field(0,100),'caption':text_field(0,75),'sfx':{'type':'string','enum':CUES},
}


LINES={'type':'array','maxItems':3,'items':{'type':'object','required':['speaker','text'],'additionalProperties':False,
       'properties':{'speaker':{'type':'string','enum':['lead','support']},'text':text_field(1,140)}}}


def dialogue(value):
    """At most three short spoken lines per shot, each by the lead or the support character."""
    if not isinstance(value,list):return []
    out=[]
    for item in value[:3]:
        if isinstance(item,dict) and item.get('speaker') in ('lead','support') and isinstance(item.get('text'),str):
            text=' '.join(item['text'].split())[:140]   # a whole shower thought is 10-20 words
            if text:out.append(dict(speaker=item['speaker'],text=text))
    return out


def acting(scene):
    """The rig's performance for a shot; a first plan has flat fields, a validated plan carries them under acting."""
    held=scene.get('acting') if isinstance(scene.get('acting'),dict) else {}
    pick=lambda key,flat,allowed,default:next((v for v in (held.get(key),scene.get(flat)) if v in allowed),default)
    return dict(acting=dict(lead=pick('lead','lead_action',RIG_ACTIONS,'idle'),support=pick('support','support_action',RIG_ACTIONS,'idle'),
                            prop=pick('prop','prop_motion',PROP_MOTIONS,'none')))


VARIANTS={'shock':('stare','rage','facepalm'),'point':('shrug','nod','talk'),'facepalm':('cry','shrug'),'laugh':('dance','nod'),
          'rage':('shock','facepalm'),'shrug':('nod','stare'),'game':('phone','stare'),'phone':('game','stare'),'stare':('nod','shrug'),'faint':('cry','shock','facepalm'),'cry':('facepalm','shrug'),'dance':('laugh','nod'),'nod':('stare','shrug')}


# What a shot's action text says a body does, for when the writer left the rig on talk or idle.
ACT_WORDS=((r'slap|smack','slap'),(r'push|shove','push'),(r'shake(?:s)? hands|handshake','handshake'),(r'\bhug','hug'),(r'(?:takes?|pulls?|lifts?|tips?) off (?:his|her|their) (?:cap|hat|beanie)|hat off|tips? (?:his|her|their) (?:cap|hat)','hat_off'),
           (r'crouch|squat|duck(?:s)? down|kneel','crouch'),(r'\bruns? (?:around|across|away|in circles)|chases?','run'),(r'storm(?:s)? (?:off|out)|walk(?:s)? (?:away|off|out)|leave(?:s)?|exit(?:s)?','walk_out'),(r'run(?:s)? in|rush|dash|sprint|burst(?:s)? in|charge(?:s)?','run_in'),
           (r'walk(?:s)? in|enter(?:s)?|arriv|step(?:s)? in|approach','walk_in'),(r'\bpac(?:e|es|ing)\b|back and forth','pace'),(r'sneak|tiptoe|creep','sneak'),(r'jump|hop(?:s)?\b|leap|bounce(?:s)? up','jump'),
           (r'terror|scream|fear|frighten|recoil|jerk|gasp|bulg|startl|jump back','shock'),(r'trembl|shiver|cower|sob|cry|tear','cry'),
           (r'laugh|giggl|smirk','laugh'),(r'facepalm|sigh|head in (?:his|her|their) hand','facepalm'),(r'faint|collaps|pass(?:es)? out|fall(?:s)? back','faint'),
           (r'danc|celebrat|cheer','dance'),(r'angry|rage|furious|yell|stomp','rage'),(r'shrug','shrug'),(r'nod','nod'),
           (r'phone|scroll','phone'),(r'controller|gaming|joystick','game'),(r'point|reach|tap|click|press|lunge|grab','point'),
           (r'stare|watch|deadpan|glare','stare'))


BIG=('crouch','cry','faint','jump','run','dance','sneak','pace','push','slap','hug','handshake','run_in','walk_in','walk_out','rage','hat_off')


def calm(act,lines,show,beat):
    """13 Nov (owner: "furán mozognak ahol nem is indokolt"): a crouch while asking a question, crying at a pun. A big
    body action stays only when what is said or shown in the shot calls for it; arriving and leaving only open or close
    the episode. Otherwise the speaker talks and the listener watches, like the reference Shorts."""
    said={l['speaker']:l['text'] for l in lines}
    text=' '.join(said.values())+' '+show
    out=dict(act)
    for role in ('lead','support'):
        name=out.get(role,'idle')
        if name not in BIG:continue
        if name=='walk_in' and beat=='hook' or name=='walk_out' and beat=='loop':continue
        pattern=next((p for p,a in ACT_WORDS if a==name),None)
        if pattern and re.search(r'\b(?:'+pattern+r')',text,re.I):continue
        out[role]='talk' if role in said else 'stare'
    return out


# 15 Nov (owner, with four reference Shorts): "a hanghatások szűkösek és nem relevánsak, hangosak". One model-picked
# cue per 7-second shot (an airhorn under a line about money) said nothing. A sound now belongs to something the
# viewer SEES: each body action and prop motion has its own sounds at the moment it happens; frac is a position inside
# the shot (the rig's contact point for a push or slap is 0.75), at is seconds from the shot's start.
ACTION_SOUNDS={
    'walk_in':(('at',.15,'footsteps'),('at',.7,'footsteps')),'walk_out':(('at',.2,'footsteps'),('at',.75,'footsteps')),
    'pace':(('at',.2,'footsteps'),('at',.9,'footsteps')),'sneak':(('at',.3,'tick'),('at',1.,'tick')),
    'run_in':(('at',.05,'footsteps'),('at',.35,'footsteps'),('at',.65,'footsteps')),'run':(('at',.05,'footsteps'),('at',.35,'footsteps'),('at',.65,'footsteps')),
    'jump':(('at',.1,'whoosh'),('at',.6,'impact')),'crouch':(('at',.15,'whoosh'),),'faint':(('at',.25,'whoosh'),('frac',.55,'impact')),
    'slap':(('frac',.75,'impact'),),'push':(('frac',.75,'impact'),),'hug':(('frac',.75,'pop'),),'handshake':(),
    'shock':(('at',.08,'pop'),),'facepalm':(('at',.4,'impact'),),'rage':(('at',.3,'impact'),),'hat_off':(('at',.3,'whoosh'),),
    'phone':(('at',.3,'tick'),),'game':(('at',.3,'tick'),('at',.8,'tick')),'point':(),'cry':(),'laugh':(),'dance':()}
PROP_SOUNDS={'fly_in':(('at',0.,'whoosh'),('at',.45,'impact')),'bounce':(('at',.2,'pop'),),'shake':(('at',.2,'tick'),),'grow':(('at',.1,'power_up'),)}
# A cue the writer picked stays only where the shot's own text shows its cause.
SFX_WORDS={'glass':r'glass|window|shatter|break|mirror|bottle|vase','door':r'door|knock|slam|enter|exit','crunch':r'chip|crisp|crunch|bite|eat|snack|cereal|cookie',
           'splat':r'splat|drop|spill|fall|slime|mud|pie','coins':r'coin|money|pay|cash|wallet|buy','snore':r'sleep|snor|nap|doz|bed',
           'glitch':r'glitch|screen|loading|wifi|phone|computer|game|server|app|buffer','error':r'error|wrong|fail|declin|denied','game_over':r'game|lose|lost|controller',
           'win':r'win|won|victory|trophy','power_up':r'level|power|upgrade|charge','ding':r'idea|bell|notification|message|microwave|elevator',
           'footsteps':r'walk|step|run|sneak|tiptoe|chase','zap':r'zap|shock|electric|lightning|laser','scratch':r'stop|freeze|record|wait',
           'boom':r'explod|boom|crash|bang|collaps','impact':r'hit|punch|slap|smack|throw|bonk|kick|bump','whoosh':r'throw|swing|fly|jump|dash|swipe|wave',
           'pop':r'pop|appear|bubble|balloon','tick':r'clock|tick|press|click|button|type|switch','chime':r'reveal|magic|sparkle','reveal':r'reveal|unveil|turn'}


def sound_cues(shot,limit=4):
    """The shot's sounds, each tied to what is seen in it: the bodies' actions, the prop, and the writer's own cue when
    the shot's text shows its cause. A meme sound stays only on the twist. At most three, no cue twice."""
    acting=shot.get('acting') or {}
    cues=[]
    for role in ('lead','support'):
        if shot.get('cast') in (role,'both'):cues+=ACTION_SOUNDS.get(acting.get(role),())
    cues+=PROP_SOUNDS.get(acting.get('prop'),())
    text=' '.join(str(shot.get(k) or '') for k in ('visual_action','visible_result','opening_image'))+' '+' '.join(l['text'] for l in shot.get('lines') or [])
    named=shot.get('sfx')
    if named in MEME_CUES:
        if shot.get('beat')=='twist':cues.append(('frac',.72,named))
    elif named and named!='none' and re.search(SFX_WORDS.get(named,'$^'),text,re.I):
        cues.append(('at',.2,named))
    # The punchline's sound and a hit's impact are the ones a viewer waits for: they are kept first.
    out,seen=[],set()
    for kind,value,name in sorted(cues,key=lambda c:(c[2] not in MEME_CUES,c[0]!='frac',c[1])):
        if name in seen or len(out)>=limit:continue
        seen.add(name);out.append({kind:value,'name':name})
    return sorted(out,key=lambda c:('frac' in c,c.get('at',c.get('frac'))))


PASSIVE=('idle','talk','stare','nod')


def active(act,scene,names,cast):
    """Visual-gag staging: the body does what the shot's action text says. The writer often leaves "talk" next to an
    action text that says "tiptoes to the fridge"; the text wins, and nothing is calmed down."""
    out=dict(act)
    text=str(scene.get('visual_action') or '')
    clauses=re.split(r'[;.]|,? (?:while|and then|then|as|and) ',text)
    for role in ('lead','support'):
        if out.get(role,'idle') not in PASSIVE:continue
        own=' '.join(c for c in clauses if names[role].lower() in c.lower() or re.search(r'\b'+role+r'\b',c,re.I))
        found=acted(own) or (acted(text) if cast==role else None)
        if found:out[role]=found
    return out


def acted(text):
    return next((action for pattern,action in ACT_WORDS if re.search(r'\b(?:'+pattern+r')',text,re.I)),None)


VIEWS=(' — another part of the same place, a different angle with other objects',' — later, in a different corner with new details')


def narrate(clean):
    """A question or history topic is told by a narrator through more than one place. The local writer rarely does it
    (11 Nov: five tries, no narration, one setting), so the shot's own action text becomes the narration and a single
    setting is split into differently framed parts of the place."""
    # A narrator only where nobody speaks: narration over dialogue played as two voice tracks at once (11 Nov).
    if any(shot.get('lines') for shot in clean):
        for shot in clean:
            if shot.get('lines'):shot['voice']=''
        clean_places(clean)
        return
    for shot in clean:
        if len(str(shot.get('voice') or '').split())<5:
            first=re.split(r'(?<=[.!?;])\s',' '.join(str(shot.get('visual_action') or '').split()))[0]
            words=first.rstrip('.;').split()
            # A stage direction ("mirroring the opening pose") is not narration.
            if len(words)>=4 and not re.search(r'\b(pose|mirror\w*|camera|shot|frame|opening|close-?up|cut)\b',first,re.I):shot['voice']=' '.join(words[:16])+'.'
        if shot.get('voice') and not shot.get('lines') and shot['beat'] not in ('hook','twist'):shot['caption']=shot['voice'][:75]
    clean_places(clean)


def clean_places(clean):
    if len({caption_key(sh['setting'])[:40] for sh in clean})<2:
        for i,shot in enumerate(clean):
            part=min(2,i*3//max(1,len(clean)))
            if part:shot['setting']=(shot['setting'][:100]+VIEWS[part-1])[:140]


def staging(clean,names=None,free=False):
    """What the rig acts must carry the joke: the punchline is not spoken before the twist, nobody "talks" in a silent
    shot, a character does not repeat one action in back-to-back shots, and the prop the twist is about is seen."""
    twist=next((s for s in clean if s['beat']=='twist'),None)
    if twist and twist.get('caption'):
        punch=caption_key(twist['caption'])
        for shot in clean[:clean.index(twist)]:
            shot['lines']=[l for l in shot['lines'] if caption_key(l['text'])!=punch]
    last,used={},{'lead':[],'support':[]}
    for shot in clean:
        acting=shot.get('acting')
        if not acting:continue
        speakers={l['speaker'] for l in shot['lines']}
        # A conversation needs both people in the picture: whoever speaks is seen, and wide shots show the pair.
        if shot.get('cast') in ('lead','support') and (speakers-{shot['cast']} or re.search('wide|two',str(shot.get('framing')),re.I)):
            shot['cast']='both'
        clauses=re.split(r'[;.]|, (?:while|and|as) ',shot.get('visual_action',''))
        for role in ('lead','support'):
            if acting[role] in ('talk','idle') and names:
                own=' '.join(c for c in clauses if names[role].lower() in c.lower())
                acting[role]=acted(own) or acting[role]
            if acting[role]=='idle':
                # Nobody just stands there: the big beats get a reaction, and a listener watches the speaker.
                if shot['beat'] in ('reaction','twist') and role not in speakers:acting[role]='shock'
                elif speakers-{role}:acting[role]='stare'
            if acting[role]=='talk' and role not in speakers:acting[role]='stare'
            if acting[role]=='idle' and role in speakers:acting[role]='talk'
            if acting[role] not in ('stare','nod','talk','shrug','point') and (acting[role]==last.get(role) or used[role].count(acting[role])>=2) and acting[role] in VARIANTS:
                options=[v for v in VARIANTS[acting[role]] if v!=last.get(role)]
                acting[role]=next((v for v in options if v not in used[role]),options[0])
            last[role]=acting[role];used[role].append(acting[role])
    # Owner 12 Nov: the forced walking (three travelling actions per episode) made the characters "össze vissza mozognak".
    # Bodies travel at most twice: an arrival at the start and an exit at the end stay, the rest becomes a gesture.
    staged=[s for s in clean if s.get('acting')] if not free else []      # a visual gag keeps every movement
    calm=dict(pace='shrug',sneak='stare',run='shock',run_in='walk_in',jump='laugh',walk_in='talk',walk_out='nod')
    for extra in [s for s in staged if s.get('seated')][2:]:extra['seated']=False
    travels=0
    for i,shot in enumerate(staged):
        for role in ('lead','support'):
            act=shot['acting'][role]
            if act not in calm:continue
            allowed=(act in ('walk_in','run_in') and i==0) or (act=='walk_out' and i==len(staged)-1) or (act in ('run','jump') and shot['beat']=='twist')
            if not allowed or travels>=2:
                act=calm[act]
                if act=='walk_in':act='talk'
                shot['acting'][role]='talk' if act in ('talk','nod') and role in {l['speaker'] for l in shot['lines']} else ('stare' if act=='talk' else act)
            else:travels+=1
    if twist and twist.get('acting') and all(s.get('acting',{}).get('prop','none')=='none' for s in clean):
        twist['acting']['prop']='fly_in'
        loop=clean[-1]
        if loop is not twist and loop.get('acting'):loop['acting']['prop']='wobble'


def schema(beats,meme=False):
    result={'type':'object','required':['title','scenes'],'additionalProperties':False,'properties':{
        'title':text_field(1,100),'scenes':{'type':'array','minItems':len(beats),'maxItems':len(beats),
        'items':{'type':'object','required':list(SHOT_FIELDS),'properties':SHOT_FIELDS,'additionalProperties':False}}}}
    if meme:
        result['properties']['story_prop']=text_field(10,180)
        result['required'].append('story_prop')
        fields=dict(SHOT_FIELDS,cast={'type':'string','enum':['lead','support','both']},lines=LINES,
                    lead_action={'type':'string','enum':list(RIG_ACTIONS)},support_action={'type':'string','enum':list(RIG_ACTIONS)},
                    prop_motion={'type':'string','enum':list(PROP_MOTIONS)},seated={'type':'boolean'},show=text_field(0,140))
        result['properties']['scenes']['items']=dict(result['properties']['scenes']['items'],properties=fields,
                                                     required=list(SHOT_FIELDS)+['lines','lead_action','support_action','prop_motion','seated','show'])
        result['properties']['music']={'type':'string','enum':list(MOODS)}
        result['properties']['music_prompt']=text_field(10,240)
        result['required']+=['music','music_prompt']
    return result


def timing(seconds, count):
    frames=round(seconds*24)
    hook=min(42,round(frames*.19))
    remain=frames-hook
    base,extra=divmod(remain,count-1)
    return [hook]+[base+(i<extra) for i in range(count-1)]


def layout(selected, seconds):
    beats=selected['beats']
    framing=SHOT_ORDER[selected['arc']]
    if len(beats)<len(framing):
        framing=('close','wide','two-shot','detail') if selected['arc']=='meme' else (*framing[:len(beats)-1],framing[-1])
    lengths=timing(seconds,len(beats))
    if selected['arc']=='meme':
        total=round(seconds*24)
        # A short episode opens on a flash; a longer one opens on a whole spoken thought (the reference: ~6 s).
        hook=min(42 if seconds<25 else 130,round(total*.15))
        loop=min(30 if seconds<25 else 60,round(total*.15))
        middle,extra=divmod(total-hook-loop,len(beats)-2)
        lengths=[hook]+[middle+(i<extra) for i in range(len(beats)-2)]+[loop]
    return zip(beats,lengths,framing)


def art_valid(art):
    return isinstance(art,dict) and all(isinstance(art.get(k),str) and 10<=len(art[k].strip())<=180 for k in ART_FIELDS)


QUALIFIER={'hook':'at the start','setup':'for the first time','escalation':'harder and bigger','reaction':'in shock',
           'twist':'with a surprising result','loop':'once more','payoff':'with the final result'}


MORPH = (r'\b(flatten\w*|pancake|melt\w*|morph\w*|stretch\w* (?:like|into)|turns? into|turned into|transform\w*|inflat\w*|'
         r'deflat\w*|liquef\w*|collaps\w* into|shrink\w*|shrank|dissolv\w*|evaporat\w*|vanish\w*|disappear\w*)\b')


def distinct(clean, repair=False):
    """Every beat needs its own first frame, action and result; the loop beat may return to the hook's first frame.

    A repeated first frame is repaired from the previous shot's end state, which is the frame the scene really starts
    on. Repeated actions or results are all named at once so the writer can fix them in one pass. With repair=True (the
    last attempt) a single repeat gets a beat-specific qualifier; a script that copies two or more earlier beats is a
    garbled script (the 2026-11-09 episode replayed shots 1-3 as 4-6) and is refused instead of being shipped."""
    clashes=[]
    for key,limit in (('opening_image',210),('visual_action',210),('visible_result',140)):
        seen={}
        for index,shot in enumerate(clean):
            if key=='opening_image' and shot['beat']=='loop':
                continue
            value=shot[key]
            if value.casefold() in seen:
                first=seen[value.casefold()]
                if key=='opening_image' and index and clean[index-1]['visible_result'].casefold() not in seen and len(clean[index-1]['visible_result'])>=18:
                    value=clean[index-1]['visible_result']
                else:
                    clashes.append((key,clean[first]['beat'],shot['beat'],index,limit))
            seen[value.casefold()]=index
            shot[key]=value
    if not clashes:
        return
    copied={beat for _,_,beat,_,_ in clashes if beat!='loop'}
    if not repair or len(copied)>=2:
        detail='; '.join(f'{key} of {later} repeats {earlier}' for key,earlier,later,_,_ in clashes)
        raise ValueError(f'Every scene needs a different opening_image, visual_action and visible_result ({detail}). '
                         f'Rewrite the {", ".join(dict.fromkeys(b for _,_,b,_,_ in clashes))} shot(s) as new story beats that continue '
                         'the previous shot; never copy earlier beats.')
    for key,_,beat,index,limit in clashes:
        shot=clean[index]
        tail=' ('+QUALIFIER.get(beat,beat)+')'
        shot[key]=shot[key][:limit-len(tail)].rstrip(' .')+tail


def copied(scenes):
    """Indexes of shots whose action or result copies an earlier shot word for word (the loop may reuse the opening)."""
    seen,out=set(),[]
    for index,scene in enumerate(scenes):
        keys={str(scene.get(k) or '').strip().casefold() for k in ('visual_action','visible_result')}-{''}
        if keys&seen:out.append(index)
        seen|=keys
    return out


def morphing(clean):
    """Beats the local video model cannot animate: a body or object that changes shape or appears from nothing."""
    import re
    found=[]
    for shot in clean:
        hit=re.search(MORPH,shot['visual_action']+' '+shot['visible_result'],re.I)
        if hit:found.append((shot['beat'],hit.group(1)))
    return found


def caption_key(text):
    import re
    return re.sub(r'[^\w]+',' ',str(text).casefold()).strip()


def plan(draft, premise, seconds, repair=False):
    art=premise.get('art')
    selected=premise.get('profile')
    if not art_valid(art) or not isinstance(selected,dict):
        raise ValueError('Missing original episode art direction.')
    if selected['arc']=='meme':
        prop=draft.get('story_prop')
        if not isinstance(prop,str) or not 10<=len(prop.strip())<=180:
            raise ValueError('Define story_prop: one precise prop design including shape and color, shared by all shots.')
        art=dict(art,signature_prop=prop.strip())
    beats=selected['beats']
    scenes=draft.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=len(beats):
        raise ValueError('Return the required number of ordered story shots.')
    clean=[]
    for (beat,frames,framing),scene in zip(layout(selected,seconds),scenes):
        if not isinstance(scene,dict):
            raise ValueError('Each shot must be an object.')
        current={}
        for key,rule in SHOT_FIELDS.items():
            value=scene.get(key)
            if not isinstance(value,str):
                raise ValueError(f'Shot is missing {key}.')
            value=value.strip()
            if ('enum' in rule and value not in rule['enum']) or not rule.get('minLength',0)<=len(value)<=rule.get('maxLength',300):
                raise ValueError(f'Shot contains invalid {key}.')
            current[key]=value
        current['lines']=dialogue(scene.get('lines'))
        if selected['arc']=='meme':
            current.update(acting(scene),seated=bool(scene.get('seated')))
            current['show']=' '.join(str(scene.get('show') or '').split())[:140]
            if premise.get('series_format')=='gag':
                # A visual gag is told by bodies: no pop-up pictures, one short line at most, every movement kept.
                current['show']='';current['lines']=[dict(l,text=' '.join(l['text'].split()[:8])) for l in current['lines'][:1]]
                current['acting']=active(current['acting'],scene,{r:name_of(art[r],r) for r in ('lead','support')},current['cast'])
                current['pace']='fast'
            else:
                current['acting']=calm(current['acting'],current['lines'],current['show'],beat)
        clean.append(dict(current,beat=beat,frames=frames,framing=framing))
    distinct(clean,repair)
    # The narrator field is not a second copy of the dialogue: the writer put "Zig: '...' / Zog: '...'" there too,
    # and a narrator read the lines again over the characters' own voices.
    for shot in clean:
        said=caption_key(shot.get('voice') or '')
        # ... and not a voice name either ("am_echo" was put there and would have been read aloud six times).
        if said and (re.search(r"^\s*[\w' -]{1,24}:\s",shot['voice']) or any(caption_key(l['text']) in said for l in shot['lines'])
                     or shot['voice'].strip().lower() in VOICES or selected['arc']=='meme' and len(said.split())<3):
            shot['voice']=''
        shot['caption']=' '.join(re.sub('[\U00010000-\U0010FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]','',shot['caption']).split())
    # One effect is a texture, the same one in every shot is a glitch: a cue plays at most twice per episode.
    count={}
    for shot in clean:
        if shot['sfx']!='none':
            count[shot['sfx']]=count.get(shot['sfx'],0)+1
            if count[shot['sfx']]>2 and shot['beat']!='twist':shot['sfx']='none'
    # A spoken line is said once; a copied line (the 2026-11-09 loop replayed the reaction's lines) is dropped.
    said=set()
    for shot in clean:
        kept=[]
        for line in shot['lines']:
            key=caption_key(line['text'])
            if key not in said:said.add(key);kept.append(line)
        shot['lines']=kept
    if selected['arc']=='meme':
        bad=morphing(clean)
        if bad and not repair:
            raise ValueError('These beats change a shape, which the animator cannot draw cleanly: '
                             +', '.join(f'{b} ("{w}")' for b,w in bad)+'. Show the consequence with a pose, a face, '
                             'or an object that tips, falls, rolls or breaks into clear pieces.')
        if sum(s['cast']!='none' for s in clean)<3:
            raise ValueError('Show a character performing the action in at least three shots.')
        for shot in clean:
            shot['camera']='Static'
        twist=next(shot for shot in clean if shot['beat']=='twist')
        if twist['sfx'] not in MEME_CUES:twist['sfx']='vine_boom'      # the dumb-genius line lands on the meme boom
        captions=premise.get('approved_captions') or dict(hook=premise.get('hook_caption'),twist=premise.get('payoff_caption'))
        captions={beat:value for beat,value in captions.items() if beat in ('hook','twist')
                  and isinstance(value,str) and 1<=len(value.strip())<=75}
        captions={beat:' '.join(re.sub('[\U00010000-\U0010FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]','',value).split()) for beat,value in captions.items()}
        for shot in clean:
            if shot['beat'] in captions:shot['caption']=captions[shot['beat']].strip()
        # One caption appears once: a middle shot repeating the hook or payoff line (or an earlier caption) stays silent.
        used={caption_key(v) for v in captions.values()}
        for shot in clean:
            if shot['beat'] in captions:continue
            key=caption_key(shot['caption'])
            if key and key in used:shot['caption']=''
            elif key:used.add(key)
    elif sum(bool(s['voice']) for s in clean)<2:
        raise ValueError('Use at least two short voiceover lines, with silent beats where useful.')
    if selected['arc']=='meme' and premise.get('format')=='explainer':
        narrate(clean)
    if selected['arc']=='meme':
        # Owner 12 Nov: "más a szöveg mint amit felolvas". A shot with spoken lines shows those lines (timed, as
        # subtitles); a narrated shot shows its narration. Only a silent shot keeps a caption card.
        for shot in clean:
            if shot.get('lines'):shot['caption']=''
            elif shot.get('voice'):shot['caption']=shot['voice'][:75]
        # A card that someone also says aloud appears twice (12 Nov: the twist card and the loop's spoken punchline overlapped).
        spoken={caption_key(l['text']) for shot in clean for l in shot.get('lines') or []}
        for shot in clean:
            if not shot.get('lines') and caption_key(shot.get('caption') or '') in spoken:shot['caption']=''
    if selected['arc']=='meme':
        gag=premise.get('series_format')=='gag'
        staging(clean,{r:name_of(art[r],r) for r in ('lead','support')},free=gag)
        if gag:
            # 15 Nov trial: the pizza flew in six times and Dale walked in three times. Someone arrives once, a prop
            # lands once; after that they are simply there.
            arrived,landed=set(),False
            for shot in clean:
                act=shot['acting']
                for role in ('lead','support'):
                    if act[role] in ('walk_in','run_in'):
                        if role in arrived:act[role]='shock' if shot['beat'] in ('reaction','twist') else 'stare'
                        arrived.add(role)
                if act['prop']=='fly_in':
                    if landed:act['prop']='bounce' if shot['beat']=='escalation' else 'wobble'
                    landed=True
                elif act['prop']=='none' and landed:act['prop']='wobble'      # none would hide the object the gag is about
        for shot in clean:
            if gag and not shot.get('lines'):shot['caption']=''      # no caption cards over a silent gag
            shot['cues']=sound_cues(shot)
    if draft.get('music') in MOODS:
        selected=dict(selected,music=draft['music'])
    music_prompt=' '.join(str(draft.get('music_prompt') or '').split())[:240]
    result=dict(engine='original-episode-v2',title=str(draft.get('title') or 'ORBIT Original')[:100],
                profile=selected,art=art,scenes=clean,frames=sum(s['frames'] for s in clean))
    if selected['arc']=='meme':
        # The rig paints up to three places from the shots' own settings; location is the first one.
        result['location']=str(draft.get('location') or clean[0]['setting']).strip()
        if sum(bool(sh.get('voice')) for sh in clean)>=3:result['caption_position']='bottom'   # narrated: subtitles at the bottom
        result['story_prop']=art['signature_prop']
        result['approved_captions']=captions
        result['voices']=voices(draft.get('voices') or premise.get('voices') or art.get('voices'))
        if music_prompt:result['music_prompt']=music_prompt
        for key in ('reference','caption_position','custom_cast'):
            if premise.get(key) or draft.get(key):result[key]=draft.get(key) or premise.get(key)
    return result


def visual_key(episode):
    return [episode['profile']['style'],episode['profile']['arc'],
            [[s['setting'],s['framing'],s['cast'],s['visual_action']] for s in episode['scenes']]]


def anchor_prompt(episode):
    """The episode's model sheet: the locked location with the whole cast and the prop, neutral poses, wide framing."""
    art=episode['art']
    return (f"Flat 2D stickman cartoon, thick black outlines. Wide establishing shot, vertical 9:16. "
            f"Both characters full body, standing side by side in the middle, neutral friendly pose, facing the viewer: "
            f"{art['lead']} {art['support']} Main prop beside them: {art['signature_prop']}. "
            f"Location: {episode.get('location') or episode['scenes'][0]['setting']}. {art['world']}. {art['palette']}. "
            f"{episode['profile']['look']} No text or logos.")


def prompts(episode,shot,before):
    art=episode['art']
    if episode.get('location'):
        shot=dict(shot,setting=episode['location'])
    cast={'lead':art['lead'],'support':art['support'],'both':art['lead']+' and '+art['support'],
          'none':'No characters visible in this insert'}[shot['cast']]
    shared=(f"{episode['profile']['look']}. {art['world']}. Palette: {art['palette']}. "
            f"{shot['framing']} framing at {shot['setting']}. Visible cast: {cast}. "
            f"Continuity prop, when shown: {art['signature_prop']}. "
            'Compose a vertical 9:16 mobile image. No text, lettering, captions or logos.')
    still=shared+f" Single starting frame before motion: {shot['opening_image']}."
    motion=(shared+f" Start from the supplied image and keep its design. Previous state: {before}. "
            f"One continuous visible action: {shot['visual_action']}. End on {shot['visible_result']}. No scene cuts.")
    if episode['profile']['arc']=='meme':
        # Schnell's T5 encoder keeps 256 tokens. Put the pose and identities before
        # descriptive background text so the decisive hand/prop pose is retained.
        still=(f"Flat 2D stickman cartoon, thick black outlines. Starting pose: {shot['opening_image']}. "
               f"Visible cast: {cast}. Main prop: {art['signature_prop']}. "
               f"{shot['framing']} framing, vertical 9:16. {episode['profile']['look']}. "
               f"{shot['setting']}. {art['world']}. {art['palette']}. No text or logos.")
        motion=(f"Animate the supplied 2D drawing. First anticipate, then visibly perform: {shot['visual_action']}. "
                f"Finish with this held reaction or result: {shot['visible_result']}. "
                "Fixed camera and fixed background. Keep every character fully inside the frame for the whole clip. "
                "Exaggerated facial expression, decisive arm and leg motion, snappy timing with brief pose holds. "
                "Keep head size, cap, face color and black limb design. The character moves independently from props. "
                "No camera pan or zoom, morphing, new limbs, 3D shading, text or scene cuts. "+shared)
        talkers=[l['speaker'] for l in shot.get('lines') or []]
        if talkers:
            who=' and '.join(name_of(art[r],r) for r in dict.fromkeys(talkers))
            motion=f"{who} talks with clear open-and-close mouth movement and small head nods. "+motion
    return still,motion
