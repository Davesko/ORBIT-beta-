"""Project-scoped local web apps served through ORBIT's isolated artifact preview."""
import base64
import html
import json
import mimetypes
import uuid
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ENTRY = 'workspace/app/index.html'
IMPORTED = 'workspace/product/index.html'
ASSETS = {'.css', '.js', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}
MAX_BUNDLE = 2 * 1024 * 1024


def app_id(pid):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'orbit-workspace-app:' + pid).hex


def describe(s, pid):
    for name in (ENTRY, IMPORTED):
        path = s.safe_path(pid, name)
        if path.is_file():
            return dict(id=app_id(pid), imported=name == IMPORTED, entry=name)
    return None


class Bundle(HTMLParser):
    """Inline selected local assets while leaving external resources to the preview CSP."""
    def __init__(self, directory):
        super().__init__(convert_charrefs=False)
        self.directory = directory
        self.parts = []
        self.used = 0

    def inline(self, value, tag):
        try:
            url = urlsplit(value)
            if url.scheme or url.netloc or url.path.startswith('/') or not url.path:
                return value
            path = (self.directory / unquote(url.path)).resolve()
            if self.directory not in path.parents or not path.is_file() or path.suffix.lower() not in ASSETS:
                return value
            kind = mimetypes.guess_type(path)[0]
            allowed = {'script': path.suffix.lower() == '.js', 'link': path.suffix.lower() == '.css', 'img': bool(kind and kind.startswith('image/'))}
            size = path.stat().st_size
            if not allowed[tag] or size + self.used > MAX_BUNDLE:
                return value
            self.used += size
            return 'data:' + kind + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        except (OSError, ValueError):
            return value

    def tag(self, tag, attrs, close='>'):
        asset = {'script': 'src', 'img': 'src', 'link': 'href'}.get(tag)
        if not asset or not any(k == asset for k, _ in attrs):
            self.parts.append(self.get_starttag_text())
            return
        pairs = [(k, self.inline(v, tag) if k == asset and v else v) for k, v in attrs]
        self.parts.append('<' + tag + ''.join(' ' + k + ('="' + html.escape(v, quote=True) + '"' if v is not None else '') for k, v in pairs) + close)

    def handle_starttag(self, tag, attrs): self.tag(tag, attrs)
    def handle_startendtag(self, tag, attrs): self.tag(tag, attrs, '/>')
    def handle_endtag(self, tag): self.parts.append('</' + tag + '>')
    def handle_data(self, data): self.parts.append(data)
    def handle_entityref(self, name): self.parts.append('&' + name + ';')
    def handle_charref(self, name): self.parts.append('&#' + name + ';')
    def handle_decl(self, decl): self.parts.append('<!' + decl + '>')
    def handle_comment(self, data): self.parts.append('<!--' + data + '-->')


def bundle_path(s, pid, entry=None, artifact=None):
    if entry is None:
        app = describe(s, pid)
        if not app:
            raise ValueError('Ehhez a projekthez még nincs futtatható felület.')
        entry = s.safe_path(pid, app['entry'])
    if entry.stat().st_size > MAX_BUNDLE:
        raise ValueError('A projektfelület legfeljebb 2 MB-os HTML lehet.')
    parser = Bundle(entry.parent)
    parser.used = entry.stat().st_size
    parser.feed(entry.read_text(encoding='utf-8'))
    parser.close()
    # This HTML goes through OrbitMedia's sandbox and network-denying response policy.
    target = s.root / 'private' / 'workspace-preview' / ((artifact or app_id(pid)) + '.html')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(''.join(parser.parts), encoding='utf-8')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def data(s, pid, args):
    s.project(pid)
    s.db.execute('CREATE TABLE IF NOT EXISTS workspace_app_data(project TEXT PRIMARY KEY, value TEXT NOT NULL)')
    if 'value' not in args:
        row = s.db.execute('SELECT value FROM workspace_app_data WHERE project=?', (pid,)).fetchone()
        return json.loads(row[0]) if row else None
    value = json.dumps(args['value'], ensure_ascii=False, allow_nan=False)
    if len(value.encode()) > 128 * 1024:
        raise ValueError('A projektalkalmazás állapota legfeljebb 128 KB lehet.')
    s.db.execute('INSERT OR REPLACE INTO workspace_app_data VALUES(?,?)', (pid, value))
    s.db.commit()
    return True


def gallery_html():
    """A small runnable app using only the current canvas's image artifacts."""
    return '''<!doctype html>
<html lang="hu"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Projektgrafikák</title>
<style>body{margin:0;padding:clamp(1rem,4vw,3rem);background:#10131b;color:#eef1f8;font:16px system-ui}h1{margin-top:0}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,170px),1fr));gap:1rem}
figure{margin:0;padding:.7rem;background:#202534;border-radius:12px;overflow-wrap:anywhere}img{width:100%;aspect-ratio:1;object-fit:contain}
button{background:#c5cbff;color:#181d34;border:0;border-radius:8px;padding:.55rem .8rem;margin-top:.7rem;cursor:pointer}</style>
<h1>Elkészült grafikák</h1><p id="status">Betöltés…</p><div id="grid"></div><button id="more" hidden>További grafikák</button>
<script>
const status=document.querySelector('#status'),grid=document.querySelector('#grid'),more=document.querySelector('#more');
let items=[],offset=0,seq=0;
function request(op,args={}){
 return new Promise(resolve=>{
  const id=String(++seq);
  function receive(e){if(e.source===parent&&e.data?.orbitWorkspaceReply&&e.data.id===id){clearTimeout(timer);window.removeEventListener('message',receive);resolve(e.data.value);}}
  const timer=setTimeout(()=>{window.removeEventListener('message',receive);resolve(null);},12000);
  window.addEventListener('message',receive);parent.postMessage({orbitWorkspace:true,id,op,...args},'*');
 });
}
async function page(){
 more.hidden=true;
 for(const item of items.slice(offset,offset+8)){
  const figure=document.createElement('figure'),caption=document.createElement('figcaption');
  caption.textContent=item.name;figure.append(caption);grid.append(figure);
  const data=await request('image',{artifact:item.id});
  if(data?.image){const img=document.createElement('img');img.src=data.image;img.alt=item.name;figure.prepend(img);}
 }
 offset+=8;more.hidden=offset>=items.length;
}
more.onclick=page;
request('images').then(list=>{
 items=list||[];status.textContent=items.length?items.length+' grafika':'A projektben még nincs elérhető grafika.';page();
});
</script></html>'''
