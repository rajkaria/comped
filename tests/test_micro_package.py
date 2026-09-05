"""The twelve micro packages: frontmatter, parameter parity, and that the argv actually runs.

A Play is a contract between a YAML block and a command line. The failure that matters is the one
where the two drift apart, because it only shows up on a stranger's machine — so every step's argv
is parsed here by the real dispatch with the real defaults.
"""
import io
import json
import pathlib
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from micro_core import cli                                    # noqa: E402

SPEC = json.loads((ROOT / "docs" / "plays" / "_micro-spec.json").read_text(encoding="utf-8"))
SLUGS = list(SPEC)
WRITERS = {"punch", "spent", "jot", "streak", "since-last"}
LOG_WRITERS = {"punch", "spent", "jot", "streak"}   # since-last owns a snapshot, not a log
PRICED = {"fits", "last-turn", "budget-left"}


def setUpModule():
    """Generate and sync first, the way CI and a release do: the packages are build output."""
    for tool in ("tools/build_micro_plays.py", "tools/sync_plays.py"):
        proc = subprocess.run([sys.executable, tool], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            raise RuntimeError("{0} failed: {1}".format(tool, proc.stdout.decode()))


def frontmatter(slug):
    text = (ROOT / "plays" / slug / "main.ts").read_text(encoding="utf-8")
    block = text.split(" * ---\n", 2)[1]
    return "\n".join(line[3:] if line.startswith(" * ") else line[2:].lstrip()
                     for line in block.splitlines())


def steps_of(slug):
    out, current, in_argv = {}, None, False
    for line in frontmatter(slug).splitlines():
        if line == "steps:":
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


def params_of(slug):
    return json.loads((ROOT / "docs" / "plays" / slug / "PARAMETERS.json").read_text(encoding="utf-8"))


def run_demo(slug, step="report"):
    """Run one step the way the package declares it, with the demo switch on."""
    argv, i = [], 0
    declared = steps_of(slug)[step]["argv"][2:]
    while i < len(declared):
        if declared[i].startswith("--") and i + 1 < len(declared) and declared[i + 1].startswith("$"):
            i += 2
            continue
        argv.append(declared[i])
        i += 1
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(argv + ["--demo", "true", "--now", "2026-09-05T12:00:00Z"])
    return rc, json.loads(buf.getvalue().rstrip("\n").split("\n")[-1])


class TestPackage(unittest.TestCase):
    def test_each_play_has_its_files(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                d = ROOT / "plays" / slug
                self.assertTrue((d / "main.ts").is_file())
                self.assertTrue((d / "deps.toml").is_file())
                self.assertTrue((d / "resources" / "micro_core" / "cli.py").is_file())
                self.assertTrue((d / "resources" / "micro_core" / "fixtures").is_dir())

    def test_only_the_three_priced_plays_carry_a_second_core(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                has = (ROOT / "plays" / slug / "resources" / "comped_core").is_dir()
                self.assertEqual(has, slug in PRICED)
                self.assertEqual((ROOT / "plays" / slug / "resources" / "prices.json").is_file(),
                                 slug in PRICED)

    def test_the_core_in_every_package_is_the_repository_core(self):
        proc = subprocess.run([sys.executable, "tools/sync_plays.py", "--check"], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode())
        self.assertNotIn("DRIFT", proc.stdout.decode())

    def test_deps_declares_python_and_nothing_else(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                deps = (ROOT / "plays" / slug / "deps.toml").read_text(encoding="utf-8")
                self.assertEqual(deps.count("[[tools]]"), 1)
                self.assertIn('command = "python3"', deps)
                for banned in ("node", "npm", "git", "curl", "jq"):
                    self.assertNotIn('command = "{0}"'.format(banned), deps)


class TestFrontmatter(unittest.TestCase):
    def test_the_tags_appear_in_all_three_places_the_rubric_reads(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                fm = frontmatter(slug)
                effect = "effect-local-write" if slug in WRITERS else "effect-read-only"
                self.assertEqual(fm.count(effect), 3, "tags go under metadata, top level and discoverability")
                self.assertIn("license: MIT", fm)
                self.assertIn("execution_model: steps_with_presentation", fm)
                self.assertIn("requires_sessions: false", fm)

    def test_a_writer_is_never_tagged_read_only(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                tags = SPEC[slug]["tags"]
                if slug in WRITERS:
                    self.assertIn("effect-local-write", tags)
                    self.assertNotIn("effect-read-only", tags)
                else:
                    self.assertIn("effect-read-only", tags)
                    self.assertNotIn("effect-local-write", tags)

    def test_the_frontmatter_declares_exactly_the_documented_parameters(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                declared = re.findall(r"^- name: (\w+)$", frontmatter(slug), re.M)
                self.assertEqual(declared, [p["name"] for p in params_of(slug)])

    def test_every_parameter_carries_a_default_a_label_and_a_description(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                fm = frontmatter(slug)
                for p in params_of(slug):
                    self.assertIn("- name: {0}".format(p["name"]), fm)
                    self.assertTrue(p["description"].strip())
                    self.assertTrue(p["label"].strip())
                self.assertEqual(fm.count("required: false"), len(params_of(slug)))

    def test_every_play_offers_now_and_demo_and_no_out_dir(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                names = [p["name"] for p in params_of(slug)]
                self.assertIn("demo", names)
                self.assertIn("now", names)
                self.assertNotIn("out_dir", names, "a micro Play prints; it does not write a report")

    def test_every_writer_declares_where_it_writes(self):
        for slug in WRITERS:
            with self.subTest(slug=slug):
                names = [p["name"] for p in params_of(slug)]
                self.assertIn("state_dir", names)


class TestSteps(unittest.TestCase):
    def test_every_parameter_referenced_by_a_step_is_declared(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                names = {p["name"] for p in params_of(slug)}
                for step in steps_of(slug).values():
                    for token in step["argv"]:
                        if token.startswith("$"):
                            self.assertIn(token[1:], names)

    def test_every_step_argv_addresses_the_bundled_core(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                for name, step in steps_of(slug).items():
                    self.assertEqual(step["argv"][0], "python3")
                    self.assertEqual(step["argv"][1], "@resource{micro_core/cli.py}")
                    self.assertIn((step["argv"][2], step["argv"][3]), cli._DISPATCH)

    def test_a_two_step_play_reports_after_it_records(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                steps = steps_of(slug)
                self.assertIn("report", steps)
                if len(steps) == 2:
                    self.assertIn("record", steps)
                    self.assertEqual(steps["report"]["depends_on"], ["record"])
                else:
                    self.assertEqual(steps["report"]["depends_on"], [])

    def test_every_step_declares_a_timeout(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                for step in steps_of(slug).values():
                    self.assertGreaterEqual(step["timeout_ms"], 30000)

    def test_every_step_has_a_presentation_fixture_that_exists(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                declared = json.loads(
                    (ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json").read_text())
                self.assertEqual(sorted(declared), sorted(steps_of(slug)))
                for rel in declared.values():
                    self.assertTrue((ROOT / "plays" / slug / rel).is_file(), rel)


class TestOutputSchema(unittest.TestCase):
    def test_the_declared_output_keys_are_the_keys_the_step_prints(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                rc, doc = run_demo(slug)
                self.assertEqual(rc, 0)
                for key in SPEC[slug]["outputs"]:
                    self.assertIn(key, doc)

    def test_the_summary_reads_a_key_the_output_declares(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                used = set(re.findall(r"j\.(\w+)", SPEC[slug]["summary"]))
                declared = set(SPEC[slug]["outputs"]) | {"error"}
                self.assertTrue(used <= declared, "{0}: {1}".format(slug, used - declared))


class TestDocs(unittest.TestCase):
    def test_every_play_has_its_three_documents(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                for name in ("DESCRIPTION.md", "PARAMETERS.json", "STEPS.md"):
                    self.assertTrue((ROOT / "docs" / "plays" / slug / name).is_file(), name)

    def test_every_description_states_its_write_behaviour(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                text = (ROOT / "docs" / "plays" / slug / "DESCRIPTION.md").read_text(encoding="utf-8")
                if slug in LOG_WRITERS:
                    self.assertIn("append", text.lower())
                if slug in WRITERS:
                    self.assertIn("- Writes:", text)
                    self.assertTrue("~/.rote-micro" in text or "state_dir" in text)
                else:
                    self.assertIn("Writes nothing", text)

    def test_every_description_makes_the_offline_claim_checkable(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                text = (ROOT / "docs" / "plays" / slug / "DESCRIPTION.md").read_text(encoding="utf-8")
                self.assertIn("imports no `urllib`, `http`, `socket` or `subprocess`", text)
                self.assertIn("Never reads:", text)

    def test_the_description_in_the_package_is_the_description_in_docs(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                doc = (ROOT / "docs" / "plays" / slug / "DESCRIPTION.md").read_text(encoding="utf-8")
                first = doc.strip().splitlines()[0][:60].replace("'", "''")
                self.assertIn(first, frontmatter(slug))
