Every other number a coding agent produces is about what it cost. This one is about what it was worth: of everything the agent wrote for you, how much of it is still in the file. Git already knows the answer and nobody asks it.

It reads two things. The session transcripts your agents already keep — Claude Code, Codex and Pi — for the file-writing tool calls and the times they happened, and nothing else in them: no prompt, no reply, no model name, no content. Then, in the repositories under a root you choose, one fixed read-only `git` command line for the commits and the blame that say what became of those lines.

The whole Play rests on one heuristic, and because the heuristic is arguable it is printed verbatim on the report rather than buried. Git records who *committed* a line, never who *typed* it, so a line is called the agent's when the commit that introduced it has an author time inside a session window — from the first file-writing call in that session to the last, plus a grace period. That miscounts in both directions and the two errors do not cancel. What makes the answer honest anyway is the control group: the identical computation over the same files outside every window, which is you. A survival rate with nothing to compare it against is a dunk, not a measurement, so the card prints both or it prints neither.

You get the lines ever written and the lines still alive for both, the gap between the two survival rates, where the rest went — reverted, deleted with the file, rewritten by a later edit, never committed at all — and a half-life curve with a denominator on every bucket. Everything expensive is bounded and every bound is reported, because a blame that was cut short gives a lower bound and a lower bound presented as a total is a lie.

- Reads: the session transcript folders you name, for file-write records only, and git repositories under `root` through `git log`, `git blame` and their read-only siblings.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. It does not read prompts, replies or any conversation content, and the git commands it will run are an allow-list containing nothing able to change a repository.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: an agent you do not use, a repository with no commits, a missing git and a shallow clone are each reported by name with the reason, and the run still completes. A shallow clone lowers the confidence rating on that repository's answer rather than being quietly averaged in.
- Runs cold: set `demo=true` to run the whole Play against a bundled synthetic transcript set and two synthetic repositories with nothing configured, before you point it at your own.

Requires python3 3.9 or newer, and `git` for a real run. No pip install, no node, no adapters, no credentials.
