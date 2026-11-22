#!/usr/bin/env python3
"""Read quota from a same-user Antigravity server without exporting credentials."""

import argparse
import datetime
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import struct
import time


SERVICE = "/exa.language_server_pb.LanguageServerService/"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ERRORS = {
    "not-running": "Open Antigravity, sign in, and open a workspace. No readable local server was found.",
    "no-listener": "Antigravity is running but its local listening socket is not accessible. Check /proc permissions.",
    "unavailable": "Local quota is unavailable. Check Antigravity sign-in and connectivity, then refresh.",
    "unsupported": "The local server returned no supported quota data. Update Antigravity and try again.",
    "internal": "The local quota reader failed. Check Python 3 and /proc access.",
}


class UsageError(Exception):
    pass


def text(value, fallback=""):
    if not isinstance(value, str):
        return fallback
    return " ".join(value.split())[:160] or fallback


def fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return float(value)


def reset_time(value):
    try:
        if not isinstance(value, str):
            return None
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(datetime.timezone.utc).isoformat()
    except ValueError:
        return None


def normalize_summary(payload):
    if not isinstance(payload, dict):
        return []
    summary = payload.get("response", payload)
    if not isinstance(summary, dict) or not isinstance(summary.get("groups"), list):
        return []
    buckets = []
    for group_index, group in enumerate(summary["groups"]):
        if not isinstance(group, dict) or not isinstance(group.get("buckets"), list):
            continue
        group_name = text(group.get("displayName"), f"Quota group {group_index + 1}")
        for bucket_index, bucket in enumerate(group["buckets"]):
            if not isinstance(bucket, dict):
                continue
            remaining = fraction(bucket.get("remainingFraction"))
            if remaining is None:
                continue
            bucket_id = text(bucket.get("bucketId"), str(bucket_index))
            window = text(bucket.get("window"), "unknown")
            name = text(bucket.get("displayName"), window if window != "unknown" else "Quota")
            buckets.append({
                "id": f"summary:{group_index}:{bucket_id}",
                "group": group_name,
                "name": name,
                "window": window,
                "remaining": remaining,
                "resetAt": reset_time(bucket.get("resetTime")),
            })
    return buckets


def normalize_legacy(payload):
    if not isinstance(payload, dict):
        return [], None
    status = payload.get("userStatus")
    if not isinstance(status, dict):
        return [], None
    plan_status = status.get("planStatus", {})
    plan_info = plan_status.get("planInfo", {}) if isinstance(plan_status, dict) else {}
    plan = text(plan_info.get("planName")) if isinstance(plan_info, dict) else ""
    config = status.get("cascadeModelConfigData", {})
    models = config.get("clientModelConfigs", []) if isinstance(config, dict) else []
    if not isinstance(models, list):
        return [], plan or None
    buckets = []
    for index, model in enumerate(models):
        if not isinstance(model, dict) or not isinstance(model.get("quotaInfo"), dict):
            continue
        quota = model["quotaInfo"]
        remaining = fraction(quota.get("remainingFraction"))
        if remaining is None:
            continue
        buckets.append({
            "id": f"legacy:{index}",
            "group": "Model quota (window not provided)",
            "name": text(model.get("label"), f"Model {index + 1}"),
            "window": "unknown",
            "remaining": remaining,
            "resetAt": reset_time(quota.get("resetTime")),
        })
    return buckets, plan or None


def flag(arguments, name):
    for index, argument in enumerate(arguments):
        if argument.startswith(name + "="):
            return argument[len(name) + 1:]
        if argument == name and index + 1 < len(arguments):
            return arguments[index + 1]
    return None


def is_antigravity(arguments):
    if not arguments:
        return False
    executable = Path(arguments[0]).name.lower()
    if executable in {"agy", "antigravity"}:
        return True
    if executable == "node" and len(arguments) > 1:
        return Path(arguments[1]).name.lower() == "agy"
    if not executable.startswith("language_server"):
        return False
    return "antigravity" in arguments[0].lower() or any(
        "antigravity" in (flag(arguments, option) or "").lower()
        for option in ("--app_data_dir", "--extension_server_path")
    )


def discover_processes(proc_root=Path("/proc"), selected_pid=0):
    candidates = []
    for entry in proc_root.iterdir():
        if not entry.name.isdecimal() or (selected_pid and int(entry.name) != selected_pid):
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            arguments = entry.joinpath("cmdline").read_bytes().decode("utf-8").rstrip("\0").split("\0")
            if is_antigravity(arguments):
                candidates.append({"pid": int(entry.name), "token": flag(arguments, "--csrf_token")})
        except (OSError, UnicodeError):
            continue
    return sorted(candidates, key=lambda candidate: candidate["pid"], reverse=True)[:12]


def decode_address(encoded, family):
    raw = bytes.fromhex(encoded)
    words = struct.unpack("=" + "I" * (len(raw) // 4), raw)
    network = struct.pack(">" + "I" * len(words), *words)
    return socket.inet_ntop(family, network)


def listening_addresses(process, proc_root=Path("/proc")):
    process_root = proc_root / str(process["pid"])
    inodes = set()
    try:
        for descriptor in process_root.joinpath("fd").iterdir():
            try:
                match = re.fullmatch(r"socket:\[(\d+)\]", os.readlink(descriptor))
                if match:
                    inodes.add(match[1])
            except OSError:
                continue
    except OSError:
        return []
    addresses = set()
    for table, family in (("tcp", socket.AF_INET), ("tcp6", socket.AF_INET6)):
        try:
            rows = process_root.joinpath("net", table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) < 10 or fields[3] != "0A" or fields[9] not in inodes:
                continue
            try:
                encoded, encoded_port = fields[1].split(":")
                address = decode_address(encoded, family)
                port = int(encoded_port, 16)
            except (ValueError, OSError, struct.error):
                continue
            if address in {"0.0.0.0", "127.0.0.1"}:
                addresses.add(("127.0.0.1", port))
            elif address in {"::", "::1"}:
                addresses.add(("::1", port))
    return sorted(addresses)[:12]


def request_json(host, port, tls, method, token, timeout):
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Only loopback connections are allowed")
    headers = {"Content-Type": "application/json", "Connect-Protocol-Version": "1"}
    if token:
        headers["x-codeium-csrf-token"] = token
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection = http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
    else:
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("POST", SERVICE + method, body="{}", headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise UsageError("unavailable")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise UsageError("unsupported")
        return json.loads(body)
    finally:
        connection.close()


def collect(selected_pid=0, proc_root=Path("/proc"), budget=18):
    processes = discover_processes(proc_root, selected_pid)
    if not processes:
        raise UsageError("not-running")
    deadline = time.monotonic() + budget
    endpoints = [
        (process, host, port, tls)
        for process in processes
        for host, port in listening_addresses(process, proc_root)
        for tls in (True, False)
    ]
    if not endpoints:
        raise UsageError("no-listener")
    received_response = False
    for method in ("RetrieveUserQuotaSummary", "GetUserStatus"):
        phase_deadline = min(deadline, time.monotonic() + budget / 2) if method == "RetrieveUserQuotaSummary" else deadline
        for process, host, port, tls in endpoints:
            remaining_time = phase_deadline - time.monotonic()
            if remaining_time <= 0:
                break
            try:
                payload = request_json(host, port, tls, method, process["token"], min(1.0, remaining_time))
                received_response = True
                if method == "RetrieveUserQuotaSummary":
                    buckets, plan = normalize_summary(payload), None
                else:
                    buckets, plan = normalize_legacy(payload)
                if buckets:
                    return {
                        "ok": True,
                        "source": "summary" if method == "RetrieveUserQuotaSummary" else "legacy",
                        "sourcePid": process["pid"],
                        "plan": plan,
                        "fetchedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "buckets": buckets,
                    }
            except (OSError, ValueError, http.client.HTTPException, UsageError):
                continue
    raise UsageError("unsupported" if received_response else "unavailable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, default=0, help="Server PID; zero means automatic")
    arguments = parser.parse_args()
    try:
        result = collect(arguments.pid)
    except UsageError as error:
        code = str(error)
        result = {"ok": False, "error": {"code": code, "message": ERRORS[code]}}
    except Exception:
        result = {"ok": False, "error": {"code": "internal", "message": ERRORS["internal"]}}
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
