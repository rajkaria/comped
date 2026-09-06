"""where-it-went: where your attention actually went, from the history your browser already keeps.

A browser will show you the last nine things you opened. It will not tell you that one domain took
a fifth of your year, that you opened the same question thirty-one times, or that your longest
unbroken run at one site was four hours on a Tuesday afternoon. Every one of those numbers is
already sitting in a SQLite file on this machine, so this reads it and says so.

Three families, three schemas, three epochs, read independently: a browser this machine does not
have, or one macOS will not let a terminal open, costs that browser and never the run.

What it reads is the history table and nothing else. The tuple below names, once and in one place,
the stores this module deliberately never touches; those words appear nowhere else in this file,
not as a table name, not as a path, not as a query, and a test asserts it.
"""
import hashlib
import json
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from ..common import (Budget, EPOCH_1601, EPOCH_2001, Source, day, delta, expand, from_apple,
                      from_chrome, from_unix, host_of, iso, load_table, open_sqlite_readonly,
                      parse_date, pct, plural, redact_url, registrable, since_note)
from .tabs import CHROMIUM, FIREFOX, support_dirs

NEVER_READ = ("cookie", "password", "autofill", "form_data", "downloads", "login")

PRIVACY_SENTENCE = (
    "History rows only. This Play never opens, names or queries the "
    + ", ".join(NEVER_READ[:-1]) + " or " + NEVER_READ[-1]
    + " stores your browser keeps in the same folder; those six words appear exactly once in this "
      "module, in the list this sentence is built from, and never as a table, a path or a query.")

FAMILIES = ("chromium", "firefox", "safari")

DEFAULT_DAYS = 90
DEFAULT_GAP_MINUTES = 30
DEFAULT_TOP = 10
MAX_ROWS = 400000

CHROMIUM_DB = "History"
FIREFOX_DB = "places.sqlite"
SAFARI_DB = "~/Library/Safari/History.db"

SQL_CHROMIUM = ("SELECT u.url, u.title, v.visit_time, v.transition "
                "FROM visits v JOIN urls u ON u.id = v.url "
                "WHERE v.visit_time >= ? ORDER BY v.visit_time, u.url")
SQL_FIREFOX = ("SELECT p.url, p.title, h.visit_date, h.visit_type "
               "FROM moz_historyvisits h JOIN moz_places p ON p.id = h.place_id "
               "WHERE h.visit_date >= ? ORDER BY h.visit_date, p.url")
SQL_SAFARI = ("SELECT i.url, v.title, v.visit_time "
              "FROM history_visits v JOIN history_items i ON i.id = v.history_item "
              "WHERE v.visit_time >= ? ORDER BY v.visit_time, i.url")

# Chromium packs a core page-transition type into the low byte of `transition`; Firefox stores a
# small enum in `visit_type`. Only the values that separate intent from drift are named, and every
# value either table can hold that this module has no opinion about becomes "other", never a guess.
CHROMIUM_TRANSITION = {0: "linked", 1: "typed", 5: "typed", 8: "reload", 9: "typed", 10: "typed"}
FIREFOX_TRANSITION = {1: "linked", 2: "typed", 8: "linked", 9: "reload"}
INTENT_KINDS = ("typed", "linked", "reload", "other")

CATEGORIES = ("code", "docs", "social", "video", "ai", "shopping", "news", "mail", "finance", "local")
UNCATEGORISED = "uncategorised"

# A machine talking to itself. These never appear in a public-suffix list and never will.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", "host.docker.internal")
LOCAL_SUFFIXES = (".local", ".localhost", ".test", ".internal")

SEARCH_HOSTS = ("google.com", "bing.com", "duckduckgo.com", "ecosia.org", "startpage.com",
                "search.brave.com", "brave.com", "yandex.com", "baidu.com", "yahoo.com",
                "mojeek.com", "qwant.com", "kagi.com", "youtube.com",
                "github.com", "stackoverflow.com", "reddit.com", "wikipedia.org", "npmjs.com",
                "amazon.com", "amazon.co.uk", "perplexity.ai")
SEARCH_PARAMS = ("q", "query", "p", "search_query")

# Three or four columns of category, so a domain row keeps the room it needs for the domain.
CATEGORY_SHORT = {"code": "code", "docs": "docs", "social": "soc", "video": "vid", "ai": "ai",
                  "shopping": "shop", "news": "news", "mail": "mail", "finance": "fin",
                  "local": "local", UNCATEGORISED: "?"}

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# ---------------------------------------------------------------- reading

def _cutoff(cfg: dict):
    """Two windows' worth: this one, and the equal-length one before it that gives it a shape."""
    days = max(1, int(cfg.get("days") or DEFAULT_DAYS))
    return _now_of(cfg) - timedelta(days=2 * days)


def _now_of(cfg: dict):
    n = cfg.get("now")
    if isinstance(n, datetime):
        return n if n.tzinfo else n.replace(tzinfo=timezone.utc)
    parsed = parse_date(n) if n else None
    return parsed or datetime.now(timezone.utc)


def _to_chrome(d) -> int:
    return int((d - EPOCH_1601).total_seconds() * 1000000)


def _to_unix_us(d) -> int:
    return int((d - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1000000)


def _to_apple(d) -> float:
    return float((d - EPOCH_2001).total_seconds())


def _os_note(exc, path=None) -> str:
    """Absent and forbidden look alike from one failed open; only the parent directory tells them apart."""
    import os
    if isinstance(exc, PermissionError):
        return "macOS blocked the read; grant Full Disk Access to your terminal"
    if isinstance(exc, FileNotFoundError):
        parent = os.path.dirname(str(path)) if path else ""
        if parent and os.path.isdir(parent) and not os.access(parent, os.R_OK):
            return "macOS blocked the read; grant Full Disk Access to your terminal"
        return "not installed here"
    if isinstance(exc, sqlite3.DatabaseError):
        return "history database has a shape this reader does not know: {0}".format(str(exc)[:70])
    return str(exc)[:120]


def _profiles_chromium():
    """Every Chromium-family profile with a history database, using tab-debt's vendor table."""
    for label, mac, linux in CHROMIUM:
        for base in support_dirs():
            root = base / mac if base.name == "Application Support" else base / linux
            if not root.is_dir():
                continue
            try:
                children = sorted(p for p in root.iterdir() if p.is_dir())
            except OSError:
                children = []
            for profile in children:
                db = profile / CHROMIUM_DB
                if db.is_file():
                    name = label if profile.name in ("Default", "default") \
                        else "{0} ({1})".format(label, profile.name)
                    yield name, db
            break


def _profiles_firefox():
    for label, mac, linux in FIREFOX:
        for base in support_dirs():
            root = base / mac if base.name == "Application Support" else base / linux
            if not root.is_dir():
                continue
            try:
                children = sorted(p for p in root.iterdir() if p.is_dir())
            except OSError:
                children = []
            for profile in children:
                db = profile / FIREFOX_DB
                if db.is_file():
                    yield "{0} ({1})".format(label, profile.name.split(".")[-1][:18]), db
            break


def _query(db, sql: str, bound, budget: Budget) -> list:
    """Open a copy of the database read-only, pull the rows, and always remove the copy.

    The live file is held open by a running browser with a write-ahead log; opening it in place
    would block, and any journal this package caused would be a change it promises never to make.
    """
    con, tmp = None, None
    try:
        con, tmp = open_sqlite_readonly(db)
        out = []
        for row in con.execute(sql, (bound,)):
            out.append(tuple(row))
            if len(out) >= MAX_ROWS or (len(out) % 2000 == 0 and budget.exhausted):
                break
        return out
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _record(url, title, when, browser, family, transition, known) -> dict:
    return {"url": str(url or ""), "title": " ".join(str(title or "").split())[:120],
            "when": iso(when), "browser": browser, "family": family,
            "transition": transition, "transition_known": bool(known)}


def read_source(family: str, budget: Budget, cfg: dict) -> tuple:
    """Read one browser family's history. Returns (sources, records). Never raises for a browser."""
    cfg = cfg or {}
    if cfg.get("demo_root"):
        return _read_demo(family, cfg)

    cutoff = _cutoff(cfg)
    sources, records = [], []

    if family == "chromium":
        for name, db in _profiles_chromium():
            src = Source(name=name, path=str(db))
            try:
                rows = _query(db, SQL_CHROMIUM, _to_chrome(cutoff), budget)
            except (OSError, sqlite3.Error) as exc:
                sources.append(src.miss(_os_note(exc, db)))
                continue
            got = 0
            for url, title, stamp, transition in rows:
                when = from_chrome(stamp)
                if when is None or when < cutoff:
                    continue
                core = int(transition) & 0xFF if isinstance(transition, int) else -1
                records.append(_record(url, title, when, name, family,
                                       CHROMIUM_TRANSITION.get(core, "other"), True))
                got += 1
            budget.spend(_size(db))
            sources.append(src.hit(got, "urls + visits, {0} rows".format(len(rows))))

    elif family == "firefox":
        for name, db in _profiles_firefox():
            src = Source(name=name, path=str(db))
            try:
                rows = _query(db, SQL_FIREFOX, _to_unix_us(cutoff), budget)
            except (OSError, sqlite3.Error) as exc:
                sources.append(src.miss(_os_note(exc, db)))
                continue
            got = 0
            for url, title, stamp, kind in rows:
                when = from_unix((stamp or 0) / 1000000.0)
                if when is None or when < cutoff:
                    continue
                records.append(_record(url, title, when, name, family,
                                       FIREFOX_TRANSITION.get(kind, "other"), True))
                got += 1
            budget.spend(_size(db))
            sources.append(src.hit(got, "moz_places + moz_historyvisits, {0} rows".format(len(rows))))

    elif family == "safari":
        db = expand(SAFARI_DB)
        src = Source(name="Safari", path=str(db))
        try:
            rows = _query(db, SQL_SAFARI, _to_apple(cutoff), budget)
        except (OSError, sqlite3.Error) as exc:
            sources.append(src.miss(_os_note(exc, db)))
            rows = None
        if rows is not None:
            got = 0
            for url, title, stamp in rows:
                when = from_apple(stamp)
                if when is None or when < cutoff:
                    continue
                # Safari records no page-transition type at all, so intent is genuinely unknown
                # here rather than assumed to be a link, which would flatter the drift number.
                records.append(_record(url, title, when, "Safari", family, "unknown", False))
                got += 1
            budget.spend(_size(db))
            sources.append(src.hit(got, "history_items + history_visits; no transition column"))

    if not sources:
        sources.append(Source(name=family).miss("no profile found on this machine"))
    return sources, records


def _size(db) -> int:
    try:
        return db.stat().st_size
    except OSError:
        return 0


def _read_demo(family: str, cfg: dict) -> tuple:
    """The bundled fixture, so a first run says something before it is pointed at a real profile.

    The fixture is a JSON list of visit rows, not a copied database: a synthetic SQLite file would
    carry a schema version that drifts, and every timestamp in it would age into the wrong window.
    """
    path = expand(cfg["demo_root"]) / "browser-history.json"
    src = Source(name="{0} (demo)".format(family), path=str(path))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [src.miss("fixture unreadable: {0}".format(str(exc)[:60]))], []
    rows = doc.get("visits", doc) if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        return [src.miss("fixture is not a list of visits")], []

    cutoff, records = _cutoff(cfg), []
    for row in rows:
        if not isinstance(row, dict) or (row.get("family") or "chromium") != family:
            continue
        when = parse_date(row.get("when") or "")
        if when is None or when < cutoff:
            continue
        known = family != "safari" and row.get("transition") not in (None, "", "unknown")
        records.append(_record(row.get("url"), row.get("title"), when,
                               row.get("browser") or "{0} (demo)".format(family), family,
                               (row.get("transition") or "unknown") if known else "unknown", known))
    records.sort(key=lambda r: (r["when"], r["url"]))
    if not records:
        return [src.miss("fixture holds no {0} visits in the window".format(family))], []
    return [src.hit(len(records), "bundled fixture")], records


# ---------------------------------------------------------------- categories

def categories_table() -> dict:
    """The bundled domain map, shipped as JSON next to the code so a reader can audit the claim."""
    doc = load_table("domain-categories")
    mapping = doc.get("domains") if isinstance(doc.get("domains"), dict) else {}
    return {str(k).lower(): str(v) for k, v in mapping.items() if v in CATEGORIES}


def categorise(domain: str, table: dict) -> str:
    """One category or the honest absence of one. Nothing here infers a category from a name."""
    d = str(domain or "").lower()
    if not d:
        return UNCATEGORISED
    if d in LOCAL_HOSTS or d.endswith(LOCAL_SUFFIXES) or re.match(r"^\d+\.\d+\.\d+\.\d+$", d):
        return "local"
    return table.get(d, UNCATEGORISED)


# ---------------------------------------------------------------- search terms

def _unquote(s: str) -> str:
    text = str(s or "").replace("+", " ")
    out, i = bytearray(), 0
    while i < len(text):
        ch = text[i]
        if ch == "%" and i + 3 <= len(text):
            try:
                out.append(int(text[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.extend(ch.encode("utf-8"))
        i += 1
    return out.decode("utf-8", "replace")


def search_term(url: str) -> str:
    """The words you typed, from your own search URL, or "" when this is not one.

    Only the query keys real search forms use, and only on hosts that are search boxes, so a
    document id in a `q=` parameter on some unrelated app is never mistaken for a search.
    """
    u = str(url or "")
    host = host_of(u)
    if not host:
        return ""
    if host not in SEARCH_HOSTS and registrable(host) not in SEARCH_HOSTS:
        return ""
    query = u.split("?", 1)[1].split("#", 1)[0] if "?" in u else ""
    for pair in query.split("&"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        if key.strip().lower() in SEARCH_PARAMS and value:
            return " ".join(_unquote(value).split())[:120]
    return ""


def _fingerprint(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------- analysis

def _shift(d, mode: str):
    """Clock-face time. Local by default, because a heatmap in UTC is a heatmap of the wrong day."""
    return d.astimezone(timezone.utc) if mode == "utc" else d.astimezone()


def _hm(minutes) -> str:
    m = int(round(minutes))
    return "{0}m".format(m) if m < 60 else "{0}h{1:02d}m".format(m // 60, m % 60)


def _part_of_day(hour: int) -> str:
    return ("morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17
            else "evening" if 17 <= hour < 22 else "night")


def analyse(records: list, now, cfg: dict) -> dict:
    """Turn a flat visit list into the shape of a quarter's attention.

    Everything is counted against a denominator that is also reported. A domain share is a share of
    the visits in the window, a category share is a share of the same number, and the visits this
    table could not categorise are named as such rather than folded into "other" and forgotten.
    """
    cfg = cfg or {}
    days = max(1, int(cfg.get("days") or DEFAULT_DAYS))
    gap_minutes = max(1, int(cfg.get("gap_minutes") or DEFAULT_GAP_MINUTES))
    top_n = max(1, int(cfg.get("top") or DEFAULT_TOP))
    redact = cfg.get("redact", True)
    tz_mode = str(cfg.get("tz") or "local").lower()
    table = categories_table()

    start = now - timedelta(days=days)
    earlier = now - timedelta(days=2 * days)

    rows = []
    for r in records:
        when = parse_date(r.get("when") or "")
        if when is None or when > now or when < earlier:
            continue
        host = host_of(r.get("url") or "")
        domain = registrable(host) or (host or "(non-web)")
        rows.append({"when": when, "url": r.get("url") or "", "title": r.get("title") or "",
                     "browser": r.get("browser") or "?", "domain": domain,
                     "category": categorise(domain, table),
                     "transition": r.get("transition") or "unknown",
                     "known": bool(r.get("transition_known"))})
    rows.sort(key=lambda r: (r["when"], r["url"]))
    window = [r for r in rows if r["when"] >= start]
    before = [r for r in rows if r["when"] < start]
    total = len(window)

    domains = Counter(r["domain"] for r in window)
    cats = Counter(r["category"] for r in window)
    cats_before = Counter(r["category"] for r in before)
    browsers = Counter(r["browser"] for r in window)

    ranked = sorted(domains.items(), key=lambda kv: (-kv[1], kv[0]))
    category_rows = sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))

    view = {
        "days": days, "gap_minutes": gap_minutes, "top": top_n, "tz": tz_mode,
        "redacted": bool(redact),
        "window": {"from": day(start), "to": day(now), "days": days},
        "visits": total, "previous_visits": len(before),
        "unique_urls": len({r["url"] for r in window}),
        "unique_domains": len(domains),
        "per_day": round(total / float(days), 1),
        "browsers": [{"name": k, "visits": v, "share": (v / float(total)) if total else 0.0}
                     for k, v in sorted(browsers.items(), key=lambda kv: (-kv[1], kv[0]))],
        "domains": [{"domain": d, "visits": c, "share": (c / float(total)) if total else 0.0,
                     "category": categorise(d, table)} for d, c in ranked[:top_n]],
        "domain_total": len(ranked),
        "categories": [{"category": k, "visits": v, "share": (v / float(total)) if total else 0.0,
                        "domains": len({r["domain"] for r in window if r["category"] == k})}
                       for k, v in category_rows],
        "uncategorised": {
            "visits": cats.get(UNCATEGORISED, 0),
            "share": pct(cats.get(UNCATEGORISED, 0), total),
            "domains": len({r["domain"] for r in window if r["category"] == UNCATEGORISED}),
            "note": "not in the bundled table; reported as unknown rather than guessed at"},
        "table_size": len(table),
    }
    view["sessions"] = _sessions(window, gap_minutes, days, tz_mode)
    view["rereads"] = _rereads(window, top_n, redact)
    view["heatmap"] = _heatmap(window, tz_mode)
    view["intent"] = _intent(window)
    view["searches"] = _searches(window, top_n, redact)
    view["trend"] = _trend(window, before, now, days, cats, cats_before)
    view["busiest_day"] = _busiest_day(window)
    payload = baseline_payload(view)
    baseline = cfg.get("baseline") or {}
    view["delta"] = delta(payload, baseline.get("payload") or {})
    view["since"] = since_note(baseline, now)
    view["verdict"] = _verdict(view)
    view["privacy"] = PRIVACY_SENTENCE
    return view


def baseline_payload(view: dict) -> dict:
    """What the next run compares against: one number per category, so the net is the visit change."""
    return {c["category"]: c["visits"] for c in view["categories"]}


def _sessions(window: list, gap_minutes: int, days: int, tz_mode: str) -> dict:
    """Visits within `gap_minutes` of each other are one sitting; a longer silence ends it."""
    gap = timedelta(minutes=gap_minutes)
    sittings, run = [], []
    for r in window:
        if run and (r["when"] - run[-1]["when"]) > gap:
            sittings.append(run)
            run = []
        run.append(r)
    if run:
        sittings.append(run)

    lengths = [(s[-1]["when"] - s[0]["when"]).total_seconds() / 60.0 for s in sittings]
    longest = max(range(len(sittings)), key=lambda i: (lengths[i], -i)) if sittings else None

    # The single-domain run is the quotable one: a maximal stretch of consecutive visits inside one
    # sitting that never left the domain. A stretch of one visit has no duration and is not a run.
    best, current = None, []
    for s in sittings:
        for r in s:
            if current and current[-1]["domain"] != r["domain"]:
                best = _better_run(best, current)
                current = []
            current.append(r)
        best = _better_run(best, current)
        current = []
    best = _better_run(best, current)

    return {
        "count": len(sittings),
        "per_day": round(len(sittings) / float(days), 2),
        "mean_minutes": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
        "mean": _hm(sum(lengths) / len(lengths)) if lengths else "0m",
        "median_visits": _median([len(s) for s in sittings]),
        "longest": None if longest is None else _describe_run(sittings[longest], tz_mode),
        "longest_domain_run": None if best is None else _describe_run(best, tz_mode),
    }


def _better_run(best, candidate):
    if len(candidate) < 2:
        return best
    span = (candidate[-1]["when"] - candidate[0]["when"]).total_seconds()
    if best is None:
        return list(candidate)
    return list(candidate) if span > (best[-1]["when"] - best[0]["when"]).total_seconds() else best


def _describe_run(run: list, tz_mode: str) -> dict:
    start, end = run[0]["when"], run[-1]["when"]
    local = _shift(start, tz_mode)
    minutes = (end - start).total_seconds() / 60.0
    counts = Counter(r["domain"] for r in run)
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return {"minutes": round(minutes, 1), "length": _hm(minutes), "visits": len(run),
            "domain": top, "domains": len(counts),
            "start": iso(start), "end": iso(end), "date": day(start),
            "weekday": DAY_NAMES[local.weekday()], "hour": local.hour,
            "when": "{0} {1}".format(DAY_NAMES[local.weekday()], _part_of_day(local.hour))}


def _median(values: list) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    m = float(vals[mid]) if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
    return int(m) if m == int(m) else m


def _rereads(window: list, top_n: int, redact: bool) -> list:
    """The exact pages opened most often. The quotable line, and a list of things to automate."""
    counts, sample = Counter(), {}
    for r in window:
        key = r["url"].split("#")[0]
        counts[key] += 1
        sample.setdefault(key, r)
    out = []
    for url, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if n < 2:
            continue
        r = sample[url]
        # Even with redaction off the display form drops the query string, because the card and
        # the top of the report are the parts a person screenshots.
        item = {"url": redact_url(url, True) or r["domain"], "count": n, "domain": r["domain"],
                "category": r["category"], "title": r["title"] if not redact else "",
                "fingerprint": _fingerprint(url)}
        if not redact:
            item["full"] = url
        out.append(item)
        if len(out) >= top_n:
            break
    return out


def _heatmap(window: list, tz_mode: str) -> dict:
    grid = [[0] * 24 for _ in range(7)]
    for r in window:
        local = _shift(r["when"], tz_mode)
        grid[local.weekday()][local.hour] += 1
    flat = [(grid[d][h], d, h) for d in range(7) for h in range(24)]
    best = max(flat) if any(c for c, _, _ in flat) else None
    return {"grid": grid, "rows": list(DAY_SHORT), "hours": list(range(24)),
            "peak": None if best is None else {
                "weekday": DAY_NAMES[best[1]], "hour": best[2], "visits": best[0],
                "label": "{0} {1:02d}:00".format(DAY_NAMES[best[1]], best[2])},
            "by_weekday": [{"day": DAY_NAMES[d], "visits": sum(grid[d])} for d in range(7)]}


def _intent(window: list) -> dict:
    """Typed is intent; linked is drift. Where a browser records neither, that is what is reported."""
    counts = Counter()
    unknown_browsers = set()
    for r in window:
        if r["known"]:
            counts[r["transition"] if r["transition"] in INTENT_KINDS else "other"] += 1
        else:
            counts["unknown"] += 1
            unknown_browsers.add(r["browser"])
    known = sum(counts[k] for k in INTENT_KINDS)
    return {"typed": counts["typed"], "linked": counts["linked"], "reload": counts["reload"],
            "other": counts["other"], "unknown": counts["unknown"], "known": known,
            "typed_share": pct(counts["typed"], known),
            "linked_share": pct(counts["linked"], known),
            "not_exposed": sorted(unknown_browsers),
            "note": ("{0} does not record how a page was reached, so those visits are counted in "
                     "the total and left out of the split above".format(
                         ", ".join(sorted(unknown_browsers))) if unknown_browsers else "")}


def _searches(window: list, top_n: int, redact: bool) -> dict:
    """Your own searches, from your own URLs. Never rendered on the card, redacted in the report."""
    terms, hosts = Counter(), Counter()
    for r in window:
        term = search_term(r["url"])
        if not term:
            continue
        hosts[r["domain"]] += 1
        terms[term.lower()] += 1
    rows = []
    for term, n in sorted(terms.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]:
        row = {"count": n, "words": len(term.split()), "characters": len(term),
               "fingerprint": _fingerprint(term)}
        row["term"] = "(redacted #{0})".format(row["fingerprint"]) if redact else term
        rows.append(row)
    return {"total": sum(terms.values()), "distinct": len(terms), "redacted": bool(redact),
            "hosts": [{"domain": h, "searches": n}
                      for h, n in sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]],
            "terms": rows,
            "note": "search terms are never drawn on the card, in any redaction mode"}


def _trend(window: list, before: list, now, days: int, cats, cats_before) -> dict:
    """This window against the equal-length one before it, whole and per category."""
    from ..card import sparkline
    bucket_days = 7 if days >= 21 else 1
    buckets = max(1, int(round(days / float(bucket_days))))
    span = timedelta(days=bucket_days)
    edges = [now - span * (buckets - i) for i in range(buckets + 1)]

    def series(subset):
        out = [0] * buckets
        for r in subset:
            for i in range(buckets):
                if edges[i] <= r["when"] < edges[i + 1] or (i == buckets - 1 and r["when"] >= edges[i]):
                    out[i] += 1
                    break
        return out

    overall = series(window)
    per_category = []
    for name in sorted(set(list(cats.keys()) + list(cats_before.keys()))):
        current, prior = cats.get(name, 0), cats_before.get(name, 0)
        per_category.append({
            "category": name, "visits": current, "previous": prior, "change": current - prior,
            "change_pct": pct(current - prior, prior) if prior else None,
            "spark": sparkline(series([r for r in window if r["category"] == name]))})
    per_category.sort(key=lambda c: (-c["visits"], c["category"]))
    return {"bucket_days": bucket_days, "buckets": overall, "spark": sparkline(overall),
            "visits": len(window), "previous": len(before),
            "change": len(window) - len(before),
            "change_pct": pct(len(window) - len(before), len(before)) if before else None,
            "categories": per_category,
            "note": "the previous window is the {0} days before this one, read from the same "
                    "history rows".format(days)}


def _busiest_day(window: list) -> dict:
    counts = Counter(day(r["when"]) for r in window)
    if not counts:
        return {"date": "", "visits": 0, "days_with_visits": 0}
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return {"date": best[0], "visits": best[1], "days_with_visits": len(counts)}


def _verdict(view: dict) -> str:
    if not view["visits"]:
        return "no history rows in the window"
    parts = ["{0:,} pages in {1} days".format(view["visits"], view["days"])]
    if view["domains"]:
        d = view["domains"][0]
        parts.append("{0} took {1}%".format(d["domain"], int(round(d["share"] * 100))))
    run = view["sessions"]["longest_domain_run"]
    if run:
        parts.append("longest single-domain run {0}".format(run["length"]))
    return "; ".join(parts)


# ---------------------------------------------------------------- presentation

def _hour_labels() -> list:
    marks = {0: "0", 3: "3", 6: "6", 9: "9", 12: "N", 15: "3", 18: "6", 21: "9"}
    return [marks.get(h, " ") for h in range(24)]


def render(v: dict, cfg: dict) -> str:
    from ..card import Card, heatmap, legend, sparkline, tier_bar

    cfg = cfg or {}
    c = Card("WHERE IT WENT", "{0} days".format(v["days"]), cfg.get("color"))
    c.blank()
    if not v["visits"]:
        c.headline("no history rows in the last {0} days".format(v["days"]), "1;33")
        c.wrap("Every browser this Play knows about was absent, empty or unreadable. The sources "
               "table in the report says which, and why.")
        c.blank()
        c.wrap(PRIVACY_SENTENCE)
        return c.close()

    c.headline("{0:,} pages in {1} days".format(v["visits"], v["days"]), "1;36")
    c.row("{0:,} distinct pages across {1:,} sites · {2} a day".format(
        v["unique_urls"], v["unique_domains"], v["per_day"]))
    c.row(" · ".join("{0} {1:,}".format(b["name"], b["visits"]) for b in v["browsers"][:3]))
    c.blank()

    c.rule("WHERE")
    for d in v["domains"][:6]:
        c.bar("{0} · {1}".format(d["domain"], CATEGORY_SHORT.get(d["category"], "?")),
              "{0:,}".format(d["visits"]), d["share"], 10, 26)
    c.row("{0:,} sites; the top {1} are {2}% of {3:,} pages".format(
        v["domain_total"], len(v["domains"]),
        pct(sum(d["visits"] for d in v["domains"]), v["visits"]), v["visits"]))

    # Four named tiers and one honest remainder, so the bar really does partition the visits
    # rather than quietly normalising over whichever five happened to come top.
    named = v["categories"][:4]
    rest = v["visits"] - sum(x["visits"] for x in named)
    tiers = [(x["category"], x["visits"]) for x in named] + ([("everything else", rest)] if rest else [])
    if any(n for _, n in tiers):
        c.rule("WHAT KIND")
        c.row(tier_bar(tiers, 56))
        c.row(legend(tiers))
        c.row("{0:,} pages ({1}%) are on sites the table does not name".format(
            v["uncategorised"]["visits"], v["uncategorised"]["share"]))

    c.rule("WHEN")
    for line in heatmap(v["heatmap"]["grid"], v["heatmap"]["rows"], _hour_labels()):
        c.row(line)
    peak = v["heatmap"]["peak"]
    if peak:
        c.row("busiest hour: {0} ({1:,} pages) · times are {2}".format(
            peak["label"], peak["visits"], "UTC" if v["tz"] == "utc" else "local"))

    s = v["sessions"]
    c.rule("SITTINGS")
    c.row("{0:,} sittings ({1}m gap) · mean {2} · {3} a day".format(
        s["count"], v["gap_minutes"], s["mean"], s["per_day"]))
    run = s["longest_domain_run"]
    if run:
        c.row("longest single-domain run: {0} on {1}, {2}".format(
            run["length"], run["domain"], run["when"]))
    if s["longest"]:
        c.row("longest sitting: {0}, {1:,} pages, {2}".format(
            s["longest"]["length"], s["longest"]["visits"], s["longest"]["when"]))

    if v["rereads"]:
        c.rule("OPENED AGAIN AND AGAIN")
        for r in v["rereads"][:4]:
            c.cols(r["url"], "{0}×".format(r["count"]), 6)
        c.row("each is a bookmark, an alias or a script away from free")

    i = v["intent"]
    c.rule("HOW YOU GOT THERE")
    if i["known"]:
        c.row("typed {0}% · link {1}% · reload {2}%   of {3:,} judged".format(
            i["typed_share"], i["linked_share"], pct(i["reload"], i["known"]), i["known"]))
    if i["unknown"]:
        c.wrap("{0:,} visits carry no transition record{1}; they are in every total above and in "
               "none of the three shares.".format(
                   i["unknown"], " ({0})".format(", ".join(i["not_exposed"])) if i["not_exposed"] else ""))

    t = v["trend"]
    if t["spark"]:
        c.rule("MOVEMENT")
        c.row("{0}  {1:,} this window vs {2:,} the {3} before".format(
            t["spark"], t["visits"], t["previous"], plural(v["days"], "day")))
        for row in t["categories"][:3]:
            if row["spark"]:
                c.cols("{0} {1}".format(row["spark"], row["category"]),
                       "{0:+,}".format(row["change"]), 10)

    c.blank()
    c.wrap(PRIVACY_SENTENCE)
    if v["searches"]["total"]:
        c.wrap("{0:,} of those pages were your own searches. The words are in neither this card "
               "nor, unless you ask, the report.".format(v["searches"]["total"]))
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    cfg = cfg or {}
    total = v["visits"] or 0
    L = ["# Where it went", "",
         "{0:,} page visits between {1} and {2} ({3} days), across {4:,} sites.".format(
             total, v["window"]["from"], v["window"]["to"], v["days"], v["unique_domains"]), "",
         v["verdict"] + ".", "",
         "| measure | value | of |", "|---|---|---|",
         "| page visits | {0:,} | {1} days |".format(total, v["days"]),
         "| distinct pages | {0:,} | {1:,} visits |".format(v["unique_urls"], total),
         "| sites | {0:,} | {1:,} visits |".format(v["unique_domains"], total),
         "| visits a day | {0} | {1} days |".format(v["per_day"], v["days"]),
         "| sittings | {0:,} | {1}-minute gap |".format(v["sessions"]["count"], v["gap_minutes"]),
         "| mean sitting | {0} | {1:,} sittings |".format(v["sessions"]["mean"], v["sessions"]["count"]),
         "| sittings a day | {0} | {1} days |".format(v["sessions"]["per_day"], v["days"]),
         "| busiest day | {0} ({1:,} visits) | {2} dates with any visit |".format(
             v["busiest_day"]["date"] or "n/a", v["busiest_day"]["visits"],
             v["busiest_day"]["days_with_visits"]),
         "| previous window | {0:,} visits | the {1} days before |".format(
             v["previous_visits"], v["days"]),
         ""]

    L += ["## Where the visits went", "", "| site | visits | share of {0:,} | category |".format(total),
          "|---|---|---|---|"]
    L += ["| {0} | {1:,} | {2}% | {3} |".format(d["domain"], d["visits"],
                                                int(round(d["share"] * 100)), d["category"])
          for d in v["domains"]]
    L += ["", "The top {0} of {1:,} sites account for {2}% of the {3:,} visits.".format(
        len(v["domains"]), v["domain_total"],
        pct(sum(d["visits"] for d in v["domains"]), total), total), ""]

    L += ["## By category", "", "| category | visits | share of {0:,} | sites |".format(total),
          "|---|---|---|---|"]
    L += ["| {0} | {1:,} | {2}% | {3:,} |".format(c["category"], c["visits"],
                                                  int(round(c["share"] * 100)), c["domains"])
          for c in v["categories"]]
    L += ["", "Categories come from a hand-curated table of {0} domains bundled with this Play. "
          "{1:,} visits ({2}% of {3:,}), on {4}, are on domains the table does not name; "
          "they are reported as `{5}` rather than guessed at.".format(
              v["table_size"], v["uncategorised"]["visits"], v["uncategorised"]["share"], total,
              plural(v["uncategorised"]["domains"], "site"), UNCATEGORISED), ""]

    L += ["## Sittings", "",
          "A sitting is a run of visits no more than {0} minutes apart. There were {1:,} of them, "
          "{2} a day, averaging {3} and a median of {4} each.".format(
              v["gap_minutes"], v["sessions"]["count"], v["sessions"]["per_day"],
              v["sessions"]["mean"], plural(v["sessions"]["median_visits"], "page")), ""]
    for label, key in (("Longest sitting", "longest"), ("Longest single-domain run", "longest_domain_run")):
        run = v["sessions"][key]
        if run:
            L.append("- **{0}**: {1}, {2:,} visits across {3}, starting {4} ({5}), "
                     "mostly {6}.".format(label, run["length"], run["visits"],
                                          plural(run["domains"], "site"), run["start"],
                                          run["when"], run["domain"]))
    L.append("")

    L += ["## When", "",
          "A visit count per weekday and hour, in {0} time.".format(
              "UTC" if v["tz"] == "utc" else "this machine's local"), "",
          "| day | " + " | ".join("{0:02d}".format(h) for h in range(24)) + " | total |",
          "|---" * 26 + "|"]
    for i, name in enumerate(v["heatmap"]["rows"]):
        row = v["heatmap"]["grid"][i]
        L.append("| {0} | {1} | {2:,} |".format(name, " | ".join(str(c) for c in row), sum(row)))
    if v["heatmap"]["peak"]:
        L += ["", "Busiest hour: {0}, {1:,} of {2:,} visits.".format(
            v["heatmap"]["peak"]["label"], v["heatmap"]["peak"]["visits"], total)]
    L.append("")

    if v["rereads"]:
        L += ["## Opened again and again", "",
              "| page | times opened | site | category |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(r.get("full", r["url"]), r["count"], r["domain"],
                                                 r["category"]) for r in v["rereads"]]
        L += ["", "Each row is one page opened more than once out of {0:,} distinct pages. "
              "URLs are {1}.".format(v["unique_urls"],
                                     "shown in full because redaction was turned off"
                                     if not v["redacted"] else
                                     "truncated to host and path; query strings are removed and the "
                                     "fingerprint column in the JSON identifies the exact URL "
                                     "without printing it"), ""]

    i = v["intent"]
    L += ["## Intent versus drift", "", "| how the page was reached | visits | share of {0:,} judged |".format(
        i["known"]), "|---|---|---|"]
    for name, key in (("typed or searched", "typed"), ("followed a link", "linked"),
                      ("reloaded", "reload"), ("other", "other")):
        L.append("| {0} | {1:,} | {2}% |".format(name, i[key], pct(i[key], i["known"])))
    L.append("| not recorded by the browser | {0:,} | n/a |".format(i["unknown"]))
    L += ["", i["note"] or "Every browser read here records how each page was reached.", ""]

    s = v["searches"]
    L += ["## Your own searches", "",
          "{0:,} of the {1:,} visits were searches you ran yourself, {2:,} of them distinct, on "
          "{3} search host(s).".format(s["total"], total, s["distinct"], len(s["hosts"])), ""]
    if s["terms"]:
        L += ["| term | times | words |", "|---|---|---|"]
        L += ["| {0} | {1} | {2} |".format(t["term"], t["count"], t["words"]) for t in s["terms"]]
        L += ["", "Terms are {0}. {1}".format(
            "redacted to a stable fingerprint, so a repeat is still countable"
            if s["redacted"] else "shown in full because redaction was turned off", s["note"]), ""]

    t = v["trend"]
    L += ["## Movement", "",
          "{0:,} visits this window against {1:,} in the {2} days before it ({3:+,}).".format(
              t["visits"], t["previous"], v["days"], t["change"]), "",
          "| category | this window | the window before | change |", "|---|---|---|---|"]
    L += ["| {0} | {1:,} | {2:,} | {3:+,} |".format(c["category"], c["visits"], c["previous"],
                                                    c["change"]) for c in t["categories"]]
    d = v["delta"]
    L += ["", "Against the last run of this Play: {0}.".format(v["since"])]
    if not d["first_run"]:
        L.append("Net {0:+,} visits; grew {1}, shrank {2}, new {3}, gone {4}.".format(
            int(d["net"]), len(d["grew"]), len(d["shrank"]), len(d["added"]), len(d["removed"])))
    L.append("")

    L += ["## Sources", "", "| source | read | visits | detail |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2:,} | {3} |".format(s2["name"], "yes" if s2["found"] else "no",
                                               s2["items"], s2["note"] or "")
          for s2 in sources]
    L += ["", "## What this read", "", PRIVACY_SENTENCE, "",
          "Each history database was copied to a temporary file and opened read-only, so a running "
          "browser was never locked and the original was never journalled, upgraded or written. "
          "Nothing left this machine.", ""]
    return "\n".join(L)
