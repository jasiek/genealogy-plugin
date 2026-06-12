# SessionStart hook (PowerShell variant) for the genealogy plugin.
#
# Mirrors check-uv.sh for Windows hosts where Claude Code runs hooks via
# PowerShell (i.e. Git Bash is not installed). The genealogy MCP server is
# launched with `uv run`; if `uv` is missing the server never starts and its
# tools silently fail to load. This warns the user instead.
#
# Stays silent (exit 0, no output) on the happy path.
$ErrorActionPreference = 'Stop'

if (Get-Command uv -ErrorAction SilentlyContinue) {
    exit 0
}

# uv not found. Emit the same SessionStart JSON shape as check-uv.sh:
#   systemMessage                        -> shown to the user
#   hookSpecificOutput.additionalContext -> injected into Claude's context
# ConvertTo-Json handles all escaping (newlines, non-ASCII) for us.
$userMsg = @"
⚠️  genealogy plugin: 'uv' was not found on your PATH.

The genealogy MCP server is launched with 'uv run', so its tools (heredis_*, geneteka_*, basia_*, …) will not load until uv is installed.

Install uv → https://docs.astral.sh/uv/getting-started/installation/
    irm https://astral.sh/uv/install.ps1 | iex
Then restart Claude Code.
"@

$ctx = "The 'uv' CLI is not installed on this machine. The genealogy MCP server runs via 'uv run', so all genealogy plugin tools (heredis_*, gedcom_*, geneteka_*, genbaza_*, lubgens_*, basia_*, genpod_*, genealogyindexer_*, familysearch_*) are unavailable until the user installs uv (https://docs.astral.sh/uv) and restarts Claude Code. If asked to use any of these tools, explain this rather than attempting to call them."

$payload = [ordered]@{
    systemMessage      = $userMsg
    hookSpecificOutput = [ordered]@{
        hookEventName     = 'SessionStart'
        additionalContext = $ctx
    }
}

$payload | ConvertTo-Json -Compress -Depth 5
exit 0
