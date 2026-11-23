import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class AntigravityUsagePreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const page = new Adw.PreferencesPage({title: 'Antigravity', icon_name: 'preferences-system-symbolic'});
        const group = new Adw.PreferencesGroup({title: 'Quota display'});
        const interval = new Adw.ActionRow({title: 'Refresh interval', subtitle: 'Seconds between updates (60–3600)'});
        const intervalControl = new Gtk.SpinButton({
            adjustment: new Gtk.Adjustment({lower: 60, upper: 3600, step_increment: 60}),
            valign: Gtk.Align.CENTER,
            numeric: true,
        });
        settings.bind('update-interval-seconds', intervalControl, 'value', Gio.SettingsBindFlags.DEFAULT);
        interval.add_suffix(intervalControl);
        interval.activatable_widget = intervalControl;
        group.add(interval);
        const mode = new Adw.ComboRow({title: 'Display value', model: Gtk.StringList.new(['Remaining', 'Used'])});
        mode.selected = settings.get_string('display-mode') === 'used' ? 1 : 0;
        mode.connect('notify::selected', () => settings.set_string('display-mode', mode.selected === 1 ? 'used' : 'left'));
        const modeChanged = settings.connect('changed::display-mode', () => {
            mode.selected = settings.get_string('display-mode') === 'used' ? 1 : 0;
        });
        group.add(mode);
        const pid = new Adw.ActionRow({title: 'Server process ID', subtitle: '0 = CLI, imported response, then desktop; a PID pins a desktop server'});
        const pidControl = new Gtk.SpinButton({
            adjustment: new Gtk.Adjustment({lower: 0, upper: 2147483647, step_increment: 1}),
            valign: Gtk.Align.CENTER,
            numeric: true,
        });
        settings.bind('server-pid', pidControl, 'value', Gio.SettingsBindFlags.DEFAULT);
        pid.add_suffix(pidControl);
        pid.activatable_widget = pidControl;
        group.add(pid);
        page.add(group);
        const source = new Adw.PreferencesGroup({title: 'Data source', description:
            'CLI: connect the status-line bridge below, restart the CLI and run a prompt. Desktop: keep a signed-in workspace open. ' +
            'No Google OAuth credentials are imported, stored, or refreshed. Select the panel quota in the indicator menu. ' +
            'Only windows returned by the quota source are shown; unavailable limits are never assumed to be 100%.'});
        const cli = new Adw.ActionRow({title: 'Antigravity CLI', subtitle:
            'Adds a quota-only statusLine command to ~/.gemini/antigravity-cli/settings.json. Existing custom status lines are not replaced.'});
        const connect = new Gtk.Button({label: 'Connect CLI', valign: Gtk.Align.CENTER});
        cli.add_suffix(connect);
        cli.activatable_widget = connect;
        connect.connect('clicked', () => {
            connect.sensitive = false;
            try {
                const process = Gio.Subprocess.new(['python3',
                    GLib.build_filenamev([this.path, 'helpers', 'antigravity_usage.py']), '--install-cli-statusline'],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
                process.communicate_utf8_async(null, null, (reader, result) => {
                    try {
                        const [, output] = reader.communicate_utf8_finish(result);
                        const response = JSON.parse(output);
                        cli.subtitle = response.ok ? response.message : response.error.message;
                    } catch {
                        cli.subtitle = 'Cannot connect the CLI. Check Python 3 and see README for manual setup.';
                    }
                    connect.sensitive = true;
                });
            } catch {
                cli.subtitle = 'Cannot start setup. Install Python 3 and check extension files.';
                connect.sensitive = true;
            }
        });
        source.add(cli);
        source.add(new Adw.ActionRow({title: 'Alternative: import quota response', subtitle:
            'No CLI quota or desktop server? Pipe quota response JSON to helpers/antigravity_usage.py --import-quota. ' +
            'Supports grouped array responses, weekly/5h windows and reset timestamps. See README; captures expire after ten minutes.'}));
        page.add(source);
        window.add(page);
        window.connect('close-request', () => {
            settings.disconnect(modeChanged);
            return false;
        });
    }
}
