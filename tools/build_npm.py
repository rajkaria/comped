#!/usr/bin/env python3
"""Assemble the npm package: `npx comped` for anyone who has node but not a spare account.

npm is a delivery lorry here, not a dependency. The package carries the same standard-library
Python the download and the Play carry, byte for byte, and bin/comped.js does nothing but find an
interpreter and hand it payload/comped.py. There are no node dependencies, and there never will
be: a tool that reads your session logs should not ask you to trust a dependency tree as well.

    python3 tools/build_npm.py     assemble npm/
    npm pack npm/                  make the tarball, to inspect before publishing
    npm publish npm/               publish it (needs your own npm login; nothing here holds one)
"""
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import build_dist  # noqa: E402

PKG = ROOT / "npm"
PAYLOAD = PKG / "payload"

DESCRIPTION = ("What your AI coding subscription would have cost at full API price, read from the "
               "session logs your tools already keep. Your logs never leave your machine.")


def package_json(version: str) -> dict:
    return {
        "name": "comped",
        "version": version,
        "description": DESCRIPTION,
        "bin": {"comped": "bin/comped.js"},
        "files": ["bin/", "payload/", "README.md", "LICENSE"],
        "keywords": ["ai", "claude", "codex", "chatgpt", "usage", "cost", "tokens",
                     "claude-code", "llm", "pricing", "leaderboard"],
        "homepage": "https://gotcomped.com",
        "repository": {"type": "git", "url": "git+https://github.com/rajkaria/comped.git"},
        "bugs": {"url": "https://github.com/rajkaria/comped/issues"},
        "license": "MIT",
        "author": "rajkaria",
        # No dependencies, and no install scripts. Nothing runs until you type comped.
        "dependencies": {},
        "engines": {"node": ">=14"},
        "preferGlobal": True,
    }


README = """# comped

{description}

```bash
npx comped
```

That is the whole thing. It reads the logs your AI coding tools already write, prices the last 30
days at the provider's public API rates, and prints a card with your **comp score**: how many times
over your subscription paid for itself. Then it posts just that score to
[gotcomped.com](https://gotcomped.com) and tells you your rank.

## What it needs

**Python 3.9 or newer on your PATH.** Every Mac has it. comped is standard-library Python; this
package has no node dependencies and no install script. `bin/comped.js` finds an interpreter and
runs `payload/comped.py`. That is all it does.

## What it reads, and what it sends

- **Reads:** session logs under `~/.claude/projects`, `~/.codex/sessions`, `~/.pi/agent/sessions`
  and `~/.local/share/opencode/storage`. Nothing else.
- **Never reads:** `~/.claude.json`, `~/.codex/auth.json`, or any credential, keychain or token
  file. Which AI you use is worked out from the model ids already in those logs. Your plan tier is
  never read from your account.
- **Sends:** one thing, once, after the card is written: your score. The exact payload is saved to
  `~/comped/comped-rank.json` before it goes, so you can read it. `leaderboard=false` sends nothing
  at all, and then the run makes no network call whatsoever.
- **Writes:** only under `~/comped`. Every path is listed in the report.

## Options

Arguments are `key=value`, the same ones the rote Play takes:

```bash
npx comped handle=yourname            # your name on the board instead of anon-xxxx
npx comped plan=claude-pro-20         # the tier you actually pay for
npx comped leaderboard=false          # the card only, no network call at all
npx comped days_back=7                # a different window
npx comped --help                     # all fourteen
```

Try it on the sample logs that ship with it, before pointing it at your own:

```bash
npx comped claude_dir=resources/fixtures/claude codex_dir=resources/fixtures/codex leaderboard=false
```

## Other ways to run it

- **No node:** `curl -fsSL https://gotcomped.com/comped.sh | sh`
- **As an inspectable rote Play,** with a consent screen listing every path it will touch:
  `curl -fsSL https://gotcomped.com/run.sh | sh`

Same code, same parameters, same card. Full docs at <https://gotcomped.com/docs.html>.

MIT licensed. Source: <https://github.com/rajkaria/comped>
"""


def main() -> int:
    version = build_dist.version()
    if PAYLOAD.exists():
        shutil.rmtree(PAYLOAD)
    count = 0
    for name, data in build_dist.members():
        if name in ("LICENSE", "VERSION"):
            continue                      # they live at the package root, not in the payload
        out = PAYLOAD / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        count += 1
    (PKG / "package.json").write_text(json.dumps(package_json(version), indent=2) + "\n", encoding="utf-8")
    (PKG / "README.md").write_text(README.format(description=DESCRIPTION), encoding="utf-8")
    (PKG / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
    (PKG / ".npmignore").write_text("# Everything shipped is named in package.json's files list.\n", encoding="utf-8")
    print("wrote {0} (comped@{1}, {2} payload files)".format(PKG, version, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
