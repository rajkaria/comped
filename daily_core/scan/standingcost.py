"""standing-cost: what that recurring meeting has actually cost.

Nobody schedules a meeting by its price. A 30-minute standup with nine people is four and a half
person-hours every time it fires, and over a year that is a number no calendar will ever show you.
Every fact needed to compute it is already in the calendar — who was invited, who accepted, how
long it ran, how often it was cancelled — so this does the arithmetic and prints the denominators.

## This module never touches a network, and that is the architecture, not an accident

`daily_core` is network-free and `tests/test_daily_safety.py` proves it statically: no `urllib`,
`http`, `socket`, `ssl`, `requests` or `asyncio` import exists anywhere in the package. That claim
is the most valuable thing these Plays say, so it is not spent on a calendar fetch. Instead the
Play's TypeScript step calls the Google Calendar adapter and writes a **normalized JSON partial**
into `out_dir`; this module only ever reads that file. The fetch and the arithmetic are separate
programs on purpose, and the one you are reading cannot reach anything but a local file.

## The partial's schema (version 1)

The TypeScript step is generated against exactly this shape. Keys are snake_case; the camelCase
spellings Google itself uses (`recurringEventId`, `responseStatus`, `displayName`) are accepted as
aliases so a thin adapter can pass a lightly-mapped payload through. Everything except `id`,
`start` and `end` is optional, and every missing field degrades to a labelled unknown.

    {
      "schema": 1,                       // int, this document's version
      "source": "google-calendar",       // free text, printed in the report's source table
      "account": "work",                 // a label, never an address
      "fetched": "2026-09-05T09:00:00Z", // when the fetch step ran
      "window": {"start": "...", "end": "..."},   // ISO 8601, what the fetch asked for
      "timezone": "Europe/London",       // the calendar's own zone, the last-resort fallback
      "truncated": false,                // true when the fetch stopped at a page limit
      "note": "",                        // anything the fetch step wants the report to say
      "events": [
        {
          "id": "evt_0001",                     // required, unique per occurrence
          "recurring_event_id": "series_stand", // "" for a one-off; groups a series otherwise
          "summary": "Monday Standup",          // the title as shown in the calendar
          "start": "2026-01-05T09:00:00+00:00", // required, ISO 8601 with an offset
          "end":   "2026-01-05T09:30:00+00:00", // required, ISO 8601 with an offset
          "status": "confirmed",                // confirmed | tentative | cancelled
          "organizer": "alice@example.com",     // an address; never printed unredacted
          "agenda_link": "https://...",         // any agenda/notes URL the event carries
          "has_agenda": false,                  // true if the description holds an agenda
          "attendance_recorded": true,          // true when `attended` below is trustworthy
          "attendees": [
            {
              "email": "alice@example.com",     // required to identify a person
              "display_name": "Alice Brown",    // optional
              "response_status": "accepted",    // accepted | declined | tentative | needsAction
              "optional": false,                // the invite was marked optional
              "self": true,                     // this attendee is the calendar's owner
              "organizer": false,
              "timezone": "Europe/London",      // the attendee's own zone, where known
              "utc_offset_minutes": 60,         // that zone's offset at this event
              "attended": true                  // only meaningful with attendance_recorded
            }
          ]
        }
      ]
    }

A document may also be a bare JSON list of events, which is the same thing with the envelope left
off. Anything else is a labelled miss.

## What the arithmetic refuses to do

* There is no default hourly rate. A rate invented by this program would be a fact-shaped guess,
  so with `hourly_rate` unset the Play reports person-hours and says the rate is unset, and with it
  set every single surface that prints money carries the word "assumed" next to the number.
* Declined and non-responding invitees are counted, reported, and left out of the headline
  person-hours: billing someone for a meeting they said no to is how these numbers become fiction.
* Cancelled occurrences are credited, never billed. A series that is skipped half the time costs
  half as much, and the theoretical maximum is a number nobody paid.
* Attendee names and addresses are reduced to initials unless `redact=false`, and no address is
  ever printed in full on the card or in the report either way.
"""
import json
import os
import re
from collections import Counter
from datetime import timedelta, timezone
from pathlib import Path

from ..card import Card, legend, tier_bar
from ..common import (Budget, Source, baseline_read, baseline_write, day, delta, iso, parse_date,
                      pct, plural, redact_name, since_note)

NAME = "standing-cost"
FIXTURE = "calendar.json"
PARTIAL = ".standing-cost-calendar.json"
SCHEMA = 1

WINDOW_DAYS = 365
FOCUS_BLOCK_MINUTES = 90
WORK_START, WORK_END = 9, 18

# A response is one of four things. Everything a calendar can say maps onto these, and the two that
# are billed are named once here so no later line can quietly widen them.
ACCEPTED, TENTATIVE, DECLINED, NO_RESPONSE = "accepted", "tentative", "declined", "no response"
BILLED = (ACCEPTED, TENTATIVE)

ASSUMED = "(assumed)"           # every money surface carries this; the tests check every line

_OFFSET = re.compile(r"([+-])(\d{1,2}):?(\d{2})?$")


# ---------------------------------------------------------------- normalising the partial

def _text(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def _pick(d: dict, *names):
    """The first of several spellings that is present, so a camelCase adapter also parses."""
    for n in names:
        if isinstance(d, dict) and d.get(n) not in (None, ""):
            return d[n]
    return None


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _rate(cfg: dict):
    """The hourly rate, or None. Blank, zero, negative and unparseable all mean "you did not say"."""
    raw = cfg.get("hourly_rate", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _zone_offset(zone: str):
    """Minutes east of UTC for the offset-shaped zone strings, or None for a named zone.

    An IANA name cannot be resolved without a database this package will not import, so a named
    zone is carried as a label and the offset is taken from the event's own timestamp instead.
    That is the honest half of "timezone-aware": say which zone, and say when you had to guess.
    """
    z = _text(zone)
    if not z:
        return None
    if z.upper() in ("UTC", "GMT", "Z"):
        return 0
    m = _OFFSET.search(z.replace("UTC", "").replace("GMT", ""))
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    return sign * (int(m.group(2)) * 60 + int(m.group(3) or 0))


def _response(v) -> str:
    r = _text(v).lower().replace("_", "").replace("-", "")
    if r.startswith("accept"):
        return ACCEPTED
    if r.startswith("declin"):
        return DECLINED
    if r.startswith("tentat"):
        return TENTATIVE
    return NO_RESPONSE


def _attendee(raw: dict, default_zone: str) -> dict:
    email = _text(_pick(raw, "email", "address")).lower()
    zone = _text(_pick(raw, "timezone", "time_zone", "timeZone")) or _text(default_zone)
    offset = _int(_pick(raw, "utc_offset_minutes", "utcOffsetMinutes", "offset_minutes"))
    if offset is None:
        offset = _zone_offset(zone)
    attended = _pick(raw, "attended", "present")
    return {
        "email": email,
        "name": _text(_pick(raw, "display_name", "displayName", "name")),
        "response": _response(_pick(raw, "response_status", "responseStatus", "response")),
        "optional": bool(raw.get("optional", False)),
        "self": bool(_pick(raw, "self", "is_self") or False),
        "organizer": bool(_pick(raw, "organizer", "is_organizer") or False),
        "zone": zone,
        "offset": offset,
        "zone_known": bool(zone),
        "attended": None if attended is None else bool(attended),
        "implied": False,
    }


def normalize(raw: dict, default_zone: str = "") -> dict:
    """One event, in the shape everything below expects. Idempotent: a normalized event survives.

    Nothing here raises. An event without a usable start and end is kept and marked `bad`, because
    "the calendar gave me 812 events and 3 of them had no end time" is a fact the report prints.
    """
    if isinstance(raw, dict) and raw.get("_normalized"):
        return raw
    raw = raw if isinstance(raw, dict) else {}
    start = parse_date(_text(_start_of(_pick(raw, "start", "start_time", "startTime"))))
    end = parse_date(_text(_start_of(_pick(raw, "end", "end_time", "endTime"))))
    status = _text(_pick(raw, "status")).lower() or "confirmed"
    zone = _text(_pick(raw, "timezone", "time_zone", "timeZone")) or _text(default_zone)
    organizer = _pick(raw, "organizer", "organiser") or ""
    if isinstance(organizer, dict):
        organizer = _pick(organizer, "email", "address") or ""
    attendees = [_attendee(a, zone) for a in (raw.get("attendees") or []) if isinstance(a, dict)]
    if not attendees and _text(organizer):
        # A recurring block with no invitee list still costs the person who holds it. One implied
        # attendee is the smallest honest answer, and it is counted so the card can say how many.
        attendees = [_attendee({"email": organizer, "response_status": ACCEPTED, "self": True,
                                "organizer": True, "timezone": zone}, zone)]
        attendees[0]["implied"] = True
    minutes = 0.0
    if start and end and end > start:
        minutes = (end - start).total_seconds() / 60.0
    recorded = _pick(raw, "attendance_recorded", "attendanceRecorded")
    if recorded is None:
        recorded = any(a["attended"] is not None for a in attendees)
    agenda_link = _text(_pick(raw, "agenda_link", "agendaLink", "notes_link", "notesLink"))
    return {
        "_normalized": True,
        "id": _text(_pick(raw, "id", "event_id", "eventId")),
        "series": _text(_pick(raw, "recurring_event_id", "recurringEventId", "series")),
        "summary": _text(_pick(raw, "summary", "title")) or "(no title)",
        "start": start,
        "end": end,
        "minutes": minutes,
        "status": status,
        "cancelled": status.startswith("cancel"),
        "organizer": _text(organizer).lower(),
        "agenda": bool(agenda_link) or bool(_pick(raw, "has_agenda", "hasAgenda") or False),
        "agenda_link": agenda_link,
        "attendance_recorded": bool(recorded),
        "attendees": attendees,
        "zone": zone,
        "bad": "" if minutes > 0 else ("no start time" if not start else "no usable end time"),
    }


def _start_of(v):
    """Google wraps a time in {"dateTime": ...} or {"date": ...}; a flat string is also accepted."""
    if isinstance(v, dict):
        return _pick(v, "dateTime", "date_time", "date", "value") or ""
    return v or ""


# ---------------------------------------------------------------- reading

def read_source(source, budget: Budget, cfg: dict) -> tuple:
    """Load the normalized calendar partial. Returns (sources, events); never raises, never fetches.

    `cfg["partial"]` names the file the Play's calendar step wrote (relative paths resolve under
    `out_dir`). `cfg["demo_root"]` reads the bundled fixture calendar instead, which is what makes
    a cold `demo=true` run work on a machine with no account attached at all.
    """
    label = _text(source) or "calendar"
    if cfg.get("demo_root"):
        path = Path(os.path.expanduser(str(cfg["demo_root"]))) / FIXTURE
        src = Source(name="{0} (demo)".format(label), path=str(path))
        note = "bundled fixture"
    else:
        path = _partial_path(cfg)
        src = Source(name=label, path=str(path))
        note = "written by the calendar step"

    if not path.is_file():
        return [src.miss(
            "the calendar step has not run: nothing at {0}. That step is the one that talks to "
            "Google; this one only reads the file it leaves behind.".format(path.name))], []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return [src.miss("could not read {0}".format(path.name))], []
    budget.spend(len(raw.encode("utf-8", "replace")))
    try:
        doc = json.loads(raw)
    except ValueError:
        return [src.miss("{0} is not valid JSON; the calendar step wrote it "
                         "incompletely".format(path.name))], []

    if isinstance(doc, list):
        doc = {"events": doc}
    if not isinstance(doc, dict):
        return [src.miss("{0} is not a calendar document".format(path.name))], []
    schema = _int(doc.get("schema"))
    if schema is not None and schema > SCHEMA:
        return [src.miss("{0} is schema {1}; this build reads schema {2}".format(
            path.name, schema, SCHEMA))], []

    default_zone = _text(doc.get("timezone"))
    events, stopped = [], False
    for item in (doc.get("events") or []):
        if not budget.spend(0):
            stopped = True
            break
        events.append(normalize(item, default_zone))
    events.sort(key=lambda e: (iso(e["start"]), e["id"], e["summary"]))

    detail = [note]
    if _text(doc.get("account")):
        detail.append("account {0}".format(_text(doc["account"])))
    if _text(doc.get("source")):
        detail.append(_text(doc["source"]))
    if doc.get("truncated"):
        detail.append("the fetch stopped at its page limit; counts are a lower bound")
    if stopped:
        detail.append("stopped at the traversal bound")
    if _text(doc.get("note")):
        detail.append(_text(doc["note"]))
    if not events:
        return [src.hit(0, "; ".join(detail + ["no events in the window"]))], []
    return [src.hit(len(events), "; ".join(detail))], events


def _partial_path(cfg: dict) -> Path:
    raw = _text(cfg.get("partial")) or PARTIAL
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute() and cfg.get("out_dir"):
        p = Path(os.path.expanduser(str(cfg["out_dir"]))) / raw
    return p


# ---------------------------------------------------------------- analysis

def analyse(events: list, now, cfg: dict) -> dict:
    """Everything the card and the report print, computed once. Same input + same `now` → same view."""
    days = max(1, _int(cfg.get("days")) or WINDOW_DAYS)
    focus_block = max(1, _int(cfg.get("focus_block_minutes")) or FOCUS_BLOCK_MINUTES)
    redact = cfg.get("redact", True)
    rate = _rate(cfg)
    currency = _text(cfg.get("currency")) or "£"

    events = [normalize(e) for e in (events or [])]
    window_start = now - timedelta(days=days)
    inside, outside, unusable = [], 0, []
    for e in events:
        if e["bad"] or not e["start"]:
            unusable.append(e)
        elif window_start <= e["start"] <= now:
            inside.append(e)
        else:
            outside += 1
    inside.sort(key=lambda e: (iso(e["start"]), e["id"]))

    for e in inside:
        e["_billed"] = [a for a in e["attendees"] if a["response"] in BILLED]
        e["_declined"] = [a for a in e["attendees"] if a["response"] == DECLINED]
        e["_silent"] = [a for a in e["attendees"] if a["response"] == NO_RESPONSE]
        e["_hours"] = e["minutes"] / 60.0

    live = [e for e in inside if not e["cancelled"]]
    killed = [e for e in inside if e["cancelled"]]

    person_hours = sum(len(e["_billed"]) * e["_hours"] for e in live)
    recurring_hours = sum(len(e["_billed"]) * e["_hours"] for e in live if e["series"])
    declined_hours = sum(len(e["_declined"]) * e["_hours"] for e in live)
    no_response_hours = sum(len(e["_silent"]) * e["_hours"] for e in live)
    tentative_hours = sum(sum(1 for a in e["_billed"] if a["response"] == TENTATIVE) * e["_hours"]
                          for e in live)
    credit_hours = sum(len(e["_billed"]) * e["_hours"] for e in killed)
    meeting_hours = sum(e["_hours"] for e in live)

    owner = _owner(inside, cfg)
    series = _series(live, killed, now, redact, rate, person_hours)
    people = _people(live, redact, rate, person_hours)
    silent = _silent(series)
    frag = _fragmentation(live, owner, focus_block)
    zones = _zones(live)
    covered = _covered_days(inside, now, days)
    projection = _projection(person_hours, len(live), covered)

    view = {
        "schema": SCHEMA,
        "now": iso(now),
        "window_days": days,
        "window_start": day(window_start),
        "window_end": day(now),
        "days_covered": covered,
        "events_read": len(events),
        "events_outside_window": outside,
        "events_unusable": len(unusable),
        "unusable_reasons": _reasons(unusable),
        "occurrences": len(live),
        "cancelled_occurrences": len(killed),
        "scheduled_occurrences": len(inside),
        "one_off_occurrences": sum(1 for e in live if not e["series"]),
        "meeting_hours": round(meeting_hours, 2),
        "person_hours": round(person_hours, 2),
        "recurring_person_hours": round(recurring_hours, 2),
        "one_off_person_hours": round(person_hours - recurring_hours, 2),
        "tentative_person_hours": round(tentative_hours, 2),
        "declined_person_hours": round(declined_hours, 2),
        "no_response_person_hours": round(no_response_hours, 2),
        "implied_attendees": sum(1 for e in live for a in e["attendees"] if a["implied"]),
        "attendee_occurrences": sum(len(e["_billed"]) for e in live),
        "series": series,
        "series_total": len(series),
        "series_without_agenda": sum(1 for s in series if not s["agenda"]),
        "people": people,
        "people_total": len(people),
        "silent": silent,
        "silent_total": len(silent),
        "silent_people": len(set(row["person"] for row in silent)),
        "silent_person_hours": round(sum(s["hours"] for s in silent), 2),
        "cancellation": {
            "cancelled": len(killed),
            "scheduled": len(inside),
            "share": pct(len(killed), len(inside)),
            "credit_person_hours": round(credit_hours, 2),
            "note": "billed on the {0} that actually happened, not the {1} that were "
                    "scheduled".format(plural(len(live), "occurrence"), len(inside)),
        },
        "drift": [s for s in series if s["drift"]],
        "fragmentation": frag,
        "zones": zones,
        "projection": projection,
        "ranking_cost": [{"name": s["name"], "id": s["id"], "person_hours": s["person_hours"],
                          "share": s["share"]} for s in series[:8]],
        "ranking_decision": _decision_ranking(series),
        "rate": {
            "set": rate is not None,
            "hourly_rate": rate,
            "currency": currency,
            # `label` is short and always carries the word "assumed" next to the figure, because it
            # is printed on one card row and a row that wrapped could separate the two.
            "label": ("assumed {0}{1}/hour".format(currency, _plain(rate)) if rate is not None
                      else "hourly rate unset, so no money is claimed"),
            "caveat": ("a rate you supplied, taken on trust: this Play has no way to check it, and "
                       "every figure derived from it is an assumption, not a measurement."
                       if rate is not None else
                       "person-hours only. A rate invented here would be a guess wearing the "
                       "clothes of a fact, so set hourly_rate to see money."),
        },
        "cost": _cost_block(person_hours, rate, currency),
        "redacted": bool(redact),
        "focus_block_minutes": focus_block,
        "owner": redact_name(_person_name({"email": owner, "name": ""}), True) if owner else "",
    }
    view["headline"] = _headline(view)
    view["baseline"] = _payload(view)
    previous = baseline_read(cfg["out_dir"], NAME) if cfg.get("out_dir") else {}
    view["delta"] = delta(view["baseline"], previous.get("payload", {}))
    view["since"] = since_note(previous, now)
    return view


def _reasons(unusable: list) -> list:
    counts = Counter(e["bad"] or "unreadable" for e in unusable)
    return [{"reason": k, "events": v} for k, v in sorted(counts.items())]


def _covered_days(inside: list, now, days: int) -> int:
    """How much of the window the calendar actually spans, so a projection divides by the truth."""
    starts = [e["start"] for e in inside if e["start"]]
    if not starts:
        return 0
    return max(1, min(days, int((now - min(starts)).total_seconds() // 86400) + 1))


# -- series ----------------------------------------------------------------

def _series(live: list, killed: list, now, redact: bool, rate, total_hours: float) -> list:
    """One row per recurring series, ranked by what it cost. One-off events are not a series."""
    groups, cancelled_groups = {}, {}
    for e in live:
        if e["series"]:
            groups.setdefault(e["series"], []).append(e)
    for e in killed:
        if e["series"]:
            cancelled_groups.setdefault(e["series"], []).append(e)

    out = []
    for key in sorted(set(list(groups.keys()) + list(cancelled_groups.keys()))):
        ran = sorted(groups.get(key, []), key=lambda e: (iso(e["start"]), e["id"]))
        skipped = sorted(cancelled_groups.get(key, []), key=lambda e: (iso(e["start"]), e["id"]))
        if not ran and not skipped:
            continue
        sample = ran or skipped
        hours = sum(len(e["_billed"]) * e["_hours"] for e in ran)
        credit = sum(len(e["_billed"]) * e["_hours"] for e in skipped)
        typical_minutes = _typical([e["minutes"] for e in ran] or [e["minutes"] for e in skipped])
        typical_people = _typical([len(e["_billed"]) for e in ran] or
                                  [len(e["_billed"]) for e in skipped])
        out.append({
            "id": key,
            "name": sample[-1]["summary"],
            "occurrences": len(ran),
            "cancelled": len(skipped),
            "scheduled": len(ran) + len(skipped),
            "cancel_share": pct(len(skipped), len(ran) + len(skipped)),
            "minutes": typical_minutes,
            "attendees": typical_people,
            "person_hours": round(hours, 2),
            "credit_person_hours": round(credit, 2),
            "declined_person_hours": round(sum(len(e["_declined"]) * e["_hours"] for e in ran), 2),
            "no_response_person_hours": round(sum(len(e["_silent"]) * e["_hours"] for e in ran), 2),
            "attendee_occurrences": sum(len(e["_billed"]) for e in ran),
            "share": (hours / total_hours) if total_hours else 0.0,
            "first": day(sample[0]["start"]),
            "last": day(sample[-1]["start"]),
            "cadence": _cadence(ran + skipped),
            "agenda": any(e["agenda"] for e in ran + skipped),
            "cost": None if rate is None else round(hours * rate, 2),
            "drift": _drift(ran),
            "silent": _series_silent(ran, redact),
            "exact": abs(typical_people * (typical_minutes / 60.0) * len(ran) - hours) <= 0.02 * max(hours, 1),
        })
    return sorted(out, key=lambda s: (-s["person_hours"], s["name"], s["id"]))


def _typical(values: list):
    """The value that occurs most often; ties go to the larger, so a tie never reads as a shrink."""
    if not values:
        return 0
    counts = Counter(values)
    best = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))[0][0]
    return int(best) if float(best).is_integer() else round(float(best), 1)


def _cadence(occurrences: list) -> str:
    starts = sorted(iso(e["start"]) for e in occurrences if e["start"])
    if len(starts) < 2:
        return "once in this window"
    gaps = []
    parsed = [parse_date(s) for s in starts]
    for a, b in zip(parsed, parsed[1:]):
        gaps.append(int(round((b - a).total_seconds() / 86400.0)))
    gaps = sorted(g for g in gaps if g > 0)
    if not gaps:
        return "several a day"
    typical = gaps[len(gaps) // 2]
    if typical <= 1:
        return "daily"
    if typical <= 4:
        return "every {0} days".format(typical)
    if 5 <= typical <= 9:
        return "weekly"
    if 12 <= typical <= 16:
        return "fortnightly"
    if 27 <= typical <= 32:
        return "monthly"
    return "every {0} days".format(typical)


def _drift(ran: list):
    """Did the series grow? Halves are compared, not endpoints: one long session is not a trend."""
    if len(ran) < 4:
        return None
    half = len(ran) // 2
    first, second = ran[:half], ran[half:]
    d0 = sum(e["minutes"] for e in first) / len(first)
    d1 = sum(e["minutes"] for e in second) / len(second)
    a0 = sum(len(e["_billed"]) for e in first) / float(len(first))
    a1 = sum(len(e["_billed"]) for e in second) / float(len(second))
    grew_minutes = round(d1 - d0, 1)
    grew_people = round(a1 - a0, 1)
    if grew_minutes < 5 and grew_people < 1:
        return None
    return {
        "minutes_before": round(d0, 1), "minutes_after": round(d1, 1), "minutes_grew": grew_minutes,
        "attendees_before": round(a0, 1), "attendees_after": round(a1, 1),
        "attendees_grew": grew_people,
        "halves": [len(first), len(second)],
        "note": "; ".join(
            [t for t in ["{0} min → {1} min".format(round(d0, 1), round(d1, 1)) if grew_minutes >= 5 else "",
                         "{0} → {1} people".format(round(a0, 1), round(a1, 1)) if grew_people >= 1 else ""] if t]),
    }


def _series_silent(ran: list, redact: bool) -> list:
    """Invited every single time and never accepted, or accepted and never actually there.

    Both are the same finding stated twice: this person's presence is a formality, and the series
    would lose nothing by sending them the notes instead. Only people invited to *every*
    occurrence qualify, so somebody added last month is not accused of anything.
    """
    if not ran:
        return []
    invited, accepted, recorded, attended, hours, names = (
        Counter(), Counter(), Counter(), Counter(), Counter(), {})
    for e in ran:
        for a in e["attendees"]:
            invited[a["email"]] += 1
            names.setdefault(a["email"], a["name"])
            if a["response"] == ACCEPTED:
                accepted[a["email"]] += 1
            if a["response"] in BILLED:
                hours[a["email"]] += e["_hours"]
            if e["attendance_recorded"] and a["attended"] is not None:
                recorded[a["email"]] += 1
                if a["attended"]:
                    attended[a["email"]] += 1
    out = []
    for email in sorted(invited):
        if invited[email] < len(ran):
            continue
        if not accepted[email]:
            out.append({"person": _label(email, names.get(email), redact),
                        "reason": "never accepted", "invited": invited[email],
                        "recorded": recorded[email], "attended": attended[email],
                        "hours": 0.0, "billed": False})
        elif recorded[email] and not attended[email]:
            out.append({"person": _label(email, names.get(email), redact),
                        "reason": "accepted every time, never present",
                        "invited": invited[email], "recorded": recorded[email],
                        "attended": 0, "hours": round(hours[email], 2), "billed": True})
    return out


def _silent(series: list) -> list:
    rows = []
    for s in series:
        for person in s["silent"]:
            row = dict(person)
            row["series"] = s["name"]
            row["series_id"] = s["id"]
            rows.append(row)
    return sorted(rows, key=lambda r: (-r["hours"], -r["invited"], r["person"], r["series"]))


def _decision_ranking(series: list) -> list:
    """The second ranking: contact spent on series that leave no written trace of a decision.

    `attendees x occurrences` is the number of person-appearances a series consumed. Dividing that
    across only the series carrying no agenda and no notes link gives a cost-per-decision proxy in
    the strict sense that the denominator is missing: nobody wrote down what was decided.
    """
    blind = [s for s in series if not s["agenda"]]
    total = sum(s["attendee_occurrences"] for s in blind)
    return [{"name": s["name"], "id": s["id"],
             "attendee_occurrences": s["attendee_occurrences"],
             "person_hours": s["person_hours"],
             "share": (s["attendee_occurrences"] / total) if total else 0.0,
             "occurrences": s["occurrences"], "attendees": s["attendees"]}
            for s in sorted(blind, key=lambda s: (-s["attendee_occurrences"], s["name"], s["id"]))[:8]]


# -- people ----------------------------------------------------------------

def _people(live: list, redact: bool, rate, total_hours: float) -> list:
    """The attendee-side view: what this window cost each person, and their share of the total."""
    hours, meetings, declines, silent, names, zones, offsets = (
        Counter(), Counter(), Counter(), Counter(), {}, {}, {})
    series_seen, out_of_hours, unknown_zone = {}, Counter(), set()
    for e in live:
        for a in e["attendees"]:
            email = a["email"]
            names.setdefault(email, a["name"])
            if a["zone"] and email not in zones:
                zones[email] = a["zone"]
            if a["offset"] is not None and email not in offsets:
                offsets[email] = a["offset"]
            if a["response"] == DECLINED:
                declines[email] += 1
                continue
            if a["response"] == NO_RESPONSE:
                silent[email] += 1
                continue
            hours[email] += e["_hours"]
            meetings[email] += 1
            series_seen.setdefault(email, set()).add(e["series"] or e["id"])
            local = _local_hour(e["start"], a)
            if local is None:
                unknown_zone.add(email)
            elif local < WORK_START or local >= WORK_END:
                out_of_hours[email] += 1

    rows = []
    for email in sorted(set(list(hours.keys()) + list(declines.keys()) + list(silent.keys()))):
        h = round(hours[email], 2)
        rows.append({
            "person": _label(email, names.get(email), redact),
            "hours": h,
            "share": (hours[email] / total_hours) if total_hours else 0.0,
            "meetings": meetings[email],
            "series": len(series_seen.get(email, ())),
            "declined": declines[email],
            "no_response": silent[email],
            "zone": zones.get(email, ""),
            "zone_known": email in zones and email not in unknown_zone,
            "out_of_hours": out_of_hours[email],
            "cost": None if rate is None else round(hours[email] * rate, 2),
        })
    return sorted(rows, key=lambda r: (-r["hours"], -r["meetings"], r["person"]))


def _local_hour(start, attendee: dict):
    """The hour this meeting struck on that attendee's own clock, or None when the zone is unknown."""
    if not start:
        return None
    offset = attendee.get("offset")
    if offset is None:
        return None
    return (start.astimezone(timezone.utc) + timedelta(minutes=offset)).hour


def _offset_label(minutes: int) -> str:
    """`UTC+05:30` for an attendee whose zone arrived as an offset and no name."""
    sign = "-" if minutes < 0 else "+"
    total = abs(int(minutes))
    return "UTC{0}{1:02d}:{2:02d}".format(sign, total // 60, total % 60)


def _zones(live: list) -> dict:
    known, unknown, labels = set(), set(), Counter()
    for e in live:
        for a in e["attendees"]:
            if a["offset"] is not None:
                known.add(a["email"])
                labels[a["zone"] or _offset_label(a["offset"])] += 1
            else:
                unknown.add(a["email"])
    unknown -= known
    return {"known": len(known), "unknown": len(unknown),
            "zones": [{"zone": z, "attendee_occurrences": n}
                      for z, n in sorted(labels.items(), key=lambda kv: (-kv[1], kv[0]))[:6]],
            "note": ("every attendee carried a zone" if not unknown else
                     "{0} attendee(s) carried no zone; their hours are counted in the "
                     "calendar's own zone".format(len(unknown)))}


# -- fragmentation ---------------------------------------------------------

def _fragmentation(live: list, owner: str, focus_block: int) -> dict:
    """The gaps too short to use. A 30-minute meeting that splits an afternoon costs more than 30.

    Only gaps strictly shorter than `focus_block` count, and only the space *between* meetings:
    the meetings themselves are already counted as meeting time, and counting them twice would be
    the same trick this Play exists to expose. One-off meetings fragment a day exactly as much as
    recurring ones do, so both are here.
    """
    mine = [e for e in live if _attends(e, owner)] if owner else []
    perspective = "the calendar owner's day"
    if not mine:
        mine, perspective = list(live), "every event in the file"
    offset = _owner_offset(mine, owner)
    by_day = {}
    for e in mine:
        if not e["start"] or not e["end"]:
            continue
        local = e["start"].astimezone(timezone.utc) + timedelta(minutes=offset)
        by_day.setdefault(local.strftime("%Y-%m-%d"), []).append(e)

    days, total, gap_count, overlaps = [], 0.0, 0, 0
    for key in sorted(by_day):
        items = sorted(by_day[key], key=lambda e: (iso(e["start"]), iso(e["end"])))
        minutes, gaps = 0.0, 0
        for a, b in zip(items, items[1:]):
            space = (b["start"] - a["end"]).total_seconds() / 60.0
            if space < 0:
                overlaps += 1
                continue
            if 0 < space < focus_block:
                minutes += space
                gaps += 1
        if minutes > 0:
            days.append({"day": key, "minutes": int(round(minutes)), "gaps": gaps,
                         "meetings": len(items)})
            total += minutes
            gap_count += gaps
    worst = sorted(days, key=lambda d: (-d["minutes"], d["day"]))[:1]
    return {
        "focus_block_minutes": focus_block,
        "minutes": int(round(total)),
        "hours": round(total / 60.0, 2),
        "gaps": gap_count,
        "days_with_meetings": len(by_day),
        "days_fragmented": len(days),
        "overlaps": overlaps,
        "worst": worst[0] if worst else None,
        "days": days[:14],
        "perspective": perspective,
        "note": "gaps shorter than {0} minutes between one meeting and the next, counted "
                "separately from meeting time itself".format(focus_block),
    }


def _attends(event: dict, owner: str) -> bool:
    return any(a["email"] == owner and a["response"] in BILLED for a in event["attendees"])


def _owner(events: list, cfg: dict) -> str:
    explicit = _text(cfg.get("self")).lower()
    if explicit:
        return explicit
    votes = Counter()
    for e in events:
        for a in e["attendees"]:
            if a["self"] and a["email"]:
                votes[a["email"]] += 1
    if not votes:
        for e in events:
            if e["organizer"]:
                votes[e["organizer"]] += 1
    return sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if votes else ""


def _owner_offset(events: list, owner: str) -> int:
    for e in events:
        for a in e["attendees"]:
            if a["email"] == owner and a["offset"] is not None:
                return a["offset"]
    return 0


# -- money, projection, headline ------------------------------------------

def _cost_block(person_hours: float, rate, currency: str) -> dict:
    """Money is optional and always labelled. With no rate there is no number at all, anywhere."""
    if rate is None:
        return {"known": False, "amount": None, "text": "",
                "basis": "no hourly rate was given, so this Play reports {0} person-hours and "
                         "no money".format(round(person_hours, 1))}
    amount = person_hours * rate
    return {"known": True, "amount": round(amount, 2),
            "text": money(amount, currency),
            "basis": "{0} person-hours x an assumed {1}{2}/hour, a rate you stated and this "
                     "Play cannot verify".format(round(person_hours, 1), currency, _plain(rate))}


def money(amount, currency: str = "£") -> str:
    """Every money string in this module comes from here, so every one carries its label."""
    if amount is None:
        return ""
    return "{0}{1:,.0f} {2}".format(currency, round(float(amount)), ASSUMED)


def _plain(value) -> str:
    if value is None:
        return ""
    return "{0:,.0f}".format(value) if float(value).is_integer() else "{0:,.2f}".format(value)


def _projection(person_hours: float, occurrences: int, covered: int) -> dict:
    if not covered or not person_hours:
        return {"person_hours": 0.0, "occurrences": 0, "days_covered": covered,
                "label": "projection: not enough history to extrapolate"}
    factor = 365.0 / covered
    return {"person_hours": round(person_hours * factor, 1),
            "occurrences": int(round(occurrences * factor)),
            "days_covered": covered,
            "label": "projection, not a measurement: the last {0} days repeated for a "
                     "year".format(covered)}


def _headline(v: dict) -> str:
    top = v["series"][0] if v["series"] else None
    if not top:
        return "{0} person-hours across {1}".format(
            _hours(v["person_hours"]), plural(v["occurrences"], "occurrence"))
    return "{0}: {1} x {2} min x {3} = {4} person-hours.".format(
        top["name"], plural(top["attendees"], "attendee"), _plain(top["minutes"]),
        plural(top["occurrences"], "occurrence"), _hours(top["person_hours"]))


def _hours(value) -> str:
    v = float(value or 0)
    return "{0:,.0f}".format(v) if v >= 10 else "{0:,.1f}".format(v)


# -- people labels ---------------------------------------------------------

def _person_name(attendee: dict) -> str:
    name = _text(attendee.get("name"))
    if name:
        return name
    local = _text(attendee.get("email")).split("@")[0]
    return " ".join(p for p in re.split(r"[._\-+]+", local) if p) or "someone"


def _label(email: str, name: str, redact: bool) -> str:
    """A person, countable but never an address. No email is printed in full on either surface.

    With `redact=false` the display name is shown, because a name is what makes the row usable and
    the user asked for it; the address itself stays behind a masked domain either way, since an
    address in a shared report is a mailing list somebody else now owns.
    """
    display = _person_name({"email": email, "name": name})
    if redact:
        return redact_name(display, True)
    local = _text(email).split("@")[0]
    return "{0} <{1}@…>".format(display, local) if local else display


def _payload(v: dict) -> dict:
    payload = {"series::{0}".format(s["id"]): s["person_hours"] for s in v["series"]}
    payload["fragmentation_hours"] = v["fragmentation"]["hours"]
    return payload


def save_baseline(view: dict, cfg: dict, now) -> str:
    """Kept out of `analyse` deliberately: analysing twice must not change what the delta says."""
    return baseline_write(cfg["out_dir"], NAME, view["baseline"], now) if cfg.get("out_dir") else ""


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    c = Card("STANDING COST", "{0} days".format(v["window_days"]), cfg.get("color"))
    c.blank()
    c.wrap(v["headline"])
    # Every money line on this card is one `row`, never a `wrap`: a wrapped line could put the
    # figure and the word "assumed" on different rows, and a number that lost its label is exactly
    # the failure this Play is about.
    if v["cost"]["known"]:
        c.row("At the stated rate, {0}.".format(v["cost"]["text"]))
    else:
        c.row("Hourly rate unset, so no money is claimed: person-hours only.")
    if v["silent"]:
        c.row("{0} never accepted or never turned up.".format(
            plural(v["silent_people"], "attendee has", "attendees have")))
    c.blank()

    c.rule("WHERE THE HOURS WENT")
    for s in v["series"][:5]:
        c.bar("{0}".format(s["name"]), _hours(s["person_hours"]) + "h", s["share"], 10, 26)
    if v["one_off_occurrences"]:
        c.row("plus {0} outside any series: {1} person-hours".format(
            plural(v["one_off_occurrences"], "one-off meeting"),
            _hours(v["one_off_person_hours"])))
    c.row("{0} person-hours billed · {1} declined · {2} never answered".format(
        _hours(v["person_hours"]), _hours(v["declined_person_hours"]),
        _hours(v["no_response_person_hours"])))
    tiers = [("billed", int(round(v["person_hours"]))), ("declined", int(round(v["declined_person_hours"]))),
             ("no answer", int(round(v["no_response_person_hours"])))]
    bar = tier_bar(tiers, 40)
    if bar:
        c.row(bar)
        c.row(legend(tiers))

    c.rule("WHAT WAS NOT BILLED")
    ca = v["cancellation"]
    c.row("{0} of {1} occurrences cancelled ({2}%)".format(ca["cancelled"], ca["scheduled"],
                                                           ca["share"]))
    credit = "credited back: {0} person-hours".format(_hours(ca["credit_person_hours"]))
    if v["rate"]["set"]:
        credit += " · {0}".format(money(ca["credit_person_hours"] * v["rate"]["hourly_rate"],
                                        v["rate"]["currency"]))
    c.row(credit)

    if v["silent"]:
        c.rule("COULD HAVE BEEN AN EMAIL")
        for s in v["silent"][:4]:
            c.cols("{0} — {1}".format(s["person"], s["series"]),
                   "{0} of {1}".format(s["attended"] if s["billed"] else 0, s["invited"]), 12)
            c.row("  {0}".format(s["reason"]))

    if v["drift"]:
        c.rule("SERIES THAT GREW")
        for s in v["drift"][:3]:
            c.cols(s["name"], s["drift"]["note"], 30)

    f = v["fragmentation"]
    if f["minutes"]:
        c.rule("FOCUS TIME DESTROYED")
        c.row("{0} min ({1}h) in gaps under {2} min, across {3}".format(
            f["minutes"], _hours(f["hours"]), f["focus_block_minutes"],
            plural(f["days_fragmented"], "day")))
        if f["worst"]:
            c.row("worst day {0}: {1} min lost between {2}".format(
                f["worst"]["day"], f["worst"]["minutes"], plural(f["worst"]["meetings"], "meeting")))
        c.row("counted separately from the {0} hours of meeting itself".format(
            _hours(v["meeting_hours"])))

    if v["people"]:
        c.rule("WHO PAID FOR IT")
        for p in v["people"][:5]:
            c.bar(p["person"], _hours(p["hours"]) + "h", p["share"], 10, 22)

    c.rule("PROJECTION")
    c.row("{0} person-hours a year at this cadence".format(_hours(v["projection"]["person_hours"])))
    if v["rate"]["set"]:
        c.row(money(v["projection"]["person_hours"] * v["rate"]["hourly_rate"],
                    v["rate"]["currency"]) + " a year")
    c.note(v["projection"]["label"])

    c.blank()
    c.note("Rate: {0}".format(v["rate"]["label"]))
    c.wrap(v["rate"]["caveat"])
    c.note(v["since"])
    c.wrap("Read from the calendar file the fetch step wrote. This step opened no network "
           "connection and no address is printed in full.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    rate = v["rate"]
    L = ["# Standing cost", "",
         v["headline"], ""]
    L.append("{0} person-hours across {1} in {2}, from {3} to {4}.".format(
        _hours(v["person_hours"]), plural(v["occurrences"], "occurrence"),
        plural(v["series_total"], "recurring series", "recurring series"),
        v["window_start"], v["window_end"]))
    L += ["", "**Rate:** {0} — {1}".format(rate["label"], rate["caveat"]), "",
          "**Cost basis:** {0}".format(v["cost"]["basis"]), ""]
    L += ["| measure | value | denominator |", "|---|---|---|",
          "| person-hours billed | {0} | {1} attendee-occurrences over {2} |".format(
              _hours(v["person_hours"]), v["attendee_occurrences"],
              plural(v["occurrences"], "occurrence")),
          "| meeting hours | {0} | wall-clock, one row per occurrence |".format(_hours(v["meeting_hours"])),
          "| in recurring series | {0} | {1} series |".format(
              _hours(v["recurring_person_hours"]), v["series_total"]),
          "| in one-off meetings | {0} | {1} |".format(
              _hours(v["one_off_person_hours"]),
              plural(v["one_off_occurrences"], "occurrence outside any series",
                     "occurrences outside any series")),
          "| declined, not billed | {0} | invitees who said no |".format(_hours(v["declined_person_hours"])),
          "| never answered, not billed | {0} | invitees who never replied |".format(
              _hours(v["no_response_person_hours"])),
          "| tentative, billed | {0} | counted, and separable here |".format(
              _hours(v["tentative_person_hours"])),
          "| cancelled and credited | {0} | {1} of {2} occurrences cancelled |".format(
              _hours(v["cancellation"]["credit_person_hours"]), v["cancellation"]["cancelled"],
              v["cancellation"]["scheduled"]),
          "| focus time destroyed | {0} min | {1} under {2} min |".format(
              v["fragmentation"]["minutes"], plural(v["fragmentation"]["gaps"], "gap"),
              v["fragmentation"]["focus_block_minutes"])]
    if rate["set"]:
        L.append("| cost | {0} | {1} |".format(v["cost"]["text"], v["cost"]["basis"]))
    L += ["", "## Series, ranked by cost", "",
          "| series | occurrences | typical | person-hours | " +
          ("cost | " if rate["set"] else "") + "cadence | agenda |",
          "|---|---|---|---|---|---|" + ("---|" if rate["set"] else "")]
    for s in v["series"]:
        row = "| {0} | {1}{2} | {3} × {4} min | {5} | ".format(
            s["name"], s["occurrences"],
            "" if not s["cancelled"] else " (+{0} cancelled)".format(s["cancelled"]),
            s["attendees"], _plain(s["minutes"]), _hours(s["person_hours"]))
        if rate["set"]:
            row += "{0} | ".format(money(s["cost"], rate["currency"]))
        row += "{0} | {1} |".format(s["cadence"], "yes" if s["agenda"] else "none")
        L.append(row)

    L += ["", "## Cancelled-occurrence credit", "", v["cancellation"]["note"], "",
          "{0} of {1} scheduled occurrences were cancelled ({2}%), crediting back {3} "
          "person-hours{4}.".format(
              v["cancellation"]["cancelled"], v["cancellation"]["scheduled"],
              v["cancellation"]["share"], _hours(v["cancellation"]["credit_person_hours"]),
              "" if not rate["set"] else " ({0})".format(
                  money(v["cancellation"]["credit_person_hours"] * rate["hourly_rate"],
                        rate["currency"])))]

    L += ["", "## Could have been an email", ""]
    if v["silent"]:
        L += ["Invited to every occurrence and never accepted, or accepted and never present "
              "where the calendar recorded attendance.", "",
              "| person | series | invited | attended | reason | hours billed |",
              "|---|---|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            s["person"], s["series"], s["invited"],
            "{0} of {1}".format(s["attended"], s["recorded"]) if s["recorded"] else "not recorded",
            s["reason"], _hours(s["hours"])) for s in v["silent"]]
        L += ["", "{0} person-hours are billed to people who never turned up.".format(
            _hours(v["silent_person_hours"]))]
    else:
        L.append("Nobody was invited to every occurrence of a series and never accepted.")

    L += ["", "## Series that grew", ""]
    if v["drift"]:
        L += ["| series | minutes | attendees | halves compared |", "|---|---|---|---|"]
        L += ["| {0} | {1} → {2} | {3} → {4} | {5} vs {6} occurrences |".format(
            s["name"], s["drift"]["minutes_before"], s["drift"]["minutes_after"],
            s["drift"]["attendees_before"], s["drift"]["attendees_after"],
            s["drift"]["halves"][0], s["drift"]["halves"][1]) for s in v["drift"]]
    else:
        L.append("No series grew in length or headcount across the window.")

    f = v["fragmentation"]
    L += ["", "## Focus time destroyed", "", f["note"], "",
          "Measured from {0}. {1} ({2} hours) lost in {3}, across {4} of {5} days with "
          "meetings. This is counted separately from the {6} hours of meeting "
          "itself.".format(f["perspective"], plural(f["minutes"], "minute"), _hours(f["hours"]),
                           plural(f["gaps"], "gap"), f["days_fragmented"],
                           f["days_with_meetings"], _hours(v["meeting_hours"]))]
    if f["days"]:
        L += ["", "| day | meetings | gaps | minutes lost |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(d["day"], d["meetings"], d["gaps"], d["minutes"])
              for d in f["days"]]

    L += ["", "## Who paid for it", "", "| person | hours | share | meetings | series | declined | "
          "never answered | zone | outside 09–18 local |",
          "|---|---|---|---|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2}% | {3} | {4} | {5} | {6} | {7} | {8} |".format(
        p["person"], _hours(p["hours"]), int(round(p["share"] * 100)), p["meetings"], p["series"],
        p["declined"], p["no_response"],
        p["zone"] or "unknown",
        # An unresolvable zone name cannot produce a local hour, and a 0 there would read as an
        # answer. It is not one.
        p["out_of_hours"] if p["zone_known"] else "unknown")
        for p in v["people"]]
    L += ["", v["zones"]["note"]]

    L += ["", "## Cost per decision, where no decision was written down", "",
          "`attendees × occurrences` is the number of person-appearances a series consumed. "
          "Ranked here across only the {0} series that carry no agenda and no notes link, "
          "because those are the ones with no record of what the time bought.".format(
              v["series_without_agenda"]), ""]
    if v["ranking_decision"]:
        L += ["| series | attendee-occurrences | share of the unrecorded | person-hours |",
              "|---|---|---|---|"]
        L += ["| {0} | {1} | {2}% | {3} |".format(r["name"], r["attendee_occurrences"],
                                                  int(round(r["share"] * 100)), _hours(r["person_hours"]))
              for r in v["ranking_decision"]]
    else:
        L.append("Every series carries an agenda or a notes link.")

    L += ["", "## Projection", "", "{0} person-hours a year at this cadence{1}. {2}".format(
        _hours(v["projection"]["person_hours"]),
        "" if not rate["set"] else " ({0})".format(
            money(v["projection"]["person_hours"] * rate["hourly_rate"], rate["currency"])),
        v["projection"]["label"])]

    d = v["delta"]
    L += ["", "## Since the last run", "", v["since"], ""]
    if d.get("first_run"):
        L.append("Nothing to compare against yet: this run wrote the first baseline.")
    else:
        L += ["| movement | series |", "|---|---|",
              "| grew | {0} |".format(_movement(d["grew"]) or "none"),
              "| shrank | {0} |".format(_movement(d["shrank"]) or "none"),
              "| new | {0} |".format(_movement(d["added"]) or "none"),
              "| gone | {0} |".format(_movement(d["removed"]) or "none"),
              "| net person-hours | {0:+.1f} |".format(d["net"])]

    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(_src(s, "name"), "yes" if _src(s, "found") else "no",
                                       _src(s, "note") or "") for s in sources]
    L += ["", "Computed from the JSON partial the Play's calendar step wrote into the output "
          "folder. This program imports no network module of any kind — the fetch and the "
          "arithmetic are separate programs on purpose — and prints no address in full.", ""]
    return "\n".join(L)


def _movement(items: dict) -> str:
    return ", ".join("{0} {1:+.1f}h".format(k.replace("series::", ""), float(vv))
                     for k, vv in sorted(items.items())[:6])


def _src(s, key: str):
    return s.get(key) if isinstance(s, dict) else getattr(s, key, "")
