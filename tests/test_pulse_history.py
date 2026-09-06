"""where-it-went, against real databases in the real three shapes.

Every claim this Play makes on its card is a claim about somebody's browsing history, so the tests
build actual SQLite files in the Chromium, Firefox and Safari shapes, with timestamps in each
vendor's own epoch, and read them through the same code path a real profile would take. The three
things that would quietly ruin the answer — an epoch off by four centuries, a subdomain counted as
its own site, a sitting split by a gap that was never there — are asserted directly, and so is the
promise that nothing but history rows is ever touched.
"""
import ast
import json
import pathlib
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daily_core.common import Budget
from daily_core.scan import history

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
UTC_CFG = {"days": 30, "tz": "utc", "gap_minutes": 30, "top": 10}

MODULE = pathlib.Path("daily_core/scan/history.py")
EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)
EPOCH_2001 = datetime(2001, 1, 1, tzinfo=timezone.utc)
EPOCH_1970 = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------- fixtures

def _chrome_us(d) -> int:
    return int((d - EPOCH_1601).total_seconds() * 1000000)


def _firefox_us(d) -> int:
    return int((d - EPOCH_1970).total_seconds() * 1000000)


def _apple_seconds(d) -> float:
    return float((d - EPOCH_2001).total_seconds())


def chromium_db(path, rows):
    """The two tables Chrome actually keeps, with the columns this reader names and nothing else."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url LONGVARCHAR, "
                "title LONGVARCHAR, visit_count INTEGER DEFAULT 0)")
    con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER NOT NULL, "
                "visit_time INTEGER NOT NULL, transition INTEGER DEFAULT 0)")
    for i, row in enumerate(rows, start=1):
        url, title, when, transition = row
        con.execute("INSERT INTO urls VALUES (?,?,?,1)", (i, url, title))
        con.execute("INSERT INTO visits VALUES (?,?,?,?)", (i, i, _chrome_us(when), transition))
    con.commit()
    con.close()
    return path


def firefox_db(path, rows):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url LONGVARCHAR, "
                "title LONGVARCHAR, visit_count INTEGER DEFAULT 0)")
    con.execute("CREATE TABLE moz_historyvisits (id INTEGER PRIMARY KEY, place_id INTEGER, "
                "visit_date INTEGER, visit_type INTEGER)")
    for i, row in enumerate(rows, start=1):
        url, title, when, kind = row
        con.execute("INSERT INTO moz_places VALUES (?,?,?,1)", (i, url, title))
        con.execute("INSERT INTO moz_historyvisits VALUES (?,?,?,?)", (i, i, _firefox_us(when), kind))
    con.commit()
    con.close()
    return path


def safari_db(path, rows):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE history_items (id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER)")
    con.execute("CREATE TABLE history_visits (id INTEGER PRIMARY KEY, history_item INTEGER, "
                "visit_time REAL, title TEXT)")
    for i, row in enumerate(rows, start=1):
        url, title, when = row
        con.execute("INSERT INTO history_items VALUES (?,?,1)", (i, url))
        con.execute("INSERT INTO history_visits VALUES (?,?,?,?)", (i, i, _apple_seconds(when), title))
    con.commit()
    con.close()
    return path


def record(url, minutes_ago, transition="linked", known=True, browser="Chrome", title=""):
    """A record in the shape read_source emits, so analyse can be tested without a database."""
    return {"url": url, "title": title, "browser": browser, "family": "chromium",
            "when": (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "transition": transition, "transition_known": known}


# ---------------------------------------------------------------- reading

class TestEpochsPerBrowser(unittest.TestCase):
    """Each vendor counts from a different year. Getting one wrong moves a visit by centuries."""

    def _read(self, family, patch, path):
        budget = Budget()
        cfg = {"days": 30, "now": NOW}
        original = getattr(history, patch)
        try:
            if patch == "SAFARI_DB":
                history.SAFARI_DB = str(path)
            else:
                setattr(history, patch, lambda: iter([("Test", Path(path))]))
            return history.read_source(family, budget, cfg)
        finally:
            setattr(history, patch, original)

    def test_chromium_microseconds_since_1601_land_on_the_right_minute(self):
        when = NOW - timedelta(days=3, hours=2)
        with tempfile.TemporaryDirectory() as tmp:
            db = chromium_db(Path(tmp) / "History", [("https://github.com/a", "A", when, 1)])
            sources, records = self._read("chromium", "_profiles_chromium", db)
        self.assertTrue(sources[0].found)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["when"], when.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(records[0]["transition"], "typed")
        self.assertTrue(records[0]["transition_known"])

    def test_chromium_transition_is_read_from_the_low_byte_not_the_whole_word(self):
        when = NOW - timedelta(days=1)
        with tempfile.TemporaryDirectory() as tmp:
            # 0x18000000 | 0 is a plain link with two qualifier bits set, as Chrome really stores it.
            db = chromium_db(Path(tmp) / "History", [("https://example.com/x", "X", when, 0x18000000)])
            _, records = self._read("chromium", "_profiles_chromium", db)
        self.assertEqual(records[0]["transition"], "linked")

    def test_firefox_microseconds_since_1970_land_on_the_right_minute(self):
        when = NOW - timedelta(days=5, minutes=17)
        with tempfile.TemporaryDirectory() as tmp:
            db = firefox_db(Path(tmp) / "places.sqlite", [("https://mozilla.org/d", "D", when, 2)])
            sources, records = self._read("firefox", "_profiles_firefox", db)
        self.assertTrue(sources[0].found)
        self.assertEqual(records[0]["when"], when.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(records[0]["transition"], "typed")

    def test_safari_seconds_since_2001_land_on_the_right_minute_and_carry_no_transition(self):
        when = NOW - timedelta(days=2)
        with tempfile.TemporaryDirectory() as tmp:
            db = safari_db(Path(tmp) / "History.db", [("https://apple.com/s", "S", when)])
            sources, records = self._read("safari", "SAFARI_DB", db)
        self.assertTrue(sources[0].found)
        self.assertEqual(records[0]["when"], when.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(records[0]["transition"], "unknown")
        self.assertFalse(records[0]["transition_known"],
                         "Safari records no transition; claiming one would be an invention")

    def test_a_visit_older_than_the_two_windows_is_not_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = chromium_db(Path(tmp) / "History", [
                ("https://github.com/new", "n", NOW - timedelta(days=3), 0),
                ("https://github.com/old", "o", NOW - timedelta(days=400), 0)])
            _, records = self._read("chromium", "_profiles_chromium", db)
        self.assertEqual([r["url"] for r in records], ["https://github.com/new"])


class TestUnreadableProfilesDegrade(unittest.TestCase):
    """An absent, corrupt or forbidden profile costs that browser a row, never the run."""

    def _chromium(self, path):
        budget, original = Budget(), history._profiles_chromium
        try:
            history._profiles_chromium = lambda: iter([("Chrome", Path(path))])
            return history.read_source("chromium", budget, {"days": 30, "now": NOW})
        finally:
            history._profiles_chromium = original

    def test_an_absent_database_is_a_labelled_miss_not_an_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = self._chromium(Path(tmp) / "History")
        self.assertEqual(records, [])
        self.assertFalse(sources[0].found)
        self.assertTrue(sources[0].note)

    def test_a_file_that_is_not_a_database_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "History"
            p.write_bytes(b"this is not a sqlite file, it is a note someone left")
            sources, records = self._chromium(p)
        self.assertEqual(records, [])
        self.assertFalse(sources[0].found)
        self.assertIn("shape this reader does not know", sources[0].note)

    def test_a_browser_that_is_not_installed_is_a_miss_while_the_others_still_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = firefox_db(Path(tmp) / "places.sqlite",
                              [("https://github.com/a", "A", NOW - timedelta(days=1), 1)])
            original = history._profiles_firefox
            try:
                history._profiles_firefox = lambda: iter([("Firefox", good)])
                fsources, frecords = history.read_source("firefox", Budget(), {"days": 30, "now": NOW})
            finally:
                history._profiles_firefox = original
            csources, crecords = self._chromium(Path(tmp) / "Nothing")
        self.assertTrue(fsources[0].found)
        self.assertEqual(len(frecords), 1)
        self.assertFalse(csources[0].found)

    def test_no_profile_at_all_is_one_honest_row_rather_than_silence(self):
        original = history._profiles_chromium
        try:
            history._profiles_chromium = lambda: iter([])
            sources, records = history.read_source("chromium", Budget(), {"days": 30, "now": NOW})
        finally:
            history._profiles_chromium = original
        self.assertEqual(len(sources), 1)
        self.assertFalse(sources[0].found)
        self.assertIn("no profile", sources[0].note)

    def test_reading_leaves_the_original_database_untouched_and_unjournalled(self):
        """The reason a copy is taken: a live browser must not be locked, journalled or upgraded."""
        with tempfile.TemporaryDirectory() as tmp:
            db = chromium_db(Path(tmp) / "History",
                             [("https://github.com/a", "A", NOW - timedelta(days=1), 0)])
            before = db.read_bytes()
            self._chromium(db)
            self.assertEqual(db.read_bytes(), before, "the history file changed byte for byte")
            leftovers = sorted(p.name for p in Path(tmp).iterdir())
            self.assertEqual(leftovers, ["History"], "a sidecar journal was left behind")


class TestDemoFixture(unittest.TestCase):
    def _write(self, root, visits):
        (root / "browser-history.json").write_text(json.dumps({"visits": visits}), encoding="utf-8")

    def test_the_demo_loader_reads_a_json_fixture_and_filters_by_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, [
                {"family": "chromium", "url": "https://github.com/a", "title": "A",
                 "when": (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "transition": "typed"},
                {"family": "firefox", "url": "https://mozilla.org/b", "title": "B",
                 "when": (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "transition": "linked"}])
            cfg = {"days": 30, "now": NOW, "demo_root": str(root)}
            csources, crecords = history.read_source("chromium", Budget(), cfg)
            fsources, frecords = history.read_source("firefox", Budget(), cfg)
            ssources, srecords = history.read_source("safari", Budget(), cfg)
        self.assertEqual([r["url"] for r in crecords], ["https://github.com/a"])
        self.assertEqual(crecords[0]["transition"], "typed")
        self.assertEqual([r["url"] for r in frecords], ["https://mozilla.org/b"])
        self.assertTrue(csources[0].found and fsources[0].found)
        self.assertEqual(srecords, [])
        self.assertFalse(ssources[0].found, "a family with no fixture rows says so")

    def test_a_missing_or_broken_fixture_is_a_miss_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = history.read_source("chromium", Budget(),
                                                   {"days": 30, "now": NOW, "demo_root": tmp})
            self.assertFalse(sources[0].found)
            (Path(tmp) / "browser-history.json").write_text("{not json", encoding="utf-8")
            sources, records = history.read_source("chromium", Budget(),
                                                   {"days": 30, "now": NOW, "demo_root": tmp})
        self.assertFalse(sources[0].found)
        self.assertEqual(records, [])


# ---------------------------------------------------------------- analysis

class TestDomainRollup(unittest.TestCase):
    def test_subdomains_roll_up_to_the_site_a_person_would_name(self):
        v = history.analyse([record("https://gist.github.com/x", 10),
                             record("https://github.com/y", 20),
                             record("https://raw.githubusercontent.com/z", 30)], NOW, UTC_CFG)
        by_domain = {d["domain"]: d["visits"] for d in v["domains"]}
        self.assertEqual(by_domain.get("github.com"), 2)
        self.assertEqual(by_domain.get("githubusercontent.com"), 1,
                         "a different registrable domain must stay separate")
        self.assertEqual(v["unique_domains"], 2)

    def test_shares_are_a_share_of_the_visits_in_the_window(self):
        v = history.analyse([record("https://github.com/a", 5), record("https://github.com/b", 6),
                             record("https://news.ycombinator.com/", 7)], NOW, UTC_CFG)
        self.assertEqual(v["visits"], 3)
        top = v["domains"][0]
        self.assertEqual(top["domain"], "github.com")
        self.assertAlmostEqual(top["share"], 2 / 3.0)

    def test_the_previous_window_is_excluded_from_this_window_but_counted_as_the_comparison(self):
        cfg = dict(UTC_CFG, days=10)
        now_visits = [record("https://github.com/a", 60 * 24 * 2) for _ in range(3)]
        old_visits = [record("https://github.com/a", 60 * 24 * 15) for _ in range(5)]
        v = history.analyse(now_visits + old_visits, NOW, cfg)
        self.assertEqual(v["visits"], 3)
        self.assertEqual(v["previous_visits"], 5)
        self.assertEqual(v["trend"]["change"], -2)


class TestCategories(unittest.TestCase):
    def test_the_bundled_table_is_present_and_only_uses_the_declared_categories(self):
        doc = json.loads(pathlib.Path("daily_core/tables/domain-categories.json").read_text("utf-8"))
        self.assertIn("_source", doc)
        self.assertIn("_note", doc)
        for word in ("hand-curated", "not exhaustive", "uncategorised"):
            self.assertIn(word, (doc["_source"] + " " + doc["_note"]).lower(), word)
        self.assertGreaterEqual(len(doc["domains"]), 150)
        self.assertLessEqual(len(doc["domains"]), 260)
        self.assertEqual(set(doc["domains"].values()) - set(history.CATEGORIES), set())

    def test_every_row_is_a_registrable_domain_so_it_can_actually_match(self):
        """A subdomain row would be dead weight: the rollup never produces one to look up."""
        from daily_core.common import registrable
        table = history.categories_table()
        for domain in table:
            self.assertEqual(registrable(domain), domain,
                             "{0} can never be matched after the rollup".format(domain))

    def test_a_known_domain_gets_its_category_and_an_unknown_one_is_not_guessed_at(self):
        table = history.categories_table()
        self.assertEqual(history.categorise("github.com", table), "code")
        self.assertEqual(history.categorise("nytimes.com", table), "news")
        self.assertEqual(history.categorise("claude.ai", table), "ai")
        self.assertEqual(history.categorise("some-startup-nobody-listed.example", table),
                         "uncategorised")
        self.assertEqual(history.categorise("", table), "uncategorised")

    def test_a_machine_talking_to_itself_is_local_however_it_is_addressed(self):
        table = history.categories_table()
        for host in ("localhost", "127.0.0.1", "192.168.1.14", "myapp.test", "printer.local"):
            self.assertEqual(history.categorise(host, table), "local", host)

    def test_the_rollup_reports_uncategorised_with_its_own_denominator(self):
        v = history.analyse([record("https://github.com/a", 5),
                             record("https://nobody-listed-this.example/b", 6),
                             record("http://localhost:3000/", 7)], NOW, UTC_CFG)
        cats = {c["category"]: c["visits"] for c in v["categories"]}
        self.assertEqual(cats["code"], 1)
        self.assertEqual(cats["local"], 1)
        self.assertEqual(cats["uncategorised"], 1)
        self.assertEqual(v["uncategorised"]["visits"], 1)
        self.assertEqual(v["uncategorised"]["share"], 33)
        self.assertEqual(v["uncategorised"]["domains"], 1)
        self.assertEqual(sum(cats.values()), v["visits"], "categories must partition the visits")


class TestSessions(unittest.TestCase):
    def test_a_gap_longer_than_the_threshold_starts_a_new_sitting(self):
        cfg = dict(UTC_CFG, gap_minutes=30)
        # 0, 10, 20 minutes apart, then a 90-minute silence, then two more.
        offsets = [200, 190, 180, 90, 80]
        v = history.analyse([record("https://github.com/a", m) for m in offsets], NOW, cfg)
        self.assertEqual(v["sessions"]["count"], 2)

    def test_a_gap_exactly_on_the_threshold_is_still_the_same_sitting(self):
        cfg = dict(UTC_CFG, gap_minutes=30)
        v = history.analyse([record("https://github.com/a", 60), record("https://github.com/a", 30)],
                            NOW, cfg)
        self.assertEqual(v["sessions"]["count"], 1, "the boundary is inclusive, and says so")
        v2 = history.analyse([record("https://github.com/a", 61), record("https://github.com/a", 30)],
                             NOW, cfg)
        self.assertEqual(v2["sessions"]["count"], 2)

    def test_the_longest_single_domain_run_names_its_domain_weekday_and_time_of_day(self):
        cfg = dict(UTC_CFG, gap_minutes=30)
        # A four-hour stretch on one domain, interrupted once by a different site.
        start = NOW - timedelta(days=2)
        rows = []
        for i in range(17):                                   # 17 visits, 15 minutes apart = 4h00m
            rows.append(record("https://github.com/x",
                               int((NOW - (start + timedelta(minutes=15 * i))).total_seconds() // 60)))
        rows.append(record("https://nytimes.com/",
                           int((NOW - (start + timedelta(minutes=15 * 8))).total_seconds() // 60) - 1))
        v = history.analyse(rows, NOW, cfg)
        run = v["sessions"]["longest_domain_run"]
        self.assertIsNotNone(run)
        self.assertEqual(run["domain"], "github.com")
        self.assertIn(run["weekday"], ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                       "Saturday", "Sunday"))
        self.assertIn(run["when"].split()[-1], ("morning", "afternoon", "evening", "night"))
        self.assertRegex(run["length"], r"^\d+h\d\dm$|^\d+m$")

    def test_sittings_per_day_and_the_mean_are_reported_against_the_window(self):
        cfg = dict(UTC_CFG, days=10, gap_minutes=30)
        rows = []
        for d in range(5):
            base = 60 * 24 * (d + 1)
            rows += [record("https://github.com/a", base), record("https://github.com/a", base - 20)]
        v = history.analyse(rows, NOW, cfg)
        self.assertEqual(v["sessions"]["count"], 5)
        self.assertEqual(v["sessions"]["per_day"], 0.5)
        self.assertEqual(v["sessions"]["mean"], "20m")
        self.assertEqual(v["sessions"]["median_visits"], 2.0)

    def test_no_visits_yields_a_shaped_empty_answer_rather_than_a_crash(self):
        v = history.analyse([], NOW, UTC_CFG)
        self.assertEqual(v["visits"], 0)
        self.assertEqual(v["sessions"]["count"], 0)
        self.assertIsNone(v["sessions"]["longest"])
        self.assertIsNone(v["heatmap"]["peak"])
        self.assertIn("no history rows", v["verdict"])
        self.assertTrue(history.render(v, {}))


class TestRereadList(unittest.TestCase):
    def test_the_same_page_opened_many_times_is_the_top_row_with_its_count(self):
        rows = [record("https://stackoverflow.com/questions/1234/how", m) for m in range(31)]
        rows += [record("https://github.com/a", 100), record("https://github.com/a", 200)]
        rows += [record("https://github.com/only-once", 300)]
        v = history.analyse(rows, NOW, UTC_CFG)
        self.assertEqual(v["rereads"][0]["count"], 31)
        self.assertEqual(v["rereads"][0]["domain"], "stackoverflow.com")
        self.assertNotIn("only-once", json.dumps(v["rereads"]),
                         "a page opened once is not a re-read")

    def test_a_fragment_is_the_same_page(self):
        v = history.analyse([record("https://github.com/a#top", 5),
                             record("https://github.com/a#bottom", 6)], NOW, UTC_CFG)
        self.assertEqual(v["rereads"][0]["count"], 2)

    def test_the_list_is_capped_at_the_configured_top(self):
        rows = []
        for i in range(20):
            rows += [record("https://github.com/{0}".format(i), i * 2),
                     record("https://github.com/{0}".format(i), i * 2 + 1)]
        v = history.analyse(rows, NOW, dict(UTC_CFG, top=5))
        self.assertEqual(len(v["rereads"]), 5)


class TestHeatmap(unittest.TestCase):
    def test_the_grid_is_seven_days_by_twenty_four_hours(self):
        v = history.analyse([record("https://github.com/a", 5)], NOW, UTC_CFG)
        grid = v["heatmap"]["grid"]
        self.assertEqual(len(grid), 7)
        self.assertTrue(all(len(row) == 24 for row in grid))
        self.assertEqual(sum(sum(r) for r in grid), v["visits"])
        self.assertEqual(v["heatmap"]["rows"], ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])

    def test_a_visit_lands_in_its_own_weekday_and_hour_cell(self):
        # 2026-09-05T12:00Z is a Saturday; a visit two hours earlier is Saturday 10:00 UTC.
        v = history.analyse([record("https://github.com/a", 120)], NOW, UTC_CFG)
        self.assertEqual(v["heatmap"]["grid"][5][10], 1)
        self.assertEqual(v["heatmap"]["peak"]["weekday"], "Saturday")
        self.assertEqual(v["heatmap"]["peak"]["hour"], 10)

    def test_the_grid_feeds_the_shared_heatmap_renderer(self):
        from daily_core import card
        v = history.analyse([record("https://github.com/a", 120)], NOW, UTC_CFG)
        rows = card.heatmap(v["heatmap"]["grid"], v["heatmap"]["rows"], history._hour_labels())
        self.assertEqual(len(rows), 8, "seven day rows plus one label row")
        self.assertIn("█", "".join(rows))


class TestIntent(unittest.TestCase):
    def test_typed_and_linked_are_split_and_shares_use_the_judged_denominator(self):
        rows = ([record("https://github.com/a", 10, "typed")] * 3
                + [record("https://github.com/b", 11, "linked")] * 7)
        v = history.analyse(rows, NOW, UTC_CFG)
        self.assertEqual(v["intent"]["typed"], 3)
        self.assertEqual(v["intent"]["linked"], 7)
        self.assertEqual(v["intent"]["known"], 10)
        self.assertEqual(v["intent"]["typed_share"], 30)

    def test_a_browser_that_does_not_expose_the_column_is_named_not_guessed(self):
        rows = [record("https://github.com/a", 10, "typed"),
                record("https://apple.com/x", 11, "unknown", known=False, browser="Safari")]
        v = history.analyse(rows, NOW, UTC_CFG)
        self.assertEqual(v["intent"]["unknown"], 1)
        self.assertEqual(v["intent"]["known"], 1)
        self.assertEqual(v["intent"]["not_exposed"], ["Safari"])
        self.assertIn("Safari", v["intent"]["note"])
        self.assertEqual(v["visits"], 2, "an unjudged visit is still counted in the total")


class TestSearchesAndRedaction(unittest.TestCase):
    def test_a_search_term_is_extracted_from_the_users_own_search_url(self):
        self.assertEqual(history.search_term("https://duckduckgo.com/?q=sqlite+wal+mode"),
                         "sqlite wal mode")
        self.assertEqual(history.search_term("https://www.bing.com/search?q=a%20b&form=X"), "a b")
        self.assertEqual(history.search_term("https://uk.search.yahoo.com/search?p=trains"), "trains")
        self.assertEqual(history.search_term("https://github.com/search?query=rote+play"),
                         "rote play")

    def test_a_query_parameter_on_a_site_that_is_not_a_search_box_is_not_a_search(self):
        self.assertEqual(history.search_term("https://example.com/report?q=secret-document-id"), "")
        self.assertEqual(history.search_term("not a url at all"), "")

    def test_terms_are_redacted_by_default_and_never_reach_the_card(self):
        rows = [record("https://duckduckgo.com/?q=how+to+quit+vim", 5),
                record("https://duckduckgo.com/?q=how+to+quit+vim", 6)]
        v = history.analyse(rows, NOW, UTC_CFG)
        self.assertEqual(v["searches"]["total"], 2)
        self.assertEqual(v["searches"]["distinct"], 1)
        self.assertTrue(v["searches"]["redacted"])
        self.assertNotIn("quit vim", json.dumps(v["searches"]))
        self.assertEqual(v["searches"]["terms"][0]["words"], 4)
        card = history.render(v, {})
        self.assertNotIn("quit", card)
        self.assertNotIn("vim", card)

    def test_turning_redaction_off_shows_the_term_in_the_report_and_still_not_on_the_card(self):
        rows = [record("https://duckduckgo.com/?q=how+to+quit+vim", 5)]
        v = history.analyse(rows, NOW, dict(UTC_CFG, redact=False))
        self.assertEqual(v["searches"]["terms"][0]["term"], "how to quit vim")
        self.assertIn("how to quit vim", history.report_markdown(v, {}, []))
        self.assertNotIn("quit vim", history.render(v, {}))

    def test_no_query_string_ever_reaches_the_card_or_the_reread_display_url(self):
        rows = [record("https://example.com/doc?token=abcd1234&id=99", 5),
                record("https://example.com/doc?token=abcd1234&id=99", 6)]
        v = history.analyse(rows, NOW, UTC_CFG)
        self.assertNotIn("?", v["rereads"][0]["url"])
        self.assertNotIn("abcd1234", v["rereads"][0]["url"])
        for text in (history.render(v, {}), history.report_markdown(v, {}, [])):
            self.assertNotIn("abcd1234", text)

    def test_even_with_redaction_off_the_card_carries_no_query_string(self):
        rows = [record("https://example.com/doc?token=abcd1234", 5),
                record("https://example.com/doc?token=abcd1234", 6)]
        v = history.analyse(rows, NOW, dict(UTC_CFG, redact=False))
        self.assertIn("abcd1234", v["rereads"][0]["full"])
        self.assertNotIn("abcd1234", history.render(v, {}))

    def test_a_redacted_url_still_carries_a_stable_fingerprint_so_it_stays_countable(self):
        v1 = history.analyse([record("https://example.com/a?x=1", 5),
                              record("https://example.com/a?x=1", 6)], NOW, UTC_CFG)
        v2 = history.analyse([record("https://example.com/a?x=1", 5),
                              record("https://example.com/a?x=1", 6)], NOW, UTC_CFG)
        self.assertEqual(v1["rereads"][0]["fingerprint"], v2["rereads"][0]["fingerprint"])
        self.assertEqual(len(v1["rereads"][0]["fingerprint"]), 8)


# ---------------------------------------------------------------- promises

class TestPrivacyGuarantee(unittest.TestCase):
    """History rows only. The six words below are allowed in exactly one line of the module."""

    BANNED = ("cookie", "login", "password", "autofill", "form_data", "downloads")

    def test_the_banned_words_appear_only_in_the_one_declared_line(self):
        text = MODULE.read_text(encoding="utf-8")
        declaration = [l for l in text.splitlines() if l.startswith("NEVER_READ = (")]
        self.assertEqual(len(declaration), 1, "the allowed line must be exactly one and findable")
        rest = text.replace(declaration[0], "").lower()
        for word in self.BANNED:
            self.assertNotIn(word, rest,
                             "{0} appears outside the one prose declaration".format(word))

    def test_the_declared_line_really_is_the_privacy_sentence_and_names_them_all(self):
        for word in self.BANNED:
            self.assertIn(word, history.NEVER_READ, word)
            self.assertIn(word, history.PRIVACY_SENTENCE, word)

    def test_the_sentence_reaches_the_report_and_the_card(self):
        v = history.analyse([record("https://github.com/a", 5)], NOW, UTC_CFG)
        self.assertIn("History rows only", history.report_markdown(v, {}, []))
        self.assertIn("History rows only", history.render(v, {}))

    def test_every_sql_statement_selects_from_a_history_table_and_nothing_else(self):
        allowed = {"visits", "urls", "moz_historyvisits", "moz_places", "history_visits",
                   "history_items"}
        for sql in (history.SQL_CHROMIUM, history.SQL_FIREFOX, history.SQL_SAFARI):
            tables = set(re.findall(r"(?:FROM|JOIN)\s+(\w+)", sql))
            self.assertTrue(tables)
            self.assertEqual(tables - allowed, set(), sql)
            for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ATTACH", "PRAGMA", "CREATE"):
                self.assertNotIn(verb, sql.upper())

    def test_the_module_names_no_file_beside_the_history_database(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "/" in node.value and node.value.endswith((".db", ".sqlite", ".plist")):
                    self.assertIn("History", node.value, node.value)


class TestDeterminism(unittest.TestCase):
    ROWS = [record("https://github.com/a", 5, "typed"),
            record("https://gist.github.com/b", 40, "linked"),
            record("https://news.ycombinator.com/", 41, "linked"),
            record("https://duckduckgo.com/?q=x+y", 42, "typed"),
            record("http://localhost:3000/app", 900, "reload"),
            record("https://github.com/a", 901, "linked"),
            record("https://apple.com/z", 60 * 24 * 20, "unknown", known=False, browser="Safari")]

    def test_the_same_input_and_the_same_now_produce_an_identical_view(self):
        a = history.analyse(list(self.ROWS), NOW, UTC_CFG)
        b = history.analyse(list(reversed(self.ROWS)), NOW, UTC_CFG)
        self.assertEqual(json.dumps(a, sort_keys=True, default=str),
                         json.dumps(b, sort_keys=True, default=str))

    def test_the_card_and_the_report_are_identical_across_runs(self):
        a = history.analyse(list(self.ROWS), NOW, UTC_CFG)
        b = history.analyse(list(reversed(self.ROWS)), NOW, UTC_CFG)
        self.assertEqual(history.render(a, {}), history.render(b, {}))
        self.assertEqual(history.report_markdown(a, {}, []), history.report_markdown(b, {}, []))

    def test_the_card_stays_inside_sixty_four_columns(self):
        from daily_core.common import display_width
        v = history.analyse(list(self.ROWS), NOW, UTC_CFG)
        for line in history.render(v, {"color": False}).splitlines():
            self.assertEqual(display_width(line), 64, line)


class TestBaselineAndReport(unittest.TestCase):
    def test_a_first_run_says_so_and_a_second_reports_movement_per_category(self):
        rows = [record("https://github.com/a", 5), record("https://github.com/b", 6)]
        first = history.analyse(rows, NOW, UTC_CFG)
        self.assertTrue(first["delta"]["first_run"])
        self.assertIn("first run", first["since"])

        payload = history.baseline_payload(first)
        self.assertEqual(payload, {"code": 2})
        second = history.analyse(rows + [record("https://github.com/c", 7)], NOW,
                                 dict(UTC_CFG, baseline={"captured": "2026-09-01T00:00:00Z",
                                                         "payload": payload}))
        self.assertFalse(second["delta"]["first_run"])
        self.assertEqual(second["delta"]["grew"], {"code": 1})
        self.assertEqual(second["since"], "since 2026-09-01")

    def test_the_report_carries_every_number_with_its_denominator(self):
        v = history.analyse(list(TestDeterminism.ROWS), NOW, UTC_CFG)
        text = history.report_markdown(v, {}, [{"name": "Chrome", "found": True, "items": 6,
                                                "note": "urls + visits"}])
        for heading in ("## Where the visits went", "## By category", "## Sittings", "## When",
                        "## Intent versus drift", "## Your own searches", "## Movement",
                        "## Sources", "## What this read"):
            self.assertIn(heading, text)
        self.assertIn("share of", text)
        self.assertIn("of the {0:,} visits".format(v["visits"]), text)
        self.assertIn("copied to a temporary file and opened read-only", text)


if __name__ == "__main__":
    unittest.main()
