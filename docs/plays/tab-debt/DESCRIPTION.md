Your browser shows a tab strip. It never shows you a number, and it never shows you a date. Both are sitting in the session files the browser already writes, so this reads them and answers what the strip cannot: how many tabs are open across every browser on the machine, and how long since each one was actually looked at.

Four formats, read directly and with no browser running. Chrome, Brave, Edge, Chromium, Vivaldi, Opera and Comet keep the live tab set as an SNSS command log, which is replayed here rather than scanned, because the last navigation recorded for a tab is the page it is showing and a tab closed later must not appear at all. Firefox, Zen and LibreWolf keep theirs as JSON inside an LZ4 container, decoded here by a decompressor written for the purpose. Safari and Arc keep property lists and a JSON sidebar store. Every profile is read separately, so a second Chrome profile is its own row.

You get the count, the oldest tab with the date it was last used, an age histogram, the sites the tabs actually belong to, the pages open more than once and how many would close with nothing lost, and Safari's reading list backlog with the date each item was saved. A tab whose browser recorded no last-used time is counted in the total and left out of every age figure, and the number of those is printed, because a cold-tab count quietly computed over half your tabs would be worse than one that admits what it could not judge.

URLs are reduced to hostnames by default and query strings never appear anywhere, so the card is safe to show someone. Set keep_path=true to keep paths locally.

- Reads: only the locations listed above. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
