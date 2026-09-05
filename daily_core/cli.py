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

from .common import (Budget, as_bool, emit, envelope, fixtures_dir, now_utc, out_path,
                     state_read, state_write, write_text)

PLAYS = ("tabs", "contacts", "apps", "notes", "clutter", "receipts")


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
    sp.add_argument("--max-seconds", default="60")
    sp.set_defaults(fn=cmd_receipts_read)

    sp = view_args(common(sub.add_parser("receipts-report", help="total the receipts per currency")))
    sp.add_argument("--months-back", default="12")
    sp.set_defaults(fn=cmd_receipts_report)
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
