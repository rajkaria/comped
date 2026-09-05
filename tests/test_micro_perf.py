"""Micro means micro. A step that takes half a second is a different product."""
import io
import json
import time
import unittest
from contextlib import redirect_stdout

from micro_core import cli

BUDGET_MS = 400
STEPS = (["whatis", "report"], ["fits", "report"], ["secret", "report"], ["cron", "report"],
         ["punch", "report"], ["spent", "report"], ["jot", "report"], ["streak", "report"],
         ["last-turn", "report"], ["budget", "report"], ["since-last", "report"],
         ["staged", "report"])


def _run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(args)
    return json.loads(buf.getvalue().rstrip("\n").split("\n")[-1])


class TestSpeed(unittest.TestCase):
    def test_every_step_is_under_the_budget_on_fixtures(self):
        slow = []
        for args in STEPS:
            _run(args + ["--demo", "true", "--now", "2026-09-05T12:00:00Z"])   # warm the imports
            start = time.perf_counter()
            _run(args + ["--demo", "true", "--now", "2026-09-05T12:00:00Z"])
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed > BUDGET_MS:
                slow.append("{0} took {1:.0f}ms".format(" ".join(args), elapsed))
        self.assertEqual(slow, [])
