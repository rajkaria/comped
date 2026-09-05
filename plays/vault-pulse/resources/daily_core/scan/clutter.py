"""desktop-clutter: what is actually on your Desktop and in Downloads, by age and by size.

Both folders are append-only in practice: things arrive, nothing leaves, and the Finder sorts by
name so the oldest file is invisible. Every fact needed to fix that is in the file system, so this
counts it — how old, how big, how many are screenshots, and which files are the same file twice.
"""
import hashlib
import plistlib
import re
from collections import Counter

from ..common import (Budget, Source, ago, day, expand, from_unix, human_bytes, iso, pct, read_bytes, walk)
from ..card import pad, rpad

KINDS = ("desktop", "downloads", "screenshots")
SKIP = (".DS_Store", ".localized", ".Trash", "Icon\r")
SCREENSHOT = re.compile(
    r"^(screenshot|screen shot|cleanshot|shottr|scr-|capto_capture|simulator screen shot|image \d)", re.I)
INSTALLER = (".dmg", ".pkg", ".mpkg", ".iso", ".msi", ".exe", ".appimage")
ARCHIVE = (".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar")
DOCUMENT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pages", ".numbers", ".key", ".csv", ".txt", ".md")
MEDIA = (".png", ".jpg", ".jpeg", ".gif", ".heic", ".mov", ".mp4", ".webm", ".m4a", ".mp3", ".wav", ".webp", ".svg")


def screenshot_dir() -> tuple:
    """Where macOS is configured to drop screenshots, which is the Desktop until someone changes it."""
    prefs = expand("~/Library/Preferences/com.apple.screencapture.plist")
    if prefs.is_file():
        try:
            doc = plistlib.loads(prefs.read_bytes()) or {}
            location = doc.get("location")
            if location:
                p = expand(location)
                if p.is_dir():
                    return p, "from com.apple.screencapture"
        except Exception:
            pass
    return expand("~/Desktop"), "default (Desktop)"


def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    if cfg.get("demo_root"):
        # The demo reads a manifest rather than real files: a folder in a git checkout carries the
        # checkout's timestamps, and every age in this card would then be "today".
        import json
        path = expand(cfg["demo_root"]) / "files.json"
        src = Source(name="{0} (demo)".format(kind), path=str(path))
        if not path.is_file():
            return [src.miss("fixture missing")], []
        rows = [r for r in json.loads(path.read_text(encoding="utf-8")) if r["root"] == kind]
        if kind == "screenshots":
            return [src.hit(0, "same folder as the Desktop")], []
        return [src.hit(len(rows), "bundled fixture")], rows
    if kind == "screenshots":
        root, how = screenshot_dir()
        if str(root) == str(expand("~/Desktop")):
            # Counting the Desktop twice would double every total; the desktop step already has it.
            return [Source(name="screenshots", path=str(root)).hit(0, "same folder as the Desktop")], []
    else:
        override = cfg.get("{0}_dir".format(kind)) or "~/{0}".format(kind.capitalize())
        root, how = expand(override), str(override)

    src = Source(name=kind, path=str(root))
    if not root.is_dir():
        return [src.miss("no folder at {0}".format(root))], []
    files, folders = [], 0
    for path, st, depth in walk(root, budget, skip_names=SKIP, want_dirs=True):
        if path.is_dir():
            folders += 1
            continue
        files.append({"name": path.name, "rel": str(path.relative_to(root)), "root": kind,
                      "bytes": st.st_size, "ext": path.suffix.lower(), "depth": depth,
                      "modified": iso(from_unix(st.st_mtime)),
                      "created": iso(from_unix(getattr(st, "st_birthtime", st.st_ctime)))})
    return [src.hit(len(files), "{0}; {1} folder(s)".format(how, folders))], files


# ---------------------------------------------------------------- analysis

def analyse(files: list, now, cold_days: int, hash_dupes: bool, roots: dict) -> dict:
    from ..common import parse_date
    total_bytes = sum(f["bytes"] for f in files)
    buckets, labels = [0, 0, 0, 0, 0], ["today", "this week", "this month", "this year", "older"]
    byte_buckets = [0, 0, 0, 0, 0]
    for f in files:
        when = parse_date(f["modified"]) if f["modified"] else None
        f["_when"] = when
        d = (now - when).days if when else 0
        i = 0 if d < 1 else 1 if d < 7 else 2 if d < 30 else 3 if d < 365 else 4
        buckets[i] += 1
        byte_buckets[i] += f["bytes"]

    cold = [f for f in files if f["_when"] and (now - f["_when"]).days >= cold_days]
    shots = [f for f in files if SCREENSHOT.match(f["name"])]
    installers = [f for f in files if f["ext"] in INSTALLER]
    archives = [f for f in files if f["ext"] in ARCHIVE]
    oldest = min((f for f in files if f["_when"]), key=lambda f: f["_when"], default=None)

    kinds = Counter()
    for f in files:
        kinds["screenshot" if SCREENSHOT.match(f["name"]) else
              "installer" if f["ext"] in INSTALLER else
              "archive" if f["ext"] in ARCHIVE else
              "document" if f["ext"] in DOCUMENT else
              "media" if f["ext"] in MEDIA else
              "other"] += 1

    dupes = _duplicates(files, hash_dupes)
    per_root = Counter()
    per_root_bytes = Counter()
    for f in files:
        per_root[f["root"]] += 1
        per_root_bytes[f["root"]] += f["bytes"]

    reclaim = sum(d["wasted_bytes"] for d in dupes) + sum(f["bytes"] for f in installers if
                                                          f["_when"] and (now - f["_when"]).days >= 30)
    return {
        "files": len(files), "bytes": total_bytes, "roots": roots,
        "per_root": [{"root": k, "files": v, "bytes": per_root_bytes[k], "size": human_bytes(per_root_bytes[k])}
                     for k, v in sorted(per_root.items())],
        "buckets": [{"label": l, "files": c, "bytes": b, "size": human_bytes(b)}
                    for l, c, b in zip(labels, buckets, byte_buckets)],
        "cold": len(cold), "cold_days": cold_days, "cold_share": pct(len(cold), len(files)),
        "cold_bytes": sum(f["bytes"] for f in cold),
        "oldest": None if not oldest else {"name": oldest["name"], "root": oldest["root"],
                                           "modified": day(oldest["_when"]), "age": ago(oldest["_when"], now),
                                           "size": human_bytes(oldest["bytes"])},
        "screenshots": len(shots), "screenshot_bytes": sum(f["bytes"] for f in shots),
        "screenshot_share": pct(len(shots), len(files)),
        "installers": len(installers), "installer_bytes": sum(f["bytes"] for f in installers),
        "archives": len(archives), "archive_bytes": sum(f["bytes"] for f in archives),
        "kinds": [{"kind": k, "files": c, "share": c / len(files) if files else 0.0}
                  for k, c in kinds.most_common()],
        "duplicates": dupes[:6], "duplicate_total": len(dupes),
        "duplicate_bytes": sum(d["wasted_bytes"] for d in dupes),
        "reclaimable": reclaim,
        "deepest": max((f["depth"] for f in files), default=0),
        "biggest": [{"name": f["name"], "root": f["root"], "size": human_bytes(f["bytes"]),
                     "age": ago(f["_when"], now) if f["_when"] else "unknown"}
                    for f in sorted(files, key=lambda f: -f["bytes"])[:6]],
        "score": _score(len(files), len(cold), len(dupes), total_bytes),
        "hashed": hash_dupes,
    }


def _duplicates(files: list, hash_dupes: bool) -> list:
    """Same size and same extension is a candidate; only a content hash makes it a duplicate.

    Hashing every candidate is the difference between a claim and a fact, so the size-and-name
    grouping only ever narrows the field and the report says which test it applied.
    """
    groups = {}
    for f in files:
        groups.setdefault((f["bytes"], f["ext"]), []).append(f)
    out = []
    for (size, ext), group in sorted(groups.items(), key=lambda kv: -kv[0][0]):
        if len(group) < 2 or size == 0:
            continue
        if hash_dupes and size <= 64 * 1024 * 1024:
            by_hash = {}
            for f in group:
                digest = _digest(f)
                if digest:
                    by_hash.setdefault(digest, []).append(f)
            clusters = [g for g in by_hash.values() if len(g) > 1]
            proof = "identical contents"
        else:
            clusters, proof = [group], "same size and type, contents not compared"
        for cluster in clusters:
            out.append({"name": cluster[0]["name"], "copies": len(cluster), "size": human_bytes(size),
                        "wasted_bytes": size * (len(cluster) - 1), "proof": proof,
                        "paths": sorted("{0}/{1}".format(f["root"], f["rel"]) for f in cluster)[:4]})
    return sorted(out, key=lambda d: -d["wasted_bytes"])


def _digest(f: dict):
    from ..common import expand as _expand
    root = {"desktop": "~/Desktop", "downloads": "~/Downloads"}.get(f["root"])
    path = (_expand(root) / f["rel"]) if root else None
    if path is None or not path.is_file():
        return None
    data = read_bytes(path, 64 * 1024 * 1024)
    return hashlib.sha256(data).hexdigest() if data else None


def _score(files: int, cold: int, dupes: int, total_bytes: int) -> dict:
    """A grade you can compare with someone else's, from the three things that make a folder a mess."""
    if not files:
        return {"grade": "A", "points": 0, "why": "nothing in either folder"}
    points = min(40, files // 10) + min(40, int(60.0 * cold / files)) + min(20, dupes * 2)
    grade = "A" if points < 15 else "B" if points < 30 else "C" if points < 50 else "D" if points < 70 else "F"
    return {"grade": grade, "points": points,
            "why": "{0} files, {1} of them cold, {2} duplicate group(s)".format(files, cold, dupes)}


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card

    c = Card("DESKTOP CLUTTER", "grade {0}".format(v["score"]["grade"]), cfg.get("color"))
    c.blank()
    c.headline("{0:,} files, {1}".format(v["files"], human_bytes(v["bytes"])), "1;36")
    o = v["oldest"]
    if o:
        c.row("oldest is from {0} ({1} ago): {2}".format(o["modified"], o["age"], o["name"]))
    c.row(" · ".join("{0} {1} ({2})".format(r["files"], r["root"], r["size"]) for r in v["per_root"]))
    c.blank()

    c.rule("BY AGE")
    top = max([b["files"] for b in v["buckets"]] or [1]) or 1
    for b in v["buckets"]:
        bar = "▇" * (0 if not b["files"] else max(1, int(round(b["files"] / top * 16))))
        c.row("{0}{1}  {2}{3}".format(pad(b["label"], 12), rpad(str(b["files"]), 6), pad(bar, 17),
                                      rpad(b["size"], 9)))
    c.row("{0} untouched {1}+ days ({2}%), {3}".format(
        v["cold"], v["cold_days"], v["cold_share"], human_bytes(v["cold_bytes"])))

    c.rule("WHAT THEY ARE")
    for k in v["kinds"][:5]:
        c.bar(k["kind"], str(k["files"]), k["share"])
    if v["screenshots"]:
        c.row("screenshots alone: {0} files, {1}".format(v["screenshots"], human_bytes(v["screenshot_bytes"])))
    if v["installers"]:
        c.row("installers you already ran: {0}, {1}".format(v["installers"], human_bytes(v["installer_bytes"])))

    if v["duplicate_total"]:
        c.rule("THE SAME FILE TWICE")
        for d in v["duplicates"][:4]:
            c.cols("{0}× {1}".format(d["copies"], d["name"]), human_bytes(d["wasted_bytes"]), 12)
        c.row("proof: {0}".format(v["duplicates"][0]["proof"]))

    c.rule("BIGGEST")
    for b in v["biggest"][:4]:
        c.cols(b["name"], "{0}  {1}".format(b["size"], b["age"]), 18)

    c.blank()
    c.headline("{0} reclaimable without opening a single file".format(human_bytes(v["reclaimable"])), "1;32")
    c.wrap("Grade {0}: {1}. Nothing was moved, renamed or deleted.".format(
        v["score"]["grade"], v["score"]["why"]))
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    L = ["# Desktop clutter", "",
         "{0:,} files, {1}. Grade {2}.".format(v["files"], human_bytes(v["bytes"]), v["score"]["grade"]), "",
         "| measure | value |", "|---|---|",
         "| files | {0:,} |".format(v["files"]),
         "| total size | {0} |".format(human_bytes(v["bytes"])),
         "| untouched {0}+ days | {1} ({2}%) |".format(v["cold_days"], v["cold"], v["cold_share"]),
         "| screenshots | {0} ({1}) |".format(v["screenshots"], human_bytes(v["screenshot_bytes"])),
         "| installers | {0} ({1}) |".format(v["installers"], human_bytes(v["installer_bytes"])),
         "| duplicate groups | {0} ({1} wasted) |".format(v["duplicate_total"], human_bytes(v["duplicate_bytes"])),
         "| reclaimable | {0} |".format(human_bytes(v["reclaimable"])),
         "| grade | {0} ({1} points) |".format(v["score"]["grade"], v["score"]["points"]), "",
         "## By age", "", "| age | files | size |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(b["label"], b["files"], b["size"]) for b in v["buckets"]]
    if v["duplicates"]:
        L += ["", "## The same file twice", "", "| file | copies | wasted | proof |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(d["name"], d["copies"], human_bytes(d["wasted_bytes"]), d["proof"])
              for d in v["duplicates"]]
    L += ["", "## Biggest", "", "| file | where | size | last touched |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} |".format(b["name"], b["root"], b["size"], b["age"]) for b in v["biggest"]]
    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "") for s in sources]
    L += ["", "Read-only. File names, sizes and dates were read; contents were read only to prove "
          "a duplicate, and nothing was moved, renamed or deleted.", ""]
    return "\n".join(L)
