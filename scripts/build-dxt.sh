#!/usr/bin/env bash
# Build a .dxt bundle for Claude Desktop.
#
# Output: dist/polish-genealogy-mcp-<version>.dxt
#
# Strategy: ship src/ + bin/run.sh + manifest. Runtime deps (fastmcp, httpx,
# pydantic) are pip-installed into the extension directory on first launch,
# matching whatever Python interpreter the user has. This avoids the
# (Python-version × platform) matrix of pre-built native wheels.
#
# Requires: npx (for @anthropic-ai/dxt). Install Node via `brew install node`.

set -euo pipefail

chmod +x bin/run.sh 2>/dev/null || true

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

VERSION="$(grep -E '^version' pyproject.toml | head -1 | cut -d'"' -f2)"
echo "→ building DXT for polish-genealogy-mcp ${VERSION}"

# Validate manifest before packing.
npx --yes @anthropic-ai/dxt validate manifest.json

# Pack via the official DXT tool.
mkdir -p dist
echo "→ packing manifest + src + bin into dist/"
npx --yes @anthropic-ai/dxt pack . "dist/polish-genealogy-mcp-${VERSION}.dxt"

echo "✓ dist/polish-genealogy-mcp-${VERSION}.dxt"
