"""PAPER-only fast trading, timed and cheap: trade with the trend, enter on a pullback with a resting limit order.

Why this design (measured on 2 Nov 2026, 16 coins, 3.5 days of 1-minute and 17 days of 5-minute Hyperliquid bars):
- The first version chased breakouts and momentum with market orders. After its signals the price moved on by only
  0.4-2 bp in the next 1-15 minutes (46-49% hits) while a round trip cost 20 bp: about -15 bp a trade. None of 234
  chase/fade/RSI variants was positive after costs in both halves of the data (TradingCalc deflated Sharpe ~0).
- Waiting for the price to come back to the broken level (a "retest") in the direction of the hour trend, with a
  resting limit order, and taking profit with a resting limit too, cut the average to about -0.5 bp a trade with 53%
  winners: roughly break-even instead of a sure loss. It is the cheapest and best-timed setup found, not a proven edge.
- Costs at Hyperliquid's base tier: maker 0.015%, taker 0.045% (+0.03% slippage on market exits). A limit entry and a
  limit take-profit cost 0.03% in all (TradingCalc breakeven_planning); a stopped trade 0.09%.

Sizing (TradingCalc risk_reward, position_sizing, liquidation_safety, kelly_frontier):
- Size = dollars at risk / (stop + costs): 1% risk on a 0.7% stop is ~12 670 $, 1.27x the account.
- A position's liquidation price stays at least 3 stops away, which caps alts near 5x.
- 0.375 of full Kelly keeps the chance of ever halving the account at 5%; after 20 trades the risk per trade follows
  the AI's own record at the profile's Kelly fraction.
"""
import hashlib
import json
from datetime import datetime, timezone
from decimal import ROUND_DOWN

from agent import number, stamp
from copy_trading import PaperCopyLedger, apply_paper_orders, paper_equity
from research_engine import BARS

MAKER_FEE = number('0.00015')
FEE = number('0.00045')            # taker fee, for market exits (stop, time limit, stop button)
SLIPPAGE = number('0.0003')
COST = MAKER_FEE + FEE + SLIPPAGE  # worst round trip: limit entry, market stop
MAX_SPREAD = number('0.0015')
# Positions of the earlier news-AI mode keep the exits they were opened with.
LEGACY = dict(stop='0.0075', take='0.015', seconds=180)
TAKE_UNITS, STOP_UNITS = 1.5, 2.5   # in units of the coin's typical 15-minute move (4 x the 1-minute average range)
MIN_STOP, MAX_STOP = 0.004, 0.04
HOLD = 90 * 60
ORDER_LIFE = {'retest': 300, 'news': 60, 'research': 60}
COOLDOWN = 10 * 60
LIQ_BUFFER = 3
PROFILES = {
    'ovatos': dict(label='Óvatos', risk='0.005', risk_cap='0.01', kelly='0.25', leverage=2, gross=2, positions=2, daily_loss='0.03'),
    'normal': dict(label='Normál', risk='0.01', risk_cap='0.02', kelly='0.375', leverage=3, gross=4, positions=3, daily_loss='0.05'),
    'meresz': dict(label='Merész', risk='0.02', risk_cap='0.03', kelly='0.5', leverage=5, gross=6, positions=5, daily_loss='0.08'),
}
FAMILIES = {
    'retest': 'Visszateszt a trend irányában',
    'news': 'Friss hír',
    'research': 'Bevált kutatási szabály',
}
DEFAULT_SETTINGS = {'profile': 'normal', 'families': {k: True for k in FAMILIES}, 'coins': 10}


def settings_from(raw):
    """The owner's fast-AI settings, validated: profile, setups on/off, number of coins watched."""
    raw = raw if isinstance(raw, dict) else {}
    profile = raw.get('profile', 'normal')
    if profile not in PROFILES: raise ValueError('Ismeretlen kockázati profil.')
    families = dict(DEFAULT_SETTINGS['families'], **{k: bool(v) for k, v in (raw.get('families') or {}).items() if k in FAMILIES})
    if not any(families.values()): raise ValueError('Legalább egy belépési mód maradjon bekapcsolva.')
    coins = int(raw.get('coins', 10))
    if not 3 <= coins <= 20: raise ValueError('3 és 20 közötti számú piacot figyelhet.')
    return {'profile': profile, 'families': families, 'coins': coins}


def liq_distance(leverage, mmr, side):
    """Distance to an isolated position's liquidation (TradingCalc liquidation_safety: 5x long, 1.25% -> 18.99%)."""
    return (1 / leverage - mmr) / (1 - mmr if side > 0 else 1 + mmr)


def validate_quote(quote, now):
    bid, ask = number(quote['bid']), number(quote['ask'])
    # The exchange's clock may run up to a couple of seconds apart from the Mac's.
    if bid <= 0 or ask < bid or not -2 <= (now - stamp(quote['at'])).total_seconds() <= 10:
        raise ValueError('Nincs friss, használható kötési ár.')
    return bid, ask


def close_orders(book, quotes, now):
    """Market exits at the current quote with slippage and the taker fee."""
    orders = []
    for identifier, position in book['positions'].items():
        bid, ask = validate_quote(quotes[identifier], now)
        quantity = number(position['quantity']); delta = -quantity
        price = (ask if delta > 0 else bid) * (1 + SLIPPAGE if delta > 0 else 1 - SLIPPAGE)
        orders.append({'instrument': identifier, 'delta': str(delta), 'price': str(price), 'fee': str(abs(delta) * price * FEE),
                       'transition': 'teljes zárás', 'side': 'buy' if delta > 0 else 'sell', 'target': '0'})
    return orders


def limit_exit(identifier, position, price):
    """A resting take-profit limit order: the target price and the maker fee."""
    quantity = number(position['quantity']); delta = -quantity
    return {'instrument': identifier, 'delta': str(delta), 'price': str(price), 'fee': str(abs(delta) * price * MAKER_FEE),
            'transition': 'teljes zárás', 'side': 'buy' if delta > 0 else 'sell', 'target': '0'}


def signal_for(strategy, bars, now_ms):
    """The research rule (research_engine.simulate) for the bar opening now: {direction, bar_open, move} or None."""
    step = BARS[strategy.get('bar', '1m')]; window = int(strategy['window'])
    closed = [b for b in bars if b['T'] < now_ms]
    if len(closed) < window + 1: return None
    last = closed[-window - 1:]
    if any(b['t'] - a['t'] != step for a, b in zip(last, last[1:])) or now_ms - last[-1]['T'] > step: return None
    move = last[-1]['c'] / last[0]['c'] - 1
    if abs(move) < float(strategy['threshold']): return None
    direction = (1 if move > 0 else -1) * (1 if strategy['family'] == 'momentum' else -1)
    return {'direction': direction, 'bar_open': last[-1]['t'] + step, 'move': move}


def pct(x, digits=1):
    return (('+' if x > 0 else '') + ('%.' + str(digits) + 'f') % (x * 100)).replace('.', ',') + '%'


def share(x, digits=1):
    return (('%.' + str(digits) + 'f') % (abs(x) * 100)).replace('.', ',') + '%'


def num(x):
    return ('{:,.' + ('0' if x >= 1000 else '2' if x >= 1 else '5') + 'f}').format(x).replace(',', ' ').replace('.', ',')


def ema(values, n):
    k = 2 / (n + 1); out = values[0]
    for v in values[1:]: out = k * v + (1 - k) * out
    return out


def atr_fraction(bars, n=14):
    ranges = [max(b['h'] - b['l'], abs(b['h'] - a['c']), abs(b['l'] - a['c'])) / b['c'] for a, b in zip(bars, bars[1:])][-n:]
    return sum(ranges) / len(ranges) if ranges else None


def market_view(bars, now_ms):
    """The hour trend (1- and 4-hour averages on 1-minute closes) and the coin's typical 15-minute move."""
    closed = [b for b in bars if b['T'] < now_ms]
    if len(closed) < 250 or now_ms - closed[-1]['T'] > 120000: return None
    closes = [b['c'] for b in closed]
    fast, slow = ema(closes[-600:], 60), ema(closes[-600:], 240)
    last = closes[-1]
    # A 0.05% dead band: two averages a hair apart are no trend.
    trend = 1 if last > slow and fast > slow * 1.0005 else -1 if last < slow and fast < slow * 0.9995 else 0
    unit = (atr_fraction(closed) or 0) * 4
    return {'trend': trend, 'unit': unit, 'last': last, 'bar': closed[-1], 'closed': closed}


def retest_setup(view, now_ms):
    """A breakout of the last hour's range on heavy volume, in the trend's direction, on the bar that just closed:
    a limit order rests at the broken level and fills only if the price comes back to it."""
    if not view or not view['trend']: return None
    closed = view['closed']; last = closed[-1]
    if now_ms - last['T'] > 70000: return None
    prior = closed[-61:-1]
    high, low = max(b['h'] for b in prior), min(b['l'] for b in prior)
    volume = sum(b['v'] for b in prior) / len(prior)
    ratio = last['v'] / volume if volume > 0 else 0
    if ratio < 1.8: return None
    if view['trend'] > 0 and last['c'] > high:
        return {'family': 'retest', 'direction': 1, 'limit': high, 'why': 'emelkedő trendben áttörte az 1 órás csúcsot ' + ('%.1f' % ratio).replace('.', ',') +
                '× forgalommal; limitáras vétel a régi csúcson (' + num(high) + '), ha az ár visszajön rá'}
    if view['trend'] < 0 and last['c'] < low:
        return {'family': 'retest', 'direction': -1, 'limit': low, 'why': 'csökkenő trendben áttörte az 1 órás mélypontot ' + ('%.1f' % ratio).replace('.', ',') +
                '× forgalommal; limitáras eladás a régi mélyponton (' + num(low) + '), ha az ár visszajön rá'}
    return None


def news_setup(symbol, items, view, now, minutes=3):
    """A fresh, clearly positive or negative headline about the coin, not against the trend, that the price already
    confirms by 0.1-1.5%: a limit order joins the best price for a minute."""
    if not view: return None
    best = None
    for item in items:
        if symbol not in (item.get('assets') or []): continue
        reading = item.get('reading') or {}
        if reading.get('impact') not in ('positive', 'negative'): continue
        published = stamp(item['published_at']); age = (now - published).total_seconds()
        if not 0 <= age <= minutes * 60: continue
        direction = 1 if reading['impact'] == 'positive' else -1
        strength = float(reading.get('strength') or 0.5) * (1.2 if item.get('group') == 'x' else 1)
        if strength < 0.65 or view['trend'] == -direction: continue
        at = int(published.timestamp() * 1000)
        then = next((b['o'] for b in view['closed'] if b['t'] <= at <= b['T']), None)
        move = (view['last'] / then - 1) * direction if then else 0
        if not 0.001 <= move <= 0.015: continue
        if not best or strength > best[0]:
            best = (strength, {'family': 'news', 'direction': direction, 'limit': None,
                               'why': item['source'] + ': „' + item['title'][:110] + '” (' + ('AI-elemzés' if reading.get('by') == 'ai' else 'gyors értékelés') +
                               ', ' + str(int(age)) + ' mp-e; az ár azóta ' + pct(move * direction, 2) + ')'})
    return best[1] if best else None


class FastPaper:
    def __init__(self, path):
        self.ledger = PaperCopyLedger(path)
        self.db = self.ledger.connection
        self.db.execute('CREATE TABLE IF NOT EXISTS fast_events(id TEXT PRIMARY KEY, at REAL, kind TEXT, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS fast_days(day TEXT PRIMARY KEY, starting_equity TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS fast_trades(id TEXT PRIMARY KEY, symbol TEXT, direction INTEGER, opened_at TEXT, closed_at TEXT,'
                        ' entry TEXT, exit TEXT, notional TEXT, risk_usd TEXT, pnl TEXT, r REAL, families TEXT, reasons TEXT, exit_reason TEXT, score REAL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS fast_equity(at REAL PRIMARY KEY, equity TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS fast_orders(id TEXT PRIMARY KEY, symbol TEXT, direction INTEGER, price TEXT, unit REAL, family TEXT,'
                        ' why TEXT, created_at TEXT, expires_at TEXT, status TEXT, max_leverage INTEGER)')

    def closed(self):
        return [dict(zip(('symbol', 'r', 'pnl', 'families'), (s, r, p, json.loads(f)))) for s, r, p, f in
                self.db.execute('SELECT symbol,r,pnl,families FROM fast_trades WHERE closed_at IS NOT NULL ORDER BY closed_at')]

    def family_stats(self):
        """Each entry kind's paper record; one that keeps losing (15 trades, average below -0.15R) pauses itself."""
        trades = self.closed(); out = {}
        for family, label in FAMILIES.items():
            mine = [t for t in trades if family in t['families']]
            n = len(mine); avg = sum(t['r'] for t in mine) / n if n else 0.0
            out[family] = {'id': family, 'label': label, 'trades': n, 'wins': sum(1 for t in mine if t['r'] > 0), 'avg_r': round(avg, 2),
                           'net': str(sum((number(t['pnl']) for t in mine), number(0))), 'paused': n >= 15 and avg < -0.15}
        return out

    def stats(self):
        trades = self.closed(); n = len(trades); wins = sum(1 for t in trades if t['r'] > 0)
        return {'trades': n, 'wins': wins, 'net': str(sum((number(t['pnl']) for t in trades), number(0))),
                'win_rate': round(100 * wins / n, 1) if n else None, 'avg_r': round(sum(t['r'] for t in trades) / n, 2) if n else None}

    def risk_fraction(self, profile):
        """Risk per trade: the profile's start value, then its Kelly fraction of the AI's own record (TradingCalc kelly_frontier)."""
        trades = self.closed(); cap = float(profile['risk_cap'])
        if len(trades) < 20:
            return float(profile['risk']), 'induló tét: a számla ' + share(float(profile['risk'])) + '-a ügyletenként (20 lezárt ügylet után a saját eredményeiből számol)'
        wins = [t['r'] for t in trades if t['r'] > 0]; losses = [-t['r'] for t in trades if t['r'] <= 0]
        p = len(wins) / len(trades)
        if not wins or not losses:
            return float(profile['risk']), 'még nincs elég nyerő és vesztes ügylet a Kelly-számításhoz'
        b = (sum(wins) / len(wins)) / max(1e-9, sum(losses) / len(losses))
        kelly = p - (1 - p) / b
        if kelly <= 0:
            return 0.0025, 'a saját eredményei szerint most nincs előnye (' + str(round(p * 100)) + '% találat), ezért a legkisebb téttel kereskedik'
        fraction = min(cap, max(0.0025, kelly * float(profile['kelly'])))
        return fraction, 'a saját eredményei alapján (' + str(round(p * 100)) + '% találat, nyerő/vesztő arány ' + ('%.2f' % b).replace('.', ',') + \
            ') a teljes Kelly ' + str(round(float(profile['kelly']) * 100)) + '%-a: ' + share(fraction, 2) + ' ügyletenként'

    def size(self, equity, stop, profile, max_leverage, gross, risk, side):
        """Dollar size from the risk, capped by the profile's leverage, the room left and a liquidation 3 stops away."""
        mmr = 1 / (2 * max(1, max_leverage))
        safe = 1 / (LIQ_BUFFER * stop * (1 + mmr) + mmr)
        notional = min(equity * risk / (stop + float(COST)), min(profile['leverage'], safe) * equity, max(0.0, profile['gross'] * equity - gross))
        leverage = notional / equity if equity > 0 else 0
        return max(0.0, notional), {'leverage': round(leverage, 2), 'risk_usd': round(equity * risk, 2),
                                    'liquidation_distance': round(liq_distance(leverage, mmr, side), 4) if leverage > 0 else None}

    def sample(self, now, equity):
        last = self.db.execute('SELECT MAX(at) FROM fast_equity').fetchone()[0]
        if not last or now.timestamp() - last >= 60:
            self.db.execute('INSERT OR REPLACE INTO fast_equity VALUES(?,?)', (now.timestamp(), str(equity)))

    def equity_curve(self, since, points=240):
        rows = self.db.execute('SELECT at,equity FROM fast_equity WHERE at>=? ORDER BY at', (since,)).fetchall()
        step = max(1, len(rows) // points)
        return [[int(at * 1000), round(float(e), 2)] for at, e in rows[::step]] + ([[int(rows[-1][0] * 1000), round(float(rows[-1][1]), 2)]] if rows and (len(rows) - 1) % step else [])

    def journal(self, limit=30):
        rows = self.db.execute('SELECT id,symbol,direction,opened_at,closed_at,entry,exit,notional,risk_usd,pnl,r,families,reasons,exit_reason,score '
                               'FROM fast_trades ORDER BY opened_at DESC LIMIT ?', (limit,)).fetchall()
        keys = ('id', 'symbol', 'direction', 'opened_at', 'closed_at', 'entry', 'exit', 'notional', 'risk_usd', 'pnl', 'r', 'families', 'reasons', 'exit_reason', 'score')
        out = []
        for row in rows:
            item = dict(zip(keys, row)); item['families'] = json.loads(item['families']); item['reasons'] = json.loads(item['reasons'])
            out.append(item)
        return out

    def open_orders(self):
        keys = ('id', 'symbol', 'direction', 'price', 'unit', 'family', 'why', 'created_at', 'expires_at', 'status', 'max_leverage')
        return [dict(zip(keys, r)) for r in self.db.execute("SELECT * FROM fast_orders WHERE status='open' ORDER BY created_at")]

    def recent_orders(self, limit=12):
        keys = ('id', 'symbol', 'direction', 'price', 'unit', 'family', 'why', 'created_at', 'expires_at', 'status', 'max_leverage')
        return [dict(zip(keys, r)) for r in self.db.execute('SELECT * FROM fast_orders ORDER BY created_at DESC LIMIT ?', (limit,))]

    def _close(self, book, identifier, order, now, reason):
        position = book['positions'][identifier]
        exit_price = number(order['price']); quantity = number(position['quantity'])
        pnl = quantity * (exit_price - number(position['entry'])) - number(order['fee']) - number(position.get('entry_fee', '0'))
        risk = number(position.get('risk_usd') or '0')
        updated = apply_paper_orders(book, [order])
        self.db.execute('INSERT INTO fast_events VALUES(?,?,?,?)', (hashlib.sha256((now.isoformat() + identifier + reason).encode()).hexdigest(), now.timestamp(), 'CLOSE',
                                                                     json.dumps({'reason': reason, 'orders': [order], 'pnl': str(pnl)})))
        if position.get('trade_id'):
            self.db.execute('UPDATE fast_trades SET closed_at=?,exit=?,pnl=?,r=?,exit_reason=? WHERE id=?',
                            (now.isoformat(), str(exit_price), str(pnl), float(pnl / risk) if risk > 0 else 0.0, reason, position['trade_id']))
        return updated, {'kind': 'close', 'symbol': identifier.split(':')[3], 'reason': reason, 'pnl': str(pnl)}

    def _exit(self, identifier, position, quotes, now, daily_block, setups):
        """(reason, order) when the position should close now, else None."""
        bid, ask = validate_quote(quotes[identifier], now)
        quantity = number(position['quantity']); entry = number(position['entry']); side = 1 if quantity > 0 else -1
        fast = position.get('strategy') == 'fast'
        stop = number(str(position.get('stop', LEGACY['stop']))); take = number(str(position.get('take', LEGACY['take'])))
        age = (now - stamp(position['opened_at'])).total_seconds()
        limit = float(position.get('seconds', HOLD if fast else LEGACY['seconds']))
        market = lambda reason: (reason, close_orders({'positions': {identifier: position}}, quotes, now)[0])
        symbol = identifier.split(':')[3]
        if daily_block: return market('Napi veszteségkorlát elérve')
        if (side > 0 and bid <= entry * (1 - stop)) or (side < 0 and ask >= entry * (1 + stop)): return market('Veszteségkorlát')
        target = entry * (1 + take * side)
        # The take-profit rests as a limit order: it fills when the price trades through it, at the target and the maker fee.
        if fast and ((side > 0 and bid > target) or (side < 0 and ask < target)): return ('Nyereségcél (limitáron)', limit_exit(identifier, position, target))
        if not fast and ((side > 0 and bid >= target) or (side < 0 and ask <= target)): return market('Nyereségcél')
        if age >= limit: return market('Lejárt a tartási idő (' + str(int(limit // 60)) + ' perc)')
        if fast and any(s['symbol'] == symbol and s['family'] == 'news' and s['direction'] == -side for s in setups):
            return market('Ellentétes friss hír')
        return None

    def _open(self, book, order, price, now, equity, gross, profile, risk, lots):
        """A filled limit order becomes a position, sized from the risk at fill time."""
        symbol, side = order['symbol'], order['direction']; identifier = 'hyperliquid:default:perpetual:' + symbol + ':USDC'
        stop = min(MAX_STOP, max(MIN_STOP, STOP_UNITS * order['unit'])); take = TAKE_UNITS / STOP_UNITS * stop
        notional, info = self.size(float(equity), stop, profile, int(order['max_leverage'] or 3), gross, risk, side)
        lot = number((lots or {}).get(symbol, '0'))
        if lot <= 0: raise ValueError('Hibás kereskedési lépésköz: ' + symbol)
        quantity = (number(str(notional)) / price / lot).to_integral_value(rounding=ROUND_DOWN) * lot * side
        if notional < 50 or quantity == 0: return book, None
        fee = abs(quantity) * price * MAKER_FEE
        fill = {'instrument': identifier, 'delta': str(quantity), 'price': str(price), 'fee': str(fee),
                'transition': 'nyitás', 'side': 'buy' if side > 0 else 'sell', 'target': str(quantity)}
        book = apply_paper_orders(book, [fill])
        reasons = [FAMILIES[order['family']] + ': ' + order['why']]
        book['positions'][identifier].update(strategy='fast', trade_id=order['id'], opened_at=now.isoformat(), entry_fee=str(fee), stop=str(stop),
                                             take=str(take), seconds=HOLD, risk_usd=str(info['risk_usd']), leverage=info['leverage'],
                                             families=[order['family']], reasons=reasons)
        self.db.execute('INSERT OR REPLACE INTO fast_trades(id,symbol,direction,opened_at,entry,notional,risk_usd,families,reasons,score) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (order['id'], symbol, side, now.isoformat(), str(price), str(abs(quantity) * price), str(info['risk_usd']),
                         json.dumps([order['family']]), json.dumps(reasons, ensure_ascii=False), 0))
        self.db.execute('INSERT OR REPLACE INTO fast_events VALUES(?,?,?,?)', (order['id'], now.timestamp(), 'OPEN', json.dumps({'symbol': symbol, 'orders': [fill]})))
        return book, {'kind': 'open', 'symbol': symbol, 'direction': side, 'notional': str(abs(quantity) * price), 'price': str(price)}

    def step(self, now, quotes, setups=(), settings=None, lots=None):
        """Exits first, then fills or expiry of the resting limit orders, then new orders for fresh setups."""
        if isinstance(now, str): now = stamp(now)
        settings = settings_from(settings or {}); profile = PROFILES[settings['profile']]
        self.db.execute('BEGIN IMMEDIATE')
        try:
            book = self.ledger.book()
            usable = set()
            for identifier, position in book['positions'].items():
                if position.get('strategy') not in ('fast', 'research', 'news_ai'): raise ValueError('A Gyors AI nem kezel más módhoz tartozó pozíciót.')
                try: validate_quote(quotes[identifier], now); usable.add(identifier)
                except (KeyError, ValueError): pass
            # One missing quote must not stop the exits of the others; only new orders wait for a full valuation.
            complete = len(usable) == len(book['positions'])
            equity = paper_equity({'settled': book['settled'], 'positions': {i: book['positions'][i] for i in usable}}, quotes)
            day = now.date().isoformat()
            self.db.execute('INSERT OR IGNORE INTO fast_days VALUES(?,?)', (day, str(equity)))
            baseline = number(self.db.execute('SELECT starting_equity FROM fast_days WHERE day=?', (day,)).fetchone()[0])
            daily_block = complete and (equity <= baseline * (1 - number(profile['daily_loss'])) or equity <= 0)
            events, skipped = [], []
            for identifier in [i for i in book['positions'] if i in usable]:
                found = self._exit(identifier, book['positions'][identifier], quotes, now, daily_block, setups)
                if found:
                    book, event = self._close(book, identifier, found[1], now, found[0]); events.append(event)
            risk, basis = self.risk_fraction(profile)
            stats = self.family_stats()
            # Resting limit orders: filled when the price trades through them, cancelled when they expire or the day is lost.
            for order in self.open_orders():
                identifier = 'hyperliquid:default:perpetual:' + order['symbol'] + ':USDC'; price = number(order['price']); side = order['direction']
                if daily_block or now >= stamp(order['expires_at']) or not settings['families'].get(order['family'], True):
                    self.db.execute("UPDATE fast_orders SET status=? WHERE id=?", ('cancelled' if daily_block else 'expired', order['id']))
                    events.append({'kind': 'expired', 'symbol': order['symbol']}); continue
                quote = quotes.get(identifier)
                if not quote or not complete: continue
                bid, ask = validate_quote(quote, now)
                if (side > 0 and (bid < price or ask <= price)) or (side < 0 and (ask > price or bid >= price)):
                    gross = sum(float(abs(number(p['quantity'])) * number(p['entry'])) for p in book['positions'].values())
                    equity = paper_equity(book, quotes)
                    book, event = self._open(book, order, price, now, equity, gross, profile, risk, lots)
                    self.db.execute("UPDATE fast_orders SET status=? WHERE id=?", ('filled' if event else 'skipped', order['id']))
                    if event: events.append(event)
                    else: skipped.append({'symbol': order['symbol'], 'reason': 'Elfogyott a profil kockázati kerete'})
            held = {i.split(':')[3]: (1 if number(p['quantity']) > 0 else -1) for i, p in book['positions'].items()}
            waiting = {o['symbol'] for o in self.open_orders()}
            for setup in setups:
                symbol, side = setup['symbol'], setup['direction']
                if symbol in held or symbol in waiting or not settings['families'].get(setup['family'], True): continue
                if stats[setup['family']]['paused']:
                    skipped.append({'symbol': symbol, 'reason': FAMILIES[setup['family']] + ': szünetel, mert 15 ügylet után veszteséges volt'}); continue
                if daily_block: skipped.append({'symbol': symbol, 'reason': 'Napi veszteségkorlát: ma nem nyit új ügyletet'}); break
                if not complete: skipped.append({'symbol': symbol, 'reason': 'Egy nyitott ügylet friss ára hiányzik'}); break
                if len(held) + len(waiting) >= profile['positions']:
                    skipped.append({'symbol': symbol, 'reason': 'Már ' + str(profile['positions']) + ' ügylet vagy megbízás él (a profil korlátja)'}); break
                # One market direction at a time: no long ETH against a short BTC.
                if held and any(d != side for d in held.values()):
                    skipped.append({'symbol': symbol, 'reason': 'A nyitott ügyletekkel ellentétes irány'}); continue
                recent = self.db.execute('SELECT MAX(closed_at) FROM fast_trades WHERE symbol=?', (symbol,)).fetchone()[0]
                if recent and (now - stamp(recent)).total_seconds() < COOLDOWN:
                    skipped.append({'symbol': symbol, 'reason': 'Nemrég zárt rajta ügyletet: 10 perc szünet'}); continue
                identifier = 'hyperliquid:default:perpetual:' + symbol + ':USDC'
                if identifier not in quotes: skipped.append({'symbol': symbol, 'reason': 'Nincs friss ár'}); continue
                bid, ask = validate_quote(quotes[identifier], now)
                if (ask - bid) / ((ask + bid) / 2) > MAX_SPREAD: skipped.append({'symbol': symbol, 'reason': 'Túl nagy a vételi–eladási árkülönbség'}); continue
                # Always a resting order: never above the bid when buying, never below the ask when selling.
                limit = number(str(setup['limit'])) if setup.get('limit') else (bid if side > 0 else ask)
                limit = min(limit, bid) if side > 0 else max(limit, ask)
                order_id = hashlib.sha256((symbol + now.isoformat() + setup['family']).encode()).hexdigest()[:16]
                expires = now.timestamp() + ORDER_LIFE.get(setup['family'], 60)
                self.db.execute('INSERT INTO fast_orders VALUES(?,?,?,?,?,?,?,?,?,?,?)', (order_id, symbol, side, str(limit), float(setup['unit']), setup['family'], setup['why'],
                                now.isoformat(), datetime.fromtimestamp(expires, timezone.utc).isoformat(), 'open', int(setup.get('max_leverage') or 3)))
                waiting.add(symbol); events.append({'kind': 'order', 'symbol': symbol, 'direction': side, 'price': str(limit)})
            self.db.execute('UPDATE book SET payload=? WHERE id=1', (json.dumps(book),))
            if complete: self.sample(now, paper_equity(book, {i: quotes[i] for i in book['positions']}))
            self.db.execute('COMMIT')
            return {'events': events, 'skipped': skipped, 'daily_block': daily_block, 'risk': risk, 'risk_basis': basis}
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def close(self): self.ledger.close()


def journal_closes(connection, book, orders, now, reason):
    """Closes made outside the engine (the stop button) still land in the fast-trade journal with their result."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fast_trades'").fetchone(): return
    for order in orders:
        position = book['positions'].get(order['instrument']) or {}
        if not position.get('trade_id'): continue
        quantity, exit_price = number(position['quantity']), number(order['price'])
        pnl = quantity * (exit_price - number(position['entry'])) - number(order['fee']) - number(position.get('entry_fee', '0'))
        risk = number(position.get('risk_usd') or '0')
        connection.execute('UPDATE fast_trades SET closed_at=?,exit=?,pnl=?,r=?,exit_reason=? WHERE id=? AND closed_at IS NULL',
                           (now.isoformat(), str(exit_price), str(pnl), float(pnl / risk) if risk > 0 else 0.0, reason, position['trade_id']))
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fast_orders'").fetchone():
        connection.execute("UPDATE fast_orders SET status='cancelled' WHERE status='open'")
