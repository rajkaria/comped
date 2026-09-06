Something ate 40 GB and nothing will tell you what. Every disk tool answers the wrong question: they show what is big, and what is big is mostly what was always big. The useful question is what *moved*, and nothing can answer it without having looked before. So this Play is built around a baseline rather than a scan — one bounded walk records a directory-size snapshot, and every run after that says what changed.

It walks the tree you name with `os.scandir`, reading directory entries and `stat` results. It opens no file it measures. Sizes are on-disk sizes wherever the filesystem exposes them, so APFS clones and sparse files do not inflate the total; the apparent total is printed alongside so the gap is visible rather than silently chosen for you.

Four rules the report keeps. The first run has nothing to compare against and says exactly that: it records the baseline and tells you when to come back, rather than printing a zero delta as though the disk had stood still. Growth and shrinkage are reported in separate classes — newly appeared, grew in place, shrank in place, deleted — because a folder that vanished is not the same event as a folder that got smaller, and merging them loses the only fact worth having. The reclaim figure counts regenerable bytes only, caches and build output a command can rebuild, and is kept strictly apart from data nobody can regenerate, because a headline that mixes the two is an invitation to delete the wrong thing. And nothing is ever deleted, moved or opened.

You get the total, the folders that moved most in each direction with their names, free space, the net change since the baseline you chose, and how many past baselines are being kept.

- Reads: directory entries and `stat` results under `root`. No file it measures is ever opened.
- Never reads: file contents of any kind, and no credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. No folder name leaves this machine.
- Writes: only inside `out_dir`, which is created if missing — the report, and the baselines the next run compares against. Every written path is listed in the run output. Nothing under `root` is modified.
- Degrades, never fails: a folder that cannot be read is reported by name with the reason and the run still completes. A walk that hits its own entry or time bound says so and reports its totals as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against a bundled synthetic tree that already carries two baselines, so the comparison has something to show on the very first run.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
