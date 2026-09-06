"""The ten pulse Plays, run cold in demo mode through the real command line.

A stranger's first run of one of these Plays is `--demo true` against the bundled fixtures, and
that run is also what every published screenshot is made from. So this suite drives the real
`cli.main` -- the same argv a Play step passes -- and asserts three separate things about each of
the ten:

1. **It works cold.** Every read verb and the report verb exit 0, the report and its JSON are
   written under the given out_dir, and the card carries the Play's own headline number rather
   than a zero.
2. **It is the same card everywhere.** Two runs at the same `--now`, into two fresh out_dirs,
   produce byte-identical markdown. The fixtures carry their own clock, so nothing here depends
   on the machine's timezone, its locale, its disk or its network. The network claim is enforced
   rather than asserted: every socket entry point is replaced with one that raises for the whole
   of every run below.
3. **Every advertised class actually fires.** A demo whose "dangerous permission combination"
   section, or "dormant single-publisher production dependency" section, or "silent attendee"
   section is empty teaches a reader that the section is decoration. Each case below names the
   class its fixture was built to demonstrate and asserts it is in the view.

The fixed `--now` is the clock `tools/build_daily_fixtures.py` writes the fixtures against, so the
numbers asserted here are exact rather than approximate.
"""
import hashlib
import io
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from daily_core import cli
from daily_core.common import fixtures_dir

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILDER = ROOT / "tools" / "build_daily_fixtures.py"

# The clock in tools/build_daily_fixtures.py. Same clock, same card.
NOW = "2026-09-01T12:00:00Z"

# slug -> (read steps, report step). One entry per read verb, exactly as each Play's steps run it.
PLAYS = {
    "bus-factor": ([["busfactor-read", "--source", "git"]], ["busfactor-report"]),
    "night-shift": ([["nightshift-read", "--source", "commits"]], ["nightshift-report"]),
    "kept": ([["kept-read", "--source", s] for s in ("agent", "git")], ["kept-report"]),
    "extension-reach": ([["extensions-read", "--source", s]
                         for s in ("chromium", "firefox", "safari")], ["extensions-report"]),
    "where-it-went": ([["history-read", "--source", s]
                       for s in ("chromium", "firefox", "safari")], ["history-report"]),
    "photo-debt": ([["photos-read", "--source", s] for s in ("photos", "folder")],
                   ["photos-report"]),
    "what-grew": ([["grew-read", "--source", "home"]], ["grew-report"]),
    "standing-cost": ([["standingcost-read"]], ["standingcost-report"]),
    "reply-debt": ([["replydebt-read"]], ["replydebt-report"]),
    "upstream-pulse": ([["upstream-read", "--source", s] for s in ("lockfiles", "registry")],
                       ["upstream-report"]),
}

# Which fixture folder each Play's demo has to have read from. A Play that quietly fell back to
# the machine would still produce a card, and that card would be somebody's real data.
FIXTURE_DIR = {"bus-factor": "busfactor", "night-shift": "nightshift", "kept": "kept",
               "extension-reach": "extensions", "where-it-went": "history",
               "photo-debt": "photos", "what-grew": "grew", "standing-cost": "standingcost",
               "reply-debt": "replydebt", "upstream-pulse": "upstream"}


class NoNetwork(AssertionError):
    """Raised if anything under test so much as reaches for a socket."""


def _forbidden(*args, **kwargs):
    raise NoNetwork("a demo run tried to open a network connection")


class Offline(object):
    """Every socket entry point replaced for the duration of a block."""

    NAMES = ("socket", "socketpair", "create_connection", "getaddrinfo", "gethostbyname")

    def __enter__(self):
        self._saved = {}
        for name in self.NAMES:
            if hasattr(socket, name):
                self._saved[name] = getattr(socket, name)
                setattr(socket, name, _forbidden)
        return self

    def __exit__(self, *exc):
        for name, original in self._saved.items():
            setattr(socket, name, original)
        return False


def tree_hash(root: pathlib.Path) -> str:
    """One digest over every file in a tree, name and content, in a fixed order."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def step(argv, out_dir) -> tuple:
    """One step, the way a Play runs it: (exit code, human text, the trailing JSON object)."""
    args = list(argv) + ["--out-dir", str(out_dir), "--demo", "true", "--now", NOW]
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(args)
    lines = [l for l in buf.getvalue().splitlines() if l.strip()]
    return code, "\n".join(lines[:-1]), json.loads(lines[-1])


def run_play(case, out_dir) -> dict:
    """Every step of one Play. Returns what the report step produced, plus the written files."""
    reads, report = PLAYS[case]
    results = []
    for argv in reads:
        results.append((argv, step(argv, out_dir)))
    code, card, doc = step(report, out_dir)
    name = case
    return {"reads": results, "code": code, "card": card, "doc": doc,
            "md": (pathlib.Path(out_dir) / "{0}.md".format(name)),
            "json": (pathlib.Path(out_dir) / "{0}.json".format(name))}


class PulseDemo(unittest.TestCase):
    """One test method per Play, plus the two properties every Play shares."""

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls._offline = Offline()
        cls._offline.__enter__()
        cls._dirs = []
        cls._runs = {}
        for slug in PLAYS:
            out = pathlib.Path(tempfile.mkdtemp(prefix="pulse-demo-"))
            cls._dirs.append(out)
            cls._runs[slug] = run_play(slug, out)

    @classmethod
    def tearDownClass(cls):
        cls._offline.__exit__(None, None, None)
        for path in cls._dirs:
            shutil.rmtree(path, ignore_errors=True)

    def view(self, slug: str) -> dict:
        return json.loads(self._runs[slug]["json"].read_text(encoding="utf-8"))["view"]

    def card(self, slug: str) -> str:
        return self._runs[slug]["card"]

    # -- the properties every one of the ten shares ------------------------------------------

    def test_every_step_exits_zero_and_writes_a_report(self):
        for slug in PLAYS:
            run = self._runs[slug]
            for argv, (code, _text, doc) in run["reads"]:
                self.assertEqual(code, 0, "{0}: {1} exited {2}".format(slug, argv, code))
                self.assertTrue(doc.get("ok"), "{0}: {1} did not report ok".format(slug, argv))
            self.assertEqual(run["code"], 0, "{0}: report exited {1}".format(slug, run["code"]))
            self.assertTrue(run["doc"].get("ok"), slug)
            self.assertNotIn("empty", run["doc"], "{0}: the demo report is empty".format(slug))
            for path in (run["md"], run["json"]):
                self.assertTrue(path.is_file(), "{0}: {1} was not written".format(slug, path.name))
                self.assertGreater(path.stat().st_size, 1200,
                                   "{0}: {1} is too small to be a report".format(slug, path.name))

    def test_the_card_is_a_card(self):
        for slug in PLAYS:
            card = self.card(slug)
            self.assertTrue(card.strip(), "{0}: the card is empty".format(slug))
            self.assertIn("┌", card, slug)
            self.assertGreaterEqual(len(card.splitlines()), 12, slug)

    def test_every_source_read_was_a_bundled_fixture(self):
        """Nothing here may have reached the machine this test runs on."""
        root = str(fixtures_dir().resolve())
        for slug in PLAYS:
            found = [s for s in self.view_sources(slug) if s.get("found")]
            self.assertTrue(found, "{0}: no source answered".format(slug))
            wanted = str((fixtures_dir() / FIXTURE_DIR[slug]).resolve())
            paths = [s.get("path") or "" for s in found if s.get("path")]
            self.assertTrue(paths, "{0}: no source named a path".format(slug))
            for path in paths:
                resolved = str(pathlib.Path(path).resolve())
                self.assertTrue(resolved.startswith(root),
                                "{0}: read {1}, which is outside the bundled fixtures".format(
                                    slug, path))
            self.assertTrue(any(str(pathlib.Path(p).resolve()).startswith(wanted) for p in paths),
                            "{0}: nothing was read from {1}".format(slug, wanted))

    def view_sources(self, slug: str) -> list:
        return json.loads(self._runs[slug]["json"].read_text(encoding="utf-8"))["sources"]

    def test_two_runs_at_the_same_clock_are_byte_identical(self):
        """A fresh out_dir each time, because these Plays write baselines and a baseline is
        exactly the state a second run is supposed to notice."""
        for slug in PLAYS:
            first = self._runs[slug]["md"].read_bytes()
            second_dir = pathlib.Path(tempfile.mkdtemp(prefix="pulse-demo-again-"))
            try:
                again = run_play(slug, second_dir)
                self.assertEqual(again["code"], 0, slug)
                self.assertEqual(first, again["md"].read_bytes(),
                                 "{0}: two runs at the same --now differ".format(slug))
            finally:
                shutil.rmtree(second_dir, ignore_errors=True)

    def test_the_network_guard_is_actually_armed(self):
        """The offline guard above only means something if it would have caught a call."""
        with self.assertRaises(NoNetwork):
            socket.socket()

    def test_the_generator_is_idempotent(self):
        """Running the builder again must leave the tree byte for byte where it was.

        The fixtures in the working tree are the builder's own output, so re-running it and
        finding a different tree means some generator picked up the wall clock, an unseeded
        random, or a set's iteration order -- and a fixture that moves is a demo card that
        differs between two machines.
        """
        if not BUILDER.is_file():
            self.skipTest("tools/build_daily_fixtures.py is not in this tree")
        before = tree_hash(fixtures_dir())
        proc = subprocess.run([sys.executable, str(BUILDER)], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode("utf-8", "replace")[-2000:])
        self.assertEqual(before, tree_hash(fixtures_dir()),
                         "build_daily_fixtures.py is not idempotent: the second run wrote "
                         "different bytes")

    # -- bus-factor ---------------------------------------------------------------------------

    def test_bus_factor(self):
        v, card = self.view("bus-factor"), self.card("bus-factor")
        self.assertEqual(v["tracked_files"], 275)
        self.assertIn("275 files.", card)
        self.assertGreater(v["sole_files"], 60)
        self.assertGreater(v["tracked_lines"], 50000)
        # The class this fixture exists for: one directory, thirty-one files, one name.
        cluster = v["largest_cluster"]
        self.assertIsNotNone(cluster)
        self.assertGreaterEqual(cluster["files"], 25)
        self.assertIn("settlement", cluster["where"])
        self.assertIn("Largest cluster:", card)
        # That name has not committed for over a year, so the cluster is also a departure.
        self.assertTrue(v["departed"], "no departed author, so ALREADY GONE never prints")
        self.assertGreater(v["stale_sole_files"], 20)
        # One person is the only author in more than one repository.
        self.assertTrue(v["cross_repo"])
        # The degradations: a bot, a set of excluded paths, a file nobody owns, a shallow clone.
        self.assertGreaterEqual(v["bots_excluded"], 1)
        self.assertGreater(v["excluded_paths"], 0)
        self.assertGreaterEqual(v["unattributed_files"], 1)
        self.assertTrue(v["shallow"])
        self.assertTrue(v["shallow_repos"])

    # -- night-shift --------------------------------------------------------------------------

    def test_night_shift(self):
        v, card = self.view("night-shift"), self.card("night-shift")
        self.assertGreater(v["commits"], 250)
        self.assertGreater(v["late"]["commits"], 40)
        self.assertIn("% of commits after 11pm", card)
        self.assertNotIn("0% of commits", card)
        # The correlation the Play exists to report: late work is undone and patched up more often.
        late, rest = v["quality"]["late"], v["quality"]["rest"]
        self.assertGreater(late["reverted"], 0)
        self.assertGreater(late["fixups"], 0)
        self.assertGreater(late["revert_rate"], rest["revert_rate"])
        self.assertGreater(late["fixup_rate"], rest["fixup_rate"])
        # Two UTC offsets in the window, so the caveat that a card without it would hide prints.
        self.assertTrue(v["travel"])
        self.assertEqual(len(v["offsets"]), 2)
        self.assertIn("UTC offsets appear in this window", card)
        # A rebased stretch, reported rather than straightened out.
        self.assertGreater(v["rewritten"]["commits"], 0)
        self.assertGreater(v["weekend"]["commits"], 0)
        self.assertGreater(v["streak"]["longest"], 5)

    # -- kept ---------------------------------------------------------------------------------

    def test_kept(self):
        v, card = self.view("kept"), self.card("kept")
        self.assertGreater(v["totals"]["ever"]["agent"], 10000)
        self.assertIn("lines written", card)
        self.assertIsNotNone(v["survival"]["agent"])
        # The control group is the whole point: a survival rate alone is a dunk, not a measurement.
        self.assertIsNotNone(v["survival"]["control"])
        self.assertIsNotNone(v["survival"]["gap"])
        # All four fates are represented, so the WHERE IT WENT bar partitions something real.
        classes = v["classes"]
        for key in ("alive", "reverted", "deleted_with_file", "rewritten"):
            self.assertGreater(classes[key], 0, "kept: nothing was {0}".format(key))
        self.assertGreater(classes["never_committed"], 0)
        self.assertGreater(v["reverts"]["count"], 0)
        # Every half-life bucket has a denominator on both sides, agent and hand-written.
        for bucket in v["half_life"]["buckets"]:
            self.assertGreater(bucket["ever"], 0, "kept: empty bucket {0}".format(bucket["label"]))
            self.assertIsNotNone(bucket["rate"], bucket["label"])
            self.assertIsNotNone(bucket["human_rate"], bucket["label"])
        # The degradation: one repository is a shallow clone, so its answer is rated low.
        self.assertIn("low", [row["level"] for row in v["confidence"]])
        self.assertGreaterEqual(v["sessions"]["count"], 15)

    # -- extension-reach ----------------------------------------------------------------------

    def test_extension_reach(self):
        v, card = self.view("extension-reach"), self.card("extension-reach")
        self.assertGreaterEqual(v["extensions"], 18)
        self.assertGreater(v["all_urls"], 0)
        self.assertIn("read every page including your bank", card)
        # The headline class: blanket page access paired with a second power.
        permissions = [c["permission"] for c in v["combinations"]]
        self.assertIn("cookies", permissions)
        self.assertIn("webRequest", permissions)
        self.assertGreater(v["combination_extensions"], 0)
        # Every reach tier is populated, so the bar is a partition and not one block.
        tiers = dict((r["tier"], r["extensions"]) for r in v["reach"])
        for tier in ("all_urls", "broad_wildcard", "specific_hosts", "active_tab_only", "none"):
            self.assertGreater(tiers[tier], 0, "extension-reach: no extension is {0}".format(tier))
        # Unmaintained, unused, and still reading every page.
        self.assertGreater(v["stale"]["count"], 0)
        self.assertGreater(v["idle"]["still_reading"], 0)
        self.assertGreater(v["mv2"]["count"], 0)
        # Where they came from, all four kinds.
        self.assertGreater(v["sideloaded"]["count"], 0)
        self.assertGreater(v["policy"]["count"], 0)
        self.assertGreater(v["unpacked"]["count"], 0)
        self.assertGreater(v["withheld"], 0)
        self.assertTrue(v["cross_browser"])
        # The degradation: Safari publishes no host permissions, so those are unknown, not none.
        self.assertGreater(v["reach_unknown"], 0)
        self.assertTrue(v["reach_unknown_names"])

    # -- where-it-went ------------------------------------------------------------------------

    def test_where_it_went(self):
        v, card = self.view("where-it-went"), self.card("where-it-went")
        self.assertGreater(v["visits"], 8000)
        self.assertIn("{0:,} pages in 90 days".format(v["visits"]), card)
        self.assertGreater(v["unique_domains"], 15)
        self.assertGreater(v["per_day"], 50)
        # A previous window to compare against, which is what makes the trend a trend.
        self.assertGreater(v["trend"]["previous"], 1000)
        # The quotable class: pages opened over and over.
        self.assertTrue(v["rereads"])
        self.assertGreater(v["rereads"][0]["count"], 100)
        # A single-domain run inside one sitting.
        self.assertTrue(v["sessions"]["longest_domain_run"])
        # The degradation: Safari records no page transition, so those visits are counted in the
        # total and left out of the intent split.
        self.assertTrue(v["intent"]["not_exposed"])
        self.assertGreater(v["intent"]["unknown"], 0)
        self.assertGreater(v["intent"]["typed"], 0)
        self.assertGreater(v["intent"]["linked"], 0)
        # And the honest remainder: sites the bundled table does not name.
        self.assertGreater(v["uncategorised"]["visits"], 0)
        self.assertGreaterEqual(len(v["categories"]), 6)

    # -- photo-debt ---------------------------------------------------------------------------

    def test_photo_debt(self):
        v, card = self.view("photo-debt"), self.card("photo-debt")
        self.assertGreater(v["assets"], 8000)
        self.assertIn("burst siblings", card)
        self.assertNotIn("0 burst siblings", card)
        # Three separate claims, each with its own confidence, each present.
        self.assertGreater(v["bursts"]["siblings"], 100)
        self.assertGreaterEqual(v["bursts"]["largest"], 4)
        self.assertGreater(v["duplicates"]["extra"], 0)
        self.assertGreater(v["screenshots"]["count"], 500)
        self.assertTrue(v["screenshots"]["reopen_known"])
        self.assertGreater(v["screenshots"]["never_reopened"], 0)
        for tier in v["reclaim"]["tiers"]:
            self.assertGreater(tier["count"], 0, "photo-debt: empty tier {0}".format(tier["name"]))
        self.assertGreater(v["reclaim"]["bytes"], 10 ** 9)
        # The degradation: a pair too large to hash is shown and never counted as reclaimable.
        self.assertGreater(v["duplicates"]["unproven_groups"], 0)
        self.assertIn("not compared", v["duplicates"]["unproven_note"])
        # Live Photos counted once, iCloud placeholders named rather than assumed present.
        self.assertGreater(v["live"], 0)
        self.assertGreater(v["not_local"], 0)
        self.assertGreater(v["protected"]["favourites"], 0)
        self.assertGreater(v["protected"]["edited"], 0)
        self.assertGreaterEqual(len(v["years"]), 8)

    # -- what-grew ----------------------------------------------------------------------------

    def test_what_grew(self):
        """A delta needs two measurements on two days, so the fixture ships both.

        A snapshot-diffing Play whose demo could only print "nothing to compare against yet" would
        be demonstrating the one state it exists to get past, so `sizes-previous.json` is seeded as
        a baseline on a cold run and the stranger's first card is a real delta."""
        v, card = self.view("what-grew"), self.card("what-grew")
        self.assertTrue(v["readable"])
        self.assertFalse(v["first_run"], "the fixture ships an older snapshot to compare against")
        # All four classes the report keeps separate must fire, or the demo is not demonstrating.
        self.assertTrue(v["grew"], "nothing grew in place")
        self.assertTrue(v["appeared"], "nothing newly appeared")
        self.assertTrue(v["shrank"], "nothing shrank — a growth-only card is half the tool")
        self.assertTrue(v["deleted"], "nothing was deleted")
        self.assertGreater(v["net_bytes"], 100 * 10 ** 9)
        self.assertIn("since", card)
        self.assertIsNotNone(v["rate_bytes_per_day"])
        self.assertGreater(v["total_bytes"], 500 * 10 ** 9)
        # The delta card leads with the movement, not the absolute total: what is on the card is
        # the disk context line, which is the denominator every other number here needs.
        self.assertIn(v["free_size"], card)
        self.assertGreater(v["files"], 10 ** 6)
        self.assertGreaterEqual(v["dirs_named"], 40)
        # What you could get back, split by what it would cost you.
        self.assertGreater(v["reclaim_bytes"], 100 * 10 ** 9)
        self.assertGreater(v["regenerable_bytes"], 0)
        self.assertGreater(v["safe_bytes"], 0)
        self.assertGreater(v["think_bytes"], 0)
        self.assertGreater(v["irreplaceable_bytes"], 0)
        self.assertTrue(v["biggest"])
        self.assertGreater(v["free_bytes"], 0)
        # The degradation: folders this run could not open are counted, named, and in no total.
        self.assertEqual(v["denied"]["count"], 3)
        self.assertTrue(v["denied"]["paths"])
        self.assertGreater(v["placeholder_files"], 0)

    # -- standing-cost ------------------------------------------------------------------------

    def test_standing_cost(self):
        v, card = self.view("standing-cost"), self.card("standing-cost")
        self.assertGreater(v["person_hours"], 800)
        self.assertEqual(v["series_total"], 8)
        self.assertIn("person-hours.", card)
        self.assertIn("Engineering Standup", card)
        # The headline class: somebody whose presence is a formality.
        reasons = sorted({row["reason"] for row in v["silent"]})
        self.assertIn("never accepted", reasons)
        self.assertIn("accepted every time, never present", reasons)
        self.assertGreater(v["silent_people"], 0)
        # A series that grew, in both minutes and people.
        self.assertTrue(v["drift"])
        drift = v["drift"][0]["drift"]
        self.assertGreater(drift["minutes_grew"], 0)
        self.assertGreater(drift["attendees_grew"], 0)
        # Cancelled occurrences are credited, never billed.
        self.assertGreater(v["cancellation"]["cancelled"], 0)
        self.assertGreater(v["cancellation"]["credit_person_hours"], 0)
        # Declined and unanswered invitations are counted and kept out of the headline.
        self.assertGreater(v["declined_person_hours"], 0)
        self.assertGreater(v["no_response_person_hours"], 0)
        # No rate was given, so no money is claimed anywhere.
        self.assertFalse(v["rate"]["set"])
        self.assertFalse(v["cost"]["known"])
        # The degradations: three events with no end time, and one attendee with no zone.
        self.assertEqual(v["events_unusable"], 3)
        self.assertTrue(v["unusable_reasons"])
        self.assertGreater(v["zones"]["unknown"], 0)
        self.assertGreater(v["fragmentation"]["minutes"], 0)

    # -- reply-debt ---------------------------------------------------------------------------

    def test_reply_debt(self):
        v, card = self.view("reply-debt"), self.card("reply-debt")
        self.assertGreater(v["debt"], 10)
        self.assertGreater(v["direct"], 5)
        self.assertGreater(v["implied"], 0)
        self.assertGreater(v["fyi"], 0)
        self.assertIn("awaiting your reply", card)
        self.assertNotIn("0 threads awaiting", card)
        # The class this fixture exists for: the newest message quotes a question that was already
        # answered. Quoted history is stripped before anything is matched, so it is not an ask.
        quoted = [r for r in v["fyi_threads"] if r["thread_id"] == "t-quoted-00"]
        self.assertEqual(len(quoted), 1, "the quoted-history thread is not in the FYI list")
        self.assertEqual(quoted[0]["class"], "pure FYI")
        self.assertEqual(quoted[0]["signals"], [])
        self.assertNotIn("t-quoted-00", [r["thread_id"] for r in v["awaiting"]])
        # The other side of the ledger, without which this Play is only an instrument of guilt.
        self.assertGreater(v["reciprocity"]["threads"], 0)
        # One person, several threads.
        self.assertTrue(v["repeat_senders"])
        self.assertGreaterEqual(v["repeat_senders"][0]["threads"], 2)
        self.assertGreater(v["cold"], 0)
        self.assertGreater(v["too_recent"], 0)
        # Every exclusion reason is represented, because the denominator is only honest if they are.
        reasons = sorted(row["reason"] for row in v["exclusions"])
        self.assertEqual(reasons, ["automated notification", "calendar invite", "mailing list",
                                   "no-reply sender"])
        # No subject is ever printed on the card.
        for row in v["awaiting"]:
            self.assertTrue(row["card_subject"].startswith("#"))

    # -- upstream-pulse -----------------------------------------------------------------------

    def test_upstream_pulse(self):
        v, card = self.view("upstream-pulse"), self.card("upstream-pulse")
        self.assertGreater(v["totals"]["packages"], 100)
        self.assertGreater(v["totals"]["direct"], 60)
        self.assertIn("direct dependencies.", card)
        self.assertGreater(v["checks"]["checked"], 40)
        # The headline class: dormant, single-publisher, and in the production request path.
        self.assertGreater(v["headline"]["count"], 0)
        self.assertGreater(v["headline"]["both"], 0)
        self.assertIn("DORMANT · SINGLE-PUBLISHER · PRODUCTION", card)
        for pkg in v["headline"]["packages"]:
            self.assertEqual(pkg["radius"], "production")
            self.assertEqual(pkg["maintainers"], 1)
        self.assertGreater(v["dormant"]["count"], 0)
        self.assertGreater(v["single_maintainer"]["count"], 0)
        self.assertGreater(v["deprecated"]["count"], 0)
        self.assertGreater(v["archived"]["count"], 0)
        # A successor, from the one place a successor may come from.
        self.assertTrue(v["replacements"])
        self.assertTrue(all(r["successor"] for r in v["replacements"]))
        # A licence that changed between the version pinned and the version on offer.
        self.assertTrue(v["licence_changes"])
        # Four ecosystems, read by four different lockfile readers.
        self.assertGreaterEqual(v["totals"]["lockfiles"], 4)
        self.assertGreaterEqual(len(v["ecosystems"]), 3)
        # The degradations: a lockfile that could not be read, lookups that failed, and packages
        # nobody asked about -- none of which may read as "healthy".
        self.assertFalse(v["network"]["offline"])
        self.assertGreater(v["network"]["unchecked"], 0)
        self.assertGreater(v["checks"]["failed"], 0)
        unread = [s for s in self.view_sources("upstream-pulse") if not s.get("found")]
        self.assertTrue(unread, "no lockfile in the demo tree is unreadable")


if __name__ == "__main__":
    unittest.main()
