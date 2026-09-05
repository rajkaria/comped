macOS records the last time you opened every application and never shows you the list. This asks Spotlight for those dates, measures each bundle on disk, and turns "what can I delete" into a list with evidence on every row.

It also answers a question nobody thinks to ask. Sixteen bytes into an application's executable is the list of architectures it ships, and on an Apple silicon machine an app with no arm64 slice runs under translation every single time you open it. Reading that needs no tools and runs no code: the header is just read. Apps still shipping Intel-only are listed with their sizes.

The report gives the applications unopened past your threshold, sorted by what they cost you in disk, the ones with no recorded opening at all, the total that would come back, anything installed twice under the same bundle identifier, and your Homebrew casks including superseded versions still on disk and casks whose application is no longer anywhere.

Every date says where it came from. Spotlight answers for most applications; where it has no record the file access time is used instead and the row is labelled as such, because the two are not the same measurement and mixing them silently would make the whole list untrustworthy. A bundle too large to walk inside the per-app file cap has its size reported as a lower bound and is counted.

- Reads: only the locations listed above. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
