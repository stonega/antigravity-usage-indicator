export function groupBuckets(buckets) {
    const groups = new Map();
    for (const bucket of buckets) {
        if (!groups.has(bucket.group))
            groups.set(bucket.group, []);
        groups.get(bucket.group).push(bucket);
    }
    return [...groups].map(([name, entries]) => ({name, buckets: entries}));
}

export function windowLabel(bucket) {
    if (bucket.window === '5h')
        return '5h';
    if (bucket.window === 'weekly')
        return 'Weekly';
    return bucket.window && bucket.window !== 'unknown' ? bucket.window : bucket.name;
}

export function panelLabel(buckets, selectedId = '', window = '5h', mode = 'left') {
    if (selectedId) {
        const selected = buckets.find(bucket => bucket.id === selectedId);
        return selected ? `AG ${bucketLabel(selected)} ${percentLabel(selected.remaining, mode)}` :
            'AG Selected quota unavailable';
    }
    const groups = groupBuckets(buckets);
    if (!groups.length)
        return 'AG —';
    const labels = groups.flatMap(group => {
        const selected = group.buckets.filter(bucket => window === 'all' || bucket.window === window);
        return selected.length ? selected.map(bucket => `${bucketLabel(bucket)} ${percentLabel(bucket.remaining, mode)}`) :
            [`${group.name} · ${window} unavailable`];
    });
    return `AG ${labels.join(' | ')}`;
}

export function percentLabel(remaining, mode = 'left') {
    const value = mode === 'used' ? 1 - remaining : remaining;
    const percent = (value * 100).toFixed(2);
    const formatted = value > 0 && percent === '0.00' ? '<0.01' : value < 1 && percent === '100.00' ? '>99.99' : percent;
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
    return `${bucket.group} · ${windowLabel(bucket)}`;
}

export function resetDetails(resetAt, now = Date.now()) {
    const relative = resetLabel(resetAt, now);
    return resetAt && Number.isFinite(Date.parse(resetAt)) ?
        `${relative} · ${new Date(resetAt).toLocaleString()}` : relative;
}

export function sourceLabel(snapshot) {
    const source = snapshot.source === 'cli' ? 'CLI (latest session)' :
        snapshot.source === 'import' ? 'Imported response (manual capture)' : `PID ${snapshot.sourcePid}`;
    return `${source} · Updated ${new Date(snapshot.fetchedAt).toLocaleString()}`;
}
