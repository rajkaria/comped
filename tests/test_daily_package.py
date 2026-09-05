"""The six published packages: frontmatter, parameter parity, and that the argv actually runs.

A Play is a contract between a YAML block and a command line. The failure that matters is the one
where the two drift apart, because it only shows up on a stranger's machine, so the argv in every
step is parsed here by the real parser with the real defaults.
"""
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SLUGS = ["tab-debt", "birthday-radar", "app-graveyard", "vault-pulse", "desktop-clutter", "receipt-ledger"]


def setUpModule():
    """Sync the core into every package first, the way CI and a release do.

    The copies under `plays/*/resources/` are generated and deliberately untracked, so a fresh
    checkout has none of them. Running the sync here is what makes these tests mean the same
    thing on a clean clone as they do on a working tree that has already built.
    """
    proc = subprocess.run([sys.executable, "tools/sync_plays.py"], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise RuntimeError("sync_plays.py failed: {0}".format(proc.stdout.decode()))


def frontmatter(slug: str) -> str:
    text = (ROOT / "plays" / slug / "main.ts").read_text(encoding="utf-8")
    block = text.split(" * ---\n", 2)[1]
    return "\n".join(line[3:] if line.startswith(" * ") else line[2:].lstrip()
                     for line in block.splitlines())


def steps_of(slug: str) -> dict:
    """Parse the steps block without a YAML library: name, depends_on and argv are all it holds."""
    out, current, in_argv = {}, None, False
    for line in frontmatter(slug).splitlines():
        if re.match(r"^steps:$", line):
            current, in_argv = "", False
            continue
        if current is None:
            continue
        m = re.match(r"^  ([a-z_]+):$", line)
        if m:
            current = m.group(1)
            out[current] = {"argv": [], "depends_on": [], "timeout_ms": 0}
            in_argv = False
            continue
        if not current:
            continue
        if line.strip() == "argv:":
            in_argv = True
            continue
        if line.strip() == "depends_on:":
            in_argv = False
            continue
        m = re.match(r"^    timeout_ms: (\d+)$", line)
        if m:
            out[current]["timeout_ms"] = int(m.group(1))
            continue
        m = re.match(r"^    - '(.*)'$", line)
        if m:
            out[current]["argv"].append(m.group(1).replace("''", "'"))
            continue
        m = re.match(r"^    - ([a-z_]+)$", line)
        if m and not in_argv:
            out[current]["depends_on"].append(m.group(1))
    return out


def params_of(slug: str) -> list:
    return json.loads((ROOT / "docs" / "plays" / slug / "PARAMETERS.json").read_text(encoding="utf-8"))


class TestPackage(unittest.TestCase):
    def test_each_play_has_its_files(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                d = ROOT / "plays" / slug
                self.assertTrue((d / "main.ts").is_file())
                self.assertTrue((d / "deps.toml").is_file())
                self.assertTrue((d / "resources" / "daily_core" / "cli.py").is_file())
                self.assertTrue((d / "resources" / "daily_core" / "fixtures").is_dir())

    def test_the_core_in_every_package_is_the_repository_core(self):
        """After the sync in setUpModule, every package must hold the repository core byte for byte."""
        proc = subprocess.run([sys.executable, "tools/sync_plays.py", "--check"], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode())
        self.assertNotIn("DRIFT", proc.stdout.decode())

    def test_the_tags_appear_in_all_three_places_the_rubric_reads(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                fm = frontmatter(slug)
                self.assertEqual(fm.count("effect-read-only"), 3, "tags go under metadata, top level and discoverability")
                self.assertIn("license: MIT", fm)
                self.assertIn("execution_model: steps_with_presentation", fm)
                self.assertIn("requires_sessions: false", fm)

    def test_deps_declares_python_and_nothing_else(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                deps = (ROOT / "plays" / slug / "deps.toml").read_text(encoding="utf-8")
                self.assertEqual(deps.count("[[tools]]"), 1)
                self.assertIn('command = "python3"', deps)
                for banned in ("node", "deno", "curl", "pip"):
                    self.assertNotIn('command = "{0}"'.format(banned), deps)


class TestParameterParity(unittest.TestCase):
    def test_the_frontmatter_declares_exactly_the_documented_parameters(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                declared = re.findall(r"^- name: (\w+)$", frontmatter(slug), re.M)
                self.assertEqual(declared, [p["name"] for p in params_of(slug)])

    def test_every_parameter_carries_a_default_and_a_description(self):
        for slug in SLUGS:
            fm = frontmatter(slug)
            for p in params_of(slug):
                with self.subTest(play=slug, param=p["name"]):
                    self.assertIn("- name: {0}".format(p["name"]), fm)
                    self.assertTrue(p["description"].strip())
                    self.assertTrue(p["label"].strip())
            self.assertEqual(fm.count("required: false"), len(params_of(slug)))

    def test_every_parameter_referenced_by_a_step_is_declared(self):
        for slug in SLUGS:
            names = {p["name"] for p in params_of(slug)}
            for step, spec in steps_of(slug).items():
                for token in spec["argv"]:
                    if token.startswith("$"):
                        with self.subTest(play=slug, step=step, token=token):
                            self.assertIn(token[1:], names)

    def test_every_play_offers_out_dir_and_demo(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                names = {p["name"] for p in params_of(slug)}
                self.assertIn("out_dir", names)
                self.assertIn("demo", names)


class TestArgvActuallyRuns(unittest.TestCase):
    """Substitute the declared defaults into each step's argv and hand it to the real parser."""

    def test_every_step_argv_parses(self):
        from daily_core.cli import build_parser
        parser = build_parser()
        for slug in SLUGS:
            defaults = {p["name"]: str(p["default"]) for p in params_of(slug)}
            for step, spec in steps_of(slug).items():
                with self.subTest(play=slug, step=step):
                    argv = spec["argv"]
                    self.assertEqual(argv[0], "python3")
                    self.assertEqual(argv[1], "@resource{daily_core/cli.py}")
                    resolved = [defaults.get(a[1:], "") if a.startswith("$") else a for a in argv[2:]]
                    args = parser.parse_args(resolved)
                    self.assertTrue(callable(args.fn))

    def test_the_report_step_depends_on_every_read_step(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                steps = steps_of(slug)
                reads = [n for n, s in steps.items() if not s["depends_on"]]
                self.assertTrue(reads)
                self.assertEqual(sorted(steps["report"]["depends_on"]), sorted(reads))

    def test_every_step_declares_a_timeout(self):
        for slug in SLUGS:
            for step, spec in steps_of(slug).items():
                with self.subTest(play=slug, step=step):
                    self.assertGreaterEqual(spec["timeout_ms"], 30000)


class TestFixtures(unittest.TestCase):
    def test_every_step_has_a_declared_presentation_fixture_that_exists(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                declared = json.loads(
                    (ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json").read_text(encoding="utf-8"))
                self.assertEqual(sorted(declared), sorted(steps_of(slug)))
                for step, rel in declared.items():
                    path = ROOT / "plays" / slug / rel
                    self.assertTrue(path.is_file(), path)
                    self.assertIn("kind: process.exec", path.read_text(encoding="utf-8"))
                    stdout = path.parent / "stdout.txt"
                    self.assertTrue(stdout.is_file())
                    last = [l for l in stdout.read_text(encoding="utf-8").splitlines() if l.strip()][-1]
                    json.loads(last)

    def test_the_lint_sidecar_records_a_pass(self):
        """When a sidecar is present it must record a pass; it is written by lint and not committed."""
        for slug in SLUGS:
            with self.subTest(play=slug):
                sidecar = ROOT / "plays" / slug / ".rote-flow-lint.json"
                if not sidecar.is_file():
                    self.skipTest("no lint sidecar here; rote play lint has not run in this checkout")
                doc = json.loads(sidecar.read_text(encoding="utf-8"))
                self.assertTrue(doc["static_checks_passed"], doc.get("violations"))
                self.assertTrue(doc["runtime_checks_passed"], doc.get("violations"))


class TestDocs(unittest.TestCase):
    def test_the_description_makes_the_promises_the_tests_enforce(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                text = (ROOT / "docs" / "plays" / slug / "DESCRIPTION.md").read_text(encoding="utf-8")
                self.assertGreater(len(text), 900, "the registry copy is the whole shop window")
                for promise in ("demo=true", "Never sends", "Never reads", "Writes: only inside `out_dir`",
                                "python3 3.9"):
                    self.assertIn(promise, text)

    def test_steps_md_lists_every_step(self):
        for slug in SLUGS:
            with self.subTest(play=slug):
                text = (ROOT / "docs" / "plays" / slug / "STEPS.md").read_text(encoding="utf-8")
                for step in steps_of(slug):
                    self.assertIn("`{0}`".format(step), text)


if __name__ == "__main__":
    unittest.main()
