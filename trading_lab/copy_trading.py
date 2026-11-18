"""Proportional position following with an atomic, persistent PAPER ledger only.

No signing, credentials, broker submission or live execution is implemented here.
"""
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN

from agent import number, stamp


@dataclass(frozen=True)
class CopyLimits:
    max_position_fraction: Decimal = Decimal("0.50")
    max_gross_fraction: Decimal = Decimal("1.00")
    max_snapshot_age_seconds: int = 30
    max_quote_age_seconds: int = 10
    max_spread_fraction: Decimal = Decimal("0.005")
    max_reference_deviation: Decimal = Decimal("0.01")
    fee_fraction: Decimal = Decimal("0.0005")
    slippage_fraction: Decimal = Decimal("0.0005")


def limits_from_settings(settings):
    allowed = {"max_position_percent", "max_gross_percent"}
    if not isinstance(settings, dict) or set(settings) != allowed:
        raise ValueError("Csak a pozíciónkénti és az összesített virtuális kitettség módosítható.")
    position, gross = number(settings["max_position_percent"]), number(settings["max_gross_percent"])
    if not (0 < position <= gross <= 100):
        raise ValueError("A pozíciókorlát legyen pozitív, legfeljebb az összkorlát; az összkorlát maximum 100%.")
    return CopyLimits(max_position_fraction=position / 100, max_gross_fraction=gross / 100)


def empty_book(capital="10000"):
    amount = number(capital)
    if amount <= 0:
        raise ValueError("A virtuális keretnek pozitívnak kell lennie.")
    return {"settled": str(amount), "positions": {}, "last_source_at": None, "leader": None, "currency": None, "scope": None}


def paper_equity(book, quotes):
    value = number(book["settled"])
    for instrument, position in book["positions"].items():
        quote = quotes[instrument]
        mid = (number(quote["bid"]) + number(quote["ask"])) / 2
        value += number(position["quantity"]) * (mid - number(position["entry"]))
    return value


def plan_copy(snapshot, book, quotes, instruments, now, limits=None, size="1"):
    """size: the owner's copy size, 1 = the leader's exposure in proportion to capital (0.25-2)."""
    limits = limits or CopyLimits()
    size = number(size)
    if not number("0.25") <= size <= 2:
        raise ValueError("A másolási méret 25% és 200% között lehet.")
    now = stamp(now) if isinstance(now, str) else now
    if snapshot.get("source_class") != "direct_positions":
        raise ValueError("Késleltetett jelentésből nem készül pontos másolási megbízás.")
    if snapshot.get("complete") is not True:
        raise ValueError("Hiányos pozíciólista alapján nem zárunk vagy nyitunk.")
    if not isinstance(snapshot.get("leader"), str) or not snapshot["leader"]:
        raise ValueError("Nincs azonosított követett kereskedő.")
    if book["leader"] and snapshot["leader"] != book["leader"]:
        raise ValueError("Másik kereskedőhöz külön másolási számla kell.")
    if book["currency"] and snapshot.get("currency") != book["currency"]:
        raise ValueError("A másolási számla elszámolási devizája nem változtatható meg.")
    if not isinstance(snapshot.get("scope"), str) or not snapshot["scope"]:
        raise ValueError("A pozíciólista piaci hatóköre nincs megadva.")
    if book["scope"] and snapshot["scope"] != book["scope"]:
        raise ValueError("Másik piaci hatókörhöz külön másolási számla kell.")
    source_time = stamp(snapshot["source_at"])
    age = (now - source_time).total_seconds()
    if age < 0 or age > limits.max_snapshot_age_seconds:
        raise ValueError("Elavult vagy jövőbeli kereskedői állapot.")
    if book["last_source_at"] and source_time <= stamp(book["last_source_at"]):
        raise ValueError("Korábbi vagy már feldolgozott kereskedői állapot.")
    leader_equity = number(snapshot["equity"])
    if leader_equity <= 0:
        raise ValueError("A követett számla tőkéje nem pozitív.")
    positions = snapshot["positions"]
    if not isinstance(positions, dict):
        raise ValueError("Hibás pozíciólista.")
    instrument_ids = set(positions) | set(book["positions"])
    for instrument in instrument_ids:
        if instrument not in instruments or instrument not in quotes:
            raise ValueError("Hiányzó termékazonosítás vagy ár: " + instrument)
        specification = instruments[instrument]
        if specification.get("currency") != snapshot.get("currency"):
            raise ValueError("Eltérő elszámolási deviza; nincs automatikus átváltás.")
        quote = quotes[instrument]
        bid, ask = number(quote["bid"]), number(quote["ask"])
        if bid <= 0 or ask < bid:
            raise ValueError("Hibás vételi/eladási ár.")
        quote_age = (now - stamp(quote["at"])).total_seconds()
        if quote_age < 0 or quote_age > limits.max_quote_age_seconds:
            raise ValueError("Elavult árfolyam: " + instrument)
        if number(specification["step"]) <= 0:
            raise ValueError("Hibás mennyiségi lépésköz.")
    equity = paper_equity(book, quotes)
    if equity <= 0:
        raise ValueError("A virtuális követői tőke nem pozitív.")
    scale = equity / leader_equity * size
    orders, gross, increases = [], Decimal(0), False
    increasing_instruments = set()
    reasons = []
    targets = {}
    for instrument in sorted(instrument_ids):
        specification, quote = instruments[instrument], quotes[instrument]
        source_position = positions.get(instrument, {"quantity": "0"})
        source_qty = number(source_position["quantity"])
        step = number(specification["step"])
        target = (source_qty * scale / step).quantize(Decimal(1), rounding=ROUND_DOWN) * step
        current = number(book["positions"].get(instrument, {}).get("quantity", "0"))
        bid, ask = number(quote["bid"]), number(quote["ask"])
        mid = (bid + ask) / 2
        targets[instrument] = str(target)
        gross += abs(target) * mid
        increasing = abs(target) > abs(current) or target * current < 0
        increases = increases or increasing
        if increasing:
            increasing_instruments.add(instrument)
        if specification.get("kind") not in ("perpetual", "cash_equity", "spot"):
            reasons.append("Nem támogatott termékfajta: " + instrument)
        if target < 0 and specification.get("kind") != "perpetual":
            reasons.append("Shortolás ehhez a termékhez nincs bekapcsolva: " + instrument)
        if increasing and abs(target) * mid > equity * limits.max_position_fraction:
            reasons.append("Pozíciónkénti korlát: " + instrument)
        if increasing and (ask - bid) / bid > limits.max_spread_fraction:
            reasons.append("Túl nagy vételi/eladási árkülönbség: " + instrument)
        if increasing and source_qty:
            reference = number(source_position["reference_price"])
            if reference <= 0 or abs(mid / reference - 1) > limits.max_reference_deviation:
                reasons.append("Túl nagy eltérés a forrás referenciaárától: " + instrument)
        delta = target - current
        if not delta:
            continue
        side = "buy" if delta > 0 else "sell"
        price = (ask if side == "buy" else bid) * (1 + limits.slippage_fraction if side == "buy" else 1 - limits.slippage_fraction)
        if current == 0:
            transition = "nyitás"
        elif target == 0:
            transition = "teljes zárás"
        elif current * target < 0:
            transition = "irányváltás"
        elif abs(target) > abs(current):
            transition = "ráépítés"
        else:
            transition = "részleges zárás"
        orders.append({"instrument": instrument, "side": side, "delta": str(delta),
                       "target": str(target), "price": str(price), "transition": transition,
                       "fee": str(abs(delta) * price * limits.fee_fraction)})
    if increases and gross > equity * limits.max_gross_fraction:
        reasons.append("Összesített kitettségi korlát; a vezető tőkeáttételét nem másoljuk korlátlanul.")
    if increases and not reasons:
        projected_equity = paper_equity(apply_paper_orders(book, orders), quotes)
        if projected_equity <= 0 or gross > projected_equity * limits.max_gross_fraction:
            reasons.append("A végrehajtási költségekkel együtt túllépett összkitettség.")
        for instrument in increasing_instruments:
            mid = (number(quotes[instrument]["bid"]) + number(quotes[instrument]["ask"])) / 2
            if abs(number(targets[instrument])) * mid > projected_equity * limits.max_position_fraction:
                reasons.append("A végrehajtási költségekkel együtt túllépett pozíciókorlát: " + instrument)
    return {"status": "BLOCKED" if reasons else "READY", "reasons": reasons,
            "orders": [] if reasons else orders, "targets": targets, "scale": str(scale),
            "equity_before": str(equity), "notice": "PAPER_ONLY; quantity rounding and execution costs cause tracking differences."}


def apply_paper_orders(book, orders):
    # A derivative-style marked-to-market simulator, not a brokerage settlement ledger.
    updated = json.loads(json.dumps(book))
    settled = number(updated["settled"])
    for order in orders:
        instrument = order["instrument"]
        old = updated["positions"].get(instrument, {"quantity": "0", "entry": "0"})
        old_qty, old_entry = number(old["quantity"]), number(old["entry"])
        delta, price = number(order["delta"]), number(order["price"])
        target = old_qty + delta
        if old_qty * delta < 0:
            closed = min(abs(old_qty), abs(delta))
            settled += closed * (price - old_entry) * (1 if old_qty > 0 else -1)
        settled -= number(order["fee"])
        if target == 0:
            updated["positions"].pop(instrument, None)
            continue
        if old_qty == 0 or target * old_qty < 0:
            entry = price
        elif delta * old_qty > 0:
            entry = (abs(old_qty) * old_entry + abs(delta) * price) / abs(target)
        else:
            entry = old_entry
        updated["positions"][instrument] = {"quantity": str(target), "entry": str(entry)}
    updated["settled"] = str(settled)
    return updated


class PaperCopyLedger:
    def __init__(self, path=":memory:", capital="10000"):
        self.connection = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self.connection.execute("CREATE TABLE IF NOT EXISTS book (id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS snapshots (leader TEXT, event_id TEXT, result TEXT, PRIMARY KEY(leader,event_id))")
        self.connection.execute("INSERT OR IGNORE INTO book VALUES (1,?)", (json.dumps(empty_book(capital)),))

    def book(self):
        return json.loads(self.connection.execute("SELECT payload FROM book WHERE id=1").fetchone()[0])

    def follow(self, snapshot, quotes, instruments, now, limits=None, size="1"):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            identity = snapshot["leader"], snapshot["id"]
            if not all(isinstance(x, str) and x for x in identity):
                raise ValueError("Hiányzó eseményazonosító.")
            exists = self.connection.execute("SELECT 1 FROM snapshots WHERE leader=? AND event_id=?", identity).fetchone()
            if exists:
                self.connection.execute("ROLLBACK")
                return {"status": "DUPLICATE", "orders": [], "reasons": ["Már feldolgozott esemény."]}
            book = self.book()
            try:
                plan = plan_copy(snapshot, book, quotes, instruments, now, limits, size)
            except (KeyError, TypeError, ValueError) as exc:
                plan = {"status": "BLOCKED", "orders": [], "reasons": [str(exc)]}
            if plan["status"] == "READY":
                updated = apply_paper_orders(book, plan["orders"])
                updated["last_source_at"] = snapshot["source_at"]
                updated["leader"] = snapshot["leader"]
                updated["currency"] = snapshot["currency"]
                updated["scope"] = snapshot["scope"]
                self.connection.execute("UPDATE book SET payload=? WHERE id=1", (json.dumps(updated),))
            self.connection.execute("INSERT INTO snapshots VALUES (?,?,?)", (*identity, json.dumps(plan)))
            self.connection.execute("COMMIT")
            return plan
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise

    def close(self):
        self.connection.close()


def demonstration():
    # Fictional trader, fictional quotes, independent virtual ledger on each invocation.
    ledger = PaperCopyLedger()
    instrument = "demo:perpetual:BTC:USDC"
    instruments = {instrument: {"kind": "perpetual", "currency": "USDC", "step": "0.000001"}}
    steps = []
    start = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
    for index, qty in enumerate(("0.1", "0.2", "0.08", "0", "-0.1", "0")):
        now = (start + timedelta(seconds=index)).isoformat()
        snapshot = {"id": "demo-" + str(index), "leader": "FIKTIV_KERESKEDO", "source_class": "direct_positions",
                    "source_at": now, "equity": "100000", "currency": "USDC", "complete": True, "scope": "demo:perpetual",
                    "positions": {instrument: {"quantity": qty, "reference_price": "60000"}} if number(qty) else {}}
        quotes = {instrument: {"bid": "59999", "ask": "60001", "at": now}}
        plan = ledger.follow(snapshot, quotes, instruments, now)
        steps.append({"leader_quantity": qty, **plan})
    final_book = ledger.book()
    ledger.close()
    return {"status": "SYNTHETIC_PAPER_DEMO", "steps": steps, "final_book": final_book,
            "notice": "No real trader, live feed or live order. Funding, liquidations and partial fills are not simulated."}
