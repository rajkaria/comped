"""Enough of PDF to read a receipt, with no dependency and no claim to be a PDF library.

A PDF's visible text lives in content streams, usually Flate-compressed, as strings handed to the
Tj and TJ operators. Pulling those out recovers the text of a machine-generated receipt or invoice
almost every time. It recovers nothing from a scan, and nothing from a document whose fonts use a
custom encoding — both of which are reported as unreadable rather than guessed at, because a
half-decoded total is worse than no total.
"""
import re
import zlib

STREAM = re.compile(rb"stream\r?\n?(.*?)\r?\n?endstream", re.S)
LITERAL = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
HEXSTR = re.compile(rb"<([0-9A-Fa-f\s]+)>\s*Tj")
# Deliberately no regex for the whole `[ ... ] TJ` array: a nested-alternation pattern of that
# shape backtracks catastrophically on a real bank statement, taking ten seconds on two megabytes.
# Literal strings alone are unambiguous (an escape starts with a backslash, a plain byte cannot),
# so scanning a chunk for them is linear and recovers the same text.
BREAK = re.compile(rb"(?:^|\s)(?:T\*|TD|Td|ET)(?:\s|$)")

ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
           b"(": b"(", b")": b")", b"\\": b"\\"}


class Unreadable(Exception):
    pass


def _unescape(raw: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch != b"\\":
            out += ch
            i += 1
            continue
        nxt = raw[i + 1:i + 2]
        if nxt in ESCAPES:
            out += ESCAPES[nxt]
            i += 2
        elif nxt.isdigit():
            digits = raw[i + 1:i + 4]
            octal = bytes(c for c in digits if 48 <= c <= 55)[:3]
            out += bytes([int(octal, 8) & 0xFF]) if octal else b""
            i += 1 + len(octal)
        elif nxt == b"\n":
            i += 2                       # a backslash at end of line is a continuation, not a character
        else:
            out += nxt
            i += 2
    return bytes(out)


def _decode(raw: bytes) -> str:
    """PDF strings are PDFDocEncoding or UTF-16BE; the byte-order mark is the only reliable tell."""
    if raw[:2] in (b"\xfe\xff", b"\xff\xfe"):
        return raw.decode("utf-16", "replace")
    return raw.decode("latin-1", "replace")


def _streams(data: bytes):
    for m in STREAM.finditer(data):
        blob = m.group(1)
        try:
            yield zlib.decompress(blob)
            continue
        except zlib.error:
            pass
        try:
            yield zlib.decompressobj().decompress(blob)     # a stream truncated by a bad length
            continue
        except zlib.error:
            pass
        if b"Tj" in blob or b"TJ" in blob:
            yield blob                                      # uncompressed content stream


def extract_text(data: bytes, max_chars: int = 120000, max_streams: int = 80) -> str:
    """The visible text, in reading order as far as the operators give one.

    Both bounds matter for a folder of real documents: a design-heavy PDF can decompress to tens
    of megabytes of drawing operators that hold no text at all, and scanning it to the end would
    cost more than every receipt in the folder put together.
    """
    if not data.startswith(b"%PDF"):
        raise Unreadable("not a PDF")
    parts = []
    size = 0
    for index, content in enumerate(_streams(data)):
        if size > max_chars or index >= max_streams:
            break
        if len(content) > 4 * 1024 * 1024:
            content = content[:4 * 1024 * 1024]
        if b"Tj" not in content and b"TJ" not in content:
            continue
        for chunk in re.split(BREAK, content):
            if b"Tj" not in chunk and b"TJ" not in chunk:
                continue
            line = []
            for lit in LITERAL.finditer(chunk):
                line.append(_decode(_unescape(lit.group(0)[1:-1])))
            for m in HEXSTR.finditer(chunk):
                digits = re.sub(rb"\s", b"", m.group(1))
                if len(digits) % 2 == 0:
                    try:
                        line.append(_decode(bytes.fromhex(digits.decode("ascii"))))
                    except ValueError:
                        pass
            if line:
                text = "".join(line)
                parts.append(text)
                size += len(text)
    out = "\n".join(p for p in parts if p.strip())
    if not out.strip():
        raise Unreadable("no extractable text; likely a scan or a custom font encoding")
    return out[:max_chars]
