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


def heatmap(grid, row_labels, col_labels=(), width_per_col: int = 1) -> list:
    """A day-by-hour (or any two-dimensional) count grid, shaded by share of the busiest cell.

    One scale across the whole grid, not per row: the point of a heatmap is that Tuesday 3am is
    comparable to Wednesday 3pm, and a per-row scale quietly destroys exactly that.
    """
    glyphs = " ░▒▓█"
    flat = [c for row in grid for c in row]
    top = max(flat) if flat and max(flat) else 0
    out = []
    if col_labels:
        out.append(" " * 4 + "".join(str(c)[:width_per_col].ljust(width_per_col) for c in col_labels))
    for label, row in zip(row_labels, grid):
        cells = "".join(
            (glyphs[min(len(glyphs) - 1, int(round((c / top) * (len(glyphs) - 1))))] if top else " ")
            * width_per_col for c in row)
        out.append("{0} {1}".format(pad(str(label)[:3], 3), cells))
    return out


def tier_bar(tiers, width: int = 40) -> str:
    """One row that spends its width proportionally between named tiers, worst-first.

    Used wherever a total is only meaningful once it is split — reach levels, confidence tiers,
    survival classes. Every tier with a non-zero count gets at least one column, so a small but
    real number never disappears into a rounding error.
    """
    counts = [max(0, int(c)) for _, c in tiers]
    total = sum(counts)
    if not total:
        return ""
    glyphs = "█▓▒░·"
    widths, spent = [], 0
    for i, c in enumerate(counts):
        w = 0 if not c else max(1, int(round(c / total * width)))
        widths.append(w)
        spent += w
    while spent > width:                                # give back from the widest first
        widest = widths.index(max(widths))
        widths[widest] -= 1
        spent -= 1
    return "".join(glyphs[min(i, len(glyphs) - 1)] * w for i, w in enumerate(widths))


def legend(tiers) -> str:
    """The key for a tier_bar, in the same order, so the glyphs mean something."""
    glyphs = "█▓▒░·"
    return "  ".join("{0} {1}".format(glyphs[min(i, len(glyphs) - 1)], name)
                     for i, (name, count) in enumerate(tiers) if count)
