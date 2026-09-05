`did=water`. One word, several times a day, and the Play keeps the only part of habit tracking that ever changes anyone's behaviour: how long the run is, and which day you keep dropping it.

Each habit gets its current streak, its longest ever, a grid of the last twenty-one days, and — once there is enough history to say it honestly — the weekday you miss most often. Marking the same habit twice in one day is one day; the log keeps both marks, the streak counts the day.

Today not being marked yet does not end your streak. The day is not over, and a tracker that resets at midnight punishes you for checking it in the morning.

- Reads: only its own log, at `state_dir/streak.jsonl`. Nothing else on the machine.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
- Writes: one appended line to `~/.rote-micro/streak.jsonl` (or wherever you point `state_dir`), and nothing else, ever. Appends only: nothing is deleted, truncated or rewritten in place.
- The missed-weekday reading is withheld until there are at least fourteen days of history and one weekday is clearly worse than the others, because a pattern read from four days is not a pattern.
- Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log is not opened.

See also: `punch` for the hours inside a day, and `jot` for the thoughts. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
