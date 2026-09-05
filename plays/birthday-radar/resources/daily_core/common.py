"""Shared machinery: bounded read-only traversal, source degradation, state, formatting.

Three rules every scanner in this package keeps, enforced here rather than restated six times:

1. A source that cannot be read becomes a labelled unknown (`Source.found=False` with a note),
   never an exception that ends the run. A step that read nothing still exits 0 and says so.
2. Every traversal is bounded (files, bytes, depth, seconds) and says when a bound was hit, so a
   partial answer is reported as a lower bound and never as a complete one.
3. Nothing is opened for writing outside the caller's out_dir, and nothing is opened over a
   network. SQLite databases are copied to a temp file and reopened read-only, so a live database
   is never locked, journalled or upgraded by being looked at.
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- console

for _stream in (sys.stdout, sys.stderr):
    # The cards are drawn with box characters. On a Windows code page, printing one to a pipe dies
    # with UnicodeEncodeError before a single row reaches the screen. Ask for UTF-8; carry on if
    # the stream is something a test harness substituted that cannot be reconfigured.
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


# ---------------------------------------------------------------- bounds

@dataclass
class Budget:
    """A traversal bound. `hit` names the first limit reached, so a partial scan can say so."""
    max_files: int = 200000
    max_bytes: int = 512 * 1024 * 1024
    max_depth: int = 12
    max_seconds: float = 20.0
    files: int = 0
    read_bytes: int = 0
    started: float = field(default_factory=time.monotonic)
    hit: str = ""

    def spend(self, nbytes: int = 0) -> bool:
        """Count one visited file. Returns False once a bound is reached (and records which)."""
        self.files += 1
        self.read_bytes += max(0, nbytes)
        if self.hit:
            return False
        if self.files > self.max_files:
            self.hit = "file count ({0})".format(self.max_files)
        elif self.read_bytes > self.max_bytes:
            self.hit = "bytes read ({0})".format(human_bytes(self.max_bytes))
        elif time.monotonic() - self.started > self.max_seconds:
            self.hit = "time ({0:.0f}s)".format(self.max_seconds)
        return not self.hit

    @property
    def exhausted(self) -> bool:
        return bool(self.hit)


# ---------------------------------------------------------------- sources

@dataclass
class Source:
    """One place a scanner looked. Absent and unreadable are different answers; both are reported."""
    name: str
    path: str = ""
    found: bool = False
    note: str = ""
    items: int = 0

    def miss(self, note: str) -> "Source":
        self.found, self.note = False, note
        return self

    def hit(self, items: int, note: str = "") -> "Source":
        self.found, self.items, self.note = True, items, note
        return self


def absent_note(sources) -> str:
    """One line naming what could not be read, or empty when everything was."""
    misses = ["{0} ({1})".format(s.name, s.note) if s.note else s.name for s in sources if not s.found]
    return "; ".join(misses)


# ---------------------------------------------------------------- paths

def expand(p) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(str(p)))).resolve() if str(p) else Path()


def out_path(out_dir, name: str) -> Path:
    d = Path(os.path.expanduser(str(out_dir)))
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def write_text(out_dir, name: str, text: str) -> str:
    """The only write in this package. Everything a Play produces lands under out_dir."""
    p = out_path(out_dir, name)
    p.write_text(text, encoding="utf-8")
    return str(p)


def first_dir(*candidates):
    """The first candidate that exists, so a scanner can offer several vendor paths and pick one."""
    for c in candidates:
        if not c:
            continue
        p = expand(c)
        if p.exists():
            return p
    return None


def walk(root: Path, budget: Budget, skip_names=(), follow_symlinks=False, want_dirs=False):
    """Depth-bounded scandir walk that never leaves `root` and never follows a symlink out of it.

    Yields (path, os.stat_result, depth). Directories it cannot read are skipped silently; the
    caller learns about incompleteness from `budget.hit`, which is the honest single signal.
    """
    root = root.resolve()
    stack = [(root, 0)]
    skip = set(skip_names)
    while stack:
        d, depth = stack.pop()
        if depth > budget.max_depth or budget.exhausted:
            continue
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
            continue
        for e in entries:
            if e.name in skip or e.name.startswith("._"):
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=follow_symlinks)
                st = e.stat(follow_symlinks=follow_symlinks)
            except (OSError, ValueError):
                continue
            if is_dir:
                if want_dirs:
                    if not budget.spend(0):
                        return
                    yield Path(e.path), st, depth
                stack.append((Path(e.path), depth + 1))
                continue
            # The budget counts files visited, not bytes on disk: a sizing walk reads nothing, and
            # a reading walk adds what it actually read through `budget.spend`.
            if not budget.spend(0):
                return
            yield Path(e.path), st, depth


def read_bytes(p: Path, limit: int = 8 * 1024 * 1024) -> bytes:
    """Read at most `limit` bytes. Returns b"" for anything unreadable: callers degrade, never raise."""
    try:
        with open(p, "rb") as fh:
            return fh.read(limit)
    except (OSError, ValueError):
        return b""


def read_text(p: Path, limit: int = 4 * 1024 * 1024) -> str:
    b = read_bytes(p, limit)
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def open_sqlite_readonly(src: Path):
    """Open a copy of a SQLite database, read-only.

    Browsers and Contacts hold their databases open with WAL journals. Opening the live file even
    read-only can block, and any write at all (a journal, a schema upgrade) would be a change this
    package must never make. Copying the database plus its sidecars and opening the copy with
    mode=ro leaves the original untouched byte for byte. The caller gets (connection, tempdir) and
    must remove the tempdir.
    """
    tmp = tempfile.mkdtemp(prefix="daily-core-")
    dst = Path(tmp) / src.name
    shutil.copy2(src, dst)
    for suffix in ("-wal", "-shm"):
        side = Path(str(src) + suffix)
        if side.exists():
            try:
                shutil.copy2(side, Path(str(dst) + suffix))
            except OSError:
                pass
    con = sqlite3.connect("file:{0}?mode=ro".format(dst.as_posix().replace("?", "%3f")), uri=True)
    con.row_factory = sqlite3.Row
    return con, tmp


# ---------------------------------------------------------------- time

EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)   # Chrome / WebKit
EPOCH_2001 = datetime(2001, 1, 1, tzinfo=timezone.utc)   # Apple Core Data


def from_chrome(us) -> "datetime | None":
    """Chrome stores microseconds since 1601-01-01 UTC. 0 means never, not the Renaissance."""
    try:
        us = int(us)
    except (TypeError, ValueError):
        return None
    if us <= 0 or us > 20000000000000000:
        return None
    return EPOCH_1601 + timedelta(microseconds=us)


def from_apple(seconds) -> "datetime | None":
    """Apple Core Data stores seconds since 2001-01-01 UTC, sometimes fractional."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return None
    if abs(s) > 4000000000:
        return None
    return EPOCH_2001 + timedelta(seconds=s)


def from_unix(seconds) -> "datetime | None":
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return None
    if s <= 0 or s > 4102444800:
        return None
    return datetime.fromtimestamp(s, timezone.utc)


def now_utc(s: str = "") -> datetime:
    """The clock, overridable with --now so every test and every fixture run is deterministic."""
    if s:
        d = parse_date(s)
        if d:
            return d
    return datetime.now(timezone.utc)


def parse_date(s: str):
    t = str(s).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z",
                # mdls and several exporters put a space before the offset; strptime needs it declared.
                "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S.%f %z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            d = datetime.strptime(t, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(t)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def iso(d) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else ""


def day(d) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d") if d else ""


def age_days(d, now) -> "int | None":
    return None if not d else max(0, int((now - d).total_seconds() // 86400))


def ago(d, now) -> str:
    """A duration a person reads without doing arithmetic: 3d, 5w, 14mo."""
    n = age_days(d, now)
    if n is None:
        return "unknown"
    if n == 0:
        return "today"
    if n == 1:
        return "yesterday"
    if n < 21:
        return "{0}d".format(n)
    if n < 90:
        return "{0}w".format(n // 7)
    if n < 730:
        return "{0}mo".format(n // 30)
    return "{0}y".format(round(n / 365.25, 1)).replace(".0y", "y")


def month(d) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m") if d else ""


# ---------------------------------------------------------------- formatting

def human_bytes(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return "{0:.0f} {1}".format(n, unit) if unit == "B" or abs(n) >= 100 else "{0:.1f} {1}".format(n, unit)
        n /= 1024.0
    return "{0:.1f} TB".format(n)


def plural(n: int, one: str, many: str = "") -> str:
    return "{0} {1}".format(n, one if n == 1 else (many or one + "s"))


def pct(part, whole) -> int:
    return 0 if not whole else int(round(100.0 * part / whole))


def ellipsis(s: str, width: int) -> str:
    """Collapse whitespace, then truncate on display width. For prose and single values."""
    return trunc(" ".join(str(s or "").split()), width)


def trunc(s: str, width: int) -> str:
    """Truncate on display width, preserving the spaces that align an already-formatted row."""
    s = str(s or "")
    if display_width(s) <= width:
        return s
    out, used = [], 0
    for ch in s:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + w > width - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def shorten_path(p, width: int) -> str:
    """Keep the end of a path, which is the part that identifies it, and elide the front."""
    text = str(p).replace(str(Path.home()), "~")
    if display_width(text) <= width:
        return text
    parts = text.split("/")
    out = parts[-1]
    for part in reversed(parts[:-1]):
        candidate = part + "/" + out
        if display_width(candidate) + 2 > width:
            break
        out = candidate
    return "…/" + out


def display_width(s: str) -> int:
    return sum(0 if unicodedata.combining(c) else (2 if unicodedata.east_asian_width(c) in ("W", "F") else 1)
               for c in str(s))


_HOST = re.compile(r"^[a-z][a-z0-9+.-]*://(?:[^/@\s]*@)?([^/:\s?#]+)", re.I)


def host_of(url: str) -> str:
    m = _HOST.match(str(url or "").strip())
    if not m:
        return ""
    h = m.group(1).lower().strip(".")
    return h[4:] if h.startswith("www.") else h


def registrable(host: str) -> str:
    """Group by the name a person recognises: docs.google.com and mail.google.com are both Google.

    A public-suffix list would need a network fetch to stay current, so this uses a small table of
    the two-label suffixes that actually appear in browsing, and says nothing it cannot support.
    """
    parts = [p for p in str(host or "").split(".") if p]
    if len(parts) < 3:
        return ".".join(parts)
    two = {"co.uk", "org.uk", "ac.uk", "gov.uk", "co.in", "co.jp", "com.au", "com.br", "co.nz",
           "com.sg", "co.za", "com.mx", "co.kr", "com.tr", "com.cn", "co.il", "github.io"}
    return ".".join(parts[-3:]) if ".".join(parts[-2:]) in two else ".".join(parts[-2:])


# ---------------------------------------------------------------- privacy

def redact_url(url: str, keep_path: bool) -> str:
    """A URL a person can recognise without carrying a session token into a report.

    Query strings and fragments hold auth tokens, search terms and document ids; they never appear
    in output. With keep_path false only the host survives, which is the safe default for anything
    that could be shared.
    """
    u = str(url or "").strip()
    if not u:
        return ""
    host = host_of(u)
    if not host:
        return "(non-web)" if not u.startswith(("http://", "https://")) else ""
    if not keep_path:
        return host
    rest = u.split("://", 1)[-1]
    path = rest[len(rest.split("/", 1)[0]):].split("?")[0].split("#")[0]
    path = re.sub(r"/\d{4,}(?=/|$)", "/…", path)
    return host + ellipsis(path, 44) if path not in ("", "/") else host


def redact_name(name: str, redact: bool) -> str:
    """Initials when redacting, so a row stays countable without naming a person."""
    n = " ".join(str(name or "").split())
    if not redact or not n:
        return n
    parts = [p for p in re.split(r"[\s,]+", n) if p]
    return " ".join(p[0].upper() + "." for p in parts[:3]) or "(name)"


# ---------------------------------------------------------------- step contract

def emit(human: str, result: dict) -> int:
    """The step contract: a human block, then exactly one JSON object as the last line.

    The presentation plane splits on that last line, so nothing may follow it and it must always
    be present, including on the paths where a scanner found nothing at all.
    """
    text = (human or "").rstrip()
    if text:
        sys.stdout.write(text + "\n")
    sys.stdout.write(json.dumps(result, default=str, sort_keys=True) + "\n")
    sys.stdout.flush()
    return 0


def envelope(sources, budget: Budget, extra: dict) -> dict:
    """Every step's JSON answers the same three questions before it answers its own."""
    doc = {"ok": True, "sources": [asdict(s) for s in sources],
           "complete": not budget.exhausted, "scanned_files": budget.files}
    if budget.exhausted:
        doc["truncated"] = budget.hit
        doc["warning"] = "stopped at the {0} bound; counts are a lower bound".format(budget.hit)
    absent = absent_note(sources)
    if sources and not any(s.found for s in sources):
        doc["warning"] = "nothing to read: {0}".format(absent or "no source found")
        doc["empty"] = True
    elif absent:
        doc["note"] = "not read: {0}".format(absent)
    doc.update(extra)
    return doc


def state_write(out_dir, name: str, doc: dict) -> str:
    return write_text(out_dir, ".{0}.json".format(name), json.dumps(doc, default=str, sort_keys=True, indent=1) + "\n")


def state_read(out_dir, name: str) -> dict:
    p = Path(os.path.expanduser(str(out_dir))) / ".{0}.json".format(name)
    if not p.exists():
        raise FileNotFoundError("run the earlier step first: {0} is missing from {1}".format(p.name, out_dir))
    return json.loads(p.read_text(encoding="utf-8"))


def as_bool(s) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def fixtures_dir() -> Path:
    """Bundled synthetic data, so a stranger's first run works with nothing configured."""
    return Path(__file__).resolve().parent / "fixtures"
