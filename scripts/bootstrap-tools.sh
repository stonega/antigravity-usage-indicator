#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null; then
    uv python install 3.12
    export PATH="$(dirname "$(uv python find 3.12)"):$PATH"
fi
if ! command -v node >/dev/null; then
    mise install node@22
    export PATH="$(dirname "$(mise which node@22)"):$PATH"
fi
if ! command -v gjs >/dev/null || ! command -v glib-compile-schemas >/dev/null; then
    tools="${ANTIGRAVITY_TOOLS_DIR:-/env/antigravity-tools}"
    if [[ ! -x "$tools/root/usr/bin/gjs" || ! -x "$tools/root/usr/bin/glib-compile-schemas" ]]; then
        mkdir -p "$tools/lists/partial" "$tools/archives/partial" "$tools/root"
        apt_options=(-o "Dir::State::lists=$tools/lists" -o "Dir::Cache::archives=$tools/archives" -o Debug::NoLocking=1)
        apt-get "${apt_options[@]}" update
        apt-get "${apt_options[@]}" --download-only --no-install-recommends -y install gjs libglib2.0-bin
        for package in "$tools"/archives/*.deb; do
            dpkg-deb -x "$package" "$tools/root"
        done
    fi
    multiarch="$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
    export PATH="$tools/root/usr/bin:$PATH"
    export LD_LIBRARY_PATH="$tools/root/usr/lib/$multiarch:$tools/root/lib/$multiarch${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export GI_TYPELIB_PATH="$tools/root/usr/lib/$multiarch/girepository-1.0:$tools/root/usr/lib/$multiarch/gjs/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
fi
