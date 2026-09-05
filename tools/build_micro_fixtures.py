#!/usr/bin/env python3
"""Write micro_core/fixtures — the synthetic inputs behind `demo=true`.

Everything here is generated rather than copied, so nothing real can leak into the package: the
keys are shaped like keys and belong to nobody, the transcripts are hand-built, and the git
repository is written byte by byte (index and loose objects) rather than shelled out to git, which
also means the fixture builds on a machine with no git installed.
"""
import binascii
import hashlib
import json
import pathlib
import random
import shutil
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "micro_core" / "fixtures"
NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def write(rel, body):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
    return p


# ---------------------------------------------------------------- a git repository, written by hand

def _loose(objects_dir, kind, body):
    raw = "{0} {1}".format(kind, len(body)).encode("ascii") + b"\x00" + body
    sha = hashlib.sha1(raw).hexdigest()
    p = objects_dir / sha[:2] / sha[2:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(zlib.compress(raw))
    return sha


def _index(entries):
    """A version 2 index: header, then one 62-byte record per path, NUL-padded to a multiple of 8."""
    body = b"DIRC" + struct.pack(">II", 2, len(entries))
    for path, sha, size in sorted(entries):
        raw = path.encode("utf-8")
        fixed = struct.pack(">10I", 0, 0, 0, 0, 0, 0, 0o100644, 0, 0, size)
        entry = fixed + binascii.unhexlify(sha) + struct.pack(">H", min(len(raw), 0x0FFF)) + raw + b"\x00"
        entry += b"\x00" * ((8 - len(entry) % 8) % 8)
        body += entry
    return body + hashlib.sha1(body).digest()


def staged_repo():
    repo = OUT / "staged" / "repo"
    if repo.exists():
        shutil.rmtree(str(repo))
    # Named dot-git, not .git: a nested .git directory inside this repository would be read as a
    # gitlink and the fixture would never be committed. gitindex accepts both spellings and says so.
    objects = repo / "dot-git" / "objects"
    objects.mkdir(parents=True)
    files = {
        "src/app.py": ("def main():\n    print('here')\n    return 0\n"
                       "\n\nif __name__ == '__main__':\n    main()\n"),
        "scripts/report.py": "print('total: 42')\n",
        "config/dev.env": ("DATABASE_URL=postgres://app:localdevpassword@localhost:5432/dev\n"
                           "AWS_ACCESS_KEY_ID=AKIA1234567890ABCD12\n"
                           "FEATURE_FLAG=true\n"),
        "README.md": "# demo repo\n\nA fixture, not a project.\n",
    }
    entries = []
    for path, body in files.items():
        raw = body.encode("utf-8")
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_bytes(raw)
        entries.append((path, _loose(objects, "blob", raw), len(raw)))
    (repo / "dot-git" / "index").write_bytes(_index(entries))
    (repo / "dot-git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return repo


# ---------------------------------------------------------------- whatis

def _b64url(raw):
    return binascii.b2a_base64(raw, newline=False).decode("ascii").replace("+", "-").replace("/", "_").rstrip("=")


def whatis_input():
    """A JWT inside gzip inside base64: three layers, and every byte of it invented here."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64url(json.dumps({"sub": "user_8812", "iss": "rote-demo", "scope": "read:cards",
                                 "iat": int((NOW - timedelta(days=1)).timestamp()),
                                 "exp": int((NOW + timedelta(days=120)).timestamp())},
                                separators=(",", ":")).encode())
    token = "{0}.{1}.{2}".format(header, claims, _b64url(b"this-signature-is-not-real-and-signs-nothing"))
    packed = binascii.b2a_base64(zlib.compress(token.encode("ascii"), 9), newline=False).decode("ascii")
    # zlib, not gzip, would peel as a different kind: write real gzip framing.
    import gzip as _gzip
    packed = binascii.b2a_base64(_gzip.compress(token.encode("ascii")), newline=False).decode("ascii")
    write("whatis/input.txt", packed)


# ---------------------------------------------------------------- fits

LOREM = ("The card is the product. A number nobody can check is a number nobody repeats, so every "
         "figure printed here is one the reader could recompute from their own machine. ")
CODE = """def price(record, table):
    rate = table["models"].get(record.model)
    if rate is None:
        return None, "unpriced: {0}".format(record.model)
    return (record.input_tokens * rate["in"] + record.output_tokens * rate["out"]), None
"""


def fits_sample():
    body = [LOREM * 3, "", "```python", CODE * 6, "```", ""]
    while sum(len(x) for x in body) < 40000:
        body += [LOREM * 4, "", "```python", CODE * 3, "```", ""]
    write("fits/sample.txt", "\n".join(body))


# ---------------------------------------------------------------- is-it-secret

def secret_config():
    write("secret/config.env", "\n".join([
        "# a fixture: every value below is invented and signs nothing",
        "APP_NAME=comped",
        "PORT=5432",
        "API_KEY=your-key-here",
        "AWS_ACCESS_KEY_ID=AKIA9F2K1LQ8ZXVB4TDM",
        "DATABASE_URL=postgres://app:s3cr3t-but-fake@db.internal:5432/prod",
        "SESSION_SECRET=8fJ2kL9mQ4xR7vN1pZ3wY6bC0dE5gH",
        "GITHUB_TOKEN=${GITHUB_TOKEN}",
        "",
    ]))


# ---------------------------------------------------------------- the four logs

TOPICS = ("api", "docs", "review", "tests", "email", "api", "planning")
SPENDS = (("320", "lunch", "food"), ("60", "coffee", "food"), ("1200", "train ticket", "travel"),
          ("450", "groceries", "home"), ("199", "cloud bill", "tools"))
NOTES = ("ring the dentist", "look up the cron OR rule", "ask about the invoice",
         "the parser needs a bound", "buy coffee beans", "reply to Priya")
HABITS = ("water", "gym", "reading")


def logs():
    rng = random.Random(20260905)
    punch, spent, jot, streak = [], [], [], []
    for back in range(13, -1, -1):
        day = NOW - timedelta(days=back)
        for i in range(rng.randint(3, 7)):
            at = day.replace(hour=9 + i, minute=rng.choice((0, 12, 25, 40)), second=0, microsecond=0)
            if at > NOW:
                continue
            topic = TOPICS[(back + i) % len(TOPICS)]
            punch.append({"t": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "v": 1, "topic": topic,
                          "note": "{0} — {1}".format(topic, rng.choice(
                              ("picking it back up", "one more pass", "finishing the edge case",
                               "reading it through", "writing it down"))), "tag": ""})
        for i in range(rng.randint(1, 3)):
            amount, label, tag = SPENDS[(back + i) % len(SPENDS)]
            at = day.replace(hour=11 + 3 * i, minute=15, second=0, microsecond=0)
            if at > NOW:
                continue
            spent.append({"t": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "v": 1, "amount": amount,
                          "currency": "INR", "label": label, "tag": tag})
        for i in range(rng.randint(0, 3)):
            at = day.replace(hour=10 + 4 * i, minute=5, second=0, microsecond=0)
            if at > NOW:
                continue
            jot.append({"t": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "v": 1,
                        "note": NOTES[(back + i) % len(NOTES)], "written": None})
        for name in HABITS:
            if name == "water" or (name == "gym" and back % 2 == 0) or (name == "reading" and back % 3):
                at = day.replace(hour=8, minute=0, second=0, microsecond=0)
                if at <= NOW:
                    streak.append({"t": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "v": 1, "habit": name})
    for name, rows in (("punch", punch), ("spent", spent), ("jot", jot), ("streak", streak)):
        write("log/{0}.jsonl".format(name),
              "".join(json.dumps(r, sort_keys=True) + "\n" for r in sorted(rows, key=lambda r: r["t"])))


# ---------------------------------------------------------------- agent transcripts

def transcripts():
    rng = random.Random(5092026)
    rows = []
    for back in range(2, -1, -1):
        day = NOW - timedelta(days=back)
        for i in range(6):
            at = day.replace(hour=10 + i, minute=rng.choice((3, 17, 34, 51)), second=0, microsecond=0)
            if at > NOW:
                continue
            model = "claude-opus-5" if i % 3 else "claude-sonnet-5"
            rows.append({"type": "assistant", "timestamp": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "message": {"model": model, "usage": {
                             "input_tokens": rng.randint(2000, 9000),
                             "cache_read_input_tokens": rng.randint(20000, 60000),
                             "cache_creation_input_tokens": rng.choice((0, 0, 3000)),
                             "output_tokens": rng.randint(300, 2600)}}})
    write("agent/claude/demo-session.jsonl",
          "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    codex = [{"type": "turn_context", "timestamp": (NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "payload": {"model": "gpt-5", "cwd": "/tmp/demo"}}]
    total = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    for i in range(4):
        total = {"input_tokens": total["input_tokens"] + rng.randint(3000, 8000),
                 "cached_input_tokens": total["cached_input_tokens"] + rng.randint(1000, 4000),
                 "output_tokens": total["output_tokens"] + rng.randint(200, 900)}
        at = NOW - timedelta(hours=5 - i)
        codex.append({"type": "event_msg", "timestamp": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "payload": {"type": "token_count", "info": {"total_token_usage": dict(total)}}})
    write("agent/codex/demo-session.jsonl",
          "".join(json.dumps(r, sort_keys=True) + "\n" for r in codex))


# ---------------------------------------------------------------- since-last

def since_tree():
    tree = OUT / "since" / "tree"
    if tree.exists():
        shutil.rmtree(str(tree))
    files = {
        "README.md": "# demo tree\n\nFour files, so a delta has something to say.\n",
        "src/parse.py": "def parse(line):\n    return line.split(',')\n",
        "src/render.py": "def render(rows):\n    for r in rows:\n        print(r)\n",
        "notes/todo.md": "- [ ] read the index format\n- [x] write the fixture\n",
    }
    for rel, body in files.items():
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    from micro_core import snapshot
    snap, _meta = snapshot.scan_tree(tree, snapshot.DEFAULT_IGNORE, 1000)
    # The seed is the tree as it was BEFORE the last turn: one file had not been written yet and
    # another was shorter, so a demo run shows a real created/modified pair rather than nothing.
    seed = {k: list(v) for k, v in snap.items() if k != "src/render.py"}
    if "src/parse.py" in seed:
        seed["src/parse.py"] = [seed["src/parse.py"][0] - 60_000_000_000, 24, 1]
    write("since/state/seed.json", json.dumps(seed, sort_keys=True))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    staged_repo()
    whatis_input()
    fits_sample()
    secret_config()
    logs()
    transcripts()
    since_tree()
    print("fixtures: {0}".format(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
