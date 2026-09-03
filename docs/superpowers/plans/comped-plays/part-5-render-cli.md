# Part 5 — Tasks 11–13: renderers, CLI, cross-cutting tests

---

## Task 11: Renderers — terminal card, markdown report, explain, share text, SVG, PNG

**Files:**
- Create: `comped_core/render_terminal.py`, `comped_core/render_report.py`, `comped_core/render_svg.py`, `comped_core/render_png.py`
- Test: `tests/test_render.py`

**Interfaces:**
- `render_terminal(view: dict, color: bool) -> str` (64-column box, SPEC §8.1)
- `render_report(view) -> str`, `render_explain(summary) -> str`, `share_text(view) -> str`
- `render_svg(view, theme) -> str`, `render_png(svg_path: Path, out_dir: Path) -> tuple[str | None, str]` (png path or None, note)
- The **view dict** is the single input to every renderer, built by the CLI:

```python
view = {
  "window_days": 30, "window_start": "...", "window_end": "...",
  "total_usd": Decimal, "multiplier": Decimal | None, "plan_labels": ["Claude Max 20x", "ChatGPT Plus"], "plan_cost": Decimal | None,
  "per_model": [{"model","usd","share": Decimal}], "cache_share": Decimal, "active_days": int, "sessions": int,
  "delta": {...from baseline.delta...},
  "repeats": [{"label","count","repeat_usd","capture_command"}], "dividend_98": Decimal, "dividend_80": Decimal,
  "unpriced": [{"model","records","tokens"}], "price_as_of": "2026-09-01", "price_source": "...",
  "sources": [{"harness","found","files","duplicates","note"}], "written": [...], "play_uri": "https://play.modiqo.ai/<handle>/comped",
  "explain_path": "~/comped/comped-explain.txt", "handle": "priya"
}
```

- [ ] **Step 1: Write the failing tests.**

```python
import unittest, tempfile, pathlib
from decimal import Decimal
from comped_core.render_terminal import render_terminal
from comped_core.render_report import render_report, share_text
from comped_core.render_svg import render_svg
from comped_core.render_png import render_png

def V(mult=Decimal("42.9")):
    return {"window_days": 30, "window_start": "2026-08-04T00:00:00Z", "window_end": "2026-09-03T00:00:00Z", "total_usd": Decimal("8570.2"),
            "multiplier": mult, "plan_labels": ["Claude Max 20x", "ChatGPT Plus"], "plan_cost": Decimal("216.84"),
            "per_model": [{"model": "claude-opus-5", "usd": Decimal("5102.4"), "share": Decimal("0.61")}, {"model": "gpt-5.5", "usd": Decimal("456.05"), "share": Decimal("0.05")}],
            "cache_share": Decimal("0.78"), "active_days": 27, "sessions": 312,
            "delta": {"first_run": False, "days_since": 2, "total_usd_delta": Decimal("611.1"), "multiplier_delta": Decimal("0.9"), "new_repeats": [], "resolved_repeats": [], "per_model_delta": []},
            "repeats": [{"label": "push it to prod", "count": 4, "repeat_usd": Decimal("283"), "capture_command": '/play settle priya "push it to prod"'}],
            "dividend_98": Decimal("404"), "dividend_80": Decimal("330"), "unpriced": [{"model": "nano_banana", "records": 3, "tokens": 900}],
            "price_as_of": "2026-09-01", "price_source": "https://x", "sources": [{"harness": "claude-code", "found": True, "files": 10, "duplicates": 4000, "note": ""}],
            "written": [], "play_uri": "https://play.modiqo.ai/priya/comped", "explain_path": "~/comped/comped-explain.txt", "handle": "priya"}

class RenderTests(unittest.TestCase):
    def test_terminal_card_shape(self):
        out = render_terminal(V(), color=False); lines = out.splitlines()
        self.assertTrue(all(len(l) == 64 for l in lines), [len(l) for l in lines])
        self.assertIn("$8,570.20 comped", out); self.assertIn("42.9×", out); self.assertIn("since last run (2d ago): +$611.10, +0.9×", out)
        self.assertIn("4× \"push it to prod\"", out); self.assertIn("Rote dividend: $404 at 98% · $330 at 80%", out)
        self.assertIn("list-price equivalent, not a bill", out); self.assertIn("1 model unpriced", out)
    def test_terminal_no_plan(self):
        out = render_terminal(V(mult=None), color=False); self.assertIn("no plan given", out); self.assertNotIn("×  vs", out)
    def test_color_toggle(self):
        self.assertIn("\x1b[", render_terminal(V(), color=True)); self.assertNotIn("\x1b[", render_terminal(V(), color=False))
    def test_report_and_share(self):
        md = render_report(V())
        for h in ("## Card", "## Models", "## Sources", "## Repeat offenders", "## Rote dividend", "## Delta since last run", "## Unpriced models", "## Methodology", "## Privacy"): self.assertIn(h, md)
        self.assertIn("never reads", md.lower()); s = share_text(V())
        self.assertIn("$8,570", s); self.assertIn("43×", s); self.assertIn("@Modiqo", s); self.assertIn("play.modiqo.ai/priya/comped", s)
    def test_svg_escapes_and_size(self):
        v = V(); v["per_model"][0]["model"] = "<script>&"
        svg = render_svg(v, "dark"); self.assertIn('width="1200"', svg); self.assertIn("&lt;script&gt;&amp;", svg); self.assertNotIn("<script>", svg)
        self.assertIn("not a bill", svg); self.assertNotIn("<image", svg); self.assertNotIn("http", svg.split("play.modiqo.ai")[0].split("xmlns")[0])
    def test_png_missing_renderer_is_note(self):
        d = pathlib.Path(tempfile.mkdtemp()); p = d / "c.svg"; p.write_text(render_svg(V(), "dark"))
        png, note = render_png(p, d, renderers=[])
        self.assertIsNone(png); self.assertIn("PNG skipped", note)
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: comped_core.render_terminal`.

- [ ] **Step 3: Implement `render_terminal.py`.**

```python
from decimal import Decimal
W = 64
def money(d: Decimal) -> str: return f"${d:,.2f}"
def _c(s, code, on): return f"\x1b[{code}m{s}\x1b[0m" if on else s
def _row(text: str, color_len=0) -> str:
    pad = W - 4 - (len(text) - color_len)
    return "│ " + text + " " * max(pad, 0) + " │"
def _bar(share: Decimal, width=12) -> str: return "▇" * max(0, min(width, int(round(float(share) * width))))

def render_terminal(v: dict, color: bool) -> str:
    L = ["┌" + "─" * (W - 2) + "┐"]
    head = "COMPED"; right = f"last {v['window_days']} days"
    L.append(_row(head + " " * (W - 4 - len(head) - len(right)) + right))
    L.append(_row(""))
    total = f"{money(v['total_usd'])} comped"; L.append(_row(_c(total, "1;32", color), len(total) - len(total) if not color else 11))
    if v.get("multiplier") is not None:
        L.append(_row(f"{v['multiplier']:.1f}×  vs {' + '.join(v['plan_labels'])} ({money(v['plan_cost'])} prorated)"[: W - 4]))
    else:
        L.append(_row("no plan given: list-price total only (set plan= to see your multiplier)"[: W - 4]))
    L.append(_row(""))
    for m in v["per_model"][:3]:
        name = m["model"][:18].ljust(18); L.append(_row(f"{name} {money(m['usd']):>12} {int(round(float(m['share']) * 100)):>4}%   {_bar(m['share'])}"[: W - 4]))
    L.append(_row(f"cache read share {int(round(float(v['cache_share']) * 100))}%   active days {v['active_days']}/{v['window_days']}   sessions {v['sessions']}"[: W - 4]))
    d = v.get("delta") or {}
    if d.get("first_run"): L.append(_row("baseline saved; next run shows the delta"))
    else:
        md = f", {'+' if d['multiplier_delta'] >= 0 else ''}{d['multiplier_delta']:.1f}×" if d.get("multiplier_delta") is not None else ""
        L.append(_row(f"since last run ({d['days_since']}d ago): {'+' if d['total_usd_delta'] >= 0 else '-'}{money(abs(d['total_usd_delta']))}{md}"[: W - 4]))
    L.append(_row("")); L.append(_row("REPEAT OFFENDERS"))
    if not v["repeats"]: L.append(_row("none met the threshold (3 asks, 2 sessions, 2 days)"))
    for r in v["repeats"][:3]:
        label = f"{r['count']}× \"{r['label'][:34]}\""; L.append(_row(f"{label.ljust(44)}{money(r['repeat_usd']):>16}"[: W - 4]))
    if v["repeats"]:
        L.append(_row(f"Rote dividend: ${v['dividend_98']:,.0f} at 98% · ${v['dividend_80']:,.0f} at 80%"[: W - 4]))
        L.append(_row(f"capture: {v['repeats'][0]['capture_command']}"[: W - 4]))
    L.append(_row("")); L.append(_row(f"list-price equivalent, not a bill · prices as of {v['price_as_of']}"[: W - 4]))
    n = len(v["unpriced"]); names = ", ".join(u["model"] for u in v["unpriced"][:3])
    L.append(_row((f"{n} model{'s' if n != 1 else ''} unpriced ({names}) · " if n else "") + "explain →"[: W - 4]))
    L.append(_row(v["explain_path"][: W - 4]))
    L.append("└" + "─" * (W - 2) + "┘")
    return "\n".join(L)
```
(The colour row length bookkeeping: `_row(text, color_len)` subtracts escape-code length; the only coloured cell is the total; escape codes `\x1b[1;32m` + `\x1b[0m` are 11 chars.)

- [ ] **Step 4: Implement `render_report.py`.**

```python
from decimal import Decimal
PRIVACY = ("Reads: session logs under the configured directories. Nothing else. Never reads: ~/.claude.json, ~/.codex/auth.json, any credential, "
           "keychain or token file; plan is typed by you. Never sends: no network calls of any kind. Writes: only under out_dir, listed below. "
           "Message text: truncated to 120 characters and hashed by default.")
def money(d: Decimal) -> str: return f"${d:,.2f}"

def share_text(v: dict) -> str:
    mult = f" {v['multiplier']:.0f}×." if v.get("multiplier") is not None else ""
    plan = f" on a {money(v['plan_cost'])} plan" if v.get("plan_cost") is not None else ""
    return (f"I got comped {money(v['total_usd']).split('.')[0]}{plan} in the last {v['window_days']} days.{mult} "
            f"Measured from my own agent logs with the comped Play on @Modiqo's rote. Run it on yours: rote play run {v['play_uri']}")

def render_report(v: dict) -> str:
    o = [f"# Comped report · last {v['window_days']} days", "", "## Card", "", "```", v["terminal_card"], "```", "", share_text(v), "", "## Models", "",
         "| model | usd | share |", "|---|---|---|"] + [f"| {m['model']} | {money(m['usd'])} | {float(m['share']) * 100:.0f}% |" for m in v["per_model"]]
    o += ["", "## Sources", "", "| harness | found | files | duplicates removed | note |", "|---|---|---|---|---|"]
    o += [f"| {s['harness']} | {s['found']} | {s['files']} | {s['duplicates']} | {s['note']} |" for s in v["sources"]]
    o += ["", "## Repeat offenders", ""]
    if v["repeats"]:
        o += ["| asks | label | repeat cost | capture |", "|---|---|---|---|"] + [f"| {r['count']} | {r['label']} | {money(r['repeat_usd'])} | `{r['capture_command']}` |" for r in v["repeats"]]
        o += ["", "Codex and Cursor use `$play settle ...`; Kimi uses `/skill:play settle ...`."]
    else: o += ["None met the threshold (asked ≥ 3 times across ≥ 2 sessions on ≥ 2 days)."]
    o += ["", "## Rote dividend", "", f"Repeat cost that a Play would have avoided: ${v['dividend_98']:,.2f} at Modiqo's stated 98% reduction; ${v['dividend_80']:,.2f} at a conservative 80%. Both are derived from repeat cost = cluster cost minus its cheapest solve."]
    d = v.get("delta") or {}
    o += ["", "## Delta since last run", ""]
    o += ["First run: baseline saved."] if d.get("first_run") else [f"{d['days_since']} days since baseline: total {'+' if d['total_usd_delta'] >= 0 else ''}{money(d['total_usd_delta'])}; new repeats: {', '.join(d['new_repeats']) or 'none'}; resolved: {', '.join(d['resolved_repeats']) or 'none'}."]
    o += ["", "## Unpriced models", ""] + ([f"- {u['model']}: {u['records']} records, {u['tokens']:,} tokens (no rate in the table; never estimated)" for u in v["unpriced"]] or ["None."])
    o += ["", "## Methodology", "", "usd = uncached_input×in + cache_write×cw + cache_read×cr + output×out (reasoning bills as output). Claude Code lines deduplicated on (message.id, requestId); Codex per-turn values are differences of cumulative counters.",
          f"Price table as of {v['price_as_of']} from {v['price_source']}. Plan prorated by days/30.4375. Full arithmetic: {v['explain_path']}.", "", "## Privacy", "", PRIVACY, "", "Written:", ""] + [f"- {p}" for p in v["written"]]
    o += ["", "See also: session-ledger (the normalized log this reads) and wrong-turns (your agent's recurring mistakes, with drafted rules)."]
    return "\n".join(o) + "\n"

def render_explain(summary) -> str:
    return "\n".join(summary.explain) + "\n"
```

- [ ] **Step 5: Implement `render_svg.py`.**

```python
from decimal import Decimal
from xml.sax.saxutils import escape
THEMES = {"dark": {"bg": "#0b0f14", "fg": "#f2f5f7", "muted": "#8a94a0", "accent": "#5cf2a0", "bar": "#2a3440"},
          "light": {"bg": "#ffffff", "fg": "#0b0f14", "muted": "#5b6570", "accent": "#0f9d58", "bar": "#e6eaee"}}
def render_svg(v: dict, theme: str) -> str:
    t = THEMES.get(theme, THEMES["dark"]); e = escape
    total = f"${v['total_usd']:,.0f}"; mult = f"{v['multiplier']:.0f}×" if v.get("multiplier") is not None else "list price"
    plan = " + ".join(v.get("plan_labels") or []) or "no plan given"
    bars = []
    for i, m in enumerate(v["per_model"][:3]):
        y = 380 + i * 60; w = int(700 * float(m["share"]))
        bars.append(f'<rect x="80" y="{y}" width="700" height="28" rx="6" fill="{t["bar"]}"/><rect x="80" y="{y}" width="{max(w, 4)}" height="28" rx="6" fill="{t["accent"]}"/>'
                    f'<text x="80" y="{y - 10}" font-size="22" fill="{t["muted"]}">{e(m["model"])}</text><text x="1120" y="{y + 21}" font-size="22" text-anchor="end" fill="{t["fg"]}">${m["usd"]:,.0f}</text>')
    rep = v["repeats"][0]["label"] if v["repeats"] else "no repeat offenders yet"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" font-family="-apple-system, Inter, Segoe UI, Helvetica, Arial, sans-serif">
<rect width="1200" height="675" fill="{t["bg"]}"/>
<text x="80" y="90" font-size="28" letter-spacing="6" fill="{t["muted"]}">COMPED · LAST {v["window_days"]} DAYS</text>
<text x="80" y="230" font-size="120" font-weight="700" fill="{t["fg"]}">{e(total)} <tspan fill="{t["accent"]}">comped</tspan></text>
<text x="80" y="300" font-size="48" fill="{t["fg"]}">{e(mult)} <tspan fill="{t["muted"]}" font-size="32">vs {e(plan)}</tspan></text>
{"".join(bars)}
<text x="80" y="580" font-size="22" fill="{t["muted"]}">cache read {int(round(float(v["cache_share"]) * 100))}% · active days {v["active_days"]}/{v["window_days"]} · top repeat: {e(rep[:48])}</text>
<text x="80" y="630" font-size="20" fill="{t["muted"]}">list-price equivalent, not a bill · prices as of {e(v["price_as_of"])} · {e(v["play_uri"].replace("https://", ""))}</text>
</svg>
'''
```

- [ ] **Step 6: Implement `render_png.py` (the only module allowed to use subprocess).**

```python
import shutil, subprocess
from pathlib import Path
from typing import Optional, Tuple, List

def default_renderers() -> List[Tuple[str, list]]:
    r = []
    if shutil.which("rsvg-convert"): r.append(("rsvg-convert", ["rsvg-convert", "-w", "1200", "-o", "{png}", "{svg}"]))
    if shutil.which("qlmanage"): r.append(("qlmanage", ["qlmanage", "-t", "-s", "1200", "-o", "{dir}", "{svg}"]))
    return r

def render_png(svg_path: Path, out_dir: Path, renderers=None) -> Tuple[Optional[str], str]:
    renderers = default_renderers() if renderers is None else renderers
    png = Path(out_dir) / (Path(svg_path).stem + ".png")
    for name, argv in renderers:
        cmd = [a.format(png=str(png), svg=str(svg_path), dir=str(out_dir)) for a in argv]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        except (subprocess.SubprocessError, OSError):
            continue
        if name == "qlmanage":
            produced = Path(out_dir) / (Path(svg_path).name + ".png")
            if produced.exists(): produced.replace(png)
        if png.exists(): return str(png), f"PNG rendered with {name}"
    return None, "PNG skipped: no renderer found (rsvg-convert or macOS qlmanage); the SVG uploads to LinkedIn as-is and can be screenshotted for X"
```

- [ ] **Step 7: Run tests; fix the 64-column assertion until every line is exactly 64 characters** (box-drawing chars count as one). Expected: pass.

- [ ] **Step 8: Commit.** `git add -A && git commit -m "feat(render): terminal card, markdown report, share text, svg card, opportunistic png"`

---

## Task 12: CLI

**Files:**
- Create: `comped_core/cli.py`, `comped_core/__main__.py` (`from .cli import main; main()`)
- Test: `tests/test_cli.py`

**Interfaces:** subcommands and flags exactly as in the plan index, plus two required by rote's play-shape standard (one reading = one step; see `docs/research/ROTE-FORMAT.md`): `ledger --only <harness>` writes `ledger-<harness>.jsonl` for exactly one harness, and `merge --out-dir` joins every `ledger-*.jsonl` present into `ledger.jsonl` + `ledger-summary.json` (running turn attribution on the merged set). Without `--only`, `ledger` behaves as before (all harnesses, one file), which the tests and the determinism suite keep using.

Failure contract (rote renders it as a labelled unknown): expected absence, such as a missing log directory or zero records in the window, prints `{"ok": true, "warning": "<reason>", ...}` and exits 0. Bad arguments exit 2 with `{"ok": false, "error": ...}`. Unexpected exceptions are caught, printed as `{"ok": false, "error": "<type>: <msg>"}` to stdout, echoed to stderr, and exit 1, never a traceback. Booleans arrive as strings `true`/`false` from rote parameters. Steps have no TTY, so nothing may prompt.

- [ ] **Step 1: Write the failing tests.**

```python
import unittest, tempfile, pathlib, json, subprocess, sys
FIX = {"--claude-dir": "resources/fixtures/claude", "--codex-dir": "resources/fixtures/codex", "--pi-dir": "resources/fixtures/pi", "--opencode-dir": "resources/fixtures/opencode/storage"}
NOW = "2026-09-03T00:00:00Z"
def run(*args):
    p = subprocess.run([sys.executable, "-m", "comped_core", *args], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else None), p.stdout, p.stderr
class CliTests(unittest.TestCase):
    def setUp(self): self.out = tempfile.mkdtemp()
    def _ledger(self):
        return run("ledger", *sum(([k, v] for k, v in FIX.items()), []), "--days-back", "3650", "--out-dir", self.out, "--include-subagents", "true", "--redact", "true", "--now", NOW)
    def test_only_and_merge_equal_full_ledger(self):
        full = tempfile.mkdtemp(); parts = tempfile.mkdtemp()
        run("ledger", *sum(([k, v] for k, v in FIX.items()), []), "--days-back", "3650", "--out-dir", full, "--now", NOW)
        for h in ("claude-code", "codex", "pi", "opencode"):
            rc, j, *_ = run("ledger", *sum(([k, v] for k, v in FIX.items()), []), "--days-back", "3650", "--out-dir", parts, "--now", NOW, "--only", h)
            self.assertEqual(rc, 0); self.assertTrue(pathlib.Path(parts, f"ledger-{h}.jsonl").exists())
        rc, j, *_ = run("merge", "--out-dir", parts); self.assertEqual(rc, 0)
        self.assertEqual(pathlib.Path(full, "ledger.jsonl").read_bytes(), pathlib.Path(parts, "ledger.jsonl").read_bytes())
    def test_expected_absence_is_warning_not_error(self):
        rc, j, *_ = run("ledger", "--claude-dir", "/nope", "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", self.out, "--now", NOW)
        self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertIn("warning", j)
    def test_full_pipeline(self):
        rc, j, *_ = self._ledger(); self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertTrue(pathlib.Path(self.out, "ledger.jsonl").exists())
        rc, j, *_ = run("price", "--out-dir", self.out, "--plan", "claude-max-200,chatgpt-plus-20", "--days-back", "3650", "--now", NOW)
        self.assertEqual(rc, 0); self.assertGreater(float(j["total_usd"]), 0); self.assertIsNotNone(j["multiplier"])
        rc, j, *_ = run("repeats", "--out-dir", self.out, "--repeat-threshold", "3", "--handle", "priya"); self.assertEqual(rc, 0); self.assertGreaterEqual(len(j["repeats"]), 1)
        rc, j, out, _ = run("card", "--out-dir", self.out, "--card-theme", "dark"); self.assertEqual(rc, 0)
        self.assertIn("COMPED", out); self.assertTrue(pathlib.Path(self.out, "comped-card.svg").exists()); self.assertTrue(pathlib.Path(self.out, "comped-report.md").exists())
        rc, j, *_ = run("wrongturns", "--out-dir", self.out, "--min-recurrence", "2", "--show-snippets", "true"); self.assertEqual(rc, 0)
        rc, j, *_ = run("rules", "--out-dir", self.out, "--rules-target", "both"); self.assertEqual(rc, 0); self.assertTrue(pathlib.Path(self.out, "wrong-turns-rules.md").exists())
        rc, j, *_ = run("verify", "--out-dir", self.out); self.assertEqual(rc, 0); self.assertTrue(j["ok"])
        rc, j, *_ = run("sources", *sum(([k, v] for k, v in FIX.items()), [])); self.assertEqual(rc, 0); self.assertTrue(all(s["found"] for s in j["sources"]))
        rc, j, *_ = run("summary", "--out-dir", self.out); self.assertEqual(rc, 0); self.assertGreater(j["records"], 0)
    def test_bad_args_exit_2_json(self):
        rc, j, *_ = run("price", "--out-dir", self.out, "--days-back", "x"); self.assertEqual(rc, 2); self.assertFalse(j["ok"])
    def test_missing_ledger_is_json_error(self):
        rc, j, *_ = run("card", "--out-dir", self.out); self.assertEqual(rc, 1); self.assertFalse(j["ok"]); self.assertIn("ledger", j["error"])
```

- [ ] **Step 2: Run to verify failure.** Expected: `No module named comped_core.__main__`.

- [ ] **Step 3: Implement `comped_core/cli.py`.**

```python
import argparse, json, os, sys, dataclasses
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
from .timeutil import parse_ts, window_start, iso
from .adapters import parse_all
from .ledger import write_ledger, read_ledger, summary as ledger_summary
from .prices import load_table
from .plans import load_plans, parse_plan_ids
from .pricing import price_ledger
from .repeats import find_repeats
from .wrongturns import classify, draft_rules
from .baseline import load_baseline, save_baseline, delta
from .render_terminal import render_terminal
from .render_report import render_report, render_explain, share_text
from .render_svg import render_svg
from .render_png import render_png

def _bool(s) -> bool: return str(s).strip().lower() in ("1", "true", "yes", "y", "on")
def _now(s): return parse_ts(s) if s else datetime.now(timezone.utc)
def _json(o):
    def enc(x):
        if isinstance(x, Decimal): return str(x)
        if dataclasses.is_dataclass(x): return dataclasses.asdict(x)
        raise TypeError(str(type(x)))
    print(json.dumps(o, default=enc, sort_keys=True))
def _state(out_dir: Path, name: str, doc=None):
    p = Path(out_dir).expanduser() / f".{name}.json"
    if doc is None:
        if not p.exists(): raise FileNotFoundError(f"run the earlier step first: missing {p.name} in {out_dir}")
        return json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(doc, default=str, sort_keys=True, indent=1) + "\n", encoding="utf-8")

def cmd_ledger(a):
    now = _now(a.now); cfg = {"claude_dir": a.claude_dir, "codex_dir": a.codex_dir, "pi_dir": a.pi_dir, "opencode_dir": a.opencode_dir,
                             "include_subagents": _bool(a.include_subagents), "redact": _bool(a.redact), "since": window_start(now, a.days_back), "now": now}
    if a.only:
        from .adapters import ADAPTERS
        if a.only not in ADAPTERS: raise ValueError(f"--only must be one of {sorted(ADAPTERS)}")
        for h, (_, key) in ADAPTERS.items():
            if h != a.only: cfg[key] = "/nonexistent"     # other adapters report found=false and are dropped below
    led = parse_all(cfg)
    if a.only:
        led.sources = [s for s in led.sources if s.harness == a.only]
        out = Path(a.out_dir).expanduser(); out.mkdir(parents=True, exist_ok=True)
        p = out / f"ledger-{a.only}.jsonl"
        with open(p, "w", encoding="utf-8") as fh:
            for kind, items in (("record", led.records), ("human", led.humans), ("tool", led.tools), ("source", led.sources)):
                for it in items: fh.write(json.dumps({"kind": kind, **dataclasses.asdict(it)}, sort_keys=True) + "\n")
        written = [str(p)]
    else:
        written = write_ledger(led, a.out_dir)
    _state(a.out_dir, "ledger-args", {"days_back": a.days_back, "now": iso(now), "redact": _bool(a.redact)})
    s = ledger_summary(led); s.update({"ok": True, "written": written, "note": "; ".join(f"{x['harness']}: {x['note']}" for x in s["sources"] if x["note"])})
    absent = [x["harness"] for x in s["sources"] if not x["found"]]
    if absent and len(absent) == len(s["sources"]): s["warning"] = f"no log directory found for {', '.join(absent)}; nothing to read"
    elif s["records"] == 0: s["warning"] = "no usage records in the window"
    return s

def cmd_merge(a):
    from .models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger
    from .ledger import attribute_turns
    out = Path(a.out_dir).expanduser(); parts = sorted(out.glob("ledger-*.jsonl")); parts = [p for p in parts if p.name != "ledger-summary.json"]
    if not parts: return {"ok": True, "warning": "no partial ledgers (ledger-<harness>.jsonl) found to merge", "written": [], "note": ""}
    recs, hums, tools, srcs = [], [], [], []
    for p in parts:
        for line in open(p, encoding="utf-8"):
            o = json.loads(line); kind = o.pop("kind")
            {"record": lambda: recs.append(UsageRecord(**o)), "human": lambda: hums.append(HumanMessage(**o)),
             "tool": lambda: tools.append(ToolEvent(**o)), "source": lambda: srcs.append(Source(**o))}[kind]()
    st = _state(a.out_dir, "ledger-args")
    led = Ledger(sorted(recs, key=lambda r: (r.harness, r.session_id, r.timestamp, r.record_id)), sorted(hums, key=lambda h: (h.harness, h.session_id, h.timestamp, h.message_id)),
                 sorted(tools, key=lambda t: (t.harness, t.session_id, t.timestamp, t.event_id)), sorted(srcs, key=lambda s: s.harness), st["now"])
    attribute_turns(led); written = write_ledger(led, out)
    s = ledger_summary(led); s.update({"ok": True, "written": written, "note": f"merged {len(parts)} partial ledgers"})
    if s["records"] == 0: s["warning"] = "no usage records in the window"
    return s

def cmd_price(a):
    st = _state(a.out_dir, "ledger-args"); now = _now(a.now or st["now"]); led = read_ledger(a.out_dir)
    table = load_table(Path(a.rates_path).expanduser() if a.rates_path else None); plans = load_plans()
    s = price_ledger(led, table, plans, parse_plan_ids(a.plan), a.days_back or st["days_back"], now)
    doc = {"total_usd": s.total_usd, "per_model": s.per_model, "unpriced": s.unpriced, "cache_share": s.cache_share, "active_days": s.active_days,
           "sessions": s.sessions, "per_turn_usd": s.per_turn_usd, "plan_cost": s.plan_cost, "multiplier": s.multiplier, "plan_ids": s.plan_ids,
           "explain": s.explain, "window_start": s.window_start, "window_end": s.window_end, "price_meta": s.price_meta, "days_back": a.days_back or st["days_back"], "now": iso(now)}
    _state(a.out_dir, "priced", doc)
    p = Path(a.out_dir).expanduser() / "comped-explain.txt"; p.write_text(render_explain(s), encoding="utf-8")
    return {"ok": True, "written": [str(p)], "total_usd": s.total_usd, "multiplier": s.multiplier, "plan_cost": s.plan_cost, "per_model": s.per_model,
            "unpriced": s.unpriced, "cache_share": s.cache_share, "active_days": s.active_days, "sessions": s.sessions, "note": ""}

def cmd_repeats(a):
    pr = _state(a.out_dir, "priced"); led = read_ledger(a.out_dir)
    per_turn = {k: Decimal(v) for k, v in pr["per_turn_usd"].items()}
    cl = find_repeats(led.humans, per_turn, a.repeat_threshold, a.handle or "")
    doc = [dataclasses.asdict(c) for c in cl]; _state(a.out_dir, "repeats", {"clusters": doc, "handle": a.handle or ""})
    return {"ok": True, "written": [], "repeats": doc, "dividend_98": sum((c.dividend_98 for c in cl), Decimal("0")), "dividend_80": sum((c.dividend_80 for c in cl), Decimal("0")), "note": ""}

def _view(a, pr, rp, led):
    plans = load_plans(); labels = [plans["plans"][p]["label"] for p in pr["plan_ids"]]
    total = Decimal(pr["total_usd"]); pm = [{"model": m["model"], "usd": Decimal(m["usd"]), "share": (Decimal(m["usd"]) / total if total else Decimal("0"))} for m in pr["per_model"]]
    cl = rp["clusters"]; handle = rp.get("handle") or "<handle>"
    return {"window_days": pr["days_back"], "window_start": pr["window_start"], "window_end": pr["window_end"], "total_usd": total,
            "multiplier": Decimal(pr["multiplier"]) if pr["multiplier"] is not None else None, "plan_labels": labels,
            "plan_cost": Decimal(pr["plan_cost"]) if pr["plan_cost"] is not None else None, "per_model": pm, "cache_share": Decimal(pr["cache_share"]),
            "active_days": pr["active_days"], "sessions": pr["sessions"],
            "repeats": [{"label": c["label"], "count": c["count"], "repeat_usd": Decimal(c["repeat_usd"]), "capture_command": c["capture_command"]} for c in cl],
            "dividend_98": sum((Decimal(c["dividend_98"]) for c in cl), Decimal("0")), "dividend_80": sum((Decimal(c["dividend_80"]) for c in cl), Decimal("0")),
            "unpriced": pr["unpriced"], "price_as_of": pr["price_meta"].get("as_of", "?"), "price_source": pr["price_meta"].get("source_url", "?"),
            "sources": [dataclasses.asdict(s) for s in led.sources], "written": [], "play_uri": f"https://play.modiqo.ai/{handle}/comped",
            "explain_path": str(Path(a.out_dir).expanduser() / "comped-explain.txt"), "handle": handle}

def cmd_card(a):
    pr = _state(a.out_dir, "priced"); rp = _state(a.out_dir, "repeats") if (Path(a.out_dir).expanduser() / ".repeats.json").exists() else {"clusters": [], "handle": ""}
    led = read_ledger(a.out_dir); now = _now(pr["now"]); v = _view(a, pr, rp, led); out = Path(a.out_dir).expanduser()
    class _S: pass
    s = _S(); s.total_usd = v["total_usd"]; s.multiplier = v["multiplier"]; s.per_model = v["per_model"]
    class _C: pass
    cls = []
    for r in v["repeats"]:
        c = _C(); c.label = r["label"]; cls.append(c)
    v["delta"] = delta(load_baseline(out), s, cls, now)
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    v["terminal_card"] = render_terminal(v, False); card = render_terminal(v, color)
    svg = out / "comped-card.svg"; svg.write_text(render_svg(v, a.card_theme), encoding="utf-8"); written = [str(svg)]
    png, note = render_png(svg, out)
    if png: written.append(png)
    written.append(save_baseline(out, s, cls, now))
    v["written"] = written + [str(out / "comped-report.md"), str(out / "comped-explain.txt"), str(out / "ledger.jsonl")]
    rep = out / "comped-report.md"; rep.write_text(render_report(v), encoding="utf-8"); written.append(str(rep))
    sh = out / "comped-share.txt"; sh.write_text(share_text(v) + "\n", encoding="utf-8"); written.append(str(sh))
    print(card); print(); print(share_text(v)); print()
    return {"ok": True, "written": written, "total_usd": v["total_usd"], "multiplier": v["multiplier"], "repeats": len(v["repeats"]), "png": png, "note": note}

def cmd_wrongturns(a):
    led = read_ledger(a.out_dir); p = Path(a.out_dir).expanduser() / ".priced.json"
    per_turn = {k: Decimal(v) for k, v in (json.loads(p.read_text())["per_turn_usd"].items() if p.exists() else [])}
    cl = classify(led, per_turn, a.min_recurrence, _bool(a.show_snippets)); doc = [dataclasses.asdict(c) for c in cl]
    _state(a.out_dir, "wrongturns", {"classes": doc})
    return {"ok": True, "written": [], "classes": doc, "note": "" if per_turn else "no priced ledger found; recovery costs are 0 (run price first for costs)"}

def cmd_rules(a):
    wt = _state(a.out_dir, "wrongturns"); from .wrongturns import MistakeClass
    cl = [MistakeClass(**{**c, "recovery_usd": Decimal(c["recovery_usd"])}) for c in wt["classes"]]
    out = Path(a.out_dir).expanduser(); rules = out / "wrong-turns-rules.md"; rules.write_text(draft_rules(cl, a.rules_target), encoding="utf-8")
    rep = out / "wrong-turns-report.md"
    lines = ["# Wrong turns report", "", "| kind | confidence | tool | signature | count | sessions | recovery | evidence |", "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {c.kind} | {c.confidence} | {c.tool_name} | {c.signature} | {c.count} | {c.sessions} | ${c.recovery_usd:.2f} | {c.evidence} |" for c in cl]
    lines += ["", f"Drafted rules: {rules}", "", "Read-only: nothing was applied to CLAUDE.md or AGENTS.md."]
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8"); print("\n".join(lines))
    return {"ok": True, "written": [str(rules), str(rep)], "classes": len(cl), "note": ""}

def cmd_explain(a):
    p = Path(a.out_dir).expanduser() / "comped-explain.txt"; print(p.read_text(encoding="utf-8")); return {"ok": True, "written": [], "note": ""}

def cmd_sources(a):
    """No parsing: report which log directories exist and how many files each holds. The session-ledger Play's first step."""
    out = []
    for harness, key, pat in (("claude-code", a.claude_dir, "*/*.jsonl"), ("codex", a.codex_dir, "*/*/*/rollout-*.jsonl"), ("pi", a.pi_dir, "*.jsonl"), ("opencode", a.opencode_dir, "message/**/*.json")):
        p = Path(key).expanduser(); n = sum(1 for _ in p.glob(pat)) if p.is_dir() else 0
        out.append({"harness": harness, "root": str(p), "found": p.is_dir(), "files": n})
    return {"ok": True, "written": [], "sources": out, "note": "; ".join(f"{s['harness']}: not found" for s in out if not s["found"])}

def cmd_summary(a):
    p = Path(a.out_dir).expanduser() / "ledger-summary.json"; doc = json.loads(p.read_text(encoding="utf-8")); print(json.dumps(doc, indent=1, sort_keys=True))
    return {"ok": True, "written": [], "note": "", **doc}

def cmd_verify(a):
    pr = _state(a.out_dir, "priced"); led = read_ledger(a.out_dir); table = load_table(); plans = load_plans()
    s = price_ledger(led, table, plans, pr["plan_ids"], pr["days_back"], _now(pr["now"]))
    ok = str(s.total_usd) == str(pr["total_usd"])
    return {"ok": ok, "written": [], "recomputed_total_usd": s.total_usd, "reported_total_usd": pr["total_usd"], "note": "totals reproduce" if ok else "MISMATCH: ledger or price table changed since the report"}

def build_parser():
    P = argparse.ArgumentParser(prog="comped"); sub = P.add_subparsers(dest="cmd", required=True)
    def common(p): p.add_argument("--out-dir", default="~/comped")
    p = sub.add_parser("ledger"); common(p)
    for k, d in (("claude-dir", "~/.claude/projects"), ("codex-dir", "~/.codex/sessions"), ("pi-dir", "~/.pi/agent/sessions"), ("opencode-dir", "~/.local/share/opencode/storage")): p.add_argument(f"--{k}", default=d)
    p.add_argument("--days-back", type=int, default=30); p.add_argument("--include-subagents", default="true"); p.add_argument("--redact", default="true"); p.add_argument("--now", default="")
    p.add_argument("--only", default="", help="read exactly one harness and write ledger-<harness>.jsonl (rote: one reading = one step)")
    p = sub.add_parser("merge"); common(p)
    p = sub.add_parser("price"); common(p); p.add_argument("--plan", default=""); p.add_argument("--rates-path", default=""); p.add_argument("--days-back", type=int, default=0); p.add_argument("--now", default="")
    p = sub.add_parser("repeats"); common(p); p.add_argument("--repeat-threshold", type=int, default=3); p.add_argument("--handle", default="")
    p = sub.add_parser("card"); common(p); p.add_argument("--card-theme", default="dark")
    p = sub.add_parser("wrongturns"); common(p); p.add_argument("--min-recurrence", type=int, default=3); p.add_argument("--show-snippets", default="true")
    p = sub.add_parser("rules"); common(p); p.add_argument("--rules-target", default="both")
    p = sub.add_parser("explain"); common(p)
    p = sub.add_parser("verify"); common(p)
    p = sub.add_parser("sources")
    for k, d in (("claude-dir", "~/.claude/projects"), ("codex-dir", "~/.codex/sessions"), ("pi-dir", "~/.pi/agent/sessions"), ("opencode-dir", "~/.local/share/opencode/storage")): p.add_argument(f"--{k}", default=d)
    p = sub.add_parser("summary"); common(p)
    return P

def main(argv=None):
    P = build_parser()
    try: a = P.parse_args(argv)
    except SystemExit: _json({"ok": False, "error": "bad arguments; see --help"}); return 2
    try:
        _json(globals()[f"cmd_{a.cmd}"](a)); return 0
    except Exception as e:  # never a traceback
        _json({"ok": False, "error": f"{type(e).__name__}: {e}"}); return 1

if __name__ == "__main__":
    sys.exit(main())
```
(argparse writes its own error to stderr and raises SystemExit(2); we catch it and emit JSON. `python3 -m comped_core` needs `__main__.py` containing `import sys; from .cli import main; sys.exit(main())`.)

- [ ] **Step 4: Run tests.** Expected: pass. `test_full_pipeline` exercises every subcommand on fixtures; `--days-back 3650` because fixture timestamps are fixed at 2026-09-01 and `--now` is pinned.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(cli): json-first subcommands for ledger, price, repeats, card, wrongturns, rules, explain, verify"`

---

## Task 13: Cross-cutting tests

**Files:**
- Create: `tests/test_determinism.py`, `tests/test_no_network.py`, `tests/test_robustness.py`, `tests/test_conformance_ccusage.py`, `tests/test_perf.py`, `tests/test_no_credential_reads.py`

- [ ] **Step 1: Determinism.**

```python
import unittest, tempfile, pathlib, subprocess, sys, hashlib
FIX = ["--claude-dir", "resources/fixtures/claude", "--codex-dir", "resources/fixtures/codex", "--pi-dir", "resources/fixtures/pi", "--opencode-dir", "resources/fixtures/opencode/storage"]
def pipeline(out):
    for args in (["ledger", *FIX, "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"], ["price", "--plan", "claude-max-200", "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"],
                 ["repeats", "--handle", "demo"], ["card"], ["wrongturns", "--min-recurrence", "2"], ["rules"]):
        subprocess.run([sys.executable, "-m", "comped_core", *args, "--out-dir", out], check=True, capture_output=True, env={"NO_COLOR": "1", "PATH": ""})
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path(out).glob("*") if p.suffix in (".md", ".svg", ".txt", ".jsonl", ".json")}
class Determinism(unittest.TestCase):
    def test_two_runs_identical(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp(); ha, hb = pipeline(a), pipeline(b)
        self.assertEqual({k: v for k, v in ha.items() if k != "comped-baseline.json"}, {k: v for k, v in hb.items() if k != "comped-baseline.json"})
```
(`PATH=""` also proves the pipeline needs no external binary; PNG is skipped with a note.)

- [ ] **Step 2: No network and no credential reads (static).**

```python
import unittest, pathlib, re
SRC = pathlib.Path("comped_core")
class StaticSafety(unittest.TestCase):
    def test_no_network_imports(self):
        for p in SRC.rglob("*.py"):
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(urllib|http|socket|requests|ssl)\b", p.read_text(), re.M), p)
    def test_subprocess_only_in_png(self):
        for p in SRC.rglob("*.py"):
            if p.name != "render_png.py": self.assertNotIn("subprocess", p.read_text(), p)
    def test_no_credential_paths(self):
        bad = re.compile(r"\.claude\.json|auth\.json|config\.toml|keychain|credential", re.I)
        for p in SRC.rglob("*.py"):
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if bad.search(line) and "Never reads" not in line and "PRIVACY" not in line:
                    self.fail(f"{p}:{n} references a credential path: {line.strip()}")
```

- [ ] **Step 3: Robustness.**

```python
import unittest, tempfile, pathlib, os, subprocess, sys, json
class Robustness(unittest.TestCase):
    def _run(self, claude_dir):
        p = subprocess.run([sys.executable, "-m", "comped_core", "ledger", "--claude-dir", claude_dir, "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", tempfile.mkdtemp(), "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1]), p.stderr
    def test_empty_and_missing_dirs(self):
        rc, j, err = self._run(tempfile.mkdtemp()); self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertEqual(j["records"], 0); self.assertEqual(err, "")
        rc, j, _ = self._run("/definitely/missing"); self.assertEqual(rc, 0); self.assertFalse(j["sources"][0]["found"])
    def test_garbage_files(self):
        d = pathlib.Path(tempfile.mkdtemp()); proj = d / "p"; proj.mkdir()
        (proj / "a.jsonl").write_text('{"type":"assistant","message":{"usage":{}}}\n{"type":"assistant"}\n\x00\x01binary\n{"type":"user","message":{"content":[]}}\n{"trunc')
        (proj / "b.jsonl").write_bytes(b"\xff\xfe\x00\x00")
        rc, j, err = self._run(str(d)); self.assertEqual(rc, 0); self.assertTrue(j["ok"]); self.assertGreater(j["sources"][0]["unparsed"], 0)
    def test_unreadable_file(self):
        d = pathlib.Path(tempfile.mkdtemp()); proj = d / "p"; proj.mkdir(); f = proj / "a.jsonl"; f.write_text("{}\n"); os.chmod(f, 0)
        try:
            rc, j, _ = self._run(str(d)); self.assertEqual(rc, 0); self.assertIn("unreadable", j["sources"][0]["note"])
        finally: os.chmod(f, 0o644)
```

- [ ] **Step 4: ccusage conformance (skips when npx is unavailable).**

```python
import unittest, shutil, subprocess, json, tempfile, sys, pathlib
from decimal import Decimal
class CcusageConformance(unittest.TestCase):
    def test_claude_totals_match_ccusage(self):
        if not shutil.which("npx"): self.skipTest("npx not available")
        out = tempfile.mkdtemp()
        subprocess.run([sys.executable, "-m", "comped_core", "ledger", "--claude-dir", "resources/fixtures/claude", "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", out, "--days-back", "3650", "--now", "2026-12-31T00:00:00Z"], check=True, capture_output=True)
        p = subprocess.run([sys.executable, "-m", "comped_core", "price", "--out-dir", out], capture_output=True, text=True, check=True)
        ours = {m["model"]: (m["input"], m["cache_write"], m["cache_read"], m["output"]) for m in json.loads(p.stdout.splitlines()[-1])["per_model"]}
        env = {"CLAUDE_CONFIG_DIR": str(pathlib.Path("resources/fixtures").resolve()), "PATH": subprocess.os.environ["PATH"]}
        # ccusage reads $CLAUDE_CONFIG_DIR/projects; our fixture root is resources/fixtures/claude, so symlink it
        cfg = pathlib.Path(tempfile.mkdtemp()); (cfg / "projects").symlink_to(pathlib.Path("resources/fixtures/claude").resolve()); env["CLAUDE_CONFIG_DIR"] = str(cfg)
        try: r = subprocess.run(["npx", "-y", "ccusage@latest", "daily", "--json", "--offline"], capture_output=True, text=True, timeout=300, env=env, check=True)
        except (subprocess.SubprocessError, OSError) as e: self.skipTest(f"ccusage unavailable: {e}")
        cc = json.loads(r.stdout)
        theirs = {}
        for day in cc.get("daily", []):
            for mb in day.get("modelBreakdowns", []):
                t = theirs.setdefault(mb["modelName"], [0, 0, 0, 0])
                t[0] += mb["inputTokens"]; t[1] += mb["cacheCreationTokens"]; t[2] += mb["cacheReadTokens"]; t[3] += mb["outputTokens"]
        for model, toks in ours.items():
            if model in theirs: self.assertEqual(tuple(theirs[model]), toks, model)
```
Token counts are compared rather than dollars because ccusage may carry a different price snapshot; identical token totals under identical dedup is the conformance claim. If ccusage's dedup differs, document the difference in `docs/research/LANDSCAPE.md` and keep ours (ours is measured).

- [ ] **Step 5: Performance guard.**

```python
import unittest, time, tempfile, subprocess, sys, pathlib, os
class Perf(unittest.TestCase):
    def test_real_logs_under_10s(self):
        home = pathlib.Path.home()
        if not (home / ".claude" / "projects").is_dir() or os.environ.get("CI"): self.skipTest("no real logs or CI")
        t = time.time()
        subprocess.run([sys.executable, "-m", "comped_core", "ledger", "--out-dir", tempfile.mkdtemp(), "--days-back", "30"], check=True, capture_output=True)
        self.assertLess(time.time() - t, 10.0)
```

- [ ] **Step 6: Run the whole suite; profile if perf fails** (`python3 -m cProfile -s cumtime -m comped_core ledger ...`), the usual fix is avoiding `json.loads` on lines that cannot be assistant/user lines: pre-check `'"usage"' in line or '"type":"user"' in line` before parsing.

- [ ] **Step 7: Commit.** `git add -A && git commit -m "test: determinism, static safety, robustness, ccusage conformance, perf guard"`
