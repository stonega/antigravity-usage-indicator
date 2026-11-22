import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export class QuotaClient {
    constructor(helperPath, timeoutSeconds = 25) {
        this._helperPath = helperPath;
        this._timeoutSeconds = timeoutSeconds;
        this._pending = null;
    }

    fetch(pid = 0) {
        if (this._pending)
            return this._pending.promise;
        let process;
        try {
            process = Gio.Subprocess.new(
                ['python3', this._helperPath, '--pid', String(pid)],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch {
            return Promise.reject(new Error('Cannot start the quota reader. Install Python 3 and check extension files.'));
        }
        const pending = {process, timeout: 0, cancelled: false, timedOut: false};
        this._pending = pending;
        pending.promise = new Promise((resolve, reject) => {
            pending.timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, this._timeoutSeconds, () => {
                pending.timeout = 0;
                pending.timedOut = true;
                process.force_exit();
                return GLib.SOURCE_REMOVE;
            });
            process.communicate_utf8_async(null, null, (source, result) => {
                if (pending.timeout)
                    GLib.source_remove(pending.timeout);
                if (this._pending === pending)
                    this._pending = null;
                try {
                    const [, stdout] = source.communicate_utf8_finish(result);
                    if (pending.cancelled)
                        throw new Error('Refresh cancelled');
                    if (pending.timedOut)
                        throw new Error('The local quota reader timed out. Try refreshing again.');
                    if (!source.get_successful())
                        throw new Error('The local quota reader failed. Check Python 3 and extension files.');
                    let response;
                    try {
                        response = JSON.parse(stdout);
                    } catch {
                        throw new Error('The local quota reader returned invalid data.');
                    }
                    if (response?.ok !== true)
                        throw new Error(response?.error?.message || 'Local quota is unavailable.');
                    if (!Array.isArray(response.buckets) || !response.buckets.length ||
                        !response.buckets.every(bucket => typeof bucket.id === 'string' &&
                            typeof bucket.name === 'string' && typeof bucket.group === 'string' &&
                            Number.isFinite(bucket.remaining) && bucket.remaining >= 0 && bucket.remaining <= 1))
                        throw new Error('The local quota reader returned invalid quota values.');
                    resolve(response);
                } catch (error) {
                    reject(error);
                }
            });
        });
        return pending.promise;
    }

    cancel() {
        const pending = this._pending;
        if (!pending)
            return;
        pending.cancelled = true;
        if (pending.timeout) {
            GLib.source_remove(pending.timeout);
            pending.timeout = 0;
        }
        this._pending = null;
        pending.process.force_exit();
    }
}
