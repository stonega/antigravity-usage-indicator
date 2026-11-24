import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

function assertEqual(actual, expected) {
    if (actual !== expected)
        throw new Error(`Expected ${expected}, got ${actual}`);
}

const schemaId = 'org.gnome.shell.extensions.antigravity-usage-indicator';
const settings = new Gio.Settings({schema_id: schemaId});
assertEqual(settings.get_string('panel-window'), '5h');
assertEqual(settings.get_string('panel-bucket-id'), '');
assertEqual(settings.get_string('display-mode'), 'left');
settings.set_string('panel-bucket-id', 'summary:example:model-5h');
settings.set_string('panel-window', 'all');
settings.set_string('display-mode', 'used');
Gio.Settings.sync();
const reopened = new Gio.Settings({schema_id: schemaId});
assertEqual(reopened.get_string('panel-bucket-id'), 'summary:example:model-5h');
assertEqual(reopened.get_string('panel-window'), 'all');
assertEqual(reopened.get_string('display-mode'), 'used');
const key = reopened.settings_schema.get_key('panel-window');
assertEqual(key.range_check(new GLib.Variant('s', '5h')), true);
assertEqual(key.range_check(new GLib.Variant('s', 'all')), true);
assertEqual(key.range_check(new GLib.Variant('s', 'invalid')), false);
reopened.reset('panel-bucket-id');
assertEqual(reopened.get_string('panel-bucket-id'), '');
assertEqual(reopened.get_string('panel-window'), 'all');
print('Real GSettings defaults, saved selections and window constraints passed (memory backend)');
