"""One entry point for twelve Plays.

A Play that remembers is two steps, `record` then `report`, and the state file is what they share.
A Play that is a pure function is one `report` step: giving it a second step would mean inventing a
scratch file for the halves to talk through, and a Play that claims to write nothing should not
write a file to prove it.
"""
import argparse
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:      # invoked as a file path from a Play step
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "micro_core"

from . import common

PLAYS = ("whatis", "fits", "secret", "cron", "punch", "spent", "jot", "streak",
         "last-turn", "budget", "since-last", "staged")

DEFAULT_STATE_DIR = "~/.rote-micro"


def _parser(prog, *specs):
    """Every step parses `now` and `demo`; the rest is whatever that step actually varies on."""
    p = argparse.ArgumentParser(prog=prog, add_help=False)
    for name, default in specs:
        p.add_argument("--" + name.replace("_", "-"), dest=name, default=default)
    p.add_argument("--now", dest="now", default="")
    p.add_argument("--demo", dest="demo", default="false")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in PLAYS:
        sys.stderr.write("usage: cli.py <{0}> <step> [options]\n".format("|".join(PLAYS)))
        return 2
    play, step, rest = argv[0], argv[1], argv[2:]
    handler = _DISPATCH.get((play, step))
    if handler is None:
        sys.stderr.write("unknown step: {0} {1}\n".format(play, step))
        return 2
    return handler(rest)


_DISPATCH = {}


if __name__ == "__main__":
    sys.exit(main())
