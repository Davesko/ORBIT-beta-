"""Bounded public data readers and durable automatic news analysis. No orders/tools."""
import hashlib
import html
import json
import re
import sqlite3
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from agent import NoRedirect, local_analysis, number
from market_data import public_info

FEEDS = {
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "ECB": "https://www.ecb.europa.eu/rss/press.html",
    "SEC": "https://www.sec.gov/news/pressreleases.rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
}
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"


def utcnow():
    return datetime.now(timezone.utc)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False) + "\n")
    temporary.replace(path)


def fetch_bytes(url, maximum=2_000_000, allowed=()):
    """Only the configured sources (news-sources.json, validated there) and the fixed public endpoints."""
    if url not in set(FEEDS.values()) | {LEADERBOARD} | set(allowed):
        raise ValueError("Csak az ellenőrzött adatforrások kérdezhetők le.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "MiLLIONS/0.5 personal research news reader"})
    with opener.open(request, timeout=25) as response:
        body = response.read(maximum + 1)
    if len(body) > maximum:
        raise ValueError("Az adatforrás túllépte a méretkorlátot.")
    return body


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def plain(value):
    parser = VisibleText(); parser.feed(value or "")
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


# Coins named in words; $CASHTAGS of any listed coin are matched separately.
ASSET_NAMES = (
    ("BTC", r"\b(bitcoin|btc)\b"), ("ETH", r"\b(ethereum|ether|eth)\b"), ("SOL", r"\b(solana|sol)\b"),
    ("HYPE", r"\b(hyperliquid|hype)\b"), ("DOGE", r"\b(dogecoin|doge)\b"), ("PUMP", r"\bpump\.fun\b|\bpump (token|coin)\b|\$pump\b"),
    ("kPEPE", r"\bpepe\b"), ("kBONK", r"\bbonk\b"), ("kSHIB", r"\b(shiba inu|shib)\b"), ("WIF", r"\b(dogwifhat|wif)\b"),
    ("XRP", r"\b(xrp|ripple)\b"), ("BNB", r"\b(bnb|binance coin)\b"), ("ADA", r"\b(cardano|ada)\b"), ("AVAX", r"\b(avalanche|avax)\b"),
    ("LINK", r"\bchainlink\b"), ("LTC", r"\b(litecoin|ltc)\b"), ("TRX", r"\b(tron|trx)\b"), ("TON", r"\btoncoin\b"),
    ("SUI", r"\bsui\b"), ("APT", r"\baptos\b"), ("ARB", r"\barbitrum\b"), ("OP", r"\boptimism\b"), ("NEAR", r"\bnear protocol\b"),
    ("ZEC", r"\b(zcash|zec)\b"), ("XMR", r"\b(monero|xmr)\b"), ("ENA", r"\bethena\b"), ("AAVE", r"\baave\b"), ("UNI", r"\buniswap\b"),
    ("WLD", r"\bworldcoin\b"), ("TRUMP", r"\btrump (coin|token|memecoin)\b"), ("FARTCOIN", r"\bfartcoin\b"), ("TIA", r"\bcelestia\b"),
    ("INJ", r"\binjective\b"), ("DOT", r"\bpolkadot\b"), ("BCH", r"\bbitcoin cash\b"), ("ONDO", r"\bondo\b"), ("PENGU", r"\bpudgy penguins?\b"))
# Market-wide: central banks, macro data, ETF flows and exchange-level failures move every coin.
MACRO = re.compile(r"\b(fed|fomc|federal reserve|rate (cut|hike)s?|interest rates?|inflation|cpi|pce|payrolls|jobs report|unemployment|tariffs?|"
                   r"recession|treasury yields?|powell|etf (inflows?|outflows?)|stablecoin (bill|law))\b|"
                   r"\b(binance|coinbase|okx|bybit|kraken|exchange)\b.{0,80}\b(hack|hacked|exploit|withdrawals?|insolven\w*|halt\w*|outage)", re.I)
OFFICIAL = re.compile(r"\b(rate|rates|inflation|monetary|fomc|economic|securities|crypto|bitcoin|etf|exchange|regulation|liquidity|employment)\b", re.I)
POSITIVE = re.compile(r"\b(approv(e|es|ed|al)|inflows?|partner(s|ship|ed)?|integrat(e|es|ed|ion)|launch(es|ed)?|will list|lists|listed|listing|"
                      r"adds? support|record high|all[- ]time high|ath|surg(e|es|ed|ing)|soar(s|ed|ing)?|rall(y|ies|ied)|breaks? above|"
                      r"buybacks?|upgrade[sd]?|mainnet|acquir(e|es|ed|ing)|acquisition|invest(s|ed|ment)|adopt(s|ed|ion)?|legal tender|"
                      r"strategic reserve|accumulat(e|es|ed|ing)|bought|buys|resum(e|es|ed)|reopen(s|ed)?|recover(s|ed|y)?|dismiss(es|ed)|"
                      r"bullish|ris(e|es|ing)|jump(s|ed)?|gain(s|ed)?|wins?)\b", re.I)
NEGATIVE = re.compile(r"\b(hack(s|ed|er|ers)?|exploit(s|ed)?|drain(s|ed)?|stolen|theft|breach|sues?|sued|lawsuit|charg(e|es|ed)|indict\w*|arrest\w*|"
                      r"ban(s|ned)?|delist(s|ed|ing)?|halt(s|ed)?|suspend(s|ed)?|outage|liquidat(ion|ions|ed)|plung(e|es|ed|ing)|crash(es|ed)?|"
                      r"dump(s|ed|ing)?|sell-?off|outflows?|investigat(e|es|ed|ion|ing)|probe|fraud|insolven\w*|bankrupt\w*|depeg\w*|rug ?pull|"
                      r"sold|sells|unlocks?|fined|reject(s|ed)?|den(y|ies|ied)|bearish|falls?|drops?|slump(s|ed)?|tumbl(e|es|ed))\b", re.I)


def tag_assets(text, universe=(), official=False):
    """The coins a headline is about: names, $CASHTAGS of listed coins, MACRO for market-wide events."""
    assets = [symbol for symbol, pattern in ASSET_NAMES if re.search(pattern, text, re.I)]
    listed = set(universe)
    for tag in re.findall(r"\$([A-Za-z][A-Za-z0-9]{1,9})\b", text):
        for symbol in (tag.upper(), "k" + tag.upper()):
            if symbol in listed and symbol not in assets: assets.append(symbol)
    if MACRO.search(text) or (official and not assets and OFFICIAL.search(text)):
        assets.append("MACRO")
    return assets


def quick_sentiment(text):
    """An instant keyword reading for fast trading; the local AI's analysis replaces it when it is done."""
    plus = sorted({m.group(0).lower() for m in POSITIVE.finditer(text)})
    minus = sorted({m.group(0).lower() for m in NEGATIVE.finditer(text)})
    if len(plus) == len(minus):
        return {"impact": "uncertain", "strength": 0, "words": plus + minus}
    impact = "positive" if len(plus) > len(minus) else "negative"
    return {"impact": impact, "strength": min(1.0, 0.35 + 0.15 * abs(len(plus) - len(minus))), "words": plus if impact == "positive" else minus}


def news_row(source, title, summary, link, published, now, group="portal", universe=(), analyze=True):
    age = (now - published).total_seconds()
    text = title + " " + summary
    assets = tag_assets(text, universe, official=group == "official")
    identity = hashlib.sha256((source + "|" + link + "|" + title + "|" + summary).encode()).hexdigest()
    return {"id": identity, "source": source, "group": group, "title": title, "summary": summary, "url": link,
            "published_at": published.isoformat(), "assets": assets, "quick": quick_sentiment(text),
            "eligible": analyze and bool(assets) and 0 <= age <= 48 * 3600}


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(body, source, now=None, expected=None, group=None, universe=(), analyze=True):
    """RSS or Atom. Article links must stay on the feed's own site; dates are required."""
    now = now or utcnow()
    document = body.decode("utf-8-sig")
    if "<!DOCTYPE" in document.upper() or "<!ENTITY" in document.upper():
        raise ValueError("Nem támogatott XML deklaráció.")
    root = ET.fromstring(document)
    expected = (expected or urlsplit(FEEDS[source]).hostname).removeprefix("www.")
    group = group or ("official" if source in ("Federal Reserve", "ECB", "SEC") else "portal")
    entries = []
    for item in root.findall(".//item")[:60]:
        entries.append((item.findtext("title"), item.findtext("description"), item.findtext("link"), item.findtext("pubDate"), False))
    for item in root.findall(".//" + ATOM + "entry")[:60]:
        link = next((l.get("href") for l in item.findall(ATOM + "link") if l.get("rel") in (None, "alternate")), "")
        entries.append((item.findtext(ATOM + "title"), item.findtext(ATOM + "summary") or item.findtext(ATOM + "content"), link,
                        item.findtext(ATOM + "published") or item.findtext(ATOM + "updated"), True))
    rows = []
    for raw_title, raw_summary, link, date, iso in entries:
        title, summary = plain(raw_title)[:400], plain(raw_summary)[:6500]
        link = (link or "").strip()
        host = urlsplit(link).hostname or ""
        if urlsplit(link).scheme != "https" or not (host == expected or host.endswith("." + expected)):
            continue
        try:
            published = datetime.fromisoformat((date or "").strip().replace("Z", "+00:00")) if iso else parsedate_to_datetime(date or "")
            if published.tzinfo is None: raise ValueError("Missing timezone")
            published = published.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if not title or (now - published).total_seconds() < -300:
            continue
        rows.append(news_row(source, title, summary, link, published, now, group, universe, analyze))
    return rows


def parse_telegram(body, source, channel, now=None, group="x", universe=(), analyze=True):
    """A public Telegram channel's web preview (t.me/s/<channel>). Many X news accounts post the same items there."""
    now = now or utcnow()
    document = body.decode("utf-8", "replace")
    rows = []
    for block in document.split("tgme_widget_message_wrap")[1:][-40:]:
        post = re.search(r'data-post="([A-Za-z0-9_]+)/(\d+)"', block)
        text = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        moment = re.search(r'<time datetime="([^"]+)"', block)
        if not (post and text and moment) or post.group(1).lower() != channel.lower():
            continue
        lines = [line for line in (plain(part) for part in re.split(r"<br\s*/?>", text.group(1))) if line]
        if not lines: continue
        # Alert accounts open with a row of emoji: the headline starts at the first word.
        title = re.sub(r"^[^\w$#@]+", "", next((line for line in lines if re.search(r"[A-Za-z]{3}", line)), lines[0]))[:220]
        try:
            published = datetime.fromisoformat(moment.group(1).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if (now - published).total_seconds() < -300:
            continue
        rows.append(news_row(source, title, " ".join(lines)[:3000], "https://t.me/" + post.group(1) + "/" + post.group(2),
                             published, now, group, universe, analyze))
    return rows


class NewsStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS news (id TEXT PRIMARY KEY, payload TEXT, status TEXT, analysis TEXT, attempts INTEGER DEFAULT 0, retry_at REAL DEFAULT 0)")
        self.db.commit()

    def ingest(self, rows):
        with self.db:
            for row in rows:
                self.db.execute("INSERT INTO news(id,payload,status) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, status=CASE WHEN news.status='archive' AND excluded.status='pending' THEN 'pending' ELSE news.status END", (
                    row["id"], json.dumps(row, ensure_ascii=False), "pending" if row["eligible"] else "archive"))
            self.db.execute("DELETE FROM news WHERE id NOT IN (SELECT id FROM news ORDER BY json_extract(payload,'$.published_at') DESC LIMIT 1000)")

    def analyze_one(self, now=None):
        now = now or utcnow()
        row = self.db.execute("SELECT id,payload,attempts FROM news WHERE status IN ('pending','failed') AND retry_at<=? ORDER BY json_extract(payload,'$.published_at') DESC LIMIT 1", (now.timestamp(),)).fetchone()
        if row is None: return False
        identity, raw, attempts = row; item = json.loads(raw)
        age = (now - datetime.fromisoformat(item["published_at"])).total_seconds()
        if not 0 <= age <= 48 * 3600:
            with self.db: self.db.execute("UPDATE news SET status='archive' WHERE id=?", (identity,))
            return True
        with self.db: self.db.execute("UPDATE news SET status='analyzing' WHERE id=?", (identity,))
        try:
            result = local_analysis("qwen3.8:27b", ",".join(item["assets"]),
                                    "RSS cím és kivonat; a teljes cikk és a hír hitelessége nincs függetlenül ellenőrizve.\n" + item["title"] + "\n" + item["summary"], hungarian=True,
                                    # The shared model answers ORBIT's Autopilot too; a background analysis waits its turn.
                                    timeout=900)
            with self.db:
                self.db.execute("UPDATE news SET status='analyzed', analysis=? WHERE id=?", (json.dumps(result, ensure_ascii=False), identity))
        except Exception as exc:
            with self.db:
                self.db.execute("UPDATE news SET status=?,analysis=?,attempts=?,retry_at=? WHERE id=?", (
                    "pending" if attempts < 2 else "failed", json.dumps({"error": str(exc)}), min(attempts + 1, 3), now.timestamp() + (300 if attempts < 2 else 900), identity))
        return True

    def summary(self, limit=80):
        rows = []
        for raw, status, analysis in self.db.execute("SELECT payload,status,analysis FROM news ORDER BY json_extract(payload,'$.published_at') DESC LIMIT ?", (limit,)):
            item = json.loads(raw); item["status"] = status; item["analysis"] = json.loads(analysis) if analysis else None
            item["summary"] = item.get("summary", "")[:500]
            rows.append(item)
        counts = dict(self.db.execute("SELECT status,COUNT(*) FROM news GROUP BY status"))
        return {"items": rows, "counts": counts}

    def recent(self, minutes=30, now=None):
        """Fresh items for fast trading, with the AI's reading when it is done and the instant one before."""
        since = ((now or utcnow()) - timedelta(minutes=minutes)).isoformat()
        rows = []
        for raw, analysis in self.db.execute("SELECT payload,analysis FROM news WHERE json_extract(payload,'$.published_at')>=? ORDER BY json_extract(payload,'$.published_at') DESC LIMIT 60", (since,)):
            item = json.loads(raw); analysis = json.loads(analysis) if analysis else None
            if analysis and analysis.get("impact"):
                item["reading"] = {"impact": analysis["impact"], "strength": 0.8, "by": "ai"}
            else:
                item["reading"] = dict(item.get("quick") or {"impact": "uncertain", "strength": 0}, by="quick")
            rows.append(item)
        return rows

    def close(self): self.db.close()


def shortlist(raw):
    """Coarse discovery only. Never infer perp skill from spot-inflated global ROI."""
    rows, seen = [], set()
    for row in raw.get("leaderboardRows", []):
        try:
            address = row["ethAddress"].lower()
            if not re.fullmatch(r"0x[0-9a-f]{40}", address) or address in seen: continue
            seen.add(address)
            windows = dict(row["windowPerformances"])
            month, week = windows["month"], windows["week"]
            capital, volume = number(row["accountValue"]), number(month["vlm"])
            roi = number(month["roi"])
            if not (10000 <= capital <= 10000000 and number(month["pnl"]) > 0 and number(week["pnl"]) > 0
                    and number(windows["allTime"]["pnl"]) > 0 and 0 < roi <= 1 and 1 <= volume / capital <= 300):
                continue
            rows.append({"address": address, "name": plain(str(row.get("displayName") or ""))[:60] or address[:8] + "…" + address[-4:], "roi": roi,
                         "turnover": volume / capital})
        except (KeyError, TypeError, ValueError, ZeroDivisionError): continue
    # Prefer established, moderate outcomes over newly funded extreme-ROI accounts.
    # Final ordering uses independent perp PnL/drawdown, not this discovery key.
    return sorted(rows, key=lambda row: abs(row["roi"] - number("0.15")))[:120]


def verify_candidate(row, portfolio, state, now=None):
    now = now or utcnow()
    history = dict(portfolio)
    month, week, total = history["perpMonth"], history["perpWeek"], history["perpAllTime"]
    pnl = month["pnlHistory"]; equity_series = month["accountValueHistory"]
    if len(pnl) < 14 or len(equity_series) < 14: raise ValueError("Kevés múltbeli adat.")
    start, end = int(pnl[0][0]), int(pnl[-1][0])
    days = (end - start) / 86400000
    if days < 25 or abs(now.timestamp() - end / 1000) > 7200: raise ValueError("Rövid vagy elavult múlt.")
    def delta(window):
        curve = window["pnlHistory"]
        return number(curve[-1][1]) - number(curve[0][1])
    gain = delta(month)
    if gain <= 0 or delta(week) <= 0 or delta(total) <= 0: raise ValueError("Nem egyenletesen pozitív megfigyelt eredmény.")
    initial = number(equity_series[0][1]); current = number(state["marginSummary"]["accountValue"])
    if abs(now.timestamp() - int(state["time"]) / 1000) > 30:
        raise ValueError("Elavult számlakitettség.")
    if initial < 10000 or current < 10000: raise ValueError("Túl alacsony megfigyelt tőke.")
    estimated_roi = gain / initial
    if not 0 < estimated_roi <= 1: raise ValueError("Szélsőséges vagy nem összevethető hozam.")
    base = number(pnl[0][1]); peak = initial; drawdown = number(0)
    for _, value in pnl:
        synthetic_equity = initial + number(value) - base
        peak = max(peak, synthetic_equity)
        drawdown = max(drawdown, (peak - synthetic_equity) / peak)
    if drawdown > number("0.20"): raise ValueError("Magas megfigyelt visszaesés.")
    positions = state["assetPositions"]
    if len(positions) > 20 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,29}", p["position"]["coin"]) for p in positions):
        raise ValueError("Nem támogatott pozíciólista a másolási hatókörben.")
    values = [abs(number(p["position"]["positionValue"])) for p in positions]
    gross = sum(values, number(0)) / current
    maximum = max(values, default=number(0)) / current
    if gross > 1 or maximum > number("0.5"): raise ValueError("Nem fér a kezdeti másolási kitettségi keretbe.")
    # Steady gains copy better than one lucky day: the share of rising steps in the month's PnL curve.
    steps = [number(b[1]) - number(a[1]) for a, b in zip(pnl, pnl[1:])]
    consistency = number(sum(1 for s in steps if s > 0)) / max(1, len(steps))
    # A copy follows every 5 s from public data: a trader who turns the account over many times a month trades
    # faster than a follower can, so the copy gets worse prices or misses trades. Half credit at 60x, none above.
    turnover = number(str(row.get("turnover", 0)))
    if turnover > 60: raise ValueError("Túl gyors kereskedés a másoláshoz (havi forgalom > 60× tőke).")
    copyable = number(1) if turnover <= 15 else number(1) - (turnover - 15) / 90
    score = estimated_roi / max(drawdown, number("0.02")) * (number("0.5") + consistency) * copyable
    return {"address": row["address"], "name": row["name"], "pnl_month": str(gain),
            "return_percent": str(estimated_roi * 100), "drawdown_percent": str(drawdown * 100),
            "equity": str(current), "gross_percent": str(gross * 100), "days": int(days),
            "consistency_percent": str(consistency * 100), "turnover": str(turnover), "copyable_percent": str(copyable * 100),
            "score": str(score), "checked_at": now.isoformat()}


def hu(value, digits=1):
    """A number the Hungarian way: 802 492 or 6,8."""
    return format(round(value, digits), "," + ("." + str(digits) + "f")).replace(",", " ").replace(".", ",")


def assess_trader(address, now=None, info=public_info):
    """Any public account the owner names: the same checks as the ranking, reported instead of rejected."""
    address = str(address).strip().lower()
    if not re.fullmatch(r"0x[0-9a-f]{40}", address):
        raise ValueError("Egy nyilvános Hyperliquid-számlacím kell (0x + 40 karakter). Privát kulcsot soha ne adj meg.")
    now = now or utcnow()
    portfolio = dict(info({"type": "portfolio", "user": address}))
    state = info({"type": "clearinghouseState", "user": address})
    equity = number(state["marginSummary"]["accountValue"])
    month = portfolio.get("perpMonth") or {}
    pnl = month.get("pnlHistory") or []; values = month.get("accountValueHistory") or []
    def delta(window):
        curve = (portfolio.get(window) or {}).get("pnlHistory") or []
        return number(curve[-1][1]) - number(curve[0][1]) if len(curve) >= 2 else number(0)
    gain = delta("perpMonth")
    initial = number(values[0][1]) if values else equity
    roi = gain / initial if initial > 0 else number(0)
    peak, drawdown = initial, number(0)
    for _, value in pnl:
        synthetic = initial + number(value) - number(pnl[0][1])
        peak = max(peak, synthetic)
        if peak > 0: drawdown = max(drawdown, (peak - synthetic) / peak)
    steps = [number(b[1]) - number(a[1]) for a, b in zip(pnl, pnl[1:])]
    consistency = number(sum(1 for s in steps if s > 0)) / max(1, len(steps))
    turnover = number(month.get("vlm") or 0) / equity if equity > 0 else number(0)
    positions = []
    for row in state.get("assetPositions") or []:
        position = row["position"]; quantity = number(position["szi"])
        if quantity:
            positions.append({"coin": position["coin"], "direction": "long" if quantity > 0 else "short",
                              "value": str(abs(number(position["positionValue"]))), "pnl": str(number(position.get("unrealizedPnl") or 0))})
    gross = sum((number(p["value"]) for p in positions), number(0)) / equity if equity > 0 else number(0)
    try:
        verify_candidate({"address": address, "name": address[:6] + "…" + address[-4:], "turnover": turnover}, portfolio, state, now)
        ranked, reason = True, None
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        ranked, reason = False, str(exc)
    checks = [
        {"ok": gain > 0, "text": "Az elmúlt hónapban " + ("nyereséges" if gain > 0 else "veszteséges") + " volt."},
        {"ok": delta("perpWeek") > 0, "text": "Az elmúlt héten " + ("nyereséges" if delta("perpWeek") > 0 else "nem volt nyereséges") + "."},
        {"ok": drawdown <= number("0.20"), "text": "A legnagyobb visszaesése " + hu(float(drawdown) * 100) + "% (20% felett kockázatos)."},
        {"ok": turnover <= 60, "text": "Havi forgalma a tőkéje " + hu(float(turnover)) + "-szerese (" + ("követhető tempó" if turnover <= 60 else "túl gyors a másoláshoz") + ")."},
        {"ok": gross <= 1, "text": "Most a tőkéje " + hu(float(gross) * 100, 0) + "%-át kockáztatja nyitott ügyletekben."},
        {"ok": equity >= 10000, "text": "Számlaértéke " + hu(float(equity), 0) + " $."}]
    curve = [[int(t), str(number(v) - number(pnl[0][1]))] for t, v in pnl[:: max(1, len(pnl) // 60)]] if pnl else []
    return {"address": address, "equity": str(equity), "pnl_month": str(gain), "return_percent": str(roi * 100),
            "drawdown_percent": str(drawdown * 100), "consistency_percent": str(consistency * 100), "turnover": str(turnover),
            "gross_percent": str(gross * 100), "positions": positions, "ranked": ranked, "reason": reason, "checks": checks,
            "curve": curve, "checked_at": now.isoformat()}


def discover_traders(stop=None, progress=None):
    raw = json.loads(fetch_bytes(LEADERBOARD, maximum=60_000_000))
    candidates, checked, rejected = [], 0, {}
    def report(searching):
        ordered = sorted(candidates, key=lambda row: number(row["score"]), reverse=True)
        return {"updated_at": utcnow().isoformat(), "candidates": ordered, "checked": checked, "rejected": rejected,
                "searching": searching, "source": LEADERBOARD, "error": None,
                "method": "Fő perpetual piac: ≥25 nap, pozitív havi/heti/teljes PnL, becsült visszaesés ≤20%, jelenlegi összkitettség ≤100%, egy pozíció ≤50%, havi forgalom ≤60× tőke. Pontszám: havi hozam / visszaesés × egyenletesség × másolhatóság. A hozam és visszaesés induló tőkével közelített, nem auditált vagy jövőbeli eredmény."}
    if progress: progress(report(True))
    for row in shortlist(raw):
        if stop is not None and stop.is_set(): break
        try:
            portfolio = public_info({"type": "portfolio", "user": row["address"]})
            state = public_info({"type": "clearinghouseState", "user": row["address"]})
            checked += 1
            candidates.append(verify_candidate(row, portfolio, state))
        except (ValueError, KeyError, TypeError, IndexError, urllib.error.URLError, TimeoutError) as exc:
            reason = str(exc)
            rejected[reason] = rejected.get(reason, 0) + 1
        if progress: progress(report(True))
        if stop is not None and stop.wait(0.3): break
        if len(candidates) >= 15: break
    return report(False)
