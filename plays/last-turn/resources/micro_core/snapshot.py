"""What changed under this directory since the last time you asked.

The question people actually have after an agent turn is not "what did it say" but "what did it
touch, and did it touch anything outside the repo". Both halves are answered here, and the second
half is answered without reading a byte of anything private: the sensitive paths are checked by
directory mtime alone, so the Play can say ~/.ssh changed without ever opening it.
"""
import hashlib
import json
import os
from pathlib import Path

from .common import expand

DEFAULT_IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                  ".next", ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", ".DS_Store",
                  ".tox", ".gradle", "vendor", ".terraform"}
SENSITIVE = ("~/.ssh", "~/.aws", "~/.config", "~/.gnupg", "~/Library/LaunchAgents",
             "~/.claude", "~/.codex")
LINE_LIMIT = 2 * 1024 * 1024


def _lines(path, size):
    if size > LINE_LIMIT:
        return -1
    try:
        with open(str(path), "rb") as fh:
            raw = fh.read()
    except OSError:
        return -1
    if b"\x00" in raw[:8192]:
        return -1                                   # binary: a line count would be a fiction
    return raw.count(b"\n") + (0 if raw.endswith(b"\n") or not raw else 1)


def scan_tree(root, ignore=None, max_files=20000):
    """(files, meta). Bounded, and it says when a bound was hit rather than reporting a short list."""
    ignore = set(ignore or DEFAULT_IGNORE)
    root = Path(str(root)).expanduser()
    files, truncated, skipped = {}, False, 0
    if not root.is_dir():
        return ({}, {"truncated": False, "root": str(root), "missing": True, "files": 0})
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d not in ignore and not d.startswith(".git"))
        for name in sorted(filenames):
            if name in ignore:
                continue
            full = Path(dirpath) / name
            try:
                st = full.stat()
                if not full.is_file() or full.is_symlink():
                    continue
                rel = str(full.relative_to(root))
            except (OSError, ValueError):
                skipped += 1
                continue
            files[rel] = [st.st_mtime_ns, st.st_size, _lines(full, st.st_size)]
            if len(files) >= max_files:
                truncated = True
                break
        if truncated:
            break
    return (files, {"truncated": truncated, "root": str(root), "files": len(files),
                    "unreadable": skipped, "missing": False})


def key_for(root):
    """One snapshot per directory, named by a digest of its absolute path."""
    return hashlib.sha256(str(Path(str(root)).expanduser().resolve()).encode("utf-8")).hexdigest()[:16]


def _path(state_dir, key):
    return expand(state_dir) / "snapshot-{0}.json".format(key)


def save(state_dir, key, snap):
    p = _path(state_dir, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, sort_keys=True), encoding="utf-8")
    return str(p)


def load(state_dir, key):
    try:
        return json.loads(_path(state_dir, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def delta(prev, cur):
    """Created, modified, deleted — and modified means the bytes moved, not that mtime did."""
    prev, cur = prev or {}, cur or {}
    created = sorted(set(cur) - set(prev))
    deleted = sorted(set(prev) - set(cur))
    modified = sorted(p for p in set(cur) & set(prev) if cur[p][1:] != prev[p][1:])
    added = removed = 0
    for p in created:
        added += max(0, cur[p][2])
    for p in deleted:
        removed += max(0, prev[p][2])
    for p in modified:
        before, after = prev[p][2], cur[p][2]
        if before >= 0 and after >= 0:
            added += max(0, after - before)
            removed += max(0, before - after)
    churn = [(abs(cur[p][1] - prev[p][1]), p) for p in modified] + [(cur[p][1], p) for p in created]
    biggest = max(churn)[1] if churn else None
    return {"created": created, "modified": modified, "deleted": deleted,
            "lines_added": added, "lines_removed": removed,
            "biggest": {"path": biggest, "bytes": (cur.get(biggest) or [0, 0, 0])[1]} if biggest else None}


def sensitive_state(home=None):
    """Directory mtimes only. Enough to notice, never enough to be a second thing worth stealing."""
    home = Path(str(home)).expanduser() if home else Path.home()
    out = {}
    for label in SENSITIVE:
        p = home / label[2:]
        try:
            out[label] = int(p.stat().st_mtime_ns)
        except OSError:
            continue
    return out


def sensitive_changed(prev, cur):
    prev, cur = prev or {}, cur or {}
    return sorted(k for k in cur if k in prev and cur[k] != prev[k])
