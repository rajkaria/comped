"""standing-cost: the arithmetic, the refusals, and the promise that this half never fetches.

The Play is split across two programs on purpose — the TypeScript step calls Google Calendar and
writes a JSON partial, the Python module computes from that file and nothing else — so these tests
write the partial themselves. Every number below is asserted with its denominator, because a
person-hour total whose denominator nobody checked is the same kind of made-up number this Play
exists to expose.
"""
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daily_core.common import Budget
from daily_core.scan import standingcost as sc

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
SOURCE = Path(sc.__file__).read_text(encoding="utf-8")

ALICE = "alice@example.com"
BOB = "bob@example.com"
CARA = "cara@example.com"
DAN = "dan@example.com"
ERIN = "erin@example.com"


# ---------------------------------------------------------------- fixture builders

def att(email, response="accepted", **extra):
    row = {"email": email, "response_status": response,
           "display_name": email.split("@")[0].capitalize() + " Example"}
    row.update(extra)
    return row


def event(eid, series, summary, start, minutes, attendees, status="confirmed", **extra):
    end = start + timedelta(minutes=minutes)
    doc = {"id": eid, "recurring_event_id": series, "summary": summary,
           "start": start.isoformat(), "end": end.isoformat(), "status": status,
           "organizer": ALICE, "attendees": attendees}
    doc.update(extra)
    return doc


def weekly(series, summary, count, minutes, attendees, first=None, hour=9, cancel_every=0,
           status="confirmed"):
    """`count` weekly occurrences ending before NOW, oldest first."""
    start = first or (NOW - timedelta(days=7 * count)).replace(hour=hour, minute=0, second=0,
                                                               microsecond=0)
    out = []
    for i in range(count):
        when = start + timedelta(days=7 * i)
        cancelled = bool(cancel_every) and (i % cancel_every == cancel_every - 1)
        out.append(event("{0}-{1:03d}".format(series, i), series, summary, when, minutes,
                         attendees, "cancelled" if cancelled else status))
    return out


def partial(events, **envelope):
    doc = {"schema": 1, "source": "google-calendar", "account": "work",
           "fetched": sc.iso(NOW), "timezone": "Europe/London", "events": events}
    doc.update(envelope)
    return doc


def write_partial(tmp, events, name=sc.PARTIAL, **envelope):
    path = Path(tmp) / name
    path.write_text(json.dumps(partial(events, **envelope)), encoding="utf-8")
    return path


def load(tmp, cfg=None):
    conf = {"out_dir": str(tmp), "partial": sc.PARTIAL}
    conf.update(cfg or {})
    sources, events = sc.read_source("calendar", Budget(), conf)
    return sources, events, conf


def analysed(tmp, events, **cfg):
    write_partial(tmp, events)
    sources, loaded, conf = load(tmp, cfg)
    return sc.analyse(loaded, NOW, conf), sources, conf


# The clean case: ten weekly occurrences, four people who accepted, one who declined, one who
# never answered. Every later test bends one variable away from this baseline.
CLEAN = weekly("standup", "Monday Standup", 10, 30,
               [att(ALICE, self=True, timezone="Europe/London", utc_offset_minutes=60),
                att(BOB), att(CARA), att(DAN, "tentative"),
                att(ERIN, "declined"), att("frank@example.com", "needsAction")])


class TestPersonHourArithmetic(unittest.TestCase):
    def test_the_headline_is_attendees_times_duration_times_occurrences(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, CLEAN)
            self.assertEqual(v["occurrences"], 10)
            series = v["series"][0]
            self.assertEqual(series["attendees"], 4)          # 3 accepted + 1 tentative
            self.assertEqual(series["minutes"], 30)
            self.assertEqual(series["occurrences"], 10)
            # 4 people x 0.5 h x 10 occurrences
            self.assertEqual(series["person_hours"], 20.0)
            self.assertEqual(v["person_hours"], 20.0)
            self.assertEqual(v["attendee_occurrences"], 40)
            self.assertEqual(v["meeting_hours"], 5.0)         # wall clock, one row per occurrence
            self.assertIn("4 attendees x 30 min x 10 occurrences = 20 person-hours",
                          v["headline"])

    def test_declined_and_unanswered_are_counted_and_kept_out_of_the_headline(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, CLEAN)
            self.assertEqual(v["declined_person_hours"], 5.0)        # 1 x 0.5 x 10
            self.assertEqual(v["no_response_person_hours"], 5.0)     # 1 x 0.5 x 10
            self.assertEqual(v["tentative_person_hours"], 5.0)       # billed, but separable
            self.assertEqual(v["person_hours"], 20.0)
            self.assertNotEqual(v["person_hours"], 30.0)             # the six-attendee fiction

    def test_a_second_series_is_ranked_below_the_expensive_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            small = weekly("11", "Design sync", 4, 60, [att(ALICE, self=True), att(BOB)])
            v, _, _ = analysed(tmp, CLEAN + small)
            self.assertEqual([s["name"] for s in v["series"]], ["Monday Standup", "Design sync"])
            self.assertEqual(v["series"][1]["person_hours"], 8.0)    # 2 x 1 h x 4
            self.assertEqual(v["series_total"], 2)
            self.assertAlmostEqual(sum(s["share"] for s in v["series"]), 1.0, places=6)

    def test_events_outside_the_window_are_excluded_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = weekly("ancient", "Old ritual", 2, 60, [att(ALICE), att(BOB)],
                         first=NOW - timedelta(days=800))
            v, _, _ = analysed(tmp, CLEAN + old, days=365)
            self.assertEqual(v["events_outside_window"], 2)
            self.assertEqual(v["occurrences"], 10)
            self.assertEqual(v["series_total"], 1)

    def test_an_event_with_no_usable_end_is_labelled_not_dropped_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = dict(CLEAN[0])
            broken["id"], broken["end"] = "broken-1", ""
            v, _, _ = analysed(tmp, CLEAN + [broken])
            self.assertEqual(v["events_unusable"], 1)
            self.assertEqual(v["unusable_reasons"], [{"reason": "no usable end time", "events": 1}])
            self.assertEqual(v["person_hours"], 20.0)

    def test_a_recurring_block_with_no_invitees_still_costs_its_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            solo = weekly("solo", "Deep work", 4, 120, [])
            v, _, _ = analysed(tmp, solo)
            self.assertEqual(v["person_hours"], 8.0)      # 1 implied attendee x 2 h x 4
            self.assertEqual(v["implied_attendees"], 4)


class TestTheRateIsNeverInvented(unittest.TestCase):
    def test_with_no_rate_there_is_no_money_anywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, CLEAN)
            self.assertFalse(v["rate"]["set"])
            self.assertIsNone(v["rate"]["hourly_rate"])
            self.assertFalse(v["cost"]["known"])
            self.assertIsNone(v["cost"]["amount"])
            self.assertEqual(v["cost"]["text"], "")
            self.assertIn("no hourly rate was given", v["cost"]["basis"])
            self.assertIsNone(v["series"][0]["cost"])
            self.assertIsNone(v["people"][0]["cost"])
            card = sc.render(v, cfg)
            report = sc.report_markdown(v, cfg, sources)
            for surface, name in ((card, "card"), (report, "report")):
                self.assertNotIn("£", surface, name)
                self.assertNotIn("$", surface, name)
            self.assertIn("unset", card)
            self.assertIn("person-hours", card)

    def test_a_blank_or_zero_or_nonsense_rate_is_the_same_as_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("", "   ", 0, -50, "free", None):
                v, _, _ = analysed(tmp, CLEAN, hourly_rate=value)
                self.assertFalse(v["rate"]["set"], value)
                self.assertFalse(v["cost"]["known"], value)

    def test_with_a_rate_the_money_is_right_and_every_line_that_prints_it_says_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, CLEAN, hourly_rate="75")
            self.assertTrue(v["rate"]["set"])
            self.assertEqual(v["cost"]["amount"], 1500.0)            # 20 person-hours x £75
            self.assertEqual(v["series"][0]["cost"], 1500.0)
            self.assertIn("assumed", v["rate"]["label"])
            self.assertIn("assumed", v["cost"]["basis"])
            self.assertIn("assumed", v["cost"]["text"])
            card = sc.render(v, cfg)
            report = sc.report_markdown(v, cfg, sources)
            self.assertIn("£1,500", card)
            self.assertIn("£1,500", report)
            for surface, name in ((card, "card"), (report, "report")):
                money_lines = [ln for ln in surface.splitlines() if "£" in ln]
                self.assertTrue(money_lines, name)
                for line in money_lines:
                    self.assertIn("assum", line,
                                  "{0} prints money without labelling it: {1!r}".format(name, line))

    def test_the_currency_is_a_parameter_not_a_hardcoded_pound(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, CLEAN, hourly_rate=100, currency="$")
            self.assertEqual(v["cost"]["amount"], 2000.0)
            card = sc.render(v, cfg)
            self.assertIn("$2,000", card)
            self.assertNotIn("£", card)
            for line in [ln for ln in card.splitlines() if "$" in ln]:
                self.assertIn("assum", line, line)


class TestCancellationCredit(unittest.TestCase):
    """Nine scheduled, every third cancelled: three cancellations, six that actually happened."""

    def _series(self):
        return weekly("standup", "Monday Standup", 9, 30,
                      [att(ALICE, self=True), att(BOB), att(CARA), att(DAN)], cancel_every=3)

    def test_only_the_occurrences_that_happened_are_billed(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, self._series())
            self.assertEqual(v["scheduled_occurrences"], 9)
            self.assertEqual(v["cancelled_occurrences"], 3)
            self.assertEqual(v["occurrences"], 6)
            self.assertEqual(v["person_hours"], 12.0)          # 4 x 0.5 x 6, not x 9
            self.assertEqual(v["cancellation"]["credit_person_hours"], 6.0)   # 4 x 0.5 x 3
            self.assertEqual(v["cancellation"]["share"], 33)
            self.assertEqual(v["series"][0]["cancelled"], 3)
            self.assertEqual(v["series"][0]["scheduled"], 9)

    def test_the_credit_is_stated_on_both_surfaces_and_priced_when_a_rate_is_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, self._series(), hourly_rate=50)
            self.assertEqual(v["cost"]["amount"], 600.0)                    # 12 h x £50
            card, report = sc.render(v, cfg), sc.report_markdown(v, cfg, sources)
            self.assertIn("credited back", card)
            self.assertIn("£300", card)                                     # 6 h credited x £50
            self.assertIn("3 of 9", report)
            self.assertIn("crediting back", report)


class TestSilentAttendees(unittest.TestCase):
    def test_invited_to_every_occurrence_and_never_accepting_is_the_could_be_an_email_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 6, 30,
                            [att(ALICE, self=True), att(BOB),
                             att(CARA, "needsAction"), att(ERIN, "declined")])
            v, _, _ = analysed(tmp, events)
            reasons = {row["person"]: row["reason"] for row in v["silent"]}
            self.assertEqual(sorted(reasons), ["C. E.", "E. E."])
            self.assertEqual(reasons["C. E."], "never accepted")
            self.assertEqual(reasons["E. E."], "never accepted")
            self.assertEqual(v["silent"][0]["invited"], 6)
            self.assertEqual(v["silent_person_hours"], 0.0)   # neither was billed

    def test_someone_added_halfway_through_is_not_accused_of_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 6, 30, [att(ALICE, self=True), att(BOB)])
            for e in events[3:]:
                e["attendees"] = e["attendees"] + [att(CARA, "needsAction")]
            v, _, _ = analysed(tmp, events)
            self.assertEqual(v["silent"], [])

    def test_accepting_every_time_and_never_turning_up_is_billed_and_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 5, 60,
                            [att(ALICE, self=True, attended=True), att(BOB, attended=False)])
            for e in events:
                e["attendance_recorded"] = True
            v, sources, cfg = analysed(tmp, events)
            ghost = [r for r in v["silent"] if r["reason"].endswith("never present")]
            self.assertEqual(len(ghost), 1)
            self.assertEqual(ghost[0]["person"], "B. E.")
            self.assertEqual(ghost[0]["hours"], 5.0)          # 1 h x 5, and it was billed
            self.assertTrue(ghost[0]["billed"])
            self.assertEqual(v["silent_person_hours"], 5.0)
            self.assertIn("COULD HAVE BEEN AN EMAIL", sc.render(v, cfg))
            self.assertIn("never present", sc.report_markdown(v, cfg, sources))

    def test_attendance_that_was_never_recorded_makes_no_accusation(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 5, 60,
                            [att(ALICE, self=True), att(BOB)])
            v, _, _ = analysed(tmp, events)
            self.assertEqual(v["silent"], [])


class TestSeriesDrift(unittest.TestCase):
    def test_a_series_that_grew_in_length_and_headcount_is_reported_with_both_halves(self):
        with tempfile.TemporaryDirectory() as tmp:
            small = [att(ALICE, self=True), att(BOB)]
            big = small + [att(CARA), att(DAN)]
            events = weekly("grow", "Weekly review", 4, 30, small,
                            first=NOW - timedelta(days=56))
            events += weekly("grow", "Weekly review", 4, 60, big,
                             first=NOW - timedelta(days=28))
            for i, e in enumerate(events):
                e["id"] = "grow-{0:03d}".format(i)
            v, sources, cfg = analysed(tmp, events)
            drift = v["series"][0]["drift"]
            self.assertIsNotNone(drift)
            self.assertEqual(drift["minutes_before"], 30.0)
            self.assertEqual(drift["minutes_after"], 60.0)
            self.assertEqual(drift["attendees_before"], 2.0)
            self.assertEqual(drift["attendees_after"], 4.0)
            self.assertEqual(drift["halves"], [4, 4])
            self.assertEqual(len(v["drift"]), 1)
            self.assertIn("SERIES THAT GREW", sc.render(v, cfg))
            self.assertIn("Series that grew", sc.report_markdown(v, cfg, sources))

    def test_a_steady_series_reports_no_drift_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, CLEAN)
            self.assertIsNone(v["series"][0]["drift"])
            self.assertEqual(v["drift"], [])


class TestFragmentationCost(unittest.TestCase):
    """One day, four meetings, gaps of 30, 120 and 45 minutes: two of them destroy focus."""

    def _day(self):
        base = NOW.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=3)
        people = [att(ALICE, self=True), att(BOB)]
        return [
            event("f1", "", "Standup", base, 30, people),                        # 09:00–09:30
            event("f2", "", "Review", base + timedelta(minutes=60), 30, people),   # 10:00, gap 30
            event("f3", "", "Planning", base + timedelta(minutes=210), 60, people),  # 12:30, gap 120
            event("f4", "", "1:1", base + timedelta(minutes=315), 30, people),     # 14:15, gap 45
        ]

    def test_only_gaps_shorter_than_the_focus_block_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, self._day())
            f = v["fragmentation"]
            self.assertEqual(f["focus_block_minutes"], 90)
            self.assertEqual(f["minutes"], 75)            # 30 + 45; the 120 gap is usable time
            self.assertEqual(f["gaps"], 2)
            self.assertEqual(f["days_fragmented"], 1)
            self.assertEqual(f["worst"]["minutes"], 75)
            self.assertEqual(f["worst"]["meetings"], 4)

    def test_the_focus_block_is_a_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, self._day(), focus_block_minutes=150)
            self.assertEqual(v["fragmentation"]["minutes"], 195)   # 30 + 120 + 45
            self.assertEqual(v["fragmentation"]["gaps"], 3)
            v, _, _ = analysed(tmp, self._day(), focus_block_minutes=40)
            self.assertEqual(v["fragmentation"]["minutes"], 30)
            self.assertEqual(v["fragmentation"]["gaps"], 1)

    def test_destroyed_focus_is_reported_separately_from_meeting_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, self._day())
            self.assertEqual(v["meeting_hours"], 2.5)              # 30 + 30 + 60 + 30 minutes
            self.assertEqual(v["fragmentation"]["hours"], 1.25)
            self.assertNotEqual(v["fragmentation"]["hours"], v["meeting_hours"])
            card = sc.render(v, cfg)
            self.assertIn("FOCUS TIME DESTROYED", card)
            self.assertIn("counted separately", card)
            self.assertIn("counted separately", sc.report_markdown(v, cfg, sources))

    def test_a_day_with_one_meeting_fragments_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, _ = analysed(tmp, self._day()[:1])
            self.assertEqual(v["fragmentation"]["minutes"], 0)
            self.assertEqual(v["fragmentation"]["days_fragmented"], 0)


class TestAttendeeSideView(unittest.TestCase):
    def test_each_person_gets_their_hours_and_their_share_of_the_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 4, 60,
                            [att(ALICE, self=True), att(BOB), att(CARA, "declined")])
            events += weekly("sync", "Design sync", 4, 30, [att(ALICE, self=True), att(DAN)],
                             hour=14)
            v, _, _ = analysed(tmp, events)
            by_person = {p["person"]: p for p in v["people"]}
            self.assertEqual(v["person_hours"], 12.0)        # 2x1x4 + 2x0.5x4
            self.assertEqual(by_person["A. E."]["hours"], 6.0)
            self.assertEqual(by_person["A. E."]["series"], 2)
            self.assertEqual(by_person["A. E."]["meetings"], 8)
            self.assertEqual(by_person["B. E."]["hours"], 4.0)
            self.assertEqual(by_person["D. E."]["hours"], 2.0)
            self.assertEqual(by_person["C. E."]["hours"], 0.0)
            self.assertEqual(by_person["C. E."]["declined"], 4)
            self.assertAlmostEqual(by_person["A. E."]["share"], 0.5, places=6)
            self.assertAlmostEqual(sum(p["share"] for p in v["people"]), 1.0, places=6)
            self.assertEqual([p["person"] for p in v["people"]][0], "A. E.")

    def test_an_attendee_keeps_their_own_timezone_where_the_event_carries_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 16:00 UTC is 17:00 in London and 01:00 the next day in Tokyo.
            base = NOW.replace(hour=16, minute=0, second=0, microsecond=0) - timedelta(days=2)
            people = [att(ALICE, self=True, timezone="Europe/London", utc_offset_minutes=60),
                      att(BOB, timezone="Asia/Tokyo", utc_offset_minutes=540),
                      att(CARA)]
            v, sources, cfg = analysed(tmp, [event("tz1", "tz", "Handover", base, 60, people)])
            by_person = {p["person"]: p for p in v["people"]}
            self.assertEqual(by_person["A. E."]["zone"], "Europe/London")
            self.assertEqual(by_person["A. E."]["out_of_hours"], 0)      # 17:00 local
            self.assertEqual(by_person["B. E."]["zone"], "Asia/Tokyo")
            self.assertEqual(by_person["B. E."]["out_of_hours"], 1)      # 01:00 local
            self.assertFalse(by_person["C. E."]["zone_known"])
            self.assertEqual(v["zones"]["known"], 2)
            self.assertEqual(v["zones"]["unknown"], 1)
            self.assertIn("carried no zone", v["zones"]["note"])
            self.assertIn("Asia/Tokyo", sc.report_markdown(v, cfg, sources))


class TestRankingsAndProjection(unittest.TestCase):
    def test_the_second_ranking_covers_only_the_series_with_no_agenda_or_notes_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            documented = weekly("doc", "Documented sync", 8, 60,
                                [att(ALICE, self=True), att(BOB), att(CARA), att(DAN)])
            for e in documented:
                e["agenda_link"] = "https://notes.example.com/doc"
            blind = weekly("blind", "Status update", 6, 30,
                           [att(ALICE, self=True), att(BOB), att(CARA)], hour=15)
            v, sources, cfg = analysed(tmp, documented + blind)
            self.assertEqual(v["series"][0]["name"], "Documented sync")     # ranked by cost
            self.assertEqual([r["name"] for r in v["ranking_decision"]], ["Status update"])
            self.assertEqual(v["ranking_decision"][0]["attendee_occurrences"], 18)  # 3 x 6
            self.assertEqual(v["ranking_decision"][0]["share"], 1.0)
            self.assertEqual(v["series_without_agenda"], 1)
            self.assertIn("no decision was written down", sc.report_markdown(v, cfg, sources))

    def test_the_annual_figure_is_labelled_a_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 10, 60,
                            [att(ALICE, self=True), att(BOB)])
            v, sources, cfg = analysed(tmp, events)
            self.assertEqual(v["person_hours"], 20.0)
            self.assertEqual(v["days_covered"], 71)                 # ten weeks of history
            self.assertAlmostEqual(v["projection"]["person_hours"], round(20.0 * 365 / 71, 1),
                                   places=1)
            self.assertIn("projection", v["projection"]["label"])
            self.assertIn("PROJECTION", sc.render(v, cfg))
            self.assertIn("projection, not a measurement",
                          sc.report_markdown(v, cfg, sources))


class TestRedaction(unittest.TestCase):
    def test_no_address_reaches_the_card_the_report_or_the_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, CLEAN, hourly_rate=90)
            blob = json.dumps(v, default=str)
            card, report = sc.render(v, cfg), sc.report_markdown(v, cfg, sources)
            for email in (ALICE, BOB, CARA, DAN, ERIN):
                self.assertNotIn(email, card)
                self.assertNotIn(email, report)
                self.assertNotIn(email, blob)
            self.assertNotIn("@example.com", card)
            self.assertNotIn("@example.com", report)
            self.assertTrue(v["redacted"])
            self.assertIn("A. E.", card)

    def test_turning_redaction_off_shows_names_but_still_never_a_whole_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, sources, cfg = analysed(tmp, CLEAN, redact=False)
            card, report = sc.render(v, cfg), sc.report_markdown(v, cfg, sources)
            self.assertIn("Alice Example", card)
            for email in (ALICE, BOB, CARA, DAN, ERIN):
                self.assertNotIn(email, card)
                self.assertNotIn(email, report)
            self.assertIn("alice@…", report)
            self.assertFalse(v["redacted"])

    def test_a_name_the_calendar_never_carried_falls_back_to_the_address_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = weekly("standup", "Monday Standup", 3, 30,
                            [{"email": "priya.nair@example.com", "response_status": "accepted",
                              "self": True}])
            v, _, _ = analysed(tmp, events)
            self.assertEqual(v["people"][0]["person"], "P. N.")


class TestDeltaAgainstTheBaseline(unittest.TestCase):
    def test_a_first_run_says_so_and_a_second_reports_what_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, cfg = analysed(tmp, CLEAN)
            self.assertTrue(v["delta"]["first_run"])
            self.assertIn("first run", v["since"])
            sc.save_baseline(v, cfg, NOW)

            grown = CLEAN + weekly("standup", "Monday Standup", 2, 30,
                                   [att(ALICE, self=True), att(BOB), att(CARA), att(DAN)],
                                   first=NOW - timedelta(days=10))
            for i, e in enumerate(grown):
                e["id"] = "standup-{0:03d}".format(i)
            v2, sources, cfg2 = analysed(tmp, grown)
            self.assertFalse(v2["delta"]["first_run"])
            self.assertEqual(v2["delta"]["grew"], {"series::standup": 4.0})
            self.assertEqual(v2["delta"]["net"], 4.0)
            self.assertIn("since", v2["since"])
            self.assertIn("Since the last run", sc.report_markdown(v2, cfg2, sources))

    def test_analysing_twice_reports_the_same_delta(self):
        """Reading the baseline in `analyse` and writing it in `save_baseline` are separate."""
        with tempfile.TemporaryDirectory() as tmp:
            v1, _, cfg = analysed(tmp, CLEAN)
            sc.save_baseline(v1, cfg, NOW)
            a = sc.analyse(load(tmp)[1], NOW, cfg)
            b = sc.analyse(load(tmp)[1], NOW, cfg)
            self.assertEqual(a["delta"], b["delta"])
            self.assertEqual(a["delta"]["net"], 0.0)


class TestDegradation(unittest.TestCase):
    def test_a_missing_partial_is_a_labelled_miss_that_explains_the_calendar_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            self.assertEqual(events, [])
            self.assertEqual(len(sources), 1)
            self.assertFalse(sources[0].found)
            self.assertIn("calendar step has not run", sources[0].note)
            self.assertIn("this one only reads the file", sources[0].note)

    def test_a_missing_partial_still_analyses_renders_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"out_dir": tmp, "partial": sc.PARTIAL}
            sources, events = sc.read_source("calendar", Budget(), cfg)
            v = sc.analyse(events, NOW, cfg)
            self.assertEqual(v["person_hours"], 0.0)
            self.assertEqual(v["series"], [])
            self.assertEqual(v["occurrences"], 0)
            self.assertIn("STANDING COST", sc.render(v, cfg))
            self.assertIn("Standing cost", sc.report_markdown(v, cfg, sources))

    def test_a_truncated_or_invalid_partial_is_a_miss_not_an_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sc.PARTIAL).write_text('{"events": [{"id": "a",', encoding="utf-8")
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            self.assertEqual(events, [])
            self.assertFalse(sources[0].found)
            self.assertIn("not valid JSON", sources[0].note)

    def test_a_newer_schema_is_refused_in_words_rather_than_misread(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_partial(tmp, CLEAN, schema=99)
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            self.assertEqual(events, [])
            self.assertIn("schema 99", sources[0].note)

    def test_an_empty_calendar_is_read_successfully_and_says_it_found_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_partial(tmp, [])
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            self.assertEqual(events, [])
            self.assertTrue(sources[0].found)
            self.assertIn("no events in the window", sources[0].note)

    def test_a_truncated_fetch_is_reported_as_a_lower_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_partial(tmp, CLEAN, truncated=True)
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            self.assertEqual(len(events), 10)
            self.assertIn("lower bound", sources[0].note)

    def test_the_demo_root_reads_a_bundled_fixture_calendar_with_no_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "standing-cost"
            demo.mkdir()
            (demo / sc.FIXTURE).write_text(json.dumps(partial(CLEAN)), encoding="utf-8")
            cfg = {"out_dir": tmp, "demo_root": str(demo)}
            sources, events = sc.read_source("calendar", Budget(), cfg)
            self.assertEqual(len(events), 10)
            self.assertTrue(sources[0].found)
            self.assertIn("demo", sources[0].name)
            v = sc.analyse(events, NOW, cfg)
            self.assertEqual(v["person_hours"], 20.0)

    def test_a_missing_demo_fixture_is_a_miss_not_an_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "demo_root": tmp + "/nope"})
            self.assertEqual(events, [])
            self.assertFalse(sources[0].found)

    def test_a_bare_list_of_events_parses_as_a_calendar_with_the_envelope_left_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sc.PARTIAL).write_text(json.dumps(CLEAN), encoding="utf-8")
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            self.assertEqual(len(events), 10)

    def test_the_camelcase_spellings_google_itself_uses_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = [{"id": "c1", "recurringEventId": "series", "summary": "Sync",
                    "start": {"dateTime": (NOW - timedelta(days=2)).isoformat()},
                    "end": {"dateTime": (NOW - timedelta(days=2, hours=-1)).isoformat()},
                    "organizer": {"email": ALICE},
                    "attendees": [{"email": ALICE, "responseStatus": "accepted",
                                   "displayName": "Alice Example", "self": True},
                                  {"email": BOB, "responseStatus": "declined"}]}]
            (Path(tmp) / sc.PARTIAL).write_text(json.dumps({"events": raw}), encoding="utf-8")
            sources, events = sc.read_source("calendar", Budget(),
                                             {"out_dir": tmp, "partial": sc.PARTIAL})
            v = sc.analyse(events, NOW, {"out_dir": tmp})
            self.assertEqual(v["person_hours"], 1.0)
            self.assertEqual(v["declined_person_hours"], 1.0)
            self.assertEqual(v["series"][0]["name"], "Sync")


class TestRecurringAndOneOffAreNeverConflated(unittest.TestCase):
    def test_one_off_meetings_are_counted_and_kept_out_of_the_series_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = NOW.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=5)
            people = [att(ALICE, self=True), att(BOB)]
            one_offs = [event("o1", "", "Interview", base, 60, people),
                        event("o2", "", "Vendor call", base + timedelta(days=1), 30, people)]
            v, sources, cfg = analysed(tmp, CLEAN + one_offs)
            self.assertEqual(v["series_total"], 1)                  # one-offs are not a series
            self.assertEqual(v["one_off_occurrences"], 2)
            self.assertEqual(v["recurring_person_hours"], 20.0)     # 4 x 0.5 x 10
            self.assertEqual(v["one_off_person_hours"], 3.0)        # 2x1 + 2x0.5
            self.assertEqual(v["person_hours"], 23.0)
            card = sc.render(v, cfg)
            self.assertIn("plus 2 one-off meetings outside any series: 3.0 person-hours", card)
            self.assertIn("| in one-off meetings | 3.0 |", sc.report_markdown(v, cfg, sources))

    def test_a_one_off_meeting_still_fragments_the_day_it_lands_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = NOW.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=5)
            people = [att(ALICE, self=True), att(BOB)]
            pair = [event("o1", "", "Interview", base, 30, people),
                    event("o2", "", "Debrief", base + timedelta(minutes=60), 30, people)]
            v, _, _ = analysed(tmp, pair)
            self.assertEqual(v["series_total"], 0)
            self.assertEqual(v["fragmentation"]["minutes"], 30)

    def test_a_person_silent_in_two_series_is_one_person_on_the_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiet = att(CARA, "needsAction")
            events = weekly("a", "Standup", 5, 30, [att(ALICE, self=True), att(BOB), quiet])
            events += weekly("b", "Retro", 5, 60, [att(ALICE, self=True), quiet], hour=16)
            v, _, cfg = analysed(tmp, events)
            self.assertEqual(v["silent_total"], 2)          # two series-level findings
            self.assertEqual(v["silent_people"], 1)         # one human
            self.assertIn("1 attendee has never accepted", sc.render(v, cfg))

    def test_a_zone_that_cannot_be_resolved_says_unknown_rather_than_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = NOW.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(days=2)
            people = [att(ALICE, self=True, timezone="UTC+00:00", utc_offset_minutes=0),
                      att(BOB, timezone="Europe/Lisbon")]
            v, sources, cfg = analysed(tmp, [event("z1", "z", "Late call", base, 60, people)])
            by_person = {p["person"]: p for p in v["people"]}
            self.assertTrue(by_person["A. E."]["zone_known"])
            self.assertEqual(by_person["A. E."]["out_of_hours"], 1)      # 22:00 UTC
            self.assertFalse(by_person["B. E."]["zone_known"])
            report = sc.report_markdown(v, cfg, sources)
            self.assertIn("| B. E. | 1.0 | 50% | 1 | 1 | 0 | 0 | Europe/Lisbon | unknown |", report)


class TestDeterminism(unittest.TestCase):
    def test_the_same_input_and_the_same_now_render_byte_identical_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = CLEAN + weekly("sync", "Design sync", 5, 45,
                                    [att(ALICE, self=True), att(BOB), att(CARA, "needsAction")],
                                    hour=15, cancel_every=4)
            first, sources, cfg = analysed(tmp, events, hourly_rate=80)
            shuffled = list(reversed(events))
            write_partial(tmp, shuffled)
            second_sources, loaded, cfg2 = load(tmp, {"hourly_rate": 80})
            second = sc.analyse(loaded, NOW, cfg2)
            self.assertEqual(json.dumps(first, default=str, sort_keys=True),
                             json.dumps(second, default=str, sort_keys=True))
            self.assertEqual(sc.render(first, cfg), sc.render(second, cfg2))
            self.assertEqual(sc.report_markdown(first, cfg, sources),
                             sc.report_markdown(second, cfg2, second_sources))

    def test_the_card_stays_inside_its_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, _, cfg = analysed(tmp, CLEAN, hourly_rate=125)
            for line in sc.render(v, cfg).splitlines():
                from daily_core.common import display_width
                self.assertEqual(display_width(line), 64, repr(line))


class TestTheModuleCannotReachTheNetwork(unittest.TestCase):
    """The whole architecture in one assertion: the fetch lives in TypeScript, not in here."""

    def test_no_network_module_is_imported(self):
        pattern = re.compile(
            r"^\s*(?:import|from)\s+(urllib|http|https|socket|ssl|requests|ftplib|smtplib|"
            r"telnetlib|xmlrpc|asyncio|selectors)\b", re.M)
        self.assertIsNone(pattern.search(SOURCE))

    def test_nothing_that_opens_a_connection_is_even_named(self):
        for banned in ("urlopen", "urlretrieve", "create_connection", "HTTPSConnection",
                       "subprocess", "socketpair"):
            self.assertNotIn(banned, SOURCE, banned)

    def test_the_partial_schema_is_documented_in_the_module_itself(self):
        """The TypeScript step is generated against this docstring; it has to stay in the file."""
        doc = sc.__doc__ or ""
        for key in ("recurring_event_id", "response_status", "attendance_recorded", "attendees",
                    "utc_offset_minutes", "organizer", "status", "summary"):
            self.assertIn(key, doc, key)

    def test_the_module_writes_nothing_except_through_the_shared_helper(self):
        self.assertNotIn(".write_text(", SOURCE)
        self.assertNotIn(".write_bytes(", SOURCE)
        self.assertIn("baseline_write(cfg[\"out_dir\"]", SOURCE)


if __name__ == "__main__":
    unittest.main()
