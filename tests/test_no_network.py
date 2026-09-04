import unittest, pathlib, re
SRC = pathlib.Path("comped_core")
class StaticSafety(unittest.TestCase):
    def test_no_network_imports(self):
        for p in SRC.rglob("*.py"):
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(urllib|http|socket|requests|ssl)\b", p.read_text(), re.M), p)
    def test_subprocess_only_in_png(self):
        for p in SRC.rglob("*.py"):
            if p.name != "render_png.py": self.assertNotIn("subprocess", p.read_text(), p)
    def test_no_credential_paths(self):
        bad = re.compile(r"\.claude\.json|auth\.json|config\.toml|keychain|credential", re.I)
        for p in SRC.rglob("*.py"):
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if bad.search(line) and "Never reads" not in line and "PRIVACY" not in line:
                    self.fail("{0}:{1} references a credential path: {2}".format(p, n, line.strip()))
