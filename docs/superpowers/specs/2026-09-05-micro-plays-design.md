# Micro Plays — design

**Date:** 2026-09-05 · **Status:** approved for planning · **Branch:** `claude/plays-micro-interactions-2dbab6`

Twelve rote Plays you run *many times a day*, on a third stdlib-only core (`micro_core`). The three
comped Plays answer a question about a month; the six daily Plays answer a question about a day. These
answer a question about **the last thirty seconds**, and the answer arrives before you have finished
looking at the terminal.

## Why this shape does not exist yet

A registry survey on 5 Sep 2026 (`rote play search --source registry --scope public`, 27 queries)
returned **zero** public Plays for: clipboard, base64/JWT decode, quick capture, timer, unit convert,
habit streak, expense log, context switch, scratch note, mood, hex colour, password generation, QR,
checklist, stopwatch, standup note, file size. Of 821 public manifests, nearly all are once-a-day repo
reports. All twelve names below are free.

The reason the category is empty is a design problem, not an oversight: a Play you run twice needs a
reason to be run the second time. So the twelve split into two kinds, and the second kind is the point.

- **`fn`** — pure: an input goes in, an answer comes out, nothing persists. Useful every time, identical
  every time.
- **`log`** — the Play appends one line to a local file and reports on the accumulation. The tenth run
  is more useful than the first. This is what makes a micro-interaction worth building.

## Decisions taken

| Decision | Choice |
|---|---|
| Leaderboard | **None.** No `/api/score` change, no Supabase migration, no page on gotcomped.com. Every Play still prints one shareable line. |
| Branch base | The six daily Plays were merged in first (`claude/publish-plays-daily-activities-122fcf`), so one branch carries all eighteen. Merge was clean; 329 tests pass. |
| Publishing | All twelve pushed live to `play.modiqo.ai/rajkaria/<name>@0.1.0`. |
| Core | A third core, `micro_core/`. `comped_core` and `daily_core` are untouched. |
| Composition | No. Bundle copies, as with the other nine. |

## The contract every micro Play keeps

1. **One step if pure, two if it remembers.** A `log` Play is `record` → `report`, the two sharing the
   state file that is the whole point of it. A `fn` Play is a single `report` step: giving it a second
   step would mean inventing a scratch file for the two halves to talk through, and a Play that claims
   to write nothing should not write a scratch file to prove it. The presentation template handles both.
2. **Fast enough to not think about it.** Each step ≤ 400 ms on the bundled fixtures, asserted by
   `tests/test_micro_perf.py`. A future edit that makes a micro Play slow fails the suite.
3. **No `out_dir`.** The daily Plays write a report file; these print. The only things that touch disk
   are the four `log` Plays' own state file, `jot`'s vault line, and `since-last`'s snapshot.
4. **One shareable line**, printed last before the JSON, phrased as a fact about you, not a metric.
5. **`demo=true`** runs the whole Play against bundled fixtures, so a stranger's first run needs
   nothing installed and touches nothing of theirs.
6. **`now`** is injectable on every Play, so every test is deterministic and no clock is read twice.

## The twelve

`W` marks a Play that writes. Params listed are the ones that vary on reuse; every Play also takes
`demo` and `now`.

### Family A — paste in, answer out (`fn`, read-only)

| Play | Params | Answers | Shareable line |
|---|---|---|---|
| `whatis` | `text`, `depth=4`, `reveal=false` | Identifies and **peels** an opaque string: JWT (header, claims, expiry), base64/base64url, hex, URL-encoding, gzip, JSON, epoch s/ms/µs/ns, ISO-8601, UUID v1/v3/v4/v5/v7 (with the time embedded in v1 and v7), ULID, git SHA, IPv4/IPv6 with RFC-1918 / loopback / CGNAT classification, CIDR, MAC, semver, cron, hex colour, data URI, hash-by-length, e-mail, URL with its query broken out, and file magic bytes behind a base64 blob. Recurses: base64 → gzip → JSON → JWT is one input and four layers. | "four layers deep: base64 → gzip → JSON → JWT, expired 4h ago" |
| `fits` | `text`, `path`, `window=200000`, `models`, `rates_path` | Will this fit, and what will it cost. Exact bytes, lines, words; a token **range** from a documented character-class estimator, never a single number dressed up as exact; percentage of the window; and cost per model from the maintained price table. | "38k–44k tokens · 21% of a 200k window · $0.34–$0.39 on Opus" |
| `is-it-secret` | `text`, `path`, `strict=true`, `show=redacted` | Run it before pasting anything into a chat or an agent. Detects AWS, GitHub, Slack, Stripe, Google, OpenAI, Anthropic, Twilio, SendGrid and npm/PyPI token shapes, PEM and SSH private keys, JWTs, connection strings and basic-auth URLs carrying a password, `.env` assignments whose value has high Shannon entropy, and prints the redacted text ready to paste. | "2 things to redact before you paste that" |
| `cron-when` | `expr`, `tz`, `count=5` | Next N fires in your zone and in UTC, the schedule in English, the average interval, and a DST warning when the expression fires in a transition window or pins an hour in a zone that shifts. | "every weekday 09:30 — next Mon 09:30 IST (04:00 UTC); skipped once on 29 Mar" |

### Family B — two-second write that compounds (`log`, `W`)

| Play | Params | Answers | Shareable line |
|---|---|---|---|
| `punch` W | `note`, `tag`, `state_dir`, `days_back=14` | Appends what you are doing now; reports today's punch count, **context switches** (a switch is a punch whose topic differs from the one before it), the length of the block you are in, the longest block today, a day-shape sparkline, and the streak of days with at least one punch. Low is good here, which makes it a fresher number than "biggest wins". | "6 switches today · longest block 74 min · 9-day streak" |
| `spent` W | `entry`, `currency`, `budget`, `state_dir` | `entry='320 lunch'` — parses amount, currency symbol, label and `#tag`. Reports today, this month, the top categories, the daily average, and the projection against `budget`. No bank login, no file parsing; a different axis from the published `receipt-ledger`, which reads receipt files. | "₹3,240 this month · food is 41% · on pace for ₹6,100 of ₹6,000" |
| `jot` W | `note`, `vault_dir`, `inbox=Inbox.md`, `state_dir` | Quick capture. Appends `- HH:MM note` to the vault inbox (plain Markdown, Obsidian-compatible), refuses an identical note within 60 s, and mirrors to the log so the count survives a vault move. Pairs with the published `vault-pulse`, which measures the vault this one fills. | "captured · 7 today · 12 unfiled in the inbox" |
| `streak` W | `did`, `state_dir`, `window=21` | `did=water`. Per-habit current streak, longest ever, a 21-day grid, and the weekday you miss most — which is the only part of a habit tracker that ever changes behaviour. | "water: 12-day streak · longest 19 · you miss Sundays" |

### Family C — mid-agent-loop

| Play | Params | Answers | Shareable line |
|---|---|---|---|
| `last-turn` | `claude_dir`, `codex_dir`, `rates_path`, `plan` | What the turn that just finished cost: model, tokens in/out, cache read and write, dollars, and today's running total. `comped` answers this for a month; nothing answers it for the last ninety seconds. Reads only the **tail** of the newest transcript, which is what keeps it micro. | "that turn: 41.2k in / 2.1k out · 88% cached · $0.19 · $4.10 today" |
| `budget-left` | `daily_budget=10`, `claude_dir`, `codex_dir`, `rates_path`, `plan` | Spent today against the budget you set, the burn rate per hour, and the clock time you run out at the current rate. Shares `turn.py` with `last-turn`. | "$4.10 of $15 · burning $2.40/h · cap reached about 16:40" |
| `since-last` W | `root=.`, `ignore`, `max_files=20000`, `watch_sensitive=true` | The agent's blast radius. Files created, modified and deleted under `root` since the last time you asked, with line deltas and the biggest offender — plus a loud flag if anything changed under `~/.ssh`, `~/.aws`, `~/.config` or `~/Library/LaunchAgents`, which is the question people actually have after an agent turn. | "11 files touched · +412 / −38 lines · nothing outside the repo" |
| `safe-to-commit` | `repo=.`, `max_file_kb=512`, `strict=true` | Reads the staged set and flags secrets, debug prints, oversized files and a stray `.env` before you commit. Distinct from the registry's `pr-preflight` and `commit-message-lint`, which read the message and the PR, not the staged bytes. | "3 staged files · 1 blocker: AWS key in config/dev.env" |

## `micro_core`

```
micro_core/
  __init__.py  __main__.py
  cli.py        one argparse dispatch; one subcommand per step; every step prints
                human text then one JSON object as its last line
  common.py     emit, envelope, as_bool, now_utc, expand, human numbers, sparkline,
                width-aware truncation. A deliberate ~200-line subset of daily_core.common
                rather than a cross-core import: three cores, zero coupling between them.
  store.py      append-only JSONL + streak and rollup maths        → punch, spent, jot, streak
  decode.py     the peeling identifier                             → whatis
  secrets.py    token shapes, PEM blocks, entropy, redaction       → is-it-secret, safe-to-commit
  cronx.py      cron parse, next fires, English, DST warning       → cron-when
  size.py       bytes/lines/words, token range, window fit, cost   → fits
  turn.py       tail the newest transcript, price one turn         → last-turn, budget-left
  snapshot.py   filesystem snapshot and delta                      → since-last
  gitindex.py   .git/index v2 parser (paths, blob shas, sizes)     → safe-to-commit
  fixtures/     synthetic inputs for demo=true, one dir per Play
```

Nine modules, twelve Plays: `punch`, `spent`, `jot` and `streak` are four thin CLIs over one `store.py`,
and `last-turn`/`budget-left` share `turn.py`. That is why twelve is not twelve times the work.

**The one reuse across cores.** `fits`, `last-turn` and `budget-left` need model prices, and there is
already a maintained table with a resolver: `comped_core.prices.rate_for` and
`comped_core.pricing.usd_for` over `resources/prices.json`. Those three Plays bundle `comped_core`
alongside `micro_core` rather than growing a second price list that would silently drift. No other
micro Play links to another core.

**No subprocess, anywhere.** `safe-to-commit` does not shell out to `git`; it parses `.git/index`
(version 2, documented format) for the staged paths and blob shas, reads loose objects with `zlib`, and
where a staged blob lives in a packfile it reads the working-tree copy and says so in the output rather
than pretending it read the blob. This keeps the invariant that made the other nine Plays trustworthy:
`micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, and a test asserts it.

## Writing, declared loudly

Five of the twelve write: `punch`, `spent`, `jot`, `streak` and `since-last`. `last-turn` and
`budget-left` only read transcripts, so they keep `effect-read-only`. Every published Play so far is tagged `effect-read-only`, and blurring that
would cost more than the feature is worth, so:

- Writers are tagged `effect-local-write`, never `effect-read-only`. (If the registry taxonomy rejects
  that literal, the closest accepted `effect-*` term is used and the choice recorded here.)
- Every write in the four log Plays is an **append** to one file under `state_dir` (default
  `~/.rote-micro`), or, for `jot`, one line appended to an explicitly named vault inbox. Nothing is
  deleted, truncated or rewritten in place. `since-last` is the one exception and is not a log: it
  replaces the single snapshot file it owns under `state_dir`, which is the whole mechanism.
- Every written path is printed in the run output and named in `DESCRIPTION.md`.
- `since-last` writes exactly one snapshot file, and only under `state_dir`.
- A test asserts that no write lands outside `state_dir` or the explicit `vault_dir`.

## State format

One JSONL file per stream at `state_dir/<stream>.jsonl`, one object per line, append-only:

```json
{"t": "2026-09-05T14:22:03Z", "v": 1, "kind": "punch", "note": "back on the API", "tag": "api"}
```

Appends open with `"a"` and write one `line + "\n"` in a single `write` call, which is atomic for a
line under `PIPE_BUF` on the platforms in scope; a partially written trailing line is tolerated on
read and skipped. A corrupt or unreadable state file degrades to "no history yet" with a warning and
never fails the run — the same absence-is-expected rule the daily Plays use for an unreadable browser.

## Testing

Mirrors the daily suite. Target roughly 150 new tests on top of the current 329.

| File | Covers |
|---|---|
| `tests/test_micro_core.py` | every module's unit behaviour: decode layers, entropy scoring, cron edge cases (DST, dom/dow OR semantics, `@daily`), token-range monotonicity, streak maths across gaps and timezones, snapshot deltas, `.git/index` parsing |
| `tests/test_micro_cli.py` | every step prints parseable JSON as its last line; a missing source warns and exits 0; `now` injection makes output byte-identical across runs |
| `tests/test_micro_package.py` | all twelve: params in `main.ts` match `PARAMETERS.json`, output schema keys match what the CLI emits, `rote play lint` clean, core copy byte-identical to the repo's |
| `tests/test_micro_safety.py` | no `urllib`/`http`/`socket`/`subprocess` import anywhere in `micro_core`; writes confined to `state_dir`/`vault_dir`; redaction holds on adversarial input; `is-it-secret` never prints a live secret |
| `tests/test_micro_perf.py` | every step ≤ 400 ms on bundled fixtures |

## Build and publish

`tools/build_micro_plays.py` generates the twelve `main.ts` + `deps.toml` from `docs/plays/_micro-spec.json`
and each Play's `DESCRIPTION.md` / `PARAMETERS.json`, exactly as `build_daily_plays.py` does for the six.
`tools/sync_plays.py` gains a `MICRO_PLAYS` list so the bundled core stays byte-identical and CI fails on
drift. `tools/build_micro_fixtures.py` writes the synthetic demo inputs.

Publish sequence, per Play: build → `rote play lint` → dry-run push → push at `0.1.0` → run it back from
its published URI with `demo=true` → paste the real output into `docs/context/micro-plays.md`.

## Out of scope, deliberately

- The leaderboard. No `/api/score` `play` column, no board page, gotcomped.com untouched.
- A real BPE tokenizer for `fits`. Stdlib has none; the estimator prints a range and states its method,
  which is honest, where a single confident number would not be.
- Packfile reading in `safe-to-commit`. Loose objects are read; a packed staged blob falls back to the
  working-tree copy and says so.
- Anything that needs a network call, a credential, or a permission dialog.
