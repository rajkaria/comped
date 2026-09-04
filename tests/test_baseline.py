import unittest, tempfile, pathlib
from decimal import Decimal
from datetime import datetime, timezone
from comped_core.baseline import load_baseline, save_baseline, delta
from comped_core.pricing import PricedSummary
from comped_core.repeats import RepeatCluster
def S(total, mult, models): return PricedSummary(Decimal(total), [{"model": m, "usd": Decimal(u)} for m, u in models], [], Decimal("0.5"), 3, 4, {}, Decimal("197"), Decimal(mult) if mult else None, [])
def C(label): return RepeatCluster(label, 3, 3, 3, Decimal("9"), Decimal("6"), Decimal("5.88"), Decimal("4.80"), "cmd", [])
class BaselineTests(unittest.TestCase):
    def test_first_run_then_delta(self):
        d = pathlib.Path(tempfile.mkdtemp()); t1 = datetime(2026, 9, 1, tzinfo=timezone.utc); t2 = datetime(2026, 9, 3, tzinfo=timezone.utc)
        self.assertIsNone(load_baseline(d))
        r0 = delta(None, S("100", "1.5", [("m1", "100")]), [C("a")], t1); self.assertTrue(r0["first_run"])
        save_baseline(d, S("100", "1.5", [("m1", "100")]), [C("a")], t1)
        prev = load_baseline(d); r = delta(prev, S("160", "2.0", [("m1", "150"), ("m2", "10")]), [C("b")], t2)
        self.assertFalse(r["first_run"]); self.assertEqual(r["days_since"], 2)
        self.assertEqual(r["total_usd_delta"], Decimal("60")); self.assertEqual(r["multiplier_delta"], Decimal("0.5"))
        self.assertEqual(r["new_repeats"], ["b"]); self.assertEqual(r["resolved_repeats"], ["a"])
        self.assertEqual(r["per_model_delta"], [{"model": "m1", "delta": Decimal("50")}, {"model": "m2", "delta": Decimal("10")}])
