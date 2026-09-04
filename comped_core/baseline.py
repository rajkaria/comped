import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from typing import Optional

from .timeutil import iso, parse_ts

NAME = "comped-baseline.json"


def load_baseline(out_dir: Path) -> Optional[dict]:
    p = Path(out_dir).expanduser() / NAME
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def save_baseline(out_dir: Path, s, clusters, now: datetime) -> str:
    p = Path(out_dir).expanduser() / NAME
    doc = {"saved_at": iso(now), "total_usd": str(s.total_usd),
           "multiplier": (str(s.multiplier) if s.multiplier is not None else None),
           "per_model": {m["model"]: str(m["usd"]) for m in s.per_model},
           "repeats": sorted(c.label for c in clusters)}
    p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return str(p)


def delta(prev: Optional[dict], s, clusters, now: datetime) -> dict:
    if not prev:
        return {"first_run": True, "days_since": 0, "total_usd_delta": Decimal("0"), "multiplier_delta": None,
                "new_repeats": [], "resolved_repeats": [], "per_model_delta": []}
    then = parse_ts(prev.get("saved_at"))
    days = (now - then).days if then else 0
    pm = {k: Decimal(v) for k, v in (prev.get("per_model") or {}).items()}
    cur = {m["model"]: m["usd"] for m in s.per_model}
    per_model = [{"model": m, "delta": cur.get(m, Decimal("0")) - pm.get(m, Decimal("0"))} for m in sorted(set(cur) | set(pm))]
    labels = {c.label for c in clusters}
    old = set(prev.get("repeats") or [])
    md = None
    if s.multiplier is not None and prev.get("multiplier") is not None:
        md = s.multiplier - Decimal(prev["multiplier"])
    return {"first_run": False, "days_since": days, "total_usd_delta": s.total_usd - Decimal(prev.get("total_usd", "0")),
            "multiplier_delta": md, "new_repeats": sorted(labels - old), "resolved_repeats": sorted(old - labels),
            "per_model_delta": per_model}
