#!/usr/bin/env python3
"""Sync the single-source core into each Play's resources dir. `--check` verifies byte-identity (used by CI)."""
import hashlib, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYS = ["session-ledger", "comped", "wrong-turns"]
SRC = [("comped_core", ROOT / "comped_core"), ("prices.json", ROOT / "resources" / "prices.json"),
       ("plans.json", ROOT / "resources" / "plans.json"), ("fixtures", ROOT / "resources" / "fixtures")]
# Only comped posts to the leaderboard, and the poster lives outside the core so the core stays offline.
EXTRA = {"comped": [("post_score.py", ROOT / "leaderboard" / "post_score.py")]}

# The six daily Plays share a second core. Its demo fixtures ship inside the package, so one entry
# copies both and the byte-identity check below covers the fixtures as well as the code.
DAILY_PLAYS = ["tab-debt", "birthday-radar", "app-graveyard", "vault-pulse", "desktop-clutter",
               "receipt-ledger"]
DAILY_SRC = [("daily_core", ROOT / "daily_core")]


def tree_hash(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    files = sorted(x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts) if p.is_dir() else [p]
    for f in files:
        h.update(str(f.relative_to(p if p.is_dir() else p.parent)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def main(check=False):
    bad = 0
    for slug in PLAYS + DAILY_PLAYS:
        dst = ROOT / "plays" / slug / "resources"
        sources = (DAILY_SRC if slug in DAILY_PLAYS else SRC + EXTRA.get(slug, []))
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
