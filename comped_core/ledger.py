import json, bisect, dataclasses
from pathlib import Path
from typing import List

from .models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger
from . import SCHEMA_VERSION


def attribute_turns(led: Ledger) -> None:
    idx = {}
    for h in led.humans:
        if h.origin == "human":
            idx.setdefault((h.harness, h.session_id), []).append((h.timestamp, h.message_id))
    for k in idx:
        idx[k].sort()

    def turn_for(harness, sid, ts):
        arr = idx.get((harness, sid))
        if not arr:
            return "{0}:pre".format(sid)
        i = bisect.bisect_right([a[0] for a in arr], ts)
        return arr[i - 1][1] if i else "{0}:pre".format(sid)

    led.records = [dataclasses.replace(r, turn_id=turn_for(r.harness, r.session_id, r.timestamp)) for r in led.records]
    led.tools = [dataclasses.replace(t, turn_id=turn_for(t.harness, t.session_id, t.timestamp)) for t in led.tools]


def summary(led: Ledger) -> dict:
    return {"schema_version": SCHEMA_VERSION, "generated_at": led.generated_at, "records": len(led.records), "humans": len(led.humans),
            "human_typed": sum(1 for h in led.humans if h.origin == "human"), "tools": len(led.tools),
            "tool_errors": sum(1 for t in led.tools if t.is_error), "sessions": len({(r.harness, r.session_id) for r in led.records}),
            "subagent_records": sum(1 for r in led.records if r.is_subagent),
            "sources": [dataclasses.asdict(s) for s in led.sources]}


def write_ledger(led: Ledger, out_dir: Path) -> List[str]:
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "ledger.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for kind, items in (("record", led.records), ("human", led.humans), ("tool", led.tools)):
            for it in items:
                row = {"kind": kind}
                row.update(dataclasses.asdict(it))
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    s = out_dir / "ledger-summary.json"
    s.write_text(json.dumps(summary(led), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return [str(p), str(s)]


def read_ledger(out_dir: Path) -> Ledger:
    out_dir = Path(out_dir).expanduser()
    recs, hums, tools = [], [], []
    types = {"record": (recs, UsageRecord), "human": (hums, HumanMessage), "tool": (tools, ToolEvent)}
    for line in open(out_dir / "ledger.jsonl", encoding="utf-8"):
        o = json.loads(line)
        kind = o.pop("kind")
        bucket, cls = types[kind]
        bucket.append(cls(**o))
    s = json.loads((out_dir / "ledger-summary.json").read_text(encoding="utf-8"))
    return Ledger(recs, hums, tools, [Source(**x) for x in s.get("sources", [])], s.get("generated_at", ""))
