"""The file the assistant made, open next to the chat: its code, a running preview, the owner's own edits and an undo."""
import shutil,subprocess,time
from pathlib import Path

LIMIT=2*1024*1024
LANGUAGES={'.setting':'fusion preset','.lua':'lua','.html':'html','.htm':'html','.md':'markdown','.py':'python','.js':'javascript','.mjs':'javascript','.ts':'typescript','.css':'css','.json':'json','.txt':'text','.csv':'csv','.sh':'bash','.swift':'swift','.xml':'xml','.svg':'xml','.yaml':'yaml','.yml':'yaml'}
CREATIONS='workspace/creations'

def creations_folder(s):
 """Where the assistant's apps, games and documents go. Writing a new file here needs no review: it touches nothing else."""
 return (s.root/'projects'/'universe'/CREATIONS).resolve()

def is_creation(s,action):
 if action.get('type')!='write_file':return False
 try:path=Path(action.get('path') or '').expanduser().resolve()
 except (OSError,RuntimeError):return False
 return creations_folder(s) in path.parents and path.suffix.lower() in LANGUAGES

def row_of(s,artifact):
 row=s.db.execute("SELECT id,project,name,path,kind FROM artifacts WHERE id=? AND kind='text'",(str(artifact or ''),)).fetchone()
 if not row:raise ValueError('Ez a fájl már nem érhető el.')
 row=dict(row);path=Path(row['path'])
 if not path.is_file():raise ValueError('A fájl már nincs a helyén: '+row['name'])
 if path.stat().st_size>LIMIT:raise ValueError('Ez a fájl túl nagy a megnyitáshoz.')
 return row,path

def versions(s,artifact):
 return s.root/'backups'/'canvas'/str(artifact)

def history(s,artifact):
 folder=versions(s,artifact)
 return sorted((p for p in folder.iterdir() if p.name.isdigit()),key=lambda p:int(p.name)) if folder.is_dir() else []

def keep_version(s,artifact,source):
 """The state before a change, so Undo also takes back what the assistant wrote."""
 folder=versions(s,artifact);folder.mkdir(parents=True,exist_ok=True)
 number=(int(history(s,artifact)[-1].name) if history(s,artifact) else 0)+1
 shutil.copy2(source,folder/str(number))

def read(s,artifact):
 row,path=row_of(s,artifact)
 try:content=path.read_text()
 except UnicodeDecodeError:raise ValueError('Ez nem szöveges fájl.') from None
 language=LANGUAGES.get(path.suffix.lower(),'text')
 return dict(id=row['id'],project=row['project'],name=row['name'],language=language,content=content,version=len(history(s,artifact))+1,can_undo=bool(history(s,artifact)),previewable=language in ('html','markdown'),updated=path.stat().st_mtime)

def save(s,artifact,content):
 row,path=row_of(s,artifact)
 if not isinstance(content,str) or len(content.encode())>LIMIT:raise ValueError('Túl nagy szöveg.')
 if content!=path.read_text():
  keep_version(s,artifact,path);path.write_text(content)
 return read(s,artifact)

def undo(s,artifact):
 row,path=row_of(s,artifact);old=history(s,artifact)
 if not old:raise ValueError('Nincs korábbi változat.')
 path.write_text(old[-1].read_text());old[-1].unlink()
 return read(s,artifact)

def open_outside(s,artifact):
 """In the owner's own browser or editor, on their click."""
 row,path=row_of(s,artifact)
 subprocess.run(['/usr/bin/open',str(path)],check=False,capture_output=True)
 return dict(opened=row['name'])

def dispatch(s,op,args=None):
 args=args or {};artifact=args.get('id')
 if op=='canvas_read':return read(s,artifact)
 if op=='canvas_save':return save(s,artifact,args.get('content'))
 if op=='canvas_undo':return undo(s,artifact)
 if op=='canvas_open':return open_outside(s,artifact)
 raise ValueError('Ismeretlen fájlművelet.')
