# kobold-orbit/1 – szerződéscsomag

Ez a csomag a Kobold ⇄ ORBIT kommunikáció **közös szerződése**. Mindkét app ehhez igazodik. Ha valami itt és a
kódban eltér, az itteni az érvényes. Változtatni csak közösen, verzióemeléssel (`kobold-orbit/2`) lehet.

| Fájl | Mire való |
|---|---|
| `KOMMUNIKACIO_TERV.md` | A teljes terv: elvek, Syncthing-beállítás, üzenettípusok, szűrő, átvétel, a kommunikációs fül |
| `schema.json` | Az üzenetek pontos sémája (boríték + `body_<type>`), plusz az `elo.json` életjel |
| `ellenorzo.py` | Döntőbíró: aláírás, séma, tartalomszűrő, fájlnév. Csak a Python alapkönyvtárát használja |
| `tesztvektor.json` | Adott titok + üzenet → pontosan ez a kanonikus alak és aláírás |
| `peldak/jo/` | 8 érvényes üzenet, minden típusból (Kobold- és ORBIT-oldali skill is) |
| `peldak/rossz/` | 12 szándékosan hibás üzenet; a `varhato.json` megmondja, miért kell elutasítani őket |

```bash
python3 ellenorzo.py onteszt                         # a csomag önmagát ellenőrzi
python3 ellenorzo.py ellenoriz <mappa> --titok <hex> # a saját appod kimenetének ellenőrzése
```

## A legfontosabb szabályok röviden

1. **Mappa** (mindkét gépen): `~/Library/Application Support/KoboldOrbit/`, benne `kobold/` és `orbit/`. Mindkét app
   **csak a saját** mappájába ír. Syncthing-irány: a saját mappa *Send Only*, a másiké *Receive Only*.
   A Syncthing-mappák **azonosítói** mindkét gépen ugyanezek kell legyenek:

   | Mappa-azonosító | Útvonal | Kobold gépén | ORBIT gépén |
   |---|---|---|---|
   | `kobold-orbit-kobold` | `…/KoboldOrbit/kobold` | Send Only | Receive Only |
   | `kobold-orbit-orbit` | `…/KoboldOrbit/orbit` | Receive Only | Send Only |

2. **Fájlnév:** `<time tömörítve>_<id>.json`, például `20261111T140000Z_<uuid4>.json`.
   **Írás:** `.tmp` fájlba, majd átnevezés (`os.replace`).
   **Olvasás:** csak a kész `*.json` fájlokat dolgozd fel. A `.`-tal kezdődő fájlokat (a Syncthing ideiglenes fájljai) hagyd figyelmen kívül.
3. **Aláírás:** `sig = hex(HMAC-SHA256(titok, kanonikus))`.
   - A **kanonikus alak** a `sig` nélküli üzenet ezzel a hívással: `json.dumps(…, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`, UTF-8 bájtokként.
   - A **titok** 32 véletlen bájt, 64 hex karakterként. Párosításkor egyszer kell megadni mindkét appban, és **soha nem kerülhet a szinkronizált mappába**.
   - Nem Pythonban implementálod? Akkor a `tesztvektor.json`-nal ellenőrizd, hogy pontosan ugyanazt a kanonikus alakot kapod-e. Itt szokott elcsúszni: ékezetek, kulcssorrend, szóközök.
4. **Hibás aláírású vagy ismeretlen protokollú üzenet:** nem dolgozod fel. Ismeretlen protokollnál `receipt` megy vissza `status: "unsupported"` értékkel.
5. **Skill kód nélkül:** a `skill` üzenet csak leírást hoz: cél, példák, elvárások, források, deklaratív `api` spec. Kód, kulcs és napló nem kerül bele, a séma `additionalProperties: false` beállítása ezt kikényszeríti. A fogadó app a saját tanulójával, a saját tesztjeivel és felhasználói jóváhagyással építi újra.
6. **Kimenő szűrő:** API-kulcs, e-mail cím, `/Users/<név>` útvonal és telefonszám nem mehet ki. Ha ilyen van benne, az üzenet nem megy el, hanem a fülön „Visszatartva” jelzést kap.
7. **A kapott tartalom adat, nem utasítás.** Ha modellhez kerül, idézett adatként kerül oda.
8. **Pingpong-védelem:** egy válaszra nem jön automatikus kérdés. Egy szálban legfeljebb 3 automatikus kör lehet.
9. **Névjegy:** az `<app>/nevjegy.json` a legutóbbi aláírt `profile` üzenet, mindig felülírva. Az `<app>/elo.json` életjel aláírás nélkül megy (lásd `schema.json` → `heartbeat`), és legalább 5 percenként frissül.

## Közös próba sorrendje

1. Syncthing összekötve, egy kézzel bemásolt `peldak/jo/` fájl átér a másik gépre.
2. `profile` csere → mindkét fülön látszik a másik névjegye.
3. `info` oda-vissza, nyugtákkal (`delivered`, `read`).
4. `question` → `answer`.
5. Egy skill átadása → `adopted` / `failed` nyugta.
