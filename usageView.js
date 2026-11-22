export function selectBucket(buckets, selectedId) {
    return buckets.find(bucket => bucket.id === selectedId) ??
        buckets.reduce((lowest, bucket) => !lowest || bucket.remaining < lowest.remaining ? bucket : lowest, null);
}

export function percentLabel(remaining, mode = 'left') {
    const value = mode === 'used' ? 1 - remaining : remaining;
    const percent = Math.round(value * 100);
    const formatted = value > 0 && percent === 0 ? '<1' : value < 1 && percent === 100 ? '>99' : `${percent}`;
    return `${formatted}% ${mode === 'used' ? 'used' : 'left'}`;
}

export function resetLabel(resetAt, now = Date.now()) {
    if (!resetAt || !Number.isFinite(Date.parse(resetAt)))
        return 'Reset time unavailable';
    const difference = Date.parse(resetAt) - now;
    if (difference <= 0)
        return 'Reset due — refresh to confirm';
    const minutes = Math.ceil(difference / 60000);
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor(minutes % 1440 / 60);
    const remainder = minutes % 60;
    const duration = days ? `${days}d ${hours}h` : hours ? `${hours}h ${remainder}m` : `${remainder}m`;
    return `Resets in ${duration}`;
}

export function bucketLabel(bucket) {
    return `${bucket.group} · ${bucket.name}`;
}
