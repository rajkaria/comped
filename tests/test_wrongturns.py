import unittest
from decimal import Decimal
from comped_core.models import HumanMessage, ToolEvent, Ledger
from comped_core.wrongturns import classify, draft_rules, signature
def T(eid, sid, ts, name, summ, err, text, turn): return ToolEvent("claude-code", sid, eid, ts, name, summ, err, text, turn)
def H(mid, sid, ts, text): return HumanMessage("claude-code", sid, mid, ts, text, "h", "/p", "human")
class WrongTurnTests(unittest.TestCase):
    def test_signature_strips_paths_numbers(self):
        self.assertEqual(signature("ENOENT: no such file or directory, open '/Users/x/y.py' line 42"), "enoent: no such file or directory, open '<path>' line <num>")
    def test_tool_error_class_recurs_across_sessions(self):
        tools = [T("e1", "s1", "2026-09-01T10:00:01Z", "Bash", "cat x.py", True, "cat: /a/x.py: No such file or directory", "h1"),
                 T("e2", "s2", "2026-09-02T10:00:01Z", "Bash", "cat y.py", True, "cat: /b/y.py: No such file or directory", "h2"),
                 T("e3", "s3", "2026-09-03T10:00:01Z", "Bash", "cat z.py", True, "cat: /c/z.py: No such file or directory", "h3"),
                 T("e4", "s3", "2026-09-03T10:00:02Z", "Bash", "ls", False, "", "h3")]
        humans = [H("h1", "s1", "2026-09-01T10:00:00Z", "x"), H("h1b", "s1", "2026-09-01T10:01:00Z", "y"), H("h2", "s2", "2026-09-02T10:00:00Z", "x"), H("h3", "s3", "2026-09-03T10:00:00Z", "x")]
        led = Ledger([], humans, tools, [], "x")
        cost = {"h1": Decimal("1"), "h1b": Decimal("2"), "h2": Decimal("3"), "h3": Decimal("4")}
        cl = classify(led, cost, 3, True)
        self.assertEqual(len(cl), 1); c = cl[0]
        self.assertEqual((c.kind, c.confidence, c.tool_name, c.count, c.sessions), ("tool_error", "high", "Bash", 3, 3))
        self.assertEqual(c.recovery_usd, Decimal("10"))   # h1+h1b, h2, h3
        self.assertIn("no such file", c.signature); self.assertIn("cat x.py", c.evidence); self.assertIn("exists", c.rule_draft.lower())
    def test_correction_pairs_with_preceding_tool(self):
        tools = [T("e{0}".format(i), "s{0}".format(i), "2026-09-0{0}T10:00:01Z".format(i), "Edit", "file.py", False, "", "h{0}".format(i)) for i in (1, 2, 3)]
        humans = [H("h{0}".format(i), "s{0}".format(i), "2026-09-0{0}T10:00:00Z".format(i), "change it") for i in (1, 2, 3)] + \
                 [H("c{0}".format(i), "s{0}".format(i), "2026-09-0{0}T10:00:05Z".format(i), "no, revert that and do it the other way") for i in (1, 2, 3)]
        cl = classify(Ledger([], humans, tools, [], "x"), {}, 3, True)
        self.assertEqual(len(cl), 1); self.assertEqual((cl[0].kind, cl[0].confidence, cl[0].tool_name, cl[0].count), ("correction", "medium", "Edit", 3))
    def test_revert_detected(self):
        tools = [T("e{0}".format(i), "s{0}".format(i), "2026-09-0{0}T10:00:01Z".format(i), "Bash", "git reset --hard HEAD~1", False, "", "h{0}".format(i)) for i in (1, 2, 3)]
        cl = classify(Ledger([], [], tools, [], "x"), {}, 3, True)
        self.assertEqual(cl[0].kind, "revert"); self.assertEqual(cl[0].confidence, "high")
    def test_snippets_hidden(self):
        tools = [T("e{0}".format(i), "s{0}".format(i), "2026-09-0{0}T10:00:01Z".format(i), "Bash", "secret cmd", True, "boom", "h{0}".format(i)) for i in (1, 2, 3)]
        cl = classify(Ledger([], [], tools, [], "x"), {}, 3, False); self.assertEqual(cl[0].evidence, "(snippets hidden)")
    def test_draft_rules_targets(self):
        tools = [T("e{0}".format(i), "s{0}".format(i), "2026-09-0{0}T10:00:01Z".format(i), "Bash", "npm test", True, "3 tests failed", "h{0}".format(i)) for i in (1, 2, 3)]
        cl = classify(Ledger([], [], tools, [], "x"), {}, 3, True)
        md = draft_rules(cl, "both"); self.assertIn("CLAUDE.md", md); self.assertIn("AGENTS.md", md); self.assertIn("confidence: high", md)
        self.assertNotIn("AGENTS.md", draft_rules(cl, "claude"))
