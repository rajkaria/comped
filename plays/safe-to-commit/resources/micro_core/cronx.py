"""When does that expression actually fire.

The rule most implementations get wrong, and this one does not: when BOTH day-of-month and
day-of-week are restricted, a day matches if EITHER matches. `0 0 13 * 5` is the 13th and every
Friday, not Friday the 13th. When only one of the two is restricted, only that one applies.

The second thing it refuses to get wrong is the clock going forward. A schedule pinned to 01:30 in
a zone that springs forward does not fire on that day at all, and a Play that quietly printed
02:30 instead would be lying about the one day of the year you needed it.
"""
from datetime import datetime, timedelta, timezone

FIELDS = ("minute", "hour", "dom", "month", "dow")
BOUNDS = {"minute": (0, 59), "hour": (0, 23), "dom": (1, 31), "month": (1, 12), "dow": (0, 7)}
NAMES = {"month": {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))},
    "dow": {d: i for i, d in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))}}
MACROS = {"@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *",
          "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
          "@hourly": "0 * * * *"}
DAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def _field(text, name):
    lo, hi = BOUNDS[name]
    out = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty {0} field".format(name))
        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) < 1:
                raise ValueError("bad step in the {0} field: {1!r}".format(name, raw_step))
            step = int(raw_step)
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part.lstrip("-"):
            a, _, b = part.partition("-")
            start, end = _value(a, name), _value(b, name)
            if start > end:                       # 22-2 wraps midnight, as cron allows
                out.update(range(start, hi + 1, step))
                out.update(range(lo, end + 1, step))
                continue
        else:
            start = end = _value(part, name)
        out.update(range(start, end + 1, step))
    if name == "dow" and 7 in out:
        out.discard(7)
        out.add(0)
    return out


def _value(token, name):
    token = token.strip().lower()
    if token in NAMES.get(name, {}):
        return NAMES[name][token]
    if not token.lstrip("-").isdigit():
        raise ValueError("cannot read {0!r} in the {1} field".format(token, name))
    n = int(token)
    lo, hi = BOUNDS[name]
    if not lo <= n <= hi:
        raise ValueError("{0} out of range in the {1} field ({2}-{3})".format(n, name, lo, hi))
    return n


def parse(expr):
    text = str(expr or "").strip()
    if text.lower() in MACROS:
        text = MACROS[text.lower()]
    parts = text.split()
    if len(parts) != 5:
        raise ValueError("a cron expression has five fields (minute hour day month weekday); "
                         "got {0}".format(len(parts)))
    spec = {name: _field(part, name) for name, part in zip(FIELDS, parts)}
    spec["dom_restricted"] = parts[2].strip() != "*"
    spec["dow_restricted"] = parts[4].strip() != "*"
    spec["expr"] = " ".join(parts)
    return spec


def _day_matches(spec, d):
    if d.month not in spec["month"]:
        return False
    dom_ok = d.day in spec["dom"]
    dow_ok = ((d.weekday() + 1) % 7) in spec["dow"]
    if spec["dom_restricted"] and spec["dow_restricted"]:
        return dom_ok or dow_ok               # the POSIX OR
    if spec["dom_restricted"]:
        return dom_ok
    if spec["dow_restricted"]:
        return dow_ok
    return True


def _exists(naive, tz):
    """A wall-clock time that the zone skipped over is not a time. Ask the zone, do not assume."""
    aware = naive.replace(tzinfo=tz)
    back = aware.astimezone(timezone.utc).astimezone(tz)
    return (back.hour, back.minute) == (naive.hour, naive.minute)


def next_fires(spec, start, count, tz, horizon_days=1500):
    """The next `count` fires, in `tz`, strictly after `start`. Skipped local times are skipped."""
    after = start.astimezone(tz)
    hours, minutes = sorted(spec["hour"]), sorted(spec["minute"])
    out, day = [], after.date()
    for _ in range(horizon_days):
        if _day_matches(spec, day):
            for h in hours:
                for m in minutes:
                    naive = datetime(day.year, day.month, day.day, h, m)
                    if not _exists(naive, tz):
                        continue
                    cand = naive.replace(tzinfo=tz)
                    if cand > after:
                        out.append(cand)
                        if len(out) >= count:
                            return out
        day += timedelta(days=1)
    return out


def average_interval_min(fires):
    if len(fires) < 2:
        return None
    gaps = [(b - a).total_seconds() / 60.0 for a, b in zip(fires, fires[1:])]
    return int(round(sum(gaps) / len(gaps)))


def dst_warning(spec, tz, start, horizon_days=400):
    """Does this schedule land on an hour the zone skips, or on one it repeats?"""
    day = start.astimezone(tz).date()
    for _ in range(horizon_days):
        if _day_matches(spec, day):
            for h in sorted(spec["hour"]):
                for m in sorted(spec["minute"]):
                    naive = datetime(day.year, day.month, day.day, h, m)
                    if not _exists(naive, tz):
                        return ("{0:02d}:{1:02d} does not exist on {2} in this zone — the clocks go "
                                "forward and this run is skipped".format(h, m, day))
                    early = naive.replace(tzinfo=tz, fold=0)
                    late = naive.replace(tzinfo=tz, fold=1)
                    if early.utcoffset() != late.utcoffset():
                        return ("{0:02d}:{1:02d} happens twice on {2} in this zone — the clocks go "
                                "back and this run may fire twice".format(h, m, day))
        day += timedelta(days=1)
    return None


def _list(values, names=None):
    items = [names[v] if names else "{0:02d}".format(v) for v in sorted(values)]
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def describe(spec):
    mins, hours = sorted(spec["minute"]), sorted(spec["hour"])
    every_minute = len(mins) == 60
    if every_minute and len(hours) == 24:
        return "every minute"
    if len(hours) == 24 and len(mins) > 1:
        gaps = {b - a for a, b in zip(mins, mins[1:])}
        if len(gaps) == 1:
            return "every {0} minutes".format(gaps.pop())
        return "at {0} minutes past every hour".format(_list(mins))
    if every_minute:
        return "every minute of {0}".format(_list(hours))
    when = " and ".join("{0:02d}:{1:02d}".format(h, m) for h in hours for m in mins) if len(hours) * len(mins) <= 4 \
        else "{0} past {1}".format(_list(mins), _list(hours))
    if spec["dow_restricted"] and spec["dow"] == {1, 2, 3, 4, 5}:
        day = "every weekday"
    elif spec["dow_restricted"] and spec["dow"] == {0, 6}:
        day = "every weekend day"
    elif spec["dow_restricted"] and not spec["dom_restricted"]:
        day = "every " + _list(spec["dow"], DAY_NAMES)
    elif spec["dom_restricted"] and not spec["dow_restricted"]:
        day = "on the {0} of the month".format(_list(spec["dom"], {d: str(d) for d in range(1, 32)}))
    elif spec["dom_restricted"] and spec["dow_restricted"]:
        day = "on the {0} of the month or every {1}".format(
            _list(spec["dom"], {d: str(d) for d in range(1, 32)}), _list(spec["dow"], DAY_NAMES))
    else:
        day = "every day"
    if len(spec["month"]) != 12:
        day += " in {0}".format(_list(spec["month"], {i + 1: m for i, m in enumerate(
            ("January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"))}))
    return "{0} at {1}".format(day, when)
