import unittest, dataclasses
from comped_core.models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger

class ModelTests(unittest.TestCase):
    def test_usage_record_is_frozen_and_serialisable(self):
        r = UsageRecord("claude-code", "s", "r", "2026-09-03T00:00:00Z", "claude-opus-5", 1, 2, 3, 4, 1, "proj", False, "t")
        with self.assertRaises(dataclasses.FrozenInstanceError): r.model = "x"
        self.assertEqual(dataclasses.asdict(r)["cache_read_tokens"], 3)
    def test_ledger_defaults(self):
        l = Ledger(records=[], humans=[], tools=[], sources=[], generated_at="2026-09-03T00:00:00Z")
        self.assertEqual(l.records, [])
