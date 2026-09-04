import unittest, json, pathlib, re, shutil, subprocess

SLUGS = ("session-ledger", "comped", "wrong-turns")
# Only these may sit at a Play package root; rote refuses anything else as an unsupported package file.
ALLOWED_ROOT = {"main.ts", "deps.toml", "lib", "vendor", "resources"}


class PlayPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "tools/sync_plays.py"], check=True, capture_output=True)

    def test_generator_is_idempotent(self):
        before = {s: pathlib.Path("plays", s, "main.ts").read_text(encoding="utf-8") for s in SLUGS}
        subprocess.run(["python3", "tools/build_plays.py"], check=True, capture_output=True)
        for s in SLUGS:
            self.assertEqual(before[s], pathlib.Path("plays", s, "main.ts").read_text(encoding="utf-8"), s)

    def test_package_root_holds_only_supported_files(self):
        for s in SLUGS:
            for p in pathlib.Path("plays", s).iterdir():
                if p.name.startswith("."):
                    continue   # rote drops its own lint cache (.rote-flow-lint.json) here
                self.assertIn(p.name, ALLOWED_ROOT, "{0}/{1} would be refused by rote".format(s, p.name))

    def test_steps_address_the_core_through_a_resource_token(self):
        for s in SLUGS:
            text = pathlib.Path("plays", s, "main.ts").read_text(encoding="utf-8")
            self.assertIn("@resource{comped_core/cli.py}", text, s)
            # A host path in argv would break on anyone else's machine.
            self.assertNotIn("/Users/", text, s)

    def test_presentation_references_only_declared_steps(self):
        for s in SLUGS:
            text = pathlib.Path("plays", s, "main.ts").read_text(encoding="utf-8")
            declared = set(re.findall(r"^ \*   (\w+):$", text, re.M))
            for ref in set(re.findall(r'stepName\("(\w+)"\)', text)):
                self.assertIn(ref, declared, "{0}: presentation references undeclared step {1}".format(s, ref))

    def test_every_declared_fixture_exists(self):
        for s in SLUGS:
            text = pathlib.Path("plays", s, "main.ts").read_text(encoding="utf-8")
            block = re.search(r"^ \* presentation_fixtures:$(.*?)^ \* \w", text, re.M | re.S)
            self.assertIsNotNone(block, "{0} declares no presentation fixtures".format(s))
            paths = re.findall(r"(resources/presentation-fixtures/\S+)", block.group(1))
            self.assertTrue(paths, s)
            for rel in paths:
                self.assertTrue(pathlib.Path("plays", s, rel).is_file(), "{0}: missing {1}".format(s, rel))

    def test_rote_validates_lints_and_scores_each_play(self):
        if not shutil.which("rote"):
            self.skipTest("rote CLI not installed")
        for s in SLUGS:
            path = "plays/{0}/main.ts".format(s)
            v = subprocess.run(["rote", "play", "validate", path], capture_output=True, text=True)
            self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
            l = subprocess.run(["rote", "play", "lint", path], capture_output=True, text=True)
            self.assertEqual(l.returncode, 0, l.stdout + l.stderr)
            sc = subprocess.run(["rote", "play", "score", path, "--format", "json"], capture_output=True, text=True)
            self.assertEqual(sc.returncode, 0, sc.stdout + sc.stderr)
            self.assertEqual(json.loads(sc.stdout)["data"]["result"]["score"], 1.0, "{0} score".format(s))
