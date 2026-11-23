import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import antigravity_usage as usage
import cli_quota


EVENT = {
    "quotas": {"available": True, "models": {
        "gemini-pro": {"remaining": 42.5, "unrecognized": "private-data"},
        "claude-model": {"remaining": 0},
        "unknown": {"remaining": None},
    }},
    "context_window": {"remaining": 100},
    "workspace": {"current_dir": "/private/project"},
    "session_id": "private-session",
    "token": "private-token",
}

CURRENT_EVENT = {
    "product": "antigravity", "email": "private@example.com", "token": "private-token",
    "quota": {
        "gemini-weekly": {"remaining_fraction": 0.20886855, "reset_time": "2026-11-28T10:52:58Z", "reset_in_seconds": 500},
        "gemini-5h": {"remaining_fraction": 0.98493, "reset_time": "2026-11-23T09:19:34Z"},
        "3p-weekly": {"remaining_fraction": 0.498844},
        "3p-5h": {"remaining_fraction": 1},
        "gemini-argon-wtu-weekly": {"remaining_fraction": 0},
        "credits": {"remaining_amount": 1000},
        "disabled-weekly": {"remaining_fraction": 1, "disabled": True},
    },
}


class CliQuotaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        environment = patch.dict(os.environ, {"HOME": str(self.root), "XDG_CACHE_HOME": str(self.root / "cache")})
        environment.start()
        self.addCleanup(environment.stop)
        self.helper = HELPERS / "antigravity_usage.py"
        self.settings = self.root / ".gemini" / "antigravity-cli" / "settings.json"

    def capture(self, payload=EVENT):
        return cli_quota.capture(io.BytesIO(json.dumps(payload).encode()))

    def run_helper(self, *arguments, payload=None):
        return subprocess.run([sys.executable, str(self.helper), *arguments],
                              input=json.dumps(payload) if payload is not None else "",
                              text=True, capture_output=True, timeout=5, check=True)

    def test_legacy_percentage_schema_and_privacy(self):
        self.assertEqual(self.capture(), "AG 0% left")
        result = cli_quota.read_cache()
        self.assertEqual([bucket["remaining"] for bucket in result["buckets"]], [0.425, 0])
        self.assertEqual(result["source"], "cli")
        self.assertIsNone(result["sourcePid"])
        self.assertTrue(all(bucket["window"] == "unknown" and bucket["resetAt"] is None
                            for bucket in result["buckets"]))
        cache = cli_quota.cache_path()
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cache.parent.stat().st_mode & 0o777, 0o700)
        for private in ["private-data", "/private/project", "private-session", "private-token", "context_window"]:
            self.assertNotIn(private, cache.read_text())
            self.assertNotIn(private, json.dumps(result))

    def test_current_cli_setup_hook_cache_reader_end_to_end(self):
        old_settings = self.root / ".gemini" / "settings.json"
        old_settings.parent.mkdir()
        old_settings.write_text('{"theme":"preserve-old-settings"}')
        installed = json.loads(self.run_helper("--install-cli-statusline").stdout)
        self.assertTrue(installed["ok"])
        self.assertEqual(json.loads(old_settings.read_text()), {"theme": "preserve-old-settings"})
        command = json.loads(self.settings.read_text())["statusLine"]["command"]
        hook = subprocess.run(command, shell=True, input=json.dumps(CURRENT_EVENT), text=True,
                              capture_output=True, timeout=5, check=True)
        self.assertEqual(hook.stdout, "AG 0% left\n")
        result = json.loads(self.run_helper().stdout)
        self.assertEqual(result["source"], "cli")
        buckets = result["buckets"]
        self.assertEqual([bucket["remaining"] for bucket in buckets], [0.20886855, 0.98493, 0.498844, 1, 0])
        self.assertEqual([bucket["window"] for bucket in buckets], ["weekly", "5h", "weekly", "5h", "weekly"])
        self.assertEqual(buckets[0]["resetAt"], "2026-11-28T10:52:58+00:00")
        self.assertIsNone(buckets[2]["resetAt"])
        self.assertEqual(buckets[0]["group"], buckets[1]["group"])
        self.assertNotEqual(buckets[2]["group"], buckets[4]["group"])
        for private in ["private-token", "private@example.com", "remaining_amount", "reset_in_seconds"]:
            self.assertNotIn(private, cli_quota.cache_path().read_text() + json.dumps(result))

    def test_current_cli_unavailable_fields_and_unknown_windows(self):
        for value in [None, True, "0.5", -1, 1.01, float("nan"), float("inf"), 10 ** 1000]:
            self.assertEqual(cli_quota.normalize({"quota": {"gemini-weekly": {"remaining_fraction": value}}}), [])
        for quota in [None, [], {}, {"test": {"remaining_amount": 100}}, {"test": None},
                      {"invalid\nlabel": {"remaining_fraction": 1}}]:
            self.capture()
            self.assertEqual(self.capture({"quota": quota}), "AG quota unavailable")
            self.assertIsNone(cli_quota.read_cache())
        buckets = cli_quota.normalize({"quota": {"new-bucket": {"remaining_fraction": 0, "reset_time": "bad", "reset_in_seconds": 300}}})
        self.assertEqual(buckets[0]["window"], "unknown")
        self.assertIsNone(buckets[0]["resetAt"])

    def test_current_schema_takes_priority_over_legacy_fields(self):
        payload = {**EVENT, **CURRENT_EVENT}
        self.assertEqual(cli_quota.normalize(payload), cli_quota.normalize(CURRENT_EVENT))
        self.assertEqual(cli_quota.normalize({**EVENT, "quota": {}}), [])

    def test_invalid_or_missing_values_are_never_invented(self):
        for value in [None, True, False, "42", -1, 101, float("nan"), float("inf"), 10 ** 1000]:
            with self.subTest(value=value):
                self.assertEqual(cli_quota.normalize({"quotas": {"models": {"test": {"remaining": value}}}}), [])
        for payload in [None, [], {}, {"quotas": None}, {"quotas": {"models": []}},
                        {"quotas": {"models": {"test": None}}},
                        {"quotas": {"models": {"invalid\nlabel": {"remaining": 50}}}}]:
            self.assertEqual(cli_quota.normalize(payload), [])
        full = cli_quota.normalize({"quotas": {"models": {"test": {"remaining": 100}}}})
        self.assertEqual(full[0]["remaining"], 1)

    def test_hook_does_not_round_partial_quota_to_empty_or_full(self):
        for remaining, expected in [(0, "0"), (0.1, "<1"), (99.9, ">99"), (100, "100")]:
            payload = {"quotas": {"models": {"test": {"remaining": remaining}}}}
            self.assertEqual(self.capture(payload), f"AG {expected}% left")

    def test_unavailable_event_invalidates_previous_account_quota(self):
        for payload in [{}, {"quotas": {"available": False}}, {"quotas": {"models": {}}},
                        {"quotas": {"available": False, "models": EVENT["quotas"]["models"]}}]:
            self.capture()
            self.assertEqual(self.capture(payload), "AG quota unavailable")
            self.assertIsNone(cli_quota.read_cache())
        for raw in [b"bad json", b"\xff", b" " * (cli_quota.MAX_BYTES + 1)]:
            self.capture()
            cli_quota.capture(io.BytesIO(raw))
            self.assertIsNone(cli_quota.read_cache())

    def test_reading_does_not_retimestamp_and_stale_data_is_rejected(self):
        self.capture()
        first = cli_quota.read_cache()
        self.assertEqual(cli_quota.read_cache()["fetchedAt"], first["fetchedAt"])
        for delta in [-cli_quota.MAX_AGE_SECONDS - 1, 60]:
            self.capture()
            path = cli_quota.cache_path()
            payload = json.loads(path.read_text())
            timestamp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delta)
            payload["capturedAt"] = timestamp.isoformat()
            cli_quota.atomic_json(path, payload)
            with self.assertRaisesRegex(cli_quota.CliError, "cli-stale"):
                cli_quota.read_cache()

    def test_malformed_cache_and_permissions(self):
        self.assertIsNone(cli_quota.read_cache())
        for payload in [None, {}, {"capturedAt": "bad"}, {**EVENT, "capturedAt": "2026-11-23T00:00:00"}]:
            self.capture()
            cli_quota.atomic_json(cli_quota.cache_path(), payload)
            with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
                cli_quota.read_cache()
        self.capture()
        cli_quota.cache_path().chmod(0o644)
        with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
            cli_quota.read_cache()
        self.capture()
        uid = os.getuid()
        with patch.object(cli_quota.os, "getuid", return_value=uid + 1):
            with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
                cli_quota.read_cache()
        path = cli_quota.cache_path()
        path.unlink()
        path.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
            cli_quota.read_cache()
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
            cli_quota.read_cache()

    def test_capture_refuses_insecure_or_redirected_cache_directory(self):
        path = cli_quota.cache_path()
        path.parent.mkdir(parents=True, mode=0o755)
        with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
            self.capture()
        path.parent.rmdir()
        target = self.root / "target"
        target.mkdir(mode=0o700)
        path.parent.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(cli_quota.CliError, "cli-cache"):
            self.capture()
        self.assertEqual(list(target.iterdir()), [])

    def test_auto_cli_source_does_not_require_proc_or_listener(self):
        self.capture()
        with patch.object(usage, "discover_processes", side_effect=AssertionError("Must not read /proc")):
            self.assertEqual(usage.collect()["source"], "cli")
        with patch.object(usage, "collect_server", return_value={"source": "summary"}) as server:
            self.assertEqual(usage.collect(123)["source"], "summary")
            server.assert_called_once_with(123, Path("/proc"), 18)

    def test_desktop_fallback_and_cli_specific_errors(self):
        with patch.object(cli_quota, "read_cache", side_effect=cli_quota.CliError("cli-stale")), \
                patch.object(usage, "collect_server", return_value={"source": "legacy"}):
            self.assertEqual(usage.collect()["source"], "legacy")
        with patch.object(cli_quota, "read_cache", side_effect=cli_quota.CliError("cli-stale")), \
                patch.object(usage, "collect_server", side_effect=usage.UsageError("not-running")):
            with self.assertRaisesRegex(cli_quota.CliError, "cli-stale"):
                usage.collect()

    def test_setup_preserves_settings_and_is_idempotent(self):
        self.settings.parent.mkdir(parents=True)
        original = {"theme": "dark", "security": {"auth": "private-value"}, "unknown": [1, 2]}
        self.settings.write_text(json.dumps(original))
        result = self.run_helper("--install-cli-statusline")
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertNotIn("private-value", result.stdout + result.stderr)
        installed = json.loads(self.settings.read_text())
        self.assertEqual({key: installed[key] for key in original}, original)
        self.assertIn("--statusline", installed["statusLine"]["command"])
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)
        self.assertTrue(json.loads(self.run_helper("--install-cli-statusline").stdout)["ok"])
        self.assertEqual(json.loads(self.settings.read_text()), installed)

    def test_setup_never_overwrites_custom_or_malformed_settings(self):
        self.settings.parent.mkdir(parents=True)
        for raw in ['{"statusLine":{"type":"command","command":"custom"}}',
                    '{"statusLine":false}', 'invalid-json-private', '[]']:
            self.settings.write_text(raw)
            result = self.run_helper("--install-cli-statusline")
            self.assertFalse(json.loads(result.stdout)["ok"])
            self.assertEqual(self.settings.read_text(), raw)
            self.assertNotIn("invalid-json-private", result.stdout + result.stderr)
        self.settings.unlink()
        self.settings.symlink_to(self.root / "missing")
        self.assertFalse(json.loads(self.run_helper("--install-cli-statusline").stdout)["ok"])
        self.assertFalse((self.root / "missing").exists())
        self.settings.unlink()
        os.mkfifo(self.settings)
        self.assertFalse(json.loads(self.run_helper("--install-cli-statusline").stdout)["ok"])

    def test_setup_hook_and_reader_end_to_end_with_quoted_path(self):
        installed = self.root / "CLI test's $(not-a-command)"
        installed.mkdir()
        for name in ["antigravity_usage.py", "cli_quota.py", "quota_summary.py"]:
            shutil.copy(HELPERS / name, installed / name)
        self.helper = installed / "antigravity_usage.py"
        self.run_helper("--install-cli-statusline")
        command = json.loads(self.settings.read_text())["statusLine"]["command"]
        hook = subprocess.run(command, shell=True, input=json.dumps(EVENT), text=True,
                              capture_output=True, timeout=5, check=True)
        self.assertEqual(hook.stdout, "AG 0% left\n")
        result = json.loads(self.run_helper().stdout)
        self.assertEqual(result["source"], "cli")
        self.assertEqual(result["buckets"][0]["remaining"], 0.425)
        self.assertNotIn("private-token", json.dumps(result))
        self.assertEqual(list(cli_quota.cache_path().parent.glob(".quota-*")), [])

    def test_statusline_failures_are_sanitized(self):
        path = cli_quota.cache_path()
        path.parent.mkdir(parents=True)
        path.parent.chmod(0o755)
        result = self.run_helper("--statusline", payload=EVENT)
        self.assertEqual(result.stdout, "AG quota unavailable\n")
        self.assertEqual(result.stderr, "")

    def test_relative_xdg_cache_home_is_not_used(self):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": "relative"}):
            self.assertEqual(cli_quota.cache_path(), self.root / ".cache" / "antigravity-usage-indicator" / "cli-quota.json")


if __name__ == "__main__":
    unittest.main()
