The last thing between a live credential and permanent git history is you, at the moment you type commit. This reads what is actually staged and tells you what is in it: credentials, an `.env` that should not be tracked, leftover debugging, and files large enough that you will regret them for the life of the repository.

It does not run git. The index format is public and stable, so `.git/index` is parsed directly for the staged paths and their blob ids, and the blobs are read out of `.git/objects` with zlib — which means this keeps the same promise every other Play here keeps: no subprocess, no shell, nothing executed. Where a staged blob lives in a packfile rather than a loose object, the working-tree copy is read instead and the output names the files that happened to, so you know which lines were read from where. A version 4 index, whose paths are prefix-compressed, is declined by name rather than mis-parsed.

The credential detectors are the same ones `is-it-secret` uses, with the same exclusions, so `API_KEY=your-key-here` is not a finding here either. The debug detectors are deliberately narrow: `print(` counts in a `.py` file under `src/` and not in one under `scripts/`, where printing is the job; `console.log` counts only in JavaScript and TypeScript; a Go `fmt.Println` does not count in a main package. A pre-commit check that cries about everything gets bypassed within a week, and then it is protecting nothing.

The verdict is one of four words: `clean`, `review` (something is worth a look), `do-not-commit` (a live credential shape is staged), or `nothing-staged`.

- Reads: `.git/index` and the loose objects for the staged paths, plus the working-tree copy of any staged file whose blob is packed. Nothing outside `repo`.
- Never reads: your git credentials, `~/.gitconfig` secrets, any keychain or token file. It reads what you staged and nothing else.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. This is the check that reads your secrets; it is also the one with no network stack.
- Writes nothing. It does not stage, unstage, commit, amend or modify anything. It reads and reports.
- Never prints what it found. Every credential is masked to its first four and last two characters plus a length, and a test asserts the original never appears in the output.
- Runs cold: set `demo=true` to read a bundled synthetic repository — a real index and real loose objects, written byte by byte, with a fake key staged in it.

See also: `is-it-secret` for the same detectors over a paste, and `since-last` for what changed whether or not you staged it. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
