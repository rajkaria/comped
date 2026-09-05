---
feature: comped-plays
globs:
  - docs/**
  - comped_core/**
  - plays/**
  - resources/**
  - site/**
  - tests/**
  - tools/**
  - .github/**
  - README.md
  - api/**
  - leaderboard/**
  - vercel.json
  - VISION.md
updated: 2026-09-05
---

# Comped Plays — session context

Rote Playoffs entry (Modiqo). Build window 1–7 Sep 2026; **submissions close 7 Sep 20:00 London (00:30 IST 8 Sep)**. Publishing a Play to Community is the submission; prizes are per Play; judged on runs / stranger-trust / adoption downloads.

## Current state — what's working, deployed, broken

- **The repo now holds nine published Plays, not three.** Six local-machine Plays on a second
  stdlib-only core (`daily_core`) were built and published on 5 Sep 2026 and live in their own
  context doc: [daily-plays.md](daily-plays.md). Nothing in `comped_core` changed for them;
  `tools/sync_plays.py` gained a second list.

- **Live on prod, verified end to end (05 Sep).** `main` is at `afb7d92`; Vercel has deployed it. The full production path was run and watched: `curl -fsSL https://gotcomped.com/comped.sh | sh -s -- handle=rajkaria` downloaded the archive, matched the published sha256, printed the card and posted. Board reads one row, `rajkaria` 13.31x $2,623.20. The published checksum and the live archive hash agree byte for byte.
- **Three front doors, one core.** `comped.sh` (no account, ~150 KB temp dir, deletes itself), `npx comped` (**published to npm at 0.1.5**), and `run.sh` (the rote Play, consent screen, free Modiqo account). All take the same fourteen parameters, asserted against `docs/plays/comped/PARAMETERS.json`. The core copy in each is byte-identical and CI fails on drift.
- **`npx comped` is live on npm (05 Sep).** `comped@0.1.5`, the name was free. The tarball pulled back down from the registry is the one that was built here: 44 files, 156,248 bytes, shasum `0d7f4c8c1a554879f911749fdfe4bb3656ca6a7e`, its `comped_core` identical to the repo's and its `payload/comped.py` sha256-equal to `standalone/comped.py`. Ran the published payload off its own shipped fixtures: card, PNG, SVG, report and share text all written, `leaderboard=false` honoured. `npm whoami` had been 401 the whole time — that was the only blocker, and the dead token in `~/.npmrc` is still worth rotating (next steps).
- **All three Plays published at 0.1.5.** Push command is `rote registry play push plays/<slug> rajkaria` — the slug argument is the *namespace*, not the play name. Gates 1.00 on validate/lint/score for all three; smoke run off the public 0.1.5 archive from a fresh dir passes.
- **Windows works and is proven.** The `windows-standalone` CI job unpacks the real archive on windows-latest and runs it with stdout redirected, then installs and runs the npm package. Green on `f2a3008`, so it now **gates** the build. `npx comped` is the Windows answer; the curl line still needs WSL.
- **Site:** landing page, docs and leaderboard lead with the account-free line; `llms.txt` is the hand-written agent briefing (not generated) and now offers comped.sh and npx before the git clone; `robots.txt` and `sitemap.xml` added. 200 tests green.
- **Not done:** launch posts; judge-panel rounds; daily adoption-log rows; a self-serve "remove my row" path (currently: open a GitHub issue).

## Recent changes — files touched and why

- `comped_core/cli.py` — `run` subcommand (read, price, cluster, render in one command), parser refactored into per-step argument groups, `main()` exits non-zero when a command reports `ok:false`. Plus a UTF-8 stdout guard, without which the card dies against a Windows code page on a pipe, and progress on stderr.
- `standalone/comped.py` (new) — the entry point the two account-free doors share. `key=value` args like the Play, calls `cmd_run` then `post_score.py`. Relative log dirs resolve against the package so the documented demo line works from anywhere; packaged fixtures get their mtime stamped on use; the core's `--flag` advice is rewritten into the `key=value` this door takes.
- `tools/build_dist.py` (new) — reproducible `site/comped.tar.gz` + `.sha256`. `tools/build_npm.py` (new) — assembles `npm/` from the same `members()` payload. `tools/build_site.py` calls both, so Vercel builds them on deploy.
- `site/comped.sh` (new) — 65 lines: find python3, download, verify checksum, unpack, run, delete. Not `exec`, or the cleanup trap never fires.
- `npm/bin/comped.js` (new, the only hand-written file in `npm/`) — finds an interpreter, sets `PYTHONIOENCODING`, hands over `payload/comped.py`. No node dependencies, no install script.
- `site/llms.txt` — the agent briefing gained options B and D (comped.sh, npx) ahead of the git clone.
- `site/index.html`, `site/leaderboard.html`, `README.md`, `docs/SPEC.md` §18, `CLAUDE.md`, `docs/adoption-log.md`, `.github/workflows/ci.yml`.
- `tests/test_standalone.py` (23) and `tests/test_npm.py` (9) new; `tests/test_site.py` extended.

## Key decisions — choices and trade-offs

- **Three doors, not a replacement.** `run.sh` and the Play are untouched: the Play is the Playoffs submission, and its consent screen plus public archive are the real answer to "why would I paste this". The other two are for everyone who will not make an account to find out what their subscription is worth. Measured, not assumed: `rote play run` refuses without a login for a *local* package directory as well as a registry URI; `rote play inspect` works anonymously.
- **npm is a delivery lorry, not a dependency.** Zero node dependencies, no install script, one launcher file. A tool that reads session logs has no business pulling in a dependency tree nobody reads.
- The archive carries the sample logs (+112 KB) so a stranger can watch it work on invented data first, through any door.
- The checksum is served from the same origin as the archive, so it proves the download arrived whole, not that the origin is honest. The script says exactly that rather than implying more.
- **`site/llms.txt` stays hand-written**, not generated. A generated llmstxt.org summary was written this session and deleted: two files cannot own one path, and the hand-written briefing is the one with tests checking every command it names against the parser that will receive it.
- Where two sessions collided on `cmd_run`, the version on `main` won on design (argument groups, JSON contract, exit codes) and this branch's Windows fix and stderr progress were folded into it.
- Flagship `comped`; satellites `session-ledger` (primitive) and `wrong-turns`. Composition between Plays does not exist in rote, so each bundles a byte-identical core, enforced by `sync_plays.py --check`.
- Plan tier is **inferred from the model ids in the logs**, never typed and never read from an account; `~/.claude.json` and `~/.codex/auth.json` are never opened, enforced by a source-grep test. The inference is deliberately unflattering and every other tier is shown beside it.
- No network in the core; bundled price snapshot with source/sha/as-of; unknown models reported, never guessed. The single network step (`post_score`) lives outside the core, is default-on, switchable, and can never fail the run.
- `execution_model: steps_with_presentation`. Tags in **all three** places or the rubric scores 0.88. Presentation fixtures captured from real runs, never hand-written.
- Site is static with zero third-party requests and one same-origin fetch. Docs are generated from the code they document and CI fails on drift.
- The leaderboard is self-reported only (no daemon, no signed keys); storage reached only through SQL functions so the publishable key is enough. Existing shared Supabase project reused; objects are `comped_`-prefixed in `public`.

## Next steps — specific, actionable

1. **Rotate the npm token that was pasted into a chat session on 05 Sep.** Revoke it at npmjs.com under Access Tokens and mint a fresh one. It should be treated as compromised.
2. **Post the launch** — Discord #sharing, X, LinkedIn, in the plain voice of the landing page. Two pitches now, and they are different: "paste this in Terminal, no account" and "paste this at your coding agent". Lead with the board.
3. **Daily adoption-log rows** from `playoffs-standings author=rajkaria` (manifest `stats.downloads`) and the board count from `https://gotcomped.com/api/leaderboard?limit=1`.
4. **Judge loop, twice** (SPEC §15) against gotcomped.com, the three Play pages and a clean run; fix and republish as patch versions until ≥ 9.5.
5. **Watch the board for junk.** `select handle, multiplier, comped_usd, held from comped_scores order by updated_at desc` via the Supabase MCP; `update … set held = true` hides a row.
6. **`tests/test_perf.py` is marginal locally.** It reads ~1 GB of real logs against a 10 s budget and takes 9–15 s depending on disk cache. It skips in CI. Raise the budget or scope the fixture; it is not a regression.
7. **Optional polish:** an OG image per handle (`/api/card/<handle>.svg`); a "this week" window; per-provider boards as real routes; a voice pass on `docs.html` / `developers.html`; purge the rote account address from three early commits (needs Raj).
