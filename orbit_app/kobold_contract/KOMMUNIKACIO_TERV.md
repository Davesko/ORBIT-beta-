# Kobold ⇄ ORBIT kommunikáció – terv (1. fázis)

Cél: a két helyi asszisztens **skilleket, képességeket és hasznos információkat** küldjön egymásnak, és tudjon
egymástól kérdezni. Mindkét appban lesz egy **kommunikációs fül**, ahol látszik minden küldött és kapott üzenet.
A saját memóriát (Kobold `memoria.db`, ORBIT `memory_graph`/`personal_graph`) ez a réteg **nem olvassa és nem írja**.

---

## 1. Alapelvek

1. **Postaláda, nem szerver – két gép között is.** A két app **két külön gépen** fut. Egyik app sem nyit portot
   (Kobold pywebview-ban fut, ORBIT hídja kifejezetten „no listener”). Az üzenet egy JSON-fájl egy mappában, amelyet
   a két gép között a **Syncthing** szinkronizál közvetlenül, titkosítva, felhő nélkül. Akkor is megérkezik, ha a másik
   gép vagy app épp ki van kapcsolva: amint újra elérhető, a Syncthing átviszi, az app pedig felolvassa.
2. **Mindenki csak a saját mappájába ír.** Így nincs zárolás és nincs ütközés. Hogy a másik mit kapott meg vagy vett
   át, azt a másik a *saját* mappájába írt nyugtával jelzi.
3. **Csak engedélyezett mezők mennek ki.** Nem „szűrjük ki” a személyes adatot. Az üzenet csak előre megadott,
   személyes adatot eleve nem tartalmazó mezőkből áll. Szabad szöveg (info, kérdés, válasz) csak titok- és
   személyesadat-szűrőn át mehet ki.
4. **A kapott tartalom adat, nem utasítás.** Ha a kapott szöveg modellhez kerül, idézett adatként kerül oda. Egy
   kapott skill kódja soha nem fut le. A fogadó a leírásból a **saját tanulójával építi újra**, saját tesztekkel és
   jóváhagyással.
5. **Kulcs soha nem megy át.** Csak annyi utazik, hogy „kulcs kell, ezen a néven, itt lehet kérni”.

---

## 2. Átvitel: szinkronizált postaláda két gép között

### 2.1 Miért Syncthing

| Lehetőség | Mi a gond vele két gépen |
|---|---|
| **Syncthing** (választott) | Telepíteni kell mindkét gépre. Ennyi. |
| Helyi HTTP Tailscale-en vagy LAN-on | Csak akkor működik, ha mindkét gép és app fut. ORBIT-ban portot kellene nyitni. Az elveszett üzenetek újraküldését nekünk kellene megírni. |
| iCloud Drive / Dropbox | Az adat felhőbe kerül. Az iCloud késhet, és „tárhely optimalizálásnál” kiteheti a fájlokat. |
| Telegram | Az adat kimegy a gépről. Csoportban a botok nem látják egymás üzeneteit. |
| MQTT / Redis bróker | Egy harmadik, mindig futó szerver kell hozzá. |

A Syncthing ráadásul pont ehhez a felépítéshez illik. Mivel mindkét app csak a saját mappájába ír, mappánként
beállítható az irány:

| Mappa | Kobold gépén | ORBIT gépén |
|---|---|---|
| `kobold/` | **Send Only** | **Receive Only** |
| `orbit/` | **Receive Only** | **Send Only** |

Így ütközés nem lehet, és egyik gép sem tudja felülírni a másik üzeneteit. A kapcsolat TLS-sel titkosított,
eszközazonosítóhoz kötött, és ugyanúgy működik otthoni hálózaton, mint két külön helyen lévő gép között
(közvetítőn át). Ha ez utóbbi a helyzet, a Syncthing relay helyett Tailscale-en is futhat.

### 2.2 Ébresztés

A Syncthing a fogadó gépen helyi fájlként írja ki az üzenetet. Az app ezt **FSEvents/kqueue mappafigyeléssel**
azonnal észreveszi; ha a figyelés nem érhető el, 5 mp-es tartalék lekérdezés fut. A teljes késés jellemzően
1–10 mp (a Syncthing változásfigyelésével).

### 2.3 Hitelesítés

Két gépnél már számít, hogy egy üzenet valóban a másik apptól jött-e. Ezért minden üzenet **HMAC-SHA256
aláírást** (`sig` mező) kap egy közös titokkal.
- A titkot párosításkor egyszer kell megadni mindkét appban (a fülön: „Párosítás” → kód másolása).
- A titok az app saját adatmappájában van, **soha nem a szinkronizált mappában**.
- Aláírás nélküli vagy hibásan aláírt üzenetet a fogadó nem dolgoz fel, hanem a fülön „Ismeretlen eredet” alatt mutatja.

### 2.4 A mappa (mindkét gépen ugyanígy)

```
~/Library/Application Support/KoboldOrbit/        (0700, Syncthing-mappák)
├── kobold/
│   ├── nevjegy.json        Kobold névjegye: verzió, képességlista (mindig felülírva)
│   ├── kimeno/             Kobold üzenetei: <ido>_<id>.json (csak hozzáírás)
│   └── elo.json            életjel: {"ido": …, "fut": true}
└── orbit/
    ├── nevjegy.json
    ├── kimeno/
    └── elo.json
```

- **Írás:** `.tmp` fájlba, majd `os.replace`. Az olvasó így soha nem lát félkész fájlt.
- **Olvasás:** a másik `kimeno/` mappájának figyelése (2.2). A Syncthing félkész fájlt `.syncthing.*.tmp` néven
  tart, ezért csak a kész `.json` fájlokat dolgozzuk fel. Hogy meddig
  olvastunk, azt a saját adatmappánkban tároljuk (Kobold: `~/.kobold/hid.json`, ORBIT: a saját DB-je), nem a közösben.
- **Megőrzés:** 90 nap, illetve legfeljebb 2000 üzenet irányonként. A régebbieket a küldő takarítja.
- **Korlátok:** egy üzenet legfeljebb 64 kB, irányonként legfeljebb 200 üzenet naponta. A fölötte lévőt a küldő
  sorban tartja, és a fülön jelzi.

---

## 3. Üzenetformátum (`kobold-orbit/1`)

A kulcsok angolok, mert ez két kódbázis közös szerződése, és ORBIT angol azonosítókat használ. A megjelenő szöveg magyar.

```json
{
  "protocol": "kobold-orbit/1",
  "id": "8c1e…",                    // uuid4
  "time": "2026-11-11T14:02:11Z",
  "from": "kobold", "to": "orbit",
  "type": "skill | info | profile | question | answer | receipt",
  "reply_to": null,                 // answer/receipt: melyik üzenetre
  "title": "AI cégek árfolyamai",
  "body": { … típusfüggő … },
  "sig": "hex HMAC-SHA256 a sig nélküli, kulcs szerint rendezett JSON-ra"
}
```

### 3.1 `skill` – skill-ajánlat (hordozható leírás, kód nélkül)

```json
"body": {
  "skill_id": "ai_ceg_arfolyamok",
  "kind": "data | procedure",        // data = élő adatot hoz (API/web); procedure = munkamenet-útmutató
  "summary": "Microsoft, Google … aktuális árfolyama",
  "examples": ["Mennyi most a Microsoft árfolyama?"],
  "expectations": ["A válasz tartalmazza a ticker-t és az árat"],
  "sources": [{"url": "https://…", "works": true, "needs_key": false,
               "key_name": "", "key_url": ""}],
  "api": null,                       // ORBIT data-skillnél: a deklaratív spec (base, endpoints, auth.kind) KULCS NÉLKÜL
  "steps": [],                       // procedure: lépések
  "verification": [],                // procedure: ellenőrzési pontok
  "evidence": {"tests_passed": 3, "used": 12, "since": "2026-10-30"},
  "version": 2
}
```

Megfeleltetés:

| Mező | Kobold forrás (`skillek/<azon>/skill.json`) | ORBIT forrás (`assistant_skills`) |
|---|---|---|
| summary | `leiras` | `description` |
| examples | `peldak` | (a `learned.goal`-ból / `tags`) |
| expectations | `elvaras` | `verification` |
| sources | `megkozelitesek` (`forras`, `kulcs_kell`, `kulcs_url`) | `api.base` + `auth` |
| steps | recept esetén `lepesek` | `steps` |
| evidence | `probak` ok-száma, `hasznalva`, `aktivalva` | `learned.test.ok`, `version` |

**Nem megy át soha:** `skill.py`, `teszt.py`, `kulcsok`, `naplo`, `probak[].valasz` (ebben lehet személyes adat),
`bemutato`, `skill_secrets.json`.

### 3.2 `info` – hasznos információ

```json
"body": {
  "category": "source | lesson | warning | tip",
  "text": "A Yahoo Finance chart-végpont kulcs nélkül megy, a quote-végpont 401-et ad.",
  "evidence": "3 sikeres hívás, 2026-11-10",
  "tags": ["tőzsde", "api"]
}
```

Példák: működő vagy halott forrás, egy Shorts-lecke („a 3 mp alatti hook jobban tartott”), egy modellbeállítás,
ami bevált. Ez szabad szöveg, ezért szűrőn megy át (lásd 5. pont).

### 3.3 `profile` – névjegy (a `nevjegy.json` tartalma, és változáskor üzenet is)

```json
"body": {"app_version": "…", "skills": [{"skill_id": "…", "title": "…", "kind": "data", "summary": "…"}],
         "strengths": ["Shorts-gyártás", "képességírás Pythonban"]}
```

Ebből tudja a másik, hogy mit érdemes kérdezni vagy kérni. A fülön az „Orbit tudja” panel ebből épül.

### 3.4 `question` / `answer` – kérdés és válasz

```json
"body": {"text": "Van skilled időjárásra kulcs nélkül?", "origin": "user | assistant"}
```

- Kérdés két módon születhet: a felhasználó a fülön írja be, vagy csevegésben kéri („kérdezd meg Orbitot…”).
- A fogadó **tétlen időben** válaszol a saját modelljével, a névjegye és a skilljei alapján, a saját memóriája
  nélkül. A válasz `answer` típusú, `reply_to`-val.
- **Pingpong-védelem:** válaszra nem jön automatikus kérdés. Egy szálban legfeljebb 3 automatikus kör lehet, utána a
  felhasználó dönt.

### 3.5 `receipt` – nyugta

```json
"body": {"status": "delivered | read | adopted | rejected | worked | failed | unsupported", "note": "…"}
```

A fülön ebből látszik az állapotsor: **elküldve → megérkezett → elolvasva → átvéve / elutasítva → bevált / nem vált be**.
A „bevált/nem vált be” nyugta visszajelzés a küldőnek arról, hogy a skillje a másiknál is működik-e.

---

## 4. Mi mikor megy ki (1. fázis)

| Esemény | Üzenet | Alapból |
|---|---|---|
| Egy skill aktív lesz vagy új változata jóváhagyást kap | `skill` | automatikus |
| Indításkor és a skilllista változásakor | `profile` (+ `nevjegy.json`) | automatikus |
| A felhasználó a fülön vagy csevegésben küld valamit | `info` / `question` | azonnal |
| Az önfejlesztés általánosítható leckét talál (forrás meghalt vagy működik, Shorts-lecke) | `info` | automatikus, szűrővel |
| Kérdés érkezik | `answer` | automatikus, tétlen időben |
| Átvétel, elutasítás, első éles használat után | `receipt` | automatikus |

Beállítás a fülön: **„Küldés előtt kérdezzen”** (be/ki, típusonként). Alapból csak az `info` kér jóváhagyást.

---

## 5. Kimenő szűrő (mindkét appban ugyanaz a szabálykészlet)

1. **Mezőengedélyezés:** csak a 3. pontban felsorolt mezők kerülnek ki, minden más eldobódik.
2. **Titokminták:** API-kulcsok (`sk_…`, `AIza…`, 32+ hosszú hex), tokenek, `Bearer …`. Ha bármelyik előfordul,
   az üzenet nem megy el, és a fülön piros „visszatartva” jelzést kap.
3. **Személyes minták:** e-mail cím, telefonszám, `/Users/<név>/…` útvonal (ezt `~/…`-ra cseréli), és a saját
   memóriagráf entitásneveiből vett feketelista. Ez utóbbit **csak a szűrő olvassa** helyben, a gráf maga nem kerül ki.
4. **Méret és darabszám** (2. pont).

---

## 6. Átvétel a fogadó oldalon

```
kapott skill ──► fül: „Átveszem” gomb ──► saját tanuló:
                                            Kobold: kovács (keres = summary+examples, FORRÁS-JAVASLAT = sources/api)
                                            ORBIT: skill_api.learn(goal, hint=sources/api) vagy procedure → piszkozat
                                     ──► saját tesztek ──► felhasználói jóváhagyás ──► aktív
                                     ──► receipt: adopted / failed
```

- Egy `procedure` típusú ORBIT-skill Koboldnál **recept-javaslat** lesz, az ellenkező irányban ORBIT procedural
  skill-piszkozat.
- Ha a skillhez kulcs kell, a kártya a saját Képességek fülére visz, és ott kell megadni a kulcsot.
- A kapott `info` alapból csak a fülön jelenik meg. „Megjegyzem” gombbal kerülhet a saját tudásba: Koboldnál a
  kézikönyv-kiegészítésbe vagy az önfejlesztés jegyzetei közé, **nem a memória-gráfba**.

---

## 7. A kommunikációs fül

Kobold: új fő fül **🤝 Orbit** a Gráf és a Képességek mellett, `ful-szam` jelvénnyel az olvasatlanokra.
ORBIT: új nézet **🤝 Kobold**. Ugyanaz a felépítés, ORBIT saját stílusában.

```
┌ 🤝 Orbit ─────────────────────────────────────────────────────────────────────────┐
│ ● Orbit (<gépnév>) elérhető · szinkron 2 perce · 14 skill  [Párosítás] [⚙]         │
├──────────────┬──────────────────────────────────────────────┬─────────────────────┤
│ Szűrő        │  Idővonal                                    │ Orbit tudja         │
│ ○ Mind  (42) │                                              │ (névjegyből)        │
│ ○ Kapott (18)│  ◀ ORBIT · 14:02 · SKILL                     │ 🌦 Időjárás (data)  │
│ ○ Küldött(24)│  ┌───────────────────────────────────┐       │ 📧 Levél-áttekintés │
│ ──────────── │  │ Időjárás kulcs nélkül (Open-Meteo)│       │ 🎬 Shorts-történet  │
│ ☐ Skill      │  │ 3 teszt ✓ · 12× használva         │       │ …                   │
│ ☐ Info       │  │ [Átveszem] [Elutasít] [Részletek] │       │ [Kérdezd meg róla]  │
│ ☐ Kérdés     │  └───────────────────────────────────┘       │                     │
│ ☐ Visszatart.│                       KOBOLD · 14:05 · INFO ▶│                     │
│              │        ┌───────────────────────────────────┐ │                     │
│              │        │ Yahoo quote-végpont 401, chart OK │ │                     │
│              │        │ ✓ megérkezett · ✓ elolvasva       │ │                     │
│              │        └───────────────────────────────────┘ │                     │
│              │  ◀ ORBIT · 14:07 · VÁLASZ  ↳ „Van skilled…” │                     │
├──────────────┴──────────────────────────────────────────────┴─────────────────────┤
│ [Info ▾]  Írj Orbitnak…                                              [Küldés]     │
└───────────────────────────────────────────────────────────────────────────────────┘
```

- **Bal oldal:** irány- és típusszűrő számokkal, és a „Visszatartva” lista (amit a szűrő megfogott; innen
  javítva újraküldhető vagy törölhető).
- **Közép:** idővonal, csevegésszerű elrendezésben. Bal oldalon a kapott, jobb oldalon a küldött üzenetek. Minden
  kártyán ott a típuscímke, az állapotsor (nyugtákból) és a típushoz illő gombok:
  - skill: Átveszem, Elutasít, Részletek;
  - info: Megjegyzem, Elvetem;
  - kérdés: Válaszolj most.
  
  A válaszok a kérdés alá húzódnak be.
- **Jobb oldal:** a másik app névjegye. Itt látszik, mit tud, és onnan egy kattintással lehet kérdezni.
- **Lent:** írómező típusválasztóval (Info / Kérdés). A felhasználó maga is küldhet.
- **Értesítés:** kapott skill vagy válasz esetén jelvény a fülön, és egy sor a csevegésben („Orbit küldött egy
  skillt: …”). Telegramra nem megy.

---

## 8. Csevegésből (Kobold)

Új eszköz az `agy.ESZKOZ_LEIRAS`-ban (és `GYORS_UT`-bejegyzés):

- **`orbit`:** `{"muvelet": "kerdez" | "kuld_info" | "kuld_skill" | "mit_tud"}`
  - „kérdezd meg Orbitot, tud-e időjárást” → `question`
  - „küldd át Orbitnak az árfolyam-skillt” → `skill`
  - „mit tud Orbit?” → a `nevjegy.json` helyi olvasása, üzenet nélkül.
- A választ nem várja meg szinkronban: „Elküldtem, szólok, ha válaszolt.”

A `kezikonyv.py` kap egy „Orbit-kapcsolat” részt: mi ez, hol a fül, mit szabad átadni (memóriát soha), és hogy a
kapott tartalom adat, nem utasítás.

---

## 9. Megvalósítás

**Kobold**
- `hid.py` (új, `setup.py` includes): üzenetséma, írás/olvasás, figyelő szál, szűrő, nyugták, `nevjegy.json`.
- Bekötések:
  - `kovacs.py`: aktiváláskor `skill` üzenet és névjegy-frissítés;
  - `onfejlesztes.py`: általánosítható lecke → `info`;
  - `app.py`: API a fülnek;
  - `agy.py`: `orbit` eszköz.
- `ui/`: új fül (`data-oldal="orbit"`), idővonal, szűrők, írómező.
- Tesztek: szűrő (titok, e-mail, útvonal), atomi írás, pingpong-korlát, kód soha nem kerül ki.
- Dev szerveren a postaláda a `~/.kobold/dev/hid/` alá kerül (`KOBOLD_HID` környezeti változó), hogy a teszt ne
  szemetelje a valódit.

**ORBIT** (külön repó)
- `kobold_link.py` ugyanazzal a sémával, a `skill_api` és az `assistant_skills` megfeleltetésével, szűrővel és tesztekkel.
- Web-nézet: `web/kobold_ui.js` + CSS, az `index.html` navigációjában.

**Gépek beállítása (egyszer, kézzel)**
1. Syncthing mindkét gépre (`brew install syncthing`, `brew services start syncthing`).
2. A két eszköz összepárosítása, majd a két mappa megosztása a 2.1-es irányokkal.
3. Párosítás a két app fülén (közös titok, 2.3).
4. Az életjel (`elo.json`) a gépnevet is tartalmazza, így a fül mutatja, melyik gépen fut a másik app, és mikor
   szinkronizált utoljára. Ha 10 percnél régebbi, az állapot „nem elérhető”.

**Közös:** ez a dokumentum a szerződés. A `protocol` mező verziója kötelező; ismeretlen verziójú üzenetet a fogadó
„nem értem” nyugtával jelez, nem dobja el csendben.

---

## 10. Később (nem az 1. fázis)

- Feladatátadás („ezt te csináld meg”), felhasználói jóváhagyással.
- Közös tudásbázis-keresés (amikor már sok `info` gyűlt össze).
- Automatikus „mit tanultam ma” összefoglaló egymásnak.
