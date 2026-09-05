"""Every Play, end to end, in demo mode: the step contract, determinism, and where writes land.

These are the tests that would catch a Play that works on this machine and fails on a stranger's,
which is the only failure mode that matters for something published to a public registry.
"""
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from daily_core import cli

NOW = "2026-09-05T12:00:00Z"

# Every Play as its steps run it: the read steps first, then the report.
PLAYS = {
    "tab-debt": ([["tabs-read", "--source", s] for s in ("chromium", "firefox", "safari", "arc")],
                 ["tabs-report"]),
    "birthday-radar": ([["contacts-read", "--source", s] for s in ("addressbook", "vcard", "csv")],
                       ["contacts-report"]),
    "app-graveyard": ([["apps-read", "--source", s] for s in ("applications", "casks")],
                      ["apps-report"]),
    "vault-pulse": ([["notes-read"]], ["notes-report"]),
    "desktop-clutter": ([["clutter-read", "--source", s] for s in ("desktop", "downloads", "screenshots")],
                        ["clutter-report"]),
    "receipt-ledger": ([["receipts-read", "--source", s] for s in ("files", "mail")],
                       ["receipts-report"]),
}
REPORT_FILE = {"tab-debt": "tab-debt", "birthday-radar": "birthday-radar", "app-graveyard": "app-graveyard",
               "vault-pulse": "vault-pulse", "desktop-clutter": "desktop-clutter",
               "receipt-ledger": "receipt-ledger"}


def run(argv, out_dir, demo=True, now=NOW):
    """Invoke one step the way a Play does, and return (exit code, human text, parsed JSON)."""
    args = list(argv) + ["--out-dir", str(out_dir), "--demo", "true" if demo else "false"]
    if any(a.endswith("-report") for a in argv):
        args += ["--now", now]
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(args)
    text = buf.getvalue()
    lines = [l for l in text.splitlines() if l.strip()]
    return code, "\n".join(lines[:-1]), json.loads(lines[-1])


class TestStepContract(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="daily-test-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_every_play_completes_in_demo_mode(self):
        for slug, (reads, report) in PLAYS.items():
            with self.subTest(play=slug):
                out = self.dir / slug
                for step in reads:
                    code, _, doc = run(step, out)
                    self.assertEqual(code, 0)
                    self.assertTrue(doc["ok"])
                code, human, doc = run(report, out)
                self.assertEqual(code, 0)
                self.assertTrue(doc["ok"])
                self.assertIn("┌", human, "the card should be printed above the JSON line")
                self.assertTrue(doc["written"])

    def test_the_last_line_of_every_step_is_one_json_object(self):
        out = self.dir / "contract"
        for slug, (reads, report) in PLAYS.items():
            for step in reads + [report]:
                with self.subTest(step=" ".join(step)):
                    _, _, doc = run(step, out / slug)
                    self.assertIsInstance(doc, dict)
                    self.assertIn("ok", doc)

    def test_a_report_before_any_read_says_so_and_still_exits_zero(self):
        for slug, (_, report) in PLAYS.items():
            with self.subTest(play=slug):
                code, _, doc = run(report, self.dir / ("empty-" + slug))
                self.assertEqual(code, 0)
                self.assertTrue(doc["ok"])
                self.assertIn("warning", doc)

    def test_nothing_is_written_outside_out_dir(self):
        out = self.dir / "writes"
        before = _snapshot(self.dir)
        for slug, (reads, report) in PLAYS.items():
            for step in reads + [report]:
                run(step, out)
        written = _snapshot(self.dir) - before
        stray = [p for p in written if not str(p).startswith(str(out))]
        self.assertEqual(stray, [], "these paths were written outside out_dir")

    def test_every_written_path_is_reported(self):
        for slug, (reads, report) in PLAYS.items():
            with self.subTest(play=slug):
                out = self.dir / ("reported-" + slug)
                for step in reads:
                    run(step, out)
                _, _, doc = run(report, out)
                for path in doc["written"]:
                    self.assertTrue(pathlib.Path(path).is_file(), path)
                self.assertTrue(any(p.endswith(REPORT_FILE[slug] + ".md") for p in doc["written"]))


class TestDeterminism(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="daily-det-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_same_clock_gives_the_same_card_twice(self):
        for slug, (reads, report) in PLAYS.items():
            with self.subTest(play=slug):
                first = self._once(slug, reads, report, "a")
                second = self._once(slug, reads, report, "b")
                self.assertEqual(first[0], second[0], "card differs between runs")
                self.assertEqual(_stable(first[1]), _stable(second[1]), "result differs between runs")

    def _once(self, slug, reads, report, tag):
        """Run the whole Play into its own folder, with that folder's name removed from the output.

        Two runs necessarily write to two directories, so the paths differ by construction; what
        has to be identical is everything the reader sees above them.
        """
        out = self.dir / (slug + tag)
        for step in reads:
            run(step, out)
        _, human, doc = run(report, out)
        return human.replace(str(out), "<out>"), doc


class TestDegradation(unittest.TestCase):
    """A source that is absent, forbidden or corrupt must cost that source and never the run."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="daily-degrade-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_folder_that_does_not_exist_is_named_not_raised(self):
        missing = str(self.dir / "nowhere")
        cases = [(["notes-read", "--vault", missing], "notes"),
                 (["clutter-read", "--source", "desktop", "--desktop-dir", missing], "desktop"),
                 (["receipts-read", "--source", "files", "--receipts-dir", missing], "files"),
                 (["contacts-read", "--source", "vcard", "--vcard-dir", missing], "vCard files")]
        for argv, name in cases:
            with self.subTest(source=name):
                code, _, doc = run(argv, self.dir, demo=False)
                self.assertEqual(code, 0)
                self.assertTrue(doc["ok"])
                self.assertTrue(any(not s["found"] and s["note"] for s in doc["sources"]))

    def test_a_corrupt_fixture_is_reported_and_does_not_raise(self):
        broken = self.dir / "broken"
        shutil.copytree(pathlib.Path(cli.fixtures_dir()), broken)
        (broken / "tabs" / "chrome-session.snss").write_bytes(b"SNSS" + b"\xff" * 40)
        (broken / "contacts" / "contacts.vcf").write_bytes(b"\xff\xfe not a vcard")
        from daily_core.common import Budget
        from daily_core.scan import tabs
        sources, found = tabs.read_source("chromium", Budget(), broken / "tabs")
        self.assertEqual(found, [])
        self.assertFalse(sources[0].found)
        self.assertTrue(sources[0].note)

    def test_an_empty_source_set_reports_empty_rather_than_zero(self):
        code, _, doc = run(["contacts-read", "--source", "csv", "--csv-path", ""], self.dir, demo=False)
        self.assertEqual(code, 0)
        self.assertTrue(doc.get("empty"))
        self.assertIn("warning", doc)


class TestBounds(unittest.TestCase):
    def test_a_traversal_that_hits_its_bound_says_the_counts_are_a_lower_bound(self):
        from daily_core.common import Budget, envelope, Source
        budget = Budget(max_files=1)
        budget.spend(0)
        budget.spend(0)
        doc = envelope([Source(name="x").hit(1)], budget, {})
        self.assertFalse(doc["complete"])
        self.assertIn("lower bound", doc["warning"])

    def test_a_complete_traversal_says_so(self):
        from daily_core.common import Budget, envelope, Source
        doc = envelope([Source(name="x").hit(1)], Budget(), {})
        self.assertTrue(doc["complete"])
        self.assertNotIn("warning", doc)


def _snapshot(root: pathlib.Path):
    return {p for p in root.rglob("*") if p.is_file()}


def _stable(doc: dict) -> str:
    """Drop the paths, which carry a temporary directory name, and compare the rest."""
    trimmed = {k: v for k, v in doc.items() if k not in ("written", "sources")}
    trimmed["sources"] = [{k: v for k, v in s.items() if k != "path"} for s in doc.get("sources", [])]
    return json.dumps(trimmed, sort_keys=True, default=str)


if __name__ == "__main__":
    unittest.main()
