"""Agent transcripts, read for one fact: which file the agent wrote to, and when.

Every coding agent keeps a JSONL transcript of its own session on disk, and every one of them
records the tool calls it made. That is enough to answer "when was this agent writing into this
repository", which is the only question this reader exists to serve. It deliberately reads none of
the prose: no prompt, no response, no tool output. A file path, a timestamp, a session id, the
harness and the model are the whole of what leaves this module.

Three shapes are covered, each with the quirk that makes a naive reader wrong:

Claude Code (`~/.claude/projects/<project>/<session>.jsonl`)
    Tool calls appear as `tool_use` content blocks on assistant messages. Assistant messages are
    written more than once while a response streams, so the same `tool_use` block can appear on
    several lines; the block id is stable, so it is the deduplication key. Subagents write their
    own transcripts in subdirectories of the project, and those are agent writes too, so they are
    read rather than skipped -- a Play that ignored them would undercount every parallel run.

Codex (`~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl`)
    Writes go through `apply_patch`, either as a `function_call` whose arguments carry the patch
    envelope or as a shell command with the envelope on stdin, and newer builds additionally log a
    `patch_apply_begin` event with the changed paths already broken out. All three are read. The
    cwd and the model arrive on `session_meta` / `turn_context` lines rather than on the calls
    themselves, so they are carried forward through the file.

Pi and anything else (`~/.pi/sessions/*.jsonl`)
    Read generically: any nested object that names a writing tool and carries an input object is
    taken as an edit. This is best effort and labelled as such rather than silently trusted.

A directory that does not exist is a labelled miss, not an error. A line that does not parse is
skipped and counted. A transcript half-written by a session still running reads fine up to the
truncation.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..common import Budget, Source, expand, iso, parse_date

CLAUDE_DIR = "~/.claude/projects"
CODEX_DIR = "~/.codex/sessions"
PI_DIR = "~/.pi/sessions"

# The tools that put bytes into a file. Read, Grep, Bash and friends are deliberately absent: a
# session that only looked at a repository never wrote a line into it.
WRITE_TOOLS = frozenset((
    "Edit", "MultiEdit", "Write", "NotebookEdit",
    "edit_file", "write_file", "create_file", "apply_patch",
    "str_replace_editor", "str_replace_based_edit_tool",
))

# Directories inside a Claude Code project that hold state rather than a session transcript.
SKIP_DIRS = frozenset(("memory", "tool-results", "workflows", "shell-snapshots", "statsig"))

PATCH_BEGIN = "*** Begin Patch"
_PATCH_MARKS = (("*** Add File: ", "add"), ("*** Update File: ", "update"),
                ("*** Delete File: ", "delete"))


@dataclass
class Edit:
    """One file-writing tool call, reduced to the six things attribution needs."""
    session_id: str = ""
    harness: str = ""
    model: str = ""
    repo_hint: str = ""
    path: str = ""
    timestamp: str = ""
    added: int = -1                     # -1 when the transcript does not say
    tool: str = ""
    subagent: bool = False

    def as_record(self) -> dict:
        return {"kind": "edit", "session_id": self.session_id, "harness": self.harness,
                "model": self.model, "repo_hint": self.repo_hint, "path": self.path,
                "timestamp": self.timestamp, "added": self.added, "tool": self.tool,
                "subagent": self.subagent}


@dataclass
class Stats:
    files: int = 0
    lines: int = 0
    unparsed: int = 0
    duplicates: int = 0
    notes: list = field(default_factory=list)

    def note(self) -> str:
        bits = list(self.notes)
        if self.duplicates:
            bits.append("{0} restated tool call(s) collapsed".format(self.duplicates))
        if self.unparsed:
            bits.append("{0} unreadable line(s)".format(self.unparsed))
        return "; ".join(bits)


# ---------------------------------------------------------------- entry point

def read_all(cfg: dict, budget: Budget) -> tuple:
    """Every harness this reader knows, in a fixed order. Returns (sources, edit records)."""
    cfg = cfg or {}
    sources, records = [], []
    for name, key, default, reader in (
            ("claude-code", "claude_dir", CLAUDE_DIR, read_claude),
            ("codex", "codex_dir", CODEX_DIR, read_codex),
            ("pi", "pi_dir", PI_DIR, read_pi)):
        source, edits = reader(cfg.get(key) or default, budget)
        sources.append(source)
        records += [e.as_record() for e in edits]
    records.sort(key=lambda r: (r["timestamp"], r["harness"], r["session_id"], r["path"], r["tool"]))
    return sources, records


# ---------------------------------------------------------------- Claude Code

def read_claude(root, budget: Budget) -> tuple:
    root = expand(root)
    source = Source(name="claude-code", path=str(root))
    if not root.is_dir():
        return source.miss("no transcript directory at {0}".format(root)), []
    stats, edits, seen = Stats(), [], set()
    for path, is_sub in _claude_files(root, budget):
        stats.files += 1
        model, session = "", path.stem
        for obj in _json_lines(path, stats):
            if obj.get("type") != "assistant":
                continue
            message = obj.get("message")
            message = message if isinstance(message, dict) else {}
            model = str(message.get("model") or model)
            if model == "<synthetic>":
                model = ""
            session = str(obj.get("sessionId") or session)
            stamp = _stamp(obj.get("timestamp"))
            cwd = str(obj.get("cwd") or "")
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name") or "")
                if name not in WRITE_TOOLS:
                    continue
                key = str(block.get("id") or "")
                if key:
                    # An assistant message is rewritten as it streams, so the same call is on
                    # several lines. The block id is what makes them one call.
                    if key in seen:
                        stats.duplicates += 1
                        continue
                    seen.add(key)
                for target, added in _targets(block.get("input"), name):
                    edits.append(Edit(session_id=session, harness="claude-code", model=model,
                                      repo_hint=cwd, path=target, timestamp=stamp, added=added,
                                      tool=name, subagent=bool(is_sub or obj.get("isSidechain"))))
    subs = sum(1 for e in edits if e.subagent)
    if subs:
        stats.notes.append("{0} write(s) from subagent transcripts".format(subs))
    return source.hit(len(edits), _detail(stats)), edits


def _claude_files(root: Path, budget: Budget):
    """Every session transcript under the projects directory, including subagent transcripts."""
    for project in _dirs(root):
        for path in sorted(project.glob("*.jsonl")):
            if not budget.spend(0):
                return
            yield path, False
        for sub in _dirs(project):
            if sub.name in SKIP_DIRS:
                continue
            for path in sorted(sub.rglob("*.jsonl")):
                if not budget.spend(0):
                    return
                yield path, True


# ---------------------------------------------------------------- Codex

def read_codex(root, budget: Budget) -> tuple:
    root = expand(root)
    source = Source(name="codex", path=str(root))
    if not root.is_dir():
        return source.miss("no transcript directory at {0}".format(root)), []
    stats, edits = Stats(), []
    for path in _rollouts(root, budget):
        stats.files += 1
        session, cwd, model = path.stem, "", ""
        for obj in _json_lines(path, stats):
            kind = obj.get("type")
            payload = obj.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if kind == "session_meta":
                session = str(payload.get("id") or session)
                cwd = str(payload.get("cwd") or cwd)
                continue
            if kind == "turn_context":
                model = str(payload.get("model") or model)
                cwd = str(payload.get("cwd") or cwd)
                continue
            stamp = _stamp(obj.get("timestamp"))
            found = []
            if kind == "response_item" and payload.get("type") == "function_call":
                found = _codex_call(str(payload.get("name") or ""), payload.get("arguments"))
            elif kind == "event_msg" and payload.get("type") == "patch_apply_begin":
                found = _codex_changes(payload.get("changes"))
            for target, added, tool in found:
                edits.append(Edit(session_id=session, harness="codex", model=model, repo_hint=cwd,
                                  path=target, timestamp=stamp, added=added, tool=tool))
    return source.hit(len(edits), _detail(stats)), edits


def _rollouts(root: Path, budget: Budget):
    """The dated rollout layout first, then anything else, so an older tree still reads."""
    seen = set()
    for pattern in ("*/*/*/rollout-*.jsonl", "*.jsonl", "*/*.jsonl"):
        for path in sorted(root.glob(pattern)):
            if str(path) in seen:
                continue
            seen.add(str(path))
            if not budget.spend(0):
                return
            yield path


def _codex_call(name: str, arguments) -> list:
    """A Codex tool call, reduced to (path, added, tool). Patches are read, everything else asked."""
    args = _loads(arguments)
    if name == "apply_patch" or (isinstance(args, dict) and isinstance(args.get("input"), str)
                                 and PATCH_BEGIN in args.get("input", "")):
        text = args.get("input") if isinstance(args, dict) else ""
        return [(p, n, "apply_patch") for p, n in parse_patch(str(text or ""))]
    if name in ("shell", "local_shell", "container.exec"):
        command = (args or {}).get("command") if isinstance(args, dict) else None
        joined = " ".join(str(c) for c in command) if isinstance(command, list) else str(command or "")
        if PATCH_BEGIN in joined:
            return [(p, n, "apply_patch") for p, n in parse_patch(joined)]
        return []
    if name in WRITE_TOOLS and isinstance(args, dict):
        return [(p, n, name) for p, n in _targets(args, name)]
    return []


def _codex_changes(changes) -> list:
    """`patch_apply_begin` already names every changed path; count the added lines it shows."""
    if not isinstance(changes, dict):
        return []
    out = []
    for path in sorted(changes):
        spec = changes[path]
        added = -1
        if isinstance(spec, dict):
            add = spec.get("add")
            update = spec.get("update")
            if isinstance(add, dict) and isinstance(add.get("content"), str):
                added = _count_lines(add["content"])
            elif isinstance(update, dict) and isinstance(update.get("unified_diff"), str):
                added = _added_in_diff(update["unified_diff"])
        out.append((str(path), added, "apply_patch"))
    return out


def parse_patch(text: str) -> list:
    """The paths and added-line counts inside an apply-patch envelope, in envelope order.

    A deleted file is reported with zero additions rather than dropped: the agent touched it, and
    a Play that only counted files it created would miss every deletion the agent made.
    """
    out, order, current = {}, [], ""
    for line in str(text or "").split("\n"):
        marked = False
        for prefix, _kind in _PATCH_MARKS:
            if line.startswith(prefix):
                current = line[len(prefix):].strip()
                if current and current not in out:
                    out[current] = 0
                    order.append(current)
                marked = True
                break
        if marked or not current:
            continue
        if line.startswith("*** "):                 # End Patch, End of File, a hunk marker
            continue
        if line[:1] == "+" and not line.startswith("+++"):
            out[current] = out.get(current, 0) + 1
    return [(p, out[p]) for p in order]


# ---------------------------------------------------------------- Pi and friends

def read_pi(root, budget: Budget) -> tuple:
    root = expand(root)
    source = Source(name="pi", path=str(root))
    if not root.is_dir():
        return source.miss("no transcript directory at {0}".format(root)), []
    stats, edits = Stats(), []
    stats.notes.append("best-effort reader: shape inferred, not specified")
    for path in sorted(root.rglob("*.jsonl")):
        if not budget.spend(0):
            break
        stats.files += 1
        session, model, cwd = path.stem, "", ""
        for obj in _json_lines(path, stats):
            model = str(obj.get("model") or model)
            cwd = str(obj.get("cwd") or cwd)
            session = str(obj.get("sessionId") or obj.get("session_id") or session)
            stamp = _stamp(obj.get("timestamp") or obj.get("time"))
            for name, args in _walk_tool_calls(obj, 0):
                for target, added in _targets(args, name):
                    edits.append(Edit(session_id=session, harness="pi", model=model, repo_hint=cwd,
                                      path=target, timestamp=stamp, added=added, tool=name))
    return source.hit(len(edits), _detail(stats)), edits


def _walk_tool_calls(node, depth: int):
    """Any nested object that names a writing tool and carries its input. Bounded, so a deep
    transcript cannot turn into a long walk."""
    if depth > 8:
        return
    if isinstance(node, dict):
        name = node.get("name") or node.get("tool") or node.get("toolName")
        if isinstance(name, str) and name in WRITE_TOOLS:
            for key in ("input", "arguments", "args", "parameters", "params"):
                args = _loads(node.get(key))
                if isinstance(args, dict):
                    yield name, args
                    break
        for key in sorted(node):
            for found in _walk_tool_calls(node[key], depth + 1):
                yield found
    elif isinstance(node, list):
        for item in node:
            for found in _walk_tool_calls(item, depth + 1):
                yield found


# ---------------------------------------------------------------- shared

def _targets(inp, tool: str) -> list:
    """(path, added) for one tool input. `added` is the transcript's own claim, or -1.

    The counts here are advisory. What a tool call says it wrote and what the commit actually
    added differ whenever an edit is later amended, reformatted or reverted before committing, so
    every number that reaches a percentage comes from git; these only order and label.
    """
    if not isinstance(inp, dict):
        return []
    path = ""
    for key in ("file_path", "notebook_path", "path", "filePath", "file", "target_file"):
        value = inp.get(key)
        if isinstance(value, str) and value.strip():
            path = value.strip()
            break
    if not path:
        return []
    added = -1
    if tool in ("Write", "write_file", "create_file"):
        added = _count_lines(inp.get("content") or inp.get("contents") or inp.get("text"))
    elif tool == "NotebookEdit":
        added = _count_lines(inp.get("new_source"))
    elif tool == "MultiEdit":
        edits = inp.get("edits")
        if isinstance(edits, list):
            added = sum(_count_lines(e.get("new_string")) for e in edits if isinstance(e, dict))
    elif tool in ("Edit", "edit_file", "str_replace_editor", "str_replace_based_edit_tool"):
        for key in ("new_string", "new_str", "replacement", "content"):
            if isinstance(inp.get(key), str):
                added = _count_lines(inp[key])
                break
    return [(path, added)]


def _json_lines(path: Path, stats: Stats):
    """Every JSON object in a JSONL file. A bad line is counted and skipped, never raised."""
    try:
        handle = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as exc:
        stats.notes.append("unreadable {0}: {1}".format(path.name, exc.strerror or exc))
        return
    with handle:
        try:
            for line in handle:
                stats.lines += 1
                text = line.strip()
                if not text or text[0] != "{":
                    continue
                try:
                    obj = json.loads(text)
                except ValueError:
                    stats.unparsed += 1
                    continue
                if isinstance(obj, dict):
                    yield obj
                else:
                    stats.unparsed += 1
        except (OSError, UnicodeError):
            stats.notes.append("stopped part way through {0}".format(path.name))


def _dirs(root: Path) -> list:
    try:
        return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    except (OSError, PermissionError):
        return []


def _loads(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _count_lines(text) -> int:
    if not isinstance(text, str) or not text:
        return 0
    count = text.count("\n")
    return count if text.endswith("\n") else count + 1


def _added_in_diff(diff: str) -> int:
    return sum(1 for line in str(diff or "").split("\n")
               if line[:1] == "+" and not line.startswith("+++"))


def _stamp(value) -> str:
    when = parse_date(value) if value else None
    return iso(when) if when else ""


def _detail(stats: Stats) -> str:
    parts = ["{0} transcript(s)".format(stats.files)]
    note = stats.note()
    if note:
        parts.append(note)
    return "; ".join(parts)


def default_dirs() -> dict:
    """Where each harness keeps its transcripts, so a caller can print what it looked at."""
    return {"claude-code": os.path.expanduser(CLAUDE_DIR),
            "codex": os.path.expanduser(CODEX_DIR),
            "pi": os.path.expanduser(PI_DIR)}
