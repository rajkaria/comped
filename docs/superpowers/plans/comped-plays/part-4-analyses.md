# Part 4 — Tasks 8–10: text normalisation, repeat offenders, wrong turns, baseline delta

---

## Task 8: Text normalisation and repeat offenders

**Files:**
- Create: `comped_core/textnorm.py`, `comped_core/repeats.py`
- Test: `tests/test_textnorm.py`, `tests/test_repeats.py`

**Interfaces:**
- Produces: `normalize(text) -> list[str]`, `shingles(tokens, k=2) -> set[tuple]`, `jaccard(a, b) -> float`, `is_excluded(h: HumanMessage) -> str | None` (reason or None), `find_repeats(humans, per_turn_usd, threshold, handle) -> list[RepeatCluster]`.
- Thresholds (SPEC §7.6): Jaccard ≥ 0.5 on 2-shingles; cluster qualifies when size ≥ threshold, ≥ 2 sessions, ≥ 2 days; label = medoid; repeat_usd = total − min turn cost.

- [ ] **Step 1: Write the failing tests.**

`tests/test_textnorm.py`:
```python
import unittest
from comped_core.textnorm import normalize, shingles, jaccard, is_excluded
from comped_core.models import HumanMessage
def H(text, origin="human", project="/home/demo/p"): return HumanMessage("claude-code", "s", "m", "2026-09-01T00:00:00Z", text, "h", project, origin)
class TextNormTests(unittest.TestCase):
    def test_normalize_replaces_paths_urls_numbers(self):
        toks = normalize("Push /Users/x/proj to https://example.com at 10:42, see @file.md and 0xdeadbeef")
        self.assertEqual(toks, ["push", "<path>", "<url>", "<num>", "see", "<ref>", "<hex>"])
    def test_stopwords_and_cap(self):
        self.assertEqual(normalize("the a an and to of push it"), ["push"])
        self.assertEqual(len(normalize(" ".join(["word"] * 100))), 40)
    def test_shingles_jaccard(self):
        a = shingles(["push", "it", "to", "prod"]); b = shingles(["push", "it", "to", "staging"])
        self.assertAlmostEqual(jaccard(a, b), 2 / 4); self.assertEqual(jaccard(set(), set()), 0.0)
    def test_exclusions(self):
        self.assertEqual(is_excluded(H("<system-reminder>x</system-reminder>")), "injected")
        self.assertEqual(is_excluded(H("You are a helpful observer")), "system-prompt")
        self.assertEqual(is_excluded(H("ok", origin="automated")), "automated")
        self.assertEqual(is_excluded(H("hi")), "too-short")
        self.assertEqual(is_excluded(H(" ".join(["w"] * 401))), "too-long")
        self.assertEqual(is_excluded(H("push it to prod", project="/x/claude-mem-observer-sessions")), "observer-project")
        self.assertEqual(is_excluded(H("fix the failing test [Request interrupted by user]")), "interrupted")
        self.assertIsNone(is_excluded(H("push it to prod now")))
```

`tests/test_repeats.py`:
```python
import unittest
from decimal import Decimal
from comped_core.models import HumanMessage
from comped_core.repeats import find_repeats
def H(mid, text, sid, day, origin="human"): return HumanMessage("claude-code", sid, mid, f"2026-09-{day:02d}T10:00:00Z", text, "h", "/home/demo/p", origin)
class RepeatTests(unittest.TestCase):
    def test_cluster_found_and_costed(self):
        hs = [H("a", "push it to prod please", "s1", 1), H("b", "push it to prod", "s2", 2), H("c", "push it to prod now", "s3", 3),
              H("d", "write the changelog for release", "s1", 1), H("e", "explain this stack trace", "s4", 4)]
        cost = {"a": Decimal("10"), "b": Decimal("4"), "c": Decimal("6"), "d": Decimal("1"), "e": Decimal("2")}
        cl = find_repeats(hs, cost, 3, "priya")
        self.assertEqual(len(cl), 1); c = cl[0]
        self.assertEqual(c.count, 3); self.assertEqual(c.sessions, 3); self.assertEqual(c.days, 3)
        self.assertEqual(c.total_usd, Decimal("20")); self.assertEqual(c.repeat_usd, Decimal("16"))
        self.assertEqual(c.dividend_98, Decimal("15.68")); self.assertEqual(c.dividend_80, Decimal("12.80"))
        self.assertEqual(c.label, "push it to prod"); self.assertEqual(sorted(c.members), ["a", "b", "c"])
        self.assertEqual(c.capture_command, '/play settle priya "push it to prod"')
    def test_requires_two_sessions_and_two_days(self):
        hs = [H("a", "push it to prod", "s1", 1), H("b", "push it to prod", "s1", 1), H("c", "push it to prod", "s1", 1)]
        self.assertEqual(find_repeats(hs, {}, 3, ""), [])
    def test_automated_excluded_and_sorted_by_repeat_cost(self):
        hs = [H("a", "hello memory agent", "s1", 1, "automated"), H("b", "hello memory agent", "s2", 2, "automated"), H("c", "hello memory agent", "s3", 3, "automated"),
              H("d", "deploy the site to vercel", "s1", 1), H("e", "deploy the site to vercel", "s2", 2), H("f", "deploy the site to vercel", "s3", 3),
              H("g", "run the test suite", "s1", 1), H("h", "run the test suite", "s2", 2), H("i", "run the test suite", "s3", 3)]
        cost = {k: Decimal(v) for k, v in {"d": 1, "e": 1, "f": 1, "g": 5, "h": 5, "i": 5}.items()}
        cl = find_repeats(hs, cost, 3, "")
        self.assertEqual([c.label for c in cl], ["run the test suite", "deploy the site to vercel"])
        self.assertEqual(cl[0].capture_command, '/play settle <handle> "run the test suite"')
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: comped_core.textnorm`.

- [ ] **Step 3: Implement `comped_core/textnorm.py`.**

```python
import re
from typing import List, Optional, Set, Tuple
from .models import HumanMessage

STOP = set("the a an and or to of in on at for with by from is are be it this that these those please pls can you could would i we my our me just now then".split())
_URL = re.compile(r"https?://\S+|www\.\S+"); _PATH = re.compile(r"(?:~|/)[\w.\-]+(?:/[\w.\-]+)+|[A-Za-z]:\\\S+")
_REF = re.compile(r"@[\w./\-]+"); _HEX = re.compile(r"\b(?:0x)?[0-9a-f]{8,}\b"); _NUM = re.compile(r"\b\d+(?:[.:,]\d+)*\b")
_WORD = re.compile(r"[a-z<>][a-z0-9<>'\-]*")
OBSERVER_DIRS = ("observer", "claude-mem")

def normalize(text: str, cap: int = 40) -> List[str]:
    t = (text or "").lower()
    t = _URL.sub(" <url> ", t); t = _PATH.sub(" <path> ", t); t = _REF.sub(" <ref> ", t); t = _HEX.sub(" <hex> ", t); t = _NUM.sub(" <num> ", t)
    toks = [w for w in _WORD.findall(t) if w not in STOP]
    return toks[:cap]

def shingles(tokens: List[str], k: int = 2) -> Set[Tuple[str, ...]]:
    if len(tokens) < k: return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}

def jaccard(a: set, b: set) -> float:
    if not a and not b: return 0.0
    return len(a & b) / len(a | b)

def is_excluded(h: HumanMessage) -> Optional[str]:
    t = (h.text or "").strip()
    if h.origin == "automated": return "automated"
    if any(d in (h.project or "").lower() for d in OBSERVER_DIRS): return "observer-project"
    if t.startswith("<"): return "injected"
    if t.lower().startswith("you are "): return "system-prompt"
    if "[request interrupted" in t.lower(): return "interrupted"
    n = len(t.split())
    if n < 3: return "too-short"
    if n > 400: return "too-long"
    return None
```

- [ ] **Step 4: Implement `comped_core/repeats.py`.**

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List
from .models import HumanMessage
from .textnorm import normalize, shingles, jaccard, is_excluded

JACCARD_MIN = 0.5
ZERO = Decimal("0"); CENT = Decimal("0.01")

@dataclass
class RepeatCluster:
    label: str; count: int; sessions: int; days: int; total_usd: Decimal; repeat_usd: Decimal
    dividend_98: Decimal; dividend_80: Decimal; capture_command: str; members: List[str]

def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x

def find_repeats(humans: List[HumanMessage], per_turn_usd: Dict[str, Decimal], threshold: int, handle: str) -> List[RepeatCluster]:
    cand = [h for h in humans if is_excluded(h) is None]
    sh = [shingles(normalize(h.text)) for h in cand]
    parent = list(range(len(cand)))
    for i in range(len(cand)):
        if not sh[i]: continue
        for j in range(i + 1, len(cand)):
            if sh[j] and jaccard(sh[i], sh[j]) >= JACCARD_MIN:
                ri, rj = _find(parent, i), _find(parent, j)
                if ri != rj: parent[max(ri, rj)] = min(ri, rj)
    groups: Dict[int, List[int]] = {}
    for i in range(len(cand)): groups.setdefault(_find(parent, i), []).append(i)
    out = []
    for idxs in groups.values():
        if len(idxs) < max(2, int(threshold)): continue
        ms = [cand[i] for i in idxs]
        sessions = {(m.harness, m.session_id) for m in ms}; days = {m.timestamp[:10] for m in ms}
        if len(sessions) < 2 or len(days) < 2: continue
        costs = [per_turn_usd.get(m.message_id, ZERO) for m in ms]
        total = sum(costs, ZERO); repeat = total - min(costs)
        best = max(idxs, key=lambda i: (sum(jaccard(sh[i], sh[j]) for j in idxs if j != i), -len(cand[i].text), cand[i].message_id))
        label = " ".join(cand[best].text.split())[:120].rstrip("…").strip()
        h = handle.strip() or "<handle>"
        out.append(RepeatCluster(label, len(ms), len(sessions), len(days), total, repeat,
                                 (repeat * Decimal("0.98")).quantize(CENT), (repeat * Decimal("0.80")).quantize(CENT),
                                 f'/play settle {h} "{label}"', sorted(m.message_id for m in ms)))
    return sorted(out, key=lambda c: (-c.repeat_usd, -c.count, c.label))
```

- [ ] **Step 5: Run tests.** Expected: pass. In `test_cluster_found_and_costed`, medoid: "push it to prod" (b) has the highest mean Jaccard to a and c; label is b's text.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat(repeats): normalisation, shingle clustering, repeat offenders with capture commands"`

---

## Task 9: Wrong turns and rule drafting

**Files:**
- Create: `comped_core/wrongturns.py`
- Test: `tests/test_wrongturns.py`

**Interfaces:**
- Produces: `classify(ledger, per_turn_usd, min_recurrence, show_snippets) -> list[MistakeClass]`, `draft_rules(classes, target) -> str` (markdown with one fenced block per class for `claude`, `agents`, or `both`), `signature(text) -> str`.
- Recovery cost: usd of the signal's turn plus the next human turn in the same session.

- [ ] **Step 1: Write the failing tests.**

```python
import unittest
from decimal import Decimal
from comped_core.models import HumanMessage, ToolEvent, Ledger
from comped_core.wrongturns import classify, draft_rules, signature
def T(eid, sid, ts, name, summ, err, text, turn): return ToolEvent("claude-code", sid, eid, ts, name, summ, err, text, turn)
def H(mid, sid, ts, text): return HumanMessage("claude-code", sid, mid, ts, text, "h", "/p", "human")
class WrongTurnTests(unittest.TestCase):
    def test_signature_strips_paths_numbers(self):
        self.assertEqual(signature("ENOENT: no such file or directory, open '/Users/x/y.py' line 42"), "enoent: no such file or directory, open '<path>' line <num>")
    def test_tool_error_class_recurs_across_sessions(self):
        tools = [T("e1", "s1", "2026-09-01T10:00:01Z", "Bash", "cat x.py", True, "cat: /a/x.py: No such file or directory", "h1"),
                 T("e2", "s2", "2026-09-02T10:00:01Z", "Bash", "cat y.py", True, "cat: /b/y.py: No such file or directory", "h2"),
                 T("e3", "s3", "2026-09-03T10:00:01Z", "Bash", "cat z.py", True, "cat: /c/z.py: No such file or directory", "h3"),
                 T("e4", "s3", "2026-09-03T10:00:02Z", "Bash", "ls", False, "", "h3")]
        humans = [H("h1", "s1", "2026-09-01T10:00:00Z", "x"), H("h1b", "s1", "2026-09-01T10:01:00Z", "y"), H("h2", "s2", "2026-09-02T10:00:00Z", "x"), H("h3", "s3", "2026-09-03T10:00:00Z", "x")]
        led = Ledger([], humans, tools, [], "x")
        cost = {"h1": Decimal("1"), "h1b": Decimal("2"), "h2": Decimal("3"), "h3": Decimal("4")}
        cl = classify(led, cost, 3, True)
        self.assertEqual(len(cl), 1); c = cl[0]
        self.assertEqual((c.kind, c.confidence, c.tool_name, c.count, c.sessions), ("tool_error", "high", "Bash", 3, 3))
        self.assertEqual(c.recovery_usd, Decimal("10"))   # h1+h1b, h2, h3
        self.assertIn("no such file", c.signature); self.assertIn("cat x.py", c.evidence); self.assertIn("exists", c.rule_draft.lower())
    def test_correction_pairs_with_preceding_tool(self):
        tools = [T(f"e{i}", f"s{i}", f"2026-09-0{i}T10:00:01Z", "Edit", "file.py", False, "", f"h{i}") for i in (1, 2, 3)]
        humans = [H(f"h{i}", f"s{i}", f"2026-09-0{i}T10:00:00Z", "change it") for i in (1, 2, 3)] + \
                 [H(f"c{i}", f"s{i}", f"2026-09-0{i}T10:00:05Z", "no, revert that and do it the other way") for i in (1, 2, 3)]
        cl = classify(Ledger([], humans, tools, [], "x"), {}, 3, True)
        self.assertEqual(len(cl), 1); self.assertEqual((cl[0].kind, cl[0].confidence, cl[0].tool_name, cl[0].count), ("correction", "medium", "Edit", 3))
    def test_revert_detected(self):
        tools = [T(f"e{i}", f"s{i}", f"2026-09-0{i}T10:00:01Z", "Bash", "git reset --hard HEAD~1", False, "", f"h{i}") for i in (1, 2, 3)]
        cl = classify(Ledger([], [], tools, [], "x"), {}, 3, True)
        self.assertEqual(cl[0].kind, "revert"); self.assertEqual(cl[0].confidence, "high")
    def test_snippets_hidden(self):
        tools = [T(f"e{i}", f"s{i}", f"2026-09-0{i}T10:00:01Z", "Bash", "secret cmd", True, "boom", f"h{i}") for i in (1, 2, 3)]
        cl = classify(Ledger([], [], tools, [], "x"), {}, 3, False); self.assertEqual(cl[0].evidence, "(snippets hidden)")
    def test_draft_rules_targets(self):
        tools = [T(f"e{i}", f"s{i}", f"2026-09-0{i}T10:00:01Z", "Bash", "npm test", True, "3 tests failed", f"h{i}") for i in (1, 2, 3)]
        cl = classify(Ledger([], [], tools, [], "x"), {}, 3, True)
        md = draft_rules(cl, "both"); self.assertIn("CLAUDE.md", md); self.assertIn("AGENTS.md", md); self.assertIn("confidence: high", md)
        self.assertNotIn("AGENTS.md", draft_rules(cl, "claude"))
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: comped_core.wrongturns`.

- [ ] **Step 3: Implement `comped_core/wrongturns.py`.**

```python
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List
from .models import Ledger, ToolEvent, HumanMessage
from .textnorm import _PATH, _NUM, _HEX, _URL

ZERO = Decimal("0")
CORRECTION = re.compile(r"\b(no,|don'?t|wrong|revert|undo|instead|not what i|that'?s not|stop|roll ?back|why did you|i said)\b|\[request interrupted", re.I)
REVERT = re.compile(r"git (revert|reset --hard|checkout -- |restore )")
TEMPLATES = [  # (pattern on signature, rule text)
    (r"no such file|enoent|not found: file|cannot find path", "Before reading or editing a path, confirm it exists (`ls` or a glob). If it does not, search for the file by name before assuming a location."),
    (r"permission denied|eacces", "Do not retry a permission-denied command verbatim. Report the path and the permission that is missing, and ask before escalating."),
    (r"command not found|not recognized as an internal", "Check the tool is installed (`which <tool>`) before invoking it; if missing, say so and propose the install command rather than retrying."),
    (r"modulenotfounderror|cannot find module|no module named", "Run the project's dependency install (`npm install`, `pip install -e .`, `uv sync`) once before running code; do not guess module names."),
    (r"tests? failed|failed tests?|assertionerror", "After a change, run the narrowest failing test first and read its assertion before editing further; do not rerun the full suite until it passes."),
    (r"typeerror|type error|is not assignable", "Run the type checker on the touched file before declaring a change done."),
    (r"timed out|timeout", "Set an explicit timeout and a smaller scope on long-running commands; do not rerun the same command unchanged after a timeout."),
    (r"merge conflict|conflict", "Before merging or rebasing, fetch and inspect divergence; resolve conflicts file by file and run tests before continuing."),
    (r"eaddrinuse|address already in use", "Check for a process on the port before starting a server, and reuse the running one if it is the same app."),
]

@dataclass
class MistakeClass:
    kind: str; confidence: str; tool_name: str; signature: str; count: int; sessions: int; recovery_usd: Decimal; evidence: str; rule_draft: str

def signature(text: str) -> str:
    first = next((ln for ln in (text or "").splitlines() if ln.strip()), "").lower()
    first = _URL.sub("<url>", first); first = _PATH.sub("<path>", first); first = _HEX.sub("<hex>", first); first = _NUM.sub("<num>", first)
    return " ".join(first.split())[:80]

def _rule_for(tool: str, sig: str, kind: str, count: int, sessions: int) -> str:
    for pat, text in TEMPLATES:
        if re.search(pat, sig): return text
    if kind == "correction":
        return f"When the user asks for a change via `{tool}`, restate the intended change in one line and wait for confirmation if the request is ambiguous; this was corrected {count} times across {sessions} sessions."
    if kind == "revert":
        return f"Before a destructive git command (`{sig}`), state what will be lost and get explicit confirmation; {count} reverts across {sessions} sessions."
    return f"Before calling `{tool}` for `{sig}`, verify the precondition; this failed {count} times across {sessions} sessions."

def _next_turn_cost(h: HumanMessage, humans_by_session: Dict, per_turn: Dict[str, Decimal]) -> Decimal:
    arr = humans_by_session.get((h.harness, h.session_id), [])
    for i, x in enumerate(arr):
        if x.message_id == h.message_id:
            return per_turn.get(arr[i + 1].message_id, ZERO) if i + 1 < len(arr) else ZERO
    return ZERO

def classify(led: Ledger, per_turn_usd: Dict[str, Decimal], min_recurrence: int, show_snippets: bool) -> List[MistakeClass]:
    hb: Dict = {}
    for h in led.humans:
        if h.origin == "human": hb.setdefault((h.harness, h.session_id), []).append(h)
    for k in hb: hb[k].sort(key=lambda h: (h.timestamp, h.message_id))
    turn_h = {h.message_id: h for arr in hb.values() for h in arr}
    def turn_cost(turn_id: str) -> Decimal:
        c = per_turn_usd.get(turn_id, ZERO); h = turn_h.get(turn_id)
        return c + (_next_turn_cost(h, hb, per_turn_usd) if h else ZERO)
    buckets: Dict[tuple, dict] = {}
    def add(key, kind, conf, tool, sig, sess, turn, ev):
        b = buckets.setdefault(key, {"kind": kind, "conf": conf, "tool": tool, "sig": sig, "n": 0, "sess": set(), "usd": ZERO, "ev": ev})
        b["n"] += 1; b["sess"].add(sess); b["usd"] += turn_cost(turn)
    # A: tool errors, C: reverts
    last_tool_by_session: Dict[tuple, ToolEvent] = {}
    for t in led.tools:
        last_tool_by_session[(t.harness, t.session_id)] = t
        if REVERT.search(t.input_summary or ""):
            add(("revert", t.tool_name, REVERT.search(t.input_summary).group(0).strip()), "revert", "high", t.tool_name, REVERT.search(t.input_summary).group(0).strip(), (t.harness, t.session_id), t.turn_id, t.input_summary)
        if t.is_error:
            sig = signature(t.error_text)
            add(("tool_error", t.tool_name, sig), "tool_error", "high", t.tool_name, sig, (t.harness, t.session_id), t.turn_id, f"{t.tool_name}: {t.input_summary} → {sig}")
    # B: corrections paired with the preceding tool in the same session
    tools_by_session: Dict[tuple, List[ToolEvent]] = {}
    for t in led.tools: tools_by_session.setdefault((t.harness, t.session_id), []).append(t)
    for h in led.humans:
        if h.origin != "human" or not CORRECTION.search(h.text or ""): continue
        prev = [t for t in tools_by_session.get((h.harness, h.session_id), []) if t.timestamp <= h.timestamp]
        tool = prev[-1].tool_name if prev else "text reply"
        stem = CORRECTION.search(h.text).group(0).lower().strip()
        add(("correction", tool, stem), "correction", "medium", tool, stem, (h.harness, h.session_id), h.message_id, f"{tool} → \"{h.text[:80]}\"")
    out = []
    for b in buckets.values():
        if b["n"] < int(min_recurrence) or len(b["sess"]) < 2: continue
        out.append(MistakeClass(b["kind"], b["conf"], b["tool"], b["sig"], b["n"], len(b["sess"]), b["usd"],
                                (" ".join(b["ev"].split())[:160] if show_snippets else "(snippets hidden)"),
                                _rule_for(b["tool"], b["sig"], b["kind"], b["n"], len(b["sess"]))))
    return sorted(out, key=lambda c: (-c.count, -c.recovery_usd, c.tool_name, c.signature))

def draft_rules(classes: List[MistakeClass], target: str) -> str:
    files = {"claude": ["CLAUDE.md"], "agents": ["AGENTS.md"], "both": ["CLAUDE.md", "AGENTS.md"]}.get(target, ["CLAUDE.md", "AGENTS.md"])
    if not classes: return "# Drafted rules\n\nNo recurring mistake class met the threshold. Nothing to draft.\n"
    out = ["# Drafted rules", "", "Paste the block(s) you agree with. Nothing here was applied automatically.", ""]
    for f in files:
        out += [f"## For {f}", ""]
        for c in classes:
            out += [f"<!-- comped wrong-turns · {c.kind} · confidence: {c.confidence} · {c.count}× across {c.sessions} sessions · recovery ≈ ${c.recovery_usd:.2f} -->",
                    f"- {c.rule_draft}", ""]
    return "\n".join(out)
```

- [ ] **Step 4: Run tests.** Expected: pass. In `test_tool_error_class_recurs_across_sessions`, recovery: h1 (1) + next h1b (2) = 3; h2 = 3; h3 = 4 → 10.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(wrongturns): error/correction/revert classes with confidence and drafted rules"`

---

## Task 10: Baseline and delta

**Files:**
- Create: `comped_core/baseline.py`
- Test: `tests/test_baseline.py`

**Interfaces:**
- Produces: `load_baseline(out_dir) -> dict | None`, `save_baseline(out_dir, summary: PricedSummary, clusters, now) -> str`, `delta(prev: dict | None, summary, clusters, now) -> dict` with keys `first_run`, `days_since`, `total_usd_delta`, `multiplier_delta`, `new_repeats`, `resolved_repeats`, `per_model_delta`.

- [ ] **Step 1: Write the failing tests.**

```python
import unittest, tempfile, pathlib
from decimal import Decimal
from datetime import datetime, timezone
from comped_core.baseline import load_baseline, save_baseline, delta
from comped_core.pricing import PricedSummary
from comped_core.repeats import RepeatCluster
def S(total, mult, models): return PricedSummary(Decimal(total), [{"model": m, "usd": Decimal(u)} for m, u in models], [], Decimal("0.5"), 3, 4, {}, Decimal("197"), Decimal(mult) if mult else None, [])
def C(label): return RepeatCluster(label, 3, 3, 3, Decimal("9"), Decimal("6"), Decimal("5.88"), Decimal("4.80"), "cmd", [])
class BaselineTests(unittest.TestCase):
    def test_first_run_then_delta(self):
        d = pathlib.Path(tempfile.mkdtemp()); t1 = datetime(2026, 9, 1, tzinfo=timezone.utc); t2 = datetime(2026, 9, 3, tzinfo=timezone.utc)
        self.assertIsNone(load_baseline(d))
        r0 = delta(None, S("100", "1.5", [("m1", "100")]), [C("a")], t1); self.assertTrue(r0["first_run"])
        save_baseline(d, S("100", "1.5", [("m1", "100")]), [C("a")], t1)
        prev = load_baseline(d); r = delta(prev, S("160", "2.0", [("m1", "150"), ("m2", "10")]), [C("b")], t2)
        self.assertFalse(r["first_run"]); self.assertEqual(r["days_since"], 2)
        self.assertEqual(r["total_usd_delta"], Decimal("60")); self.assertEqual(r["multiplier_delta"], Decimal("0.5"))
        self.assertEqual(r["new_repeats"], ["b"]); self.assertEqual(r["resolved_repeats"], ["a"])
        self.assertEqual(r["per_model_delta"], [{"model": "m1", "delta": Decimal("50")}, {"model": "m2", "delta": Decimal("10")}])
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: comped_core.baseline`.

- [ ] **Step 3: Implement.**

```python
import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from typing import Optional
from .timeutil import iso, parse_ts

NAME = "comped-baseline.json"

def load_baseline(out_dir: Path) -> Optional[dict]:
    p = Path(out_dir).expanduser() / NAME
    if not p.is_file(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except ValueError: return None

def save_baseline(out_dir: Path, s, clusters, now: datetime) -> str:
    p = Path(out_dir).expanduser() / NAME
    doc = {"saved_at": iso(now), "total_usd": str(s.total_usd), "multiplier": (str(s.multiplier) if s.multiplier is not None else None),
           "per_model": {m["model"]: str(m["usd"]) for m in s.per_model}, "repeats": sorted(c.label for c in clusters)}
    p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return str(p)

def delta(prev: Optional[dict], s, clusters, now: datetime) -> dict:
    if not prev: return {"first_run": True, "days_since": 0, "total_usd_delta": Decimal("0"), "multiplier_delta": None, "new_repeats": [], "resolved_repeats": [], "per_model_delta": []}
    then = parse_ts(prev.get("saved_at")); days = (now - then).days if then else 0
    pm = {k: Decimal(v) for k, v in (prev.get("per_model") or {}).items()}
    cur = {m["model"]: m["usd"] for m in s.per_model}
    per_model = [{"model": m, "delta": cur.get(m, Decimal("0")) - pm.get(m, Decimal("0"))} for m in sorted(set(cur) | set(pm))]
    labels = {c.label for c in clusters}; old = set(prev.get("repeats") or [])
    md = None
    if s.multiplier is not None and prev.get("multiplier") is not None: md = s.multiplier - Decimal(prev["multiplier"])
    return {"first_run": False, "days_since": days, "total_usd_delta": s.total_usd - Decimal(prev.get("total_usd", "0")), "multiplier_delta": md,
            "new_repeats": sorted(labels - old), "resolved_repeats": sorted(old - labels), "per_model_delta": per_model}
```

- [ ] **Step 4: Run tests.** Expected: pass.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(baseline): save last run and compute deltas"`
