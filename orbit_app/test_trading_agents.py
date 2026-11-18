"""TradingAgents stays a research tool: local models, public data, its own environment, no project and no order."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trading_agents as ta
from studio import Studio


class TradingAgentsTool(unittest.TestCase):
    def setUp(self):
        language = patch('language_bridge.translate_many', side_effect=lambda texts, root: list(texts))
        language.start()
        self.addCleanup(language.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.s = Studio(Path(self.temp.name))

    def tearDown(self):
        self.s.db.close()
        self.temp.cleanup()

    def test_not_installed_means_no_run(self):
        self.assertFalse(ta.status(self.s)['installed'])
        with self.assertRaises(ValueError):
            ta.enqueue(self.s, 'NVDA')

    def test_only_a_ticker_is_accepted(self):
        for bad in ('', 'rm -rf /', 'NVDA; ls', 'x' * 20):
            with self.assertRaises(ValueError):
                ta.enqueue(self.s, bad)

    def test_research_only_and_local(self):
        runner = ta.RUNNER
        self.assertIn("llm_provider='ollama'", runner)
        self.assertIn("fundamental_data='yfinance'", runner)     # no SEC EDGAR contact address
        self.assertNotIn('broker', runner.lower())
        self.assertIn('nem befektetési tanács', ta.DISCLAIMER)
        self.assertTrue(ta.SOURCE.endswith('@' + ta.VERSION))   # pinned release

    def test_reports_are_read_by_id_only(self):
        with self.assertRaises(ValueError):
            ta.report(self.s, '../../etc/passwd')


    def test_the_small_model_is_picked_once_for_both_tiers(self):
        listing = [dict(name='gemma4:26b'), dict(name='qwen3.8:27b-q4_K_M'), dict(name='qwen3-embedding:0.6b'), dict(name='qwen3.5:9b')]
        with patch('model_hub.models', return_value=listing):
            self.assertEqual(ta.models(), ('qwen3.5:9b', 'qwen3.5:9b'))


if __name__ == '__main__':
    unittest.main()
