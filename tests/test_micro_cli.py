"""Step-level tests: every step exits 0, prints one JSON object last, and says the same thing twice."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from micro_core import cli, store


def run(args):
    """Run one CLI step; return (exit code, human text, parsed final JSON line)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(args)
    lines = buf.getvalue().rstrip("\n").split("\n")
    return rc, "\n".join(lines[:-1]), json.loads(lines[-1])


class TestPunch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_record_then_report_counts_switches(self):
        for at, note in [("09:00", "api"), ("09:40", "api"), ("10:30", "docs"), ("11:00", "api")]:
            rc, _, j = run(["punch", "record", "--note", note, "--state-dir", self.dir,
                            "--now", "2026-09-05T{0}:00Z".format(at)])
            self.assertEqual(rc, 0)
            self.assertTrue(j["ok"])
        rc, human, j = run(["punch", "report", "--state-dir", self.dir, "--tz", "UTC",
                            "--now", "2026-09-05T11:30:00Z"])
        self.assertEqual(rc, 0)
        self.assertEqual(j["punches"], 4)
        self.assertEqual(j["switches"], 2)
        self.assertEqual(j["current_block_min"], 30)
        self.assertIn("switch", human)

    def test_report_with_no_history_warns_and_exits_zero(self):
        rc, human, j = run(["punch", "report", "--state-dir", self.dir, "--now", "2026-09-05T11:30:00Z"])
        self.assertEqual(rc, 0)
        self.assertTrue(j["ok"])
        self.assertIn("warning", j)

    def test_record_with_no_note_records_nothing(self):
        rc, _, j = run(["punch", "record", "--state-dir", self.dir, "--now", "2026-09-05T09:00:00Z"])
        self.assertEqual(rc, 0)
        self.assertFalse(j["recorded"])
        self.assertEqual(store.read(self.dir, "punch"), [])

    def test_tag_beats_the_note_as_the_topic(self):
        run(["punch", "record", "--note", "fixing the parser", "--tag", "api",
             "--state-dir", self.dir, "--now", "2026-09-05T09:00:00Z"])
        run(["punch", "record", "--note", "different words entirely", "--tag", "api",
             "--state-dir", self.dir, "--now", "2026-09-05T10:00:00Z"])
        _rc, _h, j = run(["punch", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T10:30:00Z"])
        self.assertEqual(j["switches"], 0)

    def test_output_is_byte_identical_for_a_fixed_now(self):
        run(["punch", "record", "--note", "api", "--state-dir", self.dir, "--now", "2026-09-05T09:00:00Z"])
        a = run(["punch", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T11:30:00Z"])
        b = run(["punch", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T11:30:00Z"])
        self.assertEqual(a, b)


class TestSpent(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_parses_symbol_amount_label_and_tag(self):
        d = store.parse_entry("₹320 lunch #food", "INR")
        self.assertEqual((str(d["amount"]), d["currency"], d["label"], d["tag"]),
                         ("320", "INR", "lunch", "food"))

    def test_bare_number_uses_default_currency(self):
        self.assertEqual(store.parse_entry("12.50 coffee", "USD")["currency"], "USD")

    def test_no_amount_is_a_value_error(self):
        with self.assertRaises(ValueError):
            store.parse_entry("lunch", "USD")

    def test_month_total_and_projection(self):
        for d, amt in [("01", "100"), ("02", "200"), ("03", "300")]:
            rc, _, j = run(["spent", "record", "--entry", amt + " food", "--currency", "INR",
                            "--state-dir", self.dir, "--now", "2026-09-{0}T10:00:00Z".format(d)])
            self.assertTrue(j["recorded"])
        rc, human, j = run(["spent", "report", "--state-dir", self.dir, "--budget", "6000", "--tz", "UTC",
                            "--now", "2026-09-03T20:00:00Z"])
        self.assertEqual(j["month"], "600.00")
        self.assertEqual(j["today"], "300.00")
        self.assertEqual(j["projection"], "6000.00")
        self.assertFalse(j["over"])
        self.assertIn("food", human)

    def test_a_bad_entry_explains_itself_and_exits_zero(self):
        rc, human, j = run(["spent", "record", "--entry", "lunch", "--state-dir", self.dir,
                            "--now", "2026-09-05T10:00:00Z"])
        self.assertEqual(rc, 0)
        self.assertFalse(j["recorded"])
        self.assertIn("amount", j["warning"])

    def test_mixed_currencies_are_kept_apart(self):
        run(["spent", "record", "--entry", "$10 coffee", "--state-dir", self.dir,
             "--now", "2026-09-05T09:00:00Z"])
        run(["spent", "record", "--entry", "₹500 lunch", "--state-dir", self.dir,
             "--now", "2026-09-05T13:00:00Z"])
        _rc, _h, j = run(["spent", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T20:00:00Z"])
        self.assertEqual({c["currency"] for c in j["currencies"]}, {"USD", "INR"})


class TestJot(unittest.TestCase):
    def setUp(self):
        self.state, self.vault = tempfile.mkdtemp(), tempfile.mkdtemp()

    def test_writes_a_markdown_line_into_the_vault_inbox(self):
        rc, _, j = run(["jot", "record", "--note", "ring the dentist", "--vault-dir", self.vault,
                        "--state-dir", self.state, "--now", "2026-09-05T14:22:00Z"])
        self.assertEqual(rc, 0)
        with open(os.path.join(self.vault, "Inbox.md")) as fh:
            body = fh.read()
        self.assertIn("ring the dentist", body)
        self.assertIn(j["written"], (os.path.join(self.vault, "Inbox.md"),))

    def test_identical_note_within_a_minute_is_refused(self):
        args = ["jot", "record", "--note", "same", "--vault-dir", self.vault, "--state-dir", self.state]
        run(args + ["--now", "2026-09-05T14:22:00Z"])
        rc, _, j = run(args + ["--now", "2026-09-05T14:22:30Z"])
        self.assertFalse(j["recorded"])
        self.assertEqual(j["reason"], "duplicate")
        with open(os.path.join(self.vault, "Inbox.md")) as fh:
            self.assertEqual(fh.read().count("same"), 1)

    def test_the_same_note_an_hour_later_is_a_new_thought(self):
        args = ["jot", "record", "--note", "same", "--vault-dir", self.vault, "--state-dir", self.state]
        run(args + ["--now", "2026-09-05T14:22:00Z"])
        rc, _, j = run(args + ["--now", "2026-09-05T15:22:00Z"])
        self.assertTrue(j["recorded"])

    def test_no_vault_dir_still_records_to_the_log(self):
        rc, _, j = run(["jot", "record", "--note", "x", "--state-dir", self.state,
                        "--now", "2026-09-05T14:22:00Z"])
        self.assertTrue(j["recorded"])
        self.assertEqual(len(store.read(self.state, "jot")), 1)

    def test_report_counts_the_inbox(self):
        for i, note in enumerate(["a", "b", "c"]):
            run(["jot", "record", "--note", note, "--vault-dir", self.vault, "--state-dir", self.state,
                 "--now", "2026-09-05T1{0}:00:00Z".format(i)])
        rc, human, j = run(["jot", "report", "--vault-dir", self.vault, "--state-dir", self.state,
                            "--tz", "UTC", "--now", "2026-09-05T20:00:00Z"])
        self.assertEqual(j["today"], 3)
        self.assertEqual(j["inbox_lines"], 3)


class TestStreak(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_two_habits_are_tracked_apart(self):
        for d in ("03", "04", "05"):
            run(["streak", "record", "--did", "water", "--state-dir", self.dir,
                 "--now", "2026-09-{0}T09:00:00Z".format(d)])
        run(["streak", "record", "--did", "gym", "--state-dir", self.dir, "--now", "2026-09-05T18:00:00Z"])
        rc, human, j = run(["streak", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T20:00:00Z"])
        by = {h["name"]: h for h in j["habits"]}
        self.assertEqual(by["water"]["current"], 3)
        self.assertEqual(by["gym"]["current"], 1)
        self.assertEqual(j["best"], "water")
        self.assertIn("water", human)

    def test_recording_the_same_habit_twice_in_a_day_is_one_day(self):
        for at in ("09:00", "18:00"):
            run(["streak", "record", "--did", "water", "--state-dir", self.dir,
                 "--now", "2026-09-05T{0}:00Z".format(at)])
        _rc, _h, j = run(["streak", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T20:00:00Z"])
        self.assertEqual(j["habits"][0]["current"], 1)

    def test_no_habits_yet_warns(self):
        _rc, _h, j = run(["streak", "report", "--state-dir", self.dir, "--tz", "UTC", "--now", "2026-09-05T20:00:00Z"])
        self.assertIn("warning", j)


class TestWhatis(unittest.TestCase):
    def test_reports_the_chain_and_the_first_kind(self):
        import base64
        blob = base64.b64encode(b'{"hello":"world"}').decode()
        rc, human, j = run(["whatis", "report", "--text", blob])
        self.assertEqual(rc, 0)
        self.assertEqual(j["kind"], "base64")
        self.assertEqual(j["chain"], "base64 → json")
        self.assertIn("2 layers deep", human)

    def test_no_text_warns_and_exits_zero(self):
        rc, human, j = run(["whatis", "report"])
        self.assertEqual(rc, 0)
        self.assertIn("warning", j)


class TestSecretStep(unittest.TestCase):
    def test_blocker_makes_the_verdict_do_not_paste(self):
        rc, human, j = run(["secret", "report", "--text", "k=AKIA1234567890ABCD12"])
        self.assertEqual(rc, 0)
        self.assertEqual(j["verdict"], "do-not-paste")
        self.assertIn("do not paste", human)

    def test_the_secret_itself_is_never_printed(self):
        key = "AKIA1234567890ABCD12"
        rc, human, j = run(["secret", "report", "--text", "k=" + key])
        self.assertNotIn(key, human)
        self.assertNotIn(key, json.dumps(j))

    def test_clean_text_says_so(self):
        rc, human, j = run(["secret", "report", "--text", "host=db\nport=5432"])
        self.assertEqual(j["verdict"], "safe")
        self.assertEqual(j["findings"], [])

    def test_reads_a_file_by_path(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "dev.env")
        with open(p, "w") as fh:
            fh.write("API_KEY=AKIA1234567890ABCD12\n")
        rc, human, j = run(["secret", "report", "--path", p])
        self.assertEqual(j["verdict"], "do-not-paste")
        self.assertIn("dev.env", j["source"])
