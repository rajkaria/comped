#!/usr/bin/env python3
"""reply-debt's network half: read recent mail headers and normalise them into the Play's partial.

`daily_core` is proven network-free by `tests/test_daily_safety.py` and does the ageing and the
arithmetic; this file is the only part of the Play that opens a connection, and it is deliberately
small enough to read in full before you run it -- the same split `leaderboard/post_score.py` uses
for comped.

What leaves the machine, and what does not:

    Sent: authenticated GETs to https://gmail.googleapis.com/gmail/v1/users/me -- the thread list
          for the window you chose, then one metadata read per thread. Nothing is sent anywhere
          else.
    Never: this file composes nothing, saves no draft, marks nothing read, and sends no mail. It
           calls three read methods and no others; there is no code path here that writes to a
           mailbox.
    Asked for: `format=metadata` with a fixed header list, so Gmail returns headers and its own
          one-line snippet -- not message bodies, not attachments.
    Kept: `<out_dir>/<partial>`, the schema documented at the top of
          `daily_core/scan/replydebt.py`.

The credential:

    This file opens no keychain, no token file and no browser. It reads one OAuth access token out
    of the environment variable you name with `--token-env` (default GMAIL_OAUTH_TOKEN), scoped
    https://www.googleapis.com/auth/gmail.metadata or gmail.readonly, and uses it for these
    requests only. It is never written to disk, never printed, and never put in the partial.

    --demo true    writes nothing, reads no environment variable and opens no connection.
    no token       prints what is missing and exits 0. The read step then reports the absence and
                   the Play still runs; it just has no threads to age.
"""
import argparse
import json
import os
import ssl
import sys
import time
from email.utils import getaddresses, parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = 1
BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
PARTIAL = ".reply-debt-mail.json"
DEFAULT_TOKEN_ENV = "GMAIL_OAUTH_TOKEN"
USER_AGENT = "reply-debt/0.1.0 (+https://play.modiqo.ai/rajkaria/reply-debt)"
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
              "/etc/pki/tls/certs/ca-bundle.crt")
HEADERS = ("From", "To", "Cc", "Date", "Subject", "List-Id", "List-Unsubscribe",
           "Auto-Submitted", "Precedence", "Content-Type")
PAGE = 100


def _bool(s) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def _out(text: str, doc: dict) -> int:
    if text:
        print(text)
    print(json.dumps(doc, sort_keys=True))
    return 0


def _context():
    try:
        return ssl.create_default_context()
    except Exception:                                            # pragma: no cover - exotic build
        return None


def _bundle_context():
    for path in CA_BUNDLES:
        if os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:                                    # pragma: no cover - unreadable
                continue
    return None


def get(url: str, token: str, timeout: float, context) -> tuple:
    """(document, error). A refused or expired token is an error string, never a traceback."""
    req = Request(url, headers={"Authorization": "Bearer " + token,
                                "User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read(16 * 1024 * 1024)
    except HTTPError as exc:
        if exc.code in (401, 403):
            return None, ("the mailbox refused the token (HTTP {0}); it may have expired or may "
                          "lack the gmail.metadata scope".format(exc.code))
        return None, "HTTP {0}".format(exc.code)
    except (URLError, OSError, ValueError) as exc:
        return None, str(getattr(exc, "reason", exc))[:160]
    try:
        return json.loads(raw.decode("utf-8", "replace")), ""
    except ValueError:
        return None, "the mailbox did not return JSON"


# ---------------------------------------------------------------- normalisation
#
# Gmail's own document into the shape daily_core/scan/replydebt.py documents. Everything here is
# header text; no body is requested and none is stored.

def people(value: str) -> list:
    """"A <a@x>, b@y" -> [{"name": ..., "email": ...}]. Malformed pairs are dropped, not guessed."""
    out = []
    for name, addr in getaddresses([value or ""]):
        addr = (addr or "").strip()
        if "@" not in addr:
            continue
        out.append({"name": (name or "").strip(), "email": addr})
    return out


def _date(value: str) -> str:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def message(raw: dict, me: list) -> dict:
    """One Gmail message as one partial message, or {} when it has no usable From or Date."""
    headers = {}
    for h in ((raw.get("payload") or {}).get("headers") or []):
        key = str(h.get("name") or "").lower()
        if key and key not in headers:
            headers[key] = str(h.get("value") or "")
    sender = people(headers.get("from", ""))
    date = _date(headers.get("date", ""))
    if not sender or not date:
        return {}
    labels = [str(x) for x in (raw.get("labelIds") or [])]
    mine = {a.lower() for a in me}
    automated = bool(headers.get("auto-submitted", "").strip().lower() not in ("", "no")
                     or headers.get("precedence", "").strip().lower() in ("bulk", "list", "junk")
                     or headers.get("list-id"))
    return {"from": sender[0],
            "to": people(headers.get("to", "")),
            "cc": people(headers.get("cc", "")),
            "date": date,
            "direction": "outbound" if sender[0]["email"].lower() in mine else "inbound",
            "subject": headers.get("subject", ""),
            "snippet": str(raw.get("snippet") or ""),
            "labels": labels,
            "is_automated": automated,
            "list_id": headers.get("list-id", ""),
            "list_unsubscribe": headers.get("list-unsubscribe", ""),
            "is_calendar": "text/calendar" in headers.get("content-type", "").lower()}


def thread(raw: dict, me: list) -> dict:
    """One Gmail thread as one partial thread, or {} when nothing in it survived normalisation."""
    messages = [m for m in (message(x, me) for x in (raw.get("messages") or [])) if m]
    if not messages:
        return {}
    messages.sort(key=lambda m: m["date"])
    seen, participants = set(), []
    for m in messages:
        for person in [m["from"]] + m["to"] + m["cc"]:
            key = person["email"].lower()
            if key not in seen:
                seen.add(key)
                participants.append(person)
    labels = []
    for m in messages:
        for label in m["labels"]:
            if label not in labels:
                labels.append(label)
    return {"thread_id": str(raw.get("id") or ""), "subject": messages[0]["subject"],
            "labels": labels, "participants": participants, "messages": messages}


def partial_path(out_dir: str, partial: str) -> str:
    raw = os.path.expanduser(str(partial or PARTIAL))
    return raw if os.path.isabs(raw) else os.path.join(out_dir, raw)


def build_parser():
    """The step's command line, built where a test can reach it without running anything."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out-dir", default="~/daily")
    p.add_argument("--demo", default="false")
    p.add_argument("--partial", default=PARTIAL)
    p.add_argument("--days", default="120")
    p.add_argument("--max-threads", default="400")
    p.add_argument("--query", default="-in:chats", help="extra Gmail search terms")
    p.add_argument("--token-env", default=DEFAULT_TOKEN_ENV)
    p.add_argument("--timeout", default="20")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)

    out_dir = os.path.expanduser(str(a.out_dir))
    target = partial_path(out_dir, a.partial)
    if _bool(a.demo):
        return _out("demo run: no environment variable was read and no connection was opened; "
                    "the report reads the bundled mailbox fixture.",
                    {"ok": True, "available": False, "demo": True, "threads": 0,
                     "warning": "demo run: the bundled mailbox fixture is used"})

    name = str(a.token_env or DEFAULT_TOKEN_ENV)
    token = str(os.environ.get(name) or "").strip()
    if not token:
        return _out("no access token in ${0}, so nothing was fetched. Export a Gmail OAuth "
                    "access token with the gmail.metadata scope into that variable, or leave it "
                    "unset and run with demo=true.".format(name),
                    {"ok": True, "available": False, "threads": 0,
                     "warning": "no mail credential was offered; nothing was fetched"})

    context = _context()
    timeout = max(1.0, float(a.timeout))
    profile, error = get(BASE + "/profile", token, timeout, context)
    if error and context is not None:
        fallback = _bundle_context()
        if fallback is not None:
            context = fallback
            profile, error = get(BASE + "/profile", token, timeout, context)
    if error:
        return _out("could not read the mailbox: {0}".format(error),
                    {"ok": True, "available": False, "threads": 0, "warning": error})
    account = str((profile or {}).get("emailAddress") or "")
    me = [account] if account else []

    days = max(1, int(a.days))
    limit = max(1, int(a.max_threads))
    query = "newer_than:{0}d {1}".format(days, str(a.query or "")).strip()
    ids, page_token, truncated = [], "", False
    while len(ids) < limit:
        params = {"maxResults": str(min(PAGE, limit - len(ids))), "q": query}
        if page_token:
            params["pageToken"] = page_token
        doc, error = get(BASE + "/threads?" + urlencode(params), token, timeout, context)
        if error:
            return _out("could not list threads: {0}".format(error),
                        {"ok": True, "available": False, "threads": 0, "warning": error})
        ids += [str(t.get("id")) for t in (doc.get("threads") or []) if t.get("id")]
        page_token = str(doc.get("nextPageToken") or "")
        if not page_token:
            break
    else:
        truncated = bool(page_token)

    detail = "?" + urlencode([("format", "metadata")] + [("metadataHeaders", h) for h in HEADERS])
    threads, failed = [], 0
    for tid in ids[:limit]:
        doc, error = get("{0}/threads/{1}{2}".format(BASE, tid, detail), token, timeout, context)
        if error or doc is None:
            failed += 1
            continue
        item = thread(doc, me)
        if item.get("thread_id"):
            threads.append(item)

    partial = {"schema": SCHEMA, "account": account, "me": me,
               "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "truncated": truncated, "threads": threads}
    os.makedirs(out_dir, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(partial, indent=1, sort_keys=True) + "\n")
    doc = {"ok": True, "threads": len(threads), "days": days, "failed": failed,
           "truncated": truncated, "written": target}
    if failed:
        doc["warning"] = "{0} thread(s) could not be read and are not in the partial".format(failed)
    return _out("{0} thread(s) over {1} day(s) written to {2}.".format(
        len(threads), days, target), doc)


if __name__ == "__main__":
    sys.exit(main())
