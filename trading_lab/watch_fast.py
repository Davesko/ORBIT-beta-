"""Continuous PAPER fast mode: follows the hour trend of the most traded coins and trades their retests with limit orders.

Every 3 s it manages the open trades and the resting limit orders; once a minute, when a bar closes, it looks for new
setups. It writes everything the owner's screen shows to reports/fast-state.json: what it is doing, where the money
is, each coin's trend and setup, the resting orders, price charts with entry, stop, target and limit, the journal,
the equity curve and how each entry kind has done.
"""
import json
import signal
import sqlite3
import threading
from pathlib import Path

from account import active_account, database_path
from agent import number, stamp
from continuous_data import NewsStore, atomic_json, utcnow
from fast_ai import FAMILIES, PROFILES, FastPaper, market_view, news_setup, num, retest_setup, settings_from, signal_for
from market_data import market_snapshot, public_info, timestamp_millis
from research_engine import BARS

ROOT = Path.home() / 'Library/Application Support/ReszvenyAI'
LOOP = 3
CHART_BARS = 90
HISTORY = 300


def load_settings(root=ROOT):
    try: return settings_from(json.loads((root / 'fast-settings.json').read_text()))
    except (OSError, ValueError): return settings_from({})


def validated_strategy(root=ROOT):
    """The best strategy that passed the research test and its new-data observation, or None."""
    try: state = json.loads((root / 'reports/research-state.json').read_text())
    except (OSError, ValueError): return None
    usable = [e for e in state.get('eligible') or [] if isinstance(e.get('strategy'), dict) and e.get('symbol')]
    return max(usable, key=lambda e: float(e.get('forward_net_percent') or 0)) if usable else None


def market_rows(root=ROOT):
    """The monitor's 3-second market file when it is fresh, else one direct read."""
    try:
        state = json.loads((root / 'reports/market-state.json').read_text())
        if (utcnow() - stamp(state['updated_at'])).total_seconds() <= 10 and state['rows'] and 'funding' in state['rows'][0]:
            return {r['symbol']: r for r in state['rows']}
    except (OSError, ValueError, KeyError, IndexError): pass
    return {r['symbol']: r for r in market_snapshot()['rows']}


def recent_news(root=ROOT):
    path = root / 'data/automatic-news.sqlite'
    if not path.exists(): return []
    store = NewsStore(path)
    try: return store.recent(30)
    except sqlite3.Error: return []
    finally: store.close()


def recent_bars(symbol, bar, count, now_ms):
    step = BARS[bar]
    raw = public_info({'type': 'candleSnapshot', 'req': {'coin': symbol, 'interval': bar, 'startTime': now_ms - (count + 2) * step, 'endTime': now_ms}})
    return sorted(({'t': int(r['t']), 'T': int(r['T']), 'o': float(r['o']), 'h': float(r['h']), 'l': float(r['l']), 'c': float(r['c']), 'v': float(r['v'])}
                   for r in raw if r.get('s') == symbol and r.get('i') == bar), key=lambda b: b['t'])


def refresh_bars(cache, symbol, now_ms):
    """5 hours of 1-minute bars once, then only the last few each minute (the exchange's rate limit counts requests)."""
    held = cache.get(symbol)
    fresh = recent_bars(symbol, '1m', 5 if held and len(held['bars']) >= 250 else HISTORY, now_ms)
    merged = {b['t']: b for b in (held['bars'] if held else [])}
    merged.update({b['t']: b for b in fresh})
    cache[symbol] = {'minute': now_ms // 60000, 'bars': [merged[t] for t in sorted(merged)][-HISTORY:]}


def book_quote(symbol):
    data = public_info({'type': 'l2Book', 'coin': symbol})
    if data.get('coin') != symbol or len(data.get('levels', [])) != 2 or not data['levels'][0] or not data['levels'][1]:
        raise ValueError('Hibás árfolyam: ' + symbol)
    return {'bid': data['levels'][0][0]['px'], 'ask': data['levels'][1][0]['px'], 'at': timestamp_millis(data['time'])}, data['levels']


def pick_universe(market, count, held, news):
    liquid = [s for s, r in sorted(market.items(), key=lambda kv: -float(kv[1]['volume'])) if float(market[s]['volume']) >= 20e6][:count]
    mentioned = [a for item in news for a in item.get('assets') or [] if a in market and float(market[a]['volume']) >= 5e6]
    return list(dict.fromkeys(held + liquid + mentioned))[:count + 6]


def describe(positions, orders, watch, result, settings, news_count):
    """What the AI is doing right now, in one sentence for the owner."""
    profile = PROFILES[settings['profile']]
    if result.get('daily_block'):
        return 'blocked', 'Elérte a napi veszteségkorlátot (' + str(round(float(profile['daily_loss']) * 100)) + '%): ma már nem nyit új ügyletet.'
    if positions:
        parts = [p['symbol'] + ' (' + ('emelkedésre' if p['direction'] > 0 else 'esésre') + ')' for p in positions]
        return 'in_trade', str(len(positions)) + ' ügylet nyitva: ' + ', '.join(parts) + '. A nyereségcél limitáron vár, a veszteségkorlátot és az időt figyeli.'
    if orders:
        o = orders[0]
        return 'waiting_fill', 'Limitáras megbízás vár: ' + o['symbol'] + ' ' + ('vétel' if o['direction'] > 0 else 'eladás') + ' ' + num(float(o['price'])) + \
            '-on. Csak akkor teljesül, ha az ár visszajön ide – így olcsón és jó áron lép be.'
    ups = sum(1 for w in watch if w['trend'] > 0); downs = sum(1 for w in watch if w['trend'] < 0)
    return 'watching', 'Figyel ' + str(len(watch)) + ' piacot és ' + str(news_count) + ' friss hírt: ' + str(ups) + ' emelkedő, ' + str(downs) + \
        ' csökkenő trendben. Kitörésre vár, utána a visszatesztnél lép be limitárral.'


def tick(engine, cache, root=ROOT):
    """One round: manage trades and orders, look for setups on fresh bars, and return the owner's view of it."""
    result, setups, quotes, error, news, market, views = {}, [], {}, None, [], {}, {}
    bars = cache.setdefault('bars', {}); settings = load_settings(root)
    try:
        now = utcnow(); now_ms = int(now.timestamp() * 1000); minute = now_ms // 60000
        market = market_rows(root); book = engine.ledger.book()
        held = [i.split(':')[3] for i in book['positions']]
        orders = engine.open_orders()
        news = recent_news(root) if settings['families'].get('news', True) else []
        universe = [s for s in pick_universe(market, settings['coins'], held + [o['symbol'] for o in orders], news) if s in market]
        for symbol in [s for s in universe if bars.get(s, {}).get('minute') != minute][:cache.get('per_round', 5)]:
            try: refresh_bars(bars, symbol, now_ms)
            except Exception: pass
        strategy = validated_strategy(root)
        for symbol in universe:
            view = market_view((bars.get(symbol) or {}).get('bars') or [], now_ms)
            views[symbol] = view
            if not view: continue
            extra = {'symbol': symbol, 'unit': view['unit'], 'max_leverage': market[symbol].get('max_leverage', 3)}
            if settings['families'].get('retest', True):
                found = retest_setup(view, now_ms)
                if found: setups.append(dict(found, **extra))
            if news:
                found = news_setup(symbol, news, view, now)
                if found: setups.append(dict(found, **extra))
            if strategy and strategy['symbol'] == symbol and settings['families'].get('research', True):
                sig = signal_for(strategy['strategy'], view['closed'], now_ms)
                if sig and sig['bar_open'] == minute * 60000 and view['trend'] != -sig['direction']:
                    setups.append(dict(extra, family='research', direction=sig['direction'], limit=None,
                                       why=strategy['id'] + ' (a kutatás teszt- és megfigyelési időszakán is nyereséges volt)'))
        for symbol in set(held + [o['symbol'] for o in orders] + [s['symbol'] for s in setups]):
            quotes['hyperliquid:default:perpetual:' + symbol + ':USDC'] = book_quote(symbol)[0]
        if (orders or setups) and not cache.get('lots'):
            cache['lots'] = {i['name']: str(number(10) ** -int(i['szDecimals'])) for i in public_info({'type': 'meta'})['universe']}
        # The step's clock is read after all the fetching: quotes fetched during the round must not look like the future.
        result = engine.step(utcnow(), quotes, setups, settings, cache.get('lots'))
    except Exception as exc:
        error = str(exc); result = {'skipped': [], 'events': []}
    now = utcnow(); book = engine.ledger.book(); orders = engine.open_orders()
    positions = []
    for identifier, p in book['positions'].items():
        symbol = identifier.split(':')[3]; quote = quotes.get(identifier)
        q, entry = float(p['quantity']), float(p['entry']); side = 1 if q > 0 else -1
        price = (float(quote['bid']) + float(quote['ask'])) / 2 if quote else float((market.get(symbol) or {}).get('price') or entry)
        stop = float(p.get('stop', 0.0075)); take = float(p.get('take', 0.015))
        positions.append({'symbol': symbol, 'direction': side, 'quantity': p['quantity'], 'entry': entry, 'price': price,
                          'notional': abs(q) * price, 'pnl': q * (price - entry), 'r': q * (price - entry) / float(p.get('risk_usd') or 1),
                          'stop_price': entry * (1 - stop * side), 'take_price': entry * (1 + take * side), 'opened_at': p.get('opened_at'),
                          'leverage': p.get('leverage'), 'risk_usd': p.get('risk_usd'), 'families': p.get('families') or [],
                          'reasons': p.get('reasons') or []})
    by_symbol = {o['symbol']: o for o in orders}; trading = {p['symbol'] for p in positions}
    watch = []
    for symbol, view in views.items():
        row = market.get(symbol) or {}
        found = [s for s in setups if s['symbol'] == symbol]
        if symbol in trading: status = 'ügyletben'
        elif symbol in by_symbol:
            o = by_symbol[symbol]; status = 'limitáras ' + ('vétel' if o['direction'] > 0 else 'eladás') + ' vár ' + num(float(o['price'])) + '-on'
        elif found: status = found[0]['why']
        elif not view: status = 'adatok töltődnek'
        else: status = {1: 'emelkedő trend · kitörésre vár', -1: 'csökkenő trend · kitörésre vár', 0: 'nincs egyértelmű trend · most nem kereskedik'}[view['trend']]
        watch.append({'symbol': symbol, 'trend': view['trend'] if view else 0, 'unit': view['unit'] if view else None, 'price': row.get('price'),
                      'change_percent': row.get('change_percent'), 'funding': row.get('funding'), 'status': status,
                      'active': symbol in trading or symbol in by_symbol,
                      'signals': [{'label': FAMILIES[s['family']], 'direction': s['direction'], 'why': s['why']} for s in found]})
    watch.sort(key=lambda w: (not w['active'], not w['signals'], w['trend'] == 0))
    journal = engine.journal(30)
    charted = list(dict.fromkeys([p['symbol'] for p in positions] + [o['symbol'] for o in orders] + [w['symbol'] for w in watch[:4]] +
                                 [t['symbol'] for t in journal[:4] if t.get('closed_at') and (now - stamp(t['closed_at'])).total_seconds() < 7200]))
    charts = {s: [[b['t'], b['c']] for b in bars[s]['bars'][-CHART_BARS:]] for s in charted if bars.get(s)}
    phase, message = describe(positions, orders, watch, result, settings, len(news))
    families = engine.family_stats()
    for f in families.values(): f['enabled'] = settings['families'].get(f['id'], True)
    return {'mode': 'PAPER_ONLY', 'updated_at': now.isoformat(), 'settings': settings, 'profile': dict(PROFILES[settings['profile']], id=settings['profile']),
            'phase': 'error' if error else phase, 'message': ('Adat- vagy működési hiba, most nem nyit új ügyletet: ' + error) if error else message,
            'error': error, 'positions': positions, 'orders': orders, 'order_history': engine.recent_orders(12), 'watch': watch[:16], 'charts': charts,
            'journal': journal, 'equity': engine.equity_curve(now.timestamp() - 86400), 'families': list(families.values()), 'stats': engine.stats(),
            'risk': {'fraction': result.get('risk'), 'basis': result.get('risk_basis')}, 'events': result.get('events', []),
            'skipped': result.get('skipped', []), 'news_count': len(news), 'book': book}


def main():
    account = active_account(ROOT)
    if not account or account['mode'] != 'fast_ai': raise ValueError('Nincs aktív Gyors AI portfólió.')
    engine = FastPaper(database_path(ROOT, account['database']))
    stop = threading.Event(); cache = {}
    signal.signal(signal.SIGTERM, lambda *_: stop.set()); signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        while not stop.is_set():
            try: state = tick(engine, cache)
            except Exception as exc:
                state = {'mode': 'PAPER_ONLY', 'updated_at': utcnow().isoformat(), 'phase': 'error', 'message': 'Az állapot nem írható: ' + str(exc), 'error': str(exc)}
            atomic_json(ROOT / 'reports/fast-state.json', state)
            stop.wait(LOOP)
    finally:
        stop.set(); engine.close()


if __name__ == '__main__': main()
