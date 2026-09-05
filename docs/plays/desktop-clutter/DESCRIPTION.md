The Desktop and the Downloads folder are append-only in practice. Things arrive, nothing leaves, and the Finder sorts by name so the oldest file in there is invisible. Every fact needed to fix that is already in the file system.

This counts both folders, and the screenshot folder as well when you have moved it somewhere else, which it learns from the same preference macOS wrote when you changed it. You get the file count and total size, the oldest file with its date, an age histogram in both files and bytes, what the files actually are as screenshots, installers, archives, documents and media, and the biggest files with how long since each was touched.

Duplicates are proven, not guessed. Files of the same size and type are only candidates; each cluster is then hashed and only files with identical contents are reported as duplicates, and the report states which test it applied. Set hash_duplicates=false for a faster pass, and the wording changes to say the contents were not compared, because a claim you cannot support should not read the same as one you can.

It ends with a grade from A to F built from three things: how many files, how many of them are cold, and how many duplicate groups. It is the same formula on every machine, so the grade is comparable with someone else's.

Nothing is moved, renamed or deleted. Contents are read only to prove a duplicate.

- Reads: only the locations listed above. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
