"""The format readers, tested on bytes this file builds and on the bundled fixtures.

A reader that guesses is worse than one that refuses, so every test here has a negative half: the
malformed, the truncated and the unsupported must raise rather than return something plausible.
"""
import json
import plistlib
import struct
import unittest
import zlib

from daily_core.parsers import applesafari, arcsidebar, machoarch, mozlz4, pdftext, snss, vcard
from daily_core.common import fixtures_dir


class TestSNSS(unittest.TestCase):
    def session(self):
        return snss.read_session((fixtures_dir() / "tabs" / "chrome-session.snss").read_bytes())

    def test_replays_the_bundled_session(self):
        r = self.session()
        self.assertEqual(len(r["tabs"]), 10)
        self.assertEqual(r["windows"], 1)

    def test_a_closed_tab_is_not_in_the_tab_set(self):
        urls = [t["url"] for t in self.session()["tabs"]]
        self.assertNotIn("https://example.invalid/closed", urls)
        self.assertEqual(self.session()["closed"], 1)

    def test_the_selected_navigation_wins_over_the_first_one(self):
        urls = [t["url"] for t in self.session()["tabs"]]
        self.assertNotIn("https://example.invalid/start", urls)
        self.assertIn("https://mail.google.com/mail/u/0/#inbox", urls)

    def test_every_tab_carries_a_navigation_timestamp(self):
        self.assertTrue(all(t["navigated_at"] for t in self.session()["tabs"]))

    def test_pinned_state_is_read(self):
        self.assertEqual(sum(1 for t in self.session()["tabs"] if t["pinned"]), 1)

    def test_a_non_snss_file_is_refused(self):
        with self.assertRaises(snss.Unreadable):
            snss.read_session(b"not a session file at all")

    def test_an_encrypted_session_is_named_as_such(self):
        with self.assertRaises(snss.Unreadable) as caught:
            snss.read_session(b"SNSS" + struct.pack("<i", 2))
        self.assertIn("encrypted", str(caught.exception))

    def test_a_truncated_trailing_command_stops_the_replay_without_raising(self):
        data = bytearray((fixtures_dir() / "tabs" / "chrome-session.snss").read_bytes())
        data += struct.pack("<H", 400) + b"\x06partial"
        self.assertEqual(len(snss.read_session(bytes(data))["tabs"]), 10)

    def test_a_command_with_a_corrupt_payload_costs_only_that_command(self):
        good = snss.read_session((fixtures_dir() / "tabs" / "chrome-session.snss").read_bytes())
        body = bytes([snss.CMD_UPDATE_TAB_NAVIGATION]) + struct.pack("<I", 4000) + b"\xff" * 8
        data = bytearray((fixtures_dir() / "tabs" / "chrome-session.snss").read_bytes())
        data += struct.pack("<H", len(body)) + body
        self.assertEqual(len(snss.read_session(bytes(data))["tabs"]), len(good["tabs"]))


class TestLZ4(unittest.TestCase):
    def test_literals_and_an_overlapping_match(self):
        block = bytes([0x54]) + b"hello" + struct.pack("<H", 5)
        self.assertEqual(mozlz4.lz4_block_decompress(block, 13), b"hellohellohel")

    def test_a_declared_length_that_does_not_match_is_refused(self):
        block = bytes([0x54]) + b"hello" + struct.pack("<H", 5)
        with self.assertRaises(mozlz4.Unreadable):
            mozlz4.lz4_block_decompress(block, 12)

    def test_an_offset_pointing_outside_the_output_is_refused(self):
        with self.assertRaises(mozlz4.Unreadable):
            mozlz4.lz4_block_decompress(bytes([0x14]) + b"h" + struct.pack("<H", 99), 9)

    def test_a_container_round_trip(self):
        payload = json.dumps({"windows": [{"tabs": []}]}).encode()
        # A stored-literal LZ4 block: one token per 255 literals, then the bytes themselves.
        block = bytearray()
        rest = len(payload)
        block.append(0xF0)
        rest -= 15
        while rest >= 255:
            block.append(255)
            rest -= 255
        block.append(rest)
        block += payload
        data = mozlz4.MAGIC + struct.pack("<I", len(payload)) + bytes(block)
        self.assertEqual(mozlz4.read_json(data), {"windows": [{"tabs": []}]})

    def test_a_non_mozlz4_file_is_refused(self):
        with self.assertRaises(mozlz4.Unreadable):
            mozlz4.read_json(b"{}")

    def test_the_bundled_firefox_session_flattens_to_tabs(self):
        r = mozlz4.read_session((fixtures_dir() / "tabs" / "firefox-sessionstore.json").read_bytes())
        self.assertEqual(len(r["tabs"]), 3)
        self.assertTrue(all(t["url"].startswith("http") for t in r["tabs"]))


class TestApplePlists(unittest.TestCase):
    def test_the_bundled_safari_session(self):
        r = applesafari.read_session((fixtures_dir() / "tabs" / "safari-lastsession.plist").read_bytes())
        self.assertEqual(len(r["tabs"]), 2)
        self.assertEqual(r["tabs"][0]["history_depth"], None)

    def test_the_reading_list_marks_what_was_never_opened(self):
        items = applesafari.read_reading_list(
            (fixtures_dir() / "tabs" / "safari-bookmarks.plist").read_bytes())
        self.assertEqual(len(items), 3)
        self.assertEqual(sum(1 for i in items if i["unread"]), 2)

    def test_a_non_plist_is_refused(self):
        with self.assertRaises(applesafari.Unreadable):
            applesafari.read_session(b"<<<not a plist")

    def test_a_plist_that_is_not_a_session_is_refused(self):
        with self.assertRaises(applesafari.Unreadable):
            applesafari.read_session(plistlib.dumps([1, 2, 3]))


class TestArc(unittest.TestCase):
    def test_the_bundled_sidebar(self):
        r = arcsidebar.read_session((fixtures_dir() / "tabs" / "arc-sidebar.json").read_bytes())
        self.assertEqual(len(r["tabs"]), 3)

    def test_a_store_without_a_sidebar_is_refused(self):
        with self.assertRaises(arcsidebar.Unreadable):
            arcsidebar.read_session(b'{"something": 1}')


class TestVCard(unittest.TestCase):
    def cards(self):
        return vcard.parse((fixtures_dir() / "contacts" / "contacts.vcf").read_text(encoding="utf-8"))

    def test_the_bundled_book(self):
        cards = self.cards()
        self.assertEqual(len(cards), 7)
        self.assertEqual(cards[0]["name"], "Ada Lovelace")

    def test_folded_lines_are_rejoined_without_the_fold_character(self):
        # RFC 2426 folding inserts CRLF plus one whitespace, and unfolding removes both. The space
        # is the fold marker, not part of the value, so a name folded mid-word rejoins unbroken.
        self.assertEqual(vcard.parse("BEGIN:VCARD\r\nFN:Ada\r\n Lovelace\r\nEND:VCARD\r\n")[0]["name"],
                         "AdaLovelace")
        self.assertEqual(vcard.parse("BEGIN:VCARD\r\nFN:Ada \r\n Lovelace\r\nEND:VCARD\r\n")[0]["name"],
                         "Ada Lovelace")

    def test_quoted_printable_values_are_decoded(self):
        cards = vcard.parse("BEGIN:VCARD\nFN;ENCODING=QUOTED-PRINTABLE:Ren=C3=A9\nEND:VCARD\n")
        self.assertEqual(cards[0]["name"], "René")

    def test_birthday_forms(self):
        self.assertEqual(vcard.parse_bday("1985-07-04"), (7, 4, 1985))
        self.assertEqual(vcard.parse_bday("19850704"), (7, 4, 1985))
        self.assertEqual(vcard.parse_bday("--07-04"), (7, 4, None))
        self.assertEqual(vcard.parse_bday("--0704"), (7, 4, None))
        self.assertEqual(vcard.parse_bday("1604-07-04"), (7, 4, None))

    def test_a_birthday_that_is_not_one(self):
        for bad in ("", "unknown", "2026-13-40", "next tuesday"):
            self.assertIsNone(vcard.parse_bday(bad), bad)


class TestMachO(unittest.TestCase):
    def test_a_thin_little_endian_arm64_image(self):
        head = struct.pack("<II", machoarch.MH_MAGIC_64, machoarch.CPU_ARM64)
        self.assertEqual(machoarch.architectures(head), ["arm64"])

    def test_a_thin_big_endian_image(self):
        head = struct.pack(">II", machoarch.MH_MAGIC_64, machoarch.CPU_X86_64)
        self.assertEqual(machoarch.architectures(head), ["x86_64"])

    def test_a_fat_binary_lists_every_slice(self):
        head = struct.pack(">III", machoarch.FAT_MAGIC, 2, machoarch.CPU_X86_64)
        head += b"\0" * 16 + struct.pack(">I", machoarch.CPU_ARM64) + b"\0" * 16
        self.assertEqual(machoarch.architectures(head), ["arm64", "x86_64"])

    def test_anything_else_is_not_a_mach_o(self):
        self.assertEqual(machoarch.architectures(b"#!/bin/sh\n"), [])
        self.assertEqual(machoarch.architectures(b""), [])


class TestPDF(unittest.TestCase):
    @staticmethod
    def build(content: bytes) -> bytes:
        comp = zlib.compress(content)
        return (b"%PDF-1.4\n1 0 obj<</Length " + str(len(comp)).encode()
                + b"/Filter/FlateDecode>>stream\n" + comp + b"\nendstream endobj\n%%EOF")

    def test_a_literal_string_and_a_kerned_array(self):
        text = pdftext.extract_text(self.build(
            b"BT /F1 12 Tf 40 700 Td (Total) Tj [(Amount) -400 (due)] TJ ET"))
        self.assertIn("Total", text)
        self.assertIn("Amount due", text)

    def test_a_new_line_starts_when_the_pen_moves_down(self):
        text = pdftext.extract_text(self.build(
            b"BT /F1 12 Tf 40 700 Td (first) Tj 40 680 Td (second) Tj ET"))
        self.assertEqual([l for l in text.splitlines() if l], ["first", "second"])

    def test_a_scan_has_no_text_and_says_so(self):
        with self.assertRaises(pdftext.Unreadable):
            pdftext.extract_text(b"%PDF-1.4\n1 0 obj<</Length 3>>stream\n\x00\x01\x02\nendstream\n%%EOF")

    def test_something_that_is_not_a_pdf(self):
        with self.assertRaises(pdftext.Unreadable):
            pdftext.extract_text(b"PK\x03\x04")

    def test_glyph_codes_without_a_cmap_are_refused_rather_than_reported(self):
        # Hex strings that decode to control bytes are a font's own glyph indices, not characters.
        with self.assertRaises(pdftext.Unreadable) as caught:
            pdftext.extract_text(self.build(b"BT /F1 12 Tf 40 700 Td <00030004000500060007> Tj ET"))
        self.assertIn("custom encoding", str(caught.exception))

    def test_a_tounicode_cmap_turns_glyph_codes_back_into_text(self):
        cmap = (b"/CIDInit /ProcSet findresource begin\n1 beginbfchar\n<0003> <0054>\nendbfchar\n"
                b"1 beginbfrange\n<0004> <0007> <006F>\nendbfrange\nend")
        comp_cmap = zlib.compress(cmap)
        content = zlib.compress(b"BT /F1 12 Tf 40 700 Td <00030004000500060007> Tj ET")
        pdf = (b"%PDF-1.4\n"
               b"1 0 obj<</Type/Page/Resources<</Font<</F1 2 0 R>>>>>>endobj\n"
               b"2 0 obj<</Type/Font/ToUnicode 3 0 R>>endobj\n"
               b"3 0 obj<</Length " + str(len(comp_cmap)).encode() + b"/Filter/FlateDecode>>stream\n"
               + comp_cmap + b"\nendstream endobj\n"
               b"4 0 obj<</Length " + str(len(content)).encode() + b"/Filter/FlateDecode>>stream\n"
               + content + b"\nendstream endobj\n%%EOF")
        self.assertEqual(pdftext.extract_text(pdf).strip(), "Topqr")

    def test_the_bundled_invoice_reads(self):
        text = pdftext.extract_text((fixtures_dir() / "receipts" / "hosting-invoice.pdf").read_bytes())
        self.assertIn("Amount due", text)
        self.assertIn("72.00", text)

    def test_the_bundled_scan_does_not(self):
        with self.assertRaises(pdftext.Unreadable):
            pdftext.extract_text((fixtures_dir() / "receipts" / "scanned-receipt.pdf").read_bytes())


if __name__ == "__main__":
    unittest.main()
