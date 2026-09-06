A browser will show you the last nine things you opened. It will not tell you that one domain took a fifth of your quarter, that you opened the same question thirty-one times, or that your longest unbroken run at one site was four hours on a Tuesday afternoon. All of that is already sitting in a SQLite file on this machine, so this reads it and says so.

Three families, three schemas, three different epochs, read independently and with no browser running. Chromium-family browsers, Firefox-family browsers and Safari each store visits their own way; each profile is read separately, so a second Chrome profile is its own row. The database is copied and opened read-only, so a browser that is running is not disturbed and nothing is ever written back to it.

You get the visit count over the window, the domains that took the most of it, a category rollup from a lookup table that ships inside the package so you can read what it claims, sessions reconstructed from the gaps between visits, the longest single-domain run with the day it happened, and the hour-of-day and weekday shapes. Repeat visits to the same URL are counted separately, because opening one page thirty-one times is a different fact from opening thirty-one pages.

What it reads is the history table and nothing else. The code names, once and in one place, the stores it deliberately never touches — form data, saved logins, autofill — and a test asserts those words appear nowhere else in the module: not as a table name, not as a path, not as a query. URLs are reduced to hostnames on the card and query strings never appear anywhere.

- Reads: the visit history table of each browser profile listed above, through a read-only copy. Nothing else on your disk is opened.
- Never reads: saved passwords, autofill, form data, cookies, or any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. No URL you visited is looked up anywhere; the categories come from a table bundled in the package.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a browser this machine does not have, or one that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic history databases with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
