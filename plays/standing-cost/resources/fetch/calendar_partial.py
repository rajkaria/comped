#!/usr/bin/env python3
"""standing-cost's network half: fetch a calendar window and normalise it into the Play's partial.

`daily_core` is proven network-free by `tests/test_daily_safety.py` and does the arithmetic; this
file is the only part of the Play that opens a connection, and it is deliberately small enough to
read in full before you run it -- the same split `leaderboard/post_score.py` uses for comped.

What leaves the machine:

    Sent: one authenticated GET per page to https://www.googleapis.com/calendar/v3, asking for the
          events in the window you chose from the calendar you named. Nothing is sent anywhere
          else, nothing is uploaded, and nothing is written back to the calendar -- this is a read
          of `events.list` and nothing more.
    Kept: `<out_dir>/<partial>`, the schema documented at the top of
          `daily_core/scan/standingcost.py`. Attendee addresses are in it because the arithmetic
          needs to tell people apart; the card and the report reduce them to initials.

The credential:

    This file opens no keychain, no token file and no browser. It reads one OAuth access token out
    of the environment variable you name with `--token-env` (default GOOGLE_OAUTH_TOKEN), scoped
    https://www.googleapis.com/auth/calendar.readonly, and uses it for these requests only. It is
    never written to disk, never printed, and never included in the partial.

    --demo true    writes nothing, reads no environment variable and opens no connection.
    no token       prints what is missing and exits 0. The read step then reports the absence and
                   the Play still runs; it just has nothing to price.
"""
import argparse
import json
import os
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

SCHEMA = 1
BASE = "https://www.googleapis.com/calendar/v3/calendars/{0}/events"
PARTIAL = ".standing-cost-calendar.json"
DEFAULT_TOKEN_ENV = "GOOGLE_OAUTH_TOKEN"
USER_AGENT = "standing-cost/0.1.0 (+https://play.modiqo.ai/rajkaria/standing-cost)"
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
              "/etc/pki/tls/certs/ca-bundle.crt")
PAGE = 2500
MAX_PAGES = 20


def _bool(s) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def _out(text: str, doc: dict) -> int:
    if text:
        print(text)
    print(json.dumps(doc, sort_keys=True))
    return 0


def _context():
    for maker in (lambda: ssl.create_default_context(),):
        try:
            return maker()
        except Exception:                                        # pragma: no cover - exotic build
            pass
    return None


def _bundle_context():
    for path in CA_BUNDLES:
        if os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:                                    # pragma: no cover - unreadable
                continue
    return None


def _instant(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def get_page(url: str, token: str, timeout: float, context) -> tuple:
    """(document, error). An expired token is an error string, never a traceback."""
    req = Request(url, headers={"Authorization": "Bearer " + token,
                                "User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read(32 * 1024 * 1024)
    except HTTPError as exc:
        if exc.code in (401, 403):
            return None, ("the calendar refused the token (HTTP {0}); it may have expired or may "
                          "lack the calendar.readonly scope".format(exc.code))
        return None, "HTTP {0}".format(exc.code)
    except (URLError, OSError, ValueError) as exc:
        return None, str(getattr(exc, "reason", exc))[:160]
    try:
        return json.loads(raw.decode("utf-8", "replace")), ""
    except ValueError:
        return None, "the calendar did not return JSON"


# ---------------------------------------------------------------- normalisation
#
# Google's own document into the snake_case shape daily_core/scan/standingcost.py documents.
# An all-day event has `date` instead of `dateTime` and no clock time at all, so it is dropped
# rather than priced: a day marked "out of office" is not a meeting anybody sat in.

def _when(node) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("dateTime") or "")


def _attendee(raw: dict, default_zone: str) -> dict:
    email = str(raw.get("email") or "").strip()
    if not email:
        return {}
    out = {"email": email,
           "display_name": str(raw.get("displayName") or ""),
           "response_status": str(raw.get("responseStatus") or "needsAction"),
           "optional": bool(raw.get("optional")),
           "self": bool(raw.get("self")),
           "organizer": bool(raw.get("organizer"))}
    if default_zone:
        out["timezone"] = default_zone
    return out


def normalise(raw: dict, default_zone: str) -> dict:
    """One Google event as one partial event, or {} when it carries no clock time."""
    start, end = _when(raw.get("start")), _when(raw.get("end"))
    if not start or not end:
        return {}
    description = str(raw.get("description") or "")
    attachments = [str(a.get("fileUrl") or "") for a in (raw.get("attachments") or [])
                   if isinstance(a, dict) and a.get("fileUrl")]
    zone = str((raw.get("start") or {}).get("timeZone") or default_zone or "")
    return {
        "id": str(raw.get("id") or ""),
        "recurring_event_id": str(raw.get("recurringEventId") or ""),
        "summary": str(raw.get("summary") or ""),
        "start": start,
        "end": end,
        "status": str(raw.get("status") or "confirmed"),
        "organizer": str((raw.get("organizer") or {}).get("email") or ""),
        "agenda_link": attachments[0] if attachments else "",
        # Google records no attendance, only invitations, so `attendance_recorded` is false and
        # `attended` is never claimed. Pretending otherwise would bill people for a room they
        # were invited to and never entered.
        "has_agenda": len(description.strip()) >= 80,
        "attendance_recorded": False,
        "attendees": [a for a in (_attendee(x, zone) for x in (raw.get("attendees") or []))
                      if a],
    }


def partial_path(out_dir: str, partial: str) -> str:
    raw = os.path.expanduser(str(partial or PARTIAL))
    return raw if os.path.isabs(raw) else os.path.join(out_dir, raw)


def build_parser():
    """The step's command line, built where a test can reach it without running anything."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out-dir", default="~/daily")
    p.add_argument("--demo", default="false")
    p.add_argument("--partial", default=PARTIAL)
    p.add_argument("--calendar-id", default="primary")
    p.add_argument("--days", default="365")
    p.add_argument("--token-env", default=DEFAULT_TOKEN_ENV)
    p.add_argument("--timeout", default="20")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)

    out_dir = os.path.expanduser(str(a.out_dir))
    target = partial_path(out_dir, a.partial)
    if _bool(a.demo):
        return _out("demo run: no environment variable was read and no connection was opened; "
                    "the report reads the bundled calendar fixture.",
                    {"ok": True, "available": False, "demo": True, "events": 0,
                     "warning": "demo run: the bundled calendar fixture is used"})

    name = str(a.token_env or DEFAULT_TOKEN_ENV)
    token = str(os.environ.get(name) or "").strip()
    if not token:
        return _out("no access token in ${0}, so nothing was fetched. Export a Google OAuth "
                    "access token with the calendar.readonly scope into that variable, or leave "
                    "it unset and run with demo=true.".format(name),
                    {"ok": True, "available": False, "events": 0,
                     "warning": "no calendar credential was offered; nothing was fetched"})

    days = max(1, int(a.days))
    now = time.time()
    window = {"start": _instant(now - days * 86400.0), "end": _instant(now)}
    query = {"timeMin": window["start"], "timeMax": window["end"], "singleEvents": "true",
             "showDeleted": "true", "maxResults": str(PAGE), "orderBy": "startTime"}
    base = BASE.format(quote(str(a.calendar_id or "primary"), safe=""))
    context = _context()
    timeout = max(1.0, float(a.timeout))

    events, zone, truncated, page_token, pages = [], "", False, "", 0
    while pages < MAX_PAGES:
        params = dict(query)
        if page_token:
            params["pageToken"] = page_token
        doc, error = get_page(base + "?" + urlencode(params), token, timeout, context)
        if error and pages == 0 and context is not None:
            fallback = _bundle_context()
            if fallback is not None:
                context = fallback
                doc, error = get_page(base + "?" + urlencode(params), token, timeout, context)
        if error:
            return _out("could not read the calendar: {0}".format(error),
                        {"ok": True, "available": False, "events": 0, "warning": error})
        zone = zone or str(doc.get("timeZone") or "")
        for raw in (doc.get("items") or []):
            item = normalise(raw, zone)
            if item.get("id"):
                events.append(item)
        page_token = str(doc.get("nextPageToken") or "")
        pages += 1
        if not page_token:
            break
    else:
        truncated = True

    partial = {"schema": SCHEMA, "source": "google-calendar", "account": str(a.calendar_id or ""),
               "fetched": _instant(time.time()), "window": window, "timezone": zone,
               "truncated": truncated or bool(page_token),
               "note": "fetched by the Play's calendar step; attendance is not recorded by "
                       "Google, so only invitations are counted",
               "events": events}
    os.makedirs(out_dir, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(partial, indent=1, sort_keys=True) + "\n")
    return _out("{0} event(s) over {1} day(s) written to {2}.".format(
        len(events), days, target),
        {"ok": True, "events": len(events), "days": days, "pages": pages,
         "truncated": partial["truncated"], "written": target})


if __name__ == "__main__":
    sys.exit(main())
