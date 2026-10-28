#!/usr/bin/env bash
# Install the pinned Playwright test runner into <repo>/.qa/node_modules (outside the workspace, git-excluded)
# and make sure its Chromium build is present. Idempotent; prints the versions.
# Usage: pw-setup.sh [repo-root]
set -euo pipefail

# `timeout` is GNU coreutils; macOS has it as `gtimeout` (brew install coreutils). Neither → run unbounded.
to() { local s="$1"; shift; if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"; elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"; else "$@"; fi; }

# Pinned: released >= 2 weeks before this skill was written; bump deliberately, then re-run this script.
PW_VERSION="1.64.0"
YAML_VERSION="2.9.1"

root="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
qa="$root/.qa"
[[ -f "$qa/playwright.config.ts" ]] || { echo "run: qa.py init <slug> first ($qa/playwright.config.ts missing)" >&2; exit 2; }

cd "$qa"
# A package.json here makes .qa its own npm project, so the repo's pnpm workspace and .npmrc are not touched.
[[ -f package.json ]] || printf '{\n  "name": "qa-local",\n  "private": true\n}\n' > package.json

have="$(node -p "try{require('./node_modules/@playwright/test/package.json').version}catch{''}" 2>/dev/null || true)"
if [[ "$have" != "$PW_VERSION" ]]; then
  to 600 npm install --no-fund --no-audit --loglevel=error --save-exact \
    "@playwright/test@$PW_VERSION" "yaml@$YAML_VERSION"
fi

# Downloads only when this Playwright's Chromium revision is not already cached
# (~/.cache/ms-playwright on Linux, ~/Library/Caches/ms-playwright on macOS).
to 900 npx --no-install playwright install chromium

echo "playwright: $(npx --no-install playwright --version)"
echo "qa dir: $qa"
