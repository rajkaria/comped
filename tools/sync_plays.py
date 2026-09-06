#!/usr/bin/env python3
"""Sync the single-source core into each Play's resources dir. `--check` verifies byte-identity (used by CI)."""
import hashlib, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYS = ["session-ledger", "comped", "wrong-turns"]
SRC = [("comped_core", ROOT / "comped_core"), ("prices.json", ROOT / "resources" / "prices.json"),
       ("plans.json", ROOT / "resources" / "plans.json"), ("fixtures", ROOT / "resources" / "fixtures")]
# Only comped posts to the leaderboard, and the poster lives outside the core so the core stays offline.
EXTRA = {"comped": [("post_score.py", ROOT / "leaderboard" / "post_score.py")]}

# The sixteen daily Plays share a second core. One entry copies the whole package tree, so the
# byte-identity check below covers everything that ships beside the code: `fixtures/` (the demo
# data) and `tables/` (the bundled lookup tables `common.load_table` reads -- without them
# `load_table` returns {} inside a published Play and where-it-went's category rollup empties
# silently, so a missing table is a correctness bug, not a cosmetic one).
DAILY_PLAYS = ["tab-debt", "birthday-radar", "app-graveyard", "vault-pulse", "desktop-clutter",
               "receipt-ledger", "bus-factor", "night-shift", "kept", "extension-reach",
               "where-it-went", "photo-debt", "what-grew", "standing-cost", "reply-debt",
               "upstream-pulse"]
DAILY_SRC = [("daily_core", ROOT / "daily_core")]
# Everything under `daily_core` must reach a package; naming the subdirectories here is what makes
# a new one a test failure rather than a silent omission.
DAILY_SUBDIRS = ["fixtures", "parsers", "scan", "tables"]

# The three Plays with a network half. The fetcher lives outside the core for the same reason
# `leaderboard/post_score.py` lives outside comped_core: the core stays verifiably offline, and
# everything that opens a connection sits in one short file a reader can check.
DAILY_EXTRA = {
    "standing-cost": [("fetch/calendar_partial.py", ROOT / "fetch" / "calendar_partial.py")],
    "reply-debt": [("fetch/mail_partial.py", ROOT / "fetch" / "mail_partial.py")],
    "upstream-pulse": [("fetch/registry_partial.py", ROOT / "fetch" / "registry_partial.py")],
}

# The twelve micro Plays share a third core. Three of them price tokens, and rather than grow a
# second price list that would drift, those three carry comped_core and its table as well.
MICRO_PLAYS = ["whatis", "fits", "is-it-secret", "cron-when", "punch", "spent", "jot", "streak",
               "last-turn", "budget-left", "since-last", "safe-to-commit"]
MICRO_SRC = [("micro_core", ROOT / "micro_core")]
MICRO_PRICED = {"fits", "last-turn", "budget-left"}
MICRO_PRICE_SRC = [("comped_core", ROOT / "comped_core"), ("prices.json", ROOT / "resources" / "prices.json")]


def tree_hash(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    files = sorted(x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts) if p.is_dir() else [p]
    for f in files:
        h.update(str(f.relative_to(p if p.is_dir() else p.parent)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def main(check=False):
    bad = 0
    for slug in PLAYS + DAILY_PLAYS + MICRO_PLAYS:
        dst = ROOT / "plays" / slug / "resources"
        if slug in DAILY_PLAYS:
            sources = DAILY_SRC + DAILY_EXTRA.get(slug, [])
        elif slug in MICRO_PLAYS:
            sources = MICRO_SRC + (MICRO_PRICE_SRC if slug in MICRO_PRICED else [])
        else:
            sources = SRC + EXTRA.get(slug, [])
        for name, src in sources:
            target = dst / name
            if check:
                if not target.exists() or tree_hash(target) != tree_hash(src):
                    print("DRIFT {0}/{1}".format(slug, name))
                    bad += 1
                continue
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, target)
        print("{0}: {1}".format(slug, tree_hash(dst)[:12]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
