import base64
import json
from decimal import Decimal

from .render_terminal import render_terminal
from .tiers import tier, score

PRIVACY = ("Reads: session logs under the configured directories. Nothing else. Never reads: ~/.claude.json, ~/.codex/auth.json, any credential, "
           "keychain or token file; the plan is inferred from the model ids already in those logs, never from your account. "  # PRIVACY text, not paths
           "Never sends: no network calls of any kind. Writes: only under out_dir, listed below. "
           "Message text: truncated to 120 characters and hashed by default.")


def money(d: Decimal) -> str:
    return "${0:,.2f}".format(d)


def share_text(v: dict) -> str:
    """The post. Leads with the score and the tier, because that is what people compare; the rank
    when the score has been posted; the receipt is the second sentence, and the site is the call."""
    site = (v.get("site") or "https://gotcomped.com").replace("https://", "")
    total = money(v["total_usd"]).split(".")[0]
    m = v.get("multiplier")
    t = v.get("tier") or tier(m)
    who = _vendor_word(v)
    rank, of = v.get("rank"), v.get("rank_of")
    where = ", #{0} of {1} on the {2} leaderboard".format(rank, of, site) if rank and of else ""
    if m is None:
        return ("{0} of AI at full price in the last {1} days, comped by my subscription. What's your comp score? "
                "One line: {2} #gotcomped".format(total, v["window_days"], site))
    return ("My comp score is {0} ({1}){2}. {3} gave me {4} of AI for {5} this month. "
            "What's yours? One line: {6} #gotcomped".format(
                score(m), t["name"], where, who, total, money(v["plan_cost"]).split(".")[0], site))


def _round(x, places):
    """A Decimal, a float or None, as a JSON number the browser can read back."""
    if x is None:
        return None
    return round(float(x), places)


def card_url(v: dict) -> str:
    """A link that draws this card on the site, as a picture you can download and post.

    The numbers ride in the fragment -- everything after the "#" -- and a browser never puts the
    fragment in a request, so opening this uploads nothing: the page rebuilds the card locally.
    What it carries is exactly the field list the leaderboard row already holds (score, tier, the
    list-price total, the plan it was scored against, which AIs and tools were found, the window,
    active days, sessions and cache-read share). No paths, no prompts, no model ids.
    """
    site = (v.get("site") or "https://gotcomped.com").rstrip("/")
    det = v.get("detected") or {}
    handle = v.get("handle") or ""
    if handle.startswith("<"):  # the CLI's placeholder for "you did not give one"
        handle = ""
    m = v.get("multiplier")
    t = v.get("tier") or tier(m)
    doc = {"v": 1, "h": handle[:32], "m": _round(m, 4), "t": (t or {}).get("name", ""),
           "u": _round(v.get("total_usd"), 2) or 0, "p": _round(v.get("plan_cost"), 2),
           "pl": " + ".join(v.get("plan_labels") or [])[:60],
           "pv": [p["key"] for p in det.get("providers", []) if p.get("records")][:6],
           "hs": [h["harness"] for h in det.get("harnesses", []) if h.get("records")][:6],
           "d": int(v.get("window_days") or 30), "a": int(v.get("active_days") or 0),
           "c": _round(v.get("cache_share"), 4), "s": int(v.get("sessions") or 0)}
    if v.get("rank") and v.get("rank_of"):
        doc["r"], doc["n"] = int(v["rank"]), int(v["rank_of"])
    blob = base64.urlsafe_b64encode(json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return "{0}/card.html#c={1}".format(site, blob.decode("ascii").rstrip("="))


def _vendor_word(v: dict) -> str:
    provs = [p for p in (v.get("detected") or {}).get("providers", []) if p.get("records")]
    names = [p["label"] for p in provs[:2]]
    return " and ".join(names) if names else "My subscription"


def render_report(v: dict) -> str:
    # The card is normally rendered by the CLI and passed in; render it here when a caller
    # builds the view without one, so the report never depends on call order.
    card = v.get("terminal_card") or render_terminal(v, False)
    o = ["# Comped report · last {0} days".format(v["window_days"]), "", "## Card", "", "```", card, "```", "", share_text(v), "",
         "The same card as a picture, drawn in your browser and ready to download: " + card_url(v),
         "", "## Models", "",
         "| model | usd | share |", "|---|---|---|"] + ["| {0} | {1} | {2:.0f}% |".format(m["model"], money(m["usd"]), float(m["share"]) * 100) for m in v["per_model"]]
    o += ["", "## Detected", "",
          "Worked out from the model ids in your own logs -- nothing was typed and no account was read.", "",
          "| provider | what you call it | models | records | usd |", "|---|---|---|---|---|"]
    for pr in (v.get("detected") or {}).get("providers", []):
        o.append("| {0} | {1} | {2} | {3} | {4} |".format(
            pr["label"], pr["talk_to"], ", ".join(pr["models"]) or "-", pr["records"], money(Decimal(str(pr.get("usd", 0))))))
    if not (v.get("detected") or {}).get("providers"):
        o.append("| - | - | - | 0 | $0.00 |")
    o += ["", "Harnesses: " + (", ".join("{0} ({1} files)".format(h["label"], h["files"])
                                         for h in (v.get("detected") or {}).get("harnesses", []) if h["found"]) or "none found") + ".",
          "Not installed here: " + (", ".join(h["label"] for h in (v.get("detected") or {}).get("harnesses", []) if not h["found"]) or "none") + "."]
    ladder = v.get("plan_ladder") or []
    if ladder:
        o += ["", "## If you're on", "",
              "The one thing a log cannot tell you is which tier you pay for -- a Pro session and a Max session are the same bytes. "
              "So every tier the detected providers sell is priced here at once, and the assumed row is the least flattering of them. "
              "Override with `plan=<id>`, or `plan=usd:<amount>` for a subscription this table does not carry.", "",
              "| plan | cost for the window | multiplier | |", "|---|---|---|---|"]
        o += ["| {0} | {1} | {2} | {3} |".format(
            r["label"], money(r["cost"]), "{0:.1f}x".format(r["multiplier"]) if r["multiplier"] is not None else "-",
            "assumed" if r["assumed"] else "") for r in ladder]
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
