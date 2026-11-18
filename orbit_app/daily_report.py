"""One clean morning summary on Telegram instead of a stream of event messages."""
import datetime,json,re,time
import connections

HOUR=8

def compose(s,now=None,since=None,title=None):
 now=now or time.time();since=since or now-86400
 lines=[title or '🌅 ORBIT napi összefoglaló · '+datetime.datetime.fromtimestamp(now).strftime('%m.%d.')]
 import venture
 b=venture.brief(s) or {}
 runs=s.rows("SELECT r.status FROM orbit_mission_runs r JOIN orbit_missions m ON m.id=r.mission WHERE m.origin='orbit:business-lab' AND r.finished>=?",(since,)) if b.get('status')!='not_started' else []
 if b.get('status') and b.get('status')!='not_started':
  state={'active':'fut','paused':'szünetel'}.get(b['status'],b['status'])
  build=b.get('building')
  lines.append('\n🤖 Autopilóta ('+state+'): '+str(len(runs))+' kör, ebből '+str(sum(r['status']=='done' for r in runs))+' sikeres')
  lines.append('   Most: '+('„'+build['name']+'” építése, '+str(build['done'])+'/'+str(build['total'])+' lépés' if build else 'új, ember nélküli ötleteket keres'))
  import venture_build
  for m in venture_build.recent_builds(s,b['id'],since)[-6:] if b.get('id') else []:
   lines.append('   '+('✅' if m['ran'] else '⚠️' if m['ran'] is False else '🔨')+' '+m['title']+' · '+str(m['files'])+' fájl'+(' · lefutott' if m['ran'] else ' · futtatási hiba, javítás alatt' if m['ran'] is False else '')+(' · részben' if m['partial'] else ''))
  fresh=[i['name'] for i in b.get('ideas') or [] if i.get('cycles')==1][:3]
  if fresh:lines.append('   Új ötletek: '+' · '.join(fresh))
  live=[p for p in b.get('portfolio') or [] if (p.get('launch') or {}).get('status')=='live']
  if build and build.get('launch')=='live':live.append(dict(name=build['name'],launch=dict(verdict=None)))
  if live:lines.append('   Élő oldalak: '+' · '.join(p['name']+({'passed':' ✅','failed':' ❌','low_traffic':' ⚠️'}.get((p.get('launch') or {}).get('verdict'),'')) for p in live))
  if b.get('revenue') and b['revenue']!='nincs igazolt bevétel':lines.append('   💶 Igazolt bevétel: '+b['revenue'])
  waiting=len((build or {}).get('owner_actions') or [])
  if waiting:lines.append('   Rád vár: '+str(waiting)+' lépés (az Autopilóta oldalon)')
 videos=s.db.execute("SELECT count(*) FROM jobs WHERE kind='graph' AND status='done' AND json_extract(payload,'$.auto_step')='verify' AND finished>=?",(since,)).fetchone()[0]
 stopped=s.db.execute("SELECT count(DISTINCT json_extract(payload,'$.run')) FROM jobs WHERE kind='graph' AND status='failed' AND finished>=?",(since,)).fetchone()[0]
 if videos or stopped:lines.append('\n🎬 Videók: '+str(videos)+' elkészült'+(', '+str(stopped)+' megállt' if stopped else ''))
 try:
  disk=json.loads((s.root/'storage-health.json').read_text())
  free=disk['free_bytes']/1e9
  if free<12:lines.append('\n💾 Kevés a hely: '+str(round(free,1))+' GB szabad'+(' – új munka szünetel' if disk.get('admission_paused') else ''))
 except (OSError,ValueError,KeyError):pass
 try:
  hk=json.loads((s.root/'housekeeping.json').read_text())
  idle=hk.get('unused_models') or []
  if idle:lines.append('\n🧹 Egy hete nem használt modellek: '+', '.join(m['name']+' ('+str(m['gb'])+' GB)' for m in idle[:4])+' – törölhetők, ha nem kellenek.')
 except (OSError,ValueError):pass
 improved=improvements(s,since)
 # The backlog grows in order, so the last rows are the newest work.
 if improved:lines.append('\n🛠 Az ORBIT '+str(len(improved))+' fejlesztést kapott'+(' – a legutóbbiak' if len(improved)>8 else '')+': '+' · '.join(improved[::-1][:8]))
 try:
  from youtube import needs_reconnect
  lost=needs_reconnect(s.root)
  if lost:lines.append('\n⚠️ Rád vár: YouTube-újracsatlakozás ('+str(len(lost))+' projekt) – a fejlécben lévő jelzésre kattintva.')
 except Exception:pass
 if len(lines)==1:lines.append('\nTegnap óta nem történt érdemi esemény.')
 return '\n'.join(lines)

def improvements(s,since):
 """Hungarian titles of the self-improvement backlog items finished since a time. tools/deploy.py
 copies orbit_app/IMPROVEMENT-BACKLOG.md here; a row is done when its state reads "kész (YYYY-MM-DD"."""
 try:text=(s.root/'improvements.md').read_text()
 except OSError:return []
 days={datetime.date.fromtimestamp(since+n*86400).isoformat() for n in range(int((time.time()-since)//86400)+2)}
 out=[]
 for row in text.splitlines():
  cells=[c.strip() for c in row.strip().strip('|').split('|')]
  if len(cells)<5:continue
  done=re.match(r'kész \((\d{4}-\d{2}-\d{2})',cells[-1])
  title=re.search(r'\*\*(.+?)\*\*',cells[1])
  if done and title and done.group(1) in days:out.append(title.group(1).rstrip('.'))
 return out

def today(s,now=None):
 """The /ma answer: the same summary from local midnight until now."""
 now=now or time.time();start=datetime.datetime.fromtimestamp(now).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
 return compose(s,now,since=start,title='📋 ORBIT ma · '+datetime.datetime.fromtimestamp(now).strftime('%H:%M'))

EVENING_HOUR=22

def state(s):
 try:return json.loads((s.root/'daily-report.json').read_text())
 except (OSError,ValueError):return {}

def toggle_evening(s):
 """The owner's /esti switch for the evening summary (off by default); returns the new setting."""
 st=state(s);st['evening']=not st.get('evening');(s.root/'daily-report.json').write_text(json.dumps(st));return st['evening']

def tick(s,now=None):
 """The morning summary once a day after 08:00, and, when the owner switched it on with /esti, the
 evening summary of the day after 22:00; only while Telegram notifications are on."""
 now=now or time.time();today=datetime.datetime.fromtimestamp(now);day=today.strftime('%Y-%m-%d')
 st=state(s)
 morning=today.hour>=HOUR and st.get('date')!=day
 evening=st.get('evening') and today.hour>=EVENING_HOUR and st.get('evening_date')!=day and not morning
 if not morning and not evening:return False
 cfg=connections.settings()['providers'].get('telegram',{})
 if not cfg.get('notifications') or not cfg.get('chat_id') or not connections.allowed('telegram'):return False
 if morning:text=compose(s,now);st.update(date=day,sent=now)
 else:
  start=today.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
  text=compose(s,now,since=start,title='🌙 ORBIT esti összefoglaló · '+today.strftime('%m.%d.'));st.update(evening_date=day)
 connections.http('telegram','sendMessage',dict(chat_id=cfg['chat_id'],text=text),timeout=10,priority=True)
 (s.root/'daily-report.json').write_text(json.dumps(st));return True
