A photo library only ever grows. The shutter fires ten times to get one usable frame, every screenshot lands next to the family album, and the same image arrives again from a message, an AirDrop and a download. None of that is visible in the Photos app, which is organised by date and by face rather than by waste, so the honest number — how much of this is not really photographs — has never been on screen.

It reads the Photos library's own database, through a copy opened read-only so the library is never touched, and a folder of loose images alongside it. What it reads is file metadata: name, size, dates, dimensions. For duplicate confirmation it hashes bytes; no image is ever decoded, displayed, uploaded or moved.

Three separate claims, each carrying its own confidence and never added together without saying which is which. Files whose bytes are byte-for-byte identical: a fact. Extra frames from a burst, inferred from capture time, dimensions and file name: an inference. Screenshots old enough to have served their purpose: a judgement, and you set the age. You get all three with their own totals, the largest groups by name, and how much disk each class would give back.

Two things this deliberately does not do. It never deletes, moves or renames anything: the output is a list to review, and every removal stays a decision you make in the Photos app, where there is an undo. And it never compares images by content similarity — the standard library decodes neither JPEG nor HEIC, an imaging package would break the stdlib-only promise, and shelling out to a converter would break the no-child-process promise. So "duplicate" here always means identical bytes, and "near-duplicate" always means metadata, never pixels.

- Reads: the Photos library database (through a read-only copy) and file metadata under the image folder you name. Candidate duplicates are hashed. Nothing else on your disk is opened.
- Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. It reads no face, place or person data, and no image is decoded.
- Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. No photo, thumbnail or hash leaves this machine.
- Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output. Nothing in your library or your image folder is ever modified.
- Degrades, never fails: a library this machine does not have, or one that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
- Runs cold: set `demo=true` to run the whole Play against a bundled synthetic library and image folder with nothing configured, before you point it at your own machine.

Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.
