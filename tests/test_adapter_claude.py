import json, tempfile, unittest, pathlib
from datetime import datetime, timezone
from comped_core.adapters import claude_code

def _w(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

def _asst(sid, mid, rid, block, model="claude-opus-5", ts="2026-09-02T10:00:05Z", side=False, content=None):
    return {"type": "assistant", "sessionId": sid, "requestId": rid, "apiBlockIndex": block, "isSidechain": side,
            "timestamp": ts, "cwd": "/home/demo/p1", "uuid": "u-{0}-{1}".format(mid, block),
            "message": {"id": mid, "model": model, "role": "assistant", "content": content or [{"type": "text", "text": "hi"}],
                        "usage": {"input_tokens": 2, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000,
                                  "output_tokens": 50, "output_tokens_details": {"thinking_tokens": 10}}}}

def _user(sid, uid, text, ts="2026-09-02T10:00:00Z", origin="human", meta=False):
    d = {"type": "user", "sessionId": sid, "uuid": uid, "timestamp": ts, "cwd": "/home/demo/p1", "isSidechain": False,
         "message": {"role": "user", "content": text}}
    if origin: d["origin"] = {"kind": origin}
    if meta: d["isMeta"] = True
    return d

class ClaudeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        proj = self.root / "-home-demo-p1"
        _w(proj / "s1.jsonl", [
            _user("s1", "h1", "fix the failing test"),
            _asst("s1", "m1", "r1", 0), _asst("s1", "m1", "r1", 1),            # duplicate pair
            {"type": "user", "sessionId": "s1", "uuid": "t1", "timestamp": "2026-09-02T10:00:06Z", "isSidechain": False,
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "is_error": True, "content": "ENOENT: no such file /home/demo/p1/x.py"}]}},
            _asst("s1", "m2", "r2", 0, ts="2026-09-02T10:00:07Z", content=[{"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "cat x.py"}}]),
            _asst("s1", "m3", "r3", 0, model="<synthetic>", ts="2026-09-02T10:00:08Z"),
            _user("s1", "h2", "<system-reminder>injected</system-reminder>", ts="2026-09-02T10:00:09Z", origin=None),
            _user("s1", "h3", "You are a Claude-Mem observer", ts="2026-09-02T10:00:10Z", origin=None),
            _user("s1", "h4", "old message", ts="2026-07-01T00:00:00Z"),
        ])
        _w(proj / "s1" / "subagents" / "agent-abc.jsonl", [_asst("s1", "m9", "r9", 0, ts="2026-09-02T10:00:06Z")])
        _w(proj / "memory" / "notes.jsonl", [{"type": "assistant", "message": {"usage": {"input_tokens": 999}}}])
        self.since = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def test_dedup_and_synthetic(self):
        recs, humans, tools, src = claude_code.parse(self.root, self.since, True, True)
        ids = sorted(r.record_id for r in recs)
        self.assertEqual(ids, ["m1|r1", "m2|r2", "m9|r9"])
        self.assertEqual(src.duplicates, 1); self.assertEqual(src.files, 2)
        self.assertTrue(any(r.is_subagent for r in recs))
        self.assertIn("synthetic", src.note)

    def test_usage_mapping(self):
        recs, *_ = claude_code.parse(self.root, self.since, True, True)
        r = next(x for x in recs if x.record_id == "m1|r1")
        self.assertEqual((r.input_tokens, r.cache_write_tokens, r.cache_read_tokens, r.output_tokens, r.reasoning_tokens), (2, 100, 1000, 50, 10))
        self.assertEqual(r.project, "/home/demo/p1"); self.assertEqual(r.harness, "claude-code")

    def test_humans_filtered_and_windowed(self):
        _, humans, _, _ = claude_code.parse(self.root, self.since, True, True)
        self.assertEqual([h.text for h in humans if h.origin == "human"], ["fix the failing test"])
        autos = [h for h in humans if h.origin == "automated"]
        self.assertEqual(len(autos), 2)   # injected + "You are" kept but labelled automated

    def test_tool_error_with_name(self):
        _, _, tools, _ = claude_code.parse(self.root, self.since, True, True)
        self.assertEqual(len(tools), 1); t = tools[0]
        self.assertTrue(t.is_error); self.assertEqual(t.tool_name, "Bash"); self.assertIn("ENOENT", t.error_text)
        self.assertIn("cat x.py", t.input_summary)

    def test_exclude_subagents_flag(self):
        recs, *_ = claude_code.parse(self.root, self.since, False, True)
        self.assertFalse(any(r.is_subagent for r in recs))

    def test_missing_root(self):
        recs, humans, tools, src = claude_code.parse(pathlib.Path("/nope"), self.since, True, True)
        self.assertEqual(recs, []); self.assertFalse(src.found)
