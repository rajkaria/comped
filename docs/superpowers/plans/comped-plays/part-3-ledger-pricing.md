# Part 3 — Tasks 6–7: ledger assembly and pricing

---

## Task 6: Ledger assembly, turn attribution, summary, JSONL I/O

**Files:**
- Modify: `comped_core/adapters/__init__.py` (add `parse_all`)
- Create: `comped_core/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces: `parse_all(config) -> Ledger`; `attribute_turns(ledger) -> None` (fills `turn_id` on records and tools in place by rebuilding lists); `write_ledger(ledger, out_dir) -> list[str]` (paths written); `read_ledger(out_dir) -> Ledger`; `summary(ledger) -> dict`.
- Turn rule: within one `(harness, session_id)`, every record or tool event gets the `message_id` of the latest human message with `origin == "human"` whose timestamp ≤ the event's timestamp. Subagent records use the parent session's human messages (same `session_id`). Events before any human message get `turn_id = "<session>:pre"`.

- [ ] **Step 1: Write the failing tests.**

`tests/test_ledger.py`:
```python
import unittest, tempfile, pathlib, json
from datetime import datetime, timezone
from comped_core.models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger
from comped_core.ledger import attribute_turns, write_ledger, read_ledger, summary
from comped_core.adapters import parse_all

def R(ts, sid="s", sub=False): return UsageRecord("claude-code", sid, f"r{ts}", ts, "claude-opus-5", 1, 0, 0, 1, 0, "/p", sub, "")
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
```

- [ ] **Step 2: Run to verify failure.** Expected: `ImportError: cannot import name 'attribute_turns'`.

- [ ] **Step 3: Implement.**

Add to `comped_core/adapters/__init__.py`:
```python
from ..models import Ledger
from ..timeutil import iso
from ..ledger import attribute_turns

def parse_all(config: dict) -> Ledger:
    records, humans, tools, sources = [], [], [], []
    for harness in sorted(ADAPTERS):
        mod, key = ADAPTERS[harness]
        r, h, t, s = mod.parse(Path(str(config.get(key) or "")), config["since"], bool(config.get("include_subagents", True)), bool(config.get("redact", True)))
        records += r; humans += h; tools += t; sources.append(s)
    led = Ledger(sorted(records, key=lambda r: (r.harness, r.session_id, r.timestamp, r.record_id)),
                 sorted(humans, key=lambda h: (h.harness, h.session_id, h.timestamp, h.message_id)),
                 sorted(tools, key=lambda t: (t.harness, t.session_id, t.timestamp, t.event_id)),
                 sources, iso(config["now"]))
    attribute_turns(led)
    return led
```
(Import order: `ledger.py` must not import `adapters`, to avoid a cycle.)

`comped_core/ledger.py`:
```python
import json, bisect, dataclasses
from pathlib import Path
from typing import List
from .models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger
from . import SCHEMA_VERSION

def attribute_turns(led: Ledger) -> None:
    idx = {}
    for h in led.humans:
        if h.origin == "human":
            idx.setdefault((h.harness, h.session_id), []).append((h.timestamp, h.message_id))
    for k in idx: idx[k].sort()
    def turn_for(harness, sid, ts):
        arr = idx.get((harness, sid))
        if not arr: return f"{sid}:pre"
        i = bisect.bisect_right([a[0] for a in arr], ts)
        return arr[i - 1][1] if i else f"{sid}:pre"
    led.records = [dataclasses.replace(r, turn_id=turn_for(r.harness, r.session_id, r.timestamp)) for r in led.records]
    led.tools = [dataclasses.replace(t, turn_id=turn_for(t.harness, t.session_id, t.timestamp)) for t in led.tools]

def summary(led: Ledger) -> dict:
    return {"schema_version": SCHEMA_VERSION, "generated_at": led.generated_at, "records": len(led.records), "humans": len(led.humans),
            "human_typed": sum(1 for h in led.humans if h.origin == "human"), "tools": len(led.tools),
            "tool_errors": sum(1 for t in led.tools if t.is_error), "sessions": len({(r.harness, r.session_id) for r in led.records}),
            "subagent_records": sum(1 for r in led.records if r.is_subagent),
            "sources": [dataclasses.asdict(s) for s in led.sources]}

def write_ledger(led: Ledger, out_dir: Path) -> List[str]:
    out_dir = Path(out_dir).expanduser(); out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "ledger.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for kind, items in (("record", led.records), ("human", led.humans), ("tool", led.tools)):
            for it in items:
                fh.write(json.dumps({"kind": kind, **dataclasses.asdict(it)}, sort_keys=True) + "\n")
    s = out_dir / "ledger-summary.json"
    s.write_text(json.dumps(summary(led), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return [str(p), str(s)]

def read_ledger(out_dir: Path) -> Ledger:
    out_dir = Path(out_dir).expanduser()
    recs, hums, tools = [], [], []
    for line in open(out_dir / "ledger.jsonl", encoding="utf-8"):
        o = json.loads(line); kind = o.pop("kind")
        {"record": (recs, UsageRecord), "human": (hums, HumanMessage), "tool": (tools, ToolEvent)}[kind][0].append(
            {"record": UsageRecord, "human": HumanMessage, "tool": ToolEvent}[kind](**o))
    s = json.loads((out_dir / "ledger-summary.json").read_text(encoding="utf-8"))
    return Ledger(recs, hums, tools, [Source(**x) for x in s.get("sources", [])], s.get("generated_at", ""))
```

- [ ] **Step 4: Run all tests.** Expected: pass. `test_parse_all_on_fixtures` depends on fixtures from Tasks 3–5 existing.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(ledger): assembly, turn attribution, jsonl round-trip, summary"`

---

## Task 7: Pricing engine, windows, explain

**Files:**
- Create: `comped_core/pricing.py`
- Test: `tests/test_pricing.py`

**Interfaces:**
- Produces: `price_ledger(ledger, table, plans, plan_ids, days_back, now) -> PricedSummary` (fields in the index) and `usd_for(record, table) -> tuple[Decimal, str | None]`.
- `explain` lines are strings, one per (harness, model) group, then plan arithmetic, then source notes.

- [ ] **Step 1: Write the failing tests.**

```python
import unittest
from decimal import Decimal
from datetime import datetime, timezone
from comped_core.models import UsageRecord, Ledger, Source
from comped_core.pricing import price_ledger, usd_for
from comped_core.prices import load_table
from comped_core.plans import load_plans

def R(model, inp, cw, cr, out, ts="2026-09-01T10:00:00Z", turn="t1", harness="claude-code", sid="s"):
    return UsageRecord(harness, sid, f"{model}{ts}{turn}", ts, model, inp, cw, cr, out, 0, "/p", False, turn)

class PricingTests(unittest.TestCase):
    def setUp(self): self.table = load_table(); self.plans = load_plans(); self.now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    def test_usd_for_opus5(self):
        usd, key = usd_for(R("claude-opus-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000), self.table)
        self.assertEqual(key, "claude-opus-5"); self.assertEqual(usd, Decimal("5") + Decimal("6.25") + Decimal("0.5") + Decimal("25"))
    def test_unknown_is_zero_and_flagged(self):
        usd, key = usd_for(R("nano_banana", 10, 0, 0, 10), self.table); self.assertEqual(usd, Decimal("0")); self.assertIsNone(key)
    def test_summary_totals_multiplier_cache_share(self):
        led = Ledger([R("claude-opus-5", 1_000_000, 0, 3_000_000, 0), R("claude-opus-5", 0, 0, 0, 100_000, turn="t2"),
                      R("nano_banana", 5, 0, 0, 5, turn="t3"), R("claude-opus-5", 1, 0, 0, 1, ts="2026-07-01T00:00:00Z", turn="old")],
                     [], [], [Source("claude-code", "/x", True)], "2026-09-03T00:00:00Z")
        s = price_ledger(led, self.table, self.plans, ["claude-max-200"], 30, self.now)
        self.assertEqual(s.total_usd, Decimal("5") + Decimal("1.5") + Decimal("2.5"))
        self.assertEqual(s.per_model[0]["model"], "claude-opus-5"); self.assertEqual(s.per_model[0]["records"], 2)
        self.assertEqual(s.unpriced, [{"model": "nano_banana", "records": 1, "tokens": 10}])
        self.assertEqual(s.cache_share, Decimal("0.75")); self.assertEqual(s.active_days, 1); self.assertEqual(s.sessions, 1)
        self.assertEqual(s.plan_cost.quantize(Decimal("0.01")), Decimal("197.13"))
        self.assertEqual(s.multiplier.quantize(Decimal("0.1")), Decimal("0.0"))
        self.assertEqual(s.per_turn_usd["t1"], Decimal("6.5")); self.assertEqual(s.per_turn_usd["t2"], Decimal("2.5"))
        self.assertTrue(any("claude-opus-5" in e and "0.000005" in e for e in s.explain))
        self.assertTrue(any("plan" in e.lower() for e in s.explain))
    def test_no_plan(self):
        led = Ledger([R("claude-opus-5", 10, 0, 0, 10)], [], [], [], "x")
        s = price_ledger(led, self.table, self.plans, [], 30, self.now)
        self.assertIsNone(s.plan_cost); self.assertIsNone(s.multiplier)
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: comped_core.pricing`.

- [ ] **Step 3: Implement `comped_core/pricing.py`.**

```python
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from .models import UsageRecord, Ledger
from .prices import resolve_model
from .plans import plan_cost
from .timeutil import window_start, parse_ts, day_key, iso

ZERO = Decimal("0")

@dataclass
class PricedSummary:
    total_usd: Decimal
    per_model: list
    unpriced: list
    cache_share: Decimal
    active_days: int
    sessions: int
    per_turn_usd: Dict[str, Decimal]
    plan_cost: Optional[Decimal]
    multiplier: Optional[Decimal]
    plan_ids: list
    explain: List[str] = field(default_factory=list)
    window_start: str = ""
    window_end: str = ""
    price_meta: dict = field(default_factory=dict)
    records_in_window: int = 0

def usd_for(r: UsageRecord, table: dict) -> Tuple[Decimal, Optional[str]]:
    key = resolve_model(r.model, table)
    if key is None: return ZERO, None
    p = table["models"][key]
    return (Decimal(r.input_tokens) * p["in"] + Decimal(r.cache_write_tokens) * p["cache_write"]
            + Decimal(r.cache_read_tokens) * p["cache_read"] + Decimal(r.output_tokens) * p["out"]), key

def price_ledger(led: Ledger, table: dict, plans: dict, plan_ids: list, days_back: int, now: datetime) -> PricedSummary:
    start = window_start(now, days_back)
    groups: Dict[str, dict] = {}; unpriced: Dict[str, dict] = {}; per_turn: Dict[str, Decimal] = {}
    total = ZERO; cache_read = 0; inp_all = 0; days = set(); sessions = set(); n = 0
    for r in led.records:
        ts = parse_ts(r.timestamp)
        if ts is None or ts < start or ts > now: continue
        n += 1; sessions.add((r.harness, r.session_id)); days.add(day_key(ts))
        usd, key = usd_for(r, table)
        toks = r.input_tokens + r.cache_write_tokens + r.cache_read_tokens + r.output_tokens
        cache_read += r.cache_read_tokens; inp_all += r.input_tokens + r.cache_write_tokens + r.cache_read_tokens
        if key is None:
            u = unpriced.setdefault(r.model or "(blank)", {"model": r.model or "(blank)", "records": 0, "tokens": 0})
            u["records"] += 1; u["tokens"] += toks
            continue
        g = groups.setdefault(r.model, {"model": r.model, "key": key, "usd": ZERO, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "records": 0, "priced": True})
        g["usd"] += usd; g["input"] += r.input_tokens; g["cache_write"] += r.cache_write_tokens; g["cache_read"] += r.cache_read_tokens
        g["output"] += r.output_tokens; g["records"] += 1
        total += usd; per_turn[r.turn_id] = per_turn.get(r.turn_id, ZERO) + usd
    per_model = sorted(groups.values(), key=lambda g: (-g["usd"], g["model"]))
    cost, resolved, notes = plan_cost(plan_ids, days_back, plans)
    mult = (total / cost) if cost and cost > 0 else None
    explain = [f"window {iso(start)} .. {iso(now)} ({days_back} days), {n} priced+unpriced records, price table {table['meta'].get('as_of')} from {table['meta'].get('source_url')}"]
    for g in per_model:
        p = table["models"][g["key"]]
        explain.append(f"{g['model']} -> {g['key']}: input {g['input']}×{p['in']} + cache_write {g['cache_write']}×{p['cache_write']} + cache_read {g['cache_read']}×{p['cache_read']} + output {g['output']}×{p['out']} = ${g['usd']:.4f} over {g['records']} records")
    for u in sorted(unpriced.values(), key=lambda u: u["model"]):
        explain.append(f"UNPRICED {u['model']}: {u['records']} records, {u['tokens']} tokens (no rate in table; never estimated)")
    if cost is not None:
        explain.append(f"plan cost: {' + '.join(resolved)} prorated {days_back}/{plans['meta'].get('mean_month_days')} days = ${cost:.4f}; multiplier = {total:.4f}/{cost:.4f} = {mult:.4f}")
    else:
        explain.append("plan cost: not computed (no priced plan given); card shows list-price total only")
    explain += [f"note: {x}" for x in notes]
    for s in led.sources:
        explain.append(f"source {s.harness} at {s.root}: found={s.found} files={s.files} lines={s.lines} parsed={s.parsed} duplicates_removed={s.duplicates} unparsed={s.unparsed} {s.note}".rstrip())
    return PricedSummary(total, per_model, sorted(unpriced.values(), key=lambda u: u["model"]),
                         (Decimal(cache_read) / Decimal(inp_all)) if inp_all else ZERO, len(days), len(sessions), per_turn,
                         cost, mult, resolved, explain, iso(start), iso(now), dict(table["meta"]), n)
```

- [ ] **Step 4: Run tests.** Expected: pass. Check the arithmetic in `test_summary_totals_multiplier_cache_share`: 1M input × $5/M = $5; 3M cache read × $0.5/M = $1.5; 100k output × $25/M = $2.5; cache share = 3M / (1M + 3M) = 0.75; plan 200 × 30 / 30.4375 = 197.13.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(pricing): decimal pricing, windows, plan multiplier, explain lines"`
