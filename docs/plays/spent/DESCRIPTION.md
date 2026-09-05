`entry='320 lunch #food'`. That is the interaction. Three or four of those a day and you have a spend log that owes nothing to a bank, an app, a login or an export.

It reads an amount with or without a currency symbol, a label, and an optional #tag, and it keeps money in decimal arithmetic from end to end — never a float, because a float is how a total quietly becomes 4907.999999999999. The report gives you today, this month, the top categories with their share, the daily average, and — if you set a budget — where the month lands at the current rate.

Currencies are totalled apart and never converted. A made-up exchange rate would make one clean number out of two honest ones, so a month with rupees and dollars in it reports both.

- Reads: only its own log, at `state_dir/spent.jsonl`. It does not read your bank, your mail, your receipts or your files.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step, and it could not connect to a bank if it wanted to.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
- Writes: one appended line to `~/.rote-micro/spent.jsonl` (or wherever you point `state_dir`), and nothing else, ever. Appends only: nothing is deleted, truncated or rewritten in place.
- An entry it cannot read an amount out of is refused with a message that says how to write it, and the run still exits cleanly.
- Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log is not opened.

See also: `receipt-ledger`, which totals the receipt files already on your disk — a different axis on the same question. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
