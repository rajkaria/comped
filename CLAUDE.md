# Comped — project context

## What this is
Rote Playoffs hackathon entry (build window 1–7 Sep 2026, submissions close 7 Sep 20:00 London / 00:30 IST 8 Sep). Three rote Plays on one stdlib-only Python core. Publishing to Community is the submission; prizes are per Play.

## Read first
- `docs/SPEC.md` — the approved spec (contracts, math, outputs, distribution, projected 9.6 panel score).
- `docs/superpowers/plans/2026-09-03-comped-plays.md` — plan index; detailed tasks in `comped-plays/part-0..6`.
- `docs/research/LANDSCAPE.md` — competitors, judging, manifest schema, measurements on this machine.
- `docs/research/ROTE-FORMAT.md` — written by Task 0 after installing rote; gates Part 6.

## Key decisions (2026-09-03)
- Flagship is `comped` (card + repeat offenders + Rote dividend). Satellites: `session-ledger` (primitive), `wrong-turns`. The earlier "Standings / package health / name check" ideas were dropped: all three already exist in the registry.
- Plan tier is a typed input; the Play never reads `~/.claude.json` or `~/.codex/auth.json`.
- No network at runtime; bundled LiteLLM price snapshot with source, sha, as-of; unknown models reported, never guessed.
- Claude Code dedup key is `(message.id, requestId)` (41% duplicate lines measured). Codex per-turn usage is the difference of consecutive cumulative `token_count` snapshots.
- Repeat detection: Jaccard ≥ 0.5 on 2-shingles, cluster needs ≥ 3 asks, ≥ 2 sessions, ≥ 2 days; automated/observer prompts excluded (measured to be necessary).
- Composition between Plays is unverified; fallback is byte-identical `comped_core` copies per Play, checked by `tools/sync_plays.py --check`.
- The earlier, wider Comped product draft lives at `~/Projects/unbilled/docs/SPEC.md` (leaderboard etc.). Out of scope for the Plays.

## Current state
Spec and plan written. No code yet. Task 0 is half done: the installer chain was inspected and dry-run, the Play package source (modiqo/play v0.4.87) was read, and `docs/research/ROTE-FORMAT.md` holds every verified format fact (main.ts + @rote-frontmatter header, one-reading-per-step DAG standard, failure contract, settle/publish flow, /tmp smoke test). The unattended install was blocked by the permission classifier; the user must run `curl -fsSL https://getrote.dev/playoffs/install.sh | sh` in a terminal, sign in, and claim a handle. Latest rote is v0.79.0.

## Next steps
1. Task 0 remainder (part-0-gate.md Steps 1–7): user installs rote; then `/play what's new`, Hello, playoffs-standings, practice Play, `rote how`/`rote guidance`, read the rote-flow-authoring skill, pull token-tab's archive, fill every PENDING in ROTE-FORMAT.md, play-quality-doctor on the practice Play, post "warmed up".
2. Tasks 1–13 in order (parts 1–5); Tasks 3/4/5 can run in parallel.
3. Part 6: package, capture with one kept wrong turn per Play, quality-doctor gate, publish `session-ledger` + `comped` same day, `wrong-turns` next day, then daily distribution and the adoption log.

## Conventions
- Python ≥ 3.9 stdlib only in `comped_core/`; tests via `python3 -m unittest discover -s tests`.
- Commit per task, conventional messages.
- Keep `docs/adoption-log.md` updated daily once published.
