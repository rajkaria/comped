import unittest, subprocess, sys
class PlaySync(unittest.TestCase):
    def test_sync_then_check_is_clean(self):
        subprocess.run([sys.executable, "tools/sync_plays.py"], check=True, capture_output=True)
        r = subprocess.run([sys.executable, "tools/sync_plays.py", "--check"], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stdout)
    def test_play_runs_from_its_own_resources(self):
        r = subprocess.run([sys.executable, "plays/comped/resources/comped_core/cli.py", "ledger", "--claude-dir", "plays/comped/resources/fixtures/claude", "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", "out/test-play", "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
