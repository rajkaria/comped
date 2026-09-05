Before you paste forty kilobytes into an agent: will it fit, and what will it cost. Point it at text or at a file and it answers both, plus the things nobody bothers to count — bytes, lines, words, and what the text actually looks like.

The bytes, lines and words are facts. The token count is not, and this Play refuses to pretend otherwise. The standard library has no tokenizer, so the count comes from a stated character-class model — ASCII prose at roughly four characters per token, punctuation-dense code nearer three, CJK at about one token per character — and it is printed as a RANGE with a band of ±15%, widened to ±25% when the text is mostly non-ASCII. The method travels in the same output as the number, so nobody has to guess how much to trust it. A single confident figure would have been easier to read and worse to rely on.

The money is real, though: the cost comes from the same maintained price table the `comped` Play prices a month with, so the rates are the ones actually charged, and a model the table does not know is named in the output instead of being priced at zero.

- Reads: the text you pass, or the file or folder at `path` (up to 200 files, 2 MB each). Nothing else.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. The price table is a JSON file bundled inside the Play; nothing is fetched at run time.
- Writes nothing. No state, no cache, no output file.
- Runs cold: set `demo=true` to measure a bundled 40 KB document with nothing configured.

See also: `last-turn`, which prices the turn that actually happened, and `budget-left`, which tells you what today has left in it. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
