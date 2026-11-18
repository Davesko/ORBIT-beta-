"""Decimal valuations for the active paper account. Exposure is never added as cash."""
from agent import number


def value_portfolio(book, prices, price_fresh, gross_limit="100", initial_capital="10000"):
    initial = number(initial_capital)
    if initial <= 0:
        raise ValueError("Hibás induló portfóliókeret.")
    result = {"settled_balance": None, "unrealized_pnl": None, "gross_exposure": None,
              "available_capacity": None, "capacity_deficit": None, "equity": None,
              "change": None, "change_percent": None, "paper_positions": [],
              "position_count": 0, "valuation_complete": False}
    if book is None:
        return result
    settled = number(book["settled"])
    result["settled_balance"] = str(settled)
    gross, pnl, complete, rows = number(0), number(0), True, []
    for identifier, position in book.get("positions", {}).items():
        quantity, entry = number(position["quantity"]), number(position["entry"])
        if quantity == 0:
            continue
        parts = identifier.split(":")
        supported = (len(parts) == 5 and parts[:3] == ["hyperliquid", "default", "perpetual"]
                     and parts[4] == "USDC" and book.get("currency") in (None, "USDC"))
        symbol = parts[-2] if len(parts) >= 2 else identifier
        row = {"instrument": identifier, "symbol": symbol, "quantity": str(quantity), "entry": str(entry),
               "direction": "long" if quantity > 0 else "short",
               "strategy": "fast" if position.get("strategy") in ("fast", "research", "news_ai") else "copy",
               "price": None, "notional": None, "unrealized_pnl": None, "pnl_percent": None,
               "equity_percent": None, "exposure_percent": None, "error": None}
        if not supported:
            row["error"] = "Az eszköz piaci hatóköre nem támogatott."
        elif not price_fresh:
            row["error"] = "Nincs friss árfolyam."
        elif symbol not in prices:
            row["error"] = "Az eszközhöz nem érkezett árfolyam."
        elif entry <= 0 or number(prices[symbol]) <= 0:
            row["error"] = "Hibás belépési vagy aktuális ár."
        else:
            price = number(prices[symbol])
            notional = abs(quantity) * price
            profit = quantity * (price - entry)
            row.update(price=str(price), notional=str(notional), unrealized_pnl=str(profit),
                       pnl_percent=str(profit / (abs(quantity) * entry) * 100))
            gross += notional; pnl += profit
        if row["error"]:
            complete = False
        rows.append(row)
    rows.sort(key=lambda row: (row["notional"] is None, -number(row["notional"] or "0"), row["instrument"]))
    result.update(paper_positions=rows, position_count=len(rows), valuation_complete=complete)
    if complete:
        equity = settled + pnl
        limit = number(gross_limit)
        if not 0 < limit <= 100:
            raise ValueError("Hibás virtuális kitettségi korlát.")
        remaining = equity * limit / 100 - gross
        result.update(equity=str(equity), unrealized_pnl=str(pnl), gross_exposure=str(gross),
                      available_capacity=str(max(number(0), remaining)), capacity_deficit=str(max(number(0), -remaining)),
                      change=str(equity - initial), change_percent=str((equity - initial) / initial * 100))
        for row in rows:
            row["equity_percent"] = str(number(row["notional"]) / equity * 100) if equity > 0 else None
            row["exposure_percent"] = str(number(row["notional"]) / gross * 100) if gross > 0 else None
    return result
