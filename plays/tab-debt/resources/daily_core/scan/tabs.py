"""tab-debt: every tab you have open, across every browser, with the age you never see.

A browser shows a tab strip, never a tab count, and never the date a tab was last looked at. Both
numbers are in the session files the browser already writes, so this reads them and answers the
question the strip cannot: how many tabs are open, and how long since each was actually used.

Four families, four formats, read independently so a browser this machine does not have, or a
container macOS will not open, costs that browser and never the run.
"""
import os
from datetime import timedelta

from ..common import (Budget, Source, ago, day, expand, from_apple, from_chrome, from_unix,
                      host_of, iso, pct, redact_url, registrable)
from ..parsers import applesafari, arcsidebar, mozlz4, snss

# Chromium-family vendors, as (label, macOS support dir, Linux config dir). A profile is any child
# directory holding a Sessions folder, which is how "Default" and "Profile 3" are found alike.
CHROMIUM = [
    ("Chrome", "Google/Chrome", "google-chrome"),
    ("Chrome Beta", "Google/Chrome Beta", "google-chrome-beta"),
    ("Chrome Canary", "Google/Chrome Canary", "google-chrome-unstable"),
    ("Brave", "BraveSoftware/Brave-Browser", "BraveSoftware/Brave-Browser"),
    ("Edge", "Microsoft Edge", "microsoft-edge"),
    ("Chromium", "Chromium", "chromium"),
    ("Vivaldi", "Vivaldi", "vivaldi"),
    ("Opera", "com.operasoftware.Opera", "opera"),
    ("Comet", "Comet", "comet"),
    ("Dia", "Dia", "dia"),
]
FIREFOX = [("Firefox", "Firefox/Profiles", ".mozilla/firefox"),
           ("Zen", "zen/Profiles", ".zen"),
           ("LibreWolf", "librewolf/Profiles", ".librewolf")]

FAMILIES = ("chromium", "firefox", "safari", "arc")


def support_dirs():
    """Where a browser keeps its profile on this platform, most specific first."""
    home = expand("~")
    return [home / "Library" / "Application Support", home / ".config", home]


def _profiles_chromium():
    for label, mac, linux in CHROMIUM:
        for base in support_dirs():
            root = base / mac if base.name == "Application Support" else base / linux
            if not root.is_dir():
                continue
            for profile in sorted(root.iterdir()) if root.is_dir() else []:
                sessions = profile / "Sessions"
                if profile.is_dir() and sessions.is_dir():
                    yield label, profile.name, sessions
            break


def _newest(directory, prefix: str):
    """Chromium keeps several generations; the current tab set is the most recently written one."""
    try:
        files = [p for p in directory.iterdir() if p.name.startswith(prefix) and p.is_file()]
    except OSError:
        return None
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _read_file(path, reader, epoch):
    with open(path, "rb") as fh:
        parsed = reader(fh.read())
    for tab in parsed["tabs"]:
        tab["last_used"] = iso(epoch(tab.get("active_at") or tab.get("navigated_at")))
        tab["opened"] = iso(epoch(tab.get("navigated_at")))
    return parsed


def read_source(family: str, budget: Budget, demo_root=None) -> tuple:
    """Read one browser family. Returns (sources, tabs). Never raises for a browser it cannot read."""
    sources, tabs = [], []
    if demo_root is not None:
        return _read_demo(family, demo_root)

    if family == "chromium":
        for label, profile, sessions in _profiles_chromium():
            name = label if profile in ("Default", "default") else "{0} ({1})".format(label, profile)
            src = Source(name=name, path=str(sessions))
            newest = _newest(sessions, "Session_")
            if newest is None:
                sources.append(src.miss("no session file written yet"))
                continue
            try:
                parsed = _read_file(newest, snss.read_session, from_chrome)
            except snss.Unreadable as exc:
                sources.append(src.miss(str(exc)))
                continue
            except OSError as exc:
                sources.append(src.miss(_os_note(exc, newest)))
                continue
            if not parsed["commands"]:
                # The file is there and its header parsed, but nothing in it replayed. That is a
                # session format this reader does not know, not a browser with no tabs open.
                sources.append(src.miss("no commands could be replayed; unsupported session format"))
                continue
            for tab in parsed["tabs"]:
                tab["browser"] = name
            tabs += parsed["tabs"]
            budget.spend(newest.stat().st_size)
            sources.append(src.hit(len(parsed["tabs"]), "{0} commands replayed".format(parsed["commands"])))

    elif family == "firefox":
        for label, mac, linux in FIREFOX:
            for base in support_dirs():
                root = base / mac if base.name == "Application Support" else base / linux
                if not root.is_dir():
                    continue
                for profile in sorted(p for p in root.iterdir() if p.is_dir()):
                    # recovery is the live session; sessionstore is written on a clean shutdown.
                    candidates = [profile / "sessionstore-backups" / "recovery.jsonlz4",
                                  profile / "sessionstore-backups" / "previous.jsonlz4",
                                  profile / "sessionstore.jsonlz4"]
                    chosen = next((c for c in candidates if c.is_file()), None)
                    if chosen is None:
                        continue
                    name = "{0} ({1})".format(label, profile.name.split(".")[-1][:18])
                    src = Source(name=name, path=str(chosen))
                    try:
                        parsed = _read_file(chosen, mozlz4.read_session, from_unix)
                    except (mozlz4.Unreadable, OSError, ValueError) as exc:
                        sources.append(src.miss(_os_note(exc, chosen)))
                        continue
                    for tab in parsed["tabs"]:
                        tab["browser"] = name
                    tabs += parsed["tabs"]
                    budget.spend(chosen.stat().st_size)
                    sources.append(src.hit(len(parsed["tabs"]), chosen.name))
                break

    elif family == "safari":
        base = expand("~/Library/Safari")
        src = Source(name="Safari", path=str(base / "LastSession.plist"))
        try:
            parsed = _read_file(base / "LastSession.plist", applesafari.read_session, from_apple)
            for tab in parsed["tabs"]:
                tab["browser"] = "Safari"
            tabs += parsed["tabs"]
            sources.append(src.hit(len(parsed["tabs"])))
        except (applesafari.Unreadable, OSError) as exc:
            sources.append(src.miss(_os_note(exc, base / "LastSession.plist")))

    elif family == "arc":
        store = expand("~/Library/Application Support/Arc/StorableSidebar.json")
        src = Source(name="Arc", path=str(store))
        try:
            parsed = _read_file(store, arcsidebar.read_session, from_apple)
            for tab in parsed["tabs"]:
                tab["browser"] = "Arc"
            tabs += parsed["tabs"]
            sources.append(src.hit(len(parsed["tabs"]), "sidebar store"))
        except (arcsidebar.Unreadable, OSError) as exc:
            sources.append(src.miss(_os_note(exc, store)))

    if not sources:
        sources.append(Source(name=family).miss("no profile found on this machine"))
    return sources, tabs


def _os_note(exc, path=None) -> str:
    """Absent and forbidden look alike from one failed open; only the parent directory tells them apart."""
    if isinstance(exc, PermissionError):
        return "macOS blocked the read; grant Full Disk Access to your terminal"
    if isinstance(exc, FileNotFoundError):
        parent = os.path.dirname(str(path)) if path else ""
        if parent and os.path.isdir(parent) and not os.access(parent, os.R_OK):
            return "macOS blocked the read; grant Full Disk Access to your terminal"
        if parent and os.path.exists(parent):
            try:
                os.listdir(parent)
            except PermissionError:
                return "macOS blocked the read; grant Full Disk Access to your terminal"
            except OSError:
                pass
        return "not installed here"
    return str(exc)[:120]


def _read_demo(family: str, root):
    """The bundled fixtures, so a first run works before the reader is pointed at anything real."""
    readers = {"chromium": (snss.read_session, from_chrome, "chrome-session.snss", "Chrome"),
               "firefox": (mozlz4.read_session, from_unix, "firefox-sessionstore.json", "Firefox"),
               "safari": (applesafari.read_session, from_apple, "safari-lastsession.plist", "Safari"),
               "arc": (arcsidebar.read_session, from_apple, "arc-sidebar.json", "Arc")}
    reader, epoch, filename, label = readers[family]
    path = expand(root) / filename
    src = Source(name="{0} (demo)".format(label), path=str(path))
    if not path.is_file():
        return [src.miss("fixture missing")], []
    try:
        parsed = _read_file(path, reader, epoch)
    except Exception as exc:                     # a broken fixture must not look like a broken browser
        return [src.miss("fixture unreadable: {0}".format(str(exc)[:60]))], []
    if not parsed["commands"]:
        return [src.miss("fixture replayed no commands")], []
    for tab in parsed["tabs"]:
        tab["browser"] = "{0} (demo)".format(label)
    return [src.hit(len(parsed["tabs"]), "bundled fixture")], parsed["tabs"]


# ---------------------------------------------------------------- analysis

COLD_DAYS = 7


def reading_list(demo_root=None):
    """Safari's reading list: the backlog with a date on every row, which is what makes it damning."""
    path = (expand(demo_root) / "safari-bookmarks.plist") if demo_root else expand("~/Library/Safari/Bookmarks.plist")
    src = Source(name="Safari reading list", path=str(path))
    try:
        with open(path, "rb") as fh:
            items = applesafari.read_reading_list(fh.read())
    except (applesafari.Unreadable, OSError) as exc:
        return src.miss(_os_note(exc, path)), []
    return src.hit(len(items)), items


def analyse(tabs: list, lists: list, now, keep_path: bool) -> dict:
    """Turn a flat tab list into the four numbers a person can act on, and nothing they cannot.

    Age is the one measurement here that can be missing: a browser that never recorded a
    last-active time for a tab is counted in the total and excluded from every age figure, and the
    excluded count is reported, because a cold-tab number quietly computed over half the tabs is
    worse than one that says how many it could not judge.
    """
    from ..common import parse_date
    seen, hosts, per_browser, dated = {}, {}, {}, []
    for t in tabs:
        stamp = parse_date(t.get("last_used") or "") if t.get("last_used") else None
        t["_when"] = stamp
        if stamp:
            dated.append(t)
        host = registrable(host_of(t.get("url") or ""))
        t["_host"] = host or "(local file)"
        hosts[t["_host"]] = hosts.get(t["_host"], 0) + 1
        per_browser[t.get("browser", "?")] = per_browser.get(t.get("browser", "?"), 0) + 1
        key = (t.get("url") or "").split("#")[0]
        seen.setdefault(key, []).append(t)

    total = len(tabs)
    undated = total - len(dated)
    buckets = [0, 0, 0, 0, 0]
    labels = ["today", "this week", "this month", "3 months", "older"]
    for t in dated:
        d = (now - t["_when"]).days
        buckets[0 if d < 1 else 1 if d < 7 else 2 if d < 30 else 3 if d < 90 else 4] += 1

    cold = [t for t in dated if (now - t["_when"]).days >= COLD_DAYS]
    oldest = min(dated, key=lambda t: t["_when"]) if dated else None
    dupes = sorted(([{"url": redact_url(v[0].get("url"), keep_path), "count": len(v),
                      "browsers": sorted({x.get("browser", "?") for x in v})}
                     for k, v in seen.items() if len(v) > 1]),
                   key=lambda d: (-d["count"], d["url"]))
    dupe_extra = sum(d["count"] - 1 for d in dupes)

    unread = [i for i in lists if i.get("unread")]
    list_dates = [from_apple(i.get("added")) if isinstance(i.get("added"), (int, float)) else i.get("added")
                  for i in lists]
    list_dates = [d for d in list_dates if hasattr(d, "year")]

    return {
        "total": total, "windows": len({(t.get("browser"), t.get("window")) for t in tabs}),
        "browsers": [{"name": k, "tabs": v} for k, v in sorted(per_browser.items(), key=lambda kv: -kv[1])],
        "undated": undated,
        "buckets": [{"label": l, "tabs": c} for l, c in zip(labels, buckets)],
        "cold": len(cold), "cold_days": COLD_DAYS,
        "cold_share": pct(len(cold), len(dated)),
        "oldest": None if not oldest else {
            "url": redact_url(oldest.get("url"), keep_path), "title": (oldest.get("title") or "")[:60],
            "browser": oldest.get("browser"), "last_used": day(oldest["_when"]),
            "age_days": (now - oldest["_when"]).days, "age": ago(oldest["_when"], now)},
        "hosts": [{"host": h, "tabs": c, "share": (c / total) if total else 0.0}
                  for h, c in sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]],
        "duplicates": dupes[:8], "duplicate_tabs": dupe_extra,
        "pinned": sum(1 for t in tabs if t.get("pinned")),
        "grouped": sum(1 for t in tabs if t.get("grouped")),
        "deep": sum(1 for t in tabs if (t.get("history_depth") or 0) >= 10),
        "reading_list": {"total": len(lists), "unread": len(unread),
                         "oldest": day(min(list_dates)) if list_dates else ""},
        "closable": _closable(dupes, cold, now, keep_path),
        "verdict": _verdict(total, len(cold), dupe_extra),
    }


def _closable(dupes, cold, now, keep_path):
    """The shortlist, ordered by how little you would miss it: duplicates first, then the coldest."""
    out = [{"why": "open {0}×".format(d["count"]), "what": d["url"]} for d in dupes[:3]]
    for t in sorted(cold, key=lambda t: t["_when"])[:5 - len(out)]:
        out.append({"why": "untouched {0}".format(ago(t["_when"], now)),
                    "what": redact_url(t.get("url"), keep_path)})
    return out


def _verdict(total, cold, dupes):
    if total == 0:
        return "no open tabs found"
    if cold == 0 and dupes == 0:
        return "clean: every tab was used this week and none is open twice"
    parts = []
    if cold:
        parts.append("{0} of {1} tabs untouched for a week or more".format(cold, total))
    if dupes:
        parts.append("{0} duplicate{1}".format(dupes, "" if dupes == 1 else "s"))
    return "; ".join(parts)


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card, bucket_bars

    c = Card("TAB DEBT", "{0} browser{1}".format(len(v["browsers"]), "" if len(v["browsers"]) == 1 else "s"),
             cfg.get("color"))
    c.blank()
    c.headline("{0} open tabs across {1} window{2}".format(v["total"], v["windows"], "" if v["windows"] == 1 else "s"),
               "1;36")
    o = v["oldest"]
    if o:
        c.row("oldest was last used {0} ago, on {1}".format(o["age"], o["last_used"]))
        c.row("  {0}".format(o["title"] or o["url"]))
    if v["undated"]:
        c.wrap("{0} tab{1} carried no last-used time; they are counted above and left out of the "
               "ages below.".format(v["undated"], "" if v["undated"] == 1 else "s"))
    c.blank()

    c.rule("HOW COLD")
    for line in bucket_bars([b["tabs"] for b in v["buckets"]], [b["label"] for b in v["buckets"]]):
        c.row(line)
    c.row("{0} untouched {1}+ days  ({2}% of the tabs with a date)".format(v["cold"], v["cold_days"], v["cold_share"]))

    c.rule("WHERE THEY LIVE")
    for h in v["hosts"][:5]:
        c.bar(h["host"], str(h["tabs"]), h["share"])
    extras = []
    if v["pinned"]:
        extras.append("{0} pinned".format(v["pinned"]))
    if v["grouped"]:
        extras.append("{0} in groups".format(v["grouped"]))
    if v["deep"]:
        extras.append("{0} with 10+ pages of back history".format(v["deep"]))
    if extras:
        c.row(" · ".join(extras))

    if v["duplicates"]:
        c.rule("OPEN MORE THAN ONCE")
        for d in v["duplicates"][:4]:
            c.cols("{0}× {1}".format(d["count"], d["url"]),
                   "across browsers" if len(d["browsers"]) > 1 else "")
        c.row("{0} tab{1} would close with no page lost".format(
            v["duplicate_tabs"], "" if v["duplicate_tabs"] == 1 else "s"))

    rl = v["reading_list"]
    if rl["total"]:
        c.rule("READING LIST")
        c.row("{0} saved, {1} never opened{2}".format(
            rl["total"], rl["unread"], ", oldest {0}".format(rl["oldest"]) if rl["oldest"] else ""))

    if v["closable"]:
        c.rule("START HERE")
        for item in v["closable"]:
            c.cols(item["what"], item["why"], 22)

    c.blank()
    c.wrap("Read from the session files your browsers already wrote. Nothing was opened for "
           "writing, and no query string left this machine.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    L = ["# Tab debt", "",
         "{0} open tabs across {1} window(s) in {2} browser(s).".format(
             v["total"], v["windows"], len(v["browsers"])), "",
         "| measure | value |", "|---|---|",
         "| open tabs | {0} |".format(v["total"]),
         "| untouched {0}+ days | {1} ({2}%) |".format(v["cold_days"], v["cold"], v["cold_share"]),
         "| duplicates that would close cleanly | {0} |".format(v["duplicate_tabs"]),
         "| pinned | {0} |".format(v["pinned"]),
         "| no last-used time recorded | {0} |".format(v["undated"])]
    if v["oldest"]:
        L.append("| oldest tab last used | {0} ({1} ago) |".format(v["oldest"]["last_used"], v["oldest"]["age"]))
    L += ["", "## Browsers", "", "| browser | tabs |", "|---|---|"]
    L += ["| {0} | {1} |".format(b["name"], b["tabs"]) for b in v["browsers"]]
    L += ["", "## Where the tabs are", "", "| site | tabs | share |", "|---|---|---|"]
    L += ["| {0} | {1} | {2}% |".format(h["host"], h["tabs"], int(round(h["share"] * 100))) for h in v["hosts"]]
    if v["duplicates"]:
        L += ["", "## Open more than once", "", "| page | copies |", "|---|---|"]
        L += ["| {0} | {1} |".format(d["url"], d["count"]) for d in v["duplicates"]]
    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "") for s in sources]
    L += ["", "Read-only. Session files were read, never written. URLs are shown "
          + ("with their path, query strings removed." if cfg.get("keep_path") else "as hostnames only."), ""]
    return "\n".join(L)
