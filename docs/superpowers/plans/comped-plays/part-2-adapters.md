# Part 2 — Tasks 3–5: harness adapters and fixtures

Every adapter exposes the same function signature and never raises:

```python
def parse(root: Path, since: datetime, include_subagents: bool, redact: bool) -> AdapterResult
# AdapterResult = (records: list[UsageRecord], humans: list[HumanMessage], tools: list[ToolEvent], source: Source)
```

`turn_id` is left as `""` by adapters except where the harness gives it directly; `ledger.attribute_turns` (Part 3) fills it by timestamp. Adapters set `record_id` to a stable dedup key. Text redaction is done through `comped_core/textnorm.redact(text, redact) -> (text, sha)` which Part 4 owns; for Part 2 create a minimal `comped_core/redact.py` with that function and have textnorm import it later.

---

## Task 3: Claude Code adapter and fixture generator

**Files:**
- Create: `comped_core/redact.py`, `comped_core/adapters/__init__.py` (registry stub), `comped_core/adapters/claude_code.py`, `tools/make_fixtures.py` (Claude part), `resources/fixtures/claude/...`
- Test: `tests/test_adapter_claude.py`, `tests/test_fixture_privacy.py`

**Interfaces:**
- Consumes: `iter_jsonl`, `JsonlStats`, `parse_ts`, `iso`, models.
- Produces: `claude_code.parse(...)`, `redact.redact(text, on) -> (str, str)`.

Facts the adapter encodes (measured, see LANDSCAPE.md):
- Layout: `<root>/<project-slug>/<session>.jsonl`; subagents at `<root>/<project-slug>/<session>/subagents/agent-*.jsonl`; skip `memory/`, `tool-results/`, `workflows/` dirs.
- Assistant usage line: `type == "assistant"`, `message.usage`, `message.model`, `message.id`, `requestId`, `apiBlockIndex`, `isSidechain`, `timestamp`, `sessionId`, `cwd`.
- Dedup key `(message.id, requestId)`; 41% duplicates. Drop `model == "<synthetic>"`, count them.
- Human line: `type == "user"`, not `isSidechain`, not `isMeta`, `message.content` is a `str`, or a list containing `{"type":"text"}` blocks and no `tool_result`. `origin.kind` when present.
- Tool result line: `type == "user"`, `message.content` list with `{"type":"tool_result","is_error":bool,"content":...,"tool_use_id":...}`; the tool name comes from the preceding assistant `tool_use` block with the same id (`message.content[].type == "tool_use"`, `.name`, `.input`).

- [ ] **Step 1: Write `comped_core/redact.py` (tiny, shared).**

```python
import hashlib

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()

def redact(text: str, on: bool, keep: int = 120):
    """Return (stored_text, sha256). With redaction on, stored_text is the first `keep` chars, whitespace-collapsed."""
    t = " ".join((text or "").split())
    h = sha(t)
    if on and len(t) > keep:
        t = t[:keep] + "…"
    return t, h
```

- [ ] **Step 2: Write the failing adapter tests against a hand-written mini fixture.**

`tests/test_adapter_claude.py`:
```python
import json, tempfile, unittest, pathlib
from datetime import datetime, timezone
from comped_core.adapters import claude_code

def _w(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

def _asst(sid, mid, rid, block, model="claude-opus-5", ts="2026-09-02T10:00:05Z", side=False, content=None):
    return {"type": "assistant", "sessionId": sid, "requestId": rid, "apiBlockIndex": block, "isSidechain": side,
            "timestamp": ts, "cwd": "/home/demo/p1", "uuid": f"u-{mid}-{block}",
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
```

- [ ] **Step 3: Run tests to verify they fail.** Expected: `ModuleNotFoundError: comped_core.adapters`.

- [ ] **Step 4: Write `comped_core/adapters/__init__.py` (registry; `parse_all` is completed in Part 3).**

```python
from pathlib import Path
from . import claude_code, codex, pi, opencode

ADAPTERS = {
    "claude-code": (claude_code, "claude_dir"),
    "codex": (codex, "codex_dir"),
    "pi": (pi, "pi_dir"),
    "opencode": (opencode, "opencode_dir"),
}
```
(Create empty `pi.py` and `opencode.py` modules now with a `parse` that returns an empty result and `Source(found=False, note="adapter pending")`, so the import works; Task 5 fills them.)

- [ ] **Step 5: Write `comped_core/adapters/claude_code.py`.**

```python
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from ..models import UsageRecord, HumanMessage, ToolEvent, Source
from ..jsonl import iter_jsonl, JsonlStats
from ..timeutil import parse_ts, iso
from ..redact import redact

HARNESS = "claude-code"
SKIP_DIRS = {"memory", "tool-results", "workflows"}
AUTOMATED_PREFIXES = ("<", "You are ", "you are ")

def _iter_files(root: Path, include_subagents: bool):
    for proj in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(proj.glob("*.jsonl")):
            yield f, False
        if include_subagents:
            for sess in sorted(p for p in proj.iterdir() if p.is_dir() and p.name not in SKIP_DIRS):
                for f in sorted((sess / "subagents").glob("agent-*.jsonl")):
                    yield f, True

def _summ(inp) -> str:
    if isinstance(inp, dict):
        for k in ("command", "file_path", "pattern", "query", "url", "description", "prompt"):
            if k in inp and isinstance(inp[k], str):
                return " ".join(inp[k].split())[:80]
        return " ".join(str(inp).split())[:80]
    return " ".join(str(inp or "").split())[:80]

def _text_of(content) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""

def _err_text(content) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return str(content or "")

def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool) -> Tuple[List[UsageRecord], List[HumanMessage], List[ToolEvent], Source]:
    src = Source(HARNESS, str(root))
    recs: List[UsageRecord] = []; humans: List[HumanMessage] = []; tools: List[ToolEvent] = []
    root = Path(root).expanduser()
    if not root.is_dir():
        src.note = "directory not found"; return recs, humans, tools, src
    src.found = True
    seen = set(); synthetic = 0
    for f, is_sub in _iter_files(root, include_subagents):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=since.tzinfo) < since: continue
        except OSError: continue
        src.files += 1
        stats = JsonlStats()
        tool_names = {}  # tool_use_id -> (name, input_summary)
        for _, o in iter_jsonl(f, stats):
            t = o.get("type"); ts = parse_ts(o.get("timestamp"))
            sid = str(o.get("sessionId") or f.stem); proj = str(o.get("cwd") or f.parent.name)
            msg = o.get("message") if isinstance(o.get("message"), dict) else {}
            if t == "assistant":
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_names[b.get("id")] = (str(b.get("name") or "tool"), _summ(b.get("input")))
                u = msg.get("usage")
                if not isinstance(u, dict) or ts is None or ts < since: continue
                model = str(msg.get("model") or "")
                if model == "<synthetic>": synthetic += 1; continue
                key = f"{msg.get('id') or o.get('uuid')}|{o.get('requestId') or ''}"
                if key in seen: src.duplicates += 1; continue
                seen.add(key)
                det = u.get("output_tokens_details") if isinstance(u.get("output_tokens_details"), dict) else {}
                recs.append(UsageRecord(HARNESS, sid, key, iso(ts), model,
                    int(u.get("input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0),
                    int(u.get("cache_read_input_tokens") or 0), int(u.get("output_tokens") or 0),
                    int(det.get("thinking_tokens") or 0), proj, bool(is_sub or o.get("isSidechain")), ""))
            elif t == "user" and not is_sub:
                if ts is None or ts < since or o.get("isSidechain"): continue
                content = msg.get("content")
                if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            name, summ = tool_names.get(b.get("tool_use_id"), ("tool", ""))
                            err = bool(b.get("is_error"))
                            tools.append(ToolEvent(HARNESS, sid, str(o.get("uuid") or f"{f.stem}:{stats.lines}"), iso(ts), name, summ, err,
                                                   " ".join(_err_text(b.get("content")).split())[:300] if err else "", ""))
                    continue
                text = _text_of(content)
                if not text.strip() or o.get("isMeta"): continue
                origin = (o.get("origin") or {}).get("kind") if isinstance(o.get("origin"), dict) else None
                if origin is None:
                    origin = "automated" if text.lstrip().startswith(AUTOMATED_PREFIXES) or "[Request interrupted" in text else "unknown"
                elif origin != "human":
                    origin = "automated"
                stored, h = redact(text, redact_on)
                humans.append(HumanMessage(HARNESS, sid, str(o.get("uuid") or f"{f.stem}:{stats.lines}"), iso(ts), stored, h, proj, origin))
        src.lines += stats.lines; src.parsed += stats.parsed; src.unparsed += stats.unparsed
        if stats.note: src.note = (src.note + "; " + stats.note).strip("; ")
    if synthetic: src.note = (src.note + f"; {synthetic} synthetic lines skipped").strip("; ")
    return recs, humans, tools, src
```

- [ ] **Step 6: Run the tests.** Expected: 6 tests pass. Note the `test_humans_filtered_and_windowed` case: "old message" is dropped by `since`; the two automated ones are kept and labelled so Part 4 can exclude them while the ledger stays complete.

- [ ] **Step 7: Write the fixture generator (Claude half) and generate fixtures.**

`tools/make_fixtures.py` (Codex half added in Task 4):
```python
#!/usr/bin/env python3
"""Derive synthetic fixtures from real logs. Keeps structure, token counts, models, timestamps (shifted), dedup pattern,
subagent layout. Replaces all text with deterministic lorem seeded by the text's hash. Replaces paths with /home/demo/project-N.
Usage: python3 tools/make_fixtures.py claude ~/.claude/projects 3   (3 = number of sessions to sample)"""
import json, sys, hashlib, random, re, pathlib, datetime

WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo "
         "sierra tango uniform victor whiskey xray yankee zulu build test deploy fix rename refactor push commit").split()
REPEATS = ["push it to prod", "merge and push to main and then save-context", "create a post for the launch with all metrics",
           "fix the failing test and rerun", "update the readme with the new commands"]
SHIFT = datetime.timedelta(days=0)

def lorem(text: str, n=None) -> str:
    rnd = random.Random(hashlib.sha256(text.encode("utf-8", "replace")).hexdigest())
    n = n or min(max(3, len(text.split()) // 3), 40)
    return " ".join(rnd.choice(WORDS) for _ in range(n))

def clean_path(p: str, table: dict) -> str:
    if p not in table: table[p] = f"/home/demo/project-{len(table) + 1}"
    return table[p]

def scrub(obj, table, is_human=False):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("cwd",): out[k] = clean_path(str(v), table)
            elif k in ("text", "content", "message", "command", "description", "prompt", "output", "file_path") and isinstance(v, str):
                out[k] = v if v.startswith("<system") else lorem(v)
            elif k == "gitBranch": out[k] = "main"
            else: out[k] = scrub(v, table)
        return out
    if isinstance(obj, list): return [scrub(x, table) for x in obj]
    if isinstance(obj, str) and obj.startswith("/Users/"): return clean_path(obj, table)
    return obj

def claude(src: pathlib.Path, n: int, dst=pathlib.Path("resources/fixtures/claude")):
    table = {}
    files = sorted(src.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[: n * 4]
    picked = [f for f in files if f.stat().st_size > 20000][:n]
    for i, f in enumerate(picked):
        proj = dst / f"-home-demo-project-{i + 1}"; proj.mkdir(parents=True, exist_ok=True)
        rows = []
        k = 0
        for line in open(f, errors="replace"):
            try: o = json.loads(line)
            except ValueError: continue
            o = scrub(o, table)
            if o.get("type") == "user" and isinstance(o.get("message", {}).get("content"), str):
                if k % 2 == 0: o["message"]["content"] = REPEATS[k % len(REPEATS)]   # plant repeats deterministically
                k += 1
            rows.append(o)
        (proj / f"{f.stem}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        sub = f.parent / f.stem / "subagents"
        if sub.is_dir():
            (proj / f.stem / "subagents").mkdir(parents=True, exist_ok=True)
            for sf in sorted(sub.glob("agent-*.jsonl"))[:2]:
                rows = [scrub(json.loads(l), table) for l in open(sf, errors="replace") if l.strip().startswith("{")]
                (proj / f.stem / "subagents" / sf.name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"claude fixtures: {len(picked)} sessions → {dst}")

if __name__ == "__main__":
    kind, src, n = sys.argv[1], pathlib.Path(sys.argv[2]).expanduser(), int(sys.argv[3])
    {"claude": claude}[kind](src, n)
```

Run: `python3 tools/make_fixtures.py claude ~/.claude/projects 3` → Expected: `claude fixtures: 3 sessions → resources/fixtures/claude`. Then `du -sh resources/fixtures/claude` under 3 MB; if larger, pick smaller sessions (adjust the size filter).

- [ ] **Step 8: Write the fixture privacy test.**

`tests/test_fixture_privacy.py`:
```python
import unittest, pathlib, re
DENY = re.compile(r"(/Users/|rajkaria|hunch|Argus|Flume|Foundry|chipcount|@gmail|sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{10,})")
class FixturePrivacy(unittest.TestCase):
    def test_no_real_paths_or_names(self):
        for p in pathlib.Path("resources/fixtures").rglob("*.jsonl"):
            for n, line in enumerate(open(p, errors="replace"), 1):
                self.assertIsNone(DENY.search(line), f"{p}:{n} leaks: {DENY.search(line).group(0)}")
```

Run: `python3 -m unittest tests.test_fixture_privacy -v` → Expected: pass. If it fails, extend `scrub` for the leaking key and regenerate.

- [ ] **Step 9: Commit.**

```bash
git add -A && git commit -m "feat(adapters): claude code adapter with dedup, subagents, tool errors; synthetic fixtures"
```

---

## Task 4: Codex adapter and fixtures

**Files:**
- Create: `comped_core/adapters/codex.py`; extend `tools/make_fixtures.py` with `codex(...)`; `resources/fixtures/codex/2026/09/01/rollout-*.jsonl`
- Test: `tests/test_adapter_codex.py`

Facts encoded: layout `<root>/YYYY/MM/DD/rollout-*.jsonl`; `session_meta.payload{id,cwd,originator,cli_version}`; `turn_context.payload{turn_id,model,cwd}`; `event_msg.payload.type ∈ {user_message, token_count, task_started, task_complete, agent_message}`; `token_count.info.total_token_usage` cumulative; `response_item.payload.type ∈ {function_call{name,arguments,call_id}, function_call_output{call_id,output}}`; `input_tokens` includes `cached_input_tokens`; `output_tokens` includes `reasoning_output_tokens`.

- [ ] **Step 1: Write the failing tests.**

`tests/test_adapter_codex.py`:
```python
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
            _tc("2026-09-01T08:00:11Z", 1000, 200, 100, 40),          # identical snapshot → zero delta, dropped
            {"timestamp": "2026-09-01T08:00:12Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "{\"cmd\":\"pytest -q\"}", "call_id": "c1"}},
            {"timestamp": "2026-09-01T08:00:13Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": "Chunk ID: x\nWall time: 1\nProcess exited with code 1\nOutput:\nFAILED tests/test_a.py::test_b"}},
            _tc("2026-09-01T08:00:20Z", 3000, 1200, 160, 60),
            {"timestamp": "2026-09-01T08:00:21Z", "type": "turn_context", "payload": {"turn_id": "t2", "model": "gpt-5.4", "cwd": "/home/demo/p"}},
            _tc("2026-09-01T08:00:30Z", 500, 0, 10, 0),               # negative delta → new baseline
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
```

- [ ] **Step 2: Run to verify failure.** Expected: `AttributeError: module 'comped_core.adapters.codex' has no attribute 'parse'` (or ModuleNotFoundError).

- [ ] **Step 3: Write `comped_core/adapters/codex.py`.**

```python
import json, re
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from ..models import UsageRecord, HumanMessage, ToolEvent, Source
from ..jsonl import iter_jsonl, JsonlStats
from ..timeutil import parse_ts, iso
from ..redact import redact

HARNESS = "codex"
_EXIT = re.compile(r"Process exited with code (\d+)")

def _summ_args(args) -> str:
    try:
        d = json.loads(args) if isinstance(args, str) else (args or {})
    except ValueError:
        return " ".join(str(args).split())[:80]
    if isinstance(d, dict):
        for k in ("cmd", "command", "path", "query", "pattern"):
            if k in d: return " ".join(str(d[k]).split())[:80]
    return " ".join(str(d).split())[:80]

def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool) -> Tuple[List[UsageRecord], List[HumanMessage], List[ToolEvent], Source]:
    src = Source(HARNESS, str(root)); recs = []; humans = []; tools = []
    root = Path(root).expanduser()
    if not root.is_dir():
        src.note = "directory not found"; return recs, humans, tools, src
    src.found = True; resets = 0
    for f in sorted(root.glob("*/*/*/rollout-*.jsonl")):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=since.tzinfo) < since: continue
        except OSError: continue
        src.files += 1; stats = JsonlStats()
        sid = f.stem; proj = ""; model = ""; prev = None; calls = {}
        for _, o in iter_jsonl(f, stats):
            t = o.get("type"); p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
            ts = parse_ts(o.get("timestamp"))
            if t == "session_meta":
                sid = str(p.get("id") or sid); proj = str(p.get("cwd") or proj); continue
            if t == "turn_context":
                model = str(p.get("model") or model); proj = str(p.get("cwd") or proj); continue
            if ts is None or ts < since: continue
            if t == "event_msg":
                pt = p.get("type")
                if pt == "user_message":
                    text = str(p.get("message") or "")
                    if text.strip():
                        stored, h = redact(text, redact_on)
                        humans.append(HumanMessage(HARNESS, sid, f"{sid}:{stats.lines}", iso(ts), stored, h, proj, "human"))
                elif pt == "token_count":
                    tot = ((p.get("info") or {}).get("total_token_usage")) or {}
                    cur = tuple(int(tot.get(k) or 0) for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"))
                    if prev is None or any(c < q for c, q in zip(cur, prev)):
                        if prev is not None: resets += 1
                        d = cur
                    else:
                        d = tuple(c - q for c, q in zip(cur, prev))
                    prev = cur
                    if d == (0, 0, 0, 0):
                        src.duplicates += 1; continue
                    inp, cached, out, reas = d
                    recs.append(UsageRecord(HARNESS, sid, f"{sid}:{stats.lines}", iso(ts), model, max(inp - cached, 0), 0, cached, out, reas, proj, False, ""))
            elif t == "response_item":
                pt = p.get("type")
                if pt == "function_call":
                    calls[p.get("call_id")] = (str(p.get("name") or "tool"), _summ_args(p.get("arguments")))
                elif pt == "function_call_output":
                    name, summ = calls.get(p.get("call_id"), ("tool", ""))
                    out = str(p.get("output") or ""); m = _EXIT.search(out)
                    err = bool(m and m.group(1) != "0")
                    tools.append(ToolEvent(HARNESS, sid, f"{sid}:{stats.lines}", iso(ts), name, summ, err,
                                           " ".join(out.split("Output:", 1)[-1].split())[:300] if err else "", ""))
        src.lines += stats.lines; src.parsed += stats.parsed; src.unparsed += stats.unparsed
    if resets: src.note = (src.note + f"; {resets} baseline reset(s) on non-monotonic counters").strip("; ")
    return recs, humans, tools, src
```

- [ ] **Step 4: Run tests.** Expected: both pass. Check `r2`: totals 3000/1200/160/60 minus 1000/200/100/40 = 2000/1000/60/20 → uncached input 1000, cache_read 1000, output 60.

- [ ] **Step 5: Add the Codex half to `tools/make_fixtures.py` and generate.**

Append before `if __name__`:
```python
def codex(src: pathlib.Path, n: int, dst=pathlib.Path("resources/fixtures/codex/2026/09/01")):
    table = {}; dst.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_size, reverse=True)[:n]
    for i, f in enumerate(files):
        rows = []; k = 0
        for line in open(f, errors="replace"):
            try: o = json.loads(line)
            except ValueError: continue
            p = o.get("payload", {})
            if o.get("type") == "session_meta": p.pop("base_instructions", None); p["id"] = f"demo-sess-{i + 1}"
            if o.get("type") == "turn_context": p.pop("collaboration_mode", None)
            if o.get("type") == "response_item" and p.get("type") == "reasoning": p["encrypted_content"] = ""
            o = scrub(o, table)
            if o.get("type") == "event_msg" and o["payload"].get("type") == "user_message":
                o["payload"]["message"] = REPEATS[k % len(REPEATS)]; k += 1
            o["timestamp"] = "2026-09-01" + str(o.get("timestamp", ""))[10:]
            rows.append(o)
        (dst / f"rollout-2026-09-01T08-00-0{i}-demo-sess-{i + 1}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"codex fixtures: {len(files)} sessions → {dst}")
```
and register `{"claude": claude, "codex": codex}`. Run: `python3 tools/make_fixtures.py codex ~/.codex/sessions 2`, then `python3 -m unittest tests.test_fixture_privacy`.

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit -m "feat(adapters): codex adapter with cumulative-counter differencing; codex fixtures"
```

---

## Task 5: Pi and OpenCode best-effort adapters

**Files:**
- Create/replace: `comped_core/adapters/pi.py`, `comped_core/adapters/opencode.py`, `resources/fixtures/pi/session-1.jsonl`, `resources/fixtures/opencode/storage/message/ses_1/msg_1.json`, `.../msg_2.json`
- Test: `tests/test_adapter_pi_opencode.py`

These schemas come from public docs and were not observed on this machine. Both adapters key on field presence and label their `Source.note` with `best-effort adapter; schema from public docs`.

- [ ] **Step 1: Write hand-made fixtures.**

`resources/fixtures/pi/session-1.jsonl`:
```json
{"type":"message","role":"user","timestamp":"2026-09-01T09:00:00Z","content":"fix the failing test and rerun"}
{"type":"message","role":"assistant","timestamp":"2026-09-01T09:00:05Z","model":"claude-sonnet-5","provider":"anthropic","usage":{"input":1200,"output":300,"cacheRead":8000,"cacheWrite":500,"reasoning":50}}
{"type":"message","role":"assistant","timestamp":"2026-09-01T09:00:09Z","model":"claude-sonnet-5","provider":"anthropic","usage":{"input":100,"output":40,"cacheRead":9000,"cacheWrite":0}}
```

`resources/fixtures/opencode/storage/message/ses_1/msg_1.json`:
```json
{"id":"msg_1","sessionID":"ses_1","role":"user","time":{"created":1788252000000},"parts":[{"type":"text","text":"push it to prod"}]}
```
`resources/fixtures/opencode/storage/message/ses_1/msg_2.json`:
```json
{"id":"msg_2","sessionID":"ses_1","role":"assistant","providerID":"deepseek","modelID":"deepseek-chat","time":{"created":1788252005000,"completed":1788252009000},
 "tokens":{"input":900,"output":200,"reasoning":0,"cache":{"read":3000,"write":0}},"cost":0.0012,"path":{"cwd":"/home/demo/project-1"}}
```

- [ ] **Step 2: Write the failing tests.**

```python
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
```

- [ ] **Step 3: Implement.**

`pi.py`:
```python
from pathlib import Path
from datetime import datetime
from ..models import UsageRecord, HumanMessage, Source
from ..jsonl import iter_jsonl, JsonlStats
from ..timeutil import parse_ts, iso
from ..redact import redact
HARNESS = "pi"
def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool):
    src = Source(HARNESS, str(root), note="best-effort adapter; schema from public docs"); recs = []; humans = []; tools = []
    root = Path(root).expanduser()
    if not root.is_dir(): src.note += "; directory not found"; return recs, humans, tools, src
    src.found = True
    for f in sorted(root.glob("*.jsonl")):
        src.files += 1; stats = JsonlStats(); sid = f.stem
        for _, o in iter_jsonl(f, stats):
            ts = parse_ts(o.get("timestamp") or o.get("time"))
            if ts is None or ts < since: continue
            role = o.get("role"); u = o.get("usage")
            if role == "assistant" and isinstance(u, dict):
                recs.append(UsageRecord(HARNESS, sid, f"{sid}:{stats.lines}", iso(ts), str(o.get("model") or ""),
                    int(u.get("input") or 0), int(u.get("cacheWrite") or 0), int(u.get("cacheRead") or 0), int(u.get("output") or 0),
                    int(u.get("reasoning") or 0), str(o.get("cwd") or ""), False, ""))
            elif role == "user":
                c = o.get("content"); text = c if isinstance(c, str) else "\n".join(b.get("text", "") for b in c or [] if isinstance(b, dict))
                if text.strip():
                    stored, h = redact(text, redact_on); humans.append(HumanMessage(HARNESS, sid, f"{sid}:{stats.lines}", iso(ts), stored, h, "", "human"))
        src.lines += stats.lines; src.parsed += stats.parsed; src.unparsed += stats.unparsed
    return recs, humans, tools, src
```

`opencode.py`:
```python
import json
from pathlib import Path
from datetime import datetime
from ..models import UsageRecord, HumanMessage, Source
from ..timeutil import parse_ts, iso
from ..redact import redact
HARNESS = "opencode"
def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool):
    src = Source(HARNESS, str(root), note="best-effort adapter; schema from public docs"); recs = []; humans = []; tools = []
    base = Path(root).expanduser() / "message"
    if not base.is_dir(): src.note += "; directory not found"; return recs, humans, tools, src
    src.found = True
    for f in sorted(base.rglob("*.json")):
        src.files += 1; src.lines += 1
        try: o = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except ValueError: src.unparsed += 1; continue
        if not isinstance(o, dict): src.unparsed += 1; continue
        src.parsed += 1
        ts = parse_ts((o.get("time") or {}).get("created"))
        if ts is None or ts < since: continue
        sid = str(o.get("sessionID") or f.parent.name)
        if o.get("role") == "assistant" and isinstance(o.get("tokens"), dict):
            t = o["tokens"]; c = t.get("cache") or {}
            recs.append(UsageRecord(HARNESS, sid, str(o.get("id") or f.stem), iso(ts), str(o.get("modelID") or ""),
                int(t.get("input") or 0), int(c.get("write") or 0), int(c.get("read") or 0), int(t.get("output") or 0),
                int(t.get("reasoning") or 0), str((o.get("path") or {}).get("cwd") or ""), False, ""))
        elif o.get("role") == "user":
            text = "\n".join(p.get("text", "") for p in o.get("parts") or [] if isinstance(p, dict) and p.get("type") == "text")
            if text.strip():
                stored, h = redact(text, redact_on); humans.append(HumanMessage(HARNESS, sid, str(o.get("id") or f.stem), iso(ts), stored, h, "", "human"))
    return recs, humans, tools, src
```

- [ ] **Step 4: Run all tests.** Expected: everything passes. Note the OpenCode epoch-millis timestamp `1788252005000` → `2026-09-01T08:40:05Z` (2026-09-01T00:00:00Z is epoch 1788220800).

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "feat(adapters): best-effort pi and opencode adapters with fixtures"
```
