import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Tuple


@dataclass
class JsonlStats:
    lines: int = 0
    parsed: int = 0
    unparsed: int = 0
    note: str = ""


def iter_jsonl(path: Path, stats: JsonlStats) -> Iterator[Tuple[int, dict]]:
    """Yield (line_number, object) for every JSON object line. Never raises on bad content.

    Blank lines count towards `lines` but are not `unparsed`: they carry no content to
    misread, so counting them would overstate how much of a log we failed to understand.
    """
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as e:
        stats.note = (stats.note + "; unreadable {0}: {1}".format(path, e.strerror or e)).strip("; ")
        return
    with fh:
        for n, line in enumerate(fh, 1):
            stats.lines += 1
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except ValueError:
                stats.unparsed += 1
                continue
            if not isinstance(obj, dict):
                stats.unparsed += 1
                continue
            stats.parsed += 1
            yield n, obj
