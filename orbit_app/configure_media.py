"""Connect installed media tools only to the existing Shorts project; preserve other work."""
import json
import shutil
import sqlite3
import time
from pathlib import Path
from studio import Studio,ROOT
from configure_shorts import PROJECT


def configure():
    s=Studio();s.project(PROJECT)
    backup=ROOT/'backups'/('before-media-'+str(int(time.time())));backup.mkdir(parents=True)
    target=sqlite3.connect(str(backup/'studio.sqlite'));s.db.backup(target);target.close()
    folder=ROOT/'projects'/PROJECT/'workspace';shutil.copytree(folder,backup/'workspace')
    old='Eszközeid projektbeli szöveges fájlok olvasására és új szöveges fájl mentésére valók. Nincs közvetlen streamfigyelő, beszédfelismerő, képkockaelemző, videóvágó vagy feltöltő eszközöd. '
    new='A projektfájlok mellett Echo transcribe_media eszköze helyi angol Whisper-átiratot és SRT-t készít; Pixel detect_faces eszköze YuNet arcdobozokat ad képeken és megadott videómintákon. Csak a saját engedélyezett eszközeidet használhatod. Nincs streamfigyelés, készvideó-render vagy feltöltés. '
    for row in s.rows('SELECT id FROM agents WHERE project=?',(PROJECT,)):
        a=s.agent(row['id']);a['prompt']=a['prompt'].replace(old,new)
        if a['name']=='Echo':
            if 'transcribe_media' not in a['tools']:a['tools'].append('transcribe_media')
            a['prompt']=a['prompt'].replace('A tervezett motor MLX Whisper large-v3-turbo; ez még nincs bekötve. Ha csak fájlnevet vagy URL-t kaptál és nincs átirat, kérd a tényleges időbélyeges átiratot; ne írj kitalált leiratot.','A MLX Whisper large-v3-turbo telepítve van. A project_files segítségével keresd az importált hangot/videót, majd transcribe_media(name) eszközzel készíts tényleges átiratot. Az eredmény JSON és SRT a results/ alatt; őrizd meg a szóidőzítést. URL-t nem dolgozhatsz fel: ehhez helyi forrásfájl szükséges.')
        if a['name']=='Pixel':
            if 'detect_faces' not in a['tools']:a['tools'].append('detect_faces')
            a['prompt']=a['prompt'].replace('A végrehajtás tervezett motorja FFmpeg, az arcdetektor opcionális YuNet. A motorok nincsenek bekötve; tényleges videó nélkül csak edit-decision listát adj.','A detect_faces(name,timestamps) valódi YuNet-arcdobozokat ad importált képről vagy legfeljebb 12 videóképkockáról, másodpercben megadott időpontokban. Ez mintavétel, nem folyamatos követés és nem személyazonosítás. FFmpeg hangkinyerésre és mintaképkockákra működik; a kész 9:16 videórender még nincs bekötve. Tényleges render nélkül csak edit-decision listát adj.')
        s.save_agent(a)
    status=json.loads((folder/'STATUS.json').read_text());status.update(asr_connected=True,frame_analysis_connected=True,face_tracking_connected=False,video_render_connected=False,media_runtime='local MLX Whisper + YuNet + bundled FFmpeg',media_input='native project file picker; local files only',max_input_bytes=2*1024**3,max_asr_seconds=7200,max_face_samples=12)
    status['allowed_current_outputs']+=['local_whisper_transcript_with_word_timestamps','srt_subtitles','sampled_face_boxes']
    status['allowed_current_outputs']=list(dict.fromkeys(status['allowed_current_outputs']))
    status['missing_inputs']=['actual source video or permitted source-access connection','finished-video rendering adapter','target YouTube channel connection']
    (folder/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
    for filename in ['SHORTS-BRIEF.md','WORKSPACE.md']:
        p=folder/filename;content=p.read_text()
        content=content.replace('A jelenlegi ORBIT ügynökök szöveges tervezésre és projektfájlokra képesek. A streamfigyelés, ASR, képkockaelemzés, renderelés és YouTube-feltöltés még nincs bekötve.','Echo már helyi Whisper-átiratot és SRT-t készít importált hangból/videóból. Pixel YuNet-arcdobozokat mér képeken és kiválasztott videóképkockákon. A streamfigyelés, folyamatos arckövetés, készvideó-render és YouTube-feltöltés még nincs bekötve.')
        content=content.replace('Első valódi próba: egy rövid, engedélyezetten feldolgozható forrásvideó és hozzá időbélyeges angol átirat. Ezek nélkül ne kérj késznek mondott vágást. A következő fejlesztés az ASR- és FFmpeg-adapter, nem további figurák hozzáadása.','Valódi feldolgozás: Projektfájlok → Média hozzáadása → Echo: Angol átirat és SRT; Pixel: Arcok keresése. Az időpontok másodpercben értendők. A következő hiányzó lépés a készvideó-render és a forrás-/publikálási kapcsolat.')
        p.write_text(content)
    (folder/'MODELS.md').write_text('''# Telepített helyi modellek

- Qwen3.8:27b: az ügynökök közös beszélgető és tervező modellje, Ollama.
- Whisper large-v3-turbo MLX: Echo transcribe_media eszköze; angol átirat, szószintű időbélyeges JSON és SRT. Helyi hang/videó, legfeljebb 2 GB és 2 óra; legfeljebb 30 perces futási idő.
- YuNet 2023mar / OpenCV 4: Pixel detect_faces eszköze; képen vagy 1–12 megadott videóképkockán arcdobozok. Nem azonosít embert, nem folyamatos követő.
- FFmpeg: helyi hangkinyerés és képkockamintavétel; nem AI-modell. Készvideó-vágás és felirat-ráégetés még nincs integrálva.

Az adapter kizárólag importált projektfájlt fogad. A feldolgozás helyben fut, hálózati forrás-URL nem adható át. A Whisper és YuNet médiaeszköz, nem chatmodell, ezért külön szerepel a modelltárban. Az ORBIT egy feldolgozási sorban futtatja a feladatokat; más appok memóriahasználatát nem szabályozza.

Használat: Projektfájlok → Média hozzáadása, majd feldolgozás. Chatben Echo és Pixel a saját engedélyezett eszközét is meghívhatja. Eredmények: results/ és a galéria.

Hivatalos források: https://huggingface.co/mlx-community/whisper-large-v3-turbo és https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
''')
    s.db.execute('UPDATE projects SET description=? WHERE id=?',('Angol streamklipek: helyi Whisper-átirat, YuNet arcdobozok, jelenetválogatás és vágási terv. Kai Cenat, IShowSpeed és további forrásjelöltek. Készvideó-render és feltöltés még nincs bekötve.',PROJECT));s.db.commit()
    s.event(PROJECT,'Whisper → Echo · YuNet → Pixel · helyi médiaeszközök telepítve')
    print('Configured media tools. Backup:',backup)

if __name__=='__main__':configure()
