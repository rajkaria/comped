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

- **The leaderboard is live (05 Sep).** comped is the product; the Play is how you run it. Every run of `comped` ends with a new step `post_score` that POSTs the score to `https://gotcomped.com/api/score` and prints the rank (`Leaderboard: #1 of 1 · …/leaderboard.html#rajkaria`); `leaderboard=false` sends nothing; a failed post is a warning, exit 0. The poster is `leaderboard/post_score.py` (stdlib; urllib → system CA bundle → `curl` fixed-argv fallback for python.org builds without certs), synced by `tools/sync_plays.py` into `plays/comped/resources/post_score.py` only. `comped_core` is still verifiably offline (`test_no_network.py`), and `tests/test_leaderboard.py` (20 tests) proves the poster is the only file in any package that can open a socket.
- **Server:** `api/score.py` + `api/leaderboard.py` + `api/_common.py`, stdlib Python on Vercel (same project `comped`, auto-deployed from `main`, env `SUPABASE_URL`/`SUPABASE_KEY` = publishable key). They call two `security definer` SQL functions on the existing Supabase project `bpwmpkguhrcpxtcignzo` (shared with hunch; migration `comped_leaderboard`): `comped_submit(jsonb)` validates every bound (handle regex, ranges, `multiplier == comped_usd/plan_usd` ±2%, 15 s per-device interval, held over 2,000×/$250k) and upserts on the device uuid; `comped_board(text,int)` ranks the view `comped_board_rows` (eligible = multiplier present, ≥$20, ≥3 active days; one row per handle, latest wins; anon rows per device shown as `anon-xxxx`). Table and view are closed to anon; the device id is never returned. Verified live: POST/GET from Python, 400/429/405 paths, the registry copy posting from a fresh dir, and `sh site/run.sh` on real logs.
- **Site:** `site/leaderboard.html` (sort by score/dollars, provider chips, handle search, `#handle` highlight) + `site/board.js` (one fetch to this origin, `cache: "no-store"`; the API sends `max-age=0, must-revalidate, s-maxage=30` because Chrome honours stale-while-revalidate and showed a stale empty board). Home page: nav link, "See the leaderboard" button, live people-count stat, a `#board` top-ten section, rewritten privacy tiles/FAQ/share sample. CSP is now `connect-src 'self'`. `tools/devserver.py 8123` serves site + API locally (`.claude/launch.json` config `site`; `vercel env pull .env.local` first).
- **Copy rule (enforced by `test_site.py`):** "Nothing leaves your computer" / "0 bytes" is gone everywhere. The honest line: your logs never leave; the one thing sent is your score; here is the list (`~/comped/comped-rank.json` holds the exact payload and reply); here is the switch. SPEC §9 paragraph reworded (verbatim in all three DESCRIPTIONs), SPEC §17 documents the leaderboard, README/VISION/CLAUDE.md updated, docs page has a Leaderboard section and developers page a Leaderboard API section.
- **Share text** (`render_report.share_text`) now takes `rank`/`rank_of`: "My comp score is 13× (All-you-can-eat), #1 of 1 on the gotcomped.com leaderboard. Anthropic gave me $2,578 of AI for $197 this month. What's yours? One line: gotcomped.com #gotcomped". `post_score` rewrites `comped-share.txt` with it once ranked. `run.sh` passes `handle=<rote whoami>` unless the caller set one and prints the rank URL.
- **All three Plays at 0.1.4 and published** (comped, session-ledger re-pushed; **wrong-turns first publish**, per the stagger plan). 151 tests green; `rote play validate/lint/score` 1.00 on comped with nine fixtures captured from a run through the live API (`docs/plays/comped/PRESENTATION_FIXTURES.json`). Smoke run off the public 0.1.4 archive from a fresh dir: 9/9, post reached the API.
- **Redesign (05 Sep).** New palette shared by site and card: cream `#fff7ea`, plum ink `#1e1b2e`, coral `#ff6b4a` (score, CTA), violet `#6a4bff`, yellow `#ffd23f` (tier sticker), rounded system type (`ui-rounded`). `site/style.css` rewritten; `site/index.html` rewritten in plain sentences (a `test_site` test forbids em dashes on every page; `tools/build_site.py` copy was de-dashed too). `comped_core/render_svg.py` rebuilt: wordmark, huge full-price number, coral score line, model bars, "IF YOU'RE ON" panel with the assumed row marked, a crooked yellow sticker for the tier, `dark` (plum) and `light` (cream) themes. The site's sample card is now Raj's real month (`site/card.svg/.png/-wide.png`, wide = PIL crop of the square PNG rows 262..937; qlmanage pads the wide SVG to a square). `tools/devserver.py 8123` serves site + API locally; `.env.local` must be written by hand because `vercel env pull` writes `[SENSITIVE]` for the two values.
- **An agent can run it now (05 Sep).** `site/llms.txt` is the briefing agents are pointed at: what comped reads and refuses to read, three ways to run it in order (rote signed in → `rote play run … --yes`; no rote → `git clone --depth 1` and one `python3` command; no shell at all → hand the human `run.sh`), consent before the leaderboard post, the output contract, and how to read the card back. The paste line, on the landing page, in the docs and in the README, is `Fetch https://gotcomped.com/llms.txt and do what it says.` Backing it: `comped_core run`, one command that is `ledger → price → repeats → card` in one process (byte-identical output to the four steps, proven in `test_cli.py`), and `main()` now exits 1 when a command reports `ok: false`. `tests/test_llms.py` (11 tests) parses every command in llms.txt with the real argparse parser, checks every `name=` against `docs/plays/comped/PARAMETERS.json`, and fails if the consent sentences or the paste line go missing. The Play is unchanged and still runs one reading per step.
- **Board contents right now:** one row, `rajkaria` 13× $2,578. Test/demo rows were deleted after each verification.
- Earlier state (tiers, one-paste `run.sh`, auto-detection, 78-model price table, Vercel hosting at gotcomped.com, rote 0.79.0, handle `rajkaria`) all still holds; see git history for detail.
- **Not done:** Discord/X/LinkedIn launch posts (drafts exist but predate the redesign and the board; rewrite them in the new voice); judge-panel rounds; daily adoption-log rows; a self-serve "remove my row" path (currently: open a GitHub issue); the docs/developers pages got the new theme but not a copy pass in the new voice.

## Recent changes — files touched and why

- `leaderboard/post_score.py` (new) — the poster; payload built in `payload()`, TLS fallbacks in `post()`, share rewrite via the core's `share_text`.
- `api/_common.py`, `api/score.py`, `api/leaderboard.py` (new) — Vercel functions; `submit()` and `board()` are plain functions the tests call with a fake opener.
- `tools/build_plays.py` — VERSION 0.1.4, `post_score` step (depends on `render_card`), `leaderboard` in the output schema, comped presentation reads the poster's JSON and appends the rank to human/summary/result. `tools/sync_plays.py` — `EXTRA` per-play files. `tools/devserver.py` (new). `tools/build_site.py` — nav/footer link, docs Leaderboard section + troubleshooting, developers Leaderboard API section, privacy bullets.
- `docs/plays/comped/{PARAMETERS.json,STEPS.md,DESCRIPTION.md}` — `leaderboard` param, `handle` reworded, new step and outputs. `docs/SPEC.md` §9 + §17. `docs/plays/*/DESCRIPTION.md` privacy paragraph. `README.md`, `VISION.md`, `CLAUDE.md`, `pyproject.toml` 0.1.4, `docs/adoption-log.md`.
- `site/leaderboard.html`, `site/board.js` (new); `site/index.html`, `site/style.css` (board styles), `site/run.sh`, `site/app.js` comment; `vercel.json` CSP `connect-src 'self'`; `.gitignore` ignores the synced `post_score.py`.
- `comped_core/render_report.py` — `share_text` rank-aware and no longer claims to be offline. `comped_core/render_svg.py` — the card redesign (new THEMES, sticker, ladder panel, blobs; `_mult(None)` says "no plan").
- `site/style.css` (full rewrite, new tokens), `site/index.html` (full rewrite, no em dashes, `hide-xs` nav trick for phones), `site/card.svg/.png/-wide.png` (real month), `site/app.js` (verdict copy), `tools/devserver.py` (site + API locally, reads `.env.local`), `.claude/launch.json` config `site` → `tools/devserver.py 8123`.
- `tests/test_leaderboard.py` (new), `tests/test_site.py` (four pages, new CSP, new copy guard, board.js guard, run.sh guard).
- `site/llms.txt` (new, the agent briefing), `tests/test_llms.py` (new, it cannot drift from the CLI or the Play parameters). `comped_core/cli.py` — `cmd_run`, option groups shared between `run` and the steps it runs, `main()` exits 1 on `ok: false`. `site/index.html` + `site/style.css` (`.agent-line` callout under the three steps), `tools/build_site.py` (docs `#agent` section, developers `#agent` section and a `run`-first "without rote"), `README.md` (agent section, python3-only section, test count).

## Key decisions — choices and trade-offs

- Flagship `comped`; satellites `session-ledger` (primitive) and `wrong-turns`. Composition between Plays does not exist in rote, so each bundles a byte-identical `comped_core`, enforced by `sync_plays.py --check`.
- Plan tier is **inferred from the model ids in the logs**, never typed and never read from an account; `~/.claude.json` and `~/.codex/auth.json` are still never opened, enforced by the same source-grep test. The inference is deliberately unflattering (most expensive plan that fits) and every other tier is shown beside it, because guessing in your own favour is the one thing this tool must not do.
- No network in the core; bundled price snapshot with source/sha/as-of; unknown models reported, never guessed. The single network step (`post_score`) lives outside the core, is default-on because the leaderboard is the product, is switchable, and can never fail the run.
- `execution_model: steps_with_presentation`. Tags are carried in **all three** places (`metadata.discoverability.tags`, top-level `tags`, top-level `discoverability`) — the rubric reads all three and scores 0.88 without them.
- Presentation fixtures are captured from real runs, never hand-written; lint replays the body against them.
- Repeat clustering excludes harness-generated text (continuation preamble, local-command caveat) and, on a priced ledger, drops zero-cost clusters. Both found by running on real logs.
- Site is static with zero third-party requests and one same-origin fetch (the board). Docs are generated from the code they document and CI fails on drift.
- The agent path leads with the Play (`rote play run`) and falls back to a clone, so an agent with no rote account is not turned away and a signed-in one still runs the published Play. The briefing tells the agent to ask before posting a score: a run someone did not choose to publish is worth less than the row it would add.
- Publishing staggered: `session-ledger` + `comped` 04 Sep, `wrong-turns` 05 Sep.
- The leaderboard is a slice of the earlier `~/Projects/unbilled/docs/SPEC.md` draft: self-reported only (no daemon, no signed keys, no Merkle audit), ranked by multiplier, the same eligibility idea ($20, 3 days). Storage is reached only through SQL functions so the publishable key is enough; no service-role key exists in Vercel.
- Existing shared Supabase project reused (creating a new one needs a cost confirmation from Raj); objects are `comped_`-prefixed in `public`.

## Next steps — specific, actionable

1. **Say the agent line out loud in the launch posts.** "Paste this at your coding agent" is a different pitch from "paste this in Terminal" and it is the one that fits where these people already are.
2. **Post the launch** — Discord #sharing, X, LinkedIn, in the plain voice of the new landing page (no em dashes, no triads). Lead with the board and the card PNG (`site/card-wide.png` is Raj's real month): `curl -fsSL https://gotcomped.com/run.sh | sh` puts you on https://gotcomped.com/leaderboard.html; the share line in `~/comped/comped-share.txt` already carries the rank.
3. **Daily adoption-log rows** from `playoffs-standings author=rajkaria` (manifest `stats.downloads`), and the board count from `https://gotcomped.com/api/leaderboard?limit=1` (`count`, `submissions`).
4. **Judge loop, twice** (SPEC §15) against gotcomped.com (home + leaderboard), the three Play pages and a clean run; fix and republish as patch versions until ≥ 9.5.
5. **Watch the board for junk.** `select handle, multiplier, comped_usd, held from comped_scores order by updated_at desc` via the Supabase MCP; `update … set held = true` hides a row. Consider a `removed` flag + an issue template for "take me off".
6. **Voice pass on docs.html / developers.html** (`tools/build_site.py` `docs_page()` / `developers_page()`): same plain sentences as the landing page; the dashes are gone but the register is still terse-technical. Also the Play DESCRIPTION.md texts.
7. **Optional polish:** an OG image per handle (`/api/card/<handle>.svg`) so a shared rank link unfurls with the score; a "this week" window; per-provider boards as real routes. Decide `repeat_threshold` default (spec 3, real logs need 2).
8. Optional: purge the rote account address from three early commits (`git filter-branch`; needs the user).
