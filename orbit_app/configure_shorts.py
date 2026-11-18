"""Configure only the user's existing Shorts project; never starts jobs or downloads."""
import argparse
import hashlib
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from studio import Studio,ROOT,DEFAULT_MODEL,uid

PROJECT='032bf922a7ce44acbd9ba259554cb430'
ROOM_PLAN=[
 ('workshop','Vágóasztal','9:16 képkivágás és vágási terv',21,9.5,'workshop','#bdb09c','#ebdfca','#f1b68f'),
 ('bridge','Gyártásirányítás','Brief, feladatsor és gyártási státusz',0,0,'command','#babfa6','#e4e5d1','#d9f883'),
 ('research','Forrásellenőrzés','Streamerek, eredet és felhasználhatóság',10.5,0,'research','#a6b7b4','#dbe7df','#8ad1ee'),
 ('media','Felirat és hang','Angol szóidőzítés és hangminőség',10.5,9.5,'media','#afa9bd','#e0d9eb','#cbb2fa'),
 ('shorts-discovery','Klipvadászat','Átirat, reakciók és jelenetjelöltek',21,0,'research','#aeb9ce','#dce5f1','#a9cfff'),
 ('shorts-publish','Ellenőrzés és publikálás','Címcsomag, minőségellenőrzés, átadás',0,9.5,'command','#b0bea6','#e1ead5','#f2d897')]
COMMON=('A YouTube Shorts projektben dolgozol. A kezelőnek magyarul magyarázz, de a kész videó szövege, felirata, címe és leírása angol legyen. '
 'Olvasd el először a workspace/SHORTS-BRIEF.md és workspace/STATUS.json fájlokat. '
 'Eszközeid projektbeli szöveges fájlok olvasására és új szöveges fájl mentésére valók. Nincs közvetlen streamfigyelő, beszédfelismerő, képkockaelemző, videóvágó vagy feltöltő eszközöd. '
 'Különítsd el a tervet, a valódi bementből levezetett eredményt és a ténylegesen létrehozott médiafájlt. Ne állítsd, hogy megnéztél, átírtál, megvágtál vagy feltöltöttél videót, ha nincs ilyen eszközeredmény. '
 'Hiányzó bemenetnél jelöld: INPUT_REQUIRED; megoldatlan forráshasználatnál: SOURCE_REVIEW_REQUIRED. Ilyenkor ne találj ki idézetet, időbélyeget, reakciót vagy teljesítménymutatót. '
 'A kapcsolatok továbbadhatnak ilyen státuszt is, ezért hiányos előzményből ne készíts késznek látszó gyártási eredményt. '
 'A workspace/sources.json a forrásjelölteket tartalmazza, nem igazolt letöltési vagy publikálási engedélyeket. '
 'Meglévő fájlt ne írj felül; saját új verziót ments. ')
AGENTS=[
 ('producer','Nova','Producer','bridge','#d9f883','A megadott célból készíts rövid gyártási briefet: célközönség, angol hangvétel, 15–60 másodperces célhossz, 1080×1920 kimenet. Rögzítsd a tényleges forrásfájlt vagy a hiányzó bemenetet. Az első eredmény gyártási terv, nem kész videó.'),
 ('source','Atlas','Forrásszerkesztő','research','#8ad1ee','Ellenőrizd a megadott eredeti forrás azonosítóját, eredetét, streamert, nyelvet és a rendelkezésre bocsátott felhasználási státuszt. A felhasználó Kai és Speed neve alatt Kai Cenat és IShowSpeed tartalmára gondol. A többi jelölt xQc, CaseOh, Jynxzi. Megadott videó vagy hozzáférés hiányában csak forrásjegyzéket és hiánylistát adj. Ne tekints egy csatornalinket tartalomfelhasználási engedélynek.'),
 ('transcript','Echo','Átiratgazda','shorts-discovery','#a9cfff','A valódi beszédfelismerő kimenetét kezeld: angol szöveg, szószintű kezdet és vég, forrásazonosító, bizonytalan nevek és kifejezések. A tervezett motor MLX Whisper large-v3-turbo; ez még nincs bekötve. Ha csak fájlnevet vagy URL-t kaptál és nincs átirat, kérd a tényleges időbélyeges átiratot; ne írj kitalált leiratot.'),
 ('selection','Scout','Klipszerkesztő','shorts-discovery','#9fe5c0','Valódi időbélyeges átiratból és rendelkezésre álló reakció-/chatadatból javasolj legfeljebb 3 önálló, 15–60 másodperces jelenetet. Minden jelöltnél add meg az igazolható kezdést, véget, kontextust, első 1–2 másodperc figyelemfelkeltő részét, bizonyítékot és bizonytalanságot. Pontozásod szerkesztői becslés, nem garantált viralitás. Chatadat hiányában azt ne állítsd megfigyeltnek.'),
 ('edit','Pixel','Videószerkesztő','workshop','#f1b68f','A kiválasztott jelenetből készíts pontos 9:16 vágási specifikációt. Célozz 1080×1920 képet, olvasható kezelőfelületet és az arc/akció együttes láthatóságát. IRL felvételnél követett kivágást, játékos elrendezésnél szükség szerint arc+gameplay osztott képet tervezz. A végrehajtás tervezett motorja FFmpeg, az arcdetektor opcionális YuNet. A motorok nincsenek bekötve; tényleges videó nélkül csak edit-decision listát adj.'),
 ('captions','Lex','Felirat- és hangszerkesztő','media','#cbb2fa','Valódi angol átirat és szóidőzítés alapján tervezz rövid, jól olvasható feliratblokkokat és visszafogott szavankénti kiemelést. A nevek és érzékeny részletek ellenőrzendők; az emojit ne használd minden szónál. Tartsd szabadon az arcot és a fontos képrészleteket. Eredeti hangot őrizz meg; nem szükséges hangklónozás. ASS/SRT specifikációt csak tényleges időbélyegből készíts. Ráégetett feliratot kizárólag valódi renderkimenet esetén jelents késznek.'),
 ('packaging','Reach','Cím- és csomagszerkesztő','shorts-publish','#f2d897','A tényleges kliptartalomhoz készíts legfeljebb 3 pontos angol címet, rövid angol leírást és 3–5 releváns hashtaget. Ne találj ki idézetet vagy a klipben nem látható eseményt. Add meg a forrásmegjelölés szükséges adatait és az elkészült kimenetek listáját. Feltöltés nincs bekötve; csak publikálási csomagot készíthetsz.'),
 ('qa','Vega','Végellenőr','shorts-publish','#f8b9a3','Ellenőrizd a valódi kimenet és bizonyítékok meglétét: jelenetazonosító, 15–60 s időtartam, 9:16 kép, arc/akció láthatósága, angol felirat időzítése, cím tartalmi pontossága, hang és forrásstátusz. Puszta tervből nem állapíthatsz meg vizuális vagy hangminőséget. Add meg READY_FOR_REVIEW, INPUT_REQUIRED vagy SOURCE_REVIEW_REQUIRED állapotot tételes indoklással. YouTube-kapcsolat nélkül semmit nem tölthetsz fel.')]
EDGE_SPECS=[
 ('producer','source','Gyártási brief','Ellenőrizd a forráslistát, a tényleges elérhető bemenetet és a forráshasználat státuszát.'),
 ('source','transcript','Forráscsomag','Rendszerezd a tényleges angol átiratot és szóidőzítést; hiány esetén adj bemenetlistát.'),
 ('transcript','selection','Időbélyeges angol átirat','Az igazolt átiratból és elérhető reakcióadatokból rangsorolj legfeljebb 3 jelenetet.'),
 ('selection','edit','Kiválasztott jelenet','Az igazolható idősávhoz készíts arcot és akciót megtartó 9:16 vágási tervet.'),
 ('edit','captions','Vágási terv és időalap','A tényleges átiratot és vágási időalapot használva készíts angol felirat-specifikációt.'),
 ('captions','packaging','Feliratos klip csomagja','A ténylegesen rendelkezésre álló kliptartalomhoz készíts angol cím-, leírás- és hashtagcsomagot.'),
 ('packaging','qa','Ellenőrzésre váró csomag','Ellenőrizd a bizonyítékokat és hiányokat. Kész média és kapcsolat nélkül ne jelents publikált videót.')]

SOURCES={'content_language':'en','operator_language':'hu','collection_enabled':False,'streamers':[
 {'name':'Kai Cenat','platform':'Twitch','profile_url':'https://www.twitch.tv/kaicenat','selection':'user_requested','identity_review':'profile_candidate','reuse_status':'not_provided'},
 {'name':'IShowSpeed','platform':'YouTube','profile_url':'https://www.youtube.com/@IShowSpeed','selection':'user_requested','identity_review':'profile_candidate_verify_channel_id','reuse_status':'not_provided'},
 {'name':'xQc','platform':'Twitch','profile_url':'https://www.twitch.tv/xqc','selection':'suggested','reuse_status':'not_provided'},
 {'name':'CaseOh','platform':'Twitch','profile_url':'https://www.twitch.tv/caseoh_','selection':'suggested','reuse_status':'not_provided'},
 {'name':'Jynxzi','platform':'Twitch','profile_url':'https://www.twitch.tv/jynxzi','selection':'suggested','reuse_status':'not_provided'}]}
STATUS={'workspace':'configured','content_language':'en','operator_language':'hu','current_agent_model':DEFAULT_MODEL,'source_collection_connected':False,'asr_connected':False,'frame_analysis_connected':False,'video_render_connected':False,'youtube_upload_connected':False,'scheduled_jobs_enabled':False,'allowed_current_outputs':['production_brief','source_checklist','transcript_review_if_supplied','edit_plan','caption_spec_if_timestamps_supplied','english_metadata','quality_checklist'],'missing_inputs':['actual source video or permitted source-access connection','time-coded English transcript or connected ASR','video processing adapter','target YouTube channel connection']}
BRIEF='''# YouTube Shorts · gyártási brief

Cél: népszerű Twitch/YouTube streamerek valódi jeleneteiből angol nyelvű, 15–60 másodperces Shortsok. Elsődleges jelöltek: Kai Cenat és IShowSpeed; további javasolt jelöltek: xQc, CaseOh, Jynxzi. A profilok még ellenőrizendő forrásjelöltek, nem automatikusan letölthető vagy publikálható tartalmak.

Kimenet: 1080×1920, 9:16, a forrás alapján megfelelő képkockasebességgel; az arc és fő akció megtartása. Játékos streamhez szükség esetén osztott kép, IRL-hez követett kivágás. Eredeti angol hang, valódi átiratból időzített angol felirat, tömör angol cím és leírás. A kezelővel magyarul kommunikálj.

Minőségi cél: önmagában érthető jelenet, gyors felvezetés, pontos felirat és forráshű cím. A hangosság, nevetés, chataktivitás csak jelzés, nem garantált nézettség. Ismeretlen adatot vagy időbélyeget nem szabad kitalálni.

A jelenlegi ORBIT ügynökök szöveges tervezésre és projektfájlokra képesek. A streamfigyelés, ASR, képkockaelemzés, renderelés és YouTube-feltöltés még nincs bekötve. A szobák és kapcsolatok konfigurálása önmagában ezeket nem valósítja meg. A modellek szükségességét a MODELS.md, a tényleges integrációs állapotot a STATUS.json rögzíti.

Ne induljon automatikus ütemezés, amíg nincs tényleges bemenet és kipróbált feldolgozókapcsolat. A teljes folyamat kézzel indítható tervezési láncként; hiányos adat esetén hiánylistát adjon, ne kész videó látszatát.
'''
MODELS='''# Helyi modellek és eszközök · Mac mini M4, 32 GB

## Kezdő összeállítás

1. **Qwen3.8:27b — már telepítve.** Produceri döntések, klipjelöltek értékelése, angol címek és ellenőrzés. A helyi szolgáltatás completion, vision, tools és thinking képességet jelez; a letöltött csomag kb. 18,2 GB. Az ORBIT jelenlegi ügynökfutása azonban szöveges, képkockákat még nem továbbít ennek a modellnek. Egyetlen közös modell elég az összes szerephez; nyolc ügynökhöz nem kell nyolc modell.
2. **Whisper large-v3-turbo MLX-változat — javasolt következő modell.** `mlx-community/whisper-large-v3-turbo`, `mlx-whisper` futtatóval. Angol beszéd átirata és szószintű időbélyegek a felirathoz. A konkrét streamhangon kell ellenőrizni a neveket, átfedő beszédet és szlengszavakat. Még nincs telepítve/bekötve ehhez a projekthez.
3. **FFmpeg, megfelelő felirat- és libass-támogatással — szükséges videóeszköz, nem AI-modell.** Kivágás, egymás fölé rendezett arc/gameplay kép, átméretezés, hangfeldolgozás és felirat ráégetése. Az ORBIT-hoz végrehajtó adapter szükséges; a nyelvi modellből érkező tetszőleges parancsot nem szabad automatikusan futtatni.

## Csak indokolt esetben hozzáadandó

- **Qwen3.5:9b, kvantált változat:** kisebb nyelvi/képi modell a gyakori, rövid feladatokhoz. A hivatalos Ollama-oldal külön futtatóváltozatokat mutat; a csomag kb. 6,6–7,6 GB. Több memória maradhat az ASR-nek és vágásnak. Ezen a gépen még nem hasonlítottuk össze a meglévő 27B modellel; gyorsulást vagy pontossági elsőbbséget nem állítunk mérés nélkül. Kezdetben nem szükséges még egy nagy letöltés.
- **YuNet / OpenCV:** kis arcdetektor a streamer arcdobozának követéséhez. Nem érti meg a játék fő akcióját; a stream képelrendezését külön sablon és követési logika kezeli. Még nincs bekötve.
- **Silero VAD:** beszédszakaszok előszűrése, a hosszú hanganyag feldarabolásának támogatása. Nem nevetésfelismerő és nem nézettség-előrejelző. Még nincs bekötve.

Videógeneráló vagy beszédszintetizáló modellt ehhez a kezdeti streamklipes folyamathoz nem választanék: a projekt meglévő felvételt és eredeti hangot dolgoz fel. A 32 GB közös memórián a nagy nyelvi modell, az ASR és a képfeldolgozó feladatok ütemezetten, egymást követve fussanak. A jelenlegi MiLLIONS AI is ugyanazt a gépet használja.

## Források

- Qwen: https://ollama.com/library/qwen3.8 és https://ollama.com/library/qwen3.5:9b
- MLX Whisper, szószintű időbélyegek: https://github.com/ml-explore/mlx-examples/tree/main/whisper
- Modell: https://huggingface.co/mlx-community/whisper-large-v3-turbo
- Eredeti modell: https://huggingface.co/openai/whisper-large-v3-turbo
- YuNet: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- Silero: https://github.com/snakers4/silero-vad
- FFmpeg: https://ffmpeg.org/ffmpeg-filters.html
'''
WORKSPACE='''# A Shorts munkafelülete

A felső sorban: Gyártásirányítás → Forrásellenőrzés → Klipvadászat. Az alsó sorban jobbról balra: Vágóasztal → Felirat és hang → Ellenőrzés és publikálás.

Nova (producer) → Atlas (forrásszerkesztő) → Echo (átiratgazda) → Scout (klipszerkesztő) → Pixel (videószerkesztő) → Lex (felirat/hang) → Reach (angol cím és leírás) → Vega (végellenőrzés).

Minden összeköttetés átadja az elkészült szöveges eredményt és az adott lépés fájllistáját. A lánc előző átadási csomagját minden ügynök vigye tovább, az aktuális lépésével kiegészítve; hiányos adat státuszát tartsa meg. Nem fut automatikus streamfigyelés vagy feltöltés.

A Gyártásirányítás szobában Nova kijelölése, majd a Folyamat indítása indítja a tervezési munkát. Egy szoba pusztán szervezési hely; az összeköttetés a tényleges feladatátadás. A nyolc ügynök közös helyi modellt használ, és sorban fut.

Első valódi próba: egy rövid, engedélyezetten feldolgozható forrásvideó és hozzá időbélyeges angol átirat. Ezek nélkül ne kérj késznek mondott vágást. A következő fejlesztés az ASR- és FFmpeg-adapter, nem további figurák hozzáadása.
'''

def docs(original):return {'SHORTS-BRIEF.md':BRIEF,'MODELS.md':MODELS,'WORKSPACE.md':WORKSPACE,'ORIGINAL-BRIEF.md':original+'\n','sources.json':json.dumps(SOURCES,ensure_ascii=False,indent=2)+'\n','STATUS.json':json.dumps(STATUS,ensure_ascii=False,indent=2)+'\n'}

def configure(s,pid=PROJECT):
    project=s.project(pid)
    if project['kind']!='general':raise ValueError('Nem általános kreatív projekt.')
    if s.db.execute("SELECT 1 FROM jobs WHERE project=? AND status IN ('queued','running')",(pid,)).fetchone():raise ValueError('A projektben feladat fut; a konfigurálás előtt várd meg a végét.')
    rows=s.rows('SELECT * FROM agents WHERE project=? ORDER BY rowid',(pid,));byname={a['name']:a for a in rows}
    required={'Nova','Atlas','Pixel'}
    if not required<=set(byname):raise ValueError('Az induló csapat nem az elvárt: kézi egyeztetés szükséges.')
    original_path=s.root/'projects'/pid/'workspace/ORIGINAL-BRIEF.md'
    original=original_path.read_text().rstrip() if original_path.exists() else project['description']
    documents=docs(original)
    for name,content in documents.items():
        path=s.safe_path(pid,'workspace/'+name)
        if path.exists() and path.read_text()!=content:raise ValueError('A konfigurációs fájl kézzel módosult, nem írom felül: '+name)
    for rid,name,sub,x,y,decor,floor,wall,accent in ROOM_PLAN:s.save_room(pid,dict(id=rid,name=name,sub=sub,x=x,y=y,width=8.5,height=7.5,decor=decor,floor=floor,wall=wall,accent=accent))
    ids={}
    for key,name,role,room,color,prompt in AGENTS:
        previous=byname.get(name);aid=previous['id'] if previous else None
        ids[key]=s.save_agent(dict(id=aid,project=pid,name=name,role=role,room=room,color=color,prompt=COMMON+prompt,model=DEFAULT_MODEL,tools=['project_files','read_file','write_file'],interval=0))
    for source,target,name,task in EDGE_SPECS:s.save_connection(pid,dict(source=ids[source],target=ids[target],name=name,mode='both',instructions='Vidd tovább az előző gyártási csomagot, az igazolt forrásazonosítót és a hiányzó bemenet státuszát. A saját lépésed eredményével egészítsd ki. Csak tényleges eszközeredményt jelents elkészültnek.',task=task))
    for name,content in documents.items():
        path=s.safe_path(pid,'workspace/'+name);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
        if not s.db.execute('SELECT 1 FROM artifacts WHERE project=? AND path=?',(pid,str(path))).fetchone():s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uid(),pid,name,str(path),'text',time.time(),'shorts-workspace-configuration'))
    s.db.execute('UPDATE projects SET name=?,description=? WHERE id=?',('YouTube Shorts','Angol streamklipek: forrásellenőrzés → átirat és klipkeresés → 9:16 vágási terv → felirat → publikálási csomag. Elsődleges jelöltek: Kai Cenat és IShowSpeed. A videós kapcsolatok még bekötésre várnak.',pid));s.db.commit()
    s.event(pid,'Shorts munkafelület felépítve · 6 szoba, 8 szerep · EN tartalom · HU kezelés')
    result=s.snapshot(pid)
    assert len([r for r in result['rooms'] if not r['archived']])==6
    assert len(result['agents'])==8 and len(result['connections'])==7
    assert all(a['interval']==0 for a in result['agents'])
    return {'project':pid,'rooms':[r['name'] for r in result['rooms'] if not r['archived']],'agents':[{'name':a['name'],'role':a['role'],'room':a['room'],'model':a['model']} for a in result['agents']],'connections':len(result['connections']),'configuration_files':list(documents),'jobs_started':0,'models_downloaded':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    live=Studio()
    # Validate against an isolated complete database copy before any live change.
    with tempfile.TemporaryDirectory() as temporary:
        target=Path(temporary)/'studio.sqlite';copy=sqlite3.connect(str(target));live.db.backup(copy);copy.close();test=Studio(Path(temporary));preview=configure(test);test.db.close()
    if args.apply:
        folder=ROOT/'backups';folder.mkdir(parents=True,exist_ok=True);backup=folder/('before-shorts-workspace-'+str(int(time.time()))+'.sqlite');db=sqlite3.connect(str(backup));live.db.backup(db);db.close()
        result=configure(live);result['backup']=str(backup)
    else:result=preview
    print(json.dumps(result,ensure_ascii=False,indent=2))
