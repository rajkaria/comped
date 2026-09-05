"""receipt-ledger: the receipts already on your disk, totalled by vendor and by month.

Every purchase leaves a file somewhere — a PDF invoice, a saved confirmation page, an exported
message — and none of them are ever added up because they are four formats in one folder. This
reads all four, pulls the vendor, the date and the amount from each, and totals them per currency,
never across currencies, because a single number spanning three currencies would be a fiction.

Nothing here logs in to anything. It reads files you already have.
"""
import email
import email.policy
import html as htmlmod
import re
from collections import Counter, defaultdict

from ..common import (Budget, Source, day, expand, from_unix, iso, month, parse_date, read_bytes,
                      read_text, walk)
from ..parsers import pdftext

KINDS = ("files", "mail")
EXTENSIONS = (".pdf", ".eml", ".html", ".htm", ".txt", ".msg", ".mhtml")
SKIP = (".DS_Store", "node_modules", ".git")

SYMBOLS = {"$": "USD", "US$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY", "₽": "RUB",
           "R$": "BRL", "A$": "AUD", "C$": "CAD", "CHF": "CHF", "kr": "SEK", "₩": "KRW", "₪": "ILS"}
CODES = ("USD", "EUR", "GBP", "INR", "JPY", "AUD", "CAD", "CHF", "SGD", "AED", "SEK", "NOK", "DKK",
         "PLN", "BRL", "MXN", "ZAR", "NZD", "HKD", "CNY", "KRW", "ILS", "TRY")

MONEY = re.compile(
    r"(?:(?P<code>\b(?:" + "|".join(CODES) + r")\b)\s*|(?P<sym>R\$|A\$|C\$|US\$|[$£€₹¥₽₩₪]))\s*"
    r"(?P<amount>\d{1,3}(?:[,   ]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"|(?P<amount2>\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s*(?P<code2>\b(?:" + "|".join(CODES) + r")\b)")
TOTAL_WORD = re.compile(
    r"(grand\s+total|amount\s+(?:due|paid|charged)|total\s+(?:due|paid|charged|amount)|order\s+total|"
    r"you\s+paid|charged|total)\b", re.I)
REFUND = re.compile(r"\b(refund|credit note|reversed|cancelled|canceled|voided)\b", re.I)
SUBSCRIPTION = re.compile(r"\b(subscription|renew(?:al|s|ed)?|monthly plan|annual plan|billing period|recurring)\b", re.I)
TAG = re.compile(r"<[^>]{0,4000}>", re.S)
SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
RECEIPTISH = re.compile(r"receipt|invoice|order|payment|billing|purchase|statement|subscription", re.I)
# A document is a receipt when it says so. A pitch deck with a large dollar figure is not one, and
# the difference is vocabulary that only ever appears on something that charged you.
EVIDENCE = [
    ("invoice number", re.compile(r"\binvoice\s*(?:no\.?|number|#)", re.I)),
    ("receipt number", re.compile(r"\breceipt\s*(?:no\.?|number|#|for)", re.I)),
    ("order number", re.compile(r"\border\s*(?:no\.?|number|#|confirmation)", re.I)),
    ("amount due", re.compile(r"\bamount\s+(?:due|paid|charged)\b", re.I)),
    ("subtotal", re.compile(r"\bsub[\s-]?total\b", re.I)),
    ("tax line", re.compile(r"\b(vat|gst|sales tax|tax\s*\(|tax:)\b", re.I)),
    ("payment method", re.compile(r"\b(payment method|card ending|paid with|visa ending|mastercard|"
                                  r"charged to|billed to|bill to)\b", re.I)),
    ("transaction id", re.compile(r"\b(transaction|payment)\s*(?:id|reference|ref)\b", re.I)),
    ("billing period", re.compile(r"\b(billing period|next billing|renews on|service period)\b", re.I)),
    ("thanks for paying", re.compile(r"\b(thank you for your (?:order|payment|purchase)|"
                                     r"your (?:receipt|invoice) from)\b", re.I)),
]


NEGATED = re.compile(r"\b(no|not|without|any)\s*$", re.I)


def receipt_evidence(text: str, confidence: str) -> list:
    """What in this document says it is a receipt. An empty list means it is not treated as one.

    Two guards keep prose out. A phrase introduced by a negation ("no invoice number") is not
    evidence of an invoice, and a single incidental phrase is not enough on its own: without an
    amount sitting on a total line, a document has to say it twice before it counts.
    """
    head = text[:20000]
    found = []
    for name, pattern in EVIDENCE:
        m = pattern.search(head)
        if m and not NEGATED.search(head[max(0, m.start() - 12):m.start()]):
            found.append(name)
    if confidence == "total line":
        return ["a total line with an amount"] + found
    return found if len(found) >= 2 else []


def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    demo = cfg.get("demo_root")
    if demo and kind == "mail":
        # The demo has one folder of documents; reading it twice would double every total.
        return [Source(name="mail (demo)", path=str(demo)).hit(0, "the demo reads one folder")], []
    root = expand(demo) if demo else expand(
        cfg.get("receipts_dir") or ("~/Library/Mail" if kind == "mail" else "~/Downloads"))
    src = Source(name="{0}{1}".format(kind, " (demo)" if demo else ""), path=str(root))
    if not root.is_dir():
        return [src.miss("no folder at {0}".format(root))], []
    try:
        next(iter(root.iterdir()), None)
    except PermissionError:
        return [src.miss("macOS blocked the read; grant Full Disk Access, or point receipts_dir elsewhere")], []

    docs, looked, unreadable, rejected = [], 0, 0, 0
    for path, st, _ in walk(root, budget, skip_names=SKIP):
        if path.suffix.lower() not in EXTENSIONS or st.st_size > 24 * 1024 * 1024:
            continue
        looked += 1
        parsed = _read_one(path, st, budget)
        if parsed is None:
            unreadable += 1
        elif parsed.get("evidence_kinds"):
            docs.append(parsed)
        else:
            rejected += 1
    note = "{0} candidate file(s), {1} were receipts".format(looked, len(docs))
    if rejected:
        note += ", {0} had no receipt wording".format(rejected)
    if unreadable:
        note += ", {0} unreadable".format(unreadable)
    if not looked:
        return [src.miss("no PDF, email or saved page under {0}".format(root))], []
    return [src.hit(len(docs), note)], docs


def _read_one(path, st, budget: Budget):
    suffix = path.suffix.lower()
    sender = subject = ""
    when = None
    try:
        if suffix == ".pdf":
            data = read_bytes(path, 24 * 1024 * 1024)
            budget.spend(len(data))
            text = pdftext.extract_text(data)
        elif suffix in (".eml", ".msg", ".mhtml"):
            data = read_bytes(path, 24 * 1024 * 1024)
            budget.spend(len(data))
            text, sender, subject, when = _read_email(data)
        else:
            raw = read_text(path, 8 * 1024 * 1024)
            budget.spend(len(raw))
            text = strip_html(raw) if suffix in (".html", ".htm") else raw
            subject = _html_title(raw) if suffix in (".html", ".htm") else ""
    except (pdftext.Unreadable, OSError, ValueError):
        return None
    if not text or not text.strip():
        return None

    amount, currency, evidence, confidence = find_amount(text)
    kinds = receipt_evidence(text, confidence) if amount is not None else []
    stamp = when or _date_in(text) or from_unix(st.st_mtime)
    vendor, how = guess_vendor(sender, subject, path.name, text)
    return {"file": path.name, "ext": suffix, "vendor": vendor, "vendor_from": how,
            "amount": amount, "currency": currency, "evidence": evidence, "confidence": confidence,
            "date": iso(stamp), "date_from": "message header" if when else
            ("text" if _date_in(text) else "file modification time"),
            "evidence_kinds": kinds,
            "refund": bool(REFUND.search(text[:4000])),
            "subscription": bool(SUBSCRIPTION.search(text[:8000])),
            "subject": subject[:120], "text_head": text[:400]}


def _read_email(data: bytes) -> tuple:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    parts = []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            body = part.get_content()
        except (LookupError, ValueError, KeyError):
            continue
        parts.append(strip_html(body) if ctype == "text/html" else str(body))
    sender = str(msg.get("From") or "")
    when = parse_date(str(msg.get("Date") or "")) or _rfc2822(str(msg.get("Date") or ""))
    return "\n".join(parts), sender, str(msg.get("Subject") or ""), when


def _rfc2822(value: str):
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    from datetime import timezone
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def strip_html(text: str) -> str:
    return htmlmod.unescape(TAG.sub(" ", SCRIPT.sub(" ", str(text or ""))))


def _html_title(raw: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    return htmlmod.unescape(TAG.sub("", m.group(1))).strip() if m else ""


def _date_in(text: str):
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text[:6000])
    if m:
        return parse_date(m.group(1))
    m = re.search(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", text[:6000])
    if m:
        return parse_date("{0} {1} {2}".format(m.group(1), m.group(2), m.group(3)).replace(
            m.group(2), str(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                             "Dec"].index(m.group(2)) + 1).zfill(2)).replace(" ", "-")[:10])
    return None


def find_amount(text: str) -> tuple:
    """The amount actually charged, preferring a figure a total word points at.

    A receipt holds many numbers: line items, tax, shipping, a loyalty balance. The charged amount
    is the one on a line that says total, amount due or you paid. When no such line exists this
    falls back to the largest figure and says so, so a fallback is never mistaken for a reading.
    """
    best = None
    for line in str(text).splitlines():
        if not line.strip():
            continue
        totalish = TOTAL_WORD.search(line)
        for m in MONEY.finditer(line):
            raw = m.group("amount") or m.group("amount2")
            code = m.group("code") or m.group("code2") or SYMBOLS.get((m.group("sym") or "").strip(), "")
            try:
                value = float(re.sub(r"[,   ]", "", raw))
            except ValueError:
                continue
            if value <= 0 or value > 10 ** 9:
                continue
            rank = (2 if totalish else 1, value)
            if best is None or rank > best[0]:
                best = (rank, value, code or "", line.strip()[:80], "total line" if totalish else "largest figure")
    if best is None:
        return None, "", "", "none"
    return round(best[1], 2), best[2], best[3], best[4]


def guess_vendor(sender: str, subject: str, filename: str, text: str) -> tuple:
    """Who charged you, from the strongest evidence available, and which evidence that was."""
    m = re.search(r"<([^@>]+)@([^>]+)>", sender) or re.search(r"([^\s@]+)@([^\s>]+)", sender)
    if m:
        domain = m.group(2).lower().strip(">.")
        from ..common import registrable
        base = registrable(domain).split(".")[0]
        skip = {"gmail", "googlemail", "outlook", "hotmail", "yahoo", "icloud", "me", "proton"}
        if base and base not in skip:
            return base.title(), "sender domain"
    display = re.sub(r"<[^>]*>", "", sender).strip().strip('"')
    if display and "@" not in display:
        return display[:40], "sender name"
    for line in [l.strip() for l in str(text).splitlines() if l.strip()][:4]:
        if 2 < len(line) < 48 and not MONEY.search(line) and not RECEIPTISH.search(line):
            return line[:40], "first line of the document"
    stem = re.split(r"[_\-\s]", re.sub(r"\.[a-z0-9]+$", "", filename))
    words = [w for w in stem if w and not w.isdigit() and not RECEIPTISH.fullmatch(w)]
    if words and len(words[0]) > 2:
        return words[0][:40].title(), "file name"
    return "(unknown)", "nothing identified it"


# ---------------------------------------------------------------- analysis

def analyse(docs: list, now, months_back: int) -> dict:
    from datetime import timedelta
    cutoff = now - timedelta(days=31 * months_back)
    priced = [d for d in docs if d.get("amount") is not None]
    inside = [d for d in priced if d["date"] and parse_date(d["date"]) >= cutoff]

    by_currency = defaultdict(float)
    per_currency_count = Counter()
    by_vendor = defaultdict(lambda: defaultdict(float))
    counts = Counter()
    by_month = defaultdict(lambda: defaultdict(float))
    vendor_months = defaultdict(set)
    for d in inside:
        cur = d["currency"] or "?"
        sign = -1.0 if d["refund"] else 1.0
        by_currency[cur] += sign * d["amount"]
        per_currency_count[cur] += 1
        by_vendor[d["vendor"]][cur] += sign * d["amount"]
        counts[d["vendor"]] += 1
        by_month[month(parse_date(d["date"]))][cur] += sign * d["amount"]
        vendor_months[d["vendor"]].add(month(parse_date(d["date"])))

    recurring = sorted(((v, sorted(ms)) for v, ms in vendor_months.items() if len(ms) >= 3),
                       key=lambda kv: -len(kv[1]))
    seen, dupes = {}, []
    for d in inside:
        key = (d["vendor"], round(d["amount"], 2), (d["date"] or "")[:10], d["currency"])
        seen.setdefault(key, []).append(d)
    for key, group in seen.items():
        if len(group) > 1:
            dupes.append({"vendor": key[0], "amount": key[1], "currency": key[3], "date": key[2],
                          "copies": len(group), "files": sorted(g["file"] for g in group)[:4]})

    top = sorted(((v, dict(c), counts[v]) for v, c in by_vendor.items()),
                 key=lambda kv: -max(kv[1].values() or [0]))[:8]
    newest = max((d["date"] for d in priced if d["date"]), default="")
    return {
        "documents": len(docs), "priced": len(priced), "in_window": len(inside),
        "newest": newest[:10], "outside_window": len(priced) - len(inside),
        "unpriced": len(docs) - len(priced), "months_back": months_back,
        "currencies": [{"currency": k, "total": round(v, 2), "receipts": per_currency_count[k]}
                       for k, v in sorted(by_currency.items(), key=lambda kv: -abs(kv[1]))],
        "mixed": len(by_currency) > 1,
        "no_currency": sum(1 for d in inside if not d["currency"]),
        "vendors": [{"vendor": v, "totals": t, "receipts": n} for v, t, n in top],
        "vendor_total": len(by_vendor),
        "months": [{"month": m, "totals": {k: round(x, 2) for k, x in t.items()}}
                   for m, t in sorted(by_month.items())],
        "recurring": [{"vendor": v, "months": len(ms), "first": ms[0], "last": ms[-1]} for v, ms in recurring[:6]],
        "recurring_total": len(recurring),
        "subscriptions": sum(1 for d in inside if d["subscription"]),
        "refunds": sum(1 for d in inside if d["refund"]),
        "duplicates": sorted(dupes, key=lambda d: -d["copies"])[:6], "duplicate_total": len(dupes),
        "guessed_amounts": sum(1 for d in inside if d["confidence"] == "largest figure"),
        "guessed_dates": sum(1 for d in inside if d["date_from"] == "file modification time"),
        "biggest": sorted(({"vendor": d["vendor"], "amount": d["amount"], "currency": d["currency"],
                            "date": (d["date"] or "")[:10], "file": d["file"]} for d in inside),
                          key=lambda d: -d["amount"])[:6],
        "by_kind": [{"ext": k, "files": c} for k, c in Counter(d["ext"] for d in docs).most_common()],
        "evidence": [{"kind": k, "documents": c} for k, c in
                     Counter(e for d in docs for e in d.get("evidence_kinds", [])).most_common(6)],
    }


def _money(value: float, currency: str) -> str:
    sign = "-" if value < 0 else ""
    symbol = {"USD": "$", "GBP": "£", "EUR": "€", "INR": "₹", "JPY": "¥"}.get(currency, "")
    return "{0}{1}{2:,.2f}{3}".format(sign, symbol, abs(value), "" if symbol else " " + (currency or "?"))


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card

    c = Card("RECEIPT LEDGER", "last {0} months".format(v["months_back"]), cfg.get("color"))
    c.blank()
    if v["currencies"]:
        for cur in v["currencies"][:3]:
            c.headline("{0} across {1}".format(_money(cur["total"], cur["currency"]),
                                               "1 receipt" if cur["receipts"] == 1
                                               else "{0} receipts".format(cur["receipts"])), "1;32")
        if v["mixed"]:
            c.row("shown per currency: these are never added together")
    else:
        c.headline("nothing charged inside the last {0} months".format(v["months_back"]))
        if v["newest"]:
            c.wrap("{0} receipt(s) were read and all of them are older; the most recent is dated "
                   "{1}. Raise months_back to include them.".format(v["outside_window"], v["newest"]))
    c.row("{0} documents read · {1} carried an amount · {2} did not".format(
        v["documents"], v["priced"], v["unpriced"]))
    c.blank()

    if v["vendors"]:
        c.rule("WHO CHARGED YOU")
        for row in v["vendors"][:6]:
            amounts = " · ".join(_money(a, k) for k, a in sorted(row["totals"].items(), key=lambda kv: -abs(kv[1])))
            c.cols("{0}  ({1})".format(row["vendor"], row["receipts"]), amounts, 22)

    if v["months"]:
        c.rule("BY MONTH")
        for row in v["months"][-6:]:
            amounts = " · ".join(_money(a, k) for k, a in sorted(row["totals"].items(), key=lambda kv: -abs(kv[1])))
            c.cols(row["month"], amounts, 22)

    if v["recurring_total"]:
        c.rule("SHOWS UP EVERY MONTH")
        for r in v["recurring"][:4]:
            c.cols(r["vendor"], "{0} months, {1} → {2}".format(r["months"], r["first"], r["last"]), 30)

    if v["duplicate_total"]:
        c.rule("THE SAME CHARGE TWICE")
        for d in v["duplicates"][:3]:
            c.cols("{0} {1}".format(d["vendor"], _money(d["amount"], d["currency"])),
                   "{0}× on {1}".format(d["copies"], d["date"]), 20)
        c.wrap("Two files can describe one charge. Open them before you call it a double billing.")

    c.rule("HOW SURE")
    c.cols("amount came from a total line", str(v["in_window"] - v["guessed_amounts"]), 6)
    c.cols("amount is the largest figure on the page", str(v["guessed_amounts"]), 6)
    c.cols("date came from the file, not the text", str(v["guessed_dates"]), 6)
    if v["no_currency"]:
        c.cols("no currency stated", str(v["no_currency"]), 6)
    if v["refunds"]:
        c.cols("refunds, subtracted from the totals", str(v["refunds"]), 6)
    if v["evidence"]:
        c.wrap("Counted as receipts because they said so: {0}.".format(
            ", ".join("{0} ({1})".format(e["kind"], e["documents"]) for e in v["evidence"][:4])))

    c.blank()
    c.wrap("Read from files already on this disk. Nothing logged in anywhere, nothing was sent, "
           "and this is a reading of your documents, not a statement from anyone.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    L = ["# Receipt ledger", "",
         "{0} documents read, {1} carried an amount, {2} fell inside the last {3} months.".format(
             v["documents"], v["priced"], v["in_window"], v["months_back"]), "",
         "## Totals", "", "| currency | total | receipts |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(c["currency"], _money(c["total"], c["currency"]), c["receipts"])
          for c in v["currencies"]]
    L += ["", "Totals are per currency and are never summed across currencies.", "",
          "## By vendor", "", "| vendor | receipts | total |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(r["vendor"], r["receipts"],
                                       " · ".join(_money(a, k) for k, a in sorted(r["totals"].items())))
          for r in v["vendors"]]
    L += ["", "## By month", "", "| month | total |", "|---|---|"]
    L += ["| {0} | {1} |".format(m["month"], " · ".join(_money(a, k) for k, a in sorted(m["totals"].items())))
          for m in v["months"]]
    if v["recurring"]:
        L += ["", "## Recurring", "", "| vendor | months seen | first | last |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(r["vendor"], r["months"], r["first"], r["last"])
              for r in v["recurring"]]
    if v["duplicates"]:
        L += ["", "## The same charge twice", "", "| vendor | amount | date | copies | files |", "|---|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} | {4} |".format(d["vendor"], _money(d["amount"], d["currency"]),
                                                       d["date"], d["copies"], ", ".join(d["files"]))
              for d in v["duplicates"]]
    L += ["", "## How sure", "", "| basis | receipts |", "|---|---|",
          "| amount came from a total line | {0} |".format(v["in_window"] - v["guessed_amounts"]),
          "| amount is the largest figure on the page | {0} |".format(v["guessed_amounts"]),
          "| date taken from the file, not the text | {0} |".format(v["guessed_dates"]),
          "| no currency stated | {0} |".format(v["no_currency"]), ""]
    L += ["## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "") for s in sources]
    L += ["", "Read-only, offline. No account was contacted and nothing left this machine. A scanned "
          "PDF has no text to read and is counted as unreadable rather than guessed at.", ""]
    return "\n".join(L)
