"""kept: does the agent's code survive, and is the comparison it is judged against a fair one?

The claim on this card is unusually easy to get wrong in a flattering direction, so the tests are
built around a real repository with a real history rather than around fixtures: a real `git blame`
of a real HEAD, real commits inside and outside a real session window, a real deletion and a real
revert. Every number the card prints is asserted against a history whose arithmetic is written out
by hand above the assertion.

The single most important test in this file is the one that says the human control group is
computed and printed. A survival percentage with nothing beside it is a rhetorical device; the
same percentage next to the same measurement of hand-written lines in the same files is evidence.
"""
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from daily_core.common import Budget
from daily_core.gitread import Git
from daily_core.parsers import agentedits
from daily_core.parsers.blame import parse_porcelain
from daily_core.scan import kept

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

HUMAN = ("Ada Lovelace", "ada@example.com")
BOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")

# The session, and therefore the window: 10:05 to 10:15 plus 30 minutes of grace, so 10:05-10:45.
WINDOW_EDITS = ("2026-09-01T10:05:00.000Z", "2026-09-01T10:15:00.000Z")


def _git_or_skip() -> Git:
    git = Git.find()
    if not git.ok:
        raise unittest.SkipTest(git.note)
    return git


def _body(n: int, tag: str) -> str:
    return "".join("{0} line {1}\n".format(tag, i) for i in range(n))


def _run(git: Git, root: Path, args, env=None):
    subprocess.run([git.binary, "-C", str(root)] + list(args), check=True, capture_output=True,
                   env=env)


def _commit(git: Git, root: Path, who, when: str, changes: dict, message: str, body: str = ""):
    """One commit with an author time we choose, which is the whole basis of the attribution."""
    for rel, content in sorted(changes.items()):
        target = root / rel
        if content is None:
            if target.exists():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1],
           "GIT_COMMITTER_NAME": who[0], "GIT_COMMITTER_EMAIL": who[1],
           "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
           "PATH": "/usr/bin:/bin", "HOME": str(root)}
    _run(git, root, ["add", "-A"], env)
    args = ["commit", "-q", "--no-gpg-sign", "-m", message]
    if body:
        args += ["-m", body]
    _run(git, root, args, env)
    return _run_out(git, root, ["rev-parse", "HEAD"])


def _run_out(git: Git, root: Path, args) -> str:
    done = subprocess.run([git.binary, "-C", str(root)] + list(args), capture_output=True,
                          check=True)
    return done.stdout.decode("utf-8").strip()


def _make_history(root: Path) -> dict:
    """A repository whose arithmetic is known exactly.

        H1  1 Aug   human     app.py +30, keep.py +40
        A1  1 Sep 10:10  IN WINDOW   app.py +40, gone.py +25, alive.py +30
        A2  1 Sep 10:20  IN WINDOW   undone.py +22
        H2  2 Sep 09:00  human     deletes gone.py, keep.py +15
        H3  2 Sep 10:00  human     deletes undone.py, reverting A2

    So the agent wrote 117 lines into four files. 70 of them are still at HEAD (app.py's 40 and
    alive.py's 30). 25 went with a deleted file, 22 were reverted, none were merely rewritten.
    The control group is the 30 hand-written lines of app.py, all of which are still there --
    keep.py's 55 lines are deliberately not in it, because the agent never touched that file.
    """
    git = _git_or_skip()
    root.mkdir(parents=True, exist_ok=True)
    _run(git, root, ["init", "-q", "-b", "main"])
    _run(git, root, ["config", "user.email", HUMAN[1]])
    _run(git, root, ["config", "user.name", HUMAN[0]])
    shas = {}
    shas["H1"] = _commit(git, root, HUMAN, "2026-08-01T09:00:00+00:00",
                         {"src/app.py": _body(30, "human"), "src/keep.py": _body(40, "human")},
                         "start the app")
    shas["A1"] = _commit(git, root, HUMAN, "2026-09-01T10:10:00+00:00",
                         {"src/app.py": _body(30, "human") + _body(40, "agent"),
                          "src/gone.py": _body(25, "agent"),
                          "src/alive.py": _body(30, "agent")},
                         "agent: three files")
    shas["A2"] = _commit(git, root, HUMAN, "2026-09-01T10:20:00+00:00",
                         {"src/undone.py": _body(22, "agent")}, "agent: add undone")
    shas["H2"] = _commit(git, root, HUMAN, "2026-09-02T09:00:00+00:00",
                         {"src/gone.py": None, "src/keep.py": _body(55, "human")},
                         "drop the experiment")
    shas["H3"] = _commit(git, root, HUMAN, "2026-09-02T10:00:00+00:00",
                         {"src/undone.py": None}, 'Revert "agent: add undone"',
                         "This reverts commit {0}.".format(shas["A2"]))
    return shas


def _claude_transcript(root: Path, repo: Path, session: str = "s1",
                       model: str = "claude-opus-5", subagent: bool = False) -> Path:
    """A transcript in the shape Claude Code writes, including one restated (streamed) tool call."""
    project = root / "-tmp-project"
    if subagent:
        target = project / session / "subagents"
    else:
        target = project
    target.mkdir(parents=True, exist_ok=True)
    path = target / ("agent-sub.jsonl" if subagent else "{0}.jsonl".format(session))
    lines = ["", "not json at all", "[1, 2, 3]"]
    tag = "sub" if subagent else "main"
    calls = [("{0}-t1".format(tag), "Write", str(repo / "src/alive.py"), WINDOW_EDITS[0]),
             ("{0}-t2".format(tag), "Edit", str(repo / "src/app.py"), WINDOW_EDITS[1])]
    for call_id, tool, file_path, stamp in calls:
        payload = {"type": "assistant", "timestamp": stamp, "sessionId": session,
                   "cwd": str(repo),
                   "message": {"model": model, "content": [
                       {"type": "text", "text": "ignored"},
                       {"type": "tool_use", "id": call_id, "name": tool,
                        "input": ({"file_path": file_path, "content": _body(30, "agent")}
                                  if tool == "Write"
                                  else {"file_path": file_path, "old_string": "a",
                                        "new_string": _body(40, "agent")})}]}}
        lines.append(json.dumps(payload))
        lines.append(json.dumps(payload))          # the streamed restatement of the same call
    lines.append(json.dumps({"type": "assistant", "timestamp": WINDOW_EDITS[0],
                             "sessionId": session, "message": {"model": model, "content": [
                                 {"type": "tool_use", "id": "{0}-t9".format(tag), "name": "Read",
                                  "input": {"file_path": "/elsewhere/x.py"}}]}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _codex_transcript(root: Path, repo: Path) -> Path:
    day = root / "2026" / "09" / "01"
    day.mkdir(parents=True, exist_ok=True)
    path = day / "rollout-2026-09-01T10-05-00.jsonl"
    patch = ("*** Begin Patch\n*** Add File: src/alive.py\n+one\n+two\n"
             "*** Update File: src/app.py\n@@\n+three\n-four\n*** End Patch\n")
    lines = [
        json.dumps({"type": "session_meta", "timestamp": WINDOW_EDITS[0],
                    "payload": {"id": "codex-1", "cwd": str(repo)}}),
        json.dumps({"type": "turn_context", "timestamp": WINDOW_EDITS[0],
                    "payload": {"model": "gpt-5-codex", "cwd": str(repo)}}),
        json.dumps({"type": "response_item", "timestamp": WINDOW_EDITS[0],
                    "payload": {"type": "function_call", "name": "apply_patch",
                                "arguments": json.dumps({"input": patch})}}),
        json.dumps({"type": "event_msg", "timestamp": WINDOW_EDITS[1],
                    "payload": {"type": "patch_apply_begin", "changes": {
                        "src/undone.py": {"add": {"content": "a\nb\nc\n"}}}}}),
        "{oops",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _read(tmp: Path, repo: Path, claude_root: Path, cfg_extra=None) -> tuple:
    cfg = {"root": str(tmp), "claude_dir": str(claude_root),
           "codex_dir": str(tmp / "no-codex"), "pi_dir": str(tmp / "no-pi"),
           "out_dir": str(tmp / "out")}
    cfg.update(cfg_extra or {})
    sources, records = [], []
    for name in kept.SOURCES:
        found, rows = kept.read_source(name, Budget(max_seconds=30.0), cfg)
        sources += found
        records += rows
    return cfg, sources, records


class TestBlamePorcelain(unittest.TestCase):
    def test_a_real_line_porcelain_run_is_parsed_line_for_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "proj"
            shas = _make_history(repo)
            git = _git_or_skip()
            text = git.run(repo, ["blame", "--line-porcelain", "HEAD", "--", "src/app.py"])
            lines = parse_porcelain(text)
            self.assertEqual(len(lines), 70, "app.py is 30 human lines then 40 agent lines")
            self.assertEqual(lines[0].sha, shas["H1"])
            self.assertEqual(lines[-1].sha, shas["A1"])
            self.assertEqual(lines[0].author_key, "ada@example.com")
            self.assertEqual(lines[0].author_time.year, 2026)
            self.assertEqual(lines[0].author_time.month, 8)
            self.assertEqual([line.final_line for line in lines[:3]], [1, 2, 3])
            self.assertEqual(len({line.sha for line in lines}), 2)

    def test_a_repeated_commit_that_carries_its_header_only_once_is_still_attributed(self):
        """`--porcelain` names a commit's author the first time only. Later groups must inherit it."""
        text = (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1 1 2\n"
            "author Ada Lovelace\nauthor-mail <ada@example.com>\nauthor-time 1756719000\n"
            "author-tz +0000\nsummary first\nboundary\nfilename a.py\n\tone\n"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 2 2\n\ttwo\n"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 1 3 1\n"
            "author Charles\nauthor-mail <charles@example.com>\nauthor-time 1756719600\n"
            "author-tz +0000\nsummary second\nfilename a.py\n\tthree\n"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 3 4\n\tfour\n")
        lines = parse_porcelain(text)
        self.assertEqual(len(lines), 4)
        self.assertEqual([line.author_name for line in lines],
                         ["Ada Lovelace", "Ada Lovelace", "Charles", "Ada Lovelace"])
        self.assertEqual([line.author_key for line in lines],
                         ["ada@example.com", "ada@example.com", "charles@example.com",
                          "ada@example.com"])
        self.assertTrue(lines[0].boundary)
        self.assertEqual(lines[2].summary, "second")
        self.assertEqual([line.final_line for line in lines], [1, 2, 3, 4])

    def test_junk_truncation_and_emptiness_are_answers_not_exceptions(self):
        self.assertEqual(parse_porcelain(""), [])
        self.assertEqual(parse_porcelain(None), [])
        self.assertEqual(parse_porcelain("fatal: no such path\n"), [])
        cut = ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1 1 2\nauthor Ada\n"
               "author-time 1756719000\nfilename a.py\n\tone\n"
               "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 2 2 1\nauthor Cut\n")
        lines = parse_porcelain(cut)
        self.assertEqual(len(lines), 1, "the truncated final record is dropped, the rest stands")

    def test_the_rollups_count_lines_per_commit_and_per_author(self):
        from daily_core.parsers.blame import authors, by_commit
        text = ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1 1 1\nauthor Ada\n"
                "author-mail <ada@example.com>\nauthor-time 1756719000\nfilename a.py\n\tone\n"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 1 2 2\nauthor Ada\n"
                "author-mail <ada+work@example.com>\nauthor-time 1756719600\nfilename a.py\n\ttwo\n"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 2 3\n\tthree\n")
        lines = parse_porcelain(text)
        self.assertEqual(by_commit(lines), {"a" * 40: 1, "b" * 40: 2})
        self.assertEqual(authors(lines), {"ada@example.com": 3},
                         "a plus-tagged address is the same human")

    def test_a_missing_author_time_is_none_rather_than_a_wrong_instant(self):
        lines = parse_porcelain("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1 1 1\n"
                                "author Ada\nfilename a.py\n\tone\n")
        self.assertIsNone(lines[0].author_time)


class TestTranscriptReading(unittest.TestCase):
    def test_a_directory_that_does_not_exist_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"claude_dir": str(Path(tmp) / "nope"), "codex_dir": str(Path(tmp) / "nope2"),
                   "pi_dir": str(Path(tmp) / "nope3")}
            sources, records = agentedits.read_all(cfg, Budget())
            self.assertEqual(records, [])
            self.assertEqual([s.found for s in sources], [False, False, False])
            for source in sources:
                self.assertIn("no transcript directory", source.note)

    def test_claude_writes_are_read_once_including_from_a_subagent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "proj"
            claude = root / "claude"
            _claude_transcript(claude, repo)
            _claude_transcript(claude, repo, session="s1", subagent=True)
            source, edits = agentedits.read_claude(claude, Budget())
            self.assertTrue(source.found)
            self.assertEqual(len(edits), 4, "two calls per transcript, restatements collapsed")
            self.assertEqual(sum(1 for e in edits if e.subagent), 2)
            self.assertEqual({e.tool for e in edits}, {"Write", "Edit"})
            self.assertEqual({e.model for e in edits}, {"claude-opus-5"})
            self.assertNotIn("Read", [e.tool for e in edits], "reading a file is not writing one")
            write = [e for e in edits if e.tool == "Write"][0]
            self.assertEqual(write.added, 30)
            self.assertIn("restated", source.note)

    def test_codex_patch_envelopes_and_patch_events_both_yield_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _codex_transcript(root / "codex", root / "proj")
            source, edits = agentedits.read_codex(root / "codex", Budget())
            self.assertTrue(source.found)
            by_path = {e.path: e for e in edits}
            self.assertEqual(sorted(by_path), ["src/alive.py", "src/app.py", "src/undone.py"])
            self.assertEqual(by_path["src/alive.py"].added, 2)
            self.assertEqual(by_path["src/app.py"].added, 1, "a - line is not an addition")
            self.assertEqual(by_path["src/undone.py"].added, 3)
            self.assertEqual(by_path["src/app.py"].session_id, "codex-1")
            self.assertEqual(by_path["src/app.py"].model, "gpt-5-codex")

    def test_the_patch_envelope_reader_keeps_envelope_order_and_counts_only_additions(self):
        pairs = agentedits.parse_patch(
            "*** Begin Patch\n*** Update File: b.py\n@@\n+one\n-two\n+three\n"
            "*** Add File: a.py\n+alpha\n*** Delete File: c.py\n*** End Patch\n")
        self.assertEqual(pairs, [("b.py", 2), ("a.py", 1), ("c.py", 0)])


class TestAttribution(unittest.TestCase):
    def _view(self, cfg_extra=None):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        repo = root / "proj"
        self.shas = _make_history(repo)
        _claude_transcript(root / "claude", repo)
        cfg, sources, records = _read(root, repo, root / "claude", cfg_extra)
        return kept.analyse(records, NOW, cfg), cfg, sources, records

    def tearDown(self):
        tmp = getattr(self, "tmp", None)
        if tmp:
            tmp.cleanup()

    def test_only_commits_inside_the_window_are_the_agents(self):
        view, _cfg, _s, _r = self._view()
        totals = view["totals"]
        self.assertEqual(totals["ever"]["agent"], 117, "40 + 25 + 30 + 22")
        self.assertEqual(totals["alive"]["agent"], 70, "app.py's 40 and alive.py's 30")
        self.assertEqual(view["survival"]["agent"], 60)
        self.assertEqual(view["gone"], 40)
        self.assertEqual(view["sessions"]["count"], 1)
        self.assertEqual(view["repos"][0]["in_window"], 2, "H1, H2 and H3 are outside it")

    def test_the_human_control_group_is_computed_and_printed_next_to_the_agent(self):
        """The hard requirement: the number is meaningless without the one beside it."""
        view, cfg, _s, _r = self._view()
        self.assertEqual(view["totals"]["ever"]["human"], 30,
                         "app.py's hand-written lines, in the same file the agent edited")
        self.assertEqual(view["totals"]["alive"]["human"], 30)
        self.assertEqual(view["survival"]["human"], 100)
        self.assertEqual(view["survival"]["you"], 100, "the configured address is you")
        self.assertIsNotNone(view["survival"]["control"])
        self.assertEqual(view["survival"]["gap"], 40, "the agent is 40 points worse here")

        card = kept.render(view, cfg)
        self.assertIn("60%", card)
        self.assertIn("100%", card)
        self.assertIn("hand-written", card)
        report = kept.report_markdown(view, cfg, [])
        self.assertIn("control group", report)
        self.assertIn("| the agent |", report)

    def test_files_never_touched_by_the_agent_stay_out_of_the_control_group(self):
        view, _cfg, _s, _r = self._view()
        self.assertEqual(view["totals"]["ever"]["human"], 30,
                         "keep.py's 55 hand-written lines must not inflate the control group")
        paths = sorted(r["key"] for r in view["directories"])
        self.assertEqual(paths, ["proj/src"])

    def test_lines_in_a_file_that_no_longer_exists_count_as_not_survived(self):
        view, _cfg, _s, _r = self._view()
        self.assertEqual(view["deleted"]["files"], 2, "gone.py and undone.py")
        self.assertEqual(view["deleted"]["total_lines"], 47)
        self.assertEqual(view["classes"]["deleted_with_file"], 25,
                         "undone.py's 22 belong to the revert class, not this one")
        self.assertEqual(view["classes"]["alive"] + view["classes"]["reverted"]
                         + view["classes"]["deleted_with_file"] + view["classes"]["rewritten"],
                         view["totals"]["ever"]["agent"], "the classes partition what was written")

    def test_a_reverted_commit_is_its_own_class_and_not_ordinary_churn(self):
        view, _cfg, _s, _r = self._view()
        self.assertEqual(view["reverts"]["count"], 1)
        self.assertEqual(view["reverts"]["lines"], 22)
        self.assertEqual(view["reverts"]["same_day"], 1, "reverted 23 hours later")
        self.assertEqual(view["reverts"]["items"][0]["sha"], self.shas["A2"][:8])
        self.assertEqual(view["classes"]["rewritten"], 0, "nothing here was merely rewritten")
        self.assertIn("UNDONE", kept.render(view, {}))

    def test_the_half_life_buckets_place_each_commit_by_its_own_age(self):
        view, _cfg, _s, _r = self._view()
        buckets = {b["label"]: b for b in view["half_life"]["buckets"]}
        self.assertEqual(sorted(buckets), ["1 month", "1 week", "older", "same day"])
        self.assertEqual(buckets["same day"]["ever"], 0)
        self.assertEqual(buckets["1 week"]["ever"], 117, "both agent commits are four days old")
        self.assertEqual(buckets["1 week"]["alive"], 70)
        self.assertEqual(buckets["1 week"]["rate"], 60)
        self.assertEqual(buckets["older"]["human_ever"], 30, "H1 is five weeks old")
        self.assertIsNone(view["half_life"]["days"],
                          "more than half survives, so there is no median yet")
        self.assertIn("still standing", view["half_life"]["note"])

    def test_a_group_under_the_floor_is_unrated_rather_than_given_a_percentage(self):
        view, _cfg, _s, _r = self._view({"min_lines": 200})
        self.assertIsNone(view["survival"]["agent"])
        self.assertIsNone(view["survival"]["human"])
        self.assertEqual(view["min_lines"], 200)
        self.assertIsNone(view["worst_directory"], "nothing clears the floor, so nothing is named")
        self.assertIn("floor", kept.render(view, {}))

    def test_a_floor_of_zero_is_a_setting_and_not_an_unset_key(self):
        view, _cfg, _s, _r = self._view({"min_lines": 0})
        self.assertEqual(view["min_lines"], 0)
        buckets = {b["label"]: b for b in view["half_life"]["buckets"]}
        self.assertIsNone(buckets["same day"]["rate"], "an empty group is still never rated")
        self.assertEqual(buckets["older"]["human_rate"], 100)

    def test_the_floor_lets_the_real_groups_through_and_names_the_worst_directory(self):
        view, _cfg, _s, _r = self._view()
        worst = view["worst_directory"]
        self.assertIsNotNone(worst)
        self.assertEqual(worst["key"], "proj/src")
        self.assertEqual(worst["rate"], 60)
        languages = {row["key"]: row for row in view["languages"]}
        self.assertEqual(languages[".py"]["ever"], 117)

    def test_the_grace_period_decides_a_commit_on_the_edge(self):
        view, _cfg, _s, _r = self._view({"grace_minutes": 1})
        self.assertEqual(view["repos"][0]["in_window"], 1,
                         "A2 at 10:20 falls outside a window that closes at 10:16")
        self.assertEqual(view["totals"]["ever"]["agent"], 95, "117 less undone.py's 22")

    def test_every_repository_carries_a_confidence_label_and_a_reason(self):
        view, _cfg, _s, _r = self._view()
        self.assertEqual(len(view["confidence"]), 1)
        row = view["confidence"][0]
        self.assertIn(row["level"], ("high", "medium", "low", "none"))
        self.assertEqual(row["coverage"], 40, "2 of 5 commits are in a window")
        self.assertTrue(row["why"])

    def test_the_attribution_rule_is_printed_verbatim_in_the_report(self):
        view, cfg, sources, _r = self._view()
        rule = kept.attribution_rule(view["grace_minutes"])
        self.assertEqual(view["rule"], rule)
        report = kept.report_markdown(view, cfg, [s.__dict__ for s in sources])
        self.assertIn(rule, report)
        self.assertIn("How a line is attributed", report)

    def test_a_baseline_round_trips_into_a_delta_block(self):
        view, cfg, _s, records = self._view()
        self.assertTrue(view["delta"]["first_run"])
        self.assertIn("first run", view["since"])
        kept.save_baseline(view, cfg, NOW)
        again = kept.analyse(records, NOW, cfg)
        self.assertFalse(again["delta"]["first_run"])
        self.assertEqual(again["delta"]["net"], 0)
        self.assertIn("since 2026-09-05", again["since"])

    def test_the_same_input_and_the_same_clock_give_the_same_answer(self):
        view, cfg, _s, records = self._view()
        second = kept.analyse(records, NOW, cfg)
        self.assertEqual(json.dumps(view, sort_keys=True, default=str),
                         json.dumps(second, sort_keys=True, default=str))
        self.assertEqual(kept.render(view, cfg), kept.render(second, cfg))

    def test_the_card_and_the_report_render_without_a_missing_key(self):
        view, cfg, sources, _r = self._view()
        card = kept.render(view, cfg)
        self.assertTrue(card.startswith("┌"))
        self.assertTrue(card.endswith("┘"))
        self.assertTrue(all(len(line) <= 200 for line in card.splitlines()))
        self.assertIn("KEPT", card)
        report = kept.report_markdown(view, cfg, [s.__dict__ for s in sources])
        for heading in ("# Kept", "## Half-life", "## By repository", "## Confidence",
                        "## Where it went", "## Sources"):
            self.assertIn(heading, report)


class TestDegradation(unittest.TestCase):
    def test_no_transcripts_at_all_still_produces_a_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_history(root / "proj")
            cfg, sources, records = _read(root, root / "proj", root / "no-claude")
            self.assertFalse(any(s.found for s in sources if "claude" in s.name))
            view = kept.analyse(records, NOW, cfg)
            self.assertEqual(view["sessions"]["count"], 0)
            self.assertEqual(view["totals"]["ever"]["agent"], 0)
            self.assertIsNone(view["survival"]["agent"])
            self.assertIn("no agent session", view["confidence"][0]["why"]
                          if view["confidence"] else "no agent session")
            self.assertIn("KEPT", kept.render(view, cfg))

    def test_no_repository_under_the_root_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "empty").mkdir()
            sources, records = kept.read_source("git", Budget(), {"root": str(root / "empty")})
            self.assertFalse(sources[0].found)
            self.assertIn("no git repository", sources[0].note)
            self.assertEqual(records, [])

    def test_writes_into_a_directory_that_is_not_a_repository_are_counted_as_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _claude_transcript(root / "claude", root / "not-a-repo")
            cfg = {"out_dir": str(root / "out")}
            _sources, records = agentedits.read_all(
                {"claude_dir": str(root / "claude"), "codex_dir": str(root / "x"),
                 "pi_dir": str(root / "y")}, Budget())
            view = kept.analyse(records, NOW, cfg)
            self.assertEqual(view["sessions"]["count"], 0)
            self.assertEqual(view["sessions"]["orphans"], 1)
            self.assertEqual(view["sessions"]["orphan_writes"], 2)

    def test_an_unknown_source_name_is_a_miss_rather_than_a_crash(self):
        sources, records = kept.read_source("moon", Budget(), {})
        self.assertFalse(sources[0].found)
        self.assertEqual(records, [])

    def test_malformed_records_are_dropped_and_the_rest_still_counts(self):
        view = kept.analyse([{"kind": "edit"}, {"kind": "edit", "path": "/x", "timestamp": "nope"},
                             "not a dict", {"kind": "unknown"}], NOW, {})
        self.assertEqual(view["sessions"]["count"], 0)
        self.assertEqual(view["totals"]["ever"]["agent"], 0)


class TestReplayedDocument(unittest.TestCase):
    """The demo path: the same analysis, fed a recorded document instead of a machine."""

    FIXTURE = {"records": [
        {"kind": "edit", "session_id": "d1", "harness": "claude-code", "model": "claude-opus-5",
         "repo_hint": "/demo/acme", "path": "/demo/acme/a.py",
         "timestamp": "2026-09-01T10:00:00Z", "added": 40, "tool": "Write"},
        {"kind": "repo", "path": "/demo/acme", "name": "acme", "head": "h", "shallow": False},
        {"kind": "own", "keys": ["ada@example.com"]},
        {"kind": "commits", "repo": "/demo/acme", "commits": [
            {"sha": "a" * 40, "at": "2026-09-01T10:05:00Z", "name": "Ada",
             "email": "ada@example.com", "subject": "agent work", "body": "",
             "files": [["a.py", 40, 0], ["b.py", 30, 0]]},
            {"sha": "b" * 40, "at": "2026-08-01T09:00:00Z", "name": "Ada",
             "email": "ada@example.com", "subject": "by hand", "body": "",
             "files": [["a.py", 25, 0]]}]},
        {"kind": "tracked", "repo": "/demo/acme", "paths": ["a.py"]},
        {"kind": "blame", "repo": "/demo/acme", "lines": {"a.py": (
            [["a" * 40, "2026-09-01T10:05:00Z", "ada@example.com"]] * 22 +
            [["b" * 40, "2026-08-01T09:00:00Z", "ada@example.com"]] * 25)}},
    ]}

    def test_the_recorded_document_drives_the_same_arithmetic(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "kept"
            demo.mkdir()
            (demo / "kept.json").write_text(json.dumps(self.FIXTURE), encoding="utf-8")
            cfg = {"demo_root": str(demo), "out_dir": tmp}
            sources, records = [], []
            for name in kept.SOURCES:
                found, rows = kept.read_source(name, Budget(), cfg)
                sources += found
                records += rows
            self.assertTrue(all(s.found for s in sources))
            view = kept.analyse(records, NOW, cfg)
            self.assertEqual(view["totals"]["ever"]["agent"], 70, "a.py's 40 and b.py's 30")
            self.assertEqual(view["totals"]["alive"]["agent"], 22)
            self.assertEqual(view["survival"]["agent"], 31)
            self.assertEqual(view["totals"]["ever"]["human"], 25)
            self.assertEqual(view["survival"]["human"], 100)
            self.assertEqual(view["deleted"]["files"], 1, "b.py is not tracked at HEAD")
            self.assertIn("KEPT", kept.render(view, cfg))

    def test_a_missing_fixture_is_a_labelled_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = kept.read_source("agent", Budget(), {"demo_root": tmp})
            self.assertFalse(sources[0].found)
            self.assertEqual(records, [])


class TestLogParsing(unittest.TestCase):
    def test_the_numstat_log_format_round_trips_through_a_real_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "proj"
            shas = _make_history(repo)
            git = _git_or_skip()
            text = git.run(repo, ["log", "--no-merges", "--numstat",
                                  "--format={0}".format(kept.LOG_FORMAT), "HEAD"])
            commits = kept.parse_log(text)
            self.assertEqual(len(commits), 5)
            by_sha = {c["sha"]: c for c in commits}
            first = by_sha[shas["A1"]]
            self.assertEqual(sorted(f["path"] for f in first["files"]),
                             ["src/alive.py", "src/app.py", "src/gone.py"])
            self.assertEqual({f["path"]: f["added"] for f in first["files"]}["src/app.py"], 40)
            self.assertIn("This reverts commit", by_sha[shas["H3"]]["body"])

    def test_a_rename_is_recorded_under_the_name_it_has_now(self):
        self.assertEqual(kept.rename_target("old.py => new.py"), "new.py")
        self.assertEqual(kept.rename_target("src/{old => new}/a.py"), "src/new/a.py")
        self.assertEqual(kept.rename_target("plain.py"), "plain.py")

    def test_a_binary_file_has_no_lines_to_survive(self):
        commits = kept.parse_log("\x01" + "c" * 40 + "\x1f1756719000\x1fAda\x1fada@example.com"
                                 "\x1fbin\x1f\x1e-\t-\timage.png\n")
        self.assertEqual(commits[0]["files"][0]["added"], 0)


if __name__ == "__main__":
    unittest.main()
