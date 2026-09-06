# Launch pack

Twenty-one Plays are published and 19 of 21 sit at one download, which is the run that verified
them. Nothing has ever been posted anywhere. That is the whole problem, and it is the cheapest one
in the project to fix.

Everything below is ready to paste. Swap the numbers for your own current ones before you post:
run `comped` and read `~/comped/comped-share.txt`, and run `desktop-clutter` and `tab-debt` for the
two lines that need a figure. Never post a number you have not just seen.

## The one thing to understand before posting

The audience splits in two, and the pitch is not the same for both.

**People who already have rote.** The Playoffs Discord, the registry feed, anyone who has run
somebody else's Play this week. For them every one of the twenty-one is one paste away, and each
paste is a download that counts. This is the highest-yield audience by a distance and it is small
enough to talk to individually. Lead with the Plays.

**Everyone else.** X, LinkedIn, Hacker News, Reddit. For them, twenty of the twenty-one need an
account they have never heard of, so leading with the Plays converts nobody. Lead with the one
door that needs nothing (`curl -fsSL https://gotcomped.com/comped.sh | sh`) and let the card, the
board and https://gotcomped.com/plays.html carry the other twenty.

Order matters. Discord first, because it converts today. The rest can follow within the hour.

---

## 1. Discord, the sharing channel

Three posts, spaced through the day. One firehose of twenty-one links reads like a dump and gets
scrolled past; three posts with a number in each get read.

### Post A, now. The flagship.

> I built `comped`. It reads the session transcripts Claude Code, Codex, Pi and OpenCode already
> write on your machine and tells you what the last 30 days would have cost at API list price
> against what you actually pay.
>
> Mine came back **13.3x**. $2,623 of AI for $197.
>
> ```
> rote play run https://play.modiqo.ai/rajkaria/comped
> ```
>
> Three things I would want to know before running someone else's Play on my own logs:
> it never opens `~/.claude.json` or `~/.codex/auth.json`, and there is a test that greps the
> source to prove it. Your plan tier is inferred from the model ids in the logs, never read from
> an account, and every other tier is priced beside it. The core imports no `urllib`, `http` or
> `socket`, so it cannot phone home; the one step that does is a separate short file you can read,
> and `leaderboard=false` turns it off.
>
> There is a board: https://gotcomped.com/leaderboard.html
>
> If you would rather not make an account to find out, `curl -fsSL https://gotcomped.com/comped.sh | sh`
> does the same thing in a temp directory and deletes itself.

### Post B, a few hours later. The six that read your machine.

> Follow-up on the same idea, away from agents this time: six Plays that read files your machine
> already keeps and never shows you.
>
> `desktop-clutter` graded mine **F**, with 164 duplicate groups sitting in Desktop and Downloads.
> `tab-debt` found my oldest open tab was **21 months** old.
>
> ```
> rote play run https://play.modiqo.ai/rajkaria/desktop-clutter demo=true
> rote play run https://play.modiqo.ai/rajkaria/tab-debt demo=true
> ```
>
> `demo=true` runs against bundled fixtures, so you can watch one work before pointing it at
> anything of yours. Drop it for the real run.
>
> Also `app-graveyard` (what you stopped opening, and what is still Intel-only), `vault-pulse`
> (orphan notes, broken links, daily-note streak), `birthday-radar`, and `receipt-ledger`.
> All six read-only, stdlib Python, no network. The browser format readers are written from the
> format up: Chrome's session file is a binary command log and Firefox's is a compressed
> container, so both got a decoder.
>
> All of them, with a paste-ready line each: https://gotcomped.com/plays.html

### Post C, evening. The twelve you run on reflex.

> Last batch. Twelve Plays small enough to run many times a day.
>
> ```
> rote play run https://play.modiqo.ai/rajkaria/whatis text=aHR0cHM6Ly9nb3Rjb21wZWQuY29t
> rote play run https://play.modiqo.ai/rajkaria/safe-to-commit repo=.
> rote play run https://play.modiqo.ai/rajkaria/is-it-secret path=some-file-you-are-about-to-paste
> ```
>
> `whatis` peels an opaque string: base64 holding gzip holding JSON holding a JWT is one input and
> four layers, and you get all four. `safe-to-commit` parses `.git/index` directly, with no
> subprocess, and tells you what is staged that should not enter history. `is-it-secret` hands back
> the same text with the credentials replaced, and never prints what it found.
>
> Plus `fits`, `cron-when`, `last-turn`, `budget-left`, `since-last`, `punch`, `spent`, `jot`,
> `streak`. Twenty-one in total now, three stdlib-only cores, no pip install anywhere:
> https://gotcomped.com/plays.html

### While you are in there

Reciprocity is the mechanic in a room this size, and it is not a trick if you mean it. Run three
or four other people's Plays today and reply with what they actually found on your machine, with
the number. People run the Play of the person who ran theirs. `sidships/token-tab` (34 downloads),
`adnandev/skill-audit` (7) and `lgoyal6/agent-spend-ledger` are all in the same territory as
comped and their authors are the people most likely to care about it.

---

## 2. X

A thread. The first post has to work with no context and no link, because the link costs reach.

> Your AI coding subscription writes down every token it spends. Nobody reads those files.
>
> I read 30 days of mine.
>
> $2,623 of API usage. I pay $197.
>
> 13.3x.

> 2/ It is not a bill. You are on a subscription and you paid what you paid. It is what the same
> work would have cost at the provider's published API prices, which is a fair way to ask what the
> plan is actually worth to you.

> 3/ You do not tell it anything. It works out which AI you run from the model ids in the logs,
> then prices every plan those providers sell and marks the most expensive one that fits, so the
> number it gives you is the smallest one you could honestly claim.

> 4/ Your logs never leave. The part that reads them imports no urllib, no http, no socket, and a
> test proves it. It never opens a credential file. The only thing that leaves is your score, to a
> leaderboard, and one parameter turns even that off.

> 5/ One line, no account, nothing installed. It downloads about 40 KB of stdlib Python to a temp
> directory, runs, and deletes itself.
>
> curl -fsSL https://gotcomped.com/comped.sh | sh
>
> Board: gotcomped.com

> 6/ It is one of twenty-one Plays I published this week on the same rule: your machine already
> wrote the answer down and nothing reads it back.
>
> How many browser tabs are open and how old is the oldest. What is staged that should not enter
> git history. What that opaque string actually is.
>
> gotcomped.com/plays.html

**The reply that gets you the most reach:** when anyone posts their number back, reply with where
they land in the tier list. That is what makes it a game rather than an announcement.

---

## 3. LinkedIn

> Every AI coding tool on your machine keeps a receipt for every request it makes. Model, tokens
> in, tokens out, cache hits. Nobody ever reads those files.
>
> I spent this week building something that does. Thirty days of my own sessions came to $2,623 at
> published API prices. I pay $197 a month. That is 13.3 times.
>
> The interesting part was not the number, it was what it takes to get it right. Claude Code writes
> one line per content block, so about four in ten usage lines are streaming duplicates of the same
> API call and a naive sum is badly wrong. Codex writes cumulative counters, so per-turn values are
> differences. Subagent spend lives in a subdirectory most tools never look in.
>
> It reads only counts and model ids, never your prompts or your code, and it never opens a
> credential file. The part that reads your logs cannot make a network call, and there is a test
> that proves it rather than a paragraph that claims it.
>
> One line, no account, nothing installed: https://gotcomped.com
>
> It is one of twenty-one small tools I published this week on the same idea. Your machine already
> wrote the answer down, and nothing reads it back to you.

---

## 4. Hacker News

Title (the number in the title is what gets clicked, and it is true):

> Show HN: Comped: my AI subscription comped me $2,623 this month, and I can prove it

First comment, posted by you immediately after submitting:

> Author here. Every AI coding tool writes a transcript with a usage record per request: model,
> uncached input, cache writes, cache reads, output. This reads those, prices them against a
> bundled table that carries its source URL and an as-of date, and divides by what your plan
> actually costs.
>
> The parsing is most of the work. Claude Code writes one line per content block, so roughly four
> in ten usage lines are streaming duplicates of the same API call and have to be collapsed on
> (message.id, requestId) before anything is priced. Codex writes cumulative counters, so per-turn
> values are differences, not values. Subagent transcripts live in a subdirectory.
>
> Two things I decided early and would defend. It never reads your account: which AI you run is
> inferred from the model ids already in the logs, and since no local file honestly knows your
> plan tier, it prices every tier the provider sells and marks the most expensive one that fits.
> Your real score is at least the one it prints. And a model missing from the price table is
> reported with its token counts and left unpriced, never guessed.
>
> Stdlib Python, no dependencies. The core imports no urllib, http or socket, which a test
> asserts by walking the AST. The one network step is a separate 100-line file that posts the
> score to a leaderboard, and leaderboard=false skips it, at which point the run makes no network
> calls at all.
>
> One line, no account, nothing installed, deletes itself: curl -fsSL https://gotcomped.com/comped.sh | sh
> Source: https://github.com/rajkaria/comped

Post it on a weekday morning US Eastern. Answer every comment within the hour, especially the
hostile ones about piping curl into sh, and answer that one with the checksum and the fact that
the archive is public and readable before you run it.

---

## 5. Reddit, r/ClaudeAI

Title:

> I added up 30 days of my Claude Code usage at API prices. $2,623 on a $197 plan.

Body:

> Claude Code keeps a transcript of every session with a usage record per request. I wrote
> something that reads them and prices them at published API rates.
>
> Thirty days: $2,623.20 at list. I pay $197. So 13.3x, and 98% of my input tokens were cache
> reads, which is the only reason the number is that shape.
>
> Two things worth knowing if you try it. Roughly four in ten usage lines in a Claude Code
> transcript are streaming duplicates of the same API call, so anything that just sums the file
> tells you a number about twice too big. And subagent transcripts live in a subdirectory, so
> anything that skips those undercounts you.
>
> It never opens ~/.claude.json or any credential file, it does not read your prompts or your code,
> and the part that reads your logs cannot make a network call.
>
> One line, no account, nothing installed: curl -fsSL https://gotcomped.com/comped.sh | sh
> Source: https://github.com/rajkaria/comped
>
> Curious what everyone else's multiplier is, particularly people on Pro rather than Max.

---

## Answers to the questions you will actually get

**"Why would I pipe curl into sh?"** You would not have to. The archive is at
https://gotcomped.com/comped.tar.gz with its sha256 published beside it, the script is sixty lines
and readable in the browser, and `rote play run https://play.modiqo.ai/rajkaria/comped` shows you a
consent screen listing every file it touches before anything happens. The checksum is served from
the same origin as the archive, so it proves the download arrived whole, not that the origin is
honest. That is said on the site in those words.

**"So it uploads my logs."** No. The core cannot: it imports no urllib, http or socket, and a test
walks the AST to prove it. One separate step posts your score, and only your score. The exact
payload is written to `~/comped/comped-rank.json` before it is sent, so you can read what went.
`leaderboard=false` and there is no network call at all.

**"Is this a bill?"** No, and the tool says so on the card. You are on a subscription and you paid
what you paid.

**"How does it know my plan?"** It does not, and it refuses to find out, because that would mean
reading your account. It prices every plan the provider sells and assumes the most expensive one
that fits, which is the least flattering honest answer.

**"Does it work on Windows?"** `npx comped`. Every commit installs and runs it on a Windows runner
before it ships. The curl line needs WSL.

---

## What to do in the next three hours

1. Run `comped` and `desktop-clutter` and `tab-debt` on your own machine right now and put the real
   numbers into the posts above. Nothing in this file is postable with someone else's figures.
2. Post A in Discord. Stay in the channel for an hour and answer everything.
3. Run three other people's Plays and reply with what they found on your machine.
4. Post the X thread and the LinkedIn post.
5. Post B in Discord in the afternoon, Post C in the evening.
6. Hacker News tomorrow morning US Eastern, not today, because you want to be at the keyboard for
   the first two hours after it goes up.
7. Add a row to `docs/adoption-log.md` tonight with the download counts and what you posted, so
   tomorrow you know which channel did anything.
