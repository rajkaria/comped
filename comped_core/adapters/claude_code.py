from pathlib import Path
from datetime import datetime
from typing import List, Tuple

from ..models import UsageRecord, HumanMessage, ToolEvent, Source
from ..jsonl import iter_jsonl, JsonlStats
from ..timeutil import parse_ts, iso
from ..redact import redact

HARNESS = "claude-code"
SKIP_DIRS = {"memory", "tool-results", "workflows"}
AUTOMATED_PREFIXES = ("<", "You are ", "you are ")


def _iter_files(root: Path, include_subagents: bool):
    for proj in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(proj.glob("*.jsonl")):
            yield f, False
        if include_subagents:
            for sess in sorted(p for p in proj.iterdir() if p.is_dir() and p.name not in SKIP_DIRS):
                for f in sorted((sess / "subagents").glob("agent-*.jsonl")):
                    yield f, True


def _summ(inp) -> str:
    if isinstance(inp, dict):
        for k in ("command", "file_path", "pattern", "query", "url", "description", "prompt"):
            if k in inp and isinstance(inp[k], str):
                return " ".join(inp[k].split())[:80]
        return " ".join(str(inp).split())[:80]
    return " ".join(str(inp or "").split())[:80]


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _err_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return str(content or "")


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
    seen = set()
    synthetic = 0
    for f, is_sub in _iter_files(root, include_subagents):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=since.tzinfo) < since:
                continue
        except OSError:
            continue
        src.files += 1
        stats = JsonlStats()
        tool_names = {}   # tool_use_id -> (name, input_summary)
        pending = []      # tool events awaiting their tool_use id; a result can precede its declaration
        for _, o in iter_jsonl(f, stats):
            t = o.get("type")
            ts = parse_ts(o.get("timestamp"))
            sid = str(o.get("sessionId") or f.stem)
            proj = str(o.get("cwd") or f.parent.name)
            msg = o.get("message") if isinstance(o.get("message"), dict) else {}
            if t == "assistant":
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_names[b.get("id")] = (str(b.get("name") or "tool"), _summ(b.get("input")))
                u = msg.get("usage")
                if not isinstance(u, dict) or ts is None or ts < since:
                    continue
                model = str(msg.get("model") or "")
                if model == "<synthetic>":
                    synthetic += 1
                    continue
                key = "{0}|{1}".format(msg.get("id") or o.get("uuid"), o.get("requestId") or "")
                if key in seen:
                    src.duplicates += 1
                    continue
                seen.add(key)
                det = u.get("output_tokens_details") if isinstance(u.get("output_tokens_details"), dict) else {}
                recs.append(UsageRecord(HARNESS, sid, key, iso(ts), model,
                    int(u.get("input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0),
                    int(u.get("cache_read_input_tokens") or 0), int(u.get("output_tokens") or 0),
                    int(det.get("thinking_tokens") or 0), proj, bool(is_sub or o.get("isSidechain")), ""))
            elif t == "user" and not is_sub:
                if ts is None or ts < since or o.get("isSidechain"):
                    continue
                content = msg.get("content")
                if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            err = bool(b.get("is_error"))
                            pending.append((b.get("tool_use_id"),
                                            ToolEvent(HARNESS, sid, str(o.get("uuid") or "{0}:{1}".format(f.stem, stats.lines)), iso(ts),
                                                      "tool", "", err,
                                                      " ".join(_err_text(b.get("content")).split())[:300] if err else "", "")))
                    continue
                text = _text_of(content)
                if not text.strip() or o.get("isMeta"):
                    continue
                origin = (o.get("origin") or {}).get("kind") if isinstance(o.get("origin"), dict) else None
                if origin is None:
                    origin = "automated" if text.lstrip().startswith(AUTOMATED_PREFIXES) or "[Request interrupted" in text else "unknown"
                elif origin != "human":
                    origin = "automated"
                stored, h = redact(text, redact_on)
                humans.append(HumanMessage(HARNESS, sid, str(o.get("uuid") or "{0}:{1}".format(f.stem, stats.lines)), iso(ts), stored, h, proj, origin))
        # Resolve tool names once the whole file is read: a tool_result may appear before the tool_use that names it.
        for tool_use_id, ev in pending:
            name, summ = tool_names.get(tool_use_id, ("tool", ""))
            tools.append(ToolEvent(ev.harness, ev.session_id, ev.event_id, ev.timestamp, name, summ,
                                   ev.is_error, ev.error_text, ev.turn_id))
        src.lines += stats.lines
        src.parsed += stats.parsed
        src.unparsed += stats.unparsed
        if stats.note:
            src.note = (src.note + "; " + stats.note).strip("; ")
    if synthetic:
        src.note = (src.note + "; {0} synthetic lines skipped".format(synthetic)).strip("; ")
    return recs, humans, tools, src
