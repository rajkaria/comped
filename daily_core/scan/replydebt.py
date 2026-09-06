"""reply-debt: who asked you something and never got an answer.

WHY THIS MODULE NEVER TOUCHES A MAILBOX
---------------------------------------
`daily_core` is proven offline by a static test: no module in the package may import a networking
module of any kind, and none may start a process. That proof is the most valuable claim these
Plays make, and a mail Play must not be the exception that quietly retires it. So the work is
split across the two planes the Play already has:

    the Play's mail step (TypeScript, in the presentation plane)   ->  talks to the mail adapter
    this module (Python, in daily_core)                            ->  only ever reads a file

The mail step writes ONE normalised JSON file into `out_dir` and exits. Everything below reads
that file and computes. If the file is not there, that is a labelled miss saying the mail step has
not run — never an exception, and never an attempt to go and get the data itself.

Nothing here composes a message, saves a draft, or transmits anything. The only writes in this
module go through `common.baseline_write`, which resolves under the caller's `out_dir`.

THE PARTIAL'S SCHEMA (version 1)
--------------------------------
The mail step is generated against exactly this shape. Every field except `thread_id` and
`messages` is optional; anything missing degrades to "unknown" rather than to a crash.

    {
      "schema": 1,
      "account": "you@example.com",          # optional, the mailbox that was read
      "me": ["you@example.com", "you@work.example"],   # optional, all of your own addresses
      "generated": "2026-09-05T12:00:00Z",   # optional, when the mail step ran
      "truncated": false,                    # optional, true when the adapter paged out
      "threads": [
        {
          "thread_id": "t-0001",             # required, stable across runs
          "subject": "Contract redlines",    # optional, thread-level subject
          "labels": ["INBOX"],               # optional, thread-level labels
          "participants": [                  # optional; a dict or "Name <addr>" both parse
            {"name": "Dana Okoye", "email": "dana@example.com"},
            "You <you@example.com>"
          ],
          "messages": [                      # required, one entry per message, any order
            {
              "from": {"name": "Dana Okoye", "email": "dana@example.com"},
              "to":   [{"name": "You", "email": "you@example.com"}],
              "cc":   [],
              "date": "2026-06-04T09:12:00Z",        # ISO 8601; anything parse_date accepts
              "direction": "inbound",                # "inbound" | "outbound"; inferred from `me`
              "subject": "Contract redlines",
              "snippet": "Could you send the signed copy by Friday?",
              "labels": ["INBOX", "IMPORTANT"],
              "is_automated": false,                 # adapter hint, used for exclusions
              "list_id": "",                         # List-Id header, when the adapter has it
              "list_unsubscribe": "",                # List-Unsubscribe header
              "is_calendar": false                   # a calendar invite part was present
            }
          ]
        }
      ]
    }

A bare list of threads at the top level is accepted too, so a minimal adapter can emit just that.
`snippet` is whatever body text the adapter can supply — a Gmail snippet, a first-part plain-text
body, anything. Quoted history inside it is stripped here, not there.
"""
import hashlib
import json
import re
from collections import Counter

from ..card import Card, bucket_bars, legend, pad, tier_bar
from ..common import (Budget, Source, age_days, ago, baseline_read, baseline_write, day, delta,
                      ellipsis, expand, iso, parse_date, pct, plural, read_text, redact_name,
                      since_note, trunc)

SCHEMA = 1
DEMO_FILE = "mailbox.json"
NAME = "reply-debt"

NOT_RUN = ("the mail step has not run: no normalised mail partial to read. reply-debt computes "
           "only from that file and never fetches mail itself")

PROMISE = ("Read-only by construction. reply-debt reads one JSON file the mail step already "
           "wrote and computes from it. It never composes a message, never saves a draft, never "
           "marks anything read and never transmits anything anywhere.")

DIRECT, IMPLIED, FYI = "direct ask", "FYI with an implied action", "pure FYI"
CLASSES = (DIRECT, IMPLIED, FYI)


# ---------------------------------------------------------------- the rule, written down once
#
# Every phrase this module matches on is listed here, and the report prints the whole table. A
# heuristic nobody can read is a heuristic nobody can argue with, and this one WILL be wrong about
# somebody's mail; the least it can do is show its working.

QUESTION_RULE = "a question mark surviving quote-stripping"

MODALS = (
    "could you", "can you", "would you mind", "would you be able", "would you",
    "are you able", "will you", "do you have time", "do you have a moment",
    "do you have bandwidth", "any chance you", "mind taking a look", "mind having a look",
)

REQUESTS = (
    "please send", "please share", "please review", "please confirm", "please let me know",
    "please advise", "let me know", "any update", "thoughts?", "circling back", "following up",
    "gentle reminder", "just checking in", "waiting on you", "need your", "your input",
    "your thoughts", "sign off", "action required", "get back to me", "look forward to hearing",
)

DEADLINES = (
    r"by (?:mon|tues|wednes|thurs|fri|satur|sun)day", r"by tomorrow", r"by today", r"by noon",
    r"by the end of (?:the )?(?:day|week|month)", r"end of day", r"end of week", r"\beod\b",
    r"\beow\b", r"before the (?:call|meeting|standup|stand-up|review|deadline|demo)",
    r"\bdeadline\b", r"\basap\b", r"no later than", r"by \d{1,2}(?:st|nd|rd|th)?\b",
    r"by next week", r"this week", r"time-sensitive",
)

IMPLIED_PHRASES = (
    "for your review", "for review", "for your records", "for approval", "for sign-off",
    "when you get a chance", "when you have a moment", "at your convenience", "heads up",
    "fyi", "no rush", "keep an eye", "in case you", "just so you know", "for visibility",
    "flagging", "wanted you to see", "over to you",
)

RULE_TEXT = (
    "A thread is debt when the NEWEST message is inbound, it is older than the minimum age, it "
    "was not excluded, and its unanswered run carries an ask.",
    "The unanswered run is every inbound message newer than your last reply, plus that message's "
    "subject line.",
    "Quoted history is removed before anything is matched: lines beginning with '>', everything "
    "from an 'On ... wrote:' attribution onwards, forwarded-message and Original-Message "
    "dividers, the Outlook rule line, and anything after a '-- ' signature marker.",
    "direct ask = any question / modal / request signal. FYI with an implied action = no direct "
    "signal but a deadline or an implied-action phrase. pure FYI = none of those, and it is NOT "
    "counted as debt.",
)


def rule() -> dict:
    """The whole ask-detection rule as data, so the report can print it and a test can assert it."""
    return {
        "headline": "How reply-debt decides something is an ask",
        "statements": list(RULE_TEXT),
        "signals": [
            {"name": "question", "description": QUESTION_RULE, "phrases": ["?"]},
            {"name": "modal", "description": "second-person modals", "phrases": list(MODALS)},
            {"name": "request", "description": "request verbs", "phrases": list(REQUESTS)},
            {"name": "deadline", "description": "a deadline phrase", "phrases": list(DEADLINES)},
            {"name": "implied", "description": "an implied-action phrase",
             "phrases": list(IMPLIED_PHRASES)},
        ],
        "classes": [
            {"name": DIRECT, "rule": "question or modal or request", "counts_as_debt": True},
            {"name": IMPLIED, "rule": "no direct signal, but deadline or implied-action phrase",
             "counts_as_debt": True},
            {"name": FYI, "rule": "no signal at all", "counts_as_debt": False},
        ],
    }


# ---------------------------------------------------------------- quoted history

_QUOTE_LINE = re.compile(r"^\s*>")
_SIGNATURE = re.compile(r"\n--\s*\n")
_CUT_MARKERS = tuple(re.compile(p, re.I | re.S) for p in (
    r"\bon\b.{0,300}?\bwrote:",                    # Gmail / Apple Mail attribution, may wrap
    r"-{2,}\s*original message\s*-{2,}",           # Outlook, classic
    r"\bbegin forwarded message:",                 # Apple Mail forward
    r"-{2,}\s*forwarded message\s*-{2,}",          # Gmail forward
    r"\n_{10,}\n",                                 # Outlook's horizontal rule above the quote
    r"\nfrom:.{0,200}?\n(?:sent|date):",           # Outlook header block
))


def strip_quotes(text: str) -> str:
    """Remove quoted history, then collapse whitespace.

    This is the single most common way an ask heuristic goes wrong: the question mark that makes a
    thread "urgent" turns out to be the recipient quoting a question they already answered. Cutting
    at the attribution line first and only then dropping '>' lines handles both the clients that
    quote with markers and the ones that quote with indentation.
    """
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cut = len(t)
    for pattern in _CUT_MARKERS:
        m = pattern.search(t)
        if m and m.start() < cut:
            cut = m.start()
    t = t[:cut]
    t = "\n".join(line for line in t.split("\n") if not _QUOTE_LINE.match(line))
    t = _SIGNATURE.split(t)[0]
    return " ".join(t.split())


# ---------------------------------------------------------------- signals

def _phrase(p: str) -> str:
    return r"\b" + re.escape(p)


_MODAL_RE = re.compile("|".join(_phrase(p) for p in MODALS), re.I)
_REQUEST_RE = re.compile("|".join(_phrase(p) for p in REQUESTS), re.I)
_DEADLINE_RE = re.compile("|".join(DEADLINES), re.I)
_IMPLIED_RE = re.compile("|".join(_phrase(p) for p in IMPLIED_PHRASES), re.I)


def signals(text: str) -> list:
    """Which named signals the (already quote-stripped) text carries. Sorted, so runs compare."""
    found = []
    if "?" in text:
        found.append("question")
    if _MODAL_RE.search(text):
        found.append("modal")
    if _REQUEST_RE.search(text):
        found.append("request")
    if _DEADLINE_RE.search(text):
        found.append("deadline")
    if _IMPLIED_RE.search(text):
        found.append("implied")
    return sorted(found)


def classify(found) -> str:
    s = set(found or ())
    if s & {"question", "modal", "request"}:
        return DIRECT
    if s & {"deadline", "implied"}:
        return IMPLIED
    return FYI


# ---------------------------------------------------------------- exclusions

_NOREPLY = re.compile(
    r"(?:^|[._+-])(?:no-?reply|do-?not-?reply|donotreply|mailer-daemon|bounces?|notification[s]?|"
    r"automated|automation|alerts?|postmaster|noc|robot|bot|system|updates?|digest)(?:[._+-]|$)",
    re.I)
_CALENDAR_SUBJECT = re.compile(
    r"^\s*(?:updated )?(?:invitation|invite|accepted|declined|tentative|canceled|cancelled|"
    r"new time proposed)\s*:", re.I)
_LIST_LABELS = {"category_promotions", "category_forums", "category_social", "newsletter", "list"}
_CALENDAR_LABELS = {"category_calendar", "calendar", "invite"}

REASONS = ("mailing list", "calendar invite", "no-reply sender", "automated notification")


def exclusion(thread: dict) -> str:
    """Why this thread is not a person waiting on you, or "" when it is. Order is deliberate.

    A calendar invite usually arrives from a real colleague's address, so it must be tested before
    the no-reply rule; a newsletter is a mailing list even when a human's name is on it.
    """
    messages = thread.get("messages") or []
    last = messages[-1] if messages else {}
    labels = set(str(l).lower() for l in (thread.get("labels") or []))
    labels |= set(str(l).lower() for l in (last.get("labels") or []))
    if last.get("list_id") or last.get("list_unsubscribe") or (labels & _LIST_LABELS):
        return "mailing list"
    subject = str(last.get("subject") or thread.get("subject") or "")
    if last.get("is_calendar") or (labels & _CALENDAR_LABELS) or _CALENDAR_SUBJECT.match(subject):
        return "calendar invite"
    local = str((last.get("from") or {}).get("email") or "").split("@")[0]
    if local and _NOREPLY.search(local):
        return "no-reply sender"
    if last.get("is_automated"):
        return "automated notification"
    return ""


# ---------------------------------------------------------------- normalising the partial

_ADDR = re.compile(r"^\s*(?:\"?(?P<name>[^\"<]*?)\"?\s*)?<(?P<email>[^>]+)>\s*$")


def person(value) -> dict:
    """{"name", "email"} from either a dict or a "Name <addr>" string. Never raises."""
    if isinstance(value, dict):
        name = " ".join(str(value.get("name") or "").split())
        email = str(value.get("email") or value.get("address") or "").strip().lower()
    else:
        s = " ".join(str(value or "").split())
        m = _ADDR.match(s)
        if m:
            name, email = (m.group("name") or "").strip(), m.group("email").strip().lower()
        elif "@" in s:
            name, email = "", s.lower()
        else:
            name, email = s, ""
    if not name and email:
        name = email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ").title()
    return {"name": name, "email": email}


def _people(values) -> list:
    if isinstance(values, (list, tuple)):
        return [person(v) for v in values]
    return [person(values)] if values else []


def normalise(thread: dict, me=()) -> dict:
    """One thread in the shape the rest of this module expects. Idempotent, so it can run twice."""
    mine = set(str(a).strip().lower() for a in (me or ()) if str(a).strip())
    messages = []
    for i, raw in enumerate(thread.get("messages") or []):
        sender = person(raw.get("from"))
        direction = str(raw.get("direction") or "").strip().lower()
        if direction not in ("inbound", "outbound"):
            direction = "outbound" if (sender["email"] and sender["email"] in mine) else "inbound"
        elif mine and sender["email"]:
            direction = "outbound" if sender["email"] in mine else "inbound"
        when = parse_date(raw.get("date") or "")
        messages.append({
            "from": sender,
            "to": _people(raw.get("to")),
            "cc": _people(raw.get("cc")),
            "date": iso(when),
            "direction": direction,
            "subject": " ".join(str(raw.get("subject") or "").split()),
            "snippet": str(raw.get("snippet") or raw.get("body") or ""),
            "labels": sorted(str(l) for l in (raw.get("labels") or [])),
            "is_automated": bool(raw.get("is_automated")),
            "is_calendar": bool(raw.get("is_calendar")),
            "list_id": str(raw.get("list_id") or ""),
            "list_unsubscribe": str(raw.get("list_unsubscribe") or ""),
            "_order": i,
        })
    messages.sort(key=lambda m: (m["date"] or "", m["_order"]))
    for m in messages:
        m.pop("_order", None)
    return {
        "thread_id": str(thread.get("thread_id") or thread.get("id") or ""),
        "subject": " ".join(str(thread.get("subject")
                                or (messages[-1]["subject"] if messages else "")).split()),
        "labels": sorted(str(l) for l in (thread.get("labels") or [])),
        "participants": _people(thread.get("participants")),
        "messages": messages,
    }


# ---------------------------------------------------------------- reading

def read_source(source, budget: Budget, cfg: dict) -> tuple:
    """(sources, threads). Loads the partial the mail step wrote; reads nothing else, ever."""
    cfg = cfg or {}
    label = str(source or "mail")
    if cfg.get("demo_root"):
        path = expand(cfg["demo_root"]) / DEMO_FILE
        src = Source(name="{0} (demo)".format(label), path=str(path))
        ok_note = "bundled fixture mailbox"
    else:
        configured = cfg.get("partial") or ""
        if not configured:
            return [Source(name=label).miss(NOT_RUN)], []
        path = expand(configured)
        src = Source(name=label, path=str(path))
        ok_note = "normalised mail partial"

    if not path.is_file():
        return [src.miss(NOT_RUN)], []
    raw = read_text(path, 32 * 1024 * 1024)
    budget.spend(len(raw))
    if not raw.strip():
        return [src.miss("the mail partial is empty")], []
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return [src.miss("the mail partial is not valid JSON ({0})".format(exc))], []

    if isinstance(doc, list):
        doc = {"threads": doc}
    if not isinstance(doc, dict):
        return [src.miss("the mail partial is not an object or a list")], []
    version = doc.get("schema", SCHEMA)
    if version != SCHEMA:
        return [src.miss("mail partial schema {0}, this build reads {1}".format(version, SCHEMA))], []

    me = list(doc.get("me") or ([doc["account"]] if doc.get("account") else []))
    raw_threads = doc.get("threads") or []
    threads = [normalise(t, me) for t in raw_threads if isinstance(t, dict)]
    threads = [t for t in threads if t["thread_id"] and t["messages"]]
    threads.sort(key=lambda t: t["thread_id"])
    dropped = len(raw_threads) - len(threads)
    notes = [ok_note]
    if me:
        notes.append("{0} own address(es)".format(len(me)))
    if dropped > 0:
        notes.append("{0} thread(s) had no id or no message".format(dropped))
    if doc.get("truncated"):
        notes.append("the mail step paged out; this is a lower bound")
    return [src.hit(len(threads), "; ".join(notes))], threads


# ---------------------------------------------------------------- analysis

def _run_after_last(messages: list, direction: str) -> list:
    """The trailing run of `direction` messages: everything since the other side last spoke."""
    run = []
    for m in reversed(messages):
        if m["direction"] != direction:
            break
        run.append(m)
    return list(reversed(run))


def _text_of(run: list) -> str:
    parts = []
    for m in run:
        if m["subject"]:
            parts.append(m["subject"])
        body = strip_quotes(m["snippet"])
        if body:
            parts.append(body)
    return " ".join(parts)


def _hash(subject: str) -> str:
    return "#" + hashlib.sha256(str(subject or "").encode("utf-8")).hexdigest()[:8]


def _row(thread: dict, last, run: list, now, klass: str, found: list, redact: bool) -> dict:
    subject = thread["subject"] or last["subject"]
    who = last["from"]
    days = age_days(parse_date(last["date"]), now)
    return {
        "thread_id": thread["thread_id"],
        "card_subject": _hash(subject),
        "subject": _hash(subject) if redact else trunc(subject, 60),
        "subject_hash": _hash(subject),
        "person": redact_name(who["name"] or who["email"], redact),
        "person_key": who["email"] or (who["name"] or "").lower(),
        "domain": who["email"].split("@")[-1] if "@" in who["email"] else "",
        "last": last["date"],
        "last_day": day(parse_date(last["date"])),
        "age_days": days if days is not None else 0,
        "age": ago(parse_date(last["date"]), now),
        "class": klass,
        "signals": found,
        "messages": len(thread["messages"]),
        "unanswered": len(run),
    }


ORDER = {DIRECT: 0, IMPLIED: 1, FYI: 2}


def _sort_key(r: dict) -> tuple:
    return (-r["age_days"], ORDER.get(r["class"], 9), r["person_key"], r["thread_id"])


BUCKETS = ((7, "under a week"), (14, "1-2 weeks"), (30, "2-4 weeks"), (90, "1-3 months"),
           (10 ** 9, "older"))

WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve")


def word(n: int) -> str:
    return WORDS[n] if 0 <= int(n) < len(WORDS) else str(n)


def analyse(threads: list, now, cfg: dict) -> dict:
    cfg = cfg or {}
    redact = cfg.get("redact", True)
    min_age = int(cfg.get("min_age_days", 3))
    cold_days = int(cfg.get("cold_days", 30))
    me = cfg.get("me") or ()

    prepared = sorted((normalise(t, me) for t in (threads or []) if isinstance(t, dict)),
                      key=lambda t: t["thread_id"])

    excluded = Counter()
    awaiting, fyi_rows, owed, too_recent = [], [], [], 0

    for thread in prepared:
        messages = thread["messages"]
        if not messages:
            continue
        reason = exclusion(thread)
        if reason:
            excluded[reason] += 1
            continue
        last = messages[-1]
        days = age_days(parse_date(last["date"]), now)
        days = 0 if days is None else days

        if last["direction"] == "inbound":
            run = _run_after_last(messages, "inbound")
            found = signals(_text_of(run))
            klass = classify(found)
            row = _row(thread, last, run, now, klass, found, redact)
            if klass == FYI:
                fyi_rows.append(row)
            elif days < min_age:
                too_recent += 1
            else:
                awaiting.append(row)
        else:
            # The other side of the ledger. A thread whose newest message is yours, carrying a
            # direct ask nobody answered, is a debt owed TO you — without it this Play would be
            # nothing but an instrument of guilt.
            run = _run_after_last(messages, "outbound")
            found = signals(_text_of(run))
            if classify(found) == DIRECT and days >= min_age:
                other = None
                for m in reversed(messages):
                    if m["direction"] == "inbound":
                        other = m["from"]
                        break
                if other is None:
                    other = (last["to"] or [{"name": "", "email": ""}])[0]
                row = _row(thread, last, run, now, DIRECT, found, redact)
                row["person"] = redact_name(other["name"] or other["email"], redact)
                row["person_key"] = other["email"] or (other["name"] or "").lower()
                owed.append(row)

    awaiting.sort(key=_sort_key)
    fyi_rows.sort(key=_sort_key)
    owed.sort(key=_sort_key)

    direct = [r for r in awaiting if r["class"] == DIRECT]
    implied = [r for r in awaiting if r["class"] == IMPLIED]
    cold = [r for r in awaiting if r["age_days"] >= cold_days]

    counts = [0] * len(BUCKETS)
    for r in awaiting:
        for i, (edge, _label) in enumerate(BUCKETS):
            if r["age_days"] < edge:
                counts[i] += 1
                break

    senders = _cluster(awaiting, cold_days)
    repeat = [s for s in senders if s["threads"] >= 2]
    top = senders[0] if senders and senders[0]["threads"] >= 2 else None

    payload = dict((r["thread_id"], r["age_days"]) for r in awaiting)
    baseline = cfg.get("baseline")
    if baseline is None:
        baseline = baseline_read(cfg["out_dir"], NAME) if cfg.get("out_dir") else {}
    moved = delta(payload, (baseline or {}).get("payload") or {})

    oldest = awaiting[0] if awaiting else None
    headline = _headline(len(direct), oldest, top)
    subhead = "{0} more {1} an implied action; {2} need no reply at all.".format(
        len(implied), "carries" if len(implied) == 1 else "carry", len(fyi_rows))

    return {
        "schema": SCHEMA,
        "threads_seen": len(prepared),
        "excluded": sum(excluded.values()),
        "exclusions": [{"reason": r, "threads": excluded[r]} for r in REASONS if excluded[r]],
        "considered": len(prepared) - sum(excluded.values()),
        "too_recent": too_recent,
        "min_age_days": min_age,
        "cold_days": cold_days,
        "debt": len(awaiting),
        "direct": len(direct),
        "implied": len(implied),
        "fyi": len(fyi_rows),
        "classes": [{"name": DIRECT, "threads": len(direct)},
                    {"name": IMPLIED, "threads": len(implied)},
                    {"name": FYI, "threads": len(fyi_rows)}],
        "awaiting": awaiting,
        "fyi_threads": fyi_rows,
        "oldest": oldest,
        "buckets": [{"label": label, "threads": c} for (_edge, label), c in zip(BUCKETS, counts)],
        "cold": len(cold),
        "cold_share": pct(len(cold), len(awaiting)),
        "cold_threads": cold,
        "senders": senders,
        "repeat_senders": repeat,
        "top_sender": top,
        "reciprocity": {
            "threads": len(owed),
            "oldest_days": owed[0]["age_days"] if owed else 0,
            "oldest": owed[0] if owed else None,
            "items": owed,
            "note": "threads where you asked and nobody has come back to you",
        },
        # On a first run every thread is technically "added"; reporting that as "23 new" would be
        # a lie dressed as a delta, so the first run reports no movement and says why.
        "delta": {
            "new": 0 if moved["first_run"] else len(moved["added"]),
            "cleared": 0 if moved["first_run"] else len(moved["removed"]),
            "net": 0 if moved["first_run"] else len(moved["added"]) - len(moved["removed"]),
            "first_run": moved["first_run"],
            "since": since_note(baseline or {}, now),
        },
        "baseline_payload": payload,
        "rule": rule(),
        "headline": headline,
        "subhead": subhead,
        "redacted": bool(redact),
        "promise": PROMISE,
    }


def _cluster(rows: list, cold_days: int) -> list:
    """Four threads from one person is one relationship, not four tasks. Group, then rank."""
    groups = {}
    for r in rows:
        groups.setdefault(r["person_key"], []).append(r)
    out = []
    for key in sorted(groups):
        group = sorted(groups[key], key=_sort_key)
        out.append({
            "person": group[0]["person"],
            "person_key": key,
            "domain": group[0]["domain"],
            "threads": len(group),
            "direct": sum(1 for r in group if r["class"] == DIRECT),
            "implied": sum(1 for r in group if r["class"] == IMPLIED),
            "oldest_days": group[0]["age_days"],
            "oldest": group[0]["age"],
            "cold": sum(1 for r in group if r["age_days"] >= cold_days),
            "thread_ids": sorted(r["thread_id"] for r in group),
        })
    out.sort(key=lambda s: (-s["threads"], -s["oldest_days"], s["person_key"]))
    return out


def _headline(direct: int, oldest, top) -> str:
    bits = ["{0} awaiting your reply.".format(plural(direct, "thread"))]
    if oldest:
        bits.append("Oldest {0}.".format(plural(oldest["age_days"], "day")))
    if top:
        bits.append("{0} from the same person.".format(word(top["threads"]).capitalize()))
    return " ".join(bits)


def write_baseline(view: dict, cfg: dict) -> str:
    """Record this run so tomorrow's can say what moved. The only write this module performs."""
    return baseline_write(cfg["out_dir"], NAME, view["baseline_payload"], cfg["now"])


# ---------------------------------------------------------------- presentation

def _wrap_lines(text: str, width: int) -> list:
    """Word-wrap without losing a word to an ellipsis: the headline is the whole point of the card."""
    lines, line = [], ""
    for w in str(text).split():
        candidate = (line + " " + w) if line else w
        if len(candidate) > width and line:
            lines.append(line)
            line = w
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def render(view: dict, cfg: dict) -> str:
    v, cfg = view, (cfg or {})
    c = Card("REPLY DEBT", "{0} thread(s) seen".format(v["threads_seen"]), cfg.get("color"))
    c.blank()
    for line in _wrap_lines(v["headline"], 60):
        c.row(*c.paint(line, "1;33"))
    c.wrap(v["subhead"])
    c.blank()

    tiers = [(t["name"], t["threads"]) for t in v["classes"]]
    bar = tier_bar(tiers, 40)
    if bar:
        c.row(bar)
        c.row(legend(tiers))

    if v["awaiting"]:
        c.rule("OLDEST FIRST")
        for r in v["awaiting"][:6]:
            # The card never carries a subject line, redacted or not: a card is the thing that
            # gets screenshotted. The hash is enough to match a row against the report.
            c.row("{0}{1}{2}{3}".format(pad(ellipsis(r["age"], 5), 6),
                                        pad(ellipsis(r["person"], 15), 16),
                                        pad(r["card_subject"], 11), r["class"]))
        if len(v["awaiting"]) > 6:
            c.row("… and {0} more".format(len(v["awaiting"]) - 6))

        c.rule("BY AGE")
        for line in bucket_bars([b["threads"] for b in v["buckets"]],
                                [b["label"] for b in v["buckets"]], 18):
            c.row(line)
        if v["cold"]:
            c.row("{0} gone cold ({1}+ days, {2}% of the debt)".format(
                v["cold"], v["cold_days"], v["cold_share"]))

    if v["repeat_senders"]:
        c.rule("ONE PERSON, SEVERAL THREADS")
        for s in v["repeat_senders"][:4]:
            c.row("{0}{1}{2}".format(pad(ellipsis(s["person"], 21), 22),
                                     pad(plural(s["threads"], "thread"), 12),
                                     "oldest {0}".format(s["oldest"])))

    c.rule("THE OTHER SIDE OF THE LEDGER")
    rec = v["reciprocity"]
    if rec["threads"]:
        c.wrap("{0} where you asked and got nothing back. Oldest {1}.".format(
            plural(rec["threads"], "thread"), plural(rec["oldest_days"], "day")))
    else:
        c.wrap("Nobody owes you a reply: every thread you ended with a question got an answer.")

    c.rule("SINCE LAST RUN")
    d = v["delta"]
    if d["first_run"]:
        c.row(d["since"])
    else:
        c.row("{0} new {1}, {2} cleared.".format(d["new"], d["since"], d["cleared"]))

    c.blank()
    excl = ", ".join("{0} {1}".format(e["threads"], e["reason"]) for e in v["exclusions"])
    c.wrap("{0} excluded from the denominator{1}. {2} newer than {3} days.".format(
        v["excluded"], " ({0})".format(excl) if excl else "", v["too_recent"], v["min_age_days"]))
    c.wrap("Read-only: nothing was composed, saved or transmitted.")
    return c.close()


def report_markdown(view: dict, cfg: dict, sources: list) -> str:
    v = view
    r = v["rule"]
    L = ["# Reply debt", "", v["headline"], "", v["subhead"], "",
         "| measure | value |", "|---|---|",
         "| threads in the partial | {0} |".format(v["threads_seen"]),
         "| excluded | {0} |".format(v["excluded"]),
         "| considered | {0} |".format(v["considered"]),
         "| newer than {0} days | {1} |".format(v["min_age_days"], v["too_recent"]),
         "| awaiting your reply | {0} |".format(v["debt"]),
         "| {0} | {1} |".format(DIRECT, v["direct"]),
         "| {0} | {1} |".format(IMPLIED, v["implied"]),
         "| {0} | {1} |".format(FYI, v["fyi"]),
         "| gone cold ({0}+ days) | {1} ({2}%) |".format(v["cold_days"], v["cold"], v["cold_share"]),
         "| people involved | {0} |".format(len(v["senders"])),
         "| threads owed to you | {0} |".format(v["reciprocity"]["threads"]), "",
         "## " + r["headline"], ""]
    L += ["- {0}".format(s) for s in r["statements"]]
    L += ["", "| signal | what it means | what it matches |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], s["description"],
                                       ", ".join("`{0}`".format(p) for p in s["phrases"]))
          for s in r["signals"]]
    L += ["", "| class | rule | counted as debt |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(k["name"], k["rule"], "yes" if k["counts_as_debt"] else "no")
          for k in r["classes"]]

    L += ["", "## Oldest first", "", "| age | from | thread | class | signals | messages |",
          "|---|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} | {4} | {5} |".format(
        x["age"], x["person"], x["subject"], x["class"], ", ".join(x["signals"]) or "—",
        x["messages"]) for x in v["awaiting"]] or ["| — | — | nothing awaiting a reply | — | — | — |"]

    L += ["", "## By age", "", "| bucket | threads |", "|---|---|"]
    L += ["| {0} | {1} |".format(b["label"], b["threads"]) for b in v["buckets"]]

    L += ["", "## One person, several threads", "",
          "Four threads from one person is one relationship, not four tasks.", "",
          "| person | threads | direct | implied | oldest | cold |", "|---|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3} | {4} | {5} |".format(
        s["person"], s["threads"], s["direct"], s["implied"], s["oldest"], s["cold"])
        for s in v["senders"]] or ["| — | — | — | — | — | — |"]

    rec = v["reciprocity"]
    L += ["", "## The other side of the ledger", "", rec["note"] + ".", ""]
    if rec["threads"]:
        L += ["| age | to | thread | signals |", "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(x["age"], x["person"], x["subject"],
                                                 ", ".join(x["signals"]) or "—")
              for x in rec["items"]]
    else:
        L += ["Nobody owes you a reply."]

    L += ["", "## FYI, no reply needed", "",
          "{0} thread(s) ended with an inbound message carrying no ask at all.".format(v["fyi"]), ""]
    if v["fyi_threads"]:
        L += ["| age | from | thread |", "|---|---|---|"]
        L += ["| {0} | {1} | {2} |".format(x["age"], x["person"], x["subject"])
              for x in v["fyi_threads"]]

    L += ["", "## What was excluded, and why", "",
          "The denominator is only honest if the exclusions are printed. "
          "{0} of {1} thread(s) were left out:".format(v["excluded"], v["threads_seen"]), "",
          "| reason | threads |", "|---|---|"]
    L += ["| {0} | {1} |".format(e["reason"], e["threads"]) for e in v["exclusions"]] or \
         ["| — | 0 |"]

    d = v["delta"]
    L += ["", "## Since last run", "",
          d["since"] if d["first_run"] else
          "{0} new {1}, {2} cleared (net {3:+d}).".format(d["new"], d["since"], d["cleared"], d["net"])]

    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "")
          for s in (sources or [])]
    L += ["", PROMISE, "",
          "Subjects are {0}.".format("hashed, never printed" if v["redacted"]
                                     else "printed here in full, and never on the card"), ""]
    return "\n".join(L)
