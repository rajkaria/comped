"""What the turn that just finished cost.

`comped` prices a month and takes seconds to do it, because it reads every session you have. This
answers a question about the last ninety seconds, so it reads 256 KB off the end of one file. That
is the whole trick, and it is also the whole limitation: this is a tail, not an accounting, and it
says so in its own output rather than letting a partial number pass as a total.
"""
import json
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from .common import day, now_utc, tz_of

TAIL_BYTES = 262144
HEAD_BYTES = 32768


def _jsonl(text):
    out, skipped = [], 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if isinstance(doc, dict):
            out.append(doc)
        else:
            skipped += 1
    return out, skipped


def tail_records(path, max_bytes=TAIL_BYTES):
    """The end of the file, minus the line the window cut in half."""
    try:
        size = os.path.getsize(str(path))
        with open(str(path), "rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()                      # the first line is a fragment; drop it
            raw = fh.read()
    except OSError:
        return []
    return _jsonl(raw.decode("utf-8", "replace"))[0]


def head_records(path, max_bytes=HEAD_BYTES):
    """The start of the file, for the session metadata that is only ever written once."""
    try:
        with open(str(path), "rb") as fh:
            raw = fh.read(max_bytes)
    except OSError:
        return []
    return _jsonl(raw.decode("utf-8", "replace"))[0]


def newest_transcript(dirs, depth=3):
    newest, when = None, -1
    for d in dirs:
        root = Path(str(d)).expanduser()
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                if len(path.relative_to(root).parts) > depth:
                    continue
                mtime = path.stat().st_mtime
            except (OSError, ValueError):
                continue
            if mtime > when:
                newest, when = path, mtime
    return newest


def recent_transcripts(dirs, since_mtime, depth=3, limit=40):
    """Deduplicated by resolved path: two configured directories may be the same directory, or one
    may sit inside the other, and a file counted twice would double today's bill."""
    out, seen = [], set()
    for d in dirs:
        root = Path(str(d)).expanduser()
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                if len(path.relative_to(root).parts) > depth:
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                if path.stat().st_mtime >= since_mtime:
                    seen.add(key)
                    out.append(path)
            except (OSError, ValueError):
                continue
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def _claude(doc):
    msg = doc.get("message")
    if not isinstance(msg, dict):
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    model = str(msg.get("model") or "")
    if model == "<synthetic>":
        return None
    return {"harness": "claude-code", "at": doc.get("timestamp") or "", "model": model,
            "input": int(usage.get("input_tokens") or 0),
            "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
            "cache_read": int(usage.get("cache_read_input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0)}


def _codex_totals(doc):
    payload = doc.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    tot = info.get("total_token_usage")
    return tot if isinstance(tot, dict) else None


def records_from(path):
    """Normalised usage records from one transcript, newest last, plus the count of unreadable lines."""
    path = Path(str(path))
    try:
        size = os.path.getsize(str(path))
        with open(str(path), "rb") as fh:
            if size > TAIL_BYTES:
                fh.seek(size - TAIL_BYTES)
                fh.readline()                      # the first line is a fragment; drop it
            docs, skipped = _jsonl(fh.read().decode("utf-8", "replace"))
    except OSError:
        return ([], 0)
    out, prev, model = [], None, ""
    if size > TAIL_BYTES:
        # Codex names the model once, at the top of the session. A tail alone prices it as unknown.
        for doc in head_records(path):
            payload = doc.get("payload")
            if doc.get("type") == "turn_context" and isinstance(payload, dict) and payload.get("model"):
                model = str(payload["model"])
    for doc in docs:
        payload = doc.get("payload")
        if doc.get("type") == "turn_context" and isinstance(payload, dict) and payload.get("model"):
            model = str(payload["model"])
        rec = _claude(doc)
        if rec is not None:
            out.append(rec)
            continue
        tot = _codex_totals(doc)
        if tot is None:
            continue
        # Codex reports running totals. The turn is the difference; a total that went down is a
        # new session rather than a negative turn, so it is taken whole and not subtracted.
        cur = tuple(int(tot.get(k) or 0) for k in ("input_tokens", "cached_input_tokens", "output_tokens"))
        if prev is None or any(c < q for c, q in zip(cur, prev)):
            delta = cur
        else:
            delta = tuple(c - q for c, q in zip(cur, prev))
        prev = cur
        if delta == (0, 0, 0):
            continue
        inp, cached, output = delta
        out.append({"harness": "codex", "at": doc.get("timestamp") or "", "model": model,
                    "input": max(inp - cached, 0), "cache_write": 0, "cache_read": cached,
                    "output": output})
    return (out, skipped)


def _priced(rec, table):
    from comped_core.models import UsageRecord
    from comped_core.pricing import usd_for
    usage = UsageRecord("micro", "", "", rec["at"], rec["model"], rec["input"], rec["cache_write"],
                        rec["cache_read"], rec["output"], 0, "", False, "")
    usd, resolved = usd_for(usage, table)
    out = dict(rec)
    out["usd"] = str(Decimal(usd).quantize(Decimal("0.000001")))
    out["resolved"] = resolved
    out["tokens"] = rec["input"] + rec["cache_write"] + rec["cache_read"] + rec["output"]
    cached = rec["cache_read"]
    total_in = rec["input"] + rec["cache_write"] + cached
    out["cache_pct"] = int(round(cached * 100.0 / total_in)) if total_in else 0
    return out


def last_turn(dirs, table):
    """The newest usage record in the newest transcript, priced. None when there is nothing to read."""
    path = newest_transcript(dirs)
    if path is None:
        return None
    records, skipped = records_from(path)
    if not records:
        return None
    out = _priced(records[-1], table)
    out["source"] = str(path)
    out["skipped_lines"] = skipped
    out["turns_in_tail"] = len(records)
    return out


def today_total(dirs, table, now, tz=None):
    """Today's spend, still by tail. Only files touched today are opened at all."""
    tz = tz or tz_of()
    today = day(now, tz)
    start = (now - timedelta(days=2)).timestamp()
    usd, turns, first, last, models = Decimal("0"), 0, None, None, {}
    for path in recent_transcripts(dirs, start):
        records, _skipped = records_from(path)
        for rec in records:
            at = now_utc(rec["at"]) if rec["at"] else None
            if at is None or day(at, tz) != today:
                continue
            priced = _priced(rec, table)
            usd += Decimal(priced["usd"])
            turns += 1
            first = at if first is None or at < first else first
            last = at if last is None or at > last else last
            if priced["resolved"]:
                models[priced["resolved"]] = models.get(priced["resolved"], 0) + 1
    return {"usd": str(usd.quantize(Decimal("0.000001"))), "turns": turns,
            "first_at": first, "last_at": last, "models": models}
