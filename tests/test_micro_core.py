"""Unit tests for micro_core: the emit contract, scalars and formatting."""
import base64
import gzip
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from micro_core import common, cronx, decode, secrets, size, store


class TestEmit(unittest.TestCase):
    def test_json_is_the_last_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = common.emit("two lines\nof human text", {"ok": True, "n": 3})
        self.assertEqual(rc, 0)
        lines = buf.getvalue().rstrip("\n").split("\n")
        self.assertEqual(lines[:2], ["two lines", "of human text"])
        self.assertEqual(json.loads(lines[-1]), {"ok": True, "n": 3})

    def test_empty_human_still_emits_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            common.emit("", {"ok": True})
        self.assertEqual(json.loads(buf.getvalue().strip()), {"ok": True})


class TestScalars(unittest.TestCase):
    def test_as_bool(self):
        for s in ("true", "TRUE", "1", "yes", "on"):
            self.assertTrue(common.as_bool(s), s)
        for s in ("false", "0", "", "no", None, "maybe"):
            self.assertFalse(common.as_bool(s), s)

    def test_now_utc_parses_z_and_defaults_aware(self):
        self.assertEqual(common.now_utc("2026-09-05T14:22:03Z"),
                         datetime(2026, 9, 5, 14, 22, 3, tzinfo=timezone.utc))
        self.assertIsNotNone(common.now_utc("").tzinfo)

    def test_now_utc_tolerates_a_naive_string(self):
        self.assertEqual(common.now_utc("2026-09-05T14:22:03"),
                         datetime(2026, 9, 5, 14, 22, 3, tzinfo=timezone.utc))

    def test_day_is_local(self):
        d = common.now_utc("2026-09-05T14:22:03Z")
        self.assertEqual(common.day(d, timezone.utc), "2026-09-05")

    def test_sparkline_and_trunc(self):
        self.assertEqual(common.sparkline([]), "")
        self.assertEqual(len(common.sparkline([0, 1, 2, 3])), 4)
        self.assertEqual(len(common.sparkline([5, 5, 5])), 3)
        self.assertEqual(common.trunc("abcdefgh", 5), "abcd…")
        self.assertEqual(common.trunc("abc", 5), "abc")

    def test_human_numbers(self):
        self.assertEqual(common.human_int(1234567), "1,234,567")
        self.assertEqual(common.human_usd("0.19"), "$0.19")
        self.assertEqual(common.human_usd("1234.5"), "$1,234.50")


class TestWarn(unittest.TestCase):
    def test_warn_is_ok_true(self):
        w = common.warn("nothing here yet")
        self.assertTrue(w["ok"])
        self.assertEqual(w["warning"], "nothing here yet")


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_append_then_read_roundtrip(self):
        store.append(self.dir, "punch", {"note": "api", "t": "2026-09-05T10:00:00Z"})
        store.append(self.dir, "punch", {"note": "docs", "t": "2026-09-05T11:30:00Z"})
        got = store.read(self.dir, "punch")
        self.assertEqual([e.data["note"] for e in got], ["api", "docs"])
        self.assertEqual(got[0].t.hour, 10)

    def test_append_stamps_time_and_version(self):
        store.append(self.dir, "punch", {"note": "x"})
        with open(str(store.stream_path(self.dir, "punch"))) as fh:
            line = json.loads(fh.read().strip())
        self.assertIn("t", line)
        self.assertEqual(line["v"], 1)

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(store.read(self.dir, "never-written"), [])

    def test_torn_trailing_line_is_skipped_not_fatal(self):
        p = store.stream_path(self.dir, "punch")
        os.makedirs(self.dir, exist_ok=True)
        with open(str(p), "w") as fh:
            fh.write('{"t":"2026-09-05T10:00:00Z","note":"good"}\n{"t":"2026-')
        self.assertEqual(len(store.read(self.dir, "punch")), 1)

    def test_read_since_filters(self):
        store.append(self.dir, "punch", {"note": "old", "t": "2026-09-01T10:00:00Z"})
        store.append(self.dir, "punch", {"note": "new", "t": "2026-09-05T10:00:00Z"})
        got = store.read(self.dir, "punch", since=common.now_utc("2026-09-03T00:00:00Z"))
        self.assertEqual([e.data["note"] for e in got], ["new"])

    def test_streak_counts_back_from_today(self):
        days = {"2026-09-03", "2026-09-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (3, 3))

    def test_streak_survives_a_today_with_no_entry(self):
        self.assertEqual(store.streak({"2026-09-03", "2026-09-04"}, "2026-09-05")[0], 2)

    def test_streak_breaks_on_a_two_day_gap(self):
        days = {"2026-09-01", "2026-09-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (2, 2))

    def test_streak_longest_is_not_the_current_one(self):
        days = {"2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-09-05"}
        self.assertEqual(store.streak(days, "2026-09-05"), (1, 4))

    def test_grid_is_window_long_and_ends_today(self):
        g = store.grid({"2026-09-05"}, "2026-09-05", 7)
        self.assertEqual(len(g), 7)
        self.assertTrue(g.endswith("█"))
        self.assertEqual(g.count("·"), 6)

    def test_worst_weekday_needs_enough_history(self):
        self.assertIsNone(store.worst_weekday({"2026-09-05"}, "2026-09-05", 7))

    def test_worst_weekday_names_the_day_missed_most(self):
        days = set()
        d = datetime(2026, 8, 10, tzinfo=timezone.utc)          # a Monday
        for i in range(28):
            day_ = d + timedelta(days=i)
            if day_.weekday() != 6:                              # never on a Sunday
                days.add(day_.strftime("%Y-%m-%d"))
        self.assertEqual(store.worst_weekday(days, "2026-09-06", 28), "Sunday")

    def test_days_with_entries_uses_local_time(self):
        store.append(self.dir, "punch", {"note": "x", "t": "2026-09-05T10:00:00Z"})
        got = store.days_with_entries(store.read(self.dir, "punch"), timezone.utc)
        self.assertEqual(got, {"2026-09-05"})


class TestDecode(unittest.TestCase):
    JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
           "eyJzdWIiOiJ1c2VyXzg4MTIiLCJleHAiOjE3ODg2MDAwMDB9.c2lnbmF0dXJlLWJ5dGVz")

    def test_jwt_is_identified_with_claims_and_expiry(self):
        layers = decode.peel(self.JWT)
        self.assertEqual(layers[0].kind, "jwt")
        self.assertEqual(layers[0].detail["alg"], "HS256")
        self.assertIn("sub", layers[0].detail["claims"])
        self.assertIn("exp", layers[0].detail)

    def test_jwt_signature_is_never_printed_whole(self):
        rendered = decode.render(decode.peel(self.JWT))
        self.assertNotIn("c2lnbmF0dXJlLWJ5dGVz", rendered)

    def test_peels_base64_then_json(self):
        inner = base64.b64encode(b'{"hello":"world"}').decode()
        self.assertEqual([l.kind for l in decode.peel(inner)], ["base64", "json"])

    def test_peels_base64_gzip_json(self):
        blob = base64.b64encode(gzip.compress(b'{"a":1}')).decode()
        self.assertEqual([l.kind for l in decode.peel(blob)], ["base64", "gzip", "json"])

    def test_depth_is_honoured(self):
        blob = base64.b64encode(gzip.compress(b'{"a":1}')).decode()
        self.assertEqual(len(decode.peel(blob, depth=2)), 2)

    def test_url_encoding_is_a_layer(self):
        layers = decode.peel("%7B%22a%22%3A1%7D")
        self.assertEqual([l.kind for l in layers], ["urlencoded", "json"])

    def test_uuid_v7_reports_its_embedded_time(self):
        l = decode.identify("018f2c3d-4e5f-7abc-8def-0123456789ab")
        self.assertEqual(l.kind, "uuid")
        self.assertEqual(l.detail["version"], 7)
        self.assertIn("time", l.detail)

    def test_uuid_v4_has_no_time(self):
        l = decode.identify("f47ac10b-58cc-4372-a567-0e02b2c3d479")
        self.assertEqual(l.detail["version"], 4)
        self.assertNotIn("time", l.detail)

    def test_epoch_ms_vs_seconds(self):
        self.assertEqual(decode.identify("1788600000").detail["unit"], "s")
        self.assertEqual(decode.identify("1788600000000").detail["unit"], "ms")

    def test_an_implausible_epoch_stays_a_number(self):
        self.assertEqual(decode.identify("42").kind, "number")

    def test_private_ip_is_classified(self):
        self.assertEqual(decode.identify("10.1.2.3").detail["scope"], "private")
        self.assertEqual(decode.identify("8.8.8.8").detail["scope"], "public")
        self.assertEqual(decode.identify("100.64.0.1").detail["scope"], "carrier-grade NAT")

    def test_plain_text_is_a_leaf_not_a_guess(self):
        l = decode.identify("just some words here")
        self.assertEqual(l.kind, "text")
        self.assertIsNone(l.text)

    def test_hash_by_length(self):
        self.assertEqual(decode.identify("a" * 64).detail["candidates"], ["sha256"])
        self.assertTrue(decode.identify("a" * 40).detail["git"])

    def test_hex_colour(self):
        l = decode.identify("#1f6feb")
        self.assertEqual(l.kind, "color")
        self.assertEqual(l.detail["rgb"], [31, 111, 235])

    def test_url_breaks_out_its_query(self):
        l = decode.identify("https://example.com/a/b?x=1&y=two")
        self.assertEqual(l.kind, "url")
        self.assertEqual(l.detail["host"], "example.com")
        self.assertEqual(l.detail["query"], {"x": "1", "y": "two"})

    def test_data_uri_peels_to_its_payload(self):
        uri = "data:application/json;base64," + base64.b64encode(b'{"a":1}').decode()
        self.assertEqual([l.kind for l in decode.peel(uri)], ["data-uri", "json"])

    def test_magic_bytes_behind_base64(self):
        blob = base64.b64encode(b"%PDF-1.7\n" + b"x" * 40).decode()
        layers = decode.peel(blob)
        self.assertEqual(layers[-1].kind, "binary")
        self.assertEqual(layers[-1].detail["format"], "PDF")

    def test_a_git_sha_is_not_read_as_base64(self):
        self.assertEqual(decode.identify("356a192b7913b04c54574d18c28d46e6395428ab").kind, "hash")

    def test_semver_and_mac_and_cidr(self):
        self.assertEqual(decode.identify("1.2.3-rc.1").kind, "semver")
        self.assertEqual(decode.identify("3c:22:fb:aa:bb:cc").kind, "mac")
        self.assertEqual(decode.identify("192.168.0.0/24").kind, "cidr")

    def test_cron_is_recognised_as_a_schedule(self):
        self.assertEqual(decode.identify("30 9 * * 1-5").kind, "cron")

    def test_reveal_false_truncates_long_values(self):
        blob = base64.b64encode(json.dumps({"k": "y" * 400}).encode()).decode()
        rendered = decode.render(decode.peel(blob, reveal=False))
        self.assertNotIn("y" * 200, rendered)


class TestSecrets(unittest.TestCase):
    def test_aws_key_is_a_blocker(self):
        f = secrets.scan("aws_access_key_id = AKIA1234567890ABCD12")
        self.assertEqual(f[0].kind, "aws-access-key")
        self.assertEqual(f[0].severity, "blocker")

    def test_github_and_slack_and_stripe(self):
        kinds = {f.kind for f in secrets.scan(
            "a=ghp_" + "a" * 36 + "\nb=xox" + "b-123456789012-abcdefghijklmnop\nc=sk_live_" + "b" * 24)}
        self.assertEqual(kinds, {"github-token", "slack-token", "stripe-key"})

    def test_private_key_block(self):
        f = secrets.scan("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----")
        self.assertEqual(f[0].kind, "private-key")
        self.assertEqual(f[0].severity, "blocker")

    def test_placeholder_is_not_a_finding(self):
        self.assertEqual(secrets.scan("API_KEY=your-key-here"), [])
        self.assertEqual(secrets.scan("TOKEN=${GITHUB_TOKEN}"), [])
        self.assertEqual(secrets.scan("password=changeme"), [])
        self.assertEqual(secrets.scan("SECRET=<your-secret>"), [])
        self.assertEqual(secrets.scan("KEY=$MY_VAR"), [])

    def test_documented_example_key_is_not_a_finding(self):
        self.assertEqual(secrets.scan("key = AKIAIOSFODNN7EXAMPLE"), [])
        self.assertEqual(secrets.scan("k=sk_test_" + "c" * 24), [])

    def test_low_entropy_env_value_is_not_a_finding(self):
        self.assertEqual(secrets.scan("API_KEY=aaaaaaaaaaaaaaaa"), [])

    def test_high_entropy_env_value_is_medium_not_blocker(self):
        f = secrets.scan("SESSION_SECRET=8fJ2kL9mQ4xR7vN1pZ3wY6bC0dE5gH")
        self.assertEqual(f[0].severity, "medium")

    def test_connection_string_password(self):
        f = secrets.scan("postgres://app:hunter2hunter2@db.internal:5432/prod")
        self.assertEqual(f[0].kind, "connection-string")

    def test_a_url_without_credentials_is_not_a_finding(self):
        self.assertEqual(secrets.scan("https://example.com/a?b=1"), [])

    def test_redaction_removes_every_secret_and_keeps_the_rest(self):
        text = "host=db\nAPI_KEY=AKIA1234567890ABCD12\nport=5432"
        out = secrets.redact(text, secrets.scan(text))
        self.assertNotIn("AKIA1234567890ABCD12", out)
        self.assertIn("host=db", out)
        self.assertIn("port=5432", out)

    def test_redaction_handles_two_secrets_on_one_line(self):
        text = "a=AKIA1234567890ABCD12 b=ghp_" + "z" * 36
        out = secrets.redact(text, secrets.scan(text))
        self.assertNotIn("AKIA1234567890ABCD12", out)
        self.assertNotIn("ghp_" + "z" * 36, out)

    def test_masked_finding_never_carries_the_secret(self):
        for f in secrets.scan("API_KEY=AKIA1234567890ABCD12"):
            self.assertNotIn("1234567890ABCD12", f.masked)

    def test_line_numbers_are_one_based(self):
        f = secrets.scan("one\ntwo\nkey=AKIA1234567890ABCD12")
        self.assertEqual(f[0].line, 3)

    def test_entropy_separates_random_from_repeated(self):
        self.assertLess(secrets.entropy("aaaaaaaaaaaaaaaa"), 1.0)
        self.assertGreater(secrets.entropy("8fJ2kL9mQ4xR7vN1"), 3.0)

    def test_verdicts(self):
        self.assertEqual(secrets.verdict([]), "safe")
        self.assertEqual(secrets.verdict(secrets.scan("k=AKIA1234567890ABCD12")), "do-not-paste")
        self.assertEqual(secrets.verdict(secrets.scan("SESSION_SECRET=8fJ2kL9mQ4xR7vN1pZ3wY6bC0dE5gH")),
                         "redact")


class TestCron(unittest.TestCase):
    def test_weekday_morning(self):
        spec = cronx.parse("30 9 * * 1-5")
        fires = cronx.next_fires(spec, common.now_utc("2026-09-05T12:00:00Z"), 3, timezone.utc)
        self.assertEqual([f.strftime("%a %H:%M") for f in fires], ["Mon 09:30", "Tue 09:30", "Wed 09:30"])

    def test_dom_and_dow_are_ored_not_anded(self):
        spec = cronx.parse("0 0 13 * 5")
        fires = cronx.next_fires(spec, common.now_utc("2026-11-01T00:00:00Z"), 5, timezone.utc)
        got = [f.strftime("%Y-%m-%d") for f in fires]
        self.assertIn("2026-11-13", got)
        self.assertIn("2026-11-06", got)

    def test_only_dom_restricted_does_not_or_in_every_day(self):
        spec = cronx.parse("0 0 1 * *")
        fires = cronx.next_fires(spec, common.now_utc("2026-09-05T00:00:00Z"), 2, timezone.utc)
        self.assertEqual([f.day for f in fires], [1, 1])

    def test_macros(self):
        self.assertEqual(cronx.parse("@daily"), cronx.parse("0 0 * * *"))
        self.assertEqual(cronx.parse("@hourly")["minute"], {0})

    def test_step_and_names(self):
        spec = cronx.parse("*/15 * * * MON")
        self.assertEqual(sorted(spec["minute"]), [0, 15, 30, 45])
        self.assertEqual(spec["dow"], {1})

    def test_sunday_is_both_zero_and_seven(self):
        self.assertEqual(cronx.parse("0 0 * * 7")["dow"], cronx.parse("0 0 * * 0")["dow"])

    def test_bad_field_is_a_value_error_with_a_readable_message(self):
        with self.assertRaises(ValueError) as e:
            cronx.parse("99 * * * *")
        self.assertIn("minute", str(e.exception))
        with self.assertRaises(ValueError):
            cronx.parse("* * *")

    def test_english(self):
        self.assertEqual(cronx.describe(cronx.parse("30 9 * * 1-5")), "every weekday at 09:30")
        self.assertEqual(cronx.describe(cronx.parse("0 0 * * *")), "every day at 00:00")
        self.assertEqual(cronx.describe(cronx.parse("*/15 * * * *")), "every 15 minutes")

    def test_average_interval(self):
        fires = cronx.next_fires(cronx.parse("0 * * * *"), common.now_utc("2026-09-05T00:00:00Z"),
                                 5, timezone.utc)
        self.assertEqual(cronx.average_interval_min(fires), 60)

    def test_dst_warning_for_an_hour_that_does_not_exist(self):
        tz = common.tz_of("Europe/London")
        w = cronx.dst_warning(cronx.parse("30 1 * * *"), tz, common.now_utc("2027-03-01T00:00:00Z"))
        self.assertIsNotNone(w)

    def test_no_dst_warning_in_utc(self):
        self.assertIsNone(cronx.dst_warning(cronx.parse("30 1 * * *"), timezone.utc,
                                            common.now_utc("2027-03-01T00:00:00Z")))

    def test_a_skipped_local_hour_is_not_offered_as_a_fire(self):
        tz = common.tz_of("Europe/London")
        fires = cronx.next_fires(cronx.parse("30 1 * * *"), common.now_utc("2027-03-27T12:00:00Z"), 2, tz)
        self.assertNotIn("2027-03-28", [f.strftime("%Y-%m-%d") for f in fires])


class TestSize(unittest.TestCase):
    def test_measurements_are_exact(self):
        m = size.measure("one two\nthree\n")
        self.assertEqual((m["lines"], m["words"], m["bytes"]), (2, 3, 14))

    def test_token_range_brackets_the_estimate(self):
        low, mid, high = size.token_range("hello world " * 100)
        self.assertLess(low, mid)
        self.assertLess(mid, high)

    def test_more_text_is_never_fewer_tokens(self):
        self.assertGreater(size.token_range("x" * 2000)[1], size.token_range("x" * 1000)[1])

    def test_cjk_is_denser_than_ascii(self):
        self.assertGreater(size.token_range("的" * 200)[1], size.token_range("a" * 200)[1])

    def test_code_is_denser_than_prose(self):
        prose = "the quick brown fox jumps over the lazy dog " * 20
        code = "if (x[i] != y.z) { return f(a, b); } // n=1\n" * 20
        self.assertGreater(size.token_range(code)[1] / len(code), size.token_range(prose)[1] / len(prose))

    def test_a_wider_band_when_the_text_is_mostly_non_ascii(self):
        low, mid, high = size.token_range("的" * 500)
        self.assertGreaterEqual((high - mid) / float(mid), 0.2)

    def test_window_fit(self):
        f = size.window_fit(50000, 200000)
        self.assertTrue(f["fits"])
        self.assertEqual(f["pct"], 25)
        self.assertEqual(f["headroom"], 150000)
        self.assertFalse(size.window_fit(300000, 200000)["fits"])

    def test_costs_scale_with_the_range(self):
        from comped_core import prices
        rows = size.costs(1000, 2000, ["claude-opus-5"], prices.load_table())
        self.assertEqual(rows[0]["resolved"], "claude-opus-5")
        self.assertLess(float(rows[0]["low_usd"]), float(rows[0]["high_usd"]))

    def test_unknown_model_is_reported_not_priced_at_zero(self):
        from comped_core import prices
        rows = size.costs(100, 200, ["not-a-model"], prices.load_table())
        self.assertIsNone(rows[0]["resolved"])
        self.assertNotIn("low_usd", rows[0])
