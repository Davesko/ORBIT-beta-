"""🎱 Szimulációs videók: 2D fizikai szimuláció (labdák, pályák, szabályok) függőleges shortként – "Will it overflow?".

Nem képernyőfelvétel: a szimulációt a gép ablak nélkül, képkockánként számolja ki (pymunk) és rajzolja meg (Pillow), az
ffmpeg fűzi videóvá. Gyorsabb a valós időnél, nem kell hozzá se nyelvi modell, se képgenerátor, és ugyanaz a mag
(kezdőszám) ugyanazt a videót adja – ezért renderelés ELŐTT több magot lefuttatunk rajz nélkül, és azt választjuk,
ahol a csattanó (túlcsordul / kijut / betelik) a videó végére esik. Ha egyik magnál sem jó az időzítés, a tempót
(a szabályok várakozási idejét) magától hangolja.

UNIVERZÁLIS: nem egy fix jelenet, hanem ÉPÍTŐELEMEK leírása (SPEC): pálya + labdák + szabályok (mikor → mit) + vég-
feltétel + számláló + hang + színek. Ebből áll össze az osztódó labdás pohár, a növő labda a körben, a forgó gyűrűkből
szökés, a szögtábla stb. – és bármilyen új kombináció. A gyár ügynökei a koncepciót írják meg, a beépített 🎱 Szimulátor
(gyarak.py) fordítja SPEC-re, és ez a modul gyártja le.

TANULÁS: minden videó SPEC-je és mérőszámai a termék mellé kerülnek; a jóváhagyott videók SPEC-jei mintaként, az
elvetettek kerülendőként mennek vissza a tervezőhöz (tudas()). Amit a tervező az építőelemekből nem tud kirakni, azt a
kívánságlistára írja (~/.kobold/szimulacio/kivansagok.json) – ebből látszik, mivel érdemes a motort bővíteni.

Kézi próba:  ../.venv/bin/python szimulacio.py 0 /tmp/proba.mp4     (0 = a beépített minták sorszáma)
"""
import json
import math
import os
import random
import re as _re
import shutil
import subprocess
import sys
import time
import wave

SZ, M, FPS = 1080, 1920, 60
KX, KY = 540, 1090          # az aréna közepe
R_MAX = 470                 # az aréna legnagyobb fél-mérete
RAJZ_SKALA = 1.5            # ekkora képre rajzolunk, az ffmpeg kicsinyíti 1080×1920-ra (élsimítás)
MAX_LABDA = 1500
# 🥤 TÚLCSORDULÁS 2.0 ("tulcs2"): forrás-labda, gyorsuló szorzó, lefolyó (IN/OUT), fordulatok, lassítás, második pohár
ALSO_TETO, ALSO_ALJ = 1610, 1885   # a második (alsó) pohár: ide ömlik a lefolyó és a túlcsordulás
ALSO_MAX = 150                     # ennyi labda fér el benne; a legrégebbiek "elolvadnak"
CSAPAT_NEV = ["RED", "BLUE"]
CSAPAT_SZIN = ["#ff3d5a", "#3d9bff"]
FORDULATOK = {"lefolyo_nyit": "DRAIN OPEN!", "lefolyo_zar": "DRAIN CLOSED!", "szelesit": "CUP GOT BIGGER!",
              "eso": "BALL RAIN!", "turbo": "TURBO MODE!", "csere": "COLOR SWAP!", "szorzo": ""}
MIN_SUGAR = 7             # ennél kisebbre nem osztódik / zsugorodik egy labda (különben zajjá válik a kép)
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
MAPPA = os.environ.get("ORBIT_SZIM_ADAT") or os.path.expanduser("~/Library/Application Support/Orbit/szimgyar")
BETU = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

PALYAK = ["pohar", "doboz", "kor", "gyuru", "szogtabla", "ures"]
MIKOR = ["labda_fal", "labda_labda", "labda_akadaly", "idokozonkent", "kilep"]
MIT = ["osztodik", "no", "zsugorodik", "gyorsul", "szinvalt", "uj_labda", "eltunik", "res_no", "palya_szukul", "palya_no"]
VEGE = ["tulcsordul", "kijut", "labdaszam", "betelt", "utolso", "ido"]
SZAMLALO = ["labdak", "utkozesek", "kijutottak", "ido", "nincs"]
HANG = ["dallam", "pentaton", "koppanas", "nincs"]  # a régi, egyszavas hangmódok (a régi tervekhez)
# hangszerek: dallamosak és VICCES / meghökkentő effektek – mind helyben szintetizált (nincs benne idegen felvétel),
# és mind hangolható: a "boing" vagy a "kacsa" is el tudja játszani a dallamot
HANGSZEREK = ["marimba", "zongora", "harang", "pengetes", "8bit", "xilofon", "boing", "pop", "buborek", "vizcsepp", "kacsa",
              "lezer", "puki", "bumm", "nyavogas", "sip", "ugras", "koppanas", "nincs"]
VICCES = ("boing", "pop", "buborek", "vizcsepp", "kacsa", "lezer", "puki", "bumm", "nyavogas", "sip", "ugras")
# dallamok félhangokban (közkincs dallamok + skálák); minden ütközés a következő hangot játssza
DALLAMOK = {
    "emelkedo": [0, 2, 4, 7, 9, 12, 14, 16, 19, 21, 24, 21, 19, 16, 14, 12, 9, 7, 4, 2],
    "orom_oda": [4, 4, 5, 7, 7, 5, 4, 2, 0, 0, 2, 4, 4, 2, 2, 4, 4, 5, 7, 7, 5, 4, 2, 0, 0, 2, 4, 2, 0, 0],
    "fur_elise": [7, 6, 7, 6, 7, 2, 5, 3, 0, -9, -5, 0, 2, -5, -1, 2, 3, -5, 7, 6, 7, 6, 7, 2, 5, 3, 0, -9, -5, 0, 2, -5, 3, 2, 0],
    "hegyi_kiraly": [0, 2, 3, 5, 7, 3, 7, 6, 2, 6, 5, 1, 5, 0, 2, 3, 5, 7, 3, 7, 12, 10, 7, 3, 7, 10],
    "korobeiniki": [7, 2, 3, 5, 3, 2, 0, 0, 3, 7, 5, 3, 2, 3, 5, 7, 3, 0, 0, 5, 8, 12, 10, 8, 7, 3, 7, 5, 3, 2, 2, 3, 5, 7, 3, 0, 0],
    "torok_indulo": [2, 0, -1, 0, 3, 5, 3, 2, 3, 7, 8, 7, 6, 7, 14, 12, 11, 12, 14, 12, 11, 12, 15],
    "csillag": [0, 0, 7, 7, 9, 9, 7, 5, 5, 4, 4, 2, 2, 0, 7, 7, 5, 5, 4, 4, 2, 7, 7, 5, 5, 4, 4, 2],
    "kanon": [16, 14, 12, 11, 9, 7, 9, 11, 12, 11, 9, 7, 5, 4, 5, 2],
    "meret": [],      # nincs dallam: a hangmagasság a labda méretétől függ (kicsi = magas)
    "veletlen": [],   # véletlen pentaton hangok
}
HANG_MAPPA = os.path.join(MAPPA, "hangok")   # ide tehetsz SAJÁT hangokat (wav / mp3 / m4a / aiff): "sajat:<fájlnév>"


def sajat_hangok():
    try:
        return sorted(os.path.splitext(f)[0] for f in os.listdir(HANG_MAPPA)
                      if f.lower().endswith((".wav", ".mp3", ".m4a", ".aiff", ".aif", ".ogg")) and not f.startswith("."))[:40]
    except OSError:
        return []
PALETTAK = {
    "neon": ("#0b0b16", "#16162c", "#f5f5ff", ["#ff2d6f", "#ffd23f", "#3bf4fb", "#7dff6b", "#b56bff", "#ff8a3d"]),
    "tuz": ("#120606", "#2a0c08", "#ffe9d6", ["#ff3b1f", "#ff7a1a", "#ffb81f", "#ffe14a", "#ff5a5a"]),
    "jeg": ("#06101c", "#0c2238", "#e8f6ff", ["#48cae4", "#90e0ef", "#00b4d8", "#caf0f8", "#5e9bff"]),
    "pasztell": ("#fbf6ee", "#f1e6d6", "#3b3440", ["#ff9aa2", "#ffdac1", "#b5ead7", "#c7ceea", "#e2f0cb", "#ffb7b2"]),
    "szivarvany": ("#0d0d12", "#1b1b26", "#ffffff", ["#ff595e", "#ff924c", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"]),
    "mono": ("#000000", "#111111", "#ffffff", ["#ffffff", "#d9d9d9", "#ff2d2d"]),
}

SPEC_SEMA = {"type": "object", "properties": {
    "cim": {"type": "string"}, "kerdes": {"type": "string"},
    "hossz": {"type": "integer"}, "paletta": {"type": "string", "enum": list(PALETTAK)},
    "gravitacio": {"type": "number"},
    "palya": {"type": "object", "properties": {
        "tipus": {"type": "string", "enum": PALYAK}, "meret": {"type": "number"}, "forog": {"type": "number"},
        "res": {"type": "number"}, "gyuruk": {"type": "integer"}},
        "required": ["tipus", "meret", "forog", "res", "gyuruk"]},
    "labdak": {"type": "object", "properties": {
        "db": {"type": "integer"}, "sugar": {"type": "number"}, "sebesseg": {"type": "number"},
        "ruganyossag": {"type": "number"}, "indulas": {"type": "string", "enum": ["kozep", "fent", "szorva"]},
        "adagolas": {"type": "number"}, "max": {"type": "integer"}},
        "required": ["db", "sugar", "sebesseg", "ruganyossag", "indulas", "adagolas", "max"]},
    "szabalyok": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
        "mikor": {"type": "string", "enum": MIKOR}, "mit": {"type": "string", "enum": MIT},
        "ertek": {"type": "number"}, "esely": {"type": "number"}, "varakozas": {"type": "number"}},
        "required": ["mikor", "mit", "ertek", "esely", "varakozas"]}},
    "vege": {"type": "object", "properties": {"mikor": {"type": "string", "enum": VEGE}, "ertek": {"type": "number"}},
             "required": ["mikor", "ertek"]},
    "szamlalo": {"type": "string", "enum": SZAMLALO},
    "hang": {"type": "object", "properties": {"hangszer": {"type": "string"}, "dallam": {"type": "string", "enum": list(DALLAMOK)},
                                              "zene": {"type": "string"}},
             "required": ["hangszer", "dallam", "zene"]},
    "latvany": {"type": "object", "properties": {"stilus": {"type": "string", "enum": ["tele", "neon"]}, "nyom": {"type": "boolean"}},
                "required": ["stilus", "nyom"]},
    "siker_felirat": {"type": "string"}, "kudarc_felirat": {"type": "string"}, "hianyzik": {"type": "string"},
    "elemek": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
        "azon": {"type": "string"}, "p": {"type": "object"}}, "required": ["azon", "p"]}}},
    "required": ["cim", "kerdes", "hossz", "paletta", "gravitacio", "palya", "labdak", "szabalyok", "vege", "szamlalo",
                 "hang", "siker_felirat", "kudarc_felirat", "hianyzik"]}

def spec_sema():
    """A SPEC sémája a most elérhető hangszerekkel (a saját hangmappa fájljaival együtt)."""
    import copy

    sema = copy.deepcopy(SPEC_SEMA)
    sema["properties"]["hang"]["properties"]["hangszer"]["enum"] = HANGSZEREK + [f"sajat:{n}" for n in sajat_hangok()]
    sema["properties"]["hang"]["properties"]["zene"]["enum"] = ["trend", "nincs"] + [z["azon"] for z in _trend_zenek()]
    return sema


def _trend_zenek():
    try:
        import szim_trendhang as trendhang
        return trendhang.zenek()
    except Exception:
        return []


def _zene_tisztit(z):
    """A háttérzene: "nincs" | "trend" (a gyártáskor a legfrissebb, legkevésbé használt felkapott dal) | egy letöltött
    trending dal azonosítója. Ha nincs letöltött dal, "nincs"."""
    z = str(z or "nincs").strip()
    lista = _trend_zenek()
    azonok = [x["azon"] for x in lista]
    if z == "trend":
        return z if any((x.get("tipus") or "dal") == "dal" for x in lista) else "brainrot" if lista else "nincs"
    if z == "brainrot":   # 🧠 a napi brainrot-hangok közül (ha még nincs, a felkapott dal)
        return z if any(x.get("tipus") == "brainrot" for x in lista) else "trend" if lista else "nincs"
    return z if z in azonok else "nincs"


def _hang_tisztit(h):
    regi = {"dallam": ("marimba", "emelkedo"), "pentaton": ("harang", "meret"), "koppanas": ("koppanas", "meret"), "nincs": ("nincs", "emelkedo")}
    if isinstance(h, str):
        h = dict(zip(("hangszer", "dallam"), regi.get(h, regi["dallam"])))
    h = h if isinstance(h, dict) else {}
    hangszer = h.get("hangszer")
    if hangszer not in HANGSZEREK and not (str(hangszer).startswith("sajat:") and str(hangszer)[6:] in sajat_hangok()):
        hangszer = "marimba"
    meme = str(h.get("meme") or "nincs").strip()
    if meme.startswith("sajat:"):
        meme = meme[6:]
    if meme not in ("nincs", "trend", "brainrot") and meme not in sajat_hangok():
        meme = "nincs"
    return {"hangszer": hangszer, "dallam": h.get("dallam") if h.get("dallam") in DALLAMOK else "emelkedo",
            "zene": _zene_tisztit(h.get("zene")), "meme": meme,
            "meme_mod": h.get("meme_mod") if h.get("meme_mod") in ("pattanas", "merfoldko", "auto") else "auto",
            # 🧠 INGER-mód: zene nélkül, minden pattanásra egy brainrot mém-hang (a memek készletből, váltakozva) + sok vizuális inger
            "inger": bool(h.get("inger")),
            "memek": [m for m in (h.get("memek") or []) if isinstance(m, str) and m in sajat_hangok()][:8]}


# Az ügynököknek és a SPEC-fordítónak: miből lehet építkezni (angolul, mint a munkautasítások).
ELEMEK = """BUILDING BLOCKS of the 2D physics simulation engine (vertical 1080x1920 short, 60 fps, no narration; sound = one
note per collision). Any concept must be expressible with these - combine them freely:
- kerdes: the hook question shown on top the whole time (English, max 40 chars, e.g. "Will it overflow?").
- hossz: 20-50 seconds. paletta: neon | tuz | jeg | pasztell | szivarvany | mono. gravitacio: 0 (balls float and keep
  their speed) ... 900 (normal) ... 1800 (heavy).
- palya.tipus: pohar (open-top cup: balls can OVERFLOW over the rim) | doboz (closed box) | kor (closed circle) |
  gyuru (1-4 concentric rotating rings, each with a gap of `res` degrees: balls can ESCAPE) | szogtabla (peg board with
  open bottom, balls fall through) | ures (just the screen edges). meret 0.4-1.0, forog = rotation in degrees/second
  (rings, box, circle), res = gap 15-90 degrees, gyuruk = number of rings.
- labdak: db = starting balls (1-60), sugar = radius 8-90 px, sebesseg = start speed 0-1200, ruganyossag 0.3-1.05
  (bounciness), indulas: kozep | fent | szorva, adagolas = new balls per second dropped in (0 = none), max = ball cap
  (up to 1500; 150-600 looks best).
- szabalyok (max 5): WHEN -> WHAT. mikor: labda_fal (ball hits the container) | labda_labda (two balls hit) |
  labda_akadaly (ball hits a peg) | idokozonkent (every `varakozas` seconds) | kilep (a ball overflows / escapes).
  mit: osztodik (the ball splits in two; ertek = size factor of the halves, 1.0 = same size, 0.8 = smaller) |
  no (grows, ertek e.g. 1.06) | zsugorodik (shrinks, ertek e.g. 0.9) | gyorsul (ertek e.g. 1.05) | szinvalt (new
  colour) | uj_labda (a new ball appears) | eltunik (the ball disappears) | res_no (ring gaps widen by ertek degrees) |
  palya_szukul / palya_no (the container shrinks / grows, ertek e.g. 0.98 / 1.02). esely = probability 0-1,
  varakozas = cooldown in seconds per ball (0.1-3; lower = faster escalation).
- vege (the payoff): tulcsordul (ertek balls left the cup) | kijut (ertek balls escaped the rings) | labdaszam (ball
  count reaches ertek) | betelt (balls fill ertek = 0.3-0.9 of the container) | utolso (only ertek balls remain) |
  ido (just runs for hossz seconds).
- szamlalo: live counter next to the progress bar: labdak | utkozesek | kijutottak | ido | nincs (if it does not match
  the end condition the engine picks the matching one).
- LOGIC (the engine enforces it, design accordingly): the question must be answered by the end condition (question
  about escaping -> kijut; about overflowing -> tulcsordul on a pohar; about filling -> betelt; a number in the question
  = the end value); a ring gap is always wide enough for the ball; rules that cancel each other are dropped; ONE main
  escalation rule plus at most one cosmetic rule (szinvalt) reads best.
- hang = {hangszer, dallam}: every collision plays ONE note - the sound is half of why these videos work.
  hangszer (melodic): marimba | zongora (piano) | harang (bell) | pengetes (plucked string) | 8bit | xilofon;
  hangszer (FUNNY / surprising, still tuned so they can play the melody): boing (cartoon spring) | pop | buborek
  (bubble) | vizcsepp (water drop) | kacsa (duck quack) | lezer (pew) | puki (fart) | bumm (deep meme boom) | nyavogas
  (cat meow) | sip (slide whistle) | ugras (game jump) | koppanas (click) | nincs. Pick a funny one when the idea is
  playful or absurd, a melodic one when it should feel satisfying.
  dallam: emelkedo (rising scale) | orom_oda (Ode to Joy) | fur_elise | hegyi_kiraly (In the Hall of the Mountain King) |
  korobeiniki (the "Tetris" folk tune) | torok_indulo (Turkish March) | csillag (Twinkle Twinkle) | kanon (Canon in D) |
  meret (pitch by ball size: small = high) | veletlen (random pentatonic). A well-known tune played by bounces ("the
  balls play a song") is a proven hook - best with FEW balls (under ~40), otherwise use emelkedo / meret.
  zene: a TRENDING TikTok song under the collision sounds (its catchiest part, faded in/out; the collisions play
  quieter on top) - trending audio is a proven reach boost: "trend" = today's freshest trending song (the default
  choice), "nincs" = only the collision sounds (use it when the bounces play a well-known tune, so they do not clash),
  or the id of a specific downloaded trending song. With a song, prefer a percussive / funny hangszer (pop, koppanas,
  buborek, vizcsepp, boing or a trending meme sound "sajat:trend_...") with dallam meret or veletlen.
- latvany = {stilus: tele (filled glossy balls) | neon (glowing outlines on black), nyom: true = fading motion trails
  (only shown with up to ~70 balls)}. Walls glow and flash in the colour of the ball that hits them, splits and escapes
  throw particles, the payoff flashes and shakes the screen, and a PROGRESS BAR under the question shows how close the
  payoff is (derived from the end condition) - so the viewer always understands the goal.
- siker_felirat / kudarc_felirat: 1-3 word ALL-CAPS banner if the payoff happens / does not happen in time.
- hianyzik: if the concept needs something these blocks cannot do, name it here in one sentence (else empty).
The engine itself picks the random seed and tunes the pacing so that the payoff lands near the end of the video."""

# Beépített minták (a tervező ezekből és a jóváhagyott videók SPEC-jeiből tanul)
MINTAK = [
    {"cim": "Will it overflow?", "kerdes": "Will it overflow?", "hossz": 32, "paletta": "neon", "gravitacio": 900,
     "palya": {"tipus": "pohar", "meret": 0.8, "forog": 0, "res": 0, "gyuruk": 1},
     "labdak": {"db": 1, "sugar": 26, "sebesseg": 500, "ruganyossag": 0.86, "indulas": "fent", "adagolas": 0, "max": 1500},
     "szabalyok": [{"mikor": "labda_fal", "mit": "osztodik", "ertek": 1.0, "esely": 1, "varakozas": 0.9}],
     "vege": {"mikor": "tulcsordul", "ertek": 1}, "szamlalo": "labdak", "hang": {"hangszer": "marimba", "dallam": "emelkedo"},
     "siker_felirat": "OVERFLOW!", "kudarc_felirat": "IT HELD!", "hianyzik": ""},
    {"cim": "The ball grows every bounce", "kerdes": "Every bounce = bigger", "hossz": 30, "paletta": "tuz", "gravitacio": 0,
     "palya": {"tipus": "kor", "meret": 0.9, "forog": 0, "res": 0, "gyuruk": 1},
     "labdak": {"db": 1, "sugar": 22, "sebesseg": 800, "ruganyossag": 1.0, "indulas": "kozep", "adagolas": 0, "max": 5},
     "szabalyok": [{"mikor": "labda_fal", "mit": "no", "ertek": 1.07, "esely": 1, "varakozas": 0.05},
                   {"mikor": "labda_fal", "mit": "szinvalt", "ertek": 1, "esely": 1, "varakozas": 0.05}],
     "vege": {"mikor": "betelt", "ertek": 0.8}, "szamlalo": "utkozesek", "hang": {"hangszer": "zongora", "dallam": "fur_elise"},
     "latvany": {"stilus": "neon", "nyom": True},
     "siker_felirat": "FULL!", "kudarc_felirat": "SO CLOSE", "hianyzik": ""},
    {"cim": "Can one ball escape 3 rings?", "kerdes": "Can it escape?", "hossz": 35, "paletta": "szivarvany", "gravitacio": 500,
     "palya": {"tipus": "gyuru", "meret": 0.95, "forog": 55, "res": 32, "gyuruk": 3},
     "labdak": {"db": 1, "sugar": 16, "sebesseg": 600, "ruganyossag": 1.0, "indulas": "kozep", "adagolas": 0, "max": 60},
     "szabalyok": [{"mikor": "labda_fal", "mit": "osztodik", "ertek": 1.0, "esely": 0.5, "varakozas": 1.2}],
     "vege": {"mikor": "kijut", "ertek": 1}, "szamlalo": "labdak", "hang": {"hangszer": "boing", "dallam": "hegyi_kiraly"},
     "latvany": {"stilus": "tele", "nyom": True},
     "siker_felirat": "ESCAPED!", "kudarc_felirat": "TRAPPED", "hianyzik": ""},
    {"cim": "1000 balls vs the peg board", "kerdes": "Pure chaos", "hossz": 28, "paletta": "jeg", "gravitacio": 1100,
     "palya": {"tipus": "szogtabla", "meret": 0.95, "forog": 0, "res": 0, "gyuruk": 1},
     "labdak": {"db": 0, "sugar": 13, "sebesseg": 60, "ruganyossag": 0.6, "indulas": "fent", "adagolas": 14, "max": 900},
     "szabalyok": [{"mikor": "labda_akadaly", "mit": "szinvalt", "ertek": 1, "esely": 1, "varakozas": 0.1}],
     "vege": {"mikor": "ido", "ertek": 0}, "szamlalo": "utkozesek", "hang": {"hangszer": "harang", "dallam": "meret", "zene": "trend"},
     "siker_felirat": "", "kudarc_felirat": "", "hianyzik": ""},
    {"cim": "The arena shrinks on every hit", "kerdes": "The walls close in", "hossz": 30, "paletta": "mono", "gravitacio": 0,
     "palya": {"tipus": "kor", "meret": 1.0, "forog": 0, "res": 0, "gyuruk": 1},
     "labdak": {"db": 6, "sugar": 30, "sebesseg": 700, "ruganyossag": 1.0, "indulas": "szorva", "adagolas": 0, "max": 60},
     "szabalyok": [{"mikor": "labda_fal", "mit": "palya_szukul", "ertek": 0.988, "esely": 1, "varakozas": 0.2},
                   {"mikor": "labda_labda", "mit": "szinvalt", "ertek": 1, "esely": 1, "varakozas": 0.1}],
     "vege": {"mikor": "betelt", "ertek": 0.45}, "szamlalo": "utkozesek", "hang": {"hangszer": "pop", "dallam": "meret", "zene": "trend"},
     "siker_felirat": "CRUSHED!", "kudarc_felirat": "SURVIVED", "hianyzik": ""},
]


SZAMOS_VEG = ("kijut", "tulcsordul", "labdaszam")


def _szam(x, also, felso, alap):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return alap
    return alap if math.isnan(x) else max(also, min(felso, x))


def tisztit(spec):
    """A (modelltől jövő) SPEC biztonságos, futtatható formára hozása: hiányzó mezők pótlása, értékhatárok."""
    s = dict(spec or {})
    p, l, v = dict(s.get("palya") or {}), dict(s.get("labdak") or {}), dict(s.get("vege") or {})
    tipus = p.get("tipus") if p.get("tipus") in PALYAK else "kor"
    ki = {"cim": str(s.get("cim") or "Physics simulation").strip()[:90],
          "kerdes": str(s.get("kerdes") or s.get("cim") or "").strip()[:48],
          "hossz": int(_szam(s.get("hossz"), 15, 55, 30)),
          "paletta": s.get("paletta") if s.get("paletta") in PALETTAK else "neon",
          "gravitacio": _szam(s.get("gravitacio"), 0, 2200, 900),
          "palya": {"tipus": tipus, "meret": _szam(p.get("meret"), 0.35, 1.0, 0.85),
                    "forog": _szam(p.get("forog"), -240, 240, 0) if tipus != "pohar" and tipus != "szogtabla" else 0,
                    "res": _szam(p.get("res"), 12, 120, 35), "gyuruk": int(_szam(p.get("gyuruk"), 1, 4, 1))},
          "labdak": {"db": int(_szam(l.get("db"), 0, 80, 1)), "sugar": _szam(l.get("sugar"), 7, 110, 22),
                     "sebesseg": _szam(l.get("sebesseg"), 0, 1400, 500), "ruganyossag": _szam(l.get("ruganyossag"), 0.2, 1.05, 0.9),
                     "indulas": l.get("indulas") if l.get("indulas") in ("kozep", "fent", "szorva") else "kozep",
                     "adagolas": _szam(l.get("adagolas"), 0, 40, 0), "max": int(_szam(l.get("max"), 1, MAX_LABDA, 1200))},
          "szabalyok": [], "vege": {"mikor": v.get("mikor") if v.get("mikor") in VEGE else "ido", "ertek": _szam(v.get("ertek"), 0, 5000, 1)},
          "szamlalo": s.get("szamlalo") if s.get("szamlalo") in SZAMLALO else "labdak",
          "hang": _hang_tisztit(s.get("hang")),
          "latvany": {"stilus": (s.get("latvany") or {}).get("stilus") if isinstance(s.get("latvany"), dict)
                      and s["latvany"].get("stilus") in ("tele", "neon") else "tele",
                      "nyom": bool((s.get("latvany") or {}).get("nyom", True)) if isinstance(s.get("latvany"), dict) else True},
          "siker_felirat": str(s.get("siker_felirat") or "").strip().upper()[:18],
          "kudarc_felirat": str(s.get("kudarc_felirat") or "").strip().upper()[:18],
          "hianyzik": str(s.get("hianyzik") or "").strip()[:300], "tempo": _szam(s.get("tempo"), 0.1, 10, 1.0), "elemek": [],
          "majdnem_felirat": str(s.get("majdnem_felirat") or "ALMOST...").strip().upper()[:16],
          "recept": str(s.get("recept") or "")[:40], "kerdes_sablon": str(s.get("kerdes_sablon") or "")[:60],
          "tulcs2": bool(s.get("tulcs2")) and tipus == "pohar"}
    ismert = {e["azon"] for e in elemek() if e.get("allapot") == "aktiv"} | set(s.get("_elem_fajlok") or {})
    for e in (s.get("elemek") or [])[:3]:
        if isinstance(e, dict) and e.get("azon") in ismert:
            ki["elemek"].append({"azon": e["azon"], "p": {str(k)[:30]: (v if isinstance(v, (int, float, bool)) else str(v)[:60])
                                                          for k, v in list((e.get("p") or {}).items())[:12]}})
    if s.get("_elem_fajlok"):
        ki["_elem_fajlok"] = dict(s["_elem_fajlok"])
    hatar = {"osztodik": (0.5, 1.0, 1.0), "no": (1.005, 1.5, 1.06), "zsugorodik": (0.5, 0.995, 0.9), "gyorsul": (0.7, 1.3, 1.05),
             "res_no": (0.5, 20, 3), "palya_szukul": (0.9, 0.999, 0.985), "palya_no": (1.001, 1.1, 1.01)}
    for r in (s.get("szabalyok") or [])[:5]:
        if r.get("mikor") in MIKOR and r.get("mit") in MIT:
            a, f, d = hatar.get(r["mit"], (0, 10, 1))
            ki["szabalyok"].append({"mikor": r["mikor"], "mit": r["mit"], "ertek": _szam(r.get("ertek"), a, f, d),
                                    "esely": _szam(r.get("esely"), 0.02, 1, 1) or 1,
                                    "varakozas": _szam(r.get("varakozas"), 0.03, 10, 0.5)})
    if ki["labdak"]["db"] == 0 and ki["labdak"]["adagolas"] == 0:
        ki["labdak"]["db"] = 1
    # a végfeltétel illjen a pályához (a modell néha zárt körre kér túlcsordulást)
    veg = ki["vege"]["mikor"]
    if veg == "tulcsordul" and tipus != "pohar" or veg == "kijut" and tipus not in ("gyuru", "szogtabla", "pohar"):
        ki["vege"] = {"mikor": "betelt" if tipus in ("kor", "doboz") else "ido", "ertek": 0.75}
    # "csak N maradjon" nem jöhet el, ha a szabályok csak szaporítanak (mérés: 2500 labda, 3,6 millió ütközés, csattanó
    # nélkül) – ilyenkor a pályához illő elérhető csattanó lesz belőle
    szaporit = any(r["mit"] in ("osztodik", "uj_labda") for r in ki["szabalyok"]) or ki["labdak"]["adagolas"] > 0
    fogyaszt = any(r["mit"] in ("eltunik", "zsugorodik") for r in ki["szabalyok"])
    if ki["vege"]["mikor"] == "utolso" and szaporit and not fogyaszt:
        ki["vege"] = ({"mikor": "kijut", "ertek": 20} if tipus == "gyuru" else {"mikor": "tulcsordul", "ertek": 1} if tipus == "pohar"
                      else {"mikor": "betelt", "ertek": 0.7} if tipus in ("kor", "doboz") else {"mikor": "labdaszam", "ertek": ki["labdak"]["max"]})
    if ki["vege"]["mikor"] == "labdaszam":
        ki["vege"]["ertek"] = max(2, min(ki["labdak"]["max"], int(ki["vege"]["ertek"])))
    if ki["vege"]["mikor"] == "betelt":
        ki["vege"]["ertek"] = _szam(ki["vege"]["ertek"], 0.25, 0.9, 0.75)
    elif ki["vege"]["mikor"] in ("tulcsordul", "kijut", "utolso"):
        ki["vege"]["ertek"] = max(1, int(ki["vege"]["ertek"]))
    return _logika(ki)


def _logika(ki):
    """A terv belső LOGIKÁJA (a modell gyakran következetlen): a fizika, a szabályok, a csattanó, a számláló és a kérdés
    illeszkedjen egymáshoz. Mérés (éles gyártás): "Can 400 play the song?" kérdés labdaszám-véggel, rés, amin a labda
    nem fér ki, egymást kioltó szabályok, zárt pályán szökés mint csattanó."""
    p, l, tipus, veg = ki["palya"], ki["labdak"], ki["palya"]["tipus"], ki["vege"]["mikor"]
    R = p["meret"] * R_MAX
    # -- méretek: a labda férjen el és látsszon
    if tipus == "pohar":
        l["sugar"] = min(l["sugar"], R * 0.82 / 4)
        ki["gravitacio"] = max(ki["gravitacio"], 500)
    elif tipus == "gyuru":
        belso = R / p["gyuruk"]
        l["sugar"] = max(8, min(l["sugar"], belso / 3.2))                        # a legbelső gyűrűben is mozogjon
        p["res"] = max(p["res"], math.degrees(2 * math.asin(min(0.95, (l["sugar"] * 2.6) / (2 * belso)))))  # a rés ne legyen szűkebb a labdánál
        if p["forog"] == 0:
            p["forog"] = 45
        l["indulas"] = "kozep"
    elif tipus in ("kor", "doboz"):
        l["sugar"] = min(l["sugar"], R / 3)
    elif tipus == "szogtabla":
        l["sugar"] = min(l["sugar"], 20)
        ki["gravitacio"] = max(ki["gravitacio"], 700)
        l["indulas"] = "fent"
        if l["adagolas"] == 0:
            l["adagolas"] = 8
    if ki["gravitacio"] == 0:
        l["sebesseg"] = max(l["sebesseg"], 320)      # súlytalanul csak a sebesség mozgat
        l["ruganyossag"] = max(l["ruganyossag"], 0.98)
    # a labdakeret akkora, amennyi olvashatóan elfér (terület alapján)
    terulet = {"pohar": (2 * R * 0.82) * (2 * R * 1.05), "doboz": 4 * R * R}.get(tipus, math.pi * R * R)
    ki["labdak"]["max"] = int(max(1, min(l["max"], MAX_LABDA, 1.15 * terulet / (math.pi * max(MIN_SUGAR, l["sugar"] * 0.75) ** 2))))
    # -- szabályok: egymást kioltó párok, ismétlések
    lattam, tiszta = set(), []
    ellentet = {"no": "zsugorodik", "zsugorodik": "no", "palya_szukul": "palya_no", "palya_no": "palya_szukul"}
    for r in ki["szabalyok"]:
        if (r["mikor"], r["mit"]) in lattam or any(x["mit"] == ellentet.get(r["mit"]) for x in tiszta):
            continue
        if r["mit"] == "res_no" and tipus != "gyuru" or r["mikor"] == "labda_akadaly" and tipus != "szogtabla" \
                or r["mikor"] == "kilep" and tipus not in ("pohar", "gyuru", "szogtabla"):
            continue  # ezen a pályán ez sosem történne meg
        if r["mit"] == "osztodik" and tipus == "pohar":
            r["ertek"] = 1.0  # a pohár csak azonos méretű utódokkal telik meg
        if r["mit"] in ("osztodik", "uj_labda") and r["mikor"] in ("labda_labda", "labda_fal"):
            r["varakozas"] = max(r["varakozas"], 0.25)  # különben egy pillanat alatt elszabadul
        lattam.add((r["mikor"], r["mit"]))
        tiszta.append(r)
    ki["szabalyok"] = tiszta
    # -- a csattanó illjen a pályához és a szabályokhoz
    szaporit = any(r["mit"] in ("osztodik", "uj_labda") for r in tiszta) or l["adagolas"] > 0
    no = any(r["mit"] == "no" for r in tiszta) or any(r["mit"] == "palya_szukul" for r in tiszta)
    if veg == "betelt" and not (szaporit or no):
        ki["vege"] = {"mikor": "ido", "ertek": 0}
    if veg == "labdaszam" and not szaporit:
        ki["vege"] = {"mikor": "betelt", "ertek": 0.7} if no and tipus in ("kor", "doboz") else {"mikor": "ido", "ertek": 0}
    if veg == "kijut" and tipus == "pohar":
        ki["vege"]["mikor"] = "tulcsordul"
    veg = ki["vege"]["mikor"]
    # -- a számláló azt mutassa, amiről a csattanó szól
    ki["szamlalo"] = {"kijut": "kijutottak", "tulcsordul": "labdak", "labdaszam": "labdak", "utolso": "labdak"}.get(
        veg, ki["szamlalo"] if ki["szamlalo"] != "kijutottak" or tipus in ("gyuru", "pohar", "szogtabla") else "utkozesek")
    # -- a kérdésben lévő szám = a csattanó küszöbe
    if veg in SZAMOS_VEG:
        szamok = _re.findall(r"(?<![\d.,])\d+(?![\d.,])", ki["kerdes"])
        if len(szamok) == 1 and int(szamok[0]) != int(ki["vege"]["ertek"]) and int(szamok[0]) > 1:
            ki["vege"]["ertek"] = max(1, min(MAX_LABDA, int(szamok[0])))
    # -- feliratok: ne maradjon üresen
    alap = {"tulcsordul": ("OVERFLOW!", "IT HELD!"), "kijut": ("ESCAPED!", "TRAPPED!"), "labdaszam": ("MADE IT!", "NOT ENOUGH"),
            "betelt": ("FULL!", "SO CLOSE"), "utolso": ("LAST ONE!", "TOO MANY")}.get(veg)
    if alap:
        ki["siker_felirat"], ki["kudarc_felirat"] = ki["siker_felirat"] or alap[0], ki["kudarc_felirat"] or alap[1]
    ki["hossz"] = int(max(20, min(45, ki["hossz"])))
    # dallam csak kevés labdánál hallható ki; sok labdánál skála / méret szerinti hang
    if ki["labdak"]["max"] > 150 and ki["hang"]["dallam"] not in ("emelkedo", "meret", "veletlen"):
        ki["hang"]["dallam"] = "emelkedo"
    return ki


# ---------------------------------------------------------------- a szimuláció

class Szim:
    """Egy futás adott maggal. lep() egy képkockányit léptet; az állapot kirajzolható (rajz())."""

    def __init__(self, spec, mag):
        import pymunk

        self.pm, self.s, self.rnd = pymunk, spec, random.Random(mag)
        self.ter = pymunk.Space()
        self.ter.gravity = (0, spec["gravitacio"])
        self.ter.iterations = 12
        self.t, self.labdak, self.hangok = 0.0, [], []       # hangok: (idő, fajta, méret 0..1)
        self.utkozes, self.kint, self.vege_ido, self.adag = 0, 0, None, 0.0
        self.szinek = self.paletta = self.szinei = PALETTAK[spec["paletta"]][3]
        self.R = spec["palya"]["meret"] * R_MAX
        self.res = spec["palya"]["res"]
        self.testek, self.szogek, self._esem, self._kezd = [], [], [], []
        self.kov_ido = [r["varakozas"] * spec["tempo"] for r in spec["szabalyok"]]
        # 🥤 túlcsordulás 2.0
        self.v2 = bool(spec.get("tulcs2")) and spec["palya"]["tipus"] == "pohar"
        self.lassit, self._lassu_kezd, self.lefolyo, self.lefolyo_ido, self.szelesitve = 1.0, None, False, 0.0, False
        self.also, self.forrasok, self.szorzo, self.be_db, self.ki_db = [], [], 1, 0, 0
        self.reszesedes, self.vezeto, self.vezetovaltas, self.gyoztes, self.tores, self.eso_ido = [0.5, 0.5], None, 0, None, False, None
        self.lendulet = (0, 0.0, 3.5)   # (csapat, eddig gyors, következő váltás ideje)
        self.fordulatok, self.fordulat_felirat, self.kov_fordulat, self.forras_cd, self.turbo_ig = [], None, 6.0, 0.0, -1.0
        self._forras_allo, self.utolso_esemeny, self.uresjarat, self.haladas_max = 0.0, 0.0, 0.0, 0.0
        self.lefolyo_w = spec["labdak"]["sugar"] * 5.0
        self._palya_epit()
        for a, b, fajta in ((1, 2, "labda_fal"), (1, 1, "labda_labda"), (1, 3, "labda_akadaly"), (5, 1, "forras_labda"), (5, 2, "forras_fal")):
            self.ter.on_collision(a, b, begin=lambda arb, ter, adat, f=fajta: self._esem.append((f, arb.shapes)))
        if self.v2:
            self.ter.sleep_time_threshold = 0.5   # a kupacban nyugvó labdák "megfagynak" (gyorsabb, és nem osztódnak)
            self._forras_uj()
        for _ in range(0 if getattr(self, "v2", False) else spec["labdak"]["db"]):   # 🥤 2.0: csak a forrás-labda indul
            self._uj_labda()
        # tanult építőelemek (bővítmények): saját állapot, horgok
        self.allapot, self.felirat, self.extra, self.elem_hivas, self._kenyszer_vege = {}, None, [], 0, False
        self.latv, self.fal_villan, self._reszlep, self._max_bent = [], {}, 2, 1   # látvány-események (képkockánként), falak villanása
        self.elemek = [(elem_betolt(e["azon"], (spec.get("_elem_fajlok") or {}).get(e["azon"])), e["p"]) for e in spec.get("elemek") or []]
        for h, p in self.elemek:
            if "indul" in h:
                h["indul"](self, p)

    # -- a bővítmények API-ja (ezeket hívhatja egy tanult építőelem)
    def uj_labda(self, hely=None, sugar=None, seb=None, szin=None):
        self.elem_hivas += 1
        return self._uj_labda(hely, sugar, seb, szin)

    def torol(self, al):
        self.elem_hivas += 1
        self._torol(al)

    def atmeretez(self, al, r):
        self.elem_hivas += 1
        if al in self.labdak:
            self._atmeretez(al, max(MIN_SUGAR, min(R_MAX, float(r))))

    def uj_fal(self, pontok, forog=0, kozep=None):
        """Új fal(ak) a megadott pontokon át (a `kozep`-hez képesti koordináták); forog: fok/mp. Visszaadja a testet."""
        pm = self.pm
        self.elem_hivas += 1
        t = pm.Body(body_type=pm.Body.KINEMATIC)
        t.position = kozep or (KX, KY)
        t.angular_velocity = math.radians(forog)
        alakok = []
        for a, b in zip(list(pontok)[:200], list(pontok)[1:201]):
            al = pm.Segment(t, tuple(a), tuple(b), 7)
            al.elasticity, al.friction, al.collision_type = 1.0, 0.0, 2
            alakok.append(al)
        self.ter.add(t, *alakok)
        self.extra.append((t, alakok))
        return t

    def uj_szog(self, x, y, r=13):
        self.elem_hivas += 1
        al = self.pm.Circle(self.ter.static_body, max(4, min(120, r)), (x, y))
        al.elasticity, al.friction, al.collision_type = 0.9, 0.0, 3
        self.ter.add(al)
        self.szogek.append(al)
        return al

    def hang(self, meret=0.5):
        self.elem_hivas += 1
        self.hangok.append((self.t, "ut", max(0.0, min(1.0, meret)), 0.8))

    def vege_jelez(self):
        self.elem_hivas += 1
        self._kenyszer_vege = True

    # -- pálya
    def _szakaszok(self):
        """[(szögsebesség fok/s, [(a, b)…])] – testenként a falak szakaszai a pálya közepéhez képest."""
        p, R = self.s["palya"], self.R
        if p["tipus"] == "pohar":
            w, h = R * 0.82, R * 1.05
            if not getattr(self, "v2", False):
                return [(0, [((-w, -h), (-w, h)), ((-w, h), (w, h)), ((w, h), (w, -h))])]
            g = self.lefolyo_w / 2
            alj = [((-w, h), (-g, h)), ((g, h), (w, h))] if self.lefolyo else [((-w, h), (w, h))]
            x0, x1, y0, y1 = 36 - KX, SZ - 36 - KX, ALSO_TETO - KY, ALSO_ALJ - KY
            also = (0, [((x0, y0), (x0, y1)), ((x0, y1), (x1, y1)), ((x1, y1), (x1, y0))])
            if self.tores:   # szétrobbant: csak az alsó pohár marad
                return [also]
            return [(0, [((-w, -h), (-w, h))] + alj + [((w, h), (w, -h))]), also]
        if p["tipus"] in ("doboz", "ures"):
            w, h = (R, R) if p["tipus"] == "doboz" else (SZ / 2 - 8, M / 2 - 8)
            return [(p["forog"] if p["tipus"] == "doboz" else 0,
                     [((-w, -h), (w, -h)), ((w, -h), (w, h)), ((w, h), (-w, h)), ((-w, h), (-w, -h))])]
        if p["tipus"] == "szogtabla":
            w, h = R, R * 1.25
            return [(0, [((-w, -h), (-w, h)), ((w, -h), (w, h))])]
        gyuruk = p["gyuruk"] if p["tipus"] == "gyuru" else 1
        ki = []
        for g in range(gyuruk):
            r = R * (g + 1) / gyuruk
            res = math.radians(self.res) if p["tipus"] == "gyuru" else 0
            n = max(24, int(r / 5))
            if g >= len(self._kezd):  # a rés kezdőszöge gyűrűnként egyszer dől el (újraépítéskor ugyanaz marad)
                self._kezd.append(self.rnd.uniform(0, math.tau) if p["tipus"] == "gyuru" else 0)
            kezd = self._kezd[g]
            pontok = [(r * math.cos(kezd + res / 2 + (math.tau - res) * i / n), r * math.sin(kezd + res / 2 + (math.tau - res) * i / n))
                      for i in range(n + 1)]
            irany = 1 if g % 2 == 0 else -1
            ki.append((p["forog"] * irany * (1 + 0.25 * (gyuruk - 1 - g)), list(zip(pontok, pontok[1:]))))
        return ki

    def _palya_epit(self):
        pm = self.pm
        szogek = [t.angle for t, _ in self.testek]
        for t, alakok in self.testek:
            self.ter.remove(t, *alakok)
        self.testek = []
        szak = self._szakaszok()
        for i, (forog, szakaszok) in enumerate(szak):
            t = pm.Body(body_type=pm.Body.KINEMATIC)
            t.position = (KX, KY)
            t.angular_velocity = math.radians(forog)
            if i < len(szogek):
                t.angle = szogek[i]
            alakok = []
            for a, b in szakaszok:
                al = pm.Segment(t, a, b, 7)
                al.elasticity, al.friction, al.collision_type = 1.0, 0.0, 2
                alakok.append(al)
            self.ter.add(t, *alakok)
            self.testek.append((t, alakok))
        if self.s["palya"]["tipus"] == "szogtabla" and not self.szogek:
            w, h = self.R, self.R * 1.25
            for sor in range(9):
                n = 7 if sor % 2 == 0 else 6
                for j in range(n):
                    x = KX - w + (j + (0.5 if sor % 2 == 0 else 1.0)) * (2 * w / 7)
                    al = pm.Circle(self.ter.static_body, 13, (x, KY - h * 0.62 + sor * (h * 1.5 / 9)))
                    al.elasticity, al.friction, al.collision_type = 0.9, 0.0, 3
                    self.ter.add(al)
                    self.szogek.append(al)

    def _terulet(self):
        tip = self.s["palya"]["tipus"]
        if tip == "pohar":
            return (2 * self.R * 0.82) * (2 * self.R * 1.05)
        if tip == "doboz":
            return 4 * self.R * self.R
        return math.pi * self.R * self.R

    # -- labdák
    def _uj_labda(self, hely=None, sugar=None, seb=None, szin=None):
        pm, l = self.pm, self.s["labdak"]
        if len(self.labdak) >= l["max"]:
            return None
        r = sugar or l["sugar"]
        if hely is None:
            mod = l["indulas"]
            if mod == "fent":
                hely = (KX + self.rnd.uniform(-0.45, 0.45) * self.R, KY - self.R * (1.2 if self.s["palya"]["tipus"] != "kor" else 0.5))
            elif mod == "szorva":   # ne szülessen labda egy másikba (különben az első pillanatban ütköznek)
                for _ in range(25):
                    sz, d = self.rnd.uniform(0, math.tau), self.rnd.uniform(0, 0.75) * self.R
                    hely = (KX + d * math.cos(sz), KY + d * math.sin(sz))
                    if all(math.hypot(hely[0] - a.body.position.x, hely[1] - a.body.position.y) > r + a.radius + 4 for a in self.labdak):
                        break
            else:
                hely = (KX + self.rnd.uniform(-8, 8), KY + self.rnd.uniform(-8, 8))
        if seb is None:
            sz = self.rnd.uniform(0, math.tau)
            seb = (l["sebesseg"] * math.cos(sz), l["sebesseg"] * math.sin(sz))
        t = pm.Body(1, pm.moment_for_circle(1, 0, r))
        t.position, t.velocity = hely, seb
        al = pm.Circle(t, r)
        al.elasticity, al.friction, al.collision_type = l["ruganyossag"], 0.0, 1
        al.szin = self.rnd.randrange(len(self.szinek)) if szin is None else szin
        al.cd, al.kint, al.adat, al.also, al.olvad = {}, False, {}, False, False
        self.ter.add(t, al)
        self.labdak.append(al)
        if getattr(self, "v2", False):
            self.be_db += 1
            self.utolso_esemeny = self.t
        return al

    # -- 🥤 túlcsordulás 2.0: PIROS vs KÉK – két forrás-labda, mindegyik a saját színét szórja
    def _forras_uj(self):
        pm, r = self.pm, self.s["labdak"]["sugar"] * 1.6
        for j, dx in enumerate((-0.4, 0.4)):
            t = pm.Body(1, pm.moment_for_circle(1, 0, r))
            t.position = (KX + dx * self.R * 0.82, KY + self.R * 0.3)
            t.velocity = (self.rnd.uniform(-120, 120), 0)
            al = pm.Circle(t, r)
            al.elasticity, al.friction, al.collision_type = 0.5, 0.0, 5
            al.szin, al.cd_ = j, 0.0
            self.ter.add(t, al)
            self.forrasok.append(al)

    def _forras_ut(self, fr, kenyszer=False):
        """A forrás-labda a kupacra / a pohár aljára esett: új labdák a csapata színében, és újra feldobódik."""
        if fr not in self.forrasok or self.vege_ido is not None or (self.t < fr.cd_ and not kenyszer):
            return
        turbo = self.t < self.turbo_ig
        # LENDÜLET: 2,5–4 mp-enként az egyik csapat (inkább a vesztésre álló) „begyorsul” -> hullámzik az állás, van vezetőváltás
        tuz = fr.szin == self.lendulet[0] and self.t < self.lendulet[1]
        fr.cd_ = self.t + 0.3 * self.s["tempo"] * (0.5 if turbo else 1)
        x, y = fr.body.position
        r0 = self.s["labdak"]["sugar"]
        n = 3 if self.be_db < 2 else self.szorzo * (3 if tuz else 1)   # robbanásszerű kezdés; lendületben triplán
        for _ in range(n):
            self._uj_labda((x + self.rnd.uniform(-fr.radius, fr.radius), y - fr.radius - r0 - 3), r0,
                           (self.rnd.uniform(-380, 380), -self.rnd.uniform(260, 520)), fr.szin)
        self.hangok.append((self.t, "ut", 0.95, 1.0))
        self.latv.append(("forras", x, y, fr.szin, fr.radius))
        fr.body.activate()
        fr.body.velocity = (self.rnd.uniform(-240, 240), -self.rnd.uniform(620, 790) * (1.1 if turbo else 1) * (0.75 if tuz else 1))

    def _fordulat(self, tipus, felirat=None):
        felirat = felirat or FORDULATOK.get(tipus, "")
        self.fordulatok.append((round(self.t, 2), tipus))
        self.fordulat_felirat = (felirat, self.t, tipus)
        self.hangok.append((self.t, "fordulat", 0.5, 1.0))
        self.latv.append(("fordulat", KX, KY, 0, 0))
        self.utolso_esemeny = self.t
        if tipus == "lefolyo_nyit":
            self.lefolyo, self.lefolyo_ido = True, self.t
            self._palya_epit()
            for a in self.labdak:   # a nyugvó (alvó) labdák is induljanak meg a lyuk felé
                a.body.activate()
        elif tipus == "lefolyo_zar":
            self.lefolyo = False
            self._palya_epit()
        elif tipus == "szelesit":
            self.szelesitve = True
            self.R = min(R_MAX * 0.98, self.R * 1.1)
            self._palya_epit()
            for a in self.labdak:
                a.body.activate()
        elif tipus == "eso":
            self.eso_ido = self.t + 0.7   # előbb 0,7 mp villogó figyelmeztetés, aztán jön a labdaeső
        elif tipus == "turbo":
            self.turbo_ig = self.t + 3.0
        elif tipus == "csere":   # a vezető csapat labdáinak ~30%-a átszíneződik: megfordulhat az állás
            vez = 0 if self.reszesedes[0] >= self.reszesedes[1] else 1
            for a in self.labdak:
                if not a.kint and a.szin % 2 == vez and self.rnd.random() < 0.3:
                    a.szin = 1 - vez
                    self.latv.append(("oszt", a.body.position.x, a.body.position.y, a.szin, a.radius))

    def _v2_lep(self, dt):
        """Képkockánként: forrás-labdák, szorzó, csapat-arány és vezetőváltás, fordulatok, lassítás, alsó pohár."""
        h = self.haladas()
        self.haladas_max = max(self.haladas_max, h or 0)
        w = self.R * 0.82
        for fr in self.forrasok:
            x, y = fr.body.position
            vx, vy = fr.body.velocity
            if abs(x - KX) > w - fr.radius - 6 and (x - KX) * vx > 0:   # a perem fölött sem repülhet ki (láthatatlan fal)
                fr.body.velocity = (-vx * 0.8, vy)
            fr.allo = (getattr(fr, "allo", 0.0) + dt) if fr.body.velocity.length < 80 else 0.0
            if fr.allo > 0.3:   # beszorult a kupacba: magától újra feldobódik
                fr.allo = 0.0
                self._forras_ut(fr, kenyszer=True)
            if y > KY + self.R * 1.05 + 40 or y < -400 or not (0 < x < SZ):   # kiesett (pl. a lefolyón): vissza a pohárba
                fr.body.position, fr.body.velocity = (KX, KY - self.R * 0.8), (0, 0)
        # csapat-arány (a pohárban lévő labdák) és vezetőváltás (hiszterézissel)
        db = [0, 0]
        for a in self.labdak:
            if not a.kint:
                db[a.szin % 2] += 1
        ossz = max(1, db[0] + db[1])
        self.reszesedes = [db[0] / ossz, db[1] / ossz]
        if ossz >= 12:
            elol = 0 if db[0] > db[1] else 1
            if self.vezeto is None:
                self.vezeto = elol
            elif elol != self.vezeto and self.reszesedes[elol] > 0.52:
                self._vezet_jelolt = getattr(self, "_vezet_jelolt", 0.0) + dt
                if self._vezet_jelolt > 0.4 and self.vege_ido is None:
                    self.vezeto, self._vezet_jelolt = elol, 0.0
                    self.vezetovaltas += 1
                    self.utolso_esemeny = self.t
                    self.hangok.append((self.t, "vezet", 0.5, 1.0))
                    ff = self.fordulat_felirat
                    if not ff or self.t - ff[1] > 1.2:
                        self.fordulat_felirat = (f"{CSAPAT_NEV[elol]} TAKES THE LEAD!", self.t, "vezet")
            else:
                self._vezet_jelolt = 0.0
        if self.t >= self.lendulet[2] and self.vege_ido is None:
            hatul = 0 if self.reszesedes[0] < self.reszesedes[1] else 1
            cs = hatul if self.rnd.random() < 0.75 else 1 - hatul
            self.lendulet = (cs, self.t + self.rnd.uniform(2.0, 3.0), self.t + self.rnd.uniform(3.0, 4.2))
            ff = self.fordulat_felirat
            if self.t > 3 and (not ff or self.t - ff[1] > 1.4):
                self.fordulat_felirat = (f"{CSAPAT_NEV[cs]} IS ON FIRE!", self.t, "tuz")
        if self.eso_ido is not None and self.t >= self.eso_ido:
            self.eso_ido = None
            r0 = self.s["labdak"]["sugar"]
            for i in range(10):
                self._uj_labda((KX + self.rnd.uniform(-0.7, 0.7) * w, KY - self.R * 1.05 - 60 - i * 26), r0,
                               (self.rnd.uniform(-80, 80), 200), i % 2)
        if self.vege_ido is None and h is not None:
            uj = 1 if h < 0.45 else 2 if h < 0.75 else 4
            if uj > self.szorzo:
                self.szorzo = uj
                self._fordulat("szorzo", f"x{uj} BALLS!")
            # fordulat 3–4 mp-enként (a végső rohamban már nem); a lefolyó csak közel a peremhez nyílik, és rövid ideig
            if self.t >= self.kov_fordulat and self.t < self.s["hossz"] - 4 and h < 0.88:
                if self.lefolyo:
                    tip = "lefolyo_zar"
                elif h > 0.62 and self.t - self.lefolyo_ido > 6:
                    tip = "lefolyo_nyit"
                elif h > 0.5 and not self.szelesitve and self.rnd.random() < 0.5:
                    tip = "szelesit"
                else:
                    tip = self.rnd.choice(["eso", "turbo", "csere", "csere"])
                self._fordulat(tip)
                self.kov_fordulat = self.t + (self.rnd.uniform(2.4, 3.0) if tip == "lefolyo_nyit" else self.rnd.uniform(3.0, 4.0))
        # LASSÍTÁS a perem előtt (legfeljebb 3 mp), a csattanó után vissza
        cel = 1.0
        if self.vege_ido is None and (h or 0) >= 0.9:
            if self._lassu_kezd is None:
                self._lassu_kezd = self.t
            if self.t - self._lassu_kezd < 3.0:
                cel = 0.45
        elif self.vege_ido is not None and self.t - self.vege_ido < 0.8:
            cel = 0.45
        self.lassit += (cel - self.lassit) * 0.12
        # 💥 a csattanó után 0,5 mp-cel a pohár SZÉTRobban: a falai eltűnnek, a labdák az alsó pohárba zúdulnak
        if self.vege_ido is not None and not self.tores and self.t - self.vege_ido > 0.5 and self.gyoztes is not None:
            self.tores = True
            w_, h_ = self.R * 0.82, self.R * 1.05
            self.latv.append(("tores", KX, KY, self.gyoztes, self.R))
            self.hangok.append((self.t, "tores", 1.0, 1.0))
            self._palya_epit()
            for a in self.labdak:
                a.body.activate()
                a.body.velocity = (a.body.velocity.x + (a.body.position.x - KX) * 1.4, a.body.velocity.y - self.rnd.uniform(0, 260))
        # az alsó pohár: a legrégebbi labdák elolvadnak, hogy elférjen az új
        if len(self.also) > ALSO_MAX:
            for a in self.also[: len(self.also) - ALSO_MAX]:
                a.olvad = True
        for a in list(self.also):
            if a.olvad:
                if a.radius * 0.9 < MIN_SUGAR:
                    self.also.remove(a)
                    self.ter.remove(a.body, a)
                else:
                    self._atmeretez(a, a.radius * 0.9)
                    a.body.activate()
        if self.vege_ido is None:
            self.uresjarat = max(self.uresjarat, self.t - self.utolso_esemeny)
        self.felirat = ""

    def _also_be(self, al, lefolyt):
        self.labdak.remove(al)
        al.also = True
        self.also.append(al)
        if lefolyt and not self.tores:
            self.ki_db += 1
            self.hangok.append((self.t, "le", 0.5, 0.6))

    def _torol(self, al):
        if al in self.labdak:
            self.labdak.remove(al)
            self.ter.remove(al.body, al)

    def _atmeretez(self, al, r):
        al.unsafe_set_radius(r)
        al.body.moment = self.pm.moment_for_circle(1, 0, r)

    def _tesz(self, r, al):
        """Egy szabály hatása (al: az érintett labda, vagy None a globális hatásoknál)."""
        mit, e = r["mit"], r["ertek"]
        if mit == "uj_labda":
            self._uj_labda()
        elif mit == "res_no":
            self.res = min(170, self.res + e)
            self._palya_epit()
        elif mit in ("palya_szukul", "palya_no"):
            self.R = max(0.22 * R_MAX, min(R_MAX, self.R * e))
            self._palya_epit()
        elif al is None or al not in self.labdak:
            return
        elif mit == "osztodik":
            rr = al.radius * e
            v = al.body.velocity
            if len(self.labdak) < self.s["labdak"]["max"] and rr >= MIN_SUGAR:
                self._atmeretez(al, rr)
                sz = self.rnd.uniform(0.35, 0.7)
                al.body.velocity = v.rotated(sz)
                uj = self._uj_labda((al.body.position.x + self.rnd.uniform(-2, 2), al.body.position.y - 1), rr, tuple(v.rotated(-sz)),
                                    al.szin if self.v2 else (al.szin + 1) % len(self.szinek))
                if uj:
                    uj.cd = dict(al.cd)
                    self.latv.append(("oszt", al.body.position.x, al.body.position.y, uj.szin, rr))
        elif mit == "no":
            self._atmeretez(al, min(self.R * 0.98, al.radius * e))
        elif mit == "zsugorodik":
            self._torol(al) if al.radius * e < MIN_SUGAR else self._atmeretez(al, al.radius * e)
        elif mit == "gyorsul":
            v = al.body.velocity * e
            al.body.velocity = v if v.length < 2600 else v.normalized() * 2600
        elif mit == "szinvalt":
            al.szin = (al.szin + 1) % len(self.szinek)
        elif mit == "eltunik":
            self.latv.append(("oszt", al.body.position.x, al.body.position.y, al.szin, al.radius))
            self._torol(al)

    def _szabaly(self, mikor, labdak):
        for i, r in enumerate(self.s["szabalyok"]):
            if r["mikor"] != mikor:
                continue
            for al in labdak:
                if al is not None and (al.kint and mikor != "kilep" or al not in self.labdak):
                    continue
                cd = (al.cd if al is not None else {}).get(i, 0)
                if self.v2 and r["mit"] == "osztodik" and al is not None and al.body.velocity.length < 200:
                    continue   # 🥤 csak a repülő labda osztódik, a kupacban nyugvó nem
                if self.t >= cd and self.rnd.random() < r["esely"]:
                    if al is not None:
                        al.cd[i] = self.t + r["varakozas"] * self.s["tempo"]
                    self._tesz(r, al)

    def lep(self):
        dt, s = 1 / FPS, self.s
        for _ in range(self._reszlep):  # a részlépések száma a leggyorsabb / legkisebb labdához igazodik (ne menjen át a falon)
            self.ter.step(dt * self.lassit / self._reszlep)   # lassit < 1: lassított felvétel (a videó-idő ugyanúgy halad)
        self.t += dt
        esem, self._esem = self._esem, []
        self.latv = []
        latott = set()
        for fajta, alakok in esem[:4000]:
            if fajta.startswith("forras"):
                self.utkozes += 1
                fr = next((a for a in alakok if a.collision_type == 5), None)
                if fr is not None and (fajta == "forras_labda" or fr.body.position.y > KY + self.R * 1.05 - fr.radius - 20):
                    self._forras_ut(fr)
                continue
            lb = [a for a in alakok if a.collision_type == 1]
            if not lb or any(a.kint or a.also for a in lb):
                continue
            self.utkozes += 1
            kulcs = (fajta, id(lb[0]))
            if kulcs in latott:
                continue
            latott.add(kulcs)
            x0, y0 = lb[0].body.position
            ero = min(1.0, lb[0].body.velocity.length / 1400)
            self.hangok.append((self.t, "ut", min(1.0, lb[0].radius / 90), ero))
            if len(self.latv) < 60:
                self.latv.append(("ut", x0, y0, lb[0].szin, lb[0].radius))
            if fajta == "labda_fal":
                fal = next((a for a in alakok if a.collision_type == 2), None)
                if fal is not None:
                    self.fal_villan[fal.body] = (lb[0].szin, self.t)
            self._szabaly(fajta, lb)
            for h, p in self.elemek:
                if "utkozes" in h:
                    h["utkozes"](self, p, fajta, [a for a in lb if a in self.labdak])
        for h, p in self.elemek:
            if "lep" in h:
                h["lep"](self, p, dt)
        # időzített szabályok
        for i, r in enumerate(s["szabalyok"]):
            if r["mikor"] == "idokozonkent" and self.t >= self.kov_ido[i]:
                self.kov_ido[i] = self.t + r["varakozas"] * s["tempo"]
                bent = [a for a in self.labdak if not a.kint]
                if self.rnd.random() < r["esely"]:
                    self._tesz(r, self.rnd.choice(bent) if bent and r["mit"] not in ("uj_labda", "res_no", "palya_szukul", "palya_no") else None)
        # adagolás
        if s["labdak"]["adagolas"] > 0:
            self.adag += s["labdak"]["adagolas"] * dt
            while self.adag >= 1:
                self.adag -= 1
                self._uj_labda()
        # kilépők, lendület
        tip, kilepok = s["palya"]["tipus"], []
        min_seb = s["labdak"]["sebesseg"] * 0.85 if s["gravitacio"] == 0 else 0
        leggyorsabb = 0.0
        for al in list(self.labdak):
            x, y = al.body.position
            leggyorsabb = max(leggyorsabb, al.body.velocity.length / max(MIN_SUGAR, al.radius))
            if not (-200 < x < SZ + 200 and -900 < y < M + 200) or math.isnan(x):
                self._torol(al)
                continue
            if self.v2:   # 🥤 a lefolyón kiesett / túlcsordult labda az alsó pohárba kerül
                if not al.kint and y > KY + self.R * 1.05 + al.radius * 0.6 and (abs(x - KX) < self.R * 0.82 or self.tores):
                    self.latv.append(("le", x, y, al.szin, al.radius))
                    self._also_be(al, True)
                    continue
                if al.kint and y > ALSO_TETO - 60:
                    self._also_be(al, False)
                    continue
                fent = (not al.kint and self.vege_ido is None and y < KY - self.R * 1.05 - al.radius * 0.5
                        and self.t > 4 and abs(x - KX) < self.R * 0.82 and al.body.velocity.length < 220)
                al.fent = (getattr(al, "fent", 0.0) + dt) if fent else 0.0
                if al.fent > 0.5 or fent and al.body.is_sleeping:
                    # a perem FÖLÖTT ül (a kupac kidomborodott): ez már túlcsordulás, legurul az oldalán, ne épüljön torony
                    al.body.activate()
                    irany = 1 if x >= KX else -1
                    al.body.velocity = (irany * self.rnd.uniform(320, 460), -self.rnd.uniform(60, 160))
                    al.kint = True
                    self.kint += 1
                    self.hangok.append((self.t, "ki", 0.5, 1.0))
                    self.latv.append(("ki", x, y, al.szin, al.radius))
            if not al.kint:
                kint = (tip == "pohar" and (abs(x - KX) > self.R * 0.82 + al.radius + 8)
                        or tip == "gyuru" and math.hypot(x - KX, y - KY) > self.R + al.radius + 10
                        or tip == "szogtabla" and y > KY + self.R * 1.25 + al.radius)
                if kint:
                    al.kint = True
                    self.kint += 1
                    kilepok.append(al)
                    self.hangok.append((self.t, "ki", 0.5, 1.0))
                    self.latv.append(("ki", x, y, al.szin, al.radius))
                elif min_seb:
                    v = al.body.velocity
                    if 1e-6 < v.length < min_seb:
                        al.body.velocity = v.normalized() * min_seb
                    elif v.length <= 1e-6:
                        sz = self.rnd.uniform(0, math.tau)
                        al.body.velocity = (min_seb * math.cos(sz), min_seb * math.sin(sz))
        self._reszlep = max(2, min(8, math.ceil(leggyorsabb * dt / 0.6)))
        if self.v2:
            self._v2_lep(dt)
        if kilepok:
            self._szabaly("kilep", kilepok)
        # végfeltétel
        if self.vege_ido is None:
            bent = [a for a in self.labdak if not a.kint]
            v, e = s["vege"]["mikor"], s["vege"]["ertek"]
            if (self._kenyszer_vege or any("vege" in h and h["vege"](self, p) for h, p in self.elemek)
                    or v in ("tulcsordul", "kijut") and not self.v2 and self.kint >= e or v == "labdaszam" and len(self.labdak) >= e
                    or self.v2 and v == "tulcsordul" and self._csapat_kint(e)
                    or v == "betelt" and sum(math.pi * a.radius ** 2 for a in bent) >= e * self._terulet()
                    or v == "utolso" and self.t > 2 and len(bent) <= e):
                self.vege_ido = self.t
                self.hangok.append((self.t, "vege", 1.0, 1.0))
                self.latv.append(("vege", KX, KY, 0, 0))
                for fr in self.forrasok:   # a forrás-labdák szétpukkannak
                    self.latv.append(("forras", fr.body.position.x, fr.body.position.y, fr.szin, fr.radius * 2))
                    self.ter.remove(fr.body, fr)
                self.forrasok = []

    def _csapat_kint(self, e):
        """🥤 PIROS vs KÉK: az a csapat nyer, amelyikből előbb csordul ki e labda (vészfék: ha a kupac 2,5 mp-ig
        a peremen áll, a több kiömlött labdájú csapat nyer)."""
        db = [0, 0]
        for a in self.labdak + self.also:
            if a.kint:
                db[a.szin % 2] += 1
        h = self.haladas() or 0
        self._tetot_ido = (getattr(self, "_tetot_ido", 0.0) + 1 / 60) if h >= 0.98 else 0.0
        if self._tetot_ido > 2.5 and sum(db):
            self.gyoztes = 0 if db[0] >= db[1] else 1
            return True
        for j in (0, 1):
            if db[j] >= e:
                self.gyoztes = j if db[j] >= db[1 - j] else 1 - j
                return True
        return False

    def haladas(self):
        """0..1: mennyire van közel a csattanó (a haladásjelzőhöz); None, ha nincs mihez mérni."""
        v, e = self.s["vege"]["mikor"], self.s["vege"]["ertek"]
        if self.vege_ido is not None:
            return 1.0
        bent = [a for a in self.labdak if not a.kint]
        self._max_bent = max(self._max_bent, len(bent))
        if v == "kijut":
            h = self.kint / max(1, e)
        elif v == "labdaszam":
            h = len(self.labdak) / max(1, e)
        elif v == "betelt":
            h = math.sqrt(sum(math.pi * a.radius ** 2 for a in bent) / max(1.0, e * self._terulet()))  # gyök: egyenletesebben nő
        elif v == "tulcsordul" and self.v2:   # 🥤 a kupac teteje: a lassú labdák felső 6%-ának magassága (a repülők nem számítanak)
            w, hh = self.R * 0.82, self.R * 1.05
            ys = sorted(a.body.position.y - a.radius for a in bent if abs(a.body.position.x - KX) < w and a.body.velocity.length < 150)
            if len(ys) >= 3:
                y_ = ys[min(len(ys) - 1, int(len(ys) * 0.06))]
                h = (KY + hh - y_) / (2 * hh)
            else:
                h = 0.0
        elif v == "tulcsordul":   # a legfelső nyugvó labda magassága a peremhez képest
            teto, alj = KY - self.R * 1.05, KY + self.R * 1.05
            lassu = [a.body.position.y - a.radius for a in bent if a.body.velocity.length < 260 and abs(a.body.position.x - KX) < self.R * 0.82]
            h = (alj - min(lassu)) / (alj - teto) if lassu else 0.0
        elif v == "utolso":
            h = 1 - (len(bent) - e) / max(1, self._max_bent - e)
        else:
            return None
        return max(0.0, min(0.99, h))

    def szamlalo(self):
        if self.felirat is not None:
            return str(self.felirat)[:28]
        return {"labdak": f"BALLS: {len(self.labdak)}", "utkozesek": f"HITS: {self.utkozes}", "kijutottak": f"ESCAPED: {self.kint}",
                "ido": f"{self.t:0.1f} s"}.get(self.s["szamlalo"], "")


def futtat(spec, mag, kepkocka=None, max_mp=None):
    """Egy teljes futás. kepkocka(szim): képkockánként hívódik (rajzoláshoz). Visszaad: mérőszámok + hangesemények."""
    sz = Szim(spec, mag)
    hossz, kezd = spec["hossz"], time.time()
    labda_max, i, tele_ido = 0, 0, None
    idovonal, mp_ut, elso_ut = [], 0, None   # másodpercenként: (idő, bent lévő labdák, ütközések abban a mp-ben, haladás)
    while True:
        elotte = sz.utkozes
        sz.lep()
        i += 1
        mp_ut += sz.utkozes - elotte
        if elso_ut is None and sz.utkozes > 0:
            elso_ut = sz.t
        labda_max = max(labda_max, len(sz.labdak))
        if tele_ido is None and len(sz.labdak) >= spec["labdak"]["max"] > 1:
            tele_ido = sz.t  # elérte a labdakeretet: innen már nem tud tovább fokozódni
        if i % FPS == 0:
            h = sz.haladas()
            idovonal.append((round(sz.t, 2), sum(1 for a in sz.labdak if not a.kint), mp_ut, None if h is None else round(h, 3)))
            mp_ut = 0
        if kepkocka:
            kepkocka(sz)
        if sz.vege_ido is not None and sz.t >= sz.vege_ido + 2.6 and sz.t >= 8 or sz.t >= hossz:
            break
        if max_mp and i % 30 == 0 and time.time() - kezd > max_mp:
            break
    lenyomat = f"{len(sz.labdak)}:{sum(round(a.body.position.x + 3 * a.body.position.y + 7 * a.radius) for a in sz.labdak)}:{sum(a.szin for a in sz.labdak)}"
    return {"mag": mag, "lenyomat": lenyomat, "hossz": round(sz.t, 2), "vege_ido": round(sz.vege_ido, 2) if sz.vege_ido is not None else None,
            "labdak_max": labda_max, "labdak_vege": len(sz.labdak), "tele_ido": tele_ido, "utkozesek": sz.utkozes, "kijutottak": sz.kint, "hangok": sz.hangok, "elem_hivas": sz.elem_hivas,
            "idovonal": idovonal, "elso_utkozes": None if elso_ut is None else round(elso_ut, 2),
            "tulcs2": sz.v2, "fordulatok": len(sz.fordulatok), "fordulat_lista": [t for t, x in sz.fordulatok if x != "szorzo"],
            "uresjarat": round(sz.uresjarat, 2), "be": sz.be_db, "ki": sz.ki_db, "haladas_max": round(sz.haladas_max, 3),
            "vezetovaltas": sz.vezetovaltas, "gyoztes_szin": CSAPAT_NEV[sz.gyoztes] if sz.v2 and sz.gyoztes is not None else None,
            "szamitas_mp": round(time.time() - kezd, 1)}


def minoseg(spec, e):
    """✅ MÉRT minőségkapu egy lefutásra – a renderelés ELŐTT, a valódi eseményekből (nem a koncepció szövegéből).
    Mérés (éles gyártás, 2026-11-10, 38 szimulációs videó, ~30 elvetve): nem jött el a csattanó; 1 labda volt a
    „350 labdás” videóban; 8 mp-es videó (a csattanó a 4. mp-ben); „túl sok labda és hang az elején, nem épít ki
    várakozást”; „nem pattognak elég ideig, hamar unalmas”. Ezeket mind kiszűri. Visszaad: {pont 0–10, jo, hibak}."""
    hibak, pont = [], 10.0
    hossz, veg = spec["hossz"], spec["vege"]["mikor"]
    iv = e.get("idovonal") or []
    if e["hossz"] < 18:
        hibak.append(f"túl rövid ({e['hossz']:.0f} mp)")
        pont -= 4
    tartott = e.get("tulcs2") and e["vege_ido"] is None and (e.get("haladas_max") or 0) >= 0.85 and e["hossz"] >= hossz - 0.5
    if veg != "ido":
        if tartott:
            pass   # 🥤 "IT HELD!" – majdnem túlcsordult, de a lefolyó megmentette: ez is csattanó
        elif e["vege_ido"] is None:
            hibak.append("nem jön el a csattanó")
            pont -= 5
        else:
            arany = e["vege_ido"] / hossz
            if e["vege_ido"] < 15:   # kell ~15 mp felvezetés, különben nincs feszültség (a videó a csattanó után 2,6 mp-cel véget ér)
                hibak.append(f"túl korán jön a csattanó ({e['vege_ido']:.0f}. mp)")
                pont -= 3.5
            elif arany < 0.5:
                hibak.append(f"korán jön a csattanó ({e['vege_ido']:.0f}. mp)")
                pont -= 1
            elif arany > 0.95:
                hibak.append("a csattanó az utolsó pillanatban jön, nincs ideje hatni")
                pont -= 1
    if e["labdak_max"] < 1 or (iv and iv[0][1] == 0 and spec["labdak"]["adagolas"] == 0):
        hibak.append("nincsenek labdák")
        pont -= 6
    szaporit = any(r["mit"] in ("osztodik", "uj_labda") for r in spec["szabalyok"]) or spec["labdak"]["adagolas"] > 0
    if szaporit and e["labdak_max"] < 4:
        hibak.append(f"a szaporodás nem indult be ({e['labdak_max']} labda)")
        pont -= 4
    szamok = [int(x) for x in _re.findall(r"(?<![\d.,])\d+(?![\d.,])", spec.get("kerdes", "")) if int(x) > 1]
    if szamok and veg in SZAMOS_VEG and max(szamok) > max(e["labdak_max"], e["kijutottak"]) * 1.05 + 1:
        hibak.append(f"a kérdésben {max(szamok)} szerepel, de csak {max(e['labdak_max'], e['kijutottak'])} lett")
        pont -= 3
    # HOOK: az első másodpercben már pattanjon (különben a néző továbbgörget)
    if e.get("elso_utkozes") is None or e["elso_utkozes"] > 1.2:
        hibak.append("az első másodpercben nem történik semmi (késik a hook)")
        pont -= 2
    # nyugodt kezdés, fokozódás: az első 3 mp ne legyen káosz
    if len(iv) >= 3:
        eleje_labda = iv[2][1]
        if szaporit and eleje_labda > max(14, 0.3 * e["labdak_max"]) and e["labdak_max"] > 20:
            hibak.append(f"túl sok labda az elején ({eleje_labda} a 3. mp-ben) – nem épít várakozást")
            pont -= 2.5
        eleje_ut = sum(x[2] for x in iv[:3]) / 3
        if eleje_ut > 40:
            hibak.append("túl sok hang az elején")
            pont -= 2.5
    # pattogjon végig: ne legyen néma szakasz, és legyen elég ütközés (a hang a műfaj fele)
    vege_mp = int(e["vege_ido"] or e["hossz"])
    csend, leghosszabb = 0, 0
    for t, _, ut, _ in iv:
        if t > vege_mp:
            break
        csend = csend + 1 if ut == 0 else 0
        leghosszabb = max(leghosszabb, csend)
    if leghosszabb >= 2:
        hibak.append(f"{leghosszabb} mp csend (nem pattog)")
        pont -= 2
    atlag = e["utkozesek"] / max(1.0, e["hossz"])
    if atlag < 1.5:
        hibak.append(f"kevés pattanás ({atlag:.1f}/mp) – unalmas")
        pont -= 2
    # fokozódás: a haladásjelző ne álljon meg félúton sokáig
    hal = [x[3] for x in iv if x[3] is not None and x[0] <= vege_mp]
    if len(hal) >= 8 and veg in ("betelt", "labdaszam") or veg == "kijut" and spec["vege"]["ertek"] >= 5 and len(hal) >= 8:
        allo = max((sum(1 for j in range(i, min(len(hal), i + 8)) if abs(hal[j] - hal[i]) < 0.02) for i in range(len(hal) - 7)), default=0)
        if allo >= 8 and hal[-1] < 0.9:
            hibak.append("a haladás 8+ mp-ig áll – leül a feszültség")
            pont -= 1.5
    if e.get("tulcs2"):   # 🥤 a haladás ne álljon 3 mp-nél tovább (a perem előtti lassítás kivétel)
        hal_ = [(x[0], x[3]) for x in iv if x[3] is not None and x[0] <= vege_mp]
        allo, leg = 0, 0
        for (t0, a), (t1, b) in zip(hal_, hal_[1:]):
            allo = allo + 1 if abs(b - a) < 0.02 and b < 0.88 else 0
            leg = max(leg, allo)
        if leg >= 3:
            hibak.append(f"a haladás {leg} mp-ig áll")
            pont -= 2
    if e.get("tulcs2"):   # 🥤 üresjárat: 2,5 mp-nél tovább se új labda, se fordulat -> leül
        if (e.get("uresjarat") or 0) > 2.5:
            hibak.append(f"{e['uresjarat']:.1f} mp-ig nem történik semmi (üresjárat)")
            pont -= 2
        if (e.get("fordulatok") or 0) < 3:
            hibak.append("kevés fordulat")
            pont -= 1
    pont = round(max(0.0, min(10.0, pont)), 1)
    return {"pont": pont, "jo": pont >= 7.5 and not any(h.startswith(("nem jön", "nincsenek", "a szaporodás")) for h in hibak),
            "hibak": hibak}


def _pont(spec, e):
    """Mennyire jó videó lenne ez a futás: a csattanó a hossz 55–92%-ánál a legjobb, legyen elég esemény – és menjen át
    a mért minőségkapun (minoseg)."""
    hossz = spec["hossz"]
    suruseg = min(1.0, e["utkozesek"] / max(1.0, e["hossz"]) / 3)
    m = minoseg(spec, e)
    e["minoseg"] = m
    kapu = 0.55 + 0.45 * m["pont"] / 10
    if spec["vege"]["mikor"] == "ido":
        return (0.5 + 0.5 * suruseg) * kapu
    if e["vege_ido"] is None:
        if e.get("tulcs2") and m["jo"] and (e.get("haladas_max") or 0) >= 0.85:
            return 0.82 * (0.7 + 0.3 * suruseg) * kapu   # "IT HELD!" – jó, de a túlcsordulás egy hajszállal jobb
        return (0.25 + 0.2 * suruseg) * kapu
    arany = e["vege_ido"] / hossz
    if e.get("tulcs2"):   # 🥤 a túlcsordulás a videó 78–95%-ánál a legjobb (addig tart a feszültség)
        return (1.0 if 0.78 <= arany <= 0.95 else max(0.3, 1 - abs(arany - 0.86) * 2.2)) * (0.7 + 0.3 * suruseg) * kapu
    return (1.0 if 0.55 <= arany <= 0.92 else max(0.3, 1 - abs(arany - 0.75) * 1.6)) * (0.7 + 0.3 * suruseg) * kapu


def valaszt(spec, keret_mp=90, halad=lambda s: None, ellenoriz=lambda: None):
    """Előválogatás rajz nélkül: több mag, és ha kell, HANGOLÁS két karral: (1) a tempó (a szabályok várakozási ideje),
    (2) a darabszámos csattanó küszöbe (hány labda jusson ki / legyen): ha a tempó nem segít. Mérés (éles gyártás,
    2026-11-10): "5 jusson ki" a 4. mp-ben megvolt bármilyen tempóval (8 mp-es videó lett), a "400 labda" pedig elérhetetlen
    volt, mert az osztódás a legkisebb labdaméretnél megáll. Visszaad: (a végső spec, a legjobb futás, napló)."""
    kezd, naplo, legjobb = time.time(), [], None
    spec = dict(spec, vege=dict(spec["vege"]))
    hossz, szamos = spec["hossz"], spec["vege"]["mikor"] in SZAMOS_VEG
    elozo_median, korai_db, elmarad_db = None, 0, 0
    for kor in range(6):
        eredmenyek = []
        for n in range(6):
            ellenoriz()
            if time.time() - kezd > keret_mp and (eredmenyek or legjobb):
                break
            e = futtat(spec, 1000 * kor + n * 7919 + 17, max_mp=max(8, keret_mp / 4))
            e["pont"], e["tempo"], e["vege_ertek"] = round(_pont(spec, e), 3), spec["tempo"], spec["vege"]["ertek"]
            eredmenyek.append(e)
            halad(f"Előválogatás: {kor * 6 + n + 1}. futás (vége: {e['vege_ido'] or '–'} mp, {e['labdak_max']} labda)")
            if e["pont"] >= 0.9 and e["minoseg"]["jo"]:
                break
        if not eredmenyek:
            break
        jo = max(eredmenyek, key=lambda e: e["pont"])
        if legjobb is None or jo["pont"] > legjobb["pont"]:
            legjobb = jo
        naplo.append(f"tempó {spec['tempo']:.2f}, küszöb {spec['vege']['ertek']:g}: {len(eredmenyek)} futás, legjobb pont {jo['pont']}, vége {jo['vege_ido']}")
        if legjobb["pont"] >= 0.8 and legjobb["minoseg"]["jo"] or spec["vege"]["mikor"] == "ido" or time.time() - kezd > keret_mp:
            break
        vegek = sorted(e["vege_ido"] for e in eredmenyek if e["vege_ido"] is not None)
        median = vegek[len(vegek) // 2] if vegek else None
        if len(vegek) >= len(eredmenyek) / 2 and median < 0.55 * hossz:
            # túl hamar jön a csattanó
            korai_db += 1
            javult = elozo_median is None or median > elozo_median * 1.3
            if szamos and (korai_db >= 2 and not javult or spec["tempo"] >= 9.9 or not spec["szabalyok"]):
                # a tempó nem segít: több labdának kell kijutnia / meglennie
                spec["vege"]["ertek"] = min(MAX_LABDA, max(spec["vege"]["ertek"] + 1,
                                                           math.ceil(spec["vege"]["ertek"] * max(1.5, min(6.0, (0.75 * hossz / max(1.0, median)) ** 1.3)))))
            else:
                spec["tempo"] = min(10, spec["tempo"] * max(1.25, min(3.0, 0.75 * hossz / max(1.0, median))))
            elozo_median = median
        elif sum(1 for e in eredmenyek if e["tele_ido"] is not None and e["tele_ido"] < 0.5 * hossz) > len(eredmenyek) / 2:
            spec["tempo"] = min(10, spec["tempo"] * 2.0)  # a csattanó előtt kifogy a labdakeret: lassabb fokozás kell
        else:
            # nem (vagy túl későn) jön
            elmarad_db += 1
            elert = sorted((e["labdak_max"] if spec["vege"]["mikor"] == "labdaszam" else e["kijutottak"]) for e in eredmenyek)
            elert = elert[len(elert) // 2]
            if szamos and not vegek and (elmarad_db >= 2 or spec["tempo"] <= 0.11 or not spec["szabalyok"]) and 2 <= elert < spec["vege"]["ertek"]:
                spec["vege"]["ertek"] = max(1, int(elert * 0.85))  # elérhetetlen küszöb: a ténylegesen elérthez igazítjuk
            else:
                spec["tempo"] = max(0.1, spec["tempo"] * 0.6)
        if not spec["szabalyok"] and not szamos:
            break
    spec["tempo"], spec["vege"]["ertek"] = legjobb["tempo"], legjobb["vege_ertek"]
    return spec, legjobb, naplo


# ---------------------------------------------------------------- hang

def _szinti(hangszer, f, rata=44100):
    """Egy hang (numpy tömb, -1..1) a megadott hangszeren, f Hz alaphanggal. Minden helyben szintetizált."""
    import numpy as np

    def t_(hossz):
        return np.arange(int(hossz * rata)) / rata

    def burok(t, lecseng, felfut=600):
        return np.exp(-t * lecseng) * np.minimum(1, t * felfut)

    def fazis(frek):  # változó frekvenciájú hang fázisa
        return math.tau * np.cumsum(frek) / rata

    def formans(t, f0, formansok):  # összeadó szintézis formánsokkal (kacsa, macska): "orrhangú" hangszín
        ki, fz = np.zeros(len(t)), fazis(f0)
        kozep = float(np.mean(f0))
        for k in range(1, max(2, int(5200 / kozep))):
            suly = sum(a * math.exp(-((k * kozep - fc) / sz) ** 2) for fc, sz, a in formansok)
            if suly > 0.02:
                ki += suly * np.sin(k * fz)
        return ki / max(1e-6, np.abs(ki).max())

    if hangszer == "zongora":
        t = t_(0.75)
        x = sum((1 / k ** 1.3) * np.sin(math.tau * k * f * t) * np.exp(-t * (3.5 + 2 * k)) for k in range(1, 7)) * np.minimum(1, t * 900)
    elif hangszer == "harang":
        t = t_(1.1)
        x = sum(a * np.sin(math.tau * r * f * t) * np.exp(-t * d) for r, a, d in ((1, 1, 4), (2.76, .6, 6), (5.4, .35, 9), (8.93, .2, 12))) * np.minimum(1, t * 900)
    elif hangszer == "xilofon":
        t = t_(0.28)
        x = (np.sin(math.tau * f * t) + .4 * np.sin(math.tau * 3 * f * t) * np.exp(-t * 60) + .2 * np.sin(math.tau * 6.2 * f * t) * np.exp(-t * 80)) * burok(t, 24)
    elif hangszer == "pengetes":   # Karplus–Strong pengetett húr
        n, hossz = max(2, int(rata / f)), int(0.55 * rata)
        rs = np.random.RandomState(int(f))
        puffer, x = rs.uniform(-1, 1, n), np.zeros(hossz)
        for i in range(hossz):
            x[i] = puffer[i % n]
            puffer[i % n] = 0.996 * 0.5 * (puffer[i % n] + puffer[(i + 1) % n])
    elif hangszer == "8bit":
        t = t_(0.2)
        x = np.sign(np.sin(math.tau * f * t)) * burok(t, 13) * 0.55
    elif hangszer == "boing":      # rajzfilmes rugó: a hangmagasság berezeg
        t = t_(0.5)
        fz = fazis(f * 0.7 * (1 + 0.55 * np.exp(-t * 5) * np.sin(math.tau * 17 * t)))
        x = (np.sin(fz) + .3 * np.sin(2 * fz)) * burok(t, 6.5)
    elif hangszer == "pop":
        t = t_(0.09)
        x = np.sin(fazis(f * (0.6 + 1.8 * t / 0.09))) * burok(t, 42, 2000)
    elif hangszer == "buborek":
        t = t_(0.17)
        x = np.sin(fazis(f * (1 + 1.3 * (t / 0.17) ** 2))) * burok(t, 20)
    elif hangszer == "vizcsepp":
        t = t_(0.16)
        x = np.sin(fazis(f * (2.4 * np.exp(-t * 60) + 1 + 0.5 * t / 0.16))) * burok(t, 26)
    elif hangszer == "kacsa":      # háp: orrhangú, lefelé csúszó
        t = t_(0.2)
        x = formans(t, f * 0.6 * (1.1 - 0.25 * t / 0.2), ((1150, 420, 1.0), (2450, 600, 0.7), (300, 200, 0.3)))
        x *= np.minimum(1, t * 250) * np.exp(-t * 9) * (0.8 + 0.2 * np.sin(math.tau * 34 * t))
    elif hangszer == "nyavogas":   # miaú: felfelé majd lefelé hajló, vándorló formánssal
        t = t_(0.45)
        iv = np.sin(math.pi * t / 0.45)
        x = formans(t, f * 0.8 * (0.9 + 0.5 * iv) * (1 + 0.012 * np.sin(math.tau * 6 * t)), ((850 + 500 * float(iv.mean()), 380, 1.0), (2700, 700, 0.6)))
        x *= np.minimum(1, t * 30) * np.minimum(1, (0.45 - t) * 14)
    elif hangszer == "lezer":      # pjú
        t = t_(0.22)
        x = np.tanh(3 * np.sin(fazis(f * (0.8 + 5.2 * np.exp(-t * 16))))) * burok(t, 11) * 0.6
    elif hangszer == "puki":       # mély, berregő, lefelé csúszó
        t = t_(0.34)
        fz = fazis(max(48.0, f * 0.19) * (1.15 - 0.4 * t / 0.34))
        rs = np.random.RandomState(3)
        berreges = 0.55 + 0.45 * np.sign(np.sin(math.tau * 41 * t + 2 * rs.uniform(-1, 1, len(t)).cumsum() / 60))
        x = np.convolve((2 * ((fz / math.tau) % 1) - 1) * berreges, np.ones(10) / 10, "same") * np.minimum(1, t * 120) * np.exp(-t * 5)
    elif hangszer == "bumm":       # mély mém-dörrenés
        t = t_(0.75)
        x = np.tanh(3.2 * np.sin(fazis(max(42.0, f * 0.14) * (1 + 1.3 * np.exp(-t * 28))))) * np.exp(-t * 4.5)
        x[:400] += np.random.RandomState(5).uniform(-1, 1, 400) * np.linspace(0.6, 0, 400)
    elif hangszer == "sip":        # csúszósíp
        t = t_(0.3)
        x = np.sin(fazis(f * (1 + t / 0.3) * (1 + 0.01 * np.sin(math.tau * 9 * t)))) * np.minimum(1, t * 80) * np.minimum(1, (0.3 - t) * 30)
    elif hangszer == "ugras":      # játék-ugrás
        t = t_(0.19)
        x = np.sign(np.sin(fazis(f * 0.7 * (1 + 1.9 * t / 0.19)))) * burok(t, 9) * 0.5
    elif hangszer == "koppanas":
        t = t_(0.06)
        x = (np.random.RandomState(7).uniform(-1, 1, len(t)) * np.exp(-t * 95) + 0.5 * np.sin(math.tau * f * 2 * t) * np.exp(-t * 60)) * 0.8
    elif hangszer == "harsona":    # a "szomorú harsona" egy hangja (kudarcnál)
        t = t_(0.5)
        fz = fazis(f * (1 - 0.06 * t / 0.5) * (1 + 0.012 * np.sin(math.tau * 5.5 * t)))
        x = sum(np.sin(k * fz) / k for k in range(1, 9)) * np.minimum(1, t * 40) * np.minimum(1, (0.5 - t) * 12) * 0.5
    else:                          # marimba
        t = t_(0.38)
        x = (np.sin(math.tau * f * t) + .25 * np.sin(math.tau * 4 * f * t) * np.exp(-t * 40) + .08 * np.sin(math.tau * 10 * f * t) * np.exp(-t * 90)) * burok(t, 16)
    cs = float(np.abs(x).max()) or 1.0
    return (x / cs).astype(np.float32)


def _sajat_hang(nev, rata=44100):
    """Saját hangfájl a hangmappából (mono, legfeljebb 1,5 mp, az eleji csend levágva) – vagy None."""
    import numpy as np

    fajl = next((os.path.join(HANG_MAPPA, f) for f in sorted(os.listdir(HANG_MAPPA)) if os.path.splitext(f)[0] == nev), None) \
        if os.path.isdir(HANG_MAPPA) else None
    if not fajl:
        return None
    r = subprocess.run([FFMPEG, "-v", "error", "-i", fajl, "-ac", "1", "-ar", str(rata), "-t", "4", "-f", "f32le", "-"], capture_output=True, timeout=60)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    if len(x) < 200:
        return None
    eleje = int(np.argmax(np.abs(x) > 0.02 * float(np.abs(x).max())))
    x = x[eleje:eleje + int(1.5 * rata)].copy()
    x[-min(len(x), 2000):] *= np.linspace(1, 0, min(len(x), 2000))
    return x / (float(np.abs(x).max()) or 1.0)


def _meme_minta(nev, rata=44100, hossz=0.42):
    """Egy mém-hang rövid, ütős változata pattanáshoz: a csend levágva, a hossz-ra vágva, kiúsztatva."""
    import numpy as np

    x = _sajat_hang(nev, rata)
    if x is None:
        return None, None
    rovid = x[:int(hossz * rata)].copy()
    n = min(len(rovid), int(0.08 * rata))
    rovid[-n:] *= np.linspace(1, 0, n)
    return rovid, x


def merfoldkovek(idovonal, hangok):
    """A „nagy pillanatok” ideje (mém-hanghoz sok labdánál): az első pattanás, a labdaszám duplázódásai (2, 4, 8 …
    csak 8 fölött minden második), a haladás 25 / 50 / 75%-a és minden kijutás (ritkítva)."""
    ki, kov, lepcso = [], 2, 0
    elso = next((h[0] for h in hangok if h[1] == "ut"), None)
    if elso is not None:
        ki.append(elso)
    for t, bent, _, hal in idovonal:
        while bent >= kov:
            lepcso += 1
            if kov <= 8 or lepcso % 2 == 0:
                ki.append(t - 0.5)
            kov *= 2
    kuszob = [0.25, 0.5, 0.75]
    for t, _, _, hal in idovonal:
        while kuszob and hal is not None and hal >= kuszob[0]:
            ki.append(t - 0.3)
            kuszob.pop(0)
    utolso = -9
    for h in hangok:
        if h[1] == "ki" and h[0] - utolso > 0.6:
            ki.append(h[0])
            utolso = h[0]
    ki = sorted(set(round(max(0.0, t), 2) for t in ki))
    ritkitott = []
    for t in ki:
        if not ritkitott or t - ritkitott[-1] > 0.9:
            ritkitott.append(t)
    return ritkitott


def _reteg(buf, rata, hangok, hossz, idovonal, inger, tulcs2, jegy, rak):
    """🥤 Hangrétegek: (inger-módban) halk phonk-szerű ütem a pattanások alatt, ami 50% fölött tapssal sűrűsödik;
    (túlcsordulás 2.0) szívverés 70% fölött (egyre gyorsabb), emelkedő zúgás az utolsó 4 mp-ben, basszus-drop a csattanón."""
    import numpy as np

    vege = next((h[0] for h in hangok if h[1] == "vege"), None)
    meddig = vege if vege is not None else hossz

    def hal(t):   # a haladás az idővonalból (másodpercenként), lineárisan
        pts = [(x[0], x[3]) for x in idovonal if x[3] is not None]
        if not pts:
            return 0.0
        for (t0, h0), (t1, h1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                return h0 + (h1 - h0) * (t - t0) / max(1e-6, t1 - t0)
        return pts[-1][1] if t > pts[-1][0] else pts[0][1]
    rng = np.random.default_rng(9)
    if inger:   # ütem: 140 BPM lábdob + nyolcados lábcin, 50% fölött taps a 2-re és a 4-re
        ut_ = 60 / 140
        lab = jegy(-14, "bumm")[: int(0.25 * rata)]
        L_ = int(0.04 * rata)
        cin = (rng.uniform(-1, 1, L_) * np.exp(-np.linspace(0, 9, L_))).astype(np.float32)
        cin = cin - np.concatenate([[0], cin[:-1]]).astype(np.float32)
        L2 = int(0.12 * rata)
        taps = (rng.uniform(-1, 1, L2) * np.exp(-np.linspace(0, 6, L2))).astype(np.float32)
        t, n = 0.4, 0
        while t < meddig + 0.4:
            if n % 2 == 0:
                rak(t, lab, 0.32)
            rak(t, cin, 0.10)
            if n % 4 == 2 and hal(t) >= 0.5:
                rak(t, taps, 0.22)
            t += ut_ / 2
            n += 1
    if tulcs2:
        t = None   # szívverés 70% fölött: kettős dobbanás, a periódus 0,8 -> 0,38 mp
        tt = 0.0
        while tt < meddig:
            h = hal(tt)
            if h >= 0.7:
                per = 0.8 - 0.42 * min(1.0, (h - 0.7) / 0.3)
                rak(tt, jegy(-16, "bumm")[: int(0.18 * rata)], 0.45)
                rak(tt + 0.14, jegy(-16, "bumm")[: int(0.14 * rata)], 0.3)
                tt += per
            else:
                tt += 0.1
        if vege is not None:   # zúgás az utolsó 4 mp-ben + basszus-drop
            L_ = int(min(4.0, vege) * rata)
            tv = np.linspace(0, 1, L_, dtype=np.float32)
            frek = 180 + 900 * tv ** 2
            fazis = np.cumsum(frek / rata) * math.tau
            zug = (0.6 * np.sin(fazis) + 0.4 * rng.uniform(-1, 1, L_)) * tv ** 2 * 0.22
            rak(vege - L_ / rata, zug.astype(np.float32), 1.0)
            L2 = int(1.3 * rata)
            tb = np.arange(L2) / rata
            drop = (np.sin(math.tau * 52 * tb) * np.exp(-tb * 2.6)).astype(np.float32) * 0.8
            rak(vege, drop, 1.0)


INGER_SZAVAK = ["BONK!", "BRUH", "SIGMA", "RIZZ", "OHIO", "YEET", "SHEESH", "AURA +100", "NO WAY", "SKIBIDI", "W", "MEWING",
                "BOING", "GOOFY", "BRAINROT", "SUS", "BUSSIN", "NPC", "TUNG TUNG", "TRALALERO", "BOMBARDIRO", "OIIA"]
INGER_KOZ = 0.14   # INGER-mód: két brainrot-hang (és a hozzá tartozó vizuális inger) között legalább ennyi mp


def hang_ir(hangok, hossz, hang, ut, kudarc_ido=None, idovonal=None, labdak_max=0, tulcs2=False):
    """A hangesemények (ütközés / kilépés / vég) hanggá. hang = {hangszer, dallam}: minden ütközés egy hang a választott
    hangszeren (dallamos vagy vicces effekt – az is hangolva van), a dallam hangjai sorban jönnek. A sikeres csattanó
    fanfárt kap, a kudarc (kudarc_ido) "szomorú harsonát"."""
    import numpy as np

    rata = 44100
    hang = _hang_tisztit(hang)
    hangszer, dallam = hang["hangszer"], DALLAMOK[hang["dallam"]]
    buf = np.zeros(int((hossz + 1.5) * rata), dtype=np.float32)
    tar, sajat = {}, None
    if hangszer.startswith("sajat:"):
        try:
            sajat = _sajat_hang(hangszer[6:], rata)
        except Exception as hiba:
            print("[SZIMULÁCIÓ] saját hang hiba:", hiba, flush=True)
        if sajat is None:
            hangszer = "marimba"

    def jegy(felhang, hsz=None):
        hsz = hsz or hangszer
        felhang = max(-14, min(28, felhang))
        k = (hsz, felhang)
        if k not in tar:
            if hsz.startswith("sajat:") and sajat is not None:   # a saját hang hangolása újramintavételezéssel
                arany = 2 ** (max(-9, min(12, felhang)) / 12)
                tar[k] = np.interp(np.arange(0, len(sajat) - 1, arany), np.arange(len(sajat)), sajat).astype(np.float32)
            else:
                tar[k] = _szinti(hsz, 392.0 * 2 ** (felhang / 12), rata)
        return tar[k]

    def rak(t, h, ero):
        i = int(t * rata)
        if 0 <= i < len(buf):
            veg = min(len(buf), i + len(h))
            buf[i:veg] += h[:veg - i] * ero

    meme_rovid = meme_teljes = None
    if hang.get("meme") not in (None, "nincs", "trend"):
        try:
            meme_rovid, meme_teljes = _meme_minta(hang["meme"], rata)
        except Exception as hiba:
            print("[SZIMULÁCIÓ] mém-hang hiba:", hiba, flush=True)
    inger = []   # 🧠 INGER-mód: a brainrot mém-hangok rövid, ütős változatai (pattanásonként váltakozva)
    if hang.get("inger"):
        for m in hang.get("memek") or []:
            try:
                r_, _ = _meme_minta(m, rata, hossz=0.5)
            except Exception as hiba:
                print("[SZIMULÁCIÓ] inger-hang hiba:", m, hiba, flush=True)
                r_ = None
            if r_ is not None:
                inger.append(r_)
    meme_mod = hang.get("meme_mod", "auto")
    if inger:
        meme_mod = "inger"
    elif meme_mod == "auto":
        meme_mod = "pattanas" if labdak_max <= 14 else "merfoldko"
    meme_tar = {}

    def meme_jegy(felhang):
        felhang = max(-5, min(7, felhang))
        if felhang not in meme_tar:
            arany = 2 ** (felhang / 12)
            meme_tar[felhang] = np.interp(np.arange(0, len(meme_rovid) - 1, arany), np.arange(len(meme_rovid)), meme_rovid).astype(np.float32)
        return meme_tar[felhang]

    if hangszer != "nincs" or meme_rovid is not None or inger:
        pent = [0, 2, 4, 7, 9]
        rs = random.Random(11)
        hosszu = len(jegy(0)) > 0.3 * rata
        min_koz = 1 / 14 if hosszu and hangszer in VICCES else 1 / 22 if hosszu else 1 / 34   # különben zajjá olvad
        utolso, n, meme_utolso = -1.0, 0, -9.0
        alap_halk = 0.6 if meme_rovid is not None and meme_mod == "pattanas" else 0.4 if inger else 1.0
        ri, inger_db, le_utolso = random.Random(23), 0, -9.0
        for esem in hangok:
            t, fajta, meret = esem[0], esem[1], esem[2]
            ero = esem[3] if len(esem) > 3 else 0.7
            if fajta == "ut":
                if t - utolso < min_koz:
                    continue
                utolso = t
                if hang["dallam"] == "meret":
                    lep_ = int((1 - meret) * 9)
                    felhang = pent[lep_ % 5] + 12 * (lep_ // 5) - 5
                elif hang["dallam"] == "veletlen":
                    felhang = rs.choice(pent) + 12 * rs.randrange(0, 2)
                else:
                    felhang = dallam[n % len(dallam)]
                    n += 1
                if hangszer != "nincs":
                    rak(t, jegy(felhang), (0.2 + 0.22 * ero) * alap_halk)
                # 😂 mém-hang a pattanásra (kevés labdánál minden pattanás, ritkítva, a dallam szerint hangolva)
                if inger and t - meme_utolso >= INGER_KOZ:   # 🧠 minden pattanásra brainrot-hang (váltakozva, kicsit hangolva)
                    meme_utolso = t
                    h_ = inger[inger_db % len(inger)]
                    inger_db += 1
                    f_ = ri.choice((-2, 0, 0, 2, 3))
                    if f_:
                        h_ = np.interp(np.arange(0, len(h_) - 1, 2 ** (f_ / 12)), np.arange(len(h_)), h_).astype(np.float32)
                    rak(t, h_, 0.5 + 0.25 * ero)
                elif meme_rovid is not None and meme_mod == "pattanas" and t - meme_utolso >= 0.2:
                    meme_utolso = t
                    rak(t, meme_jegy(felhang - 4 if hang["dallam"] not in ("meret", "veletlen") else 0), 0.42 + 0.25 * ero)
            elif fajta == "ki":
                rak(t, jegy(12, "buborek"), 0.4)
            elif fajta == "le":   # 🥤 a lefolyón kiesett labda
                if t - le_utolso >= 0.09:
                    le_utolso = t
                    rak(t, jegy(-5, "buborek"), 0.22)
            elif fajta == "vezet":   # 🥤 vezetőváltás: suhanás felfelé
                for j, x in enumerate((0, 4, 7)):
                    rak(t + 0.04 * j, jegy(x + 5, "8bit"), 0.22)
            elif fajta == "tores":   # 💥 a pohár szétrobban: üvegcsörömpölés-szerű zaj + dörrenés
                L_ = int(0.7 * rata)
                zaj = np.random.default_rng(3).uniform(-1, 1, L_).astype(np.float32)
                zaj = (zaj - np.concatenate([[0], zaj[:-1]])) * np.exp(-np.linspace(0, 7, L_)).astype(np.float32) * 0.5
                rak(t, zaj, 1.0)
                rak(t, jegy(-9, "bumm"), 0.7)
            elif fajta == "fordulat":   # 🥤 fordulat: dörrenés + mém-hang
                rak(t, jegy(-7, "bumm"), 0.55)
                if inger:
                    rak(t + 0.03, inger[(inger_db + 3) % len(inger)], 0.75)
                elif meme_teljes is not None:
                    rak(t + 0.03, meme_teljes[: int(0.9 * rata)], 0.6)
                else:
                    for j, x in enumerate((0, 7, 12)):
                        rak(t + 0.05 * j, jegy(x, "8bit"), 0.3)
            elif fajta == "vege":   # fanfár: felbontott akkord + mély dörrenés
                for j, x in enumerate((0, 4, 7, 12, 16)):
                    rak(t + 0.07 * j, jegy(x, "harang"), 0.3)
                    rak(t + 0.07 * j, jegy(x, "zongora"), 0.25)
                rak(t, jegy(0, "bumm"), 0.55)
                if meme_teljes is not None:   # a csattanóra a teljes mém-hang
                    rak(t + 0.05, meme_teljes, 0.75)
        if meme_rovid is not None and meme_mod == "merfoldko":   # sok labdánál: mém a nagy pillanatokra
            for t in merfoldkovek(idovonal or [], hangok):
                rak(t, meme_rovid, 0.7)
        if tulcs2 or inger:
            _reteg(buf, rata, hangok, hossz, idovonal or [], inger, tulcs2, jegy, rak)
        if kudarc_ido is not None:   # szomorú harsona: négy lefelé lépő hang
            for j, x in enumerate((-2, -3, -4, -5)):
                h = jegy(x, "harsona")
                rak(kudarc_ido + 0.42 * j, np.tile(h, 2)[:int(len(h) * (1.9 if j == 3 else 1))] if j == 3 else h, 0.5)
        # enyhe tér (két rövid visszaverődés), majd hangerő: a műfaj hangos és telt
        for kesl, ero in ((0.031, 0.16), (0.053, 0.1)):
            d = int(kesl * rata)
            buf[d:] += buf[:-d] * ero
        cs = float(np.sqrt((buf[np.abs(buf) > 1e-4] ** 2).mean())) if np.any(np.abs(buf) > 1e-4) else 0
        if cs > 0:
            buf = np.tanh(buf * min(6.0, 0.16 / cs)) * 0.92
    with wave.open(ut, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rata)
        w.writeframes((buf * 32767).astype("<i2").tobytes())


# ---------------------------------------------------------------- rajz + videó

def _rgb(szin):
    szin = szin.lstrip("#")
    return tuple(int(szin[i:i + 2], 16) for i in (0, 2, 4))


def _kever(a, b, m):
    """a és b szín keveréke (m = 0: a, m = 1: b)."""
    return (int(a[0] + (b[0] - a[0]) * m), int(a[1] + (b[1] - a[1]) * m), int(a[2] + (b[2] - a[2]) * m))


class Rajzolo:
    """A látvány: ragyogó, ütéskor felvillanó falak, fényes vagy neon labdák, halványuló nyomvonal, részecskék,
    haladásjelző a csattanóig, és villanás + rázkódás a csattanónál. (Átlátszóság nélkül, a háttérszínbe kevert
    színekkel rajzol – így sok labdánál is gyors.)"""

    def __init__(self, spec, veg_felirat=None, zene_terv=None):
        from PIL import Image, ImageChops, ImageDraw, ImageFont

        self.Image, self.ImageDraw, self.ImageChops = Image, ImageDraw, ImageChops
        self.k = RAJZ_SKALA
        self.W, self.H = int(SZ * self.k) // 2 * 2, int(M * self.k) // 2 * 2
        hatter1, hatter2, self.vilagos, self.szinek = PALETTAK[spec["paletta"]]
        self.hatter = Image.linear_gradient("L").resize((self.W, self.H))
        self.hatter = Image.composite(Image.new("RGB", (self.W, self.H), hatter2), Image.new("RGB", (self.W, self.H), hatter1), self.hatter)
        self.sotet = hatter1
        self.bg = _kever(_rgb(hatter1), _rgb(hatter2), 0.5)
        self.vil, self.rgb = _rgb(self.vilagos), [_rgb(c) for c in self.szinek]
        self.spec, self.veg_felirat = spec, veg_felirat
        self.neon = spec.get("latvany", {}).get("stilus") == "neon"
        self.nyom_kell = bool(spec.get("latvany", {}).get("nyom", True))
        self.nyomok, self.reszecskek, self.razas, self.villanas = {}, [], 0.0, 0.0
        self.rnd = random.Random(5)
        # 🎧 a zene DROPJA és ütemei (trendhang.drop_terv): a dropnál robban a kép, utána ütemre lüktet
        zt = zene_terv or {}
        self.drop = zt.get("drop")
        self.utemek = list(zt.get("utemek") or [])
        self.drop_volt, self.pulzus, self.utem_i = False, 0.0, 0
        # 🧠 INGER-mód: minden brainrot-hangos pattanásnál lökéshullám, szikra, mini-rázkódás, színvillanás, néha felirat
        self.v2 = bool(spec.get("tulcs2"))
        self.felirat_y = 570 if self.v2 else 1745   # 🥤 lent a második pohár van: a feliratok a pohár fölé kerülnek
        if self.v2:   # 🥤 PIROS vs KÉK: a labdák a csapatuk színében; élő kamera; veszély-jelzés
            self.szinek = list(CSAPAT_SZIN)
            self.rgb = [_rgb(c) for c in CSAPAT_SZIN]
            self.cam_z, self.cam_y, self.punch, self.elso_kep = 1.0, None, 0.0, None
            self.vignetta = Image.radial_gradient("L").resize((self.W, self.H))   # közép 0, szélek 255
        self.majdnem_kuszob = 0.9 if self.v2 else 0.72
        self.forras_puls = 0.0
        self.inger = bool((spec.get("hang") or {}).get("inger"))
        self.inger_utolso, self.inger_db = -9.0, 0
        self.hullamok, self.szavak, self.inger_villan = [], [], 0.0
        self.inger_szin = self.rgb[0]

        def betu(m):
            try:
                return ImageFont.truetype(BETU, int(m * self.k))
            except Exception:
                return ImageFont.load_default()
        self.b_kerdes, self.b_szam, self.b_veg, self.b_kis = betu(84), betu(54), betu(128), betu(40)
        # a kérdés tördelése legfeljebb 3 sorba
        d = ImageDraw.Draw(self.hatter)
        szavak, sorok, sor = spec["kerdes"].split(), [], ""
        for sz in szavak:
            if sor and d.textlength(f"{sor} {sz}", font=self.b_kerdes) > self.W * 0.88:
                sorok.append(sor)
                sor = sz
            else:
                sor = f"{sor} {sz}".strip()
        self.sorok = (sorok + [sor])[:3] if sor or sorok else []
        self.hatter_ures = self.hatter.copy()   # kérdés nélkül: az első pillanatokban a kérdés "beugrik" (hook)
        self.majdnem_volt, self.majdnem_ido = False, None
        for i, s in enumerate(self.sorok):  # a kérdés állandó: a háttérre kerül, nem rajzoljuk képkockánként
            d.text((self.W / 2, (165 + i * 98) * self.k), s, font=self.b_kerdes, fill=self.vilagos, anchor="mm",
                   stroke_width=int(5 * self.k), stroke_fill=self.sotet)
        self.sav_y = 165 + len(self.sorok) * 98 + 5

    def _szikra(self, x, y, szin, db, ero=1.0):
        for _ in range(db):
            if len(self.reszecskek) > 700:
                break
            sz, v = self.rnd.uniform(0, math.tau), self.rnd.uniform(120, 620) * ero
            self.reszecskek.append([x, y, v * math.cos(sz), v * math.sin(sz) - 150, self.rnd.uniform(0.35, 0.8), 0.0, szin, self.rnd.uniform(4, 10)])

    def kep(self, sz):
        k, dt = self.k, 1 / FPS
        BEUGRAS = 0.35
        kep = (self.hatter if sz.t >= BEUGRAS else self.hatter_ures).copy()
        d = self.ImageDraw.Draw(kep)
        if sz.t < BEUGRAS and self.sorok:
            # HOOK: a kérdés az első képkockán nagyban beugrik, és rugózva áll be (a néző azonnal tudja, mit néz)
            x = sz.t / BEUGRAS
            sk = 1 + 0.45 * (1 - x) ** 2 * math.cos(x * 7)
            betu = self.b_kerdes.font_variant(size=max(10, int(84 * k * sk)))
            for i, s in enumerate(self.sorok):
                d.text((self.W / 2, (165 + i * 98) * k), s, font=betu, fill=self.vilagos, anchor="mm",
                       stroke_width=int(5 * k), stroke_fill=self.sotet)
        n = len(sz.labdak)
        # --- események -> részecskék, villanás, rázkódás
        for fajta, x, y, szin, r in sz.latv:
            c = self.rgb[szin % len(self.rgb)]
            if fajta == "ut" and n <= 160:
                self._szikra(x, y, c, 2, 0.5)
            elif fajta == "oszt":
                self._szikra(x, y, c, 7 if n < 400 else 2, 0.8)
            elif fajta == "ki":
                self._szikra(x, y, c, 14)
            elif fajta == "forras":   # 🥤 a forrás-labda becsapódik: szikraeső + lüktetés
                self._szikra(x, y, self.vil, 10 if r < 80 else 60, 1.0 if r < 80 else 1.8)
                self.forras_puls = 1.0
            elif fajta == "le":
                self._szikra(x, y, c, 3, 0.4)
            elif fajta == "fordulat":
                self.villanas, self.razas = max(self.villanas, 0.07), max(self.razas, 0.22)
                self.punch = 1.0
            elif fajta == "tores":   # 💥 a pohár szétrobban: szilánkok a falak mentén + konfetti
                w_, h_ = r * 0.82, r * 1.05
                for _ in range(70):
                    oldal = self.rnd.choice((-1, 1))
                    self._szikra(KX + oldal * w_, KY + self.rnd.uniform(-h_, h_), self.vil, 1, 1.7)
                for _ in range(40):
                    self._szikra(KX + self.rnd.uniform(-w_, w_), KY + h_, self.vil, 1, 1.5)
                for _ in range(160):
                    self._szikra(KX + self.rnd.uniform(-w_, w_), KY - h_ + self.rnd.uniform(0, 200), self.rnd.choice(
                        [self.rgb[szin % 2], (255, 220, 60), (255, 255, 255)]), 1, 2.2)
                self.razas, self.villanas, self.punch = 0.6, 0.2, 1.4
            elif fajta == "vege":
                self.razas, self.villanas = 0.5, 0.16
                for _ in range(90):
                    self._szikra(KX + self.rnd.uniform(-300, 300), KY + self.rnd.uniform(-300, 300), self.rnd.choice(self.rgb), 1, 1.6)
        if self.inger:
            for fajta, x, y, szin, r in sz.latv:
                if fajta != "ut" or sz.t - self.inger_utolso < INGER_KOZ:
                    continue
                self.inger_utolso = sz.t
                self.inger_db += 1
                c = self.rgb[szin % len(self.rgb)]
                self.hullamok.append([x, y, sz.t, c, max(18.0, r)])
                self._szikra(x, y, c, 8, 0.9)
                self.razas = max(self.razas, 0.07)
                self.inger_villan, self.inger_szin = 1.0, c
                if self.inger_db % 2 == 1:   # felirat a pattanás mellett
                    self.szavak.append([x + self.rnd.uniform(-60, 60), y - 70 - self.rnd.uniform(0, 50), sz.t,
                                        self.rnd.choice(INGER_SZAVAK), c, self.rnd.uniform(-12, 12)])
            del self.hullamok[:-14], self.szavak[:-5]
        # --- DROP: villanás, rázkódás, minden labdából szikrák, középről lökéshullám; utána ütemre lüktet a kép
        if self.drop is not None and not self.drop_volt and sz.t >= self.drop and sz.vege_ido is None:
            self.drop_volt = True
            self.razas, self.villanas = max(self.razas, 0.6), max(self.villanas, 0.22)
            for a in sz.labdak[:: max(1, len(sz.labdak) // 45)]:
                self._szikra(a.body.position.x, a.body.position.y, self.rgb[getattr(a, "szin", 0) % len(self.rgb)], 3, 1.3)
            for _ in range(70):
                self._szikra(KX, KY, self.rnd.choice(self.rgb), 1, 2.2)
            self.pulzus = 1.6
        if self.drop_volt:
            while self.utem_i < len(self.utemek) and self.utemek[self.utem_i] <= sz.t + 1e-6:
                if self.utemek[self.utem_i] > self.drop + 0.05:
                    self.pulzus = max(self.pulzus, 1.0)
                self.utem_i += 1
        # --- falak: halvány ragyogás + mag; ütéskor a labda színében villan
        fal = int(14 * k)
        for t, alakok in sz.testek + sz.extra:
            szin = self.vil
            v = sz.fal_villan.get(t)
            if v:
                e = 1 - (sz.t - v[1]) / 0.3
                if e > 0:
                    szin = _kever(self.vil, self.rgb[v[0] % len(self.rgb)], min(1.0, e * 1.2))
            ragyog = _kever(self.bg, szin, 0.22)
            pontok = [(t.local_to_world(al.a), t.local_to_world(al.b)) for al in alakok]
            for a, b in pontok:
                d.line((a.x * k, a.y * k, b.x * k, b.y * k), fill=ragyog, width=int(fal * 2.6))
            for a, b in pontok:
                d.line((a.x * k, a.y * k, b.x * k, b.y * k), fill=szin, width=fal)
                d.ellipse((a.x * k - fal / 2, a.y * k - fal / 2, a.x * k + fal / 2, a.y * k + fal / 2), fill=szin)
            if pontok:
                b = pontok[-1][1]
                d.ellipse((b.x * k - fal / 2, b.y * k - fal / 2, b.x * k + fal / 2, b.y * k + fal / 2), fill=szin)
        for al in sz.szogek:
            x, y, r = al.offset.x * k, al.offset.y * k, al.radius * k
            d.ellipse((x - r * 1.5, y - r * 1.5, x + r * 1.5, y + r * 1.5), fill=_kever(self.bg, self.vil, 0.2))
            d.ellipse((x - r, y - r, x + r, y + r), fill=self.vil)
        # --- nyomvonal (kevés labdánál): halványuló, szűkülő csík a labda mögött
        if self.nyom_kell and n <= 70:
            elo = set()
            for al in sz.labdak:
                elo.add(id(al))
                ny = self.nyomok.setdefault(id(al), [])
                ny.append((al.body.position.x, al.body.position.y))
                if len(ny) > 14:
                    del ny[0]
                c, m = self.rgb[al.szin % len(self.rgb)], len(ny)
                for i, (x, y) in enumerate(ny[:-1]):
                    r = al.radius * (0.25 + 0.65 * i / m) * k
                    d.ellipse((x * k - r, y * k - r, x * k + r, y * k + r), fill=_kever(self.bg, c, 0.08 + 0.4 * i / m))
            if len(self.nyomok) > 200:
                self.nyomok = {i: v for i, v in self.nyomok.items() if i in elo}
        # --- részecskék
        if self.reszecskek:
            marad = []
            for p in self.reszecskek:
                p[5] += dt
                if p[5] >= p[4]:
                    continue
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[3] += 900 * dt
                e = 1 - p[5] / p[4]
                r = p[7] * e * k
                d.ellipse((p[0] * k - r, p[1] * k - r, p[0] * k + r, p[1] * k + r), fill=_kever(self.bg, p[6], 0.25 + 0.75 * e))
                marad.append(p)
            self.reszecskek = marad
        # --- labdák
        kontur = max(1, int(2 * k))
        arany = self.v2 and sz.szorzo >= 4 and sz.vege_ido is None
        for al in sz.labdak + getattr(sz, "also", []):
            x, y, r = al.body.position.x * k, al.body.position.y * k, al.radius * k
            c = self.rgb[al.szin % len(self.rgb)]
            if arany and not al.also:   # x4: arany glória a pohárban lévő labdákon
                d.ellipse((x - r * 1.18, y - r * 1.18, x + r * 1.18, y + r * 1.18), fill=_kever(self.bg, (255, 200, 40), 0.55))
            if n <= 90:   # ragyogás
                d.ellipse((x - r * 1.32, y - r * 1.32, x + r * 1.32, y + r * 1.32), fill=_kever(self.bg, c, 0.26))
            if self.neon:
                d.ellipse((x - r, y - r, x + r, y + r), fill=_kever(self.bg, c, 0.12), outline=c, width=max(2, int(r * 0.24)))
            else:
                d.ellipse((x - r, y - r, x + r, y + r), fill=c, outline=self.sotet if r > 6 * k else None, width=kontur)
                if n <= 400 and r > 9 * k:   # fénypont: gömbnek hat
                    fr = r * 0.2
                    d.ellipse((x - r * 0.42 - fr, y - r * 0.42 - fr, x - r * 0.42 + fr, y - r * 0.42 + fr), fill=_kever(c, (255, 255, 255), 0.65))
        if sz.elemek:
            toll = _Toll(d, k, self)
            for h, p in sz.elemek:
                if "rajzol" in h:
                    h["rajzol"](sz, p, toll)
        for fr in getattr(sz, "forrasok", []):   # 🥤 a forrás-labdák: nagyok, világítók (a csapat színében), becsapódáskor lüktetnek
            x, y = fr.body.position.x * k, fr.body.position.y * k
            r = fr.radius * k * (1 + 0.18 * self.forras_puls)
            c = self.rgb[fr.szin % len(self.rgb)]
            for m_, a_ in ((1.9, 0.12), (1.45, 0.3)):
                d.ellipse((x - r * m_, y - r * m_, x + r * m_, y + r * m_), fill=_kever(self.bg, c, a_ + 0.2 * self.forras_puls))
            d.ellipse((x - r, y - r, x + r, y + r), fill=_kever(c, (255, 255, 255), 0.55), outline=(255, 255, 255), width=int(4 * k))
            if sz.szorzo > 1:
                d.text((x, y), f"x{sz.szorzo}", font=self.b_kis, fill=self.sotet, anchor="mm")
        self.forras_puls *= math.exp(-dt / 0.12)
        if self.v2:
            self._v2_vilag(d, sz)
        if self.inger:   # lökéshullámok + felugró brainrot-szavak (a labdák fölött)
            uj = []
            for hx, hy, t0, c, r0 in self.hullamok:
                e = (sz.t - t0) / 0.38
                if e >= 1:
                    continue
                rr = (r0 + 210 * e ** 0.7) * k
                d.ellipse((hx * k - rr, hy * k - rr, hx * k + rr, hy * k + rr), outline=_kever(self.bg, _kever(c, (255, 255, 255), 0.3), 1 - e),
                          width=max(2, int(14 * k * (1 - e))))
                uj.append([hx, hy, t0, c, r0])
            self.hullamok = uj
            uj = []
            for wx, wy, t0, szo, c, szog in self.szavak:
                e = (sz.t - t0) / 0.6
                if e >= 1:
                    continue
                m_ = 1 + 0.6 * max(0.0, 1 - e / 0.25) ** 2
                betu = self.b_szam.font_variant(size=int(78 * k * m_))
                fel = d.textlength(szo, font=betu) / k / 2 + 30   # a felirat ne lógjon ki a képből
                wx_ = max(fel, min(SZ - fel, wx))
                d.text((wx_ * k, (wy - 40 * e) * k), szo, font=betu, fill=_kever(self.bg, c, 1 - max(0.0, e - 0.6) / 0.4),
                       anchor="mm", stroke_width=int(5 * k), stroke_fill=self.sotet)
                uj.append([wx, wy, t0, szo, c, szog])
            self.szavak = uj
            if self.inger_villan > 0.02:   # a háttér a pattanó labda színében villan + pici zoom-punch
                z = 1 + 0.02 * self.inger_villan
                w2, h2 = int(self.W / z) // 2 * 2, int(self.H / z) // 2 * 2
                x0, y0 = (self.W - w2) // 2, (self.H - h2) // 2
                kep = kep.crop((x0, y0, x0 + w2, y0 + h2)).resize((self.W, self.H), self.Image.BILINEAR)
                kep = self.Image.blend(kep, self.Image.new("RGB", kep.size, self.inger_szin), 0.11 * self.inger_villan)
                self.inger_villan *= math.exp(-dt / 0.07)
        # --- ütem-lüktetés a drop után: zoom-punch + a háttér felvillan a fő színben (a feliratok alatt)
        if self.pulzus > 0.02:
            z = 1 + 0.035 * min(1.6, self.pulzus)
            w2, h2 = int(self.W / z) // 2 * 2, int(self.H / z) // 2 * 2
            x0, y0 = (self.W - w2) // 2, (self.H - h2) // 2
            kep = kep.crop((x0, y0, x0 + w2, y0 + h2)).resize((self.W, self.H), self.Image.BILINEAR)
            kep = self.Image.blend(kep, self.Image.new("RGB", kep.size, self.rgb[0]), 0.10 * min(1.0, self.pulzus))
            self.pulzus *= math.exp(-dt / 0.06)
        # --- 🥤 lassítás: ráközelítés a pohár peremére
        lassit = getattr(sz, "lassit", 1.0)
        if self.v2:
            kep = self._kamera(kep, sz, lassit, dt)
        elif lassit < 0.97:   # csak a kérdés + haladásjelző ALATTI részt nagyítjuk (a kérdés maradjon olvasható)
            z = 1 + 0.32 * min(1.0, (1 - lassit) / 0.55)
            Y0 = int((self.sav_y + 80) * k)
            RW, RH = self.W, self.H - Y0
            w2, h2 = int(RW / z) // 2 * 2, int(RH / z) // 2 * 2
            cx, cy = KX * k, (KY - sz.R * 1.05 + 160) * k - Y0
            x0 = int(max(0, min(RW - w2, cx - w2 / 2)))
            y0 = int(max(0, min(RH - h2, cy - h2 / 2)))
            resz = kep.crop((x0, Y0 + y0, x0 + w2, Y0 + y0 + h2)).resize((RW, RH), self.Image.BILINEAR)
            kep.paste(resz, (0, Y0))
        # --- rázkódás / villanás a csattanónál (a feliratok alatt: azok nem rázkódnak)
        if self.razas > 0:
            a = 22 * k * self.razas / 0.5
            kep = self.ImageChops.offset(kep, int(self.rnd.uniform(-a, a)), int(self.rnd.uniform(-a, a)))
            self.razas -= dt
        if self.villanas > 0:
            kep = self.Image.blend(kep, self.Image.new("RGB", kep.size, (255, 255, 255)), min(0.7, 0.45 * self.villanas / 0.16))
            self.villanas -= dt
        if self.v2:
            kep = self._veszely(kep, sz)
        d = self.ImageDraw.Draw(kep)
        # --- haladásjelző (mennyire közel a csattanó) + számláló
        h, szoveg = sz.haladas(), sz.szamlalo()
        y = self.sav_y * k
        if h is not None:
            sw, sh, x0 = 560 * k, 30 * k, (self.W - 560 * k) / 2 - 60 * k
            d.rounded_rectangle((x0, y - sh / 2, x0 + sw, y + sh / 2), radius=sh / 2, fill=_kever(self.bg, self.vil, 0.16))
            if h > 0.02:
                d.rounded_rectangle((x0, y - sh / 2, x0 + max(sh, sw * h), y + sh / 2), radius=sh / 2,
                                    fill=self.rgb[1 % len(self.rgb)] if h < 0.8 else self.rgb[0])
            d.text((x0 + sw + 18 * k, y), f"{int(h * 100)}%", font=self.b_szam, fill=self.vilagos, anchor="lm",
                   stroke_width=int(4 * k), stroke_fill=self.sotet)
            y += 62 * k
        if self.v2:   # 🥤 PIROS vs KÉK arány-sáv
            p0 = sz.reszesedes[0]
            sw, sh, x0 = 640 * k, 34 * k, (self.W - 640 * k) / 2
            d.rounded_rectangle((x0, y - sh / 2, x0 + sw, y + sh / 2), radius=sh / 2, fill=self.rgb[1])
            if p0 > 0.02:
                d.rounded_rectangle((x0, y - sh / 2, x0 + max(sh, sw * p0), y + sh / 2), radius=sh / 2, fill=self.rgb[0])
            for j, (xx, anc) in enumerate(((x0 - 14 * k, "rm"), (x0 + sw + 14 * k, "lm"))):
                d.text((xx, y), f"{int(round(100 * sz.reszesedes[j]))}%", font=self.b_kis, fill=self.rgb[j], anchor=anc,
                       stroke_width=int(4 * k), stroke_fill=self.sotet)
            for j, (xx, anc) in enumerate(((x0 + 22 * k, "lm"), (x0 + sw - 22 * k, "rm"))):
                d.text((xx, y), CSAPAT_NEV[j], font=self.b_kis.font_variant(size=int(26 * k)), fill=(255, 255, 255), anchor=anc)
            if sz.vezeto is not None and sz.vege_ido is None:   # korona a vezető felén
                cx_ = x0 + (sw * 0.25 if sz.vezeto == 0 else sw * 0.75)
                d.polygon([(cx_ - 20 * k, y - sh / 2 - 4 * k), (cx_ - 20 * k, y - sh / 2 - 26 * k), (cx_ - 8 * k, y - sh / 2 - 14 * k),
                           (cx_, y - sh / 2 - 30 * k), (cx_ + 8 * k, y - sh / 2 - 14 * k), (cx_ + 20 * k, y - sh / 2 - 26 * k),
                           (cx_ + 20 * k, y - sh / 2 - 4 * k)], fill=(255, 205, 40), outline=self.sotet)
        elif szoveg:
            d.text((self.W / 2, y), szoveg, font=self.b_kis if h is not None else self.b_szam, fill=self.szinek[0], anchor="mm",
                   stroke_width=int(4 * k), stroke_fill=self.sotet)
        felirat = None
        if self.v2 and sz.vege_ido is not None and getattr(sz, "gyoztes", None) is not None:
            felirat = f"{CSAPAT_NEV[sz.gyoztes]} WINS!"
        elif sz.vege_ido is not None and self.spec["siker_felirat"]:
            felirat = self.spec["siker_felirat"]
        elif sz.vege_ido is None and self.veg_felirat and sz.t >= self.spec["hossz"] - 2.4:
            felirat = self.veg_felirat
        # ÚJRA-HOOK: közel a csattanó -> "ALMOST..." felirat (a néző kivárja a végét)
        if h is not None and h >= self.majdnem_kuszob and not self.majdnem_volt and sz.vege_ido is None and self.spec.get("majdnem_felirat", "ALMOST...") \
                and sz.t > 6:
            self.majdnem_volt, self.majdnem_ido = True, sz.t
        if self.majdnem_ido is not None and sz.vege_ido is None and sz.t - self.majdnem_ido < 1.6 and not felirat:
            e_ = (sz.t - self.majdnem_ido) / 0.2
            betu = self.b_szam.font_variant(size=int(72 * k * (1 + 0.3 * max(0.0, 1 - e_))))
            d.text((self.W / 2, self.felirat_y * k), self.spec.get("majdnem_felirat") or "ALMOST...", font=betu, fill=self.vilagos, anchor="mm",
                   stroke_width=int(6 * k), stroke_fill=self.sotet)
        ff = getattr(sz, "fordulat_felirat", None)
        if ff and ff[0] and sz.t - ff[1] < 1.4 and not felirat:   # 🥤 fordulat-felirat: beugrik, rugózik, elhalványul
            e_ = (sz.t - ff[1]) / 1.4
            m_ = 1 + 0.45 * max(0.0, 1 - e_ / 0.15) ** 2
            betu = self.b_szam.font_variant(size=int(86 * k * m_))
            if e_ < 0.85 or int(sz.t * 20) % 2 == 0:   # a végén villogva tűnik el (élénk szín, nem halványul a háttérbe)
                d.text((self.W / 2, self.felirat_y * k), ff[0], font=betu, fill=self.vilagos, anchor="mm", stroke_width=int(8 * k),
                       stroke_fill=self.rgb[len(sz.fordulatok) % len(self.rgb)])
        if felirat:
            ugr = 1 + 0.25 * max(0.0, 1 - (sz.t - (sz.vege_ido if sz.vege_ido is not None else self.spec["hossz"] - 2.4)) / 0.25)
            betu = self.b_veg if ugr <= 1.01 else self.b_veg.font_variant(size=int(128 * k * ugr))
            szin_ = self.rgb[sz.gyoztes] if self.v2 and getattr(sz, "gyoztes", None) is not None else self.szinek[1 % len(self.szinek)]
            d.text((self.W / 2, self.felirat_y * k), felirat, font=betu, fill=szin_, anchor="mm",
                   stroke_width=int(9 * k), stroke_fill=self.sotet)
            if self.v2 and sz.vege_ido is not None and sz.t - sz.vege_ido > 0.6:
                d.text((self.W / 2, (self.felirat_y + 95) * k), "COMMENT YOUR COLOR!", font=self.b_kis, fill=self.vilagos, anchor="mm",
                       stroke_width=int(5 * k), stroke_fill=self.sotet)
        if self.v2:   # 🔁 loop: az utolsó 0,35 mp-ben visszaúszik az első képkocka (újranézésre csábít)
            if self.elso_kep is None and sz.t > 0.5:
                self.elso_kep = kep.copy()
            veg = (sz.vege_ido + 2.6) if sz.vege_ido is not None else self.spec["hossz"]
            if self.elso_kep is not None and sz.t > veg - 0.35:
                kep = self.Image.blend(kep, self.elso_kep, min(1.0, (sz.t - (veg - 0.35)) / 0.35))
        return kep

    # -- 🥤 túlcsordulás 2.0: világ-rétegű effektek, kamera, veszély
    def _v2_vilag(self, d, sz):
        k = self.k
        w, h = sz.R * 0.82, sz.R * 1.05
        hal = sz.haladas() or 0
        if sz.lefolyo and not sz.tores:   # örvény a lefolyó fölött
            cx, cy = KX * k, (KY + h) * k
            for i in range(5):
                rr = (30 + i * 26) * k
                a0 = (sz.t * 540 + i * 60) % 360
                d.arc((cx - rr, cy - rr * 0.55, cx + rr, cy + rr * 0.55), a0, a0 + 120, fill=_kever(self.bg, self.vil, 0.9 - i * 0.15),
                      width=max(2, int(6 * k)))
        if sz.eso_ido is not None and int(sz.t * 10) % 2 == 0:   # labdaeső előtt: villogó figyelmeztető háromszögek
            y = (KY - h - 90) * k
            for j in range(5):
                x = (KX - w + (j + 0.5) * 2 * w / 5) * k
                d.polygon([(x, y - 34 * k), (x - 30 * k, y + 20 * k), (x + 30 * k, y + 20 * k)], fill=(255, 205, 40), outline=self.sotet)
                d.text((x, y + 2 * k), "!", font=self.b_kis, fill=self.sotet, anchor="mm")
        if sz.t < sz.turbo_ig and sz.vege_ido is None:   # turbó: sebesség-csíkok
            for _ in range(14):
                x = self.rnd.uniform(KX - w, KX + w) * k
                y = self.rnd.uniform(KY - h - 200, KY + h) * k
                d.line((x, y, x, y + self.rnd.uniform(60, 160) * k), fill=_kever(self.bg, (255, 230, 120), 0.6), width=max(2, int(3 * k)))
        if hal >= 0.75 and sz.vege_ido is None and not sz.tores and int(sz.t * 6) % 2 == 0:   # villogó veszélycsík a peremen
            y = (KY - h) * k
            n = 12
            for j in range(n):
                x0 = (KX - w + 2 * w * j / n) * k
                d.line((x0, y - 16 * k, x0 + 2 * w / n * k, y - 16 * k), fill=(255, 205, 40) if j % 2 == 0 else (25, 20, 20),
                       width=int(12 * k))

    def _kamera(self, kep, sz, lassit, dt):
        """Élő kamera a kérdés alatti részen: ráközelít a pohárra és a forrás-labdákra, a fordulatoknál belerúg, a perem
        előtti lassításnál a peremre zoomol, a csattanó után kizoomol (látszik a szétrobbanás és az alsó pohár)."""
        k = self.k
        Y0 = int((self.sav_y + 130) * k)
        RW, RH = self.W, self.H - Y0
        fr = getattr(sz, "forrasok", [])
        fy = sum(f.body.position.y for f in fr) / len(fr) if fr else KY
        if sz.vege_ido is not None:
            cel_z, cel_y = (1.0, (M * k + Y0) / 2) if sz.t - sz.vege_ido > 0.4 else (1.35, (KY - sz.R * 1.05 + 150) * k)
        elif lassit < 0.97:
            cel_z, cel_y = 1.15 + 0.3 * min(1.0, (1 - lassit) / 0.55), (KY - sz.R * 1.05 + 160) * k
        else:
            cel_z, cel_y = 1.15, (0.65 * KY + 0.35 * fy) * k
        self.cam_y = cel_y if self.cam_y is None else self.cam_y + (cel_y - self.cam_y) * 0.08
        self.cam_z += (cel_z - self.cam_z) * 0.08
        z = self.cam_z + 0.07 * self.punch
        self.punch *= math.exp(-dt / 0.18)
        if z < 1.005:
            return kep
        w2, h2 = int(RW / z) // 2 * 2, int(RH / z) // 2 * 2
        x0 = int(max(0, min(RW - w2, KX * k - w2 / 2)))
        y0 = int(max(0, min(RH - h2, self.cam_y - Y0 - h2 / 2)))
        resz = kep.crop((x0, Y0 + y0, x0 + w2, Y0 + y0 + h2)).resize((RW, RH), self.Image.BILINEAR)
        kep.paste(resz, (0, Y0))
        return kep

    def _veszely(self, kep, sz):
        """70% fölött a kép szélei pirosan lüktetnek (szívverés), egyre gyorsabban."""
        hal = sz.haladas() or 0
        if hal < 0.7 or sz.vege_ido is not None:
            return kep
        ero = (hal - 0.7) / 0.3
        frek = 1.3 + 1.6 * ero
        puls = 0.5 + 0.5 * math.cos(sz.t * frek * math.tau)
        a = (0.18 + 0.32 * ero) * (0.55 + 0.45 * puls)
        maszk = self.vignetta.point(lambda v, a=a: int(max(0, v - 90) * 1.55 * a))
        return self.Image.composite(self.Image.new("RGB", kep.size, (230, 20, 40)), kep, maszk)


class _Toll:
    """A tanult elemek rajzeszköze (világ-koordinátákban; a szín: palettaindex vagy "#rrggbb")."""

    def __init__(self, d, k, rajz):
        self.d, self.k, self.rajz = d, k, rajz

    def _szin(self, szin):
        return self.rajz.szinek[szin % len(self.rajz.szinek)] if isinstance(szin, int) else (szin or self.rajz.vilagos)

    def kor(self, x, y, sugar, szin=0, kitoltve=True):
        k = self.k
        self.d.ellipse(((x - sugar) * k, (y - sugar) * k, (x + sugar) * k, (y + sugar) * k), fill=self._szin(szin) if kitoltve else None,
                       outline=None if kitoltve else self._szin(szin), width=max(1, int(4 * k)))

    def vonal(self, x1, y1, x2, y2, szin=None, vastag=6):
        self.d.line((x1 * self.k, y1 * self.k, x2 * self.k, y2 * self.k), fill=self._szin(szin), width=max(1, int(vastag * self.k)))

    def szoveg(self, x, y, szoveg, szin=None):
        self.d.text((x * self.k, y * self.k), str(szoveg)[:40], font=self.rajz.b_szam, fill=self._szin(szin), anchor="mm",
                    stroke_width=int(4 * self.k), stroke_fill=self.rajz.sotet)


class MinosegHiba(RuntimeError):
    """A mért minőségkapun egyik lefutás sem ment át (a renderelés előtt derül ki, így olcsó újrapróbálni)."""

    def __init__(self, kapu):
        super().__init__("MINŐSÉG: " + "; ".join(kapu["hibak"]) + f" ({kapu['pont']}/10)")
        self.kapu = kapu


def keszit(spec, cel, munka=None, halad=lambda s: None, ellenoriz=lambda: None, keret_mp=90, _gyerekben=False, szigoru=False):
    """SPEC -> kész mp4 (1080×1920, 60 fps, hanggal). Visszaad: {spec (a végső tempóval), mag, mérőszámok, napló}.
    Ha a SPEC tanult építőelemet használ (Kobold által írt kód), az egész a HOMOKOZÓBAN fut (külön folyamat, hálózat
    és fájlhozzáférés nélkül, időkorláttal)."""
    spec = tisztit(spec)
    munka = munka or os.path.dirname(cel)
    os.makedirs(munka, exist_ok=True)
    if spec["hang"]["zene"] in ("trend", "brainrot") and not _gyerekben:   # a felkapott dalok / brainrot-hangok közül
        import szim_trendhang as trendhang
        z = trendhang.kovetkezo("brainrot" if spec["hang"]["zene"] == "brainrot" else "dal") or trendhang.kovetkezo()
        spec["hang"]["zene"] = z["azon"] if z else "nincs"
    if spec["hang"].get("meme") in ("trend", "brainrot") and not _gyerekben:   # a mai felkapott (brainrot-) mém-hangok közül
        import szim_trendhang as trendhang
        m_ = trendhang.kovetkezo_meme(tipus="brainrot" if spec["hang"]["meme"] == "brainrot" else None)
        spec["hang"]["meme"] = m_["azon"] if m_ else "nincs"
    if spec["hang"].get("inger") and not spec["hang"].get("memek") and not _gyerekben:   # 🧠 6 különböző brainrot mém-hang
        import szim_trendhang as trendhang
        memek = []
        for _ in range(6):
            m_ = trendhang.kovetkezo_meme(kizar=memek, tipus="brainrot")
            if not m_ or m_["azon"] in memek:
                break
            memek.append(m_["azon"])
        spec["hang"]["memek"] = [m for m in memek if m in sajat_hangok()]
        spec["hang"]["zene"] = "nincs"
        for mezo in ("kerdes", "cim"):   # a pattanás most brainrot-hang, nem hangjegy
            if isinstance(spec.get(mezo), str):
                spec[mezo] = _re.sub(r"(?i)\b(plays|makes) a (musical )?note\b", r"\1 a brainrot sound", spec[mezo])
                spec[mezo] = _re.sub(r"(?i)\b(plays|makes|sings) a (song|melody|tune)\b", "goes full brainrot", spec[mezo]).replace("🎵", "🧠")
                spec[mezo] = _re.sub(r"(?i)\bnotes?\b", "brainrot sounds" if mezo == "cim" else "sounds", spec[mezo]) \
                    if "brainrot" not in spec[mezo].lower() else spec[mezo]
    if spec["elemek"] and not _gyerekben:
        er = homokozoban({"mod": "keszit", "spec": spec, "cel": cel, "keret_mp": keret_mp}, munka, 900, halad, ellenoriz)
        _zene_hasznalt(spec)
        return er
    halad("Előválogatás: melyik lefutásnál jön a csattanó a végén…")
    regi_ertek = spec["vege"]["ertek"]
    spec, valasztott, naplo = valaszt(spec, keret_mp, halad, ellenoriz)
    if spec["vege"]["ertek"] != regi_ertek and spec["vege"]["mikor"] in SZAMOS_VEG:
        for mezo in ("kerdes", "cim"):  # "Can 5 escape?" -> "Can 40 escape?"
            spec[mezo] = _re.sub(rf"(?<![\d.,]){int(regi_ertek)}(?![\d.,])", str(int(spec["vege"]["ertek"])), spec[mezo])
        if "{n}" in spec.get("kerdes_sablon", ""):
            spec["kerdes"] = spec["kerdes_sablon"].replace("{n}", str(int(spec["vege"]["ertek"])))
    kapu = valasztott.get("minoseg") or minoseg(spec, valasztott)
    if szigoru and not kapu["jo"]:
        raise MinosegHiba(kapu)
    lesz_vege = valasztott["vege_ido"] is not None
    zene, zene_terv = None, None
    if spec["hang"]["zene"] not in ("nincs", "trend", "brainrot"):
        import szim_trendhang as trendhang
        zene = trendhang.zene(spec["hang"]["zene"])
    if zene:   # 🎧 hol a dal dropja -> úgy indítjuk a dalt, hogy a drop a videó közepén szóljon, és ott a képen is robban valami
        try:
            zene_terv = trendhang.drop_terv(zene["fajl"], valasztott["hossz"], FFMPEG, csattano=valasztott.get("vege_ido"))
        except Exception as hiba_:
            print(f"[SZIMULÁCIÓ] drop-elemzés nem sikerült: {hiba_}", flush=True)
    rajz = Rajzolo(spec, veg_felirat=None if lesz_vege or spec["vege"]["mikor"] == "ido" else spec["kudarc_felirat"],
                   zene_terv=zene_terv)
    nema = os.path.join(munka, "szim_nema.mp4")
    ff = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{rajz.W}x{rajz.H}",
                           "-r", str(FPS), "-i", "-", "-vf", f"scale={SZ}:{M}:flags=area", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "20", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p", nema], stdin=subprocess.PIPE)
    osszes, kezd = int(valasztott["hossz"] * FPS), time.time()
    allapot = {"n": 0}

    def kocka(sz):
        ff.stdin.write(rajz.kep(sz).tobytes())
        allapot["n"] += 1
        if allapot["n"] % 60 == 0:
            ellenoriz()
            halad(f"Renderelés: {min(99, int(100 * allapot['n'] / max(1, osszes)))}% ({len(sz.labdak)} labda)")
    try:
        e = futtat(spec, valasztott["mag"], kepkocka=kocka)
    finally:
        try:
            ff.stdin.close()
        except Exception:
            pass
        ff.wait(timeout=600)
    if ff.returncode != 0 or not os.path.exists(nema):
        raise RuntimeError("a videó kódolása nem sikerült (ffmpeg)")
    halad("Hang: az ütközésekből dallam készül")
    wav = os.path.join(munka, "szim_hang.wav")
    hang_ir(e["hangok"], e["hossz"], spec["hang"], wav,
            kudarc_ido=None if lesz_vege or spec["vege"]["mikor"] == "ido" else max(0.0, e["hossz"] - 2.4),
            idovonal=e.get("idovonal"), labdak_max=e["labdak_max"], tulcs2=bool(spec.get("tulcs2")))
    if zene:
        import szim_trendhang as trendhang
        halad(f"Trending zene alá: {zene['eloado']} – {zene['cim']}")
        zene_kezd = trendhang.kever(nema, wav, zene["fajl"], e["hossz"], cel, FFMPEG, csattano=e.get("vege_ido"),
                                    kezd=(zene_terv or {}).get("kezd"), ismetel=(zene_terv or {}).get("ismetel"))
        print(f"[SZIMULÁCIÓ] trending zene: {zene['eloado']} – {zene['cim']} ({zene_kezd:.0f}. mp-től)", flush=True)
    else:
        r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", nema, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                            "-shortest", "-movflags", "+faststart", cel], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"a hang rákeverése nem sikerült: {r.stderr[-200:]}")
    for f in (nema, wav):
        try:
            os.remove(f)
        except OSError:
            pass
    meres = {k: v for k, v in e.items() if k not in ("hangok", "idovonal", "minoseg")}
    meres.update(render_mp=round(time.time() - kezd, 1), tempo=spec["tempo"], csattano=lesz_vege, hangolas=naplo,
                 zene=f"{zene['eloado']} – {zene['cim']}" if zene else "", minoseg=kapu,
                 zene_tipus=(zene.get("tipus") or "dal") if zene else "brainrot" if spec["hang"].get("inger") else "",
                 inger=bool(spec["hang"].get("inger")),
                 drop=(zene_terv or {}).get("drop"), bpm=round(60 / zene_terv["utem"]) if (zene_terv or {}).get("utem") else None,
                 meme=spec["hang"].get("meme") if spec["hang"].get("meme") not in (None, "nincs") else "")
    if not _gyerekben:
        _zene_hasznalt(spec)
    return {"spec": spec, "mag": valasztott["mag"], "meres": meres}


def _meme_hasznalt(spec):
    for m in spec["hang"].get("memek") or []:
        try:
            import szim_trendhang as trendhang
            trendhang.meme_felhasznal(m)
        except Exception as hiba:
            print("[SZIMULÁCIÓ] mém jelölés hiba:", hiba, flush=True)
    if spec["hang"].get("meme") not in (None, "nincs", "trend"):
        try:
            import szim_trendhang as trendhang
            trendhang.meme_felhasznal(spec["hang"]["meme"])
        except Exception as hiba:
            print("[SZIMULÁCIÓ] mém jelölés hiba:", hiba, flush=True)


def _zene_hasznalt(spec):
    _meme_hasznalt(spec)
    if spec["hang"].get("zene") not in (None, "nincs", "trend", "brainrot"):
        try:
            import szim_trendhang as trendhang
            trendhang.felhasznal(spec["hang"]["zene"])
        except Exception as hiba:
            print("[SZIMULÁCIÓ] trendzene jelölés hiba:", hiba, flush=True)


# ---------------------------------------------------------------- tanulás: mintatár, kerülendők, kívánságok

def kivansag(szoveg, cim=""):
    """Amit a tervező az építőelemekből nem tudott kirakni: a kívánságlistára (a motor bővítéséhez)."""
    szoveg = (szoveg or "").strip()
    if not szoveg:
        return
    os.makedirs(MAPPA, exist_ok=True)
    ut = os.path.join(MAPPA, "kivansagok.json")
    try:
        with open(ut, encoding="utf-8") as f:
            lista = json.load(f)
    except Exception:
        lista = []
    lista = [x for x in lista if x.get("szoveg") != szoveg] + [{"ido": time.time(), "szoveg": szoveg, "cim": cim}]
    with open(ut, "w", encoding="utf-8") as f:
        json.dump(lista[-100:], f, ensure_ascii=False, indent=1)
    print(f"[SZIMULÁCIÓ] hiányzó építőelem: {szoveg}", flush=True)


def kivansagok():
    try:
        with open(os.path.join(MAPPA, "kivansagok.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _rovid(spec):
    spec = tisztit(spec)  # a régi tervek is a mostani formában (hang, látvány) kerüljenek a tervező elé
    return json.dumps({k: v for k, v in spec.items() if k not in ("hianyzik", "tempo") and not k.startswith("_")}, ensure_ascii=False)


def tiltott_palya(klipek=()):
    """Változatosság: ha az utolsó 3 szimulációs videóból legalább 2 ugyanazt a pályát használta, az most tiltott.
    (Mérés: egy éjszaka 8 videóból 7 "forgó gyűrűk + osztódás" lett.) Visszaad: (tiltott típus vagy None, ajánlottak)."""
    szim = sorted((k for k in klipek if (k.get("szim") or {}).get("spec")), key=lambda k: -(k.get("letrehozva") or 0))
    tipusok = [k["szim"]["spec"]["palya"]["tipus"] for k in szim]
    tiltott = next((t for t in set(tipusok[:3]) if tipusok[:3].count(t) >= 2), None)
    ajanlott = sorted((t for t in PALYAK if t not in ("ures", tiltott)), key=lambda t: tipusok[:12].count(t))
    return tiltott, ajanlott[:3]


def tudas(klipek=(), trend_munka=False):
    """A tervezőnek: az építőelemek + bevált minták (a jóváhagyott videók SPEC-jei, mérőszámokkal) + kerülendők
    (az elvetettek). klipek: a Kincseskamra termékei (amelyikben van "szim" mező, az szimulációs videó)."""
    # a felhasználó által a tanulásból kizárt klipek (pl. tömeges elutasítás) se mintának, se kerülendőnek nem számítanak
    szim = sorted((k for k in klipek if (k.get("szim") or {}).get("spec") and not k.get("tanulasbol_kizarva")),
                  key=lambda k: -(k.get("letrehozva") or 0))
    jo = [k for k in szim if k.get("allapot") in ("jovahagyva", "feltoltes", "feltoltve")]
    rossz = [k for k in szim if k.get("allapot") == "elvetve"]
    # A legfrissebb döntések azonnal eljutnak a tervezőhöz, nem várnak az összesített tanulságokra.
    velemenyek = sorted((k for k in jo + rossz if k.get("megjegyzes")),
                        key=lambda k: -(k.get("dontes_ido") or k.get("letrehozva") or 0))[:8]
    # a nézettség szerint legjobbak előre (ha van adat), különben a legfrissebbek
    jo.sort(key=lambda k: -(k.get("megtekintes") or k.get("nezettseg") or 0))
    reszek = [ELEMEK, "\nPROVEN EXAMPLES (complete specs - reuse their structure, but never repeat one unchanged: vary the "
                      "container, the rule, the question, the palette):"]
    if velemenyek:
        reszek.append("RECENT OWNER FEEDBACK (apply to the next video; approval can also include requested improvements):")
        for k in velemenyek:
            reszek.append(json.dumps({"id": k["id"], "title": k.get("cim"),
                "decision": "rejected" if k["allapot"] == "elvetve" else "approved",
                "feedback": str(k["megjegyzes"])[:1000], "spec": json.loads(_rovid(k["szim"]["spec"]))}, ensure_ascii=False))
    for k in jo[:3]:
        m = k["szim"].get("meres") or {}
        reszek.append(f"- APPROVED by the user ({m.get('labdak_max', '?')} balls max, payoff at {m.get('vege_ido', '-')} s): {_rovid(k['szim']['spec'])}")
    for s in MINTAK[:max(2, 4 - len(jo[:3]))]:
        reszek.append(f"- built-in: {_rovid(s)}")
    if rossz:
        reszek.append("REJECTED by the user (avoid these combinations / fix what is named): " + "; ".join(
            f"\"{k.get('cim', '')[:50]}\" ({k['szim']['spec']['palya']['tipus']}, "
            + ", ".join(f"{r['mikor']}->{r['mit']}" for r in k["szim"]["spec"]["szabalyok"])
            + (f"; reason: {str(k.get('megjegyzes') or k.get('elvetes_ok') or '')[:300]}" if k.get("megjegyzes") or k.get("elvetes_ok") else "")
            + ")" for k in rossz[:5]))
    tanult = [e for e in elemek() if e.get("allapot") == "aktiv"]
    if tanult:
        reszek.append("LEARNED EXTRA ELEMENTS (plugins Kobold wrote itself; add them to a spec as \"elemek\": [{\"azon\": id, "
                      "\"p\": {parameters}}], max 3 per video, combined with the normal blocks):\n"
                      + "\n".join(f"- {e['azon']}: {e['leiras']}" + (f" (e.g. p = {json.dumps(e['proba_p'])})" if e.get("proba_p") else "") for e in tanult[-12:]))
    trend = [f for f in trendek().get("formulak", [])][:5]
    if trend:
        reszek.append("WHAT IS GOING VIRAL NOW (formulas of the most-viewed recent simulation shorts - copy the FORMULA and "
                      "why it works, never the title or the look):\n"
                      + "\n".join(f"- {f['napi_nezettseg']:,} views/day" + (f", {f['hossz']:.0f} s long" if f.get("hossz") else "")
                                  + f": {f['formula'][:260]} Why it works: {f['miert_megy'][:120]}" for f in trend))
    tiltott, ajanlott = tiltott_palya(klipek)
    if tiltott and not trend_munka:
        reszek.append(f"VARIETY RULE (mandatory): the last videos all used the container '{tiltott}' - this video must NOT use "
                      f"it. Build it on: {', '.join(ajanlott)}. Also use a different main rule than the recent ones: "
                      + "; ".join(", ".join(f"{r['mikor']}->{r['mit']}" for r in k["szim"]["spec"]["szabalyok"]) for k in szim[:3]))
    if szim:
        reszek.append("Already made (do not repeat the same question): " + "; ".join(k["szim"]["spec"]["kerdes"] for k in szim[:12]))
    return "\n".join(reszek)



# ---------------------------------------------------------------- 🧩 tanult építőelemek (Kobold maga írja őket)
# Ha egy koncepcióhoz olyan kell, amit az építőelemek nem tudnak (új erő, új alakzat, új szabály, új látvány), Kobold
# megírja BŐVÍTMÉNYKÉNT: egy kis Python-fájl horgokkal (indul / lep / utkozes / rajzol / vege), ami a szimuláció API-ját
# hívja. Biztonság – az app szabályai szerint, mint a képességeknél: (1) kódellenőrzés (nincs import, nincs fájl / hálózat /
# rendszerhívás, nincs "__" név), (2) a tanult elemet használó szimuláció mindig HOMOKOZÓBAN fut (külön folyamat,
# hálózat nélkül, a saját mappádból semmit nem olvashat, csak a munkamappába írhat, időkorláttal), (3) próbafutás, mielőtt
# bekerül a tárba, (4) ha élesben kétszer hibázik, magától kikapcsol. A kész videó ugyanúgy a jóváhagyásodra vár.

ELEM_MAPPA = os.path.join(MAPPA, "elemek")
TILTOTT_NEV = {"eval", "exec", "compile", "open", "input", "getattr", "setattr", "delattr", "globals", "locals", "vars",
               "breakpoint", "memoryview", "type", "super", "object", "classmethod", "staticmethod", "print", "exit", "quit", "help"}
HORGOK = ("indul", "lep", "utkozes", "rajzol", "vege")
ELEM_API = """You write a small PLUGIN ("element") for a 2D ball-physics video engine (pymunk, y axis points DOWN, screen
1080x1920, arena centre KX=540, KY=1090). The plugin adds ONE new capability the engine lacks. It is a Python module
that defines one or more of these hook functions (define only what you need):
  def indul(sz, p):                  # once, at the start (build walls / pegs, init sz.allapot)
  def lep(sz, p, dt):                # every frame (dt = 1/60): forces, spawning, timers, moving things
  def utkozes(sz, p, fajta, labdak): # on every collision; fajta: "labda_fal" | "labda_labda" | "labda_akadaly"; labdak = involved balls
  def rajzol(sz, p, toll):           # extra drawing each frame, on top of the scene
  def vege(sz, p):                   # return True when YOUR payoff happened (optional)
p = dict of parameters from the scene spec - ALWAYS read with defaults: p.get("ero", 600).
API (use only this):
  sz.t (seconds), sz.R (arena half-size in px), sz.allapot (dict: your persistent state), sz.rnd (random.Random: use it, never other randomness)
  sz.szinek -> list of the palette's colours (a ball's al.szin is an index into it: next colour = (al.szin + 1) % len(sz.szinek))
  sz.s -> the scene spec dict (read-only), e.g. sz.s["labdak"]["sugar"], sz.s["gravitacio"]
  sz.labdak -> list of balls. A ball `al`: al.body.position (x, y) and al.body.velocity (vx, vy) - both readable and
      assignable as tuples; al.radius; al.szin (palette index, assignable int); al.kint (True once it left the arena);
      al.adat (dict: your per-ball data).
  sz.uj_labda(hely=(x, y), sugar=20, seb=(vx, vy), szin=0) -> ball or None (None when the ball cap is reached)
  sz.torol(al); sz.atmeretez(al, new_radius)
  sz.uj_fal([(x1, y1), (x2, y2), ...], forog=0, kozep=(KX, KY)) -> body   # polyline wall, points RELATIVE to kozep;
      forog = degrees/second rotation around kozep; the returned body has .angle (radians) and .position (assignable)
  sz.uj_szog(x, y, r=13)             # static round peg
  sz.hang(meret=0.5)                 # play a note (0 = high, 1 = low)
  sz.felirat = "TEXT"                # replaces the counter text under the question (None = default counter)
  sz.vege_jelez()                    # trigger the payoff now
  toll.kor(x, y, sugar, szin=0, kitoltve=True); toll.vonal(x1, y1, x2, y2, szin=None, vastag=6); toll.szoveg(x, y, text, szin=None)
      (szin: palette index int, a "#rrggbb" string, or None = wall colour)
Globals available: math, KX, KY, SZ (1080), M (1920), and the builtins abs min max len range float int round sum
enumerate zip list dict tuple set bool str sorted any all isinstance reversed id.
In utkozes, `labdak` holds 1 or 2 balls (a ball may already have been removed by a rule): never unpack it blindly, and
never compare or sort ball objects themselves (use id(al) or al.radius).
HARD RULES: NO import statements, no file / network / OS access, no names containing "__", no eval/exec/open/getattr/
print, no classes, no infinite loops (every loop must be bounded), keep per-frame work light (it runs 60x per second
with up to 1500 balls: no O(n^2) over all balls unless you cap n at 150). Never crash: guard divisions and empty lists.
The engine's own rules, container and counters keep working - do not re-implement them.
Example:
def lep(sz, p, dt):
    ero = p.get("ero", 700)
    for al in sz.labdak:
        x, y = al.body.position
        dx, dy = KX - x, KY - y
        d = max(40.0, math.hypot(dx, dy))
        vx, vy = al.body.velocity
        al.body.velocity = (vx + dx / d * ero * dt, vy + dy / d * ero * dt)
"""
ELEM_SEMA = {"type": "object", "properties": {
    "azon": {"type": "string"}, "nev": {"type": "string"}, "leiras": {"type": "string"}, "alap": {"type": "integer"},
    "proba_p": {"type": "object"}, "kod": {"type": "string"}},
    "required": ["azon", "nev", "leiras", "alap", "kod"]}
_BIZTONSAGOS = {f.__name__: f for f in (abs, min, max, len, range, float, int, round, sum, enumerate, zip, list, dict, tuple,
                                        set, bool, str, sorted, any, all, isinstance, reversed, id)}


def _json_olvas(nev, alap):
    try:
        with open(os.path.join(MAPPA, nev), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return alap


def _json_ir(nev, adat):
    os.makedirs(MAPPA, exist_ok=True)
    tmp = os.path.join(MAPPA, f"{nev}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(adat, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(MAPPA, nev))


def elemek():
    """A tanult építőelemek nyilvántartása: [{azon, nev, leiras, allapot: aktiv|ki, alap, proba_p, hasznalva, hibak, …}]"""
    return _json_olvas("elemek.json", [])


def elem_modosit(azon, **kv):
    lista = elemek()
    for e in lista:
        if e["azon"] == azon:
            e.update(kv)
    _json_ir("elemek.json", lista)


def elem_hiba(azon, szoveg):
    """Élesben hibázott: feljegyezzük; a második hiba után magától kikapcsol (nem rontja tovább a gyártást)."""
    for e in elemek():
        if e["azon"] == azon:
            hibak = int(e.get("hibak") or 0) + 1
            elem_modosit(azon, hibak=hibak, utolso_hiba=str(szoveg)[-300:], **({"allapot": "ki"} if hibak >= 2 else {}))
            print(f"[SZIMULÁCIÓ] a(z) {azon} elem hibázott ({hibak}×){' – kikapcsoltam' if hibak >= 2 else ''}: {str(szoveg)[-200:]}", flush=True)


def elemek_ertekel(klipek):
    """A felhasználó döntései alapján: ha egy tanult elemmel készült videók közül legalább 2-t elvetett, és egyet sem
    hagyott jóvá, az elem kikapcsol (nem vált be). Visszaad: a most kikapcsoltak azonjai."""
    ki = []
    for e in elemek():
        if e.get("allapot") != "aktiv":
            continue
        vele = [k for k in klipek if not k.get("tanulasbol_kizarva") and any(x.get("azon") == e["azon"] for x in ((k.get("szim") or {}).get("spec") or {}).get("elemek") or [])]
        rossz = sum(1 for k in vele if k.get("allapot") == "elvetve")
        jo = sum(1 for k in vele if k.get("allapot") in ("jovahagyva", "feltoltes", "feltoltve"))
        if rossz >= 2 and not jo:
            elem_modosit(e["azon"], allapot="ki", utolso_hiba=f"a vele készült {rossz} videót elvetetted")
            print(f"[SZIMULÁCIÓ] a(z) {e['azon']} elemet kikapcsoltam: a vele készült {rossz} videót elvetetted", flush=True)
            ki.append(e["azon"])
    return ki


def elem_torol(azon):
    _json_ir("elemek.json", [e for e in elemek() if e["azon"] != azon])
    try:
        os.remove(os.path.join(ELEM_MAPPA, azon + ".py"))
    except OSError:
        pass


def elem_ellenoriz(kod):
    """Statikus ellenőrzés: hibalista (üres = rendben)."""
    import ast

    try:
        fa = ast.parse(kod)
    except SyntaxError as hiba:
        return [f"SyntaxError: {hiba}"]
    hibak = []
    for n in ast.walk(fa):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            hibak.append("import is forbidden (math is already available as a global)")
        elif isinstance(n, (ast.ClassDef, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef)):
            hibak.append(f"forbidden construct: {type(n).__name__}")
        elif isinstance(n, ast.Name) and (n.id in TILTOTT_NEV or "__" in n.id):
            hibak.append(f"forbidden name: {n.id}")
        elif isinstance(n, ast.Attribute) and ("__" in n.attr or n.attr.startswith("_")):
            hibak.append(f"forbidden attribute: .{n.attr}")
        elif isinstance(n, ast.While) and isinstance(n.test, ast.Constant) and n.test.value:
            hibak.append("forbidden: while True (loops must be bounded)")
    if not any(isinstance(n, ast.FunctionDef) and n.name in HORGOK for n in fa.body):
        hibak.append("the module must define at least one hook: " + ", ".join(HORGOK))
    return sorted(set(hibak))


def elem_betolt(azon, ut=None):
    """Egy tanult elem horgai ({név: függvény}). Csak szűkített beépítettekkel fut; hibás kódnál kivétel."""
    with open(ut or os.path.join(ELEM_MAPPA, azon + ".py"), encoding="utf-8") as f:
        kod = f.read()
    hibak = elem_ellenoriz(kod)
    if hibak:
        raise RuntimeError(f"ELEM {azon}: " + "; ".join(hibak))
    ter = {"__builtins__": dict(_BIZTONSAGOS), "math": math, "KX": KX, "KY": KY, "SZ": SZ, "M": M}
    exec(compile(kod, f"elem_{azon}.py", "exec"), ter)  # noqa: S102 – ellenőrzött kód, homokozóban futó folyamatban
    return {h: ter[h] for h in HORGOK if callable(ter.get(h))}


def homokozoban(be, munka, idokorlat=600, halad=lambda s: None, ellenoriz=lambda: None):
    """A szimuláció futtatása külön, homokozóba zárt folyamatban (macOS sandbox-exec): nincs hálózat, a saját mappából
    csak a Python, a csomagok, Kobold kódja, a tanult elemek és a munkamappa olvasható, írni csak a munkamappába lehet,
    indítani csak a Pythont és az ffmpeg-et. be: {"mod": "keszit" | "proba", "spec", …}. Visszaad: a gyerek eredménye."""
    import kovacs
    import pymunk

    munka = os.path.realpath(munka)
    os.makedirs(munka, exist_ok=True)
    home = os.path.realpath(os.path.expanduser("~"))
    py = kovacs._python()
    kod_mappa = os.path.dirname(os.path.abspath(__file__))
    csomagok = os.path.dirname(os.path.dirname(os.path.realpath(pymunk.__file__)))
    olvashat = [os.path.dirname(os.path.dirname(py)), csomagok, kod_mappa, os.path.realpath(MAPPA), munka]
    olvashat += [os.path.dirname(os.path.realpath(u)) for u in (be.get("spec", {}).get("_elem_fajlok") or {}).values()]
    profil = f"""(version 1)
(allow default)
(deny network*)
(deny file-write* (require-not (subpath "{munka}")))
(allow file-write* (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr"))
(deny file-read* (subpath "{home}"))
(allow file-read* {" ".join(f'(subpath "{u}")' for u in olvashat)})
(deny process-exec)
(allow process-exec (literal "{py}") (literal "{os.path.realpath(FFMPEG)}"))
"""
    be_ut, profil_ut, hiba_ut = (os.path.join(munka, n) for n in ("szim_be.json", "szim_profil.sb", "szim_hiba.txt"))
    with open(be_ut, "w", encoding="utf-8") as f:
        json.dump(be, f, ensure_ascii=False)
    with open(profil_ut, "w") as f:
        f.write(profil)
    indito = (f"import sys; sys.path[:0] = [{kod_mappa!r}, {csomagok!r}]; import szim_engine; szim_engine._gyerek_fo(sys.argv[1])")
    eredmeny, kezd = None, time.time()
    with open(hiba_ut, "w") as hiba_f:
        p = subprocess.Popen(["sandbox-exec", "-f", profil_ut, py, "-s", "-S", "-X", "utf8", "-u", "-c", indito, be_ut], cwd=munka,
                             stdout=subprocess.PIPE, stderr=hiba_f, text=True, encoding="utf-8", errors="replace",
                             env={"HOME": home, "KOBOLD_ADAT": os.path.dirname(os.path.realpath(MAPPA)), "LANG": "hu_HU.UTF-8",
                                  "PATH": "/usr/bin:/bin", "TMPDIR": munka})
        import threading

        idozito = threading.Timer(idokorlat, p.kill)
        idozito.daemon = True
        idozito.start()
        try:
            for sor in p.stdout:
                if sor.startswith("<<<SZIM>>>"):
                    eredmeny = json.loads(sor[10:])
                elif sor.startswith("HALAD: "):
                    halad(sor[7:].strip())
                ellenoriz()
            p.wait()
        except BaseException:
            p.kill()
            raise
        finally:
            idozito.cancel()
    with open(hiba_ut, encoding="utf-8", errors="replace") as f:
        hiba = f.read()[-1800:]
    for u in (be_ut, profil_ut, hiba_ut):
        try:
            os.remove(u)
        except OSError:
            pass
    if eredmeny is None:
        raise RuntimeError("ELEM-HIBA: " + (f"időtúllépés ({idokorlat} mp)" if time.time() - kezd >= idokorlat - 1 else hiba.strip() or f"kilépési kód {p.returncode}"))
    return eredmeny


def _gyerek_fo(be_ut):
    """A homokozóban futó folyamat belépési pontja."""
    with open(be_ut, encoding="utf-8") as f:
        be = json.load(f)
    if be["mod"] == "keszit":
        er = keszit(be["spec"], be["cel"], halad=lambda s: print("HALAD: " + s, flush=True), keret_mp=be.get("keret_mp", 60), _gyerekben=True)
    else:  # proba: rövid futás az elemmel és nélküle – fut-e hiba nélkül, és van-e hatása
        spec = tisztit(be["spec"])
        spec["hossz"] = 12
        nelkul = dict(spec, elemek=[])
        er = {"futasok": []}
        for mag in (11, 23):
            a, b = futtat(spec, mag, max_mp=40), futtat(nelkul, mag, max_mp=40)
            er["futasok"].append({k: a[k] for k in ("hossz", "labdak_max", "labdak_vege", "utkozesek", "elem_hivas", "szamitas_mp", "lenyomat")}
                                 | {"nelkule_max": b["labdak_max"], "keret": spec["labdak"]["max"], "mas_mint_nelkule": a["lenyomat"] != b["lenyomat"] or a["utkozesek"] != b["utkozesek"]})
    print("<<<SZIM>>>" + json.dumps(er, ensure_ascii=False), flush=True)


def _tanulas_keret(felhasznal=False, napi=3):
    """Naponta legfeljebb `napi` elemtanulási kísérlet (a kódoló modell betöltése percekbe kerül)."""
    ma = time.strftime("%Y-%m-%d")
    a = _json_olvas("allapot.json", {})
    db = a.get("tanulas", {}).get(ma, 0)
    if felhasznal:
        a["tanulas"] = {ma: db + 1}
        _json_ir("allapot.json", a)
    return db < napi


def elem_tanul(leiras, naplo=lambda s: None, forras="hiányzó építőelem"):
    """Új építőelem megtanulása: a kódoló modell megírja, ellenőrizzük, a homokozóban kipróbáljuk (elemmel és nélküle),
    hiba esetén a hibával együtt újraírja (legfeljebb 4 kör). Siker: bekerül a tárba (aktív), és visszaadjuk a
    bejegyzését; különben None. A kódoló modell hívásai a Kovács szabályait követik (csevegés közben vár, pihenőre megáll)."""
    import tempfile

    import kovacs

    if not _tanulas_keret():
        naplo("Ma már elég új elemet próbáltam tanulni – holnap folytatom.")
        return None
    _tanulas_keret(felhasznal=True)
    meglevo = "\n".join(f"- {e['azon']}: {e['leiras'][:160]}" for e in elemek() if e.get("allapot") == "aktiv") or "none"
    feladat = (f"NEEDED CAPABILITY (from a video concept the engine could not build):\n{leiras[:1500]}\n\n"
               f"What the engine can already do without a plugin:\n{ELEMEK}\n\nAlready learned elements (do not duplicate):\n{meglevo}\n\n"
               "Return JSON: azon = short snake_case ASCII id; nev = short Hungarian name; leiras = ENGLISH usage doc for the "
               "scene planner in 1-3 sentences: what it does and every parameter of p with its sensible range; alap = "
               "which built-in scene to test it on (0 = cup with splitting balls, 1 = one growing ball in a circle, 2 = "
               "rotating rings, 3 = peg board, 4 = balls in a shrinking circle); proba_p = parameter values for the test; "
               "kod = the complete plugin module.")
    munka = tempfile.mkdtemp(prefix="kobold-szim-")
    hiba = ""
    try:
        for kor in range(4):
            naplo(f"Új építőelemet tanulok ({kor + 1}. kör): megírom a kódját…")
            d = kovacs._ollama_json(ELEM_API, feladat + (f"\n\nYOUR PREVIOUS VERSION FAILED - fix it:\n{hiba}" if hiba else ""),
                                    ELEM_SEMA, temperature=0.2 + 0.1 * kor, num_predict=3500)
            azon = "".join(c for c in str(d.get("azon") or "").lower() if c.isalnum() or c == "_")[:30] or f"elem_{int(time.time()) % 10000}"
            if any(e["azon"] == azon for e in elemek()):
                azon = f"{azon}_{int(time.time()) % 1000}"
            kod = str(d.get("kod") or "")
            hibak = elem_ellenoriz(kod)
            if os.environ.get("SZIM_DEBUG"):
                print("---- KÓD ----\n" + kod + "\n---- /KÓD ----", flush=True)
            if hibak:
                hiba = "--- code ---\n" + kod[:3000] + "\nStatic check failed: " + "; ".join(hibak)
                naplo(f"A kód nem ment át az ellenőrzésen ({hibak[0][:80]})")
                continue
            ut = os.path.join(munka, azon + ".py")
            with open(ut, "w", encoding="utf-8") as f:
                f.write(kod)
            alap = MINTAK[int(_szam(d.get("alap"), 0, len(MINTAK) - 1, 0))]
            proba_p = d.get("proba_p") if isinstance(d.get("proba_p"), dict) else {}
            spec = dict(alap, elemek=[{"azon": azon, "p": proba_p}], _elem_fajlok={azon: ut})
            naplo("Kipróbálom az új elemet a homokozóban…")
            try:
                er = homokozoban({"mod": "proba", "spec": spec}, munka, 150)
            except RuntimeError as h:
                hiba = ("--- code ---\n" + kod[:3000] + f"\nIt crashed in the test run:\n{str(h)[-1200:]}\nONLY the documented API "
                        "exists - rewrite the failing line with it (do not return the same code again).")
                naplo(f"A próbán elbukott ({str(h).strip().splitlines()[-1][:100]})")
                continue
            futasok = er.get("futasok") or []
            van_rajz = "def rajzol" in kod
            if not van_rajz and not any(f["mas_mint_nelkule"] for f in futasok):
                hiba = "--- code ---\n" + kod[:3000] + "\nIt ran without error but had NO EFFECT: the simulation was identical with and without it."
                naplo("Lefutott, de nem volt hatása – újraírom")
                continue
            if all(f["labdak_vege"] == 0 for f in futasok):
                hiba = "--- code ---\n" + kod[:3000] + "\nAfter 12 s NO balls were left on screen: it removes or loses every ball."
                naplo("Minden labdát eltüntetett – újraírom")
                continue
            if any(f["labdak_max"] >= f["keret"] > f["nelkule_max"] * 1.5 for f in futasok):
                hiba = ("--- code ---\n" + kod[:3000] + "\nRUNAWAY: within 12 s it filled the whole ball cap (the scene without it "
                        "stays far below). Never spawn / split every frame: use per-ball cooldowns (al.adat) or timers.")
                naplo("Elszabadult a labdaszám – újraírom")
                continue
            # független bíráló (a router modell, nem a kód írója): tényleg azt csinálja-e, amit kértünk, és jól használja-e az API-t
            try:
                b = kovacs._ollama_json(
                    "You review a small plugin for a 2D ball-physics video engine. Trace the code against the API below and "
                    "decide: does it REALLY implement the requested capability so that a viewer would SEE it working? Fail it "
                    "(megfelel=false) for: wrong coordinates (sz.uj_fal points are RELATIVE to kozep - absolute screen "
                    "coordinates put walls off-screen), effects that never trigger, logic unrelated to the request, a "
                    "parameter that must be set for anything to happen but has a default that disables it, spawning or "
                    "splitting every frame without cooldown, or a usage doc (leiras) that does not match the code. hiba = the "
                    "concrete problem and fix in English (empty if it passes).\n\n" + ELEM_API,
                    f"REQUESTED CAPABILITY:\n{leiras[:900]}\n\nUSAGE DOC: {d.get('leiras')}\nTEST PARAMETERS: {json.dumps(proba_p)}\n\n--- plugin code ---\n{kod[:5000]}",
                    {"type": "object", "properties": {"nyomkovetes": {"type": "string"}, "megfelel": {"type": "boolean"}, "hiba": {"type": "string"}},
                     "required": ["nyomkovetes", "megfelel", "hiba"]}, temperature=0, num_predict=1200, modell=kovacs.TARTALEK_KODOLO)
            except kovacs.Szunet:
                raise
            except Exception as h:
                b = {"megfelel": True, "hiba": ""}
                print("[SZIMULÁCIÓ] elem-bíráló hiba:", h, flush=True)
            if not b.get("megfelel", True):
                hiba = "--- code ---\n" + kod[:3000] + f"\nAn independent reviewer REJECTED it: {str(b.get('hiba'))[:700]}"
                naplo(f"A bíráló visszadobta ({str(b.get('hiba'))[:90]})")
                continue
            if any(f["szamitas_mp"] > 30 for f in futasok):
                hiba = "--- code ---\n" + kod[:3000] + "\nToo slow (over 30 s for a 12 s scene): make the per-frame work lighter."
                naplo("Túl lassú – újraírom")
                continue
            os.makedirs(ELEM_MAPPA, exist_ok=True)
            with open(os.path.join(ELEM_MAPPA, azon + ".py"), "w", encoding="utf-8") as f:
                f.write(kod)
            e = {"azon": azon, "nev": str(d.get("nev") or azon)[:40], "leiras": str(d.get("leiras") or "")[:500], "allapot": "aktiv",
                 "alap": MINTAK.index(alap), "proba_p": proba_p, "letrehozva": time.time(), "forras": forras, "keres": leiras[:500],
                 "korok": kor + 1, "hasznalva": 0, "hibak": 0}
            _json_ir("elemek.json", elemek() + [e])
            print(f"[SZIMULÁCIÓ] új építőelem megtanulva: {azon} – {e['leiras'][:160]}", flush=True)
            naplo(f"🧩 Megtanultam egy új építőelemet: {e['nev']} ({azon})")
            return e
        naplo("Ezt az elemet most nem sikerült megtanulni – a kívánságlistán marad.")
        return None
    except kovacs.Szunet:
        raise InterruptedError("megállítva")
    finally:
        shutil.rmtree(munka, ignore_errors=True)
        try:
            kovacs.kodolo_kirak()
        except Exception:
            pass


# ---------------------------------------------------------------- 📈 napi trendkutatás: mi megy most nagyot, és mi a formulája
TREND_HASHTAGEK = ["ballsimulation", "bouncingballsimulation", "satisfyingsimulation", "physicssimulation", "ballescape",
                   "2dsimulation", "bouncingballs"]
# a műfaj szűrője (mérés: a #bouncingball alatt főleg valódi sportfelvételek és 3D-renderek voltak a legnézettebbek)
TREND_KELL = _re.compile(r"(?i)simulat|physics|bounc|escape|overflow|\bring|multipl|split")
TREND_NEM = _re.compile(r"(?i)\b3d\b|blender|unreal|houdini|cloth|real ?life|football|soccer|basketball|cricket|coach|trainer|"
                        r"\bboys?\b|\bgirls?\b|athlet|gameplay|roblox|minecraft")
FORMULA_SEMA = {"type": "object", "properties": {"formulak": {"type": "array", "items": {"type": "object", "properties": {
    "sorszam": {"type": "integer"}, "illik": {"type": "boolean"}, "formula": {"type": "string"}, "kerdes": {"type": "string"},
    "miert_megy": {"type": "string"}, "hianyzik": {"type": "string"}},
    "required": ["sorszam", "illik", "formula", "kerdes", "miert_megy", "hianyzik"]}}}, "required": ["formulak"]}


def trendek():
    return _json_olvas("trendek.json", {"ido": 0, "formulak": []})


def trend_friss_kell(orak=20):
    """Naponta egyszer – vagy ha már minden formulát felhasználtunk, 6 óránként (hátha van új)."""
    t = trendek()
    kor = time.time() - float(t.get("ido") or 0)
    return kor > orak * 3600 or (kor > 6 * 3600 and all(f.get("felhasznalva") for f in t.get("formulak", [])))


def trend_megnez(url, munka, naplo=lambda s: None):
    """👀 A trendkutató MEGNÉZI a videót (2026-11-14: addig csak a címből és a leírásból találgatta a formulát): letölti
    kis felbontásban, 4 képkockát vesz belőle (eleje / közepe / vége előtt / vége), és a látó modell leírja, mi
    történik. Visszaad: {"lattam": szöveg, "hossz": mp} vagy None (ha nem sikerült – akkor marad a cím)."""
    import base64

    import clipping
    import szim_megszakitas as megszakitas
    import osszeolvadas

    os.makedirs(munka, exist_ok=True)
    vid = os.path.join(munka, "trend.mp4")
    for f_ in os.listdir(munka):
        if f_.startswith("trend"):
            os.remove(os.path.join(munka, f_))
    try:
        # a legkisebb, képet is tartalmazó formátum (a Shorts gyakran csak m3u8-ban van meg: "worst[ext=mp4]" nincs)
        megszakitas.run([clipping.YTDLP, "--no-warnings", "-q", "-f", "wv*/w", "--max-filesize", "40M", "--remux-video", "mp4",
                         "-o", vid, url], capture_output=True, text=True, timeout=180)
        if not os.path.exists(vid):
            return None
        p = megszakitas.run([FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of",
                             "csv=p=0", vid], capture_output=True, text=True, timeout=30)
        hossz = float((p.stdout or "0").strip() or 0)
        if hossz < 4:
            return None
        kepek = []
        for i, h in enumerate((0.04, 0.4, 0.75, 0.96)):
            kf = os.path.join(munka, f"trend_{i}.jpg")
            megszakitas.run([FFMPEG, "-v", "error", "-y", "-ss", f"{hossz * h:.2f}", "-i", vid, "-frames:v", "1", "-vf",
                             "scale=-2:512", kf], capture_output=True, timeout=30)
            with open(kf, "rb") as f:
                kepek.append(base64.b64encode(f.read()).decode())
        d = osszeolvadas._lat_hiv(kepek, "Four frames of ONE short vertical video in time order (start, middle, near the end, "
                                         "end). mi_tortenik: describe in 2-3 plain sentences what the video shows and how it "
                                         "changes from start to end (container / arena shape, what the balls or objects do, "
                                         "what grows or escalates, the final payoff). felirat: the on-screen text / question "
                                         "you can read (empty if none). szimulacio: true only if it is a 2D computer "
                                         "simulation (not real footage, not 3D, not a game recording).",
                                  {"mi_tortenik": {"type": "string"}, "felirat": {"type": "string"}, "szimulacio": {"type": "boolean"}},
                                  ["mi_tortenik", "felirat", "szimulacio"], num_predict=260)
        return {"lattam": (" ".join(str(d.get("mi_tortenik") or "").split())[:420]
                           + (f" On-screen text: {' '.join(str(d['felirat']).split())[:80]}" if d.get("felirat") else "")),
                "hossz": round(hossz, 1), "szimulacio": bool(d.get("szimulacio"))}
    except InterruptedError:
        raise
    except Exception as hiba:
        print("[SZIMULÁCIÓ] trend-megnézés hiba:", str(hiba)[:160], flush=True)
        return None
    finally:
        for f_ in os.listdir(munka):
            if f_.startswith("trend"):
                try:
                    os.remove(os.path.join(munka, f_))
                except OSError:
                    pass


def trend_kutat(llm, naplo=lambda s: None, napok=30):
    """Mely szimulációs shortok mentek nagyot az elmúlt hetekben (YouTube-keresés: nézettség / nap), és mi a FORMULÁJUK
    a motor építőelemeivel kifejezve. A formulát másoljuk (mechanika, kérdés, csattanó), a videót, a címet, a csatorna
    arculatát nem. Az eredmény a trendek.json-ba kerül; a korábban már felhasznált formulák jelölése megmarad."""
    import clipping
    import szim_megszakitas as megszakitas

    # 1) a műfaj hashtag-oldalainak Shorts-listái (gyors: azonosító + nézettség), 2) a legnézettebbek adatai egyenként
    # (feltöltés dátuma, cím, leírás), 3) rangsor: nézettség / nap az elmúlt hetekben feltöltöttek között.
    # (Mérés: a sima YouTube-keresés hosszú, régi válogatásokat ad, dátumszűrővel szinte semmit.)
    jeloltek = {}
    for h in TREND_HASHTAGEK:
        naplo(f"Trendkutatás: #{h}")
        try:
            p = megszakitas.run([clipping.YTDLP, "--flat-playlist", "--no-warnings", "--ignore-errors", "--playlist-end", "60", "--print",
                                 "%(id)s|%(view_count)s", f"https://www.youtube.com/hashtag/{h}/shorts"],
                                capture_output=True, text=True, timeout=120)
        except InterruptedError:
            raise
        except Exception as hiba:
            print("[SZIMULÁCIÓ] trendkeresés hiba:", hiba, flush=True)
            continue
        for sor in (p.stdout or "").splitlines():
            vid, _, nez = sor.partition("|")
            if vid and nez.isdigit():
                jeloltek[vid] = max(int(nez), jeloltek.get(vid, 0))
    videok = {}
    naplo(f"Trendkutatás: {len(jeloltek)} shortból a legnézettebbek adatait kérem le")
    for vid, _ in sorted(jeloltek.items(), key=lambda x: -x[1])[:60]:
        try:
            p = megszakitas.run([clipping.YTDLP, "--skip-download", "--no-warnings", "--print",
                                 "%(.{id,view_count,like_count,upload_date,duration,channel,channel_follower_count,title,description})j",
                                 f"https://www.youtube.com/shorts/{vid}"], capture_output=True, text=True, timeout=60)
            v = json.loads((p.stdout or "").strip().splitlines()[-1])
            kor = max(1.0, (time.time() - time.mktime(time.strptime(v["upload_date"], "%Y%m%d"))) / 86400)
        except InterruptedError:
            raise
        except Exception:
            continue
        szoveg = f"{v.get('title') or ''} {str(v.get('description') or '')[:300]}"
        if not v.get("view_count") or (v.get("duration") or 0) > 90 or not TREND_KELL.search(szoveg) or TREND_NEM.search(szoveg):
            continue
        videok[vid] = {"url": f"https://www.youtube.com/shorts/{vid}", "cim": str(v.get("title") or "")[:120],
                       "csatorna": str(v.get("channel") or "")[:60], "nezettseg": int(v["view_count"]),
                       "napi_nezettseg": int(v["view_count"] / kor), "napos": round(kor), "kedveles": v.get("like_count"),
                       "hossz": v.get("duration"), "kovetok": v.get("channel_follower_count"),
                       "leiras": " ".join(str(v.get("description") or "").split())[:220]}
        e = videok[vid]
        # 🚀 KIUGRÓ: a nézettség a csatorna követőszámához képest – a kis csatorna nagyot menő videója a FORMULA érdeme,
        # nem a csatorna méretéé (0,6–2,5× szorzó a rangsorban; ha nincs követőszám: 1,0)
        # (mérés 2026-11-14: a műfaj felkapott shortjainál a nézettség a követőszám 50–1100-szorosa -> 100× = 1,0)
        e["kiugro"] = round(max(0.6, min(2.5, (e["nezettseg"] / max(1.0, float(e["kovetok"] or 0) or e["nezettseg"] / 100.0)
                                               / 100.0) ** 0.3)), 2)
        # ⚡ GYORSULÁS: ha tegnap is láttuk, a tegnap óta jött napi nézettség (ami MOST megy, nem ami régen ment)
        elozo = (trendek().get("latott") or {}).get(vid)
        if elozo and time.time() - elozo[0] > 0.4 * 86400 and e["nezettseg"] >= elozo[1]:
            e["friss_napi"] = int((e["nezettseg"] - elozo[1]) / ((time.time() - elozo[0]) / 86400))
        e["rang"] = max(e["napi_nezettseg"], e.get("friss_napi") or 0) * e["kiugro"]
    latott = {**(trendek().get("latott") or {}), **{vid: [time.time(), v["nezettseg"]] for vid, v in videok.items()}}
    latott = dict(sorted(latott.items(), key=lambda x: -x[1][0])[:300])
    frissek = {k: v for k, v in videok.items() if v["napos"] <= napok}
    if len(frissek) >= 4:  # ha van elég friss, csak azok számítanak; különben a tágabb időszak
        videok = frissek
    top = sorted(videok.values(), key=lambda v: -v["rang"])[:14]
    # 👀 a legjobb 5-öt MEG IS NÉZI (képkockák + látó modell): a formula a látottakból jön, nem csak a címből
    for i, v in enumerate(top[:5]):
        naplo(f"Trendkutatás: megnézem a(z) {i + 1}. videót ({v['napi_nezettseg']:,}/nap)")
        latas = trend_megnez(v["url"], os.path.join(MAPPA, "trend_munka"), naplo)
        if latas:
            v["lattam"] = latas["lattam"]
            v["hossz"] = latas["hossz"] or v.get("hossz")
            if not latas["szimulacio"]:
                v["nem_szim"] = True
    top = [v for v in top if not v.get("nem_szim")]
    if not top:
        print("[SZIMULÁCIÓ] trendkutatás: nincs találat (a korábbi trendek maradnak)", flush=True)
        return trendek()
    naplo(f"Trendkutatás: {len(videok)} friss videóból a {len(top)} legnézettebb formuláját fejtem meg")
    d = llm("You analyse viral 2D physics-simulation shorts (bouncing balls, 'will it overflow', escape the ring...). For each "
            "video below, infer its FORMULA from the title and description: the on-screen question, the container, what "
            "the balls do, the RULE that escalates it, and the payoff - written as one concrete English concept (2-3 "
            "sentences) that can be rebuilt with the engine's building blocks below. kerdes = a short hook question for our "
            "own version (our own wording, not the original title). miert_megy = one sentence: why it gets views (tension, "
            "escalation, satisfying sound, clear question). illik = false if it is NOT a 2D ball / physics simulation we "
            "could rebuild (e.g. 3D render, real footage, a game). hianyzik = the capability the building blocks lack for "
            "this formula, in one sentence (empty if they suffice).\n\n" + ELEMEK
            + "\nLearned extra elements: " + ("; ".join(f"{e['azon']} = {e['leiras'][:120]}" for e in elemek() if e.get("allapot") == "aktiv") or "none"),
            "\n".join(f"{i + 1}. \"{v['cim']}\" – {v['csatorna']}, {v['nezettseg']:,} views in {v['napos']} days"
                      + (f", {v['hossz']:.0f} s long" if v.get("hossz") else "") + f". {v['leiras']}"
                      + (f" WHAT THE VIDEO ACTUALLY SHOWS (watched): {v['lattam']}" if v.get("lattam") else "")
                      for i, v in enumerate(top)), FORMULA_SEMA, num_predict=3500, temperature=0.3)
    if os.environ.get("SZIM_DEBUG"):
        print("TOP:", json.dumps(top, ensure_ascii=False)[:2500], "\nLLM:", json.dumps(d, ensure_ascii=False)[:2500], flush=True)
    regi = {f["url"]: f for f in trendek().get("formulak", [])}
    ujak = []
    for f in d.get("formulak") or []:
        i = int(f.get("sorszam") or 0) - 1
        if 0 <= i < len(top) and f.get("illik") and str(f.get("formula") or "").strip():
            v = top[i]
            ujak.append({**v, "formula": str(f["formula"]).strip()[:600], "kerdes": str(f.get("kerdes") or "").strip()[:48],
                         "miert_megy": str(f.get("miert_megy") or "").strip()[:200], "hianyzik": str(f.get("hianyzik") or "").strip()[:300],
                         "felhasznalva": (regi.get(v["url"]) or {}).get("felhasznalva", 0), "talalva": (regi.get(v["url"]) or {}).get("talalva") or time.time()})
    # a korábbi, még fel nem használt formulák 5 napig megmaradnak (ha ma kevés az új)
    megtart = [f for u, f in regi.items() if u not in {x["url"] for x in ujak} and not f.get("felhasznalva")
               and time.time() - float(f.get("talalva") or 0) < 5 * 86400]
    hosszak = sorted(float(f["hossz"]) for f in ujak if f.get("hossz"))
    adat = {"ido": time.time(), "formulak": sorted(ujak + megtart, key=lambda f: -(f.get("rang") or f["napi_nezettseg"]))[:20],
            "latott": latott, "hossz_median": hosszak[len(hosszak) // 2] if len(hosszak) >= 4 else None}
    _json_ir("trendek.json", adat)
    print(f"[SZIMULÁCIÓ] trendkutatás: {len(ujak)} formula ({len(videok)} videóból); legjobb: "
          + (f"\"{ujak[0]['cim'][:60]}\" {ujak[0]['napi_nezettseg']:,}/nap" if ujak else "–"), flush=True)
    return adat


def trend_kovetkezo():
    """A legkevesebbszer felhasznált (azon belül a legnézettebb) trend-formula, vagy None. Ha már mindet feldolgoztuk,
    a legjobbakból készül ÚJ változat (a "felhasznalva" mutatja, hányadik) – régen ilyenkor formula nélkül ment a munka."""
    lista = trendek().get("formulak", [])
    return min(lista, key=lambda f: (int(f.get("felhasznalva") or 0), -(f.get("rang") or f["napi_nezettseg"]))) if lista else None


def trend_felhasznal(url):
    adat = trendek()
    for f in adat.get("formulak", []):
        if f["url"] == url:
            f["felhasznalva"] = int(f.get("felhasznalva") or 0) + 1
    _json_ir("trendek.json", adat)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--gyerek":
        _gyerek_fo(sys.argv[2])
        sys.exit(0)
    minta = MINTAK[int(sys.argv[1]) if len(sys.argv) > 1 else 0]
    hova = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MAPPA, "proba.mp4")
    eredmeny = keszit(minta, hova, halad=lambda s: print("  ", s, flush=True), keret_mp=int(os.environ.get("SZIM_KERET", 45)))
    print(json.dumps(eredmeny["meres"], ensure_ascii=False, indent=1))
    print(hova)


# ---------------------------------------------------------------- ✂ rövidebb változat (Instagram)
def rovid_valtozat(szim, cel, max_mp, munka=None, halad=lambda s: None, ellenoriz=lambda: None):
    """✂ Ugyanaz a receptes videó rövidebben (az Instagram a ~30 mp-nél hosszabb Reelst API-n visszadobja): UGYANAZ a
    lefutás (spec a végső tempóval + mag) – minden 1,x-edik fizikai lépés kerül képre, így az események gyorsabban
    jönnek; a hangesemények az új időpontokban, EREDETI hangszínnel / hosszal szólnak, a dal is eredeti tempóban megy
    (a dropja az új hosszhoz igazítva). Előbb ellenőrzi, hogy a lefutás pontosan ugyanaz-e (lenyomat). Visszaad:
    {hossz, gyors, vege_ido}."""
    import math as _m

    munka = munka or os.path.dirname(cel)
    os.makedirs(munka, exist_ok=True)
    spec, mag, meres = szim["spec"], szim["mag"], szim.get("meres") or {}
    if spec.get("elemek"):
        raise RuntimeError("tanult (homokozós) építőelemmel készült videó – nem renderelem újra")
    spec = json.loads(json.dumps(spec))   # a mentett (már tisztított, végső tempójú) spec – változatlanul
    if meres.get("tempo"):
        spec["tempo"] = meres["tempo"]
    halad("Ugyanaz a lefutás: a fizika újrafuttatása az eredeti maggal")
    e0 = futtat(spec, mag)
    if meres.get("lenyomat") and e0["lenyomat"] != meres["lenyomat"] or \
            meres.get("utkozesek") is not None and e0["utkozesek"] != meres["utkozesek"]:
        raise RuntimeError("az újrafuttatás nem pontosan ugyanaz, mint az eredeti – nem renderelem újra")
    lepesek = int(round(e0["hossz"] * FPS))
    gyors = max(1.0, lepesek / (max_mp * FPS) * 1.005)
    if gyors > 3.0:
        raise RuntimeError(f"{max_mp} mp-re csak háromszorosnál nagyobb gyorsítással férne rá")
    n_kep = int(_m.floor((lepesek - 1) / gyors)) + 1
    hossz = n_kep / FPS
    vege = e0.get("vege_ido")
    lesz_vege = vege is not None
    halad(f"Gyorsítás: {gyors:.2f}× (≤ {max_mp:.0f} mp), a hangok eredeti sebességgel")
    zene, zene_terv, zt_fiz = None, None, None
    if spec["hang"]["zene"] not in ("nincs", "trend", "brainrot"):
        import szim_trendhang as trendhang
        zene = trendhang.zene(spec["hang"]["zene"])
    if zene:
        try:
            zene_terv = trendhang.drop_terv(zene["fajl"], hossz, FFMPEG, csattano=vege / gyors if lesz_vege else None)
            # a rajz a fizikai időt látja: a drop és az ütemek fizikai időben
            zt_fiz = dict(zene_terv, drop=zene_terv["drop"] * gyors if zene_terv.get("drop") is not None else None,
                          utemek=[u * gyors for u in zene_terv.get("utemek") or []])
        except Exception as hiba_:
            print(f"[SZIMULÁCIÓ] drop-elemzés nem sikerült: {hiba_}", flush=True)
    rajz = Rajzolo(spec, veg_felirat=None if lesz_vege or spec["vege"]["mikor"] == "ido" else spec["kudarc_felirat"], zene_terv=zt_fiz)
    nema = os.path.join(munka, "szim_nema.mp4")
    ff = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{rajz.W}x{rajz.H}",
                           "-r", str(FPS), "-i", "-", "-vf", f"scale={SZ}:{M}:flags=area", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "20", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p", nema], stdin=subprocess.PIPE)
    allapot = {"lepes": 0, "kep": 0}

    def kocka(sz):
        allapot["lepes"] += 1
        if allapot["kep"] < n_kep and allapot["lepes"] - 1 >= round(allapot["kep"] * gyors):   # minden gyors-adik lépés
            ff.stdin.write(rajz.kep(sz).tobytes())
            allapot["kep"] += 1
            if allapot["kep"] % 60 == 0:
                ellenoriz()
                halad(f"Renderelés: {min(99, int(100 * allapot['kep'] / n_kep))}%")
    try:
        e = futtat(spec, mag, kepkocka=kocka)
    finally:
        try:
            ff.stdin.close()
        except Exception:
            pass
        ff.wait(timeout=600)
    if ff.returncode != 0 or not os.path.exists(nema):
        raise RuntimeError("a videó kódolása nem sikerült (ffmpeg)")
    hossz = allapot["kep"] / FPS
    halad("Hang: ugyanazok a hangok, az új időpontokban")
    wav = os.path.join(munka, "szim_hang.wav")
    hangok = [(h[0] / gyors,) + tuple(h[1:]) for h in e["hangok"]]
    idovonal = [(round(x[0] / gyors, 2),) + tuple(x[1:]) for x in e.get("idovonal") or []]
    hang_ir(hangok, hossz, spec["hang"], wav,
            kudarc_ido=None if lesz_vege or spec["vege"]["mikor"] == "ido" else max(0.0, hossz - 2.4),
            idovonal=idovonal, labdak_max=e["labdak_max"], tulcs2=bool(spec.get("tulcs2")))
    if zene:
        import szim_trendhang as trendhang
        trendhang.kever(nema, wav, zene["fajl"], hossz, cel, FFMPEG, csattano=vege / gyors if lesz_vege else None,
                        kezd=(zene_terv or {}).get("kezd"), ismetel=(zene_terv or {}).get("ismetel"))
    else:
        r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", nema, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                            "-shortest", "-movflags", "+faststart", cel], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"a hang rákeverése nem sikerült: {r.stderr[-200:]}")
    for f in (nema, wav):
        try:
            os.remove(f)
        except OSError:
            pass
    return {"hossz": round(hossz, 2), "gyors": round(gyors, 3), "vege_ido": round(vege / gyors, 2) if lesz_vege else None}
