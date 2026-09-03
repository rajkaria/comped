# Comped

> Read the agent session logs already on your disk and get one card: what your week of Claude Code and Codex would have cost at API list price, the multiplier against the plan you actually pay for, the jobs you keep asking your agent to redo, and what each one would cost as a Play.

Three rote Plays on one stdlib-only Python core:

| Play | What it gives you |
|---|---|
| `session-ledger` | One deduplicated ledger of usage records, human messages and tool calls from Claude Code (incl. subagents), Codex, Pi and OpenCode. The primitive other session Plays should read. |
| `comped` | The card: list-price total, multiplier vs your plan, cache share, delta since last run, repeat offenders with the `/play settle` command to capture each, Rote dividend at 98% and 80%. SVG and PNG card, share text. |
| `wrong-turns` | Your agent's recurring mistakes (tool errors, corrections, reverts), their recovery cost, and drafted CLAUDE.md / AGENTS.md rules. |

Read-only. No credentials. No network. Writes only under the folder you choose.

Status: **specified, not yet built.** Start with [docs/SPEC.md](docs/SPEC.md), then the implementation plan at [docs/superpowers/plans/2026-09-03-comped-plays.md](docs/superpowers/plans/2026-09-03-comped-plays.md). Research behind every decision is in [docs/research/LANDSCAPE.md](docs/research/LANDSCAPE.md).

## Try it on synthetic logs first

```bash
rote play run https://play.modiqo.ai/<handle>/comped claude_dir=resources/fixtures/claude codex_dir=resources/fixtures/codex plan=claude-max-200
```

## Privacy

Reads: session logs under the configured directories. Nothing else. Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file; plan is typed by you. Never sends: no network calls of any kind. Writes: only under `out_dir`, every path listed in the report. Message text: truncated to 120 characters and hashed by default.

## License

MIT
