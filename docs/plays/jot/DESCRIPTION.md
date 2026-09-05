A thought arrives while you are doing something else. `note='ring the dentist'` and it is in your notes, timestamped, and you are back to what you were doing. No app to open, no window to find, no place to decide on.

It appends `- 14:22 ring the dentist` to one Markdown file inside your vault — plain Markdown, so Obsidian, Logseq, a text editor or `cat` all read it the same way — and mirrors the capture to its own log, so the count and the streak survive you moving the vault. The same note twice within a minute is refused, because the second one is a slip of the hand rather than a second thought. An hour later the same words are a new thought and are captured.

Leave `vault_dir` empty and it writes to the log only, touching nothing in your notes at all.

- Reads: its own log, and the one inbox file inside `vault_dir` to count what is sitting there. Not the rest of your vault.
- Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
- Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. What you capture here stays on the machine.
- Writes: one appended line to `~/.rote-micro/jot.jsonl` and one appended line to `<vault_dir>/<inbox>`. Both are appends: nothing in your notes is deleted, truncated or rewritten in place, and no other file in the vault is opened for writing. The exact path written is printed in the output.
- Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log and vault are not opened.

See also: `vault-pulse`, which measures the vault this one fills — orphans, broken links, and the notes you never went back to. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.
