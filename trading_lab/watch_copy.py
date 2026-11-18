"""Continuous public-account observation and PAPER position following only."""
import json
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path

from copy_trading import PaperCopyLedger, apply_paper_orders, paper_equity, limits_from_settings
from market_data import public_trader_snapshot, public_quote
from account import database_path
from agent import number, stamp
from continuous_data import atomic_json
from fast_ai import close_orders


ROOT = Path.home() / "Library/Application Support/ReszvenyAI"
# Following the best trader: the ranking is checked every 10 minutes; a switch needs a clearly better score
# (1.3x) after a day of following, or the followed trader dropping out of the qualified list for 6 hours.
CHECK_EVERY = 600
BETTER = 1.3
MIN_HOLD = 24 * 3600
DROPPED_HOLD = 6 * 3600


def best_switch(config, now, root=ROOT):
    """The candidate to switch to, or None."""
    try:
        report = json.loads((root / "reports/trader-candidates.json").read_text())
    except (OSError, ValueError):
        return None
    ranked = sorted(report.get("candidates") or [], key=lambda c: -float(c["score"]))
    if not ranked or (now - stamp(report["updated_at"])).total_seconds() > 7200:
        return None
    best, address = ranked[0], config["address"]
    if best["address"] == address:
        return None
    held = (now - stamp(config.get("since") or now.isoformat())).total_seconds()
    current = next((c for c in ranked if c["address"] == address), None)
    if current is None and held >= DROPPED_HOLD:
        return best
    if current is not None and held >= MIN_HOLD and float(best["score"]) >= BETTER * float(current["score"]):
        return best
    return None


def switch_leader(ledger, config, best, now, quote=public_quote, root=ROOT):
    """Close the virtual positions at fresh prices and follow the better trader from a flat book."""
    ledger.connection.execute("BEGIN IMMEDIATE")
    try:
        book = ledger.book(); quotes = {}
        for identifier in book["positions"]:
            fresh = quote(identifier.split(":")[3]); fresh.pop("instrument", None); quotes[identifier] = fresh
        orders = close_orders(book, quotes, now) if book["positions"] else []
        updated = apply_paper_orders(book, orders) if orders else book
        updated.update(leader=None, scope=None, currency=None, last_source_at=None)
        ledger.connection.execute("UPDATE book SET payload=? WHERE id=1", (json.dumps(updated),))
        ledger.connection.execute("COMMIT")
    except Exception:
        if ledger.connection.in_transaction:
            ledger.connection.execute("ROLLBACK")
        raise
    switched = dict(config, address=best["address"], since=now.isoformat(), previous=config["address"])
    atomic_json(root / "paper-copy-config.json", switched)
    account = root / "portfolio-account.json"
    if account.exists():
        atomic_json(account, dict(json.loads(account.read_text()), leader=best["address"]))
    return switched, orders


def cycle(address, ledger, limits=None, size="1"):
    incoming = public_trader_snapshot(address)
    for identifier in ledger.book()["positions"]:
        if identifier not in incoming["quotes"]:
            parts = identifier.split(":")
            if len(parts) != 5 or parts[:3] != ["hyperliquid", "default", "perpetual"] or parts[4] != "USDC":
                raise ValueError("A meglévő pozíció nem ebbe a piaci hatókörbe tartozik.")
            quote = public_quote(parts[3])
            quote.pop("instrument")
            incoming["quotes"][identifier] = quote
    now = datetime.now(timezone.utc).isoformat()
    plan = ledger.follow(incoming["snapshot"], incoming["quotes"], incoming["instruments"], now, limits, size)
    book = ledger.book()
    return {"mode": "PAPER_ONLY", "leader": address, "updated_at": now, "plan": plan,
            "book": book, "marked_equity": str(paper_equity(book, incoming["quotes"])),
            "scope": "Main Hyperliquid perpetual venue only; not the trader's full wealth.",
            "notice": "No orders are submitted. Fees/slippage simulated; funding, liquidation and partial fills are not."}


def main():
    config = json.loads((ROOT / "paper-copy-config.json").read_text())
    address = config["address"]; checked = 0; switch_note = None
    output = ROOT / "reports/paper-copy-state.json"
    database = database_path(ROOT, config.get("database", "paper-copy-" + address.lower() + ".sqlite"))
    ledger = PaperCopyLedger(database, capital="10000")
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    try:
        while not stopped.is_set():
            try:
                settings = ROOT / "paper-risk.json"
                limits = limits_from_settings(json.loads(settings.read_text())) if settings.exists() else None
                now = datetime.now(timezone.utc)
                if config.get("auto_best") and now.timestamp() - checked >= CHECK_EVERY:
                    checked = now.timestamp(); best = best_switch(config, now)
                    if best:
                        config, closed = switch_leader(ledger, config, best, now); address = config["address"]
                        switch_note = {"at": now.isoformat(), "to": address, "name": best["name"], "score": best["score"], "closed_orders": len(closed),
                                       "message": "Váltás jobb kereskedőre: " + best["name"] + " (pontszám " + str(round(float(best["score"]), 2)) + ")"}
                size = str(number(str(config.get("size_percent", 100))) / 100)
                result = cycle(address, ledger, limits, size)
                result.update(auto_best=bool(config.get("auto_best")), since=config.get("since"), last_switch=switch_note,
                              size_percent=config.get("size_percent", 100))
            except Exception as exc:
                result = {"mode": "PAPER_ONLY", "leader": address, "error": str(exc),
                          "updated_at": datetime.now(timezone.utc).isoformat(),
                          "notice": "No new simulated order was generated from the failed data request."}
            temporary = output.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(output)
            stopped.wait(5)
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
