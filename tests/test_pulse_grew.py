"""what-grew, tested against a real directory tree that really changes between two runs.

The whole Play is one claim — "this is what moved since last time" — and the only way to test a
claim like that is to make something move. Every test here builds a temp tree, runs the scan to
write a baseline, mutates the tree (grows a file, shrinks another, adds a folder, deletes one) and
runs again. The rest of the file guards the promises around that number: that the first run says it
has nothing to compare against instead of printing a zero, that a folder it could not open is
counted rather than silently dropped, that the projection is labelled a straight line and not a
forecast, that the reclaim figure is regenerable bytes and nothing else, and that the module never
deletes anything.
"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daily_core.card import W
from daily_core.common import Budget, display_width
from daily_core.scan import grew

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=7)
KB = 1024


def _file(path: Path, kb: int):
    """Real bytes, so st_blocks is a real block count and not a compressed or sparse surprise."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(kb * KB))


def _cfg(out_dir, root, **over) -> dict:
    cfg = {"root": str(root), "out_dir": str(out_dir), "depth": 4, "floor_bytes": 0,
           "keep_baselines": 10, "since": "", "color": False}
    cfg.update(over)
    return cfg


def _run(out_dir, root, now, **over) -> tuple:
    cfg = _cfg(out_dir, root, **over)
    sources, snapshot = grew.read_source("home", Budget(), cfg)
    return sources, snapshot, grew.analyse(snapshot, now, cfg)


def _run_fixed(out_dir, root, now, free=100 * KB * KB, **over) -> tuple:
    """The same run with the disk's free space pinned, so a busy machine cannot make a test flaky."""
    cfg = _cfg(out_dir, root, **over)
    sources, snapshot = grew.read_source("home", Budget(), cfg)
    snapshot["free_bytes"], snapshot["disk_total_bytes"] = free, free * 2
    snapshot["disk_used_bytes"] = free
    return sources, snapshot, grew.analyse(snapshot, now, cfg)


def _by_path(rows) -> dict:
    return dict((r["path"], r) for r in rows)


class TestTheFirstRun(unittest.TestCase):
    """It has nothing to compare against. It must say so, write the baseline, and invent nothing."""

    def test_it_refuses_to_print_a_delta_and_says_when_to_come_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "home"
            out = Path(tmp) / "out"
            _file(root / "Documents" / "a.bin", 200)

            sources, snapshot, view = _run(out, root, NOW)
            self.assertTrue(sources[0].found)
            self.assertTrue(view["first_run"])
            self.assertIsNone(view["delta"], "a first run has no delta and must not fake one")
            self.assertEqual(view["net_bytes"], 0)
            self.assertEqual((view["grew"], view["appeared"], view["shrank"], view["deleted"]),
                             ([], [], [], []))
            self.assertIsNone(view["rate_bytes_per_day"])
            self.assertIsNone(view["projection"])
            self.assertIn("first run", view["first_run_note"].lower())
            self.assertIn("tomorrow", view["first_run_note"].lower())
            self.assertIn("first run", view["since_note"].lower())

            card = grew.render(view, {"color": False})
            self.assertIn("First run", card)
            self.assertIn("baseline", card)
            self.assertNotIn("±0 B", card, "a zero delta must never be shown on a first run")
            self.assertIn("First run", grew.report_markdown(view, {}, [s.__dict__ for s in sources]))

    def test_the_baseline_is_written_so_the_next_run_has_something_to_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "Documents" / "a.bin", 200)
            _run(out, root, NOW)
            self.assertTrue((out / ".{0}-baseline.json".format(grew.NAME)).is_file())
            history = json.loads((out / ".{0}-baseline.json".format(grew.HISTORY)).read_text())
            self.assertEqual(len(history["payload"]["runs"]), 1)
            self.assertEqual(history["payload"]["runs"][0]["captured"], "2026-09-05T12:00:00Z")

    def test_a_run_that_read_nothing_writes_no_baseline_at_all(self):
        """A zero snapshot recorded as a baseline would report the whole disk as gone tomorrow."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            sources, snapshot, view = _run(out, Path(tmp) / "nothing-here", NOW)
            self.assertFalse(sources[0].found)
            self.assertIn("no folder", sources[0].note)
            self.assertFalse(view["readable"])
            self.assertFalse((out / ".{0}-baseline.json".format(grew.NAME)).exists())
            grew.render(view, {})          # must not raise
            grew.report_markdown(view, {}, [s.__dict__ for s in sources])


class TestTheThreeClasses(unittest.TestCase):
    """Grew, appeared and deleted are different events. So is shrank. None of them may be merged."""

    def _tree(self, tmp) -> tuple:
        root, out = Path(tmp) / "home", Path(tmp) / "out"
        _file(root / "keep" / "big.bin", 400)
        _file(root / "steady" / "same.bin", 200)
        _file(root / "gone" / "old.bin", 300)
        _run(out, root, NOW)
        return root, out

    def _mutate(self, root):
        _file(root / "keep" / "big.bin", 900)                       # grew in place
        _file(root / "steady" / "same.bin", 20)                     # shrank in place
        _file(root / "fresh" / "node_modules" / "lib.bin", 500)     # newly appeared
        shutil.rmtree(str(root / "gone"))                           # deleted

    def test_every_class_is_reported_separately_and_with_the_right_sign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self._tree(tmp)
            self._mutate(root)
            _, _, view = _run(out, root, LATER)

            self.assertFalse(view["first_run"])
            self.assertEqual(view["compared_with"], "2026-09-05T12:00:00Z")
            self.assertEqual(view["elapsed_days"], 7.0)

            grew_rows, appeared, shrank, deleted = (_by_path(view["grew"]), _by_path(view["appeared"]),
                                                    _by_path(view["shrank"]), _by_path(view["deleted"]))
            self.assertIn("keep", grew_rows)
            self.assertIn("fresh/node_modules", appeared)
            self.assertIn("steady", shrank)
            self.assertIn("gone", deleted)

            self.assertGreater(grew_rows["keep"]["change"], 450 * KB)
            self.assertGreater(appeared["fresh/node_modules"]["change"], 450 * KB)
            self.assertLess(shrank["steady"]["change"], -150 * KB)
            self.assertLess(deleted["gone"]["change"], -250 * KB)
            self.assertEqual(deleted["gone"]["bytes"], 0, "a deleted folder holds nothing now")

            for a, b in ((grew_rows, appeared), (grew_rows, shrank), (grew_rows, deleted),
                         (appeared, shrank), (appeared, deleted), (shrank, deleted)):
                self.assertFalse(set(a) & set(b), "a folder may only be in one class")

            self.assertGreater(view["net_bytes"], 0)
            self.assertIn("+", view["net_size"])
            self.assertEqual(view["delta"]["first_run"], False)
            self.assertIn("keep", view["delta"]["grew"])
            self.assertIn("gone", view["delta"]["removed"])
            self.assertIn("fresh/node_modules", view["delta"]["added"])
            self.assertIn("steady", view["delta"]["shrank"])

    def test_shrinkage_is_never_dropped_even_when_the_disk_grew_overall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self._tree(tmp)
            self._mutate(root)
            _, _, view = _run(out, root, LATER)
            self.assertLess(view["shrank_bytes"], 0)
            self.assertLess(view["deleted_bytes"], 0)
            self.assertTrue(view["shrinkers"], "the headline must be able to name what shrank")
            self.assertIn("Shrunk:", view["headline"])
            self.assertNotIn("Shrunk: nothing", view["headline"])
            md = grew.report_markdown(view, {}, [])
            self.assertIn("## Shrank in place", md)
            self.assertIn("## Deleted", md)

    def test_a_disk_that_only_shrank_says_so_rather_than_reporting_no_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self._tree(tmp)
            shutil.rmtree(str(root / "gone"))
            _file(root / "keep" / "big.bin", 10)
            _, _, view = _run(out, root, LATER)
            self.assertLess(view["net_bytes"], 0)
            self.assertTrue(view["net_size"].startswith("-"))
            self.assertEqual(view["grew"], [])
            self.assertIsNone(view["projection"], "a shrinking disk gets no fill date")
            self.assertIn("Shrunk:", view["headline"])


class TestDepthRollup(unittest.TestCase):
    def test_everything_below_the_configured_depth_is_summarised_at_that_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "a" / "b" / "c" / "d" / "deep.bin", 120)
            _file(root / "a" / "b" / "shallow.bin", 60)
            _, snapshot, _ = _run(out, root, NOW, depth=2)
            self.assertEqual(sorted(snapshot["dirs"]), ["a/b"])
            self.assertGreater(snapshot["dirs"]["a/b"], 170 * KB)

    def test_a_deeper_setting_names_the_deeper_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "a" / "b" / "c" / "d" / "deep.bin", 120)
            _, snapshot, _ = _run(out, root, NOW, depth=4)
            self.assertEqual(sorted(snapshot["dirs"]), ["a/b/c/d"])

    def test_a_file_in_the_root_itself_is_kept_under_a_dot_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "loose.bin", 40)
            _, snapshot, _ = _run(out, root, NOW)
            self.assertIn(".", snapshot["dirs"])

    def test_the_floor_folds_small_folders_into_one_total_that_still_reconciles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "big" / "x.bin", 400)
            _file(root / "small" / "y.bin", 8)
            _, snapshot, _ = _run(out, root, NOW, floor_bytes=100 * KB)
            self.assertEqual(sorted(snapshot["dirs"]), ["big"])
            self.assertGreater(snapshot["other_bytes"], 0)
            self.assertEqual(snapshot["total_bytes"],
                             sum(snapshot["dirs"].values()) + snapshot["other_bytes"])


class TestKnownHogs(unittest.TestCase):
    def test_the_table_only_ever_gives_one_of_the_three_verdicts(self):
        for hog in grew.HOGS:
            self.assertIn(hog["verdict"], grew.VERDICTS, hog["name"])
            self.assertIn(hog["kind"], ("prefix", "segment", "contains"), hog["name"])
            self.assertTrue(hog["how"], hog["name"])

    def test_every_hog_the_play_promises_is_classified(self):
        expected = {
            "Projects/app/node_modules": ("node_modules", "regenerable"),
            "Projects/app/.venv": ("virtualenv", "regenerable"),
            "Projects/app/venv": ("virtualenv", "regenerable"),
            "Projects/rust/target": ("build output", "regenerable"),
            "Projects/app/build": ("build output", "regenerable"),
            "Projects/app/dist": ("build output", "regenerable"),
            "Projects/web/.next": ("Next.js build", "regenerable"),
            "Projects/py/__pycache__": ("bytecode cache", "regenerable"),
            "Library/Developer/Xcode/DerivedData": ("Xcode DerivedData", "regenerable"),
            "Library/Developer/CoreSimulator": ("Simulator runtimes", "think first"),
            "Library/Developer/Xcode/Archives": ("Xcode archives", "think first"),
            "Library/Developer/Xcode/iOS DeviceSupport": ("iOS device support", "safe to delete"),
            "Library/Containers/com.docker.docker/Data": ("Docker data", "think first"),
            "Library/Containers/com.docker.docker/Data/vms/0/Docker.raw":
                ("Docker disk image", "think first"),
            "Library/Caches/Homebrew": ("Homebrew cache", "safe to delete"),
            "Library/Caches/pip": ("pip cache", "safe to delete"),
            "Library/Caches/Yarn": ("yarn cache", "safe to delete"),
            "Library/Caches/Google/Chrome": ("browser cache", "safe to delete"),
            "Library/Caches/Firefox/Profiles": ("browser cache", "safe to delete"),
            "Library/pnpm/store/v3": ("pnpm store", "safe to delete"),
            ".npm/_cacache": ("npm cache", "safe to delete"),
            ".gradle/caches": ("Gradle cache", "regenerable"),
            ".m2/repository": ("Maven repository", "regenerable"),
            ".cargo/registry": ("Cargo registry", "regenerable"),
            "go/pkg/mod": ("Go module cache", "regenerable"),
        }
        for path, (name, verdict) in sorted(expected.items()):
            hog = grew.classify(path)
            self.assertIsNotNone(hog, "{0} should be a known hog".format(path))
            self.assertEqual((hog["name"], hog["verdict"]), (name, verdict), path)

    def test_an_ordinary_folder_gets_no_verdict_at_all(self):
        for path in ("Documents/tax", "Pictures/2024", "Music", ".", ""):
            self.assertIsNone(grew.classify(path), path)

    def test_the_reclaim_number_is_regenerable_bytes_and_excludes_irreplaceable_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "Projects" / "app" / "node_modules" / "dep.bin", 400)
            _file(root / "Library" / "Caches" / "Homebrew" / "bottle.bin", 200)
            _file(root / "Library" / "Developer" / "CoreSimulator" / "device.bin", 300)
            _file(root / "Documents" / "irreplaceable.bin", 500)
            _, _, view = _run(out, root, NOW)

            self.assertGreater(view["regenerable_bytes"], 380 * KB)
            self.assertLess(view["regenerable_bytes"], 460 * KB, "only node_modules is regenerable")
            self.assertGreater(view["safe_bytes"], 180 * KB)
            self.assertGreater(view["think_bytes"], 280 * KB)
            self.assertGreater(view["irreplaceable_bytes"], 480 * KB)
            self.assertEqual(view["reclaim_bytes"], view["regenerable_bytes"] + view["safe_bytes"])
            self.assertNotIn("Documents", [h["path"] for h in view["hogs"]])
            self.assertEqual(view["regenerable_bytes"] + view["safe_bytes"] + view["think_bytes"]
                             + view["irreplaceable_bytes"], view["total_bytes"])
            self.assertEqual([x["verdict"] for x in view["verdicts"]], list(grew.VERDICTS))

    def test_the_growth_rows_carry_the_verdict_so_the_card_can_show_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "Documents" / "a.bin", 100)
            _run(out, root, NOW)
            _file(root / "Projects" / "app" / "node_modules" / "dep.bin", 600)
            _, _, view = _run(out, root, LATER)
            row = _by_path(view["appeared"])["Projects/app/node_modules"]
            self.assertEqual((row["hog"], row["verdict"]), ("node_modules", "regenerable"))
            self.assertTrue(view["movers"])
            self.assertIn("node_modules", view["headline"])

    def test_many_copies_of_one_hog_are_grouped_into_a_single_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "Documents" / "a.bin", 100)
            _run(out, root, NOW)
            for name in ("one", "two", "three"):
                _file(root / "Projects" / name / "node_modules" / "dep.bin", 200)
            _, _, view = _run(out, root, LATER)
            mover = view["movers"][0]
            self.assertEqual(mover["name"], "node_modules")
            self.assertEqual(mover["dirs"], 3)
            self.assertIn("across 3", mover["phrase"])


class TestPermissionDenied(unittest.TestCase):
    def test_a_folder_it_cannot_open_is_counted_and_named_not_skipped(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read anything, so nothing would be denied")
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "open" / "a.bin", 100)
            locked = root / "locked"
            _file(locked / "secret.bin", 200)
            os.chmod(str(locked), 0o000)
            try:
                _, snapshot, view = _run(out, root, NOW)
            finally:
                os.chmod(str(locked), 0o700)
            self.assertEqual(snapshot["denied_count"], 1)
            self.assertEqual(snapshot["denied"], ["locked"])
            self.assertEqual(view["denied"]["count"], 1)
            self.assertIn("locked", view["denied"]["paths"])
            self.assertIn("not skipped", view["denied"]["note"])
            self.assertTrue(any("could not be opened" in c for c in view["caveats"]))
            self.assertIn("could not be read", grew.render(view, {}))
            self.assertIn("could not be read", grew.report_markdown(view, {}, []))


class TestRateAndProjection(unittest.TestCase):
    def _grown(self, tmp, free_bytes):
        root, out = Path(tmp) / "home", Path(tmp) / "out"
        _file(root / "data" / "a.bin", 100)
        cfg = _cfg(out, root)
        sources, snapshot = grew.read_source("home", Budget(), cfg)
        snapshot["free_bytes"], snapshot["disk_total_bytes"] = free_bytes, free_bytes * 2
        snapshot["disk_used_bytes"] = free_bytes
        grew.analyse(snapshot, NOW, cfg)

        _file(root / "data" / "a.bin", 800)
        sources, snapshot = grew.read_source("home", Budget(), cfg)
        snapshot["free_bytes"], snapshot["disk_total_bytes"] = free_bytes, free_bytes * 2
        snapshot["disk_used_bytes"] = free_bytes
        return grew.analyse(snapshot, LATER, cfg)

    def test_the_rate_is_bytes_per_day_since_the_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._grown(tmp, 100 * KB * KB)
            self.assertAlmostEqual(view["rate_bytes_per_day"], view["net_bytes"] / 7.0, places=3)
            self.assertIn("/day", view["rate_note"])
            self.assertIn("two measurements", view["rate_note"])

    def test_the_projection_is_labelled_a_straight_line_and_not_a_forecast(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._grown(tmp, 100 * KB * KB)
            projection = view["projection"]
            self.assertIsNotNone(projection)
            self.assertIn("straight-line", projection["note"].lower())
            self.assertIn("not a forecast", projection["note"].lower())
            self.assertEqual(projection["days"], int(view["free_bytes"] / view["rate_bytes_per_day"]))
            self.assertTrue(projection["date"])
            card = grew.render(view, {})
            self.assertIn("straight-line extrapolation", card.lower())
            self.assertIn("forecast", card.lower())

    def test_free_space_gives_every_number_a_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._grown(tmp, 100 * KB * KB)
            self.assertEqual(view["free_share"], 50)
            self.assertEqual(view["used_share"], 50)
            self.assertIn("free", grew.render(view, {}))

    def test_a_very_slow_fill_is_capped_rather_than_projected_to_a_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._grown(tmp, 400 * KB * KB * KB)
            self.assertTrue(view["projection"]["capped"])
            self.assertIsNone(view["projection"]["days"])
            self.assertIn("not a forecast", view["projection"]["note"].lower())

    def test_two_runs_in_the_same_minute_are_too_close_to_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 100)
            _run(out, root, NOW)
            _file(root / "data" / "b.bin", 100)
            _, _, view = _run(out, root, NOW + timedelta(minutes=1))
            self.assertIsNone(view["rate_bytes_per_day"])
            self.assertIn("too short", view["rate_note"])
            self.assertIsNone(view["projection"])


class TestRetainedBaselines(unittest.TestCase):
    def _five_runs(self, tmp, keep):
        root, out = Path(tmp) / "home", Path(tmp) / "out"
        views = []
        for i in range(5):
            _file(root / "data" / "a.bin", 100 * (i + 1))
            _, _, view = _run(out, root, NOW + timedelta(days=i), keep_baselines=keep)
            views.append(view)
        return root, out, views

    def test_only_the_newest_are_kept_and_the_older_ones_are_trimmed_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out, views = self._five_runs(tmp, 3)
            self.assertEqual(views[-1]["baselines_held"], 3)
            self.assertEqual([b["captured"] for b in views[-1]["baselines"]],
                             ["2026-09-07T12:00:00Z", "2026-09-08T12:00:00Z", "2026-09-09T12:00:00Z"])
            # Retention trims a list inside one file; it never removes a file from the disk.
            self.assertEqual(sorted(p.name for p in out.glob(".*baseline.json")),
                             sorted([".{0}-baseline.json".format(grew.HISTORY),
                                     ".{0}-baseline.json".format(grew.NAME)]))

    def test_since_selects_which_retained_baseline_to_compare_against(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out, _ = self._five_runs(tmp, 3)
            _file(root / "data" / "a.bin", 900)
            last = NOW + timedelta(days=5)

            _, _, latest = _run(out, root, last)
            _, _, oldest = _run(out, root, last, since="oldest")
            _, _, two_back = _run(out, root, last, since="2")
            _, _, a_week = _run(out, root, last, since="7d")
            _, _, by_date = _run(out, root, last, since="2026-09-07")

            self.assertEqual(latest["compared_with"], "2026-09-09T12:00:00Z")
            self.assertEqual(latest["since_label"], "the last run")
            self.assertEqual(oldest["compared_with"], "2026-09-07T12:00:00Z")
            self.assertEqual(two_back["compared_with"], "2026-09-07T12:00:00Z")
            self.assertEqual(by_date["compared_with"], "2026-09-07T12:00:00Z")
            self.assertEqual(a_week["compared_with"], "2026-09-07T12:00:00Z")
            self.assertIn("oldest retained", a_week["since_label"])
            self.assertGreater(oldest["net_bytes"], latest["net_bytes"],
                               "a longer window must show more growth")
            self.assertEqual(oldest["elapsed_days"], 3.0)
            self.assertEqual(latest["elapsed_days"], 1.0)

    def test_a_baseline_captured_at_or_after_now_is_never_the_comparison(self):
        """Running twice in one minute must not reset the comparison to zero."""
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 100)
            _run(out, root, LATER)
            _, _, second = _run(out, root, LATER)
            self.assertTrue(second["first_run"], "the run it just wrote is not a comparison point")
            _, _, third = _run(out, root, LATER + timedelta(days=1))
            self.assertFalse(third["first_run"])
            self.assertEqual(third["compared_with"], "2026-09-12T12:00:00Z")


class TestDegradedInputs(unittest.TestCase):
    def test_a_schema_bump_degrades_to_a_first_run_rather_than_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 100)
            _run(out, root, NOW)
            for name in (grew.NAME, grew.HISTORY):
                path = out / ".{0}-baseline.json".format(name)
                doc = json.loads(path.read_text())
                doc["schema"] = 999
                path.write_text(json.dumps(doc))

            _file(root / "data" / "b.bin", 100)
            _, _, view = _run(out, root, LATER)
            self.assertTrue(view["first_run"])
            self.assertIsNone(view["delta"])
            self.assertIn("first run", view["first_run_note"].lower())
            reread = json.loads((out / ".{0}-baseline.json".format(grew.HISTORY)).read_text())
            self.assertEqual(reread["schema"], 1, "the new baseline is written at the current schema")

    def test_an_unreadable_history_file_is_a_first_run_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 100)
            out.mkdir(parents=True, exist_ok=True)
            (out / ".{0}-baseline.json".format(grew.HISTORY)).write_text("{not json")
            _, _, view = _run(out, root, NOW)
            self.assertTrue(view["first_run"])

    def test_a_single_old_style_baseline_seeds_the_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 100)
            _run(out, root, NOW)
            (out / ".{0}-baseline.json".format(grew.HISTORY)).unlink()
            _file(root / "data" / "b.bin", 100)
            _, _, view = _run(out, root, LATER)
            self.assertFalse(view["first_run"], "the current baseline is still a comparison point")
            self.assertEqual(view["compared_with"], "2026-09-05T12:00:00Z")

    def test_an_empty_root_is_measured_as_nothing_rather_than_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            root.mkdir()
            sources, snapshot, view = _run(out, root, NOW)
            self.assertTrue(sources[0].found)
            self.assertEqual(snapshot["total_bytes"], 0)
            self.assertTrue(view["first_run"])
            grew.render(view, {})

    def test_a_bound_that_was_hit_is_reported_as_a_lower_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            for i in range(6):
                _file(root / "data" / "f{0}.bin".format(i), 4)
            cfg = _cfg(out, root)
            sources, snapshot = grew.read_source("home", Budget(max_files=2), cfg)
            self.assertFalse(snapshot["complete"])
            self.assertIn("file count", snapshot["truncated"])
            view = grew.analyse(snapshot, NOW, cfg)
            self.assertTrue(any("lower bound" in c for c in view["caveats"]))
            self.assertIn("lower bound", grew.render(view, {}))
            self.assertIn("lower bound", grew.report_markdown(view, {}, []))


class TestExclusions(unittest.TestCase):
    def test_icloud_placeholders_are_excluded_and_counted_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "Documents" / "real.bin", 100)
            _file(root / "Documents" / ".big.pdf.icloud", 40)
            _, snapshot, view = _run(out, root, NOW)
            self.assertEqual(snapshot["placeholder_files"], 1)
            self.assertGreaterEqual(snapshot["placeholder_bytes"], 40 * KB)
            self.assertLess(snapshot["total_bytes"], 140 * KB)
            self.assertTrue(any("iCloud" in c for c in view["caveats"]))
            self.assertIn("iCloud", view["excluded"]["note"])

    def test_a_volumes_folder_is_never_descended_into(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "Documents" / "real.bin", 100)
            _file(root / "Volumes" / "backup" / "huge.bin", 400)
            _, snapshot, view = _run(out, root, NOW)
            self.assertNotIn("Volumes", snapshot["dirs"])
            self.assertIn("Volumes", snapshot["excluded"]["system"])
            self.assertLess(snapshot["total_bytes"], 200 * KB)
            self.assertIn("/Volumes", view["excluded"]["note"])

    def test_a_symlink_out_of_the_tree_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            outside = Path(tmp) / "elsewhere"
            _file(outside / "huge.bin", 400)
            _file(root / "Documents" / "real.bin", 100)
            os.symlink(str(outside), str(root / "link"))
            _, snapshot, _ = _run(out, root, NOW)
            self.assertNotIn("link", snapshot["dirs"])
            self.assertLess(snapshot["total_bytes"], 200 * KB)


class TestApfsAwareness(unittest.TestCase):
    def test_the_on_disk_size_is_used_where_the_filesystem_reports_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 200)
            _, snapshot, view = _run(out, root, NOW)
            if not snapshot["on_disk_sizes"]:
                self.skipTest("this filesystem reports no block counts")
            self.assertTrue(any("on-disk" in c for c in view["caveats"]))
            self.assertGreater(snapshot["apparent_bytes"], 0)
            self.assertLess(abs(snapshot["total_bytes"] - snapshot["apparent_bytes"]), 64 * KB)

    def test_a_sparse_file_counts_what_it_occupies_not_what_it_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            (root / "data").mkdir(parents=True)
            with open(str(root / "data" / "sparse.bin"), "wb") as fh:
                fh.truncate(64 * KB * KB)          # 64 MB of nothing
            _file(root / "data" / "real.bin", 100)
            _, snapshot, _ = _run(out, root, NOW)
            if not snapshot["on_disk_sizes"]:
                self.skipTest("this filesystem reports no block counts")
            if snapshot["total_bytes"] > 4 * KB * KB:
                self.skipTest("this filesystem allocated the hole instead of leaving it sparse")
            self.assertGreater(snapshot["apparent_bytes"], 60 * KB * KB)
            self.assertLess(snapshot["total_bytes"], 4 * KB * KB,
                            "a hole on disk must not be charged as bytes")


class TestDemoFixture(unittest.TestCase):
    def test_the_demo_reads_a_bundled_manifest_instead_of_a_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture, out = Path(tmp) / "fixture", Path(tmp) / "out"
            fixture.mkdir()
            (fixture / "sizes.json").write_text(json.dumps({
                "root": "/Users/demo", "depth": 4, "floor_bytes": 0,
                "dirs": {"Projects/app/node_modules": 9 * KB * KB * KB,
                         "Library/Developer/CoreSimulator": 14 * KB * KB * KB,
                         "Documents/tax": 2 * KB * KB * KB},
                "other_bytes": 0, "files": 40000, "free_bytes": 80 * KB * KB * KB,
                "disk_total_bytes": 500 * KB * KB * KB, "denied": ["Library/Application Support/x"],
            }), encoding="utf-8")
            sources, snapshot, view = _run(out, "/nonexistent", NOW, demo_root=str(fixture))
            self.assertTrue(sources[0].found)
            self.assertIn("demo", sources[0].name)
            self.assertEqual(snapshot["dirs_kept"], 3)
            self.assertEqual(view["denied"]["count"], 1)
            self.assertEqual(view["regenerable_bytes"], 9 * KB * KB * KB)
            self.assertEqual(view["think_bytes"], 14 * KB * KB * KB)
            self.assertTrue(view["first_run"])

    def test_a_missing_fixture_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, snapshot, view = _run(Path(tmp) / "out", "/nonexistent", NOW,
                                           demo_root=str(Path(tmp) / "absent"))
            self.assertFalse(sources[0].found)
            self.assertFalse(snapshot["readable"])
            self.assertFalse(view["readable"])


class TestReadOnly(unittest.TestCase):
    SOURCE = Path("daily_core/scan/grew.py").read_text(encoding="utf-8")

    def test_the_module_contains_nothing_that_could_delete_a_file(self):
        for banned in ("os.remove", "os.unlink", "shutil.rmtree", "os.rmdir", ".unlink(",
                       "shutil.move", "os.rename", "os.replace", "os.truncate", "os.chmod"):
            self.assertNotIn(banned, self.SOURCE, "grew.py must never {0}".format(banned))

    def test_the_module_opens_nothing_for_writing_and_shells_out_to_nothing(self):
        for banned in ("subprocess", "os.system", "popen", "urlopen", "socket"):
            self.assertNotIn(banned, self.SOURCE.lower(), banned)
        self.assertNotIn('open(', self.SOURCE.replace("os.scandir(", "").replace("_open(", ""),
                         "no file is ever opened by this module")

    def test_it_writes_only_through_the_shared_helper_under_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "data" / "a.bin", 100)
            before = sorted(p.name for p in (root).rglob("*"))
            _run(out, root, NOW)
            self.assertEqual(sorted(p.name for p in (root).rglob("*")), before,
                             "the scanned tree must be untouched")
            self.assertTrue(all(p.name.startswith(".") for p in out.iterdir()))


class TestDeterminism(unittest.TestCase):
    def _view_json(self, view) -> str:
        return json.dumps(view, sort_keys=True, default=str)

    def test_the_same_tree_and_the_same_now_give_the_same_answer_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "keep" / "a.bin", 200)
            _file(root / "Projects" / "app" / "node_modules" / "b.bin", 300)
            _, _, first = _run_fixed(out, root, NOW)
            _, _, second = _run_fixed(out, root, NOW)
            self.assertEqual(self._view_json(first), self._view_json(second))
            self.assertEqual(grew.render(first, {}), grew.render(second, {}))

    def test_a_repeated_second_run_compares_against_the_same_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "keep" / "a.bin", 200)
            _run(out, root, NOW)
            _file(root / "keep" / "a.bin", 700)
            _, _, first = _run_fixed(out, root, LATER)
            _, _, second = _run_fixed(out, root, LATER)
            self.assertEqual(self._view_json(first), self._view_json(second))

    def test_two_out_dirs_over_one_tree_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "home"
            _file(root / "keep" / "a.bin", 200)
            _, _, a = _run_fixed(Path(tmp) / "out-a", root, NOW)
            _, _, b = _run_fixed(Path(tmp) / "out-b", root, NOW)
            self.assertEqual(self._view_json(a), self._view_json(b))

    def test_every_list_is_sorted_by_size_then_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            _file(root / "a" / "x.bin", 50)
            _run(out, root, NOW)
            for name, kb in (("b", 300), ("c", 200), ("d", 400)):
                _file(root / name / "x.bin", kb)
            _, _, view = _run(out, root, LATER)
            changes = [r["change"] for r in view["appeared"]]
            self.assertEqual(changes, sorted(changes, reverse=True))
            self.assertEqual([r["path"] for r in view["appeared"]][:3], ["d", "b", "c"])


class TestPresentation(unittest.TestCase):
    def _views(self, tmp) -> tuple:
        root, out = Path(tmp) / "home", Path(tmp) / "out"
        _file(root / "Documents" / "a.bin", 200)
        _file(root / "gone" / "b.bin", 100)
        _, _, first = _run_fixed(out, root, NOW)
        _file(root / "Projects" / "app" / "node_modules" / "dep.bin", 600)
        _file(root / "Documents" / "a.bin", 20)
        shutil.rmtree(str(root / "gone"))
        _, _, second = _run_fixed(out, root, LATER)
        return first, second

    def test_the_card_is_sixty_four_columns_in_both_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            for view in self._views(tmp):
                card = grew.render(view, {"color": False})
                for line in card.splitlines():
                    self.assertEqual(display_width(line), W, line)

    def test_the_card_names_every_class_it_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, view = self._views(tmp)
            card = grew.render(view, {"color": False})
            for heading in ("NEWLY APPEARED", "SHRANK", "DELETED", "WHAT YOU CAN GET BACK"):
                self.assertIn(heading, card)
            self.assertIn("regenerable", card)
            self.assertIn("Nothing was deleted", card)

    def test_the_markdown_reports_both_directions_and_states_the_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, view = self._views(tmp)
            md = grew.report_markdown(view, {}, [{"name": "home", "found": True, "note": "ok"}])
            for heading in ("## Newly appeared", "## Shrank in place", "## Deleted",
                            "## What you can get back", "## What was excluded", "## Caveats",
                            "## Retained baselines", "## Sources"):
                self.assertIn(heading, md)
            self.assertIn("/Volumes", md)
            self.assertIn("iCloud", md)
            self.assertIn("Read-only", md)

    def test_the_headline_leads_with_the_net_move_and_names_the_hogs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, view = self._views(tmp)
            self.assertTrue(view["headline"].startswith("Since "))
            self.assertIn("node_modules", view["headline"])
            self.assertIn("Shrunk:", view["headline"])

    def test_a_generic_folder_name_borrows_from_its_parent_until_it_identifies_something(self):
        self.assertEqual(grew._leaf("Projects/calendar/.git/objects"), "calendar/.git/objects")
        self.assertEqual(grew._leaf("Projects/app/.turbo/cache"), "app/.turbo/cache")
        self.assertEqual(grew._leaf("Pictures/2024-holiday"), "2024-holiday")
        self.assertEqual(grew._leaf("."), "the root folder")

    def test_a_truncated_walk_says_so_on_the_card_after_a_comparison_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "home", Path(tmp) / "out"
            for i in range(8):
                _file(root / "data" / "f{0}.bin".format(i), 4)
            _run(out, root, NOW)
            _file(root / "data" / "big.bin", 200)
            cfg = _cfg(out, root)
            _, snapshot = grew.read_source("home", Budget(max_files=4), cfg)
            view = grew.analyse(snapshot, LATER, cfg)
            self.assertFalse(view["complete"])
            self.assertIn("lower bound", grew.render(view, {}))

    def test_signed_sizes_never_hide_the_direction(self):
        self.assertEqual(grew.signed(0), "±0 B")
        self.assertTrue(grew.signed(5 * KB * KB).startswith("+"))
        self.assertTrue(grew.signed(-5 * KB * KB).startswith("-"))


if __name__ == "__main__":
    unittest.main()
