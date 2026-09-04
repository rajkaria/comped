import json
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from .prices import _bundled

BUNDLED = _bundled("plans.json")


def load_plans(path: Optional[Path] = None) -> dict:
    return json.loads(Path(path or BUNDLED).read_text(encoding="utf-8"))


def parse_plan_ids(raw: str) -> List[str]:
    return [p.strip().lower() for p in (raw or "").split(",") if p.strip()]


def plan_cost(plan_ids: List[str], days_back: int, plans: dict) -> Tuple[Optional[Decimal], List[str], List[str]]:
    notes, resolved, total = [], [], Decimal("0")
    mean_days = Decimal(str(plans["meta"].get("mean_month_days", "30.4375")))
    for pid in plan_ids:
        entry = plans["plans"].get(pid)
        if entry is None:
            notes.append("unknown plan id '{0}' ignored; valid: {1}".format(pid, ", ".join(sorted(plans["plans"]))))
            continue
        if entry.get("monthly_usd") is None:
            notes.append("plan '{0}' has no monthly price; multiplier not computed".format(pid))
            continue
        resolved.append(pid)
        total += Decimal(str(entry["monthly_usd"])) * Decimal(int(days_back)) / mean_days
    if not resolved:
        return None, resolved, notes
    return total, resolved, notes
