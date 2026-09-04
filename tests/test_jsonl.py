import tempfile, unittest, pathlib
from comped_core.jsonl import iter_jsonl, JsonlStats

class JsonlTests(unittest.TestCase):
    def _write(self, text):
        d = tempfile.mkdtemp(); p = pathlib.Path(d) / "a.jsonl"; p.write_text(text, encoding="utf-8"); return p

    def test_yields_objects_and_skips_bad_lines(self):
        p = self._write('{"a":1}\nnot json\n\n{"b":2}\n{"trunc')
        stats = JsonlStats()
        rows = list(iter_jsonl(p, stats))
        self.assertEqual([r[1] for r in rows], [{"a": 1}, {"b": 2}])
        self.assertEqual([r[0] for r in rows], [1, 4])
        self.assertEqual(stats.lines, 5); self.assertEqual(stats.parsed, 2); self.assertEqual(stats.unparsed, 2)

    def test_missing_file_yields_nothing_and_notes(self):
        stats = JsonlStats()
        self.assertEqual(list(iter_jsonl(pathlib.Path("/nonexistent/x.jsonl"), stats)), [])
        self.assertIn("nonexistent", stats.note)

    def test_non_object_lines_are_unparsed(self):
        p = self._write('[1,2]\n"str"\n{"ok":true}')
        stats = JsonlStats(); rows = list(iter_jsonl(p, stats))
        self.assertEqual(len(rows), 1); self.assertEqual(stats.unparsed, 2)
