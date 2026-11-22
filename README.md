# Antigravity Usage Indicator

A GNOME Shell 45–51 top-bar extension for **Antigravity subscription quota**. Inspired by
[stonega/codex-usage-indicator](https://github.com/stonega/codex-usage-indicator), using its
pinned reference commit `3cc6ff7550a14e141f2ca3de983452c90f93495c` for the panel/menu/settings
interaction. This is an independent, unofficial project, not a Google product.

## Features

- Top bar shows remaining or used quota; automatically selects the lowest remaining bucket.
- Popup lists every quota group/window actually returned by Antigravity, with progress bars,
  reset countdowns, last successful update time, and the local server PID.
- Choose a specific quota bucket in the popup, or return to automatic selection.
- Configurable 60–3600 second polling (default: five minutes) and manual refresh.
- Failed refreshes preserve the last successful result, explicitly marked **Stale**; missing
  data is never presented as an unused or unlimited allowance.
- Supports current quota summaries and a clearly labelled legacy model-quota fallback.

The extension does **not** assume that any plan has fixed five-hour or weekly limits.
It does not calculate token balances, pool unrelated model quotas, or invent missing windows.
This initial version supports Linux/GNOME only; no Xfce adapter or multi-account credential
store is included. You can select an already-running local server by PID.

## Requirements and installation

- GNOME Shell 45–51 (compatibility declared; test on your actual Shell version).
- Linux with readable `/proc`, Python **3.9+**, and GLib schema tools (`glib-compile-schemas`).
- Antigravity open, signed in, and with a workspace open so its local server is running.
  Sandboxed installations may prevent host `/proc` or loopback access and are not guaranteed.

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
When several Antigravity servers exist, automatic discovery prefers the highest PID with
readable quota. The popup identifies the chosen PID. Set **Server process ID** in preferences
to pin a specific server; changing it clears cached data. PID selection is not permanent
account identity: update it after restarting Antigravity or return to `0` for automatic.

To remove: disable the extension and remove
`~/.local/share/gnome-shell/extensions/antigravity-usage-indicator@stone.dev`.

## Data source and privacy

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
Only normalized quota, an optional plan name, timestamp and PID reach GNOME Shell.
No remote Google endpoints, OAuth refresh flows, credential databases, telemetry, or browser
profiles are accessed by the extension. The Antigravity app itself may contact its own service.
HTTP proxies are ignored and redirects are not followed. For the app's local self-signed
HTTPS listener only, certificate verification is disabled; there is no remote TLS bypass.
The helper uses bounded reads/timeouts, while the extension kills readers exceeding 25 seconds
and cancels active readers when disabled or when the server selection changes.

## Troubleshooting

- **No readable local server:** open a workspace, complete sign-in, and check that Antigravity
  is running as the same Linux user as GNOME Shell.
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

Runs Python normalization/discovery/security and loopback HTTP tests, JavaScript syntax and
view tests, **real GJS/Gio subprocess** lifecycle tests, strict schema compilation/settings
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

1. With a signed-in Antigravity workspace, compare every displayed group/window and reset
   time with the app, including zero quota and any weekly caps.
2. Change display mode, panel bucket, refresh interval and server PID; check both the menu
   and preferences. An invalid selected bucket falls back to the lowest remaining quota.
3. Close Antigravity, refresh, verify stale/error states, reopen it, and verify recovery.
4. Disable/re-enable the extension while refreshing; check there are no orphan readers,
   timers, or Shell errors. Check light/dark themes and UI scaling.

## License

GPL-3.0, as provided in `LICENSE`. The reference project's license is also GPL-3.0.
