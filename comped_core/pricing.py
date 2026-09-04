from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict, Tuple

from .models import UsageRecord, Ledger
from .prices import resolve_model
from .plans import plan_cost, plan_label, is_auto
from .detect import detect_stack, infer_plans, attach_costs, summary_line
from .timeutil import window_start, parse_ts, day_key, iso

ZERO = Decimal("0")


@dataclass
class PricedSummary:
    total_usd: Decimal
    per_model: list
    unpriced: list
    cache_share: Decimal
    active_days: int
    sessions: int
    per_turn_usd: Dict[str, Decimal]
    plan_cost: Optional[Decimal]
    multiplier: Optional[Decimal]
    plan_ids: list
    explain: List[str] = field(default_factory=list)
    window_start: str = ""
    window_end: str = ""
    price_meta: dict = field(default_factory=dict)
    records_in_window: int = 0
    detected: dict = field(default_factory=dict)
    plan_ladder: list = field(default_factory=list)
    plan_source: str = "typed"


def usd_for(r: UsageRecord, table: dict) -> Tuple[Decimal, Optional[str]]:
    key = resolve_model(r.model, table)
    if key is None:
        return ZERO, None
    p = table["models"][key]
    return (Decimal(r.input_tokens) * p["in"] + Decimal(r.cache_write_tokens) * p["cache_write"]
            + Decimal(r.cache_read_tokens) * p["cache_read"] + Decimal(r.output_tokens) * p["out"]), key


def price_ledger(led: Ledger, table: dict, plans: dict, plan_ids: list, days_back: int, now: datetime) -> PricedSummary:
    start = window_start(now, days_back)
    groups: Dict[str, dict] = {}
    unpriced: Dict[str, dict] = {}
    per_turn: Dict[str, Decimal] = {}
    total = ZERO
    cache_read = 0
    inp_all = 0
    days = set()
    sessions = set()
    in_window = []
    n = 0
    for r in led.records:
        ts = parse_ts(r.timestamp)
        if ts is None or ts < start or ts > now:
            continue
        n += 1
        in_window.append(r)
        sessions.add((r.harness, r.session_id))
        days.add(day_key(ts))
        usd, key = usd_for(r, table)
        toks = r.input_tokens + r.cache_write_tokens + r.cache_read_tokens + r.output_tokens
        cache_read += r.cache_read_tokens
        inp_all += r.input_tokens + r.cache_write_tokens + r.cache_read_tokens
        if key is None:
            u = unpriced.setdefault(r.model or "(blank)", {"model": r.model or "(blank)", "records": 0, "tokens": 0})
            u["records"] += 1
            u["tokens"] += toks
            continue
        g = groups.setdefault(r.model, {"model": r.model, "key": key, "usd": ZERO, "input": 0, "cache_write": 0,
                                        "cache_read": 0, "output": 0, "records": 0, "priced": True})
        g["usd"] += usd
        g["input"] += r.input_tokens
        g["cache_write"] += r.cache_write_tokens
        g["cache_read"] += r.cache_read_tokens
        g["output"] += r.output_tokens
        g["records"] += 1
        total += usd
        per_turn[r.turn_id] = per_turn.get(r.turn_id, ZERO) + usd
    per_model = sorted(groups.values(), key=lambda g: (-g["usd"], g["model"]))

    # Who you are actually running, worked out from the ids in the records rather than asked for.
    detected = attach_costs(detect_stack(in_window, led.sources, table),
                            dict([(g["model"], g["usd"]) for g in groups.values()]
                                 + [(u["model"], ZERO) for u in unpriced.values()]), ZERO)
    auto = is_auto(plan_ids)
    notes = []
    if auto:
        effective, candidates, notes = infer_plans(detected, plans)
    else:
        effective = [p for p in plan_ids if p != "auto"]
        candidates = [pid for prov in detected["providers"] for pid in prov["plans"]]
    cost, resolved, plan_notes = plan_cost(effective, days_back, plans)
    notes = notes + plan_notes
    mult = (total / cost) if cost and cost > 0 else None
    ladder = _ladder(candidates, resolved, total, days_back, plans)
    explain = ["window {0} .. {1} ({2} days), {3} priced+unpriced records, price table {4} from {5}".format(
        iso(start), iso(now), days_back, n, table["meta"].get("as_of"), table["meta"].get("source_url"))]
    for g in per_model:
        p = table["models"][g["key"]]
        explain.append("{0} -> {1}: input {2}x{3} + cache_write {4}x{5} + cache_read {6}x{7} + output {8}x{9} = ${10:.4f} over {11} records".format(
            g["model"], g["key"], g["input"], p["in"], g["cache_write"], p["cache_write"],
            g["cache_read"], p["cache_read"], g["output"], p["out"], g["usd"], g["records"]))
    for u in sorted(unpriced.values(), key=lambda u: u["model"]):
        explain.append("UNPRICED {0}: {1} records, {2} tokens (no rate in table; never estimated)".format(
            u["model"], u["records"], u["tokens"]))
    explain.append("detected: {0} (basis: {1}); plan {2}: {3}".format(
        summary_line(detected), detected["basis"], "inferred" if auto else "as typed",
        " + ".join(plan_label(p, plans) for p in resolved) or "none priced"))
    for row in ladder:
        explain.append("ladder {0}: ${1:.2f} for {2} days -> {3}{4}".format(
            row["label"], row["cost"], days_back,
            "{0:.2f}x".format(row["multiplier"]) if row["multiplier"] is not None else "n/a",
            "  <- assumed" if row["assumed"] else ""))
    if cost is not None:
        explain.append("plan cost: {0} prorated {1}/{2} days = ${3:.4f}; multiplier = {4:.4f}/{5:.4f} = {6:.4f}".format(
            " + ".join(resolved), days_back, plans["meta"].get("mean_month_days"), cost, total, cost, mult))
    else:
        explain.append("plan cost: not computed (no priced plan given); card shows list-price total only")
    explain += ["note: {0}".format(x) for x in notes]
    for s in led.sources:
        explain.append("source {0} at {1}: found={2} files={3} lines={4} parsed={5} duplicates_removed={6} unparsed={7} {8}".format(
            s.harness, s.root, s.found, s.files, s.lines, s.parsed, s.duplicates, s.unparsed, s.note).rstrip())
    return PricedSummary(total, per_model, sorted(unpriced.values(), key=lambda u: u["model"]),
                         (Decimal(cache_read) / Decimal(inp_all)) if inp_all else ZERO, len(days), len(sessions), per_turn,
                         cost, mult, resolved, explain, iso(start), iso(now), dict(table["meta"]), n,
                         detected, ladder, "auto" if auto else "typed")


def _ladder(candidates: list, resolved: list, total: Decimal, days_back: int, plans: dict) -> list:
    """Every subscription the detected providers sell, priced against this window's spend.

    The tier is the one fact the logs do not carry, so instead of asking for it the card shows all
    of them and highlights the one it assumed. Reading your own row costs a glance; typing your
    plan cost a re-run.
    """
    rows, seen = [], set()
    ids = list(candidates) + [p for p in resolved if p not in candidates]
    if len(resolved) > 1:
        ids.append(tuple(resolved))
    for pid in ids:
        combo = list(pid) if isinstance(pid, tuple) else [pid]
        key = "+".join(combo)
        if key in seen:
            continue
        seen.add(key)
        cost, ok, _ = plan_cost(combo, days_back, plans)
        if cost is None:
            continue
        rows.append({"plan_id": key, "label": " + ".join(plan_label(p, plans) for p in ok),
                     "cost": cost, "multiplier": (total / cost) if cost > 0 else None,
                     "assumed": ok == resolved})
    rows.sort(key=lambda r: (r["cost"], r["label"]))
    return rows
