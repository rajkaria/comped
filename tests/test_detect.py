import unittest
from decimal import Decimal
from datetime import datetime, timezone

from comped_core.detect import provider_of, detect_stack, infer_plans, summary_line
from comped_core.models import UsageRecord, Ledger, Source
from comped_core.plans import load_plans, parse_plan_ids, plan_entry, plan_cost
from comped_core.prices import load_table, resolve_model
from comped_core.pricing import price_ledger


def R(model, harness="claude-code", sid="s1", ts="2026-09-01T10:00:00Z", inp=1000, out=1000):
    return UsageRecord(harness, sid, "{0}{1}{2}".format(harness, model, ts), ts, model, inp, 0, 0, out, 0, "/p", False, "t1")


class ProviderNames(unittest.TestCase):
    def test_the_big_two(self):
        self.assertEqual(provider_of("claude-opus-5")[0], "anthropic")
        self.assertEqual(provider_of("gpt-5.5")[0], "openai")
        self.assertEqual(provider_of("gpt-5.1-codex")[0], "openai")
        self.assertEqual(provider_of("o4-mini")[0], "openai")

    def test_a_harness_pointed_somewhere_else(self):
        # Claude Code against Moonshot or Z.ai writes their model ids into the same log shape.
        # The id is the only trace of it, and it is enough.
        self.assertEqual(provider_of("kimi-k2-0905-preview")[0], "moonshot")
        self.assertEqual(provider_of("kimi-k2.6")[2], "Kimi")
        self.assertEqual(provider_of("glm-4.6")[0], "zai")
        self.assertEqual(provider_of("deepseek-chat")[0], "deepseek")
        self.assertEqual(provider_of("qwen3-coder-plus")[0], "alibaba")
        self.assertEqual(provider_of("MiniMax-M2.5")[0], "minimax")
        self.assertEqual(provider_of("grok-code-fast-1")[0], "xai")
        self.assertEqual(provider_of("gemini-3-pro-preview")[0], "google")

    def test_gateways_are_routing_not_identity(self):
        for m in ("us.anthropic.claude-opus-5", "bedrock/anthropic.claude-sonnet-5", "openrouter/anthropic/claude-opus-5"):
            self.assertEqual(provider_of(m)[0], "anthropic", m)
        self.assertEqual(provider_of("openrouter/z-ai/glm-4.7")[0], "zai")
        self.assertEqual(provider_of("moonshot/kimi-k2.6")[0], "moonshot")

    def test_a_model_nobody_knows_is_never_assigned_by_guess(self):
        self.assertEqual(provider_of("nano_banana")[0], "unknown")
        self.assertEqual(provider_of("")[0], "unknown")
        self.assertEqual(provider_of("(blank)")[0], "unknown")


class Detection(unittest.TestCase):
    def setUp(self):
        self.table = load_table()
        self.sources = [Source("claude-code", "/logs/claude", True, files=12),
                        Source("codex", "/logs/codex", True, files=3),
                        Source("pi", "/logs/pi", False, note="directory not found")]

    def test_it_names_the_providers_the_harnesses_and_the_models(self):
        d = detect_stack([R("claude-opus-5"), R("claude-opus-5", ts="2026-09-01T11:00:00Z"), R("kimi-k2.6"),
                          R("gpt-5.5", harness="codex", sid="c1")], self.sources, self.table)
        self.assertEqual(d["basis"], "models")
        self.assertEqual([p["key"] for p in d["providers"]], ["anthropic", "moonshot", "openai"])
        self.assertEqual(d["providers"][0]["records"], 2)
        found = [h for h in d["harnesses"] if h["found"]]
        self.assertEqual([h["label"] for h in found], ["Claude Code", "Codex CLI"])
        self.assertEqual([h["label"] for h in d["harnesses"] if not h["found"]], ["Pi"])
        self.assertEqual(sorted(m["model"] for m in d["models"]), ["claude-opus-5", "gpt-5.5", "kimi-k2.6"])
        self.assertTrue(all(m["priced"] for m in d["models"]), [m for m in d["models"] if not m["priced"]])

    def test_an_empty_window_still_reports_the_harnesses_it_found(self):
        d = detect_stack([], self.sources, self.table)
        self.assertEqual(d["basis"], "harnesses")
        self.assertEqual(sorted(p["key"] for p in d["providers"]), ["anthropic", "openai"])
        self.assertEqual(sum(p["records"] for p in d["providers"]), 0)

    def test_nothing_at_all(self):
        d = detect_stack([], [Source("claude-code", "/nope", False)], self.table)
        self.assertEqual(d["basis"], "nothing")
        self.assertEqual(d["providers"], [])
        self.assertIn("no log directory", summary_line(d))

    def test_summary_line_reads_as_a_sentence(self):
        d = detect_stack([R("claude-opus-5"), R("kimi-k2.6")], self.sources, self.table)
        self.assertEqual(summary_line(d), "Claude 50% · Kimi 50% via Claude Code, Codex CLI")


class PlanInference(unittest.TestCase):
    def setUp(self):
        self.plans = load_plans()
        self.table = load_table()
        self.sources = [Source("claude-code", "/logs/claude", True, files=12)]

    def test_it_assumes_the_least_flattering_tier_and_offers_the_rest(self):
        d = detect_stack([R("claude-opus-5")], self.sources, self.table)
        assumed, candidates, notes = infer_plans(d, self.plans)
        self.assertEqual(assumed, ["claude-max-200"])          # the most expensive Anthropic plan
        self.assertEqual(candidates, ["claude-pro-20", "claude-max-100", "claude-max-200"])
        self.assertEqual(notes, [])

    def test_a_provider_with_no_subscription_says_so_instead_of_inventing_one(self):
        d = detect_stack([R("kimi-k2.6")], self.sources, self.table)
        assumed, candidates, notes = infer_plans(d, self.plans)
        self.assertEqual(assumed, [])
        self.assertEqual(candidates, [])
        self.assertTrue(any("Moonshot" in n and "no subscription" in n for n in notes), notes)
        self.assertTrue(any("usd:" in n for n in notes), notes)

    def test_two_vendors_assume_one_plan_each(self):
        d = detect_stack([R("claude-opus-5"), R("gpt-5.5", harness="codex", sid="c1")], self.sources, self.table)
        assumed, _, _ = infer_plans(d, self.plans)
        self.assertEqual(sorted(assumed), ["chatgpt-pro-200", "claude-max-200"])


class CustomAndAutoPlans(unittest.TestCase):
    def setUp(self):
        self.plans = load_plans()
        self.table = load_table()
        self.now = datetime(2026, 9, 3, tzinfo=timezone.utc)
        self.led = Ledger([R("claude-opus-5", inp=10 ** 6, out=10 ** 6)], [], [],
                          [Source("claude-code", "/logs/claude", True, files=1)], "2026-09-03T00:00:00Z")

    def test_a_subscription_the_table_does_not_carry_can_still_be_priced(self):
        e = plan_entry("usd:29", self.plans)
        self.assertEqual(e["monthly_usd"], "29")
        self.assertIn("29", e["label"])
        cost, ok, notes = plan_cost(["usd:29"], 30, self.plans)
        self.assertEqual(ok, ["usd:29"])
        self.assertEqual(cost.quantize(Decimal("0.01")), Decimal("28.58"))
        self.assertEqual(notes, [])
        self.assertIsNone(plan_entry("usd:banana", self.plans))

    def test_auto_is_the_default_and_needs_nothing_typed(self):
        s = price_ledger(self.led, self.table, self.plans, parse_plan_ids("auto"), 30, self.now)
        self.assertEqual(s.plan_source, "auto")
        self.assertEqual(s.plan_ids, ["claude-max-200"])
        self.assertIsNotNone(s.multiplier)
        self.assertEqual([r["label"] for r in s.plan_ladder], ["Claude Pro", "Claude Max 5x", "Claude Max 20x"])
        self.assertEqual([r["assumed"] for r in s.plan_ladder], [False, False, True])
        # every row is the same spend over a different price, so the cheapest plan has the biggest number
        self.assertGreater(s.plan_ladder[0]["multiplier"], s.plan_ladder[-1]["multiplier"])
        self.assertEqual(s.detected["providers"][0]["key"], "anthropic")
        self.assertTrue(any("detected:" in e for e in s.explain))
        self.assertTrue(any("ladder" in e and "assumed" in e for e in s.explain))

    def test_a_typed_plan_still_wins(self):
        s = price_ledger(self.led, self.table, self.plans, ["claude-pro-20"], 30, self.now)
        self.assertEqual(s.plan_source, "typed")
        self.assertEqual(s.plan_ids, ["claude-pro-20"])
        self.assertTrue([r for r in s.plan_ladder if r["assumed"]][0]["label"] == "Claude Pro")

    def test_unpriced_models_are_still_detected(self):
        led = Ledger([R("nano_banana")], [], [], [Source("claude-code", "/logs/claude", True, files=1)], "x")
        s = price_ledger(led, self.table, self.plans, ["auto"], 30, self.now)
        self.assertEqual(s.detected["providers"][0]["key"], "unknown")
        self.assertIsNone(resolve_model("nano_banana", self.table))
        self.assertIsNone(s.multiplier)
        self.assertEqual(s.plan_ladder, [])
