import argparse, json, os, sys, dataclasses
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

if __name__ == "__main__" and __package__ is None:  # invoked as a file path from a Play step
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "comped_core"

from .timeutil import parse_ts, window_start, iso
from .adapters import parse_all
from .ledger import write_ledger, read_ledger, summary as ledger_summary
from .prices import load_table
from .plans import load_plans, parse_plan_ids, plan_label, AUTO
from .pricing import price_ledger
from .repeats import find_repeats
from .wrongturns import classify, draft_rules
from .baseline import load_baseline, save_baseline, delta
from .render_terminal import render_terminal
from .render_report import render_report, render_explain, share_text
from .detect import summary_line
from .tiers import tier, score
from .render_svg import render_svg, render_svg_square
from .render_png import render_png

# The card is drawn with box characters and the report is UTF-8. On Windows the default stdout
# encoding is the system code page, and printing the card to a pipe dies with UnicodeEncodeError
# before anything reaches the screen. Ask for UTF-8 and carry on if the stream cannot provide it
# (a test harness may have replaced stdout with something that has no reconfigure).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass



def _bool(s) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def _now(s):
    return parse_ts(s) if s else datetime.now(timezone.utc)


def _json(o):
    def enc(x):
        if isinstance(x, Decimal):
            return str(x)
        if dataclasses.is_dataclass(x):
            return dataclasses.asdict(x)
        raise TypeError(str(type(x)))
    print(json.dumps(o, default=enc, sort_keys=True))


def _state(out_dir: Path, name: str, doc=None):
    p = Path(out_dir).expanduser() / ".{0}.json".format(name)
    if doc is None:
        if not p.exists():
            raise FileNotFoundError("run the earlier step first: missing {0} in {1}".format(p.name, out_dir))
        return json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(doc, default=str, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def cmd_ledger(a):
    now = _now(a.now)
    cfg = {"claude_dir": a.claude_dir, "codex_dir": a.codex_dir, "pi_dir": a.pi_dir, "opencode_dir": a.opencode_dir,
           "include_subagents": _bool(a.include_subagents), "redact": _bool(a.redact),
           "since": window_start(now, a.days_back), "now": now}
    if a.only:
        from .adapters import ADAPTERS
        if a.only not in ADAPTERS:
            raise ValueError("--only must be one of {0}".format(sorted(ADAPTERS)))
        for h, (_, key) in ADAPTERS.items():
            if h != a.only:
                cfg[key] = "/nonexistent"     # other adapters report found=false and are dropped below
    led = parse_all(cfg)
    if a.only:
        led.sources = [s for s in led.sources if s.harness == a.only]
        out = Path(a.out_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        p = out / "ledger-{0}.jsonl".format(a.only)
        with open(p, "w", encoding="utf-8") as fh:
            for kind, items in (("record", led.records), ("human", led.humans), ("tool", led.tools), ("source", led.sources)):
                for it in items:
                    row = {"kind": kind}
                    row.update(dataclasses.asdict(it))
                    fh.write(json.dumps(row, sort_keys=True) + "\n")
        written = [str(p)]
    else:
        written = write_ledger(led, a.out_dir)
    _state(a.out_dir, "ledger-args", {"days_back": a.days_back, "now": iso(now), "redact": _bool(a.redact)})
    s = ledger_summary(led)
    s.update({"ok": True, "written": written,
              "note": "; ".join("{0}: {1}".format(x["harness"], x["note"]) for x in s["sources"] if x["note"])})
    absent = [x["harness"] for x in s["sources"] if not x["found"]]
    if absent and len(absent) == len(s["sources"]):
        s["warning"] = "no log directory found for {0}; nothing to read".format(", ".join(absent))
    elif s["records"] == 0:
        s["warning"] = "no usage records in the window"
    return s


def cmd_merge(a):
    from .models import UsageRecord, HumanMessage, ToolEvent, Source, Ledger
    from .ledger import attribute_turns
    out = Path(a.out_dir).expanduser()
    parts = [p for p in sorted(out.glob("ledger-*.jsonl")) if p.name != "ledger-summary.json"]
    if not parts:
        return {"ok": True, "warning": "no partial ledgers (ledger-<harness>.jsonl) found to merge", "written": [], "note": ""}
    recs, hums, tools, srcs = [], [], [], []
    for p in parts:
        for line in open(p, encoding="utf-8"):
            o = json.loads(line)
            kind = o.pop("kind")
            if kind == "record":
                recs.append(UsageRecord(**o))
            elif kind == "human":
                hums.append(HumanMessage(**o))
            elif kind == "tool":
                tools.append(ToolEvent(**o))
            elif kind == "source":
                srcs.append(Source(**o))
    st = _state(a.out_dir, "ledger-args")
    led = Ledger(sorted(recs, key=lambda r: (r.harness, r.session_id, r.timestamp, r.record_id)),
                 sorted(hums, key=lambda h: (h.harness, h.session_id, h.timestamp, h.message_id)),
                 sorted(tools, key=lambda t: (t.harness, t.session_id, t.timestamp, t.event_id)),
                 sorted(srcs, key=lambda s: s.harness), st["now"])
    attribute_turns(led)
    written = write_ledger(led, out)
    s = ledger_summary(led)
    s.update({"ok": True, "written": written, "note": "merged {0} partial ledgers".format(len(parts))})
    if s["records"] == 0:
        s["warning"] = "no usage records in the window"
    return s


def cmd_price(a):
    st = _state(a.out_dir, "ledger-args")
    now = _now(a.now or st["now"])
    led = read_ledger(a.out_dir)
    table = load_table(Path(a.rates_path).expanduser() if a.rates_path else None)
    plans = load_plans()
    # An empty plan= means "work it out", not "give up": the ids in the logs name the providers,
    # and every tier they sell is priced side by side. Typing a plan overrides the inference.
    ids = parse_plan_ids(a.plan) or [AUTO]
    # Say it once. A typed plan is remembered under out_dir, so the next bare run uses it; the
    # logs cannot tell a Pro month from a Max month, and nobody should have to retype what the
    # tool cannot know. plan=auto with no memory infers; delete the file to go back to inferring.
    memo = Path(a.out_dir).expanduser() / "comped-plan.txt"
    remembered = False
    if ids == [AUTO] and memo.exists():
        kept = parse_plan_ids(memo.read_text(encoding="utf-8"))
        if kept and kept != [AUTO]:
            ids, remembered = kept, True
    elif ids != [AUTO]:
        memo.parent.mkdir(parents=True, exist_ok=True)
        memo.write_text(",".join(ids) + "\n", encoding="utf-8")
    s = price_ledger(led, table, plans, ids, a.days_back or st["days_back"], now)
    if remembered:
        s.plan_source = "remembered"
        s.explain.append("plan: remembered from {0} (pass plan=<id> to change it, or delete the file to infer)".format(memo))
    doc = {"total_usd": s.total_usd, "per_model": s.per_model, "unpriced": s.unpriced, "cache_share": s.cache_share,
           "active_days": s.active_days, "sessions": s.sessions, "per_turn_usd": s.per_turn_usd, "plan_cost": s.plan_cost,
           "multiplier": s.multiplier, "plan_ids": s.plan_ids, "explain": s.explain, "window_start": s.window_start,
           "window_end": s.window_end, "price_meta": s.price_meta, "days_back": a.days_back or st["days_back"], "now": iso(now),
           "detected": s.detected, "plan_ladder": s.plan_ladder, "plan_source": s.plan_source,
           "tier": tier(s.multiplier)}
    _state(a.out_dir, "priced", doc)
    p = Path(a.out_dir).expanduser() / "comped-explain.txt"
    p.write_text(render_explain(s), encoding="utf-8")
    return {"ok": True, "written": [str(p)], "total_usd": s.total_usd, "multiplier": s.multiplier, "plan_cost": s.plan_cost,
            "per_model": s.per_model, "unpriced": s.unpriced, "cache_share": s.cache_share, "active_days": s.active_days,
            "sessions": s.sessions, "detected": summary_line(s.detected), "plan_source": s.plan_source,
            "plans": [{"label": r["label"], "multiplier": r["multiplier"], "assumed": r["assumed"]} for r in s.plan_ladder],
            "tier": tier(s.multiplier),
            "note": ("plan inferred from the logs: {0}".format(" + ".join(plan_label(p, plans) for p in s.plan_ids))
                     if s.plan_source == "auto" and s.plan_ids else
                     ("plan remembered from an earlier run: {0}".format(" + ".join(plan_label(p, plans) for p in s.plan_ids))
                      if s.plan_source == "remembered" else ""))}


def cmd_repeats(a):
    pr = _state(a.out_dir, "priced")
    led = read_ledger(a.out_dir)
    per_turn = {k: Decimal(v) for k, v in pr["per_turn_usd"].items()}
    cl = find_repeats(led.humans, per_turn, a.repeat_threshold, a.handle or "")
    doc = [dataclasses.asdict(c) for c in cl]
    _state(a.out_dir, "repeats", {"clusters": doc, "handle": a.handle or ""})
    return {"ok": True, "written": [], "repeats": doc,
            "dividend_98": sum((c.dividend_98 for c in cl), Decimal("0")),
            "dividend_80": sum((c.dividend_80 for c in cl), Decimal("0")), "note": ""}


def _view(a, pr, rp, led):
    plans = load_plans()
    labels = [plan_label(p, plans) for p in pr["plan_ids"]]
    total = Decimal(pr["total_usd"])
    pm = [{"model": m["model"], "usd": Decimal(m["usd"]), "share": (Decimal(m["usd"]) / total if total else Decimal("0"))} for m in pr["per_model"]]
    cl = rp["clusters"]
    handle = rp.get("handle") or "<handle>"
    return {"window_days": pr["days_back"], "window_start": pr["window_start"], "window_end": pr["window_end"], "total_usd": total,
            "multiplier": Decimal(pr["multiplier"]) if pr["multiplier"] is not None else None, "plan_labels": labels,
            "plan_cost": Decimal(pr["plan_cost"]) if pr["plan_cost"] is not None else None, "per_model": pm,
            "cache_share": Decimal(pr["cache_share"]), "active_days": pr["active_days"], "sessions": pr["sessions"],
            "repeats": [{"label": c["label"], "count": c["count"], "repeat_usd": Decimal(c["repeat_usd"]),
                         "capture_command": c["capture_command"]} for c in cl],
            "dividend_98": sum((Decimal(c["dividend_98"]) for c in cl), Decimal("0")),
            "dividend_80": sum((Decimal(c["dividend_80"]) for c in cl), Decimal("0")),
            "unpriced": pr["unpriced"], "price_as_of": pr["price_meta"].get("as_of", "?"),
            "price_source": pr["price_meta"].get("source_url", "?"),
            "detected": pr.get("detected") or {}, "plan_source": pr.get("plan_source", "typed"),
            "tier": pr.get("tier"), "site": "https://gotcomped.com",
            "plan_ladder": [{"label": r["label"], "cost": Decimal(str(r["cost"])),
                             "multiplier": Decimal(str(r["multiplier"])) if r.get("multiplier") is not None else None,
                             "assumed": r["assumed"]} for r in (pr.get("plan_ladder") or [])],
            "sources": [dataclasses.asdict(s) for s in led.sources], "written": [],
            "play_uri": "https://play.modiqo.ai/{0}/comped".format(handle),
            "explain_path": str(Path(a.out_dir).expanduser() / "comped-explain.txt"), "handle": handle}


def cmd_card(a):
    # Read the ledger first: on an empty out_dir the useful error names the missing ledger,
    # not the internal state file the next line would have looked for.
    led = read_ledger(a.out_dir)
    pr = _state(a.out_dir, "priced")
    rp = _state(a.out_dir, "repeats") if (Path(a.out_dir).expanduser() / ".repeats.json").exists() else {"clusters": [], "handle": ""}
    now = _now(pr["now"])
    v = _view(a, pr, rp, led)
    out = Path(a.out_dir).expanduser()

    class _S:
        pass

    s = _S()
    s.total_usd = v["total_usd"]
    s.multiplier = v["multiplier"]
    s.per_model = v["per_model"]

    class _C:
        pass

    cls = []
    for r in v["repeats"]:
        c = _C()
        c.label = r["label"]
        cls.append(c)
    v["delta"] = delta(load_baseline(out), s, cls, now)
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    v["terminal_card"] = render_terminal(v, False)
    card = render_terminal(v, color)
    svg = out / "comped-card.svg"
    svg.write_text(render_svg(v, a.card_theme), encoding="utf-8")
    sq = out / "comped-card-square.svg"
    sq.write_text(render_svg_square(v, a.card_theme), encoding="utf-8")
    written = [str(svg), str(sq)]
    png, note = render_png(sq, out, png_name="comped-card.png")
    if png:
        written.append(png)
    written.append(save_baseline(out, s, cls, now))
    v["written"] = written + [str(out / "comped-report.md"), str(out / "comped-explain.txt"), str(out / "ledger.jsonl")]
    rep = out / "comped-report.md"
    rep.write_text(render_report(v), encoding="utf-8")
    written.append(str(rep))
    sh = out / "comped-share.txt"
    sh.write_text(share_text(v) + "\n", encoding="utf-8")
    written.append(str(sh))
    print(card)
    print()
    print(share_text(v))
    print()
    return {"ok": True, "written": written, "total_usd": v["total_usd"], "multiplier": v["multiplier"],
            "repeats": len(v["repeats"]), "png": png, "note": note,
            "detected": summary_line(v["detected"]) if v.get("detected") else "",
            "plan": " + ".join(v["plan_labels"]), "plan_source": v.get("plan_source", "typed"),
            "tier": (v.get("tier") or {}).get("name", ""), "score": score(v["multiplier"])}


def cmd_run(a):
    """Read, price, cluster and render in one command: the four steps the Play runs as steps.

    Same functions, same order, same numbers; it exists because a person or an agent working from a
    shell has no runner to sequence them, and four commands that must not be reordered is a trap.
    Prints the card, then one JSON object like every other command. Still offline: the leaderboard
    post is a separate script outside this package, and this never calls it.
    """
    print("Reading your logs...", file=sys.stderr)
    led = cmd_ledger(a)
    warnings = [w for w in [led.get("warning")] if w]
    if not led.get("records"):
        looked = ", ".join(str(Path(d).expanduser()) for d in (a.claude_dir, a.codex_dir, a.pi_dir, a.opencode_dir))
        return {"ok": False, "written": led.get("written", []), "warnings": warnings,
                "error": led.get("warning") or "no usage records in the window",
                "note": "looked in {0}. Widen the window with --days-back 90, or point --claude-dir "
                        "and --codex-dir at where your logs actually are.".format(looked)}
    print("Pricing {0} records from {1} sessions...".format(led["records"], led["sessions"]), file=sys.stderr)
    cmd_price(a)
    print("Finding what you have asked for more than once...", file=sys.stderr)
    cmd_repeats(a)
    print("", file=sys.stderr)
    res = cmd_card(a)
    out = Path(a.out_dir).expanduser()
    res["warnings"] = warnings + [n for n in [led.get("note"), res.get("note")] if n]
    res["sources"] = led.get("sources", [])
    res["records"] = led["records"]
    res["report"] = str(out / "comped-report.md")
    res["share"] = str(out / "comped-share.txt")
    res["explain"] = str(out / "comped-explain.txt")
    res["out_dir"] = str(out)
    return res


def cmd_wrongturns(a):
    led = read_ledger(a.out_dir)
    p = Path(a.out_dir).expanduser() / ".priced.json"
    per_turn = {k: Decimal(v) for k, v in (json.loads(p.read_text())["per_turn_usd"].items() if p.exists() else [])}
    cl = classify(led, per_turn, a.min_recurrence, _bool(a.show_snippets))
    doc = [dataclasses.asdict(c) for c in cl]
    _state(a.out_dir, "wrongturns", {"classes": doc})
    return {"ok": True, "written": [], "classes": doc,
            "note": "" if per_turn else "no priced ledger found; recovery costs are 0 (run price first for costs)"}


def cmd_rules(a):
    wt = _state(a.out_dir, "wrongturns")
    from .wrongturns import MistakeClass
    cl = []
    for c in wt["classes"]:
        d = dict(c)
        d["recovery_usd"] = Decimal(d["recovery_usd"])
        cl.append(MistakeClass(**d))
    out = Path(a.out_dir).expanduser()
    rules = out / "wrong-turns-rules.md"
    rules.write_text(draft_rules(cl, a.rules_target), encoding="utf-8")
    rep = out / "wrong-turns-report.md"
    lines = ["# Wrong turns report", "", "| kind | confidence | tool | signature | count | sessions | recovery | evidence |",
             "|---|---|---|---|---|---|---|---|"]
    lines += ["| {0} | {1} | {2} | {3} | {4} | {5} | ${6:.2f} | {7} |".format(
        c.kind, c.confidence, c.tool_name, c.signature, c.count, c.sessions, c.recovery_usd, c.evidence) for c in cl]
    lines += ["", "Drafted rules: {0}".format(rules), "", "Read-only: nothing was applied to CLAUDE.md or AGENTS.md."]
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return {"ok": True, "written": [str(rules), str(rep)], "classes": len(cl), "note": ""}


def cmd_explain(a):
    p = Path(a.out_dir).expanduser() / "comped-explain.txt"
    print(p.read_text(encoding="utf-8"))
    return {"ok": True, "written": [], "note": ""}


def cmd_sources(a):
    """No parsing: report which log directories exist and how many files each holds. The session-ledger Play's first step."""
    out = []
    for harness, key, pat in (("claude-code", a.claude_dir, "*/*.jsonl"), ("codex", a.codex_dir, "*/*/*/rollout-*.jsonl"),
                              ("pi", a.pi_dir, "*.jsonl"), ("opencode", a.opencode_dir, "message/**/*.json")):
        p = Path(key).expanduser()
        n = sum(1 for _ in p.glob(pat)) if p.is_dir() else 0
        out.append({"harness": harness, "root": str(p), "found": p.is_dir(), "files": n})
    from .detect import HARNESSES
    for s in out:
        s["label"] = HARNESSES.get(s["harness"], (s["harness"], ""))[0]
    found = [s["label"] for s in out if s["found"]]
    return {"ok": True, "written": [], "sources": out, "detected": ", ".join(found) or "no log directory found",
            "note": "; ".join("{0}: not found".format(s["harness"]) for s in out if not s["found"])}


def cmd_summary(a):
    p = Path(a.out_dir).expanduser() / "ledger-summary.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    print(json.dumps(doc, indent=1, sort_keys=True))
    res = {"ok": True, "written": [], "note": ""}
    res.update(doc)
    return res


def cmd_verify(a):
    pr = _state(a.out_dir, "priced")
    led = read_ledger(a.out_dir)
    table = load_table()
    plans = load_plans()
    s = price_ledger(led, table, plans, pr["plan_ids"], pr["days_back"], _now(pr["now"]))
    ok = str(s.total_usd) == str(pr["total_usd"])
    return {"ok": ok, "written": [], "recomputed_total_usd": s.total_usd, "reported_total_usd": pr["total_usd"],
            "note": "totals reproduce" if ok else "MISMATCH: ledger or price table changed since the report"}


def build_parser():
    P = argparse.ArgumentParser(prog="comped")
    sub = P.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--out-dir", default="~/comped")

    def dirs(p):
        for k, d in (("claude-dir", "~/.claude/projects"), ("codex-dir", "~/.codex/sessions"),
                     ("pi-dir", "~/.pi/agent/sessions"), ("opencode-dir", "~/.local/share/opencode/storage")):
            p.add_argument("--{0}".format(k), default=d)

    # One group per step, so `run` takes exactly the arguments of the steps it runs, with the same
    # defaults. A flag that means one thing under `price` and another under `run` is a bug waiting.
    def read_args(p):
        p.add_argument("--days-back", type=int, default=30)
        p.add_argument("--include-subagents", default="true")
        p.add_argument("--redact", default="true")
        p.add_argument("--now", default="")

    def price_args(p):
        p.add_argument("--plan", default=AUTO,
                       help="auto (default) infers the providers from the logs and prices every tier they sell; "
                            "or a comma-separated list of plan ids, or usd:<amount>")
        p.add_argument("--rates-path", default="")

    def repeat_args(p):
        p.add_argument("--repeat-threshold", type=int, default=3)
        p.add_argument("--handle", default="", help="your name in the /play settle command, and on the leaderboard")

    def card_args(p):
        p.add_argument("--card-theme", default="dark")

    p = sub.add_parser("ledger"); common(p); dirs(p); read_args(p)
    p.add_argument("--only", default="", help="read exactly one harness and write ledger-<harness>.jsonl (rote: one reading = one step)")
    p = sub.add_parser("merge"); common(p)
    p = sub.add_parser("price"); common(p); price_args(p)
    p.add_argument("--days-back", type=int, default=0)
    p.add_argument("--now", default="")
    p = sub.add_parser("repeats"); common(p); repeat_args(p)
    p = sub.add_parser("card"); common(p); card_args(p)
    # The whole card in one command, for a shell with no runner in front of it. The Play still runs
    # the steps separately: one reading per step is what makes a step's evidence readable.
    p = sub.add_parser("run", help="read, price, cluster and render in one command")
    common(p); dirs(p); read_args(p); price_args(p); repeat_args(p); card_args(p)
    p.set_defaults(only="")
    p = sub.add_parser("wrongturns"); common(p)
    p.add_argument("--min-recurrence", type=int, default=3)
    p.add_argument("--show-snippets", default="true")
    p = sub.add_parser("rules"); common(p)
    p.add_argument("--rules-target", default="both")
    p = sub.add_parser("explain"); common(p)
    p = sub.add_parser("verify"); common(p)
    p = sub.add_parser("sources"); dirs(p)
    p = sub.add_parser("summary"); common(p)
    return P


def main(argv=None):
    P = build_parser()
    try:
        a = P.parse_args(argv)
    except SystemExit:
        _json({"ok": False, "error": "bad arguments; see --help"})
        return 2
    try:
        res = globals()["cmd_{0}".format(a.cmd)](a)
        _json(res)
        # A command that reports ok:false has not done its job; say so in the exit code too, so a
        # script or an agent that only checks the status does not read failure as success.
        return 0 if res.get("ok", True) else 1
    except Exception as e:  # never a traceback
        msg = "{0}: {1}".format(type(e).__name__, e)
        _json({"ok": False, "error": msg})
        print(msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
