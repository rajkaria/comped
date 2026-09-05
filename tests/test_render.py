import unittest, tempfile, pathlib, base64, json
from decimal import Decimal
from comped_core.render_terminal import render_terminal
from comped_core.render_report import render_report, share_text, card_url
from comped_core.render_svg import render_svg
from comped_core.render_png import render_png

def V(mult=Decimal("42.9")):
    return {"window_days": 30, "window_start": "2026-08-04T00:00:00Z", "window_end": "2026-09-03T00:00:00Z", "total_usd": Decimal("8570.2"),
            "multiplier": mult, "plan_labels": ["Claude Max 20x", "ChatGPT Plus"], "plan_cost": Decimal("216.84"),
            "per_model": [{"model": "claude-opus-5", "usd": Decimal("5102.4"), "share": Decimal("0.61")}, {"model": "gpt-5.5", "usd": Decimal("456.05"), "share": Decimal("0.05")}],
            "cache_share": Decimal("0.78"), "active_days": 27, "sessions": 312,
            "delta": {"first_run": False, "days_since": 2, "total_usd_delta": Decimal("611.1"), "multiplier_delta": Decimal("0.9"), "new_repeats": [], "resolved_repeats": [], "per_model_delta": []},
            "repeats": [{"label": "push it to prod", "count": 4, "repeat_usd": Decimal("283"), "capture_command": '/play settle priya "push it to prod"'}],
            "dividend_98": Decimal("404"), "dividend_80": Decimal("330"), "unpriced": [{"model": "nano_banana", "records": 3, "tokens": 900}],
            "price_as_of": "2026-09-01", "price_source": "https://x", "sources": [{"harness": "claude-code", "found": True, "files": 10, "duplicates": 4000, "note": ""}],
            "written": [], "play_uri": "https://play.modiqo.ai/priya/comped", "explain_path": "~/comped/comped-explain.txt", "handle": "priya",
            "plan_source": "auto",
            "detected": {"basis": "models",
                         "providers": [{"key": "anthropic", "label": "Anthropic", "talk_to": "Claude", "records": 90, "tokens": 9,
                                        "models": ["claude-opus-5"], "plans": ["claude-max-200"], "usd": Decimal("5102.4")},
                                       {"key": "moonshot", "label": "Moonshot", "talk_to": "Kimi", "records": 10, "tokens": 1,
                                        "models": ["kimi-k2.6"], "plans": [], "usd": Decimal("456.05")}],
                         "harnesses": [{"harness": "claude-code", "label": "Claude Code", "found": True, "files": 10, "records": 90,
                                        "sessions": 3, "models": ["claude-opus-5"], "default_provider": "anthropic", "note": ""},
                                       {"harness": "pi", "label": "Pi", "found": False, "files": 0, "records": 0,
                                        "sessions": 0, "models": [], "default_provider": "anthropic", "note": "directory not found"}],
                         "models": []},
            "plan_ladder": [{"label": "Claude Pro", "cost": Decimal("19.71"), "multiplier": Decimal("434.8"), "assumed": False},
                            {"label": "Claude Max 20x", "cost": Decimal("197.13"), "multiplier": Decimal("43.5"), "assumed": True}]}

class RenderTests(unittest.TestCase):
    def test_terminal_card_shape(self):
        out = render_terminal(V(), color=False); lines = out.splitlines()
        self.assertTrue(all(len(l) == 64 for l in lines), [len(l) for l in lines])
        self.assertIn("$8,570.20 comped", out); self.assertIn("42.9×", out); self.assertIn("since last run (2d ago): +$611.10, +0.9×", out)
        self.assertIn("4× \"push it to prod\"", out); self.assertIn("Rote dividend: $404 at 98% · $330 at 80%", out)
        self.assertIn("list-price equivalent, not a bill", out); self.assertIn("1 model unpriced", out)
    def test_terminal_no_plan(self):
        out = render_terminal(V(mult=None), color=False)
        self.assertIn("no subscription matched what you run", out); self.assertNotIn("×  vs", out)
    def test_terminal_shows_what_it_detected_and_never_asks_for_it(self):
        out = render_terminal(V(), color=False); lines = out.splitlines()
        self.assertTrue(all(len(l) == 64 for l in lines), [len(l) for l in lines])
        self.assertIn("DETECTED", out)
        self.assertIn("Claude", out); self.assertIn("Kimi", out)          # both providers, from model ids alone
        self.assertIn("read from Claude Code", out)
        self.assertIn("not installed here: Pi", out)
        self.assertIn("assumed from your own logs", out)
    def test_terminal_prices_every_tier_so_you_read_your_row(self):
        out = render_terminal(V(), color=False)
        self.assertIn("Claude Pro", out); self.assertIn("434.8×", out)
        self.assertIn("← assumed", out); self.assertIn("plan=usd:29", out)
    def test_report_carries_the_detection_and_the_ladder(self):
        md = render_report(V())
        self.assertIn("## Detected", md); self.assertIn("| Moonshot | Kimi |", md)
        self.assertIn("## If you're on", md); self.assertIn("| Claude Max 20x | $197.13 | 43.5x | assumed |", md)
        self.assertIn("Claude Code (10 files)", md); self.assertIn("Not installed here: Pi", md)
    def test_color_toggle(self):
        self.assertIn("\x1b[", render_terminal(V(), color=True)); self.assertNotIn("\x1b[", render_terminal(V(), color=False))
    def test_report_and_share(self):
        md = render_report(V())
        for h in ("## Card", "## Models", "## Sources", "## Repeat offenders", "## Rote dividend", "## Delta since last run", "## Unpriced models", "## Methodology", "## Privacy"): self.assertIn(h, md)
        self.assertIn("never reads", md.lower()); s = share_text(V())
        self.assertIn("$8,570", s); self.assertIn("43×", s); self.assertIn("gotcomped.com", s); self.assertIn("#gotcomped", s)
    def test_svg_escapes_and_size(self):
        v = V(); v["per_model"][0]["model"] = "<script>&"
        svg = render_svg(v, "dark"); self.assertIn('width="1200"', svg); self.assertIn("&lt;script&gt;&amp;", svg); self.assertNotIn("<script>", svg)
        self.assertIn("not a bill", svg); self.assertNotIn("<image", svg)
        self.assertIn("Claude 90%", svg); self.assertIn("IF YOU'RE ON", svg); self.assertIn("Claude Code", svg); self.assertNotIn("http", svg.split("play.modiqo.ai")[0].split("xmlns")[0])
    def test_png_missing_renderer_is_note(self):
        d = pathlib.Path(tempfile.mkdtemp()); p = d / "c.svg"; p.write_text(render_svg(V(), "dark"))
        png, note = render_png(p, d, renderers=[])
        self.assertIsNone(png); self.assertIn("PNG skipped", note)


class CardLinkTests(unittest.TestCase):
    """The link the run prints so a machine with no rasteriser can still get a PNG.

    Two promises are load bearing: the numbers sit in the fragment, which a browser never puts in
    a request, and they are the same fields the leaderboard row already carries. A path, a prompt
    or a model id sliding into this link would put it into every post someone pastes it in.
    """

    def doc(self, v):
        url = card_url(v)
        head, blob = url.split("#c=", 1)
        self.assertEqual(head, "https://gotcomped.com/card.html", "the numbers must be after the #")
        return json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)).decode("utf-8")), blob

    def test_it_carries_the_leaderboard_fields_and_no_others(self):
        d, _ = self.doc(V())
        self.assertEqual(set(d), {"v", "h", "m", "t", "u", "p", "pl", "pv", "hs", "d", "a", "c", "s"})
        self.assertEqual(d["h"], "priya")
        self.assertEqual(d["m"], 42.9)
        self.assertEqual(d["u"], 8570.2)
        self.assertEqual(d["p"], 216.84)
        self.assertEqual(d["pl"], "Claude Max 20x + ChatGPT Plus")
        self.assertEqual(d["pv"], ["anthropic", "moonshot"])
        self.assertEqual(d["hs"], ["claude-code"])          # a harness with no records is not a source
        self.assertEqual((d["d"], d["a"], d["s"], d["c"]), (30, 27, 312, 0.78))
        self.assertEqual(d["t"], "Hostage situation")

    def test_no_path_prompt_or_model_id_rides_along(self):
        _, blob = self.doc(V())
        text = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)).decode("utf-8")
        for leak in ("claude-opus-5", "push it to prod", "play settle", "comped-explain", "/", "\\"):
            self.assertNotIn(leak, text, "the card link carries {0!r}".format(leak))

    def test_a_run_with_no_handle_and_no_plan_still_makes_a_link(self):
        v = V(mult=None)
        v["handle"] = "<handle>"                            # the CLI's placeholder for "not given"
        v["plan_labels"] = []
        v["plan_cost"] = None
        d, _ = self.doc(v)
        self.assertEqual(d["h"], "")
        self.assertIsNone(d["m"])
        self.assertIsNone(d["p"])
        self.assertEqual(d["pl"], "")

    def test_the_rank_rides_along_once_the_score_has_been_posted(self):
        v = V()
        v["rank"], v["rank_of"] = 3, 128
        d, _ = self.doc(v)
        self.assertEqual((d["r"], d["n"]), (3, 128))

    def test_the_report_hands_you_the_link(self):
        self.assertIn("https://gotcomped.com/card.html#c=", render_report(V()))
