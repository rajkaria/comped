# Adoption log

Downloads are read from the Play's manifest (`https://play.modiqo.ai/<handle>/<play>.json` → `stats.downloads`), not from the feed page, which lags and counts differently.

| date (IST) | play | version | downloads (manifest) | delta | notes (posts, Discord, asks) |
|---|---|---|---|---|---|
| 2026-09-03 | — | — | — | — | Spec and plan written; rote not yet installed; nothing published. Participant leader: hackathon-submission-readiness at 19 (feed) / 7 (manifest). |
| 2026-09-04 | session-ledger | 0.1.0 | 0 | first publish | Published to Community. Registry rubric 1.00, quality-doctor full marks. |
| 2026-09-04 | comped | 0.1.0 | 0 | first publish | Published to Community. Smoke-run from a fresh dir off the public archive: 8/8 steps. |
| 2026-09-04 | wrong-turns | — | — | — | Held for 05 Sep per the distribution plan (staggered so each publish gets its own NEW row in playoffs-standings). |
| 2026-09-04 | session-ledger + comped | 0.1.1 | 0 | re-push | Version bump so the registry copy carries the https://gotcomped.com link. |
| 2026-09-04 | comped | 0.1.2 | 0 | re-push | Auto-detection release: the Play works out which AI you run from the model ids and prices every tier those providers sell. Smoke-run from a fresh dir off the public 0.1.2 archive: 8/8 steps. |
| 2026-09-04 | session-ledger | 0.1.2 | 0 | re-push | Same core, same detection underneath. |
| 2026-09-05 | comped | 0.1.3 | 0 | re-push | Tiers on the card and in the share text (Paying customer → Please stop), a remembered `plan=`, and the one-paste `gotcomped.com/run.sh` that skips the Ready selector. |
| 2026-09-05 | session-ledger | 0.1.3 | 0 | re-push | Same core. |
| 2026-09-05 | comped | 0.1.4 | 0 | re-push | **The leaderboard.** Last step `post_score` posts the score to gotcomped.com and prints the rank; `leaderboard=false` sends nothing. Site: `/leaderboard.html`, live top ten on the home page, honest privacy copy. Smoke-run from a fresh dir off the public 0.1.4 archive: 9/9 steps, post reached the live API. |
| 2026-09-05 | session-ledger | 0.1.4 | 0 | re-push | Same core; privacy paragraph now names comped's poster as the one network step. |
| 2026-09-05 | wrong-turns | 0.1.4 | 0 | first publish | Published to Community per the stagger plan (its own NEW row). |

| 2026-09-05 | comped | 0.1.5 | 0 | re-push | **Two more front doors.** `curl gotcomped.com/comped.sh \| sh` needs no account and installs nothing; `npx comped` for anyone with node. Same core all three ways, byte-identical, CI fails on drift. Core gained a `run` subcommand and a UTF-8 stdout fix so the card survives a Windows code page. Registry gates still 1.00; smoke-run off the public 0.1.5 archive from a fresh dir: 9/9. |
| 2026-09-05 | session-ledger | 0.1.5 | 0 | re-push | Same core. |
| 2026-09-05 | wrong-turns | 0.1.5 | 0 | re-push | Same core. |
| 2026-09-05 | comped (npm) | 0.1.5 | — | first publish | **`npx comped` is live.** Published to npm as [`comped`](https://www.npmjs.com/package/comped) — the name was free. 44 files, 156 KB, no node dependencies and no install script; `bin/comped.js` only finds a Python and hands it the payload. The tarball pulled back from the registry matches the local build (shasum `0d7f4c8c1a554879f911749fdfe4bb3656ca6a7e`) and its core is byte-identical to the repo's; ran it end to end off its own fixtures. Downloads column is the Play manifest, which npm has no part in; npm's own counts lag about a day, so read them at npmjs.com from 06 Sep. |
