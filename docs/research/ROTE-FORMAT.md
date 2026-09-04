# rote Play format — verified 2026-09-03 from the Play package source (v0.4.87), rote NOT yet installed

Status legend: **VERIFIED** = read from modiqo's shipped source or a live registry artefact. **PENDING** = needs the rote binary (`rote how`, `rote guidance`, `rote-flow-authoring` skill) and is filled in after install.

## Handle (VERIFIED 2026-09-04)
`rajkaria` — reserved with `rote profile set-handle rajkaria` (one-time, immutable). Account `rajkaria67@gmail.com`, rote **0.79.0** at `/Users/rajkaria/.local/bin/rote`. Public namespace: `play.modiqo.ai/rajkaria/{session-ledger,comped,wrong-turns}`.
Note: `rote whoami` reports the signed-in identity; the handle is separate and is set by `rote profile set-handle`, not by the OAuth flow. `rote profile show` confirms it.

## Plan tier for demos and the card (VERIFIED with the user 2026-09-04)
Claude Max 20x → plan id `claude-max-200` in `resources/plans.json`. No ChatGPT/Codex subscription stated, so demo runs use `plan=claude-max-200` alone unless the user adds one.

## Install facts (VERIFIED)
- `https://getrote.dev/playoffs/install.sh` is a 385-byte selector pinned to Play release `v0.4.87`; it fetches `https://raw.githubusercontent.com/modiqo/play/v0.4.87/install.sh`, which downloads the `modiqo/play` archive and runs `scripts/bin/play-bootstrap install`.
- Requirements: macOS/Linux, python3 ≥ 3.10, `uv`. Both present here (python 3.10.2, uv 0.11.6).
- The bootstrap plan for this machine (dry run, JSON, `--harness claude`): install Play 0.4.87 into Claude Code (Rote skills, hooks, launchers, public Play cache), install Rote via its official remote installer `https://getrote.dev/install` (binary to `~/.local/bin/rote`, state in `~/.rote`, sha256-verified download of `modiqo/rote-releases` asset `rote-macos-aarch64.tar.gz`, latest **v0.79.0**, published 2026-09-03), Tulving optional and skipped. It snapshots prior state and rolls back on failed verification.
- Guided setup needs a TTY. Unattended form: `PLAY_INSTALL_YES=1 PLAY_APPROVE_REMOTE_INSTALLER=1`. The unattended form was **blocked by the Claude Code permission classifier** in this session; the user runs the interactive installer in a terminal (see part-0-gate.md Step 1).
- Sign-in is a browser OAuth flow (Google or GitHub) triggered on first `/play`; the agent never handles it.

## Archive layout (PENDING for the exact archive; VERIFIED for the entry file)
- A Play is a rote **Flow**: a directory whose entry file is `main.ts` (TypeScript, run by rote's bundled Deno). `~/.rote/flows/<name>/main.ts` for local flows; `~/.rote/flows/<owner>/<name>/main.ts` for pulled ones. Source: `scripts/lib/play/intercept.py`.
- `deps.toml` sits beside it and declares external tools with **per-step `timeout_ms`**; `rote deps check` validates executables. Source: `actions.yaml` author_release and explore policies.
- Registry manifests show `distribution.mediaType: application/vnd.modiqo.rote-flow`, 13–68 KB, so the archive is the flow directory (main.ts + deps.toml + bundled resources). Token-tab bundles demo logs and a rates table; play-quality-doctor defaults a parameter to `resources/samples/needs-work`, so a `resources/` directory travels with the archive.
- Whether Python step scripts must live under `resources/` or anywhere in the directory: PENDING.

## Entry file header (VERIFIED, from `tests/foundation/test_tag_hints.py` and `test_intercept.py`)

```ts
#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: comped
 * description: <registry description; the first document of this YAML is the card>
 * metadata:
 *   version: 0.1.0
 *   discoverability:
 *     tags:
 *     - job-agent-cost-review
 *     - tool-claude-code
 *     - tool-codex
 * parameters: []
 * ---
 */
export default async function main() {}
```
- The shebang must match `^#!.*\brote play run\b` or Play's local index ignores the flow.
- Play reads the first YAML document between `@rote-frontmatter` and `*/`; keys seen: `name`, `version` (either top-level or under `metadata`), `description`, `metadata.discoverability.tags`, `parameters`.
- Tag convention observed in modiqo's own fixture: `job-<outcome>` and `tool-<provider>`. Before release run `scripts/bin/play-tag-hints --request "<originating request>" --play main.ts --json` and add every suggested tag so the Play is discoverable by the request that created it.
- Parameter schema in the manifest: `name`, `type` (string|integer), `default`, `required`, `description`, `example`, `input.label`, `input.choices`, `input.allowCustom`. The exact frontmatter spelling of `input.*`: PENDING (copy from the token-tab archive after `rote play inspect ... --json` and a local pull).

## Step definition (VERIFIED as policy, PENDING as syntax)
From `actions.yaml` `prepare_candidate` and `author_release` (the "play-shape standard"):
- **One reading = one step.** A step that fetches five things is a monolith and fails review. For Comped: one step per harness (`read_claude`, `read_codex`, `read_pi`, `read_opencode`), then `merge_ledger`, `price_ledger`, `find_repeats`, `render_card`.
- **Author-named steps** (`probe_harnesses`, never `python3_2`).
- **Independent steps are roots** so the runner parallelises them; `depends_on` declares ordering; `@step{...}` references declare every consumed value, piped through `join` when needed, with a self-sufficient fallback in the script.
- **Failure contract**: expected absence prints `{"ok":true,"warning":"..."}` and exits 0 → rendered as one labelled unknown. Real faults write stderr and exit non-zero. Steps have no TTY, so interactive subcommands carry `--yes`.
- **`--resume` must work** after an injected hard fault; a degraded-source run must complete with a labelled unknown. Both are tested before release.
- **Presentation**: a classified presentation with a per-step stage ledger, never an information dump. The run output prints "layer lines" showing the DAG; verify the DAG is real (multi-source work rendering as one step = standards skipped).
- Steps are shell invocations recorded during captured exploration (`rote proc` for CLIs, `rote query @N` to consume upstream responses). Exact TypeScript step API (`out.result()`, `@step{}` syntax): PENDING from `rote-flow-authoring`.

Consequence for `comped_core/cli.py` (already applied to the plan): `ledger` accepts `--only <harness>` and writes `ledger-<harness>.jsonl`; a `merge` subcommand joins the partial ledgers into `ledger.jsonl`; every subcommand prints `{"ok":true,"warning":...}` with exit 0 for expected absence (missing directory, no records) and exits non-zero only on real faults.

## Parameter passing (PENDING)
Literals in the captured commands are reified into typed parameters at crystallisation ("hardcoded values become typed parameters; the agent decides which literals are inputs"). How a parameter reaches the shell string (template vs env var): PENDING.

## Resources (PENDING)
`resources/` travels with the archive (evidence above). How a step addresses it (relative path from the flow directory vs a rote-provided variable): PENDING.

## Fixtures, tags, license, output schema keys (PARTIAL)
- Tags: `metadata.discoverability.tags` (VERIFIED).
- License: manifests carry a top-level `license` (play-quality-doctor: MIT) (VERIFIED in manifest; frontmatter key PENDING).
- Fixtures key and output-schema key read by the registry quality rubric: PENDING; play-quality-doctor's description says two rubric signals are lost "by declaring the right thing under the wrong key". Run it against our Play before publishing.

## Composition (PENDING)
No manifest shows a Play depending on another Play. `rote-releases` README says flows compose. Decision stands: bundle byte-identical copies via `tools/sync_plays.py`; revisit if `rote-flow-authoring` documents flow imports.

## declaredWrites (PARTIAL)
Token-tab writes `~/token-tab.md` and declares `declaredWrites: []`, so `declaredWrites` appears to cover services, not local files. We still state every local write in the description and report.

## Settle and publish flow (VERIFIED from `references/publish/lifecycle.md`, `prompts.yaml`, `actions.yaml`)
1. `/play explore <outcome>` searches first; on no match it creates a capture handle `cap_xxxxxxxxxxxxxxxx` and a Rote workspace **before** the work. Work done outside the capture can never be settled.
2. Explore "in the shape of the play it may become": one rote call per reading, stages named as you go, `rote query @N` before values move on, a clean happy-path rerun before export. Keep the wrong turn: errored steps stay in the workspace as evidence and are filtered at crystallisation.
3. `/play settle <capture-handle> <one-line summary>`. Play judges worth-saving from trace evidence: ≥ 2 effect-bearing steps, ≥ 1 input that varies on reuse, a stable output shape. Setup/auth/smoke steps count zero.
4. Prompt `private_public_or_skip`: **Team** (private org URI) / **Community** (public; then verifies the exact public Play and produces paste-ready X ≤ 280 chars and LinkedIn copy) / **Skip**.
5. `author_release` is delegated to the `rote-flow-authoring` skill: author, test, lint, `rote play release`; must stop before any push. Then `play-birth capture` (owner-private birth certificate under `~/.play/births/`), then `rote-registry` push, then `play-birth bind`, then `rote play inspect <owner/name> --json` readback.
6. Public gates: credential-contract check, then a **smoke run** `rote play run <registry-returned versioned URI> <verified params> --yes` from a fresh directory under `/tmp`. So the published Play must be fully self-contained; nothing may depend on the repo checkout or the author's home directory beyond the declared log directories.
7. Birth certificate is rendered once; Play prints the URI and social copy; it never posts.

## Publishing commands (VERIFIED names, PENDING exact flags)
`rote play release`, `rote registry flow push <path> <slug>` (README of rote-releases), `rote play inspect <owner/name>[@version] --json`, `rote play run <uri> name=value --yes`, `rote registry whoami --verbose`, `rote registry org list --json`.

## Decisions taken for Part 6
- Steps are one-per-reading shell commands invoking `python3 resources/comped_core/cli.py <sub> --only <harness>`; the DAG has four parallel root reads, then merge → price → repeats → card.
- `comped_core` is referenced as `resources/comped_core/` inside the flow directory (path form PENDING).
- Composition: no → bundle copies.
- Every CLI subcommand honours the failure contract (`{"ok":true,"warning":...}` exit 0 for expected absence; stderr + non-zero for real faults).
- The originating request typed at `/play explore` must contain the outcome words we want as tags: "price my agent session logs, find repeat asks, print the comped card".

## Still to do after the user installs rote (Task 0 Steps 2–7)
`rote --version`; `/play what's new`; claim handle; run Hello + playoffs-standings; practice Play (do not publish); `rote how`, `rote guidance`, read `~/.claude/skills/rote-flow-authoring/SKILL.md` (or wherever `rote install skill` staged it) and pull token-tab to read a real archive; fill every PENDING above; run play-quality-doctor on the practice Play; post "warmed up" in Discord.
