#!/usr/bin/env python3
"""Derive synthetic fixtures from real logs. Keeps structure, token counts, models, timestamps (shifted), dedup pattern,
subagent layout. Replaces all text with deterministic lorem seeded by the text's hash. Replaces paths with /home/demo/project-N.
Usage: python3 tools/make_fixtures.py claude ~/.claude/projects 3   (3 = number of sessions to sample)"""
import json, sys, hashlib, random, pathlib, datetime

WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo "
         "sierra tango uniform victor whiskey xray yankee zulu build test deploy fix rename refactor push commit").split()
REPEATS = ["push it to prod", "merge and push to main and then save-context", "create a post for the launch with all metrics",
           "fix the failing test and rerun", "update the readme with the new commands"]
SHIFT = datetime.timedelta(days=0)
# Structural string values we must preserve verbatim live under keys not listed here; everything textual is lorem'd.
TEXT_KEYS = ("text", "content", "message", "command", "description", "prompt", "output", "file_path", "summary",
             "title", "old_string", "new_string", "error", "stdout", "stderr", "note", "reason",
             "arguments", "instructions", "query", "pattern", "url", "thinking", "signature", "encrypted_content")


def lorem(text: str, n=None) -> str:
    rnd = random.Random(hashlib.sha256(text.encode("utf-8", "replace")).hexdigest())
    n = n or min(max(3, len(text.split()) // 3), 40)
    return " ".join(rnd.choice(WORDS) for _ in range(n))


def clean_path(p: str, table: dict) -> str:
    if p not in table:
        table[p] = "/home/demo/project-{0}".format(len(table) + 1)
    return table[p]


def scrub(obj, table, is_human=False):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # Some maps are keyed by content, not by a field name (e.g. AskUserQuestion answers are
            # keyed by the question text). Anything key-shaped is short and separator-free; the rest is prose.
            if isinstance(k, str) and (" " in k or "/" in k or len(k) > 40):
                out[lorem(k)] = scrub(v, table)
                continue
            if k in ("cwd",):
                out[k] = clean_path(str(v), table)
            elif k in TEXT_KEYS and isinstance(v, str):
                out[k] = v if v.startswith("<system") else lorem(v)
            elif k == "gitBranch":
                out[k] = "main"
            else:
                out[k] = scrub(v, table)
        return out
    if isinstance(obj, list):
        return [scrub(x, table) for x in obj]
    if isinstance(obj, str):
        if obj.startswith("/Users/") or obj.startswith("/home/"):
            return clean_path(obj, table)
        # Prose, paths and anything with a separator get lorem'd. Structural tokens (ids, types,
        # model names, roles) have no spaces and no slashes, so they survive untouched.
        if " " in obj or "/" in obj:
            return lorem(obj)
        return obj
    return obj


def claude(src: pathlib.Path, n: int, dst=pathlib.Path("resources/fixtures/claude")):
    table = {}
    files = sorted(src.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    sized = [f for f in files if 20000 < f.stat().st_size < 900000]
    # Always include one session that dispatched subagents so the fixture set exercises the sidechain
    # layout; those sessions run long, so take the smallest one rather than the most recent.
    withsub = sorted((f for f in files if f.stat().st_size > 20000 and (f.parent / f.stem / "subagents").is_dir()),
                     key=lambda p: p.stat().st_size)[:1]
    picked = (withsub + [f for f in sized if f not in withsub])[:n]
    for i, f in enumerate(picked):
        proj = dst / "-home-demo-project-{0}".format(i + 1)
        proj.mkdir(parents=True, exist_ok=True)
        rows = []
        k = 0
        for line in open(f, errors="replace"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            o = scrub(o, table)
            if o.get("type") == "user" and isinstance(o.get("message", {}).get("content"), str):
                if k % 2 == 0:
                    o["message"]["content"] = REPEATS[k % len(REPEATS)]   # plant repeats deterministically
                k += 1
            rows.append(o)
        (proj / "{0}.jsonl".format(f.stem)).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        sub = f.parent / f.stem / "subagents"
        if sub.is_dir():
            (proj / f.stem / "subagents").mkdir(parents=True, exist_ok=True)
            for sf in sorted(sub.glob("agent-*.jsonl"))[:2]:
                rows = [scrub(json.loads(l), table) for l in open(sf, errors="replace") if l.strip().startswith("{")]
                (proj / f.stem / "subagents" / sf.name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print("claude fixtures: {0} sessions -> {1}".format(len(picked), dst))


def codex(src: pathlib.Path, n: int, dst=pathlib.Path("resources/fixtures/codex/2026/09/01")):
    table = {}
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_size, reverse=True)[:n]
    for i, f in enumerate(files):
        rows = []
        k = 0
        for line in open(f, errors="replace"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get("payload", {})
            if o.get("type") == "session_meta":
                p.pop("base_instructions", None)
                p["id"] = "demo-sess-{0}".format(i + 1)
            if o.get("type") == "turn_context":
                p.pop("collaboration_mode", None)
            if o.get("type") == "response_item" and p.get("type") == "reasoning":
                p["encrypted_content"] = ""
            o = scrub(o, table)
            if o.get("type") == "event_msg" and o.get("payload", {}).get("type") == "user_message":
                o["payload"]["message"] = REPEATS[k % len(REPEATS)]
                k += 1
            o["timestamp"] = "2026-09-01" + str(o.get("timestamp", ""))[10:]
            rows.append(o)
        (dst / "rollout-2026-09-01T08-00-0{0}-demo-sess-{1}.jsonl".format(i, i + 1)).write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n")
    print("codex fixtures: {0} sessions -> {1}".format(len(files), dst))


def probe(src: pathlib.Path, n: int):
    """Report what layouts actually exist under a real log root, without copying any content out."""
    sessions = sorted(src.glob("*/*.jsonl"))
    subs = [f for f in sessions if (f.parent / f.stem / "subagents").is_dir()]
    rollouts = sorted(src.glob("*/*/*/rollout-*.jsonl"))
    print("sessions: {0}".format(len(sessions)))
    print("sessions with a subagents/ dir: {0}".format(len(subs)))
    print("agent-*.jsonl files: {0}".format(sum(len(list((f.parent / f.stem / 'subagents').glob('agent-*.jsonl'))) for f in subs)))
    print("codex rollout files: {0}".format(len(rollouts)))


if __name__ == "__main__":
    kind, src, n = sys.argv[1], pathlib.Path(sys.argv[2]).expanduser(), int(sys.argv[3])
    {"claude": claude, "codex": codex, "probe": probe}[kind](src, n)
