import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {QuotaClient} from './quotaClient.js';
import {bucketLabel, groupBuckets, panelLabel, percentLabel, resetDetails, sourceLabel, windowLabel} from './usageView.js';

const UsageIndicator = GObject.registerClass(
class UsageIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, 'Antigravity Usage');
        this._extension = extension;
        this._settings = extension.getSettings();
        this._client = new QuotaClient(GLib.build_filenamev([extension.path, 'helpers', 'antigravity_usage.py']));
        this._snapshot = null;
        this._error = null;
        this._busy = false;
        this._disposed = false;
        this._generation = 0;
        this._timer = 0;
        this._label = new St.Label({text: 'AG …', y_align: Clutter.ActorAlign.CENTER});
        this.add_child(this._label);
        this._status = new PopupMenu.PopupMenuItem('Reading local Antigravity quota…', {reactive: false});
        this.menu.addMenuItem(this._status);
        this._usageSection = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(this._usageSection);
        this._updated = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._updated.label.add_style_class_name('ag-updated');
        this._updated.label.clutter_text.line_wrap = true;
        this._updated.label.clutter_text.ellipsize = 0;
        this.menu.addMenuItem(this._updated);
        this._selector = new PopupMenu.PopupSubMenuMenuItem('Panel quota');
        this.menu.addMenuItem(this._selector);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._refreshItem = this.menu.addAction('Refresh now', () => void this.refresh());
        this.menu.addAction('Settings', () => extension.openPreferences());
        this._settingsChanged = this._settings.connect('changed', (_settings, key) => {
            if (key === 'server-pid') {
                this._generation++;
                this._client.cancel();
                this._busy = false;
                this._snapshot = null;
                this._error = null;
                void this.refresh();
            } else if (key === 'update-interval-seconds') {
                this._schedule();
            } else {
                this._render();
            }
        });
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open)
                this._render();
        });
        this._schedule();
        void this.refresh();
    }

    _schedule() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT,
            this._settings.get_int('update-interval-seconds'), () => {
                void this.refresh();
                return GLib.SOURCE_CONTINUE;
            });
    }

    async refresh() {
        if (this._busy || this._disposed)
            return;
        this._busy = true;
        const generation = this._generation;
        this._render();
        try {
            const snapshot = await this._client.fetch(this._settings.get_int('server-pid'));
            if (this._disposed || generation !== this._generation)
                return;
            this._snapshot = snapshot;
            this._error = null;
        } catch (error) {
            if (this._disposed || generation !== this._generation)
                return;
            this._error = error.message;
        } finally {
            if (!this._disposed && generation === this._generation) {
                this._busy = false;
                this._render();
            }
        }
    }

    _render() {
        const snapshot = this._snapshot;
        const mode = this._settings.get_string('display-mode');
        const selectedId = this._settings.get_string('panel-bucket-id');
        const panelWindow = this._settings.get_string('panel-window');
        const stale = Boolean(this._error && snapshot);
        this._label.text = snapshot ? `${panelLabel(snapshot.buckets, selectedId, panelWindow, mode)}${stale ? ' ⚠' : ''}` :
            this._busy ? 'AG …' : 'AG —';
        this.accessible_name = snapshot ? `Antigravity quota: ${this._label.text}${stale ? ' (stale)' : ''}` : 'Antigravity quota unavailable';
        this._status.label.text = this._error ? `${stale ? 'Stale — ' : ''}${this._error}` : snapshot ?
            snapshot.plan || 'Antigravity subscription quota' :
            'Reading local Antigravity quota…';
        this._updated.visible = Boolean(snapshot);
        if (snapshot)
            this._updated.label.text = sourceLabel(snapshot);
        this._status.label.clutter_text.line_wrap = true;
        this._status.label.clutter_text.ellipsize = 0;
        this._status.add_style_class_name('ag-status');
        this._refreshItem.setSensitive(!this._busy);
        this._refreshItem.label.text = this._busy ? 'Refreshing…' : 'Refresh now';
        this._usageSection.removeAll();
        this._selector.menu.removeAll();
        this._selector.visible = Boolean(snapshot);
        if (!snapshot)
            return;
        for (const [window, label] of [['5h', 'All model groups · 5h'], ['all', 'All model groups · all windows']]) {
            const automatic = new PopupMenu.PopupMenuItem(label);
            automatic.setOrnament(!selectedId && panelWindow === window ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
            automatic.connect('activate', () => {
                this._settings.set_string('panel-window', window);
                this._settings.set_string('panel-bucket-id', '');
            });
            this._selector.menu.addMenuItem(automatic);
        }
        if (selectedId && !snapshot.buckets.some(bucket => bucket.id === selectedId))
            this._selector.menu.addMenuItem(new PopupMenu.PopupMenuItem('Selected quota unavailable — choose another', {reactive: false}));
        for (const group of groupBuckets(snapshot.buckets)) {
            const heading = new PopupMenu.PopupMenuItem(group.name, {reactive: false});
            heading.label.add_style_class_name('ag-group');
            heading.label.clutter_text.line_wrap = true;
            heading.label.clutter_text.ellipsize = 0;
            this._usageSection.addMenuItem(heading);
            for (const bucket of group.buckets) {
                const row = new PopupMenu.PopupBaseMenuItem({reactive: false});
                const content = new St.BoxLayout({vertical: true, x_expand: true, style_class: 'ag-quota'});
                const title = new St.BoxLayout({x_expand: true, style_class: 'ag-quota-title'});
                title.add_child(new St.Label({text: windowLabel(bucket), x_expand: true}));
                title.add_child(new St.Label({text: percentLabel(bucket.remaining, mode)}));
                content.add_child(title);
                const track = new St.Bin({x_expand: true, style_class: 'ag-track'});
                const fill = new St.Widget({
                    x_align: Clutter.ActorAlign.START,
                    style_class: bucket.remaining <= 0.1 ? 'ag-fill ag-low' : 'ag-fill',
                });
                track.set_child(fill);
                const value = mode === 'used' ? 1 - bucket.remaining : bucket.remaining;
                track.connect('notify::width', () => fill.set_width(track.width * value));
                content.add_child(track);
                const reset = new St.Label({text: resetDetails(bucket.resetAt), style_class: 'ag-reset dim-label'});
                reset.clutter_text.line_wrap = true;
                reset.clutter_text.ellipsize = 0;
                content.add_child(reset);
                row.add_child(content);
                this._usageSection.addMenuItem(row);
                const choice = new PopupMenu.PopupMenuItem(bucketLabel(bucket));
                choice.setOrnament(bucket.id === selectedId ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
                choice.connect('activate', () => this._settings.set_string('panel-bucket-id', bucket.id));
                this._selector.menu.addMenuItem(choice);
            }
            if (!group.buckets.some(bucket => bucket.window === '5h'))
                this._usageSection.addMenuItem(new PopupMenu.PopupMenuItem('5h quota unavailable from this source', {reactive: false}));
        }
        if (snapshot.source === 'cli')
            this._usageSection.addMenuItem(new PopupMenu.PopupMenuItem('CLI capture; run a prompt to update quota.', {reactive: false}));
        if (snapshot.source === 'import')
            this._usageSection.addMenuItem(new PopupMenu.PopupMenuItem('Manual capture; import a fresh response to update quota.', {reactive: false}));
        if (snapshot.source === 'legacy')
            this._usageSection.addMenuItem(new PopupMenu.PopupMenuItem('Legacy model quota; weekly limits may not be available.', {reactive: false}));
    }

    destroy() {
        this._disposed = true;
        this._generation++;
        this._client.cancel();
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        this._settings.disconnect(this._settingsChanged);
        super.destroy();
    }
});

export default class AntigravityUsageExtension extends Extension {
    enable() {
        this._indicator = new UsageIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
