# polish-genealogy-mcp

MCP server for Polish genealogy research. Two tiers:

- **`heredis_*`** — read-only access to your local `.heredis` SQLite file (verified facts).
- **`geneteka_*`** and **`genealogia_w_archiwach_*`** — live search of public Polish parish-record indexes (research candidates).

Live sources are rate-limited (default 5 s between requests) and use a browser-style User-Agent.

## Install

### Claude Desktop (one-click via DXT)

1. Download the latest `polish-genealogy-mcp-<version>.dxt` from the GitHub releases page.
2. Open Claude Desktop → **Settings → Extensions** → drag the `.dxt` onto the window (or click *Install Extension*).
3. When prompted, optionally point **Heredis database** at your `.heredis` file. Leave empty to use only the live research sources.

**Requirements:** [`uv`](https://docs.astral.sh/uv/) on PATH (recommended —
auto-downloads a compatible Python and resolves deps from `pyproject.toml`).
Install with `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`.

If `uv` is unavailable, the wrapper falls back to system Python ≥3.11 +
`pip install` into the extension directory.

### Claude Code / any MCP client (via `uvx`)

Once published to PyPI:

```jsonc
// ~/Library/Application Support/Claude/claude_desktop_config.json
// or via:  claude mcp add polish-genealogy -- uvx polish-genealogy-mcp --heredis-db /path/to/file.heredis
{
  "mcpServers": {
    "polish-genealogy": {
      "command": "uvx",
      "args": ["polish-genealogy-mcp", "--heredis-db", "/path/to/file.heredis"]
    }
  }
}
```

### From source

```bash
git clone https://github.com/jszumiec/heredis-mcp
cd heredis-mcp
uv sync
claude mcp add polish-genealogy -- \
  uv --directory "$PWD" run polish-genealogy-mcp --heredis-db /path/to/file.heredis
```

## Configuration

| Flag / env var | Default | Purpose |
|---|---|---|
| `--heredis-db` / `HEREDIS_DB` | unset | Path to `.heredis` SQLite file. If omitted, only live sources register. |
| `--no-geneteka` | off | Disable the Geneteka source. |
| `--no-genealogia-w-archiwach` | off | Disable the Genealogia w Archiwach source. |
| `GENETEKA_MIN_INTERVAL` | `5` | Seconds between Geneteka requests. |
| `GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL` | `5` | Seconds between Genealogia w Archiwach requests. |
| `GENETEKA_USER_AGENT`, `GENEALOGIA_W_ARCHIWACH_USER_AGENT` | browser UA | Override outgoing User-Agent. |

If neither a Heredis DB nor any live source is enabled, the server refuses to start.

## Develop

```bash
uv sync                  # install deps
uv run pytest            # run tests
uv run black .           # format
```

See [SCHEMA.md](SCHEMA.md) for the Heredis schema and [AGENTS.md](AGENTS.md) for source-tier notes.

## Build a `.dxt` for distribution

```bash
./scripts/build-dxt.sh
```

Produces `dist/polish-genealogy-mcp-<version>.dxt`. The script vendors runtime
deps into `lib/` and packs everything via `@anthropic-ai/dxt`. Requires `uv`
and `npx` on PATH. Attach the resulting file to a GitHub release.

## Publish to PyPI

```bash
uv build
uv publish               # needs UV_PUBLISH_TOKEN or ~/.pypirc
```

## License

MIT
