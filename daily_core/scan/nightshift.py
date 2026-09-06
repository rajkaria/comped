"""night-shift: when the commits actually land, and how the late ones behave afterwards.

Every editor and every dashboard reports commit times in whatever zone the machine is set to
today, which quietly rewrites history every time someone travels or changes a laptop. This module
does the opposite: git records the committer's own UTC offset in the timestamp, so a commit made at
04:12 in Tokyo is a 04:12 commit forever, no matter where the machine reading it happens to be.
`--date=iso-strict` hands that offset over intact and every hour, weekday and calendar date in this
card is the wall clock the offset encodes, never `datetime.now()`'s idea of local time.

The distributions are the easy half. The half that is worth having is the correlation: for late
commits against the rest, how often a commit was later reverted, how often a fix-up followed it
within the hour, and how long its subject line was. Those three are recorded facts with
denominators printed next to them, which is the only reason it is defensible to put them on a card.

Two things this deliberately does not do. It does not interpret: the numbers here are counts of
commits and nothing else, they are not a measure of health, sleep, wellbeing or output quality, and
nothing in this module offers advice. And it does not guess at a timezone: when more than one UTC
offset appears in the window the card says so, because a fortnight in another zone and a changed
routine look identical in an hour histogram and only one of them is about the schedule.
"""
import json
import re
from collections import Counter
from datetime import timedelta

from .. import gitread
from ..card import heatmap, pad, rpad, sparkline
from ..common import (Budget, Source, baseline_read, baseline_write, delta, expand, iso,
                      parse_date, pct, plural, shorten_path, since_note)

KINDS = ("commits",)
NAME = "night-shift"
DEMO_FILE = "commits.json"

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
FULL_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# git's own revert message names the commit it undoes in quotes, which is the only in-repository
# link between the two that exists without a network call.
REVERT = re.compile(r'^Revert\s+"(.+)"\s*$')
FIXUP = re.compile(r"fixup!|squash!|^amend|fix typo|oops|whoops|typo", re.I)

# One record per commit, fields separated by unit separators so a subject containing a pipe, a tab
# or a quote cannot forge a field boundary.
LOG_FORMAT = "--format=%x1e%H%x1f%aN%x1f%aE%x1f%ad%x1f%cd%x1f%s"

FRAMING = ("These are counts of commits. They are not a measure of health, sleep, wellbeing or "
           "the quality of anyone's work, and nothing here is a recommendation.")
FRAMING_SHORT = "Counts of commits. Nothing else is claimed."


# ---------------------------------------------------------------- reading

def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    """Every repository under `cfg["root"]`, one `git log` each, or a labelled reason there is none.

    Commits by other people are kept and flagged `mine=False` rather than dropped at this stage:
    a revert of your commit is very often somebody else's commit, and throwing it away here would
    silently zero the one correlation this Play exists to report. Everything counted downstream is
    still only yours.
    """
    if cfg.get("demo_root"):
        return _read_demo(cfg)

    root = cfg.get("root") or "~"
    src = Source(name="git", path=str(expand(root)))
    git = gitread.Git.find()
    if not git.ok:
        return [src.miss(git.note)], []
    if not expand(root).is_dir():
        return [src.miss("no folder at {0}".format(shorten_path(expand(root), 40)))], []

    repos = gitread.discover(root, budget)
    if not repos:
        return [src.miss("no git repository under {0}".format(shorten_path(expand(root), 40)))], []

    keys = gitread.own_identities(git, repos, cfg.get("emails") or ())
    days = max(1, int(cfg.get("days") or 90))
    since = _since_argument(cfg, days)

    sources, records, usable, skipped = [], [], 0, []
    for path in repos:
        if not budget.spend():
            break
        repo = gitread.describe(git, path)
        if not repo.usable:
            skipped.append(Source(name=repo.name or str(path), path=str(path)).miss(repo.note))
            continue
        usable += 1
        text = git.run(path, ["log", "--all", "--since={0}".format(since),
                              "--date=iso-strict", LOG_FORMAT])
        records.extend(_parse_log(text, repo.name, keys))
        if repo.shallow:
            skipped.append(Source(name=repo.name, path=str(path)).miss(repo.note))

    mine = sum(1 for r in records if r["mine"])
    note = "{0} of {1} repositories readable; {2} of {3} commits in the last {4} are yours".format(
        usable, len(repos), mine, len(records), plural(days, "day"))
    if not keys:
        note += "; no git identity is configured, so every author is counted"
    sources.append(src.hit(mine, note))
    sources.extend(sorted(skipped, key=lambda s: s.name)[:8])
    return sources, _sorted_records(records)


def _since_argument(cfg: dict, days: int) -> str:
    """An absolute instant, never a relative phrase: `--since=90.days` would be read against the
    machine's clock at the moment git runs, which is exactly the ambiguity this Play removes."""
    now = parse_date(cfg.get("now") or "")
    start = (now - timedelta(days=days)) if now else None
    if start is None:
        from ..common import now_utc
        start = now_utc() - timedelta(days=days)
    return iso(start)


def _parse_log(text: str, repo_name: str, keys) -> list:
    out = []
    for chunk in str(text or "").split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 6:
            continue
        sha, name, email, authored, committed, subject = parts[:6]
        if not sha:
            continue
        out.append({
            "repo": repo_name, "sha": sha[:12], "name": name, "email": email,
            "authored": authored, "committed": committed,
            "subject": " ".join(str(subject).split()),
            "mine": (not keys) or gitread.identity_key(name, email) in keys,
        })
    return out


def _read_demo(cfg: dict) -> tuple:
    """The demo reads a manifest of commits rather than a repository.

    A checkout has whatever dates the clone gave it, so a demo run against real history would put
    every commit in the same week and the whole card would be a single bar. The fixture carries its
    own offsets, which is also the only way to demonstrate the timezone caveat without travelling.
    """
    path = expand(cfg["demo_root"]) / DEMO_FILE
    src = Source(name="git (demo)", path=str(path))
    if not path.is_file():
        return [src.miss("fixture missing")], []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [src.miss("fixture unreadable: {0}".format(exc))], []
    if not isinstance(rows, list):
        return [src.miss("fixture is not a list of commits")], []

    records = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not row.get("authored"):
            continue
        records.append({
            "repo": str(row.get("repo") or "demo"),
            "sha": str(row.get("sha") or "demo{0:08d}".format(i)),
            "name": str(row.get("name") or "You"),
            "email": str(row.get("email") or "you@example.com"),
            "authored": str(row["authored"]),
            "committed": str(row.get("committed") or row["authored"]),
            "subject": " ".join(str(row.get("subject") or "").split()),
            "mine": bool(row.get("mine", True)),
        })
    return [src.hit(sum(1 for r in records if r["mine"]), "bundled fixture")], _sorted_records(records)


def _sorted_records(records: list) -> list:
    return sorted(records, key=lambda r: (r["authored"], r["repo"], r["sha"]))


# ---------------------------------------------------------------- analysis

def analyse(records: list, now, cfg: dict) -> dict:
    days = max(1, int(cfg.get("days") or 90))
    late_hour = max(0, min(23, int(cfg.get("late_hour") or 23)))
    dawn_hour = max(0, min(12, int(cfg.get("dawn_hour", 5))))
    fixup_minutes = max(1, int(cfg.get("fixup_minutes") or 60))
    aftermath_hours = max(1, int(cfg.get("aftermath_hours") or 12))
    start = now - timedelta(days=days)

    chron = _in_window(records, start, now)
    mine = [c for c in chron if c["mine"]]
    reverted = _reverts(chron)
    fixed = _followups(chron, fixup_minutes)

    hours = [0] * 24
    weekdays = [0] * 7
    grid = [[0] * 24 for _ in range(7)]
    for c in mine:
        hours[c["hour"]] += 1
        weekdays[c["weekday"]] += 1
        grid[c["weekday"]][c["hour"]] += 1

    late = [c for c in mine if _is_late(c["hour"], late_hour, dawn_hour)]
    rest = [c for c in mine if not _is_late(c["hour"], late_hour, dawn_hour)]
    weekend = [c for c in mine if c["weekday"] >= 5]
    total = len(mine)

    dates = sorted({c["date"] for c in mine})
    streak, gap = _streaks(dates)
    offsets = _offsets(mine)
    rewritten = [c for c in mine if c["committed_stamp"] < c["stamp"]]

    view = {
        "days": days, "late_hour": late_hour, "dawn_hour": dawn_hour,
        "window": {"start": iso(start), "end": iso(now)},
        "commits": total, "commits_in_window": len(chron),
        "others": len(chron) - total,
        "repos": sorted({c["repo"] for c in mine}),
        "hours": hours, "weekdays": weekdays, "grid": grid,
        "busiest_hour": _busiest(hours),
        "late": {"commits": len(late), "total": total, "share": pct(len(late), total),
                 "window": _late_window(late_hour, dawn_hour)},
        "weekend": {"commits": len(weekend), "total": total, "share": pct(len(weekend), total)},
        "quality": {
            "fixup_minutes": fixup_minutes,
            "late": _group_stats(late, reverted, fixed),
            "rest": _group_stats(rest, reverted, fixed),
        },
        "streak": streak, "gap": gap,
        "days_with_commits": len(dates), "day_share": pct(len(dates), days),
        "trend": _trend(mine, start, now, late_hour, dawn_hour),
        "per_repo": _per_repo(mine, late_hour, dawn_hour),
        "offsets": offsets,
        "travel": len(offsets) > 1,
        "travel_note": _travel_note(offsets),
        "rewritten": {"commits": len(rewritten), "total": total,
                      "note": ("{0} of {1} commits carry an author date later than their committer "
                               "date, so this history was rebased or amended and the timeline is "
                               "approximate").format(len(rewritten), total) if rewritten else ""},
        "latest": _aftermath(_latest(late or mine, late_hour, reverted, fixed, aftermath_hours),
                             chron, reverted, aftermath_hours),
        "framing": FRAMING,
    }
    view["quality"]["difference"] = {
        "revert_points": view["quality"]["late"]["revert_rate"] - view["quality"]["rest"]["revert_rate"],
        "fixup_points": view["quality"]["late"]["fixup_rate"] - view["quality"]["rest"]["fixup_rate"],
        "subject_chars": round(view["quality"]["late"]["mean_subject"]
                               - view["quality"]["rest"]["mean_subject"], 1),
    }
    view["caveats"] = _caveats(view)
    view["snapshot"] = {"commits": total, "late": len(late), "weekend": len(weekend),
                        "longest_streak": streak["longest"], "repos": len(view["repos"])}
    baseline = baseline_read(cfg["out_dir"], NAME) if cfg.get("out_dir") else {}
    view["delta"] = delta(view["snapshot"], baseline.get("payload") or {})
    view["since"] = since_note(baseline, now)
    return view


def save_baseline(view: dict, cfg: dict, now) -> str:
    """Record this run so the next one can say what moved. Separate from `analyse`, which reads only."""
    return baseline_write(cfg["out_dir"], NAME, view["snapshot"], now) if cfg.get("out_dir") else ""


def _in_window(records: list, start, now) -> list:
    """Parse once, keep the recorded offset, and sort by the real instant.

    `parse_date` preserves the `%z` offset rather than normalising to UTC, which is the whole point:
    `.hour`, `.weekday()` and `.date()` below are then the committer's wall clock, and `.timestamp()`
    is still the true instant for ordering two commits made in different zones.
    """
    out = []
    for r in records:
        when = parse_date(r.get("authored") or "")
        if when is None or not (start <= when <= now):
            continue
        committed = parse_date(r.get("committed") or "") or when
        out.append({
            "repo": r.get("repo") or "", "sha": r.get("sha") or "",
            "author": gitread.identity_key(r.get("name") or "", r.get("email") or ""),
            "name": r.get("name") or "", "subject": r.get("subject") or "",
            "mine": bool(r.get("mine", True)),
            "when": when, "stamp": when.timestamp(), "committed_stamp": committed.timestamp(),
            "hour": when.hour, "minute": when.minute, "weekday": when.weekday(),
            "date": when.strftime("%Y-%m-%d"), "clock": when.strftime("%H:%M"),
            "offset": _offset_minutes(when),
        })
    return sorted(out, key=lambda c: (c["stamp"], c["repo"], c["sha"]))


def _offset_minutes(when) -> int:
    off = when.utcoffset()
    return 0 if off is None else int(off.total_seconds() // 60)


def _is_late(hour: int, late_hour: int, dawn_hour: int) -> bool:
    return hour >= late_hour or hour < dawn_hour


def _late_window(late_hour: int, dawn_hour: int) -> str:
    return "{0} to {1}".format(_clock(late_hour), _clock(dawn_hour))


def _clock(hour: int) -> str:
    hour = int(hour) % 24
    if hour == 0:
        return "midnight"
    if hour == 12:
        return "noon"
    return "{0}{1}".format(hour if hour < 12 else hour - 12, "am" if hour < 12 else "pm")


def _busiest(hours: list) -> dict:
    top = max(hours) if hours else 0
    if not top:
        return {"hour": None, "commits": 0, "label": "none"}
    h = hours.index(top)
    return {"hour": h, "commits": top, "label": "{0:02d}:00".format(h)}


# -- correlation ---------------------------------------------------------

def _reverts(chron: list) -> set:
    """Shas that a later commit in the same repository names in a `Revert "…"` subject.

    Walking forward and remembering the most recent commit per subject makes this one pass and also
    picks the nearest match, which is the right one when a subject has been used twice.
    """
    seen, reverted = {}, set()
    for c in chron:
        match = REVERT.match(c["subject"])
        if match:
            target = seen.get((c["repo"], match.group(1).strip()))
            if target:
                reverted.add(target)
        seen[(c["repo"], c["subject"])] = c["sha"]
    return reverted


def _followups(chron: list, minutes: int) -> set:
    """Shas followed within `minutes` by the same author in the same repository with a fix-up subject."""
    lanes = {}
    for c in chron:
        lanes.setdefault((c["repo"], c["author"]), []).append(c)
    flagged, limit = set(), minutes * 60
    for key in sorted(lanes):
        lane = lanes[key]
        for i, c in enumerate(lane):
            for j in range(i + 1, len(lane)):
                gap = lane[j]["stamp"] - c["stamp"]
                if gap > limit:
                    break
                if FIXUP.search(lane[j]["subject"]):
                    flagged.add(c["sha"])
                    break
    return flagged


def _group_stats(group: list, reverted: set, fixed: set) -> dict:
    n = len(group)
    rev = sum(1 for c in group if c["sha"] in reverted)
    fix = sum(1 for c in group if c["sha"] in fixed)
    subjects = sum(len(c["subject"]) for c in group)
    return {"commits": n,
            "reverted": rev, "revert_rate": pct(rev, n),
            "fixups": fix, "fixup_rate": pct(fix, n),
            "mean_subject": round(float(subjects) / n, 1) if n else 0.0}


# -- calendar ------------------------------------------------------------

def _streaks(dates: list) -> tuple:
    """Longest run of consecutive days carrying a commit, and the longest genuine break inside them.

    A break is only counted between two days that both have commits: the silence before your first
    commit in the window and after your last one is the window's edge, not a break.
    """
    empty_streak = {"longest": 0, "start": "", "end": "", "days_with_commits": 0}
    empty_gap = {"longest": 0, "start": "", "end": ""}
    if not dates:
        return empty_streak, empty_gap

    days = [parse_date(d).date() for d in dates]
    best, best_start, best_end = 1, days[0], days[0]
    run, run_start = 1, days[0]
    gap, gap_start, gap_end = 0, None, None
    for prev, cur in zip(days, days[1:]):
        step = (cur - prev).days
        if step == 1:
            run += 1
        else:
            run, run_start = 1, cur
            if step - 1 > gap:
                gap, gap_start, gap_end = step - 1, prev + timedelta(days=1), cur - timedelta(days=1)
        if run > best:
            best, best_start, best_end = run, run_start, cur
    return ({"longest": best, "start": best_start.isoformat(), "end": best_end.isoformat(),
             "days_with_commits": len(days)},
            {"longest": gap, "start": gap_start.isoformat() if gap_start else "",
             "end": gap_end.isoformat() if gap_end else ""})


def _trend(mine: list, start, now, late_hour: int, dawn_hour: int) -> dict:
    """The window in equal thirds, so "is the share moving" is a question with an answer."""
    span = (now - start) / 3
    edges = [start, start + span, start + 2 * span, now]
    thirds = []
    for i in range(3):
        lo, hi = edges[i], edges[i + 1]
        part = [c for c in mine if lo <= c["when"] < hi or (i == 2 and c["when"] == hi)]
        n_late = sum(1 for c in part if _is_late(c["hour"], late_hour, dawn_hour))
        thirds.append({"label": "{0} → {1}".format(lo.strftime("%d %b"), hi.strftime("%d %b")),
                       "commits": len(part), "late": n_late, "share": pct(n_late, len(part))})
    shares = [t["share"] for t in thirds]
    move = shares[2] - shares[0]
    return {"thirds": thirds, "spark": sparkline(shares, width=3),
            "move": move,
            "direction": "up {0} points".format(move) if move > 0 else
                         "down {0} points".format(-move) if move < 0 else "level"}


def _per_repo(mine: list, late_hour: int, dawn_hour: int) -> list:
    total, late = Counter(), Counter()
    for c in mine:
        total[c["repo"]] += 1
        if _is_late(c["hour"], late_hour, dawn_hour):
            late[c["repo"]] += 1
    rows = [{"repo": r, "commits": n, "late": late[r], "share": pct(late[r], n)}
            for r, n in total.items()]
    return sorted(rows, key=lambda r: (-r["late"], -r["commits"], r["repo"]))


def _offsets(mine: list) -> list:
    seen = {}
    for c in mine:
        row = seen.setdefault(c["offset"], {"minutes": c["offset"], "label": _offset_label(c["offset"]),
                                            "commits": 0, "first": c["date"], "last": c["date"]})
        row["commits"] += 1
        row["first"] = min(row["first"], c["date"])
        row["last"] = max(row["last"], c["date"])
    return [seen[m] for m in sorted(seen)]


def _offset_label(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    minutes = abs(int(minutes))
    return "UTC{0}{1:02d}:{2:02d}".format(sign, minutes // 60, minutes % 60)


def _travel_note(offsets: list) -> str:
    if len(offsets) < 2:
        return ""
    parts = ", ".join("{0} from {1} to {2} ({3})".format(o["label"], o["first"], o["last"],
                                                         plural(o["commits"], "commit"))
                      for o in offsets)
    return ("{0} UTC offsets appear in this window — {1}. Hours recorded under a different offset "
            "are a different zone, not a different routine; a daylight-saving change looks the "
            "same here.").format(len(offsets), parts)


def _latest(candidates: list, late_hour: int, reverted: set, fixed: set, aftermath_hours: int) -> dict:
    """The commit furthest into the night, ranked on the wall clock the commit itself recorded."""
    if not candidates:
        return {}
    ranked = sorted(candidates, key=lambda c: (_night_rank(c["hour"], late_hour), c["stamp"],
                                               c["repo"], c["sha"]))
    c = ranked[-1]
    return {"clock": c["clock"], "hour": c["hour"], "weekday": FULL_DAYS[c["weekday"]],
            "date": c["date"], "offset": _offset_label(c["offset"]), "repo": c["repo"],
            "subject": c["subject"], "sha": c["sha"], "reverted": c["sha"] in reverted,
            "aftermath": "", "aftermath_hours": aftermath_hours,
            "followed_by": 0, "followed_reverted": 0, "followed_fixups": 0}


def _night_rank(hour: int, late_hour: int) -> int:
    """23:00 is earlier than 04:00. Wrapping the evening hours below zero makes `max` agree."""
    return hour - 24 if hour >= late_hour else hour


def _aftermath(latest: dict, chron: list, reverted: set, hours: int) -> dict:
    """What the same author committed in the same repository in the hours after the latest commit."""
    if not latest:
        return latest
    anchor = [c for c in chron if c["sha"] == latest["sha"]]
    if not anchor:
        return latest
    a = anchor[0]
    limit = hours * 3600
    after = [c for c in chron if c["repo"] == a["repo"] and c["author"] == a["author"]
             and 0 < c["stamp"] - a["stamp"] <= limit]
    reverts = sum(1 for c in after if c["sha"] in reverted or REVERT.match(c["subject"]))
    fixups = sum(1 for c in after if FIXUP.search(c["subject"]))
    latest["followed_by"] = len(after)
    latest["followed_reverted"] = reverts
    latest["followed_fixups"] = fixups
    if latest.get("reverted"):
        latest["aftermath"] = "it was reverted by a later commit"
    elif reverts:
        latest["aftermath"] = "{0} of the {1} that followed within {2}h {3} reverted".format(
            reverts, plural(len(after), "commit"), hours, "was" if reverts == 1 else "were")
    elif fixups:
        latest["aftermath"] = "{0} of the {1} that followed within {2}h match a fix-up subject".format(
            fixups, plural(len(after), "commit"), hours)
    elif after:
        latest["aftermath"] = "{0} followed within {1}h, none reverted".format(
            plural(len(after), "commit"), hours)
    else:
        latest["aftermath"] = "nothing followed it within {0}h".format(hours)
    return latest


def _caveats(view: dict) -> list:
    out = []
    if view["travel_note"]:
        out.append(view["travel_note"])
    if view["rewritten"]["note"]:
        out.append(view["rewritten"]["note"])
    if view["others"]:
        out.append("{0} in the window were by other authors and are counted only when they revert "
                   "or follow one of yours".format(plural(view["others"], "commit")))
    if not view["commits"]:
        out.append("no commits of yours in the last {0}: every number below is zero because there "
                   "was nothing to count".format(plural(view["days"], "day")))
    return out


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card

    c = Card("NIGHT SHIFT", "{0} days".format(v["days"]), cfg.get("color"))
    c.blank()
    c.headline("{0} of commits after {1} ({2} of {3})".format(
        _share(v["late"]["share"]), _clock(v["late_hour"]), v["late"]["commits"], v["late"]["total"]))
    c.row("{0} on weekends ({1} of {2}) · {3} · {4}".format(
        _share(v["weekend"]["share"]), v["weekend"]["commits"], v["weekend"]["total"],
        plural(len(v["repos"]), "repo"),
        plural(v["days_with_commits"], "day with a commit", "days with a commit")))
    c.blank()

    c.rule("WHEN, ON THE CLOCK EACH COMMIT RECORDED")
    c.row("    " + _ruler())
    for row, n in zip(heatmap(v["grid"], DAYS), v["weekdays"]):
        # `cols` would collapse the runs of spaces that are the empty hours, so pad by hand.
        c.row("{0}{1}".format(pad(row, 32), rpad(str(n), 28)))
    if v["busiest_hour"]["hour"] is not None:
        c.row("busiest hour {0} ({1})".format(v["busiest_hour"]["label"],
                                              plural(v["busiest_hour"]["commits"], "commit")))
    lat = v["latest"]
    if lat:
        c.row("latest {0} {1} {2} ({3}) in {4}".format(
            lat["clock"], lat["weekday"], lat["date"], lat["offset"], lat["repo"]))
        c.wrap("— {0}".format(lat["aftermath"]))

    c.rule("LATE ({0}) AGAINST THE REST".format(v["late"]["window"]))
    q = v["quality"]
    c.table([("", "commits", "reverted", "fix-ups", "subject"),
             ("late", q["late"]["commits"], _rate(q["late"]["reverted"], q["late"]["revert_rate"]),
              _rate(q["late"]["fixups"], q["late"]["fixup_rate"]),
              "{0} ch".format(q["late"]["mean_subject"])),
             ("the rest", q["rest"]["commits"], _rate(q["rest"]["reverted"], q["rest"]["revert_rate"]),
              _rate(q["rest"]["fixups"], q["rest"]["fixup_rate"]),
              "{0} ch".format(q["rest"]["mean_subject"]))],
            [10, -8, -11, -11, -10])
    c.row("a fix-up is a follow-up by you within {0}".format(
        plural(q["fixup_minutes"], "minute")))

    c.rule("TREND")
    c.row("late share by third: {0}  {1}".format(
        " → ".join("{0}%".format(t["share"]) for t in v["trend"]["thirds"]), v["trend"]["spark"]))
    c.row("across the window: {0}".format(v["trend"]["direction"]))

    c.rule("RUNS")
    s, g = v["streak"], v["gap"]
    c.row("longest run of days with a commit: {0}{1}".format(
        plural(s["longest"], "day"), _span(s["start"], s["end"]) if s["longest"] else ""))
    c.row("longest break between two of them: {0}{1}".format(
        plural(g["longest"], "day"), _span(g["start"], g["end"]) if g["longest"] else ""))

    if v["per_repo"]:
        c.rule("WHERE THE LATE COMMITS ARE")
        for r in v["per_repo"][:4]:
            c.cols(r["repo"], "{0} late of {1} ({2}%)".format(r["late"], r["commits"], r["share"]), 26)

    if v["caveats"]:
        c.rule("READ THIS FIRST")
        for note in v["caveats"]:
            c.wrap(note)

    c.blank()
    c.wrap(v["since"] if v["delta"].get("first_run")
           else "{0}: {1}".format(v["since"], _delta_line(v["delta"])))
    c.wrap(FRAMING_SHORT)
    return c.close()


def _span(start: str, end: str) -> str:
    """`(15 Aug → 21 Aug)`. The year is already in the window line and does not fit twice."""
    return " ({0} → {1})".format(_short_date(start), _short_date(end)) if start and end else ""


def _short_date(s: str) -> str:
    d = parse_date(s)
    return d.strftime("%d %b") if d else str(s)


def _ruler() -> str:
    marks = [" "] * 24
    for h in (0, 6, 12, 18):
        for k, ch in enumerate(str(h)):
            if h + k < 24:
                marks[h + k] = ch
    return "".join(marks)


def _share(share: int) -> str:
    return "{0}%".format(share)


def _rate(count: int, share: int) -> str:
    return "{0} ({1}%)".format(count, share)


def _delta_line(d: dict) -> str:
    if d.get("first_run"):
        return "no previous run to compare against"
    moved = []
    for key in sorted(set(list(d.get("grew", {})) + list(d.get("shrank", {})))):
        change = d.get("grew", {}).get(key, d.get("shrank", {}).get(key, 0))
        moved.append("{0} {1}{2:g}".format(key, "+" if change > 0 else "", change))
    return ", ".join(moved) if moved else "nothing moved"


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    q = v["quality"]
    L = ["# Night shift", "",
         "{0} in the last {1}, {2} of them after {3} ({4} of {5}).".format(
             plural(v["commits"], "commit"), plural(v["days"], "day"),
             _share(v["late"]["share"]), _clock(v["late_hour"]),
             v["late"]["commits"], v["late"]["total"]), "",
         "Every hour, weekday and date below is the wall clock recorded in the commit's own UTC "
         "offset, not this machine's timezone.", "",
         "| measure | value | of |", "|---|---|---|",
         "| commits (yours) | {0} | {1} in the window |".format(v["commits"], v["commits_in_window"]),
         "| after {0} or before {1} | {2} | {3} ({4}%) |".format(
             _clock(v["late_hour"]), _clock(v["dawn_hour"]), v["late"]["commits"],
             v["late"]["total"], v["late"]["share"]),
         "| on weekends | {0} | {1} ({2}%) |".format(
             v["weekend"]["commits"], v["weekend"]["total"], v["weekend"]["share"]),
         "| days with at least one commit | {0} | {1} ({2}%) |".format(
             v["days_with_commits"], v["days"], v["day_share"]),
         "| longest run of consecutive such days | {0} | {1} → {2} |".format(
             v["streak"]["longest"], v["streak"]["start"] or "—", v["streak"]["end"] or "—"),
         "| longest break between two of them | {0} | {1} → {2} |".format(
             v["gap"]["longest"], v["gap"]["start"] or "—", v["gap"]["end"] or "—"),
         "| repositories | {0} | — |".format(len(v["repos"])),
         "| window | {0} | {1} |".format(v["window"]["start"], v["window"]["end"]), "",
         "## Late commits against the rest", "",
         "Rates are of each group, and each group's size is printed next to it.", "",
         "| group | commits | later reverted | followed by a fix-up within {0} min | mean subject |".format(
             q["fixup_minutes"]),
         "|---|---|---|---|---|",
         "| after {0} or before {1} | {2} | {3} of {2} ({4}%) | {5} of {2} ({6}%) | {7} chars |".format(
             _clock(v["late_hour"]), _clock(v["dawn_hour"]), q["late"]["commits"],
             q["late"]["reverted"], q["late"]["revert_rate"], q["late"]["fixups"],
             q["late"]["fixup_rate"], q["late"]["mean_subject"]),
         "| every other hour | {0} | {1} of {0} ({2}%) | {3} of {0} ({4}%) | {5} chars |".format(
             q["rest"]["commits"], q["rest"]["reverted"], q["rest"]["revert_rate"],
             q["rest"]["fixups"], q["rest"]["fixup_rate"], q["rest"]["mean_subject"]), "",
         "Difference, late minus the rest: revert rate {0:+d} points, fix-up rate {1:+d} points, "
         "subject {2:+g} characters.".format(
             q["difference"]["revert_points"], q["difference"]["fixup_points"],
             q["difference"]["subject_chars"]), "",
         "A revert is a later commit in the same repository whose subject is `Revert \"…\"` naming "
         "this one. A fix-up is a later commit by the same author in the same repository within "
         "{0} minutes whose subject matches `{1}`.".format(q["fixup_minutes"], FIXUP.pattern), "",
         "## Hour of day", "", "| hour | commits | share of {0} |".format(v["commits"]), "|---|---|---|"]
    L += ["| {0:02d}:00 | {1} | {2}% |".format(h, n, pct(n, v["commits"]))
          for h, n in enumerate(v["hours"]) if n]
    L += ["", "## Day of week", "", "| day | commits | share of {0} |".format(v["commits"]), "|---|---|---|"]
    L += ["| {0} | {1} | {2}% |".format(FULL_DAYS[i], n, pct(n, v["commits"]))
          for i, n in enumerate(v["weekdays"])]
    L += ["", "## Trend", "", "| third of the window | commits | late | share |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3}% |".format(t["label"], t["commits"], t["late"], t["share"])
          for t in v["trend"]["thirds"]]
    L += ["", "Across the window the late share is {0}.".format(v["trend"]["direction"])]

    if v["latest"]:
        lat = v["latest"]
        L += ["", "## The latest commit on the clock", "",
              "{0} on {1} {2} ({3}) in `{4}`, `{5}` — {6}.".format(
                  lat["clock"], lat["weekday"], lat["date"], lat["offset"], lat["repo"],
                  lat["sha"], lat["aftermath"])]

    L += ["", "## UTC offsets seen", "", "| offset | commits | first | last |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} |".format(o["label"], o["commits"], o["first"], o["last"])
          for o in v["offsets"]] or ["| — | 0 | — | — |"]
    if v["travel_note"]:
        L += ["", v["travel_note"]]

    if v["per_repo"]:
        L += ["", "## By repository", "", "| repository | commits | late | share |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3}% |".format(r["repo"], r["commits"], r["late"], r["share"])
              for r in v["per_repo"]]

    L += ["", "## Movement", "",
          "{0}.".format(v["since"]) if v["delta"].get("first_run")
          else "{0}: {1}.".format(v["since"], _delta_line(v["delta"]))]
    if v["caveats"]:
        L += ["", "## Caveats", ""] + ["- {0}".format(n) for n in v["caveats"]]
    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "")
          for s in sources]
    L += ["", "Read-only: commit metadata was read through git's own log, no file content was "
          "opened, no repository was changed and nothing left this machine.", "",
          FRAMING, ""]
    return "\n".join(L)
