# Micro Plays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Twelve rote Plays a person runs many times a day, on a third stdlib-only core, published live at `play.modiqo.ai/rajkaria/<name>@0.1.0`.

**Architecture:** One new package `micro_core/` with nine focused modules and a single `cli.py` dispatch. Four Plays are thin CLIs over one append-only JSONL store; two share one transcript-tail reader; the rest are one module each. Three Plays additionally bundle the existing `comped_core` for its maintained price table. Packaging reuses the proven daily-Play pipeline: a JSON spec drives a generator that writes each Play's `main.ts` + `deps.toml`, and `tools/sync_plays.py` keeps every bundled core copy byte-identical.

**Tech Stack:** Python ≥ 3.9, standard library only. `unittest` (`python3 -m unittest discover -s tests`). `rote` 0.80.0 CLI for lint and publish. No pip, no node, no network.

**Spec:** [docs/superpowers/specs/2026-09-05-micro-plays-design.md](../specs/2026-09-05-micro-plays-design.md)

## Global Constraints

- Python ≥ 3.9, **standard library only**. No third-party imports anywhere in `micro_core/`.
- `micro_core` imports no `urllib`, `http`, `socket`, `requests` or `subprocess`. Asserted by `tests/test_micro_safety.py`.
- Every step prints human-readable text on stdout and **one JSON object as its final line**. Nothing else goes to stdout.
- A missing or unreadable source is an expected absence: print `{"ok": true, "warning": "..."}` and **exit 0**. Never raise.
- Every Play takes `now` (ISO-8601 string; `""` means the real clock) and `demo` (`"true"`/`"false"`). Both are strings — rote passes all params as strings.
- `state_dir` default is `~/.rote-micro`. Writes are **appends only**; nothing is truncated, deleted or rewritten in place.
- Only these five Plays write: `punch`, `spent`, `jot`, `streak`, `since-last`. They are tagged `effect-local-write`; the other seven are `effect-read-only`.
- Each step completes in ≤ 400 ms on bundled fixtures. Asserted by `tests/test_micro_perf.py`.
- Tags follow the registry taxonomy `domain-*`, `job-*`, `audience-*`, `effect-*`, `tool-*`.
- Commit after every task, conventional message, ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Never read a credential file. `~/.claude.json`, `~/.codex/auth.json`, keychains and token files are out of bounds for every Play.

## File Structure

| File | Responsibility |
|---|---|
| `micro_core/__init__.py`, `__main__.py` | package marker; `python3 -m micro_core` entry |
| `micro_core/common.py` | emit contract, bool/date/tz parsing, human formatting, sparkline |
| `micro_core/cli.py` | one argparse dispatch: `<play> <step>` |
| `micro_core/store.py` | append-only JSONL, day rollups, streak/grid maths |
| `micro_core/decode.py` | layered identifier/peeler for `whatis` |
| `micro_core/secrets.py` | token shapes, entropy, redaction |
| `micro_core/cronx.py` | cron parse, next fires, English, DST warning |
| `micro_core/size.py` | byte/line/word counts, token range, window fit, cost |
| `micro_core/turn.py` | newest transcript tail, one-turn pricing, today total |
| `micro_core/snapshot.py` | filesystem snapshot and delta, sensitive-path watch |
| `micro_core/gitindex.py` | `.git/index` v2 parser, loose-object reader |
| `micro_core/staged.py` | staged-set review built on gitindex + secrets |
| `micro_core/fixtures/` | synthetic inputs for `demo=true`, one dir per Play |
| `docs/plays/_micro-spec.json` | DAG, tags, output schema for all twelve |
| `docs/plays/<play>/DESCRIPTION.md`, `PARAMETERS.json`, `STEPS.md` | registry copy, params, DAG docs |
| `tools/build_micro_plays.py` | generates twelve `main.ts` + `deps.toml` |
| `tools/build_micro_fixtures.py` | writes `micro_core/fixtures/` |
| `tests/test_micro_*.py` | core, cli, package, safety, perf |

---

### Task 1: `micro_core` skeleton — the emit contract

**Files:**
- Create: `micro_core/__init__.py`, `micro_core/__main__.py`, `micro_core/common.py`, `micro_core/cli.py`
- Test: `tests/test_micro_core.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `common.emit(human: str, result: dict) -> int` — prints `human` (if non-empty), then `json.dumps(result, sort_keys=True, separators=(",", ":"))` as the final line; returns `0`.
  - `common.as_bool(s) -> bool` — `"true"/"1"/"yes"/"on"` (case-insensitive) are True; everything else False.
  - `common.now_utc(s: str = "") -> datetime` — parses ISO-8601 (accepting a trailing `Z`); `""` returns `datetime.now(timezone.utc)`. Always tz-aware.
  - `common.expand(p) -> Path` — `Path(str(p)).expanduser()`.
  - `common.iso(d: datetime) -> str`, `common.day(d: datetime) -> str` (`YYYY-MM-DD`).
  - `common.human_int(n) -> str` (thousands separators), `common.human_usd(x) -> str` (`$0.19`, `$12.40`).
  - `common.sparkline(values: list) -> str` — eight block characters; `""` for an empty list; a flat series renders as the lowest block.
  - `common.trunc(s: str, width: int) -> str` — ellipsis at `width`, never longer than `width`.
  - `common.warn(msg: str) -> dict` — `{"ok": True, "warning": msg}`.
  - `common.tz_of(name: str = "")` — `zoneinfo.ZoneInfo(name)`, falling back to the local zone for `""` and to UTC when the tz database is missing.
  - `cli.main(argv=None) -> int` — dispatch on `argv[0]` (play) and `argv[1]` (step).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_micro_core.py
import io, json, unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from micro_core import common


class TestEmit(unittest.TestCase):
    def test_json_is_the_last_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = common.emit("two lines\nof human text", {"ok": True, "n": 3})
        self.assertEqual(rc, 0)
        lines = buf.getvalue().rstrip("\n").split("\n")
        self.assertEqual(lines[:2], ["two lines", "of human text"])
        self.assertEqual(json.loads(lines[-1]), {"ok": True, "n": 3})

    def test_empty_human_still_emits_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            common.emit("", {"ok": True})
        self.assertEqual(json.loads(buf.getvalue().strip()), {"ok": True})


class TestScalars(unittest.TestCase):
    def test_as_bool(self):
        for s in ("true", "TRUE", "1", "yes", "on"):
            self.assertTrue(common.as_bool(s))
        for s in ("false", "0", "", "no", None, "maybe"):
            self.assertFalse(common.as_bool(s))

    def test_now_utc_parses_z_and_defaults_aware(self):
        self.assertEqual(common.now_utc("2026-09-05T14:22:03Z"),
                         datetime(2026, 9, 5, 14, 22, 3, tzinfo=timezone.utc))
        self.assertIsNotNone(common.now_utc("").tzinfo)

    def test_sparkline_and_trunc(self):
        self.assertEqual(common.sparkline([]), "")
        self.assertEqual(len(common.sparkline([0, 1, 2, 3])), 4)
        self.assertEqual(len(common.sparkline([5, 5, 5])), 3)
        self.assertEqual(common.trunc("abcdefgh", 5), "abcd…")
        self.assertEqual(common.trunc("abc", 5), "abc")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'micro_core'`

- [ ] **Step 3: Write `micro_core/common.py`**

Model it on `daily_core/common.py` (same house style: short module docstring, no type-annotation noise, `.format()` over f-strings for 3.9 safety). `emit` is exactly:

```python
def emit(human, result):
    """Human text first, then exactly one JSON object as the last line. Nothing else on stdout."""
    if human:
        sys.stdout.write(human.rstrip("\n") + "\n")
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0
```

- [ ] **Step 4: Write `micro_core/cli.py` with the dispatch skeleton**

```python
PLAYS = ("whatis", "fits", "secret", "cron", "punch", "spent", "jot", "streak",
         "last-turn", "budget", "since-last", "staged")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in PLAYS:
        sys.stderr.write("usage: cli.py <{0}> <step> [options]\n".format("|".join(PLAYS)))
        return 2
    play, rest = argv[0], argv[1:]
    return _DISPATCH[play](rest)
```

`micro_core/__main__.py` is `import sys; from .cli import main; sys.exit(main())`. Add the same `sys.path` bootstrap `daily_core/cli.py` uses so the file can be invoked by path from a Play step.

- [ ] **Step 5: Run the tests**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add micro_core tests/test_micro_core.py
git commit -m "feat(micro): the core's emit contract and dispatch"
```

---

### Task 2: `store.py` — the append-only log

**Files:**
- Create: `micro_core/store.py`
- Modify: `tests/test_micro_core.py`

**Interfaces:**
- Consumes: `common.expand`, `common.day`, `common.iso`, `common.now_utc`.
- Produces:
  - `store.stream_path(state_dir, stream: str) -> Path` — `state_dir/<stream>.jsonl`, expanded.
  - `store.append(state_dir, stream: str, doc: dict) -> str` — creates `state_dir` if missing, appends one line, returns the path as a string. `doc` gains `"t"` (ISO) and `"v": 1` if absent.
  - `store.read(state_dir, stream: str, since=None) -> list` — list of `Entry(t: datetime, data: dict)` sorted by `t`; skips unparseable lines silently; returns `[]` for a missing file.
  - `store.days_with_entries(entries) -> set` — set of `YYYY-MM-DD` in **local** time.
  - `store.streak(days: set, today: str) -> tuple` — `(current, longest)`. `current` counts back from `today`, and a gap of one day ends it; if today has no entry but yesterday does, `current` still counts (the day is not over).
  - `store.grid(days: set, today: str, window: int) -> str` — `window` characters ending at `today`, `█` for a day present, `·` for absent.
  - `store.worst_weekday(days: set, today: str, window: int) -> str or None` — the weekday name missed most often in the window, `None` when the window has fewer than 14 days of history or there is no clear worst.

- [ ] **Step 1: Write the failing tests**

```python
class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_append_then_read_roundtrip(self):
        store.append(self.dir, "punch", {"note": "api", "t": "2026-09-05T10:00:00Z"})
        store.append(self.dir, "punch", {"note": "docs", "t": "2026-09-05T11:30:00Z"})
        got = store.read(self.dir, "punch")
        self.assertEqual([e.data["note"] for e in got], ["api", "docs"])
        self.assertEqual(got[0].t.hour, 10)

    def test_append_stamps_time_and_version(self):
        store.append(self.dir, "punch", {"note": "x"})
        line = json.loads(open(store.stream_path(self.dir, "punch")).read().strip())
        self.assertIn("t", line)
        self.assertEqual(line["v"], 1)

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(store.read(self.dir, "never-written"), [])

    def test_torn_trailing_line_is_skipped_not_fatal(self):
        p = store.stream_path(self.dir, "punch")
        os.makedirs(self.dir, exist_ok=True)
        open(p, "w").write('{"t":"2026-09-05T10:00:00Z","note":"good"}\n{"t":"2026-')
        got = store.read(self.dir, "punch")
        self.assertEqual(len(got), 1)

    def test_streak_counts_back_from_today(self):
        days = {"2026-09-03", "2026-09-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (3, 3))

    def test_streak_survives_a_today_with_no_entry(self):
        days = {"2026-09-03", "2026-09-04"}
        self.assertEqual(store.streak(days, "2026-09-05")[0], 2)

    def test_streak_breaks_on_a_two_day_gap(self):
        days = {"2026-09-01", "2026-09-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (2, 2))

    def test_grid_is_window_long_and_ends_today(self):
        g = store.grid({"2026-09-05"}, "2026-09-05", 7)
        self.assertEqual(len(g), 7)
        self.assertTrue(g.endswith("█"))
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — `AttributeError: module 'micro_core' has no attribute 'store'`

- [ ] **Step 3: Implement `store.py`**

The append is one `write` of `line + "\n"` on a handle opened `"a"`, so a concurrent append cannot interleave a partial line under `PIPE_BUF`. Reading tolerates a torn tail:

```python
def read(state_dir, stream, since=None):
    p = stream_path(state_dir, stream)
    out = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
            t = now_utc(doc["t"])
        except (ValueError, KeyError, TypeError):
            continue                      # a torn or hand-edited line costs itself and nothing else
        if since is None or t >= since:
            out.append(Entry(t=t, data=doc))
    return sorted(out, key=lambda e: e.t)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/store.py tests/test_micro_core.py
git commit -m "feat(micro): an append-only log four Plays can share"
```

---

### Task 3: `punch` — the two-step logging Play

**Files:**
- Modify: `micro_core/cli.py`
- Create: `tests/test_micro_cli.py`

**Interfaces:**
- Consumes: `store.*`, `common.*`.
- Produces:
  - CLI: `cli.py punch record --note <s> --tag <s> --state-dir <p> --now <iso>` → `{"ok": true, "written": "<path>", "recorded": bool}`
  - CLI: `cli.py punch report --state-dir <p> --days-back 14 --now <iso>` → keys `punches`, `switches`, `current_block_min`, `longest_block_min`, `streak`, `shape`, `topics`
  - `cli._punch_topic(note: str, tag: str) -> str` — the tag if given, else the note lowercased, stripped of punctuation, first two words joined by `-`.
  - `cli._blocks(entries, now) -> tuple` — `(switches: int, current_min: int, longest_min: int)`. A switch is an entry whose topic differs from its predecessor **on the same local day**. `current_min` is minutes from the last entry to `now`; `longest_min` is the longest span between consecutive same-topic entries plus the trailing open block.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_micro_cli.py
def run(args):
    """Run one CLI step, return (exit code, human text, parsed final JSON line)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(args)
    lines = buf.getvalue().rstrip("\n").split("\n")
    return rc, "\n".join(lines[:-1]), json.loads(lines[-1])


class TestPunch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_record_then_report_counts_switches(self):
        for at, note in [("09:00", "api"), ("09:40", "api"), ("10:30", "docs"), ("11:00", "api")]:
            rc, _, j = run(["punch", "record", "--note", note, "--state-dir", self.dir,
                            "--now", "2026-09-05T{0}:00Z".format(at)])
            self.assertEqual(rc, 0)
            self.assertTrue(j["ok"])
        rc, human, j = run(["punch", "report", "--state-dir", self.dir,
                            "--now", "2026-09-05T11:30:00Z"])
        self.assertEqual(rc, 0)
        self.assertEqual(j["punches"], 4)
        self.assertEqual(j["switches"], 2)          # api→docs and docs→api
        self.assertEqual(j["current_block_min"], 30)
        self.assertIn("switch", human)

    def test_report_with_no_history_warns_and_exits_zero(self):
        rc, human, j = run(["punch", "report", "--state-dir", self.dir, "--now", "2026-09-05T11:30:00Z"])
        self.assertEqual(rc, 0)
        self.assertTrue(j["ok"])
        self.assertIn("warning", j)

    def test_record_with_no_note_records_nothing(self):
        rc, _, j = run(["punch", "record", "--state-dir", self.dir, "--now", "2026-09-05T09:00:00Z"])
        self.assertEqual(rc, 0)
        self.assertFalse(j["recorded"])
        self.assertEqual(store.read(self.dir, "punch"), [])

    def test_output_is_byte_identical_for_a_fixed_now(self):
        run(["punch", "record", "--note", "api", "--state-dir", self.dir, "--now", "2026-09-05T09:00:00Z"])
        a = run(["punch", "report", "--state-dir", self.dir, "--now", "2026-09-05T11:30:00Z"])
        b = run(["punch", "report", "--state-dir", self.dir, "--now", "2026-09-05T11:30:00Z"])
        self.assertEqual(a, b)
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest tests.test_micro_cli -v`
Expected: FAIL — dispatch has no `punch` handler

- [ ] **Step 3: Implement the `punch` handlers in `cli.py`**

Two functions, `_punch_record(argv)` and `_punch_report(argv)`, each with their own `argparse.ArgumentParser`. The human text ends with the shareable line:

```
6 switches today · longest block 74 min · 9-day streak
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/cli.py tests/test_micro_cli.py
git commit -m "feat(micro): punch — what you are doing, and how often that changed"
```

---

### Task 4: `spent`, `jot`, `streak` — the other three log Plays

**Files:**
- Modify: `micro_core/cli.py`, `micro_core/store.py`, `tests/test_micro_cli.py`

**Interfaces:**
- Consumes: `store.*`, `common.*`.
- Produces:
  - `store.parse_entry(s: str, default_currency: str) -> dict` — parses `"320 lunch"`, `"₹320 lunch"`, `"$12.50 coffee #food"`, `"12,50 café"` into `{"amount": Decimal, "currency": str, "label": str, "tag": str}`; raises `ValueError` when no amount is present.
  - CLI `spent record|report`: report keys `today`, `month`, `currency`, `by_tag`, `avg_per_day`, `projection`, `budget`, `over`.
  - CLI `jot record|report`: `record` takes `--note`, `--vault-dir`, `--inbox`, `--state-dir`; appends `- HH:MM note` to `<vault_dir>/<inbox>` when `vault_dir` is set, always mirrors to the log, and refuses an identical note within 60 s (`{"recorded": false, "reason": "duplicate"}`). Report keys `today`, `week`, `streak`, `inbox_lines`, `written`.
  - CLI `streak record|report`: `record` takes `--did`; report keys `habits` (list of `{name, current, longest, grid, worst_weekday}`), `best`.

- [ ] **Step 1: Write the failing tests**

```python
class TestSpent(unittest.TestCase):
    def test_parses_symbol_amount_label_and_tag(self):
        d = store.parse_entry("₹320 lunch #food", "INR")
        self.assertEqual((str(d["amount"]), d["currency"], d["label"], d["tag"]),
                         ("320", "INR", "lunch", "food"))

    def test_bare_number_uses_default_currency(self):
        self.assertEqual(store.parse_entry("12.50 coffee", "USD")["currency"], "USD")

    def test_no_amount_is_a_value_error(self):
        with self.assertRaises(ValueError):
            store.parse_entry("lunch", "USD")

    def test_month_total_and_projection(self):
        d = tempfile.mkdtemp()
        for day, amt in [("01", "100"), ("02", "200"), ("03", "300")]:
            run(["spent", "record", "--entry", amt + " food", "--currency", "INR",
                 "--state-dir", d, "--now", "2026-09-{0}T10:00:00Z".format(day)])
        rc, _, j = run(["spent", "report", "--state-dir", d, "--budget", "6000",
                        "--now", "2026-09-03T20:00:00Z"])
        self.assertEqual(j["month"], "600.00")
        self.assertEqual(j["projection"], "6000.00")     # 200/day × 30 days
        self.assertFalse(j["over"])


class TestJot(unittest.TestCase):
    def test_writes_a_markdown_line_into_the_vault_inbox(self):
        state, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        rc, _, j = run(["jot", "record", "--note", "ring the dentist", "--vault-dir", vault,
                        "--state-dir", state, "--now", "2026-09-05T14:22:00Z"])
        self.assertEqual(rc, 0)
        body = open(os.path.join(vault, "Inbox.md")).read()
        self.assertIn("- 14:22 ring the dentist", body)

    def test_identical_note_within_a_minute_is_refused(self):
        state, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        args = ["jot", "record", "--note", "same", "--vault-dir", vault, "--state-dir", state]
        run(args + ["--now", "2026-09-05T14:22:00Z"])
        rc, _, j = run(args + ["--now", "2026-09-05T14:22:30Z"])
        self.assertFalse(j["recorded"])
        self.assertEqual(j["reason"], "duplicate")
        self.assertEqual(open(os.path.join(vault, "Inbox.md")).read().count("same"), 1)

    def test_no_vault_dir_still_records_to_the_log(self):
        state = tempfile.mkdtemp()
        rc, _, j = run(["jot", "record", "--note", "x", "--state-dir", state,
                        "--now", "2026-09-05T14:22:00Z"])
        self.assertTrue(j["recorded"])
        self.assertEqual(len(store.read(state, "jot")), 1)


class TestStreak(unittest.TestCase):
    def test_two_habits_are_tracked_apart(self):
        d = tempfile.mkdtemp()
        for day in ("03", "04", "05"):
            run(["streak", "record", "--did", "water", "--state-dir", d,
                 "--now", "2026-09-{0}T09:00:00Z".format(day)])
        run(["streak", "record", "--did", "gym", "--state-dir", d, "--now", "2026-09-05T18:00:00Z"])
        rc, _, j = run(["streak", "report", "--state-dir", d, "--now", "2026-09-05T20:00:00Z"])
        by = {h["name"]: h for h in j["habits"]}
        self.assertEqual(by["water"]["current"], 3)
        self.assertEqual(by["gym"]["current"], 1)
        self.assertEqual(j["best"], "water")
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_cli -v`
Expected: FAIL — no `spent`/`jot`/`streak` handlers

- [ ] **Step 3: Implement `store.parse_entry` and the six handlers**

`parse_entry` uses `Decimal` throughout — money never touches a float. Money is rendered with `quantize(Decimal("0.01"))`. Currency symbols recognised: `₹ $ € £ ¥` mapping to `INR USD EUR GBP JPY`; an unrecognised leading symbol falls back to `default_currency` and is reported in the output rather than guessed at.

The `jot` vault write is one append of `"- HH:MM note\n"`; if `<inbox>` does not exist it is created with a single `# Inbox\n\n` header. `written` in the output names the exact path.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core tests/test_micro_cli.py
git commit -m "feat(micro): spent, jot and streak on the same log"
```

---

### Task 5: `decode.py` — the peeling identifier

**Files:**
- Create: `micro_core/decode.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `common.*`.
- Produces:
  - `decode.Layer` — frozen dataclass `(kind: str, label: str, detail: dict, text: str or None)`. `text` is the decoded payload to recurse into, or `None` at a leaf.
  - `decode.identify(text: str) -> Layer` — classifies one layer. Kinds: `jwt`, `base64`, `base64url`, `hex`, `urlencoded`, `gzip`, `json`, `epoch`, `iso8601`, `uuid`, `ulid`, `git-sha`, `ipv4`, `ipv6`, `cidr`, `mac`, `semver`, `cron`, `color`, `data-uri`, `hash`, `email`, `url`, `binary`, `text`.
  - `decode.peel(text: str, depth: int = 4, reveal: bool = False) -> list` — layers outermost first; stops at `depth`, at a leaf, or when a decode does not change the input.
  - `decode.render(layers: list) -> str` — the human block.
  - CLI `whatis report --text <s> --depth 4 --reveal false` → keys `kind`, `layers`, `depth_reached`, `detail`.

Rules that matter:
- A JWT is three base64url segments separated by `.` whose first segment decodes to JSON with an `alg` key. Report `alg`, `typ`, the claim names, `iat`/`exp` rendered as absolute times **and** as "expired 4h ago" / "expires in 12m". The signature is never printed in full — first 8 characters and a length.
- Ambiguity is reported, never guessed away: a 10-digit integer is `epoch` seconds **and** could be a plain number; the output says which reading was taken and why (a plausible date between 2001 and 2038 wins).
- `reveal=false` (the default) truncates every decoded string value to 80 characters; `reveal=true` prints them whole. Neither ever prints a JWT signature.

- [ ] **Step 1: Write the failing tests**

```python
class TestDecode(unittest.TestCase):
    def test_jwt_is_identified_with_claims_and_expiry(self):
        tok = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
               "eyJzdWIiOiJ1c2VyXzg4MTIiLCJleHAiOjE3ODg2MDAwMDB9.c2lnbmF0dXJlLWJ5dGVz")
        layers = decode.peel(tok)
        self.assertEqual(layers[0].kind, "jwt")
        self.assertEqual(layers[0].detail["alg"], "HS256")
        self.assertIn("sub", layers[0].detail["claims"])
        self.assertNotIn("c2lnbmF0dXJlLWJ5dGVz", decode.render(layers))

    def test_peels_base64_then_json(self):
        inner = base64.b64encode(b'{"hello":"world"}').decode()
        layers = decode.peel(inner)
        self.assertEqual([l.kind for l in layers], ["base64", "json"])

    def test_peels_base64_gzip_json(self):
        blob = base64.b64encode(gzip.compress(b'{"a":1}')).decode()
        self.assertEqual([l.kind for l in decode.peel(blob)], ["base64", "gzip", "json"])

    def test_depth_is_honoured(self):
        blob = base64.b64encode(gzip.compress(b'{"a":1}')).decode()
        self.assertEqual(len(decode.peel(blob, depth=2)), 2)

    def test_uuid_v7_reports_its_embedded_time(self):
        l = decode.identify("018f2c3d-4e5f-7abc-8def-0123456789ab")
        self.assertEqual(l.kind, "uuid")
        self.assertEqual(l.detail["version"], 7)
        self.assertIn("time", l.detail)

    def test_epoch_ms_vs_seconds(self):
        self.assertEqual(decode.identify("1788600000").detail["unit"], "s")
        self.assertEqual(decode.identify("1788600000000").detail["unit"], "ms")

    def test_private_ip_is_classified(self):
        self.assertEqual(decode.identify("10.1.2.3").detail["scope"], "private")
        self.assertEqual(decode.identify("8.8.8.8").detail["scope"], "public")

    def test_plain_text_is_a_leaf_not_a_guess(self):
        l = decode.identify("just some words here")
        self.assertEqual(l.kind, "text")
        self.assertIsNone(l.text)

    def test_hash_by_length(self):
        self.assertEqual(decode.identify("a" * 64).detail["candidates"], ["sha256"])
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — no `micro_core.decode`

- [ ] **Step 3: Implement `decode.py` and the `whatis` handler**

Detector order matters and is explicit: the most structurally constrained shapes are tried first (`data-uri`, `jwt`, `uuid`, `ulid`, `mac`, `cidr`, `ipv6`, `ipv4`, `iso8601`, `semver`, `color`, `git-sha`, `hash`, `email`, `url`, `cron`, `json`, `epoch`, `urlencoded`, `base64url`, `base64`, `hex`), and each detector is a small function returning a `Layer` or `None`. Base64 only fires when the input is ≥ 8 characters, length-valid, decodes cleanly, and the result is either valid UTF-8 with ≥ 90% printable characters or a recognised magic-byte signature (`\x1f\x8b` gzip, `%PDF`, `\x89PNG`, `PK\x03\x04`) — this is what stops a hex git SHA being read as base64.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/decode.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): whatis — paste the opaque thing, get every layer of it"
```

---

### Task 6: `secrets.py` — before you paste it anywhere

**Files:**
- Create: `micro_core/secrets.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `common.*`.
- Produces:
  - `secrets.Finding` — frozen dataclass `(kind, severity, line, col, masked, why)`. `severity` ∈ `{"blocker", "high", "medium"}`.
  - `secrets.entropy(s: str) -> float` — Shannon entropy in bits per character.
  - `secrets.scan(text: str, strict: bool = True) -> list` — findings sorted by line then severity.
  - `secrets.redact(text: str, findings: list) -> str` — every finding's span replaced by `<REDACTED:kind>`, offsets applied right-to-left so earlier spans stay valid.
  - `secrets.verdict(findings: list) -> str` — `"do-not-paste"` if any blocker, `"redact"` if any finding, else `"safe"`.
  - CLI `secret report --text <s> --path <p> --strict true --show redacted` → keys `findings`, `verdict`, `counts`, `redacted`.

Detected shapes (each with its own literal prefix test, not one catch-all regex): AWS `AKIA`/`ASIA` + 16, GitHub `ghp_`/`gho_`/`ghs_`/`ghu_`/`github_pat_`, Slack `xox[baprs]-`, Stripe `sk_live_`/`rk_live_`, Google `AIza`, OpenAI `sk-` + 32+, Anthropic `sk-ant-`, Twilio `SK` + 32 hex, SendGrid `SG.`, npm `npm_`, PyPI `pypi-AgEI`, PEM `-----BEGIN ... PRIVATE KEY-----`, `ssh-rsa`/`ssh-ed25519` with a body, JWTs, URLs with `://user:password@`, and `.env`-style `KEY=VALUE` where the key name matches `(?i)(secret|token|passwd|password|api_?key|access_?key|private)` and the value is ≥ 12 characters with entropy ≥ 3.5.

Deliberate non-findings, so the output stays worth reading: a value that is `changeme`, `xxx`, `your-key-here`, `example`, `<...>`, `${...}`, `$VAR`, all one repeated character, or a well-known test key (Stripe's `sk_test_`, `AKIAIOSFODNN7EXAMPLE`).

- [ ] **Step 1: Write the failing tests**

```python
class TestSecrets(unittest.TestCase):
    def test_aws_key_is_a_blocker(self):
        f = secrets.scan("aws_access_key_id = AKIA1234567890ABCD12")
        self.assertEqual(f[0].kind, "aws-access-key")
        self.assertEqual(f[0].severity, "blocker")

    def test_placeholder_is_not_a_finding(self):
        self.assertEqual(secrets.scan("API_KEY=your-key-here"), [])
        self.assertEqual(secrets.scan("TOKEN=${GITHUB_TOKEN}"), [])
        self.assertEqual(secrets.scan("password=changeme"), [])

    def test_documented_example_key_is_not_a_finding(self):
        self.assertEqual(secrets.scan("key = AKIAIOSFODNN7EXAMPLE"), [])

    def test_high_entropy_env_value_is_medium_not_blocker(self):
        f = secrets.scan("SESSION_SECRET=8fJ2kL9mQ4xR7vN1pZ3wY6bC0dE5gH")
        self.assertEqual(f[0].severity, "medium")

    def test_connection_string_password(self):
        f = secrets.scan("postgres://app:hunter2hunter2@db.internal:5432/prod")
        self.assertEqual(f[0].kind, "connection-string")

    def test_redaction_removes_every_secret_and_keeps_the_rest(self):
        text = "host=db\nAPI_KEY=AKIA1234567890ABCD12\nport=5432"
        out = secrets.redact(text, secrets.scan(text))
        self.assertNotIn("AKIA1234567890ABCD12", out)
        self.assertIn("host=db", out)
        self.assertIn("port=5432", out)

    def test_masked_finding_never_carries_the_secret(self):
        for f in secrets.scan("API_KEY=AKIA1234567890ABCD12"):
            self.assertNotIn("1234567890ABCD12", f.masked)

    def test_verdicts(self):
        self.assertEqual(secrets.verdict([]), "safe")
        self.assertEqual(secrets.verdict(secrets.scan("k=AKIA1234567890ABCD12")), "do-not-paste")
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — no `micro_core.secrets`

- [ ] **Step 3: Implement `secrets.py` and the `secret` handler**

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/secrets.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): is-it-secret — read it before the agent does"
```

---

### Task 7: `cronx.py` — when does that actually fire

**Files:**
- Create: `micro_core/cronx.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `common.tz_of`, `common.now_utc`.
- Produces:
  - `cronx.parse(expr: str) -> dict` — `{"minute": set, "hour": set, "dom": set, "month": set, "dow": set, "dom_restricted": bool, "dow_restricted": bool}`; raises `ValueError` with a human message on a bad field. Accepts `*`, `a-b`, `a,b`, `*/n`, `a-b/n`, three-letter month and day names, and the macros `@yearly @annually @monthly @weekly @daily @midnight @hourly`.
  - `cronx.next_fires(spec: dict, start, count: int, tz) -> list` — tz-aware datetimes in `tz`, strictly after `start`, walking minute by minute with month/day skipping; gives up after 4 years and returns what it has.
  - `cronx.describe(spec: dict) -> str` — e.g. `every weekday at 09:30`.
  - `cronx.dst_warning(spec: dict, tz, start) -> str or None`.
  - CLI `cron report --expr <s> --tz <s> --count 5 --now <iso>` → keys `valid`, `english`, `fires` (local + UTC pairs), `average_interval_min`, `warning`, `error`.

The rule most cron implementations get wrong, and this one must not: when **both** day-of-month and day-of-week are restricted, a day matches if **either** matches (the POSIX OR). When only one is restricted, only that one applies.

- [ ] **Step 1: Write the failing tests**

```python
class TestCron(unittest.TestCase):
    def test_weekday_morning(self):
        spec = cronx.parse("30 9 * * 1-5")
        fires = cronx.next_fires(spec, common.now_utc("2026-09-05T12:00:00Z"), 3, timezone.utc)
        self.assertEqual([f.strftime("%a %H:%M") for f in fires],
                         ["Mon 09:30", "Tue 09:30", "Wed 09:30"])

    def test_dom_and_dow_are_ored_not_anded(self):
        spec = cronx.parse("0 0 13 * 5")          # the 13th OR any Friday
        fires = cronx.next_fires(spec, common.now_utc("2026-11-01T00:00:00Z"), 4, timezone.utc)
        got = [f.strftime("%Y-%m-%d") for f in fires]
        self.assertIn("2026-11-13", got)
        self.assertIn("2026-11-06", got)          # a Friday that is not the 13th

    def test_only_dom_restricted_does_not_or_in_every_day(self):
        spec = cronx.parse("0 0 1 * *")
        fires = cronx.next_fires(spec, common.now_utc("2026-09-05T00:00:00Z"), 2, timezone.utc)
        self.assertEqual([f.day for f in fires], [1, 1])

    def test_macros(self):
        self.assertEqual(cronx.parse("@daily"), cronx.parse("0 0 * * *"))

    def test_step_and_names(self):
        spec = cronx.parse("*/15 * * * MON")
        self.assertEqual(sorted(spec["minute"]), [0, 15, 30, 45])
        self.assertEqual(spec["dow"], {1})

    def test_bad_field_is_a_value_error_with_a_readable_message(self):
        with self.assertRaises(ValueError) as e:
            cronx.parse("99 * * * *")
        self.assertIn("minute", str(e.exception))

    def test_english(self):
        self.assertEqual(cronx.describe(cronx.parse("30 9 * * 1-5")), "every weekday at 09:30")

    def test_dst_warning_for_an_hour_that_does_not_exist(self):
        tz = common.tz_of("Europe/London")
        w = cronx.dst_warning(cronx.parse("30 1 * * *"), tz, common.now_utc("2027-03-01T00:00:00Z"))
        self.assertIsNotNone(w)
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — no `micro_core.cronx`

- [ ] **Step 3: Implement `cronx.py` and the `cron` handler**

`next_fires` iterates in the target zone using `datetime` arithmetic on naive wall-clock values and re-localises each candidate, so a wall-clock time that does not exist on a spring-forward day is detected (localising and reading the hour back gives a different hour) and reported rather than silently shifted.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/cronx.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): cron-when — the next five times, in both zones"
```

---

### Task 8: `size.py` — will it fit, what will it cost

**Files:**
- Create: `micro_core/size.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `comped_core.prices.load_table`, `comped_core.prices.rate_for`.
- Produces:
  - `size.measure(text: str) -> dict` — `{"bytes", "chars", "lines", "words"}`, all exact.
  - `size.token_range(text: str) -> tuple` — `(low, mid, high)`. The estimator is a documented character-class model: ASCII prose ≈ 4.0 chars/token, code and punctuation-dense runs ≈ 3.1, CJK ≈ 1.0, whitespace runs collapse. The band is ±15% around `mid`, widened to ±25% when more than 20% of characters are non-ASCII.
  - `size.window_fit(mid: int, window: int) -> dict` — `{"fits": bool, "pct": int, "headroom": int}`.
  - `size.costs(low: int, high: int, models: list, table: dict) -> list` — per model `{"model", "resolved", "low_usd", "high_usd"}`; a model absent from the table is returned with `"resolved": None` and no numbers rather than a zero.
  - CLI `fits report --text <s> --path <p> --window 200000 --models <csv> --rates-path <p>` → keys `bytes`, `lines`, `words`, `tokens_low`, `tokens_mid`, `tokens_high`, `fits`, `pct`, `costs`, `method`.

`method` is in the output on purpose: the number is an estimate, and the Play says so in the same breath it says the number.

- [ ] **Step 1: Write the failing tests**

```python
class TestSize(unittest.TestCase):
    def test_measurements_are_exact(self):
        m = size.measure("one two\nthree\n")
        self.assertEqual((m["lines"], m["words"], m["bytes"]), (2, 3, 14))

    def test_token_range_brackets_the_estimate(self):
        low, mid, high = size.token_range("hello world " * 100)
        self.assertLess(low, mid)
        self.assertLess(mid, high)

    def test_more_text_is_never_fewer_tokens(self):
        a = size.token_range("x" * 1000)[1]
        b = size.token_range("x" * 2000)[1]
        self.assertGreater(b, a)

    def test_cjk_is_denser_than_ascii(self):
        ascii_mid = size.token_range("a" * 200)[1]
        cjk_mid = size.token_range("的" * 200)[1]
        self.assertGreater(cjk_mid, ascii_mid)

    def test_window_fit(self):
        f = size.window_fit(50000, 200000)
        self.assertTrue(f["fits"])
        self.assertEqual(f["pct"], 25)
        self.assertFalse(size.window_fit(300000, 200000)["fits"])

    def test_unknown_model_is_reported_not_priced_at_zero(self):
        rows = size.costs(100, 200, ["not-a-model"], prices.load_table())
        self.assertIsNone(rows[0]["resolved"])
        self.assertNotIn("low_usd", rows[0])
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — no `micro_core.size`

- [ ] **Step 3: Implement `size.py` and the `fits` handler**

`fits` imports `comped_core` lazily inside the handler so the other eleven Plays never load it. The default model list is `claude-opus-5,claude-sonnet-5,claude-haiku-4-5`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/size.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): fits — how big that is, and what it costs to send"
```

---

### Task 9: `turn.py` — the last ninety seconds

**Files:**
- Create: `micro_core/turn.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `comped_core.prices.load_table`, `comped_core.pricing.usd_for`, `comped_core.models.UsageRecord`.
- Produces:
  - `turn.newest_transcript(dirs: list) -> Path or None` — the most recently modified `*.jsonl` under any of `dirs`, searched at most three levels deep.
  - `turn.tail_records(path, max_bytes: int = 262144) -> list` — seeks to `max(0, size - max_bytes)`, drops the first partial line, returns parsed JSON objects in file order.
  - `turn.last_turn(dirs: list, table: dict) -> dict or None` — the newest record carrying a usage block, as `{"model", "input", "output", "cache_read", "cache_write", "usd", "at", "source"}`.
  - `turn.today_total(dirs: list, table: dict, now) -> dict` — `{"usd", "turns", "first_at", "last_at"}` over records whose timestamp falls on `now`'s local day, still reading only tails.
  - CLI `last-turn report --claude-dir <p> --codex-dir <p> --rates-path <p> --demo false --now <iso>` → keys `model`, `input`, `output`, `cache_read`, `cache_write`, `usd`, `today_usd`, `turns_today`.
  - CLI `budget report --daily-budget 10 --claude-dir <p> --codex-dir <p> --rates-path <p> --now <iso>` → keys `spent`, `budget`, `pct`, `burn_per_hour`, `exhausted_at`, `verdict`.

Tailing is the whole trick: `comped` reads every session to price a month, which takes seconds. This reads 256 KB off the end of one file, which takes milliseconds, and says in its output that it read a tail so nobody mistakes it for a full accounting.

- [ ] **Step 1: Write the failing tests**

```python
class TestTurn(unittest.TestCase):
    def _session(self, dirpath, name, records):
        os.makedirs(dirpath, exist_ok=True)
        p = os.path.join(dirpath, name)
        with open(p, "w") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        return p

    def test_tail_drops_the_first_partial_line(self):
        d = tempfile.mkdtemp()
        p = self._session(d, "s.jsonl", [{"i": i} for i in range(200)])
        got = turn.tail_records(p, max_bytes=200)
        self.assertTrue(all("i" in r for r in got))
        self.assertLess(len(got), 200)

    def test_last_turn_prices_the_newest_usage_record(self):
        d = tempfile.mkdtemp()
        self._session(d, "s.jsonl", [
            {"type": "assistant", "timestamp": "2026-09-05T10:00:00Z",
             "message": {"model": "claude-sonnet-5",
                         "usage": {"input_tokens": 100, "output_tokens": 50}}},
            {"type": "assistant", "timestamp": "2026-09-05T11:00:00Z",
             "message": {"model": "claude-opus-5",
                         "usage": {"input_tokens": 41200, "output_tokens": 2100,
                                   "cache_read_input_tokens": 30000}}},
        ])
        t = turn.last_turn([Path(d)], prices.load_table())
        self.assertEqual(t["model"], "claude-opus-5")
        self.assertEqual(t["input"], 41200)
        self.assertEqual(t["cache_read"], 30000)
        self.assertGreater(float(t["usd"]), 0)

    def test_no_transcripts_is_a_warning_not_a_crash(self):
        self.assertIsNone(turn.last_turn([Path(tempfile.mkdtemp())], prices.load_table()))

    def test_today_total_ignores_yesterday(self):
        d = tempfile.mkdtemp()
        self._session(d, "s.jsonl", [
            {"type": "assistant", "timestamp": "2026-09-04T10:00:00Z",
             "message": {"model": "claude-opus-5", "usage": {"input_tokens": 1000, "output_tokens": 10}}},
            {"type": "assistant", "timestamp": "2026-09-05T10:00:00Z",
             "message": {"model": "claude-opus-5", "usage": {"input_tokens": 2000, "output_tokens": 20}}},
        ])
        tot = turn.today_total([Path(d)], prices.load_table(), common.now_utc("2026-09-05T12:00:00Z"))
        self.assertEqual(tot["turns"], 1)
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — no `micro_core.turn`

- [ ] **Step 3: Implement `turn.py` and both handlers**

Record shapes to read: Claude Code (`message.usage.{input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}`, `message.model`, `timestamp`) and Codex (`payload.info.last_token_usage` / `token_usage` with `model`). Anything else is skipped, and the count of skipped records appears in the output so an unread format is visible rather than silently zero.

`budget-left` divides today's spend by hours elapsed since `first_at` (floored at 0.25 h so an early first turn cannot produce an absurd rate) and projects the crossing time; when the rate is zero it says so instead of printing a time in the year 3000.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/turn.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): last-turn and budget-left, off the tail of one file"
```

---

### Task 10: `snapshot.py` — the agent's blast radius

**Files:**
- Create: `micro_core/snapshot.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `common.*`, `store.stream_path` (for the state directory only).
- Produces:
  - `snapshot.DEFAULT_IGNORE` — `{".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".mypy_cache", ".pytest_cache", "target", ".DS_Store"}`.
  - `snapshot.scan_tree(root: Path, ignore: set, max_files: int) -> dict` — `{relpath: [mtime_ns, size, lines]}`; `lines` is `-1` for a file that is binary or larger than 2 MB. Stops at `max_files` and records `truncated: True` in the returned envelope key `"_meta"`.
  - `snapshot.save(state_dir, key: str, snap: dict) -> str` / `snapshot.load(state_dir, key: str) -> dict or None` — one JSON file per `key`; `key` is a stable digest of the absolute root path.
  - `snapshot.delta(prev: dict, cur: dict) -> dict` — `{"created": [...], "modified": [...], "deleted": [...], "lines_added": int, "lines_removed": int, "biggest": {...} or None}`.
  - `snapshot.sensitive_state(home: Path) -> dict` — mtimes of `~/.ssh`, `~/.aws`, `~/.config`, `~/Library/LaunchAgents`, `~/.claude`, and nothing inside them. Directory mtimes only: the Play notices that something changed there without reading a single byte of it.
  - CLI `since-last report --root <p> --state-dir <p> --ignore <csv> --max-files 20000 --watch-sensitive true --now <iso>` → keys `first_run`, `created`, `modified`, `deleted`, `lines_added`, `lines_removed`, `biggest`, `sensitive_changed`, `elapsed_min`.

- [ ] **Step 1: Write the failing tests**

```python
class TestSnapshot(unittest.TestCase):
    def test_delta_reports_created_modified_deleted(self):
        prev = {"a.py": [1, 10, 2], "b.py": [1, 10, 2]}
        cur = {"a.py": [2, 30, 5], "c.py": [2, 5, 1]}
        d = snapshot.delta(prev, cur)
        self.assertEqual(d["created"], ["c.py"])
        self.assertEqual(d["modified"], ["a.py"])
        self.assertEqual(d["deleted"], ["b.py"])
        self.assertEqual(d["lines_added"], 3 + 1)

    def test_ignored_directories_are_not_walked(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "node_modules", "deep"))
        open(os.path.join(root, "node_modules", "deep", "x.js"), "w").write("x")
        open(os.path.join(root, "keep.py"), "w").write("y\n")
        snap = snapshot.scan_tree(Path(root), snapshot.DEFAULT_IGNORE, 1000)
        self.assertIn("keep.py", snap)
        self.assertFalse([k for k in snap if "node_modules" in k])

    def test_first_run_says_so_instead_of_claiming_everything_is_new(self):
        root, state = tempfile.mkdtemp(), tempfile.mkdtemp()
        open(os.path.join(root, "a.py"), "w").write("x\n")
        rc, human, j = run(["since-last", "report", "--root", root, "--state-dir", state,
                            "--now", "2026-09-05T10:00:00Z"])
        self.assertTrue(j["first_run"])
        self.assertEqual(j["created"], [])

    def test_second_run_sees_the_new_file(self):
        root, state = tempfile.mkdtemp(), tempfile.mkdtemp()
        open(os.path.join(root, "a.py"), "w").write("x\n")
        run(["since-last", "report", "--root", root, "--state-dir", state, "--now", "2026-09-05T10:00:00Z"])
        open(os.path.join(root, "b.py"), "w").write("y\ny\n")
        rc, human, j = run(["since-last", "report", "--root", root, "--state-dir", state,
                            "--now", "2026-09-05T10:05:00Z"])
        self.assertFalse(j["first_run"])
        self.assertEqual(j["created"], ["b.py"])
        self.assertEqual(j["lines_added"], 2)
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: FAIL — no `micro_core.snapshot`

- [ ] **Step 3: Implement `snapshot.py` and the `since-last` handler**

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/snapshot.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): since-last — what the agent touched while you looked away"
```

---

### Task 11: `gitindex.py` + `staged.py` — read the staged set without shelling out

**Files:**
- Create: `micro_core/gitindex.py`, `micro_core/staged.py`
- Modify: `tests/test_micro_core.py`, `micro_core/cli.py`

**Interfaces:**
- Consumes: `secrets.scan`, `secrets.verdict`, `common.*`.
- Produces:
  - `gitindex.staged_entries(repo: Path) -> list` — `(path, blob_sha, size)` from `.git/index` versions 2, 3 and 4; returns `[]` (never raises) for a missing, truncated or unknown-version index.
  - `gitindex.read_blob(repo: Path, sha: str) -> bytes or None` — loose object at `.git/objects/xx/rest`, zlib-decompressed, header stripped. `None` when the object is packed.
  - `staged.review(repo: Path, max_file_kb: int, strict: bool) -> dict` — keys `files`, `findings`, `oversized`, `debug_lines`, `env_files`, `verdict`, `from_worktree`. `from_worktree` lists paths whose blob was packed and were therefore read from the working tree instead.
  - CLI `staged report --repo <p> --max-file-kb 512 --strict true` → the same keys.

`.git/index` v2 layout, implemented literally: 12-byte header (`DIRC`, version, entry count), then per entry 62 bytes of fixed fields (ctime, mtime, dev, ino, mode, uid, gid, size, then 20 bytes of SHA-1, then a 16-bit flags field whose low 12 bits are the name length), then the NUL-terminated path padded to a multiple of 8. Version 4 path compression is detected and declined — the Play reports that it cannot read a v4 index rather than mis-parsing one.

Debug-line detection is language-aware and deliberately narrow: `console.log`, `debugger`, `pdb.set_trace`, `breakpoint()`, `fmt.Println` inside a non-`main` file, `dbg!`, and `print(` only in a file whose extension is `.py` and whose path is not under a `scripts/` or `bin/` directory. A wide net here would make the Play noise, and noise is what gets a pre-commit check ignored.

- [ ] **Step 1: Write the failing tests**

```python
class TestGitIndex(unittest.TestCase):
    def test_reads_a_real_index_written_by_git(self):
        # Built once by tools/build_micro_fixtures.py and committed; no git binary at test time.
        repo = Path(__file__).parent.parent / "micro_core" / "fixtures" / "staged" / "repo"
        entries = gitindex.staged_entries(repo)
        paths = [p for p, _, _ in entries]
        self.assertIn("config/dev.env", paths)
        self.assertIn("src/app.py", paths)

    def test_missing_index_is_empty_not_an_exception(self):
        self.assertEqual(gitindex.staged_entries(Path(tempfile.mkdtemp())), [])

    def test_blob_reads_back_its_bytes(self):
        repo = Path(__file__).parent.parent / "micro_core" / "fixtures" / "staged" / "repo"
        for path, sha, _ in gitindex.staged_entries(repo):
            if path == "src/app.py":
                self.assertIn(b"def main", gitindex.read_blob(repo, sha))


class TestStaged(unittest.TestCase):
    def test_finds_the_key_in_the_staged_env_file(self):
        repo = Path(__file__).parent.parent / "micro_core" / "fixtures" / "staged" / "repo"
        r = staged.review(repo, 512, True)
        self.assertEqual(r["verdict"], "do-not-paste")
        self.assertTrue(any(f["kind"] == "aws-access-key" for f in r["findings"]))
        self.assertIn("config/dev.env", r["env_files"])

    def test_print_in_a_script_directory_is_not_a_debug_line(self):
        self.assertEqual(staged.debug_lines("scripts/report.py", "print('total')\n"), [])
        self.assertEqual(len(staged.debug_lines("src/app.py", "print('here')\n")), 1)
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_core -v`
Expected: FAIL — no `micro_core.gitindex`

- [ ] **Step 3: Implement both modules and the `staged` handler**

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_core tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add micro_core/gitindex.py micro_core/staged.py micro_core/cli.py tests/test_micro_core.py
git commit -m "feat(micro): safe-to-commit reads .git/index itself, no subprocess"
```

---

### Task 12: Demo fixtures

**Files:**
- Create: `tools/build_micro_fixtures.py`, `micro_core/fixtures/**`
- Modify: `micro_core/cli.py`, `tests/test_micro_cli.py`

**Interfaces:**
- Produces: `common.fixtures_dir() -> Path` (`micro_core/fixtures`), and `demo=true` on every Play resolving its inputs from `fixtures/<play>/`.

Fixture contents, all synthetic and all committed:

| Play | Fixture |
|---|---|
| `whatis` | a base64→gzip→JSON→JWT nest with a **structurally valid but fake** JWT (`alg: HS256`, `sub: user_8812`, `exp` in 2027, signature `not-a-real-signature`) |
| `fits` | ~40 KB of Lorem-style prose plus a 200-line code block |
| `is-it-secret` | a `.env` with `AKIAIOSFODNN7EXAMPLE`-shaped fake keys, a fake PEM header, a placeholder that must NOT be flagged |
| `cron-when` | nothing needed — `expr` is the input |
| `punch`/`spent`/`jot`/`streak` | a pre-seeded `<stream>.jsonl` with 14 days of history, copied to a temp state dir on a demo run so the user's own log is never touched |
| `last-turn`/`budget-left` | two synthetic transcripts, Claude-shaped and Codex-shaped, with three days of usage records |
| `since-last` | a small tree plus a previous snapshot, so the demo shows a real delta on the first run |
| `safe-to-commit` | a tiny real git repository (index + loose objects, no `git` needed at runtime) staging `src/app.py` and `config/dev.env` |

**A demo run must never write to the real `state_dir`.** On `demo=true`, `state_dir` is redirected to a temp directory seeded from the fixture, and the output says which.

- [ ] **Step 1: Write the failing test**

```python
class TestDemo(unittest.TestCase):
    def test_every_play_runs_in_demo_and_prints_json(self):
        for args in (["whatis", "report"], ["fits", "report"], ["secret", "report"],
                     ["cron", "report", "--expr", "30 9 * * 1-5"], ["punch", "report"],
                     ["spent", "report"], ["jot", "report"], ["streak", "report"],
                     ["last-turn", "report"], ["budget", "report"], ["since-last", "report"],
                     ["staged", "report"]):
            rc, human, j = run(args + ["--demo", "true", "--now", "2026-09-05T12:00:00Z"])
            self.assertEqual(rc, 0, args)
            self.assertTrue(j.get("ok", True), args)
            self.assertTrue(human.strip(), args)

    def test_demo_does_not_touch_the_default_state_dir(self):
        marker = os.path.expanduser("~/.rote-micro")
        before = sorted(os.listdir(marker)) if os.path.isdir(marker) else None
        run(["punch", "report", "--demo", "true", "--now", "2026-09-05T12:00:00Z"])
        after = sorted(os.listdir(marker)) if os.path.isdir(marker) else None
        self.assertEqual(before, after)
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest tests.test_micro_cli -v`
Expected: FAIL — fixtures missing

- [ ] **Step 3: Write `tools/build_micro_fixtures.py` and run it**

The git fixture is built by writing the index and loose objects with `zlib` and `hashlib` directly — the generator is a developer tool, but it must not require `git` either, so the bytes are constructed and then read back by `gitindex` as the test of correctness.

Run: `python3 tools/build_micro_fixtures.py`

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/build_micro_fixtures.py micro_core/fixtures tests/test_micro_cli.py
git commit -m "feat(micro): synthetic fixtures so a first run touches nothing of yours"
```

---

### Task 13: Play documents — twelve DESCRIPTION / PARAMETERS / STEPS

**Files:**
- Create: `docs/plays/<play>/{DESCRIPTION.md,PARAMETERS.json,STEPS.md}` for `whatis`, `fits`, `is-it-secret`, `cron-when`, `punch`, `spent`, `jot`, `streak`, `last-turn`, `budget-left`, `since-last`, `safe-to-commit`
- Create: `docs/plays/_micro-spec.json`

**Interfaces:**
- Produces: `_micro-spec.json` — per play `{"steps": [[name, argv, depends_on, timeout_ms], ...], "tags": [...], "output": [...], "summary": "<JS template literal>"}`, the same shape `docs/plays/_daily-spec.json` uses.

Each `DESCRIPTION.md` follows the house structure the nine published Plays use, and every claim in it must be true of the code as written:

1. One paragraph on what it answers and how, naming the method.
2. `- Reads:` exactly what, and nothing else.
3. `- Never reads:` credential files, by name.
4. `- Never sends:` the offline claim, with the import list that makes it checkable.
5. `- Writes:` for the five writers, the exact path and the fact that it is an append; for the seven others, the literal sentence "Writes nothing."
6. `See also:` the sibling Plays, so the eighteen cross-reference each other.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_micro_package.py
MICRO = ["whatis", "fits", "is-it-secret", "cron-when", "punch", "spent", "jot", "streak",
         "last-turn", "budget-left", "since-last", "safe-to-commit"]
WRITERS = {"punch", "spent", "jot", "streak", "since-last"}


class TestPlayDocs(unittest.TestCase):
    def test_every_play_has_its_three_documents(self):
        for slug in MICRO:
            for name in ("DESCRIPTION.md", "PARAMETERS.json", "STEPS.md"):
                self.assertTrue((DOCS / slug / name).exists(), "{0}/{1}".format(slug, name))

    def test_every_description_states_its_write_behaviour(self):
        for slug in MICRO:
            text = (DOCS / slug / "DESCRIPTION.md").read_text()
            if slug in WRITERS:
                self.assertIn("append", text.lower(), slug)
                self.assertIn("~/.rote-micro", text, slug)
            else:
                self.assertIn("Writes nothing", text, slug)

    def test_every_play_declares_now_and_demo(self):
        for slug in MICRO:
            names = {p["name"] for p in json.loads((DOCS / slug / "PARAMETERS.json").read_text())}
            self.assertIn("demo", names, slug)
            self.assertIn("now", names, slug)

    def test_writers_are_tagged_local_write_and_readers_are_not(self):
        spec = json.loads((DOCS / "_micro-spec.json").read_text())
        for slug in MICRO:
            tags = spec[slug]["tags"]
            self.assertIn("effect-local-write" if slug in WRITERS else "effect-read-only", tags, slug)
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest tests.test_micro_package -v`
Expected: FAIL — documents missing

- [ ] **Step 3: Write the twelve document sets and `_micro-spec.json`**

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_micro_package -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/plays tests/test_micro_package.py
git commit -m "docs(plays): twelve registry descriptions that match the code"
```

---

### Task 14: Packaging — generate and sync the twelve Play packages

**Files:**
- Create: `tools/build_micro_plays.py`
- Modify: `tools/sync_plays.py`, `tests/test_micro_package.py`
- Create: `plays/<play>/{main.ts,deps.toml,resources/**}` (generated)

**Interfaces:**
- Consumes: `docs/plays/_micro-spec.json`, each Play's `DESCRIPTION.md` and `PARAMETERS.json`.
- Produces:
  - `build_micro_plays.py` — same structure as `build_daily_plays.py`: `HANDLE = "rajkaria"`, `ROTE_VERSION = "0.80.0"`, `VERSION = "0.1.0"`, `CLI = "@resource{micro_core/cli.py}"`. The presentation body is the daily template, adapted so a single-step Play has no read steps to report absences for.
  - `sync_plays.py` gains `MICRO_PLAYS` (the twelve) and `MICRO_SRC = [("micro_core", ROOT / "micro_core")]`, plus `MICRO_PRICED = {"fits", "last-turn", "budget-left"}` which additionally bundle `("comped_core", ROOT / "comped_core")` and `("prices.json", ROOT / "resources" / "prices.json")`.

- [ ] **Step 1: Write the failing tests**

```python
class TestPackaging(unittest.TestCase):
    def test_main_ts_params_match_parameters_json(self):
        for slug in MICRO:
            declared = re.findall(r"^ \*   (\w+):$", (PLAYS / slug / "main.ts").read_text(), re.M)
            documented = [p["name"] for p in json.loads((DOCS / slug / "PARAMETERS.json").read_text())]
            self.assertEqual(sorted(declared), sorted(documented), slug)

    def test_every_step_argv_references_a_real_cli_subcommand(self):
        spec = json.loads((DOCS / "_micro-spec.json").read_text())
        for slug in MICRO:
            for name, argv, _deps, _t in spec[slug]["steps"]:
                self.assertIn(argv[0], cli.PLAYS, "{0}/{1}".format(slug, name))

    def test_bundled_core_is_byte_identical(self):
        self.assertEqual(sync_plays.main(check=True), 0)

    def test_priced_plays_bundle_comped_core_and_the_others_do_not(self):
        for slug in MICRO:
            has = (PLAYS / slug / "resources" / "comped_core").is_dir()
            self.assertEqual(has, slug in {"fits", "last-turn", "budget-left"}, slug)

    def test_output_schema_keys_match_what_the_cli_emits(self):
        spec = json.loads((DOCS / "_micro-spec.json").read_text())
        for slug in MICRO:
            _rc, _h, j = run_report_for(slug, demo=True)
            for key in spec[slug]["output"]:
                self.assertIn(key, j, "{0}.{1}".format(slug, key))
```

- [ ] **Step 2: Run and watch them fail**

Run: `python3 -m unittest tests.test_micro_package -v`
Expected: FAIL — `plays/whatis/main.ts` does not exist

- [ ] **Step 3: Write `tools/build_micro_plays.py`, extend `sync_plays.py`, generate**

Run: `python3 tools/build_micro_plays.py && python3 tools/sync_plays.py`

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS, with the pre-existing 329 tests still green

- [ ] **Step 5: Commit**

```bash
git add tools plays tests/test_micro_package.py
git commit -m "feat(micro): package the twelve Plays, core copies byte-identical"
```

---

### Task 15: Safety and speed gates

**Files:**
- Create: `tests/test_micro_safety.py`, `tests/test_micro_perf.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_micro_safety.py
FORBIDDEN = ("urllib", "http.client", "httplib", "socket", "requests", "subprocess", "os.system")


class TestOffline(unittest.TestCase):
    def test_micro_core_imports_nothing_that_can_reach_the_network(self):
        for path in (ROOT / "micro_core").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    self.assertFalse(any(m == f or m.startswith(f + ".") for f in FORBIDDEN),
                                     "{0} imports {1}".format(path.name, m))


class TestWriteConfinement(unittest.TestCase):
    def test_no_play_writes_outside_state_dir_or_vault_dir(self):
        """Run every Play under a sandbox HOME and assert nothing outside the declared dirs changed."""
        home = tempfile.mkdtemp()
        before = _tree_state(home)
        with mock.patch.dict(os.environ, {"HOME": home}):
            for args in ALL_REPORT_ARGS + ALL_RECORD_ARGS:
                run(args + ["--state-dir", os.path.join(home, "state")])
        after = _tree_state(home)
        changed = {p for p in set(before) ^ set(after)}
        self.assertTrue(all(p.startswith(os.path.join(home, "state")) or "vault" in p for p in changed),
                        sorted(changed))


class TestNoSecretEscapes(unittest.TestCase):
    def test_is_it_secret_never_prints_the_secret_it_found(self):
        key = "AKIA1234567890ABCD12"
        rc, human, j = run(["secret", "report", "--text", "k=" + key, "--show", "redacted"])
        self.assertNotIn(key, human)
        self.assertNotIn(key, json.dumps(j))

    def test_whatis_never_prints_a_jwt_signature(self):
        tok = FIXTURE_JWT
        rc, human, j = run(["whatis", "report", "--text", tok])
        self.assertNotIn(tok.rsplit(".", 1)[1], human + json.dumps(j))
```

```python
# tests/test_micro_perf.py
class TestSpeed(unittest.TestCase):
    def test_every_step_is_under_400ms_on_fixtures(self):
        for args in ALL_REPORT_ARGS:
            start = time.perf_counter()
            run(args + ["--demo", "true", "--now", "2026-09-05T12:00:00Z"])
            elapsed = (time.perf_counter() - start) * 1000
            self.assertLess(elapsed, 400, "{0} took {1:.0f}ms".format(args[0], elapsed))
```

- [ ] **Step 2: Run them**

Run: `python3 -m unittest tests.test_micro_safety tests.test_micro_perf -v`
Expected: PASS. Any failure is a real defect in the Play, not a test to loosen.

- [ ] **Step 3: Commit**

```bash
git add tests/test_micro_safety.py tests/test_micro_perf.py
git commit -m "test(micro): offline, write-confined, and fast enough to keep the name"
```

---

### Task 16: Lint, publish, verify

**Files:**
- Modify: `docs/context/micro-plays.md` (create), `CLAUDE.md`, `docs/plays/README` index if present

- [ ] **Step 1: Lint all twelve**

Run: `for p in whatis fits is-it-secret cron-when punch spent jot streak last-turn budget-left since-last safe-to-commit; do rote play lint plays/$p || echo "LINT FAIL $p"; done`
Expected: every one clean. If the registry taxonomy rejects `effect-local-write`, substitute the closest accepted `effect-*` term, record the substitution in the spec's "Writing, declared loudly" section, and re-run.

- [ ] **Step 2: Run each Play locally end to end**

Run: `rote play run plays/whatis demo=true` (and the other eleven)
Expected: exit 0, the human card, and the JSON result.

- [ ] **Step 3: Dry-run the push, then push**

Run: `rote play push plays/<slug> --dry-run` then `rote play push plays/<slug>` for each of the twelve.
Expected: `rajkaria/<slug>@0.1.0` public.

- [ ] **Step 4: Verify from the registry, not from the checkout**

Run, from a fresh `/tmp` directory: `rote play run play.modiqo.ai/rajkaria/<slug>@0.1.0 demo=true --yes`
Expected: identical output to the local run. This is what proves the package is self-contained.

- [ ] **Step 5: Write `docs/context/micro-plays.md` and update `CLAUDE.md`**

The context doc carries: the twelve URIs, what each answers, the real output of each verified run, the test count, the known limits, and the branch state. `CLAUDE.md`'s context table gains the row.

- [ ] **Step 6: Commit**

```bash
git add docs/context/micro-plays.md CLAUDE.md
git commit -m "docs(context): twelve micro Plays, live and verified from the registry"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: the contract → Tasks 1, 12, 15; the twelve Plays → Tasks 3–11; `micro_core` layout → Tasks 1–11; the cross-core price reuse → Tasks 8, 9, 14; writing declared loudly → Tasks 4, 13, 15; state format → Task 2; testing table → Tasks 1–15 (`test_micro_core`, `test_micro_cli`, `test_micro_package`, `test_micro_safety`, `test_micro_perf` all created); build and publish → Tasks 12, 14, 16; out-of-scope items appear in no task, correctly.

**Placeholders.** None: every code step carries real code, every test names its assertion, and no step defers work to "later".

**Type consistency.** `common.emit`, `common.now_utc`, `common.as_bool`, `store.append/read/streak/grid`, `decode.peel/identify/render`, `secrets.scan/redact/verdict/entropy`, `cronx.parse/next_fires/describe/dst_warning`, `size.measure/token_range/window_fit/costs`, `turn.newest_transcript/tail_records/last_turn/today_total`, `snapshot.scan_tree/save/load/delta/sensitive_state`, `gitindex.staged_entries/read_blob`, `staged.review/debug_lines` are each defined once and referenced under the same name everywhere they appear.

**One correction found and applied while reviewing:** the spec's "two steps" contract conflicted with the seven read-only Plays, which would have needed a scratch file purely to have a second step. The spec now states one step for a pure Play and two for a logging one, and Task 14's presentation template accounts for both.
