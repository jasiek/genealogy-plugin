# genealogy-mcp

Multi-source MCP server (Python) for genealogy research.

Two source tiers, layered under `src/genealogy_mcp/sources/`:

- **`heredis_*` tools** — read-only access to the user's `.heredis` SQLite
  file. This is the **verified facts** tier: data the user has researched
  and committed locally. See [SCHEMA.md](SCHEMA.md) for the schema.
- **`gedcom_*` tools** — same verified-facts tier loaded from a GEDCOM
  file via `ged4py`. The file is parsed into in-memory dicts at startup;
  queries run as pure Python scans. Activated when `GEDCOM_PATH` (env) or
  `--gedcom-path` (CLI) is set. xref ids (`@I1@`, `@F1@`, `@S1@`) are
  exposed verbatim; events get synthetic ids `<owner_xref>:<TAG>[#<n>]`.
- **`geneteka_*` tools** — live search of https://geneteka.genealodzy.pl
  (Polish parish-record indexes). This is the **research** tier — candidate
  matches, never authoritative. The HTTP client is rate-limited
  (`GENETEKA_MIN_INTERVAL`, default 5s) and uses a browser-style UA
  because the upstream API rejects bot UAs with 403.
- **`genbaza_*` tools** — live search of the genbaza-family regional
  vital-record indexes (`swietogen`, `polishgenealogy`, `warmia`,
  `kurpie`, `pomerania`). All five share the same `/php/getdata.php`
  endpoint with two row layouts; the parser handles both. Rate-limited
  via `GENBAZA_MIN_INTERVAL` (default 5s). Surfaces `scan_url` to
  `metryki.genbaza.pl` when the indexed entry links to a digitised
  image (viewing scans typically requires a free GenBaza account).
- **`lubgens_*` tools** — live search of https://regestry.lubgens.eu
  ("Baza indeksów Lubelszczyzny"), the Lubelskie Korzenie regional
  index of Lublin-area parish registers and USC. The form POSTs to
  `viewpage.php?page_id=1057` and returns a full HTML page with up to
  three result tables (births / marriages / deaths), each capped at
  500 rows. Surfaces `scan_url` (typically szukajwarchiwach.gov.pl or
  familysearch.org) and best-effort `father_name` / `mother_name`
  extracted from the `UWAGI` cell. Rate-limited via
  `LUBGENS_MIN_INTERVAL` (default 5s); browser-style UA required.
- **`basia_*` tools** — live search of https://basia.famula.pl (BaSIA,
  "Baza Systemu Indeksacji Archiwalnej"), the WTG-Gniazdo / PSNC index of
  Wielkopolska (Greater Poland) archival vital records (6.6M+ entries,
  18th-20th c.). Drives the advanced form (POST to `/`); the search is a
  **slow** server-side fuzzy name match — a bare common surname can take
  80s+ or time out upstream and return a truncated page (the parser raises
  a "narrow your query" error in that case), so the client uses a long
  default timeout (`BASIA_TIMEOUT`, default 200s). Narrow with given name /
  year range / place / `record_type` / `similarity`. Results are parsed
  from `result_box` divs into person/parents/spouse/place/year plus
  `scan_url` (szukajwarchiwach / familysearch) and a stable `permalink`.
  Rate-limited via `BASIA_MIN_INTERVAL` (default 5s); browser-style UA.

To add a new source: create `sources/<name>/` with a `tools.py` that exposes
`register(mcp, ...)`, then call it from `server.build_server`. Keep tool
names prefixed with the source so they don't collide.

## Instructions

* To determine if a change was successful, run the test suite.
* If you added a new tool, run uv run  genealogy-mcp-call --list to see that it was added. Additional configuration may be needed for it to become visible.
* Surface any new configuration knob through `_cli_config.py` (`CONFIG_ENTRIES`
  for `--flag`/`ENV_VAR` pairs, `_DISABLE_FLAGS` for `--no-<source>` toggles).
  That single registry drives both the CLI and the env-var channel MCP clients
  use; document the knob in `README.md` too. (There is no `manifest.json` — the
  project ships as a Claude Code plugin via `.claude-plugin/`.)
* Before committing, format code using black.
* Manage dependencies using uv.
* Use python >= 3.11.
* When a change is complete and working, create a descriptive message of what was the objective of the change, and what was changed.
* When in doubt, ask questions and provide options.
* Spawn sub-agents to reduce context pollution (for summarizing, running tools, etc)
* When writing crawling scripts keep in mind the following:
  * These scripts are to produce CSV, with the following columns:
    Miejscowość, Parafia, Rodzaj Ksiegi, Rok od, Rok do
  * Use comma as the separator. Quote if needed, output is UTF-8.
  * The role of these is to act as an index, to select the right source, so it needs to be greppable/fzf/etc.
  * Additonal columns can be added if the source supports it: Powiat, Województwo, Rodzaj źródła
  * For sources with date ranges which are not continuous, produce one row for each range, so for 3 disjoint ranges produce 3 rows, each with a date range.
  * When writing scripts add sanity checks which are going to have the script bail out if the structure of the page has changed, so there is some other quality issue.
