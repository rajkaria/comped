import json, tempfile, unittest, pathlib
from datetime import datetime, timezone
from comped_core.adapters import codex

def _tc(ts, inp, cached, out, reas):
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out, "reasoning_output_tokens": reas, "total_tokens": inp + out},
        "last_token_usage": {}, "model_context_window": 258400}, "rate_limits": None}}

class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp()); d = self.root / "2026" / "09" / "01"; d.mkdir(parents=True)
        rows = [
            {"timestamp": "2026-09-01T08:00:00Z", "type": "session_meta", "payload": {"id": "sess1", "cwd": "/home/demo/p", "originator": "Codex CLI", "cli_version": "0.133.0"}},
            {"timestamp": "2026-09-01T08:00:01Z", "type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5.5", "cwd": "/home/demo/p"}},
            {"timestamp": "2026-09-01T08:00:02Z", "type": "event_msg", "payload": {"type": "user_message", "message": "push it to prod"}},
            _tc("2026-09-01T08:00:10Z", 1000, 200, 100, 40),
            _tc("2026-09-01T08:00:11Z", 1000, 200, 100, 40),          # identical snapshot -> zero delta, dropped
            {"timestamp": "2026-09-01T08:00:12Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "{\"cmd\":\"pytest -q\"}", "call_id": "c1"}},
            {"timestamp": "2026-09-01T08:00:13Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": "Chunk ID: x\nWall time: 1\nProcess exited with code 1\nOutput:\nFAILED tests/test_a.py::test_b"}},
            _tc("2026-09-01T08:00:20Z", 3000, 1200, 160, 60),
            {"timestamp": "2026-09-01T08:00:21Z", "type": "turn_context", "payload": {"turn_id": "t2", "model": "gpt-5.4", "cwd": "/home/demo/p"}},
            _tc("2026-09-01T08:00:30Z", 500, 0, 10, 0),               # negative delta -> new baseline
            _tc("2026-09-01T08:00:31Z", 900, 100, 30, 5),
        ]
        (d / "rollout-2026-09-01T08-00-00-sess1.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        self.since = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def test_deltas(self):
        recs, humans, tools, src = codex.parse(self.root, self.since, True, True)
        by_ts = {r.timestamp: r for r in recs}
        r1 = by_ts["2026-09-01T08:00:10Z"]; self.assertEqual((r1.input_tokens, r1.cache_read_tokens, r1.output_tokens, r1.reasoning_tokens), (800, 200, 100, 40))
        r2 = by_ts["2026-09-01T08:00:20Z"]; self.assertEqual((r2.input_tokens, r2.cache_read_tokens, r2.output_tokens), (1000, 1000, 60))
        self.assertEqual(r2.model, "gpt-5.5")
        r3 = by_ts["2026-09-01T08:00:30Z"]; self.assertEqual((r3.input_tokens, r3.output_tokens), (500, 10)); self.assertEqual(r3.model, "gpt-5.4")
        r4 = by_ts["2026-09-01T08:00:31Z"]; self.assertEqual((r4.input_tokens, r4.cache_read_tokens, r4.output_tokens), (300, 100, 20))
        self.assertEqual(len(recs), 4); self.assertEqual(src.duplicates, 1); self.assertIn("baseline reset", src.note)
        self.assertTrue(all(r.cache_write_tokens == 0 for r in recs))

    def test_humans_and_tools(self):
        recs, humans, tools, src = codex.parse(self.root, self.since, True, True)
        self.assertEqual([h.text for h in humans], ["push it to prod"]); self.assertEqual(humans[0].origin, "human")
        self.assertEqual(len(tools), 1); self.assertTrue(tools[0].is_error); self.assertEqual(tools[0].tool_name, "exec_command")
        self.assertIn("pytest -q", tools[0].input_summary); self.assertIn("FAILED", tools[0].error_text)
        self.assertEqual(recs[0].session_id, "sess1"); self.assertEqual(recs[0].project, "/home/demo/p")
