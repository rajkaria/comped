Every editor and every dashboard shows commit times in whatever zone this machine is set to today, which quietly rewrites your history every time you travel or change laptops. Git records the committer's own UTC offset inside the timestamp, so a commit made at 04:12 in Tokyo is a 04:12 commit for ever. This reads that offset intact and answers, from the record rather than from memory, how much of your work lands after midnight.

Every git repository under a root you choose, read through one fixed, read-only `git` command line. Every hour, weekday and calendar date on the card is the wall clock the committer's own offset encodes, never this machine's idea of local time. Commits are matched to you by the addresses git already knows, plus any others you name.

The distributions are the easy half. The half worth having is the correlation: for late commits against the rest, how often a commit was later reverted, how often a fix-up followed it within the hour, and how long its subject line was — three recorded facts, each printed with its denominator beside it, which is the only reason they belong on a card at all. You also get the weekend count, the longest unbroken run of days, and the stretches that were rebased, reported rather than straightened out.

Two things this deliberately does not do. It does not interpret: these are counts of commits, they are not a measure of health, sleep, wellbeing or output quality, and nothing here offers advice. And it does not guess at a time zone: when more than one UTC offset appears in the window the card says so, because a fortnight abroad and a changed routine look identical in an hour histogram and only one of them is about your schedule.

- Reads: git repositories under `root`, through `git log` and its read-only siblings. No working-tree file is opened and nothing outside `root` is looked at.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. The git commands it will run are an allow-list that contains nothing able to change a repository — no commit, no checkout, no fetch, no clean.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a repository with no commits, a missing git, a directory that cannot be read, and a shallow clone are each reported by name with the reason, and the run still completes. A scan that hits its own repository or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against a bundled synthetic commit history with nothing configured, before you point it at your own.

Requires python3 3.9 or newer, and `git` for a real run. No pip install, no node, no adapters, no credentials.
