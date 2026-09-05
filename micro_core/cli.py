"""One entry point for twelve Plays.

A Play that remembers is two steps, `record` then `report`, and the state file is what they share.
A Play that is a pure function is one `report` step: giving it a second step would mean inventing a
scratch file for the halves to talk through, and a Play that claims to write nothing should not
write a file to prove it.
"""
import argparse
import calendar
import re
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

if __name__ == "__main__" and __package__ is None:      # invoked as a file path from a Play step
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "micro_core"

from . import common, store

PLAYS = ("whatis", "fits", "secret", "cron", "punch", "spent", "jot", "streak",
         "last-turn", "budget", "since-last", "staged")

DEFAULT_STATE_DIR = "~/.rote-micro"


def _parser(prog, *specs):
    """Every step parses `now` and `demo`; the rest is whatever that step actually varies on."""
    p = argparse.ArgumentParser(prog=prog, add_help=False)
    for name, default in specs:
        p.add_argument("--" + name.replace("_", "-"), dest=name, default=default)
    p.add_argument("--now", dest="now", default="")
    p.add_argument("--demo", dest="demo", default="false")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in PLAYS:
        sys.stderr.write("usage: cli.py <{0}> <step> [options]\n".format("|".join(PLAYS)))
        return 2
    play, step, rest = argv[0], argv[1], argv[2:]
    handler = _DISPATCH.get((play, step))
    if handler is None:
        sys.stderr.write("unknown step: {0} {1}\n".format(play, step))
        return 2
    return handler(rest)


# ---------------------------------------------------------------- demo

def _state_dir(a, streams=()):
    """A demo run must never touch your own log: it copies the fixture into a temp dir first."""
    if not common.as_bool(getattr(a, "demo", "false")):
        return common.expand(a.state_dir), None
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="rote-micro-demo-"))
    src = common.fixtures_dir() / "log"
    for stream in streams:
        f = src / "{0}.jsonl".format(stream)
        if f.exists():
            shutil.copy2(str(f), str(tmp / f.name))
    return tmp, str(tmp)


def _demo_note(demo_dir):
    return "" if not demo_dir else "demo run: reading a bundled 14-day log in {0}\n".format(demo_dir)


# ---------------------------------------------------------------- punch

def _topic(note, tag):
    """What you called it, reduced to something two punches can be compared on."""
    if str(tag or "").strip():
        return str(tag).strip().lower()
    words = re.sub(r"[^\w\s-]", " ", str(note or "").lower()).split()
    return "-".join(words[:2]) if words else "unlabelled"


def _blocks(entries, now, tz):
    """(switches, current block minutes, longest block minutes) across one local day.

    A block is a run of punches on the same topic; it ends when the topic changes, and the last
    block of the day is still open, so it is measured against now rather than against nothing.
    """
    if not entries:
        return (0, 0, 0)
    topics = [e.data.get("topic") or "unlabelled" for e in entries]
    switches = sum(1 for a, b in zip(topics, topics[1:]) if a != b)
    edges = [e.t for e in entries] + [now]
    longest, start = 0, 0
    for i in range(1, len(edges)):
        if i == len(edges) - 1 or topics[i] != topics[start]:
            longest = max(longest, int((edges[i] - edges[start]).total_seconds() // 60))
            start = i
    current = max(0, int((now - entries[-1].t).total_seconds() // 60))
    return (switches, current, longest)


def _punch_record(argv):
    a = _parser("punch record", ("note", ""), ("tag", ""), ("state_dir", DEFAULT_STATE_DIR)).parse_args(argv)
    now = common.now_utc(a.now)
    if not str(a.note or "").strip() and not str(a.tag or "").strip():
        return common.emit("Nothing to record — pass note='what you are doing now'.",
                           {"ok": True, "recorded": False, "written": None})
    state, demo_dir = _state_dir(a, ("punch",))
    written = store.append(state, "punch", {"t": common.iso(now), "note": str(a.note).strip(),
                                            "tag": str(a.tag).strip(), "topic": _topic(a.note, a.tag)})
    return common.emit("punched at {0} — {1}".format(common.hhmm(now), a.note or a.tag),
                       {"ok": True, "recorded": True, "written": written})


def _punch_report(argv):
    a = _parser("punch report", ("state_dir", DEFAULT_STATE_DIR), ("days_back", "14"), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    state, demo_dir = _state_dir(a, ("punch",))
    entries = store.read(state, "punch")
    if not entries:
        return common.emit("No punches yet. Run it with note='what you are doing' and it starts counting.",
                           common.warn("no punches recorded yet"))
    days = store.days_with_entries(entries, tz)
    today = common.day(now, tz)
    mine = [e for e in entries if common.day(e.t, tz) == today]
    switches, current, longest = _blocks(mine, now, tz)
    back = max(1, int(a.days_back))
    buckets = store.by_day(entries, tz)
    counts = [len(buckets.get(common.day(now - timedelta(days=i), tz), [])) for i in range(back - 1, -1, -1)]
    cur_streak, best_streak = store.streak(days, today)
    tops = {}
    for e in mine:
        tops[e.data.get("topic", "unlabelled")] = tops.get(e.data.get("topic", "unlabelled"), 0) + 1
    ranked = sorted(tops.items(), key=lambda kv: (-kv[1], kv[0]))
    lines = [_demo_note(demo_dir) + common.rule("today")]
    for e in mine:
        lines.append("  {0}  {1}".format(common.hhmm(e.t, tz),
                                         common.trunc(e.data.get("note") or e.data.get("topic", ""), 48)))
    if not mine:
        lines.append("  (nothing today yet)")
    lines += ["", "  {0} over {1} days  {2}".format(common.plural(len(entries), "punch", "punches"), back,
                                                    common.sparkline(counts)),
              "", "{0} {1} today · longest block {2} · {3}-day streak".format(
                  switches, common.plural(switches, "switch", "switches"), common.minutes(longest), cur_streak)]
    return common.emit("\n".join(lines),
                       {"ok": True, "punches": len(mine), "switches": switches,
                        "current_block_min": current, "longest_block_min": longest,
                        "streak": cur_streak, "longest_streak": best_streak,
                        "shape": common.sparkline(counts),
                        "topics": [{"topic": t, "punches": n} for t, n in ranked]})


# ---------------------------------------------------------------- spent

def _spent_record(argv):
    a = _parser("spent record", ("entry", ""), ("currency", "USD"),
                ("state_dir", DEFAULT_STATE_DIR)).parse_args(argv)
    now = common.now_utc(a.now)
    if not str(a.entry or "").strip():
        return common.emit("Nothing to record — pass entry='320 lunch'.",
                           {"ok": True, "recorded": False, "written": None})
    try:
        parsed = store.parse_entry(a.entry, a.currency)
    except ValueError as e:
        return common.emit("Could not read that: {0}".format(e),
                           dict(common.warn(str(e)), recorded=False, written=None))
    state, _demo = _state_dir(a, ("spent",))
    written = store.append(state, "spent", {"t": common.iso(now), "amount": store.money(parsed["amount"]),
                                            "currency": parsed["currency"], "label": parsed["label"],
                                            "tag": parsed["tag"]})
    return common.emit("logged {0} {1} — {2}".format(store.money(parsed["amount"]), parsed["currency"],
                                                     parsed["label"]),
                       {"ok": True, "recorded": True, "written": written})


def _spent_report(argv):
    a = _parser("spent report", ("state_dir", DEFAULT_STATE_DIR), ("budget", "0"),
                ("currency", ""), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    state, demo_dir = _state_dir(a, ("spent",))
    entries = store.read(state, "spent")
    if not entries:
        return common.emit("Nothing logged yet. Run it with entry='320 lunch' and it starts adding up.",
                           common.warn("no spend recorded yet"))
    today, month = common.day(now, tz), common.day(now, tz)[:7]
    per_currency = {}
    for e in entries:
        cur = e.data.get("currency", "USD")
        amt = Decimal(str(e.data.get("amount", "0")))
        d = common.day(e.t, tz)
        row = per_currency.setdefault(cur, {"today": Decimal("0"), "month": Decimal("0"),
                                            "all": Decimal("0"), "tags": {}, "n": 0})
        row["all"] += amt
        row["n"] += 1
        if d[:7] == month:
            row["month"] += amt
            row["tags"][e.data.get("tag", "unlabelled")] = row["tags"].get(e.data.get("tag", "unlabelled"),
                                                                          Decimal("0")) + amt
        if d == today:
            row["today"] += amt
    primary = str(a.currency).upper() or max(per_currency, key=lambda c: (per_currency[c]["n"], c))
    row = per_currency.get(primary) or list(per_currency.values())[0]
    elapsed = int(now.astimezone(tz).day)
    days_in_month = calendar.monthrange(now.astimezone(tz).year, now.astimezone(tz).month)[1]
    per_day = row["month"] / Decimal(max(1, elapsed))
    projection = per_day * Decimal(days_in_month)
    budget = Decimal(str(a.budget or "0"))
    ranked = sorted(row["tags"].items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    lines = [_demo_note(demo_dir) + common.rule(month)]
    for tag, amt in ranked:
        share = int(amt * 100 / row["month"]) if row["month"] else 0
        lines.append("  {0:<16} {1:>10} {2:>4}%".format(common.trunc(tag, 16), store.money(amt), share))
    lines += ["", "  today {0} · month {1} · {2}/day".format(store.money(row["today"]), store.money(row["month"]),
                                                             store.money(per_day))]
    for cur, other in sorted(per_currency.items()):
        if cur != primary:
            lines.append("  also {0} {1} this month".format(store.money(other["month"]), cur))
    tail = "{0} {1} this month".format(store.money(row["month"]), primary)
    if ranked and row["month"]:
        tail += " · {0} is {1}%".format(ranked[0][0], int(ranked[0][1] * 100 / row["month"]))
    if budget > 0:
        tail += " · on pace for {0} of {1}".format(store.money(projection), store.money(budget))
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "currency": primary, "today": store.money(row["today"]),
                        "month": store.money(row["month"]), "avg_per_day": store.money(per_day),
                        "projection": store.money(projection), "budget": store.money(budget),
                        "over": bool(budget > 0 and projection > budget),
                        "by_tag": [{"tag": t, "amount": store.money(v)} for t, v in ranked],
                        "currencies": [{"currency": c, "month": store.money(v["month"])}
                                       for c, v in sorted(per_currency.items())]})


# ---------------------------------------------------------------- jot

def _inbox_path(vault_dir, inbox):
    return common.expand(vault_dir) / str(inbox or "Inbox.md")


def _jot_record(argv):
    a = _parser("jot record", ("note", ""), ("vault_dir", ""), ("inbox", "Inbox.md"),
                ("state_dir", DEFAULT_STATE_DIR)).parse_args(argv)
    now = common.now_utc(a.now)
    note = str(a.note or "").strip()
    if not note:
        return common.emit("Nothing to capture — pass note='the thought'.",
                           {"ok": True, "recorded": False, "written": None, "reason": "empty"})
    state, _demo = _state_dir(a, ("jot",))
    recent = store.read(state, "jot", since=now - timedelta(seconds=60))
    if any(e.data.get("note") == note for e in recent):
        return common.emit("Already captured that a moment ago; not writing it twice.",
                           {"ok": True, "recorded": False, "written": None, "reason": "duplicate"})
    written = None
    if str(a.vault_dir or "").strip():
        p = _inbox_path(a.vault_dir, a.inbox)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("# Inbox\n\n", encoding="utf-8")
        with open(str(p), "a", encoding="utf-8") as fh:
            fh.write("- {0} {1}\n".format(common.hhmm(now), note))
        written = str(p)
    store.append(state, "jot", {"t": common.iso(now), "note": note, "written": written})
    return common.emit("captured — {0}".format(common.trunc(note, 60)),
                       {"ok": True, "recorded": True, "written": written})


def _jot_report(argv):
    a = _parser("jot report", ("vault_dir", ""), ("inbox", "Inbox.md"),
                ("state_dir", DEFAULT_STATE_DIR), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    state, demo_dir = _state_dir(a, ("jot",))
    entries = store.read(state, "jot")
    if not entries:
        return common.emit("Nothing captured yet. Run it with note='the thought'.",
                           common.warn("no notes captured yet"))
    days = store.days_with_entries(entries, tz)
    today = common.day(now, tz)
    n_today = len([e for e in entries if common.day(e.t, tz) == today])
    week = len([e for e in entries if e.t >= now - timedelta(days=7)])
    inbox_lines = 0
    if str(a.vault_dir or "").strip():
        p = _inbox_path(a.vault_dir, a.inbox)
        try:
            inbox_lines = len([l for l in p.read_text(encoding="utf-8").split("\n") if l.startswith("- ")])
        except OSError:
            inbox_lines = 0
    cur_streak, best = store.streak(days, today)
    recent = entries[-5:]
    lines = [_demo_note(demo_dir) + common.rule("last captured")]
    for e in recent:
        lines.append("  {0}  {1}".format(common.hhmm(e.t, tz), common.trunc(e.data.get("note", ""), 52)))
    lines += ["", "{0} today · {1} this week · {2} in the inbox · {3}-day streak".format(
        n_today, week, inbox_lines, cur_streak)]
    return common.emit("\n".join(lines),
                       {"ok": True, "today": n_today, "week": week, "inbox_lines": inbox_lines,
                        "streak": cur_streak, "longest_streak": best, "captured": len(entries)})


# ---------------------------------------------------------------- streak

def _streak_record(argv):
    a = _parser("streak record", ("did", ""), ("state_dir", DEFAULT_STATE_DIR)).parse_args(argv)
    now = common.now_utc(a.now)
    habit = re.sub(r"\s+", "-", str(a.did or "").strip().lower())
    if not habit:
        return common.emit("Nothing to mark — pass did='water'.",
                           {"ok": True, "recorded": False, "written": None})
    state, _demo = _state_dir(a, ("streak",))
    written = store.append(state, "streak", {"t": common.iso(now), "habit": habit})
    return common.emit("marked {0} for {1}".format(habit, common.day(now)),
                       {"ok": True, "recorded": True, "written": written})


def _streak_report(argv):
    a = _parser("streak report", ("state_dir", DEFAULT_STATE_DIR), ("window", "21"),
                ("did", ""), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    state, demo_dir = _state_dir(a, ("streak",))
    entries = store.read(state, "streak")
    if not entries:
        return common.emit("No habits marked yet. Run it with did='water' and it starts counting.",
                           common.warn("no habits recorded yet"))
    window = max(7, int(a.window))
    today = common.day(now, tz)
    per_habit = {}
    for e in entries:
        per_habit.setdefault(e.data.get("habit", "unnamed"), set()).add(common.day(e.t, tz))
    rows = []
    for name in sorted(per_habit):
        cur, best = store.streak(per_habit[name], today)
        rows.append({"name": name, "current": cur, "longest": best,
                     "grid": store.grid(per_habit[name], today, window),
                     "worst_weekday": store.worst_weekday(per_habit[name], today, window),
                     "days": len(per_habit[name])})
    rows.sort(key=lambda r: (-r["current"], -r["longest"], r["name"]))
    lines = [_demo_note(demo_dir) + common.rule("last {0} days".format(window))]
    for r in rows:
        lines.append("  {0:<14} {1}  {2} day{3}".format(common.trunc(r["name"], 14), r["grid"],
                                                        r["current"], "" if r["current"] == 1 else "s"))
    best_row = rows[0]
    tail = "{0}: {1}-day streak · longest {2}".format(best_row["name"], best_row["current"], best_row["longest"])
    if best_row["worst_weekday"]:
        tail += " · you miss {0}s".format(best_row["worst_weekday"])
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "habits": rows, "best": best_row["name"], "window": window})


_DISPATCH = {
    ("punch", "record"): _punch_record, ("punch", "report"): _punch_report,
    ("spent", "record"): _spent_record, ("spent", "report"): _spent_report,
    ("jot", "record"): _jot_record, ("jot", "report"): _jot_report,
    ("streak", "record"): _streak_record, ("streak", "report"): _streak_report,
}


if __name__ == "__main__":
    sys.exit(main())
