import json, re
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

from ..models import UsageRecord, HumanMessage, ToolEvent, Source
from ..jsonl import iter_jsonl, JsonlStats
from ..timeutil import parse_ts, iso
from ..redact import redact

HARNESS = "codex"
_EXIT = re.compile(r"Process exited with code (\d+)")


def _summ_args(args) -> str:
    try:
        d = json.loads(args) if isinstance(args, str) else (args or {})
    except ValueError:
        return " ".join(str(args).split())[:80]
    if isinstance(d, dict):
        for k in ("cmd", "command", "path", "query", "pattern"):
            if k in d:
                return " ".join(str(d[k]).split())[:80]
    return " ".join(str(d).split())[:80]


def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool) -> Tuple[List[UsageRecord], List[HumanMessage], List[ToolEvent], Source]:
    src = Source(HARNESS, str(root))
    recs: List[UsageRecord] = []
    humans: List[HumanMessage] = []
    tools: List[ToolEvent] = []
    root = Path(root).expanduser()
    if not root.is_dir():
        src.note = "directory not found"
        return recs, humans, tools, src
    src.found = True
    resets = 0
    for f in sorted(root.glob("*/*/*/rollout-*.jsonl")):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=since.tzinfo) < since:
                continue
        except OSError:
            continue
        src.files += 1
        stats = JsonlStats()
        sid = f.stem
        proj = ""
        model = ""
        prev = None
        calls = {}
        for _, o in iter_jsonl(f, stats):
            t = o.get("type")
            p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
            ts = parse_ts(o.get("timestamp"))
            if t == "session_meta":
                sid = str(p.get("id") or sid)
                proj = str(p.get("cwd") or proj)
                continue
            if t == "turn_context":
                model = str(p.get("model") or model)
                proj = str(p.get("cwd") or proj)
                continue
            if ts is None or ts < since:
                continue
            if t == "event_msg":
                pt = p.get("type")
                if pt == "user_message":
                    text = str(p.get("message") or "")
                    if text.strip():
                        stored, h = redact(text, redact_on)
                        humans.append(HumanMessage(HARNESS, sid, "{0}:{1}".format(sid, stats.lines), iso(ts), stored, h, proj, "human"))
                elif pt == "token_count":
                    tot = ((p.get("info") or {}).get("total_token_usage")) or {}
                    cur = tuple(int(tot.get(k) or 0) for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"))
                    if prev is None or any(c < q for c, q in zip(cur, prev)):
                        if prev is not None:
                            resets += 1
                        d = cur
                    else:
                        d = tuple(c - q for c, q in zip(cur, prev))
                    prev = cur
                    if d == (0, 0, 0, 0):
                        src.duplicates += 1
                        continue
                    inp, cached, out, reas = d
                    recs.append(UsageRecord(HARNESS, sid, "{0}:{1}".format(sid, stats.lines), iso(ts), model,
                                            max(inp - cached, 0), 0, cached, out, reas, proj, False, ""))
            elif t == "response_item":
                pt = p.get("type")
                if pt == "function_call":
                    calls[p.get("call_id")] = (str(p.get("name") or "tool"), _summ_args(p.get("arguments")))
                elif pt == "function_call_output":
                    name, summ = calls.get(p.get("call_id"), ("tool", ""))
                    out = str(p.get("output") or "")
                    m = _EXIT.search(out)
                    err = bool(m and m.group(1) != "0")
                    tools.append(ToolEvent(HARNESS, sid, "{0}:{1}".format(sid, stats.lines), iso(ts), name, summ, err,
                                           " ".join(out.split("Output:", 1)[-1].split())[:300] if err else "", ""))
        src.lines += stats.lines
        src.parsed += stats.parsed
        src.unparsed += stats.unparsed
    if resets:
        src.note = (src.note + "; {0} baseline reset(s) on non-monotonic counters".format(resets)).strip("; ")
    return recs, humans, tools, src
