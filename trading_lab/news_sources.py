"""Where MiLLIONS reads the news: official releases, crypto news sites and the X news accounts.

X has no free reading access (its API is paid, and the public mirrors such as nitter answered 410/451 on 2 Nov 2026),
so the X accounts are read from the public Telegram channels where the same accounts post the same items.
The owner can switch any source off and add an RSS feed or a public Telegram channel.
"""
import hashlib
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from continuous_data import FEEDS, atomic_json, fetch_bytes, parse_feed, parse_telegram, plain, utcnow

GROUPS = {"official": "Hivatalos", "portal": "Hírportál", "x": "X-hírfiók", "custom": "Saját forrás"}
# Seconds between two reads of one source: breaking-news accounts often, articles less, official releases rarely.
INTERVAL = {"official": 300, "portal": 120, "x": 30}
SOURCES = (
    dict(id="fed", name="Federal Reserve", group="official", kind="rss", url=FEEDS["Federal Reserve"]),
    dict(id="ecb", name="ECB", group="official", kind="rss", url=FEEDS["ECB"]),
    dict(id="sec", name="SEC", group="official", kind="rss", url=FEEDS["SEC"]),
    dict(id="coindesk", name="CoinDesk", group="portal", kind="rss", url=FEEDS["CoinDesk"]),
    dict(id="cointelegraph", name="Cointelegraph", group="portal", kind="rss", url="https://cointelegraph.com/rss"),
    dict(id="decrypt", name="Decrypt", group="portal", kind="rss", url="https://decrypt.co/feed"),
    dict(id="theblock", name="The Block", group="portal", kind="rss", url="https://www.theblock.co/rss.xml"),
    dict(id="bitcoinmagazine", name="Bitcoin Magazine", group="portal", kind="rss", url="https://bitcoinmagazine.com/feed"),
    dict(id="cryptoslate", name="CryptoSlate", group="portal", kind="rss", url="https://cryptoslate.com/feed/"),
    dict(id="defiant", name="The Defiant", group="portal", kind="rss", url="https://thedefiant.io/api/feed"),
    dict(id="bitcoinist", name="Bitcoinist", group="portal", kind="rss", url="https://bitcoinist.com/feed/"),
    dict(id="newsbtc", name="NewsBTC", group="portal", kind="rss", url="https://www.newsbtc.com/feed/"),
    dict(id="x-watcherguru", name="Watcher Guru", handle="@WatcherGuru", group="x", kind="telegram", channel="WatcherGuru"),
    dict(id="x-treenews", name="Tree News", handle="@TreeNewsFeed", group="x", kind="telegram", channel="TreeNewsFeed"),
    dict(id="x-wublockchain", name="Wu Blockchain", handle="@WuBlockchain", group="x", kind="telegram", channel="wublockchainenglish"),
    dict(id="x-walterbloomberg", name="Walter Bloomberg", handle="@DeItaone", group="x", kind="telegram", channel="WalterBloomberg"),
    dict(id="x-unfolded", name="unfolded.", handle="@cryptounfolded", group="x", kind="telegram", channel="unfolded"),
    # Transfers are information, not news to analyse: shown and used, never queued for the local AI.
    dict(id="x-whalealert", name="Whale Alert", handle="@whale_alert", group="x", kind="telegram", channel="whale_alert_io", analyze=False),
)
MAX_CUSTOM = 20


def url_of(source):
    return source["url"] if source["kind"] == "rss" else "https://t.me/s/" + source["channel"]


def safe_feed_url(url):
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    try:
        ipaddress.ip_address(host); literal = True
    except ValueError:
        literal = False
    if parts.scheme != "https" or not host or literal or "." not in host or host.endswith((".local", ".localhost", ".internal")) \
            or parts.username or parts.password or parts.port not in (None, 443) or len(url) > 300:
        raise ValueError("RSS-forrásnak nyilvános https:// címet adj meg (bejelentkezés, IP-cím és helyi cím nélkül).")
    return url.strip()


def channel_name(value):
    name = re.sub(r"^(https://)?(t\.me/(s/)?|@)", "", value.strip()).strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
        raise ValueError("Telegram-csatornának a nevét add meg (pl. WatcherGuru vagy https://t.me/WatcherGuru).")
    return name


def load(root):
    """All sources with their on/off state."""
    try:
        saved = json.loads((Path(root) / "news-sources.json").read_text())
    except (OSError, ValueError):
        saved = {}
    disabled = set(saved.get("disabled") or [])
    sources = [dict(s) for s in SOURCES] + [dict(s, group="custom") for s in saved.get("custom") or []]
    for source in sources:
        source["enabled"] = source["id"] not in disabled
        source.setdefault("analyze", True)
    return sources


def save(root, payload):
    """{"disabled": [ids], "custom": [{"name", "kind": "rss"|"telegram", "url"|"channel"}]} after validation."""
    if not isinstance(payload, dict):
        raise ValueError("Hibás forráslista.")
    custom = []
    for row in (payload.get("custom") or [])[:MAX_CUSTOM + 1]:
        if len(custom) >= MAX_CUSTOM:
            raise ValueError("Legfeljebb " + str(MAX_CUSTOM) + " saját forrás adható meg.")
        kind = row.get("kind")
        if kind == "rss":
            entry = {"kind": "rss", "url": safe_feed_url(str(row.get("url", "")))}
        elif kind == "telegram":
            entry = {"kind": "telegram", "channel": channel_name(str(row.get("channel", "")))}
        else:
            raise ValueError("A forrás RSS vagy Telegram-csatorna lehet.")
        key = entry.get("url") or entry["channel"].lower()
        entry["id"] = "custom-" + hashlib.sha256(key.encode()).hexdigest()[:10]
        entry["name"] = plain(str(row.get("name") or ""))[:40] or (urlsplit(entry["url"]).hostname if kind == "rss" else entry["channel"])
        if any(c["id"] == entry["id"] for c in custom):
            continue
        custom.append(entry)
    known = {s["id"] for s in SOURCES} | {c["id"] for c in custom}
    disabled = sorted({str(i) for i in payload.get("disabled") or [] if str(i) in known})
    atomic_json(Path(root) / "news-sources.json", {"disabled": disabled, "custom": custom})
    return load(root)


def read(source, universe=(), now=None):
    body = fetch_bytes(url_of(source), maximum=3_000_000, allowed=[url_of(source)])
    analyze = source.get("analyze", True)
    if source["kind"] == "telegram":
        return parse_telegram(body, source["name"], source["channel"], now, source["group"], universe, analyze)
    return parse_feed(body, source["name"], now, urlsplit(source["url"]).hostname, source["group"], universe, analyze)


def collect(root, store, memory, universe=(), now=None, reader=read):
    """Read every enabled source that is due. memory keeps each source's last read and outcome between calls."""
    now = now or utcnow()
    report = []
    for source in load(root):
        if not source["enabled"]:
            continue
        last = memory.get(source["id"]) or {}
        due = now.timestamp() - last.get("at", 0) >= INTERVAL.get(source["group"], 120 if source["kind"] == "rss" else 30)
        if due:
            try:
                rows = reader(source, universe, now)
                store.ingest(rows)
                newest = max((r["published_at"] for r in rows), default=None)
                last = {"at": now.timestamp(), "ok": True, "count": len(rows), "newest_at": newest, "error": None}
            except Exception as exc:
                last = {"at": now.timestamp(), "ok": False, "count": 0, "newest_at": last.get("newest_at"), "error": str(exc)[:200]}
            memory[source["id"]] = last
        report.append({"id": source["id"], "name": source["name"], "group": source["group"], "handle": source.get("handle"),
                       "ok": last.get("ok"), "count": last.get("count"), "newest_at": last.get("newest_at"), "error": last.get("error")})
    return {"updated_at": now.isoformat(), "sources": report}
