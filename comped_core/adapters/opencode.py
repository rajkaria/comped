import json
from pathlib import Path
from datetime import datetime

from ..models import UsageRecord, HumanMessage, Source
from ..timeutil import parse_ts, iso
from ..redact import redact

HARNESS = "opencode"


def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool):
    src = Source(HARNESS, str(root), note="best-effort adapter; schema from public docs")
    recs = []
    humans = []
    tools = []
    base = Path(root).expanduser() / "message"
    if not base.is_dir():
        src.note += "; directory not found"
        return recs, humans, tools, src
    src.found = True
    for f in sorted(base.rglob("*.json")):
        src.files += 1
        src.lines += 1
        try:
            o = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            src.unparsed += 1
            continue
        if not isinstance(o, dict):
            src.unparsed += 1
            continue
        src.parsed += 1
        ts = parse_ts((o.get("time") or {}).get("created"))
        if ts is None or ts < since:
            continue
        sid = str(o.get("sessionID") or f.parent.name)
        if o.get("role") == "assistant" and isinstance(o.get("tokens"), dict):
            t = o["tokens"]
            c = t.get("cache") or {}
            recs.append(UsageRecord(HARNESS, sid, str(o.get("id") or f.stem), iso(ts), str(o.get("modelID") or ""),
                int(t.get("input") or 0), int(c.get("write") or 0), int(c.get("read") or 0), int(t.get("output") or 0),
                int(t.get("reasoning") or 0), str((o.get("path") or {}).get("cwd") or ""), False, ""))
        elif o.get("role") == "user":
            text = "\n".join(p.get("text", "") for p in o.get("parts") or [] if isinstance(p, dict) and p.get("type") == "text")
            if text.strip():
                stored, h = redact(text, redact_on)
                humans.append(HumanMessage(HARNESS, sid, str(o.get("id") or f.stem), iso(ts), stored, h, "", "human"))
    return recs, humans, tools, src
