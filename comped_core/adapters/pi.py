from pathlib import Path
from datetime import datetime

from ..models import UsageRecord, HumanMessage, Source
from ..jsonl import iter_jsonl, JsonlStats
from ..timeutil import parse_ts, iso
from ..redact import redact

HARNESS = "pi"


def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool):
    src = Source(HARNESS, str(root), note="best-effort adapter; schema from public docs")
    recs = []
    humans = []
    tools = []
    root = Path(root).expanduser()
    if not root.is_dir():
        src.note += "; directory not found"
        return recs, humans, tools, src
    src.found = True
    for f in sorted(root.glob("*.jsonl")):
        src.files += 1
        stats = JsonlStats()
        sid = f.stem
        for _, o in iter_jsonl(f, stats):
            ts = parse_ts(o.get("timestamp") or o.get("time"))
            if ts is None or ts < since:
                continue
            role = o.get("role")
            u = o.get("usage")
            if role == "assistant" and isinstance(u, dict):
                recs.append(UsageRecord(HARNESS, sid, "{0}:{1}".format(sid, stats.lines), iso(ts), str(o.get("model") or ""),
                    int(u.get("input") or 0), int(u.get("cacheWrite") or 0), int(u.get("cacheRead") or 0), int(u.get("output") or 0),
                    int(u.get("reasoning") or 0), str(o.get("cwd") or ""), False, ""))
            elif role == "user":
                c = o.get("content")
                text = c if isinstance(c, str) else "\n".join(b.get("text", "") for b in c or [] if isinstance(b, dict))
                if text.strip():
                    stored, h = redact(text, redact_on)
                    humans.append(HumanMessage(HARNESS, sid, "{0}:{1}".format(sid, stats.lines), iso(ts), stored, h, "", "human"))
        src.lines += stats.lines
        src.parsed += stats.parsed
        src.unparsed += stats.unparsed
    return recs, humans, tools, src
