import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import Lab, local_analysis, number, run, validate_analysis


class LabTests(unittest.TestCase):
    def setUp(self):
        self.event = json.loads(Path(__file__).with_name("demo.json").read_text())["events"][0]
        self.analysis = self.event["demo_annotation"]

    def test_duplicate_cannot_buy_twice(self):
        lab = Lab()
        lab.process(self.event, self.analysis)
        cash = lab.cash
        self.assertEqual(lab.process(self.event, self.analysis)["reason"], "Duplicate event")
        self.assertEqual(cash, lab.cash)

    def test_invalid_quotes_do_not_mutate_state(self):
        for bad in ("NaN", "Infinity", "-1", True):
            with self.subTest(bad=bad):
                lab = Lab()
                event = {**self.event, "bid": bad}
                self.assertEqual(lab.process(event, self.analysis)["decision"], "REJECT")
                self.assertEqual(lab.cash, lab.limits.start_cash)
                self.assertFalse(lab.positions)

    def test_stale_and_future_news_are_held(self):
        for date in ("2026-10-16T11:00:00Z", "2026-10-16T13:00:00Z"):
            event = {**self.event, "published_at": date}
            lab = Lab()
            self.assertEqual(lab.process(event, self.analysis)["decision"], "HOLD")
            self.assertFalse(lab.positions)

    def test_wide_spread_rejected(self):
        lab = Lab()
        self.assertEqual(lab.process({**self.event, "ask": "110"}, self.analysis)["decision"], "REJECT")

    def test_ai_output_cannot_change_limits(self):
        bad = {**self.analysis, "position_fraction": 1}
        with self.assertRaises(ValueError):
            validate_analysis(bad)
        lab = Lab()
        self.assertEqual(lab.process(self.event, bad)["decision"], "HOLD")
        self.assertFalse(lab.positions)

    def test_missing_analysis_has_no_entry(self):
        lab = Lab()
        self.assertEqual(lab.process(self.event, None)["decision"], "HOLD")
        self.assertFalse(lab.positions)

    def test_gap_stop_uses_available_price_and_keeps_costs(self):
        lab = Lab()
        lab.process(self.event, self.analysis)
        event = {**self.event, "id": "gap", "bid": "80", "ask": "80.10"}
        result = lab.process(event, None)
        self.assertEqual(result["decision"], "PAPER_SELL")
        self.assertLess(number(result["price"]), number("80"))
        self.assertLess(lab.cash, lab.limits.start_cash)
        self.assertFalse(lab.positions)
        self.assertTrue(lab.halted)
        next_event = {**self.event, "id": "new", "symbol": "DEMO-B"}
        self.assertIn("Daily loss", lab.process(next_event, self.analysis)["reason"])

    def test_exposure_and_cash_bounds(self):
        lab = Lab()
        for i in range(8):
            event = {**self.event, "id": str(i), "symbol": "DEMO-" + str(i)}
            lab.process(event, self.analysis)
        self.assertGreaterEqual(lab.cash, 0)
        self.assertLessEqual(lab.equity() - lab.cash, lab.equity() * lab.limits.total_fraction)

    def test_untrusted_source_does_not_open_position(self):
        lab = Lab()
        result = lab.process({**self.event, "source": "social_media"}, self.analysis)
        self.assertEqual(result["decision"], "HOLD")
        self.assertFalse(lab.positions)

    def test_old_quote_and_out_of_order_event_rejected(self):
        lab = Lab()
        result = lab.process({**self.event, "quote_at": "2026-10-16T11:59:00Z"}, self.analysis)
        self.assertEqual(result["decision"], "REJECT")
        lab.process(self.event, self.analysis)
        result = lab.process({**self.event, "id": "old", "received_at": "2026-10-16T11:59:59Z"}, self.analysis)
        self.assertEqual(result["decision"], "REJECT")

    def test_local_ai_failure_never_uses_demo_annotation(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("agent.local_analysis", side_effect=TimeoutError):
                report = run(Path(__file__).with_name("demo.json"), Path(directory) / "report.json", "local-test")
            self.assertFalse(report["positions"])
            self.assertFalse(any(d["decision"] == "PAPER_BUY" for d in report["decisions"]))
            self.assertTrue(any(d["decision"] == "AI_ERROR" for d in report["decisions"]))

    def test_local_ai_request_and_hungarian_response_contract(self):
        annotation = {"impact": "negative", "novel": True, "evidence": "Csökkent az előrejelzés."}
        response = {"done": True, "message": {"content": json.dumps(annotation)}, "eval_count": 20}
        with patch("agent.urllib.request.build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            telemetry = {}
            actual = local_analysis("qwen3.8:27b", "DEMO-A", "sample", telemetry, hungarian=True)
            request = factory.return_value.open.call_args[0][0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
            self.assertIn("Hungarian", payload["messages"][0]["content"])
            self.assertEqual(actual, annotation)
            self.assertEqual(telemetry["eval_count"], 20)

    def test_cloud_model_names_rejected_before_network(self):
        with patch("agent.urllib.request.build_opener") as factory:
            with self.assertRaises(ValueError):
                local_analysis("qwen:cloud", "DEMO-A", "sample")
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
