"""🧪 Szimulációs RECEPTEK: kipróbált, jól működő videótípusok szűk, biztonságos változási tartományokkal.

Miért: a szabad (nyelvi modell által kitalált) tervek ~80%-a elbukott az appban (2026-11-10: 38 videóból ~30 elvetve:
nem jött el a csattanó, 1 labda a „350 labdás” videóban, káosz az elején, unalmas hang, és szinte mind ugyanaz a
„Exponential Growth vs Shrinking Rings” lett). A kézzel hangolt minták viszont jók voltak. Ezért:

  * minden recept egy BEVÁLT alap-terv (szimulacio SPEC) + a változtatható pontjai (paletta, méretek, tempó, hangszer,
    dallam, mém-hang, kérdés-sablonok, cím-sablonok) a még biztosan működő tartományban;
  * a gyártás a receptből húz változatot, a mért minőségkapu (szimulacio.minoseg) ellenőrzi RENDERELÉS ELŐTT, és ha
    nem megy át, új változat, végül a recept alap-terve (az mindig átmegy) – így minden kész videó kitehető;
  * a választás az eredményekből tanul – BANDIT (Thompson-mintavétel, 2026-11-14): minden videó 0..1 jutalmat ad
    (teljesitmeny.jutalom: elvetett 0; mért videó a KÖZÖS pontszámból – azonos korban mért, csatornánként normált
    nézettség × megtartás; jóváhagyott, de még méretlen 0,55). Receptenként és változó-értékenként (paletta, hangszer,
    dallam, zene…) Beta-eloszlás; a sorsolás a jobbakat gyakrabban hozza, de a keveset próbáltaknak is ad esélyt.
    Ugyanaz a recept nem jön kétszer egymás után (változatosság);
  * a HOSSZ is tanul (hossz_szorzo): ha már elég a mért videó, a legjobb harmad hossza és a megtartási görbék (t50:
    meddig marad a nézők fele) felé húz, ±15%-on belül;
  * továbbra is fejlődik: időnként (KISERLET_ARANY) szabad kísérlet készül; ami ebből jóváhagyást kap, TANULT
    RECEPT lesz (~/.kobold/szimulacio/tanult_receptek.json), és onnantól ugyanígy változatokat húzhat belőle.
"""
import copy
import json
import math
import os
import random
import re
import time

import szim_engine as S
import szim_teljesitmeny as teljesitmeny

TANULT_FAJL = os.path.join(S.MAPPA, "tanult_receptek.json")
KISERLET_ARANY = 0.15            # ennyi eséllyel készül szabad kísérlet a receptek helyett (fejlődés)
JO = ("jovahagyva", "feltoltes", "feltoltve")
VICCES_HANGSZER = ["pop", "boing", "buborek", "vizcsepp", "koppanas", "8bit", "xilofon"]
DALLAMOS = ["marimba", "xilofon", "zongora", "harang", "pengetes"]
HIRES = ["fur_elise", "korobeiniki", "hegyi_kiraly", "orom_oda", "torok_indulo", "csillag", "kanon"]

# változó-leírás: "ut.a.b": [lehetőségek] (választás) vagy ("tart", min, max) / ("egesz", min, max)
RECEPTEK = [
    {"azon": "tulcsordulas", "nev": "Túlcsordul a pohár?", "ikon": "🥤",
     "leiras": "TÚLCSORDULÁS 2.0 – PIROS vs KÉK: két világító forrás-labda (piros és kék) a kupac tetején pattog, minden becsapódásra új labdák (gyorsuló "
               "szorzó: x1 → x2 → x4); csak a repülő labdák osztódnak. Felül piros–kék arány-sáv (koronával a vezetőn), lendület-váltások "
               "(X IS ON FIRE!), vezetőváltás (X TAKES THE LEAD!), 3–4 mp-enként fordulat (lefolyó, nagyobb pohár, labdaeső, turbó, "
               "színcsere), élő kamera, veszély-vignetta és szívverés a perem közelében, lassítás + ráközelítés, a peremre kiülő labdák "
               "legurulnak. Vége: az a szín nyer, amelyikből előbb csordul ki 5 labda – a pohár szétrobban, konfetti, X WINS!, "
               "COMMENT YOUR COLOR!, és az utolsó kocka visszaúszik az elsőbe (loop).",
     "kulcs": r"(?i)overflow|t[uú]lcsordul|poh[aá]r",
     "alap": {"tulcs2": True, "cim": "Will it overflow?", "kerdes": "Will it overflow?", "hossz": 32, "paletta": "neon", "gravitacio": 900,
              "palya": {"tipus": "pohar", "meret": 0.9, "forog": 0, "res": 0, "gyuruk": 1},
              "labdak": {"db": 1, "sugar": 32, "sebesseg": 500, "ruganyossag": 0.86, "indulas": "fent", "adagolas": 0, "max": 1500},
              "szabalyok": [{"mikor": "labda_fal", "mit": "osztodik", "ertek": 1.0, "esely": 1, "varakozas": 0.9}],
              "vege": {"mikor": "tulcsordul", "ertek": 5}, "szamlalo": "labdak",
              "hang": {"hangszer": "marimba", "dallam": "emelkedo", "zene": "nincs", "meme": "trend", "meme_mod": "merfoldko"},
              "latvany": {"stilus": "tele", "nyom": True}, "siker_felirat": "OVERFLOW!", "kudarc_felirat": "IT HELD!", "hianyzik": ""},
     "valtozok": {"paletta": ["neon", "jeg", "szivarvany", "mono"],   # sötét háttér: a piros és a kék világítson "palya.meret": ("tart", 0.86, 0.93), "labdak.sugar": ("tart", 30, 35),
                  "szabalyok.0.varakozas": ("tart", 0.8, 1.05), "gravitacio": ("tart", 820, 1000),
                  "hang.hangszer": ["marimba", "xilofon", "pop", "buborek", "8bit", "vizcsepp"], "hang.dallam": ["emelkedo", "meret"],
                  "hang.zene": ["trend", "nincs"], "latvany.stilus": ["tele"]},
     "kerdesek": ["Which color overflows first?", "Red or blue: who overflows first?", "Pick a color: who spills first?",
                  "Red vs blue: who overflows the cup?", "Which color wins the overflow?"],
     "cimek": ["Red vs Blue: which color overflows first? 🔴🔵", "Pick a color before it overflows 😳", "Which color spills first? 🥤",
               "Red or blue? Comment your color before the overflow", "The drain almost saved it… red vs blue 🫗"]},

    {"azon": "szokes", "nev": "Kijut a gyűrűkből?", "ikon": "⭕",
     "leiras": "Egy labda forgó, réses gyűrűkben; pattanáskor néha kettéválik – kijut-e a legkülső gyűrűn túl.",
     "alap": {"cim": "Can it escape?", "kerdes": "Can it escape?", "hossz": 35, "paletta": "szivarvany", "gravitacio": 500,
              "palya": {"tipus": "gyuru", "meret": 0.95, "forog": 55, "res": 32, "gyuruk": 3},
              "labdak": {"db": 1, "sugar": 16, "sebesseg": 600, "ruganyossag": 1.0, "indulas": "kozep", "adagolas": 0, "max": 60},
              "szabalyok": [{"mikor": "labda_fal", "mit": "osztodik", "ertek": 1.0, "esely": 0.5, "varakozas": 1.2}],
              "vege": {"mikor": "kijut", "ertek": 1}, "szamlalo": "kijutottak",
              "hang": {"hangszer": "boing", "dallam": "hegyi_kiraly", "zene": "nincs", "meme": "trend", "meme_mod": "auto"},
              "latvany": {"stilus": "tele", "nyom": True}, "siker_felirat": "ESCAPED!", "kudarc_felirat": "TRAPPED", "hianyzik": ""},
     "valtozok": {"paletta": list(S.PALETTAK), "palya.forog": ("tart", 42, 65), "palya.res": ("tart", 28, 36),
                  "palya.gyuruk": [2, 3, 3, 4], "labdak.sugar": ("tart", 14, 18), "szabalyok.0.esely": ("tart", 0.4, 0.6),
                  "hang.hangszer": VICCES_HANGSZER + ["marimba"], "hang.dallam": HIRES + ["emelkedo"],
                  "latvany.stilus": ["tele", "neon"]},
     "kerdesek": ["Can it escape?", "Can {n} balls escape?", "Will any ball get out?", "Escape the spinning rings?"],
     "cimek": ["Can one ball escape the spinning rings? ⭕", "It splits on every bounce… can it escape?",
               "Escape the rings challenge 🔥", "Will it get out? Wait for it…"]},

    {"azon": "novo", "nev": "Minden pattanás = nagyobb", "ikon": "🎈",
     "leiras": "Egy labda súlytalanul pattog egy körben, minden pattanásnál nő és színt vált; minden pattanás egy hang "
               "egy ismert dallamból – a végén betölti a kört.",
     "alap": {"cim": "The ball grows every bounce", "kerdes": "Every bounce = bigger", "hossz": 30, "paletta": "tuz", "gravitacio": 0,
              "palya": {"tipus": "kor", "meret": 0.9, "forog": 0, "res": 0, "gyuruk": 1},
              "labdak": {"db": 1, "sugar": 22, "sebesseg": 800, "ruganyossag": 1.0, "indulas": "kozep", "adagolas": 0, "max": 5},
              "szabalyok": [{"mikor": "labda_fal", "mit": "no", "ertek": 1.07, "esely": 1, "varakozas": 0.05},
                            {"mikor": "labda_fal", "mit": "szinvalt", "ertek": 1, "esely": 1, "varakozas": 0.05}],
              "vege": {"mikor": "betelt", "ertek": 0.8}, "szamlalo": "utkozesek",
              "hang": {"hangszer": "zongora", "dallam": "fur_elise", "zene": "nincs", "meme": "trend", "meme_mod": "pattanas"},
              "latvany": {"stilus": "neon", "nyom": True}, "siker_felirat": "FULL!", "kudarc_felirat": "SO CLOSE", "hianyzik": ""},
     "valtozok": {"paletta": list(S.PALETTAK), "palya.meret": ("tart", 0.82, 0.95), "labdak.sebesseg": ("tart", 700, 900),
                  "szabalyok.0.ertek": ("tart", 1.05, 1.08), "hang.hangszer": DALLAMOS + ["8bit", "boing", "kacsa"],
                  "hang.dallam": HIRES, "hang.meme_mod": ["pattanas", "pattanas", "merfoldko"], "latvany.stilus": ["tele", "neon"]},
     "kerdesek": ["Every bounce = bigger", "It grows on every bounce", "Can it fill the circle?", "Every bounce plays a note"],
     "cimek": ["Every bounce makes it bigger 🎈", "This ball plays a song while it grows 🎵", "Can it fill the whole circle?",
               "Bounce, grow, repeat… 😮‍💨"]},

    {"azon": "szukulo", "nev": "Összeszűkülő aréna", "ikon": "🫨",
     "leiras": "Néhány labda súlytalanul egy körben, minden falpattanás összébb húzza az arénát – a végén összepréseli őket.",
     "alap": {"cim": "The arena shrinks on every hit", "kerdes": "The walls close in", "hossz": 30, "paletta": "mono", "gravitacio": 0,
              "palya": {"tipus": "kor", "meret": 1.0, "forog": 0, "res": 0, "gyuruk": 1},
              "labdak": {"db": 6, "sugar": 30, "sebesseg": 700, "ruganyossag": 1.0, "indulas": "szorva", "adagolas": 0, "max": 60},
              "szabalyok": [{"mikor": "labda_fal", "mit": "palya_szukul", "ertek": 0.988, "esely": 1, "varakozas": 0.2},
                            {"mikor": "labda_labda", "mit": "szinvalt", "ertek": 1, "esely": 1, "varakozas": 0.1}],
              "vege": {"mikor": "betelt", "ertek": 0.45}, "szamlalo": "utkozesek",
              "hang": {"hangszer": "pop", "dallam": "meret", "zene": "trend", "meme": "trend", "meme_mod": "merfoldko"},
              "latvany": {"stilus": "tele", "nyom": True}, "siker_felirat": "CRUSHED!", "kudarc_felirat": "SURVIVED", "hianyzik": ""},
     "valtozok": {"paletta": list(S.PALETTAK), "labdak.db": [6, 7], "labdak.sugar": ("tart", 28, 32),
                  "szabalyok.0.ertek": ("tart", 0.984, 0.989), "hang.hangszer": VICCES_HANGSZER, "hang.zene": ["trend", "nincs"],
                  "latvany.stilus": ["tele", "neon"]},
     "kerdesek": ["The walls close in", "Every hit shrinks the arena", "How long until they're crushed?", "No space left?"],
     "cimek": ["Every hit makes the arena smaller 😬", "The walls are closing in…", "Satisfying shrinking arena",
               "They can't escape the shrinking circle"]},

    {"azon": "res_no", "nev": "Nő a rés", "ikon": "🚪",
     "leiras": "Egy labda egy forgó gyűrűben, minden pattanásnál szélesebb lesz a rés – mikor jut ki?",
     "alap": {"cim": "The gap grows every bounce", "kerdes": "Every bounce = bigger gap", "hossz": 32, "paletta": "neon", "gravitacio": 600,
              "palya": {"tipus": "gyuru", "meret": 0.8, "forog": 60, "res": 14, "gyuruk": 1},
              "labdak": {"db": 1, "sugar": 20, "sebesseg": 700, "ruganyossag": 1.0, "indulas": "kozep", "adagolas": 0, "max": 5},
              "szabalyok": [{"mikor": "labda_fal", "mit": "res_no", "ertek": 1.2, "esely": 1, "varakozas": 0.3},
                            {"mikor": "labda_fal", "mit": "szinvalt", "ertek": 1, "esely": 1, "varakozas": 0.05}],
              "vege": {"mikor": "kijut", "ertek": 1}, "szamlalo": "utkozesek",
              "hang": {"hangszer": "xilofon", "dallam": "korobeiniki", "zene": "nincs", "meme": "trend", "meme_mod": "pattanas"},
              "latvany": {"stilus": "neon", "nyom": True}, "siker_felirat": "FREEDOM!", "kudarc_felirat": "TRAPPED", "hianyzik": ""},
     "valtozok": {"paletta": list(S.PALETTAK), "palya.forog": ("tart", 45, 80), "palya.res": ("tart", 10, 16),
                  "labdak.sugar": ("tart", 16, 22), "szabalyok.0.ertek": ("tart", 0.8, 1.5), "gravitacio": ("tart", 400, 800),
                  "hang.hangszer": DALLAMOS + ["8bit", "boing", "kacsa", "ugras"], "hang.dallam": HIRES,
                  "latvany.stilus": ["tele", "neon"]},
     "kerdesek": ["Every bounce = bigger gap", "When will it escape?", "The gap grows every bounce", "Will it get out?"],
     "cimek": ["Every bounce makes the gap bigger 🚪", "When will it finally escape? 😤", "The exit grows on every bounce",
               "Wait for the escape… 🎵"]},

    {"azon": "utolso", "nev": "Csak egy marad", "ikon": "🏆",
     "leiras": "Sok labda súlytalanul egy körben; ha két labda ütközik, az egyik eltűnik – az utolsó a győztes.",
     "alap": {"cim": "Only one survives", "kerdes": "Only 1 will survive", "hossz": 34, "paletta": "szivarvany", "gravitacio": 0,
              "palya": {"tipus": "kor", "meret": 0.95, "forog": 0, "res": 0, "gyuruk": 1},
              "labdak": {"db": 20, "sugar": 20, "sebesseg": 520, "ruganyossag": 1.0, "indulas": "szorva", "adagolas": 0, "max": 40},
              "szabalyok": [{"mikor": "labda_labda", "mit": "eltunik", "ertek": 1, "esely": 0.5, "varakozas": 0.4}],
              "vege": {"mikor": "utolso", "ertek": 1}, "szamlalo": "labdak",
              "hang": {"hangszer": "pop", "dallam": "veletlen", "zene": "trend", "meme": "trend", "meme_mod": "merfoldko"},
              "latvany": {"stilus": "tele", "nyom": True}, "siker_felirat": "WINNER!", "kudarc_felirat": "TOO MANY", "hianyzik": ""},
     "valtozok": {"paletta": list(S.PALETTAK), "labdak.db": [14, 16, 18, 20, 24], "labdak.sugar": ("tart", 17, 23),
                  "szabalyok.0.esely": ("tart", 0.3, 0.6), "labdak.sebesseg": ("tart", 420, 600),
                  "hang.hangszer": VICCES_HANGSZER, "hang.zene": ["trend", "nincs"], "latvany.stilus": ["tele", "neon"]},
     "kerdesek": ["Only 1 will survive", "Last ball standing wins", "Who will be the last one?", "Every crash = one gone"],
     "cimek": ["Only one ball will survive 🏆", "Last ball standing… who wins?", "Every crash removes a ball 😳",
               "Battle royale, but it's balls"]},
]


# ---------------------------------------------------------------- tár (tanult receptek)

def _olvas():
    try:
        with open(TANULT_FAJL, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _ir(lista):
    os.makedirs(S.MAPPA, exist_ok=True)
    with open(TANULT_FAJL + ".tmp", "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(TANULT_FAJL + ".tmp", TANULT_FAJL)


def osszes():
    return RECEPTEK + [r for r in _olvas() if r.get("aktiv", True)]


def recept(azon):
    return next((r for r in osszes() if r["azon"] == azon), None)


# ---------------------------------------------------------------- változat húzása

def _beallit(spec, ut, ertek):
    reszek = ut.split(".")
    cel = spec
    for r in reszek[:-1]:
        cel = cel[int(r)] if r.isdigit() else cel.setdefault(r, {})
    utolso = reszek[-1]
    if utolso.isdigit():
        cel[int(utolso)] = ertek
    else:
        cel[utolso] = ertek


def _olvas_ut(spec, ut):
    cel = spec
    for r in ut.split("."):
        try:
            cel = cel[int(r)] if r.isdigit() else cel[r]
        except (KeyError, IndexError, TypeError):
            return None
    return cel


def _huz(leiras, rnd):
    if isinstance(leiras, tuple):
        tip, a, b = leiras
        return round(rnd.uniform(a, b), 3) if tip == "tart" else rnd.randint(int(a), int(b))
    return rnd.choice(leiras)


def ertek_tapasztalat(klipek, r):
    """🎰 Változó-értékenként a jutalmak: {út: {érték: [siker, kudarc]}} a recept eddigi videóiból (csak a felsorolásos
    változókra: paletta, hangszer, dallam, zene…)."""
    ki = {}
    for k in _recept_klipjei(klipek, r["azon"]):
        j = teljesitmeny.jutalom(k, JO)
        if j is None:
            continue
        for ut, leiras in r.get("valtozok", {}).items():
            if isinstance(leiras, list):
                v = _olvas_ut(k["szim"]["spec"], ut)
                if isinstance(v, (str, int, float, bool)) and v in leiras:
                    e = ki.setdefault(ut, {}).setdefault(v, [0.0, 0.0])
                    e[0] += j
                    e[1] += 1 - j
    return ki


def valtozat(r, rnd=None, kozeli=None, alap_csak=False, kerul=(), tapasztalat=None):
    """Egy változat a receptből (SPEC). kozeli: egy bevált (jóváhagyott / sokat nézett) videó SPEC-je ebből a receptből –
    ilyenkor annak értékei körül marad (kiaknázás); alap_csak: csak kozmetikai változás (paletta, kérdés), a fizika a
    bevált alap. kerul: ezeket a palettákat / hangszereket most kerüljük (az előző videók). tapasztalat: az értékek
    eddigi jutalmai (ertek_tapasztalat) – a felsorolásos változók ebből Thompson-mintavétellel választanak."""
    rnd = rnd or random.Random()
    spec = copy.deepcopy(r["alap"])
    for ut, leiras in r.get("valtozok", {}).items():
        fizika = not (ut.startswith(("paletta", "hang.", "latvany.")))
        if alap_csak and fizika:
            continue
        if kozeli is not None and rnd.random() < 0.6:
            v = _olvas_ut(kozeli, ut)
            if v is not None:
                _beallit(spec, ut, v)
                continue
        jelolt = leiras
        if isinstance(leiras, list) and kerul:
            jelolt = [x for x in leiras if x not in kerul] or leiras
        if isinstance(jelolt, list) and tapasztalat and tapasztalat.get(ut):   # 🎰 Thompson: a bevált értékek gyakrabban
            t_ = tapasztalat[ut]
            _beallit(spec, ut, max(jelolt, key=lambda x: rnd.betavariate(1 + t_.get(x, [0, 0])[0], 1 + t_.get(x, [0, 0])[1])))
            continue
        _beallit(spec, ut, _huz(jelolt, rnd))
    kerdesek = r.get("kerdesek") or [spec["kerdes"]]
    k = rnd.choice(kerdesek)
    spec["kerdes_sablon"] = k
    spec["kerdes"] = k.replace("{n}", str(int(spec["vege"]["ertek"])))
    spec["cim"] = rnd.choice(r.get("cimek") or [spec["cim"]])
    spec["recept"] = r["azon"]
    return spec


# ---------------------------------------------------------------- tanulás az eredményekből

def _recept_klipjei(klipek, azon):
    return [k for k in klipek if ((k.get("szim") or {}).get("spec") or {}).get("recept") == azon and not k.get("tanulasbol_kizarva")]


def statisztika(klipek):
    """Receptenként: készült, jóváhagyva, elvetve, átlagos megtekintés, utolsó használat."""
    ki = {}
    for r in osszes():
        ks = _recept_klipjei(klipek, r["azon"])
        nez = [int(k.get("megtekintes") or 0) for k in ks if k.get("megtekintes") is not None]
        ki[r["azon"]] = {"nev": r["nev"], "ikon": r.get("ikon", "🎱"), "keszult": len(ks),
                         "jovahagyva": sum(1 for k in ks if k.get("allapot") in JO),
                         "elvetve": sum(1 for k in ks if k.get("allapot") == "elvetve"),
                         "megtekintes_atlag": round(sum(nez) / len(nez)) if nez else None,
                         "utolso": max((k.get("letrehozva") or 0 for k in ks), default=0), "tanult": bool(r.get("tanult"))}
    return ki


def recept_minta(klipek, azon, rnd):
    """🎰 Thompson-minta a receptre: Beta(1 + Σjutalom, 1 + Σ(1 − jutalom)) – a kevés adatú recept szórása nagy, így
    magától kap esélyt (felfedezés), a sok jó videót hozó pedig egyre biztosabban nyer (kiaknázás)."""
    a = b = 1.0
    for k in _recept_klipjei(klipek, azon):
        j = teljesitmeny.jutalom(k, JO)
        if j is not None:
            a, b = a + j, b + 1 - j
    return rnd.betavariate(a, b)


def hossz_szorzo(klipek):
    """⏱ A receptek hosszának tanult szorzója (0,85–1,15; 1,0, amíg nincs legalább 9 mért videó): a legjobb harmad
    átlagos hossza a mért videók átlagához képest, és ha a megtartási görbék szerint a nézők fele a videó 60%-a előtt
    elmegy, rövidítés. Visszaad: (szorzó, magyarázat vagy None)."""
    mert = [(teljesitmeny.pont(k), k) for k in klipek if teljesitmeny.pont(k) is not None and (k.get("szim") or {}).get("meres")]
    if len(mert) < 9:
        return 1.0, None
    mert.sort(key=lambda x: -x[0])
    hossz = lambda l: sum(k["szim"]["meres"].get("hossz") or 0 for _, k in l) / max(1, len(l))   # noqa: E731
    f = hossz(mert[: max(3, len(mert) // 3)]) / max(1.0, hossz(mert))
    miert = f"a legjobb harmad átlagosan {hossz(mert[: max(3, len(mert) // 3)]):.0f} mp (az összes: {hossz(mert):.0f} mp)"
    arany = sorted(k["t50"] / k["szim"]["meres"]["hossz"] for _, k in mert if k.get("t50") and k["szim"]["meres"].get("hossz"))
    if len(arany) >= 4 and arany[len(arany) // 2] < 0.6:
        f *= 0.93
        miert += f"; a nézők fele a videó {arany[len(arany) // 2] * 100:.0f}%-áig marad"
    return round(max(0.85, min(1.15, f)), 3), miert


def tanul(klipek):
    """A jóváhagyott SZABAD kísérletekből tanult recept lesz (a fizikája bevált alap, a kozmetika változhat)."""
    tanultak = _olvas()
    ismert = {r.get("forras_klip") for r in tanultak}
    uj = 0
    for k in klipek:
        spec = (k.get("szim") or {}).get("spec") or {}
        if k.get("allapot") not in JO or spec.get("recept") or k["id"] in ismert:
            continue
        m = (k.get("szim") or {}).get("meres") or {}
        if m.get("minoseg") and not m["minoseg"].get("jo"):
            continue
        alap = {x: v for x, v in spec.items() if not x.startswith("_") and x not in ("tempo", "kerdes_sablon")}
        tanultak.append({"azon": f"tanult_{k['id'][:6]}", "nev": (k.get("cim") or spec.get("cim") or "Tanult recept")[:60],
                         "ikon": "🧪", "tanult": True, "aktiv": True, "forras_klip": k["id"], "letrehozva": time.time(),
                         "leiras": f"Kobold saját kísérletéből (jóváhagytad): {spec.get('kerdes', '')}",
                         "alap": alap, "kerdesek": [spec.get("kerdes") or "Wait for it…"], "cimek": [k.get("cim") or spec.get("cim")],
                         "valtozok": {"paletta": list(S.PALETTAK), "latvany.stilus": ["tele", "neon"],
                                      "hang.hangszer": VICCES_HANGSZER + DALLAMOS}})
        uj += 1
    # a tanult recept, ami háromszor egymás után elbukott (elvetve), kikapcsol
    for r in tanultak:
        ks = sorted(_recept_klipjei(klipek, r["azon"]), key=lambda k: -(k.get("letrehozva") or 0))[:3]
        if len(ks) == 3 and all(k.get("allapot") == "elvetve" for k in ks):
            r["aktiv"] = False
    if uj or tanultak:
        _ir(tanultak)
    if uj:
        print(f"[RECEPT] {uj} új tanult szimulációs recept", flush=True)
    return uj


def terv(klipek, tema="", rnd=None, kiserlet_arany=KISERLET_ARANY):
    """Mit gyártsunk most: {"mod": "recept"|"kiserlet", "recept", "spec", "miert"}. klipek: a gyár eddigi szimulációs
    termékei (a döntéseiddel és a nézettséggel)."""
    rnd = rnd or random.Random()
    try:
        tanul(klipek)
    except Exception as hiba:
        print("[RECEPT] tanulás hiba:", hiba, flush=True)
    szim = sorted((k for k in klipek if (k.get("szim") or {}).get("spec")), key=lambda k: -(k.get("letrehozva") or 0))
    st = statisztika(klipek)
    receptek = osszes()
    # a téma név szerint kér egy receptet (pl. "túlcsordulás", "overflow") -> az készül
    kert = [r for r in receptek if r.get("kulcs") and re.search(r["kulcs"], tema or "")]
    if kert:
        r = kert[0]
        return {"mod": "recept", "recept": r, "spec": valtozat(r, rnd), "miert": f"{r['ikon']} {r['nev']} (a téma ezt kérte)"}
    # a téma kifejezetten valami újat / trendet kér -> kísérlet; különben ritkán, ha már elég jó videó van
    uj_kell = any(x in tema.lower() for x in ("új", "kísérlet", "kiserlet", "trend", "viral", "virál", "felkapott"))
    if uj_kell or (sum(s["jovahagyva"] for s in st.values()) >= 3 and rnd.random() < kiserlet_arany):
        return {"mod": "kiserlet", "recept": None, "spec": None, "miert": "szabad kísérlet (fejlődés): ha bejön, recept lesz belőle"}
    utolsok = [((k["szim"]["spec"]).get("recept") or "") for k in szim[:2]]
    jeloltek = [r for r in receptek if r["azon"] not in utolsok] or receptek
    r = max(jeloltek, key=lambda r_: recept_minta(klipek, r_["azon"], rnd))   # 🎰 Thompson-mintavétel
    # kiaknázás: a recept legjobb (jóváhagyott; a közös pontszám, aztán a nézettség szerint) videója körül
    jok = sorted((k for k in _recept_klipjei(klipek, r["azon"]) if k.get("allapot") in JO),
                 key=lambda k: (-(teljesitmeny.pont(k) or 0), -(k.get("megtekintes") or 0)))
    kozeli = jok[0]["szim"]["spec"] if jok and rnd.random() < 0.5 else None
    kerul = []
    if szim:
        h = szim[0]["szim"]["spec"]
        kerul = [h.get("paletta"), (h.get("hang") or {}).get("hangszer") if isinstance(h.get("hang"), dict) else None]
    spec = valtozat(r, rnd, kozeli=kozeli, kerul=[x for x in kerul if x], tapasztalat=ertek_tapasztalat(klipek, r))
    szorzo, _ = hossz_szorzo(klipek)
    if szorzo != 1.0 and spec.get("hossz"):
        spec["hossz"] = round(spec["hossz"] * szorzo, 1)   # ⏱ tanult hossz (a minőségkapu ezt is ellenőrzi renderelés előtt)
    s = st[r["azon"]]
    return {"mod": "recept", "recept": r, "spec": spec,
            "miert": f"{r['ikon']} {r['nev']} ({s['jovahagyva']} jóváhagyva / {s['elvetve']} elvetve"
                     + (f", átlag {s['megtekintes_atlag']:,} megtekintés" if s['megtekintes_atlag'] is not None else "") + ")"
                     + (" – a legjobb videója körül" if kozeli else "")}


def leiras_szoveg():
    """A kézikönyvnek / a csevegésnek: milyen receptek vannak."""
    return "\n".join(f"- {r.get('ikon', '🎱')} {r['nev']} ({r['azon']}): {r['leiras']}" for r in osszes())


if __name__ == "__main__":
    # Kézi próba: minden receptből N változat, előválogatás + minőségkapu (renderelés nélkül)
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    csak = sys.argv[2] if len(sys.argv) > 2 else None
    for r in RECEPTEK:
        if csak and r["azon"] != csak:
            continue
        jo = 0
        for i in range(n):
            spec = S.tisztit(valtozat(r, random.Random(i * 31 + 7), alap_csak=(i == 0)))
            t = time.time()
            vegso, e, naplo = S.valaszt(spec, keret_mp=60)
            m = e.get("minoseg") or S.minoseg(vegso, e)
            jo += m["jo"]
            print(f"{r['azon']:13} #{i} {m['pont']:>4} {'OK ' if m['jo'] else 'BUK'} vége {e['vege_ido']} / {e['hossz']} s, "
                  f"max {e['labdak_max']} labda, tempó {vegso['tempo']:.2f}, küszöb {vegso['vege']['ertek']} | {'; '.join(m['hibak'])} "
                  f"({time.time() - t:.0f} s)", flush=True)
        print(f"== {r['azon']}: {jo}/{n} átment\n", flush=True)
