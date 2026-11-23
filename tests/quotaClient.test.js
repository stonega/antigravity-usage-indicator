import GLib from 'gi://GLib';
import {QuotaClient} from '../quotaClient.js';
import {percentLabel, selectBucket, sourceLabel} from '../usageView.js';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

async function rejects(promise, expected) {
    let message = '';
    try {
        await promise;
    } catch (error) {
        message = error.message;
    }
    assert(message.includes(expected), `Expected ${expected}, got ${message}`);
}

async function run() {
    const path = GLib.build_filenamev([GLib.get_current_dir(), 'tests', 'fixtures', 'reader.py']);
    const client = new QuotaClient(path, 1);
    const first = client.fetch();
    assert(first === client.fetch(), 'Concurrent requests must coalesce');
    const response = await first;
    assert(response.buckets[0].remaining === 0, 'Zero is valid quota');
    assert(percentLabel(selectBucket(response.buckets, '').remaining) === '0% left', 'GJS view module works');
    const cliResponse = await client.fetch(6);
    assert(cliResponse.source === 'cli' && cliResponse.sourcePid === null, 'CLI needs no local server PID');
    assert(sourceLabel(cliResponse).startsWith('CLI (latest session)'), 'CLI source must be identified');
    await rejects(client.fetch(1), 'Sign in');
    await rejects(client.fetch(2), 'invalid data');
    await rejects(client.fetch(3), 'reader failed');
    await rejects(client.fetch(5), 'invalid quota values');
    await rejects(client.fetch(4), 'timed out');
    const pending = client.fetch(4);
    client.cancel();
    const replacement = client.fetch();
    await rejects(pending, 'cancelled');
    assert((await replacement).ok, 'Cancellation must allow immediate replacement');
    assert((await client.fetch()).ok, 'Client must recover from errors');
    print('GJS subprocess, cancellation, timeout and recovery tests passed');
}

const loop = new GLib.MainLoop(null, false);
let failure = null;
run().catch(error => {
    failure = error;
}).finally(() => loop.quit());
loop.run();
if (failure)
    throw failure;
