import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List

from .models import Ledger, ToolEvent, HumanMessage
from .textnorm import _PATH, _NUM, _HEX, _URL

ZERO = Decimal("0")
CORRECTION = re.compile(r"\b(no,|don'?t|wrong|revert|undo|instead|not what i|that'?s not|stop|roll ?back|why did you|i said)\b|\[request interrupted", re.I)
REVERT = re.compile(r"git (revert|reset --hard|checkout -- |restore )")
TEMPLATES = [  # (pattern on signature, rule text)
    (r"no such file|enoent|not found: file|cannot find path", "Before reading or editing a path, confirm it exists (`ls` or a glob). If it does not, search for the file by name before assuming a location."),
    (r"permission denied|eacces", "Do not retry a permission-denied command verbatim. Report the path and the permission that is missing, and ask before escalating."),
    (r"command not found|not recognized as an internal", "Check the tool is installed (`which <tool>`) before invoking it; if missing, say so and propose the install command rather than retrying."),
    (r"modulenotfounderror|cannot find module|no module named", "Run the project's dependency install (`npm install`, `pip install -e .`, `uv sync`) once before running code; do not guess module names."),
    (r"tests? failed|failed tests?|assertionerror", "After a change, run the narrowest failing test first and read its assertion before editing further; do not rerun the full suite until it passes."),
    (r"typeerror|type error|is not assignable", "Run the type checker on the touched file before declaring a change done."),
    (r"timed out|timeout", "Set an explicit timeout and a smaller scope on long-running commands; do not rerun the same command unchanged after a timeout."),
    (r"merge conflict|conflict", "Before merging or rebasing, fetch and inspect divergence; resolve conflicts file by file and run tests before continuing."),
    (r"eaddrinuse|address already in use", "Check for a process on the port before starting a server, and reuse the running one if it is the same app."),
]


@dataclass
class MistakeClass:
    kind: str
    confidence: str
    tool_name: str
    signature: str
    count: int
    sessions: int
    recovery_usd: Decimal
    evidence: str
    rule_draft: str


def signature(text: str) -> str:
    first = next((ln for ln in (text or "").splitlines() if ln.strip()), "").lower()
    first = _URL.sub("<url>", first)
    first = _PATH.sub("<path>", first)
    first = _HEX.sub("<hex>", first)
    first = _NUM.sub("<num>", first)
    return " ".join(first.split())[:80]


def _rule_for(tool: str, sig: str, kind: str, count: int, sessions: int) -> str:
    for pat, text in TEMPLATES:
        if re.search(pat, sig):
            return text
    if kind == "correction":
        return ("When the user asks for a change via `{0}`, restate the intended change in one line and wait for "
                "confirmation if the request is ambiguous; this was corrected {1} times across {2} sessions.".format(tool, count, sessions))
    if kind == "revert":
        return ("Before a destructive git command (`{0}`), state what will be lost and get explicit confirmation; "
                "{1} reverts across {2} sessions.".format(sig, count, sessions))
    return "Before calling `{0}` for `{1}`, verify the precondition; this failed {2} times across {3} sessions.".format(tool, sig, count, sessions)


def _next_turn_cost(h: HumanMessage, humans_by_session: Dict, per_turn: Dict[str, Decimal]) -> Decimal:
    arr = humans_by_session.get((h.harness, h.session_id), [])
    for i, x in enumerate(arr):
        if x.message_id == h.message_id:
            return per_turn.get(arr[i + 1].message_id, ZERO) if i + 1 < len(arr) else ZERO
    return ZERO


def classify(led: Ledger, per_turn_usd: Dict[str, Decimal], min_recurrence: int, show_snippets: bool) -> List[MistakeClass]:
    hb: Dict = {}
    for h in led.humans:
        if h.origin == "human":
            hb.setdefault((h.harness, h.session_id), []).append(h)
    for k in hb:
        hb[k].sort(key=lambda h: (h.timestamp, h.message_id))
    turn_h = {h.message_id: h for arr in hb.values() for h in arr}

    def turn_cost(turn_id: str) -> Decimal:
        c = per_turn_usd.get(turn_id, ZERO)
        h = turn_h.get(turn_id)
        return c + (_next_turn_cost(h, hb, per_turn_usd) if h else ZERO)

    buckets: Dict[tuple, dict] = {}

    def add(key, kind, conf, tool, sig, sess, turn, ev):
        b = buckets.setdefault(key, {"kind": kind, "conf": conf, "tool": tool, "sig": sig, "n": 0, "sess": set(), "usd": ZERO, "ev": ev})
        b["n"] += 1
        b["sess"].add(sess)
        b["usd"] += turn_cost(turn)

    # A: tool errors, C: reverts
    for t in led.tools:
        m = REVERT.search(t.input_summary or "")
        if m:
            stem = m.group(0).strip()
            add(("revert", t.tool_name, stem), "revert", "high", t.tool_name, stem,
                (t.harness, t.session_id), t.turn_id, t.input_summary)
        if t.is_error:
            sig = signature(t.error_text)
            add(("tool_error", t.tool_name, sig), "tool_error", "high", t.tool_name, sig,
                (t.harness, t.session_id), t.turn_id, "{0}: {1} -> {2}".format(t.tool_name, t.input_summary, sig))
    # B: corrections paired with the preceding tool in the same session
    tools_by_session: Dict[tuple, List[ToolEvent]] = {}
    for t in led.tools:
        tools_by_session.setdefault((t.harness, t.session_id), []).append(t)
    for h in led.humans:
        if h.origin != "human" or not CORRECTION.search(h.text or ""):
            continue
        prev = [t for t in tools_by_session.get((h.harness, h.session_id), []) if t.timestamp <= h.timestamp]
        tool = prev[-1].tool_name if prev else "text reply"
        stem = CORRECTION.search(h.text).group(0).lower().strip()
        add(("correction", tool, stem), "correction", "medium", tool, stem,
            (h.harness, h.session_id), h.message_id, '{0} -> "{1}"'.format(tool, h.text[:80]))
    out = []
    for b in buckets.values():
        if b["n"] < int(min_recurrence) or len(b["sess"]) < 2:
            continue
        out.append(MistakeClass(b["kind"], b["conf"], b["tool"], b["sig"], b["n"], len(b["sess"]), b["usd"],
                                (" ".join(b["ev"].split())[:160] if show_snippets else "(snippets hidden)"),
                                _rule_for(b["tool"], b["sig"], b["kind"], b["n"], len(b["sess"]))))
    return sorted(out, key=lambda c: (-c.count, -c.recovery_usd, c.tool_name, c.signature))


def draft_rules(classes: List[MistakeClass], target: str) -> str:
    files = {"claude": ["CLAUDE.md"], "agents": ["AGENTS.md"], "both": ["CLAUDE.md", "AGENTS.md"]}.get(target, ["CLAUDE.md", "AGENTS.md"])
    if not classes:
        return "# Drafted rules\n\nNo recurring mistake class met the threshold. Nothing to draft.\n"
    out = ["# Drafted rules", "", "Paste the block(s) you agree with. Nothing here was applied automatically.", ""]
    for f in files:
        out += ["## For {0}".format(f), ""]
        for c in classes:
            out += ["<!-- comped wrong-turns · {0} · confidence: {1} · {2}× across {3} sessions · recovery ≈ ${4:.2f} -->".format(
                        c.kind, c.confidence, c.count, c.sessions, c.recovery_usd),
                    "- {0}".format(c.rule_draft), ""]
    return "\n".join(out)
