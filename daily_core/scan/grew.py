"""what-grew: what got bigger since last time, what got smaller, and what is safe to get back.

"Something ate 40 GB and nothing will tell you what." Every disk tool answers the wrong question:
they show what is big, and what is big is mostly what was always big. The useful question is what
*moved*, and no tool can answer it without having looked before. So this Play is built around a
baseline rather than a scan: one bounded `os.scandir` walk records a directory-size snapshot, and
every run after that diffs against it.

Four rules the rest of the module keeps:

1. The first run has nothing to compare against, and says exactly that. It writes the baseline and
   tells you when to come back. It never prints a zero delta as though the disk stood still.
2. Growth and shrinkage are both reported, in three separate classes — newly appeared, grew in
   place, deleted — plus shrank in place. A folder that vanished is not the same event as a folder
   that got smaller, and merging them loses the only fact worth knowing.
3. The reclaim number is regenerable bytes: caches and build output a command can rebuild. It is
   kept strictly apart from data nobody can regenerate, because a headline that mixes the two is
   an invitation to delete the wrong thing.
4. Nothing is deleted, moved or opened. The walk reads directory entries and `stat` results; the
   only file this module ever writes is its own baseline, under the caller's out_dir.

Sizes are on-disk sizes (`st_blocks` × 512) wherever the filesystem exposes them, so APFS clones
and sparse files do not inflate the total; the apparent total is reported alongside so the gap is
visible rather than silently chosen for you.
"""
import json
import os
import re
import shutil
from datetime import timedelta

from ..card import Card, pad
from ..common import (Budget, Source, baseline_read, baseline_write, day, delta, expand,
                      human_bytes, iso, parse_date, pct, plural, since_note)

KINDS = ("home",)

NAME = "whatgrew"                   # the current baseline, .whatgrew-baseline.json
HISTORY = "whatgrew-history"        # the retained ones, .whatgrew-history-baseline.json

DEFAULT_DEPTH = 4                   # directories are summarised this deep, so a baseline stays small
DEFAULT_FLOOR = 16 * 1024 * 1024    # and only directories this big are kept by name
DEFAULT_KEEP = 10                   # how many past snapshots are retained for `since`
GB = 1024.0 * 1024.0 * 1024.0

# Never descended into, and said so in the report. A volume that is not the one being measured is
# somebody else's disk; the rest are the filesystem's own bookkeeping, which is not your data.
SKIP_NAMES = ("Volumes", ".Trash", ".Trashes", ".fseventsd", ".Spotlight-V100",
              ".DocumentRevisions-V100", ".TemporaryItems", ".vol")

VERDICTS = ("regenerable", "safe to delete", "think first")

# ---------------------------------------------------------------- the known hogs
#
# One table, in one place, so a reader can check every claim this Play makes about their disk.
# `kind` is how the pattern is matched against a directory path relative to the scanned root:
#   prefix   — the path is exactly this, or starts with it followed by "/"
#   segment  — any single path component equals this
#   contains — the pattern appears anywhere in the path
# The first entry that matches wins, so the specific paths are listed before the generic names.
# `verdict` is exactly one of VERDICTS and answers one question: if this were gone tomorrow, what
# would it cost you? regenerable — a command rebuilds it. safe to delete — a cache, byte for byte
# re-downloadable. think first — it holds state or history that is not coming back on its own.

HOGS = (
    # -- caches with a vendor command that empties them ------------------------------------
    {"name": "Homebrew cache", "kind": "prefix", "pattern": "Library/Caches/Homebrew",
     "verdict": "safe to delete", "how": "brew cleanup"},
    {"name": "Homebrew downloads", "kind": "prefix", "pattern": "Library/Caches/downloads",
     "verdict": "safe to delete", "how": "brew cleanup"},
    {"name": "pip cache", "kind": "prefix", "pattern": "Library/Caches/pip",
     "verdict": "safe to delete", "how": "pip cache purge"},
    {"name": "pip cache", "kind": "prefix", "pattern": ".cache/pip",
     "verdict": "safe to delete", "how": "pip cache purge"},
    {"name": "npm cache", "kind": "prefix", "pattern": ".npm/_cacache",
     "verdict": "safe to delete", "how": "npm cache clean --force"},
    {"name": "yarn cache", "kind": "prefix", "pattern": "Library/Caches/Yarn",
     "verdict": "safe to delete", "how": "yarn cache clean"},
    {"name": "pnpm store", "kind": "prefix", "pattern": "Library/pnpm/store",
     "verdict": "safe to delete", "how": "pnpm store prune"},
    {"name": "pnpm store", "kind": "prefix", "pattern": ".local/share/pnpm/store",
     "verdict": "safe to delete", "how": "pnpm store prune"},
    {"name": "browser cache", "kind": "prefix", "pattern": "Library/Caches/Google/Chrome",
     "verdict": "safe to delete", "how": "the browser refills it; clearing costs you page loads"},
    {"name": "browser cache", "kind": "prefix", "pattern": "Library/Caches/com.apple.Safari",
     "verdict": "safe to delete", "how": "the browser refills it; clearing costs you page loads"},
    {"name": "browser cache", "kind": "prefix", "pattern": "Library/Caches/Firefox",
     "verdict": "safe to delete", "how": "the browser refills it; clearing costs you page loads"},
    {"name": "browser cache", "kind": "prefix", "pattern": "Library/Caches/BraveSoftware",
     "verdict": "safe to delete", "how": "the browser refills it; clearing costs you page loads"},
    {"name": "browser cache", "kind": "prefix", "pattern": "Library/Caches/Microsoft Edge",
     "verdict": "safe to delete", "how": "the browser refills it; clearing costs you page loads"},
    {"name": "browser cache", "kind": "prefix", "pattern": "Library/Caches/Arc",
     "verdict": "safe to delete", "how": "the browser refills it; clearing costs you page loads"},
    {"name": "iOS device support", "kind": "contains", "pattern": "xcode/ios devicesupport",
     "verdict": "safe to delete", "how": "Xcode re-downloads it the next time you attach a device"},
    {"name": "watchOS device support", "kind": "contains", "pattern": "xcode/watchos devicesupport",
     "verdict": "safe to delete", "how": "Xcode re-downloads it the next time you attach a device"},

    # -- build output and dependency trees a command rebuilds --------------------------------
    {"name": "Xcode DerivedData", "kind": "segment", "pattern": "deriveddata",
     "verdict": "regenerable", "how": "Xcode rebuilds it; the next build is slow, that is all"},
    {"name": "Gradle cache", "kind": "prefix", "pattern": ".gradle",
     "verdict": "regenerable", "how": "Gradle re-downloads and recompiles it"},
    {"name": "Maven repository", "kind": "prefix", "pattern": ".m2/repository",
     "verdict": "regenerable", "how": "Maven re-downloads it from the declared repositories"},
    {"name": "Cargo registry", "kind": "prefix", "pattern": ".cargo/registry",
     "verdict": "regenerable", "how": "cargo re-downloads it from crates.io"},
    {"name": "Go module cache", "kind": "prefix", "pattern": "go/pkg/mod",
     "verdict": "regenerable", "how": "go mod download, or go clean -modcache"},
    {"name": "node_modules", "kind": "segment", "pattern": "node_modules",
     "verdict": "regenerable", "how": "your package manager rebuilds it from the lockfile"},
    {"name": "virtualenv", "kind": "segment", "pattern": ".venv",
     "verdict": "regenerable", "how": "recreate it and reinstall from the requirements file"},
    {"name": "virtualenv", "kind": "segment", "pattern": "venv",
     "verdict": "regenerable", "how": "recreate it and reinstall from the requirements file"},
    {"name": "Next.js build", "kind": "segment", "pattern": ".next",
     "verdict": "regenerable", "how": "the next build writes it again"},
    {"name": "bytecode cache", "kind": "segment", "pattern": "__pycache__",
     "verdict": "regenerable", "how": "Python writes it again on import"},
    {"name": "build output", "kind": "segment", "pattern": "target",
     "verdict": "regenerable", "how": "a build output if this is a project folder; your build tool rebuilds it"},
    {"name": "build output", "kind": "segment", "pattern": "build",
     "verdict": "regenerable", "how": "a build output if this is a project folder; your build tool rebuilds it"},
    {"name": "build output", "kind": "segment", "pattern": "dist",
     "verdict": "regenerable", "how": "a build output if this is a project folder; your build tool rebuilds it"},

    # -- big, and holding something you would miss -------------------------------------------
    {"name": "Simulator runtimes", "kind": "segment", "pattern": "coresimulator",
     "verdict": "think first", "how": "delete unavailable simulators from Xcode, not by hand: this holds device state"},
    {"name": "Xcode archives", "kind": "contains", "pattern": "xcode/archives",
     "verdict": "think first", "how": "these are what symbolicate a shipped build's crash reports"},
    {"name": "Docker disk image", "kind": "contains", "pattern": "docker.raw",
     "verdict": "think first", "how": "docker system prune; the file itself holds every image and volume"},
    {"name": "Docker data", "kind": "contains", "pattern": "com.docker.docker",
     "verdict": "think first", "how": "docker system prune; deleting the folder loses your volumes"},
)


def classify(path: str):
    """The table row that describes this directory, or None. Read-only lookup, no filesystem access."""
    low = str(path or "").replace("\\", "/").lower().strip("/")
    if not low or low == ".":
        return None
    segments = [s for s in low.split("/") if s]
    for hog in HOGS:
        pattern = hog["pattern"].lower()
        kind = hog["kind"]
        if kind == "segment" and pattern in segments:
            return hog
        if kind == "prefix" and (low == pattern or low.startswith(pattern + "/")):
            return hog
        if kind == "contains" and pattern in low:
            return hog
    return None


# ---------------------------------------------------------------- reading

def read_source(source: str, budget: Budget, cfg: dict) -> tuple:
    """One bounded walk of cfg["root"], rolled up to cfg["depth"]. Returns (sources, snapshot)."""
    cfg = cfg or {}
    depth = _int(cfg.get("depth"), DEFAULT_DEPTH)
    floor = _int(cfg.get("floor_bytes"), DEFAULT_FLOOR)
    name = source or "home"

    if cfg.get("demo_root"):
        return _read_demo(name, cfg, depth, floor)

    root = expand(cfg.get("root") or "~")
    src = Source(name=name, path=str(root))
    if not root.is_dir():
        return [src.miss("no folder at {0}".format(root))], _blank(root, depth, floor)
    try:
        os.stat(str(root))
    except OSError as exc:
        return [src.miss("unreadable: {0}".format(exc.__class__.__name__))], _blank(root, depth, floor)

    snap = _measure(root, budget, depth, floor)
    note = "{0} folder(s) at depth {1}, floor {2}".format(len(snap["dirs"]), depth, human_bytes(floor))
    if snap["denied_count"]:
        note += "; {0} unreadable".format(plural(snap["denied_count"], "folder"))
    if budget.exhausted:
        note += "; stopped at the {0} bound".format(budget.hit)
    return [src.hit(snap["files"], note)], snap


def _measure(root, budget: Budget, depth_limit: int, floor: int) -> dict:
    """Depth-first scandir walk that stays on one volume and counts what it could not read.

    A number that quietly omits a locked folder is a wrong number, so every directory that refuses
    to open is recorded by name and reported rather than skipped.
    """
    sizes = {}
    files = 0
    apparent = 0
    on_disk = 0
    denied = []
    unreadable = []
    excluded = {"other volume": [], "system": [], "count": 0}
    placeholder_files = 0
    placeholder_bytes = 0
    blocks_seen = False
    try:
        root_dev = os.stat(str(root)).st_dev
    except OSError:
        root_dev = -1

    stack = [(str(root), 0, ".", ".")]
    while stack:
        here, depth, key, rel = stack.pop()
        if budget.exhausted:
            break
        try:
            with os.scandir(here) as it:
                entries = sorted(it, key=lambda e: e.name)
        except PermissionError:
            denied.append(rel)
            continue
        except OSError:
            unreadable.append(rel)
            continue

        for entry in entries:
            name = entry.name
            child_rel = name if rel == "." else rel + "/" + name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                st = entry.stat(follow_symlinks=False)
            except (OSError, ValueError):
                unreadable.append(child_rel)
                continue

            if is_dir:
                if name in SKIP_NAMES:
                    _note_excluded(excluded, "system", child_rel)
                    continue
                if root_dev >= 0 and st.st_dev != root_dev:
                    # A different device under this tree is a mount: another volume, or a network
                    # share. Counting it would attribute somebody else's disk to this one.
                    _note_excluded(excluded, "other volume", child_rel)
                    continue
                child_depth = depth + 1
                stack.append((entry.path, child_depth, child_rel if child_depth <= depth_limit else key,
                              child_rel))
                continue

            if not budget.spend(0):
                break

            size = int(getattr(st, "st_size", 0) or 0)
            blocks = getattr(st, "st_blocks", None)
            apparent += max(0, size)
            if blocks is None:
                real = max(0, size)
            else:
                blocks_seen = True
                real = max(0, int(blocks)) * 512

            if name.startswith(".") and name.endswith(".icloud"):
                placeholder_files += 1
                placeholder_bytes += max(0, size)
                continue
            if blocks is not None and int(blocks) == 0 and size > 0:
                # Present in the listing, occupying nothing: an iCloud file that was never pulled
                # down, or a clone the filesystem charges to somebody else. Either way it is not
                # bytes this disk would get back, so it is counted apart rather than added in.
                placeholder_files += 1
                placeholder_bytes += max(0, size)
                continue

            files += 1
            on_disk += real
            sizes[key] = sizes.get(key, 0) + real

    kept = dict((k, v) for k, v in sizes.items() if v >= floor)
    other = sum(v for k, v in sizes.items() if v < floor)
    free, total_disk, used_disk = _disk_usage(root)
    return {
        "root": str(root), "depth": depth_limit, "floor_bytes": floor,
        "dirs": kept, "other_bytes": other, "dir_total": len(sizes), "dirs_kept": len(kept),
        "total_bytes": on_disk, "apparent_bytes": apparent, "files": files,
        "denied": sorted(denied)[:40], "denied_count": len(denied),
        "unreadable": sorted(unreadable)[:20], "unreadable_count": len(unreadable),
        "excluded": {"other volume": sorted(excluded["other volume"])[:20],
                     "system": sorted(excluded["system"])[:20], "count": excluded["count"]},
        "placeholder_files": placeholder_files, "placeholder_bytes": placeholder_bytes,
        "on_disk_sizes": blocks_seen,
        "free_bytes": free, "disk_total_bytes": total_disk, "disk_used_bytes": used_disk,
        "complete": not budget.exhausted, "truncated": budget.hit, "readable": True,
    }


def _note_excluded(excluded: dict, bucket: str, rel: str):
    excluded["count"] += 1
    if len(excluded[bucket]) < 40:
        excluded[bucket].append(rel)


def _disk_usage(root) -> tuple:
    try:
        usage = shutil.disk_usage(str(root))
        return int(usage.free), int(usage.total), int(usage.used)
    except (OSError, ValueError, AttributeError):
        return 0, 0, 0


def _blank(root, depth: int, floor: int) -> dict:
    """A snapshot for a root that could not be read. Never written to a baseline: see analyse."""
    return {"root": str(root), "depth": depth, "floor_bytes": floor, "dirs": {}, "other_bytes": 0,
            "dir_total": 0, "dirs_kept": 0, "total_bytes": 0, "apparent_bytes": 0, "files": 0,
            "denied": [], "denied_count": 0, "unreadable": [], "unreadable_count": 0,
            "excluded": {"other volume": [], "system": [], "count": 0},
            "placeholder_files": 0, "placeholder_bytes": 0, "on_disk_sizes": False,
            "free_bytes": 0, "disk_total_bytes": 0, "disk_used_bytes": 0,
            "complete": True, "truncated": "", "readable": False}


def _read_demo(name: str, cfg: dict, depth: int, floor: int) -> tuple:
    """The demo reads a manifest of directory sizes, not a folder.

    A real walk of a git checkout would measure the checkout, which is nobody's disk problem; and a
    demo has to be able to show a week of growth, which no freshly cloned tree can.
    """
    path = expand(cfg["demo_root"]) / "sizes.json"
    src = Source(name="{0} (demo)".format(name), path=str(path))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [src.miss("fixture missing")], _blank(path.parent, depth, floor)
    if not isinstance(doc, dict) or not isinstance(doc.get("dirs"), dict):
        return [src.miss("fixture unreadable")], _blank(path.parent, depth, floor)

    snap = _blank(doc.get("root") or "/Users/demo", _int(doc.get("depth"), depth),
                  _int(doc.get("floor_bytes"), floor))
    snap["dirs"] = dict((str(k), int(_num(v))) for k, v in doc["dirs"].items())
    snap["other_bytes"] = _int(doc.get("other_bytes"), 0)
    snap["total_bytes"] = _int(doc.get("total_bytes"), sum(snap["dirs"].values()) + snap["other_bytes"])
    snap["apparent_bytes"] = _int(doc.get("apparent_bytes"), snap["total_bytes"])
    snap["files"] = _int(doc.get("files"), len(snap["dirs"]))
    snap["dir_total"] = snap["dirs_kept"] = len(snap["dirs"])
    snap["denied"] = [str(d) for d in (doc.get("denied") or [])][:40]
    snap["denied_count"] = _int(doc.get("denied_count"), len(snap["denied"]))
    snap["placeholder_files"] = _int(doc.get("placeholder_files"), 0)
    snap["placeholder_bytes"] = _int(doc.get("placeholder_bytes"), 0)
    snap["on_disk_sizes"] = bool(doc.get("on_disk_sizes", True))
    snap["free_bytes"] = _int(doc.get("free_bytes"), 0)
    snap["disk_total_bytes"] = _int(doc.get("disk_total_bytes"), 0)
    snap["disk_used_bytes"] = _int(doc.get("disk_used_bytes"),
                                   max(0, snap["disk_total_bytes"] - snap["free_bytes"]))
    snap["readable"] = True
    snap["demo_previous"] = _demo_previous(path.parent, snap)
    return [src.hit(snap["files"], "bundled fixture")], snap


def _demo_previous(root, snap: dict) -> dict:
    """The optional older snapshot beside the fixture, so the demo can show a delta and not a first run.

    Without it the bundled demo can only ever print the first-run card, which is the one card this
    Play exists to get past. The file is optional: a fixture that ships only `sizes.json` still
    demos correctly, it just demos the first run.
    """
    path = root / "sizes-previous.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict) or not isinstance(doc.get("dirs"), dict):
        return {}
    older = _blank(doc.get("root") or snap.get("root", ""),
                   _int(doc.get("depth"), snap.get("depth", DEFAULT_DEPTH)),
                   _int(doc.get("floor_bytes"), snap.get("floor_bytes", DEFAULT_FLOOR)))
    older["dirs"] = dict((str(k), int(_num(v))) for k, v in doc["dirs"].items())
    older["other_bytes"] = _int(doc.get("other_bytes"), 0)
    older["total_bytes"] = _int(doc.get("total_bytes"),
                                sum(older["dirs"].values()) + older["other_bytes"])
    older["apparent_bytes"] = _int(doc.get("apparent_bytes"), older["total_bytes"])
    older["files"] = _int(doc.get("files"), len(older["dirs"]))
    older["free_bytes"] = _int(doc.get("free_bytes"), 0)
    older["disk_total_bytes"] = _int(doc.get("disk_total_bytes"), 0)
    return {"captured": str(doc.get("captured") or ""), "payload": _payload(older)}


# ---------------------------------------------------------------- baselines

def _history_read(out_dir) -> list:
    """Every retained snapshot, oldest first.

    A missing, unreadable or older-schema file is a first run, not an error (see common.baseline_read):
    an upgrade costs the user one delta, never a failed run and a file to go and remove by hand.
    """
    if not out_dir:
        return []
    doc = baseline_read(out_dir, HISTORY)
    runs = ((doc.get("payload") or {}).get("runs") or []) if doc else []
    out = [r for r in runs if isinstance(r, dict) and r.get("captured") and isinstance(r.get("payload"), dict)]
    if not out:
        # No history yet, but a single current baseline may exist from an older run: seed from it
        # rather than throwing away a comparison the user already paid a day for.
        single = baseline_read(out_dir, NAME)
        if single and isinstance(single.get("payload"), dict) and single.get("captured"):
            out = [{"captured": single["captured"], "payload": single["payload"]}]
    out.sort(key=lambda r: str(r.get("captured")))
    return out


def _seed_demo_history(out_dir, snapshot: dict) -> bool:
    """Plant the fixture's older snapshot as a baseline, once, so a cold demo shows a real delta.

    Only ever fires for a demo run that carries `sizes-previous.json`, and only when out_dir holds
    no history at all — so it can never overwrite a real user's own recorded baseline, and a second
    demo run in the same out_dir compares against the first run rather than re-seeding.
    """
    previous = (snapshot or {}).get("demo_previous") or {}
    if not out_dir or not previous.get("captured") or not previous.get("payload"):
        return False
    if _history_read(out_dir):
        return False
    baseline_write(out_dir, HISTORY, {"runs": [previous], "keep": DEFAULT_KEEP},
                   parse_date(previous["captured"]))
    return True


def _history_write(out_dir, history: list, snapshot: dict, now, keep: int) -> list:
    """Append this run and keep the newest `keep`.

    Retention trims the list inside one file rather than removing older files, because this module
    never deletes anything on the user's disk — including its own past output.
    """
    payload = _payload(snapshot)
    runs = [r for r in history if _captured(r) and _captured(r) < now]
    runs.append({"captured": iso(now), "payload": payload})
    runs = runs[-max(1, keep):]
    baseline_write(out_dir, NAME, payload, now)
    baseline_write(out_dir, HISTORY, {"runs": runs, "keep": max(1, keep)}, now)
    return runs


def _payload(snapshot: dict) -> dict:
    """What a baseline stores: the floored size map and the totals needed to reconcile it."""
    return {"root": snapshot.get("root", ""), "depth": snapshot.get("depth", DEFAULT_DEPTH),
            "floor_bytes": snapshot.get("floor_bytes", DEFAULT_FLOOR),
            "dirs": dict(snapshot.get("dirs") or {}),
            "other_bytes": int(snapshot.get("other_bytes") or 0),
            "total_bytes": int(snapshot.get("total_bytes") or 0),
            "apparent_bytes": int(snapshot.get("apparent_bytes") or 0),
            "files": int(snapshot.get("files") or 0),
            "denied_count": int(snapshot.get("denied_count") or 0),
            "free_bytes": int(snapshot.get("free_bytes") or 0),
            "disk_total_bytes": int(snapshot.get("disk_total_bytes") or 0),
            "complete": bool(snapshot.get("complete", True))}


def _captured(run: dict):
    return parse_date(str((run or {}).get("captured") or ""))


def _select(history: list, since, now) -> tuple:
    """Which retained baseline to compare against, and a label saying which one it was.

    A run captured at or after `now` is never chosen: running twice in the same minute must not
    reset the comparison to zero, and a fixed --now has to give the same answer every time.
    """
    runs = [r for r in history if _captured(r) and _captured(r) < now]
    if not runs:
        return None, ""
    runs.sort(key=_captured)
    want = str(since or "").strip().lower()
    if not want or want in ("last", "latest", "recent", "previous"):
        return runs[-1], "the last run"
    if want in ("first", "oldest", "all"):
        return runs[0], "the oldest retained baseline"
    if want.isdigit():
        back = min(int(want), len(runs) - 1)
        return runs[-1 - back], "{0} run(s) back".format(back)
    match = re.match(r"^(\d+)\s*(d|day|days|w|week|weeks|m|month|months)$", want)
    if match:
        units = {"d": 1, "day": 1, "days": 1, "w": 7, "week": 7, "weeks": 7,
                 "m": 30, "month": 30, "months": 30}[match.group(2)]
        cutoff = now - timedelta(days=int(match.group(1)) * units)
        older = [r for r in runs if _captured(r) <= cutoff]
        if older:
            return older[-1], "the newest baseline at least {0} old".format(want)
        return runs[0], "the oldest retained baseline (nothing goes back {0})".format(want)
    when = parse_date(want)
    if when:
        older = [r for r in runs if _captured(r) <= when]
        if older:
            return older[-1], "the newest baseline on or before {0}".format(day(when))
        return runs[0], "the oldest retained baseline (nothing that old)"
    return runs[-1], "the last run"


# ---------------------------------------------------------------- analysis

def analyse(snapshot: dict, now, cfg: dict) -> dict:
    """Diff this snapshot against a retained baseline, then retain this one.

    The write lives here rather than in the caller because the comparison and the recording are one
    decision: a run that could not read the tree must not record a baseline, or the next run would
    report the whole disk as having vanished overnight.
    """
    cfg = cfg or {}
    snap = snapshot or {}
    out_dir = cfg.get("out_dir")
    keep = max(1, _int(cfg.get("keep_baselines"), DEFAULT_KEEP))
    dirs = dict((str(k), int(_num(v))) for k, v in (snap.get("dirs") or {}).items())
    total = int(snap.get("total_bytes") or 0)
    free = int(snap.get("free_bytes") or 0)
    disk_total = int(snap.get("disk_total_bytes") or 0)
    disk_used = int(snap.get("disk_used_bytes") or max(0, disk_total - free))

    _seed_demo_history(out_dir, snap)

    hogs_now, verdict_bytes = _classify_all(dirs)
    reclaim = verdict_bytes["regenerable"] + verdict_bytes["safe to delete"]
    irreplaceable = max(0, total - sum(verdict_bytes.values()))

    view = {
        "root": snap.get("root", ""), "depth": _int(snap.get("depth"), DEFAULT_DEPTH),
        "floor_bytes": _int(snap.get("floor_bytes"), DEFAULT_FLOOR),
        "floor_size": human_bytes(_int(snap.get("floor_bytes"), DEFAULT_FLOOR)),
        "readable": bool(snap.get("readable")),
        "total_bytes": total, "total_size": human_bytes(total),
        "apparent_bytes": int(snap.get("apparent_bytes") or 0),
        "apparent_size": human_bytes(int(snap.get("apparent_bytes") or 0)),
        "on_disk_sizes": bool(snap.get("on_disk_sizes")),
        "files": int(snap.get("files") or 0),
        "dirs_measured": int(snap.get("dir_total") or 0), "dirs_named": len(dirs),
        "other_bytes": int(snap.get("other_bytes") or 0),
        "biggest": [_row(k, dirs[k], 0) for k in sorted(dirs, key=lambda k: (-dirs[k], k))[:8]],
        "hogs": hogs_now[:20], "hog_total": len(hogs_now),
        "regenerable_bytes": verdict_bytes["regenerable"],
        "regenerable_size": human_bytes(verdict_bytes["regenerable"]),
        "safe_bytes": verdict_bytes["safe to delete"], "safe_size": human_bytes(verdict_bytes["safe to delete"]),
        "think_bytes": verdict_bytes["think first"], "think_size": human_bytes(verdict_bytes["think first"]),
        "reclaim_bytes": reclaim, "reclaim_size": human_bytes(reclaim),
        "irreplaceable_bytes": irreplaceable, "irreplaceable_size": human_bytes(irreplaceable),
        "verdicts": [{"verdict": v, "bytes": verdict_bytes[v], "size": human_bytes(verdict_bytes[v]),
                      "dirs": sum(1 for h in hogs_now if h["verdict"] == v)} for v in VERDICTS],
        "free_bytes": free, "free_size": human_bytes(free),
        "disk_total_bytes": disk_total, "disk_total_size": human_bytes(disk_total),
        "disk_used_bytes": disk_used, "disk_used_size": human_bytes(disk_used),
        "free_share": pct(free, disk_total), "used_share": pct(disk_used, disk_total),
        "denied": {"count": int(snap.get("denied_count") or 0),
                   "paths": list(snap.get("denied") or [])[:8],
                   "note": "counted, not skipped: their size is unknown and is not in any total below"},
        "unreadable": {"count": int(snap.get("unreadable_count") or 0),
                       "paths": list(snap.get("unreadable") or [])[:8]},
        "excluded": _excluded(snap),
        "placeholder_files": int(snap.get("placeholder_files") or 0),
        "placeholder_bytes": int(snap.get("placeholder_bytes") or 0),
        "complete": bool(snap.get("complete", True)), "truncated": snap.get("truncated", ""),
        "caveats": [], "baselines": [], "baselines_kept": keep,
        "since": str(cfg.get("since") or ""), "since_label": "", "since_note": "",
        "compared_with": "", "elapsed_days": None,
        "first_run": True, "first_run_note": "",
        "delta": None, "net_bytes": 0, "net_size": human_bytes(0),
        "appeared": [], "grew": [], "shrank": [], "deleted": [],
        "appeared_bytes": 0, "grew_bytes": 0, "shrank_bytes": 0, "deleted_bytes": 0,
        "movers": [], "shrinkers": [],
        "rate_bytes_per_day": None, "rate_gb_per_day": None,
        "rate_note": "", "projection": None, "headline": "",
    }
    view["caveats"] = _caveats(view, snap)

    if not view["readable"]:
        view["first_run_note"] = ("nothing was read, so no baseline was written: the next run still "
                                  "has nothing to compare against")
        view["since_note"] = since_note({}, now)
        view["headline"] = "Nothing could be read at {0}.".format(view["root"] or "the given root")
        return view

    history = _history_read(out_dir)
    chosen, label = _select(history, cfg.get("since"), now)
    view["since_note"] = since_note({"captured": (chosen or {}).get("captured", "")} if chosen else {}, now)
    view["since_label"] = label

    if chosen:
        view.update(_compare(view, dirs, total, chosen, now))
    else:
        view["first_run"] = True
        view["first_run_note"] = (
            "first run: this is the baseline, not a result. There is nothing to compare against "
            "yet. Run it again tomorrow and it will tell you what moved.")
        view["headline"] = "First run: baseline written. Nothing to compare against yet."

    if cfg.get("write_baseline", True) and out_dir:
        history = _history_write(out_dir, history, snap, now, keep)
    view["baselines"] = [{"captured": r.get("captured", ""),
                          "day": day(_captured(r)),
                          "total_bytes": int((r.get("payload") or {}).get("total_bytes") or 0),
                          "total_size": human_bytes(int((r.get("payload") or {}).get("total_bytes") or 0))}
                         for r in history]
    view["baselines_held"] = len(view["baselines"])
    return view


def _compare(view: dict, dirs: dict, total: int, chosen: dict, now) -> dict:
    prev = chosen.get("payload") or {}
    prev_dirs = dict((str(k), int(_num(v))) for k, v in (prev.get("dirs") or {}).items())
    prev_total = int(prev.get("total_bytes") or 0)
    d = delta(dirs, prev_dirs)

    appeared = [_row(k, dirs[k], dirs[k]) for k in sorted(d["added"])]
    grew = [_row(k, dirs[k], int(_num(d["grew"][k]))) for k in sorted(d["grew"])]
    shrank = [_row(k, dirs[k], int(_num(d["shrank"][k]))) for k in sorted(d["shrank"])]
    deleted = [_row(k, 0, -int(_num(prev_dirs[k]))) for k in sorted(d["removed"])]
    for group in (appeared, grew, shrank, deleted):
        group.sort(key=lambda r: (-abs(r["change"]), r["path"]))

    net = total - prev_total
    captured = _captured(chosen)
    elapsed = max(0.0, (now - captured).total_seconds() / 86400.0) if captured else 0.0
    rate, rate_note, projection = _rate(net, elapsed, view["free_bytes"], now)
    movers = _movers(appeared + grew)
    shrinkers = _movers(shrank + deleted)

    out = {
        "first_run": False, "first_run_note": "",
        "compared_with": chosen.get("captured", ""),
        "elapsed_days": round(elapsed, 2),
        "delta": {"added": d["added"], "removed": d["removed"], "grew": d["grew"],
                  "shrank": d["shrank"], "net": d["net"], "first_run": d["first_run"]},
        "net_bytes": net, "net_size": signed(net),
        "previous_total_bytes": prev_total, "previous_total_size": human_bytes(prev_total),
        "appeared": appeared[:12], "appeared_total": len(appeared),
        "grew": grew[:12], "grew_total": len(grew),
        "shrank": shrank[:12], "shrank_total": len(shrank),
        "deleted": deleted[:12], "deleted_total": len(deleted),
        "appeared_bytes": sum(r["change"] for r in appeared),
        "grew_bytes": sum(r["change"] for r in grew),
        "shrank_bytes": sum(r["change"] for r in shrank),
        "deleted_bytes": sum(r["change"] for r in deleted),
        "movers": movers[:6], "shrinkers": shrinkers[:6],
        "rate_bytes_per_day": rate, "rate_gb_per_day": None if rate is None else round(rate / GB, 2),
        "rate_note": rate_note, "projection": projection,
    }
    out["headline"] = _headline(view, out, movers, shrinkers)
    return out


def _row(path: str, now_bytes: int, change: int) -> dict:
    hog = classify(path)
    return {"path": path, "bytes": int(now_bytes), "size": human_bytes(int(now_bytes)),
            "change": int(change), "change_size": signed(int(change)),
            "hog": hog["name"] if hog else "", "verdict": hog["verdict"] if hog else "",
            "how": hog["how"] if hog else ""}


def _classify_all(dirs: dict) -> tuple:
    """Every measured directory that the table knows, and the bytes behind each verdict."""
    rows, totals = [], dict((v, 0) for v in VERDICTS)
    for path in sorted(dirs, key=lambda k: (-dirs[k], k)):
        hog = classify(path)
        if not hog:
            continue
        totals[hog["verdict"]] += dirs[path]
        rows.append({"path": path, "bytes": dirs[path], "size": human_bytes(dirs[path]),
                     "hog": hog["name"], "verdict": hog["verdict"], "how": hog["how"]})
    return rows, totals


def _movers(rows: list) -> list:
    """Growth grouped by what it is: twelve node_modules is one fact, not twelve rows."""
    groups = {}
    for r in rows:
        key = r["hog"] or _leaf(r["path"])
        g = groups.setdefault(key, {"name": key, "bytes": 0, "dirs": 0, "verdict": r["verdict"],
                                    "how": r["how"], "hog": bool(r["hog"])})
        g["bytes"] += r["change"]
        g["dirs"] += 1
    out = sorted(groups.values(), key=lambda g: (-abs(g["bytes"]), g["name"]))
    for g in out:
        g["size"] = signed(g["bytes"])
        g["phrase"] = ("{0} across {1} {2} {3}".format(g["name"], g["dirs"], "places", signed(g["bytes"]))
                       if g["dirs"] > 1 else "{0} {1}".format(g["name"], signed(g["bytes"])))
    return out


# Folder names that identify nothing on their own: "objects +733 MB" is not a fact anybody can act
# on, so a label made of one of these keeps borrowing from its parent until it names something.
GENERIC = ("objects", "cache", "caches", "data", "build", "dist", "target", "worktrees", "files",
           "tmp", "temp", "store", "logs", "log", "src", "lib", "bin", "out", "output", "assets",
           "images", "media", "backup", "backups", "archive", "archives", "downloads", "documents")


def _leaf(path: str) -> str:
    """A label that says which folder this is, not merely what it is called."""
    parts = [p for p in str(path).split("/") if p and p != "."]
    if not parts:
        return "the root folder"
    i = len(parts) - 1
    label = parts[i]
    while i > 0 and len(label) < 28 and (parts[i].lower() in GENERIC or parts[i].startswith(".")):
        i -= 1
        label = parts[i] + "/" + label
    return label


def _rate(net: int, elapsed_days: float, free: int, now) -> tuple:
    """GB/day since the baseline, and a straight line drawn from it. Labelled as exactly that."""
    if elapsed_days < 1.0 / 24.0:
        return None, "less than an hour since the baseline: too short an interval to rate", None
    rate = net / elapsed_days
    note = "{0}/day over {1:.1f} day(s), from two measurements".format(signed(int(rate)), elapsed_days)
    if rate <= 0 or free <= 0:
        return rate, note, None
    days = free / rate
    if days > 3650:
        return rate, note, {"days": None, "date": "", "capped": True,
                            "note": "At this rate the disk lasts more than ten years. Straight-line "
                                    "extrapolation from one interval, not a forecast."}
    return rate, note, {
        "days": int(days), "date": day(now + timedelta(days=days)), "capped": False,
        "note": "straight-line extrapolation from one interval, not a forecast: it assumes today's "
                "rate never changes, which it will."}


def _headline(view: dict, out: dict, movers: list, shrinkers: list) -> str:
    when = view["since_note"].replace("since ", "Since ") if view["since_note"] else "Since the last run"
    parts = ["{0}: {1}.".format(when, signed(out["net_bytes"]))]
    for g in movers[:3]:
        parts.append(g["phrase"] + ".")
    parts.append("Shrunk: {0}.".format(shrinkers[0]["phrase"] if shrinkers else "nothing"))
    return " ".join(parts)


def _excluded(snap: dict) -> dict:
    ex = snap.get("excluded") or {}
    return {"count": int(ex.get("count") or 0),
            "other volume": list(ex.get("other volume") or [])[:8],
            "system": list(ex.get("system") or [])[:8],
            "note": "not counted: /Volumes, anything on another or network volume, the filesystem's "
                    "own metadata folders, and iCloud files that were never pulled down"}


def _caveats(view: dict, snap: dict) -> list:
    out = []
    if view["on_disk_sizes"]:
        out.append("Sizes are on-disk sizes (st_blocks x 512), so APFS clones and sparse files are "
                   "not double counted; the apparent total is {0} against {1} on disk.".format(
                       view["apparent_size"], view["total_size"]))
    else:
        out.append("This filesystem does not report block counts, so sizes are apparent sizes: "
                   "clones and sparse files may be counted more than once.")
    if view["floor_bytes"] > 0:
        out.append("Folders are summarised {0} deep and named only above {1}; everything smaller is "
                   "carried in one 'other' total, so a small folder's growth is invisible here.".format(
                       view["depth"], view["floor_size"]))
        out.append("A folder that fell below {0} between runs is reported as deleted, because the "
                   "baseline stopped holding it by name.".format(view["floor_size"]))
    else:
        out.append("Folders are summarised {0} deep, so growth inside a deeper folder is reported "
                   "against its {0}-deep parent.".format(view["depth"]))
    if view["denied"]["count"]:
        out.append("{0} could not be opened. They are counted and named, never silently dropped, "
                   "but their size is unknown and is missing from every total.".format(
                       plural(view["denied"]["count"], "folder")))
    if view["placeholder_files"]:
        out.append("{0} are on iCloud or otherwise occupy no blocks ({1} apparent); they are "
                   "excluded from the on-disk total.".format(
                       plural(view["placeholder_files"], "file"), human_bytes(view["placeholder_bytes"])))
    if not view["complete"]:
        out.append("The walk stopped at the {0} bound, so every total is a lower bound.".format(
            view["truncated"]))
    return out


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    cfg = cfg or {}
    right = v["since_note"] if v.get("since_note") else ""
    c = Card("WHAT GREW", right if len(right) < 26 else "", cfg.get("color"))
    c.blank()

    if not v["readable"]:
        c.headline("Nothing could be read.", "1;33")
        c.wrap(v["first_run_note"])
        return c.close()

    if v["first_run"]:
        c.headline("First run: baseline written, nothing to compare against yet.", "1;33")
        c.blank()
        c.wrap("Measured {0} across {1} in {2} folder(s), {3} deep.".format(
            v["total_size"], plural(v["files"], "file"), v["dirs_measured"], v["depth"]))
        if not v["complete"]:
            c.row("lower bound: stopped at the {0} bound".format(v["truncated"]))
        c.wrap("Come back tomorrow: the next run reports what grew, what shrank, what appeared and "
               "what was deleted. This one has no delta to show, and will not invent one.")
        c.blank()
        c.rule("WHAT IS BIG TODAY")
        for row in v["biggest"][:5]:
            c.cols(row["path"], row["size"], 12)
        c.rule("DISK")
        c.row("{0} used of {1} · {2} free ({3}%)".format(
            v["disk_used_size"], v["disk_total_size"], v["free_size"], v["free_share"]))
        if v["denied"]["count"]:
            c.row("{0} could not be read (counted, size unknown)".format(
                plural(v["denied"]["count"], "folder")))
        return c.close()

    c.headline("{0} {1}".format(signed(v["net_bytes"]), v["since_note"]), "1;36")
    c.row("{0} used of {1} · {2} free ({3}%)".format(
        v["disk_used_size"], v["disk_total_size"], v["free_size"], v["free_share"]))
    if v["rate_bytes_per_day"] is not None:
        c.row("{0}/day over {1} day(s), from two measurements".format(
            signed(int(v["rate_bytes_per_day"])), v["elapsed_days"]))
    if not v["complete"]:
        c.row("lower bound: stopped at the {0} bound".format(v["truncated"]))
    c.blank()

    _section(c, "GREW IN PLACE", v["grew"], v["grew_total"])
    _section(c, "NEWLY APPEARED", v["appeared"], v["appeared_total"])
    _section(c, "SHRANK", v["shrank"], v["shrank_total"])
    _section(c, "DELETED", v["deleted"], v["deleted_total"])

    c.rule("WHAT YOU CAN GET BACK")
    c.headline("{0} regenerable".format(v["regenerable_size"]), "1;32")
    c.row("{0} cache, safe to delete · {1} needs a decision".format(v["safe_size"], v["think_size"]))
    c.row("{0} is data nothing can rebuild — not in the number above".format(v["irreplaceable_size"]))
    for row in v["hogs"][:4]:
        c.cols("{0}  {1}".format(pad(row["hog"], 20), row["path"]), row["size"], 10)

    if v["projection"]:
        c.rule("IF NOTHING CHANGES")
        if v["projection"]["capped"]:
            c.wrap("More than ten years of headroom at this rate.")
        else:
            c.wrap("Full in {0} day(s), around {1}.".format(v["projection"]["days"], v["projection"]["date"]))
        c.wrap("Straight-line extrapolation from one interval, not a forecast.")

    c.rule("READ THIS BEFORE ACTING")
    if v["denied"]["count"]:
        c.wrap("{0} could not be opened; counted, size unknown.".format(
            plural(v["denied"]["count"], "folder")))
    c.wrap(v["excluded"]["note"] + ".")
    c.wrap("Nothing was deleted, moved or opened.")
    return c.close()


def _section(c: Card, title: str, rows: list, total: int):
    if not rows:
        return
    c.rule(title)
    for row in rows[:4]:
        c.cols(row["path"], "{0}{1}".format(row["change_size"], "  " + row["verdict"] if row["verdict"] else ""),
               24 if row["verdict"] else 12)
    if total > 4:
        c.row("+ {0} more".format(total - 4))


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    L = ["# What grew", ""]
    if not v["readable"]:
        L += ["Nothing could be read, so no baseline was written.", ""]
        L += _sources_table(sources)
        return "\n".join(L)

    if v["first_run"]:
        L += ["**First run.** {0}".format(v["first_run_note"]), "",
              "Measured {0} across {1:,} file(s) in {2} folder(s), {3} deep, on {4}.".format(
                  v["total_size"], v["files"], v["dirs_measured"], v["depth"], v["root"]), ""]
    else:
        L += ["{0}".format(v["headline"]), "",
              "| measure | value |", "|---|---|",
              "| compared with | {0} ({1}) |".format(v["compared_with"], v["since_label"]),
              "| interval | {0} day(s) |".format(v["elapsed_days"]),
              "| net change | {0} |".format(v["net_size"]),
              "| grew in place | {0} folder(s), {1} |".format(v["grew_total"], signed(v["grew_bytes"])),
              "| newly appeared | {0} folder(s), {1} |".format(v["appeared_total"], signed(v["appeared_bytes"])),
              "| shrank in place | {0} folder(s), {1} |".format(v["shrank_total"], signed(v["shrank_bytes"])),
              "| deleted | {0} folder(s), {1} |".format(v["deleted_total"], signed(v["deleted_bytes"])),
              "| rate | {0} |".format(v["rate_note"] or "not measurable yet"), ""]

    if not v["complete"]:
        L += ["> The walk stopped at the {0} bound. Every total below is a lower bound, and a run "
              "compared against it is comparing two lower bounds.".format(v["truncated"]), ""]
    L += ["## Disk", "", "| measure | value |", "|---|---|",
          "| measured | {0} on disk ({1} apparent) |".format(v["total_size"], v["apparent_size"]),
          "| used | {0} of {1} ({2}%) |".format(v["disk_used_size"], v["disk_total_size"], v["used_share"]),
          "| free | {0} ({1}%) |".format(v["free_size"], v["free_share"]),
          "| files counted | {0:,} |".format(v["files"]),
          "| folders named | {0} of {1} measured |".format(v["dirs_named"], v["dirs_measured"]), ""]

    if v["projection"]:
        L += ["## If nothing changes", "", v["projection"]["note"], ""]
        if not v["projection"]["capped"]:
            L += ["Free space runs out in about **{0} day(s)**, around **{1}**.".format(
                v["projection"]["days"], v["projection"]["date"]), ""]

    for title, key, total_key in (("Grew in place", "grew", "grew_total"),
                                  ("Newly appeared", "appeared", "appeared_total"),
                                  ("Shrank in place", "shrank", "shrank_total"),
                                  ("Deleted", "deleted", "deleted_total")):
        rows = v.get(key) or []
        if not rows:
            continue
        L += ["## {0} ({1})".format(title, v.get(total_key, len(rows))), "",
              "| folder | change | now | what it is | verdict |", "|---|---|---|---|---|"]
        L += ["| `{0}` | {1} | {2} | {3} | {4} |".format(r["path"], r["change_size"], r["size"],
                                                         r["hog"] or "—", r["verdict"] or "—")
              for r in rows]
        L += [""]

    L += ["## What you can get back", "",
          "**{0} regenerable** — output a command rebuilds. Kept apart from {1} of data nothing "
          "can rebuild.".format(v["regenerable_size"], v["irreplaceable_size"]), "",
          "| verdict | folders | size |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(x["verdict"], x["dirs"], x["size"]) for x in v["verdicts"]]
    L += [""]
    if v["hogs"]:
        L += ["| folder | what it is | size | verdict | how it comes back |", "|---|---|---|---|---|"]
        L += ["| `{0}` | {1} | {2} | {3} | {4} |".format(h["path"], h["hog"], h["size"], h["verdict"], h["how"])
              for h in v["hogs"]]
        L += [""]

    if v["baselines"]:
        L += ["## Retained baselines ({0} of {1} kept)".format(len(v["baselines"]), v["baselines_kept"]), "",
              "Any of these can be the comparison point: `since=oldest`, `since=7d`, `since=2` "
              "(runs back) or a date.", "", "| captured | measured |", "|---|---|"]
        L += ["| {0} | {1} |".format(b["captured"], b["total_size"]) for b in v["baselines"]]
        L += [""]

    if v["denied"]["count"]:
        L += ["## Folders that could not be read ({0})".format(v["denied"]["count"]), "",
              v["denied"]["note"], ""]
        L += ["- `{0}`".format(p) for p in v["denied"]["paths"]]
        L += [""]

    L += ["## What was excluded", "", v["excluded"]["note"] + ".", ""]
    if v["excluded"]["other volume"]:
        L += ["- another volume: " + ", ".join("`{0}`".format(p) for p in v["excluded"]["other volume"]), ""]

    L += ["## Caveats", ""] + ["- {0}".format(c) for c in v["caveats"]] + [""]
    L += _sources_table(sources)
    L += ["Read-only. Directory entries and their sizes were read; no file was opened, and nothing "
          "was deleted, moved or renamed. The only file written is this report and the size "
          "baseline beside it.", ""]
    return "\n".join(L)


def _sources_table(sources: list) -> list:
    L = ["## Sources", "", "| source | read | detail |", "|---|---|---|"]
    for s in sources or []:
        row = s if isinstance(s, dict) else s.__dict__
        L.append("| {0} | {1} | {2} |".format(row.get("name", ""), "yes" if row.get("found") else "no",
                                              row.get("note", "") or ""))
    return L + [""]


# ---------------------------------------------------------------- small helpers

def signed(n) -> str:
    """+38.2 GB / -3.0 GB / ±0 B. human_bytes alone would print a bare minus and no plus at all."""
    n = int(_num(n))
    if n == 0:
        return "±0 B"
    return "{0}{1}".format("+" if n > 0 else "-", human_bytes(abs(n)))


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
