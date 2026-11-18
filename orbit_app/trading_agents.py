"""TradingAgents (TauricResearch, Apache-2.0) as an ORBIT research tool (owner, 12 Nov: "csak építsd be az appba ha hasznos,
projektbe ne használd").

A team of LLM agents (market, news and fundamentals analysts, a bull/bear debate, a trader and risk managers) reads public
market data and writes a research report that ends in a BUY / HOLD / SELL style view. Here it is research only:
  * it runs on ORBIT's own local models (the Ollama server ORBIT already uses), never a cloud model or key;
  * public data only (Yahoo Finance); SEC EDGAR is left out because it asks for a personal contact address;
  * no order is ever placed and no broker is connected; the report is saved under Application Support/Orbit/trading-agents
    and is not handed to any project (MiLLIONS included) unless the owner does that himself.
The package lives in its own virtual environment (tools/tradingagents), pinned to a release, so it cannot disturb ORBIT.
"""
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

VERSION = 'v0.7.1'
SOURCE = f'git+https://github.com/TauricResearch/TradingAgents@{VERSION}'
TICKER = re.compile(r'^[A-Z0-9][A-Z0-9.\-^=]{0,14}$')
DISCLAIMER = ('Kutatási eszköz, nem befektetési tanács. Az ORBIT nem köt üzletet és nem kapcsolódik brókerhez; '
              'a döntés a tiéd.')


def home(root):
    return Path(root) / 'trading-agents'


def venv(root):
    return Path(root) / 'tools' / 'tradingagents'


def python(root):
    return venv(root) / 'bin' / 'python3'


def status(s):
    root = s.root
    reports = sorted(home(root).glob('reports/*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:12]
    items = []
    for p in reports:
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            items.append(dict(id=p.stem, ticker=d.get('ticker'), date=d.get('date'), decision=d.get('decision'), created=d.get('created'),
                              models=d.get('models')))
        except (OSError, ValueError):
            continue
    running = [dict(r) for r in s.rows("SELECT id,status,json_extract(payload,'$.task') task,json_extract(payload,'$.ticker') ticker FROM jobs "
                                       "WHERE kind='assist' AND status IN ('queued','running') AND json_extract(payload,'$.task') LIKE 'trading_agents%'")]
    return dict(installed=python(root).is_file() and (venv(root) / 'orbit-installed.json').is_file(), version=VERSION, reports=items,
                running=running, disclaimer=DISCLAIMER)


def runtime_python():
    """A Python 3.11+ for the virtual environment: the media runtime's interpreter (3.12)."""
    import connections
    candidate = Path(connections.ROOT) / 'media-runtime' / 'bin' / 'python3'
    return candidate if candidate.is_file() else Path(sys.executable)


def install(s, job=None):
    root = s.root
    target = venv(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if job:
        s.job_stage(job['id'], 'install', 'Külön Python-környezet létrehozása')
    if not python(root).is_file():
        subprocess.run([str(runtime_python()), '-m', 'venv', str(target)], check=True, capture_output=True, timeout=300)
    if job:
        s.job_stage(job['id'], 'install', f'TradingAgents {VERSION} telepítése (pip)')
    done = subprocess.run([str(python(root)), '-m', 'pip', 'install', '--disable-pip-version-check', '-q', SOURCE],
                          capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise ValueError('A TradingAgents telepítése nem sikerült: ' + done.stderr[-500:])
    (target / 'orbit-installed.json').write_text(json.dumps(dict(version=VERSION, at=time.time())))
    return f'A TradingAgents {VERSION} telepítve, külön környezetben.'


def models():
    """Quick and deep local models: the small fast chat model for analysts, the largest text model for the managers."""
    import model_hub
    names = [m.get('name', '') for m in model_hub.models() if isinstance(m, dict)]
    text = [n for n in names if not re.search(r'embed|vl|vision|coder', n)]
    # "qwen3.8:27b" contains "7b": the size is the number right after the colon or dash.
    quick = next((n for n in text if re.search(r'[:\-_](?:4|7|8|9)b\b', n)), text[0] if text else None)
    # One model for both tiers: ORBIT's model server keeps one model loaded, and swapping a 9B and a 27B model at every
    # agent step made the first NVDA run spend most of its time reloading (12 Nov).
    deep = quick
    if not quick:
        raise ValueError('Nincs telepített helyi szöveges modell a TradingAgents futtatásához.')
    return quick, deep


def port():
    import model_hub
    return 11435 if model_hub.online() else 11434


def enqueue(s, ticker, date=None):
    ticker = str(ticker or '').strip().upper()
    if not TICKER.fullmatch(ticker):
        raise ValueError('Adj meg egy tőzsdei jelet, például NVDA, AAPL vagy OTP.BD.')
    date = date or datetime.date.today().isoformat()
    datetime.date.fromisoformat(date)
    if not status(s)['installed']:
        raise ValueError('Előbb telepítsd a TradingAgents eszközt.')
    agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
    return s.enqueue(agent[0], 'TradingAgents-elemzés · ' + ticker, 'assist', payload=dict(task='trading_agents_run', ticker=ticker, date=date, local_only=True))


RUNNER = r'''
import json, os, sys
request = json.loads(sys.argv[1])
os.environ.setdefault('TRADINGAGENTS_HOME', request['home'])
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
config = DEFAULT_CONFIG.copy()
config.update(llm_provider='ollama', backend_url=request['url'], quick_think_llm=request['quick'], deep_think_llm=request['deep'],
              max_debate_rounds=1, max_risk_discuss_rounds=1, output_language='English',
              # A local 9B model: fewer tool rounds and articles, or one ticker took over an hour (12 Nov).
              max_tool_rounds=6, news_article_limit=8, global_news_article_limit=5,
              results_dir=os.path.join(request['home'], 'logs'), data_cache_dir=os.path.join(request['home'], 'cache'),
              memory_log_path=os.path.join(request['home'], 'memory', 'trading_memory.md'))
config['data_vendors'] = dict(config['data_vendors'], fundamental_data='yfinance')
ta = TradingAgentsGraph(selected_analysts=['market', 'news', 'fundamentals'], debug=False, config=config)
state, decision = ta.propagate(request['ticker'], request['date'])
keys = ('market_report', 'news_report', 'fundamentals_report', 'investment_plan', 'trader_investment_plan', 'final_trade_decision')
print(json.dumps(dict(decision=str(decision), sections={k: str(state.get(k) or '') for k in keys})))
'''


def run(s, job):
    payload = json.loads(job['payload'])
    root = s.root
    quick, deep = models()
    folder = home(root)
    (folder / 'reports').mkdir(parents=True, exist_ok=True)
    s.job_stage(job['id'], 'research', f"Elemzőcsapat: {payload['ticker']} · {quick} / {deep}")
    request = dict(ticker=payload['ticker'], date=payload['date'], quick=quick, deep=deep, home=str(folder), url=f'http://127.0.0.1:{port()}/v1')
    done = subprocess.run([str(python(root)), '-I', '-c', RUNNER, json.dumps(request)], capture_output=True, text=True, timeout=3 * 3600,
                          cwd=str(folder))
    if done.returncode:
        raise ValueError('A TradingAgents futása hibát adott: ' + done.stderr[-600:])
    result = json.loads(done.stdout.strip().splitlines()[-1])
    stamp = time.strftime('%Y%m%d-%H%M%S')
    report = dict(ticker=payload['ticker'], date=payload['date'], decision=result['decision'][:400], sections=result['sections'],
                  models=dict(quick=quick, deep=deep), created=time.time(), disclaimer=DISCLAIMER, source=f'TradingAgents {VERSION}')
    path = folder / 'reports' / f"{payload['ticker']}-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return f"TradingAgents · {payload['ticker']}: {report['decision'][:160]} (kutatás, nem tanács)"


def report(s, rid):
    if not re.fullmatch(r'[A-Z0-9.\-^=]+-\d{8}-\d{6}', str(rid or '')):
        raise ValueError('Ismeretlen jelentés.')
    return json.loads((home(s.root) / 'reports' / f'{rid}.json').read_text(encoding='utf-8'))


def dispatch(s, op, args=None):
    args = args or {}
    if op == 'trading_agents_status':
        return status(s)
    if op == 'trading_agents_install':
        agent = s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()
        return s.enqueue(agent[0], 'TradingAgents telepítése', 'assist', payload=dict(task='trading_agents_install', local_only=True))
    if op == 'trading_agents_run':
        return enqueue(s, args.get('ticker'), args.get('date'))
    if op == 'trading_agents_report':
        return report(s, args.get('id'))
    raise ValueError('Ismeretlen TradingAgents-művelet.')
