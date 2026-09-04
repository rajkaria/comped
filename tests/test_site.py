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
                self.assertTrue(re.match(r"https://(gotcomped\.com|github\.com|www\.modiqo\.ai|play\.modiqo\.ai)", ref),
                                "{0} loads or links a third party: {1}".format(page, ref))
            for bad in ("googletagmanager", "google-analytics", "plausible", "fonts.googleapis", "cdn."):
                self.assertNotIn(bad, text, "{0} references {1}".format(page, bad))

    def test_the_published_play_uris_are_the_real_ones(self):
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for slug in ("comped", "session-ledger", "wrong-turns"):
            self.assertIn("https://play.modiqo.ai/rajkaria/{0}".format(slug), text, slug)

    def test_the_canonical_host_is_the_one_the_dns_points_at(self):
        # site/CNAME is what GitHub Pages serves the site as. A canonical or og:url on any other
        # host tells crawlers and unfurlers to go somewhere this repo does not publish.
        host = (SITE / "CNAME").read_text(encoding="utf-8").strip()
        self.assertTrue(host and "/" not in host, "CNAME should hold a bare hostname")
        for page in ("index.html", "docs.html"):
            text = (SITE / page).read_text(encoding="utf-8")
            canon = re.findall(r'<link rel="canonical" href="([^"]+)"', text)
            self.assertEqual(len(canon), 1, "{0} needs exactly one canonical".format(page))
            self.assertTrue(canon[0].startswith("https://{0}/".format(host)),
                            "{0} canonical {1} is not on {2}".format(page, canon[0], host))
            for url in re.findall(r'<meta property="og:(?:url|image)" content="([^"]+)"', text):
                self.assertTrue(url.startswith("https://{0}/".format(host)),
                                "{0} og url {1} is not on {2}".format(page, url, host))

    def test_social_card_images_exist_and_declare_their_real_size(self):
        # An og:image whose declared size is a lie gets letterboxed or cropped by every unfurler.
        import struct
        text = (SITE / "index.html").read_text(encoding="utf-8")
        pairs = re.findall(
            r'<meta property="og:image" content="[^"]*/([^"/]+)">\s*'
            r'<meta property="og:image:width" content="(\d+)">\s*'
            r'<meta property="og:image:height" content="(\d+)">', text)
        self.assertTrue(pairs, "index.html declares no sized og:image")
        for name, w, h in pairs:
            data = (SITE / name).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", name)
            self.assertEqual(struct.unpack(">II", data[16:24]), (int(w), int(h)), name)

    def test_privacy_claims_match_the_spec_wording(self):
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for claim in ("Never sends", "No network calls of any kind", "Never reads", "credential"):
            self.assertIn(claim, text, claim)
