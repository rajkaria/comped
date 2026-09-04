import unittest, time, tempfile, subprocess, sys, pathlib, os
class Perf(unittest.TestCase):
    def test_real_logs_under_10s(self):
        home = pathlib.Path.home()
        if not (home / ".claude" / "projects").is_dir() or os.environ.get("CI"): self.skipTest("no real logs or CI")
        t = time.time()
        subprocess.run([sys.executable, "-m", "comped_core", "ledger", "--out-dir", tempfile.mkdtemp(), "--days-back", "30"], check=True, capture_output=True)
        self.assertLess(time.time() - t, 10.0)
