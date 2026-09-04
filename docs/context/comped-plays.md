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
- **Spec and plan complete, no code yet.** `docs/SPEC.md` (approved), plan index `docs/superpowers/plans/2026-09-03-comped-plays.md` + `comped-plays/part-0..6.md` (17 tasks, TDD, full code in each step), research in `docs/research/LANDSCAPE.md` and `docs/research/ROTE-FORMAT.md`.
- **Task 0 half done.** Installer chain inspected and dry-run; Play package source (modiqo/play v0.4.87) read; Play format facts verified (main.ts + `@rote-frontmatter` YAML header, one-reading-per-step DAG standard, `{"ok":true,"warning":...}` failure contract, settle/publish flow with `/tmp` smoke test). Latest rote is v0.79.0.
- **Unblocked 2026-09-04:** rote **0.79.0** installed at `/Users/rajkaria/.local/bin/rote`, signed in as `rajkaria67@gmail.com`, handle **`rajkaria`** reserved (`rote profile set-handle`, one-time/immutable). Public namespace `play.modiqo.ai/rajkaria/...`. Plan tier for pricing demos: **Claude Max 20x → `claude-max-200`**. Part-0 Steps 1–2 done; Steps 3–9 (warm-up runs, practice Play, format PENDINGs, quality doctor) still open.
- Nothing published. `docs/adoption-log.md` has its header row only.
- Two git commits on `main` in `/Users/rajkaria/Projects/comped` (docs only).

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
1. ~~Install + handle~~ done 2026-09-04 (`rajkaria`).
2. Finish Task 0 (part-0-gate.md Steps 2–7): `/play what's new`; run Hello and `dotisacat/playoffs-standings author=<handle>`; practice Play (Skip, don't publish); `rote how`, `rote guidance`, read the `rote-flow-authoring` skill and a pulled token-tab archive; fill every PENDING in `docs/research/ROTE-FORMAT.md`; run play-quality-doctor on the practice Play; post "warmed up" in Discord; commit.
3. Tasks 1–2 (part-1-core.md): scaffold, models, jsonl, timeutil, `tools/build_prices.py`, `prices.py`, `plans.py`. Can start before the install.
4. Tasks 3–5 in parallel (adapters + fixtures), then 6–13, then Part 6 packaging/capture/publish, then daily distribution + adoption log.
