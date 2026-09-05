Type one line saying what you are doing. That is the whole interaction, and it takes two seconds. Do it five or ten times a day and the Play starts answering a question your calendar cannot: not where the time went, but how many times the day was broken.

A punch whose topic differs from the one before it is a context switch. The report gives you today's punches with their times, how many switches there were, how long the block you are currently in has run, the longest block you managed today, a sparkline of the last fortnight, and the streak of days you have kept it up. Pass `tag=api` and the tag is the topic, so "fixing the parser" and "back on the API" count as the same thread rather than as a switch.

The number worth sharing here is the switch count, and low is good — which makes it a stranger leaderboard than most, and a more honest one. Nothing here judges you for the number; it just tells you what it was, from what you typed.

- Reads: only its own log, at `state_dir/punch.jsonl`. It does not read your calendar, your editor, your shell history or your machine.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. Nothing you type here leaves the machine.
- Writes: one appended line to `~/.rote-micro/punch.jsonl` (or wherever you point `state_dir`), and nothing else, ever. Appends only: nothing is deleted, truncated or rewritten in place, so the log is always something you can read yourself.
- A corrupt or half-written line costs itself and nothing else; the rest of the log still reports.
- Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log is not opened.

See also: `jot` for capturing a thought rather than a state, `streak` for the days rather than the hours, and `since-last`, which answers the same "what just happened" question about files. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
