"""GET /api/leaderboard?sort=multiplier|comped_usd&limit=100: the board, as JSON.

Reply: {"ok": true, "sort": str, "count": n, "submissions": n, "updated": iso|null, "rows": [
          {"rank", "handle", "anonymous", "multiplier", "tier", "comped_usd", "plan_usd", "plan", "plan_id",
           "plan_source", "providers", "harnesses", "days_back", "active_days", "cache_share", "runs",
           "first_seen", "updated_at"}], "rules": {...}}
Rows are one per handle (latest run wins) or one per anonymous device; a device id is never in a reply.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import StorageError, preflight, reply, rpc  # noqa: E402

SORTS = ("multiplier", "comped_usd")
DEFAULT_LIMIT, MAX_LIMIT = 100, 500
RULES = {
    "ranks_from_usd": 20, "ranks_from_active_days": 3,
    "held_above_multiplier": 2000, "held_above_usd": 250000,
    "primary_sort": "multiplier", "tie_break": ["comped_usd", "active_days", "first to post"],
    "one_row_per": "handle (latest run), or per anonymous device",
}


def board(query, opener=None):
    """Returns (status, body, cache header)."""
    q = parse_qs(query or "")
    sort = (q.get("sort") or ["multiplier"])[0]
    if sort not in SORTS:
        return 400, {"ok": False, "error": "sort must be one of {0}".format(", ".join(SORTS))}, "no-store"
    try:
        limit = int((q.get("limit") or [DEFAULT_LIMIT])[0])
    except ValueError:
        return 400, {"ok": False, "error": "limit must be an integer"}, "no-store"
    limit = max(1, min(MAX_LIMIT, limit))
    try:
        result = rpc("comped_board", {"p_sort": sort, "p_limit": limit}, opener=opener)
    except StorageError as e:
        return 502, {"ok": False, "error": "leaderboard storage unavailable ({0})".format(e)}, "no-store"
    if not isinstance(result, dict) or not result.get("ok"):
        return 502, {"ok": False, "error": "leaderboard storage answered with something unexpected"}, "no-store"
    result["limit"] = limit
    result["rules"] = RULES
    # s-maxage is for the edge. No max-age or stale-while-revalidate for browsers: Chrome honours the
    # latter and would show a reader the board from before their own run posted.
    return 200, result, "public, max-age=0, must-revalidate, s-maxage=30"


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        preflight(self)

    def do_GET(self):
        status, body, cache = board(urlsplit(self.path).query)
        reply(self, status, body, cache=cache)

    def do_POST(self):
        reply(self, 405, {"ok": False, "error": "scores are posted to /api/score"})

    def log_message(self, fmt, *args):
        pass
