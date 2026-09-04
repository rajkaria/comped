import unittest, pathlib, re, subprocess, sys

SITE = pathlib.Path("site")


class Site(unittest.TestCase):
    def test_docs_are_regenerated_from_the_repo(self):
        before = (SITE / "docs.html").read_text(encoding="utf-8")
        subprocess.run([sys.executable, "tools/build_site.py"], check=True, capture_output=True)
        self.assertEqual(before, (SITE / "docs.html").read_text(encoding="utf-8"),
                         "site/docs.html is stale; run python3 tools/build_site.py")

    def test_every_local_link_and_asset_resolves(self):
        for page in ("index.html", "docs.html"):
            text = (SITE / page).read_text(encoding="utf-8")
            for ref in re.findall(r'(?:href|src)="([^"#][^"]*)"', text):
                if ref.startswith(("http://", "https://", "data:", "mailto:")):
                    continue
                target = ref.split("#", 1)[0]
                if not target or target == "./":
                    continue
                self.assertTrue((SITE / target).is_file(), "{0} -> missing {1}".format(page, target))

    def test_every_in_page_anchor_exists(self):
        for page in ("index.html", "docs.html"):
            text = (SITE / page).read_text(encoding="utf-8")
            ids = set(re.findall(r'id="([^"]+)"', text))
            for ref in re.findall(r'href="#([^"]+)"', text):
                self.assertIn(ref, ids, "{0} links to #{1}, which does not exist".format(page, ref))

    def test_the_site_makes_no_network_calls_of_its_own(self):
        # The Play promises no network. A landing page that quietly loads a font or an analytics
        # script from a third party would make that promise a lie in the one place people read it.
        for page in ("index.html", "docs.html"):
            text = (SITE / page).read_text(encoding="utf-8")
            for ref in re.findall(r'(?:src|href)="(https?://[^"]+)"', text):
                self.assertTrue(re.match(r"https://(github\.com|www\.modiqo\.ai|play\.modiqo\.ai)", ref),
                                "{0} loads or links a third party: {1}".format(page, ref))
            for bad in ("googletagmanager", "google-analytics", "plausible", "fonts.googleapis", "cdn."):
                self.assertNotIn(bad, text, "{0} references {1}".format(page, bad))

    def test_the_published_play_uris_are_the_real_ones(self):
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for slug in ("comped", "session-ledger", "wrong-turns"):
            self.assertIn("https://play.modiqo.ai/rajkaria/{0}".format(slug), text, slug)

    def test_privacy_claims_match_the_spec_wording(self):
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for claim in ("Never sends", "No network calls of any kind", "Never reads", "credential"):
            self.assertIn(claim, text, claim)
