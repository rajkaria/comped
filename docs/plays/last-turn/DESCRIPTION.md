The turn just finished. What did it cost? Not this month, not this project — that one turn, ninety seconds ago. Model, tokens in, tokens out, how much of the input was cache, the dollars, and today's running total underneath it.

The reason this can run twenty times a day is that it does not read your history. It finds the most recently modified transcript under the directories you configure and reads the last 256 KB of it — a tail, not an accounting, and the output says exactly that so nobody mistakes a partial number for a total. `comped` is the Play that reads everything and prices a month; this is the one you can afford to run between turns.

It reads Claude Code and Codex transcripts. Codex reports running totals rather than per-turn ones, so the turn is the difference between consecutive records, and a total that went down is treated as a new session rather than as a negative turn. Codex also names the model once at the top of the session, so when the file is long enough that the model would fall outside the tail, the head is read for that one fact. A record in a format this does not know is skipped and counted, and the count is in the output, so an unread format shows up as a number rather than as a silent zero.

Prices come from the same maintained table `comped` uses. A model the table does not know is reported by name with its tokens and no dollar figure, because no number is better than a wrong one.

- Reads: `*.jsonl` transcripts under `claude_dir` and `codex_dir`, tails only, up to three directories deep. Two directories that turn out to be the same directory are read once, not twice.
- Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Which model you ran is taken from the model ids already in the transcript; your plan and your account are never consulted.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. Your transcripts are read, priced and printed on this machine.
- Writes nothing. No state, no cache, no output file.
- No message text is read or printed. Only the usage blocks, the model ids and the timestamps are touched.
- Runs cold: set `demo=true` to read bundled synthetic transcripts with nothing configured.

See also: `budget-left` for what today has left in it, `comped` for the month and the multiplier, and `session-ledger` for the normalized ledger underneath both. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
