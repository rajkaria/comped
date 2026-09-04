import unittest, pathlib
from datetime import datetime, timezone
from comped_core.adapters import pi, opencode
S = datetime(2026, 8, 1, tzinfo=timezone.utc)
class PiOpenCodeTests(unittest.TestCase):
    def test_pi(self):
        recs, humans, tools, src = pi.parse(pathlib.Path("resources/fixtures/pi"), S, True, True)
        self.assertEqual(len(recs), 2); self.assertEqual(recs[0].cache_read_tokens, 8000); self.assertEqual(recs[0].reasoning_tokens, 50)
        self.assertEqual(recs[0].model, "claude-sonnet-5"); self.assertEqual(humans[0].text, "fix the failing test and rerun"); self.assertIn("best-effort", src.note)
    def test_opencode(self):
        recs, humans, tools, src = opencode.parse(pathlib.Path("resources/fixtures/opencode/storage"), S, True, True)
        self.assertEqual(len(recs), 1); self.assertEqual(recs[0].model, "deepseek-chat"); self.assertEqual(recs[0].cache_read_tokens, 3000)
        self.assertEqual(recs[0].timestamp, "2026-09-01T08:40:05Z"); self.assertEqual(humans[0].text, "push it to prod")
    def test_missing(self):
        self.assertFalse(pi.parse(pathlib.Path("/nope"), S, True, True)[3].found)
        self.assertFalse(opencode.parse(pathlib.Path("/nope"), S, True, True)[3].found)
