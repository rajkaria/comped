"""micro_core — twelve Plays you run many times a day, on one stdlib-only core.

Two rules hold everywhere in this package, and everything else follows from them:

1. A step prints human text, then exactly one JSON object as its last line, and nothing else on
   stdout. The presentation plane splits on that line.
2. An absence is expected. No history yet, no transcript, no vault: the step says so, prints
   `{"ok": true, "warning": ...}` and exits 0. Nothing here raises at a user.
"""
