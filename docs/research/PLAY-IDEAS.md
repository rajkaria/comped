# Day-to-day Play ideas — registry survey, 5 Sep 2026

Source: `rote play search --source registry --scope public` across ~30 everyday topics, plus the full
821-manifest list on modiqo.ai/feed and the six fields of Modiqo's "150 ideas" kit (cloud ops, agent
ops, security, finance, people, public+personal).

## What the registry already has

821 public plays. Roughly nine in ten are developer tooling: git/PR/CI hygiene, secret scans, dependency
drift, MCP audits, agent-session audits, hackathon readiness. Many near-duplicates (5+ env-drift plays,
5 mac-storage plays, 6 token-spend plays incl. ours). What gets downloads: pinned modiqo plays, then
zero-key read-only python3 plays with one punchy hook (token-tab, repo-fire-check, meeting-prep, ship-recap).

Everyday plays that DO exist (avoid): umbrella-check, before-you-click, scamcheck, daily-inbox-triage,
gmail-subscription-audit, gmail-price-hike-detector, subscription-free-trial-sentinel,
return-warranty-guardian, mac-storage-report/disk-diet/storage-cleanup-scan, downloads-filed,
rss-morning-brief, 5× HN digests, jobwatch/headhunter/applyradar, calorie-meal-advisor,
smart-fitness-coach, start-my-day, morning-workstation-prep, traffic-check-tomtom, 5× weather,
calendar-load-audit, ics-meeting-cost, commitment-capacity-check, password-breach-check, ssh-key-audit,
laptop-loss-drill, timezone-hazards, dupe-sweep, streak-truth, dont-forget, keep-my-notes.

Searches that returned NOTHING: browser tabs/bookmarks/history, battery, wifi/network (personal),
health/sleep/screen time, notes/journal vault, contacts/birthdays, bank statements/receipts/tax,
apps never opened, reboot/pending updates, habit tracker, todo, recipes, groceries, wardrobe.

## Ideas (all: python3 stdlib, zero keys, read-only, local files only, one shareable number)

1. tab-debt — Chrome/Safari session files → open tab count, oldest tab age, duplicate tabs, reading-list
   backlog. Leaderboard-able ("213 tabs, oldest from March").
2. battery-truth — pmset + system_profiler → cycle count, health %, top energy hogs right now, charge
   habit. Leaderboard-able on cycle count.
3. reboot-debt — uptime + softwareupdate -l + login items/launch agents → days since restart, pending
   updates, boot tax. Funny shareable number.
4. wifi-doctor — networksetup/airport, gateway ping, DNS latency, captive-portal probe → "your wifi /
   your ISP / the site" verdict. Personal counterpart to provider-outage-triage.
5. browser-day — Chrome/Safari History sqlite (copied, read-only) → where the browsing day went, top
   domains, doomscroll share, first/last activity. Nothing leaves the machine.
6. health-brief — Apple Health export.xml → weekly steps, sleep, resting HR, trend vs last month, one card.
7. statement-diet — any bank/card CSV → recurring charges, forgotten subscriptions, price creep,
   month-over-month. No bank login; nothing sent anywhere.
8. birthday-radar — Contacts AddressBook sqlite → birthdays next 30 days, contacts missing birthdays,
   duplicates.
9. app-graveyard — /Applications via mdls last-used → apps untouched 6+ months, GB reclaimable, brew
   casks never launched.
10. vault-pulse — Obsidian/markdown folder → notes never revisited, orphans (no links in/out), daily-note
    streak, growth per week.
11. desktop-clutter / screenshot-graveyard — Desktop + screenshots by age/GB → clutter score,
    leaderboard-able.
12. receipt-ledger — Mail.app local .emlx or Downloads invoices (text/HTML only) → spend by vendor by
    month. Lower priority: PDF parsing needs non-stdlib.

Reuse: comped.sh door pattern, standalone one-file entry, tests asserting param parity, and the
gotcomped.com leaderboard (generalise /api/score with a `play` column) for 1, 2, 3, 11.
