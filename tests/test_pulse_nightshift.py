"""night-shift: the promises the card makes, checked against real repositories.

The load-bearing one is the first class in this file. Every other tool that plots commit times
renders them in whatever zone the reading machine is set to, so a fortnight in Tokyo shows up as a
sleep-schedule collapse and a laptop that moved offices rewrites last year. This Play reads the
offset git recorded in the commit itself, and that is asserted here twice: once against the UTC
instant it is not allowed to use, and once against a machine timezone deliberately changed under
the test.

Everything else is the same shape: real `git init`, real commits with explicit author and committer
dates, and assertions on numbers that have their denominators printed next to them.
"""
import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from daily_core import gitread
from daily_core.common import Budget, display_width
from daily_core.scan import nightshift

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
CFG = {"now": "2026-09-05T12:00:00+00:00", "days": 90}

ME = ("Ada", "ada@example.com")
SOMEONE_ELSE = ("Charles", "charles@example.com")


def _git_or_skip() -> gitread.Git:
    git = gitread.Git.find()
    if not git.ok:
        raise unittest.SkipTest(git.note)
    return git


def _make_repo(root: Path, commits, who=ME) -> Path:
    """A real repository, because the point of these tests is the real git binary's real output.

    Each entry is (subject, authored) or (subject, authored, committed) or
    (subject, authored, committed, name, email). The dates are passed through verbatim so a commit
    can carry any UTC offset a traveller's laptop would have written.
    """
    git = _git_or_skip()
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run([git.binary, "init", "-q", "-b", "main", str(root)], check=True,
                   capture_output=True)
    for key, value in (("user.email", who[1]), ("user.name", who[0])):
        subprocess.run([git.binary, "-C", str(root), "config", key, value], check=True,
                       capture_output=True)
    for i, spec in enumerate(commits):
        subject, authored = spec[0], spec[1]
        committed = spec[2] if len(spec) > 2 and spec[2] else authored
        name = spec[3] if len(spec) > 3 else who[0]
        email = spec[4] if len(spec) > 4 else who[1]
        (root / "f{0}.txt".format(i)).write_text("{0}\n".format(i), encoding="utf-8")
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
               "GIT_AUTHOR_DATE": authored, "GIT_COMMITTER_DATE": committed,
               "PATH": "/usr/bin:/bin", "HOME": str(root)}
        subprocess.run([git.binary, "-C", str(root), "add", "-A"], check=True,
                       capture_output=True, env=env)
        subprocess.run([git.binary, "-C", str(root), "commit", "-q", "-m", subject], check=True,
                       capture_output=True, env=env)
    return root


def _run(tmp, commits, cfg=None, name="project", who=ME):
    """One repository under a root, read and analysed exactly as the step would do it."""
    root = Path(tmp)
    _make_repo(root / name, commits, who=who)
    conf = dict(CFG)
    conf["root"] = str(root)
    conf.update(cfg or {})
    sources, records = nightshift.read_source("commits", Budget(), conf)
    return sources, records, nightshift.analyse(records, NOW, conf)


# ---------------------------------------------------------------- the timezone promise

class TestTheCommitterSRecordedOffsetIsTheClockUsed(unittest.TestCase):
    """A commit made in Tokyo is a Tokyo commit forever."""

    TOKYO = "2026-08-19T04:12:00+09:00"          # 19:12 the previous day in UTC

    def test_the_hour_bucket_is_the_offset_s_wall_clock_not_utc(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("late night parser", self.TOKYO)])
            self.assertEqual(v["commits"], 1)
            self.assertEqual(v["hours"][4], 1, "04:12+09:00 belongs in the 04:00 bucket")
            self.assertEqual(v["hours"][19], 0, "19:12 is the UTC instant, not a clock anyone read")
            self.assertEqual(sum(v["hours"]), 1)

    def test_the_weekday_and_the_date_follow_the_same_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("late night parser", self.TOKYO)])
            self.assertEqual(v["weekdays"][2], 1, "04:12 on the 19th is a Wednesday in Tokyo")
            self.assertEqual(v["weekdays"][1], 0, "in UTC it would fall on the Tuesday")
            self.assertEqual(v["latest"]["weekday"], "Wednesday")
            self.assertEqual(v["latest"]["date"], "2026-08-19")
            self.assertEqual(v["latest"]["clock"], "04:12")
            self.assertEqual(v["latest"]["offset"], "UTC+09:00")

    def test_the_machine_s_own_timezone_cannot_move_a_commit(self):
        if not hasattr(time, "tzset"):
            raise unittest.SkipTest("no tzset on this platform")
        before = os.environ.get("TZ")
        seen = []
        try:
            for zone in ("UTC", "America/Los_Angeles", "Pacific/Auckland"):
                os.environ["TZ"] = zone
                time.tzset()
                with tempfile.TemporaryDirectory() as tmp:
                    _, _, v = _run(tmp, [("late night parser", self.TOKYO)])
                seen.append((tuple(v["hours"]), tuple(v["weekdays"]), v["latest"]["date"]))
        finally:
            if before is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = before
            time.tzset()
        self.assertEqual(len(set(seen)), 1, "the reading machine's zone changed the answer: {0}".format(seen))
        self.assertEqual(seen[0][0][4], 1)

    def test_the_grid_places_the_commit_in_one_cell_of_seven_by_twenty_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("late night parser", self.TOKYO)])
            self.assertEqual(len(v["grid"]), 7)
            self.assertTrue(all(len(row) == 24 for row in v["grid"]))
            self.assertEqual(v["grid"][2][4], 1)
            self.assertEqual(sum(sum(row) for row in v["grid"]), 1)


# ---------------------------------------------------------------- shares

class TestSharesCarryTheirDenominator(unittest.TestCase):

    COMMITS = [
        ("tokyo night", "2026-08-19T04:12:00+09:00"),        # late, Wed
        ("evening push", "2026-08-20T23:30:00+00:00"),       # late, Thu
        ("small hours", "2026-08-21T01:05:00+00:00"),        # late, Fri
        ("saturday work", "2026-08-15T14:00:00+00:00"),      # weekend
        ("sunday work", "2026-08-16T15:00:00+00:00"),        # weekend
        ("monday one", "2026-08-17T09:00:00+00:00"),
        ("monday two", "2026-08-17T11:00:00+00:00"),
        ("tuesday one", "2026-08-18T14:00:00+00:00"),
        ("tuesday two", "2026-08-18T16:00:00+00:00"),
        ("wednesday one", "2026-08-19T10:00:00+00:00"),
    ]

    def test_late_is_after_the_late_hour_or_before_dawn_with_its_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["commits"], 10)
            self.assertEqual(v["late"]["commits"], 3)
            self.assertEqual(v["late"]["total"], 10)
            self.assertEqual(v["late"]["share"], 30)
            self.assertEqual(v["late"]["window"], "11pm to 5am")

    def test_the_weekend_share_counts_saturday_and_sunday_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["weekend"]["commits"], 2)
            self.assertEqual(v["weekend"]["total"], 10)
            self.assertEqual(v["weekend"]["share"], 20)

    def test_the_late_hour_is_configurable_and_moves_the_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, records, _ = _run(tmp, self.COMMITS)
            conf = dict(CFG)
            conf["late_hour"] = 22
            v = nightshift.analyse(records, NOW, conf)
            self.assertEqual(v["late"]["commits"], 3, "nothing sits between 22:00 and 23:00 here")
            conf["late_hour"] = 16
            v = nightshift.analyse(records, NOW, conf)
            self.assertEqual(v["late"]["commits"], 4, "16:00 on the Tuesday joins the late group")

    def test_a_window_with_no_commits_reports_zero_rather_than_dividing_by_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = dict(CFG)
            conf["days"] = 1
            _, _, v = _run(tmp, self.COMMITS, cfg=conf)
            self.assertEqual(v["commits"], 0)
            self.assertEqual(v["late"]["share"], 0)
            self.assertEqual(v["quality"]["late"]["mean_subject"], 0.0)
            self.assertEqual(v["latest"], {})
            self.assertTrue(any("nothing to count" in c for c in v["caveats"]))
            nightshift.render(v, {})                      # must not raise on an empty window


# ---------------------------------------------------------------- the correlation

class TestLateWorkQualityCorrelation(unittest.TestCase):

    COMMITS = [
        ("add parser", "2026-08-10T23:30:00+00:00"),                 # late, later reverted
        ('Revert "add parser"', "2026-08-11T10:00:00+00:00"),
        ("tidy imports", "2026-08-12T10:00:00+00:00"),               # followed by a fix-up
        ("fix typo in tidy imports", "2026-08-12T10:30:00+00:00"),
    ]

    def test_a_revert_names_the_commit_it_undoes_and_only_that_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["quality"]["late"]["commits"], 1)
            self.assertEqual(v["quality"]["late"]["reverted"], 1)
            self.assertEqual(v["quality"]["late"]["revert_rate"], 100)
            self.assertEqual(v["quality"]["rest"]["commits"], 3)
            self.assertEqual(v["quality"]["rest"]["reverted"], 0)

    def test_a_fix_up_within_the_window_is_attributed_to_the_commit_before_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["quality"]["rest"]["fixups"], 1)
            self.assertEqual(v["quality"]["rest"]["fixup_rate"], 33)
            self.assertEqual(v["quality"]["fixup_minutes"], 60)

    def test_a_fix_up_outside_the_window_is_not_a_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, records, _ = _run(tmp, self.COMMITS)
            conf = dict(CFG)
            conf["fixup_minutes"] = 10
            v = nightshift.analyse(records, NOW, conf)
            self.assertEqual(v["quality"]["rest"]["fixups"], 0, "30 minutes is outside a 10 minute window")

    def test_the_mean_subject_length_is_reported_for_both_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["quality"]["late"]["mean_subject"], float(len("add parser")))
            self.assertGreater(v["quality"]["rest"]["mean_subject"], 0)

    def test_the_difference_between_the_groups_is_stated_in_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["quality"]["difference"]["revert_points"], 100)
            self.assertEqual(v["quality"]["difference"]["fixup_points"], -33)

    def test_a_revert_by_someone_else_still_counts_against_your_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            commits = [("add parser", "2026-08-10T23:30:00+00:00"),
                       ('Revert "add parser"', "2026-08-11T10:00:00+00:00", None,
                        SOMEONE_ELSE[0], SOMEONE_ELSE[1])]
            _, records, v = _run(tmp, commits)
            self.assertEqual(v["commits"], 1, "only your own commit is counted in the totals")
            self.assertEqual(v["others"], 1)
            self.assertEqual(v["quality"]["late"]["reverted"], 1)
            self.assertTrue(any(r["mine"] is False for r in records))

    def test_a_matching_subject_in_another_repository_is_not_a_revert(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [("add parser", "2026-08-10T23:30:00+00:00")])
            _make_repo(Path(tmp) / "two", [('Revert "add parser"', "2026-08-11T10:00:00+00:00")])
            conf = dict(CFG)
            conf["root"] = tmp
            _, records = nightshift.read_source("commits", Budget(), conf)
            v = nightshift.analyse(records, NOW, conf)
            self.assertEqual(v["quality"]["late"]["reverted"], 0)


# ---------------------------------------------------------------- calendar

class TestStreaksAndBreaks(unittest.TestCase):

    COMMITS = [("day {0}".format(d), "2026-07-{0:02d}T12:00:00+00:00".format(d))
               for d in (1, 2, 3, 4, 5, 10, 11, 12)]

    def test_the_longest_run_of_consecutive_days_is_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["streak"]["longest"], 5)
            self.assertEqual(v["streak"]["start"], "2026-07-01")
            self.assertEqual(v["streak"]["end"], "2026-07-05")
            self.assertEqual(v["days_with_commits"], 8)

    def test_the_longest_break_is_the_silence_between_two_commit_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, self.COMMITS)
            self.assertEqual(v["gap"]["longest"], 4)
            self.assertEqual(v["gap"]["start"], "2026-07-06")
            self.assertEqual(v["gap"]["end"], "2026-07-09")

    def test_two_commits_on_one_day_are_one_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("a", "2026-07-01T09:00:00+00:00"),
                                 ("b", "2026-07-01T21:00:00+00:00")])
            self.assertEqual(v["days_with_commits"], 1)
            self.assertEqual(v["streak"]["longest"], 1)
            self.assertEqual(v["gap"]["longest"], 0)

    def test_the_day_a_commit_belongs_to_is_the_day_its_own_offset_says(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 23:30+13:00 is still the 1st locally, and the 1st in UTC would be the 2nd here.
            _, _, v = _run(tmp, [("a", "2026-07-01T23:30:00+13:00"),
                                 ("b", "2026-07-02T23:30:00+13:00")])
            self.assertEqual(v["streak"]["longest"], 2)
            self.assertEqual(v["streak"]["start"], "2026-07-01")


class TestTrendAcrossThirdsOfTheWindow(unittest.TestCase):
    def test_the_window_splits_into_three_and_the_late_share_is_reported_per_third(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 90 days back from 5 Sep is 7 Jun; the thirds break at 7 Jul and 6 Aug.
            commits = [("early day", "2026-06-20T10:00:00+00:00"),
                       ("middle day", "2026-07-20T10:00:00+00:00"),
                       ("middle night", "2026-07-21T23:30:00+00:00"),
                       ("late night one", "2026-08-20T23:30:00+00:00"),
                       ("late night two", "2026-08-21T02:00:00+00:00")]
            _, _, v = _run(tmp, commits)
            thirds = v["trend"]["thirds"]
            self.assertEqual(len(thirds), 3)
            self.assertEqual([t["commits"] for t in thirds], [1, 2, 2])
            self.assertEqual([t["share"] for t in thirds], [0, 50, 100])
            self.assertEqual(sum(t["commits"] for t in thirds), v["commits"])
            self.assertEqual(v["trend"]["move"], 100)
            self.assertEqual(v["trend"]["direction"], "up 100 points")
            self.assertTrue(v["trend"]["spark"], "three shares should draw a sparkline")

    def test_a_flat_window_reports_level_rather_than_a_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("a", "2026-06-20T10:00:00+00:00"),
                                 ("b", "2026-08-20T10:00:00+00:00")])
            self.assertEqual(v["trend"]["direction"], "level")


class TestPerRepositorySplit(unittest.TestCase):
    def test_the_repository_with_the_most_late_commits_comes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "quiet", [("a", "2026-08-10T10:00:00+00:00")])
            _make_repo(Path(tmp) / "loud", [("b", "2026-08-11T23:30:00+00:00"),
                                            ("c", "2026-08-12T01:00:00+00:00")])
            conf = dict(CFG)
            conf["root"] = tmp
            _, records = nightshift.read_source("commits", Budget(), conf)
            v = nightshift.analyse(records, NOW, conf)
            self.assertEqual([r["repo"] for r in v["per_repo"]], ["loud", "quiet"])
            self.assertEqual(v["per_repo"][0]["late"], 2)
            self.assertEqual(v["per_repo"][0]["commits"], 2)
            self.assertEqual(v["per_repo"][0]["share"], 100)
            self.assertEqual(v["per_repo"][1]["late"], 0)
            self.assertEqual(sorted(v["repos"]), ["loud", "quiet"])


# ---------------------------------------------------------------- caveats

class TestTimezoneTravelIsNotMistakenForASchedule(unittest.TestCase):
    def test_one_offset_is_not_travel(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("a", "2026-08-10T10:00:00+01:00"),
                                 ("b", "2026-08-11T10:00:00+01:00")])
            self.assertFalse(v["travel"])
            self.assertEqual(v["travel_note"], "")
            self.assertEqual([o["label"] for o in v["offsets"]], ["UTC+01:00"])

    def test_a_second_offset_raises_the_caveat_with_the_dates_it_covers(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("home one", "2026-08-01T10:00:00+01:00"),
                                 ("home two", "2026-08-02T10:00:00+01:00"),
                                 ("away", "2026-08-20T02:00:00+09:00")])
            self.assertTrue(v["travel"])
            self.assertEqual([o["label"] for o in v["offsets"]], ["UTC+01:00", "UTC+09:00"])
            self.assertEqual(v["offsets"][0]["commits"], 2)
            self.assertEqual(v["offsets"][0]["first"], "2026-08-01")
            self.assertEqual(v["offsets"][0]["last"], "2026-08-02")
            self.assertEqual(v["offsets"][1]["commits"], 1)
            self.assertIn("UTC+09:00", v["travel_note"])
            self.assertIn(v["travel_note"], v["caveats"])

    def test_the_card_prints_the_caveat_when_travel_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("home", "2026-08-01T10:00:00+01:00"),
                                 ("away", "2026-08-20T02:00:00+09:00")])
            card = nightshift.render(v, {})
            self.assertIn("UTC offsets appear", card)
            self.assertIn("UTC+09:00", card)

    def test_a_negative_offset_is_labelled_with_its_sign(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("a", "2026-08-10T22:00:00-07:00")])
            self.assertEqual(v["offsets"][0]["label"], "UTC-07:00")


class TestRewrittenHistoryIsDeclared(unittest.TestCase):
    def test_an_author_date_later_than_its_committer_date_raises_the_caveat(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("rebased", "2026-08-14T12:00:00+00:00",
                                  "2026-08-13T12:00:00+00:00")])
            self.assertEqual(v["rewritten"]["commits"], 1)
            self.assertEqual(v["rewritten"]["total"], 1)
            self.assertIn("rebased", v["rewritten"]["note"])
            self.assertIn(v["rewritten"]["note"], v["caveats"])

    def test_ordinary_history_says_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, [("normal", "2026-08-14T12:00:00+00:00")])
            self.assertEqual(v["rewritten"]["commits"], 0)
            self.assertEqual(v["rewritten"]["note"], "")


# ---------------------------------------------------------------- the framing

JUDGEMENT = (
    "burnout", "unhealthy", "wellbeing", "well-being", "sleep", "health", "healthy", "tired",
    "exhausted", "overwork", "work-life", "balance", "should", "ought", "advice", "advise",
    "recommend", "suggest", "lazy", "workaholic", "grind", "toxic", "concerning", "worrying",
    "alarming", "worse", "better", "improve", "bad", "good", "wrong", "guilty", "shame",
    "too much", "cut down", "slow down", "take a break",
)


def _without_framing(text: str) -> str:
    return text.replace(nightshift.FRAMING, "").replace(nightshift.FRAMING_SHORT, "")


def _judgement_in(text: str) -> list:
    body = _without_framing(text).lower()
    return [w for w in JUDGEMENT if re.search(r"(?<![a-z]){0}(?![a-z])".format(re.escape(w)), body)]


class TestItReportsCommitsAndClaimsNothingElse(unittest.TestCase):

    COMMITS = [("tokyo night", "2026-08-19T04:12:00+09:00"),
               ("evening push", "2026-08-20T23:30:00+00:00"),
               ("oops", "2026-08-20T23:50:00+00:00"),
               ("saturday work", "2026-08-15T14:00:00+00:00"),
               ("monday", "2026-08-17T09:00:00+00:00")]

    def _view(self, tmp):
        return _run(tmp, self.COMMITS)

    def test_the_card_uses_no_judgement_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, v = self._view(tmp)
            found = _judgement_in(nightshift.render(v, {}))
            self.assertEqual(found, [], "the card judges: {0}".format(found))

    def test_the_markdown_uses_no_judgement_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, v = self._view(tmp)
            report = nightshift.report_markdown(v, {}, [s.__dict__ for s in sources])
            found = _judgement_in(report)
            self.assertEqual(found, [], "the report judges: {0}".format(found))

    def test_the_report_says_in_one_sentence_what_it_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, v = self._view(tmp)
            report = nightshift.report_markdown(v, {}, [s.__dict__ for s in sources])
            self.assertIn(nightshift.FRAMING, report)
            for phrase in ("not a measure of health", "wellbeing", "nothing here is a recommendation"):
                self.assertIn(phrase, nightshift.FRAMING)
            self.assertEqual(v["framing"], nightshift.FRAMING)

    def test_the_module_itself_offers_no_advice(self):
        source = Path("daily_core/scan/nightshift.py").read_text(encoding="utf-8")
        for phrase in ("you should", "try to", "consider ", "make sure you", "it is time to",
                       "burnout", "unhealthy", "workaholic"):
            self.assertNotIn(phrase, source.lower(), "the module advises: {0}".format(phrase))


class TestEveryNumberCarriesItsDenominator(unittest.TestCase):
    def test_the_report_prints_the_group_size_next_to_every_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, v = _run(tmp, TestSharesCarryTheirDenominator.COMMITS)
            report = nightshift.report_markdown(v, {}, [s.__dict__ for s in sources])
            self.assertIn("| 3 | 10 (30%) |", report)          # late, of ten
            self.assertIn("| 2 | 10 (20%) |", report)          # weekend, of ten
            self.assertIn("of 10 |", report)                   # hour and weekday shares
            self.assertIn("Rates are of each group", report)

    def test_the_card_prints_the_totals_beside_the_shares(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, TestSharesCarryTheirDenominator.COMMITS)
            card = nightshift.render(v, {})
            self.assertIn("30% of commits after 11pm (3 of 10)", card)
            self.assertIn("20% on weekends (2 of 10)", card)


# ---------------------------------------------------------------- rendering

class TestTheCardIsSixtyFourColumns(unittest.TestCase):
    def test_every_row_is_exactly_the_frame_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, TestSharesCarryTheirDenominator.COMMITS +
                           [("away", "2026-08-25T02:00:00+09:00")])
            card = nightshift.render(v, {})
            widths = {display_width(line) for line in card.splitlines()}
            self.assertEqual(widths, {64}, "a row escaped the frame: {0}".format(sorted(widths)))
            self.assertTrue(card.startswith("┌"))
            self.assertTrue(card.endswith("┘"))

    def test_the_heatmap_has_one_row_per_weekday(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, v = _run(tmp, TestSharesCarryTheirDenominator.COMMITS)
            card = nightshift.render(v, {})
            for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
                self.assertIn(day, card)


# ---------------------------------------------------------------- determinism

class TestDeterminism(unittest.TestCase):
    def test_the_same_records_and_the_same_now_give_an_identical_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, records, _ = _run(tmp, TestSharesCarryTheirDenominator.COMMITS)
            first = nightshift.analyse(records, NOW, CFG)
            second = nightshift.analyse(list(reversed(records)), NOW, CFG)
            self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_the_card_and_the_report_are_byte_identical_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records, _ = _run(tmp, TestSharesCarryTheirDenominator.COMMITS)
            rows = [s.__dict__ for s in sources]
            a = nightshift.analyse(records, NOW, CFG)
            b = nightshift.analyse(records, NOW, CFG)
            self.assertEqual(nightshift.render(a, {}), nightshift.render(b, {}))
            self.assertEqual(nightshift.report_markdown(a, {}, rows),
                             nightshift.report_markdown(b, {}, rows))

    def test_records_come_back_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, records, _ = _run(tmp, TestSharesCarryTheirDenominator.COMMITS)
            keys = [(r["authored"], r["repo"], r["sha"]) for r in records]
            self.assertEqual(keys, sorted(keys))


# ---------------------------------------------------------------- degradation

class TestAMissingSourceIsLabelledNotRaised(unittest.TestCase):
    def test_no_git_binary_is_a_labelled_miss_with_no_records(self):
        original = gitread.Git.find
        gitread.Git.find = classmethod(lambda cls: gitread.Git(note="git was not found"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                conf = dict(CFG)
                conf["root"] = tmp
                sources, records = nightshift.read_source("commits", Budget(), conf)
        finally:
            gitread.Git.find = original
        self.assertEqual(records, [])
        self.assertFalse(sources[0].found)
        self.assertIn("git was not found", sources[0].note)
        v = nightshift.analyse(records, NOW, dict(CFG))
        self.assertEqual(v["commits"], 0)
        nightshift.render(v, {})

    def test_a_root_with_no_repository_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            _git_or_skip()
            conf = dict(CFG)
            conf["root"] = tmp
            sources, records = nightshift.read_source("commits", Budget(), conf)
            self.assertEqual(records, [])
            self.assertFalse(sources[0].found)
            self.assertIn("no git repository", sources[0].note)

    def test_a_root_that_does_not_exist_says_so(self):
        _git_or_skip()
        conf = dict(CFG)
        conf["root"] = "/nonexistent/place/that/is/not/here"
        sources, records = nightshift.read_source("commits", Budget(), conf)
        self.assertEqual(records, [])
        self.assertFalse(sources[0].found)
        self.assertIn("no folder at", sources[0].note)

    def test_a_repository_with_no_commits_is_a_labelled_miss_beside_the_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            _git_or_skip()
            _make_repo(Path(tmp) / "real", [("a", "2026-08-10T10:00:00+00:00")])
            empty = Path(tmp) / "empty"
            empty.mkdir()
            subprocess.run([_git_or_skip().binary, "init", "-q", "-b", "main", str(empty)],
                           check=True, capture_output=True)
            conf = dict(CFG)
            conf["root"] = tmp
            sources, records = nightshift.read_source("commits", Budget(), conf)
            self.assertEqual(len(records), 1)
            misses = [s for s in sources if not s.found]
            self.assertEqual([s.name for s in misses], ["empty"])
            self.assertIn("not a repository", misses[0].note)


# ---------------------------------------------------------------- the demo path

class TestTheDemoReadsAFixtureRatherThanRunningGit(unittest.TestCase):

    ROWS = [{"repo": "demo", "sha": "aaaa1111", "name": "Ada", "email": "ada@example.com",
             "authored": "2026-08-19T04:12:00+09:00", "committed": "2026-08-19T04:12:00+09:00",
             "subject": "tokyo night"},
            {"repo": "demo", "sha": "bbbb2222", "name": "Ada", "email": "ada@example.com",
             "authored": "2026-08-17T09:00:00+01:00", "committed": "2026-08-17T09:00:00+01:00",
             "subject": "morning"}]

    def _fixture(self, tmp, rows):
        path = Path(tmp) / nightshift.DEMO_FILE
        path.write_text(json.dumps(rows), encoding="utf-8")
        return {"demo_root": tmp, "days": 90, "now": CFG["now"]}

    def test_the_fixture_feeds_the_same_analysis_as_a_real_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = self._fixture(tmp, self.ROWS)
            sources, records = nightshift.read_source("commits", Budget(), conf)
            self.assertTrue(sources[0].found)
            self.assertEqual(len(records), 2)
            v = nightshift.analyse(records, NOW, conf)
            self.assertEqual(v["commits"], 2)
            self.assertEqual(v["hours"][4], 1)
            self.assertEqual(v["hours"][9], 1)
            self.assertTrue(v["travel"])
            nightshift.render(v, {})

    def test_a_missing_fixture_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = nightshift.read_source(
                "commits", Budget(), {"demo_root": tmp, "days": 90})
            self.assertEqual(records, [])
            self.assertFalse(sources[0].found)
            self.assertIn("fixture missing", sources[0].note)

    def test_a_corrupt_fixture_is_a_labelled_miss_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / nightshift.DEMO_FILE).write_text("{not json", encoding="utf-8")
            sources, records = nightshift.read_source(
                "commits", Budget(), {"demo_root": tmp, "days": 90})
            self.assertEqual(records, [])
            self.assertFalse(sources[0].found)
            self.assertIn("unreadable", sources[0].note)


# ---------------------------------------------------------------- movement

class TestBaselineDelta(unittest.TestCase):
    def test_a_first_run_says_there_is_nothing_to_compare_against(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            _, records, _ = _run(tmp, [("a", "2026-08-10T23:30:00+00:00")])
            conf = dict(CFG)
            conf["out_dir"] = str(out)
            v = nightshift.analyse(records, NOW, conf)
            self.assertTrue(v["delta"]["first_run"])
            self.assertIn("first run", v["since"])

    def test_a_written_baseline_is_read_back_as_movement(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            _, records, _ = _run(tmp, [("a", "2026-08-10T23:30:00+00:00"),
                                       ("b", "2026-08-11T23:30:00+00:00")])
            conf = dict(CFG)
            conf["out_dir"] = str(out)
            first = nightshift.analyse(records, NOW, conf)
            nightshift.save_baseline(first, conf, NOW)
            second = nightshift.analyse(records[:1], NOW, conf)
            self.assertFalse(second["delta"]["first_run"])
            self.assertEqual(second["delta"]["shrank"]["commits"], -1)
            self.assertIn("since 2026-09-05", second["since"])
            self.assertIn("commits -1", nightshift.render(second, {}))


if __name__ == "__main__":
    unittest.main()
