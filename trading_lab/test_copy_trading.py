import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from agent import number
from copy_trading import PaperCopyLedger, CopyLimits, demonstration, plan_copy, empty_book


class CopyTradingTests(unittest.TestCase):
    def setUp(self):
        self.instrument = "test:perpetual:BTC:USDC"
        self.now = datetime(2026, 10, 18, 10, tzinfo=timezone.utc)
        self.specs = {self.instrument: {"kind": "perpetual", "currency": "USDC", "step": "0.000001"}}
        self.quotes = {self.instrument: {"bid": "59999", "ask": "60001", "at": self.now.isoformat()}}

    def snapshot(self, qty="0.1", offset=0):
        return {"id": "event-" + str(offset), "leader": "test-leader", "source_class": "direct_positions",
                "source_at": (self.now + timedelta(seconds=offset)).isoformat(), "equity": "100000",
                "complete": True, "currency": "USDC", "scope": "test:perps",
                "positions": {self.instrument: {"quantity": qty, "reference_price": "60000"}} if number(qty) else {}}

    def test_proportional_open_and_close(self):
        ledger = PaperCopyLedger()
        opened = ledger.follow(self.snapshot(), self.quotes, self.specs, self.now)
        self.assertEqual(opened["orders"][0]["target"], "0.010000")
        closed = ledger.follow(self.snapshot("0", 1), self.quotes, self.specs, self.now + timedelta(seconds=1))
        self.assertEqual(closed["orders"][0]["transition"], "teljes zárás")
        self.assertFalse(ledger.book()["positions"])
        self.assertLess(number(ledger.book()["settled"]), number("10000"))
        ledger.close()

    def test_the_owner_sets_the_copy_size(self):
        # The owner (2 Nov): copying must be adjustable; half size follows the leader at half the proportional exposure.
        half = PaperCopyLedger().follow(self.snapshot(), self.quotes, self.specs, self.now, size="0.5")
        self.assertEqual(half["orders"][0]["target"], "0.005000")
        with self.assertRaises(ValueError): plan_copy(self.snapshot(), empty_book(), self.quotes, self.specs, self.now, size="3")

    def test_open_add_reduce_close_and_short_are_exercised(self):
        report = demonstration()
        self.assertTrue(all(step["status"] == "READY" for step in report["steps"]))
        transitions = [step["orders"][0]["transition"] for step in report["steps"]]
        self.assertEqual(transitions, ["nyitás", "ráépítés", "részleges zárás", "teljes zárás", "nyitás", "teljes zárás"])
        self.assertLess(number(report["steps"][4]["orders"][0]["target"]), 0)

    def test_duplicate_is_blocked_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.sqlite"
            ledger = PaperCopyLedger(path)
            ledger.follow(self.snapshot(), self.quotes, self.specs, self.now)
            original = ledger.book()
            ledger.close()
            restarted = PaperCopyLedger(path)
            self.assertEqual(restarted.follow(self.snapshot(), self.quotes, self.specs, self.now)["status"], "DUPLICATE")
            self.assertEqual(original, restarted.book())
            restarted.close()

    def test_delayed_disclosure_is_not_treated_as_live_copy(self):
        snapshot = {**self.snapshot(), "source_class": "disclosure"}
        with self.assertRaises(ValueError):
            plan_copy(snapshot, empty_book(), self.quotes, self.specs, self.now)

    def test_incomplete_snapshot_never_closes_existing_position(self):
        ledger = PaperCopyLedger()
        ledger.follow(self.snapshot(), self.quotes, self.specs, self.now)
        before = ledger.book()
        incomplete = {**self.snapshot("0", 1), "complete": False}
        self.assertEqual(ledger.follow(incomplete, self.quotes, self.specs, self.now + timedelta(seconds=1))["status"], "BLOCKED")
        self.assertEqual(before, ledger.book())
        ledger.close()

    def test_wrong_instrument_or_currency_not_substituted(self):
        for specs in ({}, {self.instrument: {**self.specs[self.instrument], "currency": "USD"}}):
            with self.assertRaises(ValueError):
                plan_copy(self.snapshot(), empty_book(), self.quotes, specs, self.now)

    def test_large_leverage_is_rejected_without_clipping(self):
        ledger = PaperCopyLedger()
        plan = ledger.follow(self.snapshot("10"), self.quotes, self.specs, self.now)
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertFalse(plan["orders"])
        self.assertFalse(ledger.book()["positions"])
        ledger.close()

    def test_short_equity_is_rejected(self):
        specs = {self.instrument: {**self.specs[self.instrument], "kind": "cash_equity"}}
        plan = plan_copy(self.snapshot("-0.1"), empty_book(), self.quotes, specs, self.now)
        self.assertEqual(plan["status"], "BLOCKED")

    def test_stale_or_out_of_order_snapshot_and_quote_are_rejected(self):
        for offset in (-60, 1):
            with self.assertRaises(ValueError):
                plan_copy(self.snapshot(offset=offset), empty_book(), self.quotes, self.specs, self.now)
        quotes = {self.instrument: {**self.quotes[self.instrument], "at": (self.now - timedelta(seconds=20)).isoformat()}}
        with self.assertRaises(ValueError):
            plan_copy(self.snapshot(), empty_book(), quotes, self.specs, self.now)

    def test_exits_remain_allowed_when_the_limit_is_exceeded(self):
        book = empty_book()
        book["positions"][self.instrument] = {"quantity": "0.2", "entry": "60000"}
        plan = plan_copy(self.snapshot("0"), book, self.quotes, self.specs, self.now)
        self.assertEqual(plan["status"], "READY")
        self.assertEqual(plan["orders"][0]["target"], "0.000000")

    def test_change_of_leader_or_venue_scope_cannot_close_positions(self):
        ledger = PaperCopyLedger()
        ledger.follow(self.snapshot(), self.quotes, self.specs, self.now)
        before = ledger.book()
        for field, value in (("leader", "other"), ("scope", "other-venue"), ("currency", "USD")):
            snapshot = {**self.snapshot("0", 1), field: value, "id": field}
            self.assertEqual(ledger.follow(snapshot, self.quotes, self.specs, self.now + timedelta(seconds=1))["status"], "BLOCKED")
            self.assertEqual(before, ledger.book())
        ledger.close()

    def test_fee_reserve_prevents_hidden_exposure_overrun(self):
        # 50% exposure before fees exceeds the same cap after execution costs.
        snapshot = self.snapshot("0.833333")
        plan = plan_copy(snapshot, empty_book(), self.quotes, self.specs, self.now)
        self.assertEqual(plan["status"], "BLOCKED")

    def test_flip_realizes_old_side_and_opens_new_side(self):
        ledger = PaperCopyLedger()
        ledger.follow(self.snapshot(), self.quotes, self.specs, self.now)
        plan = ledger.follow(self.snapshot("-0.1", 1), self.quotes, self.specs, self.now + timedelta(seconds=1))
        self.assertEqual(plan["orders"][0]["transition"], "irányváltás")
        position = ledger.book()["positions"][self.instrument]
        self.assertLess(number(position["quantity"]), 0)
        self.assertEqual(number(position["entry"]), number(plan["orders"][0]["price"]))
        self.assertLess(number(ledger.book()["settled"]), number("10000"))
        ledger.close()


if __name__ == "__main__":
    unittest.main()
