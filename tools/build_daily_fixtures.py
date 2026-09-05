#!/usr/bin/env python3
"""Generate the bundled demo fixtures for the six daily Plays.

Every fixture is produced here rather than copied from a machine, for three reasons: nothing
personal can leak into a published Play, the binary formats (SNSS, property lists, PDF) are
exercised by the same readers a real run uses, and re-running this script reproduces the files
byte for byte, so drift is a diff rather than a mystery.
"""
import json
import pathlib
import plistlib
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
