# ORBIT · Local AI Studio

Independent personal macOS application. Projects are visual stations, rooms group agents, and each agent has its own role, local Ollama model, prompt, project tools, conversation, schedule and durable jobs. MiLLIONS is an existing linked project, not the studio's foundation. Its account, jobs and installation remain separate.

- Native SwiftUI/WebKit shell loads the Pixel Workshop UI with original SVG tile/sprite artwork and the approved goblin mascot. No website/server needed; remote navigation and browser requests are denied.
- Python/SQLite WAL core stores projects, messages, jobs, chains, schedules and artifacts under `~/Library/Application Support/Orbit/`.
- `hu.orbit.studio-worker` persists across closing the UI and login. One generation lane serializes studio text and ComfyUI tasks to reduce memory contention; model downloads use an independent lane. The pre-existing MiLLIONS AI remains independently managed.
- Schedules are opt-in, 5–10080 minutes, 48 unattended jobs/agent/rolling day. Missed intervals are skipped. Five model turns and at most four tool calls per turn bound a job. Mac must be awake.
- Per-agent tools: list/read project text files, create a new project file, and MiLLIONS cached state reading for trading projects. No arbitrary terminal, financial orders, external messaging or unrestricted web browsing. Tools are enforced by Python, not by prompting alone.
- Stop marks the job cancelled immediately. A current Ollama request may finish; subsequent tools/results are discarded. For ComfyUI, queued jobs can be removed; already running GPU work may complete in ComfyUI. Global interrupt is never sent because that could cancel another app's work.
- Multi-agent chains pass completed results to subsequent agents. Failure/cancellation blocks dependent jobs. Crash recovery does not replay running tools: interrupted jobs become visible failures.
- Ollama model installs are explicit streamed pulls, shared with the existing Ollama model library. Models are chosen per agent. No extra model is downloaded by installation.
- Optional local ComfyUI at `127.0.0.1:8188`: import a trusted API JSON workflow and choose the prompt input; submit prompts and collect image/video/audio outputs. A compatible engine, installed nodes and actual models are required. ORBIT does not install them or pretend text models can generate video.

Build:

```sh
swiftc -D ORBIT_APP -parse-as-library trading_lab/ReszvenyAI.swift trading_lab/Dashboard.swift orbit_app/OrbitApp.swift orbit_app/OrbitMedia.swift -o orbit_app/runtime/Orbit -framework SwiftUI -framework AppKit -framework WebKit -framework UniformTypeIdentifiers -framework PDFKit -module-cache-path trading_lab/runtime/build-cache
python3 -m unittest discover -s orbit_app -p 'test_*.py'
python3 orbit_app/install.py
```

Official references: [Ollama chat](https://docs.ollama.com/api/chat), [model pulls](https://docs.ollama.com/api/pull), [ComfyUI routes](https://docs.comfy.org/development/comfyui-server/comms_routes). Visual reference: [StarNet](https://www.starnetos.com/); ORBIT uses original artwork and its own implementation.

## 1.1: editable space and handoff graph

`space.py` adds per-project persistent rooms, recoverable removal with transactional agent rehoming, capacity/geometry validation, and acyclic connection contracts. Existing projects receive four default rooms once; later room deletion is never undone by migration. Many agents can share a room without sharing tool grants.

Graph runs snapshot reachable edges and enforce every active parent dependency before claim. Fanout and joins are supported with up to 12 agents/run; source output versus job-created artifact metadata is selected deterministically. Recipient instructions are model interpreted. Cancellation/failure propagates only to dependent jobs; editing a graph never changes queued handoff payloads. Saving a connection never starts model work.

The SVG world uses pointer capture for background pan, room rearrangement, agent transfer and drag-to-connect. Wheel zoom preserves the cursor anchor. Cameras and selected agents persist per project. Geometry is tested independently; animations pause for dragging, dialogs and hidden windows. Static rooms, avatars and connection DOM are reused across status refreshes.

Extra checks: `node orbit_app/test_map.cjs` and `node orbit_app/test_native.cjs`.


## Helyi médiaeszközök (1.2)

A Whisper és YuNet a beszélgető modelltől külön működik. A modelladatok az Orbit/models, a Python-környezet az Orbit/media-runtime könyvtárban vannak. A rendszer Python 3.9-es háttérfolyamata egy elkülönített Python 3.12 futtatót indít a rögzített media_inference.py adapterrel. A pontos csomagverziók a media-requirements.lock fájlban találhatók. A futtatókörnyezet alap Pythonja a Codex helyi runtime-könyvtárából származik; annak eltávolítása esetén a médiafuttatót újra kell telepíteni.

Projektfájlok és média → Média hozzáadása: helyi videó/hang/kép másolata a projekt saját inputs/media mappájába. Az AI nem importálhat tetszőleges külső fájlt. Echo: transcribe_media; Pixel: detect_faces. A jogosultságok más ügynökökön is bekapcsolhatók a beállításaiknál. A médiaelemzés a tartós munkasorban fut, leállítható; kész eredmények JSON/SRT fájlok a galériában. Az agent-chat ugyanazt az adaptert hívja.

Korlátok: 2 GB/bemenet, legfeljebb kétórás ASR és 30 perc futás; arcdetektálás 1–12 megadott képkockán, legfeljebb 1920 pixeles hosszú oldalon, nem folytonos követés. Csak helyi média, FFmpeg hálózati protokollok nélkül. Angol átirat, nem fordítás. Az SRT szegmensidőzítéses; a JSON szószintű időbélyegeket is tartalmaz. Streambegyűjtés, készvideó-render és YouTube-publikálás továbbra sincs integrálva.

## Élő munkakövetés, ellenőrzött kimenetek (1.3)

A folyamatjelző a ténylegesen elkészült lépéseket számolja. A modell válaszidejét nem alakítjuk kitalált százalékká. A render százalékát az FFmpeg által kiírt feldolgozott idő adja. A modellkérés, az eszköz indulása, eredménye és hibája tartós SQLite-naplóba kerül; nem tárolunk belső modellgondolatokat. A figurára kattintva a Munka és bemenet fülön megnyitható a feladat, a valóban átvett csomag, az aktuális lépés, a kimenet és a napló. A Beszélgetés fül változatlanul használható.

Az átadási bizonylat akkor keletkezik, amikor az app a fogadó bemenetébe összeállítja az előző eredményt/fájllistát. A várakozás önmagában nem adatátadás. Az összeköttetés ilyenkor 12 másodpercig animál, majd az előzmények jelzése megmarad. A kapcsolatra kattintva a bizonylatok és a szerkesztés is elérhető. Régi futásokhoz nem gyártunk utólag részletes eseményeket. A frissítés előtti megszakadt feladatok és azok valódi hibái megmaradnak.

Az összeköttetésen megadható a fogadó kötelező kimenete (szövegfájl/kép/videó/hang). Ilyenkor kizárólag az adott lépésben ténylegesen mentett megfelelő típusú alkotás jelent sikert. Fájl nélküli, késznek mondott modellválasz hibával állítja meg a függő ágakat. A Shorts Lex lépésénél kötelező MP4-kimenet van. A munkafolyamat pillanatképe rögzíti ezt, későbbi szerkesztés nem írja át a már indított munkát.

A render_short eszköz source_video paramétere a projektbeli relatív bemeneti videóútvonal. A kezdés/hossz másodpercben értendő, a hossz 1–180 s. Fit: teljes kép megőrzése kitöltő sávokkal; cover: középre vágás. Az SRT a teljes forrás időalapján legyen, a motor a részlethez igazítja, majd 1080×1920 vásznon rögzített méretű ASS-felirattá alakítja. Nincs arckövető vágás. Eredmény: H.264/AAC MP4, 30 fps, valamint renderjegyzék és szükség esetén eltolással mentett SRT az Alkotásokban.

## Opcionális YouTube-kapcsolat

Alkotások → YouTube-kapcsolat. Előfeltétel egy saját Google Cloud-projekt bekapcsolt YouTube Data API v3-mal, OAuth hozzájárulási képernyővel és Desktop app kliens JSON-jával. Tesztmódnál a bejelentkező fiókot tesztfelhasználóként is engedélyezni kell. Az OAuth JSON importálása elkülönített integrációs konfigurációba kerül, soha nem az ügynök projektfájljai közé.

A csatlakozás a rendszerböngészőben, PKCE-vel és véletlen state-tel, rövid életű 127.0.0.1-es visszahívással történik. A tokenek a macOS Kulcskarikájában vannak, nem az adatbázisban vagy a naplóban. Scope: youtube.upload és youtube.readonly (csatornaazonosításhoz). A helyi leválasztás törli a gépen tárolt tokent; a Google-fiók hozzáférési listájából a hozzájárulás külön is visszavonható.

Feltöltés: egy elkészült render az Alkotásokban → YouTube · privát feltöltés. Cím, leírás, gyermekeknek készült jelölés és külön indítás szükséges. Csak privát, folytatható feltöltés készül; nincs időzített/ügynök által automatikusan indított publikálás. Új API-projekteknél a Google auditig privátra korlátozhatja a feltöltéseket. Megszakadt feltöltés kézi újraindítása előtt ellenőrizni kell a YouTube Studiót; nem indítunk automatikusan új videót.

Hivatalos referenciák:
- https://developers.google.com/youtube/data/guides/auth/installed-apps
- https://developers.google.com/youtube/data/reference/rest/v3/videos/insert

A Google-adapter szerződését hálózat és fiók nélküli tesztek ellenőrzik (PKCE, Keychain backend, privát/resumable feltöltés). Valódi OAuth és éles feltöltés csak saját klienskonfigurációval és fiókkal ellenőrizhető; a helyi render ettől teljesen független.

## Nyilvános internetes automata gyártás és közvetlen ügynökkattintás (1.4)

Az Automata klipgyártás gomb egyszeri vagy ismétlődő, teljes helyi láncot indít. Alapbeállítás a Shorts projektnél: IShowSpeed-téma, 180 perces ellenőrzés, napi legfeljebb 3 gyártási kísérlet, átfedő automatikus futás nélkül. A témát, időközt és keretet a felületen lehet módosítani vagy leállítani. Az automatikus feltöltés kikapcsolva marad.

A producer chatből a start_short_production eszközzel valóban indíthatja a csapatot. A find_stream_clips nyilvános YouTube-találatokat ad; a download_stream_clip csak az adott projekt regisztrált candidate_id találatát fogadja, nem tetszőleges belső hálózati URL-t. A közvetlen bemenet csak https youtube.com/youtu.be videólink. A letöltő nem olvas böngészőcookie-t, nem kér felhasználói jelszót, nem futtat külső yt-dlp plugint, és nem engedélyez távolról lehúzott végrehajtókomponenst. A Node és FFmpeg az elkülönített runtime saját bin könyvtárában érhető el. A forrást 720p-ig tölti le; a végső vászon 1080×1920, ami nem jelent új képrészletet a forráshoz képest.

Automatikusan legfeljebb 180 s forrást hoz be, legfeljebb 3 jelöltet próbál, 500 MB-os letöltési korláttal. Egyedi eszközhívásban 10–600 s választható. A már letöltött videókat automata keresésnél átugorja; a felhasználó által kifejezetten megadott videólink újra feldolgozható. A nyilvános hozzáférés nem igazolja a publikálási jogosultságot. Közvetlen Twitch API/keresés nincs beállítva; a YouTube-on található streamrészletek, köztük Twitch-eredetű feltöltések kezelhetők.

A nyolclépéses végrehajtás pillanatképet rögzít, és az adott futáshoz tartozó forrást viszi végig. A helyi AI egyetlen, ellenőrzött időhatárú jelenetet választ a valós Whisper-átiratból. Érvénytelen AI-válasz esetén címkézett, valódi beszédszakaszra igazított tartalék vágás készül. A teljes képet megőrző fit elrendezés után valódi SRT-ráégetés és H.264/AAC MP4 keletkezik. A végellenőr a renderjegyzéket, méretet, forrásazonosságot és fájllenyomatot ellenőrzi; a nézettséget és a felirat minden szavának szemantikai pontosságát nem garantálja.

Az ügynökre kattintást az SVG pointer capture korábban elnyelhette. A rövid pointerup most közvetlenül választ ügynököt, a tényleges elhúzás külön ág. Egy kattintás a saját chatre vált; az Ügynök adatai részen a szoba, ütemezés, eszközök és saját utasítás olvasható. Munka közben az üzenet sorba állítható, az aktuális feladat pillanatképét nem módosítja. A futó munkát a felület előbb mutatja, mint az újabb sorba állított chatet.

A teljes, valódi internetes próba 8/8 lépést teljesített, 180 s nyilvános forrást töltött le és 17 s feliratos MP4-et hozott létre a Shorts projekt Alkotásaiban. A forrásmetaadat és eredetellenőrzés a projekt runs/ és sources/ fájljaiban megmarad.

A feliratok alapértelmezett social-safe-v1 elrendezése 1080×1920 képen a (108,880)–(864,1220) területen, legfeljebb két sorban jelenik meg, rövid halványuló/nagyító belépéssel. A hosszú szöveget mért betűszélesség alapján bontja. Ez konzervatív közös alapbeállítás; a platformok változó kezelőfelülete miatt publikálás előtt előnézet javasolt. A feliratblokkokon belüli bontás arányos időzítés, nem szó szerinti hangillesztés.

1.5: Nocturne megjelenés: grafit/neon stúdió, 4 választható háttér és ügynökönként 5 karakter (ezen a Macen mentve). Az automata klipgyártás budapesti idő szerinti dátumtartományt, hét napjait és napi indítási idősávot kezel; a határidő után kikapcsol. A már futó videót az idősáv vége nem szakítja meg.

## ORBIT 2 · fő asszisztens és SSD-modelltár
Az induló nézet a globális fő chat. A bal oldali alkalmazásváltó nyitja az ügynökműhelyt, modelltárat, alkotásokat és munkamappákat. A chat a fejlécben kiválasztott projekt környezetét kapja, saját beszélgetés- és műveletnaplóval. A helyi asszisztens képes engedélyezett szöveges fájlok olvasására, változások előkészítésére, csapatok/szobák/kapcsolatok és Shorts-ütemezés szerkesztésére, kód és automatizálás előkészítésére, VL képelemzésre és FLUX képgenerálásra.
Minden módosítás konkrét tervként jelenik meg. A fájlátírás előtt diff, végrehajtáskor biztonsági másolat és tartalomváltozás-ellenőrzés készül. A parancsok külön átnézési ablak után futnak a saját felhasználó jogosultságaival; **ez nem sandbox**, a cwd engedélyezése nem korlátozza a parancs teljes hozzáférését. Parancsonként 5 perc, naplóméret- és leállításkezelés van. Általános automatikus egér/billentyű vezérlés nincs; macOS hozzáférési engedélyt nem kapcsol be automatikusan.
Az SSD modelltár `/Volumes/MODELS/ORBIT-Models`: Qwen 2.5 14B, Qwen 2.5 Coder 14B, Qwen 2.5 VL 7B az Ollama helyi 11435 portján. A meglévő 11434-es modell változatlanul elérhető. A `model-storage.json` tárolja az útvonalakat. A kiszolgáló leválasztott SSD mellett nem hoz létre pótmappát. Az app új modellletöltése az SSD-kiszolgálóra kerül; leválasztott meghajtónál leáll hibával. A külön `image-runtime` MFLUX 0.23 + Pillow 12.3 környezetet használ, és offline módban futtatja a rögzített FLUX Schnell 4 bites csomagot. A képkimenet a projekt `media/` mappájába és az Alkotásokba kerül.

A főchat általános projekteknél ismétlődő recepteket és ügynök-feladatokat is létrehozhat. A projektkörnyezet rövid kivonat; teljes ügynök-/kapcsolatadatot csak szükség esetén olvas be, csökkentve a felesleges modellterhelést. A főchat feladatai nem jelennek meg ügynökmunkaként a térképen.

A fő asszisztens a fejlécben kijelölt projekt mellett más saját projektekhez is kérhet környezetet, és a jóváhagyásra bemutatott művelet explicit project mezőjével megcélozhatja őket. A kész műveletek szöveges projektfájljai az Alkotások között is megjelennek.

## ORBIT 2.1 · személyes asszisztens
A főchat globális beszélgetés, a projektválasztótól független előzményekkel. A régi projektbeszélgetések megmaradnak. A felső középső koboldra mutatás megnyitja az asszisztenspanelt, kattintás rögzíti; Escape és a bezárás gomb bezárja. A panel minden alkalmazásnézetben használható. Az Automata modellválasztó a helyi elérhetőséget és a feladat típusát követi: chat / Coder / VL / FLUX tervező és renderelő. Kifejezett, tisztán médiakészítési kérésnél a helyi generálás további modellválasztási vagy tervjóváhagyási kérdés nélkül indul. A fájlátírás és parancsvégrehajtás továbbra is áttekinthető terv.
Képek/videók/hangok közvetlenül a chatben jelennek meg, a natív orbit-media URL-kezelő csak ellenőrzött projektalkotásokat szolgál ki, tartománykérésekkel. A Shorts-folyamat később elkészülő videója is visszakapcsolódik a chatkéréshez. Nincs új videógenerátor letöltve: a meglévő valódi streamklip-vágó működik, szövegből tetszőleges videót nem ígérünk. Beállítások: öt színtéma és animációkapcsoló, helyi mentéssel és csökkentettmozgás-támogatással.

A 2.1-es nyelvi határ a magyar természetes nyelvű feladatokat és szereputasításokat helyi, gyorsítótárazott angol fordításként adja a háttérmodelleknek. Az eredeti beállítások, fájlok és magyar üzenetek nem változnak. Fájlútvonalakat és kódrészleteket megőrző jelölések védik a fordításban. A fő rendszer- és eszközutasítások angolok, a felhasználói válaszok és kezelőszervek magyarok. A FLUX külön angol képprompt-ellenőrzést kap. A technikai adatok, projektnevek és forrásdokumentumok eredeti szövege adatként megmarad.

A személyes asszisztens minden kérésnél teljes projekt-/ügynök-/szoba-/kapcsolatjegyzéket, közelmúltbeli feladatállapotokat és hibákat, valamint az app felépítését leíró térképet kap. Egyedi ügynökdelegálás, csapatindítás, receptek, archiválás/visszaállítás, munkaleállítás, meglévő médiaeszközök és megjelenési beállítások a fő chatből kezelhetők. A rutin belső appműveletek a felhasználó állandó felhatalmazásával automatikusak; a fájl- és parancsműveletek továbbra is külön átnézhetők. Külső publikálás és hozzáférésbővítés nem része az általános belső műveletlistának. A projekt-/ügynökneveket a rendszer pontos, projekthez kötött azonosítóra oldja fel; hibás vagy többértelmű cél nem indul el.
A Beállítások → Személyes memória és áttekintés oldalon tartós preferenciák szerkeszthetők és elfelejthetők. A memória a helyi adatbázisban marad, az angol munkakörnyezetbe fordítva kerül. A témát, animációt, hátteret és karaktereket az asszisztens ugyanabban a tartós tárolóban módosítja, amelyet a felület is követ. A „legutóbbi kész videó” egyértelmű megnyitása nem igényel modelltervezési kört.

## Pixel Workshop appearance

See [PIXEL_WORKSHOP.md](PIXEL_WORKSHOP.md) for the UI layout, original artwork, one-time room migration, mascot prompt and interaction checks.

## Másik Macre

`python3 tools/package.py` a szülőmappából elkészíti a `dist/ORBIT-<verzió>.zip` csomagot. Az app magában hordozza a háttérrészt, és első indításkor a helyére másolja; a felhasználónak a Command Line Tools és az Ollama kell (az első indítás végigvezeti), a videós és képes funkciókhoz külön médiakészlet. Apple Developer ID nélkül a macOS figyelmeztet: az első indítás jobb kattintás, Megnyitás.
