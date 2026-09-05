"""What each Play concludes from the bundled fixtures, pinned to exact numbers.

The fixtures were built to contain the cases that matter: a tab open in two browsers, a contact
with no birthday and one with no year, an Intel-only application, an orphan note and a broken
link, two files that are byte-identical, and a document full of money that charged nobody. Every
one of those has an assertion here, so a refactor that quietly stops finding one fails the build.
"""
import json
import unittest
from datetime import datetime, timezone

from daily_core.common import Budget, fixtures_dir
from daily_core.scan import apps, clutter, contacts, notes, receipts, tabs

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def read_all(family_reader, families, root):
    sources, items = [], []
    for family in families:
        s, i = family_reader(family, root)
        sources += s
        items += i
    return sources, items


class TestTabDebt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = fixtures_dir() / "tabs"
        sources, found = read_all(lambda f, r: tabs.read_source(f, Budget(), r),
                                  tabs.FAMILIES, root)
        _, items = tabs.reading_list(root)
        cls.view = tabs.analyse(found, items, NOW, keep_path=False)

    def test_every_browser_family_contributed(self):
        self.assertEqual(len(self.view["browsers"]), 4)
        self.assertEqual(self.view["total"], 18)

    def test_a_page_open_in_two_browsers_is_one_duplicate(self):
        across = [d for d in self.view["duplicates"] if len(d["browsers"]) > 1]
        self.assertTrue(across, "the fixture opens Gmail in Chrome and in Arc")
        self.assertEqual(self.view["duplicate_tabs"], 3)

    def test_the_oldest_tab_is_dated_not_guessed(self):
        self.assertEqual(self.view["oldest"]["last_used"], "2026-02-03")
        self.assertGreater(self.view["oldest"]["age_days"], 200)

    def test_a_query_string_never_reaches_the_output(self):
        blob = json.dumps(self.view)
        self.assertNotIn("?id=", blob)
        self.assertNotIn("watch?v=", blob)

    def test_the_reading_list_backlog_is_counted(self):
        self.assertEqual(self.view["reading_list"], {"total": 3, "unread": 2, "oldest": "2025-07-26"})

    def test_keeping_paths_keeps_the_path_and_still_drops_the_query(self):
        root = fixtures_dir() / "tabs"
        _, found = read_all(lambda f, r: tabs.read_source(f, Budget(), r), tabs.FAMILIES, root)
        view = tabs.analyse(found, [], NOW, keep_path=True)
        blob = json.dumps(view)
        self.assertIn("/mail/u/0/", blob)
        self.assertNotIn("?v=demo1", blob)


class TestBirthdayRadar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources, people = contacts.read_source("vcard", Budget(), {"demo_root": fixtures_dir() / "contacts"})
        cls.view = contacts.analyse(people, NOW, horizon=45, redact=True)

    def test_the_book_is_counted_including_what_it_lacks(self):
        self.assertEqual(self.view["people"], 7)
        self.assertEqual(self.view["with_birthday"], 5)
        self.assertEqual(self.view["missing"], 2)

    def test_a_birthday_without_a_year_reports_no_age(self):
        self.assertEqual(self.view["no_year"], 1)
        no_age = [u for u in self.view["upcoming"] if u["turning"] is None]
        self.assertTrue(no_age)

    def test_the_next_birthday_is_the_soonest_one(self):
        self.assertEqual(self.view["next"]["in_days"], 1)
        self.assertEqual(self.view["next"]["turning"], 41)

    def test_the_same_person_entered_twice_is_found(self):
        self.assertEqual(self.view["duplicate_total"], 1)
        self.assertEqual(self.view["duplicates"][0]["copies"], 2)

    def test_names_are_reduced_to_initials_and_no_contact_detail_is_printed(self):
        blob = json.dumps(self.view)
        self.assertNotIn("Lovelace", blob)
        self.assertNotIn("@example.com", blob)
        self.assertIn("A. L.", blob)

    def test_redact_false_prints_the_name(self):
        _, people = contacts.read_source("vcard", Budget(), {"demo_root": fixtures_dir() / "contacts"})
        view = contacts.analyse(people, NOW, horizon=45, redact=False)
        self.assertIn("Ada Lovelace", json.dumps(view))

    def test_a_february_29_birthday_lands_on_the_28th_in_a_common_year(self):
        from datetime import date
        self.assertEqual(contacts._next_occurrence(date(2026, 1, 1), 2, 29), date(2026, 2, 28))
        self.assertEqual(contacts._next_occurrence(date(2028, 1, 1), 2, 29), date(2028, 2, 29))


class TestAppGraveyard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, found = apps.read_source("applications", Budget(), {"demo_root": fixtures_dir() / "apps"})
        _, casks = apps.read_source("casks", Budget(), {"demo_root": fixtures_dir() / "apps"})
        cls.view = apps.analyse(found, casks, NOW, unused_days=180)

    def test_unused_and_never_opened_are_separate_answers(self):
        self.assertEqual(self.view["apps"], 8)
        self.assertEqual(self.view["unused"], 4)
        self.assertEqual(self.view["never_used"], 1)

    def test_reclaimable_counts_both(self):
        self.assertGreater(self.view["reclaimable"], 1_500_000_000)

    def test_intel_only_bundles_are_named(self):
        self.assertEqual(self.view["intel_only_total"], 3)
        self.assertNotIn("arm64", sum((a["architectures"] for a in self.view["intel_only"]), []))

    def test_a_cask_with_no_matching_application_is_flagged(self):
        self.assertIn("old-editor", self.view["orphan_casks"])
        self.assertEqual(self.view["cask_versions"], 2)

    def test_every_date_says_where_it_came_from(self):
        self.assertEqual(self.view["spotlight"] + self.view["guessed"], 7)
        for row in self.view["graveyard"]:
            self.assertIn(row["how"], ("spotlight", "file access time", ""))


class TestVaultPulse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, docs = notes.read_source("vault", Budget(), {"demo_root": fixtures_dir() / "notes"})
        cls.view = notes.analyse(docs[0], NOW, stale_days=180)

    def test_the_vault_is_counted(self):
        self.assertEqual(self.view["notes"], 10)
        self.assertGreater(self.view["words"], 200)

    def test_an_orphan_is_a_note_with_no_link_in_or_out(self):
        paths = [o["path"] for o in self.view["orphan_list"]]
        self.assertIn("orphan-thoughts.md", paths)
        self.assertIn("projects/abandoned.md", paths)

    def test_a_link_to_a_note_that_does_not_exist_is_reported(self):
        self.assertEqual(self.view["broken"], 1)
        self.assertEqual(self.view["broken_list"][0]["to"], "missing-note")

    def test_the_most_linked_note_is_the_hub(self):
        self.assertEqual(self.view["hubs"][0]["path"], "projects/comped.md")

    def test_the_daily_streak_is_measured_from_the_file_names(self):
        self.assertEqual(self.view["daily"]["notes"], 3)
        self.assertEqual(self.view["daily"]["longest"], 3)
        self.assertEqual(self.view["daily"]["last"], "2026-09-01")

    def test_open_checkboxes_are_counted_separately_from_closed_ones(self):
        self.assertEqual(self.view["todo"], 5)
        self.assertEqual(self.view["done"], 1)

    def test_one_creation_time_across_the_vault_is_declared_unmeasurable(self):
        self.assertTrue(self.view["clone_like"], "a checkout stamps every file at once")


class TestDesktopClutter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources, files = read_all(
            lambda k, r: clutter.read_source(k, Budget(), {"demo_root": r}), clutter.KINDS,
            fixtures_dir() / "clutter")
        cls.view = clutter.analyse(files, NOW, cold_days=90, hash_dupes=False, roots={})

    def test_both_folders_are_counted_once(self):
        self.assertEqual(self.view["files"], 18)
        self.assertEqual([r["files"] for r in self.view["per_root"]], [10, 8])

    def test_screenshots_are_recognised_by_name(self):
        self.assertEqual(self.view["screenshots"], 4)

    def test_the_oldest_file_carries_its_date(self):
        self.assertEqual(self.view["oldest"]["name"], "resume.pdf")

    def test_without_hashing_the_claim_is_weaker_and_says_so(self):
        self.assertTrue(self.view["duplicates"])
        self.assertIn("not compared", self.view["duplicates"][0]["proof"])

    def test_the_grade_is_the_same_formula_every_time(self):
        self.assertEqual(self.view["score"]["grade"], "C")
        self.assertEqual(clutter._score(0, 0, 0, 0)["grade"], "A")
        self.assertEqual(clutter._score(1000, 1000, 50, 0)["grade"], "F")


class TestReceiptLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, docs = receipts.read_source("files", Budget(), {"demo_root": fixtures_dir() / "receipts"})
        cls.docs = docs
        cls.view = receipts.analyse(docs, NOW, months_back=12)

    def test_five_of_the_seven_files_are_receipts(self):
        self.assertEqual(self.view["documents"], 5)
        self.assertEqual(self.view["priced"], 5)

    def test_a_pitch_deck_full_of_money_is_not_a_receipt(self):
        self.assertNotIn("Acme Robotics", json.dumps(self.view))
        self.assertTrue(all(d["amount"] < 1000 for d in self.docs))

    def test_currencies_are_totalled_separately_and_never_summed(self):
        totals = {c["currency"]: c["total"] for c in self.view["currencies"]}
        self.assertEqual(totals, {"USD": 113.17, "GBP": 27.95, "EUR": 11.99})

    def test_the_vendor_comes_from_the_strongest_evidence_available(self):
        by_vendor = {v["vendor"]: v for v in self.view["vendors"]}
        self.assertIn("Netflix", by_vendor)
        self.assertIn("Acme Hosting Ltd", by_vendor)

    def test_every_amount_here_came_from_a_total_line(self):
        self.assertEqual(self.view["guessed_amounts"], 0)
        self.assertEqual(self.view["guessed_dates"], 0)

    def test_a_scanned_pdf_is_unreadable_rather_than_counted(self):
        self.assertNotIn("scanned-receipt.pdf", json.dumps(self.view))

    def test_a_negated_phrase_is_not_evidence(self):
        self.assertEqual(receipts.receipt_evidence("There is no invoice number here.", "none"), [])
        self.assertEqual(receipts.receipt_evidence("Invoice number: 1\nSubtotal 2", "none"),
                         ["invoice number", "subtotal"])

    def test_one_incidental_phrase_is_not_enough(self):
        self.assertEqual(receipts.receipt_evidence("Our order number system is great.", "none"), [])

    def test_a_total_line_alone_is_enough(self):
        self.assertIn("a total line with an amount", receipts.receipt_evidence("x", "total line"))

    def test_a_refund_is_subtracted_rather_than_added(self):
        docs = [{"amount": 10.0, "currency": "USD", "date": "2026-09-01T00:00:00Z", "refund": False,
                 "subscription": False, "vendor": "A", "confidence": "total line",
                 "date_from": "text", "file": "a", "ext": ".eml"},
                {"amount": 4.0, "currency": "USD", "date": "2026-09-01T00:00:00Z", "refund": True,
                 "subscription": False, "vendor": "A", "confidence": "total line",
                 "date_from": "text", "file": "b", "ext": ".eml"}]
        view = receipts.analyse(docs, NOW, months_back=12)
        self.assertEqual(view["currencies"][0]["total"], 6.0)
        self.assertEqual(view["refunds"], 1)


class TestAmountReading(unittest.TestCase):
    def test_a_total_line_beats_a_bigger_number_elsewhere(self):
        amount, currency, _, how = receipts.find_amount(
            "Market cap $9,000,000\nSubtotal $10.00\nGrand total: $12.50")
        self.assertEqual((amount, currency, how), (12.5, "USD", "total line"))

    def test_the_currency_can_follow_the_number(self):
        self.assertEqual(receipts.find_amount("Amount due 1,299.00 INR")[1], "INR")

    def test_a_line_broken_by_glyph_placement_still_matches(self):
        self.assertEqual(receipts.find_amount("Am ount due  $20.00")[3], "total line")

    def test_no_money_at_all(self):
        self.assertEqual(receipts.find_amount("nothing numeric here"), (None, "", "", "none"))


if __name__ == "__main__":
    unittest.main()
