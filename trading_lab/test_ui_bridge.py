import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import ui_bridge


class BridgeTests(unittest.TestCase):
    def test_invalid_asset_cannot_invoke_model(self):
        with patch("ui_bridge.local_analysis") as model:
            with self.assertRaises(ValueError):
                ui_bridge.dispatch({"action": "analyze", "symbol": ";rm", "news": "test"})
            model.assert_not_called()

    def test_empty_or_long_news_cannot_invoke_model(self):
        for text in ("", "x" * 12001):
            with patch("ui_bridge.local_analysis") as model:
                with self.assertRaises(ValueError):
                    ui_bridge.dispatch({"action": "analyze", "symbol": "DEMO-A", "news": text})
                model.assert_not_called()

    def test_annotation_is_stored_locally_and_no_order_exists(self):
        annotation = {"impact": "uncertain", "novel": False, "evidence": "No confirmed event."}
        with tempfile.TemporaryDirectory() as directory:
            with patch("ui_bridge.ROOT", Path(directory)), patch("ui_bridge.local_analysis", return_value=annotation):
                result = ui_bridge.dispatch({"action": "analyze", "symbol": "demo-a", "news": "sample"})
                self.assertTrue(result["ok"])
                self.assertTrue((Path(directory) / "data/research.sqlite").is_file())
                self.assertNotIn("order", result)

    def test_unknown_actions_are_rejected(self):
        with self.assertRaises(ValueError):
            ui_bridge.dispatch({"action": "live_buy"})

    def test_status_distinguishes_missing_model(self):
        with patch("ui_bridge.api_get", side_effect=[{"version": "test"}, {"models": []}, {"models": []}]):
            self.assertFalse(ui_bridge.status()["model_installed"])

    def test_paper_copy_cannot_start_without_public_trader_address(self):
        with patch("ui_bridge.subprocess.run") as processes:
            with self.assertRaises(ValueError):
                ui_bridge.dispatch({"action": "paper_start", "symbol": ""})
            processes.assert_not_called()

    def test_balance_is_labelled_virtual_and_never_uses_synthetic_demo_as_live_money(self):
        with tempfile.TemporaryDirectory() as directory, patch("ui_bridge.ROOT", Path(directory)):
            reports = Path(directory) / "reports"
            reports.mkdir()
            (reports / "copy-demo.json").write_text(json.dumps({"final_book": {"settled": "9990.25", "positions": {}}}))
            summary = ui_bridge.portfolio_summary()
            self.assertEqual(summary["equity"], "10000")
            self.assertEqual(summary["change"], "0")
            self.assertFalse(summary["real_account_connected"])
            self.assertEqual(summary["source"], "virtual_empty")

    def test_missing_following_price_never_shows_demo_money_as_current(self):
        with tempfile.TemporaryDirectory() as directory, patch("ui_bridge.ROOT", Path(directory)):
            reports = Path(directory) / "reports"
            reports.mkdir()
            (reports / "paper-copy-state.json").write_text(json.dumps({"error": "unavailable"}))
            (reports / "copy-demo.json").write_text(json.dumps({"final_book": {"settled": "12000", "positions": {}}}))
            summary = ui_bridge.portfolio_summary()
            self.assertIsNone(summary["equity"])
            self.assertIsNone(summary["change"])
            self.assertEqual(summary["source"], "paper_follow")

    def test_risk_settings_cannot_enable_unbounded_leverage(self):
        with tempfile.TemporaryDirectory() as directory, patch("ui_bridge.ROOT", Path(directory)):
            with self.assertRaises(ValueError):
                ui_bridge.dispatch({"action": "save_risk", "news": json.dumps({"max_position_percent": "200", "max_gross_percent": "1000"})})
            self.assertFalse((Path(directory) / "paper-risk.json").exists())
            result = ui_bridge.dispatch({"action": "save_risk", "news": json.dumps({"max_position_percent": "25", "max_gross_percent": "75"})})
            self.assertEqual(result["max_position_percent"], "25")

    def test_monitor_stop_waits_for_transient_launchd_registration(self):
        with tempfile.TemporaryDirectory() as directory, patch('ui_bridge.Path.home', return_value=Path(directory)), patch('ui_bridge.job_running',side_effect=[True,True,False]) as running, patch('ui_bridge.subprocess.run') as process, patch('ui_bridge.time.sleep') as sleep:
            self.assertTrue(ui_bridge.monitor_control(False)['ok'])
            self.assertEqual(running.call_count,3)
            process.assert_called_once();sleep.assert_called_once_with(0.1)


if __name__ == "__main__":
    unittest.main()
