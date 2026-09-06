"""`git blame --line-porcelain`, parsed into one record per line of the file.

The porcelain format is one of the few things git specifies precisely, and it is worth reading
carefully rather than with a regular expression per line. A record starts with a header line

    <40-hex sha> <line in the original file> <line in the final file> [<lines in this group>]

followed by zero or more `key value` fields, followed by exactly one line beginning with a TAB
that holds the file content. Two details are what make a naive reader wrong:

1. In `--porcelain` the full key/value block appears only the *first* time a commit is seen; later
   groups from the same commit carry the header line alone. `--line-porcelain` repeats the block
   for every line. Both are handled here by remembering each commit's fields the first time they
   appear and reusing them when a group does not repeat them, so this reader is correct against
   either flag and never invents an author for a repeated commit.
2. A `boundary` field is a bare key with no value, and marks a commit at the edge of the range
   that has been walked. It carries no author fields of its own and must not be mistaken for one.

Nothing here raises. Truncated output, an interleaved warning on stdout, a header with no content
line: each is dropped and the lines around it are still returned, because a blame that was cut off
is a lower bound, and a lower bound is a usable answer where an exception is not.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from ..gitread import identity_key

# The header line, and only the header line: a `key value` field can never match it, because a
# field's first token is a word and this insists on hex followed by two or three integers.
_HEADER = re.compile(r"^([0-9a-f]{7,40}) (\d+) (\d+)(?: (\d+))?$")


@dataclass
class BlameLine:
    """One line of the blamed file, and the commit that introduced it."""
    sha: str = ""
    author_time: object = None          # aware datetime in UTC, or None when git did not say
    author_key: str = ""                # the identity key two commits by one human share
    author_name: str = ""
    final_line: int = 0
    boundary: bool = False
    summary: str = ""
    filename: str = ""

    @property
    def short(self) -> str:
        return self.sha[:8]


def parse_porcelain(text: str) -> list:
    """Every line of a blamed file, in file order. Returns [] for anything unparseable."""
    out, commits = [], {}
    sha, final_line, fields = "", 0, {}
    for raw in str(text or "").split("\n"):
        if raw[:1] == "\t":                         # the content line closes the record
            if sha:
                out.append(_build(sha, final_line, _fields_for(commits, sha, fields)))
            sha, final_line, fields = "", 0, {}
            continue
        header = _HEADER.match(raw)
        if header:
            if sha:                                 # a header with no content line: keep the facts
                _fields_for(commits, sha, fields)
            sha, final_line, fields = header.group(1), _int(header.group(3)), {}
            continue
        if not raw or not sha:
            continue
        key, _, value = raw.partition(" ")
        if key:
            fields[key] = value
    return out


def by_commit(lines) -> dict:
    """{sha: line count}, so a caller can ask how much of one commit is still standing."""
    counts = {}
    for line in lines:
        counts[line.sha] = counts.get(line.sha, 0) + 1
    return counts


def authors(lines) -> dict:
    """{author_key: line count}, in the same spirit."""
    counts = {}
    for line in lines:
        counts[line.author_key] = counts.get(line.author_key, 0) + 1
    return counts


# ---------------------------------------------------------------- internals

def _fields_for(commits: dict, sha: str, fields: dict) -> dict:
    """The fields for this commit, remembering the first full block and reusing it afterwards."""
    known = commits.get(sha)
    if known is None or "author-time" in fields:
        merged = dict(known or {})
        merged.update(fields)
        commits[sha] = merged
        return merged
    if fields:
        # A repeated group with only the odd extra field (`boundary`, `previous`) still counts.
        merged = dict(known)
        merged.update(fields)
        return merged
    return known


def _build(sha: str, final_line: int, fields: dict) -> BlameLine:
    name = fields.get("author", "")
    mail = (fields.get("author-mail") or "").strip().strip("<>")
    return BlameLine(sha=sha, author_time=_when(fields.get("author-time")),
                     author_key=identity_key(name, mail), author_name=name,
                     final_line=final_line, boundary="boundary" in fields,
                     summary=fields.get("summary", ""), filename=fields.get("filename", ""))


def _when(value):
    """A git epoch second as an aware UTC datetime. The timezone field is display only.

    `author-time` is already an absolute instant; `author-tz` says how the author's clock was
    labelled, which changes how a date reads to a human but never which instant it was. Windows
    are compared in UTC, so the offset is deliberately not applied.
    """
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if seconds <= 0 or seconds > 4102444800:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
