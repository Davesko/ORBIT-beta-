"""📊 KÖZÖS TELJESÍTMÉNY-PONTSZÁM a kitett videókra (2026-11-14) – ebből tanul minden gyár (szimulációs receptek,
összeolvadós láncok, időpontok).

Miért: a nyers nézettség félrevezet. (1) A régi videó mindig „jobb” az újnál, mert több ideje gyűlik rajta a nézettség.
(2) A csatornák összeadva torzítanak: egy YouTube-videó 1300, ugyanaz Instagramon 150 megtekintést hoz – ez a platform
különbsége, nem a videóé. (3) A Shortsnál a megtartás (a videó hány %-át nézik meg) erősebb jel, mint a nézettség.

Ezért videónként:
  * AZONOS KORBAN mérünk: a poszt nézettsége KOR_NAP (3) napos korában a napi pillanatképekből (csatornak: nezettseg.json);
    a fiatalabb posztnál a betöltött egész napjainál (legalább 1 nap);
  * CSATORNÁNKÉNT normálunk: az érték / a csatorna többi posztjának mediánja UGYANABBAN a korban (legalább MIN_MINTA poszt
    kell a csatornán, különben nincs arány);
  * a videó aránya = a csatornánkénti arányok mértani közepe;
  * × (megtartás / a megtartások mediánja)^1,5, ha van megtartás-adat (YouTube Analytics).
1,0 = a mi átlagos videónk; 0,2–4 közé szorítva. Ha még nincs elég adat, a pont None (a tanulók ilyenkor a döntésedből
indulnak ki). A megtartási GÖRBÉBŐL (youtube.megtartas_gorbe) a t50: hány mp-ig marad a nézők fele.
"""
import datetime
import math

KOR_NAP = 3          # ennyi napos korban hasonlítjuk össze a posztokat
MIN_MINTA = 3        # ennyi poszt kell egy csatornán (ugyanabban a korban) a mediánhoz
PONT_MIN, PONT_MAX = 0.2, 4.0


def _datum(ts, plusz=0):
    return (datetime.date.fromtimestamp(ts) + datetime.timedelta(days=plusz)).isoformat()


def _median(lista):
    lista = sorted(lista)
    if not lista:
        return None
    n = len(lista)
    return lista[n // 2] if n % 2 else (lista[n // 2 - 1] + lista[n // 2]) / 2


def ertek_korban(poszt, sor, kor_nap, most):
    """A poszt nézettsége kor_nap napos korában (None, ha még nincs annyi idős, vagy nincs róla pillanatkép).
    sor: {"ÉÉÉÉ-HH-NN": nézettség} – a poszt napi pillanatképei."""
    kint = poszt.get("kint_ido")
    if not kint or (most - kint) < kor_nap * 86400:
        return None
    for plusz in (0, 1):                         # a célnap, vagy ha aznap nem futott a gép: a következő nap
        v = (sor or {}).get(_datum(kint, kor_nap + plusz))
        if v is not None:
            return int(v)
    if (most - kint) < (kor_nap + 2) * 86400 and poszt.get("nezettseg") is not None:
        return int(poszt["nezettseg"])           # épp most ennyi idős: a mostani érték
    return None


def pontok(posztok, tortenet, klipek, most):
    """{klip_id: {"pont", "kor", "aranyok": {csatorna: arány}, "megtartas_arany"}} – csak azokra, amelyekről van mérés.
    posztok: a csatornakezelő posztjai; tortenet: {poszt_id: {nap: nézettség}}; klipek: {klip_id: klip} (megtartás)."""
    kint = [p for p in posztok if p.get("allapot") == "kint" and p.get("kint_ido")]
    # csatornánként, koronként és fajtánként (short / 🎬 long form: más a nézettség nagyságrendje) a posztok értékei
    ertekek = {}      # (csatorna, kor, long form-e) -> {poszt_id: érték}
    for p in kint:
        for kor in range(1, KOR_NAP + 1):
            v = ertek_korban(p, tortenet.get(p["id"]), kor, most)
            if v is not None:
                ertekek.setdefault((p["csatorna"], kor, bool(p.get("hosszu"))), {})[p["id"]] = v
    tart_med = {}
    for h in (False, True):
        tart = [float(k["megtartas"]) for k in klipek.values() if k.get("megtartas") and bool(k.get("hosszu")) == h]
        tart_med[h] = _median(tart) if len(tart) >= MIN_MINTA else None
    ki = {}
    for p in kint:
        kor = min(KOR_NAP, int((most - p["kint_ido"]) // 86400))
        fajta = bool(p.get("hosszu"))
        while kor >= 1 and p["id"] not in ertekek.get((p["csatorna"], kor, fajta), {}):
            kor -= 1
        if kor < 1:
            continue
        minta = ertekek[(p["csatorna"], kor, fajta)]
        if len(minta) < MIN_MINTA:
            continue
        med = max(1.0, float(_median(list(minta.values()))))
        e = ki.setdefault(p["klip"], {"aranyok": {}, "kor": 0})
        e["aranyok"][p["csatorna"]] = round((minta[p["id"]] + 1.0) / (med + 1.0), 3)
        e["kor"] = max(e["kor"], kor)
    for kid, e in ki.items():
        ar = list(e["aranyok"].values())
        pont = math.exp(sum(math.log(max(0.01, a)) for a in ar) / len(ar))
        k = klipek.get(kid) or {}
        e["megtartas_arany"] = None
        tm = tart_med[bool(k.get("hosszu"))]
        if tm and k.get("megtartas"):
            e["megtartas_arany"] = round(float(k["megtartas"]) / tm, 3)
            pont *= e["megtartas_arany"] ** 1.5
        e["pont"] = round(max(PONT_MIN, min(PONT_MAX, pont)), 3)
    return ki


def pont(k):
    """Egy klip közös pontszáma (None, ha még nincs mérve)."""
    return ((k or {}).get("telj") or {}).get("pont")


def jutalom(k, jo=("jovahagyva", "feltoltes", "feltoltve")):
    """A tanulóknak 0..1 jutalom: elvetett = 0; mért videó = pont / (pont + 1) (az átlagos videó 0,5; a kétszeres 0,67;
    a fele 0,33); jóváhagyott, de még méretlen = 0,55 (a gazda ízlése is jel); döntésre vár = None."""
    if (k or {}).get("allapot") == "elvetve":
        return 0.0
    p = pont(k)
    if p is not None:
        return p / (p + 1.0)
    if (k or {}).get("allapot") in jo:
        return 0.55
    return None


def t50(gorbe, hossz):
    """A megtartási görbéből: hány mp-ig marad a nézők fele. gorbe: [(a videó hányada 0..1, a nézők aránya)], hossz: mp.
    Ha a görbe sosem megy 50% alá (a hurok miatt 100% fölött is lehet), a teljes hossz."""
    if not gorbe or not hossz:
        return None
    for hanyad, arany in gorbe:
        if hanyad > 0.03 and arany < 0.5:
            return round(hanyad * float(hossz), 1)
    return round(float(hossz), 1)


def leeses(gorbe, hossz):
    """A legnagyobb egy lépésnyi nézővesztés helye (mp) az első 2 mp UTÁN (az eleji továbbgörgetés mindig nagy) és
    mértéke (a nézők hány %-a). None, ha nincs kiugró esés (≥ 4 százalékpont)."""
    if not gorbe or not hossz or len(gorbe) < 5:
        return None
    legjobb = None
    for (h0, a0), (h1, a1) in zip(gorbe, gorbe[1:]):
        if h1 * hossz <= 2.0:
            continue
        eses = a0 - a1
        if legjobb is None or eses > legjobb[1]:
            legjobb = (round(h1 * float(hossz), 1), eses)
    return (legjobb[0], round(legjobb[1] * 100, 1)) if legjobb and legjobb[1] >= 0.04 else None
