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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    staged_repo()
    print("fixtures: {0}".format(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
