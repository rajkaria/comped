import unittest
from decimal import Decimal
from datetime import datetime, timezone
from comped_core.models import UsageRecord, Ledger, Source
from comped_core.pricing import price_ledger, usd_for
from comped_core.prices import load_table
from comped_core.plans import load_plans

def R(model, inp, cw, cr, out, ts="2026-09-01T10:00:00Z", turn="t1", harness="claude-code", sid="s"):
    return UsageRecord(harness, sid, "{0}{1}{2}".format(model, ts, turn), ts, model, inp, cw, cr, out, 0, "/p", False, turn)

class PricingTests(unittest.TestCase):
    def setUp(self): self.table = load_table(); self.plans = load_plans(); self.now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    def test_usd_for_opus5(self):
        usd, key = usd_for(R("claude-opus-5", 1000000, 1000000, 1000000, 1000000), self.table)
        self.assertEqual(key, "claude-opus-5"); self.assertEqual(usd, Decimal("5") + Decimal("6.25") + Decimal("0.5") + Decimal("25"))
    def test_unknown_is_zero_and_flagged(self):
        usd, key = usd_for(R("nano_banana", 10, 0, 0, 10), self.table); self.assertEqual(usd, Decimal("0")); self.assertIsNone(key)
    def test_summary_totals_multiplier_cache_share(self):
        led = Ledger([R("claude-opus-5", 1000000, 0, 3000000, 0), R("claude-opus-5", 0, 0, 0, 100000, turn="t2"),
                      R("nano_banana", 5, 0, 0, 5, turn="t3"), R("claude-opus-5", 1, 0, 0, 1, ts="2026-07-01T00:00:00Z", turn="old")],
                     [], [], [Source("claude-code", "/x", True)], "2026-09-03T00:00:00Z")
        s = price_ledger(led, self.table, self.plans, ["claude-max-200"], 30, self.now)
        self.assertEqual(s.total_usd, Decimal("5") + Decimal("1.5") + Decimal("2.5"))
        self.assertEqual(s.per_model[0]["model"], "claude-opus-5"); self.assertEqual(s.per_model[0]["records"], 2)
        self.assertEqual(s.unpriced, [{"model": "nano_banana", "records": 1, "tokens": 10}])
        # cache share covers every record in the window, unpriced ones included, so the
        # nano_banana record's 5 input tokens sit in the denominator: 3M / 4,000,005.
        self.assertEqual(s.cache_share.quantize(Decimal("0.001")), Decimal("0.750"))
        self.assertEqual(s.active_days, 1); self.assertEqual(s.sessions, 1)
        self.assertEqual(s.plan_cost.quantize(Decimal("0.01")), Decimal("197.13"))
        self.assertEqual(s.multiplier.quantize(Decimal("0.1")), Decimal("0.0"))
        self.assertEqual(s.per_turn_usd["t1"], Decimal("6.5")); self.assertEqual(s.per_turn_usd["t2"], Decimal("2.5"))
        self.assertTrue(any("claude-opus-5" in e and "0.000005" in e for e in s.explain))
        self.assertTrue(any("plan" in e.lower() for e in s.explain))
    def test_no_plan(self):
        led = Ledger([R("claude-opus-5", 10, 0, 0, 10)], [], [], [], "x")
        s = price_ledger(led, self.table, self.plans, [], 30, self.now)
        self.assertIsNone(s.plan_cost); self.assertIsNone(s.multiplier)
