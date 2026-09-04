Rote asks you to keep one wrong turn in every Play as proof a human was steering. Your logs already hold hundreds. This reads Claude Code and Codex transcripts and finds three kinds: tool calls that returned an error, the message where you corrected the agent, and reverts. It groups them into recurring mistake classes by tool and error signature, counts how often each recurred across sessions and days, prices what the recovery cost in tokens, and shows one redacted line of evidence per class. For every class that recurred three or more times it drafts the rule that would have prevented it, in a block you can paste into CLAUDE.md or AGENTS.md, and labels each draft with the confidence of the signal behind it: tool errors are high, phrase-detected corrections are medium, and it never upgrades a guess. It writes the draft next to the report and never edits your rules files. Read-only, no credentials, no network, python3 only. Point claude_dir at resources/fixtures/claude to see a full run on synthetic logs first.

- Reads: session logs under the four configured directories. Nothing else.
- Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Plan is typed by you.
- Never sends: no network calls of any kind. Verifiable: the core imports no `urllib`, `http`, `socket`, `subprocess` (except the PNG renderer, which is invoked with a fixed argv and no shell).
- Writes: only under `out_dir`. Every written path is listed in the report.
- Message text: truncated to 120 chars and hashed by default. `redact=false` keeps full text locally, never in the card.

See also: `session-ledger` (the normalized ledger this reads) and `comped` (prices it and finds your repeat asks). Docs, the full methodology and a worked example: https://gotcomped.com
