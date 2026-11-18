# ORBIT – kezdő útmutató

Öt perc, és használhatod.

## 1. Telepítés
1. Telepítsd az [Ollama](https://ollama.com/download) appot, és indítsd el egyszer.
2. Töltsd le ezt a repót, és a mappájában futtasd: `./install.sh`
3. Az ORBIT magától elindul. Az első induláskor beállítja a háttérfolyamatát is.

## 2. Első indítás
1. **Név:** add meg, hogyan szólítson. (Ez az első emlék a memóriájában.)
2. **AI-modell:**
   - Ha már van modelled, az ORBIT megkeresi: a futó Ollama modelljeit magától látja, egy másik mappát (pl. külső SSD) vagy LM Studio GGUF-fájlokat a **Mappa kiválasztása…** gombbal kötsz be.
   - Ha nincs, válassz a felajánlott, a gépedhez illő modellek közül; a letöltés a háttérben fut. 16 GB memóriához egy 7–9B-s modell ajánlott, 32 GB-hoz 14–27B-s.
3. **Kész:** kattints a Kezdésre.

## 3. Amit érdemes először kipróbálni
| Írd a fő chatbe | Mi történik |
|---|---|
| „Építs egy snake játékot” | A játék a chat mellett nyílik meg, és rögtön játszható. |
| „Mostantól tegezz és röviden válaszolj” | Megjegyzi; a **Memória** oldalon látod a gráfban. |
| „Generálj egy képet egy rókáról a hóban” | Helyi képgenerálás (a képmodellt a Modellek oldalon telepítheted). |
| „Mit csinálnak a YouTube Shorts ügynökei?” | Bemutatja a kész videós csapatot. |

## 4. Az oldalak röviden
- **Fő chat** – egy beszélgetés az összes projekthez. A műveleteket előre megmutatja, a fájlmódosításokat jóváhagyod.
- **Műhely / Ügynökök** – a projektek ügynökcsapatai; a promptjaik szerkeszthetők.
- **Memória** – amit rólad tanult, gráfként: te középen, körülötted a projektjeid, eszközeid, témáid. Minden szerkeszthető és törölhető; a tanulás kikapcsolható.
- **Modellek** – helyi modellek keresése, letöltése, mérése; a meglévők felismerése.
- **Email** – fiók összekötése (alkalmazásjelszóval); összefoglalók és válaszpiszkozatok helyi modellel.
- **Beállítások** – témák (köztük mozgó hátterű Cyber Noir), animációk, felhős modellek (opcionális).

## 5. A két kész projekt
- **YouTube Shorts:** forrásvideóból vagy streamből feliratos 9:16-os rövid videót vágó ügynökcsapat. Feltölteni csak a jóváhagyásod után tud; a YouTube-fiókot te kötöd össze.
- **MiLLIONS:** gyakorló kereskedési projekt kizárólag virtuális pénzzel, kutató, koordinátor és alkotó ügynökkel. Valódi pénz soha nem mozog. Az élő piaci műszerfal a külön kereskedési labort igényli; nélküle az ügynökök működnek, a műszerfal pedig ezt jelzi.

## 6. Élő adás figyelő és Clip Farm (videógyártás)
A két projekt az első induláskor megjelenik. Indítás: kösd össze a YouTube-fiókodat (Publikálás → Fiókok), majd kapcsold be az **Élő adás figyelő**t. Ő olvassa a legnagyobb streamerek chatjét, kivágja a legerősebb pillanatokat, a **Clip Farm** Shortot csinál belőlük, a **Publikálás** oldalon pontszámot kapnak, és te posztolsz vagy ütemezel (vagy az automatikus ütemezés teszi). Az **Autopilóta** oldal „⏹ Mindent leállít” gombja mindent megállít. A videós rész első telepítése 10–20 perc.

## Frissítés
Beállítások → Frissítés → „Van újabb verzió?” → „Frissítés most”. Git és GitHub-belépés nem kell. (Ha a Frissítés azt írja, hogy nincs frissítési forrás: töltsd le egyszer újra a tárat ZIP-ben, és futtasd benne az `./install.sh`-t.)

## Ha valami nem megy
- **„Még nincs modell, ami válaszolna”** – indítsd el az Ollamát, vagy a Modellek oldalon válassz modellt.
- **A chat nem válaszol** – a háttérfolyamat újraindítása: `launchctl kickstart -k gui/$(id -u)/hu.orbit.studio-worker`
- **Naplók:** `~/Library/Application Support/Orbit/logs`
