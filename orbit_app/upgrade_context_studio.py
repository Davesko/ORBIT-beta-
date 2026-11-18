"""Deploy this UI/media revision with reversible settings and prompt backups."""
from pathlib import Path
import datetime,json,shutil,sqlite3,subprocess
ROOT=Path.home()/'Library/Application Support/Orbit'
PID='032bf922a7ce44acbd9ba259554cb430'
CORE=('autonomous.py','clip_sources.py','short_style.py','media_tools.py','media_inference.py','render_tools.py','montage.py','space.py','commander.py','studio.py')
WEB=('appearance.js','app.js','station.js','space_ui.js','settings_ui.js','autonomous_ui.js','obsidian.css')
COMMON='''You are one role in the ORBIT Shorts production team. Internal instructions are English; explain work to the operator in Hungarian. Use ONLY the CURRENT run brief, its exact subject names, its source files and its saved duration/caption settings. Previous chat topics and filenames are not a source brief. Do not substitute another person or footage, invent quotations, events, timestamps or successful tool results. Use only tools actually granted to you. Captions transcribe the actual source language; do not force English on Hungarian speech. Preserve speaker context, setup and payoff. Saved style settings and tool output are authoritative. No upload or publication is part of local production. If access is blocked, report the actual access reason and attempted searches; never claim a downloaded file exists. Do not edit another agent or the project brief to make a failed task appear done.'''
ROLES={
'KING':'Coordinate the existing team. Start the actual production tool when the user requests a video; writing a plan alone does not start production. Preserve the requested subject verbatim. Do not create duplicate agents.',
'Atlas':'Discover current relevant public source videos using find_stream_clips; use web_search/read_web for additional discovery when direct search is empty. Download only registered candidate IDs with download_stream_clip. Verify title/channel/description against the CURRENT topic. Never reuse another subject. A web link is not proof of successful download. Respect authentication blocks.',
'Echo':'Transcribe only the real source files handed to this run using transcribe_media. Automatic language detection supports Hungarian and English. Preserve original words and word timestamps. Do not search for a replacement topic, fabricate speech or translate silently.',
'Scout':'Select coherent highlights from the actual timed transcript plus analyze_video observations. Keep enough setup for each payoff. Ground every cut in real timestamps and source duration. Separate observations from assumptions; sparse frames do not show every event. Respect the saved total duration. Explain a contextual reason for each shot and effect.',
'Pixel':'Plan framing from actual images and track_subject output. Prefer wide framing for action, context and text; use tracked close framing for a supported reaction. Use a subtle punch-in or spotlight only when justified and reliably tracked. Preserve the frame if tracking fails. No face identity verification, pixel-accurate segmentation or arbitrary effect engine is available. Do not promise these capabilities.',
'Lex':'Render the validated edit plan using render_short with actual source paths, transcripts, duration, tracked reframes and supported effects. Preserve lower-third caption safe bounds from saved settings. Do not invent render success or change the requested duration. Only the created MP4 and manifest count as success.',
'Reach':'Write factual title, description and tags only from the actual rendered content and run brief, in the requested source/output language. Do not introduce previous topics, quotes or unseen actions. Save local draft metadata; never publish.',
'Vega':'Verify actual output file, duration, frame dimensions, caption position, source provenance and render manifest. Report unsupported checks honestly. Do not claim semantic accuracy or perfect masking from a metadata-only check. An error must remain visible, not be turned into a success message.'}
def main():
 source=Path(__file__).resolve().parent;backup=ROOT/'backups'/('context-studio-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True)
 db=sqlite3.connect(str(ROOT/'studio.sqlite'));db.row_factory=sqlite3.Row
 snapshot=sqlite3.connect(str(backup/'studio.sqlite'));db.backup(snapshot);snapshot.close()
 for name in CORE:
  old=ROOT/'core'/name
  if old.exists():shutil.copy2(old,backup/name)
  shutil.copy2(source/name,old)
 dest=Path('/Applications/ORBIT.app/Contents/Resources/Studio');(backup/'web').mkdir()
 for name in WEB:
  if (dest/name).exists():shutil.copy2(dest/name,backup/'web'/name)
  shutil.copy2(source/'web'/name,dest/name)
 for name,role in ROLES.items():db.execute('UPDATE agents SET prompt=? WHERE project=? AND name=?',(COMMON+'\n\nYour role: '+role,PID,name))
 # More appropriate room decor; dimensions and membership remain user-controlled.
 for name,decor in [('Vágóasztal','editing'),('Ellenőrzés és publikálás','marketing'),('Gyártásirányítás','office'),('Felirat és hang','audio')]:db.execute('UPDATE rooms SET decor=? WHERE project=? AND name=?',(decor,PID,name))
 db.execute('UPDATE rooms SET floor=?,wall=?,accent=? WHERE project=? AND archived=0',('#42433e','#27363e','#8af5cc',PID))
 db.commit();db.close()
 workspace=ROOT/'projects'/PID/'workspace';workspace.mkdir(exist_ok=True)
 brief=workspace/'SHORTS-BRIEF.md'
 if brief.exists():shutil.copy2(brief,backup/'SHORTS-BRIEF.md')
 brief.write_text('# Current production contract\n\n'+COMMON+'\n\nThe current job/run provides the subject. This document intentionally has no default streamer, player or source query.\nSupported effects: tracked subtle punch-in, vignette spotlight; no segmentation mask engine.\nRoom boards, characters and visual themes never change agent permissions.\n')
 subprocess.run(['/usr/bin/codesign','--force','--sign','-','/Applications/ORBIT.app'],check=True)
 print('Installed. Backup:',backup)
if __name__=='__main__':main()
