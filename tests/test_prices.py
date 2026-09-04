import unittest, json, tempfile, pathlib
from decimal import Decimal
from comped_core.prices import load_table, resolve_model, rate_for, PREFIXES

class PriceTests(unittest.TestCase):
    def setUp(self):
        self.table = load_table()
    def test_bundled_table_has_header(self):
        m = self.table["meta"]
        for k in ("source_url", "as_of", "upstream_sha", "generated_by"): self.assertIn(k, m)
    def test_known_models_resolve_directly(self):
        for m in ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"):
            self.assertEqual(resolve_model(m, self.table), m)
    def test_prefix_and_date_stripping(self):
        self.assertEqual(resolve_model("us.anthropic.claude-opus-5", self.table), "claude-opus-5")
        self.assertEqual(resolve_model("azure_ai/gpt-5.5-2026-04-23", self.table), "gpt-5.5")
        self.assertEqual(resolve_model("gpt-5.5", self.table), "gpt-5.5")
    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_model("nano_banana", self.table)); self.assertIsNone(resolve_model("<synthetic>", self.table))
    def test_rates_are_decimal_per_token(self):
        r = rate_for("claude-opus-5", self.table)
        self.assertIsInstance(r["in"], Decimal); self.assertEqual(r["in"], Decimal("0.000005"))
        self.assertEqual(r["cache_write"], Decimal("0.00000625")); self.assertEqual(r["cache_read"], Decimal("0.0000005"))
    def test_openai_has_zero_cache_write(self):
        self.assertEqual(rate_for("gpt-5.5", self.table)["cache_write"], Decimal("0"))
    def test_override_path(self):
        d = tempfile.mkdtemp(); p = pathlib.Path(d) / "r.json"
        p.write_text(json.dumps({"meta": {"source_url": "x", "as_of": "2026-01-01", "upstream_sha": "", "generated_by": "test"},
                                 "models": {"my-model": {"in": "0.000001", "out": "0.000002", "cache_write": "0", "cache_read": "0"}}}))
        t = load_table(p); self.assertEqual(rate_for("my-model", t)["out"], Decimal("0.000002"))
    def test_prefix_list_is_ordered_longest_first(self):
        self.assertEqual(PREFIXES, sorted(PREFIXES, key=len, reverse=True))
    def test_play_layout_resolution(self):
        # Simulate plays/<slug>/resources/{comped_core, prices.json}: the table must be found beside the package dir.
        import shutil
        from comped_core import prices as pm
        d = pathlib.Path(tempfile.mkdtemp()).resolve()  # macOS /var -> /private/var; _bundled() resolves symlinks
        shutil.copytree(pathlib.Path(pm.__file__).parent, d / "comped_core")
        shutil.copy(pathlib.Path("resources/prices.json"), d / "prices.json")
        r = __import__("subprocess").run([__import__("sys").executable, "-c", "from comped_core.prices import BUNDLED; print(BUNDLED)"], cwd=d, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), str(d / "prices.json"))
