from pathlib import Path

from . import claude_code, codex, pi, opencode
from ..models import Ledger
from ..timeutil import iso
from ..ledger import attribute_turns

ADAPTERS = {
    "claude-code": (claude_code, "claude_dir"),
    "codex": (codex, "codex_dir"),
    "pi": (pi, "pi_dir"),
    "opencode": (opencode, "opencode_dir"),
}


def parse_all(config: dict) -> Ledger:
    records, humans, tools, sources = [], [], [], []
    for harness in sorted(ADAPTERS):
        mod, key = ADAPTERS[harness]
        r, h, t, s = mod.parse(Path(str(config.get(key) or "")), config["since"],
                               bool(config.get("include_subagents", True)), bool(config.get("redact", True)))
        records += r
        humans += h
        tools += t
        sources.append(s)
    led = Ledger(sorted(records, key=lambda r: (r.harness, r.session_id, r.timestamp, r.record_id)),
                 sorted(humans, key=lambda h: (h.harness, h.session_id, h.timestamp, h.message_id)),
                 sorted(tools, key=lambda t: (t.harness, t.session_id, t.timestamp, t.event_id)),
                 sources, iso(config["now"]))
    attribute_turns(led)
    return led
