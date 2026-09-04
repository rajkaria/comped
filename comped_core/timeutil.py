from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_ts(v) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        secs = float(v) / (1000.0 if v > 1e11 else 1.0)
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(v, str):
        return None
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def window_start(now: datetime, days_back: int) -> datetime:
    return now - timedelta(days=int(days_back))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_key(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
