"""Credential-free CLI quota bridge and private quota-response import cache."""

import datetime
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile

from quota_summary import fraction, normalize_summary, reset_time, sanitized_summary

MAX_BYTES = 2 * 1024 * 1024
MAX_AGE_SECONDS = 600
MESSAGES = {
    "cli-stale": "CLI quota is stale. Run a prompt in the connected Antigravity CLI, then refresh.",
    "cli-cache": "CLI quota is unreadable. Reconnect the CLI status-line bridge in Settings, then run a prompt.",
    "cli-settings": "Cannot connect the CLI. Check ~/.gemini/antigravity-cli/settings.json is a writable JSON object without an existing custom statusLine. See README for manual setup.",
    "import-invalid": "No supported quota summary in stdin JSON. Import only the quota response body, not headers, cookies or credentials.",
    "import-cache": "Imported quota is unreadable. Check the private quota cache permissions and import again.",
    "import-stale": "Imported quota is stale. Import a fresh quota response, then refresh.",
}


class CliError(Exception):
    pass


def normalize(payload):
    if not isinstance(payload, dict):
        return []
    if "quota" in payload:
        quota = payload["quota"]
        if not isinstance(quota, dict):
            return []
        buckets = []
        for name, status in quota.items():
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,119}", name):
                continue
            if not isinstance(status, dict) or status.get("disabled") is True:
                continue
            remaining = fraction(status.get("remaining_fraction"))
            if remaining is None:
                continue
            group, separator, suffix = name.rpartition("-")
            window = suffix if separator and suffix in {"weekly", "5h"} else "unknown"
            buckets.append({"id": f"cli:{name}", "group": f"CLI quota · {group if window != 'unknown' else name}",
                            "name": name, "window": window, "remaining": remaining,
                            "resetAt": reset_time(status.get("reset_time"))})
        return buckets
    quotas = payload.get("quotas")
    if isinstance(quotas, dict) and quotas.get("available") is False:
        return []
    models = quotas.get("models") if isinstance(quotas, dict) else None
    if not isinstance(models, dict):
        return []
    buckets = []
    for name, model in models.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,119}", name):
            continue
        remaining = model.get("remaining") if isinstance(model, dict) else None
        if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
            continue
        if not 0 <= remaining <= 100 or not math.isfinite(remaining):
            continue
        buckets.append({
            "id": f"cli:{name}", "group": "CLI model quota (window not provided)",
            "name": name, "window": "unknown", "remaining": remaining / 100,
            "resetAt": None,
        })
    return buckets


def cache_path(source="cli"):
    configured = Path(os.environ.get("XDG_CACHE_HOME", ""))
    root = configured if configured.is_absolute() else Path.home() / ".cache"
    return root / "antigravity-usage-indicator" / f"{source}-quota.json"


def atomic_json(path, payload):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".quota-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(payload, output, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture(stream):
    path = cache_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.parent.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise CliError("cli-cache")
    try:
        raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Oversized status-line event")
        event = json.loads(raw)
        buckets = normalize(event)
    except (ValueError, UnicodeError, RecursionError):
        buckets = []
    if not buckets:
        path.unlink(missing_ok=True)
        return "AG quota unavailable"
    payload = {"capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if "quota" in event:
        payload["quota"] = {bucket["name"]: {"remaining_fraction": bucket["remaining"],
                                               "reset_time": bucket["resetAt"]} for bucket in buckets}
    else:
        payload["quotas"] = {"models": {bucket["name"]: {"remaining": bucket["remaining"] * 100}
                                         for bucket in buckets}}
    atomic_json(path, payload)
    remaining = min(bucket["remaining"] for bucket in buckets)
    percent = round(remaining * 100)
    label = "<1" if 0 < remaining and percent == 0 else ">99" if remaining < 1 and percent == 100 else str(percent)
    return f"AG {label}% left"


def import_summary(stream):
    path = cache_path("import")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.parent.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise CliError("import-cache")
    try:
        raw = stream.read(MAX_BYTES + 1)
        buckets = normalize_summary(json.loads(raw)) if len(raw) <= MAX_BYTES else []
    except (ValueError, UnicodeError, RecursionError):
        buckets = []
    if not buckets:
        path.unlink(missing_ok=True)
        raise CliError("import-invalid")
    atomic_json(path, {"capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "summary": sanitized_summary(buckets)})
    return {"ok": True, "message": f"Imported {len(buckets)} quota buckets. Refresh the indicator; reimport within ten minutes."}


def read_cache(source="cli"):
    path = cache_path(source)
    cache_error = "import-cache" if source == "import" else "cli-cache"
    stale_error = "import-stale" if source == "import" else "cli-stale"
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as cached:
            metadata = os.fstat(cached.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise CliError(cache_error)
            raw = cached.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise CliError(cache_error)
        payload = json.loads(raw)
        buckets = normalize_summary(payload.get("summary")) if source == "import" and isinstance(payload, dict) else normalize(payload)
        captured = payload.get("capturedAt") if isinstance(payload, dict) else None
        timestamp = datetime.datetime.fromisoformat(captured) if isinstance(captured, str) else None
        if not timestamp or timestamp.tzinfo is None or not buckets:
            raise CliError(cache_error)
        age = (datetime.datetime.now(datetime.timezone.utc) - timestamp).total_seconds()
        if not 0 <= age <= MAX_AGE_SECONDS:
            raise CliError(stale_error)
        return {"ok": True, "source": source, "sourcePid": None, "plan": None,
                "fetchedAt": timestamp.isoformat(), "buckets": buckets}
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise CliError(cache_error) from None


def install(helper_path):
    path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    command = shlex.join([sys.executable, str(Path(helper_path).resolve()), "--statusline"])
    setting = {"type": "command", "command": command}
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink():
            raise CliError("cli-settings")
        if path.exists():
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as existing:
                metadata = os.fstat(existing.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
                    raise CliError("cli-settings")
                raw = existing.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise CliError("cli-settings")
            settings = json.loads(raw)
        else:
            settings = {}
        if not isinstance(settings, dict):
            raise CliError("cli-settings")
        previous = settings.get("statusLine")
        if previous is not None and previous != setting:
            raise CliError("cli-settings")
        settings["statusLine"] = setting
        atomic_json(path, settings)
    except (OSError, ValueError, UnicodeError):
        raise CliError("cli-settings") from None
    return {"ok": True, "message": "CLI connected. Restart Antigravity CLI and run a prompt, then refresh the indicator."}
