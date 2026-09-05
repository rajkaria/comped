"""Firefox session store (`recovery.jsonlz4`), read without Firefox.

Mozilla wraps a JSON document in its own container: the ASCII magic `mozLz40\\0`, a little-endian
uint32 giving the decompressed size, then one LZ4 block. LZ4 block decoding is thirty lines of
byte shuffling with no tables and no entropy coding, so the file is readable from the standard
library alone rather than by taking a dependency to open a file the user already owns.
"""
import json
import struct

MAGIC = b"mozLz40\0"


class Unreadable(Exception):
    """Not a mozlz4 container, or a block that does not decode to its declared length."""


def lz4_block_decompress(src: bytes, expected: int) -> bytes:
    """Decode one LZ4 block. Raises rather than returning a plausible-looking partial buffer."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        literal = token >> 4
        if literal == 15:
            while True:
                if i >= n:
                    raise Unreadable("literal length ran past the block")
                b = src[i]
                i += 1
                literal += b
                if b != 255:
                    break
        if i + literal > n:
            raise Unreadable("literal run ran past the block")
        out += src[i:i + literal]
        i += literal
        if i >= n:
            break                       # the last sequence is literals only, by design
        if i + 2 > n:
            raise Unreadable("match offset ran past the block")
        offset = struct.unpack_from("<H", src, i)[0]
        i += 2
        if offset == 0 or offset > len(out):
            raise Unreadable("match offset {0} points outside the output".format(offset))
        match = token & 0x0F
        if match == 15:
            while True:
                if i >= n:
                    raise Unreadable("match length ran past the block")
                b = src[i]
                i += 1
                match += b
                if b != 255:
                    break
        match += 4                      # LZ4 never encodes a match shorter than four bytes
        start = len(out) - offset
        for k in range(match):          # overlapping copies are legal and common: copy byte by byte
            out.append(out[start + k])
        if len(out) > expected + 1024:
            raise Unreadable("output overran its declared size")
    if len(out) != expected:
        raise Unreadable("decoded {0} bytes, header declared {1}".format(len(out), expected))
    return bytes(out)


def read_json(data: bytes) -> dict:
    if not data.startswith(MAGIC):
        raise Unreadable("not a mozlz4 file")
    expected = struct.unpack_from("<I", data, len(MAGIC))[0]
    if expected > 256 * 1024 * 1024:
        raise Unreadable("declared size is not plausible")
    raw = lz4_block_decompress(data[len(MAGIC) + 4:], expected)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise Unreadable("decompressed bytes are not JSON: {0}".format(exc))


def read_session(data: bytes) -> dict:
    """Flatten a Firefox session document into the same tab shape the Chrome reader returns."""
    doc = read_json(data) if data[:len(MAGIC)] == MAGIC else json.loads(data.decode("utf-8", "replace"))
    tabs, windows = [], 0
    for w_index, window in enumerate(doc.get("windows") or []):
        if not isinstance(window, dict):
            continue
        windows += 1
        for t_index, tab in enumerate(window.get("tabs") or []):
            if not isinstance(tab, dict):
                continue
            entries = [e for e in (tab.get("entries") or []) if isinstance(e, dict)]
            if not entries:
                continue
            # `index` is one-based and may point past the list on a session still being written.
            pos = tab.get("index")
            entry = entries[pos - 1] if isinstance(pos, int) and 1 <= pos <= len(entries) else entries[-1]
            url = str(entry.get("url") or "")
            if not url or url.startswith("about:newtab"):
                continue
            tabs.append({"tab_id": "{0}:{1}".format(w_index, t_index), "window": w_index, "index": t_index,
                         "url": url, "title": str(entry.get("title") or tab.get("label") or ""),
                         "pinned": bool(tab.get("pinned")), "grouped": tab.get("groupId") is not None,
                         "history_depth": len(entries),
                         "navigated_at": _ms(entry.get("lastAccessed") or tab.get("lastAccessed")),
                         "active_at": _ms(tab.get("lastAccessed"))})
    return {"tabs": tabs, "windows": windows, "closed": len(doc.get("_closedWindows") or []),
            "commands": len(tabs)}


def _ms(value):
    """Firefox records milliseconds since the Unix epoch; the readers above expect UTC seconds."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else (v if v > 0 else None)
