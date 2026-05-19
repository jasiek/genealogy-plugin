---
name: research-person
description: "Perform research on a person with the given name"
argument-hint: <given-name> <surname> <date-of-some-event-within-their-lifetime>
tools: heredis_* genbaza_* genealogia_* geneteka_* genpod_* lubgens_* Read Grep Bash
---

# Research person skill

Perform genealogy research for person named $0 $1 with an event in their life dated at $2.

## Instructions

For each person, maintain an Obsidian-style markdown file. Name of the file should be persons/<Firstname>_<Lastname>_<ID>.md
where ID is a unique identifier.

Use Obsidian's aliases to make the note cross-referenceable by listing heredis record identifier, and GEDCOM id.
Use assets/research-person-template.md as the template.

- When looking for existing, established evidence, check sources of truth, such as tool:Heredis, or tool:GEDCOM.
  Heredis files or GED files should be in the current directory.
- When referring to other people, use hyperlinks which refer to other files in persons/
- Hyperlinks shouldn't break unless the person hyperlinked doesn't exist yet.
- After editing a note, run `uv run python scripts/check_vault_links.py` from the
  vault root. The script reports two buckets:
  - **Broken** wiki-links and markdown links — must be fixed.
  - **Unresearched persons** — links to person notes that don't exist yet; these
    are acceptable and the script exits 0 if they are the only finding.

