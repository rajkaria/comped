import unittest
from decimal import Decimal
from comped_core.plans import load_plans, plan_cost

class PlanTests(unittest.TestCase):
    def test_bundled_plans(self):
        p = load_plans()
        for pid in ("claude-pro-20", "claude-max-100", "claude-max-200", "chatgpt-plus-20", "chatgpt-pro-200", "api", "unknown"):
            self.assertIn(pid, p["plans"])
        self.assertIn("as_of", p["meta"])
    def test_cost_prorated_30_days(self):
        cost, ids, notes = plan_cost(["claude-max-200", "chatgpt-plus-20"], 30, load_plans())
        self.assertEqual(ids, ["claude-max-200", "chatgpt-plus-20"])
        self.assertEqual(cost.quantize(Decimal("0.01")), Decimal("216.84"))  # 220 * 30 / 30.4375
    def test_api_or_unknown_gives_none(self):
        self.assertIsNone(plan_cost(["api"], 30, load_plans())[0]); self.assertIsNone(plan_cost([], 30, load_plans())[0])
        self.assertIsNone(plan_cost(["unknown"], 30, load_plans())[0])
    def test_bad_id_is_noted_not_fatal(self):
        cost, ids, notes = plan_cost(["claude-max-200", "bogus"], 30, load_plans())
        self.assertEqual(ids, ["claude-max-200"]); self.assertTrue(any("bogus" in n for n in notes))
