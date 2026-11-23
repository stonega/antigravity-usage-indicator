"""Decode object and positional Antigravity quota summaries without credentials."""

import datetime
import math
import re


def text(value, fallback=""):
    if not isinstance(value, str):
        return fallback
    return " ".join(value.split())[:160] or fallback


def fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 <= value <= 1 or not math.isfinite(value):
        return None
    return float(value)


def reset_time(value):
    try:
        if isinstance(value, list) and len(value) == 1:
            seconds = value[0]
            if not isinstance(seconds, str) or not re.fullmatch(r"[0-9]{1,12}", seconds):
                return None
            return datetime.datetime.fromtimestamp(int(seconds), datetime.timezone.utc).isoformat()
        if not isinstance(value, str):
            return None
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(datetime.timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def array_groups(payload):
    pending = [(payload, 0)]
    visited = 0
    while pending and visited < 10000:
        node, depth = pending.pop()
        visited += 1
        if not isinstance(node, list) or depth > 12:
            continue
        if len(node) >= 2 and isinstance(node[0], list) and text(node[1]):
            buckets = []
            for bucket in node[0]:
                if (not isinstance(bucket, list) or len(bucket) < 4 or
                        not all(isinstance(value, str) and value.strip() for value in bucket[:3])):
                    continue
                buckets.append({"bucketId": bucket[0], "displayName": bucket[1],
                                "window": bucket[2], "remainingFraction": bucket[3],
                                "resetTime": bucket[5] if len(bucket) > 5 else None})
            if buckets:
                yield {"displayName": node[1], "buckets": buckets}
                continue
        pending.extend((child, depth + 1) for child in reversed(node) if isinstance(child, list))


def normalize_summary(payload):
    summary = payload.get("response", payload) if isinstance(payload, dict) else payload
    groups = list(array_groups(summary)) if isinstance(summary, list) else (
        summary.get("groups", []) if isinstance(summary, dict) else [])
    if not isinstance(groups, list):
        return []
    buckets = []
    for group_index, group in enumerate(groups):
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
            buckets.append({
                "id": f"summary:{group_index}:{bucket_id}", "group": group_name,
                "name": text(bucket.get("displayName"), window if window != "unknown" else "Quota"),
                "window": window, "remaining": remaining,
                "resetAt": reset_time(bucket.get("resetTime")),
            })
    return buckets


def sanitized_summary(buckets):
    groups = {}
    for bucket in buckets:
        _, group_id, bucket_id = bucket["id"].split(":", 2)
        group = groups.setdefault(group_id, {"displayName": bucket["group"], "buckets": []})
        group["buckets"].append({"bucketId": bucket_id, "displayName": bucket["name"],
                                 "window": bucket["window"], "remainingFraction": bucket["remaining"],
                                 "resetTime": bucket["resetAt"]})
    return {"groups": list(groups.values())}
