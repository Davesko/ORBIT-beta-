from pathlib import Path
import datetime,json,shutil,sqlite3,subprocess,os
root=Path.home()/'Library/Application Support/Orbit';src=Path(__file__).resolve().parent;pid='032bf922a7ce44acbd9ba259554cb430'
backup=root/'backups'/('story-public-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True)
db=sqlite3.connect(str(root/'studio.sqlite'));other=sqlite3.connect(str(backup/'studio.sqlite'));db.backup(other);other.close()
for n in ('autonomous.py','editorial.py','short_style.py','video_intelligence.py','montage.py','render_tools.py','youtube.py','youtube_runtime.py','bridge.py','progress.py'):
 if (root/'core'/n).exists():shutil.copy2(root/'core'/n,backup/n)
 shutil.copy2(src/n,root/'core'/n)
web=Path('/Applications/ORBIT.app/Contents/Resources/Studio');(backup/'web').mkdir()
for n in ('autonomous_ui.js','video_ui.js','app.js'):
 shutil.copy2(web/n,backup/'web'/n);shutil.copy2(src/'web'/n,web/n)
row=db.execute('SELECT data FROM short_styles WHERE project=?',(pid,)).fetchone()
style=json.loads(row[0]) if row else {}
style.update(publish_to_youtube=True,made_for_kids=False,max_shot_seconds=12,max_shots=24)
if row:db.execute('UPDATE short_styles SET data=? WHERE project=?',(json.dumps(style),pid))
for aid,name,prompt in db.execute('SELECT id,name,prompt FROM agents WHERE project=?',(pid,)).fetchall():
 prompt=prompt.replace('No upload or publication is part of local production.','Publication is handled by the app upload queue after verified rendering, only when the user enables it.')
 if name in ('Scout','Pixel','Lex'):prompt+='\nBuild a truthful hook, necessary context, real payoff and ending. Cut at complete speech units. Default to full-frame gameplay; sparse speaking/reaction closeups only with visible evidence and a strict camera budget. Use restrained transitions and quiet sound accents, not constant zoom. Choose a readable caption theme appropriate to the video. Never claim segmentation masks exist; supported privacy masks are stationary rectangles.'
 db.execute('UPDATE agents SET prompt=? WHERE id=?',(prompt,aid))
db.commit();db.close()
subprocess.run(['/usr/bin/codesign','--force','--sign','-','/Applications/ORBIT.app'],check=True)
subprocess.run(['/bin/launchctl','kickstart','-k','gui/'+str(os.getuid())+'/hu.orbit.studio-worker'],check=True)
print('Installed with backup:',backup)
