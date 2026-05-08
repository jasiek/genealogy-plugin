# heredis-mcp

Multi-source MCP server (Python) for genealogy research.

Two source tiers, layered under `src/heredis_mcp/sources/`:

- **`heredis_*` tools** — read-only access to the user's `.heredis` SQLite
  file. This is the **verified facts** tier: data the user has researched
  and committed locally. See [SCHEMA.md](SCHEMA.md) for the schema.
- **`geneteka_*` tools** — live search of https://geneteka.genealodzy.pl
  (Polish parish-record indexes). This is the **research** tier — candidate
  matches, never authoritative. The HTTP client is rate-limited
  (`GENETEKA_MIN_INTERVAL`, default 5s) and uses a browser-style UA
  because the upstream API rejects bot UAs with 403.

To add a new source: create `sources/<name>/` with a `tools.py` that exposes
`register(mcp, ...)`, then call it from `server.build_server`. Keep tool
names prefixed with the source so they don't collide.

## Instructions

* To determine if a change was successful, run the test suite.
* Before committing, format code using black.
* Manage dependencies using uv.
* Use python 3.14.3 (provided via asdf here).
* When a change is complete and working, create a descriptive message of what was the objective of the change, and what was changed.
* When in doubt, ask questions and provide options.
* Spawn sub-agents to reduce context pollution (for summarizing, running tools, etc)

