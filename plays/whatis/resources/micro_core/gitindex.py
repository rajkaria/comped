"""Read the staged set out of .git/index, without running git.

Every other core in this repository is offline and subprocess-free, and safe-to-commit keeps that
promise rather than shelling out to `git diff --cached`. The index format is public and stable, so
the entries are parsed directly and the blobs are read out of .git/objects with zlib.

What it will not do is guess. A version 4 index uses prefix-compressed paths; this reader declines
one by name instead of mis-parsing it, and a blob that lives in a packfile comes back as None so
the caller can say it read the working tree instead.
"""
import binascii
import struct
import zlib
from pathlib import Path


def git_dir(repo):
    """`.git` as a directory, as a `gitdir:` pointer file, or the bundled fixture's `dot-git`."""
    root = Path(str(repo)).expanduser()
    candidate = root / ".git"
    if candidate.is_dir():
        return candidate
    if candidate.is_file():
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if text.startswith("gitdir:"):
            target = Path(text.split(":", 1)[1].strip())
            target = target if target.is_absolute() else (root / target)
            return target if target.is_dir() else None
        return None
    packaged = root / "dot-git"
    return packaged if packaged.is_dir() else None


def staged_entries(repo):
    """(path, blob sha, size) for every staged path. Never raises: an unreadable index is []."""
    gd = git_dir(repo)
    if gd is None:
        return []
    try:
        raw = (gd / "index").read_bytes()
    except OSError:
        return []
    if len(raw) < 12 or raw[:4] != b"DIRC":
        return []
    version, count = struct.unpack(">II", raw[4:12])
    if version not in (2, 3):
        return []                          # version 4 compresses paths; declining beats guessing
    out, pos = [], 12
    for _ in range(count):
        if pos + 62 > len(raw):
            break
        size = struct.unpack(">I", raw[pos + 36:pos + 40])[0]
        sha = binascii.hexlify(raw[pos + 40:pos + 60]).decode("ascii")
        flags = struct.unpack(">H", raw[pos + 60:pos + 62])[0]
        name_len = flags & 0x0FFF
        cursor = pos + 62
        if flags & 0x4000:                 # a version 3 extended flag adds two more bytes
            cursor += 2
        if name_len < 0x0FFF:
            name = raw[cursor:cursor + name_len]
            cursor += name_len
        else:                              # a path at or over 4095 bytes is NUL-terminated instead
            end = raw.index(b"\x00", cursor)
            name, cursor = raw[cursor:end], end
        # An entry runs to at least one NUL and is then padded so its length is a multiple of 8.
        used = cursor - pos + 1
        pos += used + (8 - used % 8) % 8
        out.append((name.decode("utf-8", "replace"), sha, size))
    return out


def read_blob(repo, sha):
    """The staged bytes from a loose object, or None when the object is packed."""
    gd = git_dir(repo)
    if gd is None or len(sha) != 40:
        return None
    p = gd / "objects" / sha[:2] / sha[2:]
    try:
        raw = zlib.decompress(p.read_bytes())
    except (OSError, zlib.error):
        return None
    nul = raw.find(b"\x00")
    return raw[nul + 1:] if nul >= 0 else raw
