Every team knows some of its code has exactly one author left and nobody knows which files those are. The facts that settle it are already in the repository — who wrote which line, when they last committed anything, and whether a second person has ever been in the file — so this reads them and does the arithmetic nobody does by hand.

Every git repository under a root you choose, read through one fixed, read-only `git` command line. A file's authors come from its whole history rather than from blame on the current text, because a person who wrote a file and was then edited over still knows it and blame has already forgotten them. Ownership is measured in lines written, which is the only size git gives without opening a working-tree file, so every count on the card says "lines written" and never "lines". Bots, vendored trees, generated code and lock files are excluded by name, and both the count kept and the count excluded are printed, because an exclusion you cannot see is an exclusion you cannot check.

You get the number of files with a single author, the largest cluster of them in one directory with the name attached, whether that name has committed anywhere in the last year, the truck factor, and the files that are both sole-authored and untouched — the ones where the knowledge and the attention have both gone. The truck factor is computed greedily, largest owner first, which makes it an upper bound on the true minimum; the card says so, because a number that can only be wrong in one direction is worth more than one that could be wrong in either.

Author names and addresses are reduced to initials unless you turn redaction off, and no address is printed in full on the card either way.

- Reads: git repositories under `root`, through `git log`, `git blame` and their read-only siblings. No working-tree file is opened and nothing outside `root` is looked at.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. The git commands it will run are an allow-list that contains nothing able to change a repository — no commit, no checkout, no fetch, no clean.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a repository with no commits, a missing git, a directory that cannot be read, and a shallow clone are each reported by name with the reason, and the run still completes. A shallow clone is reported as a lower bound, because a truncated history is exactly that. A scan that hits its own repository or time bound says so.
- Runs cold: set `demo=true` to run the whole Play against three bundled synthetic repositories with nothing configured, before you point it at your own.

Requires python3 3.9 or newer, and `git` for a real run. No pip install, no node, no adapters, no credentials.
