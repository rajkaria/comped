Something opaque is on your clipboard and you need to know what it is before you can do anything with it. Paste it here. This identifies it and then peels it: a base64 blob holding gzip holding JSON holding a JWT is one input and four layers, and you get all four.

It reads JWTs (algorithm, every claim, and whether the thing expired four hours ago or expires in ninety days), base64 and base64url, hex, percent-encoding, gzip, JSON described by its shape rather than dumped at you, unix time in seconds, milliseconds, microseconds or nanoseconds, UUIDs v1 through v7 with the timestamp that is buried inside a v1 and a v7, ULIDs, IPv4 and IPv6 with the scope spelled out (private, loopback, link-local, carrier-grade NAT), CIDR ranges with their size, MAC addresses, semantic versions, cron expressions, hex colours, data URIs, e-mail addresses, URLs with the query string broken into pairs, hashes named by length, and the magic bytes of a PDF, PNG, ZIP or SQLite file sitting behind a base64 wrapper.

The order the detectors run in is the design. A forty-character git object id is reported as a sha1, not offered to the base64 reader, because the more constrained shape always wins. And where two readings are genuinely possible the output says so rather than picking quietly: a ten-digit integer is read as a time only when it lands between 2001 and 2038, and the note explaining that choice is printed next to the answer.

- Reads: the text you pass in, and nothing else. There is no file access, no clipboard access, and no directory to configure.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, which a test in the repository asserts on every commit. It does not even use `urllib.parse`; the percent-decoder is forty lines in the package, so the offline claim needs no exception.
- Writes nothing. No state, no cache, no output file.
- A JWT signature is never printed. You get its first eight characters and its length, which is enough to recognise it in your own file and not enough to use.
- Runs cold: set `demo=true` to peel a bundled synthetic token with nothing configured.

See also: `is-it-secret`, which reads the same kind of paste and tells you what to redact, and `fits`, which tells you how big it is and what it costs to send. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
