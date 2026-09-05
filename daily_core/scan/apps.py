"""app-graveyard: the applications you installed once, sized and dated.

macOS knows when every application was last opened and never shows you the list. Spotlight holds
kMDItemLastUsedDate; the bundle holds its identifier, its version and its architectures. Put those
together and the question "what is safe to delete" has an evidenced answer instead of a guess,
including the answer nobody expects: which apps are still Intel-only on an Apple silicon machine.
"""
import os
import platform
import plistlib
import subprocess
from pathlib import Path

from ..common import (Budget, Source, ago, expand, from_unix, human_bytes, iso, parse_date, read_bytes, walk)
from ..parsers.machoarch import architectures

KINDS = ("applications", "casks")
APP_ROOTS = ["/Applications", "~/Applications", "/Applications/Utilities", "~/Applications/Chrome Apps.localized"]
CASK_ROOTS = ["/opt/homebrew/Caskroom", "/usr/local/Caskroom", "~/homebrew/Caskroom"]
MDLS = "/usr/bin/mdls"
PER_APP_FILES = 40000


def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    if cfg.get("demo_root"):
        return _read_demo(kind, cfg["demo_root"])
    if kind == "applications":
        return _read_applications(budget, cfg)
    if kind == "casks":
        return _read_casks(budget)
    return [Source(name=kind).miss("unknown source")], []


# ---------------------------------------------------------------- applications

def _read_applications(budget: Budget, cfg: dict) -> tuple:
    roots = [expand(r) for r in (cfg.get("app_dirs") or APP_ROOTS)]
    sources, apps = [], []
    for root in roots:
        src = Source(name=str(root), path=str(root))
        if not root.is_dir():
            sources.append(src.miss("no such folder"))
            continue
        try:
            bundles = sorted(p for p in root.iterdir() if p.suffix == ".app")
        except (OSError, PermissionError) as exc:
            sources.append(src.miss("cannot list: {0}".format(str(exc)[:60])))
            continue
        for bundle in bundles:
            apps.append(_describe(bundle, budget))
        sources.append(src.hit(len(bundles)))
    if apps:
        _attach_last_used(apps, sources)
    if not sources:
        sources.append(Source(name="applications").miss("no application folder on this machine"))
    return sources, apps


def _describe(bundle: Path, budget: Budget) -> dict:
    info = {}
    try:
        info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes()) or {}
    except Exception:
        info = {}
    executable = info.get("CFBundleExecutable")
    exe_path = bundle / "Contents" / "MacOS" / str(executable) if executable else None
    arches = architectures(read_bytes(exe_path, 8192)) if exe_path and exe_path.is_file() else []
    size, files, complete = _measure(bundle, budget)
    try:
        st = bundle.stat()
        installed, touched = st.st_birthtime if hasattr(st, "st_birthtime") else st.st_ctime, st.st_mtime
        atime = max(st.st_atime, exe_path.stat().st_atime if exe_path and exe_path.is_file() else 0)
    except OSError:
        installed = touched = atime = 0
    return {"name": bundle.stem, "path": str(bundle),
            "bundle_id": str(info.get("CFBundleIdentifier") or ""),
            "version": str(info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or ""),
            "min_system": str(info.get("LSMinimumSystemVersion") or ""),
            "architectures": arches, "bytes": size, "files": files, "sized": complete,
            "installed": iso(from_unix(installed)), "updated": iso(from_unix(touched)),
            "accessed": iso(from_unix(atime)), "last_used": "", "last_used_source": ""}


def _measure(bundle: Path, budget: Budget) -> tuple:
    """Sum a bundle, capped: an Xcode-sized app must not spend the whole step's file budget."""
    total, count = 0, 0
    local = Budget(max_files=PER_APP_FILES, max_seconds=max(2.0, budget.max_seconds / 4.0))
    for _, st, _ in walk(bundle, local):
        total += st.st_size
        count += 1
        if not budget.spend(0):
            break
    return total, count, not local.exhausted and not budget.exhausted


def _attach_last_used(apps: list, sources: list) -> None:
    """Spotlight first, file access time second, and the card says which one answered.

    mdls prints one line per requested attribute per path, in the order the paths were given, so a
    single call answers for every application. A machine with Spotlight disabled returns nulls for
    all of them, which is why the access-time fallback is labelled rather than silently mixed in.
    """
    dates = _mdls([a["path"] for a in apps])
    got = 0
    for app, value in zip(apps, dates + [None] * (len(apps) - len(dates))):
        when = parse_date(value) if value else None
        if when:
            app["last_used"], app["last_used_source"] = iso(when), "spotlight"
            got += 1
        elif app["accessed"]:
            app["last_used"], app["last_used_source"] = app["accessed"], "file access time"
    if not dates:
        sources.append(Source(name="Spotlight last-used dates", path=MDLS).miss(
            "mdls unavailable; falling back to file access times, which are less exact"))
    else:
        sources.append(Source(name="Spotlight last-used dates", path=MDLS).hit(
            got, "{0} of {1} answered by Spotlight".format(got, len(apps))))


def _mdls(paths: list) -> list:
    """One fixed argv, no shell, read-only. Returns [] when Spotlight cannot answer at all."""
    if not paths or not os.path.exists(MDLS):
        return []
    out = []
    for chunk in [paths[i:i + 200] for i in range(0, len(paths), 200)]:
        try:
            proc = subprocess.run([MDLS, "-nullMarker", "", "-name", "kMDItemLastUsedDate"] + chunk,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return []
        lines = [l for l in proc.stdout.decode("utf-8", "replace").splitlines() if "kMDItemLastUsedDate" in l]
        if len(lines) != len(chunk):
            return []                       # a shape this reader does not understand is not guessed at
        out += [l.split("=", 1)[1].strip().strip('"') for l in lines]
    return out


# ---------------------------------------------------------------- homebrew casks

def _read_casks(budget: Budget) -> tuple:
    for root in (expand(r) for r in CASK_ROOTS):
        if not root.is_dir():
            continue
        src = Source(name="Homebrew casks", path=str(root))
        casks = []
        try:
            names = sorted(p for p in root.iterdir() if p.is_dir())
        except (OSError, PermissionError) as exc:
            return [src.miss(str(exc)[:60])], []
        for entry in names:
            size, files, complete = _measure(entry, budget)
            versions = sorted(p.name for p in entry.iterdir() if p.is_dir()) if entry.is_dir() else []
            casks.append({"name": entry.name, "path": str(entry), "bytes": size, "files": files,
                          "sized": complete, "versions": versions})
        return [src.hit(len(casks), "{0} versions on disk".format(sum(len(c["versions"]) for c in casks)))], casks
    return [Source(name="Homebrew casks", path=CASK_ROOTS[0]).miss("Homebrew is not installed here")], []


def _read_demo(kind: str, root) -> tuple:
    import json
    path = expand(root) / ("apps.json" if kind == "applications" else "casks.json")
    src = Source(name="{0} (demo)".format(kind), path=str(path))
    if not path.is_file():
        return [src.miss("fixture missing")], []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [src.miss("fixture unreadable: {0}".format(exc))], []
    return [src.hit(len(items), "bundled fixture")], items


# ---------------------------------------------------------------- analysis

def analyse(apps: list, casks: list, now, unused_days: int) -> dict:
    host = platform.machine()
    dated, undated = [], []
    for app in apps:
        when = parse_date(app["last_used"]) if app["last_used"] else None
        app["_when"] = when
        (dated if when else undated).append(app)

    def days(app):
        return (now - app["_when"]).days

    unused = sorted([a for a in dated if days(a) >= unused_days], key=lambda a: -a["bytes"])
    reclaim = sum(a["bytes"] for a in unused) + sum(a["bytes"] for a in undated)
    intel_only = [a for a in apps if a["architectures"] and "arm64" not in a["architectures"]]
    by_id = {}
    for app in apps:
        if app["bundle_id"]:
            by_id.setdefault(app["bundle_id"], []).append(app)
    duplicates = [{"bundle_id": k, "copies": len(v), "paths": sorted(a["path"] for a in v)}
                  for k, v in sorted(by_id.items()) if len(v) > 1]

    cask_names = {c["name"].lower().replace("-", "") for c in casks}
    app_names = {a["name"].lower().replace(" ", "").replace("-", "") for a in apps}
    orphan_casks = sorted(c["name"] for c in casks if c["name"].lower().replace("-", "") not in app_names
                          and not any(c["name"].lower().replace("-", "") in n for n in app_names))

    buckets = [0, 0, 0, 0]
    for app in dated:
        d = days(app)
        buckets[0 if d < 7 else 1 if d < 30 else 2 if d < 180 else 3] += 1

    return {
        "apps": len(apps), "bytes": sum(a["bytes"] for a in apps),
        "unsized": sum(1 for a in apps if not a["sized"]),
        "host_arch": host, "unused_days": unused_days,
        "never_used": len(undated), "unused": len(unused),
        "reclaimable": reclaim,
        "buckets": [{"label": l, "apps": c} for l, c in
                    zip(["this week", "this month", "6 months", "older"], buckets)],
        "graveyard": [{"name": a["name"], "size": human_bytes(a["bytes"]), "bytes": a["bytes"],
                       "last_used": (a["last_used"] or "")[:10], "age": ago(a["_when"], now) if a["_when"] else "never",
                       "how": a["last_used_source"], "version": a["version"]}
                      for a in (unused + sorted(undated, key=lambda a: -a["bytes"]))[:10]],
        "intel_only": [{"name": a["name"], "size": human_bytes(a["bytes"]),
                        "architectures": a["architectures"]} for a in
                       sorted(intel_only, key=lambda a: -a["bytes"])[:6]],
        "intel_only_total": len(intel_only),
        "translated": host == "arm64",
        "duplicates": duplicates[:6], "duplicate_total": len(duplicates),
        "spotlight": sum(1 for a in apps if a["last_used_source"] == "spotlight"),
        "guessed": sum(1 for a in apps if a["last_used_source"] == "file access time"),
        "casks": len(casks), "cask_bytes": sum(c["bytes"] for c in casks),
        "cask_versions": sum(max(0, len(c["versions"]) - 1) for c in casks),
        "orphan_casks": orphan_casks[:8], "orphan_cask_total": len(orphan_casks),
        "biggest": [{"name": a["name"], "size": human_bytes(a["bytes"])}
                    for a in sorted(apps, key=lambda a: -a["bytes"])[:5]],
    }


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card, bucket_bars

    c = Card("APP GRAVEYARD", human_bytes(v["bytes"]) + " installed", cfg.get("color"))
    c.blank()
    dead = v["unused"] + v["never_used"]
    c.headline("{0} of {1} apps unopened in {2}+ days".format(dead, v["apps"], v["unused_days"]), "1;36")
    c.headline("{0} reclaimable".format(human_bytes(v["reclaimable"])), "1;32")
    if v["never_used"]:
        c.row("{0} of those have no recorded opening at all".format(v["never_used"]))
    c.blank()

    c.rule("LAST OPENED")
    for line in bucket_bars([b["apps"] for b in v["buckets"]], [b["label"] for b in v["buckets"]]):
        c.row(line)
    c.row("{0} dated by Spotlight, {1} by file access time".format(v["spotlight"], v["guessed"]))

    if v["graveyard"]:
        c.rule("BIGGEST AND COLDEST")
        for g in v["graveyard"][:6]:
            c.cols("{0}  {1}".format(g["name"], g["version"]), "{0}  {1}".format(g["size"], g["age"]), 20)

    if v["intel_only_total"] and v["translated"]:
        c.rule("INTEL ONLY, ON AN ARM MACHINE")
        for a in v["intel_only"][:4]:
            c.cols(a["name"], a["size"], 12)
        c.wrap("Each of these runs under Rosetta every time you open it. Check for a universal "
               "build before you decide it is fine.")
    elif v["intel_only_total"]:
        c.row("{0} app(s) ship no arm64 slice".format(v["intel_only_total"]))

    if v["casks"]:
        c.rule("HOMEBREW")
        c.row("{0} casks, {1} on disk, {2} superseded version(s) still kept".format(
            v["casks"], human_bytes(v["cask_bytes"]), v["cask_versions"]))
        if v["orphan_cask_total"]:
            c.row("no matching app for: {0}".format(", ".join(v["orphan_casks"][:4])))

    if v["duplicate_total"]:
        c.rule("INSTALLED TWICE")
        for d in v["duplicates"][:3]:
            c.cols(d["bundle_id"], "{0} copies".format(d["copies"]), 12)

    c.blank()
    if v["unsized"]:
        c.row("{0} bundle(s) were larger than the per-app file cap; their sizes are lower bounds".format(v["unsized"]))
    c.wrap("Sizes are measured on disk. Nothing here is deleted, moved or opened: the list is "
           "yours to act on.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    L = ["# App graveyard", "",
         "{0} applications, {1} on disk. {2} have not been opened in {3} days or more.".format(
             v["apps"], human_bytes(v["bytes"]), v["unused"] + v["never_used"], v["unused_days"]), "",
         "| measure | value |", "|---|---|",
         "| applications | {0} |".format(v["apps"]),
         "| total size | {0} |".format(human_bytes(v["bytes"])),
         "| unopened {0}+ days | {1} |".format(v["unused_days"], v["unused"]),
         "| never opened on record | {0} |".format(v["never_used"]),
         "| reclaimable | {0} |".format(human_bytes(v["reclaimable"])),
         "| Intel-only bundles | {0} |".format(v["intel_only_total"]),
         "| installed twice | {0} |".format(v["duplicate_total"]),
         "| Homebrew casks | {0} ({1}) |".format(v["casks"], human_bytes(v["cask_bytes"])), "",
         "## The graveyard", "", "| app | version | size | last opened | dated by |", "|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} | {4} |".format(g["name"], g["version"] or "-", g["size"],
                                                   g["last_used"] or "never", g["how"] or "-")
          for g in v["graveyard"]]
    if v["intel_only"]:
        L += ["", "## Intel-only", "", "| app | size | architectures |", "|---|---|---|"]
        L += ["| {0} | {1} | {2} |".format(a["name"], a["size"], ", ".join(a["architectures"]))
              for a in v["intel_only"]]
    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "") for s in sources]
    L += ["", "Read-only. Bundles are measured and their headers read; nothing is executed, moved "
          "or removed. Last-opened dates come from Spotlight where it answered and from file "
          "access times otherwise, and every row says which.", ""]
    return "\n".join(L)
