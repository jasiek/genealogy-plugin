# genealogy-plugin

Plugin for Claude and other agents to help you do your genealogy research.
Claude knows about where things are located, what historical events took place and how births/marriages/deaths tie together. This plugin
uses different data sources which lets Claude do autonomous research. You can hook up a source of truth in the form of a Heredis file, or
a GEDCOM file and it'll treat it as a source of reference.

- **`heredis_*`** / **`gedcom_*`** — read-only access to your local
  `.heredis` SQLite file or a GEDCOM file (verified facts).
- **`geneteka_*`**, **`genealogia_w_archiwach_*`**, **`genbaza_*`**,
  **`lubgens_*`**, **`basia_*`**, **`genpod_*`** — live search of public
  Polish parish-record indexes (research candidates).
- **`genealogyindexer_*`** — full-text OCR search of
  [Genealogy Indexer](https://genealogyindexer.org): digitised directories,
  yizkor (memorial) books, military lists, histories, and school sources from
  Central/Eastern Europe (research candidates).

Live sources are rate-limited (default 5 s between requests) and use a
browser-style User-Agent.

This repository ships as a Claude Code plugin (the `.claude-plugin/`
directory and the `research-person` skill under `skills/`). You can also
run the MCP server stand-alone against any MCP client.

## Configuration

Every knob can be set three ways. Precedence, highest to lowest:

1. **Command-line flag** — passed to `genealogy-mcp` (or `genealogy-mcp-call`).
2. **Environment variable** — this is the channel MCP clients use.
   `claude mcp add ... -e KEY=value` injects env vars into the MCP server
   entry.
3. **Built-in default**.

Run `genealogy-mcp --help` for the full list. Common knobs:

| CLI flag | Environment variable | Default | Purpose |
|---|---|---|---|
| `--heredis-db PATH` | `HEREDIS_DB` | unset | Path to `.heredis` SQLite file. Heredis tools register only when set. |
| `--gedcom-path PATH` | `GEDCOM_PATH` | unset | Path to a GEDCOM file. GEDCOM tools register only when set. |
| `--no-geneteka` | — | enabled | Disable the Geneteka source. |
| `--no-genealogia-w-archiwach` | — | enabled | Disable the Genealogia w Archiwach source. |
| `--no-genbaza` | — | enabled | Disable the genbaza-family source. |
| `--no-lubgens` | — | enabled | Disable the Lubgens source. |
| `--no-basia` | — | enabled | Disable the BaSIA source. |
| `--no-genealogyindexer` | — | enabled | Disable the Genealogy Indexer source. |
| `--no-genpod` | — | enabled | Disable the GenPod source. |
| `--geneteka-min-interval N` | `GENETEKA_MIN_INTERVAL` | `5` | Seconds between Geneteka requests. |
| `--genealogia-w-archiwach-min-interval N` | `GENEALOGIA_W_ARCHIWACH_MIN_INTERVAL` | `5` | Seconds between Genealogia w Archiwach requests. |
| `--genbaza-min-interval N` | `GENBAZA_MIN_INTERVAL` | `5` | Seconds between genbaza requests. |
| `--lubgens-min-interval N` | `LUBGENS_MIN_INTERVAL` | `5` | Seconds between Lubgens requests. |
| `--basia-min-interval N` | `BASIA_MIN_INTERVAL` | `5` | Seconds between BaSIA requests. |
| `--basia-timeout N` | `BASIA_TIMEOUT` | `200` | Per-request timeout for BaSIA (its fuzzy search is slow). |
| `--genealogyindexer-min-interval N` | `GENEALOGYINDEXER_MIN_INTERVAL` | `5` | Seconds between Genealogy Indexer requests. |
| `--genealogyindexer-timeout N` | `GENEALOGYINDEXER_TIMEOUT` | `90` | Per-request timeout for Genealogy Indexer (common-term pages are large). |
| `--genpod-min-interval N` | `GENPOD_MIN_INTERVAL` | `5` | Seconds between GenPod requests. |
| `--geneteka-user-agent UA` | `GENETEKA_USER_AGENT` | browser UA | Outgoing User-Agent for Geneteka. |
| `--genealogia-w-archiwach-user-agent UA` | `GENEALOGIA_W_ARCHIWACH_USER_AGENT` | browser UA | Outgoing User-Agent for Genealogia w Archiwach. |
| `--genbaza-user-agent UA` | `GENBAZA_USER_AGENT` | browser UA | Outgoing User-Agent for genbaza. |
| `--lubgens-user-agent UA` | `LUBGENS_USER_AGENT` | browser UA | Outgoing User-Agent for Lubgens. |
| `--basia-user-agent UA` | `BASIA_USER_AGENT` | browser UA | Outgoing User-Agent for BaSIA. |
| `--genealogyindexer-user-agent UA` | `GENEALOGYINDEXER_USER_AGENT` | browser UA | Outgoing User-Agent for Genealogy Indexer. |
| `--genpod-user-agent UA` | `GENPOD_USER_AGENT` | browser UA | Outgoing User-Agent for GenPod. |
| `--genpod-username NAME` | `GENPOD_USERNAME` | unset | Required to enable `genpod_*` tools. |
| `--genpod-password PW` | `GENPOD_PASSWORD` | unset | Required to enable `genpod_*` tools. |

If neither a Heredis DB nor any live source is enabled, the server refuses to start.

## Testing tools from the command line

`genealogy-mcp-call` invokes any registered tool without spinning up
an MCP client. It honours the same config precedence as the server.

```bash
# list every registered tool
genealogy-mcp-call --heredis-db Szumiec.heredis --list

# show a tool's input JSON Schema
genealogy-mcp-call --tool geneteka_search --schema

# invoke with key=value (each value is JSON-parsed; falls back to string)
genealogy-mcp-call --heredis-db Szumiec.heredis \
    --tool heredis_search_persons surname=Szumiec limit=5

# or pass the full argument object as JSON
genealogy-mcp-call --tool geneteka_search \
    --json '{"region":"06mp","surname":"Szumiec"}'
```

## Develop

```bash
uv sync                  # install deps
uv run pytest            # run tests
uv run black .           # format
```

See [SCHEMA.md](SCHEMA.md) for the Heredis schema and [AGENTS.md](AGENTS.md) for source-tier notes.

## Publish to PyPI

```bash
uv build
uv publish               # needs UV_PUBLISH_TOKEN or ~/.pypirc
```

## License

MIT
