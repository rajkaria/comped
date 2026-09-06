An extension's install page shows its permissions once, in a dialog nobody re-reads, and then never again. The browser keeps the answer on disk for ever. This reads it and answers the question the browser stops asking after install day: what can see your bank tab, and is anyone still shipping updates for it.

Three families, read independently and with no browser running. Chromium-family browsers keep a manifest per extension and a settings entry per profile saying whether it is enabled, where it was installed from and which hosts you actually granted. Firefox-family browsers keep the same facts in their own store. Safari publishes rather less, and where it publishes nothing that is reported as nothing rather than filled in. Every profile is read separately, so a second Chrome profile is its own row.

You get the count, the extensions that can read every page you open, the ones that pair blanket page access with a second power — reading what you type, rewriting requests, seeing every tab — the ones nobody has shipped a fix for in a year, and the ones you installed and stopped using, which are the cheapest permissions to take back. Every tier says what it is based on, and a permission the manifest does not declare is never inferred.

This reads manifests and settings metadata only. It never opens extension storage: idle detection looks at the modification *time* of a state folder with `os.stat`, and the folder is never opened. Nothing under a local-storage, database or cookie path is opened by this Play, and a test in the repository asserts that those words appear nowhere in its code as a path, a table or a query.

- Reads: the extension manifests and profile settings files listed above, plus the modification time of each extension's state folder. Nothing else on your disk is opened.
- Never reads: extension storage, browsing data, cookies, or any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. Nothing is looked up about an extension anywhere; every judgement comes from files already on this machine.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a browser this machine does not have, or one that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic extension stores with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
