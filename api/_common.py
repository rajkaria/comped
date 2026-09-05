"""Shared plumbing for the two leaderboard functions (api/score.py, api/leaderboard.py).

Stdlib only, like everything else in this repo. Storage is a Postgres behind PostgREST; the two
functions call exactly two SQL functions, comped_submit and comped_board, with a publishable key.
Those SQL functions are the trust boundary: the table itself is closed to the API role, every
bound is enforced there, and the device id that keys a row is never returned by either call.
"""
import json
import os
import urllib.error
import urllib.request

SITE = "https://gotcomped.com"
BOARD_URL = SITE + "/leaderboard.html"
MAX_BODY = 32 * 1024
HANDLE_MAX = 32


class StorageError(RuntimeError):
    pass


def config():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise StorageError("leaderboard storage is not configured")
    return url, key


def rpc(name, args, timeout=10, opener=None):
    """POST one PostgREST RPC and return its JSON. `opener` is swapped in by the tests."""
    url, key = config()
    req = urllib.request.Request(
        "{0}/rest/v1/rpc/{1}".format(url, name), data=json.dumps(args).encode("utf-8"), method="POST",
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raise StorageError("storage answered {0}".format(e.code))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise StorageError("storage unreachable: {0}".format(e.__class__.__name__))


def reply(handler, status, obj, cache="no-store"):
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def preflight(handler):
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Max-Age", "86400")
    handler.end_headers()


def read_json(handler):
    """The request body as a dict, or (None, error)."""
    try:
        n = int(handler.headers.get("content-length") or 0)
    except ValueError:
        return None, "bad content-length"
    if n <= 0:
        return None, "empty body"
    if n > MAX_BODY:
        return None, "body too large"
    raw = handler.rfile.read(n)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "body is not JSON"
    if not isinstance(doc, dict):
        return None, "body must be a JSON object"
    return doc, None


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_score(p):
    """Shape check before the database sees it; the SQL function re-checks every bound."""
    if not isinstance(p.get("device"), str) or len(p["device"]) != 36 or p["device"].count("-") != 4:
        return "device must be a uuid"
    handle = p.get("handle", "")
    if not isinstance(handle, str) or len(handle) > HANDLE_MAX:
        return "handle must be a string of at most {0} characters".format(HANDLE_MAX)
    if not _num(p.get("comped_usd")):
        return "comped_usd must be a number"
    for k in ("multiplier", "plan_usd", "cache_share"):
        if p.get(k) is not None and not _num(p[k]):
            return "{0} must be a number or null".format(k)
    for k in ("days_back", "active_days", "sessions"):
        if p.get(k) is not None and not _num(p[k]):
            return "{0} must be a number".format(k)
    for k in ("tier", "plan", "plan_id", "plan_source", "client"):
        if p.get(k) is not None and not isinstance(p[k], str):
            return "{0} must be a string".format(k)
    for k in ("providers", "harnesses"):
        v = p.get(k, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v) or len(v) > 12:
            return "{0} must be a short list of strings".format(k)
    return None


def with_links(result):
    """Where to look after a post: the board, and the row when there is a handle to anchor on."""
    handle = result.get("handle") or ""
    result["board"] = BOARD_URL
    result["url"] = BOARD_URL + ("#" + handle if handle else "")
    return result
