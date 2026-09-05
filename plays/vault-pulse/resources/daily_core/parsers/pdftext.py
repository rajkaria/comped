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
OBJECT = re.compile(rb"(\d{1,7})\s+\d+\s+obj\b(.*?)\bendobj", re.S)
RESOURCE_FONTS = re.compile(rb"/Font\s*<<(.*?)>>", re.S)
FONT_REF = re.compile(rb"/([A-Za-z0-9#+.\-]{1,40})\s+(\d{1,7})\s+\d+\s+R")
TOUNICODE = re.compile(rb"/ToUnicode\s+(\d{1,7})\s+\d+\s+R")
SET_FONT = re.compile(rb"/([A-Za-z0-9#+.\-]{1,40})\s+[-\d.]+\s+Tf")
BFCHAR = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
BFRANGE = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
HEXTOKEN = re.compile(rb"<([0-9A-Fa-f]*)>")
ANYHEX = re.compile(rb"<([0-9A-Fa-f\s]{2,})>")
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


def _object_bodies(data: bytes) -> dict:
    return {int(m.group(1)): m.group(2) for m in OBJECT.finditer(data)}


def _stream_of(body: bytes) -> bytes:
    m = STREAM.search(body)
    if not m:
        return b""
    blob = m.group(1)
    try:
        return zlib.decompress(blob)
    except zlib.error:
        try:
            return zlib.decompressobj().decompress(blob)
        except zlib.error:
            return blob


def _utf16be(hexdigits: bytes) -> str:
    raw = bytes.fromhex(hexdigits.decode("ascii")) if len(hexdigits) % 2 == 0 else b""
    return raw.decode("utf-16-be", "replace") if raw else ""


def parse_cmap(text: bytes) -> dict:
    """A ToUnicode CMap: glyph code -> the characters it stands for.

    Two forms carry the mapping. `beginbfchar` pairs a source code with its destination, and
    `beginbfrange` gives a low and high source with either a starting destination that increments
    or an explicit array of destinations, one per code in the range.
    """
    out = {}
    for block in BFCHAR.findall(text):
        tokens = HEXTOKEN.findall(block)
        for src, dst in zip(tokens[0::2], tokens[1::2]):
            try:
                out[int(src, 16)] = _utf16be(dst)
            except ValueError:
                continue
    for block in BFRANGE.findall(text):
        for m in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[(?:[^\]]*)\]|<[0-9A-Fa-f]*>)",
                             block, re.S):
            try:
                lo, hi = int(m.group(1), 16), int(m.group(2), 16)
            except ValueError:
                continue
            if hi < lo or hi - lo > 65535:
                continue
            target = m.group(3)
            if target.startswith(b"["):
                for offset, dst in enumerate(HEXTOKEN.findall(target)):
                    if lo + offset <= hi:
                        out[lo + offset] = _utf16be(dst)
            else:
                start = _utf16be(target[1:-1])
                if not start:
                    continue
                base = ord(start[-1])
                for offset in range(hi - lo + 1):
                    out[lo + offset] = start[:-1] + chr(base + offset)
    return out


def font_maps(data: bytes) -> dict:
    """Resource name (F1, TT0, …) -> its ToUnicode map, for every font that declares one."""
    bodies = _object_bodies(data)
    by_object = {}
    for number, body in bodies.items():
        m = TOUNICODE.search(body)
        if not m:
            continue
        target = bodies.get(int(m.group(1)))
        if target is None:
            continue
        try:
            table = parse_cmap(_stream_of(target))
        except (ValueError, zlib.error):
            continue
        if table:
            by_object[number] = table
    if not by_object:
        return {}
    named = {}
    for body in bodies.values():
        for block in RESOURCE_FONTS.findall(body):
            for name, number in FONT_REF.findall(block):
                table = by_object.get(int(number))
                if table:
                    named.setdefault(name.decode("latin-1"), table)
    # A font whose resource name was never found still helps: one document, one fallback table.
    if not named and len(by_object) == 1:
        named["*"] = next(iter(by_object.values()))
    return named


def _apply_cmap(hexdigits: bytes, table: dict) -> str:
    """Map glyph codes through the table. Two bytes per code is overwhelmingly the common case."""
    raw = re.sub(rb"\s", b"", hexdigits)
    if len(raw) % 2:
        raw += b"0"
    try:
        codes = bytes.fromhex(raw.decode("ascii"))
    except ValueError:
        return ""
    if len(codes) >= 2 and all((codes[i] << 8 | codes[i + 1]) in table for i in range(0, len(codes) - 1, 2)):
        return "".join(table[codes[i] << 8 | codes[i + 1]] for i in range(0, len(codes) - 1, 2))
    if all(c in table for c in codes):
        return "".join(table[c] for c in codes)
    return ""


TOKEN = re.compile(rb"""
      (?P<lit>\((?:\\.|[^\\()])*\))
    | (?P<hex><[0-9A-Fa-f\s]*>)
    | (?P<num>[-+]?\d*\.?\d+)
    | (?P<name>/[^\s/<>\[\]()]{0,60})
    | (?P<arr>[\[\]])
    | (?P<op>[A-Za-z'\"*][A-Za-z0-9'\"*]{0,4})
""", re.X | re.S)


# Widths in ems, close enough to Helvetica that the pen keeps up with the glyphs. Without this an
# "m" is under-counted, the pen falls behind, and every wide letter earns a space it never had.
_NARROW = set("iljtfrI.,'\";:!|()[]{}` ")
_WIDE = set("mwMW@%&")


def _width(text: str) -> float:
    total = 0.0
    for ch in text:
        total += 0.28 if ch in _NARROW else 0.86 if ch in _WIDE else \
            0.68 if ch.isupper() else 0.55 if ch.isdigit() else 0.5
    return total


class _Text:
    """Reconstructs lines from the text matrix, because a PDF has no concept of a line of text.

    Every glyph is placed at a coordinate. A document that draws one character per placement is
    common, and joining those placements naively produces one character per line, or one long word
    with the spaces gone. So the pen is tracked: a change in y starts a new line, and a gap in x
    wider than the pen should have travelled is the space that was never drawn.
    """

    def __init__(self):
        self.lines, self.line = [], []
        self.x = self.y = self.pen = 0.0
        self.line_x = self.line_y = 0.0
        self.size, self.scale, self.leading = 12.0, 1.0, 12.0
        self.started = False

    def font(self, size):
        self.size = abs(size) or 12.0

    def matrix(self, ops):
        if len(ops) >= 6:
            self.scale = abs(ops[-6]) or 1.0
            self.line_x, self.line_y = ops[-2], ops[-1]
            self.move_to(self.line_x, self.line_y)

    def offset(self, dx, dy):
        self.line_x += dx
        self.line_y += dy
        self.move_to(self.line_x, self.line_y)

    def next_line(self):
        self.line_y -= self.leading
        self.move_to(self.line_x, self.line_y)

    def move_to(self, x, y):
        em = max(1.0, self.size * self.scale)
        if self.started and abs(y - self.y) > 0.3 * em:
            self.flush()
        elif self.started and x - self.pen > 0.3 * em:
            self.line.append(" ")
        self.x, self.y, self.pen = x, y, x

    def shift(self, thousandths):
        # A kern wider than a fifth of an em is how a PDF writes a space inside a TJ array.
        em = max(1.0, self.size * self.scale)
        self.pen -= thousandths / 1000.0 * em
        if thousandths > 180:
            self.line.append(" ")

    def show(self, text):
        if not text:
            return
        self.started = True
        self.line.append(text)
        self.pen += _width(text) * self.size * self.scale

    def flush(self):
        joined = "".join(self.line).strip()
        if joined:
            self.lines.append(joined)
        self.line = []

    def result(self):
        self.flush()
        return "\n".join(self.lines)


def _read_stream(content: bytes, maps: dict, out: _Text) -> None:
    stack, array, font = [], False, ""
    for m in TOKEN.finditer(content):
        kind = m.lastgroup
        raw = m.group()
        if kind == "num":
            try:
                value = float(raw)
            except ValueError:
                continue
            if array:
                out.shift(-value)
            else:
                stack.append(value)
            continue
        if kind == "arr":
            array = raw == b"["
            continue
        if kind in ("lit", "hex"):
            stack.append(raw)
            if array:
                out.show(_show_text(raw, maps.get(font) or maps.get("*") or {}))
            continue
        if kind == "name":
            stack.append(raw)
            continue
        if kind != "op":
            continue
        op = raw
        if op == b"Tf":
            names = [t for t in stack if isinstance(t, bytes) and t.startswith(b"/")]
            if names:
                font = names[-1][1:].decode("latin-1")
            numbers = [t for t in stack if isinstance(t, float)]
            out.font(numbers[-1] if numbers else 12.0)
        elif op == b"Tm":
            out.matrix([t for t in stack if isinstance(t, float)])
        elif op in (b"Td", b"TD"):
            numbers = [t for t in stack if isinstance(t, float)]
            if len(numbers) >= 2:
                out.offset(numbers[-2], numbers[-1])
            if op == b"TD" and numbers:
                out.leading = -numbers[-1]
        elif op == b"TL":
            numbers = [t for t in stack if isinstance(t, float)]
            if numbers:
                out.leading = numbers[-1]
        elif op in (b"T*", b"'", b'"'):
            out.next_line()
        if op in (b"Tj", b"'", b'"'):
            strings = [t for t in stack if isinstance(t, bytes) and t[:1] in (b"(", b"<")]
            if strings:
                out.show(_show_text(strings[-1], maps.get(font) or maps.get("*") or {}))
        elif op == b"BT":
            out.flush()
            out.line_x = out.line_y = 0.0
        elif op == b"ET":
            out.flush()
        stack = []


def _show_text(token: bytes, table: dict) -> str:
    if token.startswith(b"("):
        return _decode(_unescape(token[1:-1]))
    digits = re.sub(rb"\s", b"", token[1:-1])
    if table:
        return _apply_cmap(digits, table)
    if len(digits) % 2 == 0 and digits:
        try:
            return _decode(bytes.fromhex(digits.decode("ascii")))
        except ValueError:
            return ""
    return ""


def extract_text(data: bytes, max_chars: int = 120000, max_streams: int = 80) -> str:
    """The visible text, laid back out into lines from the coordinates each glyph was placed at.

    Both bounds matter for a folder of real documents: a design-heavy PDF can decompress to tens
    of megabytes of drawing operators that hold no text at all, and scanning it to the end would
    cost more than every receipt in the folder put together.
    """
    if not data.startswith(b"%PDF"):
        raise Unreadable("not a PDF")
    maps = font_maps(data)
    out = _Text()
    for index, content in enumerate(_streams(data)):
        if index >= max_streams or len("".join(out.lines)) > max_chars:
            break
        if b"Tj" not in content and b"TJ" not in content:
            continue
        if len(content) > 2 * 1024 * 1024:
            content = content[:2 * 1024 * 1024]
        _read_stream(content, maps, out)
    text = out.result()
    if not text.strip():
        raise Unreadable("no extractable text; likely a scan or a custom font encoding")
    if legibility(text) < 0.75:
        # The strings came out, but as the font's own glyph indices rather than characters. Every
        # figure read from this would be fiction, so the document is reported unreadable instead.
        raise Unreadable("text decoded to glyph codes; the fonts use a custom encoding")
    return text[:max_chars]


def legibility(text: str) -> float:
    """The share of characters that belong in prose. A custom font encoding scores near zero."""
    sample = text[:4000]
    if not sample:
        return 0.0
    good = sum(1 for ch in sample if ch.isalnum() or ch.isspace() or ch in ".,:;!?@#%&*()[]{}-_+=/\\'\"$£€₹¥")
    return good / len(sample)
