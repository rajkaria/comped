# rote Play format — verified 2026-09-04 against rote 0.79.0

Status legend: **VERIFIED** = read from the installed CLI, from a live registry archive, or proven by
running it on this machine. **OPEN** = still unanswered.

Everything below was checked against rote 0.79.0 plus two real registry archives pulled and read on
2026-09-04: `modiqo/hello@0.2.2` and `dotisacat/playoffs-standings@0.2.5`, whose entry files land at
`~/.rote/workspaces/dag-<name>-<hash>/main.ts` when the Play runs.

## Handle (VERIFIED)
`rajkaria` — reserved with `rote profile set-handle rajkaria` (one-time, immutable). rote **0.79.0**
at `~/.local/bin/rote`. Public namespace: `play.modiqo.ai/rajkaria/{session-ledger,comped,wrong-turns}`.

The plan expected the handle to be claimed during the sign-in flow. It is not: `rote whoami` reports
the signed-in identity and prints `rote profile set-handle <handle>` as the next action. The two are
separate; `rote profile show` confirms the handle.

## Plan tier for demos and the card (VERIFIED with the user)
Claude Max 20x → plan id `claude-max-200` in `resources/plans.json`. No ChatGPT/Codex subscription,
so demo runs pass `plan=claude-max-200` alone.

## Archive layout (VERIFIED)
A Play is a package directory. Its root admits **only** these entries — anything else is refused by
`rote play validate` as "unsupported package file", with the fix "move it into `lib/`, `vendor/`, or
`resources/`":

```
<play>/
├── main.ts       entry file: shebang + @rote-frontmatter JSDoc block, then the presentation body
├── deps.toml     declared external tools
├── resources/    process payloads: our comped_core/, prices.json, plans.json, fixtures/, presentation-fixtures/
├── lib/          presentation modules (unused here)
└── vendor/       vendored modules (unused here)
```

That rule is why this repo keeps each Play's registry copy under `docs/plays/<slug>/` and generates
`main.ts` from it with `tools/build_plays.py`.

## Entry file header (VERIFIED)

```ts
#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: comped
 * description: '<the registry copy; single-quoted YAML, doubled apostrophes>'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/comped
 * metadata:
 *   version: '0.1.0'
 *   rote_version: '0.79.0'
 *   status: released
 *   kind: atomic
 *   flow_type: parallel
 *   execution_model: steps_with_presentation
 *   requires_endpoints: []
 *   requires_sessions: false
 *   license: MIT
 *   discoverability:
 *     tags: [...]
 * tags: [...]
 * discoverability:
 *   tags: [...]
 * output:
 *   schema: {...}
 * presentation_fixtures:
 *   <step>: resources/presentation-fixtures/<step>/fixture.yaml
 * parameters:
 * - name: out_dir
 *   param_type: string
 *   required: false
 *   default: '~/comped'
 *   description: '...'
 *   example: '~/comped'
 * steps:
 *   read_claude:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv: [...]
 * ---
 */
```

`execution_model` accepts exactly `legacy`, `steps_only` or `steps_with_presentation`; anything else
fails validation by name. Tags are the one duplicated field: the guidance says they belong only in
`metadata.discoverability.tags`, but the **quality rubric reads top-level `tags` and
`discoverability` too**, and scores `frontmatter_completeness` 0.50 without them — 0.88 overall.
Carrying all three copies, as the live archives do, is what makes the score 1.00.

## Step definition (VERIFIED)
Steps are frontmatter YAML, run by a DAG runner. A local command is:

```yaml
 *   price_ledger:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - merge_ledger
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'price'
 *     - '--out-dir'
 *     - '$out_dir'
```

`depends_on` forms execution layers; a layer is a barrier, and siblings in one layer run together.
Our four `read_*` steps are roots with no `depends_on`, so rote ran them four-wide (observed in the
runner report). Default step budget is 30s; `timeout_ms` raises it.

**Process exit contract** (verbatim from `rote grammar steps`): child exit status is the DAG failure
signal, stdout is data, and *"exit-zero degradation only for expected optional absence, represented
explicitly as success such as `{"ok":true,"available":false,"warning":"..."}`"*. That is precisely the
contract `comped_core/cli.py` already implements — a missing harness directory prints
`{"ok":true,...,"warning":...}` and exits 0.

## Parameter passing (VERIFIED)
`$name` resolves from the declared parameters in every step string field, including each argv
element. A field that is exactly `$name` keeps the value's JSON type; embedded `$name` substitutes at
identifier boundaries. `$item`/`$item_index` are reserved for `for_each`. Booleans reach a step as
the strings `true`/`false`, which is why the CLI parses them with `_bool()`.

## Resources (VERIFIED)
`@resource{<relpath>}` in argv resolves at run time to `<package root>/resources/<relpath>`. It is
read-only, legal in `argv[]` and `stdin.file`, refused in capture paths (a step never writes into its
own package). Parameters are **not** substituted inside the braces, so the path stays literal and
lint can enumerate it. Our steps therefore call `python3 @resource{comped_core/cli.py} <sub> ...`,
and `comped_core/prices.py::_bundled()` finds `prices.json` beside the package dir.

Observed: a run's working directory is the package root, so `claude_dir=resources/fixtures/claude`
resolves for the demo run without any absolute path.

## Presentation plane and fixtures (VERIFIED)
With `steps_with_presentation`, the TypeScript body is deprivileged: it imports only
`__ROTE_PRESENTATION_SDK__`, reads recorded observations via `loadPresentationContext()` and
`ctx.requireAvailable(stepName("literal"))`, and owns no effects. Two hard rules found by lint:

- `stepName()` must take a **literal** string. A helper that takes the name as a variable fails
  `PRESENTATION_DYNAMIC_STEP_REF`, so the generated bodies build their step arrays from literals.
- `rote play lint` **replays the body** in human, summary and json modes. Without fixtures it replays
  against absent observations and every mode fails. The fix is `presentation_fixtures:` mapping each
  step to a manifest under `resources/presentation-fixtures/<step>/fixture.yaml`:

```yaml
schema_version: 1
kind: process.exec
status:
  exit:
    kind: code
    code: 0
  duration_ms: 894
  timeout_ms: 60000
stdout: resources/presentation-fixtures/render_card/stdout.txt
stderr: resources/presentation-fixtures/render_card/stderr.txt
```

Real observations come from a run's `.rote/presentation/<run-id>/input.json` (keys: `flow`, `params`,
`run`, `steps`; each step at `steps.<name>.outcome.output.body`). `tools/build_fixtures.py` captures
them. Each fixture resource is capped at 1 MiB.

`FlowOutput` requires at least three calls across `out.human`, `out.summary` and `out.result`.

## Tags, license and output schema (VERIFIED)
Tags follow the registry taxonomy `domain-*`, `job-*`, `audience-*`, `effect-*`, `tool-*`. `license`
sits under `metadata`. `output.schema` is a JSON-schema-shaped object; the rubric's `output_format`
signal scores it 1.00 when present.

## Composition (VERIFIED: not needed, and not used)
`rote play` has no dependency mechanism between Plays; `rote run <script>` is described as "run play
with composition metadata", and `kind: composite` exists, but nothing in the CLI lets one published
Play declare another as a dependency. The decision stands: each Play bundles a byte-identical copy of
`comped_core`, enforced by `tools/sync_plays.py --check`.

## declaredWrites (VERIFIED)
The consent screen prints `Writes  none declared` for hello and playoffs-standings, both of which do
write files under their run workspace. Writes appear to be declared for *services*, not local paths;
nothing in validation demanded a declaration for our `out_dir` writes. We state the write set in the
description and list every written path in the report instead.

## Quality gates, measured (VERIFIED)
| Gate | Result for all three Plays |
|---|---|
| `rote play validate <path>` | OK, no errors, no warnings |
| `rote play lint <path>` | passed, zero findings (static + runtime replay in all three output modes) |
| `rote play score <path>` | 1.00 (rubric v1.1.0), full marks on all seven signals |
| `himanshu-jha/play-quality-doctor` | "SCORE: 1.00 (pass) — Full marks. Nothing here needs changing." |
| End-to-end run on bundled fixtures | comped 8/8 steps in 1.8s, session-ledger 6/6, wrong-turns 5/5 |

## Machine facts worth knowing (VERIFIED)
- This machine's `python3` has **no root certificates**: every HTTPS call from a Play's python step
  fails with `CERTIFICATE_VERIFY_FAILED`. `modiqo/hello` degraded five readings to labelled unknowns
  because of it. Our Plays make no network calls, so they are unaffected — and `tools/build_prices.py`
  (a developer tool, never a Play step) falls back to `/etc/ssl/cert.pem`.
- `rote play run <registry-uri>` needs `--yes` when stdin is not a TTY; a **local** path run has no
  consent gate and refuses `--yes`.
- `rote play lint` writes `.rote-flow-lint.json` into the package root; it is gitignored.
- `rote play template create` / `frontmatter` both require `--adapter` and refuse `none`, so an
  adapterless play has no generator — ours is hand-authored via `tools/build_plays.py`.

## Settle and publish flow (VERIFIED from the Play package source; not yet exercised)
1. `/play explore <outcome>` searches first; on no match it opens a capture handle and a workspace
   **before** the work. Work done outside the capture cannot be settled.
2. `/play settle <capture-handle> <one-line summary>`; Play judges worth-saving from trace evidence:
   ≥ 2 effect-bearing steps, ≥ 1 input that varies on reuse, a stable output shape.
3. Prompt `private_public_or_skip`: Team (private org URI) / Community (public, with paste-ready X
   and LinkedIn copy) / Skip.
4. `rote play release <name>` marks draft → released and reruns lint as a gate.
5. Registry push, then `rote play inspect <owner/name> --json` readback, then a smoke run
   `rote play run <versioned URI> <params> --yes` from a fresh `/tmp` directory. The published Play
   must therefore be self-contained: nothing may depend on this checkout or the author's home
   directory beyond the declared log directories.

## OPEN
- The exact registry push command and its flags (`rote play release` is confirmed; the push step is
  delegated to the `rote-registry` skill inside `/play settle`, which has not been run).
- Whether publishing through `/play settle` Community differs in any way from a direct release +
  push for a Play that was authored outside a capture workspace.
- The verbatim `/play settle` prompts, which need an interactive harness session.

## Decisions taken for Part 6
- Steps are one reading per step: four parallel `read_*` roots → `merge_ledger` → the analysis chain.
- `comped_core` is addressed as `@resource{comped_core/cli.py}`; `tools/sync_plays.py` keeps each
  Play's copy byte-identical to the repo's.
- Composition: no. Bundle copies.
- `execution_model: steps_with_presentation`, with a generated body that renders the last step's
  human block and re-emits its JSON, plus one line per harness that reported an expected absence.
- Fixtures are captured from real runs, never hand-written.
