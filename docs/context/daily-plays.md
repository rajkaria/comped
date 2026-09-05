---
feature: daily-plays
globs:
  - daily_core/**
  - plays/tab-debt/**
  - plays/birthday-radar/**
  - plays/app-graveyard/**
  - plays/vault-pulse/**
  - plays/desktop-clutter/**
  - plays/receipt-ledger/**
  - docs/plays/tab-debt/**
  - docs/plays/birthday-radar/**
  - docs/plays/app-graveyard/**
  - docs/plays/vault-pulse/**
  - docs/plays/desktop-clutter/**
  - docs/plays/receipt-ledger/**
  - docs/plays/_daily-spec.json
  - docs/research/PLAY-IDEAS.md
  - tests/test_daily_*.py
  - tools/build_daily_plays.py
  - tools/build_daily_fixtures.py
updated: 2026-09-05
---

# Daily Plays — session context

Six read-only rote Plays over files the machine already keeps, on a second stdlib-only core
(`daily_core`) that is entirely separate from `comped_core`. Built and published 5 Sep 2026.
The comped entry (`session-ledger`, `comped`, `wrong-turns`) is a different feature doc:
[comped-plays.md](comped-plays.md).

## Current state — what's working, deployed, broken

**All six are published, public, and verified running from the registry.** Pushed at `0.1.0`
under the `rajkaria` personal namespace (no orgs exist on this account). Each was dry-run first,
pushed, inspected, then executed through its published URI with `demo=true` and, for
`desktop-clutter`, against real machine data as well.

| Play | URI | Answers |
|---|---|---|
| tab-debt | `play.modiqo.ai/rajkaria/tab-debt@0.1.0` | how many tabs are open, how old the oldest is |
| birthday-radar | `play.modiqo.ai/rajkaria/birthday-radar@0.1.0` | whose birthday is next, how much of the book has none |
| app-graveyard | `play.modiqo.ai/rajkaria/app-graveyard@0.1.0` | apps you stopped opening; Intel-only bundles |
| vault-pulse | `play.modiqo.ai/rajkaria/vault-pulse@0.1.0` | orphan notes, broken links, daily-note streak |
| desktop-clutter | `play.modiqo.ai/rajkaria/desktop-clutter@0.1.0` | Desktop and Downloads by age and size, graded A–F |
| receipt-ledger | `play.modiqo.ai/rajkaria/receipt-ledger@0.1.0` | what your own receipt files total, per currency |

- **Tests: 329 in the repo, all passing** (`python3 -m unittest discover -s tests`), 118 of them new.
- **All six pass `rote play lint`** with runtime checks, sidecars committed.
- **Verified on real data on this Mac.** 62 tabs across 6 browsers, oldest last used 21 months ago.
  22 applications, 4 unopened past 180 days. 1,724 Desktop+Downloads files, grade F, 164 hashed
  duplicate groups. 13 real receipts found among 168 candidate files in Downloads.
- **Merged to `main`** at `2c35002` (fast-forward, no PR). CI green on all five jobs: Ubuntu and
  macOS on Python 3.9 and 3.12, plus the Windows standalone job.
- **Working tree clean.** The test suite regenerates `npm/` and `site/comped.tar.gz`; they match.

Known limits, deliberate and documented in each DESCRIPTION.md:

- Safari, Contacts and Mail are TCC-protected on this machine. Those sources report
  "grant Full Disk Access" by name rather than reporting zero. `os.access` is useless here
  because TCC does not touch the permission bits, so the code calls `iterdir`/`listdir` and
  catches `PermissionError` instead.
- 69 of 157 Downloads PDFs decode to glyph codes their fonts do not map. Those are declared
  unreadable rather than guessed at (a legibility gate below 0.75 refuses the text).
- `app-graveyard` last-used dates come from Spotlight where it answers and file access time
  otherwise; every row says which. On this machine Spotlight answered 9 of 22.

## Recent changes — files touched and why

**New core** — `daily_core/`:
- `common.py` — the three rules enforced once: bounded traversal (`Budget`), a source that cannot
  be read becomes a labelled unknown (`Source`, `envelope`), and nothing is opened for writing
  outside `out_dir` (`write_text`). Also SQLite copy-then-open-read-only, epoch conversion for
  Chrome/Apple/Unix, display-width truncation, URL and name redaction.
- `card.py` — one 64-column box card shared by all six, padded on display width.
- `cli.py` — twelve subcommands: `<play>-read` (one per source) and `<play>-report`.
- `scan/{tabs,contacts,apps,notes,clutter,receipts}.py` — one module per Play: `read_source`,
  `analyse`, `render`, `report_markdown`.
- `parsers/` — `snss.py` (Chrome command log replay), `mozlz4.py` (LZ4 block decoder + Firefox),
  `applesafari.py`, `arcsidebar.py`, `vcard.py`, `machoarch.py`, `pdftext.py`.
- `fixtures/` — generated, never hand-edited.

**Generators** — `tools/build_daily_fixtures.py` (deterministic demo fixtures at a fixed clock,
including a hand-built SNSS file and a hand-built PDF), `tools/build_daily_plays.py` (main.ts +
deps.toml from `docs/plays/_daily-spec.json`), `tools/sync_plays.py` (extended: `DAILY_PLAYS`
copies `daily_core` into each package and `--check` proves byte identity).

**Docs** — `docs/plays/<slug>/{DESCRIPTION.md,PARAMETERS.json,STEPS.md,PRESENTATION_FIXTURES.json}`
for all six, plus `docs/plays/_daily-spec.json` as the DAG/tags/output source, plus
`docs/research/PLAY-IDEAS.md` (the registry survey that picked these six).

**Tests** — `tests/test_daily_parsers.py` (38, each with a negative half), `test_daily_cli.py`
(11, every Play end to end in demo mode), `test_daily_scan.py` (44, exact fixture numbers),
`test_daily_package.py` (15, frontmatter/parameter parity and argv actually parsing),
`test_daily_safety.py` (10, the static proofs).

## Key decisions — choices and trade-offs, why X over Y

- **A second core, not an extension of `comped_core`.** Nothing is shared. `comped_core` is agent
  session accounting; `daily_core` is local file state. Mixing them would have made both harder
  to reason about and would have broken the existing no-subprocess invariant.
- **Subprocess is allowed in exactly one place.** `scan/apps.py` calls `/usr/bin/mdls` with a
  fixed argv and no shell, because Spotlight is the only source of a real last-opened date.
  `test_daily_safety.py` parses the AST to prove there is exactly one `subprocess.run`, that
  `shell=` is never set, and that the binary is the `MDLS` constant.
- **Degrade, never fail, and say which.** Every source returns `Source(found=..., note=...)`.
  A step that read nothing still exits 0 with a `warning` in its JSON. The alternative, a run
  that dies because Safari is protected, would make the Play useless to a stranger.
- **Bounds are reported, not hidden.** `Budget` records which limit it hit and `envelope` turns
  that into "counts are a lower bound". A partial answer must never read like a complete one.
- **Demo fixtures are generated, not copied from this machine.** Reproducible byte for byte,
  nothing personal can leak, and the binary formats get exercised by the same readers a real run
  uses. `clutter` and `apps` read a JSON manifest in demo mode because a git checkout stamps every
  file with the checkout time and every age would read "today".
- **The generated copies under `plays/*/resources/` are gitignored, not committed.** The six
  packages were briefly tracking their own copy of `daily_core`, 276 files of duplication. They now
  follow the same rule as `comped_core`: CI regenerates them with `tools/sync_plays.py`. Any test
  that reads a package's core must sync first, which `tests/test_daily_package.py` does in
  `setUpModule`. The lint sidecars are gitignored too, so that assertion skips when absent.
  Verify changes like this in a clean clone, because a working tree hides exactly this class of bug.
- **Presentation fixtures must be captured from a run whose `out_dir` has no personal path.**
  The first capture used a scratchpad path containing the username and
  `tests/test_fixture_privacy.py` caught it. Capture with `out_dir=/tmp/daily-demo/<slug>`.
- **`receipt-ledger` requires positive evidence.** An amount on a total line is enough on its own;
  otherwise two distinct receipt phrases are required, and a phrase introduced by a negation does
  not count. Before this gate, pitch decks with big dollar figures were being totalled.
- **Currencies are never summed across each other.** Per-currency totals only.
- **PDF text is reconstructed from the text matrix.** Splitting on positioning operators produced
  one character per line. A pen-tracking state machine with per-character width estimates gives
  real lines; ToUnicode CMap decoding took readable PDFs from 41 to 85 of 157.
- **Published public.** The three existing plays are public in the same namespace and a Playoffs
  submission has to be public to count.

## Next steps — specific, actionable

1. **Announce the six.** The X and Discord posts from the earlier session covered comped only.
   `desktop-clutter` (grade F, 164 duplicate groups) and `tab-debt` (oldest tab 21 months) are the
   two with a number worth posting.
2. **Decide whether the leaderboard generalises.** `api/score` and the Supabase functions are
   comped-shaped. Adding a `play` column would let `tab-debt`, `desktop-clutter` and
   `app-graveyard` post a score too. This is the largest remaining piece of work and it is
   optional.
3. **Consider a landing-page section** on gotcomped.com for the six, or leave the site
   comped-only. Currently the site says nothing about them.
4. **Watch adoption.** `rote play search --source registry` and `docs/adoption-log.md`.
5. **Optional recall work on `receipt-ledger`.** The 69 unreadable PDFs would need per-font
   encoding tables beyond ToUnicode. Only worth it if downloads suggest people care.
