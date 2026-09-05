A notes folder only grows. Nothing in the editor ever says which notes are load-bearing and which were written once and never opened again, so the answer is usually a feeling. Both facts are in the files: the links give the graph, the timestamps give the habit.

This reads a markdown folder, finds your Obsidian vault on its own if you do not name one, and builds the link graph from wiki links and relative markdown links together. Out of that come the notes nothing points at and that point nowhere, the notes that have inbound links but no outbound ones, the links that point at a note which does not exist, and the notes everything else points at.

Then the habit. Notes never edited after the minute they were created, notes under thirty words, notes untouched past your threshold, the count of new notes per week for the last sixteen weeks, your daily-note streak with the longest run you have ever managed, and every unchecked box in the vault with the number of notes holding them.

One caveat is built in rather than left for you to discover. If every note carries the same creation time, which is what a fresh clone or a restored backup looks like, the never-edited count is meaningless and the Play says so instead of reporting a confident hundred per cent.

Nothing is written inside the vault. The report goes to your output folder.

- Reads: only the locations listed above. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
