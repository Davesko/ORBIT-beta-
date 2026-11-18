import unittest
import json
from datetime import datetime, timezone, timedelta
from fast_ai import (COST, FAMILIES, MAKER_FEE, PROFILES, FastPaper, journal_closes, close_orders, liq_distance, market_view, news_setup,
                     retest_setup, settings_from, signal_for)
from agent import number

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)
BTC = 'hyperliquid:default:perpetual:BTC:USDC'
SOL = 'hyperliquid:default:perpetual:SOL:USDC'
LOTS = {'BTC': '0.00001', 'SOL': '0.01', 'ETH': '0.0001'}
RULE = {'family': 'momentum', 'window': 4, 'threshold': 0.01, 'stop': 0.015, 'hold': 4, 'bar': '15m'}
STEP = 15 * 60000


def quote(price='60000', now=NOW, spread=1):
    return {'bid': price, 'ask': str(number(price) + number(str(spread))), 'at': now.isoformat()}


def minute_bars(closes, end_ms=NOW_MS, volumes=None):
    start = end_ms - len(closes) * 60000
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append({'t': start + i * 60000, 'T': start + (i + 1) * 60000 - 1, 'o': o, 'h': max(o, c) * 1.0003, 'l': min(o, c) * 0.9997, 'c': c,
                    'v': (volumes[i] if volumes else 100.0)})
    return out


def setup(symbol='BTC', direction=1, limit=None, family='retest', unit=0.0028):
    return {'symbol': symbol, 'direction': direction, 'limit': limit, 'family': family, 'unit': unit, 'max_leverage': 40 if symbol == 'BTC' else 20,
            'why': 'emelkedő trendben áttörte az 1 órás csúcsot'}


class DesignTests(unittest.TestCase):
    def test_sizing_matches_the_tradingcalc_design(self):
        # TradingCalc risk_reward, 2 Nov 2026: 10 000 $, 1% risk, entry 78 000, stop 0.7% lower, 0.015% limit entry and
        # 0.075% market stop (fee + slippage) -> 12 666.65 $ notional.
        engine = FastPaper(':memory:'); self.addCleanup(engine.close)
        notional, info = engine.size(10000.0, 0.007, PROFILES['normal'], 40, 0.0, 0.01, 1)
        self.assertAlmostEqual(notional, 12666.65, delta=12666.65 * 0.002)
        self.assertEqual(info['risk_usd'], 100.0)
        # TradingCalc breakeven_planning: a limit entry and a limit take-profit cost 0.030% together (0.2% before).
        self.assertAlmostEqual(float(2 * MAKER_FEE), 0.0003); self.assertAlmostEqual(float(COST), 0.0009)

    def test_liquidation_distance_matches_tradingcalc(self):
        # TradingCalc liquidation_safety: 5x BTC long at 1.25% maintenance -> 63 227.95 from 78 047; 10x SOL short at 5% -> 98.6176 from 94.135.
        self.assertAlmostEqual(liq_distance(5, 0.0125, 1), 1 - 63227.94936708861 / 78047, places=6)
        self.assertAlmostEqual(liq_distance(10, 0.05, -1), 98.61761904761906 / 94.135 - 1, places=6)

    def test_leverage_stays_under_the_profile_and_three_stops_from_liquidation(self):
        engine = FastPaper(':memory:'); self.addCleanup(engine.close)
        notional, info = engine.size(10000.0, 0.03, PROFILES['meresz'], 3, 0.0, 0.03, -1)
        self.assertGreaterEqual(info['liquidation_distance'], 3 * 0.03 - 1e-9)
        self.assertLessEqual(engine.size(10000.0, 0.004, PROFILES['ovatos'], 40, 0.0, 0.01, 1)[1]['leverage'], 2)
        self.assertAlmostEqual(engine.size(10000.0, 0.007, PROFILES['normal'], 40, 39000.0, 0.01, 1)[0], 1000.0, msg='only the room left under 4x gross')

    def test_settings_are_validated(self):
        self.assertEqual(settings_from({})['families'], {f: True for f in FAMILIES})
        self.assertEqual(settings_from({'families': {'breakout': False}})['families']['retest'], True, 'old keys are ignored')
        with self.assertRaises(ValueError): settings_from({'profile': 'all-in'})
        with self.assertRaises(ValueError): settings_from({'families': {f: False for f in FAMILIES}})
        with self.assertRaises(ValueError): settings_from({'coins': 50})


class SetupTests(unittest.TestCase):
    def rising(self, last=None, volume=100.0):
        closes = [100 * (1 + 0.0002 * i) for i in range(299)] + [last or 100 * (1 + 0.0002 * 299)]
        return minute_bars(closes, volumes=[100.0] * 299 + [volume])

    def test_the_hour_trend_and_the_typical_move(self):
        view = market_view(self.rising(), NOW_MS)
        self.assertEqual(view['trend'], 1); self.assertGreater(view['unit'], 0)
        falling = minute_bars([100 * (1 - 0.0002 * i) for i in range(300)])
        self.assertEqual(market_view(falling, NOW_MS)['trend'], -1)
        self.assertIsNone(market_view(self.rising()[:200], NOW_MS), 'too little history')

    def test_a_breakout_in_the_trend_waits_for_its_retest(self):
        bars = self.rising(last=106.8, volume=300)
        found = retest_setup(market_view(bars, NOW_MS), NOW_MS)
        prior_high = max(b['h'] for b in bars[-61:-1])
        self.assertEqual((found['direction'], found['limit']), (1, prior_high))
        self.assertIn('3,0× forgalommal', found['why'])
        self.assertIsNone(retest_setup(market_view(self.rising(last=106.8), NOW_MS), NOW_MS), 'no volume, no setup')
        self.assertIsNone(retest_setup(market_view(bars, NOW_MS + 90000), NOW_MS + 90000), 'only on the bar that just closed')
        flat = minute_bars([100.0] * 299 + [101.0], volumes=[100.0] * 299 + [300])
        self.assertIsNone(retest_setup(market_view(flat, NOW_MS), NOW_MS), 'no trend, no trade')

    def test_fresh_confirmed_news_in_the_trend(self):
        view = market_view(self.rising(), NOW_MS)
        published = NOW - timedelta(minutes=2)
        then = next(b['o'] for b in view['closed'] if b['t'] <= int(published.timestamp() * 1000) <= b['T'])
        view = dict(view, last=then * 1.002)
        item = {'source': 'Watcher Guru', 'group': 'x', 'title': 'SEC approves ETF', 'assets': ['BTC'], 'published_at': published.isoformat(),
                'reading': {'impact': 'positive', 'strength': 0.65, 'by': 'quick'}}
        found = news_setup('BTC', [item], view, NOW)
        self.assertEqual((found['family'], found['direction'], found['limit']), ('news', 1, None))
        self.assertIsNone(news_setup('BTC', [dict(item, reading=dict(item['reading'], impact='negative'))], view, NOW), 'against the trend')
        self.assertIsNone(news_setup('BTC', [item], dict(view, last=then * 1.03), NOW), 'the move is already over')
        self.assertIsNone(news_setup('BTC', [dict(item, published_at=(NOW - timedelta(minutes=5)).isoformat())], view, NOW), 'too old for a fast trade')
        self.assertIsNone(news_setup('BTC', [dict(item, group='portal', reading=dict(item['reading'], strength=0.5))], view, NOW), 'weak reading')

    def test_the_research_rule_is_still_read(self):
        bars = [{'t': NOW_MS - (5 - i) * STEP, 'T': NOW_MS - (4 - i) * STEP - 1, 'c': c} for i, c in enumerate([100, 100.2, 100.5, 100.8, 101.2])]
        self.assertEqual(signal_for(RULE, bars, NOW_MS)['direction'], 1)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = FastPaper(':memory:')

    def tearDown(self): self.engine.close()

    def at(self, seconds): return NOW + timedelta(seconds=seconds)

    def order_and_fill(self, engine=None, settings=None):
        engine = engine or self.engine
        engine.step(NOW, {BTC: quote('60010')}, [setup(limit='60000')], settings or {}, LOTS)
        t = self.at(6)
        return engine.step(t, {BTC: quote('59990', t)}, [], settings or {}, LOTS)

    def test_a_setup_becomes_a_resting_limit_order_that_fills_only_on_a_retest(self):
        result = self.engine.step(NOW, {BTC: quote('60100')}, [setup(limit='60000')], {}, LOTS)
        self.assertEqual(result['events'], [{'kind': 'order', 'symbol': 'BTC', 'direction': 1, 'price': '60000'}])
        t = self.at(3); self.engine.step(t, {BTC: quote('60050', t)}, [], {}, LOTS)
        self.assertFalse(self.engine.ledger.book()['positions'], 'the price has not come back yet')
        t = self.at(6); result = self.engine.step(t, {BTC: quote('59995', t)}, [], {}, LOTS)
        self.assertEqual(result['events'][0]['kind'], 'open')
        position = self.engine.ledger.book()['positions'][BTC]
        self.assertEqual((position['entry'], position['strategy']), ('60000', 'fast'))
        self.assertAlmostEqual(float(position['stop']), 0.007); self.assertAlmostEqual(float(position['take']), 0.0042)
        self.assertAlmostEqual(float(position['entry_fee']), abs(float(position['quantity'])) * 60000 * 0.00015, msg='maker fee')

    def test_a_limit_is_never_placed_above_the_bid(self):
        self.engine.step(NOW, {BTC: quote('59900')}, [setup(limit='60000')], {}, LOTS)
        self.assertEqual(self.engine.open_orders()[0]['price'], '59900')
        self.engine.step(NOW, {BTC: quote('59900'), SOL: quote('150', spread='0.02')}, [setup('SOL', 1, limit=None)], {}, LOTS)
        self.assertEqual(next(o for o in self.engine.open_orders() if o['symbol'] == 'SOL')['price'], '150', 'a buy joins the bid')

    def test_an_unfilled_order_expires(self):
        self.engine.step(NOW, {BTC: quote('60100')}, [setup(limit='60000')], {}, LOTS)
        t = self.at(301); result = self.engine.step(t, {BTC: quote('59000', t)}, [], {}, LOTS)
        self.assertEqual(result['events'], [{'kind': 'expired', 'symbol': 'BTC'}]); self.assertFalse(self.engine.ledger.book()['positions'])

    def test_take_profit_fills_at_the_limit_and_the_stop_at_market(self):
        self.order_and_fill()
        t = self.at(60); result = self.engine.step(t, {BTC: quote('60260', t)}, [], {}, LOTS)
        event = result['events'][0]
        self.assertEqual(event['reason'], 'Nyereségcél (limitáron)'); self.assertGreater(float(event['pnl']), 0)
        self.assertAlmostEqual(float(self.engine.journal()[0]['exit']), 60252.0)
        engine = FastPaper(':memory:'); self.addCleanup(engine.close); self.order_and_fill(engine)
        t = self.at(60); result = engine.step(t, {BTC: quote('59570', t)}, [], {}, LOTS)
        self.assertEqual(result['events'][0]['reason'], 'Veszteségkorlát'); self.assertAlmostEqual(engine.journal()[0]['r'], -1.0, delta=0.15)

    def test_time_limit_and_contrary_news_close(self):
        self.order_and_fill(); t = self.at(90 * 60 + 10)
        self.assertIn('tartási idő', self.engine.step(t, {BTC: quote('60010', t)}, [], {}, LOTS)['events'][0]['reason'])
        engine = FastPaper(':memory:'); self.addCleanup(engine.close); self.order_and_fill(engine)
        t = self.at(30); result = engine.step(t, {BTC: quote('60010', t)}, [setup(direction=-1, family='news')], {}, LOTS)
        self.assertEqual(result['events'][0]['reason'], 'Ellentétes friss hír')

    def test_one_direction_limits_and_cooldown(self):
        self.order_and_fill(); t = self.at(10)
        quotes = {BTC: quote('60000', t), SOL: quote('150', t, '0.01')}
        self.assertIn('ellentétes irány', self.engine.step(t, quotes, [setup('SOL', -1)], {}, LOTS)['skipped'][0]['reason'])
        result = self.engine.step(t, quotes, [setup('SOL', 1, limit='149'), setup('ETH', 1)], {'profile': 'ovatos'}, LOTS)
        self.assertIn('profil korlátja', result['skipped'][0]['reason'])
        t = self.at(60); self.engine.step(t, {BTC: quote('59570', t), SOL: quote('150', t, '0.01')}, [], {'profile': 'ovatos'}, LOTS)
        t = self.at(120)
        result = self.engine.step(t, {BTC: quote('60000', t), SOL: quote('150', t, '0.01')}, [setup()], {'profile': 'ovatos'}, LOTS)
        self.assertIn('10 perc szünet', result['skipped'][0]['reason'])

    def test_daily_loss_closes_trades_and_cancels_orders(self):
        self.order_and_fill(); t = self.at(10)
        self.engine.step(t, {BTC: quote('60000', t), SOL: quote('150', t, '0.01')}, [setup('SOL', 1, limit='149')], {}, LOTS)
        self.engine.db.execute("UPDATE fast_days SET starting_equity='20000'")
        t = self.at(20); result = self.engine.step(t, {BTC: quote('60000', t), SOL: quote('150', t, '0.01')}, [], {}, LOTS)
        self.assertEqual([e.get('reason') or e['kind'] for e in result['events']], ['Napi veszteségkorlát elérve', 'expired'])
        self.assertFalse(self.engine.open_orders()); self.assertTrue(result['daily_block'])

    def test_a_missing_quote_does_not_stop_the_other_exits(self):
        # 2 Nov: quotes fetched after the round's clock looked like the future; every round failed and no exit was managed.
        book = self.engine.ledger.book()
        for identifier, entry, quantity in ((BTC, '60000', '0.1'), (SOL, '150', '10')):
            book['positions'][identifier] = {'quantity': quantity, 'entry': entry, 'strategy': 'fast', 'opened_at': NOW.isoformat(),
                                             'stop': '0.007', 'take': '0.0042', 'seconds': 5400, 'risk_usd': '100'}
        self.engine.db.execute('UPDATE book SET payload=? WHERE id=1', (json.dumps(book),))
        t = self.at(30); result = self.engine.step(t, {BTC: quote('59500', t)}, [setup('ETH')], {}, LOTS)
        self.assertEqual(result['events'][0]['reason'], 'Veszteségkorlát'); self.assertIn('friss ára hiányzik', result['skipped'][0]['reason'])
        self.assertIn(SOL, self.engine.ledger.book()['positions'])
        self.assertIsNotNone(self.engine.step(t, {SOL: quote('150', t + timedelta(seconds=1), '0.01')}, [], {}, LOTS), 'a quote a second ahead is fine')

    def test_the_stop_button_records_the_result_and_cancels_orders(self):
        self.order_and_fill(); t = self.at(10)
        self.engine.step(t, {BTC: quote('60000', t), SOL: quote('150', t, '0.01')}, [setup('SOL', 1, limit='149')], {}, LOTS)
        book = self.engine.ledger.book(); t = self.at(30)
        journal_closes(self.engine.db, book, close_orders(book, {BTC: quote('59800', t)}, t), t, 'Kézi lezárás')
        trade = self.engine.journal()[0]
        self.assertEqual(trade['exit_reason'], 'Kézi lezárás'); self.assertLess(float(trade['pnl']), 0); self.assertFalse(self.engine.open_orders())

    def test_a_losing_entry_kind_pauses(self):
        rows = [('t%d' % i, 'BTC', 1, NOW.isoformat(), NOW.isoformat(), '1', '1', '1', '100', '-100', -1.0, json.dumps(['retest']), '[]', 'x', 0) for i in range(15)]
        self.engine.db.executemany('INSERT INTO fast_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        self.assertTrue(self.engine.family_stats()['retest']['paused'])
        self.assertIn('szünetel', self.engine.step(NOW, {BTC: quote()}, [setup()], {}, LOTS)['skipped'][0]['reason'])

    def test_risk_follows_the_record_at_a_kelly_fraction(self):
        self.assertEqual(self.engine.risk_fraction(PROFILES['normal'])[0], 0.01)
        rows = [('t%d' % i, 'BTC', 1, NOW.isoformat(), NOW.isoformat(), '1', '1', '1', '100', '0', r, '[]', '[]', 'x', 0)
                for i, r in enumerate([2.0] * 12 + [-1.0] * 8)]
        self.engine.db.executemany('INSERT INTO fast_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        fraction, basis = self.engine.risk_fraction(PROFILES['normal'])
        self.assertEqual(fraction, 0.02); self.assertIn('Kelly', basis)

    def test_an_old_news_ai_position_keeps_its_exits(self):
        book = self.engine.ledger.book(); book['positions'][BTC] = {'quantity': '0.001', 'entry': '60000', 'strategy': 'news_ai', 'opened_at': NOW.isoformat()}
        self.engine.db.execute('UPDATE book SET payload=? WHERE id=1', (json.dumps(book),))
        late = self.at(181)
        self.assertIn('tartási idő', self.engine.step(late, {BTC: quote(now=late)}, [], {}, LOTS)['events'][0]['reason'])

    def test_the_worker_can_start(self):
        # 2 Nov: fast_ai.signal shadowed the signal module and the worker died at start, restarting every 30 s.
        import signal as module, watch_fast
        self.assertIs(watch_fast.signal, module)


if __name__ == '__main__': unittest.main()
