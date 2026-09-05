"""The no-account path: one archive, one entry point, one shell script.

comped has two front doors. The rote Play is the inspectable one, with a consent screen and a
public archive. This is the other one, for a person who will not make an account to find out what
their subscription is worth. They must agree about everything that matters: the same core, the
same parameters, the same card. These tests are what stops them drifting apart.
"""
import hashlib
import http.server
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "standalone"))

import comped  # noqa: E402  the standalone entry point
from tools import build_dist  # noqa: E402

ARCHIVE = ROOT / "site" / "comped.tar.gz"
SCRIPT = ROOT / "site" / "comped.sh"
FIXTURES = ROOT / "resources" / "fixtures"


def setUpModule():
    build_dist.main()


class Parameters(unittest.TestCase):
    def test_both_ways_to_run_take_exactly_the_same_parameters(self):
        # A line someone copies from the docs has to work whichever door they came in through.
        declared = json.loads((ROOT / "docs" / "plays" / "comped" / "PARAMETERS.json").read_text(encoding="utf-8"))
        params = declared["parameters"] if isinstance(declared, dict) else declared
        play = {p["name"]: str(p.get("default", "")) for p in params}
        self.assertEqual(set(play), set(comped.PARAMS), "the Play and the standalone entry disagree on parameter names")
        for name, default in play.items():
            self.assertEqual(default, comped.PARAMS[name], "default for {0} differs".format(name))

    def test_every_parameter_maps_to_a_flag_the_core_accepts(self):
        from comped_core.cli import build_parser
        a = build_parser().parse_args(comped.core_argv(dict(comped.PARAMS)))
        self.assertEqual(a.cmd, "run")
        self.assertEqual(a.plan, "auto")
        self.assertEqual(a.days_back, 30)

    def test_a_mistyped_parameter_is_named_and_the_valid_ones_listed(self):
        with self.assertRaises(ValueError) as e:
            comped.parse_args(["plna=claude-pro-20"])
        self.assertIn("plna", str(e.exception))
        self.assertIn("plan", str(e.exception))
        with self.assertRaises(ValueError) as e:
            comped.parse_args(["--plan"])
        self.assertIn("key=value", str(e.exception))

    def test_an_empty_rates_path_is_left_out_rather_than_passed_as_empty(self):
        self.assertNotIn("--rates-path", comped.core_argv(dict(comped.PARAMS)))
        self.assertIn("--rates-path", comped.core_argv(dict(comped.PARAMS, rates_path="/tmp/r.json")))


class Archive(unittest.TestCase):
    def test_two_builds_of_one_commit_produce_one_checksum(self):
        # The script prints a sha256 and refuses a download that does not match it. That is only
        # worth doing if the number is stable.
        first = build_dist.build()
        second = build_dist.build()
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

    def test_the_published_checksum_matches_the_published_archive(self):
        stated = (ROOT / "site" / "comped.tar.gz.sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(stated, hashlib.sha256(ARCHIVE.read_bytes()).hexdigest())

    def test_the_archive_carries_the_same_core_as_the_repo_byte_for_byte(self):
        with tarfile.open(ARCHIVE) as tar:
            packed = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
        for p in sorted((ROOT / "comped_core").rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            name = "comped/" + str(p.relative_to(ROOT))
            self.assertIn(name, packed, "{0} is missing from the archive".format(name))
            self.assertEqual(p.read_bytes(), packed[name], "{0} drifted from the repo".format(name))
        self.assertEqual((ROOT / "leaderboard" / "post_score.py").read_bytes(), packed["comped/post_score.py"])
        self.assertEqual((ROOT / "standalone" / "comped.py").read_bytes(), packed["comped/comped.py"])

    def test_the_archive_carries_what_it_needs_and_no_logs_of_anyones(self):
        with tarfile.open(ARCHIVE) as tar:
            names = tar.getnames()
        for needed in ("comped/comped.py", "comped/post_score.py", "comped/LICENSE", "comped/VERSION",
                       "comped/resources/prices.json", "comped/resources/plans.json",
                       "comped/comped_core/cli.py", "comped/comped_core/adapters/claude_code.py"):
            self.assertIn(needed, names)
        # The sample logs ride along so the demo line works without an account.
        self.assertTrue(any(n.startswith("comped/resources/fixtures/claude/") for n in names))
        for name in names:
            self.assertNotIn(".env", name)
            self.assertNotIn("/.git", name)


class FakeBoard(http.server.BaseHTTPRequestHandler):
    """Stands in for gotcomped.com/api/score so a successful post can be tested off the real board."""
    reply = {"ok": True, "rank": 4, "of": 11, "percentile": 36,
             "url": "https://gotcomped.com/leaderboard.html#tester",
             "board": "https://gotcomped.com/leaderboard.html"}

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(self.reply).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class EndToEnd(unittest.TestCase):
    """Unpack the real archive and run it, the way the one-liner does."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        with tarfile.open(ARCHIVE) as tar:
            tar.extractall(cls.dir.name)
        cls.entry = pathlib.Path(cls.dir.name) / "comped" / "comped.py"

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def run_it(self, out, *args, **env):
        import os
        e = dict(os.environ, **env)
        return subprocess.run([sys.executable, str(self.entry),
                               "claude_dir={0}".format(FIXTURES / "claude"),
                               "codex_dir={0}".format(FIXTURES / "codex"),
                               "pi_dir={0}".format(FIXTURES / "pi"),
                               "opencode_dir={0}".format(FIXTURES / "opencode"),
                               "out_dir={0}".format(out)] + list(args),
                              capture_output=True, text=True, env=e, timeout=180)

    def test_it_prints_a_card_and_writes_the_files_with_no_runner_and_no_account(self):
        with tempfile.TemporaryDirectory() as out:
            r = self.run_it(out, "leaderboard=false")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("COMPED", r.stdout)
            self.assertIn("comped", r.stdout)
            self.assertIn("IF YOU'RE ON", r.stdout)
            for name in ("comped-card.svg", "comped-report.md", "comped-share.txt", "ledger.jsonl"):
                self.assertTrue((pathlib.Path(out) / name).is_file(), name)
            self.assertIn("nothing was sent anywhere", r.stdout)

    def test_the_card_is_the_output_and_no_json_is_spilled_under_it(self):
        # Every Play step ends in a JSON line for rote to read. A person at a terminal gets none of it.
        with tempfile.TemporaryDirectory() as out:
            r = self.run_it(out, "leaderboard=false")
            for line in r.stdout.splitlines():
                self.assertFalse(line.startswith('{"'), "raw step JSON reached the terminal: {0}".format(line[:60]))

    def test_a_successful_post_is_reported_in_words_with_the_rank(self):
        server = http.server.HTTPServer(("127.0.0.1", 0), FakeBoard)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:{0}/api/score".format(server.server_address[1])
        try:
            with tempfile.TemporaryDirectory() as out:
                r = self.run_it(out, "handle=tester", COMPED_LEADERBOARD_URL=url)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("posted as tester", r.stdout)
                self.assertIn("#4 of 11", r.stdout)
                self.assertNotIn("anonymously", r.stdout)
                sent = json.loads((pathlib.Path(out) / "comped-rank.json").read_text(encoding="utf-8"))
                self.assertEqual(sent["sent"]["handle"], "tester")
                self.assertEqual(sent["reply"]["rank"], 4)
        finally:
            server.shutdown()
            server.server_close()

    def test_without_a_handle_it_says_how_to_claim_a_name(self):
        server = http.server.HTTPServer(("127.0.0.1", 0), FakeBoard)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:{0}/api/score".format(server.server_address[1])
        try:
            with tempfile.TemporaryDirectory() as out:
                r = self.run_it(out, COMPED_LEADERBOARD_URL=url)
                self.assertIn("anonymously", r.stdout)
                self.assertIn("handle=yourname", r.stdout)
        finally:
            server.shutdown()
            server.server_close()

    def test_the_documented_demo_line_works_through_this_door_too(self):
        # rote runs a Play from the package root, so the docs say claude_dir=resources/fixtures/...
        # The same line has to work here, where the person is standing somewhere else entirely.
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run([sys.executable, str(self.entry),
                                "claude_dir=resources/fixtures/claude",
                                "codex_dir=resources/fixtures/codex",
                                "out_dir={0}".format(out), "leaderboard=false"],
                               capture_output=True, text=True, cwd=out, timeout=180)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("COMPED", r.stdout)
            self.assertNotIn("nothing to price", r.stdout)

    def test_an_unreachable_board_is_a_warning_not_a_failure(self):
        with tempfile.TemporaryDirectory() as out:
            r = self.run_it(out, COMPED_LEADERBOARD_URL="http://127.0.0.1:9/api/score")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Your card is unaffected", r.stdout)
            self.assertNotIn("Traceback", r.stderr)

    def test_reading_nothing_names_the_directories_and_posts_nothing(self):
        # Pointed at the wrong place, over an out_dir that already holds yesterday's card, it must
        # not send yesterday's score as if it were today's.
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_it(out, "leaderboard=false").returncode, 0)
            before = (pathlib.Path(out) / ".priced.json").read_text(encoding="utf-8")
            r = subprocess.run([sys.executable, str(self.entry), "claude_dir=/nonexistent",
                                "codex_dir=/nonexistent", "pi_dir=/nonexistent",
                                "opencode_dir=/nonexistent", "out_dir={0}".format(out)],
                               capture_output=True, text=True, timeout=120)
            # ok:false in the core means a non-zero exit, so a script wrapping this can tell.
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("nothing to price", r.stdout)
            self.assertIn("/nonexistent", r.stdout)
            self.assertNotIn("LEADERBOARD", r.stdout)
            self.assertFalse((pathlib.Path(out) / "comped-rank.json").exists())
            self.assertEqual(before, (pathlib.Path(out) / ".priced.json").read_text(encoding="utf-8"))


class Script(unittest.TestCase):
    def setUp(self):
        self.sh = SCRIPT.read_text(encoding="utf-8")

    def test_it_is_valid_posix_shell(self):
        self.assertEqual(0, subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True).returncode)

    def test_it_does_nothing_clever_with_your_machine(self):
        # Judge the code, not the comments: the header quotes the very one-liner people paste,
        # and the python3 advice names apt and dnf. Neither is something this script runs.
        code = "\n".join(l for l in self.sh.splitlines() if not l.lstrip().startswith("#"))
        for bad in ("rm -rf /", "eval", "base64", "chmod 777", "| sh", "| bash", "> /dev/null 2>&1 &"):
            self.assertNotIn(bad, code, bad)
        for n, line in enumerate(self.sh.splitlines(), 1):
            self.assertFalse(line.lstrip().startswith("sudo"), "line {0} runs sudo".format(n))
        # It downloads exactly two things, both from the one origin, and pipes neither anywhere.
        self.assertEqual(code.count("curl"), 4,
                         "probe for curl, the message when it is missing, the archive, the checksum")
        # Every fetch is from the one origin. A second host in here would be a second thing to trust.
        fetches = [l for l in code.splitlines() if "curl -fsSL" in l]
        self.assertEqual(len(fetches), 2, fetches)
        for line in fetches:
            self.assertIn('"$BASE/', line, line)

    def test_it_pins_https_for_the_published_origin(self):
        self.assertIn("https://gotcomped.com", self.sh)
        self.assertIn("--proto =https", self.sh)

    def test_it_checks_the_download_against_the_published_checksum(self):
        self.assertIn("comped.tar.gz.sha256", self.sh)
        self.assertIn("did not match its published checksum", self.sh)

    def test_it_leaves_nothing_behind(self):
        self.assertIn("trap 'rm -rf \"$TMP\"' EXIT INT TERM", self.sh)
        # exec would replace this shell and the trap would never run.
        self.assertNotIn("exec \"$PY\"", self.sh)

    def test_it_passes_the_parameters_straight_through(self):
        self.assertIn('"$@"', self.sh)
        self.assertIn("leaderboard=false", self.sh)

    def test_it_points_at_the_rote_play_for_people_who_want_the_consent_screen(self):
        self.assertIn("run.sh", self.sh)
        self.assertIn("rote", self.sh)

    def test_it_needs_no_account_anywhere_in_it(self):
        for word in ("login", "sign in", "token", "api key", "whoami"):
            self.assertNotIn(word, self.sh.lower().replace("needs a free account", ""))


if __name__ == "__main__":
    unittest.main()
