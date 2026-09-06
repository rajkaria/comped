"""bus-factor, against real repositories built by the real git binary.

Every claim this Play prints is a claim about what git said, so almost nothing here is faked: the
tests build repositories, commit as two or three distinct people (one of them a bot), write a
mailmap, make a shallow clone, and then assert on the card and the view. The fixture path is the
only synthetic one, because a repository cannot be shipped inside a repository.

These tests may start a process. The module under test may not, which the safety suite asserts
statically; here the point is the opposite, that the module's answers survive contact with git.
"""
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from daily_core.card import W
from daily_core.common import Budget
from daily_core.gitread import Git
from daily_core.scan import busfactor

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
ADA = ("Ada Lovelace", "ada@example.com")
CHARLES = ("Charles Babbage", "charles@example.com")
GRACE = ("Grace Hopper", "grace@example.com")
BOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")


def _git_or_skip() -> Git:
    git = Git.find()
    if not git.ok:
        raise unittest.SkipTest(git.note)
    return git


def _env(root: Path, who, stamp: str) -> dict:
    name, email = who
    return {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
            "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
            "PATH": "/usr/bin:/bin", "HOME": str(root),
            "GIT_CONFIG_GLOBAL": str(root / ".gitconfig"),
            "GIT_CONFIG_SYSTEM": str(root / ".gitconfig-system")}


def _make_repo(root: Path, commits) -> Path:
    """A real repository. `commits` is (who, path, body, stamp) — one commit each, in order."""
    git = _git_or_skip()
    subprocess.run([git.binary, "init", "-q", "-b", "main", str(root)], check=True,
                   capture_output=True)
    for who, path, body, stamp in commits:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        env = _env(root, who, stamp)
        subprocess.run([git.binary, "-C", str(root), "add", "-A"], check=True,
                       capture_output=True, env=env)
        subprocess.run([git.binary, "-C", str(root), "commit", "-q", "--no-gpg-sign",
                        "-m", "touch {0}".format(path)], check=True, capture_output=True, env=env)
    return root


def _lines(n: int, tag: str = "x") -> str:
    return "".join("{0} {1}\n".format(tag, i) for i in range(n))


def _stamp(day: int) -> str:
    return "2026-0{0}-{1:02d}T09:00:00+00:00".format(8 if day <= 31 else 9, min(day, 28))


def _old(days_ago_year: int = 2023) -> str:
    return "{0}-01-15T09:00:00+00:00".format(days_ago_year)


def _read(root, **cfg) -> tuple:
    conf = {"root": str(root)}
    conf.update(cfg)
    return busfactor.read_source("git", Budget(max_seconds=60.0), conf)


def _view(records, **cfg) -> dict:
    conf = {"redact": False}
    conf.update(cfg)
    return busfactor.analyse(records, NOW, conf)


class TestReadingRepositories(unittest.TestCase):
    def test_every_tracked_file_becomes_one_record_with_its_whole_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a.py", _lines(10), _stamp(1)),
                (CHARLES, "a.py", _lines(14), _stamp(2)),
                (ADA, "b.py", _lines(3), _stamp(3)),
            ])
            sources, records = _read(tmp)
            self.assertTrue(all(s.found for s in sources), [s.note for s in sources])
            paths = sorted(r["path"] for r in records)
            self.assertEqual(paths, ["a.py", "b.py"])
            a = [r for r in records if r["path"] == "a.py"][0]
            self.assertEqual(sorted(x["email"] for x in a["authors"]),
                             ["ada@example.com", "charles@example.com"])
            self.assertEqual(a["commits"], 2)
            self.assertEqual(sorted(r["repo"] for r in records), ["one", "one"])

    def test_a_file_deleted_from_head_is_not_a_tracked_file(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(Path(tmp) / "one", [
                (ADA, "keep.py", _lines(4), _stamp(1)),
                (ADA, "gone.py", _lines(4), _stamp(2)),
            ])
            env = _env(root, ADA, _stamp(3))
            (root / "gone.py").unlink()
            subprocess.run([git.binary, "-C", str(root), "add", "-A"], check=True,
                           capture_output=True, env=env)
            subprocess.run([git.binary, "-C", str(root), "commit", "-q", "--no-gpg-sign",
                            "-m", "drop"], check=True, capture_output=True, env=env)
            _, records = _read(tmp)
            self.assertEqual([r["path"] for r in records], ["keep.py"])

    def test_a_directory_with_no_repository_in_it_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = _read(tmp)
            self.assertEqual(records, [])
            self.assertEqual(len(sources), 1)
            self.assertFalse(sources[0].found)
            self.assertIn("no git repository", sources[0].note)

    def test_a_root_that_does_not_exist_is_a_labelled_miss(self):
        sources, records = _read("/nonexistent/place/for/a/test")
        self.assertEqual(records, [])
        self.assertFalse(sources[0].found)
        self.assertIn("no folder", sources[0].note)

    def test_an_empty_repository_is_a_labelled_miss_not_an_exception(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "empty"
            root.mkdir()
            subprocess.run([git.binary, "init", "-q", "-b", "main", str(root)], check=True,
                           capture_output=True)
            sources, records = _read(tmp)
            self.assertEqual(records, [])
            self.assertFalse(any(s.found for s in sources))
            self.assertTrue(sources[0].note)

    def test_no_git_binary_degrades_to_a_labelled_miss(self):
        real = busfactor.gitread.Git.find
        try:
            busfactor.gitread.Git.find = classmethod(
                lambda cls: Git(note="git was not found at any of /usr/bin/git"))
            sources, records = _read("/tmp")
            self.assertEqual(records, [])
            self.assertFalse(sources[0].found)
            self.assertIn("not found", sources[0].note)
        finally:
            busfactor.gitread.Git.find = real

    def test_a_single_repository_can_be_read_by_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(3), _stamp(1))])
            sources, records = busfactor.read_source(str(root), Budget(), {})
            self.assertTrue(sources[0].found)
            self.assertEqual([r["path"] for r in records], ["a.py"])


class TestShallowCloneIsALowerBound(unittest.TestCase):
    def test_a_shallow_clone_says_every_count_is_a_lower_bound(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            origin = _make_repo(Path(tmp) / "origin", [
                (ADA, "a.py", _lines(5), _stamp(1)),
                (CHARLES, "a.py", _lines(9), _stamp(2)),
                (GRACE, "a.py", _lines(12), _stamp(3)),
            ])
            work = Path(tmp) / "work"
            work.mkdir()
            done = subprocess.run(
                [git.binary, "clone", "-q", "--depth", "1", "--no-local",
                 "file://" + str(origin), str(work / "shallow")],
                capture_output=True, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp)})
            if done.returncode != 0:
                self.skipTest("this git will not make a shallow clone here")
            sources, records = _read(work)
            self.assertTrue(sources[0].found)
            self.assertIn("lower bound", sources[0].note)
            self.assertTrue(all(r["shallow"] for r in records))

            view = _view(records)
            self.assertTrue(view["shallow"])
            self.assertEqual(view["shallow_repos"], ["shallow"])
            self.assertIn("Shallow history", busfactor.render(view, {}))
            self.assertIn("lower bound", busfactor.report_markdown(view, {}, []))


class TestSoleAuthorship(unittest.TestCase):
    def _records(self, tmp):
        _make_repo(Path(tmp) / "one", [
            (ADA, "billing/tax.py", _lines(40), _stamp(1)),
            (ADA, "billing/invoice.py", _lines(30), _stamp(2)),
            (ADA, "shared.py", _lines(10), _stamp(3)),
            (CHARLES, "shared.py", _lines(18), _stamp(4)),
            (CHARLES, "web/app.py", _lines(12), _stamp(5)),
        ])
        return _read(tmp)[1]

    def test_a_file_only_one_person_has_ever_touched_is_a_sole_author_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = _view(self._records(tmp))
            self.assertEqual(view["tracked_files"], 4)
            self.assertEqual(view["sole_files"], 3)
            self.assertEqual(view["tiers"], [["one author", 3], ["two", 1], ["three or more", 0]])

    def test_a_file_two_people_have_touched_is_not_at_risk_even_if_one_wrote_most_of_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = _view(self._records(tmp))
            worst = [f["path"] for f in view["worst_files"]]
            self.assertNotIn("shared.py", worst)

    def test_sole_author_files_cluster_by_directory_and_the_largest_cluster_is_the_headline(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = _view(self._records(tmp))
            largest = view["largest_cluster"]
            self.assertEqual(largest["dir"], "billing/")
            self.assertEqual(largest["files"], 2)
            self.assertEqual(largest["owner"], "Ada Lovelace")
            self.assertIn("billing/", view["cluster_line"])
            self.assertIn("one name", view["cluster_line"])

    def test_the_directory_rollup_carries_its_own_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = _view(self._records(tmp))
            billing = [d for d in view["directories"] if d["dir"] == "billing/"][0]
            self.assertEqual((billing["sole_files"], billing["files"], billing["share"]), (2, 2, 100))
            root = [d for d in view["directories"] if d["dir"] == "./"]
            self.assertEqual(root, [], "shared.py has two authors, so ./ has no sole-author files")

    def test_a_headline_names_files_sole_authors_and_untouched_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = _view(self._records(tmp))
            self.assertIn("4 files.", view["headline"])
            self.assertIn("3 have exactly one author, ever.", view["headline"])
            self.assertIn("Largest cluster: one/billing/", view["cluster_line"])
            self.assertIn("untouched in a year", view["headline"])


class TestBotsAreExcluded(unittest.TestCase):
    def test_a_bot_is_not_a_second_author_and_the_exclusion_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a.py", _lines(20), _stamp(1)),
                (BOT, "a.py", _lines(24), _stamp(2)),
                (BOT, "b.py", _lines(6), _stamp(3)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["bots_excluded"], 1)
            self.assertEqual(view["bot_rows"], 2)
            self.assertIn("dependabot[bot]", view["bot_names"])
            self.assertEqual(view["sole_files"], 1, "a.py is Ada's alone; the bot is not an author")
            self.assertEqual(view["author_count"], 1)
            self.assertEqual(view["unattributed_files"], 1, "b.py has only a bot on it")
            self.assertIn("dependabot", busfactor.report_markdown(view, {}, []))

    def test_a_bot_never_appears_in_the_risk_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (BOT, "vendored.py", _lines(400), _stamp(1)),
                (ADA, "a.py", _lines(5), _stamp(2)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual([a["name"] for a in view["risk"]], ["Ada Lovelace"])


class TestExclusions(unittest.TestCase):
    def test_vendored_generated_and_lock_files_are_excluded_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "src/real.py", _lines(10), _stamp(1)),
                (ADA, "vendor/other/lib.py", _lines(900), _stamp(2)),
                (ADA, "package-lock.json", _lines(4000), _stamp(3)),
                (ADA, "static/site.min.js", _lines(50), _stamp(4)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["tracked_files"], 1)
            self.assertEqual(view["excluded_paths"], 3)
            self.assertEqual(sorted(view["excluded_examples"]),
                             ["package-lock.json", "static/site.min.js", "vendor/other/lib.py"])

    def test_the_patterns_are_a_module_level_constant_a_reader_can_check(self):
        self.assertIsInstance(busfactor.EXCLUDED_PATTERNS, tuple)
        self.assertGreater(len(busfactor.EXCLUDED_PATTERNS), 10)
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(3), _stamp(1))])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["excluded_patterns"], list(busfactor.EXCLUDED_PATTERNS))


class TestTruckFactor(unittest.TestCase):
    def test_one_author_who_owns_everything_gives_a_truck_factor_of_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a.py", _lines(50), _stamp(1)),
                (ADA, "b.py", _lines(50), _stamp(2)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["truck_factor"]["n"], 1)
            self.assertEqual(view["truck_factor"]["who"], ["Ada Lovelace"])
            self.assertGreater(view["truck_factor"]["orphaned_share"], 50)

    def test_two_authors_who_own_exactly_half_each_need_two_departures(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a.py", _lines(50), _stamp(1)),
                (CHARLES, "b.py", _lines(50), _stamp(2)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["truck_factor"]["n"], 2,
                             "exactly half is not more than half; the test is a strict inequality")
            self.assertEqual(view["truck_factor"]["of"], 2)

    def test_the_larger_of_two_disjoint_owners_can_be_the_whole_truck_factor(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a.py", _lines(50), _stamp(1)),
                (CHARLES, "b.py", _lines(20), _stamp(2)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["truck_factor"]["n"], 1)
            self.assertEqual(view["truck_factor"]["who"], ["Ada Lovelace"])

    def test_a_file_everybody_has_touched_is_orphaned_only_when_everybody_goes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "shared.py", _lines(30), _stamp(1)),
                (CHARLES, "shared.py", _lines(60), _stamp(2)),
                (GRACE, "shared.py", _lines(90), _stamp(3)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["truck_factor"]["n"], 3,
                             "no subset of the three orphans a file all three have touched")

    def test_the_threshold_is_configurable_and_reported_with_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a.py", _lines(60), _stamp(1)),
                (CHARLES, "b.py", _lines(20), _stamp(2)),
                (GRACE, "c.py", _lines(20), _stamp(3)),
            ])
            records = _read(tmp)[1]
            low = _view(records, threshold=0.1)
            high = _view(records, threshold=0.9)
            self.assertEqual(low["truck_factor"]["n"], 1)
            self.assertEqual(high["truck_factor"]["n"], 3)
            self.assertEqual(low["truck_factor"]["threshold_pct"], 10)

    def test_the_method_says_it_is_greedy_on_the_card_and_in_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(5), _stamp(1))])
            view = _view(_read(tmp)[1])
            self.assertIn("greedy", view["truck_factor"]["method"])
            self.assertIn("greedy", busfactor.render(view, {}))
            self.assertIn("greedy", busfactor.report_markdown(view, {}, []))

    def test_the_file_weighted_answer_is_computed_as_well_as_the_line_weighted_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "big.py", _lines(400), _stamp(1)),
                (CHARLES, "one.py", _lines(2), _stamp(2)),
                (CHARLES, "two.py", _lines(2), _stamp(3)),
                (CHARLES, "three.py", _lines(2), _stamp(4)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["truck_factor"]["n"], 1, "Ada owns most of the lines")
            self.assertEqual(view["truck_factor_files"]["unit"], "files")
            self.assertEqual(view["truck_factor_files"]["total"], 4)


class TestMailmapAndIdentity(unittest.TestCase):
    def test_a_mailmap_makes_two_addresses_one_author(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "one"
            _make_repo(root, [
                (("Ada Lovelace", "ada@work.example"), "a.py", _lines(10), _stamp(1)),
                (("A. Lovelace", "ada@home.example"), "a.py", _lines(14), _stamp(2)),
                ((".mailmap seed", "seed@example.com"), "seed.txt", "seed\n", _stamp(3)),
            ])
            view_without = _view(_read(tmp)[1])
            self.assertEqual(len(view_without["authors"]), 3)

            (root / ".mailmap").write_text(
                "Ada Lovelace <ada@work.example> <ada@home.example>\n", encoding="utf-8")
            git = _git_or_skip()
            env = _env(root, ADA, _stamp(4))
            subprocess.run([git.binary, "-C", str(root), "add", "-A"], check=True,
                           capture_output=True, env=env)
            subprocess.run([git.binary, "-C", str(root), "commit", "-q", "--no-gpg-sign",
                            "-m", "mailmap"], check=True, capture_output=True, env=env)

            records = _read(tmp)[1]
            a = [r for r in records if r["path"] == "a.py"][0]
            self.assertEqual({x["email"] for x in a["authors"]}, {"ada@work.example"},
                             "%aE must resolve both addresses through the repository's mailmap")
            self.assertEqual(len(a["authors"]), 1)

    def test_one_name_over_two_unrelated_addresses_is_still_one_author(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (("Ada Lovelace", "ada@work.example"), "a.py", _lines(10), _stamp(1)),
                (("Ada Lovelace", "ada@home.example"), "a.py", _lines(14), _stamp(2)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["author_count"], 1)
            self.assertEqual(view["sole_files"], 1)

    def test_the_same_person_across_repositories_is_one_risk_not_several(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(10), _stamp(1))])
            _make_repo(Path(tmp) / "two", [(ADA, "b.py", _lines(10), _stamp(2))])
            view = _view(_read(tmp)[1])
            self.assertEqual(view["repo_count"], 2)
            self.assertEqual(len(view["cross_repo"]), 1)
            self.assertEqual(view["cross_repo"][0]["repos"], ["one", "two"])
            self.assertEqual(view["cross_repo"][0]["files"], 2)
            self.assertIn("Across repositories", busfactor.report_markdown(view, {}, []))


class TestDepartedAuthors(unittest.TestCase):
    def test_a_sole_author_who_has_not_committed_in_a_year_is_reported_as_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (CHARLES, "old/thing.py", _lines(40), _old(2023)),
                (ADA, "new/thing.py", _lines(40), _stamp(1)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual([a["name"] for a in view["departed"]], ["Charles Babbage"])
            self.assertGreater(view["departed"][0]["idle_days"], 365)
            self.assertIn("ALREADY GONE", busfactor.render(view, {}))

    def test_the_departure_window_is_configurable(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(CHARLES, "a.py", _lines(4), _old(2023))])
            self.assertEqual(len(_view(_read(tmp)[1], departed_days=100000)["departed"]), 0)


class TestKnowledgeAtRisk(unittest.TestCase):
    def test_risk_rises_with_lines_with_age_and_with_being_referenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "billing/settlement.py", _lines(100), _stamp(1)),
                (ADA, "billing/settlement_test.py", _lines(10), _stamp(2)),
                (ADA, "web/settlement_view.py", _lines(10), _stamp(3)),
                (CHARLES, "web/tiny.py", _lines(2), _stamp(4)),
            ])
            view = _view(_read(tmp)[1])
            top = view["risk"][0]
            self.assertEqual(top["name"], "Ada Lovelace")
            self.assertGreater(top["risk"], view["risk"][1]["risk"])
            settlement = [f for f in view["worst_files"] if f["path"] == "billing/settlement.py"][0]
            self.assertGreaterEqual(settlement["referenced_by"], 2,
                                    "two other paths carry the settlement token")

    def test_a_generic_stem_is_never_counted_as_a_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "a/index.py", _lines(10), _stamp(1)),
                (ADA, "b/index.py", _lines(10), _stamp(2)),
                (ADA, "c/index.py", _lines(10), _stamp(3)),
            ])
            view = _view(_read(tmp)[1])
            self.assertEqual({f["referenced_by"] for f in view["worst_files"]}, {0})

    def test_the_rule_behind_the_reference_count_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(3), _stamp(1))])
            md = busfactor.report_markdown(_view(_read(tmp)[1]), {}, [])
            self.assertIn("referenced", md)
            self.assertIn("generic names", md)
            self.assertIn("lines added over the file's history", md)

    def test_both_a_line_weighted_and_a_file_weighted_author_view_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "big.py", _lines(200), _stamp(1)),
                (CHARLES, "a.py", _lines(3), _stamp(2)),
                (CHARLES, "b.py", _lines(3), _stamp(3)),
                (CHARLES, "c.py", _lines(3), _stamp(4)),
            ])
            view = _view(_read(tmp)[1])
            by_lines = view["authors"][0]
            self.assertEqual(by_lines["name"], "Ada Lovelace")
            charles = [a for a in view["authors"] if a["name"] == "Charles Babbage"][0]
            self.assertEqual((charles["files"], charles["majority_files"]), (3, 3))
            self.assertEqual((by_lines["files"], by_lines["majority_files"]), (1, 1))


class TestRedaction(unittest.TestCase):
    def _view_and_card(self, tmp, redact):
        _make_repo(Path(tmp) / "one", [
            (ADA, "billing/tax.py", _lines(40), _stamp(1)),
            (CHARLES, "web/app.py", _lines(20), _stamp(2)),
        ])
        view = busfactor.analyse(_read(tmp)[1], NOW, {"redact": redact})
        return view, busfactor.render(view, {})

    def test_redaction_is_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(4), _stamp(1))])
            view = busfactor.analyse(_read(tmp)[1], NOW, {})
            self.assertTrue(view["redacted"])
            self.assertEqual(view["authors"][0]["name"][:2], "A.")

    def test_a_redacted_name_is_initials_plus_a_stable_short_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            view, card = self._view_and_card(tmp, True)
            name = view["risk"][0]["name"]
            self.assertNotIn("Lovelace", card)
            self.assertNotIn("Babbage", card)
            self.assertIn("·", name)
            initials, _, short = name.partition("·")
            self.assertEqual(len(short), 6)
            self.assertTrue(all(c in "0123456789abcdef" for c in short))
            again = busfactor.analyse(_read(tmp)[1], NOW, {"redact": True})
            self.assertEqual(again["risk"][0]["name"], name, "the hash must be stable")

    def test_no_email_address_ever_reaches_the_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (("ada", "ada@example.com"), "billing/tax.py", _lines(40), _stamp(1)),
                (CHARLES, "web/app.py", _lines(20), _stamp(2)),
            ])
            records = _read(tmp)[1]
            for redact in (True, False):
                view = busfactor.analyse(records, NOW, {"redact": redact})
                card = busfactor.render(view, {})
                self.assertNotIn("@", card, "an address must never leave on a card")
                self.assertNotIn("example.com", busfactor.report_markdown(view, {}, []))

    def test_turning_redaction_off_shows_the_name_git_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            view, card = self._view_and_card(tmp, False)
            self.assertIn("Ada Lovelace", card)
            self.assertNotIn("·", view["risk"][0]["name"])


class TestDemoFixture(unittest.TestCase):
    RECORDS = [
        {"repo": "demo", "repo_path": "/demo", "shallow": False, "path": "billing/tax.py",
         "authors": [{"name": "Ada Lovelace", "email": "ada@example.com", "lines": 400,
                      "deleted": 10, "commits": 9, "first": 1690000000, "last": 1750000000}],
         "commits": 9, "last": 1750000000},
        {"repo": "demo", "repo_path": "/demo", "shallow": False, "path": "web/app.py",
         "authors": [{"name": "Ada Lovelace", "email": "ada@example.com", "lines": 20,
                      "deleted": 0, "commits": 1, "first": 1690000000, "last": 1750000000},
                     {"name": "Grace Hopper", "email": "grace@example.com", "lines": 30,
                      "deleted": 2, "commits": 3, "first": 1700000000, "last": 1760000000}],
         "commits": 4, "last": 1760000000},
    ]

    def _fixture(self, tmp, payload):
        root = Path(tmp) / "busfactor"
        root.mkdir(parents=True, exist_ok=True)
        (root / busfactor.FIXTURE).write_text(json.dumps(payload), encoding="utf-8")
        return root

    def test_the_demo_reads_the_bundled_records_instead_of_running_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp, {"records": self.RECORDS})
            sources, records = busfactor.read_source("git", Budget(), {"demo_root": str(root)})
            self.assertTrue(sources[0].found)
            self.assertEqual(len(records), 2)
            view = _view(records)
            self.assertEqual(view["sole_files"], 1)
            self.assertTrue(busfactor.render(view, {}).startswith("┌"))

    def test_a_bare_list_is_accepted_as_well_as_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp, self.RECORDS)
            sources, records = busfactor.read_source("git", Budget(), {"demo_root": str(root)})
            self.assertTrue(sources[0].found)
            self.assertEqual(len(records), 2)

    def test_a_missing_or_corrupt_fixture_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = busfactor.read_source("git", Budget(),
                                                     {"demo_root": str(Path(tmp) / "nowhere")})
            self.assertFalse(sources[0].found)
            self.assertIn("fixture missing", sources[0].note)

            root = Path(tmp) / "busfactor"
            root.mkdir()
            (root / busfactor.FIXTURE).write_text("{not json", encoding="utf-8")
            sources, records = busfactor.read_source("git", Budget(), {"demo_root": str(root)})
            self.assertFalse(sources[0].found)
            self.assertEqual(records, [])


class TestBaselineAndDelta(unittest.TestCase):
    def test_a_first_run_says_so_and_a_second_run_reports_what_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "work"
            root.mkdir()
            _make_repo(root / "one", [(ADA, "a.py", _lines(10), _stamp(1))])
            out = Path(tmp) / "out"
            out.mkdir()
            first = _view(_read(root)[1], out_dir=str(out))
            self.assertTrue(first["delta"]["first_run"])
            self.assertIn("first run", first["since"])
            busfactor.save_baseline(first, {"out_dir": str(out)}, NOW)

            git = _git_or_skip()
            env = _env(root / "one", ADA, _stamp(5))
            (root / "one" / "b.py").write_text(_lines(20), encoding="utf-8")
            subprocess.run([git.binary, "-C", str(root / "one"), "add", "-A"], check=True,
                           capture_output=True, env=env)
            subprocess.run([git.binary, "-C", str(root / "one"), "commit", "-q", "--no-gpg-sign",
                            "-m", "more"], check=True, capture_output=True, env=env)

            second = _view(_read(root)[1], out_dir=str(out))
            self.assertFalse(second["delta"]["first_run"])
            self.assertEqual(second["delta"]["grew"]["tracked_files"], 1)
            self.assertEqual(second["delta"]["grew"]["sole_files"], 1)
            self.assertIn("Since the last run", busfactor.report_markdown(second, {}, []))

    def test_analysing_twice_does_not_invent_a_delta_against_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(4), _stamp(1))])
            out = Path(tmp) / "out"
            out.mkdir()
            records = _read(tmp)[1]
            self.assertEqual(_view(records, out_dir=str(out))["delta"],
                             _view(records, out_dir=str(out))["delta"])


class TestRendering(unittest.TestCase):
    def _view(self, tmp):
        _make_repo(Path(tmp) / "one", [
            (ADA, "billing/tax.py", _lines(40), _stamp(1)),
            (ADA, "billing/invoice.py", _lines(30), _stamp(2)),
            (CHARLES, "web/app.py", _lines(20), _stamp(3)),
            (GRACE, "web/app.py", _lines(10), _stamp(4)),
        ])
        return _view(_read(tmp)[1])

    def test_every_card_row_is_exactly_the_card_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            from daily_core.common import display_width
            for line in busfactor.render(self._view(tmp), {}).splitlines():
                self.assertEqual(display_width(line), W, repr(line))

    def test_the_card_splits_files_by_author_count_with_a_legend_under_the_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = busfactor.render(self._view(tmp), {})
            self.assertIn("AUTHORS PER FILE", card)
            self.assertIn("█ one author", card)
            self.assertIn("▓ two", card)

    def test_the_card_survives_having_nothing_to_say(self):
        card = busfactor.render(busfactor.analyse([], NOW, {}), {})
        self.assertIn("No tracked file could be read", card)
        self.assertTrue(card.endswith("┘"))

    def test_the_report_gives_every_number_a_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._view(tmp)
            md = busfactor.report_markdown(view, {}, [{"name": "one", "found": True, "note": "n"}])
            self.assertIn("| tracked files | 3 | 3 scanned, 0 excluded |", md)
            self.assertIn("| files with exactly one author | 2 (67%) | 3 attributed |", md)
            self.assertIn("| 2 of 2 | 70 of 70 |", md)
            self.assertIn("## Sources", md)
            self.assertIn("| one | yes | n |", md)
            self.assertIn("nothing left this machine", md)

    def test_the_view_carries_the_keys_a_step_reports_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._view(tmp)
            for key in ("tracked_files", "sole_files", "truck_factor", "largest_cluster", "risk",
                        "departed", "clusters", "repos", "cross_repo", "delta", "excluded_paths",
                        "bots_excluded", "tiers", "shallow", "headline", "verdict"):
                self.assertIn(key, view)


class TestDeterminism(unittest.TestCase):
    def test_the_same_records_and_the_same_now_give_the_identical_card_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [
                (ADA, "billing/tax.py", _lines(40), _stamp(1)),
                (CHARLES, "billing/tax.py", _lines(12), _stamp(2)),
                (GRACE, "web/app.py", _lines(20), _stamp(3)),
                (BOT, "web/app.py", _lines(8), _stamp(4)),
            ])
            records = _read(tmp)[1]
            first = _view(records)
            second = _view(list(reversed(records)))
            self.assertEqual(json.dumps(first, sort_keys=True, default=str),
                             json.dumps(second, sort_keys=True, default=str),
                             "record order must not change a single number")
            self.assertEqual(busfactor.render(first, {}), busfactor.render(second, {}))
            self.assertEqual(busfactor.report_markdown(first, {}, []),
                             busfactor.report_markdown(second, {}, []))

    def test_two_reads_of_one_repository_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_repo(Path(tmp) / "one", [(ADA, "a.py", _lines(6), _stamp(1))])
            self.assertEqual(_read(tmp)[1], _read(tmp)[1])


class TestPathDecoding(unittest.TestCase):
    def test_a_quoted_non_ascii_path_is_decoded_rather_than_counted_twice(self):
        self.assertEqual(busfactor._unquote('"src/caf\\303\\251.py"'), "src/café.py")
        self.assertEqual(busfactor._unquote("src/plain.py"), "src/plain.py")
        self.assertEqual(busfactor._unquote('"a\\tb.py"'), "a\tb.py")

    def test_a_binary_numstat_row_is_a_commit_against_a_file_of_no_known_size(self):
        parsed = busfactor._parse_log(
            "abc|Ada|ada@example.com|1700000000\n\n-\t-\timage.png\n", {"image.png"})
        row = parsed["image.png"][("Ada", "ada@example.com")]
        self.assertEqual((row["lines"], row["commits"]), (0, 1))

    def test_an_author_name_containing_a_pipe_still_parses(self):
        parsed = busfactor._parse_log(
            "abc|Ada | Lovelace|ada@example.com|1700000000\n\n3\t1\ta.py\n", {"a.py"})
        self.assertEqual(list(parsed["a.py"]), [("Ada | Lovelace", "ada@example.com")])


if __name__ == "__main__":
    unittest.main()
