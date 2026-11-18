"""Quiver read-only API adapter; disclosures are signals, not exact real-time fills."""
import json
import os
import urllib.request
from datetime import date, datetime, timezone

from agent import NoRedirect, number


def normalize_congress_record(row):
    traded, reported = str(row["TransactionDate"]), str(row["ReportDate"])
    # Preserve date precision; never invent an intraday publication timestamp.
    lag = (date.fromisoformat(reported[:10]) - date.fromisoformat(traded[:10])).days
    if lag < 0:
        raise ValueError("A jelentés megelőzi az ügylet dátumát.")
    return {"source": "quiver", "source_class": "disclosure", "exact_copy_eligible": False,
            "trader": row.get("Representative"), "ticker": row.get("Ticker"),
            "reported_instrument_type": row.get("TickerType", "unknown"),
            "transaction": row.get("Transaction"), "transaction_date": traded,
            "report_date": reported, "disclosure_lag_days": lag,
            "reported_amount_lower_bound_usd": str(number(row.get("Amount", "0"))),
            "reported_amount_range": row.get("Range"), "exact_quantity": None,
            "first_seen_at": datetime.now(timezone.utc).isoformat(),
            "notice": "Reported amount is a range/lower bound, not an exact order size or current account weight."}


def recent_congress(api_key=None):
    key = api_key or os.environ.get("QUIVER_API_KEY")
    if not key:
        raise ValueError("A Quiverhez saját API-hozzáférés szükséges. Kulcsot ne írj a beszélgetésbe.")
    request = urllib.request.Request("https://api.quiverquant.com/beta/live/congresstrading",
                                    headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=15) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("Túl nagy Quiver-adatválasz.")
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("Hibás Quiver-adatválasz.")
    # Schema errors stop processing instead of creating guessed trade instructions.
    return [normalize_congress_record(row) for row in rows]
