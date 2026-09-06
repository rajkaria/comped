"""photo-debt: how much of your photo library is bursts, screenshots and the same file twice.

A photo library only ever grows. The shutter fires ten times to get one usable frame, every
screenshot lands next to the family album, and the same image arrives again from a message, an
AirDrop and a download. None of that is visible in the Photos app, which is organised by date and
face rather than by waste, so the honest number — how much of this is not really photographs —
has never been on screen.

This counts it, and counts it conservatively. Three separate claims are made, each with its own
confidence: files whose bytes are byte-for-byte identical (a fact), extra frames from a burst
(an inference from time, dimensions and file name), and screenshots old enough to have served
their purpose (a judgement). They are never added into one number without saying which is which.

Two things this deliberately does not do. It never deletes, moves or renames anything: the output
is a list to review, and every removal stays a decision a person makes in the Photos app, where
there is an undo. And it never compares images by content similarity — the standard library
decodes neither JPEG nor HEIC, a third-party imaging package would break the stdlib-only promise,
and shelling out to a system converter would break the no-child-process promise. So "duplicate"
here always means identical bytes, and "near-duplicate" always means metadata, never pixels.
"""
import hashlib
import os
import re
from collections import Counter

from ..card import Card, legend, pad, rpad, sparkline, tier_bar
from ..common import (Budget, Source, ago, day, delta, expand, from_unix, human_bytes, iso, parse_date,
                      pct, plural, shorten_path, since_note, walk)
from ..parsers import photosdb

KINDS = ("photos", "folder")

LIBRARY = "~/Pictures/Photos Library.photoslibrary"
DB_REL = "database/Photos.sqlite"
SKIP = (".DS_Store", ".localized", "Thumbs.db")

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tif", ".tiff", ".bmp", ".webp",
             ".dng", ".raw", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf")
VIDEO_EXT = photosdb.VIDEO_EXT

# Confidence is part of the answer, so the tiers carry their own wording into card and report.
TIERS = (("identical bytes", "safe"),
         ("burst siblings", "probably"),
         ("old screenshots", "your call"))

HASH_CHUNK = 1024 * 1024
HASH_CAP = 64 * 1024 * 1024


# ---------------------------------------------------------------- sources

def read_source(source: str, budget: Budget, cfg: dict) -> tuple:
    """One place to look for assets. Returns (sources, records); a miss is labelled, never raised."""
    if cfg.get("demo_root"):
        return _read_demo(source, cfg)
    if source == "photos":
        return _read_library(budget, cfg)
    if source == "folder":
        return _read_folder(budget, cfg)
    return [Source(name=source).miss("unknown source")], []


def _read_demo(source: str, cfg: dict) -> tuple:
    """The bundled fixture, so a first run works on a machine with no library and no photographs.

    A manifest rather than real image files: a folder in a checkout carries the checkout's
    timestamps, so every capture date in the card would be the day the user cloned it.
    """
    import json
    path = expand(cfg["demo_root"]) / "assets.json"
    src = Source(name="{0} (demo)".format(source), path=str(path))
    if source != "photos":
        return [src.hit(0, "the demo reads one library")], []
    if not path.is_file():
        return [src.miss("fixture missing")], []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [src.miss("fixture unreadable: {0}".format(str(exc)[:60]))], []
    records = [photosdb.asset(**r) for r in raw if isinstance(r, dict)]
    for r in records:
        r["source"] = "demo"
    return [src.hit(len(records), "bundled fixture")], records


def _read_library(budget: Budget, cfg: dict) -> tuple:
    """The Photos library, through a temporary read-only copy of its database."""
    lib = expand(cfg.get("library") or LIBRARY)
    db = lib / DB_REL
    src = Source(name="Photos library", path=str(db))
    try:
        present = db.is_file()
    except (OSError, PermissionError) as exc:
        return [src.miss(_denied(exc, lib))], []
    if not present:
        if not lib.exists():
            return [src.miss("no Photos library at {0}".format(shorten_path(lib, 44)))], []
        if not os.access(str(lib), os.R_OK):
            return [src.miss(_denied(PermissionError(), lib))], []
        return [src.miss("no Photos.sqlite inside {0}".format(lib.name))], []

    try:
        mapping, records, note = photosdb.read_library(db, budget)
    except (OSError, PermissionError) as exc:
        return [src.miss(_denied(exc, db))], []
    except Exception as exc:                       # sqlite3 raises several unrelated types
        return [src.miss("database unreadable: {0}".format(str(exc)[:70]))], []
    if not mapping.get("ok"):
        return [src.miss(note or "unrecognised schema")], []
    for r in records:
        r["path"] = _resolve(lib, r)
    if not records:
        return [src.hit(0, "no assets in the library ({0})".format(note))], []
    return [src.hit(len(records), note)], records


def _read_folder(budget: Budget, cfg: dict) -> tuple:
    """A plain directory of images, for anyone who keeps photographs in folders and not in Photos."""
    where = cfg.get("root") or "~/Pictures"
    root = expand(where)
    src = Source(name="folder", path=str(root))
    try:
        if not root.is_dir():
            return [src.miss("no folder at {0}".format(where))], []
    except (OSError, PermissionError) as exc:
        return [src.miss(_denied(exc, root))], []

    records, skipped = [], 0
    for path, st, _depth in walk(root, budget, skip_names=SKIP):
        ext = path.suffix.lower()
        if ext not in IMAGE_EXT and ext not in VIDEO_EXT:
            skipped += 1
            continue
        stem, _ = os.path.splitext(path.name)
        # The modification time is the one timestamp that survives being copied between disks, so
        # it is the closest thing a bare file has to a capture date. Said in the report, not hidden.
        when = from_unix(st.st_mtime)
        records.append(photosdb.asset(
            id=str(path), filename=path.name, stem=stem, ext=ext,
            dir=str(path.parent.relative_to(root)) if path.parent != root else "",
            path=str(path), captured=iso(when),
            added=iso(from_unix(getattr(st, "st_birthtime", st.st_mtime)) or when),
            bytes=st.st_size, video=ext in VIDEO_EXT,
            screenshot=(ext not in VIDEO_EXT) and bool(photosdb.SCREENSHOT_NAME.match(path.name)),
            source="folder",
            # A bare file records none of these; saying so is the difference between "no
            # favourites" and "this source cannot see favourites".
            unknown=["burst_id", "edited", "favourite", "local", "trashed", "viewed"]))
    if not records:
        return [src.miss("no images or video under {0}".format(shorten_path(root, 40)))], []
    return [src.hit(len(records), "{0} non-image file(s) skipped".format(skipped))], records


def _resolve(lib, rec: dict) -> str:
    """Where an asset's original actually sits, tried in the orders the library has used.

    A directory value out of the database is data, not a path to trust: anything absolute or
    containing a parent reference is dropped rather than joined, so a corrupt row cannot point
    this scanner at a file outside the library.
    """
    name = rec.get("filename") or ""
    if not name or "/" in name or name in (".", ".."):
        return ""
    sub = str(rec.get("dir") or "")
    if sub.startswith("/") or ".." in sub.split("/"):
        sub = ""
    uid = str(rec.get("uuid") or rec.get("id") or "")
    candidates = []
    if sub:
        candidates += [lib / sub / name, lib / "originals" / sub / name]
    candidates.append(lib / "originals" / name)
    if uid and uid[0].isalnum():
        candidates.append(lib / "originals" / uid[0] / name)
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except (OSError, ValueError):
            continue
    return ""


def _denied(exc, path) -> str:
    if isinstance(exc, PermissionError) or (path and os.path.exists(str(path)) and not os.access(str(path), os.R_OK)):
        return ("macOS blocked the read; grant Full Disk Access, or point root= at an exported folder")
    if not os.path.exists(str(path)):
        return "nothing at {0}".format(shorten_path(path, 40))
    return str(exc)[:100]


# ---------------------------------------------------------------- analysis

def analyse(records: list, now, cfg: dict) -> dict:
    """Every number the card and the report show, computed once from the normalized records."""
    window = max(0, int(cfg.get("burst_window") or 2))
    shot_days = max(0, int(cfg.get("screenshot_days") or 90))
    top = max(1, int(cfg.get("top") or 5))
    hash_dupes = cfg.get("hash_dupes", True)

    unknown = _unknown(records)
    items = sorted((dict(r) for r in records), key=_order)
    items, live = _fold_live(items)
    for r in items:
        r["_when"] = parse_date(r.get("captured") or "") if r.get("captured") else None
        r["_added"] = parse_date(r.get("added") or "") if r.get("added") else None

    trashed = [r for r in items if r.get("trashed")]
    kept = [r for r in items if not r.get("trashed")]
    not_local = [r for r in kept if not r.get("local", True)]
    on_disk = [r for r in kept if r.get("local", True)]

    stills = [r for r in kept if not r.get("video")]
    videos = [r for r in kept if r.get("video")]
    shots = [r for r in kept if r.get("screenshot")]

    dupes = _duplicates(on_disk, hash_dupes, cfg)
    bursts = _bursts([r for r in on_disk if not r.get("video")], window)
    reclaim = _reclaim(dupes, bursts, shots, now, shot_days)

    sized = [r for r in on_disk if _size(r) > 0]
    years = _years(kept)
    protected = [r for r in kept if _protected(r)]

    view = {
        "assets": len(kept), "stills": len(stills), "videos": len(videos), "live": live,
        "bytes": sum(_size(r) for r in kept),
        "local_bytes": sum(_size(r) for r in on_disk),
        "still_bytes": sum(_size(r) for r in stills), "video_bytes": sum(_size(r) for r in videos),
        "video_byte_share": pct(sum(_size(r) for r in videos), sum(_size(r) for r in kept)),
        "sized": len(sized), "unsized": len(on_disk) - len(sized),
        "not_local": len(not_local), "not_local_share": pct(len(not_local), len(kept)),
        "trashed": {"count": len(trashed), "bytes": sum(_size(r) for r in trashed)},
        "bursts": _burst_view(bursts, top),
        "duplicates": _dupe_view(dupes, top),
        "screenshots": _shot_view(shots, now, shot_days, len(kept), unknown),
        "reclaim": reclaim,
        "protected": {"favourites": sum(1 for r in protected if r.get("favourite")),
                      "edited": sum(1 for r in protected if r.get("edited")),
                      "count": len(protected), "bytes": sum(_size(r) for r in protected)},
        "years": years,
        "spark_assets": sparkline([y["assets"] for y in years]),
        "spark_bytes": sparkline([y["bytes"] for y in years]),
        "largest": [{"name": r.get("filename") or r.get("id"), "bytes": _size(r),
                     "size": human_bytes(_size(r)), "kind": "video" if r.get("video") else "still",
                     "age": ago(r.get("_when"), now) if r.get("_when") else "unknown"}
                    for r in sorted(on_disk, key=lambda r: (-_size(r), r.get("filename") or "", r["id"]))[:top]],
        "oldest": _edge(kept, now, first=True), "newest": _edge(kept, now, first=False),
        "unknown_fields": unknown,
        "kinds": _kinds(kept),
        "burst_window": window, "screenshot_days": shot_days, "top": top,
        "method": _method(unknown, hash_dupes, records),
        "never_deletes": ("photo-debt never deletes, moves or renames anything: this is a list to "
                          "review in Photos, where there is an undo."),
        "no_pixel_compare": ("Duplicates are byte-identical files, proven by SHA-256. Nothing here "
                             "compares images by appearance: no pixels are decoded and no similarity "
                             "score is invented."),
    }
    current = {"assets": view["assets"], "bytes": view["local_bytes"],
               "screenshots": view["screenshots"]["count"],
               "duplicates": view["duplicates"]["groups"],
               "burst_siblings": view["bursts"]["siblings"],
               "reclaimable": view["reclaim"]["bytes"]}
    baseline = cfg.get("baseline") or {}
    view["baseline"] = current
    view["delta"] = delta(current, baseline.get("payload") or {})
    view["since"] = since_note(baseline, now)
    return view


def _order(r: dict) -> tuple:
    return (r.get("captured") or "~", str(r.get("filename") or ""), str(r.get("id") or ""))


def _size(r: dict) -> int:
    return max(0, int(r.get("bytes") or 0)) + max(0, int(r.get("live_bytes") or 0))


def _protected(r: dict) -> bool:
    """The one rule with no exceptions: a favourite or an edited asset is never reclaimable.

    Both are evidence a person did something deliberate with that frame. Whatever else it is —
    a burst sibling, a duplicate, a screenshot from 2019 — it does not enter a reclaim number.
    """
    return bool(r.get("favourite")) or bool(r.get("edited"))


def _unknown(records: list) -> list:
    """Fields no source could see. A field one source knows is known, so two sources fill each other in."""
    sets = [set(r.get("unknown") or []) for r in records]
    if not sets:
        return []
    common = sets[0]
    for s in sets[1:]:
        common = common & s
    return sorted(common)


def _fold_live(items: list) -> tuple:
    """A Live Photo is one photograph, whatever the file system thinks.

    On disk it is a still and a movie with the same stem in the same folder; in some library
    schemas it is two rows. Counting it twice would inflate the asset count and, worse, would make
    every Live Photo look like a still with a video duplicate. The movie's bytes are folded into
    the still so the size total stays true.
    """
    by_key = {}
    for r in items:
        by_key.setdefault((r.get("dir") or "", r.get("stem") or ""), []).append(r)
    out, folded = [], 0
    for r in items:
        if not r.get("video"):
            out.append(r)
            continue
        group = by_key.get((r.get("dir") or "", r.get("stem") or ""), [])
        still = next((s for s in group if not s.get("video")), None)
        if still is None or not r.get("stem"):
            out.append(r)
            continue
        still["live_bytes"] = int(still.get("live_bytes") or 0) + max(0, int(r.get("bytes") or 0))
        still["live"] = True
        folded += 1
    return out, folded


# ---------------------------------------------------------------- duplicates

def _duplicates(items: list, hash_dupes: bool, cfg: dict) -> list:
    """Same size and same extension is a candidate; only a matching SHA-256 makes it a duplicate.

    The size grouping exists to keep the hashing bounded, never to stand in for it. A group whose
    bytes were never compared is still shown — twenty-five files of exactly the same size is worth
    a look — but it is marked unproven, it is counted separately, and `_reclaim` will not touch it.
    Anything else would put a guess into the tier whose whole meaning is "this one is a fact".
    """
    groups = {}
    for r in items:
        size = _size(r)
        if size > 0:
            groups.setdefault((size, r.get("ext") or ""), []).append(r)
    out = []
    for (size, ext), group in sorted(groups.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
        if len(group) < 2:
            continue
        if hash_dupes and size <= HASH_CAP:
            by_hash = {}
            for r in sorted(group, key=_order):
                digest = _digest(r)
                if digest:
                    by_hash.setdefault(digest, []).append(r)
            clusters = [g for g in (by_hash[k] for k in sorted(by_hash)) if len(g) > 1]
            proven, proof = True, "identical bytes (SHA-256)"
        else:
            clusters = [sorted(group, key=_order)]
            proven = False
            proof = ("same size and type; bytes not compared ({0} is over the {1} hashing limit)"
                     .format(human_bytes(size), human_bytes(HASH_CAP)) if size > HASH_CAP
                     else "same size and type; bytes not compared")
        for cluster in clusters:
            keeper = _keeper(cluster)
            others = [r for r in cluster if r["id"] != keeper["id"]]
            out.append({"name": keeper.get("filename") or keeper.get("id"), "copies": len(cluster),
                        "bytes": size, "size": human_bytes(size), "proof": proof, "proven": proven,
                        "wasted_bytes": size * (len(cluster) - 1),
                        "keeper": keeper["id"], "others": [r["id"] for r in others],
                        "paths": sorted(shorten_path(r.get("path") or r.get("filename") or r["id"], 52)
                                        for r in cluster)[:4],
                        "_cluster": cluster})
    return sorted(out, key=lambda d: (0 if d["proven"] else 1, -d["wasted_bytes"], d["name"]))


def _digest(r: dict) -> str:
    """Streaming SHA-256 of the whole file, or nothing at all.

    A digest of the first N bytes is not a digest: two different videos out of the same camera
    share a long header, and a truncated hash would call them the same file. So the read is bounded
    by refusing an oversized file outright rather than by stopping partway through one.
    """
    if r.get("sha256"):
        return str(r["sha256"])
    path = r.get("path") or ""
    if not path:
        return ""
    h = hashlib.sha256()
    read = 0
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(HASH_CHUNK)
                if not chunk:
                    break
                read += len(chunk)
                if read > HASH_CAP:
                    return ""
                h.update(chunk)
    except (OSError, ValueError):
        return ""
    if not read:
        return ""
    r["sha256"] = h.hexdigest()
    return r["sha256"]


def _keeper(group: list):
    """Which frame survives: a favourite or an edit if there is one, otherwise the first shot."""
    return sorted(group, key=lambda r: (0 if _protected(r) else 1,) + _order(r))[0]


def _dupe_view(dupes: list, top: int) -> dict:
    """Proven and unproven groups are two different claims, so they are two different numbers."""
    proven = [d for d in dupes if d["proven"]]
    guessed = [d for d in dupes if not d["proven"]]
    return {"groups": len(proven), "copies": sum(d["copies"] for d in proven),
            "extra": sum(d["copies"] - 1 for d in proven),
            "bytes": sum(d["wasted_bytes"] for d in proven),
            "proof": "identical bytes (SHA-256)",
            "unproven_groups": len(guessed), "unproven_extra": sum(d["copies"] - 1 for d in guessed),
            "unproven_bytes": sum(d["wasted_bytes"] for d in guessed),
            "unproven_note": (guessed[0]["proof"] if guessed else ""),
            "top": [{k: v for k, v in d.items() if not k.startswith("_")} for d in dupes[:top]]}


# ---------------------------------------------------------------- bursts

def _bursts(stills: list, window: int) -> list:
    """Runs of frames that are one press of the shutter: same instant, same frame, same counter.

    Every frame is compared with the group's *first* frame rather than with the one before it, so a
    burst can never be longer than the window. Chaining would be the wrong reading of "the same
    second": a time-lapse folder shot one frame per second would chain into a single group of four
    hundred, and this Play would then offer to reclaim three hundred and ninety-nine deliberate
    photographs. A bounded group errs towards keeping a frame too many, which is the right way for
    this particular number to be wrong. Everything the comparison uses is metadata; no image is
    ever decoded.
    """
    groups, current = [], []
    for r in stills:
        if current and _same_burst(current[0], current[-1], r, window):
            current.append(r)
            continue
        if len(current) > 1:
            groups.append(current)
        current = [r]
    if len(current) > 1:
        groups.append(current)
    return groups


def _same_burst(anchor: dict, prev: dict, b: dict, window: int) -> bool:
    """Time and frame size are measured against the group's first frame; the counter against its last.

    The counter has to run against the previous frame or a ten-shot burst would break in the middle
    of its own numbering, while the clock has to run against the first or the group has no bound.
    """
    if anchor.get("burst_id") and anchor.get("burst_id") == b.get("burst_id"):
        return True                                  # the library said so; nothing to infer
    if anchor.get("width") != b.get("width") or anchor.get("height") != b.get("height"):
        return False
    ta, tb = anchor.get("_when"), b.get("_when")
    if not ta or not tb or abs((tb - ta).total_seconds()) > window:
        return False
    return _sequential(prev.get("stem") or "", b.get("stem") or "")


_TRAILING = re.compile(r"^(.*?)(\d+)$")


def _sequential(a: str, b: str) -> bool:
    """`IMG_0421` and `IMG_0422` are one burst; `IMG_0421` and `sunset` are two photographs."""
    ma, mb = _TRAILING.match(a), _TRAILING.match(b)
    if not ma or not mb:
        return bool(a) and a == b
    if ma.group(1) != mb.group(1):
        return False
    return abs(int(ma.group(2)) - int(mb.group(2))) <= 4


def _burst_view(groups: list, top: int) -> dict:
    siblings = sum(len(g) - 1 for g in groups)
    rows = []
    for g in sorted(groups, key=lambda g: (-len(g), _order(g[0])))[:top]:
        keeper = _keeper(g)
        rows.append({"frames": len(g), "keeper": keeper.get("filename") or keeper["id"],
                     "bytes": sum(_size(r) for r in g if r["id"] != keeper["id"]),
                     "when": day(g[0].get("_when")) if g[0].get("_when") else "unknown"})
    return {"groups": len(groups), "siblings": siblings,
            "bytes": sum(_size(r) for g in groups for r in g if r["id"] != _keeper(g)["id"]),
            "largest": max([len(g) for g in groups] or [0]), "top": rows}


# ---------------------------------------------------------------- screenshots

def _shot_view(shots: list, now, shot_days: int, total: int, unknown: list) -> dict:
    seen = [r for r in shots if r.get("viewed")]
    old = [r for r in shots if r.get("_when") and (now - r["_when"]).days >= shot_days]
    knows_viewed = "viewed" not in unknown
    return {
        "count": len(shots), "bytes": sum(_size(r) for r in shots),
        "share": pct(len(shots), total),
        "reopen_known": knows_viewed,
        "reopened": len(seen) if knows_viewed else None,
        "never_reopened": (len(shots) - len(seen)) if knows_viewed else None,
        "never_share": pct(len(shots) - len(seen), len(shots)) if knows_viewed else None,
        "reopen_note": ("" if knows_viewed else
                        "this library's schema has no last-viewed column, so whether a screenshot "
                        "was ever reopened cannot be answered here"),
        "old": len(old), "old_bytes": sum(_size(r) for r in old),
    }


# ---------------------------------------------------------------- reclaim

def _reclaim(dupes: list, bursts: list, shots: list, now, shot_days: int) -> dict:
    """Three tiers, each asset counted once, favourites and edits never counted at all.

    The tiers are ordered by how much the claim can be defended: identical bytes is a fact, an
    extra burst frame is an inference, and an old screenshot is a judgement about the user's own
    habits. Adding them into one number without the split would be the dishonest version of this.
    """
    claimed = set()

    def take(candidates):
        out = []
        for r in sorted(candidates, key=_order):
            if r["id"] in claimed or _protected(r) or r.get("trashed") or not r.get("local", True):
                continue
            claimed.add(r["id"])
            out.append(r)
        return out

    # Only groups whose bytes were actually compared. An unproven group is a thing to look at,
    # never a thing to count in the tier whose name is a claim about the bytes.
    dupe_extra = take([r for d in dupes if d["proven"]
                       for r in d["_cluster"] if r["id"] != d["keeper"]])
    burst_extra = take([r for g in bursts for r in g if r["id"] != _keeper(g)["id"]])
    old_shots = take([r for r in shots if r.get("_when") and (now - r["_when"]).days >= shot_days])

    picked = [dupe_extra, burst_extra, old_shots]
    tiers = []
    for (name, confidence), group in zip(TIERS, picked):
        label = name if name != "old screenshots" else "screenshots >{0}d".format(shot_days)
        tiers.append({"name": label, "confidence": confidence, "count": len(group),
                      "bytes": sum(_size(r) for r in group)})
    pairs = [(t["name"], t["count"]) for t in tiers]
    return {"tiers": tiers, "count": sum(t["count"] for t in tiers),
            "bytes": sum(t["bytes"] for t in tiers),
            "safe_bytes": tiers[0]["bytes"],
            "bar": tier_bar(pairs), "legend": legend(pairs),
            "ids": sorted(claimed)}


# ---------------------------------------------------------------- shape

def _years(items: list) -> list:
    by_year, bytes_year = Counter(), Counter()
    for r in items:
        when = r.get("_added") or r.get("_when")
        if not when:
            continue
        # Bucketed in UTC, never in the local zone: the same library must produce the same card
        # on a laptop that crossed a date line since the last run.
        y = iso(when)[:4]
        if not y:
            continue
        by_year[y] += 1
        bytes_year[y] += _size(r)
    return [{"year": y, "assets": by_year[y], "bytes": bytes_year[y], "size": human_bytes(bytes_year[y])}
            for y in sorted(by_year)]


def _kinds(items: list) -> list:
    counts = Counter()
    for r in items:
        counts["screenshot" if r.get("screenshot") else
               "video" if r.get("video") else
               "live photo" if r.get("live") else "still"] += 1
    total = sum(counts.values()) or 1
    return [{"kind": k, "assets": c, "share": c / float(total)}
            for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _edge(items: list, now, first: bool):
    dated = [r for r in items if r.get("_when")]
    if not dated:
        return None
    r = sorted(dated, key=lambda r: (r["_when"], _order(r)))[0 if first else -1]
    return {"name": r.get("filename") or r["id"], "day": day(r["_when"]), "age": ago(r["_when"], now)}


def _method(unknown: list, hash_dupes: bool, records: list) -> dict:
    sources = sorted({str(r.get("source") or "unknown") for r in records})
    return {"sources": sources, "hashed": bool(hash_dupes), "unknown_fields": unknown,
            "burst_rule": "same capture second within the window, identical dimensions, sequential file names",
            "duplicate_rule": "SHA-256 over the file's bytes" if hash_dupes else "size and type only",
            "pixels": "never decoded"}


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    c = Card("PHOTO DEBT", "{0} assets".format(_n(v["assets"])), cfg.get("color"))
    c.blank()
    c.headline("{0} photos. {1} burst siblings.".format(_n(v["stills"]), _n(v["bursts"]["siblings"])), "1;36")
    shots = v["screenshots"]
    if shots["reopen_known"] and shots["count"]:
        c.headline("{0} screenshots, {1}% never reopened.".format(_n(shots["count"]), shots["never_share"]), "1;36")
    else:
        c.headline("{0} screenshots.".format(_n(shots["count"])), "1;36")
    c.headline("{0} byte-identical duplicates. {1} reclaimable.".format(
        _n(v["duplicates"]["extra"]), human_bytes(v["reclaim"]["bytes"])), "1;36")

    c.rule("WHAT IS IN THERE")
    for k in v["kinds"][:4]:
        c.bar(k["kind"], _n(k["assets"]), k["share"])
    c.row("{0} on disk · videos are {1}% of the bytes".format(human_bytes(v["local_bytes"]), v["video_byte_share"]))
    if v["live"]:
        c.row("{0} counted once each, not twice".format(plural(v["live"], "Live Photo")))
    if v["not_local"]:
        c.row("{0} not on this disk (iCloud placeholders), {1}% of the library".format(
            _n(v["not_local"]), v["not_local_share"]))
    if v["oldest"] and v["newest"]:
        c.row("{0} → {1} ({2} of photographs)".format(v["oldest"]["day"], v["newest"]["day"], v["oldest"]["age"]))

    if v["years"]:
        c.rule("ADDED PER YEAR")
        c.row("{0}  {1}".format(pad(v["spark_assets"], 26), rpad("assets", 8)))
        if v["spark_bytes"]:
            c.row("{0}  {1}".format(pad(v["spark_bytes"], 26), rpad("bytes", 8)))
        c.row(" ".join("{0} {1}".format(y["year"], _n(y["assets"])) for y in v["years"][-4:]))

    if v["bursts"]["groups"]:
        c.rule("BURSTS")
        c.row("{0} extra frames across {1} bursts, biggest {2} frames".format(
            _n(v["bursts"]["siblings"]), _n(v["bursts"]["groups"]), v["bursts"]["largest"]))
        for b in v["bursts"]["top"][:3]:
            c.cols("{0}× {1}".format(b["frames"], b["keeper"]), human_bytes(b["bytes"]), 12)

    if v["duplicates"]["groups"] or v["duplicates"]["unproven_groups"]:
        c.rule("THE SAME FILE TWICE")
        for d in v["duplicates"]["top"][:3]:
            c.cols("{0}{1}× {2}".format("" if d["proven"] else "maybe ", d["copies"], d["name"]),
                   human_bytes(d["wasted_bytes"]), 12)
        c.row("proof: {0}".format(v["duplicates"]["proof"]))
        if v["duplicates"]["unproven_groups"]:
            c.wrap("{0} more, {1}, are only the same size: too large to hash, so they are shown "
                   "but never counted as reclaimable.".format(
                       plural(v["duplicates"]["unproven_groups"], "group"),
                       human_bytes(v["duplicates"]["unproven_bytes"])))

    c.rule("SCREENSHOTS")
    c.row("{0}, {1}, {2}% of the library".format(
        plural(shots["count"], "screenshot"), human_bytes(shots["bytes"]), shots["share"]))
    if shots["reopen_known"]:
        c.row("{0} never reopened; {1} older than {2} days".format(
            _n(shots["never_reopened"] or 0), _n(shots["old"]), v["screenshot_days"]))
    else:
        c.wrap(shots["reopen_note"])

    c.rule("RECLAIMABLE")
    if v["reclaim"]["bar"]:
        c.row(v["reclaim"]["bar"])
        c.row(v["reclaim"]["legend"])
    for t in v["reclaim"]["tiers"]:
        c.cols("{0} ({1})".format(t["name"], t["confidence"]),
               "{0}  {1}".format(rpad(_n(t["count"]), 6), rpad(human_bytes(t["bytes"]), 8)), 18)
    if v["trashed"]["count"]:
        c.cols("already in Recently Deleted", "{0}  {1}".format(
            rpad(_n(v["trashed"]["count"]), 6), rpad(human_bytes(v["trashed"]["bytes"]), 8)), 18)
    c.row("{0} and {1} are excluded, always".format(
        plural(v["protected"]["favourites"], "favourite"),
        plural(v["protected"]["edited"], "edited asset")))

    c.blank()
    c.headline("{0} reclaimable, {1} of it certain".format(
        human_bytes(v["reclaim"]["bytes"]), human_bytes(v["reclaim"]["safe_bytes"])), "1;32")
    c.wrap(v["never_deletes"])
    if v["unknown_fields"]:
        c.wrap("Unknown on this schema: {0}.".format(", ".join(v["unknown_fields"])))
    c.note(v["since"])
    return c.close()


def _n(n) -> str:
    try:
        return "{0:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    shots = v["screenshots"]
    L = ["# Photo debt", "",
         "{0} assets, {1} on this disk. {2} reclaimable, {3} of it byte-certain.".format(
             _n(v["assets"]), human_bytes(v["local_bytes"]),
             human_bytes(v["reclaim"]["bytes"]), human_bytes(v["reclaim"]["safe_bytes"])), "",
         v["never_deletes"], "", v["no_pixel_compare"], "",
         "| measure | value |", "|---|---|",
         "| assets | {0} |".format(_n(v["assets"])),
         "| stills / videos | {0} / {1} |".format(_n(v["stills"]), _n(v["videos"])),
         "| Live Photos (counted once) | {0} |".format(_n(v["live"])),
         "| bytes on this disk | {0} |".format(human_bytes(v["local_bytes"])),
         "| videos' share of the bytes | {0}% |".format(v["video_byte_share"]),
         "| not on this disk (iCloud) | {0} ({1}%) |".format(_n(v["not_local"]), v["not_local_share"]),
         "| burst siblings | {0} across {1} bursts |".format(_n(v["bursts"]["siblings"]), _n(v["bursts"]["groups"])),
         "| byte-identical duplicates | {0} extra copies in {1} groups |".format(
             _n(v["duplicates"]["extra"]), _n(v["duplicates"]["groups"])),
         "| same size, bytes not compared | {0} extra copies in {1} groups, never counted as reclaimable |".format(
             _n(v["duplicates"]["unproven_extra"]), _n(v["duplicates"]["unproven_groups"])),
         "| screenshots | {0} ({1}) |".format(_n(shots["count"]), human_bytes(shots["bytes"])),
         "| screenshots never reopened | {0} |".format(
             "unknown on this schema" if not shots["reopen_known"] else _n(shots["never_reopened"])),
         "| already in Recently Deleted | {0} ({1}) |".format(
             _n(v["trashed"]["count"]), human_bytes(v["trashed"]["bytes"])),
         "| favourites, never reclaimable | {0} |".format(_n(v["protected"]["favourites"])),
         "| edited, never reclaimable | {0} |".format(_n(v["protected"]["edited"])), "",
         "## Reclaimable, by confidence", "", "| tier | confidence | assets | size |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} |".format(t["name"], t["confidence"], _n(t["count"]), human_bytes(t["bytes"]))
          for t in v["reclaim"]["tiers"]]
    L += ["", "Every asset is counted in at most one tier, and a favourite or an edited asset is "
          "counted in none of them.", ""]

    if v["years"]:
        L += ["## Added per year", "", "| year | assets | size |", "|---|---|---|"]
        L += ["| {0} | {1} | {2} |".format(y["year"], _n(y["assets"]), y["size"]) for y in v["years"]]
        L += [""]
    if v["bursts"]["top"]:
        L += ["## Biggest bursts", "", "| frames | keeper | when | extra bytes |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(b["frames"], b["keeper"], b["when"], human_bytes(b["bytes"]))
              for b in v["bursts"]["top"]]
        L += [""]
    if v["duplicates"]["top"]:
        L += ["## The same file twice", "", "| file | copies | wasted | proof |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(d["name"], d["copies"], human_bytes(d["wasted_bytes"]), d["proof"])
              for d in v["duplicates"]["top"]]
        L += [""]
    L += ["## Largest single assets", "", "| file | kind | size | age |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} |".format(b["name"], b["kind"], b["size"], b["age"]) for b in v["largest"]]

    L += ["", "## Method", "",
          "- Bursts: {0}, within {1}s.".format(v["method"]["burst_rule"], v["burst_window"]),
          "- Duplicates: {0}.".format(v["method"]["duplicate_rule"]),
          "- Screenshots: the saved-asset type the library records, falling back to the file name.",
          "- Pixels: {0}. No image is decoded and no similarity score is invented.".format(v["method"]["pixels"]),
          "- Sources read: {0}.".format(", ".join(v["method"]["sources"]) or "none"), ""]
    if v["unknown_fields"]:
        L += ["This library's schema does not expose: {0}. Those facts are reported as unknown "
              "rather than as zero.".format(", ".join(v["unknown_fields"])), ""]
    if shots["reopen_note"]:
        L += [shots["reopen_note"].capitalize() + ".", ""]

    L += ["## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "")
          for s in sources]
    L += ["", "Read-only. Asset metadata was read, and file bytes were read only to prove a "
          "duplicate. {0}".format(v["never_deletes"]), ""]
    return "\n".join(L)
