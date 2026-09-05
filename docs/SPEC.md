# Comped — Rote Playoffs build spec

*v1.0 · 2026-09-03 · status: approved for build*
*Companion documents: [research/LANDSCAPE.md](research/LANDSCAPE.md) (facts), [superpowers/plans/2026-09-03-comped-plays.md](superpowers/plans/2026-09-03-comped-plays.md) (implementation plan).*

---

## 0. One-liner

**Comped reads the agent session logs already on your disk and prints one card: what your week of Claude Code and Codex would have cost at API list price, the multiplier against the plan you actually pay for, the jobs you keep asking your agent to redo, and what each one would cost as a Play.**

Headline the Play exists to produce, on a stranger's machine, in under ten seconds, with no credentials:

> `$8,570 comped · 43× · Claude Max 20x · last 30 days`
> `3 repeat offenders · $412 spent re-solving them · capture: /play settle ...`

---

## 1. The problem, as the judges framed it

The hackathon brief asks every participant one question: *which workflow have you done three times this week and resented?* Nobody can answer it from memory. The answer is already written down, in `~/.claude/projects/**/*.jsonl` and `~/.codex/sessions/**/*.jsonl`, in a format no human reads. Every participant is generating more of it every hour of the competition.

Comped reads it. It is the status check that takes too many clicks, applied to the one dataset every judge, every participant and Modiqo itself cares about.

## 2. Why this wins first, in the judges' own three criteria

| Criterion | How Comped scores it | Evidence the design rests on |
|---|---|---|
| **It runs** | Zero credentials, zero network, python3 stdlib only, read-only, sub-10s on 1 GB of logs. Bundled synthetic fixtures let a stranger see a full run before touching their own logs. Every source degrades to a labelled unknown instead of failing. | Hello, the most downloaded Play (167), is zero-credential. Audit Play's description boasts "no network call". Token-tab bundles demo logs. |
| **A stranger understands and trusts it** | Output is one card with one number. The description states what is read, what is written, what is never read (OAuth files), what is estimated and how. Every headline figure cites its formula and price-table version. `explain` prints the arithmetic line by line. | Play-quality-doctor and audit-play, the two most rigorous participant descriptions, both win trust by naming their evidence. |
| **People adopt it** | The card is the social post participants need for the Apple Watch prize. The repeat-offender list tells participants what Play to build next, so it manufactures more Plays. Both give a participant a reason to run it today and again tomorrow. | Hackathon-week meta-Plays lead the participant table (Submission Readiness 19, Standings 13). Token-only Plays do not spread (token-tab 6, session-digest 3): the card and the repeats are the difference. |
| **Sponsor thesis** | Modiqo's homepage sells a 98% token reduction on repeat runs. Comped measures repeats and prices the reduction. Agent-work-daily-close proves Modiqo sanctions reading session logs. | modiqo.ai headline; agent-work-daily-close@1.0.1 |

## 3. Competitive positioning

What 80% of entries are: git hygiene, CI diagnosis, secret scanning, submission-readiness audits. Three token Plays exist and are thin (see LANDSCAPE.md §Direct competitors). None computes a plan multiplier, none detects repeats across sessions, none mines corrections, none renders a card, none covers Claude Code + Codex + Pi with subagent transcripts and dedup done right.

Where we must be at least as good as the incumbents, because judges will compare:
- token-tab: honest "list price is not a bill" language, bundled price table with source and as-of date, bundled demo logs, four waste checks. We match every one and add the multiplier.
- audit-play: "every headline number cites its field", DAG steps, no network. We match.
- playoffs-standings: compares against your last run and shows deltas. We do the same for the card (delta since last run).

## 4. Target user persona

**Priya**, a participant in this hackathon. Runs Claude Code on Max 20x and Codex on ChatGPT Plus. Has built two Plays, needs a third idea, needs three social posts for the Apple Watch, and has no idea what her week of agent use would have cost on the API. She runs `rote play run .../comped` -- no parameters, because the model ids in her logs already say she is on Claude and on Codex -- gets the card with a multiplier against every tier either vendor sells, posts it, reads her three repeat offenders, and runs `/play settle` on the first one. Tomorrow she runs it again to see the delta.

**Chetan**, judging. Opens the Play page. Reads a description that says exactly what is read and what is never read. Runs it against the bundled fixtures. Sees a multiplier, a repeat list, and a Rote dividend quoted at his own 98% figure and at a conservative 80%. Recognises his company's thesis measured on a participant's machine.

## 5. The Play family

Three published Plays, one shared core. Prizes are per Play; each is independently useful; each points at the others in its description.

| # | Play slug | Purpose | Publish day |
|---|---|---|---|
| 1 | `session-ledger` | The primitive. Normalizes every local agent log (Claude Code incl. subagents, Codex, Pi, OpenCode) into one deduplicated JSONL of usage records, human messages and tool events. No pricing, no opinions. Other Play authors can build on it. | Day 1 |
| 2 | `comped` | The flagship. Ledger → priced → card + repeat offenders + Rote dividend + SVG/PNG card + share text + delta since last run. | Day 1 |
| 3 | `wrong-turns` | Ledger → your agent's most repeated mistakes this week (tool errors, corrections, reverts), their recovery cost, and drafted CLAUDE.md / AGENTS.md rules. | Day 2 |

**Composition decision gate.** If rote lets a Play depend on another Play (LANDSCAPE.md unknown #3), `comped` and `wrong-turns` declare `session-ledger` as a dependency and every run of theirs pulls it (downloads for the primitive). If not, each Play bundles an identical copy of `comped_core/` under `resources/`, and a CI test asserts the three copies are byte-identical. Either way there is one codebase.

## 6. Contracts

All three Plays share: `requirements.localTools = ["python3"]`, no adapters, no browser, no credentials, `license: MIT`, read-only on logs, writes only under `out_dir`. The core makes no network calls; `comped` alone has one extra step, `post_score`, that posts the score to the gotcomped.com leaderboard (§17) and can be switched off. Minimum python 3.9. Every step is a shell command invoking `python3 resources/comped_core/cli.py <subcommand>`, so rote records literals it can reify into parameters and each step's stdout is a JSON object the next step references. Plays are rote Flows (`main.ts` with an `@rote-frontmatter` YAML header, `deps.toml` with per-step `timeout_ms`, bundled `resources/`); the verified format facts and remaining unknowns are in [research/ROTE-FORMAT.md](research/ROTE-FORMAT.md).

### 6.1 `session-ledger`

Description (registry copy, final):

> Every agent harness on this machine keeps a transcript, each in its own shape, and none of them agree on what a token record looks like. Claude Code writes one line per content block so four in ten usage lines are duplicates of the same API call, and buries subagent spend in a subdirectory. Codex writes cumulative counters that have to be differenced. Pi and OpenCode have their own layouts. This reads all of them and emits one deduplicated ledger: usage records with uncached input, cache write, cache read, output and reasoning tokens per model per turn; the human messages that started each turn; and every tool call with whether it errored. Nothing is priced, nothing is judged, and message text is truncated and hashed unless you ask for it. It is the file the other session Plays should be reading instead of each re-parsing the logs, and it says which sources it found, which it could not read, and why. Read-only, no credentials, no network. Writes one JSONL and one summary JSON under the folder you choose. Point it at resources/fixtures to see a full run on synthetic logs first.

Parameters:

| name | type | default | notes |
|---|---|---|---|
| `days_back` | integer | 30 | filter on each record's own timestamp |
| `out_dir` | string | `~/comped` | created if missing |
| `claude_dir` | string | `~/.claude/projects` | set to `resources/fixtures/claude` for demo |
| `codex_dir` | string | `~/.codex/sessions` | set to `resources/fixtures/codex` for demo |
| `pi_dir` | string | `~/.pi/agent/sessions` | best-effort adapter, labelled |
| `opencode_dir` | string | `~/.local/share/opencode/storage` | best-effort adapter, labelled |
| `include_subagents` | string (`true`/`false`) | `true` | Claude subagent transcripts |
| `redact` | string (`true`/`false`) | `true` | human message text stored as 120-char truncation + sha256; `false` stores full text locally |

Steps (rote's play-shape standard requires one reading per step; the four reads are parallel roots): `read_claude`, `read_codex`, `read_pi`, `read_opencode` → `merge_ledger` → `summarize`. Outputs: `out_dir/ledger-<harness>.jsonl` per read, `out_dir/ledger.jsonl`, `out_dir/ledger-summary.json`, JSON on stdout. A missing harness directory is an expected absence: the step prints `{"ok":true,"warning":...}`, exits 0, and renders as one labelled unknown.

### 6.2 `comped`

Description (registry copy, final):

> Every coding session on this machine wrote down exactly what it consumed, and none of it is readable by hand. This reads all of it: Claude Code including the subagent transcripts in subdirectories, where four in ten usage lines are streaming duplicates that must be collapsed before pricing, Codex, whose counters are cumulative and need differencing, and Pi. You get one card: the API list-price equivalent of the last N days per model, the multiplier against the plan you actually pay for, your cache-read share, and how all of it moved since your last run. Under it, the jobs you have asked your agent for three or more times, each with its repeat cost and the exact play settle command to capture it. Then what those repeats would have cost as Plays, at Modiqo's stated 98% and at a conservative 80%. Prices come from a bundled table that names its source and as-of date; a model the table does not know is reported as tokens and never priced by guess. You do not tell it what you run: the model ids in your own logs name the providers behind them -- Claude, GPT/Codex, Kimi, GLM, DeepSeek, Gemini, Grok, Qwen -- and every subscription those providers sell is priced on the card at once, the least flattering one marked as assumed, so you read your row instead of typing it. It refuses to open your OAuth files to find the tier, and the card says plainly that list price is not a bill. Read-only and no credentials. Writes a Markdown report, an SVG card, a PNG when the machine can render one, and a small baseline for next run's delta, all under the folder you choose. Then, unless you say leaderboard=false, it posts the score to the gotcomped.com leaderboard and prints your rank: that is the one thing this Play ever sends, and the exact payload is saved next to the card so you can read it. Point claude_dir at resources/fixtures/claude to see a full run on synthetic logs before you run it on your own.

Parameters (superset of session-ledger's, plus):

| name | type | default | notes |
|---|---|---|---|
| `plan` | string | `auto` | `auto` (the default, and empty means the same) infers the providers from the model ids in the ledger and prices every tier they sell, assuming the most expensive one that fits -- the smallest multiplier that is honest -- and showing the rest as a ladder. Override with comma-separated ids from `plans.json`: `claude-pro-20`, `claude-max-100`, `claude-max-200`, `chatgpt-plus-20`, `chatgpt-pro-200`, `api`, `unknown`; or `usd:<amount>` for a subscription the table does not carry. With `unknown`/`api`, or when no detected provider sells one, the card shows the list-price total and no multiplier. |
| `repeat_threshold` | integer | 3 | minimum cluster size |
| `rates_path` | string | `""` | override bundled `prices.json` |
| `handle` | string | `""` | your rote handle, used only to print the `/play settle <handle>` command |
| `card_theme` | string | `dark` | `dark` / `light` |

Steps: `read_claude`, `read_codex`, `read_pi`, `read_opencode` (parallel roots) → `merge_ledger` → `price_ledger` → `find_repeats` → `render_card`. Outputs: `out_dir/comped-report.md`, `out_dir/comped-card.svg`, `out_dir/comped-card.png` (opportunistic), `out_dir/comped-baseline.json`, `out_dir/comped-explain.txt`, terminal card on stdout of the last step plus JSON.

### 6.3 `wrong-turns`

Description (registry copy, final):

> Rote asks you to keep one wrong turn in every Play as proof a human was steering. Your logs already hold hundreds. This reads Claude Code and Codex transcripts and finds three kinds: tool calls that returned an error, the message where you corrected the agent, and reverts. It groups them into recurring mistake classes by tool and error signature, counts how often each recurred across sessions and days, prices what the recovery cost in tokens, and shows one redacted line of evidence per class. For every class that recurred three or more times it drafts the rule that would have prevented it, in a block you can paste into CLAUDE.md or AGENTS.md, and labels each draft with the confidence of the signal behind it: tool errors are high, phrase-detected corrections are medium, and it never upgrades a guess. It writes the draft next to the report and never edits your rules files. Read-only, no credentials, no network, python3 only. Point claude_dir at resources/fixtures/claude to see a full run on synthetic logs first.

Parameters: `days_back` 14, `out_dir`, `claude_dir`, `codex_dir`, `include_subagents`, `min_recurrence` 3, `show_snippets` `true`, `rules_target` (`claude` / `agents` / `both`, default `both`).

Steps: `read_claude`, `read_codex` (parallel roots) → `merge_ledger` → `classify_turns` → `draft_rules`. Outputs: `out_dir/wrong-turns-report.md`, `out_dir/wrong-turns-rules.md`, JSON on stdout.

## 7. The core math

### 7.1 Record model

```
UsageRecord
  harness           "claude-code" | "codex" | "pi" | "opencode"
  session_id        string
  record_id         dedup key (see 7.3)
  timestamp         ISO-8601 UTC
  model             raw id as logged
  input_tokens      UNCACHED input
  cache_write_tokens
  cache_read_tokens
  output_tokens     includes reasoning
  reasoning_tokens  informational subset of output
  project           cwd or project slug (never leaves the machine)
  is_subagent       bool
  turn_id           id of the human message that started this turn
```

### 7.2 Price per record

```
usd(r) = input_tokens       × price_in(m)
       + cache_write_tokens × price_cache_write(m)     (0 when the table has none, e.g. OpenAI)
       + cache_read_tokens  × price_cache_read(m)
       + output_tokens      × price_out(m)             (reasoning bills as output)
```

Harness normalisation into the model above:
- **Claude Code**: `input_tokens` is already uncached; `cache_creation_input_tokens` → cache_write; `cache_read_input_tokens` → cache_read; `output_tokens` → output; `output_tokens_details.thinking_tokens` → reasoning.
- **Codex**: `input_tokens` includes `cached_input_tokens`, so uncached = input − cached; cache_write = 0; `output_tokens` includes `reasoning_output_tokens`. Per-turn values are the **difference between consecutive `total_token_usage` snapshots** in the same session file (415 snapshots per session observed; `last_token_usage` alone is unsafe). A negative delta (context reset) starts a new baseline and is logged in explain.
- **Pi**: per-turn `usage` in `~/.pi/agent/sessions/*.jsonl` (schema from public docs, fixture-tested, labelled "best effort" in the summary).
- **OpenCode**: per-message `tokens{input,output,reasoning,cache{read,write}}` with `providerID/modelID` under `~/.local/share/opencode/storage/message/**` (same labelling).

### 7.3 Deduplication

- Claude Code: key `(message.id, requestId)`; keep the first line. Measured on this machine: 14,854 of 36,196 usage lines are duplicates (41%). Lines with `isSidechain: true` in the main file are kept (they are real calls) and flagged. Subagent files under `<session>/subagents/agent-*.jsonl` are parsed and flagged `is_subagent`. `<synthetic>` model lines are dropped and counted.
- Codex: dedup is implicit in the delta method; identical consecutive snapshots produce a zero delta and are dropped.
- The ledger summary reports raw lines, duplicates removed, records kept, per source.

### 7.4 Windows, plan cost, multiplier

The tier is the one fact no log carries -- a Pro session and a Max session are the same bytes -- so it is inferred rather than asked for. `comped_core/detect.py` maps each record's model id (after gateway and region prefixes are stripped) to a provider, and each provider to the plans it sells; the assumed plan is the most expensive one per detected vendor, and every candidate is priced beside it as a ladder. A provider that sells no subscription in the table is named, its spend stays in the total, and the card says nothing in the plan cost covers it.

```
W            = [now − days_back, now], on each record's own timestamp
comped_total = Σ usd(r), r ∈ W
plan_cost    = Σ_plans monthly_price × days_back / 30.4375
multiplier   = comped_total / plan_cost            (omitted when plan is api/unknown, or when nothing detected sells a subscription)
comped_net   = comped_total − plan_cost
cache_share  = Σ cache_read / Σ (input + cache_write + cache_read)
```

Plan prices live in `resources/plans.json` with `as_of` and `source_url` per entry. They are never fetched at runtime.

### 7.5 Price table

- `resources/prices.json`: a reduced snapshot of LiteLLM's `model_prices_and_context_window.json` (source URL, upstream commit sha and as-of date recorded in the file header), containing every entry whose normalised name matches a model seen in fixtures plus an allow-list of current Anthropic, OpenAI, Google, DeepSeek, Moonshot, xAI and Mistral ids. Target size under 60 KB so the Play stays inspectable.
- Alias resolution, in order: exact id; strip provider prefixes (`anthropic.`, `us.anthropic.`, `eu.anthropic.`, `global.anthropic.`, `azure/`, `azure_ai/`, `openrouter/openai/`, `openai/`, `bedrock/`); strip a trailing `-YYYY-MM-DD` or `-YYYYMMDD` date; strip `-v1:0`. First hit wins and the chosen key is recorded on the priced record.
- Unknown model → `priced: false`, usd 0, listed in the card footer as "N models unpriced: ids" with token totals. Never estimated.
- Prices are per-token floats; all arithmetic in `decimal.Decimal` with 6-place rounding at display only.

### 7.6 Repeat offenders

Input: human messages from the ledger (Claude: `type=user`, content string or text blocks, not `isSidechain`, not `isMeta`, `origin.kind` absent or `human`; Codex: `event_msg/user_message`).

Exclusions, all measured necessary (LANDSCAPE.md): text starting with `<` (injected context), text starting with "You are" (observer/system prompts), text containing `[Request interrupted`, text under 3 content tokens or over 400 tokens (pasted documents), project dirs matching `*observer*` or `*claude-mem*`.

Normalise: lowercase; replace URLs, absolute paths, `@file` refs, hex ids, numbers with placeholder tokens; drop stopwords; keep first 40 tokens.

Cluster: 2-shingles; union-find over pairs with Jaccard ≥ 0.5; a cluster is a **repeat offender** when size ≥ `repeat_threshold` AND spans ≥ 2 distinct sessions AND ≥ 2 distinct days. Label = the medoid message (highest mean Jaccard to the rest), redacted to 120 chars.

Cost: turn cost = Σ usd of usage records with `turn_id` equal to that message (main + subagents). Repeat cost = Σ turn costs in the cluster minus the cheapest one (the first solve is not waste).

Rote dividend per cluster = repeat_cost × 0.98 (Modiqo's stated figure) and × 0.80 (conservative), both shown, both labelled.

Capture command per cluster: `/play settle <handle> "<label>"` (Claude Code prefix; the report also prints the `$play` form for Codex/Cursor).

### 7.7 Wrong turns

Signals, with confidence:
- **A. Tool error (high)**: Claude `tool_result.is_error == true`; Codex `function_call_output.output` containing `Process exited with code N`, N ≠ 0. Class key = `(tool_name, error_signature)` where signature is the first non-empty line of the error with paths, numbers and hex removed, truncated to 80 chars.
- **B. Correction (medium)**: a human message matching `\b(no,|don'?t|wrong|revert|undo|instead|not what i|that'?s not|stop|roll ?back|why did you|i said)\b` or containing `[Request interrupted by user`. Paired with the immediately preceding assistant action (tool name + 80-char input summary, or "text reply"). Class key = `(preceding_tool_name, correction_stem)`.
- **C. Revert (high)**: a Bash/exec tool input matching `git (revert|reset --hard|checkout -- |restore )`.

A class is **recurring** when it appears ≥ `min_recurrence` times across ≥ 2 sessions. Recovery cost = usd of the turn containing the signal plus the following turn.

Rule drafting is template-based and deterministic: known signatures (`ENOENT|No such file`, `permission denied`, `command not found`, `ModuleNotFoundError|Cannot find module`, `test(s)? failed`, `TypeError|type error`, `timed out`, `merge conflict`, `EADDRINUSE`) map to specific rule text; unknown classes get "Before calling `<tool>` for `<signature>`, verify the precondition; this failed N times across M sessions." Every draft carries its confidence label and evidence count. Nothing is applied.

## 8. Output design

### 8.1 Terminal card (stdout of the final step)

```
┌──────────────────────────────────────────────────────────────┐
│  COMPED                                     last 30 days      │
│                                                               │
│  $8,570.20 comped                                             │
│  42.9×  vs Claude Max 20x + ChatGPT Plus ($220.00 prorated)   │
│                                                               │
│  claude-opus-5     $5,102.40   61%   ▇▇▇▇▇▇▇▇▇▇▇▇             │
│  claude-fable-5    $3,011.75   35%   ▇▇▇▇▇▇▇                  │
│  gpt-5.5             $456.05    5%   ▇                        │
│  cache read share 78%   active days 27/30   sessions 312      │
│  since last run (2d ago): +$611.10, +0.9×                     │
│                                                               │
│  REPEAT OFFENDERS                                             │
│  3× "create a post for <project> completion..."   $88.40      │
│  3× "merge and push to main and then save-context" $41.20     │
│  4× "push it to prod"                              $283.00    │
│  Rote dividend: $404 at 98% · $330 at 80%                     │
│  capture: /play settle priya "create a post for ..."          │
│                                                               │
│  list-price equivalent, not a bill · prices as of 2026-09-01  │
│  2 models unpriced (nano_banana, <synthetic>) · explain →     │
│  ~/comped/comped-explain.txt                                  │
└──────────────────────────────────────────────────────────────┘
```

ANSI colour when stdout is a TTY and `NO_COLOR` is unset; plain otherwise. Box width fixed at 64 columns.

### 8.2 SVG card

1200×675 (16:9 for X and LinkedIn). Dark default, light theme by parameter. Headline number at 120px, multiplier line at 48px, three model bars, footer with "list-price equivalent, not a bill", price as-of date, and the Play URI. System font stack, no external assets, no scripts. Pure string templating with XML escaping.

### 8.3 PNG

Opportunistic: macOS `qlmanage -t -s 1200 -o <out_dir> comped-card.svg` (ships with the OS); Linux `rsvg-convert` if on PATH; otherwise skipped and the report says "PNG skipped: no renderer found; the SVG uploads fine to LinkedIn and can be screenshotted for X".

### 8.4 Share text

Printed under the card and saved:

> I got comped $8,570 on a $220 plan this month. 43×. Measured from my own Claude Code and Codex logs with the comped Play on @Modiqo's rote. Run it on yours: rote play run https://play.modiqo.ai/<handle>/comped

### 8.5 Markdown report

Sections: Card · Models · Harnesses and sources found (with unreadable sources and why) · Repeat offenders (table + capture commands) · Rote dividend · Delta since last run · Unpriced models · Methodology (formula, dedup counts, price table version, plan table version) · Privacy (what was read, what was written, what was never read).

### 8.6 Explain file

One line per priced record group: model, key resolved, tokens by class, rate, usd. Then dedup decisions per source, delta baselines for Codex, and the plan proration arithmetic. This is the reproducibility artefact.

### 8.7 Delta since last run

`comped-baseline.json` stores the previous run's totals, multiplier, per-model usd and repeat clusters (labels + counts). The card shows the change; the first run says "baseline saved". Mirrors playoffs-standings, which judges have seen.

## 9. Privacy and trust statements (verbatim in every description and report)

- Reads: session logs under the four configured directories. Nothing else.
- Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Which AI you run is inferred from the model ids already in those logs; the plan tier is never read from your account.
- Never sends from the core: reading, pricing and rendering make no network calls. Verifiable: `comped_core` imports no `urllib`, `http`, `socket`, `subprocess` (except the PNG renderer, which is invoked with a fixed argv and no shell). The one step that talks to the network is `comped`'s `post_score`, a separate short script that sends your score to the gotcomped.com leaderboard after the card is written and nothing before; `leaderboard=false` skips it, and a failed post never fails the run.
- Writes: only under `out_dir`. Every written path is listed in the report.
- Message text: truncated to 120 chars and hashed by default. `redact=false` keeps full text locally, never in the card.

## 10. Registry-quality checklist (fixes the 0.45 floor)

Before publishing each Play, run `himanshu-jha/play-quality-doctor` on it and clear every named signal:
- fixtures declared under the key the rubric reads (`resources/fixtures/**` exist for both harnesses)
- parameters typed, defaulted, with `example` and `input.label`, choices for `plan`, `card_theme`, `rules_target`
- output schema: every step's final `out.result()` (or stdout JSON) has stable keys documented in the description
- tags from the registry taxonomy (observe existing tags on token-tab, audit-play; likely `sessions`, `shell`, `tokens`, `cost`, `claude-code`, `codex`)
- `license: MIT`
- description length and specificity comparable to play-quality-doctor's

## 11. Testing standard

- Stdlib `unittest`, run with `python3 -m unittest discover -s tests`. No third-party runtime or test deps.
- Fixture generator `tools/make_fixtures.py` derives synthetic logs from real ones: keeps structure, token counts, timestamps (shifted), model ids, dedup duplication pattern, subagent layout; replaces every human/assistant text with deterministic lorem seeded by a hash; replaces paths with `/home/demo/project-N`. Output committed under `resources/fixtures/`. A test asserts no fixture line contains a real path or a word from a deny-list.
- Golden tests: fixture totals per model to the cent, dedup counts, Codex delta sums equal the final cumulative total, repeat clusters and wrong-turn classes exact.
- Conformance: if `npx` is available, `ccusage daily --json` on the Claude fixture must match our Claude totals to the cent under the same price table (skip with a message otherwise).
- Determinism: two runs with `--now` pinned produce byte-identical report, SVG, explain and JSON.
- No-network test: import graph of `comped_core` contains none of `urllib`, `http`, `socket`, `requests`.
- Performance: 1 GB of logs in under 10 s on this machine (single pass, streaming JSON per line, no re-reads).
- Robustness: truncated last line, malformed JSON line, missing `usage`, missing `model`, empty directory, non-existent directory, permission-denied file. Each yields a labelled unknown in the summary and never a traceback.

## 12. Distribution plan (adoption is a judged criterion)

1. Publish `session-ledger` and `comped` on the same day, `wrong-turns` the next day. Downloads compound; a Play published Friday cannot catch one published Wednesday.
2. Discord: one post per Play in the sharing channel with the run command, one screenshot of the card, and the sentence "point claude_dir at resources/fixtures/claude to try it on synthetic logs". Reply to every question within the hour.
3. Social: one card per day on X and LinkedIn tagging Modiqo, with the multiplier as the hook. Ask five participants to post theirs. This is the Apple Watch entry and the adoption engine at once.
4. Cross-reference: each description names the other two Plays. The report ends with "see also".
5. Run `playoffs-standings` each morning with `author=<handle>` and log deltas in `docs/adoption-log.md`.
6. Never ask anyone to download without running. Purchased or bot engagement disqualifies.

## 13. What outlives the hackathon (product vision)

Month 1: `session-ledger` becomes the shared parser other Play authors depend on; add Gemini CLI, Goose, Cline family adapters via the same fixture-first method. Month 3: the Comped card grows the optional, opt-in aggregate leaderboard already specified in the earlier product draft (see `~/Projects/unbilled/docs/SPEC.md` §5–8), kept out of this Play on purpose. Month 6: `wrong-turns` rules feed back into Plays as preconditions. Revenue: none inside the Plays, ever; the hosted board and team views are the business. The hackathon validates the parser, the pricing, and whether the card spreads.

## 14. Risks and the answer to each

| Risk | Mitigation |
|---|---|
| Rote step format differs from assumption (script files vs recorded commands) | Gate task 0 verifies before any build; CLI is designed so either works (each step is one shell command with literal flags). |
| Composition unsupported | Bundle identical `comped_core` copies; CI asserts byte-equality. |
| Log schema drift across Claude Code / Codex versions | Adapters key on field presence, not version; unknown shapes count as "unparsed lines" in the summary. Fixtures include the current schema; add fixtures when a new version appears. |
| Price table wrong or stale | Header carries source, sha, as-of; unknown models never guessed; `rates_path` override; explain shows every rate used. |
| Judges see "meta Play" as gaming | The core value (cost, repeats, rules) is useful any week of the year; description never mentions the hackathon. |
| Repeat detection produces junk clusters | Exclusion list measured on real logs; medoid labelling; thresholds are parameters; report shows why each cluster qualified (sessions, days). |
| Wrong-turn phrase signal is noisy | Confidence labels; phrase hits are medium and never produce a rule alone unless recurring across sessions; tool errors carry the rules. |
| Someone's logs are 10 GB | Streaming line reader, `days_back` prefilter on file mtime before parsing, progress line to stderr. |
| PNG renderer absent | SVG is the deliverable; PNG is opportunistic and the report says so. |

## 15. Simulated judge panel: projected scorecard

Weights follow the three published criteria plus sponsor fit. Scores assume the plan is executed in full, including the checklist in §10 and the tests in §11.

| Judge | Focus | Score | What earns it | What still costs points |
|---|---|---|---|---|
| CEO, token-cost thesis | on-thesis, work worth teaching | 10 | Measures repeats and prices the 98% claim on the participant's own machine; drafts the next Play | none identified |
| Tracing engineer | runs deterministically, degrades gracefully | 9.5 | delta method for Codex, dedup on measured duplicates, byte-identical reruns, every source degrades to labelled unknown | Pi/OpenCode adapters are fixture-verified only |
| Domain modeller | honest contract | 9.5 | plan inferred from log model ids and never from an account, no credential file read, writes listed, effects and confidence labels | `declaredWrites` semantics unknown until install (gate task) |
| Community lead | will the crowd run it this week | 9.5 | card is the post; repeat list is the next Play; delta gives a reason to rerun; three Plays cross-linked | adoption is ultimately market-driven |
| DX lead | 10-second comprehension | 9.5 | one number, one card, fixtures for a risk-free first run, `explain` for the sceptic | description length must stay under control |
| Adoption market | downloads | 9 | published day 1 with distribution plan; three shots at the prize | incumbents have a two-day head start |
| **Weighted** | | **9.6** | | |

Residual risk that no spec can remove: adoption depends on other people. The distribution plan in §12 is the only lever and it is executed daily.

## 16. Acceptance criteria (definition of done)

1. All three Plays published to Community, inspectable at `play.modiqo.ai/<handle>/{session-ledger,comped,wrong-turns}`, each with `stats.downloads ≥ 1` from a machine that is not ours.
2. `rote play run .../comped claude_dir=resources/fixtures/claude codex_dir=resources/fixtures/codex --yes` completes in under 10 s on a clean machine with only python3 and prints the card.
3. On this machine, Claude totals match `ccusage` to the cent under the same price table.
4. `python3 -m unittest discover -s tests` passes; determinism, no-network, robustness and fixture-privacy tests included.
5. `play-quality-doctor` reports no fixable signal on any of the three Plays.
6. Each description contains the privacy paragraph from §9 verbatim.
7. Public GitHub repo with README (card screenshot, run commands, methodology), `VISION.md`, MIT licence, CI running the test suite on macOS and Linux.
8. One card posted per day on X and LinkedIn tagging Modiqo from publish day to close; `docs/adoption-log.md` updated daily.
9. The captured run for each Play contains one visible wrong turn, kept on purpose.

## 17. The leaderboard (added 05 Sep)

comped is the product; the Play is how you run it. Every run ends by posting the score to a leaderboard at `https://gotcomped.com/leaderboard.html`, because a number people compare is what makes a card travel.

**What is sent, and nothing else** (`leaderboard/post_score.py`, bundled into `comped` as `resources/post_score.py`, never into the other two Plays): handle (or blank), multiplier, tier, `comped_usd`, `plan_usd`, plan label and id, `plan_source`, provider keys, harness keys, `days_back`, `active_days`, `sessions`, `cache_share`, client version, and a random device id kept in `out_dir/comped-device.txt` that keys the row. No paths, prompts, model ids, session ids or hostnames; a test asserts the field list. The payload and the reply are written to `out_dir/comped-rank.json` before and after the call. `leaderboard=false` exits before opening a connection. A failed post is a warning and exit 0; the card never depends on the network.

**Storage and API.** Postgres (Supabase) behind PostgREST, reached only through two `security definer` SQL functions, `comped_submit(jsonb)` and `comped_board(text, int)`, with a publishable key from two stdlib Python functions on Vercel: `POST /api/score` and `GET /api/leaderboard?sort=multiplier|comped_usd&limit=N`. The table and the ranking view are closed to the API roles. SQL enforces every bound (handle `^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$`, `comped_usd` 0–10M, `multiplier` 0–100k, `plan_usd` 0.5–100k, days 1–366, `multiplier == comped_usd / plan_usd` within 2%), a 15-second per-device interval, and holds entries over 2,000× or $250,000. The device id is never returned, so a reader cannot write anyone's row.

**Ranking.** By multiplier, then `comped_usd`, then `active_days`, then first to post. Eligible = not held, has a multiplier, `comped_usd >= 20`, `active_days >= 3`. One row per handle (latest run wins) or per anonymous device (`anon-` + last four of the id). The site fetches the board from its own origin only (`connect-src 'self'`).

**Copy.** The absolute "nothing leaves your machine" is retired everywhere. The honest line is: your logs never leave; the one thing sent is your score, here is the exact list, and here is the switch.


## 18. The account-free path (added 05 Sep)

rote will not run a Play until the person running it is signed in to a Modiqo account. That is true of a published Play fetched from the registry and equally true of a local package directory, verified by running both from a clean config: `error: rote requires login`. Reading a Play needs no account (`rote play inspect rajkaria/comped` returns the full manifest anonymously); running one does.

For a tool whose growth thesis is that the card spreads on its own, an account gate in front of the payoff is the most expensive thing in the funnel: install a binary runner, then create an account, and only then see your number. So comped ships a second front door, and the Play stays as the first.

**Two doors, one tool.**

| | `comped.sh` | `run.sh` (the Play) |
|---|---|---|
| Account | none | free Modiqo account |
| Installs | nothing; a temp dir, deleted on exit | rote, to `~/.local/bin` |
| Before it runs | the script, and a published sha256 | a consent screen listing every path, and a public archive |
| Download | ~150 KB | rote binary, then the Play |
| Code that runs | byte-identical core | byte-identical core |

Both take the same fourteen parameters with the same defaults, enforced by `tests/test_standalone.py` against `docs/plays/comped/PARAMETERS.json`. A line copied from the docs works through either door.

**How it is built.** `tools/build_dist.py` assembles `site/comped.tar.gz` from `comped_core/`, `resources/{prices,plans}.json`, `leaderboard/post_score.py`, `standalone/comped.py`, the sample logs and the licence. Layout matches the repo so `prices.py::_bundled()` finds its resources unchanged. The archive is reproducible: fixed mtimes, fixed ownership, sorted entries, a gzip header with no timestamp. Two builds of one commit produce one sha256, which is what makes the published checksum worth checking. `tools/build_site.py` builds it, so Vercel produces it on every deploy.

**The entry point.** `standalone/comped.py` takes `key=value` arguments exactly as the Play does, calls `comped_core.cli.cmd_run` for the offline pipeline, then `post_score.py` for the one network call. The core stays provably offline: `cmd_run` reads, prices, clusters and renders, and knows nothing about the poster, so `test_no_network.py` is unchanged.

**Two things the archive forced.**

- `comped_core/cli.py` gained a `run` subcommand: the same functions the eight Play steps call, in one process, printing the card for a person instead of a JSON line for a runner. Progress goes to stderr so a piped stdout is exactly the card.
- Reproducible mtimes made the packaged sample logs invisible, because the readers skip files modified before the window. `comped.py` stamps the packaged fixtures with the current time when a relative path resolves inside the package, and never touches anybody's real logs.

**Windows.** The paste needs a Unix shell, so WSL remains the answer for the one-liner. The tool underneath is standard-library Python with no Unix dependency; `cli.py` now asks for UTF-8 on stdout, without which the card's box characters raise `UnicodeEncodeError` against a Windows code page whenever stdout is a pipe. A non-gating `windows-standalone` CI job unpacks the real archive on `windows-latest` and runs it with stdout redirected. The site offers that path and does not promise it until that job has been green.
