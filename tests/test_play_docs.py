import unittest, json, pathlib, re

SPEC = pathlib.Path("docs/SPEC.md").read_text(encoding="utf-8")
PRIVACY = SPEC.split("## 9. Privacy and trust statements (verbatim in every description and report)\n")[1].split("\n## 10.")[0].strip()
SLUGS = ("session-ledger", "comped", "wrong-turns")
# Registry copy is public and permanent; the hackathon is not part of what these Plays do.
# "judged" appears in session-ledger's copy as an ordinary verb ("nothing is judged"), so it is
# not part of the pattern.
HACKATHON = re.compile(r"hackathon|playoffs|prize|submission|contest|competition", re.I)


class PlayDocs(unittest.TestCase):
    def test_every_play_has_its_registry_copy(self):
        for slug in SLUGS:
            for name in ("DESCRIPTION.md", "PARAMETERS.json", "STEPS.md"):
                self.assertTrue(pathlib.Path("plays", slug, name).is_file(), "{0}/{1}".format(slug, name))

    def test_description_carries_the_privacy_paragraph_verbatim(self):
        for slug in SLUGS:
            text = pathlib.Path("plays", slug, "DESCRIPTION.md").read_text(encoding="utf-8")
            self.assertIn(PRIVACY, text, slug)

    def test_description_never_mentions_the_hackathon(self):
        for slug in SLUGS:
            text = pathlib.Path("plays", slug, "DESCRIPTION.md").read_text(encoding="utf-8")
            m = HACKATHON.search(text)
            self.assertIsNone(m, "{0} mentions {1}".format(slug, m.group(0) if m else ""))

    def test_parameters_are_well_formed_and_defaults_are_real(self):
        for slug in SLUGS:
            params = json.loads(pathlib.Path("plays", slug, "PARAMETERS.json").read_text(encoding="utf-8"))
            self.assertTrue(params)
            for p in params:
                for k in ("name", "type", "default", "label", "description"):
                    self.assertIn(k, p, "{0}.{1}".format(slug, p.get("name")))
                self.assertIn(p["type"], ("string", "integer"))
                if "choices" in p and p["default"] not in ("", None):
                    self.assertIn(p["default"], p["choices"], "{0}.{1}".format(slug, p["name"]))

    def test_plan_ids_offered_exist_in_the_bundled_table(self):
        plans = json.loads(pathlib.Path("resources/plans.json").read_text(encoding="utf-8"))["plans"]
        params = json.loads(pathlib.Path("plays/comped/PARAMETERS.json").read_text(encoding="utf-8"))
        choices = next(p for p in params if p["name"] == "plan")["choices"]
        for c in choices:
            self.assertIn(c, plans, c)

    def test_steps_reference_only_real_cli_subcommands_and_parameters(self):
        from comped_core.cli import build_parser
        subs = set(build_parser()._subparsers._group_actions[0].choices)
        for slug in SLUGS:
            names = {p["name"] for p in json.loads(pathlib.Path("plays", slug, "PARAMETERS.json").read_text(encoding="utf-8"))}
            steps = pathlib.Path("plays", slug, "STEPS.md").read_text(encoding="utf-8")
            for cmd in re.findall(r"cli\.py (\w+)", steps):
                self.assertIn(cmd, subs, "{0}: unknown subcommand {1}".format(slug, cmd))
            for ref in re.findall(r"<(\w+)>", steps):
                if ref != "harness":
                    self.assertIn(ref, names, "{0}: step uses undeclared parameter {1}".format(slug, ref))
