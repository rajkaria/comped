import json, re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional, Tuple

from .prices import _bundled

BUNDLED = _bundled("plans.json")
# A provider whose subscription is not in the table -- a GLM coding plan, a team seat, a bundle --
# is still a number you know. `usd:29` or `$29` prices it without the table having to guess.
CUSTOM = re.compile(r"^(?:usd:|\$)\s*(\d+(?:\.\d+)?)$")
AUTO = "auto"


def load_plans(path: Optional[Path] = None) -> dict:
    return json.loads(Path(path or BUNDLED).read_text(encoding="utf-8"))


def parse_plan_ids(raw: str) -> List[str]:
    return [p.strip().lower() for p in (raw or "").split(",") if p.strip()]


def is_auto(plan_ids: List[str]) -> bool:
    """Auto is the default: work the plan out from the logs rather than asking for it."""
    return any(p == AUTO for p in plan_ids)


def plan_entry(pid: str, plans: dict) -> Optional[dict]:
    """The plan table's row for an id, or a synthesised one for a `usd:<amount>` price."""
    entry = plans["plans"].get(pid)
    if entry is not None:
        return entry
    m = CUSTOM.match(pid or "")
    if not m:
        return None
    try:
        amount = Decimal(m.group(1))
    except InvalidOperation:
        return None
    return {"label": "your plan (${0:g}/mo)".format(float(amount)), "monthly_usd": str(amount),
            "vendor": "any", "source_url": "", "custom": True}


def plan_label(pid: str, plans: dict) -> str:
    entry = plan_entry(pid, plans)
    return entry["label"] if entry else pid


def monthly_usd(pid: str, plans: dict) -> Optional[Decimal]:
    entry = plan_entry(pid, plans)
    if entry is None or entry.get("monthly_usd") is None:
        return None
    return Decimal(str(entry["monthly_usd"]))


def plan_cost(plan_ids: List[str], days_back: int, plans: dict) -> Tuple[Optional[Decimal], List[str], List[str]]:
    notes, resolved, total = [], [], Decimal("0")
    mean_days = Decimal(str(plans["meta"].get("mean_month_days", "30.4375")))
    for pid in plan_ids:
        if pid == AUTO:
            continue
        entry = plan_entry(pid, plans)
        if entry is None:
            notes.append("unknown plan id '{0}' ignored; valid: {1}, auto, or usd:<amount>".format(
                pid, ", ".join(sorted(plans["plans"]))))
            continue
        if entry.get("monthly_usd") is None:
            notes.append("plan '{0}' has no monthly price; multiplier not computed".format(pid))
            continue
        resolved.append(pid)
        total += Decimal(str(entry["monthly_usd"])) * Decimal(int(days_back)) / mean_days
    if not resolved:
        return None, resolved, notes
    return total, resolved, notes
