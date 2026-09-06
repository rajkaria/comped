"""upstream-pulse: not "is there a CVE" — "is anyone still home?"

A vulnerability scanner tells you about the bugs somebody has already found and written down. This
tells you about the packages where nobody is looking for them any more: the last release was three
years ago, there is exactly one human who can publish, the repository is archived, and the thing is
sitting in the code path that answers requests. None of that is a CVE. All of it is the shape of
the next one.

## Why this module never opens a socket

`daily_core` is network-free and `tests/test_daily_safety.py` proves it statically, on every
commit, for every module in the package. That proof is the single most valuable claim these Plays
make and it is not worth trading for a registry lookup, so the work is split in two and the seam is
a file:

* the local half is here and in `parsers/lockfiles.py` — the inventory, the dependency graph, and
  every judgement that follows from them, all of it from files already on the disk;
* the network half is a TypeScript step in the Play, which queries the public registries and writes
  one JSON partial into `out_dir`. This module reads that partial as data.

So the numbers on the card come from two places and the card says which. If the partial is missing
or every lookup in it failed, the run still succeeds, still reports the whole inventory, and says
in as many words that the network half is unknown — because "we did not check it" must never read
as "it is fine".

## The JSON partial: `upstream-registry.json`

Written by the Play's registry step into `out_dir`, read here through `read_source("registry", …)`.
UTF-8, one JSON object. Unknown top-level and per-entry fields are ignored, so the step may add
more later without a version bump.

```json
{
  "schema": 1,
  "cached_at": "2026-09-05T08:30:00Z",
  "source": "registry.npmjs.org, pypi.org, proxy.golang.org, crates.io",
  "requested": 84,
  "packages": [
    {
      "name": "left-pad",
      "ecosystem": "npm",
      "pinned_version": "1.3.0",
      "latest_version": "1.3.0",
      "last_release_date": "2018-05-17T00:00:00Z",
      "release_dates": ["2016-03-23T00:00:00Z", "2018-05-17T00:00:00Z"],
      "maintainer_count": 1,
      "deprecated": true,
      "deprecation_message": "use String.prototype.padStart",
      "repository_archived": true,
      "license": "WTFPL",
      "pinned_license": "WTFPL",
      "successor": "",
      "error": ""
    }
  ]
}
```

| field | meaning, and what this module does without it |
|---|---|
| `schema` | integer, currently 1. A partial with a schema this module does not know is ignored with a note, never guessed at. |
| `cached_at` | RFC 3339 instant the registry data was fetched. Absent means the age of the answers is unknown and the card says so. |
| `source` | free text naming the registries queried. Printed, never parsed. |
| `requested` | how many lookups the step was asked for. Used only to report how many came back. |
| `packages[]` | one entry per package looked up. A package absent from this list is `not checked`, never healthy. |
| `.name` | the package name as the registry spells it. Matched against the lockfile inventory after PyPI's PEP 503 normalisation. |
| `.ecosystem` | one of `npm`, `pypi`, `go`, `crates`. Any other value makes the entry unmatched, and the package stays `unpriced`. |
| `.pinned_version` | the version your lockfile pins, echoed back so a mismatch is visible. |
| `.latest_version` | the newest version the registry offers. Absent means version drift is an unknown input, not a zero. |
| `.last_release_date` | RFC 3339 instant of the newest release. The dominant grade input; absent makes the whole staleness signal unknown. |
| `.release_dates[]` | recent release instants, newest or oldest first, both accepted. Used only for cadence — two years of them is plenty. |
| `.maintainer_count` | integer count of accounts that can publish. Absent (or negative) is unknown, and scores zero rather than a penalty. |
| `.deprecated` | boolean, the registry's own flag. |
| `.deprecation_message` | the registry's own text, printed verbatim and never parsed for a package name. |
| `.repository_archived` | boolean, whether the source repository the registry links to is archived. |
| `.license` | the licence of the latest version. |
| `.pinned_license` | the licence of the version you pin. Both are needed before this module will claim a licence changed; one alone proves nothing. |
| `.successor` | the replacement the registry itself names, or `""`. **The only source of a replacement hint in this Play.** Never inferred from a name, never extracted from prose. |
| `.error` | non-empty when the lookup failed. The package is then reported as failed, never as healthy. |

## The grade

Every package that was checked gets a dormancy grade A–F, and every single input to it is printed
next to it with its own points and its own maximum. A reader who thinks a single publisher matters
more than two years of silence can see both numbers, disagree with the weighting, and re-do the
arithmetic themselves. A bare score would be an assertion; a score with its inputs is an argument.

    last release     0-4   cadence          0-2   publishers    0-2
    deprecation      0-3   repository       0-2   licence       0-1   version drift  0-1

    A 0-1    B 2-3    C 4-6    D 7-9    F 10-15    ? not checked
"""
import json

from ..card import Card, legend, pad, rpad, tier_bar
from ..common import (Budget, Source, age_days, ago, baseline_read, baseline_write, day, delta,
                      expand, iso, parse_date, pct, plural, read_text, shorten_path, since_note,
                      walk)
from ..parsers import lockfiles

NAME = "upstream-pulse"
KINDS = ("lockfiles", "registry")

PARTIAL = "upstream-registry.json"
PARTIAL_SCHEMA = 1
DEMO_REGISTRY = "registry.json"

# The registries the Play's network step knows how to ask. Anything else is inventoried and
# labelled unpriced: counted, named, and honestly reported as never looked up.
CHECKABLE = ("crates", "go", "npm", "pypi")

DORMANT_DAYS = 730          # two years without a release
CACHE_HOURS = 24
GRADES = ("A", "B", "C", "D", "F")
UNKNOWN_GRADE = "?"

SKIP_DIRS = ("node_modules", ".git", ".hg", ".svn", "vendor", "target", "dist", "build",
             ".venv", "venv", "site-packages", ".tox", "__pycache__", ".next", ".cache",
             "Pods", "bower_components", ".gradle", ".terraform")

HEADLINE_CLASS = "single-publisher, dormant, and in the production path"

SIGNAL_ORDER = ("last release", "release cadence", "publishers", "deprecation", "repository",
                "licence", "version drift")
SIGNAL_MAX = {"last release": 4, "release cadence": 2, "publishers": 2, "deprecation": 3,
              "repository": 2, "licence": 1, "version drift": 1}
MAX_POINTS = 15

UNCHECKED_NOTE = ("not checked. Nothing here says these packages are healthy; it says nobody "
                  "asked the registry about them on this run.")


# ---------------------------------------------------------------- reading

def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    if kind == "lockfiles":
        return _read_lockfiles(budget, cfg)
    if kind == "registry":
        return _read_registry(cfg)
    return [Source(name=str(kind)).miss("not a source this Play reads")], []


def _read_lockfiles(budget: Budget, cfg: dict) -> tuple:
    """Every lockfile under the root, parsed locally. The whole first half of the Play.

    `demo_root` points at a bundled project tree and is walked exactly the same way, so the demo
    exercises the real readers rather than a manifest of pre-chewed answers.
    """
    root = expand(cfg.get("demo_root") or cfg.get("root") or "~")
    label = "lockfiles (demo)" if cfg.get("demo_root") else "lockfiles"
    src = Source(name=label, path=str(root))
    if not root.is_dir():
        return [src.miss("no folder at {0}".format(shorten_path(root, 40)))], []

    by_dir = {}
    for path, st, _depth in walk(root, budget, skip_names=SKIP_DIRS):
        if lockfiles.is_lockfile(path.name):
            by_dir.setdefault(path.parent, []).append(path.name)

    if not by_dir:
        return [src.miss("no lockfile under {0}".format(shorten_path(root, 40)))], []

    records, per_file = [], []
    for folder in sorted(by_dir, key=str):
        names = sorted(by_dir[folder])
        for name in names:
            # go.mod is a lockfile only when there is no go.sum beside it; otherwise it is the
            # manifest that tells go.sum which modules you asked for, and reading it twice would
            # count every module twice.
            if name == "go.mod" and "go.sum" in names:
                continue
            path = folder / name
            text = read_text(path)
            budget.spend(len(text.encode("utf-8", "replace")))
            manifest_text, manifest_name = "", ""
            for candidate in lockfiles.manifests_for(name):
                sibling = folder / candidate
                if sibling.is_file():
                    manifest_text, manifest_name = read_text(sibling), candidate
                    break
            result, packages = lockfiles.read(name, text, manifest_text, manifest_name)
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = str(path)
            note = result.get("note") or "{0}; direct from {1}".format(
                result.get("format") or name, result.get("direct_basis") or "nothing in the file")
            if manifest_name:
                note += "; read {0} beside it".format(manifest_name)
            entry = Source(name=rel, path=str(path))
            per_file.append(entry.hit(len(packages), note) if result.get("ok")
                            else entry.miss(result.get("note") or "unreadable"))
            for p in packages:
                p = dict(p)
                p["kind"] = "dep"
                p["lockfile"] = rel
                p["format"] = result.get("format") or name
                p["direct_basis"] = result.get("direct_basis") or ""
                records.append(p)
            if budget.exhausted:
                break
        if budget.exhausted:
            break

    files = len(per_file)
    src.hit(len(records), "{0} across {1}".format(
        plural(len(records), "package row"), plural(files, "lockfile")))
    return [src] + sorted(per_file, key=lambda s: s.name)[:12], _sorted(records)


def _read_registry(cfg: dict) -> tuple:
    """The JSON partial the Play's network step wrote. Missing is a labelled unknown, not a failure."""
    if cfg.get("demo_root"):
        path = expand(cfg["demo_root"]) / DEMO_REGISTRY
        label = "registry (demo)"
    else:
        given = cfg.get("registry_partial")
        path = expand(given) if given else (expand(cfg.get("out_dir") or ".") / PARTIAL)
        label = "registry"
    src = Source(name=label, path=str(path))
    if not path.is_file():
        return [src.miss("no {0} in {1}; the network half of this Play did not run".format(
            path.name, shorten_path(path.parent, 32)))], []
    try:
        doc = json.loads(read_text(path))
    except (ValueError, TypeError):
        return [src.miss("{0} is not readable JSON".format(path.name))], []
    if not isinstance(doc, dict):
        return [src.miss("{0} is not a JSON object".format(path.name))], []
    schema = doc.get("schema")
    if schema is not None and schema != PARTIAL_SCHEMA:
        return [src.miss("{0} declares schema {1}, this Play reads schema {2}".format(
            path.name, schema, PARTIAL_SCHEMA))], []

    entries = doc.get("packages")
    entries = entries if isinstance(entries, list) else []
    records = [{"kind": "registry_meta", "cached_at": str(doc.get("cached_at") or ""),
                "source": str(doc.get("source") or ""), "requested": doc.get("requested"),
                "returned": len(entries)}]
    failed = 0
    for raw in entries:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        entry = {"kind": "registry"}
        entry.update(raw)
        entry["name"] = str(raw.get("name"))
        entry["ecosystem"] = str(raw.get("ecosystem") or "")
        entry["error"] = str(raw.get("error") or "")
        if entry["error"]:
            failed += 1
        records.append(entry)
    note = "{0} looked up, {1} failed".format(plural(len(entries), "package"), failed)
    if doc.get("cached_at"):
        note += "; fetched {0}".format(doc.get("cached_at"))
    return [src.hit(len(entries) - failed, note)], _sorted(records)


def _sorted(records: list) -> list:
    return sorted(records, key=lambda r: (str(r.get("kind") or ""), str(r.get("ecosystem") or ""),
                                          str(r.get("name") or ""), str(r.get("version") or ""),
                                          str(r.get("lockfile") or "")))


# ---------------------------------------------------------------- the grade

def _signal(name: str, value: str, points: int, why: str, unknown: bool = False) -> dict:
    return {"signal": name, "value": value, "points": int(points), "max": SIGNAL_MAX[name],
            "why": why, "unknown": bool(unknown)}


def score(entry: dict, now, cfg: dict) -> dict:
    """Every input to the grade, each with its own points, its own maximum and its own reason.

    Returned whole so the card and the report can print the arithmetic instead of the conclusion.
    A caller can sum `points` themselves and get the same number; that is the point.
    """
    dormant_days = int(cfg.get("dormant_days") or DORMANT_DAYS)
    signals = []

    last = parse_date(entry.get("last_release_date") or "")
    n = age_days(last, now)
    if n is None:
        signals.append(_signal("last release", "unknown", 0,
                               "the registry gave no release date, so this scores nothing rather "
                               "than a penalty", True))
    else:
        points = 0 if n < 180 else 1 if n < 365 else 2 if n < 730 else 3 if n < 1460 else 4
        signals.append(_signal("last release", "{0} ago ({1})".format(ago(last, now), day(last)),
                               points, "0 under 6 months · 1 under a year · 2 under two years · "
                                       "3 under four · 4 beyond that"))

    dates = sorted(d for d in [parse_date(x) for x in (entry.get("release_dates") or [])] if d)
    recent = sum(1 for d in dates if (now - d).days < 365)
    prior = sum(1 for d in dates if 365 <= (now - d).days < 730)
    if len(dates) < 2:
        signals.append(_signal("release cadence", "unknown", 0,
                               "fewer than two release dates were supplied", True))
    elif recent == 0 and prior == 0:
        signals.append(_signal("release cadence", "no release in two years", 2,
                               "2 when releases stopped · 1 when they slowed · 0 when steady"))
    elif recent == 0:
        signals.append(_signal("release cadence", "{0} two years ago, none since".format(prior), 2,
                               "2 when releases stopped · 1 when they slowed · 0 when steady"))
    elif recent < prior:
        signals.append(_signal("release cadence", "{0} this year, {1} the year before".format(
            recent, prior), 1, "2 when releases stopped · 1 when they slowed · 0 when steady"))
    else:
        signals.append(_signal("release cadence", "{0} this year, {1} the year before".format(
            recent, prior), 0, "2 when releases stopped · 1 when they slowed · 0 when steady"))

    count = entry.get("maintainer_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        signals.append(_signal("publishers", "unknown", 0,
                               "the registry did not say how many accounts can publish", True))
    else:
        points = 2 if count <= 1 else 1 if count == 2 else 0
        signals.append(_signal("publishers", plural(count, "account"), points,
                               "2 for a single publisher · 1 for two · 0 for three or more"))

    if entry.get("deprecated"):
        message = str(entry.get("deprecation_message") or "").strip()
        signals.append(_signal("deprecation", "deprecated by its own publisher", 3,
                               "3 when the registry's deprecation flag is set" +
                               (": " + message if message else "")))
    else:
        signals.append(_signal("deprecation", "not deprecated", 0,
                               "3 when the registry's deprecation flag is set"))

    if entry.get("repository_archived"):
        signals.append(_signal("repository", "archived", 2,
                               "2 when the linked source repository is archived"))
    else:
        signals.append(_signal("repository", "not archived", 0,
                               "2 when the linked source repository is archived"))

    pinned_licence = str(entry.get("pinned_license") or "").strip()
    latest_licence = str(entry.get("license") or "").strip()
    if not pinned_licence or not latest_licence:
        signals.append(_signal("licence", latest_licence or "unknown", 0,
                               "both the pinned and the current licence are needed before a "
                               "change can be claimed", True))
    elif pinned_licence != latest_licence:
        signals.append(_signal("licence", "{0} → {1}".format(pinned_licence, latest_licence), 1,
                               "1 when the licence changed after the version you pin"))
    else:
        signals.append(_signal("licence", "{0}, unchanged".format(latest_licence), 0,
                               "1 when the licence changed after the version you pin"))

    pinned = str(entry.get("pinned_version") or "").strip()
    latest = str(entry.get("latest_version") or "").strip()
    if not pinned or not latest:
        signals.append(_signal("version drift", "unknown", 0,
                               "the registry did not give both versions", True))
    elif pinned != latest:
        signals.append(_signal("version drift", "pinned {0}, latest {1}".format(pinned, latest), 1,
                               "1 when the pin is behind the newest release"))
    else:
        signals.append(_signal("version drift", "on the newest release ({0})".format(latest), 0,
                               "1 when the pin is behind the newest release"))

    signals.sort(key=lambda s: SIGNAL_ORDER.index(s["signal"]))
    points = sum(s["points"] for s in signals)
    grade = "A" if points <= 1 else "B" if points <= 3 else "C" if points <= 6 else \
        "D" if points <= 9 else "F"
    return {
        "signals": signals,
        "points": points,
        "max_points": MAX_POINTS,
        "grade": grade,
        "unknown_inputs": sorted(s["signal"] for s in signals if s["unknown"]),
        "dormant": None if n is None else n >= dormant_days,
        "dormant_days": None if n is None else n,
        "last_release": day(last),
        "single_maintainer": None if not isinstance(count, int) or isinstance(count, bool) or count < 0
        else count <= 1,
        "maintainer_count": count if isinstance(count, int) and not isinstance(count, bool) else None,
        "deprecated": bool(entry.get("deprecated")),
        "archived": bool(entry.get("repository_archived")),
        "licence": latest_licence,
        "pinned_licence": pinned_licence,
        "licence_changed": bool(pinned_licence and latest_licence and pinned_licence != latest_licence),
        "cadence": [s["value"] for s in signals if s["signal"] == "release cadence"][0],
    }


def replacement(entry: dict) -> dict:
    """The only replacement hint this Play will ever produce, and it comes from one field.

    A registry that names a successor is stating a fact its publisher put there. Everything else —
    a similarly spelled package, a fork with more stars, the name in the middle of a deprecation
    sentence — is a guess, and a guess about what to install is exactly the wrong thing for a
    read-only report to make. So: `successor`, verbatim, or nothing at all. The deprecation message
    is carried alongside as the publisher's own words and is never mined for a name.
    """
    successor = str(entry.get("successor") or "").strip()
    if not successor:
        return {"successor": "", "source": "", "message": str(entry.get("deprecation_message") or "").strip()}
    return {"successor": successor, "source": "the registry's own successor field",
            "message": str(entry.get("deprecation_message") or "").strip()}


# ---------------------------------------------------------------- analysis

def analyse(records: list, now, cfg: dict) -> dict:
    deps = [r for r in records if r.get("kind") == "dep"]
    meta = {}
    registry = {}
    for r in records:
        if r.get("kind") == "registry_meta":
            meta = r
        elif r.get("kind") == "registry":
            eco = str(r.get("ecosystem") or "")
            registry[(eco, lockfiles.normalise(eco, r.get("name")))] = r

    depth_limit = max(0, int(cfg.get("depth") or 0))
    dormant_days = int(cfg.get("dormant_days") or DORMANT_DAYS)
    packages = _merge(deps)
    lockfile_rows = _lockfile_rows(deps)

    for pkg in packages:
        _classify(pkg, registry, depth_limit, now, cfg)

    checked = [p for p in packages if p["check_state"] == "checked"]
    requested = [p for p in packages if p["requested"]]
    failed = [p for p in packages if p["check_state"] == "failed"]
    missing = [p for p in packages if p["check_state"] == "missing"]
    unpriced = [p for p in packages if p["check_state"] == "unpriced"]
    not_requested = [p for p in packages if p["check_state"] == "not requested"]
    local = [p for p in packages if p["check_state"] == "local"]

    offline = bool(requested) and not checked
    dormant = [p for p in checked if p["dormant"]]
    single = [p for p in checked if p["single_maintainer"]]
    deprecated = [p for p in checked if p["deprecated"]]
    archived = [p for p in checked if p["archived"]]
    licence_changed = [p for p in checked if p["licence_changed"]]
    both = [p for p in dormant if p["single_maintainer"]]
    headline = [p for p in both if p["blast"]["radius"] == "production"]

    direct = [p for p in packages if p["direct"] is True]
    transitive = [p for p in packages if p["direct"] is False]
    direct_unknown = [p for p in packages if p["direct"] is None]
    production = [p for p in packages if p["blast"]["radius"] == "production"]
    development = [p for p in packages if p["blast"]["radius"] == "dev/test"]
    scope_unknown = [p for p in packages if p["blast"]["radius"] == "unknown"]

    grades = dict((g, sum(1 for p in checked if p["grade"] == g)) for g in GRADES)
    grades[UNKNOWN_GRADE] = len(packages) - len(checked)

    view = {
        "schema": PARTIAL_SCHEMA,
        "name": NAME,
        "generated": iso(now),
        "root": str(expand(cfg.get("demo_root") or cfg.get("root") or "~")),
        "lockfiles": lockfile_rows,
        "ecosystems": _ecosystems(packages),
        "totals": {
            "packages": len(packages),
            "direct": len(direct),
            "transitive": len(transitive),
            "direct_unknown": len(direct_unknown),
            "production": len(production),
            "development": len(development),
            "scope_unknown": len(scope_unknown),
            "local": len(local),
            "lockfiles": len(lockfile_rows),
        },
        "checks": {
            "requested": len(requested),
            "checked": len(checked),
            "failed": len(failed),
            "missing": len(missing),
            "not_requested": len(not_requested),
            "unpriced": len(unpriced),
            "local": len(local),
        },
        "network": {
            "offline": offline,
            "checked": len(checked),
            "unchecked": len(packages) - len(checked),
            "note": UNCHECKED_NOTE,
            "reason": _offline_reason(offline, requested, failed, missing, meta),
            "source": str(meta.get("source") or ""),
        },
        "cache": _cache(meta, now, cfg),
        "depth": {
            "limit": depth_limit,
            "transitive_included": depth_limit > 0,
            "note": ("direct dependencies only: transitive packages are inventoried but not looked "
                     "up, because turning {0} lookups into every package in the graph is the "
                     "difference between a run and a rate limit. Pass depth=1 or more to widen it."
                     ).format(len(requested)) if depth_limit == 0 else
                    "transitive packages up to depth {0} were looked up too".format(depth_limit),
        },
        "grades": grades,
        "grade_tiers": [[g, grades[g]] for g in ("F", "D", "C", "B", "A")],
        "dormant": {
            "days": dormant_days,
            "years": round(dormant_days / 365.0, 1),
            "count": len(dormant),
            "share": pct(len(dormant), len(checked)),
            "packages": [_brief(p) for p in dormant],
        },
        "single_maintainer": {"count": len(single), "packages": [_brief(p) for p in single]},
        "deprecated": {"count": len(deprecated), "packages": [_brief(p) for p in deprecated]},
        "archived": {"count": len(archived), "packages": [_brief(p) for p in archived]},
        "licence_changes": [
            {"name": p["display"], "ecosystem": p["ecosystem"], "from": p["pinned_licence"],
             "to": p["licence"], "pinned_version": p["version"]} for p in licence_changed],
        "headline": {
            "class": HEADLINE_CLASS,
            "count": len(headline),
            "both": len(both),
            "packages": [_brief(p) for p in headline],
            "also_dev": [_brief(p) for p in both if p["blast"]["radius"] != "production"],
        },
        "worst": [_full(p) for p in sorted(
            checked, key=lambda q: (-q["points"], q["ecosystem"], q["name"]))[:8]],
        "replacements": [
            {"name": p["display"], "ecosystem": p["ecosystem"], "successor": p["replacement"]["successor"],
             "source": p["replacement"]["source"], "message": p["replacement"]["message"]}
            for p in sorted(checked, key=lambda q: (q["ecosystem"], q["name"]))
            if p["replacement"]["successor"]],
        "deprecated_without_successor": [
            _brief(p) for p in deprecated if not p["replacement"]["successor"]],
        "packages": [_full(p) for p in packages],
        "unpriced": {"count": len(unpriced),
                     "ecosystems": sorted(set(p["ecosystem"] for p in unpriced)),
                     "packages": [_brief(p) for p in unpriced]},
    }
    view["snapshot"] = _snapshot(view, packages)
    baseline = baseline_read(cfg["out_dir"], NAME) if cfg.get("out_dir") else {}
    view["delta"] = delta(view["snapshot"], baseline.get("payload") or {})
    view["since"] = since_note(baseline, now)
    view["notes"] = _notes(view)
    return view


def save_baseline(view: dict, cfg: dict, now) -> str:
    return baseline_write(cfg["out_dir"], NAME, view["snapshot"], now) if cfg.get("out_dir") else ""


def _merge(deps: list) -> list:
    """One row per package, however many lockfiles mention it. Worst case wins every field."""
    merged = {}
    for r in deps:
        eco = str(r.get("ecosystem") or "unknown")
        name = lockfiles.normalise(eco, r.get("name"))
        key = (eco, name)
        pkg = merged.get(key)
        if pkg is None:
            pkg = {"key": "{0}:{1}".format(eco, name), "ecosystem": eco, "name": name,
                   "display": str(r.get("display") or name), "versions": [], "lockfiles": [],
                   "direct": False, "direct_seen": [], "scopes": [], "depths": [], "path": [],
                   "local": True, "bases": []}
            merged[key] = pkg
        version = str(r.get("version") or "")
        if version and version not in pkg["versions"]:
            pkg["versions"].append(version)
        if r.get("lockfile") and r["lockfile"] not in pkg["lockfiles"]:
            pkg["lockfiles"].append(r["lockfile"])
        pkg["direct_seen"].append(r.get("direct"))
        pkg["scopes"].append(str(r.get("scope") or "unknown"))
        if isinstance(r.get("depth"), int):
            pkg["depths"].append(r["depth"])
        if r.get("path") and (not pkg["path"] or len(r["path"]) < len(pkg["path"])):
            pkg["path"] = list(r["path"])
        if not r.get("local"):
            pkg["local"] = False
        if r.get("direct_basis") and r["direct_basis"] not in pkg["bases"]:
            pkg["bases"].append(r["direct_basis"])

    out = []
    for key in sorted(merged):
        pkg = merged[key]
        seen = pkg.pop("direct_seen")
        pkg["direct"] = True if True in seen else (None if None in seen else False)
        scopes = pkg.pop("scopes")
        pkg["scope"] = ("production" if "production" in scopes else
                        "development" if "development" in scopes else "unknown")
        pkg["versions"] = sorted(pkg["versions"])
        pkg["version"] = pkg["versions"][0] if pkg["versions"] else ""
        pkg["lockfiles"] = sorted(pkg["lockfiles"])
        pkg["depth"] = min(pkg["depths"]) if pkg["depths"] else None
        pkg.pop("depths")
        pkg["blast"] = {
            "radius": ("production" if pkg["scope"] == "production" else
                       "dev/test" if pkg["scope"] == "development" else "unknown"),
            "direct": pkg["direct"],
            "depth": pkg["depth"],
            "path": pkg["path"],
            "lockfiles": pkg["lockfiles"],
            "why": _blast_why(pkg),
        }
        out.append(pkg)
    return out


def _blast_why(pkg: dict) -> str:
    if pkg["scope"] == "unknown":
        return ("the lockfile does not record which of its packages are dev-only, so this could be "
                "either; it is not counted as dev/test")
    where = "the production path" if pkg["scope"] == "production" else "dev and test only"
    if pkg["direct"] is True:
        return "you asked for it directly, in {0}".format(where)
    if pkg["path"] and len(pkg["path"]) > 1:
        return "reached through {0}".format(" → ".join(pkg["path"]))
    if pkg["direct"] is None:
        return "in {0}; the lockfile does not say whether you asked for it".format(where)
    return "a transitive dependency in {0}".format(where)


def _classify(pkg: dict, registry: dict, depth_limit: int, now, cfg: dict):
    """Decide whether this package was looked up, and if so grade it. Never invents an answer."""
    pkg["checkable"] = pkg["ecosystem"] in CHECKABLE
    wanted = pkg["direct"] is not False or (
        depth_limit > 0 and (pkg["depth"] is None or pkg["depth"] <= depth_limit))
    pkg["requested"] = bool(wanted and pkg["checkable"] and not pkg["local"])
    entry = registry.get((pkg["ecosystem"], pkg["name"])) or {}

    defaults = {"grade": UNKNOWN_GRADE, "points": None, "max_points": MAX_POINTS, "signals": [],
                "unknown_inputs": [], "dormant": None, "dormant_days": None, "last_release": "",
                "single_maintainer": None, "maintainer_count": None, "deprecated": False,
                "archived": False, "licence": "", "pinned_licence": "", "licence_changed": False,
                "cadence": "unknown", "latest_version": "",
                "replacement": {"successor": "", "source": "", "message": ""}}
    pkg.update(defaults)

    if pkg["local"]:
        pkg["check_state"] = "local"
        pkg["status"] = "your own package, not something you depend on"
        return
    if not pkg["checkable"]:
        pkg["check_state"] = "unpriced"
        pkg["status"] = "no registry this Play knows how to ask about {0}".format(
            pkg["ecosystem"] or "this ecosystem")
        return
    if not wanted:
        pkg["check_state"] = "not requested"
        pkg["status"] = "transitive, and transitive lookups are off (depth={0})".format(depth_limit)
        return
    if not entry:
        pkg["check_state"] = "missing"
        pkg["status"] = "not in the registry partial"
        return
    if entry.get("error"):
        pkg["check_state"] = "failed"
        pkg["status"] = "the lookup failed: {0}".format(entry.get("error"))
        return

    graded = score(entry, now, cfg)
    pkg.update(graded)
    pkg["latest_version"] = str(entry.get("latest_version") or "")
    pkg["replacement"] = replacement(entry)
    pkg["check_state"] = "checked"
    pkg["status"] = "grade {0} ({1} of {2} points)".format(
        graded["grade"], graded["points"], MAX_POINTS)


def _brief(pkg: dict) -> dict:
    return {"name": pkg["display"], "ecosystem": pkg["ecosystem"], "version": pkg["version"],
            "grade": pkg["grade"], "points": pkg["points"], "radius": pkg["blast"]["radius"],
            "direct": pkg["direct"], "last_release": pkg["last_release"],
            "maintainers": pkg["maintainer_count"], "why": pkg["blast"]["why"],
            "lockfiles": pkg["lockfiles"]}


def _full(pkg: dict) -> dict:
    out = dict(pkg)
    out.pop("bases", None)
    return out


def _ecosystems(packages: list) -> list:
    rows = {}
    for p in packages:
        row = rows.setdefault(p["ecosystem"], {"ecosystem": p["ecosystem"], "packages": 0,
                                               "direct": 0, "checkable": p["ecosystem"] in CHECKABLE})
        row["packages"] += 1
        if p["direct"] is True:
            row["direct"] += 1
    return [rows[k] for k in sorted(rows)]


def _lockfile_rows(deps: list) -> list:
    rows = {}
    for r in deps:
        name = str(r.get("lockfile") or "")
        row = rows.setdefault(name, {"lockfile": name, "format": str(r.get("format") or ""),
                                     "ecosystem": str(r.get("ecosystem") or ""), "packages": 0,
                                     "direct": 0, "direct_basis": str(r.get("direct_basis") or "")})
        row["packages"] += 1
        if r.get("direct") is True:
            row["direct"] += 1
    return [rows[k] for k in sorted(rows)]


def _offline_reason(offline: bool, requested: list, failed: list, missing: list, meta: dict) -> str:
    if not requested:
        return "nothing was requested: no package in the inventory is in an ecosystem this Play checks"
    if not offline:
        return ""
    if failed and not missing:
        return "every one of the {0} lookups in the partial reported an error".format(len(failed))
    if not meta:
        return ("the registry partial was not there at all, so the network half of this Play did "
                "not run")
    return "the partial answered for none of the {0} packages this Play asked about".format(
        len(requested))


def _cache(meta: dict, now, cfg: dict) -> dict:
    window = float(cfg.get("cache_hours") or CACHE_HOURS)
    cached = parse_date(meta.get("cached_at") or "") if meta else None
    if not cached:
        return {"cached_at": "", "age_hours": None, "window_hours": window, "within_window": False,
                "fresh": None,
                "note": "the partial did not say when it was fetched, so how old these registry "
                        "answers are is unknown"}
    hours = round(max(0.0, (now - cached).total_seconds() / 3600.0), 1)
    within = hours < window
    return {
        "cached_at": iso(cached), "age_hours": hours, "window_hours": window,
        "within_window": within, "fresh": within,
        "note": ("these registry answers are {0}h old, inside the {1}h cache window: this run is "
                 "reporting yesterday's facts, not today's".format(hours, int(window)) if within
                 else "these registry answers are {0}h old, past the {1}h cache window".format(
                     hours, int(window))),
    }


def _snapshot(view: dict, packages: list) -> dict:
    """What the next run compares against: one number per package, plus the headline counts."""
    snap = {"@direct": view["totals"]["direct"], "@dormant": view["dormant"]["count"],
            "@single-publisher": view["single_maintainer"]["count"],
            "@headline": view["headline"]["count"], "@packages": view["totals"]["packages"]}
    for p in packages:
        if p["points"] is not None:
            snap[p["key"]] = p["points"]
    return snap


def _notes(view: dict) -> list:
    notes = []
    if view["network"]["offline"]:
        notes.append("The registry half did not answer: {0}. The inventory below is complete; "
                     "every grade is “?” and {1}".format(
                         view["network"]["reason"], UNCHECKED_NOTE))
    elif view["network"]["unchecked"]:
        notes.append("{0} of {1} packages were {2}".format(
            view["network"]["unchecked"], view["totals"]["packages"], UNCHECKED_NOTE))
    if view["totals"]["direct_unknown"]:
        notes.append("{0} of {1} packages sit in a lockfile that does not record which of them you "
                     "asked for, so they are counted separately rather than folded into either "
                     "number".format(view["totals"]["direct_unknown"], view["totals"]["packages"]))
    if view["totals"]["scope_unknown"]:
        notes.append("{0} of {1} packages could not be placed in the production or the dev path "
                     "from the lockfile alone; they are not counted as dev-only".format(
                         view["totals"]["scope_unknown"], view["totals"]["packages"]))
    if view["unpriced"]["count"]:
        notes.append("{0} packages are in an ecosystem this Play cannot query ({1}); they are "
                     "inventoried and left unpriced".format(
                         view["unpriced"]["count"], ", ".join(view["unpriced"]["ecosystems"])))
    notes.append(view["cache"]["note"])
    notes.append(view["depth"]["note"])
    notes.append("Replacement hints come from one place only: the registry's own successor field. "
                 "Nothing here is inferred from a package name.")
    return notes


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    t, n = v["totals"], v["network"]
    c = Card("UPSTREAM PULSE", "{0} pkgs".format(t["packages"]), cfg.get("color"))
    c.blank()
    c.headline("{0}. {1} no release in {2} years.".format(
        plural(t["direct"], "direct dependency", "direct dependencies"),
        v["dormant"]["count"], v["dormant"]["years"]), "1;36")
    c.wrap("{0} single-publisher. {1}".format(
        v["single_maintainer"]["count"], _headline_tail(v)))
    c.blank()

    c.rule("DORMANCY GRADE")
    tiers = [(g, n_) for g, n_ in v["grade_tiers"]]
    bar = tier_bar(tiers, 40)
    if bar:
        c.row(bar)
        c.row(legend(tiers))
    c.row("{0} of {1} checked · {2} not checked".format(
        n["checked"], t["packages"], n["unchecked"]))
    if n["offline"]:
        c.wrap("No registry answer: {0}.".format(n["reason"]))
        c.wrap("Nothing below says a package is healthy — only that nobody asked.")

    worst = v["worst"][0] if v["worst"] else None
    if worst:
        c.rule("WHY {0} IS {1}".format(str(worst["display"]).upper()[:28], worst["grade"]))
        for s in worst["signals"]:
            c.row("{0}{1}/{2}  {3}".format(pad(s["signal"], 17), rpad(str(s["points"]), 2),
                                           pad(str(s["max"]), 2), s["value"]))
        c.row("{0}{1}/{2}  grade {3}".format(pad("total", 17), rpad(str(worst["points"]), 2),
                                             pad(str(worst["max_points"]), 2), worst["grade"]))
        c.wrap("blast radius: {0} — {1}".format(worst["blast"]["radius"], worst["blast"]["why"]))

    if v["headline"]["count"]:
        c.rule("DORMANT · SINGLE-PUBLISHER · PRODUCTION")
        for p in v["headline"]["packages"][:4]:
            c.cols("{0} {1}".format(p["name"], p["version"]),
                   "{0} · {1}".format(p["last_release"] or "no date",
                                      plural(p["maintainers"] or 0, "publisher")), 26)

    if v["replacements"]:
        c.rule("THE REGISTRY NAMES A SUCCESSOR")
        for r in v["replacements"][:3]:
            c.cols(r["name"], "→ {0}".format(r["successor"]), 26)
        c.row("(only where the registry says so; never inferred)")

    if v["unpriced"]["count"]:
        c.rule("INVENTORIED, NOT PRICED")
        c.wrap("{0} in {1}: counted, never looked up.".format(
            plural(v["unpriced"]["count"], "package"),
            ", ".join(v["unpriced"]["ecosystems"]) or "an unknown ecosystem"))

    c.blank()
    c.row("{0} · {1}".format(v["since"], _delta_line(v["delta"])))
    c.wrap(v["cache"]["note"])
    return c.close()


def _headline_tail(v: dict) -> str:
    both, head = v["headline"]["both"], v["headline"]["count"]
    if not both:
        return "None are both."
    if not head:
        return "{0} both, none in the production path.".format(both)
    return "{0} both, and {1} in your production request path.".format(
        both, "one is" if head == 1 else "{0} are".format(head))


def _delta_line(d: dict) -> str:
    if d.get("first_run"):
        return "first run: nothing to compare against yet"
    moved = len(d.get("grew") or {}) + len(d.get("shrank") or {})
    return "{0} added, {1} gone, {2} changed grade points".format(
        len(d.get("added") or {}), len(d.get("removed") or {}), moved)


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    t, n, ch = v["totals"], v["network"], v["checks"]
    L = ["# Upstream pulse", "",
         "{0} across {1}. {2} were checked against a registry; {3} were not.".format(
             plural(t["packages"], "package"), plural(t["lockfiles"], "lockfile"),
             n["checked"], n["unchecked"]), ""]
    if n["offline"]:
        L += ["> **The network half did not answer.** {0}. Everything below is the lockfile "
              "inventory, which is complete. Every grade is `?`, and that is {1}".format(
                  n["reason"], UNCHECKED_NOTE), ""]

    L += ["## The inventory", "", "| measure | count | of | share |", "|---|---|---|---|",
          "| direct dependencies | {0} | {1} packages | {2}% |".format(
              t["direct"], t["packages"], pct(t["direct"], t["packages"])),
          "| transitive | {0} | {1} packages | {2}% |".format(
              t["transitive"], t["packages"], pct(t["transitive"], t["packages"])),
          "| direct-ness not recorded | {0} | {1} packages | {2}% |".format(
              t["direct_unknown"], t["packages"], pct(t["direct_unknown"], t["packages"])),
          "| in the production path | {0} | {1} packages | {2}% |".format(
              t["production"], t["packages"], pct(t["production"], t["packages"])),
          "| dev/test only | {0} | {1} packages | {2}% |".format(
              t["development"], t["packages"], pct(t["development"], t["packages"])),
          "| path not recorded | {0} | {1} packages | {2}% |".format(
              t["scope_unknown"], t["packages"], pct(t["scope_unknown"], t["packages"])), "",
          "## What was and was not looked up", "", "| state | packages | of |", "|---|---|---|",
          "| checked | {0} | {1} |".format(ch["checked"], t["packages"]),
          "| lookup failed | {0} | {1} |".format(ch["failed"], t["packages"]),
          "| absent from the partial | {0} | {1} |".format(ch["missing"], t["packages"]),
          "| transitive, not requested | {0} | {1} |".format(ch["not_requested"], t["packages"]),
          "| unpriced ecosystem | {0} | {1} |".format(ch["unpriced"], t["packages"]),
          "| your own packages | {0} | {1} |".format(ch["local"], t["packages"]), "",
          v["depth"]["note"], "", v["cache"]["note"], ""]

    L += ["## Dormancy grades", "", "| grade | packages | of checked |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(g, c, n["checked"]) for g, c in v["grade_tiers"]]
    L += ["| ? (not checked) | {0} | of all {1} packages |".format(
        v["grades"][UNKNOWN_GRADE], t["packages"]), ""]

    L += ["## The headline class: {0}".format(HEADLINE_CLASS), "",
          "{0} of {1} checked packages are both dormant and single-publisher; {2} of those {3} in "
          "the production path.".format(v["headline"]["both"], n["checked"],
                                        v["headline"]["count"],
                                        "is" if v["headline"]["count"] == 1 else "are"), ""]
    if v["headline"]["packages"]:
        L += ["| package | ecosystem | pinned | last release | publishers | reached by |",
              "|---|---|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            p["name"], p["ecosystem"], p["version"] or "?", p["last_release"] or "unknown",
            "unknown" if p["maintainers"] is None else p["maintainers"], p["why"])
            for p in v["headline"]["packages"]]
        L += [""]

    if v["worst"]:
        L += ["## Every input to every grade", "",
              "A grade with its arithmetic shown, so you can disagree with the weighting.", ""]
        for p in v["worst"]:
            L += ["### {0} {1} — grade {2} ({3} of {4} points)".format(
                p["display"], p["version"], p["grade"], p["points"], p["max_points"]), "",
                "| input | points | of | reading | how it is scored |", "|---|---|---|---|---|"]
            L += ["| {0} | {1} | {2} | {3} | {4} |".format(
                s["signal"], s["points"], s["max"], s["value"], s["why"]) for s in p["signals"]]
            L += ["| **total** | **{0}** | **{1}** | grade {2} | A 0-1 · B 2-3 · C 4-6 · D 7-9 · "
                  "F 10+ |".format(p["points"], p["max_points"], p["grade"]), "",
                  "Blast radius: **{0}** — {1}. Seen in {2}.".format(
                      p["blast"]["radius"], p["blast"]["why"], ", ".join(p["lockfiles"]) or "?"), ""]
            if p["unknown_inputs"]:
                L += ["Unknown inputs (scored zero, not scored well): {0}.".format(
                    ", ".join(p["unknown_inputs"])), ""]

    L += ["## Replacements", ""]
    if v["replacements"]:
        L += ["| package | successor | where it came from | the publisher's own words |",
              "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(r["name"], r["successor"], r["source"],
                                                 r["message"] or "—") for r in v["replacements"]]
    else:
        L += ["No registry named a successor for anything here."]
    L += ["", "Replacement hints have exactly one source: the registry's own successor field. "
          "{0} deprecated packages named no successor, and this report does not guess one for "
          "them.".format(len(v["deprecated_without_successor"])), ""]

    L += ["## Lockfiles read", "",
          "| file | format | packages | direct | how direct was decided |", "|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} | {4} |".format(r["lockfile"], r["format"], r["packages"],
                                                   r["direct"], r["direct_basis"])
          for r in v["lockfiles"]]

    if v["licence_changes"]:
        L += ["", "## Licence changes since the version you pin", "",
              "| package | pinned | was | now |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(r["name"], r["pinned_version"], r["from"], r["to"])
              for r in v["licence_changes"]]

    if v["unpriced"]["count"]:
        L += ["", "## Inventoried, never looked up", "",
              "{0} of {1} packages are in an ecosystem this Play cannot query ({2}). They are "
              "counted and named; nothing is claimed about them.".format(
                  v["unpriced"]["count"], t["packages"],
                  ", ".join(v["unpriced"]["ecosystems"]) or "unknown"), "",
              "| package | ecosystem | pinned | seen in |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(p["name"], p["ecosystem"], p["version"] or "?",
                                                 ", ".join(p["lockfiles"]))
              for p in v["unpriced"]["packages"][:40]]

    L += ["", "## Movement", "", "{0}: {1}.".format(v["since"], _delta_line(v["delta"])), "",
          "## Notes", ""]
    L += ["- {0}".format(note) for note in v["notes"]]
    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "")
          for s in sources]
    L += ["", "Read-only. Lockfiles and manifests were read from the disk; the registry half came "
          "from a JSON file another step wrote. This module opens no socket, and "
          "`tests/test_daily_safety.py` proves it.", ""]
    return "\n".join(L)
