import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from agent import number
from continuous_data import assess_trader, verify_candidate
from copy_trading import PaperCopyLedger, apply_paper_orders
from test_continuous_data import ADDRESS, NOW, histories
import watch_copy

OTHER = '0x' + '2' * 40
STATE = {'time': int(NOW.timestamp() * 1000), 'marginSummary': {'accountValue': '100000'}, 'assetPositions': []}


def ranking(root, rows, at=NOW):
    (root / 'reports').mkdir(parents=True, exist_ok=True)
    (root / 'reports/trader-candidates.json').write_text(json.dumps({'updated_at': at.isoformat(), 'candidates': rows}))


class BestTraderTests(unittest.TestCase):
    def test_steady_copyable_traders_rank_first(self):
        # A trader who turns the account over 100x a month trades faster than a 5 s follower can copy.
        with self.assertRaisesRegex(ValueError, 'Túl gyors'):
            verify_candidate({'address': ADDRESS, 'name': 'Gyors', 'turnover': 100}, histories(), STATE, NOW)
        calm = verify_candidate({'address': ADDRESS, 'name': 'Nyugodt', 'turnover': 10}, histories(), STATE, NOW)
        busy = verify_candidate({'address': ADDRESS, 'name': 'Sürgős', 'turnover': 50}, histories(), STATE, NOW)
        self.assertGreater(float(calm['score']), float(busy['score']))
        self.assertEqual((float(calm['consistency_percent']), float(calm['copyable_percent'])), (100.0, 100.0))
        jumpy = histories(); curve = jumpy[0][1]['pnlHistory']
        for i in range(1, 31, 2): curve[i][1] = str(int(curve[i - 1][1]) - 50)  # every other day a loss, same end result
        uneven = verify_candidate({'address': ADDRESS, 'name': 'Hullámzó', 'turnover': 10}, jumpy, STATE, NOW)
        self.assertLess(float(uneven['score']), float(calm['score']), 'an uneven curve scores lower')

    def test_any_public_address_can_be_checked_before_copying(self):
        # The owner can name an outside account: the same checks as the ranking, reported instead of silently rejected.
        def info(payload):
            return histories() if payload['type'] == 'portfolio' else dict(STATE, assetPositions=[{'position': {'coin': 'BTC', 'szi': '-0.5', 'positionValue': '30000', 'unrealizedPnl': '120'}}])
        report = assess_trader(ADDRESS.upper().replace('0X', '0x'), NOW, info)
        self.assertTrue(report['ranked']); self.assertEqual(report['positions'][0]['direction'], 'short')
        self.assertEqual(float(report['return_percent']), 3.0); self.assertTrue(all(c['ok'] for c in report['checks']))
        risky = lambda p: histories() if p['type'] == 'portfolio' else dict(STATE, assetPositions=[{'position': {'coin': 'BTC', 'szi': '2', 'positionValue': '150000'}}])
        report = assess_trader(ADDRESS, NOW, risky)
        self.assertFalse(report['ranked']); self.assertIn('kitettség', report['reason'])
        with self.assertRaisesRegex(ValueError, 'Privát kulcsot'): assess_trader('0x123', NOW, info)

    def test_the_follower_switches_only_to_a_clearly_better_trader(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); config = {'address': ADDRESS, 'auto_best': True, 'since': (NOW - timedelta(days=2)).isoformat()}
            ranking(root, [{'address': ADDRESS, 'name': 'A', 'score': '5'}, {'address': OTHER, 'name': 'B', 'score': '6'}])
            self.assertIsNone(watch_copy.best_switch(config, NOW, root), '20% better is not enough to churn')
            ranking(root, [{'address': ADDRESS, 'name': 'A', 'score': '5'}, {'address': OTHER, 'name': 'B', 'score': '7'}])
            self.assertEqual(watch_copy.best_switch(config, NOW, root)['address'], OTHER)
            self.assertIsNone(watch_copy.best_switch(dict(config, since=(NOW - timedelta(hours=3)).isoformat()), NOW, root), 'not within the first day')
            ranking(root, [{'address': OTHER, 'name': 'B', 'score': '3'}])
            self.assertIsNone(watch_copy.best_switch(dict(config, since=(NOW - timedelta(hours=3)).isoformat()), NOW, root), 'a dropped trader gets 6 hours')
            self.assertEqual(watch_copy.best_switch(dict(config, since=(NOW - timedelta(hours=7)).isoformat()), NOW, root)['address'], OTHER)
            ranking(root, [{'address': OTHER, 'name': 'B', 'score': '9'}], at=NOW - timedelta(hours=3))
            self.assertIsNone(watch_copy.best_switch(config, NOW, root), 'an old ranking never moves money, even virtual')

    def test_a_switch_closes_virtually_and_follows_from_a_flat_book(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); ledger = PaperCopyLedger(root / 'paper.sqlite')
            book = ledger.book(); book['leader'] = ADDRESS
            book = apply_paper_orders(book, [{'instrument': 'hyperliquid:default:perpetual:BTC:USDC', 'delta': '0.01', 'price': '60000', 'fee': '0.3', 'transition': 'nyitás', 'side': 'buy', 'target': '0.01'}])
            ledger.connection.execute('UPDATE book SET payload=? WHERE id=1', (json.dumps(book),)); ledger.connection.commit()
            (root / 'portfolio-account.json').write_text(json.dumps({'mode': 'copy', 'leader': ADDRESS, 'database': 'paper.sqlite'}))
            quote = lambda symbol: {'bid': '60100', 'ask': '60101', 'at': NOW.isoformat(), 'instrument': symbol}
            config, orders = watch_copy.switch_leader(ledger, {'address': ADDRESS, 'auto_best': True}, {'address': OTHER}, NOW, quote, root)
            after = ledger.book(); ledger.close()
            self.assertEqual((after['positions'], after['leader'], len(orders)), ({}, None, 1))
            self.assertEqual((config['address'], config['previous']), (OTHER, ADDRESS))
            self.assertEqual(json.loads((root / 'paper-copy-config.json').read_text())['address'], OTHER)
            self.assertEqual(json.loads((root / 'portfolio-account.json').read_text())['leader'], OTHER)
            self.assertGreater(number(after['settled']), number('10000'), 'the closed position kept its gain')


if __name__ == '__main__':
    unittest.main()
