# Antigravity Usage Indicator

A GNOME Shell 45–51 top-bar extension for **Antigravity subscription quota**. Inspired by
[stonega/codex-usage-indicator](https://github.com/stonega/codex-usage-indicator), using its
pinned reference commit `3cc6ff7550a14e141f2ca3de983452c90f93495c` for the panel/menu/settings
interaction. This is an independent, unofficial project, not a Google product.

## Features

- Top bar shows remaining or used quota; automatically selects the lowest remaining bucket.
- Popup lists every quota group/window actually returned by Antigravity, with progress bars,
  reset countdowns when provided, the capture time, and the CLI/server source.
- Choose a specific quota bucket in the popup, or return to automatic selection.
- Configurable 60–3600 second polling (default: five minutes) and manual refresh.
- Failed refreshes preserve the last successful result, explicitly marked **Stale**; missing
  data is never presented as an unused or unlimited allowance.
- Supports the Antigravity CLI through its quota status-line hook, without a desktop server.
- Retains desktop quota summaries and a clearly labelled legacy model-quota fallback.

The extension does **not** assume that any plan has fixed five-hour or weekly limits.
It does not calculate token balances, pool unrelated model quotas, or invent missing windows.
This initial version supports Linux/GNOME only; no Xfce adapter or multi-account credential
store is included. You can select an already-running local server by PID.

## Requirements and installation

- GNOME Shell 45–51 (compatibility declared; test on your actual Shell version).
- Linux, Python **3.9+**, and GLib schema tools (`glib-compile-schemas`).
- Either a signed-in Antigravity CLI with status-line quota support (setup below), or the
  desktop app open and signed in with a workspace and readable `/proc`. Desktop sandboxes
  may prevent host `/proc` or loopback access and are not guaranteed.

On Debian/Ubuntu, install runtime prerequisites with `sudo apt install python3 libglib2.0-bin`.
No Python packages, API keys, Google OAuth tokens, or Codex CLI files are required.

Build an installable archive from this directory:

```bash
bash scripts/package.sh
gnome-extensions install --force dist/antigravity-usage-indicator@stone.dev.shell-extension.zip
```

Log out and back in (required on Wayland after installing a new extension), then:

```bash
gnome-extensions enable antigravity-usage-indicator@stone.dev
gnome-extensions prefs antigravity-usage-indicator@stone.dev
```

Use the menu's **Panel quota** selector to choose which allowance appears in the top bar.
**Used** is `1 − remaining`; neither mode estimates tokens or absolute subscription capacity.
Automatic mode first uses a recent CLI capture, then tries desktop servers.
When several Antigravity servers exist, desktop discovery prefers the highest PID with
readable quota. The popup identifies the chosen PID. Set **Server process ID** in preferences
to pin a specific desktop server and ignore CLI captures; changing it clears displayed data. PID selection is not permanent
account identity: update it after restarting Antigravity or return to `0` for automatic.

To remove: disconnect the CLI hook as described below, disable the extension, and remove
`~/.local/share/gnome-shell/extensions/antigravity-usage-indicator@stone.dev`.

## Connect Antigravity CLI

Signing in to the CLI alone does not start the desktop quota server the original reader
expected. This integration instead uses the CLI's
[status-line quota JSON](https://antigravity.google/docs/cli/statusline).

1. Install/update the extension, open **Settings**, and click **Connect CLI**.
2. Restart the Antigravity CLI and run a prompt in its interactive session. Keep status-line
   rendering enabled; project settings or `--hide-statusline` can override the user setting.
3. Choose **Refresh now** in the indicator. Leave **Server process ID** at `0`.

The button adds only a `statusLine` command to `~/.gemini/settings.json`, preserving other
settings. It refuses malformed files, symbolic links, and existing custom status lines
rather than silently replacing them. If you already have a custom status line, manually
chain the same stdin JSON to the bridge and your renderer, or opt to replace that setting.
The CLI's `/statusline` command may replace this hook, requiring reconnection.

Equivalent one-time setup from a terminal after installing:

```bash
python3 ~/.local/share/gnome-shell/extensions/antigravity-usage-indicator@stone.dev/helpers/antigravity_usage.py --install-cli-statusline
```

For a custom installation directory, run that installed helper's `--install-cli-statusline`
mode instead. Setup records its absolute path and the current Python interpreter, quoting
paths safely. If you move the extension or remove that Python installation, remove the
old bridge setting before reconnecting.
Older CLI versions without quota status-line data need an update, or use the desktop source.

**Freshness and accounts:** the bridge receives data when the CLI redraws its status line;
refreshing the indicator cannot ask the CLI for new data. It does not use a login token or
make remote requests. Each read rejects captures older than ten minutes (or dated in the
future); at the next indicator refresh, old displayed values are marked **Stale** rather
than presented as current. The timestamp is the capture time, not the indicator's poll time.
With several CLI sessions/accounts, the latest capture wins and is labelled **CLI (latest
session)**. Use a desktop PID to pin a particular desktop account. CLI data provides no
reset timestamps or window lengths, so those remain unavailable.

To disconnect before uninstalling, remove the bridge's `statusLine` entry from
`~/.gemini/settings.json` (or restore your previous custom command), restart the CLI, and
remove `${XDG_CACHE_HOME:-$HOME/.cache}/antigravity-usage-indicator/cli-quota.json`.

## Data source and privacy

### CLI bridge

The helper accepts the status-line JSON on stdin via `--statusline`, validates
`quotas.models[model-id].remaining` as a percentage, and stores only model identifiers,
quota percentages and capture time in the cache file above. The cache directory is private
(`0700`), the file is private (`0600`), and updates are atomic. Input is size-bounded;
malformed or quota-less events invalidate the previous capture. Workspace paths, session
IDs, conversation data and arbitrary JSON fields are never persisted or returned. CLI
OAuth files and credential databases are not read, imported, stored or refreshed.

### Desktop fallback

The Python helper finds **same-user** Antigravity processes (`language_server*` associated
with Antigravity, or `agy`) using `/proc`. It reads the process's ephemeral CSRF argument,
and correlates its socket file descriptors with `/proc/<pid>/net/tcp{,6}` to locate the
server. It sends read-only JSON POST requests to the process's **loopback sockets only**:

1. `/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary`, using
   `groups[].buckets[]`: `remainingFraction`, `resetTime`, `displayName`, and `window`.
2. If no usable summary is returned, `GetUserStatus`, using
   `userStatus.cascadeModelConfigData.clientModelConfigs[].quotaInfo`.

Legacy model quotas do not necessarily expose weekly caps, so the popup says so. A missing
`remainingFraction`, invalid fraction, or absent quota data stays unknown rather than
becoming 100% or 0%. Missing/invalid reset times remain unavailable. A past reset time
says **Reset due — refresh to confirm**, without assuming the server replenished quota.

These are **undocumented internal app interfaces**, not an official supported quota API.
The wire contract was investigated using primary implementation examples:
[QuotaGauge local client](https://github.com/Automaat/QuotaGauge/blob/main/README.md),
[opencode-agy-quota](https://github.com/AlpHa-neXus/opencode-agy-quota), and
[antigravity-quota](https://github.com/brianlovin/antigravity-quota).
Plan policy is not inferred from third-party subscription tables. Google can change this
interface; an unsupported response is an error, not simulated quota. No external repository
is needed at runtime or to verify this project.

Credentials never appear in helper output, settings, cache files, or diagnostic errors.
Only normalized quota, an optional desktop plan name, timestamp and source identifier
reach GNOME Shell.
No remote Google endpoints, OAuth refresh flows, credential databases, telemetry, or browser
profiles are accessed by the extension. The Antigravity app itself may contact its own service.
HTTP proxies are ignored and redirects are not followed. For the app's local self-signed
HTTPS listener only, certificate verification is disabled; there is no remote TLS bypass.
The helper uses bounded reads/timeouts, while the extension kills readers exceeding 25 seconds
and cancels active readers when disabled or when the server selection changes.

## Troubleshooting

- **No quota source / CLI signed in but no data:** connect the CLI hook in Settings, restart
  the CLI, run a prompt and refresh. A CLI login alone is not a local desktop server. For
  desktop mode, open a workspace as the same Linux user as GNOME Shell.
- **CLI stale:** run a prompt in the connected CLI. Refresh reads its last capture; it cannot
  force a CLI update. Check that status-line rendering is enabled and not overridden by
  project settings. No supported quotas means unknown data, not 100% remaining.
- **Cannot connect the CLI:** preserve any existing custom status line and use manual
  chaining, or resolve malformed/unwritable `~/.gemini/settings.json`. Do not share that
  file or raw status-line input; either may contain private configuration.
- **No accessible listener:** inspect your sandbox or `/proc` restrictions. Do not make
  credentials world-readable or expose the server to the network.
- **Local quota unavailable:** verify the app's sign-in/connectivity and try **Refresh now**.
- **Unsupported quota data:** the installed app may use a different internal interface.
  Update the app and report its version with sanitized field names, never tokens or raw status.
- **Stale:** the displayed values are from the shown successful timestamp, not a new reading.

For a one-shot diagnostic (prints normalized quota only):

```bash
python3 helpers/antigravity_usage.py
python3 helpers/antigravity_usage.py --pid 12345
```

## Development and verification

```bash
bash scripts/verify.sh
```

Runs Python CLI setup/hook/cache end-to-end, normalization/discovery/security and loopback
HTTP tests, JavaScript syntax and view tests, **real GJS/Gio subprocess** lifecycle tests, strict schema compilation/settings
load, package construction/integrity, and whitespace checks. All tests use synthetic data,
not personal credentials or a running Antigravity session.

The script uses installed `python3`, `node`, `gjs` and GLib tools. In the application runner,
missing Python/Node are prepared through `uv`/`mise`; missing GJS/GLib packages are downloaded
with APT and extracted **without root** under `/env/antigravity-tools`. Outside that runner,
install those development tools normally, or set `ANTIGRAVITY_TOOLS_DIR` to a writable tools
directory on a Debian-compatible system. Downloads require package-network access, not
GitHub credentials. Build artifacts stay in `schemas/` and `dist/` and are ignored by Git.

### Manual release checks

Automated tests cannot authenticate a real subscription or render a GNOME top bar in a
headless runner. Before publishing, install on the intended GNOME versions and check:

1. Connect a signed-in CLI, restart it and run a prompt; compare displayed model percentages
   with its quota display. Check missing quota, stale capture, reconnect and custom-status-line
   conflicts. With a signed-in desktop workspace, compare every group/window and reset time
   with the app, including zero quota and any weekly caps.
2. Change display mode, panel bucket, refresh interval and server PID; check both the menu
   and preferences. An invalid selected bucket falls back to the lowest remaining quota.
3. Close Antigravity, refresh, verify stale/error states, reopen it, and verify recovery.
4. Disable/re-enable the extension while refreshing; check there are no orphan readers,
   timers, or Shell errors. Check light/dark themes and UI scaling.

## License

GPL-3.0, as provided in `LICENSE`. The reference project's license is also GPL-3.0.
