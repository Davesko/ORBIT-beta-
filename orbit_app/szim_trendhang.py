"""🎵 Trending hangok: Kobold magától megkeresi és letölti a most felkapott TikTok-dalokat és mém-hangeffekteket a
szimulációs videókhoz. Csak a felhasználó saját használatára (a jogtisztaságot itt szándékosan nem vizsgáljuk).

* Felkapott dalok: a tokchart.com napi TikTok-listái (trending songs + trending sounds; a névtelen "Original audio"
  hangokat kihagyjuk, mert név nélkül nem találhatók meg) -> yt-dlp letölti a dalt YouTube-ról ("előadó cím").
  (A TikTok saját listája bejelentkezést kér, a yt-dlp TikTok-hang letöltője pedig el van romolva – ezért ez az út.)
* Mém-hangeffektek: a myinstants.com népszerű gombjai (rövid mp3-ak) -> a szimuláció saját hangmappájába kerülnek
  "trend_…" néven, így ütközéshangként választhatók ("sajat:trend_…").
* A dalok ~/.kobold/szimulacio/trendzene/ alá kerülnek; a videó alá a dal LEGHANGOSABB (refrén-gyanús) része megy,
  az ütközéshangok halkabban rá.

Kézi próba:  ../.venv/bin/python trendhang.py            (frissít és kiírja, mi van)
"""
import html as _html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ADAT = os.path.dirname(os.environ.get("ORBIT_SZIM_ADAT") or os.path.expanduser("~/Library/Application Support/Orbit/szimgyar"))
SZIM = os.environ.get("ORBIT_SZIM_ADAT") or os.path.expanduser("~/Library/Application Support/Orbit/szimgyar")
ZENE_MAPPA = os.path.join(SZIM, "trendzene")
EFFEKT_MAPPA = os.path.join(SZIM, "hangok")          # = szimulacio.HANG_MAPPA (saját ütközéshangok)
INDEX = os.path.join(SZIM, "trendhangok.json")
YTDLP = os.path.expanduser("~/Library/Application Support/Orbit/media-runtime/bin/yt-dlp")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
LISTAK = ["https://tokchart.com/tiktok-trending-songs", "https://tokchart.com/tiktok-trending-songs/united-states",
          "https://tokchart.com/tiktok-trending-sounds"]
# a myinstants "index" oldala a most felkapott gombok (országonként), a kategóriák a mém / virális gombok
EFFEKT_LISTAK = ["https://www.myinstants.com/en/index/us/", "https://www.myinstants.com/en/categories/memes/",
                 "https://www.myinstants.com/en/categories/viral/", "https://www.myinstants.com/en/index/gb/"]
MAX_ZENE, MAX_EFFEKT = 10, 24          # ennyi friss darab marad meg (a régiek törlődnek, ne teljen a lemez)
# 🧠 BRAINROT (gen z figyelemfogó hangok): a videók legalább 2/3-a ezekre megy, nem a felkapott dalra.
# Alá: YouTube brainrot-dalok / -phonk / meme funk – a minden idők legnézettebbjei (bevált himnuszok: Tung Tung Tung Sahur,
# Brainrot Rap, Meme Funk…) ÉS a hónap legnézettebbjei (hogy friss maradjon). Pattanásra: myinstants brainrot-keresés.
BRAINROT_KERESESEK = ["italian brainrot song", "brainrot song", "brainrot phonk", "brainrot meme funk", "skibidi song",
                      "steal a brainrot song", "sigma phonk meme", "brainrot rap"]
BRAINROT_SP = {"mindenkori": "CAMSAhAB", "honap": "CAMSBAgEEAE"}   # YouTube-szűrő: nézettség szerint / ebben a hónapban
BRAINROT_TILTO = re.compile(r"(?i)minecraft|roblox|gameplay|\blive\b|story|build battle|fortnite|reaction|tutorial|"
                            r"how to|\bdolls?\b|in real life|3:00 ?am|compilation|1 hour|10 hours|extended|lyrics? video")
BRAINROT_EFFEKT_LISTAK = ["https://www.myinstants.com/en/search/?name=italian+brainrot",
                          "https://www.myinstants.com/en/search/?name=brainrot",
                          "https://www.myinstants.com/en/search/?name=skibidi",
                          "https://www.myinstants.com/en/search/?name=sigma"]
BRAINROT_SZO = re.compile(r"(?i)brain ?rot|skibidi|sigma|phonk|tung|sahur|tralalero|bombardiro|cappuccin|capuchin|"
                          r"gigachad|giga chad|oiia|chipi|crab rave|rizz|gyatt|ohio|meme|funk|italian|aura|mewing|fanum")
MAX_BRAINROT, MAX_BRAINROT_EFFEKT = 12, 20
BRAINROT_HONAP = 4          # ennyi hely jut a hónap friss brainrot-slágereinek (a többi a bevált, mindenkori himnuszoké)
MEGTART_NAP = 14


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _azon(szoveg):
    s = re.sub(r"[^a-z0-9]+", "_", _html.unescape(szoveg).lower().encode("ascii", "ignore").decode()).strip("_")
    return s[:40] or "hang"


def index():
    try:
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"ido": 0, "zenek": [], "effektek": []}


def _index_ir(adat):
    os.makedirs(SZIM, exist_ok=True)
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(adat, f, ensure_ascii=False, indent=1)
    os.replace(tmp, INDEX)


def friss_kell(orak=20):
    return time.time() - float(index().get("ido") or 0) > orak * 3600


# ---------------------------------------------------------------- listák

def _itemlistak(d):
    """A JSON-LD összes ItemList-je, bármilyen mélyen (@graph, mainEntity …)."""
    if isinstance(d, dict):
        if d.get("@type") == "ItemList":
            yield d
        for v in d.values():
            if isinstance(v, (dict, list)):
                yield from _itemlistak(v)
    elif isinstance(d, list):
        for v in d:
            yield from _itemlistak(v)


def felkapott_dalok():
    """A tokchart napi TikTok-listáiból a NÉVVEL rendelkező dalok/hangok, rangsorban: [{cim, eloado, rang, lista}]."""
    ki, latott = [], set()
    for url in LISTAK:
        try:
            h = _get(url)
        except Exception as hiba:
            print("[TRENDHANG] lista hiba:", url, hiba, flush=True)
            continue
        for blokk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h, re.S):
            try:
                d = json.loads(blokk)
            except ValueError:
                continue
            for elem in _itemlistak(d):
                if not isinstance(elem, dict) or elem.get("@type") != "ItemList":
                    continue
                for li in elem.get("itemListElement") or []:
                    it = li.get("item") or {}
                    cim = " ".join(str(it.get("name") or "").split())
                    art = it.get("byArtist") or []
                    art = art if isinstance(art, list) else [art]
                    eloado = ", ".join(str(a.get("name") or "") for a in art if isinstance(a, dict) and a.get("name"))
                    if not cim or re.search(r"(?i)^original (audio|sound)|^som original|^sonido original", cim):
                        continue
                    kulcs = (cim.lower(), eloado.lower())
                    if kulcs in latott:
                        continue
                    latott.add(kulcs)
                    ki.append({"cim": cim[:100], "eloado": eloado[:80], "rang": int(li.get("position") or 99),
                               "lista": "dalok" if "songs" in url else "hangok"})
    return sorted(ki, key=lambda x: (x["rang"], x["lista"]))


def felkapott_effektek():
    """A myinstants most felkapott + mém / virális gombjai, összefésülve (amelyik több listán is elöl van, az előrébb
    kerül): [{nev, url, lista}]."""
    pont, adat = {}, {}
    for li, url in enumerate(EFFEKT_LISTAK):
        try:
            h = _get(url)
        except Exception as hiba:
            print("[TRENDHANG] effektlista hiba:", url, hiba, flush=True)
            continue
        latott = set()
        for m in re.finditer(r"""play\('(/media/sounds/[^']+\.mp3)'""", h):
            ut = m.group(1)
            if ut in latott:
                continue
            latott.add(ut)
            hely = len(latott)
            pont[ut] = pont.get(ut, 0) + max(0.0, 1 - hely / 60) * (1.5 if li == 0 else 1.0)
            adat.setdefault(ut, {"nev": os.path.splitext(os.path.basename(ut))[0], "url": "https://www.myinstants.com" + ut,
                                 "lista": url.rstrip("/").split("/")[-1]})
    return [adat[u] for u in sorted(pont, key=lambda u: -pont[u])]


def felkapott_brainrot():
    """YouTube brainrot-hangok: [{url, cim, nezettseg, hossz, honap}] – a mindenkori és a havi legnézettebbek, 20–240 mp,
    a gameplay / sztori / hosszú válogatás nélkül. Pontozás: nézettség (log), a hónap friss slágerei előnyt kapnak."""
    import math
    import urllib.parse

    talalat = {}
    for q in BRAINROT_KERESESEK:
        for nev, sp in BRAINROT_SP.items():
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={sp}"
            try:
                r = subprocess.run([YTDLP, "--no-warnings", "--flat-playlist", "--playlist-end", "12", "--print",
                                    "%(id)s\t%(view_count)s\t%(duration)s\t%(title)s", url],
                                   capture_output=True, text=True, timeout=90)
            except Exception as hiba:
                print("[TRENDHANG] brainrot-keresés hiba:", q, hiba, flush=True)
                continue
            for sor in r.stdout.splitlines():
                reszek = sor.split("\t", 3)
                if len(reszek) < 4 or not reszek[1].isdigit():
                    continue
                vid, nez, hossz, cim = reszek[0], int(reszek[1]), reszek[2], reszek[3]
                try:
                    hossz = float(hossz)
                except ValueError:
                    continue
                if not (20 <= hossz <= 240) or BRAINROT_TILTO.search(cim) or not BRAINROT_SZO.search(cim) or nez < 20000:
                    continue
                pont = math.log10(nez)
                if vid not in talalat or talalat[vid]["pont"] < pont:
                    talalat[vid] = {"url": f"https://www.youtube.com/watch?v={vid}", "cim": " ".join(cim.split())[:100],
                                    "nezettseg": nez, "hossz": hossz, "honap": nev == "honap", "pont": pont}
    # a havi listán sok a rajzfilm-epizód / sztori: ott csak a dalnak látszó cím jöhet (song, phonk, funk, remix…)
    dal = re.compile(r"(?i)\b(song|phonk|funk|rap|remix|music|theme|beat|audio|sound|mix|edit)\b")
    honap = sorted((x for x in talalat.values() if x["honap"] and dal.search(x["cim"])), key=lambda x: -x["pont"])[:BRAINROT_HONAP]
    mindenkori = sorted((x for x in talalat.values() if x not in honap), key=lambda x: -x["pont"])
    return honap + mindenkori   # a friss elöl: a letöltés sorrendje = a helyek elosztása


def felkapott_brainrot_effektek():
    """A myinstants brainrot / skibidi / sigma keresésének gombjai, sorrendben (a több listán is elöl lévő előbb)."""
    pont, adat = {}, {}
    for url in BRAINROT_EFFEKT_LISTAK:
        try:
            h = _get(url)
        except Exception as hiba:
            print("[TRENDHANG] brainrot-effektlista hiba:", url, hiba, flush=True)
            continue
        latott = []
        for m in re.finditer(r"""play\('(/media/sounds/[^']+\.mp3)'""", h):
            if m.group(1) not in latott:
                latott.append(m.group(1))
        for hely, ut in enumerate(latott[:30]):
            pont[ut] = pont.get(ut, 0) + 1 - hely / 40
            adat.setdefault(ut, {"nev": os.path.splitext(os.path.basename(ut))[0], "url": "https://www.myinstants.com" + ut,
                                 "lista": "brainrot", "tipus": "brainrot"})
    return [adat[u] for u in sorted(pont, key=lambda u: -pont[u])]


# ---------------------------------------------------------------- letöltés

def _brainrot_letolt(b):
    """Egy brainrot-hang (YouTube-videó) hangja m4a-ként. Visszaad: fájlútvonal vagy None."""
    import szim_megszakitas as megszakitas

    os.makedirs(ZENE_MAPPA, exist_ok=True)
    nev = "br_" + _azon(b["cim"])[:50]
    meglevo = [f for f in os.listdir(ZENE_MAPPA) if os.path.splitext(f)[0] == nev]
    if meglevo:
        return os.path.join(ZENE_MAPPA, meglevo[0])
    p = megszakitas.run([YTDLP, "--no-warnings", "--no-playlist", "-f", "bestaudio[ext=m4a]/bestaudio", "-x", "--audio-format",
                         "m4a", "-o", os.path.join(ZENE_MAPPA, nev + ".%(ext)s"), "--print", "after_move:filepath", b["url"]],
                        capture_output=True, text=True, timeout=240)
    ut = (p.stdout or "").strip().splitlines()[-1:]
    return ut[0] if ut and os.path.exists(ut[0]) else None

def _dal_letolt(d):
    """Egy felkapott dal hangja YouTube-ról (yt-dlp, első találat, max 8 perc). Visszaad: fájlútvonal vagy None."""
    import szim_megszakitas as megszakitas

    os.makedirs(ZENE_MAPPA, exist_ok=True)
    nev = _azon(f"{d['eloado']} {d['cim']}")
    meglevo = [f for f in os.listdir(ZENE_MAPPA) if os.path.splitext(f)[0] == nev]
    if meglevo:
        return os.path.join(ZENE_MAPPA, meglevo[0])
    keres = f"ytsearch1:{d['eloado']} {d['cim']} audio".replace("\n", " ")
    p = megszakitas.run([YTDLP, "--no-warnings", "--no-playlist", "-f", "bestaudio[ext=m4a]/bestaudio",
                         "--match-filter", "duration<480 & duration>20", "-x", "--audio-format", "m4a",
                         "-o", os.path.join(ZENE_MAPPA, nev + ".%(ext)s"), "--print", "after_move:filepath", keres],
                        capture_output=True, text=True, timeout=240)
    ut = (p.stdout or "").strip().splitlines()[-1:]
    return ut[0] if ut and os.path.exists(ut[0]) else None


def _effekt_letolt(e):
    os.makedirs(EFFEKT_MAPPA, exist_ok=True)
    cel = os.path.join(EFFEKT_MAPPA, "trend_" + _azon(e["nev"])[:30] + ".mp3")
    if os.path.exists(cel):
        return cel
    req = urllib.request.Request(e["url"], headers={"User-Agent": UA, "Referer": "https://www.myinstants.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        adat = r.read(3_000_000)
    if len(adat) < 1000:
        return None
    with open(cel, "wb") as f:
        f.write(adat)
    return cel


def frissit(naplo=lambda s: None, max_zene=MAX_ZENE, max_effekt=MAX_EFFEKT):
    """Megkeresi és letölti a most felkapott dalokat és mém-hangokat; a régieket (MEGTART_NAP után, ha már nincsenek a
    listán) törli. Visszaad: a friss index."""
    regi = index()
    most = time.time()
    naplo("Trending hangok: a mai TikTok-listák lekérése")
    dalok = felkapott_dalok()[:max_zene + 4]
    zenek = {z["fajl"]: z for z in regi.get("zenek", []) if os.path.exists(z.get("fajl") or "")}
    db = 0
    for d in dalok:
        if db >= max_zene:
            break
        naplo(f"Letöltés: {d['eloado']} – {d['cim']}")
        try:
            ut = _dal_letolt(d)
        except InterruptedError:
            raise
        except Exception as hiba:
            print("[TRENDHANG] dal letöltés hiba:", d["cim"], hiba, flush=True)
            ut = None
        if not ut:
            continue
        db += 1
        z = zenek.get(ut) or {"fajl": ut, "felhasznalva": 0, "talalva": most}
        z.update(azon=os.path.splitext(os.path.basename(ut))[0], cim=d["cim"], eloado=d["eloado"], rang=d["rang"],
                 lista=d["lista"], latva=most)
        zenek[ut] = z
    naplo("Trending mém-hangeffektek letöltése")
    effektek = {e["fajl"]: e for e in regi.get("effektek", []) if os.path.exists(e.get("fajl") or "")}
    for i, e in enumerate(felkapott_effektek()[:max_effekt]):
        try:
            ut = _effekt_letolt(e)
        except Exception as hiba:
            print("[TRENDHANG] effekt letöltés hiba:", e["nev"], hiba, flush=True)
            continue
        if ut:
            x = effektek.get(ut) or {"fajl": ut, "talalva": most}
            x.update(azon=os.path.splitext(os.path.basename(ut))[0], nev=e["nev"], rang=i + 1, latva=most)
            effektek[ut] = x
    naplo("🧠 Brainrot-hangok: a legnézettebb brainrot-dalok és mém-hangok")
    try:
        br = felkapott_brainrot()
    except Exception as hiba:
        print("[TRENDHANG] brainrot hiba:", hiba, flush=True)
        br = []
    db_br = 0
    for b in br:
        if db_br >= MAX_BRAINROT:
            break
        try:
            ut = _brainrot_letolt(b)
        except InterruptedError:
            raise
        except Exception as hiba:
            print("[TRENDHANG] brainrot letöltés hiba:", b["cim"], hiba, flush=True)
            ut = None
        if not ut:
            continue
        db_br += 1
        z = zenek.get(ut) or {"fajl": ut, "felhasznalva": 0, "talalva": most}
        z.update(azon=os.path.splitext(os.path.basename(ut))[0], cim=b["cim"], eloado="brainrot", rang=db_br,
                 lista="brainrot-honap" if b["honap"] else "brainrot", tipus="brainrot", nezettseg_yt=b["nezettseg"], latva=most,
                 url=b["url"])
        zenek[ut] = z
    for i, e in enumerate(felkapott_brainrot_effektek()[:MAX_BRAINROT_EFFEKT]):
        try:
            ut = _effekt_letolt(e)
        except Exception as hiba:
            print("[TRENDHANG] brainrot-effekt letöltés hiba:", e["nev"], hiba, flush=True)
            continue
        if ut:
            x = effektek.get(ut) or {"fajl": ut, "talalva": most}
            x.update(azon=os.path.splitext(os.path.basename(ut))[0], nev=e["nev"], rang=i + 1, latva=most, tipus="brainrot")
            effektek[ut] = x
    # takarítás: ami MEGTART_NAP óta nem volt a listán, megy
    for tar in (zenek, effektek):
        for ut, x in list(tar.items()):
            if most - float(x.get("latva") or 0) > MEGTART_NAP * 86400:
                for f_ in (ut, os.path.splitext(ut)[0] + ".jpg"):
                    try:
                        os.remove(f_)
                    except OSError:
                        pass
                del tar[ut]
    adat = {"ido": most, "zenek": sorted(zenek.values(), key=lambda z: (-float(z["latva"]), z["rang"])),
            "effektek": sorted(effektek.values(), key=lambda e: (-float(e["latva"]), e["rang"]))}
    if not dalok and regi.get("zenek"):
        adat["ido"] = regi.get("ido", 0)   # a lista nem jött le: holnap ne várjunk vele, próbáljuk újra
    _index_ir(adat)
    print(f"[TRENDHANG] {len(adat['zenek'])} dal (ebből {sum(1 for z in adat['zenek'] if z.get('tipus') == 'brainrot')} brainrot), "
          f"{len(adat['effektek'])} effekt (ma {db} dal, {db_br} brainrot letöltve)", flush=True)
    return adat


# ---------------------------------------------------------------- használat a videókban

def borito(z):
    """A zene borítóképe (a YouTube-videó bélyegképe, négyzetesre vágva, 512 px) – a verseny-golyókba ez kerül.
    A trendzene mellé menti (<azon>.jpg); ha nem sikerül, None."""
    cel = os.path.splitext(z["fajl"])[0] + ".jpg"
    if os.path.exists(cel):
        return cel
    import szim_megszakitas as megszakitas

    hol = z.get("url") or ("ytsearch1:" + (z["cim"] if z.get("tipus") == "brainrot" else f"{z.get('eloado', '')} {z['cim']}")).replace("\n", " ")
    try:
        p = megszakitas.run([YTDLP, "--no-warnings", "--no-playlist", "--skip-download", "--print", "thumbnail", hol],
                            capture_output=True, text=True, timeout=90)
        url = ((p.stdout or "").strip().splitlines() or [""])[-1]
        if not url.startswith("http"):
            return None
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            adat = r.read(8_000_000)
        import io

        from PIL import Image, ImageOps

        im = Image.open(io.BytesIO(adat)).convert("RGB")
        # a YouTube-bélyegkép gyakran fekete sávos (4:3-ba tett 16:9): levágjuk a sötét széleket
        szurke = im.convert("L").point(lambda v: 255 if v > 18 else 0)
        dob = szurke.getbbox()
        if dob and (dob[2] - dob[0]) > im.width * 0.4 and (dob[3] - dob[1]) > im.height * 0.4:
            im = im.crop(dob)
        ImageOps.fit(im, (512, 512), Image.LANCZOS).save(cel, quality=90)
        return cel
    except InterruptedError:
        raise
    except Exception as hiba:
        print("[TRENDHANG] borító hiba:", z.get("cim"), hiba, flush=True)
        return None


def zenek():
    """A meglévő trending dalok (a legfrissebb listán szereplők elöl)."""
    return [z for z in index().get("zenek", []) if os.path.exists(z.get("fajl") or "")]


def zene(azon):
    return next((z for z in zenek() if z["azon"] == azon), None)


def kovetkezo(tipus="dal"):
    """A videóhoz ajánlott alap: tipus="dal" (felkapott TikTok-dal) vagy "brainrot". A legkevesebbszer használt, azon belül
    a legfrissebb / legjobb helyezésű."""
    lista = [z for z in zenek() if (z.get("tipus") or "dal") == tipus]
    return min(lista, key=lambda z: (int(z.get("felhasznalva") or 0), -float(z["latva"]), z["rang"])) if lista else None


def felhasznal(azon):
    adat = index()
    for z in adat.get("zenek", []):
        if z.get("azon") == azon:
            z["felhasznalva"] = int(z.get("felhasznalva") or 0) + 1
    _index_ir(adat)


def effektek():
    """A letöltött mém-hangok (a legfrissebb listán szereplők elöl)."""
    return [e for e in index().get("effektek", []) if os.path.exists(e.get("fajl") or "")]


def kovetkezo_meme(kizar=(), tipus=None):
    """A videóhoz ajánlott mém-hang: ami nagyot ment (átlag nézettség a videóiban) előnyben, aztán a legkevésbé
    használt, friss, jó helyezésű. kizar: ezeket most ne (pl. az előző videó mémje). tipus="brainrot": csak a brainrot-
    mémek közül (ha van)."""
    alap = [e for e in effektek() if tipus is None or e.get("tipus") == tipus] or effektek()
    lista = [e for e in alap if e["azon"] not in kizar] or alap
    if not lista:
        return None

    def kulcs(e):
        nez = e.get("nezettseg") or []
        atlag = sum(nez) / len(nez) if nez else None
        return (-(atlag or 0) if atlag and len(nez) >= 2 else 0, int(e.get("felhasznalva") or 0), -float(e.get("latva") or 0),
                int(e.get("rang") or 99))
    return min(lista, key=kulcs)


def meme_felhasznal(azon):
    adat = index()
    for e in adat.get("effektek", []):
        if e.get("azon") == azon:
            e["felhasznalva"] = int(e.get("felhasznalva") or 0) + 1
    _index_ir(adat)


def meme_eredmeny(azon, nezettseg, klip):
    """Tanulás: egy videó (klip) nézettsége a benne szóló mém-hanghoz (a választásnál a bevált mémek előnyt kapnak)."""
    adat = index()
    for e in adat.get("effektek", []):
        if e.get("azon") == azon:
            v = dict(e.get("videok") or {})
            v[klip] = int(nezettseg)
            e["videok"] = dict(list(v.items())[-30:])
            e["nezettseg"] = list(e["videok"].values())
    _index_ir(adat)


def legjobb_resz(fajl, hossz, ffmpeg="ffmpeg", csattano=None):
    """A dal leghangosabb (refrén-gyanús), hossz mp-es részének kezdete másodpercben."""
    import numpy as np

    r = subprocess.run([ffmpeg, "-v", "error", "-i", fajl, "-ac", "1", "-ar", "4000", "-f", "f32le", "-"],
                       capture_output=True, timeout=120)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    mp = len(x) // 4000
    if mp <= hossz + 2:
        return 0.0
    e = (x[:mp * 4000].reshape(mp, 4000) ** 2).mean(axis=1)
    h = int(round(hossz))
    if csattano:
        # a dal "dropja" (a leghangosabb 3 mp, ahol a hangerő hirtelen megugrik) essen a csattanóra
        sima = np.convolve(e, np.ones(3) / 3, "same")
        ugras = sima - np.concatenate([np.full(4, sima[:4].mean()), sima[:-4]])
        pont = sima / (sima.max() or 1) + 0.6 * np.clip(ugras, 0, None) / (np.clip(ugras, 0, None).max() or 1)
        jelolt = [i for i in np.argsort(-pont) if csattano <= i <= mp - (hossz - csattano) - 1 and i >= 6]
        if jelolt:
            return float(int(jelolt[0] - csattano))
    ablak = np.convolve(e, np.ones(h), "valid")
    ablak[: min(len(ablak), 8)] *= 0.8          # az intró ritkán a jó rész
    return float(int(np.argmax(ablak)))


def drop_terv(fajl, hossz, ffmpeg="ffmpeg", csattano=None):
    """🎧 A dal DROPJA és ütemei a videóhoz: hol kezdődjön a dal, hogy a drop a videó közepe táján (a 30–60%-ánál, a
    csattanó előtt) szóljon – ott a képen is történik valami (villanás, rázás, szikrák, utána ütemre lüktetés).
    Drop = ahol a basszus / hangerő hirtelen és tartósan megugrik (utána 1,5 mp hangos, előtte 2 mp halkabb).
    Visszaad: {kezd, ismetel, drop (a videó ideje, mp), utem (mp), utemek: [videóidők a droptól]}."""
    import numpy as np

    SR, HOP = 4000, 40                    # 10 ms-os keretek
    r = subprocess.run([ffmpeg, "-v", "error", "-i", fajl, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, timeout=120)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    hossz_dal = len(x) / SR
    ismetel = hossz_dal < hossz + 1
    n = len(x) // HOP
    if n < 300:
        return {"kezd": 0.0, "ismetel": ismetel, "drop": None, "utem": None, "utemek": []}
    e = (x[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1)
    lp = np.convolve(x, np.ones(16) / 16, "same")                        # ~250 Hz alatti rész: a basszus
    eb = (lp[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1) * 0.6 + e * 0.4
    # tempó: az ütésburkoló autokorrelációja 60–180 BPM között (a 90–150 közötti kicsit előnyt kap)
    on = np.clip(np.diff(np.log(e + 1e-7), prepend=np.log(e[0] + 1e-7)), 0, None)
    on = on - on.mean()
    ac = np.correlate(on, on, "full")[len(on) - 1:]
    lagok = np.arange(33, 101)
    suly = np.array([1.15 if 40 <= l <= 67 else 1.0 for l in lagok])
    utem = float(lagok[int(np.argmax(ac[lagok] * suly))]) / 100
    # drop-jelöltek
    cs = np.cumsum(np.concatenate([[0], eb]))
    ut = lambda a, b: (cs[min(b, n)] - cs[max(a, 0)]) / max(1, min(b, n) - max(a, 0))  # noqa: E731
    p70 = float(np.percentile(eb, 70))
    jeloltek = []
    for i in range(150, n - 150, 5):
        utana, elotte = ut(i, i + 150), ut(i - 200, i)
        if utana > p70:
            jeloltek.append((utana / (elotte + 1e-9) * min(2.0, utana / (p70 + 1e-9)), i))
    jeloltek.sort(reverse=True)
    # a jelölt pontosítása a legerősebb ütésre a ±0,3 mp-es környezetben
    def pontos(i):
        a = max(0, i - 30)
        return (a + int(np.argmax(on[a:i + 30] if i + 30 <= n else on[a:]))) / 100
    lo, hi = 0.3 * hossz, 0.6 * hossz
    if csattano:
        hi = max(lo, min(hi, csattano - 2.5))
    kezd = drop = None
    latott = []
    for _, i in jeloltek[:60]:
        t = pontos(i)
        if any(abs(t - x_) < 3 for x_ in latott):
            continue
        latott.append(t)
        if ismetel:
            for m in range(0, int(hossz // max(1.0, hossz_dal)) + 2):
                if lo <= t + m * hossz_dal <= hi:
                    kezd, drop = 0.0, t + m * hossz_dal
                    break
        else:
            a, b = max(0.0, t - hi), min(t - lo, hossz_dal - hossz - 0.3)
            if a <= b:
                kezd = min(max(t - 0.42 * hossz, a), b)
                drop = t - kezd
        if drop is not None:
            break
    if drop is None:   # nincs jól elhelyezhető drop: a dal leghangosabb része szól, a drop a legerősebb ütés a 30–60%-ban
        kezd = 0.0 if ismetel else legjobb_resz(fajl, hossz, ffmpeg)
        a, b = int((kezd + lo) * 100), int((kezd + hi) * 100)
        drop = (a + int(np.argmax(on[a:b]))) / 100 - kezd if 0 <= a < b <= n else lo
    utemek = [round(drop + k * utem, 3) for k in range(0, int((hossz - drop) / utem) + 1)]
    return {"kezd": round(float(kezd), 2), "ismetel": bool(ismetel), "drop": round(float(drop), 2), "utem": round(utem, 3),
            "utemek": utemek}


def _hossz(fajl, ffmpeg="ffmpeg"):
    r = subprocess.run([ffmpeg, "-i", fajl], capture_output=True, text=True, timeout=30)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def kever(video, utkozes_wav, zene_fajl, hossz, cel, ffmpeg="ffmpeg", csattano=None, kezd=None, ismetel=None):
    """Néma videó + ütközéshangok + trending dal (be/kiúsztatva) -> kész mp4. Ha van csattanó, a dal dropja arra esik;
    különben a dal leghangosabb része szól."""
    if ismetel is None:
        hossz_zene = _hossz(zene_fajl, ffmpeg)
        ismetel = bool(hossz_zene and hossz_zene < hossz + 1)   # rövid brainrot-hang: körbe-körbe szól (mint a brainrot editekben)
    if kezd is None:   # (drop_terv adja; e nélkül a dal leghangosabb része / a drop a csattanóra)
        kezd = 0.0 if ismetel else legjobb_resz(zene_fajl, hossz, ffmpeg, csattano=csattano)
    ki = max(0.1, hossz - 1.2)
    szuro = (f"[2:a]{'aloop=loop=-1:size=2e9,' if ismetel else ''}atrim=start={kezd}:duration={hossz + 0.5},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo,"
             f"afade=t=in:d=0.4,afade=t=out:st={ki}:d=1.2,volume=0.85[z];"
             f"[1:a]aformat=channel_layouts=stereo,volume=0.55[u];"
             f"[z][u]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", video, "-i", utkozes_wav, "-i", zene_fajl,
                        "-filter_complex", szuro, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", cel], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"a trending zene rákeverése nem sikerült: {r.stderr[-200:]}")
    return kezd


def osszefoglalo(n=10):
    """Rövid magyar lista a csevegéshez."""
    adat = index()
    z, e = zenek(), [x for x in adat.get("effektek", []) if os.path.exists(x.get("fajl") or "")]
    if not z and not e:
        return "Még nincs letöltött trending hang."
    mikor = time.strftime("%m.%d. %H:%M", time.localtime(float(adat.get("ido") or 0)))
    sorok = [f"Trending hangok (utolsó frissítés: {mikor}):"]
    sorok += [f"🎵 {x['eloado']} – {x['cim']} (#{x['rang']}, {x['lista']}, {int(x.get('felhasznalva') or 0)}× használva)"
              for x in z if (x.get("tipus") or "dal") == "dal"][:n]
    br = [x for x in z if x.get("tipus") == "brainrot"]
    if br:
        sorok.append("🧠 Brainrot (a videók 2/3-a ezekre megy): " + ", ".join(x["cim"] for x in br[:n]))
    if e:
        sorok.append("🔊 Mém-effektek (ütközéshangnak): " + ", ".join(x["nev"] for x in e[:n]))
    return "\n".join(sorok)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    frissit(naplo=lambda s: print("  ", s, flush=True))
    print(osszefoglalo())
