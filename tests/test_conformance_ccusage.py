import unittest, shutil, subprocess, json, tempfile, sys, pathlib
from decimal import Decimal
class CcusageConformance(unittest.TestCase):
    def test_claude_totals_match_ccusage(self):
        if not shutil.which("npx"): self.skipTest("npx not available")
        out = tempfile.mkdtemp()
        subprocess.run([sys.executable, "-m", "comped_core", "ledger", "--claude-dir", "resources/fixtures/claude", "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", out, "--days-back", "3650", "--now", "2026-12-31T00:00:00Z"], check=True, capture_output=True)
        p = subprocess.run([sys.executable, "-m", "comped_core", "price", "--out-dir", out], capture_output=True, text=True, check=True)
        ours = {m["model"]: (m["input"], m["cache_write"], m["cache_read"], m["output"]) for m in json.loads(p.stdout.splitlines()[-1])["per_model"]}
        # ccusage reads $CLAUDE_CONFIG_DIR/projects; our fixture root is resources/fixtures/claude, so symlink it
        cfg = pathlib.Path(tempfile.mkdtemp()); (cfg / "projects").symlink_to(pathlib.Path("resources/fixtures/claude").resolve())
        env = {"CLAUDE_CONFIG_DIR": str(cfg), "PATH": subprocess.os.environ["PATH"], "HOME": subprocess.os.environ.get("HOME", "")}
        try: r = subprocess.run(["npx", "-y", "ccusage@latest", "daily", "--json", "--offline"], capture_output=True, text=True, timeout=300, env=env, check=True)
        except (subprocess.SubprocessError, OSError) as e: self.skipTest("ccusage unavailable: {0}".format(e))
        cc = json.loads(r.stdout)
        theirs = {}
        for day in cc.get("daily", []):
            for mb in day.get("modelBreakdowns", []):
                t = theirs.setdefault(mb["modelName"], [0, 0, 0, 0])
                t[0] += mb["inputTokens"]; t[1] += mb["cacheCreationTokens"]; t[2] += mb["cacheReadTokens"]; t[3] += mb["outputTokens"]
        self.assertTrue(theirs, "ccusage reported no model breakdowns; cannot conform")
        for model, toks in ours.items():
            if model in theirs: self.assertEqual(tuple(theirs[model]), toks, model)
