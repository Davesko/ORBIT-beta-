"""Enable local final renders, preserving all projects and account states."""
import json
from pathlib import Path
import shutil
import sqlite3
import time
from studio import Studio,ROOT
from configure_shorts import PROJECT


def configure():
    s=Studio();backup=ROOT/'backups'/('before-execution-'+str(int(time.time())));backup.mkdir(parents=True)
    target=sqlite3.connect(str(backup/'studio.sqlite'));s.db.backup(target);target.close()
    workspace=ROOT/'projects'/PROJECT/'workspace';shutil.copytree(workspace,backup/'workspace')
    for row in s.rows('SELECT id FROM agents WHERE project=?',(PROJECT,)):
        a=s.agent(row['id'])
        a['prompt']=a['prompt'].replace('render_short(name,start,duration,layout,subtitle)','render_short(source_video,start,duration,layout,subtitle)')
        a['prompt']=a['prompt'].replace('Nincs streamfigyelés, készvideó-render vagy feltöltés.','Helyi render_short eszköz elérhető Pixel és Lex számára: 1080×1920 MP4 mentése az Alkotásokba. Nincs streambegyűjtés vagy automatikus feltöltés.')
        a['prompt']=a['prompt'].replace('FFmpeg hangkinyerésre és mintaképkockákra működik; a kész 9:16 videórender még nincs bekötve. Tényleges render nélkül csak edit-decision listát adj.','FFmpeg hangkinyerésre, mintaképkockákra és render_short eszközzel valódi 9:16 MP4 készítésére működik. A végleges, feliratos videót Lex renderelje. Te készíts pontos kivágási tervet: source projektfájl, start és duration másodperc, layout=fit (teljes kép) vagy cover (középre vágás). Tényleges render nélkül ne jelents kész videót.')
        if a['name'] in ('Pixel','Lex'):
            if 'render_short' not in a['tools']:a['tools'].append('render_short')
        if a['name']=='Lex' and 'VÉGREHAJTÁS:' not in a['prompt']:
            a['prompt']+=' VÉGREHAJTÁS: A kiválasztott tényleges videórészlethez ments valódi SRT-t a write_file eszközzel (a teljes forrás időalapján), majd hívd a render_short(source_video,start,duration,layout,subtitle) eszközt. A source_video a bemeneti videó relatív fájlútvonala, nem cím. A subtitle az SRT projektbeli fájlneve; a motor levonja a kezdési időpontot. 1–180 másodperces videó készíthető. A felhasználó elsődlegesen az Alkotásokba kéri az MP4-et, YouTube-fiók nélkül. Ha nincs hiteles átirat, ne találj ki beszédet; csak kifejezett kérésre készíts felirat nélküli videót. A helyi videóútvonalat add tovább Reach és Vega felé.'
        if a['name']=='Scout' and 'Forrásfájl:' not in a['prompt']:
            a['prompt']+=' A legjobb jelöltet egyértelműen jelöld ki a vágáshoz. Forrásfájl: projektbeli relatív név; start és duration másodpercben; legyen 1–180 s között és a valódi forráshosszon belül. Az elsődleges cél 15–60 s, rövidebb tesztanyagnál a tényleges időtartam.'
        if a['name']=='Lex' and 'A source_video a bemeneti' not in a['prompt']:a['prompt']+=' A source_video a bemeneti videó relatív fájlútvonala (inputs/media/...), nem a videó címe.'
        s.save_agent(a)
    lex=s.rows('SELECT id FROM agents WHERE project=? AND name=?',(PROJECT,'Lex'))[0]['id']
    s.db.execute("UPDATE connections SET task=?,output_kind='video' WHERE project=? AND target=? AND archived=0",('A valódi átiratot és vágási időalapot használva készíts angol SRT-t, majd render_short eszközzel ments tényleges feliratos 9:16 MP4-et az Alkotásokba. A forrásfájl, start, duration és elkészült fájlok adatait add tovább.',PROJECT,lex));s.db.commit()
    path=workspace/'STATUS.json';status=json.loads(path.read_text());status.update(video_render_connected=True,youtube_connector_prepared=True,youtube_upload_connected=False,automatic_upload_enabled=False)
    status['missing_inputs']=['actual source video or permitted source-access connection','Google Desktop OAuth client JSON and user account authorization (optional upload only)']
    status['allowed_current_outputs']=list(dict.fromkeys(status['allowed_current_outputs']+['local_1080x1920_mp4','burned_in_english_subtitles']))
    path.write_text(json.dumps(status,ensure_ascii=False,indent=2))
    for filename in ['SHORTS-BRIEF.md','WORKSPACE.md','MODELS.md']:
        path=workspace/filename;content=path.read_text()
        content=content.replace('A streamfigyelés, folyamatos arckövetés, készvideó-render és YouTube-feltöltés még nincs bekötve.','A helyi készvideó-render működik. A streamfigyelés és folyamatos arckövetés még nincs bekötve. YouTube-feltöltés opcionális, külön fiókcsatlakozással és kézi indítással.')
        content=content.replace('A következő hiányzó lépés a készvideó-render és a forrás-/publikálási kapcsolat.','A helyi MP4-render Pixel és Lex render_short eszközével vagy a médiafelületről indítható. A forrásbegyűjtéshez további kapcsolat szükséges; YouTube opcionálisan csatlakoztatható.')
        content=content.replace('Készvideó-vágás és felirat-ráégetés még nincs integrálva.','Készvideó-vágás és SRT-ráégetés integrálva: render_short, 1080×1920, 30 fps MP4. A fit elrendezés megőrzi a teljes képet; a cover középre vág, nem követ arcot.')
        if '## Munkakövetés és render' not in content:content+='\n\n## Munkakövetés és render\nA folyamat alatt a csík az elkészült lépéseket mutatja. Kattints a figurára: Munka és bemenet → kapott feladat, átvett információ, aktuális művelet és napló. Az összeköttetésen csak rögzített adatátvételnél indul animáció.\nVideó: Fájlok és média → videó → 9:16 MP4 renderelése. Eredmény: Alkotások. YouTube nélkül is működik; a csatlakozó az Alkotások → YouTube-kapcsolat alatt van. Automatikus feltöltés nincs.\n'
        path.write_text(content)
    s.db.execute('UPDATE projects SET description=? WHERE id=?',('Angol streamklipek: helyi Whisper-átirat → jelenetválogatás → feliratos 9:16 MP4 az Alkotásokba. Élő munkakövetés és adatátadási napló. YouTube opcionális.',PROJECT));s.db.commit()
    s.event(PROJECT,'Élő munkakövetés és helyi MP4-render bekapcsolva · YouTube opcionális')
    print('Backup:',backup)

if __name__=='__main__':configure()
