import unittest, pathlib, re, subprocess, sys

SITE = pathlib.Path("site")
PAGES = ("index.html", "leaderboard.html", "docs.html", "developers.html")


class Site(unittest.TestCase):
    def test_docs_are_regenerated_from_the_repo(self):
        before = {p: (SITE / p).read_text(encoding="utf-8") for p in ("docs.html", "developers.html")}
        subprocess.run([sys.executable, "tools/build_site.py"], check=True, capture_output=True)
        for p, text in before.items():
            self.assertEqual(text, (SITE / p).read_text(encoding="utf-8"),
                             "site/{0} is stale; run python3 tools/build_site.py".format(p))

    def test_every_local_link_and_asset_resolves(self):
        for page in PAGES:
            text = (SITE / page).read_text(encoding="utf-8")
            for ref in re.findall(r'(?:href|src)="([^"#][^"]*)"', text):
                if ref.startswith(("http://", "https://", "data:", "mailto:")):
                    continue
                target = ref.split("#", 1)[0]
                if not target or target == "./":
                    continue
                self.assertTrue((SITE / target).is_file(), "{0} -> missing {1}".format(page, target))

    def test_every_in_page_anchor_exists(self):
        for page in PAGES:
            text = (SITE / page).read_text(encoding="utf-8")
            ids = set(re.findall(r'id="([^"]+)"', text))
            for ref in re.findall(r'href="#([^"]+)"', text):
                self.assertIn(ref, ids, "{0} links to #{1}, which does not exist".format(page, ref))

    def test_the_site_makes_no_network_calls_of_its_own(self):
        # The Play sends one thing, to this origin. A landing page that quietly loads a font or an
        # analytics script from a third party would make that promise a lie in the one place people read it.
        for page in PAGES:
            text = (SITE / page).read_text(encoding="utf-8")
            for ref in re.findall(r'(?:src|href)="(https?://[^"]+)"', text):
                # x.com and linkedin.com appear only as share-intent links a person clicks; the page
                # itself loads nothing from them (and the CSP would refuse if it tried).
                self.assertTrue(re.match(r"https://(gotcomped\.com|github\.com|www\.modiqo\.ai|play\.modiqo\.ai|x\.com/intent|www\.linkedin\.com/feed)", ref),
                                "{0} loads or links a third party: {1}".format(page, ref))
            for bad in ("googletagmanager", "google-analytics", "plausible", "fonts.googleapis", "cdn."):
                self.assertNotIn(bad, text, "{0} references {1}".format(page, bad))

    def test_the_deploy_builds_the_docs_page_it_serves(self):
        # Serving a committed docs.html without regenerating it is how a deployed page starts
        # disagreeing with the code it documents. The build command is the guard.
        import json
        conf = json.loads(pathlib.Path("vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(conf["outputDirectory"], "site")
        self.assertIn("tools/build_site.py", conf["buildCommand"])

    def test_the_www_host_redirects_to_the_canonical_one(self):
        import json
        from tools.build_site import SITE_URL
        conf = json.loads(pathlib.Path("vercel.json").read_text(encoding="utf-8"))
        host = SITE_URL.split("://", 1)[1]
        rules = [r for r in conf.get("redirects", [])
                 if any(h.get("value") == "www." + host for h in r.get("has", []))]
        self.assertTrue(rules, "www.{0} should redirect to the canonical host".format(host))
        for rule in rules:
            self.assertTrue(rule["destination"].startswith(SITE_URL), rule["destination"])
            self.assertTrue(rule["permanent"], "the www redirect should be permanent")
        # "/:path*" does not match the bare root, so the home page needs a rule of its own or
        # www.<host>/ quietly serves a second copy of the site.
        self.assertIn("/", [r["source"] for r in rules], "no www redirect covers the root")

    def test_the_published_play_uris_are_the_real_ones(self):
        text = (SITE / "developers.html").read_text(encoding="utf-8")
        for slug in ("comped", "session-ledger", "wrong-turns"):
            self.assertIn("https://play.modiqo.ai/rajkaria/{0}".format(slug), text, slug)
        # The landing page leads with the registry's own one-line installer for the flagship.
        text = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://gotcomped.com/run.sh", text)
        self.assertIn('https://play.modiqo.ai/install?play=rajkaria/comped', text)
        self.assertTrue((SITE / "run.sh").is_file())

    def test_the_one_line_script_runs_the_published_play_and_nothing_else(self):
        sh = (SITE / "run.sh").read_text(encoding="utf-8")
        self.assertIn("https://play.modiqo.ai/rajkaria/comped", sh)
        self.assertIn("https://getrote.dev/install", sh)
        for bad in ("sudo", "rm -rf", "eval", "base64"):
            self.assertNotIn(bad, sh, bad)
        self.assertEqual(sh.count("curl"), 2, "one curl in the comment, one for the rote installer")

    def test_the_landing_page_speaks_to_people_not_parsers(self):
        # Jargon that belongs on the developers page, not the front door.
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for word in ("JSONL", "dedup", "requestId", "harness", "argparse", "stdlib"):
            self.assertNotIn(word, text, "landing page says '{0}'".format(word))
        self.assertIn("Get my <span class=\"hide-xs\">comp </span>score", text)

    def test_every_page_is_canonical_on_the_one_configured_origin(self):
        # tools/build_site.py's SITE_URL is the single source of truth for where this site lives.
        # A canonical or og:url on any other host points crawlers and unfurlers somewhere we do
        # not publish, and two hosts serving the same page compete with each other.
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from tools.build_site import SITE_URL
        self.assertTrue(SITE_URL.startswith("https://") and not SITE_URL.endswith("/"), SITE_URL)
        for page in PAGES:
            text = (SITE / page).read_text(encoding="utf-8")
            canon = re.findall(r'<link rel="canonical" href="([^"]+)"', text)
            self.assertEqual(len(canon), 1, "{0} needs exactly one canonical".format(page))
            self.assertTrue(canon[0].startswith(SITE_URL + "/"),
                            "{0} canonical {1} is not on {2}".format(page, canon[0], SITE_URL))
            for url in re.findall(r'<meta property="og:(?:url|image)" content="([^"]+)"', text):
                self.assertTrue(url.startswith(SITE_URL + "/"),
                                "{0} og url {1} is not on {2}".format(page, url, SITE_URL))

    def test_the_deployed_headers_forbid_the_network_the_site_promises_not_to_use(self):
        # The page tells people their logs never leave and the only call is to this origin. The host
        # config should make that true of the page itself: it may fetch the board from itself and
        # nothing from anyone else.
        import json
        conf = json.loads(pathlib.Path("vercel.json").read_text(encoding="utf-8"))
        csp = [h["value"] for rule in conf["headers"] for h in rule["headers"]
               if h["key"] == "Content-Security-Policy"]
        self.assertEqual(len(csp), 1, "expected exactly one CSP")
        for directive in ("default-src 'none'", "connect-src 'self'", "script-src 'self'",
                          "form-action 'none'", "object-src 'none'"):
            self.assertIn(directive, csp[0], directive)

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
        for claim in ("Sends one thing", "no network calls of any kind", "leaderboard=false", "comped-rank.json",
                      "Never reads", "credential"):
            self.assertIn(claim, text, claim)
        # The old absolute promise is gone everywhere it used to be made; the honest one replaced it.
        for page in PAGES:
            page_text = (SITE / page).read_text(encoding="utf-8")
            for stale in ("Nothing leaves your computer", "nothing leaves your machine", "0 bytes"):
                self.assertNotIn(stale, page_text, "{0} still says '{1}'".format(page, stale))

    def test_the_pages_people_read_have_no_em_dashes(self):
        # House style: sentences, commas and full stops. The dash is how a page ends up sounding
        # like it was generated rather than written.
        for page in PAGES:
            text = (SITE / page).read_text(encoding="utf-8")
            self.assertNotIn("\u2014", text, "{0} has an em dash".format(page))

    def test_the_board_is_fetched_from_this_origin_only_and_the_page_degrades_without_it(self):
        js = (SITE / "board.js").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'fetch\(("[^"]*")', js), ['"/api/leaderboard?sort="'])
        self.assertNotIn("supabase", js.lower())
        for page in ("index.html", "leaderboard.html"):
            text = (SITE / page).read_text(encoding="utf-8")
            self.assertIn('<script src="board.js" defer></script>', text, page)
            self.assertIn("board-empty", text, page)   # a static placeholder is there before any fetch
        self.assertIn('id="board-top"', (SITE / "index.html").read_text(encoding="utf-8"))
        self.assertIn('id="board-full"', (SITE / "leaderboard.html").read_text(encoding="utf-8"))

    def test_the_one_line_script_posts_under_the_rote_handle_and_can_be_told_not_to(self):
        sh = (SITE / "run.sh").read_text(encoding="utf-8")
        self.assertIn("rote whoami", sh)
        self.assertIn("handle=$H", sh)
        self.assertIn("leaderboard=false", sh)
        self.assertIn("leaderboard.html", sh)
