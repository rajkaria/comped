"""The machinery the ten new Plays share, tested once here instead of ten times downstream.

Everything in this module is a promise some Play makes on its card: that a git call cannot be
talked into writing anything, that two addresses belonging to one human are counted as one human,
that a first run says so rather than inventing a delta, and that a heatmap's shading means the same
thing in every cell.
"""
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from daily_core import card
from daily_core.common import (Budget, baseline_read, baseline_write, delta, load_table,
                               since_note)
from daily_core.gitread import (ALLOWED, Git, coalesce, describe, discover, identity_key,
                                own_identities)

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _git_or_skip() -> Git:
    git = Git.find()
    if not git.ok:
        raise unittest.SkipTest(git.note)
    return git


def _make_repo(root: Path, commits) -> Path:
    """A real repository, because the point of these tests is the real git binary's real output."""
    git = _git_or_skip()
    subprocess.run([git.binary, "init", "-q", "-b", "main", str(root)], check=True,
                   capture_output=True)
    for i, (name, email, path, body) in enumerate(commits):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(body, encoding="utf-8")
        stamp = "2026-09-0{0}T09:00:00+00:00".format(i + 1)
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
               "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
               "PATH": "/usr/bin:/bin", "HOME": str(root)}
        subprocess.run([git.binary, "-C", str(root), "add", "-A"], check=True, capture_output=True,
                       env=env)
        subprocess.run([git.binary, "-C", str(root), "commit", "-q", "-m", "c{0}".format(i)],
                       check=True, capture_output=True, env=env)
    return root


class TestGitRunnerRefusesAnythingThatWrites(unittest.TestCase):
    def test_the_allowlist_contains_no_writing_subcommand(self):
        for banned in ("commit", "push", "add", "checkout", "reset", "gc", "fetch", "clone",
                       "merge", "rebase", "filter-branch", "update-ref", "am", "apply"):
            self.assertNotIn(banned, ALLOWED, "{0} would let this package change a repository")

    def test_a_subcommand_outside_the_allowlist_raises_rather_than_running(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            for argv in (["commit", "-m", "x"], ["push"], ["gc"], []):
                with self.assertRaises(ValueError):
                    git.run(tmp, argv)

    def test_config_is_permitted_only_in_its_reading_form(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                git.run(tmp, ["config", "user.email", "someone@example.com"])
            git.run(tmp, ["config", "--get", "user.email"])          # allowed, may return ""

    def test_a_missing_git_is_a_labelled_miss_not_an_exception(self):
        absent = Git(binary="/nonexistent/git", ok=False, note="not found")
        self.assertEqual(absent.run("/tmp", ["log"]), "")

    def test_a_directory_that_is_not_a_repository_returns_empty_not_an_error(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(git.run(tmp, ["rev-parse", "HEAD"]).strip(), "")


class TestRepositoryFacts(unittest.TestCase):
    def test_describe_reads_head_and_flags_a_repository_with_no_commits(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "r"
            _make_repo(root, [("Ada", "ada@example.com", "a.py", "one\ntwo\n")])
            repo = describe(git, root)
            self.assertTrue(repo.usable)
            self.assertEqual(len(repo.head), 40)
            self.assertFalse(repo.shallow)

            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertFalse(describe(git, empty).usable)
            self.assertIn("not a repository", describe(git, empty).note)

    def test_discover_treats_a_repository_as_a_leaf_and_skips_dependency_directories(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root / "one", [("Ada", "ada@example.com", "a.py", "x\n")])
            _make_repo(root / "nest" / "two", [("Ada", "ada@example.com", "b.py", "y\n")])
            (root / "node_modules" / "pkg").mkdir(parents=True)
            _make_repo(root / "node_modules" / "pkg", [("Ada", "ada@example.com", "c.py", "z\n")])
            found = discover(root, Budget(max_depth=6))
            names = {p.name for p in found}
            self.assertEqual(names, {"one", "two"}, "node_modules must never be descended into")


class TestIdentityCoalescing(unittest.TestCase):
    def test_a_github_noreply_address_names_the_account_and_wins(self):
        self.assertEqual(identity_key("Ada", "12345+ada@users.noreply.github.com"), "gh:ada")
        self.assertEqual(identity_key("Ada L", "ada@users.noreply.github.com"), "gh:ada")

    def test_a_plus_tag_is_the_same_person(self):
        self.assertEqual(identity_key("Ada", "ada+github@example.com"),
                         identity_key("Ada", "ada@example.com"))

    def test_two_unrelated_addresses_under_one_name_become_one_identity(self):
        merged = coalesce([("Ada Lovelace", "ada@work.example"),
                           ("Ada Lovelace", "ada@home.example"),
                           ("Charles", "charles@work.example")])
        self.assertEqual(len(merged), 2)
        ada = [i for i in merged.values() if i.display == "Ada Lovelace"][0]
        self.assertEqual(ada.emails, {"ada@work.example", "ada@home.example"})

    def test_bots_are_identifiable_so_a_play_can_exclude_them(self):
        merged = coalesce([("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
                           ("Ada", "ada@example.com")])
        self.assertEqual(sum(1 for i in merged.values() if i.is_bot), 1)

    def test_own_identities_reads_the_configured_address(self):
        git = _git_or_skip()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "r"
            _make_repo(root, [("Ada", "ada@example.com", "a.py", "x\n")])
            subprocess.run([git.binary, "-C", str(root), "config", "user.email",
                            "ada@example.com"], check=True, capture_output=True)
            self.assertIn("ada@example.com", own_identities(git, [root]))


class TestBaselineAndDelta(unittest.TestCase):
    def test_a_first_run_says_so_rather_than_inventing_a_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(baseline_read(tmp, "x"), {})
            self.assertIn("first run", since_note({}, NOW))
            self.assertTrue(delta({"a": 1}, {})["first_run"])

    def test_a_baseline_round_trips_and_reports_movement_in_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline_write(tmp, "x", {"a": 10, "b": 5, "gone": 3}, NOW)
            previous = baseline_read(tmp, "x")
            self.assertEqual(since_note(previous, NOW), "since 2026-09-05")
            moved = delta({"a": 14, "b": 2, "new": 7}, previous["payload"])
            self.assertEqual(moved["grew"], {"a": 4})
            self.assertEqual(moved["shrank"], {"b": -3})
            self.assertEqual(moved["added"], {"new": 7})
            self.assertEqual(moved["removed"], {"gone": 3})
            self.assertFalse(moved["first_run"])

    def test_a_schema_bump_degrades_to_a_first_run_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".x-baseline.json"
            p.write_text(json.dumps({"schema": 99, "payload": {"a": 1}}), encoding="utf-8")
            self.assertEqual(baseline_read(tmp, "x"), {})

    def test_a_corrupt_baseline_is_a_first_run_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".x-baseline.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(baseline_read(tmp, "x"), {})

    def test_reordering_is_not_movement(self):
        self.assertEqual(delta({"a": 1, "b": 2}, {"b": 2, "a": 1})["net"], 0)


class TestCardRenderers(unittest.TestCase):
    def test_a_heatmap_uses_one_scale_across_the_whole_grid(self):
        rows = card.heatmap([[0, 10], [5, 0]], ["Mon", "Tue"])
        self.assertEqual(len(rows), 2)
        self.assertIn("█", rows[0], "the busiest cell in the grid should be full")
        self.assertNotIn("█", rows[1], "a per-row scale would wrongly fill this one too")

    def test_an_empty_heatmap_renders_blank_rather_than_dividing_by_zero(self):
        self.assertEqual(card.heatmap([[0, 0]], ["Mon"]), ["Mon   "])

    def test_a_tier_bar_never_loses_a_small_but_real_tier(self):
        bar = card.tier_bar([("all urls", 1), ("broad", 1), ("specific", 200)], width=20)
        self.assertLessEqual(len(bar), 20)
        self.assertIn("█", bar)
        self.assertIn("▓", bar, "a tier with a real count must occupy at least one column")

    def test_a_tier_bar_with_nothing_in_it_is_empty(self):
        self.assertEqual(card.tier_bar([("a", 0), ("b", 0)]), "")

    def test_the_legend_names_only_the_tiers_that_appear(self):
        self.assertNotIn("empty", card.legend([("shown", 3), ("empty", 0)]))

    def test_renderers_are_deterministic(self):
        grid = [[3, 1], [0, 9]]
        self.assertEqual(card.heatmap(grid, ["a", "b"]), card.heatmap(grid, ["a", "b"]))
        tiers = [("x", 4), ("y", 9)]
        self.assertEqual(card.tier_bar(tiers), card.tier_bar(tiers))


class TestLookupTables(unittest.TestCase):
    def test_a_missing_table_is_an_empty_dict_not_a_failure(self):
        self.assertEqual(load_table("no-such-table-exists"), {})


if __name__ == "__main__":
    unittest.main()
