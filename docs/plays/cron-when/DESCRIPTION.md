You have a cron expression and a suspicion. This tells you what it says in English, the next five times it actually fires — in your zone and in UTC, side by side — how often that works out to be, and whether the clocks are going to ruin it.

Two things most cron readers get wrong, and this one does not. When both day-of-month and day-of-week are restricted, a day matches if EITHER matches: `0 0 13 * 5` is the thirteenth AND every Friday, not Friday the thirteenth. And a schedule pinned to an hour that a zone skips does not fire that day at all — `30 1 * * *` in Europe/London simply does not happen on the morning the clocks go forward — so that day is not offered as a fire, and the warning says which day and why. The other side of the same coin, an hour that happens twice when the clocks go back, is reported too.

Ranges, lists, steps, wrapping ranges like `22-2`, three-letter month and day names, Sunday as both 0 and 7, and the macros `@daily`, `@hourly`, `@weekly`, `@monthly`, `@yearly` and `@midnight` all read the way cron reads them. An expression that is not valid gets a message naming the field that is wrong, and the run still exits cleanly.

- Reads: the expression you pass, and the system time-zone database. No files, no directories.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
- Writes nothing. No state, no cache, no output file.
- Runs cold: set `demo=true` to read a bundled expression with nothing configured.

See also: `whatis`, which recognises a cron expression among everything else it recognises. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
