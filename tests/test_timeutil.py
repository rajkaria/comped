import unittest
from datetime import datetime, timezone, timedelta
from comped_core.timeutil import parse_ts, window_start, iso, day_key

class TimeTests(unittest.TestCase):
    def test_parse_iso_z(self):
        self.assertEqual(parse_ts("2026-09-03T14:01:44.790Z"), datetime(2026, 9, 3, 14, 1, 44, 790000, tzinfo=timezone.utc))
    def test_parse_offset(self):
        self.assertEqual(parse_ts("2026-09-02T14:09:52+05:30").utcoffset(), timedelta(0))
    def test_parse_epoch_seconds_and_millis(self):
        self.assertEqual(parse_ts(1780387497).year, 2026); self.assertEqual(parse_ts(1780387497000).year, 2026)
    def test_bad_returns_none(self):
        self.assertIsNone(parse_ts("yesterday")); self.assertIsNone(parse_ts(None))
    def test_window_and_iso(self):
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)
        self.assertEqual(window_start(now, 30), datetime(2026, 8, 4, tzinfo=timezone.utc))
        self.assertEqual(iso(now), "2026-09-03T00:00:00Z"); self.assertEqual(day_key(now), "2026-09-03")
