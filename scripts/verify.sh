#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/bootstrap-tools.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
for script in extension.js prefs.js quotaClient.js usageView.js tests/quotaClient.test.js tests/settings.test.js; do
    node --input-type=module --check < "$script"
done
node tests/usageView.test.mjs
node tests/extension.test.mjs
gjs -m tests/quotaClient.test.js
glib-compile-schemas --strict schemas
GSETTINGS_BACKEND=memory GSETTINGS_SCHEMA_DIR="$PWD/schemas" gjs -m tests/settings.test.js
GSETTINGS_BACKEND=memory GSETTINGS_SCHEMA_DIR="$PWD/schemas" gsettings list-recursively org.gnome.shell.extensions.antigravity-usage-indicator
bash scripts/package.sh
python3 - <<'PY'
from pathlib import Path
import json
import zipfile

path = Path("dist/antigravity-usage-indicator@stone.dev.shell-extension.zip")
with zipfile.ZipFile(path) as archive:
    assert archive.testzip() is None
    names = set(archive.namelist())
    required = {"metadata.json", "extension.js", "prefs.js", "quotaClient.js", "usageView.js",
                "helpers/antigravity_usage.py", "helpers/cli_quota.py", "helpers/quota_summary.py", "schemas/gschemas.compiled", "LICENSE", "README.md"}
    assert required <= names, required - names
    assert all(not name.startswith((".git/", ".github/", "tests/")) for name in names)
    assert json.loads(archive.read("metadata.json"))["uuid"] == "antigravity-usage-indicator@stone.dev"
print("Package integrity checks passed")
PY
git diff --check
