You set a number you are willing to spend on agents today. This tells you how much of it is gone, how fast you are burning it, and whether you are going to hit the cap before the day ends.

Today's spend is priced from the transcripts the agents already write, by tail, the same way `last-turn` does it, so it is cheap enough to check between tasks. The burn rate is measured from your first turn of the day rather than from midnight, because an hour you were not working is not an hour you were spending. The crossing time is only ever printed when the crossing happens today: "about 16:40" for a moment eighteen days away would read as this afternoon and mean nothing, so instead it says the cap is not today's problem at this rate.

A day with nothing billed says so, rather than dividing by zero and inventing a rate.

- Reads: `*.jsonl` transcripts under `claude_dir` and `codex_dir`, tails only, up to three directories deep. Only files touched in the last two days are opened at all.
- Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Your plan, your invoice and your account balance are never consulted — this is arithmetic over your own logs, not a billing integration.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
- Writes nothing. The budget is a parameter, not a stored setting; nothing is kept between runs.
- No message text is read or printed. Only usage blocks, model ids and timestamps.
- Runs cold: set `demo=true` to read bundled synthetic transcripts with nothing configured.

See also: `last-turn` for the turn that just finished, and `comped` for what the month actually came to. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
