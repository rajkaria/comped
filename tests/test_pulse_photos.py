"""photo-debt: the schema probe, the three reclaim tiers, and the two promises on the card.

Two of these tests are the whole reason the Play exists in this shape. The first builds the same
library in two different ZASSET schemas — one with the columns macOS shipped, one where Core Data
has renamed and dropped some of them — and asserts that both bind and that the dropped ones become
a labelled unknown rather than a zero or an exception. The second asserts the two things photo-debt
promises never to do: delete anything, and pretend it can compare images by appearance.

Everything is built from real temporary SQLite databases and real files on disk, because a probe
layer tested against a mock of itself proves only that the mock matches the code.
"""
import ast
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from daily_core.card import W
from daily_core.common import Budget
from daily_core.parsers import photosdb
from daily_core.scan import photos

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

SRC = pathlib.Path("daily_core")
SCAN = SRC / "scan" / "photos.py"
PARSER = SRC / "parsers" / "photosdb.py"


def apple(when) -> float:
    return (when - APPLE_EPOCH).total_seconds()


# ---------------------------------------------------------------- two schemas, one library

# The columns macOS has actually shipped, and the same fields after a Core Data model migration
# renamed them, suffixed one and dropped three. Neither list is hard-coded anywhere in the reader.
SCHEMA_SHIPPED = [
    ("Z_PK", "INTEGER"), ("ZUUID", "TEXT"), ("ZDATECREATED", "REAL"), ("ZADDEDDATE", "REAL"),
    ("ZLASTVIEWEDDATE", "REAL"), ("ZWIDTH", "INTEGER"), ("ZHEIGHT", "INTEGER"),
    ("ZFILENAME", "TEXT"), ("ZDIRECTORY", "TEXT"), ("ZFAVORITE", "INTEGER"),
    ("ZHASADJUSTMENTS", "INTEGER"), ("ZTRASHEDSTATE", "INTEGER"), ("ZKIND", "INTEGER"),
    ("ZKINDSUBTYPE", "INTEGER"), ("ZSAVEDASSETTYPE", "INTEGER"),
    ("ZUNIFORMTYPEIDENTIFIER", "TEXT"), ("ZORIGINALFILESIZE", "INTEGER"),
    ("ZLOCALLYAVAILABLE", "INTEGER"), ("ZAVALANCHEUUID", "TEXT"),
]

SCHEMA_MIGRATED = [
    ("Z_PK", "INTEGER"), ("ZUUID", "TEXT"), ("Z54_DATECREATED", "REAL"), ("Z54_ADDEDDATE", "REAL"),
    ("ZPIXELWIDTH", "INTEGER"), ("ZPIXELHEIGHT", "INTEGER"), ("ZORIGINALFILENAME", "TEXT"),
    ("ZDIRECTORY", "TEXT"), ("ZISFAVORITE", "INTEGER"), ("ZHASADJUSTMENT", "INTEGER"),
    ("ZTRASHED", "INTEGER"), ("ZMEDIATYPE", "INTEGER"), ("ZSUBTYPE", "INTEGER"),
    ("ZCONTENTTYPE", "TEXT"), ("ZFILESIZE2", "INTEGER"), ("ZCLOUDLOCALSTATE", "INTEGER"),
]

# One logical library, written into whichever columns the schema happens to have.
LIBRARY = [
    {"uuid": "a1", "filename": "IMG_0001.HEIC", "captured": NOW - timedelta(days=10),
     "added": NOW - timedelta(days=10), "viewed": NOW - timedelta(days=1),
     "width": 4032, "height": 3024, "favourite": 1, "edited": 0, "trashed": 0, "kind": 0,
     "subtype": 0, "saved_type": 0, "uti": "public.heic", "bytes": 2000000, "local": 1,
     "burst_id": "", "dir": "originals/a"},
    {"uuid": "a2", "filename": "IMG_0002.HEIC", "captured": NOW - timedelta(days=10),
     "added": NOW - timedelta(days=10), "viewed": None,
     "width": 4032, "height": 3024, "favourite": 0, "edited": 0, "trashed": 0, "kind": 0,
     "subtype": 0, "saved_type": 0, "uti": "public.heic", "bytes": 2000000, "local": 1,
     "burst_id": "", "dir": "originals/a"},
    {"uuid": "a3", "filename": "Screenshot 2019-01-02.png", "captured": NOW - timedelta(days=900),
     "added": NOW - timedelta(days=900), "viewed": None,
     "width": 2880, "height": 1800, "favourite": 0, "edited": 0, "trashed": 0, "kind": 0,
     "subtype": 10, "saved_type": 3, "uti": "public.png", "bytes": 500000, "local": 1,
     "burst_id": "", "dir": "originals/b"},
    {"uuid": "a4", "filename": "IMG_9000.MOV", "captured": NOW - timedelta(days=30),
     "added": NOW - timedelta(days=30), "viewed": None,
     "width": 1920, "height": 1080, "favourite": 0, "edited": 0, "trashed": 0, "kind": 1,
     "subtype": 0, "saved_type": 0, "uti": "com.apple.quicktime-movie", "bytes": 90000000,
     "local": 0, "burst_id": "", "dir": "originals/c"},
]

COLUMN_FOR = {
    "shipped": {"uuid": "ZUUID", "filename": "ZFILENAME", "captured": "ZDATECREATED",
                "added": "ZADDEDDATE", "viewed": "ZLASTVIEWEDDATE", "width": "ZWIDTH",
                "height": "ZHEIGHT", "favourite": "ZFAVORITE", "edited": "ZHASADJUSTMENTS",
                "trashed": "ZTRASHEDSTATE", "kind": "ZKIND", "subtype": "ZKINDSUBTYPE",
                "saved_type": "ZSAVEDASSETTYPE", "uti": "ZUNIFORMTYPEIDENTIFIER",
                "bytes": "ZORIGINALFILESIZE", "local": "ZLOCALLYAVAILABLE",
                "burst_id": "ZAVALANCHEUUID", "dir": "ZDIRECTORY"},
    "migrated": {"uuid": "ZUUID", "filename": "ZORIGINALFILENAME", "captured": "Z54_DATECREATED",
                 "added": "Z54_ADDEDDATE", "width": "ZPIXELWIDTH", "height": "ZPIXELHEIGHT",
                 "favourite": "ZISFAVORITE", "edited": "ZHASADJUSTMENT", "trashed": "ZTRASHED",
                 "kind": "ZMEDIATYPE", "subtype": "ZSUBTYPE", "uti": "ZCONTENTTYPE",
                 "bytes": "ZFILESIZE2", "local": "ZCLOUDLOCALSTATE", "dir": "ZDIRECTORY"},
}


def build_db(path, columns, shape: str, rows=LIBRARY, table: str = "ZASSET"):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE {0} ({1})".format(
        table, ", ".join("{0} {1}".format(n, t) for n, t in columns)))
    mapping = COLUMN_FOR[shape]
    for i, row in enumerate(rows):
        cols, vals = ["Z_PK"], [i + 1]
        for logical, column in sorted(mapping.items()):
            if logical not in row:
                continue
            value = row[logical]
            if logical in ("captured", "added", "viewed"):
                value = apple(value) if value else None
            cols.append(column)
            vals.append(value)
        con.execute("INSERT INTO {0} ({1}) VALUES ({2})".format(
            table, ", ".join(cols), ", ".join("?" * len(vals))), vals)
    con.commit()
    con.close()
    return path


def open_ro(path):
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


class TestSchemaProbe(unittest.TestCase):
    """The same library, two schemas, one reader that names no column it has not first seen."""

    def _bound(self, columns, shape):
        tmp = tempfile.mkdtemp()
        db = build_db(pathlib.Path(tmp) / "Photos.sqlite", columns, shape)
        con = open_ro(db)
        self.addCleanup(con.close)
        return con, photosdb.bind(con)

    def test_the_shipped_schema_binds_every_logical_field(self):
        con, mapping = self._bound(SCHEMA_SHIPPED, "shipped")
        self.assertTrue(mapping["ok"])
        self.assertEqual(mapping["missing"], [])
        self.assertEqual(mapping["map"]["captured"], "ZDATECREATED")
        self.assertEqual(mapping["map"]["filename"], "ZFILENAME")

    def test_a_renamed_and_suffixed_column_still_binds(self):
        con, mapping = self._bound(SCHEMA_MIGRATED, "migrated")
        self.assertTrue(mapping["ok"])
        # Z54_DATECREATED is ZDATECREATED behind a Core Data entity prefix; ZFILESIZE2 is
        # ZFILESIZE behind a migration suffix. Neither name appears in the reader.
        self.assertEqual(mapping["map"]["captured"], "Z54_DATECREATED")
        self.assertEqual(mapping["map"]["bytes"], "ZFILESIZE2")
        self.assertEqual(mapping["map"]["width"], "ZPIXELWIDTH")
        self.assertEqual(mapping["map"]["local"], "ZCLOUDLOCALSTATE")

    def test_every_missing_column_degrades_exactly_one_field_to_unknown(self):
        con, mapping = self._bound(SCHEMA_MIGRATED, "migrated")
        self.assertEqual(set(mapping["missing"]), {"viewed", "saved_type", "burst_id"})
        self.assertIn("unresolved on this schema", mapping["note"])
        rows = list(photosdb.rows(con, mapping))
        self.assertEqual(len(rows), len(LIBRARY))
        for r in rows:
            self.assertEqual(r["viewed"], "")                       # unknown, not "never"
            self.assertIn("viewed", r["unknown"])
            self.assertNotIn("captured", r["unknown"])              # this one resolved
        self.assertEqual(rows[0]["filename"], "IMG_0001.HEIC")      # and the rest still read

    def test_both_schemas_produce_the_same_answer_for_the_fields_they_share(self):
        shipped_con, shipped_map = self._bound(SCHEMA_SHIPPED, "shipped")
        migrated_con, migrated_map = self._bound(SCHEMA_MIGRATED, "migrated")
        a = list(photosdb.rows(shipped_con, shipped_map))
        b = list(photosdb.rows(migrated_con, migrated_map))
        shared = ("id", "filename", "captured", "added", "width", "height", "favourite",
                  "edited", "trashed", "video", "bytes", "local")
        self.assertEqual([{k: r[k] for k in shared} for r in a],
                         [{k: r[k] for k in shared} for r in b])

    def test_a_schema_with_almost_nothing_in_it_still_answers(self):
        """The degradation floor: two columns, and the run produces assets rather than an exception."""
        tmp = tempfile.mkdtemp()
        db = pathlib.Path(tmp) / "Photos.sqlite"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE ZASSET (Z_PK INTEGER, ZFILENAME TEXT)")
        con.execute("INSERT INTO ZASSET VALUES (1, 'IMG_1.JPG')")
        con.commit()
        con.close()
        con = open_ro(db)
        self.addCleanup(con.close)
        mapping = photosdb.bind(con)
        self.assertTrue(mapping["ok"])
        rows = list(photosdb.rows(con, mapping))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "IMG_1.JPG")
        self.assertEqual(rows[0]["captured"], "")
        self.assertEqual(rows[0]["bytes"], 0)

    def test_a_database_with_no_asset_table_is_a_note_not_a_crash(self):
        tmp = tempfile.mkdtemp()
        db = pathlib.Path(tmp) / "Photos.sqlite"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE ZALBUM (Z_PK INTEGER)")
        con.commit()
        con.close()
        con = open_ro(db)
        self.addCleanup(con.close)
        mapping = photosdb.bind(con)
        self.assertFalse(mapping["ok"])
        self.assertIn("no ZASSET table", mapping["note"])
        self.assertEqual(list(photosdb.rows(con, mapping)), [])

    def test_the_row_reader_respects_the_budget(self):
        con, mapping = self._bound(SCHEMA_SHIPPED, "shipped")
        budget = Budget(max_files=2)
        self.assertEqual(len(list(photosdb.rows(con, mapping, budget))), 2)
        self.assertTrue(budget.exhausted)

    def test_a_video_and_a_screenshot_are_recognised_from_the_columns_that_exist(self):
        con, mapping = self._bound(SCHEMA_SHIPPED, "shipped")
        rows = {r["filename"]: r for r in photosdb.rows(con, mapping)}
        self.assertTrue(rows["IMG_9000.MOV"]["video"])
        self.assertFalse(rows["IMG_9000.MOV"]["screenshot"])
        self.assertTrue(rows["Screenshot 2019-01-02.png"]["screenshot"])
        self.assertFalse(rows["IMG_0001.HEIC"]["screenshot"])
        self.assertTrue(rows["IMG_0001.HEIC"]["favourite"])
        self.assertFalse(rows["IMG_9000.MOV"]["local"])

    def test_a_screenshot_is_still_recognised_when_the_schema_lost_the_column(self):
        """The migrated schema has no saved-asset type, so the file name is the remaining evidence."""
        con, mapping = self._bound(SCHEMA_MIGRATED, "migrated")
        rows = {r["filename"]: r for r in photosdb.rows(con, mapping)}
        self.assertTrue(rows["Screenshot 2019-01-02.png"]["screenshot"])


# ---------------------------------------------------------------- sources

class TestSources(unittest.TestCase):
    def _library(self, columns=SCHEMA_SHIPPED, shape="shipped"):
        tmp = pathlib.Path(tempfile.mkdtemp()) / "Photos Library.photoslibrary"
        (tmp / "database").mkdir(parents=True)
        build_db(tmp / "database" / "Photos.sqlite", columns, shape)
        return tmp

    def test_a_real_library_is_read_through_the_read_only_copy(self):
        lib = self._library()
        sources, records = photos.read_source("photos", Budget(), {"library": str(lib)})
        self.assertTrue(sources[0].found)
        self.assertEqual(len(records), len(LIBRARY))
        self.assertIn("fields bound", sources[0].note)

    def test_reading_the_library_leaves_it_byte_for_byte_unchanged(self):
        lib = self._library()
        db = lib / "database" / "Photos.sqlite"
        before = db.read_bytes()
        photos.read_source("photos", Budget(), {"library": str(lib)})
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in (lib / "database").iterdir()), ["Photos.sqlite"])

    def test_an_absent_library_is_a_labelled_miss(self):
        sources, records = photos.read_source(
            "photos", Budget(), {"library": os.path.join(tempfile.mkdtemp(), "nope.photoslibrary")})
        self.assertFalse(sources[0].found)
        self.assertIn("no Photos library", sources[0].note)
        self.assertEqual(records, [])

    def test_a_library_without_a_database_is_a_different_miss(self):
        lib = pathlib.Path(tempfile.mkdtemp()) / "Photos Library.photoslibrary"
        lib.mkdir()
        sources, records = photos.read_source("photos", Budget(), {"library": str(lib)})
        self.assertFalse(sources[0].found)
        self.assertIn("no Photos.sqlite", sources[0].note)

    def test_an_unreadable_database_is_a_note_not_an_exception(self):
        lib = pathlib.Path(tempfile.mkdtemp()) / "Photos Library.photoslibrary"
        (lib / "database").mkdir(parents=True)
        (lib / "database" / "Photos.sqlite").write_bytes(b"this is not a database at all")
        sources, records = photos.read_source("photos", Budget(), {"library": str(lib)})
        self.assertFalse(sources[0].found)
        self.assertTrue(sources[0].note)
        self.assertEqual(records, [])

    def test_a_folder_of_real_files_is_a_source_of_its_own(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "IMG_0001.jpg").write_bytes(b"a" * 100)
        (root / "IMG_0002.jpg").write_bytes(b"b" * 100)
        (root / "notes.txt").write_text("not a photograph", encoding="utf-8")
        sources, records = photos.read_source("folder", Budget(), {"root": str(root)})
        self.assertTrue(sources[0].found)
        self.assertEqual(sorted(r["filename"] for r in records), ["IMG_0001.jpg", "IMG_0002.jpg"])
        for r in records:
            self.assertIn("favourite", r["unknown"])       # a bare file cannot know
            self.assertEqual(r["bytes"], 100)

    def test_an_absent_folder_is_a_labelled_miss(self):
        sources, records = photos.read_source(
            "folder", Budget(), {"root": os.path.join(tempfile.mkdtemp(), "gone")})
        self.assertFalse(sources[0].found)
        self.assertIn("no folder", sources[0].note)

    def test_a_folder_with_no_images_is_a_labelled_miss(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "readme.md").write_text("nothing here", encoding="utf-8")
        sources, records = photos.read_source("folder", Budget(), {"root": str(root)})
        self.assertFalse(sources[0].found)
        self.assertIn("no images", sources[0].note)

    def test_the_demo_reads_a_bundled_fixture_and_only_once(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "assets.json").write_text(json.dumps([
            {"id": "d1", "filename": "IMG_1.jpg", "bytes": 10, "captured": "2026-01-01T00:00:00Z"},
        ]), encoding="utf-8")
        sources, records = photos.read_source("photos", Budget(), {"demo_root": str(root)})
        self.assertTrue(sources[0].found)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "demo")
        folder_sources, folder_records = photos.read_source("folder", Budget(), {"demo_root": str(root)})
        self.assertEqual(folder_records, [])

    def test_a_missing_demo_fixture_is_a_labelled_miss(self):
        sources, records = photos.read_source("photos", Budget(), {"demo_root": tempfile.mkdtemp()})
        self.assertFalse(sources[0].found)
        self.assertIn("fixture missing", sources[0].note)

    def test_an_unknown_source_name_is_a_miss_rather_than_a_raise(self):
        sources, records = photos.read_source("telepathy", Budget(), {})
        self.assertFalse(sources[0].found)


# ---------------------------------------------------------------- analysis

def rec(ident, name, captured=None, **kw):
    base = {"id": ident, "filename": name, "stem": os.path.splitext(name)[0],
            "ext": os.path.splitext(name)[1].lower(), "width": 4032, "height": 3024,
            "bytes": 1000, "source": "photos", "unknown": []}
    base.update(kw)
    if captured is not None:
        base["captured"] = captured.strftime("%Y-%m-%dT%H:%M:%SZ")
        base.setdefault("added", base["captured"])
    return photosdb.asset(**base)


def at(**kw):
    return NOW - timedelta(**kw)


class TestBursts(unittest.TestCase):
    def _view(self, records, **cfg):
        return photos.analyse(records, NOW, cfg)

    def test_frames_inside_the_window_are_one_burst_and_frames_outside_it_are_not(self):
        t = at(days=3)
        records = [
            rec("1", "IMG_0001.HEIC", t),
            rec("2", "IMG_0002.HEIC", t + timedelta(seconds=2)),     # on the boundary: same burst
            rec("3", "IMG_0003.HEIC", t + timedelta(seconds=5)),     # 3s later: a new burst
            rec("4", "IMG_0004.HEIC", t + timedelta(seconds=6)),
        ]
        v = self._view(records)
        self.assertEqual(v["bursts"]["groups"], 2)
        self.assertEqual(v["bursts"]["siblings"], 2)

    def test_a_wider_window_merges_what_a_narrow_one_split(self):
        t = at(days=3)
        records = [rec("1", "IMG_0001.HEIC", t),
                   rec("2", "IMG_0002.HEIC", t + timedelta(seconds=5))]
        self.assertEqual(self._view(records)["bursts"]["groups"], 0)
        self.assertEqual(self._view(records, burst_window=6)["bursts"]["groups"], 1)

    def test_different_dimensions_are_never_one_burst(self):
        t = at(days=3)
        records = [rec("1", "IMG_0001.HEIC", t),
                   rec("2", "IMG_0002.HEIC", t + timedelta(seconds=1), width=1024, height=768)]
        self.assertEqual(self._view(records)["bursts"]["groups"], 0)

    def test_unrelated_file_names_are_never_one_burst(self):
        t = at(days=3)
        records = [rec("1", "IMG_0001.HEIC", t),
                   rec("2", "sunset.HEIC", t + timedelta(seconds=1))]
        self.assertEqual(self._view(records)["bursts"]["groups"], 0)

    def test_the_library_own_burst_identifier_wins_over_the_heuristic(self):
        t = at(days=3)
        records = [rec("1", "IMG_0001.HEIC", t, burst_id="avalanche"),
                   rec("2", "elsewhere.HEIC", t + timedelta(seconds=90), burst_id="avalanche")]
        self.assertEqual(self._view(records)["bursts"]["groups"], 1)

    def test_a_long_run_of_frames_never_chains_into_one_enormous_burst(self):
        """A time-lapse is one frame a second for an hour. It is not one press of the shutter."""
        t = at(days=3)
        records = [rec(str(i), "IMG_{0:04d}.HEIC".format(i), t + timedelta(seconds=i))
                   for i in range(60)]
        v = self._view(records)
        self.assertEqual(v["bursts"]["largest"], 3)          # bounded by the 2s window, not chained
        self.assertEqual(v["bursts"]["groups"], 20)

    def test_a_real_burst_keeps_its_numbering_across_the_whole_group(self):
        """Ten frames in one second: the counter runs past the anchor, and the group stays whole."""
        t = at(days=3)
        records = [rec(str(i), "IMG_{0:04d}.HEIC".format(i), t + timedelta(milliseconds=100 * i))
                   for i in range(10)]
        v = self._view(records)
        self.assertEqual(v["bursts"]["groups"], 1)
        self.assertEqual(v["bursts"]["largest"], 10)
        self.assertEqual(v["bursts"]["siblings"], 9)

    def test_a_video_is_never_a_burst_frame(self):
        t = at(days=3)
        records = [rec("1", "IMG_0001.MOV", t, video=True),
                   rec("2", "IMG_0002.MOV", t + timedelta(seconds=1), video=True)]
        self.assertEqual(self._view(records)["bursts"]["groups"], 0)


class TestDuplicates(unittest.TestCase):
    def test_identical_bytes_on_disk_are_found_and_a_size_collision_is_not(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "a.jpg").write_bytes(b"x" * 4096)
        (root / "b.jpg").write_bytes(b"x" * 4096)            # the same file, twice
        (root / "c.jpg").write_bytes(b"y" * 4096)            # same size, different bytes
        _sources, records = photos.read_source("folder", Budget(), {"root": str(root)})
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["duplicates"]["groups"], 1)
        self.assertEqual(v["duplicates"]["extra"], 1)
        self.assertEqual(v["duplicates"]["bytes"], 4096)
        self.assertIn("SHA-256", v["duplicates"]["proof"])

    def test_an_unproven_group_is_shown_but_never_counted_as_a_duplicate(self):
        """Same size is a reason to look, never a reason to claim. The two are separate numbers."""
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "a.jpg").write_bytes(b"x" * 4096)
        (root / "c.jpg").write_bytes(b"y" * 4096)
        _sources, records = photos.read_source("folder", Budget(), {"root": str(root)})
        v = photos.analyse(records, NOW, {"hash_dupes": False})
        self.assertEqual(v["duplicates"]["groups"], 0)
        self.assertEqual(v["duplicates"]["bytes"], 0)
        self.assertEqual(v["duplicates"]["unproven_groups"], 1)
        self.assertEqual(v["duplicates"]["unproven_extra"], 1)
        self.assertIn("bytes not compared", v["duplicates"]["unproven_note"])
        self.assertEqual(v["reclaim"]["ids"], [])            # nothing unproven reaches a tier
        self.assertIn("never counted as reclaimable", photos.report_markdown(v, {}, []))

    def test_a_file_too_large_to_hash_is_never_claimed_from_a_partial_digest(self):
        """Two videos out of one camera share a long header; a truncated hash would call them equal."""
        big = photos.HASH_CAP + 1
        records = [rec("1", "clip_a.mov", at(days=1), bytes=big, video=True, path="/dev/null"),
                   rec("2", "clip_b.mov", at(days=1), bytes=big, video=True, path="/dev/null")]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["duplicates"]["groups"], 0)
        self.assertEqual(v["duplicates"]["unproven_groups"], 1)
        self.assertIn("hashing limit", v["duplicates"]["unproven_note"])
        self.assertEqual(v["reclaim"]["bytes"], 0)

    def test_the_digest_refuses_an_oversized_file_rather_than_hashing_its_first_pages(self):
        root = pathlib.Path(tempfile.mkdtemp())
        path = root / "big.jpg"
        path.write_bytes(b"z" * 1024)
        self.assertTrue(photos._digest({"path": str(path)}))
        saved = photos.HASH_CAP
        try:
            photos.HASH_CAP = 512
            self.assertEqual(photos._digest({"path": str(path)}), "")
        finally:
            photos.HASH_CAP = saved

    def test_a_file_that_cannot_be_read_is_simply_not_claimed_as_a_duplicate(self):
        records = [rec("1", "a.jpg", at(days=1), path="/nonexistent/a.jpg"),
                   rec("2", "b.jpg", at(days=1), path="/nonexistent/b.jpg")]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["duplicates"]["groups"], 0)


class TestScreenshots(unittest.TestCase):
    def test_the_cohort_counts_bytes_and_how_many_were_reopened(self):
        records = [
            rec("1", "Screenshot A.png", at(days=200), screenshot=True, bytes=500,
                viewed="2026-09-01T00:00:00Z"),
            rec("2", "Screenshot B.png", at(days=200), screenshot=True, bytes=500),
            rec("3", "Screenshot C.png", at(days=2), screenshot=True, bytes=500),
            rec("4", "IMG_0001.HEIC", at(days=2)),
        ]
        v = photos.analyse(records, NOW, {})
        shots = v["screenshots"]
        self.assertEqual(shots["count"], 3)
        self.assertEqual(shots["bytes"], 1500)
        self.assertTrue(shots["reopen_known"])
        self.assertEqual(shots["reopened"], 1)
        self.assertEqual(shots["never_reopened"], 2)
        self.assertEqual(shots["old"], 2)

    def test_a_schema_without_a_last_viewed_column_says_so_instead_of_claiming_zero(self):
        records = [rec("1", "Screenshot A.png", at(days=200), screenshot=True,
                       unknown=["viewed"])]
        v = photos.analyse(records, NOW, {})
        self.assertFalse(v["screenshots"]["reopen_known"])
        self.assertIsNone(v["screenshots"]["never_reopened"])
        self.assertIn("cannot be answered", v["screenshots"]["reopen_note"])
        self.assertIn("viewed", v["unknown_fields"])
        self.assertIn("unknown", photos.report_markdown(v, {}, []))

    def test_a_field_one_source_can_see_is_not_reported_as_unknown(self):
        records = [rec("1", "a.png", at(days=1), unknown=["viewed", "favourite"]),
                   rec("2", "b.png", at(days=1), unknown=["favourite"])]
        self.assertEqual(photos.analyse(records, NOW, {})["unknown_fields"], ["favourite"])


class TestReclaimTiers(unittest.TestCase):
    def _records(self):
        t = at(days=400)
        return [
            # a byte-identical pair: same size, same extension, same digest
            rec("d1", "copy_a.jpg", at(days=5), bytes=1000, sha256="deadbeef"),
            rec("d2", "copy_b.jpg", at(days=5), bytes=1000, sha256="deadbeef"),
            # a three-frame burst, sized so it cannot collide with the pair above
            rec("b1", "IMG_0100.HEIC", t, bytes=2000),
            rec("b2", "IMG_0101.HEIC", t + timedelta(seconds=1), bytes=2000),
            rec("b3", "IMG_0102.HEIC", t + timedelta(seconds=2), bytes=2000),
            # an old screenshot
            rec("s1", "Screenshot old.png", at(days=300), bytes=3000, screenshot=True),
            # and a recent one, which is nobody's business yet
            rec("s2", "Screenshot new.png", at(days=2), bytes=3000, screenshot=True),
        ]

    def test_the_three_tiers_are_separate_and_each_asset_is_counted_once(self):
        v = photos.analyse(self._records(), NOW, {})
        tiers = {t["name"]: t for t in v["reclaim"]["tiers"]}
        self.assertEqual(sorted(tiers), ["burst siblings", "identical bytes", "screenshots >90d"])
        self.assertEqual(tiers["identical bytes"]["count"], 1)
        self.assertEqual(tiers["identical bytes"]["bytes"], 1000)
        self.assertEqual(tiers["burst siblings"]["count"], 2)
        self.assertEqual(tiers["burst siblings"]["bytes"], 4000)
        self.assertEqual(tiers["screenshots >90d"]["count"], 1)
        self.assertEqual(tiers["screenshots >90d"]["bytes"], 3000)
        self.assertEqual(v["reclaim"]["count"], 4)
        self.assertEqual(v["reclaim"]["bytes"], 8000)
        self.assertEqual(len(set(v["reclaim"]["ids"])), 4)

    def test_the_tiers_carry_their_confidence_and_render_as_one_bar(self):
        v = photos.analyse(self._records(), NOW, {})
        self.assertEqual([t["confidence"] for t in v["reclaim"]["tiers"]],
                         ["safe", "probably", "your call"])
        self.assertTrue(v["reclaim"]["bar"])
        self.assertIn("identical bytes", v["reclaim"]["legend"])

    def test_the_screenshot_threshold_is_configurable(self):
        v = photos.analyse(self._records(), NOW, {"screenshot_days": 1})
        tiers = {t["name"]: t for t in v["reclaim"]["tiers"]}
        self.assertEqual(tiers["screenshots >1d"]["count"], 2)

    def test_trashed_assets_are_their_own_already_reclaimable_bucket(self):
        records = self._records() + [rec("t1", "gone.jpg", at(days=3), bytes=7000, trashed=True)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["trashed"]["count"], 1)
        self.assertEqual(v["trashed"]["bytes"], 7000)
        self.assertNotIn("t1", v["reclaim"]["ids"])       # counted once, in its own bucket
        self.assertEqual(v["assets"], len(self._records()))


class TestNothingProtectedIsEverReclaimable(unittest.TestCase):
    """The hard requirement. A favourite or an edited asset never enters a reclaim number."""

    def _protected_everywhere(self):
        t = at(days=400)
        return [
            rec("d1", "copy_a.jpg", at(days=5), bytes=1000, sha256="beef", favourite=True),
            rec("d2", "copy_b.jpg", at(days=5), bytes=1000, sha256="beef", favourite=True),
            rec("b1", "IMG_0100.HEIC", t, bytes=2000, edited=True),
            rec("b2", "IMG_0101.HEIC", t + timedelta(seconds=1), bytes=2000, edited=True),
            rec("s1", "Screenshot old.png", at(days=300), bytes=3000, screenshot=True, favourite=True),
        ]

    def test_a_library_of_favourites_and_edits_has_nothing_to_reclaim(self):
        v = photos.analyse(self._protected_everywhere(), NOW, {})
        self.assertEqual(v["reclaim"]["count"], 0)
        self.assertEqual(v["reclaim"]["bytes"], 0)
        self.assertEqual(v["reclaim"]["ids"], [])
        self.assertEqual(v["protected"]["favourites"], 3)
        self.assertEqual(v["protected"]["edited"], 2)
        # the groups are still reported, because the user may want to look at them
        self.assertEqual(v["duplicates"]["groups"], 1)
        self.assertEqual(v["bursts"]["groups"], 1)

    def test_a_favourite_is_the_frame_that_survives_a_burst(self):
        t = at(days=400)
        records = [rec("b1", "IMG_0100.HEIC", t, bytes=2000),
                   rec("b2", "IMG_0101.HEIC", t + timedelta(seconds=1), bytes=2000, favourite=True),
                   rec("b3", "IMG_0102.HEIC", t + timedelta(seconds=2), bytes=2000)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["bursts"]["top"][0]["keeper"], "IMG_0101.HEIC")
        self.assertEqual(sorted(v["reclaim"]["ids"]), ["b1", "b3"])

    def test_one_protected_copy_never_drags_the_others_out_of_reach(self):
        records = [rec("d1", "a.jpg", at(days=5), bytes=1000, sha256="beef"),
                   rec("d2", "b.jpg", at(days=5), bytes=1000, sha256="beef", edited=True),
                   rec("d3", "c.jpg", at(days=5), bytes=1000, sha256="beef")]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(sorted(v["reclaim"]["ids"]), ["d1", "d3"])


class TestShapeOfTheLibrary(unittest.TestCase):
    def test_a_live_photo_is_one_asset_and_keeps_both_halves_of_its_size(self):
        records = [rec("1", "IMG_0001.HEIC", at(days=4), bytes=100, dir="a"),
                   rec("2", "IMG_0001.MOV", at(days=4), bytes=900, dir="a", video=True)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["assets"], 1)
        self.assertEqual(v["live"], 1)
        self.assertEqual(v["videos"], 0)
        self.assertEqual(v["stills"], 1)
        self.assertEqual(v["bytes"], 1000)

    def test_a_lone_movie_stays_a_video(self):
        records = [rec("1", "clip.MOV", at(days=4), bytes=900, video=True)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["videos"], 1)
        self.assertEqual(v["live"], 0)

    def test_videos_are_separated_from_stills_in_both_counts_and_bytes(self):
        records = [rec("1", "a.HEIC", at(days=4), bytes=100),
                   rec("2", "clip.MOV", at(days=4), bytes=9900, video=True)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual((v["stills"], v["videos"]), (1, 1))
        self.assertEqual((v["still_bytes"], v["video_bytes"]), (100, 9900))
        self.assertEqual(v["video_byte_share"], 99)

    def test_icloud_placeholders_are_counted_apart_and_left_out_of_the_local_bytes(self):
        records = [rec("1", "here.HEIC", at(days=4), bytes=1000),
                   rec("2", "cloud.HEIC", at(days=4), bytes=9000, local=False)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["not_local"], 1)
        self.assertEqual(v["not_local_share"], 50)
        self.assertEqual(v["local_bytes"], 1000)
        self.assertEqual(v["bytes"], 10000)

    def test_an_icloud_placeholder_is_never_reclaimable(self):
        records = [rec("d1", "a.jpg", at(days=5), bytes=1000, sha256="beef"),
                   rec("d2", "b.jpg", at(days=5), bytes=1000, sha256="beef", local=False)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual(v["reclaim"]["ids"], [])

    def test_growth_is_reported_per_year_with_a_sparkline(self):
        records = [rec(str(i), "IMG_{0}.HEIC".format(i),
                       datetime(2020 + i, 6, 1, tzinfo=timezone.utc), bytes=1000 * (i + 1))
                   for i in range(4)]
        v = photos.analyse(records, NOW, {})
        self.assertEqual([y["year"] for y in v["years"]], ["2020", "2021", "2022", "2023"])
        self.assertEqual([y["assets"] for y in v["years"]], [1, 1, 1, 1])
        self.assertTrue(v["spark_bytes"])

    def test_the_largest_assets_are_listed_and_capped(self):
        records = [rec(str(i), "IMG_{0}.HEIC".format(i), at(days=i + 1), bytes=1000 * (i + 1))
                   for i in range(10)]
        v = photos.analyse(records, NOW, {"top": 3})
        self.assertEqual([b["name"] for b in v["largest"]],
                         ["IMG_9.HEIC", "IMG_8.HEIC", "IMG_7.HEIC"])

    def test_an_empty_library_produces_a_card_rather_than_a_traceback(self):
        v = photos.analyse([], NOW, {})
        self.assertEqual(v["assets"], 0)
        self.assertEqual(v["reclaim"]["bytes"], 0)
        self.assertTrue(photos.render(v, {}))
        self.assertTrue(photos.report_markdown(v, {}, []))

    def test_a_delta_against_the_previous_baseline(self):
        records = [rec("1", "a.HEIC", at(days=4), bytes=1000)]
        first = photos.analyse(records, NOW, {})
        self.assertTrue(first["delta"]["first_run"])
        self.assertIn("first run", first["since"])
        later = photos.analyse(records + [rec("2", "b.HEIC", at(days=1), bytes=500)], NOW,
                               {"baseline": {"captured": "2026-09-01T00:00:00Z",
                                             "payload": first["baseline"]}})
        self.assertFalse(later["delta"]["first_run"])
        self.assertEqual(later["delta"]["grew"]["assets"], 1)
        self.assertIn("since 2026-09-01", later["since"])


# ---------------------------------------------------------------- promises

class TestPhotoDebtNeverDeletes(unittest.TestCase):
    BANNED = ("os.remove", "os.unlink", "shutil.rmtree", "Path.unlink", "send2trash", "os.rmdir")

    def test_the_scanner_contains_no_deletion_of_any_kind(self):
        text = SCAN.read_text(encoding="utf-8")
        for banned in self.BANNED:
            self.assertNotIn(banned, text, "{0} references {1}".format(SCAN, banned))

    def test_the_scanner_never_opens_anything_for_writing(self):
        tree = ast.parse(SCAN.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
                mode = node.args[1] if len(node.args) > 1 else None
                self.assertIsInstance(mode, ast.Constant, "open() must state its mode")
                self.assertNotIn("w", str(mode.value))
                self.assertNotIn("a", str(mode.value))
                self.assertNotIn("+", str(mode.value))

    def test_the_only_removal_anywhere_is_the_reader_own_temporary_copy(self):
        """The parser removes the temp copy `open_sqlite_readonly` made, and nothing else.

        A literal string ban cannot express that, because the copy must be removed: leaving one
        behind would litter a multi-gigabyte database into the temp directory on every run. So the
        call is checked instead — that there is exactly one, that it is rmtree, and that its
        argument is the temp directory name the reader was handed, never a path from the library.
        """
        text = PARSER.read_text(encoding="utf-8")
        for banned in ("os.remove", "os.unlink", "Path.unlink", "send2trash", "os.rmdir"):
            self.assertNotIn(banned, text, "{0} references {1}".format(PARSER, banned))
        tree = ast.parse(text)
        removals = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "rmtree"]
        self.assertEqual(len(removals), 1, "exactly one removal is expected")
        call = removals[0]
        self.assertEqual(getattr(call.func.value, "id", ""), "shutil")
        self.assertEqual(getattr(call.args[0], "id", ""), "tmp")
        self.assertTrue([k for k in call.keywords if k.arg == "ignore_errors"])
        self.assertIn("tmp = open_sqlite_readonly", text.replace("con, ", ""))

    def test_the_guarantee_is_stated_on_the_card_and_in_the_report(self):
        v = photos.analyse([rec("1", "a.HEIC", at(days=1))], NOW, {})
        self.assertIn("never deletes", v["never_deletes"])
        self.assertIn("never deletes", photos.render(v, {}))
        self.assertIn("never deletes", photos.report_markdown(v, {}, []))

    def test_the_live_database_is_only_ever_reached_through_the_shared_read_only_copy(self):
        for path in (SCAN, PARSER):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sqlite3.connect", text, path)
            self.assertNotIn("import sqlite3", text, path)
        self.assertIn("open_sqlite_readonly", PARSER.read_text(encoding="utf-8"))


class TestNoPerceptualHashing(unittest.TestCase):
    def test_no_imaging_library_and_no_similarity_score_anywhere(self):
        for path in (SCAN, PARSER):
            text = path.read_text(encoding="utf-8")
            for banned in ("import PIL", "from PIL", "imagehash", "phash", "dhash", "ahash",
                           "average_hash", "perceptual", "cv2", "numpy", "/usr/bin/sips"):
                self.assertNotIn(banned, text, "{0} references {1}".format(path, banned))

    def test_the_only_content_test_is_a_cryptographic_hash_of_the_bytes(self):
        text = SCAN.read_text(encoding="utf-8")
        tree = ast.parse(text)
        hashes = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and getattr(n.func.value, "id", "") == "hashlib"}
        self.assertEqual(hashes, {"sha256"})

    def test_the_method_is_stated_rather_than_left_for_the_reader_to_assume(self):
        v = photos.analyse([rec("1", "a.HEIC", at(days=1))], NOW, {})
        self.assertIn("no similarity score is invented", v["no_pixel_compare"])
        report = photos.report_markdown(v, {}, [])
        self.assertIn("No image is decoded", report)
        self.assertIn("never decoded", report)

    def test_the_reader_starts_no_child_process(self):
        for path in (SCAN, PARSER):
            self.assertNotIn("subprocess", path.read_text(encoding="utf-8"), path)


class TestDeterminism(unittest.TestCase):
    def _records(self):
        t = at(days=30)
        return [rec("b{0}".format(i), "IMG_010{0}.HEIC".format(i), t + timedelta(seconds=i),
                    bytes=2000) for i in range(4)] + [
            rec("d1", "a.jpg", at(days=5), bytes=1000, sha256="beef"),
            rec("d2", "b.jpg", at(days=5), bytes=1000, sha256="beef"),
            rec("s1", "Screenshot x.png", at(days=300), bytes=3000, screenshot=True)]

    def test_the_same_input_and_the_same_clock_give_byte_identical_output(self):
        a = photos.analyse(self._records(), NOW, {})
        b = photos.analyse(self._records(), NOW, {})
        self.assertEqual(json.dumps(a, sort_keys=True, default=str),
                         json.dumps(b, sort_keys=True, default=str))
        self.assertEqual(photos.render(a, {}), photos.render(b, {}))
        self.assertEqual(photos.report_markdown(a, {}, []), photos.report_markdown(b, {}, []))

    def test_the_order_the_records_arrive_in_does_not_change_the_answer(self):
        forward = photos.analyse(self._records(), NOW, {})
        backward = photos.analyse(list(reversed(self._records())), NOW, {})
        self.assertEqual(json.dumps(forward, sort_keys=True, default=str),
                         json.dumps(backward, sort_keys=True, default=str))

    def test_the_view_survives_the_step_boundary_as_json(self):
        v = photos.analyse(self._records(), NOW, {})
        round_tripped = json.loads(json.dumps(v))
        self.assertEqual(round_tripped["reclaim"]["ids"], v["reclaim"]["ids"])
        self.assertNotIn("_cluster", json.dumps(v))


class TestPresentation(unittest.TestCase):
    def test_the_card_is_64_columns_wide_on_every_row(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "IMG_0001.jpg").write_bytes(b"x" * 4096)
        (root / "IMG_0002.jpg").write_bytes(b"x" * 4096)
        _sources, records = photos.read_source("folder", Budget(), {"root": str(root)})
        card = photos.render(photos.analyse(records, NOW, {}), {})
        for line in card.splitlines():
            self.assertEqual(len(line), W, line)

    def test_the_report_names_every_source_it_looked_at(self):
        from dataclasses import asdict
        sources, records = photos.read_source(
            "folder", Budget(), {"root": os.path.join(tempfile.mkdtemp(), "gone")})
        report = photos.report_markdown(photos.analyse(records, NOW, {}), {},
                                        [asdict(s) for s in sources])
        self.assertIn("| folder | no |", report)


if __name__ == "__main__":
    unittest.main()
