from decimal import Decimal

W = 64


def money(d: Decimal) -> str:
    return "${0:,.2f}".format(d)


def _c(s, code, on):
    return "\x1b[{0}m{1}\x1b[0m".format(code, s) if on else s


def _row(text: str, color_len=0) -> str:
    pad = W - 4 - (len(text) - color_len)
    return "│ " + text + " " * max(pad, 0) + " │"


def _rule(label: str) -> str:
    """A section head that reads as part of the box rather than a stray line of shouting."""
    body = "─ {0} ".format(label)
    return "├" + body + "─" * max(0, W - 2 - len(body)) + "┤"


def _bar(share: Decimal, width=12) -> str:
    return "▇" * max(0, min(width, int(round(float(share) * width))))


def pick_rows(rows: list, n: int) -> list:
    """The first n rungs, but never at the cost of the one the card assumed.

    The ladder is ordered by price, and a two-vendor stack puts the combined row (the assumed one)
    at the bottom. Dropping it is the one thing the cut must not do."""
    shown = rows[:n]
    if any(r["assumed"] for r in shown) or not any(r["assumed"] for r in rows):
        return shown
    return shown[: n - 1] + [r for r in rows if r["assumed"]][:1]


def _mult(m) -> str:
    return "{0:.1f}×".format(m) if m is not None else "—"


def render_terminal(v: dict, color: bool) -> str:
    L = ["┌" + "─" * (W - 2) + "┐"]
    head = "COMPED"
    right = "last {0} days".format(v["window_days"])
    L.append(_row(head + " " * (W - 4 - len(head) - len(right)) + right))
    L.append(_row(""))
    total = "{0} comped".format(money(v["total_usd"]))
    L.append(_row(_c(total, "1;32", color), 11 if color else 0))
    if v.get("multiplier") is not None:
        L.append(_row("{0:.1f}×  vs {1} ({2} prorated)".format(v["multiplier"], " + ".join(v["plan_labels"]), money(v["plan_cost"]))[: W - 4]))
    else:
        L.append(_row("list-price total only: no subscription matched what you run"[: W - 4]))
    t = v.get("tier")
    if t:
        L.append(_row(_c("{0} · tier {1} of {2}".format(t["name"].upper(), t["rank"], t["of"]), "1;33", color), 11 if color else 0))
    if v.get("plan_source") == "auto" and v.get("plan_labels"):
        L.append(_row("assumed from your own logs — nothing typed, nothing asked"[: W - 4]))
    elif v.get("plan_source") == "remembered":
        L.append(_row("remembered from last time (plan=<id> to change)"[: W - 4]))
    L.append(_row(""))
    for m in v["per_model"][:3]:
        name = m["model"][:18].ljust(18)
        L.append(_row("{0} {1:>12} {2:>4}%   {3}".format(name, money(m["usd"]), int(round(float(m["share"]) * 100)), _bar(m["share"]))[: W - 4]))
    L.append(_row("cache read share {0}%   active days {1}/{2}   sessions {3}".format(
        int(round(float(v["cache_share"]) * 100)), v["active_days"], v["window_days"], v["sessions"])[: W - 4]))
    d = v.get("delta") or {}
    if d.get("first_run"):
        L.append(_row("baseline saved; next run shows the delta"))
    else:
        md = ", {0}{1:.1f}×".format("+" if d["multiplier_delta"] >= 0 else "", d["multiplier_delta"]) if d.get("multiplier_delta") is not None else ""
        L.append(_row("since last run ({0}d ago): {1}{2}{3}".format(
            d["days_since"], "+" if d["total_usd_delta"] >= 0 else "-", money(abs(d["total_usd_delta"])), md)[: W - 4]))

    L += _detected_block(v)
    L += _ladder_block(v)

    L.append(_rule("REPEAT OFFENDERS"))
    if not v["repeats"]:
        L.append(_row("none met the threshold (3 asks, 2 sessions, 2 days)"))
    for r in v["repeats"][:3]:
        label = '{0}× "{1}"'.format(r["count"], r["label"][:34])
        L.append(_row("{0}{1:>16}".format(label.ljust(44), money(r["repeat_usd"]))[: W - 4]))
    if v["repeats"]:
        L.append(_row("Rote dividend: ${0:,.0f} at 98% · ${1:,.0f} at 80%".format(v["dividend_98"], v["dividend_80"])[: W - 4]))
        L.append(_row("capture: {0}".format(v["repeats"][0]["capture_command"])[: W - 4]))
    L.append(_row(""))
    L.append(_row("list-price equivalent, not a bill · prices as of {0}".format(v["price_as_of"])[: W - 4]))
    n = len(v["unpriced"])
    names = ", ".join(u["model"] for u in v["unpriced"][:3])
    L.append(_row((("{0} model{1} unpriced ({2}) · ".format(n, "s" if n != 1 else "", names) if n else "") + "explain →")[: W - 4]))
    L.append(_row(v["explain_path"][: W - 4]))
    L.append("└" + "─" * (W - 2) + "┘")
    return "\n".join(L)


def _detected_block(v: dict) -> list:
    """What you are running, worked out from the logs. Nobody typed any of this."""
    det = v.get("detected") or {}
    provs = [p for p in det.get("providers", []) if p.get("records")]
    if not provs and not det.get("harnesses"):
        return []
    L = [_rule("DETECTED")]
    recs = sum(p["records"] for p in provs) or 1
    for p in provs[:3]:
        share = int(round(100.0 * p["records"] / recs))
        models = ", ".join(p["models"][:2])
        more = " +{0}".format(len(p["models"]) - 2) if len(p["models"]) > 2 else ""
        L.append(_row("{0} {1:>3}%   {2}{3}".format(p["talk_to"].ljust(12), share, models, more)[: W - 4]))
    where = ", ".join(h["label"] for h in det.get("harnesses", []) if h.get("found"))
    misses = [h["label"] for h in det.get("harnesses", []) if not h.get("found")]
    L.append(_row("read from {0}".format(where or "no log directory found")[: W - 4]))
    if misses:
        L.append(_row("not installed here: {0}".format(", ".join(misses))[: W - 4]))
    return L


def _ladder_block(v: dict) -> list:
    """Every tier the detected providers sell. You read your row; you never type it."""
    rows = v.get("plan_ladder") or []
    if len(rows) < 2:
        return []
    L = [_rule("IF YOU'RE ON…")]
    for r in pick_rows(rows, 5):
        mark = "  ← assumed" if r["assumed"] else ""
        label = r["label"] if len(r["label"]) <= 28 else r["label"][:27] + "…"
        L.append(_row("{0}{1:>10}{2:>9}{3}".format(label.ljust(28), money(r["cost"]), _mult(r["multiplier"]), mark)[: W - 4]))
    L.append(_row("not your row? plan=claude-pro-20 · plan=usd:29 for anything"[: W - 4]))
    return L
