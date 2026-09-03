# Rote Playoffs landscape (as of 2026-09-03 20:20 IST)

Facts gathered before the spec was written. Every number here was read from the live registry or measured on this machine. Re-verify anything older than a day before quoting it publicly.

## The hackathon

| Fact | Value | Source |
|---|---|---|
| Build window | 1 Sep 2026 → 7 Sep 2026, 20:00 London (00:30 IST 8 Sep) | luma.com/rotehack |
| Submission | Publishing a Play to **Community** is the submission. No form. | the-playoffs blog |
| Prizes | 1st MacBook Pro, 2nd iPad, 3rd iPhone 17, Apple Watches for best social posts tagging Modiqo | luma |
| Prizes are awarded **per Play** | teams welcome, one prize per Play | the-playoffs blog |
| Judging | (1) does it run, (2) can a stranger understand and trust it, (3) do people adopt it after publication | luma + progressiverobot |
| Adoption is measured as | downloads over the week, by other participants | progressiverobot |
| Organizer guidance | "more than one meaningful action, an input that changes next time, and a stable result"; "keep one wrong turn" as proof of human steering; "the Play you will still want six months from now"; boring beats novel | the-playoffs blog |
| Disqualifiers | purchased engagement, bot activity | the-playoffs blog |
| Rote does not | publish or post social copy for you | the-playoffs blog |
| Judges (inferred) | Modiqo founders: Chetan Conikee (CEO), Hubert Plociniczak (compilers/tracing), Roberts Pumpurs (Rust/OTel), Debasish Ghosh (domain modelling); WeMakeDevs (Kunal Kushwaha); DevTools Academy (Ankur Tyagi) | modiqo.ai/about, luma |

## Registry state

- 344 public Plays. Roughly: 60 git/repo auditing, 50 API integrations (GitHub, Gmail, Calendar, Linear, Stripe), 40 infra/DNS/CI, 35 security scanning, 40 DX/setup checks, 15 agent auditing, 8 real estate, 5 job hunting.
- Most-downloaded Plays are modiqo's own zero-credential onboarding Plays: Hello 167, List Top Committers 160, Search Github Repositories 142.
- Top participant Plays (lifetime downloads, 3 Sep evening): Hackathon Submission Readiness (himanshu-jha) 19, CI Test Healer (swapankumar) 18, Git History Secret Scan (himanshu-jha) 18, Playoffs Standings (dotisacat) 13, Reach Check (sookra) 11, Audit Play (jaylabs) 11, CI Self Healer 10, Web Game Build Readiness 10, Floor Check 9, Play Quality Doctor 9.
- Feed and Play pages report different counters (feed said Playoffs Standings 13; its manifest said 7). The manifest `stats.downloads` is the authoritative number. Feed counts appear to include something else or lag.

## Direct competitors for a token/session Play

| Play | Author | Version | Downloads (manifest) | What it does | Gap we exploit |
|---|---|---|---|---|---|
| token-tab | sidships | 0.1.0 | 6 | Claude Code only. Table of tokens + list-price per model, heaviest sessions with subagent cost, four waste checks, proposes a CLAUDE.md diff. Bundled price table with source URL and as-of date. Bundled demo logs. 2 steps: `audit`, `rates_check`. python3 only. | No Codex, no Pi. No multiplier vs plan. No repeat detection. No card. Description is honest and good; ours must be at least as honest. |
| session-digest | dotisacat | 0.1.1 | 3 | Claude Code + Codex activity summaries (counts, durations, tool calls) without content. | Counts, not dollars. No repeats, no card. |
| mcp-context-tax | dotisacat | 0.1.2 | 4 | Estimates MCP schema token cost. | Adjacent, not overlapping. |
| agent-work-daily-close | modiqo | 1.0.1 | 5 | Audits Codex, Claude Code, Pi sessions for credential exposure, tool use, git closure, "token-to-outcome attribution". 5 steps, requires node + git. | Proves the pattern is sanctioned by Modiqo. Not a cost tool. |
| audit-play | jaylabs | 0.4.1 | 1 | Least-privilege review of allow rules vs executed tools from transcripts. 6 DAG steps, 11 parameters, no network. | Shows the ceiling for rigor in a description ("every headline number cites its field"). |
| skill-rot-detector | harshitborana75 | 0.0.3 | 4 | Skill/rules health across harnesses. | Adjacent. |

Nothing in the registry: computes a multiplier against a subscription plan, detects repeated asks across sessions, drafts capture commands, mines corrections/tool errors into rules, or renders a shareable card.

## What the rote.play.v1 manifest exposes (from four real manifests, saved alongside this file)

- `description` (long prose, this is the pitch; 1000–1500 chars typical for good ones)
- `parameters[]`: `name`, `type` (string|integer), `default`, `required`, `description`, `example`, `input.label`, `input.choices[]`, `input.allowCustom`
- `requirements`: `localTools[]` (e.g. python3, curl, node, git, rote), `adapters[]`, `browser{}`, `roteCli.minimumVersion` (0.62.0), `sessions` (bool; rote MCP sessions, not agent logs)
- `effects`: `declaredWrites[]`, `credentialsProvidedBy: runner`, `credentialsRemainLocal`, `publisherReceivesCredentials: false`
- `steps`: `count`, `names[]` (snake_case)
- `distribution`: sha256 digest, `application/vnd.modiqo.rote-flow`, size 13–68 KB
- `license` (optional; play-quality-doctor declares MIT)
- `stats.downloads`, `stats.installs`
- `producedBy.roteVersion` (current authors are on 0.77–0.78)
- Run: `rote play run https://play.modiqo.ai/{owner}/{name}@{version} [name=value...] [--yes]`
- Inspect without installing: append `.json` to the Play URL.

## Quality rubric (reverse-engineered from play-quality-doctor's description)

- 67 of 119 scored Plays sit at a 0.45 floor.
- Signals include: fixtures declared under the correct frontmatter key, parametrization, an output schema derived from keys passed to `out.result()`, tags from the registry taxonomy, license.
- The rubric is not documented publicly. Plan: run play-quality-doctor against our own Plays before publishing and fix every named signal.

## How a Play is made (from Modiqo's authoring posts)

1. Record: every API/browser/shell step lands in a rote workspace as `@1, @2, ...` with dataflow edges.
2. Extract: errored and skipped steps are dropped (they stay in the workspace as evidence).
3. Package: literals become typed parameters (the agent decides which), dependencies resolved into a DAG, parallel where independent.
4. Validate: API steps fingerprinted; shell steps get preconditions.
5. Version: `rote play release`, `rote registry play push`; URI `play.modiqo.ai/<owner>/<name>@<version>`.
- Harness commands: `/play explore <task>` (search first), `/play settle <handle> <summary>` (compile). Claude Code prefix is `/play`.
- Compilation fails on: pasted payloads instead of references, overwritten variables, work done outside rote (no trace), undeclared state dependencies.
- `rote workspace health` scores compilability 0–100.
- Plays bundle a `resources/` directory (play-quality-doctor defaults a parameter to `resources/samples/needs-work`; token-tab bundles demo logs and a rates table).

## Unknowns to verify the moment rote is installed (gate for the plan)

1. Exact on-disk layout of a Play archive and how `resources/` files are referenced from steps.
2. Whether a step is a recorded shell command string, a script file, or a JS/Python step with `out.result()`.
3. Whether a Play can declare another Play as a dependency (composition). README of rote-releases says flows compose; no manifest we saw shows it.
4. The frontmatter key names for fixtures, tags, output schema, license.
5. Whether `declaredWrites` covers local files or only services (token-tab writes `~/token-tab.md` and declares none).
6. How `rote play run` passes parameters into the shell steps (env vars vs templated literals).
7. Whether a step may spawn `python3 resources/x.py` and whether python3 is a declared `localTools` entry automatically.

## Measurements on this machine (real logs, 13 Jul → 3 Sep 2026)

Claude Code, `~/.claude/projects/`:
- 124 project dirs, 319 top-level session files, 223 subagent files at `<project>/<session>/subagents/agent-*.jsonl`, plus `tool-results/`, `workflows/`, `memory/` dirs to skip.
- 36,196 assistant usage lines; **14,854 (41%) are duplicates on (requestId, message.id)** because each content block is a separate line carrying the same `usage`. Dedup is not optional.
- Usage keys: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`, `output_tokens_details.thinking_tokens`, `cache_creation.ephemeral_1h_input_tokens/5m`, `service_tier`, `speed`, `iterations[]`.
- Record keys: `type`, `timestamp`, `sessionId`, `requestId`, `apiBlockIndex`, `isSidechain`, `isMeta`, `cwd`, `version`, `gitBranch`, `entrypoint`, `message.model`, `message.id`.
- Models seen: claude-opus-5 (20,780 lines), claude-fable-5 (12,886), claude-opus-4-8 (1,888), claude-fable-5-1 (774), plus `<synthetic>` and non-LLM ids (`nano_banana`, `z_image`, `recraft_v4_1`) that must be reported as unpriced.
- Human prompts: `type: user`, `message.content` is a string for typed prompts, a list for tool_results. `origin.kind: human` and `promptSource` exist on newer lines. 296 sessions have a human first prompt.
- Automated prompts pollute naive clustering: "hello memory agent" ×67 and "You are a Claude-Mem..." ×62 openers. A Jaccard-0.3 clustering on raw first prompts produced one 123-member junk cluster. Filter `origin.kind != human`, prompts starting with `<` or "You are", and observer project dirs.
- Real repeats exist: "create a post for hunch cup completion" ×2, "push it to ..." ×3, "merge and push to main and then /save-context".
- Wrong-turn signals: 873 `tool_result.is_error` blocks, 311 human messages containing a correction phrase, 1 git revert in tool results, 0 "[Request interrupted by user" markers in this version's logs.
- `~/.claude.json` `oauthAccount` exposes `billingType: stripe_subscription` and `subscriptionCreatedAt` but **not** the tier. Plan must be an input.

Codex, `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`:
- 109 files (15 May → 9 Jun 2026 here).
- `event_msg/token_count.info.total_token_usage` is cumulative per session; `last_token_usage` is the last turn. 415 token_count events in one session, so difference consecutive totals rather than trusting one event per turn.
- Fields: `input_tokens` (includes `cached_input_tokens`), `output_tokens` (includes `reasoning_output_tokens`), `total_tokens = input + output`.
- Model lives in `turn_context.payload.model` (e.g. `gpt-5.5`) and `collaboration_mode.settings.model`. `session_meta.payload` has `cwd`, `originator`, `cli_version`, `model_provider`.
- Human prompts: `event_msg/user_message.payload.message`.
- Tool calls: `response_item/function_call` (`name`, `arguments`, `call_id`) and `function_call_output` (`output` text begins "Chunk ID ... Process exited with code N").
- `~/.codex/auth.json` keys: `auth_mode`, `OPENAI_API_KEY`, `tokens`, `last_refresh`. Do not read it.

Price table (LiteLLM `model_prices_and_context_window.json`, 2.09 MB, 3,518 entries, fetched 3 Sep):
- Has `claude-fable-5-1` ($10/$50 per M in/out, cache write $12.50, cache read $0.25), `claude-fable-5`, `claude-opus-5` ($5/$25), `claude-opus-4-8`, `claude-sonnet-5` ($2/$10), `claude-haiku-4-5-20251001`.
- `gpt-5.5` only under `azure_ai/gpt-5.5` and `azure/gpt-5.5` ($5/$30, cache read $0.50, no cache write cost). Alias resolution must strip provider prefixes and date suffixes.
- No `gpt-5.5-codex` entry. Unknown models are reported as tokens, never guessed.

Runtimes on this machine: python3 3.10.2, node 25.9, bun, uv, jq. Plays in the registry require only `python3`, so the core is stdlib-only Python 3.9+.
