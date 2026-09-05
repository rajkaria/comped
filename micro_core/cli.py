"""One entry point for twelve Plays.

A Play that remembers is two steps, `record` then `report`, and the state file is what they share.
A Play that is a pure function is one `report` step: giving it a second step would mean inventing a
scratch file for the halves to talk through, and a Play that claims to write nothing should not
write a file to prove it.
"""
import argparse
import calendar
import json
import re
import sys
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

if __name__ == "__main__" and __package__ is None:      # invoked as a file path from a Play step
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "micro_core"

from . import common, cronx, decode, secrets, size, snapshot, staged, store, turn

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
    """No path in the note. It is a temp directory the runner made, it is different every run, and
    printing it puts a machine-specific string into a card and into the committed fixtures."""
    return "" if not demo_dir else "demo run: a bundled 14-day log, copied to a temporary folder\n"


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
    requested = str(a.currency or "").upper().strip()
    # The currency parameter is what a new entry defaults to. It is only the currency of the REPORT
    # if you have actually spent in it, or a month of rupees would be labelled in dollars.
    primary = requested if requested in per_currency else max(
        per_currency, key=lambda c: (per_currency[c]["n"], c))
    row = per_currency[primary]
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
    vault_dir = str(a.vault_dir or "")
    if common.as_bool(a.demo):
        vault_dir = str(state)
        seed = common.fixtures_dir() / "log" / "Inbox.md"
        if seed.is_file():
            (state / str(a.inbox or "Inbox.md")).write_text(seed.read_text(encoding="utf-8"),
                                                            encoding="utf-8")
    entries = store.read(state, "jot")
    if not entries:
        return common.emit("Nothing captured yet. Run it with note='the thought'.",
                           common.warn("no notes captured yet"))
    days = store.days_with_entries(entries, tz)
    today = common.day(now, tz)
    n_today = len([e for e in entries if common.day(e.t, tz) == today])
    week = len([e for e in entries if e.t >= now - timedelta(days=7)])
    inbox_lines = 0
    if vault_dir.strip():
        p = _inbox_path(vault_dir, a.inbox)
        try:
            inbox_lines = len([l for l in p.read_text(encoding="utf-8").split("\n") if l.startswith("- ")])
        except OSError:
            inbox_lines = 0
    cur_streak, best = store.streak(days, today)
    recent = entries[-5:]
    lines = [_demo_note(demo_dir) + common.rule("last captured")]
    for e in reversed(recent):
        when = common.hhmm(e.t, tz) if common.day(e.t, tz) == today else common.day(e.t, tz)
        lines.append("  {0:<10} {1}".format(when, common.trunc(e.data.get("note", ""), 52)))
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


# ---------------------------------------------------------------- whatis

def _whatis_report(argv):
    a = _parser("whatis report", ("text", ""), ("depth", "4"), ("reveal", "false")).parse_args(argv)
    text = str(a.text or "")
    if common.as_bool(a.demo) and not text.strip():
        try:
            text = (common.fixtures_dir() / "whatis" / "input.txt").read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
    if not text.strip():
        return common.emit("Nothing to look at — pass text='the opaque thing'.",
                           common.warn("no text given"))
    reveal = common.as_bool(a.reveal)
    layers = decode.peel(text, depth=int(a.depth or 4), reveal=reveal)
    chain = " → ".join(l.kind for l in layers)
    body = decode.render(layers, reveal)
    tail = "{0} {1} deep: {2}".format(len(layers), common.plural(len(layers), "layer"), chain)
    for l in layers:
        if l.detail.get("expiry"):
            tail += " · {0}".format(l.detail["expiry"])
    return common.emit("\n".join([body, "", tail]),
                       {"ok": True, "kind": layers[0].kind, "chain": chain,
                        "layers": [{"kind": l.kind, "label": l.label,
                                    "detail": {k: v for k, v in l.detail.items() if k != "value"}}
                                   for l in layers],
                        "depth_reached": len(layers), "chars": len(text)})


# ---------------------------------------------------------------- is-it-secret

def _input_text(a, fixture_name, limit=2 * 1024 * 1024):
    """text, or a file, or the bundled fixture on a demo run — and which one it was."""
    if str(getattr(a, "text", "") or "").strip():
        return str(a.text), "the text you passed"
    path, label = str(getattr(a, "path", "") or "").strip(), ""
    if not path and common.as_bool(getattr(a, "demo", "false")):
        # The package lives in a temp workspace at run time; printing that path would tell the
        # reader nothing except where the runner unpacked it.
        path, label = str(common.fixtures_dir() / fixture_name), "the bundled sample"
    if not path:
        return "", ""
    p = common.expand(path)
    try:
        if p.is_dir():
            parts, names = [], []
            for f in sorted(p.rglob("*"))[:200]:
                if f.is_file() and f.stat().st_size < limit:
                    try:
                        parts.append(f.read_text(encoding="utf-8", errors="replace"))
                        names.append(f.name)
                    except OSError:
                        continue
            return "\n".join(parts), "{0} files under {1}".format(len(names), p)
        return p.read_text(encoding="utf-8", errors="replace")[:limit], label or str(p)
    except OSError as e:
        return "", "could not read {0}: {1}".format(p, e.strerror or e)


def _secret_report(argv):
    a = _parser("secret report", ("text", ""), ("path", ""), ("strict", "true"),
                ("show", "redacted")).parse_args(argv)
    body, source = _input_text(a, "secret/config.env")
    if not body.strip():
        return common.emit("Nothing to check — pass text='...' or path=/some/file.",
                           common.warn(source or "no text or path given"))
    found = secrets.scan(body, strict=common.as_bool(a.strict))
    call = secrets.verdict(found)
    lines = [common.rule("read {0}".format(common.trunc(source, 40)))]
    for f in found:
        lines.append("  {0:<9} line {1:<4} {2:<20} {3}".format(f.severity, f.line, f.kind, f.masked))
        lines.append("             {0}".format(f.why))
    if not found:
        lines.append("  nothing that looks like a credential")
    redacted = ""
    if found and str(a.show).lower() == "redacted":
        redacted = secrets.redact(body, found)
        if len(redacted) <= 4000:
            lines += ["", common.rule("safe to paste")] + ["  " + l for l in redacted.split("\n")[:60]]
    verdicts = {"safe": "nothing to redact — paste it",
                "redact": "{0} thing{1} to redact before you paste that",
                "do-not-paste": "do not paste this: {0} live credential{1} in it"}
    n = len(found)
    tail = verdicts[call].format(n, "" if n == 1 else "s") if call != "safe" else verdicts["safe"]
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "verdict": call, "findings": [
                           {"kind": f.kind, "severity": f.severity, "line": f.line, "masked": f.masked,
                            "why": f.why} for f in found],
                        "counts": secrets.counts(found), "redacted": redacted,
                        "source": source, "bytes": len(body)})


# ---------------------------------------------------------------- cron-when

def _cron_report(argv):
    a = _parser("cron report", ("expr", ""), ("tz", ""), ("count", "5")).parse_args(argv)
    expr = str(a.expr or "").strip() or ("30 9 * * 1-5" if common.as_bool(a.demo) else "")
    if not expr:
        return common.emit("Nothing to read — pass expr='30 9 * * 1-5'.", common.warn("no expression given"))
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    try:
        spec = cronx.parse(expr)
    except ValueError as e:
        return common.emit("That is not a cron expression: {0}".format(e),
                           {"ok": True, "valid": False, "error": str(e), "expr": expr})
    fires = cronx.next_fires(spec, now, max(1, int(a.count)), tz)
    english = cronx.describe(spec)
    warning = cronx.dst_warning(spec, tz, now)
    zone = getattr(tz, "key", None) or now.astimezone(tz).strftime("%Z") or "local"
    lines = [common.rule(expr), "  {0}".format(english), ""]
    for f in fires:
        lines.append("  {0}   {1} UTC".format(f.strftime("%a %d %b %Y %H:%M"),
                                              f.astimezone(timezone.utc).strftime("%H:%M")))
    if not fires:
        lines.append("  no fire in the next four years")
    gap = cronx.average_interval_min(fires)
    if warning:
        lines += ["", "  ⚠ {0}".format(warning)]
    tail = "{0} — next {1} {2}".format(english, fires[0].strftime("%a %H:%M") if fires else "never", zone)
    if fires:
        tail += " ({0} UTC)".format(fires[0].astimezone(timezone.utc).strftime("%H:%M"))
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "valid": True, "expr": expr, "english": english, "zone": str(zone),
                        "fires": [{"local": f.strftime("%Y-%m-%d %H:%M"),
                                   "utc": f.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")}
                                  for f in fires],
                        "average_interval_min": gap, "dst_warning": warning or ""})


# ---------------------------------------------------------------- fits

DEFAULT_MODELS = "claude-opus-5,claude-sonnet-5,claude-haiku-4-5"


def _fits_report(argv):
    a = _parser("fits report", ("text", ""), ("path", ""), ("window", "200000"),
                ("models", DEFAULT_MODELS), ("rates_path", "")).parse_args(argv)
    body, source = _input_text(a, "fits/sample.txt")
    if not body.strip():
        return common.emit("Nothing to measure — pass text='...' or path=/some/file.",
                           common.warn(source or "no text or path given"))
    from comped_core.prices import load_table
    table = load_table(common.expand(a.rates_path) if str(a.rates_path or "").strip() else None)
    m = size.measure(body)
    low, mid, high = size.token_range(body)
    fit = size.window_fit(mid, int(a.window))
    rows = size.costs(low, high, [x for x in str(a.models).split(",") if x.strip()], table)
    lines = [common.rule(common.trunc(source, 44)),
             "  {0} bytes · {1} lines · {2} words · {3}".format(
                 common.human_int(m["bytes"]), common.human_int(m["lines"]),
                 common.human_int(m["words"]), size.describe_shape(body)),
             "  {0}–{1} tokens (estimate) · {2}% of a {3} window".format(
                 common.human_tokens(low), common.human_tokens(high), fit["pct"],
                 common.human_tokens(fit["window"])), ""]
    for row in rows:
        if row["resolved"] is None:
            lines.append("  {0:<22} {1}".format(common.trunc(row["model"], 22), row["note"]))
        else:
            lines.append("  {0:<22} ${1}–${2}   (${3}/Mtok in)".format(
                common.trunc(row["model"], 22), row["low_usd"], row["high_usd"], row["per_mtok_usd"]))
    priced = [r for r in rows if r["resolved"]]
    tail = "{0}–{1} tokens · {2}% of a {3} window".format(
        common.human_tokens(low), common.human_tokens(high), fit["pct"], common.human_tokens(fit["window"]))
    if not fit["fits"]:
        tail = "does not fit: " + tail
    if priced:
        tail += " · ${0}–${1} on {2}".format(priced[0]["low_usd"], priced[0]["high_usd"], priced[0]["model"])
    lines += ["", "  " + size.METHOD, "", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "bytes": m["bytes"], "chars": m["chars"], "lines": m["lines"],
                        "words": m["words"], "tokens_low": low, "tokens_mid": mid, "tokens_high": high,
                        "fits": fit["fits"], "pct": fit["pct"], "window": fit["window"],
                        "costs": rows, "method": size.METHOD, "source": source})


# ---------------------------------------------------------------- last-turn, budget-left

def _agent_dirs(a):
    if common.as_bool(getattr(a, "demo", "false")):
        return [common.fixtures_dir() / "agent" / "claude", common.fixtures_dir() / "agent" / "codex"]
    return [common.expand(a.claude_dir), common.expand(a.codex_dir)]


def _price_table(a):
    from comped_core.prices import load_table
    path = str(getattr(a, "rates_path", "") or "").strip()
    return load_table(common.expand(path) if path else None)


def _last_turn_report(argv):
    a = _parser("last-turn report", ("claude_dir", "~/.claude/projects"), ("codex_dir", "~/.codex/sessions"),
                ("rates_path", ""), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    dirs, table = _agent_dirs(a), _price_table(a)
    t = turn.last_turn(dirs, table)
    if t is None:
        return common.emit("No transcript to read. Point claude_dir or codex_dir at your sessions, "
                           "or run it with demo=true.",
                           common.warn("no session transcript found under the configured directories"))
    today = turn.today_total(dirs, table, now, tz)
    model = t["resolved"] or t["model"] or "unknown model"
    lines = [common.rule("the turn that just finished"),
             "  {0:<22} {1}".format(model, t["at"] or ""),
             "  in {0} · out {1} · cache read {2} · cache write {3}".format(
                 common.human_tokens(t["input"]), common.human_tokens(t["output"]),
                 common.human_tokens(t["cache_read"]), common.human_tokens(t["cache_write"])),
             "  {0}{1}".format(common.human_usd(t["usd"]),
                               "" if t["resolved"] else "  (model not in the price table)"),
             "", "  today: {0} across {1} {2}".format(common.human_usd(today["usd"]), today["turns"],
                                                      common.plural(today["turns"], "turn")),
             "  read the last 256 KB of {0} — a tail, not an accounting".format(Path(t["source"]).name)]
    tail = "that turn: {0} in / {1} out · {2}% cached · {3} · {4} today".format(
        common.human_tokens(t["input"]), common.human_tokens(t["output"]), t["cache_pct"],
        common.human_usd(t["usd"]), common.human_usd(today["usd"]))
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "model": model, "input": t["input"], "output": t["output"],
                        "cache_read": t["cache_read"], "cache_write": t["cache_write"],
                        "cache_pct": t["cache_pct"], "usd": t["usd"], "harness": t["harness"],
                        "at": t["at"], "today_usd": today["usd"], "turns_today": today["turns"],
                        "priced": bool(t["resolved"]), "skipped_lines": t["skipped_lines"]})


def _budget_report(argv):
    a = _parser("budget report", ("daily_budget", "10"), ("claude_dir", "~/.claude/projects"),
                ("codex_dir", "~/.codex/sessions"), ("rates_path", ""), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    dirs, table = _agent_dirs(a), _price_table(a)
    today = turn.today_total(dirs, table, now, tz)
    try:
        budget = Decimal(str(a.daily_budget or "0"))
    except Exception:
        budget = Decimal("0")
    spent = Decimal(today["usd"])
    if today["turns"] == 0:
        return common.emit("Nothing billed today yet — the budget is untouched.",
                           {"ok": True, "spent": "0", "budget": str(budget), "pct": 0,
                            "burn_per_hour": "0", "exhausted_at": "", "verdict": "idle", "turns": 0})
    hours = max(0.25, (now - today["first_at"]).total_seconds() / 3600.0)
    rate = spent / Decimal(str(round(hours, 4)))
    pct = int(spent * 100 / budget) if budget > 0 else 0
    exhausted, verdict = "", "no budget set"
    if budget > 0:
        remaining = budget - spent
        if remaining <= 0:
            exhausted, verdict = "already", "over"
        elif rate > 0:
            at = now + timedelta(hours=float(remaining / rate))
            # Only a crossing that happens TODAY is a clock time worth printing: "about 08:32"
            # for a moment eighteen days out reads as this morning and means nothing.
            same_day = at.astimezone(tz).date() == now.astimezone(tz).date()
            exhausted = common.hhmm(at, tz) if same_day else ""
            verdict = "tight" if same_day else "comfortable"
        else:
            verdict = "comfortable"
    bar_width = 24
    filled = min(bar_width, int(pct / 100.0 * bar_width)) if budget > 0 else 0
    lines = [common.rule("today"),
             "  [{0}{1}] {2}%".format("█" * filled, "·" * (bar_width - filled), pct),
             "  {0} of {1} across {2} {3} since {4}".format(
                 common.human_usd(spent), common.human_usd(budget), today["turns"],
                 common.plural(today["turns"], "turn"), common.hhmm(today["first_at"], tz))]
    tail = "{0} of {1} · burning {2}/h".format(common.human_usd(spent), common.human_usd(budget),
                                               common.human_usd(rate))
    if exhausted == "already":
        tail += " · the cap is behind you"
    elif exhausted:
        tail += " · cap reached about {0}".format(exhausted)
    elif budget > 0:
        tail += " · not today at this rate"
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "spent": str(spent.quantize(Decimal("0.01"))),
                        "budget": str(budget.quantize(Decimal("0.01"))), "pct": pct,
                        "burn_per_hour": str(rate.quantize(Decimal("0.0001"))),
                        "exhausted_at": exhausted, "verdict": verdict, "turns": today["turns"],
                        "models": today["models"]})


# ---------------------------------------------------------------- since-last

def _since_last_report(argv):
    a = _parser("since-last report", ("root", "."), ("state_dir", DEFAULT_STATE_DIR), ("ignore", ""),
                ("max_files", "20000"), ("watch_sensitive", "true"), ("tz", "")).parse_args(argv)
    now, tz = common.now_utc(a.now), common.tz_of(a.tz)
    root = common.expand(a.root)
    if common.as_bool(a.demo):
        root = common.fixtures_dir() / "since" / "tree"
    state = common.expand(a.state_dir)
    if common.as_bool(a.demo):
        import tempfile
        state = Path(tempfile.mkdtemp(prefix="rote-micro-demo-"))
    ignore = set(snapshot.DEFAULT_IGNORE) | {x.strip() for x in str(a.ignore or "").split(",") if x.strip()}
    cur, meta = snapshot.scan_tree(root, ignore, int(a.max_files))
    if meta.get("missing"):
        return common.emit("No such directory: {0}".format(root),
                           common.warn("{0} is not a directory".format(root)))
    key = snapshot.key_for(root)
    prev = snapshot.load(state, key)
    if common.as_bool(a.demo):
        # The bundled seed is keyed by nothing: the fixture's absolute path differs on every
        # machine, so the demo loads the tree as it was before the last turn directly.
        try:
            prev = json.loads((common.fixtures_dir() / "since" / "state" / "seed.json")
                              .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = None
    sens_key = "sensitive-" + key
    prev_sens = snapshot.load(state, sens_key) if common.as_bool(a.watch_sensitive) else None
    cur_sens = snapshot.sensitive_state() if common.as_bool(a.watch_sensitive) else {}
    written = [snapshot.save(state, key, cur)]
    if common.as_bool(a.watch_sensitive):
        written.append(snapshot.save(state, sens_key, cur_sens))
    if common.as_bool(a.demo):
        # A demo run writes into a temp directory the runner just made. Naming it would put an
        # unrepeatable path in the output and in the committed fixture; saying what it is does not.
        written = ["a temporary folder (demo run); your own state_dir was not touched"]
    if prev is None:
        return common.emit(
            "First look at {0}: {1} files noted. Run it again after the agent works and this "
            "becomes a list of what it touched.".format(root, common.human_int(len(cur))),
            {"ok": True, "first_run": True, "created": [], "modified": [], "deleted": [],
             "lines_added": 0, "lines_removed": 0, "biggest": None, "sensitive_changed": [],
             "files": len(cur), "truncated": meta["truncated"], "written": written})
    d = snapshot.delta(prev, cur)
    changed_sens = snapshot.sensitive_changed(prev_sens, cur_sens)
    touched = len(d["created"]) + len(d["modified"]) + len(d["deleted"])
    lines = [common.rule("since you last asked")]
    for label, paths in (("new", d["created"]), ("changed", d["modified"]), ("gone", d["deleted"])):
        for p in paths[:12]:
            lines.append("  {0:<8} {1}".format(label, common.trunc(p, 56)))
        if len(paths) > 12:
            lines.append("  {0:<8} … and {1} more".format("", len(paths) - 12))
    if not touched:
        lines.append("  nothing changed")
    if meta["truncated"]:
        lines.append("  (stopped at {0} files; this is a lower bound)".format(meta["files"]))
    if changed_sens:
        lines += ["", "  ⚠ changed outside the tree: {0}".format(", ".join(changed_sens))]
    tail = "{0} {1} touched · +{2} / −{3} lines · {4}".format(
        touched, common.plural(touched, "file"), d["lines_added"], d["lines_removed"],
        "nothing outside the repo" if not changed_sens else "something outside the repo moved")
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "first_run": False, "created": d["created"],
                        "modified": d["modified"], "deleted": d["deleted"],
                        "lines_added": d["lines_added"], "lines_removed": d["lines_removed"],
                        "biggest": d["biggest"], "sensitive_changed": changed_sens,
                        "files": len(cur), "truncated": meta["truncated"], "written": written})


# ---------------------------------------------------------------- safe-to-commit

def _staged_report(argv):
    a = _parser("staged report", ("repo", "."), ("max_file_kb", "512"), ("strict", "true")).parse_args(argv)
    repo = common.fixtures_dir() / "staged" / "repo" if common.as_bool(a.demo) else common.expand(a.repo)
    r = staged.review(repo, int(a.max_file_kb), common.as_bool(a.strict))
    if r["verdict"] == "nothing-staged":
        return common.emit("Nothing staged in {0} — stage something and ask again.".format(repo),
                           dict(common.warn(r["warning"]), verdict="nothing-staged", files=[],
                                findings=[], debug=[], oversized=[], env_files=[]))
    lines = [common.rule("{0} staged {1}".format(len(r["files"]), common.plural(len(r["files"]), "file")))]
    for f in r["files"]:
        lines.append("  {0:<44} {1}".format(common.trunc(f["path"], 44), common.human_int(f["bytes"])))
    if r["findings"]:
        lines += ["", common.rule("credentials")]
        for f in r["findings"]:
            lines.append("  {0:<9} {1}:{2}  {3}  {4}".format(f["severity"], common.trunc(f["path"], 28),
                                                             f["line"], f["kind"], f["masked"]))
    if r["debug"]:
        lines += ["", common.rule("left-behind debugging")]
        for d in r["debug"][:10]:
            lines.append("  {0}:{1}  {2}".format(common.trunc(d["path"], 28), d["line"], d["text"]))
    if r["oversized"]:
        lines += ["", common.rule("large files")]
        for o in r["oversized"]:
            lines.append("  {0}  {1} bytes".format(common.trunc(o["path"], 40), common.human_int(o["bytes"])))
    if r["from_worktree"]:
        lines += ["", "  read from the working tree (the staged blob is packed): {0}".format(
            ", ".join(r["from_worktree"][:5]))]
    blockers = [f for f in r["findings"] if f["severity"] == "blocker"]
    if r["verdict"] == "clean":
        tail = "{0} staged {1} · nothing to hold the commit".format(
            len(r["files"]), common.plural(len(r["files"]), "file"))
    elif blockers:
        tail = "{0} staged {1} · {2} {3}: {4} in {5}".format(
            len(r["files"]), common.plural(len(r["files"]), "file"), len(blockers),
            common.plural(len(blockers), "blocker"), blockers[0]["kind"], blockers[0]["path"])
    else:
        n = len(r["findings"]) + len(r["debug"]) + len(r["oversized"])
        tail = "{0} staged {1} · {2} thing{3} worth a look before you commit".format(
            len(r["files"]), common.plural(len(r["files"]), "file"), n, "" if n == 1 else "s")
    lines += ["", tail]
    return common.emit("\n".join(lines),
                       {"ok": True, "verdict": r["verdict"], "files": r["files"],
                        "findings": r["findings"], "debug": r["debug"], "oversized": r["oversized"],
                        "env_files": r["env_files"], "from_worktree": r["from_worktree"],
                        "staged": len(r["files"])})


_DISPATCH = {
    ("staged", "report"): _staged_report,
    ("since-last", "report"): _since_last_report,
    ("last-turn", "report"): _last_turn_report,
    ("budget", "report"): _budget_report,
    ("fits", "report"): _fits_report,
    ("cron", "report"): _cron_report,
    ("secret", "report"): _secret_report,
    ("whatis", "report"): _whatis_report,
    ("punch", "record"): _punch_record, ("punch", "report"): _punch_report,
    ("spent", "record"): _spent_record, ("spent", "report"): _spent_report,
    ("jot", "record"): _jot_record, ("jot", "report"): _jot_report,
    ("streak", "record"): _streak_record, ("streak", "report"): _streak_report,
}


if __name__ == "__main__":
    sys.exit(main())
