---
name: research-person
description: "Perform research on a person with the given name"
argument-hint: <given-name> <surname> <date-of-some-event-within-their-lifetime>
---

# Research person skill

Perform genealogy research for person named $0 $1 with an event in their life dated at $2.

## Instructions

For each person, maintain an Obsidian-style markdown file. Name of the file should be persons/<Firstname>_<Lastname>_<ID>.md
where ID is a unique identifier.

Use Obsidian's aliases to make the note cross-referenceable by listing heredis record identifier, and GEDCOM id.
Use `${CLAUDE_PLUGIN_ROOT}/skills/research-person/template.md` as the template.

- Use uv for running python scripts.
- The set of genealogy sources grows over time — don't assume a fixed list.
  Discover what's available at runtime rather than hardcoding tool names:
  - `uv run --project "${CLAUDE_PLUGIN_ROOT}" genealogy-mcp-call --list`
    — every enabled tool, one per line with a one-line summary.
  - `uv run --project "${CLAUDE_PLUGIN_ROOT}" genealogy-mcp-call --tool <name> --schema`
    — a single tool's input JSON Schema before calling it.
  The same tool names work whether you invoke them as MCP tools or via
  `genealogy-mcp-call --tool <name> key=value` (or `--json '{...}'`).
- Treat sources by tier: `heredis_*` and `gedcom_*` are **verified facts**
  (sources of truth) — check these first; their files should be in the
  current directory. Every other prefix (`geneteka_*`, `genbaza_*`,
  `basia_*`, …) is a **research candidate** — present matches for the user
  to confirm before recording them as fact.
- When referring to other people, use hyperlinks which refer to other files in persons/
- Every person note MUST live under `persons/`. Person-shaped wiki-links
  (`[[Firstname_Lastname_ID]]`) and relative markdown links to person files
  must resolve under `persons/`. If the checker reports a misplaced person
  link, move the target file into `persons/` (preserving the slug) and update
  any markdown links that pointed at the old location; wiki-links resolve by
  slug so they don't need rewriting once the file is moved.
- Hyperlinks shouldn't break unless the person hyperlinked doesn't exist yet.
- After editing a note, run
  `uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/skills/research-person/check_vault_links.py"`
  from the vault root. (`${CLAUDE_PLUGIN_ROOT}` is set by Claude Code to this
  plugin's install dir; `--project` keeps the subprocess cwd in the vault so
  the script picks up the right notes while resolving deps from the plugin's
  `pyproject.toml`.) The script reports three buckets:
  - **Broken** wiki-links and markdown links — must be fixed.
  - **Misplaced person links** — person notes that exist but live outside
    `persons/`. Move them under `persons/` and rewrite affected links.
  - **Unresearched persons** — links to person notes that don't exist yet; these
    are acceptable and the script exits 0 if they are the only finding.
