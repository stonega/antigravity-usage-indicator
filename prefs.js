import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
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
        const pid = new Adw.ActionRow({title: 'Server process ID', subtitle: '0 = automatic; set a PID to choose between running accounts'});
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
            'Keep Antigravity open and signed in with a workspace. The indicator reads quota from its local server. ' +
            'No Google OAuth credentials are imported, stored, or refreshed. Select the panel quota in the indicator menu. ' +
            'Only windows returned by the server are shown; unavailable limits are never assumed to be 100%.'});
        page.add(source);
        window.add(page);
        window.connect('close-request', () => {
            settings.disconnect(modeChanged);
            return false;
        });
    }
}
