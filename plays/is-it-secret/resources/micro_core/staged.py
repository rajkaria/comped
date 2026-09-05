"""What is about to go into the commit, read from the index rather than from the working tree.

Narrow on purpose. A pre-commit check that cries about every print() gets skipped with --no-verify
within a week, so `print(` counts only in a .py file that is not a script, a Go println counts only
outside a main package, and the whole debug family is reported separately from the credential
family, because one is a nit and the other stops the commit.
"""
import re
from pathlib import Path

from . import gitindex, secrets

DEBUG = (
    ("javascript", re.compile(r"\bconsole\.(log|debug|dir)\s*\("), (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")),
    ("javascript", re.compile(r"^\s*debugger\s*;?\s*$"), (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")),
    ("python", re.compile(r"\b(pdb\.set_trace|breakpoint)\s*\("), (".py",)),
    ("python", re.compile(r"^\s*print\s*\("), (".py",)),
    ("ruby", re.compile(r"\bbinding\.pry\b"), (".rb",)),
    ("rust", re.compile(r"\bdbg!\s*\("), (".rs",)),
    ("go", re.compile(r"\bfmt\.Print(ln|f)?\s*\("), (".go",)),
    ("java", re.compile(r"\bSystem\.out\.print(ln)?\s*\("), (".java", ".kt")),
)
SCRIPT_DIRS = ("scripts/", "bin/", "tools/", "examples/", "docs/")
ENV_NAMES = re.compile(r"(^|/)(\.env(\..+)?|.*\.env)$")


def _ext(path):
    return path[path.rfind("."):] if "." in path.rsplit("/", 1)[-1] else ""


def debug_lines(path, text):
    """Leftover debugging in a file that is about to be committed. Deliberately a short list."""
    ext = _ext(path)
    is_script = any(path.startswith(d) or "/" + d in path for d in SCRIPT_DIRS)
    out = []
    for i, line in enumerate(str(text or "").split("\n"), start=1):
        for language, pattern, exts in DEBUG:
            if ext not in exts or not pattern.search(line):
                continue
            if language == "python" and pattern.pattern.startswith("^\\s*print") and is_script:
                continue          # printing IS the job of a script; only src code is nagged
            if language == "go" and "package main" in text:
                continue
            out.append({"line": i, "kind": "{0} debug output".format(language), "text": line.strip()[:120]})
            break
    return out


def review(repo, max_file_kb=512, strict=True):
    """Every staged path, with what is wrong in it and where the bytes came from."""
    entries = gitindex.staged_entries(repo)
    if not entries:
        return {"ok": True, "files": [], "findings": [], "oversized": [], "debug": [],
                "env_files": [], "verdict": "nothing-staged", "from_worktree": [],
                "warning": "nothing staged, or this is not a git repository"}
    findings, oversized, debug, env_files, from_worktree, files = [], [], [], [], [], []
    for path, sha, size in entries:
        raw = gitindex.read_blob(repo, sha)
        source = "index"
        if raw is None:
            source = "worktree"
            try:
                raw = (Path(str(repo)).expanduser() / path).read_bytes()
            except OSError:
                raw = b""
            from_worktree.append(path)
        files.append({"path": path, "bytes": len(raw), "source": source})
        if size > max_file_kb * 1024:
            oversized.append({"path": path, "bytes": size})
        if ENV_NAMES.search(path):
            env_files.append(path)
        if b"\x00" in raw[:8192]:
            continue                                    # a binary blob has no lines to read
        text = raw.decode("utf-8", "replace")
        for f in secrets.scan(text, strict=strict):
            findings.append({"path": path, "kind": f.kind, "severity": f.severity, "line": f.line,
                             "masked": f.masked, "why": f.why})
        for d in debug_lines(path, text):
            debug.append(dict(d, path=path))
    if any(f["severity"] == "blocker" for f in findings):
        verdict = "do-not-commit"
    elif findings or oversized or env_files or debug:
        verdict = "review"
    else:
        verdict = "clean"
    return {"ok": True, "files": files, "findings": findings, "oversized": oversized,
            "debug": debug, "env_files": env_files, "verdict": verdict,
            "from_worktree": from_worktree}
