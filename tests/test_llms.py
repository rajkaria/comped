"""The agent briefing at /llms.txt is instructions a machine will follow without a human reading them.

Every command in it is checked against the parser that will receive it, every Play parameter against
the Play's own parameter list, and every path against the repo. A briefing that has drifted from the
code is worse than none: the agent does not know to doubt it.
"""
import json
import pathlib
import re
import shlex
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from comped_core.cli import build_parser                # noqa: E402

LLMS = (ROOT / "site" / "llms.txt").read_text(encoding="utf-8")
PASTE = "Fetch https://gotcomped.com/llms.txt and do what it says."
PLAY = "https://play.modiqo.ai/rajkaria/comped"


def commands(prefix):
    return [line.strip() for line in LLMS.splitlines() if line.strip().startswith(prefix)]


class AgentBriefing(unittest.TestCase):
    def test_every_core_command_it_gives_is_one_the_cli_accepts(self):
        found = 0
        for cmd in commands("python3"):
            argv = shlex.split(cmd)
            if "cli.py" not in argv[1]:
                continue
            found += 1
            try:
                build_parser().parse_args(argv[2:])
            except SystemExit:
                self.fail("llms.txt tells an agent to run a command the CLI rejects: {0}".format(cmd))
        self.assertGreaterEqual(found, 2, "the briefing should show the run command and the follow-ups")

    def test_the_one_command_path_is_the_one_it_leads_with(self):
        # If `run` ever stops being a single command, this file is telling agents to do four things
        # in an order it no longer explains.
        self.assertIn("cli.py run --out-dir ~/comped", LLMS)
        self.assertIn("run", build_parser().parse_args(["run", "--out-dir", "x"]).cmd)

    def test_every_leaderboard_flag_it_names_exists_in_the_poster(self):
        poster = (ROOT / "leaderboard" / "post_score.py").read_text(encoding="utf-8")
        posts = [c for c in commands("python3") if "post_score.py" in c]
        self.assertEqual(len(posts), 1, "exactly one command in the briefing may send anything")
        for flag in [a for a in shlex.split(posts[0]) if a.startswith("--")]:
            self.assertIn('"{0}"'.format(flag), poster, "post_score.py has no {0}".format(flag))

    def test_every_play_parameter_it_names_is_a_real_parameter(self):
        names = {p["name"] for p in json.loads((ROOT / "docs" / "plays" / "comped" / "PARAMETERS.json").read_text(encoding="utf-8"))}
        # A query string is not a parameter list: play= in the installer URL is not the Play's.
        used = {n for n, _v in re.findall(r"(?<![?&/\w])([a-z_]+)=([A-Za-z0-9_.-]+)", LLMS)}
        self.assertTrue(used, "the briefing shows no Play parameters")
        for name in used:
            self.assertIn(name, names, "llms.txt passes {0}= to the Play, which has no such parameter".format(name))

    def test_it_runs_the_published_play_and_the_published_installer(self):
        self.assertIn(PLAY + " --yes handle=", LLMS)
        self.assertIn("https://gotcomped.com/run.sh", LLMS)
        self.assertIn("https://github.com/rajkaria/comped", LLMS)
        self.assertIn("https://play.modiqo.ai/install?play=rajkaria/comped", LLMS)

    def test_it_points_only_at_hosts_this_project_controls(self):
        for url in re.findall(r"https?://[^\s`)]+", LLMS):
            self.assertTrue(re.match(r"https://(gotcomped\.com|github\.com/rajkaria/comped|play\.modiqo\.ai)", url),
                            "llms.txt sends an agent to {0}".format(url))

    def test_the_demo_paths_it_offers_exist(self):
        for path in re.findall(r"/tmp/comped-src/(\S+)", LLMS):
            path = path.rstrip(".,`")
            if path.startswith("resources/fixtures"):
                self.assertTrue((ROOT / path).is_dir(), path)
            else:
                self.assertTrue((ROOT / path).is_file(), path)

    def test_consent_before_anything_is_sent(self):
        # The briefing is the only thing standing between an agent and a public post under someone's
        # name. These are the sentences that do it; losing them silently is the failure to catch.
        for claim in ("Ask before", "only if they said yes", "Do not run post_score.py",
                      "comped-rank.json", "leaderboard=false"):
            self.assertIn(claim, LLMS, claim)

    def test_it_repeats_the_promises_the_site_makes(self):
        for claim in ("Never reads", "credential", "no network calls", "~/comped"):
            self.assertIn(claim, LLMS, claim)
        for stale in ("nothing leaves your machine", "Nothing leaves your computer"):
            self.assertNotIn(stale, LLMS, stale)

    def test_the_site_hands_agents_the_same_line_the_file_expects(self):
        for page in ("index.html", "docs.html", "developers.html"):
            text = (ROOT / "site" / page).read_text(encoding="utf-8")
            self.assertIn("llms.txt", text, "{0} does not mention the agent briefing".format(page))
        self.assertIn(PASTE, (ROOT / "site" / "index.html").read_text(encoding="utf-8"))
        self.assertIn(PASTE.rstrip("."), (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_it_is_written_in_the_house_style(self):
        self.assertNotIn("—", LLMS, "llms.txt has an em dash")
        for n, line in enumerate(LLMS.splitlines(), 1):
            self.assertLessEqual(len(line), 100, "llms.txt:{0} is {1} columns".format(n, len(line)))


if __name__ == "__main__":
    unittest.main()
