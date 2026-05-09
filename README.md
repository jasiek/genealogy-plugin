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

Every knob can be set three ways. Precedence, highest to lowest:

1. **Command-line flag** — passed to `polish-genealogy-mcp` (or `polish-genealogy-mcp-call`).
2. **Environment variable** — this is also the channel Claude Desktop and
   Claude Code use. The DXT manifest exposes the most common knobs as
   user-config fields, and `claude mcp add ... -e KEY=value` injects env
   vars into the MCP server entry.
3. **Built-in default**.

Run `polish-genealogy-mcp --help` for the full list. Common knobs:

| CLI flag | Environment variable | Default | Purpose |
|---|---|---|---|
| `--heredis-db PATH` | `HEREDIS_DB` | unset | Path to `.heredis` SQLite file. Heredis tools register only when set. |
| `--no-geneteka` | — | enabled | Disable the Geneteka source. |
| `--no-genealogia-w-archiwach` | — | enabled | Disable the Genealogia w Archiwach source. |
| `--no-genbaza` | — | enabled | Disable the genbaza-family source. |
| `--no-lubgens` | — | enabled | Disable the Lubgens source. |
| `--no-genpod` | — | enabled | Disable the GenPod source. |
| `--geneteka-min-interval N` | `GENETEKA_MIN_INTERVAL` | `5` | Seconds between Geneteka requests. |
| `--genealogia-w-archiwach-min-interval N` | `GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL` | `5` | Seconds between Genealogia w Archiwach requests. |
| `--genbaza-min-interval N` | `GENBAZA_MIN_INTERVAL` | `5` | Seconds between genbaza requests. |
| `--lubgens-min-interval N` | `LUBGENS_MIN_INTERVAL` | `5` | Seconds between Lubgens requests. |
| `--genpod-min-interval N` | `GENPOD_MIN_INTERVAL` | `5` | Seconds between GenPod requests. |
| `--geneteka-user-agent UA` | `GENETEKA_USER_AGENT` | browser UA | Outgoing User-Agent for Geneteka. |
| `--genealogia-w-archiwach-user-agent UA` | `GENEALOGIA_W_ARCHIWACH_USER_AGENT` | browser UA | Outgoing User-Agent for Genealogia w Archiwach. |
| `--genbaza-user-agent UA` | `GENBAZA_USER_AGENT` | browser UA | Outgoing User-Agent for genbaza. |
| `--lubgens-user-agent UA` | `LUBGENS_USER_AGENT` | browser UA | Outgoing User-Agent for Lubgens. |
| `--genpod-user-agent UA` | `GENPOD_USER_AGENT` | browser UA | Outgoing User-Agent for GenPod. |
| `--genpod-username NAME` | `GENPOD_USERNAME` | unset | Required to enable `genpod_*` tools. |
| `--genpod-password PW` | `GENPOD_PASSWORD` | unset | Required to enable `genpod_*` tools. |

If neither a Heredis DB nor any live source is enabled, the server refuses to start.

### Examples

```bash
# CLI flag wins over env var
GENETEKA_MIN_INTERVAL=2 polish-genealogy-mcp --geneteka-min-interval 10  # → 10s

# Claude Code: pass config as env vars
claude mcp add polish-genealogy \
  -e HEREDIS_DB=/path/to/file.heredis \
  -e GENETEKA_MIN_INTERVAL=3 \
  -- uvx polish-genealogy-mcp
```

## Testing tools from the command line

`polish-genealogy-mcp-call` invokes any registered tool without spinning up
an MCP client. It honours the same config precedence as the server.

```bash
# list every registered tool
polish-genealogy-mcp-call --heredis-db Szumiec.heredis --list

# show a tool's input JSON Schema
polish-genealogy-mcp-call --tool geneteka_search --schema

# invoke with key=value (each value is JSON-parsed; falls back to string)
polish-genealogy-mcp-call --heredis-db Szumiec.heredis \
    --tool heredis_search_persons surname=Szumiec limit=5

# or pass the full argument object as JSON
polish-genealogy-mcp-call --tool geneteka_search \
    --json '{"region":"06mp","surname":"Szumiec"}'
```

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
