"""The three fetch steps: what they may do, what they may not, and that a demo run does neither.

`daily_core` is proven offline by `tests/test_daily_safety.py`. Three Plays need a fetch anyway, so
the fetch lives out here in one file each -- the same arrangement `leaderboard/post_score.py` uses
for comped. That arrangement is only worth anything if these files are held to a stated shape, so
this suite states it:

1. **A demo run is inert.** No environment variable is read, no connection is opened, and nothing
   is written. It is the run a stranger makes first, and it must need no account at all.
2. **A missing credential is an absence, not a failure.** Exit 0, a `warning` in the JSON, and
   `available: false` -- the exit-zero degradation the rote process contract asks for.
3. **Nothing writes outside `out_dir`,** and no token is ever written or printed.
4. **The normalisers produce the documented partial,** checked against the schema the Play's Python
   half actually parses: each normaliser's output is fed straight into `daily_core.scan.<module>`
   and the module has to accept it.

The network is not reached anywhere below: every socket entry point is replaced for the whole of
this module, so a fetcher that tried would fail here rather than on somebody's machine.
"""
import importlib.util
import io
import json
import os
import pathlib
import socket
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parent.parent
FETCH = {"calendar": "fetch/calendar_partial.py", "mail": "fetch/mail_partial.py",
         "registry": "fetch/registry_partial.py"}
# The Play each one belongs to, and the daily_core module that reads what it writes.
OWNER = {"calendar": ("standing-cost", "standingcost"), "mail": ("reply-debt", "replydebt"),
         "registry": ("upstream-pulse", "upstream")}
STDLIB = {"argparse", "email", "json", "os", "ssl", "sys", "time", "urllib"}


class NoNetwork(AssertionError):
    """Raised if anything under test so much as reaches for a socket."""


def _forbidden(*args, **kwargs):
    raise NoNetwork("a fetch step tried to open a network connection")


def load(name: str):
    path = ROOT / FETCH[name]
    spec = importlib.util.spec_from_file_location("fetch_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(module, argv) -> tuple:
    """(exit code, human text, the trailing JSON object) -- the contract every step keeps."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = module.main(list(argv))
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    return code, "\n".join(lines[:-1]), json.loads(lines[-1])


class Offline(object):
    NAMES = ("socket", "socketpair", "create_connection", "getaddrinfo", "gethostbyname")

    def __enter__(self):
        self._saved = {}
        for name in self.NAMES:
            if hasattr(socket, name):
                self._saved[name] = getattr(socket, name)
                setattr(socket, name, _forbidden)
        return self

    def __exit__(self, *exc):
        for name, original in self._saved.items():
            setattr(socket, name, original)
        return False


class FetchSteps(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        # Import first, arm second: `ssl` subclasses `socket.socket` at import time, so a guard
        # that is already in place would break the import rather than the connection.
        cls.modules = {name: load(name) for name in FETCH}
        cls._offline = Offline()
        cls._offline.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._offline.__exit__(None, None, None)

    def test_the_network_guard_is_actually_armed(self):
        with self.assertRaises(NoNetwork):
            socket.socket()

    # -- 1. a demo run is inert ---------------------------------------------------------------

    def test_a_demo_run_opens_nothing_reads_no_variable_and_writes_nothing(self):
        for name, module in self.modules.items():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as out:
                # A token in the environment must make no difference at all in demo mode.
                key = "DEMO_PROBE_TOKEN"
                os.environ[key] = "must-not-be-read"
                try:
                    code, text, doc = run(module, ["--out-dir", out, "--demo", "true",
                                                   "--token-env", key]
                                          if name != "registry" else
                                          ["--out-dir", out, "--demo", "true"])
                finally:
                    os.environ.pop(key, None)
                self.assertEqual(code, 0)
                self.assertTrue(doc["ok"])
                self.assertFalse(doc["available"])
                self.assertTrue(doc["demo"])
                self.assertIn("warning", doc)
                self.assertEqual(sorted(os.listdir(out)), [], "a demo run wrote a file")
                self.assertNotIn("must-not-be-read", text + json.dumps(doc))

    # -- 2. a missing credential is an absence -------------------------------------------------

    def test_no_credential_is_a_labelled_absence_and_still_exits_zero(self):
        for name in ("calendar", "mail"):
            with self.subTest(step=name), tempfile.TemporaryDirectory() as out:
                key = "ABSENT_PROBE_TOKEN"
                os.environ.pop(key, None)
                code, text, doc = run(self.modules[name],
                                      ["--out-dir", out, "--demo", "false", "--token-env", key])
                self.assertEqual(code, 0)
                self.assertTrue(doc["ok"])
                self.assertFalse(doc["available"])
                self.assertIn("warning", doc)
                self.assertIn(key, text, "the step must name the variable it looked for")
                self.assertEqual(sorted(os.listdir(out)), [])

    def test_the_registry_step_without_an_inventory_is_a_labelled_absence(self):
        with tempfile.TemporaryDirectory() as out:
            code, _text, doc = run(self.modules["registry"],
                                   ["--out-dir", out, "--demo", "false"])
            self.assertEqual(code, 0)
            self.assertTrue(doc["ok"])
            self.assertFalse(doc["available"])
            self.assertEqual(doc["checked"], 0)
            self.assertEqual(sorted(os.listdir(out)), [])

    # -- 3. the shape of the files themselves --------------------------------------------------

    def test_every_write_lands_under_out_dir(self):
        """Every path opened for writing resolves from `out_dir`, and each one is traced to it.

        The check is on the binding rather than on the call, because the interesting mistake is
        not `open(x, "w")` -- it is `x` having come from somewhere other than the parameter the
        description promises everything is written under.
        """
        import ast
        for name, relpath in FETCH.items():
            tree = ast.parse((ROOT / relpath).read_text(encoding="utf-8"))
            bindings = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and node.value is not None:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            bindings[target.id] = ast.dump(node.value)
            writes = 0
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open"):
                    continue
                mode = node.args[1] if len(node.args) > 1 else None
                if not (isinstance(mode, ast.Constant)
                        and any(m in str(mode.value) for m in "wax+")):
                    continue
                writes += 1
                path = node.args[0]
                source = bindings.get(path.id, "") if isinstance(path, ast.Name) else ast.dump(path)
                with self.subTest(step=name):
                    self.assertIn("out_dir", source,
                                  "a write whose path does not resolve from out_dir")
            with self.subTest(step=name):
                self.assertLessEqual(writes, 2, "{0} opens more files for writing "
                                                "than it documents".format(relpath))

    def test_nothing_here_starts_a_process_or_reads_a_credential_file(self):
        """Same shape as the core's own proof: string constants a caller could open, not prose.

        A docstring that says "this opens no keychain" is exactly the sentence worth writing, so
        the scan is over short literals the code could pass to `open`, never over the file's text.
        """
        import ast
        import re
        credential = re.compile(
            r"\.ssh|id_rsa|id_ed25519|keychain|\.netrc|\.claude\.json|auth\.json|"
            r"credentials?\.(json|yml|yaml)|\.aws/|\.docker/config|\.npmrc|\.pypirc|"
            r"token\.(json|txt)|secrets?\.(json|env)", re.I)
        for name, relpath in FETCH.items():
            text = (ROOT / relpath).read_text(encoding="utf-8")
            with self.subTest(step=name):
                self.assertNotIn("subprocess", text)
                self.assertNotIn("os.system", text)
                for node in ast.walk(ast.parse(text)):
                    if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                            and len(node.value) < 200):
                        self.assertIsNone(credential.search(node.value),
                                          "{0}: {1!r} names a credential store".format(
                                              relpath, node.value[:80]))

    def test_the_mail_step_calls_no_method_that_could_change_a_mailbox(self):
        text = (ROOT / FETCH["mail"]).read_text(encoding="utf-8")
        for banned in ("POST", "PUT", "PATCH", "DELETE", "/send", "drafts", "modify", "trash",
                       "batchModify"):
            self.assertNotIn(banned, text, "the mail step must only read")

    def test_the_calendar_step_writes_nothing_back_to_the_calendar(self):
        text = (ROOT / FETCH["calendar"]).read_text(encoding="utf-8")
        for banned in ("POST", "PUT", "PATCH", "DELETE", "insert", "quickAdd"):
            self.assertNotIn(banned, text, "the calendar step must only read")

    def test_every_import_is_the_standard_library(self):
        import ast
        for name, relpath in FETCH.items():
            tree = ast.parse((ROOT / relpath).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        with self.subTest(step=name):
                            self.assertIn(alias.name.split(".")[0], STDLIB)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    with self.subTest(step=name):
                        self.assertIn(node.module.split(".")[0], STDLIB)

    def test_every_module_parses_as_python_39(self):
        import ast
        for name, relpath in FETCH.items():
            with self.subTest(step=name):
                ast.parse((ROOT / relpath).read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_each_fetcher_is_shipped_only_in_the_play_that_uses_it(self):
        import subprocess
        import sys
        subprocess.run([sys.executable, "tools/sync_plays.py"], cwd=str(ROOT), check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        spec = json.loads((ROOT / "docs/plays/_daily-spec.json").read_text(encoding="utf-8"))
        for name, relpath in FETCH.items():
            owner = OWNER[name][0]
            for slug in spec:
                shipped = (ROOT / "plays" / slug / "resources" / relpath).is_file()
                with self.subTest(step=name, play=slug):
                    self.assertEqual(shipped, slug == owner)
            with self.subTest(step=name):
                self.assertEqual((ROOT / "plays" / owner / "resources" / relpath).read_bytes(),
                                 (ROOT / relpath).read_bytes())

    # -- 4. the normalisers produce what the Python half parses ---------------------------------

    def test_the_calendar_normaliser_produces_a_partial_standing_cost_reads(self):
        from daily_core.common import Budget
        from daily_core.scan import standingcost
        module = self.modules["calendar"]
        google = {
            "id": "evt_1", "recurringEventId": "series_1", "summary": "Weekly sync",
            "start": {"dateTime": "2026-01-05T09:00:00+00:00", "timeZone": "Europe/London"},
            "end": {"dateTime": "2026-01-05T09:30:00+00:00"},
            "status": "confirmed", "description": "x" * 100,
            "organizer": {"email": "alice@example.com"},
            "attendees": [{"email": "alice@example.com", "displayName": "Alice Brown",
                           "responseStatus": "accepted", "self": True, "organizer": True},
                          {"email": "bob@example.com", "responseStatus": "declined"}],
        }
        event = module.normalise(google, "Europe/London")
        self.assertEqual(event["id"], "evt_1")
        self.assertEqual(event["recurring_event_id"], "series_1")
        self.assertTrue(event["has_agenda"])
        self.assertFalse(event["attendance_recorded"], "Google records invitations, not attendance")
        self.assertEqual(event["attendees"][1]["response_status"], "declined")
        # An all-day event carries no clock time and must be dropped rather than priced.
        self.assertEqual(module.normalise({"id": "e", "start": {"date": "2026-01-05"},
                                           "end": {"date": "2026-01-06"}}, ""), {})
        with tempfile.TemporaryDirectory() as out:
            path = os.path.join(out, module.PARTIAL)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"schema": module.SCHEMA, "source": "google-calendar",
                                     "timezone": "Europe/London", "events": [event]}))
            sources, events = standingcost.read_source(
                "calendar", Budget(max_seconds=5), {"partial": module.PARTIAL, "out_dir": out})
        self.assertTrue(sources[0].found, sources[0].note)
        self.assertEqual(len(events), 1)

    def test_the_mail_normaliser_produces_a_partial_reply_debt_reads(self):
        from daily_core.common import Budget
        from daily_core.scan import replydebt
        module = self.modules["mail"]
        def msg(sender, to, date, subject, snippet, extra=()):
            headers = [{"name": "From", "value": sender}, {"name": "To", "value": to},
                       {"name": "Date", "value": date}, {"name": "Subject", "value": subject}]
            headers += [{"name": k, "value": v} for k, v in extra]
            return {"payload": {"headers": headers}, "snippet": snippet, "labelIds": ["INBOX"]}
        gmail = {"id": "t-1", "messages": [
            msg("You <you@example.com>", "Dana <dana@example.com>",
                "Mon, 22 Jun 2026 12:00:00 +0000", "Redlines", "Here is where we got to."),
            msg("Dana <dana@example.com>", "You <you@example.com>",
                "Fri, 26 Jun 2026 12:00:00 +0000", "Redlines", "Could you send the signed copy?"),
        ]}
        item = module.thread(gmail, ["you@example.com"])
        self.assertEqual(item["thread_id"], "t-1")
        self.assertEqual([m["direction"] for m in item["messages"]], ["outbound", "inbound"])
        self.assertEqual(len(item["participants"]), 2)
        # A mailing-list header is an adapter hint the Python half uses to exclude the thread.
        listed = module.thread({"id": "t-2", "messages": [
            msg("List <list@example.com>", "You <you@example.com>",
                "Fri, 26 Jun 2026 12:00:00 +0000", "Weekly", "News.",
                extra=[("List-Id", "<weekly.example.com>")])]}, ["you@example.com"])
        self.assertTrue(listed["messages"][0]["is_automated"])
        self.assertEqual(listed["messages"][0]["list_id"], "<weekly.example.com>")
        with tempfile.TemporaryDirectory() as out:
            path = os.path.join(out, "mail.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"schema": module.SCHEMA, "account": "you@example.com",
                                     "me": ["you@example.com"], "threads": [item, listed]}))
            sources, threads = replydebt.read_source("mail", Budget(max_seconds=5),
                                                     {"partial": path})
        self.assertTrue(sources[0].found, sources[0].note)
        self.assertEqual(len(threads), 2)

    def test_the_registry_normalisers_produce_a_partial_upstream_pulse_reads(self):
        from daily_core.scan import upstream
        module = self.modules["registry"]
        npm = module._npm("left-pad", {
            "dist-tags": {"latest": "1.3.0"},
            "versions": {"1.3.0": {"deprecated": "use String.prototype.padStart"}},
            "time": {"created": "2014-01-01T00:00:00Z", "1.0.0": "2016-03-23T00:00:00Z",
                     "1.3.0": "2018-05-17T00:00:00Z"},
            "maintainers": [{"name": "someone"}], "license": "WTFPL"})
        self.assertEqual(npm["latest_version"], "1.3.0")
        self.assertEqual(npm["last_release_date"], "2018-05-17T00:00:00Z")
        self.assertEqual(npm["maintainer_count"], 1)
        self.assertTrue(npm["deprecated"])
        pypi = module._pypi("six", {
            "info": {"version": "1.16.0", "license": "MIT",
                     "classifiers": ["Development Status :: 7 - Inactive"]},
            "releases": {"1.16.0": [{"upload_time_iso_8601": "2021-05-05T12:00:00Z"}]}})
        self.assertTrue(pypi["deprecated"])
        self.assertEqual(pypi["last_release_date"], "2021-05-05T12:00:00Z")
        # PyPI publishes no publisher count, so the field must be absent rather than a guessed 1.
        self.assertNotIn("maintainer_count", pypi)
        crates = module._crates("serde", {
            "crate": {"max_stable_version": "1.0.0"},
            "versions": [{"created_at": "2026-01-01T00:00:00Z", "license": "MIT"}]})
        self.assertEqual(crates["latest_version"], "1.0.0")
        entries = []
        for eco, entry, name in (("npm", npm, "left-pad"), ("pypi", pypi, "six"),
                                 ("crates", crates, "serde")):
            row = dict(entry)
            row.update({"name": name, "ecosystem": eco, "pinned_version": "0.0.1", "error": ""})
            entries.append(row)
        with tempfile.TemporaryDirectory() as out:
            path = os.path.join(out, module.PARTIAL)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"schema": module.SCHEMA, "cached_at": "2026-09-01T00:00:00Z",
                                     "source": module.SOURCE, "requested": 3,
                                     "packages": entries}))
            sources, records = upstream.read_source("registry", None,
                                                    {"out_dir": out, "registry_partial": path})
        self.assertTrue(sources[0].found, sources[0].note)
        # One meta record naming the fetch, then one per package.
        meta = [r for r in records if r.get("kind") == "registry_meta"]
        self.assertEqual(len(meta), 1)
        self.assertEqual(meta[0]["source"], module.SOURCE)
        self.assertEqual(sorted(r["name"] for r in records if r.get("kind") == "registry"),
                         ["left-pad", "serde", "six"])

    def test_the_lookup_bound_spends_itself_on_direct_dependencies_first(self):
        module = self.modules["registry"]
        records = [{"ecosystem": "npm", "name": "deep", "direct": False, "version": "1"},
                   {"ecosystem": "npm", "name": "chosen", "direct": True, "version": "2"},
                   {"ecosystem": "pypi", "name": "local-thing", "direct": True, "local": True},
                   {"ecosystem": "go", "name": "unsupported", "direct": True}]
        rows = module.wanted(records, module.ECOSYSTEMS, 2)
        self.assertEqual([name for _eco, name, _v in rows], ["chosen", "deep"])
        self.assertEqual(module.wanted(records, module.ECOSYSTEMS, 1)[0][1], "chosen")


if __name__ == "__main__":
    unittest.main()
