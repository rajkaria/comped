Every purchase leaves a file somewhere. A PDF invoice, a saved confirmation page, an exported message. None of them are ever added up, because they are four formats sitting in one folder and opening them one at a time is nobody's evening.

This reads all four. Email files are parsed with their headers, so the sender and the date are the real ones and not the file's. Saved pages are stripped to text. PDFs are decompressed and, where the fonts use their own encoding, decoded through the document's own ToUnicode table, then laid back out into lines from the coordinates each glyph was placed at, because a PDF has no concept of a line and reading one without reconstructing it gives you a column of single letters. A scanned receipt has no text at all and is reported as unreadable rather than guessed at.

A document only counts as a receipt if it says it is one. An amount sitting on a line that says total, amount due or you paid is enough on its own; otherwise the document needs at least two of invoice number, order number, subtotal, a tax line, a payment method, a transaction reference or a billing period, and a phrase introduced by a negation does not count. A pitch deck full of dollar figures is not a receipt and is excluded by name in the source note.

Totals are per currency and are never added across currencies. You get the spend by vendor and by month, the vendors that appear in three or more months, the same charge appearing in two files, and a confidence block saying how many amounts came from a total line rather than from being the largest figure on the page, and how many dates came from the file rather than the document.

Nothing logs in to anything. There is no bank, no email account and no API. It reads files you already have.

- Reads: only the locations listed above. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
