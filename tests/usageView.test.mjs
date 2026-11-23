import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {bucketLabel, percentLabel, resetLabel, selectBucket, sourceLabel} from '../usageView.js';

const buckets = [
    {id: 'short', group: 'Premium', name: 'Session', remaining: 0.8},
    {id: 'weekly', group: 'Premium', name: 'Weekly', remaining: 0},
];
assert.equal(selectBucket(buckets, ''), buckets[1]);
assert.equal(selectBucket(buckets, 'missing'), buckets[1]);
assert.equal(selectBucket(buckets, 'short'), buckets[0]);
assert.equal(selectBucket([], ''), null);
assert.equal(bucketLabel(buckets[0]), 'Premium · Session');
assert.equal(percentLabel(0), '0% left');
assert.equal(percentLabel(1, 'used'), '0% used');
assert.equal(percentLabel(0.425), '43% left');
assert.equal(percentLabel(0.001), '<1% left');
assert.equal(percentLabel(0.999), '>99% left');
assert.equal(percentLabel(0.001, 'used'), '>99% used');
const now = Date.parse('2026-11-22T00:00:00Z');
assert.equal(resetLabel(null, now), 'Reset time unavailable');
assert.equal(resetLabel('bad', now), 'Reset time unavailable');
assert.equal(resetLabel('2026-11-21T00:00:00Z', now), 'Reset due — refresh to confirm');
assert.equal(resetLabel('2026-11-22T00:00:01Z', now), 'Resets in 1m');
assert.equal(resetLabel('2026-11-22T05:20:00Z', now), 'Resets in 5h 20m');
assert.equal(resetLabel('2026-11-25T03:00:00Z', now), 'Resets in 3d 3h');
const metadata = JSON.parse(readFileSync(new URL('../metadata.json', import.meta.url)));
assert.equal(metadata.uuid, 'antigravity-usage-indicator@stone.dev');
assert.equal(metadata['settings-schema'], 'org.gnome.shell.extensions.antigravity-usage-indicator');
assert.deepEqual(metadata['shell-version'], ['45', '46', '47', '48', '49', '50', '51']);
assert.match(sourceLabel({source: 'cli', sourcePid: null, fetchedAt: '2026-11-23T00:00:00Z'}), /^CLI \(latest session\) · Updated /);
assert.match(sourceLabel({source: 'summary', sourcePid: 123, fetchedAt: '2026-11-23T00:00:00Z'}), /^PID 123 · Updated /);
console.log('View and metadata tests passed');
