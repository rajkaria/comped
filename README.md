# Comped

> Every coding session on your machine already wrote down what it consumed. This reads it and gives you one card: what the last 30 days would have cost at API list price, the multiplier against the plan you actually pay for, the jobs you keep re-asking your agent, and what each repeat would cost as a Play.

![The comped card, rendered from the bundled synthetic fixtures](docs/screenshots/comped-card-fixtures.png)

*Rendered from the synthetic fixtures in this repo, so the numbers are small. On real logs they are not.*

**Site and docs:** [gotcomped.com](https://gotcomped.com/) · [full docs](https://gotcomped.com/docs.html)

## What it does

Three rote Plays on one stdlib-only Python core:

| Play | What it gives you |
|---|---|
| [`session-ledger`](docs/plays/session-ledger/DESCRIPTION.md) | One deduplicated ledger of usage records, human messages and tool calls from Claude Code (including subagents), Codex, Pi and OpenCode. The primitive other session Plays should read instead of re-parsing logs. |
| [`comped`](docs/plays/comped/DESCRIPTION.md) | The card: list-price total, multiplier vs your plan, cache-read share, delta since your last run, repeat offenders with the `/play settle` command to capture each, and the Rote dividend at 98% and 80%. Markdown report, SVG and PNG card, share text, and your rank on the [gotcomped.com leaderboard](https://gotcomped.com/leaderboard.html). |
| [`wrong-turns`](docs/plays/wrong-turns/DESCRIPTION.md) | Your agent's recurring mistakes — tool errors, your corrections, reverts — with recovery cost, one redacted line of evidence per class, and drafted `CLAUDE.md` / `AGENTS.md` rules it never applies for you. |

## How it works

1. **Read.** One step per harness, in parallel. Claude Code writes one line per content block, so roughly four in ten usage lines are streaming duplicates of the same API call; they are collapsed on `(message.id, requestId)`. Codex writes cumulative counters, so per-turn values are differences. Subagent transcripts live in a subdirectory and are counted. A missing harness is an expected absence, not an error.
2. **Merge.** The reads join into one ledger and every record and tool event is bound to the human message that started its turn.
3. **Price.** `usd = uncached_input×in + cache_write×cw + cache_read×cr + output×out`, in `Decimal`, against a bundled price table that names its source, upstream sha and as-of date. A model the table does not know is reported with its token counts and never priced by guess.
4. **Read back.** Repeat asks are clustered (Jaccard ≥ 0.5 on 2-shingles, qualifying at ≥ 3 asks across ≥ 2 sessions and ≥ 2 days) and priced; recurring mistake classes are drafted into rules. Every number has a line in `comped-explain.txt` showing the arithmetic that produced it.

## Getting started

Try it on the bundled synthetic logs first — no configuration, nothing of yours read:

```bash
rote play run https://play.modiqo.ai/rajkaria/comped claude_dir=resources/fixtures/claude codex_dir=resources/fixtures/codex
```

Then on your own. There are three ways in, and they run the same code on the same parameters.

**One paste, no account, nothing installed.** Downloads ~40 KB of stdlib Python to a temporary
directory, runs it, deletes it:

```bash
curl -fsSL https://gotcomped.com/comped.sh | sh
```

**With node.** The same Python in an npm wrapper, no node dependencies, no install script:

```bash
npx comped
```

**As an inspectable rote Play.** A consent screen listing every file it touches, and a public
archive you can read first. Needs a free Modiqo account:

```bash
curl -fsSL https://gotcomped.com/run.sh | sh
```

Add `handle=yourname` for a name on the board instead of `anon-xxxx`, or `leaderboard=false` for
the card alone with no network call at all. With rote already installed:
`rote play run https://play.modiqo.ai/rajkaria/comped handle=you`.

### From the coding agent you already have

Don't open a terminal. Paste this at Claude Code, Codex, Cursor or anything else with a shell:

```
Fetch https://gotcomped.com/llms.txt and do what it says.
```

[`llms.txt`](site/llms.txt) is the briefing written for the agent instead of for you: what comped reads and refuses to read, the three ways to run it in the order to try them, the rule that it must ask you before your score goes on any board, the output contract, and how to read the card back to you. The path it takes needs no account and installs nothing: `git clone --depth 1`, then one `python3` command.

### With nothing but python3

```bash
git clone --depth 1 https://github.com/rajkaria/comped && cd comped
python3 -m comped_core run --out-dir ~/comped        # read, price, cluster, render
python3 leaderboard/post_score.py --out-dir ~/comped --handle you   # optional, and the only thing that sends
```

`run` is the four steps the Play runs, in one process, calling the same functions in the same order. The steps are still there on their own (`ledger`, `price`, `repeats`, `card`, plus `wrongturns` and `rules`); every command prints one JSON object as its last line and exits 1 if that object says `ok: false`.

## Built with

- **rote** (Modiqo) — the Plays are rote Flows; every step is a shell command whose stdout is one JSON object.
- **python3 stdlib only**, ≥ 3.9. No pip installs, no node, no lockfile. `Decimal` for money, `unittest` for tests.
- **A bundled LiteLLM price snapshot**, regenerated by `tools/build_prices.py`, which records the source URL, the upstream file's sha256 and the date it was taken.

## Methodology

The full derivation — record model, per-record pricing, deduplication, windows and plan proration, the price table, repeat clustering and wrong-turn signals — is [SPEC §7](docs/SPEC.md#7-the-core-math). Two claims worth stating here:

- **List price is not a bill.** It is what the same tokens would have cost on the API at the table's published rates. Your plan is a subscription; the multiplier is the ratio, nothing more.
- **Nothing is typed.** Which AI you run comes out of the model ids in the logs; every tier those providers sell is priced at once and the assumed row is the least flattering one. The tool refuses to read your OAuth files to discover your account.

Token totals for Claude Code are checked against [ccusage](https://github.com/ryoppippi/ccusage) in CI, per model, under identical deduplication.

## Privacy

Reads: session logs under the configured directories. Nothing else. Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file; which AI you run is inferred from the model ids in those logs, never from your account. Never sends from the core: reading, pricing and rendering make no network calls (`tests/test_no_network.py`). The one step that does is `comped`'s `post_score`, which sends the score to the gotcomped.com leaderboard after the card is written; `leaderboard=false` skips it. Writes: only under `out_dir`, every path listed in the report. Message text: truncated to 120 characters and hashed by default.

Enforced by tests, not just promised: the suite fails if `comped_core` imports `urllib`, `http`, `socket`, `requests` or `ssl`, if any module other than the PNG renderer mentions `subprocess`, or if any source line references a credential path.

## Known limitations

- **Pi and OpenCode adapters are best-effort.** Their schemas came from public documentation and fixtures, not from an installed client on the machine that wrote this. Each labels itself as such in its source note.
- **PNG needs a renderer.** `rsvg-convert` or macOS `qlmanage`. Without one the SVG is still written and the step says so instead of failing.
- **`gpt-5.5-codex` is unpriced** until the upstream table carries it, as are any other models absent from the snapshot. They appear with token counts under "unpriced" and are never estimated.
- **Windowing is by each record's own timestamp**, so a session that spans the window boundary contributes only the records inside it.

## Development

```bash
python3 -m unittest discover -s tests -v   # 165 tests
python3 tools/sync_plays.py --check        # Plays bundle a byte-identical core
```

## Links

- [`docs/SPEC.md`](docs/SPEC.md) — the build spec, including the math and the output design.
- [`VISION.md`](VISION.md) — where this goes after the week it was built in.
- [`docs/research/LANDSCAPE.md`](docs/research/LANDSCAPE.md) — what already exists, measured rather than assumed.
- Plays: `play.modiqo.ai/rajkaria/session-ledger`, `/comped`, `/wrong-turns`.

## License

MIT
