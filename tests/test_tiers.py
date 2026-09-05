import unittest, json, pathlib, tempfile, subprocess, sys
from decimal import Decimal

from comped_core.tiers import tier, score, TIERS
from comped_core.render_report import share_text
from comped_core.render_terminal import render_terminal
from comped_core.render_svg import render_svg


def V(mult):
    return {"window_days": 30, "total_usd": Decimal("2557.17"), "multiplier": mult, "plan_labels": ["Claude Max 20x"],
            "plan_cost": Decimal("197.13"), "plan_source": "auto", "per_model": [], "cache_share": Decimal("0.98"),
            "active_days": 22, "sessions": 98, "delta": {"first_run": True}, "repeats": [], "dividend_98": Decimal("0"),
            "dividend_80": Decimal("0"), "unpriced": [], "price_as_of": "2026-09-04", "price_source": "x", "sources": [],
            "written": [], "play_uri": "https://play.modiqo.ai/rajkaria/comped", "explain_path": "e", "handle": "rajkaria",
            "tier": tier(mult), "site": "https://gotcomped.com",
            "detected": {"basis": "models", "harnesses": [],
                         "providers": [{"key": "anthropic", "label": "Anthropic", "talk_to": "Claude", "records": 9,
                                        "tokens": 1, "models": ["claude-opus-5"], "plans": [], "usd": Decimal("2557")}]},
            "plan_ladder": []}


class Tiers(unittest.TestCase):
    def test_bands_are_contiguous_and_every_score_lands_somewhere(self):
        self.assertEqual(tier(Decimal("0.4"))["name"], "Paying customer")
        self.assertEqual(tier(Decimal("1"))["name"], "Break-even")
        self.assertEqual(tier(Decimal("13.0"))["name"], "All-you-can-eat")
        self.assertEqual(tier(Decimal("79.99"))["name"], "Hostage situation")
        self.assertEqual(tier(Decimal("500"))["name"], "Please stop")
        self.assertEqual(tier(Decimal("500"))["rank"], len(TIERS))
        self.assertIsNone(tier(None))

    def test_score_reads_like_a_person_wrote_it(self):
        self.assertEqual(score(Decimal("13.04")), "13×")
        self.assertEqual(score(Decimal("2.54")), "2.5×")   # one decimal below ten, none above
        self.assertEqual(score(None), "—")

    def test_share_text_leads_with_the_boast_and_ends_with_the_site(self):
        s = share_text(V(Decimal("13.0")))
        self.assertTrue(s.startswith("My comp score is 13× (All-you-can-eat)."), s)
        self.assertIn("Anthropic gave me $2,557 of AI for $197", s)
        self.assertIn("gotcomped.com", s)
        self.assertIn("#gotcomped", s)
        self.assertNotIn("play.modiqo.ai", s)   # the call is the site, not a CLI

    def test_share_text_without_a_multiplier_still_has_a_hook(self):
        s = share_text(V(None))
        self.assertIn("$2,557 of AI at full price", s)
        self.assertIn("gotcomped.com", s)

    def test_the_tier_is_on_the_card_and_in_the_image(self):
        out = render_terminal(V(Decimal("13.0")), color=False)
        self.assertIn("ALL-YOU-CAN-EAT · tier 5 of 7", out)
        self.assertTrue(all(len(l) == 64 for l in out.splitlines()))
        svg = render_svg(V(Decimal("13.0")), "dark")
        self.assertIn("ALL-YOU-CAN-EAT", svg)
        self.assertIn("gotcomped.com", svg)


class RememberedPlan(unittest.TestCase):
    def _run(self, out, *args):
        r = subprocess.run([sys.executable, "-m", "comped_core"] + list(args) + ["--out-dir", str(out)],
                           capture_output=True, text=True, check=True)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_say_it_once(self):
        out = pathlib.Path(tempfile.mkdtemp())
        self._run(out, "ledger", "--claude-dir", "resources/fixtures/claude", "--codex-dir", "/nonexistent",
                  "--pi-dir", "/nonexistent", "--opencode-dir", "/nonexistent", "--days-back", "3650", "--now", "2026-09-03T00:00:00Z")
        first = self._run(out, "price")                                  # nothing typed: inferred
        self.assertEqual(first["plan_source"], "auto")
        typed = self._run(out, "price", "--plan", "claude-pro-20")       # said once
        self.assertEqual(typed["plan_source"], "typed")
        self.assertEqual((out / "comped-plan.txt").read_text().strip(), "claude-pro-20")
        again = self._run(out, "price")                                  # remembered
        self.assertEqual(again["plan_source"], "remembered")
        self.assertIn("Claude Pro", again["note"])
        self.assertIn("tier", again)
        (out / "comped-plan.txt").unlink()
        back = self._run(out, "price")                                   # forgotten on request
        self.assertEqual(back["plan_source"], "auto")
