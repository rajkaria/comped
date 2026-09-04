import unittest, tempfile, pathlib, json
from datetime import datetime, timezone
from comped_core.models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger
from comped_core.ledger import attribute_turns, write_ledger, read_ledger, summary
from comped_core.adapters import parse_all

def R(ts, sid="s", sub=False): return UsageRecord("claude-code", sid, "r{0}".format(ts), ts, "claude-opus-5", 1, 0, 0, 1, 0, "/p", sub, "")
def H(ts, mid, origin="human", sid="s"): return HumanMessage("claude-code", sid, mid, ts, "t", "h", "/p", origin)

class LedgerTests(unittest.TestCase):
    def test_turn_attribution(self):
        l = Ledger([R("2026-09-01T10:00:05Z"), R("2026-09-01T10:00:01Z"), R("2026-09-01T09:59:00Z"), R("2026-09-01T10:00:06Z", sub=True)],
                   [H("2026-09-01T10:00:00Z", "h1"), H("2026-09-01T10:00:04Z", "auto", origin="automated"), H("2026-09-01T10:00:05Z", "h2")],
                   [ToolEvent("claude-code", "s", "e1", "2026-09-01T10:00:03Z", "Bash", "x", True, "err", "")], [], "2026-09-03T00:00:00Z")
        attribute_turns(l)
        by = {r.record_id: r.turn_id for r in l.records}
        self.assertEqual(by["r2026-09-01T09:59:00Z"], "s:pre"); self.assertEqual(by["r2026-09-01T10:00:01Z"], "h1")
        self.assertEqual(by["r2026-09-01T10:00:05Z"], "h2"); self.assertEqual(by["r2026-09-01T10:00:06Z"], "h2")
        self.assertEqual(l.tools[0].turn_id, "h1")

    def test_roundtrip_and_summary(self):
        d = pathlib.Path(tempfile.mkdtemp())
        l = Ledger([R("2026-09-01T10:00:05Z")], [H("2026-09-01T10:00:00Z", "h1")], [], [Source("claude-code", "/x", True, 1, 10, 9, 3, 1, "")], "2026-09-03T00:00:00Z")
        attribute_turns(l); paths = write_ledger(l, d)
        self.assertEqual(sorted(p.split("/")[-1] for p in paths), ["ledger-summary.json", "ledger.jsonl"])
        l2 = read_ledger(d)
        self.assertEqual(l2.records[0], l.records[0]); self.assertEqual(l2.humans[0], l.humans[0]); self.assertEqual(l2.sources[0].duplicates, 3)
        s = summary(l)
        self.assertEqual(s["records"], 1); self.assertEqual(s["sources"][0]["harness"], "claude-code"); self.assertEqual(s["schema_version"], 1)

    def test_parse_all_on_fixtures(self):
        cfg = {"claude_dir": "resources/fixtures/claude", "codex_dir": "resources/fixtures/codex", "pi_dir": "resources/fixtures/pi",
               "opencode_dir": "resources/fixtures/opencode/storage", "include_subagents": True, "redact": True,
               "since": datetime(2020, 1, 1, tzinfo=timezone.utc), "now": datetime(2026, 9, 3, tzinfo=timezone.utc)}
        l = parse_all(cfg)
        self.assertEqual([s.harness for s in l.sources], ["claude-code", "codex", "opencode", "pi"])
        self.assertTrue(all(s.found for s in l.sources)); self.assertTrue(len(l.records) > 10)
        self.assertTrue(all(r.turn_id for r in l.records)); self.assertTrue(any(r.is_subagent for r in l.records))
        self.assertEqual(l.records, sorted(l.records, key=lambda r: (r.harness, r.session_id, r.timestamp, r.record_id)))
