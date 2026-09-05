#!/usr/bin/env python3
"""Post the score on this machine's card to the gotcomped.com leaderboard, and print the rank.

This is the one step of the comped Play that talks to the network. It is kept out of comped_core
on purpose: the core stays verifiably offline (tests/test_no_network.py greps it for urllib), and
this file is the whole of what leaves the machine. Read it; it is short.

Sent, and nothing else: your handle (or nothing), the comp score, its tier, the list-price total,
the plan it was scored against and what that costs, which providers and tools were detected, the
window in days, active days, session count, cache-read share, and a random id so a re-run
replaces your row instead of adding one. No paths, no prompts, no model list, no hostnames.

    leaderboard=false   prints one line and exits without opening a connection.
    offline / refused   prints a warning and exits 0. A failed post never fails the run.

The exact payload is written to out_dir/comped-rank.json next to the reply, so you can see it.
"""
import argparse
import json
import os
import ssl
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

VERSION = "0.1.5"
DEFAULT_URL = "https://gotcomped.com/api/score"
BOARD_URL = "https://gotcomped.com/leaderboard.html"
DEVICE_FILE = "comped-device.txt"
RANK_FILE = "comped-rank.json"
SHARE_FILE = "comped-share.txt"
# macOS and most Linux distributions keep a CA bundle here; a python.org build on a Mac that never
# ran "Install Certificates.command" has none of its own, and urllib fails until it is pointed at one.
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")


def _bool(s):
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def device_id(out_dir: Path) -> str:
    """A random id, made once and kept in out_dir. It is the only key to your row: keep it."""
    p = out_dir / DEVICE_FILE
    if p.exists():
        v = p.read_text(encoding="utf-8").strip()
        try:
            return str(uuid.UUID(v))
        except ValueError:
            pass
    v = str(uuid.uuid4())
    out_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(v + "\n", encoding="utf-8")
    return v


def _plan(pr: dict):
    """(label, id) of the plan the card scored against: the assumed ladder row, else the typed one."""
    for r in pr.get("plan_ladder") or []:
        if r.get("assumed"):
            return r.get("label") or r.get("plan_id") or "", r.get("plan_id") or ""
    ids = pr.get("plan_ids") or []
    if not ids:
        return "", ""
    try:
        from comped_core.plans import load_plans, plan_label
        return " + ".join(plan_label(i, load_plans()) for i in ids), ids[0]
    except Exception:
        return " + ".join(ids), ids[0]


def _f(x, dp):
    return None if x is None else round(float(x), dp)


def payload(pr: dict, device: str, handle: str) -> dict:
    det = pr.get("detected") or {}
    label, plan_id = _plan(pr)
    return {
        "device": device, "handle": handle or "", "client": "comped/" + VERSION,
        "multiplier": _f(pr.get("multiplier"), 4), "comped_usd": _f(pr.get("total_usd"), 2) or 0.0,
        "plan_usd": _f(pr.get("plan_cost"), 2), "tier": (pr.get("tier") or {}).get("name", ""),
        "plan": label, "plan_id": plan_id, "plan_source": pr.get("plan_source", ""),
        "providers": [p["key"] for p in det.get("providers", []) if p.get("records")][:12],
        "harnesses": [h["harness"] for h in det.get("harnesses", []) if h.get("records")][:12],
        "days_back": int(pr.get("days_back") or 30), "active_days": int(pr.get("active_days") or 0),
        "sessions": int(pr.get("sessions") or 0), "cache_share": _f(pr.get("cache_share"), 4),
    }


def _urlopen(req, timeout, context=None):
    import urllib.request
    with urllib.request.urlopen(req, timeout=timeout, context=context) as r:
        return r.status, r.read().decode("utf-8")


def post(url: str, body: dict, timeout: float):
    """(status, text). Tries urllib with the default trust store, then the system CA bundle, then curl."""
    import urllib.error
    import urllib.request
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "comped/" + VERSION}
    contexts = [None] + [ssl.create_default_context(cafile=c) for c in CA_BUNDLES if os.path.exists(c)]
    last = None
    for ctx in contexts:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            return _urlopen(req, timeout, ctx)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except ssl.SSLCertVerificationError as e:
            last = "certificate verification failed ({0})".format(e.__class__.__name__)
            continue
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, ssl.SSLCertVerificationError):
                last = "certificate verification failed"
                continue
            raise
    # Python could not verify the server; curl uses the operating system's trust store. Fixed argv, no shell.
    try:
        r = subprocess.run(["curl", "-sS", "--max-time", str(int(timeout)), "-o", "-", "-w", "\n%{http_code}",
                            "-H", "Content-Type: application/json", "-H", "Accept: application/json",
                            "-A", headers["User-Agent"], "--data-binary", "@-", url],
                           input=data, capture_output=True, timeout=timeout + 5)
    except (OSError, subprocess.SubprocessError):
        raise OSError(last or "no way to open a TLS connection")
    if r.returncode != 0:
        raise OSError(last or r.stderr.decode("utf-8", "replace").strip() or "curl failed")
    text, _, code = r.stdout.decode("utf-8", "replace").rpartition("\n")
    return int(code or 0), text


def _money(x) -> str:
    return "${0:,.0f}".format(float(x))


def _score(m) -> str:
    m = float(m)
    return "{0:.1f}×".format(m) if m < 10 else "{0:.0f}×".format(m)


def rewrite_share(out_dir: Path, pr: dict, rank, of, handle: str) -> str:
    """Put the rank into the line that gets posted, and into the link that draws the card as a
    picture, using the core's own wording so neither drifts. Returns that link, or "" when the
    core is not importable from beside this script."""
    try:
        from comped_core.render_report import card_url, share_text
        from comped_core.tiers import tier
    except Exception:
        return ""
    m = Decimal(str(pr["multiplier"])) if pr.get("multiplier") is not None else None
    label, _id = _plan(pr)
    v = {"total_usd": Decimal(str(pr.get("total_usd") or "0")), "multiplier": m, "tier": pr.get("tier") or tier(m),
         "plan_cost": Decimal(str(pr["plan_cost"])) if pr.get("plan_cost") is not None else None,
         "detected": pr.get("detected") or {}, "window_days": pr.get("days_back", 30),
         "site": "https://gotcomped.com", "rank": rank, "rank_of": of, "handle": handle or "",
         "plan_labels": [label] if label else [], "active_days": pr.get("active_days") or 0,
         "sessions": pr.get("sessions") or 0, "cache_share": pr.get("cache_share")}
    (out_dir / SHARE_FILE).write_text(share_text(v) + "\n", encoding="utf-8")
    try:
        return card_url(v)
    except Exception:
        return ""


def finish(human: list, result: dict) -> int:
    print("\n".join(human))
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="post_score", description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", default="~/comped")
    ap.add_argument("--leaderboard", default="true", help="true posts; false sends nothing")
    ap.add_argument("--handle", default="", help="your name on the board; blank is anonymous")
    ap.add_argument("--url", default=os.environ.get("COMPED_LEADERBOARD_URL", DEFAULT_URL))
    ap.add_argument("--timeout", type=float, default=12.0)
    a = ap.parse_args(argv)
    out_dir = Path(a.out_dir).expanduser()

    if not _bool(a.leaderboard):
        return finish(["LEADERBOARD", "  skipped: leaderboard=false, so nothing was sent anywhere."],
                      {"posted": False, "skipped": True})
    priced = out_dir / ".priced.json"
    if not priced.exists():
        return finish(["LEADERBOARD", "  nothing to post: no priced card in {0}".format(out_dir)],
                      {"posted": False, "warning": "no priced card"})
    pr = json.loads(priced.read_text(encoding="utf-8"))
    handle = (a.handle or "").strip()
    if not handle:
        rp = out_dir / ".repeats.json"
        if rp.exists():
            try:
                handle = (json.loads(rp.read_text(encoding="utf-8")).get("handle") or "").strip()
            except ValueError:
                handle = ""
    body = payload(pr, device_id(out_dir), handle)
    record = {"sent_to": a.url, "sent": body, "reply": None}
    try:
        status, text = post(a.url, body, a.timeout)
        try:
            reply = json.loads(text) if text.strip() else {}
        except ValueError:
            reply = {"ok": False, "error": "unreadable reply ({0})".format(status)}
    except Exception as e:  # offline, DNS, TLS, timeout: the run goes on
        record["reply"] = {"ok": False, "error": str(e)}
        (out_dir / RANK_FILE).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return finish(["LEADERBOARD", "  not posted: could not reach {0} ({1}).".format(a.url, e.__class__.__name__),
                       "  Your card is unaffected. Run again when you are online, or set leaderboard=false."],
                      {"posted": False, "warning": "could not reach the leaderboard"})
    record["reply"] = reply
    (out_dir / RANK_FILE).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    who = handle or "anonymous"
    if not isinstance(reply, dict) or not reply.get("ok"):
        err = (reply or {}).get("error") if isinstance(reply, dict) else None
        return finish(["LEADERBOARD", "  not posted: {0} ({1}).".format(err or "the leaderboard said no", status),
                       "  Your card is unaffected; the reply is in {0}.".format(out_dir / RANK_FILE)],
                      {"posted": False, "warning": err or "refused ({0})".format(status)})
    rank, of, pct = reply.get("rank"), reply.get("of"), reply.get("percentile")
    url = reply.get("url") or BOARD_URL
    lines = ["LEADERBOARD", "  posted as {0}: {1} · {2} comped over {3} days".format(
        who, _score(body["multiplier"]) if body["multiplier"] is not None else "no multiplier",
        _money(body["comped_usd"]), body["days_back"])]
    link = rewrite_share(out_dir, pr, rank, of, handle)
    if rank:
        # "top 67%" of three people is technically true and reads like a joke; say it from ten up.
        top = " · top {0:g}%".format(pct) if pct and of and of >= 10 else ""
        lines.append("  #{0} of {1} on gotcomped.com{2}".format(rank, of, top))
        if link:
            lines.append("  {0} now carries your rank.".format(out_dir / SHARE_FILE))
    elif reply.get("reason"):
        lines.append("  not ranked: {0} ({1} on the board so far)".format(reply["reason"], of))
    if link:
        lines.append("  the card as a picture you can post: {0}".format(link))
    lines.append("  {0}".format(url))
    lines.append("  sent: score, tier, list-price total, plan, providers, days, your handle. Nothing else."
                 " leaderboard=false to skip.")
    return finish(lines, {"posted": True, "rank": rank, "of": of, "percentile": pct,
                          "eligible": reply.get("eligible"), "held": reply.get("held"), "reason": reply.get("reason"),
                          "handle": handle, "url": url, "card_url": link})


if __name__ == "__main__":
    # The core sits next to this file inside a Play package, and one directory up in the repo.
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (here, os.path.dirname(here)):
        if os.path.isdir(os.path.join(p, "comped_core")):
            sys.path.insert(0, p)
            break
    sys.exit(main())
