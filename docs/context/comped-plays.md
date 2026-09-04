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
- **Tasks 0(partial), 1-13 done, 14-15 partly done. 84 tests green.** `comped_core/` is complete and stdlib-only: adapters (claude-code, codex, pi, opencode) -> ledger -> pricing -> repeats/wrong-turns/baseline -> renderers -> CLI. Determinism, no-network, no-credential, robustness, perf (8.8s over 227k real log lines) and ccusage conformance (token totals match per model, actually runs) all pass.
- **rote 0.79.0 installed**, signed in as `the handle owner's Google account`, handle **`rajkaria`** reserved (`rote profile set-handle`, one-time/immutable; NOT part of the OAuth flow, contrary to plan Step 3). Plan tier for demos: **Claude Max 20x -> `claude-max-200`**.
- Fixtures: 0.93 MB synthetic, privacy-tested, 64 claude + 31 codex records, 7 tool errors, one subagent session.
- Plays packaged: `tools/sync_plays.py` (+ `--check`), `plays/<slug>/{DESCRIPTION,PARAMETERS,STEPS}`, docs tests. CI, README (with fixture card screenshot), VISION done.
- **Nothing published.** `docs/adoption-log.md` is still just a header row. Repo is still private.
- **Blocked on the user / on rote:** Task 0 Steps 3-9 (warm-up runs, practice Play through `/play settle`, filling the ROTE-FORMAT PENDINGs, play-quality-doctor), Task 14 Steps 3-7 (capture, quality gate, clean-machine run, publish), Task 15 Step 5 (make repo public), Task 16 (distribution, judge loop).
- The Claude Code permission classifier blocks reading `~/.claude/projects` from ad-hoc scripts; fixture regeneration must go through `tools/make_fixtures.py`, and even that was blocked intermittently.

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
1. **User decisions still open:** Discord membership + posting, X/LinkedIn posting, `gh` auth and making the repo public, authorisation to publish the three Plays, who drives `/play explore` and `/play settle`, whether a clean second machine exists, and whether real-log output may appear in public screenshots.
2. Task 0 Steps 3-9: `/play what's new`; run `modiqo/hello` and `dotisacat/playoffs-standings author=rajkaria`; practice Play through settle (Skip, do not publish); `rote how` / `rote guidance`; read a pulled token-tab archive; fill every PENDING in `docs/research/ROTE-FORMAT.md`; run play-quality-doctor.
3. Task 14 Steps 3-7: write each Play's `main.ts` with the verified frontmatter, capture one session per Play, quality-doctor gate, clean-machine run, publish `session-ledger` + `comped`, then `wrong-turns` the next day.
4. Task 15 Step 5 (public repo) and Task 16 (daily adoption log, social posts, two judge-panel rounds) through to close on 7 Sep 20:00 London.
