import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {bucketLabel, groupBuckets, panelLabel, percentLabel, resetDetails, resetLabel, sourceLabel, windowLabel} from '../usageView.js';

const buckets = [
    {id: 'short', group: 'Premium', name: 'Session', window: '5h', remaining: 0.8},
    {id: 'weekly', group: 'Premium', name: 'Weekly', window: 'weekly', remaining: 0},
    {id: 'other-weekly', group: 'Standard', name: 'Weekly', window: 'weekly', remaining: 0.625},
    {id: 'other-short', group: 'Standard', name: 'Session', window: '5h', remaining: 0.98493},
    {id: 'weekly-only', group: 'Separate model', name: 'Weekly', window: 'weekly', remaining: 1},
];
assert.deepEqual(groupBuckets(buckets).map(group => group.name), ['Premium', 'Standard', 'Separate model']);
assert.deepEqual(groupBuckets(buckets)[1].buckets, [buckets[2], buckets[3]]);
assert.equal(panelLabel(buckets), 'AG Premium · 5h 80.00% left | Standard · 5h 98.49% left | Separate model · 5h unavailable');
assert.equal(panelLabel(buckets, 'weekly'), 'AG Premium · Weekly 0.00% left');
assert.equal(panelLabel(buckets, 'weekly', 'all', 'used'), 'AG Premium · Weekly 100.00% used');
assert.equal(panelLabel(buckets, 'missing'), 'AG Selected quota unavailable');
assert.equal(panelLabel([]), 'AG —');
assert.equal(panelLabel([], 'missing'), 'AG Selected quota unavailable');
assert.equal(panelLabel(buckets, '', 'all'), 'AG Premium · 5h 80.00% left | Premium · Weekly 0.00% left | Standard · Weekly 62.50% left | Standard · 5h 98.49% left | Separate model · Weekly 100.00% left');
assert.equal(panelLabel([buckets[2], buckets[4]]), 'AG Standard · 5h unavailable | Separate model · 5h unavailable');
assert.equal(panelLabel(buckets.slice(0, 2), '', '5h', 'used'), 'AG Premium · 5h 20.00% used');
assert.equal(bucketLabel(buckets[0]), 'Premium · 5h');
assert.equal(windowLabel({name: 'Daily limit', window: 'daily'}), 'daily');
assert.equal(windowLabel({name: 'Model quota', window: 'unknown'}), 'Model quota');
assert.equal(windowLabel({name: 'Model quota'}), 'Model quota');
assert.equal(percentLabel(0), '0.00% left');
assert.equal(percentLabel(1, 'used'), '0.00% used');
assert.equal(percentLabel(0.425), '42.50% left');
assert.equal(percentLabel(0.001), '0.10% left');
assert.equal(percentLabel(0.999), '99.90% left');
assert.equal(percentLabel(0.001, 'used'), '99.90% used');
assert.equal(percentLabel(0.000001), '<0.01% left');
assert.equal(percentLabel(0.999999), '>99.99% left');
const now = Date.parse('2026-11-22T00:00:00Z');
assert.equal(resetLabel(null, now), 'Reset time unavailable');
assert.equal(resetLabel('bad', now), 'Reset time unavailable');
assert.equal(resetLabel('2026-11-21T00:00:00Z', now), 'Reset due — refresh to confirm');
assert.equal(resetLabel('2026-11-22T00:00:01Z', now), 'Resets in 1m');
assert.equal(resetLabel('2026-11-22T05:20:00Z', now), 'Resets in 5h 20m');
assert.equal(resetLabel('2026-11-25T03:00:00Z', now), 'Resets in 3d 3h');
assert.equal(resetDetails(null, now), 'Reset time unavailable');
assert.equal(resetDetails('bad', now), 'Reset time unavailable');
assert.equal(resetDetails('2026-11-22T05:20:00Z', now),
    `Resets in 5h 20m · ${new Date('2026-11-22T05:20:00Z').toLocaleString()}`);
const metadata = JSON.parse(readFileSync(new URL('../metadata.json', import.meta.url)));
assert.equal(metadata.uuid, 'antigravity-usage-indicator@stone.dev');
assert.equal(metadata['settings-schema'], 'org.gnome.shell.extensions.antigravity-usage-indicator');
assert.deepEqual(metadata['shell-version'], ['45', '46', '47', '48', '49', '50', '51']);
assert.match(sourceLabel({source: 'cli', sourcePid: null, fetchedAt: '2026-11-23T00:00:00Z'}), /^CLI \(latest session\) · Updated /);
assert.match(sourceLabel({source: 'summary', sourcePid: 123, fetchedAt: '2026-11-23T00:00:00Z'}), /^PID 123 · Updated /);
assert.match(sourceLabel({source: 'import', sourcePid: null, fetchedAt: '2026-11-23T00:00:00Z'}), /^Imported response \(manual capture\) · Updated /);
console.log('View and metadata tests passed');
