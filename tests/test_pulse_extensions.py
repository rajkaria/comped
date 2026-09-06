"""extension-reach: what the Play promises about browser extensions, asserted against a real tree.

Every test here builds an actual profile directory — manifests, a settings document, version
folders with real modification times — and reads it the way the Play does on a user's machine.
The promises being checked are the ones on the card: that reach is tiered by what an extension can
actually touch rather than by name, that blanket access plus a second power is named for what it
does, that one extension installed in three browsers is one row, that a folder timestamp used as a
last-update date is labelled a proxy wherever it appears, that a browser that cannot be read costs
that browser alone, and that no path belonging to extension storage is ever opened.
"""
import builtins
import json
import os
import plistlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from daily_core.common import EPOCH_1601, Budget
from daily_core.parsers import chromeprefs
from daily_core.scan import extensions

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

SHOPPER = "aaaabbbbccccddddeeeeffffgggghhhh"     # <all_urls> + cookies/webRequest/scripting, MV3
MAILER = "iiiijjjjkkkkllllmmmmnnnnoooopppp"      # one named host, and cookies, which is not a combo
LEGACY = "abcdefghijklmnopabcdefghijklmnop"      # Manifest V2, hosts declared in `permissions`
DEVTOOL = "ponmlkjihgfedcbaponmlkjihgfedcba"     # unpacked by a developer, activeTab only
PLANTED = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab"     # sideloaded by another program, no page access


def ts(days_ago: float) -> float:
    return (NOW - timedelta(days=days_ago)).timestamp()


def chrome_time(days_ago: float) -> str:
    return str(int((NOW - timedelta(days=days_ago) - EPOCH_1601).total_seconds() * 1000000))


def write(path: Path, text: str, days_ago=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if days_ago is not None:
        os.utime(str(path.parent), (ts(days_ago), ts(days_ago)))
    return path


MANIFESTS = {
    SHOPPER: ({"manifest_version": 3, "name": "Shopping Helper", "version": "4.2.0",
               "permissions": ["cookies", "webRequest", "scripting", "storage"],
               "host_permissions": ["<all_urls>"]}, 10),
    MAILER: ({"manifest_version": 3, "name": "Inbox Tidier", "version": "1.1.0",
              "permissions": ["cookies", "storage"],
              "host_permissions": ["https://mail.example.com/*"],
              "content_scripts": [{"matches": ["https://mail.example.com/*"]}]}, 400),
    LEGACY: ({"manifest_version": 2, "name": "Old Toolbar", "version": "0.9",
              "permissions": ["<all_urls>", "history", "tabs"]}, 800),
    DEVTOOL: ({"manifest_version": 3, "name": "My Own Widget", "version": "0.0.1",
               "permissions": ["activeTab", "storage"]}, 5),
    PLANTED: ({"manifest_version": 3, "name": "Coupon Companion", "version": "3.0",
               "permissions": ["storage"]}, 20),
}

PREFS = {
    SHOPPER: {"state": 1, "location": 1, "install_time": chrome_time(900),
              "manifest": {"name": "Shopping Helper", "version": "4.2.0", "manifest_version": 3},
              "active_permissions": {"api": ["cookies", "webRequest", "scripting", "storage"],
                                     "explicit_host": ["<all_urls>"]}},
    MAILER: {"state": 1, "location": 1, "install_time": chrome_time(700),
             "active_permissions": {"api": ["cookies"], "explicit_host": ["https://mail.example.com/*"]}},
    LEGACY: {"state": 0, "location": 1, "install_time": chrome_time(1200), "disable_reasons": 1},
    DEVTOOL: {"state": 1, "location": 4, "install_time": chrome_time(30)},
    PLANTED: {"state": 1, "location": 2, "install_time": chrome_time(60), "ack_external": True},
}

STATE_AGE = {SHOPPER: 2, MAILER: 200, LEGACY: 400}


def build_chrome(root: Path, ids=None, vendor="Google/Chrome", profile="Default", offset=0) -> Path:
    """One Chromium profile: version folders, manifests, a settings document, state folders."""
    base = root / "Application Support" / vendor / profile
    for ext_id in (ids if ids is not None else sorted(MANIFESTS)):
        manifest, age = MANIFESTS[ext_id]
        version = "{0}_0".format(manifest["version"])
        write(base / "Extensions" / ext_id / version / "manifest.json",
              json.dumps(manifest), days_ago=age + offset)
    settings = dict((k, v) for k, v in PREFS.items() if ids is None or k in ids)
    write(base / "Preferences", json.dumps({"extensions": {"settings": {}}, "profile": {"name": profile}}))
    write(base / "Secure Preferences", json.dumps({"extensions": {"settings": settings}}))
    for ext_id, age in STATE_AGE.items():
        if ids is not None and ext_id not in ids:
            continue
        folder = base / "Local Extension Settings" / ext_id
        folder.mkdir(parents=True, exist_ok=True)
        os.utime(str(folder), (ts(age), ts(age)))
    return base


FIREFOX_ADDONS = {
    "schemaVersion": 35,
    "addons": [
        {"id": "blocker@example.org", "type": "extension", "version": "1.5",
         "defaultLocale": {"name": "Request Blocker"}, "active": True, "userDisabled": False,
         "location": "app-profile", "signedState": 2, "manifestVersion": 2,
         "installDate": 1740000000000, "updateDate": 1750000000000,
         "userPermissions": {"permissions": ["webRequest", "webRequestBlocking"],
                             "origins": ["<all_urls>"]}},
        {"id": "theme@example.org", "type": "theme", "version": "1.0",
         "defaultLocale": {"name": "A Theme"}, "active": True, "location": "app-profile"},
    ],
}


def build_firefox(root: Path, body=None, label="Firefox/Profiles", profile="w1e2r3t4.default") -> Path:
    path = root / "Application Support" / label / profile / "extensions.json"
    write(path, body if body is not None else json.dumps(FIREFOX_ADDONS))
    return path


def read_all(root, families=("chromium", "firefox", "safari"), **cfg):
    cfg = dict(cfg)
    # The reader picks its macOS layout from a base directory literally called "Application
    # Support", exactly as it does on a real machine, so the fixture tree is shaped the same way.
    cfg.setdefault("roots", [str(Path(root) / "Application Support")])
    cfg.setdefault("safari_roots", [str(root)])
    sources, records = [], []
    for family in families:
        s, r = extensions.read_source(family, Budget(), cfg)
        sources += s
        records += r
    return sources, records


def view_for(root, **cfg):
    sources, records = read_all(root, **cfg)
    return extensions.analyse(records, NOW, {"out_dir": str(root)}), sources, records


# ---------------------------------------------------------------- reading

class TestChromiumReading(unittest.TestCase):
    def test_every_extension_in_the_profile_is_found_with_its_manifest_and_its_state(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            _, records = read_all(tmp, families=("chromium",))
            by_id = dict((r["id"], r) for r in records)
            self.assertEqual(sorted(by_id), sorted(MANIFESTS))
            self.assertEqual(by_id[SHOPPER]["name"], "Shopping Helper")
            self.assertEqual(by_id[SHOPPER]["version"], "4.2.0")
            self.assertEqual(by_id[SHOPPER]["manifest_version"], 3)
            self.assertIn("<all_urls>", by_id[SHOPPER]["host_permissions"])
            self.assertIn("https://mail.example.com/*", by_id[MAILER]["content_matches"])
            self.assertTrue(by_id[SHOPPER]["enabled"])
            self.assertFalse(by_id[LEGACY]["enabled"])
            self.assertEqual(by_id[DEVTOOL]["install_source"], "unpacked")
            self.assertEqual(by_id[PLANTED]["install_source"], "sideloaded")
            self.assertTrue(by_id[SHOPPER]["installed"].startswith("2024-"))

    def test_the_version_folder_mtime_is_carried_as_a_proxy_and_says_so(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            _, records = read_all(tmp, families=("chromium",))
            for record in records:
                self.assertTrue(record["updated_is_proxy"], record["id"])
                self.assertTrue(record["updated"], record["id"])

    def test_a_localised_manifest_name_is_resolved_from_the_bundled_strings(self):
        with TemporaryDirectory() as tmp:
            base = build_chrome(Path(tmp), ids=[SHOPPER])
            version = base / "Extensions" / SHOPPER / "4.2.0_0"
            write(version / "manifest.json", json.dumps(
                {"manifest_version": 3, "name": "__MSG_appName__", "default_locale": "en",
                 "version": "4.2.0", "host_permissions": ["<all_urls>"]}))
            write(version / "_locales" / "en" / "messages.json",
                  json.dumps({"appName": {"message": "Shopping Helper"}}))
            _, records = read_all(tmp, families=("chromium",))
            self.assertEqual(records[0]["name"], "Shopping Helper")


class TestFirefoxReading(unittest.TestCase):
    def test_the_inventory_is_read_and_a_theme_is_not_counted_as_an_extension(self):
        with TemporaryDirectory() as tmp:
            build_firefox(Path(tmp))
            sources, records = read_all(tmp, families=("firefox",))
            self.assertEqual([r["id"] for r in records], ["blocker@example.org"])
            self.assertEqual(records[0]["name"], "Request Blocker")
            self.assertEqual(records[0]["manifest_version"], 2)
            self.assertIn("<all_urls>", records[0]["host_permissions"])
            self.assertTrue(any(s.found for s in sources))

    def test_firefox_reports_a_real_update_date_rather_than_a_proxy(self):
        with TemporaryDirectory() as tmp:
            build_firefox(Path(tmp))
            _, records = read_all(tmp, families=("firefox",))
            self.assertFalse(records[0]["updated_is_proxy"])
            self.assertTrue(records[0]["updated"].startswith("2025-"))


class TestSafariIsAPartialNotAZero(unittest.TestCase):
    def test_an_absent_safari_is_a_labelled_unknown_that_refuses_to_imply_zero(self):
        with TemporaryDirectory() as tmp:
            sources, records = read_all(tmp, families=("safari",), safari_roots=[tmp])
            self.assertEqual(records, [])
            self.assertEqual(len(sources), 1)
            self.assertFalse(sources[0].found)
            self.assertIn("not zero", sources[0].note)

    def test_a_readable_safari_store_yields_rows_whose_reach_is_unknown_not_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "Library/Containers/com.apple.Safari/Data/Library/Safari/AppExtensions/Extensions.plist"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(plistlib.dumps({"Installed Extensions": [
                {"WebExtensionBundleIdentifier": "com.example.shield", "Extension Name": "Shield",
                 "Enabled": True}]}))
            sources, records = read_all(tmp, families=("safari",), safari_roots=[tmp])
            self.assertEqual([r["name"] for r in records], ["Shield"])
            self.assertFalse(records[0]["reach_published"])
            self.assertTrue(sources[0].found)
            self.assertIn("no host permissions", sources[0].note)
            view = extensions.analyse(records, NOW, {"out_dir": tmp})
            self.assertEqual(view["reach_unknown"], 1)
            self.assertEqual(view["reach_known"], 0)
            self.assertIn("Shield", view["reach_unknown_names"])
            self.assertIn("unknown rather than none", view["rows"][0]["plain"])


# ---------------------------------------------------------------- reach

class TestReachTiers(unittest.TestCase):
    def test_each_extension_lands_in_the_tier_its_patterns_earn(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            tiers = dict((r["name"], r["reach"]) for r in view["rows"])
            self.assertEqual(tiers["Shopping Helper"], "all_urls")
            self.assertEqual(tiers["Old Toolbar"], "all_urls")        # MV2 declares hosts in permissions
            self.assertEqual(tiers["Inbox Tidier"], "specific_hosts")
            self.assertEqual(tiers["My Own Widget"], "active_tab_only")
            self.assertEqual(tiers["Coupon Companion"], "none")

    def test_the_tier_list_is_ordered_by_reach_and_never_alphabetically(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertEqual([t["tier"] for t in view["reach"]],
                             ["all_urls", "broad_wildcard", "specific_hosts", "active_tab_only", "none"])
            ranks = [extensions.TIER_RANK[r["reach"]] for r in view["rows"] if r["reach_known"]]
            self.assertEqual(ranks, sorted(ranks, reverse=True))

    def test_a_wildcard_suffix_is_broad_but_one_companys_subdomains_are_specific(self):
        self.assertEqual(extensions.pattern_scope("*://*.com/*"), "wild")
        self.assertEqual(extensions.pattern_scope("https://*.example.com/*"), "specific")
        self.assertEqual(extensions.pattern_scope("<all_urls>"), "all")
        self.assertEqual(extensions.pattern_scope("*://*/*"), "all")
        self.assertEqual(extensions.pattern_scope("storage"), "")

    def test_http_and_https_wildcards_together_are_everything_but_one_alone_is_broad(self):
        self.assertEqual(extensions.reach_of(["https://*/*"], []), "broad_wildcard")
        self.assertEqual(extensions.reach_of(["https://*/*", "http://*/*"], []), "all_urls")
        self.assertEqual(extensions.reach_of([], ["activeTab"]), "active_tab_only")
        self.assertEqual(extensions.reach_of([], ["storage"]), "none")

    def test_every_row_carries_a_sentence_in_plain_english(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            plain = dict((r["name"], r["plain"]) for r in view["rows"])
            self.assertIn("every site", plain["Shopping Helper"])
            self.assertIn("signed in", plain["Shopping Helper"])
            self.assertIn("mail.example.com", plain["Inbox Tidier"])
            self.assertIn("no longer supports", plain["Old Toolbar"])
            self.assertIn("when you click it", plain["My Own Widget"])
            for sentence in plain.values():
                self.assertNotIn("risky", sentence.lower())


# ---------------------------------------------------------------- combinations

class TestDangerousCombinations(unittest.TestCase):
    def test_each_combination_is_its_own_class_named_for_what_it_does(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            named = dict((c["permission"], c) for c in view["combinations"])
            self.assertIn("cookies", named)
            self.assertIn("webRequest", named)
            self.assertIn("scripting", named)
            self.assertIn("history", named)
            self.assertIn("signed in", named["cookies"]["reason"])
            self.assertIn("browsing history", named["history"]["reason"])
            self.assertEqual(named["cookies"]["extensions"], ["Shopping Helper"])
            self.assertEqual(named["history"]["extensions"], ["Old Toolbar"])
            for combo in view["combinations"]:
                self.assertNotEqual(combo["reason"].strip().lower(), "risky")

    def test_a_second_power_without_blanket_access_is_not_a_combination(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertNotIn("Inbox Tidier", view["combination_names"])
            self.assertEqual(sorted(view["combination_names"]), ["Old Toolbar", "Shopping Helper"])
            self.assertEqual(view["combination_extensions"], 2)

    def test_the_headline_reads_the_way_the_card_promises(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertIn("5 extensions.", view["headline"])
            self.assertIn("2 read every page including your bank.", view["headline"])
            self.assertIn("not updated in a year", view["headline"])
            self.assertIn("still reading", view["headline"])


# ---------------------------------------------------------------- flags

class TestFlags(unittest.TestCase):
    def test_manifest_v2_is_flagged(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertEqual(view["mv2"]["count"], 1)
            self.assertEqual(view["mv2"]["names"], ["Old Toolbar"])

    def test_sideloaded_and_unpacked_are_counted_separately(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertEqual(view["sideloaded"]["names"], ["Coupon Companion"])
            self.assertEqual(view["unpacked"]["names"], ["My Own Widget"])
            self.assertIn("usually yours", view["unpacked"]["note"])
            self.assertEqual(view["sideloaded"]["count"], 1)
            self.assertEqual(view["unpacked"]["count"], 1)

    def test_the_staleness_proxy_is_labelled_a_proxy_everywhere_it_appears(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, sources, _ = view_for(tmp)
            self.assertTrue(view["stale"]["proxy"])
            self.assertIn("proxy", view["stale"]["proxy_note"])
            self.assertEqual(view["stale"]["days"], 365)
            self.assertEqual(sorted(view["stale"]["names"]), ["Inbox Tidier", "Old Toolbar"])
            self.assertIn("(proxy)", extensions.report_markdown(view, {}, [s.__dict__ for s in sources]))
            self.assertTrue(all(r["updated_is_proxy"] for r in view["rows"]))

    def test_idle_counts_only_state_that_has_not_moved_and_names_the_ones_still_reading(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertEqual(view["idle"]["days"], 90)
            self.assertEqual(view["idle"]["count"], 2)
            self.assertEqual(view["idle"]["still_reading"], 1)
            self.assertEqual(view["idle"]["names"], ["Old Toolbar"])
            self.assertIn("never its contents", view["idle"]["note"])

    def test_the_thresholds_are_configurable(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            _, records = read_all(tmp, families=("chromium",))
            view = extensions.analyse(records, NOW, {"out_dir": tmp, "stale_days": 15, "idle_days": 1})
            self.assertEqual(view["stale"]["days"], 15)
            self.assertEqual(view["stale"]["count"], 3)          # 800d, 400d and 20d, not 10d or 5d
            self.assertEqual(view["idle"]["count"], 5)
            self.assertIn("not updated in 15 days", view["headline"])


# ---------------------------------------------------------------- rollup

class TestCrossBrowserRollup(unittest.TestCase):
    def test_one_extension_in_two_browsers_is_one_row_with_two_badges(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            build_chrome(Path(tmp), ids=[SHOPPER], vendor="BraveSoftware/Brave-Browser", offset=20)
            view, _, records = view_for(tmp)
            self.assertEqual(len(records), 6)
            self.assertEqual(view["installs"], 6)
            self.assertEqual(view["extensions"], 5)
            row = [r for r in view["rows"] if r["id"] == SHOPPER][0]
            self.assertEqual(row["browsers"], ["Brave", "Chrome"])
            self.assertEqual(row["installs"], 2)
            self.assertEqual(row["badges"], "[Brave] [Chrome]")
            self.assertEqual([r["name"] for r in view["rows"]].count("Shopping Helper"), 1)
            self.assertEqual([x["name"] for x in view["cross_browser"]], ["Shopping Helper"])

    def test_the_rolled_up_row_keeps_the_worst_reach_and_the_newest_update(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp), ids=[MAILER])
            build_chrome(Path(tmp), ids=[MAILER], vendor="Vivaldi", offset=-395)
            view, _, _ = view_for(tmp)
            row = [r for r in view["rows"] if r["id"] == MAILER][0]
            self.assertEqual(row["installs"], 2)
            self.assertEqual(row["reach"], "specific_hosts")
            self.assertLess(row["updated_days"], 30)
            self.assertFalse(row["stale"])

    def test_a_second_profile_of_the_same_browser_is_still_one_extension(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp), ids=[SHOPPER])
            build_chrome(Path(tmp), ids=[SHOPPER], profile="Profile 3")
            view, _, _ = view_for(tmp)
            self.assertEqual(view["extensions"], 1)
            self.assertEqual(view["installs"], 2)
            self.assertEqual(view["rows"][0]["profiles"], ["Default", "Profile 3"])


# ---------------------------------------------------------------- degradation

class TestDegradation(unittest.TestCase):
    def test_an_unreadable_firefox_costs_firefox_and_nothing_else(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            build_firefox(Path(tmp), body="{not json at all")
            sources, records = read_all(tmp)
            by_name = dict((s.name, s) for s in sources)
            self.assertFalse([s for s in sources if s.name.startswith("Firefox")][0].found)
            self.assertIn("not JSON", [s for s in sources if s.name.startswith("Firefox")][0].note)
            self.assertTrue(by_name["Chrome"].found)
            self.assertEqual(len(records), 5)

    def test_a_machine_with_no_browser_at_all_reports_a_miss_per_family_and_no_rows(self):
        with TemporaryDirectory() as tmp:
            sources, records = read_all(tmp, safari_roots=[tmp])
            self.assertEqual(records, [])
            self.assertEqual(len(sources), 3)
            self.assertTrue(all(not s.found and s.note for s in sources))
            view = extensions.analyse(records, NOW, {"out_dir": tmp})
            self.assertEqual(view["extensions"], 0)
            self.assertIn("no extensions found", view["verdict"])
            self.assertIsInstance(extensions.render(view, {}), str)

    def test_a_settings_document_that_will_not_parse_still_yields_the_manifests(self):
        with TemporaryDirectory() as tmp:
            base = build_chrome(Path(tmp))
            (base / "Secure Preferences").write_text("{\"extensions\": {\"settings\": ", encoding="utf-8")
            (base / "Preferences").write_text("{", encoding="utf-8")
            sources, records = read_all(tmp, families=("chromium",))
            self.assertEqual(len(records), 5)
            self.assertTrue(sources[0].found)
            self.assertIn("settings", sources[0].note)
            self.assertTrue(all(r["enabled"] is None for r in records))

    def test_an_extension_folder_with_no_manifest_does_not_end_the_read(self):
        with TemporaryDirectory() as tmp:
            base = build_chrome(Path(tmp))
            (base / "Extensions" / SHOPPER / "4.2.0_0" / "manifest.json").unlink()
            sources, records = read_all(tmp, families=("chromium",))
            self.assertEqual(len(records), 5)
            row = [r for r in records if r["id"] == SHOPPER][0]
            self.assertEqual(row["name"], "Shopping Helper")       # the settings copy still names it
            self.assertTrue(sources[0].found)

    def test_a_profile_whose_extensions_folder_is_empty_is_a_labelled_miss(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "Application Support" / "Chromium" / "Default" / "Extensions").mkdir(parents=True)
            build_chrome(Path(tmp))
            sources, records = read_all(tmp, families=("chromium",))
            miss = [s for s in sources if not s.found]
            self.assertEqual([s.name for s in miss], ["Chromium"])
            self.assertIn("no readable extension folder", miss[0].note)
            self.assertEqual(len(records), 5)


# ---------------------------------------------------------------- promises

class TestNeverReadsExtensionStorage(unittest.TestCase):
    BANNED = ("Local Storage", "IndexedDB", "Local Extension Settings", "Cookies")

    def test_no_path_containing_a_storage_folder_is_ever_opened(self):
        opened = []
        real_open = builtins.open

        def recorder(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            build_firefox(Path(tmp))
            builtins.open = recorder
            try:
                sources, records = read_all(tmp, safari_roots=[tmp])
                view = extensions.analyse(records, NOW, {"out_dir": tmp})
                extensions.render(view, {})
                extensions.report_markdown(view, {}, [s.__dict__ for s in sources])
            finally:
                builtins.open = real_open
        self.assertTrue(opened, "the reader opened nothing at all, so this proves nothing")
        for path in opened:
            for banned in self.BANNED:
                self.assertNotIn(banned, path, "opened a storage path: {0}".format(path))

    def test_the_module_still_detects_idle_extensions_without_opening_that_folder(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertGreater(view["idle"]["count"], 0)

    def test_the_promise_is_stated_in_the_report(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, sources, _ = view_for(tmp)
            markdown = extensions.report_markdown(view, {}, [s.__dict__ for s in sources])
            self.assertIn("never opens extension storage", markdown)
            for banned in self.BANNED:
                self.assertIn(banned, markdown)


class TestRedaction(unittest.TestCase):
    def test_no_filesystem_path_reaches_the_view_or_the_card(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            build_firefox(Path(tmp))
            view, sources, _ = view_for(tmp)
            blob = json.dumps(view, default=str, sort_keys=True)
            for text in (blob, extensions.render(view, {}),
                         extensions.report_markdown(view, {}, [s.__dict__ for s in sources])):
                self.assertNotIn(tmp, text)
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn("Application Support", text)

    def test_an_unpacked_extension_is_named_without_naming_the_folder_it_was_loaded_from(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp), ids=[DEVTOOL])
            view, _, _ = view_for(tmp)
            row = view["rows"][0]
            self.assertEqual(row["install_source"], "unpacked")
            self.assertNotIn("/", json.dumps(row["location_label"]))


class TestDeterminism(unittest.TestCase):
    def test_the_same_tree_and_the_same_now_produce_byte_identical_output(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            build_chrome(Path(tmp), ids=[SHOPPER], vendor="Microsoft Edge", offset=3)
            build_firefox(Path(tmp))
            first = view_for(tmp)
            second = view_for(tmp)
            self.assertEqual(json.dumps(first[0], default=str, sort_keys=True),
                             json.dumps(second[0], default=str, sort_keys=True))
            self.assertEqual(extensions.render(first[0], {}), extensions.render(second[0], {}))
            self.assertEqual(extensions.report_markdown(first[0], {}, []),
                             extensions.report_markdown(second[0], {}, []))

    def test_the_source_list_is_stable_across_reads(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            build_chrome(Path(tmp), ids=[MAILER], vendor="Vivaldi")
            names = [[s.name for s in read_all(tmp, families=("chromium",))[0]] for _ in range(3)]
            self.assertEqual(names[0], names[1])
            self.assertEqual(names[1], names[2])


class TestDeltaAgainstTheBaseline(unittest.TestCase):
    def test_a_first_run_says_so_instead_of_inventing_a_change(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            self.assertTrue(view["delta"]["first_run"])
            self.assertIn("first run", view["since"].lower())

    def test_a_second_run_reports_what_was_added_removed_and_what_gained_reach(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp), ids=[MAILER, DEVTOOL])
            first, _, _ = view_for(tmp)
            extensions.write_baseline(tmp, first, NOW)

            build_chrome(Path(tmp), ids=[SHOPPER])
            base = Path(tmp) / "Application Support" / "Google" / "Chrome" / "Default"
            write(base / "Extensions" / MAILER / "1.1.0_0" / "manifest.json", json.dumps(
                {"manifest_version": 3, "name": "Inbox Tidier", "version": "1.1.0",
                 "host_permissions": ["<all_urls>"]}), days_ago=1)
            second, _, _ = view_for(tmp)
            self.assertFalse(second["delta"]["first_run"])
            self.assertIn(SHOPPER, second["delta"]["added"])
            self.assertIn(MAILER, second["delta"]["grew"])
            self.assertEqual(second["delta"]["removed"], {})
            self.assertIn("since", second["since"])


# ---------------------------------------------------------------- rendering

class TestRendering(unittest.TestCase):
    def test_the_card_is_sixty_four_columns_and_carries_the_reach_split(self):
        from daily_core.common import display_width

        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, _, _ = view_for(tmp)
            card = extensions.render(view, {})
            for line in card.splitlines():
                self.assertEqual(display_width(line), 64, line)
            self.assertIn("WHAT THEY CAN REACH", card)
            self.assertIn("every page you visit", card)
            self.assertIn("no extension storage was opened", card.lower())

    def test_every_number_in_the_report_carries_its_denominator(self):
        with TemporaryDirectory() as tmp:
            build_chrome(Path(tmp))
            view, sources, _ = view_for(tmp)
            markdown = extensions.report_markdown(view, {}, [s.__dict__ for s in sources])
            self.assertIn("| extensions (unique ids) | 5 |", markdown)
            self.assertIn("of 5", markdown)
            self.assertIn("share of", markdown)
            self.assertIn("Sorted by reach, worst first", markdown)
            self.assertIn("Coupon Companion", markdown)


# ---------------------------------------------------------------- the prefs parser

class TestChromePrefsParser(unittest.TestCase):
    WHOLE = json.dumps({"extensions": {"settings": PREFS}, "profile": {"name": "Default"}})

    def test_a_whole_document_yields_every_entry(self):
        settings = chromeprefs.read_settings(self.WHOLE)
        self.assertEqual(sorted(settings), sorted(PREFS))
        self.assertFalse(chromeprefs.was_partial(self.WHOLE))

    def test_a_truncated_document_yields_the_entries_that_closed_cleanly(self):
        cut = self.WHOLE[:self.WHOLE.rindex("}", 0, len(self.WHOLE) - 40)]
        settings = chromeprefs.read_settings(cut)
        self.assertTrue(settings)
        self.assertTrue(set(settings).issubset(set(PREFS)))
        self.assertTrue(chromeprefs.was_partial(cut))

    def test_a_document_with_nothing_recoverable_raises_rather_than_returning_zero(self):
        with self.assertRaises(chromeprefs.Unreadable):
            chromeprefs.read_settings("not a settings document at all")

    def test_the_signed_document_wins_where_both_name_the_same_extension(self):
        merged = chromeprefs.merge({SHOPPER: {"state": 0, "location": 2}},
                                   {SHOPPER: {"state": 1}})
        self.assertEqual(merged[SHOPPER]["state"], 1)
        self.assertEqual(merged[SHOPPER]["location"], 2)

    def test_locations_are_translated_into_something_a_person_can_act_on(self):
        self.assertEqual(chromeprefs.normalise("x", {"location": 1})["install_source"], "store")
        self.assertEqual(chromeprefs.normalise("x", {"location": 4})["install_source"], "unpacked")
        self.assertEqual(chromeprefs.normalise("x", {"location": 2})["install_source"], "sideloaded")
        self.assertEqual(chromeprefs.normalise("x", {"location": 7})["install_source"], "policy")
        self.assertEqual(chromeprefs.normalise("x", {})["install_source"], "unknown")
        self.assertIsNone(chromeprefs.normalise("x", {})["enabled"])

    def test_an_entry_that_is_not_a_dictionary_is_dropped_rather_than_crashing(self):
        settings = chromeprefs.read_settings(json.dumps(
            {"extensions": {"settings": {SHOPPER: {"state": 1}, MAILER: "corrupt"}}}))
        self.assertEqual(sorted(settings), [SHOPPER])


if __name__ == "__main__":
    unittest.main()
