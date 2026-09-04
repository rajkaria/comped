import unittest
from decimal import Decimal
from comped_core.models import HumanMessage
from comped_core.repeats import find_repeats
def H(mid, text, sid, day, origin="human"): return HumanMessage("claude-code", sid, mid, "2026-09-{0:02d}T10:00:00Z".format(day), text, "h", "/home/demo/p", origin)
class RepeatTests(unittest.TestCase):
    def test_cluster_found_and_costed(self):
        hs = [H("a", "push it to prod please", "s1", 1), H("b", "push it to prod", "s2", 2), H("c", "push it to prod now", "s3", 3),
              H("d", "write the changelog for release", "s1", 1), H("e", "explain this stack trace", "s4", 4)]
        cost = {"a": Decimal("10"), "b": Decimal("4"), "c": Decimal("6"), "d": Decimal("1"), "e": Decimal("2")}
        cl = find_repeats(hs, cost, 3, "priya")
        self.assertEqual(len(cl), 1); c = cl[0]
        self.assertEqual(c.count, 3); self.assertEqual(c.sessions, 3); self.assertEqual(c.days, 3)
        self.assertEqual(c.total_usd, Decimal("20")); self.assertEqual(c.repeat_usd, Decimal("16"))
        self.assertEqual(c.dividend_98, Decimal("15.68")); self.assertEqual(c.dividend_80, Decimal("12.80"))
        self.assertEqual(c.label, "push it to prod"); self.assertEqual(sorted(c.members), ["a", "b", "c"])
        self.assertEqual(c.capture_command, '/play settle priya "push it to prod"')
    def test_requires_two_sessions_and_two_days(self):
        hs = [H("a", "push it to prod", "s1", 1), H("b", "push it to prod", "s1", 1), H("c", "push it to prod", "s1", 1)]
        self.assertEqual(find_repeats(hs, {}, 3, ""), [])
    def test_automated_excluded_and_sorted_by_repeat_cost(self):
        hs = [H("a", "hello memory agent", "s1", 1, "automated"), H("b", "hello memory agent", "s2", 2, "automated"), H("c", "hello memory agent", "s3", 3, "automated"),
              H("d", "deploy the site to vercel", "s1", 1), H("e", "deploy the site to vercel", "s2", 2), H("f", "deploy the site to vercel", "s3", 3),
              H("g", "run the test suite", "s1", 1), H("h", "run the test suite", "s2", 2), H("i", "run the test suite", "s3", 3)]
        cost = {k: Decimal(v) for k, v in {"d": 1, "e": 1, "f": 1, "g": 5, "h": 5, "i": 5}.items()}
        cl = find_repeats(hs, cost, 3, "")
        self.assertEqual([c.label for c in cl], ["run the test suite", "deploy the site to vercel"])
        self.assertEqual(cl[0].capture_command, '/play settle <handle> "run the test suite"')

    def test_zero_cost_clusters_are_dropped_when_costs_are_known(self):
        # A repeat offender is ranked by what re-asking cost. On a priced ledger a cluster with no
        # attributed cost is boilerplate that never anchored a turn, not an ask worth showing.
        hs = [H("a", "deploy the site to vercel", "s1", 1), H("b", "deploy the site to vercel", "s2", 2),
              H("c", "deploy the site to vercel", "s3", 3),
              H("d", "run the test suite", "s1", 1), H("e", "run the test suite", "s2", 2),
              H("f", "run the test suite", "s3", 3)]
        priced = {k: Decimal(v) for k, v in {"d": 5, "e": 5, "f": 5}.items()}
        self.assertEqual([c.label for c in find_repeats(hs, priced, 3, "")], ["run the test suite"])
        # With no cost data at all (ledger not priced yet), both clusters still surface.
        self.assertEqual(len(find_repeats(hs, {}, 3, "")), 2)
