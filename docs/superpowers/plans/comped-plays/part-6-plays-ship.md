# Part 6 — Tasks 14–16: Play packaging and capture, public repo, distribution and judge loop

Prerequisite: `docs/research/ROTE-FORMAT.md` exists with every heading filled (Task 0). Where this part says "per ROTE-FORMAT", substitute the verified mechanism.

---

## Task 14: Package, capture, quality-check and publish the three Plays

**Files:**
- Create: `tools/sync_plays.py`, `plays/session-ledger/{DESCRIPTION.md,PARAMETERS.json,STEPS.md}`, `plays/comped/...`, `plays/wrong-turns/...`
- Test: `tests/test_play_sync.py`

**Interfaces:**
- `tools/sync_plays.py` copies `comped_core/`, `resources/prices.json`, `resources/plans.json`, `resources/fixtures/` into `plays/<slug>/resources/` for each slug and prints one sha256 per Play over the copied tree; `--check` exits 1 if any Play's copy differs from the source tree.

- [ ] **Step 1: Write `tools/sync_plays.py` and its test.**

```python
#!/usr/bin/env python3
"""Sync the single-source core into each Play's resources dir. `--check` verifies byte-identity (used by CI)."""
import hashlib, pathlib, shutil, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYS = ["session-ledger", "comped", "wrong-turns"]
SRC = [("comped_core", ROOT / "comped_core"), ("prices.json", ROOT / "resources" / "prices.json"), ("plans.json", ROOT / "resources" / "plans.json"), ("fixtures", ROOT / "resources" / "fixtures")]

def tree_hash(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    files = sorted(x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts) if p.is_dir() else [p]
    for f in files:
        h.update(str(f.relative_to(p if p.is_dir() else p.parent)).encode()); h.update(f.read_bytes())
    return h.hexdigest()

def main(check=False):
    bad = 0
    for slug in PLAYS:
        dst = ROOT / "plays" / slug / "resources"
        for name, src in SRC:
            target = dst / name
            if check:
                if not target.exists() or tree_hash(target) != tree_hash(src):
                    print(f"DRIFT {slug}/{name}"); bad += 1
                continue
            if target.is_dir(): shutil.rmtree(target)
            elif target.exists(): target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")) if src.is_dir() else shutil.copy2(src, target)
        print(f"{slug}: {tree_hash(dst)[:12]}")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
```

`tests/test_play_sync.py`:
```python
import unittest, subprocess, sys
class PlaySync(unittest.TestCase):
    def test_sync_then_check_is_clean(self):
        subprocess.run([sys.executable, "tools/sync_plays.py"], check=True, capture_output=True)
        r = subprocess.run([sys.executable, "tools/sync_plays.py", "--check"], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stdout)
    def test_play_runs_from_its_own_resources(self):
        r = subprocess.run([sys.executable, "plays/comped/resources/comped_core/cli.py", "ledger", "--claude-dir", "plays/comped/resources/fixtures/claude", "--codex-dir", "/nope", "--pi-dir", "/nope", "--opencode-dir", "/nope", "--out-dir", "out/test-play", "--days-back", "3650", "--now", "2026-09-03T00:00:00Z"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
```
For the second test to pass, `comped_core/cli.py` must be runnable as a script (not only as `-m`): add at the top of `cli.py`:
```python
if __name__ == "__main__" and __package__ is None:  # invoked as a file path from a Play step
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent)); __package__ = "comped_core"
```
and keep the relative imports. The bundled `prices.json`/`plans.json` are found because `prices._bundled()` (Task 2) checks the repo layout first and then the Play layout (`resources/comped_core/../prices.json`), covered by `test_play_layout_resolution`.

- [ ] **Step 2: Write each Play's registry copy.**

`plays/comped/DESCRIPTION.md`: the exact text from SPEC §6.2. `plays/session-ledger/DESCRIPTION.md`: SPEC §6.1. `plays/wrong-turns/DESCRIPTION.md`: SPEC §6.3. Each ends with the privacy paragraph from SPEC §9 verbatim and a "See also" line naming the other two Plays by slug.

`plays/comped/PARAMETERS.json` (mirrors SPEC §6.2; per ROTE-FORMAT, map to the settle-flow prompts):
```json
[
 {"name": "plan", "type": "string", "required": false, "default": "", "label": "Plan", "example": "claude-max-200,chatgpt-plus-20",
  "choices": ["claude-pro-20", "claude-max-100", "claude-max-200", "chatgpt-plus-20", "chatgpt-pro-200", "api", "unknown"], "allowCustom": true,
  "description": "What you pay for, comma-separated. Typed by you; the Play never reads OAuth files to find it. Empty shows list-price total without a multiplier."},
 {"name": "days_back", "type": "integer", "default": 30, "example": 7, "label": "Days back", "description": "Window on each record's own timestamp, not the file date."},
 {"name": "out_dir", "type": "string", "default": "~/comped", "example": "~/comped", "label": "Out dir", "description": "The only place anything is written: report, SVG, PNG when renderable, explain file, baseline for next run's delta."},
 {"name": "claude_dir", "type": "string", "default": "~/.claude/projects", "example": "resources/fixtures/claude", "label": "Claude Code logs", "description": "Point at resources/fixtures/claude to see a full run on synthetic logs."},
 {"name": "codex_dir", "type": "string", "default": "~/.codex/sessions", "example": "resources/fixtures/codex", "label": "Codex logs", "description": "Cumulative counters are differenced per turn."},
 {"name": "pi_dir", "type": "string", "default": "~/.pi/agent/sessions", "example": "~/.pi/agent/sessions", "label": "Pi logs", "description": "Best-effort adapter, labelled in the report."},
 {"name": "opencode_dir", "type": "string", "default": "~/.local/share/opencode/storage", "example": "~/.local/share/opencode/storage", "label": "OpenCode storage", "description": "Best-effort adapter, labelled in the report."},
 {"name": "include_subagents", "type": "string", "default": "true", "choices": ["true", "false"], "label": "Include subagents", "description": "Claude Code subagent transcripts under <session>/subagents/."},
 {"name": "redact", "type": "string", "default": "true", "choices": ["true", "false"], "label": "Redact", "description": "Store human messages as 120-char truncation plus sha256. false keeps full text locally, never on the card."},
 {"name": "repeat_threshold", "type": "integer", "default": 3, "example": 3, "label": "Repeat threshold", "description": "Minimum asks for a repeat offender; also needs 2 sessions and 2 days."},
 {"name": "rates_path", "type": "string", "default": "", "example": "~/my-rates.json", "label": "Rates path", "description": "Override the bundled price table (same JSON shape) for contract pricing."},
 {"name": "handle", "type": "string", "default": "", "example": "priya", "label": "Handle", "description": "Your rote handle, used only to print the /play settle command."},
 {"name": "card_theme", "type": "string", "default": "dark", "choices": ["dark", "light"], "label": "Card theme", "description": "SVG and PNG card theme."}
]
```
`session-ledger` uses the first nine minus `plan`; `wrong-turns` uses `days_back` (default 14), `out_dir`, `claude_dir`, `codex_dir`, `include_subagents`, plus `min_recurrence` (3), `show_snippets` (`true`/`false`), `rules_target` (`both`/`claude`/`agents`).

`plays/comped/STEPS.md` (the commands the capture session runs through rote, one reading per step per the play-shape standard in `docs/research/ROTE-FORMAT.md`; the four reads are independent roots, everything after depends on `merge_ledger`; literals are reified into the parameters above):
```
read_claude   : python3 resources/comped_core/cli.py ledger --only claude-code --claude-dir ~/.claude/projects --days-back 30 --out-dir ~/comped --include-subagents true --redact true
read_codex    : python3 resources/comped_core/cli.py ledger --only codex --codex-dir ~/.codex/sessions --days-back 30 --out-dir ~/comped --redact true
read_pi       : python3 resources/comped_core/cli.py ledger --only pi --pi-dir ~/.pi/agent/sessions --days-back 30 --out-dir ~/comped --redact true
read_opencode : python3 resources/comped_core/cli.py ledger --only opencode --opencode-dir ~/.local/share/opencode/storage --days-back 30 --out-dir ~/comped --redact true
merge_ledger  : python3 resources/comped_core/cli.py merge --out-dir ~/comped                          (depends_on: the four reads)
price_ledger  : python3 resources/comped_core/cli.py price --out-dir ~/comped --plan claude-max-200 --rates-path "" --days-back 30   (depends_on: merge_ledger)
find_repeats  : python3 resources/comped_core/cli.py repeats --out-dir ~/comped --repeat-threshold 3 --handle <handle>            (depends_on: price_ledger)
render_card   : python3 resources/comped_core/cli.py card --out-dir ~/comped --card-theme dark                                      (depends_on: find_repeats)
```
Expected-absence behaviour is built in: a missing `~/.pi` prints `{"ok":true,"warning":"no log directory found for pi..."}` and exits 0, which rote renders as one labelled unknown, and the merge proceeds with the harnesses that were found. Update SPEC §6.2 step names to match: `read_claude, read_codex, read_pi, read_opencode, merge_ledger, price_ledger, find_repeats, render_card` (8 steps). `session-ledger` uses the four reads + `merge_ledger` + `summarize` (6 steps); `wrong-turns` uses the two reads it needs (`read_claude`, `read_codex`) + `merge_ledger` + `classify_turns` + `draft_rules` (5 steps).

`main.ts` header for `comped` (format verified from Play's own tests; the step API below the header comes from `rote-flow-authoring` after install):
```ts
#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: comped
 * description: <plays/comped/DESCRIPTION.md, single line or YAML block scalar>
 * license: MIT
 * metadata:
 *   version: 0.1.0
 *   discoverability:
 *     tags:
 *     - job-agent-cost-review
 *     - job-repeat-ask-detection
 *     - tool-claude-code
 *     - tool-codex
 *     - tool-pi
 *     - tool-opencode
 *     - comped
 *     - tokens
 *     - sessions
 * parameters: <from plays/comped/PARAMETERS.json in the spelling rote-flow-authoring documents>
 * ---
 */
```
Run `scripts/bin/play-tag-hints --request "price my agent session logs, find repeat asks, print the comped card" --play main.ts --json` (from the Play package checkout) and add every suggested tag before `rote play release`.
`session-ledger`: the four `read_*` steps above (roots) → `merge_ledger` → `summarize` (`python3 resources/comped_core/cli.py summary --out-dir ~/comped`). `wrong-turns`: `read_claude`, `read_codex` (roots) → `merge_ledger` → `classify_turns` (`wrongturns --out-dir ~/comped --min-recurrence 3 --show-snippets true`) → `draft_rules` (`rules --out-dir ~/comped --rules-target both`). (`sources` and `summary` are the two small subcommands added at the end of Task 12; `sources` is no longer a step, it stays as a diagnostic.)

- [ ] **Step 3: Capture each Play inside rote (one Claude Code session per Play, in `plays/<slug>/`).**

For `comped`:
1. `/play explore "price my agent session logs and find repeated asks"` (search first; note any hits in ROTE-FORMAT).
2. Run the four STEPS.md commands through rote, exactly as written, on the real logs, with `--plan` set to your real plan.
3. **Keep one wrong turn on purpose**: run `price_ledger` first with `--plan claude-max-20` (an invalid id). The CLI emits a JSON note "unknown plan id"; correct it to `claude-max-200` and rerun. The errored step stays in the workspace as evidence and is filtered at compile time; mention it in the description's last line: "The captured run contains one corrected plan id, kept as proof a human was steering."
4. `rote workspace health` → must be ≥ 80 before settling; if lower, the usual cause is pasted output instead of references; rerun the step that pasted.
5. `/play settle <handle> "comped: price my agent logs, find repeat asks, print the card"`.
6. In the settle flow: paste DESCRIPTION.md, confirm each reified literal maps to the PARAMETERS.json entry (name, type, default, choices), declare `resources/` bundling per ROTE-FORMAT, set license MIT, tags per the registry taxonomy observed on token-tab and audit-play, declare writes under `out_dir` if `declaredWrites` covers files.
7. Choose **Skip** for now (not Community). Inspect: `rote play inspect <local-ref> --json` and diff its `parameters`, `requirements.localTools` (must be exactly `["python3"]`), `effects`, `steps.names` against SPEC §6.2.

Repeat for `session-ledger` (wrong turn: run with `--codex-dir ~/.codex/session` singular, get `found: false`, correct it) and `wrong-turns` (wrong turn: `--rules-target agent`, corrected to `agents`).

- [ ] **Step 4: Quality gate with the registry's own scorer.**

```bash
rote play run https://play.modiqo.ai/himanshu-jha/play-quality-doctor play=<local-ref-or-path> owner=<handle>
```
Fix every "fixable" signal it names (fixtures key, output schema, tags, license), re-settle as a patch version, rerun until it reports none. Paste the final output into `docs/research/ROTE-FORMAT.md`.

- [ ] **Step 5: Clean-machine run.**

On a second machine or a fresh macOS user account with only python3: install rote, `rote play run <local-ref> claude_dir=resources/fixtures/claude codex_dir=resources/fixtures/codex plan=claude-max-200 --yes`, time it (< 10 s), confirm the card prints and `~/comped/` holds report, SVG, explain, baseline. Then run against that machine's real logs. Record both in ROTE-FORMAT.

- [ ] **Step 6: Publish to Community, in order, same day: `session-ledger`, then `comped`. Next day: `wrong-turns`.**

Per ROTE-FORMAT: `rote play release` then `rote registry play push <path> <handle>/<slug>` (or the settle flow's Community choice). Immediately verify the public manifest:
```bash
curl -s https://play.modiqo.ai/<handle>/comped.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['version'], d['requirements'], d['effects'], d['steps'], d.get('license'))"
```
Expected: `localTools == ['python3']`, `steps.count == 4`, names `build_ledger, price_ledger, find_repeats, render_card`, license MIT. Append the first row to `docs/adoption-log.md`.

- [ ] **Step 7: Commit.** `git add -A && git commit -m "feat(plays): packaged, captured, quality-checked and published session-ledger, comped, wrong-turns"`

---

## Task 15: Public repository

**Files:**
- Create: `README.md` (replace the placeholder), `VISION.md`, `.github/workflows/ci.yml`, `docs/screenshots/comped-card.png`

- [ ] **Step 1: CI.**

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    strategy: { matrix: { os: [ubuntu-latest, macos-latest], python: ["3.9", "3.12"] } }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}" }
      - run: python -m unittest discover -s tests -v
      - run: python tools/sync_plays.py && python tools/sync_plays.py --check
```

- [ ] **Step 2: README.** Structure from the hackathon skill's template: one-liner, card screenshot, What it does, How it works (four steps), the three Plays with run commands, Built with (rote, python3 stdlib, LiteLLM price snapshot), Methodology summary with a link to SPEC §7, Privacy paragraph verbatim, Getting started (`rote play run ... claude_dir=resources/fixtures/claude`), Known limitations (Pi/OpenCode fixture-verified; PNG needs a renderer; gpt-5.5-codex unpriced until upstream adds it), Links (Play URIs, VISION.md).

- [ ] **Step 3: VISION.md** from the hackathon skill's template, content from SPEC §13: month 1 more adapters and session-ledger as shared dependency; month 3 opt-in aggregate leaderboard (the earlier product draft); month 6 rules feeding Play preconditions; revenue outside the Plays; what the hackathon validated; the ask (registry stats API for authors, feedback on composition).

- [ ] **Step 4: Screenshot** the terminal card from a real run (redact nothing; it contains no text from prompts except the repeat labels, which you choose to show or replace with fixture output).

- [ ] **Step 5: Make the repo public** (`gh repo create comped --public --source . --push`, only after `git log -p | grep -i -E "sk-|ghp_|/Users/rajkaria"` returns nothing except documented fixture-privacy patterns). Commit.

---

## Task 16: Distribution, adoption log, judge loop

- [ ] **Step 1: Daily, from publish day to close (07 Sep 20:00 London):** run `playoffs-standings author=<handle>` and `comped`; append the row to `docs/adoption-log.md`; post the day's card on X and LinkedIn tagging Modiqo (the Apple Watch entry); post the run command in the Modiqo Discord sharing channel with one sentence and the fixture hint; answer every question within the hour; ask five participants to run it and post theirs.

- [ ] **Step 2: Judge loop, twice.** Run the seven-persona panel from SPEC §15 against the live Play pages, the README and a fresh clean-machine run. Score each 1–10 with three concrete issues. Fix every issue that is fixable in a patch release; republish as a patch version (the registry treats a bump as UPDATED, not new). Stop when the weighted score is ≥ 9.5 or the remaining issues are outside our control (adoption).

- [ ] **Step 3: Final checks before close.** Public manifest for each Play resolves; `rote play run` from a clean machine works; README card screenshot matches the current version; `docs/adoption-log.md` complete; final social post with the week's delta.

- [ ] **Step 4: Save context.** Update `CLAUDE.md` at the repo root with state, decisions and next steps, per the user's global rules.
