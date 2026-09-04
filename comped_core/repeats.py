from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List

from .models import HumanMessage
from .textnorm import normalize, shingles, jaccard, is_excluded

JACCARD_MIN = 0.5
ZERO = Decimal("0")
CENT = Decimal("0.01")


@dataclass
class RepeatCluster:
    label: str
    count: int
    sessions: int
    days: int
    total_usd: Decimal
    repeat_usd: Decimal
    dividend_98: Decimal
    dividend_80: Decimal
    capture_command: str
    members: List[str]


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def find_repeats(humans: List[HumanMessage], per_turn_usd: Dict[str, Decimal], threshold: int, handle: str) -> List[RepeatCluster]:
    cand = [h for h in humans if is_excluded(h) is None]
    sh = [shingles(normalize(h.text)) for h in cand]
    parent = list(range(len(cand)))
    for i in range(len(cand)):
        if not sh[i]:
            continue
        for j in range(i + 1, len(cand)):
            if sh[j] and jaccard(sh[i], sh[j]) >= JACCARD_MIN:
                ri, rj = _find(parent, i), _find(parent, j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups: Dict[int, List[int]] = {}
    for i in range(len(cand)):
        groups.setdefault(_find(parent, i), []).append(i)
    out = []
    for idxs in groups.values():
        if len(idxs) < max(2, int(threshold)):
            continue
        ms = [cand[i] for i in idxs]
        sessions = {(m.harness, m.session_id) for m in ms}
        days = {m.timestamp[:10] for m in ms}
        if len(sessions) < 2 or len(days) < 2:
            continue
        costs = [per_turn_usd.get(m.message_id, ZERO) for m in ms]
        total = sum(costs, ZERO)
        repeat = total - min(costs)
        # This card ranks repeats by what re-asking cost. Once a ledger is priced, a cluster with no
        # attributed cost never anchored a turn -- harness boilerplate, not an ask -- so it is dropped
        # rather than shown at $0.00. With no cost data at all, every qualifying cluster still shows.
        if per_turn_usd and repeat <= ZERO:
            continue
        best = max(idxs, key=lambda i: (sum(jaccard(sh[i], sh[j]) for j in idxs if j != i), -len(cand[i].text), cand[i].message_id))
        label = " ".join(cand[best].text.split())[:120].rstrip("…").strip()
        h = handle.strip() or "<handle>"
        out.append(RepeatCluster(label, len(ms), len(sessions), len(days), total, repeat,
                                 (repeat * Decimal("0.98")).quantize(CENT), (repeat * Decimal("0.80")).quantize(CENT),
                                 '/play settle {0} "{1}"'.format(h, label), sorted(m.message_id for m in ms)))
    return sorted(out, key=lambda c: (-c.repeat_usd, -c.count, c.label))
