"""JSON bridge for the personal native Mac app. Local AI and research only."""
import json
import os
import plistlib
import re
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from agent import local_analysis, run, number
from local_model import endpoint
from evaluate_models import evaluate
from copy_trading import demonstration, limits_from_settings
from market_data import public_quote, public_trader_snapshot
from continuous_data import NewsStore, assess_trader, atomic_json, utcnow
from portfolio import value_portfolio
from account import active_account, read_book, prepare_account, database_path
from fast_ai import PROFILES, close_orders, journal_closes, settings_from
import news_sources
from copy_trading import PaperCopyLedger, apply_paper_orders


ROOT = Path.home() / "Library/Application Support/ReszvenyAI"
MODEL = "qwen3.8:27b"
PLIST = Path.home() / "Library/LaunchAgents/hu.reszvenyai.ollama.plist"
SIZES = (25, 50, 75, 100, 150, 200)


def read_report(name):
    path = ROOT / "reports" / name
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (ValueError, OSError):
        return {"error": "Az adatállapot nem olvasható."}


def fresh(state, seconds):
    try:
        age = (utcnow() - datetime.fromisoformat(state["updated_at"])).total_seconds()
        return not state.get("error") and 0 <= age <= seconds
    except (KeyError, TypeError, ValueError): return False


def job_running(label):
    """Loaded into launchd (it may be idle: after a restart a stopped job stays loaded with 'state = not running')."""
    return subprocess.run(["/bin/launchctl", "print", "gui/" + str(os.getuid()) + "/" + label], capture_output=True).returncode == 0


def job_active(label):
    """Actually running. The page said following and fast AI were on for days while both sat loaded but idle."""
    r = subprocess.run(["/bin/launchctl", "print", "gui/" + str(os.getuid()) + "/" + label], capture_output=True, text=True)
    return r.returncode == 0 and "state = running" in r.stdout


def ensure_fresh(label):
    """A loaded but idle job is removed, so starting it again registers it with KeepAlive."""
    if job_running(label) and not job_active(label):
        subprocess.run(["/bin/launchctl", "bootout", "gui/" + str(os.getuid()) + "/" + label], capture_output=True)
        for _ in range(30):
            if not job_running(label): break
            time.sleep(0.1)


def monitor_control(start):
    label = "hu.reszvenyai.market-monitor"
    plist = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    if start:
        if not job_running(label):
            for name in ("data", "reports", "logs"):
                (ROOT / name).mkdir(mode=0o700, parents=True, exist_ok=True)
            plist.parent.mkdir(parents=True, exist_ok=True)
            config = {"Label": label, "ProgramArguments": ["/usr/bin/python3", str(ROOT / "core/watch_market.py")],
                      "EnvironmentVariables": {"PYTHONDONTWRITEBYTECODE": "1"}, "RunAtLoad": True, "KeepAlive": True,
                      "ThrottleInterval": 30, "StandardOutPath": str(ROOT / "logs/market-monitor.stdout.log"),
                      "StandardErrorPath": str(ROOT / "logs/market-monitor.stderr.log")}
            plist.write_bytes(plistlib.dumps(config))
            subprocess.run(["/bin/launchctl", "bootstrap", "gui/" + str(os.getuid()), str(plist)], check=True, capture_output=True)
    else:
        if job_running(label):
            subprocess.run(["/bin/launchctl", "bootout", "gui/" + str(os.getuid()) + "/" + label], check=True, capture_output=True)
        if plist.exists():
            config = plistlib.loads(plist.read_bytes()); config.update(RunAtLoad=False, KeepAlive=False)
            plist.write_bytes(plistlib.dumps(config))
        # launchd can retain a stopping registration briefly after bootout returns.
        # Wait before reporting completion so an immediate restart cannot skip bootstrap.
        for _ in range(30):
            if not job_running(label): break
            time.sleep(0.1)
        else:
            raise ValueError('Az adatgyűjtő leállása még folyamatban van; várj pár másodpercet.')
    return {"ok": True, "message": "Folyamatos adatgyűjtés elindítva." if start else "Adatgyűjtés szüneteltetve. A virtuális követés külön állítható le."}


def research_control(action):
    label='hu.reszvenyai.research'
    control=ROOT/'research-control.json'
    enabled=json.loads(control.read_text()).get('enabled',True) if control.exists() else True
    if action=='research_ensure' and not enabled:
        return {'ok':True,'message':'A kutató kézzel szüneteltetve van.'}
    start=action!='research_stop'
    (ROOT/'data').mkdir(parents=True,exist_ok=True)
    atomic_json(control,{'enabled':start})
    plist=Path.home()/'Library/LaunchAgents'/(label+'.plist')
    if start:
        if not job_running(label):
            for name in ('logs','reports'):(ROOT/name).mkdir(parents=True,exist_ok=True)
            configuration={'Label':label,'ProgramArguments':['/usr/bin/python3',str(ROOT/'core/watch_research.py')],
                'EnvironmentVariables':{'PYTHONDONTWRITEBYTECODE':'1'},'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
                'StandardOutPath':str(ROOT/'logs/research.stdout.log'),'StandardErrorPath':str(ROOT/'logs/research.stderr.log')}
            plist.parent.mkdir(parents=True,exist_ok=True);plist.write_bytes(plistlib.dumps(configuration))
            subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(plist)],check=True,capture_output=True)
    else:
        if job_running(label):subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid())+'/'+label],check=True,capture_output=True)
        if plist.exists():
            configuration=plistlib.loads(plist.read_bytes());configuration.update(RunAtLoad=False,KeepAlive=False)
            plist.write_bytes(plistlib.dumps(configuration))
        for _ in range(30):
            if not job_running(label):break
            time.sleep(.1)
        else:raise ValueError('A kutató leállása még folyamatban van.')
    return {'ok':True,'message':'Folyamatos AI-kutatás elindítva.' if start else 'A kutató szünetel; az eredmények megmaradnak.'}


def api_get(route):
    base = endpoint(MODEL)[0].rsplit("/api/", 1)[0]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base + "/api/" + route, timeout=5) as response:
        return json.load(response)


def status():
    version = api_get("version")["version"]
    available = api_get("tags").get("models", [])
    running = api_get("ps").get("models", [])
    installed = any(m["name"] == endpoint(MODEL)[1] for m in available)
    return {"ok": True, "message": "A helyi AI elérhető." if installed else "A szolgáltatás fut, a modell még nincs kész.",
            "version": version, "model_installed": installed, "running": running,
            "model": MODEL}


def save_annotation(symbol, news, annotation, elapsed, telemetry):
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(ROOT / "data/research.sqlite")) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS annotations (id INTEGER PRIMARY KEY, created_at TEXT, symbol TEXT, news TEXT, result TEXT, elapsed REAL, model TEXT, telemetry TEXT)")
        connection.execute("INSERT INTO annotations (created_at,symbol,news,result,elapsed,model,telemetry) VALUES (?,?,?,?,?,?,?)", (
            datetime.now(timezone.utc).isoformat(), symbol, news,
            json.dumps(annotation, ensure_ascii=False), elapsed, MODEL, json.dumps(telemetry)))


def load_paper_account():
    account = active_account(ROOT)
    state = read_report("fast-state.json" if account and account['mode'] == 'fast_ai' else "paper-copy-state.json")
    book = state.get("book")
    leader = account.get('leader') if account else state.get('leader')
    authoritative = read_book(ROOT, account)
    if authoritative is not None: book = authoritative
    elif account and account.get('mode') == 'copy' and state.get('leader') != leader: book = None
    return state, book, leader


def portfolio_summary(market=None):
    state, book, leader = load_paper_account()
    market = read_report("market-state.json") if market is None else market
    account = active_account(ROOT)
    source = "fast_ai" if account and account['mode'] == 'fast_ai' else "paper_follow" if state or book or leader else "virtual_empty"
    if source == "virtual_empty":
        book = {"settled": "10000", "positions": {}}
    settings = ROOT / "paper-risk.json"
    risk = json.loads(settings.read_text()) if settings.exists() else {"max_position_percent": "50", "max_gross_percent": "100"}
    limits_from_settings(risk)
    prices = {row["symbol"]: row["price"] for row in market.get("rows", [])}
    result = value_portfolio(book, prices, fresh(market, 15), gross_limit=risk["max_gross_percent"])
    result.update(ok=True, message="Virtuális portfólió", currency="USDC", source=source,
                  real_account_connected=False, followed_address=leader,
                  updated_at=market.get("updated_at") if result["valuation_complete"] else state.get("updated_at"),
                  copy_updated_at=state.get("updated_at"), max_gross_percent=str(risk["max_gross_percent"]))
    result['strategy_mode'] = account['mode'] if account else 'copy'
    return result


def dashboard_snapshot():
    market = read_report("market-state.json")
    discovery = read_report("trader-candidates.json")
    feed_state = read_report("news-state.json")
    news = {"items": [], "counts": {}}
    database = ROOT / "data/automatic-news.sqlite"
    if database.exists():
        store = NewsStore(database)
        try: news = store.summary()
        finally: store.close()
    market["fresh"] = fresh(market, 15)
    discovery["fresh"] = fresh(discovery, 7200)
    result = portfolio_summary(market)
    state = read_report("paper-copy-state.json")
    result.update(market=market, discovery=discovery, news_items=news["items"],
                  analyzed_count=news["counts"].get("analyzed", 0), pending_count=news["counts"].get("pending", 0),
                  news_sources=feed_state.get("sources", []), news_updated_at=feed_state.get("updated_at"),
                  news_fresh=fresh(feed_state, 180), monitor_running=job_active("hu.reszvenyai.market-monitor"),
                  following=job_active("hu.reszvenyai.paper-copy"), copy_error=state_error(),
                  copy_updated_at=state.get("updated_at"))
    fast = read_report('fast-state.json'); fast.pop('book', None)
    result.update(fast_running=job_active('hu.reszvenyai.fast-ai'), fast_message=fast.get('message'),
                  fast_research=fast.get('research'), fast_error=fast.get('error') or fast.get('entry_warning'),
                  fast=fast, fast_settings=fast_settings(), fast_profiles=PROFILES, news_source_list=news_sources.load(ROOT))
    saved = power_saved()
    result.update(research=read_report('research-state.json'),research_running=job_active('hu.reszvenyai.research'),results=results(),
                  power={"on": saved.get("on", True), "changed_at": saved.get("changed_at"), "resume": (saved.get("resume") or {}).get("mode")})
    return result


def best_candidate():
    """The top fresh trader of the ranking (copyable, steady, risk-adjusted)."""
    report = read_report("trader-candidates.json")
    ranked = sorted(report.get("candidates") or [], key=lambda c: -float(c["score"]))
    if not ranked or not fresh(report, 7200):
        raise ValueError("Még nincs friss, ellenőrzött kereskedőrangsor; a piacfigyelő óránként frissíti.")
    return ranked[0]


def results():
    """What the active mode has earned so far, for the overview: the copy or the fast trades."""
    account = active_account(ROOT)
    copy = read_report("paper-copy-state.json"); fast = read_report("fast-state.json"); research = read_report("research-state.json")
    return {"mode": ("fast" if job_active("hu.reszvenyai.fast-ai") else "copy" if job_active("hu.reszvenyai.paper-copy") else "off"),
            "account_mode": account["mode"] if account else None,
            "copy": {"leader": copy.get("leader"), "auto_best": copy.get("auto_best"), "since": copy.get("since"), "last_switch": copy.get("last_switch"),
                     "marked_equity": copy.get("marked_equity"), "error": copy.get("error"), "size_percent": copy.get("size_percent", 100)},
            "fast": {"stats": fast.get("stats"), "phase": fast.get("phase"), "message": fast.get("message"), "error": fast.get("error")},
            "eligible": research.get("eligible") or [], "watching": research.get("watching") or [], "swing_symbols": research.get("swing_symbols") or []}


def fast_settings(raw=None):
    path = ROOT / 'fast-settings.json'
    if raw is not None:
        atomic_json(path, settings_from(raw))
    try: return settings_from(json.loads(path.read_text()))
    except (OSError, ValueError): return settings_from({})


def fast_control(start):
    label='hu.reszvenyai.fast-ai'
    plist=Path.home()/'Library/LaunchAgents'/ (label+'.plist')
    if start:
        if job_active('hu.reszvenyai.paper-copy'):
            raise ValueError('A gyors mód előtt szüneteltesd a kereskedőkövetést.')
        ensure_fresh(label)
        if job_active(label): return {'ok':True,'message':'A Gyors AI már fut.'}
        prepare_account(ROOT,'fast_ai')
        # The fast AI reads the monitor's 3-second prices and the news; it needs the monitor running.
        if not job_active('hu.reszvenyai.market-monitor'): monitor_control(True)
        for name in ('logs','reports'): (ROOT/name).mkdir(parents=True,exist_ok=True)
        config={'Label':label,'ProgramArguments':['/usr/bin/python3',str(ROOT/'core/watch_fast.py')],
                'EnvironmentVariables':{'PYTHONDONTWRITEBYTECODE':'1'},'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
                'StandardOutPath':str(ROOT/'logs/fast-ai.stdout.log'),'StandardErrorPath':str(ROOT/'logs/fast-ai.stderr.log')}
        plist.parent.mkdir(parents=True,exist_ok=True);plist.write_bytes(plistlib.dumps(config))
        subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(plist)],check=True,capture_output=True)
    else:
        if job_running(label): subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid())+'/'+label],check=True,capture_output=True)
        if plist.exists():
            config=plistlib.loads(plist.read_bytes());config.update(RunAtLoad=False,KeepAlive=False);plist.write_bytes(plistlib.dumps(config))
    return {'ok':True,'message':('Gyors AI virtuális mód elindítva · ' + PROFILES[fast_settings()['profile']]['label'] + ' profil.') if start else 'Gyors AI szünetel. A nyitott virtuális pozíciók megmaradnak.'}


def flatten_paper():
    if job_active('hu.reszvenyai.paper-copy') or job_active('hu.reszvenyai.fast-ai'):
        raise ValueError('Először szüneteltesd a kereskedést, hogy ne nyisson újra pozíciót.')
    account=active_account(ROOT)
    if not account: return {'ok':True,'message':'Nincs nyitott virtuális pozíció.'}
    ledger=PaperCopyLedger(database_path(ROOT,account['database']))
    try:
        book=ledger.book();quotes={}
        for identifier in book['positions']:
            parts=identifier.split(':')
            if len(parts)!=5 or parts[:3]!=['hyperliquid','default','perpetual'] or parts[4]!='USDC': raise ValueError('Nem támogatott pozíciózárás.')
            quote=public_quote(parts[3]);quote.pop('instrument');quotes[identifier]=quote
        orders=close_orders(book,quotes,utcnow())
        ledger.connection.execute('BEGIN IMMEDIATE')
        if ledger.book()!=book: raise ValueError('A portfólió közben változott; próbáld újra.')
        ledger.connection.execute('UPDATE book SET payload=? WHERE id=1',(json.dumps(apply_paper_orders(book,orders)),))
        journal_closes(ledger.connection,book,orders,utcnow(),'Kézi lezárás (Leállítás gomb)')
        ledger.connection.execute('COMMIT')
        return {'ok':True,'message':'Minden virtuális pozíció lezárva, szimulált költségekkel.'}
    finally:
        if ledger.connection.in_transaction: ledger.connection.execute('ROLLBACK')
        ledger.close()


def wait_idle():
    for _ in range(30):
        if not job_active("hu.reszvenyai.paper-copy") and not job_active("hu.reszvenyai.fast-ai"): return
        time.sleep(0.2)


POWER_JOBS = ("hu.reszvenyai.market-monitor", "hu.reszvenyai.research", "hu.reszvenyai.fast-ai", "hu.reszvenyai.paper-copy", "hu.reszvenyai.ollama")
# Starting anything needs the main switch on; the old standalone window still asks for the monitor when it opens.
NEEDS_POWER = ("monitor_start", "research_start", "fast_start", "copy_best", "copy_start", "paper_start")


def power_saved():
    try: return json.loads((ROOT / "power.json").read_text())
    except (OSError, ValueError): return {}


def powered():
    return power_saved().get("on", True)


def unload(label):
    """Stop a launch agent and keep it from starting again at login or after a crash."""
    if job_running(label):
        subprocess.run(["/bin/launchctl", "bootout", "gui/" + str(os.getuid()) + "/" + label], capture_output=True)
    plist = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    if plist.exists():
        config = plistlib.loads(plist.read_bytes()); config.update(RunAtLoad=False, KeepAlive=False)
        plist.write_bytes(plistlib.dumps(config))
    for _ in range(30):
        if not job_running(label): return
        time.sleep(0.1)


def power(on):
    """The main switch. Off: trading stops, open virtual trades close, and news, prices, trader search, research and
    MiLLIONS' own model server stop and stay stopped after a restart. On: data collection starts and the trading
    mode that ran before the switch-off resumes."""
    now = utcnow().isoformat()
    if not on:
        mode = results()["mode"]; resume = {"mode": mode}
        if mode == "copy":
            config = json.loads((ROOT / "paper-copy-config.json").read_text())
            resume["copy"] = {"address": config["address"], "auto_best": bool(config.get("auto_best")), "size_percent": config.get("size_percent", 100)}
        try: closed = dispatch({"action": "stop_all"})["message"].replace("Minden leállítva. ", "")
        except Exception as exc:  # the switch must work even when the exchange cannot be reached to close the trades
            dispatch({"action": "mode_off"}); closed = "A nyitott virtuális ügyleteket most nem sikerült lezárni (" + str(exc) + "); a Leállítás gombbal később lezárhatod őket."
        atomic_json(ROOT / "research-control.json", {"enabled": False})
        for label in POWER_JOBS: unload(label)
        atomic_json(ROOT / "power.json", {"on": False, "changed_at": now, "resume": resume})
        return {"ok": True, "message": "A MiLLIONS kikapcsolva: nem keres híreket, nem figyel árakat, nem keres kereskedőt, nem kutat és nem kereskedik; "
                                       "a háttérben semmi nem fut, és a Mac újraindításakor sem indul el. " + closed}
    resume = power_saved().get("resume") or {}
    atomic_json(ROOT / "power.json", {"on": True, "changed_at": now})
    monitor_control(True); research_control("research_start")
    parts = ["A MiLLIONS bekapcsolva: fut a hírgyűjtés, az árfigyelés, a kereskedőkeresés és a kutatás."]
    if resume.get("mode") == "fast":
        parts.append(fast_control(True)["message"])
    elif resume.get("mode") == "copy" and resume.get("copy"):
        copy = resume["copy"]
        try: parts.append(dispatch({"action": "copy_start", "symbol": copy["address"],
                                    "settings": json.dumps({"auto_best": copy["auto_best"], "size_percent": copy["size_percent"]})})["message"])
        except Exception as exc: parts.append("A korábbi másolás nem indult újra: " + str(exc))
    else:
        parts.append("Kereskedés nem indult: az Áttekintés lapon választhatod ki, hogyan kereskedjen.")
    return {"ok": True, "message": " ".join(parts)}


def state_error():
    state = read_report("paper-copy-state.json")
    reasons = state.get("plan", {}).get("reasons", [])
    return state.get("error") or (" · ".join(reasons) if state.get("plan", {}).get("status") == "BLOCKED" else None)


def recent_activity():
    lines = []
    path = ROOT / "reports/paper-copy-state.json"
    if path.exists():
        state = json.loads(path.read_text())
        lines.append("VIRTUÁLIS KÖVETÉS · " + state.get("updated_at", ""))
        if state.get("error"):
            lines.append("Adatkapcsolati hiba: " + state["error"])
        for order in state.get("plan", {}).get("orders", []):
            lines.append(order["transition"] + " · " + order["instrument"].split(":")[-2] + " · " + order["delta"])
        lines.extend(state.get("plan", {}).get("reasons", []))
    database = ROOT / "data/research.sqlite"
    if database.exists():
        with sqlite3.connect(str(database)) as connection:
            rows = connection.execute("SELECT created_at,symbol,result FROM annotations ORDER BY id DESC LIMIT 12").fetchall()
        lines.append("\nHELYI HÍRELEMZÉSEK")
        labels = {"positive": "pozitív", "negative": "negatív", "uncertain": "bizonytalan"}
        for created, symbol, result in rows:
            lines.append(created[:19].replace("T", " ") + " UTC · " + symbol + " · " + labels.get(json.loads(result)["impact"], "ismeretlen"))
    return {"ok": True, "message": "Helyi eseménynapló", "display": "\n".join(lines) if lines else "Még nincs naplózott esemény."}


def dispatch(request):
    action = request.get("action")
    if action in ("power_on", "power_off"): return power(action == "power_on")
    if action == "research_ensure" and not powered():
        return {"ok": True, "message": "A MiLLIONS ki van kapcsolva a főkapcsolóval."}
    if action in NEEDS_POWER and not powered():
        raise ValueError("A MiLLIONS ki van kapcsolva. Előbb kapcsold be a főkapcsolóval (az ORBIT Műhelyében, a MiLLIONS lap tetején).")
    if action in ('research_start','research_stop','research_ensure'):return research_control(action)
    if action == "dashboard_snapshot": return dashboard_snapshot()
    if action in ('fast_start','fast_stop'): return fast_control(action=='fast_start')
    if action == 'paper_flatten': return flatten_paper()
    if action in ("monitor_start", "monitor_stop"): return monitor_control(action == "monitor_start")
    if action == "portfolio_summary":
        return portfolio_summary()
    if action == "activity":
        return recent_activity()
    if action in ("risk_settings", "save_risk"):
        path = ROOT / "paper-risk.json"
        if action == "save_risk":
            settings = json.loads(request.get("news", ""))
            limits_from_settings(settings)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(settings))
            temporary.replace(path)
        settings = json.loads(path.read_text()) if path.exists() else {"max_position_percent": "50", "max_gross_percent": "100"}
        return {"ok": True, "message": "Virtuális kockázati korlátok mentve." if action == "save_risk" else "Virtuális kockázati korlátok",
                "max_position_percent": str(settings["max_position_percent"]), "max_gross_percent": str(settings["max_gross_percent"])}
    if action == "trading_status":
        configuration = ROOT / "paper-copy-config.json"
        leader = json.loads(configuration.read_text()).get("address", "nincs kiválasztva") if configuration.exists() else "nincs kiválasztva"
        return {"ok": True, "message": "Kereskedési központ · virtuális üzemmód",
                "display": "Kiválasztott kereskedő: " + leader + "\nMásolási motor: virtuális tesztre kész\nVégrehajtó számla: nincs csatlakoztatva\nQuiver: API-hozzáférés szükséges\nHelyi AI: Qwen3.8-27B\n\nA másolás ugyanazt a terméket és irányt, saját tőkearányos mérettel követi. Eltérő terméket nem helyettesítünk automatikusan."}
    if action == "copy_best":
        # The simple mode: follow the best-ranked trader and let the follower switch when a clearly better one appears.
        best = best_candidate()
        result = dispatch(dict(request, action="paper_start", symbol=best["address"], auto_best=True,
                               size_percent=json.loads(request.get("settings") or "{}").get("size_percent", 100)))
        result["message"] = "A legjobb kereskedő virtuális másolása elindult: " + best["name"] + ". Ha tartósan jobb kereskedő jelenik meg, automatikusan átvált. Valódi megbízás nem történik."
        return result
    if action in ("fast_settings", "save_fast_settings"):
        settings = fast_settings(json.loads(request.get("settings") or "{}") if action == "save_fast_settings" else None)
        return {"ok": True, "message": "A Gyors AI beállításai mentve; a következő körtől érvényesek." if action == "save_fast_settings" else "Gyors AI beállítások",
                "settings": settings, "profiles": PROFILES}
    if action in ("news_sources", "save_news_sources"):
        sources = news_sources.save(ROOT, json.loads(request.get("settings") or "{}")) if action == "save_news_sources" else news_sources.load(ROOT)
        return {"ok": True, "message": "Hírforrások mentve; a gyűjtő a következő körtől ezeket olvassa." if action == "save_news_sources" else "Hírforrások",
                "sources": sources}
    if action == "trader_check":
        return dict(assess_trader(request.get("symbol", "")), ok=True, message="A számla nyilvános adatai ellenőrizve. Másolás nem indult.")
    if action == "copy_start":
        # The owner picks whom to copy (from the ranking or any public address) and how big; a different trader starts from a flat book.
        address = str(request.get("symbol", "")).strip().lower()
        if not re.fullmatch(r"0x[0-9a-f]{40}", address):
            raise ValueError("Egy nyilvános Hyperliquid-számlacím kell (0x + 40 karakter).")
        settings = json.loads(request.get("settings") or "{}")
        dispatch({"action": "mode_off"}); wait_idle()
        account = active_account(ROOT); book = read_book(ROOT, account)
        closed = ""
        if book and book.get("positions") and not (account["mode"] == "copy" and (account.get("leader") or "").lower() == address):
            closed = flatten_paper()["message"] + " "
        result = dispatch({"action": "paper_start", "symbol": address, "auto_best": bool(settings.get("auto_best")),
                           "size_percent": settings.get("size_percent", 100)})
        result["message"] = closed + "Virtuális másolás elindult: " + address[:6] + "…" + address[-4:] + " · méret " + str(settings.get("size_percent", 100)) + "%" + \
            (" · automatikusan átvált, ha tartósan jobb kereskedő akad." if settings.get("auto_best") else ".") + " Valódi megbízás nem történik."
        return result
    if action == "mode_off":
        messages = []
        if job_running("hu.reszvenyai.paper-copy"): messages.append(dispatch({"action": "paper_stop"})["message"])
        if job_running("hu.reszvenyai.fast-ai"): messages.append(fast_control(False)["message"])
        return {"ok": True, "message": " ".join(messages) or "Most nem fut kereskedési mód. A virtuális pozíciók megmaradnak."}
    if action == "stop_all":
        # One button for a layperson: no new trades, and the open virtual trades closed at today's prices.
        stopped = dispatch({"action": "mode_off"})["message"]
        wait_idle()
        book = read_book(ROOT, active_account(ROOT))
        closed = flatten_paper()["message"] if book and book.get("positions") else "Nem volt nyitott virtuális ügylet."
        return {"ok": True, "message": "Minden leállítva. " + closed}
    if action == "paper_start":
        address = str(request.get("symbol", "")).strip().lower()
        if not re.fullmatch(r"0x[0-9a-f]{40}", address):
            raise ValueError("A virtuális követéshez nyilvános számlacím szükséges.")
        ensure_fresh("hu.reszvenyai.paper-copy")
        if job_active("hu.reszvenyai.paper-copy"):
            raise ValueError("Már fut virtuális követés. Kereskedőváltás előtt állítsd le.")
        if job_active('hu.reszvenyai.fast-ai'): raise ValueError('Először szüneteltesd a Gyors AI módot.')
        account=prepare_account(ROOT,'copy',address)
        for name in ("data", "reports", "logs"):
            (ROOT / name).mkdir(mode=0o700, exist_ok=True)
        size = int(request.get("size_percent") or 100)
        if size not in SIZES: raise ValueError("A másolási méret 25 és 200% között választható.")
        (ROOT / "paper-copy-config.json").write_text(json.dumps({"address": address, "mode": "PAPER_ONLY", "database":account['database'],
                                                                 "auto_best": bool(request.get("auto_best")), "size_percent": size,
                                                                 "since": datetime.now(timezone.utc).isoformat()}))
        (ROOT / "reports/paper-copy-state.json").write_text(json.dumps({"mode": "PAPER_ONLY", "leader": address, "updated_at": datetime.now(timezone.utc).isoformat(), "status": "STARTING"}))
        plist = Path.home() / "Library/LaunchAgents/hu.reszvenyai.paper-copy.plist"
        configuration = {"Label": "hu.reszvenyai.paper-copy", "ProgramArguments": ["/usr/bin/python3", str(ROOT / "core/watch_copy.py")],
                         "EnvironmentVariables": {"PYTHONDONTWRITEBYTECODE": "1"}, "RunAtLoad": True,
                         "KeepAlive": True, "ThrottleInterval": 30,
                         "StandardOutPath": str(ROOT / "logs/paper-copy.stdout.log"),
                         "StandardErrorPath": str(ROOT / "logs/paper-copy.stderr.log")}
        plist.write_bytes(plistlib.dumps(configuration))
        subprocess.run(["/bin/launchctl", "bootstrap", "gui/" + str(os.getuid()), str(plist)], check=True, capture_output=True)
        return {"ok": True, "message": "Virtuális követés elindítva. Valódi megbízás nem történik.",
                "display": "Nyilvános számla: " + address + "\n10 000 virtuális USDC-s elkülönített tesztszámla.\nA meglévő fő perpetual pozíciókat is megpróbálja arányosan követni.\nAz állapotot a Követés állapota gomb mutatja."}
    if action == "paper_stop":
        running = subprocess.run(["/bin/launchctl", "print", "gui/" + str(os.getuid()) + "/hu.reszvenyai.paper-copy"], capture_output=True)
        if running.returncode != 0:
            return {"ok": True, "message": "Jelenleg nem fut virtuális követés."}
        subprocess.run(["/bin/launchctl", "bootout", "gui/" + str(os.getuid()) + "/hu.reszvenyai.paper-copy"], check=True, capture_output=True)
        plist = Path.home() / "Library/LaunchAgents/hu.reszvenyai.paper-copy.plist"
        if plist.exists():
            config = plistlib.loads(plist.read_bytes())
            config["RunAtLoad"] = False
            config["KeepAlive"] = False
            plist.write_bytes(plistlib.dumps(config))
        return {"ok": True, "message": "A virtuális követés leállítva. A napló és tesztpozíciók megmaradnak."}
    if action == "paper_status":
        path = ROOT / "reports/paper-copy-state.json"
        if not path.exists():
            return {"ok": True, "message": "Nincs még virtuális követési eredmény."}
        state = json.loads(path.read_text())
        running = subprocess.run(["/bin/launchctl", "print", "gui/" + str(os.getuid()) + "/hu.reszvenyai.paper-copy"], capture_output=True).returncode == 0
        plan = state.get("plan", {})
        lines = ["Kereskedő: " + state.get("leader", "ismeretlen"), "Utolsó frissítés (UTC): " + state.get("updated_at", "ismeretlen")]
        if state.get("error"):
            lines.append("Adatkapcsolati hiba: " + state["error"])
        if state.get("marked_equity"):
            lines.append("Virtuális számlaérték: " + state["marked_equity"] + " USDC")
        lines.append("Legutóbbi másolási eredmény: " + plan.get("status", state.get("status", "nincs")))
        lines.extend(plan.get("reasons", []))
        for identifier, position in state.get("book", {}).get("positions", {}).items():
            lines.append(identifier.split(":")[-2] + " · mennyiség: " + position["quantity"] + " · belépési átlagár: " + position["entry"])
        return {"ok": True, "message": "Virtuális követés: " + ("fut" if running else "leállítva; az utolsó állapot látható"),
                "display": "\n".join(lines)}
    if action == "copy_demo":
        report = demonstration()
        reports = ROOT / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "copy-demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        lines = []
        for step in report["steps"]:
            for order in step["orders"]:
                lines.append(order["transition"] + " · " + ("vétel" if order["side"] == "buy" else "eladás") + " · " + order["delta"] + " BTC · célpozíció: " + order["target"])
        return {"ok": True, "message": "A kitalált kereskedő másolási próbája lefutott.",
                "display": "KITALÁLT KERESKEDŐ · VIRTUÁLIS PÉNZ\n\n" + "\n".join(lines) + "\n\nVégső nyitott pozíciók: " + str(len(report["final_book"]["positions"])) + "\nDíjak és kedvezőtlen teljesülés számítva; finanszírozás és likvidálás nincs modellezve."}
    if action == "market_quote":
        quote = public_quote("BTC")
        return {"ok": True, "message": "Nyilvános piaci adat beérkezett; megbízás nem történt.",
                "display": "ÉLŐ ADAT · HYPERLIQUID BTC PERPETUAL\n\nVételi oldal: " + quote["bid"] + "\nEladási oldal: " + quote["ask"] + "\nForrás ideje (UTC): " + quote["at"] + "\n\nEz árfolyam-adatkapcsolat, nem végrehajtási vagy teljes piacokat lefedő kapcsolat."}
    if action == "trader_preview":
        preview = public_trader_snapshot(str(request.get("symbol", "")).strip())
        source = preview["snapshot"]
        lines = [key.split(":")[-2] + ": " + value["quantity"] for key, value in source["positions"].items()]
        return {"ok": True, "message": "A nyilvános számla fő perpetual pozíciói lekérdezve. Követés nem indult.",
                "display": "Számla: " + source["leader"] + "\nSzámlaérték: " + source["equity"] + "\n\n" + ("\n".join(lines) if lines else "Nincs nyitott pozíció ebben a hatókörben.") + "\n\nSpot, más számlák, vaultok és HIP-3 piacok nincsenek benne."}
    if action == "status":
        return status()
    if action == "start":
        try:
            return status()
        except Exception:
            subprocess.run(["/bin/launchctl", "bootstrap", "gui/" + str(os.getuid()), str(PLIST)], check=True, capture_output=True)
            return {"ok": True, "message": "Az indítás megtörtént. Pár másodperc múlva ellenőrizd az állapotot."}
    if action == "stop":
        subprocess.run(["/bin/launchctl", "bootout", "gui/" + str(os.getuid()) + "/hu.reszvenyai.ollama"], check=True, capture_output=True)
        return {"ok": True, "message": "A helyi AI-szolgáltatás leállítva. Újraindításig nem használ memóriát a modellhez."}
    if action == "analyze":
        symbol = str(request.get("symbol", "")).strip().upper()
        news = str(request.get("news", "")).strip()
        if not re.fullmatch(r"[A-Z0-9._/-]{1,30}", symbol):
            raise ValueError("Adj meg egy érvényes eszközazonosítót, például BTC-USD vagy egy részvény jelét.")
        if not news or len(news) > 12000:
            raise ValueError("A hírszöveg hossza 1–12 000 karakter lehet.")
        telemetry = {}
        start = time.perf_counter()
        annotation = local_analysis(MODEL, symbol, news, telemetry, hungarian=True)
        elapsed = time.perf_counter() - start
        save_annotation(symbol, news, annotation, elapsed, telemetry)
        labels = {"positive": "Pozitív", "negative": "Negatív", "uncertain": "Bizonytalan"}
        return {"ok": True, "message": "Az elemzés elkészült és helyben mentve.", "result": annotation,
                "display": labels[annotation["impact"]] + " hatás\nÚj esemény: " + ("igen" if annotation["novel"] else "nem igazolt") + "\n\n" + annotation["evidence"],
                "elapsed_seconds": round(elapsed, 2), "telemetry": telemetry}
    if action not in ("demo", "evaluate"):
        raise ValueError("Ismeretlen művelet")
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    if action == "demo":
        report = run(Path(__file__).with_name("demo.json"), reports / "local-ai-demo.json", MODEL)
        failures = sum(d["decision"] == "AI_ERROR" for d in report["decisions"])
        return {"ok": failures == 0, "message": "A kitalált adatokon végzett szimuláció elkészült.",
                "display": "\n".join(str(d["id"]) + ": " + d["decision"] + " — " + d["reason"] for d in report["decisions"]),
                "report": str(reports / "local-ai-demo.json"), "ai_errors": failures}
    if action == "evaluate":
        report = evaluate([MODEL], reports / "model-evaluation.json")
        scores = report["summary"][MODEL]
        times = [r["elapsed_seconds"] for r in report["results"]]
        return {"ok": True, "message": "A tíz kitalált hírhelyzet vizsgálata elkészült.",
                "display": str(scores["passed"]) + "/" + str(scores["total"]) + " egyező eredmény\nMedián válaszidő: " + str(round(statistics.median(times), 2)) + " s\n\n" + "\n".join(r["case"] + ": " + ("egyezik" if r["passed"] else "eltérés / hiba") for r in report["results"]),
                "report": str(reports / "model-evaluation.json")}
    raise ValueError("Ismeretlen művelet")


if __name__ == "__main__":
    try:
        result = dispatch(json.loads(sys.stdin.read()))
    except Exception as exc:
        result = {"ok": False, "message": "A művelet nem sikerült: " + str(exc)}
    print(json.dumps(result, ensure_ascii=False))
