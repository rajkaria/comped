# Part 1 — Tasks 1–2: scaffold, models, JSONL reader, time utilities, price and plan tables

---

## Task 1: Scaffold, models, JSONL reader, timeutil

**Files:**
- Create: `comped_core/__init__.py`, `comped_core/models.py`, `comped_core/jsonl.py`, `comped_core/timeutil.py`
- Create: `tests/__init__.py`, `tests/test_jsonl.py`, `tests/test_timeutil.py`, `tests/test_models.py`
- Create: `.gitignore`, `LICENSE` (MIT, holder "Raj Karia"), `pyproject.toml` (metadata only, no deps)

**Interfaces:**
- Produces: the dataclasses in the index's "Shared interfaces", `iter_jsonl(path) -> Iterator[tuple[int, dict]]`, `JsonlStats`, `parse_ts(s) -> datetime | None`, `window_start(now, days_back) -> datetime`, `iso(dt) -> str`.

- [ ] **Step 1: Write the failing tests.**

`tests/test_jsonl.py`:
```python
import tempfile, unittest, pathlib
from comped_core.jsonl import iter_jsonl, JsonlStats

class JsonlTests(unittest.TestCase):
    def _write(self, text):
        d = tempfile.mkdtemp(); p = pathlib.Path(d) / "a.jsonl"; p.write_text(text, encoding="utf-8"); return p

    def test_yields_objects_and_skips_bad_lines(self):
        p = self._write('{"a":1}\nnot json\n\n{"b":2}\n{"trunc')
        stats = JsonlStats()
        rows = list(iter_jsonl(p, stats))
        self.assertEqual([r[1] for r in rows], [{"a": 1}, {"b": 2}])
        self.assertEqual([r[0] for r in rows], [1, 4])
        self.assertEqual(stats.lines, 5); self.assertEqual(stats.parsed, 2); self.assertEqual(stats.unparsed, 2)

    def test_missing_file_yields_nothing_and_notes(self):
        stats = JsonlStats()
        self.assertEqual(list(iter_jsonl(pathlib.Path("/nonexistent/x.jsonl"), stats)), [])
        self.assertIn("nonexistent", stats.note)

    def test_non_object_lines_are_unparsed(self):
        p = self._write('[1,2]\n"str"\n{"ok":true}')
        stats = JsonlStats(); rows = list(iter_jsonl(p, stats))
        self.assertEqual(len(rows), 1); self.assertEqual(stats.unparsed, 2)
```

`tests/test_timeutil.py`:
```python
import unittest
from datetime import datetime, timezone, timedelta
from comped_core.timeutil import parse_ts, window_start, iso, day_key

class TimeTests(unittest.TestCase):
    def test_parse_iso_z(self):
        self.assertEqual(parse_ts("2026-09-03T14:01:44.790Z"), datetime(2026, 9, 3, 14, 1, 44, 790000, tzinfo=timezone.utc))
    def test_parse_offset(self):
        self.assertEqual(parse_ts("2026-09-02T14:09:52+05:30").utcoffset(), timedelta(0))
    def test_parse_epoch_seconds_and_millis(self):
        self.assertEqual(parse_ts(1780387497).year, 2026); self.assertEqual(parse_ts(1780387497000).year, 2026)
    def test_bad_returns_none(self):
        self.assertIsNone(parse_ts("yesterday")); self.assertIsNone(parse_ts(None))
    def test_window_and_iso(self):
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)
        self.assertEqual(window_start(now, 30), datetime(2026, 8, 4, tzinfo=timezone.utc))
        self.assertEqual(iso(now), "2026-09-03T00:00:00Z"); self.assertEqual(day_key(now), "2026-09-03")
```

`tests/test_models.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd /Users/rajkaria/Projects/comped && python3 -m unittest discover -s tests -v`
Expected: `ModuleNotFoundError: No module named 'comped_core'`

- [ ] **Step 3: Write the implementation.**

`comped_core/__init__.py`:
```python
"""comped_core: stdlib-only parsing, pricing and analysis of local AI coding agent logs."""
__version__ = "0.1.0"
SCHEMA_VERSION = 1
```

`comped_core/models.py`:
```python
from dataclasses import dataclass, field
from typing import List

@dataclass(frozen=True)
class UsageRecord:
    harness: str
    session_id: str
    record_id: str
    timestamp: str
    model: str
    input_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    output_tokens: int
    reasoning_tokens: int
    project: str
    is_subagent: bool
    turn_id: str

@dataclass(frozen=True)
class HumanMessage:
    harness: str
    session_id: str
    message_id: str
    timestamp: str
    text: str
    text_sha256: str
    project: str
    origin: str  # "human" | "unknown" | "automated"

@dataclass(frozen=True)
class ToolEvent:
    harness: str
    session_id: str
    event_id: str
    timestamp: str
    tool_name: str
    input_summary: str
    is_error: bool
    error_text: str
    turn_id: str

@dataclass
class Source:
    harness: str
    root: str
    found: bool = False
    files: int = 0
    lines: int = 0
    parsed: int = 0
    duplicates: int = 0
    unparsed: int = 0
    note: str = ""

@dataclass
class Ledger:
    records: List[UsageRecord]
    humans: List[HumanMessage]
    tools: List[ToolEvent]
    sources: List[Source]
    generated_at: str
```

`comped_core/jsonl.py`:
```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Tuple

@dataclass
class JsonlStats:
    lines: int = 0
    parsed: int = 0
    unparsed: int = 0
    note: str = ""

def iter_jsonl(path: Path, stats: JsonlStats) -> Iterator[Tuple[int, dict]]:
    """Yield (line_number, object) for every JSON object line. Never raises on bad content."""
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as e:
        stats.note = (stats.note + f"; unreadable {path}: {e.strerror or e}").strip("; ")
        return
    with fh:
        for n, line in enumerate(fh, 1):
            stats.lines += 1
            s = line.strip()
            if not s:
                stats.unparsed += 1
                continue
            try:
                obj = json.loads(s)
            except ValueError:
                stats.unparsed += 1
                continue
            if not isinstance(obj, dict):
                stats.unparsed += 1
                continue
            stats.parsed += 1
            yield n, obj
```

`comped_core/timeutil.py`:
```python
from datetime import datetime, timedelta, timezone
from typing import Optional

def parse_ts(v) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        secs = float(v) / (1000.0 if v > 1e11 else 1.0)
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(v, str):
        return None
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def window_start(now: datetime, days_back: int) -> datetime:
    return now - timedelta(days=int(days_back))

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def day_key(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
```

`.gitignore`:
```
__pycache__/
*.pyc
.DS_Store
out/
/plays/*/resources/comped_core/
/plays/*/resources/prices.json
/plays/*/resources/plans.json
/plays/*/resources/fixtures/
```
(The play resources are generated by `tools/sync_plays.py`; they are regenerated, not committed, until Part 6 decides otherwise.)

`pyproject.toml`:
```toml
[project]
name = "comped-core"
version = "0.1.0"
description = "Stdlib-only parsing, pricing and analysis of local AI coding agent logs"
requires-python = ">=3.9"
license = {text = "MIT"}
dependencies = []
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `python3 -m unittest discover -s tests -v`
Expected: all 10 tests `ok`.

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "feat(core): models, tolerant jsonl reader, time utilities"
```

---

## Task 2: Price table build, `prices.py`, `plans.py`

**Files:**
- Create: `tools/build_prices.py`, `resources/prices.json`, `resources/plans.json`, `comped_core/prices.py`, `comped_core/plans.py`
- Test: `tests/test_prices.py`, `tests/test_plans.py`

**Interfaces:**
- Produces: `load_table(path=None) -> dict` (returns `{"meta": {...}, "models": {key: {in, out, cache_write, cache_read}}}` with Decimal per-token rates), `resolve_model(model: str, table) -> str | None`, `rate_for(model, table) -> dict | None`, `load_plans(path=None) -> dict`, `plan_cost(plan_ids: list[str], days_back: int, plans) -> tuple[Decimal | None, list[str], list[str]]` (cost, resolved ids, notes).

- [ ] **Step 1: Write the failing tests.**

`tests/test_prices.py`:
```python
import unittest, json, tempfile, pathlib
from decimal import Decimal
from comped_core.prices import load_table, resolve_model, rate_for, PREFIXES

class PriceTests(unittest.TestCase):
    def setUp(self):
        self.table = load_table()
    def test_bundled_table_has_header(self):
        m = self.table["meta"]
        for k in ("source_url", "as_of", "upstream_sha", "generated_by"): self.assertIn(k, m)
    def test_known_models_resolve_directly(self):
        for m in ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"):
            self.assertEqual(resolve_model(m, self.table), m)
    def test_prefix_and_date_stripping(self):
        self.assertEqual(resolve_model("us.anthropic.claude-opus-5", self.table), "claude-opus-5")
        self.assertEqual(resolve_model("azure_ai/gpt-5.5-2026-04-23", self.table), "gpt-5.5")
        self.assertEqual(resolve_model("gpt-5.5", self.table), "gpt-5.5")
    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_model("nano_banana", self.table)); self.assertIsNone(resolve_model("<synthetic>", self.table))
    def test_rates_are_decimal_per_token(self):
        r = rate_for("claude-opus-5", self.table)
        self.assertIsInstance(r["in"], Decimal); self.assertEqual(r["in"], Decimal("0.000005"))
        self.assertEqual(r["cache_write"], Decimal("0.00000625")); self.assertEqual(r["cache_read"], Decimal("0.0000005"))
    def test_openai_has_zero_cache_write(self):
        self.assertEqual(rate_for("gpt-5.5", self.table)["cache_write"], Decimal("0"))
    def test_override_path(self):
        d = tempfile.mkdtemp(); p = pathlib.Path(d) / "r.json"
        p.write_text(json.dumps({"meta": {"source_url": "x", "as_of": "2026-01-01", "upstream_sha": "", "generated_by": "test"},
                                 "models": {"my-model": {"in": "0.000001", "out": "0.000002", "cache_write": "0", "cache_read": "0"}}}))
        t = load_table(p); self.assertEqual(rate_for("my-model", t)["out"], Decimal("0.000002"))
    def test_prefix_list_is_ordered_longest_first(self):
        self.assertEqual(PREFIXES, sorted(PREFIXES, key=len, reverse=True))
    def test_play_layout_resolution(self):
        # Simulate plays/<slug>/resources/{comped_core, prices.json}: the table must be found beside the package dir.
        import shutil
        from comped_core import prices as pm
        d = pathlib.Path(tempfile.mkdtemp()); shutil.copytree(pathlib.Path(pm.__file__).parent, d / "comped_core")
        shutil.copy(pathlib.Path("resources/prices.json"), d / "prices.json")
        r = __import__("subprocess").run([__import__("sys").executable, "-c", "from comped_core.prices import BUNDLED; print(BUNDLED)"], cwd=d, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), str(d / "prices.json"))
```

`tests/test_plans.py`:
```python
import unittest
from decimal import Decimal
from comped_core.plans import load_plans, plan_cost

class PlanTests(unittest.TestCase):
    def test_bundled_plans(self):
        p = load_plans()
        for pid in ("claude-pro-20", "claude-max-100", "claude-max-200", "chatgpt-plus-20", "chatgpt-pro-200", "api", "unknown"):
            self.assertIn(pid, p["plans"])
        self.assertIn("as_of", p["meta"])
    def test_cost_prorated_30_days(self):
        cost, ids, notes = plan_cost(["claude-max-200", "chatgpt-plus-20"], 30, load_plans())
        self.assertEqual(ids, ["claude-max-200", "chatgpt-plus-20"])
        self.assertEqual(cost.quantize(Decimal("0.01")), Decimal("216.84"))  # 220 * 30 / 30.4375
    def test_api_or_unknown_gives_none(self):
        self.assertIsNone(plan_cost(["api"], 30, load_plans())[0]); self.assertIsNone(plan_cost([], 30, load_plans())[0])
        self.assertIsNone(plan_cost(["unknown"], 30, load_plans())[0])
    def test_bad_id_is_noted_not_fatal(self):
        cost, ids, notes = plan_cost(["claude-max-200", "bogus"], 30, load_plans())
        self.assertEqual(ids, ["claude-max-200"]); self.assertTrue(any("bogus" in n for n in notes))
```

- [ ] **Step 2: Run tests to verify they fail.** Expected: `ModuleNotFoundError: comped_core.prices`.

- [ ] **Step 3: Write `tools/build_prices.py` and generate `resources/prices.json`.**

```python
#!/usr/bin/env python3
"""Build resources/prices.json from the LiteLLM price table. Run by a human, never by a Play."""
import json, sys, hashlib, datetime, urllib.request, pathlib, re

SRC = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
ALLOW = [  # normalised ids we always keep, even if unseen in fixtures
    "claude-fable-5-1", "claude-fable-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5",
    "claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-1", "claude-sonnet-4-5",
    "gpt-5.5", "gpt-5.4", "gpt-5.4-pro", "gpt-5.5-codex", "gpt-5-codex", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "o4-mini",
    "gemini-3-pro", "gemini-3-flash", "gemini-2.5-pro", "gemini-2.5-flash",
    "deepseek-chat", "deepseek-reasoner", "kimi-k2", "grok-4", "mistral-large-latest", "qwen3-coder",
]
PREFIXES = ["global.anthropic.", "us.anthropic.", "eu.anthropic.", "au.anthropic.", "jp.anthropic.", "apac.anthropic.",
            "anthropic.", "openrouter/openai/", "openrouter/anthropic/", "azure_ai/", "azure/us/", "azure/eu/", "azure/",
            "openai/", "anthropic/", "bedrock/", "vertex_ai/", "gemini/", "deepseek/", "moonshot/", "xai/", "mistral/"]
DATE = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")

def normalise(k):
    for p in sorted(PREFIXES, key=len, reverse=True):
        if k.startswith(p): k = k[len(p):]; break
    k = re.sub(r"-v\d+:\d+$", "", k)
    return DATE.sub("", k)

def main(out="resources/prices.json"):
    raw = urllib.request.urlopen(SRC, timeout=60).read()
    sha = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    models = {}
    for key, e in data.items():
        if not isinstance(e, dict) or "input_cost_per_token" not in e: continue
        n = normalise(key)
        if n not in ALLOW: continue
        rec = {"in": repr(e.get("input_cost_per_token") or 0), "out": repr(e.get("output_cost_per_token") or 0),
               "cache_write": repr(e.get("cache_creation_input_token_cost") or 0),
               "cache_read": repr(e.get("cache_read_input_token_cost") or 0), "from_key": key}
        # prefer the unprefixed key when several map to the same normalised id
        if n not in models or key == n or ("/" not in key and "." not in key.split("-")[0]):
            models[n] = rec
    doc = {"meta": {"source_url": SRC, "upstream_sha": sha, "as_of": datetime.date.today().isoformat(),
                    "generated_by": "tools/build_prices.py", "unit": "USD per token",
                    "note": "List prices. Not a bill. Unknown models are never estimated."},
           "models": dict(sorted(models.items()))}
    pathlib.Path(out).write_text(json.dumps(doc, indent=1) + "\n")
    print(f"wrote {out}: {len(models)} models, sha {sha[:12]}")

if __name__ == "__main__":
    main(*sys.argv[1:])
```

Run: `python3 tools/build_prices.py` → Expected: `wrote resources/prices.json: N models` with N ≥ 20 and the file under 60 KB (`wc -c resources/prices.json`). Confirm `gpt-5.5` and `claude-fable-5-1` present with `jq '.models["gpt-5.5"], .models["claude-fable-5-1"]' resources/prices.json`. If `gpt-5.5-codex` is absent upstream, leave it absent; unknown models are reported, never guessed.

- [ ] **Step 4: Write `resources/plans.json`.**

```json
{
  "meta": {"as_of": "2026-09-03", "currency": "USD", "unit": "per month",
           "note": "Public list prices on the as_of date. Verify against anthropic.com/pricing and openai.com/chatgpt/pricing before each release.",
           "mean_month_days": "30.4375"},
  "plans": {
    "claude-pro-20":   {"label": "Claude Pro",       "monthly_usd": "20",  "vendor": "anthropic", "source_url": "https://www.anthropic.com/pricing"},
    "claude-max-100":  {"label": "Claude Max 5x",    "monthly_usd": "100", "vendor": "anthropic", "source_url": "https://www.anthropic.com/pricing"},
    "claude-max-200":  {"label": "Claude Max 20x",   "monthly_usd": "200", "vendor": "anthropic", "source_url": "https://www.anthropic.com/pricing"},
    "chatgpt-plus-20": {"label": "ChatGPT Plus",     "monthly_usd": "20",  "vendor": "openai",    "source_url": "https://openai.com/chatgpt/pricing"},
    "chatgpt-pro-200": {"label": "ChatGPT Pro",      "monthly_usd": "200", "vendor": "openai",    "source_url": "https://openai.com/chatgpt/pricing"},
    "api":             {"label": "API pay-as-you-go", "monthly_usd": null, "vendor": "any", "source_url": ""},
    "unknown":         {"label": "Unknown plan",     "monthly_usd": null, "vendor": "any", "source_url": ""}
  }
}
```

- [ ] **Step 5: Write `comped_core/prices.py` and `comped_core/plans.py`.**

`comped_core/prices.py`:
```python
import json, re
from decimal import Decimal
from pathlib import Path
from typing import Optional

def _bundled(name: str) -> Path:
    """Repo layout: comped_core/../resources/<name>. Play layout: resources/comped_core/../<name>. First existing wins."""
    here = Path(__file__).resolve().parent.parent
    for cand in (here / "resources" / name, here / name):
        if cand.exists(): return cand
    return here / "resources" / name

BUNDLED = _bundled("prices.json")
PREFIXES = sorted(["global.anthropic.", "us.anthropic.", "eu.anthropic.", "au.anthropic.", "jp.anthropic.", "apac.anthropic.",
                   "anthropic.", "openrouter/openai/", "openrouter/anthropic/", "azure_ai/", "azure/us/", "azure/eu/", "azure/",
                   "openai/", "anthropic/", "bedrock/", "vertex_ai/", "gemini/", "deepseek/", "moonshot/", "xai/", "mistral/"],
                  key=len, reverse=True)
_DATE = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")
_VER = re.compile(r"-v\d+:\d+$")

def load_table(path: Optional[Path] = None) -> dict:
    p = Path(path) if path else BUNDLED
    doc = json.loads(p.read_text(encoding="utf-8"))
    models = {}
    for k, v in doc.get("models", {}).items():
        models[k] = {f: Decimal(str(v.get(f, "0") or "0")) for f in ("in", "out", "cache_write", "cache_read")}
    return {"meta": doc.get("meta", {}), "models": models, "path": str(p)}

def _candidates(model: str):
    yield model
    m = model
    for p in PREFIXES:
        if m.startswith(p):
            m = m[len(p):]
            yield m
            break
    m2 = _VER.sub("", m)
    if m2 != m: yield m2
    m3 = _DATE.sub("", m2)
    if m3 != m2: yield m3

def resolve_model(model: str, table: dict) -> Optional[str]:
    if not model or not isinstance(model, str): return None
    for c in _candidates(model.strip()):
        if c in table["models"]: return c
    return None

def rate_for(model: str, table: dict) -> Optional[dict]:
    k = resolve_model(model, table)
    return table["models"][k] if k else None
```

`comped_core/plans.py`:
```python
import json
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from .prices import _bundled
BUNDLED = _bundled("plans.json")

def load_plans(path: Optional[Path] = None) -> dict:
    return json.loads(Path(path or BUNDLED).read_text(encoding="utf-8"))

def parse_plan_ids(raw: str) -> List[str]:
    return [p.strip().lower() for p in (raw or "").split(",") if p.strip()]

def plan_cost(plan_ids: List[str], days_back: int, plans: dict) -> Tuple[Optional[Decimal], List[str], List[str]]:
    notes, resolved, total = [], [], Decimal("0")
    mean_days = Decimal(str(plans["meta"].get("mean_month_days", "30.4375")))
    for pid in plan_ids:
        entry = plans["plans"].get(pid)
        if entry is None:
            notes.append(f"unknown plan id '{pid}' ignored; valid: {', '.join(sorted(plans['plans']))}")
            continue
        if entry.get("monthly_usd") is None:
            notes.append(f"plan '{pid}' has no monthly price; multiplier not computed")
            continue
        resolved.append(pid)
        total += Decimal(str(entry["monthly_usd"])) * Decimal(int(days_back)) / mean_days
    if not resolved:
        return None, resolved, notes
    return total, resolved, notes
```

- [ ] **Step 6: Run the tests.** Expected: all pass, including `test_cost_prorated_30_days` = 216.84.

- [ ] **Step 7: Commit.**

```bash
git add -A && git commit -m "feat(prices): bundled LiteLLM snapshot with provenance, alias resolution, plan proration"
```
