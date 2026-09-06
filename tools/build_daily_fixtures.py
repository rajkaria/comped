#!/usr/bin/env python3
"""Generate the bundled demo fixtures for the six daily Plays.

Every fixture is produced here rather than copied from a machine, for three reasons: nothing
personal can leak into a published Play, the binary formats (SNSS, property lists, PDF) are
exercised by the same readers a real run uses, and re-running this script reproduces the files
byte for byte, so drift is a diff rather than a mystery.
"""
import hashlib
import json
import pathlib
import plistlib
import random
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "daily_core" / "fixtures"
# One fixed clock for every fixture, so the demo card is the same card on every machine and in CI.
NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)
EPOCH_2001 = datetime(2001, 1, 1, tzinfo=timezone.utc)


def chrome_us(when):
    return int((when - EPOCH_1601).total_seconds() * 1000000)


def apple_s(when):
    return (when - EPOCH_2001).total_seconds()


def days(n):
    return NOW - timedelta(days=n)


# ---------------------------------------------------------------- SNSS

class Pickle:
    """base::Pickle: a uint32 payload size, then fields each padded to a four-byte boundary."""

    def __init__(self):
        self.buf = bytearray()

    def _pad(self):
        self.buf += b"\0" * ((-len(self.buf)) % 4)

    def int32(self, v):
        self.buf += struct.pack("<i", v)
        return self

    def int64(self, v):
        self.buf += struct.pack("<q", v)
        return self

    def string(self, s):
        b = s.encode("utf-8")
        self.buf += struct.pack("<i", len(b)) + b
        self._pad()
        return self

    def string16(self, s):
        b = s.encode("utf-16-le")
        self.buf += struct.pack("<i", len(b) // 2) + b
        self._pad()
        return self

    def bytes(self):
        return struct.pack("<I", len(self.buf)) + bytes(self.buf)


def navigation(tab_id, index, url, title, when):
    p = Pickle().int32(tab_id).int32(index).string(url).string16(title)
    p.string("").int32(0).int32(0).string("").int32(0).string("").int32(0).int64(chrome_us(when))
    return p.bytes()


def snss(commands) -> bytes:
    out = bytearray(b"SNSS" + struct.pack("<i", 1))
    for cid, payload in commands:
        body = bytes([cid]) + payload
        out += struct.pack("<H", len(body)) + body
    return bytes(out)


def build_chrome():
    tabs = [
        (11, 0, "https://mail.google.com/mail/u/0/#inbox", "Inbox (2,015)", 0, False),
        (12, 1, "https://github.com/rajkaria/comped/pulls", "Pull requests · comped", 0, True),
        (13, 2, "https://news.ycombinator.com/item?id=41999999", "Show HN: a thing", 3, False),
        (14, 3, "https://docs.python.org/3/library/sqlite3.html", "sqlite3 — DB-API", 12, False),
        (15, 4, "https://www.youtube.com/watch?v=demo1", "A talk you meant to watch", 41, False),
        (16, 5, "https://www.youtube.com/watch?v=demo2", "Another talk", 63, False),
        (17, 6, "https://news.ycombinator.com/item?id=41999999", "Show HN: a thing", 3, False),
        (18, 7, "https://stackoverflow.com/questions/1/how-do-i", "How do I …", 129, False),
        (19, 8, "https://calendar.google.com/calendar/u/0/r", "Calendar", 1, False),
        (20, 9, "https://docs.google.com/document/d/abc/edit", "Q3 plan", 24, False),
    ]
    cmds = []
    for tab_id, index, url, title, age, pinned in tabs:
        cmds.append((0, struct.pack("<ii", 1, tab_id)))                       # tab -> window 1
        cmds.append((2, struct.pack("<ii", tab_id, index)))                   # index in window
        cmds.append((6, navigation(tab_id, 0, "https://example.invalid/start", "Start", days(age + 5))))
        cmds.append((6, navigation(tab_id, 1, url, title, days(age))))
        cmds.append((7, struct.pack("<ii", tab_id, 1)))                       # selected navigation
        cmds.append((21, struct.pack("<iixxxx", tab_id, 0)[:8] + struct.pack("<q", chrome_us(days(age)))))
        if pinned:
            cmds.append((12, struct.pack("<i", tab_id) + b"\x01"))
    # One tab opened and closed again: it must not appear in the replayed tab set.
    cmds.append((0, struct.pack("<ii", 1, 99)))
    cmds.append((6, navigation(99, 0, "https://example.invalid/closed", "Closed already", days(2))))
    cmds.append((16, struct.pack("<i", 99) + b"\0" * 4 + struct.pack("<q", chrome_us(days(1)))))
    return snss(cmds)


def build_firefox():
    tabs = [("https://developer.mozilla.org/en-US/docs/Web/API/fetch", "fetch() - MDN", 8),
            ("https://www.youtube.com/watch?v=demo1", "A talk you meant to watch", 41),
            ("https://bugzilla.mozilla.org/show_bug.cgi?id=1", "Bug 1", 210)]
    return {"windows": [{"tabs": [
        {"entries": [{"url": u, "title": t}], "index": 1,
         "lastAccessed": int(days(age).timestamp() * 1000)} for u, t, age in tabs]}],
        "_closedWindows": []}


def build_safari():
    tabs = [("https://www.apple.com/newsroom/", "Newsroom", 5),
            ("https://gotcomped.com/leaderboard.html", "Leaderboard", 33)]
    return {"SessionVersion": "1.0", "SessionWindows": [{"SelectedTabIndex": 0, "TabStates": [
        {"TabURL": u, "TabTitle": t, "LastVisitTime": apple_s(days(age))} for u, t, age in tabs]}]}


def build_reading_list():
    items = [("https://longform.example.com/a-long-read", "A long read", 402, None),
             ("https://longform.example.com/another", "Another one", 96, 90),
             ("https://longform.example.com/third", "Read this later", 14, None)]
    return {"Children": [{"Title": "com.apple.ReadingList", "WebBookmarkType": "WebBookmarkTypeList",
                          "Children": [
                              {"URLString": u, "URIDictionary": {"title": t},
                               "WebBookmarkType": "WebBookmarkTypeLeaf",
                               "ReadingList": dict({"DateAdded": days(added).replace(tzinfo=None)},
                                                   **({"DateLastViewed": days(seen).replace(tzinfo=None)}
                                                      if seen else {}))}
                              for u, t, added, seen in items]}]}


def build_arc():
    tabs = [("https://linear.app/team/issue/ENG-1", "ENG-1 ship it", 2),
            ("https://figma.com/file/abc/Design", "Design", 58),
            ("https://mail.google.com/mail/u/0/#inbox", "Inbox (2,015)", 77)]
    items = []
    for i, (url, title, age) in enumerate(tabs):
        items.append("tab-{0}".format(i))
        items.append({"id": "tab-{0}".format(i), "title": None, "parentID": "space-1", "childrenIds": [],
                      "data": {"tab": {"savedURL": url, "savedTitle": title,
                                       "timeLastActiveAt": apple_s(days(age))}}})
    return {"version": 3, "sidebar": {"containers": [{"global": {}}, {"items": items, "spaces": []}]}}


# ---------------------------------------------------------------- other fixtures

VCARD = """BEGIN:VCARD
VERSION:3.0
FN:Ada Lovelace
ORG:Analytical Engines
BDAY:1985-09-06
EMAIL:ada@example.com
TEL:+441234567890
REV:2026-01-04T09:00:00Z
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Grace Hopper
BDAY;VALUE=date:--0909
EMAIL:grace@example.com
REV:2019-02-02T09:00:00Z
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Grace Hopper
EMAIL:grace.hopper@example.com
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Alan Turing
ORG:NPL
BDAY:1912-06-23
EMAIL:alan@example.com
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Katherine Johnson
BDAY:1918-08-26
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:No Birthday Here
ORG:Placeholder Inc
EMAIL:nobody@example.com
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Radia Perlman
BDAY:1951-09-18
TEL:+15550100
END:VCARD
"""


def build_apps():
    rows = [("Keynote", "com.apple.iWork.Keynote", "14.5", 732 * 10 ** 6, ["arm64", "x86_64"], 214),
            ("Xcode", "com.apple.dt.Xcode", "16.2", 7100 * 10 ** 6, ["arm64", "x86_64"], 9),
            ("Sparrow", "com.sparrowmailapp.sparrow", "1.7.2", 118 * 10 ** 6, ["i386", "x86_64"], 1290),
            ("Old Torrent Client", "org.example.torrent", "2.1", 46 * 10 ** 6, ["x86_64"], 640),
            ("Slack", "com.tinyspeck.slackmacgap", "4.41", 412 * 10 ** 6, ["arm64", "x86_64"], 1),
            ("Figma", "com.figma.Desktop", "124.6", 380 * 10 ** 6, ["arm64", "x86_64"], 3),
            ("Screen Recorder", "com.example.recorder", "3.0", 92 * 10 ** 6, ["x86_64"], 431),
            ("Photo Editor Trial", "com.example.photoedit", "1.0", 1240 * 10 ** 6, ["arm64"], None)]
    out = []
    for name, bundle, version, size, arches, age in rows:
        used = "" if age is None else days(age).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"name": name, "path": "/Applications/{0}.app".format(name), "bundle_id": bundle,
                    "version": version, "min_system": "12.0", "architectures": arches,
                    "bytes": size, "files": 1200, "sized": True,
                    "installed": days(900).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "updated": days(age or 900).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "accessed": used, "last_used": used,
                    "last_used_source": "spotlight" if used else ""})
    return out


def build_casks():
    return [{"name": n, "path": "/opt/homebrew/Caskroom/" + n, "bytes": b, "files": 20, "sized": True,
             "versions": v}
            for n, b, v in [("figma", 402 * 10 ** 6, ["124.5", "124.6"]),
                            ("old-editor", 210 * 10 ** 6, ["1.0"]),
                            ("slack", 390 * 10 ** 6, ["4.40", "4.41"])]]


def build_clutter():
    rows = [("desktop", "Screenshot 2026-08-30 at 10.14.22.png", 2400000, 2),
            ("desktop", "Screenshot 2026-08-12 at 09.02.10.png", 3100000, 20),
            ("desktop", "Screenshot 2025-11-02 at 18.44.51.png", 2900000, 303),
            ("desktop", "Screenshot 2025-06-18 at 08.31.09.png", 2700000, 440),
            ("desktop", "untitled folder/notes.txt", 1400, 512),
            ("desktop", "final.mp4", 84000000, 190),
            ("desktop", "final (1).mp4", 84000000, 188),
            ("desktop", "deck-v7-FINAL-really.pdf", 12400000, 96),
            ("desktop", "logo.png", 240000, 700),
            ("desktop", "logo copy.png", 240000, 700),
            ("downloads", "invoice-2026-07.pdf", 88000, 41),
            ("downloads", "Setup.dmg", 620000000, 220),
            ("downloads", "node-v22.pkg", 74000000, 400),
            ("downloads", "dataset.csv", 41000000, 15),
            ("downloads", "dataset (1).csv", 41000000, 14),
            ("downloads", "photo.heic", 3900000, 6),
            ("downloads", "archive.zip", 156000000, 610),
            ("downloads", "resume.pdf", 190000, 830)]
    out = []
    for root, rel, size, age in rows:
        when = days(age).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"name": rel.split("/")[-1], "rel": rel, "root": root, "bytes": size,
                    "ext": "." + rel.rsplit(".", 1)[-1] if "." in rel.split("/")[-1] else "",
                    "depth": rel.count("/"), "modified": when, "created": when})
    return out


NOTES = {
    "index.md": "# Index\n\nStart here: [[projects/comped]] and [[reading/queue]].\n\n#hub\n",
    "projects/comped.md": ("---\ntags: [project, shipping]\n---\n\n# comped\n\nBacked by [[research/pricing]] "
                           "and [[missing-note]].\n\n- [ ] publish the play\n- [ ] write the readme\n- [x] pick a name\n\n"
                           + "Body text. " * 60),
    "projects/abandoned.md": "# Abandoned\n\nNo links here at all.\n\n" + "Words. " * 40,
    "research/pricing.md": "# Pricing\n\nSee [[projects/comped]].\n\n" + "Analysis. " * 90,
    "reading/queue.md": "# Queue\n\n- [ ] a long read\n- [ ] another\n\n[[research/pricing]]\n",
    "stub.md": "just this\n",
    "2026-08-30.md": "Daily note.\n\n- [ ] follow up\n",
    "2026-08-31.md": "Daily note.\n",
    "2026-09-01.md": "Daily note. [[index]]\n",
    "orphan-thoughts.md": "# Orphan\n\nNothing points here and it points nowhere.\n\n" + "Text. " * 25,
}

EML = """From: Netflix <info@mailer.netflix.com>
To: you@example.com
Subject: Your Netflix receipt
Date: Tue, 12 Aug 2026 09:14:02 +0000
Content-Type: text/plain; charset=utf-8

Thank you for your payment.

Invoice number: 4410-2291
Billing period: 12 Aug 2026 - 11 Sep 2026
Subtotal      $15.49
Tax           $0.00
Total charged $15.49

Payment method: Visa ending 4242
"""

EML2 = """From: "Fly.io Billing" <billing@fly.io>
To: you@example.com
Subject: Invoice 90210 for August
Date: Thu, 03 Sep 2026 06:00:00 +0000
Content-Type: text/html; charset=utf-8

<html><body><h1>Invoice 90210</h1>
<table><tr><td>Compute</td><td>$21.40</td></tr>
<tr><td>Sub-total</td><td>$21.40</td></tr>
<tr><td>VAT</td><td>$4.28</td></tr>
<tr><td><b>Amount due</b></td><td><b>$25.68</b></td></tr></table>
<p>Payment method: card ending 1111</p></body></html>
"""

EML3 = """From: Spotify <no-reply@spotify.com>
To: you@example.com
Subject: Your receipt from Spotify
Date: Sun, 05 Jul 2026 08:00:00 +0000
Content-Type: text/plain; charset=utf-8

Receipt number: SP-77120
Order total: EUR 11.99
Payment method: card ending 9090
Next billing date: 05 Aug 2026
"""

HTML_RECEIPT = """<html><head><title>Order confirmation - Bookshop</title></head><body>
<h1>Thank you for your order</h1>
<p>Order number: BK-55120</p><p>Order date: 2026-06-21</p>
<table><tr><td>Sub-total</td><td>£24.00</td></tr>
<tr><td>Delivery</td><td>£3.95</td></tr>
<tr><td>Grand total</td><td>£27.95</td></tr></table>
<p>Billed to: card ending 7788</p></body></html>
"""

# The negative case, and the one that matters: a document full of money that charged nobody.
DECK = """Series A deck - Acme Robotics
Market size: $4,000,000,000 by 2030
Revenue run rate: $1,200,000
Ask: $8,000,000 at a $40,000,000 valuation
Team of 14, shipping since 2024
"""


def build_pdf(lines) -> bytes:
    """A minimal one-page PDF whose text the bundled reader has to decompress to find."""
    content = b"BT /F1 12 Tf 40 760 Td 14 TL\n" + b"\n".join(
        b"(" + l.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj T*"
        for l in lines) + b"\nET"
    comp = zlib.compress(content)
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(comp)).encode() + b"/Filter/FlateDecode>>stream\n" + comp + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj" + body + b"endobj\n"
    start = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    out += b"".join(str(o).zfill(10).encode() + b" 00000 n \n" for o in offsets)
    out += (b"trailer<</Size " + str(len(objects) + 1).encode() + b"/Root 1 0 R>>\nstartxref\n"
            + str(start).encode() + b"\n%%EOF\n")
    return bytes(out)


# ================================================================ the ten pulse Plays
#
# Same rules as the six above: one fixed clock, invented people at example.com, no path that
# could ever have been somebody's home directory, and every file written from this script rather
# than captured from a machine. Two extra rules apply to these ten, because their cards are
# bigger:
#
# 1. Every headline class a Play can report has to FIRE here. A demo whose "dangerous permission
#    combination" section is empty teaches a stranger that the section is decoration.
# 2. Every fixture carries at least one honest degradation -- a source that cannot be read, a
#    column the schema does not have, a package nobody looked up -- so the demo shows the
#    labelling as well as the arithmetic.
#
# Each builder seeds its own random.Random, so re-running this script rewrites the same bytes.


def compact(obj) -> str:
    """One line of JSON. The visit and asset fixtures are tens of thousands of rows; indenting
    them would triple the bytes every Play package carries for no reader's benefit."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n"


def stamp(when) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unix(when) -> int:
    return int(when.timestamp())


def at(day_age, hour=9, minute=0, offset_hours=0):
    """A wall-clock instant `day_age` days before NOW, in a fixed UTC offset."""
    zone = timezone(timedelta(hours=offset_hours))
    base = (NOW - timedelta(days=day_age)).astimezone(zone)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------- bus-factor

# Six invented humans and one bot. The bot is here because "we excluded the bots" is a claim the
# card makes, and a claim with nothing behind it in the demo is one a reader cannot check.
BF_MIRA = ("Mira Solberg", "mira@example.com")
BF_TOMAS = ("Tomas Halvorsen", "tomas@example.com")
BF_PRIYA = ("Priya Raghavan", "priya@example.com")
BF_DANIEL = ("Daniel Okafor", "daniel@example.com")          # left the team 18 months ago
BF_YUKI = ("Yuki Tanabe", "yuki@example.com")
BF_ELENA = ("Elena Marchetti", "elena@example.com")
BF_BOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")

SETTLEMENT = ("clearing", "netting", "fx_rates", "cutover", "reconcile", "payout_batch",
              "chargeback", "ledger_post", "settlement_run", "bank_file", "mt940", "iso20022",
              "value_date", "holiday_calendar", "nostro", "vostro", "sweep", "float_window",
              "instruction", "confirmation", "unwind", "novation", "margin_call", "haircut",
              "collateral", "cash_leg", "security_leg", "fail_report", "buy_in", "penalty",
              "late_matching")
API_MODULES = ("accounts", "auth", "balances", "cards", "customers", "disputes", "events",
               "fees", "holds", "idempotency", "limits", "mandates", "notifications", "payees",
               "payments", "quotes", "rates", "refunds", "schedules", "statements", "subscriptions",
               "transfers", "webhooks", "wallets", "kyc", "onboarding", "reporting", "search",
               "sessions", "tokens", "usage", "validation", "webhooks_retry", "audit")
PRICING_MODULES = ("bands", "bundles", "catalogue", "coupons", "currency", "discounts", "grid",
                   "margins", "markup", "matrix", "overrides", "plans", "promo", "rounding",
                   "rules", "spread", "surcharge", "tax", "tiers", "trials", "uplift", "volume")
INGEST_MODULES = ("batch_reader", "csv_feed", "dedupe", "drift", "envelope", "kafka_bridge",
                  "landing", "normalise", "partition", "replay", "schema_guard", "sftp_poll",
                  "sink", "stage", "throttle", "trailer", "watermark", "xml_feed")
WEB_COMPONENTS = ("AmountInput", "Badge", "BillingCard", "Breadcrumb", "Callout", "Chart",
                  "Checkbox", "CurrencyPicker", "DataGrid", "DatePicker", "Dialog", "Drawer",
                  "EmptyState", "FieldSet", "Filters", "Footer", "Header", "InvoiceRow",
                  "LineItem", "Menu", "Modal", "Nav", "Pagination", "PlanTile", "PriceTag",
                  "Progress", "RadioGroup", "SearchBox", "Select", "Sidebar", "Skeleton",
                  "Spinner", "Stepper", "Table", "Tabs", "Toast", "Toggle", "Tooltip")
WEB_LIB = ("analytics", "api-client", "cache", "currency", "dates", "errors", "feature-flags",
           "fetcher", "format", "i18n", "logger", "money", "paths", "query", "retry", "router",
           "storage", "telemetry", "url", "validate")
WEB_PAGES = ("account", "billing", "checkout", "compare", "contact", "dashboard", "invoices",
             "login", "plans", "pricing", "profile", "quote", "receipts", "settings", "signup",
             "usage")
WEB_BILLING = ("dunning", "invoice_pdf", "proration", "seat_sync", "tax_lookup", "trial_end",
               "usage_roll", "webhook_in", "webhook_out", "credit_note")
OPS_SCRIPTS = ("backfill_ledger", "bootstrap_env", "cut_release", "db_restore", "drain_node",
               "dump_metrics", "expire_tokens", "failover_drill", "gc_artifacts", "grant_access",
               "load_test", "migrate_schema", "prune_images", "reap_sandboxes", "reindex_search",
               "rotate_keys", "seed_demo", "snapshot_vols", "sync_dns", "tail_audit",
               "verify_backups", "warm_cache")
OPS_TERRAFORM = ("dns", "iam", "network", "observability", "queues", "rds", "redis", "s3",
                 "secrets", "vpc")


def _bf_record(repo, path, owners, shallow=False) -> dict:
    """One tracked file, in exactly the shape `busfactor._read_repo` produces from git."""
    authors, commits, last = [], 0, 0
    for who, lines, deleted, n, first_age, last_age in owners:
        first, latest = unix(days(first_age)), unix(days(last_age))
        authors.append({"name": who[0], "email": who[1], "lines": lines, "deleted": deleted,
                        "commits": n, "first": first, "last": latest})
        commits += n
        last = max(last, latest)
    authors.sort(key=lambda a: (-a["lines"], -a["commits"], a["name"], a["email"]))
    return {"repo": repo, "repo_path": "/work/{0}".format(repo), "shallow": shallow, "path": path,
            "authors": authors, "commits": commits, "last": last}


def build_busfactor():
    rng = random.Random(20260901)
    out = []

    def one(repo, path, who, first_age, last_age, lo=90, hi=320, shallow=False):
        out.append(_bf_record(repo, path, [(who, rng.randint(lo, hi), rng.randint(0, 70),
                                            rng.randint(2, 9), first_age, last_age)], shallow))

    def many(repo, path, people, first_age, last_age, shallow=False):
        owners = []
        for i, who in enumerate(people):
            owners.append((who, rng.randint(60, 400) // (i + 1) + 25, rng.randint(0, 90),
                           rng.randint(1, 12), first_age - rng.randint(0, 120),
                           last_age + rng.randint(0, 45)))
        out.append(_bf_record(repo, path, owners, shallow))

    # -- ledger-api: the repository with the cluster the card is about ------------------------
    # Thirty-one files in one directory, one author, and that author's last commit is far enough
    # back that both the "stale" and the "departed" tests fire on the same person.
    for i, name in enumerate(SETTLEMENT):
        one("ledger-api", "ledger/settlement/{0}.py".format(name), BF_DANIEL,
            980 + i * 4, 505 + (i % 9) * 7, lo=110, hi=340)
    for i, name in enumerate(API_MODULES):
        crew = [BF_MIRA, BF_TOMAS, BF_PRIYA][:2 + (i % 2)]
        many("ledger-api", "ledger/api/{0}.py".format(name), crew, 620 - i * 3, 4 + (i % 70))
    for i, name in enumerate(PRICING_MODULES):
        if i % 5 < 2:
            one("ledger-api", "ledger/pricing/{0}.py".format(name), BF_PRIYA,
                300 - i * 2, 9 + (i % 40), lo=70, hi=260)
        else:
            many("ledger-api", "ledger/pricing/{0}.py".format(name), [BF_PRIYA, BF_MIRA],
                 480 - i * 4, 12 + (i % 60))
    for i, name in enumerate(INGEST_MODULES):
        if i % 3 == 0:
            one("ledger-api", "ledger/ingest/{0}.py".format(name), BF_TOMAS,
                700 - i * 5, 210 + i * 6, lo=80, hi=250)
        else:
            many("ledger-api", "ledger/ingest/{0}.py".format(name), [BF_TOMAS, BF_MIRA],
                 640 - i * 5, 30 + i * 3)
    # The tests name the settlement modules, which is what gives that cluster its `referenced by`
    # count: a file nothing else mentions is a smaller problem than one twenty files import.
    for i, name in enumerate(SETTLEMENT[:18]):
        many("ledger-api", "tests/test_{0}.py".format(name), [BF_MIRA, BF_TOMAS], 500 - i * 6, 20 + i)
    for i, name in enumerate(API_MODULES[:10]):
        many("ledger-api", "tests/api/test_{0}.py".format(name), [BF_PRIYA, BF_MIRA], 420 - i * 8, 15 + i)
    for name in ("architecture", "runbook", "settlement_flow", "onboarding", "release", "oncall",
                 "glossary"):
        one("ledger-api", "docs/{0}.md".format(name), BF_MIRA, 560, 88, lo=40, hi=180)
    # Only the bot has ever touched this file, so it is attributable to nobody at all.
    out.append(_bf_record("ledger-api", ".github/workflows/ci.yml",
                          [(BF_BOT, 240, 96, 31, 900, 3)]))
    # Vendored, generated and locked: excluded by pattern, and counted so the exclusion is visible.
    for path in ("poetry.lock", "node_modules/left-pad/index.js", "node_modules/ms/index.js",
                 "dist/ledger_api.min.js", "ledger/generated/schema_pb2.py",
                 "__pycache__/settlement.cpython-311.pyc"):
        many("ledger-api", path, [BF_MIRA, BF_BOT], 700, 6)

    # -- pricing-web ---------------------------------------------------------------------------
    for i, name in enumerate(WEB_COMPONENTS):
        if i % 3 == 0:
            one("pricing-web", "src/components/{0}.tsx".format(name), BF_YUKI,
                420 - i * 3, 34 + i * 3, lo=60, hi=230)
        else:
            many("pricing-web", "src/components/{0}.tsx".format(name), [BF_YUKI, BF_ELENA],
                 500 - i * 4, 11 + i * 2)
    for i, name in enumerate(WEB_LIB):
        if i % 3 == 1:
            one("pricing-web", "src/lib/{0}.ts".format(name), BF_TOMAS, 610 - i * 6, 260 + i * 9,
                lo=70, hi=240)
        else:
            many("pricing-web", "src/lib/{0}.ts".format(name), [BF_TOMAS, BF_ELENA, BF_YUKI],
                 590 - i * 7, 18 + i * 4)
    for i, name in enumerate(WEB_PAGES):
        many("pricing-web", "src/pages/{0}.tsx".format(name), [BF_ELENA, BF_YUKI], 480 - i * 8, 22 + i * 3)
    # Priya is the only author of code in two repositories, which is one risk and not two.
    for i, name in enumerate(WEB_BILLING):
        one("pricing-web", "src/billing/{0}.ts".format(name), BF_PRIYA, 350 - i * 6, 47 + i * 11,
            lo=90, hi=300)
    for i, name in enumerate(WEB_PAGES[:12]):
        many("pricing-web", "tests/{0}.spec.ts".format(name), [BF_ELENA, BF_YUKI], 400 - i * 9, 26 + i * 2)
    for path in ("package-lock.json", "dist/app.min.js", "vendor/polyfill.js"):
        many("pricing-web", path, [BF_ELENA, BF_BOT], 620, 9)

    # -- ops-tooling: a shallow clone, so every count from it is a lower bound -----------------
    for i, name in enumerate(OPS_SCRIPTS):
        if i % 5 < 3:
            one("ops-tooling", "scripts/{0}.sh".format(name), BF_ELENA, 900 - i * 7, 395 + i * 12,
                lo=40, hi=170, shallow=True)
        else:
            many("ops-tooling", "scripts/{0}.sh".format(name), [BF_ELENA, BF_MIRA],
                 880 - i * 9, 120 + i * 5, shallow=True)
    for i, name in enumerate(OPS_TERRAFORM):
        many("ops-tooling", "terraform/{0}.tf".format(name), [BF_MIRA, BF_ELENA],
             760 - i * 11, 64 + i * 6, shallow=True)
    for name in ("README.md", "docs/runbook.md", "docs/oncall.md", "docs/access.md",
                 "docs/dr-plan.md", "docs/inventory.md"):
        one("ops-tooling", name, BF_MIRA, 820, 300, lo=30, hi=140, shallow=True)

    out.sort(key=lambda r: (r["repo"], r["path"]))
    return {"generated": stamp(NOW),
            "note": "invented repositories and invented people; no real history was read",
            "records": out}


# ---------------------------------------------------------------- night-shift

NS_ME = ("Mira Solberg", "mira@example.com")
NS_OTHERS = [("Tomas Halvorsen", "tomas@example.com"),
             ("Priya Raghavan", "priya@example.com"),
             ("Yuki Tanabe", "yuki@example.com")]
NS_REPOS = ("ledger-api", "pricing-web", "ops-tooling")
NS_SUBJECTS = (
    "handle partial settlement retries", "drop the second netting pass",
    "cache the fx rate table for a minute", "make the cutover job idempotent",
    "stop double-posting reversals", "widen the value-date window",
    "tighten the idempotency key", "return 409 instead of 500 on a replay",
    "batch the payout writes", "log the bank file checksum",
    "pin the schema guard to the trailer count", "skip empty partitions on replay",
    "reuse the connection pool in the poller", "split the invoice PDF worker",
    "debounce the currency picker", "memoise the plan tiles",
    "guard the seat-sync webhook against retries", "fix the proration rounding",
    "move dunning off the request path", "roll usage nightly, not hourly",
    "add a backoff to the sftp poll", "expire sandbox tokens after a day",
    "warm the search index before the cutover", "quieten the failover drill alert",
)


def _ns_commit(rng, repo, who, when, subject, mine, committed=None):
    sha = "{0:012x}".format(rng.getrandbits(48))
    return {"repo": repo, "sha": sha, "name": who[0], "email": who[1],
            "authored": when.isoformat(), "committed": (committed or when).isoformat(),
            "subject": subject, "mine": mine}


def build_nightshift():
    """Ninety days of commits, carrying their own UTC offsets.

    A repository cannot be shipped and a clone's dates are the dates of the clone, so the demo is
    a manifest. Two offsets appear on purpose: a fortnight at +09:00 in the middle of the window
    is what makes the card's travel caveat print, and a card that never prints its caveats has
    never shown a reader that it has any.
    """
    rng = random.Random(770118)
    rows, seq = [], 0
    late_pool, rest_pool = [], []

    for d in range(89, 0, -1):
        offset = 9 if 30 <= d <= 43 else 1
        weekday = (NOW - timedelta(days=d)).weekday()
        base = 5 if weekday < 5 else 2
        count = max(0, base + rng.randint(-4, 4))
        for _ in range(count):
            late = rng.random() < 0.235
            hour = rng.choice((23, 0, 1, 2, 3, 4)) if late else rng.choice(
                (9, 10, 10, 11, 11, 12, 14, 14, 15, 16, 16, 17, 18, 20, 21))
            minute = rng.randrange(60)
            mine = rng.random() < 0.84
            who = NS_ME if mine else rng.choice(NS_OTHERS)
            repo = rng.choice(NS_REPOS)
            seq += 1
            subject = "{0} (#{1})".format(rng.choice(NS_SUBJECTS), 3400 + seq)
            when = at(d, hour, minute, offset)
            committed = when
            if rng.random() < 0.045:
                # Rebased or amended: the author date is later than the committer date, which the
                # card reports rather than quietly straightening out.
                committed = when - timedelta(minutes=rng.randint(20, 900))
            row = _ns_commit(rng, repo, who, when, subject, mine, committed)
            rows.append(row)
            (late_pool if (late and mine) else rest_pool).append((d, row))

    def follow(pool, n, make, min_day=2):
        picked = rng.sample([p for p in pool if p[0] >= min_day], min(n, len(pool)))
        for d, row in sorted(picked, key=lambda p: -p[0]):
            make(d, row)

    # Reverts. Late work is undone more often than the rest of the day's, which is the one
    # correlation this Play exists to report, so the fixture has to contain it.
    def revert(gap_lo, gap_hi):
        def make(d, row):
            when = parse_iso(row["authored"]) + timedelta(days=rng.randint(gap_lo, gap_hi),
                                                          hours=rng.randint(1, 8))
            if when >= NOW:
                return
            mine = rng.random() < 0.6
            who = NS_ME if mine else rng.choice(NS_OTHERS)
            rows.append(_ns_commit(rng, row["repo"], who, when,
                                   'Revert "{0}"'.format(row["subject"]), mine))
        return make

    follow(late_pool, 14, revert(1, 4))
    follow(rest_pool, 5, revert(2, 9))

    # Fix-ups: a follow-up by the same person in the same repository inside the hour.
    def fixup(d, row):
        when = parse_iso(row["authored"]) + timedelta(minutes=rng.randint(6, 48))
        if when >= NOW:
            return
        rows.append(_ns_commit(rng, row["repo"], NS_ME, when,
                               "fixup! {0}".format(row["subject"][:40]), True))

    follow(late_pool, 21, fixup, min_day=1)
    follow(rest_pool, 7, fixup, min_day=1)

    rows.sort(key=lambda r: (r["authored"], r["repo"], r["sha"]))
    return rows


def parse_iso(text: str):
    """`datetime.isoformat()` back into a datetime, offset intact."""
    return datetime.fromisoformat(text)


# ---------------------------------------------------------------- kept

KEPT_REPOS = (
    {"path": "/work/ledger-api", "name": "ledger-api", "head": "main", "shallow": False, "note": ""},
    # A shallow clone, so this repository's confidence is reported as low rather than as a number
    # with nothing said about it.
    {"path": "/work/pricing-web", "name": "pricing-web", "head": "main", "shallow": True,
     "note": "shallow clone: history is truncated, so every count is a lower bound"},
)
KEPT_ME = ("Mira Solberg", "mira@example.com")
KEPT_HUMANS = (("Tomas Halvorsen", "tomas@example.com"), ("Priya Raghavan", "priya@example.com"))
KEPT_BOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
KEPT_MODELS = {"claude-code": "claude-opus-4-6", "codex": "gpt-5-codex", "pi": ""}
KEPT_FILES = {
    "/work/ledger-api": [
        "ledger/api/payments.py", "ledger/api/refunds.py", "ledger/api/transfers.py",
        "ledger/api/webhooks.py", "ledger/api/idempotency.py", "ledger/api/limits.py",
        "ledger/pricing/bands.py", "ledger/pricing/rounding.py", "ledger/pricing/tiers.py",
        "ledger/ingest/normalise.py", "ledger/ingest/replay.py", "ledger/ingest/schema_guard.py",
        "ledger/settlement/netting.py", "ledger/settlement/payout_batch.py",
        "tests/test_payments.py", "tests/test_refunds.py", "tests/test_pricing.py",
        "tests/test_replay.py", "tests/test_webhooks.py", "tests/test_limits.py",
        "docs/runbook.md", "docs/settlement_flow.md", "migrations/0041_holds.sql",
        "migrations/0042_idempotency.sql", "ledger/api/quotes.py", "ledger/api/statements.py",
        "ledger/pricing/overrides.py", "ledger/ingest/watermark.py",
    ],
    "/work/pricing-web": [
        "src/components/PlanTile.tsx", "src/components/PriceTag.tsx", "src/components/DataGrid.tsx",
        "src/lib/money.ts", "src/lib/format.ts", "src/lib/api-client.ts",
        "src/pages/pricing.tsx", "src/pages/checkout.tsx", "src/billing/proration.ts",
        "tests/pricing.spec.ts", "tests/checkout.spec.ts", "src/lib/feature-flags.ts",
    ],
}
# Written by an agent and never committed: the honest counterweight to a survival rate.
KEPT_NEVER = {"/work/ledger-api": ["scratch/spike_netting.py", "docs/draft-adr-0007.md",
                                   "ledger/api/_experiment.py"],
              "/work/pricing-web": ["src/components/_Sandbox.tsx"]}
# Deleted with the file since: the agent wrote them, the file is gone, so the lines are gone too.
KEPT_DELETED = {"/work/ledger-api": ["ledger/ingest/xml_feed.py", "tests/test_xml_feed.py"],
                "/work/pricing-web": ["src/components/LegacyBanner.tsx"]}


# Session ages, in days before the fixed clock. Spread deliberately across the half-life buckets
# the card prints -- same day, this week, this month, older -- because a bucket with nothing in it
# reads as a bug rather than as an honest "too few lines to rate".
KEPT_SESSION_AGES = (117, 96, 74, 61, 0, 45, 33, 3, 26, 19, 1, 14, 9, 5, 2)


def build_kept():
    """A recorded run: agent sessions, the commits around them, and a blame of what is left.

    A checkout carries no transcripts, no session windows and a history whose dates are the dates
    of the clone, so the demo replays a recorded document. Everything the card claims is derived
    from it by exactly the code a real run uses -- the canned backend answers the same three
    questions git would.
    """
    rng = random.Random(4242)
    records = []
    for repo in KEPT_REPOS:
        row = dict(repo)
        row["kind"] = "repo"
        records.append(row)
    records.append({"kind": "own", "keys": ["mira@example.com"]})

    for repo in KEPT_REPOS:
        path = repo["path"]
        files = KEPT_FILES[path]
        commits, sessions = [], []
        agent_added, human_added = {}, {}

        n_sessions = 15 if path.endswith("ledger-api") else 6
        harnesses = ["claude-code"] * 9 + ["codex"] * 4 + ["pi"] * 2
        for s in range(n_sessions):
            harness = harnesses[s % len(harnesses)]
            day_age = KEPT_SESSION_AGES[s % len(KEPT_SESSION_AGES)]
            start = at(day_age, rng.choice((9, 10, 14, 16, 21)) if day_age else 8,
                       rng.randrange(0, 50), 0)
            session_id = "{0}-{1:02d}".format(harness, s)
            touched = rng.sample(files, rng.randint(3, 6))
            if s == 0:
                touched = list(touched) + KEPT_DELETED[path]
            minutes = 0
            for i, rel in enumerate(touched):
                for _ in range(rng.randint(1, 3)):
                    minutes += rng.randint(3, 22)
                    records.append({
                        "kind": "edit", "session_id": session_id, "harness": harness,
                        "model": KEPT_MODELS[harness], "repo_hint": path,
                        "path": "{0}/{1}".format(path, rel),
                        "timestamp": stamp(start + timedelta(minutes=minutes)),
                        "added": rng.randint(12, 180), "tool": "Edit" if i % 3 else "Write"})
            for rel in KEPT_NEVER[path][: 1 if s % 5 else 2]:
                minutes += rng.randint(4, 15)
                records.append({
                    "kind": "edit", "session_id": session_id, "harness": harness,
                    "model": KEPT_MODELS[harness], "repo_hint": path,
                    "path": "{0}/{1}".format(path, rel),
                    "timestamp": stamp(start + timedelta(minutes=minutes)),
                    "added": rng.randint(20, 120), "tool": "Write"})
            end = start + timedelta(minutes=minutes)
            sessions.append((start, end))
            # One or two commits inside the window, which is what makes those lines the agent's.
            for k in range(rng.randint(1, 2)):
                when = end - timedelta(minutes=rng.randint(0, max(1, minutes // 2)))
                entries = []
                for rel in rng.sample(touched, max(1, len(touched) - k)):
                    added = rng.randint(30, 260)
                    entries.append({"path": rel, "added": added, "deleted": rng.randint(0, 90)})
                    agent_added[rel] = agent_added.get(rel, 0) + added
                commits.append({"sha": "{0:012x}".format(rng.getrandbits(48)), "at": unix(when),
                                "name": KEPT_ME[0], "email": KEPT_ME[1],
                                "subject": "{0} across {1}".format(
                                    rng.choice(("tidy", "wire up", "harden", "extend", "refactor")),
                                    entries[0]["path"].rsplit("/", 1)[0]),
                                "body": "", "files": entries})

        # The control group: the same files, edited outside every window, by hand.
        # A tenth of the control group lands in the last week, so the two newest half-life
        # buckets have a hand-written denominator instead of reading "unrated".
        for hand in range(38 if path.endswith("ledger-api") else 16):
            day_age = rng.randint(0, 6) if hand < 6 else rng.randint(7, 150)
            when = at(day_age, rng.choice((6, 8, 10) if day_age == 0 else (8, 11, 13, 15, 17, 19)),
                      rng.randrange(0, 59), 0)
            if any(s <= when <= e + timedelta(minutes=30) for s, e in sessions):
                when = when - timedelta(hours=6)
            who = KEPT_ME if rng.random() < 0.62 else rng.choice(KEPT_HUMANS)
            entries = []
            for rel in rng.sample(files, rng.randint(1, 4)):
                added = rng.randint(15, 190)
                entries.append({"path": rel, "added": added, "deleted": rng.randint(0, 70)})
                human_added[rel] = human_added.get(rel, 0) + added
            commits.append({"sha": "{0:012x}".format(rng.getrandbits(48)), "at": unix(when),
                            "name": who[0], "email": who[1],
                            "subject": "review follow-up on {0}".format(entries[0]["path"]),
                            "body": "", "files": entries})
        # A bot, so the card's third lane is not empty either.
        for _ in range(4):
            when = at(rng.randint(3, 140), 6, 12, 0)
            rel = rng.choice(files)
            entries = [{"path": rel, "added": rng.randint(8, 40), "deleted": 4}]
            human_added.setdefault(rel, 0)
            commits.append({"sha": "{0:012x}".format(rng.getrandbits(48)), "at": unix(when),
                            "name": KEPT_BOT[0], "email": KEPT_BOT[1],
                            "subject": "chore(deps): bump the pinned toolchain", "body": "",
                            "files": entries})

        # One revert, so "undone by a revert" is a real tier and not a legend entry with a zero.
        # The commit that was undone is chosen from work old enough for the revert itself to
        # have happened before the clock this fixture is fixed at.
        undone = max((c for c in commits
                      if c["email"] == KEPT_ME[1]
                      and from_unix_local(c["at"]) < NOW - timedelta(days=3)
                      and any(s <= from_unix_local(c["at"]) <= e + timedelta(minutes=30)
                              for s, e in sessions)),
                     key=lambda c: sum(f["added"] for f in c["files"]))
        revert_when = from_unix_local(undone["at"]) + timedelta(hours=rng.randint(4, 30))
        commits.append({"sha": "{0:012x}".format(rng.getrandbits(48)), "at": unix(revert_when),
                        "name": KEPT_HUMANS[0][0], "email": KEPT_HUMANS[0][1],
                        "subject": 'Revert "{0}"'.format(undone["subject"]),
                        "body": "This reverts commit {0}.".format(undone["sha"]),
                        "files": [{"path": f["path"], "added": f["deleted"], "deleted": f["added"]}
                                  for f in undone["files"]]})

        commits.sort(key=lambda c: (c["at"], c["sha"]))
        records.append({"kind": "commits", "repo": path, "commits": commits})
        tracked = sorted(set(files) - set(KEPT_DELETED[path]))
        records.append({"kind": "tracked", "repo": path, "paths": tracked})

        # Blame: one row per surviving line. Agent rows carry the sha of the commit that added
        # them, so the window decides who wrote them; human rows carry an identity key as well,
        # which is what separates "you" from "somebody else" in the control group.
        by_author = {}
        for c in commits:
            if c["subject"].startswith("Revert "):
                continue
            in_window = any(s <= from_unix_local(c["at"]) <= e + timedelta(minutes=30)
                            for s, e in sessions)
            for f in c["files"]:
                if f["path"] not in tracked:
                    continue
                by_author.setdefault(f["path"], []).append(
                    (c["sha"], f["added"], in_window, c["email"]))
        blame = {}
        for rel in tracked:
            rows = []
            for sha, added, in_window, email in by_author.get(rel, ()):
                keep = 0.62 if in_window else 0.79
                if "dependabot" in email:
                    keep = 0.9
                alive = int(added * (keep + rng.uniform(-0.12, 0.12)))
                rows += [[sha, 0, email]] * max(0, min(added, alive))
            if rows:
                blame[rel] = rows
        records.append({"kind": "blame", "repo": path, "lines": blame})

    return {"generated": stamp(NOW),
            "note": "an invented project and invented people; no transcript and no repository "
                    "on this machine was read",
            "records": records}


def from_unix_local(seconds):
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


# ---------------------------------------------------------------- extension-reach

# One row per install. The same extension in two browsers is two installs and one extension, which
# is the merge the card does; the fixture carries both so the merge has something to do.
#
# (id, name, version, mv, api permissions, host permissions, content matches, granted hosts,
#  enabled, install source, location label, installed days ago, updated days ago, idle days ago,
#  the browsers it is installed in)
EXT_ROWS = (
    ("hkgfoiooedgoejojocmhlaklaeopbecg", "Coupon Finder", "4.2.1", 3,
     ["cookies", "webRequest", "storage", "tabs"], ["<all_urls>"], ["<all_urls>"], ["<all_urls>"],
     True, "store", "from the Chrome Web Store", 640, 41, 3, ["Chrome", "Edge"]),
    ("mdnleldcmiljblolnjhpnblkcekpdkpa", "Page Translator", "2.9.0", 3,
     ["history", "downloads", "scripting", "storage"], ["<all_urls>"], [], ["<all_urls>"],
     True, "store", "from the Chrome Web Store", 880, 96, 61, ["Chrome"]),
    # Nobody has opened it in ten months and it still reads every page: the headline the card exists for.
    ("bcjindcccaagfpapjjmafapmmgkkhgoa", "JSON Formatter", "0.7.4", 3,
     ["storage"], ["<all_urls>"], ["<all_urls>"], ["<all_urls>"],
     True, "store", "from the Chrome Web Store", 1420, 742, 306, ["Chrome", "Arc"]),
    ("kbfnbcaeplbcioakkpcpgfkobkghlhen", "Old Ad Blocker", "1.14.2", 2,
     ["webRequestBlocking", "webRequest", "tabs"], ["http://*/*", "https://*/*"], [], ["https://*/*"],
     True, "sideloaded", "installed by another program on this machine", 1610, 831, 512, ["Chrome"]),
    ("gighmmpiobklfepjocnamgkkbiglidom", "Shop Compare", "6.0.3", 3,
     ["storage", "declarativeNetRequest"], ["*://*.com/*", "*://*.co.uk/*"], [], ["*://*.com/*"],
     True, "store", "from the Chrome Web Store", 410, 22, 9, ["Chrome"]),
    ("dbepggeogbaibhgnhhndojpepiihcmeb", "Corp Policy Agent", "3.1.0", 3,
     ["management", "nativeMessaging"], ["<all_urls>"], [], ["<all_urls>"],
     True, "policy", "installed by administrator policy", 300, 12, 2, ["Chrome", "Edge"]),
    ("cfhdojbkjhnklbpkdaibdccddilifddb", "Ledger Helper", "1.4.0", 3,
     ["storage", "activeTab"], ["https://app.example.com/*", "https://admin.example.com/*"],
     ["https://app.example.com/*"], ["https://app.example.com/*"],
     True, "store", "from the Chrome Web Store", 210, 17, 5, ["Chrome"]),
    ("aapbdbdomjkkjkaonfhkkikfgjllcleb", "Colour Picker", "2.0.1", 3,
     ["activeTab", "storage"], [], [], [],
     True, "store", "from the Chrome Web Store", 505, 190, 44, ["Chrome"]),
    ("ldgfbffkinooeloadekpmfoklnobpien", "Tab Counter", "1.1.0", 3,
     ["storage"], [], [], [],
     False, "store", "from the Chrome Web Store", 700, 402, 402, ["Chrome"]),
    # Granted less than it asked for: the card counts that separately from what it can reach today.
    ("nngceckbapebfimnlniiiahkandclblb", "Screenshot Studio", "5.5.2", 3,
     ["downloads", "storage", "scripting"], ["<all_urls>"], [], ["https://docs.example.com/*"],
     True, "store", "from the Chrome Web Store", 380, 58, 21, ["Chrome"], True),
    ("padekgcemlokbadohgkifijomclgjgif", "Local Dev Helper", "0.0.1", 3,
     ["debugger", "storage"], ["http://localhost/*", "<all_urls>"], [], ["<all_urls>"],
     True, "unpacked", "loaded unpacked from a folder", 96, 4, 1, ["Arc"]),
    ("eimadpbcbfnmbkopoojfekhnkhdbieeh", "Dark Reader", "4.9.98", 3,
     ["storage"], ["<all_urls>"], ["<all_urls>"], ["<all_urls>"],
     True, "store", "from the Chrome Web Store", 1180, 74, 6, ["Chrome", "Edge", "Arc"]),
    ("fmkadmapgofadopljbjfkapdkoienihi", "Frontend Devtools", "5.3.0", 3,
     ["scripting", "storage"], ["<all_urls>"], [], ["<all_urls>"],
     True, "store", "from the Chrome Web Store", 990, 133, 88, ["Chrome"]),
    ("dhdgffkkebhmkfjojejmpbldmpobfkfo", "Script Runner", "4.19.0", 2,
     ["clipboardRead", "storage", "tabs"], ["<all_urls>"], ["<all_urls>"], ["<all_urls>"],
     False, "sideloaded", "installed by another program on this machine", 1750, 903, 903, ["Chrome"]),
    ("ghmbeldphafepmbegfdlkpapadhbakde", "Proxy Switcher", "1.9.4", 3,
     ["proxy", "storage"], ["<all_urls>"], [], ["<all_urls>"],
     True, "store", "from the Chrome Web Store", 820, 470, 260, ["Edge"]),
)
EXT_FIREFOX = (
    ("uBlock0@raymondhill.net", "uBlock Origin", "1.60.0", 3,
     ["webRequest", "webRequestBlocking", "storage"], ["<all_urls>"], True, "store",
     "app-profile", 1290, 33, 33),
    ("{446900e4-71c2-419f-a6a7-df9c091e268b}", "Password Vault", "3.9.11", 3,
     ["clipboardRead", "storage", "tabs"], ["https://*/*"], True, "store", "app-profile", 940, 61, 61),
    ("reader@example.org", "Reading Mode", "0.4.2", 2,
     ["storage"], ["*://*.org/*"], True, "sideloaded", "winreg-app-user", 1500, 810, 810),
)
# Safari publishes names and enabled state to a reader outside the browser and nothing else, so
# these rows are the fixture's honest unknown: reach is "not published", never "none".
EXT_SAFARI = (("com.example.tabsaver", "Tab Saver", "2.1"),
              ("com.example.readerplus", "Reader Plus", "1.8"))
EXT_PROFILES = {"Chrome": ("Chrome", "Default"), "Edge": ("Microsoft Edge", "Default"),
                "Arc": ("Arc", "Profile 1")}


def build_extensions():
    out = []
    for row in EXT_ROWS:
        (ext_id, name, version, mv, perms, hosts, matches, granted, enabled, source, location,
         installed, updated, touched, browsers) = row[:15]
        withheld = bool(row[15]) if len(row) > 15 else False
        for badge in browsers:
            browser, profile = EXT_PROFILES[badge]
            out.append({
                "id": ext_id, "family": "chromium", "browser": browser, "profile": profile,
                "name": name, "version": version, "manifest_version": mv,
                "permissions": sorted(perms), "host_permissions": sorted(hosts),
                "optional_host_permissions": [], "content_matches": sorted(matches),
                "granted_hosts": sorted(granted), "hosts_withheld": withheld,
                "enabled": enabled, "install_source": source, "location_label": location,
                "installed": stamp(days(installed)), "updated": stamp(days(updated)),
                "updated_is_proxy": True, "state_touched": stamp(days(touched)),
                "settings_seen": True})
    for ext_id, name, version, mv, perms, hosts, enabled, source, location, installed, updated, touched \
            in EXT_FIREFOX:
        out.append({
            "id": ext_id, "family": "firefox", "browser": "Firefox", "profile": "default-release",
            "name": name, "version": version, "manifest_version": mv,
            "permissions": sorted(perms), "host_permissions": sorted(hosts),
            "optional_host_permissions": [], "content_matches": [], "granted_hosts": sorted(hosts),
            "hosts_withheld": False, "enabled": enabled, "install_source": source,
            "location_label": location, "installed": stamp(days(installed)),
            "updated": stamp(days(updated)), "updated_is_proxy": False,
            "state_touched": stamp(days(touched)), "settings_seen": True})
    for ext_id, name, version in EXT_SAFARI:
        out.append({
            "id": ext_id, "family": "safari", "browser": "Safari", "profile": "Default",
            "name": name, "version": version, "manifest_version": None,
            "permissions": [], "host_permissions": [], "optional_host_permissions": [],
            "content_matches": [], "granted_hosts": [], "hosts_withheld": False,
            "enabled": True, "install_source": "unknown", "location_label": "Safari container",
            "installed": "", "updated": "", "updated_is_proxy": True, "state_touched": "",
            "settings_seen": False, "reach_published": False})
    out.sort(key=lambda r: (r["family"], r["browser"], r["profile"], r["id"]))
    return {"generated": stamp(NOW),
            "note": "invented extensions on invented profiles; no browser on this machine was read",
            "installs": out}


# ---------------------------------------------------------------- where-it-went

# (domain, path template, weight). The categorised domains are the real ones the bundled table
# names, because a demo whose categories are all "uncategorised" would teach a reader nothing
# about the table; everything that could identify a person is an example.com host instead.
HIST_SITES = (
    ("github.com", "/acme-robotics/{0}/pull/{1}", 210),
    ("github.com", "/acme-robotics/{0}/actions/runs/{1}", 120),
    ("stackoverflow.com", "/questions/{1}/how-do-i-{0}", 84),
    ("docs.python.org", "/3/library/{0}.html", 46),
    ("developer.mozilla.org", "/en-US/docs/Web/API/{0}", 40),
    ("postgresql.org", "/docs/16/{0}.html", 22),
    ("claude.ai", "/chat/{1}", 96),
    ("chatgpt.com", "/c/{1}", 52),
    ("news.ycombinator.com", "/item?id={1}", 88),
    ("theguardian.com", "/technology/2026/{0}", 44),
    ("bbc.co.uk", "/news/articles/{1}", 40),
    ("reddit.com", "/r/{0}/comments/{1}", 76),
    ("linkedin.com", "/feed/update/{1}", 34),
    ("x.com", "/home", 62),
    ("youtube.com", "/watch?v={1}", 90),
    ("zoom.us", "/j/{1}", 18),
    ("gmail.com", "/mail/u/0/#inbox", 150),
    ("amazon.co.uk", "/dp/{1}", 40),
    ("ebay.com", "/itm/{1}", 14),
    ("monzo.com", "/account", 12),
    ("stripe.com", "/acct/payments/{1}", 26),
    ("app.example.com", "/dashboard/{0}", 130),
    ("app.example.com", "/orders/{1}", 70),
    ("status.example.net", "/incidents/{1}", 16),
    ("wiki.example.org", "/spaces/eng/pages/{1}", 58),
    ("localhost", ":5173/pricing", 64),
    ("google.com", "/search?q={0}", 120),
)
HIST_WORDS = ("settlement", "idempotency", "proration", "backpressure", "sqlite", "asyncio",
              "datetime", "pathlib", "subprocess", "webhooks", "netting", "rounding", "dunning",
              "collation", "vacuum", "explain", "fetch", "AbortController", "IntersectionObserver",
              "structuredClone", "python", "typescript", "postgres", "kafka", "terraform")
HIST_BROWSERS = (("Chrome", "chromium", 0.52), ("Arc", "chromium", 0.20),
                 ("Firefox", "firefox", 0.16), ("Safari", "safari", 0.12))
# The names the readers themselves produce: `linked`, `typed`, `reload`, and `other` for
# everything a browser records that is none of the three.
HIST_TRANSITIONS = (("linked", 0.62), ("typed", 0.17), ("reload", 0.11), ("other", 0.10))


def build_history():
    """Six months of visits, so the card has a window and a window before it to compare with.

    Rows rather than a copied SQLite file: a synthetic database would carry a schema version that
    drifts, and every timestamp in it would age out of the window the first time the clock moved.
    """
    rng = random.Random(9091)
    rows = []
    weights = [w for _, _, w in HIST_SITES]
    total_weight = float(sum(weights))
    browser_pick = []
    for name, family, share in HIST_BROWSERS:
        browser_pick += [(name, family)] * int(share * 100)

    for d in range(179, -1, -1):
        when_day = NOW - timedelta(days=d)
        weekday = when_day.weekday()
        # The second half of the window is busier than the first, which is what gives the trend
        # line something to be a trend about.
        load = 1.0 if d > 89 else 1.18
        base = 128 if weekday < 5 else 54
        count = max(4, int(rng.gauss(base * load, base * 0.24)))
        for _ in range(count):
            hour = rng.choice((8, 9, 9, 10, 10, 11, 11, 12, 13, 14, 14, 15, 15, 16, 16, 17,
                               18, 19, 20, 21, 22, 23))
            if d == 0 and hour >= 12:
                continue
            minute, second = rng.randrange(60), rng.randrange(60)
            pick = rng.random() * total_weight
            acc = 0.0
            domain, template = HIST_SITES[0][0], HIST_SITES[0][1]
            for dom, tpl, w in HIST_SITES:
                acc += w
                if pick <= acc:
                    domain, template = dom, tpl
                    break
            word = rng.choice(HIST_WORDS)
            path = template.format(word, rng.randrange(100000, 999999))
            scheme = "http://" if domain == "localhost" else "https://"
            url = "{0}{1}{2}".format(scheme, domain, path)
            browser, family = rng.choice(browser_pick)
            row = {"url": url, "when": stamp(when_day.replace(hour=hour, minute=minute, second=second)),
                   "browser": browser, "family": family}
            if family != "safari":
                pick_t = rng.random()
                acc_t = 0.0
                for kind, share in HIST_TRANSITIONS:
                    acc_t += share
                    if pick_t <= acc_t:
                        row["transition"] = kind
                        break
                row.setdefault("transition", "linked")
            rows.append(row)

    # The pages opened over and over: a list of things to automate, and the line people quote.
    for url, n, browser, family in (("https://github.com/acme-robotics/ledger-api/actions", 214, "Chrome", "chromium"),
                                    ("https://app.example.com/dashboard/settlement", 168, "Chrome", "chromium"),
                                    ("https://gmail.com/mail/u/0/#inbox", 402, "Chrome", "chromium"),
                                    ("https://status.example.net/", 96, "Arc", "chromium"),
                                    ("http://localhost:5173/pricing", 143, "Firefox", "firefox")):
        for i in range(n):
            d = rng.randrange(1, 90)
            when = (NOW - timedelta(days=d)).replace(hour=rng.randrange(8, 22),
                                                     minute=rng.randrange(60), second=rng.randrange(60))
            row = {"url": url, "when": stamp(when), "browser": browser, "family": family}
            if family != "safari":
                row["transition"] = "typed" if i % 4 == 0 else "reload"
            rows.append(row)

    # One long run inside a single evening, all on one domain: the "longest single-domain run".
    run_start = (NOW - timedelta(days=12)).replace(hour=20, minute=2, second=0)
    for i in range(41):
        rows.append({"url": "https://youtube.com/watch?v=demo{0:05d}".format(i),
                     "when": stamp(run_start + timedelta(minutes=4 * i)),
                     "browser": "Arc", "family": "chromium", "transition": "linked"})

    rows.sort(key=lambda r: (r["when"], r["url"]))
    return {"generated": stamp(NOW),
            "note": "synthetic visits; no browser history on this machine was read",
            "visits": rows}


# ---------------------------------------------------------------- photo-debt

PH_YEARS = ((2016, 480), (2017, 610), (2018, 720), (2019, 880), (2020, 640), (2021, 900),
            (2022, 1180), (2023, 1360), (2024, 1590), (2025, 1880), (2026, 1310))
PH_STILL_EXT = ((".heic", "HEIC", 4032, 3024), (".jpg", "JPG", 4032, 3024),
                (".jpg", "JPG", 3024, 4032), (".dng", "DNG", 6000, 4000))


def build_photos():
    """A library of about twelve thousand assets, as a manifest rather than as image files.

    A folder of real images in a checkout would carry the checkout's timestamps, so every capture
    date on the card would be the day the user cloned it. Duplicate groups carry their own SHA-256
    because the reader proves a duplicate from bytes and there are no bytes here to prove it from.
    """
    rng = random.Random(31337)
    rows, seq, taken = [], 1000, set()

    def slot(year):
        while True:
            when = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(
                days=rng.randrange(0, 365 if year != 2026 else 239),
                hours=rng.randrange(24), minutes=rng.randrange(60), seconds=rng.randrange(60))
            if when > NOW - timedelta(days=4):
                continue
            key = int(when.timestamp())
            if key in taken:
                continue
            taken.add(key)
            return when

    def add(**kw):
        rec = {"id": "p{0:06d}".format(len(rows) + 1)}
        rec.update(kw)
        rows.append(rec)
        return rec

    for year, count in PH_YEARS:
        for i in range(count):
            when = slot(year)
            folder = "{0}/{1:02d}".format(year, when.month)
            roll = rng.random()
            seq += 1
            size_salt = len(rows) + 1
            if roll < 0.135:
                shot_when = when.strftime("%Y-%m-%d at %H.%M.%S")
                add(filename="Screenshot {0}.png".format(shot_when),
                    stem="Screenshot {0}".format(shot_when), ext=".png", dir=folder,
                    captured=stamp(when), added=stamp(when + timedelta(minutes=1)),
                    width=rng.choice((1440, 1728, 2560, 3024)), height=rng.choice((900, 1117, 1440, 1964)),
                    bytes=rng.randrange(240000, 3400000) + size_salt, screenshot=True,
                    viewed=stamp(when + timedelta(days=rng.randrange(1, 60))) if rng.random() < 0.11 else "")
            elif roll < 0.225:
                big = rng.random() < 0.06
                add(filename="IMG_{0:04d}.MOV".format(seq), stem="IMG_{0:04d}".format(seq),
                    ext=".mov", dir=folder, captured=stamp(when),
                    added=stamp(when + timedelta(minutes=2)), width=1920, height=1080,
                    bytes=(rng.randrange(280000000, 940000000) if big
                           else rng.randrange(14000000, 62000000)) + size_salt,
                    video=True, favourite=rng.random() < 0.03)
            else:
                ext, tag, w, h = rng.choice(PH_STILL_EXT)
                rec = add(filename="IMG_{0:04d}.{1}".format(seq, tag), stem="IMG_{0:04d}".format(seq),
                          ext=ext, dir=folder, captured=stamp(when),
                          added=stamp(when + timedelta(minutes=rng.randrange(1, 400))),
                          width=w, height=h,
                          bytes=rng.randrange(1500000, 6200000) + size_salt,
                          favourite=rng.random() < 0.045, edited=rng.random() < 0.032)
                if rng.random() < 0.014:
                    rec["trashed"] = True
                if rng.random() < 0.055:
                    rec["local"] = False
                if rng.random() < 0.004:
                    rec["bytes"] = 0                     # the library records no size for this one
                if rng.random() < 0.085:
                    # A Live Photo: a still and a movie sharing a stem, counted once, not twice.
                    add(filename="{0}.MOV".format(rec["stem"]), stem=rec["stem"], ext=".mov",
                        dir=folder, captured=rec["captured"],
                        added=rec["added"], width=1440, height=1080,
                        bytes=rng.randrange(1400000, 3600000) + size_salt, video=True)

    # Bursts. Every frame shares one second, one frame size and a sequential file number, which is
    # exactly the inference the module documents; no image is decoded to find them.
    for _ in range(104):
        when = slot(rng.choice((2021, 2022, 2023, 2024, 2025, 2026)))
        folder = "{0}/{1:02d}".format(when.year, when.month)
        seq += 1
        frames = rng.randint(4, 12)
        for k in range(frames):
            add(filename="IMG_{0:04d}.HEIC".format(seq + k), stem="IMG_{0:04d}".format(seq + k),
                ext=".heic", dir=folder, captured=stamp(when),
                added=stamp(when + timedelta(minutes=3)), width=4032, height=3024,
                bytes=2600000 + rng.randrange(0, 40000) + k,
                favourite=(k == 0 and rng.random() < 0.35))
        seq += frames

    # The same file twice: identical bytes, proven by a digest the fixture carries because there
    # are no bytes on disk here to hash.
    stills = [r for r in rows if not r.get("video") and not r.get("screenshot")
              and r.get("bytes") and not r.get("trashed") and r.get("local", True)]
    for i, source in enumerate(rng.sample(stills, 58)):
        digest = hashlib.sha256("demo-duplicate-{0}".format(i).encode()).hexdigest()
        source["sha256"] = digest
        for copy in range(rng.randint(1, 3)):
            when = slot(rng.choice((2023, 2024, 2025, 2026)))
            add(filename="{0} ({1}){2}".format(source["stem"], copy + 1, source["ext"]),
                stem="{0} ({1})".format(source["stem"], copy + 1), ext=source["ext"],
                dir="{0}/{1:02d}".format(when.year, when.month), captured=stamp(when),
                added=stamp(when + timedelta(minutes=5)), width=source["width"],
                height=source["height"], bytes=source["bytes"], sha256=digest)

    # Two films of exactly the same size, too large to hash: shown, never counted as reclaimable.
    for name, when_year in (("Wedding-final-export.mov", 2024), ("Wedding-final-export-2.mov", 2025)):
        when = slot(when_year)
        add(filename=name, stem=name.rsplit(".", 1)[0], ext=".mov",
            dir="{0}/{1:02d}".format(when.year, when.month), captured=stamp(when),
            added=stamp(when + timedelta(hours=2)), width=3840, height=2160,
            bytes=511_000_000, video=True)

    rows.sort(key=lambda r: (r.get("captured") or "", r.get("filename") or "", r["id"]))
    return rows


# ---------------------------------------------------------------- what-grew

GREW_DIRS = (
    ("Library/Caches/Homebrew", 14_800_000_000), ("Library/Caches/pip", 3_100_000_000),
    ("Library/Caches/Yarn", 2_400_000_000), ("Library/Caches/Google/Chrome", 5_900_000_000),
    ("Library/Caches/com.apple.Safari", 1_800_000_000), ("Library/Caches/Arc", 2_050_000_000),
    ("Library/Caches/CloudKit", 900_000_000),
    ("Library/Developer/Xcode/DerivedData", 78_400_000_000),
    ("Library/Developer/Xcode/iOS DeviceSupport", 41_200_000_000),
    ("Library/Developer/CoreSimulator", 96_500_000_000),
    ("Library/Developer/Xcode/Archives", 22_900_000_000),
    ("Library/Containers/com.docker.docker", 64_300_000_000),
    ("Library/Application Support/Slack", 2_800_000_000),
    ("Library/Application Support/Code", 3_400_000_000),
    ("Library/Group Containers/group.com.example.notes", 1_240_000_000),
    ("Library/Mail", 9_600_000_000), ("Library/Messages", 5_100_000_000),
    (".cargo/registry", 11_700_000_000), (".gradle", 8_900_000_000),
    (".m2/repository", 6_400_000_000), ("go/pkg/mod", 19_300_000_000),
    (".npm/_cacache", 7_800_000_000), (".pyenv/versions", 4_600_000_000),
    ("Projects/ledger-api/node_modules", 3_900_000_000),
    ("Projects/ledger-api/.venv", 2_100_000_000),
    ("Projects/ledger-api/target", 5_700_000_000),
    ("Projects/pricing-web/node_modules", 6_200_000_000),
    ("Projects/pricing-web/.next", 1_900_000_000),
    ("Projects/pricing-web/dist", 640_000_000),
    ("Projects/ops-tooling/build", 1_100_000_000),
    ("Projects/archive/2024", 24_800_000_000),
    ("Pictures/Photos Library.photoslibrary", 148_600_000_000),
    ("Movies/exports", 61_400_000_000), ("Movies/screen-recordings", 18_700_000_000),
    ("Music/Media", 32_100_000_000), ("Documents/contracts", 4_300_000_000),
    ("Documents/decks", 7_900_000_000), ("Downloads", 26_400_000_000),
    ("Desktop", 3_800_000_000), ("Dropbox", 44_200_000_000),
    ("VirtualMachines", 88_300_000_000),
)


def build_grew():
    dirs = dict(GREW_DIRS)
    named = sum(dirs.values())
    other = 37_400_000_000
    total = named + other
    disk = 2_000_000_000_000
    free = 214_800_000_000
    return {
        "root": "/Users/demo", "depth": 4, "floor_bytes": 16 * 1024 * 1024,
        "dirs": dirs, "other_bytes": other, "total_bytes": total, "apparent_bytes": total + 9_100_000_000,
        "files": 1_284_902,
        # Three folders this run could not open. Their size is unknown and is in no total above,
        # which is the whole reason they are counted and named rather than skipped.
        "denied": ["Library/Group Containers/group.com.apple.notes",
                   "Library/Containers/com.apple.Safari",
                   "Library/Application Support/MobileSync"],
        "denied_count": 3,
        "placeholder_files": 18_402, "placeholder_bytes": 96_200_000_000,
        "on_disk_sizes": True, "free_bytes": free, "disk_total_bytes": disk,
        "disk_used_bytes": disk - free,
    }


def build_grew_previous():
    """The same disk eight days earlier, so the demo shows a delta and not the first-run card.

    A snapshot-diffing Play whose demo can only ever print "nothing to compare against yet" is
    demonstrating the one state it exists to get past, so the fixture ships two readings. The
    movement is chosen to exercise every class the report separates: caches and build output that
    grew, one simulator runtime that appeared whole, a download folder that shrank because things
    were finally filed, and a checkout that was deleted.
    """
    now = dict(GREW_DIRS)
    then = {}
    grew = {"Library/Developer/CoreSimulator": 0.34, "Library/Caches": 0.62,
            "Projects/ledger-api/node_modules": 0.55, "Library/Containers/com.docker.docker": 0.51,
            "Library/Developer/Xcode/DerivedData": 0.41, ".cache": 0.70}
    shrank = {"Downloads": 1.9}
    appeared = ("Library/Developer/Xcode/iOS DeviceSupport",)
    deleted = {"Projects/atlas-www": 4_820_000_000}
    for name, size in now.items():
        if name in appeared:
            continue                                    # not there eight days ago
        share = grew.get(name) or shrank.get(name) or 1.0
        then[name] = int(size * share)
    then.update(deleted)
    named = sum(then.values())
    other = 36_900_000_000
    total = named + other
    disk = 2_000_000_000_000
    free = 253_100_000_000                              # 38 GB more free space than today
    return {
        "captured": (NOW - timedelta(days=8)).isoformat(),
        "root": "/Users/demo", "depth": 4, "floor_bytes": 16 * 1024 * 1024,
        "dirs": then, "other_bytes": other, "total_bytes": total,
        "apparent_bytes": total + 8_800_000_000, "files": 1_231_580,
        "free_bytes": free, "disk_total_bytes": disk,
    }


# ---------------------------------------------------------------- standing-cost

# Everyone here is invented. Zones are carried as an offset as well as a name, because this package
# will not import a timezone database and an unresolvable name is reported as unknown, not guessed.
SC_PEOPLE = {
    "mira@example.com": ("Mira Solberg", "Europe/London", 60),
    "tomas@example.com": ("Tomas Halvorsen", "Europe/London", 60),
    "priya@example.com": ("Priya Raghavan", "Asia/Kolkata", 330),
    "daniel@example.com": ("Daniel Okafor", "Europe/London", 60),
    "yuki@example.com": ("Yuki Tanabe", "Asia/Tokyo", 540),
    "elena@example.com": ("Elena Marchetti", "Europe/Rome", 120),
    "casey@example.com": ("Casey Nolan", "America/New_York", -240),
    "robin@example.com": ("Robin Adeyemi", "Europe/London", 60),
    "sam@example.com": ("Sam Ortega", "America/Los_Angeles", -420),
    "noor@example.com": ("Noor Haddad", "Europe/London", 60),
    "wei@example.com": ("Wei Chen", "Asia/Singapore", 480),
    "ada@example.com": ("Ada Fenwick", "", None),          # no zone: counted, and said to be unknown
}
SC_ALL = sorted(SC_PEOPLE)


def _sc_attendee(email, response, attended=None, optional=False):
    name, zone, offset = SC_PEOPLE[email]
    row = {"email": email, "display_name": name, "response_status": response,
           "optional": optional, "self": email == "mira@example.com",
           "organizer": email == "mira@example.com"}
    if zone:
        row["timezone"] = zone
    if offset is not None:
        row["utc_offset_minutes"] = offset
    if attended is not None:
        row["attended"] = attended
    return row


def build_standingcost():
    """A year of one calendar, as the normalised partial the Play's calendar step writes.

    This module never fetches: the network half is a separate step, and the demo stands in for
    that step's output so a cold run works with no account attached at all.
    """
    rng = random.Random(60601)
    events = []
    counter = [0]

    def emit_series(series_id, summary, weekdays, minutes, hour, people, weeks, cancel_rate,
                    agenda_link="", attendance=False, absent=(), never_accept=(), grow=None,
                    every=1):
        made = 0
        for d in range(363, 0, -1):
            when = NOW - timedelta(days=d)
            if when.weekday() not in weekdays:
                continue
            if every > 1 and (d // 7) % every:
                continue
            made += 1
            if weeks and made > weeks:
                break
            second_half = grow and made > (weeks or 999) // 2
            length = (grow[0] if second_half else minutes) if grow else minutes
            crew = list(people) + (list(grow[1]) if second_half and grow else [])
            counter[0] += 1
            cancelled = rng.random() < cancel_rate
            attendees = []
            for email in crew:
                if email in never_accept:
                    attendees.append(_sc_attendee(email, "needsAction",
                                                  False if attendance else None))
                    continue
                if email in absent:
                    attendees.append(_sc_attendee(email, "accepted", False if attendance else None))
                    continue
                roll = rng.random()
                if roll < 0.09:
                    attendees.append(_sc_attendee(email, "declined"))
                elif roll < 0.17:
                    attendees.append(_sc_attendee(email, "tentative",
                                                  rng.random() < 0.6 if attendance else None))
                else:
                    attendees.append(_sc_attendee(email, "accepted",
                                                  rng.random() < 0.93 if attendance else None))
            start = when.replace(hour=hour, minute=0, second=0, microsecond=0)
            event = {"id": "evt_{0:05d}".format(counter[0]), "recurring_event_id": series_id,
                     "summary": summary, "start": stamp(start),
                     "end": stamp(start + timedelta(minutes=length)),
                     "status": "cancelled" if cancelled else "confirmed",
                     "organizer": "mira@example.com", "attendance_recorded": bool(attendance),
                     "attendees": attendees}
            if agenda_link:
                event["agenda_link"] = agenda_link
            events.append(event)

    # The one everybody recognises: short, frequent, and it grew.
    emit_series("series_standup", "Engineering Standup", (0, 2, 4), 15, 9,
                ["mira@example.com", "tomas@example.com", "priya@example.com",
                 "yuki@example.com", "elena@example.com", "noor@example.com",
                 "robin@example.com", "wei@example.com"], 156, 0.05,
                grow=(25, ["sam@example.com", "casey@example.com", "ada@example.com"]))
    # Casey is invited to every single one of these and has never once accepted.
    emit_series("series_product", "Weekly Product Review", (3,), 60, 15,
                ["mira@example.com", "tomas@example.com", "priya@example.com", "elena@example.com",
                 "noor@example.com", "sam@example.com", "wei@example.com", "casey@example.com",
                 "robin@example.com", "yuki@example.com", "ada@example.com"], 52, 0.11,
                agenda_link="https://wiki.example.org/spaces/eng/pages/product-review",
                never_accept=("casey@example.com",))
    # Robin accepts every time and the attendance log says nobody was there.
    emit_series("series_critique", "Design Critique", (1,), 60, 16,
                ["mira@example.com", "elena@example.com", "yuki@example.com", "noor@example.com",
                 "robin@example.com"], 44, 0.07, attendance=True, absent=("robin@example.com",))
    emit_series("series_arch", "Architecture Sync", (2,), 90, 13,
                ["mira@example.com", "tomas@example.com", "priya@example.com", "wei@example.com",
                 "sam@example.com", "elena@example.com"], 26, 0.08, every=2,
                agenda_link="https://wiki.example.org/spaces/eng/pages/architecture")
    emit_series("series_pricing", "Pricing Working Group", (4,), 45, 11,
                ["mira@example.com", "priya@example.com", "elena@example.com", "noor@example.com",
                 "casey@example.com"], 52, 0.27)
    emit_series("series_oneone", "1:1 Mira / Tomas", (1,), 30, 10,
                ["mira@example.com", "tomas@example.com"], 48, 0.10, attendance=True)
    emit_series("series_incident", "Incident Review", (4,), 45, 17,
                ["mira@example.com", "tomas@example.com", "yuki@example.com", "wei@example.com",
                 "sam@example.com", "noor@example.com"], 12, 0.04, every=4,
                agenda_link="https://wiki.example.org/spaces/eng/pages/incidents")
    emit_series("series_allhands", "Monthly All Hands", (2,), 60, 16, SC_ALL, 12, 0.05, every=4)

    # One-off meetings, which are counted and reported separately from any series.
    for i in range(34):
        d = rng.randrange(2, 360)
        when = (NOW - timedelta(days=d)).replace(hour=rng.choice((10, 11, 14, 15, 16)),
                                                 minute=rng.choice((0, 30)), second=0, microsecond=0)
        crew = rng.sample(SC_ALL, rng.randint(2, 6))
        if "mira@example.com" not in crew:
            crew.append("mira@example.com")
        counter[0] += 1
        events.append({
            "id": "evt_{0:05d}".format(counter[0]), "recurring_event_id": "",
            "summary": rng.choice(("Vendor call", "Interview loop", "Roadmap deep dive",
                                   "Contract review", "Customer escalation", "Offsite planning")),
            "start": stamp(when), "end": stamp(when + timedelta(minutes=rng.choice((30, 45, 60, 90)))),
            "status": "confirmed", "organizer": "mira@example.com",
            "attendance_recorded": False,
            "attendees": [_sc_attendee(e, "accepted") for e in sorted(crew)]})

    # Three events the feed sent without an end time. They are kept, counted and named as
    # unusable rather than dropped, because "812 events and 3 of them were broken" is a fact.
    for i in range(3):
        counter[0] += 1
        when = NOW - timedelta(days=40 + i * 30)
        events.append({"id": "evt_{0:05d}".format(counter[0]), "recurring_event_id": "",
                       "summary": "Blocked: focus time", "start": stamp(when), "end": "",
                       "status": "confirmed", "organizer": "mira@example.com",
                       "attendees": [_sc_attendee("mira@example.com", "accepted")]})

    events.sort(key=lambda e: (e["start"], e["id"]))
    return {"schema": 1, "source": "google-calendar (bundled demo)", "account": "work",
            "fetched": stamp(NOW), "timezone": "Europe/London", "truncated": False,
            "note": "an invented calendar; nothing was fetched and no real meeting is described",
            "window": {"start": stamp(NOW - timedelta(days=365)), "end": stamp(NOW)},
            "events": events}


# ---------------------------------------------------------------- reply-debt

RD_ME = "mira@example.com"
RD_PEOPLE = (("dana@example.com", "Dana Okoye"), ("felix@example.com", "Felix Baumann"),
             ("harper@example.com", "Harper Quinn"), ("ines@example.com", "Ines Duarte"),
             ("jonah@example.com", "Jonah Reyes"), ("kirra@example.com", "Kirra Willis"),
             ("liam@example.com", "Liam Novak"), ("maya@example.com", "Maya Farrow"),
             ("nils@example.com", "Nils Eriksen"), ("orla@example.com", "Orla Byrne"))
RD_DIRECT = (
    "Could you send the signed copy before Friday?",
    "Can you confirm the settlement window we agreed?",
    "Any update on the pricing grid? The customer is waiting.",
    "Would you mind reviewing the redlines on clause 7?",
    "Please let me know which of the two dates works.",
    "Do you have a moment to look at the failing batch?",
    "What should we tell the auditor about the netting run?",
    "Circling back on the invoice — is it approved?",
    "Please confirm the seat count before we renew.",
    "Are you able to join the escalation call tomorrow?",
)
RD_IMPLIED = (
    "Attaching the Q3 numbers for your review.",
    "Heads up: the vendor contract renews at the end of the month.",
    "For sign-off when you have a moment — no rush.",
    "Flagging that the sandbox expires by Friday.",
    "For visibility: the migration window moved to next week.",
    "Over to you for the final read before the deadline.",
)
RD_FYI = (
    "Sharing the notes from Tuesday, nothing needed.",
    "The deploy finished cleanly overnight.",
    "Welcome to the team, everyone.",
    "The office will be closed on Monday.",
    "Minutes are on the wiki.",
)


def _rd_msg(sender, to, when, subject, snippet, direction, **kw):
    row = {"from": sender, "to": to, "date": stamp(when), "direction": direction,
           "subject": subject, "snippet": snippet}
    row.update(kw)
    return row


def build_replydebt():
    """One normalised mailbox, as the Play's mail step would leave it.

    Two threads earn their place on their own. One is the quoted-history case: the newest message
    carries no ask of its own and quotes a question that was already answered, and the rule strips
    the quote before it matches, so the thread must NOT be counted as debt. The other is the debt
    owed the other way -- your own question, unanswered for weeks -- because a Play that only
    counts what you owe is an instrument of guilt rather than a measurement.
    """
    rng = random.Random(5150)
    me = {"name": "Mira Solberg", "email": RD_ME}
    threads = []

    def thread(tid, subject, other, messages, labels=None):
        threads.append({"thread_id": tid, "subject": subject, "labels": labels or ["INBOX"],
                        "participants": [me, {"name": other[1], "email": other[0]}],
                        "messages": messages})

    # -- direct asks, oldest first ------------------------------------------------------------
    for i, text in enumerate(RD_DIRECT):
        other = RD_PEOPLE[i % len(RD_PEOPLE)]
        sender = {"name": other[1], "email": other[0]}
        age = (4, 6, 9, 13, 18, 24, 33, 47, 61, 88)[i]
        subject = ("Contract redlines", "Settlement window", "Pricing grid", "Clause 7",
                   "Two dates", "Failing batch", "Audit question", "Invoice 4410",
                   "Renewal seats", "Escalation call")[i]
        msgs = []
        if i % 3 == 0:
            msgs.append(_rd_msg(me, [sender], days(age + 6), subject,
                                "Here is where we got to.", "outbound"))
        msgs.append(_rd_msg(sender, [me], days(age + 2), subject,
                            "Following up on this.", "inbound"))
        msgs.append(_rd_msg(sender, [me], days(age), subject, text, "inbound"))
        thread("t-direct-{0:02d}".format(i), subject, other, msgs)

    # -- one person, several threads: the repeat-sender section ------------------------------
    for i in range(3):
        other = RD_PEOPLE[3]
        sender = {"name": other[1], "email": other[0]}
        subject = ("Data room access", "Second data room question", "Data room, once more")[i]
        thread("t-repeat-{0}".format(i), subject, other,
               [_rd_msg(sender, [me], days(21 + i * 9), subject,
                        "Could you grant access to the folder? I still cannot open it.", "inbound")])

    # -- FYI with an implied action ------------------------------------------------------------
    for i, text in enumerate(RD_IMPLIED):
        other = RD_PEOPLE[(i + 5) % len(RD_PEOPLE)]
        sender = {"name": other[1], "email": other[0]}
        subject = ("Q3 numbers", "Vendor renewal", "Final read", "Sandbox expiry",
                   "Migration window", "Final read, again")[i]
        thread("t-implied-{0:02d}".format(i), subject, other,
               [_rd_msg(sender, [me], days(7 + i * 5), subject, text, "inbound")])

    # -- pure FYI: no signal at all, and not counted as debt -----------------------------------
    for i, text in enumerate(RD_FYI):
        other = RD_PEOPLE[(i + 2) % len(RD_PEOPLE)]
        sender = {"name": other[1], "email": other[0]}
        subject = ("Tuesday notes", "Overnight deploy", "Welcome", "Bank holiday", "Minutes")[i]
        thread("t-fyi-{0:02d}".format(i), subject, other,
               [_rd_msg(sender, [me], days(5 + i * 3), subject, text, "inbound")])

    # -- the quoted-history case: the question in this message is one you already answered ------
    quoted = RD_PEOPLE[7]
    sender = {"name": quoted[1], "email": quoted[0]}
    thread("t-quoted-00", "Notes from Tuesday", quoted, [
        _rd_msg(sender, [me], days(19), "Notes from Tuesday",
                "Could you send the signed copy by Friday?", "inbound"),
        _rd_msg(me, [sender], days(18), "Re: Notes from Tuesday",
                "Sent it over this morning.", "outbound"),
        _rd_msg(sender, [me], days(17), "Re: Notes from Tuesday",
                "Thanks, got it. Nothing else from me.\n\n"
                "On Mon, 14 Aug 2026 at 09:12, Mira Solberg wrote:\n"
                "> Sent it over this morning.\n"
                "> > Could you send the signed copy by Friday?\n"
                "> > Would you mind confirming the seat count as well?\n", "inbound")])

    # -- debt owed to you: your question, nobody answered --------------------------------------
    for i in range(3):
        other = RD_PEOPLE[(i + 6) % len(RD_PEOPLE)]
        sender = {"name": other[1], "email": other[0]}
        subject = ("Invoice query", "Sandbox quota", "Reference call")[i]
        thread("t-owed-{0}".format(i), subject, other, [
            _rd_msg(sender, [me], days(40 + i * 12), subject, "Here is the summary.", "inbound"),
            _rd_msg(me, [sender], days(31 + i * 12), subject,
                    "Could you confirm the amount before I approve it?", "outbound")])

    # -- too recent to count: newer than the minimum age ---------------------------------------
    for i in range(4):
        other = RD_PEOPLE[i]
        sender = {"name": other[1], "email": other[0]}
        thread("t-recent-{0}".format(i), "Today's question", other,
               [_rd_msg(sender, [me], NOW - timedelta(hours=6 + i * 9), "Today's question",
                        "Can you take a look at this when you get in?", "inbound")])

    # -- excluded, one thread per reason -------------------------------------------------------
    listing = {"name": "Weekly Digest", "email": "digest@lists.example.com"}
    thread("t-excl-list", "Your weekly digest", ("digest@lists.example.com", "Weekly Digest"),
           [_rd_msg(listing, [me], days(6), "Your weekly digest",
                    "Could you take a look at this week's picks?", "inbound",
                    list_id="<weekly.lists.example.com>",
                    list_unsubscribe="<mailto:unsub@lists.example.com>")],
           labels=["INBOX", "CATEGORY_PROMOTIONS"])
    invite = {"name": "Elena Marchetti", "email": "elena@example.com"}
    thread("t-excl-cal", "Invitation: Architecture Sync", ("elena@example.com", "Elena Marchetti"),
           [_rd_msg(invite, [me], days(9), "Invitation: Architecture Sync @ Wed 13:00",
                    "Please confirm your attendance.", "inbound", is_calendar=True)])
    noreply = {"name": "Build Robot", "email": "no-reply@ci.example.net"}
    thread("t-excl-noreply", "Build 4821 failed", ("no-reply@ci.example.net", "Build Robot"),
           [_rd_msg(noreply, [me], days(4), "Build 4821 failed",
                    "Could you check the failing step? Action required.", "inbound")])
    autom = {"name": "Ledger Status", "email": "status@ops.example.net"}
    thread("t-excl-auto", "Settlement job degraded", ("status@ops.example.net", "Ledger Status"),
           [_rd_msg(autom, [me], days(3), "Settlement job degraded",
                    "Please acknowledge this alert.", "inbound", is_automated=True)])

    # -- a long tail of older correspondence, so the age buckets have a shape ------------------
    for i in range(16):
        other = RD_PEOPLE[i % len(RD_PEOPLE)]
        sender = {"name": other[1], "email": other[0]}
        age = 34 + i * 11
        text = rng.choice(RD_DIRECT if i % 2 else RD_IMPLIED)
        thread("t-tail-{0:02d}".format(i), "Follow-up {0}".format(i + 1), other,
               [_rd_msg(sender, [me], days(age), "Follow-up {0}".format(i + 1), text, "inbound")])

    threads.sort(key=lambda t: t["thread_id"])
    return {"schema": 1, "account": RD_ME, "me": [RD_ME, "mira@work.example.com"],
            "generated": stamp(NOW), "truncated": False, "threads": threads}


# ---------------------------------------------------------------- upstream-pulse

# Every package name below is invented. Saying "this package has one publisher and has not shipped
# in four years" about a real project would be a claim this fixture cannot stand behind, and a demo
# is not the place to put one.
UP_NPM_PROD = ("date-fmt-lite", "qs-lite", "currency-x", "numeral-lite", "tiny-emitter-x",
               "deep-freeze2", "objpath", "ms-parse", "unwrap-args", "slugify-tiny",
               "cookie-jarred", "keepalive-agent2", "retry-policy", "csv-stringify-lite",
               "svg-sprite-min", "focus-trap-lite", "aria-live", "colour-contrast",
               "money-fmt", "idb-keyvalue", "url-template-x", "jwt-decode-lite",
               "markdown-inline", "sanitise-html-lite")
UP_NPM_DEV = ("vitest-lite", "eslint-config-house", "prettier-house", "tsx-runner",
              "type-fest-lite", "msw-lite", "playwright-shim", "coverage-report",
              "bundle-size-check", "stylelint-house", "changeset-lite", "depcheck-lite")
UP_NPM_TRANSITIVE = ("ansi-styles-x", "chalkish", "picomatch-lite", "supports-colour",
                     "escape-string", "graceful-fs2", "is-plain-obj", "kind-of-x",
                     "lru-cache-tiny", "mime-db-lite", "nanoid-x", "once-only", "path-key-x",
                     "queue-tick", "readable-stream-lite", "safe-buffer-x", "semver-lite",
                     "shebang-cmd", "signal-exit-x", "string-width-lite", "strip-ansi-x",
                     "to-regex-x", "universalify-x", "wrappy-x", "yallist-lite",
                     "brace-expand-x", "cross-spawn-lite", "define-lazy", "emoji-regex-lite",
                     "fast-deep-eq", "get-stream-x", "human-signals-x")
UP_PY_PROD = ("httpx-lite", "pydantic-slim", "sqlalchemy-mini", "alembic-lite", "uvicorn-tiny",
              "orjson-lite", "structlog-lite", "tenacity-lite", "xmlsec-lite",
              "dateutil-lite", "pyjwt-lite", "cachetools-lite", "boto-shim", "dnspython-lite")
UP_PY_DEV = ("pytest-lite", "mypy-shim", "ruff-house", "coverage-lite", "hypothesis-lite",
             "faker-lite")
UP_PY_TRANSITIVE = ("anyio-lite", "certifi-shim", "h11-lite", "idna-lite", "sniffio-lite",
                    "greenlet-mini", "mako-lite", "markupsafe-lite", "six-shim", "typing-ext-lite")
UP_RS_PROD = ("axum-lite", "hyperish", "serde-mini", "tokio-slim", "tracing-lite", "clap-tiny",
              "reqwest-shim", "rustls-mini")
UP_RS_TRANSITIVE = ("bytes-x", "futures-core-x", "http-body-x", "mio-lite", "pin-project-x",
                    "slab-x", "smallvec-x", "tower-lite")
UP_REQ_DEV = ("pytest-benchmark-lite", "nbconvert-shim", "papermill-lite", "great-tables-lite",
              "pandera-lite", "duckdb-shim", "polars-shim", "ipykernel-lite")


def _up_version(rng):
    return "{0}.{1}.{2}".format(rng.randint(0, 9), rng.randint(0, 22), rng.randint(0, 30))


def _up_bump(version: str) -> str:
    """The version the registry offers, one step ahead of the one the lockfile pins."""
    major, minor, patch = (version.split(".") + ["0", "0"])[:3]
    return "{0}.{1}.{2}".format(major, int(minor) + 1, 0)


def build_upstream_tree(rng):
    """A small project tree the real lockfile readers walk, not a manifest of pre-chewed answers."""
    files = {}
    versions = {}
    for name in UP_NPM_PROD + UP_NPM_DEV + UP_NPM_TRANSITIVE + UP_PY_PROD + UP_PY_DEV + \
            UP_PY_TRANSITIVE + UP_RS_PROD + UP_RS_TRANSITIVE + UP_REQ_DEV:
        versions[name] = _up_version(rng)

    # -- npm ----------------------------------------------------------------------------------
    kids = {}
    pool = list(UP_NPM_TRANSITIVE)
    for i, name in enumerate(UP_NPM_PROD + UP_NPM_DEV):
        kids[name] = sorted(pool[(i * 3) % len(pool):(i * 3) % len(pool) + rng.randint(1, 3)])
    entries = {"": {"name": "web-console", "version": "2.4.0",
                    "dependencies": dict((n, "^" + versions[n]) for n in UP_NPM_PROD),
                    "devDependencies": dict((n, "^" + versions[n]) for n in UP_NPM_DEV)}}
    for name in UP_NPM_PROD:
        entries["node_modules/" + name] = {"version": versions[name],
                                           "dependencies": dict((k, "^" + versions[k]) for k in kids[name])}
    for name in UP_NPM_DEV:
        entries["node_modules/" + name] = {"version": versions[name], "dev": True,
                                           "dependencies": dict((k, "^" + versions[k]) for k in kids[name])}
    for name in UP_NPM_TRANSITIVE:
        entries["node_modules/" + name] = {"version": versions[name]}
    files["web-console/package.json"] = json.dumps(
        {"name": "web-console", "version": "2.4.0", "private": True,
         "dependencies": dict((n, "^" + versions[n]) for n in UP_NPM_PROD),
         "devDependencies": dict((n, "^" + versions[n]) for n in UP_NPM_DEV)},
        indent=2, sort_keys=True) + "\n"
    files["web-console/package-lock.json"] = json.dumps(
        {"name": "web-console", "version": "2.4.0", "lockfileVersion": 3, "requires": True,
         "packages": entries}, indent=1, sort_keys=True) + "\n"

    # -- pypi ---------------------------------------------------------------------------------
    py_lines = []
    for name in UP_PY_PROD + UP_PY_DEV + UP_PY_TRANSITIVE:
        group = "dev" if name in UP_PY_DEV else "main"
        py_lines += ["[[package]]", 'name = "{0}"'.format(name),
                     'version = "{0}"'.format(versions[name]),
                     'description = "a package invented for this demo"',
                     "optional = false", 'python-versions = ">=3.9"',
                     'groups = ["{0}"]'.format(group)]
        if name in UP_PY_PROD:
            deps = sorted(UP_PY_TRANSITIVE[(UP_PY_PROD.index(name) * 2) % len(UP_PY_TRANSITIVE):]
                          [:rng.randint(1, 3)])
            if deps:
                py_lines.append("")
                py_lines.append("[package.dependencies]")
                py_lines += ['{0} = ">={1}"'.format(d, versions[d]) for d in deps]
        py_lines.append("")
    py_lines += ["[metadata]", 'lock-version = "2.1"', 'python-versions = ">=3.9,<4.0"', ""]
    files["billing-service/poetry.lock"] = "\n".join(py_lines)
    files["billing-service/pyproject.toml"] = "\n".join(
        ["[tool.poetry]", 'name = "billing-service"', 'version = "1.9.0"', "",
         "[tool.poetry.dependencies]", 'python = ">=3.9,<4.0"']
        + ['{0} = "^{1}"'.format(n, versions[n]) for n in UP_PY_PROD]
        + ["", "[tool.poetry.group.dev.dependencies]"]
        + ['{0} = "^{1}"'.format(n, versions[n]) for n in UP_PY_DEV] + [""])

    # -- crates -------------------------------------------------------------------------------
    rs = ['version = 4', ""]
    rs += ["[[package]]", 'name = "edge-router"', 'version = "0.6.2"',
           "dependencies = [", "  " + ",\n  ".join('"{0}"'.format(n) for n in UP_RS_PROD), "]", ""]
    for i, name in enumerate(UP_RS_PROD):
        deps = list(UP_RS_TRANSITIVE[i % len(UP_RS_TRANSITIVE):][:2])
        rs += ["[[package]]", 'name = "{0}"'.format(name), 'version = "{0}"'.format(versions[name]),
               'source = "registry+https://github.com/rust-lang/crates.io-index"']
        if deps:
            rs += ["dependencies = [", "  " + ",\n  ".join('"{0}"'.format(d) for d in deps), "]"]
        rs.append("")
    for name in UP_RS_TRANSITIVE:
        rs += ["[[package]]", 'name = "{0}"'.format(name), 'version = "{0}"'.format(versions[name]),
               'source = "registry+https://github.com/rust-lang/crates.io-index"', ""]
    files["edge-router/Cargo.lock"] = "\n".join(rs)
    files["edge-router/Cargo.toml"] = "\n".join(
        ["[package]", 'name = "edge-router"', 'version = "0.6.2"', 'edition = "2021"', "",
         "[dependencies]"] + ['{0} = "{1}"'.format(n, versions[n]) for n in UP_RS_PROD] + [""])

    # -- a dev-only requirements file ----------------------------------------------------------
    files["data-jobs/requirements-dev.txt"] = "".join(
        "{0}=={1}\n".format(n, versions[n]) for n in UP_REQ_DEV)

    # -- the degradation: a lockfile that stops mid-object -------------------------------------
    # A write that was interrupted. The reader has to say so and cost this one file, rather than
    # failing the run or quietly reporting a project with no dependencies in it.
    files["legacy-batch/package-lock.json"] = (
        '{\n  "name": "legacy-batch",\n  "version": "0.3.1",\n  "lockfileVersion": 3,\n'
        '  "packages": {\n    "": {\n      "name": "legacy-batch",\n')
    return files, versions


def build_upstream_registry(versions, rng):
    """What the Play's network step would have written. Some lookups fail and some are absent,
    because "we did not check it" has to read differently from "it is fine"."""
    packages = []

    def entry(name, eco, last_days, maintainers, releases, **kw):
        row = {"name": name, "ecosystem": eco, "pinned_version": versions[name],
               "latest_version": kw.pop("latest", versions[name]),
               "maintainer_count": maintainers, "error": ""}
        if last_days is not None:
            row["last_release_date"] = stamp(days(last_days))
            row["release_dates"] = [stamp(days(d)) for d in releases]
        row.update(kw)
        packages.append(row)

    # The headline class, in two ecosystems: no release in years, one account can publish, and
    # both sit in the production request path.
    entry("date-fmt-lite", "npm", 1640, 1, [2300, 2010, 1640],
          latest=_up_bump(versions["date-fmt-lite"]),
          repository_archived=True, license="MIT", pinned_license="MIT")
    entry("xmlsec-lite", "pypi", 2110, 1, [2800, 2440, 2110],
          latest=_up_bump(versions["xmlsec-lite"]),
          repository_archived=True, license="MIT", pinned_license="MIT")
    entry("objpath", "npm", 1180, 1, [1900, 1520, 1180], license="ISC", pinned_license="ISC")
    entry("aria-live", "npm", 980, 1, [1700, 1310, 980], license="MIT", pinned_license="MIT")
    # Deprecated, and the registry itself names the replacement. Nothing here is inferred.
    entry("ms-parse", "npm", 1490, 2, [2100, 1780, 1490], deprecated=True,
          deprecation_message="no longer maintained; use duration-parse instead",
          successor="duration-parse", license="MIT", pinned_license="MIT")
    entry("boto-shim", "pypi", 860, 3, [1500, 1150, 860], deprecated=True,
          deprecation_message="this project has been retired", successor="",
          license="Apache-2.0", pinned_license="Apache-2.0")
    # The licence under the version you pin is not the licence of the latest one.
    entry("keepalive-agent2", "npm", 210, 4, [700, 430, 210],
          latest=_up_bump(versions["keepalive-agent2"]),
          license="BUSL-1.1", pinned_license="MIT")
    entry("sanitise-html-lite", "npm", 96, 6, [640, 380, 96], license="MIT", pinned_license="MIT")

    healthy_npm = [n for n in UP_NPM_PROD + UP_NPM_DEV
                   if n not in {p["name"] for p in packages}]
    for i, name in enumerate(healthy_npm):
        if i % 7 == 5:
            packages.append({"name": name, "ecosystem": "npm", "error": "registry timed out"})
            continue
        if i % 9 == 8:
            continue                                    # absent: not checked, never "fine"
        last = (24, 61, 118, 210, 320, 410, 640)[i % 7]
        entry(name, "npm", last, (2, 3, 5, 8, 14)[i % 5],
              [last + 800, last + 380, last], license="MIT", pinned_license="MIT")
    healthy_py = [n for n in UP_PY_PROD + UP_PY_DEV if n not in {p["name"] for p in packages}]
    for i, name in enumerate(healthy_py):
        if i % 8 == 7:
            packages.append({"name": name, "ecosystem": "pypi", "error": "404 from the index"})
            continue
        last = (33, 74, 140, 260, 380, 520)[i % 6]
        entry(name, "pypi", last, (1, 2, 4, 9)[i % 4], [last + 700, last + 300, last],
              license="Apache-2.0", pinned_license="Apache-2.0")
    for i, name in enumerate(UP_RS_PROD):
        last = (18, 55, 130, 240, 900)[i % 5]
        entry(name, "crates", last, (1, 3, 6)[i % 3], [last + 620, last + 250, last],
              license="MIT OR Apache-2.0", pinned_license="MIT OR Apache-2.0")
    for i, name in enumerate(UP_REQ_DEV):
        last = (45, 120, 300)[i % 3]
        entry(name, "pypi", last, (2, 5, 11)[i % 3], [last + 500, last + 200, last],
              license="BSD-3-Clause", pinned_license="BSD-3-Clause")

    packages.sort(key=lambda p: (p["ecosystem"], p["name"]))
    return {"schema": 1, "cached_at": stamp(NOW - timedelta(hours=6)),
            "source": "registry.npmjs.org, pypi.org, crates.io (bundled demo answers)",
            "requested": len(packages) + 9, "packages": packages}


# ---------------------------------------------------------------- write

def write(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    elif isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("  {0:<52} {1:>8} bytes".format(str(path.relative_to(ROOT)), path.stat().st_size))


def main() -> int:
    print("fixtures, clock fixed at {0}".format(NOW.isoformat()))
    write(FIX / "tabs" / "chrome-session.snss", build_chrome())
    write(FIX / "tabs" / "firefox-sessionstore.json", build_firefox())
    write(FIX / "tabs" / "safari-lastsession.plist", plistlib.dumps(build_safari()))
    write(FIX / "tabs" / "safari-bookmarks.plist", plistlib.dumps(build_reading_list()))
    write(FIX / "tabs" / "arc-sidebar.json", build_arc())
    write(FIX / "contacts" / "contacts.vcf", VCARD)
    write(FIX / "apps" / "apps.json", build_apps())
    write(FIX / "apps" / "casks.json", build_casks())
    write(FIX / "clutter" / "files.json", build_clutter())
    for name, body in sorted(NOTES.items()):
        write(FIX / "notes" / "vault" / name, body)
    write(FIX / "receipts" / "netflix-receipt.eml", EML)
    write(FIX / "receipts" / "flyio-invoice.eml", EML2)
    write(FIX / "receipts" / "spotify-receipt.eml", EML3)
    write(FIX / "receipts" / "bookshop-order.html", HTML_RECEIPT)
    write(FIX / "receipts" / "not-a-receipt-deck.txt", DECK)
    write(FIX / "receipts" / "hosting-invoice.pdf", build_pdf([
        b"Acme Hosting Ltd", b"Tax invoice", b"Invoice number: AH-2026-0088",
        b"Invoice date: 2026-08-18", b"Service period: 01 Aug 2026 - 31 Aug 2026",
        b"Sub-total  $60.00", b"VAT 20%    $12.00", b"Amount due $72.00",
        b"Payment method: card ending 4242"]))
    write(FIX / "receipts" / "scanned-receipt.pdf",
          b"%PDF-1.4\n1 0 obj<</Type/XObject/Subtype/Image/Length 8>>stream\n\x00\x01\x02\x03\x04\x05\x06\x07\n"
          b"endstream endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")

    # -- the ten pulse Plays -------------------------------------------------------------------
    write(FIX / "busfactor" / "repos.json", build_busfactor())
    write(FIX / "nightshift" / "commits.json", compact(build_nightshift()))
    write(FIX / "kept" / "kept.json", compact(build_kept()))
    write(FIX / "extensions" / "installs.json", build_extensions())
    write(FIX / "history" / "browser-history.json", compact(build_history()))
    write(FIX / "photos" / "assets.json", compact(build_photos()))
    write(FIX / "grew" / "sizes.json", build_grew())
    write(FIX / "grew" / "sizes-previous.json", build_grew_previous())
    write(FIX / "standingcost" / "calendar.json", compact(build_standingcost()))
    write(FIX / "replydebt" / "mailbox.json", compact(build_replydebt()))
    tree_rng = random.Random(8802)
    tree, versions = build_upstream_tree(tree_rng)
    for name in sorted(tree):
        write(FIX / "upstream" / name, tree[name])
    write(FIX / "upstream" / "registry.json", build_upstream_registry(versions, tree_rng))
    return 0


if __name__ == "__main__":
    sys.exit(main())
