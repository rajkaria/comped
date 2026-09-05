"""Unit tests for micro_core: the emit contract, scalars and formatting."""
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from micro_core import common


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
