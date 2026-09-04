import unittest, pathlib, re
# Key patterns need a boundary and real key length: `sk-[A-Za-z0-9]{10,}` also matches inside
# ordinary words such as "task-management".
DENY = re.compile(r"(/Users/|rajkaria|hunch|Argus|Flume|Foundry|chipcount|@gmail"
                  r"|(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}|(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,})")
class FixturePrivacy(unittest.TestCase):
    def test_no_real_paths_or_names(self):
        for p in pathlib.Path("resources/fixtures").rglob("*.jsonl"):
            for n, line in enumerate(open(p, errors="replace"), 1):
                m = DENY.search(line)
                self.assertIsNone(m, "{0}:{1} leaks: {2}".format(p, n, m.group(0) if m else ""))
