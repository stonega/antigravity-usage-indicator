import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as usageView from '../usageView.js';

class Actor {
    constructor(properties = {}) {
        Object.assign(this, {children: [], signals: new Map(), clutter_text: {}}, properties);
    }

    add_child(child) { this.children.push(child); }
    set_child(child) { this.children = [child]; }
    set_width(width) { this.width = width; }
    add_style_class_name(name) { this.style_class = `${this.style_class ?? ''} ${name}`.trim(); }
    connect(signal, callback) { this.signals.set(signal, callback); return signal; }
    emit(signal, ...args) { this.signals.get(signal)?.(this, ...args); }
}

class Menu extends Actor {
    addMenuItem(item) { this.add_child(item); }
    removeAll() { this.children = []; }
    addAction(text, callback) {
        const item = new MenuItem(text);
        item.connect('activate', callback);
        this.addMenuItem(item);
        return item;
    }
}

class MenuItem extends Actor {
    constructor(text, properties) {
        super(properties);
        this.label = new Actor({text});
        this.add_child(this.label);
    }

    setOrnament(ornament) { this.ornament = ornament; }
    setSensitive(sensitive) { this.sensitive = sensitive; }
}

class SubMenuItem extends MenuItem {
    constructor(text) {
        super(text);
        this.menu = new Menu();
    }
}

class PanelButton extends Actor {
    constructor(...args) {
        super();
        this._init(...args);
    }

    _init(menuAlignment) { this._menuAlignment = menuAlignment; this.menu = new Menu(); }
    destroy() { this.destroyed = true; }
}

class Settings {
    constructor() {
        this.values = new Map([
            ['panel-bucket-id', ''], ['panel-window', '5h'], ['display-mode', 'left'],
            ['server-pid', 0], ['update-interval-seconds', 300],
        ]);
        this.listeners = new Map();
        this.nextId = 0;
    }

    get_string(key) { return this.values.get(key); }
    get_int(key) { return this.values.get(key); }
    set_int(key, value) { this.set_string(key, value); }
    set_string(key, value) {
        if (this.values.get(key) === value)
            return;
        this.values.set(key, value);
        for (const callback of this.listeners.values())
            callback(this, key);
    }
    connect(_signal, callback) { this.listeners.set(++this.nextId, callback); return this.nextId; }
    disconnect(id) { this.listeners.delete(id); }
}

const snapshot = {
    source: 'summary', sourcePid: 123, plan: 'Example plan', fetchedAt: '2026-11-24T00:00:00Z',
    buckets: [
        {id: 'alpha-weekly', group: 'Alpha', name: 'Weekly limit', window: 'weekly', remaining: 0.125, resetAt: '2099-01-01T00:00:00Z'},
        {id: 'alpha-5h', group: 'Alpha', name: 'Five hour limit', window: '5h', remaining: 0.875, resetAt: null},
        {id: 'beta-weekly', group: 'Beta', name: 'Weekly limit', window: 'weekly', remaining: 0.625, resetAt: null},
        {id: 'beta-5h', group: 'Beta', name: 'Five hour limit', window: '5h', remaining: 0.875, resetAt: null},
        {id: 'gamma-weekly', group: 'Gamma', name: 'Weekly limit', window: 'weekly', remaining: 0, resetAt: null},
    ],
};

class Client {
    async fetch() {
        if (this.error)
            throw new Error(this.error);
        return this.snapshot ?? snapshot;
    }
    cancel() { this.cancelled = true; }
}

const settings = new Settings();
let openedPreferences = false;
let indicator;
const timers = new Set();
const context = {
    ...usageView,
    Clutter: {ActorAlign: {CENTER: 1, START: 2}},
    GLib: {
        build_filenamev: parts => parts.join('/'),
        timeout_add_seconds: () => { const id = timers.size + 1; timers.add(id); return id; },
        source_remove: id => timers.delete(id),
    },
    GObject: {registerClass: definition => definition},
    St: {Label: Actor, BoxLayout: Actor, Bin: Actor, Widget: Actor},
    Extension: class {
        constructor() { this.path = '/example'; this.uuid = 'example'; }
        getSettings() { return settings; }
        openPreferences() { openedPreferences = true; }
    },
    Main: {panel: {addToStatusArea: (_uuid, actor) => { indicator = actor; }}},
    PanelMenu: {Button: PanelButton},
    PopupMenu: {
        PopupMenuItem: MenuItem, PopupBaseMenuItem: Actor, PopupMenuSection: Menu,
        PopupSubMenuMenuItem: SubMenuItem, PopupSeparatorMenuItem: Actor,
        Ornament: {DOT: 'dot', NONE: 'none'},
    },
    QuotaClient: Client,
};
const source = readFileSync(new URL('../extension.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '')
    .replace('export default class ', 'class ');
const ExtensionClass = vm.runInNewContext(`${source}\nAntigravityUsageExtension;`, context);
const extension = new ExtensionClass();
extension.enable();
assert.equal(indicator._menuAlignment, 0.5);
assert.equal(indicator._label.text, 'AG …');
assert.equal(indicator._refreshItem.sensitive, false);
await new Promise(resolve => setImmediate(resolve));

function texts(actor) {
    return [actor.text ?? '', ...(actor.children ?? []).flatMap(texts)].filter(Boolean);
}

function choose(label) {
    const choice = indicator._selector.menu.children.find(item => item.label?.text === label);
    assert.ok(choice, `Missing choice: ${label}`);
    choice.emit('activate');
}

assert.equal(indicator._label.text, 'AG Alpha · 5h 87.50% left | Beta · 5h 87.50% left | Gamma · 5h unavailable');
assert.match(indicator.accessible_name, /Alpha · 5h/);
assert.equal(indicator._selector.menu.children[0].ornament, 'dot');
const rows = () => indicator._usageSection.children.filter(item => item.children[0]?.style_class === 'ag-quota');
assert.equal(rows().length, 5);
assert.deepEqual(texts(indicator._usageSection).filter(text => ['Alpha', 'Beta', 'Gamma'].includes(text)), ['Alpha', 'Beta', 'Gamma']);
for (const percent of ['12.50% left', '87.50% left', '62.50% left', '0.00% left'])
    assert.ok(texts(indicator._usageSection).includes(percent), `Missing popup value: ${percent}`);
assert.equal(texts(indicator._usageSection).filter(text => text === '87.50% left').length, 2);
assert.ok(texts(indicator._usageSection).includes('5h quota unavailable from this source'));
assert.ok(texts(indicator._usageSection).includes('Reset time unavailable'));
assert.ok(texts(indicator._usageSection).some(text => text.startsWith('Resets in ') && text.includes('2099')));
assert.match(indicator._updated.label.text, /PID 123 · Updated/);
const track = rows()[0].children[0].children[1];
track.width = 200;
track.emit('notify::width');
assert.equal(track.children[0].width, 25);
assert.equal(rows()[4].children[0].children[1].children[0].style_class, 'ag-fill ag-low');
const emptyTrack = rows()[4].children[0].children[1];
emptyTrack.width = 200;
emptyTrack.emit('notify::width');
assert.equal(emptyTrack.children[0].width, 0);

choose('Beta · Weekly');
assert.equal(settings.get_string('panel-bucket-id'), 'beta-weekly');
assert.equal(indicator._label.text, 'AG Beta · Weekly 62.50% left');
assert.equal(rows().length, 5);
extension.disable();
assert.equal(timers.size, 0);
assert.equal(settings.listeners.size, 0);
extension.enable();
await new Promise(resolve => setImmediate(resolve));
assert.equal(indicator._label.text, 'AG Beta · Weekly 62.50% left');

settings.set_string('display-mode', 'used');
assert.equal(indicator._label.text, 'AG Beta · Weekly 37.50% used');
const usedTrack = rows()[0].children[0].children[1];
usedTrack.width = 200;
usedTrack.emit('notify::width');
assert.equal(usedTrack.children[0].width, 175);
const exhaustedTrack = rows()[4].children[0].children[1];
exhaustedTrack.width = 200;
exhaustedTrack.emit('notify::width');
assert.equal(exhaustedTrack.children[0].width, 200);
settings.set_string('panel-bucket-id', 'removed');
assert.equal(indicator._label.text, 'AG Selected quota unavailable');
assert.ok(texts(indicator._selector.menu).includes('Selected quota unavailable — choose another'));
choose('All model groups · all windows');
assert.equal(settings.get_string('panel-bucket-id'), '');
assert.equal(settings.get_string('panel-window'), 'all');
for (const bucket of snapshot.buckets)
    assert.ok(indicator._label.text.includes(`${usageView.bucketLabel(bucket)} ${usageView.percentLabel(bucket.remaining, 'used')}`));
choose('All model groups · 5h');
assert.equal(settings.get_string('panel-window'), '5h');
assert.equal(indicator._selector.menu.children[0].ornament, 'dot');

indicator._client.error = 'Example source unavailable';
await indicator.refresh();
assert.match(indicator._label.text, /⚠$/);
assert.match(indicator._status.label.text, /^Stale — Example source unavailable/);
assert.equal(rows().length, 5);
indicator._client.error = null;
indicator._refreshItem.emit('activate');
await new Promise(resolve => setImmediate(resolve));
assert.doesNotMatch(indicator._label.text, /⚠/);
indicator.menu.children.find(item => item.label?.text === 'Settings').emit('activate');
assert.ok(openedPreferences);
extension.disable();
assert.equal(timers.size, 0);
assert.equal(settings.listeners.size, 0);
extension.enable();
indicator._client.error = 'Example source unavailable';
settings.set_int('server-pid', 42);
await new Promise(resolve => setImmediate(resolve));
assert.equal(indicator._label.text, 'AG —');
assert.equal(indicator._status.label.text, 'Example source unavailable');
assert.equal(indicator._selector.visible, false);
assert.equal(indicator._updated.visible, false);
assert.equal(rows().length, 0);
extension.disable();
console.log('Shell renderer model/window selection, details, persistence, stale data and lifecycle tests passed (mock actors)');
