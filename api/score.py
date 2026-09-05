"""POST /api/score: one run's card, in; its rank on the board, out.

Body: {"device": uuid, "handle": str, "multiplier": num|null, "comped_usd": num, "plan_usd": num|null,
       "tier": str, "plan": str, "plan_id": str, "plan_source": str, "providers": [str], "harnesses": [str],
       "days_back": int, "active_days": int, "sessions": int, "cache_share": num|null, "client": str}
Reply: {"ok": true, "rank": n|null, "of": n, "percentile": n|null, "eligible": bool, "held": bool,
        "reason": str|null, "handle": str, "url": str, "board": str}
   or  {"ok": false, "error": str} with 400 (bad input), 429 (same device inside 15 s) or 502 (storage).
"""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import StorageError, check_score, preflight, read_json, reply, rpc, with_links  # noqa: E402


def submit(payload, opener=None):
    """Validate, store, rank. Returns (status, body)."""
    err = check_score(payload)
    if err:
        return 400, {"ok": False, "error": err}
    try:
        result = rpc("comped_submit", {"p": payload}, opener=opener)
    except StorageError as e:
        return 502, {"ok": False, "error": "leaderboard storage unavailable ({0})".format(e)}
    if not isinstance(result, dict):
        return 502, {"ok": False, "error": "leaderboard storage answered with something unexpected"}
    if not result.get("ok"):
        return (429 if result.get("retry_after") else 400), result
    return 200, with_links(result)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        preflight(self)

    def do_GET(self):
        reply(self, 405, {"ok": False, "error": "POST a score here; the board is at /api/leaderboard"})

    def do_POST(self):
        payload, err = read_json(self)
        if err:
            return reply(self, 400, {"ok": False, "error": err})
        status, body = submit(payload)
        reply(self, status, body)

    def log_message(self, fmt, *args):  # no request logging beyond the platform's own
        pass
