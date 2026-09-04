---
feature: comped-plays
globs:
  - docs/**
  - comped_core/**
  - plays/**
  - resources/**
  - tests/**
  - tools/**
  - README.md
  - VISION.md
updated: 2026-09-04
---

# Comped Plays — session context

Rote Playoffs entry (Modiqo). Build window 1–7 Sep 2026; **submissions close 7 Sep 20:00 London (00:30 IST 8 Sep)**. Publishing a Play to Community is the submission; prizes are per Play; judged on runs / stranger-trust / adoption downloads.

## Current state — what's working, deployed, broken
- **Tasks 0-15 done except publishing. 91 tests green. Repo public at https://github.com/rajkaria/comped (main), CI running on GitHub Actions.**
- `comped_core/` complete and stdlib-only. All three Plays are packaged, generated from single source by `tools/build_plays.py`, and **score 1.00 on the registry rubric**: `rote play validate` OK, `rote play lint` passed with zero findings, `rote play score` 1.00, and himanshu-jha/play-quality-doctor says "Full marks. Nothing here needs changing."
- **All three ran end to end inside rote**: comped 8/8 steps in 1.8s on fixtures, session-ledger 6/6, wrong-turns 5/5. On real logs comped takes 9.5s and reports **$2,584.71 comped, 13.1x vs Claude Max 20x, 98% cache read, 98 sessions, 22 active days**, top repeat "push and make it live on prod" at $45.69 (at repeat_threshold=2; at the spec default of 3 no cluster qualifies on this machine's 30 days).
- rote 0.79.0, handle **`rajkaria`** reserved. `docs/research/ROTE-FORMAT.md` is fully verified; only the registry push command and the verbatim `/play settle` prompts remain open, both needing an interactive harness session.
- **Nothing published.** `docs/adoption-log.md` is still a header row. Publishing is the submission and needs the user's go-ahead.

## Recent changes — files touched and why
- `docs/SPEC.md` — full build spec: three Plays (`session-ledger`, `comped`, `wrong-turns`), contracts, math (dedup on `(message.id, requestId)`, Codex cumulative-counter differencing, plan proration /30.4375), repeat detection (Jaccard ≥0.5 on 2-shingles; ≥3 asks, ≥2 sessions, ≥2 days), wrong-turn signals with confidence, outputs (terminal card, SVG/PNG, report, explain, share text, delta), privacy paragraph, quality checklist, tests, distribution plan, panel scorecard (projected 9.6).
- `docs/research/LANDSCAPE.md` — hackathon rules, registry state, competitor table (token-tab 6, session-digest 3, playoffs-standings 7 manifest downloads), manifest schema, measurements on this machine (41% duplicate usage lines; automated observer prompts pollute clustering; 873 tool errors; price-table coverage).
- `docs/research/ROTE-FORMAT.md` — verified/pending Play format facts; decisions for Part 6.
- `docs/research/manifest-*.json`, `well-known-rote.json` — saved reference artefacts.
- `docs/superpowers/plans/…` — plan index + parts 0–6. Part 5 CLI gained `--only <harness>` and `merge` subcommands; Part 6 steps rewritten to 4 parallel reads → merge → price → repeats → card, plus main.ts header template and tag-hints step.
- `docs/adoption-log.md`, `README.md`, `VISION.md`, `CLAUDE.md` (index).

## Key decisions — choices and trade-offs
- Flagship `comped` (priced card + repeat offenders + Rote dividend at 98%/80%); satellites `session-ledger` (primitive) and `wrong-turns`. Dropped "Standings / package health / name check": all pre-empted in the registry (playoffs-standings, pkg-vet, package-name-search).
- Plan tier is a typed input; never read `~/.claude.json` or `~/.codex/auth.json` (honest contract for judges).
- No network at runtime; bundled LiteLLM price snapshot with source/sha/as-of; unknown models reported, never guessed (`gpt-5.5-codex` absent upstream).
- Python ≥3.9 stdlib only; `unittest`; `decimal` money; byte-identical reruns with `--now` pinned.
- Composition between Plays unverified → bundle byte-identical `comped_core` copies per Play, checked by `tools/sync_plays.py --check`.
- One reading = one step (rote play-shape standard) → per-harness read steps as parallel roots; expected absence exits 0 with a warning.
- Publish order: `session-ledger` + `comped` same day, `wrong-turns` next day; daily card posts tagging Modiqo; keep one wrong turn per captured run.
- Earlier wider product draft (leaderboard) stays at `~/Projects/unbilled/docs/SPEC.md`, out of scope for the Plays.

## Next steps — specific, actionable
1. **User decisions still open:** authorisation to publish the three Plays to Community; Discord membership and posting; X/LinkedIn posting; whether real-log numbers may appear publicly; and whether a clean second machine exists for the portability check.
2. Publish: `rote play release` then the registry push (command still unverified -- it is delegated to the `rote-registry` skill inside `/play settle`), then `rote play inspect <owner/name> --json` readback and a smoke run from a fresh /tmp dir. Order: `session-ledger` + `comped` same day, `wrong-turns` next.
3. Task 16: daily adoption-log rows, social posts, two judge-panel rounds, final checks before 7 Sep 20:00 London.
4. Optional: decide whether the spec's repeat_threshold default of 3 should drop to 2 -- on 30 days of this machine's real logs, 3 finds nothing and 2 finds two genuine asks.
