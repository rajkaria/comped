"""How big is that, and what does it cost to send.

The bytes, lines and words are facts. The token count is not: there is no tokenizer in the standard
library, and a single confident number would be a lie dressed as precision. So this prints a RANGE
from a stated character-class model, and the model is in the output next to the number. Anything
that turns out to matter — a bill, a window that will not fit — is bracketed by the range rather
than decided by a point estimate.
"""
import re
import unicodedata
from decimal import Decimal

WORD = re.compile(r"\S+")
CJK = ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF))
METHOD = ("character-class estimate: ASCII prose ≈ 4.0 chars/token, punctuation-dense code ≈ 3.1, "
          "CJK ≈ 1.0 token/char; band ±15%, widened to ±25% when the text is mostly non-ASCII")


def measure(text):
    body = str(text or "")
    lines = body.count("\n") + (0 if body.endswith("\n") or not body else 1)
    return {"bytes": len(body.encode("utf-8")), "chars": len(body),
            "lines": max(lines, 1 if body else 0), "words": len(WORD.findall(body))}


def _is_cjk(ch):
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in CJK)


def token_range(text):
    """(low, mid, high). Monotonic in length, denser for code and for CJK, honest about the band."""
    body = str(text or "")
    if not body:
        return (0, 0, 0)
    cjk = sum(1 for ch in body if _is_cjk(ch))
    rest = [ch for ch in body if not _is_cjk(ch)]
    dense = sum(1 for ch in rest if not ch.isalnum() and not ch.isspace())
    ratio = dense / float(len(rest)) if rest else 0.0
    # More punctuation per character means shorter merges: code tokenizes denser than prose.
    chars_per_token = 4.0 - 0.9 * min(1.0, ratio / 0.30)
    mid = int(round(cjk * 1.0 + len(rest) / chars_per_token))
    non_ascii = sum(1 for ch in body if ord(ch) > 127)
    spread = 0.25 if non_ascii > 0.2 * len(body) else 0.15
    return (max(0, int(mid * (1 - spread))), max(mid, 1), int(round(mid * (1 + spread))))


def window_fit(mid, window):
    window = max(1, int(window))
    return {"fits": mid <= window, "pct": int(round(mid * 100.0 / window)),
            "headroom": window - mid, "window": window}


def costs(low, high, models, table):
    """Input-side cost per model. A model the table does not know is named, never priced at zero."""
    from comped_core.prices import rate_for, resolve_model
    rows = []
    for name in models:
        name = str(name).strip()
        if not name:
            continue
        rate = rate_for(name, table)
        if rate is None:
            rows.append({"model": name, "resolved": None,
                         "note": "not in the price table — no rate is better than a wrong one"})
            continue
        rows.append({"model": name, "resolved": resolve_model(name, table),
                     "low_usd": str((Decimal(low) * rate["in"]).quantize(Decimal("0.0001"))),
                     "high_usd": str((Decimal(high) * rate["in"]).quantize(Decimal("0.0001"))),
                     "per_mtok_usd": str((rate["in"] * Decimal(1000000)).quantize(Decimal("0.01")))})
    return rows


def describe_shape(text):
    """A one-line hint at what the text is, so a paste of the wrong thing is visible immediately."""
    body = str(text or "")
    if not body.strip():
        return "empty"
    stripped = body.lstrip()
    if stripped[0] in "{[":
        return "looks like JSON"
    if stripped.startswith("<"):
        return "looks like markup"
    if sum(1 for l in body.split("\n")[:40] if l.startswith(("  ", "\t"))) > 8:
        return "looks like indented code"
    if unicodedata.category(stripped[0]).startswith("L") and body.count("\n\n") > 2:
        return "looks like prose"
    return "plain text"
