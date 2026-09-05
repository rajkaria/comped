Run this on anything you are about to paste into a chat, an agent, an issue or a screenshot. It tells you what is in there that should not leave your machine, and hands back the same text with those parts replaced, ready to paste.

It knows the literal shapes: AWS access key ids, GitHub tokens including fine-grained ones, Slack, Stripe live keys, Google, OpenAI, Anthropic, Twilio, SendGrid, npm and PyPI tokens, PEM and OpenSSH private key blocks, SSH public keys, JWTs, and connection strings carrying a password. On top of those it reads assignments: a name that says secret, token, password or api_key whose value is at least twelve characters and random enough — measured as Shannon entropy, not guessed — is reported too.

Precision is the whole product, because a checker that cries wolf gets turned off within a week and then it is protecting nothing. So `API_KEY=your-key-here` is not a finding. Neither is `${GITHUB_TOKEN}`, `$MY_VAR`, `<your-secret>`, `changeme`, a value made of one repeated character, Stripe's own `sk_test_` keys, or AWS's documented `AKIAIOSFODNN7EXAMPLE`. Every one of those exclusions has its own test.

The verdict is one of three words. `safe` means paste it. `redact` means there are things to take out first, and the redacted copy is printed for you. `do-not-paste` means at least one of them is a live credential shape.

- Reads: the text you pass, or the file or folder at `path` (up to 200 files, 2 MB each). Nothing else.
- Never reads: any credential store, keychain or token file of its own accord. It reads only what you point it at.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. The thing that finds your secrets is the last thing that should have a network stack, and it does not have one.
- Writes nothing. The redacted copy is printed, never saved.
- Never prints what it found. Every finding is masked to its first four and last two characters plus a length, in the human block and in the JSON alike, and a test asserts that the original value appears in neither.
- Runs cold: set `demo=true` to scan a bundled synthetic `.env` with nothing configured.

See also: `safe-to-commit`, which runs the same detectors over your staged files before the commit, and `whatis`, which peels the thing rather than judging it. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
