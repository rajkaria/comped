"""What the sixteen daily Plays promise about the machine they run on, asserted statically.

The claims in every DESCRIPTION.md are that nothing reaches the network, nothing runs but two
fixed read-only commands, no credential file is opened, and nothing is written outside out_dir.
Each of those is checkable without running anything, so each is checked here on every commit.
"""
import ast
import json
import pathlib
import re
import unittest

SRC = pathlib.Path("daily_core")
PY_FILES = sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
# Every Play built on this core, read from the spec so a new one cannot be added to the registry
# without also being held to the promises below. The three network-backed Plays ship one file
# each that opens a connection; it lives outside this package on purpose, and what it may and may
# not do is asserted separately, in tests/test_fetch_steps.py.
DAILY_PLAYS = tuple(json.loads(
    pathlib.Path("docs/plays/_daily-spec.json").read_text(encoding="utf-8")))


class TestOffline(unittest.TestCase):
    def test_nothing_imports_a_network_module(self):
        pattern = re.compile(
            r"^\s*(?:import|from)\s+(urllib|http|https|socket|ssl|requests|ftplib|smtplib|telnetlib|"
            r"xmlrpc|asyncio|selectors)\b", re.M)
        for path in PY_FILES:
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), path)

    def test_no_url_is_ever_opened(self):
        for path in PY_FILES:
            text = path.read_text(encoding="utf-8")
            for banned in ("urlopen", "urlretrieve", "socket.create_connection", "HTTPSConnection"):
                self.assertNotIn(banned, text, "{0} references {1}".format(path, banned))


class TestSubprocess(unittest.TestCase):
    """Two modules may start a process, each only the one binary it names, each read-only.

    The claim is deliberately an exact shape rather than a count: what protects a reader is not
    "few subprocess calls" but "no call whose program or subcommand a caller could influence".
    """

    PROCESS_MODULES = {"apps.py": "MDLS", "gitread.py": "git"}

    def test_no_other_module_imports_subprocess(self):
        for path in PY_FILES:
            if path.name in self.PROCESS_MODULES:
                continue
            self.assertNotIn("subprocess", path.read_text(encoding="utf-8"), path)

    def test_the_spotlight_call_is_one_fixed_argv_with_no_shell(self):
        text = (SRC / "scan" / "apps.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "run"]
        self.assertEqual(len(calls), 1, "exactly one subprocess.run is expected")
        call = calls[0]
        self.assertFalse([k for k in call.keywords if k.arg == "shell"], "shell= must never be set")
        argv = call.args[0]
        self.assertIsInstance(argv, ast.BinOp, "argv should be a literal list plus the paths")
        first = argv.left.elts[0]
        self.assertEqual(first.id if isinstance(first, ast.Name) else None, "MDLS")
        self.assertIn('MDLS = "/usr/bin/mdls"', text)

    def test_the_git_call_is_one_fixed_argv_with_no_shell(self):
        text = (SRC / "gitread.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
        self.assertEqual(len(calls), 1, "exactly one subprocess.run is expected")
        call = calls[0]
        self.assertFalse([k for k in call.keywords if k.arg == "shell"], "shell= must never be set")
        self.assertIsInstance(call.args[0], ast.Name, "argv must be a name bound to a built list")

    def test_every_git_binary_it_will_run_is_an_absolute_path_it_names_itself(self):
        from daily_core.gitread import GIT_CANDIDATES
        for candidate in GIT_CANDIDATES:
            self.assertTrue(candidate.startswith("/"), candidate)
        text = (SRC / "gitread.py").read_text(encoding="utf-8")
        for searcher in ("shutil.which", "os.environ", 'get("PATH"', "PATH]"):
            self.assertNotIn(searcher, text, "the PATH must never be searched for a binary")

    def test_the_git_allowlist_admits_nothing_that_can_change_a_repository(self):
        from daily_core.gitread import ALLOWED
        for banned in ("commit", "push", "add", "checkout", "switch", "reset", "restore", "gc",
                       "fetch", "pull", "clone", "merge", "rebase", "cherry-pick", "revert",
                       "filter-branch", "update-ref", "update-index", "am", "apply", "stash",
                       "tag", "branch", "remote", "submodule", "clean", "prune", "repack"):
            self.assertNotIn(banned, ALLOWED, "{0} would let this package write".format(banned))


class TestNoCredentials(unittest.TestCase):
    """No string constant anywhere names a credential store.

    Scanning string constants rather than raw lines is the point: prose about tokens belongs in a
    docstring, and a path to one never does. Only literals the code could actually open are read.
    """

    CREDENTIAL_PATH = re.compile(
        r"\.ssh|id_rsa|id_ed25519|keychain|\.netrc|\.claude\.json|auth\.json|credentials?\.(json|yml|yaml)|"
        r"\.aws/|\.docker/config|\.npmrc|\.pypirc|token\.(json|txt)|secrets?\.(json|env)|\.env\b", re.I)

    def test_no_string_constant_names_a_credential_store(self):
        for path in PY_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 200:
                    m = self.CREDENTIAL_PATH.search(node.value)
                    self.assertIsNone(m, "{0}: string {1!r} names a credential store".format(
                        path, node.value[:80]))

    def test_the_documented_promise_is_in_every_description(self):
        seen = 0
        for doc in sorted(pathlib.Path("docs/plays").glob("*/DESCRIPTION.md")):
            if doc.parent.name not in DAILY_PLAYS:
                continue
            seen += 1
            text = doc.read_text(encoding="utf-8")
            self.assertIn("Never reads", text, doc)
            self.assertIn("Never sends", text, doc)
        self.assertEqual(seen, len(DAILY_PLAYS), "a Play in the spec has no registry copy")


class TestWritesAreConfined(unittest.TestCase):
    """One function opens a file for writing, and it resolves its path under the caller's out_dir."""

    def test_only_the_shared_helper_opens_a_file_for_writing(self):
        for path in PY_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # A bare write_text(...) is the shared helper; path.write_text(...) is a direct write.
                if (isinstance(node.func, ast.Attribute) and node.func.attr in ("write_text", "write_bytes")
                        and path.name != "common.py"):
                    self.fail("{0} writes directly; use common.write_text so writes stay in out_dir".format(path))
                if getattr(node.func, "id", "") == "open" and len(node.args) > 1:
                    mode = node.args[1]
                    if isinstance(mode, ast.Constant) and any(m in str(mode.value) for m in "wax+"):
                        self.fail("{0} opens a file for writing".format(path))

    def test_the_write_helper_builds_its_path_from_out_dir(self):
        text = (SRC / "common.py").read_text(encoding="utf-8")
        self.assertIn("def out_path(out_dir, name: str)", text)
        self.assertIn("def write_text(out_dir, name: str, text: str)", text)
        self.assertIn("p = out_path(out_dir, name)", text)

    def test_the_only_other_write_is_a_temporary_copy_of_a_database(self):
        text = (SRC / "common.py").read_text(encoding="utf-8")
        self.assertIn("tempfile.mkdtemp", text)
        self.assertIn("mode=ro", text, "a copied database must still be opened read-only")


class TestStdlibOnly(unittest.TestCase):
    def test_nothing_imports_a_third_party_package(self):
        stdlib = {
            "argparse", "ast", "collections", "csv", "dataclasses", "datetime", "decimal", "email",
            "glob", "hashlib", "html", "io", "json", "os", "pathlib", "platform", "plistlib",
            "quopri", "re", "shutil", "sqlite3", "struct", "subprocess", "sys", "tempfile", "time",
            "unicodedata", "zlib",
        }
        for path in PY_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], stdlib, "{0}: {1}".format(path, alias.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    self.assertIn(node.module.split(".")[0], stdlib, "{0}: {1}".format(path, node.module))

    def test_every_module_parses_as_python_39(self):
        """The declared floor. A match statement or a bare X | None annotation fails here, not on a user."""
        for path in PY_FILES:
            try:
                ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 9))
            except SyntaxError as exc:
                self.fail("{0} does not parse as Python 3.9: {1}".format(path, exc))


if __name__ == "__main__":
    unittest.main()
