#!/usr/bin/env node
// comped: what your AI subscription would have cost at full price.
//
// This is a launcher, nothing more. comped is standard-library Python; npm is only how you got
// it. The whole tool sits in payload/ next to this file and runs from there. Nothing is
// downloaded, nothing is compiled, nothing phones home except the one leaderboard post, which
// leaderboard=false turns off.
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");

const ENTRY = path.join(__dirname, "..", "payload", "comped.py");

// python3 first. Windows ships the `py` launcher and often no `python3` at all.
const CANDIDATES = [
  ["python3", []],
  ["python", []],
  ["py", ["-3"]],
];

function usable(cmd, prefix) {
  const probe = spawnSync(cmd, prefix.concat([
    "-c", "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)",
  ]), { stdio: "ignore" });
  return probe.status === 0;
}

function main() {
  for (const [cmd, prefix] of CANDIDATES) {
    if (!usable(cmd, prefix)) continue;
    const r = spawnSync(cmd, prefix.concat([ENTRY], process.argv.slice(2)), {
      stdio: "inherit",
      // The card is drawn with box characters. A Windows console inherits a legacy code page
      // and would kill the run on the first line; Python honours this over the code page.
      env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8" }),
    });
    if (r.error) {
      process.stderr.write("comped could not start " + cmd + ": " + r.error.message + "\n");
      process.exit(1);
    }
    process.exit(r.status === null ? 1 : r.status);
  }
  process.stderr.write(
    "comped needs Python 3.9 or newer on your PATH, and could not find it.\n" +
    "  macOS:   it is already there; try opening a new terminal.\n" +
    "  Ubuntu:  sudo apt install python3\n" +
    "  Windows: install from https://python.org, ticking \"Add python.exe to PATH\".\n" +
    "Nothing was run.\n");
  process.exit(1);
}

main();
