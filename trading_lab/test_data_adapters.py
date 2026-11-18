import json
import unittest
from unittest.mock import patch

import market_data
import quiver_data
from copy_trading import PaperCopyLedger
from watch_copy import cycle


class DataAdapterTests(unittest.TestCase):
    def test_order_actions_never_reach_public_data_endpoint(self):
        with patch("market_data.urllib.request.build_opener") as network:
            with self.assertRaises(ValueError):
                market_data.public_info({"type": "order"})
            network.assert_not_called()

    def test_private_keys_and_invalid_addresses_are_rejected(self):
        with patch("market_data.public_info") as network:
            with self.assertRaises(ValueError):
                market_data.public_trader_snapshot("private-key-not-a-public-address")
            network.assert_not_called()

    def test_empty_account_not_interpreted_as_exit_signal(self):
        with patch("market_data.public_info", return_value={"marginSummary": {"accountValue": "0"}, "assetPositions": []}):
            with self.assertRaises(ValueError):
                market_data.public_trader_snapshot("0x" + "1" * 40)

    def test_quotes_keep_instrument_identity(self):
        raw = {"coin": "BTC", "time": 1792317600000, "levels": [[{"px": "60000"}], [{"px": "60001"}]]}
        with patch("market_data.public_info", return_value=raw):
            quote = market_data.public_quote()
        self.assertEqual(quote["instrument"], "hyperliquid:default:perpetual:BTC:USDC")
        self.assertEqual(quote["bid"], "60000")

    def test_quiver_range_and_delay_cannot_be_exact_copy_signal(self):
        row = {"TransactionDate": "2026-09-01", "ReportDate": "2026-10-01", "Amount": "1001", "Range": "$1,001 - $15,000", "Ticker": "DEMO"}
        record = quiver_data.normalize_congress_record(row)
        self.assertEqual(record["disclosure_lag_days"], 30)
        self.assertFalse(record["exact_copy_eligible"])
        self.assertIsNone(record["exact_quantity"])
        self.assertEqual(record["reported_amount_lower_bound_usd"], "1001")

    def test_missing_quiver_key_never_calls_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("quiver_data.urllib.request.build_opener") as network:
            with self.assertRaises(ValueError):
                quiver_data.recent_congress()
            network.assert_not_called()

    def test_watcher_fetches_exit_quote_after_leader_has_closed(self):
        ledger = PaperCopyLedger()
        identifier = "hyperliquid:default:perpetual:BTC:USDC"
        book = ledger.book()
        book.update(leader="0x" + "1" * 40, scope="hyperliquid:perps:default", currency="USDC")
        book["positions"][identifier] = {"quantity": "0.01", "entry": "60000"}
        ledger.connection.execute("UPDATE book SET payload=? WHERE id=1", (json.dumps(book),))
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        incoming = {"snapshot": {"id": "closed", "leader": book["leader"], "scope": book["scope"], "currency": "USDC",
                                 "source_at": now, "source_class": "direct_positions", "complete": True,
                                 "equity": "100000", "positions": {}},
                    "quotes": {}, "instruments": {identifier: {"kind": "perpetual", "currency": "USDC", "step": "0.000001"}}}
        quote = {"instrument": identifier, "bid": "60000", "ask": "60001", "at": now}
        with patch("watch_copy.public_trader_snapshot", return_value=incoming), patch("watch_copy.public_quote", return_value=quote) as fetch:
            result = cycle(book["leader"], ledger)
            fetch.assert_called_once_with("BTC")
            self.assertFalse(result["book"]["positions"])
            self.assertEqual(result["plan"]["orders"][0]["transition"], "teljes zárás")
        ledger.close()

class SharedModelTests(unittest.TestCase):
    def test_millions_uses_the_model_loaded_on_orbits_ssd_server(self):
        # MiLLIONS's own server could not bind 11434 (the Ollama app holds it); every AI call got HTTP 404 there.
        import local_model
        from unittest.mock import patch, MagicMock
        def opener_for(models_by_port):
            def open_(url, timeout=None):
                port = int(url.split(':')[2].split('/')[0])
                if port not in models_by_port: raise OSError('connection refused')
                response = MagicMock(); response.__enter__.return_value = response
                response.read.return_value = json.dumps({"models": [{"name": n} for n in models_by_port[port]]}).encode()
                return response
            opener = MagicMock(); opener.open.side_effect = open_
            return opener
        local_model._found.clear()
        with patch('local_model.urllib.request.build_opener', return_value=opener_for({11434: [], 11435: ['qwen3.8:27b-q4_K_M', 'qwen3.5:9b']})):
            self.assertEqual(local_model.endpoint('qwen3.8:27b'), ('http://127.0.0.1:11435/api/chat', 'qwen3.8:27b-q4_K_M', local_model.SHARED_CONTEXT))
        local_model._found.clear()
        with patch('local_model.urllib.request.build_opener', return_value=opener_for({11434: ['qwen3.8:27b']})):
            self.assertEqual(local_model.endpoint('qwen3.8:27b'), ('http://127.0.0.1:11434/api/chat', 'qwen3.8:27b', 4096))
        local_model._found.clear()


if __name__ == "__main__":
    unittest.main()
