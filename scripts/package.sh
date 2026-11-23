#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
glib-compile-schemas --strict schemas
mkdir -p dist
python3 - <<'PY'
from pathlib import Path
import zipfile

files = ["metadata.json", "extension.js", "prefs.js", "quotaClient.js", "usageView.js",
         "stylesheet.css", "helpers/antigravity_usage.py", "helpers/cli_quota.py", "helpers/quota_summary.py", "LICENSE", "README.md"]
files += [str(path) for path in sorted(Path("schemas").glob("*")) if path.is_file()]
output = Path("dist/antigravity-usage-indicator@stone.dev.shell-extension.zip")
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for filename in files:
        archive.write(filename)
print(output)
PY
