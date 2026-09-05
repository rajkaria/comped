import unittest, tempfile, pathlib, json, subprocess, sys
FIX = {"--claude-dir": "resources/fixtures/claude", "--codex-dir": "resources/fixtures/codex", "--pi-dir": "resources/fixtures/pi", "--opencode-dir": "resources/fixtures/opencode/storage"}
NOW = "2026-09-03T00:00:00Z"
def run(*args):
    p = subprocess.run([sys.executable, "-m", "comped_core"] + list(args), capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else None), p.stdout, p.stderr
class CliTests(unittest.TestCase):
    def setUp(self): self.out = tempfile.mkdtemp()
    def _ledger(self):
        return run("ledger", *sum(([k, v] for k, v in FIX.items()), []), "--days-back", "3650", "--out-dir", self.out, "--include-subagents", "true", "--redact", "true", "--now", NOW)
    def test_only_and_merge_equal_full_ledger(self):
        full = tempfile.mkdtemp(); parts = tempfile.mkdtemp()
        run("ledger", *sum(([k, v] for k, v in FIX.items()), []), "--days-back", "3650", "--out-dir", full, "--now", NOW)
        for h in ("claude-code", "codex", "pi", "opencode"):
            rc, j, _o, _e = run("ledger", *sum(([k, v] for k, v in FIX.items()), []), "--days-back", "3650", "--out-dir", parts, "--now", NOW, "--only", h)
            self.assertEqual(rc, 0); self.assertTrue(pathlib.Path(parts, "ledger-{0}.jsonl".format(h)).exists())
        rc, j, _o, _e = run("merge", "--out-dir", parts); self.assertEqual(rc, 0)
        self.assertEqual(pathlib.Path(full, "ledger.jsonl").read_bytes(), pathlib.Path(parts, "ledger.jsonl").read_bytes())
    def test_expected_absence_is_warning_not_error(self):
        rc, j, _o, _e = run("ledger", "--claude-dir", "/nope", "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", self.out, "--now", NOW)
        self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertIn("warning", j)
    def test_full_pipeline(self):
        rc, j, _o, _e = self._ledger(); self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertTrue(pathlib.Path(self.out, "ledger.jsonl").exists())
        rc, j, _o, _e = run("price", "--out-dir", self.out, "--plan", "claude-max-200,chatgpt-plus-20", "--days-back", "3650", "--now", NOW)
        self.assertEqual(rc, 0); self.assertGreater(float(j["total_usd"]), 0); self.assertIsNotNone(j["multiplier"])
        rc, j, _o, _e = run("repeats", "--out-dir", self.out, "--repeat-threshold", "3", "--handle", "priya"); self.assertEqual(rc, 0); self.assertGreaterEqual(len(j["repeats"]), 1)
        rc, j, out, _e = run("card", "--out-dir", self.out, "--card-theme", "dark"); self.assertEqual(rc, 0)
        self.assertIn("COMPED", out); self.assertTrue(pathlib.Path(self.out, "comped-card.svg").exists()); self.assertTrue(pathlib.Path(self.out, "comped-report.md").exists())
        rc, j, _o, _e = run("wrongturns", "--out-dir", self.out, "--min-recurrence", "2", "--show-snippets", "true"); self.assertEqual(rc, 0)
        rc, j, _o, _e = run("rules", "--out-dir", self.out, "--rules-target", "both"); self.assertEqual(rc, 0); self.assertTrue(pathlib.Path(self.out, "wrong-turns-rules.md").exists())
        rc, j, _o, _e = run("verify", "--out-dir", self.out); self.assertEqual(rc, 0); self.assertTrue(j["ok"])
        rc, j, _o, _e = run("sources", *sum(([k, v] for k, v in FIX.items()), [])); self.assertEqual(rc, 0); self.assertTrue(all(s["found"] for s in j["sources"]))
        rc, j, _o, _e = run("summary", "--out-dir", self.out); self.assertEqual(rc, 0); self.assertGreater(j["records"], 0)
    def test_run_is_the_pipeline_in_one_command(self):
        # `run` exists so a shell with no runner in front of it is one command, not four in an order
        # that must not change. If it ever stops producing what the four steps produce, it is a
        # second implementation of the arithmetic, and the Play and the CLI have started to disagree.
        one, steps = tempfile.mkdtemp(), tempfile.mkdtemp()
        fix = sum(([k, v] for k, v in FIX.items()), [])
        rc, j, out, _e = run("run", *fix, "--days-back", "3650", "--now", NOW, "--out-dir", one, "--handle", "priya")
        self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertIn("COMPED", out)
        self.assertGreater(float(j["total_usd"]), 0); self.assertGreaterEqual(j["repeats"], 1)
        self.assertEqual(j["report"], str(pathlib.Path(one, "comped-report.md")))
        run("ledger", *fix, "--days-back", "3650", "--now", NOW, "--out-dir", steps)
        run("price", "--out-dir", steps, "--days-back", "3650", "--now", NOW)
        run("repeats", "--out-dir", steps, "--handle", "priya")
        run("card", "--out-dir", steps)
        for name in ("ledger.jsonl", "comped-card.svg", "comped-explain.txt", "comped-share.txt", "comped-baseline.json"):
            self.assertEqual(pathlib.Path(one, name).read_bytes(), pathlib.Path(steps, name).read_bytes(), name)
        # The report lists the paths it wrote, so it differs by out_dir and by nothing else.
        self.assertEqual(pathlib.Path(one, "comped-report.md").read_text().replace(one, "OUT"),
                         pathlib.Path(steps, "comped-report.md").read_text().replace(steps, "OUT"))

    def test_run_with_no_logs_to_read_says_what_to_do_and_exits_1(self):
        rc, j, _o, _e = run("run", "--claude-dir", "/nope", "--codex-dir", "/nope", "--pi-dir", "/nope",
                            "--opencode-dir", "/nope", "--out-dir", self.out, "--now", NOW)
        self.assertEqual(rc, 1); self.assertFalse(j["ok"])
        self.assertIn("nothing to read", j["error"]); self.assertIn("--days-back", j["note"])

    def test_bad_args_exit_2_json(self):
        rc, j, _o, _e = run("price", "--out-dir", self.out, "--days-back", "x"); self.assertEqual(rc, 2); self.assertFalse(j["ok"])
    def test_missing_ledger_is_json_error(self):
        rc, j, _o, _e = run("card", "--out-dir", self.out); self.assertEqual(rc, 1); self.assertFalse(j["ok"]); self.assertIn("ledger", j["error"])
