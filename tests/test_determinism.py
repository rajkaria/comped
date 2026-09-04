import unittest, tempfile, pathlib, subprocess, sys, hashlib
FIX = ["--claude-dir", "resources/fixtures/claude", "--codex-dir", "resources/fixtures/codex", "--pi-dir", "resources/fixtures/pi", "--opencode-dir", "resources/fixtures/opencode/storage"]
def pipeline(out):
    for args in (["ledger"] + FIX + ["--days-back", "3650", "--now", "2026-09-03T00:00:00Z"],
                 ["price", "--plan", "claude-max-200", "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"],
                 ["repeats", "--handle", "demo"], ["card"], ["wrongturns", "--min-recurrence", "2"], ["rules"]):
        subprocess.run([sys.executable, "-m", "comped_core"] + args + ["--out-dir", out], check=True, capture_output=True,
                       env={"NO_COLOR": "1", "PATH": ""})
    # Hash content with the output directory normalised away: reports legitimately name the paths
    # they wrote, so two runs into different directories differ there and nowhere else.
    def h(p):
        b = p.read_bytes().replace(str(out).encode(), b"<OUT>")
        return hashlib.sha256(b).hexdigest()
    return {p.name: h(p) for p in pathlib.Path(out).glob("*") if p.suffix in (".md", ".svg", ".txt", ".jsonl", ".json")}
class Determinism(unittest.TestCase):
    def test_two_runs_identical(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp(); ha, hb = pipeline(a), pipeline(b)
        self.assertEqual({k: v for k, v in ha.items() if k != "comped-baseline.json"}, {k: v for k, v in hb.items() if k != "comped-baseline.json"})
