Your address book already knows every birthday in it. It mentions them on the morning of, which is the one moment the information is useless. This reads the book you already have and sorts it by how soon, so the next one is a number of days rather than a surprise.

Three sources, any of which is enough. The macOS Contacts database is copied and reopened read-only, so the live database is never locked, journalled or upgraded by being looked at; when macOS refuses the read the Play says exactly that and names Full Disk Access as the fix rather than reporting an empty address book. Any folder of vCard files works, which is what every contacts app on every platform exports. So does a CSV export from Google Contacts or Outlook, with the columns matched by name.

You get the next birthdays with the weekday and the age each person is turning, today's if there are any, and then the part a contact list never tells you: how much of the book has no birthday at all, how many birthdays carry no year so no age can be shown, which names appear more than once, and which contacts have neither an email nor a phone number. A birthday on 29 February is placed on the 28th in a common year rather than skipped.

Names are printed as initials unless you set redact=false, and no email address or phone number is ever written into the report, though both are read to find duplicates.

- Reads: only the locations listed above. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
- Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
