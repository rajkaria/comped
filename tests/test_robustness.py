import unittest, tempfile, pathlib, os, subprocess, sys, json
class Robustness(unittest.TestCase):
    def _run(self, claude_dir):
        p = subprocess.run([sys.executable, "-m", "comped_core", "ledger", "--claude-dir", claude_dir, "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", tempfile.mkdtemp(), "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1]), p.stderr
    def test_empty_and_missing_dirs(self):
        rc, j, err = self._run(tempfile.mkdtemp()); self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertEqual(j["records"], 0); self.assertEqual(err, "")
        rc, j, _ = self._run("/definitely/missing"); self.assertEqual(rc, 0); self.assertFalse(j["sources"][0]["found"])
    def test_garbage_files(self):
        d = pathlib.Path(tempfile.mkdtemp()); proj = d / "p"; proj.mkdir()
        (proj / "a.jsonl").write_text('{"type":"assistant","message":{"usage":{}}}\n{"type":"assistant"}\n\x00\x01binary\n{"type":"user","message":{"content":[]}}\n{"trunc')
        (proj / "b.jsonl").write_bytes(b"\xff\xfe\x00\x00")
        rc, j, err = self._run(str(d)); self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertGreater(j["sources"][0]["unparsed"], 0)
    def test_unreadable_file(self):
        d = pathlib.Path(tempfile.mkdtemp()); proj = d / "p"; proj.mkdir(); f = proj / "a.jsonl"; f.write_text("{}\n"); os.chmod(f, 0)
        try:
            rc, j, _ = self._run(str(d)); self.assertEqual(rc, 0); self.assertIn("unreadable", j["sources"][0]["note"])
        finally: os.chmod(f, 0o644)
