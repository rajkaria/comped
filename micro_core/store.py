"""One append-only log, shared by the four Plays that remember.

The file is JSONL because a log a person runs fifteen times a day has to survive being written to
while it is being read, and appending one line is the only write that does. Nothing here truncates,
rewrites or deletes: a mistake in the log is a line you can see, not a number you cannot explain.
"""
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .common import day, expand, iso, now_utc, tz_of

SYMBOLS = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₽": "RUB", "₩": "KRW"}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
AMOUNT = re.compile(r"^\s*(?P<sym>[₹$€£¥₽₩])?\s*(?P<num>\d[\d,]*(?:[.,]\d{1,2})?)\s*(?P<rest>.*)$", re.S)
TAG = re.compile(r"#([\w-]+)")


@dataclass(frozen=True)
class Entry:
    t: datetime
    data: dict


# ---------------------------------------------------------------- the log

def stream_path(state_dir, stream):
    return expand(state_dir) / "{0}.jsonl".format(stream)


def append(state_dir, stream, doc):
    """One line, one write, opened for append: two Plays writing at once cannot interleave."""
    p = stream_path(state_dir, stream)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = dict(doc)
    body.setdefault("t", iso(now_utc()))
    body.setdefault("v", 1)
    line = json.dumps(body, default=str, sort_keys=True) + "\n"
    with open(str(p), "a", encoding="utf-8") as fh:
        fh.write(line)
    return str(p)


def read(state_dir, stream, since=None):
    """Every line that parses. A torn or hand-edited line costs itself and nothing else."""
    p = stream_path(state_dir, stream)
    out = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return out
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
            t = now_utc(doc["t"])
        except (ValueError, KeyError, TypeError):
            continue
        if since is None or t >= since:
            out.append(Entry(t=t, data=doc))
    return sorted(out, key=lambda e: e.t)


def days_with_entries(entries, tz=None):
    tz = tz or tz_of()
    return {day(e.t, tz) for e in entries}


# ---------------------------------------------------------------- streaks

def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def streak(days, today):
    """(current, longest).

    Today not being in the set does not end the current streak — the day is not over yet, and a
    tracker that resets at midnight punishes you for checking it in the morning.
    """
    if not days:
        return (0, 0)
    dates = sorted({_d(s) for s in days})
    longest, run = 1, 1
    for prev, cur in zip(dates, dates[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    end = _d(today)
    if end not in dates:
        end = end - timedelta(days=1)
        if end not in dates:
            return (0, longest)
    current = 0
    while end in dates:
        current += 1
        end -= timedelta(days=1)
    return (current, longest)


def grid(days, today, window):
    end = _d(today)
    cells = []
    for i in range(window - 1, -1, -1):
        cells.append("█" if (end - timedelta(days=i)).strftime("%Y-%m-%d") in days else "·")
    return "".join(cells)


def worst_weekday(days, today, window):
    """The weekday you miss most, or nothing. Two weeks of history is the floor for saying it."""
    end = _d(today)
    span = [end - timedelta(days=i) for i in range(window)]
    if len(span) < 14:
        return None
    misses = {}
    for d in span:
        if d.strftime("%Y-%m-%d") not in days:
            misses[d.weekday()] = misses.get(d.weekday(), 0) + 1
    if not misses:
        return None
    top = max(misses.values())
    winners = [w for w, n in misses.items() if n == top]
    if len(winners) != 1 or top < 2:
        return None
    return WEEKDAYS[winners[0]]


def by_day(entries, tz=None):
    tz = tz or tz_of()
    out = {}
    for e in entries:
        out.setdefault(day(e.t, tz), []).append(e)
    return out


# ---------------------------------------------------------------- money

def parse_entry(s, default_currency):
    """"₹320 lunch #food" → amount, currency, label, tag. Money is Decimal, never float."""
    text = str(s or "").strip()
    m = AMOUNT.match(text)
    if not m:
        raise ValueError("no amount in {0!r}: write it like '320 lunch' or '₹320 lunch #food'".format(text))
    raw = m.group("num").replace(",", "")
    if raw.count(".") > 1:
        raise ValueError("cannot read {0!r} as an amount".format(m.group("num")))
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError("cannot read {0!r} as an amount".format(m.group("num")))
    rest = m.group("rest").strip()
    tag = ""
    found = TAG.search(rest)
    if found:
        tag = found.group(1).lower()
        rest = TAG.sub("", rest).strip()
    label = re.sub(r"\s+", " ", rest).strip()
    currency = SYMBOLS.get(m.group("sym") or "", "") or (default_currency or "USD").upper()
    return {"amount": amount, "currency": currency, "label": label or "unlabelled",
            "tag": tag or (label.split(" ")[0].lower() if label else "unlabelled")}


def money(x):
    return str(Decimal(str(x)).quantize(Decimal("0.01")))
