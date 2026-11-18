"""Small display metadata for virtual gallery folders; project files stay in place."""
import json
from pathlib import Path


def enrich(studio,pid,artifacts):
    base=(studio.root/'projects'/pid).resolve()
    for item in artifacts:
        if item['kind']!='video':continue
        path=Path(item['path']).resolve()
        if base not in path.parents:continue
        try:
            manifest=path.with_suffix('.json')
            data=json.loads(manifest.read_text()) if manifest.is_file() and manifest.stat().st_size<1024*1024 else {}
            if 'duration' in data:item['duration']=data['duration']
            title=''
            parent=studio.db.execute('SELECT payload FROM jobs WHERE id=? AND project=?',(item['job'],pid)).fetchone()
            if parent:
                run=json.loads(parent['payload']).get('run')
                state=studio.db.execute('SELECT data FROM short_runs WHERE id=? AND project=?',(run,pid)).fetchone() if run else None
                if state:
                    state=json.loads(state['data']);title=state.get('metadata',{}).get('title') or state.get('source',{}).get('metadata',{}).get('title','')
            if not title and path.parent.name!='renders':
                source=path.parent/'source.json'
                if source.is_file() and source.stat().st_size<1024*1024:
                    info=json.loads(source.read_text());title=info.get('metadata',{}).get('title','')
                    item['duration']=info.get('downloaded_duration',item.get('duration'))
            if title:item['display_name']=str(title)[:120]
        except (OSError,ValueError,TypeError,KeyError):continue
    return artifacts

FOLDERS=('ready','sources','transcripts','production','project','creative','other')

def classify(base,item):
    try:path=str(Path(item['path']).relative_to(base)).lower()
    except ValueError:return 'other'
    name=item['name'].lower()
    if item['kind']=='video' and path.startswith(('renders/','media/')):return 'ready'
    if path.startswith(('sources/','inputs/')):return 'sources'
    if Path(name).suffix in ('.srt','.ass','.vtt') or path.startswith('results/transcribe_media-'):return 'transcripts'
    if path.startswith(('runs/','renders/','results/detect_faces-')) or any(word in name for word in ('publishing-package','clip-selection','quality-check','production-brief')):return 'production'
    if path.startswith('workspace/'):return 'project'
    if item['kind'] in ('image','audio','video') or path.startswith('media/'):return 'creative'
    return 'other'


def page(studio,pid,folder=None,offset=0):
    if folder is not None and folder not in FOLDERS:raise ValueError('Ismeretlen alkotásmappa.')
    if isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=1000000:raise ValueError('Érvénytelen mappalapozás.')
    base=studio.root/'projects'/pid;groups={key:[] for key in FOLDERS}
    for item in studio.rows('SELECT * FROM artifacts WHERE project=? ORDER BY created DESC',(pid,)):groups[classify(base,item)].append(item)
    items=groups[folder] if folder else []
    return dict(project=pid,projects=studio.rows('SELECT p.id,p.name,count(a.id) AS total FROM projects p LEFT JOIN artifacts a ON a.project=p.id GROUP BY p.id ORDER BY p.created'),counts={key:len(values) for key,values in groups.items()},artifacts=enrich(studio,pid,items[offset:offset+40]),offset=offset,has_more=len(items)>offset+40,total=len(items))
