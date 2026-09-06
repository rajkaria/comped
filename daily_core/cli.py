"""One entry point for six Plays. Each Play is a few `read` steps and one `report` step.

A read step handles exactly one source and always exits 0: it writes what it managed to read into
a partial file under out_dir and prints a JSON object saying which sources answered. The report
step merges the partials, computes, renders the card and writes the report. Splitting it this way
is what lets the Play run its reads in parallel and lets a browser, a folder or a database that
cannot be read cost that source alone.
"""
import argparse
import json
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:      # invoked as a file path from a Play step
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "daily_core"

from .common import (Budget, as_bool, baseline_read, baseline_write, emit, envelope, fixtures_dir,
                     now_utc, out_path, state_read, state_write, write_text)

PLAYS = ("tabs", "contacts", "apps", "notes", "clutter", "receipts",
         "busfactor", "nightshift", "kept", "extensions", "history", "photos", "grew",
         "standingcost", "replydebt", "upstream")


# ---------------------------------------------------------------- helpers

def _cfg(a) -> dict:
    return {"now": now_utc(getattr(a, "now", "")), "color": as_bool(getattr(a, "color", "false")),
            "redact": as_bool(getattr(a, "redact", "true")),
            "keep_path": as_bool(getattr(a, "keep_path", "false")),
            "demo": as_bool(getattr(a, "demo", "false")), "out_dir": a.out_dir}


def _demo_root(a, name: str):
    return (fixtures_dir() / name) if as_bool(getattr(a, "demo", "false")) else None


def _partials(out_dir, prefix: str) -> list:
    d = Path(out_dir).expanduser()
    docs = []
    for p in sorted(d.glob(".{0}-*.json".format(prefix))):
        try:
            docs.append(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return docs


def _merge(docs: list, key: str) -> tuple:
    from .common import Source
    sources, items = [], []
    for doc in docs:
        sources += [Source(**s) for s in doc.get("sources", [])]
        items += doc.get(key, [])
    return sources, items


def _no_partials(prefix: str, play: str) -> dict:
    return {"ok": True, "empty": True, "sources": [],
            "warning": "no {0} read step wrote a partial file; run `{1} read` first".format(prefix, play)}


def _finish(cfg, name: str, view: dict, sources, card: str, markdown: str, summary: dict) -> int:
    written = [write_text(cfg["out_dir"], "{0}.md".format(name), markdown),
               write_text(cfg["out_dir"], "{0}.json".format(name),
                          json.dumps({"generated": cfg["now"].isoformat(), "view": view,
                                      "sources": [s if isinstance(s, dict) else s.__dict__ for s in sources]},
                                     default=str, indent=1, sort_keys=True) + "\n")]
    doc = dict(summary)
    doc["written"] = written
    from dataclasses import asdict, is_dataclass
    doc["sources"] = [asdict(s) if is_dataclass(s) else s for s in sources]
    lines = [card, "", "wrote {0}".format(written[0])]
    absent = [s for s in doc["sources"] if not s.get("found")]
    if absent:
        lines.append("not read: " + "; ".join(
            "{0}{1}".format(s["name"], " ({0})".format(s["note"]) if s.get("note") else "") for s in absent))
        doc.setdefault("note", "not read: " + "; ".join(s["name"] for s in absent))
    if not any(s.get("found") for s in doc["sources"]):
        doc["empty"] = True
        doc.setdefault("warning", "no source could be read")
    doc["ok"] = True
    return emit("\n".join(lines), doc)


# ---------------------------------------------------------------- tab-debt

def cmd_tabs_read(a) -> int:
    from .scan import tabs
    budget = Budget(max_seconds=float(a.max_seconds))
    sources, found = tabs.read_source(a.source, budget, _demo_root(a, "tabs"))
    for t in found:
        t.pop("_when", None)
    doc = {"sources": [s.__dict__ for s in sources], "tabs": found}
    state_write(a.out_dir, "tabs-{0}".format(a.source), doc)
    return emit("{0}: {1} tab(s) from {2} source(s)".format(a.source, len(found), sum(1 for s in sources if s.found)),
                envelope(sources, budget, {"tabs": len(found), "family": a.source}))


def cmd_tabs_report(a) -> int:
    from .scan import tabs
    cfg = _cfg(a)
    docs = _partials(a.out_dir, "tabs")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("tabs", "tabs"))
    sources, found = _merge(docs, "tabs")
    rl_source, items = tabs.reading_list(_demo_root(a, "tabs"))
    if rl_source.found or as_bool(a.demo):
        sources.append(rl_source)
    view = tabs.analyse(found, items, cfg["now"], cfg["keep_path"])
    card = tabs.render(view, cfg)
    md = tabs.report_markdown(view, cfg, [s.__dict__ for s in sources])
    summary = {"tabs": view["total"], "windows": view["windows"], "cold": view["cold"],
               "duplicates": view["duplicate_tabs"],
               "oldest_days": (view["oldest"] or {}).get("age_days"),
               "browsers": len(view["browsers"]), "verdict": view["verdict"]}
    return _finish(cfg, "tab-debt", view, sources, card, md, summary)


# ---------------------------------------------------------------- birthday-radar

def cmd_contacts_read(a) -> int:
    from .scan import contacts
    budget = Budget(max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_root(a, "contacts"), "vcard_dir": a.vcard_dir, "csv_path": a.csv_path}
    sources, people = contacts.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "contacts-{0}".format(a.source), {"sources": [s.__dict__ for s in sources],
                                                             "people": people})
    return emit("{0}: {1} contact(s)".format(a.source, len(people)),
                envelope(sources, budget, {"people": len(people), "source": a.source}))


def cmd_contacts_report(a) -> int:
    from .scan import contacts
    cfg = _cfg(a)
    docs = _partials(a.out_dir, "contacts")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("contacts", "contacts"))
    sources, people = _merge(docs, "people")
    view = contacts.analyse(people, cfg["now"], int(a.horizon), cfg["redact"])
    summary = {"contacts": view["people"], "with_birthday": view["with_birthday"],
               "upcoming": view["upcoming_total"], "today": len(view["today"]),
               "next_in_days": (view["next"] or {}).get("in_days"),
               "missing": view["missing"], "duplicates": view["duplicate_total"]}
    return _finish(cfg, "birthday-radar", view, sources, contacts.render(view, cfg),
                   contacts.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- app-graveyard

def cmd_apps_read(a) -> int:
    from .scan import apps
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_root(a, "apps"),
           "app_dirs": [d for d in (a.app_dirs or "").split(",") if d.strip()] or None}
    sources, items = apps.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "apps-{0}".format(a.source),
                {"sources": [s.__dict__ for s in sources], a.source: items})
    return emit("{0}: {1} item(s)".format(a.source, len(items)),
                envelope(sources, budget, {a.source: len(items)}))


def cmd_apps_report(a) -> int:
    from .scan import apps
    cfg = _cfg(a)
    docs = _partials(a.out_dir, "apps")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("apps", "apps"))
    sources, found = _merge(docs, "applications")
    _, casks = _merge(docs, "casks")
    view = apps.analyse(found, casks, cfg["now"], int(a.unused_days))
    summary = {"apps": view["apps"], "bytes": view["bytes"], "unused": view["unused"],
               "never_used": view["never_used"], "reclaimable": view["reclaimable"],
               "intel_only": view["intel_only_total"], "casks": view["casks"]}
    return _finish(cfg, "app-graveyard", view, sources, apps.render(view, cfg),
                   apps.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- vault-pulse

def cmd_notes_read(a) -> int:
    from .scan import notes
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    sources, docs = notes.read_source("vault", budget, {"demo_root": _demo_root(a, "notes"), "vault": a.vault})
    state_write(a.out_dir, "notes-vault", {"sources": [s.__dict__ for s in sources], "vault": docs})
    return emit("vault: {0} note(s)".format(sum(len(d["notes"]) for d in docs)),
                envelope(sources, budget, {"notes": sum(len(d["notes"]) for d in docs)}))


def cmd_notes_report(a) -> int:
    from .scan import notes
    cfg = _cfg(a)
    docs = _partials(a.out_dir, "notes")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("notes", "notes"))
    sources, vaults = _merge(docs, "vault")
    if not vaults:
        return emit("No vault was read.", {"ok": True, "empty": True,
                                           "sources": [s.__dict__ for s in sources],
                                           "warning": "no notes folder could be read"})
    view = notes.analyse(vaults[0], cfg["now"], int(a.stale_days))
    summary = {"notes": view["notes"], "words": view["words"], "orphans": view["orphans"],
               "broken_links": view["broken"], "write_only": view["write_only"],
               "streak": view["daily"]["current"], "todo": view["todo"]}
    return _finish(cfg, "vault-pulse", view, sources, notes.render(view, cfg),
                   notes.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- desktop-clutter

def cmd_clutter_read(a) -> int:
    from .scan import clutter
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_root(a, "clutter"), "desktop_dir": a.desktop_dir, "downloads_dir": a.downloads_dir}
    sources, files = clutter.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "clutter-{0}".format(a.source), {"sources": [s.__dict__ for s in sources],
                                                            "files": files})
    return emit("{0}: {1} file(s)".format(a.source, len(files)),
                envelope(sources, budget, {"files": len(files), "root": a.source}))


def cmd_clutter_report(a) -> int:
    from .scan import clutter
    cfg = _cfg(a)
    docs = _partials(a.out_dir, "clutter")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("clutter", "clutter"))
    sources, files = _merge(docs, "files")
    roots = {s.name: s.path for s in sources}
    view = clutter.analyse(files, cfg["now"], int(a.cold_days), as_bool(a.hash_duplicates), roots)
    summary = {"files": view["files"], "bytes": view["bytes"], "cold": view["cold"],
               "screenshots": view["screenshots"], "duplicates": view["duplicate_total"],
               "reclaimable": view["reclaimable"], "grade": view["score"]["grade"]}
    return _finish(cfg, "desktop-clutter", view, sources, clutter.render(view, cfg),
                   clutter.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- receipt-ledger

def cmd_receipts_read(a) -> int:
    from .scan import receipts
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_root(a, "receipts"),
           "receipts_dir": a.receipts_dir if a.source == "files" else a.mail_dir}
    sources, docs = receipts.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "receipts-{0}".format(a.source), {"sources": [s.__dict__ for s in sources],
                                                             "docs": docs})
    return emit("{0}: {1} receipt-shaped document(s)".format(a.source, len(docs)),
                envelope(sources, budget, {"documents": len(docs), "source": a.source}))


def cmd_receipts_report(a) -> int:
    from .scan import receipts
    cfg = _cfg(a)
    partials = _partials(a.out_dir, "receipts")
    if not partials:
        return emit("Nothing to report yet.", _no_partials("receipts", "receipts"))
    sources, docs = _merge(partials, "docs")
    view = receipts.analyse(docs, cfg["now"], int(a.months_back))
    summary = {"documents": view["documents"], "priced": view["priced"], "in_window": view["in_window"],
               "currencies": view["currencies"], "vendors": view["vendor_total"],
               "recurring": view["recurring_total"], "duplicates": view["duplicate_total"]}
    return _finish(cfg, "receipt-ledger", view, sources, receipts.render(view, cfg),
                   receipts.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ================================================================ the ten pulse Plays
#
# Same two-step shape as the six above and nothing new in it: one `*-read` verb per source, which
# writes a partial and always exits 0, and one `*-report` verb, which merges the partials, calls
# the module's `analyse`, renders the card and writes the report.
#
# Three of these Plays -- standing-cost, reply-debt and upstream-pulse's registry half -- read a
# JSON partial that the Play's TypeScript step left behind rather than reading this machine. Their
# read verbs locate and validate that file and fetch nothing at all; a missing file is a labelled
# miss, never an error.


def _demo_dir(a, name: str):
    """This Play's demo fixture folder: the bundled one, or the one the caller named instead.

    Kept separate from `_demo_root` so the six older Plays keep exactly the behaviour they have.
    `--demo-root` is a real cfg key of eight of these ten modules, so it is a real flag here.
    """
    if not as_bool(getattr(a, "demo", "false")):
        return None
    given = str(getattr(a, "demo_root", "") or "").strip()
    return given or (fixtures_dir() / name)


def _slug(value) -> str:
    """A partial-file token for a source that may be a repository path: no separators, never empty."""
    text = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(value or ""))
    return text.strip("-")[:60] or "source"


def _csv(value) -> list:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _plus(a, **extra) -> dict:
    cfg = _cfg(a)
    cfg.update(extra)
    return cfg


# ---------------------------------------------------------------- bus-factor

def cmd_busfactor_read(a) -> int:
    from .scan import busfactor
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "busfactor"), "root": a.root,
           "max_repos": int(a.max_repos), "timeout": float(a.timeout)}
    sources, records = busfactor.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "busfactor-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "records": records})
    return emit("{0}: {1} tracked file(s) from {2} readable repositor(y/ies)".format(
        a.source, len(records), sum(1 for s in sources if s.found)),
        envelope(sources, budget, {"records": len(records), "source": a.source}))


def cmd_busfactor_report(a) -> int:
    from .scan import busfactor
    cfg = _plus(a, departed_days=int(a.departed_days), stale_days=int(a.stale_days),
                threshold=float(a.threshold))
    docs = _partials(a.out_dir, "busfactor")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("busfactor", "busfactor"))
    sources, records = _merge(docs, "records")
    view = busfactor.analyse(records, cfg["now"], cfg)
    busfactor.save_baseline(view, cfg, cfg["now"])
    summary = {"repos": view["repo_count"], "tracked_files": view["tracked_files"],
               "tracked_lines": view["tracked_lines"], "sole_files": view["sole_files"],
               "authors": view["author_count"], "truck_factor": view["truck_factor"]["n"],
               "stale_sole_files": view["stale_sole_files"], "verdict": view["verdict"]}
    return _finish(cfg, "bus-factor", view, sources, busfactor.render(view, cfg),
                   busfactor.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- night-shift

def cmd_nightshift_read(a) -> int:
    from .scan import nightshift
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "nightshift"), "root": a.root, "days": int(a.days),
           "emails": _csv(a.emails), "now": a.now}
    sources, records = nightshift.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "nightshift-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "commits": records})
    return emit("{0}: {1} commit(s), {2} of them yours".format(
        a.source, len(records), sum(1 for r in records if r.get("mine"))),
        envelope(sources, budget, {"commits": len(records), "kind": a.source}))


def cmd_nightshift_report(a) -> int:
    from .scan import nightshift
    cfg = _plus(a, days=int(a.days), late_hour=int(a.late_hour), dawn_hour=int(a.dawn_hour),
                fixup_minutes=int(a.fixup_minutes), aftermath_hours=int(a.aftermath_hours))
    docs = _partials(a.out_dir, "nightshift")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("nightshift", "nightshift"))
    sources, records = _merge(docs, "commits")
    view = nightshift.analyse(records, cfg["now"], cfg)
    nightshift.save_baseline(view, cfg, cfg["now"])
    summary = dict(view["snapshot"])
    summary["days"] = view["days"]
    return _finish(cfg, "night-shift", view, sources, nightshift.render(view, cfg),
                   nightshift.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- kept

def cmd_kept_read(a) -> int:
    from .scan import kept
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "kept"), "root": a.root, "max_repos": int(a.max_repos),
           "claude_dir": a.claude_dir, "codex_dir": a.codex_dir, "pi_dir": a.pi_dir}
    sources, records = kept.read_source(a.source, budget, cfg)
    # The partial prefix is deliberately not "kept": `_partials(out_dir, "kept")` would glob
    # `.kept-*.json` and swallow this Play's own `.kept-baseline.json`.
    state_write(a.out_dir, "keptread-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "records": records})
    return emit("{0}: {1} record(s)".format(a.source, len(records)),
                envelope(sources, budget, {"records": len(records), "source": a.source}))


def cmd_kept_report(a) -> int:
    from .scan import kept
    cfg = _plus(a, demo_root=_demo_dir(a, "kept"), grace_minutes=int(a.grace_minutes),
                min_lines=int(a.min_lines), max_blame_files=int(a.max_blame_files),
                max_commits=int(a.max_commits), max_seconds=float(a.max_seconds))
    docs = _partials(a.out_dir, "keptread")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("keptread", "kept"))
    sources, records = _merge(docs, "records")
    view = kept.analyse(records, cfg["now"], cfg)
    kept.save_baseline(view, cfg, cfg["now"])
    summary = {"agent_ever": view["totals"]["ever"]["agent"],
               "agent_alive": view["totals"]["alive"]["agent"],
               "human_ever": view["totals"]["ever"]["human"],
               "human_alive": view["totals"]["alive"]["human"],
               "survival": view["survival"]["agent"], "sessions": view["sessions"]["count"],
               "repos": len(view["repos"])}
    return _finish(cfg, "kept", view, sources, kept.render(view, cfg),
                   kept.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- extension-reach

def cmd_extensions_read(a) -> int:
    from .scan import extensions
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "extensions"), "roots": _csv(a.roots) or None,
           "safari_roots": _csv(a.safari_roots) or None}
    sources, records = extensions.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "extensions-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "installs": records})
    return emit("{0}: {1} install(s) from {2} source(s)".format(
        a.source, len(records), sum(1 for s in sources if s.found)),
        envelope(sources, budget, {"installs": len(records), "family": a.source}))


def cmd_extensions_report(a) -> int:
    from .scan import extensions
    cfg = _plus(a, stale_days=int(a.stale_days), idle_days=int(a.idle_days))
    docs = _partials(a.out_dir, "extensions")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("extensions", "extensions"))
    sources, records = _merge(docs, "installs")
    view = extensions.analyse(records, cfg["now"], cfg)
    extensions.write_baseline(cfg["out_dir"], view, cfg["now"])
    summary = {"extensions": view["extensions"], "installs": view["installs"],
               "browsers": len(view["browsers"]), "all_urls": view["all_urls"],
               "blanket": view["blanket"], "stale": view["stale"]["count"],
               "verdict": view["verdict"]}
    return _finish(cfg, "extension-reach", view, sources, extensions.render(view, cfg),
                   extensions.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- where-it-went

def cmd_history_read(a) -> int:
    from .scan import history
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "history"), "days": int(a.days), "now": now_utc(a.now)}
    sources, records = history.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "history-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "visits": records})
    return emit("{0}: {1} visit(s) from {2} profile(s)".format(
        a.source, len(records), sum(1 for s in sources if s.found)),
        envelope(sources, budget, {"visits": len(records), "family": a.source}))


def cmd_history_report(a) -> int:
    from .scan import history
    cfg = _plus(a, days=int(a.days), gap_minutes=int(a.gap_minutes), top=int(a.top), tz=a.tz)
    docs = _partials(a.out_dir, "history")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("history", "history"))
    sources, records = _merge(docs, "visits")
    # This module writes no baseline of its own, so the caller reads one in and writes one back.
    cfg["baseline"] = baseline_read(cfg["out_dir"], "where-it-went")
    view = history.analyse(records, cfg["now"], cfg)
    baseline_write(cfg["out_dir"], "where-it-went", history.baseline_payload(view), cfg["now"])
    summary = {"visits": view["visits"], "days": view["days"], "domains": view["domain_total"],
               "unique_urls": view["unique_urls"], "categories": len(view["categories"]),
               "verdict": view["verdict"]}
    return _finish(cfg, "where-it-went", view, sources, history.render(view, cfg),
                   history.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- photo-debt

def cmd_photos_read(a) -> int:
    from .scan import photos
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "photos"), "library": a.library, "root": a.root}
    sources, records = photos.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "photos-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "assets": records})
    return emit("{0}: {1} asset(s)".format(a.source, len(records)),
                envelope(sources, budget, {"assets": len(records), "source": a.source}))


def cmd_photos_report(a) -> int:
    from .scan import photos
    cfg = _plus(a, burst_window=int(a.burst_window), screenshot_days=int(a.screenshot_days),
                top=int(a.top), hash_dupes=as_bool(a.hash_dupes))
    docs = _partials(a.out_dir, "photos")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("photos", "photos"))
    sources, records = _merge(docs, "assets")
    cfg["baseline"] = baseline_read(cfg["out_dir"], "photo-debt")
    view = photos.analyse(records, cfg["now"], cfg)
    baseline_write(cfg["out_dir"], "photo-debt", view["baseline"], cfg["now"])
    return _finish(cfg, "photo-debt", view, sources, photos.render(view, cfg),
                   photos.report_markdown(view, cfg, [s.__dict__ for s in sources]),
                   dict(view["baseline"]))


# ---------------------------------------------------------------- what-grew

def cmd_grew_read(a) -> int:
    from .scan import grew
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "grew"), "root": a.root, "depth": int(a.depth),
           "floor_bytes": int(a.floor_bytes)}
    sources, snapshot = grew.read_source(a.source, budget, cfg)
    # Not "grew" and not "whatgrew": this Play keeps `.whatgrew-baseline.json` and
    # `.whatgrew-history-baseline.json` under the same out_dir, and a partial glob that matched
    # either of them would feed a baseline back in as if it were a fresh reading of the disk.
    state_write(a.out_dir, "grewsnap-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "snapshot": [snapshot]})
    return emit("{0}: {1} folder(s), {2} file(s)".format(
        a.source, len(snapshot.get("dirs") or {}), snapshot.get("files", 0)),
        envelope(sources, budget, {"folders": len(snapshot.get("dirs") or {}),
                                   "files": snapshot.get("files", 0), "root": a.source}))


def cmd_grew_report(a) -> int:
    from .scan import grew
    cfg = _plus(a, since=a.since, keep_baselines=int(a.keep_baselines),
                write_baseline=as_bool(a.write_baseline))
    docs = _partials(a.out_dir, "grewsnap")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("grewsnap", "grew"))
    sources, snapshots = _merge(docs, "snapshot")
    # `analyse` compares against the retained baselines and then retains this one itself: the
    # comparison and the recording are one decision, so nothing here writes a second baseline.
    view = grew.analyse(snapshots[0] if snapshots else {}, cfg["now"], cfg)
    summary = {"total_bytes": view["total_bytes"], "reclaim_bytes": view["reclaim_bytes"],
               "dirs_named": view["dirs_named"], "files": view["files"],
               "free_bytes": view["free_bytes"], "net_bytes": view["net_bytes"],
               "first_run": view["first_run"], "baselines_held": len(view["baselines"])}
    return _finish(cfg, "what-grew", view, sources, grew.render(view, cfg),
                   grew.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- standing-cost

def _standingcost_cfg(a) -> dict:
    return {"demo_root": _demo_dir(a, "standingcost"), "partial": a.partial, "out_dir": a.out_dir}


def cmd_standingcost_read(a) -> int:
    from .scan import standingcost
    budget = Budget(max_seconds=float(a.max_seconds))
    sources, events = standingcost.read_source(a.source, budget, _standingcost_cfg(a))
    # A normalized event carries datetimes and a `_normalized` flag, so it cannot survive a JSON
    # partial and come back out the same shape. This step's job is to say whether the calendar
    # step left a readable file behind; the report reads that same file for the events themselves.
    state_write(a.out_dir, "standingcost-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources],
                 "located": [{"source": a.source, "partial": a.partial, "events": len(events)}]})
    return emit("{0}: {1} event(s) in the partial".format(a.source, len(events)),
                envelope(sources, budget, {"events": len(events), "source": a.source}))


def cmd_standingcost_report(a) -> int:
    from .scan import standingcost
    cfg = _plus(a, days=int(a.days), focus_block_minutes=int(a.focus_block_minutes),
                currency=a.currency, hourly_rate=a.hourly_rate)
    cfg["self"] = a.owner
    docs = _partials(a.out_dir, "standingcost")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("standingcost", "standingcost"))
    sources, events = standingcost.read_source(
        a.source, Budget(max_seconds=float(a.max_seconds)), _standingcost_cfg(a))
    view = standingcost.analyse(events, cfg["now"], cfg)
    standingcost.save_baseline(view, cfg, cfg["now"])
    summary = {"events_read": view["events_read"], "occurrences": view["occurrences"],
               "cancelled": view["cancelled_occurrences"], "series": view["series_total"],
               "people": view["people_total"], "person_hours": view["person_hours"],
               "recurring_person_hours": view["recurring_person_hours"],
               "silent_person_hours": view["silent_person_hours"],
               "rate_set": view["rate"]["set"]}
    return _finish(cfg, "standing-cost", view, sources, standingcost.render(view, cfg),
                   standingcost.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- reply-debt

def cmd_replydebt_read(a) -> int:
    from .scan import replydebt
    budget = Budget(max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "replydebt"), "partial": a.partial}
    sources, threads = replydebt.read_source(a.source, budget, cfg)
    state_write(a.out_dir, "replydebt-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "threads": threads})
    return emit("{0}: {1} thread(s)".format(a.source, len(threads)),
                envelope(sources, budget, {"threads": len(threads), "source": a.source}))


def cmd_replydebt_report(a) -> int:
    from .scan import replydebt
    cfg = _plus(a, min_age_days=int(a.min_age_days), cold_days=int(a.cold_days), me=_csv(a.me))
    docs = _partials(a.out_dir, "replydebt")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("replydebt", "replydebt"))
    sources, threads = _merge(docs, "threads")
    view = replydebt.analyse(threads, cfg["now"], cfg)
    replydebt.write_baseline(view, cfg)
    summary = {"threads_seen": view["threads_seen"], "considered": view["considered"],
               "debt": view["debt"], "direct": view["direct"], "implied": view["implied"],
               "fyi": view["fyi"], "cold": view["cold"], "excluded": view["excluded"]}
    return _finish(cfg, "reply-debt", view, sources, replydebt.render(view, cfg),
                   replydebt.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- upstream-pulse

def cmd_upstream_read(a) -> int:
    from .scan import upstream
    budget = Budget(max_files=int(a.max_files), max_seconds=float(a.max_seconds))
    cfg = {"demo_root": _demo_dir(a, "upstream"), "root": a.root,
           "registry_partial": a.registry_partial, "out_dir": a.out_dir}
    sources, records = upstream.read_source(a.source, budget, cfg)
    # Not "upstream": `.upstream-*` would glob this Play's own `.upstream-pulse-baseline.json`,
    # and the registry step's `upstream-registry.json` sits in the same folder besides.
    state_write(a.out_dir, "upstreamread-{0}".format(_slug(a.source)),
                {"sources": [s.__dict__ for s in sources], "records": records})
    return emit("{0}: {1} record(s)".format(a.source, len(records)),
                envelope(sources, budget, {"records": len(records), "kind": a.source}))


def cmd_upstream_report(a) -> int:
    from .scan import upstream
    cfg = _plus(a, demo_root=_demo_dir(a, "upstream"), root=a.root, depth=int(a.depth),
                dormant_days=int(a.dormant_days), cache_hours=float(a.cache_hours))
    docs = _partials(a.out_dir, "upstreamread")
    if not docs:
        return emit("Nothing to report yet.", _no_partials("upstreamread", "upstream"))
    sources, records = _merge(docs, "records")
    view = upstream.analyse(records, cfg["now"], cfg)
    upstream.save_baseline(view, cfg, cfg["now"])
    summary = {"packages": view["totals"]["packages"], "direct": view["totals"]["direct"],
               "lockfiles": view["totals"]["lockfiles"], "checked": view["checks"]["checked"],
               "unchecked": view["network"]["unchecked"], "offline": view["network"]["offline"],
               "dormant": view["dormant"]["count"],
               "single_maintainer": view["single_maintainer"]["count"],
               "deprecated": view["deprecated"]["count"], "headline": view["headline"]["count"]}
    return _finish(cfg, "upstream-pulse", view, sources, upstream.render(view, cfg),
                   upstream.report_markdown(view, cfg, [s.__dict__ for s in sources]), summary)


# ---------------------------------------------------------------- parser

def build_parser():
    p = argparse.ArgumentParser(prog="daily_core", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--out-dir", default="~/daily")
        sp.add_argument("--now", default="")
        sp.add_argument("--demo", default="false")
        return sp

    def view_args(sp):
        sp.add_argument("--color", default="false")
        sp.add_argument("--redact", default="true")
        sp.add_argument("--keep-path", default="false")
        return sp

    sp = common(sub.add_parser("tabs-read", help="read one browser family's open tabs"))
    sp.add_argument("--source", required=True, choices=list(__import__("daily_core.scan.tabs",
                                                                       fromlist=["FAMILIES"]).FAMILIES))
    sp.add_argument("--max-seconds", default="20")
    sp.set_defaults(fn=cmd_tabs_read)

    sp = view_args(common(sub.add_parser("tabs-report", help="merge, count and render the tab card")))
    sp.set_defaults(fn=cmd_tabs_report)

    sp = common(sub.add_parser("contacts-read", help="read one address-book source"))
    sp.add_argument("--source", required=True, choices=["addressbook", "vcard", "csv"])
    sp.add_argument("--vcard-dir", default="~/Documents")
    sp.add_argument("--csv-path", default="")
    sp.add_argument("--max-seconds", default="20")
    sp.set_defaults(fn=cmd_contacts_read)

    sp = view_args(common(sub.add_parser("contacts-report", help="sort the birthdays and render the card")))
    sp.add_argument("--horizon", default="45")
    sp.set_defaults(fn=cmd_contacts_report)

    sp = common(sub.add_parser("apps-read", help="read installed applications or Homebrew casks"))
    sp.add_argument("--source", required=True, choices=["applications", "casks"])
    sp.add_argument("--app-dirs", default="")
    sp.add_argument("--max-files", default="400000")
    sp.add_argument("--max-seconds", default="90")
    sp.set_defaults(fn=cmd_apps_read)

    sp = view_args(common(sub.add_parser("apps-report", help="age the applications and render the card")))
    sp.add_argument("--unused-days", default="180")
    sp.set_defaults(fn=cmd_apps_report)

    sp = common(sub.add_parser("notes-read", help="read a markdown vault"))
    sp.add_argument("--vault", default="")
    sp.add_argument("--max-files", default="60000")
    sp.add_argument("--max-seconds", default="45")
    sp.set_defaults(fn=cmd_notes_read)

    sp = view_args(common(sub.add_parser("notes-report", help="build the link graph and render the card")))
    sp.add_argument("--stale-days", default="180")
    sp.set_defaults(fn=cmd_notes_report)

    sp = common(sub.add_parser("clutter-read", help="read one cluttered folder"))
    sp.add_argument("--source", required=True, choices=["desktop", "downloads", "screenshots"])
    sp.add_argument("--desktop-dir", default="")
    sp.add_argument("--downloads-dir", default="")
    sp.add_argument("--max-files", default="120000")
    sp.add_argument("--max-seconds", default="45")
    sp.set_defaults(fn=cmd_clutter_read)

    sp = view_args(common(sub.add_parser("clutter-report", help="age, group and grade the clutter")))
    sp.add_argument("--cold-days", default="90")
    sp.add_argument("--hash-duplicates", default="true")
    sp.set_defaults(fn=cmd_clutter_report)

    sp = common(sub.add_parser("receipts-read", help="read receipt-shaped documents from a folder"))
    sp.add_argument("--source", required=True, choices=["files", "mail"])
    sp.add_argument("--receipts-dir", default="~/Downloads")
    sp.add_argument("--mail-dir", default="~/Library/Mail")
    sp.add_argument("--max-files", default="60000")
    sp.add_argument("--max-seconds", default="120")
    sp.set_defaults(fn=cmd_receipts_read)

    sp = view_args(common(sub.add_parser("receipts-report", help="total the receipts per currency")))
    sp.add_argument("--months-back", default="12")
    sp.set_defaults(fn=cmd_receipts_report)

    # ------------------------------------------------------------ the ten pulse Plays

    def pulse(sp):
        """common(), plus the fixture folder these Plays' demo runs read instead of the machine."""
        common(sp)
        sp.add_argument("--demo-root", default="")
        return sp

    def choices_of(module: str, name: str) -> list:
        return list(getattr(__import__("daily_core.scan." + module, fromlist=[name]), name))

    sp = pulse(sub.add_parser("busfactor-read", help="read one repository, or every repo under a root"))
    sp.add_argument("--source", default="git", help='"git" to walk --root, or one repository path')
    sp.add_argument("--root", default="~")
    sp.add_argument("--max-repos", default="40")
    sp.add_argument("--timeout", default="30")
    sp.add_argument("--max-files", default="200000")
    sp.add_argument("--max-seconds", default="90")
    sp.set_defaults(fn=cmd_busfactor_read)

    sp = view_args(pulse(sub.add_parser("busfactor-report", help="attribute the files and render the card")))
    sp.add_argument("--departed-days", default="365")
    sp.add_argument("--stale-days", default="365")
    sp.add_argument("--threshold", default="0.5")
    sp.set_defaults(fn=cmd_busfactor_report)

    sp = pulse(sub.add_parser("nightshift-read", help="read the commit log of every repository under a root"))
    sp.add_argument("--source", default="commits", choices=choices_of("nightshift", "KINDS"))
    sp.add_argument("--root", default="~")
    sp.add_argument("--days", default="90")
    sp.add_argument("--emails", default="", help="extra addresses that mean you, comma separated")
    sp.add_argument("--max-files", default="200000")
    sp.add_argument("--max-seconds", default="90")
    sp.set_defaults(fn=cmd_nightshift_read)

    sp = view_args(pulse(sub.add_parser("nightshift-report", help="count the late commits and render the card")))
    sp.add_argument("--days", default="90")
    sp.add_argument("--late-hour", default="23")
    sp.add_argument("--dawn-hour", default="5")
    sp.add_argument("--fixup-minutes", default="60")
    sp.add_argument("--aftermath-hours", default="12")
    sp.set_defaults(fn=cmd_nightshift_report)

    sp = pulse(sub.add_parser("kept-read", help="read agent transcripts, or the repositories they wrote into"))
    sp.add_argument("--source", required=True, choices=choices_of("kept", "SOURCES"))
    sp.add_argument("--root", default="~")
    sp.add_argument("--max-repos", default="200")
    sp.add_argument("--claude-dir", default="~/.claude/projects")
    sp.add_argument("--codex-dir", default="~/.codex/sessions")
    sp.add_argument("--pi-dir", default="~/.pi/sessions")
    sp.add_argument("--max-files", default="200000")
    sp.add_argument("--max-seconds", default="45")
    sp.set_defaults(fn=cmd_kept_read)

    sp = view_args(pulse(sub.add_parser("kept-report", help="blame the agent's lines and render the card")))
    sp.add_argument("--grace-minutes", default="30")
    sp.add_argument("--min-lines", default="20")
    sp.add_argument("--max-blame-files", default="300")
    sp.add_argument("--max-commits", default="4000")
    sp.add_argument("--max-seconds", default="45")
    sp.set_defaults(fn=cmd_kept_report)

    sp = pulse(sub.add_parser("extensions-read", help="read one browser family's installed extensions"))
    sp.add_argument("--source", required=True, choices=choices_of("extensions", "FAMILIES"))
    sp.add_argument("--roots", default="", help="profile support directories, comma separated")
    sp.add_argument("--safari-roots", default="", help="path prefixes for the Safari stores")
    sp.add_argument("--max-files", default="200000")
    sp.add_argument("--max-seconds", default="45")
    sp.set_defaults(fn=cmd_extensions_read)

    sp = view_args(pulse(sub.add_parser("extensions-report", help="tier the extensions by reach")))
    sp.add_argument("--stale-days", default="365")
    sp.add_argument("--idle-days", default="90")
    sp.set_defaults(fn=cmd_extensions_report)

    sp = pulse(sub.add_parser("history-read", help="read one browser family's visit history"))
    sp.add_argument("--source", required=True, choices=choices_of("history", "FAMILIES"))
    sp.add_argument("--days", default="90")
    sp.add_argument("--max-files", default="200000")
    sp.add_argument("--max-seconds", default="45")
    sp.set_defaults(fn=cmd_history_read)

    sp = view_args(pulse(sub.add_parser("history-report", help="categorise the visits and render the card")))
    sp.add_argument("--days", default="90")
    sp.add_argument("--gap-minutes", default="30")
    sp.add_argument("--top", default="10")
    sp.add_argument("--tz", default="local")
    sp.set_defaults(fn=cmd_history_report)

    sp = pulse(sub.add_parser("photos-read", help="read the Photos library, or a folder of images"))
    sp.add_argument("--source", required=True, choices=choices_of("photos", "KINDS"))
    sp.add_argument("--library", default="~/Pictures/Photos Library.photoslibrary")
    sp.add_argument("--root", default="~/Pictures")
    sp.add_argument("--max-files", default="400000")
    sp.add_argument("--max-seconds", default="120")
    sp.set_defaults(fn=cmd_photos_read)

    sp = view_args(pulse(sub.add_parser("photos-report", help="group the duplicates and render the card")))
    sp.add_argument("--burst-window", default="2")
    sp.add_argument("--screenshot-days", default="90")
    sp.add_argument("--top", default="5")
    sp.add_argument("--hash-dupes", default="true")
    sp.set_defaults(fn=cmd_photos_report)

    sp = pulse(sub.add_parser("grew-read", help="measure a folder tree, rolled up to a depth"))
    sp.add_argument("--source", default="home", choices=choices_of("grew", "KINDS"))
    sp.add_argument("--root", default="~")
    sp.add_argument("--depth", default="4")
    sp.add_argument("--floor-bytes", default=str(16 * 1024 * 1024))
    # This Play opens no file it measures, so its bound is a count of directory entries rather
    # than a count of reads, and a real home directory has far more of them than 200000.
    sp.add_argument("--max-files", default="2000000")
    sp.add_argument("--max-seconds", default="180")
    sp.set_defaults(fn=cmd_grew_read)

    sp = view_args(pulse(sub.add_parser("grew-report", help="diff against a retained baseline")))
    sp.add_argument("--since", default="", help="last, first, N runs back, 7d/2w/3m, or a date")
    sp.add_argument("--keep-baselines", default="10")
    sp.add_argument("--write-baseline", default="true")
    sp.set_defaults(fn=cmd_grew_report)

    sp = pulse(sub.add_parser("standingcost-read", help="locate the calendar partial the fetch step wrote"))
    sp.add_argument("--source", default="calendar")
    sp.add_argument("--partial", default=".standing-cost-calendar.json")
    sp.add_argument("--max-seconds", default="20")
    sp.set_defaults(fn=cmd_standingcost_read)

    sp = view_args(pulse(sub.add_parser("standingcost-report", help="price the recurring meetings")))
    sp.add_argument("--source", default="calendar")
    sp.add_argument("--partial", default=".standing-cost-calendar.json")
    sp.add_argument("--days", default="365")
    sp.add_argument("--focus-block-minutes", default="90")
    sp.add_argument("--currency", default="£")
    sp.add_argument("--hourly-rate", default="", help="blank means no money is claimed at all")
    sp.add_argument("--self", dest="owner", default="", help="your own address, if the feed omits it")
    sp.add_argument("--max-seconds", default="20")
    sp.set_defaults(fn=cmd_standingcost_report)

    sp = pulse(sub.add_parser("replydebt-read", help="locate the normalised mail partial"))
    sp.add_argument("--source", default="mail")
    sp.add_argument("--partial", default="")
    sp.add_argument("--max-seconds", default="20")
    sp.set_defaults(fn=cmd_replydebt_read)

    sp = view_args(pulse(sub.add_parser("replydebt-report", help="age the unanswered threads")))
    sp.add_argument("--min-age-days", default="3")
    sp.add_argument("--cold-days", default="30")
    sp.add_argument("--me", default="", help="your own addresses, comma separated")
    sp.set_defaults(fn=cmd_replydebt_report)

    sp = pulse(sub.add_parser("upstream-read", help="walk the lockfiles, or read the registry partial"))
    sp.add_argument("--source", required=True, choices=choices_of("upstream", "KINDS"))
    sp.add_argument("--root", default="~")
    sp.add_argument("--registry-partial", default="")
    sp.add_argument("--max-files", default="200000")
    sp.add_argument("--max-seconds", default="90")
    sp.set_defaults(fn=cmd_upstream_read)

    sp = view_args(pulse(sub.add_parser("upstream-report", help="grade the dependencies and render the card")))
    sp.add_argument("--root", default="~")
    sp.add_argument("--depth", default="0")
    sp.add_argument("--dormant-days", default="730")
    sp.add_argument("--cache-hours", default="24")
    sp.set_defaults(fn=cmd_upstream_report)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except FileNotFoundError as exc:
        return emit("", {"ok": False, "error": str(exc)}) or 1
    except KeyboardInterrupt:
        return emit("", {"ok": False, "error": "interrupted"}) or 1


if __name__ == "__main__":
    sys.exit(main())
