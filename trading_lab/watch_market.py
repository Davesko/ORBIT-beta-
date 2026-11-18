"""Independent market, feed, inference and discovery loops. Read-only/paper support."""
import json
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from market_data import market_snapshot
from continuous_data import NewsStore, atomic_json, discover_traders, utcnow
import news_sources

ROOT = Path.home() / "Library/Application Support/ReszvenyAI"


def repeated(stop, seconds, path, operation):
    last = {}
    while not stop.is_set():
        try:
            last = operation()
        except Exception as exc:
            last = dict(last, error=str(exc), attempted_at=utcnow().isoformat())
        atomic_json(path, last)
        stop.wait(seconds)


def keep_ranking(path):
    """While a new search runs, the last finished ranking stays visible until the new one is at least as long."""
    try: previous = json.loads(path.read_text()).get("candidates") or []
    except (OSError, ValueError): previous = []
    def progress(result):
        if result["searching"] and len(result["candidates"]) < len(previous):
            result = dict(result, candidates=previous)
        atomic_json(path, result)
    return progress


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    reports = ROOT / "reports"
    database = ROOT / "data/automatic-news.sqlite"
    recovery = NewsStore(database)
    with recovery.db:
        recovery.db.execute("UPDATE news SET status='pending' WHERE status='analyzing'")
    recovery.close()
    memory = {}
    def collect():
        # Each source has its own pace (X news accounts every 30 s); the loop only checks which are due.
        store = NewsStore(database)
        try:
            try: universe = [row["symbol"] for row in json.loads((reports / "market-state.json").read_text())["rows"]]
            except (OSError, ValueError, KeyError): universe = []
            return news_sources.collect(ROOT, store, memory, universe)
        finally: store.close()
    def infer():
        store = NewsStore(database)
        try: return store.analyze_one()
        finally: store.close()
    def inference_loop():
        while not stop.is_set():
            try: worked = infer()
            except Exception: worked = False
            stop.wait(2 if worked else 10)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(repeated, stop, 3, reports / "market-state.json", market_snapshot),
                 pool.submit(repeated, stop, 10, reports / "news-state.json", collect),
                 pool.submit(repeated, stop, 3600, reports / "trader-candidates.json", lambda: discover_traders(stop, keep_ranking(reports / "trader-candidates.json"))),
                 pool.submit(inference_loop)]
        # Propagate an unexpected thread failure instead of silently losing a feed.
        while not stop.wait(1):
            if any(task.done() for task in tasks):
                stop.set()
                for task in tasks:
                    if task.done(): task.result()


if __name__ == "__main__":
    main()
