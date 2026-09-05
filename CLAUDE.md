# Comped — project index

Rote Playoffs hackathon entry: three rote Plays (`session-ledger`, `comped`, `wrong-turns`) on one stdlib-only Python core, plus the gotcomped.com leaderboard (`api/` on Vercel, `leaderboard/post_score.py` in the comped Play, Postgres on Supabase). comped has **three front doors on one core**: `site/comped.sh` (no account, downloads `site/comped.tar.gz`, runs, deletes itself), `npx comped` (`npm/`, built by `tools/build_npm.py`, no node dependencies) and `site/run.sh` (the rote Play, consent screen, needs a Modiqo account). `standalone/comped.py` is the entry point all the account-free doors share; all three take the same fourteen parameters, enforced by `tests/test_standalone.py` and `tests/test_npm.py`. Submissions close 7 Sep 2026 20:00 London. Session state lives in `docs/context/`, not here.

## Context docs

| Doc | Covers |
|---|---|
| [docs/context/comped-plays.md](docs/context/comped-plays.md) | Whole project: core, Play packaging and publishing, the landing site, research, adoption. Current state, decisions, next steps. |

## Read first
- `docs/SPEC.md` — approved build spec.
- `docs/superpowers/plans/2026-09-03-comped-plays.md` — plan index; tasks in `comped-plays/part-0..6.md`.
- `docs/research/LANDSCAPE.md`, `docs/research/ROTE-FORMAT.md` — facts and verified Play format.

## Conventions
- Python ≥ 3.9 stdlib only everywhere (`comped_core/`, `api/`, `leaderboard/`); tests via `python3 -m unittest discover -s tests`.
- Commit per task, conventional messages. Never read credential files; no network calls in `comped_core/` (the only poster is `leaderboard/post_score.py`).
- Update `docs/adoption-log.md` daily once published.
- Generated, never hand-edited: `plays/*/main.ts` + `deps.toml` (`tools/build_plays.py`), `plays/*/resources/` incl. comped's `post_score.py` (`tools/sync_plays.py`), `site/docs.html` + `site/developers.html` (`tools/build_site.py`), `site/comped.tar.gz` + `.sha256` (`tools/build_dist.py`), `site/llms.txt` + `site/sitemap.xml` (`build_site.py`), `npm/` except `bin/comped.js` (`tools/build_npm.py`); `build_site.py` calls the other two, `resources/prices.json` (`tools/build_prices.py`).
- Live: https://github.com/rajkaria/comped · https://gotcomped.com (Vercel, project `comped`) · leaderboard `/leaderboard.html`, `/api/score`, `/api/leaderboard` · Supabase project `bpwmpkguhrcpxtcignzo` (functions `comped_submit`, `comped_board`) · `play.modiqo.ai/rajkaria/{comped,session-ledger,wrong-turns}` at **0.1.5**. npm package `comped` is built but **not published**; `npm publish npm/` needs Raj's own login.
