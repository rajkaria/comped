"""Shared machinery: the emit contract, time, and the small formatting vocabulary.

Deliberately a separate, smaller module than daily_core.common rather than an import of it. Three
cores live in this repo and none of them import another, so a Play's bundled resources are exactly
what that Play needs and a change to one family cannot move a number in a different one.
"""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    # The cards use box and block characters; on a Windows code page, printing one to a pipe dies
    # before a single row reaches the screen. Ask for UTF-8, carry on if the stream cannot.
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

BLOCKS = "▁▂▃▄▅▆▇█"


# ---------------------------------------------------------------- the step contract

def emit(human, result):
    """A human block, then exactly one JSON object as the last line. Nothing may follow it."""
    text = (human or "").rstrip()
    if text:
        sys.stdout.write(text + "\n")
    sys.stdout.write(json.dumps(result, default=str, sort_keys=True) + "\n")
    sys.stdout.flush()
    return 0


def warn(msg):
    """An expected absence: true, and the reason. Never an exception, never a non-zero exit."""
    return {"ok": True, "warning": msg}


# ---------------------------------------------------------------- scalars

def as_bool(s):
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def expand(p):
    return Path(str(p)).expanduser()


def now_utc(s=""):
    """Parse an ISO-8601 instant, or read the clock. Always returns an aware datetime in UTC.

    Every Play takes `now` so that a test, a fixture and a demo run all produce the same bytes;
    a naive string is read as UTC rather than as the machine's zone, so a fixture cannot drift
    with the laptop it runs on.
    """
    text = str(s or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(text)
    except ValueError:
        try:
            d = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return datetime.now(timezone.utc)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def tz_of(name=""):
    """The named zone, the machine's zone for "", and UTC when there is no tz database at all."""
    text = str(name or "").strip()
    if not text:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(text)
    except Exception:
        return timezone.utc


def local(d, tz=None):
    return d.astimezone(tz or tz_of())


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day(d, tz=None):
    """The calendar day this instant falls on, in the reader's zone — streaks are lived locally."""
    return local(d, tz).strftime("%Y-%m-%d")


def hhmm(d, tz=None):
    return local(d, tz).strftime("%H:%M")


# ---------------------------------------------------------------- formatting

def human_int(n):
    try:
        return "{0:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def human_usd(x):
    try:
        v = Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        return str(x)
    return "${0:,.2f}".format(v)


def human_tokens(n):
    """41200 reads as 41.2k. The exact number is in the JSON; the human line wants the shape."""
    try:
        v = int(n)
    except (TypeError, ValueError):
        return str(n)
    if v < 1000:
        return str(v)
    if v < 1000000:
        return "{0:.1f}k".format(v / 1000.0).replace(".0k", "k")
    return "{0:.1f}M".format(v / 1000000.0).replace(".0M", "M")


def minutes(n):
    n = int(n)
    if n < 60:
        return "{0} min".format(n)
    h, m = divmod(n, 60)
    return "{0}h {1:02d}m".format(h, m)


def plural(n, one, many=""):
    return one if n == 1 else (many or one + "s")


def sparkline(values):
    """Eight blocks. A flat series draws flat rather than full, so "nothing changed" looks like it."""
    nums = [float(v) for v in values]
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    if hi <= lo:
        return BLOCKS[0] * len(nums)
    span = hi - lo
    return "".join(BLOCKS[min(len(BLOCKS) - 1, int((v - lo) / span * (len(BLOCKS) - 1) + 0.5))] for v in nums)


def trunc(s, width):
    s = str(s)
    return s if len(s) <= width else s[:max(0, width - 1)] + "…"


def rule(title="", width=60):
    if not title:
        return "─" * width
    return "── {0} {1}".format(title, "─" * max(0, width - len(title) - 4))


def fixtures_dir():
    """Bundled synthetic data, so a stranger's first run works with nothing configured."""
    return Path(__file__).resolve().parent / "fixtures"
