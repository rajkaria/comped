"""The npm package: a launcher, a payload, and no dependency tree to trust.

`npx comped` is the third door. It must carry the same core as the other two, add nothing of its
own, and refuse to grow a dependency: a tool that reads somebody's session logs has no business
pulling in a transitive graph nobody reads.
"""
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import build_npm, build_dist  # noqa: E402

PKG = ROOT / "npm"


def setUpModule():
    build_npm.main()


class Package(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PKG / "package.json").read_text(encoding="utf-8"))

    def test_it_has_no_dependencies_and_no_install_script(self):
        self.assertEqual({}, self.manifest.get("dependencies"))
        self.assertEqual({}, self.manifest.get("devDependencies", {}))
        for hook in ("scripts", "gypfile", "binary"):
            self.assertNotIn(hook, self.manifest, "npm package declares {0}".format(hook))

    def test_its_version_is_the_repo_version(self):
        self.assertEqual(build_dist.version(), self.manifest["version"])
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('version = "{0}"'.format(self.manifest["version"]), pyproject)

    def test_the_launcher_is_the_only_javascript_and_it_only_launches(self):
        js = sorted(p for p in PKG.rglob("*.js") if "node_modules" not in p.parts)
        self.assertEqual([PKG / "bin" / "comped.js"], js)
        src = js[0].read_text(encoding="utf-8")
        # It requires exactly two built-ins and nothing else. A URL inside a help string is text,
        # not a network call, so match what the code loads rather than what it says.
        required = sorted(set(re.findall(r'require\(["\']([^"\']+)["\']\)', src)))
        self.assertEqual(["child_process", "path"], required)
        self.assertNotIn("eval(", src)
        self.assertNotIn("Function(", src)

    def test_the_launcher_tries_the_windows_python_names(self):
        src = (PKG / "bin" / "comped.js").read_text(encoding="utf-8")
        for name in ("python3", "python", "py"):
            self.assertIn('"{0}"'.format(name), src)
        # A Windows console's code page would kill the card on its first box character.
        self.assertIn("PYTHONIOENCODING", src)

    def test_the_payload_is_the_same_core_the_other_doors_carry(self):
        for name, data in build_dist.members():
            if name in ("LICENSE", "VERSION"):
                continue
            packed = PKG / "payload" / name
            self.assertTrue(packed.is_file(), "{0} missing from the npm payload".format(name))
            self.assertEqual(data, packed.read_bytes(), "{0} drifted".format(name))

    def test_everything_shipped_is_declared(self):
        for entry in self.manifest["files"]:
            self.assertTrue((PKG / entry.rstrip("/")).exists(), entry)
        self.assertIn("bin/", self.manifest["files"])
        self.assertIn("payload/", self.manifest["files"])

    def test_the_readme_promises_only_what_the_tool_does(self):
        text = (PKG / "README.md").read_text(encoding="utf-8")
        self.assertIn("leaderboard=false", text)
        self.assertIn("Python 3.9", text)
        # The claim that was corrected everywhere else must not come back here.
        self.assertNotIn("nothing leaves your computer", text.lower())
        self.assertNotIn("0 bytes", text)


class Launcher(unittest.TestCase):
    """Run the payload the way the launcher does, without needing node in the test environment."""

    def test_the_payload_entry_point_runs_and_prints_a_card(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run(
                [sys.executable, str(PKG / "payload" / "comped.py"),
                 "claude_dir={0}".format(ROOT / "resources" / "fixtures" / "claude"),
                 "out_dir={0}".format(out), "leaderboard=false"],
                capture_output=True, text=True, timeout=180)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("COMPED", r.stdout)


class Version(unittest.TestCase):
    def test_every_stated_version_agrees(self):
        """Four files carry the version. A release where they disagree is a release that lies."""
        want = build_dist.version()
        checks = {
            "pyproject.toml": r'^version = "([^"]+)"',
            "tools/build_plays.py": r'^VERSION = "([^"]+)"',
            "leaderboard/post_score.py": r'^VERSION = "([^"]+)"',
        }
        for path, pattern in checks.items():
            m = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"), re.M)
            self.assertIsNotNone(m, path)
            self.assertEqual(want, m.group(1), "{0} says {1}, pyproject says {2}".format(path, m.group(1), want))
        for slug in ("comped", "session-ledger", "wrong-turns"):
            main_ts = (ROOT / "plays" / slug / "main.ts").read_text(encoding="utf-8")
            self.assertIn("version: '{0}'".format(want), main_ts, slug)


if __name__ == "__main__":
    unittest.main()
