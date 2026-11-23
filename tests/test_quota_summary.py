import copy
import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import antigravity_usage as usage
import cli_quota
from quota_summary import normalize_summary, reset_time


ARRAY = json.loads(Path(__file__).with_name("fixtures").joinpath("quota-array.json").read_text())


class SummaryTests(unittest.TestCase):
    def test_supplied_grouped_response(self):
        buckets = normalize_summary(ARRAY)
        self.assertEqual([bucket["remaining"] for bucket in buckets], [0.20886855, 0.98493, 0.498844, 1, 0])
        self.assertEqual([bucket["window"] for bucket in buckets], ["weekly", "5h", "weekly", "5h", "weekly"])
        self.assertEqual([bucket["group"] for bucket in buckets],
                         ["Gemini Models", "Gemini Models", "Claude and GPT models", "Claude and GPT models", "Gemini 4 Argon"])
        for bucket, timestamp in zip(buckets, [1795858378, 1795435174, 1795875702, 1795449299, 1795939343]):
            self.assertEqual(datetime.datetime.fromisoformat(bucket["resetAt"]).timestamp(), timestamp)
        self.assertEqual(len({bucket["id"] for bucket in buckets}), 5)
        self.assertEqual(normalize_summary({"response": ARRAY}), buckets)
        self.assertEqual(normalize_summary(ARRAY[0][0]), buckets)

    def test_invalid_fractions_do_not_become_allowances(self):
        for remaining in [None, True, False, "0.5", -1, 1.01, float("nan"), float("inf"), 10 ** 1000]:
            self.assertEqual(normalize_summary([[["test", "Test", "weekly", remaining]], "Test group"]), [])
        for payload in [None, {}, [], [0.5], ["test", 0.5], [[["test", "Test", "weekly"]], "Test group"],
                        [[["test", "Test", None, 0.5]], "Test group"]]:
            self.assertEqual(normalize_summary(payload), [])

    def test_missing_and_invalid_reset_do_not_discard_zero_quota(self):
        for reset in [None, [], [True], [1795939343], ["nan"], ["999999999999"], ["1", "2"], "tomorrow"]:
            buckets = normalize_summary([[["test", "Test", "weekly", 0, None, reset]], "Test group"])
            self.assertEqual(buckets[0]["remaining"], 0)
            self.assertIsNone(buckets[0]["resetAt"])
            self.assertIsNone(reset_time(reset))
        buckets = normalize_summary([[["test", "Test", "weekly", 1]], "Test group"])
        self.assertEqual(buckets[0]["remaining"], 1)
        self.assertIsNone(buckets[0]["resetAt"])

    def test_loopback_acquisition_decodes_arrays(self):
        with patch.object(usage, "discover_processes", return_value=[{"pid": 42, "token": "private-token"}]), \
                patch.object(usage, "listening_addresses", return_value=[("127.0.0.1", 12345)]), \
                patch.object(usage, "request_json", return_value=ARRAY):
            result = usage.collect_server()
        self.assertEqual(result["source"], "summary")
        self.assertEqual(result["buckets"], normalize_summary(ARRAY))
        self.assertNotIn("private-token", json.dumps(result))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        environment = patch.dict(os.environ, {"HOME": str(self.root), "XDG_CACHE_HOME": str(self.root / "cache")})
        environment.start()
        self.addCleanup(environment.stop)

    def capture(self):
        return cli_quota.import_summary(io.BytesIO(json.dumps(ARRAY).encode()))

    def test_stdin_import_to_reader_end_to_end_and_privacy(self):
        payload = copy.deepcopy(ARRAY)
        payload[0].append({"token": "private-token", "email": "private@example.com"})
        imported = subprocess.run([sys.executable, str(HELPERS / "antigravity_usage.py"), "--import-quota"],
                                  input=json.dumps(payload), capture_output=True, text=True, check=True, timeout=5)
        self.assertTrue(json.loads(imported.stdout)["ok"])
        fetched = subprocess.run([sys.executable, str(HELPERS / "antigravity_usage.py")],
                                 capture_output=True, text=True, check=True, timeout=5)
        result = json.loads(fetched.stdout)
        self.assertEqual(result["source"], "import")
        self.assertIsNone(result["sourcePid"])
        self.assertEqual(result["buckets"], normalize_summary(ARRAY))
        path = cli_quota.cache_path("import")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        for private in ["private-token", "private@example.com", "Models within this group", "You have hit"]:
            self.assertNotIn(private, path.read_text() + imported.stdout + fetched.stdout + fetched.stderr)

    def test_invalid_import_invalidates_only_import_cache(self):
        cli_quota.capture(io.BytesIO(b'{"quotas":{"models":{"test":{"remaining":50}}}}'))
        for raw in [b"{}", b"null", b"[]", b"private malformed JSON", b"\xff", b" " * (cli_quota.MAX_BYTES + 1)]:
            self.capture()
            with self.assertRaisesRegex(cli_quota.CliError, "import-invalid"):
                cli_quota.import_summary(io.BytesIO(raw))
            self.assertFalse(cli_quota.cache_path("import").exists())
            self.assertEqual(cli_quota.read_cache()["source"], "cli")

    def test_freshness_priority_and_pid_bypass(self):
        self.capture()
        with patch.object(usage, "collect_server", side_effect=AssertionError("No desktop required")):
            result = usage.collect()
            self.assertEqual(result["source"], "import")
            self.assertEqual(usage.collect()["fetchedAt"], result["fetchedAt"])
        cli_quota.capture(io.BytesIO(b'{"quotas":{"models":{"test":{"remaining":50}}}}'))
        self.assertEqual(usage.collect()["source"], "cli")
        with patch.object(usage, "collect_server", return_value={"source": "summary"}) as server:
            self.assertEqual(usage.collect(42)["source"], "summary")
            server.assert_called_once_with(42, Path("/proc"), 18)

    def test_stale_or_future_import_is_not_current_and_desktop_can_recover(self):
        for delta in [-601, 60]:
            self.capture()
            path = cli_quota.cache_path("import")
            payload = json.loads(path.read_text())
            payload["capturedAt"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delta)).isoformat()
            cli_quota.atomic_json(path, payload)
            with self.assertRaisesRegex(cli_quota.CliError, "import-stale"):
                cli_quota.read_cache("import")
            with patch.object(usage, "collect_server", side_effect=usage.UsageError("not-running")):
                with self.assertRaisesRegex(cli_quota.CliError, "import-stale"):
                    usage.collect()
            with patch.object(usage, "collect_server", return_value={"source": "summary"}):
                self.assertEqual(usage.collect()["source"], "summary")

    def test_cache_permissions_and_unsafe_files(self):
        self.capture()
        path = cli_quota.cache_path("import")
        path.chmod(0o644)
        with self.assertRaisesRegex(cli_quota.CliError, "import-cache"):
            cli_quota.read_cache("import")
        path.unlink()
        path.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(cli_quota.CliError, "import-cache"):
            cli_quota.read_cache("import")
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(cli_quota.CliError, "import-cache"):
            cli_quota.read_cache("import")
        path.unlink()
        path.parent.chmod(0o755)
        with self.assertRaisesRegex(cli_quota.CliError, "import-cache"):
            self.capture()


if __name__ == "__main__":
    unittest.main()
