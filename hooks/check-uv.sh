#!/usr/bin/env sh
# SessionStart hook for the genealogy plugin.
#
# The genealogy MCP server is launched via `uv run` (see .mcp.json). If `uv`
# is not on the user's PATH the server never starts and its tools silently
# fail to load — a confusing failure mode. This hook checks for uv at session
# start and, when it is missing, surfaces a clear, actionable message to the
# user and tells Claude the tools are unavailable.
#
# Stays silent (exit 0, no output) on the happy path so it never adds noise.
set -eu

if command -v uv >/dev/null 2>&1; then
  exit 0
fi

# uv not found. Emit SessionStart JSON:
#   systemMessage                       -> shown to the user
#   hookSpecificOutput.additionalContext -> injected into Claude's context
# Newlines are written as literal \n (valid JSON escapes); printf's %s passes
# the backslash-n through untouched.
user_msg="⚠️  genealogy plugin: 'uv' was not found on your PATH.\n\nThe genealogy MCP server is launched with 'uv run', so its tools (heredis_*, geneteka_*, basia_*, …) will not load until uv is installed.\n\nInstall uv → https://docs.astral.sh/uv/getting-started/installation/\n    curl -LsSf https://astral.sh/uv/install.sh | sh\nThen restart Claude Code."

ctx="The 'uv' CLI is not installed on this machine. The genealogy MCP server runs via 'uv run', so all genealogy plugin tools (heredis_*, gedcom_*, geneteka_*, genbaza_*, lubgens_*, basia_*, genpod_*, genealogyindexer_*, familysearch_*) are unavailable until the user installs uv (https://docs.astral.sh/uv) and restarts Claude Code. If asked to use any of these tools, explain this rather than attempting to call them."

printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$user_msg" "$ctx"
exit 0
