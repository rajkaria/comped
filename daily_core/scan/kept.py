"""kept: of everything the agent wrote, how much of it is still there?

Every other number an agent produces is about what it cost. This one is about what it was worth,
and it is the number nobody publishes, because git already knows it and nobody asks. The agent
wrote fourteen thousand lines last month; `git blame` will say, exactly and for free, how many of
them a stranger reading the repository today would still find.

The whole Play rests on one heuristic, and the heuristic is arguable, so it is printed verbatim on
the report rather than buried: git records who *committed* a line, never who *typed* it, so a line
is called the agent's when the commit that introduced it has an author time inside a session
window -- from the first file-writing tool call in that session to the last, plus a grace period.
That miscounts in both directions, and the two errors do not cancel. What makes the answer honest
anyway is the control group: the identical computation over the same files outside every window,
which is you. A survival rate with nothing to compare it against is a dunk, not a measurement; the
card prints both or it prints neither.

Everything expensive is bounded and every bound is reported, because a blame that was cut short
gives a lower bound and a lower bound presented as a total is a lie.
"""
import json
import re
from datetime import timedelta

from ..card import Card, legend, pad, rpad, sparkline, tier_bar
from ..common import (Budget, Source, baseline_read, baseline_write, delta, expand,
                      from_unix, iso, parse_date, pct, plural, since_note)
from ..gitread import Git, coalesce, describe, discover, own_identities
from ..parsers import agentedits
from ..parsers.blame import parse_porcelain

SOURCES = ("agent", "git")

DEFAULTS = {
    "root": "~",
    "grace_minutes": 30,
    "min_lines": 20,
    "max_repos": 200,
    "max_commits": 4000,
    "max_blame_files": 300,
    "max_seconds": 45.0,
}

# The log format. \x01 opens a commit, \x1f separates its fields, \x1e ends the header and the
# numstat rows follow. None of the three can occur in a subject, a body or a name.
LOG_FORMAT = "\x01%H\x1f%at\x1f%aN\x1f%aE\x1f%s\x1f%b\x1e"

BUCKETS = (("same day", 1), ("1 week", 7), ("1 month", 30), ("older", 10 ** 7))

HARNESS_NAMES = {"claude-code": "Claude", "codex": "Codex", "pi": "Pi"}

_REVERT_BODY = re.compile(r"This reverts commit ([0-9a-f]{7,40})")
_REVERT_SUBJECT = re.compile(r'^Revert\s+"')


def attribution_rule(grace_minutes: int) -> str:
    """The heuristic, in one paragraph, printed wherever a number from it is printed."""
    return (
        "A line is counted as the agent's when the commit that introduced it has an author time "
        "inside an agent session window for that repository. A window runs from the first "
        "file-writing tool call in a session to the last, plus {0} minutes of grace for the "
        "commit that followed. Git records who committed a line and never who typed it, so this "
        "is a time window and not a fact: a line you wrote by hand while the agent was working is "
        "counted as the agent's, and a line the agent wrote that you committed the next morning "
        "is counted as yours. The control group is the same files over the same history, outside "
        "every window, which is why both numbers are printed together and neither is printed "
        "alone.".format(grace_minutes))


# ---------------------------------------------------------------- reading

def read_source(source: str, budget: Budget, cfg: dict) -> tuple:
    """One source. `agent` reads transcripts, `git` reads the repositories they wrote into."""
    cfg = dict(cfg or {})
    if cfg.get("demo_root"):
        return _read_demo(source, cfg)
    if source == "agent":
        return agentedits.read_all(cfg, budget)
    if source == "git":
        return _read_git(cfg, budget)
    return [Source(name=source).miss("unknown source")], []


def _read_git(cfg: dict, budget: Budget) -> tuple:
    root = cfg.get("root") or DEFAULTS["root"]
    source = Source(name="git", path=str(expand(root)))
    git = Git.find()
    if not git.ok:
        return [source.miss(git.note)], []
    found = discover(root, budget, max_repos=int(cfg.get("max_repos") or DEFAULTS["max_repos"]))
    if not found:
        return [source.miss("no git repository under {0}".format(expand(root)))], []
    records, skipped = [], 0
    for path in found:
        repo = describe(git, path)
        if not repo.usable:
            skipped += 1
            continue
        records.append({"kind": "repo", "path": str(repo.path), "name": repo.name,
                        "head": repo.head, "shallow": repo.shallow, "note": repo.note})
    keys = sorted(own_identities(git, [expand(r["path"]) for r in records]))
    records.append({"kind": "own", "keys": keys})
    note = "{0} repositor(y/ies)".format(len(records) - 1)
    if skipped:
        note += "; {0} with no commits".format(skipped)
    if budget.exhausted:
        note += "; stopped at the {0} bound".format(budget.hit)
    return [source.hit(len(records) - 1, note)], records


def _read_demo(source: str, cfg: dict) -> tuple:
    """The demo reads one pre-canned document instead of a machine, so a cold run has an answer.

    A checkout has none of this: no transcripts, no session windows, and a git history whose dates
    are the dates of the clone. Replaying a recorded document is the only way the demo can show a
    survival curve that means anything.
    """
    path = expand(cfg["demo_root"]) / "kept.json"
    src = Source(name="{0} (demo)".format(source), path=str(path))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [src.miss("fixture missing or unreadable")], []
    wanted = ("edit",) if source == "agent" else ("repo", "own", "commits", "tracked", "blame")
    records = [r for r in doc.get("records", []) if isinstance(r, dict) and r.get("kind") in wanted]
    return [src.hit(len(records), "bundled fixture")], records


# ---------------------------------------------------------------- git backends

class GitBackend(object):
    """Everything the analysis asks of git, bounded and cached per (repo, path, head)."""

    def __init__(self, cfg: dict, budget: Budget):
        self.git = Git.find()
        self.max_commits = int(cfg.get("max_commits") or DEFAULTS["max_commits"])
        self.budget = budget
        self._blame = {}
        self._tracked = {}
        self.ok = self.git.ok
        self.note = "" if self.git.ok else self.git.note

    def commits(self, repo: dict) -> list:
        text = self.git.run(repo["path"], [
            "log", "--no-merges", "--numstat", "--max-count={0}".format(self.max_commits),
            "--format={0}".format(LOG_FORMAT), repo["head"]])
        return parse_log(text)

    def tracked(self, repo: dict) -> set:
        key = (repo["path"], repo["head"])
        if key not in self._tracked:
            text = self.git.run(repo["path"], ["ls-files"])
            self._tracked[key] = set(line for line in text.split("\n") if line)
        return self._tracked[key]

    def blame(self, repo: dict, path: str) -> list:
        key = (repo["path"], repo["head"], path)
        if key not in self._blame:
            text = self.git.run(repo["path"], ["blame", "--line-porcelain", repo["head"], "--", path])
            self._blame[key] = [(b.sha, b.author_time, b.author_key) for b in parse_porcelain(text)]
        return self._blame[key]


class CannedBackend(object):
    """The same three questions, answered from a recorded document. Used by the demo and by tests."""

    def __init__(self, records):
        self.ok = True
        self.note = "replayed from a recorded document"
        self._commits, self._tracked, self._blame = {}, {}, {}
        for record in records:
            repo = str(record.get("repo") or "")
            if record.get("kind") == "commits":
                self._commits[repo] = [_canned_commit(c) for c in record.get("commits") or []]
            elif record.get("kind") == "tracked":
                self._tracked[repo] = set(record.get("paths") or [])
            elif record.get("kind") == "blame":
                self._blame[repo] = record.get("lines") or {}

    def commits(self, repo: dict) -> list:
        return list(self._commits.get(repo["path"], []))

    def tracked(self, repo: dict) -> set:
        return set(self._tracked.get(repo["path"], ()))

    def blame(self, repo: dict, path: str) -> list:
        rows = (self._blame.get(repo["path"], {}) or {}).get(path) or []
        return [(str(r[0]), _time(r[1]), str(r[2]) if len(r) > 2 else "") for r in rows]


def _canned_commit(raw: dict) -> dict:
    files = []
    for entry in raw.get("files") or []:
        if isinstance(entry, dict):
            files.append({"path": str(entry.get("path") or ""), "added": int(entry.get("added") or 0),
                          "deleted": int(entry.get("deleted") or 0)})
        elif isinstance(entry, (list, tuple)) and entry:
            files.append({"path": str(entry[0]), "added": int(entry[1]) if len(entry) > 1 else 0,
                          "deleted": int(entry[2]) if len(entry) > 2 else 0})
    return {"sha": str(raw.get("sha") or ""), "at": _time(raw.get("at")),
            "name": str(raw.get("name") or ""), "email": str(raw.get("email") or ""),
            "subject": str(raw.get("subject") or ""), "body": str(raw.get("body") or ""),
            "files": files}


def _time(value):
    if value in (None, ""):
        return None
    if hasattr(value, "tzinfo"):
        return value
    try:
        return from_unix(float(value))
    except (TypeError, ValueError):
        return parse_date(str(value))


# ---------------------------------------------------------------- log parsing

def parse_log(text: str) -> list:
    """`git log --numstat` in the format above, as commit dicts. Unparseable chunks are dropped."""
    out = []
    for chunk in str(text or "").split("\x01")[1:]:
        header, _, rest = chunk.partition("\x1e")
        fields = header.split("\x1f")
        if len(fields) < 6 or not fields[0]:
            continue
        files = []
        for line in rest.split("\n"):
            parts = line.split("\t")
            if len(parts) != 3 or not parts[2]:
                continue
            files.append({"path": rename_target(parts[2]), "added": _num(parts[0]),
                          "deleted": _num(parts[1])})
        out.append({"sha": fields[0], "at": _time(fields[1]), "name": fields[2],
                    "email": fields[3], "subject": fields[4], "body": fields[5], "files": files})
    return out


def rename_target(path: str) -> str:
    """numstat writes a rename as `old => new` or `dir/{old => new}/file`. Keep where it is now."""
    if "=>" not in path:
        return path
    if "{" in path and "}" in path:
        before, _, rest = path.partition("{")
        inside, _, after = rest.partition("}")
        moved = inside.split("=>")[-1].strip()
        joined = (before + moved + after).replace("//", "/")
        return joined.strip("/") if joined.startswith("/") and not path.startswith("/") else joined
    return path.split("=>")[-1].strip()


def _num(cell: str) -> int:
    """A numstat count. `-` means a binary file, which has no lines to survive."""
    try:
        return int(cell)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- analysis

def analyse(records, now, cfg: dict) -> dict:
    cfg = dict(cfg or {})
    grace = int(cfg.get("grace_minutes") or DEFAULTS["grace_minutes"])
    # Zero is a real answer here -- "rate everything, however little of it there is" -- so it is
    # read as a setting rather than falling through to the default the way an unset key does.
    min_lines = DEFAULTS["min_lines"] if cfg.get("min_lines") is None else int(cfg["min_lines"])
    budget = cfg.get("budget") or Budget(max_seconds=float(cfg.get("max_seconds") or DEFAULTS["max_seconds"]))
    max_blame = int(cfg.get("max_blame_files") or DEFAULTS["max_blame_files"])

    records = [r for r in (records or []) if isinstance(r, dict)]
    edits = _edits(records)
    repos = sorted((r for r in records if r.get("kind") == "repo"), key=lambda r: r["path"])
    own = set()
    for record in records:
        if record.get("kind") == "own":
            own |= set(record.get("keys") or [])

    backend = _backend(records, cfg, budget)
    sessions, orphans = _sessions(edits, repos, grace)
    windows = {}
    for key in sorted(sessions):
        session = sessions[key]
        windows.setdefault(session["repo"], []).append(session)
    for path in windows:
        windows[path].sort(key=lambda s: (s["start"], s["session_id"]))

    views, notes = [], []
    if not backend.ok:
        notes.append(backend.note or "git could not be run, so nothing could be measured")
    for repo in repos:
        if not backend.ok:
            break
        views.append(_repo_view(repo, windows.get(repo["path"], []), backend, now, cfg,
                                own, min_lines, max_blame, budget))
    if budget.exhausted:
        notes.append("stopped at the {0} bound: every count below is a lower bound".format(budget.hit))

    return _combine(views, sessions, orphans, edits, repos, now, cfg, grace, min_lines,
                    budget, notes, backend)


def _edits(records) -> list:
    out = []
    for record in records:
        if record.get("kind") != "edit":
            continue
        when = parse_date(record.get("timestamp") or "")
        path = str(record.get("path") or "")
        if not when or not path:
            continue
        item = dict(record)
        item["_when"] = when
        item["_abs"] = str(expand(path)) if path.startswith(("/", "~")) else path
        out.append(item)
    return sorted(out, key=lambda e: (e["_when"], e["session_id"], e["path"]))


def _sessions(edits, repos, grace: int) -> tuple:
    """One window per (session, repository), from the first write to the last plus the grace."""
    paths = sorted((r["path"] for r in repos), key=len, reverse=True)
    sessions, orphans = {}, {}
    for edit in edits:
        repo = _repo_for(edit["_abs"], paths) or _repo_for(str(expand(edit.get("repo_hint") or "")), paths)
        if not repo:
            orphans.setdefault(edit["session_id"], 0)
            orphans[edit["session_id"]] += 1
            continue
        key = (repo, edit["session_id"])
        session = sessions.get(key)
        if session is None:
            session = {"repo": repo, "session_id": edit["session_id"], "harness": edit.get("harness", ""),
                       "model": edit.get("model", ""), "start": edit["_when"], "end": edit["_when"],
                       "writes": 0, "files": set(), "claimed": 0}
            sessions[key] = session
        session["start"] = min(session["start"], edit["_when"])
        session["end"] = max(session["end"], edit["_when"])
        session["writes"] += 1
        session["files"].add(_relative(edit["_abs"], repo))
        if int(edit.get("added") or -1) > 0:
            session["claimed"] += int(edit["added"])
        if not session["model"] and edit.get("model"):
            session["model"] = edit["model"]
    for session in sessions.values():
        session["window_end"] = session["end"] + timedelta(minutes=grace)
    return sessions, orphans


def _repo_for(path: str, repo_paths) -> str:
    for repo in repo_paths:                          # longest first: a nested repo wins
        if path == repo or path.startswith(repo.rstrip("/") + "/"):
            return repo
    return ""


def _relative(path: str, repo: str) -> str:
    return path[len(repo.rstrip("/")) + 1:] if path.startswith(repo.rstrip("/") + "/") else path


def _backend(records, cfg: dict, budget: Budget):
    canned = [r for r in records if r.get("kind") in ("commits", "tracked", "blame")]
    if canned or cfg.get("demo_root"):
        return CannedBackend(canned)
    return GitBackend(cfg, budget)


def _window_index(when, sessions) -> int:
    """The first session whose window contains this instant, or -1. Overlaps go to the earlier."""
    if when is None:
        return -1
    for i, session in enumerate(sessions):
        if session["start"] <= when <= session["window_end"]:
            return i
    return -1


# ---------------------------------------------------------------- one repository

def _repo_view(repo, sessions, backend, now, cfg, own, min_lines, max_blame, budget) -> dict:
    commits = backend.commits(repo)
    max_commits = int(cfg.get("max_commits") or DEFAULTS["max_commits"])
    truncated = len(commits) >= max_commits
    identities = coalesce([(c["name"], c["email"]) for c in commits])
    bots = {key for key, ident in identities.items() if ident.is_bot}

    from ..gitread import identity_key
    by_sha = {}
    for commit in commits:
        commit["key"] = identity_key(commit["name"], commit["email"])
        commit["bot"] = commit["key"] in bots
        commit["window"] = _window_index(commit["at"], sessions)
        commit["age"] = _age(commit["at"], now)
        by_sha[commit["sha"]] = commit

    # The file set is the one the agent touched. The control group is the same files, which is the
    # only comparison that holds churn, language and review pressure constant between the two.
    agent_files, human_files, own_files, bot_files = {}, {}, {}, {}
    for commit in commits:
        for entry in commit["files"]:
            if commit["window"] >= 0:
                agent_files[entry["path"]] = agent_files.get(entry["path"], 0) + max(0, entry["added"])
    for commit in commits:
        if commit["window"] >= 0:
            continue
        for entry in commit["files"]:
            if entry["path"] not in agent_files:
                continue
            added = max(0, entry["added"])
            target = bot_files if commit["bot"] else human_files
            target[entry["path"]] = target.get(entry["path"], 0) + added
            if not commit["bot"] and commit["key"] in own:
                own_files[entry["path"]] = own_files.get(entry["path"], 0) + added

    tracked = backend.tracked(repo)
    live = sorted(p for p in agent_files if p in tracked)
    deleted = sorted(p for p in agent_files if p not in tracked)

    blamed, unmeasured = [], []
    alive = {"agent": 0, "human": 0, "you": 0, "bot": 0}
    per_file, per_harness, per_model = {}, {}, {}
    bucket_alive = [0] * len(BUCKETS)
    human_bucket_alive = [0] * len(BUCKETS)
    day_alive = {}
    for path in live:
        if len(blamed) >= max_blame or budget.exhausted:
            unmeasured.append(path)
            continue
        lines = backend.blame(repo, path)
        budget.spend(len(lines))
        blamed.append(path)
        counted = 0
        for sha, when, key in lines:
            commit = by_sha.get(sha)
            at = commit["at"] if commit and commit["at"] else when
            index = commit["window"] if commit else _window_index(at, sessions)
            is_bot = commit["bot"] if commit else False
            age = _age(at, now)
            if index >= 0:
                alive["agent"] += 1
                counted += 1
                bucket_alive[_bucket(age)] += 1
                day_alive[age] = day_alive.get(age, 0) + 1
                session = sessions[index]
                _add(per_harness, session["harness"] or "unknown", 0, 1)
                _add(per_model, session["model"] or "(model not named)", 0, 1)
            elif is_bot:
                alive["bot"] += 1
            else:
                alive["human"] += 1
                human_bucket_alive[_bucket(age)] += 1
                if key in own:
                    alive["you"] += 1
        per_file[path] = {"path": path, "ever": agent_files.get(path, 0), "alive": counted,
                          "deleted": False}
    for path in deleted:
        per_file[path] = {"path": path, "ever": agent_files.get(path, 0), "alive": 0, "deleted": True}

    measured = set(blamed) | set(deleted)
    ever = {
        "agent": sum(agent_files.get(p, 0) for p in measured),
        "human": sum(human_files.get(p, 0) for p in measured),
        "you": sum(own_files.get(p, 0) for p in measured),
        "bot": sum(bot_files.get(p, 0) for p in measured),
    }
    bucket_ever = [0] * len(BUCKETS)
    human_bucket_ever = [0] * len(BUCKETS)
    day_ever = {}
    for commit in commits:
        added = sum(max(0, e["added"]) for e in commit["files"] if e["path"] in measured)
        if not added:
            continue
        index = _bucket(commit["age"])
        if commit["window"] >= 0:
            bucket_ever[index] += added
            day_ever[commit["age"]] = day_ever.get(commit["age"], 0) + added
            session = sessions[commit["window"]]
            _add(per_harness, session["harness"] or "unknown", added, 0)
            _add(per_model, session["model"] or "(model not named)", added, 0)
        elif not commit["bot"]:
            human_bucket_ever[index] += added

    reverts = _reverts(commits, by_sha, measured)
    # Each in-window commit's additions belong to exactly one class, decided at the commit, so a
    # line that was reverted out of a file that was later deleted is never counted twice.
    undone = set(reverts["shas"])
    deleted_set, reverted_lines, deleted_lines = set(deleted), 0, 0
    for commit in commits:
        if commit["window"] < 0:
            continue
        was_undone = commit["sha"] in undone
        for entry in commit["files"]:
            if entry["path"] not in measured:
                continue
            added = max(0, entry["added"])
            if was_undone:
                reverted_lines += added
            elif entry["path"] in deleted_set:
                deleted_lines += added

    written_files = set()
    for session in sessions:
        written_files |= set(session["files"])
    never_committed = sorted(p for p in written_files if p and p not in agent_files)

    return {
        "path": repo["path"], "name": repo["name"], "head": repo["head"],
        "shallow": bool(repo.get("shallow")),
        "sessions": len(sessions), "commits": len(commits),
        "in_window": sum(1 for c in commits if c["window"] >= 0),
        "ever": ever, "alive": alive,
        "deleted_files": len(deleted), "deleted_lines": deleted_lines,
        "deleted_lines_total": sum(agent_files.get(p, 0) for p in deleted),
        "reverted_lines": reverted_lines,
        "unmeasured_files": len(unmeasured), "unmeasured_lines": sum(agent_files.get(p, 0) for p in unmeasured),
        "blamed_files": len(blamed), "touched_files": len(agent_files),
        "never_committed": never_committed,
        "buckets": {"agent_ever": bucket_ever, "agent_alive": bucket_alive,
                    "human_ever": human_bucket_ever, "human_alive": human_bucket_alive},
        "days": {"ever": day_ever, "alive": day_alive},
        "files": [per_file[p] for p in sorted(per_file)],
        "harness": per_harness, "model": per_model,
        "reverts": reverts,
        "truncated": truncated,
        "confidence": _confidence(repo, sessions, commits, truncated, unmeasured, min_lines),
    }


def _reverts(commits, by_sha, measured) -> dict:
    """Commits that were undone, and the agent-written lines that went with them.

    A revert is the one kind of churn git states outright rather than leaving to be inferred, so it
    is worth separating: a line that was rewritten six weeks later is a codebase moving on, and a
    line reverted the same afternoon is work that should never have been done.
    """
    prefixes, subjects = {}, {}
    for sha, commit in by_sha.items():
        for length in (7, 8, 10, 12, 40):
            prefixes.setdefault(sha[:length], sha)
        subjects.setdefault(commit["subject"], sha)
    found, lines, same_day, shas = [], 0, 0, set()
    for commit in sorted(commits, key=lambda c: c["sha"]):
        target = _revert_target(commit, prefixes, subjects)
        if not target or target not in by_sha or target == commit["sha"] or target in shas:
            continue
        undone = by_sha[target]
        if undone["window"] < 0:
            continue
        cost = sum(max(0, e["added"]) for e in undone["files"] if e["path"] in measured)
        hours = -1.0
        if commit["at"] and undone["at"]:
            hours = round((commit["at"] - undone["at"]).total_seconds() / 3600.0, 1)
        if 0 <= hours <= 24:
            same_day += 1
        lines += cost
        shas.add(target)
        found.append({"sha": target[:8], "subject": undone["subject"][:60], "lines": cost,
                      "hours": hours, "by_agent": commit["window"] >= 0})
    found.sort(key=lambda r: (-r["lines"], r["sha"]))
    return {"count": len(found), "lines": lines, "same_day": same_day, "items": found[:6],
            "shas": sorted(shas)}


def _revert_target(commit: dict, prefixes: dict, subjects: dict) -> str:
    """The commit this one undoes: the sha git writes into the body, or the subject it quotes.

    `git revert` writes `This reverts commit <sha>` and that is the reliable signal. A hand-written
    `Revert "..."` with no body is the common second case, and quoting the original subject is the
    only handle it leaves; matching on it is a guess, so it is only accepted when exactly one
    commit in the history carries that subject.
    """
    match = _REVERT_BODY.search(commit.get("body") or "")
    if match:
        reference = match.group(1)
        for length in (40, 12, 10, 8, 7):
            found = prefixes.get(reference[:length])
            if found:
                return found
        return ""
    subject = commit.get("subject") or ""
    if _REVERT_SUBJECT.match(subject):
        quoted = subject.split('"', 1)[1].rsplit('"', 1)[0] if subject.count('"') >= 2 else ""
        return subjects.get(quoted, "") if quoted else ""
    return ""


def _confidence(repo, sessions, commits, truncated, unmeasured, min_lines) -> dict:
    """How much weight this repository's number can carry, and why."""
    total = len(commits)
    in_window = sum(1 for c in commits if c["window"] >= 0)
    coverage = (in_window / float(total)) if total else 0.0
    if not sessions or not in_window:
        return {"level": "none", "coverage": 0,
                "why": "no agent session maps to this repository"}
    reasons, level = [], "high"
    if coverage > 0.85:
        level = "low"
        reasons.append("{0}% of all commits fall inside a session window, so the window barely "
                       "distinguishes anything".format(int(round(coverage * 100))))
    elif coverage > 0.5:
        level = "medium"
        reasons.append("{0}% of commits fall inside a window".format(int(round(coverage * 100))))
    if repo.get("shallow"):
        level = "low"
        reasons.append("shallow clone: history is truncated")
    if truncated:
        level = "low" if level != "none" else level
        reasons.append("the commit bound was reached, so older history was not read")
    if unmeasured:
        level = "medium" if level == "high" else level
        reasons.append("{0} file(s) were not blamed within the bound".format(len(unmeasured)))
    if in_window < 2:
        level = "medium" if level == "high" else level
        reasons.append("only {0} in-window commit".format(in_window))
    if not reasons:
        reasons.append("full history read, {0}% of commits in a window".format(
            int(round(coverage * 100))))
    return {"level": level, "coverage": int(round(coverage * 100)), "why": "; ".join(reasons)}


def _add(table: dict, key: str, ever: int, alive: int):
    row = table.setdefault(key, {"ever": 0, "alive": 0})
    row["ever"] += ever
    row["alive"] += alive


def _age(when, now) -> int:
    if not when:
        return 0
    return max(0, int((now - when).total_seconds() // 86400))


def _bucket(age: int) -> int:
    for i, (_label, edge) in enumerate(BUCKETS):
        if age < edge:
            return i
    return len(BUCKETS) - 1


# ---------------------------------------------------------------- combining

def _combine(views, sessions, orphans, edits, repos, now, cfg, grace, min_lines, budget,
             notes, backend) -> dict:
    ever = {"agent": 0, "human": 0, "you": 0, "bot": 0}
    alive = {"agent": 0, "human": 0, "you": 0, "bot": 0}
    for view in views:
        for key in ever:
            ever[key] += view["ever"][key]
            alive[key] += view["alive"][key]

    deleted_files = sum(v["deleted_files"] for v in views)
    deleted_total = sum(v["deleted_lines_total"] for v in views)
    unmeasured_lines = sum(v["unmeasured_lines"] for v in views)
    unmeasured_files = sum(v["unmeasured_files"] for v in views)
    died = max(0, ever["agent"] - alive["agent"])
    # Each class was decided at the commit, so they do not overlap; they are only clipped to the
    # number of lines that actually died, because a reverted line that somehow survived is alive.
    reverted_lines = min(sum(v["reverted_lines"] for v in views), died)
    deleted_lines = min(sum(v["deleted_lines"] for v in views), died - reverted_lines)
    churn = max(0, died - deleted_lines - reverted_lines)

    buckets = []
    for i, (label, _edge) in enumerate(BUCKETS):
        b_ever = sum(v["buckets"]["agent_ever"][i] for v in views)
        b_alive = sum(v["buckets"]["agent_alive"][i] for v in views)
        h_ever = sum(v["buckets"]["human_ever"][i] for v in views)
        h_alive = sum(v["buckets"]["human_alive"][i] for v in views)
        buckets.append({"label": label, "ever": b_ever, "alive": b_alive,
                        "rate": _rate(b_alive, b_ever, min_lines),
                        "human_ever": h_ever, "human_alive": h_alive,
                        "human_rate": _rate(h_alive, h_ever, min_lines)})

    day_ever, day_alive = {}, {}
    for view in views:
        for age, value in view["days"]["ever"].items():
            day_ever[int(age)] = day_ever.get(int(age), 0) + value
        for age, value in view["days"]["alive"].items():
            day_alive[int(age)] = day_alive.get(int(age), 0) + value
    half_life = _half_life(day_ever, day_alive, min_lines)

    harness = _roll([v["harness"] for v in views], min_lines)
    model = _roll([v["model"] for v in views], min_lines)
    languages = _by_key(views, _language, min_lines)
    directories = _by_key(views, _directory, min_lines)
    worst = _worst(directories, min_lines)

    repo_rows = sorted(
        ({"name": v["name"], "path": v["path"], "sessions": v["sessions"],
          "ever": v["ever"]["agent"], "alive": v["alive"]["agent"],
          "rate": _rate(v["alive"]["agent"], v["ever"]["agent"], min_lines),
          "human_ever": v["ever"]["human"], "human_alive": v["alive"]["human"],
          "human_rate": _rate(v["alive"]["human"], v["ever"]["human"], min_lines),
          "deleted_files": v["deleted_files"], "reverts": v["reverts"]["count"],
          "confidence": v["confidence"], "commits": v["commits"], "in_window": v["in_window"],
          "blamed_files": v["blamed_files"], "unmeasured_files": v["unmeasured_files"]}
         for v in views if v["sessions"] or v["ever"]["agent"]),
        key=lambda r: (-r["ever"], r["name"]))

    agent_rate = _rate(alive["agent"], ever["agent"], min_lines)
    human_rate = _rate(alive["human"], ever["human"], min_lines)
    you_rate = _rate(alive["you"], ever["you"], min_lines)
    control_rate = you_rate if you_rate is not None else human_rate
    control_label = "your own hand-written lines" if you_rate is not None else "hand-written lines"

    by_harness_ever = sorted(harness, key=lambda h: (-h["ever"], h["key"]))
    lead = by_harness_ever[0]["key"] if by_harness_ever else ""
    session_count = len(sessions)

    baseline = baseline_read(cfg.get("out_dir") or ".", "kept") if cfg.get("out_dir") else {}
    payload = _payload(ever, alive, repo_rows)
    moved = delta(payload, (baseline or {}).get("payload") or {})

    if alive["agent"] > ever["agent"]:
        notes.append("more lines survive than the history read accounts for; the log bound cut the "
                     "history short, so the survival rate is capped at 100%")
    if unmeasured_files:
        notes.append("{0} file(s) holding {1} agent line(s) were left unblamed at the bound and are "
                     "excluded from every rate rather than assumed alive".format(
                         unmeasured_files, unmeasured_lines))

    return {
        "generated": iso(now),
        "agent_label": HARNESS_NAMES.get(lead, lead or "the agent"),
        "totals": {"ever": ever, "alive": alive},
        "survival": {"agent": agent_rate, "human": human_rate, "you": you_rate,
                     "control": control_rate, "control_label": control_label,
                     "gap": None if agent_rate is None or control_rate is None
                     else control_rate - agent_rate},
        "gone": None if agent_rate is None else 100 - agent_rate,
        "sessions": {"count": session_count, "repos": len({s["repo"] for s in sessions.values()}),
                     "orphans": len(orphans), "orphan_writes": sum(orphans.values()),
                     "writes": len(edits)},
        "classes": {"alive": alive["agent"], "reverted": reverted_lines,
                    "deleted_with_file": deleted_lines, "rewritten": churn,
                    "deleted_files": deleted_files, "never_committed": sum(
                        len(v["never_committed"]) for v in views)},
        "half_life": {"buckets": buckets, "days": half_life["days"], "note": half_life["note"],
                      "spark": sparkline([b["rate"] or 0 for b in buckets], 8),
                      "human_spark": sparkline([b["human_rate"] or 0 for b in buckets], 8)},
        "reverts": {"count": sum(v["reverts"]["count"] for v in views), "lines": reverted_lines,
                    "same_day": sum(v["reverts"]["same_day"] for v in views),
                    "items": sorted((item for v in views for item in v["reverts"]["items"]),
                                    key=lambda r: (-r["lines"], r["sha"]))[:6]},
        "deleted": {"files": deleted_files, "lines": deleted_lines, "total_lines": deleted_total},
        "unmeasured": {"files": unmeasured_files, "lines": unmeasured_lines},
        "harnesses": by_harness_ever, "models": sorted(model, key=lambda m: (-m["ever"], m["key"])),
        "repos": repo_rows, "languages": languages[:8], "directories": directories[:8],
        "worst_directory": worst,
        "confidence": [{"repo": r["name"], "level": r["confidence"]["level"],
                        "coverage": r["confidence"]["coverage"], "why": r["confidence"]["why"]}
                       for r in repo_rows],
        "rule": attribution_rule(grace),
        "bounds": {"complete": not budget.exhausted, "hit": budget.hit,
                   "scanned_files": budget.files, "backend": backend.note,
                   "repos_seen": len(repos), "repos_measured": len(views)},
        "min_lines": min_lines, "grace_minutes": grace,
        "delta": moved, "since": since_note(baseline, now),
        "notes": sorted(set(notes)),
    }


def _payload(ever, alive, repo_rows) -> dict:
    payload = {"agent_alive": alive["agent"], "agent_ever": ever["agent"],
               "human_alive": alive["human"], "human_ever": ever["human"]}
    for row in repo_rows:
        payload["repo:{0}".format(row["name"])] = row["alive"]
    return payload


def save_baseline(view: dict, cfg: dict, now) -> str:
    """Record this run so tomorrow's can say what moved. Separate from `analyse`, which never writes."""
    payload = _payload(view["totals"]["ever"], view["totals"]["alive"], view["repos"])
    return baseline_write(cfg["out_dir"], "kept", payload, now)


def _rate(alive: int, ever: int, min_lines: int):
    """A survival percentage, or None when there are too few lines for one to mean anything."""
    if ever < max(1, min_lines):                     # never rate a group with nothing in it
        return None
    return min(100, pct(alive, ever))


def _roll(tables, min_lines) -> list:
    merged = {}
    for table in tables:
        for key, row in table.items():
            _add(merged, key, row["ever"], row["alive"])
    return sorted(({"key": k, "label": HARNESS_NAMES.get(k, k), "ever": v["ever"], "alive": v["alive"],
                    "rate": _rate(v["alive"], v["ever"], min_lines)} for k, v in merged.items()),
                  key=lambda r: (-r["ever"], r["key"]))


def _language(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    ext = name[name.rfind("."):].lower() if "." in name[1:] else ""
    return ext or "(no extension)"


def _directory(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "(repository root)"


def _by_key(views, keyfn, min_lines) -> list:
    merged = {}
    for view in views:
        for entry in view["files"]:
            key = keyfn(entry["path"])
            if keyfn is _directory:
                key = "{0}/{1}".format(view["name"], key)
            _add(merged, key, entry["ever"], entry["alive"])
    return sorted(({"key": k, "ever": v["ever"], "alive": v["alive"],
                    "rate": _rate(v["alive"], v["ever"], min_lines)} for k, v in merged.items()),
                  key=lambda r: (-r["ever"], r["key"]))


def _worst(rows, min_lines):
    """The worst directory, named. Only among directories with enough lines to be rateable."""
    rated = [r for r in rows if r["rate"] is not None]
    if not rated:
        return None
    worst = sorted(rated, key=lambda r: (r["rate"], -r["ever"], r["key"]))[0]
    return dict(worst)


def _half_life(day_ever, day_alive, min_lines) -> dict:
    """The age by which half of what was written has gone.

    Read cumulatively from today backwards: at each age, how much of everything written in the last
    N days is still standing. The first N where that falls to half is the median survival, which is
    the same statistic a half-life is, and it is only reported once enough lines are in the window
    for it to mean anything.
    """
    if not day_ever:
        return {"days": None, "note": "nothing committed inside a session window"}
    ever_total = alive_total = 0
    for age in sorted(day_ever):
        ever_total += day_ever.get(age, 0)
        alive_total += day_alive.get(age, 0)
        if ever_total < max(1, min_lines):
            continue
        if alive_total * 2 <= ever_total:
            return {"days": age,
                    "note": "half of everything written in the last {0} day(s) is already gone".format(age)}
    return {"days": None,
            "note": "more than half of everything written is still standing, so there is no median yet"}


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    cfg = cfg or {}
    totals, survival = v["totals"], v["survival"]
    c = Card("KEPT", "{0} lines written".format(_n(totals["ever"]["agent"])), cfg.get("color"))
    c.blank()
    c.headline("{0} wrote {1} lines across {2}.".format(
        v["agent_label"], _n(totals["ever"]["agent"]), plural(v["sessions"]["count"], "session")))
    if survival["agent"] is None:
        c.row("Too few lines in a window to rate; the floor is {0}.".format(v["min_lines"]))
    else:
        c.row("{0}% no longer exist. {1}".format(v["gone"], _median(v)))
    if survival["control"] is None:
        c.row("No hand-written control group in these files yet.")
    else:
        c.row("{0}: {1}% still there.".format(
            survival["control_label"].capitalize(), survival["control"]))

    c.rule("AGENT VS YOU, SAME FILES")
    control = "you" if survival["you"] is not None else "human"
    _side(c, "the agent", totals["alive"]["agent"], totals["ever"]["agent"], survival["agent"])
    _side(c, survival["control_label"], totals["alive"][control], totals["ever"][control],
          survival["control"])
    if survival["gap"] is not None:
        c.row("gap: {0} points {1} for the agent".format(
            abs(survival["gap"]), "worse" if survival["gap"] > 0 else "better"))

    classes = v["classes"]
    tiers = [("still there", classes["alive"]), ("undone by a revert", classes["reverted"]),
             ("deleted with the file", classes["deleted_with_file"]),
             ("rewritten in place", classes["rewritten"])]
    bar = tier_bar(tiers, 56)
    if bar:
        c.rule("WHERE IT WENT")
        c.row(bar)
        c.wrap(legend(tiers))

    c.rule("HALF-LIFE")
    spark = v["half_life"]["spark"]
    if spark:
        c.row("agent {0}    newest → oldest".format(spark))
    if v["half_life"]["human_spark"]:
        c.row("you   {0}    same buckets, same scale".format(v["half_life"]["human_spark"]))
    for b in v["half_life"]["buckets"]:
        c.row("{0}{1}{2}{3}".format(
            pad(b["label"], 11), rpad(_rate_text(b["rate"]), 8),
            rpad("{0} lines".format(_n(b["ever"])), 13),
            "   you " + _rate_text(b["human_rate"])))
    c.note(v["half_life"]["note"])

    if v["repos"]:
        c.rule("BY REPOSITORY")
        for row in v["repos"][:5]:
            c.cols("{0}  ({1})".format(row["name"], plural(row["sessions"], "session")),
                   "{0} vs {1}".format(_rate_text(row["rate"]), _rate_text(row["human_rate"])), 18)

    if v["worst_directory"]:
        c.rule("WORST DIRECTORY")
        worst = v["worst_directory"]
        c.row("{0} — {1}% of {2} lines survive".format(
            worst["key"], worst["rate"], _n(worst["ever"])))
    if v["languages"]:
        c.rule("BY LANGUAGE")
        for row in v["languages"][:4]:
            _side(c, row["key"], row["alive"], row["ever"], row["rate"])

    if v["reverts"]["count"]:
        c.rule("WRITTEN AND IMMEDIATELY UNDONE")
        c.row("{0} reverted, {1} line(s); {2} within a day".format(
            plural(v["reverts"]["count"], "agent commit"), _n(v["reverts"]["lines"]),
            v["reverts"]["same_day"]))
        for item in v["reverts"]["items"][:2]:
            c.cols("{0} {1}".format(item["sha"], item["subject"]), "{0} lines".format(item["lines"]), 12)

    c.blank()
    c.wrap(v["since"])
    for note in v["notes"][:2]:
        c.wrap(note)
    c.wrap("Attribution is a time window, not a fact. The report prints the rule in full.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources) -> str:
    totals, survival = v["totals"], v["survival"]
    L = ["# Kept", "",
         "{0} wrote {1} lines across {2}. {3}".format(
             v["agent_label"], _n(totals["ever"]["agent"]),
             plural(v["sessions"]["count"], "session"),
             "Too few lines to rate." if survival["agent"] is None
             else "{0}% no longer exist. {1}".format(v["gone"], _median(v))), "",
         "| who | lines written | still at HEAD | survives |", "|---|---|---|---|",
         "| the agent | {0} | {1} | {2} |".format(_n(totals["ever"]["agent"]),
                                                  _n(totals["alive"]["agent"]),
                                                  _rate_text(survival["agent"])),
         "| you (control group) | {0} | {1} | {2} |".format(_n(totals["ever"]["you"]),
                                                            _n(totals["alive"]["you"]),
                                                            _rate_text(survival["you"])),
         "| everyone hand-writing | {0} | {1} | {2} |".format(_n(totals["ever"]["human"]),
                                                              _n(totals["alive"]["human"]),
                                                              _rate_text(survival["human"])),
         "| bots | {0} | {1} | {2} |".format(_n(totals["ever"]["bot"]), _n(totals["alive"]["bot"]),
                                             _rate_text(_rate(totals["alive"]["bot"],
                                                              totals["ever"]["bot"], v["min_lines"]))),
         "",
         "The control group is the same files over the same history, outside every session "
         "window. Both columns come from one `git blame` of one HEAD, so nothing about the two "
         "numbers differs except which commits fall inside a window.", "",
         "## How a line is attributed", "", v["rule"], "",
         "A group with fewer than {0} lines is reported as unrated rather than given a percentage, "
         "so a one-line session cannot move a number.".format(v["min_lines"]), "",
         "## Where it went", "", "| class | lines |", "|---|---|",
         "| still at HEAD | {0} |".format(_n(v["classes"]["alive"])),
         "| undone by a revert | {0} |".format(_n(v["classes"]["reverted"])),
         "| deleted with the file | {0} ({1} file(s)) |".format(
             _n(v["classes"]["deleted_with_file"]), v["classes"]["deleted_files"]),
         "| rewritten in place | {0} |".format(_n(v["classes"]["rewritten"])),
         "| written but never committed | {0} file(s) |".format(v["classes"]["never_committed"]), "",
         "## Half-life", "", "| age | agent lines | agent survives | your lines | you survive |",
         "|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} | {4} |".format(b["label"], _n(b["ever"]), _rate_text(b["rate"]),
                                                   _n(b["human_ever"]), _rate_text(b["human_rate"]))
          for b in v["half_life"]["buckets"]]
    L += ["", v["half_life"]["note"], ""]

    L += ["## By harness", "", "| harness | lines written | still there | survives |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} |".format(h["label"], _n(h["ever"]), _n(h["alive"]),
                                             _rate_text(h["rate"])) for h in v["harnesses"]] or ["| — | | | |"]
    L += ["", "## By model", "", "| model | lines written | still there | survives |", "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} |".format(m["key"], _n(m["ever"]), _n(m["alive"]),
                                             _rate_text(m["rate"])) for m in v["models"]] or ["| — | | | |"]

    L += ["", "## By repository", "",
          "| repository | sessions | agent lines | agent survives | you survive | confidence |",
          "|---|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} | {4} | {5} |".format(
        r["name"], r["sessions"], _n(r["ever"]), _rate_text(r["rate"]), _rate_text(r["human_rate"]),
        r["confidence"]["level"]) for r in v["repos"]]

    L += ["", "## By language", "", "| extension | lines | survives |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(r["key"], _n(r["ever"]), _rate_text(r["rate"]))
          for r in v["languages"]]
    L += ["", "## By directory", "", "| directory | lines | survives |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(r["key"], _n(r["ever"]), _rate_text(r["rate"]))
          for r in v["directories"]]
    if v["worst_directory"]:
        L += ["", "The worst is **{0}**: {1}% of {2} lines survive.".format(
            v["worst_directory"]["key"], v["worst_directory"]["rate"],
            _n(v["worst_directory"]["ever"]))]

    if v["reverts"]["items"]:
        L += ["", "## Written and immediately undone", "",
              "| commit | subject | lines | undone after |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(
            i["sha"], i["subject"], i["lines"],
            "unknown" if i["hours"] < 0 else "{0}h".format(i["hours"])) for i in v["reverts"]["items"]]

    L += ["", "## Confidence", "", "| repository | level | commits in a window | why |",
          "|---|---|---|---|"]
    L += ["| {0} | {1} | {2}% | {3} |".format(c["repo"], c["level"], c["coverage"], c["why"])
          for c in v["confidence"]]

    L += ["", "## Since the last run", "", v["since"]]
    moved = v["delta"]
    if not moved.get("first_run"):
        L += ["", "| measure | change |", "|---|---|"]
        for key in sorted(set(list(moved["grew"]) + list(moved["shrank"]))):
            change = moved["grew"].get(key, moved["shrank"].get(key, 0))
            L.append("| {0} | {1}{2} |".format(key, "+" if change > 0 else "", int(change)))

    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    for s in sources or []:
        row = s if isinstance(s, dict) else getattr(s, "__dict__", {})
        L.append("| {0} | {1} | {2} |".format(row.get("name", ""),
                                              "yes" if row.get("found") else "no",
                                              row.get("note", "") or ""))
    L += ["", "## Bounds", "",
          "Read {0} item(s). {1}".format(v["bounds"]["scanned_files"],
                                         "Complete." if v["bounds"]["complete"]
                                         else "Stopped at the {0} bound, so every count is a lower "
                                              "bound.".format(v["bounds"]["hit"]))]
    for note in v["notes"]:
        L.append("")
        L.append(note)
    L += ["", "Read-only: transcripts were read for file paths and timestamps only, and git was "
          "asked nothing but `log`, `ls-files` and `blame`. No file was written outside the "
          "output directory and no repository was changed.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- small helpers

def _side(card: Card, label: str, alive: int, ever: int, rate):
    """One row of the comparison. An unrated side says so rather than drawing an empty bar at 0%."""
    value = "{0}/{1}".format(_n(alive), _n(ever))
    if rate is None:
        return card.cols("{0}  {1}".format(label, value), "unrated", 10)
    return card.bar(label, value, _share(rate), 12, 16)


def _n(value) -> str:
    try:
        return "{0:,}".format(int(value))
    except (TypeError, ValueError):
        return "0"


def _rate_text(rate) -> str:
    return "unrated" if rate is None else "{0}%".format(rate)


def _share(rate) -> float:
    return 0.0 if rate is None else rate / 100.0


def _median(v: dict) -> str:
    days = v["half_life"]["days"]
    if days is None:
        return "More than half is still standing."
    return "Median survival {0}.".format(plural(days, "day"))
