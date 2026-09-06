#!/usr/bin/env python3
"""upstream-pulse's network half: ask the public registries about the packages you already pin.

`daily_core` is proven network-free by `tests/test_daily_safety.py`, which refuses a `urllib`,
`http`, `socket` or `ssl` import anywhere in the package. That proof is the most valuable thing
these Plays claim, so the registry lookups live out here instead, in one short file that a reader
can hold in their head -- the same arrangement `leaderboard/post_score.py` uses for comped.

Read this, because it is the whole of what leaves the machine:

    Sent: a package name and its ecosystem, to that ecosystem's own public registry, over HTTPS,
          one GET per package. Nothing else. No path, no lockfile, no version of yours, no
          hostname, no identifier, no account -- these registries need no key and are given none.
    Kept: `<out_dir>/upstream-registry.json`, exactly the schema documented at the top of
          `daily_core/scan/upstream.py`, plus a copy of the answers used as a cache.

    --demo true      writes nothing and opens no connection; the report reads the bundled fixture.
    offline/refused  every lookup is recorded with its `error` and the step still exits 0. A
                     package that could not be looked up is reported as "not checked", never as
                     healthy, which is the whole reason the field exists.

The package list comes from `<out_dir>/.upstreamread-lockfiles.json`, which the Play's
`read_lockfiles` step wrote from lockfiles already on this disk. If that file is missing this step
says so and exits 0.
"""
import argparse
import json
import os
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA = 1
PARTIAL = "upstream-registry.json"
LOCKFILE_PARTIAL = ".upstreamread-lockfiles.json"
CACHE = ".upstream-registry-cache.json"
USER_AGENT = "upstream-pulse/0.1.0 (+https://play.modiqo.ai/rajkaria/upstream-pulse)"
SOURCE = "registry.npmjs.org, pypi.org, crates.io"
# macOS and most Linux distributions keep a CA bundle here; a python.org build on a Mac that never
# ran "Install Certificates.command" has none of its own and every HTTPS call fails until pointed
# at one. A missing bundle is not fatal: it becomes a per-package `error` and an honest "unchecked".
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
              "/etc/pki/tls/certs/ca-bundle.crt")
ECOSYSTEMS = ("npm", "pypi", "crates")


def _bool(s) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def _out(text: str, doc: dict) -> int:
    if text:
        print(text)
    print(json.dumps(doc, sort_keys=True))
    return 0


def _context():
    try:
        return ssl.create_default_context()
    except Exception:                                            # pragma: no cover - exotic build
        return None


def _bundle_context():
    for path in CA_BUNDLES:
        if os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:                                    # pragma: no cover - unreadable
                continue
    return None


def get_json(url: str, timeout: float, context) -> tuple:
    """(document, error). Never raises: an unreachable registry is data, not a crash."""
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read(8 * 1024 * 1024)
    except HTTPError as exc:
        return None, "HTTP {0}".format(exc.code)
    except (URLError, OSError, ValueError) as exc:
        return None, str(getattr(exc, "reason", exc))[:120]
    try:
        return json.loads(raw.decode("utf-8", "replace")), ""
    except ValueError:
        return None, "the registry did not return JSON"


# ---------------------------------------------------------------- per-registry normalisation
#
# Each of these turns one registry's own document into the entry shape documented in
# daily_core/scan/upstream.py. Anything the registry does not say is left out rather than
# guessed at, because an absent field there means "unknown" and a zero would mean "none".

def _npm(name: str, doc: dict) -> dict:
    times = doc.get("time") or {}
    versions = [v for v in times if v not in ("created", "modified")]
    dates = sorted(str(times[v]) for v in versions if times.get(v))
    latest = ((doc.get("dist-tags") or {}).get("latest") or "")
    deprecated = ""
    if latest:
        deprecated = str(((doc.get("versions") or {}).get(latest) or {}).get("deprecated") or "")
    entry = {"latest_version": latest,
             "maintainer_count": len(doc.get("maintainers") or []),
             "deprecated": bool(deprecated),
             "deprecation_message": deprecated,
             "license": str(doc.get("license") or "")}
    if dates:
        entry["last_release_date"] = dates[-1]
        entry["release_dates"] = dates[-12:]
    repo = doc.get("repository")
    if isinstance(repo, dict) and repo.get("archived"):
        entry["repository_archived"] = True
    return entry


def _pypi(name: str, doc: dict) -> dict:
    info = doc.get("info") or {}
    releases = doc.get("releases") or {}
    dates = []
    for files in releases.values():
        for f in files or []:
            if f.get("upload_time_iso_8601"):
                dates.append(str(f["upload_time_iso_8601"]))
                break
    dates.sort()
    entry = {"latest_version": str(info.get("version") or ""),
             "license": str(info.get("license") or ""),
             "deprecated": False,
             "deprecation_message": ""}
    # PyPI publishes no maintainer count, so this stays unknown rather than becoming a 1.
    if dates:
        entry["last_release_date"] = dates[-1]
        entry["release_dates"] = dates[-12:]
    classifiers = [str(c) for c in (info.get("classifiers") or [])]
    if any(c.startswith("Development Status :: 7") for c in classifiers):
        entry["deprecated"] = True
        entry["deprecation_message"] = "Development Status :: 7 - Inactive"
    return entry


def _crates(name: str, doc: dict) -> dict:
    crate = doc.get("crate") or {}
    versions = doc.get("versions") or []
    dates = sorted(str(v.get("created_at")) for v in versions if v.get("created_at"))
    newest = versions[0] if versions else {}
    entry = {"latest_version": str(crate.get("max_stable_version")
                                   or crate.get("newest_version") or ""),
             "license": str(newest.get("license") or ""),
             "deprecated": bool(newest.get("yanked")),
             "deprecation_message": "the newest published version is yanked"
                                    if newest.get("yanked") else ""}
    if dates:
        entry["last_release_date"] = dates[-1]
        entry["release_dates"] = dates[-12:]
    return entry


READERS = {
    "npm": ("https://registry.npmjs.org/{0}", _npm),
    "pypi": ("https://pypi.org/pypi/{0}/json", _pypi),
    "crates": ("https://crates.io/api/v1/crates/{0}", _crates),
}


def wanted(records: list, ecosystems: tuple, limit: int) -> list:
    """(ecosystem, name, pinned_version) for every package worth a lookup, direct ones first.

    A registry answer costs a request, so the bound spends it where it is worth most: a direct
    production dependency you chose is asked about before a transitive one you inherited.
    """
    seen, rows = set(), []
    for record in records:
        eco = str(record.get("ecosystem") or "")
        name = str(record.get("name") or "").strip()
        if eco not in ecosystems or not name or record.get("local"):
            continue
        key = (eco, name.lower())
        if key in seen:
            continue
        seen.add(key)
        rank = (0 if record.get("direct") else 1,
                0 if record.get("scope") != "development" else 1, eco, name.lower())
        rows.append((rank, eco, name, str(record.get("version") or "")))
    rows.sort(key=lambda r: r[0])
    return [(eco, name, version) for _rank, eco, name, version in rows[:limit]]


def load_cache(path: str, hours: float) -> dict:
    """Answers from a recent run, keyed "<ecosystem>/<name>". A stale or unreadable cache is {}."""
    try:
        doc = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return {}
    if time.time() - float(doc.get("stamp") or 0) > max(0.0, hours) * 3600.0:
        return {}
    entries = doc.get("entries")
    return entries if isinstance(entries, dict) else {}


def build_parser():
    """The step's command line, built where a test can reach it without running anything."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out-dir", default="~/daily")
    p.add_argument("--demo", default="false")
    p.add_argument("--max-packages", default="120")
    p.add_argument("--cache-hours", default="24")
    p.add_argument("--timeout", default="10")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)

    out_dir = os.path.expanduser(str(a.out_dir))
    if _bool(a.demo):
        return _out("demo run: nothing was fetched and no connection was opened; the report "
                    "reads the bundled registry fixture.",
                    {"ok": True, "available": False, "demo": True, "requested": 0, "checked": 0,
                     "warning": "demo run: the bundled registry fixture is used"})

    source = os.path.join(out_dir, LOCKFILE_PARTIAL)
    try:
        inventory = json.loads(open(source, encoding="utf-8").read())
    except (OSError, ValueError):
        return _out("no lockfile inventory at {0}; the read_lockfiles step has not run, so there "
                    "is nothing to look up.".format(source),
                    {"ok": True, "available": False, "requested": 0, "checked": 0,
                     "warning": "the lockfile step wrote no inventory; nothing was looked up"})

    rows = wanted(inventory.get("records") or [], ECOSYSTEMS, max(0, int(a.max_packages)))
    cache_path = os.path.join(out_dir, CACHE)
    cached = load_cache(cache_path, float(a.cache_hours))
    context = _context()
    packages, checked, failed, reused = [], 0, 0, 0
    timeout = max(1.0, float(a.timeout))
    tried_bundle = False

    for eco, name, pinned in rows:
        key = "{0}/{1}".format(eco, name)
        if key in cached:
            entry = dict(cached[key])
            entry["pinned_version"] = pinned
            packages.append(entry)
            reused += 1
            continue
        url, reader = READERS[eco]
        doc, error = get_json(url.format(name.replace("/", "%2f")), timeout, context)
        if error and not tried_bundle and context is not None:
            # One retry against a system CA bundle, for the python builds that ship without one.
            tried_bundle = True
            fallback = _bundle_context()
            if fallback is not None:
                context = fallback
                doc, error = get_json(url.format(name.replace("/", "%2f")), timeout, context)
        entry = {"name": name, "ecosystem": eco, "pinned_version": pinned, "error": error}
        if doc is not None and not error:
            entry.update(reader(name, doc))
            entry["error"] = ""
            checked += 1
            cached[key] = dict(entry)
        else:
            failed += 1
        packages.append(entry)

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    partial = {"schema": SCHEMA, "cached_at": stamp, "source": SOURCE,
               "requested": len(rows), "packages": packages}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, PARTIAL), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(partial, indent=1, sort_keys=True) + "\n")
    with open(cache_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"schema": SCHEMA, "stamp": time.time(), "entries": cached},
                            indent=1, sort_keys=True) + "\n")

    doc = {"ok": True, "requested": len(rows), "checked": checked, "reused": reused,
           "failed": failed, "written": os.path.join(out_dir, PARTIAL)}
    if failed and not checked:
        doc["available"] = False
        doc["warning"] = ("no registry answered; every package is reported as not checked, "
                          "which is not the same as healthy")
    return _out("{0} package(s) asked about: {1} answered, {2} from cache, {3} failed.".format(
        len(rows), checked, reused, failed), doc)


if __name__ == "__main__":
    sys.exit(main())
