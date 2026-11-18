# ORBIT · v1.0 beta

Személyes AI-asszisztens és alkotóstúdió macOS-re, ami a saját gépeden fut. Egy fő chat az összes projektedhez, ügynökcsapatok, memória, ami megtanul téged, email-kezelés, képek és videók – helyi AI-modellekkel.

- **Helyi:** a beszélgetéseid, a memóriád és a fájljaid a Macen maradnak (`~/Library/Application Support/Orbit`).
- **Friss kezdés:** az app üresen indul. Két kész projekt van benne ügynökökkel és promptokkal: **YouTube Shorts** (videóvágó csapat) és **MiLLIONS** (gyakorló kereskedés, csak virtuális pénzzel).
- **A meglévő modelljeidet felismeri:** futó Ollama, Ollama-modellmappa (akár külső SSD-n) vagy LM Studio / GGUF-fájlok.

## Telepítés

Követelmény: macOS 14 (Sonoma) vagy újabb, Apple Silicon ajánlott, legalább 16 GB memória.

```bash
git clone <ennek a repónak a címe> orbit
cd orbit
./install.sh
```

Az `install.sh` a gépeden fordítja le az alkalmazást (ehhez az Apple ingyenes Command Line Tools csomagja kell, a szkript szól, ha hiányzik), majd az `/Applications/ORBIT.app` helyre telepíti és elindítja.

A helyi AI-hoz az ingyenes [Ollama](https://ollama.com/download) kell.

👉 Az első lépésekhez lásd: **[KEZDO-UTMUTATO.md](KEZDO-UTMUTATO.md)**

## Frissítés

**Beállítások → Frissítés → „Van újabb verzió?” → „Frissítés most”.** Nem kell hozzá git és GitHub-belépés: az ORBIT letölti az új verziót, telepíti (1–3 perc, a videós rész változásakor tovább), utána zárd be és nyisd meg újra (Cmd+Q). Az adataid (memória, chatek, projektek, fiókok) megmaradnak.

- Ha a tár **privát**, egyszer meg kell adni egy csak-olvasásos frissítési kulcsot (GitHub → Settings → Developer settings → Fine-grained token, „Contents: read”); a Frissítés kártyán megjelenik a mező. Utána ez is egy kattintás.
- Ha a Frissítés kártya azt írja, hogy nincs frissítési forrás (az ORBIT a frissítő előtti telepítésből való), töltsd le egyszer újra a tárat (Code → Download ZIP), és futtasd benne: `./install.sh`. Onnantól elég a gomb.

## Videógyártás: Clip Farm és Élő adás figyelő

A telepítő a videós részt is felállítja (`setup_media.sh`: Python 3.12, yt-dlp, MLX-Whisper, arcfelismerés, ffmpeg, Node, feliratozó; Apple Silicon Mac, kb. 6 GB, 10–20 perc az első alkalommal). Ha ez a lépés nem sikerül, az ORBIT többi része működik, a videós rész később a `./setup_media.sh` futtatásával pótolható.

A két projekt az első induláskor magától megjelenik, csak el kell indítani és össze kell kötni egy YouTube-fiókkal:
1. **Fiók:** Publikálás → Fiókok → YouTube → Csatlakoztatás. (Egyszer a saját Google OAuth JSON-odat kell importálni: Kapcsolatok → YouTube.)
2. **Indítás:** Élő adás figyelő projekt → Bekapcsolás (vagy az Autopilóta oldal „Önműködés” listáján). A figyelő nyilvános chatet olvas, a legnagyobb streamerek adásainak chat-csúcsainál kivágja a jeleneteket, a Clip Farm pedig Shortot csinál belőlük (facecam felül, felirat). Egy Short pontszámot kap; **feltölteni csak te tudsz** a Publikálás oldalon, vagy bekapcsolhatod az automatikus ütemezést (alapból ki).
3. **Leállítás:** Autopilóta oldal → **⏹ Mindent leállít**.

A részletes működés: `orbit_app/STREAM-WATCH.md`.

## Eltávolítás

```bash
launchctl bootout gui/$(id -u)/hu.orbit.studio-worker 2>/dev/null; launchctl bootout gui/$(id -u)/hu.orbit.ssd-models 2>/dev/null
rm -rf /Applications/ORBIT.app ~/Library/LaunchAgents/hu.orbit.*.plist
```

Az adataid a `~/Library/Application Support/Orbit` mappában vannak; ha azokat is törölni szeretnéd, ezt a mappát töröld kézzel.

## Biztonság

Az ORBIT magától soha nem költ pénzt, nem kereskedik valódi pénzzel, nem publikál és nem ír senkinek: ezeket csak előkészíti, a döntés mindig a tiéd. A levelekre írt válaszok piszkozatok maradnak, amíg el nem küldöd őket.
