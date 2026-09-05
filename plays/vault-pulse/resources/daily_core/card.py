"""One 64-column card, drawn the same way by all six Plays.

A terminal card is the whole product for most of these Plays, so the drawing rules live in one
place: rows are padded on display width (a CJK title is two columns per glyph, and an ANSI colour
sequence is zero), sections are cut into the frame rather than shouted above it, and every value
that can be a bar gets one, because a share is read faster than a percentage.
"""
from .common import display_width, ellipsis, trunc

W = 64
INNER = W - 4


class Card:
    def __init__(self, title: str, right: str = "", color: bool = False):
        self.color = color
        self.lines = ["┌" + "─" * (W - 2) + "┐"]
        gap = INNER - display_width(title) - display_width(right)
        self.row(title + " " * max(1, gap) + right if right else title)

    # -- primitives ----------------------------------------------------

    def row(self, text: str = "", invisible: int = 0):
        """One framed row, clipped to the frame. `invisible` counts characters that take no column."""
        if invisible == 0:
            text = trunc(text, INNER)
        pad = INNER - (display_width(text) - invisible)
        self.lines.append("│ " + text + " " * max(pad, 0) + " │")
        return self

    def blank(self):
        return self.row("")

    def rule(self, label: str):
        body = "─ {0} ".format(label)
        self.lines.append("├" + body + "─" * max(0, W - 2 - display_width(body)) + "┤")
        return self

    def paint(self, text: str, code: str) -> tuple:
        """(text, invisible-width) so `row` can pad a coloured string correctly."""
        return ("\x1b[{0}m{1}\x1b[0m".format(code, text), len(code) + 7) if self.color else (text, 0)

    # -- composites ----------------------------------------------------

    def headline(self, text: str, code: str = "1;36"):
        return self.row(*self.paint(ellipsis(text, INNER), code))

    def note(self, text: str):
        return self.row(ellipsis(text, INNER)) if text else self

    def wrap(self, text: str, indent: str = ""):
        """Fill to the card width on word boundaries, so a sentence is never cut mid-word."""
        words, line = str(text).split(), indent
        for w in words:
            candidate = (line + " " + w) if line.strip() else (indent + w)
            if display_width(candidate) > INNER and line.strip():
                self.row(line)
                line = indent + w
            else:
                line = candidate
        if line.strip():
            self.row(line)
        return self

    def bar(self, label: str, value: str, share: float, width: int = 12, label_w: int = 24):
        blocks = "▇" * max(0, min(width, int(round((share or 0.0) * width))))
        text = "{0} {1:>10}  {2:>3}% {3}".format(
            pad(ellipsis(label, label_w), label_w), value, int(round((share or 0.0) * 100)), blocks)
        return self.row(trunc(text, INNER))

    def kv(self, label: str, value: str, label_w: int = 26):
        return self.row(trunc("{0}{1}".format(pad(ellipsis(label, label_w), label_w + 1), value), INNER))

    def cols(self, left: str, right: str, right_w: int = 14):
        left = ellipsis(left, INNER - right_w - 1)
        gap = INNER - display_width(left) - display_width(right)
        return self.row(left + " " * max(1, gap) + right)

    def bullet(self, text: str, mark: str = "·"):
        return self.wrap(text, "") if display_width(text) + 2 <= INNER else self.wrap(text)

    def table(self, rows, widths):
        for cells in rows:
            parts = [pad(ellipsis(str(c), w), w) if w > 0 else str(c).rjust(-w)[:(-w)] for c, w in zip(cells, widths)]
            self.row(trunc(" ".join(parts).rstrip(), INNER))
        return self

    def close(self) -> str:
        self.lines.append("└" + "─" * (W - 2) + "┘")
        return "\n".join(self.lines)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - display_width(s))


def rpad(s: str, width: int) -> str:
    return " " * max(0, width - display_width(s)) + s


def sparkline(values, width: int = 24) -> str:
    """A trend in one row. Empty when there is nothing to compare, never a flat fake line."""
    vals = [float(v or 0) for v in values][-width:]
    if len(vals) < 2 or max(vals) <= 0:
        return ""
    glyphs = "▁▂▃▄▅▆▇█"
    top = max(vals)
    return "".join(glyphs[min(len(glyphs) - 1, int(round(v / top * (len(glyphs) - 1))))] for v in vals)


def bucket_bars(counts, labels, width: int = 20) -> list:
    """Aligned rows for an age or size histogram, sharing one scale so the bars are comparable."""
    top = max(counts) if counts and max(counts) else 1
    return ["{0} {1:>6}  {2}".format(pad(l, 12), c, "▇" * max(0 if not c else 1, int(round(c / top * width))))
            for l, c in zip(labels, counts)]
