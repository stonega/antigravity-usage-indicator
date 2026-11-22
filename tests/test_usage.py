import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "usage", Path(__file__).resolve().parents[1] / "helpers" / "antigravity_usage.py"
)
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)

SUMMARY = {"groups": [{"displayName": "Premium models", "buckets": [
    {"bucketId": "short", "displayName": "Session", "window": "5h",
     "remainingFraction": 0.42, "resetTime": "2026-11-22T10:00:00Z"},
    {"bucketId": "week", "displayName": "Weekly", "window": "7d", "remainingFraction": 0},
]}]}
LEGACY = {"userStatus": {"planStatus": {"planInfo": {"planName": "Test plan"}},
    "cascadeModelConfigData": {"clientModelConfigs": [
        {"label": "Test model", "quotaInfo": {"remainingFraction": 0.25}},
        {"label": "Unknown quota", "quotaInfo": {}},
    ]}}}


class NormalizationTests(unittest.TestCase):
    def test_summary_preserves_windows_and_zero(self):
        buckets = usage.normalize_summary(SUMMARY)
        self.assertEqual([bucket["remaining"] for bucket in buckets], [0.42, 0])
        self.assertEqual([bucket["window"] for bucket in buckets], ["5h", "7d"])
        self.assertEqual(buckets[0]["resetAt"], "2026-11-22T10:00:00+00:00")
        self.assertIsNone(buckets[1]["resetAt"])
        self.assertEqual(usage.normalize_summary({"response": SUMMARY}), buckets)

    def test_invalid_values_are_not_full_or_empty_quota(self):
        for value in [None, True, False, "0.5", -1, 1.1, float("nan"), float("inf")]:
            with self.subTest(value=value):
                payload = {"groups": [{"buckets": [{"remainingFraction": value}]}]}
                self.assertEqual(usage.normalize_summary(payload), [])

    def test_unknown_window_is_not_assumed(self):
        payload = {"groups": [{"buckets": [{"remainingFraction": 1}]}]}
        self.assertEqual(usage.normalize_summary(payload)[0]["window"], "unknown")

    def test_legacy_has_no_invented_weekly_limits(self):
        buckets, plan = usage.normalize_legacy(LEGACY)
        self.assertEqual(plan, "Test plan")
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0]["window"], "unknown")
        self.assertEqual(buckets[0]["remaining"], 0.25)

    def test_malformed_shapes(self):
        for value in [None, [], "bad", {}, {"response": []}, {"groups": [None, {}]},
                      {"userStatus": {"cascadeModelConfigData": {"clientModelConfigs": None}}}]:
            self.assertEqual(usage.normalize_summary(value), [])
            self.assertEqual(usage.normalize_legacy(value)[0], [])

    def test_time_and_label_sanitization(self):
        for value in [None, 123, "bad", "2026-11-22T00:00:00"]:
            self.assertIsNone(usage.reset_time(value))
        self.assertEqual(usage.text("A\nB\tC"), "A B C")
        self.assertEqual(len(usage.text("X" * 500)), 160)


class DiscoveryTests(unittest.TestCase):
    def test_antigravity_only(self):
        self.assertTrue(usage.is_antigravity(["/opt/antigravity/bin/language_server_linux_x64"]))
        self.assertTrue(usage.is_antigravity(["language_server_linux", "--app_data_dir", "antigravity"]))
        self.assertTrue(usage.is_antigravity(["/usr/bin/agy"]))
        self.assertTrue(usage.is_antigravity(["/usr/bin/node", "/usr/bin/agy"]))
        for argv in [[], ["python", "antigravity"], ["/windsurf/language_server_linux"],
                     ["/usr/bin/node", "other.js", "antigravity"]]:
            self.assertFalse(usage.is_antigravity(argv))

    def test_flags_and_selected_pid(self):
        self.assertEqual(usage.flag(["--csrf_token=test-token"], "--csrf_token"), "test-token")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for pid in [100, 200]:
                process = root / str(pid)
                process.mkdir()
                process.joinpath("cmdline").write_bytes(b"/opt/antigravity/language_server_linux\0--csrf_token\0test-token\0")
            self.assertEqual([process["pid"] for process in usage.discover_processes(root)], [200, 100])
            self.assertEqual([process["pid"] for process in usage.discover_processes(root, 100)], [100])
            self.assertEqual(usage.discover_processes(root, 300), [])
            with patch.object(usage.os, "getuid", return_value=os.getuid() + 1):
                self.assertEqual(usage.discover_processes(root), [])

    def test_only_process_owned_listening_sockets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = root / "123"
            process.joinpath("fd").mkdir(parents=True)
            process.joinpath("net").mkdir()
            process.joinpath("fd", "3").symlink_to("socket:[900]")
            process.joinpath("net", "tcp").write_text(
                "header\n"
                "0: 0100007F:C350 00000000:0000 0A 0:0 0:0 0 1000 0 900\n"
                "1: 0100007F:C351 00000000:0000 0A 0:0 0:0 0 1000 0 901\n"
                "2: 0100000A:C352 00000000:0000 0A 0:0 0:0 0 1000 0 900\n"
                "3: 0100007F:C353 00000000:0000 01 0:0 0:0 0 1000 0 900\n"
            )
            process.joinpath("net", "tcp6").write_text(
                "header\n0: 00000000000000000000000001000000:C354 "
                "00000000000000000000000000000000:0000 0A 0:0 0:0 0 1000 0 900\n"
            )
            self.assertEqual(usage.listening_addresses({"pid": 123}, root),
                             [("127.0.0.1", 50000), ("::1", 50004)])


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.process_patch = patch.object(usage, "discover_processes", return_value=[{"pid": 123, "token": "test-token"}])
        self.socket_patch = patch.object(usage, "listening_addresses", return_value=[("127.0.0.1", 50000)])
        self.process_patch.start()
        self.socket_patch.start()
        self.addCleanup(self.process_patch.stop)
        self.addCleanup(self.socket_patch.stop)

    def test_summary_is_preferred_and_credentials_not_exported(self):
        with patch.object(usage, "request_json", return_value=SUMMARY) as request:
            result = usage.collect()
        self.assertEqual(result["source"], "summary")
        self.assertEqual(request.call_count, 1)
        self.assertNotIn("test-token", json.dumps(result))
        self.assertNotIn("userStatus", result)

    def test_legacy_fallback_and_no_false_success(self):
        def respond(host, port, tls, method, token, timeout):
            return {} if method == "RetrieveUserQuotaSummary" else LEGACY
        with patch.object(usage, "request_json", side_effect=respond):
            self.assertEqual(usage.collect()["source"], "legacy")
        with patch.object(usage, "request_json", return_value={}):
            with self.assertRaisesRegex(usage.UsageError, "unsupported"):
                usage.collect()

    def test_error_categories(self):
        with patch.object(usage, "discover_processes", return_value=[]):
            with self.assertRaisesRegex(usage.UsageError, "not-running"):
                usage.collect()
        with patch.object(usage, "listening_addresses", return_value=[]):
            with self.assertRaisesRegex(usage.UsageError, "no-listener"):
                usage.collect()
        with patch.object(usage, "request_json", side_effect=OSError("test-token")):
            with self.assertRaisesRegex(usage.UsageError, "unavailable"):
                usage.collect()

    def test_error_output_does_not_expose_raw_exception(self):
        with patch.object(usage, "collect", side_effect=OSError("test-token")), \
                patch("sys.argv", ["reader"]), patch("builtins.print") as output:
            usage.main()
        result = json.loads(output.call_args.args[0])
        self.assertFalse(result["ok"])
        self.assertNotIn("test-token", json.dumps(result))

    def test_deadline(self):
        with self.assertRaisesRegex(usage.UsageError, "unavailable"):
            usage.collect(budget=0)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.body = json.dumps(SUMMARY).encode()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                owner.requests.append((self.path, self.headers, self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(owner.status)
                self.end_headers()
                self.wfile.write(owner.body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self):
        return usage.request_json("127.0.0.1", self.server.server_port, False,
                                  "RetrieveUserQuotaSummary", "test-token", 1)

    def test_post_contract_no_oauth_and_no_proxy(self):
        with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1"}):
            self.assertEqual(self.request(), SUMMARY)
        path, headers, body = self.requests[0]
        self.assertEqual(path, usage.SERVICE + "RetrieveUserQuotaSummary")
        self.assertEqual(headers["x-codeium-csrf-token"], "test-token")
        self.assertIsNone(headers["Authorization"])
        self.assertEqual(body, b"{}")

    def test_collection_end_to_end_from_fixture_proc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = root / "123"
            process.joinpath("fd").mkdir(parents=True)
            process.joinpath("net").mkdir()
            process.joinpath("cmdline").write_bytes(
                b"/opt/antigravity/language_server_linux\0--csrf_token=test-token\0"
            )
            process.joinpath("fd", "3").symlink_to("socket:[900]")
            port = self.server.server_port
            process.joinpath("net", "tcp").write_text(
                f"header\n0: 0100007F:{port:04X} 00000000:0000 0A 0:0 0:0 0 1000 0 900\n"
            )
            result = usage.collect(proc_root=root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sourcePid"], 123)
        self.assertEqual([bucket["remaining"] for bucket in result["buckets"]], [0.42, 0])
        self.assertNotIn("test-token", json.dumps(result))

    def test_refuses_nonloopback_before_connecting(self):
        with self.assertRaises(ValueError):
            usage.request_json("example.com", 443, True, "GetUserStatus", "test-token", 1)

    def test_errors_and_redirects_are_not_followed(self):
        for status in [302, 401, 403, 500]:
            self.status = status
            with self.assertRaises(usage.UsageError):
                self.request()
        self.assertEqual(len(self.requests), 4)

    def test_oversized_and_malformed_responses(self):
        self.body = b"{" * 100
        with self.assertRaises(ValueError):
            self.request()
        self.body = b" " * (usage.MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(usage.UsageError):
            self.request()


if __name__ == "__main__":
    unittest.main()
