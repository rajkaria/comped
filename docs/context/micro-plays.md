---
feature: micro-plays
globs:
  - micro_core/**
  - plays/whatis/**
  - plays/fits/**
  - plays/is-it-secret/**
  - plays/cron-when/**
  - plays/punch/**
  - plays/spent/**
  - plays/jot/**
  - plays/streak/**
  - plays/last-turn/**
  - plays/budget-left/**
  - plays/since-last/**
  - plays/safe-to-commit/**
  - docs/plays/_micro-spec.json
  - tests/test_micro_*.py
  - tools/build_micro_plays.py
  - tools/build_micro_fixtures.py
updated: 2026-09-05
---

# Micro Plays — session context

Twelve rote Plays you run *many times a day*, on a third stdlib-only core (`micro_core`), entirely
separate from `comped_core` and `daily_core`. Built and published 5 Sep 2026. The comped entry is
[comped-plays.md](comped-plays.md); the six once-a-day scanners are [daily-plays.md](daily-plays.md).

Spec: `docs/superpowers/specs/2026-09-05-micro-plays-design.md`.
Plan: `docs/superpowers/plans/2026-09-05-micro-plays.md`.

## Current state — what's working, deployed, broken

**All twelve are published, public, and verified running from the registry.** Pushed at `0.1.0` and republished at `0.1.1`
under the `rajkaria` personal namespace (this account still has no orgs). Each was linted, dry-run,
pushed, then executed through its published URI with `demo=true` **from an empty scratch
directory**, which is what proves the package is self-contained.

| Play | URI | Answers | Effect |
|---|---|---|---|
| `whatis` | `play.modiqo.ai/rajkaria/whatis@0.1.1` | what that opaque string is, and what is inside it | read-only |
| `fits` | `play.modiqo.ai/rajkaria/fits@0.1.1` | will this fit the window, and what will it cost | read-only |
| `is-it-secret` | `play.modiqo.ai/rajkaria/is-it-secret@0.1.1` | what to redact before you paste that | read-only |
| `cron-when` | `play.modiqo.ai/rajkaria/cron-when@0.1.1` | the next five fires, in both zones, and the DST trap | read-only |
| `punch` | `play.modiqo.ai/rajkaria/punch@0.1.1` | how many times the day was broken | local write |
| `spent` | `play.modiqo.ai/rajkaria/spent@0.1.1` | today, this month, and where the month lands | local write |
| `jot` | `play.modiqo.ai/rajkaria/jot@0.1.1` | the thought, into the vault inbox, in two seconds | local write |
| `streak` | `play.modiqo.ai/rajkaria/streak@0.1.1` | the run, the record, and the weekday you drop it | local write |
| `last-turn` | `play.modiqo.ai/rajkaria/last-turn@0.1.1` | what the turn that just finished cost | read-only |
| `budget-left` | `play.modiqo.ai/rajkaria/budget-left@0.1.1` | how much of today's budget is gone, and how fast | read-only |
| `since-last` | `play.modiqo.ai/rajkaria/since-last@0.1.1` | what the agent touched, and whether anything outside the repo moved | local write |
| `safe-to-commit` | `play.modiqo.ai/rajkaria/safe-to-commit@0.1.1` | what is in the staged set that should not go into history | read-only |

Verified output, from the published URIs, run in `/tmp`:

```
whatis           3 layers deep: base64 → gzip → jwt · expires in 119d
fits             9.5k–12.8k tokens · 6% of a 200k window · $0.0474–$0.0641 on claude-opus-5
is-it-secret     do not paste this: 3 live credentials in it
cron-when        every weekday at 09:30 — next Mon 09:30 IST (04:00 UTC)
punch            2 switches today · longest block 6h 33m · 14-day streak
spent            4908.00 INR this month · travel is 48%
jot              1 today · 6 this week · 6 in the inbox · 1-day streak
streak           water: 14-day streak · longest 14
last-turn        that turn: 6.5k in / 227 out · 14% cached · $0.01 · $0.17 today
budget-left      $0.17 of $10.00 · burning $0.02/h · not today at this rate
since-last       2 files touched · +4 / −0 lines · nothing outside the repo
safe-to-commit   4 staged files · 2 blockers: connection-string in config/dev.env
```

- **Tests: 516 in the repo, all passing** (`python3 -m unittest discover -s tests`), 187 of them new
  across `test_micro_core`, `test_micro_cli`, `test_micro_package`, `test_micro_safety`,
  `test_micro_perf`.
- **All twelve pass `rote play lint`** (path form: `rote play lint ./plays/<slug>`; the bare name
  form only resolves installed Plays).
- **Branch `claude/plays-micro-interactions-2dbab6`** also carries the merge of
  `claude/publish-plays-daily-activities-122fcf`, so one branch holds all twenty-one Plays. No PR yet.

## Why this shape, and what it cost

A registry survey over 27 queries on 5 Sep found the small-fast category **empty**: no public Play
for decode, quick capture, habit streak, expense log, context switch, unit conversion or token
sizing, among 821 mostly once-a-day repo reports. The reason is a design problem rather than an
oversight — a Play you run twice needs a reason to be run the second time — so five of the twelve
append to a local log and report on the accumulation, and the tenth run is worth more than the first.

Nine modules, twelve Plays: `punch`/`spent`/`jot`/`streak` are four thin CLIs over one `store.py`,
and `last-turn`/`budget-left` share `turn.py`.

## Decisions taken

- **No leaderboard.** `/api/score`, the Supabase functions and gotcomped.com are untouched. Every
  Play prints its own shareable line; nothing posts anywhere. Generalising the board with a `play`
  column stays available as a separate piece of work.
- **A third core, not a third family inside an existing one.** `micro_core` has its own ~200-line
  `common.py` rather than importing `daily_core.common`. Three cores, zero coupling, so a change to
  one family cannot move a number in another.
- **One cross-core import, deliberately.** `fits`, `last-turn` and `budget-left` bundle
  `comped_core` for `prices.rate_for` / `pricing.usd_for` and `resources/prices.json`. A second
  price list would drift. `tests/test_micro_safety.py` asserts those three modules are the *only*
  cross-core imports anywhere in `micro_core`.
- **One step if pure, two if it remembers.** A `log` Play is `record` → `report`, sharing the state
  file. A `fn` Play is a single `report` step: a second step would need a scratch file for the
  halves to talk through, and a Play that claims to write nothing should not write one to prove it.
- **`effect-local-write`, declared loudly.** The five writers are tagged that way and never
  `effect-read-only`; `test_micro_package.py` fails if a writer carries the read-only tag. `rote
  play lint` accepts the term.
- **No `out_dir`.** These print. The only things that touch disk are the four log streams, `jot`'s
  vault line, and `since-last`'s snapshot.
- **No `urllib.parse` either.** `decode.py` carries its own forty-line percent-decoder and URL
  splitter, so "imports no `urllib`, `http`, `socket` or `subprocess`" is a claim with no exception
  and `grep` settles it in a second.
- **No subprocess in `safe-to-commit`.** `.git/index` v2/v3 is parsed directly and loose objects are
  read with `zlib`. A v4 index is declined by name; a packed blob falls back to the working-tree
  copy and says so in the output.

## Known limits, deliberate and documented

- **`fits` estimates tokens, and says so.** The stdlib has no tokenizer, so it prints a range from a
  stated character-class model with the method in the same output. Exact bytes, lines and words are
  facts; the token figure is bracketed, never asserted.
- **`last-turn` and `budget-left` read tails, not history.** 256 KB off the end of the newest
  transcript, and the card says "a tail, not an accounting" so a partial number is never mistaken
  for a total. `comped` remains the Play that reads everything.
- **`since-last` sees a directory, not a system.** It watches `root` plus the *mtimes* of `~/.ssh`,
  `~/.aws`, `~/.config`, `~/.gnupg`, `~/.claude`, `~/.codex` and `~/Library/LaunchAgents`. It can
  say something under `~/.ssh` moved; it cannot say what, and it never opens it.
- **`safe-to-commit` cannot read a packfile.** Loose objects only; a packed staged blob is read from
  the working tree and named in `from_worktree`.
- **The demo git fixture ships as `dot-git`, not `.git`.** A nested `.git` directory would be read
  as a gitlink and never committed. `gitindex.git_dir` accepts `.git` (directory), `.git` (a
  `gitdir:` pointer file) and `dot-git`, and says why in its docstring.
- **Two-step Plays in demo mode do not share a state dir.** `record` and `report` each seed their
  own temp copy of the bundled log, which is right for a demo (your own log is never opened) and is
  not how a real run behaves.

## Next steps, in order

1. Open the PR for `claude/plays-micro-interactions-2dbab6` — it carries the six daily Plays as well.
2. Add the twelve to `docs/adoption-log.md` and watch the download counts against the six.
3. If the numbers justify it: generalise `/api/score` with a `play` column so `punch`, `spent`,
   `streak` and `last-turn` can post. Deliberately out of scope for 0.1.0.
4. Consider a `micro` front door on gotcomped.com, or leave the site to comped. Not decided.
