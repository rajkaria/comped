# Comped — project index

Rote Playoffs hackathon entry: **twenty-one** published rote Plays on **three** stdlib-only Python cores. `comped_core` powers the three agent-cost Plays (`session-ledger`, `comped`, `wrong-turns`); `daily_core` powers six local-machine Plays (`tab-debt`, `birthday-radar`, `app-graveyard`, `vault-pulse`, `desktop-clutter`, `receipt-ledger`); `micro_core` powers twelve micro-interaction Plays you run many times a day (`whatis`, `fits`, `is-it-secret`, `cron-when`, `punch`, `spent`, `jot`, `streak`, `last-turn`, `budget-left`, `since-last`, `safe-to-commit`). Plus the gotcomped.com leaderboard (`api/` on Vercel, `leaderboard/post_score.py` in the comped Play, Postgres on Supabase). comped has **three front doors on one core**: `site/comped.sh` (no account, downloads `site/comped.tar.gz`, runs, deletes itself), `npx comped` (`npm/`, built by `tools/build_npm.py`, no node dependencies) and `site/run.sh` (the rote Play, consent screen, needs a Modiqo account). `standalone/comped.py` is the entry point all the account-free doors share; all three take the same fourteen parameters, enforced by `tests/test_standalone.py` and `tests/test_npm.py`. Submissions close 7 Sep 2026 20:00 London. Session state lives in `docs/context/`, not here.

## Context docs

| Doc | Covers |
|---|---|
| [docs/context/comped-plays.md](docs/context/comped-plays.md) | The comped entry: `comped_core`, the three ways to run it (comped.sh, npx, the Play), publishing, the landing site, the leaderboard, adoption. |
| [docs/context/daily-plays.md](docs/context/daily-plays.md) | The six local-machine Plays on `daily_core`: format readers, demo fixtures, the safety invariants, what is published and what is left. |
| [docs/context/micro-plays.md](docs/context/micro-plays.md) | The twelve micro-interaction Plays on `micro_core`: the two Play shapes, the shared log, the one cross-core import, what is published and what is left. |

## The six daily Plays (`daily_core`)

Read-only scans of files the machine already keeps, published 5 Sep 2026 at **0.1.0** under `rajkaria`. One core, one CLI (`daily_core/cli.py`), one card renderer; each Play is a few parallel `*-read` steps plus one `*-report` step. Format readers are written from scratch and stdlib-only: Chrome SNSS command logs, Firefox mozlz4 (an LZ4 block decoder), Safari/Arc stores, vCard, Mach-O architecture headers, and PDF text with ToUnicode CMap decoding and text-matrix line reconstruction.

| Play | Answers | Sources |
|---|---|---|
| `tab-debt` | how many tabs are open and how old the oldest is | Chrome-family SNSS, Firefox, Safari, Arc |
| `birthday-radar` | whose birthday is next, how much of the book has none | Contacts db, vCard, CSV |
| `app-graveyard` | which apps you stopped opening, and Intel-only ones | /Applications + Spotlight + Homebrew casks |
| `vault-pulse` | orphan notes, broken links, daily-note streak | any markdown folder, Obsidian auto-detected |
| `desktop-clutter` | Desktop and Downloads by age and size, graded A-F | filesystem, hashed duplicates |
| `receipt-ledger` | what your own receipt files total, per currency | PDF, .eml, HTML, text |

Invariants enforced by `tests/test_daily_safety.py`: no network import anywhere, exactly one `subprocess.run` (`/usr/bin/mdls`, fixed argv, no shell), no credential path in any string constant, every write through `common.write_text` under `out_dir`, stdlib only, parses as Python 3.9. Every source degrades to a labelled unknown; every Play runs cold with `demo=true` against bundled fixtures.

Generated, never hand-edited: `daily_core/fixtures/` (`tools/build_daily_fixtures.py`), the six `plays/*/main.ts` + `deps.toml` (`tools/build_daily_plays.py`, reading `docs/plays/_daily-spec.json`), their `resources/daily_core/` (`tools/sync_plays.py`), their `resources/presentation-fixtures/` (`tools/build_fixtures.py`, captured from a real demo run — never a run whose `out_dir` contains a personal path, which `tests/test_fixture_privacy.py` enforces).

## The twelve micro Plays (`micro_core`)

Plays you run many times a day, published 5 Sep 2026 at **0.1.0** under `rajkaria`. A pure Play is one `report` step; a Play that remembers is `record` → `report` over one append-only JSONL log under `state_dir` (default `~/.rote-micro`). Five write — `punch`, `spent`, `jot`, `streak`, `since-last` — and are tagged `effect-local-write`, never `effect-read-only`; a test fails if that slips. No Play takes `out_dir`: these print.

| Play | Answers |
|---|---|
| `whatis` | what that opaque string is — peels JWT, base64, gzip, JSON, epoch, UUID, IP, cron, magic bytes |
| `fits` | will this fit the window, and what will it cost (token RANGE with the method printed) |
| `is-it-secret` | what to redact before you paste that, plus the redacted copy |
| `cron-when` | the next five fires in both zones, the English, and the DST trap |
| `punch` | how many times the day was broken, and the longest block you got |
| `spent` | today, this month, by category, and where the month lands |
| `jot` | the thought, appended to the vault inbox, in two seconds |
| `streak` | the run, the record, and the weekday you keep dropping |
| `last-turn` | what the turn that just finished cost, off a 256 KB tail |
| `budget-left` | how much of today's budget is gone and how fast it is going |
| `since-last` | what the agent touched, and whether anything outside the repo moved |
| `safe-to-commit` | what is staged that should not enter history — `.git/index` parsed directly, no subprocess |

Invariants enforced by `tests/test_micro_safety.py`: no `urllib`/`http`/`socket`/`subprocess` import anywhere (not even `urllib.parse` — `decode.py` carries its own percent-decoder), no `eval`/`exec`/`os.system`, the only cross-core imports are `comped_core.prices`/`pricing`/`models` in the three Plays that price tokens, writes confined to `state_dir` and `vault_dir`, and no found secret ever printed. `tests/test_micro_perf.py` fails any step over 400 ms on fixtures.

Generated, never hand-edited: `micro_core/fixtures/` (`tools/build_micro_fixtures.py`, including a git repository written byte by byte), the twelve `plays/*/main.ts` + `deps.toml` + `docs/plays/*/STEPS.md` + `PRESENTATION_FIXTURES.json` (`tools/build_micro_plays.py`, reading `docs/plays/_micro-spec.json`), their `resources/micro_core/` and, for `fits`/`last-turn`/`budget-left`, `resources/comped_core/` + `prices.json` (`tools/sync_plays.py`).

## Read first
- `docs/SPEC.md` — approved build spec.
- `docs/superpowers/plans/2026-09-03-comped-plays.md` — plan index; tasks in `comped-plays/part-0..6.md`.
- `docs/research/LANDSCAPE.md`, `docs/research/ROTE-FORMAT.md` — facts and verified Play format.

## Conventions
- Python ≥ 3.9 stdlib only everywhere (`comped_core/`, `api/`, `leaderboard/`); tests via `python3 -m unittest discover -s tests`.
- Commit per task, conventional messages. Never read credential files; no network calls in `comped_core/` (the only poster is `leaderboard/post_score.py`).
- Update `docs/adoption-log.md` daily once published.
- Generated, never hand-edited: `plays/*/main.ts` + `deps.toml` (`tools/build_plays.py`), `plays/*/resources/` incl. comped's `post_score.py` (`tools/sync_plays.py`), `site/docs.html` + `site/developers.html` (`tools/build_site.py`), `site/comped.tar.gz` + `.sha256` (`tools/build_dist.py`), `site/sitemap.xml` (`build_site.py`; `site/llms.txt` is hand-written), `npm/` except `bin/comped.js` (`tools/build_npm.py`); `build_site.py` calls the other two, `resources/prices.json` (`tools/build_prices.py`).
- Live: https://github.com/rajkaria/comped · https://gotcomped.com (Vercel, project `comped`) · leaderboard `/leaderboard.html`, `/api/score`, `/api/leaderboard` · Supabase project `bpwmpkguhrcpxtcignzo` (functions `comped_submit`, `comped_board`) · `play.modiqo.ai/rajkaria/{comped,session-ledger,wrong-turns}` at **0.1.5**; `play.modiqo.ai/rajkaria/{tab-debt,birthday-radar,app-graveyard,vault-pulse,desktop-clutter,receipt-ledger}` at **0.1.0**; `play.modiqo.ai/rajkaria/{whatis,fits,is-it-secret,cron-when,punch,spent,jot,streak,last-turn,budget-left,since-last,safe-to-commit}` at **0.1.0**, all public. npm package [`comped`](https://www.npmjs.com/package/comped) published at **0.1.5** (`npx comped`); republish with `python3 tools/build_npm.py && npm publish npm/`, which needs Raj's own login.
