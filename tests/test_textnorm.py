import unittest
from comped_core.textnorm import normalize, shingles, jaccard, is_excluded
from comped_core.models import HumanMessage
def H(text, origin="human", project="/home/demo/p"): return HumanMessage("claude-code", "s", "m", "2026-09-01T00:00:00Z", text, "h", project, origin)
class TextNormTests(unittest.TestCase):
    def test_normalize_replaces_paths_urls_numbers(self):
        toks = normalize("Push /Users/x/proj to https://example.com at 10:42, see @file.md and 0xdeadbeef")
        self.assertEqual(toks, ["push", "<path>", "<url>", "<num>", "see", "<ref>", "<hex>"])
    def test_stopwords_and_cap(self):
        self.assertEqual(normalize("the a an and to of push it"), ["push"])
        self.assertEqual(len(normalize(" ".join(["word"] * 100))), 40)
    def test_shingles_jaccard(self):
        a = shingles(["push", "it", "to", "prod"]); b = shingles(["push", "it", "to", "staging"])
        self.assertAlmostEqual(jaccard(a, b), 2 / 4); self.assertEqual(jaccard(set(), set()), 0.0)
    def test_exclusions(self):
        self.assertEqual(is_excluded(H("<system-reminder>x</system-reminder>")), "injected")
        self.assertEqual(is_excluded(H("You are a helpful observer")), "system-prompt")
        self.assertEqual(is_excluded(H("ok", origin="automated")), "automated")
        self.assertEqual(is_excluded(H("hi")), "too-short")
        self.assertEqual(is_excluded(H(" ".join(["w"] * 401))), "too-long")
        self.assertEqual(is_excluded(H("push it to prod", project="/x/claude-mem-observer-sessions")), "observer-project")
        self.assertEqual(is_excluded(H("fix the failing test [Request interrupted by user]")), "interrupted")
        self.assertIsNone(is_excluded(H("push it to prod now")))
