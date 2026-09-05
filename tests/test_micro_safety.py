"""The promises micro_core makes, asserted rather than described.

Offline, no subprocess, writes only where it said it writes, and nothing it reads to warn you
about a secret is ever printed back out.
"""
import ast
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from micro_core import cli

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "micro_core"
FORBIDDEN = ("urllib", "http", "httplib", "socket", "requests", "subprocess", "ftplib",
             "telnetlib", "smtplib", "asyncio", "multiprocessing", "ssl", "xmlrpc")


def run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(args)
    lines = buf.getvalue().rstrip("\n").split("\n")
    return rc, "\n".join(lines[:-1]), json.loads(lines[-1])


class TestOffline(unittest.TestCase):
    def test_micro_core_imports_nothing_that_can_reach_the_network(self):
        for path in sorted(CORE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    root = m.split(".")[0]
                    self.assertNotIn(root, FORBIDDEN,
                                     "{0} imports {1}".format(path.name, m))

    def test_no_shelling_out(self):
        for path in sorted(CORE.rglob("*.py")):
            body = path.read_text(encoding="utf-8")
            for banned in ("os.system", "os.popen", "os.exec", "os.spawn", "eval(", "exec("):
                self.assertNotIn(banned, body, "{0} contains {1}".format(path.name, banned))

    def test_the_only_cross_core_import_is_the_price_table(self):
        """fits, last-turn and budget-left borrow comped_core's prices. Nothing else may."""
        allowed = {"comped_core.prices", "comped_core.pricing", "comped_core.models"}
        for path in sorted(CORE.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                mod = getattr(node, "module", None) if isinstance(node, ast.ImportFrom) else None
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
                for m in [x for x in [mod] + names if x]:
                    if m.startswith("comped_core") or m.startswith("daily_core"):
                        self.assertIn(m, allowed, "{0} imports {1}".format(path.name, m))


class TestWriteConfinement(unittest.TestCase):
    def _steps(self, state, vault, root):
        return [
            ["punch", "record", "--note", "api", "--state-dir", state],
            ["punch", "report", "--state-dir", state],
            ["spent", "record", "--entry", "10 lunch", "--state-dir", state],
            ["spent", "report", "--state-dir", state],
            ["jot", "record", "--note", "a thought", "--vault-dir", vault, "--state-dir", state],
            ["jot", "report", "--vault-dir", vault, "--state-dir", state],
            ["streak", "record", "--did", "water", "--state-dir", state],
            ["streak", "report", "--state-dir", state],
            ["since-last", "report", "--root", root, "--state-dir", state, "--watch-sensitive", "false"],
            ["whatis", "report", "--text", "aGVsbG8gd29ybGQ="],
            ["fits", "report", "--text", "hello"],
            ["secret", "report", "--text", "k=1"],
            ["cron", "report", "--expr", "@daily"],
            ["last-turn", "report", "--claude-dir", root, "--codex-dir", root],
            ["budget", "report", "--claude-dir", root, "--codex-dir", root],
            ["staged", "report", "--repo", root],
        ]

    def test_nothing_is_written_outside_state_dir_and_vault_dir(self):
        home = tempfile.mkdtemp()
        state = os.path.join(home, "state")
        vault = os.path.join(home, "vault")
        root = os.path.join(home, "work")
        os.makedirs(root)
        with open(os.path.join(root, "a.py"), "w") as fh:
            fh.write("x\n")
        before = self._tree(home)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            for args in self._steps(state, vault, root):
                run(args + ["--now", "2026-09-05T12:00:00Z"])
        finally:
            if old_home is not None:
                os.environ["HOME"] = old_home
        changed = sorted(set(self._tree(home)) - set(before))
        self.assertTrue(changed, "the write steps wrote nothing at all")
        for path in changed:
            self.assertTrue(path.startswith(state) or path.startswith(vault),
                            "wrote outside the declared directories: {0}".format(path))

    def _tree(self, root):
        out = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                out.append(os.path.join(dirpath, name))
        return sorted(out)

    def test_a_read_only_play_writes_nothing_at_all(self):
        home = tempfile.mkdtemp()
        before = self._tree(home)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            for args in (["whatis", "report", "--text", "1788600000"],
                         ["fits", "report", "--text", "hello"],
                         ["secret", "report", "--text", "k=1"],
                         ["cron", "report", "--expr", "@daily"],
                         ["staged", "report", "--demo", "true"]):
                run(args + ["--now", "2026-09-05T12:00:00Z"])
        finally:
            if old_home is not None:
                os.environ["HOME"] = old_home
        self.assertEqual(self._tree(home), before)


class TestNoSecretEscapes(unittest.TestCase):
    def test_is_it_secret_never_prints_the_secret_it_found(self):
        key = "AKIA1234567890ABCD12"
        rc, human, j = run(["secret", "report", "--text", "k=" + key, "--show", "redacted"])
        self.assertNotIn(key, human)
        self.assertNotIn(key, json.dumps(j))

    def test_the_redacted_copy_is_safe_to_paste(self):
        text = "AWS=AKIA1234567890ABCD12\nGH=ghp_" + "q" * 36
        rc, human, j = run(["secret", "report", "--text", text])
        self.assertNotIn("AKIA1234567890ABCD12", j["redacted"])
        self.assertNotIn("ghp_" + "q" * 36, j["redacted"])
        self.assertIn("<REDACTED:", j["redacted"])

    def test_whatis_never_prints_a_jwt_signature(self):
        tok = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
               "eyJzdWIiOiJ1c2VyXzg4MTIiLCJleHAiOjE3ODg2MDAwMDB9.c2lnbmF0dXJlLWJ5dGVz")
        rc, human, j = run(["whatis", "report", "--text", tok])
        self.assertNotIn("c2lnbmF0dXJlLWJ5dGVz", human + json.dumps(j))

    def test_safe_to_commit_never_prints_the_staged_key(self):
        rc, human, j = run(["staged", "report", "--demo", "true"])
        self.assertNotIn("AKIA9F2K1LQ8ZXVB4TDM", human + json.dumps(j))
