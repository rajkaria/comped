#!/usr/bin/env python3
"""Turn one recorded run into that Play's presentation fixtures.

rote's presentation lint replays the body against declared fixtures, so every data-bearing step
needs one representative completed observation. This copies them out of a real run's
`.rote/presentation/<run-id>/input.json` -- the only source of truth for the shape -- and writes
the manifest tree the lint expects under `plays/<slug>/resources/presentation-fixtures/`.

Usage: python3 tools/build_fixtures.py <slug> <path to input.json>
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
