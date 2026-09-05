An agent has been working. What did it touch? Not what it said it did — what actually moved on disk since the last time you asked.

The first run notes the tree and says so, rather than claiming every file in your repository is new. Every run after that gives you what was created, what changed, what was deleted, the line counts that went with it, and the biggest single change. A file whose timestamp moved but whose bytes did not is not reported as modified, because that is noise and noise is what makes a check like this stop being read.

The other half is the question people actually have, and it is answered without opening anything: `~/.ssh`, `~/.aws`, `~/.config`, `~/.gnupg`, `~/.claude`, `~/.codex` and `~/Library/LaunchAgents` are checked by directory timestamp alone. The Play can tell you something under `~/.ssh` changed while it was working, and it can tell you that having read not one byte of what is in there.

The walk is bounded and says when it hit the bound, so a partial answer is reported as a lower bound and never as a complete one. `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, `target` and their friends are skipped by default; add your own with `ignore`.

- Reads: file names, sizes, timestamps and line counts under `root`; file contents only far enough to count newlines and to notice a NUL byte, which makes a file binary and its line count unreported rather than invented. The sensitive directories are read by timestamp only.
- Never reads: any credential, keychain or token file. It notices that `~/.ssh` changed; it never looks inside it.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. Your file names never leave the machine.
- Writes: one snapshot file per watched folder under `state_dir`, and nothing else, ever. Nothing in `root` is modified, moved or deleted — this Play has no way to change your tree, only to describe it.
- Runs cold: set `demo=true` to compare a bundled tree against a bundled earlier snapshot, in a temporary folder. Your own state is not touched.

See also: `safe-to-commit`, which reads what is staged rather than what changed, and `last-turn`, which prices the turn that did the changing. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
