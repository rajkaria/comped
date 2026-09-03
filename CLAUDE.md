# Comped — project index

Rote Playoffs hackathon entry: three rote Plays (`session-ledger`, `comped`, `wrong-turns`) on one stdlib-only Python core. Submissions close 7 Sep 2026 20:00 London. Session state lives in `docs/context/`, not here.

## Context docs

| Doc | Covers |
|---|---|
| [docs/context/comped-plays.md](docs/context/comped-plays.md) | Whole project: spec, plan, research, Play packaging, publishing, adoption. Current state, decisions, next steps. |

## Read first
- `docs/SPEC.md` — approved build spec.
- `docs/superpowers/plans/2026-09-03-comped-plays.md` — plan index; tasks in `comped-plays/part-0..6.md`.
- `docs/research/LANDSCAPE.md`, `docs/research/ROTE-FORMAT.md` — facts and verified Play format.

## Conventions
- Python ≥ 3.9 stdlib only in `comped_core/`; tests via `python3 -m unittest discover -s tests`.
- Commit per task, conventional messages. Never read credential files; never add network calls.
- Update `docs/adoption-log.md` daily once published.
