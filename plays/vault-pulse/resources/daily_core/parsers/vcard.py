"""vCard 2.1/3.0/4.0, enough of it to answer questions about people you already have.

The format is line-oriented but folded: a line beginning with a space or tab continues the one
before it, so unfolding has to happen before anything is split. Property names carry parameters
(`BDAY;VALUE=date:--0704`), values are escaped, and the same property may appear many times.
"""
import re
import quopri

_LINE = re.compile(r"^([A-Za-z0-9.\-]+)((?:;[^:]*)?):(.*)$", re.S)


def unfold(text: str):
    out = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\")


def parse(text: str) -> list:
    """Return one dict per card: name, org, bday, emails, tels, rev (last revision), raw property count."""
    cards, cur = [], None
    for line in unfold(text):
        m = _LINE.match(line.strip())
        if not m:
            continue
        prop, params, value = m.group(1).upper().split(".")[-1], m.group(2).upper(), m.group(3)
        if prop == "BEGIN" and value.strip().upper() == "VCARD":
            cur = {"name": "", "org": "", "bday": "", "emails": [], "tels": [], "rev": "", "props": 0,
                   "note": False, "photo": False}
            continue
        if cur is None:
            continue
        if prop == "END":
            if cur["name"] or cur["emails"] or cur["tels"]:
                cards.append(cur)
            cur = None
            continue
        cur["props"] += 1
        if "ENCODING=QUOTED-PRINTABLE" in params:
            try:
                value = quopri.decodestring(value.encode("utf-8", "replace")).decode("utf-8", "replace")
            except (ValueError, UnicodeDecodeError):
                pass
        value = _unescape(value).strip()
        if prop == "FN" and value:
            cur["name"] = value
        elif prop == "N" and not cur["name"]:
            parts = [p.strip() for p in value.split(";")]
            cur["name"] = " ".join(p for p in (parts[1:2] + parts[0:1]) if p)
        elif prop == "ORG":
            cur["org"] = value.split(";")[0].strip()
        elif prop in ("BDAY", "ANNIVERSARY") and prop == "BDAY":
            cur["bday"] = value
        elif prop == "EMAIL" and value:
            cur["emails"].append(value.lower())
        elif prop == "TEL" and value:
            cur["tels"].append(re.sub(r"[^\d+]", "", value))
        elif prop == "REV":
            cur["rev"] = value
        elif prop == "NOTE":
            cur["note"] = bool(value)
        elif prop == "PHOTO":
            cur["photo"] = True
    return cards


def parse_bday(value: str):
    """(month, day, year-or-None). A vCard may omit the year, and most contact apps do.

    Accepts 1985-07-04, 19850704, --07-04, --0704 and the T-suffixed forms Apple writes.
    """
    v = str(value or "").strip().split("T")[0]
    if not v:
        return None
    m = re.match(r"^--(\d{2})-?(\d{2})$", v)
    if m:
        month, dayn, year = int(m.group(1)), int(m.group(2)), None
    else:
        m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", v)
        if not m:
            return None
        year, month, dayn = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 1900:
            year = None
    if not (1 <= month <= 12 and 1 <= dayn <= 31):
        return None
    return month, dayn, year
