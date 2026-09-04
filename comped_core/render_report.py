from decimal import Decimal

from .render_terminal import render_terminal

PRIVACY = ("Reads: session logs under the configured directories. Nothing else. Never reads: ~/.claude.json, ~/.codex/auth.json, any credential, "
           "keychain or token file; plan is typed by you. Never sends: no network calls of any kind. Writes: only under out_dir, listed below. "  # PRIVACY text, not paths
           "Message text: truncated to 120 characters and hashed by default.")


def money(d: Decimal) -> str:
    return "${0:,.2f}".format(d)


def share_text(v: dict) -> str:
    mult = " {0:.0f}×.".format(v["multiplier"]) if v.get("multiplier") is not None else ""
    plan = " on a {0} plan".format(money(v["plan_cost"])) if v.get("plan_cost") is not None else ""
    return ("I got comped {0}{1} in the last {2} days.{3} "
            "Measured from my own agent logs with the comped Play on @Modiqo's rote. Run it on yours: rote play run {4}".format(
                money(v["total_usd"]).split(".")[0], plan, v["window_days"], mult, v["play_uri"]))


def render_report(v: dict) -> str:
    # The card is normally rendered by the CLI and passed in; render it here when a caller
    # builds the view without one, so the report never depends on call order.
    card = v.get("terminal_card") or render_terminal(v, False)
    o = ["# Comped report · last {0} days".format(v["window_days"]), "", "## Card", "", "```", card, "```", "", share_text(v), "", "## Models", "",
         "| model | usd | share |", "|---|---|---|"] + ["| {0} | {1} | {2:.0f}% |".format(m["model"], money(m["usd"]), float(m["share"]) * 100) for m in v["per_model"]]
    o += ["", "## Sources", "", "| harness | found | files | duplicates removed | note |", "|---|---|---|---|---|"]
    o += ["| {0} | {1} | {2} | {3} | {4} |".format(s["harness"], s["found"], s["files"], s["duplicates"], s["note"]) for s in v["sources"]]
    o += ["", "## Repeat offenders", ""]
    if v["repeats"]:
        o += ["| asks | label | repeat cost | capture |", "|---|---|---|---|"] + [
            "| {0} | {1} | {2} | `{3}` |".format(r["count"], r["label"], money(r["repeat_usd"]), r["capture_command"]) for r in v["repeats"]]
        o += ["", "Codex and Cursor use `$play settle ...`; Kimi uses `/skill:play settle ...`."]
    else:
        o += ["None met the threshold (asked ≥ 3 times across ≥ 2 sessions on ≥ 2 days)."]
    o += ["", "## Rote dividend", "",
          "Repeat cost that a Play would have avoided: ${0:,.2f} at Modiqo's stated 98% reduction; ${1:,.2f} at a conservative 80%. "
          "Both are derived from repeat cost = cluster cost minus its cheapest solve.".format(v["dividend_98"], v["dividend_80"])]
    d = v.get("delta") or {}
    o += ["", "## Delta since last run", ""]
    o += ["First run: baseline saved."] if d.get("first_run") else [
        "{0} days since baseline: total {1}{2}; new repeats: {3}; resolved: {4}.".format(
            d["days_since"], "+" if d["total_usd_delta"] >= 0 else "", money(d["total_usd_delta"]),
            ", ".join(d["new_repeats"]) or "none", ", ".join(d["resolved_repeats"]) or "none")]
    o += ["", "## Unpriced models", ""] + (["- {0}: {1} records, {2:,} tokens (no rate in the table; never estimated)".format(
        u["model"], u["records"], u["tokens"]) for u in v["unpriced"]] or ["None."])
    o += ["", "## Methodology", "",
          "usd = uncached_input×in + cache_write×cw + cache_read×cr + output×out (reasoning bills as output). Claude Code lines deduplicated on "
          "(message.id, requestId); Codex per-turn values are differences of cumulative counters.",
          "Price table as of {0} from {1}. Plan prorated by days/30.4375. Full arithmetic: {2}.".format(
              v["price_as_of"], v["price_source"], v["explain_path"]),
          "", "## Privacy", "", PRIVACY, "", "Written:", ""] + ["- {0}".format(p) for p in v["written"]]
    o += ["", "See also: session-ledger (the normalized log this reads) and wrong-turns (your agent's recurring mistakes, with drafted rules)."]
    return "\n".join(o) + "\n"


def render_explain(summary) -> str:
    return "\n".join(summary.explain) + "\n"
