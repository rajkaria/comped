#!/usr/bin/env python3
"""Turn one recorded run into that Play's presentation fixtures.

rote's presentation lint replays the body against declared fixtures, so every data-bearing step
needs one representative completed observation. This copies them out of a real run's
`.rote/presentation/<run-id>/input.json` -- the only source of truth for the shape -- and writes
the manifest tree the lint expects under `plays/<slug>/resources/presentation-fixtures/`.

Two ways in, and both end in the same capture:

    python3 tools/build_fixtures.py                     capture every daily Play that has none yet
    python3 tools/build_fixtures.py <slug>              recapture that one Play
    python3 tools/build_fixtures.py <slug> <input.json> import an input.json captured elsewhere

The first two forms run the Play here with `rote play run ... demo=true`, into an out_dir with no
personal path in it, and then read the input.json that run left behind -- so a fixture is still
evidence from a real run rather than something written by hand. The first form skips a Play whose
fixtures are already complete, which is what makes running this twice leave the tree alone: a
capture records its own duration, so recapturing for no reason would rewrite bytes that mean the
same thing.
"""
import json, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "plays" / "_daily-spec.json"
# tests/test_fixture_privacy.py refuses a fixture carrying a real path, and the out_dir is printed
# by every report. So a capture runs into this, which belongs to nobody.
DEMO_OUT = "/tmp/daily-demo"
# A fixture is evidence, not a payload dump: each stream resource is capped at 1 MiB by rote, and
# a smaller one reads better in review.
MAX_STREAM = 200_000


def main(slug: str, input_json: str) -> int:
    doc = json.loads(pathlib.Path(input_json).read_text(encoding="utf-8"))
    base = ROOT / "plays" / slug / "resources" / "presentation-fixtures"
    mapping = {}
    for name, step in sorted(doc.get("steps", {}).items()):
        outcome = step.get("outcome", {})
        if outcome.get("status") not in ("completed", "restored"):
            print("skip {0}: status {1}".format(name, outcome.get("status")))
            continue
        body = outcome.get("output", {}).get("body", {})
        if body.get("kind") != "process.exec":
            print("skip {0}: kind {1}".format(name, body.get("kind")))
            continue
        status = body.get("status", {})
        exit_ = status.get("exit", {})
        if exit_.get("kind") != "code" or exit_.get("code") != 0:
            print("skip {0}: non-zero exit".format(name))
            continue
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        stdout = (body.get("stdout") or {}).get("text") or ""
        stderr = (body.get("stderr") or {}).get("text") or ""
        if len(stdout.encode("utf-8")) > MAX_STREAM:
            raise SystemExit("{0}: stdout is {1} bytes, too large for a fixture".format(name, len(stdout)))
        (d / "stdout.txt").write_text(stdout, encoding="utf-8")
        (d / "stderr.txt").write_text(stderr, encoding="utf-8")
        manifest = ["schema_version: 1", "kind: process.exec", "status:",
                    "  exit:", "    kind: code", "    code: 0",
                    "  duration_ms: {0}".format(int(status.get("duration_ms") or 0)),
                    "  timeout_ms: {0}".format(int(status.get("timeout_ms") or 30000)),
                    "stdout: resources/presentation-fixtures/{0}/stdout.txt".format(name),
                    "stderr: resources/presentation-fixtures/{0}/stderr.txt".format(name)]
        (d / "fixture.yaml").write_text("\n".join(manifest) + "\n", encoding="utf-8")
        mapping[name] = "resources/presentation-fixtures/{0}/fixture.yaml".format(name)
        print("{0}: {1} bytes stdout".format(name, len(stdout)))
    out = ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json"
    out.write_text(json.dumps(mapping, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("declared {0} fixtures -> {1}".format(len(mapping), out))
    return 0


def steps_of(slug: str) -> list:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    return [step[0] for step in spec[slug]["steps"]]


def complete(slug: str) -> bool:
    """True when every step of this Play already has a fixture manifest and both streams."""
    declared = ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json"
    if not declared.is_file():
        return False
    try:
        mapping = json.loads(declared.read_text(encoding="utf-8"))
    except ValueError:
        return False
    if sorted(mapping) != sorted(steps_of(slug)):
        return False
    for rel in mapping.values():
        manifest = ROOT / "plays" / slug / rel
        if not (manifest.is_file() and (manifest.parent / "stdout.txt").is_file()
                and (manifest.parent / "stderr.txt").is_file()):
            return False
    return True


def newest_input(slug: str):
    """The input.json of the most recent local run of this Play, or None."""
    workspaces = pathlib.Path(os.path.expanduser("~/.rote/workspaces"))
    runs = []
    for d in workspaces.glob("dag-{0}-*/.rote/presentation/*/input.json".format(slug)):
        runs.append((d.stat().st_mtime, d))
    return max(runs)[1] if runs else None


def capture(slug: str) -> int:
    """Run the Play here in demo mode, then build its fixtures from what the run recorded."""
    package = ROOT / "plays" / slug / "main.ts"
    if not package.is_file():
        raise SystemExit("{0}: no package at {1}".format(slug, package))
    out_dir = os.path.join(DEMO_OUT, slug)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    argv = ["rote", "play", "run", str(package), "out_dir=" + out_dir, "demo=true"]
    proc = subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise SystemExit("{0}: {1} failed\n{2}".format(
            slug, " ".join(argv), proc.stdout.decode("utf-8", "replace")[-4000:]))
    recorded = newest_input(slug)
    if recorded is None:
        raise SystemExit("{0}: the run recorded no presentation input".format(slug))
    return main(slug, str(recorded))


def main_all(only=None) -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    for slug in (only or list(spec)):
        if only is None and complete(slug):
            print("{0}: fixtures already complete, left alone".format(slug))
            continue
        capture(slug)
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main_all())
    if len(sys.argv) == 2:
        sys.exit(main_all([sys.argv[1]]))
    sys.exit(main(sys.argv[1], sys.argv[2]))
