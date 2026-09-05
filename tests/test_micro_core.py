"""Unit tests for micro_core: the emit contract, scalars and formatting."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from micro_core import common, store


class TestEmit(unittest.TestCase):
    def test_json_is_the_last_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = common.emit("two lines\nof human text", {"ok": True, "n": 3})
        self.assertEqual(rc, 0)
        lines = buf.getvalue().rstrip("\n").split("\n")
        self.assertEqual(lines[:2], ["two lines", "of human text"])
        self.assertEqual(json.loads(lines[-1]), {"ok": True, "n": 3})

    def test_empty_human_still_emits_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            common.emit("", {"ok": True})
        self.assertEqual(json.loads(buf.getvalue().strip()), {"ok": True})


class TestScalars(unittest.TestCase):
    def test_as_bool(self):
        for s in ("true", "TRUE", "1", "yes", "on"):
            self.assertTrue(common.as_bool(s), s)
        for s in ("false", "0", "", "no", None, "maybe"):
            self.assertFalse(common.as_bool(s), s)

    def test_now_utc_parses_z_and_defaults_aware(self):
        self.assertEqual(common.now_utc("2026-09-05T14:22:03Z"),
                         datetime(2026, 9, 5, 14, 22, 3, tzinfo=timezone.utc))
        self.assertIsNotNone(common.now_utc("").tzinfo)

    def test_now_utc_tolerates_a_naive_string(self):
        self.assertEqual(common.now_utc("2026-09-05T14:22:03"),
                         datetime(2026, 9, 5, 14, 22, 3, tzinfo=timezone.utc))

    def test_day_is_local(self):
        d = common.now_utc("2026-09-05T14:22:03Z")
        self.assertEqual(common.day(d, timezone.utc), "2026-09-05")

    def test_sparkline_and_trunc(self):
        self.assertEqual(common.sparkline([]), "")
        self.assertEqual(len(common.sparkline([0, 1, 2, 3])), 4)
        self.assertEqual(len(common.sparkline([5, 5, 5])), 3)
        self.assertEqual(common.trunc("abcdefgh", 5), "abcd…")
        self.assertEqual(common.trunc("abc", 5), "abc")

    def test_human_numbers(self):
        self.assertEqual(common.human_int(1234567), "1,234,567")
        self.assertEqual(common.human_usd("0.19"), "$0.19")
        self.assertEqual(common.human_usd("1234.5"), "$1,234.50")


class TestWarn(unittest.TestCase):
    def test_warn_is_ok_true(self):
        w = common.warn("nothing here yet")
        self.assertTrue(w["ok"])
        self.assertEqual(w["warning"], "nothing here yet")


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_append_then_read_roundtrip(self):
        store.append(self.dir, "punch", {"note": "api", "t": "2026-09-05T10:00:00Z"})
        store.append(self.dir, "punch", {"note": "docs", "t": "2026-09-05T11:30:00Z"})
        got = store.read(self.dir, "punch")
        self.assertEqual([e.data["note"] for e in got], ["api", "docs"])
        self.assertEqual(got[0].t.hour, 10)

    def test_append_stamps_time_and_version(self):
        store.append(self.dir, "punch", {"note": "x"})
        line = json.loads(open(str(store.stream_path(self.dir, "punch"))).read().strip())
        self.assertIn("t", line)
        self.assertEqual(line["v"], 1)

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(store.read(self.dir, "never-written"), [])

    def test_torn_trailing_line_is_skipped_not_fatal(self):
        p = store.stream_path(self.dir, "punch")
        os.makedirs(self.dir, exist_ok=True)
        open(str(p), "w").write('{"t":"2026-09-05T10:00:00Z","note":"good"}\n{"t":"2026-')
        self.assertEqual(len(store.read(self.dir, "punch")), 1)

    def test_read_since_filters(self):
        store.append(self.dir, "punch", {"note": "old", "t": "2026-09-01T10:00:00Z"})
        store.append(self.dir, "punch", {"note": "new", "t": "2026-09-05T10:00:00Z"})
        got = store.read(self.dir, "punch", since=common.now_utc("2026-09-03T00:00:00Z"))
        self.assertEqual([e.data["note"] for e in got], ["new"])

    def test_streak_counts_back_from_today(self):
        days = {"2026-09-03", "2026-09-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (3, 3))

    def test_streak_survives_a_today_with_no_entry(self):
        self.assertEqual(store.streak({"2026-09-03", "2026-09-04"}, "2026-09-05")[0], 2)

    def test_streak_breaks_on_a_two_day_gap(self):
        days = {"2026-09-01", "2026-09-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (2, 2))

    def test_streak_longest_is_not_the_current_one(self):
        days = {"2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (1, 4))

    def test_grid_is_window_long_and_ends_today(self):
        g = store.grid({"2026-09-05"}, "2026-09-05", 7)
        self.assertEqual(len(g), 7)
        self.assertTrue(g.endswith("█"))
        self.assertEqual(g.count("·"), 6)

    def test_worst_weekday_needs_enough_history(self):
        self.assertIsNone(store.worst_weekday({"2026-09-05"}, "2026-09-05", 7))

    def test_worst_weekday_names_the_day_missed_most(self):
        days = set()
        d = datetime(2026, 8, 10, tzinfo=timezone.utc)          # a Monday
        for i in range(28):
            day_ = d + timedelta(days=i)
            if day_.weekday() != 6:                              # never on a Sunday
                days.add(day_.strftime("%Y-%m-%d"))
        self.assertEqual(store.worst_weekday(days, "2026-09-06", 28), "Sunday")

    def test_days_with_entries_uses_local_time(self):
        store.append(self.dir, "punch", {"note": "x", "t": "2026-09-05T10:00:00Z"})
        got = store.days_with_entries(store.read(self.dir, "punch"), timezone.utc)
        self.assertEqual(got, {"2026-09-05"})
