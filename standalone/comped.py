#!/usr/bin/env python3
"""comped, standalone: your card and your rank, with no runner and no account.

Same code as the rote Play, the same fourteen parameters, the same output. The Play splits the
work into eight steps because rote shows one reading per step and runs the readers in parallel;
this runs the same functions in one process, for a person who just wants the number.

    python3 comped.py                        your logs, the last 30 days
    python3 comped.py plan=claude-pro-20     tell it the tier you actually pay for
    python3 comped.py handle=yourname        your name on the board instead of anonymous
    python3 comped.py leaderboard=false      the card only; nothing is sent anywhere

Parameters are key=value, exactly as the Play takes them, so a line that works here works there.
"""
import sys

if sys.version_info < (3, 9):  # this file stays parseable by older interpreters so this can fire
    sys.stderr.write("comped needs Python 3.9 or newer. This is %s.\n" % sys.version.split()[0])
    sys.exit(1)

import io
import json
import os
import time
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Every parameter the Play declares, with the Play's default. tests/test_standalone.py fails if
# this list and docs/plays/comped/PARAMETERS.json ever disagree, because two ways to run the same
# tool that take different arguments is just two tools.
PARAMS = {
    "days_back": "30",
    "out_dir": "~/comped",
    "claude_dir": "~/.claude/projects",
    "codex_dir": "~/.codex/sessions",
    "pi_dir": "~/.pi/agent/sessions",
    "opencode_dir": "~/.local/share/opencode/storage",
    "include_subagents": "true",
    "redact": "true",
    "plan": "auto",
    "repeat_threshold": "3",
    "rates_path": "",
    "handle": "",
    "card_theme": "dark",
    "leaderboard": "true",
}
# leaderboard is the poster's business; everything else describes the offline run.
CORE_PARAMS = [k for k in PARAMS if k != "leaderboard"]


def _bool(s):
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def parse_args(argv):
    """key=value pairs, the way the Play takes them. Anything else is a mistake worth naming."""
    vals = dict(PARAMS)
    for arg in argv:
        if arg in ("-h", "--help", "help"):
            return None
        if "=" not in arg:
            raise ValueError(
                "arguments are key=value, like plan=claude-pro-20. Got: {0}\n"
                "Valid keys: {1}".format(arg, ", ".join(sorted(PARAMS))))
        key, value = arg.split("=", 1)
        key = key.strip()
        if key not in PARAMS:
            raise ValueError("unknown parameter: {0}\nValid keys: {1}".format(key, ", ".join(sorted(PARAMS))))
        vals[key] = value
    return vals


def freshen(path):
    """Stamp the packaged sample logs with today's date.

    Every file in the download carries one fixed timestamp so that two builds of a commit produce
    one checksum, which is what makes the published sha256 worth checking. The readers skip files
    last modified before the window they are asked about, so untouched sample logs would read as
    an empty machine. This runs on the packaged fixtures only, never on anybody's real logs.
    """
    stamp = time.time()
    for p in path.rglob("*"):
        if p.is_file():
            try:
                os.utime(p, (stamp, stamp))
            except OSError:
                pass


def resolve(value):
    """A relative path that is not here, but is inside the package, means the packaged one.

    rote runs a Play with the package root as the working directory, which is why the documented
    demo says claude_dir=resources/fixtures/claude. The same line has to work here, where the
    working directory is wherever the person happened to be standing.
    """
    if not value or value.startswith(("~", "/")):
        return value
    p = Path(value)
    if p.exists():
        return value
    packaged = HERE / value
    if not packaged.exists():
        return value
    freshen(packaged)
    return str(packaged)


def core_argv(vals):
    """The parameter names are the flag names with underscores swapped for dashes."""
    argv = ["run"]
    for k in CORE_PARAMS:
        if k == "rates_path" and not vals[k]:
            continue
        value = resolve(vals[k]) if k.endswith("_dir") and k != "out_dir" else vals[k]
        argv += ["--{0}".format(k.replace("_", "-")), str(value)]
    return argv


def post(vals):
    """Run the poster and show it to a human: its last line is JSON for the Play, not for you."""
    import post_score
    buf = io.StringIO()
    with redirect_stdout(buf):
        post_score.main(["--out-dir", vals["out_dir"], "--leaderboard", vals["leaderboard"],
                         "--handle", vals["handle"]])
    lines = buf.getvalue().rstrip("\n").split("\n")
    if lines and lines[-1].startswith("{"):
        try:
            json.loads(lines[-1])
            lines = lines[:-1]
        except ValueError:
            pass
    if any(line.strip() for line in lines):
        print("\n".join(lines))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        vals = parse_args(argv)
    except ValueError as e:
        sys.stderr.write("{0}\n".format(e))
        return 2
    if vals is None:
        print(__doc__.strip())
        print("\nParameters, with their defaults:")
        for k in sorted(PARAMS):
            print("  {0:<18} {1}".format(k, PARAMS[k] or "(empty)"))
        return 0

    from comped_core import cli as core
    try:
        a = core.build_parser().parse_args(core_argv(vals))
    except SystemExit:
        return 2
    # Ask for the summary so we can tell "read nothing" from "read something", then keep it to
    # ourselves: the card is the output, and a JSON blob under it helps nobody.
    a.json_out = True
    try:
        result = core.cmd_run(a) or {}
    except Exception as e:                       # a person gets one line, never a traceback
        sys.stderr.write("comped could not finish: {0}: {1}\n".format(type(e).__name__, e))
        return 1
    # Nothing was read, so there is no card from this run. Posting here would send the previous
    # run's score as if it were today's. The run already said where it looked.
    if not result.get("records"):
        return 0
    # The poster runs either way, exactly as it does in the Play: when leaderboard=false it is
    # the thing that says so out loud, and "nothing was sent" is worth reading.
    print("")
    post(vals)
    if _bool(vals["leaderboard"]) and not vals["handle"].strip():
        print("")
        print("  You are on the board anonymously. To use a name, run it again with:")
        print("    handle=yourname")
    return 0


if __name__ == "__main__":
    sys.exit(main())
