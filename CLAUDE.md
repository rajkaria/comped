# Comped: repository guide

Twenty-one published rote Plays on **three** stdlib-only Python cores, plus the gotcomped.com site
and leaderboard.

- `comped_core` powers the three agent-cost Plays: `session-ledger`, `comped`, `wrong-turns`.
- `daily_core` powers six read-only local-machine Plays: `tab-debt`, `birthday-radar`,
  `app-graveyard`, `vault-pulse`, `desktop-clutter`, `receipt-ledger`.
- `micro_core` powers twelve micro-interaction Plays: `whatis`, `fits`, `is-it-secret`,
  `cron-when`, `punch`, `spent`, `jot`, `streak`, `last-turn`, `budget-left`, `since-last`,
  `safe-to-commit`.

`comped` has **three front doors on one core**: `site/comped.sh` (no account, downloads
`site/comped.tar.gz`, runs, deletes itself), `npx comped` (`npm/`, built by `tools/build_npm.py`,
no node dependencies) and `site/run.sh` (the rote Play, consent screen, needs a Modiqo account).
`standalone/comped.py` is the entry point the account-free doors share; all three take the same
fourteen parameters, enforced by `tests/test_standalone.py` and `tests/test_npm.py`.

## Read first

- [`docs/SPEC.md`](docs/SPEC.md) — record model, pricing arithmetic, deduplication rules, output
  contracts, privacy statements and the testing standard. `tests/test_play_docs.py` reads it.
- [`README.md`](README.md) — what each Play does and how to run it.
- [`VISION.md`](VISION.md) — where this goes next.

## The six daily Plays (`daily_core`)

Read-only scans of files the machine already keeps. One core, one CLI (`daily_core/cli.py`), one
card renderer; each Play is a few parallel `*-read` steps plus one `*-report` step. Format readers
are written from scratch and stdlib-only: Chrome SNSS command logs, Firefox mozlz4 (an LZ4 block
decoder), Safari and Arc stores, vCard, Mach-O architecture headers, and PDF text with ToUnicode
CMap decoding and text-matrix line reconstruction.

Invariants enforced by `tests/test_daily_safety.py`: no network import anywhere, exactly one
`subprocess.run` (`/usr/bin/mdls`, fixed argv, no shell), no credential path in any string
constant, every write through `common.write_text` under `out_dir`, stdlib only, parses as
Python 3.9. Every source degrades to a labelled unknown; every Play runs cold with `demo=true`
against bundled fixtures.

## The twelve micro Plays (`micro_core`)

A pure Play is one `report` step; a Play that remembers is `record` then `report` over one
append-only JSONL log under `state_dir` (default `~/.rote-micro`). Five write: `punch`, `spent`,
`jot`, `streak`, `since-last`. They are tagged `effect-local-write`, never `effect-read-only`, and
a test fails if that slips. No micro Play takes `out_dir`: these print.

Invariants enforced by `tests/test_micro_safety.py`: no `urllib`/`http`/`socket`/`subprocess`
import anywhere (not even `urllib.parse`, so `decode.py` carries its own percent-decoder), no
`eval`/`exec`/`os.system`, the only cross-core imports are `comped_core.prices`/`pricing`/`models`
in the three Plays that price tokens, writes confined to `state_dir` and `vault_dir`, and no found
secret is ever printed. `tests/test_micro_perf.py` fails any step over 400 ms on fixtures.

## Conventions

- Python ≥ 3.9 stdlib only everywhere (`comped_core/`, `daily_core/`, `micro_core/`, `api/`,
  `leaderboard/`). Tests: `python3 -m unittest discover -s tests`.
- Commit per task, conventional messages. Never read credential files. No network calls in any
  core; the only poster is `leaderboard/post_score.py`.
- **Generated, never hand-edited:**
  - `plays/*/main.ts` + `deps.toml` — `tools/build_plays.py` (comped family),
    `tools/build_daily_plays.py` (reads `docs/plays/_daily-spec.json`),
    `tools/build_micro_plays.py` (reads `docs/plays/_micro-spec.json`).
  - `plays/*/resources/` — `tools/sync_plays.py`, including comped's `post_score.py`.
  - `*/fixtures/` — `tools/build_daily_fixtures.py`, `tools/build_micro_fixtures.py`.
  - `resources/presentation-fixtures/` — `tools/build_fixtures.py`, captured from a real demo run,
    never one whose `out_dir` contains a personal path (`tests/test_fixture_privacy.py` enforces).
  - `site/docs.html`, `site/developers.html`, `site/plays.html`, `site/sitemap.xml` —
    `tools/build_site.py`, which also calls `tools/build_dist.py` (`site/comped.tar.gz` + `.sha256`)
    and `tools/build_npm.py` (`npm/`, except the hand-written `npm/bin/comped.js`).
    `site/llms.txt` is hand-written.
  - `resources/prices.json` — `tools/build_prices.py`.

## Live

- https://github.com/rajkaria/comped · https://gotcomped.com (Vercel)
- Leaderboard: `/leaderboard.html`, `/api/score`, `/api/leaderboard`
- All twenty-one Plays: https://gotcomped.com/plays.html and `play.modiqo.ai/rajkaria/<slug>`
- npm: [`comped`](https://www.npmjs.com/package/comped). Republish with
  `python3 tools/build_npm.py && npm publish npm/`.
