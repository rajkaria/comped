"""reply-debt: the promises the card makes, asserted against a mailbox written on the spot.

Two of these tests matter more than the rest. The first is the one that proves the module is still
offline: a mail Play is exactly where a networking import would sneak into a package whose whole
claim is that it has none. The second is the quoted-history case — a thread whose only question
mark is inside the history it quotes back at you is the single most common way this kind of
heuristic embarrasses itself, so it gets its own fixture and its own assertion.
"""
import json
import pathlib
import re
import tempfile
import unittest
from datetime import datetime, timezone

from daily_core.common import Budget, baseline_read
from daily_core.scan import replydebt

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
ME = "you@example.com"
SRC = pathlib.Path("daily_core/scan/replydebt.py")


def msg(sender, when, snippet, subject="", direction="", **extra):
    m = {"from": sender, "to": [{"name": "You", "email": ME}], "date": when,
         "snippet": snippet, "subject": subject}
    if direction:
        m["direction"] = direction
    m.update(extra)
    return m


DANA = {"name": "Dana Okoye", "email": "dana@example.com"}
PRIYA = {"name": "Priya Raman", "email": "priya@example.com"}
SAM = {"name": "Sam Beckett", "email": "sam@example.com"}
MARCUS = {"name": "Marcus Hall", "email": "marcus@example.com"}
NADIA = {"name": "Nadia Farouk", "email": "nadia@example.com"}
YOU = {"name": "You", "email": ME}


def mailbox() -> dict:
    """One mailbox carrying every case the card claims to distinguish."""
    threads = [
        # Four threads from one person: a relationship, not four separate tasks.
        {"thread_id": "t-dana-1", "subject": "Contract redlines",
         "messages": [msg(DANA, "2026-06-03T12:00:00Z",
                          "Could you send the signed copy by Friday?", "Contract redlines")]},
        {"thread_id": "t-dana-2", "subject": "Statement of work",
         "messages": [msg(YOU, "2026-07-20T09:00:00Z", "Draft attached.", "Statement of work"),
                      msg(DANA, "2026-07-27T12:00:00Z",
                          "Any update on the numbers in section 3?", "Statement of work")]},
        {"thread_id": "t-dana-3", "subject": "Invoice 4417",
         "messages": [msg(DANA, "2026-08-16T12:00:00Z",
                          "Circling back on this one.", "Invoice 4417")]},
        {"thread_id": "t-dana-4", "subject": "Kickoff notes",
         "messages": [msg(DANA, "2026-08-26T12:00:00Z",
                          "Let me know which of the two options you prefer.", "Kickoff notes")]},

        # FYI with an implied action: no question, no modal, but a deadline sits inside it.
        {"thread_id": "t-implied", "subject": "Deck v4",
         "messages": [msg(PRIYA, "2026-08-30T12:00:00Z",
                          "Attaching the deck for your review before the call.", "Deck v4")]},

        # Pure FYI: nothing is being asked of anyone.
        {"thread_id": "t-fyi", "subject": "Release notes",
         "messages": [msg(SAM, "2026-08-20T12:00:00Z",
                          "The release notes are attached for the record.", "Release notes")]},

        # Already answered: the newest message is yours, and it asks nothing.
        {"thread_id": "t-answered", "subject": "Hotel booking",
         "messages": [msg(SAM, "2026-08-01T12:00:00Z", "Where are you staying?", "Hotel booking"),
                      msg(YOU, "2026-08-02T12:00:00Z", "Sent it over this morning, thanks.",
                          "Hotel booking")]},

        # The other side of the ledger: you asked, nobody came back.
        {"thread_id": "t-owed", "subject": "Purchase order",
         "messages": [msg(MARCUS, "2026-07-20T12:00:00Z", "Here is the PO.", "Purchase order"),
                      msg(YOU, "2026-07-26T12:00:00Z", "Can you confirm the invoice number?",
                          "Purchase order")]},

        # Excluded: a mailing list, a no-reply sender, a calendar invite, an automated build.
        {"thread_id": "t-newsletter", "subject": "This week in Python",
         "messages": [msg({"name": "Python Weekly", "email": "hello@pyweekly.example"},
                          "2026-08-10T12:00:00Z", "Want to read more?", "This week in Python",
                          list_unsubscribe="<https://pyweekly.example/u>",
                          list_id="pyweekly.example")]},
        {"thread_id": "t-noreply", "subject": "Your statement is ready",
         "messages": [msg({"name": "Bank", "email": "no-reply@bank.example"},
                          "2026-08-11T12:00:00Z", "Would you like paperless statements?",
                          "Your statement is ready")]},
        {"thread_id": "t-calendar", "subject": "Invitation: Design review",
         "messages": [msg(PRIYA, "2026-08-12T12:00:00Z", "Can you make it?",
                          "Invitation: Design review", is_calendar=True)]},
        {"thread_id": "t-automated", "subject": "Build 8812 failed",
         "messages": [msg({"name": "CI", "email": "builds@ci.example"}, "2026-08-13T12:00:00Z",
                          "Could you look at the failing step?", "Build 8812 failed",
                          is_automated=True)]},

        # The trap: the only question mark in the thread is inside the history it quotes back.
        {"thread_id": "t-quoted", "subject": "Address confirmation",
         "messages": [msg(NADIA, "2026-09-01T12:00:00Z",
                          "Thanks, that is all clear now.\n\n"
                          "On Mon, 1 Sep 2026 at 09:00, You <you@example.com> wrote:\n"
                          "> Could you confirm the address before the call on Friday?\n"
                          "> Any update would help.\n",
                          "Address confirmation")]},

        # A real ask, but too fresh to be debt.
        {"thread_id": "t-recent", "subject": "Lunch",
         "messages": [msg(SAM, "2026-09-04T12:00:00Z", "Can you make Thursday?", "Lunch")]},
    ]
    return {"schema": 1, "me": [ME], "account": ME, "generated": "2026-09-05T12:00:00Z",
            "threads": threads}


def write_partial(root, doc=None, name="mail.json") -> str:
    p = pathlib.Path(root) / name
    p.write_text(json.dumps(doc if doc is not None else mailbox()), encoding="utf-8")
    return str(p)


def load(cfg_extra=None):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = {"partial": write_partial(tmp)}
        cfg.update(cfg_extra or {})
        sources, threads = replydebt.read_source("gmail", Budget(), cfg)
    return sources, threads


def view_of(**cfg):
    _sources, threads = load()
    return replydebt.analyse(threads, NOW, cfg)


def ids(rows):
    return sorted(r["thread_id"] for r in rows)


# ---------------------------------------------------------------- the offline claim

class TestItNeverGoesNearTheNetwork(unittest.TestCase):
    """The architectural constraint, restated where it can fail loudly.

    The Play needs Gmail; `daily_core` may not have it. The mail step writes a normalised JSON
    partial and this module computes from that file. If a future edit reaches for a socket, this
    is where it stops.
    """

    def test_the_module_imports_nothing_that_can_open_a_connection(self):
        text = SRC.read_text(encoding="utf-8")
        pattern = re.compile(
            r"^\s*(?:import|from)\s+(urllib|http|https|socket|ssl|requests|ftplib|smtplib|"
            r"imaplib|poplib|telnetlib|xmlrpc|asyncio|selectors|email)\b", re.M)
        self.assertIsNone(pattern.search(text))
        for banned in ("urlopen", "urlretrieve", "HTTPSConnection", "smtplib", "imaplib",
                       "subprocess", "socket."):
            self.assertNotIn(banned, text, banned)

    def test_the_module_calls_nothing_that_could_write_or_transmit_a_message(self):
        """Read-only by construction: no verb that composes, saves or transmits is ever called."""
        text = SRC.read_text(encoding="utf-8")
        verbs = re.compile(
            r"\b(send|sendmail|send_message|sendMessage|deliver|transmit|draft|drafts|"
            r"create_draft|createDraft|compose|reply_to|post|publish|trash|archive|"
            r"mark_read|modify)\s*\(", re.I)
        self.assertIsNone(verbs.search(text), "reply-debt must never call a mail-writing verb")

    def test_the_report_says_out_loud_that_it_only_reads(self):
        v = view_of()
        md = replydebt.report_markdown(v, {}, [])
        self.assertIn("never composes a message", md)
        self.assertIn("never transmits anything", md)
        self.assertIn("Read-only", replydebt.render(v, {}))


# ---------------------------------------------------------------- loading the partial

class TestReadingThePartial(unittest.TestCase):
    def test_a_partial_loads_and_reports_what_it_found(self):
        sources, threads = load()
        self.assertTrue(sources[0].found)
        self.assertEqual(len(threads), 14)
        self.assertEqual(sources[0].items, 14)
        self.assertIn("normalised mail partial", sources[0].note)

    def test_a_missing_partial_is_a_labelled_miss_not_an_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, threads = replydebt.read_source(
                "gmail", Budget(), {"partial": str(pathlib.Path(tmp) / "nope.json")})
        self.assertEqual(threads, [])
        self.assertFalse(sources[0].found)
        self.assertIn("the mail step has not run", sources[0].note)

    def test_no_partial_configured_at_all_is_the_same_labelled_miss(self):
        sources, threads = replydebt.read_source("gmail", Budget(), {})
        self.assertEqual(threads, [])
        self.assertFalse(sources[0].found)
        self.assertIn("never fetches mail itself", sources[0].note)

    def test_a_corrupt_partial_degrades_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "mail.json"
            p.write_text("{not json", encoding="utf-8")
            sources, threads = replydebt.read_source("gmail", Budget(), {"partial": str(p)})
        self.assertEqual(threads, [])
        self.assertIn("not valid JSON", sources[0].note)

    def test_a_future_schema_is_refused_by_name_rather_than_misread(self):
        doc = mailbox()
        doc["schema"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            sources, threads = replydebt.read_source(
                "gmail", Budget(), {"partial": write_partial(tmp, doc)})
        self.assertEqual(threads, [])
        self.assertIn("schema 99", sources[0].note)

    def test_the_demo_root_loads_a_fixture_mailbox_with_no_credential_of_any_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_partial(tmp, name=replydebt.DEMO_FILE)
            sources, threads = replydebt.read_source("gmail", Budget(), {"demo_root": tmp})
        self.assertTrue(sources[0].found)
        self.assertIn("(demo)", sources[0].name)
        self.assertEqual(len(threads), 14)

    def test_a_bare_list_of_threads_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, threads = replydebt.read_source(
                "gmail", Budget(), {"partial": write_partial(tmp, mailbox()["threads"])})
        self.assertTrue(sources[0].found)
        self.assertEqual(len(threads), 14)

    def test_direction_is_inferred_from_your_own_addresses_when_absent(self):
        _sources, threads = load()
        answered = [t for t in threads if t["thread_id"] == "t-answered"][0]
        self.assertEqual([m["direction"] for m in answered["messages"]], ["inbound", "outbound"])

    def test_messages_are_sorted_by_date_however_the_adapter_ordered_them(self):
        doc = mailbox()
        for t in doc["threads"]:
            t["messages"] = list(reversed(t["messages"]))
        with tempfile.TemporaryDirectory() as tmp:
            _sources, threads = replydebt.read_source(
                "gmail", Budget(), {"partial": write_partial(tmp, doc)})
        answered = [t for t in threads if t["thread_id"] == "t-answered"][0]
        self.assertEqual([m["direction"] for m in answered["messages"]], ["inbound", "outbound"])


# ---------------------------------------------------------------- quoted history

class TestQuotedHistoryIsRemovedBeforeAnythingIsMatched(unittest.TestCase):
    def test_a_question_that_only_exists_in_the_quote_is_not_an_ask(self):
        v = view_of()
        self.assertNotIn("t-quoted", ids(v["awaiting"]))
        row = [r for r in v["fyi_threads"] if r["thread_id"] == "t-quoted"][0]
        self.assertEqual(row["class"], replydebt.FYI)
        self.assertEqual(row["signals"], [])

    def test_every_quoting_convention_is_cut(self):
        cases = [
            "Fine by me.\n> Could you resend it?",
            "Fine by me.\n\nOn Tue, 1 Sep 2026, Dana Okoye <dana@example.com> wrote:\nCan you?",
            "Fine by me.\n-----Original Message-----\nFrom: Dana\nAny update?",
            "Fine by me.\n---------- Forwarded message ----------\nThoughts?",
            "Fine by me.\n" + "_" * 30 + "\nWould you mind?",
            "Fine by me.\nFrom: Dana Okoye\nSent: Monday\nCould you confirm?",
            "Fine by me.\n-- \nDana, who always asks: could you?",
        ]
        for raw in cases:
            self.assertEqual(replydebt.strip_quotes(raw), "Fine by me.", raw)
            self.assertEqual(replydebt.signals(replydebt.strip_quotes(raw)), [], raw)

    def test_an_ask_above_the_quote_still_counts(self):
        raw = "Could you confirm?\n\nOn Tue, Dana wrote:\n> earlier stuff"
        self.assertEqual(replydebt.strip_quotes(raw), "Could you confirm?")
        self.assertEqual(replydebt.classify(replydebt.signals(replydebt.strip_quotes(raw))),
                         replydebt.DIRECT)


# ---------------------------------------------------------------- the three classes

class TestTheThreeClasses(unittest.TestCase):
    def test_direct_asks_are_the_headline_number(self):
        v = view_of()
        self.assertEqual(v["direct"], 4)
        self.assertEqual(ids([r for r in v["awaiting"] if r["class"] == replydebt.DIRECT]),
                         ["t-dana-1", "t-dana-2", "t-dana-3", "t-dana-4"])
        self.assertTrue(v["headline"].startswith("4 threads awaiting your reply."))

    def test_an_fyi_with_an_implied_action_is_counted_but_kept_out_of_the_headline(self):
        v = view_of()
        self.assertEqual(v["implied"], 1)
        row = [r for r in v["awaiting"] if r["class"] == replydebt.IMPLIED][0]
        self.assertEqual(row["thread_id"], "t-implied")
        self.assertIn("deadline", row["signals"])
        self.assertNotIn("1 thread", v["headline"])
        self.assertIn("1 more carries an implied action", v["subhead"])

    def test_a_pure_fyi_is_not_debt(self):
        v = view_of()
        self.assertEqual(v["fyi"], 2)
        self.assertEqual(ids(v["fyi_threads"]), ["t-fyi", "t-quoted"])
        self.assertNotIn("t-fyi", ids(v["awaiting"]))

    def test_a_thread_you_already_answered_appears_nowhere(self):
        v = view_of()
        everywhere = ids(v["awaiting"]) + ids(v["fyi_threads"]) + ids(v["reciprocity"]["items"])
        self.assertNotIn("t-answered", everywhere)

    def test_a_thread_younger_than_the_minimum_age_is_counted_separately(self):
        v = view_of()
        self.assertEqual(v["too_recent"], 1)
        self.assertNotIn("t-recent", ids(v["awaiting"]))
        self.assertIn("t-recent", ids(replydebt.analyse(load()[1], NOW, {"min_age_days": 0})
                                      ["awaiting"]))

    def test_every_signal_the_rule_names_actually_fires(self):
        for text, name in (("Where is it?", "question"), ("could you take a look", "modal"),
                           ("circling back", "request"), ("before the call", "deadline"),
                           ("for your review", "implied")):
            self.assertIn(name, replydebt.signals(text), text)


# ---------------------------------------------------------------- clustering, age, cold

class TestSenderClustering(unittest.TestCase):
    def test_four_threads_from_one_person_are_one_relationship(self):
        v = view_of()
        top = v["top_sender"]
        self.assertEqual(top["person_key"], "dana@example.com")
        self.assertEqual(top["threads"], 4)
        self.assertEqual(top["direct"], 4)
        self.assertEqual(top["oldest_days"], 94)
        self.assertEqual(top["thread_ids"], ["t-dana-1", "t-dana-2", "t-dana-3", "t-dana-4"])

    def test_the_headline_says_so_in_words(self):
        self.assertEqual(
            view_of()["headline"],
            "4 threads awaiting your reply. Oldest 94 days. Four from the same person.")

    def test_a_single_thread_sender_is_not_called_out_as_a_cluster(self):
        v = view_of()
        self.assertEqual([s["person_key"] for s in v["repeat_senders"]], ["dana@example.com"])
        self.assertIn("priya@example.com", [s["person_key"] for s in v["senders"]])


class TestAgeAndCold(unittest.TestCase):
    def test_the_ranking_is_oldest_first(self):
        v = view_of()
        self.assertEqual([r["age_days"] for r in v["awaiting"]], [94, 40, 20, 10, 6])
        self.assertEqual(v["oldest"]["thread_id"], "t-dana-1")

    def test_the_age_buckets_account_for_every_debt_thread(self):
        v = view_of()
        self.assertEqual(sum(b["threads"] for b in v["buckets"]), v["debt"])
        self.assertEqual([b["threads"] for b in v["buckets"]], [1, 1, 1, 1, 1])

    def test_the_cold_tier_is_everything_past_the_configured_threshold(self):
        v = view_of()
        self.assertEqual(v["cold_days"], 30)
        self.assertEqual(ids(v["cold_threads"]), ["t-dana-1", "t-dana-2"])
        self.assertEqual(v["cold"], 2)
        self.assertEqual(view_of(cold_days=15)["cold"], 3)


# ---------------------------------------------------------------- reciprocity

class TestReciprocity(unittest.TestCase):
    """Without this the Play is purely an instrument of guilt, so it is a hard requirement."""

    def test_threads_where_you_asked_and_nobody_answered_are_counted(self):
        rec = view_of()["reciprocity"]
        self.assertEqual(rec["threads"], 1)
        self.assertEqual(rec["items"][0]["thread_id"], "t-owed")
        self.assertEqual(rec["oldest_days"], 41)
        self.assertEqual(rec["items"][0]["person_key"], "marcus@example.com")

    def test_it_names_the_person_who_owes_you_not_yourself(self):
        rec = view_of()["reciprocity"]
        self.assertNotIn("Y.", rec["items"][0]["person"])
        self.assertEqual(rec["items"][0]["person"], "M. H.")

    def test_an_outbound_message_that_asks_nothing_is_not_a_debt_owed_to_you(self):
        self.assertNotIn("t-answered", ids(view_of()["reciprocity"]["items"]))

    def test_the_card_and_the_report_both_show_the_other_side(self):
        v = view_of()
        self.assertIn("THE OTHER SIDE OF THE LEDGER", replydebt.render(v, {}))
        self.assertIn("you asked and got nothing back", replydebt.render(v, {}))
        self.assertIn("## The other side of the ledger", replydebt.report_markdown(v, {}, []))


# ---------------------------------------------------------------- exclusions

class TestExclusionsAreCountedOutLoud(unittest.TestCase):
    def test_every_exclusion_heuristic_fires(self):
        v = view_of()
        self.assertEqual(dict((e["reason"], e["threads"]) for e in v["exclusions"]),
                         {"mailing list": 1, "calendar invite": 1, "no-reply sender": 1,
                          "automated notification": 1})

    def test_the_excluded_count_is_printed_so_the_denominator_is_honest(self):
        v = view_of()
        self.assertEqual(v["excluded"], 4)
        self.assertEqual(v["threads_seen"], 14)
        self.assertEqual(v["considered"], 10)
        self.assertIn("4 excluded from the denominator", replydebt.render(v, {}))
        md = replydebt.report_markdown(v, {}, [])
        self.assertIn("## What was excluded, and why", md)
        self.assertIn("4 of 14 thread(s) were left out", md)

    def test_an_excluded_thread_never_reaches_the_debt_list(self):
        v = view_of()
        for tid in ("t-newsletter", "t-noreply", "t-calendar", "t-automated"):
            self.assertNotIn(tid, ids(v["awaiting"]) + ids(v["fyi_threads"]))

    def test_a_list_id_alone_is_enough_to_exclude(self):
        thread = {"thread_id": "x", "messages": [
            {"from": SAM, "date": "2026-08-01T12:00:00Z", "direction": "inbound",
             "snippet": "Could you?", "list_id": "announce.example"}]}
        self.assertEqual(replydebt.exclusion(replydebt.normalise(thread)), "mailing list")

    def test_a_calendar_invite_from_a_real_person_is_still_a_calendar_invite(self):
        thread = {"thread_id": "x", "subject": "Invitation: Retro", "messages": [
            {"from": PRIYA, "date": "2026-08-01T12:00:00Z", "direction": "inbound",
             "snippet": "Can you make it?", "subject": "Invitation: Retro"}]}
        self.assertEqual(replydebt.exclusion(replydebt.normalise(thread)), "calendar invite")


# ---------------------------------------------------------------- the printed rule

class TestTheRuleIsPrintedSoItCanBeArguedWith(unittest.TestCase):
    def test_the_report_prints_every_phrase_the_module_matches_on(self):
        md = replydebt.report_markdown(view_of(), {}, [])
        self.assertIn("How reply-debt decides something is an ask", md)
        for phrase in ("could you", "would you mind", "any update", "circling back",
                       "thoughts?", "for your review", "end of day"):
            self.assertIn(phrase, md, phrase)
        for pattern in replydebt.DEADLINES:
            self.assertIn(pattern, md, pattern)

    def test_the_rule_says_that_quoted_history_is_stripped_first(self):
        md = replydebt.report_markdown(view_of(), {}, [])
        self.assertIn("Quoted history is removed before anything is matched", md)
        self.assertIn("wrote:", md)

    def test_the_rule_names_all_three_classes_and_which_of_them_are_debt(self):
        r = replydebt.rule()
        self.assertEqual([k["name"] for k in r["classes"]], list(replydebt.CLASSES))
        self.assertEqual([k["counts_as_debt"] for k in r["classes"]], [True, True, False])
        md = replydebt.report_markdown(view_of(), {}, [])
        for name in replydebt.CLASSES:
            self.assertIn(name, md)


# ---------------------------------------------------------------- redaction

class TestRedaction(unittest.TestCase):
    def test_subjects_are_hashed_and_names_reduced_to_initials_by_default(self):
        v = view_of()
        self.assertTrue(v["redacted"])
        row = v["awaiting"][0]
        self.assertEqual(row["person"], "D. O.")
        self.assertTrue(row["subject"].startswith("#"))
        self.assertEqual(row["subject"], row["subject_hash"])
        self.assertNotIn("Contract redlines", json.dumps(v))

    def test_a_hash_is_stable_and_distinguishes_two_subjects(self):
        self.assertEqual(view_of()["awaiting"][0]["subject_hash"],
                         view_of()["awaiting"][0]["subject_hash"])
        hashes = [r["subject_hash"] for r in view_of()["awaiting"]]
        self.assertEqual(len(set(hashes)), len(hashes))

    def test_turning_redaction_off_keeps_subjects_locally_but_never_on_the_card(self):
        v = view_of(redact=False)
        self.assertFalse(v["redacted"])
        self.assertEqual(v["awaiting"][0]["subject"], "Contract redlines")
        self.assertEqual(v["awaiting"][0]["person"], "Dana Okoye")
        self.assertIn("Contract redlines", replydebt.report_markdown(v, {}, []))
        card = replydebt.render(v, {})
        for subject in ("Contract redlines", "Statement of work", "Invoice 4417", "Deck v4"):
            self.assertNotIn(subject, card, "a subject must never reach the card")
        self.assertIn(v["awaiting"][0]["subject_hash"], card)

    def test_the_card_carries_no_email_address_in_either_mode(self):
        for redact in (True, False):
            self.assertNotIn("@", replydebt.render(view_of(redact=redact), {}))


# ---------------------------------------------------------------- delta

class TestDeltaAgainstTheBaseline(unittest.TestCase):
    def test_the_first_run_says_so_rather_than_inventing_a_delta(self):
        d = view_of()["delta"]
        self.assertTrue(d["first_run"])
        self.assertEqual((d["new"], d["cleared"]), (0, 0))
        self.assertIn("first run", d["since"])

    def test_a_second_run_reports_what_arrived_and_what_cleared(self):
        with tempfile.TemporaryDirectory() as out:
            _sources, threads = load()
            first = replydebt.analyse(threads, NOW, {"out_dir": out})
            replydebt.write_baseline(first, {"out_dir": out, "now": NOW})
            self.assertTrue(baseline_read(out, replydebt.NAME))

            later = [t for t in threads if t["thread_id"] != "t-dana-3"]
            later.append(replydebt.normalise(
                {"thread_id": "t-new", "subject": "New ask", "messages": [
                    {"from": SAM, "date": "2026-08-01T12:00:00Z", "direction": "inbound",
                     "snippet": "Could you sign this?", "subject": "New ask"}]}))
            second = replydebt.analyse(later, NOW, {"out_dir": out})

        self.assertFalse(second["delta"]["first_run"])
        self.assertEqual(second["delta"]["new"], 1)
        self.assertEqual(second["delta"]["cleared"], 1)
        self.assertIn("since 2026-09-05", second["delta"]["since"])
        self.assertIn("1 new since 2026-09-05, 1 cleared.", replydebt.render(second, {}))

    def test_the_baseline_payload_is_keyed_by_thread_so_reordering_moves_nothing(self):
        v = view_of()
        self.assertEqual(sorted(v["baseline_payload"]), ids(v["awaiting"]))


# ---------------------------------------------------------------- rendering and determinism

class TestRendering(unittest.TestCase):
    def test_the_card_is_exactly_64_columns(self):
        from daily_core.common import display_width
        for line in replydebt.render(view_of(), {}).split("\n"):
            self.assertEqual(display_width(line), 64, line)

    def test_the_headline_survives_the_card_width_intact(self):
        """It wraps rather than losing "Four from the same person." to an ellipsis."""
        card = replydebt.render(view_of(), {})
        flat = " ".join(card.replace("│", " ").split())
        self.assertIn(view_of()["headline"], flat)

    def test_a_coloured_card_is_still_padded_to_64_columns(self):
        import re as _re
        for line in replydebt.render(view_of(), {"color": True}).split("\n"):
            self.assertEqual(len(_re.sub(r"\x1b\[[0-9;]*m", "", line)), 64, line)

    def test_an_empty_mailbox_still_renders_a_card_and_a_report(self):
        v = replydebt.analyse([], NOW, {})
        self.assertEqual(v["debt"], 0)
        self.assertIn("0 threads awaiting your reply.", v["headline"])
        self.assertIn("Nobody owes you a reply", replydebt.render(v, {}))
        self.assertIn("nothing awaiting a reply", replydebt.report_markdown(v, {}, []))

    def test_the_report_carries_the_counts_the_card_claims(self):
        v = view_of()
        md = replydebt.report_markdown(v, {}, [{"name": "gmail", "found": True, "note": "n"}])
        self.assertIn("| awaiting your reply | 5 |", md)
        self.assertIn("| direct ask | 4 |", md)
        self.assertIn("| gone cold (30+ days) | 2 (40%) |", md)
        self.assertIn("| gmail | yes | n |", md)


class TestDeterminism(unittest.TestCase):
    def test_the_same_mailbox_and_the_same_clock_give_an_identical_answer(self):
        a, b = view_of(), view_of()
        self.assertEqual(json.dumps(a, sort_keys=True, default=str),
                         json.dumps(b, sort_keys=True, default=str))
        self.assertEqual(replydebt.render(a, {}), replydebt.render(b, {}))
        self.assertEqual(replydebt.report_markdown(a, {}, []), replydebt.report_markdown(b, {}, []))

    def test_shuffling_the_threads_does_not_change_the_answer(self):
        _sources, threads = load()
        straight = replydebt.analyse(threads, NOW, {})
        shuffled = replydebt.analyse(list(reversed(threads)), NOW, {})
        self.assertEqual(json.dumps(straight, sort_keys=True, default=str),
                         json.dumps(shuffled, sort_keys=True, default=str))


if __name__ == "__main__":
    unittest.main()
