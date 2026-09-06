"""The ten pulse Plays, driven through the real CLI the way a Play step drives it.

The scan modules have their own suites; this one owns the wiring. For every Play it asserts the
same six things, because these are the six ways a wired-up verb goes wrong in practice:

  * a read step exits 0 and leaves a partial behind even when its source is not on this machine,
    which is what lets a Play fan its reads out and pay for a missing browser only once;
  * a report step exits 0, writes `<play>.md` and `<play>.json` under out_dir and prints a card;
  * a report step run with no partials says "run the read step first" rather than raising;
  * every flag the parser registers is accepted by the function behind it;
  * `--now` is honoured, so two runs at the same instant produce byte-identical markdown;
  * a Play's own baseline file is never swept up by its own partial glob.

The fixtures are written by the tests rather than taken from the bundled fixture folder: these
ten Plays have no bundled fixtures yet, and a test that skipped when one was missing would assert
nothing at all on the machine that matters.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daily_core import cli
from daily_core.common import iso

NOW_TEXT = "2026-09-05T12:00:00+00:00"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def run(argv):
    """The real CLI. Returns (exit code, everything printed, the last JSON line as a dict)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(list(argv))
    text = buf.getvalue()
    lines = [line for line in text.splitlines() if line.strip()]
    return code, text, json.loads(lines[-1]) if lines else {}


def stamp(days_ago=0, hour=9):
    return (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0,
                                                    microsecond=0).isoformat()


def unix(days_ago=0):
    return int((NOW - timedelta(days=days_ago)).timestamp())


class PlayCase(unittest.TestCase):
    """One temporary out_dir and one temporary fixture folder per test.

    `play` is the report's file name, `prefix` the partial glob the report merges, and `verb` the
    stem of the two subcommands. Subclasses supply the flags and the fixture.
    """

    play = ""
    prefix = ""
    verb = ""
    reads = ()          # (extra argv, ...) one per read verb this Play runs
    report_args = ()

    def setUp(self):
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.tmp = Path(box.name)
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.demo_root = self.tmp / "fixture"
        self.demo_root.mkdir()

    # -- helpers -------------------------------------------------------

    def write_fixture(self, name, doc):
        path = self.demo_root / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def base(self):
        return ["--out-dir", str(self.out), "--now", NOW_TEXT]

    def demo(self):
        return ["--demo", "true", "--demo-root", str(self.demo_root)]

    def partials(self):
        return sorted(p.name for p in self.out.glob(".{0}-*.json".format(self.prefix)))

    def read_all(self, extra=()):
        for argv in (self.reads or ((),)):
            code, text, doc = run(["{0}-read".format(self.verb)] + self.base() +
                                  list(argv) + list(extra))
            self.assertEqual(code, 0, text)
            self.assertTrue(doc["ok"], doc)
        return self.partials()

    def report(self, extra=()):
        code, text, doc = run(["{0}-report".format(self.verb)] + self.base() +
                              list(self.report_args) + list(extra))
        self.assertEqual(code, 0, text)
        return text, doc

    def assert_card_and_files(self, text, doc):
        self.assertTrue(doc.get("ok"), doc)
        self.assertIn("┌", text, "the report should print a card")
        md = self.out / "{0}.md".format(self.play)
        js = self.out / "{0}.json".format(self.play)
        self.assertTrue(md.is_file(), "{0} was not written".format(md.name))
        self.assertTrue(js.is_file(), "{0} was not written".format(js.name))
        self.assertTrue(md.read_text(encoding="utf-8").strip())
        payload = json.loads(js.read_text(encoding="utf-8"))
        self.assertIn("view", payload)
        self.assertIn("sources", payload)
        self.assertEqual(payload["generated"], NOW.isoformat())
        self.assertTrue(any(str(md) == w for w in doc.get("written", [])), doc.get("written"))
        return md

    # -- the six shared assertions -------------------------------------

    def test_the_read_step_survives_a_source_that_is_not_here(self):
        """No fixture, no machine: still exit 0, still a partial, never an exception."""
        if not self.verb:
            return
        names = self.read_all(self.absent_args())
        self.assertTrue(names, "a read step must leave a partial even when it read nothing")

    def test_the_report_step_with_no_partials_asks_for_the_read_step(self):
        if not self.verb:
            return
        code, text, doc = run(["{0}-report".format(self.verb)] + self.base() +
                              list(self.report_args))
        self.assertEqual(code, 0, text)
        self.assertTrue(doc["ok"])
        self.assertTrue(doc["empty"])
        self.assertIn("run", doc["warning"])
        self.assertIn("read", doc["warning"])
        self.assertFalse((self.out / "{0}.md".format(self.play)).exists())

    def test_the_whole_pair_runs_against_the_fixture(self):
        if not self.verb:
            return
        self.build()
        self.read_all(self.demo_source())
        text, doc = self.report(self.demo_source_report())
        self.assert_card_and_files(text, doc)

    def test_the_same_now_gives_byte_identical_markdown(self):
        """Two cold runs at the same `--now` write the same bytes.

        The out_dir is emptied between them on purpose: leaving the first run's baseline behind
        would make the second run a comparison rather than a repeat, and the delta line it then
        prints is the correct answer, not a determinism bug.
        """
        if not self.verb:
            return
        self.build()
        name = "{0}.md".format(self.play)
        self.read_all(self.demo_source())
        self.report(self.demo_source_report())
        first = (self.out / name).read_bytes()
        for path in self.out.iterdir():
            if path.is_file():
                path.unlink()
        self.read_all(self.demo_source())
        self.report(self.demo_source_report())
        self.assertEqual(first, (self.out / name).read_bytes())

    def test_no_baseline_file_is_swept_into_the_partial_glob(self):
        """A baseline under out_dir must never be readable as a partial by this Play's own glob."""
        if not self.verb:
            return
        self.build()
        self.read_all(self.demo_source())
        self.report(self.demo_source_report())
        baselines = sorted(p.name for p in self.out.glob(".*-baseline.json"))
        for name in baselines:
            self.assertNotIn(name, self.partials(),
                             "{0} is picked up by the .{1}-* partial glob".format(name, self.prefix))

    # -- subclass hooks ------------------------------------------------

    def build(self):
        """Write whatever this Play needs to read. Default: nothing."""

    def absent_args(self):
        """Argv for "this source is not on the machine".

        Every root points somewhere that does not exist, on purpose: a test that fell back to a
        flag default would walk the real home directory, which is neither fast nor reproducible.
        """
        return ["--demo", "true", "--demo-root", str(self.tmp / "nowhere")]

    def demo_source(self):
        """Extra argv the read verbs need once `build` has run."""
        return self.demo()

    def demo_source_report(self):
        """Extra argv the report verb needs once `build` has run."""
        return []


# ================================================================ bus-factor

class TestBusFactor(PlayCase):
    play, prefix, verb = "bus-factor", "busfactor", "busfactor"
    reads = (["--source", "git"],)

    def build(self):
        self.write_fixture("repos.json", {"records": [
            {"repo": "acme", "path": "app/core.py", "commits": 4, "last": unix(10),
             "authors": [{"name": "Ada Lovelace", "email": "ada@example.com", "lines": 400,
                          "deleted": 10, "commits": 4, "last": unix(10), "first": unix(400)}]},
            {"repo": "acme", "path": "app/shared.py", "commits": 6, "last": unix(3),
             "authors": [{"name": "Ada Lovelace", "email": "ada@example.com", "lines": 120,
                          "deleted": 0, "commits": 3, "last": unix(3), "first": unix(300)},
                         {"name": "Grace Hopper", "email": "grace@example.com", "lines": 90,
                          "deleted": 4, "commits": 3, "last": unix(20), "first": unix(200)}]},
            {"repo": "acme", "path": "app/legacy.py", "commits": 1, "last": unix(900),
             "authors": [{"name": "Charles Babbage", "email": "charles@example.com", "lines": 700,
                          "deleted": 0, "commits": 1, "last": unix(900), "first": unix(900)}]},
            {"repo": "acme", "path": "node_modules/vendored.js", "commits": 1, "last": unix(5),
             "authors": [{"name": "Ada Lovelace", "email": "ada@example.com", "lines": 9000,
                          "deleted": 0, "commits": 1, "last": unix(5), "first": unix(5)}]},
        ]})

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["busfactor-read"] + self.base() + self.demo() +
                            ["--source", "git", "--root", str(self.tmp), "--max-repos", "3",
                             "--timeout", "5", "--max-files", "999", "--max-seconds", "30"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["busfactor-report"] + self.base() +
                              ["--departed-days", "120", "--stale-days", "200",
                               "--threshold", "0.6", "--color", "true", "--redact", "false",
                               "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_numbers_come_from_the_fixture(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertEqual(doc["tracked_files"], 3, "the vendored path is excluded")
        self.assertEqual(doc["sole_files"], 2)
        self.assertEqual(doc["authors"], 3)

    def test_a_repository_path_is_a_usable_partial_name(self):
        code, text, _ = run(["busfactor-read"] + self.base() +
                            ["--source", str(self.tmp / "no" / "such" / "repo")])
        self.assertEqual(code, 0, text)
        self.assertTrue(self.partials())
        for name in self.partials():
            self.assertNotIn("/", name)


# ================================================================ night-shift

class TestNightShift(PlayCase):
    play, prefix, verb = "night-shift", "nightshift", "nightshift"
    reads = (["--source", "commits"],)

    def build(self):
        rows = []
        for i in range(12):
            rows.append({"repo": "acme", "sha": "a{0:039d}".format(i), "name": "Ada",
                         "email": "ada@example.com",
                         "authored": stamp(days_ago=i * 2, hour=1 if i % 3 == 0 else 14),
                         "committed": stamp(days_ago=i * 2, hour=1 if i % 3 == 0 else 14),
                         "subject": "work {0}".format(i), "mine": True})
        rows.append({"repo": "acme", "sha": "b" * 40, "name": "Grace", "email": "g@example.com",
                     "authored": stamp(days_ago=4, hour=11), "committed": stamp(days_ago=4, hour=11),
                     "subject": 'Revert "work 2"', "mine": False})
        self.write_fixture("commits.json", rows)

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["nightshift-read"] + self.base() + self.demo() +
                            ["--source", "commits", "--root", str(self.tmp), "--days", "120",
                             "--emails", "ada@example.com,ada@work.example",
                             "--max-files", "500", "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["nightshift-report"] + self.base() +
                              ["--days", "120", "--late-hour", "22", "--dawn-hour", "6",
                               "--fixup-minutes", "45", "--aftermath-hours", "8",
                               "--color", "true", "--redact", "false", "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)
        self.assertEqual(doc["days"], 120)

    def test_the_late_commits_are_counted(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertGreater(doc["commits"], 0)
        self.assertGreater(doc["late"], 0)


# ================================================================ kept

class TestKept(PlayCase):
    play, prefix, verb = "kept", "keptread", "kept"
    reads = (["--source", "agent"], ["--source", "git"])

    FIXTURE = {"records": [
        {"kind": "edit", "session_id": "s1", "harness": "claude-code", "model": "claude-opus-5",
         "repo_hint": "/demo/acme", "path": "/demo/acme/a.py", "tool": "Write",
         "timestamp": "2026-09-01T10:00:00Z", "added": 40},
        {"kind": "repo", "path": "/demo/acme", "name": "acme", "head": "h", "shallow": False},
        {"kind": "own", "keys": ["ada@example.com"]},
        {"kind": "commits", "repo": "/demo/acme", "commits": [
            {"sha": "a" * 40, "at": "2026-09-01T10:05:00Z", "name": "Ada",
             "email": "ada@example.com", "subject": "agent work", "body": "",
             "files": [["a.py", 40, 0]]},
            {"sha": "b" * 40, "at": "2026-08-01T09:00:00Z", "name": "Ada",
             "email": "ada@example.com", "subject": "by hand", "body": "",
             "files": [["a.py", 25, 0]]}]},
        {"kind": "tracked", "repo": "/demo/acme", "paths": ["a.py"]},
        {"kind": "blame", "repo": "/demo/acme", "lines": {"a.py": (
            [["a" * 40, "2026-09-01T10:05:00Z", "ada@example.com"]] * 22 +
            [["b" * 40, "2026-08-01T09:00:00Z", "ada@example.com"]] * 25)}},
    ]}

    def build(self):
        self.write_fixture("kept.json", self.FIXTURE)

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["kept-read"] + self.base() + self.demo() +
                            ["--source", "agent", "--root", str(self.tmp), "--max-repos", "5",
                             "--claude-dir", str(self.tmp / "claude"),
                             "--codex-dir", str(self.tmp / "codex"),
                             "--pi-dir", str(self.tmp / "pi"),
                             "--max-files", "500", "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        run(["kept-read"] + self.base() + self.demo() + ["--source", "git"])
        code, text, doc = run(["kept-report"] + self.base() + self.demo() +
                              ["--grace-minutes", "15", "--min-lines", "0",
                               "--max-blame-files", "20", "--max-commits", "50",
                               "--max-seconds", "10", "--color", "true", "--redact", "false",
                               "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def demo_source_report(self):
        return self.demo()

    def test_the_survival_arithmetic_reaches_the_summary(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report(self.demo())
        self.assertEqual(doc["agent_ever"], 40)
        self.assertEqual(doc["agent_alive"], 22)
        self.assertEqual(doc["sessions"], 1)

    def test_the_kept_baseline_is_not_a_partial(self):
        """`.kept-baseline.json` would be swallowed by a `.kept-*` glob, so the prefix is not "kept"."""
        self.build()
        self.read_all(self.demo_source())
        self.report(self.demo())
        self.assertTrue((self.out / ".kept-baseline.json").is_file())
        self.assertNotIn(".kept-baseline.json", self.partials())
        self.assertEqual(cli._partials(str(self.out), "keptread"), cli._partials(str(self.out), "keptread"))
        self.assertTrue(all(d.get("records") is not None
                            for d in cli._partials(str(self.out), "keptread")))


# ================================================================ extension-reach

class TestExtensionReach(PlayCase):
    play, prefix, verb = "extension-reach", "extensions", "extensions"
    reads = (["--source", "chromium"], ["--source", "firefox"], ["--source", "safari"])

    MANIFEST = {"manifest_version": 3, "name": "Shopping Helper", "version": "4.2.0",
                "permissions": ["cookies", "webRequest", "scripting"],
                "host_permissions": ["<all_urls>"]}

    def build(self):
        """One real Chromium profile. This Play has no fixture format: it reads a tree or nothing."""
        self.roots = self.tmp / "Application Support"
        base = self.roots / "Google/Chrome/Default"
        ext = base / "Extensions" / ("a" * 32) / "4.2.0_0"
        ext.mkdir(parents=True)
        (ext / "manifest.json").write_text(json.dumps(self.MANIFEST), encoding="utf-8")
        old = (NOW - timedelta(days=500)).timestamp()
        os.utime(str(ext), (old, old))
        (base / "Secure Preferences").write_text(json.dumps({"extensions": {"settings": {
            "a" * 32: {"state": 1, "location": 1,
                       "active_permissions": {"api": ["cookies", "webRequest"],
                                              "explicit_host": ["<all_urls>"]}}}}}),
            encoding="utf-8")
        (base / "Preferences").write_text(json.dumps({"profile": {"name": "Default"}}),
                                          encoding="utf-8")

    def demo_source(self):
        return ["--roots", str(self.roots)]

    def absent_args(self):
        return ["--roots", str(self.tmp / "nowhere"), "--safari-roots", str(self.tmp / "nowhere")]

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["extensions-read"] + self.base() +
                            ["--source", "chromium", "--roots", str(self.roots),
                             "--safari-roots", str(self.tmp / "nothing"),
                             "--max-files", "5000", "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["extensions-report"] + self.base() +
                              ["--stale-days", "200", "--idle-days", "30", "--color", "true",
                               "--redact", "false", "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_profile_is_read_and_tiered(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertEqual(doc["extensions"], 1)
        self.assertEqual(doc["all_urls"], 1)
        self.assertEqual(doc["blanket"], 1)

    def test_the_reach_baseline_is_written_after_the_delta_is_taken(self):
        self.build()
        self.read_all(self.demo_source())
        self.report()
        self.assertTrue((self.out / ".extension-reach-baseline.json").is_file())


# ================================================================ where-it-went

class TestWhereItWent(PlayCase):
    play, prefix, verb = "where-it-went", "history", "history"
    reads = (["--source", "chromium"], ["--source", "firefox"], ["--source", "safari"])

    def build(self):
        visits = []
        for i in range(30):
            visits.append({"url": "https://github.com/acme/repo/pull/{0}".format(i),
                           "title": "PR {0}".format(i), "when": stamp(days_ago=i, hour=10),
                           "family": "chromium", "browser": "Chrome", "transition": "typed"})
            visits.append({"url": "https://news.ycombinator.com/item?id={0}".format(i),
                           "title": "thread", "when": stamp(days_ago=i, hour=21),
                           "family": "chromium", "browser": "Chrome", "transition": "linked"})
        visits.append({"url": "https://www.google.com/search?q=how+to+sleep", "title": "search",
                       "when": stamp(days_ago=2, hour=23), "family": "firefox",
                       "browser": "Firefox", "transition": "typed"})
        self.write_fixture("browser-history.json", {"visits": visits})

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["history-read"] + self.base() + self.demo() +
                            ["--source", "chromium", "--days", "120",
                             "--max-files", "5000", "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["history-report"] + self.base() +
                              ["--days", "120", "--gap-minutes", "45", "--top", "3",
                               "--tz", "utc", "--color", "true", "--redact", "false",
                               "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_visits_are_counted_and_categorised(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertGreater(doc["visits"], 0)
        self.assertGreater(doc["domains"], 0)

    def test_the_baseline_the_module_does_not_write_is_written_here(self):
        self.build()
        self.read_all(self.demo_source())
        self.report()
        path = self.out / ".where-it-went-baseline.json"
        self.assertTrue(path.is_file())
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["captured"], iso(NOW))
        self.assertTrue(doc["payload"])


# ================================================================ photo-debt

class TestPhotoDebt(PlayCase):
    play, prefix, verb = "photo-debt", "photos", "photos"
    reads = (["--source", "photos"], ["--source", "folder"])

    def build(self):
        rows = []
        for i in range(6):
            rows.append({"id": "asset{0}".format(i), "filename": "IMG_{0:04d}.HEIC".format(i),
                         "stem": "IMG_{0:04d}".format(i), "ext": ".heic",
                         "dir": "/demo", "path": "/demo/IMG_{0:04d}.HEIC".format(i),
                         "captured": stamp(days_ago=30 + i), "added": stamp(days_ago=30 + i),
                         "bytes": 2400000, "width": 4032, "height": 3024,
                         "sha256": "dupe" if i < 3 else "u{0}".format(i)})
        rows.append({"id": "shot", "filename": "Screenshot 2026-08-01.png", "stem": "Screenshot",
                     "ext": ".png", "dir": "/demo", "path": "/demo/Screenshot.png",
                     "captured": stamp(days_ago=200), "added": stamp(days_ago=200),
                     "bytes": 400000, "screenshot": True, "sha256": "shot"})
        self.write_fixture("assets.json", rows)

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["photos-read"] + self.base() + self.demo() +
                            ["--source", "photos", "--library", str(self.tmp / "lib"),
                             "--root", str(self.tmp / "pics"),
                             "--max-files", "5000", "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["photos-report"] + self.base() +
                              ["--burst-window", "3", "--screenshot-days", "45", "--top", "2",
                               "--hash-dupes", "false", "--color", "true", "--redact", "false",
                               "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_assets_reach_the_summary(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertEqual(doc["assets"], 7)
        self.assertEqual(doc["screenshots"], 1)

    def test_the_baseline_the_module_does_not_write_is_written_here(self):
        self.build()
        self.read_all(self.demo_source())
        self.report()
        self.assertTrue((self.out / ".photo-debt-baseline.json").is_file())


# ================================================================ what-grew

class TestWhatGrew(PlayCase):
    play, prefix, verb = "what-grew", "grewsnap", "grew"
    reads = (["--source", "home"],)

    def build(self):
        self.write_fixture("sizes.json", {
            "root": "/Users/demo", "depth": 4, "floor_bytes": 16 * 1024 * 1024,
            "dirs": {"/Users/demo/Library/Caches": 8 * 10 ** 9,
                     "/Users/demo/Projects/node_modules": 4 * 10 ** 9,
                     "/Users/demo/Downloads": 2 * 10 ** 9,
                     "/Users/demo/Pictures": 30 * 10 ** 9},
            "other_bytes": 10 ** 9, "total_bytes": 45 * 10 ** 9, "apparent_bytes": 45 * 10 ** 9,
            "files": 412000, "free_bytes": 60 * 10 ** 9, "disk_total_bytes": 500 * 10 ** 9,
        })

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["grew-read"] + self.base() + self.demo() +
                            ["--source", "home", "--root", str(self.tmp), "--depth", "3",
                             "--floor-bytes", "1048576", "--max-files", "50000",
                             "--max-seconds", "20"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["grew-report"] + self.base() +
                              ["--since", "last", "--keep-baselines", "4",
                               "--write-baseline", "true", "--color", "true",
                               "--redact", "false", "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_default_file_bound_is_large_enough_for_a_home_directory(self):
        """This Play opens nothing it measures, so its bound counts directory entries, not reads."""
        parser = cli.build_parser()
        args = parser.parse_args(["grew-read", "--out-dir", str(self.out)])
        self.assertEqual(int(args.max_files), 2000000)
        other = parser.parse_args(["clutter-read", "--source", "desktop", "--out-dir", str(self.out)])
        self.assertGreater(int(args.max_files), int(other.max_files))

    def test_its_own_baselines_are_not_read_back_as_partials(self):
        """The trap: `.whatgrew-baseline.json` and its history file live in the same out_dir."""
        self.build()
        self.read_all(self.demo_source())
        self.report()
        self.assertTrue((self.out / ".whatgrew-baseline.json").is_file())
        self.assertTrue((self.out / ".whatgrew-history-baseline.json").is_file())
        self.assertEqual(self.partials(), [".grewsnap-home.json"])
        for doc in cli._partials(str(self.out), self.prefix):
            self.assertIn("snapshot", doc)
        # The prefix that was rejected, and exactly why: both baselines answer to `.whatgrew-*`,
        # so a read step writing under that prefix would feed them back in as fresh readings.
        swallowed = cli._partials(str(self.out), "whatgrew")
        self.assertEqual(len(swallowed), 2)
        self.assertTrue(all("snapshot" not in d for d in swallowed))

    def test_the_module_keeps_its_own_baseline_and_the_cli_writes_no_second_one(self):
        """`analyse` retains the snapshot itself, so the report step must not write another."""
        self.build()
        self.read_all(self.demo_source())
        self.report()
        self.assertFalse((self.out / ".what-grew-baseline.json").exists())
        history = json.loads((self.out / ".whatgrew-history-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(len(history["payload"]["runs"]), 1)
        self.report()   # the same --now replaces that run rather than stacking a duplicate on it
        again = json.loads((self.out / ".whatgrew-history-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(len(again["payload"]["runs"]), 1)
        self.assertEqual(history, again)

    def test_the_snapshot_reaches_the_summary(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertEqual(doc["total_bytes"], 45 * 10 ** 9)
        self.assertEqual(doc["dirs_named"], 4)
        self.assertTrue(doc["first_run"])

    def test_a_run_that_read_nothing_still_reports(self):
        self.read_all(self.absent_args())
        text, doc = self.report()
        self.assert_card_and_files(text, doc)
        self.assertTrue(doc.get("empty"))


# ================================================================ standing-cost

class TestStandingCost(PlayCase):
    play, prefix, verb = "standing-cost", "standingcost", "standingcost"
    reads = (["--source", "calendar"],)

    def build(self):
        events = []
        for i in range(10):
            start = NOW - timedelta(days=7 * (10 - i))
            start = start.replace(hour=9, minute=0, second=0, microsecond=0)
            events.append({
                "id": "standup-{0:03d}".format(i), "recurring_event_id": "standup",
                "summary": "Monday Standup", "start": start.isoformat(),
                "end": (start + timedelta(minutes=30)).isoformat(), "status": "confirmed",
                "organizer": "alice@example.com",
                "attendees": [{"email": "alice@example.com", "response_status": "accepted",
                               "self": True, "display_name": "Alice Example"},
                              {"email": "bob@example.com", "response_status": "accepted",
                               "display_name": "Bob Example"},
                              {"email": "cara@example.com", "response_status": "needsAction",
                               "display_name": "Cara Example"}]})
        self.write_fixture("calendar.json", {"schema": 1, "source": "google-calendar",
                                             "account": "work", "timezone": "Europe/London",
                                             "events": events})

    def demo_source_report(self):
        return self.demo()

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["standingcost-read"] + self.base() + self.demo() +
                            ["--source", "calendar", "--partial", ".standing-cost-calendar.json",
                             "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["standingcost-report"] + self.base() + self.demo() +
                              ["--source", "calendar", "--days", "200",
                               "--focus-block-minutes", "60", "--currency", "$",
                               "--hourly-rate", "90", "--self", "alice@example.com",
                               "--max-seconds", "10", "--color", "true", "--redact", "false",
                               "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_read_step_reads_the_file_the_typescript_step_left(self):
        """No demo, no fetch: the partial under out_dir is the only thing this half ever opens."""
        self.build()
        doc = json.loads((self.demo_root / "calendar.json").read_text(encoding="utf-8"))
        (self.out / ".standing-cost-calendar.json").write_text(json.dumps(doc), encoding="utf-8")
        code, text, envelope = run(["standingcost-read"] + self.base())
        self.assertEqual(code, 0, text)
        self.assertEqual(envelope["events"], 10)
        text, summary = self.report()
        self.assert_card_and_files(text, summary)

    def test_the_person_hours_reach_the_summary(self):
        """Ten half-hour occurrences, two people who accepted and one who never answered."""
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report(self.demo())
        self.assertEqual(doc["occurrences"], 10)
        self.assertEqual(doc["series"], 1)
        self.assertEqual(doc["person_hours"], 10.0)
        self.assertFalse(doc["rate_set"], "no rate was given, so no money may be claimed")

    def test_a_missing_partial_is_a_labelled_miss_not_a_failure(self):
        code, text, doc = run(["standingcost-read"] + self.base())
        self.assertEqual(code, 0, text)
        self.assertTrue(doc["ok"])
        self.assertTrue(doc["empty"])
        self.assertIn("calendar step", doc["sources"][0]["note"])

    def test_the_calendar_partial_is_not_mistaken_for_a_state_partial(self):
        """`.standing-cost-calendar.json` and the read step's own partial must not collide."""
        self.build()
        doc = json.loads((self.demo_root / "calendar.json").read_text(encoding="utf-8"))
        (self.out / ".standing-cost-calendar.json").write_text(json.dumps(doc), encoding="utf-8")
        self.read_all()
        self.assertNotIn(".standing-cost-calendar.json", self.partials())
        for got in cli._partials(str(self.out), self.prefix):
            self.assertIn("located", got)


# ================================================================ reply-debt

class TestReplyDebt(PlayCase):
    play, prefix, verb = "reply-debt", "replydebt", "replydebt"
    reads = (["--source", "mail"],)

    def build(self):
        threads = []
        for i in range(5):
            threads.append({
                "thread_id": "t{0}".format(i), "subject": "Question {0}".format(i),
                "messages": [{"from": {"email": "bob@example.com", "name": "Bob"},
                              "to": ["alice@example.com"],
                              "date": stamp(days_ago=10 + i * 5, hour=9),
                              "subject": "Question {0}".format(i),
                              "snippet": "Could you send me the numbers? Can you confirm by Friday?",
                              "direction": "inbound"}]})
        threads.append({
            "thread_id": "answered", "subject": "Done",
            "messages": [{"from": {"email": "bob@example.com"}, "to": ["alice@example.com"],
                          "date": stamp(days_ago=20, hour=9), "snippet": "Can you look?",
                          "direction": "inbound"},
                         {"from": {"email": "alice@example.com"}, "to": ["bob@example.com"],
                          "date": stamp(days_ago=19, hour=9), "snippet": "Done.",
                          "direction": "outbound"}]})
        self.write_fixture("mailbox.json", {"schema": 1, "me": ["alice@example.com"],
                                            "threads": threads})

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["replydebt-read"] + self.base() + self.demo() +
                            ["--source", "mail", "--partial", "", "--max-seconds", "10"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["replydebt-report"] + self.base() +
                              ["--min-age-days", "1", "--cold-days", "14",
                               "--me", "alice@example.com", "--color", "true",
                               "--redact", "false", "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_debt_reaches_the_summary(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report(["--me", "alice@example.com"])
        self.assertEqual(doc["threads_seen"], 6)
        self.assertEqual(doc["debt"], 5)

    def test_the_read_step_reads_a_partial_named_on_the_command_line(self):
        self.build()
        code, text, doc = run(["replydebt-read"] + self.base() +
                              ["--partial", str(self.demo_root / "mailbox.json")])
        self.assertEqual(code, 0, text)
        self.assertEqual(doc["threads"], 6)

    def test_no_partial_named_at_all_is_a_labelled_miss(self):
        code, text, doc = run(["replydebt-read"] + self.base())
        self.assertEqual(code, 0, text)
        self.assertTrue(doc["empty"])
        self.assertIn("mail step", doc["sources"][0]["note"])


# ================================================================ upstream-pulse

class TestUpstreamPulse(PlayCase):
    play, prefix, verb = "upstream-pulse", "upstreamread", "upstream"
    reads = (["--source", "lockfiles"], ["--source", "registry"])

    LOCK = {
        "name": "acme", "lockfileVersion": 3, "packages": {
            "": {"name": "acme", "dependencies": {"left-pad": "^1.3.0"},
                 "devDependencies": {"tape": "^5.0.0"}},
            "node_modules/left-pad": {"version": "1.3.0", "resolved": "https://x/left-pad"},
            "node_modules/tape": {"version": "5.6.1", "dev": True},
        }}

    def build(self):
        project = self.demo_root / "project"
        project.mkdir(parents=True, exist_ok=True)
        (project / "package.json").write_text(json.dumps(
            {"name": "acme", "dependencies": {"left-pad": "^1.3.0"},
             "devDependencies": {"tape": "^5.0.0"}}), encoding="utf-8")
        (project / "package-lock.json").write_text(json.dumps(self.LOCK), encoding="utf-8")
        self.write_fixture("registry.json", {
            "schema": 1, "source": "npm", "cached_at": stamp(days_ago=0, hour=11),
            "requested": ["left-pad", "tape"],
            "packages": [
                {"name": "left-pad", "ecosystem": "npm", "latest": "1.3.0",
                 "last_release": stamp(days_ago=1500), "maintainers": ["stephen"],
                 "deprecated": "", "repository": "https://github.com/x/left-pad",
                 "releases": [stamp(days_ago=1500), stamp(days_ago=2000)]},
                {"name": "tape", "ecosystem": "npm", "latest": "5.6.1",
                 "last_release": stamp(days_ago=40), "maintainers": ["a", "b", "c"],
                 "deprecated": "", "repository": "https://github.com/x/tape",
                 "releases": [stamp(days_ago=40), stamp(days_ago=120)]},
            ]})

    def test_every_flag_is_accepted(self):
        self.build()
        code, text, _ = run(["upstream-read"] + self.base() + self.demo() +
                            ["--source", "lockfiles", "--root", str(self.demo_root),
                             "--registry-partial", str(self.demo_root / "registry.json"),
                             "--max-files", "5000", "--max-seconds", "20"])
        self.assertEqual(code, 0, text)
        code, text, doc = run(["upstream-report"] + self.base() +
                              ["--root", str(self.demo_root), "--depth", "1",
                               "--dormant-days", "365", "--cache-hours", "6",
                               "--color", "true", "--redact", "false", "--keep-path", "true"])
        self.assertEqual(code, 0, text)
        self.assert_card_and_files(text, doc)

    def test_the_lockfile_walk_and_the_registry_partial_come_together(self):
        self.build()
        self.read_all(self.demo_source())
        _, doc = self.report()
        self.assertEqual(doc["packages"], 2)
        self.assertGreaterEqual(doc["checked"], 1)

    def test_the_registry_partial_can_be_named_on_the_command_line(self):
        self.build()
        code, text, doc = run(["upstream-read"] + self.base() +
                              ["--source", "registry",
                               "--registry-partial", str(self.demo_root / "registry.json")])
        self.assertEqual(code, 0, text)
        self.assertGreater(doc["records"], 1)

    def test_a_missing_registry_partial_costs_the_registry_alone(self):
        self.build()
        run(["upstream-read"] + self.base() + self.demo() + ["--source", "lockfiles"])
        code, text, doc = run(["upstream-read"] + self.base() + ["--source", "registry"])
        self.assertEqual(code, 0, text)
        self.assertTrue(doc["empty"])
        text, summary = self.report()
        self.assert_card_and_files(text, summary)
        self.assertEqual(summary["packages"], 2)


# ================================================================ the wiring itself

class TestWiring(unittest.TestCase):
    """Claims about the parser rather than about any one Play."""

    VERBS = ("busfactor", "nightshift", "kept", "extensions", "history", "photos", "grew",
             "standingcost", "replydebt", "upstream")

    def setUp(self):
        self.parser = cli.build_parser()
        self.sub = [a for a in self.parser._actions
                    if isinstance(a, __import__("argparse")._SubParsersAction)][0]

    def test_every_pulse_play_registers_a_read_and_a_report(self):
        for verb in self.VERBS:
            self.assertIn("{0}-read".format(verb), self.sub.choices)
            self.assertIn("{0}-report".format(verb), self.sub.choices)

    def test_the_six_older_verbs_are_untouched(self):
        for verb in ("tabs", "contacts", "apps", "notes", "clutter", "receipts"):
            self.assertIn("{0}-read".format(verb), self.sub.choices)
            self.assertIn("{0}-report".format(verb), self.sub.choices)

    def test_every_verb_takes_the_common_arguments(self):
        for name, sub in self.sub.choices.items():
            flags = {s for action in sub._actions for s in action.option_strings}
            self.assertIn("--out-dir", flags, name)
            self.assertIn("--now", flags, name)
            self.assertIn("--demo", flags, name)

    def test_every_pulse_report_takes_the_view_arguments(self):
        for verb in self.VERBS:
            sub = self.sub.choices["{0}-report".format(verb)]
            flags = {s for action in sub._actions for s in action.option_strings}
            for flag in ("--color", "--redact", "--keep-path"):
                self.assertIn(flag, flags, verb)

    def test_top_is_offered_exactly_where_the_module_supports_it(self):
        for verb in self.VERBS:
            sub = self.sub.choices["{0}-report".format(verb)]
            flags = {s for action in sub._actions for s in action.option_strings}
            self.assertEqual("--top" in flags, verb in ("history", "photos"), verb)

    def test_every_pulse_verb_can_be_pointed_at_its_own_fixture_folder(self):
        for verb in self.VERBS:
            sub = self.sub.choices["{0}-read".format(verb)]
            flags = {s for action in sub._actions for s in action.option_strings}
            self.assertIn("--demo-root", flags, verb)

    def test_no_two_partial_prefixes_can_read_each_other(self):
        """Every prefix must be unable to match another Play's partial or any baseline name."""
        prefixes = ["tabs", "contacts", "apps", "notes", "clutter", "receipts", "busfactor",
                    "nightshift", "keptread", "extensions", "history", "photos", "grewsnap",
                    "standingcost", "replydebt", "upstreamread"]
        baselines = ["bus-factor", "night-shift", "kept", "extension-reach", "where-it-went",
                     "photo-debt", "whatgrew", "whatgrew-history", "standing-cost", "reply-debt",
                     "upstream-pulse"]
        for prefix in prefixes:
            for name in baselines:
                self.assertFalse("{0}-baseline.json".format(name).startswith("{0}-".format(prefix)),
                                 "the .{0}-* glob would read .{1}-baseline.json".format(prefix, name))
            for other in prefixes:
                if other != prefix:
                    self.assertFalse(other.startswith(prefix + "-"),
                                     "{0} and {1} share a glob".format(prefix, other))


if __name__ == "__main__":
    unittest.main()
