#!/usr/bin/env python3
"""Build site/comped.tar.gz: everything needed to run comped without rote, and nothing else.

The archive is the payload behind `curl -fsSL https://gotcomped.com/comped.sh | sh`. It carries
the same offline core the Play carries, the same two resource files, the same poster, plus the
standalone entry point that chains them. Layout matches the repo so comped_core/prices.py finds
resources/prices.json exactly where it always looks.

It is built byte-for-byte reproducibly: fixed mtimes, fixed ownership, sorted entries and a gzip
header with no timestamp. Two builds of one commit produce one sha256, which is what makes the
published checksum worth printing.
"""
import gzip
import hashlib
import io
import pathlib
import re
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "comped.tar.gz"
PREFIX = "comped"
EPOCH = 1577836800  # 2020-01-01T00:00:00Z, an arbitrary constant so the archive is reproducible


def version() -> str:
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("pyproject.toml has no version")
    return m.group(1)


def members() -> list:
    """(archive path, bytes) for every file in the distribution, in a fixed order."""
    out = []
    for p in sorted((ROOT / "comped_core").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        out.append((str(p.relative_to(ROOT)), p.read_bytes()))
    for name in ("prices.json", "plans.json"):
        p = ROOT / "resources" / name
        out.append(("resources/" + name, p.read_bytes()))
    # The sample logs travel with it. Asking someone to point a brand new tool at their own
    # session history before they have seen it do anything is the wrong way round, and this is
    # the only thing in the archive that is not needed to run.
    for p in sorted((ROOT / "resources" / "fixtures").rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            out.append((str(p.relative_to(ROOT)), p.read_bytes()))
    out.append(("comped.py", (ROOT / "standalone" / "comped.py").read_bytes()))
    out.append(("post_score.py", (ROOT / "leaderboard" / "post_score.py").read_bytes()))
    out.append(("LICENSE", (ROOT / "LICENSE").read_bytes()))
    out.append(("VERSION", (version() + "\n").encode("utf-8")))
    return sorted(out)


def build() -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data in members():
            info = tarfile.TarInfo("{0}/{1}".format(PREFIX, name))
            info.size = len(data)
            info.mtime = EPOCH
            info.mode = 0o755 if name == "comped.py" else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    packed = io.BytesIO()
    # mtime=0 keeps the gzip header constant; without it every build differs.
    with gzip.GzipFile(fileobj=packed, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw.getvalue())
    return packed.getvalue()


def main() -> int:
    blob = build()
    digest = hashlib.sha256(blob).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(blob)
    (OUT.parent / (OUT.name + ".sha256")).write_text(
        "{0}  {1}\n".format(digest, OUT.name), encoding="utf-8")
    print("wrote {0} ({1:,} bytes, {2} files)".format(OUT, len(blob), len(members())))
    print("sha256 {0}".format(digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
