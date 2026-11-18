"""Read-only, public Hyperliquid data. No wallet signing or exchange actions."""
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone

from agent import NoRedirect, number


def public_info(payload):
    if payload.get("type") not in ("l2Book", "meta", "clearinghouseState", "metaAndAssetCtxs", "portfolio", "candleSnapshot"):
        raise ValueError("Csak engedélyezett, olvasási adatlekérés használható.")
    request = urllib.request.Request("https://api.hyperliquid.xyz/info",
                                    data=json.dumps(payload).encode(),
                                    headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=15) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("Túl nagy piaci adatválasz.")
    return json.loads(body)


def market_snapshot():
    """Indicative mark prices, never execution quotes; entire main perp universe."""
    raw = public_info({"type": "metaAndAssetCtxs"})
    universe, contexts = raw[0]["universe"], raw[1]
    if len(universe) != len(contexts):
        raise ValueError("Hiányos piaci árfolyamlista.")
    rows = []
    for instrument, context in zip(universe, contexts):
        if instrument.get("isDelisted"):
            continue
        try:
            price, previous = number(context["markPx"]), number(context["prevDayPx"])
            volume = number(context["dayNtlVlm"])
            if price <= 0 or previous <= 0 or volume < 0:
                continue
            # Funding is per hour on Hyperliquid; open interest is in coins, shown in dollars.
            rows.append({"symbol": instrument["name"], "price": str(price),
                         "change_percent": str((price / previous - 1) * 100), "volume": str(volume),
                         "funding": str(number(context.get("funding") or 0)),
                         "open_interest": str(number(context.get("openInterest") or 0) * price),
                         "max_leverage": int(instrument.get("maxLeverage") or 3)})
        except (KeyError, ValueError):
            continue
    if not rows:
        raise ValueError("Nem érkezett használható árfolyam.")
    rows.sort(key=lambda row: number(row["volume"]), reverse=True)
    return {"updated_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
            "source": "Hyperliquid main perpetual mark prices", "error": None}


def timestamp_millis(value):
    return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat()


def public_quote(coin="BTC"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,29}", coin):
        raise ValueError("Ebben a kapcsolatban a fő perpetual piacok azonosítói használhatók.")
    data = public_info({"type": "l2Book", "coin": coin})
    if data.get("coin") != coin or len(data.get("levels", [])) != 2:
        raise ValueError("Hibás vagy másik piacról érkezett árfolyam.")
    bid = number(data["levels"][0][0]["px"])
    ask = number(data["levels"][1][0]["px"])
    if bid <= 0 or ask < bid:
        raise ValueError("Hibás vételi/eladási ár.")
    return {"bid": str(bid), "ask": str(ask), "at": timestamp_millis(data["time"]),
            "instrument": "hyperliquid:default:perpetual:" + coin + ":USDC"}


def public_trader_snapshot(address):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise ValueError("Érvényes nyilvános számlacím szükséges; privát kulcsot ne adj meg.")
    address = address.lower()
    state = public_info({"type": "clearinghouseState", "user": address})
    equity = number(state["marginSummary"]["accountValue"])
    if equity <= 0:
        raise ValueError("Nincs pozitív tőke ezen a fő perpetual számlán. Ellenőrizd a számlacímet és a piaci hatókört.")
    rows = state["assetPositions"]
    if not isinstance(rows, list):
        raise ValueError("Hibás pozíciólista.")
    if len(rows) > 20:
        raise ValueError("Az első változat legfeljebb húsz pozíciót vizsgál egyszerre.")
    specs = public_info({"type": "meta"})["universe"]
    decimals = {row["name"]: int(row["szDecimals"]) for row in specs}
    positions, quotes = {}, {}
    instruments = {"hyperliquid:default:perpetual:" + coin + ":USDC":
                   {"kind": "perpetual", "currency": "USDC", "step": str(number(10) ** -places)}
                   for coin, places in decimals.items() if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,29}", coin)}
    for row in rows:
        position = row["position"]
        coin, quantity = position["coin"], number(position["szi"])
        if quantity == 0:
            continue
        quote = public_quote(coin)
        identifier = quote.pop("instrument")
        if identifier in positions:
            raise ValueError("Ismétlődő termék a forrásban.")
        value = abs(number(position["positionValue"]))
        if value <= 0:
            raise ValueError("Hiányzó pozícióérték.")
        positions[identifier] = {"quantity": str(quantity), "reference_price": str(value / abs(quantity))}
        if identifier not in instruments:
            raise ValueError("Nem támogatott termék a fő perpetual hatókörben.")
        quotes[identifier] = quote
    source_at = timestamp_millis(state["time"])
    snapshot = {"id": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(),
                "leader": address, "source_class": "direct_positions", "scope": "hyperliquid:perps:default",
                "source_at": source_at, "equity": str(equity), "currency": "USDC", "complete": True,
                "positions": positions}
    return {"snapshot": snapshot, "quotes": quotes, "instruments": instruments,
            "notice": "Only this account's main perpetual venue is covered. Spot, vaults, other accounts and HIP-3 venues are not included. Read-only."}
