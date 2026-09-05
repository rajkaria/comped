"""The leaderboard: the two API functions (api/), the poster the Play runs (leaderboard/post_score.py),
and the promise that nothing else in the packages can reach the network."""
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "leaderboard"))
import _common  # noqa: E402
import leaderboard as board_fn  # noqa: E402
import post_score  # noqa: E402
import score as score_fn  # noqa: E402

GOOD = {"device": "11111111-1111-4111-8111-111111111111", "handle": "priya", "multiplier": 12.99, "comped_usd": 2560.98,
        "plan_usd": 197.13, "tier": "All-you-can-eat", "plan": "Claude Max 20x", "plan_id": "claude-max-200",
        "plan_source": "auto", "providers": ["anthropic"], "harnesses": ["claude-code"], "days_back": 30,
        "active_days": 22, "sessions": 99, "cache_share": 0.98, "client": "comped/0.1.5"}


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(doc, capture=None):
    def open_(req, timeout=None):
        if capture is not None:
            capture.append((req.full_url, json.loads(req.data.decode("utf-8")), dict(req.header_items())))
        return FakeResponse(json.dumps(doc).encode("utf-8"))
    return open_


ENV = {"SUPABASE_URL": "https://db.example.test", "SUPABASE_KEY": "sb_publishable_test"}


class ScoreFunction(unittest.TestCase):
    def test_shape_check_names_the_first_problem(self):
        self.assertIsNone(_common.check_score(GOOD))
        self.assertIn("uuid", _common.check_score(dict(GOOD, device="nope")))
        self.assertIn("handle", _common.check_score(dict(GOOD, handle="x" * 33)))
        self.assertIn("comped_usd", _common.check_score(dict(GOOD, comped_usd="2560")))
        self.assertIn("multiplier", _common.check_score(dict(GOOD, multiplier=True)))
        self.assertIn("providers", _common.check_score(dict(GOOD, providers="anthropic")))
        self.assertIn("providers", _common.check_score(dict(GOOD, providers=["a"] * 13)))

    def test_a_good_score_is_sent_to_the_submit_rpc_with_the_key_and_comes_back_with_links(self):
        calls = []
        with mock.patch.dict(os.environ, ENV):
            status, body = score_fn.submit(GOOD, opener=opener_returning(
                {"ok": True, "rank": 7, "of": 312, "percentile": 2.2, "eligible": True, "held": False, "handle": "priya"}, calls))
        self.assertEqual(status, 200)
        self.assertEqual(body["rank"], 7)
        self.assertEqual(body["url"], "https://gotcomped.com/leaderboard.html#priya")
        self.assertEqual(body["board"], "https://gotcomped.com/leaderboard.html")
        url, sent, headers = calls[0]
        self.assertEqual(url, "https://db.example.test/rest/v1/rpc/comped_submit")
        self.assertEqual(sent, {"p": GOOD})
        self.assertEqual(headers["Apikey"], "sb_publishable_test")

    def test_the_database_saying_no_is_a_400_and_too_soon_is_a_429(self):
        with mock.patch.dict(os.environ, ENV):
            self.assertEqual(score_fn.submit(GOOD, opener=opener_returning({"ok": False, "error": "handle may use letters"}))[0], 400)
            status, body = score_fn.submit(GOOD, opener=opener_returning({"ok": False, "error": "too soon", "retry_after": 15}))
        self.assertEqual(status, 429)
        self.assertEqual(body["retry_after"], 15)

    def test_a_bad_shape_never_reaches_storage(self):
        def boom(req, timeout=None):
            raise AssertionError("storage was called")
        with mock.patch.dict(os.environ, ENV):
            status, body = score_fn.submit(dict(GOOD, device=42), opener=boom)
        self.assertEqual(status, 400)

    def test_storage_trouble_is_a_502_not_a_crash(self):
        import urllib.error

        def down(req, timeout=None):
            raise urllib.error.URLError("no route")
        with mock.patch.dict(os.environ, ENV):
            self.assertEqual(score_fn.submit(GOOD, opener=down)[0], 502)
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            status, body = score_fn.submit(GOOD, opener=opener_returning({"ok": True}))
        self.assertEqual(status, 502)
        self.assertIn("not configured", body["error"])


class BoardFunction(unittest.TestCase):
    def test_sort_and_limit_are_validated_and_clamped(self):
        calls = []
        with mock.patch.dict(os.environ, ENV):
            status, body, cache = board_fn.board("sort=comped_usd&limit=9999", opener=opener_returning({"ok": True, "rows": []}, calls))
        self.assertEqual(status, 200)
        self.assertEqual(calls[0][1], {"p_sort": "comped_usd", "p_limit": 500})
        self.assertIn("s-maxage", cache)
        self.assertEqual(body["rules"]["ranks_from_usd"], 20)
        with mock.patch.dict(os.environ, ENV):
            self.assertEqual(board_fn.board("sort=handle", opener=opener_returning({"ok": True}))[0], 400)
            self.assertEqual(board_fn.board("limit=ten", opener=opener_returning({"ok": True}))[0], 400)
            status, body, cache = board_fn.board("", opener=opener_returning({"ok": True, "rows": []}, calls))
        self.assertEqual(calls[-1][1], {"p_sort": "multiplier", "p_limit": 100})

    def test_the_reply_never_carries_a_device_id(self):
        # The SQL function is what enforces this; the check here is on the field list the function
        # documents, so a change to either side shows up in review.
        doc = pathlib.Path(ROOT / "api" / "leaderboard.py").read_text(encoding="utf-8")
        self.assertNotIn('"device"', doc.split("Rows are one per")[0])


def priced_doc():
    return {"total_usd": "2560.98421505", "multiplier": "12.99165950759739583333333333", "plan_cost": "197.1252566735112936344969199",
            "plan_ids": ["claude-max-200"], "plan_source": "auto", "days_back": 30, "active_days": 22, "sessions": 99,
            "cache_share": "0.9823131493591238845582959012",
            "tier": {"name": "All-you-can-eat", "line": "x", "rank": 5, "of": 7},
            "plan_ladder": [{"assumed": False, "label": "Claude Pro", "plan_id": "claude-pro-20", "cost": "19.7", "multiplier": "129.9"},
                            {"assumed": True, "label": "Claude Max 20x", "plan_id": "claude-max-200", "cost": "197.1", "multiplier": "12.99"}],
            "detected": {"basis": "models",
                         "harnesses": [{"harness": "claude-code", "label": "Claude Code", "found": True, "records": 11151},
                                       {"harness": "codex", "label": "Codex CLI", "found": True, "records": 0}],
                         "providers": [{"key": "anthropic", "label": "Anthropic", "records": 11151, "tokens": 1, "usd": "2560.98"},
                                       {"key": "openai", "label": "OpenAI", "records": 0, "tokens": 0, "usd": "0"}]}}


class Poster(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)
        (self.out / ".priced.json").write_text(json.dumps(priced_doc()), encoding="utf-8")
        (self.out / ".repeats.json").write_text(json.dumps({"clusters": [], "handle": "fromrepeats"}), encoding="utf-8")
        (self.out / "comped-share.txt").write_text("old line\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_poster(self, *args, reply=None, raise_=None):
        calls = []

        def fake_post(url, body, timeout):
            calls.append((url, body))
            if raise_:
                raise raise_
            return reply
        buf = io.StringIO()
        with mock.patch.object(post_score, "post", fake_post), mock.patch("sys.stdout", buf):
            rc = post_score.main(["--out-dir", str(self.out)] + list(args))
        lines = buf.getvalue().rstrip("\n").split("\n")
        return rc, lines[:-1], json.loads(lines[-1]), calls

    def test_payload_is_the_five_numbers_and_a_name_and_nothing_from_the_logs(self):
        rc, human, result, calls = self.run_poster("--handle", "priya", reply=(200, json.dumps(
            {"ok": True, "rank": 7, "of": 312, "percentile": 2.2, "eligible": True, "held": False, "handle": "priya",
             "url": "https://gotcomped.com/leaderboard.html#priya"})))
        self.assertEqual(rc, 0)
        url, body = calls[0]
        self.assertEqual(url, post_score.DEFAULT_URL)
        self.assertEqual(sorted(body), sorted(GOOD))
        self.assertEqual(body["handle"], "priya")
        self.assertEqual(body["multiplier"], 12.9917)
        self.assertEqual(body["comped_usd"], 2560.98)
        self.assertEqual(body["plan_usd"], 197.13)
        self.assertEqual(body["plan"], "Claude Max 20x")
        self.assertEqual(body["plan_id"], "claude-max-200")
        self.assertEqual(body["providers"], ["anthropic"])
        self.assertEqual(body["harnesses"], ["claude-code"])
        self.assertEqual(body["tier"], "All-you-can-eat")
        self.assertEqual(body["client"], "comped/" + post_score.VERSION)
        flat = json.dumps(body)
        for never in ("/Users", "claude-fable", "models", "session_id", "path", "prompt"):
            self.assertNotIn(never, flat, never)
        self.assertEqual(result["rank"], 7)
        self.assertTrue(result["posted"])
        self.assertIn("#7 of 312", "\n".join(human))
        # The reply and the exact payload are on disk for anyone who wants to read them.
        rec = json.loads((self.out / "comped-rank.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["sent"], body)
        self.assertEqual(rec["reply"]["rank"], 7)
        # And the share line now carries the rank, in the core's own wording.
        share = (self.out / "comped-share.txt").read_text(encoding="utf-8")
        self.assertIn("#7 of 312 on the gotcomped.com leaderboard", share)
        self.assertTrue(share.startswith("My comp score is 13× (All-you-can-eat), #7 of 312"), share)

    def test_device_id_is_made_once_and_reused(self):
        self.run_poster(reply=(200, json.dumps({"ok": True, "rank": 1, "of": 1})))
        first = (self.out / "comped-device.txt").read_text(encoding="utf-8").strip()
        _, _, _, calls = self.run_poster(reply=(200, json.dumps({"ok": True, "rank": 1, "of": 1})))
        self.assertEqual(calls[0][1]["device"], first)
        self.assertEqual(len(first), 36)

    def test_handle_falls_back_to_the_one_the_repeats_step_was_given(self):
        _, _, _, calls = self.run_poster(reply=(200, json.dumps({"ok": True})))
        self.assertEqual(calls[0][1]["handle"], "fromrepeats")

    def test_leaderboard_false_sends_nothing(self):
        rc, human, result, calls = self.run_poster("--leaderboard", "false")
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])
        self.assertEqual(result, {"posted": False, "skipped": True})
        self.assertFalse((self.out / "comped-device.txt").exists())
        self.assertFalse((self.out / "comped-rank.json").exists())

    def test_offline_is_a_warning_and_exit_0_and_the_share_line_is_untouched(self):
        rc, human, result, calls = self.run_poster(raise_=OSError("Name or service not known"))
        self.assertEqual(rc, 0)
        self.assertFalse(result["posted"])
        self.assertIn("could not reach", result["warning"])
        self.assertIn("unaffected", "\n".join(human))
        self.assertEqual((self.out / "comped-share.txt").read_text(encoding="utf-8"), "old line\n")

    def test_a_refusal_is_reported_not_raised(self):
        rc, human, result, calls = self.run_poster(reply=(400, json.dumps({"ok": False, "error": "handle may use letters"})))
        self.assertEqual(rc, 0)
        self.assertFalse(result["posted"])
        self.assertIn("handle may use letters", result["warning"])

    def test_not_ranked_says_why(self):
        rc, human, result, calls = self.run_poster(reply=(200, json.dumps(
            {"ok": True, "rank": None, "of": 40, "eligible": False, "reason": "ranks from 3 active days"})))
        self.assertTrue(result["posted"])
        self.assertIsNone(result["rank"])
        self.assertIn("ranks from 3 active days", "\n".join(human))

    def test_no_priced_card_is_a_warning(self):
        (self.out / ".priced.json").unlink()
        rc, human, result, calls = self.run_poster()
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])
        self.assertIn("no priced card", result["warning"])

    def test_the_script_runs_as_a_process_and_prints_json_last(self):
        env = dict(os.environ, COMPED_LEADERBOARD_URL="http://127.0.0.1:9/api/score")
        r = subprocess.run([sys.executable, str(ROOT / "leaderboard" / "post_score.py"), "--out-dir", str(self.out),
                            "--timeout", "1"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        last = json.loads(r.stdout.rstrip("\n").split("\n")[-1])
        self.assertFalse(last["posted"])


class ShareLine(unittest.TestCase):
    def test_rank_goes_after_the_tier_and_the_line_no_longer_claims_to_be_offline(self):
        from comped_core.render_report import share_text
        v = {"total_usd": Decimal("2560.98"), "multiplier": Decimal("12.99"), "tier": {"name": "All-you-can-eat"},
             "plan_cost": Decimal("197.13"), "detected": priced_doc()["detected"], "window_days": 30, "site": "https://gotcomped.com"}
        plain = share_text(v)
        self.assertTrue(plain.startswith("My comp score is 13× (All-you-can-eat). Anthropic gave me $2,560"), plain)
        self.assertNotIn("nothing leaves", plain)
        ranked = share_text(dict(v, rank=7, rank_of=312))
        self.assertIn("(All-you-can-eat), #7 of 312 on the gotcomped.com leaderboard. Anthropic", ranked)


class Packaging(unittest.TestCase):
    def test_the_poster_version_tracks_the_play_version(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_plays
        self.assertEqual(post_score.VERSION, build_plays.VERSION)

    def test_only_the_poster_can_reach_the_network_in_any_package(self):
        subprocess.run([sys.executable, str(ROOT / "tools" / "sync_plays.py")], check=True, capture_output=True)
        net = re.compile(r"^\s*(import|from)\s+(urllib|http\b|socket|requests|ssl)", re.M)
        for slug in ("session-ledger", "comped", "wrong-turns"):
            for p in (ROOT / "plays" / slug / "resources").rglob("*.py"):
                if net.search(p.read_text(encoding="utf-8")):
                    self.assertEqual((slug, p.name), ("comped", "post_score.py"), "{0} can open a socket".format(p))
        self.assertTrue((ROOT / "plays" / "comped" / "resources" / "post_score.py").is_file())
        self.assertFalse((ROOT / "plays" / "session-ledger" / "resources" / "post_score.py").exists())

    def test_the_play_runs_the_poster_last_and_only_when_asked(self):
        text = (ROOT / "plays" / "comped" / "main.ts").read_text(encoding="utf-8")
        self.assertIn("@resource{post_score.py}", text)
        self.assertIn("- name: leaderboard", text)
        self.assertIn("default: 'true'", text.split("- name: leaderboard")[1].split("- name:")[0])
        # The poster reads the priced card, so it must come after the card is rendered.
        step = text.split(" * steps:")[1].split("  post_score:")[1].split("argv:")[0]
        self.assertIn("- render_card", step)


if __name__ == "__main__":
    unittest.main()
