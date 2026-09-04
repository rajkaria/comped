from decimal import Decimal

W = 64


def money(d: Decimal) -> str:
    return "${0:,.2f}".format(d)


def _c(s, code, on):
    return "\x1b[{0}m{1}\x1b[0m".format(code, s) if on else s


def _row(text: str, color_len=0) -> str:
    pad = W - 4 - (len(text) - color_len)
    return "│ " + text + " " * max(pad, 0) + " │"


def _bar(share: Decimal, width=12) -> str:
    return "▇" * max(0, min(width, int(round(float(share) * width))))


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
        L.append(_row("no plan given: list-price total only (set plan= to see your multiplier)"[: W - 4]))
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
    L.append(_row(""))
    L.append(_row("REPEAT OFFENDERS"))
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
